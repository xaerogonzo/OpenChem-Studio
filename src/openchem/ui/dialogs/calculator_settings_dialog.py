from __future__ import annotations

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


class CalculatorSettingsDialog(QDialog):
    """Builds its form FROM `CalculatorDefinition.parameters` -- one Qt
    widget per `CalculatorParameter` -- rather than every calculator
    hand-building its own settings dialog. A calculator with zero
    parameters (LogP, Molar Refractivity, pKa today) still shows this
    dialog with just a description and OK/Cancel, so "Open [Calculator]..."
    always means the same thing regardless of which calculator fired.
    """

    def __init__(self, definition: CalculatorDefinition, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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
            if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
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
