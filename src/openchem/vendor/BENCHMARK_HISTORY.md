# Benchmark history — `iupac_namer`

Score per change against `benchmarks/naming` (124 molecules, scored by OPSIN
round trip, not string match). Regenerate with:

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

| date | change | correct | exact | equiv | gate-dis | wrong | Sev A open | vendored suite |
|---|---|---|---|---|---|---|---|---|
| 2026-08-01 | as vendored | 120/124 | 71 | 49 | — | 4 | not yet measured | 2940 P / 5 F / 16 S |
| 2026-08-01 | WS-1 instrumentation + InChIKey gate | 120/124 | 71 | 49 | 2 | 2 | 5 known | 2953 P / 5 F / 16 S |
| 2026-08-01 | WS-2/3 test expectations + ring polyacylium | 120/124 | 71 | 49 | 2 | 2 | 14 measured, 7 fixed | 2962 P / 0 F / 16 S |
| 2026-08-01 | WS-5 ylium/ide locant | 120/124 | 71 | 49 | 2 | 2 | 14 measured, 16 fixed | 2971 P / 0 F / 16 S |
| 2026-08-01 | WS-4 charge next to unsaturation | 120/124 | 71 | 49 | 2 | 2 | 7 open, 26 fixed | 3039 P / 0 F / 16 S |
| 2026-08-01 | WS-9 refusal guard | 120/124 | 71 | 49 | 2 | 1 + 1 no-pred | 7 open, 26 fixed | 3046 P / 0 F / 16 S |

The last row is the only one where a molecule moved: diazomethane
`wrong_structure -> no_prediction`. The score is unchanged because both are
failures — but one of them was a confident wrong answer and the other is an
honest refusal, which is the trade the refusal guard exists to make.

## Why the score did not move

Every severity-A fix so far repaired molecules the corpus does not contain.
The corpus is a general-purpose naming benchmark — 124 molecules across
aliphatics, aromatics, heterocycles, drugs, stereochemistry, isotopes — and
its one `charged_zwitterion` category (8 rows) happens not to include a
carbocation adjacent to unsaturation or a ring polyacylium.

That is worth stating plainly rather than hiding: **the benchmark's role here
was as a veto, not as a scoreboard.** It proved that fixes touching a core
renderer and a perception classifier broke nothing in mainstream naming, which
is the thing that would have made them a net loss. The evidence that they
helped is in `tests/test_namer_known_defects.py`, which grew from 0 to 26
pinned severity-A cases over the same period.

A reasonable follow-up is to extend the corpus with the charged species this
work characterised, so the two measurements stop being disjoint.
