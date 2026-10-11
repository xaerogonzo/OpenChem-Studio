"""What the Results dock holds: the per-molecule reader, and the project table.

**TWO PAGES, ONE SWITCH, AND THE SWITCH IS ABSENT UNTIL IT IS NEEDED.** The
reader follows the selected molecule and answers "what did everything say about
this one"; the project table answers "what did this one calculator say about
all of them". They are different questions about different objects, so the
table is a page of its own rather than an entry in the reader's "Showing" list
-- an entry there would have the table masquerade as one molecule's report.

The switch row appears only once a project run has produced a table. Results is
docked in a column that is measured and short: 26 px of a row that does nothing
for somebody who never runs on more than one molecule is the cost that decided
this, so a person who does not use the project table sees exactly the dock they
had before.

It owns no data. The table and the retained results live in the
`ProjectTableView`, whose store is the `BatchResultStore` the batch panel has
always filled -- `BatchTable` is a projection of it. A later single-molecule run
cannot disturb the table, because it never publishes a `BatchProgress`.

**IT ADOPTS A TABLE ONLY FOR A RUN IT WAS TOLD ABOUT** (`begin_project_run`).
`BatchProgress` is one event for every batch run, so a one-molecule details run
started from the Batch panel would otherwise replace the table somebody built.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.batch import BatchRequest, BatchResultStore
from openchem.domain.execution_plan import ExecutionPlan
from openchem.events.base import EventBus
from openchem.services.batch_service import BatchProgress
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.table_export_service import TableExportService
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
from openchem.ui.widgets.project_table import ProjectTableView

#: The two pages of the Results dock. Two contracts, not one: they mean different
#: things (one molecule's whole report; one table over every molecule).
_READER_PAGE_HELP = HelpTooltip(
    text=(
        "Read everything the calculators said about the molecule you have "
        "selected.\n\nThis is the Results view you had before: it follows the "
        "selection, and the project table beside it is not affected by what you "
        "select here."
    ),
    tier=1,
    help_id="results.page_molecule",
    topic="facts",
)

#: The Project table page's switch; the reader page's is above.
_TABLE_PAGE_HELP = HelpTooltip(
    text=(
        "See the last project run as a table: one row per molecule, one column "
        "per property.\n\nIt appears after you press Run selected with 'all "
        "molecules' or 'chosen molecules'. A later run on one molecule changes "
        "only that molecule's cells; sort, hide columns or export from here."
    ),
    tier=1,
    help_id="results.page_project_table",
    topic="facts",
)


class ResultsWorkspace(QWidget):
    def __init__(
        self,
        results_view: QWidget,
        calculator_registry: CalculatorRegistry,
        table_export_service: TableExportService,
        event_bus: EventBus,
        chemistry_engine,
        project_of: Callable[[], object] = lambda: None,
        structure_version_of: Callable[[str], int] = lambda _uuid: 0,
        on_analyse=None,
        on_screen=None,
        batch_service=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._batch_service = batch_service
        self._reader = results_view
        self._engine = chemistry_engine
        self._project_of = project_of
        self._structure_version_of = structure_version_of
        #: The run whose table this workspace will adopt, or None.
        self._adopting_run: str | None = None
        self._last_run_id: str | None = None
        #: The plan behind the table on screen: what its columns are, and the settings they used.
        self._plan: ExecutionPlan | None = None
        #: The molecule whose Details is waiting for a one-molecule run to land, or None.
        self._details_when_ready: str | None = None

        self._table_view = ProjectTableView(
            calculator_registry,
            table_export_service,
            self,
            on_analyse=on_analyse,
            on_screen=on_screen,
            show_cancel=True,
        )
        self._table_view.details_requested.connect(self._on_details_requested)
        self._table_view.cancel_requested.connect(self._on_cancel_requested)

        self._reader_button = QPushButton("This molecule", self)
        self._table_button = QPushButton("Project table", self)
        self._switch = QWidget(self)
        row = QHBoxLayout(self._switch)
        row.setContentsMargins(0, 0, 0, 0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for button in (self._reader_button, self._table_button):
            button.setCheckable(True)
            self._group.addButton(button)
            row.addWidget(button)
        row.addStretch(1)
        apply_help_tooltip(self._reader_button, _READER_PAGE_HELP)
        apply_help_tooltip(self._table_button, _TABLE_PAGE_HELP)
        self._reader_button.setChecked(True)
        self._reader_button.clicked.connect(self.show_molecule_reader)
        self._table_button.clicked.connect(self.show_project_table)
        self._switch.setVisible(False)

        self._stack = QStackedWidget(self)
        self._stack.addWidget(results_view)
        self._stack.addWidget(self._table_view)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._switch)
        layout.addWidget(self._stack, 1)

        event_bus.subscribe(BatchProgress, self._on_progress)

    # -- the two pages -------------------------------------------------------

    @property
    def table_view(self) -> ProjectTableView:
        return self._table_view

    def has_project_table(self) -> bool:
        return self._table_view.table() is not None

    def showing_project_table(self) -> bool:
        return self._stack.currentWidget() is self._table_view

    def show_project_table(self, _checked: bool = False) -> None:
        self._stack.setCurrentWidget(self._table_view)
        self._table_button.setChecked(True)

    def show_molecule_reader(self, _checked: bool = False) -> None:
        self._stack.setCurrentWidget(self._reader)
        self._reader_button.setChecked(True)

    # -- a project run -------------------------------------------------------

    def begin_project_run(self, plan: ExecutionPlan) -> None:
        """Adopt the table of THIS run, and put it in front.

        Called before the run is handed to the service, so the first progress
        event (QUEUED, published synchronously) already finds the workspace
        listening.
        """
        self._adopting_run = plan.run_id
        self._last_run_id = plan.run_id
        self._plan = plan
        self._switch.setVisible(True)
        self.show_project_table()

    def last_run_id(self) -> str | None:
        return self._last_run_id

    def _on_progress(self, event: BatchProgress) -> None:
        if self._adopting_run is not None:
            running = self._table_view.apply_progress(event, adopt=True)
            if not running:
                self._adopting_run = None
            return
        if self._details_when_ready is None:
            return
        # A one-molecule run for a Details view: its results merge into the store the table
        # reads, and the table itself is NOT replaced by its one-row answer.
        if not self._table_view.apply_progress(event, adopt=False):
            # Not in this handler: a modal dialog opened inside a bus dispatch starves every
            # later subscriber of the same event (CLAUDE.md: the calculator reveal did exactly
            # that), so it is opened once the dispatch has finished.
            QTimer.singleShot(0, self, self._present_pending_details)

    def _present_pending_details(self) -> None:
        molecule_uuid, self._details_when_ready = self._details_when_ready, None
        if molecule_uuid is not None:
            self._present_details(molecule_uuid)

    def _on_cancel_requested(self) -> None:
        if self._batch_service is not None:
            self._batch_service.cancel()

    def _missing_for(self, molecule_uuid: str) -> list[str]:
        """The table's calculators this molecule has no CURRENT result for.

        Keyed on the structure version, so an edited molecule's old results do not count as
        computed: "done" and "done for a structure that no longer exists" are different.
        **Always-on properties and alert catalogs are not asked about**: the store retains
        calculator results only (they are cells of the table, not entries of the store), so
        they would read as missing every time, and Details shows what the store holds.
        """
        if self._plan is None:
            return []
        store = self._table_view._store
        have = set(store.for_molecule(molecule_uuid, self._structure_version_of(molecule_uuid))) if store else set()
        return [c for c in self._plan.calculator_ids if c not in have]

    def _on_details_requested(self, molecule_uuid: str) -> None:
        """Everything the table's properties say about one molecule, in the Properties renderer.

        **NOTHING IS COMPUTED UNASKED, AND THIS IS THE ASKING.** Opening a molecule runs the
        table's properties for THAT molecule if it has no current result for some of them
        (a row left out of the run, a structure edited since), on the same settings the
        table used, through the same service. Another run in progress is not interrupted.
        """
        project = self._project_of()
        molecule = project.find_molecule(molecule_uuid) if project is not None else None
        if molecule is None:
            return
        calculators = self._missing_for(molecule_uuid)
        if calculators and self._batch_service is not None and getattr(molecule, "molblock", ""):
            if self._batch_service.is_running():
                self._table_view.set_status("A run is already in progress -- try again when it finishes.")
                return
            self._details_when_ready = molecule_uuid
            self._table_view.set_status(f"Computing {molecule.display_name}...")
            self._batch_service.request_batch(
                BatchRequest(
                    molecule_uuids=[molecule_uuid],
                    calculator_ids=calculators,
                    parameters={cid: dict(p) for cid, p in self._plan.requested_parameters.items()},
                    per_atom_aggregate=self._plan.per_atom_aggregate,
                    structure_versions={molecule_uuid: self._structure_version_of(molecule_uuid)},
                ),
                [molecule],
            )
            return
        self._present_details(molecule_uuid)

    def _present_details(self, molecule_uuid: str) -> None:
        project = self._project_of()
        molecule = project.find_molecule(molecule_uuid) if project is not None else None
        if molecule is None:
            return
        from openchem.ui.dialogs.batch_detail_dialog import BatchDetailDialog

        store = self._table_view._store
        dialog = BatchDetailDialog(
            self._engine,
            molecule,
            store if store is not None else BatchResultStore(),
            self._structure_version_of(molecule_uuid),
            self,
        )
        dialog.exec()
