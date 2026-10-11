"""Run calculators by what you want to know.

**ONE QUESTION, TWO WAYS TO ANSWER IT.** The first page lists the goals; pick one and
press **Run recommended** and that is the whole interaction: the curated set runs on
the scope shown, with default settings. **Customise** is the longer road for the person
who wants to see what is in the set, untick one, add an optional one, or change a
setting first -- and it shows what the run will cost and what it will leave out before
anything starts.

**NOTHING HERE IS GATED.** The wizard is a shortcut over the same calculators the
launcher lists, run through the same plan and the same services; it does not change a
tick, a preset or a scope in Properties, and every calculator it can run is still one
click away there.

**A RUN IS WHAT IT WAS WHEN YOU PRESSED RUN.** Pressing Run builds a `GoalRun`, an
immutable value, and hands it on; changing the goal, the ticks or the scope afterwards
cannot reach a run already started, and a second press starts a second run beside it
rather than editing the first.

It is modeless and there is one of it (the window raises the open one), so it can sit
beside Properties and Results while a run is going. It knows no chemistry: it is handed
the lookups it needs, and it imports no engine.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.calculator import CalculatorDefinition
from openchem.domain.calculator_goals import (
    GOALS,
    SCOPE_ALL,
    SCOPE_CHOSEN,
    SCOPE_THIS,
    Goal,
    GoalRun,
    goal_of,
    needs_conformer,
)
from openchem.domain.execution_plan import build_execution_plan
from openchem.ui.dialogs.calculator_settings_dialog import CalculatorSettingsDialog
from openchem.ui.dialogs.molecule_scope_dialog import MoleculeScopeDialog
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: The goal list: one entry per question the launcher can answer as a set.
_GOAL_LIST_HELP = HelpTooltip(
    text=(
        "What you want to know about the molecule. Each goal is a short, curated set of "
        "calculators that answer it, so you do not have to know which sections they live in.\n\n"
        "The sets are editorial -- a reasonable first answer, not a validated protocol -- and "
        "every calculator in one is still in its own section of Properties."
    ),
    tier=1,
    help_id="wizard.goal_list",
    topic="properties",
    help_anchor="properties",
)

#: The scope chooser on the wizard's first page.
_SCOPE_HELP = HelpTooltip(
    text=(
        "Which molecules the run covers: the one selected in the Project Explorer, every "
        "molecule in the project, or a few you choose.\n\n"
        "It starts as the scope Properties has. Changing it here does not change Properties."
    ),
    tier=1,
    help_id="wizard.scope",
    topic="properties",
    help_anchor="properties",
)

#: The primary button: the whole quick path.
_RUN_RECOMMENDED_HELP = HelpTooltip(
    text=(
        "Run the recommended calculators for the chosen goal on the chosen molecules, with "
        "their default settings.\n\n"
        "It asks nothing further. The calculators are listed above the button, and it never "
        "changes your ticks or your presets."
    ),
    tier=2,
    help_id="wizard.run_recommended",
    topic="properties",
    help_anchor="properties",
)

#: The longer road to the same run.
_CUSTOMISE_HELP = HelpTooltip(
    text=(
        "See what is in the set before running it: untick any, add optional ones, and change "
        "a calculator's settings. The page says how many calculations that is and what will be "
        "left out."
    ),
    tier=1,
    help_id="wizard.customise",
    topic="properties",
    help_anchor="properties",
)

#: The Run button on the customise page.
_RUN_HELP = HelpTooltip(
    text=(
        "Start the run with exactly what is ticked and the settings shown. Once started it is "
        "fixed: changing anything here afterwards starts a different run, it does not edit this one."
    ),
    tier=2,
    help_id="wizard.run",
    topic="properties",
    help_anchor="properties",
)

#: One calculator's tick on the customise page.
_ENTRY_HELP = HelpTooltip(
    text=(
        "Include this calculator in the run. Recommended ones start ticked; optional ones "
        "answer a narrower or costlier version of the question and start unticked."
    ),
    tier=1,
    help_id="wizard.entry",
    topic="properties",
    help_anchor="properties",
)

#: A calculator's Settings button on the customise page.
_ENTRY_SETTINGS_HELP = HelpTooltip(
    text=(
        "Choose this calculator's settings for this run. Without it, it runs on its defaults, "
        "which is what Run recommended uses."
    ),
    tier=1,
    help_id="wizard.entry_settings",
    topic="properties",
    help_anchor="properties",
)

#: The shortcut to conformer generation, shown when 3D calculators have nothing to run on.
_CONFORMERS_HELP = HelpTooltip(
    text=(
        "Some of these calculators work on a 3D structure, and some molecules in the scope "
        "have none. This opens Structure > Generate Conformers... so you can make them, then "
        "run again."
    ),
    tier=1,
    help_id="wizard.generate_conformers",
    topic="properties",
    help_anchor="properties",
)

#: The wizard's first page: pick a goal, run its recommended set.
_PAGE_GOALS = 0

#: The wizard's second page: see the set, change it, then run it.
_PAGE_CUSTOMISE = 1


class GoalWizardDialog(QDialog):
    """Pick a goal, then run its recommended set, or customise first."""

    #: A run was asked for. Carries an immutable `GoalRun`.
    run_requested = Signal(object)

    def __init__(
        self,
        definition_of: Callable[[str], CalculatorDefinition | None],
        molecules_of: Callable[[], Sequence],
        selected_uuid_of: Callable[[], str | None],
        scope_of: Callable[[], tuple[str, set[str]]],
        parent: QWidget | None = None,
        *,
        on_generate_conformers: Callable[[], None] | None = None,
        structure_version_of: Callable[[str], int] = lambda _uuid: 0,
        plain_label: Callable[[str], str] = lambda text: text,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Run calculators by goal")
        self.setModal(False)
        #: The run most recently asked for, or None. Immutable, so holding it is safe.
        self.last_run: GoalRun | None = None
        self._definition_of = definition_of
        self._molecules_of = molecules_of
        self._selected_uuid_of = selected_uuid_of
        self._on_generate_conformers = on_generate_conformers
        self._structure_version_of = structure_version_of
        self._plain_label = plain_label
        mode, chosen = scope_of()
        self._scope_mode = mode if mode in (SCOPE_THIS, SCOPE_ALL, SCOPE_CHOSEN) else SCOPE_THIS
        self._scope_chosen: set[str] = set(chosen)
        self._goal: Goal = GOALS[0]
        #: Settings chosen on the customise page, by calculator id. Only what was chosen.
        self._chosen_parameters: dict[str, dict] = {}
        self._entry_checks: dict[str, QCheckBox] = {}

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_goals_page())
        self._stack.addWidget(self._build_customise_page())
        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self._stack)
        layout.addWidget(self._status)
        self.resize(560, 560)

        self._goal_list.setCurrentRow(0)
        self._refresh_scope_labels()
        self._refresh_goal_page()

    # -- the first page: pick a goal, run its recommended set ------------------------------

    def _build_goals_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        heading = QLabel("What do you want to know?", page)
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)

        self._goal_list = QListWidget(page)
        apply_help_tooltip(self._goal_list, _GOAL_LIST_HELP)
        for goal in GOALS:
            item = QListWidgetItem(f"{goal.label}\n{goal.question}", self._goal_list)
            item.setData(Qt.ItemDataRole.UserRole, goal.goal_id)
        self._goal_list.currentRowChanged.connect(self._on_goal_changed)
        layout.addWidget(self._goal_list, 1)

        self._will_run = QLabel("", page)
        self._will_run.setWordWrap(True)
        layout.addWidget(self._will_run)

        self._scope_combo = QComboBox(page)
        self._scope_combo.addItem("Run on: this molecule", SCOPE_THIS)
        self._scope_combo.addItem("Run on: all molecules", SCOPE_ALL)
        self._scope_combo.addItem("Run on: chosen molecules...", SCOPE_CHOSEN)
        apply_help_tooltip(self._scope_combo, _SCOPE_HELP)
        self._scope_combo.activated.connect(self._on_scope_activated)
        layout.addWidget(self._scope_combo)

        buttons = QHBoxLayout()
        self._run_recommended_button = QPushButton("Run recommended", page)
        self._run_recommended_button.setDefault(True)
        apply_help_tooltip(self._run_recommended_button, _RUN_RECOMMENDED_HELP)
        self._run_recommended_button.clicked.connect(self._on_run_recommended)
        self._customise_button = QPushButton("Customise...", page)
        apply_help_tooltip(self._customise_button, _CUSTOMISE_HELP)
        self._customise_button.clicked.connect(self._on_customise)
        close = QPushButton("Close", page)
        close.clicked.connect(self.close)
        buttons.addStretch(1)
        buttons.addWidget(self._run_recommended_button)
        buttons.addWidget(self._customise_button)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        return page

    # -- the second page: see it, change it, then run it ------------------------------------

    def _build_customise_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        self._customise_heading = QLabel("", page)
        font = self._customise_heading.font()
        font.setBold(True)
        self._customise_heading.setFont(font)
        layout.addWidget(self._customise_heading)

        self._entries_area = QScrollArea(page)
        self._entries_area.setWidgetResizable(True)
        self._entries_area.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self._entries_area, 1)

        self._plan_summary = QLabel("", page)
        self._plan_summary.setWordWrap(True)
        layout.addWidget(self._plan_summary)
        self._conformer_note = QLabel("", page)
        self._conformer_note.setWordWrap(True)
        layout.addWidget(self._conformer_note)
        self._conformer_button = QPushButton("Generate conformers...", page)
        apply_help_tooltip(self._conformer_button, _CONFORMERS_HELP)
        self._conformer_button.clicked.connect(self._on_generate_conformers_clicked)
        layout.addWidget(self._conformer_button)

        buttons = QHBoxLayout()
        back = QPushButton("Back", page)
        back.clicked.connect(self._on_back)
        self._run_button = QPushButton("Run", page)
        self._run_button.setDefault(True)
        apply_help_tooltip(self._run_button, _RUN_HELP)
        self._run_button.clicked.connect(self._on_run)
        close = QPushButton("Close", page)
        close.clicked.connect(self.close)
        buttons.addWidget(back)
        buttons.addStretch(1)
        buttons.addWidget(self._run_button)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        return page

    # -- state --------------------------------------------------------------------------------

    @property
    def goal(self) -> Goal:
        return self._goal

    def select_goal(self, goal_id: str) -> bool:
        """Choose a goal in code (the window's entry points, a test, a drive step)."""
        for row in range(self._goal_list.count()):
            if self._goal_list.item(row).data(Qt.ItemDataRole.UserRole) == goal_id:
                self._goal_list.setCurrentRow(row)
                return True
        return False

    def set_scope(self, mode: str, chosen: set[str] | None = None) -> None:
        self._scope_mode = mode
        if chosen is not None:
            self._scope_chosen = set(chosen)
        self._refresh_scope_labels()
        self._refresh_goal_page()

    def show_outcome(self, text: str) -> None:
        """What the run did on being asked, in the wizard's own words."""
        self._status.setText(text)

    def ticked_ids(self) -> list[str]:
        """What the customise page would run now, in the goal's order."""
        return [
            entry.calculator_id
            for entry in self._goal.entries
            if entry.calculator_id in self._entry_checks and self._entry_checks[entry.calculator_id].isChecked()
        ]

    def current_run(self, *, quick: bool) -> GoalRun:
        """The run as it stands -- the goal's recommended set (`quick`) or the ticks."""
        if quick:
            ids = self._goal.recommended_ids()
            parameters = {e.calculator_id: dict(e.parameters) for e in self._goal.recommended() if e.parameters}
        else:
            ids = tuple(self.ticked_ids())
            parameters = {
                cid: dict(self._chosen_parameters.get(cid) or self._goal.entry(cid).parameters)
                for cid in ids
                if self._chosen_parameters.get(cid) or self._goal.entry(cid).parameters
            }
        return GoalRun(
            goal_id=self._goal.goal_id,
            calculator_ids=tuple(ids),
            parameters=parameters,
            scope_mode=self._scope_mode,
            scope_uuids=tuple(sorted(self._scope_chosen)) if self._scope_mode == SCOPE_CHOSEN else (),
        )

    def scope_molecules(self) -> list:
        molecules = list(self._molecules_of())
        if self._scope_mode == SCOPE_ALL:
            return molecules
        if self._scope_mode == SCOPE_CHOSEN:
            return [m for m in molecules if m.uuid in self._scope_chosen]
        selected = self._selected_uuid_of()
        return [m for m in molecules if m.uuid == selected]

    # -- the first page ------------------------------------------------------------------------

    def _on_goal_changed(self, row: int) -> None:
        self._status.setText("")  # what was said about the last goal's run is not about this one
        if row < 0:
            return
        goal = goal_of(self._goal_list.item(row).data(Qt.ItemDataRole.UserRole))
        if goal is not None:
            self._goal = goal
            self._chosen_parameters.clear()
            self._refresh_goal_page()

    def _refresh_goal_page(self) -> None:
        names = [self._name_of(cid) for cid in self._goal.recommended_ids()]
        self._will_run.setText(
            f"Run recommended runs {len(names)}: " + ", ".join(names) + "."
            + f" That is {self._job_count(self._goal.recommended_ids())} calculation(s) on "
            + f"{len(self.scope_molecules())} molecule(s)."
        )
        self._run_recommended_button.setEnabled(bool(self.scope_molecules()))
        self._customise_button.setEnabled(bool(self.scope_molecules()))

    def _name_of(self, calculator_id: str) -> str:
        definition = self._definition_of(calculator_id)
        return definition.display_name if definition is not None else calculator_id

    def _job_count(self, ids) -> int:
        return len(ids) * len(self.scope_molecules())

    def _refresh_scope_labels(self) -> None:
        total = len(list(self._molecules_of()))
        chosen = len(self._scope_chosen & {m.uuid for m in self._molecules_of()})
        self._scope_combo.setItemText(1, f"Run on: all molecules ({total})")
        self._scope_combo.setItemText(
            2, f"Run on: chosen molecules ({chosen})..." if chosen else "Run on: chosen molecules..."
        )
        index = self._scope_combo.findData(self._scope_mode)
        if index >= 0 and self._scope_combo.currentIndex() != index:
            self._scope_combo.setCurrentIndex(index)

    def _on_scope_activated(self, index: int) -> None:
        mode = str(self._scope_combo.itemData(index))
        if mode == SCOPE_CHOSEN:
            dialog = MoleculeScopeDialog(list(self._molecules_of()), self._scope_chosen, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self._refresh_scope_labels()
                return
            self._scope_chosen = dialog.chosen()
        self.set_scope(mode)

    def _on_run_recommended(self, _checked: bool = False) -> None:
        self._emit(self.current_run(quick=True))

    def _emit(self, run: GoalRun) -> None:
        """Hand a run on. Kept as `last_run` too, for a drive script or a test to read back."""
        self.last_run = run
        self.run_requested.emit(run)

    def _on_customise(self, _checked: bool = False) -> None:
        self._fill_entries()
        self._stack.setCurrentIndex(_PAGE_CUSTOMISE)

    # -- the second page ----------------------------------------------------------------------------

    def _fill_entries(self) -> None:
        self._customise_heading.setText(f"{self._goal.label}: {self._goal.question}")
        self._entry_checks.clear()
        body = QWidget(self._entries_area)
        layout = QVBoxLayout(body)
        for title, entries in (("Recommended", self._goal.recommended()), ("Also available", self._goal.optional())):
            if not entries:
                continue
            heading = QLabel(title, body)
            font = heading.font()
            font.setBold(True)
            heading.setFont(font)
            layout.addWidget(heading)
            for entry in entries:
                layout.addWidget(self._entry_row(entry, body))
        layout.addStretch(1)
        self._entries_area.setWidget(body)
        self._refresh_plan()

    def _entry_row(self, entry, parent: QWidget) -> QWidget:
        definition = self._definition_of(entry.calculator_id)
        row = QWidget(parent)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        check = QCheckBox(self._name_of(entry.calculator_id), row)
        check.setChecked(entry.role == "recommended")
        check.setToolTip(entry.reason)
        apply_help_tooltip(check, _ENTRY_HELP)
        check.toggled.connect(self._on_entry_toggled)
        self._entry_checks[entry.calculator_id] = check
        reason = QLabel(entry.reason, row)
        reason.setStyleSheet("color: #666666;")
        reason.setWordWrap(True)
        row_layout.addWidget(check)
        row_layout.addWidget(reason, 1)
        if definition is not None and definition.parameters:
            settings = QPushButton("Settings...", row)
            apply_help_tooltip(settings, _ENTRY_SETTINGS_HELP)
            settings.setProperty("openchem_calculator_id", entry.calculator_id)
            settings.clicked.connect(self._on_entry_settings)
            row_layout.addWidget(settings)
        return row

    def _on_entry_toggled(self, _checked: bool) -> None:
        self._refresh_plan()

    def _on_entry_settings(self, _checked: bool = False) -> None:
        button = self.sender()
        calculator_id = button.property("openchem_calculator_id") if button is not None else None
        definition = self._definition_of(str(calculator_id)) if calculator_id else None
        if definition is None:
            return
        dialog = CalculatorSettingsDialog(definition, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._chosen_parameters[str(calculator_id)] = dialog.parameters()
            self._refresh_plan()

    def _refresh_plan(self) -> None:
        """What the run would be, said before it starts: its size, what it leaves out, what it needs."""
        ids = self.ticked_ids()
        molecules = self.scope_molecules()
        plan = build_execution_plan(
            molecules=molecules,
            calculator_ids=ids,
            chosen_parameters=self.current_run(quick=False).parameters,
            definition_of=self._definition_of,
            structure_version_of=self._structure_version_of,
            plain_label=self._plain_label,
        )
        text = f"{len(plan.calculator_ids)} calculator(s) on {plan.molecule_count} molecule(s): {plan.job_count} calculation(s)."
        left_out = plan.describe_exclusions()
        if left_out:
            text += " " + left_out
        self._plan_summary.setText(text)
        self._run_button.setEnabled(bool(plan.calculator_ids) and plan.molecule_count > 0)
        self._refresh_conformer_note(plan.calculator_ids, molecules)

    def _refresh_conformer_note(self, ids, molecules) -> None:
        threed = [
            self._name_of(cid)
            for cid in ids
            if (d := self._definition_of(cid)) is not None and needs_conformer(d)
        ]
        lacking = [m for m in molecules if not getattr(m, "conformers", None)]
        if threed and lacking:
            self._conformer_note.setText(
                f"{len(threed)} of these work on a 3D structure ({', '.join(threed[:3])}"
                f"{'...' if len(threed) > 3 else ''}), and {len(lacking)} of {len(molecules)} "
                "molecule(s) have none. Those cells will say so; generate conformers first to fill them."
            )
        else:
            self._conformer_note.setText("")
        show = bool(threed and lacking)
        self._conformer_note.setVisible(show)
        self._conformer_button.setVisible(show and self._on_generate_conformers is not None)

    def _on_generate_conformers_clicked(self, _checked: bool = False) -> None:
        if self._on_generate_conformers is not None:
            self._on_generate_conformers()

    def _on_back(self, _checked: bool = False) -> None:
        self._stack.setCurrentIndex(_PAGE_GOALS)

    def _on_run(self, _checked: bool = False) -> None:
        self._emit(self.current_run(quick=False))
