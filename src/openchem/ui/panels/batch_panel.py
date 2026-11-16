"""The project table: one table for every project run.

Properties owns ticks, goals, presets and scope. This dock is the table
those runs fill. Fill table asks Properties for the current plan rather
than building a second one.

WHY FAILURES ARE SHOWN AS CELLS. A 3D descriptor across a project with no
conformers fails for every molecule, and the difference between "this
calculator produced nothing" and "this calculator was never run" is the
difference between a bug report and a working app. Failed cells carry an
em dash and the reason as a tooltip.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.batch import (
    BatchRequest,
    BatchResultStore,
    BatchTable,
)
from openchem.domain.common import CacheState
from openchem.domain.execution_plan import ExecutionPlan
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import ScoreDefinitionsChanged
from openchem.services.batch_service import BatchProgress, BatchService
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.table_export_service import TableExportService
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
        score_definitions=None,
        fill_runner: Callable[[], None] | None = None,
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
        self._fill_runner = fill_runner
        #: Plan whose table this dock is showing, if a project run has started.
        self._plan: ExecutionPlan | None = None
        #: Ids a test asked `check()` to run; Fill table in the app ignores this.
        self._queued_ids: list[str] = []
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
            show_cancel=True,
            score_definitions=score_definitions,
        )
        self._view.details_requested.connect(self._show_details)
        self._view.cancel_requested.connect(self._cancel)

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
            if self._details_when_ready is not None:
                QTimer.singleShot(0, self, self._open_pending_details)

    def _on_score_definitions_changed(self, _event) -> None:
        """A score was defined, edited or removed: this table's score columns follow, without a second run (the Results dock's table does the same)."""
        self._view.refresh_scores()

    def set_fill_runner(self, runner):
        self._fill_runner = runner

    def begin_project_run(self, plan: ExecutionPlan) -> None:
        self._plan = plan
        self._filling_table = True

    def _build_selection(self, layout: QVBoxLayout) -> None:
        self._scope_label = QLabel("No project open.")
        layout.addWidget(self._scope_label)
        from openchem.ui.widgets.flow_layout import flow_row
        button_row = flow_row(self)
        self._run_button = QPushButton("Fill table…", self)
        self._run_button.clicked.connect(self._run)
        apply_help_tooltip(self._run_button, _HELP["run"])
        self._cancel_button = QPushButton("Cancel", self)
        self._cancel_button.clicked.connect(self._cancel)
        apply_help_tooltip(self._cancel_button, _HELP["cancel"])
        self._cancel_button.setEnabled(False)
        button_row.layout().addWidget(self._run_button)
        button_row.layout().addWidget(self._cancel_button)
        layout.addWidget(button_row)


    def _finalise(self, event_bus: EventBus) -> None:
        event_bus.subscribe(BatchProgress, self._on_progress)
        event_bus.subscribe(ScoreDefinitionsChanged, self._on_score_definitions_changed)

    # -- project / selection ----------------------------------------------

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self._refresh_scope_label()

    def _refresh_scope_label(self) -> None:
        if self._project is None:
            self._scope_label.setText("No project open.")
            return
        total = len(self._project.molecules)
        self._scope_label.setText(
            f"{total} molecule{'s' if total != 1 else ''} in this project."
        )

    def selected_molecules(self) -> list:
        return list(self._project.molecules) if self._project else []

    def selected_ids(self) -> tuple[list[str], list[str]]:
        from openchem.chem.descriptor_providers import RDKitDescriptorProvider

        provider = RDKitDescriptorProvider()
        known_desc = set(provider.descriptor_ids()) | set(provider.alert_ids())
        descriptors = [i for i in self._queued_ids if i in known_desc]
        calculators = [i for i in self._queued_ids if i not in known_desc]
        return descriptors, calculators

    def check(self, identifier: str, checked: bool = True) -> None:
        if checked:
            if identifier not in self._queued_ids:
                self._queued_ids.append(identifier)
        elif identifier in self._queued_ids:
            self._queued_ids.remove(identifier)

    def _clear_selection(self) -> None:
        self._queued_ids.clear()

    def _missing_for(self, molecule_uuid: str) -> list[str]:
        _descriptors, calculators = self._needs_computing(molecule_uuid)
        return calculators

    def calculator_parameters(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self._calculator_parameters.items()}

    def _run(self) -> None:
        if self._fill_runner is not None:
            self._fill_runner()
            return
        if self._project is None:
            self._status.setText("Open or create a project first.")
            return
        descriptors, calculators = self.selected_ids()
        if not descriptors and not calculators:
            self._status.setText("Tick at least one property first.")
            return
        molecules = self.selected_molecules()
        if not molecules:
            self._status.setText("Tick at least one molecule first.")
            return
        self._filling_table = True
        versions = {m.uuid: self._version_of(m.uuid) for m in molecules}
        self._batch_service.request_batch(
            BatchRequest(
                molecule_uuids=[m.uuid for m in molecules],
                descriptor_ids=descriptors,
                calculator_ids=calculators,
                parameters=self.calculator_parameters(),
                structure_versions=versions,
            ),
            molecules,
        )

    def _cancel(self) -> None:
        self._batch_service.cancel()




    def _version_of(self, molecule_uuid: str) -> int:
        if self._structure_check is None:
            return 0
        try:
            return int(self._structure_check.current_version(molecule_uuid))
        except TypeError:
            try:
                return int(self._structure_check.current_version())
            except Exception:
                return 0
        except Exception:
            logger.debug("Could not read the structure version for a batch run")
            return 0

    def _needs_computing(self, molecule_uuid: str) -> tuple[list[str], list[str]]:
        if self._plan is not None:
            descriptors, calculators = list(self._plan.descriptor_ids), list(self._plan.calculator_ids)
        else:
            descriptors, calculators = self.selected_ids()
        if self._store is None:
            return descriptors, calculators
        have = set(self._store.for_molecule(molecule_uuid, self._version_of(molecule_uuid)))
        return (
            [d for d in descriptors if d not in have],
            [c for c in calculators if c not in have],
        )

    def _open_pending_details(self) -> None:
        uuid, self._details_when_ready = self._details_when_ready, None
        if uuid is not None:
            self._present_details(uuid)

    def _show_details(self, molecule_uuid: str | None) -> None:
        if not molecule_uuid or self._project is None:
            return
        molecule = self._project.find_molecule(molecule_uuid)
        if molecule is None:
            return
        calculators = self._missing_for(molecule_uuid)
        if calculators and getattr(molecule, "molblock", ""):
            if self._batch_service.is_running():
                self._status.setText("A run is already in progress -- try again when it finishes.")
                return
            self._filling_table = False
            self._details_when_ready = molecule_uuid
            self._status.setText(f"Computing {molecule.display_name}...")
            parameters = (
                {cid: dict(p) for cid, p in self._plan.requested_parameters.items()}
                if self._plan is not None
                else self.calculator_parameters()
            )
            aggregate = self._plan.per_atom_aggregate if self._plan is not None else "mean"
            self._batch_service.request_batch(
                BatchRequest(
                    molecule_uuids=[molecule_uuid],
                    calculator_ids=calculators,
                    parameters=parameters,
                    per_atom_aggregate=aggregate,
                    structure_versions={molecule_uuid: self._version_of(molecule_uuid)},
                ),
                [molecule],
            )
            return
        self._present_details(molecule_uuid)

    def _present_details(self, molecule_uuid: str) -> None:
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
            self._version_of(molecule_uuid),
            self,
        )
        dialog.exec()
