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
| `openchem.domain` | Pure data: `MoleculeModel`, `ProjectModel`, `DescriptorValue`, `ConformerModel`, `MacromoleculeModel`, `DockingBox`/`DockingPoseModel`/`DockingResultModel`, plus the shared `CacheState` enum and `Provenance` dataclass (`domain/common.py`). No RDKit, no Qt. Molecules (and macromolecules, and docking results) are identified by UUID, never filename or list position. |
| `openchem.chem` | `ChemistryEngine` (MoleculeModel <-> RDKit Mol, canonicalization, 3D measurement via `rdMolTransforms`, and `formal_charge()` — the one place the UI layer can get a chemistry-derived default without importing rdkit itself), `DescriptorProvider`/`ConformerProvider`/`DockingProvider` implementations, `Importer`/`Exporter` backends, `vina_engine.py` (`VinaEngine` abstraction — see below), `orca_engine.py` (ORCA input building + output parsing). The only place `rdkit`/`openbabel` are imported. |
| `openchem.services` | `DescriptorService`, `ConformerService`, `MeasurementService`, `ImportService`, `ExportService`, `ProjectService`, `DockingService`, `QuantumChemistryService`, plus `ProgressHandle` for cancellable/progress-reporting long operations. All but `QuantumChemistryService` own `QThreadPool` execution and publish events — `QuantumChemistryService` is the one exception (see design decisions below). |
| `openchem.commands` | `QUndoCommand` subclasses wrapping service calls, giving undo/redo for structure edits, conformer generation, docking results, quantum-chemistry conformers, and project operations from day one. |
| `openchem.plugins` | `interfaces.py` (`Plugin`, `DescriptorProvider`, `ConformerProvider`, `DockingProvider`, `QuantumEngineProvider`, `PanelProvider`, `MenuProvider`, `Importer`, `Exporter`), `manifest.py` (`PluginManifest` + dependency topological sort), `context.py` (`PluginContext`, including the `context.secrets` namespace backed by the OS keychain via `keyring`, and `context.molecules`/`context.docking`/`context.quantum_chemistry`), `ui_registry.py` (`UIRegistry` protocol), `manager.py` (`PluginManager` — discovery, transactional load/unload/reload, hot-reload watcher). See `PLUGIN_SDK.md`. |
| `openchem.app` | Composition: `MainWindow`, typed `Settings`, `SessionManager`, structured logging setup. `MainWindow` implements the `UIRegistry` protocol and constructs `PluginManager` at the end of `__init__`. |
| `openchem.ui` | Widgets and dock panels. `EditorBackend`/`KetcherEditorBackend` (2D, `resources/ketcher/dist/`), `ViewerBackend`/`Mol3DViewerBackend` (3D small molecules, `resources/viewer3d/`, 3Dmol.js), and `ViewerBackend`/`MolStarViewerBackend` (macromolecules/crystallography, `resources/molstar/`, Mol*) are interface + implementation pairs — new content types get a sibling implementation, or a new optional capability method on the shared `ViewerBackend` base, without touching chemistry, services, or commands. `panels/docking_panel.py` and `panels/quantum_chemistry_panel.py` are core (not plugin) panels, same tier as `PropertyPanel`. |
| `plugins/ai_assistant` | Bundled first-party plugin (loads by default, unlike `examples/`). `providers.py` (`AIProvider` ABC, `AnthropicProvider`, `OpenAICompatibleProvider` covering OpenAI + local Ollama, `ClaudeCLIProvider` driving a locally-logged-in `claude` CLI headless for claude.ai subscription users with no separate API key), `context_builder.py` (`MoleculeContextCache` — accumulates molecule identity/descriptors purely from subscribed events, same pattern as `PropertyPanel`), `panel.py` (chat UI), `plugin.py` (registers the panel + two menu-driven canned prompts). Kept out of core `openchem` so the `anthropic`/`openai` SDKs stay optional (`pyproject.toml`'s `ai` extra) — `ClaudeCLIProvider` needs neither, just `claude` on PATH. |
| `plugins/database_search` | Bundled plugin: `DatabaseSearchProvider` ABC (`PubChemProvider`, `ChEMBLProvider`), search results import as a new molecule via `context.molecules.add(...)`. `requests` stays optional (`network` extra). |
| `plugins/reaction_prediction` | Bundled plugin: `ReactionPredictor` ABC (`RDKitTemplateProvider` — deterministic, zero-config; `RemoteReactionAPIProvider` — optional, configured via `context.settings`/`context.secrets`). |

All three bundled plugins share the same `QRunnable`+`Signal` off-GUI-thread pattern for network/provider calls, extracted into `openchem.plugins.async_task.run_async` after the third one made the duplication obvious — see `PLUGIN_SDK.md`.

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

`src/openchem/resources/molstar/` (the macromolecule viewer) follows the
same no-build-step pattern as `viewer3d/`, not Ketcher's: `molstar.js`/
`.css` are the `molstar` npm package's own prebuilt `build/viewer/` output
(MIT-licensed, `LICENSE` included), paired with a custom `viewer.html`
adapted from Mol*'s own `build/viewer/embedded.html` example (its default
`index.html` is a full demo UI, not what's wanted here).

## Vendored library maintenance

Confirm this against the actual installed package version before
finalizing, rather than assuming an API from memory or documentation —
`chem/vina_engine.py`'s `PythonVinaEngine` and `resources/molstar/viewer.html`
were both written after reading (respectively) the real cached `vina`
package source and a real Mol* spike, specifically because guessing from
memory would have been wrong in small but real ways (e.g. Mol*'s click
`BehaviorSubject` emits an initial value synchronously to a new subscriber,
which reads as a false "click" unless the handler defensively checks for
it).

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
- **`context.molecules.add(molecule)`** lets a plugin add a molecule to the
  project through the same undoable path `MainWindow._new_molecule()` uses
  — added when `database_search` needed to turn a search result into a real
  project molecule and discovered `PluginContext` had no such path at all.
- **A fire-and-forget async call must keep its own strong reference to
  the in-flight task.** `openchem.plugins.async_task.run_async` (used by
  all three bundled plugins) keeps a module-level `set` of in-flight
  `PluginAsyncTask`s until each one's `finished`/`failed` signal fires —
  confirmed directly that without this, `QThreadPool.start()`'s C++-side
  ownership does not reliably protect a `QRunnable`'s Python wrapper (and
  its child `QObject` signals) from CPython's own refcounting when no
  caller holds the returned task, which every fire-and-forget button
  handler here does.
- **`Provenance`** (`domain/common.py`) — a shared `created_by`/`method`/
  `parameters`/`timestamp` shape — was used on new Phase 6 models
  (`DockingResultModel`) first, then retrofitted onto `ConformerModel`/
  `DescriptorValue` in Phase 9.5 as an additive optional field (`None` for
  anything round-tripped from before it existed) — their own pre-existing
  `.method`/`.timestamp`/`.provider` fields were left as they are, not
  replaced. `MacromoleculeModel` stayed out of scope: it's imported user
  data, not a provider-computed result.
- **`MacromoleculeModel` is deliberately not RDKit-Mol-backed.** Full
  proteins don't fit V2000 molblock assumptions well and aren't edited or
  conformer-generated the way small molecules are — it stores raw
  `structure_text`/`source_format` (matching Mol*'s own `"pdb"`/`"mmcif"`
  vocabulary directly, no translation layer) instead.
- **`DockingProvider` (which algorithm) is a different axis from
  `VinaEngine` (how Vina itself runs).** The `vina` PyPI package has no
  prebuilt Windows wheel (confirmed directly — building it needs Boost +
  MSVC); rather than block on that, `chem/vina_engine.py` adds
  `PythonVinaEngine` and `ExecutableVinaEngine` behind one interface,
  auto-selected by `select_vina_engine()` (Python binding preferred, then a
  configured/found executable, else a clear "no backend" error) — this also
  sets up cleanly for smina/gnina/QuickVina later, a real anticipated need,
  not speculative generality. The executable path (`docking/vina_executable_path`,
  set via the docking panel's "Configure Vina..." dialog) is resolved fresh
  on every `dock()` call, not cached at construction time — same reasoning
  as `QuantumChemistryService`'s executable-path resolution, so a path
  configured mid-session takes effect without restarting the app.
  `VinaDockingProvider` itself never imports `Settings` directly (`chem/`
  stays decoupled from `app/`) — it takes a plain `Callable[[], str]`
  resolver, and `DockingService` (which is allowed to depend on `Settings`)
  supplies a closure over the real settings object.
- **`QuantumEngineProvider` has three pure methods
  (`build_input`/`command_args`/`parse_output`), not one blocking `run()`.**
  `QuantumChemistryService` owns the actual `QProcess` lifecycle entirely;
  the provider never touches a subprocess, keeping input-building and
  output-parsing trivially unit-testable without any process involved.
- **`QuantumChemistryService` runs `QProcess` on the GUI thread — the one
  deliberate exception to "async services use `QRunnable`/`QThreadPool`."**
  `QProcess` is only safely usable from the thread that constructs it, and
  ORCA jobs need real, immediate cancellation (`kill()` from a live Cancel
  button, not "the next time a worker thread checks in") plus live-streamed
  stdout — both fit `QProcess`/GUI-thread naturally, unlike a blocking
  worker-thread subprocess call. Confirmed directly that killing a running
  `QProcess` also fires `errorOccurred` (not just `finished`) — both
  handlers pop the same job from the same dict, so both must check the
  `cancelled` flag or a real cancellation gets misreported as a generic
  crash.
- **ORCA scratch directories are never derived from the project path.**
  This project's own working directory contains a space
  (`...\OpenChem Studio\`), which ORCA's documentation warns against —
  every job's scratch directory is created under
  `platformdirs.user_cache_dir(...)` instead, with cleanup guaranteed via
  `try`/`finally` covering success, cancellation, crash, and parse-failure
  alike.
- **`AddConformerCommand` exists because `SetConformersCommand` replaces
  the whole list.** ORCA (6.5) needs to add one optimized-geometry
  conformer without wiping out whatever RDKit-generated conformers already
  exist — `SetConformersCommand`'s wholesale-replace semantics would do
  exactly that if reused as-is.
- **Quantum-chemistry descriptor results reuse the existing
  `DescriptorComputed` event, not a new display mechanism.** Descriptors
  were never cached on the molecule to begin with (see above) — ORCA's
  values are just another provider's `DescriptorValue`s, and `PropertyPanel`
  already displays whatever it's given.

## Known TODOs

- `build.ps1` / `build.bat` are generic Nuitka packaging templates left over
  from project scaffolding (tkinter/pystray profile). They need a PySide6
  Nuitka profile (swap `--enable-plugin=tk-inter` for the PySide6 plugin,
  drop `pystray`, add RDKit/Open Babel data-file includes) before they can
  package this application. Not needed until an actual release build —
  explicitly out of scope for Phase 9's hardening pass too.
- `SimilarityService` doesn't exist yet; belongs to a later roadmap phase
  and would currently have no callers.
- Plugin loading has no async/background state, no `ToolbarProvider`/
  `ContextMenuProvider`, no numeric provider priority, and no declared
  permissions, and no `RemoteServicePlugin` base class exists for the
  network/async/settings/secrets boilerplate common to
  `ai_assistant`/`database_search`/`reaction_prediction` (only `run_async`
  was extracted) — all deliberately deferred, reconfirmed still true as of
  Phase 9: there is still no concrete fourth plugin whose actual
  requirements would tell us what these abstractions should look like, so
  building them now would mean guessing. See the "Explicitly deferred"
  reasoning preserved in `PLUGIN_SDK.md`'s "Known limitations" section.
- `MacromoleculeModel` only stores raw PDB/mmCIF text — no structured
  chain/residue/assembly parsing, no BinaryCIF/MMTF support yet (the
  `structure_text`/`source_format` field split makes room for it later
  without another schema change). Raw mmCIF text import into the Mol*
  viewer already works; BinaryCIF/MMTF (binary formats) have no importer
  or fetch path driving them yet.
- `RDKitTemplateProvider`'s bundled-plus-user-dir templates are an
  extensibility point with nothing built on them yet: a formal
  `context.reactions.register(...)`-style plugin-provided-templates
  namespace is a real gap, not silently dropped.
- Docking receptor prep (`VinaDockingProvider`, see Phase 9.3 in
  ROADMAP.md) still has no missing-residue repair — needs a dedicated
  structure-repair library, a genuinely different dependency/problem than
  the pH/water/cofactor/altloc handling that IS built.
- `DockingPoseModel.metadata`'s H-bond/clash analysis (Phase 9.4) is a
  heavy-atom-distance heuristic only — pharmacophore/hydrophobic contact
  detection is a real gap, less standardized and meaningfully more work
  than what's built.
- **Vina and ORCA execution are now verified against real installed
  backends** (issue #2): a real `vina_1.2.7_win.exe` and a real ORCA 6.1.1
  install were pointed at end-to-end through `DockingPanel`/
  `QuantumChemistryPanel` — real docking poses, and real single-point/
  geometry-optimization/opt+freq ORCA results including thermochemistry.
  `PythonVinaEngine`'s exact method sequence is still unverified (no `vina`
  Python wheel on Windows; `ExecutableVinaEngine` is what actually ran and
  is confirmed correct). Three real bugs surfaced only by this live testing,
  all fixed:
  - `ChemistryEngine.mol_from_molblock` used RDKit's default `removeHs=True`,
    which silently discards a conformer's explicit hydrogen *positions* on
    every round-trip (folded into implicit H-count on the heavy atom) — for
    water this sent ORCA a bare oxygen atom instead of H2O, computing a
    plausible-looking but chemically wrong energy with no error at all. Now
    `removeHs=False`.
  - `QuantumChemistryPanel._on_run_clicked` accepted a molecule with no 3D
    conformer, falling back to its 2D-editor molblock — which, combined with
    the bug above, is how the wrong-energy case above was reached in the
    first place. Now refuses ("Generate a 3D conformer first") without one,
    mirroring `DockingPanel`'s equivalent guard.
  - `QuantumChemistryService._on_finished` could read `job.stdout_chunks`
    before Qt delivered the QProcess's last `readyReadStandardOutput` signal
    for output written right as the process exited — intermittently missing
    a long job's final result block even though the identical input
    completed correctly when run directly. Now drains any remaining
    buffered bytes before parsing.
  - Not a code bug, but worth recording: ORCA fails at startup
    ("aborting the run") if its own *install* directory contains a space —
    it spawns sibling helper binaries (`orca_startup`, etc.) with an
    unquoted path internally. Distinct from the scratch/working directory
    space requirement already noted above, which was already handled
    correctly.
