"""Settings > Appearance and View > Theme are ONE setting: each reads it, each writes it, each follows the other.

The checked View entry is the stored CHOICE, never the resulting look: with "Follow the System" chosen it stays
checked whichever way Windows is. Combo rows are looked up by their stored integer, never by position.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QComboBox

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import APPEARANCE, Settings
from openchem.bootstrap import build_service_container
from openchem.domain.appearance import Appearance
from openchem.ui.dialogs.settings_dialog import APPEARANCE_SECTION, SECTIONS, SettingsDialog

_WINDOWS: list = []
_DIALOGS: list = []


def _combo(settings: Settings) -> QComboBox:
    """The page's combo, with its dialog kept alive: a combo whose dialog was collected is a deleted C++ object."""
    dialog = SettingsDialog(settings)
    _DIALOGS.append(dialog)
    return dialog.findChild(QComboBox, "appearanceChoice")


@pytest.fixture(autouse=True)
def _close_windows(qapp):
    """Close AND delete: a window that is only closed stays alive for the rest of the run, and with
    thousands of them about every later palette change takes longer than a timing test waits."""
    yield
    while _WINDOWS:
        window = _WINDOWS.pop()
        window.close()
        window.deleteLater()
    for dialog in _DIALOGS:
        dialog.deleteLater()
    _DIALOGS.clear()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def _window(tmp_path) -> tuple[MainWindow, Settings]:
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    window = MainWindow(services, settings, SessionManager())
    _WINDOWS.append(window)
    return window, settings


def _checked(window: MainWindow) -> list[int]:
    return [mode for mode, action in window._theme_actions.items() if action.isChecked()]


def _choose_in_combo(combo: QComboBox, mode: Appearance) -> None:
    combo.setCurrentIndex(combo.findData(int(mode)))


# --- the page ---------------------------------------------------------------------------------


def test_appearance_is_the_first_section_and_opens_on_request(qapp):
    assert SECTIONS[0][0] == APPEARANCE_SECTION
    dialog = SettingsDialog(Settings(build_service_container().event_bus), section=APPEARANCE_SECTION)
    assert dialog.current_section() == APPEARANCE_SECTION


def test_the_combo_offers_each_choice_with_its_stored_integer(qapp):
    combo = _combo(Settings(build_service_container().event_bus))

    offered = {combo.itemData(row): combo.itemText(row) for row in range(combo.count())}

    assert offered == {0: "Follow the system", 1: "Light", 2: "Dark"}


@pytest.mark.parametrize("mode", list(Appearance))
def test_the_combo_starts_on_the_stored_choice(qapp, mode):
    settings = Settings(build_service_container().event_bus)
    settings.set_preference(APPEARANCE, int(mode))

    combo = _combo(settings)

    assert combo.currentData() == int(mode)


def test_a_damaged_stored_value_shows_as_follow_the_system(qapp):
    settings = Settings(build_service_container().event_bus)
    settings.set(APPEARANCE.key, "banana")

    combo = _combo(settings)

    assert combo.currentData() == int(Appearance.SYSTEM)


@pytest.mark.parametrize("mode", list(Appearance))
def test_choosing_in_settings_stores_the_integer(qapp, mode):
    settings = Settings(build_service_container().event_bus)
    combo = _combo(settings)

    _choose_in_combo(combo, Appearance.DARK if mode is Appearance.SYSTEM else Appearance.SYSTEM)
    _choose_in_combo(combo, mode)

    assert settings.preference(APPEARANCE) == int(mode)


# --- the menu ---------------------------------------------------------------------------------


def test_the_view_menu_has_a_theme_submenu_with_one_entry_per_choice(qapp, tmp_path):
    window, _settings = _window(tmp_path)

    theme_menu = next(a.menu() for a in window._view_menu.actions() if a.text() == "Theme")

    assert [a.text() for a in theme_menu.actions()] == ["Follow the System", "Light", "Dark"]
    assert all(a.isCheckable() for a in theme_menu.actions())


def test_the_menu_starts_on_the_stored_choice(qapp, tmp_path):
    services = build_service_container()
    Settings(services.event_bus).set_preference(APPEARANCE, int(Appearance.DARK))

    window, settings = _window(tmp_path)

    assert settings.preference(APPEARANCE) == int(Appearance.DARK)
    assert _checked(window) == [int(Appearance.DARK)]


def test_a_fresh_install_has_follow_the_system_checked(qapp, tmp_path):
    window, _settings = _window(tmp_path)

    assert _checked(window) == [int(Appearance.SYSTEM)]


@pytest.mark.parametrize("mode", [Appearance.LIGHT, Appearance.DARK, Appearance.SYSTEM])
def test_choosing_in_the_menu_stores_the_integer(qapp, tmp_path, mode):
    window, settings = _window(tmp_path)

    window._theme_actions[int(mode)].trigger()

    assert settings.preference(APPEARANCE) == int(mode)
    assert _checked(window) == [int(mode)]


def test_a_change_in_settings_moves_the_menu(qapp, tmp_path):
    window, settings = _window(tmp_path)

    settings.set_preference(APPEARANCE, int(Appearance.DARK))

    assert _checked(window) == [int(Appearance.DARK)]


def test_a_damaged_stored_value_leaves_follow_the_system_checked(qapp, tmp_path):
    window, settings = _window(tmp_path)
    window._theme_actions[int(Appearance.DARK)].trigger()

    settings.set(APPEARANCE.key, "banana")

    assert _checked(window) == [int(Appearance.SYSTEM)]


# --- one setting ------------------------------------------------------------------------------


def test_the_menu_moves_the_open_settings_page(qapp, tmp_path):
    window, settings = _window(tmp_path)
    dialog = SettingsDialog(settings)
    combo = dialog.findChild(QComboBox, "appearanceChoice")

    window._theme_actions[int(Appearance.DARK)].trigger()

    assert combo.currentData() == int(Appearance.DARK)


def test_the_settings_page_moves_the_menu(qapp, tmp_path):
    window, settings = _window(tmp_path)
    combo = _combo(settings)

    _choose_in_combo(combo, Appearance.LIGHT)

    assert _checked(window) == [int(Appearance.LIGHT)]


def test_following_a_change_does_not_write_it_back(qapp, tmp_path):
    """Two controls reflecting each other must not become two writers answering each other."""
    window, settings = _window(tmp_path)
    dialog = SettingsDialog(settings)
    writes: list[str] = []
    settings.on_change(lambda event: writes.append(event.key))

    window._theme_actions[int(Appearance.DARK)].trigger()

    assert writes.count(APPEARANCE.key) == 1
    assert dialog.findChild(QComboBox, "appearanceChoice").currentData() == int(Appearance.DARK)


def test_a_closed_settings_page_does_not_break_a_later_change(qapp, tmp_path):
    window, settings = _window(tmp_path)
    dialog = SettingsDialog(settings)
    dialog.deleteLater()
    qapp.processEvents()
    del dialog

    window._theme_actions[int(Appearance.LIGHT)].trigger()

    assert settings.preference(APPEARANCE) == int(Appearance.LIGHT)
