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

A clean run is **3-4.5 minutes**, ending at `2803 passed, 2 skipped,
1 deselected` (measured 2026-08-07 with the presentation-layer Phase 0/1
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
- **Ketcher's bond ids are RDKit's bond indices.** Both are dense and in
  molfile order; verified by loading one molblock into each and comparing
  every (begin, end) pair, and again end-to-end through the real backend
  (selecting Ketcher bond 1 of ethanol arrived in Python as index 1, the
  C-O bond). No translation table is needed, and one would be a place for
  a silent off-by-one to live.

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

#### A PLACEHOLDER WIDGET IN A TAB THAT ALREADY HOLDS WIDGETS CORRUPTS THE HEAP

Windows fatal exception `0xc0000374`, raised inside the teardown
`gc.collect()`, in a test hundreds of tests away from the panel that
built the widget. **It is deterministic**, which is what makes it
tractable -- unlike the access violations elsewhere in this file, whose
rate moves between batches.

    placeholder in a tab that is otherwise EMPTY        safe
    placeholder in a tab that already holds widgets     corrupts the heap

So the three deferred quantum tabs (1D Signals, IR, Surfaces) get a real
placeholder; Hybrid says it through the `_hybrid_summary_label` that
already existed, and the correlation tabs PAINT the message inside
`NmrCorrelationPlotWidget`. Neither of the latter two adds a widget, and
painting it lands the message where the peaks would be, which is better
drawing anyway.

**Three hypotheses were tested against the full suite and are wrong** --
recorded so nobody pays for them twice:

- not the `dict[QWidget, ...]` holding the placeholders (removing it:
  still crashed, same test index)
- not hiding the sibling content (suppressing every visibility change:
  still crashed, same test index)
- not the new test file (removing it: still crashed, four tests earlier)

The mechanism is **not understood**. "Python-derived widget" is not it:
`WrappedLabel` and `CollapsibleSection` are Python-derived and live in
these same panels. Nor is it the widget class, since a plain `QLabel`
still killed the full suite. What tracks the crash exactly is *where* the
widget is added.

Two method notes, both of which nearly produced wrong answers:

- **Pin the baseline before blaming yourself, and before blaming the
  suite.** `git stash`-ing everything and running master gave a clean
  2788, which is what turned "probably the documented flakiness" into
  "definitely mine". CLAUDE.md's own warning that the rate moves would
  otherwise have excused it.
- **A mutation script must verify its edit LANDED.** Three arms were run
  from a Git-Bash `/tmp` path that the Windows Python could not read, so
  all three silently tested the unmodified file and reported a confident
  CRASH -- the control, three times. Every arm since asserts the edit is
  present in the file before running.

## Verification standard

This project's convention, established across many sessions: **claims are
measured, not asserted.** Before shipping a formula, a threshold, a parser
regex or a model, verify it against a primary source or a real run and record
what was checked. Several things were deliberately NOT shipped because they
could not be validated (Miller polarizability, HLB, TSEI) — that is a normal
outcome here, not a failure.

Comments explain **why**, especially where something is non-obvious or was got
wrong once. A comment restating the code is noise.

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
Parr & Pearson 1983, and Pearson 1988. **Reading them changed real claims**,
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
