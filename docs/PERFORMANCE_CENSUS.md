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
| F9 | The first display of the 3D viewer adds **~390-460 MiB** to the app process (private bytes 1,212 -> 1,599 and 1,230 -> 1,688 MiB), and switching back to the 2D editor gives back only ~25-70 MiB. In the third run the same jump landed one phase later (1,238 -> 1,653), so the amount is stable and the timing is not | MEASURED x3, phase boundaries blurred by timing | S5 | P1 |
| F10 | Event-loop stalls of seconds during conformer generation and the 3D viewer opening: worst stall 0.5 / 1.8 / 7.5 s while generating 10 conformers of a 51-heavy-atom molecule, and 1.1 / 8.7 / 5.3 s while the viewer opened. Descriptors alone were quiet in run 1 (12 ms) but stalled 1.8 s and 4.1 s in runs 2 and 3 | MEASURED, wide run-to-run spread; the start-up pages were still settling in runs 2-3 (child memory 61 and 269 MiB at the first boundary vs 567), so work and page load are not separated | S5 | P1 to confirm |
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
* **Heavy molecule (S5)** ran all phases (the 10 conformers were asserted to exist), but its stalls
  varied from 12 ms to 8.7 s between runs, and a 30 s settle did not always finish loading the web pages. F10 needs a rerun with the
  settle replaced by "all web views report loaded" before it is read as the cost of the work itself.

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
5. Replace the fixed start-up settle with a wait for the web views to finish loading, then repeat S5 (F10).
