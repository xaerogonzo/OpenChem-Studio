from __future__ import annotations

import time
from pathlib import Path

from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.plugins.manager import PluginManager
from test_plugin_manager import VALID_PLUGIN_SRC, FakeUIRegistry, _make_plugin


def test_filesystem_change_triggers_debounced_reload(tmp_path: Path, qapp):
    services = build_service_container()
    settings = Settings(services.event_bus)
    project_dir = tmp_path / "project_plugins"
    settings.set("plugins/project_directory", str(project_dir))
    settings.set("plugins/user_directory", str(tmp_path / "user_plugins"))

    manager = PluginManager(services, FakeUIRegistry(), settings)
    _make_plugin(project_dir / "good", "good", VALID_PLUGIN_SRC)
    manager.load_all()
    assert manager.loaded_plugin_ids == ["good"]

    reload_calls: list[bool] = []
    manager._debounce_timer.timeout.disconnect()
    manager._debounce_timer.timeout.connect(lambda: (reload_calls.append(True), manager.reload_all()))

    # Drives the real watcher -> debounce -> reload wiring, not just a
    # direct reload_all() call.
    manager._on_fs_changed(str(project_dir))

    deadline = time.time() + 2.0
    while not reload_calls and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)

    assert reload_calls, "debounced reload never fired"
    assert manager.loaded_plugin_ids == ["good"]
