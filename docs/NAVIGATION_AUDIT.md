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

## What exists

| | count |
| --- | --- |
| menu actions | 25 |
| calculators | 58, in 26 categories |
| panel modules | 12 |
| dialog modules | 16 |

## Finding 1 — 26 sections for 49 buttons

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

This is the strongest single candidate for the "labyrinth" complaint, and
it needs no new mechanism to fix: merging the eleven singletons into the
categories they are closest to is a registration change, not a code one.

## Finding 2 — a category name is not a heading

`_CATEGORY_LABELS` in
[property_panel.py](../src/openchem/ui/panels/property_panel.py) maps a
category id to a display name, and anything missing falls back to
`category.title()`. That fallback has already shipped a heading nobody
chose: NMR rendered as "Nmr" until a documentation sweep caught it.

The map is hand-maintained against an open vocabulary, so it is a
blocklist by another name. A registration with a new category gets a
title-cased heading and nothing fails.

## Finding 3 — eight calculator names do not fit their button

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

8 of 58. The full name is in the tooltip and the section header already
names the category, so several of these are carrying their category in
their own name as well — "NMR Shifts (experimental database)" sits under
a heading that says NMR.

## Finding 4 — features with one door, and no sign pointing at it

**A crystal can only arrive through `File ▸ Import Crystal Structure...`**
and it must already be a CIF. This is the honest answer to "how do I turn
the SMILES for table salt into a crystallography structure": there is no
such path, and there cannot be a good one — going from a molecular graph
to a lattice is crystal-structure prediction, an open research problem,
not a missing menu item. What is missing is anywhere that *says* so.
Nothing in the app connects "I have a SMILES" to "you need a CIF, and
here is where they come from".

The same shape, less severely: the Receptor Library, virtual screening
and batch analysis each have exactly one entry point and no cross-link
from the place a user would be standing when they wanted them.

## Finding 5 — a result type with no view

`molecular_dynamics` computes a 101-frame trajectory and
`_RESULT_VIEW_FACTORIES` in
[calculator_inspector_dialog.py](../src/openchem/ui/dialogs/calculator_inspector_dialog.py)
has no entry for a `TrajectoryResult`. Until this sweep, `TrajectoryComputed`
had no subscriber anywhere, so the calculator produced no row at all —
indistinguishable from never having run.

It now reports what it produced and deliberately opens no inspector,
because the fallback view would depict a trajectory as an empty
structure. **A trajectory player is the missing feature**, and it is the
one place in the audit where the gap is a real build rather than a
rearrangement.

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
unreachable -- and is now fixed. None of them is a chemistry bug and none was visible to 3613
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
