from __future__ import annotations

import os
import sys
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
from PySide6 import QtWidgets
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QSettings
from PySide6.QtWidgets import QApplication, QWidget


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

    THIS FIXTURE ALONE DOES NOT FIX THAT CRASH -- measured, it still went
    off 2 times out of 2, on the widgets `test_jobs_panel.py` abandons.
    `dispose_app_widgets` below is the other half, and only both together
    take the reproduction to 8 passes out of 8. What this one prevents is
    the queue existing at all.

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


# Weak refs to every widget of one of THIS APP's classes built since the
# current test started. Weak so that merely watching one never keeps it
# alive.
_app_widgets_created_during_test: list[weakref.ref] = []


def _track_app_widgets() -> None:
    """Start recording construction of this application's own widgets.

    Wrapping constructors, rather than sweeping `QApplication.allWidgets()`
    in teardown, for the reason `_track_web_engine_views` documents at
    length: Chromium churns through its own private QWidgets while a page
    lives, and enumerating them mid-flight faulted outright.

    The wrapper goes on every `QWidget` subclass `QtWidgets` exports, not
    on `QWidget` alone, because a Python subclass reaches C++ through the
    `__init__` of whichever Qt class it derives from -- `MainWindow`'s
    `super().__init__()` lands in `QMainWindow.__init__` and never in
    `QWidget.__init__`. Only instances whose CLASS is defined outside
    PySide6 are recorded, which is both the set worth destroying and cheap
    enough to test on every widget construction: measured over 6 runs
    before and 11 after, the suite went from a mean of 102s (92-112) to
    106s (99-115), well inside the run-to-run spread.
    """
    for name in dir(QtWidgets):
        cls = getattr(QtWidgets, name)
        if not (isinstance(cls, type) and issubclass(cls, QWidget)):
            continue
        if getattr(cls.__init__, "_openchem_tracks_widgets", False):
            continue

        def tracking_init(self, *args, _original=cls.__init__, **kwargs):
            _original(self, *args, **kwargs)
            if not type(self).__module__.startswith("PySide6"):
                _app_widgets_created_during_test.append(weakref.ref(self))

        tracking_init._openchem_tracks_widgets = True
        cls.__init__ = tracking_init


_track_app_widgets()


@pytest.fixture(autouse=True)
def dispose_app_widgets():
    """Destroy every top-level widget a test built, before the next runs.

    A test that constructs an unparented panel, window or dialog and just
    walks away leaves it alive with no owner, and Python then destroys it
    at whatever arbitrary later moment the collector happens to run -- in
    the middle of an unrelated test, from inside Qt's own event dispatch.
    Measured at the point this fixture was added: **112 such widgets
    survived a full run**, across 20 files, led by `ExternalToolsDialog`
    (22), `MainWindow` (22) and `PropertyPanel` (10).

    That is the second half of the ketcher access violation, and the half
    that made it look unfixable. With only the deferred-delete backlog
    flushed, `test_jobs_panel.py` (5 abandoned `JobsPanel`s) still crashed
    `test_ketcher_editor_backend.py` on 2 of 2 runs; with both halves
    fixed the same forced-drain reproduction is clean. Bisection could
    never have found it, because which file is the victim depends on
    allocation timing rather than on either file's code.

    Only widgets with no parent are touched: a parented one is owned by
    something else, which destroys it in its own time. Destruction is a
    per-widget `deleteLater()` plus a flush of THAT WIDGET'S deferred
    delete -- never `sendPostedEvents(None, DeferredDelete)`, whose
    process-wide drain is the crash rather than the cure. Destroying a
    parent takes its children with it, so validity is re-checked on every
    iteration rather than once up front.

    Scope is "built during this test", so a widget meant to outlive one
    would be destroyed under it. Nothing does that today -- every widget
    in the suite is built inside a test or a function-scoped fixture, and
    no module- or session-scoped fixture holds one -- and anything that
    ever needs to should be excluded here explicitly rather than this
    quietly growing an exception.
    """
    _app_widgets_created_during_test.clear()

    yield

    created = [ref() for ref in _app_widgets_created_during_test]
    _app_widgets_created_during_test.clear()
    for widget in created:
        if widget is None or not shiboken6.isValid(widget):
            continue  # already destroyed, possibly as a child of an earlier one
        if widget.parent() is not None:
            continue
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


@pytest.fixture(scope="session")
def qapp():
    """A QApplication is required for QObject-derived types used throughout
    the app (EventBus signals, QThreadPool, QUndoStack) even in headless
    tests. Session-scoped and offscreen so the suite runs in CI with no
    display.
    """
    app = QApplication.instance() or QApplication([])
    yield app


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
