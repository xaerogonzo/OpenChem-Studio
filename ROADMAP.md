# Roadmap

## Phase 1 — Application shell (in progress)
- [x] PySide6 `QMainWindow`, menu system, dockable panel layout
- [x] Project system (`ProjectModel` + `ProjectService`, `.ocsproj` JSON)
- [x] Settings (typed `QSettings` wrapper)
- [x] Session manager

## Phase 2 — Molecule editor + RDKit integration (in progress)
- [x] Embedded 2D editor (Ketcher, via `QWebEngineView`/`QWebChannel`, behind an `EditorBackend` interface)
- [x] RDKit integration (`ChemistryEngine`, canonicalization)
- [x] Live property panel (async `DescriptorService`, no manual refresh)
- [x] File import/export (MOL, MOL2, SDF, PDB, XYZ, CML, SMILES, InChI — RDKit first, Open Babel fallback)

## Phase 3 — 3D visualization
- [x] Conformer generation, geometry optimization (`ConformerService`, RDKit ETKDGv3 + MMFF94/UFF)
- [x] 3D viewer (3Dmol.js, via `QWebEngineView`/`QWebChannel`, behind a `ViewerBackend` interface)
- [x] Measurement tools (click two atoms for a distance readout, via `MeasurementService`)

## Phase 4 — Plugin architecture
- [x] Plugin interfaces (`openchem.plugins.interfaces`) — `Plugin`, `DescriptorProvider`,
      `ConformerProvider`, `PanelProvider`, `MenuProvider`, `Importer`, `Exporter`
- [x] Plugin discovery + loader (`PluginManager`, manifest-based metadata, dependency
      topological sort, transactional activate/rollback, decoupled from `MainWindow`
      via the `UIRegistry` protocol)
- [x] Plugin SDK docs (`PLUGIN_SDK.md`, plus a worked example at
      `examples/plugins/hello_plugin/`)
- [x] Hot loading (recursive `QFileSystemWatcher` + debounce, per-plugin enable/disable
      persisted in Settings)

## Phase 5 — AI assistant
- [x] Context-aware chemistry explanations (bundled `plugins/ai_assistant/` plugin,
      multi-provider — Anthropic, OpenAI, local/Ollama, plus a `ClaudeCLIProvider`
      added in Phase 7 for claude.ai subscription users (Pro/Max) with no separate
      Anthropic API key, driving a locally-logged-in `claude` CLI headless (`claude
      -p`, all tools disabled) — via a small `AIProvider` abstraction; context built
      purely from events, same pattern as `PropertyPanel`)
- [x] Workflow assistance via canned, pre-filled prompts ("Explain Selected Molecule",
      "Generate Molecule Report") — user still clicks Send, nothing fires over the
      network on its own
- [x] Documentation generation (the "report" prompt above, over the same chat pipeline)
- [x] Credential storage via a new `context.secrets` namespace (`PluginContext`), backed
      by the OS keychain (`keyring`), namespaced per-plugin
- [x] Constrained tool-calling loop (the assistant requesting safe read operations like
      SMARTS validation itself) — built in Phase 9.6, for `AnthropicProvider`/
      `OpenAICompatibleProvider` only (see there)
- [x] Response streaming — built in Phase 9.6, for `AnthropicProvider`/
      `OpenAICompatibleProvider`; `ClaudeCLIProvider` still shows a complete reply at
      once (its CLI invocation has no incremental-output mode this app uses)

## Phase 6 — Scientific extensions
Five largely independent sub-phases, built and verified in order (6.1-6.5).

- [x] 6.1 — PubChem / ChEMBL search (bundled `plugins/database_search/` plugin,
      `DatabaseSearchProvider` ABC generic over "a chemical database with a REST
      API" — `PubChemProvider`/`ChEMBLProvider` today, room for PDB/DrugBank/
      BindingDB/local later). Search results import as a new molecule via
      `context.molecules.add(...)`.
- [x] 6.2 — Reaction prediction (bundled `plugins/reaction_prediction/` plugin):
      `RDKitTemplateProvider` (deterministic, zero-config, bundled + user-data-dir
      reaction-SMARTS templates) and an optional `RemoteReactionAPIProvider`
      (documented default target: IBM RXN for Chemistry, kept genuinely
      configurable, not hardcoded — its exact request/response contract was not
      verified against a live account).
- [x] 6.3 — Mol*-based macromolecule/crystallography viewer: `MolStarViewerBackend`,
      a second `ViewerBackend` implementation (`src/openchem/ui/viewer_backend.py`)
      added as a sibling to 3Dmol.js's `Mol3DViewerBackend`, not a replacement —
      right tool for large biomolecular/PDB/crystal structures. New
      `MacromoleculeModel` domain type (deliberately not RDKit-Mol-backed) and
      "Import Macromolecule..." action.
- [x] 6.4 — Molecular docking via AutoDock Vina: `DockingProvider` ABC +
      `VinaDockingProvider`, receptor from a `MacromoleculeModel` (6.3), results
      rendered in the Mol* viewer alongside the receptor. Vina itself runs through
      a `VinaEngine` abstraction (`PythonVinaEngine` / `ExecutableVinaEngine`,
      auto-selected) after the `vina` PyPI package turned out to have no
      prebuilt Windows wheel.
- [x] 6.5 — ORCA quantum chemistry integration (single-point energy, geometry
      optimization, opt+freq thermochemistry): `QuantumEngineProvider` ABC +
      `OrcaQuantumEngineProvider`, run via `QuantumChemistryService` — the one
      service in this codebase using `QProcess` on the GUI thread instead of
      `QRunnable`/`QThreadPool`, for real cancellation and live-streamed output.
- [x] Receptor preparation for docking (pH-correct protonation, water/cofactor
      stripping, alternate-location filtering) — built in Phase 9.3. Missing-residue
      repair stays deferred (needs a dedicated structure-repair library).
- [x] A shared `JobManager` across `ConformerService`/`DockingService`/
      `QuantumChemistryService` — built in Phase 9.2, scoped to a registry +
      single-flight guard rather than a full scheduling rewrite (each service
      keeps its own QRunnable/QProcess mechanics; see there for why).
- [x] Per-pose docking interaction analysis (H-bonds/clashes) — built in Phase 9.4.
      Pharmacophore contacts stay deferred (less standardized, meaningfully more
      work).
- [x] Retrofitting `Provenance` onto `ConformerModel`/`DescriptorValue` — built in
      Phase 9.5. `MacromoleculeModel` stays out of scope (imported user data, not a
      provider-computed result).
- [ ] *Deferred, still*: full mmCIF/BinaryCIF/MMTF ingestion — raw mmCIF text
      import into the Mol* viewer already worked before Phase 9; BinaryCIF/MMTF
      (binary formats) have no importer or fetch path driving them yet. Plugin-
      provided reaction templates (a formal `context.reactions.register(...)`-style
      namespace). See ARCHITECTURE.md's design-decisions section.

## Phase 7 — Stabilization (real-world usage fixes)

First hands-on use of the built app (a real installed Vina executable, a
real window on a real screen) surfaced problems Phase 6's scripted/mocked
verification never exercised.

- [x] 7.1 — GUI layout: the six right-side dock panels (Properties, Docking,
      Quantum Chemistry, plus every plugin panel) all landed in the same
      `RightDockWidgetArea` with no tabbing, so they visually overlapped at
      anything less than a very tall window. Now `tabifyDockWidget`'d into
      one tab group. `Settings.window_geometry`/`window_state` (present
      since an earlier phase but never called) are now actually wired to
      `MainWindow.closeEvent`/init, so window size and dock layout persist
      across restarts.
- [x] 7.2 — Empty-state bugs: a brand-new/loaded-empty project now
      auto-creates and selects a blank molecule (previously nothing was
      selected, so the 2D editor's target stayed `None` and every edit was
      silently discarded until the user did File > New Molecule by hand).
      Added `EditorBackend.clear()` so switching to no-molecule/no-structure
      actually empties the canvas instead of leaving a stale drawing behind.
      `DescriptorService` now skips computation entirely for a molecule with
      no structure yet, instead of publishing a permanent "failed" row.
- [x] 7.3 — Real Vina correctness, found via testing against an actual
      installed `vina_1.2.7_win.exe`: receptor PDBQT conversion now passes
      Open Babel's rigid-receptor option (`opt={"r": None}`) — the default
      was emitting `ROOT`/`BRANCH`/`TORSDOF` records as if the whole
      receptor were one flexible ligand. `DockingPanel` now prefers a
      molecule's stored 3D conformer over its raw (possibly 2D, all-zero-z)
      molblock for the ligand, mirroring `QuantumChemistryPanel`'s existing
      pattern.
- [x] 7.4 — External Tools manager (`ExternalToolsDialog`, replacing the
      separate Vina/ORCA "Configure..." dialogs): AutoDock Vina gets a real
      Download/Update button against its public, Apache-2.0-licensed GitHub
      releases, with the exact URL/version/size shown for confirmation
      before anything downloads. ORCA is registration/EULA-gated with no
      public direct-download URL, so it only ever gets a Browse button plus
      a link to the official download page.
- [x] 7.6 — Vina and ORCA verified end-to-end against real installed
      backends (closes issue #2): real docking through `DockingPanel` and
      real single-point/geometry-optimization/opt+freq ORCA runs (with
      correct thermochemistry) through `QuantumChemistryPanel`. Surfaced —
      and fixed — three real bugs no mock/fake engine could have caught:
      `ChemistryEngine.mol_from_molblock` was silently discarding a
      conformer's explicit-hydrogen *positions* on every round-trip
      (RDKit's `removeHs=True` default), `QuantumChemistryPanel` accepted a
      molecule with no 3D conformer at all, and
      `QuantumChemistryService._on_finished` could read a QProcess's output
      before Qt delivered its last buffered chunk. See ARCHITECTURE.md's
      "Known TODOs" for the full detail on each.

## Phase 8 — Interactivity fixes (real-world usage, round 2)

More real usage after Phase 7 landed, surfacing bugs specifically about
things not *responding* to clicks, distinct from Phase 7's layout/backend
issues.

- [x] 8.1 — `DockingPanel`'s receptor/ligand combos and
      `QuantumChemistryPanel`'s molecule combo were only populated when
      `set_project()` ran (project open/new) — a molecule or macromolecule
      added afterward (File > New Molecule, an import, a plugin search
      result, or Phase 7.2's empty-project auto-create) never appeared in
      either dropdown, making them look permanently unusable. `add_molecule`/
      `_import_molecule`/`add_macromolecule` now explicitly refresh both
      panels, the same way they already refreshed the project explorer.
- [x] 8.2 — All three bundled plugins' menu actions ("Explain Selected
      Molecule", "Search Chemical Databases", "Predict Reaction Products")
      only called panel-internal focus/prefill methods, invisible whenever
      that panel was hidden behind another tab in its tabified dock group —
      confirmed live as "clicking the menu item does nothing." Added
      `UIRegistry.reveal_panel()` / `context.panels.reveal()` and wired it
      into all three plugins.
- [x] 8.3 — Small UX fixes found in the same pass: `QuantumChemistryPanel`'s
      "generate a conformer first" message referenced a nonexistent
      "Conformers panel" (it's the 3D Viewer tab's "Generate Conformers..."
      button) — fixed the wording. The AI Assistant's provider Model field
      was a plain text box requiring the exact model id typed from memory —
      now an editable combo box with current per-provider presets.

## Phase 9 — Hardening, gaps, and consolidation

Cleared the deferred backlog logged in Phase 5/6 plus ARCHITECTURE.md's "Known
TODOs" before starting new feature work — correctness gaps first, then
docking/quantum-chemistry hardening, then service consolidation, then the AI
assistant's deferred items. Packaging (`build.ps1`/`build.bat`) stayed
explicitly out of scope.

- [x] 9.1 — Conformer invalidation: `EditStructureCommand`
      (`commands/molecule_commands.py`) now clears a molecule's conformers on
      structure edit (they described the old structure) and restores them on
      undo — previously they silently kept describing a structure that no
      longer existed until the user manually regenerated them. New
      `ConformersInvalidated` event, published alongside the existing
      `ConformersChanged` (whose 3D-viewer listener already handled an empty
      conformer list correctly, so no UI changes were needed there).
- [x] 9.2 — `JobManager` (`services/job_manager.py`): a shared registry +
      single-flight guard for `ConformerService`/`DockingService`/
      `QuantumChemistryService` — deliberately not a scheduling rewrite (each
      service keeps its own `QRunnable`/`QProcess` mechanics untouched).
      Fixed two real duplicate-job bugs this surfaced:
      `MoleculeViewer3DWidget`'s "Generate Conformers..." button had no
      re-entrancy guard, and `QuantumChemistryService.request_calculation`
      wrote `self._active_jobs[molecule_uuid] = job` with no check first, so
      a second call before the first finished silently orphaned the running
      `QProcess`.
- [x] 9.3 — Docking receptor preparation
      (`VinaDockingProvider._convert_receptor_to_pdbqt`): real pH-correct
      protonation, water stripping, and cofactor stripping via Open Babel
      (`receptor_prep_options`, exposed in `DockingPanel`'s new "Receptor
      preparation" group), plus alternate-location filtering
      (`_filter_pdb_altlocs`) — confirmed live that Open Babel's own PDB
      reader does NOT dedupe altlocs on its own (a two-altloc atom came back
      as two full atoms at two positions). Missing-residue repair stays
      deferred (needs a dedicated structure-repair library, a different
      dependency). The mmCIF-format docking bug originally suspected here
      turned out not to exist on investigation — confirmed live that Open
      Babel already registers `"mmcif"` as a receptor format and round-trips
      it correctly; no fix was needed.
- [x] 9.4 — Per-pose docking interaction analysis (`chem/pose_analysis.py`):
      H-bond and steric-clash detection populate `DockingPoseModel.metadata`
      — a heavy-atom-distance heuristic, deliberately not a donor-H...acceptor
      angle check (the receptor has no experimental hydrogen positions to
      compute a real angle from), via Open Babel for receptor atoms
      (format-agnostic across PDB/mmCIF, unlike RDKit's PDB-only
      `MolFromPDBBlock` — confirmed the installed RDKit has no mmCIF block
      reader) and RDKit for the ligand pose. Pharmacophore contacts stay
      deferred — less standardized, meaningfully more work.
- [x] 9.5 — `Provenance` retrofit onto `ConformerModel`/`DescriptorValue`
      (not `MacromoleculeModel` — imported user data, not a
      provider-computed result): populated at construction in
      `RDKitDescriptorProvider.compute()`, `ConformerService`'s
      `_ConformerGenerationTask`, and `OrcaQuantumEngineProvider.parse_output()`
      (one shared `Provenance` instance per ORCA run, so every descriptor/
      conformer it produces carries an identical timestamp).
- [x] 9.6 — AI assistant tool-calling loop + streaming
      (`plugins/ai_assistant/`), scoped to `AnthropicProvider`/
      `OpenAICompatibleProvider` (both SDKs support both natively) —
      `ClaudeCLIProvider` keeps single-shot replies via `AIProvider.stream()`'s
      base-class fallback, not a special case. First tool: `validate_smarts`
      (`ai_assistant/tools.py`), executed locally against a fixed registry,
      never handed to the model directly. `AIAssistantPanel._run_completion`
      runs a bounded (`MAX_TOOL_ITERATIONS = 5`) request/tool-result loop via
      `provider.stream()` for every turn — including intermediate tool-use
      turns, since `stream()` surfaces `tool_calls` exactly like `complete()`
      does.
- [ ] *Deferred, explicitly*: the plugin-system extras
      (`ToolbarProvider`/`ContextMenuProvider`, a `RemoteServicePlugin` base
      class, numeric provider priority, declared permissions) — flagged in
      the code itself as "revisit if a fourth plugin needs the same shape,"
      and still no concrete plugin needs them. BinaryCIF/MMTF import — no
      importer, no fetch path, no driving feature. Plugin-provided
      reaction-template registration. Missing-residue repair for docking
      receptors. Pharmacophore/hydrophobic contact detection for docking
      poses. Nuitka packaging (`build.ps1`/`build.bat`) — out of scope for
      this phase, not needed until an actual release build.

## Naming — resolved, and how

Structure-to-name went through three answers in one day. Recorded because
each one was overturned by measurement, and the record is what makes the
next reassessment cheap.

**STOUT is dead, and has now been REMOVED from the codebase.** The address
compiled into `STOUT-pypi` 2.0.5 returns 404, the whole storage bucket 404s
on a listing, and the upstream repository no longer exists on GitHub. Not
recoverable from here, and re-checked since.

It is gone rather than merely disabled because it is also OBSOLETE: the
vendored nomenclature engine names structures offline, deterministically,
and scores 180/181 on `benchmarks/naming` — where STOUT was a neural model
that produced a fluent, confident name for any input including a wrong one.
Keeping a tab whose only button could never succeed, plus a sidecar
installer for weights that do not exist, cost clarity for no capability.

Deleted: `chem/stout_providers.py`, `chem/stout_runner.py`,
`services/stout_setup.py`, the External Tools tab and its tests. Java STAYS
— OPSIN (name-to-structure) is a Java library and is the surviving consumer.
A cleanup-only entry remains in `services/sidecar_inventory.py` so anyone
who installed the ~1.5 GB environment before the removal can still reclaim
the disk from the Storage tab; it offers no reinstall, because there is
nothing left to install.

**Do not re-add it** unless upstream republishes weights AND it can be shown
to beat the vendored engine on `benchmarks/naming`. The second condition is
the harder one.

**The ML replacement was rejected on evidence.** `SMILES2IUPAC-canonical-base`
scored 71% against the benchmark below — but split by whether PubChem already
had an answer, it was 87/118 where a lookup already worked and **1/6 where it
did not**. It had learned the distribution of known compounds, not the naming
rules, and 1.1 GB of torch to be right one time in six on the only cases that
matter is a bad trade. It also crashed on every stereochemical input.

**What shipped is deterministic.** A vendored Blue Book engine
(`src/openchem/vendor/`, see ARCHITECTURE.md) scores 180/181 with
stereochemistry 11/11, needs nothing beyond RDKit, and runs in ~12 ms.
The stack is PubChem first (exact, curated), then the engine (derived,
verified by OPSIN round-trip), with OPSIN also serving name-to-structure.

`benchmarks/naming/` is the permanent regression check — 181 molecules
scored by round-trip, not string equality, with failures classified so that
"99% correct" cannot hide *which* 1%. Adding an engine means producing a
predictions file and running one command. Do that before believing any
future claim that something is better.

**Still open:** metformin is a `gate_disagreement` (canonical SMILES and
InChIKey disagree over a tautomer, surfaced rather than scored as wrong).
Solvent-dependent and 2D-correlation naming remain out of scope.

## Future extension point — ML Calculator Plugins

Not a phase, not built — a documented starting point so this doesn't get
rediscovered from scratch later. hERG inhibition, CYP inhibition, Ames
mutagenicity, and similar endpoints genuinely need a trained model; no
lightweight rule or SMARTS catalog substitutes for one honestly (see the
calculator-expansion phases' own deferred lists — every attempt at a
verified lightweight hERG/CYP path came up empty, most recently checked
for a redistributable ONNX model with the same result).

The extension point for this already exists, no new core code needed:
`CalculatorRegistry.register()` (`services/calculator_registry.py`)
accepts any `Callable[[Chem.Mol, str, dict], ScientificResult]` — a
plugin (via the existing `plugins/` loader) can register a PyTorch-,
ONNX Runtime-, or other framework-backed calculator today. Model
version, confidence, and applicability domain don't need new fields
either: `Provenance.parameters` (a free `dict[str, Any]`, already carried
on every `ScientificResult`) is where a plugin should report them, e.g.
`Provenance(created_by="my_herg_plugin", method="hergpred-v1.2",
parameters={"confidence": 0.87, "applicability_domain": "in"})`.

### ML NMR shift prediction — trained locally, measured, not adopted

**This section previously read "NO-GO on Windows" and that framing was
wrong.** Windows was the wall the first spike happened to hit; it was
never the binding constraint. Two things have since been established, and
both outrank it.

**First, every pretrained option is licence-blocked, which would have
blocked on Linux too** (verified 2026-08-03):

- `thejonaslab/respredict` — the repository is now a **404**.
- `thejonaslab/fullsspruce-public` — **no licence file of any kind**.
  This document previously recorded it as MIT; that was simply wrong, and
  it is the correction that matters most here. No licence means all
  rights reserved: it cannot be vendored, shipped, or redistributed, on
  any platform.
- `stefhk3/nmr-respredict-docker` — likewise declares no licence, and
  ships only a 13C model.
- Hugging Face carries **no NMR shift model at all** (searched four
  ways).

So WSL and Docker, offered above as the "real routes", would not have
helped. They solve a compiler problem this project did not actually have.

For the record, the Windows finding still stands on its own terms and is
worth keeping: FullSSPrUCe's dependencies pip-install cleanly except
**`tinygraph`** (`thejonaslab/tinygraph`), which has a mandatory C++
Cython extension, no wheel anywhere, a single GitHub release carrying
zero assets, and a `setup.py` passing GCC/Clang flags (`-O3`, `-fPIC`,
`-fno-omit-frame-pointer`, `-g3`) that MSVC rejects — so even with Build
Tools installed it would not build as written. The `tinygraph` on PyPI is
an unrelated project by a different author and would silently supply the
wrong library.

**Second, licensing was sidestepped by training locally, and the trained
model then lost on merit.** Training on the user's own nmrshiftdb2
download, on their own machine, redistributes nothing — the same posture
the shift index already has. That was done: a HistGradientBoostingRegressor
over the lookup's per-sphere statistics plus cheap RDKit atom descriptors,
on the identical held-out split. Held-out MAE, carbon: lookup **2.91**,
model **3.32**, best hybrid **2.91** — a tie. On hydrogen the hybrid gains
0.01 ppm. The full table, four ablations and a paired bootstrap are in
[benchmarks/nmr/README.md](benchmarks/nmr/README.md), and the summary is
in `chem/nmr_database.py`'s docstring beside the lookup's own numbers.

The diagnosis is the useful part: with leakage left in, the model's
optimum is to *copy* the lookup, and it reaches it in 49 of 400
iterations. Every atom descriptor scores at or below 0.01 ppm on
permutation importance. Boosted trees over per-atom descriptors have
nothing to add to a HOSE lookup — the environment code already contains
what they encode.

**What would actually be needed** is a model that learns structure-to-shift
rather than correcting a lookup, i.e. a message-passing GNN — which means
torch (~490 MB) and a training run in a different league from the 59
seconds this took. That is a deliberate decision about the dependency
story, not an incremental step, and it should not be taken on the strength
of this result.

**The cheap fix found alongside it is the one that shipped.** 34.3% of
nmrshiftdb2's records carry explicit hydrogens, and `hose_code` walks
them, so that third spoke a code vocabulary the other two thirds could not
match — and a molecule drawn in this application, having no explicit
hydrogens, could only ever reach the 65.7%. It was a live bug on the query
side too: toluene's methyl read 8.89 ppm from `Chem.AddHs(...)` against a
literature 21.4. Normalising both sides through `heavy_atom_view` (index
format 2) takes held-out carbon from 2.91 to **2.85 ppm**, paired delta
−0.092 with a 95% CI of [−0.122, −0.064], and moves 555 atoms into the
`good` band.

That is roughly five times the ML model's only statistically real effect,
across every atom rather than one band, for a normalisation instead of
130 MB of dependencies — which is the honest summary of this whole
episode.

ONNX Runtime remains worth preferring over a full PyTorch/torch-geometric
chain if a redistributable pretrained model ever appears — lighter, pure
pip, no compiler. Revisit when one exists to point at, not before.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the codebase is structured to
make Phases 3-6 additive rather than requiring a rewrite.
