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

import ast
from pathlib import Path

from openchem.app.main_window import CENTRAL_FLOOR, MainWindow, _LAYOUT_VERSION
from openchem.ui.widgets.panel_rail import PanelRail
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.molecule import MoleculeModel

_SRC = Path(__file__).resolve().parent.parent / "src"

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

#: `CENTRAL_FLOOR` IS IMPORTED FROM PRODUCTION, not declared here.
#:
#: It was a test-only constant for as long as it existed, and nothing
#: enforced it: the real central minimum measured 149 px in the running
#: app, a quarter below the 200 these tests reasoned about, and every
#: guard passed. `MainWindow` sets it on the central `QTabWidget` now, so
#: the number below and the number the product obeys cannot drift.


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


# --- the floor, which was a test-only number until it was enforced ----------


def test_the_centre_really_cannot_be_squeezed_below_the_floor(window, app):
    """The complement of `test_the_centre_does_not_force_the_window_wide`.

    That one is a CEILING and it passed throughout: the centre asked for
    149 px in the running app, comfortably under 640, while `CENTRAL_FLOOR`
    sat in this file meaning nothing to the product.

    ASSERTED ON THE BEHAVIOUR, because `minimumSizeHint()` does not answer
    this question -- it is Qt's RECOMMENDED minimum and is unmoved by
    `setMinimumWidth`, so a guard reading it fails against a correctly
    floored widget (measured: hint 282, enforced minimum 400). What the
    floor actually buys is that squeezing the window cannot take the
    editor below it, which is what this drives.

    THIS IS THE ARM THAT MUST FAIL IF THE PRODUCTION LINE GOES, and 400 is
    what makes that possible: the emergent minimum is 282 under
    `offscreen` and 149 on a real desktop, so both are caught. At the old
    200 the emergent `offscreen` value already exceeded it and the guard
    could never say no -- the blindness `initial_right_dock_width` records
    for the dock width one section down.
    """
    was = window.size()
    try:
        window.resize(600, was.height())
        app.processEvents()
        central = window.centralWidget()

        assert window.width() < was.width(), (
            f"the window did not shrink at all (still {window.width()} px), so "
            "nothing here squeezes the centre and this guard is vacuous"
        )
        assert central.width() >= CENTRAL_FLOOR, (
            f"the centre is {central.width()} px in a {window.width()} px window, "
            f"below its declared floor of {CENTRAL_FLOOR} -- MainWindow has "
            "stopped setting a minimum on its central widget"
        )
    finally:
        window.resize(was)
        app.processEvents()
def test_the_floor_and_the_ceiling_are_bounds_on_one_quantity(window, app):
    """A floor on the editor page and a ceiling on the tab widget would
    both pass while describing different widgets.

    Asserted structurally: the object carrying the minimum IS the object
    `centralWidget()` returns. A `QTabWidget` takes the maximum over its
    pages, so a page-level floor propagates by accident today and stops
    the day the pages are rearranged.
    """
    central = window.centralWidget()

    assert central.minimumWidth() == CENTRAL_FLOOR, (
        f"the central widget's own minimum is {central.minimumWidth()}, not "
        f"{CENTRAL_FLOOR} -- the floor has been moved onto a child, where it "
        "survives only as long as that child stays the widest page"
    )
    assert central.minimumSizeHint().width() <= 640, (
        "the ceiling guard's bound no longer holds for the object the floor "
        "is set on, so the two are describing different widgets"
    )


# --- the rail fold, which was reachable and not remembered ------------------


def test_the_rail_fold_survives_a_restart_with_its_group_and_panel(qapp_module):
    """Folding the rail hands 230 px back, and used to be forgotten.

    THREE QUANTITIES, not one boolean. A flag that round-trips proves the
    setting serialises; it says nothing about whether the user's actual
    navigation state came back. The fold is persisted by this change, and
    the group and the visible panel come back through `restoreState` --
    different mechanisms, which is exactly why asserting only the one this
    commit added would leave the other two unguarded.

    A second window is built from the saved settings rather than the fold
    being toggled back, because construction ORDER is the thing at risk:
    the restore has to run after `_restore_window_state`, and a test that
    only toggles never exercises that path at all.
    """
    import tempfile

    services = build_service_container()
    settings = Settings(services.event_bus)
    with tempfile.TemporaryDirectory() as scratch:
        settings.set("plugins/project_directory", f"{scratch}/none")
        settings.set("plugins/user_directory", f"{scratch}/none")
        first = MainWindow(services, settings, SessionManager())
    first.resize(1280, 800)
    first.show()
    qapp_module.processEvents()

    rail = first._panel_rail
    assert rail.is_list_visible(), (
        "the rail does not start expanded, so folding it below proves nothing"
    )

    panel_id = first._right_docks[-1].objectName()
    first._on_panel_chosen(panel_id)
    qapp_module.processEvents()
    rail.set_list_visible(False)
    qapp_module.processEvents()

    group = rail.current_group()
    assert not rail.is_list_visible()
    assert group != PanelRail().current_group(), (
        f"{panel_id} lives in the rail's DEFAULT group, so a restored window "
        "that ignored the saved state entirely would still pass this"
    )

    from openchem.app.main_window import _LAYOUT_VERSION, _LAYOUT_VERSION_KEY

    settings.set_window_state(first.saveState())
    settings.set(_LAYOUT_VERSION_KEY, _LAYOUT_VERSION)

    with tempfile.TemporaryDirectory() as scratch:
        settings.set("plugins/project_directory", f"{scratch}/none")
        settings.set("plugins/user_directory", f"{scratch}/none")
        second = MainWindow(services, settings, SessionManager())
    second.resize(1280, 800)
    second.show()
    qapp_module.processEvents()

    restored = second._panel_rail
    assert not restored.is_list_visible(), "the fold was not remembered"

    visible = [d.objectName() for d in second._right_docks if not d.isHidden()]
    assert visible == [panel_id], (
        f"the restored window shows {visible}, not [{panel_id!r}]"
    )
    assert restored.current_group() == group, (
        f"the rail highlights {restored.current_group()!r} while the screen "
        f"shows a panel from {group!r} -- navigation is describing the wrong "
        "thing, which is what `select_panel` exists to prevent"
    )


def test_an_expanded_rail_is_what_an_install_with_no_setting_gets(qapp_module):
    """The other direction, and the one a missing key must give.

    Absent is not False in QSettings -- an INI backend hands back the
    STRING "false", and `bool("false")` is True, which would invert this
    for every existing install while the registry-backed one behaved. The
    control that matters is that a fresh profile gets the rail it always
    had.
    """
    import tempfile

    services = build_service_container()
    settings = Settings(services.event_bus)
    assert settings.get("ui/rail_collapsed", None) is None, (
        "this profile already carries the key, so it cannot test its absence"
    )
    with tempfile.TemporaryDirectory() as scratch:
        settings.set("plugins/project_directory", f"{scratch}/none")
        settings.set("plugins/user_directory", f"{scratch}/none")
        fresh = MainWindow(services, settings, SessionManager())
    fresh.resize(1280, 800)
    fresh.show()
    qapp_module.processEvents()

    assert fresh._panel_rail.is_list_visible(), "a fresh install got a folded rail"


def test_a_window_that_stored_an_UNFOLDED_rail_comes_back_unfolded(qapp_module):
    """The stored-False path, end to end, and it is not the absent one.

    A missing key defaults to a real `False`, so `bool()` handles it and
    the fresh-install guard above cannot see the defect. A key STORED as
    False is what an INI backend spells "false" -- and `bool("false")` is
    True, which folds the rail of every user who deliberately unfolded it.

    Driven through a real window rather than through `_as_bool`, because
    the helper being correct says nothing about the call site still
    calling it: a bare `bool()` at the read passes every other test in
    this file.
    """
    import tempfile

    from openchem.app.main_window import _RAIL_COLLAPSED_KEY

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set(_RAIL_COLLAPSED_KEY, False)
    assert settings.get(_RAIL_COLLAPSED_KEY, None) is not None, (
        "the key was not stored, so this exercises the absent path instead"
    )

    with tempfile.TemporaryDirectory() as scratch:
        settings.set("plugins/project_directory", f"{scratch}/none")
        settings.set("plugins/user_directory", f"{scratch}/none")
        window = MainWindow(services, settings, SessionManager())
    window.resize(1280, 800)
    window.show()
    qapp_module.processEvents()

    assert window._panel_rail.is_list_visible(), (
        f"a stored False ({settings.get(_RAIL_COLLAPSED_KEY, None)!r}) folded "
        "the rail -- the read is not going through `_as_bool`"
    )


def test_a_stored_false_does_not_read_back_as_folded(qapp_module):
    """`bool("false")` is True, and QSettings backends disagree.

    The registry hands back a real bool; an INI file -- which is what the
    suite's `isolated_settings` uses, and what a portable install uses --
    hands back the STRING "false". A setting read with a bare `bool()`
    therefore round-trips on one backend and inverts on the other, which
    is the shape `QSettings.setDefaultFormat` already cost this project
    once: correct-looking code, wrong on the machine that mattered.

    Driven through the real `Settings` rather than by calling `_as_bool`
    with a hand-typed string, so it is the BACKEND's spelling being
    tested and not my guess at it.
    """
    from openchem.app.main_window import _RAIL_COLLAPSED_KEY, _as_bool

    services = build_service_container()
    settings = Settings(services.event_bus)

    settings.set(_RAIL_COLLAPSED_KEY, False)
    stored = settings.get(_RAIL_COLLAPSED_KEY, None)
    assert stored is not None, "nothing was stored, so this proves nothing"
    assert not _as_bool(stored), (
        f"a stored False came back as {stored!r} and reads as folded"
    )

    settings.set(_RAIL_COLLAPSED_KEY, True)
    assert _as_bool(settings.get(_RAIL_COLLAPSED_KEY, None)), (
        "a stored True does not read back as folded"
    )


# --- the layout version, and what a saved layout cannot express -------------


def _fresh_layout_only_call_sites() -> list[str]:
    """Calls reached ONLY when no dock layout was restored.

    `_restore_window_state()` returns a bool precisely so its caller can
    apply defaults that a restored layout would otherwise skip -- its own
    docstring says "the caller gives the right-hand dock a starting width
    when one was not, and must not when one was". So a call inside
    `if not self._restore_window_state():` is, by construction, a
    behaviour an existing install never runs.

    Returns the CALL SITES observed, not a semantic taxonomy of them.
    """
    tree = ast.parse((_SRC / "openchem" / "app" / "main_window.py").read_text(encoding="utf-8"))
    found: list[str] = []

    def mentions_restore(node: ast.AST) -> bool:
        return any(
            isinstance(child, ast.Attribute) and child.attr == "_restore_window_state"
            for child in ast.walk(node)
        )

    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not mentions_restore(node.test):
            continue
        # `if not restored:` puts the fresh-layout branch in the body;
        # `if restored:` would put it in the else. Both are collected so
        # the guard does not depend on which way the condition is written.
        negated = isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not)
        branch = node.body if negated else node.orelse
        for call in (c for stmt in branch for c in ast.walk(stmt) if isinstance(c, ast.Call)):
            if isinstance(call.func, ast.Attribute):
                found.append(f"{call.func.attr}()")
    return sorted(set(found))


#: Every behaviour an install with a saved layout will NEVER run, and the
#: `_LAYOUT_VERSION` in force when the list was last reviewed.
#:
#: Pinned together on purpose: the question this guard exists to ask is
#: "did the version move when the list did".
FRESH_LAYOUT_ONLY = ["_set_initial_right_dock_width()"]
FRESH_LAYOUT_REVIEWED_AT_VERSION = "3"


def test_fresh_layout_behaviour_is_versioned():
    """Did a fresh-layout-only behaviour arrive without a version bump?

    **THE MISTAKE THIS EXISTS FOR HAPPENED, AND NOTHING CAUGHT IT.**
    `_LAYOUT_VERSION` went to "2" with the rail on 2026-08-07. The 420 px
    starting-width fix landed on 2026-08-15 and did NOT bump it, so
    `_set_initial_right_dock_width` was skipped on every install that had
    ever run the application -- including this project's own, read off the
    real registry at `ui/layout_version = 2`. The fix reached nobody until
    somebody went looking, weeks later.

    **THIS IS A PROXY, NOT THE INVARIANT, and saying so is the point.**
    The rule is "bump the version for any change a saved layout cannot
    express", which is a judgement no expression can decide. A branch
    guarded by `_restore_window_state()` is EVIDENCE of such a change:

      * it is not proof that everything found there is version-worthy --
        a `show_first_run_tip()` would sit in the same branch and want no
        bump;
      * it is not proof that every layout-affecting change is found --
        one buried in a helper called from elsewhere would not be, and
        neither would a change to what `saveState()` itself encodes.

    Claiming otherwise would be the over-broad-exclusion failure this
    repository has measured before: a guard that reads as complete, is
    not, and makes the gap invisible because it looks covered.

    So it is deliberately named for what it checks. What it buys is that
    the 2026-08-15 omission cannot happen silently a third time.
    """
    observed = _fresh_layout_only_call_sites()
    assert observed, (
        "no call site is guarded by _restore_window_state() any more. Either the "
        "fresh-layout defaults moved, or the guard's AST shape no longer matches "
        "-- both need a human, because this guard just stopped watching anything."
    )
    assert observed == sorted(FRESH_LAYOUT_ONLY), (
        "Fresh-layout-only behaviour changed:\n"
        f"    pinned:   {sorted(FRESH_LAYOUT_ONLY)}\n"
        f"    observed: {observed}\n"
        f"_LAYOUT_VERSION is currently {_LAYOUT_VERSION!r}, last reviewed at "
        f"{FRESH_LAYOUT_REVIEWED_AT_VERSION!r}.\n"
        "An install that restores a saved layout will never run the new behaviour. "
        "Does _LAYOUT_VERSION need a bump so those installs pick it up? If the "
        "behaviour is genuinely cosmetic, update the pin here and say why."
    )
    assert _LAYOUT_VERSION == FRESH_LAYOUT_REVIEWED_AT_VERSION, (
        f"_LAYOUT_VERSION is {_LAYOUT_VERSION!r} but the fresh-layout list was last "
        f"reviewed at {FRESH_LAYOUT_REVIEWED_AT_VERSION!r}. Re-read the list above "
        "and move this constant, so the two cannot drift apart unnoticed."
    )


#: The right-hand docks THIS APPLICATION builds, by `objectName()`.
#:
#: Derived from `MainWindow._right_docks`, which is a literal list built
#: before any plugin loads -- never `findChildren(QDockWidget)`, which
#: would make the pin depend on which plugins happen to be installed.
OWN_RIGHT_DOCKS = [
    "Properties",
    "Atom_Inspector",
    "Interactions",
    "Structure_Check",
    "Quantum_Chemistry",
    "Docking",
    "3D_Alignment",
    "Jobs",
    "Batch",
    "Compare",
]


def test_the_windows_own_docks_are_pinned_against_a_silent_rename(window):
    """A renamed or removed dock is the other half a saved layout cannot express.

    `QMainWindow.restoreState` matches docks by `objectName()`, so renaming
    one silently orphans that entry in every saved layout. This is the
    cheap half of the same question the AST pin asks.

    **SCOPED TO THE APPLICATION'S OWN DOCKS.** `_right_docks` plus the
    named built-ins, never `findChildren(QDockWidget)` -- a
    plugin-contributed dock would make the pin depend on which plugins
    happen to be installed, and `test_tooltip_coverage.py`'s `controls`
    fixture already sets the precedent by pointing both plugin
    directories at paths that do not exist.
    """
    observed = sorted(dock.objectName() for dock in window._right_docks)
    assert observed == sorted(OWN_RIGHT_DOCKS), (
        "The right-hand dock set changed:\n"
        f"    pinned:   {sorted(OWN_RIGHT_DOCKS)}\n"
        f"    observed: {observed}\n"
        f"_LAYOUT_VERSION is currently {_LAYOUT_VERSION!r}. `restoreState` matches "
        "docks by objectName, so a saved layout cannot express this change. Does it "
        "need a bump?"
    )
