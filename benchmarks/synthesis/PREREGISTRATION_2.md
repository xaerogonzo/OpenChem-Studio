# Synthesis planner quality benchmark, protocol 2 (option 3a): preregistration

Written 2026-10-20. **Status: APPROVED by Alex on 2026-10-20 (all seven choices, as proposed); FROZEN on the commit that adds its tested runner, before the first search. Nothing has been run.** After that it changes only by a dated amendment that says what and why. Drafted earlier the same day; the changes made between the draft and the freeze are listed under "At the freeze" and none touches a threshold or a reading. Background: `benchmarks/synthesis/RESULT.md` (protocol 1, verdict PARTIAL) and `docs/SYNTHESIS_HELPER_DESIGN.md`, section "After the result".

## The question

Protocol 1 measured the reference route among the first 10 routes the planner returned and found 0.373 (PARTIAL; the published figure is 0.61). Reading the PaRoutes paper and its scripts afterwards showed that **protocol 1 did not count the same thing the published figure counts** [source:genheden2022paroutes] [source:torrenperaire2024]:

* **Pool.** Protocol 1 called `build_routes()` with its defaults: at least 5 and at most 25 routes, a median of 11 returned (42% of targets fewer than 10). The paper extracted every solved route (median 273).
* **Ranking.** Protocol 1 kept the planner's order, which is its state score. That score is indiscriminate among solved routes: in a format check on a spike-seen target, **the first 11 of 49 routes had the identical state score (0.9509)**, so their order is arbitrary. The paper ranked routes by Badowski's route cost [source:genheden2022paroutes].
* **Ties.** PaRoutes' own script (`analysis/route_quality.py`, with `route_distances.utils.routes.route_ranks`, read 2026-10-20) gives routes with equal scores the **same rank** and counts "top-k" as every route whose rank is at most k. So a published top-10 is **the first 10 score levels, however many routes they hold**, not 10 routes. Because the route cost depends only on a route's shape and on which leaves are in stock, many routes tie, and a "top-10" can cover most of a pool.

**Does the recovery shortfall of protocol 1 come from how routes were pooled, ranked and counted, rather than from the planner failing to find the reference routes?** Measured, not shipped: the answer is the deliverable, whichever way it falls.

This is a re-measurement of seen targets with a protocol chosen **after** seeing the first result. That is stated as a limitation, not hidden (below), and it is why there is exactly one deciding measure and no further protocol variants will be run to chase a better number.

## What is the same, and what changes

| | Protocol 1 | Protocol 2 |
|---|---|---|
| Targets | the seeded draw: 300, the first 20 of them repeated twice more | **the same 300 and the same 20** (`draw.json` of protocol 1, copied unchanged); a paired comparison, not a fresh sample |
| Planner, models, stock | AiZynthFinder 4.4.1, public ONNX USPTO policy, no filter, the set's own stock (13,414 InChI keys) | **identical**; the report is refused if the packages, Python or selection differ from protocol 1's records, if the checksums of `targets_n1.txt` and `stock_n1.txt` differ, if the InChI-key stock differs from protocol 1's file, or if the two model files differ in size (protocol 1 recorded no checksum of them; their MD5s are recorded now) |
| Search | MCTS, 500 iterations, 1,800 s safety net, `max_transforms` 10, `return_first` false | **identical** |
| Routes returned | `build_routes()` defaults (5 to 25) | **`post_processing.all_routes` true**: every solved route when the target is solved (verified 2026-10-20 on a seen target: 49 returned, 14 by default); an unsolved target returns the default 5 to 25 as before |
| Ranking | the planner's state score | **offline, by the PaRoutes route score** (below), never inside the planner (a list of scorers makes the planner switch to a Pareto selection, so none is passed) |
| Counting | the first 10 routes | **both** the PaRoutes count (M1) and the first-10-routes count (M2), below |
| Match rule | exact set of reaction identities, stereo kept (`route_match.py`) | **identical**; ignoring stereo was measured on protocol 1's records and changes nothing (0.373 either way) |

## The measures (the code will be `route_rank.py` and `route_match.py`, tested before any run)

**The route score** replicates `route_distances.utils.routes.route_score` as read 2026-10-20 (MIT licensed, `MolecularAI/route-distances`): a terminal molecule costs 1 if the planner marks it `in_stock` and 10 if not; a molecule with a reaction below it costs `1.0 + sum(child cost / 0.8)` over the reaction's precursors; lower is better. (The paper's text says a fixed reaction cost of 10 and a yield of 1; the executable default is 1.0 and 0.8, and **the code is what the scripts ran**; the choice is recorded here because it changes the cost values, not which routes tie, since only the shape and stock flags enter.) **The rank** is dense: routes sorted by score ascending (stable in the planner's order); a route's rank is its predecessor's if the scores differ by less than 1e-8, otherwise one more.

* **M1, the PaRoutes top-k:** the reference is recovered at k if any route with rank at most k matches it by the exact rule. **This is the measure the thresholds were set against.**
* **M2, the user-facing top-10:** the routes ordered by (dense rank by route score ascending, then state score descending, then the planner's order), and the reference is recovered if one of the **first 10 routes** matches. This is what a person shown 10 routes sees. **It is reported beside every M1 number and any product wording must quote M2, not M1.**
* **M3, the planner's own order over the full pool:** the first 10 routes in the order the planner returns them with `all_routes` on. It should reproduce protocol 1's 0.373 (the pool for the top 10 is the same; only the ties at the boundary and the search's own noise differ). It is the **consistency check** and the dividing line between the pool and the ranking.
* **Pool recall:** any returned route matches the reference. The ceiling for any ranking.
* **Solved, valid, stable:** as protocol 1. **Valid** is judged on the first route of **M2's order**; **stable** on the same 20 targets run three times.

Reported, deciding nothing: M1 and M2 at k = 1, 5 and 10; the number of routes with rank at most 10 (median and the share of the pool), and the number of distinct ranks per target (this says how much of the PaRoutes "top-10" is tie-inclusion); the rank at which the reference first appears; the decomposition **0.373 (protocol 1) to M3 to M2 to M1**, which attributes the change to the pool, the ranking and the tie-inclusion in turn; leaf overlap, first-route-shorter, route counts, seconds, peak memory; recovery by reference depth.

## The reading rule, fixed now

`judge.py` is applied **unchanged** to the 300 targets with the recovered claim read from **M1 at k = 10**; the other three claims as in protocol 1. Overall GO, PARTIAL, NO-GO and NOT EVALUABLE exactly as in `PREREGISTRATION.md`. The verdict is named **protocol-2 GO / PARTIAL / NO-GO**; it **does not replace protocol 1's PARTIAL**, which stands as measured. The thresholds are protocol 1's, unchanged: PASS at 0.50 and PARTIAL from 0.35 for the recovered claim (set against the published 0.61, which is an M1-type figure).

**NOT EVALUABLE** as in protocol 1, and also if: records come from more than one commit, from a dirty `src/` or from more than one planner identity; or **|M3 minus 0.373| exceeds 0.05** (about two standard deviations of the sampling error of a fraction of 300 near 0.37), which would mean this run does not reproduce protocol 1's behaviour and nothing about the pool or the ranking can be concluded until the difference is explained.

**What each reading of M1 at 10 means (decided now):**

* **At least 0.50: the shortfall was protocol.** Protocol 1's PARTIAL is explained by pool, ranking and tie-counting; the planner's recovery of known routes, counted the PaRoutes way, is consistent with the literature for a planner of this kind. The product wording may then cite the PaRoutes-style figure **only together with M2** and the contamination caveat.
* **0.35 up to 0.50: partly protocol.** The decomposition says how much; nothing is explained away; the narrowed claim stands.
* **Below 0.35: not protocol.** The planner with this public model does not recover reference routes at the published rate however they are counted; options 3b (the reference-excluding Keras model) and 3c (a non-USPTO set) are the next candidates, and the narrowed claim stands.

None of these changes Stage 1's authorization, which was decided on the narrowed claim. What the result changes is **how many routes slice 3 asks the planner for and how they are ranked and worded**.

## What was seen first (disclosure)

* **Protocol 1 in full:** all 300 targets and their results, including which references were recovered; the diagnostics (by depth, leaf overlap, route counts); and the re-scoring of its records with stereo ignored.
* **The literature** (eight papers, `docs/sources.toml`) and the PaRoutes and route-distances source files named above.
* **A format check on spike-seen targets (indices 1 and 2) at 30 to 60 iterations** with `all_routes` on and off, to confirm the mechanics: 49 routes against 14 on target 2; the first 11 state scores identical; the same unsolved result on target 1; extraction took 0.03 to 0.23 s. These are targets the protocol-1 draw excluded and the spike already searched.
* **An end-to-end smoke test of the runner on the same two spike-seen targets (indices 1 and 2) at the full 500 iterations,** in a scratch folder outside the benchmark records (r1 on both, r2 and r3 on target 2), to catch wiring faults before a five-hour run. It took 5.5 minutes; target 2 returned 341 routes (4.1 MB) with 128 score levels, 35 routes inside its PaRoutes top-10; the stock matched protocol 1's file byte for byte; the report ran and refused the 2-target run, as it must, because M3 was 0.000 against 0.373. Its records are discarded.
* **No other search has been run for protocol 2.**

## What it cannot say

* **Nothing about generalisation:** the same public model, probably trained on these reference reactions; the contamination caveat of `PREREGISTRATION.md` applies in full. A high M1 here would not show that the planner finds routes to molecules it has not seen.
* **Nothing about feasibility,** conditions, yields or selectivity.
* **It is not blind.** The protocol was designed after seeing a low result and reading why it might be low. The defence is the rule above: one deciding measure, fixed now, no further variants.
* **It is not the official metric.** PaRoutes uses a tree edit distance of effectively zero (below 1e-6) on molecule and reaction fingerprints; this uses the exact rule of protocol 1. They are close in strictness but not identical; stereo does not matter on protocol 1's records. An optional check with the official `route-distances` code is described below.
* **M1 is generous by construction** (ties count). It is the comparable number, not the user-facing one; M2 is the user-facing one.
* **The same 300 targets are no longer fresh,** so this is a paired comparison of two protocols, not a second independent gate.

## Expected cost and records

About 340 searches as in protocol 1 (300 plus 40 repeats), so **roughly the 5.3 hours measured for protocol 1** (extraction is a fraction of a second) and about the same peak memory (2.75 GB). **Raw records are larger:** every solved route is kept, about 12 KB each as JSON, so a target with 270 routes is about 3 MB; a smoke test (below) returned 341 routes for one target in 4.1 MB, so the raw files are expected at up to about 1 GB uncompressed and around 100 MB gzipped, **kept locally and not committed unless the gzipped size is small**; the committed artifacts are the per-target table, the report, the verdict, the draw, the configuration and the provenance. It is run alone: **not at the same time as the proton-affinity or bond-dissociation ORCA runs** (one long job at a time), and not until Alex says so.

## What gets built after approval (not before)

`route_rank.py` (the score, the dense ranks, M1, M2 and M3 as pure functions), `plan_batch.py` gaining `--all-routes` (default off, so protocol 1's runner behaves as it did), `run_quality_2.py` (reads protocol 1's `draw.json`, writes `artifacts_protocol2/`, reports with the unchanged `judge.py`, refuses as above and states protocol 1's identity it compared with), tests on synthetic routes with hand-computed scores and ties, a mutation check, and the runner committed with this file **before the first search**. The run commands will be recorded in the design note as "To run", as for protocol 1.

**The optional official-metric check was approved and is built as a secondary figure that decides nothing** (`official_check.py`): M1, M2 and M3 recomputed with the official tree edit distance (`route_distances.ted.reactiontree.ReactionTreeWrapper`, a route found when the distance is below 1e-6, as `route_quality.py` does) in place of the exact rule. **It runs in a separate environment (`D:\_scratch\route_distances_env`, 234 MB: route-distances 1.2.4 installed without its dependencies, plus numpy 1.26.4, scipy, apted 1.0.3, rdkit 2023.9.6 and pydantic), never in the planner's**: installing the package normally would pull in torch and about twenty other packages and change the planner's recorded identity. Checked on 2026-10-20: a route's distance to itself is 0.0 for the planner's routes and for a PaRoutes reference route.

## At the freeze (2026-10-20)

Alex approved all seven choices below as proposed. Changes between the draft and the freeze, none to a threshold or a reading:

* **M2's order is by dense rank, then state score descending, then the planner's order** (the draft said "route score"); a route's rank, not its raw score, so two routes of one shape that differ in the last float digit still tie.
* **Protocol 1's model checksums do not exist,** so the "model files differ" refusal compares file sizes (91,518,243 and 3,313,598 bytes) and the MD5s are recorded for the future.
* **The official-metric check runs in its own environment** (above), not the planner's.
* **The runner reads protocol 1's gzipped committed records** when the raw files are absent, and takes the 0.373 for M3's consistency check from protocol 1's `verdict.json`, not from a constant.

## Approved on 2026-10-20 (all seven, as proposed)

1. **M1 (the PaRoutes count) decides the verdict; M2 (first 10 routes) is reported beside it and is what any product wording must quote.** Reason: the 0.50 and 0.35 bars were set against a published M1-type figure. The alternative is to let M2 decide, which keeps the strict count but makes the bars harder to meet than the approved ones were meant to be.
2. **The thresholds stay exactly protocol 1's** (0.50 and 0.35 for recovery).
3. **The consistency tolerance of 0.05** between M3 and protocol 1's 0.373.
4. **The same 300 targets and the same 20 stability targets, paired with protocol 1.**
5. **The 20 stability targets repeated twice more** (40 extra searches, about 40 minutes) so the noise floor of the new measure is known. The judge requires all 20 (fewer is NOT EVALUABLE), so dropping them would mean changing the judge, which this protocol does not do.
6. **Whether to ask for the optional official-metric check** (an install).
7. **When to run it,** given the queued ORCA runs.
