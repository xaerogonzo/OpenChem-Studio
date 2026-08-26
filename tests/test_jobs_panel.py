from __future__ import annotations

import pytest

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


def _counting_table(monkeypatch):
    """Counts the two calls that DESTROY whatever was in a cell."""
    from PySide6.QtWidgets import QTableWidget

    counts = {"setItem": 0, "setCellWidget": 0}
    original_item = QTableWidget.setItem
    original_widget = QTableWidget.setCellWidget

    def set_item(self, *args, **kwargs):
        counts["setItem"] += 1
        return original_item(self, *args, **kwargs)

    def set_cell_widget(self, *args, **kwargs):
        counts["setCellWidget"] += 1
        return original_widget(self, *args, **kwargs)

    monkeypatch.setattr(QTableWidget, "setItem", set_item)
    monkeypatch.setattr(QTableWidget, "setCellWidget", set_cell_widget)
    return counts


def test_an_unchanged_job_list_rebuilds_nothing(qapp, monkeypatch):
    """The poll runs twice a second and must be free when nothing moved.

    `setItem` and `setCellWidget` DELETE whatever was in the cell, so an
    unconditional rebuild is a stream of Qt destructions -- and one landing
    inside another component's event pump is this project's documented
    crash class. Measured before this: 704 such calls fired inside
    `test_molstar_viewer_backend.py`'s `processEvents()` loop, from panels
    built five files earlier.
    """
    job_manager = JobManager()
    job_manager.try_start("conformer", "mol-1")
    panel = JobsPanel(job_manager)
    panel.refresh()

    counts = _counting_table(monkeypatch)
    panel.refresh()

    assert counts == {"setItem": 0, "setCellWidget": 0}


@pytest.mark.parametrize(
    "field, mutate",
    [
        ("kind", lambda m: (m.finish("conformer", "mol-1"), m.try_start("docking", "mol-1"))),
        ("key", lambda m: (m.finish("conformer", "mol-1"), m.try_start("conformer", "mol-2"))),
        ("message", lambda m: m.update_message("conformer", "mol-1", "3/9 conformers")),
        (
            "cancellable",
            lambda m: (
                m.finish("conformer", "mol-1"),
                m.try_start("conformer", "mol-1", cancel_callback=lambda: None),
            ),
        ),
    ],
)
def test_a_changed_job_list_does_rebuild(qapp, monkeypatch, field, mutate):
    """THE NARROW HALF, and it is the load-bearing one.

    "Never rebuild" satisfies the test above and breaks the panel outright,
    so the no-op arm alone is passed by the wrong rule.

    Parametrised over EVERY field `_rendered_state` carries, one at a time,
    because that is what makes dropping one from the snapshot a failure
    rather than a silently stale cell. A field added to `JobHandle` and
    painted into a cell belongs here as a fifth case.
    """
    job_manager = JobManager()
    job_manager.try_start("conformer", "mol-1")
    panel = JobsPanel(job_manager)
    panel.refresh()

    counts = _counting_table(monkeypatch)
    mutate(job_manager)
    panel.refresh()

    assert counts["setItem"] > 0, f"a changed {field} did not reach the table"
    assert counts["setCellWidget"] > 0, f"a changed {field} did not reach the table"
