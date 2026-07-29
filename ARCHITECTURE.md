# Architecture

## Layering

Strict one-directional dependency flow. UI code never imports `rdkit` or
`openbabel` directly — enforced by a test (`tests/test_layering.py`) that
scans `app/` and `ui/` for those imports.

```
UI (widgets/panels)
   |  dispatches
   v
Commands (QUndoCommand — undo/redo, and the future scripting/automation surface)
   |  call
   v
Services (async, progress-aware, publish typed Events)
   |  operate on
   v
Domain models (pure dataclasses, no RDKit/Qt — referenced everywhere by UUID)
   |  realized by
   v
Chem engine (the ONLY layer that imports rdkit / openbabel)
```

Events flow orthogonally to this stack: services publish typed `Event`
objects (`src/openchem/events/events.py`) on a typed `EventBus`
(`src/openchem/events/base.py`); UI panels — and eventually plugins —
subscribe by event type rather than by ad-hoc signal name.

## Package map

| Package | Responsibility |
|---|---|
| `openchem.domain` | Pure data: `MoleculeModel`, `ProjectModel`, `DescriptorValue`, `ConformerModel`, plus the shared `CacheState` enum (`domain/common.py`). No RDKit, no Qt. Molecules are identified by UUID, never filename or list position. |
| `openchem.chem` | `ChemistryEngine` (MoleculeModel <-> RDKit Mol, canonicalization, and 3D measurement via `rdMolTransforms`), `DescriptorProvider`/`ConformerProvider` implementations, `Importer`/`Exporter` backends. The only place `rdkit`/`openbabel` are imported. |
| `openchem.services` | `DescriptorService`, `ConformerService`, `MeasurementService`, `ImportService`, `ExportService`, `ProjectService`, plus `ProgressHandle` for cancellable/progress-reporting long operations. The async ones own `QThreadPool` execution and publish events. |
| `openchem.commands` | `QUndoCommand` subclasses wrapping service calls, giving undo/redo for structure edits, conformer generation, and project operations from day one. |
| `openchem.plugins` | `interfaces.py` (`Plugin`, `DescriptorProvider`, `ConformerProvider`, `PanelProvider`, `MenuProvider`, `Importer`, `Exporter`), `manifest.py` (`PluginManifest` + dependency topological sort), `context.py` (`PluginContext`, including the `context.secrets` namespace backed by the OS keychain via `keyring`), `ui_registry.py` (`UIRegistry` protocol), `manager.py` (`PluginManager` — discovery, transactional load/unload/reload, hot-reload watcher). See `PLUGIN_SDK.md`. |
| `openchem.app` | Composition: `MainWindow`, typed `Settings`, `SessionManager`, structured logging setup. `MainWindow` implements the `UIRegistry` protocol and constructs `PluginManager` at the end of `__init__`. |
| `openchem.ui` | Widgets and dock panels. `EditorBackend`/`KetcherEditorBackend` (2D, `resources/ketcher/dist/`) and `ViewerBackend`/`Mol3DViewerBackend` (3D, `resources/viewer3d/`, 3Dmol.js) are both interface + single-implementation pairs — either can be swapped or extended with a sibling implementation (e.g. a future Mol*-based viewer for macromolecules/crystallography) without touching chemistry, services, or commands. |
| `plugins/ai_assistant` | Bundled first-party plugin (loads by default, unlike `examples/`). `providers.py` (`AIProvider` ABC, `AnthropicProvider`, `OpenAICompatibleProvider` covering OpenAI + local Ollama), `context_builder.py` (`MoleculeContextCache` — accumulates molecule identity/descriptors purely from subscribed events, same pattern as `PropertyPanel`), `panel.py` (chat UI, async `QRunnable` network calls), `plugin.py` (registers the panel + two menu-driven canned prompts). Kept out of core `openchem` so the `anthropic`/`openai` SDKs stay optional (`pyproject.toml`'s `ai` extra). |

`tools/ketcher-host/` is a small separate Node/Vite project (not part of the
Python package) that builds the static Ketcher bundle vendored into
`src/openchem/resources/ketcher/dist/`. Rebuild it with
`npm install && npm run build` in that directory after bumping the
`ketcher-react`/`ketcher-standalone` versions in its `package.json`. See the
comments in `tools/ketcher-host/vite.config.js` for why the config looks the
way it does — bundling Ketcher under Vite requires specific
`commonjsOptions`/`define` workarounds (raw `require`/`global` references
inside `ketcher-core`'s bundled Raphael.js — see
[epam/ketcher#5565](https://github.com/epam/ketcher/issues/5565)) and
minification must stay off (it reintroduces a temporal-dead-zone bug from
`ketcher-core`'s circular imports once variable names are mangled).

`src/openchem/resources/viewer3d/` (the 3D viewer) has no equivalent build
step — `3Dmol-min.js` is vendored directly as a single dependency-free
browser file (from the `3dmol` npm package's `build/` output, BSD-3-Clause),
paired with a small hand-written static `viewer.html`. No Node/npm involved
at all for this one.

## Design decisions worth remembering

- **Descriptors are not cached on the molecule.** `DescriptorValue` records
  (id, name, units, category, provider, value, timestamp, cache_state) live
  in the descriptor service/providers, so a future plugin-provided descriptor
  is indistinguishable in shape from a built-in RDKit one.
- **Descriptor computation is async even though it's currently fast.**
  `DescriptorService` tracks each value through `Queued -> Running ->
  Completed|Failed` on a `QThreadPool`, so slow future providers (docking,
  ORCA, AI) don't need a different code path.
- **Projects never serialize an RDKit `Mol` object.** `MoleculeModel` stores
  a molblock plus canonical SMILES/InChI/InChIKey and metadata; RDKit
  reconstructs the `Mol` on demand via `ChemistryEngine`.
- **Open Babel is a fallback, not a foundation.** `chem/io_backends.py` tries
  the RDKit importer/exporter first for every format and only instantiates
  (and imports) `openbabel` when RDKit lacks support for that format.
- **`ProjectModel` carries `project_version` / `application_version` /
  `schema_version`** from the start so a future format change is a migration
  in `ProjectService`, not a breaking change. `MoleculeModel.conformers` was
  added as a plain additive field (default `[]`) with no schema bump needed —
  old project files without a `"conformers"` key still load.
- **Conformer generation follows the same "service never mutates the model"
  rule as descriptors.** `ConformerService` publishes results as data
  (`ConformersReady`), and only `SetConformersCommand` (pushed by
  `MainWindow`, mirroring how `EditStructureCommand` is pushed from Ketcher's
  async result) actually writes to `MoleculeModel.conformers` — keeping that
  mutation on the GUI thread and undoable.
- **`PluginManager` depends on the `UIRegistry` protocol, never on
  `MainWindow` directly.** `plugins/ui_registry.py` is a `typing.Protocol`;
  `MainWindow` satisfies it structurally (matching method names/signatures)
  without inheriting from it at runtime — avoids the QObject/ABCMeta
  metaclass conflict documented in `ui/editor_backend.py`, and means a
  headless mode or a second window later needs its own `UIRegistry`, not a
  `PluginManager` change.
- **Plugin metadata lives in `manifest.toml`, never on the `Plugin` object.**
  The loader reads `plugin_id`/`api_version`/`dependencies` without ever
  importing `plugin.py` — listing, dependency-ordering, and enabling/
  disabling plugins never executes arbitrary plugin code.
- **Every `PluginContext` registration is tracked for rollback.** The same
  tracked-unregister list that makes `PluginManager.unload()` correct also
  makes plugin activation transactional: if `Plugin.activate()` raises
  partway through, the loader replays that list immediately so a
  half-failed plugin never leaves partial registrations behind.
- **Multi-file plugins are supported via synthetic namespace packages.**
  `PluginManager._import_plugin_module` sets `module.__path__ = [plugin_dir]`
  and `module.__package__ = module_name` on the `ModuleType` it `exec()`s
  `plugin.py` into, so `from . import sibling` in a plugin resolves against
  its own directory through Python's normal path-based finder. `plugin.py`
  itself is still read and `exec()`d directly (see the docstring on that
  function for why — bytecode-cache staleness during hot reload), but
  sibling-module imports go through ordinary import machinery, which writes
  `__pycache__/*.pyc` — since the hot-reload watcher recurses into a
  plugin's whole directory tree, that write would otherwise look like a
  filesystem change and trigger a spurious self-reload a few hundred ms
  after every load. `sys.dont_write_bytecode = True` at the top of
  `manager.py` disables that caching outright (undesirable for plugins
  anyway, for the same staleness reason).
- **Plugin credentials live in `context.secrets`, never in `Settings`.**
  `_PluginSecrets` (in `context.py`) wraps `keyring.get_password`/
  `set_password`/`delete_password`, namespaced per-plugin via service name
  `f"openchem-plugin-{plugin_id}"` so one plugin can never read another's
  stored key. Not tracked in the rollback list — like `context.settings`, a
  stored credential is meant to survive reload/unload.
- **`MoleculeSnapshotUpdated` gives plugins molecule identity without
  exposing `SessionManager`/`ProjectModel`.** `MoleculeSelected`/
  `MoleculeChanged` only carry a `molecule_uuid`; this additive event
  (`events/events.py`) carries display name, canonical SMILES/InChI/InChIKey,
  and conformer summary data, published by `MainWindow` from the same
  handlers that already resolve the real `MoleculeModel`. Any plugin needing
  molecule identity (not just `ai_assistant`) subscribes to this instead of
  requesting deeper access.
- **`UIRegistry.add_menu_action`'s `callback` contract is genuinely
  zero-argument, enforced at the `MainWindow` boundary.** `QAction.triggered`
  emits `triggered(checked: bool)`; connecting it directly to a callback
  would silently pass that bool as the callback's first positional argument
  — including clobbering a lambda default like
  `lambda aid=action_id: ...` (Python allows overriding a default via a
  positional argument, so the emitted bool overwrites `aid` instead of being
  rejected). `MainWindow.add_menu_action` connects through
  `lambda checked=False: callback()` so every `UIRegistry` caller genuinely
  only ever needs to handle the zero-argument case the protocol promises.

## Known TODOs

- `build.ps1` / `build.bat` are generic Nuitka packaging templates left over
  from project scaffolding (tkinter/pystray profile). They need a PySide6
  Nuitka profile (swap `--enable-plugin=tk-inter` for the PySide6 plugin,
  drop `pystray`, add RDKit/Open Babel data-file includes) before they can
  package this application. Not needed until an actual release build.
- `SimilarityService` doesn't exist yet; belongs to a later roadmap phase
  and would currently have no callers.
- Editing a molecule's 2D structure does not currently invalidate/clear its
  previously generated conformers, which then describe a stale structure
  until the user regenerates them manually. Deliberately out of scope for
  Phase 3 (no `ConformersInvalidated` event yet) — worth revisiting.
- Plugin loading has no async/background state, no `ToolbarProvider`/
  `ContextMenuProvider`, no numeric provider priority, and no declared
  permissions — all deliberately deferred; see the "Explicitly deferred"
  reasoning preserved in `PLUGIN_SDK.md`'s "Known limitations" section.
- `ai_assistant` has no tool-calling loop (the assistant can't request safe
  read operations like SMARTS validation itself) and no response streaming —
  both deliberately deferred out of Phase 5; see ROADMAP.md.
