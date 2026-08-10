# Navigation audit — every door into the application

Written 2026-08-10, after two reported regressions turned out to be
navigation problems wearing a bug's clothes:

    "major problems with all the calculators"
    "the periodic table no longer shows all the atom drawing,
     it's reverted to vanilla"

Neither was a chemistry fault. The first was the Properties panel
discarding 40% of what the calculators computed; the second was two
periodic tables, one of which is Ketcher's. Both are fixed. This document
is the sweep that followed, because the same shape almost certainly
repeats elsewhere and finding it by waiting for a report is expensive.

**Everything here is counted, not estimated.** Where a number is
uncomfortable it is still the number.

## What existed when this was written

The starting state, kept as the baseline every finding below is
measured against. Where a number moved, the finding says so.

| | count |
| --- | --- |
| menu actions | 25 (26 now: Virtual Screening gained one) |
| calculators | 58, in 26 categories (18 now) |
| panel modules | 12 |
| dialog modules | 16 |

## Finding 1 — SOLVED: 26 sections for 49 buttons, now 18

The Properties panel builds one collapsible section per calculator
*category*. Measured over the live registry:

    26 sections, holding 49 buttons between them

    0 calculators   2 sections
    1 calculator   11 sections   <- 42% of the panel
    2 calculators   5 sections
    3 calculators   5 sections
    4 calculators   2 sections
    5 calculators   1 section

**Eleven sections hold exactly one button**: alignment, dynamics,
identity, interactions, logp, markush, molar_refractivity, nmr,
regulatory, stereochemistry, structure. Two hold none at all.

So finding a calculator means scrolling twenty-six headings, most of
which conceal a single item. The category vocabulary is a free string by
design (`CalculatorDefinition.category`, deliberately open so a new
registration needs no code change) and nothing has ever pushed back on
adding one — the same structural reason the `inapplicable_calculators`
blocklist rotted.

This was the strongest single candidate for the "labyrinth" complaint.

**MERGED: 26 categories -> 18, singletons 11 -> 1.**

    1 button    11 sections  ->   1   (nmr, declared)
    2 buttons    5 sections  ->   6
    3 buttons    5 sections  ->   3
    4 buttons    2 sections  ->   3
    5 buttons    1 section   ->   3

`nmr` stays a singleton on purpose: `nmr_database` has no registry
sibling (the ORCA NMR jobs are ServiceExecution, in their own panel), and
filing a spectroscopic measurement under a structural heading to flatten
a count would be worse than the count.
`test_no_category_holds_a_single_calculator` asserts the exception BY
NAME, and a companion test fails if it ever stops being true.

**"A registration change, not a code one" was WRONG**, and this sentence
is kept as the correction. Three things move together, in three
different files, and nothing links them:

- `CalculatorDefinition.category`, which places the BUTTON;
- the `category=` on the `ReportResult`/`AlertResult` the calculator
  RETURNS, which places its ANSWER (the panel files those by
  `report.category`, not by the definition's) -- so moving one without
  the other puts a calculator's button in one section and its result in
  another, silently;
- the descriptor table's own category, which is a separate list again.
  Missing it shipped a section headed **"Logp"** to the running app while
  every test passed, because the first guard read only the registry.

`test_a_calculators_result_lands_in_its_own_section` closes the second by
running each calculator and comparing the two values; it compares 19 of
them and asserts a floor, so it cannot silently compare nothing.

**Two heading defects only the running app showed.** The section header
is a `QToolButton`, which treats `&` as a mnemonic and ELIDES when long:
"Lipophilicity & Refractivity" rendered as "Lipophilicity  Refractivity"
with the ampersand simply gone, and "Identity & Composition" as
"Identity ...mposition". Measured ceiling at the panel's real width is
**21 characters**, and both are now guarded.

## Finding 2 — SOLVED: a category name is not a heading, and there were two fallbacks

`_CATEGORY_LABELS` in
[property_panel.py](../src/openchem/ui/panels/property_panel.py) maps a
category id to a display name, and anything missing falls back to
`category.title()`. That fallback has already shipped a heading nobody
chose: NMR rendered as "Nmr" until a documentation sweep caught it.

The map is hand-maintained against an open vocabulary, so it is a
blocklist by another name. A registration with a new category gets a
title-cased heading and nothing fails.

**FOUR SOURCES CAN CREATE A SECTION, and the guard read one, then two.**
`_section_for` is reached from the calculator registry, from both
descriptor spec tables, from a calculator's own result, and from the
alerts a PROVIDER publishes -- the last being literals scattered through
`descriptor_providers.py` that no list enumerates. Measured across all
four: **19 categories reachable, 0 without a chosen heading.** So the
shipped app is clean, but it was clean by coincidence for the provider
alerts, and the guard now derives them by RUNNING `compute_alerts`.

**THERE WERE TWO FALLBACKS AND THEY DISAGREED.** The heading fell back to
`category.replace("_", " ").title()`; `as_text()`, which builds the
"Copy all" output, fell back to `category.title()`. An unlabelled
`medicinal_chemistry` would read "Medicinal Chemistry" on screen and copy
as "Medicinal_Chemistry" -- two names for one section, in one panel.
Latent rather than shipped, since no category reaches either fallback
today, which is exactly why a guard is worth more than noticing it.
`_category_label` is the one function that decides now.

**The plugin exposure is theoretical, and measured to be so.** No bundled
plugin registers a calculator or a category at all. The fallback stays
for one that might, and it reads `my_tools` as "My Tools" correctly; what
it cannot do is acronyms, and `nmr` becoming "Nmr" is how this finding
was noticed in the first place. A plugin wanting an acronym has no way to
say so -- declared here rather than solved, because building an API for a
case with no instances is the premature generalisation this codebase has
declined before.

## Finding 3 — SOLVED: seven names did not fit, and the wrapper was why

`_ElidingPushButton` elides rather than clipping, which was the right fix
for the layout. It means these are read truncated:

    34  Accessible Surface Area (per atom)
    34  Interaction energy breakdown (LED)
    34  NMR Shifts (experimental database)
    31  Hardness / Softness (delta-SCF)
    31  Molar Refractivity Contribution
    29  ADMET (hERG, CYP, Ames, ADME)
    29  H-Bond Donors/Acceptors vs pH
    29  Partial Charge (pH-dependent)

**THAT COUNT WAS WRONG AND SO WAS ITS DIAGNOSIS.** It counted characters
across all 58 display names, including the ORCA jobs, which are
ServiceExecution and have no button in the panel at all. Measured in the
running app against real pixels:

    7 of 49 buttons elide, at 192 px of available label width

    +37 px  NMR Shifts (experimental database)
    +32 px  Accessible Surface Area (per atom)
    +31 px  ADMET (hERG, CYP, Ames, ADME)
    +23 px  H-Bond Donors/Acceptors vs pH
    +13 px  Molar Refractivity Contribution
    +12 px  Partial Charge (pH-dependent)
    +11 px  Molecular Dynamics (vacuum)      <- the audit missed this one

**The names were barely the problem. The WRAPPER was.** Every button read
`Open {name}...`, and `Open ` alone is ~32 px of a 192 px button, spent
identically forty-nine times. Removing it took the count from **7 to 1**
without touching a single name. One rename finished it — "NMR Shifts
(experimental database)" to "NMR Shifts (experimental)", 5 px over — for
**0 of 49 eliding**.

`_MAX_CALCULATOR_NAME` guards it at 34 characters, which is the widest
name measured to fit; "Accessible Surface Area (per atom)..." fits by
exactly nothing, needing all 192 px. It is kept at that length rather
than mangled: it is the standard term, and eliding is graceful because
the tooltip carries the full name. A character count is a proxy for a
pixel width and an imperfect one in a proportional font — a pixel
assertion is deliberately avoided, because CI is Linux with different
fonts and a guard that fails only there gets deleted rather than fixed.

**THE "CARRYING THEIR CATEGORY" SUGGESTION IS REJECTED**, and this is the
reason rather than an omission. Under a heading that says Surface Area,
"Molecular (3D)" and "Accessible (per atom)" would read beautifully — on
the button. But `display_name` also IS the palette entry, where there is
no heading for context, and finding 4 was just spent making that search
work. "Accessible (per atom)" is meaningless in a search box. The
duplication is the price of one string serving two places, and the button
is the one with context to spare.

**Two things only looking at it showed.** The trailing `...` was assumed
to be lying on the calculators that run immediately — it is not; all 49
declare parameters, so every one really does open a dialog, and a
conditional ellipsis would have been a branch that never runs. And
"Substance & Bonding" rendered as "Substance  Bonding": a `QPushButton`
eats `&` as a mnemonic, the same bug the section headings had. Headings
were reworded because those are our own words; a calculator name is
chemistry vocabulary, so `_mnemonic_safe` escapes it instead.

**FOUR GUARDS IN A ROW HERE PASSED WHILE TESTING NOTHING**, which is
worth more than the fix. Mutation testing caught every one:

1. a wrapper test that built its own string and asserted THAT had no
   `Open ` prefix, so it tested the test;
2. a relayout test asserting the label was unchanged after two resizes,
   which is true either way (the loop wastes work, it does not change
   the answer);
3. the same test counting `setText` calls but resizing to the SAME size
   twice, where Qt sends no `resizeEvent`;
4. the same again at two different sizes, on a widget that was NEVER
   SHOWN. `resize()` on a hidden widget delivers no `resizeEvent` at
   all. Measured: 0 events hidden, 2 shown.

The last is the exact sibling of this codebase's `repaint()` lesson, in a
different Qt event. **A widget that was never shown runs almost none of
its own code**, and a test that skips `show()` measures construction
while claiming to measure behaviour.

## Finding 4 — SOLVED: one door, and the wrong word finds nothing

**A crystal can only arrive through `File ▸ Import Crystal Structure...`**
and it must already be a CIF. This is the honest answer to "how do I turn
the SMILES for table salt into a crystallography structure": there is no
such path, and there cannot be a good one — going from a molecular graph
to a lattice is crystal-structure prediction, an open research problem,
not a missing menu item. What is missing is anywhere that *says* so.
Nothing in the app connects "I have a SMILES" to "you need a CIF, and
here is where they come from".

**PART OF THE ORIGINAL FINDING WAS WRONG AND IS CORRECTED HERE.** It
said the Receptor Library and batch analysis each had "exactly one entry
point". Measured against the live palette, both are findable: the
Receptor Library is a File menu item, and the Batch panel is on the rail.
The palette indexes panels, calculators and the menu bar, so anything in
one of those has a second door for free -- a mitigation the audit failed
to weigh.

**Virtual Screening really did have one door**: a button inside the Batch
panel, in no menu and therefore in no palette. Searching "screening" or
"virtual" returned NOTHING. It has a Tools entry now; the button stays,
because that is where somebody with a table in front of them reaches.

### The real gap was VOCABULARY, and it was worse than a missing door

The palette searched display names only. Measured against its own ranker:

    cif        -> "Scientific Limitations", "Open Project Plugins Folder"
    pdb        -> "Periodic Table..."
    toxicity   -> "Toggle Explicit Hydrogens"
    sdf xyz mmcif protein lattice "unit cell" energy spectrum -> NOTHING

The first three are the subsequence tier answering with confident
nonsense, which is **worse than an empty list**: it looks like the app
considered the question. Someone arriving with a `.cif` file was told
about Scientific Limitations.

`Command.keywords` fixes it from two sources, only one hand-written:

- **Calculator `tags`, which already existed and were being ignored** --
  45 of 58 carried them, 94 distinct, and the palette read none. Derived
  from the registry, so a new calculator is searchable by its tags the
  moment it registers. The other 5 registry calculators had NO tags at
  all, `admet_ml` among them, which is why "toxicity" found nothing real;
  they are tagged now and a derived guard fails if any goes untagged.
- **A small map for menu actions**, because a `QAction` has nowhere to
  put one. Keyed on the label, which is the shape that rots, so
  `test_every_menu_keyword_names_a_live_action` fails naming the stale
  key.

A keyword never outranks a label match -- "Batch" the panel still beats a
calculator merely tagged `batch` -- but it does outrank the subsequence
tier, which is what demotes the noise. After:

    cif       -> Import Crystal Structure...   (then Scientific Limitations)
    pdb       -> Import Macromolecule...
    toxicity  -> ADMET (hERG, CYP, Ames, ADME)
    virtual   -> Virtual Screening...
    sdf xyz mmcif protein lattice "unit cell" energy -> all correct

`solubility` still returns nothing: ESOL is a DESCRIPTOR, and descriptors
were not in the palette at all.

### SOLVED: properties, which cannot be run

The palette's three indexes are all things you DO, and a descriptor is
not one -- the 36 of them are computed as a batch the moment a molecule
is selected, so there is no per-descriptor action to offer. The palette
therefore knew nothing about **Aqueous Solubility, QED, Lipinski, Veber,
Ghose, Egan, Pfizer 3/75, GSK 4/400, Radius of Gyration** or the other 27.
36 real features, invisible to search.

The action that DOES exist is to reveal the row, and it is exactly what a
palette is for: the value is already on screen somewhere, possibly a
thousand pixels down inside a collapsed section -- the same invisibility
`_reveal` was written for when ADMET "produced nothing".

`reveal_descriptor` expands the section and scrolls, computes NOTHING
(an entry that silently started work would be the surprise this panel
refuses elsewhere), and returns whether it found the row so the caller
can say something honest when it did not. The two failures are different
messages, because "no molecule selected" is a different problem from
"selected, but not computed".

Measured in the running app, 105 commands -> 142:

    solubility  -> Aqueous Solubility (ESOL, log mol/L)   (was NOTHING)
    lipinski veber ghose qed gyration asphericity
    "rule of three" pfizer                                (all were NOTHING)
    bbb         -> BBB Score Descriptors [Calculator] first, then the
                   property -- ties keep panels, calculators, properties,
                   menu items in that order

    reveal_descriptor('esol_logs') -> True, scroll 0 -> 660, row visible

**A guard here was CIRCULAR and a mutation caught it.**
`test_every_computed_property_has_a_command` derived its expectation from
`_descriptor_names()`, the same helper the production code uses -- so
dropping the shape table from that helper lost the same 10 descriptors on
both sides and the test stayed green. It reads the two SPEC TABLES now,
which are what the providers publish from. A derived guard that derives
from the code it is guarding is not derived at all.

### The crystal question now has a written answer

"How do I turn the SMILES for table salt into a crystallography
structure" is answered in `docs/SCIENTIFIC_LIMITATIONS.md`, as the FIRST
thing under Crystal structures: you cannot, it has to be measured,
because crystal structure prediction is an open research problem where
real polymorphs differ by less than the error of the methods ranking
them. It names where CIFs come from (COD, ICSD, CCDC, RCSB) and that the
fixtures in this repo came from COD.

`crystal`, `cif` and `smiles` point at that document as well as at the
importer, so the question reaches the answer. The importer still ranks
first, because a keyword never beats a label.

## Finding 5 — SOLVED: a result type with no view

`molecular_dynamics` computes a 101-frame trajectory and
`_RESULT_VIEW_FACTORIES` in
[calculator_inspector_dialog.py](../src/openchem/ui/dialogs/calculator_inspector_dialog.py)
has no entry for a `TrajectoryResult`. Until this sweep, `TrajectoryComputed`
had no subscriber anywhere, so the calculator produced no row at all —
indistinguishable from never having run.

For a while it reported what it produced and deliberately opened no
inspector, because the fallback view would have depicted the input
molecule rather than any of the frames.

**`TrajectoryPlayerWidget` is that view**: the frame in 3D, a scrubber, a
play/pause loop at ~12 fps, and the energy trace underneath with a marker
on the frame being shown. Clicking the trace jumps to that frame, because
an energy spike is the thing somebody wants to look at and making them
find it again on the slider is busywork.

**A 2D grid would have been the cheap answer and a wrong one.** Molecular
dynamics moves atoms; it does not change what is bonded to what. Every
frame of a vacuum run has identical connectivity, so a grid of 2D
depictions shows 101 copies of one picture and reads as "the calculator
produced nothing" -- the exact failure the rest of this document is
about. The motion is only visible in 3D.

The backend is INJECTED, so the 16 tests start no Chromium at all --
the same reason `ir_view_widget` and `nmr_view_widget` take theirs.

Verified in the running app on a real 101-frame run: frames 1, 41 and 101
scrub correctly with their own times and energies (0/200/500 fs,
-115.66/-115.64/-115.65 kcal/mol), and play/pause toggles.

**A defect the tests caught that a lazier fixture would not have.** Every
frame was loaded TWICE -- `setValue` on the slider re-enters `show_frame`,
and guarding the value stops the recursion but not the second
`load_conformer`, doubling the JavaScript calls at twelve frames a
second. It was visible only because the test's frames are
distinguishable; a fixture of identical frames would have shown nothing.

## Finding 6 — SOLVED: two periodic tables

Recorded because it is the worked example the rest of this document is
generalising from.

Ketcher ships a periodic table on the editor toolbar; the application has
a much richer one under Tools — configuration, radii, isotope abundances,
a shell diagram. The split was principled (one inserts atoms, one answers
questions) and it read, from the outside, as one table that had lost half
its features depending which button you pressed.

The editor's button is intercepted in
[main.jsx](../tools/ketcher-host/src/main.jsx) and answered with the
application's dialog, which gained "Insert into drawing" in the same
move. Verified in the running app: our dialog opened, Ketcher's stayed
shut, and Insert armed the canvas.

**The one thing Ketcher's could do and ours cannot is query atoms** —
any-atom, list, not-list. That is named on the dialog itself rather than
quietly dropped. `test_the_query_atom_gap_is_named_on_the_dialog` in
[tests/test_periodic_table_is_the_only_one.py](../tests/test_periodic_table_is_the_only_one.py)
fails if the sentence goes.

## Finding 7 — SOLVED: 6.5 seconds of nothing, and a "Running..." that could never appear

Reported as "Details itself has a loading time, there should probably be
some kind of waiting indicator". **Details is not slow.** Timed in the
running app, building the dialog and its `FactView`:

    27 facts (topology)     20 ms
    15 facts (regulatory)   17 ms
     2 facts                18 ms

Flat, and far too fast to notice. The wait is the CALCULATOR, and the
problem is that nothing says so. Sampling the panel every 250 ms across
an ADMET run:

    t = 0.0 s   <no row at all>
    t = 6.5 s   "[Toxicity and metabolism] | CYP1A2 inhib..."

Six and a half seconds of complete silence, then the result and its
dialog arrive together. From the outside that is indistinguishable from
a slow dialog, which is exactly how it was reported.

**`_present_alert` already renders a "Queued..." / "Running..." state and
it can never appear**, because the row is created when the first RESULT
arrives. There is nothing on screen to put "Running..." into. The state
is written, correct, and unreachable.

**Fixed by putting the indicator on the calculator's own row**, which
already exists and never moves -- a hidden `QLabel` beside the button,
rather than inserting and removing a form row around every run. This
panel's layout is delicate enough that one parked label is the smaller
risk, and a hidden widget costs no space.

**The clearing signal had to be new, and that is the interesting part.**
No result event can carry it: a result is named after ITSELF, and the two
are not always the same -- `nmr_database` publishes a spectrum called
`nmr_13c`, `gasteiger_charge_at_ph` publishes `gasteiger_charge`. Anything
clearing on the result's id leaves those showing "Running..." for the rest
of the session, which is worse than never having shown one.
`_finish_batch_run` has described itself as best-effort for exactly this
reason since it was written.

`CalculationFinished(calculator_id, molecule_uuid)` is published by
`_CalculatorTask` **in a `finally`**, so it fires for a run that failed,
raised, or returned an unpublishable type. Those are precisely the runs
whose indicator would otherwise stick forever.

Measured in the running app across a real ADMET run, sampling every
250 ms:

    t = 0.0 s   hidden
    t = 0.3 s   shown: "Running..."
    t = 6.3 s   hidden

`_finish_batch_run` stays. Results also arrive from the descriptor
providers at selection time with no dispatch behind them, and that path
has no `CalculationFinished` to fire.

A trap worth recording: `OPENCHEM_DRIVE`'s `calculator` step reproduces
`_open_calculator` minus its settings dialog, and did not set the running
state -- so the first scripted run showed no indicator at all and the
feature looked broken when it was simply not being driven. Anything
`_open_calculator` sets before dispatch has to be set there too.

## The pattern

Six of the seven findings are the same failure: **a thing exists, works,
and has no honest way to be reached or read.** Finding 7 was the sharpest
form of it -- a "Running..." state that was written, correct, and
unreachable -- and is now fixed.

**All seven findings are done.** The one declared limit that remains is
a plugin's inability to name a section containing an acronym; there are
no such plugins, and the fallback is correct for everything else.

**Three of the seven findings had something wrong in them** -- finding
1's "a registration change, not a code one", finding 3's count and its
proposed fix, and finding 4's claim about the Receptor Library. All three
were written from reading rather than from running, and all three were
corrected by measuring. That is the pattern worth taking from this
document, more than any individual count in it.

The same applies to the guards written while closing them. Between them,
**one test derived its expectation from the code it was guarding, and
four in a row passed while exercising nothing** -- every one found by
mutation rather than by review. A guard is not a guard until something
has been broken in front of it. None of them is a chemistry bug and none was visible to 3613
passing tests, because a test asserts that a value is correct and never
that a person could find it.

The two guards written during this work are the shape worth repeating —
both DERIVE what they check from the code rather than restating it:

- `test_every_summarised_result_type_has_a_field_the_table_names` reads
  the payload field names off the dataclasses, so a rename fails there
  instead of silently reverting to a blank summary.
- `test_every_dock_the_window_builds_has_a_help_topic` (which predates
  this sweep) iterates the docks the window BUILDS rather than the map,
  which is how two panels shipped with no help topic.

A guard that iterates the registry rather than a hand-written list is the
only kind that survives an open vocabulary.
