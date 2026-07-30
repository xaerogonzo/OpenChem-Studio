from __future__ import annotations

import time

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.macromolecule import MacromoleculeModel


def _wait_until(qapp, predicate, timeout_seconds=15):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_add_macromolecule_adds_to_project_and_shows_in_viewer(qapp, tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    session = SessionManager()
    window = MainWindow(services, settings, session)

    macromolecule = MacromoleculeModel(
        display_name="Test structure", structure_text="HEADER\nATOM\nEND\n", source_format="pdb"
    )
    window.add_macromolecule(macromolecule)

    assert session.project is not None
    assert session.project.find_macromolecule(macromolecule.uuid) is macromolecule
    assert window._center_tabs.currentWidget() is window._macromolecule_viewer.widget()

    window._undo_stack.undo()
    assert session.project.find_macromolecule(macromolecule.uuid) is None


def test_import_macromolecule_menu_action_present(qapp, tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    session = SessionManager()
    window = MainWindow(services, settings, session)

    # Each step assigned to a named variable — PySide6/shiboken can garbage-
    # collect an intermediate wrapper (e.g. the QAction from .actions()[0])
    # if nothing holds a Python-side reference to it, taking a chained
    # `.actions()[0].menu()` expression's QMenu down with it (same class of
    # bug as the QRunnable GC issue in openchem.plugins.async_task).
    menu_bar = window.menuBar()
    menu_bar_actions = menu_bar.actions()
    file_action = menu_bar_actions[0]
    file_menu = file_action.menu()
    file_menu_actions = file_menu.actions()
    labels = [action.text() for action in file_menu_actions]
    assert "Import Macromolecule..." in labels
