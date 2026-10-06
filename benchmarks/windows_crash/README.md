# Windows suite crash measurements

The Windows suite shards die with an access violation and no failed test. The crash cannot be reproduced locally, so the only way to learn whether a change to it did anything is to sample CI under controlled conditions: `.github/workflows/windows-crash-rate.yml` (manual dispatch) runs one shard N times per arm, once each with no retry, and `tools/crash_rate.py` reports crashed / failed / passed per arm with a Wilson interval and, for two arms, Fisher's exact p. The control arm is the SAME tree with named commits reverted, so both arms run the same files in the same pinned shard (`tools/suite-shard-pins.json`).

A leg is **crashed** if the process died with no test reported FAILED/ERROR (a fatal exception and no summary, or a clean summary and a non-zero exit); **failed** if pytest finished and reported a real failure (not a crash, reported but not counted); **passed** otherwise.

## Records

| file | question | verdict |
|---|---|---|
| [`2026-10-05_shard1_dispose_fix.md`](2026-10-05_shard1_dispose_fix.md) | does #197 (the `conftest.dispose` web-view teardown) change the crash rate? (shard 1) | **inconclusive, and the wrong shard for the question**: 4/10 crashed as-is against 6/10 reverted, Fisher p = 0.656 |
| [`2026-10-05_shard2_dispose_fix.md`](2026-10-05_shard2_dispose_fix.md) | does #197 change the crash rate on the shard it targeted? (shard 2, pre-registered, n=15 per arm) | **inconclusive by the registered rule**: 0/15 crashed as-is, 2/15 reverted (one at the fix's own target), Fisher p = 0.483 |

Run 1 is [37383273300](https://github.com/xaerogonzo/OpenChem-Studio/actions/runs/37383273300) (shard 1, master at 7996caa1, 10 legs per arm, `revert=655abcc9`). Four things worth keeping from it:

- **#197 targeted shard 2**, where the last four classified crashes died at about 82% in `test_result_presentation.py`. Run 1 sampled shard 1 only, so it cannot speak to the fix's own target.
- **All 10 crashes in run 1 were at 4-8% of shard 1** (about 80 s in); 8 of them show no frame outside pytest. That early crash happens in roughly half of shard 1 legs with or without #197 and is not explained.
- The 2 reverted-arm crashes that did show a frame were at `conftest.dispose` and in `test_calculator_inspector_structure.py` (2 against 0 in the as-is arm, Fisher p about 0.47: suggestive only).
- The 4 "failed" reverted legs are an artifact of the control arm, not crashes: reverting the code but keeping the docs makes two docs-guard tests fail (a doc cites the removed `tests/test_dispose_helper.py`). The other 6571 tests passed.

The first dispatch of this workflow (run 37356155136) is NOT pooled with run 1: its control arm never ran (a docs conflict in the revert) and its as-is arm was a pilot. Its as-is arm read 3 of 10 crashed (2 early, 1 at exit).

## Pre-registration: run 2, does #197 change the crash rate on the shard it targeted?

**Written and committed BEFORE the run is dispatched.** Nothing below may be changed after the first leg reports.

- **Question.** On shard 2, where #197's target crash occurred, is the crash rate of master lower than the same tree with #197 reverted?
- **Arms.** `as-is` = master at the commit that contains this file; `reverted` = the same tree with `655abcc9` reverted (prose conflicts keep current text).
- **Dispatch.** `gh workflow run windows-crash-rate.yml -f ref=master -f shard=2 -f replicas=15 -f revert=655abcc9`
- **Sample size: 15 legs per arm, 30 legs, fixed now.** (Run 1's early crash rate on shard 1 was 40-60%; shard 2's rate is unknown, which is why n is larger than run 1's 10.)
- **Primary outcome.** Per arm, crashed / (crashed + failed + passed), by `tools/crash_rate.py`; one comparison, two-sided Fisher's exact test, alpha = 0.05.
- **Secondary, descriptive only, no test:** where each crash happened (progress percentage and top frame), and how many sit at the `conftest.dispose` / web-view destructor frame #197 targets.
- **Decision rule.** p < 0.05 with the as-is rate lower: the fix is effective on its target (record the rate difference and interval). Anything else: **inconclusive**; it does NOT show the fix is useless, only that a difference this size was not detectable at n=15. A reverted arm lower than as-is would be reported as such.
- **No extension.** The run is not extended, re-dispatched or pooled with another run to move p across the line. A follow-up with a different n is a new pre-registration.
- **Known artifact, accepted in advance:** the reverted arm may show "failed" legs from the two docs-guard tests named above if they fall in shard 2; they are not crashes and are reported as failed.

The Known-TODOs item for the dispose fix closes when run 2's report is committed here.

### Amendment, before any leg reported

The first dispatch of run 2 (run 37395570244, from `4d119fc6`) was cancelled within minutes, **before any leg had reported a result**, because the revert step would have failed in every reverted leg: reverting `655abcc9` conflicts in `tests/test_docs_are_current.py` (the docs guard, which the pre-registration commit also edited), and the step treated every conflict under `tests/` as fatal. The conflict rule is now an allow-list of PROSE (`docs/`, `CHANGELOG.md`, `tests/test_docs_are_current.py`); any other conflict still stops the leg. Nothing else in the design above changes: same shard, arms, n, outcome, test and decision rule. The run is dispatched from the commit that contains this amendment (its SHA is recorded in the report), not from `4d119fc6`.
