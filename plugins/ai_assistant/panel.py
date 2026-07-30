from __future__ import annotations

import html
from typing import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from openchem.plugins.async_task import run_async
from openchem.plugins.context import PluginContext

from .context_builder import MoleculeContextCache
from .providers import AIMessage, AIProvider, AIProviderError, AIRequest, AIResponse, ToolCall
from .tools import AVAILABLE_TOOLS, TOOL_REGISTRY

# A runaway model that keeps requesting tools forever must not hang the
# chat indefinitely -- bounds the request/tool-result loop in
# AIAssistantPanel._run_completion.
MAX_TOOL_ITERATIONS = 5

_MODEL_PRESETS: dict[str, list[str]] = {
    # Current Claude model ids, not the stale "claude-sonnet-4-5" that used
    # to be AnthropicProvider's only option here -- still editable, so a
    # future/renamed model can always be typed in directly.
    "anthropic": ["claude-sonnet-5", "claude-opus-5", "claude-fable-5", "claude-haiku-4-5-20251001"],
    "openai": ["gpt-4o-mini", "gpt-4o"],
    "ollama": ["llama3.1", "qwen2.5-coder:14b", "mistral", "phi3"],
    # Blank means "let the claude CLI use its own configured default" --
    # ClaudeCLIProvider.default_model is "" for exactly this reason.
    "claude_cli": ["", "sonnet", "opus", "fable", "haiku"],
}

SYSTEM_PROMPT_PREFIX = (
    "You are a chemistry assistant embedded in OpenChem Studio, a molecular "
    "editor. Explain results, suggest workflows, and generate SMARTS queries "
    "or Python snippets as plain text for the user to review and apply "
    "themselves. Never claim to have modified the user's project yourself — "
    "you have no ability to. Here is the currently selected molecule:\n\n"
)


class _ChunkSignal(QObject):
    """A minimal QObject just to hold a Signal -- `provider.stream()` runs
    on a worker thread (via `run_async`), and emitting a Qt signal from
    there is this codebase's already-established cross-thread-safe
    pattern (same reasoning `EventBus.publish` relies on: a signal emit
    queues onto the thread that connected to it, the GUI thread here).
    A plain callback into a QWidget method from a worker thread would not
    be thread-safe the same way.
    """

    chunk_received = Signal(str)


class _ProviderSettingsDialog(QDialog):
    """API-key providers (Anthropic/OpenAI/Ollama) and ClaudeCLIProvider
    need genuinely different configuration -- the latter authenticates via
    a locally-logged-in `claude` CLI session, so an "API key" field would
    be actively misleading. `provider.requires_api_key` decides which of
    the two this dialog shows.
    """

    def __init__(
        self, context: PluginContext, provider_id: str, provider: AIProvider, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Configure {provider_id}")
        self._context = context
        self._provider_id = provider_id
        self._requires_api_key = provider.requires_api_key

        form = QFormLayout()
        note: QLabel | None = None

        if self._requires_api_key:
            self._api_key_edit = QLineEdit(self)
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._api_key_edit.setText(context.secrets.get(f"{provider_id}_api_key") or "")
            form.addRow("API key:", self._api_key_edit)
        else:
            self._cli_path_edit = QLineEdit(self)
            self._cli_path_edit.setText(context.settings.get(f"{provider_id}_cli_path", ""))
            browse_button = QPushButton("Browse...", self)
            browse_button.clicked.connect(self._on_browse_clicked)
            path_row = QHBoxLayout()
            path_row.addWidget(self._cli_path_edit)
            path_row.addWidget(browse_button)
            form.addRow("CLI path (optional):", path_row)
            note = QLabel(
                "Uses your local Claude Code CLI login -- run 'claude' once in a "
                "terminal to sign in with your claude.ai subscription (Pro/Max), no "
                "separate Anthropic API key or billing needed. Leave the path blank "
                "to auto-detect 'claude' on PATH.",
                self,
            )
            note.setWordWrap(True)

        self._model_combo = QComboBox(self)
        self._model_combo.setEditable(True)
        self._model_combo.addItems(_MODEL_PRESETS.get(provider_id, []))
        self._model_combo.setCurrentText(context.settings.get(f"{provider_id}_model", provider.default_model))
        form.addRow("Model:", self._model_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        if note is not None:
            layout.addWidget(note)
        layout.addWidget(buttons)

    def _on_browse_clicked(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Select claude executable")
        if path_str:
            self._cli_path_edit.setText(path_str)

    def accept(self) -> None:
        if self._requires_api_key:
            self._context.secrets.set(f"{self._provider_id}_api_key", self._api_key_edit.text())
        else:
            self._context.settings.set(f"{self._provider_id}_cli_path", self._cli_path_edit.text())
        self._context.settings.set(f"{self._provider_id}_model", self._model_combo.currentText())
        super().accept()


class AIAssistantPanel(QWidget):
    """Chat UI for the AI assistant."""

    def __init__(
        self,
        context: PluginContext,
        providers: dict[str, AIProvider],
        cache: MoleculeContextCache,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._context = context
        self._providers = providers
        self._cache = cache
        self._history: list[AIMessage] = []
        self._stream_active = False
        # Keeps the current send's chunk-signal QObject alive for the
        # worker thread's lifetime -- same reasoning `async_task.py`'s
        # `_IN_FLIGHT_TASKS` documents for its own PluginAsyncTask.
        self._current_stream_signal: _ChunkSignal | None = None

        self._provider_combo = QComboBox(self)
        self._provider_combo.addItems(list(providers.keys()))
        last_provider = context.settings.get("last_provider", "anthropic")
        if last_provider in providers:
            self._provider_combo.setCurrentText(last_provider)
        self._provider_combo.currentTextChanged.connect(
            lambda value: context.settings.set("last_provider", value)
        )

        self._configure_button = QPushButton("Configure...", self)
        self._configure_button.clicked.connect(self._on_configure_clicked)

        self._transcript = QTextEdit(self)
        self._transcript.setReadOnly(True)

        self._input = QPlainTextEdit(self)
        self._input.setPlaceholderText("Ask about the selected molecule...")
        self._input.setMaximumHeight(80)

        self._send_button = QPushButton("Send", self)
        self._send_button.clicked.connect(self._on_send_clicked)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Provider:"))
        top_bar.addWidget(self._provider_combo)
        top_bar.addWidget(self._configure_button)
        top_bar.addStretch()

        input_bar = QHBoxLayout()
        input_bar.addWidget(self._input)
        input_bar.addWidget(self._send_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top_bar)
        layout.addWidget(self._transcript)
        layout.addLayout(input_bar)

    def prefill_and_focus(self, text: str) -> None:
        self._input.setPlainText(text)
        self._input.setFocus()

    def _on_configure_clicked(self) -> None:
        provider_id = self._provider_combo.currentText()
        provider = self._providers[provider_id]
        dialog = _ProviderSettingsDialog(self._context, provider_id, provider, self)
        dialog.exec()

    def _on_send_clicked(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        self._append_transcript("You", text)
        self._history.append(AIMessage(role="user", content=text))

        provider_id = self._provider_combo.currentText()
        provider = self._providers[provider_id]
        api_key = self._context.secrets.get(f"{provider_id}_api_key") or ""
        model = self._context.settings.get(f"{provider_id}_model", provider.default_model)
        system_context = SYSTEM_PROMPT_PREFIX + self._cache.build_context_text()
        history_snapshot = list(self._history)

        self._stream_active = False
        signal = _ChunkSignal()
        signal.chunk_received.connect(self._on_chunk_received)
        self._current_stream_signal = signal

        self._send_button.setEnabled(False)
        run_async(
            lambda: self._run_completion(
                provider, system_context, history_snapshot, model, api_key, signal.chunk_received.emit
            ),
            AIProviderError,
            self._on_response,
            self._on_error,
        )

    def _run_completion(
        self,
        provider: AIProvider,
        system_context: str,
        messages: list[AIMessage],
        model: str,
        api_key: str,
        on_chunk: Callable[[str], None],
    ) -> AIResponse:
        """Runs off the GUI thread (called from `run_async`'s lambda).

        Streams every turn via `provider.stream()` — including any
        intermediate turns where the model requests a tool — rather than
        a separate non-streaming tool-call path, since `stream()` already
        surfaces `tool_calls` on its returned `AIResponse` exactly like
        `complete()` does (see providers.py). Bounded to
        `MAX_TOOL_ITERATIONS` so a model that keeps requesting tools can't
        hang the chat indefinitely. Every tool call is executed locally
        against a small fixed registry (`ai_assistant/tools.py`) — the
        model never gets direct tool access of its own.
        """
        messages = list(messages)
        tools = AVAILABLE_TOOLS if provider.supports_tools else None
        response = AIResponse(text="")
        for _ in range(MAX_TOOL_ITERATIONS):
            request = AIRequest(system_context=system_context, messages=messages, model=model, api_key=api_key)
            response = provider.stream(request, on_chunk, tools)
            if not response.tool_calls:
                return response
            messages.append(AIMessage(role="assistant", content=response.text, tool_calls=response.tool_calls))
            for tool_call in response.tool_calls:
                messages.append(
                    AIMessage(role="tool", content=self._execute_tool(tool_call), tool_call_id=tool_call.id)
                )
        return response

    def _execute_tool(self, tool_call: ToolCall) -> str:
        handler = TOOL_REGISTRY.get(tool_call.name)
        if handler is None:
            return f"Unknown tool: {tool_call.name}"
        try:
            return handler(**tool_call.input)
        except Exception as exc:  # noqa: BLE001 - a bad tool call must not crash the loop
            return f"Tool {tool_call.name} failed: {exc}"

    def _on_chunk_received(self, chunk: str) -> None:
        if not chunk:
            return
        if not self._stream_active:
            self._stream_active = True
            self._transcript.append(f"<b>{html.escape(self._provider_combo.currentText())}:</b> ")
        cursor = self._transcript.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(chunk)
        self._transcript.setTextCursor(cursor)

    def _on_response(self, response: AIResponse) -> None:
        self._send_button.setEnabled(True)
        self._history.append(AIMessage(role="assistant", content=response.text))
        if not self._stream_active:
            # Reached if a provider's stream() never actually called
            # on_chunk (e.g. an empty final reply) -- render it now so a
            # blank turn isn't silently dropped from the transcript.
            self._append_transcript(self._provider_combo.currentText(), response.text)
        self._stream_active = False
        self._current_stream_signal = None

    def _on_error(self, message: str) -> None:
        self._send_button.setEnabled(True)
        self._stream_active = False
        self._current_stream_signal = None
        self._append_transcript("Error", message)

    def _append_transcript(self, speaker: str, text: str) -> None:
        # Chemistry text (SMARTS, Python snippets) routinely contains
        # `<`/`>`/`&`, which QTextEdit.append() would otherwise interpret
        # as HTML.
        escaped = html.escape(text).replace("\n", "<br>")
        self._transcript.append(f"<b>{html.escape(speaker)}:</b> {escaped}")
