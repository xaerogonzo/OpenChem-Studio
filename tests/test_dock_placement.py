"""A panel the user puts somewhere stays there when the rail is used.

Reported: Results dragged to the top of the window disappeared the moment
Properties was picked, so the two could never be on screen together without
floating one. Measured with `dock_report` before the fix: Results at the
top, choose Properties, Results hidden. `_show_only_right_dock` hid every
non-floating dock in `_right_docks` wherever it lived.

Each test moves docks with `addDockWidget` / `splitDockWidget` /
`tabifyDockWidget` OUTSIDE the window's arranging guard, which reaches the
same `dockLocationChanged` / `topLevelChanged` a real drop does. The overlap
check reads rectangles rather than pixels, for the reason `dock_report`
gives.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget

TOP = Qt.DockWidgetArea.TopDockWidgetArea
RIGHT = Qt.DockWidgetArea.RightDockWidgetArea
LEFT = Qt.DockWidgetArea.LeftDockWidgetArea


@pytest.fixture
def window(qapp, tmp_path):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none"))
    built = MainWindow(services, settings, SessionManager())
    built.resize(1600, 900)
    built.show()
    _settle(qapp)
    yield built
    built.close()


def _settle(qapp) -> None:
    for _ in range(10):
        qapp.processEvents()


def _dock(window, name) -> QDockWidget:
    return window.findChild(QDockWidget, name)


def _choose(window, qapp, name) -> None:
    window._on_panel_chosen(name)
    _settle(qapp)


def _visible(window, name) -> bool:
    return not _dock(window, name).isHidden()


def test_construction_and_a_restored_layout_place_nothing(window):
    assert window._user_placed_docks == set()


def test_a_panel_moved_to_another_side_survives_choosing_another(window, qapp):
    """THE REPORTED CASE."""
    window.addDockWidget(TOP, _dock(window, "Results"))
    _dock(window, "Results").show()
    _settle(qapp)

    _choose(window, qapp, "Properties")

    assert _visible(window, "Results") and _visible(window, "Properties")
    assert window.dock_layout_report()["overlaps"] == []


def test_a_layout_saved_before_placement_was_tracked_keeps_its_moved_panel(window, qapp):
    """The FIRST launch after this change, on a layout like the reported one.

    A saved state with Results at the top carries no placement record, so the
    placed rule cannot protect it -- only the AREA rule can. A mutation that
    removed the area check left every other test here green; this is the
    case it exists for.
    """
    window._arranging = True  # as `restoreState` runs
    window.addDockWidget(TOP, _dock(window, "Results"))
    _dock(window, "Results").show()
    window._arranging = False
    _settle(qapp)
    assert "Results" not in window._user_placed_docks

    _choose(window, qapp, "Properties")

    assert _visible(window, "Results") and _visible(window, "Properties")


def test_a_panel_split_beside_another_stays_while_the_rail_swaps_the_other(window, qapp):
    results = _dock(window, "Results")
    window.splitDockWidget(_dock(window, "Properties"), results, Qt.Orientation.Vertical)
    results.show()
    _settle(qapp)
    assert "Results" in window._user_placed_docks

    _choose(window, qapp, "Atom_Inspector")

    assert _visible(window, "Results")
    assert _visible(window, "Atom_Inspector")
    assert not _visible(window, "Properties")
    assert window.dock_layout_report()["overlaps"] == []


def test_dropping_a_panel_back_alone_hands_it_back_to_the_rail(window, qapp):
    results = _dock(window, "Results")
    window.addDockWidget(TOP, results)
    results.show()
    _settle(qapp)
    assert "Results" in window._user_placed_docks

    _dock(window, "Properties").hide()
    window.addDockWidget(RIGHT, results)
    _settle(qapp)
    assert "Results" not in window._user_placed_docks

    _choose(window, qapp, "Properties")
    assert not _visible(window, "Results")


def test_a_floating_panel_is_never_hidden_by_the_rail(window, qapp):
    properties = _dock(window, "Properties")
    properties.setFloating(True)
    properties.show()
    _settle(qapp)

    _choose(window, qapp, "Results")
    _choose(window, qapp, "Atom_Inspector")

    assert _visible(window, "Properties")


def test_the_rail_still_shows_one_managed_panel_at_a_time(window, qapp):
    """The rule that was right stays right: nothing placed, one panel."""
    for name in ("Results", "Atom_Inspector", "Properties"):
        _choose(window, qapp, name)
        shown = [d.objectName() for d in window._right_docks if not d.isHidden()]
        assert shown == [name]


@pytest.mark.parametrize("arrangement", ["floating", "other_side", "tabified", "split"])
def test_reset_puts_every_arrangement_back(window, qapp, arrangement):
    results, properties = _dock(window, "Results"), _dock(window, "Properties")
    if arrangement == "floating":
        results.setFloating(True)
        results.show()
    elif arrangement == "other_side":
        window.addDockWidget(LEFT, results)
        results.show()
    elif arrangement == "tabified":
        window.tabifyDockWidget(properties, results)
        results.show()
    else:
        window.splitDockWidget(properties, results, Qt.Orientation.Vertical)
        results.show()
    _settle(qapp)

    window.reset_panel_layout()
    _settle(qapp)

    report = {d["id"]: d for d in window.dock_layout_report()["docks"]}
    assert window._user_placed_docks == set()
    assert not any(d["floating"] for d in report.values())
    assert report["Results"]["area"] == "right" and report["Results"]["tabified_with"] == []
    assert [d.objectName() for d in window._right_docks if not d.isHidden()] == ["Properties"]
    assert window.dock_layout_report()["overlaps"] == []


def test_placement_is_saved_with_the_layout(qapp, tmp_path):
    from openchem.app.main_window import _USER_PLACED_KEY, MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none"))
    first = MainWindow(services, settings, SessionManager())
    first.show()
    _settle(qapp)
    first.addDockWidget(TOP, _dock(first, "Results"))
    _dock(first, "Results").show()
    _settle(qapp)
    first._session.mark_clean()
    first.close()
    assert settings.get(_USER_PLACED_KEY, "") == "Results"

    second = MainWindow(build_service_container(), settings, SessionManager())
    try:
        assert second._user_placed_docks == {"Results"}
    finally:
        second.close()


def test_a_side_by_side_split_costs_no_more_than_the_second_panel(window, qapp):
    """What a split may do to the window minimum, stated so it holds anywhere.

    **NOT `<= 1366`, AND THAT WAS MEASURED.** Under `offscreen` the split
    window's minimum is 1442 px; in the running app on Windows it is 1009
    (default 889). `test_right_dock_width` records the same ~270 px gap
    between the two environments, so an absolute threshold is a statement
    about the font, not the product. The structural claim is that putting
    Results beside Properties adds at most Results' own minimum width -- the
    failure this guards is a split that drags some OTHER widget's minimum
    into the row, which is how the window reached 1474 px once before.
    """
    before = window.minimumSizeHint().width()
    results = _dock(window, "Results")
    window.splitDockWidget(_dock(window, "Properties"), results, Qt.Orientation.Horizontal)
    results.show()
    _settle(qapp)

    from PySide6.QtWidgets import QStyle

    added = window.minimumSizeHint().width() - before
    # Plus the separator a split puts between the two -- measured at 6 px
    # here, asked of the style rather than written in.
    separator = window.style().pixelMetric(QStyle.PixelMetric.PM_DockWidgetSeparatorExtent, None, window)
    allowed = results.minimumSizeHint().width() + separator
    assert added <= allowed, (before, added, allowed)


def test_locking_a_split_panel_keeps_it_and_unlocking_lets_a_click_replace_it(window, qapp):
    """The reported flow: panels once dropped beside each other stayed on screen through every rail click. The lock is
    what says so, and what releases them."""
    results = _dock(window, "Results")
    window.splitDockWidget(_dock(window, "Properties"), results, Qt.Orientation.Vertical)
    results.show()
    _settle(qapp)
    assert "Results" in window._user_placed_docks, "a drop beside another panel locks it"
    assert "Results" in window._panel_rail.locked_panels(), "and the rail shows it"

    _choose(window, qapp, "Atom_Inspector")
    assert _visible(window, "Results")

    window._on_panel_lock_toggled("Results")
    assert window._panel_rail.locked_panels().isdisjoint({"Results", "Properties"})
    _choose(window, qapp, "Structure_Check")

    assert _visible(window, "Structure_Check")
    assert not _visible(window, "Results")
    assert not _visible(window, "Properties")


def test_open_beside_hides_nothing_and_a_plain_click_then_replaces_the_unlocked(window, qapp):
    window._on_panel_chosen("Properties")
    _settle(qapp)
    window._on_panel_chosen_alongside("Results")
    _settle(qapp)
    assert _visible(window, "Properties") and _visible(window, "Results")

    _choose(window, qapp, "Atom_Inspector")
    assert _visible(window, "Atom_Inspector")
    assert not _visible(window, "Properties") and not _visible(window, "Results")


def test_a_locked_panel_survives_a_click_that_would_replace_it(window, qapp):
    window._on_panel_chosen("Properties")
    _settle(qapp)
    window._on_panel_lock_toggled("Properties")
    _choose(window, qapp, "Results")
    assert _visible(window, "Properties")
    assert "Properties" in window._panel_rail.locked_panels()
