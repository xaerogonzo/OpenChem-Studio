"""What the Results dock holds: the per-molecule reader.

**Project table** on this dock reveals the Batch dock, which is the one
table. This workspace no longer builds a second `ProjectTableView`.

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

from PySide6.QtCore import QTimer, Signal
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
from openchem.events.events import ScoreDefinitionsChanged
from openchem.services.batch_service import BatchProgress
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.table_export_service import TableExportService
from openchem.ui.widgets.dock_panel_actions import PanelMenuButton, PanelMenuItem
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

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


#: The Report menu in the Results dock's title bar (see `DockTitleBar.add_menu_button`): the two things the reader
#: does with the report on screen, which used to be reachable only from its control row and its right-click menu.
REPORT_MENU = PanelMenuButton(
    name="report",
    accessible="Report actions",
    text="Report",
    enabled=False,
    tooltip=HelpTooltip(
        text=(
            "Copy the report on screen, or save it to a file, in the format the reader's format box names. "
            "Greyed when no report is showing, and on the project table, which has no report of its own."
        ),
        tier=1,
        help_id="results.report_menu",
        topic="facts",
    ),
    items=(
        PanelMenuItem(
            "copy",
            "Copy report",
            HelpTooltip(
                text="Copies the report on screen to the clipboard in the chosen format.",
                tier=1,
                help_id="results.report_copy",
                topic="facts",
            ),
        ),
        PanelMenuItem(
            "export",
            "Export report...",
            HelpTooltip(
                text="Saves the report on screen to a file, in the chosen format. It asks where.",
                tier=1,
                help_id="results.report_export",
                topic="facts",
            ),
        ),
    ),
)


class ResultsWorkspace(QWidget):
    #: Whether the title bar's Report menu has anything to act on: the reader is the page showing AND it holds a
    #: report. Emitted when that changes, from either cause; read the current answer with `report_actions_available`.
    report_actions_available_changed = Signal(bool)
    #: The person asked to see the project table. The window reveals the Batch dock.
    project_table_requested = Signal()

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
        score_definitions=None,
    ) -> None:
        super().__init__(parent)
        self._reader = results_view
        self._last_run_id: str | None = None

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._switch)
        layout.addWidget(results_view, 1)

        self._report_actions_were_available = False
        if hasattr(results_view, "report_available_changed"):
            results_view.report_available_changed.connect(self._note_report_actions)
        self._note_report_actions()

    def report_actions_available(self) -> bool:
        if self.showing_project_table():
            return False
        return bool(getattr(self._reader, "report_available", lambda: False)())

    def _note_report_actions(self, *_args) -> None:
        available = self.report_actions_available()
        if available != self._report_actions_were_available:
            self._report_actions_were_available = available
            self.report_actions_available_changed.emit(available)

    def copy_report(self) -> None:
        if self.report_actions_available():
            self._reader.copy_report()

    def export_report(self) -> None:
        if self.report_actions_available():
            self._reader.export_report()

    def has_project_table(self) -> bool:
        return False

    def showing_project_table(self) -> bool:
        return self._table_button.isChecked()

    def show_project_table(self, _checked: bool = False) -> None:
        self._table_button.setChecked(True)
        self._note_report_actions()
        self.project_table_requested.emit()

    def show_molecule_reader(self, _checked: bool = False) -> None:
        self._reader_button.setChecked(True)
        self._note_report_actions()

    def begin_project_run(self, plan: ExecutionPlan) -> None:
        self._last_run_id = plan.run_id
        self.project_table_requested.emit()

    def last_run_id(self) -> str | None:
        return self._last_run_id
