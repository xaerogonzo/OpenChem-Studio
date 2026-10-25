# Protocol 3 addendum (2026-10-25): two papers that arrived after the freeze, 0 of 2 recovered

This is an addendum, not a second run. `PREREGISTRATION_3.md` (decision 6) says papers that arrive before the freeze are read and added and none after, and protocol 3 was frozen and run on 2026-10-24. So these papers are **not in the frozen 51, not in the reading (LOWER), and not in any figure of `RESULT_3.md`**; `artifacts_protocol3/` is unchanged and `tests/test_synthesis_protocol3_addendum.py` holds the two sets apart. Two papers cannot support a test, and none is made.

## What arrived and what was done

Three papers were obtained after the freeze. Each was read with protocol 3's own brief (the lead rule, the 4-reaction cap, leaves and intermediates), checked by `validate_refs.py` (copied here unchanged), and the two with a route were re-read by a second reader.

| paper | what the frozen run had | now | outcome |
|---|---|---|---|
| Kral, ChemMedChem (the 3'-dehydroxypurpurogallin carboxamides) | only the paper's 2-page corrigendum, excluded as `no_synthesis_in_paper` | the article and its SI | route, 4 reactions, lead 14a, tier B |
| Singh, ACS Med. Chem. Lett. (lignan-monoterpenoid xanthine oxidase inhibitors; a spare of the batch 3 draw) | the article without its SI, excluded as `route_not_explicit` | the SI | route, 4 reactions (depth 3), lead MT7, tier B |
| Ma, J. Med. Chem. (autotaxin inhibitors; not in any draw, wanted for the pilot) | not read | the article and SI | **excluded**: the lead (compound 35) takes about 8 reactions and its building blocks are "previously reported" |

Two things settled in the reading, recorded in each file's notes. **Kral's compound 14a:** the article's SAR sentence and its experimental headings disagree about which tetrazolylbenzyl isomer is 14a; the corrigendum's corrected Table 1 draws 14a as the 3-isomer (meta, 0.35 uM), which agrees with the headings and the printed NMR, and that is what the route uses (the uncorrected Table 1 in the article draws 14a as a pyridylmethyl amide, which is the production error the corrigendum fixes). **Kral's step 2:** the reader listed acetic anhydride once for a triacetylation; the carbon check flagged it and it is listed three times (once per acetyl, the brief's rule for equivalents), recorded in the file's notes. Both routes are tier B: Kral's tetrazolylbenzylamine is never named in the paper (its being purchased rests on the general sentence) and which of two amidation routes made 14a is not stated; Singh's azide has no printed name (derived from the series).

## The search

Protocol 3's settings and code unchanged (`run_addendum_3.py` calls `run_quality_3.py` and `judge_3.py`), one search per target on the primary stock: the frozen primary stock plus these routes' starting materials (3 new keys), minus their intermediates and targets (none were in it). Committed before the search (`f1353d75`); the planner identity is the frozen run's. The frozen run's primary stock gave identical results three times, so one search is its own noise floor.

| paper | depth | solved | routes | exact match in the first 10 | in the pool |
|---|---|---|---|---|---|
| Kral | 4 | no | 21 | no | no |
| Singh | 3 | yes | 298 | no | no |

**0 of 2.** Protocol 2's depth rates would expect 0.43 of these two (0.39 at depth 3, 0.04 at depth 4), so 0 is what they predict, and it neither confirms nor revises the frozen reading.

Why each missed, from the reaction-level record: **Kral** has none of its four reactions in any of the 21 routes returned and was not solved (a laccase coupling of two phenols to a benzotropolone, a triacetylation, an amide coupling on the acetylated acid and a methanolysis of the acetates: the planner proposed none of them for these molecules). **Singh** was solved with 298 routes, and each of its four reactions appears in some route (the alkylation of sesamol in 14, the propargylation in 149, the azide formation in 1, the cycloaddition in 16), but no single route holds all four: the miss is in the combination, not in a missing transformation.

## What it cannot say

Two routes, both tier B, both from 2024-2025. It is a record that these papers were read and run, not evidence about the rate. Anything that bears on the rate is protocol 3's.

## Reproducing

`python benchmarks/synthesis/run_addendum_3.py report` reads the gzipped records in `artifacts_protocol3_addendum/` and reproduces `report.txt` and `table.json` identically. The raw record (3.8 MB) is also at `D:\_scratch\synthesis_protocol3_addendum_records` with its MD5. The two searches take about 2 minutes.
