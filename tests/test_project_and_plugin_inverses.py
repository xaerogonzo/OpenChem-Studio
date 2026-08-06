"""Closing a project, and unloading a plugin.

The project half found real defects and is tested below. The plugin half
found none; why it is recorded rather than tested is at the bottom of this
file.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel


@pytest.fixture
def widgets():
    built = []
    yield built
    for widget in built:
        widget.close()
        widget.setParent(None)
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


@pytest.fixture
def window(qapp, tmp_path, widgets):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user"))
    main_window = MainWindow(services, settings, SessionManager())
    widgets.append(main_window)
    return main_window


# --- the undo stack belongs to the document ---------------------------------


def test_opening_a_new_project_clears_the_undo_stack(window, qapp):
    """Every command holds a direct reference to the project it was built
    against, so a stack that outlives the document points at a dead one."""
    window.add_molecule(MoleculeModel(display_name="A-one"))
    qapp.processEvents()
    assert window._undo_stack.count() > 0

    window._set_project(ProjectModel(name="Second"))
    qapp.processEvents()

    # The new project auto-creates a molecule, which is one command of its
    # own -- what must be gone is everything from before it.
    assert window._undo_stack.count() <= 1


def test_undo_after_switching_cannot_reach_the_previous_project(window, qapp):
    """The measured failure.

    Three Ctrl+Z presses after File > New Project walked back into the
    previous project and emptied it -- ['New molecule', 'A-one', 'A-two']
    to [] -- while the Project Explorer showed the new one and nothing
    appeared to happen.
    """
    window.add_molecule(MoleculeModel(display_name="A-one"))
    window.add_molecule(MoleculeModel(display_name="A-two"))
    qapp.processEvents()
    first = window._session.project
    before = [m.display_name for m in first.molecules]

    window._set_project(ProjectModel(name="Second"))
    qapp.processEvents()
    for _ in range(6):
        if not window._undo_stack.canUndo():
            break
        window._undo_stack.undo()
        qapp.processEvents()

    assert [m.display_name for m in first.molecules] == before


def test_a_freshly_opened_project_is_not_dirty(window, qapp):
    """`_set_project` auto-creates a molecule, which marks the session
    dirty. Without clearing it afterwards every New Project would prompt
    "you have unsaved changes" over work nobody did."""
    window._set_project(ProjectModel(name="Fresh"))
    qapp.processEvents()

    assert not window._session.is_dirty


def test_editing_marks_the_session_dirty(window, qapp):
    """The complement -- the flag has to actually rise, or the guard is
    decoration."""
    window._set_project(ProjectModel(name="Fresh"))
    qapp.processEvents()

    window.add_molecule(MoleculeModel(display_name="Real work"))
    qapp.processEvents()

    assert window._session.is_dirty


def test_a_clean_project_needs_no_confirmation(window, qapp):
    """No prompt when there is nothing to lose; the guard must not become
    a dialog on every File > New."""
    window._set_project(ProjectModel(name="Fresh"))
    qapp.processEvents()

    assert window._confirm_discarding_unsaved_changes() is True


# --- plugin unload -----------------------------------------------------------
#
# MEASURED CLEAN, AND DELIBERATELY NOT TESTED HERE.
#
# Unloading a plugin removes its dock and its menu actions, and reload
# restores both exactly: three unload/reload cycles of `database_search`
# left the dock list identical (11 -> 10 -> 11 each time) and the View menu
# byte-identical with no duplicate entries.
#
# The obvious test for that is not worth its cost. It has to load the REAL
# plugins -- their panels are what unload is supposed to remove -- and each
# carries a web view, so three cycles builds and tears down nine of them.
# Written and run, it hung the suite, which is precisely the Chromium
# accumulation `dispose_web_engine_views` in conftest.py exists to prevent
# and which CLAUDE.md records as having cost two 40-minute stalls.
#
# So the result is recorded here rather than re-derived. To re-check it by
# hand, load a window against the real `plugins/` directory and compare
# dock names across an unload/reload cycle -- flushing each dock's
# DeferredDelete first, because `remove_panel` uses `deleteLater()` and
# `processEvents()` does not deliver it. Skipping that flush is what made
# the first measurement report a leak that was not there.
