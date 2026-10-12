from __future__ import annotations

import html
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.result_envelope import outcome_envelope
from openchem.domain.run_lifecycle import RunOutcome, RunState
from openchem.plugins.async_task import run_async
from openchem.plugins.context import PluginContext

from .bridge import BridgeEvent, ToolBridge, bounded_json
from .calculation_tools import CALCULATION_HANDLERS, CALCULATION_TOOLS
from .context_builder import MoleculeContextCache
from .providers import AIMessage, AIProvider, AIProviderError, AIRequest, AIResponse, ToolCall
from .tools import AVAILABLE_TOOLS, TOOL_REGISTRY, validate_arguments

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
    "You are a chemistry assistant embedded in OpenChem Studio, a molecular editor. Explain results, suggest "
    "workflows, and generate SMARTS queries or Python snippets as plain text for the user to review and apply "
    "themselves.\n\n"
    "When tools are offered, they read this application's own results and run its calculators. Use them instead of "
    "answering from memory whenever a question is about a number, a property or a method for the selected molecule: "
    "find_calculators and describe_calculator say what exists, what each needs and whether you may run it; "
    "read_results returns what has already been computed; run_calculator runs one. A run you request is recorded in "
    "the user's project and appears in their Results like one they ran themselves, so run only what the question "
    "needs. Some calculators need the user to approve a preview first: tell them it is waiting for their approval, "
    "do not ask again, and never imply you approved or started it.\n\n"
    "Rules for numbers: state a value only if a tool result contains it, with its units and method. If a result is "
    "'historical' or 'unverifiable' it does not describe the molecule as it is now, and if a calculator was refused "
    "or has not run, say exactly that and quote the application's reason; never present a missing result as zero or "
    "fill it in from memory. Results are for the molecule that was selected when the user sent their message; you "
    "cannot name another. Here is the currently selected molecule:\n\n"
)

#: What the ledger says about a run in each state, in the user's terms.
_STATE_LABELS = {
    "previewed": "waiting for your approval",
    "running": "running",
    "completed": "completed",
    "refused": "the calculator declined",
    "failed": "failed",
    "cancelled": "cancelled; nothing was started",
    "invalidated": "withdrawn",
    "rejected": "not started",
    "timed_out": "still running",
}


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


class _BridgeSignal(QObject):
    """Carries a `BridgeEvent` from the provider's worker thread to the GUI thread, for the same
    reason `_ChunkSignal` exists: a tool runs on the worker and must never touch a widget."""

    event = Signal(object)


class _PreviewCard(QFrame):
    """One request that needs the user's decision. Approve and Cancel are the ONLY way it ever starts.

    The card is drawn from the preview the application prepared, never from anything the model wrote, so
    what the user approves is what the application would run.
    """

    approve_clicked = Signal(str)
    cancel_clicked = Signal(str)

    def __init__(self, preparation: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.run_id: str = str(preparation.get("run_id", ""))
        self.setObjectName("AIPreviewCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        title = QLabel("<b>Approve this calculation?</b>", self)
        body = QLabel("\n".join(preparation.get("preview", [])), self)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.approve_button = QPushButton("Approve", self)
        self.approve_button.setObjectName("AIPreviewApprove")
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setObjectName("AIPreviewCancel")
        self.approve_button.clicked.connect(self._on_approve)
        self.cancel_button.clicked.connect(self._on_cancel)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.approve_button)
        buttons.addWidget(self.cancel_button)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addLayout(buttons)

    def _on_approve(self, _checked: bool = False) -> None:
        self.approve_clicked.emit(self.run_id)

    def _on_cancel(self, _checked: bool = False) -> None:
        self.cancel_clicked.emit(self.run_id)


class _ServiceCard(QFrame):
    """What a job that runs from its own panel (ORCA, Vina) would take, and whether this machine is ready.

    There is NO Approve here, because there is nothing to approve: the assistant cannot start these, so the
    card offers the one thing that can help, opening the panel that owns the job.
    """

    open_clicked = Signal(str)
    dismiss_clicked = Signal(str)

    def __init__(self, key: str, preview: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.panel_id: str = str(preview.get("panel_id", ""))
        self.setObjectName("AIServicePreviewCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        lines = [line for line in preview.get("summary", []) if line]
        for requirement in preview.get("requirements", []):
            mark = "ready" if requirement.get("ok") else "missing"
            fix = f" ({requirement['how_to_fix']})" if requirement.get("how_to_fix") else ""
            lines.append(f"[{mark}] {requirement.get('what', '')}{fix}")
        title = QLabel(f"<b>{html.escape(str(preview.get('name', 'Calculation')))}</b>: run it from the "
                       f"{html.escape(str(preview.get('run_it_from', 'its own panel')))}", self)
        title.setWordWrap(True)
        body = QLabel("\n".join(lines), self)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.open_button = QPushButton(f"Open {preview.get('run_it_from', 'panel')}", self)
        self.open_button.setObjectName("AIServiceOpen")
        self.dismiss_button = QPushButton("Dismiss", self)
        self.dismiss_button.setObjectName("AIServiceDismiss")
        self.open_button.clicked.connect(self._on_open)
        self.dismiss_button.clicked.connect(self._on_dismiss)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.dismiss_button)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addLayout(buttons)

    def _on_open(self, _checked: bool = False) -> None:
        self.open_clicked.emit(self.panel_id)

    def _on_dismiss(self, _checked: bool = False) -> None:
        self.dismiss_clicked.emit(self.key)


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
        # Tool events cross from the worker thread through this; see `_BridgeSignal`.
        self._bridge_signal = _BridgeSignal()
        self._bridge_signal.event.connect(self._on_bridge_event)
        #: run id -> (calculator, molecule), so the ledger can name a run when its end is announced.
        self._runs: dict[str, tuple[str, str]] = {}
        #: previews waiting on the user. Only a run that WAS a preview is told to the model afterwards.
        self._awaiting: set[str] = set()
        #: what happened to a preview since the last message, held to go with the next one.
        self._notes: list[str] = []
        self._cards: dict[str, _PreviewCard] = {}
        self._service_cards: dict[str, _ServiceCard] = {}
        self._service_count = 0
        self._ledger_rows: dict[str, QListWidgetItem] = {}
        self._refusal_count = 0

        self._provider_combo = QComboBox(self)
        self._provider_combo.addItems(list(providers.keys()))
        last_provider = context.settings.get("last_provider", "anthropic")
        if last_provider in providers:
            self._provider_combo.setCurrentText(last_provider)
        self._provider_combo.currentTextChanged.connect(
            lambda value: context.settings.set("last_provider", value)
        )
        self._provider_combo.currentTextChanged.connect(lambda _value: self._refresh_setup_hint())
        self._provider_combo.currentTextChanged.connect(lambda _value: self._refresh_privacy())

        self._configure_button = QPushButton("Configure...", self)
        self._configure_button.clicked.connect(self._on_configure_clicked)

        # Says what to do when the chosen provider cannot answer yet. Without
        # it a first open was a blank chat above a provider box defaulting to
        # one with no key, and the first sign anything was missing was an
        # error after Send. Hidden whenever there is nothing to say.
        self._setup_hint = QLabel(self)
        self._setup_hint.setWordWrap(True)
        self._setup_hint.setVisible(False)

        self._transcript = QTextEdit(self)
        self._transcript.setReadOnly(True)

        self._input = QPlainTextEdit(self)
        self._input.setPlaceholderText("Ask about the selected molecule...")
        self._input.setMaximumHeight(80)

        self._send_button = QPushButton("Send", self)
        self._send_button.clicked.connect(self._on_send_clicked)

        # What leaves this machine. Tool results are part of the conversation, so with a remote provider
        # the calculator results the assistant reads go to it; the person is told which case this is.
        self._privacy = QLabel(self)
        self._privacy.setWordWrap(True)
        self._privacy.setObjectName("AIPrivacyNote")

        # Previews waiting for a decision, and a ledger of everything the assistant asked for. Both stay
        # hidden until there is something to show.
        self._cards_host = QWidget(self)
        self._cards_layout = QVBoxLayout(self._cards_host)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_host.setVisible(False)
        self._ledger_label = QLabel("Calculations the assistant has asked for", self)
        self._ledger = QListWidget(self)
        self._ledger.setObjectName("AICalculationLedger")
        # A refusal's reason is the part worth reading and it is long: wrap it. A row that scrolls sideways
        # was measured in the real window (the first row read "... conformer_policy must be or", cut at the
        # panel's edge, with a scroll bar to find the rest).
        self._ledger.setWordWrap(True)
        self._ledger.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._ledger.setTextElideMode(Qt.TextElideMode.ElideNone)
        self._ledger.setMaximumHeight(160)
        self._ledger_label.setVisible(False)
        self._ledger.setVisible(False)

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
        layout.addWidget(self._setup_hint)
        layout.addWidget(self._transcript)
        layout.addWidget(self._cards_host)
        layout.addWidget(self._ledger_label)
        layout.addWidget(self._ledger)
        layout.addLayout(input_bar)
        layout.addWidget(self._privacy)
        self._refresh_setup_hint()
        self._refresh_privacy()
        context.calculation_approvals.on_finished(self._on_run_finished)

    def prefill_and_focus(self, text: str) -> None:
        self._input.setPlainText(text)
        self._input.setFocus()

    def focus_input(self) -> None:
        """Put the cursor in the question box without changing what is in it."""
        self._input.setFocus()

    def setup_hint(self) -> str:
        """What the person has to do before the chosen provider can answer, or "".

        Only claims what can be known without a network call: an API-key
        provider with no stored key. A provider reached through a local CLI
        or server cannot be checked here, so it says nothing rather than
        guess, and an unreachable one still surfaces as an error on Send.
        """
        provider_id = self._provider_combo.currentText()
        provider = self._providers.get(provider_id)
        if provider is None or not provider.requires_api_key:
            return ""
        if getattr(provider, "_base_url", None):
            return ""  # a local OpenAI-compatible server (Ollama) takes no key
        try:
            has_key = bool(self._context.secrets.get(f"{provider_id}_api_key"))
        except Exception:  # noqa: BLE001 - no usable keychain is a reason to ask, not to crash
            has_key = False
        if has_key:
            return ""
        return (
            f"No API key is set for {provider_id}. Click Configure... to add one, "
            f"or choose claude_cli to use your claude.ai login instead."
        )

    def _refresh_setup_hint(self) -> None:
        hint = self.setup_hint()
        self._setup_hint.setText(hint)
        self._setup_hint.setVisible(bool(hint))

    def _on_configure_clicked(self) -> None:
        provider_id = self._provider_combo.currentText()
        provider = self._providers[provider_id]
        dialog = _ProviderSettingsDialog(self._context, provider_id, provider, self)
        dialog.exec()
        self._refresh_setup_hint()

    def _on_send_clicked(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        self._append_transcript("You", text)
        # What happened to a preview since the last message goes ahead of this one, so the model learns it
        # as the application's note and the roles still alternate. The transcript shows the user's own words.
        notes, self._notes = self._notes, []
        self._history.append(AIMessage(role="user", content="\n\n".join([*notes, text])))

        provider_id = self._provider_combo.currentText()
        provider = self._providers[provider_id]
        api_key = self._context.secrets.get(f"{provider_id}_api_key") or ""
        model = self._context.settings.get(f"{provider_id}_model", provider.default_model)
        system_context = SYSTEM_PROMPT_PREFIX + self._cache.build_context_text()
        history_snapshot = list(self._history)
        # THE TURN IS FROZEN HERE, ON THE GUI THREAD, AT THE MOMENT OF SEND. Every calculator tool the model
        # calls in this reply reads that and nothing else, so selecting another molecule while it streams
        # cannot change what an answer was based on.
        bridge = None
        if provider.supports_tools:
            bridge = ToolBridge(
                self._context.calculations, self._context.calculations.begin_turn(), self._bridge_signal.event.emit
            )

        self._stream_active = False
        signal = _ChunkSignal()
        signal.chunk_received.connect(self._on_chunk_received)
        self._current_stream_signal = signal

        self._send_button.setEnabled(False)
        run_async(
            lambda: self._run_completion(
                provider, system_context, history_snapshot, model, api_key, signal.chunk_received.emit, bridge
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
        bridge: ToolBridge | None = None,
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

        `bridge` is the turn's frozen access to the calculators (`bridge.py`). The calculator tools are
        offered only when it is usable (a host, and a molecule selected); without one the loop is exactly
        what it was before they existed.
        """
        messages = list(messages)
        tools = None
        if provider.supports_tools:
            tools = list(AVAILABLE_TOOLS)
            if bridge is not None and bridge.available:
                tools.extend(CALCULATION_TOOLS)
        response = AIResponse(text="")
        for _ in range(MAX_TOOL_ITERATIONS):
            request = AIRequest(system_context=system_context, messages=messages, model=model, api_key=api_key)
            response = provider.stream(request, on_chunk, tools)
            if not response.tool_calls:
                return response
            messages.append(AIMessage(role="assistant", content=response.text, tool_calls=response.tool_calls))
            for tool_call in response.tool_calls:
                messages.append(
                    AIMessage(role="tool", content=self._execute_tool(tool_call, bridge), tool_call_id=tool_call.id)
                )
        return response

    def _execute_tool(self, tool_call: ToolCall, bridge: ToolBridge | None = None) -> str:
        """Run one tool call, after checking it against the tool's own schema.

        The check is ours, not the provider's: a model can send a missing field, a wrong type or an
        argument the tool never declared, and the handler would then raise about its own signature or run
        on a wrong value. Problems are returned to the model and nothing runs.
        """
        calculation = tool_call.name in CALCULATION_HANDLERS
        handler = CALCULATION_HANDLERS.get(tool_call.name) or TOOL_REGISTRY.get(tool_call.name)
        if handler is None:
            return f"Unknown tool: {tool_call.name}"
        definition = next((d for d in [*AVAILABLE_TOOLS, *CALCULATION_TOOLS] if d.name == tool_call.name), None)
        if definition is not None:
            problems = validate_arguments(definition.input_schema, tool_call.input)
            if problems:
                return f"Tool {tool_call.name} was not run: " + "; ".join(problems)
        try:
            if calculation:
                if bridge is None:
                    return '{"ok": false, "problem": "unavailable", "message": "calculator access is not available in this conversation"}'
                return handler(bridge, **tool_call.input)
            return handler(**tool_call.input)
        except Exception as exc:  # noqa: BLE001 - a bad tool call must not crash the loop
            return f"Tool {tool_call.name} failed: {exc}"

    # --- what leaves this machine ----------------------------------------------------------------------

    def privacy_note(self) -> str:
        """Where the conversation, and so every calculator result the assistant reads, is sent."""
        provider_id = self._provider_combo.currentText()
        provider = self._providers.get(provider_id)
        if provider is None:
            return ""
        if not provider.supports_tools:
            return (
                f"{provider_id} cannot use this application's tools, so it can neither read nor run calculators. "
                f"Your messages and the selected molecule's summary are sent to it."
            )
        if getattr(provider, "_base_url", None):
            return (
                f"Calculator results the assistant reads are sent to the server at {provider._base_url}, as part of "
                f"the conversation."
            )
        return (
            f"Calculator results the assistant reads or runs are sent to {provider_id} as part of the conversation, "
            f"so they leave this machine."
        )

    def _refresh_privacy(self) -> None:
        self._privacy.setText(self.privacy_note())

    # --- the ledger and the previews ---------------------------------------------------------------------

    def _ledger_text(self, calculator: str, molecule: str, label: str, detail: str = "") -> str:
        text = f"{calculator} on {molecule}: {label}"
        return f"{text} ({detail[:140]})" if detail else text

    def _set_ledger(self, key: str, text: str) -> None:
        row = self._ledger_rows.get(key)
        if row is None:
            row = QListWidgetItem(text)
            self._ledger.addItem(row)
            self._ledger_rows[key] = row
        else:
            row.setText(text)
        row.setToolTip(text)
        self._ledger_label.setVisible(True)
        self._ledger.setVisible(True)
        self._ledger.scrollToBottom()

    def ledger_lines(self) -> list[str]:
        """What the ledger says, top to bottom."""
        return [self._ledger.item(i).text() for i in range(self._ledger.count())]

    def _on_bridge_event(self, event: BridgeEvent) -> None:
        """A tool did something the user should see. GUI thread: it arrived through a queued signal."""
        if event.kind == "refused":
            self._refusal_count += 1
            self._set_ledger(
                f"refused-{self._refusal_count}",
                self._ledger_text(event.calculator, event.molecule, _STATE_LABELS["rejected"], event.detail),
            )
            return
        if event.kind == "service_preview":
            self._add_service_card(event)
            return
        self._runs[event.run_id] = (event.calculator, event.molecule)
        if event.kind == "previewed":
            self._awaiting.add(event.run_id)
            self._add_card(event)
            self._set_ledger(
                event.run_id, self._ledger_text(event.calculator, event.molecule, _STATE_LABELS["previewed"])
            )
        elif event.kind == "finished":
            self._set_ledger(
                event.run_id,
                self._ledger_text(
                    event.calculator, event.molecule, _STATE_LABELS.get(event.state, event.state),
                    event.detail if event.state not in ("completed",) else "",
                ),
            )

    def _add_service_card(self, event: BridgeEvent) -> None:
        self._service_count += 1
        key = f"service-{self._service_count}"
        card = _ServiceCard(key, event.preparation, self._cards_host)
        card.open_clicked.connect(self._on_open_service_panel)
        card.dismiss_clicked.connect(self._on_dismiss_service)
        self._service_cards[key] = card
        self._cards_layout.addWidget(card)
        self._cards_host.setVisible(True)
        self._set_ledger(
            key, self._ledger_text(event.calculator, event.molecule, "cannot be started from here", event.detail)
        )

    def _on_open_service_panel(self, panel_id: str) -> None:
        if panel_id:
            self._context.panels.reveal(panel_id)

    def _on_dismiss_service(self, key: str) -> None:
        card = self._service_cards.pop(key, None)
        if card is not None:
            self._cards_layout.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards_host.setVisible(bool(self._cards or self._service_cards))

    def service_preview_keys(self) -> list[str]:
        """Service-run previews on screen."""
        return list(self._service_cards)

    def _add_card(self, event: BridgeEvent) -> None:
        card = _PreviewCard(event.preparation, self._cards_host)
        card.approve_clicked.connect(self._on_approve)
        card.cancel_clicked.connect(self._on_cancel)
        self._cards[event.run_id] = card
        self._cards_layout.addWidget(card)
        self._cards_host.setVisible(True)

    def _remove_card(self, run_id: str) -> None:
        card = self._cards.pop(run_id, None)
        if card is not None:
            self._cards_layout.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards_host.setVisible(bool(self._cards or self._service_cards))

    def pending_run_ids(self) -> list[str]:
        """Previews on screen waiting for a decision."""
        return list(self._cards)

    def _on_approve(self, run_id: str) -> None:
        """The user pressed Approve. The only path by which a preview ever starts."""
        self._remove_card(run_id)
        state = self._context.calculation_approvals.approve(run_id)
        calculator, molecule = self._runs.get(run_id, ("calculation", ""))
        if state is RunState.RUNNING:
            self._set_ledger(run_id, self._ledger_text(calculator, molecule, _STATE_LABELS["running"]))

    def _on_cancel(self, run_id: str) -> None:
        self._remove_card(run_id)
        self._context.calculation_approvals.cancel(run_id)

    def _on_run_finished(self, outcome: RunOutcome) -> None:
        """A run reached a final state (the host announces it once). GUI thread."""
        calculator, molecule = self._runs.get(outcome.run_id, (outcome.calculator_id, ""))
        state = outcome.state.value
        self._set_ledger(
            outcome.run_id,
            self._ledger_text(
                calculator, molecule, _STATE_LABELS.get(state, state), outcome.message if state != "completed" else ""
            ),
        )
        self._remove_card(outcome.run_id)
        if outcome.run_id not in self._awaiting:
            return  # an automatic run: the model already has its outcome from the tool call
        self._awaiting.discard(outcome.run_id)
        self._append_transcript("Application", f"{calculator} on {molecule}: {_STATE_LABELS.get(state, state)}.")
        self._notes.append(self._note_for(outcome, calculator, molecule))

    def _note_for(self, outcome: RunOutcome, calculator: str, molecule: str) -> str:
        """What the model is told, with the next message, about a preview it left for the user.

        The application's own record, not a paraphrase: the outcome carries the result's envelope with its
        method, units and freshness, and a refusal carries the calculator's reason.
        """
        head = (
            f"[Application note] The preview you prepared for {calculator} on {molecule} (run {outcome.run_id}) "
            f"ended '{outcome.state.value}'."
        )
        body = bounded_json(lambda caps: outcome_envelope(outcome, caps), budget=6000)
        return f"{head} The application's record of it:\n{body}"

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
