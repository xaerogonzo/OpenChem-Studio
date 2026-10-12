from __future__ import annotations

from openchem.events.events import DescriptorComputed, MoleculeSelected, MoleculeSnapshotUpdated
from openchem.plugins.context import PluginContext
from openchem.plugins.interfaces import MenuProvider, PanelProvider, Plugin

from . import providers as providers_module
from .context_builder import MoleculeContextCache
from .panel import AIAssistantPanel
from .providers import AIProvider


class AIAssistantPanelProvider(PanelProvider):
    panel_id = "AI Assistant"

    def __init__(
        self, context: PluginContext, provider_map: dict[str, AIProvider], cache: MoleculeContextCache
    ) -> None:
        self._context = context
        self._provider_map = provider_map
        self._cache = cache
        self.panel: AIAssistantPanel | None = None

    def create_panel(self) -> AIAssistantPanel:
        self.panel = AIAssistantPanel(self._context, self._provider_map, self._cache)
        return self.panel


class AIAssistantMenuProvider(MenuProvider):
    """Both entries pre-fill a prompt and focus the chat panel — the user
    still has to click Send. Nothing here fires a network request on its
    own; "documentation generation" from the roadmap is just a canned
    prompt over the same chat pipeline, not a separate subsystem.
    """

    def __init__(
        self, context: PluginContext, panel_provider: AIAssistantPanelProvider, cache: MoleculeContextCache
    ) -> None:
        self._context = context
        self._panel_provider = panel_provider
        self._cache = cache

    def menu_entries(self) -> list[tuple[str, str]]:
        # "Open AI Assistant" leads: the other two entries are named for what
        # they do, not for the assistant, and the rail files the panel under
        # "Compare and Extend" -- so without it nothing on screen said the
        # application HAS an assistant (measured in a driven run, 2026-10-12).
        return [
            ("Open AI Assistant", "ai_assistant.open"),
            ("Explain Selected Molecule", "ai_assistant.explain"),
            ("Explain Stored Results", "ai_assistant.explain_results"),
            ("Generate Molecule Report", "ai_assistant.report"),
        ]

    def handle_menu_action(self, action_id: str) -> None:
        # Reveal first, before looking at our own panel reference. The host
        # builds the panel when it is registered, so the reference is set by
        # the time any entry can fire; this ordering just keeps "show the
        # panel" independent of that detail.
        self._context.panels.reveal(AIAssistantPanelProvider.panel_id)
        panel = self._panel_provider.panel
        if panel is None:
            return
        if action_id == "ai_assistant.open":
            panel.focus_input()
            return
        if not self._cache.has_molecule():
            panel.prefill_and_focus("No molecule is currently selected.")
            return
        name = self._cache.display_name()
        if action_id == "ai_assistant.explain":
            panel.prefill_and_focus(
                f"Explain the key properties of {name} shown above (molecular weight, "
                "LogP, TPSA, stereochemistry, etc.) in plain language."
            )
        elif action_id == "ai_assistant.explain_results":
            # Asks for the tool rather than quoting numbers here: what is stored is read by the model
            # through read_results, with each result's method, units, structure and freshness, so the
            # explanation is of the application's own record and not of whatever the prompt happened to say.
            panel.prefill_and_focus(
                f"Use read_results to read every result stored for {name}, then explain in plain language what each "
                "one means: its method, its units, which structure it was computed on, and any caveat it carries. "
                "Say which results are not current or were refused, and why; do not describe a calculator that has "
                "no stored result."
            )
        elif action_id == "ai_assistant.report":
            panel.prefill_and_focus(
                f"Write a short markdown report summarizing {name}'s structure and "
                "computed properties, suitable for a lab notebook."
            )


class AIAssistantPlugin(Plugin):
    def activate(self, context: PluginContext) -> None:
        cache = MoleculeContextCache()
        context.events.subscribe(MoleculeSelected, cache.on_molecule_selected)
        context.events.subscribe(MoleculeSnapshotUpdated, cache.on_snapshot_updated)
        context.events.subscribe(DescriptorComputed, cache.on_descriptor_computed)

        provider_map = providers_module.build_default_providers(
            cli_path_resolver=lambda: context.settings.get("claude_cli_cli_path", "")
        )

        panel_provider = AIAssistantPanelProvider(context, provider_map, cache)
        context.panels.register(panel_provider)

        menu_provider = AIAssistantMenuProvider(context, panel_provider, cache)
        context.menus.register(menu_provider)

    def deactivate(self) -> None:
        pass


def create_plugin() -> Plugin:
    return AIAssistantPlugin()
