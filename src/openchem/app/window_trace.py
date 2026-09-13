"""Log every top-level window that shows, and when results land.

Off unless `OPENCHEM_TRACE_WINDOWS` is set. Written to answer one reported
symptom that reading the source could not: selecting a molecule flashed a
handful of small white windows and the Results panel took 10-15 s to fill.
Nothing in `src/` creates a hidden or off-screen top-level on purpose, so
the only honest way to name the widget is to catch it being shown.

A `QEvent.Show` on a widget whose `isWindow()` is true is exactly "a new
window appeared"; the stack says who asked. The event-bus half timestamps
dispatches and results per molecule, so "where do the 15 seconds go" is a
log to read rather than a guess.
"""

from __future__ import annotations

import logging
import os
import time
import traceback

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger("openchem.window_trace")

ENV_VAR = "OPENCHEM_TRACE_WINDOWS"


def _parent_chain(widget: QWidget) -> str:
    names = []
    current = widget.parentWidget()
    while current is not None:
        names.append(f"{type(current).__name__}({current.objectName()!r})")
        current = current.parentWidget()
    return " <- ".join(names) or "(no parent)"


class WindowShowTracer(QObject):
    """Application event filter recording each top-level window shown.

    `shown` is kept as plain data so a test can assert on it without
    parsing log lines.
    """

    def __init__(self, parent: QObject | None = None, with_stack: bool = True) -> None:
        super().__init__(parent)
        self._with_stack = with_stack
        self._started = time.monotonic()
        #: (seconds since start, class name, object name, window title, parent chain)
        self.shown: list[tuple[float, str, str, str, str]] = []

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt's own casing
        if event.type() == QEvent.Type.Show and isinstance(watched, QWidget) and watched.isWindow():
            record = (
                round(time.monotonic() - self._started, 3),
                type(watched).__name__,
                watched.objectName(),
                watched.windowTitle(),
                _parent_chain(watched),
            )
            self.shown.append(record)
            logger.info(
                "WINDOW SHOWN t=%.3f class=%s name=%r title=%r flags=%s geometry=%s parent=%s",
                record[0], record[1], record[2], record[3],
                int(watched.windowFlags().value), watched.geometry().getRect(), record[4],
            )
            if self._with_stack:
                logger.info("WINDOW SHOWN stack:\n%s", "".join(traceback.format_stack(limit=25)))
        return False


def _subscribe_result_timing(event_bus, started: float) -> None:
    """Timestamp every result event, keyed by molecule, into the log."""
    from openchem.events import events as ev

    def stamp(kind: str, uuid_of):
        def handler(event) -> None:
            try:
                uuid = uuid_of(event)
            except Exception:  # noqa: BLE001 - diagnostics must never break the app
                uuid = "?"
            logger.info("RESULT t=%.3f kind=%s molecule=%s", time.monotonic() - started, kind, uuid)
        return handler

    pairs = [
        (ev.MoleculeSelected, "selected", lambda e: e.molecule_uuid),
        (ev.DescriptorComputed, "descriptor", lambda e: f"{e.descriptor.molecule_uuid} {e.descriptor.descriptor_id} {e.descriptor.cache_state.value}"),
        (ev.ReportComputed, "report", lambda e: f"{e.report.molecule_uuid} {e.report.report_id}"),
        (ev.AlertComputed, "alert", lambda e: f"{e.alert.molecule_uuid} {getattr(e.alert, 'alert_id', '')}"),
        (ev.PerAtomDataComputed, "per_atom", lambda e: f"{e.dataset.molecule_uuid} {e.dataset.property_id}"),
        (ev.CalculationFinished, "finished", lambda e: f"{e.molecule_uuid} {e.calculator_id}"),
    ]
    # Handlers are held on the function object: the bus may hold them weakly,
    # and a collected handler would log nothing and look like "no results".
    _subscribe_result_timing.handlers = []  # type: ignore[attr-defined]
    for event_type, kind, uuid_of in pairs:
        handler = stamp(kind, uuid_of)
        _subscribe_result_timing.handlers.append(handler)  # type: ignore[attr-defined]
        event_bus.subscribe(event_type, handler)


def install_if_requested(app: QApplication, event_bus=None) -> WindowShowTracer | None:
    if not os.environ.get(ENV_VAR):
        return None
    tracer = WindowShowTracer(app)
    app.installEventFilter(tracer)
    if event_bus is not None:
        _subscribe_result_timing(event_bus, tracer._started)
    logger.info("Window/result tracing on (%s)", ENV_VAR)
    return tracer
