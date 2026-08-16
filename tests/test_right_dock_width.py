"""The window must fit on the screen, and the rail must stay reachable.

Reported from the running app: "the rightmost tab can be a bit strange
when clicking different menus, it will change size, and even became
pretty much inaccessible until I got out of fullscreen. But then while
windowed, clicking another menu item, and then maximizing will fix it."

**Measured cause, and it was not the panel in the screenshot.** Every
right-hand dock's minimum width is modest (102-280 px); the scroll
wrappers around them ask for 58. The window's minimum came almost
entirely from the CENTRE: `MoleculeViewer3DWidget` packed fourteen
controls into one `QHBoxLayout`, whose minimum width is the SUM of them
-- 1252 px of controls plus thirteen gaps = **1330**. That propagated to
the central `QStackedWidget` and made the whole window's minimum
**1877-2055 px** depending on the visible panel, against a **1920 px**
screen. So the window could not be made to fit, the rail sat at
x=1785..2055 with 135 px past the edge, and switching panels changed the
window's width by up to 178 px.

Two tests, deliberately:

- the SYMPTOM test walks the path that was reported, because a minimum
  width is only a proxy for "can you still reach the rail";
- the STRUCTURAL test asserts the arithmetic, as the explanation for
  why the symptom cannot come back.

`isVisible()` is False for every child of a window nobody showed, so the
window is shown here -- this project has been bitten by that twice.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QToolBar

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.molecule import MoleculeModel

#: A 1366x768 laptop, the smallest display this is plausibly run on. The
#: window's minimum must fit inside it with room to spare.
#:
#: **NOT a number tuned until the test passed.** The absolute minimum
#: differs by platform -- measured, 690-868 px on the real Windows
#: desktop and 1002-1158 under Qt's `offscreen`, a systematic ~270 px
#: gap -- so a threshold fitted to either one is really a statement about
#: that environment. A real screen size is a claim about the product, it
#: clears both by a wide margin, and it still catches the regression it
#: exists for by 500-700 px.
SMALLEST_LAPTOP = 1366

#: The width the symptom tests drive at, and it is the SAME number
#: deliberately.
#:
#: An earlier draft used 1000, which the clean tree could not satisfy
#: under `offscreen` -- its minimum is 1002-1158 there, so `resize(1000)`
#: clamped and the control failed. Rather than pick a number that merely
#: passes, drive at the width the product claims to support: it is above
#: the platform's floor in both environments, and still 500-700 px below
#: what the bug produced.
NARROWEST_SUPPORTED = SMALLEST_LAPTOP

#: What the central editor needs to be worth looking at.
CENTRAL_FLOOR = 200


@pytest.fixture(scope="module")
def window(qapp_module):
    """ONE window for the file.

    Building a `MainWindow` costs three `QWebEngineView`s, so six of them
    is minutes rather than seconds. It is deliberately NOT closed --
    `tests/conftest.py` retains every MainWindow for the session because
    collecting one corrupts the heap, and closing per test made this file
    hang in teardown.
    """
    import tempfile

    services = build_service_container()
    settings = Settings(services.event_bus)
    with tempfile.TemporaryDirectory() as scratch:
        settings.set("plugins/project_directory", f"{scratch}/none")
        settings.set("plugins/user_directory", f"{scratch}/none")
        built = MainWindow(services, settings, SessionManager())
    molecule = MoleculeModel(display_name="Aspirin")
    services.chemistry_engine.set_structure_from_smiles(
        molecule, "CC(=O)Oc1ccccc1C(=O)O"
    )
    built.add_molecule(molecule)
    built.resize(1280, 800)
    built.show()
    qapp_module.processEvents()
    return built


@pytest.fixture(scope="module")
def qapp_module():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def app(qapp_module):
    """Function-scoped alias, so tests read normally."""
    return qapp_module


def _rail(window) -> QToolBar:
    bar = next(
        (b for b in window.findChildren(QToolBar) if b.objectName() == "Panel_Rail"),
        None,
    )
    assert bar is not None, "the panel rail toolbar is gone"
    return bar


def _rail_is_reachable(window) -> tuple[bool, str]:
    """Geometry, NOT `isVisible()`.

    A rail sitting entirely past the right edge reports `isVisible()`
    True and is completely unusable, which is exactly the false pass this
    has to avoid. "Reachable" means: on screen inside the window, with
    real width.
    """
    bar = _rail(window)
    if bar.isHidden():
        return False, "the rail is hidden"
    if bar.width() <= 0:
        return False, f"the rail has width {bar.width()}"
    left = bar.mapTo(window, bar.rect().topLeft()).x()
    right = left + bar.width()
    if left < 0 or right > window.width():
        return False, (
            f"the rail spans x={left}..{right} in a window {window.width()} wide"
        )
    return True, ""


# --- the symptom, on the path it was reported from ---------------------------


def test_every_panel_leaves_the_rail_reachable_at_the_narrowest_width(window, app):
    """Invariant 1: navigation survives. Losing the rail is what made the
    application feel broken rather than merely cramped.

    **THE RESIZE IS ASSERTED, and the first version of this test was
    worthless without it.** Qt clamps `resize()` to `minimumSizeHint`, so
    with the bug present the window silently stayed ~2055 px wide and the
    rail sat comfortably inside that over-wide window -- every
    reachability check passed while the real application was pushing the
    rail off the screen. Measured: with the bug restored, this file's
    three symptom tests all passed and only the structural ones failed.
    Checking that the window really became the size it was asked for is
    what makes this a test of the symptom.
    """
    window.resize(NARROWEST_SUPPORTED, 800)
    app.processEvents()
    assert window.width() == NARROWEST_SUPPORTED, (
        f"asked for {NARROWEST_SUPPORTED} px and got {window.width()}; the window "
        f"cannot be made to fit, which is the reported bug"
    )

    for dock in window._right_docks:
        window._on_panel_chosen(dock.objectName())
        app.processEvents()
        assert window.width() == NARROWEST_SUPPORTED, (
            f"{dock.objectName()} widened the window to {window.width()}"
        )
        ok, why = _rail_is_reachable(window)
        assert ok, f"{dock.objectName()}: {why}"


def test_switching_panels_does_not_change_what_the_window_ASKS_FOR(window, app):
    """Invariant 2, and it is asserted on THREE quantities on purpose.

    A widget can change what the window asks for without the window
    changing size yet -- a deferred request that only bites at the next
    maximize is exactly the shape of "I had to leave fullscreen to
    recover it". Actual size alone would not see it.
    """
    window._on_panel_chosen("Properties")
    app.processEvents()
    before = (window.size(), window.minimumSize(), window.minimumSizeHint())

    for dock in window._right_docks:
        window._on_panel_chosen(dock.objectName())
        app.processEvents()

    window._on_panel_chosen("Properties")
    app.processEvents()

    assert (window.size(), window.minimumSize(), window.minimumSizeHint()) == before


def test_the_reported_resize_sequence_never_loses_the_rail(window, app):
    """windowed -> maximized -> windowed -> maximized, switching panels
    throughout: the exact path Alex took.

    Endpoint-only testing would miss it -- the state that had to be
    escaped from was reached by a TRANSITION, not by any one size.
    """
    panels = [dock.objectName() for dock in window._right_docks]

    for step, state in enumerate(("normal", "maximized", "normal", "maximized")):
        if state == "maximized":
            window.showMaximized()
        else:
            window.showNormal()
            window.resize(NARROWEST_SUPPORTED, 800)
        app.processEvents()

        for panel in panels:
            window._on_panel_chosen(panel)
            app.processEvents()
            if state == "normal":
                # Same reason as the test above: without this the window
                # is free to stay over-wide and every rail check passes.
                assert window.width() == NARROWEST_SUPPORTED, (
                    f"after {state} (step {step}), {panel} widened the window to "
                    f"{window.width()}"
                )
            ok, why = _rail_is_reachable(window)
            assert ok, f"after {state} (step {step}), panel {panel}: {why}"


# --- the structural explanation ----------------------------------------------


def test_the_window_can_be_made_narrower_than_a_small_laptop(window, app):
    """The arithmetic behind the symptom.

    The window's minimum width was 1877-2055 against a 1920 px screen, so
    it could not fit AT ALL -- `resize()` was silently clamped, which is
    why the reported workaround involved window states rather than
    dragging an edge.
    """
    for dock in window._right_docks:
        window._on_panel_chosen(dock.objectName())
        app.processEvents()
        assert window.minimumSizeHint().width() <= SMALLEST_LAPTOP, (
            f"{dock.objectName()} forces a window minimum of "
            f"{window.minimumSizeHint().width()} px"
        )


def test_no_right_hand_panel_eats_the_central_editor(window, app):
    """Iterates over `_right_docks` ITSELF, never a list kept beside it --
    the direction that caught the two missing help topics in
    `test_help.py`. A panel added later is covered because it exists."""
    rail_width = _rail(window).sizeHint().width()

    for dock in window._right_docks:
        budget = dock.minimumSizeHint().width() + rail_width + CENTRAL_FLOOR
        assert budget <= NARROWEST_SUPPORTED, (
            f"{dock.objectName()} needs {dock.minimumSizeHint().width()} px, which "
            f"with the rail ({rail_width}) leaves under {CENTRAL_FLOOR} px for the "
            f"editor at {NARROWEST_SUPPORTED} px"
        )


def test_the_centre_does_not_force_the_window_wide(window, app):
    """The actual culprit, guarded where it lives.

    `MoleculeViewer3DWidget`'s toolbar row was a `QHBoxLayout`, so its
    minimum was the SUM of fourteen controls: 1330 px. It wraps now, and
    `FlowLayout.minimumSize` returns the widest SINGLE control instead.
    """
    central = window.centralWidget()

    assert central.minimumSizeHint().width() <= 640, (
        f"the centre asks for {central.minimumSizeHint().width()} px; a row that "
        f"does not wrap has almost certainly come back"
    )


# --- the starting width, which nothing used to set ---------------------------


def test_the_right_dock_opens_wider_than_its_own_minimum_on_a_real_display():
    """Nothing used to set a starting width, so every panel opened at its
    own minimum -- 280 px, for good, until somebody dragged it. That is
    why the Properties panel's caption clipping was reachable at all.

    **The table, not the resulting dock width.** The suite's `offscreen`
    platform reports an 800 px screen, so the quarter-of-the-screen cap
    always bites there and the dock lands on 280 either way: a test
    asserting the dock's width would pass identically with this feature
    removed. The calculation is where the behaviour lives, and it is a
    pure function for exactly that reason.
    """
    from openchem.app.main_window import initial_right_dock_width

    assert initial_right_dock_width(1920, 280) == 420, "a wide display should use 420"
    assert initial_right_dock_width(1366, 280) == 341, "a laptop should be capped"
    assert initial_right_dock_width(800, 280) == 280, "the test platform is unchanged"


def test_the_starting_width_never_goes_under_the_panels_own_minimum():
    """The floor is the DOCK'S minimum, not a second constant.

    Below it the panel cannot be drawn without clipping -- which is the
    defect this whole area exists to prevent -- so a small display must
    keep today's behaviour exactly rather than being given something
    narrower than the panel can render.
    """
    from openchem.app.main_window import initial_right_dock_width

    for available in (0, 320, 640, 800, 1024, 1366, 1920, 3840):
        assert initial_right_dock_width(available, 280) >= 280, available


def test_the_starting_width_never_takes_more_than_a_quarter_of_the_screen():
    """The cap is what makes this safe on a laptop: a flat 420 is 31% of a
    1366 px display before the rail and the project tree are counted.

    Asserted across the range rather than at one point, and allowing the
    floor to win -- below about 1120 px the panel's own minimum is more
    than a quarter, and the panel's minimum is the harder constraint.
    """
    from openchem.app.main_window import initial_right_dock_width

    for available in (1366, 1600, 1920, 2560, 3840):
        width = initial_right_dock_width(available, 280)
        assert width <= max(280, available // 4), available
        assert width <= 420, f"{available}: nothing should exceed the desired width"


def test_a_saved_dock_layout_is_not_overridden_by_the_starting_width(qapp_module, window):
    """Somebody who dragged the dock where they wanted it must get it back.

    The starting width applies to a FRESH layout only. Forcing it on every
    launch would reset a width the user chose, on every launch, which is
    the same class of rudeness as discarding their window size -- and
    `_restore_window_state` already refuses to do that for the geometry.

    **This is the arm the pure-function tests cannot reach.** Removing the
    `if not self._restore_window_state():` gate leaves the calculation
    perfectly correct and all three of them passing; only building a
    window from a saved layout shows it. Measured: with the gate removed
    this test fails and nothing else in the file notices.

    It builds a second `MainWindow`, which this file otherwise avoids
    because each costs three `QWebEngineView`s. That is the price of
    testing something that only happens during construction.
    """
    import tempfile

    from PySide6.QtCore import Qt

    from openchem.app.main_window import (
        _LAYOUT_VERSION,
        _LAYOUT_VERSION_KEY,
        initial_right_dock_width,
    )

    #: Distinct from anything the starting width can produce under the
    #: test platform's 800 px screen, where the calculation yields 280.
    chosen = 500

    # WIDEN THE WINDOW FIRST. This file's other tests drive the shared
    # window down to `NARROWEST_SUPPORTED`, and Qt clamps `resizeDocks` to
    # what the window can spare -- asking for 500 in a 1024 px window got
    # 302, and the setup assertion below caught it rather than the test
    # silently comparing 302 against 302.
    was = window.size()
    window.resize(1600, 900)
    qapp_module.processEvents()

    dock = next(candidate for candidate in window._right_docks if not candidate.isHidden())
    before = dock.width()
    window.resizeDocks([dock], [chosen], Qt.Orientation.Horizontal)
    qapp_module.processEvents()
    assert dock.width() == chosen, (
        f"could not set up a {chosen} px dock to save (got {dock.width()}), so this "
        "test cannot tell a restored width from a computed one"
    )
    blob = window.saveState()
    window.resizeDocks([dock], [before], Qt.Orientation.Horizontal)
    window.resize(was)
    qapp_module.processEvents()

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set_window_state(blob)
    settings.set(_LAYOUT_VERSION_KEY, _LAYOUT_VERSION)
    with tempfile.TemporaryDirectory() as scratch:
        settings.set("plugins/project_directory", f"{scratch}/none")
        settings.set("plugins/user_directory", f"{scratch}/none")
        restored = MainWindow(services, settings, SessionManager())
    restored.resize(1280, 800)
    restored.show()
    qapp_module.processEvents()

    restored_dock = next(
        candidate for candidate in restored._right_docks if not candidate.isHidden()
    )

    # **NOT `== chosen`, AND THAT IS QT RATHER THAN A WEAKENED CLAIM.**
    # `restoreState` scales the saved dock sizes to the window it is
    # restoring into, so a 500 px dock saved from a 1600 px window comes
    # back at 424 in a smaller one. Exact equality was never available;
    # measured before this comment existed, and asserting it failed
    # against perfectly correct behaviour.
    #
    # What discriminates is that the restored width is nowhere near the
    # COMPUTED one: with the gate removed the dock is forced to exactly
    # the starting width (280 under this platform's 800 px screen), and
    # with it the dock keeps its own proportion.
    screen = restored.screen()
    available = screen.availableGeometry().width() if screen is not None else restored.width()
    computed = initial_right_dock_width(available, restored_dock.minimumSizeHint().width())
    assert restored_dock.width() != computed, (
        f"the restored dock is exactly the computed starting width ({computed} px), so "
        "the saved layout was overridden rather than honoured"
    )
    assert restored_dock.width() > computed + 40, (
        f"a saved dock width of {chosen} px came back as {restored_dock.width()} against "
        f"a computed starting width of {computed} -- the saved layout did not survive"
    )


def test_setting_the_starting_width_narrows_a_dock_that_is_too_wide(qapp_module, window):
    """`_set_initial_right_dock_width` does what it says, tested without
    depending on how wide the test platform's screen is.

    The pure-function tests cover the arithmetic and the saved-layout test
    covers the gate; this covers the step between them -- that the method
    actually resizes the visible right-hand dock to the computed width.

    **ONE MUTATION IS NOT CAUGHT ANYWHERE, AND IT IS RECORDED RATHER THAN
    PAPERED OVER**: deleting the call from `MainWindow.__init__`
    altogether. Under `offscreen`'s 800 px screen the computed width is
    the dock's own minimum, which is exactly what Qt hands it anyway, so
    applying the feature and not applying it are indistinguishable by any
    outcome a test here can read. It was verified by driving the real app
    on a 1920 px display instead -- 280 before, 420 after, captions no
    longer eliding. The `if not self._restore_window_state():` half IS
    covered, by the saved-layout test above.
    """
    from PySide6.QtCore import Qt

    from openchem.app.main_window import initial_right_dock_width

    was = window.size()
    window.resize(1600, 900)
    qapp_module.processEvents()
    dock = next(candidate for candidate in window._right_docks if not candidate.isHidden())
    before = dock.width()

    window.resizeDocks([dock], [520], Qt.Orientation.Horizontal)
    qapp_module.processEvents()
    assert dock.width() == 520, (
        f"could not widen the dock to 520 (got {dock.width()}), so narrowing it proves nothing"
    )

    window._set_initial_right_dock_width()
    qapp_module.processEvents()

    screen = window.screen()
    available = screen.availableGeometry().width() if screen is not None else window.width()
    expected = initial_right_dock_width(available, dock.minimumSizeHint().width())
    actual = dock.width()

    window.resizeDocks([dock], [before], Qt.Orientation.Horizontal)
    window.resize(was)
    qapp_module.processEvents()

    assert actual == expected, (
        f"the dock was left at {actual} px, not the computed starting width {expected}"
    )
