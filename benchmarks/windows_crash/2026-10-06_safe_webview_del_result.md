# Result: destroying the web view before Python deletes the dialog does NOT remove the crash

[Run 37426187868](https://github.com/xaerogonzo/OpenChem-Studio/actions/runs/37426187868), shard 1, window `15:20`, locked PySide6 6.11.1, commit `8d0f42acfebba4658c75e2285859a1af0cbeb362` on branch `eventfilter-hardening` (**not merged**; it carries `openchem/ui/widgets/web_view_safety.py` and `CalculatorInspectorDialog.__del__`, behind `OPENCHEM_SAFE_WEBVIEW_DEL`). 5 legs x 20 attempts = 100 attempts per arm, one fresh process per attempt, no retry. Design, sample size, test and decision rule are in [`2026-10-06_safe_webview_del_preregistration.md`](2026-10-06_safe_webview_del_preregistration.md), committed before the run and unchanged.

## Pre-registered outcome

| arm | attempts | crashed | failed | passed | crash rate | 95% interval (Wilson) |
|---|---|---|---|---|---|---|
| baseline | 100 | 7 | 0 | 93 | 7% | 3% to 14% |
| safe-del (`OPENCHEM_SAFE_WEBVIEW_DEL=1`) | 100 | 15 | 0 | 85 | 15% | 9% to 23% |

**Fisher's exact p = 0.112** (7/100 against 15/100), two-sided, one comparison.

**Verdict by the pre-registered rule: INCONCLUSIVE, and not in the hoped-for direction.** The rule required p < 0.05 with `safe-del` lower; `safe-del` is nominally HIGHER. The switch is not turned on, and the change is not merged.

## Where the crashes were (descriptive)

Identical in both arms: every crash at 79% of the window (the last file, `test_calculator_inspector_structure.py`); 3 of the baseline's 7 and 4 of safe-del's 15 name `test_calculator_inspector_structure.py:131 test_3d_labels_go_on_heavy_atoms_only_and_every_value_reaches_hover`, the others show only pytest frames. Running the safe teardown moved nothing.

## What this rules out, and what it does not

- It does **not** support the hypothesis that the crash is the refcount-death of a parentless `CalculatorInspectorDialog` with a still-loading `QWebEngineView`, destroyed as a child inside the dialog's destructor. If that were the mechanism, destroying the view first should have lowered the rate; it did not.
- It does not say the safe order is wrong: the baseline's 7/100 is lower than the 26/180 (14%) seen in earlier rounds of this window, so the baseline itself moved (all baselines for this window now: 33 of 280, 12%), and 15 against 7 is within what that spread allows. Nothing here shows `safe-del` makes it worse.
- It does not show the `__del__` fired on CI. The unit tests show the order it produces (view first, then owner) when it does; no log line was added to prove it ran inside the crashing test.
- The frame evidence still points at the moment the discarded `_inspect(...)` return value (the dialog) is released, but what is destroyed there beyond the web view is not narrowed: the dialog also owns a `QStandardItemModel` with a `QStandardItem` per atom (non-QObject wrappers, the type in the upstream stale-wrapper report), the 2D and 3D panes, and Python-side filters. Reading the code found nothing stale held by Python.

## A local reproduction was tried and failed

A script building and discarding the same dialog (the crashing test's own helpers, the 3D backend stubbed as the test does, return value discarded, `processEvents()` between iterations) ran **3000 iterations without a crash** on the development machine (a desktop with a GPU). This agrees with the long-standing observation that the crash only shows on the CI runner, and it means no local fast loop exists yet for this one.

## State of the whole chase

| question | answer |
|---|---|
| where does the early shard 1 crash happen | window `15:20`, the last file; about 12% of attempts (33 of 280) |
| what is the native fault | null read in `shiboken6` `BindingManager::releaseWrapper` |
| does it depend on the PySide6 version | yes in this window (6.9.3 1/100, locked 8/100, p = 0.035), but 6.9.3 crashes more across whole shards, so a downgrade is not a fix |
| GPU / GL / context-sharing | no effect |
| destroying the dialog's web view first | no effect (this record) |
| cause | **not identified** |

Candidates not yet tested, none favoured by evidence: stale non-QObject (`QStandardItem`) wrappers during the dialog's teardown; the interaction with garbage collection at the end of the test; the Python `eventFilter` overrides (first-line crashes on 6.9.3).
