from __future__ import annotations

import os
import sys
import gc
import weakref
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Bundled first-party plugins (src/openchem/plugins/ is the *loader*;
# plugins/ at the repo root is content it loads) aren't part of the
# installable `openchem` package, but tests still need to import their
# modules directly. plugins/<name>/ has no __init__.py, so this relies on
# PEP 420 implicit namespace packages -- `import ai_assistant.providers`
# resolves fine once `plugins/` is on sys.path.
PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"
if str(PLUGINS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGINS_DIR))

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QSettings
from PySide6.QtWidgets import QApplication


# Weak refs to every object `deleteLater()` was called on since the current
# test started. Weak so that merely watching one never keeps it alive.
_deferred_deletes_during_test: list[weakref.ref] = []

_original_delete_later = QObject.deleteLater


def _tracking_delete_later(self, *args, **kwargs):
    try:
        _deferred_deletes_during_test.append(weakref.ref(self))
    except TypeError:  # a handful of Qt types are not weak-referenceable
        pass
    return _original_delete_later(self, *args, **kwargs)


QObject.deleteLater = _tracking_delete_later


@pytest.fixture(autouse=True)
def flush_deferred_deletes():
    """Complete, per object, every deferred delete the test asked for.

    `deleteLater()` only POSTS an event, and measured against this Qt
    build, `QApplication.processEvents()` does not deliver it -- a
    DeferredDelete posted at event-loop level 0 is delivered only when an
    actual event loop at that level returns. A pytest run never enters
    one, so anything a test deletes this way is not destroyed at the end
    of that test; it sits in the process-wide queue for the whole session.

    That queue is a landmine, and the fuse is any test that later causes a
    NESTED event loop to run -- which drains the ENTIRE backlog at once,
    thousands of allocations later, in a place with no relationship to the
    code that queued it. QtWebEngine spins such loops internally while a
    page loads, so the webview tests are where it goes off:
    `test_ketcher_editor_backend.py` died with a Windows access violation
    inside its `processEvents` pump, and the backlog live at that moment
    was nine `IrViewWidget`s queued five files earlier. Left to chance it
    fired on 3 full runs and then not on the next 6, which is what made it
    read as flaky webview tests rather than as a bug five files away;
    forcing one nested loop before each ketcher test makes it a 12-second
    reproduction that crashes 8 times out of 8.

    THIS FIXTURE DOES NOT FIX THAT CRASH, and nothing here claims to. All
    it does is stop the backlog existing -- measured 18 undelivered
    deletes across a full run, now 0. Against the forced-drain
    reproduction it still went off 2 times out of 2, on the widgets
    `test_jobs_panel.py` abandons.

    A COMPANION FIXTURE THAT DESTROYED THOSE ABANDONED WIDGETS WAS TRIED
    AND REVERTED -- do not re-add it without reading this. It tracked
    every top-level widget of one of this app's classes (112 of them
    survived a full run) and destroyed each at teardown with the same
    per-object `deleteLater()` plus flush used below. On the base it was
    developed against it looked right: the forced-drain reproduction went
    from 5 crashes out of 5 to 8 passes out of 8. It then crashed the
    suite outright on master, in an interleaved A/B with an identical
    file set: **8 of 8 full runs died with an access violation with it
    active, 8 of 8 completed with it neutered**, isolated to that one
    fixture while this one stayed on. The crash sites were the
    MainWindow-plus-webview tests that pump events
    (`test_main_window_docking_visualization.py`,
    `test_ketcher_editor_backend.py`), neither of them at fault.
    Re-ordering it to finalise after `dispose_web_engine_views` was tried
    and did NOT help -- still 5 crashes out of 5 -- so the cause is not
    simply that a live view was taken down as a child, and destroying an
    abandoned widget synchronously at teardown is unsafe here for a
    reason that is still not understood.

    So the crash that started all this is NOT fixed. Do not read the
    presence of this fixture as evidence that it is.

    FLUSHED PER OBJECT, never as `sendPostedEvents(None, DeferredDelete)`.
    The global form is exactly the nested-loop drain described above -- it
    empties the whole queue, including entries this test knows nothing
    about, which is the crash rather than the cure.

    Nothing here calls `deleteLater()` itself, so a widget a test still
    wants alive is untouched: this only finishes deletions already
    requested, at the first moment Qt's own semantics allow.
    """
    _deferred_deletes_during_test.clear()

    yield

    queued = [ref() for ref in _deferred_deletes_during_test]
    _deferred_deletes_during_test.clear()
    for obj in queued:
        if obj is not None and shiboken6.isValid(obj):
            QCoreApplication.sendPostedEvents(obj, QEvent.Type.DeferredDelete)


# Weak refs to every QWebEngineView built since the current test started.
# Weak so that merely watching a view never keeps it alive.
_views_created_during_test: list[weakref.ref] = []


def _track_web_engine_views() -> bool:
    """Start recording `QWebEngineView` construction, once. True if views
    can now be tracked at all.

    Wrapping the constructor is deliberate, and the second thing tried.
    The obvious approach -- sweep `QApplication.allWidgets()` in teardown
    and destroy any view found -- reads better and is wrong: Chromium
    constantly creates and destroys its OWN internal QWidgets for each
    page, so enumerating every widget while that churn is in flight
    faulted outright (an access violation inside `allWidgets()`, roughly
    one run in six). Recording construction only ever yields the handful
    of views the tests themselves asked for, and never races Chromium's
    private widgets.

    Nothing happens until something imports the web-engine module --
    until then no view can exist, and importing it here would drag
    Chromium into the ~1000 tests that never touch a webview.
    """
    module = sys.modules.get("PySide6.QtWebEngineWidgets")
    if module is None:
        return False
    view_type = module.QWebEngineView
    if getattr(view_type.__init__, "_openchem_tracks_views", False):
        return True

    original_init = view_type.__init__

    def tracking_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _views_created_during_test.append(weakref.ref(self))

    tracking_init._openchem_tracks_views = True
    view_type.__init__ = tracking_init
    return True


@pytest.fixture(autouse=True)
def dispose_web_engine_views():
    """Destroy any `QWebEngineView` a test created, before the next runs.

    Without this the suite HANGS, and that is the entire reason the
    fixture exists -- nothing in the code below hints at it. Every
    `QWebEngineView` spawns its own Chromium helper processes, and Qt
    reaps them only when the pytest process itself exits, not when the
    last Python reference to a view goes away. So they accumulate: nine
    test files build web-engine-backed objects and none disposed of them,
    which carried one run to 116 live `QtWebEngineProcess.exe` before
    something (handles, memory, a port) gave out and pytest blocked
    forever at around 30%, sitting at 14 seconds of CPU across 40 minutes
    of wall clock while printing nothing at all. Since the strays die
    with the process, a post-mortem finds zero of them and looks
    perfectly healthy -- the count only means anything sampled DURING a
    run, never after one.

    Pumping `DeferredDelete` is what makes it work at all: `deleteLater()`
    only posts an event, so with nothing draining it the destruction never
    happens and the processes stay. There is deliberately no blocking wait
    afterwards -- measured, the count stays flat without one, because
    Chromium reaps each helper on its own once the page is destroyed.

    `stop()` is precautionary, not proven. Some tests build a backend and
    never wait for it
    (`test_set_render_option_before_ketcher_is_ready_does_not_raise` is
    exactly that), so teardown can land mid-load; cancelling first is the
    cheap defensive move. Removing it did NOT reproduce any crash in 8
    runs of the pair that used to fail, so do not read it as the fix --
    the fix is the per-view flush below.

    Scope is "created during this test", so a view meant to outlive one
    test would be destroyed under it. Nothing does that today -- every web
    view in the suite is built inside the test or a function-scoped
    fixture -- and anything that ever needs to should hold its view in a
    wider-scoped fixture and be excluded here explicitly, rather than
    this quietly growing an exception.
    """
    tracking = _track_web_engine_views()
    _views_created_during_test.clear()

    yield

    if not tracking:
        return
    created = [ref() for ref in _views_created_during_test]
    _views_created_during_test.clear()
    live = [v for v in created if v is not None and shiboken6.isValid(v)]
    if not live:
        return
    for view in live:
        view.stop()
        view.deleteLater()
        # Flushed per view, never as sendPostedEvents(None, DeferredDelete).
        # The global form drains EVERY pending deferred delete in the
        # process, including ones unrelated tests left queued on objects
        # Python had already collected -- which double-freed and crashed
        # here, but only once some earlier test had queued one (jobs-panel
        # widgets, say), so it looked like a webview bug and was not.
        QCoreApplication.sendPostedEvents(view, QEvent.Type.DeferredDelete)


@pytest.fixture(scope="session")
def qapp():
    """A QApplication is required for QObject-derived types used throughout
    the app (EventBus signals, QThreadPool, QUndoStack) even in headless
    tests. Session-scoped and offscreen so the suite runs in CI with no
    display.
    """
    app = QApplication.instance() or QApplication([])
    yield app


#: The measured WebGL capability, cached for the session. A dict rather
#: than `lru_cache` so the "not measured yet" state is distinguishable
#: from a measured zero.
_WEBGL: dict[str, object] = {}

#: The page the probe loads. It asks a BARE CANVAS, not the application's
#: viewer page: the gate must establish that the PREREQUISITE is missing,
#: not that our own code failed to use it. If WebGL works and 3Dmol still
#: cannot build a viewer, that is a real bug and the test must still fail.
_WEBGL_PROBE_PAGE = """
<!doctype html><html><body style="margin:0">
<script>
window.__probe = function () {
  var made = 0, detail = '';
  for (var i = 0; i < 2; i++) {
    try {
      var c = document.createElement('canvas');
      c.width = 64; c.height = 64;
      document.body.appendChild(c);
      var gl = c.getContext('webgl') || c.getContext('experimental-webgl');
      if (gl) {
        made++;
        if (!detail) {
          var dbg = gl.getExtension('WEBGL_debug_renderer_info');
          detail = String(dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)
                              : (gl.getParameter(gl.RENDERER) || 'unnamed'));
        }
      } else if (!detail) {
        detail = 'getContext returned null on attempt ' + (i + 1);
      }
    } catch (e) { if (!detail) detail = String(e); }
  }
  return JSON.stringify({contexts: made, detail: detail});
};
</script></body></html>
"""


def _measure_webgl(app) -> tuple[int, str]:
    """How many WebGL contexts a `QWebEnginePage` can really create here.

    **The suite's older gate was `QT_QPA_PLATFORM == "offscreen"`, which is
    a statement about the Qt platform and not about WebGL.** They are not
    the same condition, and the difference is exactly what turned CI red:
    measured on a developer machine with a GPU, `offscreen` grants
    2 contexts (ANGLE/D3D11), so the viewer tests run and pass there --
    while a GPU-less CI runner grants none and 3Dmol's `viewer` is never
    defined at all.

    Deliberately NOT wrapped in a blanket try/except. An inconclusive
    probe RAISES rather than reporting zero, because "I could not find
    out" is not "the prerequisite is absent", and turning the first into
    the second is how a real failure gets skipped silently.
    """
    import json
    import time

    from PySide6.QtWebEngineWidgets import QWebEngineView

    def pump(predicate, seconds: float) -> bool:
        deadline = time.time() + seconds
        while time.time() < deadline:
            app.processEvents()
            if predicate():
                return True
            time.sleep(0.02)
        return False

    view = QWebEngineView()
    view.resize(200, 150)
    view.show()
    try:
        loaded: list[bool] = []
        view.loadFinished.connect(loaded.append)
        view.setHtml(_WEBGL_PROBE_PAGE)
        if not pump(lambda: bool(loaded), 30):
            raise RuntimeError(
                "the WebGL probe page never finished loading, so WebGL "
                "availability could not be established"
            )

        answer: list[object] = []
        # A STRING, because runJavaScript on this Qt build marshals
        # primitives only -- an object arrives as '' and would be
        # indistinguishable from a script that returned nothing.
        view.page().runJavaScript("window.__probe()", answer.append)
        if not pump(lambda: bool(answer), 30):
            raise RuntimeError(
                "the WebGL probe did not return, so WebGL availability "
                "could not be established"
            )
        raw = answer[0]
        if not raw:
            raise RuntimeError(
                f"the WebGL probe returned {raw!r}; availability could not "
                f"be established"
            )
        report = json.loads(str(raw))
        return int(report["contexts"]), str(report["detail"])
    finally:
        view.stop()
        view.setParent(None)
        view.deleteLater()
        # Per widget, never the global drain -- see dispose_web_engine_views.
        QCoreApplication.sendPostedEvents(view, QEvent.Type.DeferredDelete)


def webgl_contexts(app) -> tuple[int, str]:
    """The cached `(contexts, detail)` for this session."""
    if "result" not in _WEBGL:
        _WEBGL["result"] = _measure_webgl(app)
    return _WEBGL["result"]  # type: ignore[return-value]


def webgl_skip_reason(app) -> str | None:
    """The reason to skip, or None to RUN.

    A plain function rather than logic buried in the fixture so
    `tests/test_webgl_gate.py` can check both answers without a webview,
    and so the "run" answer is a value that can be asserted rather than
    the absence of an exception.
    """
    contexts, detail = webgl_contexts(app)
    if contexts < 1:
        return (
            "Skipped: no usable WebGL context available in this environment "
            f"({detail})"
        )
    return None


def grid_platform_is_offscreen() -> bool:
    """Whether Qt's `offscreen` platform is in use.

    Named and shared because it is consulted with BOTH polarities, which
    is why it is a predicate rather than a mark. `grid_display` skips
    when it is True; `test_a_gallery_that_cannot_be_built_is_reported`
    skips when it is False, because that test asserts the FAILURE path
    and so `offscreen` is its prerequisite rather than its obstacle.
    """
    return os.environ.get("QT_QPA_PLATFORM", "") == "offscreen"


def grid_skip_reason(app) -> str | None:
    """Why the `createViewerGrid` guards cannot run here, or None to RUN.

    **TWO CONDITIONS, AND THEY ARE DIFFERENT IN KIND.** Keeping them in
    one place is the point: this predicate had two private copies, in
    `test_mol3d_viewer_backend.py` and `test_spatial_annotations.py`,
    which is how a third would have appeared with the gallery overlay.

    **The platform half is an ADMITTED GATE, not a probe**, and the
    ladder in `test_mol3d_viewer_backend.py` is its justification: under
    `offscreen` a bare WebGL context works, twelve work, one 3Dmol viewer
    works, six work -- and `createViewerGrid` throws for a grid of a
    SINGLE cell. Nothing underneath predicts it, so a capability probe
    here would gate a test on its own subject and turn a real regression
    into a silent skip. Why the grid call specifically fails is still
    unknown.

    **The WebGL half is MEASURED**, by `webgl_skip_reason` above, and it
    is what makes these guards safe to run anywhere. A GPU-less machine
    -- the hosted CI runner is one, Windows platform or not -- has no
    context at all, so the grid could never build and the honest answer
    is a skip naming the absent prerequisite rather than a failure
    blaming the code. Without it, running these on CI under
    `QT_QPA_PLATFORM=windows` would fail rather than skip.
    """
    if grid_platform_is_offscreen():
        return (
            "Skipped: $3Dmol.createViewerGrid does not work under Qt's "
            "offscreen platform (measured: WebGL contexts and individual "
            "viewers are fine there; the grid call is not). Run with "
            "QT_QPA_PLATFORM=windows."
        )
    return webgl_skip_reason(app)


@pytest.fixture
def grid_display(qapp):
    """Skip unless a real `$3Dmol.createViewerGrid` can be built here.

    Requested by every guard that drives the conformer gallery. A
    fixture rather than a `skipif` mark because the WebGL half has to
    MEASURE, and measuring needs a `qapp` -- the same reason `webgl`
    below is one.
    """
    reason = grid_skip_reason(qapp)
    if reason is not None:
        pytest.skip(reason)


@pytest.fixture
def webgl(qapp):
    """Skip only when a WebGL context genuinely cannot be created.

    Requested by the tests that need the real 3Dmol viewer to exist. It
    measures rather than inferring from the platform name, so:

    - a developer machine (with or without `QT_QPA_PLATFORM=offscreen`)
      has WebGL, the tests RUN, and a genuine regression still fails;
    - a GPU-less CI runner has none, and they skip with a reason saying
      so rather than failing and masking every gate behind them.
    """
    reason = webgl_skip_reason(qapp)
    if reason is not None:
        pytest.skip(reason)
    return webgl_contexts(qapp)[0]


@pytest.fixture(scope="session", autouse=True)
def _isolated_settings_for_higher_scopes(tmp_path_factory):
    """The same redirection, in force before any function-scoped fixture is.

    `isolated_settings` below is FUNCTION-scoped, and pytest sets
    higher-scoped fixtures up FIRST -- so a `scope="module"` fixture that
    builds a `Settings` or a `MainWindow` runs while `QSettings` is still
    the real one. Five fixtures in this suite do exactly that, and
    `tests/test_settings_isolation.py` could not see it because that guard
    is itself function-scoped and therefore always runs inside the patch.

    MEASURED, not reasoned about. Reading the real key's last-write time
    either side of one run of `tests/test_right_dock_width.py`:

        before   13:39:20   plugins/project_directory = .../tmpes9xm92a/none
        after    13:41:30   plugins/project_directory = .../tmpfk04ymjp/none

    -- a live rewrite of the developer's own registry, by a module-scoped
    fixture pointing at a temp directory that no longer exists.

    This does NOT replace the per-test fixture: tests must still not see
    each other's writes, and that one gives each its own file. This is the
    floor underneath it, so nothing lands in the registry no matter which
    scope built it.
    """
    import openchem.app.settings as settings_module

    ini_path = tmp_path_factory.mktemp("settings-session") / "qsettings.ini"
    patch = pytest.MonkeyPatch()
    patch.setattr(
        settings_module,
        "QSettings",
        lambda *_args, **_kwargs: QSettings(str(ini_path), QSettings.Format.IniFormat),
    )
    yield
    patch.undo()


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Point `Settings` at a throwaway INI file under `tmp_path`.

    `openchem.app.settings.Settings` wraps `QSettings(ORG_NAME, APP_NAME)`,
    which on Windows is backed by the real, persistent registry key this
    app's actual installs use. Without isolation, any test that writes a
    setting (`plugins/project_directory`, as the main-window tests do)
    pollutes the real app's settings on whatever machine runs the suite.

    REPLACING THE CONSTRUCTOR IS THE POINT, and it is the second thing
    tried. The obvious approach -- `setDefaultFormat(IniFormat)` plus a
    per-test unique org/app name -- reads like it isolates and only half
    does. `setDefaultFormat` is documented to apply to exactly the
    `QSettings(organization, application)` constructor used here, and it
    does not:

        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.defaultFormat()          -> Format.IniFormat
        QSettings("Org", "App").format()   -> Format.NativeFormat   # !
        QSettings("Org", "App").fileName() -> \\HKEY_CURRENT_USER\\...

    So writes still went to the registry, just under a per-test name --
    which did protect the real "OpenChemStudio" key, and left **84 junk
    keys per suite run** littered under HKCU\\Software instead, one per
    test, named after the test, persisting forever. Measured by clearing
    them and re-running.

    Building the QSettings from an explicit file path sidesteps the format
    question entirely: there is no org/app lookup and no registry to fall
    back to, and `tmp_path` is cleaned up by pytest. See
    `tests/test_settings_isolation.py`, which fails if this regresses.
    """
    import openchem.app.settings as settings_module

    ini_path = tmp_path / "qsettings.ini"

    # One file per test, shared by every Settings built during it -- several
    # tests construct one directly and let MainWindow construct another, and
    # they have always seen each other's writes.
    def _file_backed_qsettings(*_args, **_kwargs):
        return QSettings(str(ini_path), QSettings.Format.IniFormat)

    monkeypatch.setattr(settings_module, "QSettings", _file_backed_qsettings)


def synthetic_nmr_spectrum(mol, molecule_uuid: str = "mol-1"):
    """A deterministic NMRSpectrumResult for a molecule, for tests that need
    *some* shift values to exercise signal grouping, plotting or selection.

    Replaces the empirical SMARTS estimator these tests used to borrow.
    That estimator was removed for collapsing distinct signals onto
    identical values (11 of propranolol's 16), but the deeper point is that
    a test of grouping or rendering should never have depended on a
    predictor's accuracy in the first place -- it only needs values that
    are distinct and reproducible.

    Shifts are spread by atom index within each element's usual window, so
    every atom gets a different value and grouping/overlap behaviour is
    observable rather than accidental.
    """
    from openchem.domain.scientific_result import NMRSpectrumResult

    values: dict[int, float] = {}
    elements: dict[int, str] = {}
    protons = carbons = 0
    for atom in mol.GetAtoms():
        symbol = atom.GetSymbol()
        if symbol == "H":
            values[atom.GetIdx()] = round(0.9 + 0.37 * protons, 3)
            protons += 1
        elif symbol == "C":
            values[atom.GetIdx()] = round(18.0 + 7.3 * carbons, 3)
            carbons += 1
        else:
            continue
        elements[atom.GetIdx()] = symbol

    return NMRSpectrumResult(
        spectrum_type="nmr_calibrated",
        name="Synthetic test spectrum",
        units="ppm",
        method="test",
        molecule_uuid=molecule_uuid,
        values=values,
        elements=elements,
    )




def painted(widget, width: int = 400, height: int = 300):
    """Render `widget` and return the QImage, forcing a real paintEvent.

    `repaint()` and `update()` are BOTH no-ops on a widget that was never
    shown -- measured at zero paintEvent calls each. Rendering into an
    image is what actually runs the painter. See CLAUDE.md.
    """
    from PySide6.QtGui import QImage

    widget.resize(width, height)
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image)
    return image


def ink(widget, width: int = 400, height: int = 300) -> int:
    """How many sampled pixels differ from the background colour.

    "Was anything drawn" cannot be answered by checking for a
    non-transparent pixel: every one of these widgets fills an opaque
    background first, so alpha is set everywhere before a single mark is
    made, and such an assertion passes against a paintEvent that draws
    nothing at all. Measured -- an EMPTY spectrum widget covers all 30,000
    sampled pixels with alpha.

    Counting pixels that differ from the most common colour measures marks
    instead. Compare it against the same widget WITHOUT data rather than
    against a fixed number: axes, frames and labels already account for
    200-600 marks before any content exists, and that floor moves whenever
    the chrome changes.
    """
    from collections import Counter

    image = painted(widget, width, height)
    pixels = [
        image.pixelColor(x, y).rgba()
        for x in range(0, width, 2)
        for y in range(0, height, 2)
    ]
    background, _ = Counter(pixels).most_common(1)[0]
    return sum(1 for pixel in pixels if pixel != background)


#: Every `MainWindow` the suite builds, held for the whole session.
#:
#: THE TEARDOWN COLLECT DESTROYS MAIN WINDOWS, and until this was measured
#: nobody knew it did. `pytest_runtest_logfinish`'s docstring said the
#: collect "does not destroy anything itself" -- it does: a MainWindow a
#: test builds has no Qt parent, so PySide gives Python ownership, and
#: freeing the wrapper deletes the C++ window. The collect is what frees
#: it, because the window sits in a reference cycle nothing else breaks.
#:
#: Destroying one corrupts the heap. Windows fatal exception 0xc0000374,
#: raised inside the collect, in whichever test is unlucky. Measured on a
#: two-file, 20-second reproduction:
#:
#:     retain nothing                            crashed
#:     retain MainWindow                         clean
#:     retain the viewer backends                crashed
#:     retain QWebEngineView + QWebChannel       crashed
#:     gc.DEBUG_SAVEALL (free nothing at all)    clean
#:
#: `PYTHONMALLOC=debug` reports nothing, so the corruption is in the C++
#: heap rather than Python's allocator.
#:
#: **Leaving them alive is this project's own measured conclusion**, twice
#: over: CLAUDE.md records two separate attempts to destroy abandoned
#: MainWindows, both of which made the suite crash MORE. What was missing
#: was the realisation that the collect was destroying them anyway. This
#: makes "leave them" true rather than aspirational.
_retained_windows: list = []


def _retain_main_windows() -> None:
    """Hold every MainWindow, so the teardown collect cannot free one."""
    from openchem.app.main_window import MainWindow

    if getattr(MainWindow, "_openchem_retained", False):
        return
    original = MainWindow.__init__

    def __init__(self, *args, **kwargs):
        original(self, *args, **kwargs)
        _retained_windows.append(self)

    MainWindow.__init__ = __init__
    MainWindow._openchem_retained = True


_retain_main_windows()


#: Whether the test that just finished used Qt at all.
_used_qt = [False]


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem):
    _used_qt[0] = "qapp" in getattr(item, "fixturenames", ())


def pytest_runtest_logfinish(nodeid, location):
    """Collect Python's cycles between tests, not during a later one.

    THE MEASUREMENT THIS COMES FROM. Instrumenting `QObject.destroyed` --
    the only event that runs a C++ destructor -- over a full run recorded
    **138 widgets whose C++ object was destroyed inside a LATER test than
    the one that built it**, from seven files, 104 of them from
    `test_quantum_chemistry_panel.py`. That is the crash CLAUDE.md
    describes, measured directly: a destructor running from inside Qt's
    event dispatch in an unrelated test, on Windows an access violation.

    Why these outlive their test at all: a panel subscribes to the
    EventBus, which stores the BOUND METHOD in `_handlers`, so the bus
    holds the panel and the panel holds the bus. Reference counting cannot
    break a cycle, so nothing is freed when the test's locals go out of
    scope -- it waits for the cyclic collector, which runs whenever it
    likes. Measured per class: `JobsPanel` (no subscription) dies by
    refcounting; `DockingPanel` survives refcounting and needs the cyclic
    collector; `PropertyPanel` survives both and is a genuine leak.

    **THIS DOES DESTROY THINGS, and a previous version of this docstring
    said otherwise for three phases of UI work.** Freeing a PySide wrapper
    that owns its C++ object deletes that object, and a widget a test
    builds without a Qt parent IS Python-owned. So this collect is not
    merely choosing a moment; it is the thing that frees them.

    That mattered enormously in one case. Destroying a `MainWindow`
    corrupts the heap, and this hook was destroying every one the suite
    built -- which is why `_retained_windows` above exists and why
    fifteen full runs went into blaming widget counts instead. CLAUDE.md
    has it under "SOLVED: the teardown collect was DESTROYING
    MainWindows".

    What IS true, and is the reason to keep it: a teardown hook is a
    moment with no Qt event dispatch in progress, so an ordinary panel is
    destroyed somewhere safe rather than inside an unrelated test's event
    loop. A companion fixture that instead forced destruction with
    `deleteLater()` was tried twice, by two people, and crashed the suite
    both times -- see CLAUDE.md. Choosing the moment is right; claiming
    nothing happens at that moment was not.

    Gated on `qapp` because most of this suite is pure chemistry and
    cannot leave a widget behind. Measured over a full run:

        no collect          138 late destructions   116 s
        collect always        0 late destructions   326 s
        collect if qapp       4 late destructions   171 s   <- this

    The four that remain are all within `test_quantum_chemistry_panel.py`
    itself. Closing them costs another 155 seconds on every run, which is
    not worth it for four same-file destructions when the crash being
    chased was cross-file.
    """
    if _used_qt[0]:
        _used_qt[0] = False
        gc.collect()
