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


# --- choices are codes; labels are prose --------------------------------


def _definition(parameter):
    from openchem.domain.calculator import CalculatorDefinition, RegistryExecution

    return CalculatorDefinition(
        calculator_id="probe",
        display_name="Probe",
        category="probe",
        description="A synthetic definition, so no shipped calculator is the fixture.",
        execution=RegistryExecution(compute=lambda *a, **k: None),
        parameters=[parameter],
    )


def test_a_choice_parameter_stores_its_code_not_its_label():
    """The stored value is hashed into `parameters_key`.

    `CalculatorSettingsDialog.parameters()` read `currentText()`, so a
    `"choice"` parameter put its ENGLISH LABEL into every retained result's
    identity -- and rewording that label silently orphaned every result
    computed under the old wording.
    """
    from openchem.domain.calculator import CalculatorParameter

    dialog = CalculatorSettingsDialog(
        _definition(
            CalculatorParameter(
                name="role",
                label="Role",
                kind="choice",
                default="acid",
                choices=["auto", "acid", "base"],
                choice_labels=[
                    "Work it out from the structures",
                    "This molecule is the acid",
                    "This molecule is the base",
                ],
            )
        )
    )
    widget = dialog._widgets["role"]

    assert widget.currentText() == "This molecule is the acid", "the prose is shown"
    assert dialog.parameters() == {"role": "acid"}, "the code is stored"


def test_a_choice_parameter_without_labels_still_stores_its_text():
    """THE NARROW HALF, and the load-bearing one.

    Twenty-three of the twenty-four shipped `"choice"` parameters declare
    no labels, and their stored values are part of results already
    retained. "Always store the code" would change all of them at once;
    with `choice_labels` absent the displayed text must remain the stored
    value, byte for byte.
    """
    from openchem.domain.calculator import CalculatorParameter

    dialog = CalculatorSettingsDialog(
        _definition(
            CalculatorParameter(
                name="mode",
                label="Mode",
                kind="choice",
                default="Fast",
                choices=["Fast", "Accurate"],
            )
        )
    )

    assert dialog._widgets["mode"].currentText() == "Fast"
    assert dialog.parameters() == {"mode": "Fast"}


def test_mismatched_labels_are_refused_at_construction_not_at_click():
    """A combo box silently showing fewer entries than it stores is the
    fail-open version of this. Refused where it is written."""
    import pytest

    from openchem.domain.calculator import CalculatorParameter

    with pytest.raises(ValueError, match="matched positionally"):
        CalculatorParameter(
            name="role", label="Role", kind="choice", default="acid",
            choices=["auto", "acid", "base"], choice_labels=["Auto"],
        )

    with pytest.raises(ValueError, match="without choices"):
        CalculatorParameter(
            name="role", label="Role", kind="choice", default="acid",
            choice_labels=["Auto"],
        )


def test_an_unknown_parameter_kind_is_refused_at_registration():
    """`_build_widget` matches no branch for an unknown kind and returns
    nothing, so the control is silently absent from the dialog. A typo
    should be a failing import instead."""
    import pytest

    from openchem.domain.calculator import CalculatorParameter

    with pytest.raises(ValueError, match="unknown parameter kind"):
        CalculatorParameter(name="x", label="X", kind="slider", default=1)


def test_every_shipped_parameter_declares_a_known_kind(qapp):
    """The population, so a new calculator cannot introduce a sixth kind
    without the dialog learning to build it."""
    from openchem.bootstrap import build_service_container
    from openchem.domain.calculator import PARAMETER_KINDS

    registry = build_service_container().calculator_registry
    kinds = {
        parameter.kind
        for category in registry.categories()
        for definition in registry.by_category(category)
        for parameter in definition.parameters
    }
    assert kinds, "no shipped calculator declares a parameter, so this proves nothing"
    assert kinds <= PARAMETER_KINDS
