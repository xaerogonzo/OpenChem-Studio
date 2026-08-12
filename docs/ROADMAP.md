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

**A calculator that reports several numbers becomes several columns.** Of
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
HLB, Miller polarizability, σ/π charge separation — and that is recorded
in the modules themselves rather than left as silence.

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

**THAT NUMBER WAS THEN COMPARED AGAINST THE WRONG THING, and the sentence
here used to read "against an experimental ≈0.9 — the intensity is
essentially correct and always was."** It is not. ¹E₁ᵤ is **doubly
degenerate**, and ORCA reports each component as its own root: 0.9606 and
0.9607, summing to **1.9212**. An experimental oscillator strength is
obtained by integrating one absorption band, and two degenerate components
sit at the same energy and cannot be separated in that integral — so the
literature ≈0.9 is the BAND, and the computed quantity to compare with it
is the sum. TD-DFT overestimates it by **~2.1×**, not by 7%.

The error was exactly the degeneracy factor, which is what made it
invisible: one component against a band total reads as near-perfect
agreement. It is also the more coherent picture — a 2.1× intensity error
sitting beside a +0.98 eV energy error on benzene's hardest band is
believable, where near-perfect intensity beside a 1 eV energy error was
not.

**The relative conclusions in this section are unaffected**, because both
arms were measured the same way: the def2-SVPD collapse below is still an
order of magnitude, per component or summed. Only the absolute "essentially
correct" claim was wrong. `benchmarks/uvvis/score.py` prints components and
their sum side by side so the two can never be silently mixed again, and a
primary source giving benzene's ¹E₁ᵤ integrated intensity would put the
last of it beyond argument.

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

##### ωB97X-D HAS NOW BEEN TRIED, AND IT MOVES BENZENE THE WRONG WAY

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

**The one genuinely new finding is that ωB97X-D fixes what diffuse
functions broke.** The recorded intensity collapse at def2-SVPD — *f*
0.96 → 0.083, Rydberg states fragmenting the valence π→π\* — is a
**B3LYP** failure, not a basis-set one. With ωB97X-D3/def2-SVPD the
oscillator strength survives at 0.993 per component and the strongest
band is still identified correctly, at the cost of a worse position
(+0.84 against B3LYP/def2-SVPD's +0.49). So the two error modes still
cannot be minimised by one setting, which is the existing conclusion —
now confirmed against the functional that was supposed to resolve it
rather than only against basis sets.

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

### Visualization

Per-atom colouring on 2D and 3D from one shared `ColorScale`; molecular
surfaces (vdW/SAS/MS/SES); surfaces coloured by a continuous scalar field
(point-charge electrostatic potential, verified by correlating rendered
vertex colours against the supplied field, r = −0.96); a continuous 2D
property heat map; residue colouring driven by real docking interaction
data; and structure grids for multi-structure results.

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

Ships CWC Schedule 1 only. Every other domain — controlled substances,
precursors, export controls, transport, occupational, environmental and
the rest — registers EMPTY and says so in the coverage report, because an
absent domain is invisible and reads as "nothing applies". Adding one is a
JSON file and a build run, not a code change.

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
- **TSEI, HLB, Miller polarizability, σ/π charge separation** — measured
  and not shippable honestly, each recorded where the code would have
  gone.
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

Six benchmarks stay hand-run, because each needs a tool that cannot be
installed on a hosted runner:

| benchmark | blocked on |
|---|---|
| `ir/`, `esp/` | ORCA — registration-gated, no public direct download |
| `nmr/` | ORCA plus the 152 MB nmrshiftdb2 index |
| `docking/` | AutoDock Vina plus RCSB receptor downloads |
| `admet/` | the ~1 GB ADMET-AI sidecar environment |
| `pka/` | the pkasolver sidecar environment |

The workflow lists these by name so a green tick is not mistaken for full
coverage, and `docs/VALIDATION.md` carries their measured results with the
method and sample size behind each.

### The self-hosted phase — scaffolded, three of six wired

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

**IR, ESP and docking are wired up. NMR, ADMET and pKa are not**, and are
named as such in the workflow rather than encoded on a guess — a step that
always fails is worse than an absent one, because it trains people to
ignore red. Each has a multi-script pipeline that needs one verified
hand-run on the runner machine before it is encoded.

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
