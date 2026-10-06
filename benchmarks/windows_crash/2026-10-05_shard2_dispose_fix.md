# Run 2: does #197 change the crash rate on shard 2?

[Run 37395773485](https://github.com/xaerogonzo/OpenChem-Studio/actions/runs/37395773485), shard 2, commit `3c549bd9066d5c0e277add94798b1c7b40b65e3c` (the pre-registered design plus its amendment, see the README), 15 legs per arm, `revert=655abcc9`. Design, sample size, test and decision rule were committed before the run and are unchanged.

## Pre-registered outcome

| arm | legs | crashed | failed | passed | crash rate | 95% interval (Wilson) | missing |
|---|---|---|---|---|---|---|---|
| as-is | 15 | 0 | 0 | 15 | 0% | 0% to 20% | 0 |
| reverted | 15 | 2 | 13 | 0 | 13% | 4% to 38% | 0 |

**as-is vs reverted: Fisher's exact p = 0.483** (0/15 against 2/15 crashed).

**Verdict by the pre-registered rule: INCONCLUSIVE.** p is not below 0.05. That means a difference of this size was not detectable at n = 15, not that the fix does nothing. It is also not evidence that it works.

## Secondary, descriptive (no test, as registered)

Where the two crashes were, both in the reverted arm:

- reverted #15: shard 2 at **82%**, `conftest.py:206 dispose <- test_result_presentation.py:65 _dispose <- test_result_presentation.py:436`. **This is the crash #197 was written for**, at the test and depth it was classified from (`test_result_presentation.py`, 82-83%, a `CalculatorInspectorDialog` disposed while its web view was loading).
- reverted #8: shard 2 at 2%, `conftest.py:206 dispose <- test_batch_panel.py:68 widgets`: also a `dispose` frame.

The as-is arm had **no crash of any kind in 15 shard 2 legs** (upper bound 20%); both crashes in the arm without the fix are at the `conftest.dispose` frame the fix changes. That pattern is what #197 predicts, and it is two events: the registered test does not reach significance and this is not presented as if it did.

## The reverted arm's 13 "failed" legs are an artifact, and not the one the pre-registration named

The pre-registration expected the docs-guard tests to fail in the reverted arm. They did not (they are in shard 1). **All 13 non-crashed reverted legs failed exactly one test, `tests/test_suite_shards.py::test_adding_a_test_file_moves_no_other_file`**, and no as-is leg failed anything. The reverted tree has one fewer test file (`test_dispose_helper.py` is deleted), which moved an unpinned file in that test's simulation. The other 7300 tests passed in each of those legs, so none of them is a crash and the crash rate is unaffected; the 13 are reported as "failed" as the tool defines it.

That failure exposed a real flaw in the guard itself, not in the crash: the test asserted that no existing file moves when files are added, but only PINNED files are guaranteed not to (8 test files were unpinned at the time). It passed on master by luck of the current unpinned set. Fixed separately.

## What this run does and does not establish

- It establishes that, on shard 2 at this commit, the fixed tree crashed 0 of 15 times and that the tree with the fix removed crashed 2 of 15, one of them at the exact target of the fix. With p = 0.48 that is not a finding.
- It does not show the fix is ineffective, and it does not show it is effective. A larger pre-registered run would be needed to settle a difference of this size; none is planned, because the fix is targeted, tested and harmless to keep.
- Together with run 1 (shard 1) it shows the larger, unrelated problem: about half of shard 1's legs crash at 4-8% of the run with no test frame, which #197 does not touch and which no run here explains.
