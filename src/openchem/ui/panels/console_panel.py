from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget


class _QtLogHandler(logging.Handler, QObject):
    """Bridges the `logging` module to a Qt signal.

    Log records from a worker thread (e.g. DescriptorService's QThreadPool
    tasks) are marshaled onto the GUI thread via the signal/slot connection —
    the same trick used by EventBus — instead of touching the QPlainTextEdit
    from a non-GUI thread.
    """

    message_logged = Signal(str)

    def __init__(self) -> None:
        logging.Handler.__init__(self)
        QObject.__init__(self)

    def emit(self, record: logging.LogRecord) -> None:
        self.message_logged.emit(self.format(record))


class ConsolePanel(QWidget):
    """Read-only log sink for the structured loggers set up in app/logging_setup.py."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = QPlainTextEdit(self)
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(5000)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._text)

        self._handler = _QtLogHandler()
        self._handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
        )
        self._handler.message_logged.connect(self._text.appendPlainText)
        logging.getLogger().addHandler(self._handler)
