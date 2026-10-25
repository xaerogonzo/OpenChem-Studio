"""Runs the install self-check once, off the UI thread, and says so only if it found something.

The check itself is `openchem.install_check` (pure). This is the Qt half: one
`QRunnable` on the global pool, its answer delivered to the main thread by a
queued signal and recorded for About to read. It never blocks the window from
appearing, runs once per process, and changes nothing on disk.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from openchem import install_check
from openchem.install_check import InstallCheckResult, Status


class _TaskSignals(QObject):
    finished = Signal(object)


class _CheckTask(QRunnable):
    """`check_installed` never raises, so this only has to carry its answer back."""

    def __init__(self) -> None:
        super().__init__()
        self.signals = _TaskSignals()

    def run(self) -> None:
        self.signals.finished.emit(install_check.check_installed())


class InstallMonitor(QObject):
    """Owns the one check. Parent it to the main window so both end together."""

    changed = Signal(object)  # an InstallCheckResult, on the main thread

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._task: _CheckTask | None = None
        self._started = False

    @property
    def result(self) -> InstallCheckResult:
        return install_check.current()

    def start(self) -> None:
        """Begin the check; a second call does nothing."""
        if self._started:
            return
        self._started = True
        if not getattr(sys, "frozen", False):
            # Nothing was installed, so there is nothing to compare: answer at once.
            install_check.record(InstallCheckResult(Status.NOT_APPLICABLE))
            self.changed.emit(install_check.current())
            return
        # A strong reference: a fire-and-forget QRunnable's Python wrapper can be
        # collected before its worker finishes (see plugins/async_task.py), and
        # the result would then never arrive.
        self._task = _CheckTask()
        self._task.signals.finished.connect(self._on_finished)
        QThreadPool.globalInstance().start(self._task)

    def _on_finished(self, result: InstallCheckResult) -> None:
        install_check.record(result)
        self._task = None
        self.changed.emit(result)


#: How long the status bar shows a finding. Long: it is the only place a person is told.
_FINDING_MS = 60000


def attach(window) -> InstallMonitor:
    """Start the check for `window` and surface a finding in its status bar.

    Silent when the install is verified or not applicable: nobody needs telling
    that nothing is wrong.
    """
    monitor = InstallMonitor(window)

    def on_changed(result: InstallCheckResult) -> None:
        if result.status in (Status.MODIFIED, Status.CHECK_FAILED):
            window.statusBar().showMessage(f"Installation check: {result.summary()} (Help > About has the details)", _FINDING_MS)

    monitor.changed.connect(on_changed)
    monitor.start()
    return monitor
