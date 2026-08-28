# OpenChem Studio — notes for Claude

## Working in a git worktree — do this before anything else

A fresh worktree needs two things set up, and **both fail silently rather
than loudly**, which is why they are the first thing in this file.

```bash
uv sync --extra ai --extra network --extra openbabel
"D:/Claude Co worker/Token Save/tokensave.exe" init
```

**The venv.** A worktree has no `.venv`. `uv run` will happily create an
empty one and then report `No module named pytest`, which reads like a
broken checkout rather than a missing sync.

**The tokensave index — the dangerous one.** The MCP server is registered
globally as `tokensave.exe serve` with no `--root`, and finds its project
by searching *upward* for a `.tokensave/` directory. A worktree created
under `.claude/worktrees/` sits inside the main repo folder and has none
of its own, so the search walks up and serves **the main checkout's
code** — a different branch, without the files you just wrote. Measured
2026-08-04: `tokensave_search` for a class written minutes earlier
returned `[]`.

Every call does carry a `worktree_mismatch` warning. **That warning is not
cosmetic; it means the answers are about different code.** Never work past it.

`init` costs about 2 seconds (343 files, ~8000 nodes) and leaves
`git status` clean. Three things that cost real time when they were not
known:

- **`init` refuses to rebuild an existing index.** It prints a "use
  `tokensave sync`" hint and exits 0, so a stale index looks like a
  successful re-index. Use `sync --force` to actually rebuild.
- **Initialising mid-session does NOT rebind the MCP tools.** The server
  resolved its root when it started, so `tokensave_*` calls keep hitting
  the old index. Until the session restarts, query through the CLI
  instead: `tokensave.exe tool health --path src/openchem`,
  `tokensave.exe tool search SomeClass`.
- **`tokensave branch` does not solve this.** It tracks branches within
  one checkout and syncs from that checkout's files, so it cannot see
  another directory's working tree.

The binary is not on PATH; call it by full path.

## Driving the app for a live check -- do NOT use the mouse

Several findings in this file could only be made in the running
application, so live checks are routine here. **They used to make the
machine unusable**, because every one drove the real input queue with
`SetCursorPos` + `mouse_event` + `SendKeys`: the cursor jumps, the app
must hold focus for every step, and Alex cannot work for the length of a
run. It was also fragile in a way that reads as an app bug -- a console
window stealing focus mid-sequence sent a paste into the wrong window and
the run looked like "the app ignored the import".

**Script the app from inside instead.** `OPENCHEM_DRIVE` names a JSON
file of steps (`src/openchem/app/debug_drive.py` documents the shape),
which run on a `QTimer` inside the process:

```bash
OPENCHEM_DRIVE=/path/to/script.json uv run --no-sync python -m openchem.main
```

    {"do": "import",     "path": "..."}      no file dialog
    {"do": "select",     "molecule": -1}
    {"do": "receptor",   "pdb_id": "6WGT"}   from the CACHE, never the network
    {"do": "receptor",   "pdb_id": "1HSG", "plain": true}
    {"do": "dock_receptor", "index": -1}     CHANGES the panel's receptor
    {"do": "dock_panel", "tag": "after"}     box, its source, the status line
    {"do": "panel",      "id": "Properties"}
    {"do": "expand",     "section": "admet"}
    {"do": "calculator", "id": "admet_ml", "parameters": {...}}
    {"do": "shot",       "path": "..."}
    {"do": "lewis",      "details": true}     the Full Lewis window
    {"do": "shot",       "path": "...", "widget": "lewis"}
    {"do": "dialog",     "name": "HelpDialog"}   built by ui/dialogs/inventory
    {"do": "dialog",     "name": "PeriodicTableDialog", "tab": "Isotopes"}
    {"do": "shot",       "path": "...", "widget": "dialog"}
    {"do": "overlay",    "on": true, "gallery": true, "step": 1}
    {"do": "cip",        "on": true}          R/S and E/Z, through the menu
    {"do": "erase",      "element": "N"}      a REAL canvas edit
    {"do": "report",     "tag": "after"}      conformers, undo depth, SMILES
    {"do": "jobs_report", "tag": "running"}   rows AND whether it is POLLING
    {"do": "jobs_cancel", "row": 0}           the real button in a real row
    {"do": "wait"} {"do": "quit"}

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

**`erase` is the only step that drives the route `set_molecule` never
covers** -- the user drawing on the canvas -- so it is what any
calculated-annotation staleness has to be checked with. It goes through
Ketcher's own Delete hotkey, synthesised on the page. Pair it with
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

Three things that cost a run each:

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

## THE HELP CONTRACT: a tooltip is a RENDERING, not the thing itself

Reported as "this suite especially needs tooltips... for a great, many
things", after nothing in the app could say what the pose table's
"RMSD l.b." column meant.

**The invariant is "has a documented contract", not "has tooltip text".** A
guard that checks for a non-empty string degenerates into
`tooltip = "Options."`. The producer declares what a control MEANS and the
validator checks the STRUCTURE of that declaration, never the prose --
`applies_to` and `Provenance.parameters[TOTAL]` already work this way.

    src/openchem/ui/widgets/help_tooltip.py       the metadata, knows no Qt
    src/openchem/ui/widgets/tooltip_inventory.py  the ONE discovery layer
    tests/test_tooltip_coverage.py                the guard
    tools/list_tooltips.py                        the query surface

The guard and the tool both consume `iter_documentable_controls` and
neither walks the tree itself. Two implementations of "all interactive
controls" would drift, which this repo has paid for four times.

### The three tiers

    1  plain UI action           action + result
    2  scientific parameter      what it controls + at least ONE applicable
                                 qualifier (unit, range, default, or
                                 behavioural consequence)
    3  interpretation-sensitive  definition + units/reference frame where
                                 applicable + the interpretation limit

Tier 2 requires "at least one APPLICABLE" deliberately: a method choice has
no unit and no useful range, and demanding all four produces `Default: N/A`
written to satisfy a rule.

    BAD   "RMSD l.b. -- RMSD lower bound."
    GOOD  "RMSD lower bound in A relative to pose 1. Symmetry-equivalent
           atoms may be matched, so it can be smaller than the upper bound.
           It does not measure agreement with experiment."

### `help_id` names a DEFINITION, not an instance

`<surface>.<concept>`, lowercase ASCII. **Never renamed because the UI
moved, never reused for a different concept** -- reusing one turns every
earlier reference into a statement about something else.

**Uniqueness runs BOTH ways and the second direction was missing.** Sixty
tick boxes meaning "include this calculator in a batch run" share ONE id;
sixty calculator buttons, each its own concept, get sixty. A mutation
renaming the tick boxes to `properties.batch_selection_<id>` -- one concept
shredded into sixty -- **passed every guard**, because each id then had
exactly one contract. `test_one_concept_is_not_split_across_many_help_ids`
closes it on a structural signal: byte-identical text under two ids means
one concept wearing two, or one of them wrong.

### Three kinds of statement, one wants a source

    external scientific fact      carries source_key -> docs/sources.toml
    OpenChem behaviour            carries neither
    interpretation warning        carries help_anchor -> openchem.help

Keeping the middle row source-free is what stops the registry becoming a
dumping ground for application semantics. Anchors resolve through
`openchem.help`, which already owns topic discovery -- the guard, the tool
and `tests/test_help.py` all ask it, so there is one parser rather than
three.

### Generate the contract where a registry already knows

The sixty calculator buttons derive theirs from `CalculatorDefinition`:
`description` is already the authoritative statement, so writing sixty
tooltips beside it would be sixty chances to disagree. Same instinct as
`sources.toml -> SOURCES.md`.

### What the guard must NEVER become

**No LLM grading, here or later.** Asking a model whether a tooltip
"explains the widget" makes the oracle stochastic, and a test that can
disagree with itself between runs is worse than none. The degenerate-string
floor is a FLOOR, and its exclusions are deliberate: no label-overlap
detection, no noun/verb heuristics, no word-count rules, no "must contain
units" regexes. Every one is satisfied by nonsense like "Maximum poses.
Higher values."

`whatsThis()` counts as alternate documentation. **`accessibleDescription()`
does NOT** -- worded that way so nobody deletes accessibility work to make
the guard pass. So `--missing` means "no semantic help", not "no tooltip",
and a control with good `whatsThis()` is NOT a gap to be filled.

`verified` was considered and deferred: the sources registry's field tracks
drift against EXTERNAL documents, while a flag an author sets in the same
commit that writes the prose records nothing `git log` does not.

**AND THE FLOOR IS NOW GUARDED FROM BOTH SIDES.**
`test_no_contract_is_a_placeholder` says a contract may not be a
degenerate string; nothing said the complement, and without it that floor
creeps upward one `assert "A" in text` at a time until the guard is
grading prose.
`test_a_weak_but_well_formed_contract_is_ACCEPTED` asserts that a tier-3
contract which is structurally impeccable and says almost nothing useful
must PASS. Same move `test_a_plausible_lie_passes_the_validator_and_fails_the_chemistry`
makes for `valid_total_declaration`: the validator owns the SHAPE, a
reviewer owns the meaning. Raising the tier-3 length floor from 80 to 400
fails that guard AND the floor guard, from opposite directions.

### THE MIGRATION IS FINISHED, and its scaffolding is deleted

**355 of 355 controls carry a contract. 219 distinct `help_id`s, 164 tier
1, 138 tier 2, 53 tier 3.** `tools/list_tooltips.py --missing` answers
"Nothing matched."

The staging is kept below as the record of how, because it is the reason
the layer could be added at all -- but both fixtures are GONE and the
invariant is now one assertion,
`test_every_control_carries_a_help_contract`.

248 controls carried a raw `setToolTip` when the layer landed. A guard
failing on that would have made the commit red and forbidden the
incremental migration it exists to enable, so
`tooltip_migration_debt.json` recorded the set and was allowed only to
SHRINK, and `tooltip_completed_surfaces.json` was its mirror, naming the
surfaces at zero so a finished one could not fall back into the backlog
unseen. Neither is needed once `missing` can be a failure.

**A BLANKET ASSERTION IS ONLY SAFE BECAUSE THE WALK IS OURS.** The
`controls` fixture points both plugin directories at paths that do not
exist, so no plugin-contributed panel is walked and a third-party panel
cannot redden the suite. Checked from the built window rather than
assumed; had plugins loaded, the surface list would have had to stay.

**A NEW CONTROL IS NOW RED UNTIL IT IS DOCUMENTED**, deliberately. That is
what finishing means: whatever is added next meets the standard the rest
of the application already does.

The debt fixture was keyed on the CONTROL rather than a source call site
-- `file:line` moves under the migration and the tooltip STRING is the
very thing being rewritten, while the control survives both. Its one weak
point showed up at the end: an `instance_path` is a position in the widget
tree, so wrapping a control in a new container RENAMES it, and the Batch
aggregate combo tripped the guard when its row became a `flow_row`. That
was resolved by migrating the control rather than re-recording the path.

**"66 setToolTip call sites" was 248 CONTROLS**, and an AST estimate of 179
interactive constructions was really 372. Neither number was ever the
universe; only `iter_documentable_controls` is -- and the universe grew
353 -> 355 while the migration ran, which is exactly why it is asked
rather than remembered.

### `QAction.toolTip()` NEVER RETURNS EMPTY, and the queue believed it

**All 83 menu actions were counted as documented, and not one carried a
human-written string.** With no tooltip ever set, Qt answers `toolTip()`
with the action's own `text()` minus the `&` accelerators and the `...`, so
"&Open Project..." reports "Open Project". `_status` tested
`toolTip().strip()` and could not tell "nobody wrote one" from "somebody
wrote one".

Two costs, and the second is the one that mattered. It overstated the
migration debt by 83 -- but worse, it hid 83 controls from `--missing`,
which is **the queue this migration is worked from**. An agent burning down
the debt would have found 83 menu actions in the "already has something"
pile forever. And what they had was the exact degenerate case the whole
contract layer exists to reject: a tooltip restating the label it is
attached to.

    before   145 contracts / 137 legacy /  84 missing
    after    145 contracts /  54 legacy / 167 missing

**THE RULE IS ASKED OF QT, NOT REIMPLEMENTED.** `_tooltip_is_qt_s_own_echo`
builds a throwaway `QAction` with the same `text()` and compares, so it is
Qt's own answer by construction and cannot drift when `qt_strippedText`
changes. Reproducing that function here would have been a second
implementation of somebody else's private detail, and its edge cases are
not the obvious ones -- measured:

    '&Open Project...'      ->  'Open Project'
    'Mid...dle'             ->  'Middle'      <- stripped ANYWHERE, not just trailing
    'A && B'                ->  'A & B'
    'Trailing spaces   '    ->  'Trailing spaces'
    'Zoom In\tCtrl++'       ->  'Zoom In\tCtrl++'   <- shortcut text survives

A tooltip deliberately set to exactly the synthesised string reads as
absent, which is the right answer either way: restating the label is not an
explanation, and the degenerate-string floor already refuses it in a
contract.

**THE NARROW HALF IS WHAT NEEDED THE SEPARATE TEST.** "A `QAction` is never
`legacy_tooltip`" satisfies the reclassification guard and is wrong -- an
action somebody wrote a real tooltip for is exactly the debt the fixture
exists to burn down, and dropping it would make the migration look finished
early. `test_an_explicitly_set_action_tooltip_still_counts_as_debt` asserts
on the predicate rather than through the window, because no action in the
application carries an explicit tooltip today, so the end-to-end route
cannot tell a narrow rule from a blanket one. Mutating the comparison to a
bare `return True` is caught by that test and by nothing else.

### THE MENU BAR: 71 commands, and the contracts were INVISIBLE

**`QMenu.toolTipsVisible()` IS FALSE BY DEFAULT.** Measured on the real
window right after the 71 contracts landed: all seven top-level menus
answered False, so every one of them was documented, queryable through
`tools/list_tooltips.py`, passing the coverage guard -- and **dead on the
screen**. The contract layer's whole claim is that a tooltip is one
RENDERING of a declared meaning, and a rendering that never renders does
not honour it.

`_show_tooltips_in_menus` walks the menu bar rather than setting the flag
at each `addMenu` call: submenus are created in several places and a
plugin can contribute one, so a rule applied at a call site is a rule the
next author has to remember. 12 menus, 7 top-level and 5 sub.

**FINDING IT MEANT HITTING THIS FILE'S OWN WRAPPER TRAP.** The first probe
read `w.menuBar().actions()` and then asked each action for its menu --
that list is a TEMPORARY, so every `QMenu` wrapper it handed out was dead
by the next line (`Internal C++ object already deleted`). Hold the list.

### A menu TITLE is explained by its menu

`QMenu.menuAction()` is a `QAction` and lands in the same walk, so `&File`,
`Copy Structure As`, `2D Structure Display` and `Installed Plugins` all
arrived asking for a contract -- 12 of the 83. There is nothing honest to
write on one, and "Opens the File menu" twelve times is exactly the
restate-the-label degeneracy `test_no_contract_is_a_placeholder` refuses.
Excluded on `action.menu() is not None`: derived from Qt rather than from a
list of menu names.

**BOTH HALVES ARE GUARDED, and the second is the load-bearing one.** "A
`QAction` inside a menu needs no contract" satisfies the title guard and
silently exempts all 71 real commands while reading as a jump in coverage.
`test_menu_entries_are_not_exempted_along_with_their_titles` holds that
line; the blanket mutation is caught by four tests.

A `QWidgetAction` is excluded too, for a different reason: it is Qt's way
of putting a WIDGET into a toolbar, and the one here holds the `PanelRail`,
whose own group buttons are already walked individually.

### A FINISHED SURFACE CAN REGRESS AND NOTHING NOTICED

Deleting the contract from File > New Project **survived every guard in
the file.** `missing` cannot be a failure while 83 controls still are --
that is the staged migration working as designed -- so a completed control
simply falls back into the backlog unseen.

`tooltip_completed_surfaces.json` was the MIRROR of the debt fixture: the
debt set could only SHRINK, that one could only GROW. It recorded the
SURFACE rather than the control, so a new menu entry or a new control on a
finished panel was held to the standard the rest of that surface already
met. **Both are deleted now** -- with every surface finished, "no control
anywhere is undocumented" says the same thing and needs no fixture. The
account is kept because the REASON it existed is the durable part: a
completed control falling back into the backlog is invisible for exactly
as long as `missing` cannot be a failure.

**IT FAILED ON ITS FIRST RUN AND WAS RIGHT.** It named a `QWidgetAction`
that every earlier count had missed, because those counts filtered on
`widget_class == "QAction"` while the guard asks by KIND. Counting a
population by the wrong key is how a surface looks complete and is not.

### One concept, one help_id -- what collapsed here

    every dock's View toggle   ONE id, 13 renderings
    the three Help topics      ONE id -- "open the manual at this topic"
    explicit hydrogens         ONE id, TWO renderings: the SAME Ketcher
                               action offered from Structure and from
                               View > 2D Structure Display, under two
                               different labels

`Copy Structure As` deliberately does NOT collapse -- SMILES, InChI,
InChIKey and a molblock have genuinely different round-trip properties, and
choosing between them IS choosing between those properties. InChIKey is
tier 3 for the one thing a reader must not get wrong: it is a hash, and
nothing can reconstruct the molecule from it.

### THE SUITE CAUGHT A CONTENT ERROR IN THE PROSE, NOT A LEXICAL ONE

`test_nothing_tells_the_reader_to_go_to_the_3d_viewer_tab` failed on the
`Open 3D Viewer (Miew)` contract, which read "Separate from this
application's 3D tab, which is where conformers, measurements and
calculated surfaces live."

That is not a false positive. Pairing the 3D viewer with conformers is the
signpost this project deliberately deleted when conformer generation moved
to the Structure menu -- `main_window.py` records that "four separate
messages elsewhere told people to go there for it" -- and the sentence
would have reinstated a fifth. **A guard on PROSE caught prose that
contradicted a design decision**, which is the one thing the tooltip
guard's own no-LLM-grading rule cannot do for itself.

Run every source-scanning guard together after writing UI strings; there
are 13 and they cost 14 seconds, against 14 minutes for the full suite:

```bash
uv run --no-sync python -m pytest -q $(rg -l "ast.parse" tests/ | tr '\n' ' ')
```

**THAT SET DOES NOT INCLUDE THE DOCUMENTATION GUARD, and reading it as
though it did put a red commit on master.** `test_docs_are_current.py`
never calls `ast.parse` -- it reads markdown and asks git what the
repository contains -- so it is not in the `rg` set, and a sweep
reporting `287 passed` had not run it. The commit that followed cited two
tests the same branch had deleted, and master went red on
`test_every_test_a_doc_names_still_exists`. Anything touching CLAUDE.md
or `docs/` has to name it:

```bash
uv run --no-sync python -m pytest -q tests/test_docs_are_current.py
```

**AND IT PASSES WHILE A DELETION IS UNSTAGED.** `_repo_files` asks
`git ls-files`, so a file removed from the working tree but still in the
INDEX is still tracked and still resolves. The two fixtures deleted by
the help-contract migration were checked twice after being removed and
passed both times; the citation only broke once `git add -A` staged the
removal. A green docs run taken mid-change is not evidence about the tree
you are about to commit.

**AND IT FAILS ON A NEW FILE UNTIL THAT FILE IS STAGED**, which is the
same mechanism seen from the other side and reads as a broken citation
rather than as an unstaged one. Writing `tests/test_dialog_help_contracts.py`
and citing it in the same edit fails `test_every_file_a_doc_cites_still_exists`
with the path listed as missing; `git add` on the new file is the whole
fix. Neither direction is a bug in the guard -- `git ls-files` is the
right question and the INDEX is what answers it.

### The shared chrome: 36 buttons, 3 concepts

Every dock builds a `DockTitleBar`, so its help / float / close buttons
appear **36 times across 12 docks** -- three ids, and `instance_path` tells
the renderings apart. `_make_button` takes a `HelpTooltip` rather than a
string now, which is what stops the next button added there from being a
bare `setToolTip`.

The Properties panel's 17 section headers collapse the same way, and the
contract lives in `CollapsibleSection` rather than in the panel: the class
is used elsewhere, and "show or hide this section" means the same thing
wherever it is built.

**`panel` IS A FORBIDDEN help_id SEGMENT**, so `panel.close` is rejected --
it is in `_WIDGET_WORDS`. That is the validator working as designed even
though "panel" is this application's own domain word for the thing; the
ids are `workspace.panel_close` and friends, which name the concept without
tripping a rule that exists to stop ids encoding widgets.

### A CONTRACT AND A STATE-DEPENDENT RENDERING, TOGETHER

"Derive from ligand" is the one control here whose useful text depends on
the receptor: it names the ligand codes actually present, which is what
answers "will this button do anything for me". The contract is attached
ONCE and the tooltip is recomputed, which is exactly what "a tooltip is one
RENDERING of a declared meaning" buys.

**The failure mode is silent.** Substituting the live text for the
contract's leaves the contract attached as a Qt property, so the coverage
guard still reports the control documented while the user sees three-letter
codes and nothing saying what pressing it does.
`test_the_derive_buttons_live_tooltip_still_carries_its_contract` asserts
the rendered string CONTAINS the contract text, in both the has-ligands and
the no-ligands state.


### A `QTabBar` BREAKS QT'S OWN `qt_` NAMING CONVENTION

`_is_qt_internal` excludes Qt's scaffolding by the `qt_` object-name prefix
Qt reserves for it -- derived rather than enumerated, so it cannot rot. A
`QTabBar` honours that for itself (`qt_tabwidget_tabbar`) and **not for the
two `QToolButton`s it builds to scroll the tabs**, which it names
`ScrollLeftButton` and `ScrollRightButton`. The prefix rule reads the
widget's OWN name, so it excluded the bar and admitted its children: three
tab widgets put **six Qt scroll arrows** into the inventory as controls
owing the user an explanation.

`QTabBar` joins `QComboBox`/`QSpinBox`/`QDoubleSpinBox` in
`_is_internal_to_a_composite`, which already means "Qt built this inside
one of its own controls". A tab PAGE is a child of the stacked widget,
never of the bar, so nothing of ours is reachable.

**THE TEMPTING GENERALISATION WOULD HAVE DELETED 82% OF THE UNIVERSE.**
"Anything under a `qt_`-named ancestor is Qt's own" is the
principled-sounding version of the same fix, and it excludes **200 of 243
widgets** -- every panel in this application lives inside a `QScrollArea`,
whose viewport is named `qt_scrollarea_viewport`. Measured before it was
written rather than after. **The failure mode of an over-broad exclusion is
a GREEN suite and a smaller universe**, so it would have registered as a
large jump in coverage rather than as a fault.

The guard is therefore in two halves and the second is the load-bearing
one: `test_a_tab_bars_scroll_buttons_are_qt_s_own` asserts the arrows are
excluded -- asserting its own setup, so a window that stops building a
`QTabWidget` fails loudly instead of passing vacuously -- and
`test_the_composite_rule_does_not_swallow_the_panels` asserts the panels
are still there.

#### AND A `QLineEdit`'s CLEAR BUTTON ESCAPES THE PREFIX RULE TWICE

Same hole a third time, found in the dialogs, and it is the widest yet.
`setClearButtonEnabled(True)` makes Qt build TWO things inside the line
edit and neither carries the `qt_` prefix `_is_qt_internal` derives its
answer from -- measured on a bare `QLineEdit`:

    the button   QToolButton, objectName ''      <- no name AT ALL
    the action   QAction, '_q_qlineeditclearaction', parented to the
                 QLineEdit    <- Qt's OTHER reserved prefix, `_q_`

So the button escapes by having no name to match and the action escapes
by using a different reserved prefix. The two clear buttons in this
application are both in dialogs, which is why the window's 355 never saw
it: the help window and the receptor library each reported **twice the
controls they have** -- 4 where there are 2, and 3 where there is 1.

**THE ACTION SIDE NEEDED THE RULE APPLIED TO A SURFACE IT NEVER WAS.**
`_is_internal_to_a_composite` ran in the widget loop only, and the clear
action is a child of the line edit rather than of any widget beneath it.
It walks `parent()` rather than `parentWidget()` now so ONE
implementation serves both -- measured over the real window, the two
traversals exclude exactly the same set, so it is a widening in reach and
not in effect.

**MEASURED BEFORE IT WAS WRITTEN, as the QTabBar rule was.** The window
holds 13 `QLineEdit`s and **not one has a clear button**, so its universe
is 355 either way. Of those 13 only **2** are documentable controls at
all -- 7 live inside a `QDoubleSpinBox`, 3 inside a `QSpinBox` and 1
inside a `QComboBox`, all already excluded -- which is why
`test_the_composite_rule_does_not_swallow_the_line_edits` asserts the
survivors BY NAME (`facts.search`, `batch.property_filter`) rather than
by a threshold that would read as stronger than it is.

Five mutations, five caught, each by the intended guard:

    M1  revert the QLineEdit exclusion   the clear-button guard + the
                                         dialog blanket
    M2  exclude the line edit ITSELF     the clear-button guard's narrow
                                         arm + does_not_swallow
    M3  drop the action-side check       the same pair as M1
    M4  delete one shipped contract      the dialog blanket, ALONE
    M5  excuse a finished dialog         the unmigrated mirror

**M2 IS THE ONE WORTH READING.** It does not fail the dialog blanket at
all, correctly -- excluding more can only make the missing count smaller.
That is the green-suite-and-a-smaller-universe failure in miniature, and
the reason the narrow half is the load-bearing one.

### THE DIALOGS: every one a bare context can build is at zero

`tests/test_dialog_help_contracts.py` is the second consumer
`ui/dialogs/inventory.py` was written for. Until it existed the contracts
written into a dialog were unguarded -- M4 above is exactly that, and
nothing caught it.

**SCOPED TO WHAT A BARE `DialogContext` CAN BUILD.** Six of the 17 need a
computed result and five more need services, settings or a molecule;
handing the guard a context rich enough for all 17 makes it a slow
integration test that fails for reasons having nothing to do with help.
`test_a_dialog_that_cannot_be_built_says_so` is what stops that set
shrinking silently -- a builder must raise `DialogUnavailable` and must
never answer None.

    PeriodicTableDialog    137 of 137     ConformerOptionsDialog  6 of 6
    HelpDialog               2 of 2       CommandPalette          1 of 1
    ReceptorLibraryDialog    1 of 1       AboutDialog             0 controls

**THE EXCEPTION LIST EXISTED FOR EXACTLY ONE COMMIT AND IS GONE.**
`_NOT_YET_MIGRATED` held `PeriodicTableDialog` while its 137 contracts
were written, and its mirror required an excused dialog to still HAVE
undocumented controls -- so the day the table reached zero the guard
failed and asked for the name to be deleted. Both are deleted; "no
control anywhere is undocumented" says the same thing and needs nothing
maintained. Same arc as `tooltip_migration_debt.json` one layer up, three
days shorter.

**137 WAS NEVER 137 CONCEPTS: it is 15.** 118 are element cells -- one
concept rendered once per element, the shape
`properties.batch_selection` already has across 51 tick boxes, and
`test_one_concept_is_not_split_across_the_element_cells` is what refuses
the split. Seven more belong to `ZoomableSvgView` and `AtomDiagram`
rather than to this dialog, so documenting them documented the Lewis
dialog's four zoom buttons at the same time.

#### THE ELEMENT CELL: a contract under a tooltip rewritten 118 times

`_repaint_cells` rebuilds every cell's tooltip on every recolour, so this
is the `docking.derive_box_from_ligand` case at scale: the contract is
attached ONCE and the live text must CARRY it rather than replace it.
The failure is silent -- a bare `setToolTip` there leaves the contract
attached as a Qt property, so the coverage guard goes on reporting all
118 documented while the user reads "Hydrogen -- Nonmetal" and nothing
saying what clicking does. Mutated: only
`test_an_element_cells_live_tooltip_still_carries_its_contract` catches
it, in a discrete mode AND a heat-map mode, because those build their
live half differently.

#### THE ISOTOPE COLUMNS, AND `*` MEANS THE OPPOSITE OF WHAT IT LOOKS LIKE

The five isotope headers are where the tier-3 work is: every one prints
a source-specific mark that decides how the number reads. The sharpest
is spin/parity, and the marks are NOT guessable -- read off the shipped
`nubase_4.mas20.txt`'s OWN format block and confirmed in the paper's
legend (p18 of [source:nubase2020]):

    *    DIRECTLY MEASURED spin        1062 states
    #    non-experimental, from trends in neighbouring nuclei or theory
                                        948
    ()   weak argument, still EXPERIMENTAL
                                       1328
    T=   isospin, on isobaric analogue states
                                        108

So `*` is a STRENGTHENING mark where a footnote symbol usually implies
doubt, and the parenthesis/`#` pair is deliberately the opposite way
round from ENSDF -- NUBASE section 2.4 says so outright, because it
separates experimental from non-experimental information where ENSDF
parenthesises both.

**THE MARKS ARE NOW IN THE NOTE UNDER THE TABLE AS WELL, and that is
this file's own finding applied.** The half-life legend "explained no
marks" for exactly the same reason: a meaning that lives only in a
tooltip is absent from every screenshot. The guard derives the marks
from what the CELLS PRINT rather than from a list, so it cannot pass
vacuously.

**DRIVEN AND MAGNIFIED, AND FOR ONCE NOTHING WAS WRONG.** The longer
note is the one visible change here and this dialog's height was a
reported bug six commits ago, so it was photographed rather than
reasoned about: the note wraps to two lines, the action row and Close
stay inside a 940x900 window, and the Isotopes page's own minimum is 113
px against the 280 the guard allows. The `dialog` drive step takes a
`tab` now -- half these dialogs are tabbed and a shot of the default
page cannot show the other three. A tab name that matches nothing is
LOGGED rather than ignored, because an unrecognised INDEX would silently
photograph page 0, which is the wrong-panel-id trap again.

**AND THE `*` COUNT RECONCILES WITH THE PAPER TO THE LAST STATE.**
NUBASE2020 states 1062 directly measured spins, "827 ground states and
235 isomers"; the shipped table has 1062, split 826/236. The one-state
gap is the FREE NEUTRON -- a starred ground state (`1/2+*`) that the
build deliberately excludes because it is a nuclide and not an element,
which `test_the_free_neutron_is_not_here` already asserts. Counting `*`
in the raw source gives 827, so the reconciliation is exact once the one
deliberate exclusion is named, which is a stronger statement than a
total that merely agrees. It is also a free check on a fixed-width
slice: a column off by one would still yield plausible spins while
quietly moving the flag.

### The Quantum Chemistry panel: 25 help_ids, 39 renderings

The first panel taken to zero. 37 missing and 9 legacy became 39
contracts.

**ONE CONCEPT, ONE `help_id`, AND THE THREE CORRELATION TABS ARE THE
CASE.** HSQC, HMBC and COSY are built from ONE column tuple by ONE loop and
populated by ONE method, so their five columns mean the same five things in
each: they share five ids across fifteen renderings, with `instance_path`
telling the renderings apart. What differs between those tabs is WHICH atom
pairs appear, which is a property of the tab and not of its columns.
Splitting them would have been the batch-tick-box mutation shipped on
purpose. `_CORRELATION_COLUMN_HELP` is one tuple used three times, so there
is nowhere for the three to drift apart. `Atom` and `Element` are likewise
one concept each across the 1D spectrum and Hybrid tables.

**THE SPECTRUM COLUMN IS NAMED `Value` BECAUSE IT HOLDS TWO DIFFERENT
QUANTITIES**, which is the sharpest tier-3 contract in the panel.
Uncalibrated it is a raw isotropic shielding constant; after a TMS or
scaling calibration it is a chemical shift. The two run in OPPOSITE
directions -- a more shielded nucleus has a LARGER shielding constant and a
SMALLER shift -- so reading the uncalibrated column against literature
values is wrong in a way that looks fine. The note above the table already
said WHICH was on screen; nothing said what the difference meant.

**CHARGE IS DERIVED FROM THE STRUCTURE AND MULTIPLICITY IS NOT.**
`_on_molecule_changed` sets the charge spin from the drawn formal charge;
the multiplicity stays at 1 whatever is selected. Two adjacent spin boxes,
one of which tracks the molecule and one of which does not, so the
asymmetry is written into both contracts.

**A DASH IN `J (Hz)` MEANS NOT COMPUTED, NOT ZERO.** Cross peaks are
derived from bonding connectivity, so a peak is listed whether or not a
coupling constant exists to put beside it; only the "NMR + Spin-Spin
Coupling" calculation produces one. **`Methods differ by` IS NOT AN
ACCURACY MEASURE** for the same family of reason: a small spread says the
database and the calculation landed in the same place, and both can be in
the same place and wrong.

The atom index is **0-based over the structure WITH EXPLICIT HYDROGENS**,
not the 2D drawing's numbering -- confirmed from a real ORCA transcript in
`tests/test_orca_engine.py` (water: O=0, H=1, H=2) rather than reasoned
about, since this project has an index-space bug in its history.

Five mutations, five caught, each by the intended guard and each arm
running the full 12 tests:

    M1  revert the QTabBar exclusion       test_a_tab_bars_scroll_buttons_are_qt_s_own
    M2  the broad any-qt_-ancestor rule    test_the_composite_rule_does_not_swallow_the_panels
    M3  a contract back to raw setToolTip  the debt guard, now
                                           test_every_control_carries_a_help_contract
    M4  two ids, byte-identical text       test_one_concept_is_not_split_across_many_help_ids
    M5  one help_id reused                 test_one_help_id_means_exactly_one_thing

**M4 REPORTED A CONFIDENT SURVIVED AND THE MUTATION WAS THE BUG.** It
prepended one contract's text to another's by implicit string
concatenation, which produces text that is merely SIMILAR --
`test_one_concept_is_not_split_across_many_help_ids` requires
byte-identical, correctly. The arm was INVALID, not a survivor. Fourth
instance in this file of "a mutation that does not do what it says is not a
mutation"; the harness now prints an EDIT-CHECK asserting the two texts
really are equal before it runs the guard.

**AND A DRIVE STEP WITH A WRONG PANEL ID IS A SILENT NO-OP.**
`{"do": "panel", "id": "Quantum Chemistry"}` changes nothing:
`_dock_by_panel_id` matches on `dock.objectName()`, which is
`Quantum_Chemistry` with an UNDERSCORE, and `_on_panel_chosen` returns
quietly when it finds none. The run logged `step 1 panel` and looked
perfectly healthy while photographing the Compare panel. **Read the shot,
not the log.**

## BATCH WAS A SECOND IMPLEMENTATION OF WHAT PROPERTIES ALREADY DID

Reported as "the entire system is a total mess", with three complaints:
no select-all, no select-all-in-group, and a result table that is
"incredibly un user friendly". The third one is the structural half:
**this app had TWO batch systems and they disagreed.**

    PropertyPanel._on_run_selected    N calculators x 1 molecule
    BatchPanel                        N calculators x M molecules

Same 51 tick boxes -- one `help_id`, `properties.batch_selection` -- and
two different meanings:

    | | Properties, "Run selected" | Batch |
    | runs via | DescriptorService.run_calculator | its own _BatchTask |
    | produces | one ScientificResult | N columns via reduce_result |
    | offers | a row, Details, an inspector | a number in a cell |
    | keeps | yes, in _reports | no -- reduced and dropped |
    | costs | one calculator, when asked | molecules x properties, up front |

The third row is the complaint: **a calculator that is one coherent thing
in Properties became N unrelated columns in Batch.** Topology Analysis is
one button and one Details view on the left; on the right it was a Wiener
column, a Randic column and a Szeged column with nothing tying them
together. And lossy on top -- `result_reduction` recovers 73 numeric
columns from the real registry and REFUSES 25 real lines outright.

### The spine: the ScientificResult is the stored thing

`domain/batch.BatchResultStore` retains them; `reduce_result` is a
PRESENTATION PROJECTION and its module docstring now says so, because
that is the regression this whole change exists to prevent and a
docstring is what survives the next author.

**THE DIRECTION MATTERS ONE LEVEL DOWN.** A `BatchTable` is rows by
columns; the store is keyed by `(molecule, calculator, parameters,
structure_version)`, which is not a table and does not become one because
a table can be built from it. If the store were the table, `reduce_result`
would be back in the storage position by another route.

### NONE OF THE FOUR KEY COMPONENTS IS INVENTED

Checked rather than assumed, because a retained result makes "which
result am I looking at" a real question and getting it wrong trades a
lossy system for a stale one:

    molecule_uuid      a uuid4 carried through `to_dict()` into the
                       project file -- semantic identity, not object
                       identity. `ResultCache` warns against keying on it
                       ALONE, which is what the next line is for.
    structure_version  `StructureCheckService.current_version()`, the
                       counter `StructureReport` is already built on and
                       the Atom Inspector's cache already keyed on.
    parameters_key     a thin wrapper over `result_cache.key_for`, already
                       sorted-JSON-into-SHA-256 and already stable across
                       processes. A SECOND parameter serialisation is how
                       two identical requests become two keys.

So editing a molecule makes its results STALE rather than wrong, and
stale results are REPORTED rather than deleted -- silently serving one and
silently blanking it are the two ways this goes wrong and they look
identical from outside.

**The recorded trap applies directly**: the Atom Inspector's version is
`None` in a plain fixture, so it is 0 forever, and two guards for a
stale-index crash passed while testing the cache. Any test here that
mutates a molecule must move the thing the key is keyed on.

### RETENTION COSTS LITTLE, and the contract was not signed first

Measured over 8 drug-like molecules against all 53 registry-executable
calculators, 424 results:

    mean per result        9.05 KiB
    largest single        37.1  KiB   regulatory_screen -- and the SAME
                                      size for every molecule, which is
                                      worth knowing but was not chased
    5 molecules            2.3 MiB     50 ->  23 MiB
    200 molecules         94   MiB   1000 -> 469 MiB

No eviction, no disk spill: nothing there asks for one at the sizes the
lazy path reaches. The bulk path could reach the bottom of that table, and
it states its cost first.

### THE COMPUTATION MATRIX -- five rows, five tests

"Nothing is computed unasked" is only an invariant if *asked* is defined:

    open the Batch panel      zero calculations
    select a molecule         that molecule's ticked properties, and NO
                              other molecule's
    look at it again          nothing -- retention is what makes lazy
                              usable rather than merely lazy
    press Fill table          the full explicitly-requested matrix
    Fill table, large         asks first; Cancel computes nothing

Driven in the app, and the log IS the design:

    panel-opened        ticked 0 | rows 0 cols  0 | store 0
    category-ticked     ticked 2 | rows 0 cols  0 | store 0
    after-lazy-details  ticked 2 | rows 0 cols  0 | store 2
    filled              ticked 2 | rows 3 cols 14 | store 6

**TWO THINGS THE PANEL HAD TO LEARN**, both because the lazy and bulk
paths now arrive on the identical event. The table is adopted ONLY when
the run was a fill -- a one-molecule run returns a ONE-ROW table, and
letting that through makes opening a detail view destroy the table the
user just built. And the store is MERGED rather than replaced, or a
one-molecule run wipes the other 199.

### `ItemIsAutoTristate` DOES TOO MUCH

It looks like exactly what a select-all-in-group wants. With it set, Qt
propagates a parent's tick down to EVERY child itself, hidden ones
included -- which reaches entries the filter is hiding and contradicts the
filter's own documented promise that it filters the LIST and never the
results. Measured: the hidden-children guard fails on a child Qt ticked
before our handler ran. Both directions are ours instead, with one
re-entry guard.

**AND NEITHER OBVIOUS ASSERTION CAN TELL A CHECKABLE ROW FROM A PLAIN
ONE.** Measured on a bare `QTreeWidgetItem`:

    ItemIsUserCheckable   in Qt's DEFAULT item flags -- True on a row
                          nobody ever made checkable
    checkState(0)         Unchecked whether a state was set or not
    data(0, CheckStateRole)   None until setCheckState is called  <- the
                          only discriminator, and what decides whether a
                          box is DRAWN

A mutation emptying `_make_groups_checkable` survived both of the obvious
versions of the guard.

### A FIELD WRITTEN BY EVERY CALLER AND READ BY NOTHING

`BatchRequest.molecule_uuids` was never consulted -- `_BatchTask` iterated
whatever list it was handed -- so a request naming two molecules while the
caller passed twenty ran twenty, and nothing would have noticed. Found by
mutation: widening the request's scope changed no behaviour at all.

Latent rather than live, since no caller disagreed with itself. The lazy
path is what makes them disagree easily, because it asks for one molecule
out of a project. The request is the authority on scope now, with an empty
list still meaning "everything given".

**THE TWO HALVES NOW CROSS-CHECK, so each alone is an EQUIVALENT
mutation** -- widening the request's scope is clamped by the molecules
handed over, and vice versa. Only widening BOTH changes behaviour, and
that is caught. Verified as its own paired arm rather than assumed, since
"two survivors" otherwise reads as a coverage gap.

### THE CAP COUNTS DIALOGS; CHROMIUM JUSTIFIES THE NUMBER

Measured before it was written, sampled DURING the run because they are
all reaped at exit and a post-mortem finds zero and looks healthy:

    open inspectors      QtWebEngineProcess
    1..8                              1..8    exactly one each, linear
    disposed per widget                  0    all of them freed
    disposed via processEvents           8    NONE freed

So resources are not the binding constraint -- the recorded hang was at
91-116 processes. **The bound is READABILITY and says so**; the Properties
panel reached the same conclusion independently, declining to pop
inspectors from a multi-calculator run because "six inspectors stacking up
is not what anybody asked for". A cap expressed in `QtWebEngineProcess`
counts would change meaning under a Qt upgrade and is not something a user
can reason about.

The second row is why `close()` is followed by the per-widget
`sendPostedEvents(dialog, DeferredDelete)`: without it the cap would be
cumulative rather than concurrent. `processEvents()` never delivers a
`DeferredDelete` at event-loop level 0, which this file already records
and which held again here.

### A GUARD MUST NOT DO WORK PROPORTIONAL TO WHAT IT GUARDS

The cap's first guard built `range(MAX_OPEN_INSPECTORS)` stand-ins, so it
scaled its own work by the constant under test -- and the `1 << 30` arm
allocated a billion objects and **hung the mutation pass twice** before
the cause was spotted. Split in two: the shipped constant's magnitude is
asserted directly and cheaply, and the refusal is exercised against a
monkeypatched cap of 2.

### THE HARNESS ITSELF COST TWO RUNS

`ROOT.rglob("__pycache__")` reaches into `.venv`, which is thousands of
directories -- clearing it between arms made every one recompile the whole
dependency set and took each into the minutes. Scope a mutation harness's
cache clearing to `src/` and `tests/`.

And `batch_details` REPORTED A WORKING FEATURE BROKEN: `_show_details`
starts a background run and RETURNS, with `_present_details` called later
from the progress handler, so a patch restored in a `finally` was gone
before the dialog was built. The step said "no dialog open" for a run that
was perfectly correct.

### The cell now says WHAT it is

    SCALAR      a number, as before
    NON_SCALAR  a real result with no scalar form -- a per-atom map, a
                spectrum, a structure set. Named, italic, its own colour,
                and a tooltip saying it is one double-click away.
    FAILED      the em dash, unchanged

Those last two used to render identically, which is the OPPOSITE
statement: one says nothing was computed, the other says something was and
a table is the wrong shape for it. `reduce_result` refuses 25 of the real
registry's lines, so the second is the common case rather than an edge
one.

## THE VIEWER AND THE DOCKING WERE SHOWING DIFFERENT CHAINS

`Viewer.loadStructureFromData`'s default preset builds **biological
assembly 1**, which is not the deposited file this app hands to Vina.
Measured on 6WGT (5-HT2A with LSD), which carries three copies of 7LD and a
`REMARK 350` assembly per chain:

    copy      centre                    in assembly 1?
    A/1201    (24.28,  41.05, 54.36)    yes   <- all Mol* displayed
    B/1201    ( 6.71,   2.21, 54.62)    no    <- what docking boxes
    C/1201    (24.01, -37.77, 54.49)    no

`binding_site._single_copy` picks B by burial, for reasons measured on
other deposits. So the search box was geometrically right and drawn about
43 A from anything on screen -- and the interaction colouring, which
matches residues by NAME AND NUMBER, was painting chain A's residues for a
pose computed against chain B's site. **That second half is older than the
overlay, needed a chain term of its own, and now has one -- see "THE
COLOURING NEEDED THE CHAIN" below for the 6WGT measurements.**

#### THE COLOURING NEEDED THE CHAIN, AND NOW CARRIES IT

This file said the residue colouring "is fixed as a side effect" of the
deposited-model change and had "not been verified end to end". It has been
verified now, and it is **half fixed**.

Measured live on 6WGT, reading Mol*'s OWN loaded state rather than the
source:

    structure-from-model params   {"type":{"name":"model"}}   <- the fix IS live
    chains in the loaded structure  A,B,C                     <- was chain A alone
    GLN72 resolves to chains        A,B,C                     <- the defect

`build_interaction_layers` emitted `receptor_residue` as
`f"{residue_name}{residue_number}"` -- **no chain** -- and `viewer.html`
turned that into

    (and (= atom.auth_comp_id GLN) (= atom.auth_seq_id 72))

which had no chain term either. So the deposited-model fix changed
"paints the WRONG copy" into "paints the right copy AND two wrong ones":
chain B was displayed and coloured, and so were A and C.

**THE DATA WAS ALREADY THERE.** `analyze_pose` has carried
`receptor_chain` beside `receptor_residue` at all three of its emit sites
since the hERG work -- a homotetramer whose subunits share residue
numbering -- with a comment saying exactly why. `build_interaction_layers`
was the consumer throwing it away, so the fix is one composed key and one
extra clause:

    ResidueColorLayer key   "B/TYR652" when the chain is known
                            "TYR652"   when it is not
    the selection           (and (= atom.auth_asym_id B)
                                 (= atom.auth_comp_id TYR)
                                 (= atom.auth_seq_id 652))

The bare form is still accepted and is still right for a single-chain
receptor or a source with no chain labelling, so a producer that cannot
say which chain degrades to the old behaviour rather than losing the
colouring. **The chain goes in UNQUOTED**, for the reason residue NAMES
already do: quoting matches zero atoms while the overpaint commits
successfully. A chain id that would not survive that is dropped rather
than guessed at.

The ambiguity is the ordinary case rather than an edge one. Over the
cached deposits, counted from the PDB text:

    6WGT   3 chains, 370 of 388 residue keys in >1 chain   (95%)
    1HSG   2 chains,  99 of  99                            (100%)
    4DKL   1 chain,    0 of 442                            (0%)

and even the ligand is ambiguous -- all three copies of 7LD are
`auth_seq_id 1201`, in chains A, B and C.

**A SINGLE-CHAIN RECEPTOR CANNOT SHOW THIS**, which is why it survived:
4DKL, the deposit most of the docking work was measured on, has one chain
and 0% collision. Any test of residue targeting has to use a multi-copy
deposit or it is asserting against a structure where the bug cannot exist.

##### TWO ORACLES WERE BUILT AND THROWN AWAY BEFORE ONE WORKED

**A COMMIT THAT SUCCEEDS PROVES NOTHING.** The first probe asked whether
`atom.auth_asym_id` is a real mol-script symbol by committing an overpaint
and watching for a rejection. The candidate came back OK -- **and so did a
control using a symbol that cannot exist**. Mol* accepts a nonsense
selection and paints nothing, silently, which is the same failure mode the
quoted-residue-name finding already records. Both results were discarded.

What replaced it measured the EFFECT, on 6WGT, at 900x700:

    baseline, no overpaint                298 red px
    no chain term                         673        +375
    chain B only                          432        +134   ~ a third, as
                                                            three chains predicts
    CONTROL: chain Z, absent              298          +0   the arm that says NO

**THEN THE TEST WRITTEN FROM IT WAS TIMING-DEPENDENT AND HAD TO GO.** It
waited fixed durations for frames to land, passed when run alone, and
failed when run with its own file -- the exact class this file forbids.
The guard that shipped instead is a seam: `residueSelectionClauses` and
`applyResidueColors` share ONE `residueClause` builder, so what a test
reads is what the viewer paints, and
`test_the_colouring_and_the_diagnostic_share_one_builder` fails if the
chain term is ever written in two places. The live pixel measurement above
is what establishes the semantics; the seam defends that the expression
keeps being emitted.

Three mutations, three caught: Python dropping the chain, the page
ignoring it, and the chain quoted.

**AND ONE OF MY OWN PROBES LIED FIRST.** An aggregate sweep over
`struct.units` reported "0 keys matching more than one chain" on 6WGT --
flatly contradicting the PDB, which says 370. The tell was that its key
count, 377, is exactly chain A's residue count. Counting one residue
directly (`GLN72 chains: A,B,C`) is what settled it. **When two
measurements of the same thing disagree, the smaller and more direct one
is the one to trust**, and neither should be reported until they agree.

`showDepositedCoordinates()` in `viewer.html` updates the
`structure-from-model` transform to `{name: 'model'}` after every load.
**Scoped to one invariant** -- the structure DISPLAYED, the structure the
box is derived from and the structure docking runs against must be the same
coordinates and the same copy -- and explicitly NOT a claim that deposited
coordinates are the better representation in general. It is also what the
app already defaults to elsewhere: building an assembly for docking is an
opt-in in the Contents dialog, defaulted off, which the viewer was silently
contradicting. That opt-in is untouched.

**THE OPTION THAT LOOKS LIKE THE FIX DOES NOTHING.** Passing
`structure: {name: 'model'}` in `loadStructureFromData`'s options is
accepted and ignored -- the state tree still shows
`type: {name: "assembly", params: {id: "1"}}`. The transform has to be
updated after the load.

**A CIRCULAR FRAME TEST WOULD HAVE PASSED.** The obvious check is
`box_from_ligand` centre == the box the page was given == the ligand's
coordinates; the first two are the same value handed along, so that pair
proves plumbing and nothing else. Reading the ligand's coordinates out of
**Mol\*'s own loaded state** reported 0 of 24 atoms inside the box
immediately. Re-verified across seven receptors chosen for shape variety
(6WGT, 1HSG, 4DKL, 3HS4, 5I6X, 4EY7, 6X3T): every one now encloses its
boxed copy, and the multi-copy entries show all copies while enclosing only
the boxed one, which is the correct relationship.

### Drawing a box: `BoxShape3D` exists, and the mirror lies about it

`molstar.lib.plugin.StateTransforms.Shape` has `BoxShape3D` and
`getBoxMesh`; `createDefaultParams()` is
`{bottomLeft, topRight, radius: 0.15, color: 16711680}`. Probed against the
vendored bundle in a bare `QWebEngineView`, the same way Ketcher is, rather
than reasoned about -- `MolStarViewerBackend` inherits `apply_shapes`' no-op
default, so "Mol* cannot draw shapes" was a plausible and wrong conclusion.

**A BACK-TO-BACK BURST LEAVES ORPHANS WHILE THE STATE REPORTS ONE BOX.**
Three `showSearchBox` calls in a row left THREE shapes in the scene while
`searchBoxState()` correctly said one: a builder created before the
previous commit resolved deletes a ref the state tree does not have yet, so
the delete silently no-ops. Fixed with one desired state and one applier
that re-checks on completion, so a burst of any length costs at most two
commits. **The guard counts shapes in the SCENE**, not stored refs.

**AND `loadStructure` CALLS `plugin.clear()`**, which wipes the box and
leaves the page's refs dangling. The DESIRED box survives a load
deliberately and is restored onto the new structure, which is what makes
loading a receptor redraw its search region without the window sequencing
the two calls.

**MEASURING THE RENDER OVER THE WHOLE WINDOW SAYS THE OPPOSITE OF THE
TRUTH.** Ink went 39940 -> 39942 (+2) on the first attempt and read as
"committed but nothing drew". Two faults in the metric: the scene was empty
so the camera framed nothing, and Mol*'s UI chrome is ~57% of the window.
With a structure loaded and the count cropped to the 3D canvas, 16778 ->
20270 (+20.8%).

## THE ALIGNMENT COULD NOT MOVE A TORSION, AND THE RMSD COULD NOT SAY SO

Reported against MPMI vs 4-HO-MPMI -- the same skeleton, one hydroxyl
apart -- aligned on *Common scaffold (MCS)*: "the tail pyrrolidine is not
aligned at all, which makes no sense". The panel said **score 109.75, RMSD
0.116, 14 paired atoms**, which is a confident, healthy-looking result for
a picture that is visibly wrong.

Reproduced bit for bit from `MPMI.ocsproj`, the project the report came
from, BEFORE anything was changed. Three defects:

**A. THE STORED CONFORMERS WERE THROWN AWAY.**
`_EnsembleAlignmentTask` calls `engine.mol_from_model`, which reads
`model.molblock` -- the 2D drawing -- and never `model.conformers`. The
reference had **17** stored conformers and the alignment embedded five
fresh ones instead.

**B. O3A IS A RIGID SUPERPOSITION.** The MCS fixes the PAIRING; `Align()`
then finds the best rigid transform for it. It cannot rotate a bond. So a
probe embedded in isolation keeps whatever rotamer the embedder chose, the
rigid indole lands perfectly because it is in the MCS, and the pyrrolidine
lands wherever it was. **More starting conformers is a lottery, not a
fix** -- measured, at "Accurate" (20 conformers) rigid mode stumbles onto a
good rotamer for this molecule anyway, which is exactly why sampling is
not the answer.

**C. `AddHs` WITH NO `addCoords=True` PUTS EVERY HYDROGEN AT THE ORIGIN**
when the molecule already carries a 3D conformer -- measured on this
fixture, all **18** of them -- and `Is3D()` stays True throughout, so it
returned silently. Unreachable while the input was always a 2D drawing.
**A is what makes it reachable**, so it lands with it.

### The measurement, through the shipped path

    mode                             score   rmsd   core   flex   geometry
    rigid (today)                   109.75  0.116  0.083  0.931  embedded
    flexible                        125.15  0.046  0.052  0.036  constrained
    flexible + ref conformers       125.24  0.023  0.027  0.016  constrained

Flexible RMSD **0.931 -> 0.036, 26x**.

**AND A ALONE MAKES THE REPORTED CASE WORSE**, which is why measuring
first mattered: the probe has no stored conformer, so using the
reference's only moves the target -- core goes to **3.493** while the tail
improves to 0.212, and the popped-out shot shows the indole benzo ring
plainly out of register. B is what fixes the picture; A is a refinement
that needs B.

### THE OBVIOUS METRIC CANNOT BE COMPUTED

The first draft of the guard said "RMSD over the atoms NOT in the MCS".
**Those atoms have no correspondence by construction** -- the hydroxyl
exists in one molecule and not the other -- and every patch for it (a
second MCS, nearest neighbour, matching indices) invents one and turns the
oracle into an arbitrary geometric metric.

The atoms worth measuring are INSIDE the correspondence. What separates
them is FLEXIBILITY, not MCS membership: both molecules have the
pyrrolidine, so the MCS covers it. `mcs_partition` splits the MCS's own
pairs:

    1  pairs     the MCS correspondence, heavy atoms only
    2  scaffold  the largest fused ring system OF THE PATTERN -- computed
                 ONCE, on the shared subgraph
    3  cuttable  bonds matching RDKit's own RotatableBondSmarts
    4  core      reachable from the scaffold without crossing one
    5  classify  a PAIR takes its pattern atom's bucket

**STEP 2 IS THE LOAD-BEARING ONE.** Classifying each molecule
independently is how "14 core atoms here, 17 there" happens, and two
RMSDs over two different partitions are not comparable.

### A FLEXIBLE REQUEST THAT CANNOT EMBED DEGRADES AND SAYS SO

Pinning the shared atoms onto the reference is not always geometrically
possible, and that is chemistry rather than a bug: **ibuprofen's MCS with
naproxen spans BOTH rings of the naphthalene**, so no conformer of a single
benzene can put its shared ring atoms there. Distance geometry correctly
refuses -- measured, it fails at all 14 constraints, at the 6 ring ones,
and at every subset carrying the real shape, while an arbitrary 6 succeed.
Forcing it would mean inventing a geometry, so it falls back to an ordinary
embed and reports `embedded` rather than `constrained_embed`. The panel
shows that column, so "flexible did not take on this pair" is visible.

**`ff.Initialize()` IS REQUIRED AFTER `AddExtraPoint`**, or `Minimize`
raises a "size mismatch" pre-condition -- the force field still believes it
holds as many points as the molecule has atoms.

### `matched_atoms` IS NOT THE MCS SIZE

`len(alignment.Matches())` is O3A's own count. The panel printed it
unconditionally, so an MCS-method result read **"14 paired atoms" for a
maximum common substructure of 33**. Two fields now -- `mcs_atom_count`
and `o3a_match_count` -- because one field with a method-dependent meaning
is how that ambiguity returns under a new label.

### The mutation pass found a vacuous guard, as it usually does

Six arms. **M1 (reverting `addCoords=True`) SURVIVED** against a test
named for it: the fixture stored a conformer that already had EXPLICIT
hydrogens, so `AddHs` added nothing and the bug could not fire. It needs a
3D conformer carrying IMPLICIT hydrogens -- `Chem.RemoveHs` then
`MolToMolBlock` -- and `test_the_hydrogen_fixture_really_has_hydrogens_to_place`
now asserts that setup so it cannot go vacuous again.

**The invariant needs no table and no tolerance**: every added hydrogen is
nearer to the heavy atom it is bonded to than to any other. `Is3D()` and
"the coordinates are finite" both pass with the bug in place.

**And the self-alignment tolerance was below the representable
precision.** It asserted `abs=1e-6` and passed because rigid mode handed
O3A the same object twice; flexible builds a constrained conformer and
lands 4.9e-05 away. That is an order of magnitude BELOW the **5e-4**
molblock floor this file already records. A tolerance tighter than the data
format can represent is not a stronger test.

### THE 3D VIEW WAS 63 PIXELS TALL, and adding a control made it worse

Measured in the running app with the new `align_report` step, which dumps
every DIRECT CHILD's height -- "the viewer is 63 px" does not say which
sibling to argue with:

    panel 699 | viewer 398x63 | QGroupBox=414 QTableWidget=160 PopOutHost=95

The settings box and a results table fixed at 160 px for two rows left the
overlay -- this panel's entire output -- a strip. Two changes:

    Accuracy and Flexibility share ONE flow_row     2 form rows -> 1
    the table sizes to its rows under a cap         160 -> 100

    before   viewer 398x63
    after    viewer 398x123

`flow_row` rather than a `QHBoxLayout`, because a horizontal layout's
minimum width is the SUM of its children and this panel has already set the
whole window's minimum that way once.

**JUDGE AN OVERLAY IN THE POPPED-OUT WINDOW, NOT IN THE STRIP.** A 123 px
crop shows an edge of the molecule and nothing about whether it
superimposes. `{"do": "pop_out", "panel": "3D_Alignment"}` then
`{"do": "shot", "widget": "popout"}` gives 960x720 of it, which is what
settled both arms.

### The drive steps this added

    {"do": "open_project",     "path": "C:/tmp/MPMI.ocsproj"}
    {"do": "align",            "flexibility": "Flexible"}   (new option)
    {"do": "align_report",     "tag": "after"}
    {"do": "ensemble_visible", "row": 1, "on": false}
    {"do": "overlay_colour",   "mode": "element"}

The last two drive the CONTROL rather than the helper behind it: a test
that calls `_show_ensemble` directly proves the helper works and says
nothing about whether the box is wired to it.

## POPPING A VIEW OUT: the widget MOVES, and that was measured first

Reported against 3D Alignment: two molecules aligned on a common
scaffold, and "the 3d conformer is contained in that tiny area". The
overlay IS that panel's entire output and it renders into a strip about
400x90 px, because a settings group box, a 160 px result table and the
style row are all fixed height above it in a dock that opens at 420.

`ui/widgets/pop_out_host.py` is the mechanism. `PopOutHost` wraps one
view, puts a `↗` button in a thin header row, and moves the widget into a
`PopOutWindow` and back. Six sites use it: the alignment overlay, and
Quantum Chemistry's Surfaces, IR, 1D Signals and three correlation plots.

**IT MOVES THE WIDGET; `FactView.open_in_window` COPIES ITS VIEW. Both
are right, and the difference is the thing to keep.** A report is cheap
to re-render and two side by side is the use case. A 3D view is stateful
-- the camera angle the user just set is the whole reason they want it
bigger -- so copying hands them a default camera and a second
QtWebEngine process set.

**THE RULE, because an agent meeting `open_in_window()` will assume the
`FactView` pattern:** for a stateful visualisation the documentation and
the help contract must SAY which one it is. `workspace.pop_out_view`'s
text is explicit that the view moves. Never infer it from a label.

### RE-PARENTING A `QWebEngineView` SURVIVES, and nothing here had ever done it

Measured before a line was written, on a real display, with an ensemble
loaded and the camera turned to a distinctive angle:

    stage                    identity   parent chain              ink%  black%
    docked                   same       View -> host -> panel     10.5  0.2
    detached                 same       View -> QDialog -> ...    10.7  0.2
    drag while detached      --         camera MOVED              --    --
    returned                 same       View -> host -> panel      9.7  0.1
    3x round trip            same       stable                     9.0  0.2
    destroyed after return   ALIVE      View -> host -> panel      9.7  0.1

The camera quaternion came back byte-identical across the move, a
synthetic drag landed while detached, and the canvas genuinely re-laid
out -- 796x596 -> 1800x1400 -> 796x596 -- rather than freezing on a last
frame, which is what distinguishes a live page from a stale one.

**BLACK FRACTION IS COUNTED SEPARATELY FROM INK**, because a failed
render is a BLACK canvas and scores as heavily inked; this file already
records that metric being read backwards once, at 94875 against 3067.

**READ THE PAGE'S OWN CANVAS, not the widget.** A `QWebEngineView`
renders out of process, so 3Dmol's `viewer.pngURI()` is the honest
source and `widget.grab()` is not.

### THE LIFECYCLE: three states, four transitions, nothing else

                        pop_out()
            DOCKED  ---------------->  DETACHED
              |     <----------------      |
              |      return_home()         |
              |      window closed         |
              |                            |
              |   owner destroyed          |  owner destroyed
              +----------> DISPOSING <-----+

**"LOOKED AWAY FROM" AND "DESTROYED" ARE DIFFERENT THINGS**, and the
first draft of this design conflated them -- it said the owner being
destroyed "returns the view home", which is incoherent once there is no
home to return to. Six Qt events mean "the panel went away" and only two
bring the view back:

    another dock selected                stays open
    another tab selected                 stays open
    the dock hidden or closed            stays open (retained, not destroyed)
    the dock floated                     stays open
    a new job / the result cleared       RETURNS HOME (a semantic reset)
    the owner destroyed / app shutdown   DISPOSING, no restore

Which is why there is deliberately **NO `hideEvent` hook**: the first
four rows are all `hideEvent`, so a hideEvent-driven return snaps the
window shut every time the user glances at another tab.

**THE WINDOW IS PARENTED TO THE HOST**, which is what makes `DISPOSING` a
cascade rather than a policy somebody has to remember: panel -> host ->
window -> content, one direction, nothing dangling. An unparented window
outlives its owner, which is the one forbidden outcome.

### `finished` IS THE PRIMARY HOOK AND `closeEvent` IS NOT

A review proposed driving the restore from `PopOutWindow.closeEvent()`
with `finished` as a backstop. It is the wrong way round, and it leaks
the Escape key:

    the X button   close() -> QCloseEvent -> QDialog::closeEvent
                   -> reject() -> done() -> finished
    Escape         keyPressEvent -> reject() -> done() -> finished
                   ... and NO QCloseEvent at all

So `closeEvent` alone silently leaves the content inside a hidden window.
`closeEvent` is kept as an additional EARLIER hook on the X path, and
`return_home` is idempotent so both firing is harmless.
`test_escape_returns_the_view_even_though_it_sends_no_close_event` is the
guard, and it is the only thing that catches the closeEvent-only
mutation.

### VIEW CONTROLS STAY IN THE PANEL; the window gets only a Return button

Alignment's `Style:` combo stays in the dock and goes on driving the
detached overlay, because `Mol3DViewerBackend` holds the page and the
channel rather than the parent widget. That falls out of the existing
design rather than being built, which is exactly why it needs an
assertion -- free today, easy to break.

A duplicate control in the window would be two widgets for one setting.
The header row therefore never moves, and a header widget that already
belongs to another layout is REFUSED in the constructor, because the
silent mistake is

    layout.addWidget(style_combo)          # still there
    PopOutHost(..., header=[style_combo])  # and now here too

which Qt honours by stealing it and leaving a hole.

**THE BUTTON COSTS THE PANEL NOTHING.** Measured either side of the
change, since a `QHBoxLayout`'s minimum is the SUM of its children and
this file's worst layout bug came from exactly that: the alignment
panel's minimum is **297 x 392 before and after**. The note label in the
settings box sets it; the header row has slack.

### A PLAIN `QLabel` PLACEHOLDER, NEVER `empty_state()`

`QuantumChemistryPanel.empty_message_for_tab` returns the first
`is_empty_state` widget it finds anywhere under a tab, via
`findChildren`. Building the "showing in its own window" placeholder with
the helper whose NAME sounds right would put a hidden marked label inside
every host, and every wrapped tab would start answering for itself with
the pop-out's message. Two guards, one at each end.

### THE SECOND GLYPH WAS AN EMOJI, and only the magnified shot said so

The button first showed `U+2B1C WHITE LARGE SQUARE` while detached. All
22 tests passed, `--missing` said "Nothing matched", and a 3x crop of the
running app showed a **lavender emoji square** in the panel chrome.
Windows resolves that codepoint to a colour emoji font; `U+25FB`,
`U+29C9` and `U+1F5D6` all do the same.

**A PROBE THAT COUNTS COLOURED PIXELS CANNOT SETTLE IT.** At button size
ClearType's sub-pixel fringes are genuinely coloured, so an unassigned
control codepoint scored as "drew, in colour" too and the probe could not
discriminate. `QFontMetrics.inFont()` is no help either, for the reason
this file already records. **The screenshot was the oracle.**

The state is not carried by a glyph at all now: `setChecked` is drawn by
the platform style, is themed, and cannot be missing from a font.
`U+2197` is kept for both states because it was confirmed in a screenshot
of the real application at the real size.

### THE MUTATION PASS FOUND A VACUOUS GUARD, as it usually does

Nine arms, nine caught, each by the intended guard and each running the
full 96 -- but **M5 only after the guard it was aimed at was repaired**.
`test_a_detached_view_survives_switching_to_another_tab` never showed its
panel, and **a widget that was never shown receives no hide events at
all**, so it passed with a `hideEvent` hook installed and without one.
It shows the panel now and asserts its own setup -- that switching the
tab really did hide the host -- because otherwise the claim is about a
hide that never happened.

This is the same lesson as `repaint()` and `resize()` on an unshown
widget, one event along.

### THE DRIVE STEPS, and the trap in the first run

`{"do": "align"}` and `{"do": "pop_out", "panel": "3D_Alignment"}` --
note the UNDERSCORE, since `_dock_by_panel_id` matches
`dock.objectName()`. `{"do": "shot", "widget": "popout"}` photographs the
detached window.

**NAME THE REFERENCE.** The first run reported "Ensemble alignment
failed" and read as a bug in the panel: with no reference named, the
combo sits at index 0, which is the STARTER MOLECULE, and it has no
molblock. Same shape as the `smiles`/`conformers` trap already recorded
-- a step that does not select what it added. The failure also made the
detached screenshot 4.6 KB against 63 KB, which is how it was noticed.

## A HORIZONTAL ROW'S MINIMUM IS THE SUM, and it set the whole window's

Reported as "the rightmost tab ... will change size, and even became
pretty much inaccessible until I got out of fullscreen. But then while
windowed, clicking another menu item, and then maximizing will fix it."

**The window's minimum width was 1877-2055 px against a 1920 px screen**,
varying by which right-hand panel was showing. So `resize()` was silently
clamped, the window really was 2055 px wide on a 1920 px display, the
panel rail sat at x=1785..2055 with 135 px past the edge, and switching
panels moved the minimum by up to 178 px. Every symptom follows from that
one number, including why a windowed/maximize cycle "fixed" it.

**The panel in the screenshots was not the cause.** Measured with the
`geometry` drive step: every right-hand dock's minimum is 102-280 px and
the scroll wrappers ask for 58, so `_wrap_scrollable` -- the obvious
suspect, whose docstring even promises a "defensive floor" -- was
innocent. It came from the centre:

    central QStackedWidget      minHint 1336
      MoleculeViewer3DWidget    minHint 1330
        widest direct child     minHint  143   <- nothing explains it

Nothing inside it reached even 300 px, because **a `QHBoxLayout`'s
minimum width is the SUM of its children**: fourteen controls at 1252 px
plus thirteen gaps = 1330. "Which child is widest" is the wrong question
for a horizontal layout and the reason a chain walk comes back empty --
dump every descendant over a threshold as well, which the drive step now
does.

`ui/widgets/flow_layout.py` wraps instead, and `FlowLayout.minimumSize`
returns the widest SINGLE item. Minimums fell to 690-868, the window to
1920, the rail to x=1650..1920.

**`QToolBar` LOOKS LIKE THE FIX AND SILENTLY LOSES CONTROLS.** Its
overflow (`>>`) button exists only for a toolbar in a `QMainWindow`
toolbar area; as a plain child widget it drops whatever does not fit with
nothing to reach it by. Measured: 8 controls at 320 px left **1 visible
and no extension button**, while the minimum fell 2410 -> 115. A 20x
improvement that loses seven controls is not one.

**A SYMPTOM TEST CAN PASS WITH THE BUG RESTORED.** Both revert-mutations
were caught only by the structural tests at first, because Qt clamps
`resize()` -- so the window simply grew past the screen and the rail sat
comfortably inside an over-wide window. Asserting that the window really
BECAME the size it was asked for is what makes it a test of the symptom.

### What the geometry says about the GUI's shape -- data, not a decision

Recorded from that baseline for a future consolidation pass, since the
application has grown from an editor with calculators into a workbench
and the "every feature gets a panel" assumption will eventually bite.
**Nothing here is acted on**, with ONE exception now: the dock's
STARTING width, below.

#### ACTED ON: the right dock now opens at 420, not at its minimum

Nothing used to set a starting width, so Qt handed every panel its own
minimum -- 280 px, permanently, until somebody dragged it. **That is why
the Properties caption clipping was reachable at all**: the panel spent
its whole life at the narrowest width it was legally allowed to be.

Re-measured in the running app, and these supersede the numbers in the
list below, which are CONTENT MINIMUMS from an older tree. These are
each dock's `sizeHint` -- what it would like:

    Quantum Chemistry 576   Docking        466
    Interactions      546   Atom Inspector 417
    3D Alignment      518   Batch          413
    Structure Check   467   Jobs           264

420 clears three of those outright and comes within 10% of two more.
Capped at a quarter of the SCREEN, so 1920 gives 420, 1366 gives 341,
and anything under ~1120 keeps today's behaviour because the panel's own
minimum wins. A saved layout is never overridden.

**THE CAP MUST COME FROM THE SCREEN, NOT `self.width()`.** This runs
during construction, before the window is shown, where `self.width()` is
Qt's pre-show default rather than the geometry `restoreGeometry` is
about to apply -- about 1400 px on a 1920 px display. Capping against it
produced 350, which is a plausible-looking quarter of a window that
never exists.

**AND THE SUITE CANNOT SEE ANY OF IT.** `offscreen` reports an 800 px
screen, so the cap always bites and the computed width equals the dock's
minimum -- applying the feature and deleting it are indistinguishable by
outcome. `initial_right_dock_width` is therefore a pure function and the
table is tested directly; deleting the CALL is the one mutation nothing
catches, and it is written into the test rather than papered over.

- **The rail costs 270 px, and it IS collapsible** -- this entry used to
  end "whether it should be collapsible is a real question", and by then
  it already was. `PanelRail._on_group_clicked` folds the name list on a
  second click of the group already showing, and `set_list_visible` /
  `is_list_visible` shipped with it; the `_names` container exists so the
  fold is one `setVisible`. Measured: 270 px expanded, **40** collapsed,
  and the window's own minimum follows it 716 -> 486.

  **What was actually missing was PERSISTENCE**, which is a different
  entry in the same list and was found by reading the code rather than
  the note. `MainWindow` saved `ui/pinned_panels` and nothing else, so
  anyone who folded the rail to reclaim 230 px did it again every launch.
  It now stores `ui/rail_collapsed`, restored AFTER
  `_restore_window_state` for the reason `initial_right_dock_width`
  records.
- **Every dock is displayed at 280 px while its content wants far more**:
  Quantum Chemistry 669, Docking 462, Batch 409, Atom Inspector 352.
  Those four are the panels genuinely relying on scrolling, not merely
  benefiting from it.
- **The cheap panels are cheap**: Jobs wants 66, Structure Check 186,
  Interactions 211, Compare 222.
- **ACTED ON: the centre has a deliberate floor of 400 px.** This entry
  read "no minimum worth the name (~280 after the fix)" and the real
  figure was **149**, measured in the running app -- below even the
  `CENTRAL_FLOOR = 200` that `tests/test_right_dock_width.py` had been
  reasoning about since the flow-layout work. That constant was
  test-only: nothing enforced it, and it held solely because no dock
  happened to ask for enough to break it. The test file imports it from
  `main_window` now, so the two cannot drift.

  **ON THE `QTabWidget`, NOT ON A PAGE AND NOT ON THE WINDOW.**
  `centralWidget()` holds three pages (2D Editor, 3D Viewer,
  Macromolecule Viewer) and a `QTabWidget` takes the MAXIMUM over them,
  so a floor on the editor page propagates today by accident and
  evaporates when the pages are rearranged, while guaranteeing nothing
  for the other two. It is also the object the CEILING guard already
  measures, so the two bounds are on one quantity rather than two.

  **400 is bounded on both sides by measurement**, not chosen: the
  non-centre chrome is 567 px on the real desktop and 854 under
  `offscreen`, putting the window minimum at 967 and 1254 against the
  1366 this product supports. 640 would put `offscreen` at 1494 and
  redden `test_the_window_can_be_made_narrower_than_a_small_laptop`. And
  400 is what makes the guard able to say NO at all: `offscreen`'s
  emergent centre minimum is already 282, so a floor of 200 could never
  fail, which is the same blindness `initial_right_dock_width` records
  one entry up.

  **`minimumSizeHint()` DOES NOT ANSWER THIS.** It is Qt's RECOMMENDED
  minimum and is unmoved by `setMinimumWidth` -- measured, hint 282
  against an enforced minimum of 400 -- so the first guard written for
  this failed against correct code. Assert the behaviour: squeeze the
  window and read the centre's actual width.
- **Any future single-row toolbar will reproduce this exactly.** The
  guard in `tests/test_right_dock_width.py` catches it at the window
  level; `flow_row()` is the cure.

## A PANEL THAT LEAKS ITSELF AND THEN POLLS FOREVER

The Linux segfault's cause, and the first entry in this file's long
access-violation family that names a MECHANISM rather than heap layout.
Every link was already documented here; nothing was joined up.

    JobsPanel.refresh connects a lambda capturing `self`
      -> PySide6 holds it STRONGLY, so the panel is immortal
      -> its 500 ms QTimer is never stopped, so it polls forever
      -> every poll calls setItem/setCellWidget, which DELETE the old cell
      -> _wait_until pumps processEvents() for up to 60 s
      -> Qt destroys a widget inside an unrelated test's event dispatch
      -> segfault, in whichever test was pumping

**THE LEAK IS "ANY PANEL THAT EVER HAD A JOB TO SHOW", and that is what the
guard's fixture has to reproduce.** The lambda lived inside
`for row, job in enumerate(jobs)`, so measured with `_survives_collection`:

    one active job at construction    leaks: True   -> False after the fix
    no jobs at all                    leaks: False  (both)

A fixture built from a bare `JobManager()` **passes against the bug**, which
is why `test_a_jobs_panel_with_no_jobs_could_never_have_shown_the_leak`
exists -- it states in the suite, rather than in a comment, that the empty
panel is not evidence.

### WHAT IT COST, and why one number would have misled

Instrumented over `test_jobs_panel.py` + `test_molstar_viewer_backend.py`
alone -- five leaked panels, refreshing inside a file five positions later:

    arm                 cross-file refreshes   widget destructions there
    neither (master)                     170                         680
    the bound method
      alone (A)                            0                           0
    the snapshot
      alone (B)                          365                           0
    A + B                                  0                           0

**NEITHER FIX SUBSUMES THE OTHER.** B alone takes the DESTRUCTIONS -- the
segfault site -- to zero and leaves the panels immortal, so their refresh
count goes UP: a cheap refresh fits into the same pump window more often. A
is what removes the refreshes at all, because a collectable panel's timer
dies with it. Read either column alone and the other fix looks unnecessary.

### THE VISIBILITY GATE HAD TO LAND LAST, or it would have taken the credit

A panel that is never shown never polls, so stopping the timer in
`hideEvent` makes the crash disappear **without touching the leak**. The
attribution table above was taken before that existed, deliberately.

**AND ITS GUARD'S `show()` IS LOAD-BEARING IN THE OPPOSITE DIRECTION FROM
THE USUAL ONE.** This file records repeatedly that a widget which was never
shown runs almost none of its own code, so a guard skipping the show passes
vacuously. Here it does not: no show means no hide event, so the timer stays
running and the guard **FAILS AGAINST CORRECT CODE**. Measured both ways;
the first draft of that docstring had it backwards.

**THE TIMER IS STILL STARTED IN `__init__`.** Starting it only in
`showEvent` means the panel polls if and only if such an event arrives, and
a frozen Jobs list is indistinguishable from an idle one -- which is what it
shows most of the time. That mutation is green everywhere except
`test_a_freshly_built_panel_polls_without_waiting_for_a_show_event`.

### FIVE FILES HAD THE SAME LAMBDA; THREE HAD ALREADY BEEN FIXED

The rule existed, the cure existed (`setProperty`/`setData` + a bound method
reading `sender()`), and the population was a hand-kept list of two.

    ui/panels/jobs_panel.py                 the crash site
    ui/panels/atom_inspector_panel.py       every panel
    ui/dialogs/structure_lookup_dialog.py   two, every dialog
    app/main_window.py                      a context-menu action, one more
                                            rooted on every right-click
    services/quantum_chemistry_service.py   three, on a QProcess

**THE `QProcess` CASE LOOKS HARMLESS AND IS NOT.** The captured object is a
long-lived service, so "it lives anyway" is the obvious reading -- but the
service OWNS the process and the process holds the lambda holds the service,
which is a cycle, and the callable lives in PySide's own map that the cyclic
collector cannot see through. Every job run rooted the whole service graph.

`test_no_signal_is_connected_to_a_self_capturing_lambda` asserts it over the
package, in the shape `test_every_single_shot_timer_is_bound_to_a_context_object`
already uses. **265 connect() calls, 0 offenders**, and it prints that count
even when it passes -- `checked >= N` catches the walk collapsing to zero,
the printed count catches drift that stays above the threshold.

**IT SAYS WHAT IT DOES NOT COVER, in its own docstring**, because a green
structural guard reads as a lifetime proof: it pins ONE SHAPE and is blind
to `self` reached through another name, a `functools.partial`, a reference
held elsewhere, or a Qt parent. The two per-widget outcome guards stay.

### AND THE MUTATION HARNESS LIED ONCE, AGAIN

The arm that removes the `checked >= N` threshold sliced the file between an
`index()` and a later `index()` -- and the second matched the OTHER guard's
identical `assert not offenders`, so the slice DUPLICATED text instead of
removing the threshold. It reported a confident result from an edit that
never landed. Sixth instance in this file. **Assert the edit before running
the arm**: `assert 'assert checked >= 200' not in mutated`.

Correctly applied, it is the failure mode worth knowing: with the threshold
gone and the walk broken the guard passes **green while checking nothing**,
printing `checked 0 connect() calls`.

## THE LINUX SUITE CRASHES ON 4 OF 6 COMMITS, AND THE INSTRUMENT NEEDED FIXING TWICE

Measured 2026-08-26, after the jobs-panel fix landed. The entry above
says "THAT IS ONE RUN" about the green Linux job on `f46537e`, and
correctly declined to call it proof. Master's own subsequent runs have
now answered it, and the answer is no.

    9db5ff8  CRASHED     the sigma/pi merge
    398c084  CRASHED     that branch's PR run
    9ce6202  CRASHED     a DOCUMENTATION-ONLY commit
    469ec27  CRASHED     the #48 merge
    f46537e  OK          <- the one run the entry above cites
    e9b2716  OK

Only these six carry the verdict, because the annotation that exposes it
was added in `b229bb0` and nothing earlier can be read this way.

**`git diff f46537e 469ec27` IS EMPTY.** Those two commits carry
byte-identical trees, and Linux passed on one and crashed on the other.
That is the strongest single fact here: **no code change causes this**,
so no bisect can find it and no commit can be blamed. A
documentation-only commit crashing is the same statement said twice.

### THIS SECTION'S NUMBERS ARE FROM WINDOWS, AND THE CRASH IS ON LINUX

Stated first, because everything below is worth less than it looks
otherwise. The census figures here were taken on:

    python 3.13.7 | PySide6 / Qt 6.11.1 | rdkit 2025.09.6
    Windows-11-10.0.26200-SP0 | QT_QPA_PLATFORM=offscreen
    6090 passed, 15 skipped, 19m09, zero crash markers

**"Linux" is not a reproducible experimental condition and neither is
"Windows"** -- record the versions beside any figure that will later be
compared against CI, which is the whole reason to instrument this at all.

### The census was broken twice, and the full suite is what found it

`OPENCHEM_CENSUS=<path>` switches on the widget-lifetime census in
`tests/conftest.py`. Both defects shipped in `68aa89e`/`40f9fcf`, and both
survived because **nobody had run the full suite with it enabled**.

**ONE: IT REDDENED THE SUITE WHENEVER IT WAS SWITCHED ON.** `tests/` has
no `__init__.py`, so pytest loads the conftest under its own plugin name
-- and four tests in three files do `from tests.conftest import
painted/ink`, which imports the SAME FILE again under a second module
name and re-runs it at module level, calling `_start_census()` a second
time. The double-wrap guard then fired:

    census OFF   4 passed     `_CENSUS_PATH is None`, returns early
    census ON    4 failed     RuntimeError from the guard

An instrument that reddens the suite exactly when enabled is the hazard
that guard exists to prevent, restated. The flag records the SOURCE FILE
now rather than a bool: re-executing the same file returns quietly, a
census from a DIFFERENT file still raises. Both halves are guarded and
**the narrow one is load-bearing** -- "never raise" satisfies the first
and silently deletes the stacked-instrument protection.

**AND THE CENSUS HAD NEVER RUN IN CI AT ALL, WHICH IS WHY THIS SURVIVED.**
`conftest.py` said "The Linux CI job sets it" and no workflow did --
measured, `grep -rn OPENCHEM_CENSUS .github/` matched nothing. So an
instrument written to diagnose a crash that only reproduces on Linux was
never switched on where that crash happens, and the four failures were
unreachable until somebody ran the full suite with it locally.

**I REPEATED THAT CLAIM HERE BEFORE CHECKING IT**, in this very section,
because the docstring stated it as a fact. A comment asserting an
intention is worse than silence: it is believed, and then quoted. It is
wired into the Linux job now -- which is what makes the sentence true --
and `census.txt` goes up beside `suite.log` as an artifact, because a run
that aborts has no pytest summary line while the census's last `BEGIN`
still names the test it died in.

**RETURNING BEFORE THE `open()` IS LOAD-BEARING.** The handle is opened
`"w"`, so a second execution that reached it would TRUNCATE the trail --
destroying the evidence in exactly the crash case where it is the only
evidence there is.

**TWO: IT COULD NOT TELL PROCESS TEARDOWN FROM A CROSS-TEST LANDMINE.**
`gone()` calls a destruction LATE when the test that built the widget is
not the test running now. At interpreter shutdown every survivor is torn
down while `_census_where[0]` still holds the LAST test's nodeid, so
every one of them trips that check:

    LATE lines written during the run          0
    LATE lines written after the last test   16022   <- all teardown

Every one of the 16022 fell after the final `end` line, which is the only
reason the two could be told apart at all -- by comparing line numbers, a
step no reader is going to know to take. A `pytest_sessionfinish` sentinel
names the boundary now, so each line says `died=<session teardown>`
outright. **It is a SENTINEL, not a report**: reporting totals from that
hook cannot work, because the process dies before it -- but a line saying
"the session ended here" has the opposite property, since if the run
aborts it is simply ABSENT, and its absence is the correct answer.

### What the corrected census measures

    built                        28875
    destroyed during the run     12853
    destroyed LATE, in the run       0
    alive at the last test       16022  -> all destroyed at teardown

**ZERO cross-test late destructions, re-measured with an instrument that
is not leaking.** So the conclusion the previous entry reached survives,
while the reasoning that produced it did not: `40f9fcf` was right to doubt
the instrument, and its own extrapolation -- "late destructions appear
immediately" -- is NOT reproduced. Neither a full run nor either of two
Qt-heavy pairs shows one.

**THE LEAK WAS REAL, and this is what it was worth**, measured on
`test_property_panel.py` with the original closure restored exactly:

    census as fixed    built 1918   destroyed 1918   alive     0
    the real leak      built 1918   destroyed  310   alive  1608

84% of widgets immortalised, and `40f9fcf`'s cited test
(`test_a_pending_metrics_dump_is_cancelled_when_the_panel_is_destroyed`)
fails with it and passes without, exactly as that commit says.

**AND MY FIRST TWO ATTEMPTS TO REPRODUCE IT SHOWED NOTHING, BECAUSE THE
MUTATION WAS NOT THE BUG.** The original captured `self` in the BODY of
`gone`, inside an f-string; I put `type(self).__name__` in a DEFAULT
ARGUMENT, which evaluates at def-time and captures nothing. Both arms came
back identical and I nearly wrote up "not reproduced". Same lesson this
file already records five times: **assert that the edit changed BEHAVIOUR,
not that the bytes changed** -- and for a closure, that the name really is
a free variable.

**THE 16022 ALIVE ARE NOT A MYSTERY AND MOSTLY NOT A DEFECT.** They come
from 23 files, and the largest contributors are the MainWindow builders
this file already documents as deliberately retained -- `conftest.py` keeps
every MainWindow for the session, and
`test_main_windows_are_deliberately_never_collected` fails if that
retainer is removed:

    3810  test_isotopes.py                  946  test_right_dock_width.py
    3255  test_main_window_empty_state.py   930  test_main_window_docking_visualization.py
    2815  test_main_window_menu_actions.py  620  test_command_palette.py
    1197  test_main_window_conformers.py    468  test_receptor_library_dialog.py

A widget still alive has never been destroyed, so it cannot be the thing
that faults. It is a leak, not a landmine -- which is what the earlier
census already said, and remains the right reading.

### THE CENSUS CAUGHT ONE, ON LINUX, ON ITS FIRST LIVE RUN

Run 33031947731, 2026-08-27 -- the first Linux job ever to have
`OPENCHEM_CENSUS` set, and it crashed, which is the whole reason the
instrument exists. What the trail says:

    the `# session finished` sentinel   ABSENT  -> it aborted
    the last BEGIN, with no `end`       tests/test_nmr_view_dialog.py::
                                        test_dialog_loads_a_conformer_into_
                                        the_3d_pane_when_one_exists
    test number                         3623, at 58%
    LATE lines in the whole trail       0
    at the last completed test          built 19963  destroyed 5991
                                        late 0  alive 13972

**THE CENSUS AND THE TRACEBACK AGREE INDEPENDENTLY**, which is what
validates the instrument rather than merely using it: `suite.log`'s
`Fatal Python error: Aborted` names
`test_nmr_view_dialog.py, line 48`, and the census's last `BEGIN` names
the same test, derived from a completely different mechanism -- a line
flushed before the test ran, versus a C-level traceback written after it
died.

**ZERO LATE DESTRUCTIONS, MEASURED ON LINUX AT THE MOMENT OF THE CRASH.**
The entry above establishes that on Windows, where the suite does not
crash; this establishes it on the platform where it does, in the run that
did. So an object destroyed inside an unrelated test's event dispatch is
not the mechanism here, and a theory starting there is starting in the
wrong place -- which is what the previous entry claimed on weaker
evidence and is now measured.

**AND THE FRAME IS A CONSTRUCTOR, NOT A DISPOSAL.** Line 48 is
`NmrViewDialog(engine, molecule, spectrum, conformer.molblock,
backend=backend)` -- the dialog being BUILT. That is a second frame of
ours across four Linux logs, and it points the opposite way from the
first: the `test_panel_rail.py` lead is `sendPostedEvents(widget,
DeferredDelete)`, a forced disposal. One says building, one says tearing
down.

**n=1, THE VICTIM MOVES, AND THE TEST PASSES LOCALLY** -- 5 of 5, and
59%/59%/63% previously against 58% here, on four different tests. That is
the documented order-dependent shape: the victim is chosen by heap layout
rather than by fault. It is a lead and not a finding, and the next Linux
crash now carries a trail to compare it against, which no previous one
did.

#### AND THE VICTIM DID NOT MOVE: 58% THREE TIMES, TWICE THE SAME TEST

Measured 2026-08-27 on PR #53, and it revises the paragraph above rather
than merely adding to it. The `::error::` annotation the entry below calls
untested-in-anger has now fired live, twice, and both times the job
reported **success at every level the REST API exposes**:

    33031947731   58%   test_nmr_view_dialog.py:48 ...conformer_into_the_3d_pane
    08cb4d5       58%   "an unidentified frame"
    ecf17e0       58%   test_nmr_view_dialog.py:48 ...conformer_into_the_3d_pane

**THE PARENT COMMIT CRASHED AT THE SAME PERCENTAGE**, which is what says
the child did not cause it -- `ecf17e0` adds 19 tests and shifts
collection order, and the crash did not move. So for THIS crash the
victim is stable, not chosen by heap layout, and "the victim moves" holds
across the 59%/59%/63% batch above and NOT within this one.

That makes `test_nmr_view_dialog.py:48` the first Linux frame worth
attacking directly. It is a CONSTRUCTOR -- `NmrViewDialog(...)` being
built -- which points the opposite way from the `test_panel_rail.py`
`sendPostedEvents(widget, DeferredDelete)` lead.

**IT IS STILL NON-BLOCKING AND THE WINDOWS GATE WAS GREEN**, all four
gating steps executed. The point of recording it is that three
`gh run view --json` calls would have said `success` three times.

**AND `gh run view --job ID --log` CANNOT ANSWER THIS.** The verdict goes
to `$GITHUB_STEP_SUMMARY`; the job log carries the fingerprint SCRIPT,
whose own text contains `Fatal Python error|Windows` and
`Extension modules:` as grep PATTERNS -- so grepping the log counts the
source and reports a crash on a clean run. Read the ANNOTATION:

    gh api repos/OWNER/REPO/commits/SHA/check-runs       --jq '.check_runs[] | select(.name|startswith("linux")) | .id'
    gh api repos/OWNER/REPO/check-runs/ID/annotations       --jq '.[] | select(.annotation_level=="failure") | .message'

### The two platforms have DIFFERENT signatures

    Linux CI    Fatal Python error: Aborted           at 59%, 59%, 63%
    Windows     Windows fatal exception: access violation

`Aborted` is `abort()` -- a Qt fatal, an assertion, a C++ exception
escaping -- and NOT a segfault. Nothing is printed before it: the log goes
straight from progress dots to the traceback, so whatever calls `abort()`
is not saying why. Whether the two platforms are one bug wearing two coats
is **not established**, and the difference is large enough that assuming it
would be a guess.

**ONE OF THE THREE LINUX LOGS NAMES A FRAME OF OURS, and the other two do
not.** That one is:

    tests/test_panel_rail.py, line 19 in _dispose
    tests/test_panel_rail.py, line 250 in
        test_clicking_the_active_group_again_collapses_the_rail

Line 19 is `sendPostedEvents(widget, DeferredDelete)` -- **the disposal
recipe itself**, not a later collection. That file is well behaved: every
test calls `_dispose`, which is the documented per-widget form and not the
forbidden global drain. So the suspicion it raises is that FORCING a
deferred delete is itself the dangerous moment, which is the opposite of
what the recipe assumes. **n=1, and the other two logs cannot corroborate
it**, so it is a lead and not a finding.

### THE CRASH-MARKER GREP FALSE-POSITIVES ON THE CENSUS'S OWN PROSE

Measured: a run reporting "crash markers: 4" had not crashed. The phrase
`Fatal Python error: Aborted` appears in `_start_census`'s docstring, and
pytest echoes the source of a failing function into the log as failure
context -- so four failures printed that docstring four times and the grep
counted its own subject. Same shape as the `INFRASTRUCTURE FAILURE` string
this file already records: **grepping for a phrase counts the source, not
the outcome.** The SUMMARY LINE is the oracle, and the pair to check is
that one EXISTS and that the marker count is 0.

### What it would take, recorded so the next attempt starts here

The reproduction is on the platform this project does not ship, at 4 in 6,
with a 17-minute round trip through CI and no local Linux environment.
Windows reproduces it too but at roughly 1 in 3, and with a different
signature.

The census works now and says **zero cross-test late destructions on
Windows** -- which is a real measurement and is not an answer about Linux.
The next attempt runs it THERE, where the annotation added in `b229bb0`
can carry the trail out, and where the sentinel's ABSENCE will say the
process died before the session ended.

`flush_deferred_deletes`' own docstring has said the whole time that the
crash it was written around is not fixed, and asks not to be read as
evidence that it is. That is still true, and this entry is the measured
version of it.


## A RED SUITE SILENTLY DISABLES EVERY GATE BEHIND IT

`.github/workflows/tests.yml` runs the suite and then three gates in the
same job -- the naming benchmark, the regulatory benchmark and the
ruleset validation. GitHub skips later steps once one fails, so **a red
suite takes the gates with it**, and they report as `skipped` rather than
as anything alarming:

    failure  Run the test suite
    skipped  Naming benchmark (must stay 181/181)
    skipped  Regulatory benchmark
    skipped  Validate regulatory rulesets

Measured: master was red across three pushes, so the benchmark this file
calls the arbiter of naming quality had not actually run in CI for any of
them. **Check the STEP LIST, not just the conclusion** -- a red run hides
how much never executed.

### A SECOND PUSH TO MASTER DOES THE SAME THING, and it is not a failure

Same outcome, different mechanism, and this one is self-inflicted.
`tests.yml` declares

    concurrency:
      group: ${{ github.workflow }}-${{ github.ref }}
      cancel-in-progress: true

and every push to master shares one ref, so **a follow-up push cancels the
previous commit's run wherever it had got to.** Measured on `3eb9423`,
cancelled by a one-line lockfile push that landed nine minutes later:

    success    Run the test suite
    cancelled  Naming benchmark (must stay 181/181)
    skipped    Regulatory benchmark
    skipped    Validate regulatory rulesets

The suite had already passed; the three gates never ran. The run's
conclusion is `cancelled`, which reads as "somebody tidied up" rather than
as "the arbiter of naming quality did not execute for this commit".

**IT IS NOT A COVERAGE HOLE IF THE TREE WAS ALREADY GATED, and that is
worth checking rather than assuming.** Those gates had run and passed on
the PR's own run for `cfb630b`, and `git diff cfb630b 3eb9423` is empty --
the merge carries the branch's tree byte for byte, which is the check the
"Running the tests" section already insists on for a different reason. So
the honest statement is that the commit is gated, by a run under a
different id.

The practical rule: **do not push to master while its previous run is in
flight** unless you mean to void it. Landing two commits nine minutes
apart costs one of them its gates, and a doc-only follow-up is exactly the
change nobody thinks to check for it.

**IT HAPPENS ON A PULL REQUEST TOO, AND `gh run watch --exit-status`
REPORTS IT AS SUCCESS.** The concurrency group keys on `github.ref`, which
for a `pull_request` event is the same for every push to that PR -- so a
follow-up commit cancels the run on the previous one exactly as it does on
master. Measured on PR #36: a docsweep pushed while the first run was in
flight cancelled it, and the step list is the familiar shape --

    cancelled  Run the test suite
    skipped    Naming benchmark (must stay 181/181)
    skipped    Regulatory benchmark
    skipped    Validate regulatory rulesets

-- while **`gh run watch --exit-status` on that same run exited 0**. The
exit code is not an oracle for "the gates ran": it reports the WATCH
succeeding, and a cancelled run is a watch that finished normally. Read the
step list. This is the same lesson as `grep FAILED` on a crashed suite log,
one layer out: an absence of failure is not the presence of a result.

### `QT_QPA_PLATFORM` IS NOT A WebGL CHECK, and that is what reddened it

Four viewer tests failed on CI for environmental reasons, and the gate
meant to cover exactly that could not see it, because it asked about the
Qt PLATFORM instead of the capability:

    QT_QPA_PLATFORM=offscreen, machine with a GPU   2 contexts (ANGLE/D3D11)
    QT_QPA_PLATFORM=windows,   machine with a GPU   2 contexts
    GPU-less CI runner                              0, "getContext returned null"

So the name and the capability disagree in BOTH directions: `offscreen`
locally has WebGL and the tests really do run there, while CI has none
and 3Dmol's `viewer` is never defined -- which is why
`test_the_matrix_matches_where_atoms_are_actually_drawn` failed in its
SETUP, and why `test_a_gallery_that_cannot_be_built_is_reported` reported
"the gallery failed silently" when the reporting was fine and nothing had
got far enough to be reported.

The `webgl` fixture in `tests/conftest.py` MEASURES it, from a bare
canvas rather than from the app's own viewer page -- so the gate
establishes the PREREQUISITE is absent and never that our code failed to
use it. If WebGL works and 3Dmol still cannot build a viewer, the test
runs and fails.

**An inconclusive probe RAISES rather than reporting zero**, and that is
load-bearing: "I could not find out" is not "the prerequisite is absent".
It caught its own bug immediately -- the probe page was missing its
closing `</script>`, so `runJavaScript` returned `''` (primitives only,
as this file already records) and a blanket `except: return 0` would have
skipped all four tests on every machine while looking like it worked.

`tests/test_webgl_gate.py` guards it, and the guard that matters most is
`test_a_measured_PRESENCE_does_not_skip` -- a capability gate is worth
what its ability to say NO is worth. Measured before and after on CI:

    before   4 failed, 4173 passed,  8 skipped   gates never ran
    after    0 failed, 4178 passed, 12 skipped   "Naming benchmark holds at 181/181"

The gallery tests still skip on a platform check -- and it was
investigated afterwards and DELIBERATELY KEPT. The ladder in the
conformer-gallery section shows every capability underneath working under
`offscreen` (twelve contexts, six viewers) while `createViewerGrid`
throws even for one cell, so the only thing predicting that failure is
the call under test. **A platform gate you can justify beats a capability
probe that cannot say no**, and this is the case that draws the line
between the two.

**IT IS ONE GATE NOW, AND IT CARRIES BOTH HALVES.** `grid_display` in
`tests/conftest.py` pairs that admitted platform check with
`webgl_skip_reason`'s MEASURED one. It had been written privately twice
-- `_needs_a_display` and `_NEEDS_A_DISPLAY`, in two files -- and the
gallery overlay would have made a third; both are gone and every site
takes the fixture. `test_no_test_file_derives_the_platform_gate_for_itself`
fails if a fourth appears, walking `skipif` CONDITIONS as an AST because
a text search flags the prose explaining the rule.

The measured half is what makes them safe to run anywhere: a GPU-less
machine has no context at all, so they skip naming the absent
prerequisite rather than failing and blaming the code. **That is what
lets CI run them.** `tests.yml` has a non-blocking
`Conformer gallery guards` step under `QT_QPA_PLATFORM=windows`, placed
AFTER the three gates so it cannot disable them, which makes their status
visible instead of assumed -- the same argument as the PubChem step.
Expected to skip on the hosted runner today; if that image ever gains a
GPU they start running for free. **`continue-on-error` means advisory,
not passing**: read that step, not the job's tick.

Locally, where there is a GPU, they really run:

```bash
QT_QPA_PLATFORM=windows uv run --no-sync python -u -m pytest -q -ra tests/test_spatial_annotations.py tests/test_mol3d_viewer_backend.py
```

One INVERSE use survives and is correct:
`test_a_gallery_that_cannot_be_built_is_reported` asserts the FAILURE
path, so `offscreen` is its prerequisite rather than its obstacle. It
asks the shared `conftest.grid_platform_is_offscreen()` -- which is why
that is a predicate and not a mark.

## A WINDOWS RUNNER HANDS A BASH SCRIPT TO POWERSHELL

GitHub's default shell for a `run:` step is **bash on Linux and `pwsh` on
Windows**. `benchmarks-selfhosted.yml` is `runs-on: [self-hosted, windows,
openchem-tools]` and its steps are written in bash, and until 2026-08-26
nothing in the repository declared a shell at all.

Measured on the runner machine rather than reasoned about:

    [ ! -d tdc_data ]     ParserError: Missing type name after '['
    <<ROWS heredoc        ParserError
    case / esac           ParserError

**A POWERSHELL PARSE ERROR KILLS THE WHOLE STEP** before its first line
runs. So the step fails having done nothing, and what a reader sees is a
red benchmark rather than a wrong shell.

**THE ONE BASH-ISM THAT SURVIVED IS THE DANGEROUS ONE.** The docking
step's `mkdir -p bench-out` shipped when docking was encoded and never
failed loudly, because **PowerShell resolves `-p` as a PREFIX of
`-Path`** -- partial parameter matching. So it parses, silently means
something else, and errors only on a re-run once the directory exists,
with Actions running pwsh under `$ErrorActionPreference = 'stop'`.

**WHY NOTHING CAUGHT IT FOR SO LONG.** `tests.yml`'s Windows job is green
and declares no shell either -- because every one of its steps is a
single plain command (`uv sync ...`, `uv run ...`) that runs identically
in any shell. The default is harmless right up until a step grows a pipe,
a test bracket or a heredoc, and that happened first in the file no PR
ever runs.

The cure is one job-level `defaults: run: shell: bash`; both shells are
present on the runner. `test_a_windows_job_running_bash_declares_that_it_is_bash`
is the guard.

**IT IS TEXTUAL, NOT A YAML PARSE**, for the reason `test_workflow_safety.py`
already records: `pyyaml` is not a dependency of this project.

**AND IT IS SPLIT PER JOB, WHICH ITS FIRST RUN IS THE ARGUMENT FOR.**
Checked over the whole FILE it failed on `tests.yml`, which has a
windows-latest job and an ubuntu-latest one -- and the bash lives in the
LINUX job's fingerprint. A whole-file scan cannot attribute a step to a
job, so it read the two as one Windows job full of bash and demanded a
declaration on a file that does not need one. A guard whose first finding
is a false positive is a guard that would have been deleted.

### THE HAND-RUN RULE DOES NOT COVER THE SHELL

This is worth stating on its own, because the workflow's own comment says
a benchmark is encoded only after "running its pipeline by hand on the
runner machine first, then encoding exactly what worked" -- and that rule
was followed for docking and for all three of the last batch. It still
missed this.

A hand-run happens in whatever shell the person is using. Encoding it
into YAML changes the interpreter, and nothing about the transcription
looks different. **"Exactly what worked" is a claim about the COMMAND and
not about the thing that runs it.**

## A FORMULATION IS NOT A MOLECULE, AND THE COMPONENTS ARE EACH REFUSED

`domain/formulation.py` is the recipe as a project DOCUMENT and the
formulations half of `chem/energetics.py` is the arithmetic. **NO NEW
DETONATION EQUATION IS INTRODUCED** -- `arbitrary_gas`,
`heat_of_detonation` and `detonation_from_parameters` are pure functions
over element counts, and they accept the FRACTIONAL counts a mixture
produces. What is new is the abstraction, not any chemistry.

**THE FEATURE EXISTS BECAUSE THE SINGLE-SUBSTANCE PATH STRUCTURALLY
CANNOT ANSWER FOR ITS OWN INGREDIENTS.** Measured through the shipped
calculator:

    TNT                  answered
    RDX                  answered
    ammonium nitrate     REFUSED  over-oxidised: needs 2 <= O <= 2, has 3
    nitroglycerin        REFUSED  over-oxidised: needs 2.5 <= O <= 8.5, has 9
    dodecane (fuel oil)  REFUSED  too little oxygen to form water

...and the MIXTURE lands inside. ANFO at 94.5/5.5 composites to
`C0.3195 H4.5857 N1.9468 O2.9201` against a window of 2.2928 to 2.9317.
Two refusals in, one answer out.

### THE AUTHORS EVALUATED THE METHOD ON MIXTURES THEMSELVES

Applying Kamlet-Jacobs to a recipe reads like a liberty taken with a
single-substance correlation, and it is not. Read directly off p45 of
[source:kamlet1968_iii], its Table I's 80 data sets cover "13 explosive
compounds and 14 binary mixtures of three general types", and the same
paragraph says those calculations' parameters "were estimated from the
H2O-CO2 arbitrary according to Eqs. (13)-(15) of Ref. 1" -- the identical
arbitrary `arbitrary_gas` implements. RDX/TNT mixtures are named on that
page. [source:kamlet1968_iv] is the matching evaluation for the VELOCITY,
which this reports beside the pressure.

**BOTH ARE `citation`, NOT `citation_and_claim`**, and the distinction is
the one this file already draws: they establish the method is STATED for
mixtures, never that a number here is right. Table I's measured pressures
have NOT been transcribed -- its text layer is OCR-damaged ("4S" for 45,
"1. 632k" for 1.632k), so it needs the render-at-magnification treatment,
which is three-for-three on finding a one-digit error in this project.

### MASS IN, MOLES FOR THE FORMULA, AND THE ERROR IS SILENT

A recipe is stated the way it is mixed, by MASS; `CaHbNcOd` is per MOLE.
Treating the stated mass fractions as mole fractions is wrong by a few
percent per element, and measured on ANFO:

    mass -> mole (correct)   C0.3195 H4.5857 N1.9468 O2.9201   INSIDE
    mass AS mole (wrong)     C0.6600 H5.2100 N1.8900 O2.8350   INSIDE

**BOTH LAND INSIDE THE ARBITRARY AND BOTH GIVE AN ORDINARY PRESSURE**, so
no domain check separates them. That is why the composite formula is a
REPORTED FACT rather than an internal: it is the one number a reader can
check the arithmetic against.

### THE MUTATION PASS FOUND AN UNGUARDED WEIGHTING, as it usually does

Five arms. Four caught, and the survivor is the entry worth reading:

    M1  mole conversion -> mass-as-mole      4 tests
    M2  drop a component's dHf               **SURVIVED**
    M3  loading density falls back to a
        weighted average of the components   1 test, the intended one
    M4  fractions silently normalised        2 tests
    M5  mean molar mass as a MASS-weighted
        average of M_i                       1 test, the intended one

**M2 MOVED COMPOSITION B'S COMPOSITE ENTHALPY FROM 2.58 TO 8.90 kcal/mol
-- A FACTOR OF THREE -- AND NOTHING NOTICED.** dHf enters Q divided by the
mean molar mass, so 6.3 kcal/mol over ~224 g/mol is about 2% on Q, ~1% on
P and ~0.5% on D, which fits comfortably under the published-formulation
tolerances of rel=0.08 and rel=0.04. That is the loose-oracle trade seen
from the other side: **an oracle slack enough to tolerate an unsourced
reference value is slack enough to tolerate a real arithmetic fault.**
`test_the_composite_enthalpy_is_mole_weighted_over_EVERY_component`
asserts the weighting directly, written from the surviving arm and
confirmed to fail against it.

**AND M3'S MUTANT RETURNED 254 kbar / 7.78 mm/us FOR COMPOSITION B**
against a real ~295 / 7.89. The docstring's claim that deriving the
loading density is "a large error wearing a plausible number" is measured
rather than asserted -- nothing about that output looks wrong.

#### TWO OF THE THREE PUBLISHED FORMULATIONS ARE DEGENERATE

The sharpest finding, and it is about the FIXTURE rather than the code.
Under M1, `test_published_formulations_are_reproduced` fails on Pentolite
and **passes on Composition B AND Cyclotol** -- because RDX (222.12) and
TNT (227.13) are 2.3% apart in molar mass, so for any RDX/TNT recipe the
mass fractions and the mole fractions nearly coincide and the bug barely
moves the answer. PETN (316.14) against TNT is 39% apart.

So two of the three rows cannot see the one defect the file exists to
catch, while the parametrisation reads as three-way coverage. Do not drop
the PETN row. Same lesson as the assembly corpus blind to a transposed
matrix: **a fixture is not big or small, it is degenerate or not with
respect to a specific mutation.**

**THE ORACLE'S PROVENANCE IS THE WEAKEST THING IN THAT FILE AND SAYS SO.**
Those three velocities and pressures are widely published and NOTHING
CITES THEM; they were not read out of either paper. Recorded rather than
quietly relied on, with the tolerances left loose to match what is really
known -- tightening them without sourcing the values would assert more
than anybody here has checked.

### The loading density is supplied or the estimate is refused

`rho0` is the MEASURED bulk density of the charge. A mass-weighted average
of the components' crystal densities is arithmetically reasonable and
wrong: a packed charge is nowhere near its ingredients' crystals, and P
goes as the SQUARE. There is no source-backed route from a recipe to it,
so `test_the_loading_density_is_required_and_never_derived` holds the line
and M3 is what proves that guard is the only thing holding it.

Stated fractions are checked rather than normalised, for the reason
`CrystalModel` stores what was typed: 94.5 + 5.0 renormalises to a
perfectly ordinary recipe that is not the one anybody meant.

### ONE TOLERANCE, TWO CHECKERS, AND IT WAS NEARLY TWO LITERALS

The same claim -- how far a recipe's fractions may sum from 1 -- is
checked on the document and in the compositing, and it first shipped as
two separate `1e-3` literals. `chem/energetics.py` already imports from
`domain/` three times, so it imports the constant now;
`test_the_two_sides_check_the_same_tolerance_because_it_is_one_constant`
asserts IDENTITY rather than equality, because a copied literal compares
equal. It is the CONSTANT that is imported and not the component TYPE,
which `composite_formula` still takes structurally.

**AND THE CONSTANT HAD LANDED INSIDE ANOTHER ONE'S DOC COMMENT**, between
`ENTHALPY_NOT_SUPPLIED`'s `#:` block and `ENTHALPY_NOT_SUPPLIED` itself --
so the sentence "CHNO explosives run roughly -200 to +200 kcal/mol, so
this is outside anything real by a wide margin" was documenting a
tolerance of 1e-3, and the sentinel it was written for had no
documentation at all. Nothing catches that; it needs a reader.

### AND THE WHOLE THING WAS REACHABLE FROM NOTHING A USER COULD PRESS

`build_formulation_report` shipped correct, sourced, and covered by 24
tests. **No menu item, panel or registration invoked it.** The only
caller in the repository was its own test file.

**AND `tests/test_calculator_reachability.py` WAS GREEN THROUGHOUT**,
which is the part worth reading. That file exists precisely because PR
#41 shipped four unreachable modules, and it checks three directions --
forward from the registry, reverse from `USER_FACING_PROVIDER`, and wide
from `openchem.main`. All three passed, because **every one of them is
about the MODULE**:

    chem/energetics.py is statically reachable from openchem.main   yes
    it declares USER_FACING_PROVIDER                                yes
    ...naming "Oxygen balance, through the 'Oxygen Balance'
       calculator", which is TRUE                                  yes

So the module's own declaration was satisfied by a DIFFERENT function in
the same file, and the report sat beside it reached by nothing. PR #41's
failure at finer granularity: **"shipped" had come to mean *the file
exists and something else in it is wired up*.**

#### The rule that closes it is a real family, and it was measured first

`test_every_report_builder_is_called_by_the_application` derives its
population from the naming convention every one of them already follows,
so a seventh is checked without anybody remembering to add it. Measured
BEFORE the rule was written -- six builders, five with a real call site
in `src/` and exactly one with none:

    build_atom_report         ui/panels/atom_inspector_panel.py:517
    build_bond_report         ui/panels/atom_inspector_panel.py:511
    build_molecule_report     ui/panels/atom_inspector_panel.py:513
    build_crystal_report      app/main_window.py:2113
    build_site_report         app/main_window.py:2249
    build_formulation_report  NOTHING

**IT COUNTS `ast.Call`, NEVER TEXT, AND THAT DECIDES THE ANSWER.** Five
of the six are also named in PROSE -- `services/atom_fact_service.py`
names three in one docstring sentence, and `chem/energetics.py` mentions
`build_crystal_report` in two comments explaining a convention it
borrows. A `grep -c` rule counts those and passes, which is this file's
own *"grepping for a phrase counts the source, not the outcome"* lesson
one layer down.

**WHAT IT DOES NOT CLAIM** is that the call site is reachable from
`openchem.main`; the wide direction says that, and the two compose.

Two mutations, two caught, and the first is the demonstration: removing
the production call fails this guard **while the other 87 tests in the
file stay green**, which is the blind spot shown rather than described.
Neutering the population regex fails both halves.

### THE ANSWER SHIPPED BEHIND A FOLD, AND EVERY TEST WAS GREEN

Found by driving the app and reading the shot, which is now the
thirteenth entry in this file's running count of that. The report opened
on a name, a component list, and a collapsed **"Structure (4)"** --
`DEFAULT_EXPANDED` holds IDENTITY and ELECTRONIC, and the composite
formula, the pressure, the velocity and the heat of detonation are all
STRUCTURE. **The entire answer was one click away and invisible.**

`FactView._compact`'s own docstring already records this defect, in the
same heading and at the same count, for the solubility stats block -- and
its fix does not cover this: `_compact` fires when the CONTROLS are
hidden, and here they are shown. `set_report` takes an `expanded`
override now, defaulting to None so every existing caller is unmoved.
`DEFAULT_EXPANDED` exists because *"a hundred-odd facts rendered flat is
a wall"*; a six-fact report is not one.

**NOTHING IN THE SUITE ASSERTED A SECTION'S INITIAL STATE**, which is why
it shipped. The guard reads `isChecked()` rather than counting rows: the
facts were always PRESENT, and present is not visible.

**AND THE HELPER GUARD DOES NOT CATCH IT** -- mutating the override out
of `_formulation_report_dialog` leaves both `FactView` guards green and
fails only
`test_the_windows_own_report_dialog_opens_with_the_answer_visible`.
*Testing a helper is not testing the wiring*, for the third time in this
file.

### `Fact.units` NEVER REACHES A FactView ROW, and that is PRE-EXISTING

Recorded rather than fixed, because it is system-wide and not this
branch's. The detonation facts carry `units="kbar"`, `"mm/us"`,
`"cal/g"`; the row renders `display_value` alone and the row TOOLTIP
carries source, basis, evidence and limitations -- not units. So the
report reads `Detonation pressure (C-J)  70.7`.

**It is not a dead field**, which is the thing to check before calling it
one: `ui/report_format.py`, `ui/result_clipboard.py` and
`comparison_panel` all read it, so *Copy report* carries the units the
screen does not. And `chem/crystal_report.py` has the identical shape --
`units="A^3"`, `"g/cm^3"`, `"kJ/mol"`, none of them rendered -- so every
Fact-based report in the application reads this way and has since the
migration. Changing it touches all of them and wants its own measurement,
its own guard and its own driven check.

## A POWDER PATTERN'S POSITIONS SHIP AND ITS INTENSITIES ARE REFUSED

`chem/powder_xrd.py` reports where a calculated powder X-ray pattern's
peaks fall -- (hkl), d, 2theta, multiplicity -- and **no peak heights at
all.** The plan for this branch asked for both halves and named a
three-layer source chain for the second; the split is the plan's own
("different evidence requirements"), and the refusal is a MEASUREMENT
rather than an estimate of effort.

**POSITIONS ARE CHECKABLE BY ARITHMETIC A READER CAN REDO.** For a cubic
cell the general expression must reduce to the closed form, and halite
comes out where a textbook prints it:

    111  d 3.2564  2theta 27.37      200  d 2.8201  31.70
    220  d 1.9941  45.45             311  d 1.7006  53.87

**THE PLAN'S OWN ACCEPTANCE VALUE IS WRONG, and this is the second branch
running where a plan premise did not survive measurement.** It quotes
d(111) = 3.258 for a = 5.64; the arithmetic gives **3.2563**, and 3.258
would need a = 5.6431. Its 200 and 220 are right. Recompute a plan's
numbers before encoding them.

### The intensity refusal, measured

    numeric tokens on Waasmaier & Kirfel Table 1 (4 pages)   2267
    visibly corrupted                                         673   29.7%

...and 70.3% "clean" is an UPPER BOUND on correctness, because a token
can be well formed and still wrong. Element labels are corrupted too --
the **calcium** row extracts as `Cs`, which would silently put caesium's
scattering factors on calcium.

**THE DECIDING POINT IS THAT ONLY 6 OF THE 11 PARAMETERS HAVE AN
ORACLE.** A neutral atom's scattering factor at zero angle is its
electron count, so `sum(a_i) + c = Z` checks `a1..a5` and `c` per row.
The five `b` values have NONE: a wrong `b` is wrong at every non-zero
angle and exactly right at theta = 0, which is the one place the
checksum looks. A table where nearly a third of the numbers are visibly
damaged and 5 in 11 are unverifiable produces plausible intensities of
unknown correctness.

**AND THE PDF LIBRARY INDEXER AGREED BY A DIFFERENT ROUTE.** Branch F's
`tools/index_pdf_library.py --check` reports `brown2006` as
`unresolved` -- it finds no identity evidence inside the file at all --
which is the same conclusion about that scan's text layer, reached
without looking at a single number. That makes four unresolved scans
rather than three.

### THREE SOURCES REGISTERED, ALL `assessed_not_shipped`

    waasmaier1995   the parameters, refused with the measurement above
    brown2006       ITC Vol C 6.1.1, the intensity formalism
    coppens2006     ITC Vol B 1.2, the structure factor

**`coppens2006` IS DELIBERATELY NOT CITED AS BACKING THE ABSENCE RULE**,
which this project DOES ship. Searching that chapter finds no occurrence
of "systematic", "absence" or "extinction condition" -- reflection
conditions are Vol. A material. Citing it would be this file's own "a
citation-level entry does not authorize an implementation merely because
its title matches" trap.

**NONE OF THE THREE PRINTS A DOI**, so none is recorded. All three
citations were read off the papers' own header lines -- and
`waasmaier1995`'s page 1 opens with the TAIL OF THE PRECEDING ARTICLE's
references, which is this file's "a PDF's first page is not necessarily
its paper" trap, hit again. `brown2006`'s text layer is unusable, so its
citation, section number and five-author list were read from a **350 dpi
render**.

### THE ABSENCE RULE IS DERIVED, NEVER TABULATED

    if h.R == h  and  h.t is not an integer   ->   F(hkl) = 0

One statement over the space group's own operations reproduces every
centring and glide/screw condition a textbook lists separately --
verified against the F-centring parity rule on all eight cases. A
hand-kept table of conditions per space group would be the
`inapplicable_calculators` rot waiting to happen, 230 rows deep.

### THREE MUTATIONS, THREE CAUGHT, AND TWO SAY SOMETHING

    M1  absences disabled                    7 tests
    M2  the Friedel pair dropped             ONE test -- the P1 one
    M3  diagonal-only tensor inverse         ONE test -- the triclinic one

**M2 AND M3 ARE BOTH BLIND TO THE OBVIOUS FIXTURE.** Fm-3m is
centrosymmetric, so the Friedel pair is already in its orbit and every
cubic multiplicity test passes with the term deleted; only a P1 cell,
which has ONE operation, can show that the pairing comes from anywhere
else. And a diagonal-only inverse is EXACTLY RIGHT for an orthogonal
cell, so the whole cubic acceptance case cannot tell it from the real
one -- which is `Lattice.volume`'s own recorded lesson ("a cubic-only
check cannot tell this formula from a bare multiplication") arriving one
property along.

### WHAT DRIVING THE APP FOUND, AND WHAT IT DID NOT

**The pattern was computed and invisible.** Marked `Detail.ADVANCED`
throughout, the whole thing vanished behind "16 advanced hidden" and
nothing on screen said a powder pattern existed. The summary row is
`STANDARD` now and the individual lines stay `ADVANCED` -- the split the
regulatory report already makes, where ruleset versions are advanced so
they do not bury the findings.

**The report's sections are still collapsed, and that is PRE-EXISTING.**
`Structure` and `Geometry` are not in `DEFAULT_EXPANDED`, so the cell
volume and the density have always opened behind the same fold. Not
touched here, because the `expanded` override that fixes it lives on an
unmerged branch and duplicating it would be a merge conflict.

**AND THE CRYSTAL REPORT WAS ALREADY SLOW.** Measured with the powder
facts stubbed out, before blaming the new code:

    fixture      report WITHOUT powder     pattern alone
    1502211              10.63 s               1.17 s
    1004002               3.61 s               0.70 s
    1504676               0.07 s               0.17 s

So the pattern is 10-30% of a report that already takes ten seconds on
its worst fixture. Recorded rather than fixed; the cost is in the
coordination shells.

### HOISTING THE METRIC TENSOR IS 4-10x, AND THE GUESS WAS WRONG FIRST

`Lattice.d_spacing` inverts the metric tensor on every call, which is
right for a readable one-reflection API and ruinous inside an enumeration
reaching ~226000 index triples for a 15 A cell. Measured over the six CIF
fixtures at 60 degrees, hoisting it out of the loop took the range from
**1.9-3.9 s to 0.02-0.91 s** with every pattern unchanged.

Reordering the cheap d-test ahead of the 192-operation orbit was tried
FIRST, on the reasoning that the orbit was the expensive part, and bought
almost nothing -- one fixture got SLOWER. The inversion was the cost.
Profile before optimising, even when the expensive-looking thing is
obvious.

### A GUARD READ MY OWN COMMENT AS A DECLARATION

`chem/powder_xrd.py` declares no `USER_FACING_PROVIDER` -- it reaches the
user through the crystal report rather than through a registered
calculator, exactly as `chem/crystal_report.py` does -- and the module
says so at its head. **That explanation put it in the guard's
population**, because `_declared_providers()` finds candidates with
`if _MARKER not in text`, a TEXT scan. The module then failed two guards
for a declaration nobody had made.

The text scan is kept as a PREFILTER -- it is what lets an unimportable
module fail there rather than as a collection error elsewhere -- and
`hasattr` is the answer. **`hasattr`, not truthiness**:
`USER_FACING_PROVIDER = ""` IS a declaration and a useless one, and it
must keep failing `test_every_declaration_names_the_surface_it_reaches`
rather than vanishing from the population. Both halves are guarded.

Same family as this file's `grep FAILED`, `INFRASTRUCTURE FAILURE` and
`Fatal Python error|Windows` entries: **grepping for a phrase counts the
source, not the outcome** -- this time counting a comment that existed
only to explain why the thing it names is absent.

## A DECISION WAS REVERSED ON PRODUCT GROUNDS, AND THE RECORD SAYS SO

`docs/ARCHITECTURE.md` carried a subatomic-particle editor as a
**DECISION** against building it: nothing in this application consumes a
particle, every layer below the UI is built on atoms as the smallest
unit, and the stated expiry was "the day something downstream can read a
baryon".

**THAT DAY HAS NOT COME AND THIS DOES NOT BRING IT.** `domain/particle.py`
reaches no molecule, no property and no report. The entry is SETTLED now
and says outright that the condition was not met and the thing was built
because it was wanted -- because a DECISION marker that can be retired by
doing the thing anyway records nothing for the next reader. The original
reasoning was not refuted; it was outweighed.

**THE GUARD FIRED EXACTLY AS ITS OWN COMMENT PREDICTED.** The deferral's
predicate was `"quark" not in _src_text().lower()`, with a comment saying
"it fails the day somebody adds one, which is the point". It does:
measured after the module landed, that expression is now `False`. The
entry is removed with a note recording that it went stale in the
direction this table is least able to argue with -- somebody built the
thing.

### What the reversal buys is a boundary, not an apology

Four guards in `tests/test_particle.py`, and the last two are the
load-bearing ones:

    domain/particle.py imports nothing from openchem.chem
    no ProjectModel field mentions a particle
    ParticleState has NO to_dict/from_dict/uuid/molblock/smiles
    nothing under chem/ imports domain.particle

The third is the narrow half: "no field on `ProjectModel`" is satisfied
by smuggling a particle into `metadata`, or by giving the type a
`to_dict` a project writer would happily call. Asserting the type carries
no serialisation at all is what leaves nothing to call.

## GELL-MANN--NISHIJIMA IS THE CHECKSUM ON A HAND-ENTERED TABLE

    Q = I3 + (B + S + C + B' + T) / 2

It holds per quark and both sides are additive, so it holds for any
composition BY CONSTRUCTION -- which makes it useless as a test of the
composition logic and exactly right as a test of the six-row flavour
table this module types by hand. A wrong sign or a mistyped third in any
flavour breaks it.

**THE SIGNS IT PROTECTS ARE THE CLASSIC TRAPS**, and they came from the
PDG's own section headers rather than from memory:

    Lambda BARYONS (S = -1, I = 0)    above   Lambda0 = uds
    Xi BARYONS     (S = -2, I = 1/2)  above   Xi0 = uss, Xi- = dss
    Omega BARYONS  (S = -3, I = 0)    above   Omega- = sss

...which is the strange quark carrying **S = -1**. The negatively-charged
quarks carry NEGATIVE flavour numbers -- s has S = -1 and b has B' = -1,
while c has C = +1 and t has T = +1.

**`Fraction`, NEVER FLOAT.** A proton is 2/3 + 2/3 - 1/3, which in binary
floating point is 0.9999999999999999 -- so an equality test against +1
fails, and a tolerance would be a tolerance on a number that is exactly
an integer.

## THE PDG SUPPLIES ITS OWN COUNTEREXAMPLE, WHICH IS THE WHOLE DESIGN

Lambda and Sigma zero have the SAME quark content:

    Lambda BARYONS (S = -1, I = 0)   Lambda0 = uds    1115.683 MeV
    Sigma BARYONS  (S = -1, I = 1)   Sigma0  = uds    1192.642 MeV

Identical charge, baryon number, strangeness AND third isospin component.
They differ in **TOTAL isospin, which is not a sum over quark content the
way I3 is** -- so the derived numbers PROVABLY cannot tell them apart.

That is why the verdict is three-valued rather than known/not-known:

    invalid                not a baryon or a meson
    valid, not identified  the arithmetic works, no unique named state
    identified             exactly one PDG row has this content

Forcing two states would have to lie about `uds`. The editor names both
candidates and picks neither.

**AND THE LOOKUP IS BY CONTENT, NEVER BY QUANTUM-NUMBER TUPLE.** Searching
the table for a row whose (Q, B, S) happens to match is how "known
particle" quietly becomes "whatever came back". Asserted on the SOURCE --
an AST check that `identify` calls `_same_content` -- because the shipped
table contains no pair whose numbers coincide while their contents
differ, so no composition discriminates the two implementations end to
end. Same rule as "an unreachable branch is a question about where to
assert".

## A NEUTRAL LIGHT MESON IS A SUPERPOSITION, AND THE SOURCE PRINTS IT

The light-unflavoured meson section is headed

    for I = 1 (pi, b, rho, a):  ud, (uu-dd)/sqrt(2), du
    for I = 0 (eta, eta', ...): c1(uu + dd) + c2(ss)

so pi0 is not a quark-antiquark PAIR at all and the I = 0 states carry
mixing coefficients the table does not fix. A bare `u ubar` therefore
composes to a valid meson this editor refuses to name -- **that refusal is
the PDG's own position rather than a limitation of the arithmetic**, which
is a materially different thing to tell a reader.

## THE PDG WAS FETCHED, READ AS A PDF, AND CROSS-CHECKED

No copy in `Sci Downloads`. The summary tables are free, so they were
fetched -- and `WebFetch` cannot read a PDF, but it SAVES one, which is
the useful part: the file was then read with pymupdf exactly like every
other source here. Every page carries
`Citation: S. Navas et al. (Particle Data Group), Phys. Rev. D 110,
030001 (2024)` verbatim, which is where the registry entry comes from.

**EVERY MEASURED VALUE AGREED WITH AN INDEPENDENT EXPECTATION BEFORE IT
WAS WRITTEN DOWN** -- proton 938.27208816 MeV, neutron 939.5654205 MeV
and 878.4 s, Lambda 1115.683, Sigma+ 1189.37, Sigma0 1192.642, Sigma-
1197.449, Xi0 1314.86, Xi- 1321.71, Omega- 1672.45, pi+ 139.57039, K+
493.677. The source supplies the value; the expectation only screens for
a transcription failure. Two routes agreeing is what makes a hand-typed
number checkable, and it is the pattern the Waasmaier radius inversion
already used.

**A LIMIT IS NOT A MEASUREMENT.** `mean_life_s` is None for the proton and
the note says the PDG prints `> 9 x 10^29 years (CL 90%)`. Storing that
figure as a lifetime would turn "nobody has ever seen one decay" into "it
decays", which is the same shape as this file's `n/a is not 0` finding.

## THE DIALOG OPENED ON A DELTA++ AND EVERY TEST PASSED

Found by driving the app and reading the shot -- the fourteenth entry in
this file's running count of that, and the mechanism is new.

**`QComboBox.findData` CANNOT MATCH A PYTHON TUPLE, AND FAILS SILENTLY.**
The items carry `(Flavour, bool)` as their data; `findData` compares
through `QVariant`, returns -1, and `_select` left every box at index 0.
So `_reset_to_proton` believed it had set `u u d` and the editor opened
on `u u u`.

**NOTHING NOTICED BECAUSE `content()` READS `currentData()`** -- it was
perfectly correct about the wrong selection, so all 56 tests passed
against a dialog showing the wrong particle. The verdict on screen was
even right FOR what was displayed: "a valid baryon, not identified" is
the correct answer for a Delta++, which this table does not carry.

Comparing in Python is the fix, and the lookup now RAISES on a miss
rather than returning quietly: the whole reason the bug was invisible was
a silent -1. Both halves are guarded, and the regression test asserts the
CONTENT the dialog opens with rather than combo indices, so it survives
the picker being reordered.

## A DRIVE STEP THAT DRIVES THE CONTROLS, NOT THE FUNCTION BEHIND THEM

`{"do": "particle", "content": "u d s"}` sets the combo boxes and reads
the rendered verdict. Calling `identify` in the step would photograph an
answer the dialog never produced -- and the defect above was precisely a
broken selection sitting behind correct arithmetic, so a step that
bypassed the boxes could not have caught it. Same argument
`jobs_cancel` makes by pressing the real button.

## Running the tests

```bash
uv run --no-sync python -u -m pytest -q > /tmp/suite.log 2>&1; tail -5 /tmp/suite.log
```

Writing to a file rather than a pipe is worth doing because it lets you watch
progress while it runs.

A clean run is **6-21 minutes**, ending at `6230 passed, 16 skipped`
(measured 2026-08-27, **14m49**, on `powder-xrd` AT ITS MERGE OF MASTER --
a calculated powder pattern's POSITIONS with its intensities refused, on
top of the formulation work that landed as #53.

**MEASURED ON THE MERGE, which is what the entry below it could not be.**
That one is `energetic-formulations` and this one was `powder-xrd`, and
the two are SIBLINGS off master rather than one being an ancestor of the
other -- so **adding 6173 and 6184 is meaningless**, they share master's
tests. Only collecting the merged tree answers it.

**+57 collected and 0 REMOVED** against master at the merge:

    master     7a227be   COLLECTS 6189      <- #53 already in
    this one             COLLECTS 6246      = 6189 + 57
    the run                       6230 passed + 16 skipped = 6246

    52  test_powder_xrd.py               written
     2  test_calculator_reachability.py  the text-scan prefilter, both arms
     3  test_sources_are_current.py      parametrised cases of the EXISTING
                                         schema guard, one per new source

**THE SKIPS ARE 16 AND THE COMPOSITION IS UNCHANGED** -- 13
`createViewerGrid` under offscreen (7 spatial + 6 mol3d), the network
test, `test_namer_known_defects.py:471`'s empty parametrisation, and
`test_pdf_library_index.py:274` from #51. Chromium's `Failed to make
current` fires **41 times** in this log -- the highest count yet recorded
here, against 28, 18, 12 and 5 -- and costs **zero** skips, which is the
fifth independent confirmation that the GPU is not what moved that figure.

**The crash pair is satisfied**: there IS a summary line, and
`Windows fatal exception|Fatal Python error` matches **0**, as do
`^FAILED` and `^ERROR`. The two `DeprecationWarning`s are the same
pre-existing six-argument `QMouseEvent` overload in
`test_dock_title_bar.py` and `test_trajectory_player.py`.

**AND THE MARKER GREP MUST NOT BE ANCHORED, which cost a wrong verdict on
the first run of this figure.** `^(Windows fatal exception|...)` reported
**0 markers on a run that had plainly crashed**, because pytest's
progress dots share the line:

    .......Windows fatal exception: access violation

This file's own recipe is unanchored for exactly that reason. Tightening
it looks more careful and is strictly worse -- it is the crash-pair check
reporting clean on a crashed run, which is the one thing it exists to
prevent. The FAILED/ERROR greps stay anchored; those really do start
their line.

**THIS FIGURE IS THE THIRD RUN, AND THE FIRST TWO WERE THROWN AWAY.**
Recorded because a reader comparing numbers deserves to know:

    run 1   CRASHED at 84%, access violation, 790s, no summary line
    run 2   CLEAN but 6h11m -- 24x the norm -- with ONE failure
    run 3   6230 passed, 16 skipped, 14m49          <- the cited figure

Run 1 died in `tests/test_screening_service.py:120 in _drain`, which is
**the same file, line and function this file already records** one branch
ago at 83%. `_drain` is `waitForDone` + `processEvents()` in a
60-iteration loop -- the canonical victim position. The file is untouched
by this merge (nothing in the diff matches `screen|dock`) and passes 15 of
15 in isolation.

Run 2's single failure was a Ketcher page-load timeout in
`test_electron_overlay_lifecycle.py`, which passes 8 of 8 in isolation in
42 s. **A 24x wall clock is the finding, not the failure**: its counts
still reconcile exactly (6229 + 1 + 16 = 6246), so nothing was lost, and
the most likely cause is the machine SLEEPING mid-run -- a QtWebEngine
page load spanning a suspend times out exactly that way. Discarded rather
than diagnosed, which is this file's standing rule for a contaminated run;
the machine measured 0% load and zero stray `QtWebEngineProcess` handles
immediately afterwards, so there was nothing left to diagnose.

14m49 sits mid-band; the 6-21 range stands.)

Before it: `6173 passed, 16 skipped`
(measured 2026-08-27, **15m12**, on `energetic-formulations` -- the
formulation report reaching a control a user can press, and the
reachability guard's module-level blind spot.

**+19 collected and 0 REMOVED**, diffed both directions in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed -- `import openchem; print(openchem.__file__)` reported the
WORKTREE's `src`:

    08cb4d5              COLLECTS 6170
    this one             COLLECTS 6189   = 6170 + 19
    the run                       6173 passed + 16 skipped = 6189

**19 ITEMS, 19 NEW FUNCTIONS**, none parametrised, so for once the two
deltas are the same number:

    16  test_formulation_wiring.py       the dialog, the two commands,
                                         the events, and the fold
     3  test_calculator_reachability.py  the report-builder guard, its
                                         narrow half, and the
                                         docstring-is-not-a-call arm

**THE SKIPS ARE 16 AND THE 16th IS NOW ATTRIBUTED**, which the entry
this replaces recorded as unexplained between two candidates. It is
neither mysterious nor the GPU: **`tests/test_pdf_library_index.py:274`,
added by #51**, so master moved. Read off `-rs` rather than inferred:

    13  $3Dmol.createViewerGrid under offscreen   6 mol3d + 7 spatial
     1  test_naming_providers.py:297              hits the network
     1  test_namer_known_defects.py:471           an EMPTY PARAMETER SET
     1  test_pdf_library_index.py:274             NEW, from #51

**AND THE GPU CANDIDATE IS REFUTED RATHER THAN MERELY UNCHOSEN.**
Chromium's `Failed to make current` fires **28 times** in this very log
and costs **zero** skips -- so 15 was never "15 unless the GPU wobbles",
and the previous entry's suspicion was wrong in a checkable way.

**THE EMPTY-PARAMETER-SET SKIP IS WHY NO GREP FOUND IT.** A subset run
over every file matching `skipif|pytest.skip|importorskip|mark.skip`
gives 15, not 16, because `test_namer_known_defects.py` carries no skip
MARKER at all -- pytest reports an empty parametrisation as a skip. Any
future attempt to enumerate the skip-capable files by text will miss it
the same way; `-rs` on the full run is the only complete answer, and it
costs nothing when folded into a run you are taking anyway.

**The crash pair is satisfied**: there IS a summary line, and
`^(Windows fatal exception|Fatal Python error)` matches **0**, as do
`^FAILED` and `^ERROR`. The two `DeprecationWarning`s are the same
pre-existing six-argument `QMouseEvent` overload in
`test_dock_title_bar.py` and `test_trajectory_player.py`.

15m12 sits mid-band; the 6-21 range stands.)

Before it: `6087 passed, 15 skipped`
(measured 2026-08-26, **14m05**, on `sigma-pi-benchmarks-and-issue-8` --
the pi component, the last three self-hosted benchmarks, and the docking
half of issue #8's fix.

**+19 collected and 0 REMOVED**, diffed both directions in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed -- `import openchem; print(openchem.__file__)` reported the
WORKTREE's `src`:

    master     9ce6202   COLLECTS 6083
    this one             COLLECTS 6102   = 6083 + 19
    the run                       6087 passed + 15 skipped = 6102

**19 ITEMS, 14 NEW FUNCTIONS**, and the five-item gap is parametrisation
rather than anything written:

    12  test_electronic_properties.py   the pi component, and the tick
                                        box that does nothing for it
     2  test_docking_providers.py       the docking half of issue #8
     4  test_workflow_safety.py         ONE function over the three
                                        workflows, plus its setup guard
     1  test_sources_are_current.py     a parametrised case of the
                                        EXISTING data-table guard, for
                                        pi_orbital_electronegativity.json

**THE BENCHMARK WIRING ADDED ZERO, deliberately.** Its evidence is three
hand-runs on this machine, not a test -- the rule for that workflow is
that a step is encoded only after its pipeline has been run by hand, and
a unit test asserting a YAML string would be the decorative control that
rule exists to avoid. The four it DID earn are about the SHELL, which is
a property of the file rather than of a run.

**THIS FIGURE IS THE THIRD RUN, AND THE SECOND ONE CRASHED.** Recorded
because the class is documented here at length and a reader comparing
numbers deserves to know a run was thrown away:

    run 1   the 6097 tree    CLEAN, 6082 passed   -- and CONTAMINATED
    run 2   the 6102 tree    CRASHED at 83%, test 5083 of 6102
    run 3   the 6102 tree    CLEAN, 6087 passed   <- the cited figure

Run 2 died with `Windows fatal exception: access violation` in
`tests/test_screening_service.py:120 in _drain` -- **and pytest exited
0**, with no summary line, which is exactly the trap this file already
records. `_drain` is `waitForDone` + `processEvents()` in a 60-iteration
loop, i.e. the canonical victim position: the same pump shape as the
`_wait_until` that took the Linux segfault one branch ago.

**THE VICTIM FILE IS UNTOUCHED BY THAT BRANCH and passes 15 of 15 in
isolation**, and the five tests added between runs 1 and 2 are Qt-free --
RDKit, Open Babel and text scanning -- so none of them builds a widget.
The reading is the documented order-dependent class, where added tests
shift collection order and move the victim.

**THAT IS A READING AND NOT A FINDING.** Re-running the identical tree
is the discriminator this file uses, and it gives 1 crash and 1 clean on
that tree -- n=1 per arm, where the standing rule is that no A/B on this
crash class is worth much below about n=10. It is consistent with the
class and is not proof of it.

**RUN 1 WAS DISCARDED FOR A SECOND REASON WORTH KEEPING.** A probe fell
into an interactive Python REPL and spun for about two minutes while that
run was between 5% and 24% -- concurrent work against a run intended for
citation, which this file forbids. It came back clean anyway, and was
still superseded, because it also predated five tests.

**AND THE FIGURE WAS WRITTEN DOWN WRONG ONCE, WHICH IS THE POINT.** It
was first committed as `6082 passed, 15 skipped` / 6097 collected -- a
real measurement of run 1, taken BEFORE the shell guard's four items and
the tick-box test landed, so it was stale by 5 at the moment it was
written. The same drift this section records at 5, 10 and 11 items, made
again by somebody who had just read the warning. **Re-collect AFTER the
last test lands, and reconcile the run against it.**

**THE SKIPS ARE THE DETERMINISTIC 15** and run 3 has no crash markers --
`grep -cE "Windows fatal exception|Fatal Python error"` is 0 and there IS
a summary line, which is the pair this file insists on rather than an
absence of FAILED lines. The anchored progress-character count is 0 F/E,
and `^FAILED` and `^ERROR` are both 0. The two `DeprecationWarning`s are
the same pre-existing six-argument `QMouseEvent` overload in
`test_dock_title_bar.py` and `test_trajectory_player.py`.

14m05 sits mid-band; the 6-21 range stands.)

Before it: `6068 passed, 15 skipped`
(measured 2026-08-26, **15m06**, on `jobs-panel-leaks-and-polls-forever` --
the Linux segfault's cause, and the five files that shared one lambda.

**+11 collected and 0 REMOVED**, diffed both directions in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed -- `import openchem; print(openchem.__file__)` reported the
WORKTREE's `src`:

    master     a123fd2   COLLECTS 6072
    this one             COLLECTS 6083   = 6072 + 11
    the run                       6068 passed + 15 skipped = 6083

**THE BASELINE WAS DERIVED, NOT READ FROM THE ENTRY BELOW, and it was
stale by 4.** That entry records 6068 collected at `7b4652c`, while master
at `a123fd2` collects 6072 -- the docs-guard commit moved it. Reading the
entry would have reported +15.

**11 ITEMS BUT 8 NEW FUNCTIONS**, and the three-item gap is one
parametrisation rather than anything written:

     4  test_a_changed_job_list_does_rebuild   ONE function, over the four
                                               fields `_rendered_state`
                                               carries -- which is what
                                               makes dropping any one of
                                               them a failure
     1  test_an_unchanged_job_list_rebuilds_nothing
     1  test_a_freshly_built_panel_polls_without_waiting_for_a_show_event
     1  test_a_hidden_panel_stops_polling
     1  test_showing_it_again_resumes_polling_and_catches_up
     1  test_the_jobs_panel_does_not_leak
     1  test_a_jobs_panel_with_no_jobs_could_never_have_shown_the_leak
     1  test_no_signal_is_connected_to_a_self_capturing_lambda

**THE SKIPS ARE THE DETERMINISTIC 15** and there are no crash markers --
`grep -c "Windows fatal exception|Fatal Python error"` is 0 and there IS a
summary line, which is the pair this file insists on rather than an absence
of FAILED lines. The anchored progress-character count is 0 F/E as well.
The two `DeprecationWarning`s are the same pre-existing six-argument
`QMouseEvent` overload in `test_dock_title_bar.py` and
`test_trajectory_player.py`.

**CI MEASURES THE SAME TREE AT 6063 passed, 19 skipped, 1 deselected**
(run 32959039607, PR #48, Windows gate green, all three gates RAN), which
is the same 6083: 6063 + 19 + 1. The four extra skips are the GPU-gated
conformer gallery guards and the deselection is the PubChem network test.

**AND THE LINUX JOB REACHED THE END, which is the whole point of the
branch.** It crashed at 53% on master's merge; here it is
`6063 passed, 19 skipped, 1 deselected` in 16m50 with **zero crash
markers**, and the count reconciles to the same 6083. **THAT IS ONE RUN.**
This file's own rule is that no A/B on this crash class is worth much below
about n=10 per arm, and one green Linux run is n=1 -- it is consistent with
the fix and is not proof of it. The instrumented 170-refreshes-to-0 is the
number to trust.

**THE ANNOTATION'S CRASH BRANCH DID NOT FIRE, BECAUSE NOTHING CRASHED**, so
say what is and is not established. The classification LOGIC is verified
against the real crashed log plus three synthetic arms (empty / no-summary
/ clean / crashed), offline. That annotations from this job reach the REST
API at all is verified directly -- the linux check-run already carries two,
both `level=warning`. What has NOT run live is the `::error::` line itself.
When it does, this is how to read it, and the `failure` filter is what
tells it from the two ambient warnings:

    gh api repos/OWNER/REPO/commits/SHA/check-runs       --jq '.check_runs[] | select(.name|startswith("linux")) | .id'
    gh api repos/OWNER/REPO/check-runs/ID/annotations       --jq '.[] | select(.annotation_level=="failure")'

15m06 sits mid-band; the 6-21 range stands.)

Before it: `6053 passed, 15 skipped`
(measured 2026-08-26, **18m21**, on `joback-thermophysical` -- the Hansen
fragmenter, HOMA, Bird, and the merge of the cell/hover branch. **THIS IS THE
MERGED TREE the entry below says is owed**, so that debt is paid.

**+171 collected and 0 REMOVED**, diffed both directions in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed:

    39a7114    COLLECTS 5897
    this one   COLLECTS 6068   = 5897 + 171
    the run                     6053 passed + 15 skipped = 6068

**171 ITEMS BUT 103 NEW FUNCTIONS**, and the 68-item gap is the reason this
section records the two deltas separately. Every added item reconciles to a
new function or to a new REGISTRATION:

     66  test_hansen_fragmenter.py        the 113 SMARTS
     25  test_bird.py
     24  test_hansen_table.py
     22  test_homa.py
     12  test_failure_messages.py         arrived with the merge
      9  test_sources_are_current.py
      5  test_property_panel.py           arrived with the merge
      3  test_descriptor_providers.py
      3  test_calculator_reachability.py
      2  test_property_panel_long_values.py   arrived with the merge

Twelve of those are PARAMETRISED CASES OF PRE-EXISTING GUARDS rather than
anything written, and each names a real registration -- which is what a bare
"+171" would have hidden:

    3  ..._has_a_callable_compute       bird_aromaticity, hansen_solubility,
                                        homa_aromaticity
    5  test_every_entry_matches_the_schema
                                        bird1985, katritzky1990,
                                        kruszewski1972, krygowski1993,
                                        stefanis2008
    4  ..._data_table_declares_its_source
                                        bird_oracle.json, bird_parameters.json,
                                        hansen_groups.json, homa_parameters.json

**AND THE GROUP-CONTRIBUTION EXTRACTION ADDED ZERO**, which is the proof it
was behaviour-neutral: `test_joback_fragmenter.py`'s 59 tests are unmoved.

**THE SKIPS ARE THE DETERMINISTIC 15** and there are no crash markers --
`grep -c "Windows fatal exception"` is 0 and there IS a summary line, which
is the pair this file insists on rather than an absence of FAILED lines. The
two `DeprecationWarning`s are the same pre-existing six-argument
`QMouseEvent` overload in `test_dock_title_bar.py` and
`test_trajectory_player.py`.

**CHROMIUM'S `Failed to make current since context is marked as lost` FIRED
AND COST NO SKIPS THIS TIME.** This file records that message taking the
skips 15 -> 19 once; here it appears five times and the figure is still 15.
So it is not reliably a skip-costing event, and 15 stays the deterministic
number rather than becoming "15 unless the GPU wobbles".

**AND IT BREAKS THE OBVIOUS PROGRESS-COUNTING AWK, which read as 9
FAILURES.** Chromium writes into the middle of pytest's progress line, so a
pattern anchored `^[.sFEx]+` matches `Failed to make current...` and
`[ERROR:...]` as progress characters. Measured on this log: the loose
pattern counts **9 F/E** on a run with **zero** failures. Anchor the whole
line -- `^[.sFEx]+ *(\[ *[0-9]+%\])?$` -- which gives 0. The SUMMARY LINE is
the oracle; a progress-character count is a diagnostic, and this one lies in
the alarming direction.

**THE FIRST RUN OF THIS FIGURE WAS THROWN AWAY AT 42%, AND THE RULE IS WIDER
THAN THIS FILE HAD IT.** The recorded rule is "do not edit anything the suite
reads". Nothing was edited: the probes ran in a SEPARATE detached worktree
with `PYTHONPATH` pointed at its own `src`, so the main tree was untouched by
construction. That run still produced an `E` in
`test_ketcher_editor_backend.py` -- the file this document already names as
the canonical victim of resource and timing disturbance -- while three other
Python processes were running against the same venv.

It is recorded as DISCARDED RATHER THAN DIAGNOSED, deliberately. That file
passes 31 of 31 in isolation and the clean rerun has 0 F/E, which is
suggestive and is not proof: this file's own rule is that the crash class
moves between batches and that no A/B here is worth anything below about
n=10 per arm. **The point is that a contaminated run cannot tell the two
apart**, so it buys nothing however it comes out. Do not run ANY concurrent
work against a suite run you intend to cite -- not merely edits.

**AND THE FULL SUITE CAUGHT WHAT THE TARGETED FILES DID NOT, again.** HOMA
and Bird were verified against `test_homa.py`, `test_bird.py`, the 13
source-scanning guards and the docs guard -- all green -- and the full run
failed `test_calculation_input.py::test_geometry_is_opt_in_and_the_default_is_the_drawing`,
which enumerates the GEOMETRY calculators as an EXACT SET. Both new indices
are `calculation_input = GEOMETRY` and neither was in it. A targeted set is
chosen from where you think you changed something, and the registry-wide
guard was somewhere else.

**THE SEVEN'S OWN VERIFICATION METHOD IS DEGENERATE FOR THESE TWO**, which is
why adding them meant measuring rather than typing two names. That guard's
members were each checked by flattening z and confirming the answer changed
-- and an aromatic ring is ALREADY PLANAR, so flattening barely moves the
bonds HOMA and Bird read. Measured on benzene:

    2D drawing            REFUSED NO_CONFORMER   both -- the STRONGER claim
    3D conformer          HOMA  0.9880   Bird  99.9998
    z flattened           HOMA  0.9890   Bird  99.8308   <- nearly a no-op
    bond alternation 0.1  HOMA -1.5979   Bird  17.2222   <- what they measure
    uniform scale x1.1    HOMA -4.5164   Bird 100.0000   <- Bird ignores it

A probe built on flattening alone would have reported "unchanged" and read as
evidence they belong on DRAWING. **Bird's flatness under a uniform scale is
the method and not a defect** -- it is a coefficient of VARIATION of bond
orders, so six equal bonds score 100 at any length -- and that claim was
already shipped in its limitations and already guarded from both sides by
`test_a_ring_with_equal_bonds_scores_exactly_100` and
`test_homa_disagrees_with_bird_on_the_same_rings`. The probe confirmed prose
the code had already written, which is the outcome to hope for.

**CI MEASURES THE SAME TREE AT 6048 passed, 19 skipped, 1 deselected**
(run 32939866603, PR #46, 17m27), which is the same 6068: 6048 + 19 + 1. The
four extra skips are the GPU-gated conformer gallery guards and the
deselection is the PubChem network test, both already documented above.

**All three gates RAN** -- "Naming benchmark (must stay 181/181)", the
regulatory benchmark and the ruleset validation -- which is the step list
rather than the conclusion, and the thing a red suite would have taken with
it.

**AND THE NON-BLOCKING LINUX JOB CRASHED, WHILE REPORTING SUCCESS AT EVERY
LEVEL THE API EXPOSES.** This file's `continue-on-error` warning is stated
for the two advisory STEPS; the Linux job shows it is worse than that,
because THREE separate mechanisms each turn the failure green:

    the suite step ends `|| true`      so the STEP is [success]
    the job has continue-on-error      so the JOB is -> success
    the workflow tolerates the job     so the RUN is completed/success

Every one is deliberate and documented in `tests.yml`; together they mean
**no field the REST API returns can tell you the Linux suite failed.** The
real verdict goes to `$GITHUB_STEP_SUMMARY`, which `gh run view --json`
cannot read. What IS recoverable from the job log is the step's own
`tail -30 suite.log`: a run that finished carries a pytest summary line, and
this one carries a C-level fatal traceback instead.

    grep -oE "[0-9]+ passed[^)]*\)"        present = it reached the end
    grep -cE "Fatal Python error|Extension modules:"   1 = it did not

**AND THE `INFRASTRUCTURE FAILURE` STRING IS NOT A VERDICT.** It appears
twice in every Linux job log including the green ones, because the
fingerprint SCRIPT is echoed into the log by `##[group]Run {`. Grepping for
it counts the source, not the outcome -- the same shape as this file's
`grep FAILED` lesson, one layer out.

**IT WAS INTRODUCED ON THIS BRANCH, AND n=1 PER COMMIT IS ALL THAT SAYS SO:**

    39a7114   Linux 5877 passed, 19 skipped, 1 deselected, 16m42   GREEN
    baf5804   not measured
    c36614c   no summary line, fatal traceback                     CRASHED
    6729e26   no summary line, fatal traceback                     CRASHED

**NEITHER CANDIDATE COMMIT CONTAINS A LINE OF Qt.** `baf5804` is a JSON
table, a build tool and 24 tests; `c36614c` is a pure-Python refactor of a
SMARTS walk whose 59 existing tests did not move. So the likeliest reading is
the documented order-dependent crash class surfacing on a second platform --
"non-monotonic ... a corrupting free whose VICTIM depends on heap layout",
where adding tests shifts collection order and moves the victim, exactly as
PR #43's Windows crash took a Qt-free victim file. **That is a reading, not a
finding**: this file's own rule is that no A/B on this crash class is worth
anything below about n=10 per arm, and this is one sample per commit.

**THE VICTIM TEST IS IDENTIFIED NOW, AND FETCHING THE ARTIFACT IS WHAT DID
IT.** This entry used to end "the victim test is not identified, because
`tail -30` starts mid-traceback"; that is right about the tail and wrong
about the artifact, which carries the WHOLE `suite.log` rather than the
tail. The advice worked exactly as written -- fetch it before spending any
time on a hypothesis:

    gh api repos/OWNER/REPO/actions/runs/RUN_ID/artifacts
    gh api repos/OWNER/REPO/actions/artifacts/ARTIFACT_ID/zip > a.zip

    Fatal Python error: Segmentation fault
      src/openchem/ui/panels/jobs_panel.py, line 119 in refresh
      tests/test_molstar_viewer_backend.py, line 48 in _wait_until
      tests/test_molstar_viewer_backend.py, line 307 in
          test_a_clear_racing_a_show_ends_on_whichever_came_last

**AND THE CAUSE IS A NAMED MECHANISM RATHER THAN HEAP-LAYOUT ROULETTE** --
see "A PANEL THAT LEAKS ITSELF AND THEN POLLS FOREVER" below. The reading
recorded here, that this was "the documented order-dependent crash class
surfacing on a second platform", was the right family and the wrong level of
detail: the widget churn was not random, it was one panel doing table work
twice a second inside another test's event pump.

It did NOT gate the PR, by that job's explicit design, and the blocking
Windows gate was green. Recorded because a job whose failure is invisible to
every automated check is exactly the decorative control `tests.yml`'s own
header warns against -- and that hole is closed now, by an annotation the
REST API can read.

18m21 sits mid-band; the 6-21 range stands.)

Before it: `5882 passed, 15 skipped`
(measured 2026-08-26, **16m19**, on `joback-thermophysical` -- stage 1 of the
calculator families, the citation sweep's worktree blindness, and the
all-surfaces provenance audit.

**+27 collected and 0 REMOVED**, diffed both directions in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed -- `import openchem; print(openchem.__file__)` reported the
WORKTREE's `src`, not the main checkout:

    d7e0735    COLLECTS 5870
    this one   COLLECTS 5897   = 5870 + 27
    the run                     5882 passed + 15 skipped = 5897

**27 ITEMS BUT 22 NEW FUNCTIONS**, which is the whole reason this section
records the two deltas separately:

    14  test_descriptor_providers.py   14 functions, none parametrised
    13  test_sources_are_current.py     8 functions, PLUS 5 parametrised
                                        cases of the EXISTING schema guard,
                                        one per new source

A count that only said "+27" would have read as 27 tests written. Every one
reconciles to a new function or to a new registry entry.

**THE SKIPS ARE THE DETERMINISTIC 15** and there are no crash markers --
`grep -c "Windows fatal exception"` is 0 and there IS a summary line, which
is the pair this file insists on rather than an absence of FAILED lines. The
two `DeprecationWarning`s are the same pre-existing six-argument
`QMouseEvent` overload in `test_dock_title_bar.py` and
`test_trajectory_player.py`.

**CI MEASURES THE SAME TREE AT 5877 passed, 19 skipped, 1 deselected**
(run 32925668575, PR #46, 19m49), which is the same 5897: 5877 + 19 + 1. The
four extra skips are the GPU-gated conformer gallery guards and the
deselection is the PubChem network test, both already documented above. Worth
stating because a reader comparing the two figures should not go looking for
five lost tests.

**THAT RUN IS ON `9e9e287` AND THIS ENTRY IS IN ITS CHILD**, which is the
weaker of the two claims this file allows and is checkable rather than
assumed: the child adds only this CLAUDE.md entry and no test, so
`--collect-only` is unmoved at 5897. Citing the run that measures the tree
the figure DESCRIBES is the point -- this section has already thrown away one
figure for describing a tree that no longer existed.

**All three gates RAN** -- "Naming benchmark holds at 181/181", the
regulatory benchmark and the ruleset validation -- which is the step list
rather than the conclusion, and the thing a red suite would have taken with
it. The previous commit `d7e0735` measured 5850 + 19 + 1 = 5870 on run
32923570851, agreeing with its own local figure the same way.

**AND THAT WAS THIS BRANCH'S FIRST CI RUN AT 4,729 LINES.** `tests.yml`
fires only on push-to-master or on `pull_request`, so a branch accumulating
work sees nothing until a PR exists -- and a DRAFT PR triggers the full
workflow without being a review request. Worth knowing before the next long
branch: this project has three recorded CI-only failures no local run could
reproduce.

16m19 sits mid-band; the 6-21 range stands.)

Before it: `5855 passed, 15 skipped`
(measured 2026-08-25, **20m31**, on `joback-thermophysical` -- oxygen balance
on both published conventions, and Kamlet-Jacobs detonation.

**+84 collected and 0 REMOVED**, diffed both directions:

    previous commit   COLLECTS 5786
    this one          COLLECTS 5870   = 5786 + 84
    the run                    5855 passed + 15 skipped = 5870

    77  test_energetics.py            written
     4  test_calculator_reachability.py   the new declared module
     3  test_sources_are_current.py       klapotke2017, westwell1995, kamlet1968

**THE BAND WENT 6-19 TO 6-21 ON THIS RUN, AND IT IS UNEXPLAINED.** The
previous entry is 15m37 on a tree 84 tests smaller -- a 31% spread with
nothing to account for it, on the same machine, and 84 arithmetic-only tests
that run in 0.3 s cannot cost five minutes. Widened so a reader whose run
takes 20 minutes does not conclude the suite has hung, and recorded as the
outlier it is rather than as a new normal. This is the sixth consecutive
entry to say the band is a range with no predictive value inside it; do not
narrow it back on one fast run either.

**THE SKIPS ARE THE DETERMINISTIC 15** and there are no crash markers --
`grep -c "Windows fatal exception"` is 0 and there IS a summary line, which
is the pair this file insists on rather than an absence of FAILED lines. The
background task also exited 0, which on its own proves nothing. The two
`DeprecationWarning`s are the same pre-existing six-argument `QMouseEvent`
overload in `test_dock_title_bar.py` and `test_trajectory_player.py`.)

Before it: `5771 passed, 15 skipped`
(measured 2026-08-25, **15m37**, on `joback-thermophysical` -- the Joback
group-contribution table, its SMARTS fragmenter, and the sources backfill
that found nine shipped methods with no registry entry.

**+106 collected and 0 REMOVED**, diffed both directions in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed (`import openchem; print(openchem.__file__)` reported
`/tmp/jbase/src`, not the main checkout):

    master        d7358ac   COLLECTS 5680
    the branch              COLLECTS 5786   = 5680 + 106
    the run                          5771 passed + 15 skipped = 5786

**AND 92 OF THE 106 ARE MINE; THE OTHER 14 ARE PARAMETRISED GUARDS DOING
THEIR JOB**, which is the whole reason to diff by FILE rather than subtract
a total:

    59  test_joback_fragmenter.py     written
    33  test_joback_table.py          written
    11  test_sources_are_current.py   10 new sources + 1 new data table
     3  test_calculator_reachability.py   the new declared module

A count that only said "+106" would have read as 14 tests appearing from
nowhere. Every one reconciles to a registry entry or a declaration.

**THE SKIPS ARE THE DETERMINISTIC 15** and there are no crash markers --
`grep -c "Windows fatal exception"` is 0 and there IS a summary line, which
is the pair this file insists on rather than an absence of FAILED lines. The
background task also exited 0, which on its own proves nothing. The two
`DeprecationWarning`s are the same pre-existing six-argument `QMouseEvent`
overload in `test_dock_title_bar.py` and `test_trajectory_player.py`.

15m37 sits mid-band; the 6-19 range stands.)

**THE MERGE OF THOSE TWO BRANCHES IS MEASURED NOW, at the top of this
section.** This note is kept because the WARNING is the durable part: the two
figures below are real and NEITHER describes the merged tree. They were taken
on `joback-thermophysical` and on `failed-descriptor-cell-and-hover`, which
are SIBLINGS off master rather than one being an ancestor of the other, so
**adding 5882 to 5684 is meaningless** -- they share master's tests. The
merged tree collects 6068, which is neither sum and could only be obtained by
collecting it. Until a figure for a merge exists, the newest entry is the
newer of two parallel measurements rather than the current one.

Before it, on the OTHER branch of this merge:
A clean run is **6-19 minutes**, ending at `5684 passed, 15 skipped`
(measured 2026-08-26, **16m09**, on `failed-descriptor-cell-and-hover` --
the FAILED descriptor's reason splitting into a cell form and a full one,
and the value column learning to elide.

**+19 collected and 0 REMOVED**, diffed both directions in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed:

    master        d7358ac   COLLECTS 5680
    the branch              COLLECTS 5699   = 5680 + 19
    the run                          5684 passed + 15 skipped = 5699

Every one of the 19 reconciles to this branch: 12 in the new
`test_failure_messages.py` (the pairing rule in six arms, the two shipped
producer strings, the observational codepage walk and its control, and
the wiring guard mutation exposed), 5 in `test_property_panel.py` (the
degradation path, the cell/hover split, the export leak, the recovery
staleness, and the wide-row-versus-cell pair) and 2 in
`test_property_panel_long_values.py` (the geometry oracle and the control
that proves its fixture can still see the defect).

**THE SKIPS ARE THE DETERMINISTIC 15** and there are no crash markers --
`grep -c "Windows fatal exception"` is 0 and there IS a summary line,
which is the pair this file insists on rather than an absence of FAILED
lines. The two `DeprecationWarning`s are the same pre-existing
six-argument `QMouseEvent` overload in `test_dock_title_bar.py` and
`test_trajectory_player.py`.

**TWO OF THE SEVEN MUTATION ARMS SURVIVED FIRST TIME**, and both were
real gaps rather than uncatchable equivalents: `setText` no longer
clearing the export override (a row that fails and then succeeds goes on
exporting the stale reason), and the provider no longer attaching
`error_summary` at all (a constant that exists and is unwired). Each was
re-run against the guard it forced and caught by it.

16m09 sits mid-band; the 6-19 range stands.)

Before it: `5665 passed, 15 skipped`
(measured 2026-08-25, **14m42**, on
`alignment-geometry-and-batch-on-properties` -- the 3D alignment's three
defects, and rebuilding batch on the Properties model.

**+74 collected and 0 REMOVED**, diffed both directions in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed:

    master        6962868   COLLECTS 5606
    the branch              COLLECTS 5680   = 5606 + 74
    the run                          5665 passed + 15 skipped = 5680

Every one of the 74 reconciles to this branch: 28 in `test_batch_panel.py`
(tri-state selection, the computation matrix, the three cell kinds, the
group counts, persistence, column groups), 14 in the new
`test_batch_result_store.py`, 13 in `test_alignment.py` (the flexibility
contract in two arms, the hydrogen invariant and its own setup guard, the
partition, the two counts), 10 in the new `test_batch_detail_dialog.py`,
7 in `test_alignment_panel.py` (visibility, colour mode, the four new
columns) and 2 in `test_batch_service.py` for the scope field that was
read by nothing.

**THE SKIPS ARE THE DETERMINISTIC 15** and there are no crash markers --
`grep -c "Windows fatal exception"` is 0 and there IS a summary line,
which is the pair this file insists on rather than an absence of FAILED
lines. The two `DeprecationWarning`s are the same pre-existing
six-argument `QMouseEvent` overload in `test_dock_title_bar.py` and
`test_trajectory_player.py`.

**CI MEASURES THE SAME TREE AT 5660 passed, 19 skipped, 1 deselected**
(run 32896691945, PR #45, 23m21), which is the same 5680: 5660 + 19 + 1.
The four extra skips are the GPU-gated conformer gallery guards and the
deselection is the PubChem network test, both already documented above.
Worth stating because a reader comparing the two figures should not go
looking for five lost tests. All three gates RAN -- "Naming benchmark
holds at 181/181", the regulatory benchmark and the ruleset validation --
which is the step list rather than the conclusion, and the thing a red
suite would have taken with it.

14m42 sits mid-band; the 6-19 range stands. The run logged Chromium's
`Failed to make current since context is marked as lost` partway through
without costing any skips this time -- the `webgl` fixture's behaviour is
already recorded two entries down, where the same message took 15 skips
to 19.)

Before it: `5591 passed, 15 skipped`
(measured 2026-08-25, **15m37**, on `static-import-reachability` -- the
reachability guard's three blind spots, the widening to all 277 modules,
and the mis-routed result that measuring a doc claim turned up.

**+15 collected and 0 REMOVED**, diffed both directions against master at
`b1961d8`, which COLLECTS 5591:

    master        b1961d8   COLLECTS 5591
    the branch              COLLECTS 5606   = 5591 + 15
    the run                          5591 passed + 15 skipped = 5606

Every one of the 15 reconciles to this branch: 11 in
`test_calculator_reachability.py` (the three walk guards, the refusal, the
entry-point and wide-direction pair, the narrow half, the sidecar setup
assertion, and the kind/reason check parametrised over the three declared
modules) and 4 in `test_calculator_sections.py` (the always-on batch's
declarations, both routing halves, and the guide's category count).

**THE SKIPS ARE THE DETERMINISTIC 15** and there are no crash markers --
`grep -c "Windows fatal exception"` is 0 and there IS a summary line,
which is the pair this file insists on rather than an absence of FAILED
lines. The two `DeprecationWarning`s are the same pre-existing
six-argument `QMouseEvent` overload in `test_dock_title_bar.py` and
`test_trajectory_player.py`.

**THIRTEEN MUTATION ARMS, THIRTEEN CAUGHT**, each by the intended guard --
and one of them is a lesson about the HARNESS rather than the code. M6
(unmarking a genuinely unreachable module) scored `INVALID -- only 92 of
93 ran`, because the kind/reason guard is PARAMETRISED OVER THE DECLARED
SET, so removing a declaration legitimately removes a case. The ran-count
rule that catches an arm which errored out is the same rule that
false-positives on an arm which changes the parametrised population. Re-run
by hand it fails the wide direction, which is the intended catcher.

15m37 sits mid-band; the 6-19 range stands.)

Before it: `5559 passed, 15 skipped`
(measured 2026-08-20, **13m27**, on `make-the-new-science-reachable` --
wiring PR #41's four unreachable modules, and the three defects that
surfaced doing it.

**+185 collected and 5 REMOVED**, over two measurements, diffed both
directions in a detached worktree with the `PYTHONPATH` override
asserted before the count was believed:

    branch point   d29a077   COLLECTS 5394
    the wiring               COLLECTS 5567   = 5394 + 175 - 2
    the handbook             COLLECTS 5574   = 5567 +  10 - 3
    the run                           5559 passed + 15 skipped = 5574

**ALL FIVE REMOVALS ARE RENAMES WITH NAMED SUCCESSORS**, which is the
whole reason to diff rather than subtract, and three of them are one
event: Lange's Handbook arriving turned "no page-verified radius" into
"an element the book does not tabulate", so every fixture keyed on the
first wording had to be re-pointed at an element the BOOK stops short of
rather than one this project could not check.

    test_a_second_tier_atom_contributes_the_increment_the_paper_states
      -> test_tert_butyl_carries_the_papers_own_crowding_correction
      +  test_two_branches_are_not_corrected_and_table_4_is_why
    test_hydrogens_are_ignored_as_the_paper_simplifies
      -> test_hydrogens_are_excluded_by_default_as_eq_6_simplifies
    test_an_element_with_no_page_verified_radius_is_refused
      -> test_an_element_the_book_does_not_tabulate_is_refused
    test_every_shipped_radius_says_which_printed_value_it_came_from
      -> test_every_shipped_radius_carries_its_row_from_the_book
    test_the_registry_refuses_tsei_on_an_element_with_no_verified_radius
      -> ..._on_an_element_the_book_does_not_tabulate

The first is the sharpest: it asserted t-Bu = 1.3750 from a sentence the
paper prints and then REJECTS, so its successors assert 1.8125 and keep
the two-branch case plain.

The 185 reconcile: 64 in the new `test_calculator_reachability.py`, 44 in
`test_tsei.py` across both commits, 34 in the new `test_gutmann_bridge.py`,
11 in `test_polarizability_miller.py` for the paper's printed hybrid
assignments, 10 in the new `test_griffin_hlb_calculator.py`, 9 in the new
`test_rescued_science_end_to_end.py`, 7 for the polarizability methods, 5
for the calculator-claim guard and 2 from the new `langes15` registry
entry.

**THE SKIPS ARE THE DETERMINISTIC 15** and there are no crash markers --
`grep -c "Windows fatal exception"` is 0 and there IS a summary line,
which is the pair this file insists on rather than an absence of FAILED
lines. The two `DeprecationWarning`s are the same pre-existing
six-argument `QMouseEvent` overload in `test_dock_title_bar.py` and
`test_trajectory_player.py`.

**AN EARLIER RUN OF THIS FIGURE WAS THROWN AWAY AT 25%**, and the reason
is this file's own rule applied to itself: it was started, and then
CLAUDE.md and `docs/VALIDATION.md` were edited while it ran.
`test_docs_are_current.py` READS CLAUDE.md. The rule is not "do not edit
`src/`" -- it is "do not edit anything the suite reads".

**FOURTEEN MUTATION ARMS, ALL CAUGHT**, and two needed repairing first.
One found a real gap -- a plausible declared `TOTAL` on the TSEI
projection passed every guard in `test_declared_totals.py` AND every
guard in `test_tsei.py`, so that calculator joined the named list. The
other was not a mutation at all: `{...} if False else decline_total(...)`
changes no behaviour and scored a confident SURVIVED, which is the fifth
instance of that lesson here.

13m27 sits mid-band; the 6-19 range stands.)

Before it: `5379 passed, 15 skipped`
(measured 2026-08-20, **14m35**, on `dialogs-driven-and-documented` at
`95877c6` -- the deferred backlog: a layout guard, pop-out persistence,
and five rotted deferral reasons.

**+143 collected and 1 REMOVED**, diffed both directions in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed:

    branch before   f24be24   COLLECTS 5252
    after           95877c6   COLLECTS 5394   = 5252 + 143 - 1
    the run                            5379 passed + 15 skipped = 5394

**THE ONE REMOVAL IS A RENAME WITH A NAMED SUCCESSOR**, which is the
whole reason to diff rather than subtract. The test asserting that acetic
acid is absent from the solvent table "and that is deliberate" asserted
the opposite of what is now true, and **was right when it was written**:
the only coefficients that existed were predicted. Its successor is
`test_acetic_acid_is_present_now_and_the_refusal_is_history`, which says
so in its docstring, and four more acetic-acid guards landed beside it.
What changed was the literature, not the standard.

(And naming the OLD test here is what reddened `test_docs_are_current`
on the first attempt at this entry -- a doc may not cite a test the same
branch deleted, which is the trap this file already records one section
along. Cite the successor.)

The 143 reconcile to the nine commits: 46 in the new
`tests/test_tsei.py` (Table 1 parametrised twice over n = 1..20), 27 in
`test_gutmann.py`, 21 each in `test_polarizability_miller.py` and
`test_hlb.py`, 10 in `test_sources_are_current.py` (8 new registry
entries plus 2 new data tables, each parametrised), 7 in
`test_abraham.py`, 4 each in `test_right_dock_width.py` and
`test_pop_out_host.py`, and 3 in `test_structure_check_panel.py`.

**THE SKIPS ARE THE DETERMINISTIC 15** and there are no crash markers --
`grep -c "Windows fatal exception"` is 0 and there IS a summary line,
which is the pair this file insists on rather than an absence of FAILED
lines. The two `DeprecationWarning`s are the same pre-existing
six-argument `QMouseEvent` overload in `test_dock_title_bar.py` and
`test_trajectory_player.py`.

**FORTY MUTATION ARMS, ALL CAUGHT**, and three are worth naming because
they reconstruct recorded failures rather than inventing new ones: the
2026-08-15 `_LAYOUT_VERSION` omission, Miller's +27% on benzene, and its
-50% on CCl4. **And one arm found a vacuous guard again** -- the
Structure Check tests asserted the pop-out MECHANISM while a call site
could steal the widget back out of its host, leaving an empty strip with
an orphaned button; all 47 of that panel's tests passed with it applied.

14m35 sits mid-band; the 6-19 range stands.)

Before it: `5237 passed, 15 skipped`
(measured 2026-08-20, **14m51**, on `dialogs-driven-and-documented` at
`366640d` -- popping a cramped view out into its own window.

**+31 collected and 0 REMOVED**, diffed both directions in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed:

    branch before   05018fe   COLLECTS 5221
    after           366640d   COLLECTS 5252   = 5221 + 31
    the run                            5237 passed + 15 skipped = 5252

Every one of the 31 reconciles to this commit: 24 in the new
`tests/test_pop_out_host.py` (26 items -- the `fit_within` table is
parametrised three ways), 5 in `test_quantum_chemistry_panel.py` for the
tab machinery, and 3 in `test_alignment_panel.py` for the reported
panel.

**THE SKIPS ARE THE DETERMINISTIC 15** and there are no crash markers --
`grep -c "Windows fatal exception"` is 0 and there IS a summary line,
which is the pair this file insists on rather than an absence of FAILED
lines. The two `DeprecationWarning`s are the same pre-existing
six-argument `QMouseEvent` overload in `test_dock_title_bar.py` and
`test_trajectory_player.py`.

**A GUARD IN THIS BATCH PASSED WHILE TESTING NOTHING, and only mutation
said so.** `test_a_detached_view_survives_switching_to_another_tab`
never showed its panel, and a widget that was never shown receives no
hide events at all -- so it was green with a `hideEvent` hook installed
and without one. Nine mutation arms, nine caught, but that one only
after the guard it was aimed at was repaired to show the panel and
assert its own setup. Same lesson as `repaint()` and `resize()` on an
unshown widget, one event along.

14m51 sits mid-band; the 6-19 range stands.)

Before it: `5206 passed, 15 skipped`
(measured 2026-08-19, **14m57**, on `dialogs-driven-and-documented` at
`6480834` -- the dialog inventory and its drive step, the screening
table's clipped header, and the help contracts reaching every dialog a
bare context can build.

**+11 collected and 0 REMOVED**, diffed both directions in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed:

    master           a2ec8a8   COLLECTS 5210
    branch tip       6480834   COLLECTS 5221   = 5210 + 11
    the run                             5206 passed + 15 skipped = 5221

**THE MERGE BASE IS MASTER**, checked rather than assumed, so nothing
landed underneath this branch and the figure will be master's when it
merges.

**11 AND NOT THE 9 THE TWO NEWEST COMMITS ADDED**, which is the whole
reason to diff rather than subtract: the extra two are
`test_virtual_screening_dialog.py`, added earlier on the same branch when
the dialogs had no coverage at all. Every one of the 11 reconciles to a
commit:

    13b0b46  +2   the screening table's two column-sizing guards
    da7262c  +6   the clear-button exclusion (2), the dialog blanket
                  and its walk (4)
    6480834  +3   the element cell's live tooltip, the printed spin
                  marks, and the `*` count against the paper

**THE SKIPS ARE THE DETERMINISTIC 15** and no crash markers -- `grep -c
"Windows fatal exception"` is 0 and there IS a summary line, which is the
pair this file insists on rather than an absence of FAILED lines. The
background task also exited 0, which on its own proves nothing: this file
already records a crashed run that exited 0 with no FAILED lines in it.

14m57 sits mid-band; the 6-19 range stands. The two
`DeprecationWarning`s are the same pre-existing six-argument
`QMouseEvent` overload in `test_dock_title_bar.py` and
`test_trajectory_player.py`.)

Before it: `5195 passed, 15 skipped`
(measured 2026-08-19, **14m26**, on
`drive-consolidate-and-finish-the-contracts` -- the baseline drive's three
defects, the two geometry decisions, and the help migration reaching zero.

**+14 collected and 2 REMOVED**, diffed both directions in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed:

    branch point   60c418a   COLLECTS 5198
    branch tip               COLLECTS 5210   = 5198 + 14 - 2
    the run                           5195 passed + 15 skipped = 5210

**BOTH REMOVALS ARE THE RETIRED MIGRATION SCAFFOLDING, and they have one
named successor between them.** `test_the_migration_debt_never_grows` and
`test_a_finished_surface_does_not_regress` existed only because `missing`
could not be a failure while a migration was in flight; at zero,
`test_every_control_carries_a_help_contract` says what both said and
needs no fixture.

**CI MEASURES THE SAME TREE AT 5190 passed, 19 skipped, 1 deselected**,
which is the same 5210. The four extra skips are the GPU-gated conformer
gallery guards and the deselection is the PubChem network test -- both
already documented above, and worth stating because a reader comparing
the two figures should not go looking for five lost tests.

**THE ONE FAILURE OF THE FIRST RUN WAS A DOC CITATION, AND IT PASSED
TWICE BEFORE IT FAILED.** `test_every_file_a_doc_cites_still_exists`
caught CLAUDE.md naming the two fixtures this branch deletes. It had been
run twice after the deletion and passed both times, because `_repo_files`
asks `git ls-files` -- a file removed from the working tree but still in
the INDEX is still tracked and still resolves, so the citation only broke
once `git add -A` staged the removal. **A green docs run taken mid-change
is not evidence about the tree you are about to commit.**

The two `DeprecationWarning`s are the same pre-existing six-argument
`QMouseEvent` overload in `test_dock_title_bar.py` and
`test_trajectory_player.py`.

14m26 sits mid-band; the 6-19 range stands.)

Before it: `5183 passed, 15 skipped`
(measured 2026-08-18, **16m09**, on `isotopes-on-the-canvas` -- the
isotope reaching the canvas, the laptop-sized dialog, the right-click
menu, and the isomers.

**+77 collected and 4 REMOVED**, diffed both directions in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed:

    branch point   363ae36   COLLECTS 5125
    branch tip               COLLECTS 5198   = 5125 + 77 - 4
    the run                           5183 passed + 15 skipped = 5198

**THE LAST SEVEN WERE ADDED AFTER THE FIRST FULL RUN CAME BACK GREEN AT
5176**, which is the entry worth reading: every one of them guards a
defect the app was DRIVEN to find -- the contradicting caption, the
button hint naming the wrong nuclide, `IT` as a raw token, the status bar
claiming "ready" when nothing was armed, its two seams, and the
stay-armed pin. A green suite is a statement about the tests that exist.

**ALL FOUR REMOVALS ARE RENAMES WITH SUCCESSORS, AND THAT IS THE WHOLE
REASON TO DIFF RATHER THAN SUBTRACT.** Every one described a table that
held ground states only, and every one has a named replacement asserting
the same thing about the table that now holds states:

    test_the_table_is_ground_states_only
      -> test_the_table_carries_every_state_and_the_counts_reconcile
    test_technetium_99m_is_not_in_the_table
      -> test_technetium_99m_is_here_and_says_which_state_it_is
    test_every_key_is_its_own_z_and_a
      -> test_every_key_is_its_own_z_and_a_and_state
    test_there_are_exactly_253_stable_nuclides
      -> test_there_are_exactly_253_stable_GROUND_STATES

The third and fourth are the interesting pair: a key gained a state part
that must be asserted or Tc-99m collides onto Tc-99 and a dict silently
keeps the last one written, and 253 became "253 ground states, plus
Ta-180m named by hand" rather than a loosened bound.

**THE SKIPS ARE THE DETERMINISTIC 15**, and no crash markers -- `grep -c
"Windows fatal exception"` is 0 and there is a summary line, which is the
pair this file insists on rather than an absence of FAILED lines.

15m37 sits inside the band and near its top; the 6-19 range stands. The
two `DeprecationWarning`s are the pre-existing six-argument `QMouseEvent`
overload in `test_dock_title_bar.py` and `test_trajectory_player.py`.)

Before it: `5110 passed, 15 skipped`
(measured 2026-08-18, **17m00**, on `nuclear-isotopes-and-decay` AT ITS
MERGE OF MASTER -- the NUBASE table, the isotope picker, the two
radioactivity modes, the isotope write and the decay chains, plus
master's help-contract sweep and chain-qualified colouring arriving from
PR #36.

**MEASURED ON THE MERGE, WHICH IS THE WHOLE REASON THE EARLIER FIGURE HAD
TO BE THROWN AWAY.** This entry first recorded `5056 passed` at 16m03 on
the branch alone, and master moved underneath it while the PR was open --
so that number described a tree that no longer existed. The two counts
reconcile exactly, which is what says nothing was lost in the merge:

    branch point   76d63d3   COLLECTS 4855
    branch tip               COLLECTS 5071   = 4855 + 220 - 4
    master         1f1a0c7   COLLECTS 4808   = 4754 + 54
    the merge                COLLECTS 5125   = 5071 + 54
    the run                           5110 passed + 15 skipped = 5125

**+220 collected and 4 REMOVED** for this branch's own work, diffed both
directions in a detached worktree with the `PYTHONPATH` override asserted
before the count was believed.

**ALL FOUR REMOVALS ARE ACCOUNTED FOR AND NONE IS A LOST TEST**, which is
the whole reason to diff rather than subtract. Three are N8 replacements
-- the atom drawing used to explain why polonium had no neutron count and
now names Po-209, so tests asserting the absence became tests asserting
the name, with the "never INVENTED" invariant surviving under a new
name. The fourth is a PARAMETRISED ID changing:
`test_a_real_word_finds_the_right_thing_first[isotope-Periodic Table...]`
became `[isotope-Isotopes...]`, which is one case being re-pointed rather
than dropped.

**THE SKIPS ARE BACK TO THE DETERMINISTIC 15**, from the previous entry's
19 -- and that entry says why: the extra four were a GPU context lost
partway through an 18-minute run, which the `webgl` fixture correctly
reports rather than failing on. Nothing here needs a display.

The two `DeprecationWarning`s are pre-existing, in `test_dock_title_bar.py`
and `test_trajectory_player.py`: the six-argument `QMouseEvent` overload.
New code in this branch uses the form that takes a global position.

**AND THE MERGE ITSELF WAS NOT FREE, WHICH IS WORTH KNOWING BEFORE THE
NEXT LONG BRANCH.** GitHub would not run CI on the PR at all until the
conflicts were resolved -- a `pull_request` workflow builds against the
merge commit, and one cannot exist while the branch conflicts, so the
run list was simply EMPTY rather than red. Two of the four conflicts were
master telling this branch it was incomplete: a menu action added here
needed the `_document()` contract master had just introduced, and a panel
button using a raw `setToolTip` was refused outright by the migration-debt
guard, which is `test_every_control_carries_a_help_contract` now that the
debt is zero. The guard caught that, not review
-- the help layer working on its first contact with code written before
it existed.)

Before it: `4836 passed, 19 skipped`
(measured 2026-08-18, **17m56**, on `periodic-table-and-lewis-makeover`
at the docs commit -- the periodic-table correctness work and the Lewis
readability work. **+102 collected items and 1 REMOVED**, which is the
first entry in this list with a removal in it. The abstained-bond test
asserting it is "the only line in the picture" is false once bond guides
exist, so it became
`test_an_abstained_bond_is_the_only_line_when_guides_are_off` and asserts
the original claim in the configuration where it still holds, rather than
being weakened until green. Diffed both
directions with `comm` against a detached worktree at `068208e`, with the
`PYTHONPATH` override asserted before the count was believed.

    branch point  068208e   COLLECTS 4754
    after                   COLLECTS 4855   = 4754 - 1 + 102
    the run                          4836 passed + 19 skipped = 4855

**THE SKIPS WENT 15 -> 19 AND IT IS THE GPU, NOT A COVERAGE HOLE.** None
of the 102 new tests skips, and none of the seven touched files does
either -- measured, 266 passed and 0 skipped across them. Every subset
run of the skip-capable files gives **15**. The full run's log carries
`Failed to make current since context is marked as lost` from Chromium
partway through, after which the `webgl` fixture measures no context and
correctly skips naming the absent prerequisite rather than failing and
blaming the code. That is the fixture doing its job; treat 15 as the
deterministic figure and up to 19 as what an 18-minute run costs a GPU
context.

Before it: `4793 passed, 15 skipped`
(measured 2026-08-17, **18m12**, on `docking-box-from-the-ligand` -- the
chain-qualified residue selection. **+5 collected items and +5 test
FUNCTIONS**: 2 in `test_visualization.py` for the composed key and its
degrade-to-bare path, 3 in `test_molstar_viewer_backend.py` for the
emitted clause, the chain-only selection and the shared builder.
4803 -> 4808 collected; 4793 + 15 = 4808. Skips unchanged at 15.)

Before it: `4788 passed, 15 skipped`
(measured 2026-08-17, **22m19**, on `docking-box-from-the-ligand` -- the
Properties panel, the Docking panel and the dock title bar. **+1 collected
item and +1 test FUNCTION**,
`test_the_derive_buttons_live_tooltip_still_carries_its_contract` in
`test_docking_panel.py`. 4802 -> 4803 collected; 4788 + 15 = 4803.

**THE BAND WENT 6-19 TO 6-23 ON THIS RUN, AND IT IS UNEXPLAINED.** The
previous entry is 14m07 on a tree ONE test smaller -- a 58% spread with
nothing to account for it, on the same machine, with nothing else running
(the Mol* probes in this session finished before it started). Widened so a
reader whose run takes 20 minutes does not conclude the suite has hung, and
recorded as the outlier it is rather than as a new normal. This is the
fifth consecutive entry to say the band is a range with no predictive value
inside it.)

Before it: `4787 passed, 15 skipped`
(measured 2026-08-17, **14m07**, on `docking-box-from-the-ligand` -- the
menu bar's help contracts. **+5 collected items and +5 test FUNCTIONS**,
all in `test_tooltip_coverage.py`: the three menu-title guards, the
menu-tooltip visibility guard, and the finished-surface regression guard.
4797 -> 4802 collected; 4787 passed + 15 skipped = 4802. Skips unchanged
at 15.

**THE RUN BEFORE THIS ONE WAS RED, AND THE FAILURE WAS REAL** --
`test_nothing_tells_the_reader_to_go_to_the_3d_viewer_tab`, on a sentence
in a tooltip that contradicted a design decision. See the menu-bar section
above; it is the argument for running the 13 source-scanning guards
together before paying for a full run.)

Before it: `4782 passed, 15 skipped`
(measured 2026-08-17, **13m52**, on `docking-box-from-the-ligand` -- the
synthesised-`QAction`-tooltip reclassification. **+2 collected items and
+2 test FUNCTIONS**, both in `test_tooltip_coverage.py`: the menu actions
Qt documented for us, and the narrow-half control that keeps a real
hand-written action tooltip counting as debt. 4795 -> 4797 collected;
4782 passed + 15 skipped = 4797. Skips unchanged at 15.)

Before it: `4780 passed, 15 skipped`
(measured 2026-08-17, **13m54**, on `docking-box-from-the-ligand` -- the
Quantum Chemistry panel's help contracts and the `QTabBar` exclusion.
**+2 collected items and +2 test FUNCTIONS**, both in
`test_tooltip_coverage.py`: the tab-bar scroll buttons and the
does-not-swallow-the-panels control.

    before  1b30e1f   COLLECTS 4793
    after             COLLECTS 4795   = 4793 + 2
    the run                    4780 passed + 15 skipped = 4795

Diffed both directions in a detached worktree with the `PYTHONPATH`
override asserted before the count was believed: **0 removed, 2 added**.
Skips unchanged at 15 -- neither new test needs a display.

**39 CONTRACTS WERE ADDED AND THE SUITE GREW BY 2**, which is the staged
migration working as designed rather than a coverage hole: the contracts
are checked by the guards that already existed, and only genuinely new
BEHAVIOUR -- the exclusion rule -- needed new tests.)

Before it: `4778 passed, 15 skipped`
(measured 2026-08-17, **14m27**, on `docking-box-from-the-ligand` -- the
calculator help contracts. **+1 collected item and +1 test FUNCTION**,
`test_one_concept_is_not_split_across_many_help_ids`, written because a
mutation walked straight through the existing guards. 4792 -> 4793
collected, 0 removed.)

Before it: `4777 passed, 15 skipped`
(measured 2026-08-17, **13m54**, on `docking-box-from-the-ligand` -- the
help-contract layer. **+9 collected items and +9 test FUNCTIONS**, all in
`test_tooltip_coverage.py`: the three-surface walk, contract validity,
help_id-means-one-thing, anchor and source resolution, the placeholder
floor, the migration debt, the shared-discovery check, and the exclusion
reasons.

    before  a91fa41   COLLECTS 4783
    after             COLLECTS 4792   = 4783 + 9
    the run                    4777 passed + 15 skipped = 4792

**THE FIRST RUN OF THIS FIGURE CRASHED, AND `grep FAILED` SAID IT WAS
FINE.** It died at 4057 of 4792 with `Windows fatal exception: access
violation`, top frame `conftest.py pytest_runtest_logfinish` -- the
teardown collect. There are no `FAILED` lines in a run that never reaches
the end, so a grep for them returned nothing and read as success, and the
background task reported exit 0. **Check for a SUMMARY LINE, not for an
absence of failures** -- `grep -E "[0-9]+ passed"` and
`grep -c "Windows fatal exception"`. This is the same lesson as the
skipped-gates one two sections down, one level lower.

The likely cause was a module-scoped fixture holding **372 live Qt
references** -- widgets, `QAction`s and `QTableWidgetItem`s, which are not
even `QObject`s -- and releasing them all at once into that collect. The
fixture extracts plain data and drops every handle now, which is better
regardless. **The re-run was clean, and that is ONE run**: this crash class
is documented below as moving between batches, and n=1 is not evidence
either way.

Also note the collected-count diff needs `--include-untracked`: four of
the six files were new, so a plain `git stash push` left them in both arms
and reported 0 added.)

Before it: `4768 passed, 15 skipped`
(measured 2026-08-17, **15m10**, on `docking-box-from-the-ligand` -- the
search box drawn in the Mol* viewer. **+11 collected items and +11 test
FUNCTIONS**: 7 in `test_molstar_viewer_backend.py` for the box's committed
state, the latest-wins burst, both clear/replace races, the queued-clear
sentinel and surviving a structure reload; 4 in
`test_main_window_docking_visualization.py` for panel visibility, spinbox
redraw, the no-receptor case and the end-to-end geometry invariant.

    before  bf447a0   COLLECTS 4772
    after             COLLECTS 4783   = 4772 + 11
    the run                    4768 passed + 15 skipped = 4783

Diffed both directions, **0 removed, 11 added**. Skips unchanged at 15 --
the Mol* tests run under `offscreen`, where its state management works
without a GPU even though rendering does not.

**MOL* WAS SHOWING A DIFFERENT MOLECULE FROM THE ONE BEING DOCKED**, and
that is the finding this commit exists for -- see the section below.)

Before it: `4755 passed, 15 skipped`
(measured 2026-08-17, **17m18**, on `docking-box-from-the-ligand` -- the
docking search box deriving from the receptor's own ligand. **+16 collected
items and +16 test FUNCTIONS**, so the two deltas agree again: 6 in
`test_binding_site.py` for `describe_box_placement`'s three relationship
states plus the centre-to-centre and tolerance guards, and 10 in
`test_docking_panel.py` for the derived/manual/none payload paths, the
stale-box reset, idempotence and the pose-column tooltips.

    master 068208e   COLLECTS 4754
    after            COLLECTS 4770   = 4754 + 16
    the run                   4755 passed + 15 skipped = 4770

Diffed both directions with `--collect-only -q | grep :: | sort` and
`comm`: **0 removed, 16 added**. Skips unchanged at 15 -- none of the 16
needs a display. Baseline derived with `rev-parse` and a `--collect-only`
rather than read from the entry below, which for once was already correct.

17m18 sits inside the band and near its top. The 6-19 range stands.)

Before it: `4739 passed, 15 skipped`
(measured 2026-08-17, **15m22**, on master at `8c0c257` + the CIP
staleness fix. **+19 collected items and +19 test FUNCTIONS**, so for once
the two deltas agree: 9 in `test_ketcher_editor_backend.py` against the
real bundle, 5 in `test_molecule_editor_widget.py`, 4 in
`test_ketcher_bundle_is_current.py` -- three of those the parametrised
`window.openchem*` guard, which covers the two globals that had shipped
unguarded -- and 1 in `test_main_window_menu_actions.py`. Diffed both
directions against `8c0c257`'s 4735, **0 removed, 19 added**. Skips
unchanged at 15; the run reconciles exactly, 4739 + 15 = 4754 collected.

**THIS FIGURE WAS 4738 AN HOUR EARLIER, AND THE +1 IS THE POINT.** That
run was green and honest, and the pool-id bug below was live through all
of it -- the guard that catches it was written afterwards, from a bug
report. A green suite is a statement about the tests that exist.

**THE BASELINE WAS DERIVED, NOT READ FROM THE ENTRY BELOW, and it was
stale by 10.** That entry records 4710 + 15 = 4725, while master at
`8c0c257` COLLECTS 4735 -- the release commit moved it. Reading the entry
would have reported +28. `rev-parse`, a detached worktree and a
`--collect-only`, with the `PYTHONPATH` override asserted by
`python -c "import openchem; print(openchem.__file__)"` before the count
was believed.

**AND THE FIRST RUN OF THIS FIGURE WAS THROWN AWAY, WHICH IS THE ENTRY
WORTH READING.** It was started and then six files were edited while it
ran -- five of them DOCSTRING-ONLY, which is exactly the change a person
talks themselves into believing is inert. It came back
`2 failed, 4736 passed`:

    test_generation_has_one_implementation_reached_two_ways
    test_every_intercepted_name_has_a_route

Both pass in isolation, and neither had anything to do with the change.
**They read source FROM DISK** -- the first `ast.parse`s every file under
`src/openchem`, the second reads `main.jsx` and
`ketcher_editor_backend.py` -- so they parsed files caught mid-write. Two
plausible, alarming, entirely fictitious regressions. The rule elsewhere
in this file is that a run concurrent with anything touching `src/` is not
a measurement; this is what that costs when ignored, and "it was only a
docstring" is not an exemption, because a source-scanning test does not
care what the bytes MEAN.

Before it: `4710 passed, 15 skipped`
(measured 2026-08-16, **15m29**, on `sources-registry` -- the provenance
registry. **+77 collected items**, and for once the interesting number is
that only 4 of them are new test FUNCTIONS in existing files: 73 are
`test_sources_are_current.py`, heavily parametrised over the registry's 53
entries and the 7 shipped data tables, plus 2 in `test_lewis_adduct.py` and
2 from `docs/SOURCES.md` joining the parametrised `DOCS` list in
`test_docs_are_current.py`.

    branch point  1f0cd6b   COLLECTS 4648
    after                   COLLECTS 4725   = 4648 + 77
    the run                          4710 passed + 15 skipped = 4725

Diffed both directions, **0 removed, 77 added**, measured in a detached
worktree with the `PYTHONPATH` override asserted before the count was
believed. Skips unchanged at 15 -- nothing new needs a display.

15m29 sits mid-band. The 6-19 range stands.)

Before it: `4633 passed, 15 skipped`
(measured 2026-08-16, **14m16**, on `solubility-base-bias` -- the base-bias
power study at criteria v3. **+5 test functions**, all in
`test_abraham.py`, none parametrised: the experiment/production agreement
guard, the evidence-reading guard, the artifact-reproducibility guard, the
endpoint-eligibility guard and the duplicate-table refusal. Skips unchanged
at 15; 4643 -> 4648 collected, diffed both directions, 0 removed.

**PRODUCTION IS UNTOUCHED BY THIS ONE.** The verdict was `SURFACE_ONLY`,
so `production_change_permitted = false` and `git diff src/` is empty for
the whole power study -- the guard against fixing the model once the
answer is inconvenient.)

Before it: `4628 passed, 15 skipped`
(measured 2026-08-16, **13m29**, on `solubility-base-bias` at `435130d` --
the base-bias verdict and the arm-status work. **+6 test functions**, all
in `test_abraham.py`, none parametrised. Skips unchanged at 15.

    master f9a4627   COLLECTS 4637
    after            COLLECTS 4643   = 4637 + 6
    the run                   4628 passed + 15 skipped = 4643

Diffed both directions, 0 removed. **THE BASELINE WAS 4637 AND NOT THE
4632 THIS FILE CARRIED EARLIER IN THE DAY** -- that figure predated the
five acetic-acid guards, and reading it would have reported +11. Derived
with `rev-parse` and a `--collect-only` in a detached worktree, with the
`PYTHONPATH` override asserted before the count was believed.

13m29 sits mid-band. The 6-19 range stands.)

Before it: `4622 passed, 15 skipped`
(measured 2026-08-16, **14m03**, on `solubility-predictor` at `60643d8` --
the two open edges closed. **+5 test functions**, all in
`test_abraham.py`: the predicted-only reason, its reachability through the
calculator, the no-shipped-coefficients guard, water-first ordering, and
the familiar-solvent filter. Skips unchanged at 15.

**THE ENTRY BELOW WENT STALE BY 5 WITHIN THE SAME SESSION**, which is the
drift this section keeps recording -- and this time the tests that made it
stale were written an hour after the figure was taken, by the same person,
who then had to re-measure rather than subtract. 14m03 against the
previous run's 19m18 on a tree FIVE tests larger is a 27% spread with
nothing to explain it, so the 6-19 band stands as a range with no
predictive value inside it.)

Before it: `4617 passed, 15 skipped`
(measured 2026-08-16, **19m18**, on `solubility-predictor` at `bd91fce` +
the non-aqueous lookup route. **+24 collected items and +24 test
functions**, every one in the new `tests/test_abraham.py` and none of them
parametrised, so for once the two deltas are the same number.

**THE BAND WENT 6-18 TO 6-19, AND THIS RUN IS ITS NEW TOP.** 19m18 is the
slowest full run this file has recorded. Nothing explains it -- the tree
is 24 tests larger than a run that took 14m08, and 24 non-webview tests
cannot cost five minutes. Recorded as the outlier it is rather than as a
new normal, which is the same caution the four entries below already
carry. Do not read a 19-minute run as a hang.

**SKIPS UNCHANGED AT 15.** None of the 24 needs a display, so
4593 + 24 = 4617 passed and 15 skipped is the whole delta accounted for.

**THE BASELINE WAS DERIVED WITH `rev-parse`, NOT READ FROM THE ENTRY
BELOW** -- and that mattered, because the entry below says 4563 and the
branch had already moved to 4593 passed / 4608 collected at `bd91fce`
(the Platts-reading commit added tests). Reading 4563 as the baseline
would have reported +54 instead of +24.

    branch before  bd91fce   COLLECTS 4608
    after                    COLLECTS 4632   = 4608 + 24
    the run                           4617 passed + 15 skipped = 4632

**The +24 was DIFFED, not subtracted** -- `--collect-only -q | grep :: |
sort` on both trees, `comm -23` for removals and `comm -13` for
additions: **0 removed, 24 added**. Measured in a detached worktree with
`PYTHONPATH` pointed at ITS `src`, and the override asserted with
`python -c "import openchem; print(openchem.__file__)"` before the count
was believed -- without that, `openchem.pth` silently imports the MAIN
`src` and you measure the old tests against the new source.)

Before it: `4563 passed, 15 skipped`
(measured 2026-08-16, 14m08, on `solubility-predictor` -- the solubility
predictor. **+65 collected items and +55 test functions** over master's
4513 at `6f8a8c8`: 55 in `test_solubility.py`, 6 in `test_logd.py`
pinning the shared-factor extraction, 2 in `test_fact_view.py` for the
compact form, and 2 in `test_docs_are_current.py` from the new
assessment doc joining its parametrised list.

**The +63 was DIFFED, not subtracted** -- `--collect-only -q | grep :: |
sort` on both trees, `comm -23` for removals and `comm -13` for
additions: 0 removed. A bare subtraction cannot tell "63 added" from "70
added and 7 quietly deleted".

**SKIPS UNCHANGED AT 15.** None of the new tests needs a display, so
4498 + 65 = 4563 passed and 15 skipped is the whole delta accounted for.

**AND THE FIGURE WAS WRITTEN DOWN WRONG ONCE, WITHIN THE HOUR.** It was
first recorded as 4576, which was a real measurement taken BEFORE the
last two tests were written -- the two `FactView` guards that the live
check forced. The run then reported 4563 + 15 = 4578 and did not
reconcile. Nothing was stale about the method; the count was simply
taken too early. **Re-collect AFTER the last test lands, and reconcile
the run against it** -- a 2-item gap is exactly the size that reads as a
rounding error and is not one.

Note master had already moved 4498 -> 4513 since the entry below, which
is the same drift one level up: derive the baseline with `rev-parse` and
a `--collect-only`, never from the previous entry.

A clean run is **6-18 minutes**, ending at `4498 passed, 15 skipped`
(measured 2026-08-15, 15m32, on master at `4ba375e` — the right dock's
starting width. **+5 test functions**, all in
`test_right_dock_width.py`: the width table, the floor, the cap, the
saved-layout gate, and that the method resizes anything at all.
Collected 4508 -> 4513, skips unchanged at 15.)

**THE THREE FIGURES IN THIS SESSION RAN 11m55, 16m59 AND 15m32** on
trees within eight tests of each other. That is the band's whole story:
it is a range, not a prediction, and the entry below already says not to
narrow it on a fast run. Nothing here changes it.

**THE FIGURE WENT STALE BY 5 WITHIN THE HOUR, WHICH IS THE POINT.** The
tests that made it stale were added by the commit directly below this
one, and the gap was noticed only because somebody went looking. That is
the same drift the entries below record at 11 tests and at 111 — the
instrument is `--collect-only`, it costs six seconds, and it is the only
thing that makes "did my change add what I think it did" a question with
an answer.

Before it: `4493 passed, 15 skipped`
(measured 2026-08-15, 16m59, on master at the ORCA scratch-cleanup work.
**+2 test functions**, both in `test_quantum_chemistry_service.py`: the
scratch-isolation guard and the deterministic retry guard. Collected
4506 -> 4508, skips unchanged at 15.)

**THE BAND HAS NOW ABSORBED ITS FOURTH UNEXPLAINED SWING.** 11m55 and
16m59 on trees differing by TWO tests is a 43% spread. Same machine,
same tree to within two functions, nothing to explain it — which is now
the fourth consecutive entry to say so. **Treat 6-18 as a range with no
predictive value inside it**, and do not read a slow run as a hang or a
fast one as an improvement.

**THE SUITE LEAVES THE REAL DATA ROOTS UNTOUCHED, and that is measured
rather than assumed.** Snapshotted `data_root`, `cache_root`,
`space_free_cache_root` and `default_data_root` either side of a full
run: **+0 -0 on all four**. Worth having as a baseline, because one file
WAS writing into them until this commit (see the ORCA scratch section)
and nothing would have noticed. Re-measure it the same way if a service
gains a new on-disk artefact:

```bash
uv run --no-sync python -c "from openchem import paths; print(paths.data_root(), paths.space_free_cache_root())"
```

Before it: `4491 passed, 15 skipped`
(measured 2026-08-15, 11m55, on master at `2d5f0c8` — the Properties
panel's width clip. **+8 test functions**, all in
`test_property_panel_long_values.py`: the rendered-overflow oracle and
its two boundary controls, the production-path and wide-row caption
guards, viewport stability, the two reported strings, and the export
path. Skips unchanged at 15 — none of the eight needs a display.)

**MEASURED ON MASTER ITSELF**, on a clean tree, so none of the
branch-versus-merge reasoning below applies. Counts reconcile:

    before  f3b1689   COLLECTS 4498
    after   2d5f0c8   COLLECTS 4506   = 4498 + 8
    the run                    4491 passed + 15 skipped = 4506

**+8 COLLECTED AND +8 FUNCTIONS, which is worth stating** because the
entry below had to separate them: nothing added here is parametrised, so
for once the two deltas are the same number.

**THE BAND IS UNMOVED AND THIS RUN IS NEAR ITS FLOOR.** 11m55 against the
previous entry's 18m00 on a tree eight tests LARGER — a 51% spread with
nothing to explain it, which is the same unexplained variance this
section has now recorded three times. Do not narrow the band on it.

**THE FULL SUITE CAUGHT WHAT NINE TARGETED FILES DID NOT.** The width
work was verified against `test_property_panel*.py`,
`test_calculator_sections.py`, `test_right_dock_width.py`,
`test_docs_are_current.py`, `test_layering.py`, `test_qt_object_disposal.py`
and `test_empty_states.py` — 188 passed — and the full run then failed
`test_result_presentation.py::test_every_descriptor_row_shows_its_display_name_and_units`,
whose probe read a caption's `.text()`. That is now a width-dependent
view, so `'Molecular Weight (g/mol)'` came back `'Molecul…'`. **A
targeted set is chosen from where you think you changed something**, and
the third consumer of caption text was somewhere else.

Before it: `4483 passed, 15 skipped`
(measured 2026-08-15, 18m00, on master's merge `f3b1689` — the
regulatory-coverage work: four rulesets in two domains, plus date-aware
screening. **+111 collected items and +81 test functions** over
`ca87c60`, all of them in three files: 53 functions / 83 items in
`test_regulatory_rulesets.py`, 18 in `test_regulatory_engine.py` for the
date filtering, 10 in `test_regulatory_calculator.py`.)

**THE TWO DELTAS ARE DIFFERENT NUMBERS AND BOTH ARE RECORDED**, because
this section has conflated them before. 111 is collected ITEMS, 81 is
distinct test FUNCTIONS, and the 30-item gap is parametrisation of the
new functions — measured, not inferred: the set of added items belonging
to a PRE-EXISTING function is EMPTY, so no old function merely gained
cases. A `--collect-only` count moves for either reason and cannot tell
you which; strip the `[param]` suffix and diff again to find out.

**THE BAND DID NOT MOVE.** 18m00 sits exactly ON the top of the 6-18
band rather than past it, so 6-18 stands as written. Worth saying
explicitly because the two entries below EACH widened it and each
flagged the widening as unexplained — a reader scanning this list should
not read a third consecutive stretch into it.

**THE SKIPS ARE UNCHANGED AT 15.** Not one of the 111 is gated on
`grid_display` or on anything else, so 4372 + 111 = 4483 passed and
11 + 4 = 15 skipped is untouched. That is the whole delta accounted for.

**MEASURED ON A BRANCH, AND TREE-IDENTICAL TO THE MERGE.** `f3b1689^2`
is `f5f8ae5` and `git diff f5f8ae5 f3b1689` is **empty**, so the merge
commit carries the branch's tree byte for byte — checked AFTER merging
rather than predicted, which is the whole point of the rule. The
merge-base equals `^1`, so nothing landed while the branch was open:

    master before  ca87c60   COLLECTS 4387
    merge          f3b1689   COLLECTS 4498   = 4387 + 111
    the run                          4483 passed + 15 skipped = 4498

**THE PARENT WAS NOT THE COMMIT ANYBODY REMEMBERED, and that is the
warning rather than a footnote.** The obvious baseline for this figure is
`c9cba3b`, the `wire-the-gallery-overlay` merge the entry below was
measured against — and it is WRONG. `git rev-parse f3b1689^1` is
`ca87c60`, a `docsweep-after-the-gallery-overlay` merge that landed in
between and that no entry in this list mentions. It happens to collect
4387 as well, so the arithmetic would have come out right while naming
the wrong commit. **Derive the baseline with `rev-parse`, never from
memory or from the entry above** — this is the same drift as the 4176
entry being stale by 11, caught one step earlier.

**The +111 was DIFFED, not subtracted.** `--collect-only -q | grep :: |
sort` on both trees, `comm -23` for removals and `comm -13` for
additions: **0 removed, 111 added**, and the same on function names, 0
removed and 81 added. A bare subtraction cannot distinguish "111 added"
from "130 added and 19 quietly deleted", and this section has twice
recorded a delta that was wrong.

**A WORKTREE HAS NO `.venv`, AND THE OBVIOUS WORKAROUND MEASURES THE
WRONG TREE.** `uv run` in a fresh worktree builds an empty venv and
reports `No module named pytest`; reaching for the main checkout's
interpreter instead silently imports the MAIN `src`, because
`openchem.pth` is an editable install pointing there — so the baseline
collection would be the old tests against the new source. `PYTHONPATH`
precedes `.pth` additions in `sys.path`, so this is the cheap fix, and
it costs 7 seconds rather than a full sync:

```bash
git worktree add --detach /tmp/base f3b1689^1
cd /tmp/base && PYTHONPATH=/tmp/base/src \
  "/d/Random Projects/OpenChem Studio/.venv/Scripts/python.exe" \
  -m pytest --collect-only -q | tail -2
```

**Assert the override worked before believing the count** — one
`python -c "import openchem; print(openchem.__file__)"` says which `src`
you are about to measure, and the failure mode is a plausible number
from the wrong tree.

Before it: `4372 passed, 15 skipped`
(measured 2026-08-14, 17m50, on `wire-the-gallery-overlay` — the gallery
overlay's last wire, +20 test functions over master's `c3ab297`: 12 in
`test_spatial_overlay_widget` for the per-cell routing, 4 in
`test_spatial_annotations` for the page's build race, grid replacement,
label limitation and caption clear, 3 in `test_webgl_gate` for the
shared display gate, and 1 in `test_adopt_conformer` for the readability
thresholds.

**+4 SKIPS, and they are the four new PAGE guards** — every one is gated
on `grid_display`, like the gallery tests already there. The 16 other new
tests use fakes and run everywhere. So 4356 + 16 = 4372 passed and
11 + 4 = 15 skipped, which is the whole delta accounted for.

**THE BAND WENT 6-16 TO 6-18 ON THIS RUN**, and the same caution applies
as the last time it widened: 14m11 and 17m50 on trees differing by ONE
test function is a 25% spread that the added test cannot explain. It is
widened so a reader whose run takes 17 minutes does not conclude the
suite has hung, and recorded as unexplained rather than as a new normal.

**A BRANCH FIGURE, AND HERE IS WHAT MAKES IT CITABLE.** It adds test
functions, so the identical-tree rule below does NOT apply — the weaker
one does: `origin/master` at `c3ab297` **is** the merge-base, so nothing
landed while the branch was open. Counts reconcile exactly, in seconds:

    master        c3ab297   COLLECTS 4367
    branch tip              COLLECTS 4387   = 4367 + 20
    the run                          4372 passed + 15 skipped = 4387

**The +19 was DIFFED, not counted.** `--collect-only | grep :: | sort`
on both trees and `comm` between them names all 19 additions and shows
**zero removals** — which is what a bare subtraction cannot tell you, and
this section has twice recorded a delta that was wrong.

**AND THE FIRST RUN OF THIS FIGURE WAS THROWN AWAY**, for the reason the
entry below already gives. It was started before the CLAUDE.md edits and
`tests/test_docs_are_current.py` READS CLAUDE.md, so the run was
measuring a file being rewritten underneath it. The rule is not "do not
edit `src/`" — it is "do not edit anything the suite reads", and a
troubleshooting file is not exempt from it.

Before it: `4356 passed, 11 skipped`
(measured 2026-08-14, 12m36, on `overlay-spatial-annotations` at
`76bfcc9`; master's merge `46ccd66` adds no test function and COLLECTS
4367 = 4356 + 11, so the figure is master's. +57 passed over the 4299
below, across two branches: the spatial dialog -- 22 in
`test_spatial_annotations`, 2 for the dialog -- and the overlay -- 15 in
the service, 11 in the widget, 3 for origin resolution, 5 for recorded
parameters. **The 3 new SKIPS are the gallery per-cell guards**, which
need `QT_QPA_PLATFORM=windows` for the same `createViewerGrid` reason
the other gallery tests do.)

Before it: `4299 passed, 8 skipped`
(measured 2026-08-13, 11m57. +6 over the 4293 below, for the report
parser's sign class -- both-signs, the sign kept in the value, the
positive Huckel HOMO, the value list, the attached unit, and the
`report_fields` entry point).

**A BRANCH THAT ADDS TESTS CAN STILL DESCRIBE MASTER, AND HERE IS THE
CONDITION.** The entries below say a branch figure is citable when the
trees are identical, which this one is NOT -- it adds six test
functions. The weaker check that does apply: `origin/master` at
`be585c3` **is** the merge-base, so nothing landed while the branch was
open and the merge is a FAST-FORWARD -- so master's merge commit
`a915443` has the branch's tree, byte for byte. Confirmed after merging
rather than predicted: `git diff af0ef79 a915443` is empty. That is
strictly what "measured on the merge commit" buys, without the second
twelve-minute run.

Counts, all reconciling exactly (4 seconds each):

    master before  be585c3   COLLECTS 4301
    branch tip     af0ef79   COLLECTS 4307   = 4301 + 6
    master merge   a915443   COLLECTS 4307   same tree
    the run                          4299 passed + 8 skipped = 4307

**Check the fast-forward, do not assume it.** The whole reason the
entries below are so insistent is that master HAS moved under a branch
before, twice, and the branch figure was wrong both times:

```bash
[ "$(git merge-base origin/master HEAD)" = "$(git rev-parse origin/master)" ]
```

**AND THE FIRST RUN OF THIS FIGURE WAS THROWN AWAY.** A mutation harness
was writing to `src/openchem/chem/report_adapter.py` and clearing
`__pycache__` across the tree while that suite run was in flight, which
is exactly the "an A/B is worthless if the tree is being edited during
it" rule elsewhere in this file, applied to a plain run rather than to an
A/B. It reached 26% looking perfectly healthy. **A run concurrent with
anything that touches `src/` is not a measurement**, and the previous
entry's "CONCURRENT with funnel generation and a live app drive" was
survivable only because those two generate data rather than edit code.

Before it: 4293 (measured 2026-08-13, 12m30. +24 over the 4269 below,
for the conformer funnel work -- 5 symmetry-metric guards in the dedup
file, 5 in generation-options (the snapshot default, origin tracing, the
persistence boundary, the observational guard, the embedder wiring), 6 in
the service (four truncation, two provenance-flag), 7 for the details
dialog, and the defaults pin).

Measured on `conformer-defaults` at `6245a32`. Master's merge `2ed1100`
adds only `cdfc72e` -- a docstring and the funnel script's constant
import, no test functions -- and the cheap half of the rule confirms it:
master COLLECTS 4301, which is exactly 4293 + 8, in seven seconds. Note
the run was also CONCURRENT with funnel generation and a live app drive
for part of its length and still came in at 12m30, which says the 6-16
band has slack in it rather than being tight.

Before it: 4269 (measured 2026-08-12, 14m54. +13 over the 4255 below,
for the deferred-list sweep -- 8 for the docs staleness guard, the three
MISMATCH paths and the reaction-template example, 4 for the ORCA path
normalisation and 1 for the version-fragment fix).

**TAKEN ON A BRANCH, AND HERE IS WHY IT STILL DESCRIBES MASTER.** The run
was on `close-the-open-three`, not on master's merge commit `26e8725`.
The cheap half of the rule below was applied rather than skipped: both
COLLECT 4277, and the branch adds no test functions -- its changes are
documentation, benchmark reference data, and the bodies of existing
tests. So the count is master's. A branch that had ADDED tests could not
be cited this way, which is the trap the entries below are about.

**NOTE THE `1 deselected` IS GONE, and that is a change in the COMMAND
rather than in the suite.** The figure below was taken with the network
test deselected; this one was taken bare, and that test now passes rather
than failing on `HTTP 400`. 4277 collected either way. If it starts
failing again, deselect it as the entry below describes -- but do not read
its absence here as a test having been lost.

Before it: 4255 passed, 8 skipped, 1 deselected (master's MERGE COMMIT
`e52fa29`, measured 2026-08-12, 13m35. +58 for the declared-total
contract -- the registry audit, the Crippen hydrogen modes, the
descriptor-caption fix and the presentation guards -- over the 4197
below).

The run was actually taken on `9981029`, the branch's merge of master
INTO it, and the two are cited together because they are the same tree:
`git diff 90f094e e52fa29` is empty and nothing landed on master in
between, so the figure describes master rather than merely a branch that
had caught up. Checking that is the cheap half of the rule below -- an
identical tree makes the branch measurement valid, and a non-identical
one means it was never master's number.

**+58, AND THE BRANCH SPENT A DAY BELIEVING IT WAS +68.** It was
measured against the 4176 entry, which was already two merges stale, and
the corrected figure was sitting in an unmerged commit at the time. The
collected count settles it in four seconds and reconciles exactly:
4264 collected = 4255 + 8 + 1, against master's 4206. The instrument
below is not a nicety -- it is the difference between a delta you can
state and one you cannot.

Before it: 4197 on the MERGE COMMIT `887549a` (measured 2026-08-12,
16m22. +9 for the single-shot timer work -- two guards for the panel
reveal, two for the crystal draw, one each for the worker-thread
progress reporter, the ketcher settle token, the instrumented metrics
dump and the destroyed window, plus the package-wide invariant -- and
+1 from #15, which landed on master while that branch was in flight,
over the 4187 below).

**MEASURED ON THE MERGE COMMIT, AND THAT IS NOT WHAT THE BRANCH SAID.**
The branch itself ended at 4196 in 13m06, with five earlier runs at
11m02, 11m24, 12m06, 12m36 and 12m46 as it grew. master had moved under
it: #15 added `ui/widgets/collapsible_section.py` and a property-panel
test while the branch was open, touching the same area the branch did.
The merge reported CLEAN, which is a statement about TEXT and not about
behaviour, and the branch figure could not have told you either way.
Both are green -- but "I measured the branch" is not an answer to "what
does master do", and this is the rule at the top of this section being
paid for rather than quoted.

**THE BAND WENT 6-14 TO 6-16 ON A SINGLE RUN, AND THAT RUN IS
UNEXPLAINED.** 6-14 was written about an hour earlier, off six runs of
the same branch, and the very next measurement landed two minutes
outside it. One added test cannot cost three minutes and nothing else
changed. It is widened anyway, because a reader whose run takes 15
minutes should not conclude the suite has hung -- but it is recorded as
the outlier it is, not as a new normal. The ten-run spread further down
(361 to 568 seconds on essentially one tree) is the reason not to fit a
band to one number in either direction, and that cuts both ways: do not
narrow it back on one fast run either.

**THE 4176 ENTRY BELOW WAS ALREADY STALE BY 11 WHEN THAT BRANCH STARTED,
and nothing in this list accounts for them.** master at `9159d1d`, this
branch's base, **collects 4196**, i.e. 4187 passed against the same 8
skips and 1 deselection. Two merges landed after the Lewis entry --
`ci-webgl-skip` (#12) and `right-dock-width` (#13) -- and neither
refreshed the figure, which is precisely the drift the warning further
down describes, caught happening rather than described in the abstract.

**That 4187 is DERIVED, not measured**, and is written that way on
purpose: it comes from `pytest --collect-only -q` on the base commit
minus the skips and the deselection, not from a run, because no full
measurement has been taken on master since the Lewis entry. Treat it as
the arithmetic it is. **A collected count is the sharper instrument for
"did my change add the tests I think it did"** -- it is deterministic,
takes four seconds rather than twelve minutes, and is not perturbed by a
skip whose condition moved. The merge figure above reconciles with it
exactly: 4206 collected, 4197 + 8 + 1.

**THAT ENTRY MOVED THREE TIMES IN ONE DAY -- 4195, 4196, 4197** -- once
from the next commit on the same branch, once from a merge that landed
on master while the branch was open. Left as a note rather than quietly
corrected each time, because it is the strongest argument in this
section for the instrument rather than the number: this is not slow
drift over months, and a figure re-derived in four seconds by
`--collect-only` cannot go stale under you the way one that costs
sixteen minutes does. Take the collected count for "did my change add
what I think it did", and re-measure the passed count only when you
need the wall clock too.

Before it: 4176 on branch `full-lewis-structure` (measured 2026-08-11,
11m25, with an earlier run of the same branch at 12m15. +161 for the full
Lewis structure -- the resonance gate, the model, the SVG renderer, the
RDKit builder and the dialog -- over the 4015 below).

Before it: 4015 on branch `lone-pairs-on-the-canvas`, 11m43 and 12m47 on
two consecutive runs. +79 for drawing lone pairs on the canvas, over the
3936 below.

**THE BAND WIDENED, and it is the webview tests that did it.** Two runs
of the same tree came in at 11m43 and 12m47, both outside the old
6-9.5. About two minutes of that is
`tests/test_electron_overlay_canvas.py` and
`test_electron_overlay_lifecycle.py`, which drive the REAL vendored
Ketcher bundle -- each test builds a `QWebEngineView`, waits for the
page, and pumps events. That is the price of testing the overlay against
the thing it actually runs on, and it is worth paying; see the
lone-pair sections below for what those tests caught. Do not read 12
minutes as a hang.

**The 161 Lewis tests did NOT widen it further** -- they build no webview
and the whole set runs in about 2 s. A test count and a wall clock are
not the same measurement here, and it is the webview files that decide
the second one: the branch's two full runs came in at 12m15 and 11m25,
the FASTER of them being the one with 24 more tests in it.

Before it: 3936 on clean `master` at the `editor-as-workspace` merge,
9m03 -- measured on the merge commit itself rather than on the branch,
which is a rule this file learned the hard way. +40 for rotating in the
2D editor and +34 for the stereo/lone-pair work, over the 3862 below.

Before it: 3862 on branch `conformer-comparison`, after making
conformers comparable, putting the 3D shape into the 2D editor, and the
gallery: +4 for the Ketcher 3D gate, +21 for display alignment, camera
retention and relative energies, +29 for the camera-oriented drawing,
+13 for the gallery and +13 for the generation controls, over the 3765
below.

**The skip count went 2 -> 7, and the five are deliberate.** The
page-level gallery tests do not run under Qt's `offscreen` platform,
where `$3Dmol.createViewerGrid` throws; run them with
`QT_QPA_PLATFORM=windows`. See the gallery section below -- and note the
reason is NOT "a second WebGL context", which was measured and killed.

Before it: 3765 on branch `ketcher-overrule`, after the Ketcher overrule
and the conformer round trip: +24 for intercepting Ketcher's duplicated
controls and +17 for "Use in 2D Editor", four of those seventeen added
after it was reported broken on a bridged cage, plus +4 for the Atom
Inspector bounds check found in the same report, over the 3720 below.

Before it: 3720 on branch `Fix-A`, after the navigation-audit work: the
calculator-presentation fixes, the periodic table merge, the waiting
indicator, the section merge, the trajectory player, the palette
vocabulary and the documentation sweep. +107 over the 3613 it started
from, and every one of those a guard -- the last 18 being the
doc-currency check widening from 6 of the repo's markdown files to 15.

**THE 3-8 MINUTE BAND WAS UNDERSTATED and the spread is real.** Measured
across eight full runs of essentially the same tree on this machine:
361, 365, 367, 389, 389, 416, 490, 534, 554, 568 seconds -- and one that
blew a ten-minute wall at 89%. Do not read a slow run as a hang without
sampling; do not read a fast one as a speed-up either.

The single slowest test is deliberate and says so:
`test_a_calculators_result_lands_in_its_own_section` runs all 49 registry
calculators (~35 s warm, ~76 s in a full run, against a next-slowest of
14 s) because it is the only thing standing between a category merge and
a calculator whose button is in one section while its answer is in
another. Its cost lives in a module-scoped fixture so it is paid once and
is attributed to setup rather than hidden in a test body.

Before it: 3613 on the merge of the mmCIF element-symbol/ligand-copy/
protonation work (measured 2026-08-09, 5m25s -- the number that mattered
then, and not either side's: that branch alone gave 3611 against the 3570
it started from, and master's assembly-gate work contributed the last 2).
Before that: 3501 on clean master at `77ad231` after the conformer
de-duplication and calculator-routing work, 3446 at `14e5d08`, 3350 after
the crystallography work, 3236 before that, 3155 before the
polarity/lattice-energy work, 3081 before the substance-perception work,
3019 before the Ketcher pool-id merge, and 2788 before the
presentation-layer Phase 0-8 work.

The 3501 -> 3570 step is a worked example of the warning below: nothing
in this file recorded the assembly work's 69 tests, and a count taken
against 3501 would have read as 69 tests missing.

**THE FIGURE DRIFTS AND THIS LIST IS THE EVIDENCE.** The 3350 entry was
stale by 96 tests before anybody noticed, because a count is only
refreshed when somebody happens to take one. Treat a mismatch as "the
number is old" and re-measure before treating it as "something is
missing" -- and take that measurement on a CLEAN checkout, never a
working tree, which is a mistake this file has already recorded once.

**That figure is
from the DESELECTED form below, not the command above** -- run it bare and
the same tree reports one FAILURE, from the network test explained next.

**One test fails against the network, not against the code.**
`test_pubchem_name_round_trips_back_through_opsin` returns `HTTP 400` from
NCBI and does so on trees predating the work that was running when it was
first seen -- confirmed by stashing. Deselect it when you need a clean signal:

```bash
uv run --no-sync python -u -m pytest -q --deselect tests/test_naming_providers.py::test_pubchem_name_round_trips_back_through_opsin
```

Take the count on a **clean tree**. The main checkout often carries
work-in-progress tests, and a figure measured there is inflated -- which has
already produced one wrong edit to this file.

The suite also needs the optional extras installed, or ~40 tests fail on
missing imports and it looks like something is badly broken when nothing is:

```bash
uv sync --extra ai --extra network --extra openbabel
```

(Not `--all-extras`: that pulls in `docking`, whose `vina` wheel builds from
source and needs Boost. The reference environment does not have it.)

### The suite used to hang — fixed, kept here as history

This is no longer something to work around. It is recorded because the cause
took three attempts to identify and the failure mode was invisible.

**`QtWebEngineProcess.exe` instances accumulated and were never torn down.**
Every `QWebEngineView` a test constructs spawns Chromium helper processes, and
nothing disposed of them between tests. A hung run was caught with **91 alive**;
a measured baseline reached **116**, plateauing near 88, with the Python
process at **14 seconds of CPU** while wall clock passed 40 minutes — blocked,
not working. They pile up until something (handles, memory, a port) gives out,
always around the webview-heavy tests at roughly 30%.

They ARE reaped when pytest exits, so a post-mortem finds zero and looks
healthy. **The count only means anything sampled DURING a run.**

The fix is the autouse `dispose_web_engine_views` fixture in
`tests/conftest.py` — read its docstring before changing anything there, since
two plausible-looking implementations of it crash. Measured across two full
runs after the fix: peak **6** processes, mostly 0–1, against 116 before.

**Three wrong explanations were believed before the right one** — recorded so
a fourth does not get invented:

1. A bad shell wait-loop (`until grep -q "passed|failed"`, which never matched
   because `-q` buffers). Wrong, and accepting it cost a second 40-minute hang
   the same day.
2. The `pytest.exe` console-script shim under `uv run` spawning an extra
   nested process. Plausible, written into this file as near-fact, and also
   wrong — the module form hung the very next run. The shim was correlation.
3. While fixing it: that tearing pages down mid-load caused the teardown
   crash, so `view.stop()` was the cure. Removing `stop()` did not reproduce
   the crash in 8 runs. The actual cause was
   `sendPostedEvents(None, DeferredDelete)` draining every pending deferred
   delete in the process, including ones other tests had queued on
   already-collected objects. It is now flushed per view.

If a run ever stalls again, sample before assuming it is slow:

```bash
powershell "(Get-CimInstance Win32_Process -Filter \"Name='QtWebEngineProcess.exe'\" | Measure-Object).Count"
```

### A test that builds a panel must destroy it before the next one runs

Same family as the webview leak above, different object, and it fails much
louder. A test that constructs an unparented widget and walks away leaves it
with no owner, so Python destroys it at whatever arbitrary later moment the
collector happens to run -- inside an unrelated test, from within Qt's own
event dispatch. The result is a **Windows access violation**, and it surfaces
in whichever test happens to be pumping events at the time (any test of an
event-driven panel must, since `EventBus.publish` is a *queued* Qt signal and
nothing has been delivered when `waitForDone()` returns).

Measured on `tests/test_batch_panel.py`: **3 of 3 full runs of the file
crashed**, while running only some subsets of it passed -- because whether it
fires depends on when the collector happened to run. That "sometimes"
is exactly what makes it read as flakiness rather than as a bug in the test.

The fix is to destroy each widget deterministically and flush **that
widget's** deferred delete:

```python
widget.setParent(None)
widget.deleteLater()
QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)
```

Per widget, never `sendPostedEvents(None, DeferredDelete)` -- the global form
drains every pending deferred delete in the process, including ones other
test files left queued, which is the same double-free the webview fixture
already documents.

**Do this per file. There is no global version of it, and the attempt to
build one is recorded below as a warning.** The autouse
`flush_deferred_deletes` in `tests/conftest.py` handles only the
`deleteLater()` half -- it stops a backlog accumulating, and does NOT
destroy widgets a test walks away from.
`tests/test_qt_object_disposal.py` fails if it regresses.

#### How the ketcher crash was found, and the two things that were wrong about it

Recorded because the version of this section written before it was solved
named the wrong mechanism, and reasoning from that mechanism produced a fix
that measurably did not work.

The symptom: `test_ketcher_editor_backend.py` died with an access violation
at ~30% of a full run, on 3 runs and then not on the next 6, with CI green
throughout. **Do not trust green runs here** -- the corrected fix below was
verified against a deterministic reproduction, not against a streak.

What was wrong in the old account:

1. *"`processEvents()` drains the `DeferredDelete`."* It does not. Measured
   against this Qt build, a `DeferredDelete` posted at event-loop level 0 is
   delivered only when an actual event loop at that level returns, and
   `QApplication.processEvents()` never delivers one, however many times it
   is called. A pytest run never enters such a loop, so **every**
   `deleteLater()` in the suite sits in the process-wide queue until
   something spins a NESTED event loop -- which drains the entire backlog at
   once. QtWebEngine spins one internally while a page loads. That is the
   whole reason the victim is always a webview test: it is not that its
   `processEvents` pump is dangerous, it is that Chromium is the only thing
   in the suite that lights the fuse.
2. *"The widget's Python wrapper was already collected."* Not for the
   deleteLater'd object itself -- PySide keeps that wrapper alive until the
   event is delivered, so it is still weak-referenceable at session end,
   which is what made a census possible at all.

**Instrumentation found it in one run where bisection could not.** Wrapping
`QObject.deleteLater` to record its receiver weakly, then reporting which
receivers were still valid at each test boundary, named the offenders
exactly: 18 undelivered deletes, of which the 9 `IrViewWidget`s from
`test_ir_view_widget.py` (five files earlier) were the ones live while the
ketcher tests ran. Wrapping widget constructors the same way found the
second, larger half: **112 top-level widgets abandoned by 20 files**.

**Forcing the drain turns the heisenbug into a 12-second reproduction.** Run
one nested `QEventLoop` before each ketcher test and the crash is
deterministic:

```python
loop = QEventLoop(); QTimer.singleShot(0, loop.quit); loop.exec()
```

Measured with that lever, on `test_ir_view_widget.py` + the four files
between + `test_ketcher_editor_backend.py`:

| tree | result |
| --- | --- |
| before the fix | crash 5 / 5 |
| ketcher file alone (nothing queued) | pass |
| deferred deletes flushed only | crash 2 / 2, via `test_jobs_panel.py` |
| both fixtures | pass 8 / 8 |

That middle row looked like the whole story, and it was not.

#### THE WIDGET-DISPOSAL FIXTURE WAS REVERTED. Do not rebuild it blind.

`dispose_app_widgets` tracked every top-level widget of one of this app's
classes and destroyed each at teardown, per object. Against the base it was
developed on (`a85463f`) every number said it worked: the table above, plus
the leaked-widget census 112 -> 0 and 11 of 11 plain full runs green.

**It crashed the suite outright on master**, at `2dff778`, once the
help-window work had added many more MainWindow-with-viewer tests. Measured
by an interleaved A/B with a byte-identical file set, neutering the fixture
in place rather than deleting its test file:

| arm | full runs |
| --- | --- |
| both fixtures active | **access violation 8 / 8** |
| `dispose_app_widgets` neutered, flush still on | complete 8 / 8 |
| `flush_deferred_deletes` neutered, widgets still on | access violation 3 / 3 |

So it is that one fixture, on its own. The crash sites were
`test_main_window_docking_visualization.py` and
`test_ketcher_editor_backend.py` -- the MainWindow-plus-webview tests that
pump events, neither at fault. Re-ordering it to finalise after
`dispose_web_engine_views` did NOT help (still 5 of 5), so "a live view was
taken down as a child" is not the explanation, and why destroying an
abandoned widget synchronously at teardown faults here is **still unknown**.

**The original ketcher crash was open when this was written; it is now
solved -- skip to "SOLVED. The census named it" below before acting on
anything in this subsection.** Two further things
that were measured and do not fit together yet, for whoever picks this up:
master at `a093912` crashed 3 of 3 in a clean worktree with none of these
fixtures, while master at `2dff778` is green 8 of 8 in the main checkout
with none of them. Same suite, opposite results -- so before trusting ANY
result here, pin down the checkout and the commit, and never compare a run
in one against a run in the other.

Method note, learned the hard way: an early "before" measurement was taken
in a checkout that was being edited by hand at the time, so the two arms
were different trees and the comparison was worthless. Check `git status`
and file mtimes before believing an A/B.

#### A `lambda` that captures `self` in a `connect()` leaks the widget forever

Found while chasing the above, and it is a separate bug with a separate
fix. **PySide6 holds a connected plain callable STRONGLY and a QObject's
bound method weakly.** So this roots its widget for the life of the
process -- past refcounting AND past the cyclic collector, which cannot
see through the internal map the callable is kept in:

```python
button.clicked.connect(lambda _checked=False, d=definition: self._open(d))
```

Measured on a three-button minimal case: the self-capturing lambda leaks,
the same widget with `connect(self._go)` is freed by refcounting alone,
and a lambda capturing only plain data is also fine. It is `self` in the
closure that does it, not the lambda.

`PropertyPanel` was the worst of it -- one such connection per registered
calculator, 22 on a default registry -- so every panel ever built stayed
in memory for the session. Fixed, with the payload travelling on the
button as a Qt property and a bound method reading it back through
`sender()`. Same fix in `PeriodicTableDialog` (118 cells) and
`ExternalToolsDialog`.

`tests/test_qt_object_disposal.py` guards all of it, and deliberately
asserts the leak itself as well: if a future PySide6 stops leaking here,
that test fails and the workarounds can go.

#### The root of the cycles: `EventBus` now holds bound methods weakly

`EventBus.subscribe` used to store the handler in a plain list. A bound
method holds its object, so the bus owned every panel that ever subscribed
and the panel owned the bus -- a cycle nothing could break by reference
counting, leaving the whole graph to the cyclic collector.

Bound methods are held with `weakref.WeakMethod` now; everything else is
still held strongly, and that asymmetry is the load-bearing part. A lambda
usually has no other reference, so held weakly it would be collected the
instant `subscribe` returned and the subscription would silently never
fire -- worse than a leak, because nothing looks wrong. Measured when the
change was made: production code subscribes 38 bound methods and ZERO
lambdas, while the tests subscribe 74 lambdas.

Measured effect, per panel:

| | before | after |
| --- | --- | --- |
| `JobsPanel` | refcounting | refcounting |
| `DockingPanel` | needed the cyclic collector | **refcounting** |
| `PropertyPanel` | leaked outright | **refcounting** |

**It does NOT replace the teardown `gc.collect()`, and the numbers say so
plainly.** With weak handlers and no collect, late C++ destructions went
UP -- 138 before, 177 after -- because more objects are now destructible
at all rather than leaked. With both, 8, against 2352 destroyed inside
their own test. Keep both.

It also moved MainWindow, without fixing it: with weak handlers AND the
menu lambdas removed, the first window is destroyed cleanly and the
SECOND construction segfaults, 5/5. So destroying a MainWindow leaves
something process-global in a state the next one trips over. That is the
next thread to pull; the section below still applies until it is pulled.

#### What makes MainWindow destruction fault: the undo stack

Bisected against the real window, by disabling one piece at a time:

| window | destroyed |
| --- | --- |
| as built | **segfault 5/5** |
| `_new_molecule` suppressed (nothing ever pushed) | clean 3/3 |
| `_undo_stack.clear()` before dropping | clean 5/5 |
| `close()` alone, before `closeEvent` cleared the stack | **segfault** |

So commands sitting on the stack are what makes destruction fatal, and
clearing it first is what makes destruction safe. `closeEvent` now clears
it, which is why that line is there.

**The mechanism is NOT understood, and nothing here should pretend
otherwise.** A synthetic `QUndoCommand` on a `QUndoStack` destroys fine, so
does the real `AddMoleculeCommand` in a minimal harness, and so does a
hand-built `QMainWindow` carrying every panel, all three web views, custom
dock title bars, a status-bar widget, scroll areas, menus and a plugin
manager -- 3/3 each. It takes the whole real window. The commands are
necessary but not sufficient.

Ruled out along the way, each measured 3-5 times: `QWebEngineView`,
`MoleculeEditorWidget`, `MoleculeViewer3DWidget`, `MolStarViewerBackend`,
all three viewers together in a `QTabWidget`, `DockTitleBar`,
`CheckerStatusIndicator`, `QScrollArea` + `tabifyDockWidget`, menus,
`PluginManager`, and `_restore_window_state`.

##### The full fix IS shipped, once the collect was moved

The first attempt looked like a disaster and was reverted: menu lambdas
removed + this clear + the seven `test_main_window_*` files closing their
windows made the suite green 2/2 while late C++ destructions went from 8
to **1190**. The open question was "after `window.close()`, what still
references the window?"

**Nothing in the application does.** Listing the referrers of a window
still alive at teardown found only pytest: `SubRequest`, `TopRequest`,
`_pytest.python.Function`, and the fixture-name cache. Pytest holds every
fixture value for the whole item protocol, so a `gc.collect()` running in
`pytest_runtest_teardown` CANNOT collect a fixture-provided window -- and
the conftest hook had no `trylast`, so it ran before fixtures were even
finalised.

    collect in pytest_runtest_teardown, unordered   1190 late
    collect in pytest_runtest_teardown, trylast      135 late
    collect in pytest_runtest_logfinish                0 late

Zero, with 3587 destroyed inside their own test, the suite green 3/3, the
forced-drain reproduction 0/10, and the run slightly FASTER than before.

The trap worth remembering: a test that builds its window as a plain local
cannot tell the right hook from the wrong one, because the local is
released when the function returns either way. The guard in
`tests/test_qt_object_disposal.py` takes its window from a FIXTURE for
exactly that reason -- the first version of it did not, and the mutation
survived.

#### MainWindow's menu lambdas ARE fixed now (an earlier note said not to)

They were reverted once, with the note "the leak is load-bearing", because
removing them made the window collectable and destroying a MainWindow
crashed. Both halves of that are now solved and the fix is in:

- `closeEvent` empties the undo stack, which is what made destruction
  safe (see the section above it);
- the collect runs after the item protocol, so windows are collected at
  the right moment (see below).

Menu actions carry their payload on the `QAction` via `setData` and connect
bound methods that read it back through `sender()`. Two facts about Qt that
this depends on, measured rather than assumed, because the file previously
asserted the opposite of the first:

    menu.addAction(label, callable)     calls it with NO arguments,
                                        whatever its signature
    action.triggered.connect(callable)  passes `checked`

So a handler reached through `addAction` keeps its own defaults --
`_duplicate_molecule(molecule=None)` really does receive None -- and only
`toggled`/`triggered` connections have to take the bool.

Two measurement traps from the attempt that got reverted, both general:

- **A probe that prints "destroyed" after `del` + `gc.collect()` proves
  nothing.** It has to assert with a weakref that the object really died.
  Without that, a leaked window reads as a successful destruction, and a
  bisect across eight commits reported "destructible" everywhere while
  destroying nothing at all.
- **Reverting any ONE piece of the fix appeared to cure the crash.** It did
  not -- it just left one lambda still leaking, so nothing was destroyed.
  Any partial revert looks like a fix, which makes bisecting within the
  change actively misleading.

#### SOLVED. The census named it, and the fix is one line of timing.

Read this before acting on anything above it. The sections above are kept
as the record of how it was chased and several of their intermediate
conclusions were later reversed; the cause is now measured and the fix is
in `tests/conftest.py`.

**Census A (undelivered deletes) found nothing** -- 0 outstanding at every
test boundary and at session end. `flush_deferred_deletes` had already
closed that half completely, so every hypothesis built on the delete
backlog was chasing a queue that is empty.

**Census B (widgets alive at session end) measured the wrong population.**
It reported 65 live parentless panels, which looks damning and is
irrelevant: a widget still alive has never been destroyed, so it cannot be
the thing that faults. Those 65 are a LEAK, not a landmine.

**Census C, then D, found it.** Instrumenting `QObject.destroyed` -- the
only event that runs a C++ destructor -- and recording the test that was
running at that instant against the test that built the widget:

    destroyed inside their own test : 2003
    destroyed in a LATER test       : 138   <- the landmine, measured

138 from seven files, 104 of them `test_quantum_chemistry_panel.py`. (Do
NOT use a weakref callback for this, as census C did: it counts Python
wrappers, over-reports by an order of magnitude -- 1406 -- because a
wrapper collected after Qt already destroyed the C++ object is harmless.)

**Why they outlive their test.** `EventBus.subscribe` stores the BOUND
METHOD in `_handlers`, so the bus holds the panel and the panel holds the
bus. Reference counting cannot break a cycle; nothing is freed when the
test's locals go out of scope, and it waits for the cyclic collector,
which runs whenever it likes -- including inside Qt's event dispatch in an
unrelated test. Measured per class: `JobsPanel` (subscribes to nothing)
dies by refcounting, `DockingPanel` needs the cyclic collector,
`PropertyPanel` survives both and is a real leak.

**The fix is `gc.collect()` in a teardown hook, gated on `qapp`.** It
destroys nothing itself -- that distinction is the whole point, since
forcing destruction with `deleteLater()` has now crashed the suite twice
under two different implementations. It only chooses the MOMENT at which
Python does its own ordinary work, and a teardown hook is a moment with no
Qt event dispatch in progress.

| arm | late C++ destructions | full run |
| --- | --- | --- |
| before | 138 | 116 s |
| `gc.collect()` after every test | **0** | 326 s |
| `gc.collect()` only after `qapp` tests | **4** | 171 s |

The last row is what shipped. The four that remain are all inside
`test_quantum_chemistry_panel.py` itself; closing them costs another 155
seconds on every run, which is not worth it for four same-file
destructions when the crash being chased was cross-file.

Corroboration, given how unreliable crash-rate arms are here: the
forced-drain reproduction went **0 crashes in 10** with the fix, and three
plain full runs were green. Neither is proof on its own -- the whole
lesson below is that these arms move between batches -- which is why the
deterministic 138 -> 4 is the number to trust and to re-measure if this
ever comes back.

#### Confirmed again, independently, at the Structure Check work

The reverted fixture's central finding was re-derived from scratch by
somebody who had not yet connected it to this section, which is worth
recording because it means the result is real and not an artefact of how
`dispose_app_widgets` happened to be written.

Adding `tests/test_structure_check_panel.py` (which builds a MainWindow and
pumps events) gave **1 access violation in 5 full runs**, at
`test_a_quick_fix_lands_on_the_undo_stack`. That file inserts ~50 tests
ahead of the panel tests and so shifts collection timing; it does not
introduce anything new. Note `pytest-randomly` IS NOT INSTALLED here, so
file order is deterministic and adding a file is the only thing that
reorders anything.

Seven files build a MainWindow and abandon it -- `test_main_window_*.py`
(six of them) and `test_receptor_library_dialog.py`. Giving each the
per-file disposal recipe from the section above, so the abandoned windows
are destroyed deterministically at teardown, produced:

| arm | forced-drain subset |
| --- | --- |
| abandoned, as today | crash 3/3, then 0/10 on the same tree |
| explicitly disposed | **crash 6/6** |

So **destroying them is worse than leaving them**, which is exactly what
the `dispose_app_widgets` table already said and is now confirmed by a
second, differently-written implementation. Do not try this a third time.

The middle row is the other lesson: an unchanged tree gave 3/3 and then
0/10. The rate itself moves between batches, so **no A/B here is worth
anything below about n=10 per arm**, and a 3-run comparison -- which is
what most of the earlier work in this section used -- can say the opposite
of the truth.

The forced-drain lever from the ketcher section works on this crash too and
is the only reason any of the above could be measured at all:

```python
loop = QEventLoop(); QTimer.singleShot(0, loop.quit); loop.exec()
```

run as an autouse fixture before each test of the victim file.

One caveat worth knowing if you re-run that instrumentation: stacking BOTH
diagnostic plugins on top of the now-permanent fixtures double-wraps every
widget constructor and destabilised a run by itself (a `Fatal Python error:
Aborted` in `test_molstar_viewer_backend.py` that appears under no other
configuration). Run one census at a time.

### The suite must not touch the machine's real settings

`Settings` wraps `QSettings`, which on Windows is the real registry key a
shipped install uses. The autouse `isolated_settings` fixture redirects it to
an INI file under `tmp_path`; `tests/test_settings_isolation.py` fails if that
regresses.

Worth knowing because the previous version of that fixture **looked** correct
and half-worked. It called `QSettings.setDefaultFormat(IniFormat)` and gave
each test a unique org/app name — but `setDefaultFormat` does not affect the
`QSettings(organization, application)` constructor in practice, whatever the
docs say:

```python
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.defaultFormat()          # Format.IniFormat
QSettings("Org", "App").format()   # Format.NativeFormat  <- still the registry
```

So the real `OpenChemStudio` key stayed clean (the unique name did that much)
while every run deposited **84 junk keys** under `HKCU\Software`, one per
test, named after the test, permanent. Nothing in the suite output showed it.
Building the QSettings from an explicit file path avoids the format question
entirely.

If you touch that fixture, verify by counting, not by reading:

```bash
powershell "(Get-ChildItem 'HKCU:\Software' | Where-Object PSChildName -like 'OpenChemStudio-pytest-*' | Measure-Object).Count"
```

#### A FUNCTION-SCOPED AUTOUSE FIXTURE DOES NOT COVER A MODULE-SCOPED ONE

The isolation above is real and it had a hole underneath it for as long
as it has existed. `isolated_settings` is `autouse=True` and therefore
FUNCTION-scoped, and **pytest sets higher-scoped fixtures up first** -- so
a `scope="module"` fixture that builds a `Settings` or a `MainWindow` runs
while `QSettings` is still the real one. Five fixtures in this suite do:

    module   window       tests/test_right_dock_width.py
    module   window       tests/test_ketcher_overrule.py
    module   window       tests/test_conformers_without_the_3d_viewer.py
    module   main_window  tests/test_command_palette_vocabulary.py
    module   controls     tests/test_tooltip_coverage.py

**Measured on the real key, either side of ONE run of one file:**

    before   13:39:20   plugins/project_directory = .../tmpes9xm92a/none
    after    13:41:30   plugins/project_directory = .../tmpfk04ymjp/none

A live rewrite of the developer's own registry, pointing at a temp
directory that had already been deleted. Not junk keys under a scratch
name this time -- the real `OpenChemStudio` key, the one a shipped install
reads.

**`tests/test_settings_isolation.py` COULD NOT SEE IT, and the reason
generalises:** all three of its guards are function-scoped, so they always
ran INSIDE the patch and always found a clean INI. A guard for a
scope-ordering bug has to live at the scope where the bug happens; the
one that catches it now takes a deliberately `scope="module"` fixture and
asserts on `fileName()`, since a NativeFormat `QSettings` reports a
`\HKEY_CURRENT_USER\...` pseudo-path and that is the only thing telling
the two backends apart from inside the process.

`_isolated_settings_for_higher_scopes` is session-scoped and does the same
redirection. It does NOT replace the per-test fixture -- tests must still
not see each other's writes, and that one gives each its own file. This is
the floor underneath it.

#### The same rule, the same mistake, in the DATA root

`paths` documents `OPENCHEM_DATA_ROOT` as existing for "portable installs
and tests, which must never touch a developer's real data directory", and
six test files use it. `test_quantum_chemistry_service.py` did not -- its
`_make_service(tmp_path, provider)` **took `tmp_path` and never used it**
-- so every test in it created ORCA job directories under the real
per-user cache. A CI failure named the path outright:

    C:/Users/runneradmin/AppData/Local/OpenChemStudio/Cache/orca_job_4710091i

**"No leftovers" IS NOT EVIDENCE OF ISOLATION**, and that is the part
worth carrying. The directories were normally removed on the way out, so
counting them found nothing while every run was writing there; only a
cleanup that FAILED left proof. The guard therefore asserts where the
scratch directory is **while a job is still running**, not what is left
behind afterwards.

**And the first version of that guard passed for the wrong reason.** It
asserted the scratch was not under `paths.default_data_root()` -- the
OS-nominated location -- which sounds like the same claim and is not. A
machine with a CONFIGURED data root sends the scratch somewhere else
entirely (here `D:\OpenChemStudio-scratch`), so the assertion held while
the test wrote outside `tmp_path` exactly as before. It asserts
`is_relative_to(tmp_path)` now, with the no-space precondition asserted
too, since `space_free_cache_root()` legitimately relocates off a spaced
path. Caught only by neutering the fixture and seeing nothing fail.

### `resize()` does not resize a widget that was never shown, either

The same trap in a different Qt event, found a year of sessions later and
recorded beside its sibling because the first one did not generalise on
its own. Measured on a counting subclass of `_ElidingPushButton`:

    resize(400) then resize(420), never shown    0 resizeEvent calls
    show(), then the same two resizes           2

So a test that constructs a widget, resizes it and asserts on whatever
`resizeEvent` was supposed to do is asserting on the CONSTRUCTOR. Three
successive versions of one guard passed that way -- the last of them
counting `QPushButton.setText` calls, which is a genuinely sharp probe
aimed at code that never ran.

**A widget that was never shown runs almost none of its own code.** If a
test names an event handler, `show()` it first, or use
`conftest.painted()` where a paint is what matters.

Two smaller shapes of the same mistake, both from the same afternoon and
both caught only by mutation:

- A resize to the SAME size sends no `resizeEvent` at all. Two different
  widths, chosen so the rendered text is identical at both, is what makes
  "did it do redundant work" observable.
- `super().setText()` inside a widget method bypasses a subclass
  override, so a spy has to go on the Qt class rather than on a subclass
  of the widget under test.

### `repaint()` does not paint a widget that was never shown

A `paintEvent` test that constructs a widget, resizes it and calls
`repaint()` proves nothing. Measured on a counting subclass:

    repaint() on a never-shown widget    0 paintEvent calls
    update() + processEvents             0
    grab()                               1
    repaint() AFTER show()               1

So `widget.grab()` (or showing it first) is the only way to exercise the
painter. Four such tests existed and were green without ever running the
code they named -- including one then called
`test_highlighting_survives_a_repaint`, in which no repaint occurred. (That
name is history, not a test to go and find; all four were rewritten.)

**Use `conftest.painted()` / `conftest.ink()`**, which render into a
`QImage` and force the paint.

ASSERTING THAT SOMETHING WAS DRAWN IS HARDER THAN IT LOOKS, and two
plausible checks were tried and killed by mutation testing -- blanking a
widget's peak-drawing loop and seeing which tests noticed:

1. *"Some pixel is non-transparent."* Useless. Every one of these widgets
   fills an opaque background before its first mark, so alpha is set
   across all 30,000 sampled pixels even for an EMPTY spectrum.
2. *"More ink than the same widget with no data."* Still passes a blanked
   painter. Different data changes the axis range, so the tick labels
   alone move the count.

What works: **hold the axes fixed and vary only the content** -- two
spectra sharing their extreme shifts, differing by one peak in the
middle. Identical ticks and labels, so the ink difference can only be the
peak. That took the number of tests catching a blanked painter from 1
to 6.

`ink()` counts pixels differing from the modal (background) colour, not
transparent ones, for reason 1 above.

Tests that assert on child-widget structure rather than drawing -- e.g.
`test_structure_grid_widget.py` counting cells in a layout -- are not
affected and do not need any of this.

### The 3D viewer's JS console logs at DEBUG, and hid a daily error

`_LoggingPage.javaScriptConsoleMessage` forwards the page's console to
`logger.debug`, so **an exception thrown inside viewer.html is invisible in
normal use.** Raising it to WARNING for one measurement run found this on
**9 of 9 cold launches**:

    Uncaught TypeError: Cannot read properties of undefined (reading 'clear')

`::1` with no filename is how QtWebEngine reports a `runJavaScript` string,
which is what named the caller: Python, calling into the page before the
page existed. `MoleculeViewer3DWidget._refresh_view` runs during its own
construction, the starter molecule has no conformers, so it calls
`clear()` — and every load path in `Mol3DViewerBackend` queued behind
`loadFinished` while `clear()` and `set_style()` did not.

`clear()` merely threw. **`set_style()` was the damaging one**: a style
chosen before the page loads is silently dropped, leaving the viewer
rendering in the default representation with the combo box showing the one
the user picked. Both are queued now.

Two general points. **Raise a log level before concluding a page is fine** —
the error was thrown on every launch for months. And a `clear` that queues
must CANCEL the pending payloads rather than queue itself, or it is
overtaken on replay by the very structure it was meant to remove.

#### Ketcher had the same two holes, and a WIDER window than the viewer

`KetcherEditorBackend.set_render_option` and `trigger_toolbar_action` called
`runJavaScript` unguarded while `load_molblock` and `get_molblock` both
checked `_ketcher_ready`. Same bug class, and the exposure is larger rather
than smaller: **Ketcher's ready signal is a JS callback (`ketcherReady`), not
`loadFinished`**, so it fires after the page exists — the window in which a
call is reachable and silently dropped outlasts the one the 3D viewer had.

Neither is reachable at construction today (the View menu's toggles are never
`setChecked`, so nothing emits `toggled` until a user clicks), so this is the
same latent-ordering case `set_style` was, not a daily error.

**Queue state, drop gestures**, and say which a thing is. A render option is
state: dropped, the menu checkbox and the canvas disagree with nothing on
screen to say which is real, so it queues. A toolbar action is a transient
gesture: replayed, "Add/Remove explicit hydrogens" would mutate a structure
the user never saw (the canvas is empty until `_pending_molblock` replays a
moment later) and "3D Viewer" would open a dialog seconds after the click
that asked for it. It is dropped deliberately, and a test asserts the drop so
the asymmetry reads as a decision.

**The queue is a dict, and the test that proves it must use TWO different
options.** "The same option toggled twice applies once with the last value"
passes just as happily against a single `(name, value)` slot, which silently
discards every option but the most recent — and the menu offers two side by
side. Measured: the single-slot mutation kills only
`test_two_different_options_queued_before_ready_both_survive`, and nothing
else in the file notices.

**The two backends drain their queues in OPPOSITE orders, and both are
right.** 3Dmol's `loadMolblock` clears layers and surfaces, so
`Mol3DViewerBackend` replays those last. Ketcher's `setMolecule` does not
touch `render.options` — measured against the real bundle — so options go
first there and are laid out with the structure rather than re-rendering it
a frame later. Do not copy one ordering to the other on the strength of the
shape looking the same; check what the engine's own load actually resets.
For Ketcher it is a preference and not a constraint, which is worth stating
because inverting the replay breaks no test: a mutation of the order passed
all 14.

#### The render flakiness that could not be reproduced

Recorded so the next person does not re-derive the same non-conclusion.
Driving the app 5x per arm, the molecule path rendered a **black
half-height canvas** in 3 of 5 and then 4 of 5 runs — then 9 of 9 clean
with only a `console.log` added, and 5 of 5 clean after the fixes. **No
cause was established** and the fixes below are not claimed to be one.

The two things that DID come out of it are worth keeping:

- **A black canvas scores as heavily inked.** The `Count-Ink` helper counts
  any pixel darker than 240, so a failed render measured 94875 against a
  successful one's 3067 — 30x — and read as "drew". Measure a black
  fraction separately, or the metric reports failure as success.
- **The rate moves between batches**, exactly as the access-violation
  section already warns. Three arms of five said three different things.

### The formerly-flaky webview test

`tests/test_mol3d_viewer_backend.py::test_apply_visualization_sets_atom_colors`
used to fail intermittently on `QWebEngineView` readiness (sometimes a sibling
failed instead — the tell that the test was not what was wrong). It was the
leak above, caught where starting one more Chromium process was slow rather
than impossible.

It failed on the pre-fix baseline run and has passed **5 consecutive full runs**
since. If it flakes again, that is a genuinely new bug, not this one.

### The vendored nomenclature engine's own suite

`tests/vendor/` holds ~3,200 tests belonging to the vendored IUPAC namer. They
are **excluded from the default run** (`norecursedirs` in `pyproject.toml`)
because they take ~10 minutes against the main suite's 3, and they cover that
engine's internals rather than our integration with it.

Run them whenever you change anything under `src/openchem/vendor/`:

```bash
export JAVA_HOME="/d/Random Programs/OpenChemStudio_Data/jre/jdk-21.0.12+8-jre"
export PATH="$JAVA_HOME/bin:$PATH"
uv run --no-sync python -u -m pytest tests/vendor -q > /tmp/vendor.log 2>&1; tail -4 /tmp/vendor.log
```

Expect `3209 passed, 0 skipped` (~10 min).

**`JAVA_HOME` AND `PATH`, and they are not the same requirement.** Setting
only PATH gives `3193 passed, 16 skipped` -- which is the figure this file
carried for a long time, then "corrected" to blame an `ImportError` on
`py2opsin`. That attribution was wrong, and measuring it rather than
reasoning about it is what showed the difference:

    py2opsin imports fine, java on PATH   3193 passed, 16 skipped
    JAVA_HOME set as well                 3209 passed, 0 skipped

All 16 live in `tests/vendor/iupac_namer/test_tautomer_alignment.py`, whose
`_java_available()` reads the JAVA_HOME **environment variable** and does not
look at PATH at all. CI sets JAVA_HOME as a side effect of its setup-java
step, which is why CI saw 3209 and a PATH-only local run never could.

Finding them took mapping the `s` characters in pytest's `-q` progress output
back onto `--collect-only` order; `-rs` on the whole suite is another ten
minutes, and the skip reasons are not in a `-q` log.

PATH is still needed on its own: py2opsin shells out to a bare `java`, and
pytest does not inherit the managed Temurin the app injects per-subprocess
(`naming_providers._java_on_path`). Without PATH you get a bare
`FileNotFoundError` naming neither Java nor OPSIN.

## RESONANCE: four things measured before the Lewis diagram was built

`tests/test_resonance_gate.py` is the gate, kept as assertions. The idea
it rests on is that a delocalised bond still has a localised sigma
component, so only the excess is delocalised:

    localised pairs on a bond = MINIMUM order across resonance structures
    delocalised electrons     = (kekulised total - localised) x 2

**THE TOTAL MUST COME FROM A KEKULISED COPY.** Summed over the AROMATIC
form each bond counts 1.5, and naphthalene reports 11 delocalised
electrons against a textbook 10 -- small enough to read as a rounding
wobble and a whole electron wrong.

**`KEKULE_ALL` ALONE.** `ALLOW_CHARGE_SEPARATION` looks like the fix for
the five-membered aromatics and is not: pyrrole and furan are unchanged
at zero, and AMIDE gains two delocalised electrons from a
charge-separated contributor a Lewis structure has no business drawing.

**HYPERVALENCY IS NOT VISIBLE IN RDKit's VALENCE LIST.**
`GetValenceList(16)` is `[2, 4, 6]`, so sulfur(VI) is a perfectly normal
valence and sulfate goes undetected. Count the octet instead --
`2 x (bonds + lone pairs) > 8` -- which flags sulfate, phosphate, SF6,
sulfite, DMSO and phosphine oxide, and correctly leaves a
charge-separated perchlorate alone, since that one obeys the octet
exactly. No element list to rot.

**FORMAL CHARGES DO MOVE BETWEEN CONTRIBUTORS, and a first probe said
otherwise.** It sampled anthracene, pentacene, porphine and the
hypervalent set -- all neutral, mostly symmetric, none able to show it.
Acetate moves its negative between the two oxygens, which is the whole
point of drawing it delocalised. Read charges from the INPUT molecule.

Cost is negligible and the enumeration is small: anthracene 4 structures,
pentacene 6, porphine 2, none reaching even 16, all under 2.3 ms. So the
fail-closed truncation path is headroom rather than a working limit --
and still has to exist, because "no input I tried hit it" is not "no
input can".

**A LONE-PAIR AROMATIC CANNOT BE COUNTED THIS WAY.** Pyrrole, furan and
thiophene have ONE Kekule structure, so the arithmetic says zero when the
answer is six -- two of those electrons come from a heteroatom lone pair
that sits in the ring, and the enumeration never moves it there. Those
rings are delocalised with an UNKNOWN count: never 0, which would be a
lie, and never a fabricated 6. Asserted as a defect, so a future RDKit
that fixes it fails the gate and the abstention can go.

## The naming benchmark

`benchmarks/naming/` is the regression check on naming quality — 181 molecules,
scored by OPSIN round-trip rather than string equality. It is the arbiter for
"is this naming engine better", and it has twice overturned a conclusion
reached without it.

Generate fresh predictions, then score them:

```bash
uv run --no-sync python - <<'PY'
import json
from pathlib import Path
from openchem.vendor.iupac_namer import name_smiles
rows = json.loads(Path("benchmarks/naming/corpus.json").read_text(encoding="utf-8"))
preds = []
for r in rows:
    try: preds.append(str(name_smiles(r["smiles"]) or ""))
    except Exception as e: preds.append(f"<ERROR {type(e).__name__}>")
Path("benchmarks/naming/predictions_check.json").write_text(
    json.dumps({"check": {"predictions": preds}}, indent=1), encoding="utf-8")
PY
uv run --no-sync python benchmarks/naming/score.py benchmarks/naming/predictions_check.json
```

Current: **181/181** (82 exact, 98 equivalent, 1 tautomer — metformin, which
counts as a success since the `tautomer` outcome class was added). If a
change under `src/openchem/vendor/` drops this, that
outranks any number of narrow tests it fixed.

`score.py` takes exactly one predictions file. The committed
`predictions_full.json` and `predictions_deterministic.json` were recorded
against the older 124-molecule corpus and will now be **refused** by the
length guard rather than silently mis-scored — that guard is deliberate, not a
bug. They are kept as the record of what the ML alternatives scored at the
time; compare them only against the corpus revision they were made for.

## Ketcher CAN report atom AND bond selection, with one trap

The 2D editor was assumed to expose nothing for selection -- its Python
backend has only `load_molblock`, `set_render_option`,
`trigger_toolbar_action` and `get_molblock`. That is a fact about **our
wrapper**, not about Ketcher, and reading the wrapper is what made it look
impossible.

Probing the real vendored build (load `resources/ketcher/dist/index.html`
in a bare `QWebEngineView` and evaluate JS -- far faster than driving the
app) found:

- `ketcher.subscribe(name, handler)` is a **switch** that accepts only
  `'change'` and `'libraryUpdate'`. This is the dead end that makes
  selection look unavailable.
- `editor.subscribe` is a DIFFERENT method and does exist.
- `editor.event` carries ~30 events including **`selectionChange`**, plus
  `click`/`mousedown`/`mousemove` added at runtime by `domEventSetup` --
  so the live object has more than the `this.event = {...}` literal in the
  bundle shows.
- `editor.selection()` reads the current selection synchronously and
  returns `null` when nothing is selected. `editor.selection({atoms:[1]})`
  sets it and dispatches the event, which is how to test this without
  synthesising canvas clicks.
- **Bonds work identically**: `editor.selection({bonds:[0]})` round-trips
  as `{bonds: [0]}`. The selection object carries ONLY the keys with
  something in them -- a bond click has no `atoms` key at all -- so a
  handler must check both rather than assume one shape.
- **A SELECTION REPORTS POOL IDS, NOT MOLFILE POSITIONS.** This was
  previously recorded here as "Ketcher's bond ids are RDKit's bond
  indices... no translation table is needed, and one would be a place for
  a silent off-by-one to live". That is wrong, and the section below is
  the correction. The verification behind it was real but was performed on
  a freshly LOADED molblock -- the one state in which a pool has never had
  anything removed from it and the two agree by coincidence.

**THE TRAP: `selectionChange` hands your handler `undefined`.** It is a
`PipelineSubscription`, which feeds each handler the PREVIOUS handler's
RETURN VALUE rather than the original payload. Ketcher registers its own
handler first and that one returns nothing, so anything subscribed
afterwards receives `undefined` forever. Measured: a probe handler saw
`typeof sel === 'undefined'` on every dispatch while the event itself was
firing correctly, which reads exactly like "the event does not work".

`change` does NOT behave this way -- it is a plain `Subscription` -- so the
two look interchangeable and are not.

The fix is one line: ignore the argument and call
`ketcherInstance.editor.selection()` inside the handler.

#### A POOL ID IS NOT A MOLFILE POSITION, and a fresh load hides it

Reported from the running app: drawing a benzene and clicking a ring vertex
answered **"Atom 9 is in the 3D structure but not in the structure as drawn
-- the report covers heavy atoms and treats hydrogens as implicit. Pick a
heavy atom."** A second vertex gave atom 11. Benzene as drawn has six atoms,
and the molecule really was C6H6.

`Pool` extends `Map` and hands out ids from a counter that only ever
increments -- `add` and `newId` both `return this.nextId++` (read in the
bundle, then measured). **An id is a permanent identity handle and a freed
one is never reused**, while the molfile is positional and RDKit numbers its
atoms by reading it in order. The two agree only until something is deleted.

Reproduced through Ketcher's own API in about 20 seconds: draw two rings,
select the first and press Delete, and the surviving six-atom ring carries
pool ids **6..11** against a molfile of six atoms numbered 1..6. Every
vertex was off by six; clicking two of them sends 8 and 10, which is exactly
the report.

    molfile position  0  1  2  3  4   5
    what was sent     6  7  8  9  10  11     atoms AND bonds, both

**Bonds had the identical offset and were the worse half.** A wrong bond
index usually stays in range, so no guard fires and the panel silently
describes a DIFFERENT bond. The atom side was only ever visible because
`_atom_is_in_report` happened to catch it and say something.

Two reasons this shipped, both worth knowing:

- **A fresh `setMolecule` rebuilds the pool from zero.** Every probe that
  established the old claim loaded a molblock and read the ids straight
  back, so all of them saw a dense pool. **Any check of an index space has
  to run against an EDITED structure, never a freshly loaded one.**
- **A full erase resets it too**, so "draw, clear the canvas, draw again"
  looks fine. It takes a PARTIAL deletion -- which is the ordinary case,
  not the exotic one.

**It is NOT the vite 6 rebuild** (`001bd63`), which was the first
suspicion. The previous bundle, restored with `git archive 2768ee8`, gives a
byte-identical verdict: 6/6 atoms and 6/6 bonds wrong. This is Ketcher's
data model, and the bug is as old as the selection feature.

The fix is `molfilePosition()` in `tools/ketcher-host/src/main.jsx`, which
translates before the value crosses the bridge -- so Python's contract stays
"this is an RDKit index" and the one place that knows Ketcher exists is the
one place that knows about pools.

**INSERTION ORDER, NEVER SORTED, and this is the trap inside the fix.**
`indexOf` on `Array.from(pool.keys())` looks interchangeable with sorting the
ids, and is not. Undo re-inserts a deleted atom under its ORIGINAL id at the
END of the Map. Measured on a C-N-O-F-S-P chain with the carbon deleted and
restored:

    pool insertion order   [1, 2, 3, 4, 5, 0]
    molfile atom order      N  O  F  S  P  C     <- follows insertion order
    sorted by id           [0, 1, 2, 3, 4, 5]    <- wrong in all 6 positions

Bonds behave the same way and the case is sharper, because a bond pool can
be out of numeric order without any atom being: the same edit left bond ids
`[0, 4, 1, 2, 3]`, and RDKit's bond order matched that exactly, checked pair
by pair. A sorted implementation produces perfectly plausible indices and is
wrong, which is why `test_a_selection_is_never_forwarded_as_a_raw_ketcher_id`
asserts the absence of a `.sort(` by name.

Two guards, deliberately split. `tests/test_ketcher_editor_backend.py::`
`test_a_selection_arrives_as_a_molfile_position_not_a_ketcher_pool_id`
builds the real two-ring-minus-one state against the real bundle and asserts
what Python receives -- it must, since a stale dist leaves the app broken
with every Python test green. It **asserts its own setup** (pool ids really
are `[6..11]`) first, because if the Delete hotkey ever stops erasing, the
pool stays dense and the test would pass while testing nothing. Verified by
running it against the vite 5 bundle: fails, `assert [6,...] == [0,...]`.
The cheap half is a source check in `test_ketcher_bundle_is_current.py`,
confirmed to catch both a raw-id regression and a sorted one.

**`runJavaScript` on this Qt build returns PRIMITIVES ONLY.** Numbers and
strings arrive intact; an array or a plain object arrives as `''`,
indistinguishable from a script that returned nothing. This cost the first
probe run entirely -- every result read as empty and looked like Ketcher
failing rather than marshalling failing. Wrap anything structural in
`JSON.stringify`; `_run_js_json` in the test file does.

**THE 3D VIEWER AND A REPORT DO NOT SHARE AN INDEX SPACE**, and the
mismatch is a crash rather than a wrong answer. A conformer carries
EXPLICIT hydrogens; the structure as drawn has implicit ones. Ethanol is 3
atoms in a report and 9 in the viewer, so clicking a hydrogen in 3D sends
index 3-8 -- past the end. `GetBondBetweenAtoms(1, 5)` raises
`RuntimeError: Range Error` inside a Qt signal handler.

The heavy atoms agree ONLY because `AddHs` appends, so indices 0..n-1 line
up and nothing warns about the rest. That is why a live check that clicked
only heavy atoms found nothing, and why the bug was found by asking what a
hydrogen click would do rather than by hitting one. Anything wiring a
viewer click to a structure index needs the same bounds check;
`_atom_is_in_report` is the one in the inspector.

**3Dmol, by contrast, reports ATOMS ONLY.** Its `setClickable` callback
receives an atom, and bonds drawn in stick mode are not separately
selectable -- a click near one resolves to the nearest atom. So the 3D
viewer names a bond by its two atoms: the inspector takes two clicks and
resolves the bond between them, which uses only what the library provides.
That is deliberately NOT built on the viewer's existing multi-atom
selection, which drives distance measurement -- sharing it would make one
gesture mean two things depending on a mode nobody set.

Editing `tools/ketcher-host/src/main.jsx` requires `npm run build` in that
directory for anything to change; `resources/ketcher/dist/` is build
output. node and npm are installed, and a build takes about a minute
(measured 54 s and 1m00 on two bond-selection rebuilds).

#### DRAWING ON KETCHER'S CANVAS: the transform, and where it is safe

The lone-pair overlay draws on top of the editor without touching it.
Everything it rests on is in `tests/test_ketcher_viewport_transform.py`,
which is the gate kept as assertions; the parts worth knowing before
building anything else that draws there:

**`render.ps()` and `obj2view()` DO NOT EXIST on this build.** `page2obj`
is the only mapping exposed and it runs backwards. Inverting it at two
probe points gives a forward map accurate to **under a pixel**, and it
tracks zoom exactly because Ketcher zooms by changing the SVG viewBox and
`page2obj` already accounts for that:

    a = page2obj(0,0);  b = page2obj(100,100)
    scale = 100 / (b.x - a.x);  offset = -a.x * scale
    screen = pp * scale + offset

Better than deriving it from `microModeScale`, `zoom` and the viewBox by
hand, because it cannot drift when Ketcher changes how any of those work.
`devicePixelRatio` is deliberately absent: both sides are CSS pixels, so
display scaling cancels rather than being corrected.

**`ketcher.setZoom` DOES NOTHING.** It returns cleanly, leaves
`options.zoom` at 1 and moves no atom. `editor.zoom()` is the call that
works. Two gate arms reported a comfortable zero-pixel error against a
viewport that had never changed before this was noticed -- assert the
drawing MOVED before believing any accuracy number.

**Nothing is announced.** `zoomChanged` is in `editor.event` and does not
fire for a real zoom; Ketcher does not pan by scrolling either (its
client area has no overflow), so there is no scroll event. Both are
viewBox changes and both show up only in the derived affine. Comparing it
costs 0.009 ms against a 16 ms frame, so the overlay WATCHES on an
animation frame rather than subscribing.

**Work in MODEL SPACE and pan/zoom become free.** Ketcher's viewport
transform is scale + translate with NO rotation, so a label box is
axis-aligned in model units exactly as on screen. Put every computed
thing in model units under one `<g>`, and a viewport change rewrites one
transform attribute and touches no dot -- measured, slot identity is
unchanged across zoom 1 -> 1.8 -> 0.55 -> 1 on six fixtures. A guarantee
by construction rather than a tolerance.

**A LABEL'S HYDROGENS HANG OFF ONE SIDE, and which side varies.** Ketcher
anchors the element symbol on the atom and puts the hydrogens left or
right depending on the bonds and on conventions of its own -- water is
written H2O and ammonia NH3, opposite sides, neither with a bond to go
on. Measured as offsets from the atom in bond lengths:

    methanol  O   symbol -0.13..0.13   H  at +0.12..+0.35   (right)
    water     O   symbol -0.13..0.13   H  at -0.57..-0.33   (left)
    ammonia   N   symbol -0.12..0.12   H3 at +0.11..+0.52   (right)
    ammonium  N   the '+' reaches      +0.81
    methyl    C   H3 at -0.57..-0.13                        (left)

A box half the text wide and centred on the atom therefore under-covers
whichever side they took, and the lone-pair slot radius (0.33) sits
inside methanol's +0.35 -- so a dot was drawn straight through the H of
"OH". Reach the FULL text width on BOTH sides instead: a deliberate
over-estimate that needs no knowledge of Ketcher's side-picking, which
would be a special case that rots.

**AN OBSTACLE ERROR IS THE ONE CLASS A CHECKER CANNOT SEE.**
`chem/electron_layout.py` judges what the page drew rather than
re-implementing it, which catches a great deal -- but it is handed the
same label box the page used, so both agreed the dot was clear. Every
test passed, including the one whose whole job is to catch a dot inside a
label. It took looking at the screen. A judge grades placement against
the rules it is GIVEN.

#### AND IT HAPPENED AGAIN IN THE OWN-SVG RENDERER: Qt ignores `dominant-baseline`

The full Lewis structure (`chem/lewis_svg.py`, shown in a `QSvgWidget`)
is a second renderer with the same checker, and it reproduced the
finding above almost exactly -- the box was right, the page drew
somewhere else, and both agreed.

**Qt's SVG renderer silently ignores `dominant-baseline`, and ignores
`dy` too.** Measured, with and without the attribute giving
byte-identical output:

    plain                      ink 84..97   centre -9.5 from the anchor
    dominant-baseline=central  ink 84..97   IDENTICAL
    dy="0.35em"                ink 84..97   IDENTICAL
    dy="6.3"                   ink 84..97   IDENTICAL
    y shifted +6.3             ink 90..103  moved

So **only `x` and `y` move a glyph**. The needed shift is exactly half
the font size, glyph-independent, checked at 12/18/24/36 px.

At production scale the atom's label ink ran **74..87 against a checker
box of 78.6..101.4** -- the glyph poking 4.6 px out of the top while the
bottom 14 px of the box held nothing.

**Writing the shift into `y` costs nothing in a browser, and that was
measured rather than reasoned.** In Chromium, via `getBBox` on an inline
SVG, `dominant-baseline="central"` shifts a text element by **+6.00 px at
font-size 18 = +0.333 em**, which is `(ascent - descent)/2` for Arial. So
`y + 1/3 em` with no attribute is the same placement a compliant renderer
gives, and the exported SVG stays right.

Two method notes from that measurement, both already in this file in
other forms and both paid for again:

- **`runJavaScript` cannot return a Promise**, so the obvious probe
  (draw the SVG to a canvas via `Image.onload`, resolve the ink box)
  came back empty for every variant and read as "nothing rendered".
  Inline the SVG in the DOM and return a `JSON.stringify` synchronously.
- **Sampling a column through the atom does not isolate its label** -- it
  catches the lone-pair dots as well, and measured a 13-px "O" as 35 px
  tall. Render twice, once with the atom text stripped, and difference.

#### A REFUSED ANALYSIS MUST NOT BE HANDED TO A `QSvgWidget`, OR CLAIM A BUDGET

Two more from the same feature, both found by driving the app with every
test green, and both about what a REFUSAL looks like rather than what an
answer looks like.

**`QSvgWidget` scales its viewBox to fill the pane.** The renderer is
total and answers a refusal with a card carrying the reason, in a
200x60 viewBox -- fitted into the dialog that became ~37 px text with
both ends clipped, and read as a broken window rather than as a message.
The status line already carries the same words at a normal size, so the
view is hidden instead. **A message is not a picture; do not render one
through an image widget that fits to its box.**

**A refused diagram has no atoms, so every accounting term is zero and
the budget "balances".** The details panel was therefore reporting a
closed electron budget for a molecule the analysis had explicitly
declined to analyse. A number that agrees with itself about nothing is
worse than no number, because it reads as a result -- the same shape as
the `0` that iron(III) reported for its lone pairs before `Unknown`
existed. It says "not applicable - nothing was analysed" now.

#### A BRANCH CAN BE SHIPPED, DOCUMENTED, AND NEVER ONCE RUN

`lewis_builder` fails closed when the resonance enumeration truncates,
which is invariant 7 of its plan. Mutating that branch unreachable
**survived the entire suite**: nothing comes near `maxStructs=256` --
the gate's own measurement records pentacene at 6 -- so no fixture ever
entered it. The plan named it, the code had it, the docstring explained
it, and it had never executed.

**Reach such a branch by moving the THRESHOLD, not by hunting an input.**
`monkeypatch.setattr(builder, "MAX_RESONANCE_STRUCTURES", 2)` makes
benzene truncate in milliseconds; a molecule genuinely large enough to
truncate is also slow enough that nobody keeps the fixture (the hunt for
one was still running after 400 s and was abandoned). The existing "small
and fast on hard systems" test is now explicitly its CONTROL -- without
it a cap of 2 would satisfy the new guard while making every aromatic
molecule in the app abstain.

**A guard that SKIPS itself under its own mutation scores as neither
caught nor survived.**
`test_abstentions_are_printed_verbatim_with_their_subject` called
`pytest.skip` when nothing abstained, so removing the expanded-octet
abstention turned the guard into a skip. The only reason it was noticed
is that the harness compares the arm's test COUNT against the control's
and reported `INVALID (134 of 135 ran)`. A harness that only greps for
failures would have called that a survivor and sent somebody looking at
the wrong code. **Assert the setup; never skip on it.**

#### KETCHER'S MOLBLOCK IS NOT IN ANGSTROM, and nothing said so

Anything that takes `getMolfile` output and treats it as a measurement
has to restore the scale first. Measured against the real bundle:
cyclohexane loaded with C-C at **1.5301 A** comes back at **1.0702**, a
uniform **x0.6994** on every bond. Ketcher normalises bond lengths to its
own unit on load and writes that out.

**Harmless for as long as the canvas only ever held a LAYOUT**, which is
why it went unnoticed for the life of the project -- a 2D depiction's
coordinates are arbitrary units and nothing reads them as distances. The
moment the canvas holds a GEOMETRY (the rotation mode, the adopted
conformer) it is a 30% error in every bond length.

**It hides from almost every check.** A uniform scale preserves the atom
order, the bond orders, the formal charges, the CIP labels, the
fingerprint, and the SIGN of the oriented volume. Only a LENGTH or an
ENERGY sees one. That is why `RotateStructureCommand` asserts MMFF energy
as a separate invariant, and a mutation confirms it is the sole guard
that catches a unimodular shear -- the other plausible wrong matrix,
which has det exactly 1 and so preserves chirality too.

`ChemistryEngine.rescale_like` fits the factor by least squares over
every pairwise distance and returns the RESIDUAL, which is the thing that
says the motion was rigid at all. Three ways to not be a rotation, each
blind to the others:

    a reflection   preserves every distance   only stereochemistry sees it
    a shear        det exactly 1              only the distances see it
    a scale        preserves both of those    only a length or energy does

The corollary that bit separately: **a zero-distance drag cannot be
detected by comparing molblock TEXT.** The editor's copy is at Ketcher's
scale, so the incoming string differs from the model's on every drag
including the ones that moved nothing -- a check that looks obviously
correct and is never true. `RotateStructureCommand.moved` answers on the
geometry, after the rescale.

#### A KETCHER TOOLBAR ACTION CAN FIRE `change` WITHOUT CHANGING ANYTHING

And this app turned that into an `EditStructureCommand`, which cleared
the conformer set. Measured in the running app -- import, generate
conformers, press *Calculate CIP (Stereo Descriptors)*:

    conformers 4 -> 0,  canonical SMILES IDENTICAL either side

So a read-only annotation destroyed the geometry it was annotating.
Layout and Clean Up have the same shape, as does dragging an atom.

`_invalidate_stale_conformers` now compares canonical SMILES, which is
the same discriminator `MoleculeEditorWidget._on_molecule_changed`
already uses and for the same reason: **a coordinate change is not a
structure change.** Constitution AND stereochemistry, so flipping a wedge
still clears -- a conformer of the R enantiomer is not a conformer of the
S one, and anything comparing formulas or heavy-atom graphs would call
that edit a no-op.

#### CALCULATED ANNOTATION STATE: the category that was missing

Reported as "a bug with at least the R/S label. If a molecule is changed
while the label is turned on, it won't update ... I'm assuming all the
other 2d display functions have this bug". Half right, and the useful
half is WHICH half. Four classes, and the rule for placing a new one is
**does this value derive from the current molecular graph and get drawn
attached to it?**

    render option state       Ketcher's       re-rendered from the flag;
    carbonExplicitly,                         nothing to do on an edit
    showValence, stereo flags
    calculated annotation     OURS            MUST be recomputed when the
    CIP labels, lone pairs                    graph changes
    structural model state    the undo stack  becomes model state
    Aromatize, Layout, H
    snapshot view state       the dialog      frozen deliberately, and
    Full Lewis                                says so

The application had no third row, so CIP was implemented through the
STRUCTURAL-EDIT path (the section directly above) and the lone pairs as a
one-off. **Both went stale on the one route nothing covered**: the user
drawing on the canvas. Measured -- the four render options are fine
(checked either side of a real edit), Oxidation States is fine (its panel
is re-fed on every `MoleculeChanged`), Full Lewis is a documented
snapshot, and exactly two things were broken.

**THE LONE PAIRS WERE THE WORSE OF THE TWO and nobody had reported them.**
`_publish_electron_overlay` had exactly two call sites, `set_molecule` and
`set_electron_mode`, and an own edit reaches neither -- `_on_editor_edited`
updates `_synced_smiles` before `_on_molecule_changed` can compare, so it
returns early every time. The counts are keyed on MOLFILE POSITION, so
after a deletion the dots are not stale, they are **on the wrong atoms**.
`test_a_NEW_STRUCTURE_republishes_without_anyone_asking` covers the
`set_molecule` routes and its docstring lists them; the canvas edit is
simply not among them.

##### `ketcher.indigo.calculateCip` IS THE DOOR. The toolbar button is not.

The button was the only known integration point, and measuring found the
other one. Both routes, same fixture, same bundle:

    toolbar "Calculate CIP button"   1 change event, ASYNCHRONOUSLY
                                     (0 immediately after the click),
                                     Ketcher history undo 3 -> 4
    ketcher.indigo.calculateCip      0 change events, history 1 -> 1,
                                     and it does NOT touch the live struct

A `change` becomes an `EditStructureCommand`, so recomputing on every edit
through the button would leave a phantom undo step per edit -- and being
ASYNCHRONOUS, nothing can correlate the event with the call that caused
it, so no suppression could be written safely. A timer-bounded "armed
flag" was designed and rejected on exactly that: it can swallow a real
user edit that arrives inside the window, which is far worse than the
display bug it was fixing. The measurement removed the need for it.

`calculateCip` resolves to a **replacement Struct on its own dense pool**.
So the flow is compute, clear, copy the fields across BY POSITION,
`render.update(true)` -- which fires no `change` either, as the rotation
preview already relies on. End to end: **0 change events, no history
growth, no undo entry, and no recursion to guard against.**

##### AND THE FIRST VERSION COPIED BY POOL ID, WHICH IS THE SAME BUG AS THE SELECTION ONE

Shipped, and reported from the running app within the hour: the label
appeared "way to the left of the molecule", on a ring carbon nowhere near
the stereocentre, and **pressing Ctrl+Z fixed it** -- because undo reloads
through `setMolecule`, which rebuilds the pool dense. Measured after
erasing one atom:

    live pool          [1, 2, 3, 4, 5, 6]     the centre is id 3
    calculateCip's     [0, 1, 2, 3, 4, 5]     the centre is id 2
    where it landed    id 2                   a different atom

`calculateCip` round-trips through indigo, which parses its answer into a
pool starting at zero; the live pool only starts at zero until the first
deletion. Identical in cause to the selection bug this file already
records, one function along.

**THE "0 MISSING OVER THE FIXTURE" CHECK THAT LICENSED IT WAS
MEANINGLESS.** It counted ids present in the target -- and both pools have
the same SIZE, so every lookup succeeds and every one of them is off by
one. A membership check cannot see a shifted index space; only asking
WHICH ATOM the value landed on can.

**AND THE TEST SUITE COULD NOT SEE IT EITHER, BY EXACTLY THE DOCUMENTED
ROUTE.** The recompute-after-an-edit test erases the amine, which destroys
the stereocentre -- so no surviving atom label is left to misplace, and
the one surviving bond sits at an index the two pools happen to agree on.
Mutating the fix back to copy-by-id is caught by **one** test, the one
written afterwards; the other five CIP tests pass straight through it.
What it takes is an edit leaving a centre STANDING while making the pool
non-dense, and the guard asserts its own setup (`pool == [1..6]`) so a
dense pool cannot make it vacuous.

The rule this file already states was simply not applied: **any check of
an index space has to run against an EDITED structure, never a freshly
loaded one.** Both the probe and the first test used a fresh load.

**CLEAR BEFORE COPYING, ALWAYS.** A centre that stops being a
stereocentre keeps its old `cip` otherwise. Measured: delete the amine
from `C/C=C/[C@@H](N)CC` and the canvas still reads `(S)` -- an
answer-shaped lie, worse than an obviously missing label, and the variant
a user cannot detect. Clear-then-recompute leaves `(E)` alone, correctly.

**TWO RACE GUARDS, AND THEY CATCH DIFFERENT THINGS.** The calculation is
a promise, so an answer is in flight for a few frames. A GENERATION
counter covers a newer refresh or a `clear` issued meanwhile -- without
it, switching the display off is undone by the answer landing a moment
later, intermittently, which reads as a flaky toggle rather than a race.
A STRUCT IDENTITY check covers a `setMolecule` landing meanwhile, which
rebuilds the pool from zero and would have one molecule's descriptors
copied onto another's atoms by id. Both are mutated in
`tests/test_ketcher_editor_backend.py`; each is caught by one test.

##### A GENERIC "NOTHING CHANGED" PREDICATE WAS DESIGNED, THEN KILLED

The first plan suppressed any editor change altering neither canonical
SMILES nor coordinates. It is unsound and the counterexample is concrete:
`set_structure_from_molblock` stores `Chem.MolToMolBlock(mol)`, which
KEKULIZES, so **Aromatize** yields identical canonical SMILES and
identical coordinates while genuinely changing the drawing -- it would
have been suppressed outright, leaving the canvas aromatic and the model
never told. A wedge drawn on a non-stereogenic bond is a second case.
**A predicate that must enumerate every user-editable property to be
correct is not a safe escape hatch**, and the honest fallback if the good
route had not existed was to accept the extra undo entry.

**AND THE MOLFILE HEADER CARRIES A TIMESTAMP** -- `-INDIGO-08172603362D`,
to the minute -- so comparing `getMolfile` text across a minute boundary
reports a difference that is not one. Two reads with nothing in between
are byte-identical; two reads either side of :00 are not. That produced
one wrong reading of the probe before it was checked.

##### THE BUNDLE GUARD COVERED ONLY THE BRIDGE NAMES

`test_ketcher_bundle_is_current.py` parametrises over `bridgeObject.*` --
what JS calls on Python -- and nothing covered the globals Python calls on
JS. `openchemRotation` and `openchemElectrons` had both shipped uncovered;
`openchemCip` made it three, and a forgotten rebuild would have left the
feature silently absent with every test green. Guarded in two halves, and
the pairing is the point: a source scan proves the NAME reached the
bundle, not that the functions hanging off it did, so it is fail-open
alone. `test_the_cip_api_the_page_exposes_is_the_one_python_calls` asks
the real page.

#### KETCHER KEEPS 3D COORDINATES, including through an edit

Measured, because the whole "show the conformer's real shape in the 2D
editor" feature is unreachable if it does not, and because the failure
would have been silent and compounding: `main.jsx` forwards every canvas
change as `structureEdited(ketcher.getMolfile())`, which becomes an
`EditStructureCommand`, and that command CLEARS the conformer set. So a
Ketcher that flattened z would mean

    adopt a 3D structure -> click anything -> molblock flattened to z = 0
                                              AND conformers = []

one click destroying both the view and the geometry behind it.

It does not. `tests/test_ketcher_holds_3d_coordinates.py`, against the
real vendored bundle:

    xy pairwise distance ratio    0.7993 .. 0.7993   spread 1.0000
    3D pairwise distance ratio    0.6943 .. 0.6944   spread 1.0001
    z spread, cyclohexane chair   0.9832 A in -> 0.6828 A out
    after deleting an atom (6 -> 5)                  0.6828 A

So Ketcher applies **one uniform 3D scale** and nothing else -- no
re-layout, no flattening, and z is scaled by the same factor as x and y.
Bond lengths and angles survive exactly.

**A non-zero z is not the same as an intact geometry**, and the test that
only checks z would pass against an anisotropic scale that silently
changes every bond length. Assert that all pairwise 3D distances share
ONE ratio.

**Two scale factors from two different molecules are not evidence of
anisotropy.** 0.6943 and 0.7993 above look like a discrepancy and are
not: Ketcher normalises to its own bond length per structure, so an
aromatic molecule and cyclohexane get different factors. 0.9832 x 0.6943
= 0.6826, which is the 0.6828 measured. Nearly wrote up a bug that was
not there.

#### The bundle was rebuilt on vite 6, and what that cost

The toolchain moved from vite 5.4.21 to 6.4.3 to clear six dependabot
alerts, and the dist was regenerated on it. Worth knowing before the next
bundler bump:

**It costs almost nothing, and the obvious estimate is wrong by two
orders of magnitude.** Measured, `git count-objects -vH` before and after
the commit plus a `gc`:

    size-pack  15.27 MiB  ->  15.59 MiB      +0.32 MB

against a rewritten 34 MB JS file. Reasoning from FILE SIZE predicted
~35 MB and talked this rebuild out of happening once; the pack barely
moved because **minification is disabled here** (a TDZ bug in
ketcher-core's circular imports, see the config) so the bundle is
line-structured text that deltas against its predecessor almost
perfectly. Git even records the assets as renames-with-changes rather
than new blobs. Only the CSS was byte-identical
(`index-DaFekdiN.css`); all three JS chunks were replaced.

Measure the pack, not the file, before refusing a rebuild on size.

**No security depended on it.** All four vite/esbuild advisories are
DEV-SERVER issues -- `server.fs.deny` bypass, launch-editor NTLM, `.map`
path traversal, dev-server CORS -- and this project has no dev server:
`package.json` declares exactly one script, `build`. The output bundle
was never affected. The alerts are cleared by the LOCKFILE, so rebuilding
was a choice about keeping artifact and toolchain in step, not a fix.

`brace-expansion`, `uuid` and `nanoid` are pinned through npm `overrides`
because they arrive transitively (via `dpdm`, `vite-plugin-top-level-await`
and `postcss`) and their own CVEs are not dev-server-only.

**The bundle guard cannot tell you a rebuild WORKS.**
`test_ketcher_bundle_is_current.py` checks that each bridge name appears
as a string in the bundle -- it catches a forgotten rebuild, not a broken
one. After any toolchain change, exercise the paths that depend on module
init order, which is exactly what a bundler changes:

    npm run build                                    28 s on vite 6
    pytest tests/test_ketcher_bundle_is_current.py   names present
    pytest tests/test_ketcher_editor_backend.py      8 pass, real QtWebEngine
    a live selection probe                           see below

Selection is the one to check by hand, because it is the piece this file
already documents as fragile (the `PipelineSubscription` trap) and no
test covers it firing end to end. Drive it through Ketcher's own API
rather than synthesising canvas clicks:

```python
backend._page.runJavaScript("window.ketcher.editor.selection({atoms:[1]}); 1")
backend._page.runJavaScript("window.ketcher.editor.selection({bonds:[1]}); 1")
```

Measured on the vite 6 bundle: `atomSelected -> [1]`, `bondSelected ->
[1]`. Verify the build in a scratch outDir first (`npx vite build --outDir
...`) and repoint `_DIST_INDEX` with a one-line pytest plugin -- that
proves the toolchain before `emptyOutDir: true` deletes a working dist.

**Forgetting the rebuild is silent** -- the tests pass, the app starts, and
the feature is simply absent. `tests/test_ketcher_bundle_is_current.py`
catches it: it extracts every `bridgeObject.foo(` from the JSX and asserts
the name appears in the committed bundle, then that a `_Bridge` method of
that name exists to receive it. Verified by simulating the mistake -- adding
a call without rebuilding fails with the method named and the fix printed.

**It is a string check, not a rebuild-and-diff, and that was measured
rather than assumed.** The build IS byte-for-byte reproducible on one
machine (snapshot the dist, rebuild, diff: 5 files, zero differences, git
clean). But CI is Linux on a different node, and reproducibility across
toolchains is a much stronger claim -- one byte from a minifier would fail
every PR, and a check that cries wolf gets deleted. Bridge method names
cannot be minified (they are properties of the object Qt injects), so they
fingerprint the build for free and with no platform sensitivity. It needs
no node in CI, and `tests.yml` runs bare `pytest`, so it was picked up
without touching the workflow.

Reproducibility confirmed a second time, and with it something that saves a
rebuild: **a COMMENT-ONLY edit to `main.jsx` does not stale the dist.**
Comments do not survive the build even though minification is off -- a
distinctive phrase added to a comment appears 0 times in the 35 MB bundle --
so rewording one and rebuilding produced a byte-identical asset, same
content hash (`ea091b8d...`, `index-E55nh8EI.js`). Rebuild for a code
change; a comment is free.

**Building the dist in CI instead was considered and rejected**, with
numbers: the whole `.git` is 40 MB, only 10 MB of it large blobs, and the
dist has been rebuilt 3 times in the project's life. Moving the build out
would cost node in CI, a build step on every fresh clone, and 19 tests that
construct `KetcherEditorBackend` (which raises `FileNotFoundError` without
a dist) -- to save single-digit megabytes. Git also records the rebuilds as
99% renames, so successive versions barely cost anything.

## SHAPE-VALUED RESULTS DRAW THEMSELVES, and what that took to make honest

"Can our own dipole moment calculator resemble Marvins too, with a 3d
model?" It can, and the per-atom family already did -- the Calculator
Inspector has always drawn charges and LogP contributions on a 3D model.
What was missing was results that are one geometric OBJECT: the dipole
vector, the steric cone, the principal axes. `ReportResult.spatial`
carries them now (producer-declared `ArrowAnnotation` / `ConeAnnotation`
/ `AxesAnnotation`, validated fail-closed by `valid_spatial_annotation`),
`viewer.html` draws them, and `SpatialResultDialog` is the Marvin-style
popup. Verified against Marvin's own cis-1,2-dichloroethene screenshot:
same molecule, same charge family, 1.90 D against their 1.81, arrow
pointing the same way.

Five things measured on the way, each the kind that reads fine wrong:

- **The direction oracle runs on the RENDERED endpoints, never the
  annotation.** A producer sign bug and a renderer sign bug cancel in any
  annotation-level check, and the screenshot looks perfect. The page
  mirrors the exact geometry it hands 3Dmol into `drawnShapes`; the HCl
  guard asserts the drawn arrow runs Cl -> H (mu = sum(q*r) points
  delta-minus to delta-plus, which is also what Marvin draws) and that
  reversing the vector reverses the endpoints.
- **A review bound can be chemically wrong.** The reviewed plan
  specified a cone half-angle bound of 90 degrees; Tolman's own table has
  P(tBu)3 at a FULL angle of 182 -- half-angle 91. The validator's
  ceiling is 180, with a guard asserting 91 is accepted, because a
  validator that refuses real measurements is worse than none.
- **The steric cone only exists when its frame is displayable.**
  `_ensemble` embeds its own conformers for a flat drawing, and those
  coordinates live in a frame no viewer holds -- a cone drawn from them
  would sit plausibly on the WRONG conformer. The annotation is attached
  only when the caller's own 3D conformer was used, and
  `geometry_source` now says which happened ("provided_conformer" vs
  "free_ligand_mmff" -- the latter used to be claimed unconditionally,
  which was wrong for the provided case).
- **The cone's length is the sweep's reach, not scalar salad.**
  `metal_distance_a + sphere_radius_a` looks like a cone length and is
  two unrelated numbers; the honest extent is the farthest vdW-sphere
  edge `_half_angles` measured to, and the guard asserts the two DIFFER
  on PPh3 so nobody swaps them back for tidiness.
- **Shapes are state with one deliberate difference from the
  visualization layer's machine**: a load DROPS pending shapes (their
  coordinates are in the previous conformer's frame), where a pending
  layer survives to replay. Both halves are guarded against the real
  page, including the shapes-for-the-inflight-load case.

The dipole arrow only exists when the magnitude survives the DISPLAYED
precision -- benzene's residual vector is float noise, and "Dipole: 0.00"
beside an arrow would be the panel disagreeing with itself. And the
drawn length is display scaling (half the longest interatomic span,
floored at 1 A) of a vector whose units are DEBYE -- the one unit
confusion the whole annotation contract exists to forbid.

### The gallery overlay: CONNECTED, and what the last wire cost

For a while this section said the machinery was built and nothing called
it -- `apply_grid_shapes` reached from no production code, because
`_request_overlay` only ever passed `SINGLE_VIEW_CELL` and `_refresh_view`
diverted into `_refresh_gallery()` first. It is wired now. Verified live:
six cells, six different dipoles (1.10, 1.18, 1.12, 1.11, 1.19, 3.68 D),
each recomputed for the conformer in that cell, on the FIRST render.

`_refresh_gallery` issues one request per populated cell and
`_on_spatial_annotations_ready` routes by `event.cell_index`. Two things
about that are worth keeping:

- **`enumerate(page)`, never `index - self._page_start`.** The invariant
  is `page[cell] <-> gridCells[cell]`, because `load_conformer_grid` maps
  its entries position-for-position onto the cells. The arithmetic agrees
  while `page` is a contiguous range; only one of them says why.
- **The value stays IN THE CELL.** The page already draws each arrow's
  own caption (`shapeLabel` takes the target viewer), so the status line
  keeps saying "Conformers 1-6 of 8". One line cannot honestly carry six
  values, and one of six would be worse than none.

#### THE ANSWER ARRIVES BEFORE THE CELLS DO, and that is the ordinary case

`loadGrid` resets `gridShapes` synchronously and then builds inside
`whenGridSized`, which polls every 25 ms and wants the height repeated
across two frames. The overlay recompute is ~5 ms. `drawCellShapes`
no-ops for a cell that does not exist yet and nothing replayed
afterwards, so **the first page of a gallery drew nothing at all** and
only a later redraw appeared to fix it. `loadGrid` now replays
`gridShapes` at the foot of its build callback.

**The three existing per-cell guards could not see this**, and the reason
generalises: `_grid_of_two` waits for `.cell-overlay` before applying
anything, so every test built on it exercises a grid that already exists.
A helper that waits past the window is how a whole window goes untested.

**TWO `loadGrid` CALLS BUILD TWICE.** `whenGridSized` closes over its own
poll state, so a second call while the first is waiting leaves BOTH
callbacks armed and both reach `buildGrid`. Harmless until the replay
existed; with it, the older callback rebuilds from ITS conformers and
then replays `gridShapes`, which by then holds the NEWER request's
payloads. A `gridGeneration` counter makes the superseded build return
early. It costs a whole `createViewerGrid` (91 ms at 4 cells, 175 at 12)
per page paged through, and `gridBuilds` exists as a diagnostic seam
because nothing else can observe it -- the superseded build is overtaken
microseconds later and never reaches a screenshot.

#### Two bugs that only the running app showed, with every test green

Both found by driving a real gallery after the unit and page guards were
all passing, which is the entire argument for doing it:

- **`clearAllGridShapes` removed the arrows and LEFT THEIR CAPTIONS**, so
  unticking "Show shapes" left "1.14 D" floating over a structure with
  nothing drawn on it. It had its own clearing loop calling
  `removeAllShapes()` and not `removeAllLabels()`. **The existing guard
  could not see it**: `_drawn_cell` reads `drawnGridShapes`, the page's
  own mirror, which that function emptied perfectly correctly. A mirror
  records intent; the labels are what is on the screen. It goes through
  `drawCellShapes` now -- one path for "make this cell show exactly
  `gridShapes[i]`", and clearing is that with nothing in it.
- **`_refresh_status` wrote the SINGLE VIEW's line over the gallery's.**
  Unticking the overlay turned "Conformers 7-8 of 8" into "Conformer 7/8
  - +0.62 kcal/mol" -- describing one of the pictures, in the wording of
  a mode that was not on screen. Every unit test read the label; none
  asked what the label was describing.

#### `_overlay_tokens` and `service.accepts` are EQUIVALENT, measured

Both are set from the same value in `request()` and cleared together in
`_drop_overlay_drawings`, and a cell the service has never seen answers
False either way. So a mutation deleting EITHER survives the whole file
and only deleting BOTH is caught. Kept as the widget's own record rather
than deleted -- recorded here so nobody re-derives it, and so nobody
writes a test claiming to guard one while really exercising the other.

The one case they catch that nothing else does is real: a second spatial
result re-requests every cell, and the job already in flight was computed
from FEWER reports, so landing late it would replace a complete overlay
with an incomplete one -- same molecule, same cell, same conformer.

#### The redundant clear that no test could kill

`_refresh_gallery` called `clear_all_grid_shapes()` after
`load_conformer_grid`, and a mutation deleting it survived everything.
Measured why: `load_conformer_grid` already drops `_pending_grid_shapes`
and the page's `loadGrid` already resets `gridShapes`, so the explicit
clear only removed shapes from the OLD cells, which were being discarded
anyway. Deleted. The rebuild's own reset is guarded against the real page
instead, which is where it actually happens.

#### `ViewerBackend` now declares the shape methods, with NO-OP defaults

`apply_shapes` was called unconditionally by the widget on an interface
that never declared it -- it worked because the one test file that
reached that path happened to define it on its fake. The shape methods
are declared now and default to doing nothing, which is the opposite of
every other method on that base and is deliberate: they are drawing calls
made on the widget's own state changes, so "this backend has nothing to
draw shapes on" is a correct answer to "clear the shapes", not a failure.

**`load_conformer_grid` IS DELIBERATELY NOT DECLARED.** The widget probes
it with `hasattr` to decide whether the gallery exists at all, so
declaring it would make every backend claim a gallery it cannot build,
Mol* included.

### The overlay: recompute in the displayed frame, never transform into it

The dialog was frame-safe because it loads the STORED conformer. The
main viewer shows display-ALIGNED copies, so the obvious next step was to
expose the rigid transform `align_conformers_for_display` computes and
throws away, and rotate each annotation by it. **Measurement retired that
before a line of it was written.** Recomputing the producer on the
DISPLAYED molblock gives an annotation already in the right frame:

    four real conformers of ethylmorphine, through display_molblocks
    the vector rotates with the frame, magnitude preserved
    to 1e-4 and NOT 1e-6 -- the molblock's four-decimal text format
    5.2 ms for all four

So the transform-composition bug class -- the one whose oracle this file
already records as backwards in the camera work -- never arises: there is
no matrix to get the wrong way round. It is also the better answer, since
each conformer genuinely has its own dipole (4.43, 5.53, 5.53, 5.19 D
across those four), which is why the overlay labels its value with the
conformer and the Properties panel keeps reporting the canonical one.

**A PROBE THAT SEEDS EVERY CONFORMER THE SAME READS AS CONFIRMATION.**
The first version used `EmbedMultipleConfs(randomSeed=0)`, which is the
trap `RDKitConformerProvider` documents -- four copies of one structure.
It reported "magnitudes identical, vectors unrotated", which is exactly
what a working transform-free path would look like if alignment were a
no-op. Four identical conformers of a flexible molecule is the tell.

**A RESULT DID NOT SAY WHAT IT WAS COMPUTED WITH.** The routing layer has
recorded which CONFORMER a calculator was handed since the
calculation-input work and never the SETTINGS, so any replay would have
silently used today's defaults -- a different calculation under the
original's label. `INPUT_PREFIX + "parameters"` closes it generically for
every result, JSON-safe scalars only (`Provenance.to_dict` puts them
straight into the saved project), and a value that cannot be persisted is
DROPPED rather than stringified: a `repr()` cannot be fed back to
`compute()`, so storing one turns "I cannot replay this" into something
that looks replayable. Origin resolves through `report_id ->
CalculatorRegistry`, audited over the live registry -- 49
registry-executable calculators, 17 producing reports, zero mismatches --
with the RELATIONSHIP pinned as the contract and the counts explicitly
not.

**A REJECTED RESULT MUST STILL RELEASE THE CELL, and ten green tests
missed it.** The overlay collapses rapid conformer stepping to one
running job plus one pending request per cell, and the widget called
`service.finished()` only on the path where it ACCEPTED the answer. Step
two conformers and the first answer arrives stale, is correctly rejected
-- and the cell stays "running" forever, so the queued request never
starts and the overlay never draws again. Found by driving the app:
conformer 3 showed no arrow and no value, permanently, while every unit
test passed. `finished` is a no-op for a token that is not the running
one, so it is called unconditionally now, before any rejection.

**AND THE FIRST FIX FOR IT WAS PARTIAL, WHICH IS WORSE THAN OBVIOUS.**
It was applied to the conformer check only, so switching MOLECULES
mid-flight returned earlier still and wedged the cell identically --
found in review, measured (`jobs_started` stuck at 1 with every later
request only becoming `pending`), and fixed by hoisting the release above
EVERY rejection. Every early return after it is a rejection and none of
them may skip it. This file's own warning applies: a partial revert, or a
partial fix, looks like a fix.

A method note from the same review: the first assertion written for it
(`running is None` after the discard) FAILED against correct code,
because the release immediately starts whatever was queued and the cell
is legitimately busy again. Assert the symptom -- that the new molecule's
work runs at all -- not an instantaneous internal state.

Measured on the collapse itself, scrubbing seven conformers as fast as
the event loop allows: **7 requests -> 2 jobs started**, 5 superseded,
never more than one pending, settling in 18 ms. No debouncing was added,
because the numbers did not ask for one.

## The bond and molecule reports, and what generalising cost

`AtomReport` was written with `AtomFact`/`FactCategory` deliberately free
of anything atom-specific, on the stated bet that bonds and molecules would
want the same shape. **The bet paid: they moved to `domain/report.py`
UNCHANGED**, `AtomReport` lost only its identity fields to a shared
`StructureReport`, and every existing import still works through aliases
(`AtomFact = Fact`, `AtomFactProvider = FactProvider`,
`AtomFactService = FactService`). The panel's whole rendering half --
sections, search, copy, links -- needed no change at all.

Three things measured while building them:

- **A 2D depiction has coordinates, and they are not measurements.** Every
  bond in a layout comes out about the same length whatever its order:
  aspirin's 2D C=O reads 1.5 "units" against a real 1.264 A. So the bond
  report emits NO length from a 2D conformer rather than a wrong one, and
  the molecule report says outright which kind of coordinates exist.
- **RDKit's strict rotatable-bond definition could not be reconstructed.**
  Excluding amides leaves aspirin at 3 against `CalcNumRotatableBonds`'s 2;
  excluding all conjugated bonds drops biphenyl's central bond, which RDKit
  DOES count. Two attempts, both wrong, so the bond report reports "single,
  acyclic, non-terminal" -- the thing it can stand behind -- and names the
  gap rather than shipping a "rotatable" verdict that contradicts the
  molecule's own descriptor.
- **BRICS bonds are a synthesis statement, not a stability one.** A bond
  BRICS would cut is one a known reaction class could FORM. It says nothing
  about strength, and the fact carries that.

Two mutations survived the first pass, and both were tests that could not
discriminate rather than code that was wrong:

- **A monocyclic molecule has as many bonds as atoms.** Aspirin is 13 and
  13, so swapping `atom_count` and `bond_count` was invisible. Assert
  counts on an ACYCLIC molecule.
- **Overlapping atom and bond indices hide which field is being read.** A
  fixture with `atom_indices=(0, 1)` and `bond_indices=(0,)` gives the same
  answer either way. Make them disjoint.

## A new panel needs a help topic, and nothing was checking

`HELP_TOPIC_BY_DOCK` in `app/main_window.py` maps a dock's object name to a
section anchor in `docs/`. Both guards in `tests/test_help.py` iterated
**over the map**, so a panel MISSING from it was invisible to them: its `?`
button opened help with nothing selected, and the suite stayed green.

The Atom Inspector and the Interactions panel both shipped that way and
were found by reading the map against the docks by hand during a
documentation sweep. `test_every_dock_the_window_builds_has_a_help_topic`
now goes the other direction and names the offending dock.

A documentation sweep is worth doing for the same reason: it found four
shipped features with no user-facing documentation at all, and an LED
section missing from `SCIENTIFIC_LIMITATIONS.md` -- the file that exists
precisely to say what the app cannot honestly tell you.

**CLAUDE.md itself had drifted badly.** 132 lines were a stale duplicate of
the four sections above them, reaching the OPPOSITE conclusions: an
all-caps "DO NOT 'FIX' MAINWINDOW'S MENU LAMBDAS. THE LEAK IS
LOAD-BEARING." sat directly below "MainWindow's menu lambdas ARE fixed
now". Anyone reading top-to-bottom hit the correct account and then a
shoutier contradiction of it. Check for this when adding to a long
troubleshooting file -- appending a corrected account does not remove the
old one:

```bash
rg -n "^#{2,5} " CLAUDE.md | awk -F': ' '{print $2}' | sort | uniq -d
```

## A DOC GUARD THAT CHECKS CITATIONS CANNOT CHECK CLAIMS

`tests/test_docs_are_current.py` was built to stop the docs rotting and it
works -- 170 cited paths and 26 cited test names, zero stale. It asks
whether a document cites something that EXISTS. **It cannot ask whether a
document's CLAIM is still true**, and four claims went stale underneath it:

    ROADMAP  "ensemble alignment ... needs its own panel"   the panel shipped
    ROADMAP  "reaction templates -- Deferred, still" (x3)   the namespace shipped
    ARCH     "hydrophobic contact detection is a real gap"  it shipped
    ARCH     "IUPAC Name withheld on a morphine derivative" does not reproduce

The third is the sharpest: **ROADMAP had ALREADY corrected that exact
claim** ("seven interaction types now"), so the two documents contradicted
each other outright and the one a reader trusts for implementation detail
was the wrong one. The second went stale in a paragraph whose own subject
is a previous correction of the same list.

`DEFERRALS` in that file is the fix, and the shape is the point:

- **Scope is ARCHITECTURE.md's Known TODOs only**, because it declares a
  closed `OPEN`/`DECISION`/`SETTLED` vocabulary and is therefore the one
  place deferral status is structured data. ROADMAP's `- [ ]` bullets are
  planning prose; parsing them would produce tests whose only purpose is
  proving a TODO still exists. Same instinct as `applies_to` being closed
  while `category` stayed a free string.
- **OPEN and DECISION both need an `unbuilt` predicate**, because a
  DECISION whose feature shipped anyway is stale even when its recorded
  reason still holds. Only DECISION additionally carries a `reason`, and
  only where the reason is countable -- "there is still no concrete fourth
  plugin" is `len(shipped plugins) < 4`; "the cause was never established"
  is not checkable by anything and says so.
- **Fail closed on BOTH sides.** The parse rejects an unknown marker
  (`**OPNE**`) rather than skipping it, and cross-checks the classified
  bullet count against a raw one. The mapping requires each claim
  substring to occur EXACTLY ONCE -- without that, rewording a claim
  silently detaches its predicate and the guard goes on passing, which is
  the fail-open hole the whole thing is written against.

Six mutations, each caught by the intended test: a claim made true, a new
unguarded bullet, a typo'd marker, a reworded claim, a duplicated claim,
and a deleted justification. **The one thing it cannot catch is a
predicate hardcoded to True**, which is written into the docstring as an
admitted limit rather than papered over with a second implementation.

Writing the guard immediately caught a flaw in its own first rule: it
demanded a written reason from every entry lacking a `reason` predicate,
including OPEN ones -- which have no recorded reason by definition, so it
was demanding an explanation for something the document never claimed.

## A blocklist of category NAMES rots; a declared capability does not

`chem/crystal_report.inapplicable_calculators` matched each calculator's
`category` against a hand-written set of thirteen names. Measured before
replacing it, and it had rotted in both directions at once:

    registered calculators                              49
    correctly listed as inapplicable to a crystal       22
    silently treated as APPLICABLE                      27
    blocked category names matching no live category     3 of 13

The 27 included IUPAC Name, Tautomers, Molecular Dynamics and NMR
Shifts. **It rotted for a structural reason, not a careless one.**
`CalculatorDefinition.category` is deliberately a free string -- its own
docstring says a new category "needs no code change, just a new
registration" -- so nothing ever brought anybody back to the list.

`CalculatorDefinition.applies_to` replaces it, and **the default is the
restrictive one**: `frozenset({MOLECULE})`. A calculator registered
without a thought is molecule-only, which is the answer that cannot be
wrong about a periodic solid; applying to a crystal is an opt-in
somebody had to mean. Unlike `category` and `tags` it is a CLOSED
vocabulary, because a typo would make a calculator apply to nothing and
look fine.

The answer today is 49 of 49 inapplicable, which is honest: the crystal
report computes its own facts and no molecular calculator claims one.

**`inapplicable_calculators` had a guard test and NO production
consumer.** It was computed and thrown away, so the refusal the module
docstring describes was never shown to anybody. The guard asserted
`len(names) > 10`, which passed comfortably on a list more than half
wrong -- a threshold assertion where a derived one belonged. The
replacement recomputes the expected set from the same declarations.

### A crystal in a project stores its CIF TEXT, not its parse

Following `MacromoleculeModel.structure_text`. The deciding reason is
not tidiness: **a reader improvement then reaches projects already
saved.** Reparse and an old project gains whatever `chem/cif.py` learned
since; store the parse and it is stuck with the reader that first read
it, `Crystal.unhandled` included.

`CrystalModel` therefore has **no `to_crystal()` method**, and the first
version that did was caught by
`test_the_crystal_domain_model_imports_no_chemistry_toolkit` -- `domain/`
may not import `openchem.chem`, and a deferred import inside a method is
still an import. Callers hold the chem layer already and call
`read_cif(model.cif_text)`.

Selection publishes **`CrystalSelected`, not `MoleculeSelected` with a
crystal uuid**. Every subscriber to the latter looks the uuid up in
`project.molecules`, finds nothing, and leaves its panel showing the
previous molecule beside a crystal's name -- the same index-space
confusion as a crystal click reaching the molecular measurement.

## The presentation layer, and four things measured while fixing it

The app's chemistry was correct and its presentation was not, which is a
different kind of bug and needs a different kind of evidence. Recorded
here because three of these four cost real time and two contradict what
the obvious approach would have been.

### `WrappedLabel` is load-bearing in one place and catastrophic in another

`ui/widgets/collapsible_section.py`'s `WrappedLabel` overrides
`minimumSizeHint`, `hasHeightForWidth` and the size policy so a wrapped
label reports its true height. Inside the property panel's scroll area
that is what stops the calculator buttons being squeezed to 13 px -- its
own docstring has the table.

Used for a **one-line status in a top-level row it is the opposite**, and
by a wide margin. Measured on a bare Qt reproduction at 900x950:

    WrappedLabel batch status   461 px tall, scroll area starts at y=478
    plain QLabel                 20 px tall, scroll area starts at y=37

`MinimumExpanding` makes the row claim the panel's vertical stretch, so a
third of the Properties panel was one line of transient status. The rule
is not "always use WrappedLabel" -- it is "use it where a label's true
height must survive a squeeze", and a status line is not that.

### A STYLE CHANGE RE-ARMS THE HEIGHT-FOR-WIDTH FLAG, and starved a section

Reported as the Lipophilicity section's three calculator buttons
rendering on top of one another. It is the truncation mechanism
`ExplicitHeightLabel` already documents, coming back through a door
that class did not cover -- so read its docstring first, then this.

`QLabel::changeEvent` answers **`StyleChange` and `FontChange`** by
calling the same `QLabelPrivate::updateLabel()` that `setText` does, and
that re-derives the size policy's height-for-width flag from the
word-wrap flag. `ExplicitHeightLabel` overrode `setText` and
`resizeEvent` and **not `changeEvent`**, so setting a style sheet on ANY
ancestor silently re-armed the flag on every wrapped label beneath it,
long after the last `setText`, with nothing on the label itself having
changed. Measured by logging each transition of the flag:

    '13 atoms, -0.4195 to 0.5437'   re-set hfw on event 100
                                              (QEvent::StyleChange)

From there the whole chain is height-for-width carrying again and
`QBoxLayout.setGeometry` substitutes the section's `heightForWidth` for
its minimum. Measured in the running app, aspirin, panel at 280 px:

    arm       section h   its minimum   its 3 buttons (min 26)
    before          145           192   15 / 15 / 14
    after           192           192   26 / 26 / 26

**It was never confined to one section** -- the same run re-armed the
flag on the alert rows, the pKa and NMR hints and the substance
classification. Lipophilicity is simply where a squeeze was visible.

**THE SYMPTOM CANNOT BE REPRODUCED OUT OF THE APP, and two tests that
tried both passed with the bug deliberately restored.** In a harness the
section's `heightForWidth` and its minimum come out EQUAL (418 and 418),
so the substitution has nothing to take away -- widening the panel,
shortening it, and registering the calculator buttons all failed to
starve anything. **The fifth time an out-of-app Qt harness has
disagreed with the running application about this panel.** The guard
that ships asserts the MECHANISM (the flag stays clear across a style
change, with a plain `QLabel` as the control proving the style change
was delivered at all); the symptom was verified by driving the app.

### AND THE SAME PANEL WAS CLIPPED SIDEWAYS, by its own row captions

The height work above is a different bug from this one and both are
real. Reported as the untouched Schedule 2 "Legitimate uses" line losing
the **last character of every visual line**, with the date-refusal
message riding on the same defect — `leave the field blank` rendering as
`leave the field bla`. Recoverable by scrolling right, which is exactly
why it read as cosmetic for so long.

    admet section minimum   272     widest caption 210, word wrap off
    scroll viewport         256     panel 280, less frame and scrollbar
    scroll content          272     max(viewport, minimum)
    every widget            +14 px past the right edge

**A `QLabel` WITH WORD WRAP OFF REPORTS ITS WHOLE TEXT AS ITS MINIMUM**,
`QFormLayout` sizes the label column to the widest of them, and
`setWidgetResizable` sizes the content to `max(viewport, minimum)`. So
ONE long descriptor name clipped every row in the panel — which is why
the symptom was uniform rather than confined to a bad row, and why
hunting the row that "looked wrong" would never have found it.

It is `_ElidingPushButton`'s bug one widget along. That class was written
when the widest thing in the panel was a BUTTON (content 287 against a
256 viewport); with buttons capped, the caption inherited the title.
`_ElidingLabel` is the same cure and wrapping is NOT an option —
one height-for-width widget in a section restores everything the three
parts above exist to prevent.

**THREE IMPLEMENTATIONS PASSED THE WHOLE PANEL SUITE WHILE VISIBLY
BREAKING THE APP.** Each was found by magnifying a screenshot, and the
first two are traps anybody reaching for the obvious fix will hit:

- **`QSizePolicy.Ignored` corrupts a FORM.** It is exactly what
  `_ElidingPushButton` uses and it is right there — but an ignored label
  no longer sizes the label column, so `QFormLayout` drew the value on
  top of the caption: `Aqu36ous Solubility (...`, which is "Aqueous
  Solubility" and "-3.68" in one rectangle. **All 98 panel tests passed
  with the two overlapping.**
- **Qt's size hints LATCH on elided text.** They measure the string
  currently set, which is the elided one, so once squeezed the caption
  reported the width of `...`, was given that, and could never grow back
  — three captions rendered as a bare `...` beside their values. Both
  hints derive from `full_text` now, which does not change when the
  painted string does.
- **`QFormLayout` COLLAPSES a label whose `sizeHint` does not fit**
  rather than clamping it at `minimumSizeHint`. Measured on a bare form
  290 px wide: `QRect(16, 2, 0, 14)` — zero width, against a stated
  minimum of 120. Capping the hint at a CONSTANT fixes that and buys the
  opposite defect, a caption frozen at 120 px on a 900 px panel. The cap
  is derived from the room available instead: 130 px at host 250, 660 and
  the full string at 900, no overlap anywhere.

**A CAPTION'S PAINTED TEXT MUST NOT LEAVE THE PANEL.** Three consumers
read it and all three were wrong — `as_text` (so "Copy all" exported
`Blood-Brain Barrier Permeant (heur...`), the instrumentation dump, and
a guard in `test_result_presentation.py` that the targeted test files
never reach. `_unelided_text` is the accessor; the rule is the one
`_without_glyphs` already follows on the value side.

**AND THE VALUE COLUMN WAS READ RAW UNTIL IT ELIDED TOO**, which is the
same rule arriving one column across. See "A FAILED DESCRIPTOR'S REASON
WAS ALSO ITS TOOLTIP" below: once the value label elides, `as_text`
reading `.text()` would export the short cell form in place of the
reason, so there are now two accessors — `_unelided_text` (what it says,
ignoring width) and `_exported_text` (what belongs on a clipboard). They
differ for exactly one case and folding them back together reinstates
the coupling this whole area exists to remove.

#### The oracle, and why the obvious one is disproven

`property_panel.rendered_overflow` is shipped code, for the reason the
instrumentation beside it already is. It maps every painted descendant
into the scroll viewport and reports what left it.

**`horizontalScrollBar().maximum() == 0` IS NOT AN ORACLE.** That
assertion has been in the suite since the wide-row work, it passes on
every platform, and it passed throughout this bug. The test asserting it
is renamed to `test_the_panel_has_no_horizontal_scrollbar` and says in
its own docstring that the absence of a scrollbar does not prove the
absence of clipping.

Three things the probe had to get right, each measured:

- **BOTH EDGES.** Left-edge clipping is on record in this panel —
  `"bb_permeant"`, `"unctional Groups"` from a run that had scrolled
  right.
- **`isVisibleTo`, not `isHidden` and not `isVisible`.** A widget in a
  COLLAPSED section has `isHidden() == False` and has never been laid
  out, so it carries a default geometry: 56 findings at "right 384 px"
  against a real overflow of 14. `isVisible()` is the opposite mistake
  this file already records — False for every child of an unshown window.
- **The intra-widget term is LABELS ONLY.** A `QPushButton`'s
  `contentsRect` is not its text rectangle, so the 80 px "Details..."
  button reports 40 px of phantom overflow under the test platform's
  wider font while rendering correctly for a user.

#### A FIXTURE'S CAPTIONS WERE TOO SHORT TO REPRODUCE ANYTHING

The strongest lesson here, and it is about the guard rather than the
code. The first version of the overflow oracle **passed with the entire
fix reverted**, because `_panel_with_a_long_result` captions its rows
"LogP", "TPSA", "Ring Count" — none wider than a third of the viewport,
so no arrangement of them can push content past its edge. The real
panel's widest is `Blood-Brain Barrier Permeant (heuristic)` at 210 px.

Same shape as the assembly corpus that was blind to a transposed matrix:
**a fixture is not "big enough" or "small", it is degenerate or not with
respect to a specific mutation.** Five arms, all caught only after the
guards were repaired, all running the full 20 tests:

    M1 minimumSizeHint cap removed         4 failed
    M2 form call site -> plain string      2 failed
    M3 sizeHint ceiling removed            1 failed
    M4 wide-row caption -> plain QLabel    1 failed
    M5 export uses painted text            1 failed

M4 needed a second repair for a different reason: **a spanning row has no
field column beside it**, so its overflow is `caption - viewport` rather
than `caption + field - viewport`. At one pixel over, reverting that
caption moved the content 290 -> 293 and the row's margins absorbed it
to within tolerance. The fixture asks for 40 px now.

**A GEOMETRY CLAIM ABOUT REAL FIXED TEXT IS A CLAIM ABOUT THE FONT.**
The suite runs `offscreen`, whose default font this file already records
as more than twice as wide as the one a user sees. Pinned at a fixed
width, the two-reported-strings test failed by 40 px on a panel that is
measurably clean in the app. It sizes the panel from its own content
instead; every font-independent claim is made with captions sized from
`QFontMetrics` against the real viewport.

Measured after, in the running app, all four states — empty panel, a
molecule, the screen, the refusal: content 256 against a 256 viewport,
**zero** rendered overflow, and the horizontal scrollbar gone (viewport
height 569 -> 581). Captions elide at the 280 px minimum and recover as
the dock widens — 2 of 3 full at 340, all three at 420.

### A FAILED DESCRIPTOR'S REASON WAS ALSO ITS TOOLTIP

Reported as a shape descriptor's message clipping mid-word at the panel
edge, on any molecule with no 3D conformer. The clip is the symptom; the
cause is that ONE FIELD WAS DOING TWO JOBS.

    if descriptor.cache_state.value == "failed":
        value_label.setText(descriptor.error or "Failed")
        value_label.setToolTip(descriptor.error or "")

So a producer had a single string with which to be both a table cell and
an explanation, and it cannot be both. Measured in the running app at
Segoe UI 9 -- the font a user gets, NOT `offscreen`'s, which is more than
twice as wide and would have made every number here look hopeless:

    panel width   caption   value cell
          280       116          120     <- the dock's own minimum
          420       116          230     <- its default

against a reason of 87 characters, and a pkasolver one of 344.

**AND THE ROW DID NOT MERELY OVERFLOW ITSELF.** A `QLabel` with word wrap
off reports its WHOLE TEXT as its minimum width, so this is the caption
bug of the section above, one column across. Measured on the ten shape
descriptors with no conformer, panel at 280:

    value label width         1164 px
    scroll viewport            256
    rendered_overflow           10 findings, right = 916

-- every row in the panel clipped at the right edge, not just the failed
ones. `_ElidingCaptionLabel` became `_ElidingLabel` and serves BOTH
columns, because a second class for the value side would have been a
second copy of every lesson that class already carries. Measured on a
bare form with one caption and one long value, the mechanism is unchanged
by the role: form minimum **1972 -> 268** px.

#### `error` KEEPS ITS MEANING; `error_summary` IS THE NEW CELL FORM

`domain/common.describe_failure(error, summary)` returns `(cell, hover)`
and is the ONE place that decides which string goes where -- the panel had
FOUR independent FAILED branches, each writing `error or "Failed"` by
hand, which is this repository's most repeated failure mode.

**TWO PLAIN FIELDS, NOT ONE WIDENED TYPE**, and the reason is the
degradation. `error` is still the FULL explanation and still a `str`, so
every producer that writes it and nothing else keeps exactly today's
behaviour. A `FailureMessage` value object in that field would have
rendered as a repr in four call sites and looked plausible doing it.
`test_a_producer_that_declares_no_summary_gets_exactly_the_old_behaviour`
is the guard.

**NO LENGTH CEILING ON THE SUMMARY, DELIBERATELY.** Eliding already
handles width and is measured; a cap would be a second mechanism for one
problem and a constant nobody could derive. `describe_failure` owns WHICH
string goes where and never grades one against the other -- the same line
`valid_total_declaration` draws, and
`test_the_summary_is_not_graded_against_its_reason` holds it.

#### A WIDE ROW IS NOT A CELL, and consolidating the four lost text

The panel has FOUR FAILED branches and only ONE of them is short of
room. The other three render into an `ExplicitHeightLabel` inside
`_add_wide_row` -- spanning both form columns, word wrap ON, stating its
own height so the value shows IN FULL. The reason is already entirely
visible there.

So routing all four through `describe_failure` and rendering its CELL
member was a regression, and it was written, tested green and nearly
shipped: the pkasolver row is 344 characters of install guidance, and it
would have become "pkasolver not configured" with the rest reachable only
by hovering. Deleting what a reader could already see, in the name of
fixing a clip somewhere else.

    _on_descriptor_computed   QFormLayout field, one line, 120-230 px
                              -> the CELL form
    _present_alert            _add_wide_row, wraps, full height
    _present_result           _add_wide_row
    _on_report_computed       _add_wide_row
                              -> the FULL reason, all three

`describe_failure` still supplies all four with the "Failed" default, so
the branches cannot drift on that; what differs is which MEMBER of the
pair each renders, and that is a property of the row it is rendering
into. **The function owns which string is which; the call site owns how
much room it has.**

`test_a_wide_row_keeps_the_whole_reason_while_a_value_cell_takes_the_summary`
asserts BOTH halves in one test, deliberately: "always use the summary"
satisfies the descriptor half and "never use it" satisfies the alert
half, so either alone is passed by the wrong rule. Mutated in both
directions, caught in both.

This is "reusing a command whose invariants do not apply is not reuse",
one layer down and in a presentation function rather than a command.

#### THREE STRINGS, NOT TWO, AND MY OWN FIX SHIPPED THE BUG AGAIN

`as_text` read `value_widget.text()` raw. That was safe only while no
value elided -- the moment the value column got the caption column's
treatment, "Copy all" exported `Needs a 3D conformer` where the sentence
saying what to press belongs. The identical leak the caption rule exists
to stop, reintroduced by fixing its neighbour, and **caught only because
the guard for it was written before the fix was believed**.

    painted      what fits the present width
    unelided     what it says, ignoring width      `_unelided_text`
    exported     what belongs on a clipboard       `_exported_text`

They differ for exactly one case and agree everywhere else. Folding them
back into one accessor is the ONE-FIELD-TWO-JOBS bug in miniature, which
is why they are two names rather than a fallback chain in one.

**`setText` CLEARS THE EXPORT OVERRIDE, and that is what makes staleness
impossible.** The value label is reused as a descriptor moves through its
states, so an override set on a failure is still attached when the row
later succeeds -- exporting a conformer instruction beside a perfectly
good number. Every branch calls `setText` first, so the reset is
automatic rather than a rule four call sites have to remember.

#### FIVE MUTATIONS, FIVE CAUGHT -- AND TWO ONLY AFTER THE GUARD EXISTED

    M1  eliding value label -> plain QLabel     the geometry oracle
    M2  as_text exports the cell form           the export guard
    M3  setText stops clearing the override     SURVIVED
    M4  the non-ASCII wording restored          the codepage guard
    M5  the producer stops declaring a summary  SURVIVED

**M3 AND M5 ARE THE ENTRY WORTH READING.** M3 -- a row that fails and
then succeeds goes on exporting the stale reason forever -- passed the
whole panel suite, the geometry guards and the presentation guards. M5 --
the provider stops attaching `error_summary` -- passed every guard in the
new file too, because those read the module CONSTANTS and checked they
relate. A constant existing is not a constant REACHING, which is this
file's own "shipped is not reachable" one layer down. Both guards were
written from the surviving arm and both then caught it.

`test_the_probe_can_see_a_failed_reason_widen_the_panel` is the control
for the geometry guard: it puts the shipped defect back -- a plain,
non-eliding `QLabel` carrying the same string -- and requires the oracle
to SAY SO. Without it the guard would pass against a panel with no
eliding value label at all, which is exactly how the caption oracle in
the section above once passed with its entire fix reverted.

#### `▸` RAISES ON cp1252 TOO, so the string was unprintable everywhere

`_NEEDS_CONFORMER_ERROR` carried an em dash and a U+25B8 triangle. The
report noted the em dash; the triangle is worse and measured
independently per codepage, because the obvious probe short-circuits
(`ch.encode("cp437"); ch.encode("cp850")` never reaches cp850 when cp437
raises, which produced one wrong reading of this very table):

    char                      cp1252   cp437   cp850
    A-ring, sup-2, degree         ok      ok      ok
    sup-3                         ok   RAISE      ok
    em dash                       ok   RAISE   RAISE
    triangle U+25B8            RAISE   RAISE   RAISE

So it was unprintable on EVERY Windows console codepage rather than only
the DOS ones. `>` is the separator `_PKA_NOT_INSTALLED_MESSAGE` already
uses for "Tools > External Tools".

**`test_every_line_is_ascii` IS WEAKER THAN ITS OWN DOCSTRING SAYS.**
That guard, in `tests/test_regulatory_calculator.py`, asserts against
cp1252 -- and its docstring
claims that stream "raises on a tick or an em-dash". It raises on the
tick; it does NOT raise on an em dash. The guard is real and its stated
reach is not.

**AND `DescriptorValue.error` HAD NO SWEEP COVERAGE AT ALL.**
`benchmarks/report_lines/sweep.py` instruments `report_adapter._split`,
so it enumerates the lines reaching `AlertResult.matched` and never
touches the `error` field -- which is exactly where the shipped non-ASCII
string was. Run over the real registry, the `matched` population is 499
distinct lines, 62 of them non-ASCII and **0 failing cp1252 or cp850**;
10 fail cp437, all of them the `Å³` in `surface_analysis.py:129`. A
blanket "must be pure ASCII" rule would therefore fail 62 legitimate
lines, so the rule the constraint actually implies is "encodes under all
three", and `tests/test_failure_messages.py` is the guard for the error
population the sweep cannot see.

**THE ONE REMAINING FINDING IS NOT FIXED AND SAYS SO.** `Å³` fails cp437
only -- the least likely of the three -- and cp437 has `²` but not `³`,
so the ASCII repair (`Å^3`) would leave line 129 inconsistent with the
five `Å²` lines directly above it. Recorded rather than changed, because
it alters user-visible units for the least common codepage.

#### DRIVEN AND MAGNIFIED, and for once nothing new was wrong

`OPENCHEM_DRIVE` with a `CCO` molecule and every section above `shape`
collapsed, cropped 3x. All ten rows read a complete `Needs a 3D
conformer` in red, no ellipsis and nothing past the panel edge, and the
in-app `dump` reports **0 rendered-overflow findings** at both the dock's
420 default and a squeezed window. At the 280 minimum the cell is 120 px
against a summary needing 118 -- it fits whole, by 2 px, and past that it
elides with the reason still in the tooltip.

**`{"do": "expand", "section": ...}` TAKES THE CATEGORY ID, AND `shape`
IS BELOW THE FOLD.** A first run expanded it correctly and photographed
nothing, because the section sits under eighteen others in
`_CATEGORY_ORDER` and the panel scrolls. Collapse the ones above it
rather than scrolling; a scroll position is one more thing to get right.

### 20 of 25 `AlertResult`s were never alerts

`AlertResult.matched` is a `list[str]`, and it became the generic line
carrier for anything that was not a single scalar -- `topology_analysis`
puts `"Szeged index: 12"` in it, `regulatory/calculator.py` documents
doing so deliberately. The panel rendered any non-empty `matched` as
`"N alert(s): "` + a comma-join, in `#c62828`.

Counted rather than estimated: **25 distinct `alert_id`s, of which only
`pains`, `brenk`, `mutagenicity_alerts`, `herg_risk_factors` and a
regulatory screen WITH findings are warnings.** So four fifths of the
app's results were painted as though the molecule were flagged, and an
elemental analysis read `8 alert(s): Formula: CHNO, Mass: 43.025, ...`.

The fix is `AlertResult.severity`, declared by the PRODUCER, defaulting to
INFO. Guessing from the id would have been a heuristic; the producer
knows. `Severity` already existed in `domain/structure_issue.py` and is
already rendered by the structure-check panel -- reused rather than
paralleled, which is this project's most repeatable mistake.

**An empty `matched` was rendered as a green "Clean" without checking
`cache_state` first.** Geometry with no 3D conformer returns FAILED
carrying "This calculation needs a 3D conformer", and the panel reported
success while discarding the message that said what to do. "Clean" is a
verdict and only a catalog is entitled to give one; a report with nothing
to say has cleared the molecule of nothing.

### `QFontMetrics.inFont()` does not answer "will this glyph render"

Needed for the status glyphs, since colour alone is invisible to a
colour-blind reader and is lost entirely in copied text. The obvious check
is wrong:

    inFont('✕') -> False     and it renders perfectly
    inFont('△') -> False     and it renders perfectly
    inFont('✓') -> False     and it renders perfectly

It asks about the one nominated font, not the fallback chain Qt actually
paints with. **Painting is the only honest test**, and "it drew some ink"
is not enough either, because a tofu box is ink.

The control is a Private Use Area codepoint, which no font assigns. It
turned out to render as **nothing at all** here, byte-identical to a
space -- not as tofu, which was the guess. That is asserted in
`test_the_status_glyphs_really_render` rather than assumed, so a platform
change that starts drawing tofu fails there naming the reason instead of
quietly weakening the test.

### The cp1252 rule reaches further than `matched`

**AND cp1252 IS THE WRONG CODEPAGE TO ASSERT AGAINST, which this file says
throughout and which is measurably too weak.** `sys.stdout.encoding` reports
cp1252 in a modern terminal, so a guard written against it looks right -- but
a Windows CONSOLE defaults to an OEM codepage, and those are STRICTER:

    character   cp1252   cp437   cp850   ascii
    em dash     ok       RAISES  RAISES  RAISES
    tick        RAISES   RAISES  RAISES  RAISES
    Angstrom    ok       ok      ok      RAISES

So an em dash passes a cp1252 assertion and still renders as a replacement
character on a real console. Found the hard way: a refusal message written
with one rendered as `�`, the guard for it asserted `encode("cp1252")`,
and **the mutation restoring the em dash SURVIVED**. `isascii()` is the bound
worth asserting for a result STRING; a units field may legitimately carry an
Angstrom, which is why the rows above are separated rather than merged into
one rule.


`regulatory/calculator.py` already records that result lines hit Windows
console streams and that a tick RAISES there -- three times in one
session. The status glyphs are non-ASCII, so they are produced at RENDER
time and stripped at every exit (`_without_glyphs`, used by the panel's
"Copy all"). A glyph is decoration: somebody pasting into a paper wants
`Pass`, not `✓ Pass`, and the word already carries what the glyph
duplicates on screen.

Hit immediately, in a scratchpad script that printed the panel back:
`UnicodeEncodeError: 'charmap' codec can't encode character '✕'`.

### Reusing a command whose invariants do not apply is not reuse

"Use in 2D Editor" -- the way back from the 3D viewer, which had never
existed -- was first built on `EditStructureCommand`, because pushing a
molblock onto the undo stack is exactly what that command is for. It is
also wrong, and the three ways it is wrong were each invisible to the
tests and visible in the running app.

`EditStructureCommand.redo` **clears the conformer set**, correctly: a
structure edit invalidates geometries computed for the old structure.
Adopting a conformer edits no structure. Measured live: the count went
1 -> 0, and `_refresh_view` answers an empty list by clearing the backend
and disabling the button -- so the control **blanked the very viewer it
lives in** and discarded the set the user had just generated.

The other two are about what a conformer IS, and both are worth knowing
anywhere a geometry meets a drawing:

    aspirin as drawn                       13 atoms
    a conformer of it                      21 atoms   embedded after AddHs
    naively adopted                        21 atoms
      canonical SMILES becomes  [H]OC(=O)c1c([H])c([H])c([H])c([H])c1...

so the drawing becomes a different structure to everything that compares
one -- and `select_calculation_input` already records that eight of the
49 registered calculators return a different number for a molecule
carrying explicit hydrogens. That is why `DRAWING` is its default.

    closest heavy-atom approach in the drawing
    case                    proper   conformer x,y   laid out
    aspirin (flat)           1.500           0.701      1.500
    cyclohexane (chair)      1.500           1.331      1.500
    camphor (bicyclic)       0.781           0.476      0.624
    cholesterol (steroid)    1.500           0.219      1.500
    sucrose (two rings)      1.500           0.241      1.500

**A conformer's x and y are a projection, not a layout**, and it fails
worst on exactly the molecules whose 3D geometry is worth having.
`AllChem.GenerateDepictionMatching3DStructure` lays out a real drawing
that still follows the 3D orientation. **A test on a FLAT molecule cannot
see this** -- aspirin projects to something usable by accident -- which
is why the guard uses cholesterol and asserts the projection really does
overlap first.

#### AND THAT LAID-OUT COLUMN IS ITSELF DEGENERATE FOR A SYMMETRIC BRIDGE

The table above shipped, and was reported broken the same day: "I tried
to use a send to 2d editor, and it didn't really do anything", on a
benzobicyclo[2.2.2]octane. **Camphor's 0.624 was the warning and it was
explained away** as that molecule being cramped -- it was the only
bridged case in a five-molecule set, and it scored worst.

Seen down the bridgehead-to-bridgehead axis of a bicyclo[2.2.2] system
the two `-CH2CH2-` bridges superimpose EXACTLY, and a depiction that
follows the 3D orientation reproduces that faithfully. Measured over 29
molecules, as the ratio of the oriented layout's closest approach to the
plain depiction's:

    0.000  bicyclo[2.2.2]octane, quinuclidine, DABCO, barrelene, and the
           reported benzobicyclo[2.2.2]octane   <- two atoms AT THE SAME POINT
    0.239  tropinone
    0.392  morphine
           <-- the gap, 0.41 wide, the largest in the set
    0.799  camphor
    1.000  twenty others, norbornane / adamantane / cubane / strychnine
           among them
    1.388  sucrose, where the oriented layout BEATS the plain one

So it is **not** a "bridged" test -- norbornane and adamantane are fine.
It is the symmetric two-bridge case. The tell in a user's log is RDKit's
`Warning: ambiguous stereochemistry - overlapping neighbors`, which is it
saying two atoms share a coordinate.

`READABLE_LAYOUT_FRACTION = 0.6` sits in that gap and a guard fails if it
leaves `[0.40, 0.79]`. Below it the plain layout is used and
`ConformerDrawing.follows_geometry` is False, which the status bar says
out loud -- a correct drawing that ignores the conformer is exactly the
"did nothing" the report was about, so it has to announce itself.

**ROTATING THE REFERENCE FIRST DOES NOT HELP.** The obvious reading is
that this is a viewpoint problem, since the cage only superimposes along
one axis. `GenerateDepictionMatching3DStructure` normalises orientation
internally: all 25 combinations of rotating the conformer 0-90 degrees
about two axes returned byte-identical layouts, 0.000 every time, on all
five degenerate cases. Measured before accepting the fallback, because
"why not just rotate it" is the first thing anybody will ask.

##### THE FIXTURE-VALIDITY BOUND WAS ITSELF FITTED TO ONE CONFORMER

`test_the_drawing_is_laid_out_rather_than_projected` asserted
`projected < 0.5` before testing anything -- the setup assertion that
cholesterol's raw projection really is unusable, without which the real
claim proves nothing. It failed on the non-blocking Linux CI job at
**0.5237**, which reads as a platform quirk and is not one.

**5 OF 20 EMBEDDING SEEDS BREAK IT ON THIS MACHINE TOO.** Measured over
20 seeds, cholesterol's projection ranges **0.067 to 0.721** in molblock
units, so 0.5 sits inside its own distribution and Linux merely drew one
of the conformers that exceed it. The number was fitted to whatever
`randomSeed=0xC0FFEE` happened to produce. Same shape as the conformer
de-duplication threshold fitted to butane, one level along: not a wrong
value, a wrong KIND of bound.

Both readability bounds are RATIOS against the molecule's own ordinary
depiction now, which removes the bond-length unit, and the two
populations really are bimodal:

    the conformer's raw x,y   0.045 .. 0.480     20 seeds
    the laid-out drawing      0.940 .. 1.000
                              a gap 0.46 wide

`PROJECTION_IS_DEGENERATE_BELOW = 0.65` and
`LAYOUT_IS_READABLE_ABOVE = 0.75` both sit in that gap, and
`test_the_two_readability_thresholds_sit_in_the_measured_gap` checks
each against the RECORDED spread rather than against the other -- so
widening one to make a failure go away fails there, naming the
measurement. Linux's own value is 0.349, comfortably inside the first
band, which is what says the spread describes that machine as well.

**The behaviour is still under test, and that was mutated rather than
assumed.** Making `drawing_from_conformer` keep the raw projection fails
this test and two others; only widening the constant is caught by the
new guard alone.

**The fourth defect was found only by driving the app, with every test
green.** `MoleculeEditorWidget._on_molecule_changed` compares canonical
SMILES and deliberately ignores a coordinates-only change, so the canvas
has to be reloaded explicitly -- and doing that at the call site covers
the button press but NOT undo or redo, neither of which comes back
through it:

    state       model              canvas             conformers
    adopted      2.7760   0.0000    17.6739  -6.2560      1
    undone      -0.1507  -2.5113    17.6739  -6.2560      1   <- disagree
    undone (fixed)         -0.1507  -2.5113  both          1

The reload belongs in the command, which is the only thing that knows
about all three transitions.

One mutation SURVIVED and is genuinely equivalent: deriving the drawing
inside `redo` from the conformer instead of in the constructor produces
identical bytes, because RDKit's depiction is deterministic. Deriving it
from `self._molecule.molblock` -- which after an undo is the ORIGINAL
drawing -- is a real bug and is caught. The distinction is written into
the test rather than left as a green tick.

### Conformers are aligned for DISPLAY, and the copy is never stored

`EmbedMolecule` leaves every conformer in its own arbitrary frame -- a
gauge choice carrying no information -- so stepping between them in the
viewer changed the orientation as much as the shape. Reported as "It is
extremely difficult to compare different conformers... I arranged the
first conformer in 1 row, then in the second conformer I moved it a
certain way, then moved back to the first conformer, and it was once
again in a different way."

**The cause had been sitting in plain sight**: `GetBestRMS` computes the
optimal superposition during de-duplication and throws the transform
away -- the same shape as `CoordinationShell` discarding the positions it
already held.

`align_conformers_for_display` in `chem/alignment.py` recomputes it;
`ConformerModel.molblock` is never touched. A transform field on the
model was rejected because every consumer would have to remember to apply
it, and the one that forgets shows exactly the unaligned view the whole
thing exists to fix.

**IDENTITY ATOM MAP, NOT `GetBestRMS`.** Conformers of one molecule
already share an ordering, so identity is deterministic. `GetBestRMS`
searches symmetry-equivalent permutations, and on a symmetric core it can
pick one that flips the whole structure between conformers -- replacing
the jump being fixed with a different one.

**Fit on heavy atoms, apply to all.** A rotating methyl otherwise drags
the fit and swings the ring to chase three hydrogens nobody is comparing.

Four things the invariants had to be shaped around, three of them found
by mutation:

- **A reflection preserves every interatomic distance**, so a distance
  test cannot see one. Chirality can: the signed volume of four
  non-coplanar atoms keeps its sign under any proper rotation. Both are
  asserted, and the mirror mutation kills 4 tests.
- **"Common frame" and "idempotent" do not pin down the reference.**
  Chaining each conformer to its predecessor satisfies both, distorts
  nothing, and passed every invariant -- a surviving mutation. What it
  breaks is that a conformer's orientation then depends on which others
  are in the list, which matters because the gallery pages through
  SUBSETS. The guard aligns `[A,B,C]` and `[A,C]` and requires C to come
  out identical.
- **Compare within molblock precision, not bitwise.** Coordinates go
  through a four-decimal text format, so 5e-4 is the floor.
- **A heavy-atom fit does not align all-atom centroids**, and asserting
  that it does fails at ~0.17 A on hexanol -- fourteen hydrogens are
  exactly what varies between conformers.

#### The drawing can BE the 3D structure, turned to face the camera

"the structure is not in a *literal* 3d shape, which is the entire point
of what I'm trying to do" -- against a MarvinSketch screenshot of
buckminsterfullerene drawn in perspective inside a 2D editor. The flat
depiction that shipped first was the wrong target: **crossing bonds are
not a defect, they are what a projection of a real geometry looks like.**

`drawing_from_conformer(molblock, view=...)` rotates the conformer by the
camera and writes a **3D** molblock; the editor draws its x and y. Live,
comparing the adopted drawing against `modelToScreen` for the same atoms:
**agreement +0.9966**.

**`camera_to_model_transform` is a pure function and det(R) is asserted,
because a reflection preserves every interatomic distance** and so hides
from anything measuring geometry. The point set in its tests is
deliberately asymmetric -- a symmetric one makes an inverted transform
look correct.

**THE OBVIOUS ORACLE FOR THE DIRECTION IS WRONG.** Asking 3Dmol to apply
its own quaternion, via `$3Dmol.Vector3.applyQuaternion`, DISAGREES with
the standard convention: for `q = (0, sin35, 0, cos35)` it returns the -70
degree rotation where the standard form gives +70. Settled against where
atoms are really drawn, with `viewer.modelToScreen`:

    70 deg about y    matrix +0.9989   transpose +0.5441
    40 deg about x    matrix +0.9994   transpose +0.6598
    55 deg about z    matrix +0.9993   transpose -0.3351

Give each rotation a FRESH viewer -- rotating one through all three in
turn composes them, and scored 0.83 on a case that is really 0.9994.

**A degenerate ANGLE is reported, not repaired.** The bicyclo[2.2.2]
fallback still exists for the no-camera path, but when the orientation
came from the user's own camera, substituting a tidier one would be the
same silent-substitution failure in a new place. `ConformerDrawing.crowded`
says so and the status bar suggests turning the view.

**A drawing that loses its chiral flag says something different.** RDKit
writes 0 by default and Ketcher renders 0 as **"AND Enantiomer"** against
1 as **"ABS"** -- so a drawing derived from a conformer quietly stopped
claiming which enantiomer it was, while its SMILES kept the @ and every
calculator went on treating it as resolved. Set
`_MolFileChiralFlag` when the molecule has a defined centre, and only
then. This was PRE-EXISTING in the flat path, not introduced by the
camera work.

**"Perceive stereo before RemoveHs" is NOT load-bearing here**, though it
sounds as though it must be. `MolFromMolBlock` already assigns from 3D at
parse time, and measured on alanine with the tags wiped first, both orders
give `(1, 'R')` -- three heavy neighbours and their coordinates determine
the fourth direction. A mutation deleting the explicit call survives, and
the docstring says so rather than claiming a delicate sequence.

**Reading the camera is asynchronous, so the adoption is a SNAPSHOT.**
Pressing `>` while the read is in flight would otherwise adopt conformer 2
with conformer 1's camera -- a structure at an angle nobody ever looked
at, chemically valid and undetectable downstream. The index and structure
key are captured first and re-checked on the way back, and the button is
disabled meanwhile.

**And the camera composes with the DISPLAYED frame, not the stored one.**
The viewer shows the display-aligned copy, so rotating the retained
conformer by the on-screen camera gives some unrelated angle. Caught by a
mutation -- and only after the test was rewritten with real embedded
conformers, because placeholder molblocks do not parse and make aligned
and retained the same string. That is the SECOND time that trap fired in
this work.

#### THE FUNNEL: de-duplication was not where the conformers went

Reported as "I still feel like it's over filtering conformers", on
"virtually almost any fine molecule", after a session that had already
raised the count. A count cannot answer that -- it cannot tell
under-sampling from over-merging, and the two want opposite fixes -- so
`benchmarks/conformers/funnel.py` reports every STAGE and then the pairs
that were actually discarded. Measured at 50 embeddings, seed 0, RMSD-only
on both sides so the two are comparable:

    molecule         embedded  distinct PRE-opt  converged  POST-opt  POST shipped
    cyclohexane            50          1               50        1          2
    (S)-ibuprofen          50         17               50       10         10
    ethylmorphine          50          8               50        2         10

**De-duplication removes NOTHING on ibuprofen** -- 10 by RMSD alone, 10
under the shipped criterion. The 17 -> 10 is minimisation converging
distinct starting geometries into shared minima, which is what
minimisation is for. **Cyclohexane's 50 embeddings are one shape** before
minimisation, so at the rigid end the constraint is ETKDG's sampling and
the twist-boat arrives only through the energy veto.

**THE DISCARDED PAIRS ARE DEGENERATE, NOT DISTINCT, and that is the
answer.** Of the merged-away pairs whose largest corrected torsion moved
more than 90 degrees, the greatest energy difference is:

    butane 0.0000   pentane 0.0000   ibuprofen 0.0009   ethylmorphine 0.0680

Equal energy plus a large torsion is the signature of a MIRROR-IMAGE pair,
and butane's are exactly its g+/g- forms at +-65 degrees -- 130 degrees
apart in the C-C-C-C torsion, RMSD 0.477, dE 0.0000. Merging those is what
produces butane's textbook count of 2. So "a torsion moved 130 degrees and
it was merged anyway" reads as a smoking gun and is not one.

**The one place real conformers are lost is the CAP.** `num_conformers`
defaults to 10 and ethylmorphine finds ~12.8 at the default 50 embeddings,
so the rest are truncated -- they converged, they are distinct, and they
are silently absent. `conformers_returned` is now recorded beside
`conformers_distinct` (it was the one stage count that never was) and the
3D viewer's *Details...* dialog shows the two together. **No threshold,
window or default was changed**: nothing the funnel found is a defect in
the criterion.

##### The metric that would have lied about all of it

`MergeCandidate.max_dihedral_change` was read with a raw `GetDihedralDeg`
on fixed indices while the merge decision uses symmetry-aware
`GetBestRMS`. Measured on ibuprofen through the real `_merge_scan`:

    rmsd 0.000  dE 0.000  TFD 0.0000  maxDih 180.0  C1-C3-C4ar-C5ar

A pair of IDENTICAL structures reporting half a turn, because flipping a
para-substituted ring maps the molecule onto itself. **33 of 40 merged
pairs flagged a torsion over 90 degrees**; corrected, 14. A funnel built on
the uncorrected metric would have reported a catastrophic over-merge on
the first molecule anybody tried.

The fix takes the correspondence from `GetBestAlignmentTransform` and
CHECKS it against the RMSD `_merge_scan` used, on the
`comparison_skeleton` -- which is what makes it cheap, since carbon-bound
hydrogens carry the methyl permutations and dropping them takes ibuprofen
from 1728 automorphisms to 4, at 0.6 ms per pair. It costs no torsion:
`CalculateTorsionLists` returns identical group counts on the full
molecule and the skeleton.

**This is the SECOND time this diagnostic has been wrong** -- the first
read only the non-ring list and had a written conclusion resting on it.
The ethylmorphine claim it supported survived re-measurement to the digit,
which is luck rather than vindication.

Three things worth carrying:

- **A structure against an exact `Chem.Mol` copy of itself cannot show
  this.** Same atom ordering, so both metrics read 0. It takes two
  genuinely different embeddings that happen to superimpose, which is why
  the guard SEARCHES for the pair and asserts the naive arm still reads
  180 -- without that assertion the test passes vacuously the day the
  fixture stops containing the case.
- **A positional fixture was wrong for a subtler reason:**
  `generate_conformer_batch` sorts by energy, so "embeddings 0 and 1" of a
  2-embedding run is not the pair with those indices in a 20-embedding
  run. Everything downstream sorts, filters and truncates, so a list
  position is not an identity -- which is why `MergeCandidate` carries an
  `_oc_origin` tag (`seed=0 embedding=17`) written at the one point that
  knows the attempt number.
- **`n/a` is not 0, and ethanol is the case.** RDKit's torsion
  enumeration is EMPTY for a skeleton as small as C-C-O-H, so all 240 of
  its merged pairs report unavailable -- nothing to measure, rather than a
  measurement that failed. A forensic table that rendered those as 0.0
  would have said ethanol's discarded pairs were motionless.

##### Acted on 2026-08-13: two defaults and one sampling flag

The verdict above was put to Alex and three decisions came back; all
three shipped on the `conformer-defaults` branch, each with its evidence.

**`useSmallRingTorsions` is now on by default**, gated in ISOLATION at
the benchmark protocol (50 embeddings/seed, identical seeds, nothing else
varied -- evaluating it at the new application defaults would have
confounded the flag with the sampling increase). Ten of eleven corpus
molecules byte-identical; ethylmorphine's 5-seed union grew 17 -> 25,
because its flexibility IS ring pucker. Paired cost x1.17 total. The
funnel confirmed cyclohexane still counts 2 -- pre-opt diversity rose
1 -> 3 but chair and twist-boat still merge geometrically (0.3747 < 0.5),
so the energy veto stays load-bearing and extra sampling never became
extra counting. The azirine same-shape floor is unmoved; its guard
recomputes both bounds and passed under the flag. The flag is recorded in
provenance and the benchmark environment, read from the provider that ran
(None for a provider that never declared it), so no stored record is
ambiguous about which sampling produced it.

**Keep 10 -> 20, embeddings 50 -> 100.** 20 exceeds the maximum distinct
count observed at 100 embeddings (~15-18) -- observed headroom, not a
sufficiency claim; the union under the flag is at least 25, which is why
the cap still exists and the Details dialog still names it when it
bites. 100 embeddings doubles a flexible molecule's yield (10 -> 15
distinct on ethylmorphine) at ~5 s. The two moved together on purpose:
raising embeddings without raising keep makes the silent-loss case worse.
A pin test carries the evidence, so an accidental revert fails naming it.

**The funnel tables above are pre-flag measurements.** They motivated the
flag, so they must not be silently reread as current behaviour --
cyclohexane's PRE-opt row is 3 under it, and
`benchmarks/conformers/README.md` carries the full OFF/ON gate table.

#### Marvin-parity generation: emulate the CONTROLS, never claim the algorithm

"make it resemble marvin's conformer generator calculator much more
closely". Four controls now exist -- diversity threshold, optimisation
level, time limit, enhanced refinement -- and the discipline that matters
is what is NOT claimed.

**ChemAxon publishes no default values.** Fetched twice and confirmed:
the Generate3D page states none for diversity, `[o]`, timelimit or
hyperfine. A reported figure of 0.1 for diversity could not be confirmed,
so nothing here presents 0.5 as matching theirs.

**"hyperfine" may be EXPLAINED but never SHOWN or WRITTEN.** ChemAxon's
hyperfine is short molecular dynamics followed by strict optimisation; a
minimiser cannot leave the basin it is already in, which is the whole
point of the dynamics. Provenance records `enhanced_optimization`,
because a stored SDF property outlives every UI that wrote it. The guard
walks the AST and checks STRING LITERALS only -- the first version
forbade the word outright and failed on the very comments that exist to
prevent the confusion.

**The strictness decides how hard to try, NOT what counts as a
conformer.** The plan for this work said the level should decide whether
to keep a non-converged geometry; it must not, and this file already
records why -- such a structure corrupts the ranking, the veto, the
de-duplication and any geometry calculator. Discarded at every level, and
a test asserts it at every level.

**Minimise through the FORCE FIELD, not `MMFFOptimizeMolecule`.** That
wrapper exposes no force tolerance, and a gradient criterion is exactly
what an optimisation level has to vary. `ForceField.Minimize(maxIts,
forceTol)` returns 0 on convergence, the same contract.

##### What the four controls actually do, measured

30 embeddings each of seven molecules from the de-duplication corpus:

    molecule         Loose  Loose+refine  Normal  Very strict
    ethylmorphine        8             9       9            9
    the other six     same          same    same         same

Every level converged 30 of 30. So **the strictness is visible on exactly
one molecule**, and **enhanced refinement's only measurable effect is
recovering what a loose first pass lost** -- nothing at Normal or above,
at about 25% more time. That is what its tooltip says, rather than
implying it improves sampling.

**A from-memory SMILES nearly produced a different story.** The first run
of that benchmark used an ibuprofen and an ethylmorphine typed from
memory; the ethylmorphine did not parse and the ibuprofen showed Loose
finding 16 against 14, which reads as "Loose over-counts". Re-run with
the corpus SMILES, ibuprofen is 8 everywhere and the effect is somewhere
else entirely. **Take benchmark inputs from the corpus file, not from
memory.**

##### The plugin interface gained a parameter without breaking anybody

`ConformerProvider.generate_conformer_batch` now takes `options`, and
`ConformerProvider` is a published plugin API. The service asks
`inspect.signature` whether a provider accepts it rather than passing and
catching `TypeError` -- which would also swallow a real one raised from
inside the provider. Same instinct as the `NOT abstract, so a provider
written against the original interface keeps working` note already on
that method.

#### A GEOMETRY CAN DEFINE STEREOCHEMISTRY, and that is not the same as the drawing specifying it

Reported as two things that were one. Adopting a conformer of a
benzobicyclo[2.2.2]octane changed the molecule's identity:

    as drawn         [(6, 'R'), (14, '?'), (17, '?')]
    after adopting   [(6, 'R'), (14, 'S'), (17, 'S')]

and the naming panel then withheld a name that had not changed. **The
nomenclature engine was innocent** -- it derives the same name for both,
that name cannot express bridgehead stereo, and only the round-trip
comparison changed its mind. Chasing the namer would have been chasing
the symptom.

**The perception is not authority.** Once atoms have positions RDKit will
label centres a flat drawing left open, but that label is a consequence of
the geometry that happened to be generated. Interconverting conformations,
symmetric environments, pseudoasymmetric centres and stereogenic
axes/planes all sit outside what one embedded conformer settles. So
`chem/stereochemistry.py` REPORTS rather than asserts, with four outcomes
and two refusals:

    unchanged                commit silently, however far the atoms moved
    unspecified -> assigned  commit, and say so
    assigned -> DIFFERENT    REFUSE -- a different compound
    assigned -> unspecified  REFUSE -- perception going backwards after a
                             rigid transform is a bug, not a result

Refused in the COMMAND CONSTRUCTOR, so nothing reaches the undo stack.

**`verify_name_round_trip` returns a verdict, not a bool.** `MATCH` /
`STEREO_OMITTED` / `MISMATCH` / `UNVERIFIED`, the same move the naming
benchmark made when it added its `tautomer` class. `STEREO_OMITTED`
requires BOTH that the name parsed AND that the skeletons agree while the
full SMILES disagree -- SMILES inference alone would only establish that
two structures differ stereochemically, which is a different claim from
the name being valid for either. Benchmark unmoved at **181/181**.

Two mutations worth keeping:

- **An empty clause is invisible to a substring assertion.** Appending
  the description unconditionally gave `"...rotated in 3D -- and ."`,
  which contains no "stereocentre" and passed the guard that was meant to
  catch exactly that. Assert the SHAPE of the message, not only its
  absence of a word.
- **`includeUnassigned=True` is not load-bearing.** `compare_*` reads the
  label dicts with `.get(index, UNSPECIFIED)`, so an absent atom already
  compares as unspecified and every outcome is identical with the flag
  off. Kept for readability; recorded so nobody re-derives it.

#### The gallery reads a DIFFERENT camera, and Phase 2's tests could not see it

Reported as "when I try to use it in the 2d editor, it is again not
actually *3d*, it is just again the absolute, 2d structure".

`current_view` read `viewer.getView()` -- the SINGLE viewer -- always. In
gallery mode that one is hidden and unrotated while the cell the user
turned carries the orientation, so "Use in 2D Editor" baked in no
rotation at all. Measured: the cell pointed `(0, 0.537, 0, 0.843)` after
a 65-degree turn and the read returned `[0, 0, 0, 1]`.

**The Phase 2 tests were correct and blind.** They exercise the single
viewer, where "the camera" and "the selected cell's camera" are the same
object, so a regression that only exists once a second camera exists
could not fail them. The page now answers `currentView()`, which is the
only side that knows which mode is showing.

Its sibling: the page resets `gridSelectedCell` to 0 on every rebuild, so
paging left `_conformer_index` pointing at another page -- the CAMERA
from cell 0 and the CONFORMER from somewhere else, which is the same
mismatch the adoption snapshot exists to prevent.

#### The conformer gallery: one WebGL context, and four traps

"all separate images possible... you could check several ones to be
visible at a time if wanted, and on the screen at the same time, yet
independently rotatable." `$3Dmol.createViewerGrid` gives exactly that,
and **the whole grid shares ONE WebGL context** -- measured,
`querySelectorAll('canvas').length` stays at 2 (single viewer plus grid)
from 2x2 to 10x10. A `QWebEngineView` per conformer would instead be a
Chromium helper set per conformer, which this file already records
accumulating into a 40-minute hang.

**Cost does not set the ceiling; legibility does.**

    cells   build     redraw
        4    91 ms      1 ms
       12   175 ms      1 ms
       25   373 ms      1 ms
      100  1481 ms      5 ms

100 cells in a 1000x700 pane is 100x70 px each. It stops at 12 and pages.

**`control_all` IS NOT THE LOCK, and it looks like it is.** It ties mouse
INPUT together and does nothing for a view changed any other way:
measured with `control_all: true`, turning one cell programmatically left
the others at the identity and the cells pointed two different ways.
`linkViewer` propagates a view change however it was made -- linked in
both directions for every pair, no loop, no measurable cost. There is no
unlink, so the lock is a rebuild.

**`createViewerGrid` DOES NOT WORK UNDER `offscreen`, AND "A SECOND
WebGL CONTEXT" IS NOT WHY.** That explanation stood here for a long time
and is wrong. It throws `Cannot read properties of null (reading
'clearDepth')` under Qt's `offscreen` platform -- which
`tests/conftest.py` sets -- and works on an ordinary windowed one.
Measured against the real bundle with nothing varying but
`QT_QPA_PLATFORM`:

    rung                                offscreen      windows
    a bare WebGL context                ok             ok
    TWELVE bare contexts                12 of 12       -
    one $3Dmol.createViewer             ok             ok
    two independent viewers             ok             ok
    SIX independent viewers             6 of 6         -
    two viewers in one parent div       ok             -
    createViewerGrid 2x2 (400x300)      THROWS         ok, 4 cells, 0 null
    createViewerGrid 1x1                THROWS         -
    the app's own gallery backend       grid_failed    2 cells drawn

Not the number of contexts, not the number of viewers, not a shared
parent, and **not the container size** -- a 400x300 container failed
while a 0x0 one "succeeded". A grid of a SINGLE cell fails too, so it is
not multiplicity in any form. Every capability underneath works; only
`createViewerGrid` does not, and **why is still unknown**.

So the page reports the failure and the widget falls back to the single
view saying why, rather than leaving an empty pane -- a user on software
rendering hits the same wall. The page-level gallery tests skip under
`offscreen` (`QT_QPA_PLATFORM=windows pytest ...` runs them, verified 42
passed); the fallback path is tested where the rest of the suite runs.

**THAT SKIP STAYS A PLATFORM CHECK ON PURPOSE**, and the ladder above is
the justification rather than laziness: the only thing that predicts the
failure is the call being tested, so a "capability probe" here would gate
a test on its own subject and turn a real regression into a silent skip.
An admitted platform gate beats a probe that cannot say no. Contrast the
`webgl` fixture in `tests/conftest.py`, where a genuine prerequisite --
whether a WebGL context exists at all -- does exist and is measured.

**Wait for the container size to SETTLE, not merely to be non-zero.**
`createViewerGrid` fixes each cell's canvas at build time and never
re-fits, so building while the pane is still growing leaves the gallery
in the top half of it. `display: block` does not reflow within the same
synchronous script either -- measured `clientWidth 0`, zero overlays and
an empty `gridViews()`, while the identical sequence in a standalone
script happened to work.

##### The 3D viewer had been HALF THE SIZE IT SHOULD BE

Found while wondering why the gallery filled only the top of the pane,
and it was never the gallery. A `QWebEngineView` and a `QLabel` both
report a `Preferred` vertical policy, so `QVBoxLayout` split the spare
height evenly:

    tab               1418 x 728
    viewer widget     1412 x 698
    the 3D view       1412 x 330   <- half
    measurement label 1412 x 330   <- a ONE-LINE readout

`addWidget(view, 1)` takes it to 644 against the label's 16. **Same shape
as the `WrappedLabel` finding in the Properties panel** -- a one-line
status claiming a panel's vertical stretch -- and it had been shipping
for as long as that label has existed, invisible until something needed
the space.

#### Camera retention keys on a viewer-SESSION identity

`viewer.zoomTo()` ran on every `loadMolblock`, so the camera was re-fitted
on every conformer step. `loadMolblock(molblock, keepCamera)` now takes
the decision from Python, because only Python knows whether this is the
same molecule and the same batch.

**Not the molblock, and not the model object.** Molblock equality would
let an imported structure with a matching graph inherit an unrelated
camera; an object identity cannot survive the model being rebuilt. The
key is `(molecule.uuid, tuple of conformer timestamps)` --
`_ConformerGenerationTask` stamps one `Provenance` across a whole run, so
a regenerated set correctly re-fits and a conformer appended later by
`AddConformerCommand` changes the tuple rather than slipping in unseen.

Verified live on Alex's own sequence, reading `getView()` rather than
comparing screenshots:

    as generated       [0,0,0,0,0,0,    0,1    ]
    arranged by hand   [0,0,0,0,0,0.574,0,0.819]
    stepped to conf 2  [0,0,0,0,0,0.574,0,0.819]
    stepped back to 1  [0,0,0,0,0,0.574,0,0.819]

**A placeholder molblock makes an alignment test vacuous.** Every test in
`test_molecule_viewer3d_widget.py` used strings like `"conf-1"`, which do
not parse -- so the aligner returns them untouched and "aligned" and
"retained" are the same string. A mutation that bypassed alignment
entirely passed all of them. One test now builds real embedded
conformers, which is the only thing that tells the two apart.

### A CACHE can make a guard pass while the code under test never runs

Third instance of "a test naming a behaviour is not a test of it", and a
new mechanism for it. The Atom Inspector's report cache is keyed on
`(uuid, structure_version, subject, index)`, and the version comes from
`StructureCheckService` -- which is **None in a plain panel fixture**, so
the version is 0 forever.

Two guards for a stale-index crash therefore edited the molecule, called
`_render_facts()`, and got the CACHED report back. The builder never ran,
so `build_atom_report` was never reached, so nothing could raise. Both
passed against a panel with no bounds check at all; a mutation removing
the check outright left the file green.

The fix is a fixture supplying a version counter and bumping it on every
edit, which is what the application does. **If a panel caches, a test
that mutates state must move whatever the cache is keyed on**, or it is
testing the cache.

The same run produced a second, smaller lesson worth keeping: the
`0 <=` half of `0 <= index < limit` is **not reachable** through the
panel -- no caller produces a negative index -- so a mutation deleting it
survived every end-to-end test. It is asserted directly on the predicate
instead of being deleted, because the predicate's contract is "does this
name something in the molecule" and answering True for -1 is wrong on its
own terms. **An unreachable branch is a question about where to assert,
not automatically dead code.**

### The command palette introduces no registry, deliberately

`Ctrl+Shift+P` reads three indexes the app already has -- the rail's panel
list, `CalculatorRegistry`, and the live `QMenuBar` -- for **113 commands
with nothing registering itself**. A palette that required each feature to
register would be a fourth list to keep in step, and the one that falls
out of step is always the one nobody remembers to update. A new
calculator or menu item is in the palette because it exists.

`score()` is a pure function so the ranking is testable without a dialog,
which matters because ranking is the only part of a palette that can be
subtly WRONG rather than broken. Four tiers -- exact, prefix, word start,
subsequence -- with subsequence last because it matches almost everything
and would otherwise drown a real prefix. Ties keep the caller's order, so
panels beat calculators beat menu items and "batch" lands on the panel.

#### PySide invalidates a wrapper reached through a TEMPORARY list

Hit twice in one hour, in production code and then in a test:

```python
menu = next(a.menu() for a in bar.actions() if ...)   # menu is DEAD here
```

The C++ object is fine; the wrapper is not. `bar.actions()` is a
temporary, and releasing it invalidates every wrapper obtained from it --
the next line raises `Internal C++ object already deleted`. Hold the
parent list, or read what you need while you still have it.

`_menu_actions` does the latter: it captures each label DURING the walk
and returns `(label, source, action)`, rather than handing back a wrapper
for the caller to read later. `findChildren(QMenu)` is worse still and is
avoided -- it is recursive over the whole object tree and returns wrappers
for menus Qt has already freed.

A dock's `toggleViewAction` carries the panel's own name, so every panel
appeared twice until exact duplicates were dropped. The panel command
wins because it SHOWS the panel; a toggle can hide it, which from a
palette is a surprising thing to have asked for. Only exact duplicates go
-- Console is a dock with a toggle and no rail entry, and its View item is
the only way to reach it.

### Comparison: the engine existed, the way in did not

`chem/comparison.py` had `atom_correspondence`, `build_comparison` and
`deltas_against` since the LED work, reachable from exactly one place --
a tab inside `BatchAnalysisDialog`, behind building a batch table first.
So "how do these two molecules differ", which is a question people ask
constantly, required a workflow nobody would guess at.

`compare_values` is the everyday case beside that per-atom machinery:
molecules in columns, properties in rows, built from the values other
panels have already published. **The panel never computes** -- a blank
cell means that calculator has not run for that molecule, and the intro
says so, because a comparison view that silently launches forty
calculators is one people stop opening.

**"Differences only" is the feature, not a filter.** Measured live on the
motivating pair: aspirin against salicylic acid is **15 differing rows
out of 29**, and finding those 15 by eye is exactly the work the table was
supposed to save.

Three decisions worth keeping:

- **Absence counts as a difference.** A property one molecule has and
  another does not stays visible under "differences only" -- a missing
  value is usually the interesting thing, and hiding it would be the more
  misleading of the two choices.
- **Rows keep producer order, never alphabetical.** A calculator emits
  formula before mass before composition deliberately, and sorting
  scatters that.
- **Agreeing on everything is a RESULT, not an empty table.** Two
  molecules matching on every property known says something, so that
  empty state differs from "nothing computed yet".

The ticks do NOT follow the tree selection, for the same reason the
Interactions panel's two combos do not: the comparison is a deliberate
choice, and reshuffling it because somebody clicked elsewhere would
silently change what the table on screen describes.

#### The rail must follow a panel opened from anywhere

"Compare with..." showed the Compare panel while the rail still
highlighted Analysis. `_on_panel_chosen` now calls
`PanelRail.select_panel`, which is a no-op when the rail itself was the
caller and is what keeps the two in step for every other route -- a
plugin revealing its panel, a cross-link, the command palette. Navigation
claiming one thing while the screen shows another is worse than either
alone.

### `AlertResult` was carrying twenty reports and five alerts

`AlertResult.matched` is a `list[str]`, and it became the generic line
carrier for anything that was not a single scalar. Counted: **25 distinct
`alert_id`s, of which only pains, brenk, mutagenicity_alerts and
herg_risk_factors are catalogs.** The panel rendered every non-empty
`matched` as `"N alert(s): "` in red, so four fifths of the app's output
looked like a warning.

`ReportResult` carries `Fact`s instead -- label, value, units, basis,
evidence, limitations, which atoms it is about, how specialist it is. All
of that was already being computed and flattened away at the last step.

Measured after the migration: **16 fact-based reports, 4 alert catalogs.**

**`AlertResult` is not deprecated and must not be.** It is in the plugin
API, and for a real catalog "N alert(s)" in red is the correct rendering.
`chem/report_adapter.py` converts one to facts for anything that has not
migrated -- permanently, not as a shim.

#### The batch table shows what a string cost

`result_reduction.py` had to PARSE `"Randic index: 9.52"` back into a
label, a number and a unit, with a deliberately strict regex. Measured
when it was written: 73 numeric columns extracted and **25 lines refused**
-- formulas, prose caveats, value lists, all correctly refused and all
genuinely lost.

A `Fact` was never flattened, so `_reduce_report` has nothing to recover:
45 facts give 43 numeric columns on the same four calculators, the two
text ones being a formula and a direction vector. **The column ids are
byte-identical**, so saved tables, charts and exports survive.

#### NEVER TUNE EITHER STRING PARSER BY READING ITS PRODUCERS

There are two -- `report_adapter._MEASUREMENT` (presentation: recover a
label) and `result_reduction.parse_reported_numbers` (numeric columns) --
and they judge free-text lines written across 49 calculators, so "which
lines does my change affect" is not a grep question.
`benchmarks/report_lines/sweep.py` answers it by instrumenting
`report_adapter._split` and running the real registry: **484 distinct
lines**, and `--candidate` diffs a value pattern against them in both
directions.

```bash
uv run --no-sync python benchmarks/report_lines/sweep.py --candidate '...'
```

**It has already overruled one obviously-correct fix.** `_MEASUREMENT`
accepted a leading minus and not a leading plus, so a line formatted
`f"{v:+.2f}"` was refused for its SIGN -- 18 lines, and the panel showed
three parsed dipole components beside one unparsed one. The candidate fix
added a `(?=\s|$)` boundary so a comma-separated value list could not
mis-split, and the sweep said it **regresses 31 real lines**: `"C:
23.79%"` and `"Percent buried volume: 13.30%"` attach their unit with no
space. What shipped is the one-character `-?` -> `[-+]?`.

Two things that decided it, both worth reusing:

- **Check the candidate against `_as_float` as well.** A stricter number
  parses `"+2.00"` out of a ten-orbital spectrum, so the batch table
  would gain a numeric column asserting a list is a scalar. Leaving the
  comma in the value class makes it unfloatable, which is what keeps that
  column correctly textual.
- **The two parsers must NOT be aligned.** The numeric one is entitled to
  refuse `"Pi system: 10 atoms, 10 pi electrons"`; the presentation one
  still has to show it. Making one call the other looks like reuse and
  deletes that distinction.

#### `ReportResult.matched` is a DERIVED view, kept on purpose

Composed from the facts on demand, never stored. It exists because
`matched` is in the plugin API and because a large number of assertions
read it -- "does the topology calculator report a Randic index" is a real
question whose answer does not change with the shape it arrives in.

Regulatory's lines were already self-labelling (`"Near miss: ..."`), so
they are split at that colon and `matched` recomposes them byte-for-byte.
That is what let 13 modules migrate without rewriting their tests.

#### Regulatory finally says what it did NOT check

It computed the rulesets consulted, the coverage notes and the unchecked
domains into `Provenance.parameters` and **displayed none of it** -- the
panel showed `1 alert(s): No matches in the 1 ruleset consulted`. They
are facts now: aspirin's screen lists twelve domains with no ruleset
loaded, each carrying "this screen says nothing about it either way".
Ruleset versions and coverage notes are marked ADVANCED so they do not
bury the findings; "NOT checked" is deliberately STANDARD, because a gap
in coverage is not specialist information.

#### DATE-AWARE SCREENING: two mutations no shipped ruleset can catch

`screen(as_of=...)` withholds rules taking effect after a date, and the
whole feature is guarded by tests on FIXTURES rather than on the shipped
rulesets. That is not a stylistic preference -- for two of them the shipped
data is degenerate, and a guard written against it would pass while testing
nothing.

**THE BUILD ALREADY WROTE THE FALLBACK IN.**
`tools/build_regulatory_rulesets.py` copies a ruleset's `effective_date`
onto every rule that does not declare one, so in a shipped ruleset the
engine's runtime fallback and the baked-in value always agree. Deleting
`resolve_effective_date`'s ruleset branch therefore changes NOTHING
measurable across all 91 rules. `loader.py` does no such copying, so a USER
ruleset that dates itself and not its rules is the only thing that reaches
that branch -- and a synthetic fixture is the only way to build one.
Measured: that mutation is caught by
`test_a_rule_with_no_date_takes_its_ruleset_s` and by nothing else in the
suite.

**AND EVERY SHIPPED RULE IS DATED IN THE PAST**, so defaulting `as_of` to
`date.today()` instead of `None` gives identical answers on all 91 rules and
on all four benchmark corpora. Only a rule dated in the FUTURE tells them
apart, which is what
`test_a_rule_dated_in_the_future_still_matches_an_undated_screen` exists
for. Seven mutations were run; those two were caught by one test each.

**THE DEFAULT THAT COULD HAVE GONE THE OTHER WAY.** An undated rule is NOT
DATE-FILTERED -- and that wording is load-bearing rather than fussy, because
"applies at every date" is a claim about history the data cannot support.
The shipped split is 40 rules at 1997-04-29, 4 at 2020-06-07, and **47
undated** (the whole DEA list, at rule and ruleset level), so treating an
absent date as "never applicable" would silently empty a majority of the
screen while looking exactly like a substance that is not listed.

**A REFUSAL AND A DEGRADATION ARE OPPOSITE ANSWERS TO THE SAME BAD DATA,
and which one is right depends on whose data it is.** A malformed
`effective_date` inside a ruleset FILE degrades that one rule to undated and
is reported (`ScreeningReport.malformed_effective_dates`), because one bad
entry must not cost somebody every other rule -- the same policy as the
existing `PredicateError` skip. A malformed date typed by the USER refuses
the whole screen (`CacheState.FAILED`, no findings, no coverage rows),
because there the QUESTION is broken: answering "what applied in 2019" with
today's rulesets and a warning attached means the reader has to notice the
warning to know they were given the wrong answer. The first draft of this
had it falling back to an undated screen and was corrected in review.

One parser serves both, with three states that must not collapse into two:
absence is a VALUE (`None`), malformation is an EXCEPTION. The build lets it
become a `BuildError`; the engine catches it. Neither calls
`date.fromisoformat` itself, so they cannot drift.

**A SHIPPED RULESET CARRIED A CLAIM THIS FEATURE FALSIFIED**, and a
too-loose test assertion found it rather than review. Schedule 1's
`known_limitations` said the 2019 additions' effective date "is recorded on
the rules rather than enforced". `known_limitations` is prose inside DATA,
so no docs guard covers it -- `tests/test_docs_are_current.py` reads
markdown. Check a ruleset's own declared limits when you change what the
engine does with that ruleset's fields.

### The right-hand panels are NOT tabified, and must not become so again

Twelve panels shared one tabified dock group, and Qt gives such a group a
single `QTabBar`. **That bar wanted 1992 px and had about 920**, so every
label elided to two or three characters -- `"Qu..."`, `"J..."`, `"B..."`.
Widening the dock cannot fix it: a bar wide enough for twelve labels is
wider than the window.

`tabifyDockWidget` is what creates that bar, so the fix is not to hide it
but to stop tabifying. One right-hand dock is visible at a time and
`ui/widgets/panel_rail.py` chooses which. That also answers the reason
they were tabified in the first place -- the visible panel gets the whole
column, instead of nine slivers.

**Hiding Qt's bar does not work**, tried first: `setVisible(False)` on the
live one reads back `True` after the next relayout, because the dock area
re-shows it.

`test_the_right_hand_panels_have_no_tab_bar_to_elide` fails if a
`QTabBar` parented to the WINDOW comes back. The ones parented to a
`QTabWidget` belong to individual panels and are fine.

#### `restoreState` restores TABIFICATION, so old layouts are discarded

This is the part that a test would not have caught, and did not. Every
`tabifyDockWidget` call was gone and the elided nine-tab bar was **still
there** on a real install, because `QMainWindow.restoreState` had put it
back from the saved layout.

`_LAYOUT_VERSION` in `app/main_window.py` gates it: a state saved under an
older arrangement is dropped. There is nothing to migrate -- `saveState`
is an opaque blob with no readable structure -- so the only honest
options are restore it or do not. **The geometry is kept either way**; it
carries no dock arrangement, and discarding somebody's window size to fix
their panel layout would be a gratuitous second change.

Bump `_LAYOUT_VERSION` for any future change a saved layout cannot
express, and probe a REAL install rather than trusting the suite: every
test builds a window with no prior state, which is exactly the case that
cannot see this.

**AND THE VERY NEXT GEOMETRY CHANGE FORGOT TO, which is why that sentence
is worth more than it looks.** `_LAYOUT_VERSION` went to `"2"` on
2026-08-07 with the rail; the 420 px starting width landed 2026-08-15 and
left it alone. So every install that had run the app in between carried a
version-2 layout with 280 px docks, and the fix that exists to stop
caption clipping **never reached any of them** -- including this
project's own. Read off the real registry: `ui/layout_version = 2`, and
`_set_initial_right_dock_width` is skipped whenever a layout restores.

Measured by driving the app with the version bumped and nothing else
changed: docks 280 -> 420, and the Batch panel's horizontal scrollbar and
off-screen "Virtual Screening..." button both disappear. Bumped to `"3"`.

The tell is that the suite cannot see this class of defect AT ALL -- a
saved layout is the one state no test starts from -- so the check is
`ui/layout_version` in the real store, not a green run.

#### `isVisible()` is False for every child of an unshown window

Bit twice in two phases, in production code and in a test. A dock that
has been `setVisible(True)` on a window nobody showed still reports
`isVisible() == False`, so a check written that way answers "none of
them" under a test harness while looking right in the running app --
the same blindness as `repaint()` on a widget that was never shown.

`isHidden()` reads the explicit flag and is the one to use. Both
`_help_topic_for_visible_panel` and
`test_only_one_right_side_dock_is_visible_at_a_time` had to change.

### Empty states: iterate over what is BUILT

There was no empty-state text anywhere in `ui/` -- a search for any
placeholder string over the whole package matched two files, neither a
panel. So "not run yet", "ran and found nothing", "failed" and "not
applicable to this job" all rendered identically as blankness, and an ESP
single point left six of seven quantum tabs looking broken.

`tests/test_empty_states.py` walks the tabs **the panel actually builds**,
never a list kept beside it -- the same direction that caught the two
missing help topics. It asks each tab what it SHOWS, not how it stores
it, which is what let the three mechanisms below coexist behind one
guard. Verified by simulating the mistake: removing one tab's placeholder
fails naming the tab.

#### SOLVED: the teardown collect was DESTROYING MainWindows

Windows fatal exception `0xc0000374` (heap corruption), raised inside the
`gc.collect()` in `pytest_runtest_logfinish`, in whichever test was
unlucky. **It cost about fifteen full suite runs across three phases of
UI work**, and every appearance looked at first like an unrelated failure
somewhere else.

**Collecting a `MainWindow` corrupts the heap.** A window a test builds
has no Qt parent, so PySide gives Python ownership, and freeing the
wrapper deletes the C++ window. The window sits in a reference cycle
nothing else breaks, so the thing that eventually frees it is the
teardown collect. `tests/conftest.py` now retains every MainWindow for
the session, and `test_main_windows_are_deliberately_never_collected`
fails if that retainer is removed.

**This is the project's own conclusion, finally made true.** The sections
below record two earlier attempts to destroy abandoned MainWindows, both
of which made the suite crash MORE, and both concluded "leave them". What
nobody had noticed was that the collect was destroying them anyway --
`pytest_runtest_logfinish`'s own docstring asserted it "does not destroy
anything itself", which was wrong.

##### Why it looked like "adding a widget breaks it"

Because the crash is **non-monotonic in widget count**, which is the tell
that it is a corrupting free whose VICTIM depends on heap layout, not a
capacity being exceeded. Measured with a tunable probe that adds N empty
`QLabel`s to a panel, on the 20-second reproduction:

    0, 1, 2, 4 extra labels    clean
    8, 16 extra labels         CRASH
    32 extra labels            clean

So the widgets never caused anything; they shuffled the heap until the
freed window's memory happened to be adjacent to something that mattered.
Every "prefer a change that adds no widget" rule written into this file
across two commits was a superstition that worked by luck, and all of it
has been deleted.

##### How it was found, in the order that worked

1. **A tunable probe driven by an environment variable**, so an A/B needs
   no file edit at all. Three arms in an earlier bisect had silently
   tested an unmodified file.
2. **`PYTHONMALLOC=debug` reported nothing**, which rules out Python's
   allocator and says the corruption is in the C++ heap.
3. **`gc.DEBUG_SAVEALL` made it clean.** That is the decisive step: with
   nothing freed there is no crash, so the crash is in FREEING a member
   of a cycle, and `gc.garbage` then holds the exact candidates.
4. **Retaining one class at a time** named it. Patching `__init__` to
   append to a global list prevents collection at the source:

        retain nothing                          crashed
        retain MainWindow                       clean
        retain the three viewer backends        crashed
        retain QWebEngineView + QWebChannel     crashed

Retaining the windows also made the reproduction **twice as fast** (1.76 s
to 0.85 s), because destroying them was expensive. Full suite: 2846
passed, peak working set 760 MB.

##### Six hypotheses that are WRONG

Recorded so nobody pays for them again. Each was tested against the full
suite; two of them this file previously asserted as the rule.

1. *The `dict[QWidget, ...]` holding placeholders.* Removed -- still dead.
2. *Hiding sibling content.* Suppressed every visibility change -- still
   dead.
3. *A new test file shifting collection order.* Removed -- still dead.
4. *"A placeholder in a tab page that already holds widgets."* The log's
   `CollapsibleSection` went into a main layout and died the same way.
5. *Python-derived widget subclasses.* A plain `QLabel` killed it too.
6. *That panel's leaked test widgets.* `test_quantum_chemistry_panel.py`
   abandons 15 panels and accounts for 104 of 138 late destructions;
   giving it the per-widget disposal recipe and re-adding the fatal
   widget **still died at the same test index**.

##### AN ARM THAT DOES NOT RUN IS NOT AN ARM

Three arms reported a comfortable "no crash" and were worthless.
**Removing the widget under test usually breaks MainWindow
construction**, so the tests ERROR instead of running -- and the crash
needs a MainWindow to exist. A harness that only greps for
`fatal exception` scores that as a pass. Check the passing-test COUNT
against the control:

```bash
uv run --no-sync python -m pytest -q tests/test_receptor_library_dialog.py tests/test_regulatory_calculator.py 2>&1 | tail -1
```

That pair is the **20-second reproduction**, and having one is what made
the root cause findable at all after three phases of 3.5-minute arms.

This is the second version of a lesson already in this file. The first
was a mutation script whose edit never landed; this is an edit that
landed and a test that never ran.

##### If it ever comes back

The signature is a truncated `-q` progress line, then
`Windows fatal exception: code 0xc0000374`, then a traceback whose top
frame is `conftest.py ... pytest_runtest_logfinish` / `Garbage-collecting`.

Count how far it got and name the test:

```bash
awk '/^[.sFEx]+/ {gsub(/[^.sFEx]/,"",$0); n+=length($0)} END {print n}' /tmp/suite.log
```

**Pin the baseline before blaming yourself OR the suite**: `git stash`
everything and run master. This file's warnings about flaky access
violations elsewhere would otherwise excuse a crash that is entirely
reproducible and entirely yours.

###### AND CI HAS SEEN IT NOW, which nothing above had established

Every measurement in this section was taken locally. **PR #43's run
32794020310 crashed on the hosted Windows runner**, 2026-08-25, which moves
the class from "a thing this machine does" to "a thing the suite does".

    crashed at test 4608 of 5591   tests/test_result_reduction.py
    then 37 more dots, exit 1      and NO SUMMARY LINE
    the three gates                skipped, as a red suite always takes them

**`--log-failed` RETURNED NOTHING, CORRECTLY, AND THAT IS THE TRAP.** There
is no failing test to name -- so the first two searches for one came back
empty and read as a broken log rather than as a crash. The pair this file
insists on is what answers it: a summary line that must EXIST, and a count
of `Windows fatal exception`.

**THE VICTIM BUILDS NO QT OBJECT AT ALL.** `tests/test_result_reduction.py`
reduces results to table columns; there is no widget, no window and no event
loop in the file. That is the signature rather than a surprise -- the
corruption is in FREEING a member of a cycle, so whichever test is running
at that instant is chosen by heap layout.

**THE COMMIT THAT "CAUSED" IT EDITS FOUR DOCUMENTS AND ADDS ONE QT-FREE
TEST.** `tests/test_gutmann_bridge.py` gained
`test_the_solvent_count_is_the_merged_one`, which sorts before
`test_result_reduction.py` and shifts every later index by one. That is the
documented trigger exactly: the widgets never cause anything, they shuffle
the heap until the freed window's memory is next to something that matters.

Three cheap checks before the flake verdict, and the third is the one that
settles it:

    the runner image        IDENTICAL to the previous green run
                            (windows-2025-vs2026, 20260818.207.1), so no
                            image bump to blame
    the same tree locally   5576 passed, 15 skipped, 0 crash markers
    a re-run, SAME SHA      5571 passed, 19 skipped, 1 deselected,
                            0 crash markers, all three gates EXECUTED

**A RE-RUN ON THE SAME SHA IS THE DISCRIMINATOR AND COSTS ONLY WALL
CLOCK.** `gh run rerun <id> --failed` re-uses the ORIGINAL commit -- normally
the trap this file warns about, and here exactly what is wanted: a second
sample of one tree. The same move settled the ORCA scratch-cleanup flake.
The merge commit then made it three CI samples, one crashed.

**AND IT HAPPENED AGAIN ON PR #50, WHICH IS THE SECOND CI INSTANCE.** Run
33029344304, 2026-08-27:

    first attempt   crashed at 83%, `0xc0000374`, top frame
                    `conftest.py pytest_runtest_logfinish` /
                    `Garbage-collecting` -- the same site as before
    the three gates skipped, exactly as a red suite always takes them
    re-run, SAME SHA   6085 passed, 19 skipped, 1 deselected,
                       all three gates EXECUTED, naming 181/181

So the discriminator worked a second time and cost one wall-clock cycle.
Worth recording because the branch under test was editing `conftest.py`,
which makes "I broke it" the obvious reading -- and the census it was
changing is **switched off unless `OPENCHEM_CENSUS` is set**, which no
workflow did at the time, so every line of that change was inert on CI.
**Check whether your change is even LIVE on the job that failed before
believing you caused the failure.**

**THE TWO SKIP COUNTS ARE NOT A DISCREPANCY.** CI's 19 against the local 15
is the four GPU-gated gallery guards, and 5571 + 19 + 1 reconciles to the
5591 a local `--collect-only` reports. Check that before reading a CI figure
as five lost tests.

## A UI MUST NOT INFER SCIENTIFIC MEANING FROM A DATASET'S SHAPE

Reported as "the logp calculator is a bit confusing... I assume the
overall partition is that number 3.624, but on the detailed viewer that
number is not there". The Properties panel said `mol_logp 3.624`; the
Calculator Inspector beside it said `Overall: 0.8585`.

**Neither number was a chemistry error.** `Overall:` was
`sum(result.values.values())`, on the stated belief that everything the
dialog shows is additive over the atoms present. Measured on aspirin
across every per-atom calculator in the registry, that belief was wrong
three ways at once, meaningless twice more, and merely mute four times:

    crippen_logp_contrib       0.1511   real LogP 1.3101
    crippen_mr_contrib         35.51    real MR   44.71
    gasteiger_charge_at_ph     -1.359   the molecule is NEUTRAL
    orbital_electronegativity  134.8    summed eV, no referent
    topology_eccentricity      65       summed hops, no referent
    topology_distance_degree   492      2x Wiener, unnamed
    atom_sasa                  220.7    correct, and never said as WHAT
    atomic_polarizability      18.11    correct, unnamed
    huckel_pi_density          10       correct, unnamed

The first three share one cause: **Crippen and PEOE both give hydrogens
their own increment, and the editor's hydrogens are implicit**, so those
increments have no atom to sit on. Verified --
`sum(_CalcCrippenContribs(AddHs(mol)))` equals `MolLogP(mol)` exactly on
every molecule tried.

**THE FILE ALREADY KNEW.** `calculator_inspector_dialog.py`'s ESP branch
documents "gave neutral acetic acid a net -0.40 e" (re-measured: -0.4008)
while a branch 150 lines above printed that same sum as a total. Two
statements about one quantity, in one file, disagreeing.

**A LIST OF NUMBERS DOES NOT SAY WHETHER ADDING IT UP MEANS ANYTHING.**
The producer knows; the producer declares. `Provenance.parameters[TOTAL]`
carries `{declared, value, label, units, basis}` or
`{declared: False, reason}`, and `domain/common.valid_total_declaration`
is **structural only** -- it checks a value is numeric and a label is
non-empty, never that "A^2" is right for a surface area. Validating that
here would rebuild, in the layer being fixed, the very "the UI decides
what numbers mean" engine the key exists to remove.

That split is asserted directly:
`test_a_plausible_lie_passes_the_validator_and_fails_the_chemistry`
declares `label="LogP (Crippen)", value=sum(values)` and requires the
validator to ACCEPT it and the Crippen guard to REJECT it. If the
validator ever catches it, semantics have leaked back.

**`Overall:` had already been narrowed twice** -- for spectra, then for
categorical results -- each time by finding another special case the hard
way. Inverting the default is what ends that: no declaration, no
headline. Same instinct as `applies_to`'s restrictive default and the
same rot `inapplicable_calculators` suffered.

**A CATEGORICAL DATASET NEEDS NO SECOND DECLARATION.** `CATEGORICAL_SCALE`
already says "these are category ids, not magnitudes", which is the same
statement; requiring `TOTAL` as well would put one claim in two places.
The audit accepts either.

### The residual is the VIEW's arithmetic; its meaning is the PRODUCER's

The dialog says *"21 heavy-atom contributions sum to 0.86 - the balance
(+2.77) is on implicit hydrogens."* Subtracting two numbers is ordinary
work for a view. Concluding that the remainder IS the hydrogens is
chemistry, and this file already records what inferring a mechanism from
a residual costs. So the producer supplies `{visible_basis, explanation}`
and nothing else; with no explanation the gap goes unmentioned.

**And the sentence is suppressed within the displayed precision.** The
two hydrogen modes that DO add up reproduce their total to ~1e-16, so
without a tolerance every one of them would announce a balance of
+0.0000000000000002 -- noise given a voice.

### The hydrogen fold already existed, under Marvin's name

`gasteiger_charge_at_ph` has shipped "Increment of Hs (add implicit H
charge)" since Phase 18, and it takes acetic acid's charge sum from
-0.4008 to -0.0000. The same fold on Crippen reproduces `MolLogP` to
1e-9 (ethanol, benzene, aspirin, caffeine, morphine). Both Crippen
calculators now offer three modes; **the declared total is identical in
all three**, which is the guard that a display option never reaches the
chemistry.

`Explicit hydrogens` is a pure addition, measured rather than assumed
before being built on: `AddHs(addCoords=True)` moves every heavy atom by
**0.00e+00** in 2D and on a real conformer, leaves 0 overlapping pairs,
gives the new hydrogens real non-zero z, and `PrepareMolForDrawing`
KEEPS them (8 in, 8 out). Without an explicit-H depiction the labels are
silently dropped by `render_2d_svg`'s `drawable()` guard -- whose
docstring already described this situation for SASA and polarizability.

### THE REGISTRY AUDIT IS THE PART WORTH KEEPING

`tests/test_declared_totals.py` enumerates **from the live registry**,
never from a list of ids, and fails naming any calculator whose per-atom
result carries no `TOTAL` key. A maintained list is exactly what
`inapplicable_calculators` was when it rotted into 27 wrong entries. It
is what covers calculator #37, which nobody has written yet.

### Three smaller findings from the same screen

- **EVERY descriptor row was captioned with its raw id**, and lost its
  units: `mol_logp`, `mol_wt`, `tpsa`. `DescriptorService` publishes a
  RUNNING placeholder per id BEFORE `compute()` runs -- so it can only
  fill in `name=descriptor_id, units=""` -- and the panel wrote the row
  caption once, at creation. Measured 26 of 26 wrong. It cannot be fixed
  at the producer: the placeholder precedes the names, and the consumer
  is the only place that sees both.
- **The legend printed the COLOUR DOMAIN as the data range.** For signed
  data the scale is symmetric about zero, so it named +1.019 when no atom
  had it, while the panel an inch away said 0.5437. Two quantities, one
  name. They have separate names now (`data_range` vs the colour domain)
  specifically so a later simplification cannot merge them again.
- **One dataset rendered at four precisions on one screen** -- 2 dp atom
  labels, `.3f` legend, `.4g` headline, `.4g` panel row. All of them go
  through `label_decimals` now, and the balance tolerance derives from it.

### A BRANCH MEASURED A STARVED SECTION THAT MASTER HAD ALREADY FIXED

Kept because both halves are instructive: the measurement was right, the
conclusion drawn from it was obsolete before it was written, and only
looking at master said so.

Driving the app showed `LogP (Crippen) 3.62 - 21 atom contributions,`
ending flat against the panel edge with its range gone. Every test was
green. `OPENCHEM_INSTRUMENT_PANEL=1` gave the reason -- the Lipophilicity
section starved at 145 px against a 192 px minimum, so the result row was
handed 34 whatever it asked for -- and the branch responded by shortening
its own row to fit the shortfall it found.

**That shortfall was a bug with a fix already on master.** The section
above, `A STYLE CHANGE RE-ARMED THE HEIGHT-FOR-WIDTH FLAG`, is the same
145/192 measured independently a day earlier and repaired. Re-measured
after merging, with the `dump` drive step:

    arm                    row given/needs   section h / min
    total + count               47 / 47         192 / 192   ok
    total + count + range       63 / 63         208 / 208   ok

So the row carries everything it used to plus the total, and the guard
that pinned the shorter wording was deleted -- it would have held a
workaround in place for a bug that no longer existed.

**A CONSTRAINT DISCOVERED BY MEASUREMENT CAN STILL BE STALE.** Nothing
about the numbers was wrong; they described a tree eleven commits behind.
`git fetch` before concluding that a defect is pre-existing, and again
before shipping a design that works around one -- this branch also wrote
up two "pre-existing bugs, deliberately not fixed here" that master had
fixed while it was in flight, one of them with the exact one-line change
the write-up recommended.

**A bare Qt harness said the opposite of the app** -- it reported the
label wrapping to 4 lines and `CLIPPED: False`, because it had handed the
label 100 px instead of the real 205. That is the SIXTH time this file
has recorded an out-of-app harness disagreeing with the running
application about this panel, the fifth being in the style-change section
above, and the two were found within a day of each other by different
routes. Whatever else is true of that panel, do not measure it out of
process.

### `sum(x.values())` is not by itself evidence of this bug

Auditing every such call in the tree found only ONE offending site. The
hits in `electronic_properties.py` and `surface_analysis.py` are
PRODUCERS computing their own legitimate totals -- which is precisely
what they should be doing, and they now declare them. The rule is about
where a total may be INVENTED, not about arithmetic.

### A mutation that does not parse is not a mutation

Five arms, four caught by the guard they were aimed at. The fifth
replaced a call with text that did not parse, so the module failed to
import and **0 of 50 tests ran** -- and the harness scored it INVALID
rather than SURVIVED only because it compares the arm's ran-count against
the control's. This is the third time this file has recorded a version of
that lesson.

Method note paid for again in the same session: **an A/B is worthless if
the tree is being edited during it.** A source file was edited by hand
while the harness was mid-run, so the whole set was re-run on an
untouched tree before any result was believed.

## SOLUBILITY: an uncapped model, a 1000x review, and two defects only the screen showed

`chem/solubility.py` is the ChemAxon-shaped predictor -- intrinsic value,
value at a pH, Low/Moderate/High category, pH curve. Five things worth
carrying, each measured rather than reasoned.

**A PROBE THAT PASSES `None` FOR AN INTERPRETER PATH REPORTS "NOT
INSTALLED" ON A MACHINE WHERE IT PLAINLY IS.** `pka_predictor_available(None)`
and `admet_available(None)` both answered False while pkasolver and the
ADMET sidecar were configured and working. A whole design was built on
that -- including a Dimorphite-DL pKa fallback that was then measured and
found to put propranolol at 5.65 against a real 9.42, off by 3.8 -- before
the paths were read from settings. **Read the configured value; do not
probe with a placeholder.**

**UNCAPPED HENDERSON-HASSELBALCH REACHES 4.7e10 mg/mL.** Aspirin at pH 14,
which is 47 tonnes per litre: correct arithmetic, meaningless answer, the
same failure this file records at 40619 kcal/mol.

**TWO BOUNDS STOP IT AND THEY ARE NOT THE SAME CLAIM.** The first draft
had one symmetric +2.0, inferred from a single ChemAxon screenshot with
no source behind it. Avdeef's **"sdiff 3-4"** replaced it: in 0.15 M
NaCl the counter-ion salt precipitates once solubility exceeds intrinsic
by about FOUR orders for a weak acid and THREE for a weak base. Cited,
and asymmetric because a sodium and a chloride salt are not equally
soluble. On propranolol at gastric pH it moves the answer from 7 to
**70 mg/mL** against a real hydrochloride solubility near 50.

**THE READING WAS VERIFIED AGAINST THE PAPER'S OWN WORKED EXAMPLE**
rather than assumed: Avdeef gives amiodarone intrinsic 7.9e-9 M and Ksp
1.2e-6 M^2 "using the sdiff 3-4 approximation", and 7.9e-9 x 10^3 x 0.15
= 1.19e-6 reproduces it. That is what says the rule was understood, not
merely quoted.

**AND sdiff ALONE IS NOT ENOUGH, WHICH ONLY MEASURING SHOWED.** It is
stated for SPARINGLY-soluble drugs -- the paper's title -- and says
nothing about a compound whose intrinsic solubility is already
appreciable. Aspirin's uncapped rise of 3.91 never reaches an acid's
4.0, so the salt rule leaves it at **11,925 mg/mL**, twelve kilograms
per litre. A pure-compound ceiling of 1000 mg/mL catches the rest: a
solute cannot outweigh the solution holding it. The two are reported
separately, because "the salt precipitates here" and "past here the
number is meaningless" must not render as one sentence.

**THE FIX PARTLY DISSOLVED THE PROBLEM THAT MOTIVATED THE BOUNDED
SCREEN.** Under +2, propranolol saturated the entire ICH window. Under
the base limit of 3.0 its 2.60 at pH 6.8 fits underneath, so the window
carries real pH information again. Saturation is pushed back rather than
abolished -- a base above about pKa 10 still fills the window -- and the
verdict is unaffected either way, which is the point of it being bounded.

**THE LIMIT SATURATES THE ENTIRE ICH WINDOW FOR A STRONG BASE, and that
is the ordinary case rather than an edge one.** Propranolol (pKa 9.4)
wants +8.20 at pH 1.2 and +2.60 at pH 6.8, so every point in pH 1.2-6.8
hits the limit and the displayed spread across it is **0.000**. Found by
writing the guard, not by review.

**SO THE SAFEGUARD WAS DECIDING A REGULATORY VERDICT, AND A BOUND
REPLACED IT.** The first version returned `UNDETERMINED` whenever the
limit saturated -- i.e. for basic drugs as a class, on the strength of an
arbitrary constant. The fix is that the screen never reads the cap at
all. Two REAL bounds exist:

    S(pH) >= S0             ionization only ADDS dissolved species
    S(pH) <= uncapped HH    which assumes the salt never precipitates

so the dose number is sandwiched, and each side licenses ONE verdict --
PASS when even the pessimistic bound clears the criterion, FAIL when even
the optimistic one misses it. Measured: caffeine PASS, aspirin FAIL 1.36,
ibuprofen FAIL 26.7, ketoconazole FAIL 3497, propranolol genuinely
UNDETERMINED at 2.27 against 0.005. **Four of five get a sound answer
where the capped version gave one blank class**, and
`test_a_verdict_never_depends_on_the_adjustment_safeguard` runs the
screen at four different limits including none and requires one outcome.

**A CEILING BUILT FROM THE DISPLAYED CURVE IS NOT A CEILING, and the
mutation for it SURVIVED the whole file at first.** Swapping the uncapped
profile for the capped one understates solubility, so it can license a
FAIL the evidence does not support -- and no fixture noticed, because for
an ACID the window minimum sits at pH 1.2 where capped and uncapped agree
exactly, and propranolol at 40 mg lands on the same verdict either way.
The two only disagree about the OUTCOME when the dose falls in the gap
between them, which for propranolol is **1745-6989 mg**. The guard uses
3000 mg and asserts its own setup first. Same shape as the assembly
corpus blind to a transposed matrix: a fixture is not big or small, it is
degenerate or not with respect to a specific mutation.

**A REVIEW'S "MOST DANGEROUS CONVERSION BUG" WAS ITSELF THE BUG.** A
plan review proposed `mg/mL = 10**logS * MW / 1000`, in the point it
titled exactly that. It is wrong by 1000x -- 1 mol/L of MW 180.16 is
180.16 g/L, and a g/L IS a mg/mL. Checked against ChemAxon's own published
aspirin figure, which is categorised High and needs 2.79 mg/mL; the
proposed form gives 0.0028 and classifies it Low. **Every category would
have been wrong.** Three review rounds were taken point by point and two
of their points were rejected on measurement; the rest improved the work.
Do not apply a review wholesale, and do not dismiss one either.

**A FIXTURE SAT 0.00002 mg/mL FROM THE BOUNDARY.** Ibuprofen was the
obvious molecule for "the category must read the baseline, not the
pH-adjusted value" and is degenerate: its ESOL baseline is 0.06002 mg/mL
against a 0.06 threshold, so it reads High on BOTH sides and the mutation
is invisible. Diclofenac is 0.0019 (Low) against 0.19 (High) -- two bands
apart, neither near a threshold. Same lesson as the assembly corpus that
could not see a transposed matrix.

### IONIZATION SITES MULTIPLY. THIS CODEBASE SUMMED THEM FOR YEARS.

Found by reading Avdeef 2007 (Adv Drug Deliv Rev 59:568-590, doi
10.1016/j.addr.2007.05.008) Table 1 after Alex fetched it. The bug was in
`logd_henderson_hasselbalch`, so it reached logD, the logD curve, CNS MPO
and BBB descriptors -- not only the new solubility code.

    WRONG   log10(1 + sum of terms)
    RIGHT   sum of log10(1 + term)

A sum never reaches the doubly-ionized scaling, because getting there
needs BOTH protons off and the sum has no term for it. Measured on a pKa
3.0/4.5 diacid at pH 8: the summed form understates the adjustment by
**3.49 log units**, and at pH 12 by 5.5.

**ONE SITE IS WHERE THE TWO FORMS AGREE**, which is exactly why it
survived: monoprotic answers are bit-identical under both, and monoprotic
is the overwhelmingly common case. Every pre-existing pinned value in
`test_logd.py` that survived the change is a single-site one, and the two
that moved are the diprotic and the ampholyte.

**THE CORRECT MATH WAS ALREADY HERE, ONE MODULE AWAY.**
`ph_curves.microspecies_fractions` builds the beta-product from
successive dissociation constants and has since it was written. Two
implementations of one piece of chemistry, one right, coexisting -- which
is the whole argument for the shared `ionization_log_factor` that
replaced them.

**A TOLERANCE WOULD HAVE BURIED A REAL DISTINCTION.** The independent-site
product and Avdeef's Table 1 disagree by 4.3e-6 at pH 8, and the first
instinct was to widen `abs=1e-9` until they matched. They are not meant to
match: Avdeef's constants are MACROSCOPIC (the singly-ionized species
lumps both microstates) and ours are per-SITE -- `ph_curves` already
records that pkasolver "predicts per-site values, which are closer to
microscopic constants". The product is the form matching our inputs, and
`test_the_microscopic_and_macroscopic_forms_differ_and_we_use_the_right_one`
pins the difference rather than rounding it away.

The renamed function is the signal: `ionization_factor` returned a bare
sum, `ionization_log_factor` returns the log. A silent semantic swap under
the old name would have been the worst of both.

### THE BENCHMARK, AND A LEAK THAT WAS NOT THE OBVIOUS ONE

`benchmarks/solubility/` scores ESOL against the Solubility Challenge
(Llinas, Glen & Goodman 2008), taken from the AqSolDB repository's
`dataset-I`. Measured 2026-08-16, 61 scored of 80:

    all      n=61  MAE 0.74  RMSE 0.98  median 0.52  max 2.65  bias -0.17
    neutral  n=16  MAE 0.80                                    bias +0.02
    acid     n=18  MAE 0.55                                    bias +0.26
    base     n=27  MAE 0.84                                    bias -0.59

**THESE SUPERSEDE 67/-0.20/+0.06/-0.52, AND THE REASON IS NOT DRIFT.**
Three compounds appear in SC-1 under one InChIKey as two solid forms, and
`score.py` was scoring both -- counting them twice AND charging the
polymorph gap (up to 0.88 log) to the model as prediction error. Refusing
them is what moved every figure here; see the polymorph section below.
The old numbers are still in PR #28's body, which is immutable history.

**THE STRATIFICATION EARNED ITS KEEP ON THE FIRST RUN.** The aggregate
bias is -0.17 and reads as noise. Split by class, ESOL under-predicts
BASES by more than half a log unit while acids sit at +0.26 -- a
systematic error across a third of a druglike set, invisible in a single
MAE.

**AND IT REPLICATED ON A SECOND, INDEPENDENT SET.** The Solubility
Challenge 2 tight set (Llinas, Oprisiu & Avdeef 2020, Table 1, doi
10.1021/acs.jcim.0c00701) gives base bias **-0.42** against SC-1's -0.59,
on 73 different compounds. One set makes a bias a curiosity; two make it
a property of the model. Delaney's paper mentions ionization, amines and
salts ZERO times, so ESOL cannot tell a base from a neutral of the same
size and lipophilicity -- the bias is domain, not a fixable defect.

**A NUMBER WITHOUT A BASELINE SAYS NOTHING.** On the same 73 compounds
the General Solubility Equation scores RMSE 1.18 against ESOL's 1.26 --
and the GSE needs a MEASURED MELTING POINT that this app does not have.
So the honest reading is "the endpoint is hard", not "our model is poor".
The paper also gives the noise floor: interlab SD 0.17, and CheqSol
against high-quality shake-flask at RMSE 0.34. Nothing can score below
that.

**A CLAIM IN THIS FILE WAS OVERTURNED BY THE BETTER MEASUREMENT.** The
solubility module used to say ESOL beat Marvin on Marvin's own
documentation molecule, resting on an ESOL-era experimental value of
-2.19 for aspirin. SC-2's interlaboratory mean over 16 sources is
**-1.67**, and against that Marvin (0.14 off) and AqSolDB (0.05) both
beat ESOL (0.42). The old row is kept with its correction beside it
rather than edited away, because "where did that number come from" is the
question a reader will have.

**EXTRACTING A TABLE FROM A PDF NEEDS AN ACCEPTANCE TEST, and the paper
supplies one.** Table 1 closes with a Min/Max/Mean row. The first
extraction produced a perfectly plausible **129 rows** by running past the
end of Table 1 into Table 2 -- the "contentious" set, interlab SD 0.62 --
silently mixing two data qualities. Recomputing the summary row is what
caught it; the count alone would not have, because 129 looks as
reasonable as 100. Two further defects fell out of the same check: a row
split across a page break (`bromazepam`), and a melting point carrying a
footnote marker (`193b`) that a plain numeric match rejects.

**AND THE NAME RESOLUTION WAS NOT REPRODUCIBLE UNTIL IT WAS CACHED.** Two
consecutive PubChem runs over the same 100 names returned 100 and then
97; diazoxide, diclofenac and nortriptyline dropped out to rate limiting.
A corpus whose membership depends on network luck is not a corpus, and
nothing says so unless somebody compares row counts. It caches, retries,
and an unresolved name is now fatal rather than a warning.

**THE ANTI-LEAK RULE CAUGHT THE MODEL NOBODY SUSPECTED.** Refusing to
score the AqSolDB sidecar on AqSolDB was the obvious half and was in the
plan. The half that was NOT: **the merged AqSolDB contains Delaney's own
ESOL set as one of its nine sources**, so the first design would have
scored ESOL against its own fit. Verified against the AqSolDB README
rather than recalled -- `dataset-G` is reference [7], Delaney 2004.
`fetch.py` downloads that set purely to SUBTRACT it: 14 of 94 rows share
an InChIKey and are dropped. **An evaluation set assembled from other
people's datasets inherits all of their provenance**, and "is this model
trained on this data" has to be asked of every model, not just the one
whose name matches the file.

**16% OF A DRUGLIKE SET IS REFUSED** -- 13 of 80 are ampholytes. That is
a large slice to decline, and it is printed beside the accuracy so the
two can never be read apart; a model that refuses its hard cases looks
better the more it refuses.

**AND THE ORIGINAL PLAN'S DATA SOURCE DID NOT WORK.** TDC's Harvard
Dataverse returned 403 and PyTDC then cached the 0-byte failure as a
"local copy", so every retry reported "Found local copy..." before
failing -- which reads as a code bug rather than an outage. The GitHub
route needs no PyTDC, no throwaway virtualenv and no Dataverse, and it is
the one that exposes the constituent datasets the de-leaking depends on.

### AND TWO DEFECTS THAT ONLY THE RENDERED WIDGET SHOWED

Every unit test passed, 55 of them, and the panel looked right in the
app. Rendering the CURVE view at real font size showed both at once:

- **Four of seven facts sat behind a collapsed heading.** `FactCategory`
  STRUCTURE is not in `DEFAULT_EXPANDED`, so the stats block whose whole
  purpose is showing the intrinsic solubility beside the chart was
  showing only the method.
- **The status line advised choosing "Everything" from a combo box that
  had been deliberately hidden.** `show_controls=False` hides the depth
  filter; it did not stop the filter applying, or the hint referring to
  it.

Both come from one cause and take one line: **when the controls are
hidden, nothing may hide behind them.** `FactView._compact` derives from
`show_controls`, so the depth filter is off and every section starts
expanded. `test_hiding_the_controls_hides_nothing_behind_them` is the
guard and `test_the_full_view_still_collapses_and_filters` is its
control -- the second matters because the fix is in shared code and the
control-bearing form must be untouched.

**THE HEADLESS GRAB UNDER `offscreen` COULD NOT HAVE FOUND THEM.** That
platform has no fonts, so every label renders as tofu boxes: the chart's
SHAPE was verifiable there and not one word of text was.
`QT_QPA_PLATFORM=windows` with `widget.grab()` gives real fonts without
needing the whole application, which is the cheapest form of the rule
this file states six times over.

### 91 SOLVENTS, BY LOOKUP ON BOTH SIDES -- and three deferrals that were wrong

`chem/abraham.py` answers for solvents other than water using Abraham's
solvation equation, `log Ss = log Sw + c + eE + sS + aA + bB + vV`. Both
halves are LOOKED UP, neither is predicted: 91 measured solvent
coefficient sets (Bradley, Abraham & Acree, BMC Chemistry 2015, doi
10.1186/s13065-015-0085-4, Table 1) and 2193 measured solute descriptor
sets (Bradley, Acree & Lang, figshare, doi 10.6084/m9.figshare.1176994).
`tools/build_abraham_tables.py` fetches both; both are CC BY 4.0 and both
shipped JSON files carry their attribution.

**THIS FILE AND ARCHITECTURE.md BOTH SAID IT COULD NOT BE BUILT, FOR
THREE REASONS, AND TWO OF THEM WERE FALSE.**

- *"`E` is derivable from Crippen molar refractivity."* Measured and
  killed: hexane's Crippen-derived value is **0.805** against a defined
  `E` of **0.000** -- hexane IS the n-alkane reference `E` is an excess
  over, and MR does not carry that reference.
- *"Ethanol is structurally unreachable because it is miscible with
  water."* False, and it cost a round of the work. No two-phase partition
  coefficient exists for a miscible pair and the UFZ LSER database omits
  ethanol for exactly that reason -- which is what made this look
  structural rather than like one database's scope. **Abraham's
  coefficients here come from SOLUBILITY RATIOS**, so neat ethanol is in
  the measured table.
- *"`S`, `A` and `B` need the Platts fragment scheme."* True, and no
  longer binding. The scheme would work and is ~480 coefficients and ~132
  hand-written SMARTS patterns, every one a place for a silent error, with
  fragments 59-67 defined in a FIGURE and so unreadable from the PDF's
  text layer. **Looking up an experimental descriptor costs none of that
  and carries none of its 0.7-1.0 log error.**

The general lesson is the one the assessment doc now leads with: a
deferral's REASONS rot independently of its verdict, and the route that
finally worked is the one all three reasons had ruled out.

**TWO QUALITY GATES IN THE SOURCE, AND ONE IS A TRAP.** A `donotuse`
column with a written reason (6 rows), and **`-123` as a missing-value
sentinel** (513 rows), which `float()` reads as a perfectly ordinary
number. A single leak puts a wildly negative descriptor into a prediction
that still looks like a prediction;
`test_the_missing_value_sentinel_never_reached_the_shipped_table` walks
every shipped row.

**A DUPLICATE IS MERGED BY MEDIAN WITH ITS SPREAD KEPT PER DESCRIPTOR.**
432 InChIKeys appear more than once and only 51 of those groups agree
exactly; the widest single-descriptor disagreement is 2.24. Acetanilide
settles the design -- three rows give `S` = 3.61, 1.54, 1.37 and the
FIRST is the outlier, so "take the first row" would have shipped it. The
spread propagates into a stated uncertainty and refuses past 1.0 log,
because a solvent coefficient of -4.9 turns a 0.3 disagreement in `B`
into 1.5 log units on the answer.

**PER DESCRIPTOR, NOT ONE BLANKET NUMBER.** The first bound multiplied
the single widest spread by the SUM of all five coefficient magnitudes --
assuming every descriptor is wrong by the worst amount, all in the same
direction -- and refused aspirin, caffeine and ibuprofen, **three of the
first four drugs tried**. A bound that rejects the ordinary case is not a
safety feature.

**ACETIC ACID IS ABSENT DELIBERATELY.** The paper also PREDICTS
coefficients for 293 further solvents and says of those "not as gospel".
Only the 91 measured ones ship, which is the same call already made
against Miller polarizability, HLB and TSEI. Alex asked for acetic acid
by name, so this one is a refusal with a reason rather than an oversight.

#### AND THE RENDERED PANEL FOUND THREE MORE, WITH ALL 101 TESTS GREEN

Same lever as the two above, one feature later, and the second of the
three is the sharpest thing in this section.

- **A row labelled "Predicted intrinsic solubility" carried an ETHANOL
  number.** `baseline_logs` already includes the Abraham shift, so three
  unqualified rows reported 52.81 mg/mL in the wording every other part
  of the app uses for the aqueous value.
- **ChemAxon's Low/Moderate/High were being applied outside water.**
  Those thresholds are defined on INTRINSIC AQUEOUS solubility -- they
  encode expectations about dissolution in the gut -- so "High" for 52.81
  mg/mL in ethanol borrows an aqueous verdict's authority for a different
  question. **This is the same scoping mistake the BCS screen is guarded
  against ONE FUNCTION AWAY**, written in the same session, and it was
  still missed: getting a rule right in one place does not apply it in
  the next. It is a refusal with a reason now, not an omitted row, since
  a missing row reads as "not computed yet".
- **The panel repeated one value four times.** With no pH adjustment
  outside water the "baseline" rows and the "at pH" row coincide exactly.
  Invisible to every test, which read LABELS rather than asking whether
  two rows said the same thing.

**A REFUSAL THAT NAMES THE WRONG CAUSE IS WORSE THAN A VAGUE ONE.** The
non-aqueous BCS path first reused `BcsReason.UNSUPPORTED_SPECIES`, whose
text is "this species is outside the model" -- false, and it sends the
reader to fix their molecule. `NON_AQUEOUS_SOLVENT` says ICH M9 is
defined on aqueous media. Same family as "reusing a command whose
invariants do not apply is not reuse", one layer down in an enum.

**TEN MUTATIONS, TEN CAUGHT** -- but the tenth arm is the one worth
keeping. `varies_with_ph` losing its `is_water` term **SURVIVED** at
first, and it is not a blind test: its ONE caller already returns for a
non-aqueous solvent several lines earlier, so the term cannot change any
rendered output. Asserted directly on the predicate instead, which is
this file's existing "an unreachable branch is a question about where to
assert" applied a second time. **And that guard's own setup assertion
then caught its fixture being degenerate** -- without a pKa in BOTH arms,
aspirin classifies UNSUPPORTED in ethanol too, so `varies_with_ph` was
False for a reason having nothing to do with the solvent.

**pH, THE ICH SCREEN AND THE CURVE STAY WATER-ONLY.**
Henderson-Hasselbalch, the pKa values behind it and the regulatory window
are all defined on aqueous media. A non-aqueous solvent gets an intrinsic
solubility and no pH story rather than an authoritative-looking curve
that means nothing.

#### ACETIC ACID: REFUSED BY THE BOUND THAT WAS ALREADY THERE

Alex asked for it by name, so "not in the table" was not an acceptable
answer. The paper DOES predict its coefficients, so the question is
whether a published prediction can ship. Two measurements say no, and the
first uses no new policy at all:

**IT FAILS THE EXISTING UNCERTAINTY BOUND.** Propagating the paper's own
Table 4 out-of-bag RMSE (`e` 0.181, `s` 0.326, `a` 0.477, `b` 0.471,
`v` 0.228) through the same `sum(|error| * descriptor)` the module already
applies to measured-descriptor disagreement:

    aspirin 1.57   caffeine 2.04   ibuprofen 1.34   paracetamol 1.76
    benzene 0.51

against a ceiling of 1.0. Caffeine is a factor of 110. Only benzene
passes, and a solvent that works for benzene and no drug is not an option.
Two coefficients are poor at the source -- OOB R^2 **0.308** for `e` and
**0.474** for `b`, against in-sample 0.885 and 0.903, which is the overfit
gap and the paper flags it itself.

**AND THE PREDICTED TABLE IS THE WRONG PARAMETERISATION.** It carries only
the `c = 0` refit (`e0 s0 a0 b0 v0`), which is the paper's equation 3 for
log P and exists to make solvents comparable. The solubility equation is
equation 2 and needs the intercept: ethanol's measured `c` is +0.222 and
the predicted table has no column for it.

**THE GOOD MESSAGE WAS UNREACHABLE FOR THE ONE CASE IT EXISTS FOR.** It
was written into `solvent_shift`, and `resolve_solvent` refuses an unknown
solvent several layers earlier -- so acetic acid never reached it and the
user still got "91 solvents are supported". `predicted_only_reason()` is
one function called from both, because writing the sentence twice is how
two refusals drift into disagreeing.

**THE NAMES SHIP, THE NUMBERS DO NOT.** `predicted_only` in the solvents
JSON is 118 bare names so a refusal can be specific; a test asserts no
coefficient is ever shipped beside them.

**AND "293 FURTHER SOLVENTS" WAS WRONG IN FOUR DOCUMENTS.** 293 is the
TOTAL the paper considers (sustainable + classic + measured), of which 91
are measured -- so 202 are predicted-only, and the article's own table
lists 118 of them. Written from memory of the abstract rather than from
the sentence, which reads "a complete set of coefficients for all 293
solvents (sustainable, classic, and measured)".

#### THE NON-AQUEOUS BENCHMARK: TWO ARMS ARE CLAIMS, ONE IS NOT

**THE LEAKAGE IS STRUCTURAL AND CANNOT BE ENGINEERED AWAY.** Abraham's
solvent coefficients are, in the source's own words, "obtained by linear
regression using experimentally determined partitions and SOLUBILITIES of
solutes with known Abraham descriptors". The endpoint being scored IS the
endpoint they were fitted to -- the AqSolDB/ESOL circularity in a new
place, and this time unavoidable rather than fixable by subtraction.

`benchmarks/solubility/nonaqueous.py` is built around that. The ONS
Solubility Challenge dataset carries a CITATION column, so rows from
Abraham or Acree publications can be dropped -- 1998 of 9536, 21%. That is
the only handle that exists and it is a PARTIAL defence, since their
coefficients may rest on measurements other people published.

Measured 2026-08-16, 968 de-leaked cases, 159 solutes, 70 solvents:

    composite  our prediction vs measured    786  MAE 0.68  RMSE 0.96  HONEST
    baseline   our ESOL vs measured aqueous  786  MAE 0.61  RMSE 0.85  HONEST
    shift only predicted vs measured shift   786  MAE 0.29  RMSE 0.49  OPTIMISTIC

**THE COMPOSITE BEING BARELY WORSE THAN THE BASELINE IS THE RESULT.** It
confirms the module's claim -- a non-aqueous answer is an ESOL prediction
moved by a measured shift, so ESOL dominates the error -- and that claim
does NOT require the shift to be validated, which is why it can be made at
all. **Design the benchmark around the claim you can support**, not around
the one you wish you could.

**AND THE CONTROL MAKES THE LEAKAGE VISIBLE.** `--keep-leaked` improves
the shift arm from **0.29 to 0.21 MAE** -- the coefficients looking 28%
better on data they were fitted to -- while the composite barely moves
(0.68 -> 0.69). **A de-leaking rule whose effect you cannot see is a
de-leaking rule you have not tested**, and this one is measured in both
directions.

**`solvent_choices()` PUTS WATER FIRST, and that is not cosmetic.**
`sorted(SOLVENTS)` buries the default at position 88 of 91, and water is
not merely the default -- it is the solvent the pH curve, the BCS screen
and the entire benchmark are about. The refusal message names six
FAMILIAR solvents filtered against the real table, because the first six
alphabetically are `1,2-dichloroethane` and `1,9-decadiene`, which answer
"is my solvent here?" for nobody.

### THE BASE BIAS IS REPORTED, NOT CORRECTED -- and the test said so

`benchmarks/solubility/base_bias.py` put an adjustment for ESOL's base
bias through a cross-corpus HELD-OUT test whose criteria were fixed before
it was first run. **Outcome: `SURFACE_ONLY`.** Four of five criteria pass:

    offsets        +0.586 / +0.422, agreement 0.165        PASS
    base RMSE      0.822 -> 0.780 and 1.101 -> 0.932       PASS
    overall MAE    not worse either direction              PASS
    improvement CI [-0.231,+0.397] and [-0.0009,+0.300]    FAIL, both include zero

**ONE OF THEM MISSES BY 0.0009**, which is the entire argument for fixing
a threshold in advance. A criterion chosen after seeing that number is a
description of it, not a test.

**THE OVERLAP REMOVAL IS WHAT MADE IT UNDERPOWERED, AND IS ALSO WHAT MADE
IT HONEST.** The two corpora share 20 compounds, 7 of them bases, so the
held-out arms fall to n=10 and n=20. Two corpora that look like
independent validation are less independent than their sizes suggest --
without that exclusion this would have "passed" spuriously.

**A PRE-REGISTRATION CAN BE DEFECTIVE, AND AMENDING IT IS NOT CHEATING IF
NOTHING HAS BEEN SEEN.** v1 halted on its FIRST run having computed
nothing: SC-1 carries `chlorprothixene_form_I` and `_form_II` under one
InChIKey at -6.75 and -5.87. That is one compound as two solids, not a
corpus contradicting itself, and v1 conflated them. v2 drops polymorph
pairs, and the amendment is recorded in the docstring with the reason it
was admissible -- no offset, no arm and no verdict existed yet.

**AND IT FOUND A DEFECT IN THE SHIPPED SCORER.** `score.py` was counting
those three compounds TWICE and charging the polymorph gap -- up to 0.88
log, the size of the bias under investigation -- to the model as
prediction error. Refusing them moved acid bias +0.06 -> +0.26 and base
bias -0.52 -> **-0.59**, i.e. the fix makes the bias LARGER, not smaller.

#### MORE DATA DID NOT HELP, AND THE REASON IS WHICH SIDE IT LANDS ON

The obvious answer to a CI that missed by 0.0009 is more compounds. Two
further corpora were extracted from `avdeef2020.pdf` (v3 of the criteria,
written before they were run) and the verdict stayed `SURFACE_ONLY`:

    A1  Yalkowsky & Banerjee 1992   19 rows -> 5 after de-leaking, 0 bases
    A2  Hopfinger et al. 2009       27 rows -> 23, 7 bases

**POWER IS SET BY THE TEST SIDE, NOT THE FIT SIDE.** Neither new corpus
has the 10 bases needed to BE a held-out side, so both can only join the
fit pool -- which moves the fitted offset and narrows nothing. Measured:
the SC-1 arm's CI lower bound went **-0.0009 -> -0.0338**, slightly
FURTHER from significance. Adding data to the wrong side of a held-out
split is not adding power.

**A1 IS 74% INSIDE ESOL'S OWN TRAINING SET** -- 14 of 19 rows share an
InChIKey with Delaney's fit, and it yields zero bases. Yalkowsky &
Banerjee 1992 is a classic compilation of industrial and agrochemical
solubility, which is the chemistry ESOL was fitted on. Extracting it
anyway is what turned a suspicion into a number; dropping it unmeasured
would have been assuming the answer.

**TWO OF AVDEEF'S FIVE APPENDIX TABLES ARE THE SC-2 SETS UNDER OTHER
NAMES.** A3 is the tight set, A4 the loose set -- so a bulk extractor over
those pages would have double-counted data the project already had and
INFLATED the power of the experiment it was meant to strengthen. A naive
row count over pages 35-44 gives 172 compounds and the honest independent
gain is 49. `extract_avdeef_sets.py` refuses A3/A4/A5 by name and says
why.

**THE OUTCOME VOCABULARY EARNED ITS SPLIT.** `insufficient_evidence` (the
CI spans zero) and `contrary_evidence` (an arm got worse) are recorded
separately, because "we could not show it" and "we showed it does not
work" are opposite findings that read alike in a bare SURFACE_ONLY. The
adjustment does substantially remove the bias in-sample -- base bias
-0.619 -> -0.108 and -0.351 -> +0.265 -- which is exactly why the
distinction matters.

`production_change_permitted = false` is emitted for every non-SHIP
outcome, and `git diff src/` was checked empty: a guard against fixing the
model after an inconvenient result.

#### A FACT-LEVEL LIMITATION IS A TOOLTIP, AND A TOOLTIP TELLS NOBODY

Both new notes were attached to the `Fact`, rendered correctly, passed
every test -- and were **invisible on screen**. `FactView._add_row` puts
`fact.limitations` into the ROW'S TOOLTIP; only `report.limitations`
reaches the status line under the panel. Found by grabbing the panel,
which is the fourth defect this feature has produced with a green suite.
They are carried in BOTH places now: on the fact for the tooltip and the
export, and on the report so somebody actually reads them.

#### THE ARM STATUS IS A CLOSED ENUM, ATTACHED TO THE NUMBER

`nonaqueous.py` hand-typed `(HONEST)` into the printed TITLE while its
`--json` carried no status at all, so the two could drift and a machine
reader got the figure naked. `ArmStatus` + `ARM_STATUS` is one source
feeding both, the shift arm is `OPTIMISTIC`, and a test asserts it can
never be emitted as `VALIDATED`. **A caveat that lives beside a number
rather than inside it is one refactor from being lost.**

## SOURCES: a provenance registry, and two traps in building one

`docs/sources.toml` is the hand-edited registry of every paper, dataset,
legal text, standard and bundled library this project rests on;
`tools/build_sources_doc.py` generates `docs/SOURCES.md` from it, with the
same both-directions `--check` as `build_regulatory_rulesets.py`.
`tests/test_sources_are_current.py` is the guard.

**`source_key` IS THE INVARIANT; THE DOI SWEEP IS A BACKSTOP.** There are
71 sources and **35 DOIs**, so a DOI-only guard would cover about half of
them and leave every prose citation -- the CRC Handbook, the CWC schedules,
IUPAC 2013 -- free to rot while the suite stayed green. Prose cites with
`[source:key]`, never a bare backtick: these documents hold thousands of
backticked identifiers, so a guard reading every one as a key would need an
enormous allowlist or would teach the prose to look like the test. The
syntax is validated BEFORE it is resolved, so `[srouce:x]` fails rather than
being skipped into a false clean state -- the `**OPNE**` lesson again.

**A PLAIN TOP-LEVEL KEY IN A DATA FILE BREAKS ITS LOADER.** `_source_key`
is underscore-prefixed and that is load-bearing, not style.
`oxidation_states.electronegativity_table` and `checkers.valence.hypervalent_rules`
both read their file's TOP LEVEL as the data map and drop keys beginning
with an underscore -- the latter says so in its own docstring. A plain
`source_key` is therefore indistinguishable from an element symbol, and
adding one failed **43 tests** with `TypeError: string indices must be
integers`. Files that nest their data under a named key (`elements`,
`radii`, `solutes`) tolerate either spelling, which is exactly what makes
the mistake survivable in five files and fatal in two.

**HASHING RAW BYTES FOR A GENERATED-FILE CHECK FAILS ON CI.** The first
`--check` hashed `sources.toml`'s bytes. This repo has `core.autocrlf=true`
and no `.gitattributes`, so the same commit is CRLF in a Windows working
tree and LF on a Linux runner, and the check would have gone red for a
reason with nothing to do with content. It hashes newline-NORMALISED text
now, which still catches every content edit including a reworded comment
and ignores only a platform artifact nobody reviewed. Verified by converting
both files to LF and back.

**THE LICENCE GUARD WALKS THE FILESYSTEM, AND IT IS FILE-LEVEL.** Driving
discovery from the registry alone means a bundle nobody registered is
invisible -- how `inapplicable_calculators` rotted into 27 wrong entries --
so the walk finds the files and the registry explains them, in three
directions. File-level because directory-level is already wrong here:
`resources/viewer3d/` holds `3Dmol-min.js` (theirs) beside `viewer.html`
(entirely ours). It found that **Ketcher shipped with no LICENSE file at
all** while Mol*, 3Dmol and the vendored namer each carried one.

**AND IT PROVES DECLARATION, NOT COMPATIBILITY.** `resources/ketcher/dist/`
is a BUNDLE: EPAM's Miew 0.11.1 is in there (its banner survives) and so is
three.js, against a build tree of 429 packages. Registering Ketcher's own
Apache-2.0 was necessary and never sufficient.

**THE NOTICES CANNOT COME FROM THE ARTIFACT, SO THEY COME FROM THE
LOCKFILE.** The build strips comments even with minification off, so exactly
**two** licence banners survive in 35 MB.
`tools/build_ketcher_notices.py` generates
`resources/ketcher/THIRD-PARTY-NOTICES.txt` from `package-lock.json` plus
the licence files in `node_modules/`, and it is committed beside the dist
for the same reason the dist is: CI has no node, and a fresh clone must
carry what it redistributes. 318 packages, 437 KB, 312 of them with the
package's own licence TEXT rather than just an identifier.

**318 OF 429 IS DELIBERATELY MORE THAN THE BUNDLE CONTAINS**, being every
package the lockfile does not mark `dev`. A build-time tool can be a runtime
DEPENDENCY of a runtime package -- the whole `@babel/*` set arrives that way
via `@emotion/babel-plugin` -- and vite tree-shakes, so some listed packages
contribute no code at all. Narrowing it would mean deciding, per package,
whether any of its code survived into a comment-stripped 35 MB artifact.
**Over-attribution is the safe direction and under-attribution is not**, and
the generated file says so rather than implying a precision the method does
not have.

**MIEW APPEARS AT 0.11.1, MATCHING THE BANNER IN THE DIST EXACTLY**, which
is the check that a lockfile-derived list really describes the artifact --
along with three.js 0.153.0 and raphael 2.3.0, the latter explaining the
otherwise-mysterious `eve-raphael`.

Three guards hold it, and deleting the file trips all three: the licence
guard, the operational-path check, and
`test_the_ketcher_third_party_notices_are_current`, which runs the
generator's `--check`. That compares the RECORDED lockfile hash against the
lockfile as it stands, so a dependency bump without a regeneration fails.
**Its regenerate-and-compare half needs `node_modules/` and CI has none**,
so the tool skips that half and says so on stdout rather than passing
silently -- a check that degrades quietly is worse than one that admits what
it could not do.

The licence guard still proves DECLARATION rather than compatibility.

**VERSIONS ARE CHECKED WHERE THEY ARE RECOVERABLE, AND THE OBVIOUS PROBE
LIES.** Ketcher's version is read from `package-lock.json` -- not
`package.json`, which happens to pin exactly (`"3.17.0"`, no caret) but is a
request rather than a result; the lockfile resolves with an integrity hash.
`ketcher-core` is **3.17.1** while `ketcher-react` and `ketcher-standalone`
are 3.17.0, which is why `package_name` is declared explicitly and never
inferred from a registry key. Mol* and 3Dmol get no version check on
purpose: grepping `molstar.js` for a version yields `18.3.1`, which is
**React's** version inside the bundle. `pyproject.toml`'s `>=` lines are
constraints, and `uv.lock` is the reference environment's resolution rather
than a user's, so both are recorded as constraints.

**AND IT PROVES NEITHER COMPLETENESS NOR CORRECTNESS.** The guards check
consistency after the registry was populated; that every source was found
rests on the reconstruction sweep. They cannot tell you a citation points at
the right paper, a table number is right, or a source still supports the
claim resting on it. `citation` means the reference is right,
`citation_and_claim` means the NUMBER this project uses was checked against
the source, and the two are separate because this project has shipped a
fixture labelled "verbatim from a real run" whose energies were typed from
memory. After the verification pass below: 17 `citation_and_claim`, 21
`citation`, 16 `unverified`, and every one of the 16 genuinely has no local
copy and no local metadata to check against.

**THOSE THREE NUMBERS DESCRIBE THAT PASS AND NOT THE REGISTRY TODAY**, which
is worth saying because they read as current. Measured on master after the
four calculator families landed: **94 entries, 38 `citation_and_claim`, 56
`citation`, and ZERO `unverified`.** The 16 are gone -- not by lowering the
bar, but because every entry added since has arrived with its source read.
Kept with the correction beside it rather than edited away, because "where
did that number come from" is the question a reader will have.

### THE VERIFICATION PASS FOUND TWO WRONG ENTRIES, AND ONE WAS MARKED VERIFIED

Read the PDFs with `pymupdf` in a THROWAWAY venv (`uv venv` in a scratch
directory, `uv pip install pymupdf`) rather than the project venv, so the
suite environment stays exactly what `uv sync` produces. `pdftoppm` is not
installed, so the `Read` tool cannot open a PDF here. Force
`PYTHONIOENCODING=utf-8` or the first paper with an "∼" in its title raises
`UnicodeEncodeError` on the cp1252 console -- the same trap already recorded
for result lines.

**`avdeef2020` CARRIED A DIFFERENT PAPER'S TITLE while claiming
`citation_and_claim`.** The real title is "Prediction of aqueous intrinsic
solubility of druglike molecules using Random Forest regression trained with
Wiki-pS0 database"; the one recorded was "Multi-lab intrinsic solubility
measurement reproducibility in CheqSol and shake-flask methods", which is
Avdeef, ADMET & DMPK **2019, 7, 210-219** -- reference (5) of Llinàs 2020.
**The volume, pages and DOI were right the whole time, because those came
from the repository; only the title came from memory.** That asymmetry is
the tell: the fields nobody could check were the ones that were wrong.

**`gutmann_frontiers2022` CLAIMED A LOCAL PDF AND AN AUTHOR, BOTH
INVENTED.** `kaya2022.pdf` matched the DOI's year and was assumed to be it;
it is "On the Prediction of Lattice Energy with the Fukui Potential",
J. Phys. Chem. A 2022, 126, 4507-4516. Searching every PDF in the archive
for the Frontiers DOI or for Gutmann donor numbers returns nothing -- that
paper is not held locally at all.

**SO AUDIT THE ENTRIES THAT ALREADY CLAIM TO BE VERIFIED, not only the
unverified ones.** The pass was started to upgrade 24 `unverified` rows and
found its two real defects among the rows that already said `citation` or
`citation_and_claim`. Ten other entries checked out exactly -- `mayo1990`,
`shannon1976`, `parr_pearson1983`, `pearson1988`, `avdeef2007`,
`jenkins1999`, `platts1999`, `bolovinos1984`, `lorentzon1995`,
`moreland1974` -- each matching the paper's own running header.

**A PDF's FIRST PAGE IS NOT NECESSARILY ITS PAPER.** `Drago & Wayland EC
1965.pdf` opens on the tail of the PRECEDING article, about Co(II)
relaxation times, so a check that reads page one alone concludes the file is
the wrong paper. Searching the whole text found it, and found the sentence
the Lewis scale guard rests on: **"E A = 1.00 and CA = 1.00. Iodine was
selected because"**.

**A REFERENCE LIST IS A VERIFICATION INSTRUMENT.** Llinàs 2020's references
supplied a confirmed citation for `llinas2008` (its reference 2), named the
paper `avdeef2020` had been confused with (reference 5), and revealed a
source the sweep had missed entirely -- `llinas2019`, "Solubility Challenge
Revisited after Ten Years, with Tight (SD ~0.17 log) and Loose (SD ~0.62
log) Test Sets", which is where the tight/loose vocabulary this project uses
actually comes from. It also caught an over-attribution: Llinàs 2020 states
the interlab SD ~0.17 itself, but its RMSE = 0.34 carries a citation marker
and belongs to Avdeef 2019.

**AND THE ENTRIES WITH NO PDF NEEDED THE SAME AUDIT, FOR THE SAME REASON.**
Asked where the still-unverified citations came from, the answer was "the
repository's own text" -- mostly true, and in four cases not. `aqsoldb`,
`allred1961`, `vogel_drago1996` and `ich_m9` had each been given a TITLE or
a volume/page that the repo never carried and that nothing had checked. All
four now say only what the repository says, with "title not established" in
place of the invention. **A citation assembled from a real source plus a
remembered detail is not a real citation**, and it fails in the direction
that looks most convincing.

`vogel_drago1996` is the one worth knowing about: `lewis_parameters.json`
says the shipped E/C numbers came "via the Wikipedia ECW model compilation",
so the chain is Wikipedia -> this repo -> the registry and **no step of it
has touched the paper.** What stands in for that check today is
`test_the_shipped_table_reproduces_the_measured_enthalpies`, which
reproduces eight measured enthalpies to 0.27 kcal/mol.

### AND READING THE SOURCES FOUND TWO DEFECTS THE TESTS COULD NOT

Both were in SHIPPED data, both had passed every test for as long as they
had existed, and neither is findable without the paper open beside the file.

**THE DRAGO E/C TABLE HAD A TRANSCRIPTION ERROR.** All 53 shipped
parameters were checked against Table 1 of [source:vogel_drago1996]; **52
matched exactly** and methylamine's `C_B` was 3.13 where the paper prints
3.12. Fixed in `tools/build_lewis_parameters.py`. It does not move the
validation MAE (0.272 over eight iodine adducts), which is precisely why
nothing caught it: **a validation that averages cannot see one value that
is 0.01 out.** The scan has no text layer, so this needed a 520-dpi render.

That paper also closed the project's weakest provenance chain -- the E/C
numbers had reached the repo "via the Wikipedia ECW model compilation" with
no step touching the source -- and its **footnote 1 is the argument for
`_parameter_scale` existing**: these parameters "should not be mixed with
those parameters found in the literature prior to 1991".

**AND `electronegativity.json` CARRIED A CLAIM THAT IS FALSE.** It said the
Allred set is "the set reproduced in the CRC Handbook of Chemistry and
Physics". Measured against table 9-103 of the 97th edition: **72 of 85
agree, 13 do not** -- As, Au, Bi, Hg, Lu, Np, Pb, Pt, Pu, Tc, Tl, U, W, some
of them widely (Pb 2.33 against 1.8, W 2.36 against 1.7).

**NO SHIPPED VALUE IS WRONG**, and establishing that is the point: CRC's
table says outright it gives values "for the most common oxidation state",
a different quantity, while Allred's own Table 4 tabulates oxidation states
separately and lists Tl(I) 1.62 -- exactly what this project ships, where
CRC prints 1.8. Fe 1.83 and Tl 1.62 both appear in Allred's tables, so the
attribution is sound. Only the word "reproduced" failed.

**"WHICH EDITION" WAS THE WRONG QUESTION ABOUT THE CRC.** With the book in
hand the answer is that **no number here came from any edition**: the
lattice targets are [source:kaya2022]'s, the CRC column named in
`lattice_energy.py` is [source:jenkins1999]'s own ref 40 taken from
Jenkins' table, and the electronegativities are Allred's. It is
`reference_only`.

**`kaya2022` WAS CITED TWICE AND REGISTERED ZERO TIMES, and the coverage
check could not have found it.** The author-year sweep below greps a fixed
alternation of surnames; "Kaya" was not in it. **That check finds only
authors somebody already thought of** -- the real limit of the non-DOI
half. It was found by chasing the CRC's provenance for an unrelated reason.

#### The coverage sweep, and what it cannot do

The DOI backstop covers the DOI-bearing sources; nothing mechanical covers
a prose citation. This is the manual half, worth re-running after any batch
of source work -- every author-year it prints should resolve to a registry
key, and the alternation wants extending when a new name enters the tree:

```bash
rg -o -N --no-filename -g '!docs/sources.toml' -g '!docs/SOURCES.md' -g '!**/vendor/**' -g '!**/resources/**' -e '(Glasser|Jenkins|Sorkun|Avdeef|Llin[aà]s|Abraham|Acree|Bradley|Delaney|Platts|Pearson|Parr|Drago|Shannon|Allred|Mayo|Hopfinger|Yalkowsky|Banerjee|Kaya|Kuhn|Neese|Vogel|Gasteiger|Marsili|Saller|Wildman|Crippen|Ertl|Schuffenhauer|Rohde|Selzer|Baell|Holloway|Brenk|Bickerton|Bertz|Lovering|Joback|Reid|Stefanis|Panayiotou|Kamlet|Jacobs|Klap[oö]tke|Krygowski|Kruszewski|Bird|Schleyer|Yang|Mortier|Wiener|Randi[cć]|Balaban|Kier|Miller|Cao|Schott|Gutmann)[ ,]{0,2}(?:et al\.?)?[ ,]{0,3}(19|20)\d\d' . | sort -u
```

**IT MISSED FIVE SHIPPED METHODS FOR YEARS, AND THE REASON IS THE ALTERNATION
ITSELF.** Measured 2026-08-25: `gasteiger`, `wildman`, `baell`, `brenk`,
`labute`, `kier`, `wiener`, `randic`, `balaban`, `lipinski`, `veber` and
`huckel` all returned **zero hits** in `docs/sources.toml`, while
Gasteiger-Marsili PEOE, Wildman-Crippen logP/MR, Ertl TPSA and the
PAINS/BRENK catalogues each backed a shipped calculator. None of those
surnames was in the list above, so the sweep could not have found them --
this is its own documented limit, paid for.

**THE `rdkit` ENTRY DOES NOT COVER THEM.** It is `kind = "software"` -- a
licence and a version constraint -- and makes no claim about the METHODS
RDKit implements. Under the registry's own scope (`status = "shipped"` means
this source backs something we ship), a library-implemented method needs its
own entry exactly as a hand-transcribed table does.

**AND A LIBRARY'S IMPLEMENTATION IS NOT ALWAYS THE PAPER'S.** Two of the
RDKit contributions register a divergence in their own headers:
`Contrib/SA_Score/sascorer.py` records a different macrocyclic penalty, an
added symmetry term and **r2 = 0.97** against Ertl's original rather than
1.0; `Contrib/NP_Score/npscorer.py` is a 2015 re-fit on ~50k public natural
products and ~1M ZINC molecules rather than the Novartis corpus behind the
2008 paper. So a source entry for a library-implemented method says the
DEFINITION is that paper's -- never that the number is. Validating a shipped
SA score against [source:ertl2009]'s printed values would be an acceptance
test that fails against correct code.

**THE RULE THAT FOLLOWS**, and it belongs beside `verification`'s three
values: a citation-level entry does not authorize an implementation merely
because its title matches. `citation_and_claim` is granted only after the
exact method variant, its equation and parameter conventions, and an
acceptance fixture have been checked against that source.

**PDFs HELD LOCALLY AND CITED NOWHERE ARE NOT REGISTRY ENTRIES**, because
the registry records what this project rests on and an unused source
inflates it. Recorded here instead so nobody re-derives whether they
matter: `glasser2000`, `glasser2012`, `jenkins2002` (lattice-energy
family); `tantardini2021` (thermochemical electronegativities, adjacent to
`electronegativity.json`); `bodor1992`, `klopman1992`, `sun2019` and the
Yalkowsky & He *Handbook of Aqueous Solubility Data* (candidates for a
wider solubility corpus, **with the leakage question asked of each first**);
`drago1994` and `romeo1997`.

**Their DOIs are deliberately not written down anywhere in the tree**, and
that is not fussiness: the DOI backstop treats any DOI it finds as a
citation that must resolve to a registry entry, and it caught exactly this
list when they were included. Its Table 3 supplies every experimental
lattice energy the Kapustinskii route is scored against: 35 of 36 salts
located, all 35 matching.

Its file had also been dismissed twice -- first mistaken for the Gutmann
paper because the filename matched that DOI's year, then written off as
unrelated once it was not. **"Not that paper" is not "not a source"**, and
both errors were the same move: deciding what a file is without opening it.

**LOCAL PACKAGE METADATA VERIFIES SOFTWARE BETTER THAN ANY PDF.**
`importlib.metadata` gave licences for five dependencies, and corrected one:
PySide6 is "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0", not the plain
"LGPL-3.0" recorded -- flattening a disjunction loses the fact that there is
a choice. `VENDORING.md` corrected the namer's identifier, which pointed at
THIS project's repository rather than the upstream it was vendored from, and
supplied the pinned commit. And 3Dmol's own licence text turned out to
declare a second bundling case: "3Dmol.js incorporates code from GLmol,
Three.js, and jQuery" -- same shape as the Ketcher bundle, except this one
says so in the file we ship.

**`lewis_parameters.json` IS THE CASE THAT NEEDED BOTH FIELDS.** It cites
three works (1965, 1992, 1996) and the shipped numbers come from the 1996
compilation, so `_source_key` is `vogel_drago1996` with the other two
supplementary. `_parameter_scale` is a SEPARATE claim: Drago & Wayland 1965
normalise iodine to `E_A = C_A = 1.000`, where this table has iodine at
`E = 0.5, C = 2.0`, so citing the 1965 paper as the source would imply a
scale these values are not on and a reader combining the tables would get
plausible, wrong enthalpies.
`test_lewis_parameters_match_the_declared_parameter_scale` DERIVES the scale
from the iodine entry rather than trusting the label -- the same move
`test_assembly_gate.py` makes -- and lives with the Lewis tests, because a
guard over every data file in the project must not know chemistry.

### THE DOCS GUARD WAS CHECKING THE MACHINE, NOT THE REPOSITORY

`test_docs_are_current._repo_files` enumerated with `rglob("*")` over the
whole tree. Measured when it was fixed: **38,680 files against git's 1,021**
-- so 97% of what every cited path was matched against was `.venv`,
`node_modules` and `__pycache__`.

That matters because of the BASENAME FALLBACK, which is deliberate and
correct on its own terms ("see `engine.py`" should resolve): a bare filename
passes if anything anywhere carries that name. So `docs/ROADMAP.md` cited a
bare `setup.py` this repository does not contain, and passed on any machine
with numpy installed, because numpy ships one of its own under
numpy/_core/tests/examples/cython/ (written without backticks here, because
the fixed guard correctly rejects a document that cites it).

**THE A/B IS THE PART WORTH KEEPING**, because the symptom was a GREEN test
and nothing about the guard looked wrong. Citing a pandas module present
only in the virtualenv:

    old, rglob incl. .venv     19 passed in 32.18 s   <- silently accepted
    new, git ls-files          1 failed  in  0.26 s   <- caught

120x faster as well, which is what walking 38,000 files instead of 1,000
costs on every one of the 19 parametrised documents.

`test_the_citation_check_only_sees_the_repository` guards the FIX rather
than the symptom, and asserts the two things that distinguish the
enumerations: no `.venv`/`node_modules`/`__pycache__` member is in the list,
and the count is of the right ORDER. **`dist` is deliberately not in that
intruder set** -- `resources/ketcher/dist/` is a committed, shipped bundle,
and the first version of the guard failed on it. An environment directory is
one git does not track; a build OUTPUT can be a legitimate part of a repo.

**AN INCONCLUSIVE PROBE RAISES**, as with the `webgl` fixture: "I could not
ask git" is not "the repository is empty", and a blanket except would turn
every citation check into a silent pass -- the exact failure this file
exists to prevent, installed in its own foundation.

**`local` NAMES A PDF AND IS NEVER CHECKED.** `Sci Downloads` is not in the
repository, so no run can resolve it. That is an admitted gap rather than an
oversight: a check that cannot run is worse than a stated limit.

## A PANEL THAT DREW TWO THIRDS OF AN ANSWER AND SAID NOTHING

Reported as "our periodic table is rather unreliable", with polonium and
bismuth as the screenshots. The sharp one:
`OrbitalBoxes.paintEvent` packed rows against `self.height()` and

    if y + row_height > self.height():
        break

so polonium's panel stopped at `5s`. `5p6 5d10 6s2 6p4` -- **22 of its 84
electrons** -- were not drawn, while the line directly above printed the
full `[Xe] 4f14 5d10 6s2 6p4`. Measured against the shipped geometry: Po
needs 160 px at width 420 and the old panel had about 130, which leaves
exactly the 4 subshells the screenshot is missing.

**THE STRING AND THE PICTURE DISAGREED AND THE PICTURE LOST QUIETLY**,
which is the worst way for a reference table to be wrong -- and the suite
was green throughout, because
`test_the_boxes_draw_more_for_more_subshells` compares two SMALL elements
and both of them fit. The population is the whole test: the defect only
exists once a configuration is taller than its widget, which begins
around period 5.

### The scroll-area contract, which is the THIRD time this flag has bitten

`heightForWidth` + `setWidgetResizable(True)` is two mechanisms fighting:
the scroll area tells the child to fit the viewport while height-for-width
says the natural height follows from the width. `WrappedLabel` starving a
panel and a style change re-arming the flag through `changeEvent` are the
first two. So:

    _layout_rows(width)   the one authority on where anything goes
    _draw_rows(...)       draws ALL of them, no truncation branch
    the widget is told its WIDTH and answers with a minimum HEIGHT
    the QScrollArea grants it and scrolls the excess

**AND THE INVARIANT IS SELF-RESTORING, which took two attempts to
discover.** `resize()` is clamped to the widget's own minimum; dropping
the minimum first does not help either, because delivering the resize
runs `resizeEvent`, which puts it straight back and Qt grows the widget
again -- `grab()` on a widget resized to 120 returned a 256 px image. So
the diagnostic banner is unreachable through the public API, and
exercising it needs a subclass modelling the one thing that could cause
it. A restored truncation branch SURVIVED both earlier attempts.

**`QPainter` METHODS *ARE* MONKEYPATCHABLE UNDER PySide6**, which is
worth knowing because the opposite is the natural assumption and it would
have cost a rewrite. `monkeypatch.setattr(QPainter, "drawText", spy)`
works, and `grab()` paints the WHOLE widget rather than an exposed
viewport rect -- which is what lets a deliberately short widget be the
setup rather than the obstacle.

### The other three, and 34 elements with no nucleus at all

- **`nucleus()` raised for any element with no naturally occurring
  isotope**, so `ShellDiagram` drew nothing at all and the caption fell
  to a bare "Electrons: 84". Measured: 34 of 118 -- Tc, Pm, Po, At and
  everything from Rn up except Th and U. Refusing to invent a neutron
  count was right; refusing to draw the protons was the bug. **The two
  refusals must not merge**: `nucleus("Si", mass_number=99)` still
  raises, `nucleus("Po")` returns a proton-only nucleus.
- **"Typical valences" was RDKit's implicit-H model wearing a chemistry
  label.** `GetValenceList` gives Cl [1], Br [1], I [1, 3, 5] -- so the
  table said bromine has one typical valence and iodine three, when both
  do 1/3/5/7. Relabelled, not removed: the app's own valence checker acts
  on the same list.
- **A 32-electron shell drew as a solid band.** A fixed 5 px dot leaves
  uranium's N shell 0.5 px between electrons. Scaled against the ARC each
  electron has to itself, the shipped worst case is 3.8 px.

## THE CRC OVERTURNED THE REASON IT WAS OPENED

The plan for the oxidation-state review said bromine was missing +3 and
+7, "which makes it inconsistent with chlorine in the same group". Read
off the CRC Handbook 97th ed. page 2639 -- rendered at 10x, because the
poster is rotated 90 degrees and its text layer interleaves neighbouring
cells:

    F   -1
    Cl  +1 +5 +7 -1        <- no +3
    Br  +1 +5 -1           <- no +3, no +7
    I   +1 +5 +7 -1
    At  (none listed)

**Bromine matches the CRC exactly.** The group asymmetry is the source's
own. What differs is CHLORINE, where this project ships a +3 the CRC does
not -- and ClF3 and the chlorites are real, so that is the CRC being
conservative rather than this project being wrong. Nothing was changed;
what was added is the record of how the two relate.

**AN AUTOMATED EXTRACTION WAS ABANDONED, and its acceptance checks are
why that was safe.** Two positional passes over that poster each produced
113 plausible rows with every element carrying its NEIGHBOUR's states, in
two different directions. A count alone would have accepted both. The
melting-point table (4-116..4-118) extracted cleanly by the same method
once the columns were understood -- they are right-aligned, so values sit
LEFT of their headers, and binning against the headers gave 2 rows of
100.

## A BETTER LAYOUT ENGINE THAT IS WORSE ON THE REPORTED MOLECULE

`rdCoordGen` is the obvious replacement for `AllChem.Compute2DCoords`.
Closest non-bonded approach in bond lengths, higher is better:

    methane      1.414 -> 1.000   coordgen worse
    caffeine     1.177 -> 1.000   coordgen worse
    glucose      0.524 -> 0.805   coordgen better
    morphine     0.303 -> 0.186   coordgen worse
    cholesterol  0.036 -> 0.565   coordgen better, sixteenfold

**Morphine is essentially the structure the Lewis bug was reported for**,
and it is one CoordGen loses. Both are deterministic and together cost
about 20 ms on the largest case, so `lewis_builder` lays out with both
and keeps the better -- which cannot regress *according to the measured
metric*, a weaker and more honest claim than "cannot regress".

**WHICH TERM LEADS THE SCORE WAS CHOSEN ON A DESIGN SET AND FROZEN.**
`benchmarks/lewis_layout/choose.py` declares its criteria before running,
splits 42 molecules alphabetically before anything is scored, fixes the
ordering on one half and evaluates it on the other:

    A (-crossings, crowding)   design 19/21 not worse   rejected
    B (crowding, -crossings)   design 21/21             holdout 21/21,
                                                        8 strictly better

**Clearance leads, which is not the intuitive answer** -- crossings-first
makes two of twenty-one design molecules worse on clearance to remove a
crossing.

**AND THE CHOOSER MOVED AN EXISTING FIXTURE.**
`test_crowding_is_a_LEGIBILITY_number_and_not_a_refusal` used glucose as
its crowded case; glucose now measures
0.805 and is on the roomy side of `CROWDED_APPROACH`. Morphine replaces
it, being one CoordGen loses, so it stays crowded whichever engine wins.

## THE MUTATION STEP EARNED ITS KEEP SEVEN TIMES IN ONE BRANCH

Of about forty mutations run across this work, seven found a guard that
was testing nothing, and every one of those was the TEST being wrong
rather than the code:

- **a vacuous fixture.** An unshown `OrbitalBoxes` is 640x480, where
  polonium needs 112 px -- under the 120 px placeholder floor. So
  `minimumHeight() >= required_height()` held on a widget that had
  computed nothing.
- **a fixture the fix healed.** The rendered guard resized to
  `minimumHeight()` before grabbing, so every row fitted and the branch
  under test was never reached.
- **asking the wrong object.** A scroll-area guard checked
  `boxes_scroll.widget() is boxes`, which stays true when the scroll area
  is built and never added to a layout.
- **a bound that was not a bound.** "Electrons never touch" written as
  `2 * radius < arc` is satisfied by a fixed 5 px dot on uranium's N
  shell by 0.5 px -- not overlapping, and a solid band on screen. It is a
  CLEARANCE now.
- **a declared range that clipped a real element.** Helium's covalent
  radius is 0.28 against a floor declared at 0.30. Checking a declared
  range against the shipped data is what keeps "declared" from meaning
  "invented".
- **a redundant branch that double-counted.** `_segments_cross` also
  tested collinear overlap; removing it changed no test and no benchmark
  number, because two overlapping collinear segments must put an endpoint
  of one inside the other, which the atom pass already counts.
- **a claim whose wording had to change.** The abstained-bond test
  asserting it is "the only line in the picture" is false once guides
  exist. Renamed to "...when guides are off", asserting the original
  claim in the configuration where it still holds, rather than weakened
  until green.

## AND TWO DEFECTS ONLY THE MAGNIFIED SHOT FOUND

Both with the whole file green, which is now the eighth and ninth entries
in this file's running count of that:

- **the ring counts collided.** Polonium's rings are 15 px apart, so six
  labels stacked on one bearing ran together and "18 32" read as "1832".
  They fan across the left side now, buying separation from the ANGLE
  where the radius has none.
- **a label whose gap fell inside the nucleus disc was SKIPPED**,
  silently -- the innermost shell of every element, in the one branch of
  this codebase written against silent omissions.

## NUCLIDES: what the isotope and decay work cost

`chem/nuclides.py`, `chem/decay.py`, `chem/decay_svg.py` and
`chem/isotopes.py` are the NUBASE2020 table and what reads it. Most of
it is in the modules' own docstrings; these are the parts that are not
recoverable from the code.

**A HALF-LIFE HAS EIGHT STATES AND A BRANCHING HAS ITS OWN FOUR.** An
early draft of the plan attributed the branching qualifiers to the
half-life column -- "145 `<`, 20 `>` and 340 `~`" -- and they are a
different field. The half-life's own bounds are 9 `>`, 4 `<` and 6 `~`
among 5,843 rows. **AND THE VALUE AND ITS UNCERTAINTY ARE TWO
DIMENSIONS**: 38 rows have no half-life but a bound in `dT`, and 256
carry BOTH a value and a `dT` bound, so one qualifier field would force
a silent precedence rule.

**A DEGENERATE FIXTURE APPEARED IN EVERY SINGLE COMMIT OF THIS BRANCH.**
Nine mutation runs, and the survivors were almost never untested code --
they were tests that could not discriminate:

    N3  the absent-vs-zero pair used masses 101/102, so the mass
        tie-break gave the right order anyway
    N3  CARBON cannot see abundance-before-half-life; uranium can
        (U-234 abundant at 0.0054%/246 ky vs U-236 no abundance/23.4 My)
    N3  tin's ten stable isotopes all have distinct abundances, so the
        final tie-break never fired
    N5  "carbon's fill differs from uranium's" passes when the terminal
        swatch is painted with the ramp's TOP colour -- uranium sits at
        0.638
    N6  "a 13C landed" passes when the scope is hardcoded to every atom;
        ethanol has TWO carbons and counting them is the discriminator
    N6  the checkbox guard picked a row first, so it only ever reached
        the path where the label was already right
    N4  four checks of `edge_weight` did not notice the RENDERER
        ignoring it
    N4  the click test called the handler directly, so a filter that
        swallowed the press survived
    N4  the refit CONTROL switched to tab 0, which was already current,
        so `currentChanged` never fired

The last two are one lesson twice: **a control that does not move is not
a control**, and **testing a helper is not testing the wiring**.

**AND THE PLAN'S OWN REFUSAL FIXTURE WAS DEGENERATE TOO.** It specified
"asking for O-18 on a carbon must be refused". Mass number 18 is a real
nuclide of BOTH elements -- C-18 exists at 92 ms -- so that call is
correctly ACCEPTED. Mass number 2 is the sharp case: deuterium exists,
C-2 does not. Carbon's table runs 8..23.

### THE CHART OF THE NUCLIDES NEEDS NO LAYOUT ALGORITHM

x is the neutron number and y is the proton number. **(Z, N) determines
A, so CELLS cannot collide** -- measured across 200+ chains at zero,
which is a proof rather than a tolerance. Alpha is two cells down and two
left, beta-minus one up and one left, so the SHAPE carries meaning and
U-238 comes out as the staircase books draw.

**THAT PROOF IS ABOUT CELLS, NOT NODES, AND THE ISOMERS SPLIT THE TWO.**
Once a state exists, (Z, N) still determines the CELL and the state index
chooses a slot within it -- so the property to guard is one box per
STATE, not one per cell, and the injectivity guard was rewritten rather
than deleted.

**`STATE_OFFSET` WAS A CHOSEN NUMBER AND IT WAS WRONG.** Written as 11.0
against a 40 px box, two states of one isotope OVERLAPPED -- and
`node_at` returns the first box containing the point, so a click on the
isomer resolved silently to the ground state, which is the exact bug
class carrying the key end to end exists to prevent. It is `BOX_H +
STATE_GAP` now, derived, and the row PITCH grows with the deepest stack
so a stacked cell cannot reach the row below. With no isomer in a chart
-- every chart a ground-state root can draw -- `deepest` is 0, the pitch
is exactly `CELL_H`, and U-238 still renders at 2320x862 with 37 nodes.

**THE TWO GUARDS FOR IT WERE BOTH DEGENERATE FIRST**, and the reasons are
different and both worth keeping:

    the rebuild arm survived because the test called `_focus_decay_node`
    itself instead of driving the event filter -- testing a helper is not
    testing the wiring, which this branch paid for twice
    the row-pitch arm survived because Ru-99 is one column ACROSS on a
    NEUTRON-number axis, so no stack could ever reach it. Mo-98 shares
    Tc-99 N=56 and is the only arrangement that collides.

**THE FIRST RENDER WAS UNREADABLE AND WEIGHTING FIXED IT.** A cluster
emission is an enormous jump on this chart -- uranium's 32Si branch moves
14 protons and 18 neutrons at once -- so at uniform stroke a handful of
decays at ~1e-10% drew lines across the whole width while the real series
was a faint zigzag underneath. Line weight is the branching now, and
nothing is dropped: a guard counts `<line ` against followable edges.

**FOUR "STABLE" NUCLIDES ALSO CARRY A DECAY.** Pb-204, Pb-206, Pb-208 and
Hg-204 are marked `stbl` in NUBASE AND list a mode nobody has ever
observed (`A ?`, `2B- ?`). So `leaves()` correctly reports Hg-200, Hg-202
and Tl-205 for uranium-238 and omits Pb-206, which is where every
textbook says that series ends -- the status line reports which stable
nuclides a chain REACHES instead. Asserted, so a future NUBASE that
resolves the contradiction fails rather than silently redrawing.

**AND U-238 CANNOT DEMONSTRATE AN UNFOLLOWABLE LEAF.** It has seven SF
branches, and every node carrying one also has a followable alpha, so
none of them is a leaf. Measured over the whole table: 8,038 stable
leaves, 109 unfollowable, 17 off-table. Fm-259 fissions outright; Li-3
decays off the table.

### ARMING THE CANVAS: the mass number was never part of the gesture

Reported as "I can place carbon 13 for example, but it is just CH4, there
is no 13", and it is not a rendering bug. Ketcher draws isotopes
correctly -- a molblock carrying `M  ISO  1   1  13` loads as
`{label: 'C', isotope: 13}` and the canvas draws `['C','13','H','3',...]`.
The cause was one line: `set_atom_tool` armed `tool('atom', {label})`, a
BARE element, so the picked isotope was dropped before the click.

`ketcher.editor.tool('atom', {label:'C', isotope:13})` is accepted and
returns an `AtomTool2` carrying `atomProps`. Probed against the vendored
bundle rather than reasoned about, which is how this project reads
Ketcher every time.

**A SYNTHETIC DOM CLICK CANNOT DRIVE THE ATOM TOOL.** Dispatching
`mousedown`/`mouseup`, and then pointer events, left the struct untouched
in both cases -- so a drive step built that way reports "the app ignored
it" for a feature that works. Calling `AtomTool2.mousedown/mouseup`
directly with `{pageX, pageY, target}` is what places an atom.

**AND A DEAD GUARD IS NOT A WEAK TEST.** A mutation on the
element-must-match rule in the placement path survived, and the reason is
that `select()` REPOPULATES the isotope table, dropping the row selection
-- so the mismatch cannot be reached through the UI at all. It is
asserted on the predicate directly, which is this file own
"an unreachable branch is a question about where to assert" rule again.

### AND FOUR MORE THE MAGNIFIED SHOT FOUND, with 5,176 tests green

The whole suite passed, every guard was mutated, the docs were written --
and then the app was driven and cropped 2x, which is the step this file
has now recorded twelve separate findings for. Three were on the screen
and the fourth came out of the probe that failed first.

**A CAPTION CONTRADICTED THE PICTURE DIRECTLY ABOVE IT.** The decay
legend ended "**Ground states only**, so a chain that runs through an
isomer is not drawn" while the chart above it was drawing Ag-108m and its
stacked ground state. Nothing could catch it: the sentence was correct
when it was written and no test relates a caption to what was rendered.
`test_the_caption_never_contradicts_the_picture_above_it` asserts the
CONTRADICTION is absent rather than pinning the replacement wording, so a
future rewrite is free to say it better and not free to say the chart
cannot do what it is doing.

**A BUTTON HINT NAMED A DIFFERENT NUCLIDE FROM THE ONE IT PLACES.** "Adds
Ag-108m to the canvas" -- and `_insert_decay_nuclide` emits a MASS
NUMBER, which is all a molfile can record, so it adds Ag-108. It says so
now, with the same reason `IsotopeRefusal.ISOMER_NOT_IN_MOLFILE` gives.

**`IT` RENDERED AS ITS RAW TOKEN beside "beta+" and "electron capture".**
`_MODE_NAMES` exists precisely because "NUBASE's own tokens are compact
and cryptic", and `IT` arrived as the SECOND commonest mode in the table
at 1,471 rows without being added to it: the Isotopes tab read "beta+
91.3%, IT 8.7%". One line, and only a screenshot asks the question.

**AND THE STATUS BAR CLAIMED "Ready to place: 13C" WHILE NOTHING WAS
ARMED.** `set_atom_tool` DROPS before Ketcher is ready -- deliberately,
and still correctly, because a gesture replayed later primes the canvas
with an element the user has stopped thinking about. But it returned
nothing, so the window said "ready" either way. Measured, ~2 s after
launch:

    armed at 2 s   tool SelectTool2   count 0   nothing placed
    armed at 5 s   tool AtomTool2     count 1   [13CH4]

That is the user's ORIGINAL REPORT arriving through a different door --
click the element, click the canvas, nothing happens. It returns a bool
through all three layers now. **The middle layer is where the answer gets
lost**: a `MoleculeEditorWidget.set_atom_tool` that calls down and
returns None passes the backend test AND the window test while restoring
the defect, so it has its own guard with both arms.

**A FAKE THAT RETURNS `None` WAS SILENTLY MODELLING A FAILURE.** Two
existing tests stubbed `set_atom_tool` with `lambda ...: None`, which the
moment the contract gained an answer meant "did not arm" -- and one of
them failed immediately, which is how the change proved it had teeth.

### THE TOOL STAYS ARMED ACROSS PLACEMENTS, and the probe must not re-arm

Measured in the running app: arm once, then click the canvas three times
without re-arming.

    click 1   count 1   AtomTool2
    click 2   count 2   AtomTool2
    click 3   count 3   AtomTool2
    SMILES    [13CH4].[13CH4].[13CH4]

Preserved deliberately rather than ruled on -- Ketcher's own element
buttons behave this way, so a periodic table that disarmed after one
placement would make two gestures that look identical behave differently.

**THE `place` DRIVE STEP TAKES `arm: false` FOR EXACTLY THIS**, and
without it the question cannot be asked: re-arming before each click
makes every click land whether the tool was retained or not, so a probe
that arms each time answers yes regardless of the truth. Both halves go
through one `_click_canvas`, because if they clicked differently "the
tool stayed armed" would be a claim about two different gestures.

**AND THE FIRST RUN OF THAT PROBE MEASURED A COLD PAGE.** It reported
`count 0, SelectTool2` and read as "placement is broken" -- Ketcher had
simply not finished loading. That reading was wrong about the feature and
right about something else, which is how the status-bar defect above was
found. Give the page a `smiles` step and ~4 s before probing it.

### A `QTabWidget` TAKES THE MAXIMUM OVER ITS PAGES, and one tab set the floor

Reported as "there is no way to adjust the size of the periodic table
popup", with the action row off the bottom of a 1366x768 laptop. **The
buttons were not broken; they were 105 px below the screen.**

This is `A HORIZONTAL ROW MINIMUM IS THE SUM` in the vertical, one
container along. The Decay tab `ZoomableSvgView` carried
`minimum_size=(520, 360)`, copied from the Lewis dialog where that widget
is the whole window -- here it sits under a 502 px element grid, so ONE
tab set the floor for all four:

    page      before      after
    Facts     58 x 58     unchanged
    Atom      499 x 238   unchanged      <- the real floor now
    Isotopes  452 x 108   unchanged
    Decay     520 x 464   320 x 244
    dialog    902 x 1142  902 x 922

**A MINIMUM IS A FLOOR, NOT A PREFERRED SIZE**, and every page here
scrolls or zooms internally, so none loses anything by being allowed to
get small. The dialog OPENS far larger than its minimum.

**AND A `QDialog` HAS NEITHER A MAXIMISE BUTTON NOR A SIZE GRIP BY
DEFAULT**, so a window that opened too tall could not be shrunk, moved
back into view, or maximised. Both are set now -- but they are the SECOND
fix: a minimum larger than the screen cannot be rescued by resizing at
all, because `resize()` is clamped to it.

**A 1366x768 LAPTOP STILL CANNOT SHOW ALL OF IT** at 922 px, recorded as
a stated limit rather than quietly claimed as fixed. The element grid
alone is 880x502.

**THE WIDTH CANNOT BE GUARDED AND THE HEIGHT CAN.** The same dialog is
**1288 px wide under `offscreen`** against **902** in the running
application, because that platform default font is far wider -- so a
width bound is a claim about the font. Height is driven by row counts:
898 offscreen against 922 real.

Three more degenerate fixtures, in the fix for a degenerate-fixture
branch:

    `dialog.width() <= available.width()` on a dialog the fixture NEVER
    SHOWS reads Qt pre-show default and cannot fail. Replaced by a pure
    `fit_within` and a table -- and `offscreen` reports an 800x800
    screen, where the cap always bites, so **deleting the CALL is the one
    mutation nothing catches** and is written into the test rather than
    papered over. Same shape as `initial_right_dock_width`.
    "inserting reveals the editor" held with the reveal deleted, because
    the editor tab was ALREADY CURRENT. The fixture looks away first.
    lowering `ShellDiagram` changed nothing, because
    `AtomDiagram.setMinimumHeight(240)` sat above it and was the real
    binder. Measure the CONTAINER, not the widget you suspect.

### KETCHER HAS NO CONTEXT-MENU HOOK, so ours intercepts the gesture

`ketcher-react` `Config` declares `buttons`, `customButtons` and
`togglerComponent` and nothing else, so injecting into its atom menu is
unsupported in 3.17. `main.jsx` installs a CAPTURE-phase `contextmenu`
listener: on an ATOM it suppresses react-contexify and forwards to
Python; off an atom it does nothing and Ketcher own menu opens exactly
as before.

**`findItem` RETURNED `atoms#0` EVERYWHERE at first, and the coordinates
were why.** `page2obj` maps a synthetic PLAIN-OBJECT event to (0, 0), and
atom 0 sits there -- so every probe "worked" and every answer was the
same atom. Only a real `MouseEvent` carries what `page2obj` reads.

**AND THE ACTUAL BUG WAS A SILENT `ReferenceError`.**
`installAtomContextMenu(editor)` was called in a function with no such
parameter, which aborted the rest of that function -- so the listener was
never installed and nothing anywhere said so. `window.openchemContextMenuInstalled`
is set by the installer and a guard asserts the CALL SITE, because a
bundle string check proves the name reached the file and not that it ran.

**A STEP THAT OPENS A MENU MUST NOT CALL `QMenu.exec`, AND
MONKEYPATCHING IT DOES NOT HELP.** The first version of these tests ran
for **42 minutes** on an invisible modal menu; `monkeypatch.setattr(QMenu,
"exec", ...)` did not stop it, because it is a C++ slot. The fix is
structural: `build_atom_context_menu` returns the menu UNSHOWN and
`_show_atom_context_menu` is the thin caller that pops it. 48 tests in 6
seconds. Same family as the "a modal dialog step must not call `exec()`"
rule this file already carries for `OPENCHEM_DRIVE`.

### NUBASE NAMES NO DAUGHTER STATE, AND THE ASSUMPTION WAS ALREADY BEING MADE

Read off the raw rows, the whole of what the decay field carries is the
mode and the branching -- `B-=100`, `IT~100;B-=0.0037`. So which state of
Ru-99 a Tc-99m beta decay populates is not in the source, and neither is
where an `IT` cascade from index 2 lands.

**THE HONEST FRAMING IS THAT ISOMERS DID NOT CREATE THE ASSUMPTION, THEY
MADE IT VISIBLE.** The uranium chain resolved U-238 to Th-234 ground
state because ground states were all the table held. So
`DaughterProvenance` is a VALUE that reaches the screen: an assumed edge
is DASHED and the legend says what the dash means. A diagram that looked
like an exact NUBASE-derived chain while part of it is this
application own guess is precisely the plausible-looking wrongness this
project spends its time removing.

    EXACT                  an IT from state index 1 -- only the ground
                           state is below it, so nothing is chosen
    ASSUMED_GROUND_STATE   NUBASE names no state populated
    UNFOLLOWABLE           no single daughter exists to have a state

**EXACT IS NOT A DEAD BRANCH, and reaching it needed the threshold
moved rather than an input hunted.** No shipped nuclide could reach it
until the data landed, so both arms are tested by BUILDING a state-1
`Nuclide` directly. `daughter()` returns the provenance WITH the result
rather than taking a policy argument: a `DaughterStatePolicy` would have
had exactly one caller and one value, and a consumer wanting exact-only
can filter on what it is already handed.

**AN `IT` IS `(0, 0)` IN (Z, A) SPACE, WHICH IS A SELF-LOOP.** The state
index is what makes the walk a strict descent and terminate, so
`delta_for("IT")` must never be followed on its own -- callers go through
`daughter()`. An `IT` on a ground state is a contradiction in the data
rather than a branch, and is reported unfollowable rather than resolved
to itself.

### THE ISOMERS: 3,557 nuclides became 5,684, and the build refused twice

`NuclideKey(z, a, state_index)` is a TYPE rather than a bare tuple
because it is the identity contract -- the SVG node carries one, a click
resolves one, the write path refuses one, and three places reassembling
`(z, a, i)` by hand is where a click starts landing on the wrong thing.
**`state_index`, NOT "level"**: NUBASE own field is an isomer INDEX, and
calling it a level invites a later reader to treat `2` as an excitation
energy.

**THE FAIL-CLOSED RULE EARNED ITS KEEP TWICE, and the second was not
anticipated.** The zero-unrecognised-modes invariant REFUSED to build:

    IT   1,471 rows, and `is_recognised("IT")` was False
    B        1 row -- Pd-126p writes `B=72 8`, a beta with NO SIGN

The sign is exactly what decides whether Z goes up or down. Pd-126 own
ground state is `B-=100` and an isomer sits HIGHER in energy, so
beta-minus is a near-certain inference -- **which is precisely why it is
refused.** NUBASE format header documents no mode vocabulary to appeal
to, and this project does not derive physics the source declined to
state.

`UNDERSPECIFIED_MODE` is a FOURTH leaf reason and deliberately not a
physical one: the three others describe the nucleus, this one describes
the DATA. Folding it into `unfollowable` would tell a reader no daughter
exists when one does. **It never becomes a whole node leaf reason** --
Pd-126p also carries `IT=28`, which is followable -- and that is written
into the test rather than left as a silent gap.

**THE LARGEST TREE DID NOT MOVE, AND THAT IS THE RESULT.** Au-169 is
still 161 nodes: an isomer `IT` leads to its own ground state and the
ordinary chain continues, so an isomer adds a ROOT rather than a branch.
Which is why "trees containing an isomer" is exactly 2127, one per
isomer -- a non-IT decay resolves to a ground state, so no ground-state
tree ever reaches an isomer. The corpus pin is a PROFILE now, because
"the largest tree is 161" stopped being the relevant statistic:

    max nodes 161 (Au-169)   median 7 (was 8)   over-60 86 (was 54)
    max edges 223            isomer trees 2127  IT trees 1787

**THE SUFFIX IS THE SOURCE OWN AND THE MAP IS EXACT.** Read from the
name field rather than derived from the index, because a table mapping 1
to `m` would be a second implementation of somebody else notation.
Measured across all 2,127 and one-to-one both ways: 1 m, 2 n, 3 p, 4 q,
5 r, 6 x, 8 i, 9 j. Carbon tab goes 16 rows to 20 -- the four are its
isobaric analogue states, SHOWN rather than filtered, because deciding a
reader may not see a state NUBASE lists would be this application
editing its source.

**253 AND 254 ARE BOTH CORRECT.** Ta-180m is an isomer marked `stbl`, so
a bare count gives 254 and reads as an off-by-one against every
reference. The test names its population and asserts the extra one by
name rather than tolerating it with a loosened bound.

### THE WRITE PATH REFUSES AN ISOMER, AND THE REFUSAL IS THE FEATURE

`M  ISO` carries a mass number and nothing else, so Tc-99m and Tc-99
write the same bytes and every reader downstream -- RDKit, the
calculators, a saved project -- would treat the metastable structure as
the ground state. The alternative to refusing is silently discarding the
one thing the user asked for.

`IsotopeRefusal.ISOMER_NOT_IN_MOLFILE` is a VALUE with generated text, so
`if "isomer" in message` never becomes application logic.
`refuse_isomer()` builds it in ONE place because **both** the Apply path
and the PLACEMENT path need it -- a placed atom becomes a molfile too,
and that second one is easy to miss.

### THE PALETTE NEEDED NO CODE CHANGE, which is worth recording

Alex semantics: an isotope representative half-life is its
longest-lived RADIOACTIVE state, so Ag-108 legitimately wins at 439 y via
Ag-108m. **A maximum over every state already equals the maximum over
isotopes of each isotope own maximum**, so what the plan called a
per-isotope grouping falls out of the existing `max`. Nobody should add
machinery for it later. Four elements moved:

    WINNER MOVES   Ag  105 -> 108   41.3 d -> 439 y   (Ag-108m)
                   Hs  269 -> 277   16 s   -> 2.17 m  (Hs-277m)
    VALUE MOVES    Ir  A=192 both   74 d   -> 241 y   (Ir-192n)
                   Lv  A=293 both   70 ms  -> 80 ms   (Lv-293m)

The swatch NAMES the state, so nobody is told Hs-277 lasts 2.17 minutes.
**AND SILVER CANNOT DEMONSTRATE THAT**, which is why the guard does not
use it: Ag has a stable isotope, so its swatch is terminal ("has a stable
isotope") and the Ag-108m value never reaches the screen at all.

**`has_stable_isotope` IS NOT A DECISION, WHICH MEASURING SETTLED.**
"Any state" and "the ground state" are indistinguishable on this data --
exactly one isomer in NUBASE is marked stable, Ta-180m, and tantalum
already has a stable ground state in Ta-181. The simpler form stands,
with a change detector that fails the day a revision separates them.

**THE SORT STATE TIE-BREAK IS THE LAST TERM, NOT A GLOBAL RULE.** Tc-99
and Tc-99m tie on every earlier key, so without it the order comes down
to nothing. But "ground states first" would be WRONG: Ta-180m carries a
natural abundance and is marked stable while Ta-180 is neither, so it
legitimately sorts ABOVE its own ground state and never reaches the
tie-break. Both are fixtures, for exactly that contrast.

### A SOURCE CHECK MATCHED THE PROSE EXPLAINING ITS OWN RULE, AGAIN

The generator count reconciliation cannot fail on any INPUT -- every
parsed row increments exactly one bucket -- so it is a self-check on the
next EDIT, and the guard for it reads the source. The first version
asserted `"the arithmetic does not close" in text`, which also appears in
the MODULE DOCSTRING, so deleting the raise left it passing. It anchors
on fragments unique to the message now. Third instance of this shape in
this file.

### A TAB'S COMFORTABLE FLOOR BECAME THE WHOLE DIALOG'S, and the buttons left the screen

Reported as "I cannot select an element and place it on the actual
editor ... this is a new problem on this branch", with "there is no way
to adjust the size of the periodic table popup" beside it. **The buttons
were not broken. They were 105 px below the bottom of the screen.**

    available screen          1920 x 1032
    dialog minimumSizeHint     902 x 1142
    "Insert into drawing"     global y=1136   OFF SCREEN
    maximise button           False
    size grip                 False

This is `A HORIZONTAL ROW'S MINIMUM IS THE SUM` in the vertical, one
container along: **`QTabWidget` takes the MAXIMUM over its pages.** The
Decay tab's `ZoomableSvgView` carried `minimum_size=(520, 360)`, copied
from the Lewis dialog where that widget is the whole window -- here it
sits under a 502 px element grid, so one tab's comfort set the floor for
all four and the dialog could not be made short enough to show its own
action row.

    page      before      after
    Facts     58 x 58     unchanged
    Atom      499 x 238   unchanged      <- the real floor now
    Isotopes  452 x 108   unchanged
    Decay     520 x 464   320 x 244
    dialog    902 x 1142  902 x 922

**A MINIMUM IS A FLOOR, NOT A PREFERRED SIZE**, and every page here
already scrolls or zooms internally, so none of them loses anything by
being allowed to get small. The dialog OPENS far larger than its minimum.

**AND A `QDialog` HAS NEITHER A MAXIMISE BUTTON NOR A SIZE GRIP BY
DEFAULT**, so a window that opened too tall could not be shrunk, moved
back into view, or maximised. Both are set now, and both are guarded --
but they are the second fix, not the first: a minimum larger than the
screen cannot be rescued by resizing at all, because `resize()` is
clamped to it.

**A 1366x768 LAPTOP STILL CANNOT SHOW ALL OF IT** at 922 px, and that is
recorded as a stated limit rather than quietly claimed as fixed. The
element grid alone is 880x502; getting under ~728 means shrinking or
scrolling the periodic table itself, which is the primary content. It is
also pre-existing -- the dialog was ~880 before the Decay tab existed.

**THE WIDTH CANNOT BE GUARDED AND THE HEIGHT CAN.** Measured, the same
dialog is **1288 px wide under `offscreen`** against **902** in the
running application, because that platform's default font is far wider --
so a width bound is a claim about the font. Height is driven by row
counts: 898 offscreen against 922 real. The guard asserts height only and
says why.

**THREE MORE DEGENERATE FIXTURES, IN THE FIX FOR A DEGENERATE-FIXTURE
BRANCH.** Seven mutations, four caught first time:

- `dialog.width() <= available.width()` on a dialog **the fixture never
  shows**, so it read Qt's pre-show default and could not fail. Replaced
  by a pure `fit_within` and a table, because `offscreen` reports an
  800x800 screen where this dialog's minimum is larger still -- so
  calling the cap and deleting it are indistinguishable by outcome, and
  **deleting the CALL is the one mutation nothing catches**. Written into
  the guard, as `initial_right_dock_width` already does.
- "inserting reveals the editor" held with the reveal deleted, because
  **the editor tab was already current**. The fixture looks away first.
- and the suite's one real failure was `"isotope" -> "Periodic Table..."`
  in the palette vocabulary. That is the ranking WORKING: there is now a
  literal `Isotopes...` menu item, which is both a prefix match and the
  better answer. Same case as the `# NOT "valence"` note already beside
  it.

**THE PATH THAT WAS REPORTED BROKEN HAD NO END-TO-END GUARD AT ALL.** The
dialog's tests stopped at `insert_requested`; the window's wiring of that
signal to `set_atom_tool` was never asserted. That is the half that was
missing, rather than the half that failed.

### KETCHER'S CONTEXT MENU: MEASURED, AND NOT SHIPPED

The plan proposed appending items to `context-menu-for-atoms`. The spike
came back negative and the feature did not depend on it, by design.

    react-contexify is the library    no global hooks: a scan of
                                      `window` returns an empty list
    the `.contexify` root             exists only while open, and React
                                      re-renders it every time
    `main.jsx` composes `<Editor>`    the menu is inside Ketcher's own
                                      component tree; no prop, no slot

**THE DECIDING MEASUREMENT IS THAT IT CANNOT BE TESTED.** Ketcher's
canvas is **0x0 in a bare `QWebEngineView`**, even inside a laid-out host
widget and selected by its own `ketcher-canvas` testid -- `page2obj`
divides by that zero and returns non-finite coordinates, so a right-click
cannot be synthesised at an atom outside the running application. An
injection whose only verification is driving the app and watching for a
DOM node React can re-render away does not belong in a vendored bundle
that `test_ketcher_bundle_is_current.py` can only fingerprint by name.

Two facts worth keeping from the probe: **`page2obj` is on
`editor.render`, not on `editor`** (this file said only that it exists),
and `editor.event` carries `click`, `mousedown` and `mouseup` -- so
forwarding a right-click to Python and raising a Qt menu is reachable.
Not done, because Ketcher's own menu opens on the same gesture and two
menus on one right-click is worse than either.

### The zoom view is now shared, and the extraction was free

`ui/widgets/zoomable_svg_view.py` is the Lewis dialog's scroll-and-zoom
contract lifted out for the decay chart. The dialog keeps its whole
surface (`zoom`, `set_zoom`, `zoom_to_fit`, `natural_size`, `_view`,
`_scroll`) as delegations and ALIASES onto the same objects, so the
extraction is behaviour-neutral by construction rather than by
re-testing -- 43 Lewis tests unmoved.

**A ZOOM COMPUTED AGAINST AN UNSHOWN VIEWPORT IS NOT A FIT.** The decay
chart refreshes from `select`, which runs while another tab is current,
so `zoom_to_fit` measured a viewport Qt had not laid out and clamped to
its 25% floor: a 2320 px chart drawn a quarter size in a 1265 px pane. It
re-fits when its tab is shown.

### Four more defects that only the rendered widget showed

Every one with the whole suite green, which is the fifth, sixth, seventh
and eighth entries in this file's running count of that:

- **the half-life legend explained no marks.** Five cells print a
  trailing `#` because a colour cannot say "estimated", and its meaning
  lived only in a tooltip -- while the legend is the part a screenshot
  carries. The guard derives the marks from what the cells actually
  print.
- **"has a stable isotope, not established shown separately"** attaches
  the exception to the second class alone.
- **RED AND GREEN carrying a whole mode by themselves.** Every other
  discrete palette spreads its classes over four or ten hues, where
  confusing two costs one element; here it costs the picture. The cells
  print "stable" and "decays" -- not "unstable", which at 9 px differs
  from "stable" by two leading letters.
- **`**Ground states only**` rendered with its asterisks.** QLabel does
  not do markdown.

## FIVE THINGS TO KEEP DISTINCT IN A SCIENTIFIC CALCULATION

Written after a backlog sweep closed five deferrals in one branch, in
which every confusion was one of these being mistaken for another:

    definition      what quantity is computed
    applicability   when that quantity is meaningful AT ALL
    implementation  how OpenChem computes it
    provenance      which source supports the claim
    oracle          which published values establish it CORRECT

**A SOURCE USED FOR THE DEFINITION IS NOT AUTOMATICALLY AN ORACLE**, and a
validation set from a neighbouring method is not one merely because it
shares an informal name. Three near-misses in one branch, each caught by
reading the source rather than by review:

- **Guo 2006 was twice written down as the Griffin HLB oracle.** It
  tabulates 224 nonionic surfactants, which is exactly what "nothing to
  check a result against" was asking for. It mentions **Griffin zero
  times**: it is a Davies/ECL paper, and its reference column is
  manufacturer data -- its own footnotes read "reported by BASF Corp."
  and "by ICI Americas Inc.". Scoring Griffin against it would have
  compared two scales and produced a disagreement that reads as a bug.
- **TSEI's correlations read as an oracle and are a behavioural check.**
  r = 0.9912 is a fine thing to assert and a weak transcription test:
  systematically wrong implementations still correlate. Table 1's exact
  values are the transcription oracle.
- **Gutmann DN was briefly to be validated against the Drago E/C table.**
  DN is defined as -dH against SbCl5 and E/C predicts -dH, so they are
  related -- but they are distinct parameterisations, and cross-scale
  agreement as a CORRECTNESS criterion lets a real transcription error
  hide behind a legitimate difference.

### A DEFERRAL'S REASONS ROT INDEPENDENTLY OF ITS VERDICT

Fifth instance in this project. `docs/VALIDATION.md`'s "Measured, and
deliberately not shipped" section held five entries whose verdicts looked
settled and whose REASONS had quietly expired:

    acetic acid     "only predicted coefficients exist"    measured in 2015
    Miller          "the parameters are unpublished"        a claim about
                                                            ChemAxon's docs,
                                                            not the literature
    HLB             "no formulas published"                 both are printed
    TSEI            "no reference value was found"          Table 1 prints 20
    Gutmann DN/AN   "the accessible source is ionic
                     liquids"                               true of THAT paper

Not one of those was a lowered standard. The literature moved, or was
never checked. **Re-read the REASON, not the verdict**, and ask what would
have to be true today.

### TRANSCRIBING A TABLE FROM A SCIENTIFIC PDF

**The text layer is not the table.** Every scanned source in this sweep
gave usable-looking output that was wrong:

    Gutmann 1976   "Dimethylsulphoxitie", "l.o.0" for 10.0, ";:Z" where a
                   number belongs, and names and numbers extracted as two
                   SEPARATE runs needing positional alignment
    Miller 1990    "0.392 0.31 1 0.3 13 0.387" for a row of four numbers,
                   "3 .000" for 3.000, "TA" for tau_A
    Guo 2006       clean -- so the rule is to CHECK, not to assume either way

Render at 300-400 dpi and read it. It is not caution for its own sake: the
render caught t-butylamine's donicity at **57.5** where the text layer
said 57.6, which is the Drago audit's one-in-53-out-by-0.01 again.

**AND IT HAPPENED AGAIN, at one in 33.** Marsili & Gasteiger 1980's Table
I -- the pi-orbital electronegativity parameters, which now ship -- has an
OCR text layer reading `b = 11.13` for O-sp2 where the page prints
**11.73**. Three instances now, in three unrelated scans, each a single
digit and each invisible to any validation that averages. Any table
transcribed from a scan gets rendered and read, without exception.

**KEEP THE SOURCE ROW IDENTITY IN THE GENERATED DATA.** `"carbon_sp2": {...}`
loses the trail; carrying the paper's own `symbol` and `hybrid` columns
beside it means a future audit runs against the page line by line rather
than re-deriving which row was meant.

**AND THE ACCEPTANCE TEST IS THE CASE THAT FAILED BEFORE.** Miller's
recorded failures were benzene (+27%) and CCl4 (-50%), so those two are
the gate rather than a sample -- and both mutations reproducing them are
caught. A perturbed coefficient must fail something: a table no test can
falsify is a table nobody checked.

### ONE NAME, TWO QUANTITIES -- NOW FOUND FOUR TIMES

    "HLB"           Griffin or Davies, differing "substantially... in the
                    entire range of practical applications"
    "steric index"  Taft's Es, Hancock's Esc, Charton's nu, Cao-Liu TSEI
    "donicity"      dilute or BULK -- water is 18.0 and 33.0
    "SZ"            Mordred's is "sum of constitutional descriptor", not
                    the Szeged index

The move each time is the same: **ship under the specific name** -- Griffin
HLB, Cao-Liu TSEI -- never the ambiguous one, and keep the two columns
apart in the data rather than picking one. Water is the row that proves
it is not pedantry: merging the donicity columns would be wrong there by
more than the whole range from benzene to acetonitrile.

### APPLICABILITY IS A RESULT, NOT A FOOTNOTE

Griffin HLB on aspirin is 4.14 and means nothing. Returning it and relying
on documentation to say so is the failure the `AlertResult` migration
spent a phase removing.

**AND THE RULE COMES FROM THE SOURCE.** Griffin's definition opens "for
nonionic surfactants with polyoxyethylene as the sole hydrophilic
moiety" -- a structural condition, answered per molecule, in the
refusal-with-a-named-reason shape `BcsReason` and `IsotopeRefusal`
already use. Sorbitan esters are the case most likely to be got wrong:
Griffin's EXPERIMENTS produced Span and Tween's published values, but
sorbitan is a polyhydric alcohol, so his FORMULA does not apply to them.

### CHECKING AGAINST THE SOURCE FINDS BUGS READING THE CODE DOES NOT

Both of these read fine and were wrong, and both were found by comparing
against a printed closed form rather than by review:

- the polyoxyethylene SMARTS matched a chain from BOTH ends, so a C12E4
  counted as 9 units; and it matched the chain's own terminal hydroxyl,
  so **dodecanol** -- the lipophile Brij is built FROM -- was accepted as
  a surfactant and given an HLB;
- benzene assigned to Miller's `CBR` row gives 13.99 against 10.39, and
  the row's symbol is the reason anybody would.


## SHIPPED IS NOT REACHABLE, AND THE GUARD FOR IT HAD THREE BLIND SPOTS

PR #42 added `tests/test_calculator_reachability.py` after four correct,
guarded, sourced modules turned out to be reachable from nothing a user
could press. It did not stop that recurring, and both reasons are worth
knowing.

**IT CHECKED FOUR MODULES.** Only the ones declaring
`USER_FACING_PROVIDER` were checked, so a FIFTH unreachable module was
invisible unless somebody remembered to declare it -- the "somebody
remembers" failure the file exists to remove, one level up from where it
was being fought.

**AND ITS WALK UNDER-REPORTED REACHABILITY THREE WAYS**, each measured:

    from openchem.chem import nmr_hybrid    the edge landed on the PACKAGE
                                            and never the submodule, so
                                            element_palettes and nmr_hybrid
                                            both read unreachable
    importing a.b.c imports a.b             chem/regulatory/__init__.py is
                                            imported by name by NOTHING --
                                            every consumer wants
                                            regulatory.engine
    the ROOT package keyed wrong            `removesuffix` binds to the
                                            `join`, not the concatenation,
                                            so src/openchem/__init__.py
                                            became `openchem.__init__`

The third is the one to remember: every SUBpackage came out right
(`chem.regulatory.__init__` -> `chem.regulatory`) and only the root did
not, which is exactly the one nothing would notice.

**THE INVARIANT IS STATIC IMPORT REACHABILITY, NOT "THE APPLICATION RUNS
THIS".** The walk is an AST pass over `import` statements; a module can be
genuinely used without appearing in one. That distinction is concrete here
rather than pedantic, because this project has three such modules -- so
every name and message says *statically*, and nothing should ever be read
as proof the application EXECUTES anything.

    first-party modules                        277
    statically reachable from openchem.main    274
    script_path (a separate interpreter)         2   admet_runner, pka_runner
    tooling (the suite and tools/, not the app)  1   tooltip_inventory

**ONE ROOT, AND THE ROOT SET WAS A LOOPHOLE UNTIL REVIEW.** The plan
rooted on `openchem.main` PLUS every registry compute. A compute module
forced in as a root is *declared* reachable rather than *shown* to be, so
a broken registration would still pass a guard whose entire subject is
reachability. Measured, the extra roots also bought **nothing** -- `main`
alone gives the identical answer -- so they are gone, and
`test_the_registry_is_statically_reachable_from_the_entry_point` asserts
the property they were quietly assuming.

### `REACHED_BY`: a closed kind, a free reason, and both directions

The exception is declared BY THE MODULE, in production source, discovered
the way `USER_FACING_PROVIDER` already is. A test-side allowlist would be
the "somebody remembers to add it to the list" failure wearing a new
costume.

    REACHED_BY = "script_path: handed to the ADMET environment's
                  interpreter by chem/admet_providers.py"
    REACHED_BY = "tooling: consumed by tests/test_tooltip_coverage.py and
                  tools/list_tooltips.py, never by the running application"

**THE KIND IS A CLOSED VOCABULARY AND THE REASON IS FREE TEXT**, which is
the `applies_to`-beside-`category` split: a typo in a free-form kind reads
as a silent exemption, while a new instance of a known mechanism should
need no code change. The two kinds are genuinely different claims -- one
is a runtime entry surface, the other is not an application surface at all
-- and a single flat string would conflate them.

**THE NARROW HALF IS LOAD-BEARING**: a MARKED module must genuinely be
unreachable, derived from the walk. Without it, writing the marker on
anything turns a red guard green.

**A RELATIVE IMPORT IS REFUSED, NOT RESOLVED.** Review asked for
relative-import resolution; measured first, this codebase contains
**ZERO**. Building a resolver and fixtures for a case the tree does not
contain is a second untested code path, and silently dropping one is the
fail-open hole -- an edge the walk cannot see reads as an edge that is not
there. So it raises, naming the file, and a guard asserts both arms. Same
shape as the `**OPNE**` refusal and the inconclusive-probe rule.

## "25 COLLAPSIBLE CATEGORIES" WAS 20, AND MEASURING IT FOUND A 21st

`docs/USER_GUIDE.md` had claimed 25 for as long as it can be traced, and
three earlier attempts to measure it failed. Driven in the real
application -- aspirin selected, Properties dumped -- it is **20**, which
is exactly what `_every_reachable_category()` in
`tests/test_calculator_sections.py` already answered. That function reads
the registry, both descriptor spec tables, and RUNS `compute_alerts`, so
there was never a need for a second enumerator; the guard lives beside it
rather than in `test_docs_are_current.py` for that reason.

**THE FIRST RUN SHOWED 21, AND THE EXTRA ONE WAS A BUG.** A section named
`other`, holding a single result: **"Partial Charge (Gasteiger)"**.

`compute_per_atom` is the always-on batch, explicitly "not registry-driven",
and the panel routed it by looking its `property_id` up in the registry
anyway. Two of its three datasets resolved **by coincidence**:

    crippen_logp_contrib   registered too  -> lipophilicity   by luck
    crippen_mr_contrib     registered too  -> electronic      by luck
    gasteiger_charge       NOT registered  -> "Other"

The registered charge calculator is `gasteiger_charge_at_ph`, a different
calculation with a pH parameter, so no twin existed for the third one and
it fell through. `PerAtomDataset` carries a declared `category` now, the
batch sets all three, and the panel prefers the producer's declaration
with the registry as the FALLBACK -- which keeps working for every dataset
a registered calculator produces, since those declare nothing and are
placed by exactly that lookup.

**AND THE EXISTING SUITE CAUGHT THE AMBIGUITY IN THAT FIX IMMEDIATELY.**
`test_a_calculators_result_lands_in_its_own_section` reads
`getattr(result, "category", None)`, and adding a field defaulting to `""`
made every registered per-atom result start "carrying" one -- 16
mismatches, `button in 'charge', result in ''`. Empty is not a missing
value here; it is the producer saying *I am in the registry, ask it*. The
guard reads `or None` now and keeps its real teeth: a NON-empty category
disagreeing with its definition is still the bug it was written for.

**THE DIAGNOSTIC COULD NOT NAME WHAT IT LISTED.** `_dump_container_items`
printed `CollapsibleSection` twenty-one times, so its own docstring's
question -- *"one section is given half"*, which one? -- was unanswerable
from its output. It reverse-maps `_sections` and prints the category now,
which is how the `other` section was found at all.

**THIRTEEN MUTATION ARMS, THIRTEEN CAUGHT**, each by the intended guard,
and one of them is a note about harnesses rather than about the code: M6
(unmarking a genuinely unreachable module) scored `INVALID -- only 92 of
93 ran`, because the kind/reason guard is PARAMETRISED OVER THE DECLARED
SET and removing a declaration legitimately removes a case. The ran-count
rule that catches an arm which errored out is the same rule that
false-positives here. Re-run by hand it fails
`test_every_module_is_statically_reachable_or_declares_why_not`, which is
the intended catcher.

## SHIPPED IS NOT REACHABLE, AND FOUR MODULES PROVED IT

PR #41 added `chem/hlb.py`, `chem/tsei.py`, `chem/polarizability_miller.py`
and `chem/gutmann.py`. Each was correct, guarded by its own test file, and
registered in `docs/sources.toml`. **Not one was reachable from anything a
user could press.** Measured against the RUNTIME registry rather than by
grep, because a dynamic import makes a text search lie: 51 calculators
backed by 27 modules, none of them among the four.

Every test passed. "Shipped" had come to mean *the file exists* rather than
*source -> registry -> UI*.

`tests/test_calculator_reachability.py` is the guard, and it checks BOTH
directions -- every registered calculator's compute is callable, and every
module that DECLARES itself user-facing is reachable from one.

**USER-FACING IS DECLARED, NEVER INFERRED FROM LIVING UNDER `chem/`.** That
inference is `inapplicable_calculators` again, a rule keyed on something
incidental that rotted into 27 wrong entries. A module carries a
`USER_FACING_PROVIDER` string naming the surface it reaches; the audit reads
the declaration. An exemption LIST would be the same blocklist in a new
place, and a module WITHOUT the marker is not claimed to be internal -- it
is simply making no claim, the same scope `DEFERRALS` has.

**THE WALK MUST FOLLOW A DEFERRED IMPORT, and that is the load-bearing
half.** Two of the four are reached only from inside a function body --
`electronic_properties` imports Miller in its method dispatch, `lewis`
imports Gutmann in its line builder -- so an `ast` walk restricted to
module-level imports reports both unreachable and is WRONG about it.
`test_the_reachability_walk_follows_a_deferred_import` asserts those two
edges by name, and `test_a_module_nothing_reaches_would_fail_this` asserts
the walk is not simply returning everything.

### A DESCRIPTION IS A TOOLTIP, AND ONE HAD ALREADY ROTTED

`property_panel._calculator_help` GENERATES each help contract from
`CalculatorDefinition.description`, so a description is not a comment --
it is what a user reads on hover, and the one place this application says a
method is unavailable.

**`topology_analysis` said the Szeged index was "deliberately omitted"
while its own module docstring, twenty lines from the compute function,
said "The SZEGED INDEX is now included, validated by a THEOREM".** Two
statements about one quantity in one feature, disagreeing, and the one a
user reads was the wrong one. It rotted unaided.

`CALCULATOR_CLAIMS` in `tests/test_docs_are_current.py` is the guard, in the
`DEFERRALS` shape: a `fragment` that must occur EXACTLY ONCE, and an
`unbuilt` predicate over CODE. **THE CLAIM IS DECLARED, NOT DETECTED** --
"is not offered", "is unavailable" and "does not provide" are one claim in
three shapes, and deciding whether a sentence asserts unavailability is the
prose analysis `help_tooltip.py` refuses.

A phrase scan survives as a **CANDIDATE DETECTOR, never a semantic oracle**.
It says "this looks like an availability claim and is not registered --
classify it", never "this sentence is false". Its failure message is worded
that way deliberately: pretending natural language is a type system is how
such a check decays into `NEGATIVE_WORDS = {...}` and starts flagging "this
estimator is intentionally absent". **It earned its keep on its first run**,
catching a "Davies' HLB is not offered" sentence written minutes earlier.

**SCOPE IS AVAILABILITY OF AN EXTERNAL METHOD, NOT OUR OWN SCOPE.**
`orbital_electronegativity` says the pi component "is not offered -- it
needs a separate pi-charge iteration", which is a statement about OpenChem
behaviour and is still true; it was reworded rather than registered. Same
split `help_tooltip.py` draws between an external fact and our own.

### EQ 7 WAS A SPECIAL CASE AND SHIPPED AS THE DEFINITION

`chem/tsei.py` computed `TSEI = SUM 1/L_i^3`, which is [source:cao2004]'s
eq 7 -- derived one line after "**For any alkyl, it only contains carbon
and hydrogen atoms.** When its hydrogen atoms are ignored, eq 4 also can be
simplified to eq 6". The general quantity is eq 4, each atom's covalent
radius over the SUMMED BOND LENGTHS to the reaction centre.

    an all-carbon path      every R_i/R_C is 1 and every l_i is L_i x l_CC,
                            so eq 8a collapses to eq 7 EXACTLY
    a first-tier chlorine   the paper derives 1.4190 in full; eq 7 gives
                            1.000, because it cannot tell a chlorine from
                            a carbon

**TABLE 1 IS BLIND TO THIS, WHICH IS WHY IT SHIPPED.** All twenty normal
alkyls reproduced perfectly against the wrong implementation. A fixture
family is not "big enough" -- it is degenerate or not with respect to a
specific defect, and this file has now recorded that four times.

**TABLE 6 IS WHERE THE HETEROATOM VALUES ARE, and finding it changed
everything.** It prints TSEI for F, Cl, Br, I, MeO and OEt, and its
footnote c says its values include hydrogens where Tables 1/2/4 ignore
them. **18 of the 19 reachable printed values now reproduce.**

    Table 1, n = 1..20     the CONSTANT      blind to the radius term
    a first-tier halogen   the RADIUS term   1.4190 vs eq 7's 1.000
    MeO 0.9505, OEt 0.9939 the TRAVERSAL     a multi-bond path through a
                                             heteroatom, where l_i stops
                                             being L_i x l_CC

#### THE RADII WERE RECOVERED BEFORE THE BOOK ARRIVED, AND THE TWO AGREE

The paper's radius source is Lange's Handbook of Chemistry 15th ed., Table
4.7 "Covalent Radii for Atoms", p 4.35 -- its ref 18. **This project did
not hold it when TSEI was corrected**, and typing a remembered Pauling
table is the "fields nobody can check" failure recorded in this project's
own citation audit -- six errors, every one in the field nothing could
verify.

So every radius was **inverted from a TSEI value the paper prints**. For a
lone first-tier atom, eq 8a collapses to `8 rho^3 / (1+rho)^3` with
`rho = R_X/R_C`, which inverts to a radius:

    F   0.7449  ->  0.63997     Cl  1.4190  ->  0.99001
    Br  1.6957  ->  1.14002     I   2.0265  ->  1.33000
    H   from Me = 1.0362  ->  0.30001
    O   from MeO = 0.9505 ->  0.66      (OEt = 0.9939 uses both at once)

Every one landed on a clean two-decimal value, which is itself evidence
the inversion was reading a real table rather than fitting noise, and it
IDENTIFIED the family as the tetrahedral covalent radii -- a measured fact
rather than an inference from the numbers looking familiar.

**THE BOOK THEN ARRIVED AND AGREED WITH ALL SEVEN TO THE LAST DIGIT** --
64, 99, 114, 133, 30 and 66 pm, and carbon at **77.2** rather than a
rounded 77, which is the extra digit the paper itself writes and what
identifies this as the right table rather than a neighbouring one. Its
footnote settles the column: "Single-bond radii are for a tetrahedral
(CN = 4) structure". Two routes sharing no step, agreeing seven times.

**THE INVERSION IS KEPT AS A LIVE CROSS-CHECK, not as history.** A
mistyped radius for any of those seven would have to be wrong in exactly
the way that reproduces a number from a different paper. The other 21 have
the book alone, and `tsei_radii.json` says which is which -- a radius with
a second independent route to it is a different kind of number.

**WHAT THE BOOK CHANGED IS THE COVERAGE, and it is most of drug space.**
Nitrogen (70 pm), sulfur (104) and phosphorus (110) are not among the
substituents the paper tabulates, so the inversion could never have
reached them and the projection refused every amine, thiol and phosphine.
28 elements now.

**THE EQUATION IS GEOMETRIC AND THE VALIDATION IS NOT**, which is the
distinction to keep as the table widens. `R^3 / l^3` has no per-element
fitting, so a radius is the only input any element needs; but Cao & Liu
validated against alkyl, halogen and ether substituents on biphenyls, so a
silver or a mercury radius buys arithmetic rather than evidence.

**RDKit's `GetRcovalent` IS A DIFFERENT TABLE** -- Cordero 2008, carbon
0.760 against 0.772, chlorine 1.02 against 0.99 -- and it puts the paper's
own chlorine example at 1.5052 against 1.4190.

#### THE PAPER'S OWN STRAW MAN WAS SHIPPED AS A FIXTURE

A fixture quoted "their corresponding steric effect increments delta-TSEI
... should be 0.1250, 0.2500, and 0.3750" and asserted t-Bu = 1.3750; its
successors are `test_tert_butyl_carries_the_papers_own_crowding_correction`
and `test_two_branches_are_not_corrected_and_table_4_is_why`, which assert
1.8125 and keep the two-branch case plain. That sentence is
the paper setting up a question it then answers with **no**: it concludes
three carbons on one carbon contribute 6.5 times one, and every TSEI it
publishes afterwards uses that -- t-Bu is 1.8125 in Table 2 and 1.8395 in
Table 6. Table 2 tabulates both variants and prefers the corrected one,
R = 1.0000 against 0.9411.

Quoting a source is not the same as reading it. The quote was accurate and
the conclusion drawn from it was the opposite of the paper's.

#### AND ONE PRINTED VALUE DOES NOT REPRODUCE, recorded rather than chased

Table 6 gives i-Pr as 1.3752 where the traversal gives 1.2801. The paper's
own text, Table 2 and every i-Pr-bearing row of Table 4 all say 1.2500 with
hydrogens ignored, which plus its seven hydrogens is 1.2801. Reaching
1.3752 needs the two second-tier carbons scaled by 2.7611, a factor the
paper never states and which Table 4's own two-branch rows (i-Bu 1.1990,
s-Bu 1.2870) refute. 1.3752 is within 0.0002 of 1.3750 -- t-Bu's
plain-additivity value in the table directly above it.

### A PAPER'S PROSE AND ITS TABLES CAN DISAGREE, AND THE TABLES WIN

[source:miller1990] p 8535 states the `CBR` rule as a hydrogen count: "one
for branched trigonal carbon atoms (CBR) in trigonal carbon atoms **not
bonded to hydrogen atoms**, and the other for alkenes and aromatic systems
(CTR) in trigonal carbon atoms bonded to **at least one hydrogen** atom."

That sentence is simpler than the conjugation rule, reads as authoritative,
and **is contradicted by the paper's own Table II three pages later**:

    toluene       6CTR 1CTE 8H      ipso carbon, NO hydrogen, and CTR
    styrene       7CTR 1CBR 8H      ipso carbon, NO hydrogen, and CBR
    acetone       2CTE 1CTR 1OTR4 6H
                                    carbonyl carbon, no hydrogen, and CTR
    b-methylnaphthalene           8CTR 1CTE 2CBR 10H
    a-naphthalenecarboxaldehyde   8CTR 1OTR4 3CBR 8H
                                    THE SAME RING POSITION, CTR under a
                                    methyl and CBR under a conjugated CHO

No hydrogen count produces that last pair. The hydrogen rule was
implemented here for one commit on the strength of the sentence and put
benzene at **13.99 against 10.39** -- the +36% shape the module's own
docstring already warns about.

**THE ASSIGNMENT COLUMN IS A FAR STRONGER ORACLE THAN THE TOTALS**, and it
was sitting unused. Benzene and CCl4 pin the numbers; Table II pins which
ROW every atom got, which is where the error class actually lives. Nine
molecules are fixtures now, chosen because they SEPARATE the two candidate
rules -- the two-molecule check could not have caught this, and did not.

Nitrobenzene is the one disagreement in nine and is named rather than
smoothed over: the paper gives `6CTR 1NPI2 2OTE 5H`, differing on the ipso
carbon AND on the nitro oxygens. That row is also one of the worst in the
table at -6.8%, and the paper's own text lists nitrobenzene among the
molecules whose correction "lead to a larger deviation from experimental
results".

### THE JOIN FOUND A DEFECT THE TRANSCRIPTION TESTS COULD NOT

Wiring Gutmann's numbers to a drawn structure needed one row per liquid,
and two liquids turned out to be carrying **half their data each**:

    donicity("dioxane")   AN 10.8, no DN     the DN table spells it "Dioxan"
                                             and prints 14.8
    donicity("glyme")     AN 10.2, no DN     the DN table files it under
                                             "Dimethoxyethane (DME)"

One solvent, two names, split across the donor table and the acceptor
table. Every test in `tests/test_gutmann.py` passed -- they check the
transcription against the page, and each half IS on the page.

Confirmed against the paper's own prose rather than by the names looking
alike: p12 reads "faster in THF (DN = 20) than in dioxane (DN = 14,8)",
using the -e spelling for the row the DN table spells without one.

**DECLARED, NEVER FUZZY-MATCHED.** `difflib` pairs "1,2-dichloroethane"
with "dichloromethane" and "isopropylamine" with "isopropyl myristate" at
the same confidence -- two different liquids and a wrong merge no numeric
test would catch. `_SPELLING_VARIANTS` in the generator is two declared
pairs, and it fails closed on both sides: a variant naming a row that does
not exist, or a variant whose two spellings both already carry the same
field.

**AND `diglyme` IS THE ARM THAT SAYS NO** -- a different ether, keeping its
own row with an acceptor number and no donor number, which is what the
paper prints.

#### NOT ONE SMILES IS TYPED FOR THE STRUCTURE LOOKUP

`domain/lewis.py` was written with room for "what is coming -- donor and
acceptor numbers", and filling it needs a name -> structure map. Writing
sixty SMILES by hand for liquids like selenium oxychloride and
phenylphosphonic difluoride would be sixty chances to ship a plausible
wrong molecule.

The structures come from `abraham_solutes.json` instead -- a SHIPPED,
SOURCED dataset keyed by InChIKey and carrying each solute's name -- so the
join is name to name and every structure was somebody else's transcription
with its own provenance. **35 of 66 solvents are reachable from a drawn
structure**; the rest have no structure here and get no donicity rather
than a guessed one.

`test_the_structure_map_is_derived_and_not_a_typed_list_of_smiles` asserts
the module contains no `MolFromSmiles` at all.

**GUTMANN NUMBERS MUST NOT ENTER THE ABRAHAM CALCULATION.** They are
additional solvent FACTS, never another descriptor -- the creep is obvious
and would be plausible ("since we have DN, use it as a predictor") and
nothing in either source establishes that relationship. Asserted
structurally, because the numeric version would need a solvent whose DN
moved and there is none.

**DN AND AN ARE TWO LABELLED FACTS, ALWAYS**, asserted on the presentation
object rather than trusted to prose: a later tidy-up into one "Gutmann"
field would erase the distinction without breaking any numeric test. Water
is 18.0 DN against 54.8 AN with a THIRD number, 33.0 bulk; HMPA is 2nd of
46 by donor number and in the bottom third by acceptor number.

### A MUTATION FOUND A GAP IN THE DECLARED-TOTALS AUDIT

Fourteen arms, thirteen caught first time. The fourteenth -- declaring a
plausible total on the TSEI projection, `declare_total(0.0, "TSEI
projection total")` -- **passed every guard in `test_declared_totals.py`
and every guard in `test_tsei.py`.** That audit checks a declaration EXISTS
and is WELL FORMED; only naming the calculator says which answer is right,
which is exactly why
`test_the_two_meaningless_sums_are_declined_by_name` names its members
individually. `tsei_projection` joined that list.

The chemistry behind the name is worth having beside it: on chloromethane
the carbon feels 1.4190 from the chlorine and the chlorine feels 0.6729
back, across the same bond. The increments are ASYMMETRIC, because `l_i` is
a bond length and the radius sits in the numerator on one side only, so the
sum over atoms is 2.0919 -- not either atom's answer, not twice anything,
and not a property of the molecule.

**AND THE FIRST VERSION OF THAT ARM WAS NOT A MUTATION AT ALL.** It wrote
`{...} if False else decline_total(...)`, which changes no behaviour, and
scored a confident SURVIVED. Fifth instance of that lesson here; the
harness prints an EDIT-CHECK and compares the arm's ran-count against the
control's, and neither catches an edit that lands and does nothing.

### `{"do": "scroll"}` -- because a panel that scrolls hides its own output

Measured with a Lewis result on screen: **viewport 396x580 against content
396x2361**, so five sixths of the Properties panel is unphotographable from
the top. `dump` reports that the content FITS and `rendered_overflow`
reports 0 findings -- both true, and neither is a picture.

The step takes `{"to": "bottom"}`, `{"to": "top"}` or `{"y": 1000}` and
LOGS where it landed, because a request past the end is clamped and a
silent clamp makes "I scrolled to the bottom" a claim about a position
nobody checked.

**SCROLLING TO THE BOTTOM OVERSHOOTS A TALL RESULT BOX.** The result widget
is mostly empty below its text, so `to: bottom` photographs blank space
with the text above the viewport. Find the band first -- count dark rows
per scanline across a few positions -- then crop to it.

## Verification standard

This project's convention, established across many sessions: **claims are
measured, not asserted.** Before shipping a formula, a threshold, a parser
regex or a model, verify it against a primary source or a real run and record
what was checked. Several things were deliberately NOT shipped because they
could not be validated (Miller polarizability, HLB, TSEI) — that is a normal
outcome here, not a failure.

Comments explain **why**, especially where something is non-obvious or was got
wrong once. A comment restating the code is noise.

### A ROUND TRIP can pass without exercising what it is named for

`_cif_value` writes an mmCIF token back out, quoting where CIF needs it.
The test for it built an atom named `C1'`, rebuilt, and asserted the name
came back as `C1'`. It passed. **Mutating `_cif_value` to quote nothing
at all left it passing**, because `C1'` is legal bare -- CIF only treats
a quote as a delimiter after whitespace -- so this module's own tokeniser
returned it correctly either way.

A round trip through ONE reader tests the pair, not the writer, and a
symmetric bug is invisible to it. The fix was to assert the bytes as
well: `"C1'"` appears quoted in the output, which is what RCSB writes and
what stops the correctness resting on every downstream reader agreeing
about a bare apostrophe.

**A test naming a behaviour is not a test of it**, and a mutation is the
only thing that tells the two apart. Two of the three mutations run over
that change were caught immediately; this was the one that was not, and
it was the one whose test read most convincingly.

### A docking A/B needs a pinned seed AND its own noise floor

`VinaDockingProvider` passes `seed=None`, so the shipped app runs Vina
with a **random seed** and two runs of the same receptor already differ.
Any A/B on a receptor change is measuring the search wandering until the
seed is pinned -- and pinning alone is still not enough, because changing
the receptor changes the pdbqt and so the search trajectory even at a
fixed seed. **Measure the same-receptor spread as the control's control**
or there is no scale to read the difference against.

Both halves, on 4DKL with the same box:

    pinned seed, deposited vs built    dRMSD 0.33-0.54 A
    unpinned, same receptor twice      dRMSD 0.24-0.41 A

Those overlap, which is the finding: building the dimer does not move a
pose whose pocket is inside the monomer. Reported as overlapping rather
than as "identical" -- at n=3 and n=2 there is nothing else to claim.

The contrast case is what proves the measurement can detect anything at
all. HIV-1 protease (1HHP) deposits one chain and annotates a dimer, and
its site sits ON the 2-fold with one catalytic aspartate from each chain:
monomer vs dimer moves the pose **2.6-9.1 A** and scores 0.9-1.3 kcal/mol
better on every seed. **A control that cannot fail is not a control**, so
run the case where the answer must change alongside the case where it
must not.

To pin the seed without bypassing the code under test, wrap
`ExecutableVinaEngine.dock` and inject it. Note the provider calls that
method **by keyword**, so a positional wrapper raises `unexpected keyword
argument 'seed'` -- accept `**kwargs`.

### A whole CORPUS can be degenerate, and then size proves nothing

Same family as the bimodal threshold below, one level up: it is not only
a calibration molecule that can have the wrong shape, it is every case
you have.

**All 49 receptors in the bundled catalogue carry axis-aligned assembly
operators.** So a builder that TRANSPOSES its rotation matrix produces
byte-identical output for all 49, and "verified against 49 real deposits"
is worth exactly nothing against that bug. Measured through
`benchmarks/assembly/`, with the transpose applied on purpose:

    4DKL   pass      4EA3   pass      5I6X   pass
    2OMF   FAIL by 118.5 A            <- the only dense rotation in reach

`swap-translation`, by contrast, is caught by all four. So the corpus was
blind to one operation and fine on another, which is invisible until you
mutate for each separately -- **a corpus is not "big enough" or "small",
it is degenerate or not with respect to a specific mutation.**

Two habits from it:

- **Add the non-degenerate case deliberately and say why**, in the corpus
  itself. 2OMF is in that gate for no other reason, and
  `tests/test_assembly_gate.py` fails if it is removed.
- **Check the declaration against the data.** That test requires an entry
  claiming to catch a transpose AND asserts the real matrix is
  non-symmetric, because a flag on a symmetric matrix would leave the
  gate exactly as blind while looking guarded -- how
  `inapplicable_calculators` rotted.

**A gap you cannot close should be DECLARED, and the reason DERIVED.**
The same corpus has a product expression (1A34 assembly 6,
`(X0)(1-10,21-25)`) which cannot catch a reversed composition, because
that deposit defines X0 as the exact identity and composing the identity
is order-independent. Measured, not assumed: `--mutate
reverse-composition` passes the entire corpus while `--mutate
union-product` fails it by 81.7 A. Nothing better is reachable -- every
product with a non-identity outer group sits in an assembly RCSB does not
pre-generate, and the one it does serve is 16 million atoms.

A corpus that merely FAILED to cover something looks identical to one
that decided it could not. The entry therefore carries
`catches_composition_order: false` with its justification, and the guard
**derives** that flag's correct value from the deposit's own matrix
rather than reading it -- so flipping it to claim coverage fails. The
first version of that guard skipped the `true` branch instead of checking
it, which a mutation caught: the docstring promised it would fail loudly
and the code returned early.

### Open Babel reads mmCIF elements CASE-SENSITIVELY, and the archive is uppercase

The same deposit in two formats was not the same molecule.
`_atom_site.type_symbol` is written `CL`, `ZN`, `SE` throughout the PDB
archive; Open Babel 3.1.0's mmCIF reader matches that against its element
table case-sensitively and comes back with atomic number **0**, element
unknown. The PDB reader has always matched case-insensitively.

    minimal mmCIF, one atom, nothing varied but the symbol
    CL CA NA ZN FE MG MN CU BR SE NI CO   ->  0            12 of 12
    Cl Ca Na Zn Fe Mg Mn Cu Br Se Ni Co   ->  correct
    C N O S P F W I                       ->  correct either way

**It is not the eight elements it was reported for -- it is EVERY
two-letter symbol.** One-letter symbols cannot differ in case and were
never affected, which is why nothing noticed for so long: a protein is
C, N, O and S.

**The atom was then DELETED, not mistyped**, which is the worse of the
two failures and the reason it was invisible. Both Open Babel paths drop
`atomicnum == 0` -- `receptor_atoms_from_structure` skips it, and
`VinaDockingProvider._drop_untyped_atoms` deletes it because Open Babel
writes an untyped atom into a PDBQT as `*` with an empty AutoDock type
and Vina 1.2.7 then refuses the entire file. So a receptor reached Vina
silently one atom short rather than obviously broken. Measured over the
bundled catalogue in mmCIF form:

    49 receptors, 30 atoms lost, 16 entries affected
    the same 49 as PDB                            0 lost
    inside the entry's binding-site box            7 entries

**The strict in-box count UNDER-reports it, in both directions, and the
proximity measurement is the one to read.** Five of those seven are not
ions near the site at all -- the box-defining LIGAND loses its own
halogen (eticlopride, nemonapride, AM6538, diazepam, baclofen all carry
chlorine), so the box was computed from an incomplete molecule and came
out up to **0.86 A off centre with a different size**. And 3HS4's
catalytic zinc scores as OUTSIDE the box while sitting **1.94 A from the
acetazolamide that coordinates it** -- the single most important atom in
that site, on the one catalogue entry whose own caveat says binding
requires it. A binary in-or-out test cannot see either case.

The fix is `pose_analysis.normalise_element_symbols`, applied beside
`filter_altlocs` on **both** Open Babel paths -- the same
analysis-and-preparation-must-not-diverge rule that `is_stripped_residue`,
`filter_altlocs` and `is_symmetry_generated` each exist for. There is no
Open Babel read option for it (mmCIF offers only `s`, `p`, `b`, `w`).

**NOT at the `structure_io` boundary, and that is the load-bearing
choice.** The uppercase file is CORRECT mmCIF -- `type_symbol` is
case-insensitive in the format and Mol* reads it perfectly. Normalising
at import would rewrite the text that becomes
`MacromoleculeModel.structure_text`, which the viewer renders and a saved
project STORES, so a correct deposit would be permanently altered on disk
to work around one consumer's lookup. Only the copy handed to Open Babel
is touched. It also covers routes `structure_io` never sees:
`receptor_library_service`'s mmCIF fallback, and `build_assembly`, which
copies `type_symbol` verbatim and so carries the problem into every built
assembly.

Rewriting is conservative by construction -- a value is changed only when
it is **not** an element as written and **is** one after normalising, so
`?`, `.`, `D` and anything unrecognised are left for Open Babel to
reject rather than guessed at. The substitution is length-preserving, so
column alignment survives byte for byte.

`test_open_babel_really_does_lose_an_uppercase_symbol_without_the_fix`
asserts the DEFECT on purpose: if a future Open Babel stops losing `CL`,
it fails and the workaround can go.

#### Two things this cost, both general

- **A fixture with a column after the one under test proves less than it
  looks.** `_cif_tokens` split on space and tab only, so the line
  terminator folded into a row's LAST token -- `type_symbol` declared
  last read as `"NA\n"` and matched no element. Every existing caller
  strips first, so nothing had ever hit it, and every fixture built in
  RCSB's tag order (where `pdbx_PDB_model_num` is last) passed while the
  bug was live. Found only by writing the minimal reordered case.
- **Two of eight mutations survived, and both were EQUIVALENT rather than
  uncaught.** One removed a redundant `all(tag.startswith("_atom_site."))`
  guard that `tags.index` already implied -- deleted, and replaced with a
  suffix-match mutation that is real (`_chem_comp_atom.type_symbol` is a
  genuine category) and is caught. The other removed the PDB/mmCIF
  dispatch, which cannot be caught because the mmCIF walker is inert on
  PDB text. That limit is written into the test rather than papered over
  with a fixture no real file resembles. **A surviving mutation is a
  question, not automatically a verdict on the test.**

#### Two SEPARATE format divergences found beside it, both now fixed

Found while measuring the element bug, diagnosed separately, and fixed in
the same branch. Neither is caused by the element bug and neither was
fixed by it -- each was measured before and after to be sure.

##### `_single_copy` picked a different ligand copy per format

mmCIF gives Open Babel `label_asym_id` and PDB gives author chain ids,
and the tie-break sorted on the chain. It also reports **no residue
number at all** from mmCIF. 3HS4's three acetazolamides are chains D/E/F
numbered 0 in mmCIF and A/701, A/702, A/703 in PDB, so the two formats
boxed **17.96 A apart**; 8EF5 was **36.08 A** apart, with the two copies
ordered in opposite directions by the two formats.

**And one of the two answers was simply wrong.** 3HS4 is carbonic
anhydrase II, where acetazolamide binds by coordinating the catalytic
zinc, so exactly one of its three copies is the pharmacology:

    copy    protein atoms within 4.5 A    nearest Zn
    A/701                          46        1.94 A   <- the real site
    A/703                          34       16.62 A
    A/702                          22       17.31 A

The mmCIF arm was boxing A/703 -- a surface crystallisation artefact.
Ties are the NORMAL case here, not the exotic one (equivalent copies have
equal atom counts by construction), so the tie-break decides most
multi-copy structures rather than a rare few.

The fix ranks on `(atom count, burial, centroid)`: size first, as before;
then how many non-water atoms lie within 4.5 A
(`pose_analysis.HYDROPHOBIC_CUTOFF`, reused rather than reinvented); then
a geometric tie-break so a genuine draw still resolves the same way every
run. **Coordinates are the one thing the two formats agree on exactly** --
verified atom for atom to three decimals -- which is what makes a
geometric criterion reproducible where a label is not.

**Waters are excluded from burial deliberately.** An exposed copy is the
one with the most ordered waters around it almost by definition, so
counting them inverts the ranking; 3HS4 is a 1.10 A structure with waters
modelled everywhere.

**IT MOVES 13 OF 48 CATALOGUE BOXES, by 27 to 76 A, and that is not a
regression** -- it is which equivalent copy gets docked. Checked entry by
entry against two signals the rule does not optimise (nearest metal, and
distinct residues contacted): in every moved case the copies are
near-equivalent (contacts within a few percent) and the new choice is
equal or better. 3HS4's PDB arm already picked the right copy; only the
mmCIF arm changed there.

Confirmed by redocking with real Vina, one before arm and two after --
see `chem/binding_site.py` for the table. All seven targets land in the
same pocket in every arm, run-to-run scatter is ~0.03 A, and 4EY7 (whose
box moved to a more buried copy) improves **0.69 -> 0.37 A**, twenty
times the noise. The docstring's old 3.90 A for 3EML **does not
reproduce**: the before arm on unchanged code gives 2.59 A.

**`benchmarks/docking/redock.py` had to change with it.** It called
`_single_copy` a SECOND time to find the crystal pose to measure against
-- with no receptor, so no burial -- and would have compared a docked
pose against a different copy than it docked into, reporting a large
shift that reads as a bad box. `BindingSite.ligand_positions` now carries
the chosen copy, so there is one answer rather than two derivations.

##### Open Babel leaves every implicit hydrogen count at zero from mmCIF

4DKL gained **3,754 hydrogens** through the PDB reader and **41** through
the mmCIF one at the same pH. It reaches the score: Vina reads AutoDock
types, which encode hydrogen bonding, so a backbone nitrogen came out `N`
from PDB and `NA` -- acceptor, no attached hydrogen -- from mmCIF.

**It is not bond perception, which was the obvious suspect.** Both
formats give byte-identical connectivity (3,726 bonds, 2,919 single and
807 double). It is the implicit count alone, and aromaticity comes back
with it (270 aromatic bonds against 0), because both are assigned in a
pass the mmCIF reader never runs.

`OBAtomAssignTypicalImplicitHydrogens` per atom fixes it exactly, and is
**applied unconditionally because it is a no-op where the reader already
did the work** -- verified on seven deposits, the PDB arm identical with
and without it. A format branch would be one more place for the two paths
to drift.

It must run AFTER the strips: deleting a covalently bound ligand frees a
valence, and 4DKL's beta-FNA is bonded to Lys233 while every catalogue
box strips its own defining ligand. Measured, the lysine reaches Vina
with 4 polar hydrogens when assignment follows the strips and 3 when it
precedes them.

**A fixture built on a CARBON cannot test that ordering.** The rigid
PDBQT writer merges nonpolar hydrogens into their heavy atom, so an
otherwise identical covalent fixture on a CB produces byte-identical
output either way -- the first version of that test asserted nothing, and
the mutation survived. The attachment has to be to a nitrogen, where the
freed hydrogen is polar and appears as its own `HD` line.

5KIR is the one deposit that still differs, by 5 hydrogens in ~18,700,
and the bonds behind it are named atom by atom in
`_assign_implicit_hydrogens`. The mmCIF arm misses four real glycosidic
linkages AND invents one bond that cannot exist -- two oxygens 1.270 A
apart, shorter than a peroxide -- which displaces the real C6-O6 it
competes with. Same coordinates in both files; only the perception
differs.

**"Open Babel ignores mmCIF connectivity" is WRONG, and disulfides are
the counter-example.** That was written here as a fact on the strength of
the glycan result alone, and measuring it killed it: every S-S pair
within 2.5 A is bonded in BOTH formats, including all ten of 5KIR's own,
checked against the geometry rather than against the bond list across
eight deposits. Distance perception finds a disulfide regardless. What
the two readers disagree about is the cases distance alone gets wrong,
and **the mechanism is not established** -- which is the honest state,
and better than the tidy explanation that was there before.

The lesson is the file's own: a residual explained by inference is not
explained. The glycan observation was real; the sentence generalising it
to `_struct_conn` was invented, and it survived review because it sounded
like a mechanism.

##### The parity sweep: 0 of 48 before, 38 of 48 after

The single number that says what the three fixes together bought. For
each catalogue receptor, prepare the PDBQT from BOTH formats through the
real `_convert_receptor_to_pdbqt` (altlocs, elements, symmetry copies,
strips, implicit H, protonation, rigid write) and compare the AutoDock
type histogram -- which is what Vina scores against, so it subsumes every
individual fix:

    before (190e552)   identical 0 of 48    e.g. 4DKL 4,120 vs 3,496
                       aromatic carbon `A` present in PDB, ZERO in mmCIF
                       on every entry; 6JP5 differed by 3,966 atoms
    after              identical 38 of 48

**The 10 that still differ do so ONLY in `HD`/`N`/`NA`** -- polar
hydrogens and nitrogen typing. No heavy-atom element differs anywhere in
the catalogue any more, which is the element fix being complete.

The residue is a genuine Open Babel perception difference and is NOT
fixed: on 4M48 the two formats hold the same 7,488 atoms and the same
1,186 nitrogens with identical explicit degrees, yet assign 641 implicit
hydrogens to nitrogen from PDB and 955 from mmCIF, with 9 bonds and the
residue grouping (998 residues against 969) differing underneath. Which
arm is right is not established -- for a ~900-residue protein the mmCIF
figure is the more plausible of the two, which is worth knowing before
anyone "fixes" it toward the PDB answer.

Run it with `benchmarks/`-style throwaway harnesses; there is no
committed script, because it needs all 49 deposits in both formats and
the catalogue cache holds only one.

##### A mutation that ADDS a call is not a mutation that MOVES it

The "assign hydrogens before the strips" arm reported a confident
SURVIVED against a test that does catch the real thing. The arm inserted
a second call early and left the real one in place, so the correct
assignment still ran last and the behaviour never changed. The bytes
changed, which is all the harness was checking.

This is the third time this file has recorded a version of the same
lesson (a mutation script whose edit never landed; an arm that errored
instead of running). **Verify the BEHAVIOUR moved, not the bytes** -- and
for a reordering, the mutation must delete from one place as well as
insert into the other.

### A threshold fitted to a BIMODAL molecule is not validated

The conformer de-duplication threshold was measured honestly, on real
data, documented with its numbers -- and still did not generalise,
because of the SHAPE of the calibration data rather than the care taken
over it.

0.5 A was fitted to butane, whose 40 pairwise RMSDs really are bimodal:
"every pair either below 0.5 or at 0.66, nothing in between". **That
bimodality is a property of butane, not of molecules.** A drug-like
molecule's are a flat continuum -- ethylmorphine's 276 pairs run 0.21 to
0.61 with no gap anywhere -- so the same number that cleanly separates
butane's two clusters cuts a continuum arbitrarily, which is exactly why
its count moved between 2 and 3 across runs.

**Before trusting a threshold, tabulate the underlying distribution on a
case from the population you care about, and look for the gap the
threshold is supposed to sit in.** If there is no gap, no value of the
constant is right and the answer is a different criterion, not a better
number. Measured across the validation set, every purely geometric
criterion failed it; the fix was a second, independent signal.

Three corollaries from the same work, each paid for once:

- **Arguing from numbers your own pipeline produced can be circular.**
  The first evidence here used force-field energies from a path that did
  not converge -- the very defect being fixed elsewhere in the same
  change. Re-measured at convergence the claim survived, but only by
  luck. Check that the inputs to an argument are not the thing under
  repair.
- **Fixing an under-count can create an over-count, and an EXISTING test
  is what catches it.** The new criterion made 2H-azirine, a rigid
  three-membered ring, report two conformers: ~2% of embeddings converge
  to a distorted minimum 10.7 kcal/mol up with the C=N stretched to
  1.339 A. Conformers differ by torsion and ring pucker, never by bond
  length, so that is a force-field artefact and no energy gap should
  promote it.
- **A diagnostic that silently reports zero is worse than none**, because
  it gets quoted as evidence. `TorsionFingerprints.CalculateTorsionLists`
  returns `(non-ring, ring)` and reading only the first made a
  chair/twist-boat pair score "0.0 degrees" against a TFD of 0.407 --
  cyclohexane has ZERO non-ring torsions. That number reached a written
  conclusion before the contradiction was noticed.

### Two empirical fits can CROSS, so one test point proves nothing

The volume-based lattice-energy correlation has separate coefficients
for MX2 and M2X salts, and both have `2I = 6` -- the coefficient table
is keyed on the charges for that reason. A test asserted "swapping them
moves CaF2 by hundreds of kJ/mol" and FAILED, correctly: the claim was
wrong, not the code.

    V^(1/3)   MX2     M2X    difference
    0.3000   3035    3127        +92
    0.3442   2693    2703        +10   <- CaF2, where they cross
    0.6470   1598    1347       -251   <- Cs2MoCl6, real M2X territory

M2X's larger alpha is offset by its negative beta, so the two agree to
10 kJ/mol near 0.34 and diverge past 200 where the M2X salts actually
sit. **Pick the test point from where the data lives**, or assert the
crossing deliberately as that test now does.

#### The volume route needs no radii, which is the whole point

Kapustinskii refuses every polyatomic ion by name -- a thermochemical
radius is a different measurement from a different source and the
shipped table has none. `U = 2I(alpha/V^(1/3) + beta)` needs only the
formula-unit volume, so a nitrate or a hexachloromolybdate is
answerable. Measured over Jenkins 1999 Tables 2 and 3, taking the CRC
Handbook column as the target and the crystallographic volume as the
input so neither side is the paper's own estimate:

    26 salts   mean |deviation| 3.3%   worst 7.7% (Ca(NO3)2)

against Kapustinskii's 7.3% over 36 monatomic salts.

**`2I = sum(n_k z_k^2)` equals Kapustinskii's `nu |z+ z-|` exactly** for
any neutral binary salt -- verified over 1:1, 1:2, 2:1 and 2:3 rather
than taken from Glasser 1995, which is where the identity is noted. That
is what makes the generalisation strictly backward compatible: the
existing 36-salt validation carries over untouched.

**It is NOT wired to the crystal report, and the reason is data not
effort.** The equation needs ion charges; a CIF usually does not state
them, and halite's own deposition carries bare `Na` and `Cl`. The reader
does parse a charge when `_atom_site_type_symbol` gives one (`Na+`,
`O2-`) and then discards it -- the same shape as the `Neighbour`
position it used to throw away. Carrying it through is the next step;
guessing charges is not.

### Normalise the DRAWING, do not fork the vendor

The vendored organometallic perception recognises a sandwich only as
`[cH-]1cccc1.[cH-]1cccc1.[Fe+2]`. Ferrocene drawn the way most people
draw it -- bonds from the iron to both rings -- returned None, and the
plan for fixing it said to work inside
`vendor/.../organometallic.py`, which is 5,020 lines this project does
not own.

**It did not need touching.** `_as_ionic_sandwich` in
`chem/organometallic_adapter.py` converts the bonded drawing into the
ionic form and hands THAT over: metal-ring bonds removed, rings made
aromatic anions, metal given the balancing charge. Ferrocene,
ruthenocene, cobaltocene and methylferrocene all work from a bonded
drawing now, retained names included.

Three things that made it safe:

- **The ionic path runs FIRST and unchanged.** Normalisation only ever
  sees a molecule the vendor has already declined, so nothing that
  worked before can regress.
- **Removing a bond does not renumber atoms**, so reported indices still
  address the caller's molecule. Asserted, not assumed -- an index that
  quietly means something else is the bug this project hit in Ketcher's
  pool ids and again in the crystal viewer.
- **Hydrogen counts are per atom, not one each.** A substituted ring
  carbon has none, and forcing one made methylferrocene fail to sanitise
  while plain ferrocene worked -- the confusing kind of bug rather than
  the obvious kind.

**Pentamethylferrocene is a VENDOR limit, and a test says so.**
Normalisation produces a correct ionic form for it and the vendor
declines that too. Asserting both halves keeps "our conversion failed"
and "their perception declined" from ever being confused.

### A threshold with two measured bounds is not a taste question

The coordination-geometry tolerance could have been picked by feel. It
was instead squeezed between two numbers, and the window turned out to be
narrow enough that feel would probably have missed it:

    lower  a tris-chelate octahedron at en/bipy bite angles (78 deg)
           scores 7.58 RMSD, and [Co(en)3]3+ is octahedral by any
           account, so anything stricter refuses the textbook case
    upper  trigonal bipyramidal and square pyramidal are 23.24 deg
           apart, the closest pair of references, so 11.62 or above
           can match BOTH and the winner comes down to dict order

10.0 sits inside `[7.6, 11.6)`. `test_the_tolerance_stays_below_half_the_`
`closest_reference_separation` recomputes the upper bound from the
reference table itself, so widening the tolerance fails **naming the pair
that would collide** -- a guard on the constant, not on the code.

Three things worth carrying:

- **Store reference SHAPES, not reference ANGLES.** Writing "90 and 180"
  for an octahedron by hand invites the wrong multiplicities -- it is
  twelve 90s and three 180s -- and a wrong multiset still scores
  plausibly. Unit vectors derive the angle set correctly by construction.
- **Sorted-order pairing of two angle lists is the OPTIMAL pairing**, not
  just a convenient one (1-D optimal transport). Checked rather than
  cited: brute force over every permutation beat it in 0 of 2000 random
  cases. The mutation that removes the sort is caught.
- **The count must never decide.** A pentagonal pyramid has six donors
  and five angles within 5 deg of 90 -- exactly what a "six donors and
  some right angles" rule falls for. It scores 27.5 and is irregular.

#### `Conformer.Is3D()` follows the molblock HEADER, not the coordinates

Measured in all four combinations, because a square-planar complex is
flat by definition and the obvious reading would refuse it:

    header 2D, all z = 0     Is3D() False
    header 3D, all z = 0     Is3D() True     <- flat but genuinely 3D
    header 2D, one z != 0    Is3D() True     (RDKit warns and overrides)
    header 3D, one z != 0    Is3D() True

So a genuinely planar complex from a 3D source is accepted, and a 2D
drawing still is not. `GetNumConformers() > 0` remains useless as a check
-- it is true for every drawn structure.

#### `CoordinationShell` used to keep distances and DISCARD positions

FIXED. `Neighbour` now carries the Cartesian position of the periodic
IMAGE that is actually close -- not the asymmetric-unit atom's, which
would point half of any shell in the wrong direction -- and
`CoordinationShell` carries the centre's. `coordination_shell` had both
in hand the whole time and threw them away, which is the only reason the
crystal path could not report an angle.

`classify_coordination_geometry` takes bare coordinates rather than an
RDKit molecule precisely so both paths share it. Halite's sodium comes
out octahedral at 0.0 RMSD, six chlorides at 2.820 A, verified live.

`test_a_neighbour_carries_the_position_of_the_IMAGE_that_is_close`
asserts `dist(neighbour.position, shell.centre) == neighbour.distance`
for every neighbour, which catches the untranslated-original mutation.

#### A crystal click DID reach the molecular measurement, and it shipped

`MoleculeViewer3DWidget.show_crystal` did not clear `_molecule`, so
`_on_atoms_selected` ran the distance measurement on whatever conformer
was loaded, using indices that came from the unit cell. Correct
arithmetic on the wrong object, printed as a plain number -- the same
shape as the 40619 kcal/mol interaction energy.

The Atom Inspector was spared only by luck: `_atom_is_in_report` refuses
out-of-range indices, so a crystal click into it silently did nothing.

Fixed with a separate `crystal_site_clicked` signal and a
`_crystal_scene` flag that `show_crystal` sets and `set_molecule`
clears -- both halves, because a molecule shown after a cell was the
same confusion in mirror image.

#### The crystal click index DOES address the scene atoms, measured

`scene_as_xyz` writes atoms in `scene["atoms"]` order and 3Dmol preserves
it, so `atom.index` from a click indexes that list directly. **Checked
against the real vendored bundle rather than assumed** -- 60 atoms of COD
1504676, element AND x-coordinate -- because the Ketcher work proved the
identical assumption wrong there (a pool id is not a molfile position).
No translation table is needed here, and now that is a measurement.

Probe recipe, if it ever needs re-checking: build the backend, **size and
show its widget** (`drawWhenSized` waits for 200x150, so a bare unsized
view never draws), `load_crystal`, pump ~4 s, then
`JSON.stringify(viewer.getModel().selectedAtoms({}).map(...))`.

#### The shell rule is not a bond-finder, and hydrogens break it

The shell is cut at the largest RELATIVE gap in the sorted distances,
which suits the ionic structures it was built for. In anything with
hydrogens the biggest gap is usually between the hydrogens and everything
else. Measured on COD 1511792:

    C1 (methyl)   H 0.986, H 0.989, H 0.996 | 47.6% gap | C-C at 1.47 cut
    B1            F 1.361, F 1.368, O 1.502, O 1.503 -> tetrahedral 2.9

So a methyl carbon reports three hydrogens at 109 deg, scores 11.0
against trigonal planar, and comes out irregular. That is correct for
that set of neighbours and misleading only if you cannot see what the set
IS -- which is why the composition is always named ("3 (3 H)") and not
merely counted. **Do not widen the geometry tolerance to make this read
better**: 12 deg would break the trigonal-bipyramidal/square-pyramidal
uniqueness bound and the site would still be wrong.

### A library DEFAULT can be a different quantity, not a tuning knob

`rdMolDescriptors.DoubleCubicLatticeVolume` computes a **solvent-accessible**
volume unless told otherwise: its probe radius defaults to 1.4 A. Called as
its name suggests and read as a van der Waals volume, it is wrong by 700%:

    helium, analytic 4/3 pi r^3          11.494
    DoubleCubicLatticeVolume()           91.952   <- r + 1.4, a DIFFERENT quantity
    DoubleCubicLatticeVolume(probeRadius=0.0)     11.494

The danger is that 91.952 is not absurd. On any molecule without a closed
form it is simply a larger number, and nothing anywhere says which quantity
you asked for. **A one-atom test catches this and nothing else does**, because
one atom is the only case with an exact answer to compare against.

Two more measured facts from the same work, both the opposite of the obvious
reading:

- **`DoubleCubicLatticeVolume` is the ANALYTIC routine and `ComputeMolVolume`
  is the grid one**, despite the names. DCLV matches 4/3 pi r^3 to four
  decimals instantly; `ComputeMolVolume` is 5% low on a lone atom at its
  default spacing and needs 0.89 s to reach 0.04%. `surface_analysis.py` had
  shipped the grid one.
- **The cross-check is weakest where the answer is most certain.** The grid
  routine's error tracks the surface-to-volume ratio, so across ten molecules
  the worst BONDED case is 1.53% while a bare atom is 4.99%. A tolerance
  fitted to real molecules will flag a lone atom, and that is the check
  failing, not the value.

### Bound the grid, not the resolution

A projection measured at a fixed 60 samples/A cost **4.27 s** for a 92-atom
molecule -- unusable in a panel that recomputes on every selection change.
Capping total cells instead of lowering resolution everywhere took it to
**0.80 s** while leaving small molecules untouched (aspirin identical, helium
still pi r^2 to 0.13%).

That is the correct trade and not merely the cheap one: grid error is set by
the shape's perimeter-to-area ratio, so a larger molecule tolerates a coarser
grid at the same relative accuracy. Accuracy is preserved exactly where it is
hardest to get.

### A derivative can be self-consistent, symmetric, and wrong

DREIDING's optimiser needed an analytic gradient (a numerical one is
252 ms per step for neopentane -- an hour for the barrier set against
11 seconds). The first torsion derivative was wrong, and **every cheap
check it could have failed, it passed**: it summed to zero as translation
invariance requires, it was smooth, and the optimiser converged happily
to a geometry that was not a stationary point. The barrier it produced
was plausible.

Textbook forms of `dphi/dr` differ by the direction convention of `b1`
and by the argument order inside `atan2`, so a formula lifted from one
source into another's convention is exactly this failure. **Solve for the
coefficients against a central difference** rather than recalling them --
least squares on a random geometry returned them exactly, and took less
time than reading two more sources.

Two habits that fell out of it, both general:

- **Check each term separately, not just the total.** Bond, angle and
  van der Waals were exact to 1e-8 while torsion was out by a sign; a
  matching total can hide two errors cancelling.
- **Translation invariance is necessary and NOT sufficient.** The wrong
  version satisfied it, which is why it survived inspection.

### A conformer search result is part of the question, not the setup

Butane's methyl rotation barrier came out at 3.171 against DREIDING's
published 3.410 -- alone among eight molecules, and by an amount small
enough to argue about. The force field was fine: `EmbedMolecule` plus an
MMFF cleanup had landed butane in the **gauche** well at -65 degrees, and
a methyl barrier measured there is a different quantity from one measured
on the anti conformer. Forcing the backbone to 180 first gives 3.408.

The tell was not the size of the error but its DIRECTION -- the barrier
came out below propane's, and adding a remote methyl cannot lower a local
barrier. A tolerance wide enough to accept 3.171 would have hidden it.

### Koopmans hardness is wrong for the pair people actually use it on

Recorded here rather than only in `chem/conceptual_dft.py` because the trap is
general: an approximation that reproduces the first case you try is not
validated, and the second case is where it breaks.

Measured on real ORCA 6.1.1 B3LYP/def2-SVP runs of both textbook hard/soft
pairs:

| η (eV) | Koopmans | ΔSCF |
| --- | --- | --- |
| water | 4.57 | 8.06 |
| hydrogen sulfide | 3.90 | 6.93 |
| ammonia | 4.16 | 7.21 |
| phosphine | 4.27 | **7.02** |

Koopmans gets water/hydrogen sulfide right and **inverts ammonia against
phosphine**, making phosphine the harder — when hard nitrogen against soft
phosphorus is one of the most-used orderings in coordination chemistry. Every
molecule here has a NEGATIVE electron affinity, so its "LUMO" is an unbound
state belonging to the basis set rather than the molecule, and Koopmans reads
that number straight out.

Both ship. Koopmans is genuinely free from any job that has already run and
carries a caveat naming this failure on every descriptor;
`test_koopmans_inverts_ammonia_against_phosphine` asserts the inversion **on
purpose**, so if a future method stops inverting it the test fails and the
caveat can come off.

**ORCA compound jobs (`$new_job`) run all three ΔSCF calculations in one
input**, confirmed live — so this needed no notion of chained runs in the
service. The three `FINAL SINGLE POINT ENERGY` lines are told apart only by
POSITION, which is why `test_the_three_delta_scf_blocks_are_written_in_parser_order`
exists: swapping the cation and anion blocks flips the sign of both I and A,
still produces plausible numbers, and survived every other test in the file.

### ORCA ABORTS AT STARTUP IF ITS OWN PATH USES FORWARD SLASHES

Sibling of the already-known "ORCA must not be installed under a path
containing spaces", same mechanism -- ORCA derives the directory of its
helper binaries (`orca_startup` and friends) from the path it was invoked
with. Measured while building `benchmarks/uvvis/`, with the same input
file, the same working directory and the same parent process, only the
separator varying:

    subprocess.run(["D:/ORCA/orca.exe",  "x.inp"])   error termination in Startup
    subprocess.run([r"D:\ORCA\orca.exe", "x.inp"])   TERMINATED NORMALLY

The message names `orca_startup` and nothing else, so it reads as a broken
input file rather than a broken invocation -- four jobs "failed" and the
`.inp` was perfect. It cost an hour.

**A WORKING PROBE DOES NOT CLEAR THE PATH.** A TD-DFT single point ran
fine through the forward-slash path in the same directory minutes earlier;
only `Opt` died. So "I already ran ORCA successfully today" is not
evidence, and neither is any one job type.

`str(Path(p))` is the whole fix and both benchmark generators do it now.

**THE APPLICATION WAS EXPOSED TOO, and the first version of this section
said it was not.** That claim was reasoned rather than checked -- "the file
dialog gives backslashes, so the setting is fine" -- and reading the code
killed it. External Tools' path field is a hand-editable `QLineEdit` whose
`editingFinished` commits the text VERBATIM, so a pasted
`D:/ORCA/orca.exe` is stored as typed; `_resolve_executable_path` then
returned that string unchanged, and `Path(p).is_file()` accepts forward
slashes, so every check the application makes passes and the bad form
reaches `QProcess`. Browse was safe only by accident -- it round-trips
through `Path`, which normalises.

Normalised in two places on purpose:

    PathRow.commit                        where the value ENTERS, so every
                                          tool and every future tool is covered
    _resolve_executable_path              on READ, which is the only thing
                                          that repairs a setting already saved

`qm_surface_service` was already safe, also by accident, because it builds
the `orca_plot` path with `Path(...).with_name(...)`.

**`str(Path(""))` is `"."`**, so the write-time normalisation has to guard
the empty string or clearing the field would store a path to the working
directory and every "is this tool configured" check would start answering
yes. There is a test for that specific mistake.

Two existing tests asserted the old verbatim behaviour and failed when this
landed, which is the change being real rather than a regression.

### A KILLED PROCESS STILL OWNS ITS WORKING DIRECTORY, and cleanup was silent about it

Found as an intermittent CI failure in
`test_quantum_chemistry_cancel_kills_process_and_cleans_up`, on the
Windows gating job only. **Confirmed a flake rather than a regression by
re-running the SAME job on the SAME commit** -- red, then green, no code
change. That is the discriminator worth reaching for first; the local
suite had passed twice on the identical tree.

`start_job` calls `setWorkingDirectory(scratch_dir)`, so the directory
being deleted is the killed process's cwd, and **Windows refuses to
remove a live process's cwd**. `QProcess.kill()` returns before the OS
has reaped. Measured directly -- spawn a child with its cwd there, kill
it, remove immediately:

    immediate rmtree after kill    FAILED 12 of 12
    removable after                ~10 ms, every trial

In the running app the cleanup happens from a Qt signal handler, which is
usually late enough. Only a CANCEL races, and only under load.

**THE WORSE HALF WAS THE SILENCE.** The code read

    try:
        shutil.rmtree(scratch_dir, ignore_errors=True)
    except OSError:
        logger.warning("Failed to clean up ORCA scratch directory %s", ...)

and `rmtree` **cannot raise** with that flag set, so the `except` was
dead code and the warning could never fire. A scratch directory holding
the gigabytes a geometry optimisation writes could fail to be removed
and leave no trace anywhere. The retries keep the flag (a partly-removed
tree deserves another go); the LAST attempt drops it, so a real failure
has a reason and is logged.

**A RACE IS NOT A GUARD, and the obvious test cannot become one.** The
cancel test passes with or without the retry, because it depends on
whether the OS happened to let go in time -- removing the retry left the
whole file green locally.

**AND THE FIRST GUARD WRITTEN TO REPLACE IT WAS ALSO A RACE. IT
REDDENED MASTER.** It killed the child and then immediately tried a
plain `rmtree`, asserting that the attempt FAILED -- true here 12 times
out of 12, and false on a GitHub Windows runner, where the OS released
the handle first. **The control fired correctly and the test was still
wrong**, because it depended on WINNING a race rather than removing one:
a 10 ms window measured on one machine is a property of that machine.

The shape that works holds the directory open instead of hoping:

    control   a LIVE process's cwd, plain rmtree          not removed
    subject   a LIVE process's cwd, `_cleanup_scratch`,
              the process killed 50 ms in                 removed

The subject is the real claim. Cleanup starts while the directory is
definitely held, so its first attempts must fail; the kill lands inside
the retry window and a later attempt must succeed. Attempts fall at 0,
10, 30, 80 and 180 ms, so two come after the kill. Without the retry
there is one attempt and it cannot succeed. Verified by the mutation and
by five consecutive green runs rather than one lucky one.

Windows-gated, because POSIX unlinks a live process's cwd happily and
neither arm can fail there.

**THE GENERAL RULE, PAID FOR FIVE TIMES IN ONE DAY: a guard must not
depend on timing, on the machine's configuration, or on a fixture being
incidentally big enough.** Every one of this session's new guards passed
on the first attempt while testing nothing -- captions too short to
overflow, a configured data root that made a path assertion vacuous, a
250 ms setup inside a 10 ms window, a stale shared window clamping a
resize, and this one. Four were caught by mutating locally. This one
needed a different machine, which is the argument for CI being a second
opinion rather than a rubber stamp.

### A gbw remembers where it was born, and orca_plot goes there

Every ESP surface in the app failed -- `orca_plot exited 64 without
writing job.scfp.esp.cube` -- and the recorded hypothesis was that the
cube had been written under a name `_output_name` did not predict. **That
was wrong. No cube existed under any name.**

The real message, once the run was reproduced by hand:

    CANNOT OPEN FILE
    Filename: D:\OpenChemStudio-scratch\orca_job_933toma8\job.densitiesinfo

**A `.gbw` carries the ABSOLUTE path of the directory it was created in**
-- twice in the gbw, three times in the `.densitiesinfo` -- and orca_plot
follows it rather than looking in the working directory. Retaining a
wavefunction copies the files out of the scratch job directory and
deletes the directory, so the path is dead and type 43 dies with it.
Measured A/B, byte-identical files in the working directory both times:

    baked directory present   exit 0, job.scfp.esp.cube written
    baked directory absent    exit 64, no cube at all

Only ESP. Orbitals and electron density were re-measured in the broken
directory and produce their cubes normally, which is exactly why it read
as "the ESP feature is broken" rather than "the wavefunction store is".

Two traps while fixing it, both worth knowing generally:

- **Restoring only the two SMALL companions is enough.** `job.densities`
  and `job.densitiesinfo` are 35 KB and 1.8 KB against a 1.0 MB gbw; the
  gbw is read from the working directory and does not need copying. Test
  the cheap repair before building the expensive one.
- **The density name must match orca_plot's listing EXACTLY, and the
  listing is fully qualified** -- `D:\...\orca_job_x\job.scfp`, not
  `job.scfp`. The bare name is refused with `Wrong Density Name
  selected`, and this had been shipped for months because **a refused
  name still writes a cube** from the fallback density, which on a
  single-density job is the same one. The values were right; only the
  explicitness was missing. A qualified name also moves the OUTPUT, since
  ESP names its cube after the density.

**A probe that leaves state behind will lie to the next probe.** Having
recreated the baked directory to prove the hypothesis, three subsequent
"cold" runs in fresh directories all passed -- because that directory was
still there, process-wide, invisible to the test. The control that
mattered was deleting it and re-running.

### ORCA's LED summary block does not mean what it looks like it means

Recorded because a plan written without running it specified parsing the
wrong block, and the wrong numbers are plausible rather than absurd.

**`FINAL SUMMARY DLPNO-CCSD ENERGY DECOMPOSITION` is not an interaction
decomposition.** Its correlation lines split the complex's TOTAL
correlation energy into dispersive and non-dispersive parts, intra-fragment
correlation included. Verified by arithmetic against the same output, exact
to the last digit:

    Non dispersion (strong pairs)  =  intra strong pairs
                                    + (inter strong - dispersion strong)
                                    + singles
    -0.414932699                   =  -0.394372938 - 0.020556328 - 0.000003433

So that line reads **-260 kcal/mol** where the real non-dispersive
interaction is **-12.9**. Only the REF lines are what they appear to be:
`Electrostatics (REF.) + Exchange (REF.)` does equal the inter-fragment
reference interaction exactly.

**And `Total interaction` is not a binding energy** -- ORCA reports
**-428 kcal/mol** for BH3-CO, whose bond enthalpy is near -25. A
single-point LED partitions the complex's own energy, so the inter-fragment
part carries all the nuclear-electron attraction between fragments. A
binding energy needs the ISOLATED fragments, which is why `chem/orca_led.py`
writes three jobs.

With those, it reconciles: the six terms sum to -36.58 kcal/mol against a
supermolecular -36.62. **The 0.05 residual is nameable, not slop** -- it is
exactly the gap between the LED's own total and `FINAL SINGLE POINT ENERGY`,
i.e. how DLPNO splits the (T) correction. It is reported rather than hidden.

**`$new_job` does NOT generalise from delta-SCF.** Inside a compound job
ORCA restarts from the previous job's orbitals, which is valid for
delta-SCF (same geometry, different charges) and fatal here, because a
fragment has fewer atoms:

    Error: Input geometry does not match current geometry
    ORCA finished by error termination in GUESS       -- exit 55, 1 energy of 3

`PModel` on the fragment blocks fixes it. **`NOAUTOSTART` looks like the fix
and is not** -- it governs picking up a `.gbw` left on disk, not the restart
from the preceding block, and the run failed identically with it in place.

Two measurement traps from the cost estimate, both paid for once:

- **Residual disk is not peak disk, by a factor of 575.** benzene-water
  leaves 3.3 MB behind and used **1899 MB while running**. The first
  estimator was anchored on residual and under-predicted the thing that
  fills a drive by three orders of magnitude. Sample during the run.
- **The textbook cc-pVDZ contraction is wrong for this job.** 14 per
  first-row atom predicts 57 functions for BH3-CO; ORCA reports 75. Solving
  the two measured totals gives 20 and 5, confirmed against a third job it
  was not fitted to (BH3 alone: predicted 35, reported 35).

#### The two-point cost fit was an artefact. Six points, and it changed shape

The estimator was first fitted on BH3-CO and benzene-water, giving an
exponent of 4.20. **benzene-water is aromatic**, so the fit absorbed an
aromatic penalty into the exponent and then charged it to everything. On a
saturated pentane dimer it predicted 9960 s against a measured 1291 --
**7.7x too high**, the difference between "start it" and "do not bother".

Six compound jobs, one harness, peak disk sampled DURING the run:

    system            atoms  functions  aromatic   wall   peak scratch
    water dimer          6       60        0        15 s      35 MB
    BH3-CO               6       75        0        23 s     103 MB
    methanol dimer      12      120        0        48 s     220 MB
    benzene...H2O       15      180        1       644 s    1852 MB
    benzene dimer       24      300        2      2648 s    5564 MB
    pentane dimer       34      320        0      1291 s    2872 MB

    time    = 2.0064e-04 * f^2.69     worst residual x1.60
    scratch = 1.5004e-03 * f^2.51     worst residual x1.37

**The noise floor is x1.2** -- the same benzene fragment measured 280 s in
one run and 342 s in another -- so the fit is close to as good as this gets
without controlling the machine. Do not assert more tightly than that.

Three things that each produced a wrong exponent before being noticed:

- **A complex costs less than a monomer of the same size.** Half its
  electron pairs are inter-fragment and long-range, so DLPNO screens them
  out: methanol MONOMER at 60 functions takes 7 s where the water DIMER at
  60 takes 4.6. Fitting both populations together gave 1.72, which then
  under-predicted 320 functions sevenfold. Fit on complexes only.
- **Aromaticity is a x2.9 penalty and is NOT a size effect.** The methanol
  dimer has 28 correlated electrons and takes 23 s; benzene has 30 and takes
  280. Same electron count, twelve times the cost -- delocalisation defeats
  DLPNO's locality screening. It does **not** compound with ring count
  (1 ring x2.82, 2 rings x2.94), so it is a flat multiplier; a per-ring
  model predicted 7246 s for the benzene dimer against a measured 2648.
- **The fragment jobs are not a fixed fraction.** A x1.5 multiplier from
  BH3-CO (23 s compound vs 15 s complex) is wrong at the other end, where
  benzene-water is 644 vs 595 -- x1.08. Fit whole compound jobs directly.

With time no longer over-predicted, **scratch became the binding
constraint** at the top end: a 1200-function job is 10.7 hours (survivable)
and 78 GB (not, on most machines), so the refusal now triggers on either.

One more thing this work paid for, and it was a GUARD that found it rather
than review: `tests/test_layering.py` forbids a `ui/` module importing
RDKit, and the pre-launch cost dialog did exactly that to count fragments
with `Chem.GetMolFrags`. It reads as obviously fine in isolation, which is
the point -- the count now comes from `estimate_led_cost_for` in the chem
layer and the UI imports nothing chemical.

#### `EmbedMolecule` does NOT separate disconnected fragments

Found by running the app, after every test was green, and it is the best
argument in this file for doing live checks at all.

Building an ammonia/borane pair the way a user would -- draw two species,
generate 3D -- put the **N and the B 0.15 A apart**, interpenetrating.
There are no constraints between disconnected fragments, so the embedder
packs them at the origin. ORCA then ran the job perfectly happily and the
panel reported:

    Interaction energy (LED): 40619.295952 kcal/mol
    Electrostatics:            8251.870486 kcal/mol     (should be negative)

**Correct arithmetic, meaningless answer, presented as a plain number** --
the worst combination, and nothing anywhere said so. The parser was fine:
the same pair at a real geometry (B-N 1.66 A) gives -52.76 kcal/mol with a
0.006 residual, matching the offline run to every digit.

Two guards now, and the split matters. `estimate_led_cost_for` measures the
closest inter-fragment approach and REFUSES below 0.7 A (shorter than any
real bond -- H-H is 0.74) or beyond 8 A, before any compute. `parse_led`
adds a limitation past 300 kcal/mol, since a bad geometry is the common
cause of an impossible number but not the only one.

Anything else that consumes a drawn multi-fragment structure has the same
exposure. The embedder will not tell you.

### An engine and its own data table have to be run against each other

The Lewis adduct work shipped a Drago-Wayland parameter table and an
acceptor-detection engine that were each individually tested and green.
Run together, **the engine refused 14 of the 24 acids in its own table** --
every alcohol and phenol, pyrrole, chloroform. Nothing but running the two
against each other revealed it, and the fix was three new acceptor rules,
not a tweak.

Iodine and benzene were among the refused, and both are pairs in the
table's *own validation set* — so the engine could not reproduce the data
that justified shipping the table.

`test_every_acid_in_the_shipped_table_passes_the_acceptor_gate` is the
guard. Any future data table should get the equivalent.

The most useful of the three rules is worth knowing on its own: **a
hydrogen bond and a halogen bond are the same mechanism**, donation into
the sigma* of a polarised single bond, differing only in the heavy atom.
They share `LOW_LYING_SIGMA_STAR` because that is accurate, not
convenient. A consequence: alcohols and amines come out AMBIPHILIC, since
the oxygen donates its lone pairs while its O-H accepts. Water is the
textbook case, and several tests had to be updated to say `ambiphilic`
where they had said `donor` — the behaviour change was correct.

### The two orbital measures disagree on the motivating case

Measured on real ORCA delta-SCF runs of the pair the whole feature exists
for:

| | frontier gap | HSAB \|Δη\| |
| --- | --- | --- |
| BH₃ + CO | **8.13 eV** | 1.63 eV |
| BF₃ + CO | 10.90 eV | **0.89 eV** |

Borane binds CO strongly enough to isolate the adduct; BF₃ barely binds it.
The frontier gap says so. **The |Δη| proxy says the opposite**, because
CO's computed hardness (8.40) lands near BF₃'s (9.29) rather than
reflecting the softness the qualitative argument gives it — a single
number on the η scale is not Pearson's classification.

This is reported, not resolved, and it is the strongest justification for
the no-combined-score design: an average would have split the difference
on a case where one line is simply right.
`test_the_two_orbital_lines_disagree_on_carbon_monoxide` asserts it on
purpose.

Two measurement traps from the same work, both already paid for once:

- **A fixture labelled "verbatim from a real run" had energies typed from
  memory.** The assertions used `abs=0.01` tolerances, which were loose enough
  to hide it — so the arithmetic was being checked against itself rather than
  against the run. Copy the numbers, and assert tightly enough that a wrong
  fixture cannot pass.
- **`X = '' or (...)` mutates nothing**, since the empty string is falsy and
  the original is returned. Two mutations written that way reported a
  confident SURVIVED for changes never applied. A mutation script must verify
  its edit changed behaviour, not merely that the pattern matched.
- **A restored file can still run as the MUTATED one, from stale bytecode.**
  Python validates a `.pyc` against the source's mtime and size, both of
  which a write-mutate-restore cycle can leave unchanged within one mtime
  tick. Seen live: a restored `chem/lewis.py` read `0` on disk and in
  `inspect.getsource`, while the imported module held the mutated `1` — the
  test "failed after restore" and the source was innocent. Any mutation
  script should `rm -rf` the `__pycache__` directories between arms, or run
  with `PYTHONDONTWRITEBYTECODE=1`, and a surprising post-restore result
  should be re-checked with the cache cleared before it is believed.
- **A surviving mutation found a real sign error nobody would have read.**
  The Drago W term is ADDED (`−ΔH = E_A·E_B + C_A·C_B + W`) and was written
  subtracted. Every test passed, because every acid the tests touch has
  `W = 0` — only two entries in the whole table have one. Coverage of a
  parameter's *common* value is not coverage of the parameter.

### Alex has the paywalled papers. Ask before hedging around one.

Three primary sources that this work had been treating as unobtainable are
on disk at `D:\Xaero Stuff\Documents\Sci Downloads\`: Drago & Wayland 1965,
Parr & Pearson 1983, Pearson 1988, and **Mayo, Olafson & Goddard 1990** (the
DREIDING paper — this file and three others had asserted for months that
Dreiding was simply unavailable, which was the absence of a finding rather
than one; see `docs/DREIDING_ASSESSMENT.md`, and note the PDF's text layer
corrupts the atom-type labels `C_3`/`C_R` that the parameters key on).
**Reading them changed real claims**,
so when a source is needed, ask rather than write "paywalled, orderings
pinned instead".

There is no PDF text extractor in the project venv and `pdftoppm` is not
installed, so `Read` on a PDF fails. `uv pip install --system pymupdf` and
`fitz` works.

What the papers changed:

- **The 1965 E/C parameters are on a DIFFERENT SCALE from the shipped ones**
  and must not be mixed. That paper normalises iodine to E_A = C_A = 1.000
  ("relative to E_A and C_A of iodine being 1"); the modern compilation puts
  iodine at 0.50 and 2.0. Its *observed enthalpies* are scale-free, and are
  now a second, independent validation set — 12 values across three acid
  series.
- **The model's best test is one it fails.** The paper measures F-strain in
  trimethylborane's amine adducts: 8.2 kcal/mol for trimethylamine, 1.5 for
  dimethylamine, nothing for the two smaller ones. An E/C equation has no
  steric term, so it *must* over-predict exactly those two — and does, by
  6.1 and 1.1. A table that fitted all four would mean the parameters had
  absorbed a steric effect they are not supposed to contain.
- **Every hardness value quoted from memory was right**, and none of them
  should have been quoted from memory. η(H₂O)=9.5, η(NH₃)=8.2, η(H₂S)=6.2,
  η(PH₃)=6.0, all confirmed in Pearson 1988 Table II. They are asserted now.
- **A claim in this file's own tests was wrong.** ΔSCF's electron-affinity
  error is NOT one-directional. ΔSCF returns −3.6 to −3.8 eV for all four
  molecules, whose true affinities span −1.9 to −6.4: the unbound anion
  barely knows which molecule it is on. That *compresses* the hardness
  scale, and the NH₃/PH₃ ordering it gets right survives by **0.19 eV**
  where experiment separates them by 2.2. The ordering is correct; the
  margin is not something to lean on.
- **Pearson's own rows round to ±0.1** — H₂S's (I−A)/2 gives 6.3 against a
  printed η of 6.2 — so a self-consistency check on transcription needs
  `abs=0.15`, not `0.05`.

Gutmann donor/acceptor numbers were assessed and **not shipped**. The
accessible source (Frontiers in Chemistry 2022, 10.3389/fchem.2022.861379)
tabulates ionic liquids and deep eutectic solvents rather than the classical
molecular table, and reports its own acceptor-number model failing outright
("no correlation could be found"), concluding it supports "qualitative and
relative criteria but not an absolute and quantitative model". Note the
donor number is *defined* as −ΔH against SbCl₅, which is already in the
Drago table — so that line is partly available already.
