# Driven visual checks

Committed scripts that drive the real application, run the geometric oracle in
`src/openchem/ui/visual_check.py` against a surface, and save a screenshot
beside the findings.

```bash
OPENCHEM_DRIVE=benchmarks/visual/properties-width.json uv run --no-sync python -m openchem.main
```

Findings and the painted-item count go to the log as
`OPENCHEM_DRIVE: visual_check <tag> [<surface>] -- N painted item(s), M finding(s)`.
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
| `atom_selection_sync.json` | the Atom Inspector and the 2D canvas, on a FRESHLY LOADED structure and then on an EDITED one | the pool-id/molfile-position divergence, outbound: clicking a carbon answered "pick a heavy atom" -- this is the same trap inbound, where nothing declines |

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
