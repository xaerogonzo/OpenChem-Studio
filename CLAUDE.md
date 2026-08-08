# OpenChem Studio — notes for Claude

## Working in a git worktree — do this before anything else

A fresh worktree needs two things set up, and **both fail silently rather
than loudly**, which is why they are the first thing in this file.

```bash
uv sync --extra ai --extra network --extra openbabel
"D:/Claude Co worker/Token Save/tokensave.exe" init
```

**The venv.** A worktree has no `.venv`. `uv run` will happily create an
empty one and then report `No module named pytest`, which reads like a
broken checkout rather than a missing sync.

**The tokensave index — the dangerous one.** The MCP server is registered
globally as `tokensave.exe serve` with no `--root`, and finds its project
by searching *upward* for a `.tokensave/` directory. A worktree created
under `.claude/worktrees/` sits inside the main repo folder and has none
of its own, so the search walks up and serves **the main checkout's
code** — a different branch, without the files you just wrote. Measured
2026-08-04: `tokensave_search` for a class written minutes earlier
returned `[]`.

Every call does carry a `worktree_mismatch` warning. **That warning is not
cosmetic; it means the answers are about different code.** Never work past it.

`init` costs about 2 seconds (343 files, ~8000 nodes) and leaves
`git status` clean. Three things that cost real time when they were not
known:

- **`init` refuses to rebuild an existing index.** It prints a "use
  `tokensave sync`" hint and exits 0, so a stale index looks like a
  successful re-index. Use `sync --force` to actually rebuild.
- **Initialising mid-session does NOT rebind the MCP tools.** The server
  resolved its root when it started, so `tokensave_*` calls keep hitting
  the old index. Until the session restarts, query through the CLI
  instead: `tokensave.exe tool health --path src/openchem`,
  `tokensave.exe tool search SomeClass`.
- **`tokensave branch` does not solve this.** It tracks branches within
  one checkout and syncs from that checkout's files, so it cannot see
  another directory's working tree.

The binary is not on PATH; call it by full path.

## Running the tests

```bash
uv run --no-sync python -u -m pytest -q > /tmp/suite.log 2>&1; tail -5 /tmp/suite.log
```

Writing to a file rather than a pipe is worth doing because it lets you watch
progress while it runs.

A clean run is **3-6 minutes**, ending at `3019 passed, 2 skipped,
1 deselected` (measured 2026-08-07 with the presentation-layer Phase 0-8
work applied, bytecode cleared; it was 2788 before that). **That figure is
from the DESELECTED form below, not the command above** -- run it bare and
the same tree reports one FAILURE, from the network test explained next.

**One test fails against the network, not against the code.**
`test_pubchem_name_round_trips_back_through_opsin` returns `HTTP 400` from
NCBI and does so on trees predating the work that was running when it was
first seen -- confirmed by stashing. Deselect it when you need a clean signal:

```bash
uv run --no-sync python -u -m pytest -q --deselect tests/test_naming_providers.py::test_pubchem_name_round_trips_back_through_opsin
```

Take the count on a **clean tree**. The main checkout often carries
work-in-progress tests, and a figure measured there is inflated -- which has
already produced one wrong edit to this file.

The suite also needs the optional extras installed, or ~40 tests fail on
missing imports and it looks like something is badly broken when nothing is:

```bash
uv sync --extra ai --extra network --extra openbabel
```

(Not `--all-extras`: that pulls in `docking`, whose `vina` wheel builds from
source and needs Boost. The reference environment does not have it.)

### The suite used to hang — fixed, kept here as history

This is no longer something to work around. It is recorded because the cause
took three attempts to identify and the failure mode was invisible.

**`QtWebEngineProcess.exe` instances accumulated and were never torn down.**
Every `QWebEngineView` a test constructs spawns Chromium helper processes, and
nothing disposed of them between tests. A hung run was caught with **91 alive**;
a measured baseline reached **116**, plateauing near 88, with the Python
process at **14 seconds of CPU** while wall clock passed 40 minutes — blocked,
not working. They pile up until something (handles, memory, a port) gives out,
always around the webview-heavy tests at roughly 30%.

They ARE reaped when pytest exits, so a post-mortem finds zero and looks
healthy. **The count only means anything sampled DURING a run.**

The fix is the autouse `dispose_web_engine_views` fixture in
`tests/conftest.py` — read its docstring before changing anything there, since
two plausible-looking implementations of it crash. Measured across two full
runs after the fix: peak **6** processes, mostly 0–1, against 116 before.

**Three wrong explanations were believed before the right one** — recorded so
a fourth does not get invented:

1. A bad shell wait-loop (`until grep -q "passed|failed"`, which never matched
   because `-q` buffers). Wrong, and accepting it cost a second 40-minute hang
   the same day.
2. The `pytest.exe` console-script shim under `uv run` spawning an extra
   nested process. Plausible, written into this file as near-fact, and also
   wrong — the module form hung the very next run. The shim was correlation.
3. While fixing it: that tearing pages down mid-load caused the teardown
   crash, so `view.stop()` was the cure. Removing `stop()` did not reproduce
   the crash in 8 runs. The actual cause was
   `sendPostedEvents(None, DeferredDelete)` draining every pending deferred
   delete in the process, including ones other tests had queued on
   already-collected objects. It is now flushed per view.

If a run ever stalls again, sample before assuming it is slow:

```bash
powershell "(Get-CimInstance Win32_Process -Filter \"Name='QtWebEngineProcess.exe'\" | Measure-Object).Count"
```

### A test that builds a panel must destroy it before the next one runs

Same family as the webview leak above, different object, and it fails much
louder. A test that constructs an unparented widget and walks away leaves it
with no owner, so Python destroys it at whatever arbitrary later moment the
collector happens to run -- inside an unrelated test, from within Qt's own
event dispatch. The result is a **Windows access violation**, and it surfaces
in whichever test happens to be pumping events at the time (any test of an
event-driven panel must, since `EventBus.publish` is a *queued* Qt signal and
nothing has been delivered when `waitForDone()` returns).

Measured on `tests/test_batch_panel.py`: **3 of 3 full runs of the file
crashed**, while running only some subsets of it passed -- because whether it
fires depends on when the collector happened to run. That "sometimes"
is exactly what makes it read as flakiness rather than as a bug in the test.

The fix is to destroy each widget deterministically and flush **that
widget's** deferred delete:

```python
widget.setParent(None)
widget.deleteLater()
QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)
```

Per widget, never `sendPostedEvents(None, DeferredDelete)` -- the global form
drains every pending deferred delete in the process, including ones other
test files left queued, which is the same double-free the webview fixture
already documents.

**Do this per file. There is no global version of it, and the attempt to
build one is recorded below as a warning.** The autouse
`flush_deferred_deletes` in `tests/conftest.py` handles only the
`deleteLater()` half -- it stops a backlog accumulating, and does NOT
destroy widgets a test walks away from.
`tests/test_qt_object_disposal.py` fails if it regresses.

#### How the ketcher crash was found, and the two things that were wrong about it

Recorded because the version of this section written before it was solved
named the wrong mechanism, and reasoning from that mechanism produced a fix
that measurably did not work.

The symptom: `test_ketcher_editor_backend.py` died with an access violation
at ~30% of a full run, on 3 runs and then not on the next 6, with CI green
throughout. **Do not trust green runs here** -- the corrected fix below was
verified against a deterministic reproduction, not against a streak.

What was wrong in the old account:

1. *"`processEvents()` drains the `DeferredDelete`."* It does not. Measured
   against this Qt build, a `DeferredDelete` posted at event-loop level 0 is
   delivered only when an actual event loop at that level returns, and
   `QApplication.processEvents()` never delivers one, however many times it
   is called. A pytest run never enters such a loop, so **every**
   `deleteLater()` in the suite sits in the process-wide queue until
   something spins a NESTED event loop -- which drains the entire backlog at
   once. QtWebEngine spins one internally while a page loads. That is the
   whole reason the victim is always a webview test: it is not that its
   `processEvents` pump is dangerous, it is that Chromium is the only thing
   in the suite that lights the fuse.
2. *"The widget's Python wrapper was already collected."* Not for the
   deleteLater'd object itself -- PySide keeps that wrapper alive until the
   event is delivered, so it is still weak-referenceable at session end,
   which is what made a census possible at all.

**Instrumentation found it in one run where bisection could not.** Wrapping
`QObject.deleteLater` to record its receiver weakly, then reporting which
receivers were still valid at each test boundary, named the offenders
exactly: 18 undelivered deletes, of which the 9 `IrViewWidget`s from
`test_ir_view_widget.py` (five files earlier) were the ones live while the
ketcher tests ran. Wrapping widget constructors the same way found the
second, larger half: **112 top-level widgets abandoned by 20 files**.

**Forcing the drain turns the heisenbug into a 12-second reproduction.** Run
one nested `QEventLoop` before each ketcher test and the crash is
deterministic:

```python
loop = QEventLoop(); QTimer.singleShot(0, loop.quit); loop.exec()
```

Measured with that lever, on `test_ir_view_widget.py` + the four files
between + `test_ketcher_editor_backend.py`:

| tree | result |
| --- | --- |
| before the fix | crash 5 / 5 |
| ketcher file alone (nothing queued) | pass |
| deferred deletes flushed only | crash 2 / 2, via `test_jobs_panel.py` |
| both fixtures | pass 8 / 8 |

That middle row looked like the whole story, and it was not.

#### THE WIDGET-DISPOSAL FIXTURE WAS REVERTED. Do not rebuild it blind.

`dispose_app_widgets` tracked every top-level widget of one of this app's
classes and destroyed each at teardown, per object. Against the base it was
developed on (`a85463f`) every number said it worked: the table above, plus
the leaked-widget census 112 -> 0 and 11 of 11 plain full runs green.

**It crashed the suite outright on master**, at `2dff778`, once the
help-window work had added many more MainWindow-with-viewer tests. Measured
by an interleaved A/B with a byte-identical file set, neutering the fixture
in place rather than deleting its test file:

| arm | full runs |
| --- | --- |
| both fixtures active | **access violation 8 / 8** |
| `dispose_app_widgets` neutered, flush still on | complete 8 / 8 |
| `flush_deferred_deletes` neutered, widgets still on | access violation 3 / 3 |

So it is that one fixture, on its own. The crash sites were
`test_main_window_docking_visualization.py` and
`test_ketcher_editor_backend.py` -- the MainWindow-plus-webview tests that
pump events, neither at fault. Re-ordering it to finalise after
`dispose_web_engine_views` did NOT help (still 5 of 5), so "a live view was
taken down as a child" is not the explanation, and why destroying an
abandoned widget synchronously at teardown faults here is **still unknown**.

**The original ketcher crash was open when this was written; it is now
solved -- skip to "SOLVED. The census named it" below before acting on
anything in this subsection.** Two further things
that were measured and do not fit together yet, for whoever picks this up:
master at `a093912` crashed 3 of 3 in a clean worktree with none of these
fixtures, while master at `2dff778` is green 8 of 8 in the main checkout
with none of them. Same suite, opposite results -- so before trusting ANY
result here, pin down the checkout and the commit, and never compare a run
in one against a run in the other.

Method note, learned the hard way: an early "before" measurement was taken
in a checkout that was being edited by hand at the time, so the two arms
were different trees and the comparison was worthless. Check `git status`
and file mtimes before believing an A/B.

#### A `lambda` that captures `self` in a `connect()` leaks the widget forever

Found while chasing the above, and it is a separate bug with a separate
fix. **PySide6 holds a connected plain callable STRONGLY and a QObject's
bound method weakly.** So this roots its widget for the life of the
process -- past refcounting AND past the cyclic collector, which cannot
see through the internal map the callable is kept in:

```python
button.clicked.connect(lambda _checked=False, d=definition: self._open(d))
```

Measured on a three-button minimal case: the self-capturing lambda leaks,
the same widget with `connect(self._go)` is freed by refcounting alone,
and a lambda capturing only plain data is also fine. It is `self` in the
closure that does it, not the lambda.

`PropertyPanel` was the worst of it -- one such connection per registered
calculator, 22 on a default registry -- so every panel ever built stayed
in memory for the session. Fixed, with the payload travelling on the
button as a Qt property and a bound method reading it back through
`sender()`. Same fix in `PeriodicTableDialog` (118 cells) and
`ExternalToolsDialog`.

`tests/test_qt_object_disposal.py` guards all of it, and deliberately
asserts the leak itself as well: if a future PySide6 stops leaking here,
that test fails and the workarounds can go.

#### The root of the cycles: `EventBus` now holds bound methods weakly

`EventBus.subscribe` used to store the handler in a plain list. A bound
method holds its object, so the bus owned every panel that ever subscribed
and the panel owned the bus -- a cycle nothing could break by reference
counting, leaving the whole graph to the cyclic collector.

Bound methods are held with `weakref.WeakMethod` now; everything else is
still held strongly, and that asymmetry is the load-bearing part. A lambda
usually has no other reference, so held weakly it would be collected the
instant `subscribe` returned and the subscription would silently never
fire -- worse than a leak, because nothing looks wrong. Measured when the
change was made: production code subscribes 38 bound methods and ZERO
lambdas, while the tests subscribe 74 lambdas.

Measured effect, per panel:

| | before | after |
| --- | --- | --- |
| `JobsPanel` | refcounting | refcounting |
| `DockingPanel` | needed the cyclic collector | **refcounting** |
| `PropertyPanel` | leaked outright | **refcounting** |

**It does NOT replace the teardown `gc.collect()`, and the numbers say so
plainly.** With weak handlers and no collect, late C++ destructions went
UP -- 138 before, 177 after -- because more objects are now destructible
at all rather than leaked. With both, 8, against 2352 destroyed inside
their own test. Keep both.

It also moved MainWindow, without fixing it: with weak handlers AND the
menu lambdas removed, the first window is destroyed cleanly and the
SECOND construction segfaults, 5/5. So destroying a MainWindow leaves
something process-global in a state the next one trips over. That is the
next thread to pull; the section below still applies until it is pulled.

#### What makes MainWindow destruction fault: the undo stack

Bisected against the real window, by disabling one piece at a time:

| window | destroyed |
| --- | --- |
| as built | **segfault 5/5** |
| `_new_molecule` suppressed (nothing ever pushed) | clean 3/3 |
| `_undo_stack.clear()` before dropping | clean 5/5 |
| `close()` alone, before `closeEvent` cleared the stack | **segfault** |

So commands sitting on the stack are what makes destruction fatal, and
clearing it first is what makes destruction safe. `closeEvent` now clears
it, which is why that line is there.

**The mechanism is NOT understood, and nothing here should pretend
otherwise.** A synthetic `QUndoCommand` on a `QUndoStack` destroys fine, so
does the real `AddMoleculeCommand` in a minimal harness, and so does a
hand-built `QMainWindow` carrying every panel, all three web views, custom
dock title bars, a status-bar widget, scroll areas, menus and a plugin
manager -- 3/3 each. It takes the whole real window. The commands are
necessary but not sufficient.

Ruled out along the way, each measured 3-5 times: `QWebEngineView`,
`MoleculeEditorWidget`, `MoleculeViewer3DWidget`, `MolStarViewerBackend`,
all three viewers together in a `QTabWidget`, `DockTitleBar`,
`CheckerStatusIndicator`, `QScrollArea` + `tabifyDockWidget`, menus,
`PluginManager`, and `_restore_window_state`.

##### The full fix IS shipped, once the collect was moved

The first attempt looked like a disaster and was reverted: menu lambdas
removed + this clear + the seven `test_main_window_*` files closing their
windows made the suite green 2/2 while late C++ destructions went from 8
to **1190**. The open question was "after `window.close()`, what still
references the window?"

**Nothing in the application does.** Listing the referrers of a window
still alive at teardown found only pytest: `SubRequest`, `TopRequest`,
`_pytest.python.Function`, and the fixture-name cache. Pytest holds every
fixture value for the whole item protocol, so a `gc.collect()` running in
`pytest_runtest_teardown` CANNOT collect a fixture-provided window -- and
the conftest hook had no `trylast`, so it ran before fixtures were even
finalised.

    collect in pytest_runtest_teardown, unordered   1190 late
    collect in pytest_runtest_teardown, trylast      135 late
    collect in pytest_runtest_logfinish                0 late

Zero, with 3587 destroyed inside their own test, the suite green 3/3, the
forced-drain reproduction 0/10, and the run slightly FASTER than before.

The trap worth remembering: a test that builds its window as a plain local
cannot tell the right hook from the wrong one, because the local is
released when the function returns either way. The guard in
`tests/test_qt_object_disposal.py` takes its window from a FIXTURE for
exactly that reason -- the first version of it did not, and the mutation
survived.

#### MainWindow's menu lambdas ARE fixed now (an earlier note said not to)

They were reverted once, with the note "the leak is load-bearing", because
removing them made the window collectable and destroying a MainWindow
crashed. Both halves of that are now solved and the fix is in:

- `closeEvent` empties the undo stack, which is what made destruction
  safe (see the section above it);
- the collect runs after the item protocol, so windows are collected at
  the right moment (see below).

Menu actions carry their payload on the `QAction` via `setData` and connect
bound methods that read it back through `sender()`. Two facts about Qt that
this depends on, measured rather than assumed, because the file previously
asserted the opposite of the first:

    menu.addAction(label, callable)     calls it with NO arguments,
                                        whatever its signature
    action.triggered.connect(callable)  passes `checked`

So a handler reached through `addAction` keeps its own defaults --
`_duplicate_molecule(molecule=None)` really does receive None -- and only
`toggled`/`triggered` connections have to take the bool.

Two measurement traps from the attempt that got reverted, both general:

- **A probe that prints "destroyed" after `del` + `gc.collect()` proves
  nothing.** It has to assert with a weakref that the object really died.
  Without that, a leaked window reads as a successful destruction, and a
  bisect across eight commits reported "destructible" everywhere while
  destroying nothing at all.
- **Reverting any ONE piece of the fix appeared to cure the crash.** It did
  not -- it just left one lambda still leaking, so nothing was destroyed.
  Any partial revert looks like a fix, which makes bisecting within the
  change actively misleading.

#### SOLVED. The census named it, and the fix is one line of timing.

Read this before acting on anything above it. The sections above are kept
as the record of how it was chased and several of their intermediate
conclusions were later reversed; the cause is now measured and the fix is
in `tests/conftest.py`.

**Census A (undelivered deletes) found nothing** -- 0 outstanding at every
test boundary and at session end. `flush_deferred_deletes` had already
closed that half completely, so every hypothesis built on the delete
backlog was chasing a queue that is empty.

**Census B (widgets alive at session end) measured the wrong population.**
It reported 65 live parentless panels, which looks damning and is
irrelevant: a widget still alive has never been destroyed, so it cannot be
the thing that faults. Those 65 are a LEAK, not a landmine.

**Census C, then D, found it.** Instrumenting `QObject.destroyed` -- the
only event that runs a C++ destructor -- and recording the test that was
running at that instant against the test that built the widget:

    destroyed inside their own test : 2003
    destroyed in a LATER test       : 138   <- the landmine, measured

138 from seven files, 104 of them `test_quantum_chemistry_panel.py`. (Do
NOT use a weakref callback for this, as census C did: it counts Python
wrappers, over-reports by an order of magnitude -- 1406 -- because a
wrapper collected after Qt already destroyed the C++ object is harmless.)

**Why they outlive their test.** `EventBus.subscribe` stores the BOUND
METHOD in `_handlers`, so the bus holds the panel and the panel holds the
bus. Reference counting cannot break a cycle; nothing is freed when the
test's locals go out of scope, and it waits for the cyclic collector,
which runs whenever it likes -- including inside Qt's event dispatch in an
unrelated test. Measured per class: `JobsPanel` (subscribes to nothing)
dies by refcounting, `DockingPanel` needs the cyclic collector,
`PropertyPanel` survives both and is a real leak.

**The fix is `gc.collect()` in a teardown hook, gated on `qapp`.** It
destroys nothing itself -- that distinction is the whole point, since
forcing destruction with `deleteLater()` has now crashed the suite twice
under two different implementations. It only chooses the MOMENT at which
Python does its own ordinary work, and a teardown hook is a moment with no
Qt event dispatch in progress.

| arm | late C++ destructions | full run |
| --- | --- | --- |
| before | 138 | 116 s |
| `gc.collect()` after every test | **0** | 326 s |
| `gc.collect()` only after `qapp` tests | **4** | 171 s |

The last row is what shipped. The four that remain are all inside
`test_quantum_chemistry_panel.py` itself; closing them costs another 155
seconds on every run, which is not worth it for four same-file
destructions when the crash being chased was cross-file.

Corroboration, given how unreliable crash-rate arms are here: the
forced-drain reproduction went **0 crashes in 10** with the fix, and three
plain full runs were green. Neither is proof on its own -- the whole
lesson below is that these arms move between batches -- which is why the
deterministic 138 -> 4 is the number to trust and to re-measure if this
ever comes back.

#### Confirmed again, independently, at the Structure Check work

The reverted fixture's central finding was re-derived from scratch by
somebody who had not yet connected it to this section, which is worth
recording because it means the result is real and not an artefact of how
`dispose_app_widgets` happened to be written.

Adding `tests/test_structure_check_panel.py` (which builds a MainWindow and
pumps events) gave **1 access violation in 5 full runs**, at
`test_a_quick_fix_lands_on_the_undo_stack`. That file inserts ~50 tests
ahead of the panel tests and so shifts collection timing; it does not
introduce anything new. Note `pytest-randomly` IS NOT INSTALLED here, so
file order is deterministic and adding a file is the only thing that
reorders anything.

Seven files build a MainWindow and abandon it -- `test_main_window_*.py`
(six of them) and `test_receptor_library_dialog.py`. Giving each the
per-file disposal recipe from the section above, so the abandoned windows
are destroyed deterministically at teardown, produced:

| arm | forced-drain subset |
| --- | --- |
| abandoned, as today | crash 3/3, then 0/10 on the same tree |
| explicitly disposed | **crash 6/6** |

So **destroying them is worse than leaving them**, which is exactly what
the `dispose_app_widgets` table already said and is now confirmed by a
second, differently-written implementation. Do not try this a third time.

The middle row is the other lesson: an unchanged tree gave 3/3 and then
0/10. The rate itself moves between batches, so **no A/B here is worth
anything below about n=10 per arm**, and a 3-run comparison -- which is
what most of the earlier work in this section used -- can say the opposite
of the truth.

The forced-drain lever from the ketcher section works on this crash too and
is the only reason any of the above could be measured at all:

```python
loop = QEventLoop(); QTimer.singleShot(0, loop.quit); loop.exec()
```

run as an autouse fixture before each test of the victim file.

One caveat worth knowing if you re-run that instrumentation: stacking BOTH
diagnostic plugins on top of the now-permanent fixtures double-wraps every
widget constructor and destabilised a run by itself (a `Fatal Python error:
Aborted` in `test_molstar_viewer_backend.py` that appears under no other
configuration). Run one census at a time.

### The suite must not touch the machine's real settings

`Settings` wraps `QSettings`, which on Windows is the real registry key a
shipped install uses. The autouse `isolated_settings` fixture redirects it to
an INI file under `tmp_path`; `tests/test_settings_isolation.py` fails if that
regresses.

Worth knowing because the previous version of that fixture **looked** correct
and half-worked. It called `QSettings.setDefaultFormat(IniFormat)` and gave
each test a unique org/app name — but `setDefaultFormat` does not affect the
`QSettings(organization, application)` constructor in practice, whatever the
docs say:

```python
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.defaultFormat()          # Format.IniFormat
QSettings("Org", "App").format()   # Format.NativeFormat  <- still the registry
```

So the real `OpenChemStudio` key stayed clean (the unique name did that much)
while every run deposited **84 junk keys** under `HKCU\Software`, one per
test, named after the test, permanent. Nothing in the suite output showed it.
Building the QSettings from an explicit file path avoids the format question
entirely.

If you touch that fixture, verify by counting, not by reading:

```bash
powershell "(Get-ChildItem 'HKCU:\Software' | Where-Object PSChildName -like 'OpenChemStudio-pytest-*' | Measure-Object).Count"
```

### `repaint()` does not paint a widget that was never shown

A `paintEvent` test that constructs a widget, resizes it and calls
`repaint()` proves nothing. Measured on a counting subclass:

    repaint() on a never-shown widget    0 paintEvent calls
    update() + processEvents             0
    grab()                               1
    repaint() AFTER show()               1

So `widget.grab()` (or showing it first) is the only way to exercise the
painter. Four such tests existed and were green without ever running the
code they named -- including one then called
`test_highlighting_survives_a_repaint`, in which no repaint occurred. (That
name is history, not a test to go and find; all four were rewritten.)

**Use `conftest.painted()` / `conftest.ink()`**, which render into a
`QImage` and force the paint.

ASSERTING THAT SOMETHING WAS DRAWN IS HARDER THAN IT LOOKS, and two
plausible checks were tried and killed by mutation testing -- blanking a
widget's peak-drawing loop and seeing which tests noticed:

1. *"Some pixel is non-transparent."* Useless. Every one of these widgets
   fills an opaque background before its first mark, so alpha is set
   across all 30,000 sampled pixels even for an EMPTY spectrum.
2. *"More ink than the same widget with no data."* Still passes a blanked
   painter. Different data changes the axis range, so the tick labels
   alone move the count.

What works: **hold the axes fixed and vary only the content** -- two
spectra sharing their extreme shifts, differing by one peak in the
middle. Identical ticks and labels, so the ink difference can only be the
peak. That took the number of tests catching a blanked painter from 1
to 6.

`ink()` counts pixels differing from the modal (background) colour, not
transparent ones, for reason 1 above.

Tests that assert on child-widget structure rather than drawing -- e.g.
`test_structure_grid_widget.py` counting cells in a layout -- are not
affected and do not need any of this.

### The formerly-flaky webview test

`tests/test_mol3d_viewer_backend.py::test_apply_visualization_sets_atom_colors`
used to fail intermittently on `QWebEngineView` readiness (sometimes a sibling
failed instead — the tell that the test was not what was wrong). It was the
leak above, caught where starting one more Chromium process was slow rather
than impossible.

It failed on the pre-fix baseline run and has passed **5 consecutive full runs**
since. If it flakes again, that is a genuinely new bug, not this one.

### The vendored nomenclature engine's own suite

`tests/vendor/` holds ~3,200 tests belonging to the vendored IUPAC namer. They
are **excluded from the default run** (`norecursedirs` in `pyproject.toml`)
because they take ~10 minutes against the main suite's 3, and they cover that
engine's internals rather than our integration with it.

Run them whenever you change anything under `src/openchem/vendor/`:

```bash
export JAVA_HOME="/d/Random Programs/OpenChemStudio_Data/jre/jdk-21.0.12+8-jre"
export PATH="$JAVA_HOME/bin:$PATH"
uv run --no-sync python -u -m pytest tests/vendor -q > /tmp/vendor.log 2>&1; tail -4 /tmp/vendor.log
```

Expect `3209 passed, 0 skipped` (~10 min).

**`JAVA_HOME` AND `PATH`, and they are not the same requirement.** Setting
only PATH gives `3193 passed, 16 skipped` -- which is the figure this file
carried for a long time, then "corrected" to blame an `ImportError` on
`py2opsin`. That attribution was wrong, and measuring it rather than
reasoning about it is what showed the difference:

    py2opsin imports fine, java on PATH   3193 passed, 16 skipped
    JAVA_HOME set as well                 3209 passed, 0 skipped

All 16 live in `tests/vendor/iupac_namer/test_tautomer_alignment.py`, whose
`_java_available()` reads the JAVA_HOME **environment variable** and does not
look at PATH at all. CI sets JAVA_HOME as a side effect of its setup-java
step, which is why CI saw 3209 and a PATH-only local run never could.

Finding them took mapping the `s` characters in pytest's `-q` progress output
back onto `--collect-only` order; `-rs` on the whole suite is another ten
minutes, and the skip reasons are not in a `-q` log.

PATH is still needed on its own: py2opsin shells out to a bare `java`, and
pytest does not inherit the managed Temurin the app injects per-subprocess
(`naming_providers._java_on_path`). Without PATH you get a bare
`FileNotFoundError` naming neither Java nor OPSIN.

## The naming benchmark

`benchmarks/naming/` is the regression check on naming quality — 181 molecules,
scored by OPSIN round-trip rather than string equality. It is the arbiter for
"is this naming engine better", and it has twice overturned a conclusion
reached without it.

Generate fresh predictions, then score them:

```bash
uv run --no-sync python - <<'PY'
import json
from pathlib import Path
from openchem.vendor.iupac_namer import name_smiles
rows = json.loads(Path("benchmarks/naming/corpus.json").read_text(encoding="utf-8"))
preds = []
for r in rows:
    try: preds.append(str(name_smiles(r["smiles"]) or ""))
    except Exception as e: preds.append(f"<ERROR {type(e).__name__}>")
Path("benchmarks/naming/predictions_check.json").write_text(
    json.dumps({"check": {"predictions": preds}}, indent=1), encoding="utf-8")
PY
uv run --no-sync python benchmarks/naming/score.py benchmarks/naming/predictions_check.json
```

Current: **181/181** (82 exact, 98 equivalent, 1 tautomer — metformin, which
counts as a success since the `tautomer` outcome class was added). If a
change under `src/openchem/vendor/` drops this, that
outranks any number of narrow tests it fixed.

`score.py` takes exactly one predictions file. The committed
`predictions_full.json` and `predictions_deterministic.json` were recorded
against the older 124-molecule corpus and will now be **refused** by the
length guard rather than silently mis-scored — that guard is deliberate, not a
bug. They are kept as the record of what the ML alternatives scored at the
time; compare them only against the corpus revision they were made for.

## Ketcher CAN report atom AND bond selection, with one trap

The 2D editor was assumed to expose nothing for selection -- its Python
backend has only `load_molblock`, `set_render_option`,
`trigger_toolbar_action` and `get_molblock`. That is a fact about **our
wrapper**, not about Ketcher, and reading the wrapper is what made it look
impossible.

Probing the real vendored build (load `resources/ketcher/dist/index.html`
in a bare `QWebEngineView` and evaluate JS -- far faster than driving the
app) found:

- `ketcher.subscribe(name, handler)` is a **switch** that accepts only
  `'change'` and `'libraryUpdate'`. This is the dead end that makes
  selection look unavailable.
- `editor.subscribe` is a DIFFERENT method and does exist.
- `editor.event` carries ~30 events including **`selectionChange`**, plus
  `click`/`mousedown`/`mousemove` added at runtime by `domEventSetup` --
  so the live object has more than the `this.event = {...}` literal in the
  bundle shows.
- `editor.selection()` reads the current selection synchronously and
  returns `null` when nothing is selected. `editor.selection({atoms:[1]})`
  sets it and dispatches the event, which is how to test this without
  synthesising canvas clicks.
- **Bonds work identically**: `editor.selection({bonds:[0]})` round-trips
  as `{bonds: [0]}`. The selection object carries ONLY the keys with
  something in them -- a bond click has no `atoms` key at all -- so a
  handler must check both rather than assume one shape.
- **A SELECTION REPORTS POOL IDS, NOT MOLFILE POSITIONS.** This was
  previously recorded here as "Ketcher's bond ids are RDKit's bond
  indices... no translation table is needed, and one would be a place for
  a silent off-by-one to live". That is wrong, and the section below is
  the correction. The verification behind it was real but was performed on
  a freshly LOADED molblock -- the one state in which a pool has never had
  anything removed from it and the two agree by coincidence.

**THE TRAP: `selectionChange` hands your handler `undefined`.** It is a
`PipelineSubscription`, which feeds each handler the PREVIOUS handler's
RETURN VALUE rather than the original payload. Ketcher registers its own
handler first and that one returns nothing, so anything subscribed
afterwards receives `undefined` forever. Measured: a probe handler saw
`typeof sel === 'undefined'` on every dispatch while the event itself was
firing correctly, which reads exactly like "the event does not work".

`change` does NOT behave this way -- it is a plain `Subscription` -- so the
two look interchangeable and are not.

The fix is one line: ignore the argument and call
`ketcherInstance.editor.selection()` inside the handler.

#### A POOL ID IS NOT A MOLFILE POSITION, and a fresh load hides it

Reported from the running app: drawing a benzene and clicking a ring vertex
answered **"Atom 9 is in the 3D structure but not in the structure as drawn
-- the report covers heavy atoms and treats hydrogens as implicit. Pick a
heavy atom."** A second vertex gave atom 11. Benzene as drawn has six atoms,
and the molecule really was C6H6.

`Pool` extends `Map` and hands out ids from a counter that only ever
increments -- `add` and `newId` both `return this.nextId++` (read in the
bundle, then measured). **An id is a permanent identity handle and a freed
one is never reused**, while the molfile is positional and RDKit numbers its
atoms by reading it in order. The two agree only until something is deleted.

Reproduced through Ketcher's own API in about 20 seconds: draw two rings,
select the first and press Delete, and the surviving six-atom ring carries
pool ids **6..11** against a molfile of six atoms numbered 1..6. Every
vertex was off by six; clicking two of them sends 8 and 10, which is exactly
the report.

    molfile position  0  1  2  3  4   5
    what was sent     6  7  8  9  10  11     atoms AND bonds, both

**Bonds had the identical offset and were the worse half.** A wrong bond
index usually stays in range, so no guard fires and the panel silently
describes a DIFFERENT bond. The atom side was only ever visible because
`_atom_is_in_report` happened to catch it and say something.

Two reasons this shipped, both worth knowing:

- **A fresh `setMolecule` rebuilds the pool from zero.** Every probe that
  established the old claim loaded a molblock and read the ids straight
  back, so all of them saw a dense pool. **Any check of an index space has
  to run against an EDITED structure, never a freshly loaded one.**
- **A full erase resets it too**, so "draw, clear the canvas, draw again"
  looks fine. It takes a PARTIAL deletion -- which is the ordinary case,
  not the exotic one.

**It is NOT the vite 6 rebuild** (`001bd63`), which was the first
suspicion. The previous bundle, restored with `git archive 2768ee8`, gives a
byte-identical verdict: 6/6 atoms and 6/6 bonds wrong. This is Ketcher's
data model, and the bug is as old as the selection feature.

The fix is `molfilePosition()` in `tools/ketcher-host/src/main.jsx`, which
translates before the value crosses the bridge -- so Python's contract stays
"this is an RDKit index" and the one place that knows Ketcher exists is the
one place that knows about pools.

**INSERTION ORDER, NEVER SORTED, and this is the trap inside the fix.**
`indexOf` on `Array.from(pool.keys())` looks interchangeable with sorting the
ids, and is not. Undo re-inserts a deleted atom under its ORIGINAL id at the
END of the Map. Measured on a C-N-O-F-S-P chain with the carbon deleted and
restored:

    pool insertion order   [1, 2, 3, 4, 5, 0]
    molfile atom order      N  O  F  S  P  C     <- follows insertion order
    sorted by id           [0, 1, 2, 3, 4, 5]    <- wrong in all 6 positions

Bonds behave the same way and the case is sharper, because a bond pool can
be out of numeric order without any atom being: the same edit left bond ids
`[0, 4, 1, 2, 3]`, and RDKit's bond order matched that exactly, checked pair
by pair. A sorted implementation produces perfectly plausible indices and is
wrong, which is why `test_a_selection_is_never_forwarded_as_a_raw_ketcher_id`
asserts the absence of a `.sort(` by name.

Two guards, deliberately split. `tests/test_ketcher_editor_backend.py::`
`test_a_selection_arrives_as_a_molfile_position_not_a_ketcher_pool_id`
builds the real two-ring-minus-one state against the real bundle and asserts
what Python receives -- it must, since a stale dist leaves the app broken
with every Python test green. It **asserts its own setup** (pool ids really
are `[6..11]`) first, because if the Delete hotkey ever stops erasing, the
pool stays dense and the test would pass while testing nothing. Verified by
running it against the vite 5 bundle: fails, `assert [6,...] == [0,...]`.
The cheap half is a source check in `test_ketcher_bundle_is_current.py`,
confirmed to catch both a raw-id regression and a sorted one.

**`runJavaScript` on this Qt build returns PRIMITIVES ONLY.** Numbers and
strings arrive intact; an array or a plain object arrives as `''`,
indistinguishable from a script that returned nothing. This cost the first
probe run entirely -- every result read as empty and looked like Ketcher
failing rather than marshalling failing. Wrap anything structural in
`JSON.stringify`; `_run_js_json` in the test file does.

**THE 3D VIEWER AND A REPORT DO NOT SHARE AN INDEX SPACE**, and the
mismatch is a crash rather than a wrong answer. A conformer carries
EXPLICIT hydrogens; the structure as drawn has implicit ones. Ethanol is 3
atoms in a report and 9 in the viewer, so clicking a hydrogen in 3D sends
index 3-8 -- past the end. `GetBondBetweenAtoms(1, 5)` raises
`RuntimeError: Range Error` inside a Qt signal handler.

The heavy atoms agree ONLY because `AddHs` appends, so indices 0..n-1 line
up and nothing warns about the rest. That is why a live check that clicked
only heavy atoms found nothing, and why the bug was found by asking what a
hydrogen click would do rather than by hitting one. Anything wiring a
viewer click to a structure index needs the same bounds check;
`_atom_is_in_report` is the one in the inspector.

**3Dmol, by contrast, reports ATOMS ONLY.** Its `setClickable` callback
receives an atom, and bonds drawn in stick mode are not separately
selectable -- a click near one resolves to the nearest atom. So the 3D
viewer names a bond by its two atoms: the inspector takes two clicks and
resolves the bond between them, which uses only what the library provides.
That is deliberately NOT built on the viewer's existing multi-atom
selection, which drives distance measurement -- sharing it would make one
gesture mean two things depending on a mode nobody set.

Editing `tools/ketcher-host/src/main.jsx` requires `npm run build` in that
directory for anything to change; `resources/ketcher/dist/` is build
output. node and npm are installed, and a build takes about a minute
(measured 54 s and 1m00 on two bond-selection rebuilds).

#### The bundle was rebuilt on vite 6, and what that cost

The toolchain moved from vite 5.4.21 to 6.4.3 to clear six dependabot
alerts, and the dist was regenerated on it. Worth knowing before the next
bundler bump:

**It costs almost nothing, and the obvious estimate is wrong by two
orders of magnitude.** Measured, `git count-objects -vH` before and after
the commit plus a `gc`:

    size-pack  15.27 MiB  ->  15.59 MiB      +0.32 MB

against a rewritten 34 MB JS file. Reasoning from FILE SIZE predicted
~35 MB and talked this rebuild out of happening once; the pack barely
moved because **minification is disabled here** (a TDZ bug in
ketcher-core's circular imports, see the config) so the bundle is
line-structured text that deltas against its predecessor almost
perfectly. Git even records the assets as renames-with-changes rather
than new blobs. Only the CSS was byte-identical
(`index-DaFekdiN.css`); all three JS chunks were replaced.

Measure the pack, not the file, before refusing a rebuild on size.

**No security depended on it.** All four vite/esbuild advisories are
DEV-SERVER issues -- `server.fs.deny` bypass, launch-editor NTLM, `.map`
path traversal, dev-server CORS -- and this project has no dev server:
`package.json` declares exactly one script, `build`. The output bundle
was never affected. The alerts are cleared by the LOCKFILE, so rebuilding
was a choice about keeping artifact and toolchain in step, not a fix.

`brace-expansion`, `uuid` and `nanoid` are pinned through npm `overrides`
because they arrive transitively (via `dpdm`, `vite-plugin-top-level-await`
and `postcss`) and their own CVEs are not dev-server-only.

**The bundle guard cannot tell you a rebuild WORKS.**
`test_ketcher_bundle_is_current.py` checks that each bridge name appears
as a string in the bundle -- it catches a forgotten rebuild, not a broken
one. After any toolchain change, exercise the paths that depend on module
init order, which is exactly what a bundler changes:

    npm run build                                    28 s on vite 6
    pytest tests/test_ketcher_bundle_is_current.py   names present
    pytest tests/test_ketcher_editor_backend.py      8 pass, real QtWebEngine
    a live selection probe                           see below

Selection is the one to check by hand, because it is the piece this file
already documents as fragile (the `PipelineSubscription` trap) and no
test covers it firing end to end. Drive it through Ketcher's own API
rather than synthesising canvas clicks:

```python
backend._page.runJavaScript("window.ketcher.editor.selection({atoms:[1]}); 1")
backend._page.runJavaScript("window.ketcher.editor.selection({bonds:[1]}); 1")
```

Measured on the vite 6 bundle: `atomSelected -> [1]`, `bondSelected ->
[1]`. Verify the build in a scratch outDir first (`npx vite build --outDir
...`) and repoint `_DIST_INDEX` with a one-line pytest plugin -- that
proves the toolchain before `emptyOutDir: true` deletes a working dist.

**Forgetting the rebuild is silent** -- the tests pass, the app starts, and
the feature is simply absent. `tests/test_ketcher_bundle_is_current.py`
catches it: it extracts every `bridgeObject.foo(` from the JSX and asserts
the name appears in the committed bundle, then that a `_Bridge` method of
that name exists to receive it. Verified by simulating the mistake -- adding
a call without rebuilding fails with the method named and the fix printed.

**It is a string check, not a rebuild-and-diff, and that was measured
rather than assumed.** The build IS byte-for-byte reproducible on one
machine (snapshot the dist, rebuild, diff: 5 files, zero differences, git
clean). But CI is Linux on a different node, and reproducibility across
toolchains is a much stronger claim -- one byte from a minifier would fail
every PR, and a check that cries wolf gets deleted. Bridge method names
cannot be minified (they are properties of the object Qt injects), so they
fingerprint the build for free and with no platform sensitivity. It needs
no node in CI, and `tests.yml` runs bare `pytest`, so it was picked up
without touching the workflow.

Reproducibility confirmed a second time, and with it something that saves a
rebuild: **a COMMENT-ONLY edit to `main.jsx` does not stale the dist.**
Comments do not survive the build even though minification is off -- a
distinctive phrase added to a comment appears 0 times in the 35 MB bundle --
so rewording one and rebuilding produced a byte-identical asset, same
content hash (`ea091b8d...`, `index-E55nh8EI.js`). Rebuild for a code
change; a comment is free.

**Building the dist in CI instead was considered and rejected**, with
numbers: the whole `.git` is 40 MB, only 10 MB of it large blobs, and the
dist has been rebuilt 3 times in the project's life. Moving the build out
would cost node in CI, a build step on every fresh clone, and 19 tests that
construct `KetcherEditorBackend` (which raises `FileNotFoundError` without
a dist) -- to save single-digit megabytes. Git also records the rebuilds as
99% renames, so successive versions barely cost anything.

## The bond and molecule reports, and what generalising cost

`AtomReport` was written with `AtomFact`/`FactCategory` deliberately free
of anything atom-specific, on the stated bet that bonds and molecules would
want the same shape. **The bet paid: they moved to `domain/report.py`
UNCHANGED**, `AtomReport` lost only its identity fields to a shared
`StructureReport`, and every existing import still works through aliases
(`AtomFact = Fact`, `AtomFactProvider = FactProvider`,
`AtomFactService = FactService`). The panel's whole rendering half --
sections, search, copy, links -- needed no change at all.

Three things measured while building them:

- **A 2D depiction has coordinates, and they are not measurements.** Every
  bond in a layout comes out about the same length whatever its order:
  aspirin's 2D C=O reads 1.5 "units" against a real 1.264 A. So the bond
  report emits NO length from a 2D conformer rather than a wrong one, and
  the molecule report says outright which kind of coordinates exist.
- **RDKit's strict rotatable-bond definition could not be reconstructed.**
  Excluding amides leaves aspirin at 3 against `CalcNumRotatableBonds`'s 2;
  excluding all conjugated bonds drops biphenyl's central bond, which RDKit
  DOES count. Two attempts, both wrong, so the bond report reports "single,
  acyclic, non-terminal" -- the thing it can stand behind -- and names the
  gap rather than shipping a "rotatable" verdict that contradicts the
  molecule's own descriptor.
- **BRICS bonds are a synthesis statement, not a stability one.** A bond
  BRICS would cut is one a known reaction class could FORM. It says nothing
  about strength, and the fact carries that.

Two mutations survived the first pass, and both were tests that could not
discriminate rather than code that was wrong:

- **A monocyclic molecule has as many bonds as atoms.** Aspirin is 13 and
  13, so swapping `atom_count` and `bond_count` was invisible. Assert
  counts on an ACYCLIC molecule.
- **Overlapping atom and bond indices hide which field is being read.** A
  fixture with `atom_indices=(0, 1)` and `bond_indices=(0,)` gives the same
  answer either way. Make them disjoint.

## A new panel needs a help topic, and nothing was checking

`HELP_TOPIC_BY_DOCK` in `app/main_window.py` maps a dock's object name to a
section anchor in `docs/`. Both guards in `tests/test_help.py` iterated
**over the map**, so a panel MISSING from it was invisible to them: its `?`
button opened help with nothing selected, and the suite stayed green.

The Atom Inspector and the Interactions panel both shipped that way and
were found by reading the map against the docks by hand during a
documentation sweep. `test_every_dock_the_window_builds_has_a_help_topic`
now goes the other direction and names the offending dock.

A documentation sweep is worth doing for the same reason: it found four
shipped features with no user-facing documentation at all, and an LED
section missing from `SCIENTIFIC_LIMITATIONS.md` -- the file that exists
precisely to say what the app cannot honestly tell you.

**CLAUDE.md itself had drifted badly.** 132 lines were a stale duplicate of
the four sections above them, reaching the OPPOSITE conclusions: an
all-caps "DO NOT 'FIX' MAINWINDOW'S MENU LAMBDAS. THE LEAK IS
LOAD-BEARING." sat directly below "MainWindow's menu lambdas ARE fixed
now". Anyone reading top-to-bottom hit the correct account and then a
shoutier contradiction of it. Check for this when adding to a long
troubleshooting file -- appending a corrected account does not remove the
old one:

```bash
rg -n "^#{2,5} " CLAUDE.md | awk -F': ' '{print $2}' | sort | uniq -d
```

## The presentation layer, and four things measured while fixing it

The app's chemistry was correct and its presentation was not, which is a
different kind of bug and needs a different kind of evidence. Recorded
here because three of these four cost real time and two contradict what
the obvious approach would have been.

### `WrappedLabel` is load-bearing in one place and catastrophic in another

`ui/widgets/collapsible_section.py`'s `WrappedLabel` overrides
`minimumSizeHint`, `hasHeightForWidth` and the size policy so a wrapped
label reports its true height. Inside the property panel's scroll area
that is what stops the calculator buttons being squeezed to 13 px -- its
own docstring has the table.

Used for a **one-line status in a top-level row it is the opposite**, and
by a wide margin. Measured on a bare Qt reproduction at 900x950:

    WrappedLabel batch status   461 px tall, scroll area starts at y=478
    plain QLabel                 20 px tall, scroll area starts at y=37

`MinimumExpanding` makes the row claim the panel's vertical stretch, so a
third of the Properties panel was one line of transient status. The rule
is not "always use WrappedLabel" -- it is "use it where a label's true
height must survive a squeeze", and a status line is not that.

### 20 of 25 `AlertResult`s were never alerts

`AlertResult.matched` is a `list[str]`, and it became the generic line
carrier for anything that was not a single scalar -- `topology_analysis`
puts `"Szeged index: 12"` in it, `regulatory/calculator.py` documents
doing so deliberately. The panel rendered any non-empty `matched` as
`"N alert(s): "` + a comma-join, in `#c62828`.

Counted rather than estimated: **25 distinct `alert_id`s, of which only
`pains`, `brenk`, `mutagenicity_alerts`, `herg_risk_factors` and a
regulatory screen WITH findings are warnings.** So four fifths of the
app's results were painted as though the molecule were flagged, and an
elemental analysis read `8 alert(s): Formula: CHNO, Mass: 43.025, ...`.

The fix is `AlertResult.severity`, declared by the PRODUCER, defaulting to
INFO. Guessing from the id would have been a heuristic; the producer
knows. `Severity` already existed in `domain/structure_issue.py` and is
already rendered by the structure-check panel -- reused rather than
paralleled, which is this project's most repeatable mistake.

**An empty `matched` was rendered as a green "Clean" without checking
`cache_state` first.** Geometry with no 3D conformer returns FAILED
carrying "This calculation needs a 3D conformer", and the panel reported
success while discarding the message that said what to do. "Clean" is a
verdict and only a catalog is entitled to give one; a report with nothing
to say has cleared the molecule of nothing.

### `QFontMetrics.inFont()` does not answer "will this glyph render"

Needed for the status glyphs, since colour alone is invisible to a
colour-blind reader and is lost entirely in copied text. The obvious check
is wrong:

    inFont('✕') -> False     and it renders perfectly
    inFont('△') -> False     and it renders perfectly
    inFont('✓') -> False     and it renders perfectly

It asks about the one nominated font, not the fallback chain Qt actually
paints with. **Painting is the only honest test**, and "it drew some ink"
is not enough either, because a tofu box is ink.

The control is a Private Use Area codepoint, which no font assigns. It
turned out to render as **nothing at all** here, byte-identical to a
space -- not as tofu, which was the guess. That is asserted in
`test_the_status_glyphs_really_render` rather than assumed, so a platform
change that starts drawing tofu fails there naming the reason instead of
quietly weakening the test.

### The cp1252 rule reaches further than `matched`

`regulatory/calculator.py` already records that result lines hit Windows
console streams and that a tick RAISES there -- three times in one
session. The status glyphs are non-ASCII, so they are produced at RENDER
time and stripped at every exit (`_without_glyphs`, used by the panel's
"Copy all"). A glyph is decoration: somebody pasting into a paper wants
`Pass`, not `✓ Pass`, and the word already carries what the glyph
duplicates on screen.

Hit immediately, in a scratchpad script that printed the panel back:
`UnicodeEncodeError: 'charmap' codec can't encode character '✕'`.

### The command palette introduces no registry, deliberately

`Ctrl+Shift+P` reads three indexes the app already has -- the rail's panel
list, `CalculatorRegistry`, and the live `QMenuBar` -- for **113 commands
with nothing registering itself**. A palette that required each feature to
register would be a fourth list to keep in step, and the one that falls
out of step is always the one nobody remembers to update. A new
calculator or menu item is in the palette because it exists.

`score()` is a pure function so the ranking is testable without a dialog,
which matters because ranking is the only part of a palette that can be
subtly WRONG rather than broken. Four tiers -- exact, prefix, word start,
subsequence -- with subsequence last because it matches almost everything
and would otherwise drown a real prefix. Ties keep the caller's order, so
panels beat calculators beat menu items and "batch" lands on the panel.

#### PySide invalidates a wrapper reached through a TEMPORARY list

Hit twice in one hour, in production code and then in a test:

```python
menu = next(a.menu() for a in bar.actions() if ...)   # menu is DEAD here
```

The C++ object is fine; the wrapper is not. `bar.actions()` is a
temporary, and releasing it invalidates every wrapper obtained from it --
the next line raises `Internal C++ object already deleted`. Hold the
parent list, or read what you need while you still have it.

`_menu_actions` does the latter: it captures each label DURING the walk
and returns `(label, source, action)`, rather than handing back a wrapper
for the caller to read later. `findChildren(QMenu)` is worse still and is
avoided -- it is recursive over the whole object tree and returns wrappers
for menus Qt has already freed.

A dock's `toggleViewAction` carries the panel's own name, so every panel
appeared twice until exact duplicates were dropped. The panel command
wins because it SHOWS the panel; a toggle can hide it, which from a
palette is a surprising thing to have asked for. Only exact duplicates go
-- Console is a dock with a toggle and no rail entry, and its View item is
the only way to reach it.

### Comparison: the engine existed, the way in did not

`chem/comparison.py` had `atom_correspondence`, `build_comparison` and
`deltas_against` since the LED work, reachable from exactly one place --
a tab inside `BatchAnalysisDialog`, behind building a batch table first.
So "how do these two molecules differ", which is a question people ask
constantly, required a workflow nobody would guess at.

`compare_values` is the everyday case beside that per-atom machinery:
molecules in columns, properties in rows, built from the values other
panels have already published. **The panel never computes** -- a blank
cell means that calculator has not run for that molecule, and the intro
says so, because a comparison view that silently launches forty
calculators is one people stop opening.

**"Differences only" is the feature, not a filter.** Measured live on the
motivating pair: aspirin against salicylic acid is **15 differing rows
out of 29**, and finding those 15 by eye is exactly the work the table was
supposed to save.

Three decisions worth keeping:

- **Absence counts as a difference.** A property one molecule has and
  another does not stays visible under "differences only" -- a missing
  value is usually the interesting thing, and hiding it would be the more
  misleading of the two choices.
- **Rows keep producer order, never alphabetical.** A calculator emits
  formula before mass before composition deliberately, and sorting
  scatters that.
- **Agreeing on everything is a RESULT, not an empty table.** Two
  molecules matching on every property known says something, so that
  empty state differs from "nothing computed yet".

The ticks do NOT follow the tree selection, for the same reason the
Interactions panel's two combos do not: the comparison is a deliberate
choice, and reshuffling it because somebody clicked elsewhere would
silently change what the table on screen describes.

#### The rail must follow a panel opened from anywhere

"Compare with..." showed the Compare panel while the rail still
highlighted Analysis. `_on_panel_chosen` now calls
`PanelRail.select_panel`, which is a no-op when the rail itself was the
caller and is what keeps the two in step for every other route -- a
plugin revealing its panel, a cross-link, the command palette. Navigation
claiming one thing while the screen shows another is worse than either
alone.

### `AlertResult` was carrying twenty reports and five alerts

`AlertResult.matched` is a `list[str]`, and it became the generic line
carrier for anything that was not a single scalar. Counted: **25 distinct
`alert_id`s, of which only pains, brenk, mutagenicity_alerts and
herg_risk_factors are catalogs.** The panel rendered every non-empty
`matched` as `"N alert(s): "` in red, so four fifths of the app's output
looked like a warning.

`ReportResult` carries `Fact`s instead -- label, value, units, basis,
evidence, limitations, which atoms it is about, how specialist it is. All
of that was already being computed and flattened away at the last step.

Measured after the migration: **16 fact-based reports, 4 alert catalogs.**

**`AlertResult` is not deprecated and must not be.** It is in the plugin
API, and for a real catalog "N alert(s)" in red is the correct rendering.
`chem/report_adapter.py` converts one to facts for anything that has not
migrated -- permanently, not as a shim.

#### The batch table shows what a string cost

`result_reduction.py` had to PARSE `"Randic index: 9.52"` back into a
label, a number and a unit, with a deliberately strict regex. Measured
when it was written: 73 numeric columns extracted and **25 lines refused**
-- formulas, prose caveats, value lists, all correctly refused and all
genuinely lost.

A `Fact` was never flattened, so `_reduce_report` has nothing to recover:
45 facts give 43 numeric columns on the same four calculators, the two
text ones being a formula and a direction vector. **The column ids are
byte-identical**, so saved tables, charts and exports survive.

#### `ReportResult.matched` is a DERIVED view, kept on purpose

Composed from the facts on demand, never stored. It exists because
`matched` is in the plugin API and because a large number of assertions
read it -- "does the topology calculator report a Randic index" is a real
question whose answer does not change with the shape it arrives in.

Regulatory's lines were already self-labelling (`"Near miss: ..."`), so
they are split at that colon and `matched` recomposes them byte-for-byte.
That is what let 13 modules migrate without rewriting their tests.

#### Regulatory finally says what it did NOT check

It computed the rulesets consulted, the coverage notes and the unchecked
domains into `Provenance.parameters` and **displayed none of it** -- the
panel showed `1 alert(s): No matches in the 1 ruleset consulted`. They
are facts now: aspirin's screen lists twelve domains with no ruleset
loaded, each carrying "this screen says nothing about it either way".
Ruleset versions and coverage notes are marked ADVANCED so they do not
bury the findings; "NOT checked" is deliberately STANDARD, because a gap
in coverage is not specialist information.

### The right-hand panels are NOT tabified, and must not become so again

Twelve panels shared one tabified dock group, and Qt gives such a group a
single `QTabBar`. **That bar wanted 1992 px and had about 920**, so every
label elided to two or three characters -- `"Qu..."`, `"J..."`, `"B..."`.
Widening the dock cannot fix it: a bar wide enough for twelve labels is
wider than the window.

`tabifyDockWidget` is what creates that bar, so the fix is not to hide it
but to stop tabifying. One right-hand dock is visible at a time and
`ui/widgets/panel_rail.py` chooses which. That also answers the reason
they were tabified in the first place -- the visible panel gets the whole
column, instead of nine slivers.

**Hiding Qt's bar does not work**, tried first: `setVisible(False)` on the
live one reads back `True` after the next relayout, because the dock area
re-shows it.

`test_the_right_hand_panels_have_no_tab_bar_to_elide` fails if a
`QTabBar` parented to the WINDOW comes back. The ones parented to a
`QTabWidget` belong to individual panels and are fine.

#### `restoreState` restores TABIFICATION, so old layouts are discarded

This is the part that a test would not have caught, and did not. Every
`tabifyDockWidget` call was gone and the elided nine-tab bar was **still
there** on a real install, because `QMainWindow.restoreState` had put it
back from the saved layout.

`_LAYOUT_VERSION` in `app/main_window.py` gates it: a state saved under an
older arrangement is dropped. There is nothing to migrate -- `saveState`
is an opaque blob with no readable structure -- so the only honest
options are restore it or do not. **The geometry is kept either way**; it
carries no dock arrangement, and discarding somebody's window size to fix
their panel layout would be a gratuitous second change.

Bump `_LAYOUT_VERSION` for any future change a saved layout cannot
express, and probe a REAL install rather than trusting the suite: every
test builds a window with no prior state, which is exactly the case that
cannot see this.

#### `isVisible()` is False for every child of an unshown window

Bit twice in two phases, in production code and in a test. A dock that
has been `setVisible(True)` on a window nobody showed still reports
`isVisible() == False`, so a check written that way answers "none of
them" under a test harness while looking right in the running app --
the same blindness as `repaint()` on a widget that was never shown.

`isHidden()` reads the explicit flag and is the one to use. Both
`_help_topic_for_visible_panel` and
`test_only_one_right_side_dock_is_visible_at_a_time` had to change.

### Empty states: iterate over what is BUILT

There was no empty-state text anywhere in `ui/` -- a search for any
placeholder string over the whole package matched two files, neither a
panel. So "not run yet", "ran and found nothing", "failed" and "not
applicable to this job" all rendered identically as blankness, and an ESP
single point left six of seven quantum tabs looking broken.

`tests/test_empty_states.py` walks the tabs **the panel actually builds**,
never a list kept beside it -- the same direction that caught the two
missing help topics. It asks each tab what it SHOWS, not how it stores
it, which is what let the three mechanisms below coexist behind one
guard. Verified by simulating the mistake: removing one tab's placeholder
fails naming the tab.

#### SOLVED: the teardown collect was DESTROYING MainWindows

Windows fatal exception `0xc0000374` (heap corruption), raised inside the
`gc.collect()` in `pytest_runtest_logfinish`, in whichever test was
unlucky. **It cost about fifteen full suite runs across three phases of
UI work**, and every appearance looked at first like an unrelated failure
somewhere else.

**Collecting a `MainWindow` corrupts the heap.** A window a test builds
has no Qt parent, so PySide gives Python ownership, and freeing the
wrapper deletes the C++ window. The window sits in a reference cycle
nothing else breaks, so the thing that eventually frees it is the
teardown collect. `tests/conftest.py` now retains every MainWindow for
the session, and `test_main_windows_are_deliberately_never_collected`
fails if that retainer is removed.

**This is the project's own conclusion, finally made true.** The sections
below record two earlier attempts to destroy abandoned MainWindows, both
of which made the suite crash MORE, and both concluded "leave them". What
nobody had noticed was that the collect was destroying them anyway --
`pytest_runtest_logfinish`'s own docstring asserted it "does not destroy
anything itself", which was wrong.

##### Why it looked like "adding a widget breaks it"

Because the crash is **non-monotonic in widget count**, which is the tell
that it is a corrupting free whose VICTIM depends on heap layout, not a
capacity being exceeded. Measured with a tunable probe that adds N empty
`QLabel`s to a panel, on the 20-second reproduction:

    0, 1, 2, 4 extra labels    clean
    8, 16 extra labels         CRASH
    32 extra labels            clean

So the widgets never caused anything; they shuffled the heap until the
freed window's memory happened to be adjacent to something that mattered.
Every "prefer a change that adds no widget" rule written into this file
across two commits was a superstition that worked by luck, and all of it
has been deleted.

##### How it was found, in the order that worked

1. **A tunable probe driven by an environment variable**, so an A/B needs
   no file edit at all. Three arms in an earlier bisect had silently
   tested an unmodified file.
2. **`PYTHONMALLOC=debug` reported nothing**, which rules out Python's
   allocator and says the corruption is in the C++ heap.
3. **`gc.DEBUG_SAVEALL` made it clean.** That is the decisive step: with
   nothing freed there is no crash, so the crash is in FREEING a member
   of a cycle, and `gc.garbage` then holds the exact candidates.
4. **Retaining one class at a time** named it. Patching `__init__` to
   append to a global list prevents collection at the source:

        retain nothing                          crashed
        retain MainWindow                       clean
        retain the three viewer backends        crashed
        retain QWebEngineView + QWebChannel     crashed

Retaining the windows also made the reproduction **twice as fast** (1.76 s
to 0.85 s), because destroying them was expensive. Full suite: 2846
passed, peak working set 760 MB.

##### Six hypotheses that are WRONG

Recorded so nobody pays for them again. Each was tested against the full
suite; two of them this file previously asserted as the rule.

1. *The `dict[QWidget, ...]` holding placeholders.* Removed -- still dead.
2. *Hiding sibling content.* Suppressed every visibility change -- still
   dead.
3. *A new test file shifting collection order.* Removed -- still dead.
4. *"A placeholder in a tab page that already holds widgets."* The log's
   `CollapsibleSection` went into a main layout and died the same way.
5. *Python-derived widget subclasses.* A plain `QLabel` killed it too.
6. *That panel's leaked test widgets.* `test_quantum_chemistry_panel.py`
   abandons 15 panels and accounts for 104 of 138 late destructions;
   giving it the per-widget disposal recipe and re-adding the fatal
   widget **still died at the same test index**.

##### AN ARM THAT DOES NOT RUN IS NOT AN ARM

Three arms reported a comfortable "no crash" and were worthless.
**Removing the widget under test usually breaks MainWindow
construction**, so the tests ERROR instead of running -- and the crash
needs a MainWindow to exist. A harness that only greps for
`fatal exception` scores that as a pass. Check the passing-test COUNT
against the control:

```bash
uv run --no-sync python -m pytest -q tests/test_receptor_library_dialog.py tests/test_regulatory_calculator.py 2>&1 | tail -1
```

That pair is the **20-second reproduction**, and having one is what made
the root cause findable at all after three phases of 3.5-minute arms.

This is the second version of a lesson already in this file. The first
was a mutation script whose edit never landed; this is an edit that
landed and a test that never ran.

##### If it ever comes back

The signature is a truncated `-q` progress line, then
`Windows fatal exception: code 0xc0000374`, then a traceback whose top
frame is `conftest.py ... pytest_runtest_logfinish` / `Garbage-collecting`.

Count how far it got and name the test:

```bash
awk '/^[.sFEx]+/ {gsub(/[^.sFEx]/,"",$0); n+=length($0)} END {print n}' /tmp/suite.log
```

**Pin the baseline before blaming yourself OR the suite**: `git stash`
everything and run master. This file's warnings about flaky access
violations elsewhere would otherwise excuse a crash that is entirely
reproducible and entirely yours.
## Verification standard

This project's convention, established across many sessions: **claims are
measured, not asserted.** Before shipping a formula, a threshold, a parser
regex or a model, verify it against a primary source or a real run and record
what was checked. Several things were deliberately NOT shipped because they
could not be validated (Miller polarizability, HLB, TSEI) — that is a normal
outcome here, not a failure.

Comments explain **why**, especially where something is non-obvious or was got
wrong once. A comment restating the code is noise.

### A library DEFAULT can be a different quantity, not a tuning knob

`rdMolDescriptors.DoubleCubicLatticeVolume` computes a **solvent-accessible**
volume unless told otherwise: its probe radius defaults to 1.4 A. Called as
its name suggests and read as a van der Waals volume, it is wrong by 700%:

    helium, analytic 4/3 pi r^3          11.494
    DoubleCubicLatticeVolume()           91.952   <- r + 1.4, a DIFFERENT quantity
    DoubleCubicLatticeVolume(probeRadius=0.0)     11.494

The danger is that 91.952 is not absurd. On any molecule without a closed
form it is simply a larger number, and nothing anywhere says which quantity
you asked for. **A one-atom test catches this and nothing else does**, because
one atom is the only case with an exact answer to compare against.

Two more measured facts from the same work, both the opposite of the obvious
reading:

- **`DoubleCubicLatticeVolume` is the ANALYTIC routine and `ComputeMolVolume`
  is the grid one**, despite the names. DCLV matches 4/3 pi r^3 to four
  decimals instantly; `ComputeMolVolume` is 5% low on a lone atom at its
  default spacing and needs 0.89 s to reach 0.04%. `surface_analysis.py` had
  shipped the grid one.
- **The cross-check is weakest where the answer is most certain.** The grid
  routine's error tracks the surface-to-volume ratio, so across ten molecules
  the worst BONDED case is 1.53% while a bare atom is 4.99%. A tolerance
  fitted to real molecules will flag a lone atom, and that is the check
  failing, not the value.

### Bound the grid, not the resolution

A projection measured at a fixed 60 samples/A cost **4.27 s** for a 92-atom
molecule -- unusable in a panel that recomputes on every selection change.
Capping total cells instead of lowering resolution everywhere took it to
**0.80 s** while leaving small molecules untouched (aspirin identical, helium
still pi r^2 to 0.13%).

That is the correct trade and not merely the cheap one: grid error is set by
the shape's perimeter-to-area ratio, so a larger molecule tolerates a coarser
grid at the same relative accuracy. Accuracy is preserved exactly where it is
hardest to get.

### A derivative can be self-consistent, symmetric, and wrong

DREIDING's optimiser needed an analytic gradient (a numerical one is
252 ms per step for neopentane -- an hour for the barrier set against
11 seconds). The first torsion derivative was wrong, and **every cheap
check it could have failed, it passed**: it summed to zero as translation
invariance requires, it was smooth, and the optimiser converged happily
to a geometry that was not a stationary point. The barrier it produced
was plausible.

Textbook forms of `dphi/dr` differ by the direction convention of `b1`
and by the argument order inside `atan2`, so a formula lifted from one
source into another's convention is exactly this failure. **Solve for the
coefficients against a central difference** rather than recalling them --
least squares on a random geometry returned them exactly, and took less
time than reading two more sources.

Two habits that fell out of it, both general:

- **Check each term separately, not just the total.** Bond, angle and
  van der Waals were exact to 1e-8 while torsion was out by a sign; a
  matching total can hide two errors cancelling.
- **Translation invariance is necessary and NOT sufficient.** The wrong
  version satisfied it, which is why it survived inspection.

### A conformer search result is part of the question, not the setup

Butane's methyl rotation barrier came out at 3.171 against DREIDING's
published 3.410 -- alone among eight molecules, and by an amount small
enough to argue about. The force field was fine: `EmbedMolecule` plus an
MMFF cleanup had landed butane in the **gauche** well at -65 degrees, and
a methyl barrier measured there is a different quantity from one measured
on the anti conformer. Forcing the backbone to 180 first gives 3.408.

The tell was not the size of the error but its DIRECTION -- the barrier
came out below propane's, and adding a remote methyl cannot lower a local
barrier. A tolerance wide enough to accept 3.171 would have hidden it.

### Koopmans hardness is wrong for the pair people actually use it on

Recorded here rather than only in `chem/conceptual_dft.py` because the trap is
general: an approximation that reproduces the first case you try is not
validated, and the second case is where it breaks.

Measured on real ORCA 6.1.1 B3LYP/def2-SVP runs of both textbook hard/soft
pairs:

| η (eV) | Koopmans | ΔSCF |
| --- | --- | --- |
| water | 4.57 | 8.06 |
| hydrogen sulfide | 3.90 | 6.93 |
| ammonia | 4.16 | 7.21 |
| phosphine | 4.27 | **7.02** |

Koopmans gets water/hydrogen sulfide right and **inverts ammonia against
phosphine**, making phosphine the harder — when hard nitrogen against soft
phosphorus is one of the most-used orderings in coordination chemistry. Every
molecule here has a NEGATIVE electron affinity, so its "LUMO" is an unbound
state belonging to the basis set rather than the molecule, and Koopmans reads
that number straight out.

Both ship. Koopmans is genuinely free from any job that has already run and
carries a caveat naming this failure on every descriptor;
`test_koopmans_inverts_ammonia_against_phosphine` asserts the inversion **on
purpose**, so if a future method stops inverting it the test fails and the
caveat can come off.

**ORCA compound jobs (`$new_job`) run all three ΔSCF calculations in one
input**, confirmed live — so this needed no notion of chained runs in the
service. The three `FINAL SINGLE POINT ENERGY` lines are told apart only by
POSITION, which is why `test_the_three_delta_scf_blocks_are_written_in_parser_order`
exists: swapping the cation and anion blocks flips the sign of both I and A,
still produces plausible numbers, and survived every other test in the file.

### A gbw remembers where it was born, and orca_plot goes there

Every ESP surface in the app failed -- `orca_plot exited 64 without
writing job.scfp.esp.cube` -- and the recorded hypothesis was that the
cube had been written under a name `_output_name` did not predict. **That
was wrong. No cube existed under any name.**

The real message, once the run was reproduced by hand:

    CANNOT OPEN FILE
    Filename: D:\OpenChemStudio-scratch\orca_job_933toma8\job.densitiesinfo

**A `.gbw` carries the ABSOLUTE path of the directory it was created in**
-- twice in the gbw, three times in the `.densitiesinfo` -- and orca_plot
follows it rather than looking in the working directory. Retaining a
wavefunction copies the files out of the scratch job directory and
deletes the directory, so the path is dead and type 43 dies with it.
Measured A/B, byte-identical files in the working directory both times:

    baked directory present   exit 0, job.scfp.esp.cube written
    baked directory absent    exit 64, no cube at all

Only ESP. Orbitals and electron density were re-measured in the broken
directory and produce their cubes normally, which is exactly why it read
as "the ESP feature is broken" rather than "the wavefunction store is".

Two traps while fixing it, both worth knowing generally:

- **Restoring only the two SMALL companions is enough.** `job.densities`
  and `job.densitiesinfo` are 35 KB and 1.8 KB against a 1.0 MB gbw; the
  gbw is read from the working directory and does not need copying. Test
  the cheap repair before building the expensive one.
- **The density name must match orca_plot's listing EXACTLY, and the
  listing is fully qualified** -- `D:\...\orca_job_x\job.scfp`, not
  `job.scfp`. The bare name is refused with `Wrong Density Name
  selected`, and this had been shipped for months because **a refused
  name still writes a cube** from the fallback density, which on a
  single-density job is the same one. The values were right; only the
  explicitness was missing. A qualified name also moves the OUTPUT, since
  ESP names its cube after the density.

**A probe that leaves state behind will lie to the next probe.** Having
recreated the baked directory to prove the hypothesis, three subsequent
"cold" runs in fresh directories all passed -- because that directory was
still there, process-wide, invisible to the test. The control that
mattered was deleting it and re-running.

### ORCA's LED summary block does not mean what it looks like it means

Recorded because a plan written without running it specified parsing the
wrong block, and the wrong numbers are plausible rather than absurd.

**`FINAL SUMMARY DLPNO-CCSD ENERGY DECOMPOSITION` is not an interaction
decomposition.** Its correlation lines split the complex's TOTAL
correlation energy into dispersive and non-dispersive parts, intra-fragment
correlation included. Verified by arithmetic against the same output, exact
to the last digit:

    Non dispersion (strong pairs)  =  intra strong pairs
                                    + (inter strong - dispersion strong)
                                    + singles
    -0.414932699                   =  -0.394372938 - 0.020556328 - 0.000003433

So that line reads **-260 kcal/mol** where the real non-dispersive
interaction is **-12.9**. Only the REF lines are what they appear to be:
`Electrostatics (REF.) + Exchange (REF.)` does equal the inter-fragment
reference interaction exactly.

**And `Total interaction` is not a binding energy** -- ORCA reports
**-428 kcal/mol** for BH3-CO, whose bond enthalpy is near -25. A
single-point LED partitions the complex's own energy, so the inter-fragment
part carries all the nuclear-electron attraction between fragments. A
binding energy needs the ISOLATED fragments, which is why `chem/orca_led.py`
writes three jobs.

With those, it reconciles: the six terms sum to -36.58 kcal/mol against a
supermolecular -36.62. **The 0.05 residual is nameable, not slop** -- it is
exactly the gap between the LED's own total and `FINAL SINGLE POINT ENERGY`,
i.e. how DLPNO splits the (T) correction. It is reported rather than hidden.

**`$new_job` does NOT generalise from delta-SCF.** Inside a compound job
ORCA restarts from the previous job's orbitals, which is valid for
delta-SCF (same geometry, different charges) and fatal here, because a
fragment has fewer atoms:

    Error: Input geometry does not match current geometry
    ORCA finished by error termination in GUESS       -- exit 55, 1 energy of 3

`PModel` on the fragment blocks fixes it. **`NOAUTOSTART` looks like the fix
and is not** -- it governs picking up a `.gbw` left on disk, not the restart
from the preceding block, and the run failed identically with it in place.

Two measurement traps from the cost estimate, both paid for once:

- **Residual disk is not peak disk, by a factor of 575.** benzene-water
  leaves 3.3 MB behind and used **1899 MB while running**. The first
  estimator was anchored on residual and under-predicted the thing that
  fills a drive by three orders of magnitude. Sample during the run.
- **The textbook cc-pVDZ contraction is wrong for this job.** 14 per
  first-row atom predicts 57 functions for BH3-CO; ORCA reports 75. Solving
  the two measured totals gives 20 and 5, confirmed against a third job it
  was not fitted to (BH3 alone: predicted 35, reported 35).

#### The two-point cost fit was an artefact. Six points, and it changed shape

The estimator was first fitted on BH3-CO and benzene-water, giving an
exponent of 4.20. **benzene-water is aromatic**, so the fit absorbed an
aromatic penalty into the exponent and then charged it to everything. On a
saturated pentane dimer it predicted 9960 s against a measured 1291 --
**7.7x too high**, the difference between "start it" and "do not bother".

Six compound jobs, one harness, peak disk sampled DURING the run:

    system            atoms  functions  aromatic   wall   peak scratch
    water dimer          6       60        0        15 s      35 MB
    BH3-CO               6       75        0        23 s     103 MB
    methanol dimer      12      120        0        48 s     220 MB
    benzene...H2O       15      180        1       644 s    1852 MB
    benzene dimer       24      300        2      2648 s    5564 MB
    pentane dimer       34      320        0      1291 s    2872 MB

    time    = 2.0064e-04 * f^2.69     worst residual x1.60
    scratch = 1.5004e-03 * f^2.51     worst residual x1.37

**The noise floor is x1.2** -- the same benzene fragment measured 280 s in
one run and 342 s in another -- so the fit is close to as good as this gets
without controlling the machine. Do not assert more tightly than that.

Three things that each produced a wrong exponent before being noticed:

- **A complex costs less than a monomer of the same size.** Half its
  electron pairs are inter-fragment and long-range, so DLPNO screens them
  out: methanol MONOMER at 60 functions takes 7 s where the water DIMER at
  60 takes 4.6. Fitting both populations together gave 1.72, which then
  under-predicted 320 functions sevenfold. Fit on complexes only.
- **Aromaticity is a x2.9 penalty and is NOT a size effect.** The methanol
  dimer has 28 correlated electrons and takes 23 s; benzene has 30 and takes
  280. Same electron count, twelve times the cost -- delocalisation defeats
  DLPNO's locality screening. It does **not** compound with ring count
  (1 ring x2.82, 2 rings x2.94), so it is a flat multiplier; a per-ring
  model predicted 7246 s for the benzene dimer against a measured 2648.
- **The fragment jobs are not a fixed fraction.** A x1.5 multiplier from
  BH3-CO (23 s compound vs 15 s complex) is wrong at the other end, where
  benzene-water is 644 vs 595 -- x1.08. Fit whole compound jobs directly.

With time no longer over-predicted, **scratch became the binding
constraint** at the top end: a 1200-function job is 10.7 hours (survivable)
and 78 GB (not, on most machines), so the refusal now triggers on either.

One more thing this work paid for, and it was a GUARD that found it rather
than review: `tests/test_layering.py` forbids a `ui/` module importing
RDKit, and the pre-launch cost dialog did exactly that to count fragments
with `Chem.GetMolFrags`. It reads as obviously fine in isolation, which is
the point -- the count now comes from `estimate_led_cost_for` in the chem
layer and the UI imports nothing chemical.

#### `EmbedMolecule` does NOT separate disconnected fragments

Found by running the app, after every test was green, and it is the best
argument in this file for doing live checks at all.

Building an ammonia/borane pair the way a user would -- draw two species,
generate 3D -- put the **N and the B 0.15 A apart**, interpenetrating.
There are no constraints between disconnected fragments, so the embedder
packs them at the origin. ORCA then ran the job perfectly happily and the
panel reported:

    Interaction energy (LED): 40619.295952 kcal/mol
    Electrostatics:            8251.870486 kcal/mol     (should be negative)

**Correct arithmetic, meaningless answer, presented as a plain number** --
the worst combination, and nothing anywhere said so. The parser was fine:
the same pair at a real geometry (B-N 1.66 A) gives -52.76 kcal/mol with a
0.006 residual, matching the offline run to every digit.

Two guards now, and the split matters. `estimate_led_cost_for` measures the
closest inter-fragment approach and REFUSES below 0.7 A (shorter than any
real bond -- H-H is 0.74) or beyond 8 A, before any compute. `parse_led`
adds a limitation past 300 kcal/mol, since a bad geometry is the common
cause of an impossible number but not the only one.

Anything else that consumes a drawn multi-fragment structure has the same
exposure. The embedder will not tell you.

### An engine and its own data table have to be run against each other

The Lewis adduct work shipped a Drago-Wayland parameter table and an
acceptor-detection engine that were each individually tested and green.
Run together, **the engine refused 14 of the 24 acids in its own table** --
every alcohol and phenol, pyrrole, chloroform. Nothing but running the two
against each other revealed it, and the fix was three new acceptor rules,
not a tweak.

Iodine and benzene were among the refused, and both are pairs in the
table's *own validation set* — so the engine could not reproduce the data
that justified shipping the table.

`test_every_acid_in_the_shipped_table_passes_the_acceptor_gate` is the
guard. Any future data table should get the equivalent.

The most useful of the three rules is worth knowing on its own: **a
hydrogen bond and a halogen bond are the same mechanism**, donation into
the sigma* of a polarised single bond, differing only in the heavy atom.
They share `LOW_LYING_SIGMA_STAR` because that is accurate, not
convenient. A consequence: alcohols and amines come out AMBIPHILIC, since
the oxygen donates its lone pairs while its O-H accepts. Water is the
textbook case, and several tests had to be updated to say `ambiphilic`
where they had said `donor` — the behaviour change was correct.

### The two orbital measures disagree on the motivating case

Measured on real ORCA delta-SCF runs of the pair the whole feature exists
for:

| | frontier gap | HSAB \|Δη\| |
| --- | --- | --- |
| BH₃ + CO | **8.13 eV** | 1.63 eV |
| BF₃ + CO | 10.90 eV | **0.89 eV** |

Borane binds CO strongly enough to isolate the adduct; BF₃ barely binds it.
The frontier gap says so. **The |Δη| proxy says the opposite**, because
CO's computed hardness (8.40) lands near BF₃'s (9.29) rather than
reflecting the softness the qualitative argument gives it — a single
number on the η scale is not Pearson's classification.

This is reported, not resolved, and it is the strongest justification for
the no-combined-score design: an average would have split the difference
on a case where one line is simply right.
`test_the_two_orbital_lines_disagree_on_carbon_monoxide` asserts it on
purpose.

Two measurement traps from the same work, both already paid for once:

- **A fixture labelled "verbatim from a real run" had energies typed from
  memory.** The assertions used `abs=0.01` tolerances, which were loose enough
  to hide it — so the arithmetic was being checked against itself rather than
  against the run. Copy the numbers, and assert tightly enough that a wrong
  fixture cannot pass.
- **`X = '' or (...)` mutates nothing**, since the empty string is falsy and
  the original is returned. Two mutations written that way reported a
  confident SURVIVED for changes never applied. A mutation script must verify
  its edit changed behaviour, not merely that the pattern matched.
- **A restored file can still run as the MUTATED one, from stale bytecode.**
  Python validates a `.pyc` against the source's mtime and size, both of
  which a write-mutate-restore cycle can leave unchanged within one mtime
  tick. Seen live: a restored `chem/lewis.py` read `0` on disk and in
  `inspect.getsource`, while the imported module held the mutated `1` — the
  test "failed after restore" and the source was innocent. Any mutation
  script should `rm -rf` the `__pycache__` directories between arms, or run
  with `PYTHONDONTWRITEBYTECODE=1`, and a surprising post-restore result
  should be re-checked with the cache cleared before it is believed.
- **A surviving mutation found a real sign error nobody would have read.**
  The Drago W term is ADDED (`−ΔH = E_A·E_B + C_A·C_B + W`) and was written
  subtracted. Every test passed, because every acid the tests touch has
  `W = 0` — only two entries in the whole table have one. Coverage of a
  parameter's *common* value is not coverage of the parameter.

### Alex has the paywalled papers. Ask before hedging around one.

Three primary sources that this work had been treating as unobtainable are
on disk at `D:\Xaero Stuff\Documents\Sci Downloads\`: Drago & Wayland 1965,
Parr & Pearson 1983, Pearson 1988, and **Mayo, Olafson & Goddard 1990** (the
DREIDING paper — this file and three others had asserted for months that
Dreiding was simply unavailable, which was the absence of a finding rather
than one; see `docs/DREIDING_ASSESSMENT.md`, and note the PDF's text layer
corrupts the atom-type labels `C_3`/`C_R` that the parameters key on).
**Reading them changed real claims**,
so when a source is needed, ask rather than write "paywalled, orderings
pinned instead".

There is no PDF text extractor in the project venv and `pdftoppm` is not
installed, so `Read` on a PDF fails. `uv pip install --system pymupdf` and
`fitz` works.

What the papers changed:

- **The 1965 E/C parameters are on a DIFFERENT SCALE from the shipped ones**
  and must not be mixed. That paper normalises iodine to E_A = C_A = 1.000
  ("relative to E_A and C_A of iodine being 1"); the modern compilation puts
  iodine at 0.50 and 2.0. Its *observed enthalpies* are scale-free, and are
  now a second, independent validation set — 12 values across three acid
  series.
- **The model's best test is one it fails.** The paper measures F-strain in
  trimethylborane's amine adducts: 8.2 kcal/mol for trimethylamine, 1.5 for
  dimethylamine, nothing for the two smaller ones. An E/C equation has no
  steric term, so it *must* over-predict exactly those two — and does, by
  6.1 and 1.1. A table that fitted all four would mean the parameters had
  absorbed a steric effect they are not supposed to contain.
- **Every hardness value quoted from memory was right**, and none of them
  should have been quoted from memory. η(H₂O)=9.5, η(NH₃)=8.2, η(H₂S)=6.2,
  η(PH₃)=6.0, all confirmed in Pearson 1988 Table II. They are asserted now.
- **A claim in this file's own tests was wrong.** ΔSCF's electron-affinity
  error is NOT one-directional. ΔSCF returns −3.6 to −3.8 eV for all four
  molecules, whose true affinities span −1.9 to −6.4: the unbound anion
  barely knows which molecule it is on. That *compresses* the hardness
  scale, and the NH₃/PH₃ ordering it gets right survives by **0.19 eV**
  where experiment separates them by 2.2. The ordering is correct; the
  margin is not something to lean on.
- **Pearson's own rows round to ±0.1** — H₂S's (I−A)/2 gives 6.3 against a
  printed η of 6.2 — so a self-consistency check on transcription needs
  `abs=0.15`, not `0.05`.

Gutmann donor/acceptor numbers were assessed and **not shipped**. The
accessible source (Frontiers in Chemistry 2022, 10.3389/fchem.2022.861379)
tabulates ionic liquids and deep eutectic solvents rather than the classical
molecular table, and reports its own acceptor-number model failing outright
("no correlation could be found"), concluding it supports "qualitative and
relative criteria but not an absolute and quantitative model". Note the
donor number is *defined* as −ΔH against SbCl₅, which is already in the
Drago table — so that line is partly available already.
