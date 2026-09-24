"""Changing a menu command's shortcut: the registry, the Keyboard page, and the real window.

The shortcuts used to be set in code at ten sites and could not be changed. They are now kept by
`ShortcutRegistry`, filled as the window documents each menu action, and edited on Settings >
Keyboard. What has to hold, and why each is its own test:

* a shortcut a person chose survives a restart, and an EMPTY one is a choice, not an absence;
* a name shared by several actions (every panel's View entry) is not an id, and the ids do not
  depend on the order the menu was built in;
* a refused change says why and changes nothing, stores nothing, and the box goes back;
* the window's real actions change, not a copy.
"""

from __future__ import annotations

import logging

import pytest
from PySide6.QtGui import QAction

from openchem.app.settings import Settings
from openchem.app.shortcut_registry import (
    SHORTCUT_KEY_PREFIX,
    ShortcutRegistry,
    portable,
    refusal_for,
)
from openchem.events.base import EventBus


def _settings() -> Settings:
    return Settings(EventBus())


def _registry(settings, actions, *, apply=True):
    """A registry over `actions`, a list of (help key, label, default shortcut)."""
    registry = ShortcutRegistry(settings)
    built = []
    for key, label, shortcut in actions:
        action = QAction(label)
        if shortcut:
            action.setShortcut(shortcut)
        registry.track(key, action)
        built.append(action)
    if apply:
        registry.apply()
    return registry, built


THREE = [("undo", "&Undo", "Ctrl+Z"), ("rotate_in_3d", "Rotate in 3D", "F7"), ("exit", "Exit", "")]


# --- what may be a shortcut -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "sequence",
    ["", "Ctrl+K", "Ctrl+Shift+P", "Alt+1", "Meta+J", "F7", "Shift+F7", "Ctrl+,", "Ctrl+Alt+Shift+F12"],
)
def test_these_are_assignable(qapp, sequence):
    assert refusal_for(sequence) is None


@pytest.mark.parametrize("sequence", ["K", "7", "Shift+K", "Shift+7", "Delete", "Space"])
def test_a_bare_key_is_refused_because_the_canvas_owns_it(qapp, sequence):
    assert "canvas" in refusal_for(sequence)


def test_a_sequence_of_chords_is_refused(qapp):
    assert "one key combination" in refusal_for("Ctrl+K, Ctrl+C")


def test_text_that_is_not_a_key_is_refused(qapp):
    assert "not a key combination" in refusal_for("banana")


# --- naming the commands -----------------------------------------------------------------------------


def test_a_key_documenting_one_action_is_that_actions_name(qapp):
    registry, _ = _registry(_settings(), THREE)
    assert [e.command_id for e in registry.entries()] == ["undo", "rotate_in_3d", "exit"]
    assert registry.entry("undo").label == "Undo", "the mnemonic ampersand is not part of the name"


def test_a_key_shared_by_several_actions_is_qualified_by_each_label(qapp):
    """Every panel's View entry is documented under one key; that key alone would bind one
    shortcut to all of them."""
    docks = [("panel_visibility", name, "") for name in ("Molecules", "Properties", "Results")]
    registry, _ = _registry(_settings(), docks + [("exit", "Exit", "")])
    assert [e.command_id for e in registry.entries()] == [
        "panel_visibility:Molecules", "panel_visibility:Properties", "panel_visibility:Results", "exit",
    ]


def test_the_names_do_not_depend_on_the_order_the_menu_was_built_in(qapp):
    """A dock that moves in the View menu must not inherit another dock's stored shortcut."""
    docks = [("panel_visibility", name, "") for name in ("Molecules", "Properties", "Results")]
    forward, _ = _registry(_settings(), docks)
    backward, _ = _registry(_settings(), list(reversed(docks)))
    assert {e.command_id for e in forward.entries()} == {e.command_id for e in backward.entries()}


def test_a_label_can_say_what_a_bare_action_text_does_not(qapp):
    registry = ShortcutRegistry(_settings())
    registry.track("panel_rail_visibility", QAction("Panels"), label="Panel rail (show or hide)")
    registry.apply()
    assert registry.entry("panel_rail_visibility").label == "Panel rail (show or hide)"


def test_two_identical_labels_under_one_key_still_get_distinct_names(qapp):
    registry, _ = _registry(_settings(), [("help_topic", "Same", ""), ("help_topic", "Same", "")])
    names = [e.command_id for e in registry.entries()]
    assert len(set(names)) == 2, names


def test_a_command_registered_after_apply_is_ignored(qapp):
    """The installed-plugins menu is rebuilt later; its entries have no captured default."""
    registry, _ = _registry(_settings(), THREE)
    registry.track("late", QAction("Late"))
    registry.apply()
    assert "late" not in [e.command_id for e in registry.entries()]


# --- defaults and overrides ------------------------------------------------------------------------------


def test_the_shortcut_the_code_gave_is_the_default(qapp):
    registry, _ = _registry(_settings(), THREE)
    assert (registry.entry("rotate_in_3d").default, registry.entry("rotate_in_3d").current) == ("F7", "F7")
    assert registry.entry("exit").default == "" and registry.entry("exit").is_default


def test_a_stored_choice_is_in_force_after_apply(qapp):
    settings = _settings()
    settings.set(SHORTCUT_KEY_PREFIX + "rotate_in_3d", "Ctrl+Alt+R")
    registry, actions = _registry(settings, THREE)
    assert actions[1].shortcut().toString() == "Ctrl+Alt+R"
    entry = registry.entry("rotate_in_3d")
    assert (entry.default, entry.current, entry.is_default) == ("F7", "Ctrl+Alt+R", False)


def test_an_empty_choice_is_no_shortcut_and_survives_a_restart(qapp):
    """"" is a decision, not an absence: absence follows the default."""
    settings = _settings()
    first, _ = _registry(settings, THREE)
    assert first.set_shortcut("rotate_in_3d", "") is None

    second, actions = _registry(_settings(), THREE)   # a fresh Settings reads the file, not memory

    assert actions[1].shortcut().isEmpty()
    assert second.entry("rotate_in_3d").current == ""
    assert second.entry("rotate_in_3d").default == "F7"


def test_a_choice_survives_a_restart_as_written(qapp):
    _registry(_settings(), THREE)[0].set_shortcut("undo", "Ctrl+Alt+Z")
    assert _registry(_settings(), THREE)[0].entry("undo").current == "Ctrl+Alt+Z"


def test_choosing_the_default_again_stores_nothing(qapp):
    """So a later change of the default in code still reaches someone who never chose."""
    settings = _settings()
    registry, _ = _registry(settings, THREE)
    registry.set_shortcut("undo", "Ctrl+Alt+Z")
    assert settings.get(SHORTCUT_KEY_PREFIX + "undo") == "Ctrl+Alt+Z"

    registry.set_shortcut("undo", "Ctrl+Z")

    assert settings.get(SHORTCUT_KEY_PREFIX + "undo") is None


def test_an_unusable_stored_value_falls_back_to_the_default_and_says_so(qapp, caplog):
    settings = _settings()
    settings.set(SHORTCUT_KEY_PREFIX + "rotate_in_3d", "R")   # a bare letter, e.g. from a hand edit
    with caplog.at_level(logging.WARNING, logger="openchem.app"):
        registry, actions = _registry(settings, THREE)
    assert actions[1].shortcut().toString() == "F7"
    assert "rotate_in_3d" in caplog.text


def test_a_stored_choice_that_collides_with_a_default_yields_to_it(qapp, caplog):
    """A later release can give another command the key someone had chosen. Two actions on one
    key make Qt run neither, so the choice is dropped and the shipped default keeps the key."""
    settings = _settings()
    settings.set(SHORTCUT_KEY_PREFIX + "exit", "Ctrl+Z")      # undo ships with Ctrl+Z
    with caplog.at_level(logging.WARNING, logger="openchem.app"):
        registry, actions = _registry(settings, THREE)
    assert [a.shortcut().toString() for a in actions] == ["Ctrl+Z", "F7", ""]
    assert "collides" in caplog.text and "exit" in caplog.text


def test_two_stored_choices_on_one_key_both_return_to_their_defaults(qapp):
    settings = _settings()
    settings.set(SHORTCUT_KEY_PREFIX + "exit", "Ctrl+Alt+K")
    settings.set(SHORTCUT_KEY_PREFIX + "rotate_in_3d", "Ctrl+Alt+K")
    _registry_, actions = _registry(settings, THREE)
    assert [a.shortcut().toString() for a in actions] == ["Ctrl+Z", "F7", ""]


def test_a_stored_swap_of_two_commands_keys_is_kept_whole(qapp):
    """Each choice is the other's default, so they collide with nothing once both apply."""
    settings = _settings()
    settings.set(SHORTCUT_KEY_PREFIX + "undo", "F7")
    settings.set(SHORTCUT_KEY_PREFIX + "rotate_in_3d", "Ctrl+Z")
    _registry_, actions = _registry(settings, THREE)
    assert [a.shortcut().toString() for a in actions] == ["F7", "Ctrl+Z", ""]


def test_a_dropped_choice_can_return_a_default_that_collides_in_turn(qapp):
    """exit is chosen to F7, which rotate ships with; rotate is chosen to Ctrl+Z, which undo ships
    with. Only exit's choice collides at first; dropping it leaves the other two standing."""
    settings = _settings()
    settings.set(SHORTCUT_KEY_PREFIX + "exit", "F7")
    settings.set(SHORTCUT_KEY_PREFIX + "rotate_in_3d", "Ctrl+Z")
    _registry_, actions = _registry(settings, THREE)
    keys = [a.shortcut().toString() for a in actions]
    assert len({k for k in keys if k}) == len([k for k in keys if k]), f"two commands share a key: {keys}"


# --- refusals -------------------------------------------------------------------------------------------------


def test_a_shortcut_another_command_holds_is_refused_naming_it(qapp):
    settings = _settings()
    registry, actions = _registry(settings, THREE)

    reason = registry.set_shortcut("exit", "Ctrl+Z")

    assert "Undo" in reason and "already used" in reason
    assert actions[2].shortcut().isEmpty(), "nothing changes"
    assert actions[0].shortcut().toString() == "Ctrl+Z", "and the holder keeps it"
    assert settings.get(SHORTCUT_KEY_PREFIX + "exit") is None, "and nothing is stored"


def test_a_refused_bare_key_changes_and_stores_nothing(qapp):
    settings = _settings()
    registry, actions = _registry(settings, THREE)
    assert registry.set_shortcut("exit", "Q") is not None
    assert actions[2].shortcut().isEmpty() and settings.get(SHORTCUT_KEY_PREFIX + "exit") is None


def test_unreadable_text_is_refused_rather_than_clearing_the_shortcut(qapp):
    """Qt parses "banana" to one unknown key whose portable text is "" -- which, normalised
    before it was judged, read as a request to clear."""
    settings = _settings()
    registry, actions = _registry(settings, THREE)

    reason = registry.set_shortcut("rotate_in_3d", "banana")

    assert "not a key combination" in reason
    assert actions[1].shortcut().toString() == "F7", "a typo must not clear what was there"
    assert settings.get(SHORTCUT_KEY_PREFIX + "rotate_in_3d") is None


def test_an_unknown_command_is_refused(qapp):
    assert "no command" in _registry(_settings(), THREE)[0].set_shortcut("nothing", "Ctrl+K")


def test_giving_a_command_its_own_shortcut_again_is_not_a_conflict(qapp):
    assert _registry(_settings(), THREE)[0].set_shortcut("undo", "Ctrl+Z") is None


# --- resetting -------------------------------------------------------------------------------------------------


def test_reset_restores_the_default_and_forgets_the_choice(qapp):
    settings = _settings()
    registry, actions = _registry(settings, THREE)
    registry.set_shortcut("rotate_in_3d", "Ctrl+Alt+R")

    assert registry.reset("rotate_in_3d") is None

    assert actions[1].shortcut().toString() == "F7"
    assert settings.get(SHORTCUT_KEY_PREFIX + "rotate_in_3d") is None


def test_a_reset_is_refused_when_another_command_has_taken_the_default(qapp):
    registry, actions = _registry(_settings(), THREE)
    registry.set_shortcut("rotate_in_3d", "Ctrl+Alt+R")
    registry.set_shortcut("exit", "F7")           # exit takes the key rotate shipped with

    reason = registry.reset("rotate_in_3d")

    assert "Exit" in reason
    assert actions[1].shortcut().toString() == "Ctrl+Alt+R", "nothing changed"


def test_reset_all_never_collides_with_the_overrides_it_replaces(qapp):
    """The two commands swapped keys: each default is currently held by the other."""
    settings = _settings()
    registry, actions = _registry(settings, THREE)
    registry.set_shortcut("undo", "Ctrl+Alt+U")
    registry.set_shortcut("exit", "Ctrl+Z")       # exit now holds the key undo shipped with

    registry.reset_all()

    assert [a.shortcut().toString() for a in actions] == ["Ctrl+Z", "F7", ""]
    assert all(settings.get(SHORTCUT_KEY_PREFIX + e.command_id) is None for e in registry.entries())


def test_portable_text_is_the_stored_form(qapp):
    assert portable("ctrl+shift+p") == "Ctrl+Shift+P"


# --- the real window ----------------------------------------------------------------------------------------------


@pytest.fixture
def window(qapp, tmp_path):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    built = MainWindow(services, settings, SessionManager())
    yield built, settings
    built.close()


def _window_action(built, command_id):
    return built._shortcuts._actions[command_id]


def test_the_windows_ten_shortcuts_are_registered_with_their_defaults(window):
    built, _settings_ = window
    held = {e.command_id: e.default for e in built._shortcuts.entries() if e.default}
    assert held == {
        "search_facts": "Ctrl+Shift+F",
        "command_palette": "Ctrl+Shift+P",
        "undo": "Ctrl+Z",
        "redo": "Ctrl+Y",
        "paste_structure": "Ctrl+Shift+V",
        "settings": "Ctrl+,",
        "rotate_in_3d": "F7",
        "check_structure": "Ctrl+Shift+K",
        "recalculate_now": "F5",
        "help_current_panel": "F1",
    }, "a command that gained or lost a shortcut in code must say so here"


def test_every_command_has_a_unique_name_and_a_label(window):
    built, _settings_ = window
    entries = built._shortcuts.entries()
    assert len(entries) >= 40, "the menus registered almost nothing"
    assert len({e.command_id for e in entries}) == len(entries)
    assert all(e.label for e in entries), [e.command_id for e in entries if not e.label]


def test_the_panels_are_named_by_their_titles_not_by_a_shared_key(window):
    built, _settings_ = window
    ids = [e.command_id for e in built._shortcuts.entries()]
    assert "panel_visibility" not in ids, "twelve panels cannot share one command"
    assert any(i.startswith("panel_visibility:") for i in ids)


def test_a_choice_reaches_the_real_action_of_a_fresh_window(qapp, tmp_path):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    settings.set(SHORTCUT_KEY_PREFIX + "rotate_in_3d", "Ctrl+Alt+R")
    settings.set(SHORTCUT_KEY_PREFIX + "recalculate_now", "")
    built = MainWindow(services, settings, SessionManager())
    try:
        assert _window_action(built, "rotate_in_3d").shortcut().toString() == "Ctrl+Alt+R"
        assert _window_action(built, "recalculate_now").shortcut().isEmpty()
        assert _window_action(built, "undo").shortcut().toString() == "Ctrl+Z", "the rest keep theirs"
    finally:
        built.close()


def test_a_rebound_key_really_fires_the_command_and_the_old_one_no_longer_does(window, qapp):
    """The property the whole page is for, through the real key path (QShortcutMap), not through
    `action.shortcut()` -- which a registry could set correctly on an action Qt never consults."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    built, _settings_ = window
    built.show()
    built.activateWindow()
    QTest.qWaitForWindowActive(built, 3000)
    fired = []
    _window_action(built, "search_facts").triggered.connect(lambda *_: fired.append(1))
    old = (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier, Qt.Key.Key_F)
    new = (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier, Qt.Key.Key_F9)

    QTest.keyClick(built, old[1], old[0])
    assert len(fired) == 1, "the shipped key works before anything is changed"

    assert built._shortcuts.set_shortcut("search_facts", "Ctrl+Alt+F9") is None

    QTest.keyClick(built, old[1], old[0])
    assert len(fired) == 1, "the old key must stop working"
    QTest.keyClick(built, new[1], new[0])
    assert len(fired) == 2, "and the new one must start"


def test_settings_is_opened_with_the_windows_registry(window, monkeypatch):
    from openchem.ui.dialogs.settings_dialog import SettingsDialog

    built, _settings_ = window
    shown = []
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: shown.append(self) or 0)

    built.show_settings("keyboard")

    (dialog,) = shown
    assert dialog._shortcut_registry is built._shortcuts and dialog.current_section() == "keyboard"


# --- the page ------------------------------------------------------------------------------------------------------------


@pytest.fixture
def page(qapp):
    from openchem.ui.dialogs.keyboard_shortcuts_page import KeyboardShortcutsPage

    settings = _settings()
    registry, actions = _registry(settings, THREE)
    built = KeyboardShortcutsPage(registry)
    yield built, registry, actions, settings
    built.deleteLater()


def test_the_page_lists_every_command_with_the_shortcut_it_holds(page):
    built, _registry_, _actions, _settings_ = page
    assert built.shortcut_of("undo") == "Ctrl+Z"
    assert built.shortcut_of("rotate_in_3d") == "F7"
    assert built.shortcut_of("exit") == ""


def test_recording_a_key_changes_the_real_command(page):
    built, _registry_, actions, settings = page
    edit = built._rows["exit"][1]

    edit.setKeySequence("Ctrl+Alt+Q")
    edit.editingFinished.emit()

    assert actions[2].shortcut().toString() == "Ctrl+Alt+Q"
    assert settings.get(SHORTCUT_KEY_PREFIX + "exit") == "Ctrl+Alt+Q"
    assert built.status.text() == ""


def test_a_refused_key_puts_the_box_back_and_says_why(page):
    built, _registry_, actions, settings = page
    edit = built._rows["exit"][1]

    edit.setKeySequence("Ctrl+Z")
    edit.editingFinished.emit()

    assert "Not changed" in built.status.text() and "Undo" in built.status.text()
    assert built.shortcut_of("exit") == "" and actions[2].shortcut().isEmpty()
    assert settings.get(SHORTCUT_KEY_PREFIX + "exit") is None


def test_clearing_the_box_clears_the_shortcut(page):
    built, _registry_, actions, _settings_ = page
    built._rows["rotate_in_3d"][1].clear()
    built._rows["rotate_in_3d"][1].editingFinished.emit()
    assert actions[1].shortcut().isEmpty() and built.shortcut_of("rotate_in_3d") == ""


def test_reset_is_offered_only_where_there_is_something_to_reset(page):
    built, registry, _actions, _settings_ = page
    assert not built._rows["undo"][2].isEnabled() and not built._reset_all.isEnabled()

    built.assign("undo", "Ctrl+Alt+Z")

    assert built._rows["undo"][2].isEnabled() and not built._rows["exit"][2].isEnabled()
    assert built._reset_all.isEnabled()


def test_the_reset_button_puts_one_command_back(page):
    built, _registry_, actions, _settings_ = page
    built.assign("undo", "Ctrl+Alt+Z")
    built._rows["undo"][2].click()
    assert actions[0].shortcut().toString() == "Ctrl+Z" and built.shortcut_of("undo") == "Ctrl+Z"


def test_reset_all_puts_every_command_back(page):
    built, _registry_, actions, settings = page
    built.assign("undo", "Ctrl+Alt+Z")
    built.assign("exit", "Ctrl+Alt+Q")

    built._reset_all.click()

    assert [a.shortcut().toString() for a in actions] == ["Ctrl+Z", "F7", ""]
    assert not built._reset_all.isEnabled()
    assert settings.get(SHORTCUT_KEY_PREFIX + "undo") is None


def test_search_narrows_by_name_and_by_shortcut(page):
    built, _registry_, _actions, _settings_ = page

    def shown():
        return [c for c, (row, _e, _r) in built._rows.items() if not row.isHidden()]

    assert shown() == ["undo", "rotate_in_3d", "exit"]
    built._search.setText("rotate")
    assert shown() == ["rotate_in_3d"]
    built._search.setText("ctrl+z")
    assert shown() == ["undo"], "by the shortcut it holds"
    built._search.setText("nothing matches this")
    assert shown() == []
    built._search.setText("")
    assert len(shown()) == 3


def test_a_recorder_takes_one_combination_only(page):
    built, _registry_, _actions, _settings_ = page
    assert built._rows["undo"][1].maximumSequenceLength() == 1


def test_a_page_without_a_registry_says_so_and_offers_no_change(qapp):
    from openchem.ui.dialogs.keyboard_shortcuts_page import KeyboardShortcutsPage

    built = KeyboardShortcutsPage(None)
    assert built._rows == {} and not built._reset_all.isEnabled()
    assert built.assign("undo", "Ctrl+K") is not None
    built.deleteLater()
