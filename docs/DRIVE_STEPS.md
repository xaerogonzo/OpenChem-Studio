# Drive steps

The `OPENCHEM_DRIVE` step catalogue, moved out of [`CLAUDE.md`](../CLAUDE.md) on 2026-11-03 so that file stays inside the text Cursor pastes into every agent prompt (the paste stops at 100 KB). The rule, do not drive the machine's mouse, stays in `CLAUDE.md`. The lines below are the catalogue as it stood.

[`src/openchem/app/debug_drive.py`](../src/openchem/app/debug_drive.py) is the implementation. Read this file before writing a script.

    {"do": "import",     "path": "..."}      no file dialog
    {"do": "select",     "molecule": -1}
    {"do": "receptor",   "pdb_id": "6WGT"}   from the CACHE, never the network
    {"do": "receptor",   "pdb_id": "1HSG", "plain": true}
    {"do": "dock_receptor", "index": -1}     CHANGES the panel's receptor
    {"do": "dock_run"}                       the REAL button, real Vina
    {"do": "dock_panel", "tag": "after"}     box, its source, the status line
    {"do": "panel",      "id": "Properties"}
    {"do": "expand",     "section": "admet"}
    {"do": "calculator", "id": "admet_ml", "parameters": {...}}
    {"do": "calculator", "id": "...", "reveal": false}  no Calculator
                                          Inspector window -- see below
    {"do": "expect_inspectors", "count": 2, "titles": ["(qeq"]}  how many
                                          inspectors are OPEN side by side
    {"do": "atom_action", "atom": 2, "submenu": "Change", "text": "N",
     "expect": {"smiles_equals": "CCN", "undo_delta": 1}}  press an ENTRY of the
                                          atom menu the app builds, assert the
                                          structure and the undo stack
    {"do": "ketcher_hover", "bond": 0, "press": "2", "expect": {"bond_type": 1}}
                                          set Ketcher's HOVER through its own editor API
                                          (no pointer), press a key inside the editor,
                                          assert the page; "click": true sends a mouse-down
                                          and up instead; see docs/KETCHER_SPIKE.md. A
                                          script that changes a setting through the REAL
                                          Settings dialog writes the real store: put it
                                          back at the end (bond_click_cycle.json does)
    {"do": "atom_editor", "atom": 2, "set": {"charge": "1"}, "apply": true,
     "expect": {"dialog": true, "smiles_contains": "+", "undo_delta": 1}}  the atom
                                          menu's Edit... on the REAL page, asserted
                                          from the page; `ketcher_eval` runs one
                                          JS expression there and logs its string
    {"do": "shortcut", "command": "search_facts", "sequence": "Ctrl+Alt+F9",
     "press": true}                       rebind through the REAL Settings > Keyboard
                                          page, assert the ACTION and the page's
                                          status, and press the real new/old keys
    {"do": "compare_results", "property": "geometry_partial_charge",
     "expect": {"columns": 2, "atoms": 9}}     the inspector's REAL "Compare
                                          with..." menu, then the window
    {"do": "service_row", "calculator": "orca.nmr", "expect": {"panel": "Quantum_Chemistry"}}
                                          PRESS a row that opens another panel;
                                          `reveal_row` scrolls one into a shot
    {"do": "project_run", "calculators": ["topology_analysis"], "scope": "all",
     "descriptors": true}                 tick calculators, pick a scope (this/all/chosen)
                                          and press the REAL "Run selected"
    {"do": "project_run", "calculators": ["polar_surface_area"], "scope": "chosen", "chosen": [1, 2],
     "descriptor_ids": ["mol_wt"], "alert_ids": ["pains"]}   a SUBSET of the always-on properties
                                          and alert catalogs (the picker's answer, by id)
    {"do": "results_details", "molecule": 3, "expect": {"computed": ["polar_surface_area"],
     "rows": 2, "wait_ms": 5000}}         press Details in the project table for one molecule; the
                                          dialog is shown, not exec'd, and what it computed is read
    {"do": "expect_project_table", "rows": 2, "columns_contain": ["Atom count"],
     "showing": true}                     what the Results dock's PROJECT TABLE holds,
                                          read off the workspace the dock is built from
    {"do": "expand", "section": "workflow:alignment"}   open a Properties WORKFLOW section
    {"do": "workflow_move", "workflow": "docking", "to": "properties"}  move a workflow
                                          between its own tab and Properties by pressing the
                                          REAL button; `align_report` and `dock_panel` take
                                          `expect` (`home`, `rows`/`poses_at_least`,
                                          `viewer_built`, `settings_expanded`, `groups_expanded`)
                                          and read where the widget is off its containers
    {"do": "goal_wizard", "goal": "identity", "scope": "this", "press": "run_recommended",
     "expect": {"ran_all": ["elemental_analysis"], "status_contains": "Running"}}
                                          the goal wizard's REAL buttons ("customise" then
                                          "run", with "tick"/"untick", or "run_all"); `shot` takes
                                          "widget": "goal_wizard". `expect.parameters` is the settings
                                          the run carries. `run_all` reads the Properties status, and
                                          the confirmation is the harness's modal answer.
    {"do": "results", "stay": true, "jump": "Formula", "show_all": true, "open_link": "NMR",
     "expect": {"focus": "elemental_analysis", "search": "Formula", "all_results_visible": true}}
                                          `stay` keeps the reader that is open. `jump` presses the
                                          fact name, `show_all` the All results button, `open_link`
                                          the fact's Open button by its tooltip, `open_viewer` the
                                          reader's own Open button (NMR, IR, Calculator Inspector, or pKa view).
    {"do": "nmr_panes", "hide": ["2d", "3d"], "reset": true,
     "expect": {"2d": true, "splitter": true, "spectrum": true}}
                                          Hide 2D / Hide 3D on the open NMR view, or Reset Settings.
    {"do": "pka_view", "tag": "aminophenol",
     "expect": {"sites": 3, "pictures": 0, "message_contains": "same drawing atom"}}
                                          the open pKa window: stored site count, species pictures,
                                          and the refusal sentence when pictures cannot be built
    {"do": "workflow_group", "workflow": "docking", "group": "search", "expanded": false}
                                          open or close a collapsible group INSIDE a workflow
                                          (alignment: settings; docking: box, prep, search)
    {"do": "properties_height_report", "workflow": "alignment"}  each level from the workflow up to
                                          the window: height against the minimum it asks for,
                                          STARVED when shorter; `properties_width_report` says why
                                          the list scrolls sideways; `properties_grab` saves the
                                          whole list at full height. A script that moves a
                                          workflow writes the real settings: end it in its tab
    {"do": "properties_scroll", "to": "workflow:alignment"}  scroll the Properties list
                                          ("end", "top", a pixel offset) so a tall section's
                                          picture is in the shot
    {"do": "chip", "calculator": "detonation", "expect": {"status": "needs_input"}}
                                          PRESS a status chip and assert where
                                          the press went; `tool_setup` is the
                                          window half of a "Needs setup" press
    {"do": "expect_coverage", "chips": {"griffin_hlb": "Can run"}, "rows": {"orca.proton_affinity": "✓"},
     "silent": [...], "tooltips": {...}}  what the Properties rows SAY about the drawn structure before any run
                                          (`domain/structure_coverage.py`), read off the chips and service-row
                                          labels; Settings > Recalculation switches it off
    {"do": "inspector_report", "tag": "after-edit"}  the Atom Inspector's
                                          pinned line, HELD results and state
    {"do": "inspect", "id": "geometry_partial_charge", "parameters": {"ph_dependent": true}}
    {"do": "inspect_report", "tag": "ph", "filter": "N", "select_row": 0}  the
                                          structure the panes draw, labels, table
    {"do": "result_report", "calculator": "geometry_partial_charge",
     "expect_refusal": "REFUSE_NOT_CONVERGED"}  WHICH refusal Properties
                                          holds; "Not applicable" names none
    {"do": "units", "key": "mg_per_ml"}   the reader's Units COMBO, and what
                                          the chart and unit rows then say
    {"do": "reader_layout_report", "tag": "beside"}  whole fact ROWS on
                                          screen, through every clipping parent,
                                          and every CHROME row (reader_chrome)
    {"do": "fact_rows_report", "tag": "docked"}  each value row's height
                                          against its TEXT's, never the row's
                                          own answer, which is floored
    {"do": "dock_resize", "panel": "Results", "width": 380}
    {"do": "chart_cursor", "x": 7.4}       a REAL click on the line chart,
                                          and the kept reading beside the fact
    {"do": "shot",       "path": "..."}
    {"do": "lewis",      "details": true}     the Full Lewis window
    {"do": "shot",       "path": "...", "widget": "lewis"}
    {"do": "dialog",     "name": "HelpDialog"}   built by ui/dialogs/inventory
    {"do": "dialog",     "name": "PeriodicTableDialog", "tab": "Isotopes"}
    {"do": "dialog",     "name": "HelpDialog", "topic": "calc-dipole-moment"}  the Help window on a
                                          topic, or "search": "SD-POE" typed into its own box
    {"do": "dialog",     "name": "SettingsDialog", "section": "results"}
    {"do": "control",    "name": "railHidesPanels", "value": false}  a NAMED
                                          control of the open dialog, for real
    {"do": "close_dialog"}                before a key that needs MainWindow active
    {"do": "shot",       "path": "...", "widget": "dialog"}
    {"do": "overlay",    "on": true, "gallery": true, "step": 1}
    {"do": "cip",        "on": true}          R/S and E/Z, through the menu
    {"do": "erase",      "element": "N"}      a REAL canvas edit
    {"do": "menu",       "text": "Rotate 3D"}  THIS app's menu bar
    {"do": "menu",       "text": "Undo", "prefix": true}  "Undo <command>"
    {"do": "menu",       "text": "Derived Scores...", "in": "Tools > Calculators"}  an entry by its MENU PATH
                                          (the menus are grouped; the CIP toggle is in two); `dialog` takes
                                          `"real": true` for SettingsDialog, built with the window's own
                                          shortcut registry so a shot shows the real Keyboard groups, and
                                          `control` types into a QLineEdit (the page's `shortcutSearch`)
    {"do": "picture",    "index": 0, "path": "..."}  the reader's
                                          chart, through the REAL export
    {"do": "rotate_report", "tag": "entered"}  the tick, the button AND
                                              whether the PAGE is still in it
    {"do": "key", "key": "F7", "focus": "canvas"}  a REAL key, at the
    {"do": "key", "key": "Escape", "focus": "explorer"}   focus widget
    {"do": "key", "key": "Comma", "modifiers": "ctrl", "close_modal_after_ms": 1500}
                                          a shortcut that opens a MODAL: the
                                          log names it, and the ACTIVE window
    {"do": "geometry_report", "tag": "flat"}   z spread AND the conformers
    {"do": "adopt"}                            the REAL "Use in 2D Editor"
    {"do": "select_atom", "atom": 4}       the inspector ROW, and
    {"do": "selection_report"}             BOTH id spaces off the page
    {"do": "report",     "tag": "after"}      conformers, undo depth, SMILES
    {"do": "conformer_report", "tag": "x", "expect": {"canonical_method": "orca_opt",
     "canonical_mapped": true, "conformers": 3}}   each stored conformer (method, energy, whether it
                                          has the way back to the drawing's atoms, its GEOMETRY fingerprint,
                                          the same string `qc_run` logs) and which one a calculation gets;
                                          it also reads the 3D VIEWER and the status bar: `viewer_index`,
                                          `viewer_on_canonical`, `viewer_label_contains`/`_excludes`,
                                          `orca_conformers`, `origin_slot`, `status_contains` -- "the geometry
                                          is stored" and "the viewer shows it" are different claims;
                                          also `badge_contains`/`badge_empty` (the Properties header),
                                          `explorer_contains`/`explorer_excludes` (the Project Explorer row)
                                          and `methods` (every conformer's method in slot order)
    {"do": "orca_optimize_button", "via": "button", "conformer": 1, "expect": {"chosen_slot": 2,
     "calc_type": "Geometry Optimization", "job_started": false}}    put the viewer on a slot and press the REAL
                                          "ORCA optimize" button (or `"via": "menu"`, Tools > ORCA Geometry
                                          Optimization...), then assert what the Quantum Chemistry panel was SET UP
                                          to do and that NOTHING started; Run is a separate `qc_run` step
    {"do": "jobs_report", "tag": "running"}   rows AND whether it is POLLING
    {"do": "jobs_cancel", "row": 0}           the real button in a real row
    {"do": "synthesis_panel", "tag": "x", "press": "plan", "route": 1, "step": 0, "scroll": "end",
     "expect": {"routes_at_least": 1, "picture": true, "status_contains": "routes found"}}
                                          the Synthesis panel's REAL buttons and lists, and what it SHOWS (status, routes,
                                          whether a step's picture is drawn, the limitations; `details_scroll` reaches the last
                                          lines of the step's text, its consistency checks and alerts); press and report in
                                          SEPARATE steps, since Plan waits for the configuration to be read off the GUI thread
    {"do": "synthesis_setup", "python": "...", "config": "..."}  the planner's settings for THIS run ("" = not set up);
                                          writes the real registry, so `quit` or `{"restore": true}` puts them back
    {"do": "qc_fixture_run", "run_id": "fixture-optfreq", "fixture": "pa_water_optfreq", "status": "completed", "age_s": 900}  give the SELECTED molecule an ORCA run in the project's run store WITHOUT
                                          starting ORCA (a completed run is the real provider's reading of a committed real output; `failed` and `cancelled` hold none), so a script can read what the
                                          assistant's `read_quantum_runs` tells; benchmarks/visual/ai_quantum_runs.json
    {"do": "synthesis_fixture_plan", "fixture": "aspirin_it100", "screen": true}  give the SELECTED molecule a plan a real planner once made (the real parser and annotator,
                                          stored as a finished search stores one), so a script can save, reopen and read a plan without the planner; pair with `save_project`,
                                          `menu` "New Project" and `open_project`
    {"do": "ai_card", "card": "synthesis", "action": "approve"}   the Approve (or "cancel") of a card for a synthesis SEARCH the assistant asked for; `ai_expect` takes
                                          `synthesis_requests` (cards waiting) and `notes_contain` / `notes_exclude` (what is held to tell the model with its next message)
    {"do": "conformers_finish", "expect": {"enabled": true, "readout_contains": ["found"]}}
                                          the REAL Finish now in the 3D viewer, asserted
                                          before it is pressed; "press": false only looks
    {"do": "conformers_provenance", "expect": {"stop_reason": "finished_early"}}  how the
                                          stored run ended; `conformers` takes "with_settings":
                                          true for what Settings > Conformers adds, and
                                          "optimize_lowest": true to tick the Generate window's ORCA box
                                          (its real checkbox; `expect_offer` asserts what the window offered)
    {"do": "screen_run",  "receptor": 0}      the REAL Run button, and the
                                              PREP DICT the service got
    {"do": "qc_run", "calc_type": "NMR (raw shielding)", "method": "HF def2-SVP"}
                                              REAL ORCA, and the IDENTITY
                                              the service was handed; add
                                              `"conformer": 1` (zero-based slot) to
                                              point the Conformer box first, or
                                              `"automatic"` to put it back: the pick
                                              PERSISTS between runs
    {"do": "inspector_report", "expect_spectrum": "stale"}  ASSERTS the held
                                              spectrum carries that identity
    {"do": "tautomer_run", "method": "HF STO-3G"}  the REAL "Tautomers..." button,
                                              REAL ORCA, and the identity handed on
    {"do": "tautomer_report", "expect": {"in_results": true, "runs_label": "Tautomer",
     "view_enabled": true}, "view": true}     where the result is REACHABLE from, read
                                              off the widgets (Results list, Runs combo,
                                              the View button, no auto-popped dialog)
    {"do": "proton_affinity_run", "expect_refusal": "Cl"}   the REAL "Proton affinity..." button (answer its cost question with
                                              OPENCHEM_DRIVE_MODAL=yes), or a refusal asserted before anything is queued;
                                              follow a run with `qc_wait`; `proton_affinity_report` reads the STORED
                                              outputs (`pa_kj`/`gb_kj` windows or `null` for no value), the stored run
                                              and the panel's text; benchmarks/visual/proton_affinity_run.json
    {"do": "bond_dissociation_run", "bonds": [0, 1]}  the REAL "Bond dissociation..." button and its REAL bond-choice dialog
                                              (ticked and pressed through its own widgets from a timer, since it is modal;
                                              `"cancel": true`, or `expect_refusal` before the dialog opens); follow a run with
                                              `qc_wait`; `bond_dissociation_report` reads the STORED output (`dh_kj`, each bond's
                                              kJ/mol by label prefix or `null`, `reason_contains`), the stored run and the panel's
                                              text; benchmarks/visual/bond_dissociation_run.json
    {"do": "tautomer_nmr_run", "method": "HF STO-3G"}  the REAL "Tautomer NMR..." button on the
                                              newest distribution run (answer its cost question with
                                              OPENCHEM_DRIVE_MODAL=yes); `tautomer_nmr_report` reads
                                              the traces DRAWN, the stored result and the combo
    {"do": "save_project", "path": "..."}     the REAL save, results included; "results": false
                                          writes the file an older build wrote (conformers, no results)
    {"do": "dock_move", "panel": "Results", "area": "top"}   as a drop
    {"do": "dock_move", "panel": "Results", "beside": "Properties"}
    {"do": "dock_tabify", "panel": "Results", "onto": "Properties"}
    {"do": "dock_float", "panel": "Properties", "on": true}
    {"do": "reset_layout"}                    View > Reset Panel Layout
    {"do": "dock_report", "tag": "after"}     areas, rects, OVERLAPS, placed
    {"do": "log_report", "tag": "after"}      what the APPLICATION logged
    {"do": "dock_menu", "panel": "Results", "press": "move_bottom", "expect": {"present": ["move_left", "expand"], "disabled": ["move_bottom"],
     "text": {"lock": "Unlock"}}}           open a panel's title-bar layout menu through its REAL aboutToShow and press one entry (its objectName
                                          without `dockMenu_`: move_left, expand, restore, float, dock_back, lock, return, alongside_<Panel>);
                                          `dock_state` asserts where a dock is afterwards, once the layout has settled (area, hidden, floating,
                                          user_placed, expanded, min_width / max_width, no_overlaps); `dock_button` presses or asserts a panel's own
                                          title-bar button (`"item"` for one entry of its menu); benchmarks/visual/dock_layout_menu.json
    {"do": "expect_clean", "allow": ["..."]}  FAILS the run on an unexcused ERROR
    {"do": "expect_results", "expect": {"solubility": "ready",
                             "fragment_counts": {"facts_contain": ["nitro (2)"]}}}
                                          what Properties HOLDS, asserted
    {"do": "descriptors_report", "tag": "x", "values": {"sa_score": 1.58}, "equals_drawing": true,
     "alerts_equal_drawing": true}        the always-on descriptors the READER holds, against the same
                                          computed on the DRAWING (a conformer must leave every one the
                                          provider does not declare geometric alone); the geometric ones
                                          are reported and need `geometric_values`
    {"do": "pka_worker_report", "tag": "x"}  the pKa sidecar: state, pid, spawns, requests,
                                          its own startup/prediction times (never creates one)
    {"do": "ai_bridge_run", "calculator": "polar_surface_area", "parameters": {"pH": 7}}
                                          the assistant's calculator bridge in the REAL window: freeze a
                                          turn, prepare the request and, if it is automatic, call `run`
                                          from a worker thread as the tool loop would (give it `after_ms`)
    {"do": "ai_bridge_decide", "approve": true}   a person's Approve or Cancel on the pending preview
    {"do": "ai_bridge_expect", "expect": {"state": "completed", "has_number": true, "reads": [...],
     "not_run": [...], "problems": ["not_a_choice"], "route": "auto"}}  asserts what the last run did
    {"do": "ai_send", "text": "...", "script": [{"tool": "run_calculator", "input": {...}}, {"text": "..."}]}
                                          the assistant PANEL with a SCRIPTED provider: its real Send, the
                                          tool loop on its worker thread, the real host (give it `after_ms`)
    {"do": "ai_send", "text": "...", "live": {"provider": "ollama", "model": "qwen2.5:14b"}}   the same, with a REAL provider and no script: the model named here answers (nothing is
                                          written to the plugin settings) and what it asked and was told is logged; benchmarks/visual/ai_live_ollama.json
    {"do": "ai_expect", "expect": {"findings": ["waiting_approval"]}}   the kinds the application's reply check has said under the assistant's replies so far, in order (`plugins/ai_assistant/reply_check.py`);
                                          `ai_wait` logs them too. benchmarks/visual/ai_reply_check.json
    {"do": "ai_wait", "timeout_ms": 400000}   hold the script until the assistant has finished its turn (its Send button enabled again, steadily); a LIVE model takes
                                          10 s to several minutes, so this replaces a guessed `after_ms`; giving up is an ERROR. `OPENCHEM_DRIVE_CAPTURE=<file>` writes the first live
                                          request (system prompt, messages, tools) as JSON, to replay against a server outside the app
    {"do": "ai_card", "action": "approve"}   press a REAL button on the preview card showing
                                          ("approve" | "cancel" | "open" | "dismiss"; add "card": "score" for a score
                                          the assistant PROPOSED, whose Approve is the only way it is saved)
    {"do": "ai_expect", "expect": {"ledger_contains": [...], "pending": 1, "service_previews": 1,
     "tool_results_contain": [...], "tool_results_exclude": [...], "tools_offered": [...], "notes": 1, "panel_visible": "Quantum_Chemistry",
     "score_proposals": 1, "scores_stored": 0, "scores_owner": [...], "sent_contains": [...]}}
                                          what the panel shows and what the model was told, asserted
    {"do": "lewis_pairing", "first": 0, "second": 1, "method": "B3LYP def2-SVP", "role": "acid",
     "press": "job:dscf_second", "expect": {"status": "partial", "jobs_to_do": 1, "panel_calc_type": "delta_scf"}}
                                          the Lewis pairing window (Tools menu) and its REAL controls: the form's
                                          combos, "choose" a run by id, "press" Keep or a job row's button (which
                                          asks for the Quantum Chemistry panel and starts nothing); `expect` reads the
                                          screen, the project's recipe runs and where the press went
    {"do": "recipe_results", "focus": true, "expect": {"entries": 1, "stale": 0, "title_contains": ["BH3 + CO"],
     "summary_contains": ["was edited"], "stored_as_results": 0}}
                                          what the Results READER holds of the recipe answers kept in the project, for the
                                          selected molecule: how many, how many stale, the line above the facts, and that none
                                          is also a stored result; `shot` takes "widget": "results_reader"
    {"do": "score_define", "label": "Polar window", "formula": "ramp(psa, 140, 60)", "inputs": [["psa", "descriptor:tpsa"]],
     "result_unit": "1", "constants": [], "defaults": [["logp", 3.5]], "expect": {"made": true}}      define a user-defined score through `ScoreService` (the call the
                                          definition dialog will make); a refusal is asserted with `"made": false, "problem": "unit",
                                          "message_contains": [...]` and must leave the project's scores as they were
    {"do": "score_results", "focus": true, "which": "Polar window", "expect": {"entries": 1, "has_value": true,
     "value_between": [0.95, 0.96], "evidence_contains": ["Formula:"], "reason_contains": [], "stored_as_results": 0, "defaulted": ["logp"]}}
                                          what the Results READER holds of the scores, for the selected molecule: the number or the
                                          reason there is none, the label, the evidence, and that none is also a stored result
    {"do": "score_dialog", "new": true, "fill": {"label": "Polar window", "inputs": [["psa", "descriptor:tpsa"], ["ob", "calculator:oxygen_balance:Oxygen balance (CO basis)", "-50"]], "formula": "ramp(psa, 140, 60)",
     "constants": [{"name": "hi", "value": "140", "unit": "\u00c5^2"}], "result_unit": "1"}, "press": "save", "confirm": "yes",
     "expect": {"ok": true, "marked": [], "preview_contains": ["For Aspirin: 0.955"], "stored": 1, "project_unsaved": true,
     "results_listed": ["Polar window"], "asked": ["Unsaved changes"]}}
                                          the Derived Scores window (Tools menu) driven through its REAL controls: `new`, `choose` a list entry,
                                          `fill` (presses Remove/Add and types into the edits, so it checks after every keystroke), `press`
                                          save/revert/delete/new (a disabled button is logged, not pressed), `confirm` answers its two questions;
                                          `expect` reads the window (message, `where`, fields outlined as `marked`, `pointer_column` of the caret, preview, buttons, list) and the project
                                          (definitions stored, unsaved, listed in Results); `shot` takes "widget": "scores"
    {"do": "table_scores", "export_csv": "C:/tmp/table.csv", "expect": {"columns": ["Polar window (user-defined, unvalidated)"], "note": "",
     "grid": {"Aspirin": {"Polar window": "0.955"}}, "tooltips": {"Aspirin": {"Polar window": ["Inputs: psa = 63.6"]}},
     "column_tooltips": {"Polar window": ["Formula:"]}, "csv_header_contains": ["Polar window"], "csv_cells": {"Aspirin": {"Polar window": 0.955}},
     "csv_text": {"Aspirin": {"inputs given a default": "ob"}}}}
                                          the user-defined SCORES in the Results dock's project table, read off the grid a person looks at (the exact score
                                          headers in order, the note under the status, what a cell SHOWS, tooltips) and off the file the REAL "Export CSV"
                                          button writes (the file dialog answered); pair it with `project_run` and `expect_project_table`; `shot` takes
                                          "widget": "project_table"; `"panel": "batch"` reads the Batch panel's OWN table (after `batch_fill`) and
                                          `shot` then takes "widget": "batch_table"
    {"do": "tick_score_inputs", "tag": "x", "expect": {"menu_label": "Tick what my scores read (2)", "calculators": ["oxygen_balance"], "descriptor_choice": null,
     "descriptors_box": true, "run_enabled": true, "status_contains": ["Ticked 1 calculator(s)"]}}
                                          the Presets menu's REAL "Tick what my scores read" entry in Properties (a menu with no such entry fails), asserted off the
                                          ticks, the always-on choice and the status line; `project_run` then takes `"keep_ticks": true` to run with the ticks as they are
    {"do": "qc_setup", "method": "HF STO-3G"}   set the Quantum Chemistry panel's method (and "calc_type") and press NOTHING:
                                          for a run something else starts, such as the Generate window's ORCA box
    {"do": "qc_wait", "timeout_ms": 600000}   hold the script until the Quantum Chemistry service has no job running (give up = an
                                          ERROR); use it after `qc_run` instead of guessing an `after_ms` for a job of unknown length
    {"do": "qc_panel_report", "tag": "fukui", "expect": {"calc_type": "Fukui functions (Hirshfeld)", "run_calc_type": "fukui",
     "run_status": "completed", "per_atom_outputs": 4, "results_contains": ["Largest f+"], "status_contains": []}}
                                          what the Quantum Chemistry panel SHOWS after a job (its Calculation entry, the results line, the
                                          status line) and what the newest stored run holds, asserted; `shot` saves the panel
    {"do": "fukui_gate_begin"}  {"do": "fukui_gate_record", "species": "CO", "level": "HF/6-31G**", "attempt": 1}
    {"do": "fukui_gate_floor"}  {"do": "fukui_gate_judge"}  {"do": "fukui_gate_report"}
                                          the Fukui GATE (benchmarks/fukui_gate/PREREGISTRATION.md; the scripts are generated by
                                          `benchmarks/fukui_gate/make_scripts.py`): `begin` ends the run before any job unless the noise
                                          floor is measured and usable; `record` appends what the newest STORED Fukui run says (its datasets,
                                          charge, method, ORCA version, and whether it ran on the ORCA-optimized geometry) as one attempt;
                                          `floor` is the largest difference between two runs that should agree; `judge` is `app/fukui_gate.judge`
                                          and writes the outcome beside the drive's own verdict (a FAIL of the gate is a result, not a broken
                                          script); `report` writes the reported arm, which never decides
    {"do": "fukui2_begin"}  {"do": "fukui2_record", "species": "phenol", "level": "B3LYP/6-31G*", "attempt": 1}
    {"do": "fukui2_floor"}  {"do": "fukui2_judge"}  {"do": "fukui2_report"}
                                          the SECOND Fukui gate (benchmarks/fukui_gate_2/PREREGISTRATION.md, arithmetic `app/fukui_gate_2.py`, scripts
                                          from `benchmarks/fukui_gate_2/make_scripts.py`): the first gate's steps widened for what v2 needs -- an
                                          anion's run holds ONE dataset, every record carries the provenance the judge checks (grid, functions, reference
                                          charge, starts, the commit and whether `src/` differs from it, acrolein's dihedral), and `floor` measures two
                                          floors (pyridine and formate) and uses the larger
    {"do": "lewis_gate_begin"}  {"do": "lewis_gate_floor", "a": -2, "b": -1}  {"do": "lewis_gate_pair", "bh3": -3, "bf3": -2, "co": -1}
                                          the Lewis pairing GATE (benchmarks/lewis_gate/PREREGISTRATION.md): `begin` ends the run before any
                                          job unless tolerance.json holds the tolerance the preregistered rule gives the recorded floor;
                                          `floor` measures the noise floor from two repeats of CO; `pair` judges BH3/CO and BF3/CO against
                                          the documented numbers. The gate was PASSED on 2026-10-13 (PREREGISTRATION.md section 9) and a decided outcome is final: do not re-run it to see whether the number moves
    {"do": "stage_report", "tag": "x", "expect": {"rows": {"torsion_table": "full", "oxygen_balance": null},
     "reader_header": "half", "reader_rows": 0}}   the support-stage STARS on screen: each Properties row's
                                          fill (full/half/empty, or none), its tooltip carrying the reason, the star beside
                                          "Showing" and how many reader rows carry one; read off the widgets
    {"do": "color_scheme", "scheme": "dark"}   Qt's light/dark override for THIS process ("unknown" hands it back);
                                          for a widget that borrows the palette
    {"do": "appearance", "choice": "dark", "via": "menu"}  choose the colour scheme through a REAL control ("menu" is
                                          View > Theme, "settings" the open Settings dialog's combo); read the result in a LATER step,
                                          the look settles a few milliseconds after the write. It writes the real stored choice: end a
                                          script on {"choice": "system"}
    {"do": "appearance_report", "tag": "x", "expect": {"effective": "dark", "choice": "dark", "editor_style": true,
     "viewer3d": "dark"}}                 the palette, the service's settled look, the stored integer, the checked menu entry, the open
                                          combo and each page's own state, asserted; the page reads are asynchronous (give it `after_ms`)
    {"do": "reader_filter", "text": "Donors"}  type into the docked reader's fact filter (it expands what it matches)
    {"do": "wait"} {"do": "quit"}

**A DRIVEN RUN ENDS IN A VERDICT, AND EXITS NON-ZERO WHEN IT FAILED.**
`src/openchem/app/drive_ledger.py` keeps every WARNING-and-above record the application
logs, de-duplicated by (logger, exception, innermost frame, message with its
numbers collapsed), and `quit` prints `VERDICT PASS|FAIL`, writes
`<script>.report.json` (`OPENCHEM_DRIVE_REPORT` moves it) and sets the exit
status: a driver failure (`no molecule selected`, `EXPECT ... FAILED`, a step
that raised), a failed `expect_*`, or an application ERROR nothing in `allow`
excuses all fail it. `{"do": "quit", "tolerate_errors": true}` opts out for a
script that provokes an error on purpose. **`expect_clean` IS NEVER A PASS ON ITS
OWN** -- an empty ledger is what a molecule that never ran the breaking code
also produces -- so pair it with `expect_results`. A scripted run writes its
own `drive-<pid>.log`, since two processes cannot share one rotating file on
Windows. The report records the run's identity (commit, script and lockfile
hashes, Qt/RDKit/Ketcher versions).

**`OPENCHEM_TRACE_WINDOWS=1` LOGS EVERY TOP-LEVEL WINDOW THAT SHOWS**, with
its class, its parent chain and a timestamp for every result event. It is
how the 1801 flashing windows were named; see the lesson. Pair it with
any drive script.

**`jobs_report` CARRIES A FLAG NO SCREENSHOT CAN**, which is why it exists
beside a `shot` rather than instead of one: both of the Jobs panel's
recorded defects live in `QTimer.isActive()` and neither is visible. A
panel that leaked itself polled for the life of the process; a visibility
gate that never restarts the timer leaves a frozen list that looks exactly
like an idle one. Switching to another right-hand panel IS the hide --
twelve docks, one visible at a time -- so no synthetic `hide()` is needed.

**`jobs_cancel` presses the BUTTON, not the handler behind it**, and here
that is load-bearing rather than stylistic: `_on_cancel_clicked` reads
which job it means off `sender()`, so calling it directly passes
`sender() is None` and proves nothing about the wiring, which is the thing
that changed.

**`select_atom` AND `selection_report` READ BOTH ID SPACES AT ONCE**, which
is why they exist beside a `shot` rather than instead of one. A selection is
a few highlighted pixels, and the failure they guard against is a
plausible-looking one: Ketcher's pool ids and the molfile's positions
diverge as soon as anything is deleted, so the two agree on a freshly
loaded structure and disagree on an edited one. `selection_report` prints
the pool order beside what is selected -- measured on `CCNCCO` with the
nitrogen erased, `poolOrder [0,1,3,4,5]` against positions `0..4`, and
asking for the oxygen at position 4 correctly reaches pool id 5 where
reading the position as an id would have selected a carbon.

`select_atom` drives the inspector's TABLE ROW, not the `select_atom()`
method behind it, for the reason `jobs_cancel` presses the real button: the
panel's own method is the INBOUND door the 3D viewer's click lands on, and
the path under test starts one step later.

**A MODAL DIALOG OPENED INSIDE A BUS HANDLER STARVES EVERY LATER
SUBSCRIBER**, and in a driven run it read as the Atom Inspector never
receiving the result. The calculator reveal used to `exec()` the Calculator
Inspector inside `EventBus._dispatch`; measured 2026-09-13, Properties held
`gasteiger_charge_at_ph` 67 s before the Atom Inspector did (at quit). Fixed
by `PropertyPanel._reveal_after_dispatch`. `inspector_report`'s `held=` is
what separates "not shown" from "never arrived"; `"reveal": false` keeps an
unattended run free of an open inspector window. (The inspector is modeless
now -- `_open_inspector` shows it, one window per result -- so a reveal no
longer blocks anything; the deferral stays because building the Chromium view
inside a dispatch is not free.)

**`erase` is the only step that drives the route `set_molecule` never
covers** -- the user drawing on the canvas -- so it is what any
calculated-annotation staleness has to be checked with. It goes through
Ketcher's own Delete hotkey, synthesised on the page. **A canvas edit
recomputes after the recalculation pause** (Settings > Recalculation, 800 ms
by default), so a script that reads results after an `erase` must wait the
pause AND the computation -- `after_ms` of a few seconds -- and results read
STALE in between, which is the point. Pair it with
`report`, whose `undo=` is how "did this display toggle quietly become an
edit" is answered: measured across a run, `baseline undo=2 -> labels-on
undo=2 -> after-edit undo=3 -> labels-off undo=3`.

**`receptor` DOES NOT SELECT WHAT IT ADDS EITHER, and that cost a run
that read as a bug in the code under test.** `molecule_combo.repopulate`
restores the previous pick by uuid, deliberately, so adding a second
receptor leaves the panel looking at the first. A script that adds one and
then dumps the box is still describing the OLD receptor -- which, when the
thing being checked is "does a derived box survive a receptor change",
reports the exact failure it was written to detect. `dock_receptor` is the
step that changes it; measured either side, the box goes
`(6.710, 2.210, 54.620) source=derived` -> `(0,0,0) source=none` -> back
again, and the Derive button stays ENABLED on the receptor with no
annotation because that structure still has ligands to box.

**`receptor` READS THE CACHE AND NEVER THE NETWORK.** A diagnostic run
that depends on RCSB being up is not a diagnostic. Populate the cache once
through File > Receptor Library; `_do_receptor` logs and skips if the id
is not there.

**`smiles` does NOT select what it adds**, and `conformers` and
`calculator` both act on the PANEL's selection -- so without a `select`
step they operate on whatever was already showing (the starter molecule,
which has no molblock) and the run fails with `has no molblock` as though
the structure were broken. `import` has the same shape, which is why the
example above pairs them.

`overlay` takes `gallery` and applies it AFTER the overlay, deliberately:
that is the gallery's FIRST render with requests already in flight, which
is the ordering the page's replay exists for and the one a script ticking
the gallery first would never reach. It logs what the PAGE drew per cell
(`drawnGridShapes`) and `gridBuilds`, not what Python believes it sent --
the distinction that whole feature turned on. Both are asynchronous, so
give the step an `after_ms` long enough for them to reach the log; a
probe issued in the same handler reads zeroes, correctly.

`after_ms` on any step is how long to wait before the next, which is how
an asynchronous calculator is waited on. Measured on the ADMET case: the
whole import-to-screenshot run is **55 seconds unattended**, with the
window sitting behind whatever Alex is working in. Nine molecules through
the Lewis dialog is about 25 seconds.

**A step that opens a MODAL dialog must not call `exec()`.** It spins its
own event loop inside the handler, so the next step is never scheduled
and an unattended run stalls on a window with nobody to close it -- the
same trap `quit()` set, one row down. `lewis` uses `show()`, which is the
only thing it does differently from a real click.

This is the real `MainWindow` with its real docks, fonts and DPI, which is
what the **six** "the harness said the opposite of the app" entries in
this file demand -- the count reached six at the starved-section entry,
which numbers itself. Only the INPUT is skipped.

**AND DRIVING IS NO LONGER ENOUGH ON ITS OWN: MAGNIFY THE SHOT.** The
width-clip work added three cases of an ADJACENT shape, counted
separately because they are not harness-versus-app disagreements -- the
whole panel suite was green, the in-app dump agreed with the code, and
the screen showed the defect at once: a value painted on top of its
caption, captions latched at `...`, captions collapsed to zero width.
`OPENCHEM_DRIVE` takes a `shot` step; cropping it 3x took seconds and
caught all three.

When a click really is needed, `spikes/gui_drive/drive.ps1` posts it to
the window handle rather than through the machine:

- `Save-AppShot` uses `PrintWindow(PW_RENDERFULLCONTENT)` -- captures the
  window while it is BEHIND other windows, and crops to the app instead
  of photographing the whole desktop. Verified with the app deliberately
  put behind Notepad++.
- `Invoke-AppClick -FromCapture` posts `WM_LBUTTONDOWN`/`UP` with
  coordinates read straight off that capture. Verified: it switched the
  right-hand panel while the app stayed in the background and the cursor
  never moved.
- `Assert-AppWindow` replaces the old "is the app in front" guard and is
  strictly better -- that one was a race, this asks whether the handle
  belongs to the expected pid, which cannot be.

Four things that cost a run each:

- **`quit()` closes all windows in Qt 6**, so a scripted run ended on a
  modal "Unsaved changes" box with nobody to answer it -- and removing
  the explicit `window.close()` changed nothing, because `quit()` was
  doing it. `exit(0)` leaves the loop without closing anything.
- **Skipping `closeEvent` is a feature.** It saves window geometry and
  dock state, so a diagnostic run would otherwise overwrite the layout
  Alex has arranged, every time.
- **Do not `Set-StrictMode` in a dot-sourced module.** It applies to the
  caller's session; here it broke the harness's own exit-code handling
  and read as a failure of a capture that had just succeeded.
- **A step that opens a window must not ACTIVATE it.** `MainWindow.show_scores()`
  raises and focuses the Derived Scores window, which is right for a person and
  wrong for a script on a timer: the keys a person types in another window next
  land in its Name field. Measured 2026-10-15: 2 of 15 driven saves ended with one
  stray letter in the label and a form that was "unsaved" (the cause of the one
  unexplained `score_dialog.json` failure); 0 of 15 once the driven open used
  `show_scores(activate=False)`. A new drive step that shows a window with text
  fields takes the same care, and the app still takes the foreground when a run
  starts, so type nothing into it in the first seconds.
