from __future__ import annotations

from pathlib import Path

from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.events.events import PluginLoadFailed, PluginLoaded, PluginUnloaded
from openchem.plugins.manager import PluginManager


class FakeUIRegistry:
    """A plain object satisfying the UIRegistry protocol structurally --
    no Qt window, no MainWindow, involved at all."""

    def __init__(self) -> None:
        self.panels: dict[str, object] = {}
        self.menu_actions: dict[str, list[tuple[str, object]]] = {}
        self.added_molecules: list[object] = []
        self.revealed_panels: list[str] = []

    def add_panel(self, panel_id, widget_factory):
        self.panels[panel_id] = widget_factory()

    def remove_panel(self, panel_id):
        self.panels.pop(panel_id, None)

    def reveal_panel(self, panel_id):
        self.revealed_panels.append(panel_id)

    def add_menu_action(self, plugin_id, label, callback):
        self.menu_actions.setdefault(plugin_id, []).append((label, callback))

    def remove_menu_actions(self, plugin_id):
        self.menu_actions.pop(plugin_id, None)

    def add_molecule(self, molecule):
        self.added_molecules.append(molecule)


VALID_PLUGIN_SRC = """
from openchem.plugins.interfaces import Plugin

class SimplePlugin(Plugin):
    def activate(self, context):
        pass
    def deactivate(self):
        pass

def create_plugin():
    return SimplePlugin()
"""

DESCRIPTOR_PLUGIN_TEMPLATE = """
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.plugins.interfaces import DescriptorProvider, Plugin

class TestDescriptorProvider(DescriptorProvider):
    provider_id = "testplug"
    def descriptor_ids(self):
        return ["testplug.value"]
    def compute(self, mol, molecule_uuid):
        return [DescriptorValue(
            descriptor_id="testplug.value",
            name="Test Value",
            units="",
            category="test",
            provider=self.provider_id,
            molecule_uuid=molecule_uuid,
            value={value},
            cache_state=CacheState.COMPLETED,
        )]

class TestPlugin(Plugin):
    def activate(self, context):
        context.descriptors.register(TestDescriptorProvider())
    def deactivate(self):
        pass

def create_plugin():
    return TestPlugin()
"""

FAILING_ACTIVATE_PLUGIN_SRC = """
from openchem.plugins.interfaces import DescriptorProvider, Plugin

class HalfProvider(DescriptorProvider):
    provider_id = "halfplug"
    def descriptor_ids(self):
        return ["halfplug.x"]
    def compute(self, mol, molecule_uuid):
        return []

class FailingPlugin(Plugin):
    def activate(self, context):
        context.descriptors.register(HalfProvider())
        raise RuntimeError("boom")
    def deactivate(self):
        pass

def create_plugin():
    return FailingPlugin()
"""

BROKEN_PLUGIN_SRC = "this is not ( valid python"


def _make_plugin(dir_path: Path, plugin_id: str, plugin_py: str, dependencies=None) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    deps = "[" + ", ".join(repr(d) for d in (dependencies or [])) + "]"
    (dir_path / "manifest.toml").write_text(
        f'plugin_id = "{plugin_id}"\nversion = "1.0.0"\napi_version = 1\n'
        f'display_name = "{plugin_id}"\ndependencies = {deps}\n'
    )
    (dir_path / "plugin.py").write_text(plugin_py)


def _make_manager(tmp_path: Path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    project_dir = tmp_path / "project_plugins"
    user_dir = tmp_path / "user_plugins"
    settings.set("plugins/project_directory", str(project_dir))
    settings.set("plugins/user_directory", str(user_dir))
    ui = FakeUIRegistry()
    manager = PluginManager(services, ui, settings)
    return manager, services, ui, project_dir


def test_load_all_loads_valid_and_skips_broken(tmp_path: Path, qapp):
    manager, services, ui, project_dir = _make_manager(tmp_path)
    _make_plugin(project_dir / "good", "good", VALID_PLUGIN_SRC)
    _make_plugin(project_dir / "bad", "bad", BROKEN_PLUGIN_SRC)

    loaded_events = []
    failed_events = []
    services.event_bus.subscribe(PluginLoaded, lambda e: loaded_events.append(e.plugin_id))
    services.event_bus.subscribe(PluginLoadFailed, lambda e: failed_events.append(e.plugin_id))

    manager.load_all()

    assert manager.loaded_plugin_ids == ["good"]
    assert loaded_events == ["good"]
    assert failed_events == ["bad"]


def test_failed_activation_rolls_back_partial_registrations(tmp_path: Path, qapp):
    manager, services, ui, project_dir = _make_manager(tmp_path)
    _make_plugin(project_dir / "failing", "failing", FAILING_ACTIVATE_PLUGIN_SRC)

    failed_events = []
    services.event_bus.subscribe(PluginLoadFailed, lambda e: failed_events.append(e.plugin_id))

    manager.load_all()

    assert manager.loaded_plugin_ids == []
    assert failed_events == ["failing"]
    provider_ids = [p.provider_id for p in services.descriptor_service._providers]
    assert "halfplug" not in provider_ids


def test_unload_reverses_registrations(tmp_path: Path, qapp):
    manager, services, ui, project_dir = _make_manager(tmp_path)
    _make_plugin(project_dir / "descplug", "descplug", DESCRIPTOR_PLUGIN_TEMPLATE.format(value=1))
    manager.load_all()

    assert "descplug" in manager.loaded_plugin_ids
    assert "testplug" in [p.provider_id for p in services.descriptor_service._providers]

    unloaded_events = []
    services.event_bus.subscribe(PluginUnloaded, lambda e: unloaded_events.append(e.plugin_id))
    manager.unload("descplug")

    assert manager.loaded_plugin_ids == []
    assert unloaded_events == ["descplug"]
    assert "testplug" not in [p.provider_id for p in services.descriptor_service._providers]


def test_reload_picks_up_new_behavior_with_no_duplicate_registration(tmp_path: Path, qapp):
    manager, services, ui, project_dir = _make_manager(tmp_path)
    plugin_dir = project_dir / "descplug"
    _make_plugin(plugin_dir, "descplug", DESCRIPTOR_PLUGIN_TEMPLATE.format(value=1))
    manager.load_all()

    _make_plugin(plugin_dir, "descplug", DESCRIPTOR_PLUGIN_TEMPLATE.format(value=2))
    manager.reload_all()

    providers = [p for p in services.descriptor_service._providers if p.provider_id == "testplug"]
    assert len(providers) == 1

    mol = services.chemistry_engine.mol_from_smiles("C")
    values = providers[0].compute(mol, "mol-uuid")
    assert values[0].value == 2


def test_disabled_plugin_is_not_loaded(tmp_path: Path, qapp):
    manager, services, ui, project_dir = _make_manager(tmp_path)
    _make_plugin(project_dir / "good", "good", VALID_PLUGIN_SRC)

    manager.set_enabled("good", False)
    manager.load_all()
    assert manager.loaded_plugin_ids == []

    manager.set_enabled("good", True)
    assert manager.loaded_plugin_ids == ["good"]
