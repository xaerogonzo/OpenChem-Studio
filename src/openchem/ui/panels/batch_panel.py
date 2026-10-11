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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.result_reduction import PER_ATOM_AGGREGATES
from openchem.domain.batch import (
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
from openchem.ui.dialogs.calculator_settings_dialog import CalculatorSettingsDialog
from openchem.ui.widgets.collapsible_section import CollapsibleSection
from openchem.ui.widgets.flow_layout import flow_row
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
from openchem.ui.widgets.project_table import (  # noqa: F401 - `_cell_item` is re-exported for callers that read it here
    TABLE_HELP,
    ProjectTableView,
    _cell_item,
    _title,
)

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
            "Compute every ticked property for every ticked molecule, and "
            "fill the table.\n\n"
            "Everything starts ticked, so this covers the whole project "
            "until you narrow it under Molecules above.\n\n"
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
    # THE REVERSE OF THE FILTER'S PROMISE, IN AS MANY WORDS. `filter` above
    # declares that it narrows the LIST and never the results, and a reader
    # who has absorbed that will carry it straight across to the control
    # directly below it unless this one says the opposite outright.
    "molecule_scope": HelpTooltip(
        text=(
            "Choose which molecules Fill table computes.\n\n"
            "**THIS CHANGES WHAT IS COMPUTED**, unlike the property filter "
            "above it: an unticked molecule is not run and gets no row. "
            "Everything starts ticked, so a project you never narrow "
            "behaves exactly as it did before this control existed.\n\n"
            "Not remembered between launches. A molecule is identified by "
            "an id belonging to one project file, so a choice restored "
            "against a different project would name nothing -- and a panel "
            "that quietly refused to run, or quietly ran everything, is "
            "worse than starting from all.\n\n"
            "It scopes the bulk run only. Opening one molecule's details "
            "still computes that molecule whether or not it is ticked."
        ),
        tier=2,
        help_id="batch.molecule_scope",
        topic="batch",
    ),
    # NOT the same text as `select_all`/`clear_selection`, deliberately.
    # Byte-identical text under two ids is one concept wearing two, which
    # `test_one_concept_is_not_split_across_many_help_ids` refuses -- and
    # these genuinely differ, since the property pair respects the filter
    # and this pair has no filter to respect.
    "molecules_all": HelpTooltip(
        text=(
            "Tick every molecule in the project, which is where a project "
            "starts."
        ),
        tier=1,
        help_id="batch.molecule_scope_select_all",
        topic="batch",
    ),
    "molecules_none": HelpTooltip(
        text=(
            "Untick every molecule.\n\n"
            "Fill table refuses to run with none ticked rather than "
            "quietly falling back to the whole project, so this is a step "
            "towards choosing a few, not a way to run nothing."
        ),
        tier=1,
        help_id="batch.molecule_scope_clear",
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


# The table half moved to `ui/widgets/project_table.py`; its help contracts keep
# their `batch.*` ids and are folded back in here so `_HELP` is still the one
# place this panel's tooltips can be looked up.
_HELP.update(TABLE_HELP)


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
        """Built in three steps under one layout.

        Split from a single 167-line constructor. The layout is created
        HERE and passed, because `layout` is read by every step -- it spans
        112 of the original 167 lines, which makes this the constructor
        with the widest local live range of the four and the one a naive
        cut would break. Passing it is still a move: same object, same
        order.

        The two building steps are the panel's own halves -- what to run
        above, what came back below -- rather than arbitrary chunks. The
        state fields stay inline: a helper for them would take EIGHT
        parameters, which is a parameter-shuffling exercise rather than a
        clarification.
        """
        super().__init__(parent)
        self._batch_service = batch_service
        self._registry = calculator_registry
        self._engine = chemistry_engine
        self._project: ProjectModel | None = None
        #: calculator_id -> what its settings dialog produced. ONLY the
        #: calculators somebody configured; an absent one runs on the
        #: registry's own defaults, which `batch_service` builds. See
        #: `calculator_parameters`.
        self._calculator_parameters: dict[str, dict] = {}
        self._structure_check = structure_check_service
        self._settings = settings
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
        # `on_add_structure`. They go to the table view, which owns the buttons.
        self._view = ProjectTableView(
            calculator_registry,
            table_export_service,
            self,
            on_analyse=on_analyse,
            on_screen=on_screen,
        )
        self._view.details_requested.connect(self._show_details)

        layout = QVBoxLayout(self)
        self._build_selection(layout)
        layout.addWidget(self._view, stretch=1)
        self._finalise(event_bus)

    # -- the table half lives in `ProjectTableView` ---------------------------
    #
    # Everything below is a window onto it, kept under the names this panel has
    # always had so its callers (the drive harness, the tests, the details
    # path) read the same attributes and the move changed no behaviour.

    @property
    def _results(self):
        return self._view._results

    @property
    def _status(self):
        return self._view._status

    @property
    def _progress(self):
        return self._view._progress

    @property
    def _hidden_categories(self) -> set[str]:
        return self._view._hidden_categories

    @property
    def _table(self) -> BatchTable | None:
        return self._view._table

    @property
    def _store(self) -> BatchResultStore | None:
        return self._view._store

    @property
    def _csv_button(self):
        return self._view._csv_button

    @property
    def _report_button(self):
        return self._view._report_button

    @property
    def _columns_button(self):
        return self._view._columns_button

    @property
    def _details_button(self):
        return self._view._details_button

    @property
    def _analyse_button(self):
        return self._view._analyse_button

    @property
    def _screen_button(self):
        return self._view._screen_button

    def table(self) -> BatchTable | None:
        return self._view.table()

    def _render_table(self, table: BatchTable) -> None:
        self._view._render_table(table)

    def _column_category(self, column) -> str:
        return self._view._column_category(column)

    def _apply_column_visibility(self) -> None:
        self._view._apply_column_visibility()

    def _selected_molecule_uuid(self) -> str | None:
        return self._view._selected_molecule_uuid()

    def _merge_store(self, incoming: BatchResultStore) -> None:
        self._view._merge_store(incoming)

    def _on_progress(self, event: BatchProgress) -> None:
        running = event.state in (CacheState.QUEUED, CacheState.RUNNING)
        self._run_button.setEnabled(not running)
        self._cancel_button.setEnabled(running)
        self._view.apply_progress(event, adopt=self._filling_table)
        if not running:
            self._filling_table = False
            self._open_pending_details()

    def _build_selection(self, layout: QVBoxLayout) -> None:
        """What to run: the scope line, the filter, the property tree and
        the two control rows above the results.
        """
        self._scope_label = QLabel("No project open.")
        layout.addWidget(self._scope_label)

        # COLLAPSED BY DEFAULT, AND THE ALTERNATIVES WERE PRICED RATHER
        # THAN DISMISSED. A bare list here costs ~165 px of fixed height
        # taken from the only `stretch=1` widget in the panel -- on a
        # 700 px dock the results table drops from roughly 380 to 215, a
        # 43% cut to the thing this panel exists to produce, paid
        # permanently by every user including those who never narrow the
        # scope. That is the 63-px 3D viewer this project already shipped
        # once. A "Molecules..." dialog costs no height and hides the
        # scope, putting the one control that changes WHAT IS COMPUTED
        # behind a modal while the property filter, which changes nothing,
        # sits in plain view.
        #
        # Collapsed, the default layout is unchanged until somebody asks --
        # and `_scope_label` directly above is the always-visible readout,
        # so collapsing hides the CONTROL and never the STATE.
        #
        # It reuses `CollapsibleSection`, so the toggle inherits
        # `properties.section_toggle` -- one concept, however many sections
        # exist, which is the same call the sixty batch tick boxes make.
        # RECORDED RATHER THAN FIXED: that contract also carries
        # `help_anchor="properties"`, so this Batch toggle points a reader
        # at the Properties topic. Renaming a definition that has not
        # changed meaning is what `help_id`'s own rules permit only
        # reluctantly.
        self._molecule_section = CollapsibleSection("Molecules", expanded=False, parent=self)
        self._molecules = QListWidget(self)
        # The same bound `ComparisonPanel` ships, and for the same reason:
        # a project has a handful of molecules and the list must not grow
        # into the table below it.
        self._molecules.setMaximumHeight(140)
        apply_help_tooltip(self._molecules, _HELP['molecule_scope'])
        self._molecules.itemChanged.connect(self._on_molecule_item_changed)
        self._molecule_section.add_calculator_widget(self._molecules)

        # A plain `QHBoxLayout`, NOT `flow_row`. This project measured
        # `flow_row` costing 21 px of dead band on a two-child row in the
        # Docking panel, and two short buttons come nowhere near the width
        # a dock can satisfy -- `flow_row` is a cure for a row whose
        # children cannot fit, not a prophylactic.
        molecule_buttons = QWidget(self)
        molecule_row = QHBoxLayout(molecule_buttons)
        molecule_row.setContentsMargins(0, 0, 0, 0)
        self._molecules_all_button = QPushButton("All molecules", self)
        self._molecules_all_button.clicked.connect(self._select_all_molecules)
        apply_help_tooltip(self._molecules_all_button, _HELP['molecules_all'])
        self._molecules_none_button = QPushButton("No molecules", self)
        self._molecules_none_button.clicked.connect(self._clear_molecule_selection)
        apply_help_tooltip(self._molecules_none_button, _HELP['molecules_none'])
        molecule_row.addWidget(self._molecules_all_button)
        molecule_row.addWidget(self._molecules_none_button)
        molecule_row.addStretch(1)
        self._molecule_section.add_calculator_widget(molecule_buttons)
        layout.addWidget(self._molecule_section)

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
        self._tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_property_menu)
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


    def _finalise(self, event_bus: EventBus) -> None:
        """Subscribe, populate the tree, and restore the saved selection.

        Last on purpose: `_populate_tree` and `_restore_selection`
        both read controls the steps above create.
        """
        event_bus.subscribe(BatchProgress, self._on_progress)
        self._populate_tree()
        self._make_groups_checkable()
        self._refresh_group_states()
        self._tree.itemChanged.connect(self._on_item_changed)
        self._restore_selection()

    # -- project / selection ----------------------------------------------

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self._rebuild_molecule_list()
        self._refresh_scope_label()

    def _rebuild_molecule_list(self) -> None:
        """Rebuild the scope list, keeping the ticks that still name a
        molecule.

        Rebuilt WHOLESALE rather than diffed, following
        `ComparisonPanel._rebuild_molecule_list`: there are a handful of
        molecules, and a diff is a second source of truth about what is on
        screen. Ticks survive by uuid, so renaming a molecule does not
        clear it and deleting one drops it from the scope with nothing
        stale left behind.

        **AND EVERYTHING IS TICKED WHEN NO UUID SURVIVES**, which is the
        one line that makes the rest safe. Re-setting the same project
        keeps a narrowing; loading a DIFFERENT project has no surviving
        uuid and so starts fresh at "all". That makes "all" the default
        and makes an accidental empty scope self-healing across a project
        switch, so no "not yet narrowed" sentinel is needed -- which is
        good, because "not yet narrowed" and "explicitly all" are
        indistinguishable and never need distinguishing.
        """
        chosen = self._selected_molecule_uuids()
        molecules = list(self._project.molecules) if self._project else []
        survivors = chosen & {molecule.uuid for molecule in molecules}
        # `blockSignals`, not the `_suspend_tree` guard the property tree
        # uses: nothing here propagates, so there is no re-entry to guard
        # against -- only a stream of `itemChanged` during the rebuild.
        self._molecules.blockSignals(True)
        self._molecules.clear()
        for molecule in molecules:
            item = QListWidgetItem(molecule.display_name, self._molecules)
            item.setData(Qt.ItemDataRole.UserRole, molecule.uuid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if not survivors or molecule.uuid in survivors
                else Qt.CheckState.Unchecked
            )
        self._molecules.blockSignals(False)

    def calculator_parameters(self) -> dict[str, dict]:
        """What each calculator's settings dialog produced, keyed by id.

        **ONLY WHAT WAS EXPLICITLY SET, and the absences are the design.**
        `BatchRequest.parameters`' own docstring says a calculator absent
        from the mapping runs on its registered defaults, and
        `batch_service` builds those defaults itself -- so passing through
        the ticked-and-untouched calculators with a dict this panel
        constructed would be a SECOND implementation of "what defaults
        does this calculator run on", which is the drift this project has
        paid for five times.

        So the three cases collapse into one rule rather than three
        branches:

            settings opened      present here, and used
            never opened         absent, and the service uses defaults
            no parameters        absent, and the defaults are {}

        Returned as a copy, because `_run` freezes it for one run.
        """
        return {
            calculator_id: dict(parameters)
            for calculator_id, parameters in self._calculator_parameters.items()
        }

    def _open_calculator_settings(self, calculator_id: str) -> None:
        """The settings dialog for one ticked calculator.

        Reached by double-click and by the tree's context menu -- BOTH,
        rather than a button, because this panel's vertical budget is
        measured and tight (see `benchmarks/visual/`), and because a
        context menu on its own is the affordance this project already
        records looking missing when it was there all along.

        **NO MARKER ON THE PARAMETERISED LEAVES, and that was measured
        rather than assumed**: all 69 registered calculators carry
        parameters, so a marker would mark everything.
        """
        definition = self._registry.get(calculator_id)
        if definition is None or not definition.parameters:
            self._status.setText("That property has nothing to configure.")
            return
        dialog = CalculatorSettingsDialog(definition, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._calculator_parameters[calculator_id] = dialog.parameters()
        self._status.setText(f"{definition.display_name}: settings saved for the next run.")

    def _leaf_calculator_id(self, item: QTreeWidgetItem | None) -> str | None:
        payload = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if not payload:
            return None
        kind, identifier = payload
        return None if kind == "descriptor" else identifier

    def _on_tree_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        calculator_id = self._leaf_calculator_id(item)
        if calculator_id is not None:
            self._open_calculator_settings(calculator_id)

    def _show_property_menu(self, position) -> None:
        item = self._tree.itemAt(position)
        calculator_id = self._leaf_calculator_id(item)
        if calculator_id is None:
            return
        menu = QMenu(self._tree)
        menu.addAction(
            "Settings...", lambda: self._open_calculator_settings(calculator_id)
        )
        menu.exec(self._tree.viewport().mapToGlobal(position))

    def _molecule_items(self):
        for index in range(self._molecules.count()):
            yield self._molecules.item(index)

    def _selected_molecule_uuids(self) -> set[str]:
        return {
            item.data(Qt.ItemDataRole.UserRole)
            for item in self._molecule_items()
            if item.checkState() is Qt.CheckState.Checked
        }

    def selected_molecules(self) -> list:
        """THE scope object: which molecules a run covers.

        Derived from the widget on every call and never stored, the same
        discipline `selected_ids()` keeps -- a stored copy is a second
        answer to "what is ticked" that can disagree with the screen.

        **PROJECT ORDER, NOT WIDGET ORDER**, so the results table's rows
        cannot drift from the project's however the list is rebuilt.

        A uuid that no longer names a molecule is an impossible state
        rather than a silent omission: `_rebuild_molecule_list` drops it
        on every project change, and returning a list shorter than the
        ticks claim would be exactly the "the UI estimated two and the
        service ran three" defect this method exists to remove.
        """
        if self._project is None:
            return []
        wanted = self._selected_molecule_uuids()
        return [molecule for molecule in self._project.molecules if molecule.uuid in wanted]

    def check_molecule(self, uuid: str, checked: bool = True) -> None:
        """Tick one molecule by uuid -- the hook tests and drive scripts
        use to set up a scope without simulating clicks, parallel to
        `check()` for a property."""
        for item in self._molecule_items():
            if item.data(Qt.ItemDataRole.UserRole) == uuid:
                item.setCheckState(
                    Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                )

    def _on_molecule_item_changed(self, _item: QListWidgetItem) -> None:
        self._refresh_scope_label()

    def _select_all_molecules(self) -> None:
        for item in self._molecule_items():
            item.setCheckState(Qt.CheckState.Checked)

    def _clear_molecule_selection(self) -> None:
        for item in self._molecule_items():
            item.setCheckState(Qt.CheckState.Unchecked)

    def _refresh_scope_label(self) -> None:
        """ONE readout, and the untouched wording is unchanged on purpose.

        The section title stays the bare word "Molecules" so the count is
        stated in exactly one place and cannot drift from the list below
        it. A project with everything ticked reads exactly as it did
        before this control existed, which is what lets the all-selected
        control test assert today's string.
        """
        if self._project is None:
            self._scope_label.setText("No project open.")
            return
        total = len(self._project.molecules)
        chosen = len(self._selected_molecule_uuids())
        if chosen == total:
            self._scope_label.setText(
                f"{total} molecule{'s' if total != 1 else ''} in this project."
            )
        else:
            self._scope_label.setText(f"{chosen} of {total} molecules selected.")

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
        # ONE SCOPE OBJECT, RESOLVED ONCE AND FROZEN FOR THIS RUN. This
        # local feeds the cost estimate, the request and the payload; none
        # of the three re-resolves, so the panel cannot estimate two
        # molecules while the service runs three. Ticking a molecule while
        # the cost dialog is open, or while the run is in flight, affects
        # the NEXT run.
        #
        # The uuids below are DERIVED from this list rather than read from
        # the widget a second time, which matters because the service
        # clamps the payload by `set(request.molecule_uuids)` -- so
        # widening either half alone is an equivalent mutation, and only
        # deriving one from the other makes them incapable of disagreeing.
        molecules = self.selected_molecules()
        # Frozen with the scope, for the same reason: changing a
        # calculator's settings while this run is in flight affects the
        # NEXT run, never the one already submitted.
        parameters = self.calculator_parameters()
        if not molecules:
            # REFUSED, NEVER PASSED THROUGH. `batch_service` reads an empty
            # `molecule_uuids` as "everything given" -- a deliberate
            # compatibility contract with its own tests, and one this panel
            # must not send an empty user selection into: unticking every
            # molecule and pressing Fill table would run the WHOLE PROJECT,
            # which is a bug that looks like correct behaviour. The service
            # keeps its convention; the refusal lives here, mirroring the
            # "Tick at least one property first." directly above.
            self._status.setText("Tick at least one molecule first.")
            return
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
            molecule_uuids=[molecule.uuid for molecule in molecules],
            descriptor_ids=descriptors,
            calculator_ids=calculators,
            parameters=parameters,
            per_atom_aggregate=self._aggregate.currentText(),
            structure_version=self._current_structure_version(),
        )
        self._batch_service.request_batch(request, molecules)

    def _cancel(self) -> None:
        self._batch_service.cancel()




    # -- exports ----------------------------------------------------------









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
                    # THE SAME SETTINGS THE TABLE WOULD USE. A details
                    # view computed on the registry's defaults while the
                    # table beside it used somebody's chosen parameters
                    # would be two different calculations under one name.
                    parameters=self.calculator_parameters(),
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
