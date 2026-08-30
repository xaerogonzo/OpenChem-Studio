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


def flush_at_dispose(value: str | None) -> bool:
    """Whether `dispose()` flushes the delete itself, from the env value.

    A pure function so the mapping is testable without touching the
    process environment -- the two-level split `ui/visual_check.py` and
    `expansion_skip_reason` both use. **Anything but the exact string
    `"0"` means flush**, so a typo'd value fails SAFE, onto the shipped
    behaviour, rather than silently running the experimental arm.
    """
    return value != "0"


#: The shipped behaviour, and the control arm of the experiment. Set
#: `OPENCHEM_DISPOSE_FLUSH=0` to move the delete's delivery to end-of-test.
FLUSH_AT_DISPOSE = flush_at_dispose(os.environ.get("OPENCHEM_DISPOSE_FLUSH"))


def dispose(widget) -> None:
    """Destroy a widget a test built and is walking away from.

    THE ONE IMPLEMENTATION. These three lines were copy-pasted across 46
    test files under at least six names -- `_dispose`, `dispose`,
    `_dispose_panel`, `widgets`, `card`, and inline -- and
    `benchmarks/disposal/inventory.md` is what they were, measured before
    any of them was touched: 64 sequences, 8 distinct. This repository has
    paid four times for two implementations of one idea drifting.

    **IT IS NOT `dispose_app_widgets`, AND THE DIFFERENCE IS
    LOAD-BEARING.** That fixture was reverted for crashing the suite 8 of
    8 full runs on master (see `flush_deferred_deletes` above), and it was
    AUTOUSE and DISCOVERED its subjects -- 112 top-level widgets a test
    never mentioned. This serves only what a test explicitly hands over:
    same call sites, same set, same timing as the 46 copies it replaces.

    **NEVER MAKE IT AUTOUSE.** The moment it discovers its own subjects it
    becomes the fixture that was reverted, and the reason it is safe today
    stops being true.

    A `close()` or `hide()` a site needs first stays AT that site -- 7 of
    the 64 sequences have one, and folding a flag in here would make one
    helper mean three things.

    **THERE IS NO SHARED `widgets` FIXTURE, and that was measured rather
    than assumed.** One was written and deleted: ten test files define
    their own `widgets`, every one of which SHADOWS a conftest fixture of
    that name, so the shared version would have resolved for nothing --
    the "shipped is not reachable" failure `test_calculator_reachability`
    exists for. And six of the ten must `close()` each widget first,
    which a shared fixture cannot express without becoming the flag this
    docstring just refused. They delegate here instead, which is what
    makes this the one implementation.

    IT IS A PLAIN FUNCTION, reached with `import conftest`. That form
    finds the module pytest already loaded; `from tests.conftest import x`
    imports the same file AGAIN under a second name and re-runs it at
    module level, which is the hazard `_start_census` guards against.

    ## THE FLUSH IS THE EXPERIMENTAL VARIABLE, AND IT IS ENV-GATED

    Both Linux frames of ours ever named are this line
    (`test_panel_rail.py:19`, `test_screening_service.py:269`), and the
    reverted `dispose_app_widgets` crashed 8 of 8 doing the same thing
    automatically. That is a LEAD, not a cause, and
    `OPENCHEM_DISPOSE_FLUSH=0` is what lets it be tested.

    **Both arms still destroy the object. Only the TIMING changes** --
    with the flush off, `flush_deferred_deletes` above delivers the same
    `DeferredDelete` per object at end of test instead of here. Nothing
    is left queued.

    **The variable is an env var and NOT a second branch**, deliberately.
    This branch's own finding is that a byte-identical tree crashes in
    different files on different runs, so an A/B whose arms are different
    commits invites exactly the explanation it cannot rule out. One
    commit, one env var, two dispatches.

    Same shape as `OPENCHEM_CENSUS`: off by default, costing nothing, and
    the default is guarded so it cannot drift.
    """
    widget.setParent(None)
    widget.deleteLater()
    if FLUSH_AT_DISPOSE:
        QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


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

    # The census's per-test line, written from INSIDE this hook rather
    # than from a second `pytest_runtest_logfinish`. Defining that would
    # SHADOW this one -- same module, same name -- and silently disable
    # the collect above, which is the thing holding late destructions at
    # zero. A diagnostic that switches off the fix it is measuring would
    # be worse than no diagnostic.
    if _CENSUS_PATH is not None:
        _census_write(
            f"  end {nodeid} built={_census_counts['built']} "
            f"destroyed={_census_counts['destroyed']} "
            f"late={_census_counts['late']} alive={len(_census_born)}"
        )


# ---------------------------------------------------------------------------
# The Qt object census, written PER TEST so a crash leaves a trail
# ---------------------------------------------------------------------------
#
# Set `OPENCHEM_CENSUS=<path>` to switch it on; off costs nothing but the
# `if` below.
#
# **NO WORKFLOW SETS IT, AND THIS COMMENT USED TO CLAIM THE LINUX JOB
# DID.** Measured: `grep -rn OPENCHEM_CENSUS .github/` matches nothing, so
# an instrument written to diagnose a crash that only reproduces on Linux
# had never run in CI at all. The claim described an intention, and a
# comment that states an intention as a fact is worse than silence --
# somebody reading the Linux logs for a census trail would find none and
# have no way to tell that from a run where nothing was destroyed late.
#
# It is wired into the Linux job now, which is what makes the sentence
# true rather than aspirational. That job is `continue-on-error` and
# publishes its `suite.log` as an artifact; the trail goes up beside it.
#
# WHY IT IS WRITTEN PER TEST AND NOT AT SESSION END. The first version of
# this reported from `pytest_sessionfinish`, which cannot work: the
# process dies before that hook, so **the run that reports is by
# construction a run that did not crash**. It measured 0 late
# destructions over a clean run and could not have measured anything
# else. Flushing a line per test is the whole fix.
#
# WHAT IT RECORDS, and the two things it deliberately does not:
#
#   - `destroyed` is the ONLY signal meaning a C++ destructor ran. NEVER a
#     weakref callback -- that counts Python WRAPPERS and over-reports by
#     an order of magnitude, measured 1406 against a real 138. A wrapper
#     collected after Qt already destroyed the object is harmless.
#   - `alive` is not a bug count. A widget still alive has never been
#     destroyed, so it cannot be the thing that faults; the earlier census
#     reported 65 live panels and they were irrelevant. It is here as
#     context for the two numbers that matter.
#
# THE PID IS THE JOIN KEY TO A CORE FILE. `kernel.core_pattern` is set to
# `core.%p` alongside this, so `BEGIN ... pid=1234` is what pairs a trail
# with `core.1234`. Without it, matching them is guesswork.

_CENSUS_PATH = os.environ.get("OPENCHEM_CENSUS")

#: Which FILE installed the wrapper, and the identity a second execution
#: compares itself against. `realpath` rather than a bare `__file__`
#: because the two module instances are loaded by different machinery --
#: pytest's own conftest loader and an ordinary `import tests.conftest` --
#: and nothing guarantees they spell the same path identically.
_CENSUS_SOURCE = os.path.realpath(__file__)
_census_counts = {"built": 0, "destroyed": 0, "late": 0}
_census_born: dict[int, str] = {}
_census_where = ["<session>"]
_census_handle = []


def _census_write(text: str) -> None:
    """One line, flushed.

    `flush()` and NOT `fsync()`. `abort()` kills the process, not the OS
    page cache, so a flushed line survives the very crash this exists to
    catch; fsync would buy protection against a kernel panic -- which is
    not what is happening -- at the price of 6100 syncs a run.
    """
    if not _census_handle:
        return
    handle = _census_handle[0]
    handle.write(text + "\n")
    handle.flush()


def _start_census() -> None:
    """Wrap `QWidget.__init__` ONCE, and refuse to be the second wrapper.

    "Never stack two censuses" is a measured hazard here rather than a
    style rule -- double-wrapping every widget constructor destabilised a
    run by itself, producing a `Fatal Python error: Aborted` that appears
    under no other configuration. So this ASSERTS rather than documenting:
    a second copy of this instrument fails loudly instead of quietly
    making the suite less stable than the thing it is measuring.

    Same shape as `_track_web_engine_views`' `_openchem_tracks_views` flag
    and `_retain_main_windows`' `_openchem_retained`, which is the idiom
    this file already uses twice.

    **A RE-IMPORT OF THIS FILE IS NOT A SECOND CENSUS, AND A BARE FLAG
    CANNOT TELL THE DIFFERENCE.** `tests/` has no `__init__.py`, so pytest
    loads this conftest under its own plugin name -- and four tests do
    `from tests.conftest import painted/ink`, which imports the SAME FILE
    again under a second module name and re-runs everything at module
    level, including this function.

    A flag that only records "somebody wrapped it" reddens the suite on
    exactly those four tests, and only when the census is switched on:

        census OFF   4 passed      `_CENSUS_PATH is None`, returns early
        census ON    4 failed      RuntimeError from this guard

    which is the whole hazard restated -- an instrument that changes what
    it measures. It shipped in `68aa89e` and survived because nobody had
    run the full suite with the census enabled; the run that produced the
    figures below is what found it.

    So the flag records the SOURCE FILE rather than a bool. Re-executing
    this same file returns quietly and leaves the first wrapper in place;
    a census installed from a DIFFERENT file still raises, which is the
    stacked-instrument case the hazard is actually about.

    **RETURNING BEFORE THE `open()` IS LOAD-BEARING**, not incidental
    tidiness: the handle is opened in `"w"` mode, so a second execution
    that got that far would TRUNCATE the trail -- destroying the evidence
    this instrument exists to preserve, in the crash case where it is the
    only evidence there is.
    """
    if _CENSUS_PATH is None:
        return
    from PySide6.QtWidgets import QWidget

    installed_by = getattr(QWidget.__init__, "_openchem_census", None)
    if installed_by is not None:
        if installed_by == _CENSUS_SOURCE:
            # This same conftest, executed a second time by an import.
            # The first wrapper is already in place and owns the handle;
            # this module instance stays inert. `_census_write` no-ops
            # here because `_census_handle` is empty in it.
            return
        raise RuntimeError(
            "QWidget.__init__ is already census-wrapped, by "
            f"{installed_by!r}. Two censuses stacked is a measured cause "
            "of instability, not a tidiness problem -- run one at a time."
        )

    original_init = QWidget.__init__

    def census_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        key = id(self)
        born = _census_where[0]
        _census_born[key] = born
        _census_counts["built"] += 1

        # THE CLASS NAME IS BOUND AS A STRING, and `self` MUST NOT appear
        # in this closure. PySide holds a connected plain callable
        # STRONGLY, so a reference to `self` here makes every widget in
        # the suite immortal -- the exact self-capturing-`connect` leak
        # this repository documents, written into the one instrument
        # whose job is measuring widget lifetimes.
        #
        # It is not a hypothetical: the first version interpolated
        # `type(self).__name__` and it (a) failed
        # `test_a_pending_metrics_dump_is_cancelled_when_the_panel_is_destroyed`,
        # which asserts a panel really is destroyed, and (b) reported
        # `late=0` over a full run -- a number that cannot be anything
        # else when nothing can be destroyed at all.
        cls_name = type(self).__name__

        def gone(_obj=None, _key=key, _born=born, _cls=cls_name) -> None:
            if _census_born.pop(_key, None) is None:
                return
            _census_counts["destroyed"] += 1
            if _born != _census_where[0]:
                _census_counts["late"] += 1
                _census_write(f"LATE {_cls} built={_born} died={_census_where[0]}")

        try:
            self.destroyed.connect(gone)
        except Exception:  # noqa: BLE001 - a half-built widget is not our problem
            _census_born.pop(key, None)

    # The SOURCE FILE, not a bool -- see this function's docstring for why
    # a bare flag cannot tell a re-import from a stacked instrument.
    census_init._openchem_census = _CENSUS_SOURCE
    QWidget.__init__ = census_init

    handle = open(_CENSUS_PATH, "w", encoding="utf-8", buffering=1)
    _census_handle.append(handle)
    _census_write(f"# census pid={os.getpid()}")


_start_census()


def pytest_runtest_logstart(nodeid, location):
    """The line that names the victim of a crash.

    Written BEFORE the test runs, so when the process aborts partway
    through one the trail's last line is that test. `logfinish` never
    arrives for it, which is precisely the case this exists for.
    """
    if _CENSUS_PATH is None:
        return
    _census_where[0] = nodeid
    _census_write(f"BEGIN {nodeid} pid={os.getpid()}")


def pytest_sessionfinish(session, exitstatus):
    """Mark the boundary, so a shutdown destruction is not read as a landmine.

    **THIS IS A SENTINEL, NOT A REPORT**, and the distinction is the one
    this module's own docstring insists on. Reporting TOTALS from here
    cannot work -- the process dies before this hook, so the run that
    reports is by construction a run that did not crash. Writing one line
    that says "the session ended here" has the opposite property: if the
    process aborts, the line is simply ABSENT, and its absence is itself
    the correct answer.

    WHY IT IS NEEDED. `gone()` calls a destruction LATE when the test that
    built the widget is not the test running now. At interpreter shutdown
    every surviving widget is torn down while `_census_where[0]` still
    holds the LAST test's nodeid, so every one of them trips that check --
    and they are process teardown, not the cross-test landmine the
    instrument exists to find. Measured over a full run:

        LATE lines written during the run          0
        LATE lines written after the last test   16022   <- all shutdown

    Every one of the 16022 fell after the final `end` line, which is the
    only reason the two could be told apart at all. Naming the boundary
    makes each line say which it is (`died=<session teardown>`) instead of
    leaving a reader to compare line numbers -- and a reader who does not
    know to do that reads 16022 landmines that are not there.
    """
    if _CENSUS_PATH is None:
        return
    _census_write(f"# session finished exitstatus={exitstatus}")
    _census_where[0] = "<session teardown>"
