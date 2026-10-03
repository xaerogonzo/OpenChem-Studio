"""Copy or save a panel's TABLE as CSV, wherever that table is being read.

**THE TABLE VERSION OF `picture_export`.** The Quantum Chemistry, Docking,
Interactions and Alignment panels each show a table of results the reader could
look at and not take away. Rather than a button in every cramped dock, a
right-click on the table offers **Copy table as CSV** and **Export CSV...**, the
way a chart offers its picture.

**IT EXPORTS WHAT THE TABLE SHOWS.** A cell's displayed text, in the order and
with the columns the user sees (hidden columns and rows are left out). That is
the honest scope of a generic exporter: a panel that wants full-precision values
beside their rounded display is `BatchPanel`, which writes them from the data
through `TableExportService.export_csv`.

**A BOUND METHOD ON A HELPER THE TABLE OWNS, NEVER A CLOSURE CAPTURING `self`.**
A plain callable connected to a Qt signal is held strongly, so a closure over a
panel would pin it from a child widget -- the leak class this project ties to its
disposal crashes. The helper is parented to the table, so it goes with it.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QFileDialog, QMenu, QMessageBox, QTableWidget, QToolTip, QWidget

from openchem.services.table_export_service import rows_to_csv_text, write_rows_csv
from openchem.ui.picture_export import file_stem

logger = logging.getLogger("openchem.ui")


def table_rows(table: QTableWidget) -> tuple[list[str], list[list[str]]]:
    """`(headers, rows)` of what the table shows: visible columns and rows only,
    in visual order, each cell as its displayed text. A cell holding a widget
    rather than an item reads as empty -- there is no text to take from it."""
    header = table.horizontalHeader()
    columns = [
        header.logicalIndex(visual)
        for visual in range(table.columnCount())
        if not table.isColumnHidden(header.logicalIndex(visual))
    ]
    headers = []
    for column in columns:
        item = table.horizontalHeaderItem(column)
        headers.append(item.text() if item is not None else str(column + 1))
    rows = []
    for row in range(table.rowCount()):
        if table.isRowHidden(row):
            continue
        cells = []
        for column in columns:
            item = table.item(row, column)
            cells.append(item.text() if item is not None else "")
        rows.append(cells)
    return headers, rows


def copy_table_csv(table: QTableWidget) -> str:
    """Put the table on the clipboard as CSV text. Returns a status line."""
    headers, rows = table_rows(table)
    if not rows:
        return "There is nothing in the table to copy."
    clipboard = QGuiApplication.clipboard()
    if clipboard is None:  # pragma: no cover - defensive
        return "No clipboard is available."
    clipboard.setText(rows_to_csv_text(headers, rows))
    return f"Copied {len(rows)} row(s) as CSV."


def export_table_csv(table: QTableWidget, parent: QWidget | None = None, stem: str = "table") -> str:
    """Ask where to put the table and write it. Returns a status line ('' if cancelled)."""
    headers, rows = table_rows(table)
    if not rows:
        return "There is nothing in the table to export."
    path, _chosen = QFileDialog.getSaveFileName(
        parent, "Export table", f"{file_stem(stem)}.csv", "CSV (*.csv);;All files (*)"
    )
    if not path:
        return ""
    try:
        write_rows_csv(Path(path), headers, rows)
    except OSError as exc:
        QMessageBox.warning(parent, "Export table", str(exc))
        return f"Could not export: {exc}"
    return f"Exported {len(rows)} row(s) to {Path(path).name}."


class _TableExportMenu(QObject):
    """Owns one table's right-click menu. Parented to the table."""

    def __init__(self, table: QTableWidget, stem: str) -> None:
        super().__init__(table)
        self._stem = stem

    def build_menu(self) -> QMenu:
        table = self.parent()
        menu = QMenu(table)
        menu.addAction("Copy table as CSV", self._copy)
        menu.addAction("Export CSV...", self._export)
        return menu

    def show_menu(self, position) -> None:
        table = self.parent()
        self.build_menu().exec(table.viewport().mapToGlobal(position))

    def _say(self, message: str) -> None:
        # A copy that says nothing reads the same as one that failed.
        if message:
            logger.info("%s", message)
            QToolTip.showText(QCursor.pos(), message, self.parent())

    def _copy(self) -> None:
        self._say(copy_table_csv(self.parent()))

    def _export(self) -> None:
        self._say(export_table_csv(self.parent(), self.parent().window(), self._stem))


def install_table_export(table: QTableWidget, stem: str) -> _TableExportMenu:
    """Give `table` a right-click **Copy table as CSV** / **Export CSV...**.
    Returns the helper (a child of the table, so nothing needs to hold it)."""
    helper = _TableExportMenu(table, stem)
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    table.customContextMenuRequested.connect(helper.show_menu)
    return helper
