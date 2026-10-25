from __future__ import annotations

from openchem.plugins.context import PluginContext
from openchem.plugins.interfaces import MenuProvider, PanelProvider, Plugin

from .panel import SynthesisPanel


class SynthesisPanelProvider(PanelProvider):
    panel_id = "Synthesis"

    def __init__(self, context: PluginContext) -> None:
        self._context = context
        self.panel: SynthesisPanel | None = None

    def create_panel(self) -> SynthesisPanel:
        self.panel = SynthesisPanel(self._context)
        return self.panel


class SynthesisMenuProvider(MenuProvider):
    def __init__(self, context: PluginContext, panel_provider: SynthesisPanelProvider) -> None:
        self._context = context
        self._panel_provider = panel_provider

    def menu_entries(self) -> list[tuple[str, str]]:
        return [("Plan Synthesis", "synthesis_planner.focus")]

    def handle_menu_action(self, action_id: str) -> None:
        panel = self._panel_provider.panel
        if panel is None:
            return
        # Reveal first: a menu action that only focused a widget is invisible while another dock tab is in front.
        self._context.panels.reveal(SynthesisPanelProvider.panel_id)
        panel.refresh()


class SynthesisPlugin(Plugin):
    def activate(self, context: PluginContext) -> None:
        panel_provider = SynthesisPanelProvider(context)
        context.panels.register(panel_provider)
        context.menus.register(SynthesisMenuProvider(context, panel_provider))

    def deactivate(self) -> None:
        pass


def create_plugin() -> Plugin:
    return SynthesisPlugin()
