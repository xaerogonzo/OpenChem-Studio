@BASIC_INSTRUCTIONS.md

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
    {"do": "dock_run"}                       the REAL button, real Vina
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
    {"do": "screen_run",  "receptor": 0}      the REAL Run button, and the
                                              PREP DICT the service got
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

## Lessons (moved out of this file)

These were appended here after individual investigations. They live
in [`docs/LESSONS.md`](docs/LESSONS.md) and are **not** loaded on every
message — this index is. **If a title below names what you are
about to touch, read that section before you start.** Headings there
are verbatim, so grep the file for the line.

- THE DRIVEN CHECK CAN ASSERT NOW, AND THREE EYE-ONLY DEFECTS BECAME TESTS
- A RATCHET IS NOT A MIGRATION, AND CALLING THIS ONE A MIGRATION WAS WRONG
- THE HELP CONTRACT: a tooltip is a RENDERING, not the thing itself
- BATCH WAS A SECOND IMPLEMENTATION OF WHAT PROPERTIES ALREADY DID
- THE VIEWER AND THE DOCKING WERE SHOWING DIFFERENT CHAINS
- THE ALIGNMENT COULD NOT MOVE A TORSION, AND THE RMSD COULD NOT SAY SO
- POPPING A VIEW OUT: the widget MOVES, and that was measured first
- A HORIZONTAL ROW'S MINIMUM IS THE SUM, and it set the whole window's
- A PANEL THAT LEAKS ITSELF AND THEN POLLS FOREVER
- OPEN BABEL HAS NO DATA FILES ON WINDOWS -- THE PLATFORM THIS SHIPS ON
- THE LINUX JOB COULD NOT NAME ITS OWN VICTIM, AND THE DATA WAS ALREADY THERE
- THE LINUX SUITE CRASHES ON 4 OF 6 COMMITS, AND THE INSTRUMENT NEEDED FIXING TWICE
- TEN CENSUS-NAMED CRASHES, TWO FILES, AND THE COUNTER-EXAMPLE CAME ON A BYTE-IDENTICAL TREE
- A RED SUITE SILENTLY DISABLES EVERY GATE BEHIND IT
- A WINDOWS RUNNER HANDS A BASH SCRIPT TO POWERSHELL
- A FORMULATION IS NOT A MOLECULE, AND THE COMPONENTS ARE EACH REFUSED
- A POWDER PATTERN'S POSITIONS SHIP AND ITS INTENSITIES ARE REFUSED
- A DECISION WAS REVERSED ON PRODUCT GROUNDS, AND THE RECORD SAYS SO
- GELL-MANN--NISHIJIMA IS THE CHECKSUM ON A HAND-ENTERED TABLE
- THE PDG SUPPLIES ITS OWN COUNTEREXAMPLE, WHICH IS THE WHOLE DESIGN
- A NEUTRAL LIGHT MESON IS A SUPERPOSITION, AND THE SOURCE PRINTS IT
- THE PDG WAS FETCHED, READ AS A PDF, AND CROSS-CHECKED
- THE DIALOG OPENED ON A DELTA++ AND EVERY TEST PASSED
- A DRIVE STEP THAT DRIVES THE CONTROLS, NOT THE FUNCTION BEHIND THEM
- FILE DIALOGS REMEMBER WHERE YOU WERE, AND `QFileDialog` IS PATCHABLE
- THE RECEPTOR WAS PREPARED AT pH 7.4 AND THE LIGAND AT NEUTRAL
- THE ANCHOR RESIDUE IS NUMBERED DIFFERENTLY IN THE TWO STRUCTURES
- THE BOX WAS NOT THE PROBLEM, AND THE FIRST MEASUREMENT SAID IT WAS
- THE STORED RESULT WAS A PLAUSIBLE-LOOKING LIE
- CASF-2016 SPLITS THE ANSWER, AND IT IS THE ANSWER TO THE REPORT
- EXHAUSTIVENESS 25, AND THE NUMBER WAS REVISED ON READING THE SOURCE
- `flow_row` IS NOT A FREE SUBSTITUTION FOR A TWO-CHILD `QHBoxLayout`
- A REVIEW'S CITATION DID NOT RESOLVE TWICE, AND I CALLED IT FABRICATED
- `Read` CANNOT OPEN A PDF HERE, AND THE THROWAWAY VENV IS THE ANSWER
- A SCORE IS ONE DRAW, AND THE PANEL PRINTED IT TO TWO DECIMAL PLACES
- MASTER CRASHES IN THE SAME TWO TESTS, AND THAT IS THE ATTRIBUTION
- A SECOND SCORE ON A POSE, AND THREE WAYS TO SHIP A WRONG NUMBER
- A P-VALUE LOOKED AT REPEATEDLY IS NOT A P-VALUE, AND MINE CROSSED 0.05 AND CAME BACK
- REPRODUCIBLE SEARCH PLUS NO CORRELATION IS THE STRONGEST NULL AVAILABLE
- WIDENING A CORPUS AFTER A MARGINAL RESULT IS CORRECT, AND MUST BE PRE-COMMITTED
- A SCREEN COULD NOT BE PINNED EVEN IN PRINCIPLE, WHILE A SINGLE DOCK COULD
- A REFUSAL THAT NAMED ITS OWN UNBLOCKING CONDITION, UNCHECKED FOR TEN DAYS
- THE RANKING CORPUS WIDENED OFF THE GPCRs, AND THE ENDPOINT EXCLUDED TWO CLASSES
- A CHART IS DECLARED, AND THE MERGE KEEPS WHAT EACH PRODUCER DECLARED
- THE ION IS A COMPOSITION, AND POTASSIUM IS WHY
- SIX DEFECTS THE DRIVEN APP FOUND WITH 1006 TESTS GREEN
- A GUARD RED FOR A REAL REASON: a category holding one calculator
- THE ISOTOPE FOLD WAS EXPONENTIAL IN THE ATOM COUNT
- "EXACT" WAS THE ARITHMETIC AND THE CONTRACT SAID FINE STRUCTURE
- A UNIT IN BOTH FIELDS AND A UNIT IN NEITHER, AND THEY PARTITIONED PERFECTLY
- THE POWDER PATTERN REACHED THE CHART CHANNEL, AND TWO COMMENTS WERE LYING
- A SECOND CHART KIND, AND ONE RENDERER FOR CURVES
- A DEPICTION, FROM THE LAYER TYPE THAT ALREADY EXISTED
- THREE GUARDS I WROTE MATCHED THE PROSE EXPLAINING THEIR OWN RULE
- A HELP-CONTRACT FIXTURE THAT COULD NOT BE BUILT WAS SKIPPING 5 CONTROLS
- A `"choice"` PARAMETER STORED THE ENGLISH ON THE SCREEN, IN THE CACHE KEY
- A HEADER OVERFLOWS; A CELL ELIDES. AND THE ORACLE SEES NEITHER
- `batch_service` READS AN EMPTY SCOPE AS "EVERYTHING GIVEN"
- TESTING A HELPER IS NOT TESTING THE WIRING -- TWICE MORE, BOTH MINE
- A COMMITTED DRIVE SCRIPT DID NOT CONSTRUCT ITS OWN STATE
- A BLANK LINE IN A REPORT IS A ROW WITH NO VALUE
- MEASURE THE POPULATION BEFORE DESIGNING FOR IT
- A LIMIT IS A NUMBER PLUS WHAT IT IS A LIMIT ON, AND FOUR WAYS THAT GOES WRONG
- THE RESULTS LIST FOLLOWED WHICHEVER CALCULATION FINISHED FIRST
- A READER'S POSITION HAD NEVER HAD TO SURVIVE ANYTHING
- THE READER CONTRACT WAS FOUR NAMES AND THE READER READ NINE
- HALF THE APPLICATION'S OUTPUT COULD NOT REACH THE READER
- A SUMMARY WITH NO WAY BACK TO THE RESULT IS A DEAD END
- TWO SEARCHES, AND ONE BOX OVER BOTH CANNOT SAY WHAT IT MATCHED
- A SHAPE-VALUED RESULT WAS A DIFFERENT-SHAPED, MODAL WINDOW
- A READER THAT FOLLOWS THE SELECTION CANNOT BE A DIALOG
- RESULTS IS A PANEL NOW, AND ONE PANEL AT A TIME IS WHY THE POP-OUT IS LOAD-BEARING
- ONE READER, AND "DETAILS..." REACHES IT WHEREVER IT IS
- THE LAUNCHER HAS TO SAY WHETHER THERE IS ANYTHING TO READ
- EMPTYING THE LAUNCHER IS HOW YOU FIND OUT WHAT ONLY THE LAUNCHER SAID
- THE 41 DESCRIPTORS LEAVE, AND EVERY CLAIM THEY CARRIED ALONE GOES RED
- A CONTRACT FOLLOWS THE VALUE, NOT THE WIDGET
- Running the tests
- RESONANCE: four things measured before the Lewis diagram was built
- The naming benchmark
- Ketcher CAN report atom AND bond selection, with one trap
- SHAPE-VALUED RESULTS DRAW THEMSELVES, and what that took to make honest
- The bond and molecule reports, and what generalising cost
- A new panel needs a help topic, and nothing was checking
- A DOC GUARD THAT CHECKS CITATIONS CANNOT CHECK CLAIMS
- A blocklist of category NAMES rots; a declared capability does not
- The presentation layer, and four things measured while fixing it
- A UI MUST NOT INFER SCIENTIFIC MEANING FROM A DATASET'S SHAPE
- SOLUBILITY: an uncapped model, a 1000x review, and two defects only the screen showed
- SOURCES: a provenance registry, and two traps in building one
- A PANEL THAT DREW TWO THIRDS OF AN ANSWER AND SAID NOTHING
- THE CRC OVERTURNED THE REASON IT WAS OPENED
- A BETTER LAYOUT ENGINE THAT IS WORSE ON THE REPORTED MOLECULE
- THE MUTATION STEP EARNED ITS KEEP SEVEN TIMES IN ONE BRANCH
- AND TWO DEFECTS ONLY THE MAGNIFIED SHOT FOUND
- NUCLIDES: what the isotope and decay work cost
- FIVE THINGS TO KEEP DISTINCT IN A SCIENTIFIC CALCULATION
- SHIPPED IS NOT REACHABLE, AND THE GUARD FOR IT HAD THREE BLIND SPOTS
- "25 COLLAPSIBLE CATEGORIES" WAS 20, AND MEASURING IT FOUND A 21st
- SHIPPED IS NOT REACHABLE, AND FOUR MODULES PROVED IT
- `variants[0]` WAS NOT A RANKING, AND THE ORDER CAME FROM THE HASH SEED
- A CORRECT NUMBER THAT READS AS A WRONG ONE
- A REFUSAL IS NOT A FAULT, AND THE STYLE'S OWN COMMENT SAID SO
- GASTEIGER'S OWN TABLE 3 IS AN ORACLE, AND IT AGREES
- A ROUND TRIP can pass without exercising what it is named for
- A docking A/B needs a pinned seed AND its own noise floor
- A whole CORPUS can be degenerate, and then size proves nothing
- Open Babel reads mmCIF elements CASE-SENSITIVELY, and the archive is uppercase
- A threshold fitted to a BIMODAL molecule is not validated
- Two empirical fits can CROSS, so one test point proves nothing
- Normalise the DRAWING, do not fork the vendor
- A threshold with two measured bounds is not a taste question
- A library DEFAULT can be a different quantity, not a tuning knob
- Bound the grid, not the resolution
- A derivative can be self-consistent, symmetric, and wrong
- A conformer search result is part of the question, not the setup
- Koopmans hardness is wrong for the pair people actually use it on
- ORCA ABORTS AT STARTUP IF ITS OWN PATH USES FORWARD SLASHES
- A KILLED PROCESS STILL OWNS ITS WORKING DIRECTORY, and cleanup was silent about it
- A gbw remembers where it was born, and orca_plot goes there
- ORCA's LED summary block does not mean what it looks like it means
- An engine and its own data table have to be run against each other
- The two orbital measures disagree on the motivating case
- Alex has the paywalled papers. Ask before hedging around one.

## Verification standard

This project's convention, established across many sessions: **claims are
measured, not asserted.** Before shipping a formula, a threshold, a parser
regex or a model, verify it against a primary source or a real run and record
what was checked. Several things were deliberately NOT shipped because they
could not be validated (Miller polarizability, HLB, TSEI) — that is a normal
outcome here, not a failure.

Comments explain **why**, especially where something is non-obvious or was got
wrong once. A comment restating the code is noise.
