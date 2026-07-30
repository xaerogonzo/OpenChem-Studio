from __future__ import annotations

from openchem.plugins.context import PluginContext
from openchem.plugins.interfaces import MenuProvider, PanelProvider, Plugin

from . import providers as providers_module
from .panel import DatabaseSearchPanel


class DatabaseSearchPanelProvider(PanelProvider):
    panel_id = "Database Search"

    def __init__(self, context: PluginContext, provider_map: dict) -> None:
        self._context = context
        self._provider_map = provider_map
        self.panel: DatabaseSearchPanel | None = None

    def create_panel(self) -> DatabaseSearchPanel:
        self.panel = DatabaseSearchPanel(self._context, self._provider_map)
        return self.panel


class DatabaseSearchMenuProvider(MenuProvider):
    def __init__(self, context: PluginContext, panel_provider: DatabaseSearchPanelProvider) -> None:
        self._context = context
        self._panel_provider = panel_provider

    def menu_entries(self) -> list[tuple[str, str]]:
        return [("Search Chemical Databases", "database_search.focus")]

    def handle_menu_action(self, action_id: str) -> None:
        panel = self._panel_provider.panel
        if panel is None:
            return
        self._context.panels.reveal(DatabaseSearchPanelProvider.panel_id)
        panel.setFocus()


class DatabaseSearchPlugin(Plugin):
    def activate(self, context: PluginContext) -> None:
        provider_map = providers_module.build_default_providers()

        panel_provider = DatabaseSearchPanelProvider(context, provider_map)
        context.panels.register(panel_provider)

        menu_provider = DatabaseSearchMenuProvider(context, panel_provider)
        context.menus.register(menu_provider)

    def deactivate(self) -> None:
        pass


def create_plugin() -> Plugin:
    return DatabaseSearchPlugin()
