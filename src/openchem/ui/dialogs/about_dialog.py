"""About, doubling as the diagnostics a bug report needs.

The previous version was a two-line `QMessageBox.about`. The difference
between that and this is a round trip: without a version, a commit and the
resolved external-tool paths, the first reply to any bug report is a request
for exactly those.

The Copy button is the point of the dialog, not decoration -- the text is
laid out to be pasted into an issue as-is.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.build_info import BuildInfo, collect

_BLURB = (
    "<b>OpenChem Studio</b><br>"
    "An open-source, plugin-based chemistry workstation.<br>"
    "GPL-3.0-or-later &mdash; see LICENSE."
)


class AboutDialog(QDialog):
    def __init__(self, settings: object | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About OpenChem Studio")
        self._info: BuildInfo = collect(settings)

        layout = QVBoxLayout(self)

        blurb = QLabel(_BLURB, self)
        blurb.setTextFormat(Qt.TextFormat.RichText)
        blurb.setWordWrap(True)
        layout.addWidget(blurb)

        self._details = QPlainTextEdit(self._info.as_text(), self)
        self._details.setReadOnly(True)
        # Monospace so the aligned columns in as_text() survive display; a
        # proportional font turns them into ragged noise.
        font = self._details.font()
        font.setFamily("Consolas")
        font.setStyleHint(font.StyleHint.Monospace)
        self._details.setFont(font)
        self._details.setMinimumSize(520, 320)
        layout.addWidget(self._details)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        self._copy_button = QPushButton("Copy", self)
        self._copy_button.setToolTip("Copy this report to the clipboard for a bug report")
        self._copy_button.clicked.connect(self._copy)
        buttons.addButton(self._copy_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def info(self) -> BuildInfo:
        return self._info

    def _copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._info.as_text())
            self._copy_button.setText("Copied")
