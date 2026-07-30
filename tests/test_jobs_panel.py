from __future__ import annotations

from openchem.services.job_manager import JobManager
from openchem.ui.panels.jobs_panel import JobsPanel


def test_refresh_lists_active_jobs(qapp):
    job_manager = JobManager()
    job_manager.try_start("conformer", "mol-1")
    job_manager.try_start("docking", "lig-1:rec-1")
    panel = JobsPanel(job_manager)

    panel.refresh()

    assert panel._table.rowCount() == 2
    kinds = {panel._table.item(row, 0).text() for row in range(2)}
    assert kinds == {"conformer", "docking"}


def test_refresh_shows_the_latest_message(qapp):
    job_manager = JobManager()
    job_manager.try_start("conformer", "mol-1")
    job_manager.update_message("conformer", "mol-1", "3/9 conformers")
    panel = JobsPanel(job_manager)

    panel.refresh()

    assert panel._table.item(0, 2).text() == "3/9 conformers"


def test_refresh_reflects_a_finished_job_disappearing(qapp):
    job_manager = JobManager()
    job_manager.try_start("conformer", "mol-1")
    panel = JobsPanel(job_manager)
    panel.refresh()
    assert panel._table.rowCount() == 1

    job_manager.finish("conformer", "mol-1")
    panel.refresh()

    assert panel._table.rowCount() == 0


def test_cancel_button_disabled_without_a_callback(qapp):
    job_manager = JobManager()
    job_manager.try_start("conformer", "mol-1")  # no cancel_callback given
    panel = JobsPanel(job_manager)

    panel.refresh()

    cancel_button = panel._table.cellWidget(0, 3)
    assert cancel_button.isEnabled() is False


def test_cancel_button_enabled_and_wired_to_job_manager_cancel(qapp):
    job_manager = JobManager()
    calls = []
    job_manager.try_start("conformer", "mol-1", cancel_callback=lambda: calls.append(1))
    panel = JobsPanel(job_manager)
    panel.refresh()

    cancel_button = panel._table.cellWidget(0, 3)
    assert cancel_button.isEnabled() is True

    cancel_button.click()

    assert calls == [1]
