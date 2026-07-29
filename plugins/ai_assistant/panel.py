from __future__ import annotations

import html

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
from .providers import AIMessage, AIProvider, AIProviderError, AIRequest, AIResponse

SYSTEM_PROMPT_PREFIX = (
    "You are a chemistry assistant embedded in OpenChem Studio, a molecular "
    "editor. Explain results, suggest workflows, and generate SMARTS queries "
    "or Python snippets as plain text for the user to review and apply "
    "themselves. Never claim to have modified the user's project yourself — "
    "you have no ability to. Here is the currently selected molecule:\n\n"
)


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

        self._model_edit = QLineEdit(self)
        self._model_edit.setText(context.settings.get(f"{provider_id}_model", provider.default_model))
        form.addRow("Model:", self._model_edit)

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
        self._context.settings.set(f"{self._provider_id}_model", self._model_edit.text())
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

        request = AIRequest(
            system_context=SYSTEM_PROMPT_PREFIX + self._cache.build_context_text(),
            messages=list(self._history),
            model=model,
            api_key=api_key,
        )

        self._send_button.setEnabled(False)
        run_async(lambda: provider.complete(request), AIProviderError, self._on_response, self._on_error)

    def _on_response(self, response: AIResponse) -> None:
        self._send_button.setEnabled(True)
        self._history.append(AIMessage(role="assistant", content=response.text))
        self._append_transcript(self._provider_combo.currentText(), response.text)

    def _on_error(self, message: str) -> None:
        self._send_button.setEnabled(True)
        self._append_transcript("Error", message)

    def _append_transcript(self, speaker: str, text: str) -> None:
        # Chemistry text (SMARTS, Python snippets) routinely contains
        # `<`/`>`/`&`, which QTextEdit.append() would otherwise interpret
        # as HTML.
        escaped = html.escape(text).replace("\n", "<br>")
        self._transcript.append(f"<b>{html.escape(speaker)}:</b> {escaped}")
