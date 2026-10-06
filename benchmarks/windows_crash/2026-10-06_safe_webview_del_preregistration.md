# Pre-registration: does destroying a dialog's web view before Python deletes the dialog remove the early shard 1 crash?

**Committed to the pushed branch BEFORE the run is dispatched. Nothing here may change after the first leg reports.**

## Why this is the hypothesis

From the crash records in this directory:

- The early shard 1 crash is a null read in `shiboken6`'s `BindingManager::releaseWrapper`, on the locked PySide6 6.11.1, in the window `15:20` (about 14% of attempts, 26 of 180 across three baseline rounds; 0/60 for the crash file alone).
- Its faulthandler traceback has no `src/` frame and, in the crashes that show one, names `test_calculator_inspector_structure.py:131`, which is `_inspect(engine, molecule, result, qapp)` with its return value **discarded**. The remaining crashes show only pytest's own frames, which is where Python frees a test function's locals as it returns.
- `_inspect` builds a **parentless** `CalculatorInspectorDialog` holding a `QWebEngineView` (the 3D pane). A parentless widget is owned by its Python wrapper, so when the last reference goes (the discarded return value, or the test's locals) Python deletes the C++ dialog at once, **web view inside it, as a child, inside the dialog's destructor**. That is the order #197 found unsafe for `conftest.dispose` (stop, delete and flush the view first). The conftest's autouse web-view fixture runs after the test, too late for a dialog that died during it.

So the hypothesis is that the crash is the refcount-death of a dialog with a still-loading web view, and that running the safe order from the dialog's `__del__` (before Python deletes the C++ object) removes it.

## The change (the only difference between arms)

`CalculatorInspectorDialog.__del__` calls `safe_teardown_on_delete(self)` (new `openchem/ui/widgets/web_view_safety.py`), which runs `destroy_web_views_first(widget)` when the environment variable `OPENCHEM_SAFE_WEBVIEW_DEL=1`. One commit, one env var, two arms. A unit test shows the order (view destroyed before owner with the switch on; owner first, then view, with it off) so the change does what it says; whether it removes the crash is what this run decides.

## Design (fixed now)

- **Window and version:** shard 1, files `15:20` (batch_service, bbb_stereo, binarycif, bond_order_keys, calculator_inspector_structure), locked PySide6 6.11.1, the same tree and pinned shard for both arms.
- **Arms:** `baseline` (no override) and `safe-del` (`OPENCHEM_SAFE_WEBVIEW_DEL=1`).
- **Sample size: 5 legs x 20 attempts = 100 attempts per arm, fixed now.** One fresh process per attempt, no retry.
- **Primary outcome:** per arm, crashed / (crashed + failed + passed) by `tools/crash_rate.py`; ONE comparison, two-sided Fisher's exact test, alpha = 0.05.
- **Decision rule:** p < 0.05 with `safe-del` lower: the crash is the refcount-death of a dialog with a web view, and the fix is supported on this window (record rates and intervals). Anything else: inconclusive, and the switch is not turned on. A `failed` outcome (a test failure) is reported and is not a crash.
- **No extension:** the run is not extended, re-dispatched or pooled to move p.

## Accepted in advance

- A positive result is about THIS window. Whether it removes the crash across whole shards, and whether the 6.9.3-style event-filter crashes are the same mechanism, are separate questions with their own runs.
- The other test files that build `CalculatorInspectorDialog` (batch detail, compare window, result presentation, calculator inspector dialog) are covered by the same `__del__`, but are not this window.
- If the effect is real, the switch becomes unconditional in a follow-up commit; this run does not change the default.
