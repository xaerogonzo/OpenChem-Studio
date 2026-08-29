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

`properties-width.json` squeezes **and then widens** deliberately: a latched
caption is only observable once the room comes back, so a single-width run
cannot see it.

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
