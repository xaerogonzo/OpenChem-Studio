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
| `openchem.domain` | Pure data: `MoleculeModel`, `ProjectModel`, `DescriptorValue`, `ConformerModel`, the report types (`Fact`/`AtomReport`/`BondReport`/`MoleculeReport`), `MacromoleculeModel`, `DockingBox`/`DockingPoseModel`/`DockingResultModel`, plus the shared `CacheState` enum and `Provenance` dataclass (`domain/common.py`). No RDKit, no Qt. Molecules (and macromolecules, and docking results) are identified by UUID, never filename or list position. |
| `openchem.chem` | The only place `rdkit`/`openbabel` are imported, and by some margin the largest package (59 modules, plus the `regulatory/` subpackage). Grouped by what they are for, since the flat listing is no longer navigable: **core** — `engine.py` (`ChemistryEngine`: MoleculeModel <-> RDKit Mol, canonicalization, 2D depiction including the property heat map, 3D measurement, and `formal_charge()`, the one place UI gets a chemistry-derived default without importing rdkit), `identifiers.py`, `io_backends.py`. **Structure files** — `structure_io.py`, `binarycif.py`, `structure_summary.py`, `structure_assembly.py`; see the pipeline section below. **Docking** — `docking_providers.py`, `vina_engine.py`, `pose_analysis.py`, `binding_site.py`, `receptor_library.py`, `interaction_analysis.py`. **Quantum/spectroscopy** — `orca_engine.py`, the `nmr_*` family (database lookup, HOSE codes, scaling, TMS referencing, the lookup+ORCA hybrid, correlation, signals), `huckel.py`, `electronic_properties.py`, `dipole.py`, `boltzmann.py`, `vibrational_modes.py` (normal-mode character by internal-coordinate decomposition), `mode_animation.py`, `orca_surfaces.py` + `cube.py` (driving `orca_plot` and reading Gaussian cubes into the existing `ScalarField`), and `jcamp.py` + `spectrum_overlay.py` (reading a measured spectrum and reconciling it with a computed one). **Calculators** — `descriptor_providers.py` plus the per-topic modules it registers (`topology_analysis`, `geometry_analysis`, `surface_analysis`, `elemental_analysis`, `steric`, `substructure`, `structure_generators`, `markush`, `logd`, `ph_curves`, `mpo_scores`, `bbb_stereo`, `scalar_field`, `alignment`, `molecular_dynamics`, `calculator_options`). **Sidecars** — `pka_providers.py`/`pka_runner.py` and `admet_providers.py`/`admet_runner.py`, each a pair where the `_runner` is executed BY the sidecar's own interpreter and imports nothing from `openchem`. **Naming** — `naming_providers.py` (structure <-> name across PubChem, the vendored engine, and OPSIN, each result labelled with its source and whether it is `exact`, `derived` or `parsed`) and `structure_annotation.py`, which takes the SECOND return value the naming engine always had: ring systems, functional groups, stereocentres and atom numbering, as plain atom-indexed data no vendor type escapes from. **Batch** — `result_reduction.py` (every result shape collapsed to table cells), `analytics.py`, `clustering.py`. **Regulatory** — the `regulatory/` subpackage: `types.py` (the legal-source / machine-interpretation split), `predicates.py` (the rule language), `engine.py`, `loader.py`, `calculator.py`. It is a subpackage rather than flat modules because it is the only part of `chem` with its own data format, build step and on-disk rulesets. |
| `openchem.services` | `DescriptorService`, `ConformerService`, `MeasurementService`, `ImportService`, `ExportService`, `ProjectService`, `DockingService`, `QuantumChemistryService`, plus `ProgressHandle` for cancellable/progress-reporting long operations. All but `QuantumChemistryService` own `QThreadPool` execution and publish events — `QuantumChemistryService` is the one exception (see design decisions below). **Set-of-molecules services:** `BatchService` (runs chosen descriptors/calculators across a whole project as ONE pooled task, so "molecule 47 of 200" is reportable and one cancel flag stops it), `ScreeningService` (queues N ligands through `DockingService` one at a time rather than starting N Vina processes; it advances by *listening* for each job's terminal event, so no thread blocks), and `TableExportService` (`BatchTable` -> CSV/Markdown; deliberately not folded into `ExportService`, which is constructed with a `ChemistryEngine` and dispatches by chemical format — there is no chemical format whose subject is a table). |
| `openchem.commands` | `QUndoCommand` subclasses wrapping service calls, giving undo/redo for structure edits, conformer generation, docking results, quantum-chemistry conformers, and project operations from day one. |
| `openchem.plugins` | `interfaces.py` (`Plugin`, `DescriptorProvider`, `ConformerProvider`, `DockingProvider`, `QuantumEngineProvider`, `FactProvider`, `PanelProvider`, `MenuProvider`, `Importer`, `Exporter`), `manifest.py` (`PluginManifest` + dependency topological sort), `context.py` (`PluginContext`, including the `context.secrets` namespace backed by the OS keychain via `keyring`, and `context.molecules`/`context.docking`/`context.quantum_chemistry`), `ui_registry.py` (`UIRegistry` protocol), `manager.py` (`PluginManager` — discovery, transactional load/unload/reload, hot-reload watcher). See `PLUGIN_SDK.md`. |
| `openchem.app` | Composition: `MainWindow`, typed `Settings`, `SessionManager`, structured logging setup. `MainWindow` implements the `UIRegistry` protocol and constructs `PluginManager` at the end of `__init__`. |
| `openchem.ui` | Widgets and dock panels. `EditorBackend`/`KetcherEditorBackend` (2D, `resources/ketcher/dist/`), `ViewerBackend`/`Mol3DViewerBackend` (3D small molecules, `resources/viewer3d/`, 3Dmol.js), and `ViewerBackend`/`MolStarViewerBackend` (macromolecules/crystallography, `resources/molstar/`, Mol*) are interface + implementation pairs — new content types get a sibling implementation, or a new optional capability method on the shared `ViewerBackend` base, without touching chemistry, services, or commands. `panels/docking_panel.py` and `panels/quantum_chemistry_panel.py` are core (not plugin) panels, same tier as `PropertyPanel`. |
| `openchem.vendor` | Third-party code owned in-tree rather than depended on. Currently one entry: `iupac_namer`, a deterministic IUPAC nomenclature engine (structure -> name). Reached only through `chem/naming_providers.py`; nothing else imports it. See below and `vendor/VENDORING.md`. |
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

### `src/openchem/vendor/` — the IUPAC nomenclature engine

The one vendored **Python** library, and unlike the browser assets above it
is not a build artifact of somebody else's release: it is a 63,000-line
structure-to-name engine (`iupac_namer`, MIT) implementing the 2013 IUPAC
Blue Book, plus ~36,000 lines of nomenclature tables in `vendor/data/`.

It is vendored rather than depended on because **upstream is abandoned** —
created and last pushed the same day, three commits, one author, never
published to PyPI. With no upstream to track, depending on it and owning it
are the same act. `vendor/VENDORING.md` records the pinned commit, the
licence, and the single mechanical change made (302 imports re-homed).

Two traps for anyone editing it:

- `vendor/data/` is a **sibling** of `vendor/iupac_namer/`, not inside it,
  because data files are resolved from several different module depths.
  Moving it into the package requires patching every resolver and breaks on
  the second one.
- Its ~3,200 own tests live in `tests/vendor/` and are **excluded from the
  default run** (`norecursedirs`) — they take ~10 minutes. Run them after any
  change under `vendor/`, with Java on PATH. See `CLAUDE.md`.

`benchmarks/naming/` is the arbiter for naming quality: 181 molecules scored
by OPSIN round-trip rather than string equality. It has twice overturned a
conclusion reached without it, and it is what justified adopting this engine
over a 1.1 GB ML alternative that scored 26 points lower.

## The structure-file pipeline, and the invariant that runs through it

A macromolecule takes a longer path than any other data in this app, and
the same class of bug has been found on it five times. Recorded as a
pipeline because the individual steps each look correct alone — the bugs
all lived in the seams.

```
file on disk / RCSB
   |  structure_io.read_structure_file   — sniffs CONTENT, gunzips
   |  binarycif.to_mmcif                 — BinaryCIF decoded HERE, at the boundary
   v
MacromoleculeModel.structure_text  (always TEXT: "pdb" or "mmcif")
   |
   +-- structure_summary.summarize_structure   chains, sequences, ligands, waters
   +-- structure_assembly.parse_assembly       what the depositor says is biological
   +-- binding_site.box_from_ligand            a search box from a bound ligand
   |
   v  receptor_prep_options  { ph, strip_waters, strip_cofactors, keep_chains }
   |
   +-- docking_providers._convert_receptor_to_pdbqt  -> what VINA sees
   +-- pose_analysis.receptor_atoms_from_structure   -> what the ANALYSIS sees
```

**THE INVARIANT: those last two must describe the same receptor.** They
are separate code paths over separate libraries, and every time they have
drifted the result was not a crash but a confident wrong answer:

- Waters/cofactors stripped for docking but not for analysis — 195
  reported clashes against atoms deleted before Vina ran.
- Altlocs filtered for PDB only — an mmCIF receptor docked with doubled
  atoms.
- Residues keyed without a chain — a homotetramer's subunits merged, 34
  rings instead of 121.
- Open Babel's unit-cell expansion — 6WGT reached Vina as 73,707 atoms
  for an 8,100-atom deposit, eight overlapping copies.
- A search box left pointing where no receptor remained.

The structural answer is that **every filter is one shared predicate,
consulted by both paths**, and that the options controlling them travel
in one dict the service hands to both: `is_stripped_residue`,
`filter_altlocs`, `is_symmetry_generated`, `is_excluded_chain`. A new
filter belongs there too, not in one path. `_require_receptor_in_box`
then reads the PREPARED pdbqt rather than the source, so the last check
before Vina is against the exact atoms Vina gets.

BinaryCIF is decoded at the boundary rather than carried inward for the
same reason: Open Babel reads neither `bcif` nor `mmtf` (measured), so a
binary-carrying model would have been viewable and un-dockable.

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

- **A report is an assembly, never a calculation.** `AtomReport`,
  `BondReport` and `MoleculeReport` (in `domain/report.py`, built by
  `chem/atom_report.py`, `chem/bond_report.py`, `chem/molecule_report.py`)
  answer "tell me everything already known about this subject" by gathering
  results other things computed. **Nothing in a collector starts work** --
  opening the inspector, clicking an atom and switching molecules are all
  free, and a property that has not been run is ABSENT rather than zero. An
  inspector that launched ORCA on a click would be a calculator launcher,
  and people stop trusting those.
- **The report vocabulary says nothing about atoms, and that was the point.**
  `Fact`, `FactCategory` and `FactLink` describe a FINDING. `AtomReport` was
  written that way on the bet that bonds and molecules would want the same
  shape; when they arrived the types moved to `domain/report.py` UNCHANGED
  and only the identity fields differed. Facts group by CATEGORY (Electronic,
  Topology) rather than by producing module, because grouping by producer
  puts four consecutive "Lewis" headings on screen -- an implementation
  detail leaking into the UI.
- **A collector that raises is skipped, not fatal.** One analysis that
  dislikes an exotic structure, or one plugin `FactProvider`, costs its own
  facts and no others.
- **Reports are cached per `(molecule_uuid, structure_version, subject,
  index)`.** The version is `StructureCheckService.current_version()` -- the
  counter that already exists and already increments on every structure
  change -- so a report cannot outlive the structure it describes and there
  is one such mechanism rather than two. Keying on a version rather than a
  timestamp also leaves diffing two reports of one subject as a comparison
  rather than a new subsystem.
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
- **Naming reports every source separately, never one merged answer.**
  A PubChem record is a curated fact; a generated name is a derivation. They
  differ in authority and collapsing them into one string would erase that,
  so `compute_iupac_name` returns each labelled with `source` and `kind`
  (`exact` / `derived` / `parsed`).
- **A generated name is withheld unless it round-trips.** `derived_name_for_
  structure` feeds its own output back through OPSIN and requires the same
  structure out. A rule engine cannot be fluently wrong the way a language
  model can, but it can still be wrong, and a wrong systematic name looks
  exactly as authoritative as a right one. No parser available means the
  name is flagged unverified, not silently trusted.
- **Every outbound HTTP request goes through `openchem/net.py`.** It exists
  because Adoptium sits behind Cloudflare, which rejects Python's default
  `Python-urllib/3.x` User-Agent with a 403 whose body says only
  `error code: 1010` — the Java installer failed on exactly this and reported
  it as a download failure. Identifying the client is also what NCBI's usage
  policy asks of PubChem callers. It sits at the package root, like
  `paths.py`, because callers span layers: `chem/naming_providers.py` reaches
  PubChem and `chem/` must not import from `services/`. A test fails the
  build if any module opens a URL directly.
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

- ~~Packaging~~ **Done.** `build.ps1` freezes the app with **PyInstaller**
  into a ~650 MB one-directory `dist\OpenChemStudio\`, driven by
  `packaging\openchem.spec`. PyInstaller over Nuitka deliberately: nearly
  every packaging failure here is a missing data file that produces a
  silently blank window rather than a build error, so the build/launch/
  see-what-is-blank cycle gets run repeatedly, and PyInstaller's is minutes
  where Nuitka's is tens of minutes. Startup speed is not the bottleneck.

  The spec carries a comment per bundled item; the four that matter, all of
  which fail silently:
  - **QtWebEngine** needs `QtWebEngineProcess.exe`, `resources/`, and at
    least one `qtwebengine_locales/*.pak` adjacent at runtime. Qt's `.qm`
    translations are trimmed (the app has no translations); the Chromium
    locale packs are *not* — dropping them all is one way to get three blank
    web views. `build.ps1` asserts these exist post-build.
  - **`vendor/data/` must stay a sibling of `vendor/iupac_namer/`**, since
    data is resolved from two different module depths. Verified by naming a
    molecule in the built app, not by a file listing.
  - **`sascorer`** (`rdkit/Contrib/SA_Score`) is source imported by name off
    `sys.path`, which `collect_data_files` skips by default. Missing, it took
    down *every* Physicochemical property, not just its own descriptor.
  - **`sys.stdout` is `None`** in a windowed PyInstaller build. py2opsin reads
    `sys.stdout.encoding`, so naming died with a `TypeError` from py2opsin's
    own broken error handler, naming neither stdout nor the real fault. The
    frozen entry point (`packaging\openchem_launcher.py`) attaches real
    devnull streams before the app starts.

  `plugins/` ships as source **beside** the exe rather than inside the
  payload, so a user can add one without a Python install;
  `PluginManager` looks there when `sys.frozen` is set. Sidecars (pkasolver,
  ADMET, Temurin, ORCA, Vina) are not bundled and are still found in the
  configurable data directory — confirmed in the frozen build, which located
  a real Vina 1.2.7 and a managed Temurin JRE.
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
- `MacromoleculeModel` only stores raw PDB/mmCIF text. Chains and residues
  are no longer unreachable, though — `chem/structure_summary.py` derives
  them on demand, and the Docking panel's "Contents..." both shows them and
  lets chains be excluded from the receptor. Derived rather than stored
  deliberately: the summary is a view of `structure_text`, and caching it
  on the model would give the model a second copy of the truth that goes
  stale the moment the text is replaced.

  **BIOLOGICAL ASSEMBLY is the part still missing**, and it is not the same
  question as the symmetry copies `is_symmetry_generated` now discards.
  Those are junk Open Babel invents when it cannot parse a space group; an
  assembly (`pdbx_struct_assembly` / `pdbx_struct_oper_list` in mmCIF,
  `REMARK 350` in PDB) is curated depositor annotation saying which
  transformations produce the biologically real oligomer. It matters for
  docking because a deposited asymmetric unit is not always the functional
  unit, and a binding site can sit at an interface that only exists once
  the assembly is built.

  BinaryCIF is no longer: `chem/binarycif.py` decodes it and
  `chem/structure_io.py` routes files by content (and gunzips) at import.
  The `structure_text`/`source_format` split did prove sufficient, though
  for a different reason than it was written for — decoding happens at the
  boundary, so `structure_text` stays a `str` rather than growing a bytes
  variant. That is also the correct call and not just the convenient one:
  Open Babel prepares every docking receptor and reads neither BinaryCIF
  nor MMTF, so a binary-carrying model would have been viewable and
  un-dockable.

  **MMTF is refused rather than deferred** — `mmtf.rcsb.org` no longer
  resolves and the vendored Mol* bundle has no MMTF reader, so there is
  neither a source nor a viewer for it.
- `RDKitTemplateProvider`'s bundled-plus-user-dir templates are an
  extensibility point with nothing built on them yet: a formal
  `context.reactions.register(...)`-style plugin-provided-templates
  namespace is a real gap, not silently dropped.
- Docking receptor prep (`VinaDockingProvider`) has no missing-residue
  repair, and after a spike that is a DECISION rather than a gap. The
  dependency objection turned out to be obsolete — PDBFixer is three
  packages and 125 MB with cp313 Windows wheels — but the gaps are not
  near binding sites (zero of 49 curated receptors have a chain break
  within 10 Å of their site; only 3 of 48 have incomplete side chains
  there), and the repair is a template-built prediction that lands a
  median 2.3 Å from atoms actually observed in sister chains of the same
  receptor. See `chem/docking_providers.py`'s class docstring for the
  numbers. Revisit if a method reports per-atom confidence.
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
