# Review package 638e5ed5..7b87e211

## log
7b87e211 Catalog named salt ions as graphs, with sulfate and hydrogen sulfate kept apart.

## stat
 CLAUDE.md                                 |   2 +-
 docs/SOURCES.md                           |  21 +++++-
 docs/sources.toml                         |  21 ++++++
 src/openchem/chem/data/ionic_species.json | 113 ++++++++++++++++++++++++++++++
 src/openchem/chem/ionic_species.py        |  90 ++++++++++++++++++++++++
 tests/test_ionic_species.py               |  44 ++++++++++++
 6 files changed, 289 insertions(+), 2 deletions(-)

## diff
diff --git a/CLAUDE.md b/CLAUDE.md
index 1382171d..48744d60 100644
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
+- `src/openchem/domain/salt_stoichiometry.py` / `chem/salt_components.py` / `chem/salt_mode_a.py` / `chem/ionic_species.py` -- two-ion charge balance, Mode B drawing analysis, Mode A from four molecules, and the cited ion catalog (`chem/data/ionic_species.json`; docs/SALT_COMPOSITION_DESIGN.md); no UI
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
