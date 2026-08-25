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
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
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
from openchem.domain.batch import (
    SOURCE_DESCRIPTOR,
    BatchRequest,
    BatchResultStore,
    BatchTable,
)
from openchem.domain.calculator import RegistryExecution
from openchem.domain.common import CacheState
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.services.batch_service import BatchProgress, BatchService
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.table_export_service import TableExportService
from openchem.ui.widgets.flow_layout import flow_row
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
from openchem.ui.widgets.sortable_item import SORT_ROLE, SortableItem

logger = logging.getLogger("openchem.ui")

#: EIGHT CONTROLS, EIGHT CONCEPTS -- nothing here collapses. The three
#: export buttons stay apart for the reason `Copy Structure As` does: CSV
#: and Markdown make different round-trip promises, and "analyse what was
#: computed" and "screen the project against thresholds" are different
#: questions rather than two renderings of one.
_HELP: dict[str, HelpTooltip] = {
    "filter": HelpTooltip(
        text=(
            "Show only properties whose name matches what you "
            "type.\n\n"
            "It filters the LIST, never the results: a property hidden "
            "here stays ticked and still runs. A category left with no "
            "matching entries is hidden entirely rather than shown empty, "
            "which would read as a category that produced nothing."
        ),
        tier=2,
        help_id="batch.property_filter",
        topic="batch",
    ),
    "run": HelpTooltip(
        text=(
            "Compute every ticked property for every molecule in the "
            "project, and fill the whole table.\n\n"
            "**THIS IS THE BULK PATH AND IT IS DELIBERATE.** Nothing is "
            "computed until you ask: opening this panel runs nothing, and "
            "opening one molecule's details computes that molecule "
            "alone. Use this when you want the wide table itself -- to "
            "sort it, export it, or hand it to the analytics.\n\n"
            "Cost grows with molecules TIMES properties, so it says how "
            "many calculations it is about to start and waits for you to "
            "agree. The run is listed in the Jobs panel and can be "
            "cancelled; results already computed stay."
        ),
        tier=2,
        help_id="batch.run",
        topic="batch",
    ),
    "cancel": HelpTooltip(
        text=(
            "Stop the run that is in progress.\n\n"
            "Results already computed stay in the table; the rest are "
            "left blank, which reads the same as never having been run."
        ),
        tier=1,
        help_id="batch.cancel",
        topic="batch",
    ),
    "select_all": HelpTooltip(
        text=(
            "Tick every property currently shown in the list.\n\n"
            "It respects the filter: type something first and this ticks "
            "only what matches, leaving anything hidden exactly as it "
            "was. Ticking a category heading does the same for that "
            "category alone.\n\n"
            "Cost grows with molecules TIMES properties, so ticking "
            "everything over a large project is a long run -- the run "
            "tells you the size before it starts."
        ),
        tier=2,
        help_id="batch.select_all",
        topic="batch",
    ),
    "clear_selection": HelpTooltip(
        text=(
            "Untick every property.\n\n"
            "Clears the SELECTION only -- results already in the table "
            "stay, and so does anything typed in the filter."
        ),
        tier=1,
        help_id="batch.clear_selection",
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

#: Tier 3 because the CHOICE changes what the number means, not merely how
#: precise it is: the SUMMED Crippen contribution is the molecule's LogP,
#: while the mean of the same per-atom values is a different quantity that
#: is also real. Reading one against a literature value for the other is
#: wrong in a way that looks fine, which is the tier-3 test.
_PER_ATOM_AGGREGATE_HELP = HelpTooltip(
    text=(
        "How a per-atom result becomes one number per molecule.\n\n"
        "There is no universally right answer -- the summed Crippen "
        "contribution IS the molecule's LogP, but the mean of the same "
        "values is also real, and they are different quantities. The "
        "column header records which was taken."
    ),
    tier=3,
    help_id="batch.per_atom_aggregate",
    topic="batch",
)

_FAILED_BRUSH = QBrush(QColor(150, 150, 150))
#: Distinct from the failure grey ON PURPOSE. A per-atom map, a spectrum
#: or a structure set is a real answer that a table is the wrong shape
#: for, and rendering it like a failure tells the reader nothing was
#: computed. `reduce_result` refuses 25 of the real registry's lines
#: outright, so this is the common case rather than an edge one.
_NON_SCALAR_BRUSH = QBrush(QColor(60, 90, 150))
_MISSING = "—"

_UUID_ROLE = Qt.ItemDataRole.UserRole + 2

#: Above this many calculations, filling the table asks first.
#:
#: Not a refusal -- the user decides, and a bulk table is a real
#: deliverable. It is a number small enough that the ordinary case (a few
#: molecules, a handful of properties) is never interrupted, and large
#: enough that the case worth pausing on -- a whole category over a whole
#: project -- always is. Measured against the panel's own registry: 53
#: registry-executable calculators, so ticking everything trips this at
#: four molecules.
_CONFIRM_ABOVE = 200

#: Sentinel on the menu's reset entry, so it cannot collide with a real
#: category name however the registry grows.
_SHOW_ALL = object()

# Moved to `ui/widgets/sortable_item.py` once the per-atom comparison table
# needed the same thing. Aliased rather than renamed at every call site --
# the names are private to this module and the move is not worth the churn.
_SORT_ROLE = SORT_ROLE
_SortableItem = SortableItem


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
        structure_check_service=None,
        settings=None,
    ) -> None:
        super().__init__(parent)
        self._batch_service = batch_service
        self._registry = calculator_registry
        self._export_service = table_export_service
        self._engine = chemistry_engine
        self._project: ProjectModel | None = None
        self._table: BatchTable | None = None
        # The canonical results. The table beside it is a PROJECTION --
        # `reduce_result` refuses 25 of the real registry's lines outright,
        # so a panel reading only the table cannot offer a Details view or
        # an inspector, which is what Properties has offered all along.
        self._store: BatchResultStore | None = None
        self._structure_check = structure_check_service
        self._settings = settings
        self._descriptor_category_cache: dict[str, str] | None = None
        # **WHAT THIS RUN IS FOR**, and the panel is the only thing that
        # knows. A one-molecule run and a whole-project fill go down the
        # identical service path and arrive on the identical event; only
        # the caller can say whether the table that comes back describes
        # the project or a single row. `JobManager` allows one batch at a
        # time project-wide, so one flag is enough.
        self._filling_table = False
        #: uuid to open the detail view for once the run it needed lands.
        self._details_when_ready: str | None = None
        # Re-entry guard for the tree: setting a child's check state emits
        # itemChanged, which is the handler that sets children.
        self._suspend_tree = False
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
        apply_help_tooltip(self._filter, _HELP['filter'])
        layout.addWidget(self._filter)

        self._tree = QTreeWidget(self)
        self._tree.setHeaderLabels(["Property", "Basis"])
        # PROPERTY STRETCHES, BASIS DOES NOT. Qt stretches the LAST section by
        # default, which is exactly backwards here: every readable string is in
        # column 0 -- and indented up to three levels -- while "Basis" holds one
        # short word and is empty on the category rows. Left to the default, the
        # categories elided to three characters ("Ad...", "Cha...", "Elec...")
        # while the empty Basis column took 455 px of a 420 px panel. That is
        # the same unreadable-label symptom the panel rail was built to remove.
        tree_header = self._tree.header()
        tree_header.setStretchLastSection(False)
        tree_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setMinimumHeight(160)
        layout.addWidget(self._tree)

        # A `QHBoxLayout`'s minimum width is the SUM of its children, so each
        # of this panel's three control rows was setting a floor no dock width
        # could satisfy -- 409 px of content in a 280 px panel, with "Virtual
        # Screening..." off the right edge entirely. `flow_row` wraps instead
        # and reports the widest SINGLE control. Same cure as the 3D viewer's
        # toolbar; see `ui/widgets/flow_layout.py`.
        aggregate_row = flow_row(self)
        aggregate_row.layout().addWidget(QLabel("Per-atom values as:"))
        self._aggregate = QComboBox(self)
        self._aggregate.addItems(PER_ATOM_AGGREGATES)
        apply_help_tooltip(self._aggregate, _PER_ATOM_AGGREGATE_HELP)
        aggregate_row.layout().addWidget(self._aggregate)
        layout.addWidget(aggregate_row)

        button_row = flow_row(self)
        self._run_button = QPushButton("Fill table…", self)
        self._run_button.clicked.connect(self._run)
        apply_help_tooltip(self._run_button, _HELP['run'])
        self._cancel_button = QPushButton("Cancel", self)
        self._cancel_button.clicked.connect(self._cancel)
        apply_help_tooltip(self._cancel_button, _HELP['cancel'])
        self._cancel_button.setEnabled(False)
        self._select_all_button = QPushButton("Select all", self)
        self._select_all_button.clicked.connect(self._select_all_visible)
        apply_help_tooltip(self._select_all_button, _HELP['select_all'])
        self._select_none_button = QPushButton("Clear selection", self)
        self._select_none_button.clicked.connect(self._clear_selection)
        apply_help_tooltip(self._select_none_button, _HELP['clear_selection'])
        button_row.layout().addWidget(self._run_button)
        button_row.layout().addWidget(self._cancel_button)
        button_row.layout().addWidget(self._select_all_button)
        button_row.layout().addWidget(self._select_none_button)
        layout.addWidget(button_row)

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
        apply_help_tooltip(self._csv_button, _HELP['export_csv'])
        self._report_button = QPushButton("Export Report…", self)
        self._report_button.clicked.connect(self._export_report)
        apply_help_tooltip(self._report_button, _HELP['export_report'])
        self._columns_button = QPushButton("Columns…", self)
        self._columns_button.clicked.connect(self._show_column_menu)
        apply_help_tooltip(self._columns_button, _HELP['columns'])
        self._details_button = QPushButton("Details…", self)
        self._details_button.clicked.connect(self._open_details)
        apply_help_tooltip(self._details_button, _HELP['details'])
        self._analyse_button = QPushButton("Analyse…", self)
        self._analyse_button.clicked.connect(self._analyse)
        apply_help_tooltip(self._analyse_button, _HELP['analyse'])
        self._screen_button = QPushButton("Virtual Screening…", self)
        self._screen_button.clicked.connect(self._screen)
        apply_help_tooltip(self._screen_button, _HELP['screen'])
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

        event_bus.subscribe(BatchProgress, self._on_progress)
        self._populate_tree()
        self._make_groups_checkable()
        self._refresh_group_states()
        self._tree.itemChanged.connect(self._on_item_changed)
        self._restore_selection()

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

    def _make_groups_checkable(self) -> None:
        """Every non-leaf row gets a check box of its own.

        **THIS IS THE WHOLE OF WHY THERE WAS NO SELECT-ALL-IN-GROUP**:
        `_add_leaf` set `ItemIsUserCheckable` on LEAVES only, so a category
        heading had no check state at all and 91 properties could only be
        ticked one at a time.

        Qt draws the partial state for free once the flag is on; what it
        does NOT do is propagate, so `_on_item_changed` pushes a parent's
        state down and recomputes ancestors on the way back up.
        """
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.childCount():
                # `ItemIsUserCheckable` ALONE, deliberately.
                # `ItemIsAutoTristate` looks like exactly what this wants
                # and does too much: Qt then propagates a parent's tick
                # down to EVERY child itself, hidden ones included, which
                # silently reaches entries the filter is hiding and
                # contradicts the filter's own documented promise.
                # Measured -- with that flag set,
                # `test_ticking_a_category_leaves_its_hidden_children_alone`
                # fails on a child Qt ticked before this handler ran.
                # Both directions are ours instead.
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Unchecked)
                stack.extend(item.child(i) for i in range(item.childCount()))

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Push a group's tick down to its children.

        Guarded against re-entry: setting a child's state emits this again,
        and Qt's own tristate handling then walks back up -- without the
        guard a single click on a category recurses through the subtree
        once per descendant.

        HIDDEN CHILDREN ARE LEFT ALONE, which is not an optimisation. The
        filter's own help text promises it filters the LIST and never the
        results, so a group tick that reached entries the user cannot see
        would contradict a documented contract.
        """
        if self._suspend_tree or column != 0:
            return
        self._suspend_tree = True
        try:
            if item.childCount():
                state = item.checkState(0)
                if state is not Qt.CheckState.PartiallyChecked:
                    self._set_subtree(item, state)
            # Upwards on every change, leaf or group: a group's box is a
            # statement about its children and goes stale the moment one
            # of them moves. Qt would do this half with ItemIsAutoTristate
            # and the downward half wrongly -- see `_make_groups_checkable`.
            for index in range(self._tree.topLevelItemCount()):
                _group_state(self._tree.topLevelItem(index))
        finally:
            self._suspend_tree = False
        self._save_selection()

    def _set_subtree(self, item: QTreeWidgetItem, state) -> None:
        for index in range(item.childCount()):
            child = item.child(index)
            if child.isHidden():
                continue
            if child.childCount():
                child.setCheckState(0, state)
                self._set_subtree(child, state)
            else:
                child.setCheckState(0, state)

    def _select_all_visible(self) -> None:
        """Tick everything the filter is currently showing.

        Not everything that EXISTS -- see `_on_item_changed`. The status
        line says how many, because "select all" over a filtered list is
        otherwise a claim the user cannot check.
        """
        self._suspend_tree = True
        try:
            count = 0
            for item, _payload in self._leaves():
                if item.isHidden():
                    continue
                item.setCheckState(0, Qt.CheckState.Checked)
                count += 1
        finally:
            self._suspend_tree = False
        self._refresh_group_states()
        self._save_selection()
        shown = "shown" if self._filter.text().strip() else "available"
        self._status.setText(f"Ticked {count} {shown} propert{'y' if count == 1 else 'ies'}.")

    def _refresh_group_states(self) -> None:
        """Recompute every group's box from its children.

        Needed after a bulk change, which sets leaves directly and so
        never goes through the propagation above.
        """
        self._suspend_tree = True
        try:
            for index in range(self._tree.topLevelItemCount()):
                _group_state(self._tree.topLevelItem(index))
        finally:
            self._suspend_tree = False

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

    #: Where the ticked property ids live between launches.
    _SELECTION_SETTING = "batch/selected_property_ids"

    def _save_selection(self) -> None:
        """Remember the ticked IDs.

        **IDS, NEVER TREE POSITIONS OR CHECK STATES.** Categories and
        ordering come from the registry and the descriptor provider, so
        both move when a calculator is added -- a saved row index would
        then restore somebody else's property. An id names a definition,
        which is the same principle `help_id` rests on and the same
        failure the tooltip migration hit when an `instance_path` was
        renamed by wrapping a control in a new container.
        """
        if self._settings is None:
            return
        descriptors, calculators = self.selected_ids()
        try:
            self._settings.set(self._SELECTION_SETTING, list(descriptors) + list(calculators))
        except Exception:  # noqa: BLE001 - a preference is never worth a crash
            logger.debug("Could not save the batch selection")

    def _restore_selection(self) -> None:
        """Tick whatever was ticked last time, ignoring anything gone.

        An id that no longer exists is DROPPED rather than reported: a
        calculator removed between launches is not the user's problem, and
        a dialog about it on startup would be.
        """
        if self._settings is None:
            return
        try:
            stored = self._settings.get(self._SELECTION_SETTING, []) or []
        except Exception:  # noqa: BLE001
            return
        wanted = {str(identifier) for identifier in stored}
        if not wanted:
            return
        self._suspend_tree = True
        try:
            for item, (_kind, identifier) in self._leaves():
                if identifier in wanted:
                    item.setCheckState(0, Qt.CheckState.Checked)
        finally:
            self._suspend_tree = False
        self._refresh_group_states()

    def _clear_selection(self) -> None:
        self._suspend_tree = True
        try:
            for item, _payload in self._leaves():
                item.setCheckState(0, Qt.CheckState.Unchecked)
        finally:
            self._suspend_tree = False
        self._refresh_group_states()
        self._save_selection()

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
        """Fill the whole table, after saying what that costs.

        **THE COST IS STATED BEFORE THE WORK, NOT DURING IT.** This is the
        one place in the panel where the user can ask for an unbounded
        amount of computation -- molecules TIMES properties -- and a
        progress bar that appears after the decision is not a decision.
        """
        if self._project is None:
            self._status.setText("Open or create a project first.")
            return
        descriptors, calculators = self.selected_ids()
        if not descriptors and not calculators:
            self._status.setText("Tick at least one property first.")
            return
        molecules = list(self._project.molecules)
        total = len(molecules) * (len(descriptors) + len(calculators))
        if total > _CONFIRM_ABOVE:
            answer = QMessageBox.question(
                self,
                "Fill the whole table?",
                f"This will start about {total:,} calculations "
                f"({len(molecules)} molecules x {len(descriptors) + len(calculators)} "
                "properties).\n\n"
                "It runs in the background and can be cancelled; anything "
                "already computed is kept.",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Ok,
            )
            if answer is not QMessageBox.StandardButton.Ok:
                self._status.setText("Cancelled -- nothing was computed.")
                return
        self._filling_table = True
        request = BatchRequest(
            molecule_uuids=[molecule.uuid for molecule in self._project.molecules],
            descriptor_ids=descriptors,
            calculator_ids=calculators,
            per_atom_aggregate=self._aggregate.currentText(),
            structure_version=self._current_structure_version(),
        )
        self._batch_service.request_batch(request, molecules)

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
        # **THE TABLE IS ADOPTED ONLY WHEN THE RUN WAS A FILL.** A
        # one-molecule run returns a one-row table, and letting that
        # replace the project's would make opening a detail view destroy
        # the table the user had built.
        if event.table is not None and self._filling_table:
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
        if not running:
            self._filling_table = False
            self._open_pending_details()

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
        # AFTER the rebuild: `clear()` drops every hidden flag, so a
        # progress event arriving mid-run would silently un-hide
        # everything the user had put away.
        self._apply_column_visibility()

    # -- exports ----------------------------------------------------------

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

    def _current_structure_version(self) -> int:
        """The checker's counter, or 0 where no checker is wired.

        Zero is what a bare fixture has, and it is a real answer rather
        than a fallback: with nothing tracking structure edits there is no
        version to be stale against. A guard for staleness must MOVE this,
        or it is testing the cache rather than the invalidation -- the trap
        CLAUDE.md records the Atom Inspector's report cache falling into.
        """
        if self._structure_check is None:
            return 0
        try:
            return int(self._structure_check.current_version())
        except Exception:  # noqa: BLE001 - a version we cannot read is 0
            logger.debug("Could not read the structure version for a batch run")
            return 0

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
        self._show_details(uuid)

    def _show_details_for(self, name_item) -> None:
        if name_item is not None:
            self._show_details(name_item.data(_UUID_ROLE))

    def _merge_store(self, incoming: BatchResultStore) -> None:
        """Fold a run's results into what is already held.

        REPLACING would lose everything a previous run computed, which is
        the whole point of retaining them -- and a one-molecule run would
        wipe the other 199.
        """
        if self._store is None:
            self._store = BatchResultStore()
        self._store.results.update(incoming.results)

    def _needs_computing(self, molecule_uuid: str) -> tuple[list[str], list[str]]:
        """The ticked properties this molecule has no CURRENT result for.

        Keyed on the structure version, so an edited molecule's stale
        results do not count as computed -- which is the difference between
        "already done" and "done for a structure that no longer exists".
        """
        descriptors, calculators = self.selected_ids()
        if self._store is None:
            return descriptors, calculators
        have = set(
            self._store.for_molecule(molecule_uuid, self._current_structure_version())
        )
        return (
            [d for d in descriptors if d not in have],
            [c for c in calculators if c not in have],
        )

    def _open_pending_details(self) -> None:
        uuid, self._details_when_ready = self._details_when_ready, None
        if uuid is not None:
            self._present_details(uuid)

    def _show_details(self, molecule_uuid: str | None) -> None:
        """Open one molecule's results, computing them if they are missing.

        **NOTHING IS COMPUTED UNASKED, AND THIS IS THE ASKING.** Opening
        the panel runs nothing; opening a molecule runs THAT MOLECULE's
        ticked properties and no other molecule's. An arbitrary project
        size stops being dangerous because an arbitrary project size is no
        longer computed.

        It reuses `BatchService` rather than calling the registry inline:
        one molecule against every ticked calculator is still real work,
        and the service already has the thread, the progress and the
        cancel. The results land in the same store by the same key, which
        is what makes the two paths impossible to tell apart afterwards.
        """
        if not molecule_uuid or self._project is None:
            return
        molecule = self._project.find_molecule(molecule_uuid)
        if molecule is None:
            return

        descriptors, calculators = self._needs_computing(molecule_uuid)
        if descriptors or calculators:
            if self._batch_service.is_running():
                self._status.setText("A run is already in progress -- try again when it finishes.")
                return
            self._filling_table = False
            self._details_when_ready = molecule_uuid
            self._status.setText(f"Computing {molecule.display_name}...")
            self._batch_service.request_batch(
                BatchRequest(
                    molecule_uuids=[molecule_uuid],
                    descriptor_ids=descriptors,
                    calculator_ids=calculators,
                    per_atom_aggregate=self._aggregate.currentText(),
                    structure_version=self._current_structure_version(),
                ),
                [molecule],
            )
            return
        self._present_details(molecule_uuid)

    def _present_details(self, molecule_uuid: str) -> None:
        """One molecule's results, in the Properties panel's own renderer."""
        if self._project is None:
            return
        molecule = self._project.find_molecule(molecule_uuid)
        if molecule is None:
            return
        from openchem.ui.dialogs.batch_detail_dialog import BatchDetailDialog

        dialog = BatchDetailDialog(
            self._engine,
            molecule,
            self._store if self._store is not None else BatchResultStore(),
            self._current_structure_version(),
            self,
        )
        dialog.exec()

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


#: A group row's label, with its own name kept separately.
#:
#: Stored rather than re-derived by stripping the suffix off the displayed
#: text: a category legitimately called "Shape (3D)" would be mangled by
#: any parser, and a name is not a thing to reconstruct from its own
#: rendering. Same instinct as `full_text` on the eliding caption.
_GROUP_NAME_ROLE = Qt.ItemDataRole.UserRole + 3


def _leaves_under(item: QTreeWidgetItem):
    if not item.childCount():
        yield item
        return
    for index in range(item.childCount()):
        yield from _leaves_under(item.child(index))


def _label_group(item: QTreeWidgetItem) -> None:
    """Show `n / total` ticked beside a group's name.

    Counts EVERY leaf beneath it, hidden ones included -- a group that
    read "2 / 2" while a filtered-out third was unticked would be lying
    about what a run will do, which is the same contract
    `_on_item_changed` keeps when it declines to tick what it cannot show.
    """
    name = item.data(0, _GROUP_NAME_ROLE)
    if name is None:
        name = item.text(0)
        item.setData(0, _GROUP_NAME_ROLE, name)
    leaves = list(_leaves_under(item))
    if not leaves:
        item.setText(0, str(name))
        return
    ticked = sum(1 for leaf in leaves if leaf.checkState(0) is Qt.CheckState.Checked)
    item.setText(0, f"{name}  {ticked} / {len(leaves)}" if ticked else f"{name}  {len(leaves)}")


def _group_state(item: QTreeWidgetItem):
    """Set `item`'s box from its descendants, and return that state.

    Depth-first, because a category's state depends on its children's and
    a top-level group's on the categories'. Hidden leaves are counted:
    they are still ticked or not, and a group that read "all" while a
    hidden entry was unticked would be lying about what will run.
    """
    if not item.childCount():
        return item.checkState(0)
    states = [_group_state(item.child(i)) for i in range(item.childCount())]
    if all(state is Qt.CheckState.Checked for state in states):
        resolved = Qt.CheckState.Checked
    elif all(state is Qt.CheckState.Unchecked for state in states):
        resolved = Qt.CheckState.Unchecked
    else:
        resolved = Qt.CheckState.PartiallyChecked
    item.setCheckState(0, resolved)
    _label_group(item)
    return resolved


def _title(text: str) -> str:
    return text.replace("_", " ").title()
