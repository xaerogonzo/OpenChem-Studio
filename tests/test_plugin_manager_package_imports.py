from __future__ import annotations

from pathlib import Path

from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.plugins.manager import PluginManager
from test_plugin_manager import FakeUIRegistry

HELPER_SRC = """
def greet():
    return "hello from sibling module"
"""

MULTI_FILE_PLUGIN_SRC = """
from openchem.plugins.interfaces import Plugin
from . import helper

class MultiFilePlugin(Plugin):
    def activate(self, context):
        context.logger.info(helper.greet())
    def deactivate(self):
        pass

def create_plugin():
    return MultiFilePlugin()
"""


def test_plugin_with_sibling_module_loads_via_plugin_manager(tmp_path: Path, qapp):
    services = build_service_container()
    settings = Settings(services.event_bus)
    project_dir = tmp_path / "project_plugins"
    settings.set("plugins/project_directory", str(project_dir))
    settings.set("plugins/user_directory", str(tmp_path / "user_plugins"))

    plugin_dir = project_dir / "multi_file"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "manifest.toml").write_text(
        'plugin_id = "multi_file"\nversion = "1.0.0"\napi_version = 1\n'
        'display_name = "multi_file"\ndependencies = []\n'
    )
    (plugin_dir / "plugin.py").write_text(MULTI_FILE_PLUGIN_SRC)
    (plugin_dir / "helper.py").write_text(HELPER_SRC)

    manager = PluginManager(services, FakeUIRegistry(), settings)
    manager.load_all()

    assert manager.loaded_plugin_ids == ["multi_file"]
