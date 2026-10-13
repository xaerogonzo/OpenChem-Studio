"""Pair two project molecules as Lewis acid and base, from the quantum-chemistry runs already stored.

`docs/RECIPES_DESIGN.md` section 8, Stage A. Two molecules, one level of theory, and the answer the stored runs support:
the three lines of evidence, each with the run its numbers came from, and for every number that is missing a sentence
saying what would supply it. **NOTHING HERE STARTS ORCA.** A job that is still to do is a row that names it, says what
it would run with and whether this machine could run it now, and opens the Quantum Chemistry panel on the right
molecule; the person runs it there, and this window re-evaluates when it finishes.

**IT RE-EVALUATES, IT DOES NOT SAVE.** Looking at a pairing changes nothing in the project. **Keep** files the answer
with the project, where it is saved with it and read as stale when a molecule is edited or a run it used is deleted.

**A PARTIAL ANSWER IS SAID TO BE ONE.** The sentence above the jobs never makes a pairing with a gap sound complete,
and a gap in the answer is a row and a fact, not a blank.

It is modeless and there is one of it (the window raises the open one). It knows no chemistry: it is handed the lookups
it needs and renders what the recipe evaluation says.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.lewis import ROLE_ACID, ROLE_AUTO, ROLE_BASE
from openchem.domain.lewis_pairing import LEWIS_PAIRING
from openchem.domain.quantum_methods import METHOD_BASIS_PRESETS, SOLVENTS
from openchem.domain.recipe_preview import JobRow, PickChoice, headline, job_rows, pick_choices, short_ids
from openchem.domain.recipe_run import RecipeRun, StepState
from openchem.ui import molecule_combo
from openchem.ui.widgets.fact_view import FactView
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: What the role combo says. The stored value is the calculator's own code; the words are about the FIRST molecule.
_ROLE_LABELS = {
    ROLE_AUTO: "Work it out from the structures",
    ROLE_ACID: "The first molecule is the acid",
    ROLE_BASE: "The first molecule is the base",
}


def _solvent_label(solvent: str) -> str:
    return solvent or "Gas phase"


#: The help topic and anchor every control of this window points at (`docs/USER_GUIDE.md`).
_TOPIC = "lewis-pairing"

#: The first molecule's picker.
_FIRST_HELP = HelpTooltip(
    text=(
        "The first molecule of the pair. Which of the two is the acid is decided from the structures (or by the "
        "role below), never by which one is first: the same two molecules in either place give the same lines."
    ),
    tier=1, help_id="lewis_pairing.first_molecule", topic=_TOPIC, help_anchor=_TOPIC,
)
#: The second molecule's picker.
_SECOND_HELP = HelpTooltip(
    text="The second molecule of the pair. It is read from its own stored runs, never from the first molecule's.",
    tier=1, help_id="lewis_pairing.second_molecule", topic=_TOPIC, help_anchor=_TOPIC,
)
#: The one level of theory every number comes from.
_METHOD_HELP = HelpTooltip(
    text=(
        "The one level of theory every number comes from. Numbers from different levels are different scales, so the "
        "pairing never picks the level that happens to have evidence: a molecule with runs only at another level is "
        "told so, and the answer names the levels it does have.\n\n"
        "Default: the first preset. The presets are the ones the Quantum Chemistry panel offers."
    ),
    tier=2, help_id="lewis_pairing.method_basis", topic=_TOPIC, help_anchor=_TOPIC,
)
#: The solvent the stored runs must have been made in.
_SOLVENT_HELP = HelpTooltip(
    text=(
        "The solvent the stored runs were made in, or gas phase. Like the level of theory it is chosen, not found: "
        "runs in another solvent are not used, and the answer says they exist.\n\nDefault: gas phase."
    ),
    tier=2, help_id="lewis_pairing.solvent", topic=_TOPIC, help_anchor=_TOPIC,
)
#: The role of the first molecule, worked out or declared.
_ROLE_HELP = HelpTooltip(
    text=(
        "Which role the first molecule plays. \"Work it out from the structures\" asks whether each molecule has "
        "somewhere to accept or to donate an electron pair; when both ways round are possible (the common case) BOTH "
        "are reported and neither is ranked.\n\nIt says what the structures allow, not which molecule is the stronger acid."
    ),
    tier=2, help_id="lewis_pairing.role", topic=_TOPIC, help_anchor=_TOPIC,
)
#: A job row's button: open the Quantum Chemistry panel for it.
_OPEN_JOB_HELP = HelpTooltip(
    text=(
        "Open the Quantum Chemistry panel with this molecule selected, to run the job there. Nothing is started "
        "from this window; when the job finishes this one re-evaluates."
    ),
    tier=1, help_id="lewis_pairing.open_job", topic=_TOPIC, help_anchor=_TOPIC,
)
#: The chooser of one stored run among several that could be meant.
_CHOOSE_RUN_HELP = HelpTooltip(
    text=(
        "Several stored runs could be meant and nothing says which, usually because they were made at an earlier "
        "geometry than a run would use now. Choose one by its id; the choice is recorded with the answer."
    ),
    tier=1, help_id="lewis_pairing.choose_run", topic=_TOPIC, help_anchor=_TOPIC,
)
#: The button that uses the chosen run.
_USE_RUN_HELP = HelpTooltip(
    text="Use the chosen run for this molecule and re-evaluate. A run of a different structure cannot be chosen.",
    tier=1, help_id="lewis_pairing.use_run", topic=_TOPIC, help_anchor=_TOPIC,
)
#: The button that forgets every run the person chose.
_FORGET_HELP = HelpTooltip(
    text="Forget the runs you chose and let the evaluation decide again, which uses only current runs.",
    tier=1, help_id="lewis_pairing.forget_choices", topic=_TOPIC, help_anchor=_TOPIC,
)
#: The button that files the answer with the project.
_KEEP_HELP = HelpTooltip(
    text=(
        "File this answer with the project. It is saved with the project and shown in Results; it reads as stale "
        "when a molecule in it is edited or a run it used is deleted, and the numbers it was computed from stay "
        "readable either way.\n\nLooking at a pairing does not keep it."
    ),
    tier=1, help_id="lewis_pairing.keep", topic=_TOPIC, help_anchor=_TOPIC,
)


@dataclass(frozen=True)
class PairingContext:
    """What the window needs to know about the project RIGHT NOW to describe a job that is still to do."""

    names: dict[str, str]
    formal_charges: dict[str, int]
    conformer_counts: dict[str, int]
    orca_configured: bool


@dataclass
class PairingHost:
    """The lookups the dialog is handed. It imports no service and no engine."""

    #: (name, uuid) for every molecule in the open project, in project order.
    molecules: Callable[[], Sequence[tuple[str, str]]]
    #: The molecule selected in the project, or None.
    selected_uuid: Callable[[], str | None]
    #: `RecipeService.evaluate_lewis_pairing`.
    evaluate: Callable[..., RecipeRun]
    context: Callable[[], PairingContext]
    #: File an answer with the project. True when it was kept.
    keep: Callable[[RecipeRun], bool]


class LewisPairingDialog(QDialog):
    #: A job's row asked for its panel: (molecule uuid, calculation type).
    job_requested = Signal(str, str)

    def __init__(self, host: PairingHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lewis acid-base pairing")
        self.setModal(False)
        self.resize(760, 780)
        self._host = host
        #: slot -> calculation type -> run id the person chose.
        self._picks: dict[str, dict[str, str]] = {}
        self._run: RecipeRun | None = None
        self._kept_run_id: str | None = None
        self._rows: tuple[JobRow, ...] = ()
        self._choices: tuple[PickChoice, ...] = ()
        #: Whether the last evaluation had an answer, so the split follows that and not every evaluation.
        self._had_answer: bool | None = None

        self._first = QComboBox(self)
        self._second = QComboBox(self)
        self._method = QComboBox(self)
        for preset in METHOD_BASIS_PRESETS:
            self._method.addItem(preset, preset)
        self._solvent = QComboBox(self)
        for solvent in SOLVENTS:
            self._solvent.addItem(_solvent_label(solvent), solvent)
        self._role = QComboBox(self)
        for code, label in _ROLE_LABELS.items():
            self._role.addItem(label, code)
        for combo, tip in (
            (self._first, _FIRST_HELP), (self._second, _SECOND_HELP), (self._method, _METHOD_HELP),
            (self._solvent, _SOLVENT_HELP), (self._role, _ROLE_HELP),
        ):
            apply_help_tooltip(combo, tip)
            combo.currentIndexChanged.connect(self._on_form_changed)

        form = QFormLayout()
        form.addRow("First molecule:", self._first)
        form.addRow("Second molecule:", self._second)
        form.addRow("Method and basis:", self._method)
        form.addRow("Solvent:", self._solvent)
        form.addRow("Role of the first molecule:", self._role)

        self._headline = QLabel("", self)
        self._headline.setWordWrap(True)
        self._headline.setStyleSheet("font-weight: bold;")

        self._jobs_host = QWidget(self)
        self._jobs_layout = QVBoxLayout(self._jobs_host)
        self._jobs_layout.setContentsMargins(0, 0, 0, 0)

        self._facts = FactView(self)
        #: What is under the jobs: the answer when there is one, and a plain note when there is not. An empty
        #: facts panel with its filter controls is a dead box that reads as a broken one.
        self._no_answer = QLabel("", self)
        self._no_answer.setWordWrap(True)
        self._no_answer.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._answer = QStackedWidget(self)
        self._answer.addWidget(self._no_answer)
        self._answer.addWidget(self._facts)
        self._keep = QPushButton("Keep this answer in the project", self)
        apply_help_tooltip(self._keep, _KEEP_HELP)
        self._keep.clicked.connect(self._on_keep_clicked)
        self._keep_note = QLabel("", self)
        self._keep_note.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.close)

        bottom = QHBoxLayout()
        bottom.addWidget(self._keep)
        bottom.addWidget(self._keep_note, 1)
        bottom.addWidget(buttons)

        # THE JOBS SCROLL AND THE ANSWER KEEPS ITS ROOM. Four jobs with their requirements are taller than the
        # screen; stacked above the answer they pushed the window to 1052 px and squeezed the one thing the window
        # exists to show. A splitter lets the person trade one against the other.
        jobs_page = QWidget(self)
        jobs_layout = QVBoxLayout(jobs_page)
        jobs_layout.setContentsMargins(0, 0, 0, 0)
        jobs_layout.addWidget(QLabel("Jobs", jobs_page))
        jobs_layout.addWidget(self._jobs_host)
        jobs_layout.addStretch(1)
        self._jobs_scroll = QScrollArea(self)
        self._jobs_scroll.setWidgetResizable(True)
        self._jobs_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._jobs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._jobs_scroll.setWidget(jobs_page)
        self._splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(self._jobs_scroll)
        self._splitter.addWidget(self._answer)
        self._splitter.setSizes([300, 380])

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._headline)
        layout.addWidget(self._splitter, 1)
        layout.addLayout(bottom)

        self._populate_molecules(initial=True)
        self._evaluate()

    # --- the form ----------------------------------------------------------------------------------------------

    def _populate_molecules(self, *, initial: bool = False) -> None:
        """Fill both pickers from the project, keeping each pick by uuid.

        **THE SECOND PICKER NEVER DEFAULTS TO THE FIRST MOLECULE.** A combo that has been given its first item
        selects it, so with one molecule in the project it used to sit on the same molecule as the first and the
        window evaluated a molecule against itself instead of saying a pairing needs two. The second picker is
        left empty until there is another molecule to put in it. Choosing the same molecule in both on purpose is
        still allowed: it is a question (water with water), just not a default.
        """
        molecules = list(self._host.molecules())
        entries = [(name or "(unnamed)", uuid) for name, uuid in molecules]
        uuids = [uuid for _, uuid in molecules]
        # Whether the second pick is still there to keep. A pick that has gone (another project, a deleted molecule)
        # is not "item 0": that is how the second picker ended up on the same molecule as the first.
        second_survives = self._second.currentData() in uuids
        molecule_combo.repopulate(self._first, entries)
        molecule_combo.repopulate(self._second, entries)
        if initial:
            selected = self._host.selected_uuid()
            if selected in uuids:
                self._first.blockSignals(True)
                self._first.setCurrentIndex(self._first.findData(selected))
                self._first.blockSignals(False)
        if initial or not second_survives:
            others = [uuid for uuid in uuids if uuid != self._first.currentData()]
            self._second.blockSignals(True)
            self._second.setCurrentIndex(self._second.findData(others[0]) if others else -1)
            self._second.blockSignals(False)

    def _on_form_changed(self, _index: int = 0) -> None:
        # A choice names a run of one molecule at one level of theory; it means nothing after either changes.
        self._picks.clear()
        self._evaluate()

    def refresh(self) -> None:
        """Re-read the project and evaluate again: a run finished, a molecule was edited, the project changed."""
        self._populate_molecules()
        self._evaluate()

    def select_molecules(self, first_uuid: str | None, second_uuid: str | None) -> None:
        """Put the pair in the form, for a caller that already knows it. Evaluates once."""
        for combo, uuid in ((self._first, first_uuid), (self._second, second_uuid)):
            if uuid is not None:
                index = combo.findData(uuid)
                if index >= 0:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(index)
                    combo.blockSignals(False)
        self._picks.clear()
        self._evaluate()

    def set_parameters(self, *, method_basis: str | None = None, solvent: str | None = None, role: str | None = None) -> None:
        """Set the level of theory and role, for a caller that already knows them. Evaluates once."""
        for combo, value in ((self._method, method_basis), (self._solvent, solvent), (self._role, role)):
            if value is not None:
                index = combo.findData(value)
                if index < 0:
                    raise ValueError(f"{value!r} is not one of the choices")
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)
        self._picks.clear()
        self._evaluate()

    # --- evaluating --------------------------------------------------------------------------------------------

    def _evaluate(self) -> None:
        first, second = self._first.currentData(), self._second.currentData()
        self._clear(self._jobs_layout)
        self._run, self._rows, self._choices = None, (), ()
        if not first or not second:
            self._headline.setText(
                "Add a second molecule to the project to pair it with the first. A pairing needs two."
            )
            self._show_no_answer("No pairing yet.")
            self._sync_keep()
            return
        try:
            run = self._host.evaluate(
                first, second,
                method_basis=self._method.currentData(), solvent=self._solvent.currentData(),
                role=self._role.currentData(), picks=self._picks,
            )
        except ValueError as error:
            self._headline.setText(f"Cannot evaluate: {error}")
            self._show_no_answer("")
            self._sync_keep()
            return
        context = self._host.context()
        self._run = run
        self._rows = job_rows(
            run, LEWIS_PAIRING, names=context.names, formal_charges=context.formal_charges,
            conformer_counts=context.conformer_counts, orca_configured=context.orca_configured,
        )
        self._choices = pick_choices(run, names=context.names)
        self._headline.setText(headline(run))
        choice_for = {(c.slot, c.calc_type): c for c in self._choices}
        for row in self._rows:
            self._jobs_layout.addWidget(self._job_widget(row, choice_for.get((row.slot, row.calc_type))))
        if self._picks:
            forget = QPushButton("Forget my choices", self._jobs_host)
            apply_help_tooltip(forget, _FORGET_HELP)
            forget.clicked.connect(self._on_forget_clicked)
            self._jobs_layout.addWidget(forget)
        if run.result is not None:
            categories = {fact.category for fact in run.result.facts}
            self._facts.set_report(run.result, title="Lewis pairing", expanded=categories)
            self._answer.setCurrentWidget(self._facts)
        else:
            self._show_no_answer("No answer yet: " + self._why_no_answer())
        self._follow_the_answer(run.result is not None)
        self._sync_keep()

    def _follow_the_answer(self, has_answer: bool) -> None:
        """Give the room to what there is to read: the jobs when there is no answer, the answer when there is.

        Only when that CHANGES, so a person who dragged the splitter is not undone by the next re-evaluation.
        """
        if has_answer == self._had_answer:
            return
        self._had_answer = has_answer
        self._splitter.setSizes([300, 380] if has_answer else [560, 120])

    def _show_no_answer(self, text: str) -> None:
        self._no_answer.setText(text)
        self._answer.setCurrentWidget(self._no_answer)

    def _why_no_answer(self) -> str:
        run = self._run
        pair = next((s for s in run.steps if s.step_id == "pair"), None) if run else None
        return pair.reason if pair is not None and pair.reason else "see the jobs above."

    def _sync_keep(self) -> None:
        run = self._run
        can_keep = run is not None and run.result is not None and run.run_id != self._kept_run_id
        self._keep.setEnabled(can_keep)
        if run is None or run.result is None:
            self._keep_note.setText("")
        elif run.run_id == self._kept_run_id:
            self._keep_note.setText(
                "Kept. It is saved with the project, and reads as stale if a molecule in it is edited or a run it "
                "used is deleted."
            )
        else:
            self._keep_note.setText("Not kept. Looking at a pairing does not change the project.")

    # --- rows --------------------------------------------------------------------------------------------------

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _job_widget(self, row: JobRow, choice: PickChoice | None = None) -> QWidget:
        frame = QFrame(self._jobs_host)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        if not row.to_do:
            # A finished job is one line: what it was and which stored run supplied it.
            done = QLabel(f"<b>Done:</b> {html.escape(row.title)} ({html.escape(row.note)})", frame)
            done.setTextFormat(Qt.TextFormat.RichText)
            done.setWordWrap(True)
            layout.addWidget(done)
            return frame
        title = QLabel(f"<b>To do:</b> {html.escape(row.title)}", frame)
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setWordWrap(True)  # a long molecule name must wrap: the pane has no horizontal scroll bar
        layout.addWidget(title)
        note = QLabel(row.note, frame)
        note.setWordWrap(True)
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(note)
        if row.to_do:
            layout.addWidget(self._wrapped(f"It would run with: {row.would_run_with}.", frame))
            ready = [r.what for r in row.requirements if r.ok]
            if ready:
                layout.addWidget(self._wrapped("Ready: " + ", ".join(ready) + ".", frame))
            for requirement in row.requirements:
                if not requirement.ok:
                    layout.addWidget(self._wrapped(f"Missing: {requirement.what}. To fix: {requirement.how_to_fix}.", frame))
            if choice is not None:
                # The choice that would settle this job sits IN the job: it is the thing to act on, and below the
                # fold it was invisible.
                layout.addLayout(self._choice_layout(choice, frame))
            button = QPushButton("Open the Quantum Chemistry panel for this job", frame)
            apply_help_tooltip(button, _OPEN_JOB_HELP)
            button.setProperty("job_step", row.step_id)
            button.clicked.connect(self._on_job_clicked)
            layout.addWidget(button)
        return frame

    @staticmethod
    def _wrapped(text: str, parent: QWidget) -> QLabel:
        label = QLabel(text, parent)
        label.setWordWrap(True)
        return label

    def _choice_layout(self, choice: PickChoice, frame: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        caption = QLabel(f"{choice.what}, newest first:", frame)
        # It must be able to wrap: a label that cannot gives the whole row a minimum width wider than the pane, and
        # the pane grows a horizontal scroll bar where a person is looking for the control.
        caption.setWordWrap(True)
        row.addWidget(caption, 1)
        combo = QComboBox(frame)
        for shown, run_id in zip(short_ids(choice.candidates), choice.candidates):
            combo.addItem(shown, run_id)
        apply_help_tooltip(combo, _CHOOSE_RUN_HELP)
        combo.setProperty("pick_slot", choice.slot)
        combo.setProperty("pick_calc", choice.calc_type)
        use = QPushButton("Use this run", frame)
        apply_help_tooltip(use, _USE_RUN_HELP)
        use.setProperty("pick_slot", choice.slot)
        use.setProperty("pick_calc", choice.calc_type)
        use.clicked.connect(self._on_use_clicked)
        row.addWidget(combo, 1)
        row.addWidget(use)
        return row

    # --- actions -----------------------------------------------------------------------------------------------

    def _on_job_clicked(self) -> None:
        step_id = self.sender().property("job_step")
        for row in self._rows:
            if row.step_id == step_id:
                self.job_requested.emit(row.molecule_uuid, row.calc_type)
                return

    def _on_use_clicked(self) -> None:
        button = self.sender()
        frame = button.parentWidget()
        combo = frame.findChild(QComboBox)  # a job's row holds exactly one chooser
        self.choose_run(button.property("pick_slot"), button.property("pick_calc"), combo.currentData())

    def choose_run(self, slot: str, calc_type: str, run_id: str) -> None:
        """Use `run_id` for the `calc_type` runs of the molecule in `slot`, and evaluate again."""
        self._picks.setdefault(slot, {})[calc_type] = run_id
        self._evaluate()

    def _on_forget_clicked(self) -> None:
        self._picks.clear()
        self._evaluate()

    def _on_keep_clicked(self) -> None:
        run = self._run
        if run is None or run.result is None:
            return
        if self._host.keep(run):
            self._kept_run_id = run.run_id
        else:
            self._keep_note.setText("This answer could not be kept: a molecule in it is no longer in the project.")
            return
        self._sync_keep()

    # --- what a script or a test reads --------------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Everything on screen that matters, as plain data. For the drive harness and the tests."""
        run = self._run
        return {
            "headline": self._headline.text(),
            "status": None if run is None else run.status.value,
            "jobs": [
                {
                    "step": r.step_id, "title": r.title, "state": r.state.value, "note": r.note,
                    "would_run_with": r.would_run_with, "ready": r.ready_to_run,
                    "missing": [q.what for q in r.requirements if not q.ok],
                }
                for r in self._rows
            ],
            "choices": [
                {"slot": c.slot, "calc": c.calc_type, "candidates": list(c.candidates)} for c in self._choices
            ],
            "has_result": run is not None and run.result is not None,
            "result_lines": [] if run is None or run.result is None else list(run.result.matched),
            "keep_enabled": self._keep.isEnabled(),
            "kept": run is not None and run.run_id == self._kept_run_id,
            "first": self._first.currentData(),
            "second": self._second.currentData(),
            "method_basis": self._method.currentData(),
            "solvent": self._solvent.currentData(),
            "role": self._role.currentData(),
        }

    def press_job(self, step_id: str) -> bool:
        """Press the real button of the job row `step_id`. False if that job has none (it is done)."""
        for button in self._jobs_host.findChildren(QPushButton):
            if button.property("job_step") == step_id:
                button.click()
                return True
        return False

    def press_keep(self) -> bool:
        if not self._keep.isEnabled():
            return False
        self._keep.click()
        return True
