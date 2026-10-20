# Synthesis planner quality benchmark: result

Run 2026-10-19 to 2026-10-20 from commit `4ff5dbc6` (`src/` clean; one planner identity: AiZynthFinder 4.4.1, onnxruntime 1.31.0, numpy 1.26.4, rdkit 2023.9.6, pyarrow 20.0.0; configuration `artifacts/planner_config.json`, MD5 `2ff89b30...`). The protocol, the rule and the thresholds are those of `PREREGISTRATION.md`, frozen before the first search; **nothing in them was changed after the result was seen.** The verdict is `run_quality.py report`'s, and the numbers below it are diagnostics that decide nothing.

## Verdict: PARTIAL

| Claim | Result | Bar | Verdict |
|---|---|---|---|
| A route was returned (solved with the set stock), of 300 | **0.967** (290) | PASS at 0.90 | **PASS** |
| The reference route is among the first 10 returned, of 300 | **0.373** (112) | PASS 0.50, PARTIAL 0.35 | **PARTIAL** |
| The first route is fully validated, of the 298 targets whose first route has a reaction | **0.993** (296) | PASS at 0.95 | **PASS** |
| The solved flag is identical across three runs, of 20 | **20 of 20** | PASS at 19 | **PASS** |

Per the preregistration, a PARTIAL names the failing claim and **nothing is built; whether to continue is Alex's decision**, made with this report. The failing claim is the reference-route recovery: **0.373 is 0.023 above the NO-GO line (0.35) and 0.127 below the PASS bar.** No target failed (0 of 300), so the run is evaluable.

## What the numbers say beyond the four claims (`diagnostics.py`; reported, deciding nothing)

* **Recovery by rank:** 0.157 at 1, 0.343 at 5 and 0.373 at 10 (published, with an uncontaminated model and the paper's tree-edit-distance credit: 0.20, 0.55, 0.61). The first-10 recovery is only slightly above the top-5 because **the planner returns few routes: the median is 11 and 42% of targets return fewer than 10.**
* **It depends on how deep the reference route is:** reference depth 2: **0.81** recovered (80 targets); 3: **0.29** (136); 4: **0.02** (50); 5: 0.17 (24); 6 or more: 0.20 (10). The solved fraction is 0.92 to 1.00 at every depth, so the planner finds routes for the deep targets and **does not find the reference's route**: the median first solution comes at **iteration 1**, and **48% of first routes are shorter than the reference**. It prefers short alternatives.
* **Credit the strict rule does not give:** in **53% of targets one of the first 10 routes has exactly the reference's starting materials**; the mean best leaf overlap in the first 10 is 0.76; the mean best fraction of the reference's reactions found in the first 10 is 0.52; 48% of targets find at least half of the reference's reactions and 38% at least three quarters. (The paper reports a leaf overlap of 0.63 to 0.68 for the first route; here 0.60.)
* **Validity:** 296 of 298 first routes are fully validated; the validator's outcomes agree with the 60 of 60 seen in the spike.
* **Stability and the noise floor:** the solved flag and the recovered-at-10 outcome were identical across three runs for all 20 stability targets; **the route count differed in 3 of 20 and the node count in all 20**, and the seconds varied by a median 40% between runs. The planner is not deterministic in its tree, only in what it concludes about solved and reference.
* **Cost:** a median 54 s and a mean 61 s of search per target (maximum 156 s); **peak working set 2.75 GB** with the set's stock; **5.3 h of wall time for 340 searches.**

## Corrections to the preregistration's expected cost

The preregistration estimated "roughly three hours" and "under 1 GB of memory" from three small searches. **The run took about 5.3 hours (the random draw is larger and deeper than the file's head) and the planner peaked at 2.75 GB.** The 1 GB figure is withdrawn; with the ZINC stock the spike measured 5.3 GB.

## What this does and does not establish

* **Established, on 300 seeded USPTO targets with the reference stock:** the planner returns a route for 96.7%; its first route's own bookkeeping validates for 99.3%; and what it concludes is repeatable.
* **Not established, and the preregistered caveat applies in full:** the public models are probably trained on these reference reactions, so the 0.373 is **not** a generalisation figure, and a rate **below** the published 0.61 with a model that may have memorised the references is the red flag the preregistration named. Two things make a direct comparison unfair in opposite directions: the strict exact-reaction-set match is harsher than the paper's tree edit distance, and the public model is probably contaminated while the paper's is not. **Neither is used to move the verdict.**
* **Feasibility is not measured and is never reported.**

## The decision this leaves to Alex

PARTIAL means the planner passes validity, stability and solving and is **below the approved bar on agreeing with known patent routes**. The options the preregistration anticipated: (a) **stop** (NO-GO's route: name the next candidate), (b) **continue to Stage 1 with the claim narrowed to what passed**, with the 0.373 and its depth dependence stated beside any route (the product would say "valid, repeatable routes that often differ from the patent route", never "known routes"), or (c) **re-measure on a cleaner footing** (the PaRoutes-excluded Keras model, which needs TensorFlow and a NumPy conflict, or a reference set that is not USPTO) under a new preregistration. No option is taken in the result itself.

**Decided afterwards (Alex, 2026-10-20):** option (b), continue to Stage 1 with the narrowed claim. Option (c), the re-measurement, is deferred as a recorded to-do, not dropped; the frozen result above is unchanged.

## Files

`artifacts/report.txt` and `verdict.json` (the verdict), `draw.json` (the draw), `provenance.jsonl`, `planner_config.json`, `targets_r{1,2,3}.json`, and the raw per-target records as `results_r{1,2,3}.jsonl.gz` (gunzip them to rerun `run_quality.py report` or `diagnostics.py`). The 420 MB planner log is not kept.
