# Confirmation: the early shard 1 crash depends on the PySide6 version

[Run 37411184284](https://github.com/xaerogonzo/OpenChem-Studio/actions/runs/37411184284), shard 1, window `15:20` (batch_service, bbb_stereo, binarycif, bond_order_keys, calculator_inspector_structure), commit `9be029590e9feb06612e387428b782503b100a4e`, 5 legs x 20 attempts = 100 attempts per arm, one fresh process per attempt, no retry. Design, sample size, test and decision rule are in [`2026-10-06_pyside_version_preregistration.md`](2026-10-06_pyside_version_preregistration.md), committed before the run.

## Pre-registered outcome

| arm | attempts | crashed | failed | passed | crash rate | 95% interval (Wilson) |
|---|---|---|---|---|---|---|
| pyside-6.9.3 | 100 | 1 | 99 | 0 | 1% | 0% to 5% |
| pyside-6.11.1-locked | 100 | 8 | 0 | 92 | 8% | 4% to 15% |
| *pyside-6.10.0 (secondary)* | 100 | 8 | 92 | 0 | 8% | 4% to 15% |
| *pyside-6.11.0 (secondary)* | 100 | 11 | 0 | 89 | 11% | 6% to 19% |

**6.9.3 (1/100) against locked 6.11.1 (8/100): Fisher's exact p = 0.0349, two-sided, one comparison.**

**Verdict by the pre-registered rule: p < 0.05 with 6.9.3 lower, so the crash depends on the PySide6 version.** It is only just under the line, from a single comparison, and the earlier exploratory 0/60 for 6.9.3 (round 6) is not counted toward it.

## Secondary, descriptive (no test, as registered)

- The crash is present from PySide6 **6.10.0** onward (8, 8, 8 and 11 per 100 for 6.10.0, 6.11.1 and 6.11.0; 6/60 and 7/60 for 6.11.2 and 6.10.1 in round 6) and essentially absent in 6.9.3. That places the start at 6.10.0, which is the same range as the upstream report (6.10.2 and 6.11.1).
- The single 6.9.3 crash is **not the same crash**: its frames are `src/openchem/events/base.py:124 publish <- descriptor_service.py:122 run <- mol3d_viewer_backend.py:148 eventFilter`, in application code, where every other crash in this window shows no frame outside pytest or `test_calculator_inspector_structure.py:131`. One event; it may be an unrelated flake.
- "Failed" for 6.9.3 and 6.10.0 is the two compatibility failures named in the pre-registration (`test_highlight_follows_the_atom_index_and_survives_a_relayer`, `test_a_hover_label_comes_and_goes_without_taking_value_or_shape_labels`); they run after the crash test, are not crashes, and say nothing about the question.

## What the exploratory rounds established (not tests)

1. The crash lives in files 15-19 of shard 1 and needs `test_calculator_inspector_structure.py`, which builds a `QWebEngineView` in a test, to run after files 15-18 (alone 0/60; `15:20` about 14%, 26 of 180 across three baseline rounds; `15:19` without that file 0/60).
2. GPU, GL and context-sharing settings do not change it (round 4: baseline 7/60; `--disable-gpu` 10/60, `--in-process-gpu` 8/60, `QT_OPENGL=software` 5/60, `AA_ShareOpenGLContexts` in the test `qapp` 9/60).
3. A native minidump of one crash (the module timestamps and sizes match the locally installed PySide6 6.11.1 exactly) shows a **null-pointer read in `shiboken6.abi3.dll` inside `Shiboken::BindingManager::releaseWrapper(SbkObject*)`** (about 0x90 bytes in, nearest-export attribution), entered from a QtGui wrapper's C++ destructor under Qt event dispatch. Not WebEngine, not the GPU. Windows Error Reporting kept only one of about 15 crashes' dumps.
4. A Qt forum report describes a related stale-wrapper null read in PySide6 6.10.2 and 6.11.1 (stale shiboken wrapper after the C++ object is freed, address reuse, re-entrant widget destruction with a QtWebEngine compositor active), with no fix, workaround or bug ID. Same family; function differs (`retrieveMetaObject` there).

## What this does and does not establish

- It establishes that the crash is tied to the PySide6/shiboken version in the 6.10+ line and not to this project's WebEngine, GPU or driver configuration.
- It does **not** show that the project and its full suite are sound on 6.9.3, and it does not touch the locked version. **The follow-up whole-suite check found 6.9.3 is worse** (8 of 8 whole-shard legs crashed, at other places): see [`2026-10-06_pyside_693_full_suite.md`](2026-10-06_pyside_693_full_suite.md). Changing the lock, or filing an upstream report, are separate decisions for the maintainer.
