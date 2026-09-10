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

#### AND THE SECOND INSTANCE COST A WHOLE BENCHMARK, not one descriptor

**AND A SECOND CHANNEL DEFAULT, IN THE SAME SESSION AND WORSE.** That
session's write-up said the Windows `libomp140.x86_64.dll` defect was in
**conda-forge's** pytorch. It is not: read out of `conda-meta`, `pytorch`
and `libtorch` come from `https://repo.anaconda.com/pkgs/main/win-64`, and
they are 4 of the 227 packages in that environment that do. The claim was
made because the environment RECIPE says `-c conda-forge` and never checked
what the solver did -- a field nobody could check, believed and then written
down, which is this file's own most-repeated failure. **It was caught only
because filing the bug forced a verification**, one command short of
reporting it to the wrong maintainers.

The rule: a package's CHANNEL is a fact about the solve, not about the
command that started it. `conda-meta/<pkg>.json` carries `channel` and `url`
and is the only thing that answers it.

`openmmforcefields`'s `GAFFTemplateGenerator(molecules=...)` picks **the
newest GAFF it can find**, which in the free-energy environment is
`gaff-2.2.20`. FreeSolv's reference column is labelled *"Mobley group
calculated value (GAFF)"* in the database's own header and dates from 2017.
So `benchmarks/free_energy/` spent its whole life comparing **GAFF2 answers
against a GAFF1 reference**, and nothing in the stored result said which
force field had run.

Ammonia is where the two part company hardest, because GAFF2 gives it an
atom type of its own -- `n9`, described in `gaff2.dat` as literally "NH3":

    gaff-1.81    N sigma 0.32500 nm   epsilon 0.71128 kJ/mol   (n3)
    gaff-2.2.20  N sigma 0.40447 nm   epsilon 0.03975 kJ/mol   (n9)

    ammonia, 40 iterations, nothing else varied
      gaff-2.2.20   -0.672        gaff-1.81   -4.127
      FreeSolv reference -4.02    experiment  -4.29

**IT EXPLAINS EVERY ROW, WHICH IS WHAT MAKES IT THE CAUSE RATHER THAN A
CANDIDATE.** GAFF2 deepens the aliphatic hydrogen well by 32.5%, so methane
and ethane come out MORE soluble than the reference -- and ethane's shift is
1.41x methane's against a 6:4 hydrogen ratio. It makes methanol's oxygen 56%
shallower, so that row moves the OTHER way. Hydrogen sulfide's two changes
oppose each other and it barely moves. A hypothesis that explains the one
row it was invented for is worth little; this one predicts the sign of all
five from the parameters alone.

**THREE HYPOTHESES WERE REFUTED BEFORE THIS, AND ONE OF THEM WAS TESTED ON
THE MOLECULE LEAST ABLE TO SHOW IT.** "The electrostatic lambda schedule is
too coarse" was measured on METHANE, whose largest partial charge is 0.108 e
against ammonia's 1.010 -- so that arm could not have detected a coarse
ELECTROSTATIC schedule however it came out. Same lesson as the assembly
corpus blind to a transposed matrix, and as the two degenerate published
formulations: **a fixture is degenerate or not with respect to a specific
defect.**

The rule this leaves is the one the entry above already states, one level
up: a library default is a CHOICE somebody made, and when the thing being
reproduced was computed with a different one, the default is not a detail.
**Pin it, and record it in the result** -- `hydration.py` does both now, and
the recording is what would have caught this on day one.

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
