# Driven visual checks

Committed scripts that drive the real application, run the geometric oracle in
`src/openchem/ui/visual_check.py` against a surface, and save a screenshot
beside the findings.

```bash
OPENCHEM_DRIVE=benchmarks/visual/properties-width.json uv run --no-sync python -m openchem.main
```

Findings and the painted-item count go to the log as
`OPENCHEM_DRIVE: visual_check <tag> [<surface>] -- N painted item(s), H header title(s), M finding(s)`.
Shots land under `artifacts/visual/`, which is not tracked.

## Why these exist

CLAUDE.md carries a running count of roughly fourteen defects found ONLY by
driving the application and magnifying the screenshot, every one of them with a
fully green suite. Three of those are pure geometry — a value painted on top of
its caption, a caption latched at an ellipsis, a caption collapsed to zero
width — and they are the reason the oracle has the predicates it has.

Until this directory existed, **every one of those checks was written once, run
once, and thrown away.** The technique was the most productive in the project
and the least repeatable.

## THE RULE: a committed script constructs its own state

**AND THE BATCH PANEL BREAKS IT UNLESS YOU CLEAR FIRST**, which was found by
running two of these scripts back to back. `BatchPanel` persists its ticked
property ids under `batch/selected_property_ids` and restores them on
construction, so a selection OUTLIVES THE PROCESS and leaks from one committed
script into the next. Measured: a scope benchmark ticking `lewis_adduct` alone
came back with a Substance-classification column belonging to the benchmark
before it -- a table quietly carrying columns nobody in that script asked for.

Every Batch script therefore opens with `{"do": "batch_select", "clear": true}`.
The molecule scope needs no equivalent: it is deliberately NOT persisted, and a
fresh project starts with everything ticked.

> A committed visual benchmark may not depend on the current selection, the
> current project, live jobs, the clock, or the network.

Not abstract caution. Every clause names a trap already paid for here:

- **`smiles` and `import` do not select what they add.** A script without an
  explicit `select` measures the starter molecule, which has no molblock.
- **`receptor` reads the cache, never the network** — a diagnostic run that
  depends on RCSB being up is not a diagnostic.
- **A step with a wrong panel id is a silent no-op.** `_dock_by_panel_id`
  matches `objectName()`, which uses underscores, so `"Quantum Chemistry"`
  changes nothing and the run photographs whatever was already showing while
  the log looks perfectly healthy. **Read the shot, not the log.**
- **Name the reference.** An alignment run once reported failure because no
  reference was chosen, so the combo sat on the starter molecule.

KicomAI's `uishot` reached the same rule independently, from the other side: its
first golden set included scenes reading live data, and three of them "drifted"
an hour later because `just now` had become `11h ago`.

## What each script covers, and why that surface

Every one is a surface with a *recorded* history of breaking, not a guess.

| script | surface | what broke there before |
| --- | --- | --- |
| `properties-width.json` | Properties panel, squeezed then widened | three width-clip defects; the value painted over its caption; captions latched at `...`; captions collapsed to zero width |
| `periodic-table.json` | Periodic Table dialog, Elements and Isotopes | a dialog minimum taller than a 1366x768 screen, with its action row off the bottom |
| `batch_and_compare_organisation.json` | Batch and Compare panels, at 420 px and in a 1100 px window | a results-table header printing `ostance classificat` -- clipped at BOTH ends, because a `QHeaderView` overflows rather than eliding |
| `batch_molecule_scope.json` | the Batch panel's molecule scope, narrowed then emptied then restored | nothing yet -- it exists because the scope is a state NO SCREENSHOT CARRIES |
| `batch_calculator_settings.json` | one calculator batched with and without its settings | Lewis Adduct failing on EVERY molecule in Batch, because the panel sent no parameters; and then a column so wide its centred header sat off screen |
| `lewis_partner_picker.json` | the settings dialog at every parameter kind, and the three role states | a blank separator line rendering as a row with a LABEL AND NO VALUE -- a fact whose value is missing |
| `result_picture_export.json` | a depiction in the Results reader, exported through the real export path | nothing yet -- exporting a drawing existed in ONE dialog, so every other picture the application draws was read-only |
| `rotate_3d_reach.json` | Rotate 3D from the Structure menu, entered and left | nothing yet -- the mode was reachable only from one button on one tab, and two designs for the menu entry's tick disagreed with the button |
| `settings_window.json` | every Settings section, the rail setting flipped and restored, and Ctrl+, pressed from the canvas | the first Forget button drawn as the dialog's DEFAULT, which Enter from the section list pressed; and the harness's own `dialog` step failing all five times, which made the rail check report the default |
| `atom_selection_sync.json` | the Atom Inspector and the 2D canvas, on a FRESHLY LOADED structure and then on an EDITED one | the pool-id/molfile-position divergence, outbound: clicking a carbon answered "pick a heavy atom" -- this is the same trap inbound, where nothing declines |
| `qm_shift_identity.json` | a REAL ORCA NMR run in the Atom Inspector, then a new conformer search | ORCA shifts carried no identity and showed as current after the conformers changed; and the inspector's report cache, keyed on the drawing alone, kept serving the old shift |
| `qm_nmr_referencing.json` | a REAL ORCA NMR run in the Quantum Chemistry panel, asserting it ends as a referenced delta, not raw sigma | an unreferenced NMR result stayed as shielding until someone pressed Calibrate, and was drawn on the delta axis as a mirror-image spectrum |
| `lewis_gate_floor.json` | the noise floor of the Lewis pairing GATE, on REAL ORCA: carbon monoxide through optimization, single point and delta-SCF, then the single point and delta-SCF AGAIN on the same input, then a second carbon monoxide through the whole chain, and `lewis_gate_floor` reads the two repeats | the largest repeat difference of the HOMO, LUMO and hardness, and the tolerance the preregistered rule gives it (`benchmarks/lewis_gate/PREREGISTRATION.md` section 5). Touches no borane. Measured 2026-10-13: 0.0 eV, so T = 0.01 eV |
| `lewis_gate_pair.json` | the GATE (`benchmarks/lewis_gate/PREREGISTRATION.md`), on REAL ORCA: BH3, BF3 and CO each through optimization, single point and delta-SCF, then BH3/CO and BF3/CO evaluated in the real pairing window and judged against the documented numbers. **Refuses to start until `tolerance.json` holds the tolerance the rule gives the recorded floor** | PASS, FAIL or NOT EVALUABLE with every reason, and the artifact `benchmarks/lewis_gate/artifacts/pair.json`. **PASSED 2026-10-13 at T = 0.01 eV** (`benchmarks/lewis_gate/PREREGISTRATION.md` section 9); a decided outcome is final, so it is not re-run to see whether the number moves |
| `lewis_pairing.json` | the Lewis pairing window (Tools menu) on REAL ORCA: two molecules with nothing stored (every job a row to do, no answer), a job's button opening the Quantum Chemistry panel on the right molecule, calculation and level, then four real jobs (single point and delta-SCF on each of ammonia and water, B3LYP/def2-SVP) with the answer growing from none to partial to complete, Keep, save, reopen, and a new geometry that puts the ammonia runs at an earlier geometry so the window offers them as a choice that settles it | the window never shows a number it did not get from a stored run, says Partial for a partial answer, starts no job, and keeps its answer through a save and a reopen. The kept answer is in the Results reader under BOTH molecules (never also a stored result), survives the reopen and a new geometry as current, and reads stale with the cause named when a molecule is redrawn (`recipe_results` step; shots `lewis_pairing_in_results.png`, `lewis_pairing_stale_in_results.png`). Chosen molecules are NOT the BH3/BF3/CO gate pair: those numbers belong to the preregistered gate. not recorded here |
| `qm_optimized_geometry_is_used.json` | a REAL ORCA geometry optimization, then a single point, then a 3D per-atom calculator, all on one molecule that already holds force-field conformers | an ORCA-optimized conformer was stored without an energy and sorted last, so the job after an optimization still ran on the force-field geometry; and, once chosen, it had lost the way back to the drawing's atoms. VERDICT PASS: the single point was submitted with the optimized conformer's own fingerprint, and the per-atom charges projected through the recorded map with 0 mismatches |
| `score_dialog.json` | the Derived Scores window (Tools menu; `score_dialog` steps), on aspirin and the application's OWN descriptors, driven through its real controls: an empty form asks and cannot be saved; a draft is checked after every keystroke and shows the unit it works out to and the value for the selected molecule, with nothing stored until Save; a syntax error outlines the formula and puts a caret under the place; a unit clash is a problem of the formula, a threshold in the wrong unit names both units, a constant typed half-way marks the constants, two estimates of one quantity outline the inputs, a name close to a calculator's marks the name; leaving a changed form asks, and Delete asks and removes only the definition; a score nothing has calculated says which input, and the open window gets its number when the calculator finishes | what the window says is what Save and Open say (one rule, `check_score_definition`); a number is written as in the formula (`14.` is a problem, not 14); the window starts no calculation; shots `score_dialog_checks.png`, `score_dialog_syntax.png`, `score_dialog_unit_clash.png`, `score_dialog_constant.png`, `score_dialog_consensus.png`, `score_dialog_no_value.png`, `score_dialog_value.png` (the defects the magnified shots found are in `docs/DERIVED_SCORES_DESIGN.md` section 11) | not recorded here |
| `score_results.json` | the Results reader's user-defined scores (`score_define` and `score_results` steps), on aspirin and the application's OWN descriptors: a score defined through the service (the call the definition dialog will make) appears in Results under Derived scores with the label `<label> (user-defined, unvalidated)` and a number; a definition with a unit mismatch, a consensus of two estimates, or a label close to a calculator's name is refused and leaves the project's scores as they were; a score whose input nothing has calculated is a refusal naming the input, and gets its number when the calculator finishes | a score is never also a stored result, is evaluated against the molecule's CURRENT results every time the reader refreshes, and the reader re-reads when a result is recorded (the defect this script found: a calculator finished and the score stayed empty; shots `score_results_value.png`, `score_results_refused.png`, `score_results_list.png`) | not recorded here |
| `results_wrapped_row_height.json` | the charges result's Finding row in Results, fentanyl then O1OCN1, docked at the default width and then narrowed and widened | a wrapped value held the height its text needs at 100 px -- six lines in a 272 px row -- and could never shrink back |

| `charge_identity_after_edit.json` | the Atom Inspector's 3D charge through an erase, an edit and an undo | ethanol's oxygen showed carbon C1's EEM 3D charge while the result read fresh -- GEOMETRY datasets keyed by the conformer's atoms, read by the drawing's |
| `calculator_visibility.json` | the whole enable path, each step asserted: Joback and Detonation hidden by default with a footer naming them; Settings > Calculators; Learn more landing on Joback's own help section; the master toggle offering them WITHOUT running either; Detonation then run and reading Needs input; Reset withdrawing them again while the stored result stays readable. Restores the setting it changes | the tick beside a row and the launcher reading two different rules for what is offered; the real-registry run is the only place the footer and the eliding button meet a docked column's width |
| `edit_burst_baseline.json` | what drawing COSTS: twelve structural edits through the editor's own edit path, a new structure each time, on an ordinary drug and on the nitramine, under each recalculation policy -- edit latency, the longest the event loop was blocked, and how many recalculations a burst caused. Restores the setting it changes. Recorded, never asserted | not applicable: it is the baseline the recalculation policy had to beat, and the table showing that it did (see below) |
| `charge_species_and_refusals.json` | EEM and QEq on species each model declines | not recorded here |
| `energetic_nitramine_ledger.json` | a nitramine (1,3-dinitro-1,3-diazetidine) drawn, ESOL solubility and Detonation run, ending in the driven-run VERDICT: the application's log must hold no unexcused ERROR, and Properties must hold the nitro alert, no hydrazine, the fragment counts recorded as NOT partial, and Detonation as `needs_input` naming its two missing inputs | `fg:hydrazine` matched every nitramine's N-N bond, so `detect_features` raised `UndeclaredChargeState` once per edit; it was logged and never asserted, so the window looked fine. Reverted, this script exits 1 and names `structural_features.py:352` |
| `docked_pose_in_6wgt.json` | a real Vina run, the pose shown in Mol* | the pose was retargeted and the receptor left on assembly 1 -- the viewer and the docking showed different chains |
| `docking_replicates.json` | repeated real docking runs from one panel | not recorded here |
| `docking_rescore.json` | a pose scored again with Vinardo | not recorded here |
| `docking_search_controls.json` | the docking panel's search controls at their defaults | not recorded here |
| `geometry_charges.json` | 3D charges on a fresh conformer and after a new search, plus QEq on LiH | not recorded here |
| `ionescu_charges.json` | Ionescu 2013 EEM on captopril (computed, labelled an extrapolation, a saddle), sulfamethoxazole (refused: sulfur bonded to oxygen) and chlorobenzene (refused: no Cl parameters). No in-domain protein fragment: those structures are ACS supporting information outside the repository, and a committed script builds its own state | not recorded here |
| `lewis_site_depiction.json` | the Lewis acid/base site depiction, two donors and mixed roles | not recorded here |
| `logd_curve_cursor.json` | the LogD curve in Results, with a real click on the chart | not recorded here |
| `mass_spectrum_and_merged_details.json` | one, then three calculators in Results, then an edit | not recorded here |
| `modeless_inspectors.json` | two Calculator Inspectors of one calculator opened by two runs with different methods and asserted OPEN SIDE BY SIDE (`expect_inspectors`: count and titles carrying the method); the first one is still there after the second arrives | the inspector was a modal `exec()`, so a second result meant closing the first and comparing from memory |
| `periodic_charges.json` | the crystal report's EQeq charges: computed, refused for disorder, and over the atom budget | `units="e"` composed onto a sentence whose value is an atom count, painting "... C +0.062 e"; and the refusal row marked ADVANCED, so a disordered CIF showed NO charge row at all |
| `powder_pattern_chart.json` | the crystal report's powder chart, truncated and at Cu radiation | a declared chart reached the report and no renderer drew it; seven guards on the builder passed first |
| `properties_launcher_after_2c2.json` | the Properties launcher after stage 2c2, at 900 and 1600 px | not recorded here |
| `properties_launcher_stage2.json` | the Properties panel before stage 2c, at 900 and 1600 px | not recorded here |
| `atom_edit_menu.json` | the atom right-click menu's Edit...: Ketcher's own Atom Properties dialog is up (asserted from the PAGE, not from the dispatch), Cancel leaves the structure exactly as it was, and Apply of a +1 charge turns CCO into CC[OH2+] as ONE undo entry that Undo reverses | Edit... did nothing at all -- no dialog, nothing logged -- because the menu dispatched the dialog's event with a payload Ketcher's own callers never use and could not have applied its answer even if it had opened |
| `bond_order_keys.json` | a number key over a hovered bond sets its order through the application's own edit: 2 makes ethane C=C, 3 makes it C#C, 1 makes it CC again, each ONE undo entry; the order the bond already has is not an entry; with the setting off the key changes nothing; Undo reverses | Ketcher has no handler for a number over a bond, so the gesture is ours -- and it goes page -> bridge -> engine -> undo stack, a chain no single layer's test covers |
| `conformers_early_stop.json` | Settings > Conformers' experimental early-stop box, ticked through the REAL checkbox (the script sets it false, then true, and puts it back false at the end); fentanyl, 1000-embedding ceiling, through the same options method the Generate button uses; the stored record says `stop_rule: kept_set` and `stop_reason: kept_set_steady`, and the shot is the Settings page | a setting that changes when the search stops is only proven by a real run that stopped early because of it; the offline replay predicted 600 embeddings for this seed and the app stopped at 600 |
| `conformers_finish_now.json` | fentanyl, a 1000-embedding search: mid-run the REAL Finish now button is enabled and the readout says `Sampling shapes N/1000 - M found so far - ...`; pressing it ends the run, the stored record says `finished_early` with the shapes kept, and the button is greyed again afterwards | a search that can be ended and kept is a state a screenshot cannot prove: the button's enabled state, the readout text and the stored stop reason are asserted from the app, and the shots (`D:/_scratch/stoprule/`) show the wrapped toolbar |
| `tautomer_distribution_reachability.json` | the REAL "Tautomers..." button with REAL ORCA (HF STO-3G; propylene glycol, then cyclohexanone): the result is in the Results reader's "Showing:" list, the Runs combo names it and "View Tautomer Distribution..." is enabled the moment the run finishes, the stored result carries the fingerprint the service was handed, the button reopens the dialog after it was closed, and reselecting the molecule (away and back) pops no dialog | a result is reachable from three places (the live dialog, the Results panel, the Runs history) and only the app's own event order shows whether each is fed; the direct-call check and the unit tests refreshed the Runs list by hand and passed while the live app left it empty; `tautomer_report` reads the widgets, not the service |
| `tautomer_nmr_live.json` | the REAL "Tautomer NMR..." button with REAL ORCA (HF STO-3G; acetaldehyde): a distribution, then NMR on each tautomer's kept geometry, then both tautomers' peaks DRAWN over the molecule's own 1H spectrum, the average withheld with its reason, and the Runs combo naming the run whose content is on screen | the fixtures were LF and ORCA's output is CRLF on Windows, so the geometry regex found nothing and the button could never enable; a stored NMR run left the 1D tab on its placeholder, hiding the peaks the widget reported as drawn; `tautomer_nmr_report` reads the widgets and the screenshot is what showed it |
| `bond_click_cycle.json` | with Settings > Drawing's click switch off a click on a bond changes nothing; on (ticked through the REAL checkbox), each click cycles ethane CC -> C=C -> C#C -> CC as one undo entry apiece; with the Hand tool active, or an ATOM under the pointer, a click leaves the drawing alone; the script sets the switch itself and leaves it off | a click is a gesture the page decides on (tool, movement, hover) and the application acts on, and it is opt-in because it takes away click-to-select; the two guards (tool, atom) each fail their step when removed |
| `ketcher_hover_keys.json` | Ketcher's hover-aware hotkeys, with the hover set through the editor's own API: an element key over a hovered atom replaces it (the control), `/` over a bond opens its properties dialog, and a number key over a bond changes NOTHING -- so bond hover+number is not native and is ours to build | the drawing spike first said a number over a bond changes it and that no hover could be produced from automation; both were wrong, and a run of this script fails the day an editor upgrade makes the bond case native |
| `keyboard_shortcuts.json` | rebinding through the real Settings > Keyboard page, asserted on the window's own actions: a rebind takes effect (the REAL new key fires the command and the old one no longer does), a key another command holds is refused with the reason, a bare letter is refused because the canvas owns it, and a shortcut can be cleared | a registry can set a shortcut Qt never consults, and a page can show what it stored rather than what the window does; only pressing the key says which |
| `atom_menu_changes.json` | the atom right-click menu's own changes, each PRESSED from the menu the application builds and asserted on the structure and the undo stack: an oxygen changed to nitrogen (CCO -> CCN, gaining its hydrogens), that nitrogen given a +1 charge (CC[NH3+]), and the atom deleted (CC), one undo entry each | Ketcher's own menu had these and replacing it took them away; a first attempt through Ketcher's atom and charge tools armed the tool and changed nothing |
| `compare_methods.json` | two charge models run on ethanol, then the Calculator Inspector's "Compare with..." menu: offering NOTHING while only one method is held, then offering the other and opening the atom-by-atom table (columns, atom rows and the summary asserted, the window photographed) | comparing methods was hard because the store keeps one result per calculator, so a second model replaced the first and the two could never be on screen together |
| `service_rows.json` | the Properties rows for calculators run from another panel: the Quantum Chemistry and Docking sections revealed and photographed, then the NMR, LED and Vina rows each PRESSED and asserted -- the right panel came forward and, for ORCA, its calculation combo holds that job. Nothing is run | a person looking for an ab initio NMR in Properties found an italic sentence and nothing to press |
| `results_dock_stage2.json` | Details with the reader hidden, visible, and popped out | not recorded here |
| `docking_section.json` | a real Vina docking from Properties, then the workflow moved to its own tab and back: nine poses, the box on the receptor, the settings intact; ENDS WITH THE WORKFLOW IN ITS TAB because moving writes the real settings | 2026-10-10: VERDICT PASS; DMT into 6WGT, best pose about -7.07 kcal/mol |
| `hbond_sites.json` | Hydrogen-Bond Sites on GABA as drawn and at pH 7.4, read in the detached Results window | not recorded here |
| `torsions_and_ionisable_sites.json` | Torsion Table on an ibuprofen conformer and Ionisable Sites through the real pkasolver, each read in the detached Results window | not recorded here |
| `geometry_and_surface.json` | Geometry with its options (kJ/mol, optimised copy, lowest of 8, radius scale) and Molecular Surface Area (3D) with a 1.6 A probe on the major microspecies at pH 7.4, read off the Results dock | not recorded here |
| `descriptors_survive_a_conformer.json` | aspirin then a C12E6 surfactant, each given a conformer through the real service: the Results reader's always-on descriptors and alert catalogues (asserted by `descriptors_report`, against the same computed on the drawing) are the drawing's, the ten shape descriptors have values, and the Project table's cells (`expect_project_table` `cells`) hold SA 1.58, Bertz CT 343.22, 3 acceptors; with the service and the batch each put back to running the whole provider on the conformer it fails with 6.445, 608.99 and 4 | not recorded here |
| `descriptors_restored_with_a_conformer.json` | aspirin given a conformer, saved the way a build from before results were kept saved it (`save_project` with `"results": false`: conformers, no results), reopened and selected: the Results reader holds values for all ten shape descriptors and the drawing's for everything else (`descriptors_report`), and the Project table's cells still do (a guard: that path already read the conformer); with `_restore_or_compute` put back to asking for the drawing only it fails with all ten FAILED "Needs a 3D conformer" and exits non-zero | not recorded here |
| `project_properties.json` | a project run over two chosen molecules with only two always-on properties and one alert catalog picked, then Details on a molecule the table left out: it computes the missing calculator on the table's settings, opens, and leaves the table at two rows | not recorded here |
| `goal_wizard.json` | the goal wizard's quick path on one molecule (real calculators) and a customised, unticked-pKa run over the project, with the project table asserted; waits for the run so the worker threads are done before quit | 2026-10-10 |
| `workflow_groups.json` | the whole Properties list at full height with both workflows moved in and every group open, then closed, for comparing the two; ends with both back in their tabs | 2026-10-10: open 1973 px, closed 1447 px at the default dock width |
| `help_explainers.json` | the Help window on the new calculator explainers: a search for `SD-POE` through the window's own box, then the 3D partial-charge, pH-dependent charge and dipole topics at 1100x900; read the shots, because it was a shot (not the green log) that showed level-5/6 headings drawn smaller than body text | 2026-10-11: VERDICT PASS |
| `periodic_table_radius.json` | the periodic table dialog on carbon, whose Facts pane must read `van der Waals 1.7 A (Bondi 1964)`: the radius is the shared table's and names its source, where it once showed RDKit's value unlabelled; one shot at 1200x900 | 2026-10-12: VERDICT PASS |
| `ai_bridge_run.json` | the assistant's calculator bridge, run in the real window from a real worker thread and asserted at each step: a fresh turn reports a calculator as never run; an automatic request completes and Properties shows it Ready; an invalid choice, a missing required input and a service-run calculator are each refused with a typed reason and start nothing; a 50-heavy-atom molecule becomes a preview that Cancel leaves uncomputed and Approve then completes | 2026-10-12: VERDICT PASS, 13 assertions. The unit tests use a fake world, so this is the only check that the session's selection follows the UI, that the result store is wired to the open project, and that events cross the thread boundary |
| `ai_assistant_tools.json` | the assistant panel itself with a SCRIPTED provider (no network, no key): Send freezes the turn, the tool loop runs on its worker thread against the real host, and the panel shows what it should -- an automatic run recorded and visible in Properties, an invalid setting refused and listed in the ledger, a 50-heavy-atom molecule shown as a preview card whose REAL Cancel and Approve buttons start nothing / start it once, the note that goes to the next message, and an ORCA calculator described (what it needs, whether this machine is ready) with no run started and an "Open" button that reveals the panel that owns the job; and `list_goals` read with nothing started. Also opens the assistant from the menu on a layout restored from a real install | 2026-10-12: VERDICT PASS, 14 assertions. Found two defects no unit test could: `MainWindow.reveal_panel` ignored built-in panel ids (the card's "Open" did nothing), and on Windows with a saved layout a plugin panel came out of the first `show()` with no place in the layout and opened as a bare 256 x 240 rectangle over the Project Explorer -- read off the shot, not the log |
| `alignment_section.json` | a real alignment run from Properties, moved to its tab and back: the same two rows, a hidden structure and element colours survive both moves; ends in its tab | 2026-10-10: VERDICT PASS; Naproxen onto Ibuprofen, MCS, score 47.89 |
| `compare_spectra.json` | two database-lookup NMR runs of ethyl acetate at different sphere settings are compared through the NMR view's REAL "Compare with..." menu: the window opens with both columns, told apart by `max_spheres`, and a summary naming the atom they disagree on most (the carbonyl, 173.99 against 171.73 ppm) | a spectrum is one number per nucleus, so the per-atom Compare takes it; the first run showed two columns with the same heading and, after the first fix, a heading carrying a whole per-atom diagnostics table |
| `esol_warning.json` | RDX through the real Solubility calculator, then the Results reader focused on it: ESOL still answers (0.03 log mol/L), a `Baseline reliability` row sits first in the section directly above the number, and the status line under the panel begins with the same warning | the warning was first in the report's limitations and the photograph showed it buried: the merged reader pools every report's limitations under one status line (the Substance note came first and cut it off), and a tooltip is read by nobody; only the row is seen. The run asserts the answer is not a refusal and that nothing was logged |
| `status_chip_routes.json` | where a "Needs input" / "Needs setup" chip press goes: the Detonation chip on the nitramine opens the calculator's settings with the Needs line naming both inputs and the cursor on the loading density; the window's tool-setup route opens Settings > External Tools on the pkasolver, ADMET and NMR-database tabs. The setup half emits the panel's signal rather than pressing a chip, because both tools are installed on the maintainer's machine | those two states used to open a reader that could only describe them |
| `results_layout_narrow_and_short.json` | the Results dock moved beside and on top, resized | a very short dock scrolled: 234 px needed against a 162 px viewport, 72 of it chrome |
| `results_reader_memory.json` | the reader's remembered selection across close, reopen and an edit | a reader's position had never had to survive anything |
| `results_reader_stage1.json` | every result kind reaching the reader, and the selector's search | not recorded here |
| `screening_search_controls.json` | the screening dialog's controls | not recorded here |
| `screening_strips_the_pocket.json` | a real screening run, and what the service was handed | not recorded here |
| `solubility_units_live.json` | the reader's Units combo, switched and remembered | not recorded here |

**THE THIRD COLUMN IS A CLAIM, AND `not recorded here` MEANS NOBODY WROTE THE HISTORY DOWN -- NOT THAT NOTHING BROKE.** Twenty of these scripts were committed without a row at all (found 2026-09-16: the table held 12 of 36), so their surfaces are stated from what the script actually drives and the history is left blank where it cannot be supported. Filling one in is worth doing when you know the answer; inventing one is worse than the blank.

**`results_wrapped_row_height.json` LOGS EACH ROW AGAINST ITS TEXT, BECAUSE THE
ROW ITSELF CANNOT BE ASKED.** `QLabel.heightForWidth` never answers below the
label's own minimum height, so a row holding a stale height reports that height
as what it needs. `fact_rows_report` lifts that floor for the one call, measures
a fresh label as a cross-check, and logs `needs_h` beside `h` and
`over_by_a_line=` per tag. Measured 2026-09-14 after the fix: 0 at 420, 300 and
700 px, with the Finding at 6, 8, 12 and 4 lines. The O1OCN1 note's length
comes partly from the pkasolver cross-check sentence, so read the invariant,
`over_by_a_line=0`, rather than a line count.

**`qm_shift_identity.json` RUNS REAL ORCA AND ASSERTS IDENTITY, NOT A
BANNER.** A generic "stale" line would read the same if the wrong conformer
happened to be compared against the current one, so `qc_run` remembers the
identity the service was handed, and `inspector_report` with
`expect_spectrum` logs `EXPECT spectrum ... ok` only when every held spectrum
is in that state AND carries exactly that identity (`FAILED` at error level
otherwise). Measured 2026-09-14 on methanol at HF/def2-SVP, about 2 minutes:
fresh with `be281a3b...`, then stale against `3e8e4d19...` after the second
search, the held identity unchanged. Needs ORCA configured.

**`lewis_partner_picker.json` PHOTOGRAPHS A DISTINCTION THE PROVENANCE ALREADY
RECORDS**, which is the point of it: an orientation worked out from the Drago
table, one worked out from the structures, one the user forced, and one that
could not be decided are four different results, and if they read alike on
screen the record is useless to the person looking at it. They read
"from the Drago-Wayland table...", "as you set it." and "not determined from
the structures...", with the acid and base swapping as forced.

**`batch_molecule_scope.json` LOGS THE RESOLVED SCOPE BESIDE EVERY SHOT**, and
that is the point of it rather than a convenience. A panel scoped to two
molecules and one scoped to five are the same image until the table lands, so
the `batch_molecules` step prints what `selected_molecules()` resolved to and
what the readout says. It also drives the real list widget rather than the
resolver behind it, for the reason `jobs_cancel` presses the real button: a
step that called `selected_molecules` directly would prove the resolver works
and say nothing about whether the control is wired to it.

Its middle arm is the one worth keeping: unticking everything and pressing Fill
table must SHOW a refusal, because `batch_service` reads an empty scope as
"everything given" and a silent fall-through there would look exactly like
success.

**`settings_window.json` WRITES THE REAL SETTINGS, AND PUTS THEM BACK.**
A driven run uses the developer's own settings store, so the rail setting it
turns off is turned on again before it quits. Lowering the versions kept is
driven too, and asks. The harness answers No and logs the question: measured,
"Keep 1 version -- 1 older result set for 1 molecule will be removed" after
two conformer searches, with the stored value still 8. The Ctrl+, step logs
the ACTIVE WINDOW beside the result, because a window shortcut cannot fire
while another application is active, and then "opened nothing" would say
nothing about the key.

**`atom_selection_sync.json` ERASES AN ATOM BEFORE IT MEASURES ANYTHING**,
and a run that skipped that would pass while testing nothing. A fresh
`setMolecule` rebuilds Ketcher's pool dense, so ids and positions agree by
accident -- which is how this class of bug shipped the first time. The
script therefore reports the selection once on the dense pool, erases the
nitrogen, and reports again on `poolOrder [0,1,3,4,5]`; the second arm is
the only one that can fail.

Its log carries what the shot cannot: `selection_report` prints the pool
order, the pool ids, the molfile positions and the element labels together,
so "the right atom" is asserted rather than recognised. The shot is still
worth magnifying -- it is what shows the marquee is actually drawn.

`properties-width.json` squeezes **and then widens** deliberately: a latched
caption is only observable once the room comes back, so a single-width run
cannot see it.

**`batch_and_compare_organisation.json` IS THE SCRIPT THAT SHOWS WHAT THIS
ORACLE CANNOT DO, and it is kept partly for that.** It found a real,
user-visible clip that `visual_check` reported **0 findings** on, at both
widths, on both runs. A header is painted by the VIEW; `painted_items` walks
CHILD WIDGETS. The same reach limit shows in the population itself -- 12-13
painted items on Batch and 5 on Compare against 40 on Properties -- so a clean
result on an item-view-shaped panel is a far weaker statement than the same
result on a form-shaped one. The defect has a guard of its own kind in
`tests/test_batch_panel.py`, measured against the header's own font metrics.

## A CLOSED COMBO BOX PAINTS ONE ROW, AND ITS LIST IS ANOTHER WINDOW

`results_selector_order.json` is the case that needed a new target. The "Showing"
list is where the section headings live, and neither `grab()` on the results
window nor `PrintWindow` on the application reaches it: a closed combo paints
only the current entry, and its popup is a separate top-level window.

`{"do": "shot", "widget": "results_list"}` pops it and grabs `QComboBox.view()`,
which is an ordinary widget. `showPopup()` FIRST, because an unshown view has
never been laid out and grabs at its default size -- the same trap CLAUDE.md
records for `repaint()` and `resize()`.

**The log carries what even that shot cannot.** `{"do": "results"}` prints every
row with `HEADING` and `disabled` beside it, because a selectable heading and an
unselectable one render identically until somebody arrows onto one -- the
`jobs_report` rule, applied to a list instead of a timer.

## Reading the result

**The painted-item count is logged even when nothing is wrong**, and that is
load-bearing. "Nothing overflowed" and "the walk found nothing to measure" read
identically in an empty findings list, and the second is how an over-broad
exclusion reports as a clean run — a green result and a smaller universe.

**A check that cannot fail is not a check.** Before trusting a clean run,
confirm the oracle can still say NO — squeeze the window further than the
scripts do and watch findings appear.

## What this is not

- **Not a CI gate.** `offscreen`'s default font is more than twice as wide as
  the one a user sees, so a geometry claim taken there is a claim about the
  font; this project has already had a test fail by 40 px on a panel that was
  measurably clean in the running application. These run on a real desktop.
- **Not a judgement about appearance.** The oracle owns geometric invariants
  that are mechanically measurable. The screenshot owns human judgment — and
  some classes stay human on purpose, such as a glyph resolving to a colour
  emoji square, which was measured to be undetectable by counting coloured
  pixels because ClearType's sub-pixel fringes are genuinely coloured.
- **Not golden-image diffing.** Described in `docs/LIVE_VERIFICATION.md`,
  deliberately not built here: adding goldens beside a brand-new oracle would
  be two unproven mechanisms landing at once.

### `rotate_3d_leaving.json` — the mode had one way out, and it hid it

`_apply_rotation_toggle` hid the bar and returned, so `end_rotation` had one
production caller and un-checking the button HID that caller's control. The
overlay is `inset:0; z-index:20`, so it stayed up swallowing every click.

**`rotate_report` prints three facts, and the third is the one that was
wrong**: the menu tick, the button, and whether `.openchem-rotate` is still
in the document. The first two agreed throughout — both correctly reading
"off" while the page went on rotating — which is why a test asserting they
agree could not see it.

Must show `agree=True` at every tag, including after F7 with focus in the
canvas (so the key reaches Qt through the web view) and after Escape from a
panel (so `WindowShortcut` answers where the page listener cannot).

### `redraw_in_2d.json` — the way back, and the two that do not work

Measured before this shipped, after Use in 2D Editor: **Clean Up** flattens
the z column and keeps the projected positions, leaving the picture the
overlapping mess it was; **Layout** draws it properly and turned `[C@@]`
into `[C@]`, a different compound, which then correctly cleared the
conformers.

Must show `z_spread` falling to 0, `conformers` unchanged, `smiles`
unchanged, and Undo putting the 3D drawing back. The two shots are the half
no number carries — the projection is unreadable and the redraw is not.

### `conformer_search_stability.json` — the same molecule, three times

Reported as "sometimes I get six, sometimes I get nine, sometimes eight for
the exact same molecule". The search is seeded and stops on a plateau now,
so the three `report` lines must agree — measured 9 distinct, 450
embeddings, 9 batches, plateau, identical across three runs.

**Slow on purpose**: about 40 s a run against ~8 s before. That is the trade
for a count that does not move, and it is why the step allows 90 s.

**`energetic_nitramine_ledger.json` ENDS IN A VERDICT, AND SO NOW DOES EVERY RUN.**
`drive_ledger` keeps every WARNING-and-above record the application logs,
de-duplicated by (logger, exception, innermost frame, message with its numbers
collapsed), and the run ends in `VERDICT PASS|FAIL` with an exit status and a
`<script>.report.json` beside the script (`OPENCHEM_DRIVE_REPORT` names another
path). `expect_clean` never passes on its own -- a script that never drew the
molecule that breaks it has an empty ledger -- so this one pairs it with
`expect_results`, which asserts what Properties actually holds. Measured
2026-09-24 with the hydrazine fix reverted: exit 1, one entry,
`UndeclaredChargeState @ openchem/chem/structural_features.py:352`, and the
fragment-count facts empty. Restored: PASS, exit 0.

Measured again 2026-09-24, after feature detection became tolerant: with the pre-fix hydrazine pattern
restored, the run no longer loses every alert. It logs ONE warning naming both skipped instances
(`fg:hydrazine at atoms [1, 3]; ... [5, 6]`), still counts `nitro (2)`, and exits 1 on
`fragment_counts: partial is True, wanted False`. `expect_clean` passes there, because a skipped instance is a
WARNING and `expect_clean` counts errors -- so `partial` is the assertion that catches it, and the census
(strict over its corpus) is the systematic one.

A scripted run also writes its own log, `drive-<pid>.log`, because two processes
cannot share one rotating file on Windows (`WinError 32` on every record past the
rotation size while a person's own session was open); the newest twenty are kept.
The ESOL-only parameters are deliberate: the Solubility default also runs the
AqSolDB comparison in the ADMET sidecar, about five minutes.

**`edit_burst_baseline.json` IS A BASELINE, NOT A TEST, AND IT MEASURES THE PYTHON SIDE ONLY.**
Each edit is applied by `MoleculeEditorWidget.apply_edited_molblock`, the method the editor calls once
Ketcher has reported a molfile (an `EditStructureCommand` on the real undo stack, then the annotation
refresh); Ketcher's own JS and the bridge back to Python are not included, because a recompute policy does
not touch them. Measured 2026-09-24 on the maintainer's machine, idle, 12 edits 150 ms apart, in two
states of the same code: the profiler's first commit (every edit recomputed everything), and after the
recalculation policy (`RecalcScheduler`, default "after I pause", 800 ms) with two further reductions found
by profiling one burst (`"profile": true`).

| burst | edit latency (median / p95) | longest loop block | full descriptor fan-outs | results recorded |
|---|---|---|---|---|
| **before** -- aspirin, a new structure each edit | 1,121 / 1,338 ms | 3,993 ms | 12 (one per edit) | 600 |
| **before** -- nitramine, a new structure each edit | 671 / 787 ms | 2,382 ms | 12 | 600 |
| **before** -- aspirin, undo/redo between two structures | 1,130 / 1,365 ms | 2,013 ms | 0 (the result store replays) | 0 |
| **after** -- aspirin, after I pause (800 ms) | 18.4 / 23.5 ms | 93 ms | 1 | 50 |
| **after** -- nitramine, after I pause | 19.3 / 22.1 ms | 86 ms | 1 | 50 |
| **after** -- aspirin, only when I ask, then Recalculate Now | 19.4 / 23.0 ms | 95 ms | 1 | 50 |
| **after** -- aspirin, while I draw (a run per turn) | 14.1 / 16.0 ms | 124 ms | 12 | 600 |
| **after** -- two structures alternated as canvas edits | 17.1 / 20.0 ms | 90 ms | 1 | 50 |

The "while I draw" row is the like-for-like of the old behaviour -- twelve full recomputations, 600
results -- and its longest block is 124 ms against 3,993 ms, which is what the two reductions below bought
independently of the pause. **The profile of the first "after" run** (cProfile over the burst, GUI thread)
named what remained after the pause: the Results reader rebuilt once per descriptor EVENT (144 rebuilds of
about 60 rows, 1.4 s -- now one per turn of the event loop), and the Atom Inspector's atom table rebuilt on
every undo-stack index change with IUPAC locants (12 rebuilds, about 90 ms each, 80% of an edit's synchronous
cost -- now deferred to the pause). 41 descriptors' events flooding the reader is also why a REPLAY used to
cost 1.1 s with no recomputation at all.

Two things the first run got wrong and the second corrected. **Alternating two structures measures
the cache, not drawing**: the first version did exactly that and reported one recompute for twenty
edits, which would have read as "there is already a debounce". The result store simply held both
structures' results and replayed them. Drawing is a NEW structure each time, hence `grow`; and each
"after" burst starts from a DIFFERENT base structure, because a second burst over the first's structures
is replayed from the store (its `results_recorded` reads 0) and would flatter the run. The numbers depend
on the machine; what a change to the recompute policy has to show is the same table, smaller, run the same
way. Both tables are recorded here.

