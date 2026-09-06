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
      stripping, alternate-location filtering) — built in Phase 9.3, plus
      symmetry-copy removal and chain exclusion later.
- [x] **Missing-residue repair: spiked, measured, NOT shipped.** Carried for
      many phases as "the one docking gap, blocked on a dependency". All
      three assumptions were tested and only one held. The dependency is
      trivial now (PDBFixer: 3 packages, 125 MB, cp313 Windows wheels, no
      compiler). The gaps are not near binding sites — zero of 49 curated
      receptors have a chain break within 10 Å of their site, median 30.6 Å,
      and only 3 of 48 have incomplete side chains there. And the repair is
      a template-built prediction: rebuilding 4DAJ's missing side chains and
      comparing 374 atoms against the same residues observed in its sister
      chains gave a median deviation of 2.30 Å, 58% beyond 2.0 Å, worst
      8.9 Å on the LYS/ARG atoms that form salt bridges. Too loose to put
      in a pocket. See `chem/docking_providers.py`'s class docstring.
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
- [x] BinaryCIF ingestion — `chem/binarycif.py` decodes it to mmCIF text at the
      import boundary (all seven encodings), and `chem/structure_io.py` routes
      files by CONTENT rather than extension and transparently gunzips. Decoding
      rather than carrying the binary inward is deliberate: Open Babel, which
      preps every docking receptor, reads neither `bcif` nor `mmtf` (measured),
      so binary would have produced a receptor you could view and not dock.
      Validated against RCSB's own text mmCIF for the same entry — all 21
      `_atom_site` columns across 3,518 rows, from two independent encoders
      (RCSB's `python-mmcif` and Mol*'s `cif2bcif`, the latter exercising
      `FixedPoint`), worst coordinate deviation 0.000000 Å; and the whole
      downstream chain (receptor prep, pose analysis, ligand detection,
      binding-site box) is identical from either source.
- [ ] **MMTF: refused, not deferred.** `mmtf.rcsb.org` no longer resolves
      (`getaddrinfo failed`, in a run where `files.rcsb.org` and
      `models.rcsb.org` both resolved), and the vendored Mol* bundle contains
      zero occurrences of "mmtf" — the viewer dropped it too. An importer would
      read files nobody can obtain and display them in nothing.
- [x] Plugin-provided reaction templates — a formal
      `context.reactions.register([...])` namespace
      (`plugins/context.py`'s `_ReactionTemplateRegistrar`), taking a LIST
      because a reaction-SMARTS library is data that grows and registering
      thirty rules should be one call and one rollback. It also reads:
      the bundled reaction plugin has to APPLY what others registered, so a
      write-only namespace would be unusable by the one plugin that needs
      it. Worked example at `examples/plugins/reaction_templates_plugin/`.

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
      and still no concrete plugin needs them.

      **No longer deferred**, corrected because this list had gone stale:
      hydrophobic/pi-stacking/cation-pi/salt-bridge/metal contact
      detection all shipped (seven interaction types now); contour
      rendering for the 2D NMR correlation plots shipped; every registered
      calculator has options; hERG/CYP/Ames prediction shipped via the
      ADMET sidecar; and packaging is done with PyInstaller, not Nuitka.

      **And it went stale again in the same paragraph.** Plugin-provided
      reaction-template registration was listed here as deferred while
      `context.reactions` was already shipped and tested — a correction
      notice sitting directly above a claim needing the same correction.
      That is the argument for `tests/test_docs_are_current.py`'s
      staleness guard rather than another hand sweep: this list has now
      been corrected by hand twice and drifted both times.

## After Phase 9 — by capability, not by phase

Work past Phase 9 stopped fitting a numbered checklist: it arrived as
several long parallel threads (calculators, NMR, ADMET, naming, docking)
rather than sequential phases. The detailed per-phase record lives in the
plan file; what follows is what EXISTS, grouped by capability, so this
document answers "what does the app do" without being a diary.

### Batch mode and the analytics over it

The app was single-molecule end to end: `ProjectModel.molecules` was
already a list and nothing could act on it as a set. `BatchService` runs
any chosen set of descriptors, alert catalogs and calculators across every
molecule in a project through the existing `JobManager` single-flight
machinery, publishing a partial table as it fills.

**A calculator that reports several numbers becomes several columns.**
Measured when batch mode was built, at 50 registered calculators -- the
registry holds 59 today, so every figure in this paragraph is a snapshot of
that tree rather than a current count. It is left whole rather than
part-updated, because bumping one number in a measurement makes the other
five describe a tree that no longer exists. Of
the 50 registered calculators none returns a scalar; 17 return an
`AlertResult` that is really a report, whose lines (`"Randic index: 9.52"`)
are parsed rather than counted. Measured over the 16 report calculators on
one molecule: **73 numeric columns extracted, 25 lines refused** —
formulas, prose caveats, value lists, and lines carrying two numbers where
neither is obviously the value. The parser is strict because a wrong column
survives being looked at and a missing one does not. Scale: **181 molecules
× 63 columns = 9,780 cells in 1.7 s.**

Cells carry their `Provenance` and their empirical/ab-initio label, so the
labelling the single-molecule views do is not lost in a table of 200 rows.
CSV and Markdown-report export are a **second** path, separate from
`ExportService`'s single-molecule chemical-format export.

Over a finished table: **correlation** (Pearson, Spearman, n, and a ranking
of every column against a chosen one), **PCA chemical space**
(standardised, deterministic, with explained variance and loadings),
**Butina clustering** over Morgan fingerprints, and **per-column
distributions**. Each is checked against an independent implementation
rather than a recorded value — `numpy.corrcoef`, `numpy.polyfit`, a
separate rank transform, an eigendecomposition of the correlation matrix.

The correlation view is a methodological tool, not a chart: it is the
in-app form of the check that overturned this project's hERG result, where
apparent separation turned out to be molecular size at r = +0.98. Measured
on the 181-molecule corpus, molecular weight against Labute surface area
comes out at **r = +0.984** — the same magnitude — so the instrument does
resolve confounds at the scale that matters.

**UMAP and t-SNE were not added.** PCA covers the requirement, needs no
dependency, and gives one picture of a project rather than a different one
per run.

**Virtual screening** (`ScreeningService`) docks N ligands into one
receptor by queueing them through the existing `DockingService` one at a
time — handing it N at once would start N Vina processes — and ranks them.
The queue advances on the terminal job-state event rather than on the
result, so a ligand Vina refuses does not wedge it.

It is **configurable and reproducible** as of 2026-09-06: exhaustiveness,
scoring function, rescore and seed reach the search through
`request_screen(search_options=...)`, from the same
`ui/widgets/search_options.py` controls the Docking panel builds. Before
that a screen ran at whatever the provider defaulted to and could not pin a
seed even in principle -- so the one operation this application offers for
RANKING was the one that was not reproducible, while a single dock was.

Every screen carries a `ScreeningProtocol` recording how it ran, and it
keeps **what was asked** apart from **what the run used**: a requested value
of None means nothing was asked, never that the default was asked for. The
performed engine, version, scoring function and exhaustiveness are filled in
from the provider's own answer, because a stored result naming settings it
did not use is worse than one naming none.

### Calculators

Around 40 registry-executed calculators, all discoverable through
`CalculatorRegistry` and rendered generically by the Property panel from
`CalculatorDefinition` metadata — a new one is a registration, not a UI
change. Physicochemical and medicinal-chemistry scalars, PAINS/BRENK
alerts, per-atom datasets (Crippen contributions, partial charges,
polarizability, Hückel π density, SASA), topology and geometry indices,
elemental analysis, substructure search, structure generators
(stereoisomers, tautomers, resonance, Markush), pH-dependent charge/logD/
microspecies with curve output, vacuum molecular dynamics, and Hückel
orbitals. Every one carries its options; none is unlabelled as to whether
it is measured, empirical or ab initio.

Several things were deliberately NOT shipped after measurement — TSEI,
HLB, Miller polarizability, the π-charge iteration — and that is recorded
in the modules themselves rather than left as silence. The first three
have since shipped, on re-reading their reasons rather than their
verdicts; the fourth was measured against a printed oracle and refused,
which is the outcome that list exists to hold.

### Spectroscopy

NMR via three routes that share one result shape: an offline HOSE-code
database lookup, ORCA ab initio shielding with cached TMS referencing,
and a hybrid that selects per atom on measured expected error. Plus
signal grouping with diastereotopic splitting, 1D peak spectra, and
HSQC/HMBC/COSY correlation with contour rendering. The benchmark
(`benchmarks/nmr/`) is the arbiter and has overturned conclusions twice.

IR from the same `opt_freq` ORCA job that already produced the
thermochemistry — harmonic frequencies, IR intensities, per-mode
stretch/bend/torsion classification, normal-mode animation, and an
imaginary-frequency warning that says the thermochemistry from the same
job is invalid. Benchmarked in `benchmarks/ir/` (MAE 27.6 cm⁻¹ scaled,
fitted factor 0.9666).

#### TD-DFT / UV-Vis — SCOPED AND MEASURED, DELIBERATELY NOT SHIPPED

Timed and checked against experiment on the installed ORCA 6.1.1 build
(B3LYP/def2-SVP, `%tddft nroots 8`), 2026-08-05, while the IR parser work
was fresh. **The cost is trivial. The science is not turnkey, and that is
why this is a note rather than a feature.**

Cost, wall clock on the reference machine — TD-DFT is a small addition on
top of the ground-state optimisation it needs:

| | ground-state Opt | TD-DFT single point |
|---|---|---|
| formaldehyde (4 atoms) | 20 s | **8 s** |
| acetone (10 atoms) | 83 s | **13 s** |
| benzene (12 atoms) | 43 s | **19 s** |

Accuracy is excellent where the transition is a valence n→π\* and poor
where it is not:

| transition | computed | experiment | error |
|---|---|---|---|
| formaldehyde n→π\* | 4.078 eV (304 nm) | 4.07 eV | **+0.01 eV** |
| acetone n→π\* | 4.444 eV (279 nm) | ~4.48 eV | **−0.04 eV** |
| benzene ¹B₂ᵤ | 5.494 eV (226 nm) | 4.90 eV (253 nm) | **+0.59 eV** |

Both carbonyl n→π\* bands also came back with essentially zero oscillator
strength, which is correct — they are symmetry-forbidden — so the
intensity column is being read right as well.

Benzene is the reason this is not shipped. The error is more than half an
electron-volt, and the spectrum a user would be shown has its strongest
band missing from the first 8 roots. Shipping that would mean shipping a
UV-Vis feature whose default settings are wrong for aromatics, which is
most of medicinal chemistry.

##### The diffuse-basis retry — run, and it does NOT rescue this

The paragraph above used to continue "**def2-SVP has no diffuse functions,
so the π→π\* and Rydberg states are misplaced**", naming that as the cause
of the missing band. **That diagnosis was wrong**, and re-running it is what
showed so. Measured 2026-08-05 on the same optimised geometries, B3LYP,
`%tddft nroots 15`:

| | ¹B₂ᵤ (exp 4.90, f≈0) | ¹B₁ᵤ (exp 6.20, f≈0) | strongest band (exp ¹E₁ᵤ 6.94, f≈0.9) |
|---|---|---|---|
| def2-SVP | 5.49 | 6.47 | **7.918 eV, f = 0.9607** |
| def2-SVPD | 5.40 | 6.31 | **7.430 eV, f = 0.0832** |

**The ¹E₁ᵤ band was never missing because of the basis set. It was missing
because `nroots 8` was too few.** At def2-SVP with 15 roots it is right
there, at 7.918 eV carrying f = 0.9607.

**THAT NUMBER WAS COMPARED AGAINST A SINGLE COMPONENT, and the sentence
here used to read "against an experimental ≈0.9 — the intensity is
essentially correct and always was."** ¹E₁ᵤ is **doubly degenerate** and
ORCA reports each component as its own root: 0.9606 and 0.9607, summing to
**1.9212**. An experimental oscillator strength integrates ONE absorption
band and degenerate components cannot be separated in that integral, so the
comparable computed quantity is the sum.

**SOURCED, AND THE ORIGINAL NUMBER WAS RIGHT.** The ≈0.9 had no citation
anywhere in this repository, and a web summary attributed **1.25** to the
CASPT2 benzene study — a figure that would have flipped the verdict. That
paper does not contain it: Lorentzon, Malmqvist, Fülscher and Roos
(*Theor. Chim. Acta* **91** (1995) 91–108, doi:10.1007/BF01113865) say the
experimental values are "scattered in the range 0.6–1.05", give their own
graphical integration as 0.80, and note that the 0.80 includes the A₂ᵤ
Rydberg band. Bolovinos et al. (*J. Mol. Spectrosc.* **103** (1984)
240–256, doi:10.1016/0022-2852(84)90051-1) then supply the direct absolute
measurement: **f = 0.90** at ε_max 6.96 eV.

So the ≈0.9 was correct all along and is now cited, and comparing a single
component against it was the error. TD-DFT overestimates this band by
**2.13–2.23×** across the three arms.

**The relative conclusions in this section are unaffected**, because every
arm was measured the same way: the def2-SVPD collapse below is still an
order of magnitude, per component or summed. What was wrong was the
absolute "essentially correct" claim, which rested on mixing conventions.
`score.py` prints components and their sum side by side so the two can
never be silently mixed again.

Diffuse functions do improve every *position*: ¹B₂ᵤ +0.59 → +0.50 eV, ¹B₁ᵤ
+0.27 → +0.11, and the allowed band +0.98 → +0.49. **And they destroy the
intensity**, collapsing f from 0.96 to 0.083, an order of magnitude too
weak. This is the textbook diffuse-basis failure: the added functions
introduce low-lying Rydberg states that mix with the valence π→π\* and
fragment its oscillator strength across several near-degenerate roots.

So the trade is a halved energy error for a tenfold intensity error, and
for a UV-Vis spectrum that is the wrong way round — the question a spectrum
answers is *which band is strongest*, and def2-SVPD gets that wrong while
def2-SVP gets it right. Acetone's n→π\* is unmoved by the change (4.45 vs
4.44 eV, f≈0 in both), so nothing is gained there either.

**The refusal therefore stands, but the reason has changed.** It is not
"the basis set is inadequate"; it is that the two error modes cannot be
minimised by the same basis, so any shipped default is wrong for one of
them, and picking per molecule is exactly the expertise a turnkey feature
is supposed to remove. Raising `nroots` is free and correct and should be
part of whatever ships — but on its own it fixes only the band's presence,
not the +0.98 eV where def2-SVP puts it.

One more thing measured rather than assumed: **`! ... Opt` together with a
`%tddft` block does not run "optimise then compute the spectrum".** It
requests an EXCITED-STATE geometry optimisation, which needs the third
functional derivative of B88 and which this ORCA build refuses with
"not available natively with ORCA. Please, use the LibXC version." The
ground-state optimisation and the TD-DFT single point have to be two
jobs.

What shipping this would actually need: basis-set guidance per transition
type — **not** "a default with diffuse functions", which this line used to
suggest and which the retry above measured and ruled out — a root count
chosen from the molecule rather than fixed at 8, and a benchmark of its
own against experimental λ_max the way `benchmarks/ir/` was done. A
functional better suited to charge-transfer and π→π\* states (a
range-separated hybrid such as ωB97X-D) is the more promising lead than
any basis change.
None of that is blocked — the `SpectrumResult` family was shaped so a
`UvVisSpectrumResult` is an addition rather than a refactor, which is
precisely what makes deferring it safe.

##### ωB97X-D3 HAS NOW BEEN TRIED, AND IT MOVES BENZENE THE WRONG WAY

**The functional actually run is ωB97X-D3, not ωB97X-D.** The ORCA header is `wB97X-D3` and ORCA reports applying `WB97X-D3` with range separation μ = 0.25 and an atom-pairwise dispersion correction. The two differ in their dispersion treatment and are not the same functional; this section said "ωB97X-D" for a while and was wrong. The conclusion is unaffected — the blue shift is a property of range separation, which both share — but the label has to match what ran.

The line above used to end "and has not been tried". It has been, on
ORCA 6.1.1 with pre-registered acceptance criteria, and the full method,
table and two open questions are in
[benchmarks/uvvis/README.md](../benchmarks/uvvis/README.md). The refusal
stands and the reason is now measured rather than predicted.

A range-separated hybrid blue-shifts valence π→π\* **further**, which is
the opposite of what was wanted. Errors against experiment:

| benzene band | B3LYP/SVP | ωB97X-D3/SVP | ωB97X-D3/SVPD |
|---|---|---|---|
| ¹B₂ᵤ 4.90 | +0.59 | **+0.73** | +0.64 |
| ¹B₁ᵤ 6.20 | +0.27 | **+0.40** | +0.26 |
| ¹E₁ᵤ 6.94 | +0.98 | **+1.10** | +0.84 |

The carbonyls were never the problem and stay excellent everywhere —
formaldehyde and acetone land within 0.05 eV in all three arms, both
correctly dark.

**The one genuinely new finding is that ωB97X-D3 fixes what diffuse
functions broke.** The recorded intensity collapse at def2-SVPD — *f*
0.96 → 0.083, Rydberg states fragmenting the valence π→π\* — is a
**B3LYP** failure, not a basis-set one. With ωB97X-D3/def2-SVPD the
oscillator strength survives at 0.993 per component and the strongest
band is still identified correctly, at the cost of a worse position
(+0.84 against B3LYP/def2-SVPD's +0.49). So the two error modes still
cannot be minimised by one setting, which is the existing conclusion —
now confirmed against the functional that was supposed to resolve it
rather than only against basis sets.

###### TRIPLE ZETA HELPS SUBSTANTIALLY, AND STILL DOES NOT REACH IT

Everything above is **double-zeta**. The untried axis was valence basis
QUALITY rather than diffuseness, and it turns out to carry a large part of
the error — just not all of it. Measured on the same shared geometries at
`nroots 30`:

| benzene band | B3LYP/SVP | B3LYP/TZVP | B3LYP/TZVPD |
|---|---|---|---|
| ¹B₂ᵤ 4.90 | +0.59 | +0.50 | **+0.48** |
| ¹B₁ᵤ 6.20 | +0.27 | +0.08 | **+0.04** |
| ¹E₁ᵤ 6.94 | +0.98 | +0.66 | **+0.57** |

¹B₁ᵤ was almost entirely basis-limited (+0.27 → +0.04), and pyridine's
analogue behaves the same way (+0.32 → +0.10). But the best arm still fails
benzene's ¹B₂ᵤ at +0.48 and ¹E₁ᵤ at +0.57 against a 0.30 eV criterion.
**Six arms, no candidate.** The carbonyls stay excellent everywhere and
strongest-band identity passes everywhere; it is valence π→π\* in aromatics,
and only that, at every basis tried.

**The ωB97X-D3 conclusion is not a basis artefact**, which needed checking
because it was drawn at def2-SVP alone. At def2-TZVP it is +0.80 against
B3LYP's +0.66 — a 0.14 eV gap where SVP gave 0.12. The range-separated
hybrid really does blue-shift valence π→π\* further, independently of basis.

**A single fitted scaling factor cannot rescue it either**, and that needed
no new run: the carbonyls need a factor of 1.00 and the aromatics 0.88, so
the best single factor leaves 3 of 9 bands outside tolerance *and breaks the
carbonyls that were already right*. `benchmarks/ir/`'s approach does not
transfer.

So the refusal now rests on the basis axis being tested rather than assumed,
and what remains open is whether a wavefunction method reaches it at all —
`benchmarks/uvvis/README.md` carries the full tables.

**A benchmark exists for this now**, which is the durable part:
`benchmarks/uvvis/` is scoreable and runnable, with a B3LYP control that
reproduces this document's own recorded figures to four decimals, and an
identification rule that refuses to score a transition it cannot locate
rather than taking the nearest root — the direct guard against the
`nroots 8` failure recorded above.

### ADMET

hERG, CYP and Ames prediction through an out-of-process ADMET-AI sidecar,
alongside the rule-based hERG risk-factor checklist that needs no
sidecar. Benchmarked rather than assumed: hERG's apparent separation
turned out to be molecular size (r = +0.98), CYP survived the same check
and is genuinely isoform-specific, Ames is cleanest and ties the free
structural-alert alternative while failing on different compounds.

### Structure handling and docking correctness

A curated 49-receptor library with binding-site boxes validated by
redocking; BinaryCIF and gzip ingestion; chain/residue/sequence
summaries; deposited biological-assembly annotation; chain exclusion; and
a guard refusing a search box that contains no receptor. See
ARCHITECTURE.md's structure-file pipeline section for the invariant these
share and the five bugs that motivated it — the most serious being Open
Babel's silent unit-cell expansion, which handed Vina eight overlapping
copies of one protein.

### Ranking affinities — the gap is measured, and three routes are open

**Route 1 is SHIPPED, route 2's AXIS is shipped, and route 3 has been
spiked but ships nothing.** Route 3 was gated on route 1 existing and no
longer is. All three are written down because the 2026-08-31 docking work
turned "the docking has a lot to be desired" into a specific, sourced
statement about *which* ability is weak, and they differ by two orders of
magnitude in cost.

    1  an interval, not a number    SHIPPED
    2  rescore with a second
       function                     the AXIS is shipped; the ranking-power
                                    benchmark is unmeasurable here, see below
    3  relative binding free
       energy                       SPIKED. `git diff src/` is empty for all
                                    of it. The pipeline runs on both
                                    platforms and its acceptance test
                                    reproduces the reference under WSL;
                                    Windows runs a DIFFERENT force field and
                                    so cannot be checked against that column
                                    at all

**THE GAP, MEASURED RATHER THAN ASSERTED.** CASF-2016 evaluates four
separate abilities and puts Vina on opposite sides of two of them
([source:su2019]): strong at **docking power** (right pose, success "close
to 90%") and among the *"not-so-good scoring functions in the
scoring/ranking power tests"*. Measured locally on 5C1M at exhaustiveness
25, which is the same finding arriving as a number:

    one molecule, three seeds       -8.79 / -8.79 / -8.73   spread 0.06
    three different analogues       -8.88 / -8.79 / -8.75   spread 0.13

The difference between three different molecules was about **twice** what
one molecule shows against nothing but a seed change. Nothing about pose
quality touches that — it is the scoring function, which is why
[source:agboola2026] found doubling exhaustiveness left *"six of eight gross
misplacements unresolved"* and why more search effort is not on this list.

**AND THE CEILING IS LOW EVEN IF ALL OF THIS IS BUILT.** [source:su2019]:
*"even the top-ranked scoring functions (except for ΔVinaRF20) produce only
modest correlation coefficients around 0.6"*. Three analogues differing by
one CH2 are below what any of these methods resolves. Route 1 is the only
one that helps with *that* case; routes 2 and 3 help with wider series.

#### 1. Report an interval, not a number — SHIPPED

**THE HEADING KEEPS ITS ORIGINAL WORDING AND THE SHIPPED NAME DIFFERS.** What
is computed is the sample RANGE of the runs performed, and every user-facing
string says "range" — "interval" invites the confidence-interval reading the
feature exists to prevent, so the domain type is `AffinityRange` in
`domain/affinity_range.py`. This heading is left as it was written, as the
record of what was asked for.

The pose table showed `-8.88` as though it were a measurement. It is one draw
from a distribution whose width is now known.

**What shipped**

    Docking panel      a Replicates control (1..25, default 1) and a label
                       reading "Score range over 3 runs: -8.85 to -8.73
                       (median -8.79). Poses are from the median run
                       (seed 1990277, protocol seed 4712)."
    the run itself     `_DockingTask` loops N times; the poses kept are the
                       MEDIAN replicate's, and every run's seed and best
                       affinity are stored
    virtual screening  the same control, and a DOMINANCE RANK where ligands
                       whose ranges overlap share a rank
    the refusal        `compare()` returns SEPARATED / NOT_SEPARATED /
                       NOT_ASSESSED, and NOT_ASSESSED is what a
                       single-replicate screen gets for every pair

**Three answers this design reached and then had to reverse**, recorded
because each reads as reasonable and will be re-proposed:

- **"Mean ± spread" is the wrong summary, and this document asked for it.**
  The sentence above originally read "running N seeds and reporting a mean
  with its spread". A per-replicate best is a minimum over Vina's own internal
  runs *and* over the poses of each — skewed and extreme-value-shaped — so a
  mean with a standard deviation invites a Gaussian reading of a min
  statistic. It ships as **range + median + n**. The rank-based refusal is
  unaffected because it is distribution-free, which is why it is the rule.
- **The representative replicate is the MEDIAN, not the best.** Best-of-N is a
  max selection, so the headline affinity would drift more negative purely as
  the replicate count rose — the reported number becoming a function of how
  many times it was run, which is this feature's own harm reintroduced in the
  first number a reader sees.
- **The p-value is two-sided, so the minimum useful count is 4, not 3.**
  `1/comb(2n,n)` is the one-sided rate and holds only when the direction is
  fixed in advance; the panel reports an ordering in either direction. At 3
  runs each the real rate is 0.100, not 0.050.

**The default is 1, and the harm is still fixed at zero runtime cost.**
Anything higher would multiply every existing user's wall clock and every
screening budget with no announcement. At N = 1 the fix is behavioural: the
panel prints "1 run (seed …) — no spread measured" instead of a bare `-8.88`,
and a screening table stops numbering an ordering it cannot support.

**Acceptance was met, and the acceptance criterion is worth re-reading**: the
spread is measured and never assumed, and the shipped gate takes two replicate
COUNTS and nothing else — so there is no threshold in kcal/mol for anyone to
tune. `test_no_kcal_literal_lives_in_the_module` fails if one appears under
any name, and `test_the_decision_is_invariant_under_positive_scaling` fails
behaviourally if one is smuggled in as arithmetic.

`benchmarks/docking/seed_spread.py` characterises the rule against real Vina
and states in its own docstring that it must NOT be read as supplying a
threshold.

    cost         N x runtime; 5 seeds at exhaustiveness 25 is ~2 minutes
    dependency   none -- the seed is already settable and recorded
    risk         low; it changes presentation, not chemistry

**Acceptance: the reported spread must be MEASURED, never assumed.** A
hardcoded "±0.06" would be this project's own recorded failure — a constant
fitted to one molecule on one receptor, presented as a property of the
method. It must come from the runs actually performed, and the count must be
visible, because a spread over 3 seeds and over 30 says different things.

The natural shape is the refusal work's: when the spread across two ligands
overlaps, the panel should decline to imply an ordering rather than printing
one and hoping the user reads the caveat.

#### 2. Rescore the pose with a different function — THE AXIS IS SHIPPED

Docking power is already good, so the pose is worth keeping; what needs
replacing is the number attached to it. A rescoring provider slots in after
the search, consuming the PDBQT that already exists.

**What shipped**

    domain           `PoseScore` — function, protocol, value, units, engine,
                     and the sha256 of BOTH files it scored
    the interface    `PoseRescorer` + `RescoreRequest` in
                     `plugins/interfaces.py`, carrying the ORIGINALS beside
                     the prepared PDBQTs so a non-AutoDock rescorer is not
                     locked out
    the first one    `chem/rescoring.py`'s `VinaPoseRescorer` — Vinardo (or
                     Vina) through `--score_only`, needing NO new install
    the UI           a "Rescore with:" combo defaulting to Off, a column
                     hidden until one is requested, and the scale warning
                     printed under the table rather than left in a tooltip

**Vinardo first rather than X-Score, and that was a de-risking choice**: the
Vina 1.2.7 binary already installed supports `--score_only`, `--local_only`
and `--scoring vinardo`, so the whole axis could be built and proved before
anything had to be registered for or compiled.

**FOUR THINGS MEASURED WHILE BUILDING IT**, each of which would have shipped
a wrong number:

- **`--local_only`'s output PDBQT lies about which function ran.** Its
  `REMARK VINA RESULT` is a passthrough of the INPUT pose's value — measured
  identical (-8.758) under two functions whose stdout answers were 3.2
  kcal/mol apart. Both modes are read from stdout; see
  `chem/vina_engine.py`'s `parse_vina_score_output`.
- **Vina refuses a `MODEL`-wrapped single-pose ligand**, which is exactly the
  wrapper `_raw_pose_to_model` adds for Open Babel. Two consumers of one
  pose, opposite requirements.
- **Rescoring with `vina` reproduces the dock's affinity for the TOP POSE
  ONLY.** A docking run uses one shared unbound reference for every pose it
  reports (measured -0.861, spread 0.013 over five poses, equal to pose 0's
  own internal energy) while `--score_only` uses each pose's own. The
  difference is `(U − intra_i)/D`, reproduced to a worst residual of 0.005
  kcal/mol. So even the SAME function is not on the same reference — a third
  reason the two columns must not be compared.
- **Vina's built-in vinardo IS the published one.** Table 1's weights
  (-0.045, 0.000, 0.800, -0.035, -0.600) match `--weight_vinardo_*` exactly.
  The radii are not exposed by the CLI and stay unverified from outside.

**Still not measured, and the column says so:** whether Vinardo ranks better.
Driven live on 5C1M, the two functions disagreed about which pose was best —
Vina's top pose rescored worst of the first three. Nothing re-ranks on it.

**RANKING POWER IS MEASURED NOW, AND THE ANSWER IS A NULL.** The section below
survives as the record of what was closed and why; its conclusion — that this
is unmeasurable here — was overturned on 2026-09-05 by the route the paragraph
after it names. **ChEMBL is reachable with no account**, and it carries
`assay_chembl_id`, which is the one thing `rcsb_binding_affinity` lacked: a
series confined to a single assay is a real ordering where a 4000-fold
cross-assay spread is not.

**The full record is `docs/DOCKING_RANKING_BENCHMARK.md`**, including the
per-series table for all 56 series; the raw JSONL is gitignored.

`benchmarks/docking/chembl_corpus.py` builds it — 1586 single-assay series
over eight catalogued receptors from 41,073 activities — and
`rank_power.py` / `rank_report.py` measure it. **Fifty-six series, 624
ligands, 3828 real Vina searches, 14.5 hours of search time**:

    median rho(-vina, pChEMBL)      +0.082   95% series bootstrap [-0.030, +0.245]
    series with rho > 0             32/56    sign test p = 0.350, two-sided
    median rho(Vinardo) - rho(Vina) +0.000   95% [-0.104, +0.082]
    beating every trivial baseline   9/56
    above TWICE its own random floor 1/56
    SEARCH REPEATABILITY            median +0.990, 55/56 at or above +0.95
                                    60 of 3462 ligand pairs swapped (1.7%)

**The repeatability row is where the information is.** The search orders these
ligands almost identically across independent replicate halves — 1.7% of pairs
swap — so the disagreement with measured potency is **not sampling**, and more
exhaustiveness cannot address it. It is the scoring function, which is
[source:su2019]'s finding arriving as a local measurement instead of a
citation. That is **N5** on this section's own list of nulls: reproducible
search, and the score still does not order.

Vinardo does not improve on it — the delta's median is exactly +0.000 and 27 of
56 is a coin (**N2**). And **47 of 56 series are ordered at least as well by a
trivial physicochemical descriptor as by docking**, which is **N1**, the
outcome this section calls the most valuable, at 84%.

**THE INTERIM P-VALUES CROSSED 0.05 AND CAME BACK.** 15 series p = 0.118, 28
series 0.087, 37 series **0.047**, 56 series **0.350**. A p-value inspected
repeatedly as data accumulates is not a p-value; the pre-committed endpoint was
the whole frozen selection and that is the row above. `rank_report.py` prints a
PARTIAL banner short of it.

**Stated as narrowly as the data allows**: this is *no ranking ability
detectable across within-assay congeneric series at this n*, on eight targets,
with Vina at exhaustiveness 25 — not *docking cannot rank*. Two series reach
+0.75 and +0.79. The oracle's own reproducibility is unmeasurable, since ChEMBL
carries no per-row uncertainty, so rho is bounded above by a quantity nobody
can measure while the docking's own repeatability is measured and is
essentially 1.

**WHAT THIS CLOSES FOR ROUTE 3.** RBFE was to be justified by docking's ranking
being inadequate. It is now measured as inadequate rather than assumed to be,
and the same corpus is the acceptance oracle a free-energy method would have to
beat — the benchmark outlives the null it produced.

**THE HISTORICAL RECORD BELOW IS SUPERSEDED AND KEPT.** It says ranking power
is unmeasurable here, which was true of every route it surveyed and false of
the one it did not — ChEMBL's `assay_chembl_id`. Kept rather than deleted
because the WAY it was wrong is the durable part: it enumerated the closed
doors carefully and read that as a closed question.
`benchmarks/docking/rescore_power.py`.

Route 2's acceptance criterion needs measured affinities. Measured
2026-09-03, every route to a set carrying them is closed from here: the
PDBbind hosts do not connect or 403, including the plain-`wget` CASF-2016
tarball URL that published evaluations still use; PDBbind+ is a JavaScript
app behind an account; Binding MOAD's domain now serves a commercial antibody
catalogue; Zenodo and figshare carry only other people's preprocessed
derivatives. RCSB's own `rcsb_binding_affinity` is present but sparse and
assay-heterogeneous — zero records for 1HSG, 3EML and 2RH1, and 104 for 4EY7
spanning Kd 8 nM to IC50 7120 nM for ONE ligand. **A 4000-fold spread across
assays is not a ranking oracle.**

So the split that shipped is not the 2A/2B this section first planned. What
IS measurable needs no external data at all, because every catalogued
receptor is deposited with its own ligand:

    MEASURED      docking power -- CASF's own protocol, crystal pose as truth
    MEASURED      how much the rescore REORDERS the same poses, no oracle
    NOT MEASURED  ranking power -- one ligand against another

**And the docking-power arm is a NULL RESULT, which ships.**
[source:quiroga2016] reports Vinardo improving docking on the authors' data;
across eight receptors it changes nothing detectable here — 6/8 within 3 Å
either way, mean displacement 1.45 against 1.46 Å. Eight targets cannot
separate functions differing by less than about one target, so that is "no
difference visible at this n", not equivalence.

**The ceiling row is where the information is:** the search found a pose
within 3 Å on 8 of 8, so both misses are SCORING failures rather than search
failures. 3EML's search reached 2.50 Å while the two scores picked 3.77 and
4.22; 8EF5's reached 0.52 Å while both picked ~4.4.

The reordering arm is what the shipped UI's refusal rests on: Spearman
between the two orderings of the same poses is mean +0.71, range +0.07 to
+1.00. On 3EML and 1HSG they order the poses almost independently.

Leakage is recorded as `TRAINING_PROVENANCE_UNRESOLVED`, three-valued rather
than clean/contaminated: [source:quiroga2016] §3.1 names Vinardo's selection
set (122 of the 195 PDBbind Core 2013 structures) and Vina was trained on
PDBbind 2007, and neither list is obtainable from here for the same reason
CASF-2016 is not. The overlap is unknown, not absent.

**What would reopen ranking power**, in preference order: a CASF-2016 copy
obtained through a PDBbind+ account; or a curated affinity set assembled from
BindingDB/ChEMBL for targets already in the library, which is its own branch
with its own curation decisions and its own leakage analysis, and whose
numbers would not be comparable to any published table.

**CORRECTION, 2026-09-03: X-Score IS NO LONGER THE CANDIDATE, and the
paragraph below is kept because its reasoning about ΔVinaRF20 still
stands.** Two facts found while shipping the axis moved it. First,
[source:quiroga2016] §1: *"Vina uses an empirical scoring function which is
inspired by the X-score function"* — so X-Score is Vina's own ancestor and a
weaker independent second opinion than assumed here. Second, obtainability:
its public release is v1.2, ANSI C++ "tested on UNIX and LINUX", behind a
licence agreement, a registration and a server login.

**[source:neudert2011]'s DSX replaces it**: knowledge-based rather than
Vina-derived, its abstract reports *"superior performance with respect to
docking- and ranking power"*, and it states it is *"freely available to the
scientific community"*. Whether agklebe.de still serves it in 2026 is a
spike, not a claim. [source:koes2013]'s smina lands before either, being both
an engine and a rescorer and therefore the arm that tests whether
`PoseRescorer` is an abstraction; [source:mcnutt2021] (GNINA) and
[source:ballester2010] (RF-Score) are registered as later candidates, the
first with the note that its published gain is docking power rather than
ranking.

**X-Score was the candidate to start with**, not the benchmark leader.
CASF-2016's leader is **ΔVinaRF20**, a random-forest correction on top of
Vina — and the paper flags its own problem: it was *"calibrated on over 3300
protein−ligand complexes selected from the PDBbind"*, the authors
*"speculate that this overlap contributes to [its] outstanding
performance"*, and its results *"should be interpreted with care"*. That is
a training/test leakage warning from the benchmark's own authors, and this
project has already been bitten once by exactly that class (ESOL inside
AqSolDB). X-Score also beats Vina at ranking, is not an ML model, and raises
no such question.

    cost         a provider plus an external binary, in the shape
                 `DockingProvider` and `VinaEngine` already have
    dependency   external, user-installed, same treatment as Vina and ORCA
    risk         moderate -- a second score on a different scale, which is
                 the "one name, two quantities" trap this project has
                 recorded four times. It must be labelled and stored, never
                 mixed into one ranking.

**Acceptance: its own benchmark, and the leakage question asked first.**
Rank correlation against measured affinities on a set whose overlap with the
rescorer's training data has been checked — not assumed absent. The
redocking harness is the model: a number nobody can reproduce is not
evidence, and `benchmarks/docking/` already has the shape.

#### 3. Relative binding free energy — the correct tool, and the expensive one

For a congeneric series — same scaffold, one substituent differing — the
method designed for the question is relative binding free energy (FEP or
thermodynamic integration), not docking. It is what would actually rank
three fentanyl analogues.

    cost         hours of GPU per ligand PAIR, plus setup that is itself
                 a skill: parameterisation, solvation, equilibration,
                 lambda scheduling, convergence checking
    dependency   OpenMM, which this project has already measured as
                 installable -- 8.5.2 publishes cp313 Windows wheels, no
                 compiler and no conda (recorded in the missing-residue
                 spike)
    risk         high, and mostly of the silent kind: an unconverged
                 FEP returns a confident number

**Acceptance is the hard part and is why this is third.** A wrong FEP looks
exactly like a right one, so it needs convergence diagnostics reported
rather than a bare ΔΔG, and a published congeneric series reproduced before
any answer of ours is believed. **Do not start this before route 1 exists**:
without a measured spread there is nothing to judge whether an FEP number is
an improvement on the docking score it replaces.

**SPIKED, AND THE PREDICTION ABOVE WAS EXACTLY RIGHT -- FOR THE WRONG
REASON.** `benchmarks/free_energy/` builds hydration free energies with
OpenMM and openmmtools and checks them against FreeSolv's published column.
Its first run failed that check on 3 of 5 compounds while **every leg
reported itself converged**, which is the "a wrong FEP looks exactly like a
right one" risk arriving on schedule. The cause was not convergence at all:
the run used the newest installed GAFF while the reference column is GAFF1,
and nothing in the stored result recorded which. So the diagnostics were
correct and the comparison was not, and no amount of convergence checking
could have found it -- only the external oracle did. Pinned and recorded
now, the acceptance test reproduces.

Measured feasibility, since the estimate above was a guess: **251 ns/day**
on Windows OpenCL and 266 on WSL CUDA for a 27k-atom system, putting an
RBFE pair at 5-12 hours and confirming the cost line. `git diff src/` is
empty for the whole spike.

#### What is deliberately NOT on this list

- **More exhaustiveness.** Measured: it is the scoring function, not the
  sampling. [source:agarwal2022] finds convergence at 25 and
  [source:agboola2026] finds doubling it does not rescue misplacement.
- **Consensus scoring.** CASF-2016 reports limited gains, and averaging
  functions on different scales is the "one name, two quantities" trap
  wearing a statistical hat.
- **A general ML affinity predictor trained on PDBbind.** The
  similarity-bias literature is damning and CASF-2016's own reference list
  cites two papers on it. This project's rule — ask leakage of every model —
  applies before any such thing is fitted, not after.

### Visualization

Per-atom colouring on 2D and 3D from one shared `ColorScale`; molecular
surfaces (vdW/SAS/MS/SES); surfaces coloured by a continuous scalar field
(point-charge electrostatic potential, verified by correlating rendered
vertex colours against the supplied field, r = −0.96); a continuous 2D
property heat map; residue colouring driven by real docking interaction
data; and structure grids for multi-structure results.

### Explaining itself

Every interactive control carries a declared *help contract* — what it
means, at what tier of care, and the source behind any external claim — of
which the tooltip is one rendering. The guard checks the STRUCTURE of that
declaration and never the prose, because a check for "has a non-empty
string" degenerates into `tooltip = "Options."`, and it is guarded from
both sides: a contract may not be a degenerate string, and a well-formed
but uninformative one must be accepted rather than graded.

**Complete: 355 of 355 controls, 219 distinct concepts, 53 of them
interpretation-sensitive.** The staged-migration fixtures are deleted and
the invariant is now a single assertion, so a control added without a
contract is a failing test rather than an entry in a backlog.
`tools/list_tooltips.py --help-id <id> --context` prints the authoring
brief for one control: its label, tier, docs anchor, source provenance and
the standing prohibitions.

### Naming, and the annotation engine underneath it

Structure-to-name offline and deterministically via the vendored IUPAC
engine, plus PubChem lookup and OPSIN parsing, each result labelled with
its source and exactness. See the section below — this one was overturned
three times in a day.

The engine also works out ring systems, functional groups, stereocentres
and atom numbering on the way to a name, and all of that used to be
discarded with the tree. `chem/structure_annotation.py` keeps it: four
registered calculators colour those onto the 2D and 3D depictions,
`name_fragment()` names a selected substructure as a substituent, and
`name_derivation()` returns the parse tree a name was built from. An
`explain_naming` tool hands the AI assistant that record so "why is this
carbon numbered 4?" is answered from the engine rather than from
recollection.

Coverage was measured BEFORE any of it was built on, and the numbers
decided the build order: ring systems reach 45.3% of heavy atoms and
functional groups 19.7%, both on every molecule, while IUPAC locants reach
34.8% and **76 of 181 corpus molecules get none at all** — a retained name
carries no derived numbering. The three that work everywhere shipped
first, and the locant view states its coverage rather than rendering a
blank.

### Regulatory intelligence

Which frameworks have something to say about a structure — deliberately
NOT whether it is legal. `chem/regulatory/` holds a rule language, a
screening engine, an OPSIN-backed build step and the rulesets it produces.

The shape worth knowing: a rule separates the regulation's **verbatim
text** from our **machine reading** of it, carrying the assumptions made
and limitations accepted, because clauses like "except", "other than" and
"and its salts, isomers, and salts of isomers" become implementation
decisions the moment they are turned into a pattern. Confidence is capped
mechanically by whether the quote is present, so a rule cannot claim to be
verified against a statute nobody pasted.

Ships all three CWC schedules and the US DEA listed chemicals — 91 rules
over 96 entries, the five unencoded ones named below. Every other domain —
controlled substances, export controls, transport, occupational,
environmental and the rest — registers EMPTY and says so in the coverage
report, because an absent domain is invisible and reads as "nothing
applies". **Ten of the twelve domains are still empty.** Adding one is a
JSON file and a build run, not a code change.

| ruleset | domain | entries | encoded | shape |
|---|---|---|---|---|
| CWC Schedule 1 | chemical weapons | 16 | 14 | structural families, four precursors, the 2019 additions |
| CWC Schedule 2 | chemical weapons | 14 | 14 | eight identities, six generic families, three exemptions |
| CWC Schedule 3 | chemical weapons | 17 | 16 | identities and precursors, all industrial chemicals |
| 21 CFR 1310.02 | drug precursors | 49 | 47 | identities, two salts by expression |

**An identity comes from the CAS the statute prints, never from the
chemical's name.** Measured over Schedule 2 and 3's 27 named chemicals:
the statute's CAS resolved for all 27, a name resolver agreed with it for
26, and asking only "does the name resolve" would have shipped two wrong
structures — sulfur monochloride (both resolvers give a one-chlorine
species where the entry lists Cl2S2) and dimethyl phosphite (OPSIN returns
an anion for a neutral substance). `sources/README.md` carries the rule
and the numbers.

**NOT EVERY STATUTE PRINTS AN IDENTIFIER, and the drug-precursor ruleset
is anchored differently because of it.** Three were checked and only one
does: the CWC Annex gives a CAS beside every named chemical, while 21 CFR
1310.02 uses DEA chemical codes, the EU precursor annex uses CN codes, and
the UN 1988 Convention Tables give names only. So each DEA identity rests
on two independent structure derivations agreeing instead — OPSIN and
PubChem resolving the name alike, or, where OPSIN cannot parse the name
(most trivial names), PubChem's own systematic name for the structure
parsing back through OPSIN to the same structure. Measured over 49
entries: 32 by direct agreement, 14 by that round trip, 1 on connectivity
alone, 2 refused. Each rule records which route it took.

**The five unencoded entries are visible and countable**, not quietly
absent: saxitoxin and ricin, where a structural rule for a protein toxin
is meaningless; Schedule 3's diethyl phosphite, where PubChem's record for
the CAS the entry prints is a cation and OPSIN returns an anion, so
neither resolver reaches the neutral substance listed; and red and white
phosphorus, which are allotropes — the same element in different solid
forms, listed as separate entries, and not distinguishable by structure at
all. A hand-typed structure would not be traceable to the statute.

**Where the rules over-report, they say so on the finding.** Schedule 2's
entry B.4 opens "except for those listed in Schedule 1" and nothing can
exclude another ruleset's members, so a Schedule 1 organophosphorus agent
matches both; Schedule 3 carries no "and corresponding salts" wording
while the engine strips counter-ions anyway. Both are declared rather than
silently applied.

Licensing shaped the data model and is recorded in
`chem/data/regulatory/sources/README.md`: no CAS Registry (proprietary to
ACS), no DrugBank (CC BY-NC, incompatible with GPL), no ACGIH TLVs (OSHA
PELs are public instead), no IATA DGR (UN Model Regulations instead).

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
and scores 181/181 on `benchmarks/naming` — where STOUT was a neural model
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
(`src/openchem/vendor/`, see ARCHITECTURE.md) scores 181/181 with
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
[benchmarks/nmr/README.md](../benchmarks/nmr/README.md), and the summary is
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

## What is left, and why each one is left

Nothing here is simply unstarted — each is blocked on something nameable,
and three were checked again recently rather than taken on trust.

- **Plugin-system extras** (`ToolbarProvider`/`ContextMenuProvider`, a
  `RemoteServicePlugin` base, numeric priority, declared permissions). The
  recorded trigger is "a fourth plugin whose real requirements tell us the
  shape". There are still three. Building now means guessing.

  **Plugin-provided reaction templates are NO LONGER on this list**, and
  this entry claimed otherwise in three places for longer than it should
  have. `context.reactions.register([...])` exists
  (`plugins/context.py`'s `_ReactionTemplateRegistrar`), takes a list so a
  library is one call and one rollback, and is covered end to end. See
  ARCHITECTURE.md, which stated the real remaining gap correctly the whole
  time — that no *shipped* plugin called it — and which is now closed too
  by `examples/plugins/reaction_templates_plugin/`.
- **ChemSpider naming provider** — the RSC API returns 403 without a
  registered developer key. `naming_providers.py` is provider-shaped so
  it is a drop-in when a key exists.
- **Missing-residue repair** — spiked and declined on evidence, not
  blocked. See Phase 6's entry: the dependency turned out trivial, the
  gaps are not near binding sites, and the rebuild lands a median 2.3 Å
  from atoms actually observed.
- **MMTF import** — refused; the service no longer resolves and the
  vendored viewer dropped it.
- **The π-charge ITERATION** — what is left of an entry that used to read
  "σ/π charge separation" and named the whole thing.

  **The π COMPONENT shipped 2026-08-26.**
  `compute_orbital_electronegativity` takes a `component` parameter now,
  and the π branch is Marsili & Gasteiger's own Table I on their eq (7)
  [source:marsili1980] — a different parameter set, not the σ value
  relabelled, which is what the old entry rightly refused. Benzene's six
  carbons come out identical, phenol runs ipso > ortho > meta > para, and
  pyridine's nitrogen lands *below* its carbons because its own σ charge
  screens it, which is the mechanism the parameters exist to carry.

  **What is NOT shipped is the iteration that would make those values
  self-consistent**, and with it a π-charge calculator and a σ+π dipole.
  Three reconstructions were measured against the 15-molecule dipole table
  of [source:gasteiger1985]; the best scored 0.693 D against the paper's
  own 0.164 D, and the printed SD-POE equations came out at 0.834 D —
  **worse than no π term at all**. The papers specify the weighting and
  not the resonance-structure enumeration, so closing that gap means
  tuning an unspecified enumeration until 15 numbers agree. That is
  fitting, not reconstructing. docs/VALIDATION.md carries the table.

  So the shipped values are the paper's *starting POE* and say so, in the
  calculator's description, its provenance note and its docstring.

  **TSEI, HLB and Miller polarizability are NO LONGER on this list, and all
  three shipped.** They are `tsei_projection`, `griffin_hlb` and
  `polarizability` in the live registry. Each was deferred for reasons that
  expired without anyone re-reading them — "the parameters are unpublished"
  was a claim about ChemAxon's documentation rather than the literature, and
  "no reference value to gate against" was true when written and false by
  2004. **A deferral's reasons rot independently of its verdict**, which is
  why the corrected accounts are kept in `docs/sources.toml` under the
  original keys rather than deleted. See docs/VALIDATION.md for the
  measurements.
**Removed from this list because it had SHIPPED**: ensemble alignment
across a project. This entry read "`alignment.py` aligns onto a reference
SMILES; aligning a whole project needs its own panel, and nothing is
pushing on it" — while `services/alignment_service.py` was running
`_EnsembleAlignmentTask` against a reference molecule, `bootstrap.py`
was constructing it, and the panel it said was needed was sitting in
`ui/panels/alignment_panel.py`. Kept as a note rather than silently
deleted, because a deferral list that quietly loses entries is as hard to
trust as one that keeps stale ones, and `tests/test_docs_are_current.py`
now fails if this happens again.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the codebase is structured so
this has stayed additive — new content types get a sibling backend, new
calculators get a registration, and neither requires a rewrite.

## Continuous integration — built, and honest about its reach

The benchmarks are the arbiter for every scientific claim this project
makes. They used to be run entirely by hand; the cheap ones now gate every
pull request.

**`.github/workflows/tests.yml`** runs on every PR and every push to master:
the full suite, the naming benchmark, the regulatory benchmark, and
`--check` validation of the shipped regulatory rulesets. All four need only
Python, RDKit and OPSIN.

**`.github/workflows/vendor-tests.yml`** runs the vendored namer's own suite
behind a path filter on `src/openchem/vendor/**` — exactly when CLAUDE.md
says to run it — so its ~15 minutes land on the PRs that can break it and
on no others.

**Windows gates; Linux reports.** This application ships Windows-only, and
the suite is webview-heavy, so a green tick on the Windows job means green
on the platform users run. Linux is now wired as a **NON-BLOCKING** second
runner — it surfaces hidden environment assumptions without letting a
platform nobody ships block a merge.

**Non-blocking had to be made loud, or it would be decorative.**
`continue-on-error` on its own produces a green run page hiding thirty
Linux failures, which is the same failure mode as "a red suite silently
disables every gate behind it". The Linux job therefore writes a full
fingerprint to the run summary under `if: always()` —
collected/passed/failed/skipped/deselected/xfailed/xpassed plus the first
failing test names — reports the suite's real exit status rather than
inferring health from parsed output, and distinguishes **"tests failed"**
from **"the suite could not start"**. A parser that turned empty output
into `0 failed` would be the same decorative control one level down, so
that path is an explicit INFRASTRUCTURE FAILURE instead. Verified against
four inputs — clean, failures, empty, and output with no summary line.

Expect environment-only failures to arrive **one at a time**, each
unblocking the next; that is what this file already records happening
three times in a row on exactly this kind of move. The reasoning is in the
workflow header as well, where whoever revisits it will be looking.

### What CI still cannot do, and why it is not a gap to close cheaply

Six benchmarks stay off the HOSTED runners, because each needs a tool
that cannot be installed there. They are not hand-run any more — all six
are wired into the self-hosted workflow below — but no PR can gate on
them:

| benchmark | blocked on |
|---|---|
| `ir/`, `esp/` | ORCA — registration-gated, no public direct download |
| `nmr/` | the 152 MB nmrshiftdb2 index, built |
| `docking/` | AutoDock Vina plus RCSB receptor downloads |
| `admet/` | the ~1 GB ADMET-AI sidecar environment |
| `pka/` | the pkasolver sidecar environment |

**The `nmr/` row used to read "ORCA plus the 152 MB index" and that was
over-broad for the script the workflow runs.** `run_delta50.py` reads the
COMMITTED shieldings and says so in its own docstring; what it needs is
the built index, because its `lookup` rows come from
`nmr_database.predict_spectrum`. Other scripts in that directory
(`run_shieldings.py`) do need ORCA, which is where the confusion came
from — the constraint is per script, not per directory.

The workflow lists these by name so a green tick is not mistaken for full
coverage, and `docs/VALIDATION.md` carries their measured results with the
method and sample size behind each.

### The self-hosted phase — all six wired

`benchmarks-selfhosted.yml` runs these on a machine that has the tools and
publishes the results as artefacts, which is what closes the gap between
"measured once" and "still true".

**`workflow_dispatch` only, and that is a safety requirement rather than a
preference.** This repository is public and a self-hosted runner executes
with no sandbox, as whatever user started it, so a `pull_request` trigger
would hand shell access on that machine to anybody with a GitHub account —
a fork's PR brings its own workflow file. Dispatch and schedule run the
file from the default branch and cannot be fired by a fork. The reasoning,
and the two settings that shrink the remaining exposure to near zero, are
in [SELF_HOSTED_RUNNER.md](SELF_HOSTED_RUNNER.md).

**All six are wired now.** This entry read "IR, ESP and docking are wired
up. NMR, ADMET and pKa are not" until 2026-08-26; the last three joined by
the same route the first three did — one verified hand-run on the runner
machine, then encoding exactly what worked. A step that always fails is
worse than an absent one, because it trains people to ignore red.

The hand-runs, and what each settled that a guess would have got wrong:

| benchmark | hand-run result | what it found |
|---|---|---|
| NMR | 47 compounds, 13 held out; lookup MAE 13.51 ppm against ORCA's 2.51 | it needs **no ORCA**, and its reports must not go to their default directory |
| pKa | 24 of 24 compounds, MAE 0.29, median 0.14, 22/24 within 1.0 unit | a **hardcoded interpreter path** `_config.py` exists to remove |
| ADMET | 22 endpoints, 13,816 test and 9,179 train molecules, mean train/test gap +0.002 | the recorded TDC 403 **did not reproduce** |

**NMR's default output directory would have published nothing.** With no
second argument `run_delta50.py` writes into `benchmarks/nmr/reports/`,
and the workflow's artifact step uploads `bench-out/` and nothing else —
so the benchmark would have run every time and its reports would never
have left the machine. Those 24 files are also TRACKED. On this machine
the run reproduces them byte for byte and leaves the tree clean, so the
contamination is latent rather than live; it becomes live on any runner
whose nmrshiftdb2 index differs, and that index grows (~4% in three days,
per `benchmarks/nmr/README.md`). The script takes an output directory
now, defaulting to the old behaviour so a deliberate refresh still works.

**pKa's interpreter was a literal absolute path**, which is exactly what
`benchmarks/docking/_config.py` was written to remove — its docstring
says a hardcoded path "lets a benchmark drift away from the install it
claims to characterise", and this one had been missed. `_config` gained a
`pka_interpreter()` beside `vina_executable()` and `admet_interpreter()`,
reading the same `pka/pkasolver_python_path` setting the application does.

**ADMET's recorded failure mode did not reproduce, and that is recorded
rather than assumed.** CLAUDE.md notes TDC's Dataverse returning 403 with
PyTDC caching the zero-byte failure as a "local copy"; measured
2026-08-26 the download succeeded — 22 datasets, 46 files. The workflow
comment names the failure and its cure (delete `tdc_data/` before
retrying, because a bare retry reads the poisoned cache and reads as a
code bug) so the next person is not starting from nothing.

Docking joined by that route: `benchmarks/docking/redock.py` was run by
hand against real Vina 1.2.7 first (exit 0, seven targets, six landing in
the crystallographic pocket and 3EML nearby — 1HSG 0.17 Å, 4DKL 0.89,
3EML 3.92, 2RH1 0.33, 8ZYO 0.56, 1ERE 0.47, 4EY7 0.41), and only then
encoded. Two things the hand-run settled that a guess would have got
wrong: it must run from **its own directory**, because it imports a
sibling `_config`, and it must create `bench-out/` itself, because that
directory is otherwise made only by the IR/ESP generators — which are
skipped in exactly the case somebody dispatches the workflow with
`only: docking`.

**It is deliberately not gated on a distance threshold.**
`VinaDockingProvider` passes `seed=None`, so the shipped app runs Vina
with a random seed and the same-receptor spread is already 0.24–0.41 Å. A
numeric gate would fail on the search wandering rather than on a
regression. The step checks the pipeline RUNS and publishes its table; a
human reads the shifts. (This run's 3EML at 3.92 Å against a 2.59 Å figure
recorded elsewhere is that scatter, not a change — pinning the seed is
what any real A/B here needs.)

Wiring IR up found a real gap: `score.py` could SCORE a directory of ORCA
outputs but nothing could GENERATE them, so the benchmark was scoreable
and not runnable. `benchmarks/ir/generate.py` is the missing half, and
regenerating from scratch reproduced the published figures exactly — MAE
64.7 → 27.6 cm⁻¹, fitted factor 0.9666 — which is the first confirmation
those numbers have had from anything other than the run that produced
them.

**EVERY STEP IS `continue-on-error`, SO THE JOB'S TICK MEANT NOTHING.**
That is the decorative-control failure this file already describes one
section up, in the workflow written to avoid it — and the self-hosted job
had no fingerprint at all until 2026-08-26, so the verdict lived entirely
in whether a human opened the run page and read eight step outcomes. A
`Fingerprint - what actually ran` step now writes a table to
`$GITHUB_STEP_SUMMARY` and emits a `::error` annotation per failure, which
is the only half a machine can read.

**It distinguishes FOUR states, because two pairs of them are
indistinguishable from a tick:**

    ran and passed      ran and FAILED
    COULD NOT RUN       skipped by `only:`

GitHub separates success / failure / skipped by itself. It cannot tell a
missing ORCA from a benchmark that ran and came out wrong — both are a
non-zero exit — so the discriminator is whether the step left its OUTPUT
in `bench-out/`. Exercised against all four states before it shipped,
rather than reasoned about.

### What standing it up cost, recorded because it was not free

The first run went green, including the Qt and QtWebEngine tests on a
Windows runner. Three bugs were found by RUNNING the naming gate rather
than reading it — it created a scratch directory beside the repository,
left an untracked predictions file, and churned a tracked `results.json` by
using a different run label. None would have failed CI; all three would have
annoyed a developer.

CI then disproved a figure in CLAUDE.md on its first run. The vendored
suite was documented as `3193 passed, 16 skipped`; it is `3209 passed, 0
skipped`. 3193 + 16 = 3209, and those 16 are guarded by an ImportError on
`py2opsin` — a declared dependency — so the old number came from an
environment where the sync had not been done, and it contradicted the
Java-on-PATH instruction two lines above it.
