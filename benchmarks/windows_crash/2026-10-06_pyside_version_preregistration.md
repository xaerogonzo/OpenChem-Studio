# Pre-registration: does the early shard 1 crash depend on the PySide6 version?

**Committed to the pushed `crash-bisect` branch BEFORE the confirmation run is dispatched. Nothing here may change after the first leg reports.**

## What the exploratory rounds found (not a test, a reason for one)

Bisect rounds 1-6 (`windows-crash-rate.yml`, shard 1, one fresh process per attempt, no retry):

- The early shard 1 crash lives in files 15-19 of the shard, ending in `test_calculator_inspector_structure.py` (a test that builds a `QWebEngineView`); that file alone never crashes (0/60), with files 15-18 before it the window `15:20` crashes in about 14% of attempts (26 of 180 across three baseline rounds).
- GPU, GL and context-sharing settings do not change it (round 4: baseline 7/60; `--disable-gpu` 10/60, `--in-process-gpu` 8/60, `QT_OPENGL=software` 5/60, `AA_ShareOpenGLContexts` in the test `qapp` 9/60).
- A native minidump of one crash (same build as local PySide6 6.11.1, module timestamps and sizes match) shows a **null-pointer read in `shiboken6.abi3.dll`, inside `Shiboken::BindingManager::releaseWrapper(SbkObject*)`**, entered from a QtGui wrapper's C++ destructor under Qt event dispatch. A related upstream report (Qt forum, PySide6 6.10.2 and 6.11.1) describes a stale shiboken wrapper after the C++ object is freed; no fix or bug ID.
- Round 6, PySide6 versions on the same window, 60 attempts each: 6.11.1 (locked) 8/60, 6.11.2 6/60, 6.10.1 7/60, **6.9.3 0/60** (every attempt ran the whole window). Exploratory, three alternatives compared after the fact.

## Question

On the `15:20` window of shard 1, is the crash rate of PySide6 6.9.3 lower than that of the locked PySide6 6.11.1?

## Design (fixed now)

- **Code under test:** the commit of the `crash-bisect` branch that contains this file; the same tree and the same pinned shard for every arm. The only difference between arms is `OPENCHEM_PYSIDE_VERSION` (installs a matching PySide6 / PySide6-Essentials / PySide6-Addons / shiboken6 set; each leg logs the version it ran).
- **Primary arms:** `pyside-6.11.1-locked` (no override) and `pyside-6.9.3`.
- **Secondary arms, descriptive only, no test:** `pyside-6.10.0` and `pyside-6.11.0`, to place where the crash starts.
- **Sample size: 5 legs x 20 attempts = 100 attempts per arm, fixed now (400 in all).**
- **Dispatch:** `treatments` with `range` `15:20`, `replicas=5`, `attempts=20`, shard 1.
- **Primary outcome:** per arm, crashed / (crashed + failed + passed), by `tools/crash_rate.py`; ONE comparison (6.9.3 against locked), two-sided Fisher's exact test, alpha = 0.05. The secondary arms are not tested.
- **Decision rule.** p < 0.05 with 6.9.3 lower: the crash depends on the PySide6 version (record the rates and intervals). Anything else: inconclusive about version dependence, and the exploratory 0/60 is not relied on.
- **No extension.** The run is not extended, re-dispatched or pooled with another to move p. A different n is a new pre-registration.

## Accepted in advance

- Under 6.9.3 (and 6.10.1) two tests in `test_calculator_inspector_structure.py` (`test_highlight_follows_the_atom_index_and_survives_a_relayer`, `test_a_hover_label_comes_and_goes_without_taking_value_or_shape_labels`) fail deterministically in the exploratory run. Those attempts are "failed", which the tool counts in the denominator and not as crashes. They run after the test that crashes, so they cannot hide a crash in the crash test; they are a compatibility finding, not part of this question.
- A positive result says nothing yet about whether the full suite and the application are sound on 6.9.3. Changing the locked PySide6 is a separate decision for the maintainer, with its own full-suite check, and is not made by this run.
