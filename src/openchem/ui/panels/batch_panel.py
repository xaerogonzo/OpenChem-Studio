"""Pick properties, run them over the project, look at the table.

This is the panel Thread 2 exists for. Everything else in the app answers
questions about the molecule that is currently selected; this one answers
them about all of them at once, and hands the result to the analytics.

WHY THE PICKER IS A TREE AND NOT A LIST. There are 36 descriptors, 5 alert
catalogs and 50 calculators, and a flat list of 91 checkboxes is not a
choice, it is a wall. Grouping by the categories the registry already
declares means the structure comes from the data rather than from a
hardcoded menu -- a new calculator in a new category appears under a new
heading with no change here.

WHY FAILURES ARE SHOWN AS CELLS. A 3D descriptor across a project with no
conformers fails for every molecule, and the difference between "this
calculator produced nothing" and "this calculator was never run" is the
difference between a bug report and a working app. Failed cells carry an
em dash and the reason as a tooltip.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.result_reduction import PER_ATOM_AGGREGATES
from openchem.domain.batch import BatchRequest, BatchTable
from openchem.domain.calculator import RegistryExecution
from openchem.domain.common import CacheState
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.services.batch_service import BatchProgress, BatchService
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.table_export_service import TableExportService

logger = logging.getLogger("openchem.ui")

_FAILED_BRUSH = QBrush(QColor(150, 150, 150))
_MISSING = "—"

_SORT_ROLE = Qt.ItemDataRole.UserRole + 1
_UUID_ROLE = Qt.ItemDataRole.UserRole + 2


class _SortableItem(QTableWidgetItem):
    """A cell that sorts by its VALUE rather than by its printed text.

    `QTableWidget.setSortingEnabled` sorts through `QTableWidgetItem.__lt__`,
    whose default compares `DisplayRole` -- a string. So a molecular-weight
    column sorts "1000" before "200", and a LogP column sorts "-1.03" before
    "-0.5" before "1.31" only by accident of digit order. Storing the float
    under a private role is not enough on its own: without this override,
    Qt never looks at it.

    Mixed types are compared as strings rather than raising. A column can
    legitimately hold floats for most rows and the infinity that marks a
    failed cell, and `float('inf') < 'text'` is a TypeError that would
    propagate out of a header click.
    """

    def __lt__(self, other: QTableWidgetItem) -> bool:
        mine = self.data(_SORT_ROLE)
        theirs = other.data(_SORT_ROLE)
        try:
            return mine < theirs
        except TypeError:
            return str(mine) < str(theirs)


class BatchPanel(QWidget):
    """Property selection, run control, and the results table."""

    def __init__(
        self,
        batch_service: BatchService,
        calculator_registry: CalculatorRegistry,
        table_export_service: TableExportService,
        event_bus: EventBus,
        chemistry_engine,
        parent: QWidget | None = None,
        on_analyse=None,
        on_screen=None,
    ) -> None:
        super().__init__(parent)
        self._batch_service = batch_service
        self._registry = calculator_registry
        self._export_service = table_export_service
        self._engine = chemistry_engine
        self._project: ProjectModel | None = None
        self._table: BatchTable | None = None
        # Callbacks rather than dialogs constructed here: this panel lives
        # in a dock, and the analytics and screening windows are the main
        # window's to own -- same split `PropertyPanel` makes with
        # `on_add_structure`.
        self._on_analyse = on_analyse
        self._on_screen = on_screen

        layout = QVBoxLayout(self)
        self._scope_label = QLabel("No project open.")
        layout.addWidget(self._scope_label)

        self._filter = QLineEdit(self)
        self._filter.setPlaceholderText("Filter properties…")
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)

        self._tree = QTreeWidget(self)
        self._tree.setHeaderLabels(["Property", "Basis"])
        self._tree.setMinimumHeight(160)
        layout.addWidget(self._tree)

        aggregate_row = QHBoxLayout()
        aggregate_row.addWidget(QLabel("Per-atom values as:"))
        self._aggregate = QComboBox(self)
        self._aggregate.addItems(PER_ATOM_AGGREGATES)
        self._aggregate.setToolTip(
            "How a per-atom result becomes one number per molecule. There is no "
            "universally right answer — the summed Crippen contribution IS the "
            "molecule's LogP, but the mean of the same values is also real. The "
            "column header says which was taken."
        )
        aggregate_row.addWidget(self._aggregate)
        aggregate_row.addStretch(1)
        layout.addLayout(aggregate_row)

        button_row = QHBoxLayout()
        self._run_button = QPushButton("Run", self)
        self._run_button.clicked.connect(self._run)
        self._cancel_button = QPushButton("Cancel", self)
        self._cancel_button.clicked.connect(self._cancel)
        self._cancel_button.setEnabled(False)
        self._select_none_button = QPushButton("Clear selection", self)
        self._select_none_button.clicked.connect(self._clear_selection)
        button_row.addWidget(self._run_button)
        button_row.addWidget(self._cancel_button)
        button_row.addWidget(self._select_none_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self._progress = QProgressBar(self)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._results = QTableWidget(self)
        self._results.setSortingEnabled(True)
        self._results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        layout.addWidget(self._results, stretch=1)

        export_row = QHBoxLayout()
        self._csv_button = QPushButton("Export CSV…", self)
        self._csv_button.clicked.connect(self._export_csv)
        self._report_button = QPushButton("Export Report…", self)
        self._report_button.clicked.connect(self._export_report)
        self._analyse_button = QPushButton("Analyse…", self)
        self._analyse_button.clicked.connect(self._analyse)
        self._screen_button = QPushButton("Virtual Screening…", self)
        self._screen_button.clicked.connect(self._screen)
        for button in (self._csv_button, self._report_button, self._analyse_button):
            button.setEnabled(False)
            export_row.addWidget(button)
        export_row.addWidget(self._screen_button)
        export_row.addStretch(1)
        layout.addLayout(export_row)

        event_bus.subscribe(BatchProgress, self._on_progress)
        self._populate_tree()

    # -- project / selection ----------------------------------------------

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        count = len(project.molecules) if project else 0
        self._scope_label.setText(
            f"{count} molecule{'s' if count != 1 else ''} in this project."
            if project
            else "No project open."
        )

    def _populate_tree(self) -> None:
        """Build the picker from the registry and the descriptor provider.

        Descriptors are read from a live `RDKitDescriptorProvider` rather
        than from a hardcoded list so that "what can be batched" is exactly
        "what the app computes", which is the same reason
        `CalculatorRegistry.categories()` exists.
        """
        from openchem.chem.descriptor_providers import RDKitDescriptorProvider

        provider = RDKitDescriptorProvider()
        self._tree.clear()

        descriptors = QTreeWidgetItem(self._tree, ["Descriptors"])
        categories = provider.descriptor_categories()
        by_category: dict[str, list[str]] = {}
        for descriptor_id in provider.descriptor_ids():
            by_category.setdefault(categories.get(descriptor_id, "other"), []).append(descriptor_id)
        for category in sorted(by_category):
            parent = QTreeWidgetItem(descriptors, [_title(category)])
            for descriptor_id in sorted(by_category[category]):
                self._add_leaf(parent, descriptor_id, descriptor_id, "descriptor")

        alerts = QTreeWidgetItem(self._tree, ["Structural alerts"])
        for alert_id, name in sorted(provider.alert_ids().items(), key=lambda pair: pair[1]):
            self._add_leaf(alerts, alert_id, name, "descriptor")

        calculators = QTreeWidgetItem(self._tree, ["Calculators"])
        for category in self._registry.categories():
            definitions = [
                definition
                for definition in self._registry.by_category(category)
                # Docking and ORCA are registered for discovery only and run
                # through their own panels. Offering them here would produce
                # a checkbox that silently does nothing -- an inert control,
                # which this project already decided is worse than a missing
                # one.
                if isinstance(definition.execution, RegistryExecution)
            ]
            if not definitions:
                continue
            parent = QTreeWidgetItem(calculators, [_title(category)])
            for definition in sorted(definitions, key=lambda d: d.display_name):
                self._add_leaf(
                    parent,
                    definition.calculator_id,
                    definition.display_name,
                    "calculator",
                    basis=definition.prediction_basis,
                    tooltip=definition.description,
                )
        descriptors.setExpanded(True)

    def _add_leaf(
        self,
        parent: QTreeWidgetItem,
        identifier: str,
        label: str,
        kind: str,
        basis: str | None = None,
        tooltip: str = "",
    ) -> None:
        item = QTreeWidgetItem(parent, [label, (basis or "").replace("_", " ")])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Unchecked)
        item.setData(0, Qt.ItemDataRole.UserRole, (kind, identifier))
        if tooltip:
            item.setToolTip(0, tooltip)

    def _leaves(self):
        iterator = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while iterator:
            item = iterator.pop()
            payload = item.data(0, Qt.ItemDataRole.UserRole)
            if payload is not None:
                yield item, payload
            iterator.extend(item.child(i) for i in range(item.childCount()))

    def _apply_filter(self, text: str) -> None:
        """Hide non-matching leaves, and any group left with nothing shown.

        A group heading left visible above zero children reads as a
        category that produced no results, which is a different and wrong
        statement.
        """
        needle = text.strip().lower()
        for index in range(self._tree.topLevelItemCount()):
            _filter_item(self._tree.topLevelItem(index), needle)

    def _clear_selection(self) -> None:
        for item, _payload in self._leaves():
            item.setCheckState(0, Qt.CheckState.Unchecked)

    def selected_ids(self) -> tuple[list[str], list[str]]:
        """(descriptor ids, calculator ids) currently ticked."""
        descriptors, calculators = [], []
        for item, (kind, identifier) in self._leaves():
            if item.checkState(0) is not Qt.CheckState.Checked:
                continue
            (descriptors if kind == "descriptor" else calculators).append(identifier)
        return descriptors, calculators

    def check(self, identifier: str, checked: bool = True) -> None:
        """Tick one property by id -- the hook tests and callers use to set
        up a run without simulating clicks through the tree."""
        for item, (_kind, item_id) in self._leaves():
            if item_id == identifier:
                item.setCheckState(
                    0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                )

    # -- running ----------------------------------------------------------

    def _run(self) -> None:
        if self._project is None:
            self._status.setText("Open or create a project first.")
            return
        descriptors, calculators = self.selected_ids()
        request = BatchRequest(
            molecule_uuids=[molecule.uuid for molecule in self._project.molecules],
            descriptor_ids=descriptors,
            calculator_ids=calculators,
            per_atom_aggregate=self._aggregate.currentText(),
        )
        self._batch_service.request_batch(request, list(self._project.molecules))

    def _cancel(self) -> None:
        self._batch_service.cancel()

    def _on_progress(self, event: BatchProgress) -> None:
        running = event.state in (CacheState.QUEUED, CacheState.RUNNING)
        self._run_button.setEnabled(not running)
        self._cancel_button.setEnabled(running)
        self._progress.setVisible(running)
        if event.total:
            self._progress.setMaximum(event.total)
            self._progress.setValue(event.completed)
        self._status.setText(event.error or event.message)
        if event.table is not None:
            self._table = event.table
            self._render_table(event.table)
        has_results = bool(self._table and self._table.row_uuids and self._table.columns)
        for button in (self._csv_button, self._report_button, self._analyse_button):
            button.setEnabled(has_results and not running)

    def table(self) -> BatchTable | None:
        return self._table

    def _render_table(self, table: BatchTable) -> None:
        """Rebuild the grid from the table as it currently stands.

        Sorting is switched OFF around the rebuild and back on afterwards.
        With it left on, Qt re-sorts after every `setItem`, so rows move
        underneath the loop that is still filling them and cells land in
        the wrong row -- a corruption that only appears once a sort has
        been applied, which is exactly when nobody is looking for it.
        """
        self._results.setSortingEnabled(False)
        self._results.clear()
        self._results.setRowCount(len(table.row_uuids))
        self._results.setColumnCount(len(table.columns) + 1)
        self._results.setHorizontalHeaderLabels(
            ["Molecule", *(column.header for column in table.columns)]
        )
        for row, molecule_uuid in enumerate(table.row_uuids):
            name_item = _SortableItem(table.row_labels.get(molecule_uuid, molecule_uuid))
            name_item.setData(_UUID_ROLE, molecule_uuid)
            name_item.setData(_SORT_ROLE, name_item.text())
            self._results.setItem(row, 0, name_item)
            for offset, column in enumerate(table.columns, start=1):
                self._results.setItem(row, offset, _cell_item(table, molecule_uuid, column))
        for index, column in enumerate(table.columns, start=1):
            header = self._results.horizontalHeaderItem(index)
            if header is not None:
                header.setToolTip(_column_tooltip(column))
        self._results.setSortingEnabled(True)

    # -- exports ----------------------------------------------------------

    def _export_csv(self) -> None:
        self._export("CSV (*.csv)", ".csv", self._export_service.export_csv)

    def _export_report(self) -> None:
        self._export("Markdown (*.md)", ".md", self._export_service.export_report)

    def _export(self, file_filter: str, suffix: str, writer) -> None:
        if self._table is None:
            return
        path_str, _ = QFileDialog.getSaveFileName(self, "Export results", filter=file_filter)
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != suffix:
            path = path.with_suffix(suffix)
        try:
            writer(self._table, path)
        except OSError as exc:
            logger.exception("Batch export failed")
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self._status.setText(f"Wrote {path.name}.")

    def _analyse(self) -> None:
        if self._on_analyse is not None and self._table is not None:
            self._on_analyse(self._table)

    def _screen(self) -> None:
        if self._on_screen is not None:
            self._on_screen()


def _cell_item(table: BatchTable, molecule_uuid: str, column) -> QTableWidgetItem:
    cell = table.cell(molecule_uuid, column.column_id)
    if cell is None:
        item = _SortableItem("")
        item.setData(_SORT_ROLE, "")
        return item
    if cell.failed:
        item = _SortableItem(_MISSING)
        item.setForeground(_FAILED_BRUSH)
        item.setToolTip(cell.error or "This calculation failed.")
        # Failed rows sort to one end rather than interleaving with real
        # values at whatever a dash happens to compare as.
        item.setData(_SORT_ROLE, float("inf") if column.numeric else "￿")
        return item
    item = _SortableItem(cell.text)
    item.setData(_SORT_ROLE, cell.value if (column.numeric and cell.value is not None) else cell.text)
    item.setToolTip(_cell_tooltip(column, cell))
    return item


def _cell_tooltip(column, cell) -> str:
    """What produced this number, on the cell itself.

    The point of the whole panel is that tabulating results must not lose
    the labelling that the single-molecule views carry. A column header
    cannot say "computed by ADMET-AI at 14:02 with these parameters" for
    200 different runs; a cell can.
    """
    lines = [column.header]
    if column.prediction_basis:
        lines.append(f"Basis: {column.prediction_basis.replace('_', ' ')}")
    provenance = cell.provenance
    if provenance is not None:
        lines.append(f"Method: {provenance.created_by} / {provenance.method}")
        if provenance.parameters:
            lines.append(
                "Parameters: "
                + ", ".join(f"{key} = {value}" for key, value in sorted(provenance.parameters.items()))
            )
    if cell.value is not None:
        lines.append(f"Value: {cell.value!r}")
    return "\n".join(lines)


def _column_tooltip(column) -> str:
    lines = [column.header, f"Source: {column.source} / {column.source_id}"]
    if column.prediction_basis:
        lines.append(f"Basis: {column.prediction_basis.replace('_', ' ')}")
    if not column.numeric:
        lines.append("Text column — not offered to the analytics.")
    return "\n".join(lines)


def _filter_item(item: QTreeWidgetItem, needle: str) -> bool:
    """Show `item` if it or any descendant matches. Returns whether shown."""
    if item.childCount() == 0:
        visible = not needle or needle in item.text(0).lower()
        item.setHidden(not visible)
        return visible
    any_visible = False
    for index in range(item.childCount()):
        any_visible = _filter_item(item.child(index), needle) or any_visible
    item.setHidden(not any_visible)
    if needle and any_visible:
        item.setExpanded(True)
    return any_visible


def _title(text: str) -> str:
    return text.replace("_", " ").title()
