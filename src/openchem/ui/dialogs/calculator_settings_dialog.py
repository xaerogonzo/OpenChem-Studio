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
            widget.addItems(parameter.choices or [])
            widget.setCurrentText(str(parameter.default))
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
                values[parameter.name] = widget.currentText()
            elif isinstance(widget, QCheckBox):
                values[parameter.name] = widget.isChecked()
            elif isinstance(widget, QLineEdit):
                values[parameter.name] = widget.text()
        return values
