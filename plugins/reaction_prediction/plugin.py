from __future__ import annotations

from openchem.events.events import MoleculeSelected, MoleculeSnapshotUpdated
from openchem.plugins.context import PluginContext
from openchem.plugins.interfaces import MenuProvider, PanelProvider, Plugin

from . import providers as providers_module
from .molecule_cache import SelectedMoleculeCache
from .panel import ReactionPredictionPanel


class ReactionPredictionPanelProvider(PanelProvider):
    panel_id = "Reaction Prediction"

    def __init__(self, context: PluginContext, provider_map: dict, cache: SelectedMoleculeCache) -> None:
        self._context = context
        self._provider_map = provider_map
        self._cache = cache
        self.panel: ReactionPredictionPanel | None = None

    def create_panel(self) -> ReactionPredictionPanel:
        self.panel = ReactionPredictionPanel(self._context, self._provider_map, self._cache)
        return self.panel


class ReactionPredictionMenuProvider(MenuProvider):
    def __init__(self, context: PluginContext, panel_provider: ReactionPredictionPanelProvider) -> None:
        self._context = context
        self._panel_provider = panel_provider

    def menu_entries(self) -> list[tuple[str, str]]:
        return [("Predict Reaction Products", "reaction_prediction.focus")]

    def handle_menu_action(self, action_id: str) -> None:
        panel = self._panel_provider.panel
        if panel is None:
            return
        self._context.panels.reveal(ReactionPredictionPanelProvider.panel_id)
        panel.focus_and_prefill_from_selection()


class ReactionPredictionPlugin(Plugin):
    def activate(self, context: PluginContext) -> None:
        cache = SelectedMoleculeCache()
        context.events.subscribe(MoleculeSelected, cache.on_molecule_selected)
        context.events.subscribe(MoleculeSnapshotUpdated, cache.on_snapshot_updated)

        bundled_templates_path = context.resource_path("reaction_templates.json")
        # Handed the live registry, so a template registered by ANOTHER
        # plugin is applied even if that plugin activates after this one.
        provider_map = providers_module.build_default_providers(
            bundled_templates_path, context.reactions
        )

        panel_provider = ReactionPredictionPanelProvider(context, provider_map, cache)
        context.panels.register(panel_provider)

        menu_provider = ReactionPredictionMenuProvider(context, panel_provider)
        context.menus.register(menu_provider)

    def deactivate(self) -> None:
        pass


def create_plugin() -> Plugin:
    return ReactionPredictionPlugin()
