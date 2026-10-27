"""A panel's own buttons on its dock's title bar: Results' Report menu, Structure Check's Check again, Jobs' Cancel all.

Each button starts in the panel's CURRENT state (a signal that fired before the title bar existed is gone), follows
its panel from there, does what the control it replaced did, and carries a help contract.
"""

from __future__ import annotations

import conftest
import pytest
from PySide6.QtWidgets import QApplication, QDockWidget, QMessageBox, QPushButton, QToolButton

from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis
from openchem.ui.widgets.help_tooltip import help_tooltip_for
from openchem.ui.report_format import format_report


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


def _bar(window, name):
    dock = next(d for d in window.findChildren(QDockWidget) if d.objectName() == name and d.parent() is window)
    return dock, dock.titleBarWidget()


def _button(window, dock_name, button_name) -> QToolButton:
    _dock, bar = _bar(window, dock_name)
    found = bar.findChild(QToolButton, button_name)
    assert found is not None, f"{dock_name} has no {button_name}"
    return found


def _report() -> ReportResult:
    fact = Fact(
        category=FactCategory.IDENTITY, label="Element", value=1.0, display_value="Element value",
        source="test", basis=Basis.DETERMINISTIC,
    )
    return ReportResult(molecule_uuid="m1", facts=(fact,), report_id="test_report", name="Test report")


# --- Results: the Report menu -------------------------------------------------------------------


def test_the_report_menu_starts_off_and_follows_the_reader_and_the_page(window, qapp):
    menu = _button(window, "Results", "dockAction_report")
    assert not menu.isEnabled(), "no report is showing yet"

    window._results_view._view.set_report(_report(), "Subject")
    assert menu.isEnabled()

    window._results_workspace.show_project_table()
    assert not menu.isEnabled(), "the project table has no report of its own for the menu to mean"
    window._results_workspace.show_molecule_reader()
    assert menu.isEnabled()

    window._results_view._view.clear()
    assert not menu.isEnabled()


def test_a_menu_registered_after_a_report_is_already_showing_starts_right(window, qapp):
    """The window reads the panel's state when it registers the button, so a late title bar is not left wrong."""
    window._results_view._view.set_report(_report(), "Subject")
    assert window._results_workspace.report_actions_available()
    assert window._results_workspace.report_actions_available() == _button(window, "Results", "dockAction_report").isEnabled()


def test_copy_report_puts_the_report_in_the_chosen_format_on_the_clipboard(window, qapp):
    report = _report()
    view = window._results_view._view
    view.set_report(report, "Subject")
    view._copy_format.setCurrentText("JSON")
    menu = _button(window, "Results", "dockAction_report").menu()
    copy = next(a for a in menu.actions() if a.objectName().endswith("_copy"))

    QApplication.clipboard().clear()
    copy.trigger()

    assert QApplication.clipboard().text() == format_report(report, "JSON"), "the format box's choice is kept"


def test_export_report_writes_the_chosen_format_to_the_file_picked(window, qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    report = _report()
    view = window._results_view._view
    view.set_report(report, "Subject")
    view._copy_format.setCurrentText("Markdown")
    target = tmp_path / "out.md"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    menu = _button(window, "Results", "dockAction_report").menu()

    next(a for a in menu.actions() if a.objectName().endswith("_export")).trigger()

    assert target.read_text(encoding="utf-8") == format_report(report, "Markdown")


def test_the_reader_buttons_and_the_menu_share_one_copy_path(window, qapp):
    """The Copy report button now calls the public method, so there is one way a report reaches the clipboard."""
    view = window._results_view._view
    view.set_report(_report(), "Subject")
    QApplication.clipboard().clear()
    view._copy_button.click()
    assert "Element" in QApplication.clipboard().text()


def test_a_menu_with_no_report_does_nothing_if_forced(window, qapp):
    QApplication.clipboard().clear()
    window._results_workspace.copy_report()
    assert QApplication.clipboard().text() == ""


def test_every_title_bar_button_and_menu_entry_carries_a_help_contract(window):
    for dock_name, name in (("Results", "dockAction_report"), ("Structure_Check", "dockAction_recheck"), ("Jobs", "dockAction_cancel_all")):
        button = _button(window, dock_name, name)
        assert help_tooltip_for(button) is not None, name
        assert button.accessibleName(), name
        assert button.focusPolicy().name == "NoFocus"
    for action in _button(window, "Results", "dockAction_report").menu().actions():
        assert help_tooltip_for(action) is not None, action.text()


# --- Structure Check: Check again ---------------------------------------------------------------


def test_check_again_has_one_home_the_title_bar(window):
    panel = window._structure_check_panel
    assert not [b for b in panel.findChildren(QPushButton) if b.text() == "Check again"]
    assert _button(window, "Structure_Check", "dockAction_recheck") is not None


def test_check_again_in_the_title_bar_runs_the_same_recheck(window, qapp):
    calls = []
    window._structure_check_panel._on_recheck = lambda: calls.append("recheck")
    _button(window, "Structure_Check", "dockAction_recheck").click()
    assert calls == ["recheck"]


def test_check_again_still_works_when_the_dock_is_moved_or_floated(window, qapp):
    calls = []
    window._structure_check_panel._on_recheck = lambda: calls.append("recheck")
    dock, _bar_ = _bar(window, "Structure_Check")
    window.move_dock_to(dock, window.dockWidgetArea(window._dock_named("Project_Explorer")))
    qapp.processEvents()
    _button(window, "Structure_Check", "dockAction_recheck").click()
    dock.setFloating(True)
    qapp.processEvents()
    _button(window, "Structure_Check", "dockAction_recheck").click()
    assert calls == ["recheck", "recheck"]


# --- Jobs: Cancel all ----------------------------------------------------------------------------


class _Cancels:
    """A cancel callback that records the request and leaves the job running, as a real service's does."""

    def __init__(self) -> None:
        self.requests = 0

    def __call__(self) -> None:
        self.requests += 1


def _start(window, key, cancel=None):
    manager = window._jobs_panel._job_manager
    manager.try_start("test", key, cancel_callback=cancel)
    window._jobs_panel.refresh()


def test_cancel_all_starts_off_and_tracks_the_cancellable_jobs_only(window, qapp):
    button = _button(window, "Jobs", "dockAction_cancel_all")
    manager = window._jobs_panel._job_manager
    assert not button.isEnabled()

    _start(window, "a-job-nobody-can-cancel")
    assert not button.isEnabled(), "a job with no cancel callback does not enable it"

    _start(window, "b", cancel=_Cancels())
    assert button.isEnabled()

    manager.finish("test", "b")
    window._jobs_panel.refresh()
    assert not button.isEnabled()


def test_a_button_registered_after_the_panel_last_refreshed_starts_in_the_right_state(window):
    """`cancellable_count` reads the manager now, not the last poll."""
    manager = window._jobs_panel._job_manager
    manager.try_start("test", "cannot-be-cancelled")
    manager.try_start("test", "late", cancel_callback=_Cancels())
    assert window._jobs_panel.cancellable_count() == 1, "the one that has a way to stop, not both running jobs"


def test_one_job_is_asked_without_a_question_and_the_message_says_requested(window, qapp, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: asked.append(True)))
    cancel = _Cancels()
    _start(window, "only", cancel=cancel)

    _button(window, "Jobs", "dockAction_cancel_all").click()

    assert not asked and cancel.requests == 1
    message = window.statusBar().currentMessage()
    assert "requested for 1 of 1" in message and "cancelled" not in message.lower().replace("cancellation", "")
    assert window._jobs_panel._job_manager.is_active("test", "only"), "a request is not a stop: the job stays listed"


def test_several_jobs_ask_first_and_a_no_asks_nothing_of_them(window, qapp, monkeypatch):
    first, second = _Cancels(), _Cancels()
    _start(window, "one", cancel=first)
    _start(window, "two", cancel=second)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))

    window._jobs_panel.cancel_all_jobs()
    assert (first.requests, second.requests) == (0, 0)

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    window._jobs_panel.cancel_all_jobs()
    assert (first.requests, second.requests) == (1, 1)
    assert "requested for 2 of 2" in window.statusBar().currentMessage()


def test_a_callback_that_raises_is_reported_and_the_rest_still_run(window, qapp, monkeypatch, caplog):
    good = _Cancels()

    def boom():
        raise RuntimeError("the service is gone")

    _start(window, "bad", cancel=boom)
    _start(window, "good", cancel=good)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    window._jobs_panel.cancel_all_jobs()

    assert good.requests == 1
    message = window.statusBar().currentMessage()
    assert "requested for 1 of 2" in message and "1 raised an error" in message
    assert any("Cancelling test/bad raised" in r.getMessage() for r in caplog.records), "logged, not swallowed"


def test_a_job_that_finished_before_its_turn_is_counted_as_skipped_not_asked(window, qapp, monkeypatch):
    manager = window._jobs_panel._job_manager
    survivor = _Cancels()

    def finishes_the_other_first():
        manager.finish("test", "second")
        survivor.requests += 1

    _start(window, "first", cancel=finishes_the_other_first)
    _start(window, "second", cancel=_Cancels())
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    window._jobs_panel.cancel_all_jobs()

    message = window.statusBar().currentMessage()
    assert "requested for 1 of 2" in message and "1 had already finished" in message
