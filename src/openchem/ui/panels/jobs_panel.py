from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.services.job_manager import JobManager
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

_COLUMNS = ("Kind", "Key", "Status", "")

#: FOUR CONCEPTS, and the fourth column has no header TEXT because it holds
#: a button rather than a value. That is not a reason to leave it
#: undocumented: it is the only column whose contents depend on something
#: the user cannot see, namely whether the service that started the job
#: offered a way to stop it.
_COLUMN_HELP = {
    "Kind": HelpTooltip(
        text=(
            "Which kind of work this is -- conformer generation, docking or "
            "a quantum chemistry run.\n\n"
            "Every service that runs work in the background registers it "
            "here, so this list is the whole of what the application is "
            "doing, not one panel's view of it."
        ),
        tier=1,
        help_id="jobs.kind",
        topic="jobs",
    ),
    "Key": HelpTooltip(
        text=(
            "What the job is working on -- the identifier the service "
            "registered it under.\n\n"
            "It identifies the job, not the molecule: two runs on one "
            "structure appear as two rows."
        ),
        tier=1,
        help_id="jobs.key",
        topic="jobs",
    ),
    "Status": HelpTooltip(
        text=(
            "The last progress message the service reported, or "
            '"running" if it has not sent one.\n\n'
            "The list is polled a few times a second, so a job that "
            "finishes between polls simply disappears rather than showing "
            "a completed state. This panel lists ACTIVE work only."
        ),
        tier=2,
        help_id="jobs.status",
        topic="jobs",
    ),
    "": HelpTooltip(
        text=(
            "Stops the job in this row.\n\n"
            "Enabled only where the service that started the work supplied "
            "a way to cancel it -- a greyed button means this job cannot be "
            "interrupted, not that it has already stopped. Cancelling asks "
            "the service to stop; work already handed to an external "
            "program may take a moment to end."
        ),
        tier=2,
        help_id="jobs.cancel",
        topic="jobs",
    ),
}
_POLL_INTERVAL_MS = 500

#: WHICH JOB A CANCEL BUTTON MEANS TRAVELS ON THE BUTTON, never in a closure.
#: See `_on_cancel_clicked` for the measurement that forced this.
_JOB_KIND_PROPERTY = "_openchem_job_kind"
_JOB_KEY_PROPERTY = "_openchem_job_key"


class JobsPanel(QWidget):
    """Lists every active job across Conformer/Docking/QuantumChemistry
    services via `JobManager.active_jobs()`, with a Cancel button per row
    wired to `JobManager.cancel()`.

    Polls on a timer rather than listening for a JobManager-published
    event: `JobManager` stays a plain, EventBus-independent registry
    (constructed directly by 3 services and by every service-level test
    without an EventBus dependency) — a background-job list refreshing a
    few times a second is a normal, low-stakes UI pattern, not a
    correctness-sensitive one that needs push notification.
    """

    def __init__(self, job_manager: JobManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._job_manager = job_manager

        self._table = QTableWidget(0, len(_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        # On the header ITEMS, which are QTableWidgetItems rather than
        # widgets; see `docking_panel.py` for why that distinction matters
        # to the coverage walk.
        for column, name in enumerate(_COLUMNS):
            item = self._table.horizontalHeaderItem(column)
            if item is not None:
                apply_help_tooltip(item, _COLUMN_HELP[name])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._table)

        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        jobs = self._job_manager.active_jobs()
        self._table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            self._table.setItem(row, 0, QTableWidgetItem(job.kind))
            self._table.setItem(row, 1, QTableWidgetItem(job.key))
            self._table.setItem(row, 2, QTableWidgetItem(job.message or "running"))

            cancel_button = QPushButton("Cancel", self)
            cancel_button.setEnabled(job.cancel_callback is not None)
            # A BOUND METHOD, never a lambda that captures `self`.
            cancel_button.setProperty(_JOB_KIND_PROPERTY, job.kind)
            cancel_button.setProperty(_JOB_KEY_PROPERTY, job.key)
            cancel_button.clicked.connect(self._on_cancel_clicked)
            self._table.setCellWidget(row, 3, cancel_button)

    def _on_cancel_clicked(self, _checked: bool = False) -> None:
        """Which job travels on the button; `self` never travels in a closure.

        PySide6 holds a connected plain callable STRONGLY and a QObject's
        bound method weakly, so
        `connect(lambda ...: self._on_cancel_clicked(kind, key))` rooted this
        panel for the life of the process -- past refcounting and past the
        cyclic collector, which cannot see through the map the callable is
        kept in. `PropertyPanel`, `PeriodicTableDialog` and
        `ExternalToolsDialog` were each fixed for this; **this panel was
        missed**, and it is the worst place to miss it, because `refresh`
        runs on a 500 ms timer and so connected a fresh rooted lambda twice
        a second for the life of the process.

        MEASURED, before and after, with `_survives_collection`: a panel that
        has rendered ONE ROW survived three cycles of the collector; one that
        never rendered a row did not, because the loop this sits in never
        ran. So the leak was "any panel that ever had a job to show".

        What it cost is in CLAUDE.md: over two test files alone, five leaked
        panels fired **170 refreshes inside a later file's event pump** --
        704 `setItem`/`setCellWidget` calls, every one of them destroying a
        Qt object inside an unrelated test's event dispatch. That is the
        Linux segfault's own traceback.
        """
        button = self.sender()
        if button is None:
            return
        kind = button.property(_JOB_KIND_PROPERTY)
        key = button.property(_JOB_KEY_PROPERTY)
        if kind is None or key is None:
            return
        self._job_manager.cancel(str(kind), str(key))
