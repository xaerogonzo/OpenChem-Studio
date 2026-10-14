"""Define the scores of a project: a formula over numbers the application already computes (`docs/DERIVED_SCORES_DESIGN.md`, slice 3d).

A score is a formula a person writes over approved outputs (each with the unit it must carry), optionally with named constants that carry units of their own, and a
declared unit it must work out to. It is shown everywhere as `<name> (user-defined, unvalidated)`, it is evaluated against the molecule's CURRENT results when it is
read, and it never starts a calculation: a score with an input nobody has calculated says which, and gets its number when that is calculated.

**THE DIALOG KNOWS NO RULES.** It holds a `Draft` (the strings in its fields) and asks `domain.score_editor.check_draft` after every keystroke, which asks the same
`check_score_definition` the service and the project loader ask, so what it says while a person types is what Save and Open will say. A problem is shown with
the field it belongs to marked, and a syntax error points at the place in the formula.

**IT SAVES WHEN ASKED, NOT BEFORE.** Typing changes a draft and nothing else; Save makes or changes the score, and Revert puts the saved one back. Changing which
score is shown while the draft has unsaved changes asks first.

It is modeless and there is one of it (the window raises the open one). It imports no service: it is handed the lookups it needs (`ScoreHost`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.score_constants import MAX_CONSTANTS
from openchem.domain.score_definition import DISPLAY_SUFFIX, MAX_LABEL, MAX_NOTE, MAX_OWNER, ScoreDefinition
from openchem.domain.score_definition_store import KeptEntry
from openchem.domain.score_editor import (
    SHOWN_AS,
    ConstantRow,
    Draft,
    DraftCheck,
    InputRow,
    check_draft,
    output_choices,
    pointer_lines,
    suggest_name,
)
from openchem.domain.score_formula import MAX_CHARACTERS, MAX_INPUTS, FormulaError
from openchem.domain.score_value import ScoreStatus, ScoreValue
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: The help topic and anchor every control of this window points at (`docs/USER_GUIDE.md`).
_TOPIC = "derived-scores"


def _help(help_id: str, text: str, tier: int = 1) -> HelpTooltip:
    return HelpTooltip(text=text, tier=tier, help_id=f"scores.{help_id}", topic=_TOPIC, help_anchor=_TOPIC)


_LIST_HELP = _help(
    "list",
    "The scores defined in this project. Choose one to read or change it. An entry that cannot be used is listed with the reason: one written by a newer "
    "version of the application, or one that is damaged. It is kept exactly as it is and saved back with the project.",
)
_NEW_HELP = _help("new", "Start a new score. Nothing is stored until you press Save.")
_DELETE_HELP = _help(
    "delete",
    "Remove the chosen score from the project. Only the definition goes; the numbers it was read from are results of calculators and stay where they are. "
    "You are asked first.",
)
_NAME_HELP = _help(
    "name",
    f"What you call the score, at most {MAX_LABEL} characters. It is always shown followed by \"{DISPLAY_SUFFIX}\", and that part cannot be removed. The name may "
    "not be close to the name of a calculator or of an output the application provides: a number you defined must not read as one it computes.",
    tier=2,
)
_INPUT_NAME_HELP = _help(
    "input_name",
    f"The name the formula uses for this input: lowercase letters, digits and underscores, starting with a letter, not the name of a function. At most {MAX_INPUTS} "
    "inputs in one score.",
    tier=2,
)
_INPUT_OUTPUT_HELP = _help(
    "input_output",
    "The number this input reads: one of the outputs the application has approved for scores, with its unit. It is read from the molecule's CURRENT results "
    "of the drawing, and a score never calculates anything: if it has not been calculated, the score says so. Two inputs that estimate the same quantity cannot "
    "be used together.",
    tier=2,
)
_REMOVE_INPUT_HELP = _help("remove_input", "Take this input out of the score. A formula that still uses its name will say so.")
_ADD_INPUT_HELP = _help("add_input", "Add an input: a number the application computes, read by name in the formula.")
_CONSTANT_NAME_HELP = _help(
    "constant_name",
    f"The name the formula uses for this constant, under the same rules as an input's name. At most {MAX_CONSTANTS} constants in one score.",
    tier=2,
)
_CONSTANT_VALUE_HELP = _help(
    "constant_value",
    "The constant's value: a plain number, written as in the formula (digits, then a point with digits after it, then an optional exponent: 0.5, not .5 or 5.). Unlike a bare number in the formula, a named constant carries the unit beside it "
    "and is checked strictly.",
    tier=2,
)
_CONSTANT_UNIT_HELP = _help(
    "constant_unit",
    "The constant's unit, written like the others (for example \"Å^2\", \"g/mol\", \"kcal/mol\", \"1\" for none). A threshold written in the wrong unit is refused, "
    "and dividing by a constant with a unit is how to take the logarithm of a quantity that has one.",
    tier=2,
)
_REMOVE_CONSTANT_HELP = _help("remove_constant", "Take this constant out of the score.")
_ADD_CONSTANT_HELP = _help("add_constant", "Add a named constant: a number with a unit that the formula uses by name.")
_FORMULA_HELP = _help(
    "formula",
    f"The formula, at most {MAX_CHARACTERS} characters: numbers, the names above, + - * / and ^ with a whole-number exponent, parentheses, and abs, min, max, clamp, "
    "ramp, sqrt, ln, log10, exp. ramp(x, a, b) is 0 at a, 1 at b and linear between, so ramp(x, bad, good) is a desirability. A bare number takes the unit of what "
    "it is added to or compared with. Nothing in it is run as code.",
    tier=2,
)
_UNIT_HELP = _help(
    "result_unit",
    "The unit the formula is declared to work out to (\"1\" for a plain number). It is CHECKED against what the formula really works out to, never trusted: "
    "adding an area to a mass is refused, and nothing is ever converted. Default: 1.",
    tier=2,
)
_OWNER_HELP = _help("owner", f"Who wrote it, free text, at most {MAX_OWNER} characters. Kept with the score; it changes no number.")
_NOTE_HELP = _help("note", f"A note about the score, at most {MAX_NOTE} characters. Kept with the score; it changes no number.")
_SAVE_HELP = _help(
    "save",
    "Make the score, or save your changes to it. It is checked first; a score that does not check is never stored. The project is then marked as having unsaved changes.",
)
_REVERT_HELP = _help("revert", "Put the saved score back and discard what you have typed since.")


@dataclass
class ScoreHost:
    """The lookups the dialog is handed. It imports no service and no engine."""

    #: Whether there is a project to hold scores.
    has_project: Callable[[], bool]
    #: The project's definitions, in the order they were made.
    scores: Callable[[], Sequence[ScoreDefinition]]
    #: Entries of the project's block that this build cannot use (newer, damaged).
    kept: Callable[[], Sequence[KeptEntry]]
    #: Names a label may not be close to (the registry's; the approved outputs' are added by the check).
    reserved_names: Callable[[], Sequence[str]]
    #: The molecule selected in the project, as `(name, uuid)`, or None.
    molecule: Callable[[], tuple[str, str] | None]
    #: `ScoreService.preview`: the value a definition would have for a molecule, by uuid.
    preview: Callable[[ScoreDefinition, str], ScoreValue | None]
    #: `ScoreService.create(**fields)` and `update(score_id, **fields)`; each raises `FormulaError` for a definition that does not check.
    create: Callable[..., ScoreDefinition]
    update: Callable[..., ScoreDefinition]
    remove: Callable[[str], bool]


class _Row(QWidget):
    """A row of the inputs or the constants: some line edits or a combo, and a button that removes it."""

    changed = Signal()
    removed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

    def _remove_button(self, tip: HelpTooltip) -> QPushButton:
        button = QPushButton("Remove", self)
        apply_help_tooltip(button, tip)
        button.clicked.connect(lambda _checked=False: self.removed.emit(self))
        return button


class _InputRowWidget(_Row):
    def __init__(self, row: InputRow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.name = QLineEdit(row.name, self)
        self.name.setPlaceholderText("name")
        self.name.setMinimumWidth(_NAME_WIDTH)
        self.name.setMaximumWidth(160)
        self.name.setObjectName("scoreInputName")
        apply_help_tooltip(self.name, _INPUT_NAME_HELP)
        self.output = QComboBox(self)
        self.output.setObjectName("scoreInputOutput")
        for choice in output_choices():
            self.output.addItem(choice.text, choice.output_id)
        # Free to shrink to the window: the longest entry is ninety characters, and left to size the combo it made the whole form scroll sideways. The popup
        # is as wide as its longest entry, so nothing is cut there.
        self.output.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.output.setMinimumContentsLength(24)
        widest = max((self.output.fontMetrics().horizontalAdvance(self.output.itemText(i)) for i in range(self.output.count())), default=0)
        self.output.view().setMinimumWidth(widest + 40)
        index = self.output.findData(row.output_id)
        if index >= 0:
            self.output.setCurrentIndex(index)
        elif row.output_id:
            # An output that is no longer approved: shown as it is, so the check can say so, rather than silently replaced by the first entry.
            self.output.insertItem(0, f"{row.output_id} (not approved)", row.output_id)
            self.output.setCurrentIndex(0)
        apply_help_tooltip(self.output, _INPUT_OUTPUT_HELP)
        self.remove_button = self._remove_button(_REMOVE_INPUT_HELP)
        self.remove_button.setObjectName("scoreRemoveInput")
        self._layout.addWidget(self.name)
        self._layout.addWidget(self.output, 1)
        self._layout.addWidget(self.remove_button)
        self.name.textChanged.connect(lambda _text: self.changed.emit())
        self.output.currentIndexChanged.connect(lambda _index: self.changed.emit())

    def row(self) -> InputRow:
        return InputRow(self.name.text(), self.output.currentData() or "")


class _ConstantRowWidget(_Row):
    def __init__(self, row: ConstantRow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.name = QLineEdit(row.name, self)
        self.name.setPlaceholderText("name")
        self.name.setMinimumWidth(_NAME_WIDTH)
        self.name.setMaximumWidth(160)
        self.name.setObjectName("scoreConstantName")
        apply_help_tooltip(self.name, _CONSTANT_NAME_HELP)
        self.value = QLineEdit(row.value, self)
        self.value.setPlaceholderText("value")
        self.value.setMinimumWidth(_VALUE_WIDTH)
        self.value.setMaximumWidth(120)
        self.value.setObjectName("scoreConstantValue")
        apply_help_tooltip(self.value, _CONSTANT_VALUE_HELP)
        self.unit = QLineEdit(row.unit, self)
        self.unit.setPlaceholderText("unit")
        self.unit.setMinimumWidth(_VALUE_WIDTH)
        self.unit.setMaximumWidth(140)
        self.unit.setObjectName("scoreConstantUnit")
        apply_help_tooltip(self.unit, _CONSTANT_UNIT_HELP)
        self.remove_button = self._remove_button(_REMOVE_CONSTANT_HELP)
        self.remove_button.setObjectName("scoreRemoveConstant")
        for widget in (self.name, self.value, self.unit):
            self._layout.addWidget(widget)
            widget.textChanged.connect(lambda _text: self.changed.emit())
        self._layout.addStretch(1)
        self._layout.addWidget(self.remove_button)

    def row(self) -> ConstantRow:
        return ConstantRow(self.name.text(), self.value.text(), self.unit.text())


#: The least width of an input's or a constant's name, value and unit boxes: a three-letter name must not be a sliver beside a picker that takes the rest.
_NAME_WIDTH = 90
_VALUE_WIDTH = 80

#: What each field of the dialog is called in the one-line message, so a problem reads "Formula: ..." and the person knows where to look.
_FIELD_NAMES = {
    "label": "Name", "formula": "Formula", "inputs": "Inputs", "constants": "Constants", "unit": "Unit", "owner": "Owner", "note": "Note",
}

#: Green and red that read on a light and on a dark window alike.
_OK_COLOUR = "#2e7d32"
_BAD_COLOUR = "#c0392b"


class ScoreDialog(QDialog):
    def __init__(self, host: ScoreHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Derived scores")
        self.setModal(False)
        self.resize(940, 760)
        self._host = host
        #: The id of the score the form shows, or None for a new one.
        self._current_id: str | None = None
        #: The draft as it was last loaded or saved; what "unsaved changes" is measured against.
        self._saved: Draft = Draft()
        self._loading = False
        self._input_rows: list[_InputRowWidget] = []
        self._constant_rows: list[_ConstantRowWidget] = []
        self._last_check: DraftCheck = check_draft(Draft())
        #: The column the caret under the formula is at, or None when it is not shown.
        self._caret: int | None = None

        # --- the list ---
        self._list = QListWidget(self)
        self._list.setObjectName("scoreList")
        # "<name> (user-defined, unvalidated)" is long: it elides (the list's default; the tooltip has all of it) rather than scrolling the list sideways.
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        apply_help_tooltip(self._list, _LIST_HELP)
        self._list.currentItemChanged.connect(self._on_list_changed)
        self._new = QPushButton("New score", self)
        self._new.setObjectName("scoreNew")
        apply_help_tooltip(self._new, _NEW_HELP)
        self._new.clicked.connect(self._on_new)
        self._delete = QPushButton("Delete", self)
        self._delete.setObjectName("scoreDelete")
        apply_help_tooltip(self._delete, _DELETE_HELP)
        self._delete.clicked.connect(self._on_delete)
        list_buttons = QHBoxLayout()
        list_buttons.addWidget(self._new)
        list_buttons.addWidget(self._delete)
        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Scores in this project", left))
        left_layout.addWidget(self._list, 1)
        left_layout.addLayout(list_buttons)

        # --- the form ---
        self._label = QLineEdit(self)
        self._label.setObjectName("scoreLabel")
        self._label.setPlaceholderText("What you call it")
        apply_help_tooltip(self._label, _NAME_HELP)
        self._shown_as = QLabel("", self)
        self._shown_as.setWordWrap(True)
        self._shown_as.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # The rows live in frames so a problem with them can be drawn as ONE outline round the group: a border set on a combo box replaces the style's own
        # drawing and squashes its arrow.
        self._inputs_host = QFrame(self)
        self._inputs_host.setObjectName("scoreInputs")
        self._inputs_layout = QVBoxLayout(self._inputs_host)
        self._inputs_layout.setContentsMargins(4, 4, 4, 4)
        self._add_input = QPushButton("Add an input", self)
        self._add_input.setObjectName("scoreAddInput")
        apply_help_tooltip(self._add_input, _ADD_INPUT_HELP)
        self._add_input.clicked.connect(self._on_add_input)
        self._add_input.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        self._constants_host = QFrame(self)
        self._constants_host.setObjectName("scoreConstants")
        self._constants_layout = QVBoxLayout(self._constants_host)
        self._constants_layout.setContentsMargins(4, 4, 4, 4)
        self._add_constant = QPushButton("Add a constant", self)
        self._add_constant.setObjectName("scoreAddConstant")
        apply_help_tooltip(self._add_constant, _ADD_CONSTANT_HELP)
        self._add_constant.clicked.connect(self._on_add_constant)
        self._add_constant.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        self._formula = QLineEdit(self)
        self._formula.setObjectName("scoreFormula")
        self._formula.setPlaceholderText("for example  ramp(psa, 140, 60) * ramp(logp, 5, 2)")
        self._formula.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        apply_help_tooltip(self._formula, _FORMULA_HELP)
        self._pointer = QLabel("", self)
        self._pointer.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._pointer.setStyleSheet(f"color: {_BAD_COLOUR};")
        self._unit = QLineEdit("1", self)
        self._unit.setObjectName("scoreUnit")
        self._unit.setMaximumWidth(160)
        apply_help_tooltip(self._unit, _UNIT_HELP)
        self._works_out = QLabel("", self)
        unit_row = QHBoxLayout()
        unit_row.addWidget(self._unit)
        unit_row.addWidget(self._works_out, 1)

        self._owner = QLineEdit(self)
        self._owner.setObjectName("scoreOwner")
        apply_help_tooltip(self._owner, _OWNER_HELP)
        self._note = QPlainTextEdit(self)
        self._note.setObjectName("scoreNote")
        self._note.setMaximumHeight(64)
        apply_help_tooltip(self._note, _NOTE_HELP)

        self._message = QLabel("", self)
        self._message.setWordWrap(True)
        self._message.setObjectName("scoreMessage")
        self._preview = QLabel("", self)
        self._preview.setWordWrap(True)
        self._preview.setObjectName("scorePreview")
        self._save = QPushButton("Save", self)
        self._save.setObjectName("scoreSave")
        apply_help_tooltip(self._save, _SAVE_HELP)
        self._save.clicked.connect(self._on_save)
        self._revert = QPushButton("Revert", self)
        self._revert.setObjectName("scoreRevert")
        apply_help_tooltip(self._revert, _REVERT_HELP)
        self._revert.clicked.connect(self._on_revert)

        form = QFormLayout()
        self._form = form
        form.addRow("Name:", self._label)
        form.addRow("", self._shown_as)
        form.addRow("Reads:", self._inputs_host)
        form.addRow("", self._add_input)
        form.addRow("Constants:", self._constants_host)
        form.addRow("", self._add_constant)
        form.addRow("Formula:", self._formula)
        form.addRow("", self._pointer)
        form.addRow("Unit it works out to:", unit_row)
        form.addRow("Owner:", self._owner)
        form.addRow("Note:", self._note)
        form_holder = QWidget(self)
        form_holder.setLayout(form)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(form_holder)

        actions = QHBoxLayout()
        actions.addWidget(self._save)
        actions.addWidget(self._revert)
        actions.addStretch(1)
        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(scroll, 1)
        right_layout.addWidget(self._message)
        right_layout.addWidget(self._preview)
        right_layout.addLayout(actions)

        self._empty = QLabel("", self)
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([320, 620])

        about = QLabel(
            "A score is a formula you write over numbers the application already computes. It is shown as \"<name> (user-defined, unvalidated)\", it is read from the "
            "molecule's current results and starts no calculation, and nothing has checked it against measurements: it is not a prediction. A bare number in the formula "
            "takes the unit of what it is added to or compared with; a named constant carries its own unit and is checked strictly.",
            self,
        )
        about.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(self._empty)
        layout.addWidget(splitter, 1)
        layout.addWidget(about)
        layout.addWidget(buttons)
        self._splitter = splitter

        for edit in (self._label, self._formula, self._unit, self._owner):
            edit.textChanged.connect(self._on_edited)
        self._note.textChanged.connect(self._on_edited)

        self.refresh()

    # --- the draft -----------------------------------------------------------------------------------------------------------------

    def draft(self) -> Draft:
        """What the fields hold now."""
        return Draft(
            label=self._label.text(),
            formula=self._formula.text(),
            result_unit=self._unit.text(),
            inputs=tuple(row.row() for row in self._input_rows),
            constants=tuple(row.row() for row in self._constant_rows),
            owner=self._owner.text(),
            note=self._note.toPlainText(),
        )

    def set_draft(self, draft: Draft, *, saved: bool = False) -> None:
        """Put `draft` in the fields. `saved` says it IS the saved state (loading a score), so it is not 'unsaved changes'."""
        self._loading = True
        try:
            self._label.setText(draft.label)
            self._formula.setText(draft.formula)
            self._unit.setText(draft.result_unit)
            self._owner.setText(draft.owner)
            self._note.setPlainText(draft.note)
            self._clear_rows(self._input_rows, self._inputs_layout)
            self._clear_rows(self._constant_rows, self._constants_layout)
            for row in draft.inputs:
                self._append_input(row)
            for row in draft.constants:
                self._append_constant(row)
            if saved:
                self._saved = draft
        finally:
            self._loading = False
        self._recheck()

    @property
    def dirty(self) -> bool:
        return self.draft() != self._saved

    def _clear_rows(self, rows: list, layout: QVBoxLayout) -> None:
        for row in rows:
            layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        rows.clear()

    def _append_input(self, row: InputRow) -> _InputRowWidget:
        widget = _InputRowWidget(row, self._inputs_host)
        widget.changed.connect(self._on_edited)
        widget.removed.connect(self._on_remove_input)
        self._input_rows.append(widget)
        self._inputs_layout.addWidget(widget)
        return widget

    def _append_constant(self, row: ConstantRow) -> _ConstantRowWidget:
        widget = _ConstantRowWidget(row, self._constants_host)
        widget.changed.connect(self._on_edited)
        widget.removed.connect(self._on_remove_constant)
        self._constant_rows.append(widget)
        self._constants_layout.addWidget(widget)
        return widget

    def add_input(self, name: str = "", output_id: str = "") -> _InputRowWidget:
        """Add an input row, as the Add button does: with a suggested name for the first output when none is given."""
        if not output_id:
            output_id = output_choices()[0].output_id
        if not name:
            name = suggest_name(output_id, [row.name.text() for row in self._input_rows] + [row.name.text() for row in self._constant_rows])
        widget = self._append_input(InputRow(name, output_id))
        self._recheck()
        return widget

    def add_constant(self, name: str = "", value: str = "", unit: str = "") -> _ConstantRowWidget:
        widget = self._append_constant(ConstantRow(name, value, unit))
        self._recheck()
        return widget

    # --- the form's events ------------------------------------------------------------------------------------------------------------

    def _on_edited(self, *_args) -> None:
        if not self._loading:
            self._recheck()

    def _on_add_input(self, _checked: bool = False) -> None:
        if len(self._input_rows) >= MAX_INPUTS:
            self._message.setText(f"A score reads at most {MAX_INPUTS} inputs.")
            return
        self.add_input()

    def _on_add_constant(self, _checked: bool = False) -> None:
        if len(self._constant_rows) >= MAX_CONSTANTS:
            self._message.setText(f"A score has at most {MAX_CONSTANTS} constants.")
            return
        self.add_constant()

    def _on_remove_input(self, row) -> None:
        self._input_rows.remove(row)
        self._inputs_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._recheck()

    def _on_remove_constant(self, row) -> None:
        self._constant_rows.remove(row)
        self._constants_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._recheck()

    # --- checking and saying ------------------------------------------------------------------------------------------------------------

    def check_result(self) -> DraftCheck:
        """What is wrong with the draft now, or that nothing is."""
        return self._last_check

    def _recheck(self) -> None:
        draft = self.draft()
        result = check_draft(draft, reserved_names=self._host.reserved_names())
        self._last_check = result
        self._shown_as.setText(f"{SHOWN_AS} {draft.label.strip() or '(no name yet)'} {DISPLAY_SUFFIX}")
        if result.ok:
            self._message.setText(result.message)
            self._message.setStyleSheet(f"color: {_OK_COLOUR};")
        else:
            where = _FIELD_NAMES.get(result.where, "")
            self._message.setText(f"{where}: {result.message}" if where else result.message)
            self._message.setStyleSheet(f"color: {_BAD_COLOUR};" if result.problem else "")
        pointing = result.position is not None and result.where == "formula"
        self._pointer.setText(pointer_lines(draft.formula, result.position) if pointing else "")
        self._caret = len(self._pointer.text().rpartition("\n")[2]) - 1 if pointing else None
        # Its row takes room even when empty, so it is only there when it points at something.
        self._form.setRowVisible(self._pointer, pointing)
        self._works_out.setText(f"The formula works out to {result.worked_out}." if result.worked_out else "")
        self._mark_fields(result)
        self._show_preview(result, draft)
        self._sync_buttons(result)

    def _mark_fields(self, result: DraftCheck) -> None:
        marked = {"label": self._label, "formula": self._formula, "unit": self._unit, "owner": self._owner}
        for where, edit in marked.items():
            edit.setStyleSheet(f"border: 1px solid {_BAD_COLOUR};" if result.where == where and not result.ok else "")
        self._inputs_host.setStyleSheet(f"QFrame#scoreInputs {{ border: 1px solid {_BAD_COLOUR}; }}" if result.where == "inputs" else "")
        self._constants_host.setStyleSheet(f"QFrame#scoreConstants {{ border: 1px solid {_BAD_COLOUR}; }}" if result.where == "constants" else "")

    def _show_preview(self, result: DraftCheck, draft: Draft) -> None:
        self._preview.setText("")
        if not result.ok:
            return
        molecule = self._host.molecule()
        if molecule is None:
            self._preview.setText("Select a molecule to see what this score gives for it.")
            return
        name, uuid = molecule
        try:
            definition = draft.to_definition()
            value = self._host.preview(definition, uuid)
        except FormulaError:
            self._preview.setText("")
            return
        if value is None:
            self._preview.setText("")
        elif value.status is ScoreStatus.VALUE:
            unit = "" if definition.result_unit == "1" else f" {definition.result_unit}"
            self._preview.setText(f"For {name or 'the selected molecule'}: {value.value:.4g}{unit}")
        else:
            self._preview.setText(f"For {name or 'the selected molecule'}: no value. {value.reason}")

    def _sync_buttons(self, result: DraftCheck) -> None:
        has_project = self._host.has_project()
        dirty = self.dirty
        self._save.setEnabled(has_project and result.ok and dirty)
        self._revert.setEnabled(has_project and dirty)
        self._delete.setEnabled(has_project and self._current_id is not None)
        self._new.setEnabled(has_project)
        self._add_input.setEnabled(has_project)
        self._add_constant.setEnabled(has_project)

    # --- the list ---------------------------------------------------------------------------------------------------------------------------

    def refresh(self) -> None:
        """Re-read the project: the list, the form (when it has no unsaved changes) and the preview."""
        has_project = self._host.has_project()
        self._empty.setVisible(not has_project)
        self._splitter.setEnabled(has_project)
        self._empty.setText("Open or create a project to define scores in it." if not has_project else "")
        keep = self._current_id
        self._loading = True
        try:
            self._list.clear()
            for definition in self._host.scores():
                item = QListWidgetItem(definition.display_label)
                item.setToolTip(definition.display_label)
                item.setData(Qt.ItemDataRole.UserRole, definition.score_id)
                self._list.addItem(item)
            for entry in self._host.kept():
                item = QListWidgetItem(f"{entry.label or entry.score_id or 'An entry'}: {entry.reason}")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setToolTip(f"This entry cannot be used by this version and is kept as it is. {entry.reason}")
                self._list.addItem(item)
            if keep is not None:
                for row in range(self._list.count()):
                    if self._list.item(row).data(Qt.ItemDataRole.UserRole) == keep:
                        self._list.setCurrentRow(row)
                        break
        finally:
            self._loading = False
        ids = {definition.score_id: definition for definition in self._host.scores()}
        if keep is not None and keep not in ids:
            # The score being shown was removed elsewhere.
            self._current_id = None
            self.set_draft(Draft(), saved=True)
        elif keep is not None and not self.dirty:
            self.set_draft(Draft.from_definition(ids[keep]), saved=True)
        else:
            self._recheck()

    def refresh_preview(self) -> None:
        """Read the selected molecule's value again, and nothing else: the form, the list and the focus are left alone. For results arriving while it is open."""
        if self._host.has_project():
            self._recheck()

    def _on_list_changed(self, current, _previous) -> None:
        if self._loading or current is None:
            return
        score_id = current.data(Qt.ItemDataRole.UserRole)
        if score_id is None or score_id == self._current_id:
            return
        if not self._confirm_discard():
            self._loading = True
            try:
                self._select_row_of(self._current_id)
            finally:
                self._loading = False
            return
        self.show_score(score_id)

    def _select_row_of(self, score_id: str | None) -> None:
        for row in range(self._list.count()):
            if self._list.item(row).data(Qt.ItemDataRole.UserRole) == score_id:
                self._list.setCurrentRow(row)
                return
        self._list.setCurrentRow(-1)

    def show_score(self, score_id: str) -> None:
        """Load a saved score into the form, as choosing it in the list does (without asking about unsaved changes: the caller has)."""
        definition = next((d for d in self._host.scores() if d.score_id == score_id), None)
        if definition is None:
            return
        self._current_id = score_id
        self._loading = True
        try:
            self._select_row_of(score_id)
        finally:
            self._loading = False
        self.set_draft(Draft.from_definition(definition), saved=True)

    def current_score_id(self) -> str | None:
        return self._current_id

    def _confirm_discard(self) -> bool:
        """True when it is fine to replace the form: nothing unsaved, or the person said to discard it. A saved score emptied of everything is an unsaved change like any other."""
        if not self.dirty:
            return True
        answer = QMessageBox.question(
            self, "Unsaved changes", "The score you were editing has changes that are not saved. Discard them?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    # --- the buttons ---------------------------------------------------------------------------------------------------------------------------

    def _on_new(self, _checked: bool = False) -> None:
        if not self._confirm_discard():
            return
        self.start_new()

    def start_new(self) -> None:
        """An empty form for a new score."""
        self._current_id = None
        self._loading = True
        try:
            self._list.setCurrentRow(-1)
        finally:
            self._loading = False
        self.set_draft(Draft(), saved=True)
        self._label.setFocus()

    def _on_revert(self, _checked: bool = False) -> None:
        self.set_draft(self._saved, saved=True)

    def _on_delete(self, _checked: bool = False) -> None:
        if self._current_id is None:
            return
        answer = QMessageBox.question(
            self, "Delete score", "Delete this score from the project? The numbers it was read from are not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.delete_current()

    def delete_current(self) -> None:
        """Remove the shown score, without asking (the Delete button asks first)."""
        if self._current_id is None:
            return
        self._host.remove(self._current_id)
        self._current_id = None
        self.refresh()
        self.set_draft(Draft(), saved=True)

    def _on_save(self, _checked: bool = False) -> None:
        self.save()

    def save(self) -> ScoreDefinition | None:
        """Make or change the score the form holds, as Save does. None when it did not check or could not be stored (the message says why)."""
        draft = self.draft()
        result = check_draft(draft, reserved_names=self._host.reserved_names())
        if not result.ok:
            self._recheck()
            return None
        definition = draft.to_definition()
        fields = dict(
            label=definition.label, formula=definition.formula, result_unit=definition.result_unit, inputs=list(definition.inputs),
            constants=list(definition.constants), owner=definition.owner, note=definition.note,
        )
        try:
            if self._current_id is None:
                made = self._host.create(**fields)
            else:
                made = self._host.update(self._current_id, **fields)
        except (FormulaError, ValueError, KeyError) as exc:
            text = exc.message if isinstance(exc, FormulaError) else str(exc)
            self._message.setText(text)
            self._message.setStyleSheet(f"color: {_BAD_COLOUR};")
            return None
        self._current_id = made.score_id
        self.refresh()
        self.show_score(made.score_id)
        return made

    # --- what a script or a test reads ----------------------------------------------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Everything the window shows, as plain values."""
        return {
            "scores": [self._list.item(i).text() for i in range(self._list.count())],
            "current": self._current_id,
            "draft": self.draft(),
            "dirty": self.dirty,
            "ok": self._last_check.ok,
            "problem": self._last_check.problem,
            "where": self._last_check.where,
            "position": self._last_check.position,
            "message": self._message.text(),
            "works_out": self._last_check.worked_out,
            "pointer": self._pointer.text(),
            "caret": self._caret,
            "shown_as": self._shown_as.text(),
            "preview": self._preview.text(),
            "save_enabled": self._save.isEnabled(),
            "revert_enabled": self._revert.isEnabled(),
            "delete_enabled": self._delete.isEnabled(),
        }
