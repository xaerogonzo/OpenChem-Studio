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

    def __init__(self, panel_provider: AIAssistantPanelProvider, cache: MoleculeContextCache) -> None:
        self._panel_provider = panel_provider
        self._cache = cache

    def menu_entries(self) -> list[tuple[str, str]]:
        return [
            ("Explain Selected Molecule", "ai_assistant.explain"),
            ("Generate Molecule Report", "ai_assistant.report"),
        ]

    def handle_menu_action(self, action_id: str) -> None:
        panel = self._panel_provider.panel
        if panel is None:
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

        provider_map = providers_module.build_default_providers()

        panel_provider = AIAssistantPanelProvider(context, provider_map, cache)
        context.panels.register(panel_provider)

        menu_provider = AIAssistantMenuProvider(panel_provider, cache)
        context.menus.register(menu_provider)

    def deactivate(self) -> None:
        pass


def create_plugin() -> Plugin:
    return AIAssistantPlugin()
