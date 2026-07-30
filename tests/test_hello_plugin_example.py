from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem

from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.plugins.manager import PluginManager

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "plugins"


class _FakeUIRegistry:
    def __init__(self) -> None:
        self.panels: dict[str, object] = {}
        self.menu_actions: dict[str, list[tuple[str, object]]] = {}

    def add_panel(self, panel_id, widget_factory):
        self.panels[panel_id] = widget_factory()

    def remove_panel(self, panel_id):
        self.panels.pop(panel_id, None)

    def add_menu_action(self, plugin_id, label, callback):
        self.menu_actions.setdefault(plugin_id, []).append((label, callback))

    def remove_menu_actions(self, plugin_id):
        self.menu_actions.pop(plugin_id, None)


def test_hello_plugin_loads_and_registers_everything(tmp_path: Path, qapp):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(EXAMPLES_DIR))
    settings.set("plugins/user_directory", str(tmp_path / "unused_user_plugins"))

    ui = _FakeUIRegistry()
    manager = PluginManager(services, ui, settings)
    manager.load_all()

    assert "hello_plugin" in manager.loaded_plugin_ids
    assert "Hello Plugin" in ui.panels
    assert any(label == "Say Hello" for label, _ in ui.menu_actions["hello_plugin"])

    provider = next(
        p for p in services.descriptor_service._providers if p.provider_id == "hello"
    )
    mol = Chem.MolFromSmiles("c1ccccc1CCO")
    values = provider.compute(mol, "mol-uuid")
    assert values[0].descriptor_id == "hello.ring_fraction"
    assert values[0].value == pytest.approx(6 / 9, abs=1e-3)
