# Protocol 3 result (run 2026-10-24): LOWER than protocol 2's depth-matched rates

Protocol: `PREREGISTRATION_3.md` (frozen 2026-10-24, all eight decisions approved as recommended). Run exactly as frozen: 51 references, five searches of each (`primary-r1`, `leaves-r1`, `zinc-r1`, `primary-r2`, `primary-r3`), 255 searches, 0 failed, `src/` clean, the code and the prepared inputs committed before the first search. Records, references, verdicts and the report are in `artifacts_protocol3/`; the raw records (about 330 MB) are gzipped there (17 MB) and also kept at `D:\_scratch\synthesis_protocol3_records` with MD5s.

**One event during the reporting, stated here.** The first run of `report` printed "NOT EVALUABLE: the records carry more than one planner identity" because the identity check compared the stock name, which differs between the three stocks by design. The check was corrected to compare the packages, Python, expansion and filter (the stock name left out), a test was added, and the report was rerun. No measure, rule or number changed; the figures below are identical before and after.

## The reading (preregistered): LOWER

For the 36 routes of depth 2 or more, protocol 2's M2 at 10 by depth (0.81 / 0.39 / 0.04 at depths 2 / 3 / 4) predicts 14.04 recoveries. **8 were recovered (0.222, 95% interval 0.117 to 0.381); the probability of 8 or fewer under those rates is 0.0073**, below the 0.05 the protocol fixed. Reading: **LOWER**. Protocol 2's figure overstates what the planner does on routes it did not train on, and the product should quote protocol 3's figures.

| depth | routes | recovered at 10 | protocol 2's rate | expected |
|---|---|---|---|---|
| 1 | 15 | 5 (0.33) | (none) | |
| 2 | 10 | 6 (0.60) | 0.81 | 8.1 |
| 3 | 14 | 2 (0.14) | 0.39 | 5.5 |
| 4 | 12 | 0 | 0.04 | 0.5 |

The shortfall sits at depths 2 and 3 (6 of 8.1 and 2 of 5.5 expected); at depth 4 protocol 2's own rate is near zero and 0 of 12 is what it predicts.

**Headline for product wording: the paper's route is among the first 10 shown for 13 of 51 = 0.255 (95% 0.155 to 0.389)**; tier A alone (32 routes, confirmed by the second reader): 9 of 32 = 0.281 (0.156 to 0.454). The two numbers are the same finding within their intervals, so the tier B inferences did not drive it.

## By group (descriptions, not tests; 51 routes cannot support subgroup comparisons)

* **Period:** 2017: 3 of 8; 2018-2022: 8 of 30; 2023-2025: 2 of 13. The cleanest stratum (furthest from the training data) is the lowest, on 13 routes.
* **Stratum:** J. Med. Chem. 2018-2022: 3 of 13; other journals 2018-2022: 5 of 17; the widened frame (2017, 2023-2025): 5 of 21.
* **Tier:** A 9 of 32; B 4 of 19. **Publisher group:** Elsevier 9 of 18, ACS 3 of 17, Wiley 1 of 5, Springer 0 of 6, RSC 0 of 3, others 0 of 2 (a difference in the chemistry the journals publish, not a claim about publishers).

## By stock (exact M2 at 10 / lenient / M1 at 10 / pool / a same-materials route in the first 10 / solved, of 51)

| stock | exact | lenient | M1 | pool | same-materials | solved |
|---|---|---|---|---|---|---|
| primary (n1 + the references' starting materials - their intermediates and targets) | 13 | 13 | 15 | 15 | 17 | 43 |
| starting materials only | 15 | 15 | 15 | 15 | 20 | 28 |
| ZINC as the app ships | 3 | 3 | 3 | 4 | 6 | 38 |

* **The lenient match added nothing** (13 and 13): the planner's routes that miss do not miss over a small reagent.
* **Ranking costs little here:** 15 are recovered anywhere in the pool and 13 in the first 10 (two routes, `baumann2021` and `hu2025_usp5`, were returned and ranked below 10). The loss is not in the order.
* **ZINC is a different question and scores 3 of 51.** For 9 of the 51 references some returned route stops at one of the paper's own intermediates because ZINC sells it, a shorter valid route the exact rule cannot credit. The starting-materials-only stock gives 15 against the primary's 13: the two extra recoveries are the two routes the primary stock returned but ranked below 10.
* **Solved** (a route to stocked starting materials was found) is 43 of 51 on the primary stock, against protocol 2's 0.967 on its own targets.
* **Noise floor:** the primary stock run three times gave 13 of 51 each time and an identical solved flag for every target.

## Why the references were missed (primary stock, 38 misses)

| | targets |
|---|---|
| none of the paper's reactions appears in any returned route | 18 |
| some of the paper's reactions never appear in any route (others do) | 17 |
| the exact route was returned but ranked below 10 | 2 |
| every reaction appears in some route, never together | 1 |

Counting reference reactions that appear in no returned route at all: 10 of 15 at depth 1, 5 of 22 at depth 2, 28 of 43 at depth 3, 24 of 48 at depth 4. **Most misses are the model not proposing the paper's reaction at all** (a transformation or reagent outside the USPTO templates' reach, as the pilot's nitrosation, demethylation and Appel steps were), not a ranking problem and not a stock problem. Even for one-step references, two in three of the reactions were never proposed.

## What it changes for the product (decided here; `src/` is NOT changed in this PR)

* **`BENCHMARK_FINDING` stops being protocol 2's 41.7% as the general claim.** On routes from papers after the model's training data, the paper's route was among the first 10 shown for about 26% (about 22% at depth 2 or more, 60% at depth 2, 14% at depth 3, none at depth 4, on 36 routes); the patent figure (41.7%) is for targets the model probably saw. Both are quoted, with the contamination caveat and the interval, never the larger alone.
* The note on every plan should say that **a missing paper route is not evidence the plan is wrong** (the planner often finds other routes from the paper's own starting materials: one was among the first 10 for 17 of the 51 targets, and for 10 of the 38 misses), and that **an empty result or a different route is the normal outcome, not a fault**.
* The quoting follows `PREREGISTRATION_3.md` item 1: the 13-of-51 figure with its interval and the by-depth split.

## What it cannot say

Feasibility is not measured. The references are routes the papers themselves give for their lead compound, 4 reactions or fewer, from 190 papers read of which 51 qualified: the chemistry is analogue-library chemistry of ordinary reaction types, so long, hard or unpublished-in-detail routes are not measured. A paper's route is one valid route and a miss may be a valid alternative (10 of the 38 misses had a route from the paper's own starting materials in the first 10). The 2017 stratum is a few months after the training data and may hold similar chemistry. A few complex targets are written without stereochemistry. The reference transcriptions were made by reader agents and re-read by a second; 19 tier B routes rest on some inferred reactant. Eight papers' targets were never solved on the primary stock.

## Reproducing

`python benchmarks/synthesis/run_quality_3.py report` reads the gzipped records in `artifacts_protocol3/` and reproduces `report.txt`, `verdict.json` and `table.json`. The searches need the planner environment and data of `docs/SYNTHESIS_HELPER_DESIGN.md` (stage 0b) and take about 5.7 hours (255 searches; median 60 s and at most 171 s per target on the primary stock; peak working set 7.3 GB, against protocol 2's 2.9 GB).
