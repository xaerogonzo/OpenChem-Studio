# Performance and memory census

Measured 2026-10-07, on Alex's machine (Windows 11, 28 logical CPUs), commit range `db3c6fba`..HEAD of
branch `claude/suite-performance-survey-02e0e7`. **Scope: the running application.** Test-suite speed is
covered by `tools/suite-durations.json` and the CI notes. **This is a survey: nothing was fixed.**

The question was why the app feels heavy and whether anything leaks or burns CPU. The short answer:
**the measured cost is mostly structural (what a launch always builds), not a leak.** Every leak
hypothesis that survived re-measurement was ruled out; two apparent leaks did not reproduce and are
recorded as such below.

## What a launch costs (S1, 3 runs, sampler only)

| Metric | Result |
|---|---|
| Window shown ("window ready") | 3.2, 9.6, 3.0 s from process start (the 9.6 s run had system CPU 17.6% vs 24.3% and 19.5%, so it was not a busier machine: unexplained) |
| App process, private bytes at idle | ~1,080 MiB, flat over 5 minutes (delta -0.5, -0.6, +12.8 MiB) |
| of which child processes | ~550 MiB (4 `QtWebEngineProcess`, ~375 + 118 + 20 + 19 MiB) |
| Threads / handles (app) | 175-179 / ~2,740 |
| Live widgets after startup | ~1,520 (186 `QScrollBar`, 160 `QLabel`, 116 `QPushButton`, 63 `_FactRow`, ...) |
| `QWebEngineView`s alive at idle | **4** (Ketcher 2D, 3Dmol, Mol*, one more), created at startup |
| Idle CPU after 30 s | whole tree 0.31-0.36% of the machine (= 9-10% of one core); **app process only 0.09-0.11%**, so ~70% of idle CPU is the Chromium children |
| Warm `import openchem.main` | 1.6-1.8 s (no single eager import dominates: `services.container` 0.4 s, `molecule_editor_widget` 0.4 s, `atom_numbering` 0.3 s, RDKit 0.2 s, numpy 0.2 s). A cold first import after an edit took 24.8 s (bytecode rebuild + disk cache, uncontrolled) |

So "expensive to run" is, first, **four Chromium-based views built at launch (about half the process
tree's memory) and ~1,500 widgets**. That is a design cost, and the lever is laziness: Mol* and the
fourth view are not needed until a molecule or receptor is shown.

## Findings

| ID | Finding | Status | Evidence | Priority |
|---|---|---|---|---|
| F1 | Four `QWebEngineView`s are built at launch; the tree idles at ~1.08 GiB private | MEASURED | S1 x3; object census `QWebEngineView: 4` | P1 (design cost) |
| F2 | pH-dependent partial charge spawns a Python sidecar per uncached call: ~310 MiB resident, **~1.76 GiB committed**, alive 8-38 s | MEASURED | S6 `ph-sidecar` x3 (calls with different pH) | P1 |
| F3 | Chromium children take ~70% of idle CPU | MEASURED | S1: tree 0.31-0.36% vs app 0.09-0.11% | P2 |
| F4 | First show of the Docking panel costs a one-off CPU spike (median 5.6% of machine for 3 s, range 2.0-8.3%) | MEASURED | S2 x3 | P2 |
| F5 | The Atom Inspector panel idles at about twice the app-process CPU of the others (0.19% vs 0.07-0.11% of machine; ranges do not overlap) | MEASURED, small | S2 x3 | P3 |
| F6 | A 12-edit burst blocks the event loop up to 97-177 ms (4 stalls over 30 ms), one descriptor request per burst | MEASURED | S4 x3 | P3 (the 2026-09-24 fixes hold) |
| F7 | An unexpected `ZeroDivisionError` in the NP-likeness descriptor (`npscorer.py:58`) on a 0-atom structure, logged as an app ERROR once in 6 idle runs | MEASURED, incidental | startup-idle run 2 ledger (first batch) | P2 (a bug, not performance) |
| F9 | The first display of the 3D viewer adds **~360-460 MiB** to the app process (private bytes e.g. 1,214 -> 1,621; 1,210 -> 1,623), and switching back to the 2D editor gives back only ~15-70 MiB. Seen in 7 of 9 runs inside the measured window; in the two runs that did not show it the viewer also stalled the loop for 12.8-14.0 s, so its load probably landed outside the window | MEASURED, one-off at the first show (S5b: 9 of 9 first shows, none on later shows), stable in size | S5 x9 | P1 |
| F10 | **Conformer generation freezes the UI in ~0.3 s slices because RDKit's `ForceField.Minimize` holds the GIL.** During 10 conformers of a 51-heavy-atom molecule the loop's worst stall was 0.87 / 0.73 / 0.60 s and then 0.49 / 0.45 / 0.54 s, with 12-16 stalls over 100 ms, in all six runs taken after the pages had finished loading. The watchdog's stacks show the worker inside `_minimise` -> `force_field.Minimize` (`conformer_providers.py:1403`) while the main thread sits in `app.exec()` with no Python slot running. Standalone, in plain Python with no Qt: a thread running `ForceField.Minimize` per conformer left a 5 ms ticking thread **11 ticks, median gap 288 ms, 10 gaps over 100 ms**; `MMFFOptimizeMoleculeConfs` (1 or 4 threads) and `EmbedMultipleConfs` gave 546 / 229 / 649 ticks at a 5.2 ms median | MEASURED with a cause (RDKit 2025.09.6). **FIXED for the "Normal" level on 2026-10-07 (`MMFFOptimizeMoleculeConfs`)**; re-measured below | S5 + standalone GIL test | done |
| F12 | After the F10 fix the conformer phase still stalled 0.33-0.41 s: the GUI thread was in `AtomInspectorPanel._rebuild_atom_table` -> `build_atom_report` -> `collect_lewis` -> `lewis.analyse`, because the table asked for a report per atom and every report re-ran the WHOLE-molecule Lewis and oxidation-state analyses (51 identical `analyse` calls for 51 atoms). **FIXED 2026-10-07**: one analysis per table build through an explicit shared scope (`SHARED_ANALYSES`). Standalone table build 309 ms -> 12 ms, reports identical bar the timestamp. In-app worst conformer-phase stall 130 / 164 / 254 ms, and the 0.4 s watchdog fired no stack in the conformer phase in any run. Caching was chosen over moving it to a worker thread: the worker would still spend the 51x CPU and need stale-result handling | MEASURED, FIXED | S5 + standalone | done |
| F11 | **The first show of the 3D tab blocks the UI inside `QTabWidget.setCurrentWidget` for 73-640 ms, once; later shows take 1-2 ms.** Timed per switch (S5b `viewer-switch`, 6 switches x 3 runs x 2 variants, with and without conformers): the first show's call took 430 / 78 / 78 ms and 73 / 359 / 137 ms, and **all 30 later shows took 0.9-2.2 ms**; the worst loop stall tracked the call (438, 85, 84, 80, 350, 144 ms). The app process gains ~300-440 MiB at that first show and keeps it (private bytes 1,210 -> 1,537; later shows move +-30 MiB). **Showing it once early does not make the cost go away reliably**: in the third variant (an extra show/hide at idle before the timed switches) the following show still took 2.5 ms, 477 ms and **7,379 ms** in three runs (loop stall 7.7 s; the watchdog's stack for that one sits in `app.exec()`, not in `setCurrentWidget`). Multi-second freezes seen in earlier batches (1.8-14 s) remain intermittent and unexplained: no Chromium error was logged in any viewer-switch run, no new child process appeared, and system CPU was 13-38% | MEASURED: first-show cost is real and one-off (75-640 ms, ~0.4 GiB); the rare multi-second freeze is NOT explained | S5b x9 + S5 x12 | P2 (first show) / P1 to explain (multi-second) |
| F8 | Inspector open/close: a ~200 MiB one-off step on first open; **no per-open growth on clean reruns** | see Unresolved | | |

## Ruled out (measured, 3 runs each, 50 iterations, `oxidation_states` as the in-process calculator)

| Hypothesis | Result |
|---|---|
| Closed dialogs accumulate (exec'd, parented to the main window, no `WA_DeleteOnClose`: `show_settings`, `_show_about`, `_show_lewis_diagram`) | **Ruled out.** A census taken while each was open showed 1 `LewisDiagramDialog` / `SettingsDialog` (+720 widgets) / `AboutDialog`, and 1,517 widgets = the baseline afterwards. Slope 0.0-0.25 MiB per open |
| Results panel float/dock leaks | Ruled out. Private slope 0.01 / -0.23 / 0.01 MiB per cycle; widgets flat at 1,574 |
| The Jobs panel's 500 ms timer (active while hidden) costs anything measurable | Ruled out as a cost. Jobs steady tree CPU 0.26-0.37% sits inside the other panels' range |
| `connect(lambda ...)` closures over `self` still exist | Ruled out statically: one remains and it captures `callback`, not `self` |
| Probe overhead distorts the numbers | Within noise. App CPU, % of machine: sampler-only 0.076-0.133; +object census 0.085-0.129; +heartbeat 0.105-0.145; +tracemalloc 0.084-0.191. The 10 ms heartbeat itself reads a ~5.5 ms floor stall (Windows timer granularity) |
| Control instruments can see a planted signal | Pass: no-op slope -0.05 MiB/iter (limit 0.30); planted 5 MiB/iter read 4.95 (accepted 3.0-7.0); retained `QLabel`s grew 285->660; a 2 s child process was recorded |

## Re-measurement after the F10 fix (S5, 3 runs, same scenario, pages awaited)

| | Before (6 runs) | After (3 runs) |
|---|---|---|
| Conformer phase, worst loop stall | 0.87, 0.73, 0.60, 0.49, 0.45, 0.54 s | 0.34, 0.33, 0.41 s |
| Conformer phase, stalls over 100 ms | 9-16 per run | 2 per run |
| Conformer phase, stalls over 16.7 ms | n/a | 4-6 per run |
| Descriptor phase, worst stall | 8-47 ms | 16-25 ms |
| 3D viewer phase, worst stall | 1.3, 0.09, 1.0 s (watchdog runs) | 121, 149, 75 ms |
| 3D viewer first-display memory | +360-410 MiB | +370-420 MiB (unchanged: not part of this fix) |
| Whole-scenario wall time | 308-435 s | 168-192 s (page loads were also quicker, 3-9 s vs 30-71 s: machine state, not the fix) |

The UI-thread starvation by the minimiser is gone; what remained in that phase was F12, since fixed.

**After the F12 fix (3 more runs):** conformer-phase worst stall **130 / 164 / 254 ms** (was 333-405 after F10 alone, 450-870 before), stalls over 100 ms 2 / 1 / 4. Stalls between 16.7 and 100 ms went UP (13-18 per run against 4-6): not explained; they are small and the worst case halved, but it is recorded rather than ignored. The 3D-viewer phase got worse in this batch (worst 1.8 / 0.9 / 3.8 s against 75-149 ms before), which is F11 varying run to run, not something these changes touch: its stack is in `setCurrentWidget`.
**Conformer quality gate (2026-10-07, `benchmarks/conformers`, 12 molecules x 5 seeds x 50 embeddings):** predictions
generated twice on this machine, once through the batch API and once with that route switched off (the old
`ForceField.Minimize` path), then compared with each other and with the committed `predictions_shipped.json`
(built 2026-09-11, same RDKit 2025.09.6). **All three are identical across the 4,793 values compared** (counts,
per-seed sets, overlaps); `score.py` prints the same table for each, including the existing `over` (1,2-dichloroethane,
pentane) and `SHORT` (morphinan cage) verdicts, which are not new. Generation took 53 s on the batch API and 46 s on
the old path, so there is no speed claim here either way. The two regenerated files were identical to the baseline and were
not kept.

## Unresolved (do not act on these without a repeat)

* **Calculator Inspector open/close.** Batch 4 measured private bytes rising ~80 MiB per open in all
  three 50-iteration runs (1.5 -> 5.2 GiB), with the working set flat at ~480 MiB and the widget census
  flat. Three clean reruns an hour later, same code, measured -4.1, +0.3 and +0.4 MiB per open, bouncing
  between 1.2 and 1.4 GiB with no trend. Two sets of three runs disagree and **the cause of the
  difference is not identified**. What is solid: the first open adds ~200 MiB to the app process, and a
  closed inspector leaves the widget census unchanged.
* **Edit / recalculate / undo loop.** Batch 4 showed +3.7 MiB per cycle in three runs. A single
  150-iteration run alone showed a flat 1,240 MiB (slope +0.04) from iteration 1 to 150. Again not
  reproduced; the first runs read like a start-up ramp, and I did not isolate it.
* **Window-ready latency** varied 3.0-9.6 s across three otherwise identical runs.
* **3D viewer opening stalls (F11)**: 0.09-1.3 s in the last three runs but 12.8-14.0 s in two earlier ones. Whether those were the viewer, GPU initialisation, or something else on the machine at the time is not known.

## How the instruments were validated, and where they were wrong

* **Working set lies at idle.** The first startup batch showed an idle app "shrinking" from ~400 to ~50
  MiB RSS (and USS 230 -> 50 MiB) because Windows trims a background window's working set. The sampler
  now records Windows **private bytes** and that is the memory number used here. Those runs are kept in
  `benchmarks/perf/results/_superseded/`.
* **A harness-built window is not the app's window.** The driver's `inspect` and `dialog` steps build
  dialogs without the `WA_DeleteOnClose` the real paths set, and measured +150 MiB per open and 24,867
  widgets that the app does not have. They were replaced with `call_window` (the window's own method)
  and the real reveal path. Lesson: drive the code a click reaches.
* **The first "cheap" calculator was not cheap.** `gasteiger_charge_at_ph` with an invented
  `ph_dependent` parameter ran pH-dependent every time and spawned the sidecar (F2). That batch is in
  `_superseded/ph-sidecar-calculator/`; the loops use `oxidation_states`.
* **A first control run failed on its own pre-declared limit** because the pages were still loading
  (a 25 MiB step). A 30 s start-up settle was added and recorded in every result; the failing run is kept.
* **Cleanup of my own deleted three results folders** once (a `rmtree` in an ad-hoc A/B). Those runs were
  redone; the numbers above are from the reruns except where stated.

## Limits of this census

* Sampler: observed live process tree only (cadence 1 s, 0.15-0.25 s for process scenarios); a child shorter than
  the cadence can be missed. Tree RSS is a non-unique sum; USS is read every 2nd sample.
* Object census: Python-visible `QObject`/`QWidget`/`QTimer` wrappers plus `allWidgets()`, not every C++
  object. Timers are "active Python-visible `QTimer`s". `tracemalloc` sees Python allocations only.
* "Window ready" is the main window shown, not an exposed first paint. "Fresh process" start-up does not
  control OS caches.
* Three runs per scenario, one machine, one session; with differences this size between batches on the same code,
  a single batch is not evidence of a trend.

## Reproducing

```bash
uv sync --extra ai --extra network --extra openbabel --group perf
uv run --no-sync python tools/perf_census.py controls            # instruments first
uv run --no-sync python tools/perf_census.py run startup-idle panels-idle --runs 3
uv run --no-sync python tools/perf_census.py run lifecycle-inspector --runs 3
uv run --no-sync python tools/perf_census.py report              # aggregate.json, no app launch
```

Raw output: `benchmarks/perf/results/` (git-ignored); each run directory holds the generated `script.json`,
`samples.csv`, `processes.csv`, the app's `report.json`, `summary.json` (environment, commit, status) and
the log. In-app probes: `src/openchem/app/drive_probes.py` and the `mark`, `object_census`, `loop_lag`,
`tracemalloc`, `cache_probe`, `panel_cycle`, `call_window`, `close_inspectors` drive steps.

## Follow-up candidates (pick; none started)

1. Build the Mol* and fourth web view lazily (F1: up to ~half the idle tree's memory).
2. Decide whether the pH-dependent charge needs a fresh ~1.76 GiB sidecar per call, or a warm/shared one (F2).
3. Guard the NP-likeness descriptor against an empty structure (F7).
4. Repeat the inspector and edit loops under controlled conditions before treating either as a leak.
5. Stop conformer minimisation freezing the UI (F10). **Measured with `benchmarks/perf/probes/minimise_slices.py`** (10 conformers per molecule, same embeddings, ethanol to erythromycin, worker thread beside a 5 ms ticking thread; standalone, not through the app scenario):
   * **Slicing `Minimize(maxIts=N)` is not a fix.** On erythromycin, N=100 cut the worst stall from 467 ms to 91 ms but took 10.4 s against 2.85 s (3.6x) and landed on different minima (max 5.7 kcal/mol away from the shipped result, with every conformer converged); N=10/25/50 took 17-31 s and left 3-9 of 10 unconverged. Restarting BFGS at every slice boundary loses its curvature estimate. Ethylmorphine showed the same shape (8.96 kcal/mol at N=10 and 50).
   * **`MMFFOptimizeMoleculeConfs` is the candidate.** Same time (2.80 s vs 2.85 s), **identical energies on all five molecules (max |dE| 0.0000 kcal/mol)**, worst stall 17 ms with none over 30 ms. Its limit: no force tolerance, so it equals the "Normal" level (1e-4) only; "Loose", "Strict" and "Very strict" would still need `ForceField.Minimize` (or a subprocess). Not applied: the conformer module's levels, discard rule and provenance would need to be kept honest around it.
