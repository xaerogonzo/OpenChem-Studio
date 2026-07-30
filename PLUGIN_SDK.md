# OpenChem Studio Plugin SDK

## Trust model — read this first

Plugins are ordinary Python code, loaded and executed with the same
privileges as the rest of the application. There is **no sandboxing**.
Only install plugins you trust, the same way you'd only install a browser
extension or an editor plugin you trust. This may change later (declared
permissions, warnings) but nothing enforces it today.

## Where plugins live

OpenChem Studio scans two locations, non-recursively, at startup and on
every reload:

1. A **project-relative** directory — `<repo_root>/plugins/` by default,
   overridable via the `plugins/project_directory` setting. This is where
   this repo's own dev/example plugins live.
2. A **per-user** directory — via [`platformdirs`](https://pypi.org/project/platformdirs/)
   (e.g. `%LOCALAPPDATA%\OpenChemStudio\plugins` on Windows), overridable via
   `plugins/user_directory`. This is for plugins installed independently of
   any particular checkout.

If a `plugin_id` (see below) shows up in both locations, the project-relative
one wins and the other is ignored with a logged warning.

Use **Plugins > Open Project Plugins Folder** / **Open User Plugins Folder**
in the app to jump straight to either one (both are created if missing).

## Anatomy of a plugin

Every plugin is a **directory** containing exactly two required files:

```
my_plugin/
  manifest.toml
  plugin.py
  (anything else your plugin needs — icons, templates, etc.)
```

There is no single-file plugin format — this is the only shape, from day
one, so a plugin that starts simple can grow additional files without ever
needing to change format.

### `manifest.toml`

Read by the loader **without ever importing `plugin.py`** — so listing,
version-checking, and enabling/disabling plugins never runs arbitrary code.

```toml
plugin_id = "my_plugin"        # required, stable forever — never derived from the folder name
version = "0.1.0"              # required, your plugin's own version
api_version = 1                # required, must match this app's plugin API version
display_name = "My Plugin"     # required, shown in the Plugins menu
author = ""                    # optional
description = ""               # optional
homepage = ""                  # optional
license = ""                   # optional
dependencies = []              # optional, list of other plugin_ids that must load first
```

If `dependencies` names another plugin, the loader loads yours after it —
real topological ordering, not registration order. A missing dependency, a
dependency that itself failed to load, or a dependency cycle all result in
your plugin being skipped with a clear reason logged (visible in the
Console panel) and a `PluginLoadFailed` event, never a crash.

### `plugin.py`

Must define a zero-argument factory function:

```python
def create_plugin() -> Plugin:
    return MyPlugin()
```

`Plugin` has exactly two methods:

```python
from openchem.plugins.interfaces import Plugin
from openchem.plugins.context import PluginContext

class MyPlugin(Plugin):
    def activate(self, context: PluginContext) -> None:
        ...  # register everything your plugin provides, via context

    def deactivate(self) -> None:
        ...  # best-effort extra cleanup — see "Unload and hot reload" below
```

There's no `initialize`/`project_loaded`/`project_closed`/`shutdown` — if
you need to react to a project opening or closing, subscribe to the
existing `ProjectLoaded`/`ProjectClosed` events via `context.events`
(see below), the same mechanism as everything else.

### Splitting a plugin across multiple files

`plugin.py` can import sibling modules in its own directory with a relative
import, e.g. `from . import helpers` or `from .providers import MyThing`
(see `plugins/ai_assistant/` for a worked multi-file example: `plugin.py`,
`providers.py`, `context_builder.py`, `panel.py`). You don't need an
`__init__.py` and there's no package name to pick — the loader sets this up
for you automatically.

## `PluginContext` reference

Everything your plugin can do goes through `context`, grouped into small
namespaces. Nothing here is optional plumbing — every registration call is
tracked, so it can be reversed automatically (see "Unload and hot reload").

| Namespace | Call | What it's for |
|---|---|---|
| `context.descriptors` | `.register(provider: DescriptorProvider)` | Add computed molecule properties, shown in the Properties panel. |
| `context.conformers` | `.register(provider: ConformerProvider)` | Add a conformer-generation method (used via its `provider_id`). |
| `context.docking` | `.register(provider: DockingProvider)` | Add a docking algorithm (used via its `provider_id`) — `"vina"` is the only built-in one. |
| `context.quantum_chemistry` | `.register(provider: QuantumEngineProvider)` | Add a quantum-chemistry engine (used via its `provider_id`) — `"orca"` is the only built-in one. |
| `context.importers` | `.register(importer: Importer)` | Add a file-import format, checked before the built-in RDKit/Open Babel backends. |
| `context.exporters` | `.register(exporter: Exporter)` | Same, for export. |
| `context.panels` | `.register(provider: PanelProvider)` | Add a new dock panel. |
| `context.menus` | `.register(provider: MenuProvider)` | Add entries under the **Plugins** menu. |
| `context.events` | `.subscribe(event_type, handler)` / `.unsubscribe(...)` | React to app events (`MoleculeChanged`, `ProjectLoaded`, etc.) — **never** connect to the event bus or a Qt signal directly; only this is tracked for cleanup. |
| `context.settings` | `.get(key, default)` / `.set(key, value)` | Persistent settings, transparently namespaced under `plugins/<your_plugin_id>/` — you cannot read or write any other key. |
| `context.secrets` | `.get(key)` / `.set(key, value)` / `.delete(key)` | API keys and other credentials, stored in the OS keychain via `keyring` (Windows Credential Manager, macOS Keychain, Secret Service on Linux) — never in `Settings`/`QSettings`, never in plaintext config. Namespaced per-plugin under the hood (service name `openchem-plugin-<your_plugin_id>`); one plugin can never read another's stored values. `.get()` returns `None` if nothing is stored. Like `context.settings`, not tracked for rollback — a stored credential survives unload/reload, since the user shouldn't have to re-enter it every time a plugin hot-reloads. |
| `context.molecules` | `.add(molecule: MoleculeModel)` | Add a molecule to the current project as an undoable action and select it — e.g. a database search result or a predicted reaction product. A no-op (logged) if no project is currently open. Not tracked for rollback — an added molecule is real project data, same treatment as one added via File > New. |
| `context.resource_path(relative)` | — | Path to a file bundled alongside your plugin (icons, templates, etc.) — never guess your own directory. |
| `context.logger` | — | A `logging.Logger` named `openchem.plugin.<your_plugin_id>`, surfaced in the Console panel. |

### Running network/provider calls off the GUI thread

`openchem.plugins.async_task.run_async(func, expected_errors, on_finished,
on_failed)` runs `func()` on the global `QThreadPool` and delivers the
result back to the GUI thread via Qt signals — the same pattern
`ai_assistant`, `database_search`, and `reaction_prediction` all use for
their network/provider calls. `expected_errors` is the exception type (or
tuple of types) your provider raises for a "clean," documented failure
(e.g. `AIProviderError`) — caught and passed to `on_failed` as `str(exc)`;
anything else is still caught (never left to crash the pool) but prefixed
`"Unexpected error: "`. Safe to call without keeping the returned task —
`run_async` keeps its own reference for the task's actual lifetime, so a
fire-and-forget call from a button handler works correctly even though
nothing else holds onto it.

```python
run_async(
    lambda: provider.search(query, query_type),
    DatabaseSearchError,
    self._on_results,
    self._on_error,
)
```

### Descriptor IDs must be namespaced

Convention: `descriptor_ids()` should return `"<provider_id>.<local_name>"`
(e.g. `"my_plugin.custom_score"`), never a bare name like `"custom_score"`.
Two providers picking the same bare name would otherwise collide. The
Properties panel also defends against this at the display layer (it keys
rows on `(provider, descriptor_id)`), but the namespacing convention is
still what keeps your descriptor's identity stable and collision-free
everywhere else it's referenced.

### Menu entries

`MenuProvider.menu_entries()` returns `(label, action_id)` pairs. All of a
plugin's entries land as flat items directly under the **Plugins** menu
(there's no nested submenu parsing of the label in this version).
`handle_menu_action(action_id)` is called when the user triggers one.

## Unload and hot reload

- **Reload Plugins** in the Plugins menu, or simply editing a file under a
  watched plugin directory, unloads and reloads **every** plugin — not just
  the one that changed. Mapping a specific changed file back to exactly one
  plugin wasn't worth the complexity at typical plugin counts, and full
  reloads are cheap and safe.
- On unload, the loader reverses every `context.*.register(...)` and
  `context.events.subscribe(...)` call your `activate()` made, in reverse
  order, automatically. `deactivate()` is only for anything *outside* that —
  an open file handle, a background thread you started yourself, etc.
- **If `activate()` raises partway through**, the exact same rollback runs
  immediately — a plugin that fails halfway through never leaves partial
  registrations behind. Fix the error and reload; nothing needs manual
  cleanup on your end.
- **If your plugin starts background work** (a thread, a timer, a
  subprocess), tearing it down is your responsibility in `deactivate()` —
  the loader has no way to know about work it didn't start.
- Plugins can be individually disabled via **Plugins > Installed Plugins**
  without deleting their files; the setting persists across restarts.

## Worked example: `examples/plugins/hello_plugin/`

A complete, minimal plugin demonstrating all three UI-facing provider types
at once:

- `HelloDescriptorProvider` — one descriptor, `hello.ring_fraction` (ring
  atoms / heavy atoms), shown in the Properties panel.
- `HelloPanelProvider` — a static-text dock panel.
- `HelloMenuProvider` — one **Plugins** menu entry that shows a message box.

Read `examples/plugins/hello_plugin/plugin.py` alongside this guide, or
copy the whole folder into your plugins directory as a starting point.

## Known limitations

- No async/background loading state (`Loading…`/`Loaded`/`Failed`) — every
  plugin's `activate()` is expected to return quickly. Revisit if a real
  plugin needs to do slow work (loading an ML model, initializing an
  external process) at load time.
- No `ToolbarProvider` or `ContextMenuProvider` — there's no toolbar or
  context menus anywhere in the app yet for a plugin to extend.
- No numeric provider priority — for imports/exports, a plugin-registered
  backend is simply checked before the built-ins, in registration order.
- No declared permissions (filesystem/network/etc.) — not sandboxing
  either way, so there's nothing yet for a declaration to gate.
