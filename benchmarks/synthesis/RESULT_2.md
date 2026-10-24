# Synthesis planner quality benchmark, protocol 2: result

Run 2026-10-22 from commit `debbd941` (`src/` clean, one planner identity: AiZynthFinder 4.4.1, onnxruntime 1.31.0, numpy 1.26.4, rdkit 2023.9.6, pyarrow 20.0.0; configuration `artifacts_protocol2/planner_config.json`, MD5 `a061b395...`). 340 searches (300 targets, the first 20 stability targets twice more), started 00:10, last record 04:58, about 4.8 hours. The protocol, rule and thresholds are those of `PREREGISTRATION_2.md`, frozen before the first search; **nothing in them was changed after the result was seen.** The verdict is `run_quality_2.py report`'s; everything below it is reported and decides nothing.

## Verdict: protocol-2 GO (and protocol 1's PARTIAL stands as measured)

| Claim | Result | Bar | Verdict |
|---|---|---|---|
| A route was returned (solved with the set stock), of 300 | **0.967** (290) | PASS at 0.90 | **PASS** |
| The reference route is in the PaRoutes top-10 (**M1**), of 300 | **0.533** (160) | PASS 0.50, PARTIAL 0.35 | **PASS** |
| The first route is fully validated, of the 298 whose first route has a reaction | **0.993** (296) | PASS at 0.95 | **PASS** |
| The solved flag is identical across three runs, of 20 | **20 of 20** | PASS at 19 | **PASS** |

Evaluable: 0 of 300 failed, one commit, `src/` clean, one planner identity, and **|M3 - 0.373| = 0.034, inside the 0.05 tolerance** (M3 = 0.407), so the run reproduces protocol 1's behaviour closely enough to read the pool and the ranking. The preregistered reading of M1 at 10 (0.533, at least 0.50) is "the shortfall was protocol".

## The number any product wording must quote is M2, and it is 0.417

M1 counts every route in the first 10 score *levels*; routes of one shape and stock status tie, so a median of **37 routes (17% of a median pool of 291)** sit inside a PaRoutes "top-10". A person shown 10 routes sees M2: **0.417 (125 of 300)**, which is **below the 0.50 bar and above the 0.35 line**. The bars were set against an M1-type figure and the verdict is decided by M1, as approved; this is the awkward part and it is stated, not hidden: **by the user-facing count the planner would be PARTIAL again, at 0.417 instead of 0.373.**

The decomposition (each step changes one thing, recovered at 10):

| Step | Recovered | Change | What changed |
|---|---|---|---|
| Protocol 1 (planner's order, 5 to 25 routes returned) | 0.373 | | |
| M3: planner's own order over the full pool | 0.407 | **+0.034** | the pool (all solved routes, a median of 291 instead of 11) |
| M2: first 10 routes ranked by route score | 0.417 | **+0.010** | the ranking (3 more targets of 300) |
| M1: every route in the first 10 score levels | 0.533 | **+0.117** | tie-inclusion, i.e. counting 37 routes as "10" |
| Pool recall: the reference is anywhere in the returned routes | 0.547 | +0.014 over M1 | the ceiling for any ranking of this pool |

**So of the 0.160 between protocol 1 and M1, 0.117 (73%) is how "top-10" is counted, 0.034 (21%) is the pool and 0.010 (6%) is the ranking.** Ranking by the PaRoutes route score barely beats the planner's own order (125 hits against 122 of 300: 8 targets gained, 5 lost, so within the noise a rerun shows). What the shortfall "being protocol" means here is therefore mostly that the published figure and ours counted different things, not that a better ranking would find the reference.

| | k = 1 | k = 5 | k = 10 |
|---|---|---|---|
| M1 (PaRoutes count) | 0.193 | 0.500 | 0.533 |
| M2 (routes ranked by route score, first k routes) | 0.140 | 0.337 | 0.417 |
| M3 (planner's own order, first k routes) | 0.170 | 0.343 | 0.407 |
| Published, reference-excluding model, tree edit distance | 0.20 | 0.55 | 0.61 |

M1 sits 0.077 under the published 0.61 at 10 and close to it at 1 and 5, with a model that was probably trained on these references.

## What else was measured (reported, deciding nothing)

* **The ceiling is 0.547.** Even with every solved route returned (median 292, maximum 836), the reference is in the pool for only 55% of targets, 57% of those that were solved; 10 targets were unsolved. Ranking cannot get above this; the rest needs a different search or model.
* **Depth still decides it** (reference depth: targets; M1 / M2 / pool): depth 2: 80; **0.86 / 0.81 / 0.86**. Depth 3: 136; **0.54 / 0.39 / 0.55**. Depth 4: 50; **0.20 / 0.04 / 0.24**. Depth 5: 24; 0.21 / 0.12 / 0.25. Depth 6 or more: 10; 0.20 / 0.20 / 0.20. The solved fraction is 0.80 to 1.00 at every depth, as in protocol 1. At depth 2 protocol 1 already recovered 0.81, so there was little to gain; from depth 4 the reference is mostly not in a pool of hundreds of routes.
* **Score levels:** a median of 104 distinct score levels per target (maximum 313); the best matching route is at a median level of 2 for the targets that have a match.
* **Validity and shape:** 296 of 298 first routes fully validated (M2's first route; as in protocol 1); mean leaf overlap of the first route with the reference 0.619 (protocol 1: 0.60); the first route is shorter than the reference in 51% (protocol 1: 48%).
* **Cost:** median 42.7 s of search per target, peak working set 2.87 GB, 4.8 hours for 340 searches, raw records 714 MB for the main run (the planner log, as in protocol 1, is not kept).
* **Official metric** (`official_check.py`, route-distances 1.2.4 in its own environment, tree edit distance below 1e-6): **the same at 10**: M1 0.533, M2 0.417, M3 0.407 (exact rule and official distance agree to three decimals); at 5, M1 is 0.497 officially against 0.500 exactly; at 1 they agree. Of 14,129 routes compared, 3 matched by the official distance only and 1 by the exact rule only. The choice of matching rule does not move the result.

## Identity checks, honestly

* **Targets and stock:** the checksums of `targets_n1.txt` and `stock_n1.txt` are identical to protocol 1's records (`29425c56...`, `cfa7e97b...`).
* **The InChI-key stock** (`stock_n1_inchikeys.txt`, 13,432 keys, 13,414 distinct, 0 SMILES unread) could **not be compared byte for byte**: protocol 1 recorded no checksum of it and the file is no longer on disk, so `stock` printed no "identical" line and the report's check for it was skipped. What supports identity: the same source file (same MD5), the same generating script, and the same count of 13,414 distinct keys that protocol 1 recorded. It was not proved when this was written; see "The stock, checked afterwards" below.
* **The model files:** protocol 1 recorded no checksum; sizes agree with its records (91,518,243 and 3,313,598 bytes); the MD5s are recorded now (`b466a436...`, `e8fb29d4...`).
* **The draw** was copied from protocol 1 and reproduced from the seed.

## The stock, checked afterwards (2026-10-23)

`stock_identity.py` (a diagnostic of the saved records; it decides nothing and neither protocol's verdict moves) asked the question from what each search recorded, because the key file protocol 1 searched with was never kept. Every leaf of every returned route carries the stock's own `in_stock` flag, so the flags can be compared without deriving a key. Output: `artifacts_protocol2/stock_identity.txt`.

* **Same answer wherever both looked: 1,634 of 1,634.** Of the leaves both protocols recorded, 1,593 were in stock in both and 41 out of stock in both; none got different flags. No leaf got two flags inside one protocol.
* **Protocol 2 looked up far more** (10,504 distinct leaves against 1,659). The 8,870 only protocol 2 saw cannot be compared, and 25 of protocol 1's were never looked up by protocol 2 (one in stock).
* **The generating step is reproducible.** `make_stock.py` has had a single commit since it was written, the source `stock_n1.txt` has the MD5 protocol 1 recorded, and running the script again on it gives a key file with the committed one's MD5, `7c0b260ab7204fd375cd898fa4590ce0`.
* **What remains unknown:** the literal MD5 of protocol 1's key file. Nothing found disagrees with its being the same file, and the benchmark's two protocols agree on every stock answer both asked for.
* **A first attempt measured the wrong thing.** Deriving InChI keys here with RDKit and testing membership gave a few disagreements, all E-alkenes, and the same ones appeared against protocol 2's own records and its own key file. That is how the key was derived in the check, not a difference between stocks, and it is why the committed check compares flags and derives nothing.

## What this does and does not establish

* **Established, on these 300 seeded USPTO targets with the reference stock:** given every solved route the planner finds one that matches the patent route for 55% of them; the first 10 routes ranked by route score hold it for 42%; counted the PaRoutes way (every route in the first 10 score levels) 53%. Protocol 1's 0.373 was a pool and counting difference first, a ranking difference barely.
* **Not established:** anything about generalisation. This is the same public model, probably trained on these reference reactions, on targets that are no longer fresh; the contamination caveat of `PREREGISTRATION.md` applies in full. A GO here is not evidence that the planner finds known routes to molecules it has not seen. The protocol was chosen after seeing protocol 1's result (stated in the preregistration); one deciding measure was fixed in advance and **no further variant is run to chase a better number.**
* **Not the official metric,** though close to it (above). **Feasibility is not measured and is never reported.**
* **M1 is generous by construction.** It is the comparable number with the literature, not the user-facing one.

## Files

`artifacts_protocol2/`: `report.txt`, `verdict.json`, `table.json` (the per-target table), `draw.json`, `provenance.jsonl`, `planner_config.json`, `targets_r{1,2,3}.json`, and the raw records of the two repeat runs as `results_r{2,3}.jsonl.gz` (2.3 MB each). The raw main-run records (`results_r1.jsonl`, 714 MB; 38 MB gzipped) are **not committed** (too large for the repository to carry); they stay on the machine that ran it and `run_quality_2.py report` needs them to be re-run.

**Where they are, and how to restore them.** The gzipped copy is `D:\_scratch\synthesis_protocol2_records\results_r1.jsonl.gz`, with a second copy at `E:\My Area\Claude\OpenChem Studio\synthesis_protocol2_records\results_r1.jsonl.gz` (made 2026-10-23), both on the machine that ran the benchmark (37,769,150 bytes, MD5 `4d0f08e1666d43ea04c601e0a13f99b9`); it decompresses to `results_r1.jsonl` (714,459,914 bytes, MD5 `fa527fce9c489566b553b92ba272d4f9`), which goes into `artifacts_protocol2/` beside the committed files. Then `run_quality_2.py report`, `diagnostics`-style re-scoring and `stocked_rescore.py` run from the repository alone. The two repeat runs and the stock-key file are committed, so only this one file is not; if it is lost, the per-target `table.json`, `report.txt` and `verdict.json` still hold every figure above, and only a re-score from the routes themselves (not the verdict) would need a new run of about 4 hours. `stock_identity.txt` is the output of `stock_identity.py` (above), `stocked_rescore.txt` that of `stocked_rescore.py`, `official.txt` and `official.json` are the official-metric output, and `stock_n1_inchikeys.txt` (the InChI-key stock, 376 KB) is kept so that a later run can compare against it, which protocol 1 did not allow.

## Added after the result (2026-10-22)

Applying the result to the product (slice 3's ranking, `docs/SYNTHESIS_HELPER_DESIGN.md`, "Protocol 2 result", "Applied") found that **the routes the run returned with `all_routes` on are not only routes whose starting materials are all in stock**: in 281 of the solved targets some returned route had a starting material that is not in stock (a median 30% of the returned routes), and such routes took 90 of the 2,877 places in M2's first ten. The sentences above that say "every solved route" and give a pool of 291 routes count them, and the preregistration's "every solved route" was imprecise in the same way. The verdict is unchanged. `stocked_rescore.py` (a diagnostic of the saved records, deciding nothing) re-scores with only the routes whose every starting material is in stock, which is what the product keeps: **M2 is the same 125 of 300 (0.417), the pool recall the same 0.547 and M1 the same 0.533**, so the figures above hold for the list the product shows. Its output is `artifacts_protocol2/stocked_rescore.txt`.

## What it changes for the product and for slice 3

See `docs/SYNTHESIS_HELPER_DESIGN.md`, section "Protocol 2 result".
