# Panel feature inventory: Batch and Docking

**Why this exists.** The direction is one main control panel for every calculation
(see the Batch/Quantum/Alignment/Docking note in the session plan). The rule
attached to it is that **no feature may be lost**. This file is the list the rule
is checked against: every control, option, export and edge behaviour of the two
panels inventoried so far, each with where it lives, whether it has a new home yet,
and what is missing. Nothing is removed from either panel until every row here is
`PORTED` or a decision recorded against it says otherwise.

Quantum Chemistry and 3D Alignment are **not inventoried yet**.

Read from the source on 2026-10-09 (branch `claude/calculator-organization-ux-32c9fe`).
Nothing below was run live; "status" is what the code says, and each `verify` is
something I could not settle from reading.

## Status legend

| Status | Meaning |
|---|---|
| `SHARED` | the same code now serves both homes (moved, not copied); parity is by construction |
| `PORTED` | re-implemented in Properties/Results and pinned by a parity test or script |
| `LAUNCH` | the feature is a separate dialog or service that stays as it is; only its entry point had to move |
| `PARTIAL` | some of it has a new home; the gap is named |
| `MISSING` | nothing in the new surface does this yet |
| `STAYS` | belongs to the service or a shared dialog, so it does not move with a panel |
| `verify` | could not be settled by reading; needs a live check or a test |

---

## 1. Batch

Files: `src/openchem/ui/panels/batch_panel.py` (the picker and run controls),
`src/openchem/ui/widgets/project_table.py` (the results half, extracted),
`src/openchem/services/batch_service.py`, `src/openchem/ui/dialogs/batch_detail_dialog.py`,
`src/openchem/ui/dialogs/batch_analysis_dialog.py`.

### 1a. Choosing what to compute

| ID | What it does today | Status | New home / what is missing |
|---|---|---|---|
| B01 | **Molecule scope.** A "Molecules" section (collapsed by default) with a tick list, *All molecules* and *No molecules* buttons. Everything starts ticked; ticks survive a rebuild by uuid; a different project resets to all; not remembered between launches. | `PORTED` | Properties "Run on" (This molecule / All N / Chosen...) and the molecule checklist dialog; the chosen set also survives by uuid. `verify`: the dialog has no one-press *No molecules*. |
| B02 | **Scope readout** line: "N molecules in this project." or "k of N molecules selected." Always visible even when the list is collapsed. | `PORTED` | Properties scope labels. |
| B03 | **An empty scope is refused** ("Tick at least one molecule first."), never run as "everything". | `verify` | Check `Chosen` with nothing chosen refuses rather than runs all. |
| B04 | **Property filter** box: filters the *list*, never the results; hidden ticks stay ticked and run; a group with no match is hidden, not shown empty. | `PARTIAL` | Properties "Find a calculator" does this for calculators. It cannot find a **descriptor** or an **alert catalog**, because those are not listed individually in Properties (B06, B07). |
| B05 | **The picker is a tree**: Descriptors / Structural alerts / Calculators, each grouped, with a *Basis* column and the calculator description as a tooltip. | `PARTIAL` | Calculators are in Properties, grouped and A-Z. See B06, B07 for the other two branches. `verify`: whether Properties shows the basis on each calculator row. |
| B06 | **36 descriptors, individually tickable**, grouped by descriptor category. | `MISSING` | Properties has one box, "Include always-on properties": all of them or none. Picking *only* logP and TPSA for a project table is not possible there. |
| B07 | **5 structural-alert catalogs, individually tickable** (PAINS, Brenk and the others). | `MISSING` | One box, "Include structural alerts", all-or-none. |
| B08 | **Calculators offered = every one with a registry execution**, regardless of its default visibility. | `verify` | Properties hides some calculators by default (maturity) and a preset skips them ("N hidden by default, not ticked"). A calculator Batch could run but Properties hides is a silent loss unless there is a reveal. Check which. |
| B09 | **Group tick boxes** on every branch/category, tristate computed by hand; ticking a group never touches children the filter is hiding; each group reads "n / total" ticked. | `verify` | Properties sections have per-section ticks of their own; whether there is a tick-whole-section and a count needs a live look. |
| B10 | **Select all** (ticks only what the filter shows; status says how many, "shown" or "available") and **Clear selection** (selection only; results and filter untouched). | `PARTIAL` | Presets (apply a named set) and Find exist; there is no select-all-shown. `verify`. |
| B11 | **The selection is remembered** between launches (`batch/selected_property_ids`): ids not positions; an id that no longer exists is dropped silently. | `PARTIAL` | One-time, non-destructive copy into a preset named "From the Batch panel". **It keeps calculator ids only: any descriptor or alert id in the saved selection is dropped by the copy** (`clean_ids` is given the calculator ticks as the known set). The old key is left untouched. |
| B12 | **Per-calculator settings.** Double-click a leaf or right-click > *Settings...* opens the calculator's settings dialog. Only calculators somebody actually configured send parameters; the rest run on registry defaults; settings are frozen when the run starts. "That property has nothing to configure." for a calculator with none. | `PARTIAL` | "Settings for project runs..." in the Properties menu. `verify`: no double-click or right-click on a calculator row for this in the project route. |
| B13 | **Per-atom values as:** (sum / mean / and the other reductions) controlling how a per-atom result becomes one number; the column header records which. | `PORTED` | `_scope_aggregate` in Properties, same reduction list. |

### 1b. Running

| ID | What it does today | Status | New home / what is missing |
|---|---|---|---|
| B14 | **Fill table...**: needs a project, at least one property, at least one molecule; above 200 calculations it asks first, stating molecules x properties; declining says "Cancelled -- nothing was computed." The scope and parameters are resolved once and frozen for the run. | `PORTED` | `_run_selected_on_project`: same 200 threshold, built from an `ExecutionPlan`. |
| B15 | **Eligibility is decided inside the run.** Batch attempts every calculator on every molecule and records a failed cell with the reason. | `PORTED` (changed on purpose) | The plan excludes what cannot run *before* starting and lists the exclusions. Cells for what does run were shown identical in `tests/test_project_run.py`; column order differs by design (browse order). |
| B16 | **Cancel** (enabled only while running); partial results stay; message "Cancelled after k of N molecules." | `PORTED` | "Cancel run" on the Project table page. |
| B17 | **Progress** bar and per-molecule status ("k/N: name"); rows appear as they finish. | `SHARED` | Same service, same table widget. |
| B18 | **One run at a time**, project-wide, through the job manager; appears in the Jobs panel and cancels from there. | `STAYS` | `BatchService`; unchanged. |
| B19 | **Row failures**: no structure yet, unreadable structure, one provider or one calculator raising: each isolated, the run continues; refusals recorded with their classified code so a cell and Properties say the same thing. | `STAYS` | Service behaviour; the plan route removes most before running. |
| B20 | **3D input policy**: a stored conformer where one exists, the drawing otherwise (`select_calculation_input`). | `STAYS` | Service. |
| B21 | **Descriptor providers**, including plugin providers registered at run time; alert catalogs computed only when one was asked for. | `STAYS` | Service. |
| B22 | **Structure version.** Results are keyed by structure version so an edited molecule's numbers read stale. | `PORTED` | Per-molecule versions in the plan route. **Batch itself has a latent defect here**: `BatchPanel._current_structure_version` calls the checker without a molecule id, the `TypeError` is swallowed, and every Batch result is keyed at version 0. Found, deliberately left; whether to fix it while Batch exists is undecided. |

### 1c. Reading the results

| ID | What it does today | Status | New home / what is missing |
|---|---|---|---|
| B23 | **The table**: one row per molecule; sortable with numeric sort keys (failed cells sort to one end); failed cell = grey dash + reason tooltip; a result with no single number (per-atom map, spectrum) = blue italic text with "double-click to open"; cell tooltips carry basis, method, parameters, value; header tooltips carry source, basis, "text column". Column widths sampled from 20 rows and capped at the viewport. | `SHARED` | `ProjectTableView`. |
| B24 | **Columns...** menu (also right-click on the header): hide whole categories, *Show all*; status "Showing x of y columns (n group(s) hidden)". View only; exports still write everything. | `SHARED` | |
| B25 | **Export CSV** and **Export Report** (Markdown with provenance). Both write every column, hidden or not. | `SHARED` | |
| B26 | **Details...** (selected row, or double-click) opens the molecule's merged report in the Properties renderer. **If the ticked properties are not yet computed for that molecule it computes them first** ("Computing name..."), refuses while another run is in progress, and uses the same parameters as the table. | `PARTIAL` | The dialog is shared. Results' Project table does **not** compute what is missing; it says nothing is retained. This is a real gap while Batch exists. |
| B27 | **Inspect...** buttons for results with their own view, with the inspector budget refusal ("Too many inspectors open"). | `SHARED` | `BatchDetailDialog`. |
| B28 | **Analyse...**: Correlation (X/Y, and *Correlate Y against everything*, the confound check), Chemical space, Clustering, Distributions, and a Per-atom tab only when per-atom data exists for 2+ molecules. Refuses with a message when no numeric column exists. | `LAUNCH` | `BatchAnalysisDialog` is untouched; the Project table page carries the button and the callback is wired. |
| B29 | **Virtual Screening...** button. | `LAUNCH` | See D22. **Its help text is wrong**, see section 3. |
| B30 | **Retention across runs**: a later run merges into the store; a one-molecule Details run must not replace the project's table. | `PORTED` | The workspace adopts a table only for a run it was told about. |
| B31 | **Not saved in the project file**: the table and store are in memory only. | `SHARED` | Same on both sides. |

### 1d. Around the panel

| ID | What it does today | Status | New home / what is missing |
|---|---|---|---|
| B32 | **Rail entry and dock** `Batch` (Compute group), help-topic mapping `Batch -> batch`, command-palette entry found by typing "batch". | stays until Batch is retired | A redirect is needed on removal so the id, the palette entry and the topic still resolve. |
| B33 | **Help contracts**, 16 of them: `batch.property_filter`, `batch.run`, `batch.cancel`, `batch.select_all`, `batch.clear_selection`, `batch.molecule_scope`, `batch.molecule_scope_select_all`, `batch.molecule_scope_clear`, `batch.export_csv`, `batch.export_report`, `batch.column_groups`, `batch.molecule_details`, `batch.analyse`, `batch.virtual_screening`, `batch.per_atom_aggregate`, `batch.open_inspector`. | `PARTIAL` | Table-side ones are reused with their ids. The picker-side ones (filter, select all, clear, scope buttons) have no control to attach to yet. |
| B34 | **Layout facts** that were measured: minimum width 413 px, tree minimum height 160, control rows are `flow_row` so no single row sets the window's minimum, the scope section collapsed by default to protect the table's height. | `verify` | Re-measure in whatever the unified panel becomes. |
| B35 | **Drive steps** `batch_select`, `batch_select_all`, `batch_settings`, `batch_molecules`, `batch_fill`, `batch_details`, `batch_report`; visual scripts `benchmarks/visual/batch_and_compare_organisation.json`, `batch_calculator_settings.json`, `batch_molecule_scope.json`. | `PARTIAL` | `project_run` and `expect_project_table` cover run and table. No equivalent yet for settings, scope, or details. |

---

## 2. Docking

Files: `src/openchem/ui/panels/docking_panel.py`, `src/openchem/ui/widgets/search_options.py`
(shared with screening), `src/openchem/services/docking_service.py`,
`src/openchem/ui/dialogs/structure_contents_dialog.py`,
`src/openchem/ui/dialogs/virtual_screening_dialog.py`, `src/openchem/services/screening_service.py`.

Docking is a different kind of object from a calculator: it has **stateful inputs**
(a receptor, a search box that is a place in 3D), a **long external process**, a
**pose-level result** and a **drawing in the 3D viewer**. None of that is a tick box.
That decides how it can sit inside a unified panel (section 4).

### 2a. Inputs

| ID | What it does today | Notes |
|---|---|---|
| D01 | **Receptor** combo: the project's macromolecules. Changing it resets the search box, the kept-chain list and the assembly choice, because chain ids and positions mean different things in another structure. | Reset-on-change is the load-bearing part. |
| D02 | **Contents...**: chains, ligands and waters of the receptor; untick chains to exclude them; *Build the biological assembly before docking*. Parsed on demand, not on every selection. Status line "Docking against chain(s) X only." while a restriction is in force. If the assembly cannot be built, docking **stops** rather than falling back to the deposited structure. | |
| D03 | **Derive from ligand...**: boxes the site of a ligand already bound in the receptor. Enabled only when the receptor has bound ligands; its tooltip names them (first six). Uses the receptor's catalogued ligand code, else asks which ligand. Idempotent. Failure reports are distinct for "no site" and "should have a site but could not be located". | |
| D04 | **Ligand** combo: any project molecule. Follows the project selection (ligand only; the receptor is deliberately not touched by a molecule selection). Refuses a ligand with no structure. Prefers the canonical 3D conformer, because a drawn molecule is flat. | |

### 2b. The search box

| ID | What it does today | Notes |
|---|---|---|
| D05 | **Centre** x/y/z (-1000..1000 A) and **Size** x/y/z (1..200 A, default 20). Spin widths are derived from the font and style, not pixel constants, to fit a 420 px dock. | Default centre of zero is the origin, "not a site". |
| D06 | **Box provenance** (none / derived / manual) and the box status line: the annotated site; "no annotated binding site"; a failure; "manually positioned"; the **far-from-reference-site** warning; the **ligand-extent exceeds the shortest side** warning. Warn, never block. The zero-atom case is refused later, at the provider. | The status line is separate from job status on purpose, or the next "Queued" wipes it. |
| D07 | **The box is drawn in the 3D macromolecule viewer** (`box_changed` redraws it), **only while the Docking dock is showing** and a receptor is selected. | **Coupled to the dock's visibility** (`_sync_docking_box_overlay` reads the dock). A unified panel must redefine "while Docking shows", for example "while the Docking section is expanded". |
| D08 | A hand-tuned box survives unrelated refreshes (a rename, an unrelated import); only a receptor change or *Derive* rewrites it. | |

### 2c. Preparation and search

| ID | What it does today | Notes |
|---|---|---|
| D09 | **pH** 0..14, step 0.1, default 7.4, applied to **both** receptor and ligand. | |
| D10 | **Strip waters** (default on), **Strip cofactors** (default off). | |
| D11 | **The box-defining ligand is stripped automatically** (`strip_ligand_codes`), using a helper shared with screening. No control. | Must carry over or docked poses land in an occupied pocket. |
| D12 | **Exhaustiveness** (8, 16, 25, 32; default 25), **Scoring function** (the registered vocabulary; default Vina), **Rescore with** (Off, Vinardo, Vina; Off by default), **Seed** (0 shows as "Random"; a pinned seed is the root of derived per-run seeds). | One object, `SearchOptionsControls`, serves this panel **and** the screening dialog, so the two cannot disagree. Keep it shared. |
| D13 | **Replicates** 1..25, default 1; N independent searches with derived distinct seeds. | |
| D14 | **Poses** 1..50, default 9. | |

### 2d. Running

| ID | What it does today | Notes |
|---|---|---|
| D15 | **Configure Vina...** opens Settings at the external-tools entry for Vina. | |
| D16 | **Dock**: refuses with no project, no receptor or ligand, or a structureless ligand; clears the pose table; "Queued..."; disables itself and re-enables on completed or failed. Job state is shown **only for the pair this panel started**. | |
| D17 | **What the request carries**: the displayed box (never a stale copy), pose count, receptor preparation options (pH, strips, kept chains, assembly, strip codes), search options, replicates. The service builds the assembly once and hands the same text to docking and to the interaction analysis. | Service behaviour, `STAYS`. |

### 2e. Results

| ID | What it does today | Notes |
|---|---|---|
| D18 | **Pose table**: Pose, Binding Affinity (kcal/mol), RMSD l.b., RMSD u.b., and a **Rescore** column hidden unless a rescore was requested (header renamed to the function; shown even if every pose failed). Per-header help contracts at tier 2-3, two with source keys (`trott_olson2010`, `quiroga2016`). Affinity column takes the slack; the others size to contents. Export from the table's menu (`docking-poses`). | |
| D19 | **Three labels under the table**: the replicate spread (three states: not recorded / one run, no spread / a measured range with median and seeds), the rescore "separate scale" note, and the standing limitation note. Each is on screen on purpose, not only a tooltip. | |
| D20 | **Persistence and undo**: the result is pushed as an undoable command into `project.docking_results` (saved with the project). After undo or redo the pose table is rebuilt from the project: the newest result for the selected receptor/ligand pair, or nothing. | |
| D21 | **The window reacts to a result**: loads the receptor and the best pose into the macromolecule viewer, colours the site by the interaction analysis (H-bonds, clashes), and switches the centre tab. Undo clears the drawn pose and the colouring. | Lives in `MainWindow`, outside the panel. |

### 2f. Related surfaces

| ID | What it does today | Notes |
|---|---|---|
| D22 | **Virtual Screening dialog** (Tools menu and the Batch/Results button): docks **every project molecule** into one receptor, ranks them, shows dominance ranks that share a number when score ranges overlap, and a note saying why every row may read rank 1. Own Poses and Replicates controls, the shared four search controls, Run/Cancel/progress. The box comes from the receptor's catalogued ligand code. | **It is a docking feature, but it is reachable from Batch, not from Docking.** Its natural home is the Docking section. |
| D23 | **Receptor Library** (File menu) supplies receptors that carry the ligand code D03/D22 depend on. | `STAYS`. |
| D24 | **Help**: rail/dock id `Docking`, topic `docking`, and 23 `docking.*` ids (pose_rank, binding_affinity, rmsd_lower_bound, rmsd_upper_bound, rescore, receptor, receptor_contents, derive_box_from_ligand, ligand, search_box_centre, search_box_size, num_poses, replicates, affinity_spread, protonation_ph, strip_waters, strip_cofactors, configure_vina, run, exhaustiveness, scoring_function, rescore_with, random_seed). | Must keep their ids; the concept does not change when the container does. |
| D25 | **Drive steps** `receptor`, `dock_receptor`, `dock_run`, `dock_panel`, `screen_run`; visual scripts `docking_search_controls`, `docking_replicates`, `docking_rescore`, `docked_pose_in_6wgt`, `screening_search_controls`, `screening_strips_the_pocket`; benchmarks under `benchmarks/docking/`. | |

---

## 3. Findings made while inventorying

1. **The Virtual Screening help text describes a different feature.** `batch.virtual_screening`
   (shown on the Batch and Results button) says it "filter[s] the project against
   property thresholds ... keeps the molecules satisfying every rule you set". The
   dialog it opens docks every molecule into a receptor and ranks them. Pre-existing,
   not caused by the recent work. It is a copy edit to the contract, and it also
   settles where the feature belongs (D22).
2. **The Batch structure-version defect** (B22), already known, restated here because
   it is a Batch behaviour the new route does not share.
3. **The migration drops descriptor and alert ids** (B11). A person who saved a Batch
   selection of individual descriptors would find only the calculators in the
   imported preset.

## 4. What the inventory implies for the unified panel

These are recommendations to react to, not decisions.

- **Two kinds of section, not one.** Calculators and presets are tick-and-run and fit
  the existing Properties model. Docking (and, from the name, Quantum Chemistry and
  3D Alignment) are *workflows with their own inputs*. Cramming them into ticks would
  lose D01-D08. Expandable **sections** that each hold a workflow's inputs and a Run
  button fit what was described ("submenus or expansions, minimise and maximise").
- **Batch is mostly done, and the gaps are specific.** The results half (B23-B25, B27,
  B31) is the same code in both homes, and B28/B29 are dialogs that stay. What is
  missing: B06 and B07 (individual descriptors and alert catalogs), B26 (Details
  computing what is missing), B11 (descriptor ids dropped by the copy), B12 (the
  settings shortcut), B10 (select-all-shown), plus the rows marked `verify`.
- **D07 is the hard one for Docking.** The 3D box exists only while the Docking dock is
  in front. In a single panel that rule needs a new definition.
- **Keep `SearchOptionsControls` and the pose-table help contracts exactly as they
  are**; they already serve two surfaces and carry sourced claims.

## 5. Parity baseline: what already pins this behaviour

Tests that exercise the existing panels, which become the check that nothing moved:

| Area | Files (test counts) |
|---|---|
| Batch | `tests/test_batch_panel.py` (74), `test_batch_service.py` (22), `test_batch_result_store.py` (18), `test_batch_analytics.py` (26), `test_batch_detail_dialog.py` (10), `test_batch_widgets.py` (10) |
| Project run (new route) | `tests/test_project_run.py` (25), `test_execution_plan.py`, `test_selection_presets.py` |
| Docking | `tests/test_docking_panel.py` (52), `test_docking_service.py` (31), `test_docking_providers.py` (36), `test_docking_domain.py` (16), `test_rescoring.py` (28), `test_binding_site.py` (29), `test_pose_analysis.py` (47), `test_dock_placement.py` (13), `test_main_window_docking_visualization.py` (6), `test_docking_result_inverse.py` (5), `test_docking_commands.py` (1) |
| Screening | `tests/test_screening_service.py` (35), `test_screening_is_configurable.py` (17), `test_virtual_screening_dialog.py` (5) |
| Receptor library | `tests/test_receptor_library.py` (19), `test_receptor_library_dialog.py` (11) |
