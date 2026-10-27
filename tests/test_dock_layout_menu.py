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


def _build_window(tmp_path):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user"))
    win = MainWindow(services, settings, SessionManager())
    win.show()
    return win


@pytest.fixture(scope="module")
def _shared_window(qapp, tmp_path_factory):
    """ONE real window for the module, with each dock's starting features recorded.

    Building a `MainWindow` is the expensive part of every test here, and in a shard process that has been running
    for twenty minutes it costs several times what it does alone: with a window per test this file added about two
    minutes to the tightest shard and pushed it over its 30-minute limit. The tests share the window and `window`
    puts it back before and after each one.
    """
    win = _build_window(tmp_path_factory.mktemp("dock_layout_menu"))
    qapp.processEvents()
    defaults = {
        d.objectName(): (d.features(), d.allowedAreas())
        for d in win.findChildren(QDockWidget)
        if d.parent() is win
    }
    yield win, defaults
    conftest.dispose(win)


def _reset(win, defaults, qapp) -> None:
    """Everything a test here can change, put back: expansion, pending classification, features, placement, size."""
    win._expand_timer.stop()
    win._expand_state = None
    win._classify_timer.stop()
    win._docks_to_classify.clear()
    for dock in win.findChildren(QDockWidget):
        if dock.parent() is not win or dock.objectName() not in defaults:
            continue
        features, allowed = defaults[dock.objectName()]
        dock.setFloating(False)
        dock.setFeatures(features)
        dock.setAllowedAreas(allowed)
    win._user_placed_docks.clear()
    win.resize(1700, 900)
    win.reset_panel_layout()
    win.statusBar().clearMessage()
    for _ in range(3):
        qapp.processEvents()


@pytest.fixture
def window(_shared_window, qapp):
    win, defaults = _shared_window
    _reset(win, defaults, qapp)
    yield win
    _reset(win, defaults, qapp)


@pytest.fixture
def fresh_window(qapp, tmp_path):
    """A window of its own, for the one test that closes it."""
    win = _build_window(tmp_path)
    qapp.processEvents()
    yield win
    conftest.dispose(win)


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


# --- Expand panel / Restore size ----------------------------------------------------------------


def _sizes(window) -> dict[str, tuple[int, int]]:
    return {
        d.objectName(): (d.width(), d.height())
        for d in window.findChildren(QDockWidget)
        if d.parent() is window and not d.isHidden() and not d.isFloating()
    }


@pytest.fixture
def roomy(window, qapp):
    """The shared window is already 1700 px wide, so the right dock has somewhere to grow, as the default one on a
    laptop screen has not."""
    _settle(qapp)
    return window


def test_expanding_a_panel_grows_it_and_restoring_puts_every_dock_back_exactly(roomy, qapp):
    props = _dock(roomy, "Properties")
    before = _sizes(roomy)

    roomy.expand_dock(props)
    _settle(qapp)
    during = _sizes(roomy)
    assert roomy._expand_state is not None and roomy._expand_state.dock == "Properties"
    assert during["Properties"][0] > before["Properties"][0] + 24
    assert during["Project_Explorer"][0] < before["Project_Explorer"][0], "Qt gives the room up from the others"

    roomy._resolve_expansion()
    _settle(qapp)
    assert _sizes(roomy) == before, "a restore of the one dock would have left the explorer shrunk"
    assert roomy._expand_state is None


def test_one_expansion_at_a_time_and_the_second_restores_the_first(roomy, qapp):
    props, explorer = _dock(roomy, "Properties"), _dock(roomy, "Project_Explorer")
    base = _sizes(roomy)

    roomy.expand_dock(props)
    _settle(qapp)
    roomy.expand_dock(explorer)
    _settle(qapp)

    assert roomy._expand_state.dock == "Project_Explorer"
    assert _sizes(roomy)["Properties"][0] <= base["Properties"][0] + 1, "the first expansion was undone first"
    roomy._resolve_expansion()
    _settle(qapp)
    assert _sizes(roomy) == base


def test_an_expansion_with_nothing_to_gain_is_undone_and_says_so(roomy, qapp, monkeypatch):
    from openchem.app import dock_expansion

    props = _dock(roomy, "Properties")
    before = _sizes(roomy)
    monkeypatch.setattr(dock_expansion, "MIN_GAIN", 100000)

    roomy.expand_dock(props)
    _settle(qapp)

    assert roomy._expand_state is None
    assert _sizes(roomy) == before
    assert "Nothing to expand" in roomy.statusBar().currentMessage()


@pytest.mark.parametrize("operation", ["move", "float", "return", "alongside", "rail", "hide", "reset"])
def test_any_other_change_to_the_layout_ends_the_expansion(roomy, qapp, operation):
    props, results = _dock(roomy, "Properties"), _dock(roomy, "Results")
    base = _sizes(roomy)
    roomy.expand_dock(props)
    _settle(qapp)
    assert roomy._expand_state is not None

    if operation == "move":
        roomy.move_dock_to(results, BOTTOM)
    elif operation == "float":
        results.setFloating(True)
    elif operation == "return":
        roomy.return_dock_to_default_side(props)
    elif operation == "alongside":
        roomy._on_panel_chosen_alongside("Results")
    elif operation == "rail":
        roomy._on_panel_chosen("Jobs")
    elif operation == "hide":
        _dock(roomy, "Project_Explorer").hide()
    elif operation == "reset":
        roomy.reset_panel_layout()
    _settle(qapp)

    assert roomy._expand_state is None
    assert not roomy._expand_timer.isActive()
    if operation == "reset":
        assert _sizes(roomy)["Properties"][0] <= base["Properties"][0] + 24


def test_resizing_the_window_keeps_the_panel_expanded_and_the_state_agrees(roomy, qapp):
    """Qt lets an expanded panel shrink back when the window is resized and does not grow it again; the window does,
    so the menu, the state and the geometry never disagree (regression: an expansion with no usable Restore size)."""
    props = _dock(roomy, "Properties")
    roomy.expand_dock(props)
    _settle(qapp)
    expanded = props.width()
    assert expanded > 0

    roomy.resize(1500, 800)
    QTest.qWait(250)
    _settle(qapp)
    narrow = props.width()
    roomy.resize(1700, 900)
    QTest.qWait(250)
    _settle(qapp)

    state = roomy._dock_menu_state(props)
    assert roomy._expand_state is not None and state.expand == "restore", "the menu still offers Restore size"
    assert props.width() >= expanded - 8, f"expanded {expanded}, after the round trip {props.width()}, narrow {narrow}"
    assert roomy.dock_layout_report()["expanded"] == "Properties"


def test_the_report_says_which_panel_is_expanded(roomy, qapp):
    assert roomy.dock_layout_report()["expanded"] is None
    roomy.expand_dock(_dock(roomy, "Properties"))
    assert roomy.dock_layout_report()["expanded"] == "Properties"


def test_closing_while_expanded_saves_the_normal_layout_not_the_expanded_one(fresh_window, qapp, monkeypatch):
    roomy = fresh_window
    roomy.resize(1700, 900)
    _settle(qapp)
    props = _dock(roomy, "Properties")
    base = props.width()
    roomy.expand_dock(props)
    _settle(qapp)
    assert props.width() > base + 24

    seen = {}
    real = roomy.saveState

    def spy(*args):
        seen["width"] = props.width()
        return real(*args)

    monkeypatch.setattr(roomy, "saveState", spy)
    monkeypatch.setattr(roomy, "_confirm_discarding_unsaved_changes", lambda: True)
    roomy.close()

    assert roomy._expand_state is None
    assert abs(seen["width"] - base) <= 2, f"saved at {seen['width']}, the normal width was {base}"


def test_the_menu_offers_expand_then_restore_and_never_for_a_floating_panel(roomy, qapp):
    props = _dock(roomy, "Properties")
    assert roomy._dock_menu_state(props).expand == "expand"
    roomy.expand_dock(props)
    assert roomy._dock_menu_state(props).expand == "restore"
    assert roomy._dock_menu_state(_dock(roomy, "Project_Explorer")).expand == "expand"
    roomy._resolve_expansion()
    props.setFloating(True)
    _settle(qapp)
    assert roomy._dock_menu_state(props).expand == ""


def test_a_panel_sharing_a_tab_group_is_refused_with_its_reason(roomy, qapp):
    props, results = _dock(roomy, "Properties"), _dock(roomy, "Results")
    results.show()
    roomy.tabifyDockWidget(props, results)
    _settle(qapp)

    state = roomy._dock_menu_state(props)
    assert state.expand == "expand" and not state.expand_enabled and "tab group" in state.expand_reason
    roomy.expand_dock(props)
    assert roomy._expand_state is None


def test_the_expand_entry_works_from_the_real_menu(roomy, qapp):
    props = _dock(roomy, "Properties")
    bar = props.titleBarWidget()
    bar._fill_menu()
    _action(bar.layout_menu(), "dockMenu_expand").trigger()
    _settle(qapp)
    assert roomy._expand_state is not None
    bar._fill_menu()
    _action(bar.layout_menu(), "dockMenu_restore").trigger()
    _settle(qapp)
    assert roomy._expand_state is None
