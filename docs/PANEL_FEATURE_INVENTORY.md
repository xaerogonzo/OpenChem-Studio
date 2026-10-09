# Panel feature inventory: Batch, Docking, Quantum Chemistry and 3D Alignment

**Why this exists.** The direction is one main control panel for every calculation
(see the Batch/Quantum/Alignment/Docking note in the session plan). The rule
attached to it is that **no feature may be lost**. This file is the list the rule
is checked against: every control, option, export and edge behaviour of the four
panels, each with where it lives, whether it has a new home yet,
and what is missing. Nothing is removed from either panel until every row here is
`PORTED` or a decision recorded against it says otherwise.

Batch and Docking come first (sections 1-2); Quantum Chemistry and 3D Alignment
follow (sections 3-4). For the widgets inside Quantum Chemistry's tabs (NMR, IR,
surfaces, correlation plots) the panel-level controls and each widget's visible
controls are listed, but **not each widget's internals** (the NMR view alone is about
1,000 lines). They are expected to move intact, and that is the assumption to check.

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

## 3. Quantum Chemistry

Files: `src/openchem/ui/panels/quantum_chemistry_panel.py` (about 3,000 lines),
`src/openchem/services/quantum_chemistry_service.py`, `src/openchem/chem/orca_engine.py`,
`src/openchem/services/qm_surface_service.py`, and the widgets that live in its tabs
(listed under Q18-Q22).

This is the largest panel and the least like a calculator. It runs **one real ORCA job
on one molecule**, can take minutes to hours, streams a log, keeps a **history of runs
saved with the project**, and shows the answer in **eight tabs**. It is not a
`RegistryExecution` calculator, so Batch cannot run it (the Batch picker excludes it by
design) and nothing here can be fanned out over a project today.

### 3a. What goes into a run

| ID | What it does today | Notes |
|---|---|---|
| Q01 | **Molecule** combo. Follows the project selection; preserved by uuid on refresh. Choosing a molecule **sets Charge from its formal charge** and refreshes the Runs list. | Following the selection is why a project with two identically named molecules once computed on the wrong one. |
| Q02 | **Calculation** (7): Single Point, Geometry Optimization, Optimization + Frequency, NMR (raw shielding), NMR + Spin-Spin Coupling, Hardness / Softness (delta-SCF), Interaction energy breakdown (LED). The type decides which result tabs fill. | Choosing an NMR type moves the method to `B3LYP pcSseg-1`, **only if the method is still an unedited preset**. |
| Q03 | **Charge** -10..+10, auto-set from the structure, free to override. | |
| Q04 | **Multiplicity** 1..10, default 1, **never derived** from the structure. | A radical or triplet must be set by hand. |
| Q05 | **Method/basis**: editable combo, six presets (B3LYP def2-SVP, PBE0 def2-TZVP, M062X def2-TZVP, B3LYP 6-31G(d), B3LYP pcSseg-1, B3LYP pcSseg-2). The text becomes ORCA's `!` header verbatim. Ignored for LED, which is defined on DLPNO-CCSD(T). | |
| Q06 | **Solvent (CPCM)**: None plus Chloroform, DMSO, Water, Methanol, Acetone, Toluene, Benzene. Appended to the method string, which makes a solvated and a gas-phase TMS reference **separate cache entries** by construction. | Must stay in the string, not become a separate parameter. |
| Q07 | **CPU cores**: 1..machine cores, stored as `orca/cores`; pinned to 1 and disabled (with a tooltip explaining why) when Microsoft MPI is not installed; automatic default capped at 8. | |
| Q08 | **Average over all conformers (Boltzmann)** checkbox: one ORCA run per conformer, shifts averaged by population. Only effective with 2+ conformers; refuses with a reason if the conformer ensemble cannot be resolved. | |
| Q09 | Every combo and spin box is **scroll-safe** (a wheel passing over it does not change it). | A guard list is kept so a test can find them. |

### 3b. Running

| ID | What it does today | Notes |
|---|---|---|
| Q10 | **Run**: refuses with no structure, **no conformer** ("Generate one with Structure > Generate Conformers... first"), an unusable 3D geometry, or an empty method. The geometry goes through the calculation-input resolver so the identity stamped on the spectra is the geometry actually sent. Disables Run, enables Cancel, clears the log and tabs, shows "queued". | |
| Q11 | **LED guard**: before an LED job, refuses anything that is not exactly two separate species, refuses an overlapping geometry (a live run once returned +40619 kcal/mol), and above a size asks to confirm with an atom/basis-function count and a cost warning. | |
| Q12 | **Cancel**: stops ORCA and removes its scratch directory; a cancelled job leaves no partial result. | |
| Q13 | **More** menu (set-up-once items): **Configure ORCA...** (Settings at the ORCA entry), **Calibrate Reference (TMS)...**, **Calibrate Scaling (11 standards)...**. Each calibration disables its own button while it runs; scaling reports R-squared and n per element. | Real `QPushButton`s inside the menu, because every test and help contract targets those widgets. |
| Q14 | **Tautomers...** with **Full ORCA conformers** (remembered as `tautomer/full_orca_conformers`). Needs only the 2D structure. Enumerates candidates, then asks to confirm above a threshold or whenever anything was truncated, stating jobs, tautomers, stereoisomers and the incompleteness consequences. | Two model versions: a percentage is shown only for a model whose own validation passed. |
| Q15 | **Tautomer NMR...** with **Average NMR over conformers** (remembered as `tautomer/nmr_average_conformers`). Runs NMR on each tautomer of the *selected* distribution run from the geometry it stored; says what it costs and what is left out first; needs a cached TMS reference. Enabled only for a run holding a distribution with at least one stored geometry, and never while a job runs. | |
| Q16 | **Live state**: the job's text streams into the log; on "running" the tabs appear and the log tab is selected so a long job does not look hung; on failure the log stays selected (it holds the reason); on success no tab is forced, each result selects its own tab only when it has something to show. | |

### 3c. What was calculated (history)

| ID | What it does today | Notes |
|---|---|---|
| Q17 | **Currently viewing** (kept apart from "Calculation to run" on purpose, so picking an old run never looks like it changed what Run will submit): **Runs** combo, newest first, labelled `calculation · method · time`. Selecting one repaints every tab from that run **locally, never publishing on the event bus** (publishing would make Results show stale numbers as current). **Delete Run** (confirm; removes the project record only, not the cached wavefunction), **Compare NMR Shifts...** (pick another run with a spectrum; refuses when atom numbering cannot be matched), **View Tautomer Distribution...**, **View Tautomer NMR...** (each enabled only for a run that holds that result; opening never recomputes). | History is saved in the project file as its own `qc_runs` envelope, separate from the result cache. A just-finished run is added to the combo without repainting the tabs the person is looking at. |

### 3d. Where it is shown (the eight tabs)

| ID | Tab | What it holds | Notes |
|---|---|---|---|
| Q18 | **1D Signals** | `NmrViewWidget` in a pop-out: nucleus, frequency, solvent peak, smooth, decoupled, relative integral, zoom to selection, legend, palette, reference scale, reference peaks, explicit H, unit (ppm / Hz offset), labels (shift / atom index / none), and an export menu (JCAMP-DX, SD file with shifts, PDF report). Tautomer peaks overlay here with their own controls. | Moves intact if the widget is reparented. Its internal controls are listed, not individually inventoried. |
| Q19 | **IR** | `IrViewWidget` in a pop-out: overlay a measured spectrum, clear overlay, animate mode on the optimised geometry, reset zoom, copy spectrum image, export JCAMP-DX. | Modes are animated about the **optimised** geometry, not the submitted one. |
| Q20 | **Surfaces** | `EspCompareWidget` in a pop-out: point-charge ESP (Gasteiger / EEM / QEq) beside an ab-initio surface (surface type, HOMO/LUMO, **Compute QM surface**). Needs a run that kept its wavefunction. | Two web views; the most expensive tab. |
| Q21 | **Hybrid** | Merge of the run with the experimental-shift lookup per atom: 6-column sortable table, calibration-check summary, carbons only, needs an empirically scaled run (else says what to do). | |
| Q22 | **HSQC / HMBC / COSY** | Per tab: a 5-column sortable table (atom A/B, shift A/B, J in Hz or a dash), a cross-peak plot in a pop-out with a **Contours** checkbox and **Reset Zoom**, wheel/drag zoom, double-click reset, and **table row <-> plot peak** selection by atom pair (never by coordinates). | One column list and one loop build all three. |
| Q23 | **ORCA Log** | Raw stdout of this job. | Named so it is not mistaken for the app's own Console. |
| Q24 | **Per-tab status glyph** (check / dash / cross) read from the stored run's output status, **Help for this tab** (one button that follows the active tab to its help topic), and a per-tab **empty state** saying what would fill it. | |
| Q25 | **Summary lines** above the tabs: the results label (descriptor lines, or the tautomer summaries), the status line, a note saying whether the table holds raw shielding, TMS-calibrated or empirically scaled values (plus a coupling-failed note), and the 3-column spectrum table. Tables export from their menu (`orca-spectrum`, `nmr-hybrid`, `hsqc-correlations`, ...). **Tautomer distribution dialog** has an *Export table (CSV)*. | Wording is long and sourced on purpose. |

### 3e. Around the panel

| ID | What it does today | Notes |
|---|---|---|
| Q26 | **Results leave the panel through `MainWindow`**, not the panel: descriptors are republished so Properties/Results show them; an optimised geometry is added as an **undoable** conformer; spectra reach the Atom Inspector; the run goes into the project's `qc_runs`. | A move must not break these subscriptions. |
| Q27 | **Other surfaces open this panel**: Properties' `orca.*` rows open it **with the calculation type chosen (nothing runs)**; report links "open NMR" and "open IR" reveal it and select the tab (`show_spectrum_tab`). | Already a launcher into the panel from Properties; retargeting is needed, not rebuilding. |
| Q28 | **Remembered state**: `orca/cores`, `tautomer/full_orca_conformers`, `tautomer/nmr_average_conformers`; six pop-out ids (`quantum.nmr_signals`, `quantum.ir_spectrum`, `quantum.surfaces`, `quantum.correlation_hsqc`, `_hmbc`, `_cosy`). | Keep the ids or the saved pop-out placement is lost. |
| Q29 | **Hard-won structure rules.** Placeholders are found through Qt's child tree and never stored in a dict keyed by a widget (that corrupted the heap, `0xc0000374`, 3 of 3 runs, in an unrelated test); no signal is connected to a lambda capturing `self`; a new job brings a detached pop-out home so a stale picture is not left in another window. | Anything that reparents these tabs inherits the constraints. |
| Q30 | **Help**: rail/dock id `Quantum_Chemistry`, topic `quantum-chemistry` (with anchors), and 38 `quantum.*` ids (see the panel's help table). | |
| Q31 | **Layout facts**: wants 518-576 px wide (the main window records this for it and 3D Alignment), the tab strip hidden until there is something to show. | |
| Q32 | **Drive steps** `qc_run`, `qc_tab`, `qc_nmr_report`, `qc_coupling_report`, `tautomer_run`, `tautomer_report`, `tautomer_nmr_run`, `tautomer_nmr_report`; visual scripts `qm_nmr_referencing`, `qm_shift_identity`, `tautomer_distribution_reachability`, `tautomer_nmr_live`. | These drive **real ORCA**. |

**Status of every Q row: `MISSING` in the new surface**, except Q27, which is `LAUNCH`
(Properties already routes into the panel).

---

## 4. 3D Alignment

Files: `src/openchem/ui/panels/alignment_panel.py`, `src/openchem/services/alignment_service.py`,
`src/openchem/chem/alignment.py`, `src/openchem/domain/alignment.py`.

It aligns **several project molecules onto one reference** and shows the result as an
overlay. The single-molecule registry calculator "3D Alignment" (reference typed as
SMILES) is separate and already in Properties.

| ID | What it does today | Status / notes |
|---|---|---|
| A01 | **Reference** combo. Preserved by uuid; **deliberately not wired to the project selection** (the probe list is defined against it, so following the tree would reshuffle the ticks under the person). Changing it rebuilds the probe list and re-frames every number. | `MISSING` |
| A02 | **Align onto it**: a tick list of every molecule except the reference. Ticks survive rebuilds by uuid, so renaming an unrelated molecule does not clear them. | `MISSING` |
| A03 | **Method**: Extended atom types (MMFF type pairing, Open3DAlign) or Common scaffold (MCS first, then refine). | Also a parameter of the registry calculator. |
| A04 | **Accuracy**: Fast (1 conformer / 5 s), Normal (5 / 15 s, default), Accurate (20 / 60 s). | Also on the registry calculator. |
| A05 | **Flexibility**: Flexible (default; shared atoms pinned to the reference's coordinates) or Rigid. | **Panel only**: the registry calculator has no Flexibility parameter. |
| A06 | A standing **note** under the controls saying Score is higher-is-better and RMSD lower-is-better and that they are different measures. | On screen on purpose. |
| A07 | **Align**: refuses with no reference or no tick; disabled while running; status line shows "Aligning name (k/N)". The job is keyed **per reference**, so alignments to different references can run together and a second one against the same reference is refused with a message. Cancel is checked between molecules. | **There is no Cancel button in the panel**; the service registers a cancel callback, so it can be cancelled from the Jobs panel. |
| A08 | **Result table** (8 columns): Show, Molecule, Score, RMSD (A), Core, Tail, Paired atoms, Geometry. Core and Tail split the RMSD over the rigid and flexible parts (measured: a 0.116 headline RMSD hid a 0.931 flexible part). Paired atoms reads "n (MCS)" or O3A's count. Geometry reads Project / Generated / Constrained. Eight column help contracts, six of them tier 3. Exports from the table menu (`alignment-results`). Height capped (64 to 160 px) so the picture keeps the space. | `MISSING` |
| A09 | **Row semantics**: a failed molecule gets a reason spanning its numeric columns, no colour and no Show box (one unembeddable structure never discards the others); the reference row shows dashes. | |
| A10 | **Show** tick per row hides that structure from the picture only (omitted, not made transparent); its colour is kept so showing it again changes nothing. | |
| A11 | **Overlay viewer**, built on first show (it is a Chromium view and this is one of many docks): **Style** (stick, ballstick, sphere, line) and **Colour** (by molecule: 8 colour-blind-safe colours, reference grey first; or by element). The header controls stay in the dock while the view is popped out. Pop-out id `alignment.overlay`. | |
| A12 | **Stored structures are not moved**; the alignment is for display and comparison. An ensemble **replaces** the previous one; nothing is saved in the project. | Persisting results would be new behaviour, not a port. |
| A13 | **Geometry choice**: stored conformers newest first, otherwise generated, or built with shared atoms pinned for Flexible. Falls back and says so in the Geometry column. | |
| A14 | **Help**: rail/dock id `3D_Alignment`, topic `alignment`, and 15 `alignment.*` ids (flexibility, overlay_color_mode, entry_visible, core_rmsd, flexible_rmsd, geometry_source, reference, method, accuracy, run, display_style, subject, score, rmsd, paired_atoms). | |
| A15 | **Layout facts**: wants 518 px wide; the settings box is about 414 px tall, which once left the picture a 63 px strip. | The reason the table is capped. |
| A16 | **Drive steps** `align`, `align_report`, `ensemble_visible`, `overlay_colour`. | |

---

## 5. Findings made while inventorying

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
4. **Quantum Chemistry is the target of other surfaces** (Q27): Properties' `orca.*`
   rows and the "open NMR"/"open IR" report links reveal the panel and select a
   calculation type or tab. They route by the panel id `Quantum_Chemistry`, so the
   routes need retargeting rather than rebuilding.
5. **Quantum Chemistry's results are not owned by the panel** (Q26). Descriptors,
   the optimised conformer and the spectra leave through `MainWindow`; a port that
   moves only the panel's widgets would still look right and stop feeding Properties,
   the conformer list and the Atom Inspector.
6. **3D Alignment has no Cancel button** (A07), unlike Quantum Chemistry and Batch.
   It can be cancelled from the Jobs panel only. Whether that is intended is not
   recorded anywhere I found.
7. **Alignment's Flexibility exists only in the panel** (A05). The Properties
   calculator for 3D Alignment takes a method and an accuracy but not flexibility, and
   reports no Core/Tail split, so the two are not equivalent and neither can replace
   the other.
8. **The Quantum panel carries the repository's worst crash history** (Q29): a heap
   corruption from a dict keyed by widgets, found in an unrelated test hundreds of
   tests later. Reparenting its tabs is the riskiest single move in this whole plan.

## 6. What the inventory implies for the unified panel

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
- **Quantum Chemistry is a workflow, and a big one.** One molecule, a real external
  program, a saved run history, eight result tabs and six pop-outs. It is not a
  candidate for ticks or for Batch, and nothing in the inventory is an obvious
  "small" piece to move first. The least risky order is probably to leave its widgets
  where they are and give the unified panel a section that **hosts the whole panel
  unchanged** at first, then dissolve it piece by piece with the inventory as the
  checklist. That keeps every row `STAYS` until it is deliberately moved.
- **3D Alignment is small and self-contained** (16 rows, one service, no persistence),
  so it is the cheapest place to prove a "workflow section" pattern before Docking or
  Quantum Chemistry use it. Its one hard constraint is vertical space for the picture.
- **Three kinds of result live outside any table**: a pose table with a 3D drawing
  (Docking), an overlay with a score table (Alignment), and eight tabs with a run
  history (Quantum Chemistry). A single "Results" area would have to host all three
  or leave them with their sections. That is a design question, not an inventory one.
- **Nothing here can be batched over a project except the calculators.** Docking has
  its screening dialog; Quantum Chemistry and Alignment have nothing. A unified panel
  would make that gap visible rather than fix it.

## 7. Parity baseline: what already pins this behaviour

Tests that exercise the existing panels, which become the check that nothing moved:

| Area | Files (test counts) |
|---|---|
| Batch | `tests/test_batch_panel.py` (74), `test_batch_service.py` (22), `test_batch_result_store.py` (18), `test_batch_analytics.py` (26), `test_batch_detail_dialog.py` (10), `test_batch_widgets.py` (10) |
| Project run (new route) | `tests/test_project_run.py` (25), `test_execution_plan.py`, `test_selection_presets.py` |
| Docking | `tests/test_docking_panel.py` (52), `test_docking_service.py` (31), `test_docking_providers.py` (36), `test_docking_domain.py` (16), `test_rescoring.py` (28), `test_binding_site.py` (29), `test_pose_analysis.py` (47), `test_dock_placement.py` (13), `test_main_window_docking_visualization.py` (6), `test_docking_result_inverse.py` (5), `test_docking_commands.py` (1) |
| Screening | `tests/test_screening_service.py` (35), `test_screening_is_configurable.py` (17), `test_virtual_screening_dialog.py` (5) |
| Receptor library | `tests/test_receptor_library.py` (19), `test_receptor_library_dialog.py` (11) |
| Quantum Chemistry | `tests/test_quantum_chemistry_panel.py` (82), `test_quantum_chemistry_service.py` (38), `test_quantum_chemistry_run.py` (16), `test_quantum_chemistry_run_recording.py` (12), `test_tautomer_nmr_panel.py` (11), `test_orca_engine.py` (45), `test_orca_led.py` (52), `test_orca_surfaces.py` (21), `test_qm_surfaces.py` (25) |
| NMR / IR widgets in its tabs | `tests/test_nmr_view_widget.py` (84), `test_nmr_spectrum_widget.py` (69), `test_nmr_signals.py` (67), `test_nmr_correlation_plot_widget.py` (21), `test_nmr_hybrid.py` (18), `test_nmr_scaling.py` (17), `test_nmr_reference.py` (9) |
| Tautomers | `tests/test_tautomer_distribution.py` (66), `test_tautomer_distribution_service.py` (13), `test_tautomer_nmr.py` (14), `test_tautomer_nmr_average.py` (13), `test_tautomer_conformers.py` (32) |
| 3D Alignment | `tests/test_alignment.py` (31), `test_alignment_panel.py` (18), `test_alignment_service.py` (4) |

**A caution about this baseline.** These suites mostly use fakes for ORCA and Vina. In
this project mocked engines have hidden real defects (three, in Vina and ORCA), so
parity for Docking and Quantum Chemistry has to include the **driven runs against the
real programs** (`dock_run`, `qc_run`, `tautomer_run`, `tautomer_nmr_run`), not only
these tests.
