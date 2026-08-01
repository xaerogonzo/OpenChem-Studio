# Benchmark history — `iupac_namer`

Score per change against `benchmarks/naming`, scored by OPSIN round trip and
not by string match. The corpus was 124 molecules through the rows below and
is now 165; the revision each row was measured on is stated. Regenerate with:

```bash
uv run --no-sync python benchmarks/naming/score.py benchmarks/naming/predictions_check.json
```

The headline number is deliberately not the only column. It can sit still
while one molecule is fixed and another breaks, which is why `score.py` prints
a per-molecule delta and why the defect counts are tracked alongside it.

`gate_disagreement` appears from 2026-08-01: the scorer gained full InChIKey
as a second gate, and rows where the two gates disagree are surfaced for a
human rather than scored either way. It is not a regression — it split the
existing `wrong_structure` bucket into "genuinely wrong" and "same substance,
different depiction".

Rows below are all against the **124-row** corpus revision:

| date | change | correct | exact | equiv | gate-dis | wrong | Sev A open | vendored suite |
|---|---|---|---|---|---|---|---|---|
| 2026-08-01 | as vendored | 120/124 | 71 | 49 | — | 4 | not yet measured | 2940 P / 5 F / 16 S |
| 2026-08-01 | WS-1 instrumentation + InChIKey gate | 120/124 | 71 | 49 | 2 | 2 | 5 known | 2953 P / 5 F / 16 S |
| 2026-08-01 | WS-2/3 test expectations + ring polyacylium | 120/124 | 71 | 49 | 2 | 2 | 14 measured, 7 fixed | 2962 P / 0 F / 16 S |
| 2026-08-01 | WS-5 ylium/ide locant | 120/124 | 71 | 49 | 2 | 2 | 14 measured, 16 fixed | 2971 P / 0 F / 16 S |
| 2026-08-01 | WS-4 charge next to unsaturation | 120/124 | 71 | 49 | 2 | 2 | 7 open, 26 fixed | 3039 P / 0 F / 16 S |
| 2026-08-01 | WS-9 refusal guard | 120/124 | 71 | 49 | 2 | 1 + 1 no-pred | 7 open, 26 fixed | 3046 P / 0 F / 16 S |
| 2026-08-01 | WS-6 PIN consistency (Sev B) | 120/124 | 71 | 49 | 2 | 1 + 1 no-pred | 7 open, 26 fixed | 3047 P / 0 F / 16 S |

The last row is the only one where a molecule moved: diazomethane
`wrong_structure -> no_prediction`. The score is unchanged because both are
failures — but one of them was a confident wrong answer and the other is an
honest refusal, which is the trade the refusal guard exists to make.

## Why the score did not move — and then did

Every severity-A fix above repaired molecules the corpus did not contain. It
is a general-purpose naming benchmark — 124 molecules across aliphatics,
aromatics, heterocycles, drugs, stereochemistry, isotopes — and its one
`charged_zwitterion` category (8 rows) happened to include no carbocation, no
carbanion and no polyacylium. **The benchmark could not see the single largest
correctness problem the engine had.** Its role through that work was as a
veto, not a scoreboard: it proved that changes to a core renderer and a
perception classifier broke nothing mainstream.

The corpus was then extended with 41 charged species in four new categories
(`carbocation`, `carbanion`, `onium_ion`, `polycharged`), deliberately
including species that still fail. Running the **pre-work engine** against
that same extended corpus gives the comparison that was missing:

| | corrected | exact | equivalent | wrong structure |
|---|---|---|---|---|
| as vendored | 148/165 (90%) | 79 | 69 | 15 |
| after this work | **163/165 (99%)** | 80 | 83 | **0** |

| category | as vendored | after |
|---|---|---|
| carbocation | 7/12 | **12/12** |
| carbanion | 4/8 | **8/8** |
| onium_ion | 8/9 | **9/9** |
| polycharged | 9/12 | **12/12** |

**No wrong structures remain, and nothing is refused or unparsable.** The two
failures are tautomers — same InChIKey, not errors. Every molecule in the
corpus gets a name, and every name denotes the molecule it was given.

All three defects the new categories exposed — phenyl anion (D-003),
guanidinium (D-004), azide (D-016) — were fixed within a day of being made
visible. That is the corpus doing its job: none of them was findable from the
124-row revision, and each was obvious once it appeared as a red row.

| date | change | correct | notes |
|---|---|---|---|
| 2026-08-01 | corpus extended to 165 | 158/165 | +41 charged species; baseline on the same corpus is 148/165 |
| 2026-08-01 | aromatic ring carbanion + guanidinium | 160/165 | carbanion 7/8 -> 8/8, onium_ion 8/9 -> 9/9; delta reported both rows as FIXED |
| 2026-08-01 | azide | 161/165 | polycharged 11/12 -> 12/12; all four charged categories now perfect |
| 2026-08-01 | pyrazolone in substituent position | **162/165** | novel_unregistered 3/4 -> 4/4; **wrong_structure count reaches 0** |
| 2026-08-01 | pyrazole stem (severity B) | 162/165 | unchanged by design -- both stems denote the same molecule; the fix is which one is preferred |
| 2026-08-01 | the last five open severity-A defects | **163/165** | diazomethane no_prediction -> equivalent; **zero wrong structures, zero refusals, zero unparsable** |

The extension paid for itself immediately. Every defect fixed in the rows above
was surfaced by the new categories or by the one corpus row that happened to
carry a pyrazolone, and together they moved the headline number 158 -> 163 —
which the previous six changes, all real severity-A fixes, could not do at all
on the 124-row revision.

### Consequence worth knowing

Predictions files recorded against the 124-row corpus — including the ML
baselines in `predictions_full.json` — **cannot be rescored** against the
extended corpus. `score.py` now refuses them rather than letting `zip()`
silently truncate and report a model's 88/124 as "88/165". Those files remain
valid against the corpus revision they were made for.
