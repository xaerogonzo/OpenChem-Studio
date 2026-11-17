"""A calculator may declare one family axis; Partial Charge (3D) is the only one."""

from __future__ import annotations

import pytest

from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
from openchem.chem.geometry_charges import (
    EEM_IONESCU2013_E_MPA_631GS_GAS,
    EEM_IONESCU2013_E_MPA_631GSS_GAS,
    GEOMETRY_CHARGE_METHODS,
)
from openchem.chem.typed_eem import RESONANCE_AVERAGED
from openchem.domain.calculator import CalculatorDefinition, CalculatorParameter, RegistryExecution
from openchem.domain.method_family import family_axis_of, family_requests, family_shared_parameters


_NOOP = RegistryExecution(compute=lambda mol, uuid, params: None)


def _geometry_charge():
    return next(d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "geometry_partial_charge")


def test_only_geometry_partial_charge_declares_a_family_axis():
    axes = {
        definition.calculator_id: family_axis_of(definition).name
        for definition in CALCULATOR_DEFINITIONS
        if family_axis_of(definition) is not None
    }
    assert axes == {"geometry_partial_charge": "method"}


def test_geometry_charge_family_has_six_unique_codes_in_declared_order():
    axis = family_axis_of(_geometry_charge())
    assert axis is not None
    assert tuple(axis.choices) == GEOMETRY_CHARGE_METHODS
    assert len(axis.choices) == 6
    assert len(set(axis.choices)) == 6
    assert EEM_IONESCU2013_E_MPA_631GS_GAS in axis.choices
    assert EEM_IONESCU2013_E_MPA_631GSS_GAS in axis.choices
    assert axis.choices.index(EEM_IONESCU2013_E_MPA_631GS_GAS) < axis.choices.index(
        EEM_IONESCU2013_E_MPA_631GSS_GAS
    )


def test_other_choice_calculators_have_no_family_axis():
    others = [
        d
        for d in CALCULATOR_DEFINITIONS
        if d.calculator_id != "geometry_partial_charge"
        and any(p.kind == "choice" for p in d.parameters)
    ]
    assert others
    assert all(family_axis_of(d) is None for d in others)


def test_family_axis_must_be_an_always_on_choice_with_unique_codes():
    with pytest.raises(ValueError, match="kind 'choice'"):
        CalculatorParameter(name="x", label="X", kind="float", default=1.0, family_axis=True)
    with pytest.raises(ValueError, match="enabled_by"):
        CalculatorParameter(
            name="method",
            label="Method",
            kind="choice",
            default="a",
            choices=["a"],
            family_axis=True,
            enabled_by="flag",
        )
    with pytest.raises(ValueError, match="unique"):
        CalculatorParameter(
            name="method",
            label="Method",
            kind="choice",
            default="a",
            choices=["a", "a"],
            family_axis=True,
        )
    with pytest.raises(ValueError, match="not one of the choices"):
        CalculatorParameter(
            name="method",
            label="Method",
            kind="choice",
            default="z",
            choices=["a", "b"],
            family_axis=True,
        )
    with pytest.raises(ValueError, match="non-empty"):
        CalculatorParameter(
            name="method",
            label="Method",
            kind="choice",
            default="a",
            choices=[],
            family_axis=True,
        )


def test_a_definition_may_have_only_one_family_axis():
    axis = CalculatorParameter(
        name="method",
        label="Method",
        kind="choice",
        default="a",
        choices=["a", "b"],
        family_axis=True,
    )
    other = CalculatorParameter(
        name="model",
        label="Model",
        kind="choice",
        default="x",
        choices=["x", "y"],
        family_axis=True,
    )
    with pytest.raises(ValueError, match="at most one family_axis"):
        CalculatorDefinition(
            calculator_id="two_axes",
            display_name="Two",
            category="charge",
            description="",
            execution=_NOOP,
            parameters=[axis, other],
        )


def test_family_requests_share_remaining_params_and_omit_disabled_ph():
    definition = _geometry_charge()
    values = {
        "method": "qeq_rg1991_lambda_half_h_experimental",
        "resonance": RESONANCE_AVERAGED,
        "ph_dependent": False,
        "pH": 4.0,
        "include_hydrogens": True,
        "decimal_places": 3,
    }
    shared = family_shared_parameters(definition, values)
    assert "method" not in shared
    assert "pH" not in shared
    assert shared["ph_dependent"] is False
    assert shared["include_hydrogens"] is True
    assert shared["decimal_places"] == 3

    requests = family_requests(definition, "mol-1", values)
    assert [r.parameters["method"] for r in requests] == list(GEOMETRY_CHARGE_METHODS)
    assert len({r.request_id for r in requests}) == 6
    assert all(r.request_id for r in requests)
    assert {r.parameters["include_hydrogens"] for r in requests} == {True}
    assert all("pH" not in r.parameters for r in requests)
    assert EEM_IONESCU2013_E_MPA_631GS_GAS in [r.parameters["method"] for r in requests]
    assert EEM_IONESCU2013_E_MPA_631GSS_GAS in [r.parameters["method"] for r in requests]
