# Full-suite check on PySide6 6.9.3: it is worse, not better

Runs [37413274014](https://github.com/xaerogonzo/OpenChem-Studio/actions/runs/37413274014) (shard 1) and [37413296616](https://github.com/xaerogonzo/OpenChem-Studio/actions/runs/37413296616) (shard 2), commit `9a67a16f76f279837aa8fb3173171d62500c2dcc`, whole shards (no window), one attempt per leg, no retry, 4 legs per arm. The arms differ only by `OPENCHEM_PYSIDE_VERSION` (the locked PySide6 6.11.1 against 6.9.3).

**Exploratory, and small (4 legs per arm per shard).** It was run to answer "is the suite sound on 6.9.3, so that a downgrade is a fix?", not to estimate a rate; it was not pre-registered and its p-values are descriptive. The answer does not need more than this.

## Result

| shard | arm | legs | crashed | failed | passed |
|---|---|---|---|---|---|
| 1 | locked 6.11.1 | 4 | 2 | 0 | 2 |
| 1 | **6.9.3** | 4 | **4** | 0 | 0 |
| 2 | locked 6.11.1 | 4 | 0 | 0 | 4 |
| 2 | **6.9.3** | 4 | **4** | 0 | 0 |

6.9.3 crashed in **8 of 8** whole-shard legs; the locked version crashed in 2 of 8. Fisher's exact (descriptive): shard 1 p = 0.43, shard 2 p = 0.029, the two shards pooled (2/8 against 8/8) p = 0.007.

## Where the crashes were

6.9.3 does not crash in the window where 6.10+ does (`15:20`, 1/100); it crashes **elsewhere**, and consistently:

- Shard 1, 46-49% of the run, three of four legs inside the application's own `eventFilter` overrides: `scroll_safe.py:37 eventFilter <- test_main_window_conformers.py:36 _drain` (2 legs), `mol3d_viewer_backend.py:148 eventFilter <- conftest.py:350 dispose_web_engine_views` (2 legs).
- Shard 2, **81% of the run in 3 of 4 legs, the same place** (`mol3d_viewer_backend.py:148` / `scroll_safe.py:37 eventFilter <- test_result_persistence.py:50 _drain <- test_result_persistence.py:474 _select`), and one at 0% (`test_atom_menu_changes.py:133`).
- The locked version's two shard 1 crashes were at 4% (`conftest.dispose <- test_batch_detail_dialog.py:265`, the known one) and 19% (`quantum_chemistry_panel.py:963 _build_controls <- main_window.py:466`, in MainWindow construction).

No leg of either arm finished with a test failure: every 6.9.3 leg crashed before the end, so this run cannot say whether the two known compatibility failures are the only ones.

## What this means

- **Downgrading to 6.9.3 is not a fix.** It trades a ~14% crash on one window for a crash in every whole-shard attempt, at other places.
- The pre-registered window result stands as stated (6.10+ crashes in `15:20`, 6.9.3 does not), but "the crash is a PySide6 6.10 regression" is too narrow: the suite crashes in several places on every version tried.
- **The 6.9.3 crash sites are the first line of the app's `eventFilter` overrides** (`event.type()` / `watched.hasFocus()`), which Qt calls for every event on a watched widget. That is the same family as the upstream report (a stale or invalid shiboken wrapper handed back during event dispatch while widgets are being destroyed), seen at a different site and far more often on this version. This is a reading of the frames, not a demonstrated cause.
- It points at what is controllable in this repository: Python event-filter overrides and teardown ordering around widgets that own web views, rather than the library version.

The locked version is unchanged. No upstream report has been filed.
