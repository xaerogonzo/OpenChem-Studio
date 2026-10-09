"""The molecules x properties table, and the controls that read it.

**EXTRACTED FROM `BatchPanel` SO THE TABLE HAS ONE IMPLEMENTATION AND MORE
THAN ONE HOME.** The batch panel owned both halves -- what to run, and the
table that came back -- and the table is the half that must also live in
Results, once running over several molecules is something Properties does.
Two copies of a 350-line table with column menus, exports and sort-safe
rendering is how a cell-for-cell parity claim stops being true, so this is a
MOVE: the methods below are the batch panel's own, unchanged but for how
"open this molecule's details" leaves (a signal, because computing what is
missing needs the panel's selection and its service).

It owns the grid, the progress line, the status line and the export row. It
knows nothing about what is ticked: the host feeds it `BatchProgress` events
through `apply_progress`, and says whether a table that arrives is one to
ADOPT (a fill) or a one-molecule detail run that must not replace it.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.batch import (
    SOURCE_DESCRIPTOR,
    BatchResultStore,
    BatchTable,
)
from openchem.domain.common import CacheState
from openchem.services.batch_service import BatchProgress
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.table_export_service import TableExportService
from openchem.ui.widgets.flow_layout import flow_row
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
from openchem.ui.widgets.sortable_item import SORT_ROLE, SortableItem

logger = logging.getLogger("openchem.ui")

#: The help contracts of the controls this widget draws. They keep their
#: `batch.*` ids and topic: the concept did not change when the code moved.
TABLE_HELP: dict[str, HelpTooltip] = {
    "cancel_run": HelpTooltip(
        text=(
            "Stop the project run that is in progress.\n\n"
            "Results already computed stay in the table; the rest are left "
            "blank, which reads the same as never having been run. The run is "
            "also listed in the Jobs panel."
        ),
        tier=1,
        help_id="results.cancel_project_run",
        topic="batch",
    ),
    "export_csv": HelpTooltip(
        text=(
            "Write the results table to a CSV file.\n\n"
            "One row per molecule and one column per computed property, "
            "for a spreadsheet or a script. A value that could not be "
            "reduced to a number is written as text rather than dropped."
        ),
        tier=2,
        help_id="batch.export_csv",
        topic="batch",
    ),
    "export_report": HelpTooltip(
        text=(
            "Write the results as a Markdown report.\n\n"
            "The same table as the CSV plus the provenance a bare CSV "
            "cannot carry -- which calculator produced each column and on "
            "what basis. For reading rather than for re-import."
        ),
        tier=2,
        help_id="batch.export_report",
        topic="batch",
    ),
    "columns": HelpTooltip(
        text=(
            "Show or hide whole groups of columns.\n\n"
            "One calculator can contribute twenty columns, so a filled "
            "table is wide by nature. Hiding a category affects the VIEW "
            "only -- nothing is recomputed, no value is lost, and both "
            "exports still write every column.\n\n"
            "Right-click the header for the same menu."
        ),
        tier=2,
        help_id="batch.column_groups",
        topic="batch",
    ),
    "details": HelpTooltip(
        text=(
            "Show everything computed for the selected molecule, the way "
            "the Properties panel shows it.\n\n"
            "The same grouped facts, units, basis badges and limitations "
            "-- a table cell keeps one number per calculator and a "
            "calculator that reports twenty is twenty columns with "
            "nothing tying them together. Results with their own view, "
            "like a per-atom map or a spectrum, are offered there rather "
            "than flattened.\n\n"
            "Double-clicking a row does the same thing."
        ),
        tier=2,
        help_id="batch.molecule_details",
        topic="batch",
    ),
    "analyse": HelpTooltip(
        text=(
            "Open the analysis view on the table that has been "
            "computed.\n\n"
            "Plots, correlations and per-atom comparison across the "
            "molecules already in the table. It analyses what is there "
            "and starts no calculation, so a property nobody ran is "
            "absent rather than empty."
        ),
        tier=2,
        help_id="batch.analyse",
        topic="batch",
    ),
    "screen": HelpTooltip(
        text=(
            "Filter the project against property thresholds.\n\n"
            "A different question from the table: rather than reporting "
            "values it keeps the molecules satisfying every rule you set. "
            "The thresholds are yours -- nothing here is a druglikeness "
            "or regulatory verdict."
        ),
        tier=2,
        help_id="batch.virtual_screening",
        topic="batch",
    ),
}

# Moved to `ui/widgets/sortable_item.py` once the per-atom comparison table
# needed the same thing; aliased because the names are private to this module.
#: The role a cell's sort key is read from (see `sortable_item`).
_SORT_ROLE = SORT_ROLE
_SortableItem = SortableItem

#: Grey for a cell whose calculation failed, so a gap reads as a gap.
_FAILED_BRUSH = QBrush(QColor(150, 150, 150))

#: Distinct from the failure grey ON PURPOSE. A per-atom map, a spectrum
#: or a structure set is a real answer that a table is the wrong shape
#: for, and rendering it like a failure tells the reader nothing was
#: computed. `reduce_result` refuses 25 of the real registry's lines
#: outright, so this is the common case rather than an edge one.
_NON_SCALAR_BRUSH = QBrush(QColor(60, 90, 150))

#: What a failed cell shows in place of a value.
_MISSING = "—"

#: Where a row's first cell keeps the molecule uuid, so a sorted row still
#: resolves back to its molecule.
_UUID_ROLE = Qt.ItemDataRole.UserRole + 2

#: How many rows Qt may measure when sizing a results column to its
#: contents. Qt's own default is 1000, which makes column sizing grow with
#: the project for no gain: a cell here is a formatted number or a short
#: label, so twenty of them already establish the width, and the HEADER --
#: the thing that was being clipped -- is measured regardless of this.
#: Measured at 181 molecules x 63 columns: 32.8 ms unbounded, 3.7 ms here.
_WIDTH_SAMPLE_ROWS = 20

#: Sentinel on the menu's reset entry, so it cannot collide with a real
#: category name however the registry grows.
_SHOW_ALL = object()


def _title(text: str) -> str:
    return text.replace("_", " ").title()


class ProjectTableView(QWidget):
    """The results grid, its progress and status lines, and its export row."""

    #: A molecule's row was opened (double-click, or Details with a row chosen).
    #: Carries its uuid; the host decides whether anything must be computed first.
    details_requested = Signal(str)
    #: The Cancel button was pressed while a run was going (only when `show_cancel`).
    cancel_requested = Signal()

    def __init__(
        self,
        calculator_registry: CalculatorRegistry,
        table_export_service: TableExportService,
        parent: QWidget | None = None,
        on_analyse=None,
        on_screen=None,
        show_cancel: bool = False,
    ) -> None:
        super().__init__(parent)
        #: Whether this view draws its own Cancel. The Batch panel has one among its
        #: run controls, so it does not; the Results page has no other.
        self._show_cancel = show_cancel
        self._registry = calculator_registry
        self._export_service = table_export_service
        self._on_analyse = on_analyse
        self._on_screen = on_screen
        self._table: BatchTable | None = None
        # The canonical results. The table beside it is a PROJECTION --
        # `reduce_result` refuses 25 of the real registry's lines outright,
        # so a view reading only the table cannot offer a Details view or an
        # inspector, which Properties has offered all along.
        self._store: BatchResultStore | None = None
        self._descriptor_category_cache: dict[str, str] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._build(layout)

    def _build(self, layout: QVBoxLayout) -> None:
        """What came back: progress, status, the results table and the
        export row.
        """
        self._progress = QProgressBar(self)
        self._progress.setVisible(False)
        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.addWidget(self._progress, 1)
        self._cancel_button = QPushButton("Cancel run", self)
        self._cancel_button.setVisible(False)
        apply_help_tooltip(self._cancel_button, TABLE_HELP["cancel_run"])
        self._cancel_button.clicked.connect(self.cancel_requested)
        progress_row.addWidget(self._cancel_button)
        layout.addLayout(progress_row)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._results = QTableWidget(self)
        self._results.setSortingEnabled(True)
        self._results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._results.itemDoubleClicked.connect(self._on_row_activated)
        header = self._results.horizontalHeader()
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_column_menu)
        #: Category -> shown. Only categories the user has HIDDEN are
        #: recorded, so a category that appears in a later run starts
        #: visible rather than inheriting a decision about a different
        #: table.
        self._hidden_categories: set[str] = set()
        layout.addWidget(self._results, stretch=1)

        export_row = flow_row(self)
        self._csv_button = QPushButton("Export CSV…", self)
        self._csv_button.clicked.connect(self._export_csv)
        apply_help_tooltip(self._csv_button, TABLE_HELP["export_csv"])
        self._report_button = QPushButton("Export Report…", self)
        self._report_button.clicked.connect(self._export_report)
        apply_help_tooltip(self._report_button, TABLE_HELP["export_report"])
        self._columns_button = QPushButton("Columns…", self)
        self._columns_button.clicked.connect(self._show_column_menu)
        apply_help_tooltip(self._columns_button, TABLE_HELP["columns"])
        self._details_button = QPushButton("Details…", self)
        self._details_button.clicked.connect(self._open_details)
        apply_help_tooltip(self._details_button, TABLE_HELP["details"])
        self._analyse_button = QPushButton("Analyse…", self)
        self._analyse_button.clicked.connect(self._analyse)
        apply_help_tooltip(self._analyse_button, TABLE_HELP["analyse"])
        self._screen_button = QPushButton("Virtual Screening…", self)
        self._screen_button.clicked.connect(self._screen)
        apply_help_tooltip(self._screen_button, TABLE_HELP["screen"])
        for button in (
            self._columns_button,
            self._details_button,
            self._csv_button,
            self._report_button,
            self._analyse_button,
        ):
            button.setEnabled(False)
            export_row.layout().addWidget(button)
        export_row.layout().addWidget(self._screen_button)
        layout.addWidget(export_row)

    def apply_progress(self, event: BatchProgress, adopt: bool) -> bool:
        """Show one step of a run; return whether the run is still going.

        **THE TABLE IS ADOPTED ONLY WHEN THE RUN WAS A FILL (`adopt`).** A
        one-molecule run returns a one-row table, and letting that replace
        the project's would make opening a detail view destroy the table the
        user had built.
        """
        running = event.state in (CacheState.QUEUED, CacheState.RUNNING)
        self._progress.setVisible(running)
        self._cancel_button.setVisible(running and self._show_cancel)
        if event.total:
            self._progress.setMaximum(event.total)
            self._progress.setValue(event.completed)
        self._status.setText(event.error or event.message)
        if event.table is not None and adopt:
            self._table = event.table
            self._render_table(event.table)
        if event.store is not None:
            self._merge_store(event.store)
        has_results = bool(self._table and self._table.row_uuids and self._table.columns)
        for button in (self._csv_button, self._report_button, self._analyse_button):
            button.setEnabled(has_results and not running)
        # Details is enabled by the SELECTION rather than by the table: a
        # molecule with nothing computed is exactly the case the lazy path
        # exists for, and greying the button there would make it
        # unreachable.
        self._details_button.setEnabled(not running)
        self._columns_button.setEnabled(has_results and not running)
        return running

    def set_status(self, text: str) -> None:
        self._status.setText(text)

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
        # A HEADER OVERFLOWS RATHER THAN ELIDING, so a column left at Qt's
        # default section width prints its title with BOTH ENDS CUT --
        # measured in the running app at the dock's 420 px default,
        # "Substance classification" rendering as `ostance classificat`.
        # Centre alignment is why it loses both ends rather than one.
        #
        # `resizeColumnsToContents()` ONCE, rather than the
        # `ResizeToContents` MODE that reads as the tidier fix, for two
        # reasons. The mode makes every section non-draggable, and this
        # table's columns are `Interactive` on purpose. And the mode is not
        # free -- it defers the same measurement to paint time, so a probe
        # timing the `setSectionResizeMode` call reports 0.0 ms and has
        # measured nothing. Timed here instead: 32.8 ms one-shot at
        # 181 molecules x 63 columns, the largest table this project's own
        # corpus produces, against a batch run measured in seconds.
        #
        # The precision bound is what keeps that from growing with the
        # project: Qt considers up to 1000 rows per column by default, and
        # 20 formatted numbers already establish a column's width. Same
        # 181x63 table, 32.8 ms -> 3.7 ms.
        self._results.horizontalHeader().setResizeContentsPrecision(_WIDTH_SAMPLE_ROWS)
        self._results.resizeColumnsToContents()
        self._cap_column_widths()
        # AFTER the rebuild: `clear()` drops every hidden flag, so a
        # progress event arriving mid-run would silently un-hide
        # everything the user had put away.
        self._apply_column_visibility()

    def _cap_column_widths(self) -> None:
        """No column may be wider than the viewport it is shown in.

        **SIZING TO CONTENTS ALONE PUTS A HEADER OFF SCREEN**, which is the
        opposite of the clip it was added to fix and was found by driving
        the app once a calculator started returning a long text cell.
        A header is CENTRED in its section, so a column sized to a
        200-character limitation line centres its title half a column in --
        measured, 710 px against a 416 px viewport, with "Lewis Adduct"
        landing just past the edge and the column reading as though it had
        no header at all.

        Capped at the viewport, never below the header's own width: the
        cell text then elides, which is what a table does with long text,
        while the title stays reachable by scrolling to the column. The
        lower bound is what keeps this from undoing
        `resizeColumnsToContents` -- a narrow viewport must not squeeze a
        header back into the clip.
        """
        header = self._results.horizontalHeader()
        limit = self._results.viewport().width()
        if limit <= 0:
            return
        metrics = header.fontMetrics()
        for index in range(self._results.columnCount()):
            item = self._results.horizontalHeaderItem(index)
            floor = metrics.horizontalAdvance(item.text()) if item is not None else 0
            if header.sectionSize(index) > max(limit, floor):
                self._results.setColumnWidth(index, max(limit, floor))

    def _column_category(self, column) -> str:
        """Which picker category a column belongs under.

        Asked of the SAME registry and provider the picker is built from,
        so a new calculator groups itself with no change here -- the
        reason the picker is a tree rather than a hardcoded menu.
        """
        if column.source == SOURCE_DESCRIPTOR:
            return _title(self._descriptor_categories().get(column.source_id, "other"))
        definition = self._registry.get(column.source_id)
        return _title(definition.category if definition is not None else "other")

    def _descriptor_categories(self) -> dict[str, str]:
        if self._descriptor_category_cache is None:
            from openchem.chem.descriptor_providers import RDKitDescriptorProvider

            self._descriptor_category_cache = RDKitDescriptorProvider().descriptor_categories()
        return self._descriptor_category_cache

    def _show_column_menu(self, position=None) -> None:
        """Tick the column groups to show. THE VIEW ONLY.

        Nothing is recomputed and no value is lost -- both exports go on
        writing every column, because a hidden column is a thing the user
        did not want to LOOK at rather than a thing they did not want.
        """
        if self._table is None or not self._table.columns:
            return
        categories = []
        for column in self._table.columns:
            category = self._column_category(column)
            if category not in categories:
                categories.append(category)

        menu = QMenu(self)
        for category in categories:
            action = menu.addAction(category)
            action.setCheckable(True)
            action.setChecked(category not in self._hidden_categories)
            action.setData(category)
        menu.addSeparator()
        show_all = menu.addAction("Show all")
        show_all.setData(_SHOW_ALL)

        origin = (
            self._results.horizontalHeader().mapToGlobal(position)
            if position is not None and not isinstance(position, bool)
            else self._columns_button.mapToGlobal(self._columns_button.rect().bottomLeft())
        )
        chosen = menu.exec(origin)
        if chosen is None:
            return
        if chosen.data() == _SHOW_ALL:
            self._hidden_categories.clear()
        elif chosen.isChecked():
            self._hidden_categories.discard(chosen.data())
        else:
            self._hidden_categories.add(chosen.data())
        self._apply_column_visibility()

    def _apply_column_visibility(self) -> None:
        if self._table is None:
            return
        for offset, column in enumerate(self._table.columns, start=1):
            hidden = self._column_category(column) in self._hidden_categories
            self._results.setColumnHidden(offset, hidden)
        shown = sum(
            1
            for offset in range(1, self._results.columnCount())
            if not self._results.isColumnHidden(offset)
        )
        if self._hidden_categories:
            self._status.setText(
                f"Showing {shown} of {len(self._table.columns)} columns "
                f"({len(self._hidden_categories)} group(s) hidden)."
            )

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

    def _selected_molecule_uuid(self) -> str | None:
        items = self._results.selectedItems()
        if not items:
            return None
        item = self._results.item(items[0].row(), 0)
        return None if item is None else item.data(_UUID_ROLE)

    def _on_row_activated(self, item) -> None:
        self._show_details_for(self._results.item(item.row(), 0))

    def _open_details(self) -> None:
        uuid = self._selected_molecule_uuid()
        if uuid is None:
            self._status.setText("Select a molecule's row first.")
            return
        self.details_requested.emit(uuid)

    def _show_details_for(self, name_item) -> None:
        if name_item is not None:
            self.details_requested.emit(name_item.data(_UUID_ROLE))

    def _merge_store(self, incoming: BatchResultStore) -> None:
        """Fold a run's results into what is already held.

        REPLACING would lose everything a previous run computed, which is
        the whole point of retaining them -- and a one-molecule run would
        wipe the other 199.
        """
        if self._store is None:
            self._store = BatchResultStore()
        self._store.results.update(incoming.results)

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
    if cell.non_scalar:
        # **A REAL RESULT, NOT A GAP.** This used to render as the same em
        # dash a failure does, which says nothing was computed -- the
        # opposite of what happened. The text names what it is; the style
        # and the tooltip say the real thing is one double-click away.
        item = _SortableItem(cell.text)
        item.setForeground(_NON_SCALAR_BRUSH)
        font = item.font()
        font.setItalic(True)
        item.setFont(font)
        item.setToolTip(
            _cell_tooltip(column, cell)
            + "\n\nThis result has no single number. "
            "Double-click the row to open it."
        )
        item.setData(_SORT_ROLE, cell.text)
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
