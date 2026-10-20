# Synthesis planner quality benchmark: preregistration

Written 2026-10-19, **before any job of the benchmark was run** (what was run, and seen, is listed under "What was seen first"). Design, the spike's measurements and the reading behind it: `docs/SYNTHESIS_HELPER_DESIGN.md`. The rule is the code in `judge.py`, the matching is `route_match.py` and the route checks are `route_validator.py`, all tested by `tests/test_synthesis_benchmark.py` and `tests/test_synthesis_route_validator.py` before any run; where this text and that code disagree, the disagreement is fixed before the run, never after. **Status: frozen on commit of this file with its runner** (`run_quality.py` and `plan_batch.py` are written, tested and committed together with it and before the first job; this file changes only by an amendment section that says what and why).

## The question

Does AiZynthFinder 4.4.1, installed as a user would install it and run as a stated protocol, return routes that are **valid, stable, and include known patent routes**, on the PaRoutes 2.0 benchmark [source:genheden2022paroutes], at rates consistent with the literature? Measured, not shipped: **if the gate fails, no integration is built, and the failure and its reason are the deliverable.** Four claims, each judged separately; **the feasibility of a route is not a claim this benchmark makes and is never reported.**

## The data (fixed before any run)

PaRoutes 2.0, Zenodo record 7341155 (CC-BY-4.0 as the record states) [source:zenodo7341155], downloaded 2026-10-19, MD5 checked against the record: `targets_n1.txt` (10,000 targets), `stock_n1.txt` (13,432 SMILES; the paper states 13,633, **the file is what is used**), `ref_routes_n1.json` (10,000 reference routes, 31,785 reactions; `ref_routes_n1[i]` is the route of `targets_n1.txt` line `i`, verified).
**The stock is the set's own stock, the leaves of the reference routes**, as the paper prescribes (a ZINC-sized stock "could mask subtle differences" and its snapshot is arbitrary). The planner reads it as InChI keys it computes itself (`make_stock.py`): 13,432 SMILES become **13,414 distinct keys**, so 18 pairs of reference leaves are one stock entry to the planner; stated, not corrected.
**The target draw (fixed): 300 indices drawn without replacement with `random.Random(20261019).sample` from the 9,997 indices that remain after excluding indices 0, 1 and 2 (the three the spike saw); the first 20 drawn are the stability targets.** The draw is random, not the head of the file, because the file is ordered by the paper's greedy most-diverse selection, so its first entries are the most atypical (indices 0 to 2 have reference routes 8, 8 and 9 reactions deep, against a median of 3 in the set and 1% deeper than 6).

## The protocol (everything here is fixed)

**Planner and models:** the environment of `planner_env_lock.txt` (Python 3.12, aizynthfinder 4.4.1, onnxruntime 1.31.0, numpy 1.26.4, rdkit 2023.9.6, **`pyarrow` pinned below 21, without which the install does not import**), the public ONNX USPTO expansion policy and its template file as `download_public_data` installs them (`uspto_model.onnx`, `uspto_templates.csv.gz`) [source:zenodo7797465]. **No filter policy**, the configuration the published numbers describe (the three spike targets solved or failed identically with and without it).
**Search:** MCTS, `iteration_limit` **500**, `time_limit` 1,800 s as a safety net only (the budget is the iteration limit, because no seed exists and a time budget varies with load), `max_transforms` **10** (the set's reference routes are at most 10 reactions deep; the planner's default of 6 would make 1% of the references unreachable by construction), `return_first` false. One warm process per run; the configuration is passed as a UTF-8 dictionary.
**Runs:** `r1` over all 300 targets; `r2` and `r3` repeat the 20 stability targets with identical configuration. Every record carries the limits, the planner's identity (versions, configuration hash, selection) and the seconds and peak memory.
**What a route is, for every rule below:** the order the planner returned them in (`build_routes` with its defaults, never re-ranked here).

## The measures (the matching is `route_match.py`)

* **Solved:** the planner's own `is_solved` (every precursor of some route is in the set stock).
* **Recovered at k:** the reference route is among the first k returned. A predicted route **matches** the reference when its **set of reaction identities equals the reference's**; a reaction's identity is `(canonical product, sorted canonical precursors)` from the tree's parent and child nodes, stereo kept, atom maps absent (this does not depend on how either side wrote the reaction string, and it is stricter than the paper's tree edit distance, which gives credit for similar routes).
* **Valid:** the first returned route passes the route validator's outcomes 1 to 4 (molecules parse; reactions parse and their sides are the nodes they connect; mapping complete; atom conservation passes where assessable). A route whose conservation is not assessable is not valid and is not counted as invalid; it is simply not `fully_validated`.
* **Stable:** across the three runs of a stability target the solved flag is identical.

## The reading rule, fixed now (the code is `judge.py`)

On the 300 targets (a target that FAILED, meaning the planner crashed, timed out or returned nothing readable, counts as a miss):

| Claim | PASS | PARTIAL | NO-GO |
|---|---|---|---|
| **Solved** (of 300) | at least 0.90 | 0.80 to below 0.90 | below 0.80 |
| **Reference route in the first 10** (of 300) | at least 0.50 | 0.35 to below 0.50 | below 0.35 |
| **First route valid** (of the targets whose first route has a reaction) | at least 0.95 | 0.80 to below 0.95 | below 0.80 |
| **Solved flag stable** (of the 20) | at least 19 | 17 or 18 | 16 or fewer |

**Overall: GO needs all four to PASS; any NO-GO is NO-GO; otherwise PARTIAL. NOT EVALUABLE** if more than 5% of the 300 targets FAILED, if fewer than 100 targets have a first route with a reaction, or if fewer than 20 stability targets have all three runs. The first three PASS bars and the two lower bounds of the first two rows were approved by Alex on 2026-10-19; **the PARTIAL and NO-GO bars of the last two rows, the 5% failure allowance and the 100-target floor complete that approval and are stated here for amendment if Alex wants them different.**
**Where the thresholds come from:** the PaRoutes paper's own MCTS result on set-n1 (9,714 of 10,000 solved, top-1 0.20, top-5 0.55 and top-10 0.61 by tree edit distance, 500 iterations, **a one-step model that excludes the reference reactions**); the margin below the published 0.971 for a different model, a text stock and a Windows build; 0.50 sits 0.11 below the published 0.61 because the exact-match rule is stricter; the validity and stability bars are what the spike's 60 of 60 valid routes and stable solved flag already show.

## What the recovery number can and cannot say (the contamination caveat, decided now)

The paper states that a one-step model trained on the whole USPTO set, reference reactions included, is biased ("literature-lookup") [source:genheden2022paroutes]. **The public ONNX models are described only as "USPTO models"; no record says the reference reactions were excluded** [source:zenodo7797465], so they are probably in that class. Therefore: a high recovery **is not evidence that the planner generalises** to molecules it has not seen, only that it reproduces patent routes; a recovery **below** the published 0.61 is a red flag; and the claim a GO supports is **"returns valid routes that include known patent routes at a literature-consistent rate"**, never "proposes feasible routes for new targets". Every report carries this sentence.

## What each verdict does (decided now)

* **GO:** Stage 1 of `docs/SYNTHESIS_HELPER_DESIGN.md` may be built, with the claims above stated in the product's own words, the planner's installation shown with its size (about 1.7 GB on disk, up to 5.3 GB of memory with the ZINC stock), and the contamination caveat in the user guide.
* **PARTIAL:** the failing claims are named; nothing is built; whether to continue (for example with the uncontaminated Keras model, or a non-USPTO reference set) is Alex's decision, made with the report.
* **NO-GO:** nothing is built; the report and the reason are the deliverable and the next candidate (Syntheseus or an in-house template planner) is named.
* **NOT EVALUABLE:** nothing is claimed; the cause is fixed (a failure pattern usually names a protocol defect) and the benchmark re-run under a new preregistration.
* A result outside the thresholds is never explained away by hand: the diagnostics say what they can and the verdict stands.

## Reported, and in no rule

Recovered at 1, 5 and 10; the mean leaf overlap of the first route with the reference (the paper's measure; they report 0.63 to 0.68); the fraction whose first route is shorter than the reference (the paper's roughly 0.45); targets with a first route that has a reaction and how many validate; seconds per target and the peak working set; the number of routes returned; and the run-to-run spread of route count and first-solution time on the stability targets (the noise floor).

## What was seen first (disclosure)

* **The spike (`docs/SYNTHESIS_HELPER_DESIGN.md` 0b to 0d), on non-benchmark targets:** seven drug-like molecules (aspirin, paracetamol, ibuprofen and its (S) form, caffeine, sildenafil, strychnine) at 100 iterations with the ZINC stock and the filter: their routes are the validator's fixtures. Racemic ibuprofen was repeated four times and (S)-ibuprofen three times to see the run-to-run spread.
* **Benchmark targets 0, 1 and 2** (the first three lines of `targets_n1.txt`) were run once with the set stock at 500 iterations, with and without the filter, and once more at 30 iterations as a format check: targets 0 and 1 unsolved and 2 solved in both configurations (peak memory about 0.8 to 0.9 GB with this stock). **They are excluded from the draw for that reason.** The stock-conversion count (13,432 to 13,414 keys) and the file-order observation were made then.
* The PaRoutes paper's numbers and the AiZynthFinder paper's were read before this file (above). **No other benchmark target has been searched.**

## What it cannot say

* **Nothing about feasibility, yields, conditions or selectivity:** the planner gives none, and the reference routes are patent routes.
* **Nothing about targets unlike USPTO chemistry,** and, for the recovery claim, nothing about generalisation (above).
* **One planner version, one policy, one search algorithm, one stock.** A different stock (ZINC, a commercial catalogue) changes what is solved; the spike's own ZINC runs are not part of the decision.
* **A set-n1 sample of 300 of 10,000 targets**, seeded: the fractions carry the usual sampling error of a sample this size (about plus or minus 0.03 at 0.9).
* **The first route only for validity**, and the planner's ranking only for recovery.

## Records and refusals

Records are `artifacts/results_r{1,2,3}.jsonl` (one line per target and run) and `artifacts/provenance.jsonl` (the commit, whether `src/` was dirty, the configuration's and the inputs' MD5s per invocation). **A report is refused (NOT EVALUABLE) for records from more than one commit, made with a dirty `src/`, or carrying more than one planner identity.** A search that does not finish within 1,800 s, or a target the planner cannot read, is a failed record, never a pass. The run is one stage at a time (`draw`, `stock`, `run`, `report`) and resumes. **Expected cost: about 340 searches (300 plus 40 repeats) at 25 to 35 s of search each in one warm process per run, so roughly three hours of one machine's CPU and under 1 GB of memory with this stock**; it is not run while another long job is using the machine, and not until Alex says so.
