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

_COLUMNS = ("Kind", "Key", "Status", "")
_POLL_INTERVAL_MS = 500


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
            cancel_button.clicked.connect(
                lambda _checked=False, kind=job.kind, key=job.key: self._on_cancel_clicked(kind, key)
            )
            self._table.setCellWidget(row, 3, cancel_button)

    def _on_cancel_clicked(self, kind: str, key: str) -> None:
        self._job_manager.cancel(kind, key)
