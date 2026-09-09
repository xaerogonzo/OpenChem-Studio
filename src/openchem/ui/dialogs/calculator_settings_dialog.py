from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.calculator import CalculatorDefinition, CalculatorParameter
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip


#: ONE CONTRACT PER KIND, NOT PER CALCULATOR. `help_id` names a
#: DEFINITION, and "a numeric setting for this calculator" means the same
#: thing on every one of the sixty-odd calculators that has one --
#: `instance_path` is what tells the renderings apart. The same call the
#: sixty batch tick boxes and the thirty-six dock title-bar buttons make.
#:
#: `float` and `int` SHARE an id deliberately: a number is a number, and
#: splitting them would be one concept wearing two ids, which
#: `test_one_concept_is_not_split_across_many_help_ids` refuses.
_PARAMETER_HELP: dict[str, HelpTooltip] = {
    "number": HelpTooltip(
        text=(
            "Sets this calculator's numeric setting for the next run.\n\n"
            "The permitted range comes from the calculator itself, so a "
            "value outside it cannot be entered rather than being accepted "
            "and refused later. Changing it changes the RESULT, not the "
            "display: a result computed at one value and one computed at "
            "another are different calculations, and each is recorded with "
            "the settings it ran under."
        ),
        tier=2,
        help_id="calculator.parameter_number",
        topic="properties",
    ),
    "choice": HelpTooltip(
        text=(
            "Picks which variant of this calculation to run.\n\n"
            "The options come from the calculator, and they are genuine "
            "alternatives rather than display settings -- two of them "
            "answer the same question by different methods and can "
            "disagree. What is stored with the result is a stable code, "
            "so rewording an option here never changes which stored "
            "results match it."
        ),
        tier=2,
        help_id="calculator.parameter_choice",
        topic="properties",
    ),
    "bool": HelpTooltip(
        text=(
            "Turns this calculator's option on or off for the next run.\n\n"
            "It affects what is COMPUTED, not what is shown, so a result "
            "already in the table was computed under whatever this was "
            "set to at the time."
        ),
        tier=2,
        help_id="calculator.parameter_flag",
        topic="properties",
    ),
    "text": HelpTooltip(
        text=(
            "A free-text value for this calculator -- a SMARTS pattern, a "
            "date, or a list, depending on which one asked.\n\n"
            "It is not checked here. The calculator parses it and reports "
            "a failed result naming what it could not read, because this "
            "box has no way to know which of several formats the "
            "calculator wants."
        ),
        tier=2,
        help_id="calculator.parameter_text",
        topic="properties",
    ),
}

#: The combo half of a `"smiles"` parameter: pick a molecule the
#: project already holds. Absent when there is nothing to pick from.
_SMILES_FROM_PROJECT_HELP = HelpTooltip(
    text=(
        "Choose the partner from the molecules already open in this "
        "project, or the last entry to type one instead.\n\n"
        "What is stored is the molecule's SMILES rather than a reference "
        "to it, so the result stays meaningful in another project and can "
        "be a column in a batch table."
    ),
    tier=1,
    help_id="calculator.smiles_from_project",
    topic="properties",
)

#: Which contract a kind takes. `float` and `int` share one, and
#: `smiles` takes none here because `_SmilesChooser` documents the two
#: controls it builds.
_HELP_KIND = {
    "float": "number",
    "int": "number",
    "choice": "choice",
    "bool": "bool",
    "text": "text",
}

#: The line-edit half: type a SMILES. The ONLY control when no
#: molecule in the project carries a usable one.
_SMILES_TYPED_HELP = HelpTooltip(
    text=(
        "Type the molecule as SMILES -- N for ammonia, O for water, "
        "c1ccncc1 for pyridine.\n\n"
        "It is stored as text and never as a reference to a molecule in "
        "this project, which is what keeps the result replayable "
        "elsewhere. Nothing is checked as you type: a string that cannot "
        "be read comes back as a failed result naming it, because "
        "deciding what is a valid structure belongs to the chemistry "
        "engine and not to this box."
    ),
    tier=2,
    help_id="calculator.smiles_typed",
    topic="properties",
)

@dataclass(frozen=True)
class MoleculeChoice:
    """One molecule a `"smiles"` parameter may be filled from.

    A named pair rather than `tuple[str, str]`, because a bare pair invites
    `(smiles, label)` transposition -- which produces a picker labelled
    with SMILES and valued with names, a bug that looks perfectly fine in
    a screenshot.
    """

    label: str
    smiles: str


#: The entry that means "I will type one". A sentinel in the WIDGET and
#: never a parameter value: encoded as a real choice it can persist into
#: provenance through a cancellation or a path bug, and
#: `partner_smiles = "Type a SMILES..."` would then be parsed, refused and
#: reported as though somebody had typed it.
_TYPE_IT = "Type a SMILES..."


class _SmilesChooser(QWidget):
    """A SMILES value, chosen from the project or typed.

    ONE CLASS, TWO MODES. With choices it is a combo box of the project's
    molecules plus a final "type one" entry, above a line edit enabled
    only for that entry -- so precedence is a MODE rather than a race
    between two widgets. With no choices it is the line edit alone, which
    is exactly what this parameter was before the picker existed.

    **IT PARSES NOTHING.** `tests/test_layering.py` forbids a `ui/` module
    importing RDKit, which settles the question rather than leaving it to
    taste: the chem layer stays authoritative for validity and canonical
    form, and a "looks like SMILES" regex here would be a second, worse
    parser that rejects valid strings.
    """

    def __init__(
        self,
        molecules: Sequence[MoleculeChoice],
        default: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._combo: QComboBox | None = None
        self._edit = QLineEdit(self)
        self._edit.setPlaceholderText("SMILES, e.g. N for ammonia")
        apply_help_tooltip(self._edit, _SMILES_TYPED_HELP)
        self._edit.setText(str(default or ""))

        if molecules:
            self._combo = QComboBox(self)
            for choice in molecules:
                self._combo.addItem(choice.label, choice.smiles)
            self._combo.addItem(_TYPE_IT, None)
            position = self._combo.findData(str(default or ""))
            self._combo.setCurrentIndex(position if position >= 0 else 0)
            apply_help_tooltip(self._combo, _SMILES_FROM_PROJECT_HELP)
            self._combo.currentIndexChanged.connect(self._on_mode_changed)
            layout.addWidget(self._combo)
        layout.addWidget(self._edit)
        self._on_mode_changed()

    def _typing(self) -> bool:
        return self._combo is None or self._combo.currentData() is None

    def _on_mode_changed(self, _index: int = 0) -> None:
        self._edit.setEnabled(self._typing())

    def value(self) -> str:
        """The SMILES, never the label and never the sentinel."""
        if self._typing():
            return self._edit.text().strip()
        return str(self._combo.currentData())

    def set_value(self, smiles: str) -> None:
        if self._combo is not None:
            position = self._combo.findData(smiles)
            if position >= 0:
                self._combo.setCurrentIndex(position)
                self._on_mode_changed()
                return
            self._combo.setCurrentIndex(self._combo.count() - 1)
        self._edit.setText(smiles)
        self._on_mode_changed()


class CalculatorSettingsDialog(QDialog):
    """Builds its form FROM `CalculatorDefinition.parameters` -- one Qt
    widget per `CalculatorParameter` -- rather than every calculator
    hand-building its own settings dialog. A calculator with zero
    parameters (LogP, Molar Refractivity, pKa today) still shows this
    dialog with just a description and OK/Cancel, so "Open [Calculator]..."
    always means the same thing regardless of which calculator fired.
    """

    def __init__(
        self,
        definition: CalculatorDefinition,
        parent: QWidget | None = None,
        *,
        molecules: Sequence[MoleculeChoice] = (),
    ) -> None:
        # KEYWORD-ONLY WITH AN EMPTY DEFAULT, so every existing caller
        # is untouched -- including `ui/dialogs/inventory.py`, which
        # builds this dialog from a definition alone. A `"smiles"`
        # parameter with no molecules supplied degrades to the free-text
        # box this parameter has always been.
        super().__init__(parent)
        self._molecules = list(molecules)
        self.setWindowTitle(definition.display_name)
        self._widgets: dict[str, QWidget] = {}
        self._parameters = definition.parameters

        layout = QVBoxLayout(self)
        if definition.description:
            description_label = QLabel(definition.description, self)
            description_label.setWordWrap(True)
            layout.addWidget(description_label)

        form = QFormLayout()
        for parameter in definition.parameters:
            widget = self._build_widget(parameter)
            # Applied HERE rather than in each branch of
            # `_build_widget`, so a new kind cannot be added with a
            # widget and without a contract. `_SmilesChooser` documents
            # its own two controls and is not itself documentable.
            contract = _PARAMETER_HELP.get(_HELP_KIND.get(parameter.kind, ""))
            if contract is not None:
                apply_help_tooltip(widget, contract)
            self._widgets[parameter.name] = widget
            form.addRow(parameter.label, widget)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_widget(self, parameter: CalculatorParameter) -> QWidget:
        if parameter.kind == "float":
            widget = QDoubleSpinBox(self)
            if parameter.minimum is not None:
                widget.setMinimum(parameter.minimum)
            if parameter.maximum is not None:
                widget.setMaximum(parameter.maximum)
            widget.setValue(float(parameter.default))
            return widget
        if parameter.kind == "int":
            widget = QSpinBox(self)
            if parameter.minimum is not None:
                widget.setMinimum(int(parameter.minimum))
            if parameter.maximum is not None:
                widget.setMaximum(int(parameter.maximum))
            widget.setValue(int(parameter.default))
            return widget
        if parameter.kind == "choice":
            widget = QComboBox(self)
            # `addItem(label, userData=code)` when labels are declared, so
            # `parameters()` can read the CODE back off `currentData()`.
            # With none declared the item carries no data, `currentData()`
            # is None, and the displayed text is the stored value exactly
            # as before -- which is what keeps every existing caller and
            # every retained result's key unmoved.
            labels = parameter.choice_labels
            for index, choice in enumerate(parameter.choices or []):
                if labels is None:
                    widget.addItem(choice)
                else:
                    widget.addItem(labels[index], choice)
            if labels is None:
                widget.setCurrentText(str(parameter.default))
            else:
                position = widget.findData(parameter.default)
                widget.setCurrentIndex(position if position >= 0 else 0)
            return widget
        if parameter.kind == "bool":
            widget = QCheckBox(self)
            widget.setChecked(bool(parameter.default))
            return widget
        if parameter.kind == "smiles":
            # The degrade condition is `not self._molecules`, evaluated
            # HERE, so a bare caller and a project with no usable SMILES
            # take the SAME branch -- one path rather than two.
            return _SmilesChooser(self._molecules, str(parameter.default or ""), self)
        if parameter.kind == "text":
            # Phase 26: free text, added for Substructure Search's custom
            # SMARTS field. A choice list can't cover "any SMARTS the user
            # can write", which is the whole point of that calculator.
            widget = QLineEdit(self)
            widget.setText(str(parameter.default or ""))
            return widget
        raise ValueError(f"Unknown CalculatorParameter.kind: {parameter.kind!r}")

    def parameters(self) -> dict[str, Any]:
        """Current values of every parameter's widget, keyed by
        `CalculatorParameter.name` -- call after `exec()` returns
        `QDialog.DialogCode.Accepted`."""
        values: dict[str, Any] = {}
        for parameter in self._parameters:
            widget = self._widgets[parameter.name]
            if isinstance(widget, _SmilesChooser):
                values[parameter.name] = widget.value()
            elif isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                values[parameter.name] = widget.value()
            elif isinstance(widget, QComboBox):
                # THE CODE WHERE ONE EXISTS, the displayed text otherwise.
                # What this returns is hashed into `parameters_key` and so
                # into every retained result's identity, which is why a
                # calculator declaring `choice_labels` must not store its
                # prose: rewording a label would orphan the cache.
                data = widget.currentData()
                values[parameter.name] = (
                    widget.currentText() if data is None else data
                )
            elif isinstance(widget, QCheckBox):
                values[parameter.name] = widget.isChecked()
            elif isinstance(widget, QLineEdit):
                values[parameter.name] = widget.text()
        return values
