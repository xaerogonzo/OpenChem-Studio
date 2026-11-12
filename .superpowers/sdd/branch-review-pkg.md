# Review package 24775f03..55011326

## log
55011326 Add the slice-3 ionization and pKa-evidence plan.
e3d57b87 Record slice 3 of salt composition in the changelog and the file map.
7b87e211 Catalog named salt ions as graphs, with sulfate and hydrogen sulfate kept apart.
638e5ed5 List ionization microspecies at a charge; never pick among several.
5feb4351 Ionize a named atom by moving both its hydrogens and its formal charge.
abb7d6c1 Compose two supplied ions as given, without inventing protons or a pKa.
000fddc9 Record salt pKa as a named step under comparable conditions, not a proof.
5c7616e6 Refuse a salt ionization that is only a net charge or several microspecies.

## stat
 CLAUDE.md                                          |   2 +-
 .../202611111916-salt-composition-slice-3-3717.md  |   6 +
 docs/ARCHITECTURE.md                               |   2 +-
 docs/README.md                                     |   2 +-
 docs/ROADMAP.md                                    |   8 +-
 docs/SALT_COMPOSITION_DESIGN.md                    |   3 +-
 docs/SOURCES.md                                    |  21 +-
 docs/sources.toml                                  |  21 +
 .../plans/2026-11-11-salt-composition-slice-3.md   | 941 +++++++++++++++++++++
 src/openchem/chem/data/ionic_species.json          | 113 +++
 src/openchem/chem/ionic_species.py                 |  90 ++
 src/openchem/chem/salt_ionization.py               | 119 +++
 src/openchem/domain/salt_evidence.py               | 105 +++
 src/openchem/domain/salt_stoichiometry.py          |  48 ++
 tests/test_ionic_species.py                        |  44 +
 tests/test_salt_evidence.py                        | 107 +++
 tests/test_salt_ionization.py                      |  67 ++
 tests/test_salt_stoichiometry.py                   |  36 +
 tools/suite-shard-pins.json                        |   3 +
 19 files changed, 1730 insertions(+), 8 deletions(-)

## diff
diff --git a/CLAUDE.md b/CLAUDE.md
index 1382171d..e80a3c6c 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -65,21 +65,21 @@ by `tests/test_layering.py`.
 ## Key Files
 
 - `src/openchem/main.py` / `bootstrap.py` â€” composition root, DI wiring
 - `src/openchem/domain/goal_run_preferences.py` â€” goal-run settings only (saved choice, else the recommendation, else the registered default); Spectra recommends 1H while `nmr_database` stays 13C; Run all recommended confirms before it starts
 - `src/openchem/chem/engine.py` â€” the only RDKit touchpoint for molecule conversion/canonicalization
 - `src/openchem/services/descriptor_service.py` â€” async descriptor computation (Queued/Running/Completed/Failed)
 - `src/openchem/app/inspector_dump.py` / `nmr_dump.py` / `results_dump.py` â€” observational JSON dumps for `OPENCHEM_DRIVE` (`inspect_report`, `nmr_panes`, `results`); `inspect` `"source": "result"` after `calculator` + `jobs_wait`; walk is `benchmarks/visual/louder_probe.json`
 - `src/openchem/ui/widgets/ketcher_editor_backend.py` â€” the embedded 2D editor, behind the `EditorBackend` interface
 - `src/openchem/domain/structure_template.py` / `src/openchem/chem/structure_templates.py` / `src/openchem/ui/dialogs/template_library_dialog.py` â€” OpenChem-owned complete-molecule template library (`docs/STRUCTURE_TEMPLATE_LIBRARY_DESIGN.md`): shipped JSON under `src/openchem/chem/data/structure_templates/`, user store under `data_root()/structure_templates`, insert via `EditorBackend.add_fragment` with 2.0 Ã… right-side placement and one undo step; peptide sequences and polymer S-groups stay on the roadmap
 - `src/openchem/chem/naming_providers.py` â€” structure <-> name; the only entry point to the vendored nomenclature engine
-- `src/openchem/domain/salt_stoichiometry.py` / `chem/salt_components.py` / `chem/salt_mode_a.py` -- two-ion charge balance, Mode B drawing analysis, and Mode A from four molecules (docs/SALT_COMPOSITION_DESIGN.md); no UI
+- `src/openchem/domain/salt_stoichiometry.py` / `domain/salt_evidence.py` / `chem/salt_components.py` / `chem/salt_mode_a.py` / `chem/salt_ionization.py` / `chem/ionic_species.py` -- two-ion charge balance, pKa evidence that never feeds the solver, Mode B drawing analysis, Mode A from four molecules, fully specified ionization, and the cited ion catalog (`chem/data/ionic_species.json`; docs/SALT_COMPOSITION_DESIGN.md); no UI
 - `docs/NAMING_LIMITATIONS_PLAN.md` / `docs/NAMING_COVERAGE_MATRIX.md` â€” WS2 naming-limitations programme (matrix complete 2026-11-08); WS1/WS3 pins include `tests/test_namer_nl009_ws1_natural_products.py` (NL-009), `tests/test_namer_nl018_ws3_numbering_conventions.py` (NL-018), plus `test_namer_nl090_*` / `nl097_*` / round-94 NL-011 / `nl013_*`
 - `src/openchem/domain/synthesis_route.py` -- the synthesis helper's route type (Stage 1 slice 1 of `docs/SYNTHESIS_HELPER_DESIGN.md`; no planner or UI yet): `Route` (steps in forward order, a tree with one root, checked at construction), `RouteStep`/`RouteMolecule` (a field the planner did not supply is `None`, shown as "not provided" by `shown`), `ValidationReport` (separate outcomes; conservation only where the mapping is complete), `RouteSet` with a closed `RouteStatus` and `SearchTermination` and `STANDARD_LIMITATIONS` that cannot be omitted, and `read_termination` (the planner has no stop-reason field, so it is read from limits and counters and is `unknown` otherwise); tested by `tests/test_synthesis_route.py` against the real planner fixtures in `benchmarks/synthesis/fixtures/`
 - `src/openchem/chem/synthesis_gate.py` -- the regulatory gate on synthesis planning (Stage 1 slice 2 of `docs/SYNTHESIS_HELPER_DESIGN.md`; types in `domain/synthesis_gate.py`): `check_target` returns a `GateDecision` (`allowed`, `refused` on a `cwc-schedule-1` match, or `unscreened`, which stops planning exactly as a refusal does) from its OWN engine built from `load_all(include_user=False)`, failing closed on every way the ruleset or the structure can go wrong; `screen_nodes` flags the molecules of a planned route with the wider rulesets as alerts, never refusals; `permits_planning` is true only for `allowed`; tested by `tests/test_synthesis_gate.py`
 - `src/openchem/chem/aizynth_planner.py` / `aizynth_runner.py` -- the AiZynthFinder runner and parser (Stage 1 slice 3 of `docs/SYNTHESIS_HELPER_DESIGN.md`): the planner is NEVER imported, it is the user's own Python environment run as a child process (`run_planner`: argument array, `-I`, one JSON request on stdin, one JSON document on stdout, bounded output and wall clock, a cancel or overrun kills the child, nothing retries); `aizynth_runner.py` is handed to that interpreter as a PATH, imports nothing from openchem and checks every named asset before the library loads; `BENCHMARK_FINDING` is the measured result (protocol 3's 13 of 51 with its interval and the patent figure beside it, each held to `benchmarks/synthesis/RESULT_3.md` and `RESULT_2.md` by a test) that every plan it makes carries in its limitations; `parse_document` turns the response into a `RouteSet`, keeping only routes with a reaction whose starting materials are all flagged in stock and saying how many it left out; every failure is a typed result, `failed` or `unavailable` naming the asset; tested by `tests/test_synthesis_planner.py` (four tests drive the real planner where it is installed); it asks for every solved route (`all_routes` on) and keeps the first `ROUTES_SHOWN` (10) in the order of `chem/route_ranking.py` (the PaRoutes route score, then the planner's own score, then its order: protocol 2's M2, held to `benchmarks/synthesis/route_rank.py` by `tests/test_synthesis_route_ranking.py`), saying how many it did not keep
 - `src/openchem/chem/route_validation.py` -- the route validator (Stage 1 slice 6 of `docs/SYNTHESIS_HELPER_DESIGN.md`, moved from the spike): `validate_route(route)` returns the domain `ValidationReport` (molecules parse; each step's reaction parses AND its sides are the molecules the step connects; mapping complete/partial/absent; conservation only where the mapping is complete, else not assessable; stock; what the planner left out), nothing repaired or invented, never raises; `parse_document` attaches it to every route it keeps; `tests/test_synthesis_route_validation.py` runs it on the real fixtures and holds it equal to the spike's `benchmarks/synthesis/route_validator.py`, which the frozen quality benchmark still runs. The other half of slice 6 is `chem/synthesis_gate.annotate_route_set` (every distinct molecule of a plan screened through `screen_nodes` into `RouteSet.node_screenings`, applied by the planning service; an alert never removes a route, a screen that cannot run marks the molecules unscreened), tested by `tests/test_synthesis_annotations.py`
 - `benchmarks/synthesis/PREREGISTRATION_3.md` / `RESULT_3.md` / `run_quality_3.py` / `judge_3.py` / `artifacts_protocol3/` -- protocol 3 of the planner quality benchmark (option 3c, run 2026-10-24, reading LOWER): 51 routes from journal papers after the model's training data (190 papers read; lead rule, 4-reaction cap, reader agents + a second reading + `validate_refs.py`), searched on three stocks with protocol 2's settings; M2 at 10 = 13 of 51 = 0.255, 8 of 36 against 14.0 expected from protocol 2's depth rates (p = 0.007); `judge_3.py` is the pure part (lenient match, same-materials count, reaction-level recall, Wilson interval, the reading), held by `tests/test_synthesis_protocol3.py`; the references carry no DOIs (the DOI guard sweeps `.json`), the stem-to-DOI tables are kept in the maintainer's library; `BENCHMARK_FINDING` quotes it first, with protocol 2's 41.7% beside it as the patent-target figure
 - `benchmarks/synthesis/run_addendum_3.py` / `RESULT_3_ADDENDUM.md` / `artifacts_protocol3_addendum/` -- the post-freeze addendum to protocol 3 (2026-10-25): two papers that arrived after the freeze (Kral's article, Singh's SI), read with the same rules, one search each on the primary stock, 0 of 2 recovered, reported BESIDE the frozen result and never in it (a third, Ma's, was excluded: its lead needs about 8 reactions); `run_addendum_3.py` only calls `run_quality_3.py` and `judge_3.py`, the stock is the frozen primary plus these routes' leaves, and no reading is made; held apart from the frozen 51 by `tests/test_synthesis_protocol3_addendum.py`
 - `src/openchem/services/synthesis_planning_service.py` -- the synthesis helper's one planning path (Stage 1 slice 4 of `docs/SYNTHESIS_HELPER_DESIGN.md`): `request_plan(molecule, requested_by=...)` runs the regulatory gate FIRST (a refusal or an `unscreened` starts no process and registers no job), captures the target and the `PlannerSetup` before the worker starts, allows one slot per molecule and one search at a time (a pool of its own), and `cancel`/`shutdown` (wired to the application quitting) kill the planner child; `set_project(project, plans)` and `plan_store(project)` are the project file's two ends (a plan read from a FILE is input from outside: the gate is asked again, each route is validated again, the sentences are this build's; see `domain/synthesis_route_codec.py` and `domain/synthesis_plan_store.py`, the `synthesis_plans` block, only routes found or none found); `result_for(molecule)` returns the stored `RouteSet` bound to the structure it was made for (`BoundResult.is_current`, never for another molecule); events `SynthesisJobStateChanged` / `SynthesisRouteReady`; the setting provider is a stub that answers "not set up" until the External Tools slice; tested by `tests/test_synthesis_planning_service.py`
 - `src/openchem/services/synthesis_planner_setup.py` / `aizynth_setup.py` -- the planner's setting and the External Tools tab's checks (Stage 1 slice 7 of `docs/SYNTHESIS_HELPER_DESIGN.md`): `describe_status` reads two paths and starts nothing; `verify` (the Test button) names the first thing wrong in order and then runs a real trivial search; **Set Up Automatically** (`aizynth_setup.install`) builds a Python 3.12 sidecar, pins `aizynthfinder==4.4.1` and `pyarrow<21`, and runs `download_public_data`; `SetupProvider(settings)` is the planning service's `setup_provider`, reading the configuration once per file as it stands through the planner's OWN Python (`chem.aizynth_planner.inspect_environment`, the runner's `aizynth-inspect-request-1`), choosing `uspto`, `zinc` and no filter unless `aizynthfinder/expansion|stock|filter` say otherwise; the tab is `external_tool_catalog.aizynthfinder()` (a `ManagedExecutable` with an `ExtraPath` for the configuration file); tested by `tests/test_synthesis_planner_setup.py` and `tests/test_aizynth_setup.py`
 - `plugins/synthesis_planner/` / `src/openchem/plugins/synthesis_access.py` / `src/openchem/app/synthesis_host.py` / `src/openchem/chem/reaction_depiction.py` -- the Synthesis panel (Stage 1 slice 8 of `docs/SYNTHESIS_HELPER_DESIGN.md`): a bundled plugin whose `panel.py` shows the selected molecule, three lists filled from the planner's configuration on a worker (`SetupProvider.options()`), Plan and Cancel, the routes, a route's steps, each step drawn by `chem/reaction_depiction.py` (from the plain molecules, never the mapped reaction) and the standing limitations, with `route_text.py` holding the words as pure functions; it reaches the planner only through `context.synthesis` (reads, drawing) and `context.synthesis_requests` (start, cancel, choose; for a panel's buttons, never a tool) over one `SynthesisHost`, and every start is `SynthesisPlanningService.request_plan`, where the gate runs first; tested by `tests/test_synthesis_panel.py`, `test_synthesis_host.py`, `test_synthesis_options.py`, `test_synthesis_route_text.py` and `test_reaction_depiction.py`, driven by `benchmarks/visual/synthesis_panel.json`
diff --git a/changelog.d/202611111916-salt-composition-slice-3-3717.md b/changelog.d/202611111916-salt-composition-slice-3-3717.md
new file mode 100644
index 00000000..8942265a
--- /dev/null
+++ b/changelog.d/202611111916-salt-composition-slice-3-3717.md
@@ -0,0 +1,6 @@
+### Salt composition, slice 3 (library, no UI)
+
+- Fully specified ionization (site transforms; net charge alone refused;
+  several microspecies at one charge listed, not picked), two supplied ions
+  as given, a small cited ion catalog, and `pka_compatible` as named-step
+  evidence that never feeds `balance_two`. Still no panel and not a crystal.
diff --git a/docs/ARCHITECTURE.md b/docs/ARCHITECTURE.md
index 8b72303a..84ba5d02 100644
--- a/docs/ARCHITECTURE.md
+++ b/docs/ARCHITECTURE.md
@@ -25,21 +25,21 @@ Chem engine (the ONLY layer that imports rdkit / openbabel)
 Events flow orthogonally to this stack: services publish typed `Event`
 objects (`src/openchem/events/events.py`) on a typed `EventBus`
 (`src/openchem/events/base.py`); UI panels â€” and eventually plugins â€”
 subscribe by event type rather than by ad-hoc signal name.
 
 ## Package map
 
 | Package | Responsibility |
 |---|---|
 | `openchem.domain` | Pure data: `MoleculeModel`, `ProjectModel`, `DescriptorValue`, `ConformerModel`, the report types (`Fact`/`Detail`/`AtomReport`/`BondReport`/`MoleculeReport`/`ReportResult`, plus the producer-declared `ArrowAnnotation`/`ConeAnnotation`/`AxesAnnotation` a result carries on `ReportResult.spatial` â€” geometry the CALCULATION produced, validated fail-closed by `valid_spatial_annotation` and never UI decoration; `ReportResult.charts` is the SECOND such channel, built to that precedent â€” a `StickChartAnnotation` validated by `valid_chart_annotation`, which checks the SHAPE of the declaration and refuses to judge the chemistry, so a chart is declared by its producer and never derived from whatever numbers a report's facts happen to contain), `MergedResults` (several reports for one molecule kept WHOLE beside a flattened fact view, so charts, spatial annotations, provenance and stale state are read off the reports rather than copied into one anonymous result that could carry only one `report_id`), `mass_spectrum.py` (`IonSpecies`/`MassPeak`/`MassSpectrum`/`SpectrumBasis` â€” an ion's identity is a COMPOSITION plus a charge and never a scalar mass delta, because an adduct with its own isotopes contributes its own envelope and a number has nowhere to put it), `MacromoleculeModel`, `DockingBox`/`DockingPoseModel`/`DockingResultModel`, plus the shared `CacheState` enum and `Provenance` dataclass (`domain/common.py`). No RDKit, no Qt. Molecules (and macromolecules, and docking results) are identified by UUID, never filename or list position. **`crystal.py` (`Lattice`/`SymmetryOperation`/`Site`/`Crystal`) is the periodic solid, and it does NOT inherit from the molecule model in either direction** â€” see "A crystal is not a molecule" below, which is the load-bearing decision of that work. |
-| `openchem.chem` | The only place `rdkit`/`openbabel` are imported, and by some margin the largest package (**165 modules, counted 2026-11-11**, plus the `regulatory/` subpackage). Grouped by what they are for, since the flat listing is no longer navigable: **core** â€” `engine.py` (`ChemistryEngine`: MoleculeModel <-> RDKit Mol, canonicalization, 2D depiction including the property heat map, 3D measurement, and `formal_charge()`, the one place UI gets a chemistry-derived default without importing rdkit), `identifiers.py`, `io_backends.py`, `camera_orientation.py` (the rotation a 3D viewer camera applies, as a matrix â€” pure arithmetic with no RDKit in it, so the one transform that can be plausibly backwards is testable without a molecule or an event loop). **Structure files** â€” `structure_io.py`, `binarycif.py`, `structure_summary.py`, `molblock_summary.py` (counts and charge from a held molblock, for the Inspector dump), `structure_assembly.py`; see the pipeline section below. **Docking** â€” `docking_providers.py`, `vina_engine.py`, `pose_analysis.py`, `pose_plausibility.py` (four distance checks on each pose, stored beside the interactions), `pose_choice.py` (the sentence under the pose table saying pose 1 is the best-scoring pose and not a verified one, and which poses the score cannot separate from it; pure), `binding_site.py`, `receptor_library.py`, `interaction_analysis.py`. **Structure coverage** â€” `coverage_hooks.py` (the hooks behind `CalculatorDefinition.preflight`: each calls its calculator's own refusal function and says covered, covered with a limit, or certain to refuse, so a row can say so before a run; design in `docs/STRUCTURE_COVERAGE_DESIGN.md`). **Quantum/spectroscopy** â€” `orca_engine.py`, `proton_affinity.py` (the chemistry of the proton-affinity and gas-basicity calculation, ported from the benchmark that measured it: scope check, structures and ORCA input, output reader, symmetry-number override and the selection of PA and GB with the site table; no engine, the run is a later stage), `bond_dissociation.py` (the chemistry of the X-H bond dissociation enthalpy calculation, ported from the two benchmarks that measured it: scope, the bond classes, the parent's conformers and the radical starts made from them, the radical-skeleton check, the bond enthalpy from the lowest structure of each species and the measured error stated beside it; no engine, the run is `QuantumChemistryService.request_bond_dissociation`), `quantum_run_request.py` (every rule for whether a molecule may be run on ORCA as asked, with what, and what the service is handed: the Quantum Chemistry panel's Run button reads its widgets into a `RunChoice` and calls `prepare_run`, and an assistant's card is to call the same function, so the two cannot disagree; no widget, no event), `psi4_engine.py` (Psi4 as a second engine for single points and optimizations: the functional mapped by name through a table checked against ORCA, because the same label is not the same functional; `docs/PSI4_ENGINE_DESIGN.md`), `xtb_engine.py` (xtb, GFN2/GFN1-xTB, as a third engine for single points, optimizations and frequency jobs; registered with the service and offered by the Engine box when `xtb/executable_path` is set, with a locate-only External Tools tab and its own method presets (`QuantumEngineProvider.method_basis_presets`). The charge, spin and job travel in a header comment on the inputâ€™s first line because `command_args` is not handed them, the geometry is a Turbomole block because xtb refuses a `.inp` name, the electron count is checked because xtb accepts an impossible one, and a run is judged from stdout only; `docs/EXTERNAL_TOOL_CANDIDATES.md`), the `nmr_*` family (database lookup, HOSE codes, scaling, TMS referencing, the lookup+ORCA hybrid, correlation, signals), `huckel.py`, `electronic_properties.py`, `dipole.py`, `fukui.py` (condensed Fukui functions from the Hirshfeld charges of a molecule's neutral, cation and anion: pure arithmetic with no ORCA in it, which refuses a state whose charges do not sum to that state's charge; `orca_engine.py` supplies the charges), `fukui_plan.py` (which ORCA jobs a Fukui run has and which finished one it reads: an anion's N+1 state is a dianion, written last so that its failure costs f+ and not f-; the extra SCF starts an anionic state gets at a basis with diffuse functions and the choice of the lowest solution, and the hole starts of the N-1 state that look for other states of the cation; pure), `fukui_states.py` (which state of the cation f- is read from: the lowest of the N-1 jobs, a degenerate level averaged, the states within 0.5 eV reported as competing; pure), `boltzmann.py`, `tautomer_conformers.py` (the conformer pool behind one stereo class of one tautomer: seeded ETKDG, a force-field prefilter, the project's own distinct-conformer prune, a top-K or capped selection, and a recipe-based identity) and `tautomer_nmr.py` (tautomer NMR, P5: which stored tautomer geometries NMR is run on and which conformers of a tautomer belong in one average -- the part that needs no ORCA; the run itself is in `services/quantum_chemistry_service.py`) and `tautomer_distribution.py` (candidate generation, conformer-search policy, 3D embedding and incomplete-aware Boltzmann combination for the real tautomer-distribution feature -- builds on `boltzmann.py`'s own `boltzmann_weights`, never reimplements it; the QC orchestration that runs the actual ORCA jobs lives in `services/quantum_chemistry_service.py`), `nmr_measured.py` (a MEASURED NMR spectrum read from JCAMP-DX, as an immutable record with its provenance and a hash of the original bytes -- never merged into a prediction, and scaling is view state, not data) and `nmr_export.py` (a predicted spectrum written as JCAMP-DX or an SD file, read from the signals and the viewer's parameters and labelled predicted), `tautomer_ranking.py` (RDKit's own heuristic tautomer preference score, competition-ranked with ties kept as ties, and its four-valued cross-check against ORCA -- a heuristic, never an energy or a probability, so nothing in it may feed a population or the validation gate), `tautomer_validation.py` (the PREREGISTERED validation of the tautomer-distribution model: its criteria and reference values are data in `data/tautomer_validation.json`, a closed schema frozen before any number was computed and pinned by hash, and this module is the comparison -- tautomer-level, rebaselined to the reference's own zero, pairwise tie-aware ranking and a per-system MAE AND maximum-error gate -- as pure functions; the ORCA half is `tools/tautomer_validation.py`, which drives the application's own path), `ir_export.py` (a predicted IR spectrum written as a labelled JCAMP-DX PEAK TABLE -- positions and integrated intensities with no lineshape, the same decision the IR plot makes, and not readable by this application's own overlay import, which refuses peak tables by design), `vibrational_modes.py` (normal-mode character by internal-coordinate decomposition), `mode_animation.py`, `orca_surfaces.py` + `cube.py` (driving `orca_plot` and reading Gaussian cubes into the existing `ScalarField`), and `jcamp.py` + `spectrum_overlay.py` (reading a measured spectrum and reconciling it with a computed one). **Calculators** â€” `descriptor_providers.py` plus the per-topic modules it registers (`topology_analysis`, `geometry_analysis`, `surface_analysis`, `elemental_analysis`, `steric`, `substructure`, `structure_generators`, `markush`, `logd`, `ph_curves`, `pka_sites`, `pka_species_ladder`, `mpo_scores`, `bbb_stereo`, `scalar_field`, `alignment`, `molecular_dynamics`, `calculator_options`), and `components.py` (WHICH components of a drawing each calculator is handed -- the one place a `CalculatorScope` is applied, so Properties, Batch and the 3D overlay cannot select differently: a compound property on the ChEMBL parent, a description of the drawing on the whole of it, and a coded refusal when a salt has no single parent), `salt_mode_a.py` (Mode A from four molecules: two parent neutrals and two product ions, with domain refusals; no UI), `salt_components.py` (Mode B analysis of a disconnected drawing: graph identity, drawn counts, a diagnostic theoretical ratio, and no silent rewrite of an unbalanced drawing; no UI), `route_ranking.py` (the order a plan's routes are shown in: the PaRoutes route score, equal scores sharing a rank, then the planner's own score; pure, and held to the benchmark's own ranker by `tests/test_synthesis_route_ranking.py`), and `route_validation.py` (what can and cannot be checked about one planned route, as separate outcomes on the `ValidationReport` and never one pass/fail: molecules parse, each step's reaction parses and its sides are the molecules the step connects, atom mapping complete/partial/absent, atom conservation only where the mapping is complete and `not_assessable` otherwise, stock, and what the planner did not supply; nothing is repaired or invented; moved from the spike's `benchmarks/synthesis/route_validator.py`, which the frozen quality benchmark still runs and a test holds it equal to), `reaction_depiction.py` (one step of a planned route drawn as an SVG, reactants then arrow then product, from the planner's PLAIN molecules and never from its mapped reaction, so no atom-map number is printed beside an atom; raises `DepictionError` naming the molecule it cannot read, and the panel shows a sentence in its place), `synthesis_gate.py` (the regulatory gate on synthesis planning: one decision about the TARGET before any process starts, `allowed`, `refused` on a CWC Schedule 1 match or `unscreened`, from its OWN engine built from the shipped rulesets only and failing closed, plus alerts on the molecules of a planned route from the wider rulesets; the decision types are `domain/synthesis_gate.py`). **Sidecars** â€” `pka_providers.py`/`pka_runner.py` and `admet_providers.py`/`admet_runner.py`, each a pair where the `_runner` is executed BY the sidecar's own interpreter and imports nothing from `openchem`. `pka_worker.py` keeps ONE pkasolver sidecar warm between structures (a single owner thread over a request queue, `pka_runner.py --serve` as the child, idle expiry, killed on timeout, an idempotent `shutdown_worker()` wired to `aboutToQuit`): it removes the ~3 s model load a fresh process paid per new structure, while a structure already seen is still answered from `pka_providers`' own cache without reaching it, and `use_cache=False` still runs a fresh one-shot process. `aizynth_planner.py`/`aizynth_runner.py` are a third such pair for the synthesis helper, with one difference: the child runs in the USER'S OWN planner environment (AiZynthFinder needs Python 3.10 to 3.12 and `numpy<2`), never in OpenChem's and never imported into it; `aizynth_runner.py` takes one JSON request on stdin and writes one JSON document on stdout, checks every named model, template and stock file before the library loads, and is handed to that interpreter as a path, while `aizynth_planner.py` starts it with an argument array and `-I`, bounds its output and wall clock, kills it on cancel, types every failure, and turns the document into a `RouteSet` (`domain/synthesis_route.py`). **Naming** â€” `naming_providers.py` (structure <-> name across PubChem, the vendored engine, and OPSIN, each result labelled with its source and whether it is `exact`, `derived` or `parsed`) and `structure_annotation.py`, which takes the SECOND return value the naming engine always had: ring systems, functional groups, stereocentres and atom numbering, as plain atom-indexed data no vendor type escapes from, plus `atom_numbering.py` (the numbers the 2D editor draws beside the atoms: the drawing's own 1-based positions, or the engine's IUPAC locants -- and the STATUS LINE that keeps "numbered nothing" apart from "could not be numbered", since both draw an empty canvas) and `feature_vocabulary.py` (vocabulary v2's ontology -- what each feature IS, cited to the Gold Book by page, with its roles, charge states and relations -- written before any pattern; see "A feature is detected once" below) and `structural_features.py` (its detector: one SMARTS spec per feature with atom ROLES carried as map numbers, the charge state measured off the drawing, and the relation resolution and per-view projections every consumer reads). **Substances and bonding** â€” `substance.py` (what a structure IS rather than what it contains: molecule / ion / ionic salt / coordination / organometallic / mixture, each with its evidence, and a REFUSAL with its reason when the graph does not decide â€” `[Na+].[Cl-].[K+].[Br-]` could be NaCl+KBr or NaBr+KCl and nothing in the drawing says which; it also names the coordination polyhedron, but only from a real 3D conformer and only as an RMS deviation over EVERY donor-metal-donor angle against a reference with the same donor count -- the donor count never decides on its own, and the 10-degree tolerance is bounded below by the tris-chelate octahedra it must accept and above by the closest pair of references it must not match together), `organometallic_adapter.py` (**the only file that touches the vendored namer's perception**, deliberately, so that when that engine changes one file needs repairing rather than four), `lattice_energy.py` (Kapustinskii from the Shannon six-coordinate radii in `data/ionic_radii.json`; refuses polyatomic ions by name because they need a thermochemical radius instead), `nuclides.py` (NUBASE2020 as a read model, 5,684 nuclear states keyed on a `NuclideKey(z, a, state_index)` -- a TYPE rather than a bare tuple, because it is the identity contract carried through the chart, the click and the write refusal, and three places reassembling `(z, a, i)` by hand is where a click starts landing on the wrong state; half-lives in seconds with an eight-state qualifier vocabulary, because a bound, an estimate and a measurement must not render alike), `decay.py` (the decay-mode GRAMMAR rather than a 45-entry lookup, so a mode NUBASE adds later parses without a code change, plus the chain walk, whose every leaf states the reason it is one -- three PHYSICAL reasons and a fourth that is deliberately not physical, since `underspecified` describes the DATA rather than the nucleus and folding it into `unfollowable` would tell a reader no daughter exists when one does; and `DaughterProvenance`, because NUBASE names no daughter STATE, so drawing a chain at all means choosing one and every edge records whether it did), `decay_svg.py` (that chain on the chart of the nuclides -- (Z, N) determines the CELL and the state index chooses a slot within it, with the row pitch growing so a stack cannot reach the row below; an assumed edge is DASHED and the legend explains the dash, because a provenance that exists while failing to protect interpretation is worse than none), `isotopes.py` (writing a mass number onto a molblock; the element is DERIVED from the atom index and never passed in, which makes "apply C-13 to every oxygen" unexpressible rather than merely validated -- and `IsotopeRefusal` is a VALUE with generated text so `if "isomer" in message` never becomes application logic, since a molfile records a mass number with no place for a nuclear state and **the refusal is the feature**), `electron_shells.py` (an atom's configuration as `(n, l, occupancy)` triples â€” **the configuration string is an OUTPUT, never the state**, because taking an electron off the end of the displayed string is wrong for exactly the ions people try first: Fe's 4s empties before 3d though it filled after). **Crystallography** â€” `cif.py` (a small-molecule/mineral CIF reader, **separate from `binarycif.py`**, which is protein-oriented and reads neither crystal symmetry nor site occupancy â€” the overlap is "both are text with loops in"), `space_groups.py` (resolving a CIF's space-group SYMBOL to the operations it stands for, which is the fallback when the file lists none -- and `Crystal.symmetry_source` records which of the two answered, because a cell that was never expanded still has a formula and a density and every one of them is wrong), `crystal_analysis.py` (density, coordination shells under explicit periodic images, and the scene a viewer draws; a `Neighbour` carries the position of the IMAGE that is close, not the asymmetric-unit atom's, which is what lets `describe_site` answer a click with the same geometry classifier the molecular path uses), `crystal_report.py` (the facts, and the list of molecular calculators that do not apply -- derived from each calculator's own `applies_to` declaration, whose default is molecule-only, rather than from a blocklist of category names that had rotted in both directions), `powder_xrd.py` (the calculated pattern that report carries: d-spacings from the reciprocal metric tensor, absences from the structure's own symmetry operations rather than a table of extinction conditions), and `periodic_charges.py` (EQeq partial charges for a cell -- **the only calculation here about a periodic solid**, reached through `crystal_report.py` because a `CalculationRequest` cannot name a crystal; see the settled Known TODO)). **Batch** â€” `result_reduction.py` (every result shape collapsed to table cells), `analytics.py`, `clustering.py`. **Charges** â€” `charge_equilibration.py` (RappÃ©â€“Goddard QEq, Bultinck EEM and Ionescu 2013 EEM, all geometry-dependent, each refusing rather than approximating: QEq declines a non-convergent or final-bound-active solution by name, Ionescu a runaway charge; Ionescu's two shipped models live in `data/eem_ionescu2013.json`, built from the Table S1 test fixture by `tools/build_ionescu_parameters.py` and never edited by hand), `typed_eem.py` (two further EEM models typed by element and highest bond order -- JirouÅ¡kovÃ¡ 2009 B3LYP/6-31G* Merz-Kollman and NEEMP 2016 Ccd2016 NPA -- each its own model with its own kappa, never combined; pure numpy on element symbols, coordinates, a Kekule bond list and a net charge, refusing a type a model lacks by name and naming the other model when it has it; data in `data/eem_second_models.json` built by `tools/build_eem_second_models.py`; the plan and its checks are `benchmarks/charges/models/eem_second_models_preregistration.md`; reachable as methods of the 3D partial-charge calculator, NEEMP's for any molecule it can type and JirouÅ¡kovÃ¡'s for molecules with Cl, Br or S only), `resonance_forms.py` (the resonance forms of a molecule for those typed EEM models -- RDKit's own enumeration of the kekulised molecule, only the forms with the smallest sum of formal charges kept, a cap that makes the average refuse instead of guess -- and `typed_eem_for_molecule`, the one call that charges a molecule with the `resonance` option `averaged` (default), `as_drawn` or `refuse`; design `benchmarks/charges/models/eem_resonance_typing_design.md`), `geometry_charges.py` (those models ON the stored conformer, which is what makes them different answers from the drawing-based ones) and `protonation_geometry.py` (the dominant ionisation state at a pH on a conformer, with the geometry carried across rather than rebuilt â€” heavy atoms and retained hydrogens stay bit-identical and only the new hydrogens move), plus `result_structure.py` (which structure a per-atom result's indices refer to â€” the one it carries, for a result computed on a structure nothing stores, such as that pH state â€” and so which one a view must draw; kept apart from `atom_identity.py`, which answers the different question of which atom of one structure is which atom of another). `periodic_charges.py` is under Crystallography, because a crystal is not a molecule. **Lewis structures** â€” a deliberately layered family, and the layering is the point: `lewis_diagram.py` (what a Lewis structure SAYS, as data â€” no chemistry, no drawing, no Qt), `lewis_builder.py` (**the only RDKit in the feature**), `lewis_layout.py` (which 2D layout to draw it from), `lewis_svg.py` (the picture â€” no RDKit, no Qt, no chemistry), plus `lewis.py` (Lewis acid/base SITE analysis, offline from the structure alone) and `lewis_adduct.py` (whether a given acid binds a given base, and how strongly, from Dragoâ€“Wayland E and C parameters) and, for the first recipe (`domain/lewis_pairing.py`), `lewis_pairing_eval.py` (that pairing evaluated over stored quantum-chemistry runs into a `RecipeRun`) and `recipe_host.py` (the one chemistry question a recipe asks of a stored run: does its 3D input still describe the drawing). The two senses of "Lewis" living in one package is a naming collision worth knowing about: the first four are the electron-dot diagram, the last two are acid/base chemistry. **Group-contribution and empirical properties** â€” `group_contribution.py` (the mechanics two methods share, and nothing more), `joback.py`, `hansen.py` (Stefanisâ€“Panayiotou), `gutmann.py` (donor and acceptor numbers from the classical tables), `energetics.py` (oxygen balance and detonation), `aromaticity.py` (HOMA per ring), `conceptual_dft.py` (hardness, softness, electrophilicity). **Three of these ship under a narrower claim than their output suggests**, and their docstrings say so in their own first lines: `hlb.py` ("and where it means anything"), `tsei.py` ("under that name only") and `polarizability_miller.py` ("both methods, with the traps") â€” see SCIENTIFIC_LIMITATIONS' "Numbers whose applicability is narrower than their output". **Elements and the periodic table** â€” `element_reference.py` (one element's facts, assembled from the three places they live), `element_palettes.py` (**what a cell's colour is allowed to MEAN**, which is a claim rather than a style choice), `electron_layout.py` (where a lone pair may be drawn, as rules rather than a placement) and `electron_overlay.py` (what the canvas overlay is TOLD, and nothing about where it draws). **Structure handling** â€” `structure_templates.py` (shipped complete-molecule catalogs as 2D molblocks and right-side placement for the Template Library; no dummy-atom fragments), `structure_check.py` (the analysis engine: issues, checkers and their registry), `structure_clipboard.py` (reading a structure out of whatever happens to be on the clipboard), `stereochemistry.py` (what a geometry DID to a structure's stereochemistry), `conformer_providers.py` and `projection_geometry.py` (shape from the van der Waals surface: volume, area, extent), with the layers under it: `disc_union.py` (the EXACT area of a union of discs, which is what a molecule's shadow is -- exact because a minimum found over orientations needs an area that is smooth in the direction, and a grid's error is not), `projection_search.py` (the smallest and largest shadow over every orientation, the circle round it and the molecule's size along it; the area at each orientation is exact and the extreme is searched, and it says how many orientations it looked at) and `sasa.py` (accessible surface area by Shrake-Rupley on a deterministic point set, 0.3% from a dense reference; it replaced `rdFreeSASA`, which was given zero radii by its own classifier and read half the true area -- see `surface_analysis.py`'s docstring) and `vdw_radii.py` (Bondi's own radii, extended by Mantina et al.: the one table behind the accessible surface, van der Waals volume, projections, Geometry and steric bulk; RDKit's table, which is Batsanov's and not Bondi's, is only the fallback for elements neither covers -- `VDW_RADII_ASSESSMENT.md`). `hbond_sites.py` (the hydrogen-bond site table: RDKit's donor and acceptor definitions written out as patterns, because RDKit exposes a count and no atoms, held to that count by a test over a corpus in two forms -- the acceptor pattern is RDKit's own with the aromatic nitrogen restricted to two connections, which the corpus forced -- and, at a pH, each role carried back to its drawing atom through `pka_providers.heavy_correspondence`), `torsions.py` (the torsion table: which bonds the Rotatable Bonds count counts, written out as a pattern because RDKit exposes no list, held to that count by a test over a corpus, and the dihedral about each) and `ionisable_sites.py` (acid or base from the charge of pkasolver's own proton-holding state, and the Henderson-Hasselbalch fraction ionised for one site; it reads the predictions `pKa` keeps and asks the sidecar for nothing more) sit with the calculators they serve, as does `geometry_options.py` (the Geometry calculator's options, declared once: energy unit, conformer policy, optimise-before, the limit, the radius scale -- stored as codes, never labels) and `geometry_preparation.py` (a relaxed COPY of a geometry, and the lowest-energy of several seeded candidates, built on the conformer provider's own optimiser and levels so nothing here can disagree with it). Also `rescoring.py` (a SECOND score for a pose already found, under Docking) and `orca_led.py` (ORCA's Local Energy Decomposition, parsed from what it actually prints) under Quantum. The `nmr_*` family named above is `nmr_database.py` (a local index of assigned experimental shifts keyed by HOSE code), `hose_codes.py`, `nmr_scaling.py`, `nmr_reference.py`, `nmr_hybrid.py` (combining predictions from different methods, per atom) and `nmr_correlation.py`. **Regulatory** â€” the `regulatory/` subpackage: `types.py` (the legal-source / machine-interpretation split), `predicates.py` (the rule language), `engine.py`, `loader.py`, `calculator.py`. It is a subpackage rather than flat modules because it is the only part of `chem` with its own data format, build step and on-disk rulesets. |
+| `openchem.chem` | The only place `rdkit`/`openbabel` are imported, and by some margin the largest package (**167 modules, counted 2026-11-11**, plus the `regulatory/` subpackage). Grouped by what they are for, since the flat listing is no longer navigable: **core** â€” `engine.py` (`ChemistryEngine`: MoleculeModel <-> RDKit Mol, canonicalization, 2D depiction including the property heat map, 3D measurement, and `formal_charge()`, the one place UI gets a chemistry-derived default without importing rdkit), `identifiers.py`, `io_backends.py`, `camera_orientation.py` (the rotation a 3D viewer camera applies, as a matrix â€” pure arithmetic with no RDKit in it, so the one transform that can be plausibly backwards is testable without a molecule or an event loop). **Structure files** â€” `structure_io.py`, `binarycif.py`, `structure_summary.py`, `molblock_summary.py` (counts and charge from a held molblock, for the Inspector dump), `structure_assembly.py`; see the pipeline section below. **Docking** â€” `docking_providers.py`, `vina_engine.py`, `pose_analysis.py`, `pose_plausibility.py` (four distance checks on each pose, stored beside the interactions), `pose_choice.py` (the sentence under the pose table saying pose 1 is the best-scoring pose and not a verified one, and which poses the score cannot separate from it; pure), `binding_site.py`, `receptor_library.py`, `interaction_analysis.py`. **Structure coverage** â€” `coverage_hooks.py` (the hooks behind `CalculatorDefinition.preflight`: each calls its calculator's own refusal function and says covered, covered with a limit, or certain to refuse, so a row can say so before a run; design in `docs/STRUCTURE_COVERAGE_DESIGN.md`). **Quantum/spectroscopy** â€” `orca_engine.py`, `proton_affinity.py` (the chemistry of the proton-affinity and gas-basicity calculation, ported from the benchmark that measured it: scope check, structures and ORCA input, output reader, symmetry-number override and the selection of PA and GB with the site table; no engine, the run is a later stage), `bond_dissociation.py` (the chemistry of the X-H bond dissociation enthalpy calculation, ported from the two benchmarks that measured it: scope, the bond classes, the parent's conformers and the radical starts made from them, the radical-skeleton check, the bond enthalpy from the lowest structure of each species and the measured error stated beside it; no engine, the run is `QuantumChemistryService.request_bond_dissociation`), `quantum_run_request.py` (every rule for whether a molecule may be run on ORCA as asked, with what, and what the service is handed: the Quantum Chemistry panel's Run button reads its widgets into a `RunChoice` and calls `prepare_run`, and an assistant's card is to call the same function, so the two cannot disagree; no widget, no event), `psi4_engine.py` (Psi4 as a second engine for single points and optimizations: the functional mapped by name through a table checked against ORCA, because the same label is not the same functional; `docs/PSI4_ENGINE_DESIGN.md`), `xtb_engine.py` (xtb, GFN2/GFN1-xTB, as a third engine for single points, optimizations and frequency jobs; registered with the service and offered by the Engine box when `xtb/executable_path` is set, with a locate-only External Tools tab and its own method presets (`QuantumEngineProvider.method_basis_presets`). The charge, spin and job travel in a header comment on the inputâ€™s first line because `command_args` is not handed them, the geometry is a Turbomole block because xtb refuses a `.inp` name, the electron count is checked because xtb accepts an impossible one, and a run is judged from stdout only; `docs/EXTERNAL_TOOL_CANDIDATES.md`), the `nmr_*` family (database lookup, HOSE codes, scaling, TMS referencing, the lookup+ORCA hybrid, correlation, signals), `huckel.py`, `electronic_properties.py`, `dipole.py`, `fukui.py` (condensed Fukui functions from the Hirshfeld charges of a molecule's neutral, cation and anion: pure arithmetic with no ORCA in it, which refuses a state whose charges do not sum to that state's charge; `orca_engine.py` supplies the charges), `fukui_plan.py` (which ORCA jobs a Fukui run has and which finished one it reads: an anion's N+1 state is a dianion, written last so that its failure costs f+ and not f-; the extra SCF starts an anionic state gets at a basis with diffuse functions and the choice of the lowest solution, and the hole starts of the N-1 state that look for other states of the cation; pure), `fukui_states.py` (which state of the cation f- is read from: the lowest of the N-1 jobs, a degenerate level averaged, the states within 0.5 eV reported as competing; pure), `boltzmann.py`, `tautomer_conformers.py` (the conformer pool behind one stereo class of one tautomer: seeded ETKDG, a force-field prefilter, the project's own distinct-conformer prune, a top-K or capped selection, and a recipe-based identity) and `tautomer_nmr.py` (tautomer NMR, P5: which stored tautomer geometries NMR is run on and which conformers of a tautomer belong in one average -- the part that needs no ORCA; the run itself is in `services/quantum_chemistry_service.py`) and `tautomer_distribution.py` (candidate generation, conformer-search policy, 3D embedding and incomplete-aware Boltzmann combination for the real tautomer-distribution feature -- builds on `boltzmann.py`'s own `boltzmann_weights`, never reimplements it; the QC orchestration that runs the actual ORCA jobs lives in `services/quantum_chemistry_service.py`), `nmr_measured.py` (a MEASURED NMR spectrum read from JCAMP-DX, as an immutable record with its provenance and a hash of the original bytes -- never merged into a prediction, and scaling is view state, not data) and `nmr_export.py` (a predicted spectrum written as JCAMP-DX or an SD file, read from the signals and the viewer's parameters and labelled predicted), `tautomer_ranking.py` (RDKit's own heuristic tautomer preference score, competition-ranked with ties kept as ties, and its four-valued cross-check against ORCA -- a heuristic, never an energy or a probability, so nothing in it may feed a population or the validation gate), `tautomer_validation.py` (the PREREGISTERED validation of the tautomer-distribution model: its criteria and reference values are data in `data/tautomer_validation.json`, a closed schema frozen before any number was computed and pinned by hash, and this module is the comparison -- tautomer-level, rebaselined to the reference's own zero, pairwise tie-aware ranking and a per-system MAE AND maximum-error gate -- as pure functions; the ORCA half is `tools/tautomer_validation.py`, which drives the application's own path), `ir_export.py` (a predicted IR spectrum written as a labelled JCAMP-DX PEAK TABLE -- positions and integrated intensities with no lineshape, the same decision the IR plot makes, and not readable by this application's own overlay import, which refuses peak tables by design), `vibrational_modes.py` (normal-mode character by internal-coordinate decomposition), `mode_animation.py`, `orca_surfaces.py` + `cube.py` (driving `orca_plot` and reading Gaussian cubes into the existing `ScalarField`), and `jcamp.py` + `spectrum_overlay.py` (reading a measured spectrum and reconciling it with a computed one). **Calculators** â€” `descriptor_providers.py` plus the per-topic modules it registers (`topology_analysis`, `geometry_analysis`, `surface_analysis`, `elemental_analysis`, `steric`, `substructure`, `structure_generators`, `markush`, `logd`, `ph_curves`, `pka_sites`, `pka_species_ladder`, `mpo_scores`, `bbb_stereo`, `scalar_field`, `alignment`, `molecular_dynamics`, `calculator_options`), and `components.py` (WHICH components of a drawing each calculator is handed -- the one place a `CalculatorScope` is applied, so Properties, Batch and the 3D overlay cannot select differently: a compound property on the ChEMBL parent, a description of the drawing on the whole of it, and a coded refusal when a salt has no single parent), `salt_mode_a.py` (Mode A from four molecules: two parent neutrals and two product ions, with domain refusals; no UI), `salt_ionization.py` (fully specified ionization: a site transform moves hydrogen count and formal charge together, net charge alone is refused, and several microspecies at one charge are listed rather than picked; no UI), `ionic_species.py` (a small cited ion catalog from `data/ionic_species.json`; structures only, no pKa numbers; no UI), `salt_components.py` (Mode B analysis of a disconnected drawing: graph identity, drawn counts, a diagnostic theoretical ratio, and no silent rewrite of an unbalanced drawing; no UI), `route_ranking.py` (the order a plan's routes are shown in: the PaRoutes route score, equal scores sharing a rank, then the planner's own score; pure, and held to the benchmark's own ranker by `tests/test_synthesis_route_ranking.py`), and `route_validation.py` (what can and cannot be checked about one planned route, as separate outcomes on the `ValidationReport` and never one pass/fail: molecules parse, each step's reaction parses and its sides are the molecules the step connects, atom mapping complete/partial/absent, atom conservation only where the mapping is complete and `not_assessable` otherwise, stock, and what the planner did not supply; nothing is repaired or invented; moved from the spike's `benchmarks/synthesis/route_validator.py`, which the frozen quality benchmark still runs and a test holds it equal to), `reaction_depiction.py` (one step of a planned route drawn as an SVG, reactants then arrow then product, from the planner's PLAIN molecules and never from its mapped reaction, so no atom-map number is printed beside an atom; raises `DepictionError` naming the molecule it cannot read, and the panel shows a sentence in its place), `synthesis_gate.py` (the regulatory gate on synthesis planning: one decision about the TARGET before any process starts, `allowed`, `refused` on a CWC Schedule 1 match or `unscreened`, from its OWN engine built from the shipped rulesets only and failing closed, plus alerts on the molecules of a planned route from the wider rulesets; the decision types are `domain/synthesis_gate.py`). **Sidecars** â€” `pka_providers.py`/`pka_runner.py` and `admet_providers.py`/`admet_runner.py`, each a pair where the `_runner` is executed BY the sidecar's own interpreter and imports nothing from `openchem`. `pka_worker.py` keeps ONE pkasolver sidecar warm between structures (a single owner thread over a request queue, `pka_runner.py --serve` as the child, idle expiry, killed on timeout, an idempotent `shutdown_worker()` wired to `aboutToQuit`): it removes the ~3 s model load a fresh process paid per new structure, while a structure already seen is still answered from `pka_providers`' own cache without reaching it, and `use_cache=False` still runs a fresh one-shot process. `aizynth_planner.py`/`aizynth_runner.py` are a third such pair for the synthesis helper, with one difference: the child runs in the USER'S OWN planner environment (AiZynthFinder needs Python 3.10 to 3.12 and `numpy<2`), never in OpenChem's and never imported into it; `aizynth_runner.py` takes one JSON request on stdin and writes one JSON document on stdout, checks every named model, template and stock file before the library loads, and is handed to that interpreter as a path, while `aizynth_planner.py` starts it with an argument array and `-I`, bounds its output and wall clock, kills it on cancel, types every failure, and turns the document into a `RouteSet` (`domain/synthesis_route.py`). **Naming** â€” `naming_providers.py` (structure <-> name across PubChem, the vendored engine, and OPSIN, each result labelled with its source and whether it is `exact`, `derived` or `parsed`) and `structure_annotation.py`, which takes the SECOND return value the naming engine always had: ring systems, functional groups, stereocentres and atom numbering, as plain atom-indexed data no vendor type escapes from, plus `atom_numbering.py` (the numbers the 2D editor draws beside the atoms: the drawing's own 1-based positions, or the engine's IUPAC locants -- and the STATUS LINE that keeps "numbered nothing" apart from "could not be numbered", since both draw an empty canvas) and `feature_vocabulary.py` (vocabulary v2's ontology -- what each feature IS, cited to the Gold Book by page, with its roles, charge states and relations -- written before any pattern; see "A feature is detected once" below) and `structural_features.py` (its detector: one SMARTS spec per feature with atom ROLES carried as map numbers, the charge state measured off the drawing, and the relation resolution and per-view projections every consumer reads). **Substances and bonding** â€” `substance.py` (what a structure IS rather than what it contains: molecule / ion / ionic salt / coordination / organometallic / mixture, each with its evidence, and a REFUSAL with its reason when the graph does not decide â€” `[Na+].[Cl-].[K+].[Br-]` could be NaCl+KBr or NaBr+KCl and nothing in the drawing says which; it also names the coordination polyhedron, but only from a real 3D conformer and only as an RMS deviation over EVERY donor-metal-donor angle against a reference with the same donor count -- the donor count never decides on its own, and the 10-degree tolerance is bounded below by the tris-chelate octahedra it must accept and above by the closest pair of references it must not match together), `organometallic_adapter.py` (**the only file that touches the vendored namer's perception**, deliberately, so that when that engine changes one file needs repairing rather than four), `lattice_energy.py` (Kapustinskii from the Shannon six-coordinate radii in `data/ionic_radii.json`; refuses polyatomic ions by name because they need a thermochemical radius instead), `nuclides.py` (NUBASE2020 as a read model, 5,684 nuclear states keyed on a `NuclideKey(z, a, state_index)` -- a TYPE rather than a bare tuple, because it is the identity contract carried through the chart, the click and the write refusal, and three places reassembling `(z, a, i)` by hand is where a click starts landing on the wrong state; half-lives in seconds with an eight-state qualifier vocabulary, because a bound, an estimate and a measurement must not render alike), `decay.py` (the decay-mode GRAMMAR rather than a 45-entry lookup, so a mode NUBASE adds later parses without a code change, plus the chain walk, whose every leaf states the reason it is one -- three PHYSICAL reasons and a fourth that is deliberately not physical, since `underspecified` describes the DATA rather than the nucleus and folding it into `unfollowable` would tell a reader no daughter exists when one does; and `DaughterProvenance`, because NUBASE names no daughter STATE, so drawing a chain at all means choosing one and every edge records whether it did), `decay_svg.py` (that chain on the chart of the nuclides -- (Z, N) determines the CELL and the state index chooses a slot within it, with the row pitch growing so a stack cannot reach the row below; an assumed edge is DASHED and the legend explains the dash, because a provenance that exists while failing to protect interpretation is worse than none), `isotopes.py` (writing a mass number onto a molblock; the element is DERIVED from the atom index and never passed in, which makes "apply C-13 to every oxygen" unexpressible rather than merely validated -- and `IsotopeRefusal` is a VALUE with generated text so `if "isomer" in message` never becomes application logic, since a molfile records a mass number with no place for a nuclear state and **the refusal is the feature**), `electron_shells.py` (an atom's configuration as `(n, l, occupancy)` triples â€” **the configuration string is an OUTPUT, never the state**, because taking an electron off the end of the displayed string is wrong for exactly the ions people try first: Fe's 4s empties before 3d though it filled after). **Crystallography** â€” `cif.py` (a small-molecule/mineral CIF reader, **separate from `binarycif.py`**, which is protein-oriented and reads neither crystal symmetry nor site occupancy â€” the overlap is "both are text with loops in"), `space_groups.py` (resolving a CIF's space-group SYMBOL to the operations it stands for, which is the fallback when the file lists none -- and `Crystal.symmetry_source` records which of the two answered, because a cell that was never expanded still has a formula and a density and every one of them is wrong), `crystal_analysis.py` (density, coordination shells under explicit periodic images, and the scene a viewer draws; a `Neighbour` carries the position of the IMAGE that is close, not the asymmetric-unit atom's, which is what lets `describe_site` answer a click with the same geometry classifier the molecular path uses), `crystal_report.py` (the facts, and the list of molecular calculators that do not apply -- derived from each calculator's own `applies_to` declaration, whose default is molecule-only, rather than from a blocklist of category names that had rotted in both directions), `powder_xrd.py` (the calculated pattern that report carries: d-spacings from the reciprocal metric tensor, absences from the structure's own symmetry operations rather than a table of extinction conditions), and `periodic_charges.py` (EQeq partial charges for a cell -- **the only calculation here about a periodic solid**, reached through `crystal_report.py` because a `CalculationRequest` cannot name a crystal; see the settled Known TODO)). **Batch** â€” `result_reduction.py` (every result shape collapsed to table cells), `analytics.py`, `clustering.py`. **Charges** â€” `charge_equilibration.py` (RappÃ©â€“Goddard QEq, Bultinck EEM and Ionescu 2013 EEM, all geometry-dependent, each refusing rather than approximating: QEq declines a non-convergent or final-bound-active solution by name, Ionescu a runaway charge; Ionescu's two shipped models live in `data/eem_ionescu2013.json`, built from the Table S1 test fixture by `tools/build_ionescu_parameters.py` and never edited by hand), `typed_eem.py` (two further EEM models typed by element and highest bond order -- JirouÅ¡kovÃ¡ 2009 B3LYP/6-31G* Merz-Kollman and NEEMP 2016 Ccd2016 NPA -- each its own model with its own kappa, never combined; pure numpy on element symbols, coordinates, a Kekule bond list and a net charge, refusing a type a model lacks by name and naming the other model when it has it; data in `data/eem_second_models.json` built by `tools/build_eem_second_models.py`; the plan and its checks are `benchmarks/charges/models/eem_second_models_preregistration.md`; reachable as methods of the 3D partial-charge calculator, NEEMP's for any molecule it can type and JirouÅ¡kovÃ¡'s for molecules with Cl, Br or S only), `resonance_forms.py` (the resonance forms of a molecule for those typed EEM models -- RDKit's own enumeration of the kekulised molecule, only the forms with the smallest sum of formal charges kept, a cap that makes the average refuse instead of guess -- and `typed_eem_for_molecule`, the one call that charges a molecule with the `resonance` option `averaged` (default), `as_drawn` or `refuse`; design `benchmarks/charges/models/eem_resonance_typing_design.md`), `geometry_charges.py` (those models ON the stored conformer, which is what makes them different answers from the drawing-based ones) and `protonation_geometry.py` (the dominant ionisation state at a pH on a conformer, with the geometry carried across rather than rebuilt â€” heavy atoms and retained hydrogens stay bit-identical and only the new hydrogens move), plus `result_structure.py` (which structure a per-atom result's indices refer to â€” the one it carries, for a result computed on a structure nothing stores, such as that pH state â€” and so which one a view must draw; kept apart from `atom_identity.py`, which answers the different question of which atom of one structure is which atom of another). `periodic_charges.py` is under Crystallography, because a crystal is not a molecule. **Lewis structures** â€” a deliberately layered family, and the layering is the point: `lewis_diagram.py` (what a Lewis structure SAYS, as data â€” no chemistry, no drawing, no Qt), `lewis_builder.py` (**the only RDKit in the feature**), `lewis_layout.py` (which 2D layout to draw it from), `lewis_svg.py` (the picture â€” no RDKit, no Qt, no chemistry), plus `lewis.py` (Lewis acid/base SITE analysis, offline from the structure alone) and `lewis_adduct.py` (whether a given acid binds a given base, and how strongly, from Dragoâ€“Wayland E and C parameters) and, for the first recipe (`domain/lewis_pairing.py`), `lewis_pairing_eval.py` (that pairing evaluated over stored quantum-chemistry runs into a `RecipeRun`) and `recipe_host.py` (the one chemistry question a recipe asks of a stored run: does its 3D input still describe the drawing). The two senses of "Lewis" living in one package is a naming collision worth knowing about: the first four are the electron-dot diagram, the last two are acid/base chemistry. **Group-contribution and empirical properties** â€” `group_contribution.py` (the mechanics two methods share, and nothing more), `joback.py`, `hansen.py` (Stefanisâ€“Panayiotou), `gutmann.py` (donor and acceptor numbers from the classical tables), `energetics.py` (oxygen balance and detonation), `aromaticity.py` (HOMA per ring), `conceptual_dft.py` (hardness, softness, electrophilicity). **Three of these ship under a narrower claim than their output suggests**, and their docstrings say so in their own first lines: `hlb.py` ("and where it means anything"), `tsei.py` ("under that name only") and `polarizability_miller.py` ("both methods, with the traps") â€” see SCIENTIFIC_LIMITATIONS' "Numbers whose applicability is narrower than their output". **Elements and the periodic table** â€” `element_reference.py` (one element's facts, assembled from the three places they live), `element_palettes.py` (**what a cell's colour is allowed to MEAN**, which is a claim rather than a style choice), `electron_layout.py` (where a lone pair may be drawn, as rules rather than a placement) and `electron_overlay.py` (what the canvas overlay is TOLD, and nothing about where it draws). **Structure handling** â€” `structure_templates.py` (shipped complete-molecule catalogs as 2D molblocks and right-side placement for the Template Library; no dummy-atom fragments), `structure_check.py` (the analysis engine: issues, checkers and their registry), `structure_clipboard.py` (reading a structure out of whatever happens to be on the clipboard), `stereochemistry.py` (what a geometry DID to a structure's stereochemistry), `conformer_providers.py` and `projection_geometry.py` (shape from the van der Waals surface: volume, area, extent), with the layers under it: `disc_union.py` (the EXACT area of a union of discs, which is what a molecule's shadow is -- exact because a minimum found over orientations needs an area that is smooth in the direction, and a grid's error is not), `projection_search.py` (the smallest and largest shadow over every orientation, the circle round it and the molecule's size along it; the area at each orientation is exact and the extreme is searched, and it says how many orientations it looked at) and `sasa.py` (accessible surface area by Shrake-Rupley on a deterministic point set, 0.3% from a dense reference; it replaced `rdFreeSASA`, which was given zero radii by its own classifier and read half the true area -- see `surface_analysis.py`'s docstring) and `vdw_radii.py` (Bondi's own radii, extended by Mantina et al.: the one table behind the accessible surface, van der Waals volume, projections, Geometry and steric bulk; RDKit's table, which is Batsanov's and not Bondi's, is only the fallback for elements neither covers -- `VDW_RADII_ASSESSMENT.md`). `hbond_sites.py` (the hydrogen-bond site table: RDKit's donor and acceptor definitions written out as patterns, because RDKit exposes a count and no atoms, held to that count by a test over a corpus in two forms -- the acceptor pattern is RDKit's own with the aromatic nitrogen restricted to two connections, which the corpus forced -- and, at a pH, each role carried back to its drawing atom through `pka_providers.heavy_correspondence`), `torsions.py` (the torsion table: which bonds the Rotatable Bonds count counts, written out as a pattern because RDKit exposes no list, held to that count by a test over a corpus, and the dihedral about each) and `ionisable_sites.py` (acid or base from the charge of pkasolver's own proton-holding state, and the Henderson-Hasselbalch fraction ionised for one site; it reads the predictions `pKa` keeps and asks the sidecar for nothing more) sit with the calculators they serve, as does `geometry_options.py` (the Geometry calculator's options, declared once: energy unit, conformer policy, optimise-before, the limit, the radius scale -- stored as codes, never labels) and `geometry_preparation.py` (a relaxed COPY of a geometry, and the lowest-energy of several seeded candidates, built on the conformer provider's own optimiser and levels so nothing here can disagree with it). Also `rescoring.py` (a SECOND score for a pose already found, under Docking) and `orca_led.py` (ORCA's Local Energy Decomposition, parsed from what it actually prints) under Quantum. The `nmr_*` family named above is `nmr_database.py` (a local index of assigned experimental shifts keyed by HOSE code), `hose_codes.py`, `nmr_scaling.py`, `nmr_reference.py`, `nmr_hybrid.py` (combining predictions from different methods, per atom) and `nmr_correlation.py`. **Regulatory** â€” the `regulatory/` subpackage: `types.py` (the legal-source / machine-interpretation split), `predicates.py` (the rule language), `engine.py`, `loader.py`, `calculator.py`. It is a subpackage rather than flat modules because it is the only part of `chem` with its own data format, build step and on-disk rulesets. |
 | `openchem.services` | `DescriptorService`, `ConformerService`, `MeasurementService`, `ImportService`, `ExportService`, `ProjectService`, `DockingService`, `QuantumChemistryService`, plus `ProgressHandle` for cancellable/progress-reporting long operations. All but `QuantumChemistryService` own `QThreadPool` execution and publish events â€” `QuantumChemistryService` is the one exception (see design decisions below). **Set-of-molecules services:** `BatchService` (runs chosen descriptors/calculators across a whole project as ONE pooled task, so "molecule 47 of 200" is reportable and one cancel flag stops it), `ScreeningService` (queues N ligands through `DockingService` one at a time rather than starting N Vina processes; it advances by *listening* for each job's terminal event, so no thread blocks), `SpatialOverlayService` (recomputes a result's geometry for the conformer a viewer is actually showing â€” one atomic job per cell, per-cell tokens, latest-wins bounded at one running plus one pending; it recomputes rather than transforming a stored annotation, so no display-alignment matrix can be applied backwards), and `TableExportService` (`BatchTable` -> CSV/Markdown; deliberately not folded into `ExportService`, which is constructed with a `ChemistryEngine` and dispatches by chemical format â€” there is no chemical format whose subject is a table), and `SynthesisPlanningService` (a planning request for ONE molecule: the regulatory gate runs first in its one `request_plan` method and a refusal or an inability to screen starts no process; the target and the planner setting are captured before the worker starts; one slot per molecule and one search at a time on a pool of its own; cancel and application quit kill the planner child; the finished `RouteSet` is stored per molecule for the session and read back bound to the structure it was made for), with the planner run as a child process in a separate Python (`chem/aizynth_planner.py`; `services/aizynth_setup.py` builds that sidecar, or Browse points at one already installed). |
 | `openchem.commands` | `QUndoCommand` subclasses wrapping service calls, giving undo/redo for structure edits, conformer generation, docking results, quantum-chemistry conformers, and project operations from day one. |
 | `openchem.plugins` | `interfaces.py` (`Plugin`, `DescriptorProvider`, `ConformerProvider`, `DockingProvider`, `QuantumEngineProvider`, `FactProvider`, `PanelProvider`, `MenuProvider`, `Importer`, `Exporter`), `manifest.py` (`PluginManifest` + dependency topological sort), `context.py` (`PluginContext`, including the `context.secrets` namespace backed by the OS keychain via `keyring`, and `context.molecules`/`context.docking`/`context.quantum_chemistry`), `ui_registry.py` (`UIRegistry` protocol), `manager.py` (`PluginManager` â€” discovery, transactional load/unload/reload, hot-reload watcher). See `PLUGIN_SDK.md`. |
 | `openchem.app` | Composition: `MainWindow`, typed `Settings`, `SessionManager`, structured logging setup. `MainWindow` implements the `UIRegistry` protocol and constructs `PluginManager` at the end of `__init__`. `inspector_dump.py`, `nmr_dump.py` and `results_dump.py` are the read-only JSON dumps used by the drive `inspect_report`, `nmr_panes` and `results` steps. |
 | `openchem.ui` | Widgets and dock panels. `EditorBackend`/`KetcherEditorBackend` (2D, `resources/ketcher/dist/`), `ViewerBackend`/`Mol3DViewerBackend` (3D small molecules, `resources/viewer3d/`, 3Dmol.js), and `ViewerBackend`/`MolStarViewerBackend` (macromolecules/crystallography, `resources/molstar/`, Mol*) are interface + implementation pairs â€” new content types get a sibling implementation, or a new optional capability method on the shared `ViewerBackend` base, without touching chemistry, services, or commands. `panels/docking_panel.py` and `panels/quantum_chemistry_panel.py` are core (not plugin) panels, same tier as `PropertyPanel`. Four widgets **compute nothing and are handed already-decided data**, which is what keeps `ui/` free of the chemistry layer: `widgets/atom_diagram.py` (shell rings with a p/n nucleus, and orbital boxes with spin arrows, drawn from `chem/electron_shells.py`'s triples) and `widgets/zoomable_svg_view.py` (an SVG at its own size in a scroll area, shared by the Lewis dialog and the decay chart -- extracted rather than copied, with the dialog keeping its whole surface as delegations so the extraction is behaviour-neutral by construction) and `widgets/substance_card.py` (the Properties panel's identity header, whose shape follows what the structure IS â€” a salt shows its formula unit and its ions, a complex its metal and two named counts) and `widgets/stick_chart_widget.py` (a declared `ChartAnnotation`, drawn and never edited: it refuses a malformed annotation rather than repairing one, and renormalises, reorders and relabels nothing â€” the axis mechanics live in `widgets/plot_axis.py`, extracted for it rather than generalised out of the NMR and IR spectrum widgets, which know three chemistries between them and are deliberately left alone). `widgets/results_view.py` is the results reader, and it is a WIDGET rather than a window so that one class serves both formats it appears in: a dock in the `analysis` group that follows the selection, and the pop-out window `PopOutHost` MOVES it into. It replaced a per-molecule dialog, which could not follow a selection because a dialog is opened, read and closed; every "Details..." button reaches this one surface, focused by `report_id`, rather than a second implementation of it. **The help-contract layer lives here too and knows no chemistry**: `widgets/help_tooltip.py` is the metadata (a `HelpTooltip` is constructible with no `QApplication`, which is what makes it unit-testable), `widgets/tooltip_inventory.py` is the ONE definition of which controls owe the user an explanation, and `app/menu_help.py` carries the menu bar's contracts so `main_window.py` keeps only the job of building menus. `tests/test_tooltip_coverage.py` and `tools/list_tooltips.py` both consume `iter_documentable_controls` and neither walks the tree itself â€” two implementations of "all interactive controls" would drift, which this repository has paid for four times. |
 | `openchem.cli` | **The headless command line** (`openchem-cli`, or `python -m openchem.cli`): the registry's calculators asked from a script or an agent, with **no window, no event loop and no Qt**. `calculation.py` is the Qt-free twin of `DescriptorService`'s `_CalculationTask._run` -- resolve the input structure, compute, merge the geometry and parameters into the result's provenance, map a `CalculationRefusal` -- minus the events and the thread pool, which is all that task adds; `serialise.py` writes any result as plain data generically, so no field is dropped by a per-type writer; `commands.py` is the command table, the parser and `main`. Three commands, all `pure_read`: `commands --json` (the manifest, flags read from the parser), `calculators` (every registered calculator with its parameters, stage and whether this tool can run it) and `calculate --smiles S --calculator ID [--param NAME=VALUE]... [--conformer]`. **Status is `status_of`'s word, never "it did not raise":** with no sidecar configured `admet_ml` returns an `AlertResult` and `pka` a `ReportResult`, both saying "not configured", and `needs_input` exits 2, `needs_setup` exits 3, a limit or fault exits 1. The command line does not read or write the settings store (`QSettings` is the Windows registry), so the sidecar calculators run unconfigured and say so. See "The command line" below. |
 | `openchem.vendor` | Third-party code owned in-tree rather than depended on. Two entries: `iupac_namer`, a deterministic IUPAC nomenclature engine (structure -> name), reached only through `chem/naming_providers.py`; and `chembl_structure_pipeline`, ChEMBL's GetParent rule and its salt and solvent lists, verbatim, reached only through `chem/components.py`. Nothing else imports either. See below and `vendor/VENDORING.md`. |
 | `plugins/ai_assistant` | Bundled first-party plugin (loads by default, unlike `examples/`). `providers.py` (`AIProvider` ABC, `AnthropicProvider`, `OpenAICompatibleProvider` covering OpenAI + local Ollama, `ClaudeCLIProvider` driving a locally-logged-in `claude` CLI headless for claude.ai subscription users with no separate API key), `context_builder.py` (`MoleculeContextCache` â€” accumulates molecule identity/descriptors purely from subscribed events, same pattern as `PropertyPanel`), `panel.py` (chat UI), `plugin.py` (registers the panel + two menu-driven canned prompts). Kept out of core `openchem` so the `anthropic`/`openai` SDKs stay optional (`pyproject.toml`'s `ai` extra) â€” `ClaudeCLIProvider` needs neither, just `claude` on PATH. |
 | `plugins/database_search` | Bundled plugin: `DatabaseSearchProvider` ABC (`PubChemProvider`, `ChEMBLProvider`), search results import as a new molecule via `context.molecules.add(...)`. `requests` stays optional (`network` extra). |
 | `plugins/synthesis_planner` | Bundled plugin (the fourth): the synthesis panel (`panel.py`), the words it shows (`route_text.py`, pure, tested without Qt) and a Plan Synthesis menu entry. It reaches the planner only through `context.synthesis` (read the selected molecule and a plan, ask what the planner's configuration offers, draw a step) and `context.synthesis_requests` (start, cancel, choose the policy, stock or filter), two objects over one window-side host (`app/synthesis_host.py`) so a tool can be handed the reading one alone; every start goes through `SynthesisPlanningService.request_plan`, where the regulatory gate runs first. The planner's configuration is read on a worker when the panel is shown, never on the GUI thread. See `docs/SYNTHESIS_HELPER_DESIGN.md`. |
diff --git a/docs/README.md b/docs/README.md
index e90e196a..1d1cc73a 100644
--- a/docs/README.md
+++ b/docs/README.md
@@ -32,21 +32,21 @@ so they are listed here rather than left for somebody to find:
 | [SELF_HOSTED_RUNNER.md](SELF_HOSTED_RUNNER.md) | The benchmarks that cannot run on a hosted runner, what the self-hosted one needs, and the security position stated plainly |
 
 **Two of those are dated records and say so in their own first lines.** A
 measurement is not a claim about today, and re-reading one as though it were is
 how this project's own documentation has gone stale before.
 
 **Design records, references and maintainers' notes.** These were in the directory and not in this index:
 
 | | |
 |---|---|
-| [SALT_COMPOSITION_DESIGN.md](SALT_COMPOSITION_DESIGN.md) | Architecture contract for a two-ion salt composition engine (slice 1â€“2 library code, no UI): charge balance is not a salt, `substance.py` is an adapter, pKa is evidence |
+| [SALT_COMPOSITION_DESIGN.md](SALT_COMPOSITION_DESIGN.md) | Architecture contract for a two-ion salt composition engine (slice 1â€“3 library code, no UI): charge balance is not a salt, `substance.py` is an adapter, pKa is evidence |
 | [DERIVED_SCORES_DESIGN.md](DERIVED_SCORES_DESIGN.md) | Design record for derived scores, slice by slice: why a score is a projection and not a result, the approved outputs, what was measured, and the geometry decisions |
 | [RECIPES_DESIGN.md](RECIPES_DESIGN.md) | Design record for recipes (typed dependencies between calculators) and the Lewis pairing, with the preregistered gate |
 | [AI_CALCULATION_BRIDGE.md](AI_CALCULATION_BRIDGE.md) | Design record for the assistant's calculator bridge: the execution policy, the handle, the frozen turn and the approval flow |
 | [TAUTOMER_NMR_DESIGN.md](TAUTOMER_NMR_DESIGN.md) | Design for tautomer peaks on the NMR spectrum |
 | [CALCULATOR_REFERENCE.md](CALCULATOR_REFERENCE.md) | The generated reference for every calculator: options, limits and the evidence behind each (built from the registry; do not edit) |
 | [CALCULATOR_MATURITY.md](CALCULATOR_MATURITY.md) | Maintainer's document: calculator stages, default visibility, and how a calculator is classified or promoted |
 | [CALCULATOR_GAP_REPORT.md](CALCULATOR_GAP_REPORT.md) | Which calculators a user of a reference-editor-like workstation might look for that OpenChem does not have, and an order to build them in |
 | [GEOMETRY_DEFINITIONS_CHECKLIST.md](GEOMETRY_DEFINITIONS_CHECKLIST.md) | The reference editor's Geometrical Descriptors, definition by definition, written before the geometry calculators were merged |
 | [PANEL_FEATURE_INVENTORY.md](PANEL_FEATURE_INVENTORY.md) | The inventory behind "no feature may be lost" for the Batch, Docking, Quantum Chemistry and 3D Alignment panels |
 | [LESSONS.md](LESSONS.md) | The lessons moved out of `CLAUDE.md` so they are not loaded on every message |
diff --git a/docs/ROADMAP.md b/docs/ROADMAP.md
index 5f8313cf..0babf492 100644
--- a/docs/ROADMAP.md
+++ b/docs/ROADMAP.md
@@ -2367,23 +2367,25 @@ struck through and marked SHIPPED here, never deleted.
   that order (generation, and ORCA's optimized geometry, which copies it), so
   the defect is reachable only through a plugin conformer provider or a project
   file written elsewhere. Latent, and tracked in Known TODOs.
 
 ## What is left, and why each one is left
 
 Nothing here is simply unstarted â€” each is blocked on something nameable,
 and three were checked again recently rather than taken on trust.
 
 - **Salt composition engine (recorded 2026-11-10; slice 1 in master,
-  slice 2 Mode A).** Slice 1 shipped `balance_two` and Mode B drawing
-  analysis; slice 2 adds Mode A for two molecular neutrals (still library-only,
-  no panel). Charge-valid two-ion stoichiometry from identified ionic species,
+  slice 2 Mode A, slice 3 ionization).** Slice 1 shipped `balance_two` and
+  Mode B drawing analysis; slice 2 adds Mode A for two molecular neutrals;
+  slice 3 adds fully specified ionization, a small cited ion catalog, and
+  `pka_compatible` as named-step evidence (still library-only, no panel; Mode C
+  is not authorized). Charge-valid two-ion stoichiometry from identified ionic species,
   with proton-transfer conservation and independent evidence (`charge_valid` is
   not an isolable salt). `substance.py` is an adapter, not the engine; COD
   search, ion-pair 3D, hydrates as first-class features, pharmaceutical
   acceptability and `balance_many` stay out. Contract:
   `docs/SALT_COMPOSITION_DESIGN.md`.
 
 - **Peptide sequence building and polymer S-groups (recorded 2026-11-10).** The
   structure template library ships complete molecules only. Expanding
   `Ala-Glu-Gly` / `AEG` into an atomistic peptide, and repeating
   polymer S-groups as in the reference editor, wait on a measured sequence builder and on molfile S-group
diff --git a/docs/SALT_COMPOSITION_DESIGN.md b/docs/SALT_COMPOSITION_DESIGN.md
index bced42d6..172d96ea 100644
--- a/docs/SALT_COMPOSITION_DESIGN.md
+++ b/docs/SALT_COMPOSITION_DESIGN.md
@@ -1,14 +1,15 @@
 # Salt composition engine: design
 
 **Status: slice 1 (`balance_two`, Mode B) is in master; slice 2 adds Mode A
-for two molecular neutrals; Mode C and UI still not authorized by this work.**
+for two molecular neutrals; slice 3 adds ionization, a cited ion catalog, and
+pKa evidence; Mode C and UI still not authorized by this work.**
 This note is the scientific and module-boundary contract. It is not an
 implementation plan: file names below are the intended homes when code exists,
 not a commitment to write them in this change. No calculator is registered, no
 UI is specified beyond "later, beside the pKa view", and a charge-valid
 composition is never an isolable salt.
 
 This document lives on branch `cursor/salt-composition-design`, created from
 fetched `origin/master` in an isolated worktree. It was not written on
 `claude/nl005-close-validator`. Implementation, if it happens, is a later
 session with its own plan after this file is accepted.
diff --git a/docs/SOURCES.md b/docs/SOURCES.md
index 5db9e57a..8932b3f0 100644
--- a/docs/SOURCES.md
+++ b/docs/SOURCES.md
@@ -1,12 +1,12 @@
 <!-- GENERATED FROM docs/sources.toml -- do not edit -->
-<!-- SOURCE SHA256: 58e228a9cc51be3be6469ce26a4583f2e935c4a53f0aae22c68b6ced6245329a -->
+<!-- SOURCE SHA256: d69cf5cc8eee75b9f4420df3fced70edaff0852d5c59d922206f84f2490016fd -->
 
 # Sources
 
 Every primary source, dataset, legal text, standard and bundled library this
 project rests on, with what uses it and how far it has been checked.
 
 ## What this registry is, and the three things it cannot do
 
 It is a **provenance registry**, not a bibliography page. Each entry declares
 its kind, whether it is shipped, how far it is verified, and what points at
@@ -339,20 +339,21 @@ Title and DOI first; the `key` is what prose and code cite (`[source:key]`) and
 | Distributed data parallel coupled-cluster algorithm: Application to the 2-hydroxypyridine/2-pyridone tautomerism | [10.1002/jcc.540141204](https://doi.org/10.1002/jcc.540141204) | [`rendell1993`](#rendell1993) | literature | reference only | unverified |
 | An efficient and near linear scaling pair natural orbital based local coupled cluster method | [10.1063/1.4773581](https://doi.org/10.1063/1.4773581) | [`riplinger2013dlpno`](#riplinger2013dlpno) | literature | reference only | citation + claim |
 | Natural triple excitations in local coupled cluster calculations with pair natural orbitals | [10.1063/1.4821834](https://doi.org/10.1063/1.4821834) | [`riplinger2013triples`](#riplinger2013triples) | literature | reference only | citation + claim |
 | Intermolecular Nonbonded Contact Distances in Organic Crystal Structures: Comparison with Distances Expected from van der Waals Radii |  | [`rowland1996`](#rowland1996) | literature | shipped | citation + claim |
 | On non-negativity of Fukui function indices | [10.1063/1.478792](https://doi.org/10.1063/1.478792) | [`roy1999`](#roy1999) | literature | shipped | citation + claim |
 | Introduction to Active Thermochemical Tables: Several 'Key' Enthalpies of Formation Revisited | [10.1021/jp047912y](https://doi.org/10.1021/jp047912y) | [`ruscic2004`](#ruscic2004) | literature | reference only | citation |
 | Active Thermochemical Tables: Sequential Bond Dissociation Enthalpies of Methane, Ethane, and Methanol and the Related Thermochemistry | [10.1021/acs.jpca.5b01346](https://doi.org/10.1021/acs.jpca.5b01346) | [`ruscic2015`](#ruscic2015) | literature | reference only | citation |
 | MetFrag relaunched: incorporating strategies beyond in silico fragmentation | [10.1186/s13321-016-0115-9](https://doi.org/10.1186/s13321-016-0115-9) | [`ruttkies2016`](#ruttkies2016) | literature | reference only | citation |
 | Computing Fukui functions without differentiating with respect to electron number. II. Calculation of condensed molecular Fukui functions | [10.1063/1.2736698](https://doi.org/10.1063/1.2736698) | [`sablon2007`](#sablon2007) | literature | shipped | citation + claim |
 | AiZynthFinder 4.0: developments based on learnings from 3 years of industrial application | [10.1186/s13321-024-00860-x](https://doi.org/10.1186/s13321-024-00860-x) | [`saigiridharan2024aizynthfinder4`](#saigiridharan2024aizynthfinder4) | literature | reference only | citation |
+| OpenChem Studio v1 salt ion catalog: named common ions as canonical SMILES for composition, not aâ€¦ |  | [`salt_ion_catalog`](#salt_ion_catalog) | dataset | shipped | citation |
 | Reversal in the Sequence of Two Highest Occupied Molecular Orbitals in the Series Thiophen, Selenophen, and Tellurophen | [10.1039/c39730000541](https://doi.org/10.1039/c39730000541) | [`schafer1973`](#schafer1973) | literature | shipped | citation + claim |
 | Optimized SQE atomic charges for peptides accessible via a web application | [10.1186/s13321-021-00528-w](https://doi.org/10.1186/s13321-021-00528-w) | [`schindler2021`](#schindler2021) | literature | reference only | citation |
 | Correction to: Optimized SQE atomic charges for peptides accessible via a web application | [10.1186/s13321-021-00531-1](https://doi.org/10.1186/s13321-021-00531-1) | [`schindler2021_correction`](#schindler2021_correction) | literature | reference only | citation |
 | Comments on Hydrophile-Lipophile Balance Systems |  | [`schott1989`](#schott1989) | literature | shipped | citation + claim |
 | Alex's local paper archive, `D:\Xaero Stuff\Documents\Sci Downloads\`. |  | [`sci_downloads_note`](#sci_downloads_note) | reference_table | reference only | citation |
 | Ab initio study of the transition states for determining the enthalpies of formation of alkyl and halogenated alkyl free radicals | [10.1039/b001350l](https://doi.org/10.1039/b001350l) | [`seetula2000`](#seetula2000) | literature | reference only | citation |
 | Kinetics of the R + HBr = RH + Br (R = CH2Br, CHBrCl or CCl3) equilibrium. Thermochemistry of the CH2Br and CHBrCl radicals | [10.1039/b210787m](https://doi.org/10.1039/b210787m) | [`seetula2003`](#seetula2003) | literature | reference only | citation + claim |
 | Kinetics of the R + HBr = RH + Br (CH3CHBr, CHBr2 or CDBr2) equilibrium. Thermochemistry of the CH3CHBr and CHBr2 radicals | [10.1016/j.chemphys.2008.04.008](https://doi.org/10.1016/j.chemphys.2008.04.008) | [`seetula2008`](#seetula2008) | literature | reference only | citation + claim |
 | Dynamic Charge Equilibration-Morse Stretch Force Field: Application to Energetics of Pure Silica Zeolites | [10.1002/jcc.10130](https://doi.org/10.1002/jcc.10130) | [`sefcik2002`](#sefcik2002) | literature | reference only | citation + claim |
 | Synthesis of metal iodates from an energetic salt | [10.1039/d0ra02250k](https://doi.org/10.1039/d0ra02250k) | [`shancita2020`](#shancita2020) | literature | shipped | citation |
@@ -8779,20 +8780,38 @@ the one rule every calculator's `CalculatorScope` follows.
 | --- | --- |
 | Identifier | <https://atct.anl.gov/Thermochemical%20Data/version%201.228/index.php> |
 | Status | reference only |
 | Verification | citation |
 | Verified | 2026-10-22 |
 | Local copy | `ATcT Thermochemical Values ver. 1.228.htm` (not checked) |
 | Used by | `src/openchem/chem/bond_dissociation.py`, `docs/explainers/thermochemistry.md`, `benchmarks/restart_v2/PREREGISTRATION.md`, `benchmarks/bde_heldout/extract_atct.py` |
 
 **Why it is reference only.** THE REFERENCE VALUES OF THE HELD-OUT BOND-DISSOCIATION ARM: `benchmarks/bde_heldout/extract_atct.py` parses the saved page (3,455 species rows, kJ/mol at 298.15 K) and combines a parent's, a radical's and the hydrogen atom's enthalpies of formation into DH298 and its uncertainty. The arithmetic was checked against the 22 bonds Blanksby and Ellison also give: ATcT minus theirs is -0.11 kcal/mol on average, within 0.2 for every reference held to 0.1 or better, beyond three combined uncertainties for one bond (propene's allylic C-H, 87.50 against 88.8). Nothing is shipped from it yet; it backs a benchmark's reference column.
 
+### salt_ion_catalog â€” OpenChem Studio v1 salt ion catalog: named common ions as canonical SMILES for composition, not aâ€¦
+
+<a id="salt_ion_catalog"></a>
+
+> OpenChem Studio v1 salt ion catalog: named common ions as canonical SMILES for composition, not a pharmaceutical list.
+
+| | |
+| --- | --- |
+| Identifier | OpenChem Studio v1 salt ion catalog |
+| Status | shipped |
+| Verification | citation |
+| Verified | 2026-11-11 |
+| Used by | `src/openchem/chem/data/ionic_species.json` |
+
+STRUCTURES ONLY. Each row is a named ion's graph and its parent, so Mode A
+workflow 2 and the catalog agree on identity. No pKa numbers. Not safety or
+acceptability. Hydrogen sulfate and sulfate are different rows.
+
 ## Legal texts
 
 ### cwc_annex_on_chemicals â€” Convention on the Prohibition of the Development, Production, Stockpiling and Use of Chemical Weapons and onâ€¦
 
 <a id="cwc_annex_on_chemicals"></a>
 
 > Convention on the Prohibition of the Development, Production, Stockpiling and Use of Chemical Weapons and on their Destruction (CWC), Annex on Chemicals, Schedules 1, 2 and 3.
 
 | | |
 | --- | --- |
diff --git a/docs/sources.toml b/docs/sources.toml
index 83a55036..5054a86f 100644
--- a/docs/sources.toml
+++ b/docs/sources.toml
@@ -9780,10 +9780,31 @@ THE Ccd2016 PARAMETER SET `CCD_gen_DE_RMSD_B3LYP_6311G_NPA.par` (Additional file
 NPA charges of CORINA-generated CCD ligands that were NOT geometry-optimised.
 Open access, read 2026-10-30 from the article page; the paper's Tables 2, 4 and 7
 are images and were NOT read, so no per-type quality number is quoted anywhere.
 The file is copied byte for byte (SHA-256 in
 `tests/fixtures/charges/neemp2016/README.md`, marked -text in .gitattributes) and
 its numbers are read as a table. The EQUATION and the typing rule are read from
 Additional file 1's solver (`src/eem.c`, `src/io.c`): B on the diagonal, kappa
 over the SDF-coordinate distance off it, the type being the element and the
 highest bond order. There is no local copy of the paper in `Sci Downloads`.
 """
+
+[[source]]
+key = "salt_ion_catalog"
+kind = "dataset"
+citation = "OpenChem Studio v1 salt ion catalog: named common ions as canonical SMILES for composition, not a pharmaceutical list."
+identifier_type = "bibliographic"
+identifier = "OpenChem Studio v1 salt ion catalog"
+status = "shipped"
+verification = "citation"
+verified_date = 2026-11-11
+used_by = ["src/openchem/chem/data/ionic_species.json"]
+note = """
+STRUCTURES ONLY. Each row is a named ion's graph and its parent, so Mode A
+workflow 2 and the catalog agree on identity. No pKa numbers. Not safety or
+acceptability. Hydrogen sulfate and sulfate are different rows.
+"""
+reason = """
+STRUCTURES ONLY. Each row is a named ion's graph and its parent, so Mode A
+workflow 2 and the catalog agree on identity. No pKa numbers. Not safety or
+acceptability. Hydrogen sulfate and sulfate are different rows.
+"""
diff --git a/docs/superpowers/plans/2026-11-11-salt-composition-slice-3.md b/docs/superpowers/plans/2026-11-11-salt-composition-slice-3.md
new file mode 100644
index 00000000..81fd38aa
--- /dev/null
+++ b/docs/superpowers/plans/2026-11-11-salt-composition-slice-3.md
@@ -0,0 +1,941 @@
+# Salt composition slice 3 Implementation Plan
+
+> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
+
+**Goal:** Ship fully specified user ionization, proton-source rules for an already-ionic counter-species, a small cited ion catalog, and `pka_compatible` as an independent evidence claim that never feeds `balance_two`.
+
+**Architecture:** Domain owns selection uniqueness, two-ion composition from supplied ions, and pKa arithmetic (opaque identities, named steps, comparable conditions). `chem/salt_ionization.py` turns a parent molecule plus a site transform into a structure whose hydrogen count and formal charge both move. `chem/ionic_species.py` loads cited JSON rows. No Mode C enumeration, no ladder adapter, no UI, no live pKa sidecar in tests.
+
+**Tech Stack:** Python 3.11+, existing `balance_two` / `compose_mode_a`, RDKit only in `chem/` and tests, pytest. Worktree: `D:\_scratch\OpenChem-Studio-salt-slice-3`. After `uv sync`, `uv run --no-sync pytest`. If that cannot import PySide6, set `PYTHONPATH` to this worktree `src` and use `D:\Random Projects\OpenChem Studio\.venv\Scripts\python.exe`.
+
+## Global Constraints
+
+- Work on `cursor/salt-composition-slice-3` in `D:\_scratch\OpenChem-Studio-salt-slice-3`, from `origin/master` after #583. Not `claude/vendoring-fork-100-squash`.
+- No UI, no calculator registry, no Mode C (no 50-cap cartesian product), no `pka_species_ladder` adapter, no CIF/COD, no ion-pair 3D, no hydrates as first-class, no `balance_many`, no NaOH neutralization path.
+- Domain must not import `rdkit`, `openbabel`, `PySide6`, or `openchem.chem`.
+- Keep pKa out of `balance_two`. Never name a claim `acid_base_supported`.
+- `pka_compatible` is optional evidence. Already-charged / supplied-ion input is **not assessed**. Missing or incomparable conditions are recorded, not guessed.
+- `pka_compatible` must name the protonation/dissociation **step that matches the proposed microspecies**. Hydrogen sulfate is not sulfuric acid's second pKa; `BH2^2+` is not the first conjugate-acid pKa of B.
+- User-selected ionization must identify a **structure**. A desired net charge alone is refused. Several structures at one charge are listed, never auto-picked.
+- Protonation/deprotonation updates **both** hydrogen count and formal charge.
+- Presence in the ion catalog is not pharmaceutical acceptability. `HSO4-` and `SO4^2-` are different rows. No DOIs in the JSON (the DOI guard sweeps `.json`).
+- Changelog is a fragment (`tools/changelog.py new`), not an edit of `CHANGELOG.md`.
+- New test files: `python tools/suite_shards.py --pin-new` with **no** `--splits=3`.
+- New `src/openchem` modules need `REACHED_BY = ("tooling: ...")` until `openchem.main` imports them.
+- New constants in a file that already uses `#:` need a `#:` block on each (see `KIND_*` on slice 2).
+- After adding a `chem/*.py` file, update `docs/ARCHITECTURE.md` chem count (165 â†’ 167 if two modules) and name each module next to `salt_mode_a.py`.
+- Tests must not call `compute_pka` / the pkasolver sidecar. Inject `PkaValue` records.
+- A charge-valid composition is never an isolable salt. `experimentally_established` stays unset.
+
+---
+
+### Task 1: Domain ionization uniqueness
+
+**Files:**
+- Modify: `src/openchem/domain/salt_stoichiometry.py`
+- Test: `tests/test_salt_stoichiometry.py`
+
+**Interfaces:**
+- Consumes: opaque identity strings (canonical SMILES from chem, treated as opaque here)
+- Produces:
+
+```python
+@dataclass(frozen=True)
+class IonizationRefusal:
+    code: str
+    reason: str
+
+
+def choose_ionization(candidates: Sequence[str]) -> str | IonizationRefusal:
+    ...
+```
+
+- [ ] **Step 1: Write the failing tests**
+
+```python
+from openchem.domain.salt_stoichiometry import choose_ionization
+
+
+def test_one_structure_at_the_requested_state_is_accepted() -> None:
+    assert choose_ionization(["CC(=O)[O-]"]) == "CC(=O)[O-]"
+
+
+def test_a_net_charge_with_no_structure_is_refused() -> None:
+    refused = choose_ionization([])
+    assert refused.code == "net_charge_only"
+
+
+def test_two_structures_at_the_same_charge_are_not_auto_picked() -> None:
+    refused = choose_ionization(["CC(=O)[O-]", "[O-]C=O"])
+    assert refused.code == "ambiguous_microspecies"
+    assert isinstance(refused, IonizationRefusal)
+```
+
+Need `from openchem.domain.salt_stoichiometry import IonizationRefusal` with the other import. Two different identity strings at one conceptual charge; domain does not know chemistry, so any two distinct strings suffice.
+
+- [ ] **Step 2: Run tests to verify they fail**
+
+Run: `uv run --no-sync pytest tests/test_salt_stoichiometry.py::test_one_structure_at_the_requested_state_is_accepted tests/test_salt_stoichiometry.py::test_a_net_charge_with_no_structure_is_refused tests/test_salt_stoichiometry.py::test_two_structures_at_the_same_charge_are_not_auto_picked -v`
+
+Expected: FAIL with `ImportError` for `choose_ionization`.
+
+- [ ] **Step 3: Write minimal implementation**
+
+Add `#:` comments. Empty `candidates` is `net_charge_only` (a charge request with no identified structure). One unique string is returned. Two or more **distinct** strings is `ambiguous_microspecies`. Duplicate identical strings count as one (canonicalization already collapsed them).
+
+```python
+@dataclass(frozen=True)
+class IonizationRefusal:
+    code: str
+    reason: str
+
+
+#: Pick among fully specified ionic structures. An empty list is a net-charge
+#: request with no structure; several distinct graphs at one charge are not ranked.
+def choose_ionization(candidates: Sequence[str]) -> str | IonizationRefusal:
+    unique = list(dict.fromkeys(candidates))
+    if not unique:
+        return IonizationRefusal(
+            code="net_charge_only",
+            reason="A net charge is not an ionization state; name a structure.",
+        )
+    if len(unique) > 1:
+        return IonizationRefusal(
+            code="ambiguous_microspecies",
+            reason="Several structures share this charge; v1 does not pick one.",
+        )
+    return unique[0]
+```
+
+Do not import RDKit.
+
+- [ ] **Step 4: Run the three new tests**
+
+Expected: PASS.
+
+- [ ] **Step 5: Commit**
+
+```bash
+git add src/openchem/domain/salt_stoichiometry.py tests/test_salt_stoichiometry.py
+git commit -m "Refuse a salt ionization that is only a net charge or several microspecies."
+```
+
+---
+
+### Task 2: Domain pKa evidence (annotation only)
+
+**Files:**
+- Create: `src/openchem/domain/salt_evidence.py`
+- Test: `tests/test_salt_evidence.py`
+
+**Interfaces:**
+- Consumes: nothing from `balance_two`
+- Produces:
+
+```python
+ORIGIN_MEASURED = "measured"
+ORIGIN_PREDICTED = "predicted"
+
+VERDICT_NOT_ASSESSED = "not_assessed"
+VERDICT_MISSING = "missing"
+VERDICT_INCOMPARABLE = "incomparable"
+VERDICT_WRONG_STEP = "wrong_step"
+VERDICT_RECORDED = "recorded"
+
+@dataclass(frozen=True)
+class PkaValue:
+    value: float
+    origin: str
+    medium: str
+    temperature_k: float | None
+    ionic_strength: float | None
+    uncertainty: float | None
+    step_id: str
+
+@dataclass(frozen=True)
+class PkaCompatibility:
+    verdict: str
+    delta: float | None
+    acid: PkaValue | None
+    conjugate_acid: PkaValue | None
+    reason: str
+
+@dataclass(frozen=True)
+class EvidenceRecord:
+    charge_valid: bool
+    structurally_consistent: bool
+    pka_compatible: PkaCompatibility
+    experimentally_established: None
+
+def assess_pka_compatible(
+    *,
+    already_charged: bool,
+    proposed_acid_step_id: str,
+    proposed_conjugate_acid_step_id: str,
+    acid: PkaValue | None,
+    conjugate_acid: PkaValue | None,
+) -> PkaCompatibility:
+    ...
+```
+
+`Î”pKa = pKa(BH+) âˆ’ pKa(HA)` when both values are recorded under comparable conditions and each `step_id` matches the proposed microspecies. Store `delta`; do not turn it into `supported`.
+
+Comparable: same `medium` string, and `temperature_k` equal (including both `None`). Ionic strength may differ without forcing `incomparable` (the record still carries both values). Mixed `measured`/`predicted` origin is still `recorded` if conditions match; the origins stay on the values.
+
+- [ ] **Step 1: Write the failing tests**
+
+```python
+from openchem.domain.salt_evidence import (
+    ORIGIN_MEASURED,
+    VERDICT_INCOMPARABLE,
+    VERDICT_MISSING,
+    VERDICT_NOT_ASSESSED,
+    VERDICT_RECORDED,
+    VERDICT_WRONG_STEP,
+    PkaValue,
+    assess_pka_compatible,
+)
+
+
+def _acetic() -> PkaValue:
+    return PkaValue(4.76, ORIGIN_MEASURED, "water", 298.15, None, None, "acetic_acid_h1")
+
+
+def _pyridinium() -> PkaValue:
+    return PkaValue(5.23, ORIGIN_MEASURED, "water", 298.15, None, None, "pyridine_bh1")
+
+
+def test_already_charged_input_is_not_assessed() -> None:
+    result = assess_pka_compatible(
+        already_charged=True,
+        proposed_acid_step_id="acetic_acid_h1",
+        proposed_conjugate_acid_step_id="pyridine_bh1",
+        acid=_acetic(),
+        conjugate_acid=_pyridinium(),
+    )
+    assert result.verdict == VERDICT_NOT_ASSESSED
+    assert result.delta is None
+
+
+def test_missing_pka_is_missing_not_invented() -> None:
+    result = assess_pka_compatible(
+        already_charged=False,
+        proposed_acid_step_id="acetic_acid_h1",
+        proposed_conjugate_acid_step_id="pyridine_bh1",
+        acid=_acetic(),
+        conjugate_acid=None,
+    )
+    assert result.verdict == VERDICT_MISSING
+    assert result.delta is None
+
+
+def test_delta_is_conjugate_acid_minus_acid() -> None:
+    result = assess_pka_compatible(
+        already_charged=False,
+        proposed_acid_step_id="acetic_acid_h1",
+        proposed_conjugate_acid_step_id="pyridine_bh1",
+        acid=_acetic(),
+        conjugate_acid=_pyridinium(),
+    )
+    assert result.verdict == VERDICT_RECORDED
+    assert result.delta == pytest.approx(0.47)
+
+
+def test_sulfate_must_not_reuse_the_first_sulfuric_pka() -> None:
+    sulfuric_h1 = PkaValue(-3.0, ORIGIN_MEASURED, "water", 298.15, None, None, "sulfuric_h1")
+    pyridine = _pyridinium()
+    result = assess_pka_compatible(
+        already_charged=False,
+        proposed_acid_step_id="sulfuric_h2",
+        proposed_conjugate_acid_step_id="pyridine_bh1",
+        acid=sulfuric_h1,
+        conjugate_acid=pyridine,
+    )
+    assert result.verdict == VERDICT_WRONG_STEP
+    assert result.delta is None
+
+
+def test_bh2_must_not_reuse_the_first_conjugate_acid_pka() -> None:
+    bh1 = PkaValue(9.9, ORIGIN_MEASURED, "water", 298.15, None, None, "en_bh1")
+    acetic = _acetic()
+    result = assess_pka_compatible(
+        already_charged=False,
+        proposed_acid_step_id="acetic_acid_h1",
+        proposed_conjugate_acid_step_id="en_bh2",
+        acid=acetic,
+        conjugate_acid=bh1,
+    )
+    assert result.verdict == VERDICT_WRONG_STEP
+
+
+def test_different_media_are_incomparable() -> None:
+    dmso = PkaValue(12.3, ORIGIN_MEASURED, "DMSO", 298.15, None, None, "acetic_acid_h1")
+    result = assess_pka_compatible(
+        already_charged=False,
+        proposed_acid_step_id="acetic_acid_h1",
+        proposed_conjugate_acid_step_id="pyridine_bh1",
+        acid=dmso,
+        conjugate_acid=_pyridinium(),
+    )
+    assert result.verdict == VERDICT_INCOMPARABLE
+    assert result.delta is None
+```
+
+Add `import pytest` at the top of the test file.
+
+The numbers 4.76 / 5.23 / 0.47 are **fixtures for the arithmetic**, not handbook claims. Do not write them into shipped JSON.
+
+- [ ] **Step 2: Run tests to verify they fail**
+
+Run: `uv run --no-sync pytest tests/test_salt_evidence.py -v`
+
+Expected: FAIL with `ModuleNotFoundError` for `openchem.domain.salt_evidence`.
+
+- [ ] **Step 3: Write minimal implementation**
+
+```python
+"""pKa as an independent salt-composition claim, never a solver input."""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+
+REACHED_BY = (
+    "tooling: consumed by tests/test_salt_evidence.py; evidence is not "
+    "on the window yet"
+)
+
+#: Measured value supplied by the caller. Not a model output.
+ORIGIN_MEASURED = "measured"
+#: Predicted value supplied by the caller. This module does not run a model.
+ORIGIN_PREDICTED = "predicted"
+
+#: Already ionic; the drawing is the state.
+VERDICT_NOT_ASSESSED = "not_assessed"
+#: A required pKa was not supplied.
+VERDICT_MISSING = "missing"
+#: Media or temperatures do not match, so Î”pKa is not a constant.
+VERDICT_INCOMPARABLE = "incomparable"
+#: A value's step_id is not the proposed microspecies.
+VERDICT_WRONG_STEP = "wrong_step"
+#: Both values named the proposed steps under comparable conditions.
+VERDICT_RECORDED = "recorded"
+
+
+@dataclass(frozen=True)
+class PkaValue:
+    value: float
+    origin: str
+    medium: str
+    temperature_k: float | None
+    ionic_strength: float | None
+    uncertainty: float | None
+    step_id: str
+
+
+@dataclass(frozen=True)
+class PkaCompatibility:
+    verdict: str
+    delta: float | None
+    acid: PkaValue | None
+    conjugate_acid: PkaValue | None
+    reason: str
+
+
+@dataclass(frozen=True)
+class EvidenceRecord:
+    charge_valid: bool
+    structurally_consistent: bool
+    pka_compatible: PkaCompatibility
+    experimentally_established: None
+
+
+def assess_pka_compatible(
+    *,
+    already_charged: bool,
+    proposed_acid_step_id: str,
+    proposed_conjugate_acid_step_id: str,
+    acid: PkaValue | None,
+    conjugate_acid: PkaValue | None,
+) -> PkaCompatibility:
+    if already_charged:
+        return PkaCompatibility(
+            VERDICT_NOT_ASSESSED,
+            None,
+            None,
+            None,
+            "Already-charged input is not pKa-assessed; the state is in the drawing.",
+        )
+    if acid is None or conjugate_acid is None:
+        return PkaCompatibility(
+            VERDICT_MISSING,
+            None,
+            acid,
+            conjugate_acid,
+            "pKa was not assessed because a value for the proposed step is missing.",
+        )
+    if acid.step_id != proposed_acid_step_id or conjugate_acid.step_id != proposed_conjugate_acid_step_id:
+        return PkaCompatibility(
+            VERDICT_WRONG_STEP,
+            None,
+            acid,
+            conjugate_acid,
+            "pKa step identity does not match the proposed microspecies.",
+        )
+    if acid.medium != conjugate_acid.medium or acid.temperature_k != conjugate_acid.temperature_k:
+        return PkaCompatibility(
+            VERDICT_INCOMPARABLE,
+            None,
+            acid,
+            conjugate_acid,
+            "pKa values are not from comparable conditions.",
+        )
+    return PkaCompatibility(
+        VERDICT_RECORDED,
+        conjugate_acid.value - acid.value,
+        acid,
+        conjugate_acid,
+        "Î”pKa = pKa(BH+) âˆ’ pKa(HA) under the stated conditions; this is not a crystal.",
+    )
+```
+
+`balance_two` must not be imported here. Tests must not import `openchem.chem.pka_providers`.
+
+- [ ] **Step 4: Run `tests/test_salt_evidence.py -v`**
+
+Expected: PASS.
+
+- [ ] **Step 5: Commit**
+
+```bash
+git add src/openchem/domain/salt_evidence.py tests/test_salt_evidence.py
+git commit -m "Record salt pKa as a named step under comparable conditions, not a proof."
+```
+
+---
+
+### Task 3: Domain workflow 2 â€” two supplied ions
+
+**Files:**
+- Modify: `src/openchem/domain/salt_stoichiometry.py`
+- Modify: `src/openchem/domain/salt_evidence.py` (optional helper `evidence_for_supplied_ions`)
+- Test: `tests/test_salt_stoichiometry.py`, `tests/test_salt_evidence.py`
+
+**Interfaces:**
+- Consumes: `ModeASpecies`, `KIND_ION`, `balance_two`, `assess_pka_compatible`
+- Produces:
+
+```python
+def compose_supplied_ions(
+    cation: ModeASpecies,
+    anion: ModeASpecies,
+) -> ModeAComposition | ModeARefusal:
+    ...
+```
+
+Two `KIND_ION` species, opposite signs, `balance_two`, **no** formula-unit conservation against neutrals (no transfer was modelled). Mixing a molecular neutral with a supplied ion remains `missing_proton_source` on `compose_mode_a` (already shipped). Do not add a neutralization path.
+
+- [ ] **Step 1: Write the failing tests**
+
+```python
+from openchem.domain.salt_evidence import VERDICT_NOT_ASSESSED, assess_pka_compatible
+from openchem.domain.salt_stoichiometry import (
+    KIND_ION,
+    KIND_MOLECULAR_NEUTRAL,
+    ModeASpecies,
+    compose_supplied_ions,
+)
+
+
+def test_sodium_and_acetate_as_given_ions_balance_one_to_one() -> None:
+    sodium = ModeASpecies("[Na+]", 1, KIND_ION, (("Na", 1),))
+    acetate = ModeASpecies("CC(=O)[O-]", -1, KIND_ION, (("C", 2), ("H", 3), ("O", 2)))
+    result = compose_supplied_ions(sodium, acetate)
+    assert result.cation_count == 1
+    assert result.anion_count == 1
+    assert result.charge_valid is True
+
+
+def test_supplied_ions_do_not_assess_pka() -> None:
+    result = assess_pka_compatible(
+        already_charged=True,
+        proposed_acid_step_id="x",
+        proposed_conjugate_acid_step_id="y",
+        acid=None,
+        conjugate_acid=None,
+    )
+    assert result.verdict == VERDICT_NOT_ASSESSED
+
+
+def test_a_neutral_passed_to_supplied_ions_is_refused() -> None:
+    acetic = ModeASpecies("CC(=O)O", 0, KIND_MOLECULAR_NEUTRAL, (("C", 2), ("H", 4), ("O", 2)))
+    sodium = ModeASpecies("[Na+]", 1, KIND_ION, (("Na", 1),))
+    refused = compose_supplied_ions(sodium, acetic)
+    assert refused.code == "missing_proton_source"
+```
+
+- [ ] **Step 2: Run the new tests**
+
+Expected: FAIL with `ImportError` for `compose_supplied_ions`.
+
+- [ ] **Step 3: Write minimal implementation**
+
+```python
+def compose_supplied_ions(
+    cation: ModeASpecies,
+    anion: ModeASpecies,
+) -> ModeAComposition | ModeARefusal:
+    if cation.kind != KIND_ION or anion.kind != KIND_ION:
+        return ModeARefusal(
+            code="missing_proton_source",
+            reason=(
+                "A molecular neutral plus a supplied ion does not provide "
+                "the protons for a transfer; supply both ions as given."
+            ),
+        )
+    balanced = balance_two(
+        ChargedSpecies(cation.identity, cation.charge),
+        ChargedSpecies(anion.identity, anion.charge),
+    )
+    if isinstance(balanced, BalanceRefusal):
+        return ModeARefusal(code=balanced.code, reason=balanced.reason)
+    return ModeAComposition(
+        cation_count=balanced.cation_count,
+        anion_count=balanced.anion_count,
+        charge_valid=True,
+    )
+```
+
+Do not call `formula_unit_conserved`. Do not call `assess_pka_compatible` from this function.
+
+- [ ] **Step 4: Run the new tests plus `tests/test_salt_stoichiometry.py` and `tests/test_salt_evidence.py`**
+
+Expected: PASS (including existing Mode A tests).
+
+- [ ] **Step 5: Commit**
+
+```bash
+git add src/openchem/domain/salt_stoichiometry.py tests/test_salt_stoichiometry.py tests/test_salt_evidence.py
+git commit -m "Compose two supplied ions as given, without inventing protons or a pKa."
+```
+
+---
+
+### Task 4: Chem site transform (structure, not charge)
+
+**Files:**
+- Create: `src/openchem/chem/salt_ionization.py`
+- Test: `tests/test_salt_ionization.py`
+
+**Interfaces:**
+- Consumes: `fragment_key`, `fragment_formal_charge` from `salt_components`; `choose_ionization` from domain
+- Produces:
+
+```python
+@dataclass(frozen=True)
+class SiteTransform:
+    atom_index: int
+    direction: str  # "protonate" | "deprotonate"
+
+
+def apply_site_transform(mol: Chem.Mol, transform: SiteTransform) -> Chem.Mol | IdentityRefusal:
+    ...
+
+
+def ionize_at_sites(mol: Chem.Mol, transforms: Sequence[SiteTransform]) -> str | IdentityRefusal | IonizationRefusal:
+    """Apply the named sites, then choose_ionization on the single result identity."""
+```
+
+`protonate`: `SetNumExplicitHs(n+1)` and `SetFormalCharge(z+1)` on that atom, then sanitize.
+`deprotonate`: Hs must be â‰¥1 (explicit or implicit via `GetTotalNumHs`); then explicit Hs become `total-1`, charge `z-1`.
+
+- [ ] **Step 1: Write the failing tests**
+
+```python
+from rdkit import Chem
+
+from openchem.chem.salt_components import fragment_formal_charge, fragment_key
+from openchem.chem.salt_ionization import SiteTransform, apply_site_transform
+
+
+def _acetic() -> Chem.Mol:
+    return Chem.MolFromSmiles("CC(=O)O")
+
+
+def test_deprotonating_acetic_acid_updates_hydrogen_and_charge() -> None:
+    mol = _acetic()
+    oxygen = next(
+        atom.GetIdx()
+        for atom in mol.GetAtoms()
+        if atom.GetSymbol() == "O" and atom.GetTotalNumHs() == 1
+    )
+    result = apply_site_transform(mol, SiteTransform(oxygen, "deprotonate"))
+    assert fragment_formal_charge(result) == -1
+    assert fragment_key(result) == "CC(=O)[O-]"
+    # parent unchanged
+    assert fragment_formal_charge(mol) == 0
+
+
+def test_protonating_pyridine_updates_hydrogen_and_charge() -> None:
+    mol = Chem.MolFromSmiles("c1ccncc1")
+    nitrogen = next(atom.GetIdx() for atom in mol.GetAtoms() if atom.GetSymbol() == "N")
+    result = apply_site_transform(mol, SiteTransform(nitrogen, "protonate"))
+    assert fragment_formal_charge(result) == 1
+    assert "[nH+]" in fragment_key(result) or "c1cc[nH+]cc1" == fragment_key(result)
+
+
+def test_a_bad_atom_index_is_refused() -> None:
+    mol = _acetic()
+    refused = apply_site_transform(mol, SiteTransform(99, "deprotonate"))
+    assert refused.code == "invalid_site"
+```
+
+If pyridine's canonical SMILES in this RDKit pin is not `c1cc[nH+]cc1`, assert equality to `fragment_key` of `Chem.MolFromSmiles("c1cc[nH+]cc1")` instead of a literal.
+
+- [ ] **Step 2: Run to verify FAIL** (`ModuleNotFoundError` for `salt_ionization`).
+
+- [ ] **Step 3: Write minimal implementation**
+
+Copy the molecule. Do not mutate the input. `REACHED_BY` pointing at `tests/test_salt_ionization.py`. Direction must be exactly `protonate` or `deprotonate`; anything else `invalid_site`.
+
+```python
+"""Fully specified ionization states for salt composition. No pKa sidecar."""
+
+from __future__ import annotations
+
+from collections.abc import Sequence
+from dataclasses import dataclass
+
+from rdkit import Chem
+
+from openchem.chem.salt_components import IdentityRefusal, fragment_key
+from openchem.domain.salt_stoichiometry import IonizationRefusal, choose_ionization
+
+REACHED_BY = (
+    "tooling: consumed by tests/test_salt_ionization.py; ionization is not "
+    "on the window yet"
+)
+
+
+@dataclass(frozen=True)
+class SiteTransform:
+    atom_index: int
+    direction: str
+
+
+def apply_site_transform(mol: Chem.Mol, transform: SiteTransform) -> Chem.Mol | IdentityRefusal:
+    if transform.direction not in {"protonate", "deprotonate"}:
+        return IdentityRefusal(code="invalid_site", reason="direction must be protonate or deprotonate.")
+    if transform.atom_index < 0 or transform.atom_index >= mol.GetNumAtoms():
+        return IdentityRefusal(code="invalid_site", reason="atom index is not in the parent.")
+    copy = Chem.Mol(mol)
+    atom = copy.GetAtomWithIdx(transform.atom_index)
+    if transform.direction == "protonate":
+        atom.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
+        atom.SetFormalCharge(atom.GetFormalCharge() + 1)
+        atom.SetNoImplicit(True)
+    else:
+        total = atom.GetTotalNumHs()
+        if total < 1:
+            return IdentityRefusal(code="invalid_site", reason="that atom has no hydrogen to remove.")
+        atom.SetNumExplicitHs(total - 1)
+        atom.SetFormalCharge(atom.GetFormalCharge() - 1)
+        atom.SetNoImplicit(True)
+    try:
+        Chem.SanitizeMol(copy)
+    except (ValueError, RuntimeError):
+        return IdentityRefusal(code="unsanitizable", reason="the ionized structure could not be sanitized.")
+    return copy
+
+
+def ionize_at_sites(
+    mol: Chem.Mol, transforms: Sequence[SiteTransform]
+) -> str | IdentityRefusal | IonizationRefusal:
+    current: Chem.Mol | IdentityRefusal = mol
+    for transform in transforms:
+        if isinstance(current, IdentityRefusal):
+            return current
+        current = apply_site_transform(current, transform)
+    if isinstance(current, IdentityRefusal):
+        return current
+    key = fragment_key(current)
+    if isinstance(key, IdentityRefusal):
+        return key
+    return choose_ionization([key])
+```
+
+Do not import `pka_providers` or `pka_species_ladder`.
+
+- [ ] **Step 4: Run `tests/test_salt_ionization.py -v`**
+
+Expected: PASS.
+
+- [ ] **Step 5: Commit**
+
+```bash
+git add src/openchem/chem/salt_ionization.py tests/test_salt_ionization.py
+git commit -m "Ionize a named atom by moving both its hydrogens and its formal charge."
+```
+
+---
+
+### Task 5: Chem net-charge enumeration without auto-pick
+
+**Files:**
+- Modify: `src/openchem/chem/salt_ionization.py`
+- Test: `tests/test_salt_ionization.py`
+
+**Interfaces:**
+- Consumes: `apply_site_transform`, `choose_ionization`
+- Produces:
+
+```python
+def structures_at_net_charge(mol: Chem.Mol, target_charge: int) -> tuple[str, ...]:
+    """Distinct fragment_key values reachable by protonate/deprotonate of heavy atoms that match target_charge."""
+```
+
+v1 enumeration: for each heavy atom, try `protonate` once and `deprotonate` once (single-site). Collect identities whose `fragment_formal_charge` equals `target_charge`. Do not rank. Then `choose_ionization` on that tuple.
+
+Also:
+
+```python
+def select_by_net_charge(mol: Chem.Mol, target_charge: int) -> str | IonizationRefusal | IdentityRefusal:
+    return choose_ionization(structures_at_net_charge(mol, target_charge))
+```
+
+- [ ] **Step 1: Write the failing tests**
+
+```python
+from openchem.chem.salt_ionization import select_by_net_charge, structures_at_net_charge
+from openchem.domain.salt_stoichiometry import IonizationRefusal
+
+
+def test_acetic_acid_at_minus_one_is_acetate() -> None:
+    mol = Chem.MolFromSmiles("CC(=O)O")
+    chosen = select_by_net_charge(mol, -1)
+    assert chosen == fragment_key(Chem.MolFromSmiles("CC(=O)[O-]"))
+
+
+def test_acetic_acid_at_plus_one_is_net_charge_only() -> None:
+    mol = Chem.MolFromSmiles("CC(=O)O")
+    refused = select_by_net_charge(mol, 1)
+    assert isinstance(refused, IonizationRefusal)
+    assert refused.code == "net_charge_only"
+
+
+def test_two_inequivalent_sites_at_the_same_charge_are_not_picked() -> None:
+    # 4-aminophenol: O-H and aniline N are different graphs at -1 vs +1;
+    # at charge 0 the parent is already unique. Use 3-aminophenol / 4-aminophenol
+    # is not the pair. Use 4-hydroxybenzoic acid: carboxylate vs phenolate at -1.
+    mol = Chem.MolFromSmiles("O=C(O)c1ccc(O)cc1")
+    keys = structures_at_net_charge(mol, -1)
+    assert len(set(keys)) >= 2
+    refused = select_by_net_charge(mol, -1)
+    assert isinstance(refused, IonizationRefusal)
+    assert refused.code == "ambiguous_microspecies"
+```
+
+If 4-hydroxybenzoic acid yields only one SMILES in this RDKit pin (tautomer merge â€” **forbidden by design** if it happens), the test must fail: identity is graph, not formula. Do not call `CanonicalRankAtoms` tautomer canonicalization. If the two deprotonations collapse, pick another pair (e.g. `NCCCO` vs wait â€” use `OCCc1ccc(O)cc1` tyrosol: aliphatic alcohol vs phenol). Prefer `OCCc1ccc(O)cc1` if 4-hydroxybenzoic collapses.
+
+- [ ] **Step 2: Run to verify FAIL** (`select_by_net_charge` missing).
+
+- [ ] **Step 3: Implement** by looping heavy atoms, applying each direction, skipping `IdentityRefusal`, keeping keys whose charge matches. `structures_at_net_charge` returns a tuple of unique keys in atom-index then protonate-before-deprotonate order.
+
+- [ ] **Step 4: Run `tests/test_salt_ionization.py -v`**
+
+Expected: PASS.
+
+- [ ] **Step 5: Commit**
+
+```bash
+git add src/openchem/chem/salt_ionization.py tests/test_salt_ionization.py
+git commit -m "List ionization microspecies at a charge; never pick among several."
+```
+
+---
+
+### Task 6: Cited ion catalog
+
+**Files:**
+- Create: `src/openchem/chem/data/ionic_species.json`
+- Create: `src/openchem/chem/ionic_species.py`
+- Modify: `docs/sources.toml` â€” add `used_by` path on a new `salt_ion_catalog` entry (**no DOI**). Do not claim CRC pKa numbers.
+- Test: `tests/test_ionic_species.py`
+
+**Interfaces:**
+- Produces:
+
+```python
+@dataclass(frozen=True)
+class IonicSpeciesRow:
+    ion_id: str
+    name: str
+    ion_smiles: str
+    charge: int
+    parent_smiles: str | None
+    relationship: str
+    source_key: str
+
+
+def load_ionic_species() -> tuple[IonicSpeciesRow, ...]:
+    ...
+
+
+def row_by_id(ion_id: str) -> IonicSpeciesRow | None:
+    ...
+```
+
+JSON shape:
+
+```json
+{
+  "_source_key": "salt_ion_catalog",
+  "ions": [
+    {
+      "id": "chloride",
+      "name": "chloride",
+      "ion_smiles": "[Cl-]",
+      "charge": -1,
+      "parent_smiles": "Cl",
+      "relationship": "hydrohalide",
+      "source_key": "salt_ion_catalog"
+    }
+  ]
+}
+```
+
+v1 rows (exact ids): `chloride`, `bromide`, `iodide`, `hydrogen_sulfate`, `sulfate`, `dihydrogen_phosphate`, `hydrogen_phosphate`, `phosphate`, `acetate`, `nitrate`, `ammonium`, `pyridinium`.
+
+SMILES (must round-trip through `fragment_key` after `MolFromSmiles`):
+
+- chloride `[Cl-]` parent `Cl` relationship `hydrohalide`
+- bromide `[Br-]` parent `Br` relationship `hydrohalide`
+- iodide `[I-]` parent `I` relationship `hydrohalide`
+- hydrogen_sulfate `OS(=O)(=O)[O-]` parent `OS(=O)(=O)O` relationship `first_dissociation`
+- sulfate `[O-]S(=O)(=O)[O-]` parent `OS(=O)(=O)O` relationship `second_dissociation`
+- dihydrogen_phosphate `OP(=O)(O)[O-]` parent `OP(=O)(O)O` relationship `first_dissociation`
+- hydrogen_phosphate `OP(=O)([O-])[O-]` parent `OP(=O)(O)O` relationship `second_dissociation`
+- phosphate `[O-]P(=O)([O-])[O-]` parent `OP(=O)(O)O` relationship `third_dissociation`
+- acetate `CC(=O)[O-]` parent `CC(=O)O` relationship `first_dissociation`
+- nitrate `[O-][N+](=O)[O-]` parent `O[N+](=O)[O-]` relationship `first_dissociation`
+- ammonium `[NH4+]` parent `N` relationship `protonated_base`
+- pyridinium `c1cc[nH+]cc1` parent `c1ccncc1` relationship `protonated_base`
+
+If `fragment_key` of `MolFromSmiles(ion_smiles)` differs from the JSON string, **store the `fragment_key` form** so identity matches Mode B.
+
+`salt_ion_catalog` in `docs/sources.toml`:
+
+```toml
+[[source]]
+key = "salt_ion_catalog"
+kind = "dataset"
+citation = "OpenChem Studio v1 salt ion catalog: named common ions as canonical SMILES for composition, not a pharmaceutical list."
+identifier_type = "none"
+identifier = "salt_ion_catalog"
+status = "shipped"
+verification = "citation"
+verified_date = 2026-11-11
+used_by = ["src/openchem/chem/data/ionic_species.json"]
+reason = """
+STRUCTURES ONLY. Each row is a named ion's graph and its parent, so Mode A
+workflow 2 and the catalog agree on identity. No pKa numbers. Not safety or
+acceptability. Hydrogen sulfate and sulfate are different rows.
+"""
+```
+
+If `identifier_type = "none"` is rejected by `tests/test_sources_are_current.py`, use the same `identifier_type` a similar internal dataset uses (search `kind = "dataset"`). Do not invent a DOI.
+
+- [ ] **Step 1: Write failing tests** (file missing).
+
+```python
+from openchem.chem.ionic_species import load_ionic_species, row_by_id
+from openchem.chem.salt_components import fragment_formal_charge, fragment_key
+from rdkit import Chem
+
+
+def test_hydrogen_sulfate_and_sulfate_are_different_rows() -> None:
+    hso4 = row_by_id("hydrogen_sulfate")
+    so4 = row_by_id("sulfate")
+    assert hso4 is not None and so4 is not None
+    assert hso4.ion_smiles != so4.ion_smiles
+    assert hso4.charge == -1
+    assert so4.charge == -2
+
+
+def test_every_row_round_trips_to_its_charge_and_key() -> None:
+    for row in load_ionic_species():
+        mol = Chem.MolFromSmiles(row.ion_smiles)
+        assert mol is not None, row.ion_id
+        assert fragment_formal_charge(mol) == row.charge, row.ion_id
+        assert fragment_key(mol) == row.ion_smiles, row.ion_id
+
+
+def test_catalog_is_not_a_pharma_whitelist() -> None:
+    ids = {row.ion_id for row in load_ionic_species()}
+    assert "chloride" in ids
+    # An unusual ion is simply absent, not forbidden.
+    assert row_by_id("hexafluorophosphate") is None
+```
+
+- [ ] **Step 2: Run â€” FAIL import.**
+
+- [ ] **Step 3: Add JSON, loader, sources.toml entry.** Loader reads `Path(__file__).resolve().parent / "data" / "ionic_species.json"`. Refuse a row whose `charge` disagrees with `fragment_formal_charge` at load time by raising `ValueError` naming `id` (fail closed).
+
+`REACHED_BY` on the loader module.
+
+- [ ] **Step 4: Run `tests/test_ionic_species.py` and `tests/test_sources_are_current.py` (or the tests that fail on an unregistered `used_by` path / DOI).**
+
+If `test_sources_are_current` requires `SOURCES.md` regeneration, run `uv run --no-sync python tools/build_sources_doc.py` and include the generated file.
+
+- [ ] **Step 5: Commit**
+
+```bash
+git add src/openchem/chem/ionic_species.py src/openchem/chem/data/ionic_species.json docs/sources.toml docs/SOURCES.md tests/test_ionic_species.py
+git commit -m "Catalog named salt ions as graphs, with sulfate and hydrogen sulfate kept apart."
+```
+
+---
+
+### Task 7: Changelog, shards, architecture, design status
+
+**Files:**
+- Create: changelog fragment via `tools/changelog.py new salt-composition-slice-3`
+- Modify: `docs/SALT_COMPOSITION_DESIGN.md` status line â€” slice 3 adds ionization, catalog, pKa evidence; Mode C/UI still not authorized
+- Modify: `docs/ROADMAP.md` salt-composition bullet
+- Modify: `CLAUDE.md` Key Files salt line â€” mention `salt_ionization.py`, `salt_evidence.py`, `ionic_species.py`
+- Modify: `docs/ARCHITECTURE.md` â€” chem count 165 â†’ 167; name `salt_ionization.py` and `ionic_species.py` beside `salt_mode_a.py`
+- Modify: `docs/README.md` salt row if it still says slice 1â€“2 only
+- Modify: `tools/suite-shard-pins.json` via `--pin-new` **without** `--splits=3`
+- Modify: `src/openchem/domain/salt_stoichiometry.py` `REACHED_BY` to also name new tests if the reachability guard requires it
+
+**Interfaces:** none
+
+- [ ] **Step 1: Changelog fragment** titled `### Salt composition, slice 3 (library, no UI)` so it does not collide with slice 1/2 headings.
+
+Body:
+
+```markdown
+### Salt composition, slice 3 (library, no UI)
+
+- Fully specified ionization (site transforms; net charge alone refused;
+  several microspecies at one charge listed, not picked), two supplied ions
+  as given, a small cited ion catalog, and `pka_compatible` as named-step
+  evidence that never feeds `balance_two`. Still no panel and not a crystal.
+```
+
+- [ ] **Step 2: Pin** `python tools/suite_shards.py --pin-new`
+
+- [ ] **Step 3: Docs + architecture count.** Run:
+
+`uv run --no-sync pytest tests/test_docs_are_current.py::test_the_architecture_module_count_is_live tests/test_docs_are_current.py::test_every_chem_module_is_named_in_the_package_map tests/test_layering.py tests/test_salt_stoichiometry.py tests/test_salt_evidence.py tests/test_salt_ionization.py tests/test_ionic_species.py tests/test_constant_docs.py::test_no_constant_has_fallen_out_of_documentation tests/test_changelog_fragments.py -q`
+
+Expected: PASS.
+
+- [ ] **Step 4: Commit**
+
+```bash
+git add changelog.d docs/SALT_COMPOSITION_DESIGN.md docs/ROADMAP.md docs/ARCHITECTURE.md docs/README.md CLAUDE.md tools/suite-shard-pins.json src/openchem/domain/salt_stoichiometry.py
+git commit -m "Record slice 3 of salt composition in the changelog and the file map."
+```
+
+---
diff --git a/src/openchem/chem/data/ionic_species.json b/src/openchem/chem/data/ionic_species.json
new file mode 100644
index 00000000..ae36a940
--- /dev/null
+++ b/src/openchem/chem/data/ionic_species.json
@@ -0,0 +1,113 @@
+{
+  "_source_key": "salt_ion_catalog",
+  "ions": [
+    {
+      "id": "chloride",
+      "name": "chloride",
+      "ion_smiles": "[Cl-]",
+      "charge": -1,
+      "parent_smiles": "Cl",
+      "relationship": "hydrohalide",
+      "source_key": "salt_ion_catalog"
+    },
+    {
+      "id": "bromide",
+      "name": "bromide",
+      "ion_smiles": "[Br-]",
+      "charge": -1,
+      "parent_smiles": "Br",
+      "relationship": "hydrohalide",
+      "source_key": "salt_ion_catalog"
+    },
+    {
+      "id": "iodide",
+      "name": "iodide",
+      "ion_smiles": "[I-]",
+      "charge": -1,
+      "parent_smiles": "I",
+      "relationship": "hydrohalide",
+      "source_key": "salt_ion_catalog"
+    },
+    {
+      "id": "hydrogen_sulfate",
+      "name": "hydrogen sulfate",
+      "ion_smiles": "O=S(=O)([O-])O",
+      "charge": -1,
+      "parent_smiles": "OS(=O)(=O)O",
+      "relationship": "first_dissociation",
+      "source_key": "salt_ion_catalog"
+    },
+    {
+      "id": "sulfate",
+      "name": "sulfate",
+      "ion_smiles": "O=S(=O)([O-])[O-]",
+      "charge": -2,
+      "parent_smiles": "OS(=O)(=O)O",
+      "relationship": "second_dissociation",
+      "source_key": "salt_ion_catalog"
+    },
+    {
+      "id": "dihydrogen_phosphate",
+      "name": "dihydrogen phosphate",
+      "ion_smiles": "O=P([O-])(O)O",
+      "charge": -1,
+      "parent_smiles": "OP(=O)(O)O",
+      "relationship": "first_dissociation",
+      "source_key": "salt_ion_catalog"
+    },
+    {
+      "id": "hydrogen_phosphate",
+      "name": "hydrogen phosphate",
+      "ion_smiles": "O=P([O-])([O-])O",
+      "charge": -2,
+      "parent_smiles": "OP(=O)(O)O",
+      "relationship": "second_dissociation",
+      "source_key": "salt_ion_catalog"
+    },
+    {
+      "id": "phosphate",
+      "name": "phosphate",
+      "ion_smiles": "O=P([O-])([O-])[O-]",
+      "charge": -3,
+      "parent_smiles": "OP(=O)(O)O",
+      "relationship": "third_dissociation",
+      "source_key": "salt_ion_catalog"
+    },
+    {
+      "id": "acetate",
+      "name": "acetate",
+      "ion_smiles": "CC(=O)[O-]",
+      "charge": -1,
+      "parent_smiles": "CC(=O)O",
+      "relationship": "first_dissociation",
+      "source_key": "salt_ion_catalog"
+    },
+    {
+      "id": "nitrate",
+      "name": "nitrate",
+      "ion_smiles": "O=[N+]([O-])[O-]",
+      "charge": -1,
+      "parent_smiles": "O[N+](=O)[O-]",
+      "relationship": "first_dissociation",
+      "source_key": "salt_ion_catalog"
+    },
+    {
+      "id": "ammonium",
+      "name": "ammonium",
+      "ion_smiles": "[NH4+]",
+      "charge": 1,
+      "parent_smiles": "N",
+      "relationship": "protonated_base",
+      "source_key": "salt_ion_catalog"
+    },
+    {
+      "id": "pyridinium",
+      "name": "pyridinium",
+      "ion_smiles": "c1cc[nH+]cc1",
+      "charge": 1,
+      "parent_smiles": "c1ccncc1",
+      "relationship": "protonated_base",
+      "source_key": "salt_ion_catalog"
+    }
+  ]
+}
diff --git a/src/openchem/chem/ionic_species.py b/src/openchem/chem/ionic_species.py
new file mode 100644
index 00000000..7a512a73
--- /dev/null
+++ b/src/openchem/chem/ionic_species.py
@@ -0,0 +1,90 @@
+"""Named common ions as graphs for salt composition.
+
+Structures only. No pKa numbers, and not a pharmaceutical acceptability list.
+Hydrogen sulfate and sulfate are different rows.
+"""
+
+from __future__ import annotations
+
+import json
+from dataclasses import dataclass
+from pathlib import Path
+
+from rdkit import Chem
+
+from openchem.chem.salt_components import fragment_formal_charge, fragment_key
+
+#: The catalog is not on the window. Remove this when something reachable
+#: from ``openchem.main`` imports the module.
+REACHED_BY = (
+    "tooling: consumed by tests/test_ionic_species.py; the ion catalog is not "
+    "on the window yet"
+)
+
+
+@dataclass(frozen=True)
+class IonicSpeciesRow:
+    ion_id: str
+    name: str
+    ion_smiles: str
+    charge: int
+    parent_smiles: str | None
+    relationship: str
+    source_key: str
+
+
+def _catalog_path() -> Path:
+    return Path(__file__).resolve().parent / "data" / "ionic_species.json"
+
+
+def load_ionic_species() -> tuple[IonicSpeciesRow, ...]:
+    """Read the cited catalog. A charge that is not the graph's formal charge raises ``ValueError`` naming the id."""
+    payload = json.loads(_catalog_path().read_text(encoding="utf-8"))
+    rows: list[IonicSpeciesRow] = []
+    seen: set[str] = set()
+    for item in payload["ions"]:
+        row = _row(item)
+        if row.ion_id in seen:
+            raise ValueError(f"{row.ion_id}: duplicate id")
+        seen.add(row.ion_id)
+        rows.append(row)
+    return tuple(rows)
+
+
+def row_by_id(ion_id: str) -> IonicSpeciesRow | None:
+    for row in load_ionic_species():
+        if row.ion_id == ion_id:
+            return row
+    return None
+
+
+def _row(item: dict) -> IonicSpeciesRow:
+    ion_id = item["id"]
+    smiles = item["ion_smiles"]
+    charge = item["charge"]
+    if type(charge) is not int:
+        raise ValueError(f"{ion_id}: charge is not an integer")
+    mol = Chem.MolFromSmiles(smiles)
+    if mol is None:
+        raise ValueError(f"{ion_id}: ion_smiles could not be read")
+    graph_charge = fragment_formal_charge(mol)
+    if graph_charge != charge:
+        raise ValueError(
+            f"{ion_id}: charge {charge} disagrees with fragment_formal_charge {graph_charge}"
+        )
+    # Mode B identifies a drawn ion by fragment_key. A stored spelling that
+    # is not that key would miss the same graph.
+    if fragment_key(mol) != smiles:
+        raise ValueError(f"{ion_id}: ion_smiles is not the fragment_key form")
+    parent = item["parent_smiles"]
+    if parent is not None and not isinstance(parent, str):
+        raise ValueError(f"{ion_id}: parent_smiles is not a string")
+    return IonicSpeciesRow(
+        ion_id=ion_id,
+        name=item["name"],
+        ion_smiles=smiles,
+        charge=charge,
+        parent_smiles=parent,
+        relationship=item["relationship"],
+        source_key=item["source_key"],
+    )
diff --git a/src/openchem/chem/salt_ionization.py b/src/openchem/chem/salt_ionization.py
new file mode 100644
index 00000000..991aaec5
--- /dev/null
+++ b/src/openchem/chem/salt_ionization.py
@@ -0,0 +1,119 @@
+"""Fully specified ionization states for salt composition. No pKa sidecar."""
+
+from __future__ import annotations
+
+from collections.abc import Sequence
+from dataclasses import dataclass
+
+from rdkit import Chem
+
+from openchem.chem.salt_components import (
+    IdentityRefusal,
+    fragment_formal_charge,
+    fragment_key,
+)
+from openchem.domain.salt_stoichiometry import IonizationRefusal, choose_ionization
+
+REACHED_BY = (
+    "tooling: consumed by tests/test_salt_ionization.py; ionization is not "
+    "on the window yet"
+)
+
+
+@dataclass(frozen=True)
+class SiteTransform:
+    atom_index: int
+    direction: str
+
+
+def apply_site_transform(mol: Chem.Mol, transform: SiteTransform) -> Chem.Mol | IdentityRefusal:
+    if transform.direction not in {"protonate", "deprotonate"}:
+        return IdentityRefusal(code="invalid_site", reason="direction must be protonate or deprotonate.")
+    if transform.atom_index < 0 or transform.atom_index >= mol.GetNumAtoms():
+        return IdentityRefusal(code="invalid_site", reason="atom index is not in the parent.")
+    copy = Chem.Mol(mol)
+    atom = copy.GetAtomWithIdx(transform.atom_index)
+    if transform.direction == "protonate":
+        atom.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
+        atom.SetFormalCharge(atom.GetFormalCharge() + 1)
+        atom.SetNoImplicit(True)
+    else:
+        total = atom.GetTotalNumHs()
+        if total < 1:
+            return IdentityRefusal(code="invalid_site", reason="that atom has no hydrogen to remove.")
+        atom.SetNumExplicitHs(total - 1)
+        atom.SetFormalCharge(atom.GetFormalCharge() - 1)
+        atom.SetNoImplicit(True)
+    try:
+        Chem.SanitizeMol(copy)
+    except (ValueError, RuntimeError):
+        return IdentityRefusal(code="unsanitizable", reason="the ionized structure could not be sanitized.")
+    return copy
+
+
+def ionize_at_sites(
+    mol: Chem.Mol, transforms: Sequence[SiteTransform]
+) -> str | IdentityRefusal | IonizationRefusal:
+    current: Chem.Mol | IdentityRefusal = mol
+    for transform in transforms:
+        if isinstance(current, IdentityRefusal):
+            return current
+        current = apply_site_transform(current, transform)
+    if isinstance(current, IdentityRefusal):
+        return current
+    key = fragment_key(current)
+    if isinstance(key, IdentityRefusal):
+        return key
+    return choose_ionization([key])
+
+
+# Neutral Câ€“H and neutral oxygen both sanitize in this RDKit pin (acetic acid
+# gives ``[CH2-]C(=O)O``, ``CC(O)=[OH+]`` and ``CC(=O)[OH2+]``). Those are not
+# v1 microspecies: a named atom can still be transformed, but net-charge
+# enumeration only offers heteroatom acids and N/P bases, plus a proton on an
+# existing anion or off an existing cation. No ranking and no tautomer pass.
+_ACID_ELEMENTS = frozenset({7, 8, 15, 16})  # N, O, P, S
+_BASE_ELEMENTS = frozenset({7, 15})  # N, P
+
+
+def _enumeration_directions(atom: Chem.Atom) -> tuple[str, ...]:
+    charge = atom.GetFormalCharge()
+    number = atom.GetAtomicNum()
+    directions: list[str] = []
+    if number in _BASE_ELEMENTS or charge < 0:
+        directions.append("protonate")
+    if atom.GetTotalNumHs() >= 1 and (number in _ACID_ELEMENTS or charge > 0):
+        directions.append("deprotonate")
+    return tuple(directions)
+
+
+def structures_at_net_charge(mol: Chem.Mol, target_charge: int) -> tuple[str, ...]:
+    """Distinct fragment_key values from one protonate or deprotonate that match target_charge.
+
+    Order is atom index, then protonate before deprotonate. Identity refusals
+    are skipped. Keys are not ranked and are not tautomer-canonicalized:
+    ``choose_ionization`` decides whether one graph is unique.
+    """
+    keys: list[str] = []
+    seen: set[str] = set()
+    for atom in mol.GetAtoms():
+        if atom.GetAtomicNum() <= 1:
+            continue
+        for direction in _enumeration_directions(atom):
+            result = apply_site_transform(mol, SiteTransform(atom.GetIdx(), direction))
+            if isinstance(result, IdentityRefusal):
+                continue
+            if fragment_formal_charge(result) != target_charge:
+                continue
+            key = fragment_key(result)
+            if isinstance(key, IdentityRefusal) or key in seen:
+                continue
+            seen.add(key)
+            keys.append(key)
+    return tuple(keys)
+
+
+def select_by_net_charge(
+    mol: Chem.Mol, target_charge: int
+) -> str | IonizationRefusal | IdentityRefusal:
+    return choose_ionization(structures_at_net_charge(mol, target_charge))
diff --git a/src/openchem/domain/salt_evidence.py b/src/openchem/domain/salt_evidence.py
new file mode 100644
index 00000000..77ab5a37
--- /dev/null
+++ b/src/openchem/domain/salt_evidence.py
@@ -0,0 +1,105 @@
+"""pKa as an independent salt-composition claim, never a solver input."""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+
+#: Evidence is not on the window. Remove this when something reachable from
+#: ``openchem.main`` imports the module.
+REACHED_BY = (
+    "tooling: consumed by tests/test_salt_evidence.py; evidence is not "
+    "on the window yet"
+)
+
+#: Measured value supplied by the caller. Not a model output.
+ORIGIN_MEASURED = "measured"
+#: Predicted value supplied by the caller. This module does not run a model.
+ORIGIN_PREDICTED = "predicted"
+
+#: Already ionic; the drawing is the state.
+VERDICT_NOT_ASSESSED = "not_assessed"
+#: A required pKa was not supplied.
+VERDICT_MISSING = "missing"
+#: Media or temperatures do not match, so Î”pKa is not a constant.
+VERDICT_INCOMPARABLE = "incomparable"
+#: A value's step_id is not the proposed microspecies.
+VERDICT_WRONG_STEP = "wrong_step"
+#: Both values named the proposed steps under comparable conditions.
+VERDICT_RECORDED = "recorded"
+
+
+@dataclass(frozen=True)
+class PkaValue:
+    value: float
+    origin: str
+    medium: str
+    temperature_k: float | None
+    ionic_strength: float | None
+    uncertainty: float | None
+    step_id: str
+
+
+@dataclass(frozen=True)
+class PkaCompatibility:
+    verdict: str
+    delta: float | None
+    acid: PkaValue | None
+    conjugate_acid: PkaValue | None
+    reason: str
+
+
+@dataclass(frozen=True)
+class EvidenceRecord:
+    charge_valid: bool
+    structurally_consistent: bool
+    pka_compatible: PkaCompatibility
+    experimentally_established: None
+
+
+def assess_pka_compatible(
+    *,
+    already_charged: bool,
+    proposed_acid_step_id: str,
+    proposed_conjugate_acid_step_id: str,
+    acid: PkaValue | None,
+    conjugate_acid: PkaValue | None,
+) -> PkaCompatibility:
+    if already_charged:
+        return PkaCompatibility(
+            VERDICT_NOT_ASSESSED,
+            None,
+            None,
+            None,
+            "Already-charged input is not pKa-assessed; the state is in the drawing.",
+        )
+    if acid is None or conjugate_acid is None:
+        return PkaCompatibility(
+            VERDICT_MISSING,
+            None,
+            acid,
+            conjugate_acid,
+            "pKa was not assessed because a value for the proposed step is missing.",
+        )
+    if acid.step_id != proposed_acid_step_id or conjugate_acid.step_id != proposed_conjugate_acid_step_id:
+        return PkaCompatibility(
+            VERDICT_WRONG_STEP,
+            None,
+            acid,
+            conjugate_acid,
+            "pKa step identity does not match the proposed microspecies.",
+        )
+    if acid.medium != conjugate_acid.medium or acid.temperature_k != conjugate_acid.temperature_k:
+        return PkaCompatibility(
+            VERDICT_INCOMPARABLE,
+            None,
+            acid,
+            conjugate_acid,
+            "pKa values are not from comparable conditions.",
+        )
+    return PkaCompatibility(
+        VERDICT_RECORDED,
+        conjugate_acid.value - acid.value,
+        acid,
+        conjugate_acid,
+        "Î”pKa = pKa(BH+) âˆ’ pKa(HA) under the stated conditions; this is not a crystal.",
+    )
diff --git a/src/openchem/domain/salt_stoichiometry.py b/src/openchem/domain/salt_stoichiometry.py
index 52631e6c..a2635bae 100644
--- a/src/openchem/domain/salt_stoichiometry.py
+++ b/src/openchem/domain/salt_stoichiometry.py
@@ -105,40 +105,71 @@ def compose_mode_a(
                 "do not match the product ions."
             ),
         )
     return ModeAComposition(
         cation_count=balanced.cation_count,
         anion_count=balanced.anion_count,
         charge_valid=True,
     )
 
 
+def compose_supplied_ions(
+    cation: ModeASpecies,
+    anion: ModeASpecies,
+) -> ModeAComposition | ModeARefusal:
+    if cation.kind != KIND_ION or anion.kind != KIND_ION:
+        return ModeARefusal(
+            code="missing_proton_source",
+            reason=(
+                "A molecular neutral plus a supplied ion does not provide "
+                "the protons for a transfer; supply both ions as given."
+            ),
+        )
+    balanced = balance_two(
+        ChargedSpecies(cation.identity, cation.charge),
+        ChargedSpecies(anion.identity, anion.charge),
+    )
+    if isinstance(balanced, BalanceRefusal):
+        return ModeARefusal(code=balanced.code, reason=balanced.reason)
+    return ModeAComposition(
+        cation_count=balanced.cation_count,
+        anion_count=balanced.anion_count,
+        charge_valid=True,
+    )
+
+
 @dataclass(frozen=True)
 class ChargedSpecies:
     """One ion, as the stoichiometry layer is allowed to see it."""
 
     identity: str
     charge: int
 
 
 @dataclass(frozen=True)
 class TwoIonBalance:
     cation_count: int
     anion_count: int
 
 
 @dataclass(frozen=True)
 class BalanceRefusal:
     code: str
     reason: str
 
 
+@dataclass(frozen=True)
+class IonizationRefusal:
+    code: str
+    reason: str
+
+
 def balance_two(
     cation: ChargedSpecies, anion: ChargedSpecies
 ) -> TwoIonBalance | BalanceRefusal:
     if cation.charge <= 0 or anion.charge >= 0:
         return BalanceRefusal(
             code="not_opposite_signs",
             reason=(
                 "A binary salt needs one positive charge and one negative "
                 f"charge; got {cation.charge:+d} and {anion.charge:+d}."
             ),
@@ -157,10 +188,27 @@ def formula_unit_conserved(
     def _total(parts: Sequence[tuple[Mapping[str, int], int]]) -> dict[str, int]:
         out: dict[str, int] = {}
         for counts, n in parts:
             if n <= 0:
                 return {"__invalid__": 1}
             for element, count in counts.items():
                 out[element] = out.get(element, 0) + n * count
         return out
 
     return _total(left) == _total(right)
+
+
+#: Pick among fully specified ionic structures. An empty list is a net-charge
+#: request with no structure; several distinct graphs at one charge are not ranked.
+def choose_ionization(candidates: Sequence[str]) -> str | IonizationRefusal:
+    unique = list(dict.fromkeys(candidates))
+    if not unique:
+        return IonizationRefusal(
+            code="net_charge_only",
+            reason="A net charge is not an ionization state; name a structure.",
+        )
+    if len(unique) > 1:
+        return IonizationRefusal(
+            code="ambiguous_microspecies",
+            reason="Several structures share this charge; v1 does not pick one.",
+        )
+    return unique[0]
diff --git a/tests/test_ionic_species.py b/tests/test_ionic_species.py
new file mode 100644
index 00000000..e1822de3
--- /dev/null
+++ b/tests/test_ionic_species.py
@@ -0,0 +1,44 @@
+import json
+
+import pytest
+from rdkit import Chem
+
+from openchem.chem import ionic_species
+from openchem.chem.ionic_species import load_ionic_species, row_by_id
+from openchem.chem.salt_components import fragment_formal_charge, fragment_key
+
+
+def test_hydrogen_sulfate_and_sulfate_are_different_rows() -> None:
+    hso4 = row_by_id("hydrogen_sulfate")
+    so4 = row_by_id("sulfate")
+    assert hso4 is not None and so4 is not None
+    assert hso4.ion_smiles != so4.ion_smiles
+    assert hso4.charge == -1
+    assert so4.charge == -2
+
+
+def test_every_row_round_trips_to_its_charge_and_key() -> None:
+    for row in load_ionic_species():
+        mol = Chem.MolFromSmiles(row.ion_smiles)
+        assert mol is not None, row.ion_id
+        assert fragment_formal_charge(mol) == row.charge, row.ion_id
+        assert fragment_key(mol) == row.ion_smiles, row.ion_id
+
+
+def test_catalog_is_not_a_pharma_whitelist() -> None:
+    ids = {row.ion_id for row in load_ionic_species()}
+    assert "chloride" in ids
+    # An unusual ion is simply absent, not forbidden.
+    assert row_by_id("hexafluorophosphate") is None
+
+
+def test_load_refuses_a_charge_that_disagrees_with_the_graph(tmp_path, monkeypatch) -> None:
+    payload = json.loads(ionic_species._catalog_path().read_text(encoding="utf-8"))
+    for ion in payload["ions"]:
+        if ion["id"] == "chloride":
+            ion["charge"] = 0
+    path = tmp_path / "ionic_species.json"
+    path.write_text(json.dumps(payload), encoding="utf-8")
+    monkeypatch.setattr(ionic_species, "_catalog_path", lambda: path)
+    with pytest.raises(ValueError, match="chloride"):
+        load_ionic_species()
diff --git a/tests/test_salt_evidence.py b/tests/test_salt_evidence.py
new file mode 100644
index 00000000..913d2849
--- /dev/null
+++ b/tests/test_salt_evidence.py
@@ -0,0 +1,107 @@
+import pytest
+
+from openchem.domain.salt_evidence import (
+    ORIGIN_MEASURED,
+    VERDICT_INCOMPARABLE,
+    VERDICT_MISSING,
+    VERDICT_NOT_ASSESSED,
+    VERDICT_RECORDED,
+    VERDICT_WRONG_STEP,
+    PkaValue,
+    assess_pka_compatible,
+)
+
+
+def _acetic() -> PkaValue:
+    return PkaValue(4.76, ORIGIN_MEASURED, "water", 298.15, None, None, "acetic_acid_h1")
+
+
+def _pyridinium() -> PkaValue:
+    return PkaValue(5.23, ORIGIN_MEASURED, "water", 298.15, None, None, "pyridine_bh1")
+
+
+def test_supplied_ions_do_not_assess_pka() -> None:
+    result = assess_pka_compatible(
+        already_charged=True,
+        proposed_acid_step_id="x",
+        proposed_conjugate_acid_step_id="y",
+        acid=None,
+        conjugate_acid=None,
+    )
+    assert result.verdict == VERDICT_NOT_ASSESSED
+
+
+def test_already_charged_input_is_not_assessed() -> None:
+    result = assess_pka_compatible(
+        already_charged=True,
+        proposed_acid_step_id="acetic_acid_h1",
+        proposed_conjugate_acid_step_id="pyridine_bh1",
+        acid=_acetic(),
+        conjugate_acid=_pyridinium(),
+    )
+    assert result.verdict == VERDICT_NOT_ASSESSED
+    assert result.delta is None
+
+
+def test_missing_pka_is_missing_not_invented() -> None:
+    result = assess_pka_compatible(
+        already_charged=False,
+        proposed_acid_step_id="acetic_acid_h1",
+        proposed_conjugate_acid_step_id="pyridine_bh1",
+        acid=_acetic(),
+        conjugate_acid=None,
+    )
+    assert result.verdict == VERDICT_MISSING
+    assert result.delta is None
+
+
+def test_delta_is_conjugate_acid_minus_acid() -> None:
+    result = assess_pka_compatible(
+        already_charged=False,
+        proposed_acid_step_id="acetic_acid_h1",
+        proposed_conjugate_acid_step_id="pyridine_bh1",
+        acid=_acetic(),
+        conjugate_acid=_pyridinium(),
+    )
+    assert result.verdict == VERDICT_RECORDED
+    assert result.delta == pytest.approx(0.47)
+
+
+def test_sulfate_must_not_reuse_the_first_sulfuric_pka() -> None:
+    sulfuric_h1 = PkaValue(-3.0, ORIGIN_MEASURED, "water", 298.15, None, None, "sulfuric_h1")
+    pyridine = _pyridinium()
+    result = assess_pka_compatible(
+        already_charged=False,
+        proposed_acid_step_id="sulfuric_h2",
+        proposed_conjugate_acid_step_id="pyridine_bh1",
+        acid=sulfuric_h1,
+        conjugate_acid=pyridine,
+    )
+    assert result.verdict == VERDICT_WRONG_STEP
+    assert result.delta is None
+
+
+def test_bh2_must_not_reuse_the_first_conjugate_acid_pka() -> None:
+    bh1 = PkaValue(9.9, ORIGIN_MEASURED, "water", 298.15, None, None, "en_bh1")
+    acetic = _acetic()
+    result = assess_pka_compatible(
+        already_charged=False,
+        proposed_acid_step_id="acetic_acid_h1",
+        proposed_conjugate_acid_step_id="en_bh2",
+        acid=acetic,
+        conjugate_acid=bh1,
+    )
+    assert result.verdict == VERDICT_WRONG_STEP
+
+
+def test_different_media_are_incomparable() -> None:
+    dmso = PkaValue(12.3, ORIGIN_MEASURED, "DMSO", 298.15, None, None, "acetic_acid_h1")
+    result = assess_pka_compatible(
+        already_charged=False,
+        proposed_acid_step_id="acetic_acid_h1",
+        proposed_conjugate_acid_step_id="pyridine_bh1",
+        acid=dmso,
+        conjugate_acid=_pyridinium(),
+    )
+    assert result.verdict == VERDICT_INCOMPARABLE
+    assert result.delta is None
diff --git a/tests/test_salt_ionization.py b/tests/test_salt_ionization.py
new file mode 100644
index 00000000..8cc93dc5
--- /dev/null
+++ b/tests/test_salt_ionization.py
@@ -0,0 +1,67 @@
+from rdkit import Chem
+
+from openchem.chem.salt_components import fragment_formal_charge, fragment_key
+from openchem.chem.salt_ionization import (
+    SiteTransform,
+    apply_site_transform,
+    select_by_net_charge,
+    structures_at_net_charge,
+)
+from openchem.domain.salt_stoichiometry import IonizationRefusal
+
+
+def _acetic() -> Chem.Mol:
+    return Chem.MolFromSmiles("CC(=O)O")
+
+
+def test_deprotonating_acetic_acid_updates_hydrogen_and_charge() -> None:
+    mol = _acetic()
+    oxygen = next(
+        atom.GetIdx()
+        for atom in mol.GetAtoms()
+        if atom.GetSymbol() == "O" and atom.GetTotalNumHs() == 1
+    )
+    result = apply_site_transform(mol, SiteTransform(oxygen, "deprotonate"))
+    assert fragment_formal_charge(result) == -1
+    assert fragment_key(result) == "CC(=O)[O-]"
+    # parent unchanged
+    assert fragment_formal_charge(mol) == 0
+
+
+def test_protonating_pyridine_updates_hydrogen_and_charge() -> None:
+    mol = Chem.MolFromSmiles("c1ccncc1")
+    nitrogen = next(atom.GetIdx() for atom in mol.GetAtoms() if atom.GetSymbol() == "N")
+    result = apply_site_transform(mol, SiteTransform(nitrogen, "protonate"))
+    assert fragment_formal_charge(result) == 1
+    assert "[nH+]" in fragment_key(result) or "c1cc[nH+]cc1" == fragment_key(result)
+
+
+def test_a_bad_atom_index_is_refused() -> None:
+    mol = _acetic()
+    refused = apply_site_transform(mol, SiteTransform(99, "deprotonate"))
+    assert refused.code == "invalid_site"
+
+
+def test_acetic_acid_at_minus_one_is_acetate() -> None:
+    mol = Chem.MolFromSmiles("CC(=O)O")
+    chosen = select_by_net_charge(mol, -1)
+    assert chosen == fragment_key(Chem.MolFromSmiles("CC(=O)[O-]"))
+
+
+def test_acetic_acid_at_plus_one_is_net_charge_only() -> None:
+    mol = Chem.MolFromSmiles("CC(=O)O")
+    refused = select_by_net_charge(mol, 1)
+    assert isinstance(refused, IonizationRefusal)
+    assert refused.code == "net_charge_only"
+
+
+def test_two_inequivalent_sites_at_the_same_charge_are_not_picked() -> None:
+    # 4-hydroxybenzoic acid: carboxylate vs phenolate at -1 are different graphs.
+    # If RDKit collapses them to one SMILES, identity is graph, not formula â€”
+    # switch the pair to tyrosol (OCCc1ccc(O)cc1).
+    mol = Chem.MolFromSmiles("O=C(O)c1ccc(O)cc1")
+    keys = structures_at_net_charge(mol, -1)
+    assert len(set(keys)) >= 2
+    refused = select_by_net_charge(mol, -1)
+    assert isinstance(refused, IonizationRefusal)
+    assert refused.code == "ambiguous_microspecies"
diff --git a/tests/test_salt_stoichiometry.py b/tests/test_salt_stoichiometry.py
index b30ab78d..f588eb6f 100644
--- a/tests/test_salt_stoichiometry.py
+++ b/tests/test_salt_stoichiometry.py
@@ -6,26 +6,29 @@ Contract: docs/SALT_COMPOSITION_DESIGN.md. The solver never sees a molecule.
 from pathlib import Path
 
 import pytest
 
 from openchem.domain.salt_stoichiometry import (
     KIND_ION,
     KIND_METAL_HYDROXIDE,
     KIND_MOLECULAR_NEUTRAL,
     BalanceRefusal,
     ChargedSpecies,
+    IonizationRefusal,
     ModeAComposition,
     ModeARefusal,
     ModeASpecies,
     TwoIonBalance,
     balance_two,
+    choose_ionization,
     compose_mode_a,
+    compose_supplied_ions,
     formula_unit_conserved,
 )
 
 
 def _species(identity: str, charge: int, kind: str, counts: dict[str, int]) -> ModeASpecies:
     return ModeASpecies(
         identity=identity,
         charge=charge,
         kind=kind,
         element_counts=tuple(sorted(counts.items())),
@@ -150,27 +153,60 @@ def test_broken_hydrogen_count_is_not_a_composition() -> None:
     result = compose_mode_a(
         _species("EtNH2", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 7, "N": 1}),
         _species("AcOH", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 4, "O": 2}),
         _species("wrong", 1, KIND_ION, {"C": 2, "H": 9, "N": 1}),
         _species("AcO-", -1, KIND_ION, {"C": 2, "H": 3, "O": 2}),
     )
     assert isinstance(result, ModeARefusal)
     assert result.code == "conservation_failed"
 
 
+def test_sodium_and_acetate_as_given_ions_balance_one_to_one() -> None:
+    sodium = ModeASpecies("[Na+]", 1, KIND_ION, (("Na", 1),))
+    acetate = ModeASpecies("CC(=O)[O-]", -1, KIND_ION, (("C", 2), ("H", 3), ("O", 2)))
+    result = compose_supplied_ions(sodium, acetate)
+    assert isinstance(result, ModeAComposition)
+    assert result.cation_count == 1
+    assert result.anion_count == 1
+    assert result.charge_valid is True
+
+
+def test_a_neutral_passed_to_supplied_ions_is_refused() -> None:
+    acetic = ModeASpecies("CC(=O)O", 0, KIND_MOLECULAR_NEUTRAL, (("C", 2), ("H", 4), ("O", 2)))
+    sodium = ModeASpecies("[Na+]", 1, KIND_ION, (("Na", 1),))
+    refused = compose_supplied_ions(sodium, acetic)
+    assert isinstance(refused, ModeARefusal)
+    assert refused.code == "missing_proton_source"
+
+
 def test_neutral_base_plus_sulfate_without_a_proton_source_is_refused() -> None:
     result = compose_mode_a(
         _species("B", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 7, "N": 1}),
         _species("SO4", -2, KIND_ION, {"O": 4, "S": 1}),
         _species("BH+", 1, KIND_ION, {"C": 2, "H": 8, "N": 1}),
         _species("SO4", -2, KIND_ION, {"O": 4, "S": 1}),
     )
     assert isinstance(result, ModeARefusal)
     assert result.code == "missing_proton_source"
 
 
+def test_one_structure_at_the_requested_state_is_accepted() -> None:
+    assert choose_ionization(["CC(=O)[O-]"]) == "CC(=O)[O-]"
+
+
+def test_a_net_charge_with_no_structure_is_refused() -> None:
+    refused = choose_ionization([])
+    assert refused.code == "net_charge_only"
+
+
+def test_two_structures_at_the_same_charge_are_not_auto_picked() -> None:
+    refused = choose_ionization(["CC(=O)[O-]", "[O-]C=O"])
+    assert refused.code == "ambiguous_microspecies"
+    assert isinstance(refused, IonizationRefusal)
+
+
 def test_the_domain_module_does_not_import_lattice_energy() -> None:
     text = Path("src/openchem/domain/salt_stoichiometry.py").read_text(
         encoding="utf-8"
     )
     assert "lattice_energy" not in text
     assert "rdkit" not in text.lower()
diff --git a/tools/suite-shard-pins.json b/tools/suite-shard-pins.json
index 035b41ca..489bed25 100644
--- a/tools/suite-shard-pins.json
+++ b/tools/suite-shard-pins.json
@@ -4806,20 +4806,21 @@
   "tests/test_inspector_dump.py": 2,
   "tests/test_install_check.py": 1,
   "tests/test_installer_tooling.py": 5,
   "tests/test_interaction_analysis_metals.py": 2,
   "tests/test_interaction_analysis_rules.py": 7,
   "tests/test_interactions_panel.py": 3,
   "tests/test_interface_size.py": 4,
   "tests/test_io_backends.py": 3,
   "tests/test_ionescu_charges.py": 2,
   "tests/test_ionescu_eem_instrument.py": 5,
+  "tests/test_ionic_species.py": 4,
   "tests/test_ionisable_sites.py": 2,
   "tests/test_ionization_cross_check.py": 3,
   "tests/test_ir_export.py": 6,
   "tests/test_ir_spectrum_widget.py": 5,
   "tests/test_ir_view_widget.py": 4,
   "tests/test_isotopes.py": 1,
   "tests/test_java_setup.py": 6,
   "tests/test_jcamp.py": 0,
   "tests/test_jirouskova_charges.py": 1,
   "tests/test_jirouskova_eem_table.py": 5,
@@ -5222,20 +5223,22 @@
   "tests/test_right_dock_width.py": 6,
   "tests/test_rotate_3d_shortcut.py": 6,
   "tests/test_rotation_transaction.py": 3,
   "tests/test_round24_morphinan.py": 0,
   "tests/test_round24_polycycle_templates.py": 3,
   "tests/test_round25_stereo_and_esters.py": 4,
   "tests/test_round26_polyol_esters.py": 7,
   "tests/test_run_app_gate.py": 2,
   "tests/test_run_lifecycle.py": 0,
   "tests/test_salt_components.py": 2,
+  "tests/test_salt_evidence.py": 7,
+  "tests/test_salt_ionization.py": 3,
   "tests/test_salt_mode_a.py": 1,
   "tests/test_salt_stoichiometry.py": 5,
   "tests/test_sasa.py": 0,
   "tests/test_scalar_field.py": 5,
   "tests/test_scatter_plot_zoom.py": 5,
   "tests/test_schindler_sqe_instrument.py": 2,
   "tests/test_score_answer.py": 7,
   "tests/test_score_constants.py": 7,
   "tests/test_score_definition.py": 5,
   "tests/test_score_definition_store.py": 0,
