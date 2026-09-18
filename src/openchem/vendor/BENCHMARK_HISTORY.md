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

| corpus | | corrected | exact | equivalent | wrong structure |
|---|---|---|---|---|---|
| 165 rows | as vendored | 148/165 (90%) | 79 | 69 | 15 |
| 165 rows | after this work | **164/165 (99%)** | 80 | 84 | **0** |
| 181 rows | as vendored | 157/181 (87%) | 81 | 76 | 22 |
| 181 rows | after this work | **180/181 (99%)** | 82 | 98 | **0** |

Both engines were run against both corpus revisions, so each pair is a like
for like comparison. The 181-row revision is the current one.

**These four figures are as scored at the time, deliberately.** The scorer
has since gained a `tautomer` outcome class, under which this engine scores
**181/181** on the 181-row corpus — metformin round-trips to a different
tautomer of the same substance, which is a success. Restating only the row
that benefits would break the like-for-like comparison, and rescoring the
`as vendored` rows needs that engine re-run. The table stays as measured;
the current number is in the dated log below.

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
| 2026-08-01 | poly-N-substituted guanidinium (D-025) | 163/165 | unchanged: the corpus contains no substituted guanidinium. Verified by the defect table, not the score |
| 2026-08-01 | ring N-oxide substituents (D-024) | 163/165 | unchanged, and not in the corpus either. **Severity-A open list reaches empty** |
| 2026-08-01 | indicated hydrogen preserved (D-026) | **164/165** | 1,2,3-triazole gate_disagreement -> equivalent. The one remaining failure, metformin, is a genuine depiction difference |
| 2026-08-01 | corpus extended to 181 | **180/181** | +16 rows covering the last three fixes: n_oxide 6/6, guanidinium 5/5, tautomer 5/5 |
| 2026-08-04 | `tautomer` scored as the success it is | **181/181** | no engine change. Metformin round-trips to a different tautomer of the same substance; the scorer now says so instead of counting it wrong. Awarded only when canonical-tautomer AND InChIKey both agree |

The extension paid for itself immediately. Every defect fixed in the rows above
was surfaced by the new categories or by the one corpus row that happened to
carry a pyrazolone, and together they moved the headline number 158 -> 163 —
which the previous six changes, all real severity-A fixes, could not do at all
on the 124-row revision.

### Why the corpus was extended twice

Three consecutive fixes — D-024, D-025, D-026 — could not move the score,
because the corpus held no ring N-oxide substituent, no substituted
guanidinium, and no tautomer pair. Each had to be verified against the defect
table instead. A score that cannot move is a score that cannot regress either,
so the second extension exists to close that blind spot rather than to raise
the number.

It half worked, and the as-vendored comparison below says which half.
`guanidinium` goes 0/5 -> 5/5 and `n_oxide` 4/6 -> 6/6, so those rows do catch
their defects. `tautomer` reads 5/5 on both engines: the as-vendored one
emitted the bare name `1,2,3-triazole`, which OPSIN resolves to 1H, so it
round-tripped by accident. D-026 is caught by the pre-existing `heterocycle`
row instead. New rows do not automatically see the defect they were added
for — that has to be checked, not assumed.

### Consequence worth knowing

Predictions files recorded against the 124-row corpus — including the ML
baselines in `predictions_full.json` — **cannot be rescored** against the
extended corpus. `score.py` now refuses them rather than letting `zip()`
silently truncate and report a model's 88/124 as "88/181". Those files remain
valid against the corpus revision they were made for. This now applies to the
165-row revision as well.

## The 187-row revision (2026-09-17)

Six molecules added as `substituent_naming`, from a user report: three
fentanyls and three MPMI tryptamines. Every one of them ROUND-TRIPPED while
wrong, which is why the EXACT column is what moves here.

| date | change | correct | exact | equiv | stereo_wrong | vendored suite |
|---|---|---|---|---|---|---|
| 2026-09-17 | master 8be42b6, 187-row corpus | 184/187 | 82 | 101 | 3 | 3209 P / 0 F / 16 S |
| 2026-09-17 | D-027 substituent stereo inheritance | 187/187 | 82 | 104 | 0 | 3209 P / 0 F / 16 S |
| 2026-09-17 | D-028 alphanumerical order | 187/187 | 82 | 104 | 0 | — |
| 2026-09-17 | D-029 free-valence numbering | 187/187 | 87 | 99 | 0 | 3255 P / 0 F / 16 S |

On the OLD 181-row revision, for comparison with the rows above: 181/181
throughout, exact 82 -> 84 (the two nicotine rows, whose `-5-yl` locant D-029
fixed).

`stereo_wrong` is new in `score.py`. A name whose descriptor CONTRADICTS the
structure was scored `stereo_lost` -- "silently flattened" -- which is the
same conflation the app's own round-trip verifier had. It now asks that
verifier (`naming_providers._stereo_verdict`), so the benchmark and the
displayed name cannot disagree about what "wrong" means.

**D-028's whole point is invisible here**, and that is the lesson of this
revision rather than a gap in it: four corpus names changed to the correct
prefix order (chloroquine, atenolol, omeprazole's sulfoxide, the biaryl urea's
N/N') and the score did not move, because a mis-ordered name parses to the
right molecule. Those defects are pinned by exact-name rows in
`tests/test_namer_known_defects.py` and by the sort-key table in
`tests/vendor/iupac_namer/test_assembly.py`.

## 2026-09-17 -- naming round 3: 187/187, exact 87 -> 98; held-out 39/40 -> 40/40

| stage | regression exact | held-out | what moved |
|---|---|---|---|
| baseline | 87 | 39/40, one wrong_structure | -- |
| D-030 bridged free valence | 87 | 40/40 | the held-out adamantane; 5 malformed organoelement suffixes became well formed |
| D-031 fused free valence | 89 | 40/40 | both naproxen rows |
| D-032 plan budget | 92 | 40/40 | Si, P and I parents finally proposed |
| D-033 mononuclear locant | 93 | 40/40 | betaine; silyl prefixes |
| D-034 nesting order | 93 | 40/40 | 6 names re-bracketed; PubChem uses brackets throughout, so none can become exact |
| D-035 isotope hyphen | 93 | 40/40 | PubChem discards the isotope on both rows |
| D-036 retained names | 97 | 40/40 | +5 exact, and chloroform exact -> equivalent because PubChem's own string is the non-preferred one |
| D-037 ring names | 98 | 40/40 | benzofuran |

Stage records for every row are in `benchmarks/naming/stages/`. The held-out
PubChem-verbatim count stayed at 14/40 throughout, which is the honest
generalisation signal: every fix here was made on the regression corpus.

## 2026-09-18 -- naming round 4: 187/187 throughout; verbatim 98 -> 101; the fresh held-out set 9 -> 15

Three populations, and only the last one is a generalisation number
(`benchmarks/naming/README.md`). Round-trip correctness never moved from
187/187 and 40/40 on the two active sets; what moved is agreement with a
name, which the round trip cannot see.

| stage | regression verbatim | heldout_v1 verbatim | what moved |
|---|---|---|---|
| baseline (99b6281) | 98/187 | 14/40 | -- |
| stage 5a/5b comparator | 98 | 14 | decisions identical under 5a; 5b's two reorders enumerated |
| A3 N-H numbering, locant omission | 99 | 14 | benzenediazonium; cid4000 at its target |
| A4 retained parents | 100 | 14 | 1,4-xylene |
| A5 P-58.2 hydrogens | 101 | 14 | |
| A5b esters, aminium | 100 | 14 | methylammonium LOST verbatim to the book's `methanaminium` |
| A5c/A5d | 100 | 14 | chloroquine to its adjudicated name |
| A9a enclosing marks, alkoxy | 102 | 15 | |
| A9b locants, amido | 100 | 14 | four acetate-locant losses where PubChem keeps "2-" and the book drops it |
| A9c preferred prefixes | 100 | 15 | |
| A10, A8, A7 | 100 | 15 | no corpus row at their targets; the defect table carries them |
| A6 heteroatom parents | 101 | 16 | trimethylsilanol, phenylboronic acid, cid32000; cid55000's dihydrazide |
| A11, A12 | 101 | 16 | no names changed (0/187, 0/40) |

Every stage's record is in `benchmarks/naming/stages/r4-*.json`, including
the count of changed winning hypotheses, so a stage that changed decisions
without changing text is visible too.

### The final evaluation (`--final-evaluation`, stage r4-final)

| population | round trip | PubChem verbatim | engine = adjudicated PIN | PubChem = adjudicated PIN |
|---|---|---|---|---|
| regression (187) | 187/187 | 98 -> **101** | **28/30** | 15/30 |
| heldout_v1, used for tuning (40) | 40/40 | 14 -> **16** | **14/16** | 5/16 |
| heldout_v2, fresh (40) | 40/40 -> 40/40 | **9 -> 15** | not adjudicated | not adjudicated |

The v2 "before" is the baseline commit scored on the same frozen set after
the round (`r4-baseline-v2-final.json`), in aggregate: nothing in v2 was
looked at row by row, before or after. Its +6 is larger than either set the
round was tuned on, which is the evidence the fixes are rules rather than
rows.

The preferred-name columns are over rows with a SETTLED target in
`adjudication.toml`. PubChem agreeing with the adjudicated PIN on only half of
them is why the verbatim column is reported but not optimised: A5b and A9b
each LOST verbatim matches by moving to the book's form.

heldout_v2's round-5 candidates: no structural failure (0 wrong structures,
0 unparsable); 25 rows differ from PubChem and are unadjudicated, so they are
candidates for round 5's adjudication, not defects yet.
