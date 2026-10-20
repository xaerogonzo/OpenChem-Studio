"""The synthesis panel (`docs/SYNTHESIS_HELPER_DESIGN.md`, Stage 1 slice 8): plan a synthesis for the selected molecule through the user's own AiZynthFinder, and read what came back.

IT STARTS NOTHING ITSELF. Every plan goes through `context.synthesis_requests.request_plan`, which is `SynthesisPlanningService.request_plan`, where the regulatory gate runs before any process starts; this panel has no
other way to reach the planner, and a refusal, an `unscreened` target and "the planner is not set up" all come back as an ordinary stored result that this panel shows like any other.

WHAT IS SHOWN IS BOUND TO A STRUCTURE. `result_for` says whether the plan was made for the structure now drawn; a plan for an earlier structure is shown under a warning that says so, never as the plan for this one.

THE PLANNER'S CONFIGURATION IS READ OFF THE GUI THREAD. Reading it starts the planner's Python (about 1.6 s the first time, then cached by file), so the three lists are filled from a worker when the panel is shown, and a
Plan pressed before that has finished waits for it and then asks. Nothing in the window waits on a program.

NOTHING HERE SAYS A ROUTE WORKS. A route is "proposed", the planner's score is "the planner's score", and the standing limitations (`RouteSet.all_limitations`) are always on screen beside the routes.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.reaction_depiction import DepictionError
from openchem.domain.common import CacheState
from openchem.domain.synthesis_route import Route, RouteSet
from openchem.events.events import (
    MoleculeChanged,
    MoleculeSelected,
    MoleculeSnapshotUpdated,
    ProjectClosed,
    ProjectLoaded,
    SettingsChanged,
    SynthesisJobStateChanged,
    SynthesisRouteReady,
)
from openchem.plugins.async_task import run_async
from openchem.plugins.context import PluginContext
from openchem.services.synthesis_planner_setup import PlannerOptions
from openchem.services.synthesis_planning_service import BoundResult, RequestOutcome
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

from . import route_text

logger = logging.getLogger("openchem.plugin.synthesis_planner")

#: Where a person sets the planner up, as the panel says it.
SETUP_WHERE = "Edit > Settings > External tools > AiZynthFinder"

#: The label of the filter list's first entry: no filter, which is the default and what the published numbers describe.
NO_FILTER_LABEL = "No filter"

_PLAN_HELP = HelpTooltip(
    text=(
        "Ask the synthesis planner (AiZynthFinder, in the environment you set up under External tools) for routes to the selected molecule.\n\n"
        "A search takes minutes and about 3 to 5 GB of memory, and runs in a program of its own. The target is checked against the chemical-weapons "
        "schedule first, and a match is refused before anything starts. What comes back are proposals from a program trained on patent reactions: "
        "no conditions, no yields, nothing tested."
    ),
    tier=2,
    help_id="synthesis.plan",
)
_CANCEL_HELP = HelpTooltip(
    text="Stop this molecule's search and end the planner's program, or take the request out of the queue if it has not started. Nothing is kept from a search that was cancelled.",
    tier=1,
    help_id="synthesis.cancel",
)
_EXPANSION_HELP = HelpTooltip(
    text=(
        "The expansion policy: the trained model that proposes which reactions to try, as the planner's configuration names it. The default is uspto, the one the project's benchmark ran.\n\n"
        "Takes effect on the next plan; a search under way keeps the one it started with."
    ),
    tier=2,
    help_id="synthesis.expansion_policy",
)
_STOCK_HELP = HelpTooltip(
    text=(
        "The stock: the list of molecules the planner counts as available to buy, so a route ends at them. A bigger stock finds more routes and says less about what you can actually get.\n\n"
        "Takes effect on the next plan; a search under way keeps the one it started with."
    ),
    tier=2,
    help_id="synthesis.stock",
)
_FILTER_HELP = HelpTooltip(
    text=(
        "The filter policy: an optional model that discards proposed reactions it scores as unlikely to work. The default is no filter, the configuration the project's benchmark ran.\n\n"
        "Takes effect on the next plan; a search under way keeps the one it started with."
    ),
    tier=2,
    help_id="synthesis.filter_policy",
)
_ROUTES_HELP = HelpTooltip(
    text="The routes the planner returned, in the planner's own order. The order is the planner's, and a first place does not say the route is the best or that it would work.",
    tier=1,
    help_id="synthesis.routes",
)
_STEPS_HELP = HelpTooltip(
    text="The steps of the selected route in the order they would be run, each from its reactants to its product. Select one to see it drawn.",
    tier=1,
    help_id="synthesis.steps",
)


def _list(parent: QWidget, tooltip: HelpTooltip, minimum_height: int, maximum_height: int) -> QListWidget:
    widget = QListWidget(parent)
    widget.setMinimumHeight(minimum_height)
    # Capped, so the step's picture is within a short scroll of the list that chose it instead of a screenful below it.
    widget.setMaximumHeight(maximum_height)
    widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
    apply_help_tooltip(widget, tooltip)
    return widget


class SynthesisPanel(QWidget):
    def __init__(self, context: PluginContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._synthesis = context.synthesis
        self._requests = context.synthesis_requests
        self._options: PlannerOptions | None = None
        self._options_loading = False
        #: A Plan pressed before the configuration was read: the molecule to ask for once it has been.
        self._plan_after_options: str | None = None
        self._target = None
        self._shown: RouteSet | None = None
        #: The newest state message of a running search, for the molecule it is about.
        self._job_message: dict[str, str] = {}
        #: What the last request said when it started nothing; shown in place of the plan's own message until something else is selected or a plan arrives.
        self._notice = ""

        self._target_label = QLabel(self)
        self._target_label.setWordWrap(True)
        self._target_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._expansion = QComboBox(self)
        self._stock = QComboBox(self)
        self._filter = QComboBox(self)
        for combo, tooltip, section in ((self._expansion, _EXPANSION_HELP, "expansion"), (self._stock, _STOCK_HELP, "stock"), (self._filter, _FILTER_HELP, "filter")):
            apply_help_tooltip(combo, tooltip)
            combo.activated.connect(lambda _index, s=section: self._on_choice(s))
        self._version_label = QLabel("", self)
        self._version_label.setStyleSheet("color: #6e6e6e;")

        choices = QFormLayout()
        choices.addRow("Expansion policy:", self._expansion)
        choices.addRow("Stock:", self._stock)
        choices.addRow("Filter:", self._filter)

        self._plan_button = QPushButton("Plan synthesis", self)
        apply_help_tooltip(self._plan_button, _PLAN_HELP)
        self._plan_button.clicked.connect(self._on_plan_clicked)
        self._cancel_button = QPushButton("Cancel", self)
        apply_help_tooltip(self._cancel_button, _CANCEL_HELP)
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        buttons = QHBoxLayout()
        buttons.addWidget(self._plan_button)
        buttons.addWidget(self._cancel_button)
        buttons.addStretch(1)

        self._status = QLabel(self)
        self._status.setWordWrap(True)
        self._status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        #: Set only when the plan shown is for an earlier structure of the molecule.
        self._warning = QLabel(self)
        self._warning.setWordWrap(True)
        self._warning.setStyleSheet("color: #b45309; font-weight: bold;")
        self._warning.setHidden(True)

        self._routes = _list(self, _ROUTES_HELP, 90, 140)
        self._routes.currentRowChanged.connect(self._on_route_changed)
        self._steps = _list(self, _STEPS_HELP, 70, 100)
        self._steps.currentRowChanged.connect(self._on_step_changed)

        # A QSvgWidget is given a picture and nothing else: a sentence put in an SVG is scaled with the pane and becomes unreadable, so a drawing that failed is a QLabel.
        self._picture = QSvgWidget(self)
        self._picture.setMinimumHeight(180)
        self._picture_message = QLabel(self)
        self._picture_message.setWordWrap(True)
        self._picture_message.setHidden(True)

        self._details = QPlainTextEdit(self)
        self._details.setReadOnly(True)
        self._details.setMinimumHeight(140)

        self._limitations = QLabel(self)
        self._limitations.setWordWrap(True)
        self._limitations.setStyleSheet("color: #6e6e6e;")

        # Everything about routes is one block that is shown only when there are routes: two empty lists under a refusal are a screenful of nothing between the
        # reason and the limitations.
        self._route_block = QWidget(self)
        block = QVBoxLayout(self._route_block)
        block.setContentsMargins(0, 0, 0, 0)
        block.addWidget(QLabel("Routes (proposed, in the planner's order):", self))
        block.addWidget(self._routes)
        block.addWidget(QLabel("Steps, in the order they would be run:", self))
        block.addWidget(self._steps)
        block.addWidget(self._picture)
        block.addWidget(self._picture_message)
        block.addWidget(self._details)

        content = QWidget(self)
        layout = QVBoxLayout(content)
        layout.addWidget(self._target_label)
        layout.addLayout(choices)
        layout.addWidget(self._version_label)
        layout.addLayout(buttons)
        layout.addWidget(self._status)
        layout.addWidget(self._warning)
        layout.addWidget(self._route_block)
        layout.addWidget(self._limitations)
        layout.addStretch(1)

        # A scroll area, so a short dock shows everything by scrolling instead of squeezing the lists to nothing.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        events = context.events
        for event_type in (MoleculeSelected, MoleculeChanged, MoleculeSnapshotUpdated, ProjectLoaded, ProjectClosed):
            events.subscribe(event_type, self._on_molecule_event)
        events.subscribe(SettingsChanged, self._on_setting_changed)
        events.subscribe(SynthesisRouteReady, self._on_route_ready)
        events.subscribe(SynthesisJobStateChanged, self._on_job_state)

        self.refresh()

    # --- what is on screen -----------------------------------------------------------------------------------------------------

    def refresh(self) -> None:
        """Read the selected molecule and its stored plan again and show them."""
        target = self._synthesis.target()
        self._target = target
        if target is None:
            self._target_label.setText("Select a molecule with a drawn structure to plan its synthesis.")
            self._show_result(None, planning=False)
        else:
            self._target_label.setText(f"Target: {target.display_name}\n{target.canonical_smiles}")
            planning = self._synthesis.is_planning(target.molecule_uuid)
            self._show_result(self._synthesis.result_for(target.molecule_uuid), planning=planning)
        self._update_buttons()

    def _show_result(self, bound: BoundResult | None, *, planning: bool) -> None:
        self._shown = bound.route_set if bound is not None else None
        self._warning.setHidden(bound is None or bound.is_current)
        if bound is not None and not bound.is_current:
            self._warning.setText(f"EARLIER STRUCTURE: {bound.note}")
        if planning:
            message = self._job_message.get(self._target.molecule_uuid if self._target else "", "")
            self._status.setText(message or "Planning... the planner's program loads its models first, which takes about 20 seconds.")
        elif self._notice:
            self._status.setText(self._notice)
        elif bound is not None:
            self._status.setText(bound.route_set.message())
        elif self._target is None:
            self._status.setText("")
        elif self._options is not None and not self._options.ok:
            self._status.setText(f"{self._options.problem} Set it up under {SETUP_WHERE}.")
        else:
            self._status.setText("No plan for this molecule yet.")

        self._routes.blockSignals(True)
        self._routes.clear()
        if self._shown is not None:
            for route in self._shown.routes:
                self._routes.addItem(route_text.route_title(route))
        self._routes.blockSignals(False)
        limitations = self._shown.all_limitations() if self._shown is not None else ()
        self._limitations.setText("\n".join(f"- {text}" for text in limitations))
        self._route_block.setHidden(not self._routes.count())
        if self._routes.count():
            self._routes.setCurrentRow(0)
            self._on_route_changed(0)
        else:
            self._clear_route()

    def _clear_route(self) -> None:
        self._steps.blockSignals(True)
        self._steps.clear()
        self._steps.blockSignals(False)
        self._details.setPlainText("")
        self._show_picture_message("")

    def _route(self) -> Route | None:
        row = self._routes.currentRow()
        if self._shown is None or not 0 <= row < len(self._shown.routes):
            return None
        return self._shown.routes[row]

    def _on_route_changed(self, _row: int) -> None:
        route = self._route()
        if route is None:
            self._clear_route()
            return
        self._steps.blockSignals(True)
        self._steps.clear()
        for number, step in enumerate(route.steps, start=1):
            self._steps.addItem(route_text.step_title(number, step))
        self._steps.blockSignals(False)
        self._steps.setCurrentRow(0)
        self._on_step_changed(0)

    def _on_step_changed(self, row: int) -> None:
        route = self._route()
        if route is None or not 0 <= row < len(route.steps):
            self._details.setPlainText("")
            self._show_picture_message("")
            return
        step = route.steps[row]
        self._details.setPlainText(f"{route_text.step_text(step)}\n\n{route_text.route_text(route)}")
        try:
            svg = self._synthesis.depict(step)
        except (DepictionError, LookupError) as exc:
            self._show_picture_message(f"This step cannot be drawn: {exc}")
            return
        self._picture.load(QByteArray(svg.encode("utf-8")))
        self._picture.renderer().setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self._picture.setHidden(False)
        self._picture_message.setHidden(True)

    def _show_picture_message(self, text: str) -> None:
        self._picture.setHidden(True)  # a picture is shown by `_on_step_changed` alone, and only after it has loaded
        self._picture_message.setText(text)
        self._picture_message.setHidden(not text)

    def _update_buttons(self) -> None:
        target = self._target
        planning = target is not None and self._synthesis.is_planning(target.molecule_uuid)
        waiting = self._plan_after_options is not None
        self._plan_button.setEnabled(target is not None and not planning and not waiting)
        self._cancel_button.setEnabled(planning)

    # --- the planner's configuration, read off the GUI thread ---------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self._load_options()

    def _load_options(self) -> None:
        if self._options_loading:
            return
        self._options_loading = True
        run_async(self._synthesis.options, Exception, self._on_options, self._on_options_failed)

    def _on_options(self, options: PlannerOptions) -> None:
        self._options_loading = False
        self._options = options
        self._fill_choices(options)
        pending, self._plan_after_options = self._plan_after_options, None
        if pending is not None and self._target is not None and self._target.molecule_uuid == pending:
            self._start_plan(pending)
        else:
            self.refresh()

    def _on_options_failed(self, message: str) -> None:
        self._options_loading = False
        self._on_options(PlannerOptions(ok=False, problem=f"The planner's configuration could not be read ({message})."))

    def _fill_choices(self, options: PlannerOptions) -> None:
        for combo, names, chosen in (
            (self._expansion, options.expansion, options.chosen_expansion),
            (self._stock, options.stock, options.chosen_stock),
            (self._filter, (NO_FILTER_LABEL, *options.filters), options.chosen_filter or NO_FILTER_LABEL),
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(list(names))
            if chosen in names:
                combo.setCurrentText(chosen)
            combo.setEnabled(bool(options.expansion))
            combo.blockSignals(False)
        self._version_label.setText(f"AiZynthFinder {options.version}" if options.version else "")

    def _on_choice(self, section: str) -> None:
        combo = {"expansion": self._expansion, "stock": self._stock, "filter": self._filter}[section]
        name = combo.currentText()
        self._requests.choose(section, None if section == "filter" and name == NO_FILTER_LABEL else name)
        self._load_options()

    # --- asking -----------------------------------------------------------------------------------------------------------------

    def _on_plan_clicked(self) -> None:
        target = self._target
        if target is None:
            return
        if not self._synthesis.setup_is_warm():
            self._plan_after_options = target.molecule_uuid
            self._status.setText("Reading the planner's configuration...")
            self._update_buttons()
            self._load_options()
            return
        self._start_plan(target.molecule_uuid)

    def _start_plan(self, molecule_uuid: str) -> None:
        outcome = self._requests.request_plan(molecule_uuid)
        self._notice = {
            RequestOutcome.ALREADY_RUNNING: "This molecule is already being planned.",
            RequestOutcome.REJECTED: "There is nothing to plan for this molecule.",
        }.get(outcome, "")
        self.refresh()

    def _on_cancel_clicked(self) -> None:
        if self._target is not None:
            self._requests.cancel(self._target.molecule_uuid)
        self._update_buttons()

    # --- events -----------------------------------------------------------------------------------------------------------------

    def _on_molecule_event(self, _event) -> None:
        self._notice = ""
        self.refresh()

    def _on_setting_changed(self, event: SettingsChanged) -> None:
        # The External Tools tab (or a script) moved the planner: read what it offers again, off the GUI thread.
        if event.key.startswith("aizynthfinder/") and self.isVisible():
            self._load_options()

    def _on_route_ready(self, event: SynthesisRouteReady) -> None:
        self._job_message.pop(event.molecule_uuid, None)
        self._notice = ""
        self.refresh()

    def _on_job_state(self, event: SynthesisJobStateChanged) -> None:
        if event.state in (CacheState.QUEUED, CacheState.RUNNING):
            self._job_message[event.molecule_uuid] = event.message
        else:
            self._job_message.pop(event.molecule_uuid, None)
        self.refresh()
