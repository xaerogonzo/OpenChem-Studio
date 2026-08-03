from __future__ import annotations

import logging
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import platformdirs
from PySide6.QtCore import QFileSystemWatcher, QTimer

from openchem.app.settings import Settings
from openchem.events.events import PluginLoadFailed, PluginLoaded, PluginUnloaded
from openchem.plugins.context import PluginContext
from openchem.plugins.interfaces import PLUGIN_API_VERSION, Plugin
from openchem.plugins.manifest import ManifestError, PluginManifest, topological_order
from openchem.plugins.ui_registry import UIRegistry
from openchem.services.container import ServiceContainer
from openchem import paths as app_paths

logger = logging.getLogger("openchem.plugin")

def _default_project_plugins_dir() -> Path:
    """Where the plugins that ship with the application live.

    From source that is the repository's top-level `plugins/`, four levels up
    from this file (`src/openchem/plugins/manager.py`).

    Frozen, `__file__` points inside PyInstaller's `_internal/` payload
    directory, and four levels up from there happens to land beside the
    executable -- the right answer by coincidence of depth, which is not
    something to leave a build depending on silently. Say it outright
    instead: plugins are user-editable *source* that deliberately ships
    NEXT TO the exe rather than buried in the payload, precisely so that
    someone can drop a new one in without a Python install. That is
    `sys.executable`'s directory, whatever the payload depth happens to be.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "plugins"
    return Path(__file__).resolve().parents[3] / "plugins"


DEFAULT_PROJECT_PLUGINS_DIR = _default_project_plugins_dir()
DEBOUNCE_MS = 300

# A multi-file plugin's sibling-module imports (`from . import helper`)
# go through Python's normal import machinery (unlike plugin.py itself,
# which this module compiles/execs directly — see _import_plugin_module),
# and normal imports write __pycache__/*.pyc as a side effect. Since the
# recursive hot-reload watcher below watches a plugin's whole directory
# tree, that .pyc write is itself a filesystem change — creating __pycache__
# the first time a multi-file plugin loads would immediately trigger a
# spurious self-triggered reload a few hundred ms after every load. Bytecode
# caching for plugins is undesirable anyway (the same staleness class of bug
# documented on _import_plugin_module), so it's disabled outright.
sys.dont_write_bytecode = True


class PluginLoadError(Exception):
    """Raised internally when a plugin can't be imported or instantiated."""


@dataclass
class _LoadedPlugin:
    manifest: PluginManifest
    plugin: Plugin
    context: PluginContext
    module_name: str


def _import_plugin_module(plugin_dir: Path, module_name: str) -> ModuleType:
    """Imports plugin.py fresh under a unique synthetic module name.

    Deliberately reads the source and `compile()`/`exec()`s it directly,
    rather than going through `importlib.util.spec_from_file_location` +
    `exec_module` — that path uses the standard `SourceFileLoader`, which
    caches compiled bytecode in `__pycache__` keyed by the source file's
    mtime. Two quick edits during development (or in a hot-reload test) can
    land within the same mtime tick, and the loader then happily serves
    stale bytecode under a brand-new module name. Compiling from the text
    we just read has no such cache to go stale.
    """
    plugin_file = plugin_dir / "plugin.py"
    if not plugin_file.exists():
        raise PluginLoadError(f"{plugin_dir} has no plugin.py")
    source = plugin_file.read_text(encoding="utf-8")
    module = ModuleType(module_name)
    module.__file__ = str(plugin_file)
    # Makes `plugin.py` behave like a package's __init__ for sibling-module
    # imports (`from . import helpers`) — Python's standard path-based
    # finder resolves `<module_name>.helpers` by searching __path__, so a
    # multi-file plugin can organize itself into more than one module.
    module.__path__ = [str(plugin_dir)]
    module.__package__ = module_name
    sys.modules[module_name] = module
    try:
        code = compile(source, str(plugin_file), "exec")
        exec(code, module.__dict__)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


class PluginManager:
    """Discovers, loads, hot-reloads, and unloads plugins.

    Depends only on `ServiceContainer` and the `UIRegistry` protocol — never
    on a concrete window class (see `plugins/ui_registry.py`) — so a
    headless mode or a different frontend later needs its own `UIRegistry`
    implementation, not a `PluginManager` change.
    """

    def __init__(self, services: ServiceContainer, ui_registry: UIRegistry, settings: Settings) -> None:
        self._services = services
        self._ui_registry = ui_registry
        self._settings = settings
        self._loaded: dict[str, _LoadedPlugin] = {}

        self._project_plugins_dir = Path(
            settings.get("plugins/project_directory", str(DEFAULT_PROJECT_PLUGINS_DIR))
        )
        default_user_dir = app_paths.subdirectory("plugins")
        self._user_plugins_dir = Path(settings.get("plugins/user_directory", str(default_user_dir)))

        self._watcher = QFileSystemWatcher()
        self._watcher.directoryChanged.connect(self._on_fs_changed)
        self._watcher.fileChanged.connect(self._on_fs_changed)
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self.reload_all)

    @property
    def plugin_directories(self) -> list[Path]:
        return [self._project_plugins_dir, self._user_plugins_dir]

    @property
    def loaded_plugin_ids(self) -> list[str]:
        return list(self._loaded)

    def display_name(self, plugin_id: str) -> str:
        return self._loaded[plugin_id].manifest.display_name

    def discover_manifests(self) -> list[PluginManifest]:
        """All manifests found on disk, including disabled/not-yet-loaded ones."""
        return self._discover_manifests()

    def disabled_ids(self) -> set[str]:
        return self._disabled_ids()

    # --- discovery ------------------------------------------------------------

    def _discover_manifests(self) -> list[PluginManifest]:
        manifests: list[PluginManifest] = []
        seen_ids: set[str] = set()
        for root in (self._project_plugins_dir, self._user_plugins_dir):
            if not root.is_dir():
                continue
            for entry in sorted(root.iterdir()):
                if not entry.is_dir():
                    continue
                try:
                    manifest = PluginManifest.load(entry)
                except ManifestError as exc:
                    logger.warning("Skipping %s: %s", entry, exc)
                    continue
                if manifest.plugin_id in seen_ids:
                    existing = next(m.plugin_dir for m in manifests if m.plugin_id == manifest.plugin_id)
                    logger.warning(
                        "Plugin id %r found in more than one location; keeping %s, ignoring %s",
                        manifest.plugin_id,
                        existing,
                        entry,
                    )
                    continue
                seen_ids.add(manifest.plugin_id)
                manifests.append(manifest)
        return manifests

    def _disabled_ids(self) -> set[str]:
        return set(self._settings.get("plugins/disabled", []) or [])

    # --- load/unload ------------------------------------------------------------

    def load_all(self) -> None:
        disabled = self._disabled_ids()
        candidates = [m for m in self._discover_manifests() if m.plugin_id not in disabled]

        # Filter out API-incompatible manifests *before* the topological
        # sort, not after, so anything depending on one gets the same
        # "missing dependency" cascade as a truly absent plugin.
        compatible = []
        for manifest in candidates:
            if manifest.api_version != PLUGIN_API_VERSION:
                error = (
                    f"api_version {manifest.api_version} does not match this "
                    f"app's {PLUGIN_API_VERSION}"
                )
                logger.error("Not loading plugin %r: %s", manifest.plugin_id, error)
                self._services.event_bus.publish(
                    PluginLoadFailed(plugin_id=manifest.plugin_id, error=error)
                )
                continue
            compatible.append(manifest)

        ordered, skipped = topological_order(compatible)
        for plugin_id, reason in skipped.items():
            logger.error("Not loading plugin %r: %s", plugin_id, reason)
            self._services.event_bus.publish(PluginLoadFailed(plugin_id=plugin_id, error=reason))

        for manifest in ordered:
            self._load_one(manifest)
        self._resync_watcher()

    def _load_one(self, manifest: PluginManifest) -> None:
        if manifest.plugin_id in self._loaded:
            return
        if manifest.api_version != PLUGIN_API_VERSION:
            # load_all() already filters this out before the topological
            # sort so a mismatched dependency cascades correctly; re-checked
            # here too since set_enabled() can call _load_one() directly,
            # bypassing that upstream filter.
            error = (
                f"api_version {manifest.api_version} does not match this "
                f"app's {PLUGIN_API_VERSION}"
            )
            logger.error("Not loading plugin %r: %s", manifest.plugin_id, error)
            self._services.event_bus.publish(
                PluginLoadFailed(plugin_id=manifest.plugin_id, error=error)
            )
            return

        module_name = f"openchem_plugin_{manifest.plugin_id}_{uuid.uuid4().hex[:8]}"
        context = PluginContext(
            manifest.plugin_id, manifest.plugin_dir, self._services, self._ui_registry, self._settings
        )
        try:
            module = _import_plugin_module(manifest.plugin_dir, module_name)
            create_plugin = getattr(module, "create_plugin", None)
            if not callable(create_plugin):
                raise PluginLoadError(f"{manifest.plugin_dir}/plugin.py has no create_plugin()")
            plugin = create_plugin()
            if not isinstance(plugin, Plugin):
                raise PluginLoadError("create_plugin() did not return a Plugin instance")
            plugin.activate(context)
        except Exception as exc:  # noqa: BLE001 - one bad plugin must not block the rest
            logger.exception("Failed to load plugin %r", manifest.plugin_id)
            context.unwind()
            sys.modules.pop(module_name, None)
            self._services.event_bus.publish(
                PluginLoadFailed(plugin_id=manifest.plugin_id, error=str(exc))
            )
            return

        self._loaded[manifest.plugin_id] = _LoadedPlugin(manifest, plugin, context, module_name)
        logger.info("Loaded plugin %r from %s", manifest.plugin_id, manifest.plugin_dir)
        self._services.event_bus.publish(PluginLoaded(plugin_id=manifest.plugin_id))

    def unload(self, plugin_id: str) -> None:
        loaded = self._loaded.pop(plugin_id, None)
        if loaded is None:
            return
        loaded.context.unwind()
        try:
            loaded.plugin.deactivate()
        except Exception:
            logger.exception("Plugin %r raised in deactivate()", plugin_id)
        sys.modules.pop(loaded.module_name, None)
        logger.info("Unloaded plugin %r", plugin_id)
        self._services.event_bus.publish(PluginUnloaded(plugin_id=plugin_id))

    def reload_all(self) -> None:
        """Unloads and reloads every plugin, not just whichever file
        changed — mapping a specific changed path back to exactly one
        plugin isn't worth the complexity at this plugin count, and the
        transactional load/unload machinery makes a full reload cheap and
        safe."""
        for plugin_id in list(self._loaded):
            self.unload(plugin_id)
        self.load_all()

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        disabled = self._disabled_ids()
        if enabled:
            disabled.discard(plugin_id)
        else:
            disabled.add(plugin_id)
        self._settings.set("plugins/disabled", sorted(disabled))

        if not enabled:
            self.unload(plugin_id)
            return

        manifest = next((m for m in self._discover_manifests() if m.plugin_id == plugin_id), None)
        if manifest is None:
            logger.warning("Cannot enable %r: no manifest found on disk", plugin_id)
            return
        self._load_one(manifest)
        self._resync_watcher()

    # --- hot reload --------------------------------------------------------------

    def _resync_watcher(self) -> None:
        watched = self._watcher.files() + self._watcher.directories()
        if watched:
            self._watcher.removePaths(watched)
        for root in (self._project_plugins_dir, self._user_plugins_dir):
            if root.is_dir():
                self._watch_recursive(root)

    def _watch_recursive(self, root: Path) -> None:
        """QFileSystemWatcher doesn't recurse on its own, so every
        subdirectory of a plugin (icons/, templates/, etc.) is registered
        individually."""
        paths = [str(root)]
        for sub in root.rglob("*"):
            if sub.is_dir():
                paths.append(str(sub))
        if paths:
            self._watcher.addPaths(paths)

    def _on_fs_changed(self, _path: str) -> None:
        self._debounce_timer.start(DEBOUNCE_MS)
