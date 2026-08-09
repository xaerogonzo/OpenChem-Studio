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
| `openchem.domain` | Pure data: `MoleculeModel`, `ProjectModel`, `DescriptorValue`, `ConformerModel`, the report types (`Fact`/`Detail`/`AtomReport`/`BondReport`/`MoleculeReport`/`ReportResult`), `MacromoleculeModel`, `DockingBox`/`DockingPoseModel`/`DockingResultModel`, plus the shared `CacheState` enum and `Provenance` dataclass (`domain/common.py`). No RDKit, no Qt. Molecules (and macromolecules, and docking results) are identified by UUID, never filename or list position. **`crystal.py` (`Lattice`/`SymmetryOperation`/`Site`/`Crystal`) is the periodic solid, and it does NOT inherit from the molecule model in either direction** — see "A crystal is not a molecule" below, which is the load-bearing decision of that work. |
| `openchem.chem` | The only place `rdkit`/`openbabel` are imported, and by some margin the largest package (81 modules, plus the `regulatory/` subpackage). Grouped by what they are for, since the flat listing is no longer navigable: **core** — `engine.py` (`ChemistryEngine`: MoleculeModel <-> RDKit Mol, canonicalization, 2D depiction including the property heat map, 3D measurement, and `formal_charge()`, the one place UI gets a chemistry-derived default without importing rdkit), `identifiers.py`, `io_backends.py`. **Structure files** — `structure_io.py`, `binarycif.py`, `structure_summary.py`, `structure_assembly.py`; see the pipeline section below. **Docking** — `docking_providers.py`, `vina_engine.py`, `pose_analysis.py`, `binding_site.py`, `receptor_library.py`, `interaction_analysis.py`. **Quantum/spectroscopy** — `orca_engine.py`, the `nmr_*` family (database lookup, HOSE codes, scaling, TMS referencing, the lookup+ORCA hybrid, correlation, signals), `huckel.py`, `electronic_properties.py`, `dipole.py`, `boltzmann.py`, `vibrational_modes.py` (normal-mode character by internal-coordinate decomposition), `mode_animation.py`, `orca_surfaces.py` + `cube.py` (driving `orca_plot` and reading Gaussian cubes into the existing `ScalarField`), and `jcamp.py` + `spectrum_overlay.py` (reading a measured spectrum and reconciling it with a computed one). **Calculators** — `descriptor_providers.py` plus the per-topic modules it registers (`topology_analysis`, `geometry_analysis`, `surface_analysis`, `elemental_analysis`, `steric`, `substructure`, `structure_generators`, `markush`, `logd`, `ph_curves`, `mpo_scores`, `bbb_stereo`, `scalar_field`, `alignment`, `molecular_dynamics`, `calculator_options`). **Sidecars** — `pka_providers.py`/`pka_runner.py` and `admet_providers.py`/`admet_runner.py`, each a pair where the `_runner` is executed BY the sidecar's own interpreter and imports nothing from `openchem`. **Naming** — `naming_providers.py` (structure <-> name across PubChem, the vendored engine, and OPSIN, each result labelled with its source and whether it is `exact`, `derived` or `parsed`) and `structure_annotation.py`, which takes the SECOND return value the naming engine always had: ring systems, functional groups, stereocentres and atom numbering, as plain atom-indexed data no vendor type escapes from. **Substances and bonding** — `substance.py` (what a structure IS rather than what it contains: molecule / ion / ionic salt / coordination / organometallic / mixture, each with its evidence, and a REFUSAL with its reason when the graph does not decide — `[Na+].[Cl-].[K+].[Br-]` could be NaCl+KBr or NaBr+KCl and nothing in the drawing says which; it also names the coordination polyhedron, but only from a real 3D conformer and only as an RMS deviation over EVERY donor-metal-donor angle against a reference with the same donor count -- the donor count never decides on its own, and the 10-degree tolerance is bounded below by the tris-chelate octahedra it must accept and above by the closest pair of references it must not match together), `organometallic_adapter.py` (**the only file that touches the vendored namer's perception**, deliberately, so that when that engine changes one file needs repairing rather than four), `lattice_energy.py` (Kapustinskii from the Shannon six-coordinate radii in `data/ionic_radii.json`; refuses polyatomic ions by name because they need a thermochemical radius instead), `electron_shells.py` (an atom's configuration as `(n, l, occupancy)` triples — **the configuration string is an OUTPUT, never the state**, because taking an electron off the end of the displayed string is wrong for exactly the ions people try first: Fe's 4s empties before 3d though it filled after). **Crystallography** — `cif.py` (a small-molecule/mineral CIF reader, **separate from `binarycif.py`**, which is protein-oriented and reads neither crystal symmetry nor site occupancy — the overlap is "both are text with loops in"), `crystal_analysis.py` (density, coordination shells under explicit periodic images, and the scene a viewer draws; a `Neighbour` carries the position of the IMAGE that is close, not the asymmetric-unit atom's, which is what lets `describe_site` answer a click with the same geometry classifier the molecular path uses), `crystal_report.py` (the facts, and the list of molecular calculators that do not apply -- derived from each calculator's own `applies_to` declaration, whose default is molecule-only, rather than from a blocklist of category names that had rotted in both directions). **Batch** — `result_reduction.py` (every result shape collapsed to table cells), `analytics.py`, `clustering.py`. **Regulatory** — the `regulatory/` subpackage: `types.py` (the legal-source / machine-interpretation split), `predicates.py` (the rule language), `engine.py`, `loader.py`, `calculator.py`. It is a subpackage rather than flat modules because it is the only part of `chem` with its own data format, build step and on-disk rulesets. |
| `openchem.services` | `DescriptorService`, `ConformerService`, `MeasurementService`, `ImportService`, `ExportService`, `ProjectService`, `DockingService`, `QuantumChemistryService`, plus `ProgressHandle` for cancellable/progress-reporting long operations. All but `QuantumChemistryService` own `QThreadPool` execution and publish events — `QuantumChemistryService` is the one exception (see design decisions below). **Set-of-molecules services:** `BatchService` (runs chosen descriptors/calculators across a whole project as ONE pooled task, so "molecule 47 of 200" is reportable and one cancel flag stops it), `ScreeningService` (queues N ligands through `DockingService` one at a time rather than starting N Vina processes; it advances by *listening* for each job's terminal event, so no thread blocks), and `TableExportService` (`BatchTable` -> CSV/Markdown; deliberately not folded into `ExportService`, which is constructed with a `ChemistryEngine` and dispatches by chemical format — there is no chemical format whose subject is a table). |
| `openchem.commands` | `QUndoCommand` subclasses wrapping service calls, giving undo/redo for structure edits, conformer generation, docking results, quantum-chemistry conformers, and project operations from day one. |
| `openchem.plugins` | `interfaces.py` (`Plugin`, `DescriptorProvider`, `ConformerProvider`, `DockingProvider`, `QuantumEngineProvider`, `FactProvider`, `PanelProvider`, `MenuProvider`, `Importer`, `Exporter`), `manifest.py` (`PluginManifest` + dependency topological sort), `context.py` (`PluginContext`, including the `context.secrets` namespace backed by the OS keychain via `keyring`, and `context.molecules`/`context.docking`/`context.quantum_chemistry`), `ui_registry.py` (`UIRegistry` protocol), `manager.py` (`PluginManager` — discovery, transactional load/unload/reload, hot-reload watcher). See `PLUGIN_SDK.md`. |
| `openchem.app` | Composition: `MainWindow`, typed `Settings`, `SessionManager`, structured logging setup. `MainWindow` implements the `UIRegistry` protocol and constructs `PluginManager` at the end of `__init__`. |
| `openchem.ui` | Widgets and dock panels. `EditorBackend`/`KetcherEditorBackend` (2D, `resources/ketcher/dist/`), `ViewerBackend`/`Mol3DViewerBackend` (3D small molecules, `resources/viewer3d/`, 3Dmol.js), and `ViewerBackend`/`MolStarViewerBackend` (macromolecules/crystallography, `resources/molstar/`, Mol*) are interface + implementation pairs — new content types get a sibling implementation, or a new optional capability method on the shared `ViewerBackend` base, without touching chemistry, services, or commands. `panels/docking_panel.py` and `panels/quantum_chemistry_panel.py` are core (not plugin) panels, same tier as `PropertyPanel`. Two widgets **compute nothing and are handed already-decided data**, which is what keeps `ui/` free of the chemistry layer: `widgets/atom_diagram.py` (shell rings with a p/n nucleus, and orbital boxes with spin arrows, drawn from `chem/electron_shells.py`'s triples) and `widgets/substance_card.py` (the Properties panel's identity header, whose shape follows what the structure IS — a salt shows its formula unit and its ions, a complex its metal and two named counts). |
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

`spikes/` holds **throwaway learning kept for its findings**, not shipped
code — nothing under `src/` imports it and pytest collects nothing there.
A spike goes in when the cost of re-deriving what it measured would exceed
the cost of keeping it. Currently one entry, `spikes/crystallography/`:
the probe that established what the vendored 3Dmol will and will not do
with a CIF, its `FINDINGS.md`, and `render_reproducibility.ps1`.

**Run `render_reproducibility.ps1` after any change to `viewer.html`'s
draw paths.** It launches the app N times, performs the same import, and
counts the drawn pixels. That matters because the viewer failed to render
about 2 launches in 5 for an unrelated scheduling reason, so a single
screenshot could not tell a fix from luck — and several conclusions
reached that way were wrong.

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

### The presentation layer (Phases 0-4)

- **One renderer for every report.** `ui/widgets/fact_view.py` takes
  anything with `facts`/`by_category()`/`find()` and draws it: grouped
  sections, search, a depth filter, per-fact basis and evidence, a
  uniform Copy/Export/Compare/Open-in-window menu, and a detached window.
  It knows no chemistry. The Atom Inspector was its first consumer and
  kept only navigation; the Property panel opens reports in it through
  "Details...". Hyperlinks, copy formatting, units and filtering are one
  widget to change rather than eight panels.

- **`ReportResult` replaced `AlertResult` for reports, not for alerts.**
  `AlertResult.matched` is a `list[str]` and had become the generic line
  carrier: 25 `alert_id`s, only four of them real catalogs, so four
  fifths of the app's output rendered as warnings. A `Fact` carries
  units, basis, evidence, limitations, which atoms it is about and how
  specialist it is -- all of which was already computed and flattened
  away. `AlertResult` stays for PAINS/BRENK and for the plugin API;
  `chem/report_adapter.py` converts one to facts permanently, not as a
  shim.

- **The batch table shows what flattening cost.** `_reduce_alert` has to
  PARSE `"Randic index: 9.52"` back apart, and refused 25 of 98 lines
  when measured. `_reduce_report` has nothing to recover. Column ids are
  byte-identical across the change, so saved tables and exports survive.

- **Colour means one thing.** Red is failed, dangerous or invalid;
  amber is "look at this"; green is a verdict only a catalog may give;
  everything else is neutral. Each carries a glyph as well, so the
  meaning survives colour-blindness and a plain-text paste -- and the
  glyphs are stripped at every exit, because non-ASCII in a Windows
  cp1252 stream raises.

- **Navigation is a rail, not a tab bar.** Twelve tabified panels give Qt
  one `QTabBar` needing 1992 px in about 920, so every label elided.
  `tabifyDockWidget` is what creates that bar, so the panels are no
  longer tabified: one right-hand dock is visible at a time and
  `ui/widgets/panel_rail.py` chooses which. `_LAYOUT_VERSION` in
  `app/main_window.py` discards a saved layout from before the change,
  because `restoreState` restores tabification.

- **The command palette reads, never registers.** `Ctrl+Shift+P` builds
  its list from the rail's panels, `CalculatorRegistry` and the live
  `QMenuBar` -- 113 commands with nothing registering itself, so a new
  calculator or menu item is present because it exists. `score()` in
  `ui/dialogs/command_palette.py` is a pure function so the ranking is
  testable without a dialog.

- **Comparison is a destination and a lens.** `chem/comparison.py`'s
  `compare_values`/`differing_rows` put molecules in columns and
  properties in rows, from values other panels have already published;
  `ui/panels/comparison_panel.py` is the surface and "Compare with..." on
  any report is the way in. The panel never computes -- a blank cell means
  that calculator has not run. Absence counts as a difference, rows keep
  producer order, and "everything agrees" is reported as a result rather
  than an empty table.

- **Empty states are derived, never registered.** Every surface answers
  "what do you show when you have nothing", and the guard asks the panel
  rather than reading a list beside it -- so a tab that shows nothing
  fails whichever mechanism it was meant to use.

### Perception interprets, QuickFix suggests, only the user changes the structure

Three layers, kept distinct in the code and on screen:

    Structure as drawn        the user's graph, never silently altered
            |
    Perceived chemistry       what it represents, with the evidence
            |
    Suggested representation  an OFFER, applied only on request

"This molecule contains a dative bond" and "the user's graph contains a
dative bond" are different statements, and conflating them is how a
program starts rewriting people's structures. `chem/substance.py`
perceives; `chem/quick_fixes.py` offers; nothing between them writes.

The Amavadin case is the worked example. Its vanadium is held by nitrogen
and oxygen donors, which drawn with plain single bonds over-counts the
metal's valence. The coordination is *reported* from the structure as
drawn, and the dative reading is offered as `metal_bonds_to_dative`
through the existing `QuickFix` mechanism — opt-in and undoable, with no
new machinery.

### Four relationships, deliberately not one

    Bond          an actual graph edge: covalent, dative, aromatic
    Association   component <-> component, e.g. Na+ <-> Cl-. NO edge
    Coordination  a PERCEIVED metal-ligand relationship, which may or may
                  not be represented by explicit graph edges
    Hapticity     one ligand bound through a SET of atoms (eta-5)

`[Na+].[Cl-]` has no RDKit bond and **must never grow a fake one**.

**An `Association` carries no number, and must not acquire one.** It is
qualitative — "ionic, evidenced by opposite formal charges". A distance
between two ions is a *contact* measurement, needs a real 3D structure,
and belongs to whatever reports contacts. That discipline is what keeps
the model coherent if crystal structures are ever added, where the same
pair has many distances and no single bond at all.

### Classification is not naming

`chem/substance.py` says what KIND of thing a structure is; the vendored
namer says what it is called. They are read from independent sources and
the name never decides the classification, so a bizarre organometallic
nothing can name still gets its identity header:

    Classification: Organometallic     <- from perception
    Name:           (not named)        <- from the namer
    Formula:        C10H10Fe

which is worth far more than collapsing the card to "unknown" because one
of the two came up empty.

### A crystal is not a molecule, in either direction

`domain/crystal.py` does not inherit from `MoleculeModel` and
`MoleculeModel` does not inherit from it. The overlap is "both have a list
of atoms", and sharing on that basis buys one attribute and then obliges
every molecular calculator to decide what it means for an infinite
periodic structure. Most of them mean nothing for one.

A crystal has no molecular weight, no bonds and no logP; a molecule has no
lattice, no space group and no occupancy. `chem/crystal_report.py`
therefore names the calculators that do not apply — derived from the live
`CALCULATOR_DEFINITIONS`, so one added tomorrow is covered without anybody
remembering this file — rather than leaving a reader to wonder why the
Properties panel looks empty.

Two consequences worth knowing before extending it:

- **Fractional coordinates are the state; Cartesian is an output.** That is
  what symmetry operates on, what wraps, and what a CIF stores. Storing
  Cartesian would also silently pick a cell orientation; the convention is
  fixed and stated (a along x, b in the xy plane) because any other choice
  is equally valid crystallography and will not match anybody else.
- **Expansion wraps, and 3Dmol's does not.** Measured on halite, the
  viewer's own symmetry expansion left 3 of the 4 chlorides at or outside
  the cell — the right set of atoms, the wrong representatives. So Python
  expands and the viewer draws what it is given, which also means the
  picture and the density are computed from the same atoms.

### A vendored module is not an API

`chem/organometallic_adapter.py` is the only place that reaches into
`vendor/iupac_namer/perception/organometallic.py`, and it deliberately
touches private, underscore-prefixed functions of a file this project does
not own. One adapter is one place to repair when the vendored namer
changes; without it, `substance`, `oxidation_states` and `bond_report`
each grow their own coupling. Everything there fails soft — a namer that
cannot classify something must not take a calculator down with it.

The same move `chem/structure_annotation.py` already made for that
engine's ring and functional-group perception.

## Known TODOs

**Every item carries a verdict**, because this list had become half
changelog: three of its eight entries described finished work while
sitting under a heading that says TODO, and a reader could not tell open
from closed at a glance. The detail under a settled item is kept rather
than deleted -- most of it is measurements that cost real time -- but the
label says what it is.

    OPEN        not built, and nobody has decided not to
    DECISION    looked at, deliberately not built, reason recorded
    SETTLED     done; the text below is the record of how

`tests/test_docs_are_current.py` guards the mechanical half of this: no
document may cite a file or a test that does not exist.


- **SETTLED** -- Packaging. `build.ps1` freezes the app with **PyInstaller**
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
- **OPEN** -- `SimilarityService` doesn't exist yet; belongs to a later roadmap phase
  and would currently have no callers.
- **DECISION** -- plugin loading has no async/background state, no `ToolbarProvider`/
  `ContextMenuProvider`, no numeric provider priority, and no declared
  permissions, and no `RemoteServicePlugin` base class exists for the
  network/async/settings/secrets boilerplate common to
  `ai_assistant`/`database_search`/`reaction_prediction` (only `run_async`
  was extracted) — all deliberately deferred, reconfirmed still true as of
  Phase 9: there is still no concrete fourth plugin whose actual
  requirements would tell us what these abstractions should look like, so
  building them now would mean guessing. See the "Explicitly deferred"
  reasoning preserved in `PLUGIN_SDK.md`'s "Known limitations" section.
- **OPEN (partly)** -- `MacromoleculeModel` only stores raw PDB/mmCIF text. Chains and residues
  are no longer unreachable, though — `chem/structure_summary.py` derives
  them on demand, and the Docking panel's "Contents..." both shows them and
  lets chains be excluded from the receptor. Derived rather than stored
  deliberately: the summary is a view of `structure_text`, and caching it
  on the model would give the model a second copy of the truth that goes
  stale the moment the text is replaced.

  **BIOLOGICAL ASSEMBLY is built now**, from PDB, and docking can be
  aimed at it. It is not the same question as the symmetry copies
  `is_symmetry_generated` discards -- those are junk Open Babel invents
  when it cannot parse a space group, while an assembly
  (`pdbx_struct_assembly`/`pdbx_struct_oper_list`, or `REMARK 350`) is
  curated depositor annotation. `chem/structure_assembly.py` parses the
  matrices, composes operator expressions right-to-left, and
  `build_assembly` returns an `AssemblyBuildResult` in which partial
  output is not representable. `DockingJob` builds ONCE and hands the
  identical text to both `dock()` and `receptor_atoms_from_structure`;
  the opt-in is in the Contents dialog, off by default, and a build that
  fails **fails the job** rather than quietly docking the asymmetric unit.

  Three things that were wrong before this landed, each found by writing
  a test rather than by reading:

  - `_loop_rows` dropped any CIF row that WRAPPED across lines, so 1A34's
    60-operator list read as zero operators, silently.
  - PDB operator ids are scoped per `BIOMOLECULE:`, and reading them
    globally put 4EA3's second chain 42 A from where the depositor put it.
  - Every matrix in the catalogue is axis-aligned, so a TRANSPOSED
    implementation passes all 49 deposits. That is why the gate needs a
    general rotation (2OMF's 3-fold) and why the composition test uses
    non-commuting operators.

  **The RCSB gate has landed and the builder passes it**,
  `benchmarks/assembly/`: fetch, build and score against the assemblies
  RCSB generates from the mmCIF `_pdbx_struct_oper_list` where we build
  from `REMARK 350`. 4DKL, 4EA3 and 5I6X match **every atom to the
  written digit**; 1A34 is refused at 208,440 atoms, which RCSB's own
  file confirms to the atom. 2OMF differs on 115 of 8,481 atoms by
  exactly 0.001 A, and that is the deposit rather than either builder:
  the PDB states the matrix to six decimals (`-0.866025`) where the mmCIF
  carries ten (`-0.8660254038`), which moves only atoms sitting within
  ~3e-5 A of a rounding boundary.

  The gate has been shown to FAIL, which is the half that makes it
  evidence. `build.py --mutate transpose` is caught **only by 2OMF**
  (118.5 A) -- 4DKL, 4EA3 and 5I6X pass transposed, for the same reason
  all 49 catalogue deposits do. `tests/test_assembly_gate.py` guards that
  offline: it requires a corpus entry declaring it catches a transpose,
  and then checks the declaration against the real matrix rather than
  trusting the flag.

  **Docked for real, both directions, against a live Vina 1.2.7.** The
  control and the demonstration are separate structures and they separate
  by an order of magnitude:

      4DKL, pocket INSIDE the monomer, same box
          deposited vs built   dRMSD 0.33-0.54 A   dScore 0.008-0.014
          same receptor twice  dRMSD 0.24-0.41 A   dScore 0.005-0.008

      1HHP, HIV-1 protease, site ON the dimer 2-fold, same box
          monomer vs dimer     dRMSD 2.64-9.10 A   dimer better by
                                                   0.92-1.33 kcal/mol

  So building moves 4DKL's pose no more than the search moves against
  itself, and changes 1HHP's binding mode outright while scoring better
  on every seed. 1HHP deposits ONE chain and annotates a dimer, and its
  two catalytic Asp25 come out 5.36 A apart in a clean 2-fold once built,
  which is a check on the build as well as the docking.

  **The seed has to be pinned for any of that to mean anything** --
  `VinaDockingProvider` passes `seed=None`, so the shipped app runs a
  random seed and the same receptor already differs run to run. The
  unpinned spread above is what makes the pinned numbers readable.

  Still open: **building from mmCIF** (PDB refuses assemblies its
  single-character chain id or 99,999-serial limit cannot express, mmCIF
  is exactly the format for those, and it is also the only way to remove
  2OMF's 0.001 and to exercise a product expression at all -- `REMARK
  350` has no expression syntax, so right-to-left composition stays
  unit-tested until then).

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
- **SETTLED** -- `RDKitTemplateProvider` now has THREE template sources, not two: the
  bundled file, the user's app-data file, and `context.reactions`, so a
  plugin can contribute reaction SMARTS. The registry lives in core
  (`services/reaction_template_service.py`) rather than in the reaction
  plugin, because a plugin must not have to import another plugin to
  extend it. Templates are read LIVE rather than snapshotted at
  construction, so load order is not something a template author has to
  reason about.
- **DECISION** -- docking receptor prep (`VinaDockingProvider`) has no missing-residue
  repair, and after a spike that is a DECISION rather than a gap. The
  dependency objection turned out to be obsolete — PDBFixer is three
  packages and 125 MB with cp313 Windows wheels — but the gaps are not
  near binding sites (zero of 49 curated receptors have a chain break
  within 10 Å of their site; only 3 of 48 have incomplete side chains
  there), and the repair is a template-built prediction that lands a
  median 2.3 Å from atoms actually observed in sister chains of the same
  receptor. See `chem/docking_providers.py`'s class docstring for the
  numbers. Revisit if a method reports per-atom confidence.
- **SETTLED** -- a CIF's ion charges are read and used. `chem/cif.py`'s
  `charge_of` parses `_atom_site_type_symbol` (`Na+`, `O2-`) onto
  `Site.charge`, and `crystal_analysis.ionic_formula_unit` reduces a cell
  to `[(count, charge)]` so `volume_based_lattice_energy` can answer.
  **`None` means "the file did not say", never "neutral"** -- the two are
  different claims, and most depositions are silent (halite's own carries
  bare `Na` and `Cl`), so a crystal without stated charges gets no
  lattice-energy fact at all rather than a guessed one. The volume comes
  from the cell, so no ionic radius is involved and a complex ion works
  as readily as a monatomic one.
- **SETTLED** -- every calculator computed on the 2D DRAWING, never on a
  generated conformer. `ChemistryEngine.mol_from_model` reads
  `model.molblock` and never `model.conformers`, so the Properties panel
  reported "The available conformer is 2D" while the 3D viewer showed
  "Conformer 3/3".

  **The design question was already answered six times over.**
  `io_backends.mol_for_export` plus five inline copies
  (`main_window`, `property_panel`, `docking_panel`,
  `quantum_chemistry_panel`, `batch_service`) all did
  `conformers[0] if conformers else the drawing`. That is now one pure
  function, `chem/calculation_input.select_calculation_input`, and the
  six call it -- six copies is not six bugs today, it is one bug the day
  the policy changes to "the conformer the user is looking at".

  **The blanket swap would have been a regression, and the numbers say
  so.** A conformer molblock carries EXPLICIT HYDROGENS: ethylmorphine is
  23 atoms as drawn and 46 as a conformer. Measured across all 49
  registered calculators, run on the drawing and on a conformer with
  timestamps normalised, plus a third run with hydrogens folded back to
  implicit to separate the causes:

        unchanged                            30
        changed ONLY by explicit hydrogens    8   <- the regression risk
        changed by the geometry              11   <- the point of the fix

  The eight are topological -- a Wiener index over 46 atoms is a
  different number from one over 23, and neither is wrong for its input.
  So `CalculatorDefinition.calculation_input` declares `DRAWING`
  (the default, today's behaviour) or `GEOMETRY`, exactly as `applies_to`
  declares structure kinds and for the same reason.

  **Four of the eleven candidates were rejected**, and re-checking them
  found the first recorded reason ("they only echo coordinates into their
  own output") was far too weak. A conformer does not merely fail to help
  the structure generators, it **breaks** them. Measured on alanine drawn
  with its stereocentre left undefined:

        stereoisomers   drawing 2 forms   conformer 1     feature stops working
        tautomers       drawing 4 forms   conformer 10    garbage forms

  `stereoisomers` collapses because a conformer carries stereo PERCEIVED
  FROM ITS COORDINATES, so `onlyUnassigned=True` finds nothing left to
  vary and returns whichever configuration the embedder happened to
  produce -- "what are the stereoisomers of what I drew" is the question,
  and only the drawing can answer it. `tautomers` is corrupted by the
  explicit hydrogens, emitting `[H]O=C(O)...` and `[CH]([H])...`, which
  are not tautomers of anything.

  A third, separate reason: `structure_generators._entry` computes 2D
  coordinates only when the molecule has NO conformer, so a 3D input
  propagates into the structure grid -- which that module's own docstring
  says renders as "a pile". `structural_frameworks` is immune (it calls
  `Compute2DCoords` unconditionally) and is topological besides. Seven
  declare `GEOMETRY`.

  **`GEOMETRY` means prefer, not require**, and the refusal stays where
  it already worked -- `geometry_analysis._require_conformer` and
  `descriptor_providers._compute_shape_descriptors` check `Is3D()` and
  say what to do about it. Duplicating that into the routing policy would
  give two places to drift apart.

  Verified by logging what each calculator RECEIVES, not what it
  returns -- output can look plausible when the wrong molecule went in:

        topology_analysis     drawing    23 atoms   0 H   Is3D False
        geometry_analysis     geometry   46 atoms  23 H   Is3D True    conf 33be70ce, 109.52 kcal/mol

  Before the change, `geometry_analysis`, `surface_analysis`,
  `dipole_moment` and `atom_sasa` returned FAILED ("The available
  conformer is 2D") on every molecule however many conformers it had.
  **`steric_analysis` was worse: it returned COMPLETED**, computing a
  cone angle and %Vbur on a flat structure and reporting a plausible
  number -- correct arithmetic on the wrong object, the same shape as the
  40619 kcal/mol interaction energy.

  Each result now records `input_source`, `input_conformer_id` and
  `input_conformer_index`. The ID, not only the index: index 0 today is
  index 3 after the next regeneration, so a result citing a position
  cannot be traced back to a geometry.

  **The `input_` prefix is a collision fix, not a style choice.** These
  keys merge into a provenance the CALCULATOR also writes, and the two
  describe different things in the same words -- this layer records what
  a calculator was HANDED, the calculator records what it DID.
  Unprefixed, two of the 49 collided silently, the calculator's value
  winning and the routing layer's simply vanishing:

        steric_analysis     geometry_source = "free_ligand_mmff"
        molecular_dynamics  force_field     = "MMFF94"

  Neither is wrong; both wanted the same words for a different thing.
  Only the first was found by reading the code -- the second came out of
  a sweep over every calculator, which is why
  `test_no_calculator_provenance_key_collides_with_the_routing_layer`
  iterates the whole registry rather than the names anybody noticed.
- **SETTLED** -- the Properties panel CLIPPED long result values. **There is no height clipping**: `WrappedLabel` already closed
  that, and a font-metrics probe (self-tested, so it can see a clip)
  finds none at any width. What the panel actually did was STARVE the
  value -- the label column sizes to the widest label, so at the 170 px
  the dock gave it, a six-line result rendered as 24 lines.

  **Fixed for ordinary result rows**, verified by driving the app:
  `WrapLongRows` on the section's form layout, a 200 px minimum on
  multi-line values, and a 280 px minimum on the panel. Six lines render
  as six at every width, with no vertical cost -- `WrapAllRows` also
  fixes it and was measured at +75% section height, because this panel
  is mostly short scalars.

        arm                       170   240   300   360
        shipped                    24L   12L   10L    6L
        value>=140, no panel min   10L    6L   10L    6L
        value>=200, panel>=280      6L    6L    6L    6L

  **THE REPORT ROW IS FIXED. It took NINE attempts and three published
  diagnoses, all of which blamed the field, and the field was never the
  problem.** The account below is kept in full because every wrong turn
  in it was expensive and several of them look reasonable.

  **The fix, in three parts, all of which are required:**

  1. `ExplicitHeightLabel` -- a wrapped label that states a fixed height
     and reports NO height-for-width, used for every long value inside a
     `CollapsibleSection` (property panel alerts, results, reports and
     hints; `fact_view`'s `_FactRow`, which had the identical latent
     bug).
  2. `DontWrapRows` on the section's form, because `WrapLongRows` is
     height-for-width whatever its children are.
  3. `PropertyPanel._add_wide_row` -- a genuine spanning row, which is
     what gives a long value the full width now that the wrap policy no
     longer does. It also removed the minimum-width hack, and with it the
     sideways scroll that hack caused.

  Measured in the running app, Identity section with one report row,
  panel at 280 px:

        level                  before        after
        report row container   14 of 144     172 ok
        section content        94 of 206     249 ok
        CollapsibleSection    113 of 225     268 ok
        the value's WIDTH      152 px        238 px  (full width)

  Verified on screen as well as in the numbers: six lines, nothing
  truncated, the Naming section below it rather than through it. Suite
  3504 passed.

  **The old account follows. Read it before touching this again.**

  Measured IN THE RUNNING APP with `OPENCHEM_INSTRUMENT_PANEL=1`
  (`property_panel._dump_panel_metrics`), which is the only measurement
  here that describes the panel a user sees:

        row                       width  height  sizeHint  minSizeH  hasHfW  hfw
        Elemental Analysis (row)    238      14        96       144    True  112
            inside -> QLabel        152      14        96       112    True  112
        mol_wt -> QLabel            173      16        16        16   False   -1

  **THE STARVATION IS AT THE SECTION, NOT THE FIELD.** Every number in
  that table is correct and none of it is the bug. One level up:

        section          height  minSizeH  content h  content m  form min
        identity            113       225         94        206       166
        physicochemical     109       109         90         90        82

  The Identity section is given 113 px while asking 225, its content 94
  of the 206 it asks for, and the form then shares that shortfall out
  among its rows. `form min` 166 is exactly right -- `formula` 16 +
  report row 144 + spacing 6 -- and is simply not honoured.

  **The tell had been sitting in the log for a session.** In the dump
  taken BEFORE the report row exists, `formula` is 16 px tall; in the one
  after, it is 14. Nothing about a report row can shorten an unrelated
  scalar row -- only a container short of space can, by shrinking
  everything inside it. Compare the two dumps before theorising about the
  field.

  **The mechanism: a vertical `QBoxLayout` holding a height-for-width
  item uses that item's `heightForWidth` IN PLACE OF its minimum**, and
  one `WrappedLabel` anywhere inside makes every ancestor layout
  height-for-width carrying. Asked directly, the container's own layout
  item says so:

        item CollapsibleSection  geom_h=113  minSize=225  hfw=75

  225 is right and unused. 75 is the height the section needed BEFORE the
  report row's text arrived. `physicochemical` is fine for the reason
  this predicts -- it holds only plain labels, so its minimum and its
  `heightForWidth` agree at 109 and there is nothing to substitute.

  **THREE DIAGNOSES HAVE BEEN PUBLISHED HERE AND ALL THREE WERE WRONG.**
  First "the height-for-width chain does not survive the container" -- it
  survives. Then "the cause is width, not height" -- that came from an
  out-of-app harness and the app contradicts it. Then "`QFormLayout`
  ignores the field's minimum" -- it does not; the form never had the
  space to give.

  **Six fixes, each falsified by measurement rather than by argument:**

  1. Delegating height-for-width from the container. No change.
  2. Removing the container, button on its own row. Rows overlapped.
  3. "Details..." as a link in rich text. Still one line.
  4. Moving the button into the label column. The harness showed full
     parity with an alert row; the app still truncated.
  5. `heightForWidth` on `CollapsibleSection`. Never consulted --
     `QWidgetItem.heightForWidth` routes through the widget's LAYOUT and
     only falls back to the widget's own virtual when it has none.
     Measured: the item answered 75 while the widget answered 215.
  6. `heightForWidth` on the section's layout, floored at
     `minimumSize()`. It IS consulted, and it cannot help. Traced at the
     deciding call: `natural=75 floor=75`. The layout's cached geometry
     is stale during the pass that assigns the height and fresh
     immediately afterwards, so a floor read from it is stale in exactly
     the same way.

  **A relayout is NOT the answer, and this was tested properly.**
  Invalidating every layout in the panel, pumping the queue to
  completion and calling `activate()` on each leaves the section at 113.
  An earlier version of that probe pumped `processEvents()` once, which
  cannot tell "the relayout does not help" from "the relayout never
  finished" -- do not accept a single pump as an arm.

  **ONE LEVER WORKS AND IT IS NOT SUFFICIENT.** An explicit
  `setMinimumHeight` on the section survives the substitution, and fixes
  every number: section 225/225, report row 14 px -> 112, `formula`
  14 -> 16. But the parent layout still positions the SIBLINGS from the
  stale 75, so the section paints straight over the Naming, Charge and
  LogP headers below it. Confirmed by forcing a repaint and
  re-screenshotting -- it is a real overlap, not stale paint, and it is
  the same failure mode as fix 2 above. An overlap is worse than a
  truncation, so this was reverted rather than shipped.

  Two further fixes were built on that lever and BOTH still overlap:

  7. explicit minimum + `parent.layout().invalidate()`;
  8. the same plus an immediate `parent.layout().activate()`.

  **SO THE MINIMUM CAN NEVER WIN, AND THAT IS THE ANSWER TO "WHY IS THE
  HEIGHT-FOR-WIDTH STALE".** `QBoxLayout::setGeometry` assigns
  `a[i].sizeHint = a[i].minimumSize = item->heightForWidth(width)` for
  every height-for-width item before it distributes space. The minimum is
  not consulted, ignored or lost -- it is OVERWRITTEN. An explicit
  `minimumHeight` changes the widget's own size (which is why the rows
  render) without changing its ALLOCATION, and a widget larger than its
  allocation is exactly an overlap. No amount of invalidating,
  activating or re-pumping changes that, because nothing there is stale
  in the sense that a refresh would fix.

  **`physicochemical` is the control that proves it.** It holds only
  plain labels, so nothing in it is height-for-width, no substitution
  happens, its minimum is used, and it has never once misrendered.

  So a fix has to make `heightForWidth` itself correct at the moment the
  parent lays out, or take the report row out of the height-for-width
  chain so the section behaves like `physicochemical`. The root of the
  inconsistency is that **`WrappedLabel.minimumSizeHint()` computes a
  height from `self.width()` -- a layout OUTPUT used as a layout INPUT**,
  so every cached minimum in the chain is a function of whatever width a
  previous pass happened to assign. It is wrong in both directions at
  once, measured in the same dump: at the ROW, `minSizeH` 144 is the
  stale one and `hfw` 112 is right (112 is what the row rendered at when
  it worked); at the SECTION, `minSize` 225 is right and `hfw` 75 is
  stale.

  **THE CAUSE IS NOW PROVEN, BY REMOVING IT.** That candidate was built
  -- `ExplicitHeightLabel`, a wrapped label that states a fixed height
  and clears its height-for-width flag -- and it was not enough on its
  own, because **`QFormLayout`'s `WrapLongRows` policy makes the FORM
  height-for-width carrying whatever its children are.** Whether a row
  wraps depends on the width, so the form's height does too. With both
  the label and that policy changed, nothing in the chain offers a
  height-for-width, and every level comes right at once:

        level                 with WrapLongRows      without
        report row container    3 of 144 px          144 ok
        section content        56 of 206             206 ok
        CollapsibleSection     75 of 225             225 ok
        sections container    990 ok                 990 ok

  Confirmed on screen as well as in the numbers: the value renders in
  full and the Naming section sits below it rather than through it.

  **IT IS NOT SHIPPED, AND THE REASON IS A TRADE ALEX SHOULD MAKE.**
  Turning off `WrapLongRows` takes the full-width treatment away from
  every long value in the panel -- Elemental Analysis renders in 9 lines
  where 6 would fit -- and it fails five guards in
  `tests/test_property_panel_long_values.py`, one of them substantively:
  at 170 px the panel scrolls SIDEWAYS, which this file already calls
  worse than the wrapping it replaced. So it swaps one documented
  behaviour for another rather than fixing both.

  Three options were weighed and the third was built -- it is the one
  described at the top of this entry. The other two are recorded because
  each is a trap that looks like a fix:

  1. Leave it. Long values get the full width; report rows truncate.
  2. `ExplicitHeightLabel` + `DontWrapRows` ALONE. Nothing truncates, and
     long values lose the full width because nothing replaces the wrap --
     they render in 9 lines where 6 fit, and the panel scrolls sideways
     below ~200 px. Five guards fail. This is option 3 with its third
     part missing, and it is why `_add_wide_row` exists.

  **A `WrappedLabel` ANYWHERE in a section puts the height-for-width
  back and the substitution with it**, so the migration had to include
  alert rows, result rows, the hint labels and `fact_view`'s `_FactRow`.
  Half a migration leaves any section that mixes the two broken exactly
  as before. `test_no_layout_in_a_section_offers_a_height_for_width`
  walks every expanded section's three layers and is the guard on that;
  it fails if a `WrappedLabel` comes back.

  One Qt fact worth keeping regardless, which cost a run on its own:
  **`QLabelPrivate::updateLabel()` re-derives the size policy's
  height-for-width flag from the word-wrap flag on every label update**,
  so clearing it in `__init__` is undone by the first `setText`:

        after __init__ sequence   False
        after setText             True

  Clearing it once made things WORSE than not trying -- the label held a
  correct fixed height while the chain stayed height-for-width carrying,
  so the section collapsed to 75 px and crushed its rows to 3 px each,
  against 14 before.

  **DO NOT TRUST AN OUT-OF-APP HARNESS FOR THIS PANEL.** It said there
  was no clipping while the app clipped, no horizontal scrollbar while
  the app had one, and a full-width label while the app truncated. Use
  the env var.

  Two measurement traps paid for here, both general:

  - **A scroll area's content gets its VIEWPORT width, not the widget's.**
    The panel minimum was first derived against a section short enough
    not to scroll; the real panel always has a vertical scrollbar, which
    takes 24 px. Shipped at 240 it produced exactly the horizontal
    scrollbar the constant exists to prevent -- a panel that scrolls
    sideways being worse than one that wraps.
  - **The suite's `QT_QPA_PLATFORM=offscreen` uses a different font.** The
    same line needs 187 px on the platform a user sees and 420 px
    offscreen, so a "renders in six lines" assertion measures the test
    environment. `tests/test_property_panel_long_values.py` asserts the
    WRAP instead, which is font-independent. Note it does NOT catch the
    240 px case -- the live check did, and that gap is why the panel
    minimum needs re-checking in the app rather than in the suite.

  The in-process probe that once said "ok" was CIRCULAR and must not be
  repeated: it compared each label's `height()` against its own
  `minimumSizeHint()`, which `WrappedLabel` computes FROM its width, so
  an under-reporting hint passes while the text is cut off.

  Four more traps paid for while measuring this, all general:

  - **ASK THE LAYOUT ITEM, NOT THE WIDGET.** A layout consults
    `QLayoutItem`, and the two disagree here: the item answered
    `heightForWidth` 75 where the widget answered 215. Every recorded
    measurement before this one printed the widget's numbers, which is
    why the field looked guilty for three diagnoses running.
  - **An unparented widget is a WINDOW, so `QWidgetItem` treats it as
    empty** and answers `hasHeightForWidth() == False` and
    `heightForWidth() == -1` whatever the widget overrides. One probe
    "proved" the virtual is never called purely because of this. Parent
    the widget before asking a layout question about it.
  - **`awk`-ing the log for "the second dump" reads across SESSIONS.**
    The log is append-only and holds every run, so a naive filter
    silently mixed a fixed session with an old broken one and produced
    one wrong verdict about a fix. Cut from the last
    `session started` banner every time.
  - **A screenshot is not a repaint.** The first look at the working
    lever showed text over the sections below it, which could equally
    have been stale paint. Scrolling the panel and re-capturing is what
    made it a finding.

  The Details buttons are NOT implicated: the app shows one per report
  row, correctly bound, exactly as the code intends.
- **SETTLED** -- conformer generation returned implausibly few. A morphine
  derivative (C19H23NO3) gave "Kept 2 distinct conformer(s) of 10
  embedded", and 3 on an earlier run. `benchmarks/conformers/` is the
  regression check that did not exist; the same molecule now returns
  10-14 across five seeds against a reference lower bound of 12.

  **The de-duplication threshold was the suspect and was not the
  cause.** 0.5 Å was calibrated on butane, whose pairwise RMSDs are
  genuinely bimodal -- "below 0.5 or at 0.66, nothing between". That
  bimodality is a property of butane. Ethylmorphine's are a continuum,
  so no threshold works: 0.35 saves cyclohexane's twist-boat (which 0.5
  merges, calling a textbook two-conformer molecule rigid) and breaks
  ethanol and butane. **Every purely geometric criterion tested failed
  the validation set**, all-atom RMSD included.

  **Both geometric measures are blind to what these molecules do.** On a
  fused polycyclic a ring puckers through >100 degrees while the heavy
  atoms barely move -- 100 of 108 vetoed pairs had a torsion beyond 60
  degrees while sitting under both cut-offs (RMSD 0.207-0.496, TFD
  0.008-0.072 against a literature cut of 0.2). An energy term breaks
  the tie, strictly as a **merge veto**: it declines to merge on
  insufficient evidence and never claims two structures ARE different
  conformers. Below 0.15 Å it is not consulted at all, because ~2% of
  2H-azirine embeddings converge to a distorted minimum 10.7 kcal/mol up
  (C=N stretched to 1.339 Å) and an energy gap must not promote a
  bond-length artefact to a conformer. An energy CEILING was measured as
  the alternative and cannot work -- that artefact sits inside
  ethylmorphine's genuine 17.9 kcal/mol span.

  Two secondary defects fixed alongside: `MMFFOptimizeMolecule` ran at
  RDKit's default 200 iterations with its return code discarded (1 in 10
  embeddings did not converge and sat 3.67 kcal/mol high while being
  ranked as "lowest in energy"), and the dialog's "Number of conformers"
  was passed to the EMBEDDER, so 10 requested meant 10 random attempts.

  **This is not solved, and `SCIENTIFIC_LIMITATIONS.md` says so.** It is
  the best-performing heuristic on eleven molecules, half of whose
  references are computational lower bounds.
- **SETTLED** -- the ADMET calculator "produced nothing". **It produced
  everything, off the bottom of the screen.** This entry used to say the
  first question was whether the sidecar was being found; it was found,
  and asking that first is what kept the answer hidden.

  Checked in order, each measured rather than assumed:

        the sidecar interpreter is configured      yes
        running admet_runner.py by hand            exit 0, 104 columns
        the tier filter matches the columns        10/10, 17/17, 39/39
        the interpreter path reaches the calculator yes -- bootstrap
                                                   binds it per call
        the calculator through the REAL registry   COMPLETED, 12 lines
        the app log after a run in the GUI         nothing at all

  That last line is the one that misleads: only a FAILURE logs, so an
  empty log means "no exception", not "never ran". Sampling for the
  subprocess DURING a run showed it spawning normally. The row was there
  the whole time -- scrolling the panel down found
  `hERG blockade: 0.82` sitting in the ADMET / Toxicity section, which is
  collapsed by default and sits near the bottom of twenty-odd sections in
  a ~1000 px content area behind a 372 px viewport.

  **The real defect is an asymmetry in how results announce
  themselves.** Four of the six result shapes already answer a button
  press unmissably -- a per-atom dataset, a spectrum, a structure set and
  a pH curve each open a dialog when they match
  `_pending_calculator_id`. The two that render INLINE, an alert and a
  report, had no such handling, so the more a result had to say the
  better it was hidden. `PropertyPanel._reveal` expands the section and
  scrolls the row to the top of the viewport; a result nobody asked for
  (a batch run leaves `_pending_calculator_id` unset, deliberately) does
  not move the view.

  Two things measured while fixing it, both worth keeping:

  - **`ensureWidgetVisible` moves BOTH axes.** A row a little wider than
    the viewport made the panel scroll sideways, leaving every label
    clipped on its left edge ("bb_permeant", "unctional Groups") --
    the failure this file already calls worse than the one being fixed.
    Setting the vertical bar alone cannot do that.
  - **It also scrolls the MINIMUM distance, against a height that is not
    settled.** An `ExplicitHeightLabel` fixes its height from its width
    during the layout pass, so just after a row is added it is still
    short, and the caption arrived flush against the bottom edge with the
    values below the fold -- the same invisibility, one step smaller.
    Anchoring the row's TOP does not depend on its final height, so it is
    right whenever it runs.

  Guards: `test_an_explicitly_run_row_result_is_scrolled_into_view` and
  `test_a_result_nobody_asked_for_does_not_hijack_the_scroll`. Both
  mutation-tested, including against the `ensureWidgetVisible` version.
- **OPEN, possibly correct behaviour** -- IUPAC Name reports
  "A name was derived but did not parse back to this structure, so it is
  being withheld" on a morphine derivative. That is the namer's honest
  round-trip refusal working as designed, but on a real drug-like
  molecule it reads as a broken feature. Worth deciding whether to show
  the withheld name marked as unverified rather than nothing at all.
  IUPAC Locants on the same molecule DOES work (18 of 23 atoms numbered,
  rendered in the Calculator Inspector with both depictions).
- **DECISION** -- a calculation cannot be ADDRESSED to a crystal.
  `CalculationRequest` carries a `molecule_uuid` and nothing else, which
  makes the mistake unrepresentable rather than merely discouraged;
  `CalculatorDefinition.applies_to` describes the intent alongside it. If
  that field ever becomes a `structure_uuid`, every calculator's
  declaration becomes load-bearing at runtime and
  `test_a_calculation_cannot_even_be_ADDRESSED_to_a_crystal` is the place
  that says so.
- **OPEN** -- no shipped plugin calls `context.reactions`. The namespace
  and its rollback are covered by tests including an end-to-end one, but
  the third-party story would be more convincing with an `examples/`
  plugin that actually registers a template.
- **OPEN, cause unknown** -- the 3D viewer rendered a black half-height
  canvas in 3 of 5 and then 4 of 5 cold launches, then went 9 of 9 and 5
  of 5 clean with no relevant change. **No cause was established and the
  sizing fixes are not claimed to be one.** Recorded here rather than
  quietly forgotten: if it returns, `spikes/crystallography/`
  `render_reproducibility.ps1` is the harness, and CLAUDE.md carries the
  measurement trap that made the first attempt worthless (a black canvas
  scores as heavily INKED, so a failed render read as a success).
- **OPEN** -- `DockingPoseModel.metadata`'s H-bond/clash analysis (Phase 9.4) is a
  heavy-atom-distance heuristic only — pharmacophore/hydrophobic contact
  detection is a real gap, less standardized and meaningfully more work
  than what's built.
- **SETTLED** -- Vina and ORCA execution are verified against real installed
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
