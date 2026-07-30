from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox

from openchem.domain.calculator import CalculatorDefinition, CalculatorParameter, RegistryExecution
from openchem.ui.dialogs.calculator_settings_dialog import CalculatorSettingsDialog

_NOOP_EXECUTION = RegistryExecution(compute=lambda mol, uuid, params: None)


def test_float_parameter_builds_a_double_spin_box_prefilled_with_the_default(qapp):
    definition = CalculatorDefinition(
        calculator_id="charge_at_ph",
        display_name="Charge",
        category="charge",
        description="",
        execution=_NOOP_EXECUTION,
        parameters=[CalculatorParameter(name="pH", label="pH", kind="float", default=7.4, minimum=0.0, maximum=14.0)],
    )

    dialog = CalculatorSettingsDialog(definition)

    widget = dialog._widgets["pH"]
    assert isinstance(widget, QDoubleSpinBox)
    assert widget.value() == 7.4
    assert widget.minimum() == 0.0
    assert widget.maximum() == 14.0


def test_int_parameter_builds_a_spin_box():
    definition = CalculatorDefinition(
        calculator_id="test",
        display_name="Test",
        category="test",
        description="",
        execution=_NOOP_EXECUTION,
        parameters=[CalculatorParameter(name="count", label="Count", kind="int", default=5, minimum=1, maximum=10)],
    )

    dialog = CalculatorSettingsDialog(definition)

    widget = dialog._widgets["count"]
    assert isinstance(widget, QSpinBox)
    assert widget.value() == 5


def test_choice_parameter_builds_a_combo_box():
    definition = CalculatorDefinition(
        calculator_id="test",
        display_name="Test",
        category="test",
        description="",
        execution=_NOOP_EXECUTION,
        parameters=[
            CalculatorParameter(name="mode", label="Mode", kind="choice", default="B", choices=["A", "B", "C"])
        ],
    )

    dialog = CalculatorSettingsDialog(definition)

    widget = dialog._widgets["mode"]
    assert isinstance(widget, QComboBox)
    assert widget.currentText() == "B"
    assert [widget.itemText(i) for i in range(widget.count())] == ["A", "B", "C"]


def test_bool_parameter_builds_a_check_box():
    definition = CalculatorDefinition(
        calculator_id="test",
        display_name="Test",
        category="test",
        description="",
        execution=_NOOP_EXECUTION,
        parameters=[CalculatorParameter(name="flag", label="Flag", kind="bool", default=True)],
    )

    dialog = CalculatorSettingsDialog(definition)

    widget = dialog._widgets["flag"]
    assert isinstance(widget, QCheckBox)
    assert widget.isChecked() is True


def test_zero_parameter_definition_builds_an_empty_form():
    definition = CalculatorDefinition(
        calculator_id="crippen_logp_contrib",
        display_name="LogP",
        category="logp",
        description="No settings needed.",
        execution=_NOOP_EXECUTION,
    )

    dialog = CalculatorSettingsDialog(definition)

    assert dialog.parameters() == {}


def test_parameters_returns_current_widget_values_after_editing():
    definition = CalculatorDefinition(
        calculator_id="charge_at_ph",
        display_name="Charge",
        category="charge",
        description="",
        execution=_NOOP_EXECUTION,
        parameters=[CalculatorParameter(name="pH", label="pH", kind="float", default=7.4, minimum=0.0, maximum=14.0)],
    )
    dialog = CalculatorSettingsDialog(definition)

    dialog._widgets["pH"].setValue(2.0)

    assert dialog.parameters() == {"pH": 2.0}


def test_parameters_with_multiple_kinds():
    definition = CalculatorDefinition(
        calculator_id="test",
        display_name="Test",
        category="test",
        description="",
        execution=_NOOP_EXECUTION,
        parameters=[
            CalculatorParameter(name="pH", label="pH", kind="float", default=7.0),
            CalculatorParameter(name="count", label="Count", kind="int", default=3),
            CalculatorParameter(name="mode", label="Mode", kind="choice", default="X", choices=["X", "Y"]),
            CalculatorParameter(name="flag", label="Flag", kind="bool", default=False),
        ],
    )
    dialog = CalculatorSettingsDialog(definition)

    assert dialog.parameters() == {"pH": 7.0, "count": 3, "mode": "X", "flag": False}
