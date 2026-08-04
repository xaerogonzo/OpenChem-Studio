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
from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication


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
