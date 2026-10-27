"""The layout menu on every panel's title bar: what it offers, and what each entry does to the real window.

Two layers. The menu builder is pure (a `DockMenuState` in, a filled `QMenu` out), so what it offers in each state is
tested without a window. What an entry DOES -- keeps a visible dock visible, marks it placed, refuses a dock that may
not move, leaves another panel's lock alone -- needs the real `MainWindow`, whose placement bookkeeping it reuses.
"""

from __future__ import annotations

import conftest
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDockWidget, QMenu

from openchem.ui.widgets.dock_layout_menu import DockMenuState, populate_layout_menu, side_of
from openchem.ui.widgets.dock_title_bar import DockTitleBar

BOTTOM = Qt.DockWidgetArea.BottomDockWidgetArea
LEFT = Qt.DockWidgetArea.LeftDockWidgetArea
RIGHT = Qt.DockWidgetArea.RightDockWidgetArea


def _state(**changes) -> DockMenuState:
    base = dict(
        dock="Properties", floating=False, side="right", movable=True, floatable=True,
        allowed=("left", "right", "top", "bottom"), default_side="right",
    )
    base.update(changes)
    return DockMenuState(**base)


def _filled(qapp, **changes):
    menu = QMenu()
    return menu, populate_layout_menu(menu, _state(**changes))


# --- what the menu offers ----------------------------------------------------------------------


def test_a_docked_panel_may_move_to_every_other_side(qapp):
    menu, actions = _filled(qapp)
    assert [k for k in actions if k.startswith("move:")] == ["move:left", "move:right", "move:top", "move:bottom"]
    assert not actions["move:right"].isEnabled(), "it is already there"
    assert all(actions[k].isEnabled() for k in ("move:left", "move:top", "move:bottom"))


def test_a_dock_that_may_not_move_has_no_move_menu(qapp):
    menu, actions = _filled(qapp, movable=False)
    assert "move" not in actions and not [k for k in actions if k.startswith("move:")]


def test_only_the_sides_a_dock_allows_are_offered(qapp):
    menu, actions = _filled(qapp, allowed=("left", "right"))
    assert [k for k in actions if k.startswith("move:")] == ["move:left", "move:right"]


def test_a_floating_panel_can_dock_on_any_allowed_side_and_always_dock_back(qapp):
    """Whatever its features say: a capability change must never leave a floating panel with no way back."""
    menu, actions = _filled(qapp, floating=True, side="none", floatable=False)
    assert all(actions[f"move:{s}"].isEnabled() for s in ("left", "right", "top", "bottom"))
    assert actions["dock_back"].text() == "Dock panel back"
    assert "float" not in actions


def test_float_is_offered_only_to_a_floatable_docked_panel(qapp):
    assert "float" in _filled(qapp)[1]
    assert "float" not in _filled(qapp, floatable=False)[1]


def test_lock_follows_the_state_and_is_absent_for_a_panel_the_rail_does_not_own(qapp):
    open_menu, open_actions = _filled(qapp, locked=False)
    assert open_actions["lock"].text() == "Lock open"
    locked_menu, locked_actions = _filled(qapp, locked=True)
    assert locked_actions["lock"].text() == "Unlock"
    assert "lock" not in _filled(qapp, locked=None)[1]


def test_show_alongside_lists_the_targets_it_is_given(qapp):
    menu, actions = _filled(qapp, targets=(("Results", "Results"), ("Jobs", "Jobs")))
    assert [k for k in actions if k.startswith("alongside:")] == ["alongside:Results", "alongside:Jobs"]
    assert "alongside" not in _filled(qapp)[1]


def test_return_to_default_side_says_why_it_is_off(qapp):
    _menu, actions = _filled(qapp, return_enabled=False, return_reason="It is already on its starting side.")
    assert not actions["return"].isEnabled()
    assert actions["return"].toolTip() == "It is already on its starting side."
    _menu, illegal = _filled(qapp, default_side_legal=False)
    assert not illegal["return"].isEnabled() and "no longer" in illegal["return"].toolTip()


def test_expand_and_restore_appear_when_offered(qapp):
    expand_menu, expand_actions = _filled(qapp, expand="expand")
    assert expand_actions["expand"].text() == "Expand panel"
    restore_menu, restore_actions = _filled(qapp, expand="restore")
    assert restore_actions["restore"].text() == "Restore size"
    assert not [k for k in _filled(qapp)[1] if k in ("expand", "restore")]


def test_every_action_names_its_dock_and_carries_a_help_contract(qapp):
    from openchem.ui.widgets.help_tooltip import help_tooltip_for

    menu, actions = _filled(qapp, locked=False, targets=(("Results", "Results"),), expand="expand")
    for key, action in actions.items():
        if key in ("move", "alongside"):
            assert help_tooltip_for(action) is not None
            continue
        kind, dock, _argument = action.data()
        assert dock == "Properties", key
        if key.startswith(("move:", "alongside:")):
            continue
        assert help_tooltip_for(action) is not None, key
        assert action.objectName().startswith("dockMenu_")


def test_side_of_maps_qts_areas_and_names_none(qapp):
    assert side_of(LEFT) == "left" and side_of(BOTTOM) == "bottom"
    assert side_of(Qt.DockWidgetArea.NoDockWidgetArea) == "none"


# --- the real window ----------------------------------------------------------------------------


@pytest.fixture
def widgets():
    built = []
    yield built
    for widget in built:
        conftest.dispose(widget)


@pytest.fixture
def window(qapp, tmp_path, widgets):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user"))
    win = MainWindow(services, settings, SessionManager())
    widgets.append(win)
    win.show()
    qapp.processEvents()
    return win


def _dock(window, name) -> QDockWidget:
    return next(d for d in window.findChildren(QDockWidget) if d.objectName() == name and d.parent() is window)


def _settle(qapp):
    for _ in range(3):
        qapp.processEvents()
        QTest.qWait(20)


def _action(menu: QMenu, name: str) -> QAction:
    found = [a for a in menu.findChildren(QAction) if a.objectName() == name]
    assert len(found) == 1, f"{name}: {len(found)}"
    return found[0]


def test_every_dock_has_the_bar_and_the_layout_button(window):
    docks = [d for d in window.findChildren(QDockWidget) if d.parent() is window]
    assert docks
    for dock in docks:
        bar = dock.titleBarWidget()
        assert isinstance(bar, DockTitleBar), dock.objectName()
        assert bar.layout_button().objectName() == "dockLayoutButton"


def test_moving_a_visible_dock_keeps_it_visible_and_on_the_new_side(window, qapp):
    results = _dock(window, "Results")
    window._show_only_right_dock(results)
    _settle(qapp)
    assert not results.isHidden()

    window.move_dock_to(results, BOTTOM)
    _settle(qapp)

    assert window.dockWidgetArea(results) == BOTTOM
    assert not results.isHidden(), "removeDockWidget hides the dock; the move has to show it again"


def test_moving_a_hidden_dock_leaves_it_hidden(window, qapp):
    jobs = _dock(window, "Jobs")
    assert jobs.isHidden()

    window.move_dock_to(jobs, LEFT)
    _settle(qapp)

    assert window.dockWidgetArea(jobs) == LEFT and jobs.isHidden()


def test_a_move_is_the_users_placement_so_the_rail_stops_hiding_it(window, qapp):
    results = _dock(window, "Results")
    window._show_only_right_dock(results)
    window.move_dock_to(results, BOTTOM)
    _settle(qapp)

    assert "Results" in window._user_placed_docks
    window._on_panel_chosen("Properties")
    _settle(qapp)
    assert not results.isHidden(), "choosing Properties must not take a placed panel off screen"


def test_a_dock_that_may_not_move_or_may_not_go_there_is_left_alone(window, qapp):
    props = _dock(window, "Properties")
    props.setFeatures(props.features() & ~QDockWidget.DockWidgetFeature.DockWidgetMovable)
    window.move_dock_to(props, LEFT)
    assert window.dockWidgetArea(props) == RIGHT
    props.setFeatures(props.features() | QDockWidget.DockWidgetFeature.DockWidgetMovable)
    props.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
    window.move_dock_to(props, LEFT)
    assert window.dockWidgetArea(props) == RIGHT


def test_a_floating_panel_is_docked_on_the_chosen_side_and_stays_visible(window, qapp):
    props = _dock(window, "Properties")
    props.setFloating(True)
    _settle(qapp)
    assert props.isFloating()

    window.move_dock_to(props, LEFT)
    _settle(qapp)

    assert not props.isFloating() and window.dockWidgetArea(props) == LEFT and not props.isHidden()


def test_return_to_default_side_puts_it_back_and_the_classifier_decides_again(window, qapp):
    props = _dock(window, "Properties")
    window.move_dock_to(props, LEFT)
    _settle(qapp)
    assert "Properties" in window._user_placed_docks

    window.return_dock_to_default_side(props)
    _settle(qapp)

    assert window.dockWidgetArea(props) == RIGHT and not props.isHidden()
    assert "Properties" not in window._user_placed_docks, "alone on its side it is rail-managed again"


def test_return_to_default_side_touches_no_other_panel(window, qapp):
    props = _dock(window, "Properties")
    window._user_placed_docks.add("Jobs")
    window.move_dock_to(props, LEFT)
    _settle(qapp)

    window.return_dock_to_default_side(props)
    _settle(qapp)

    assert "Jobs" in window._user_placed_docks


def test_a_reset_before_the_deferred_classification_is_not_undone_by_it(window, qapp):
    """The defect the global reset used to have: a classification queued by a move fired after the reset and marked
    the dock that had just been put back as placed."""
    results = _dock(window, "Results")
    window._show_only_right_dock(results)
    window.move_dock_to(results, BOTTOM)  # queues the classification, and nothing has run it yet

    window.reset_panel_layout()
    _settle(qapp)

    assert window.dockWidgetArea(results) == RIGHT
    assert "Results" not in window._user_placed_docks
    assert not window._docks_to_classify


def test_the_menu_is_refilled_each_time_and_nothing_accumulates(window, qapp):
    bar = _dock(window, "Properties").titleBarWidget()
    menu = bar.layout_menu()
    bar._fill_menu()
    first = (len(menu.actions()), len(menu.findChildren(QMenu)))
    for _ in range(12):
        bar._fill_menu()
        qapp.processEvents()
    qapp.sendPostedEvents(None, 52)  # DeferredDelete
    assert (len(menu.actions()), len(menu.findChildren(QMenu, options=Qt.FindChildOption.FindDirectChildrenOnly))) == (
        first[0], 2
    )


def test_an_entry_of_a_submenu_reaches_the_window_through_the_menus_triggered_signal(window, qapp):
    props = _dock(window, "Properties")
    bar = props.titleBarWidget()
    bar._fill_menu()

    _action(bar.layout_menu(), "dockMenu_move_left").trigger()
    _settle(qapp)

    assert window.dockWidgetArea(props) == LEFT


def test_lock_open_flips_to_unlock_and_back_through_the_rails_own_state(window, qapp):
    bar = _dock(window, "Properties").titleBarWidget()
    bar._fill_menu()
    lock = _action(bar.layout_menu(), "dockMenu_lock")
    assert lock.text() == "Lock open"
    lock.trigger()
    _settle(qapp)
    assert "Properties" in window._panel_rail.locked_panels()

    bar._fill_menu()
    assert _action(bar.layout_menu(), "dockMenu_lock").text() == "Unlock"


def test_a_panel_the_rail_does_not_own_has_no_lock_entry(window, qapp):
    bar = _dock(window, "Project_Explorer").titleBarWidget()
    bar._fill_menu()
    assert not [a for a in bar.layout_menu().findChildren(QAction) if a.objectName() == "dockMenu_lock"]


def test_show_alongside_never_lists_the_dock_itself_and_reveals_the_chosen_panel(window, qapp):
    bar = _dock(window, "Properties").titleBarWidget()
    bar._fill_menu()
    names = [a.objectName() for a in bar.layout_menu().findChildren(QAction) if a.objectName().startswith("dockMenu_alongside_")]
    assert "dockMenu_alongside_Properties" not in names and "dockMenu_alongside_Results" in names

    results = _dock(window, "Results")
    assert results.isHidden()
    _action(bar.layout_menu(), "dockMenu_alongside_Results").trigger()
    _settle(qapp)
    assert not results.isHidden() and not _dock(window, "Properties").isHidden()


def test_the_return_entry_is_off_for_a_dock_that_needs_nothing(window, qapp):
    state = window._dock_menu_state(_dock(window, "Properties"))
    assert not state.return_enabled and state.default_side == "right"
    window.move_dock_to(_dock(window, "Properties"), LEFT)
    _settle(qapp)
    assert window._dock_menu_state(_dock(window, "Properties")).return_enabled
