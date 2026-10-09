"""The plan a run is decided as, before it starts.

Each case is a place the two old interpretations of "run these" disagreed, or a
number a cost estimate used to get wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from openchem.domain.calculator import (
    CalculatorDefinition,
    CalculatorParameter,
    RegistryExecution,
    ServiceExecution,
)
from openchem.domain.execution_plan import (
    NEEDS_INPUT,
    NO_STRUCTURE,
    SERVICE_ONLY,
    UNKNOWN,
    build_execution_plan,
)


@dataclass
class _Mol:
    uuid: str
    display_name: str
    molblock: str = "x"


def _calc(calculator_id, parameters=None, execution=None):
    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=calculator_id.title(),
        category="identity",
        description="d",
        execution=execution or RegistryExecution(compute=lambda mol, uuid, params: None),
        parameters=parameters or [],
    )


def _plan(definitions, calculator_ids, molecules=None, **kwargs):
    table = {d.calculator_id: d for d in definitions}
    return build_execution_plan(
        molecules=molecules if molecules is not None else [_Mol("m1", "One"), _Mol("m2", "Two")],
        calculator_ids=calculator_ids,
        definition_of=table.get,
        **kwargs,
    )


def test_the_cost_counts_what_will_run_not_what_was_ticked():
    plan = _plan([_calc("a"), _calc("b")], ["a", "b", "gone"])
    # 2 molecules x 2 surviving calculators, not 2 x 3 ticks.
    assert plan.job_count == 4
    assert [job.kind for job in plan.excluded] == [UNKNOWN]


def test_descriptors_count_like_calculators():
    plan = _plan([_calc("a")], ["a"], descriptor_ids=["mol_wt", "tpsa"])
    assert plan.job_count == 2 * 3


def test_a_service_only_calculator_is_left_out_and_named():
    service = _calc("orca.sp", execution=ServiceExecution(service_name="orca", panel_name="Quantum Chemistry"))
    plan = _plan([_calc("a"), service], ["a", "orca.sp"])
    assert plan.calculator_ids == ("a",)
    assert plan.excluded[0].kind == SERVICE_ONLY
    assert "own panel" in plan.excluded[0].reason


def test_a_required_parameter_with_nothing_chosen_is_left_out_with_what_it_wants():
    needs = _calc("n", parameters=[CalculatorParameter(name="smiles", label="Partner", kind="text", default="", required=True)])
    plan = _plan([needs], ["n"])
    assert plan.calculator_ids == ()
    assert plan.excluded[0].kind == NEEDS_INPUT
    assert "Partner" in plan.excluded[0].reason
    assert plan.is_empty


def test_the_same_calculator_with_chosen_settings_is_kept_and_runs_on_them():
    needs = _calc("n", parameters=[CalculatorParameter(name="smiles", label="Partner", kind="text", default="", required=True)])
    plan = _plan([needs], ["n"], chosen_parameters={"n": {"smiles": "O"}})
    assert plan.calculator_ids == ("n",)
    assert plan.parameters_for("n") == {"smiles": "O"}


def test_unchosen_calculators_run_on_their_registered_defaults():
    decimals = _calc("d", parameters=[CalculatorParameter(name="decimal_places", label="Decimals", kind="int", default=2)])
    plan = _plan([decimals], ["d"])
    assert plan.parameters_for("d") == {"decimal_places": 2}
    # ...but only what was CHOSEN goes to the service, which builds defaults itself.
    assert plan.overrides({}) == {}
    assert plan.overrides({"d": {"decimal_places": 5}}) == {"d": {"decimal_places": 5}}


def test_a_molecule_with_no_structure_keeps_its_row_but_costs_nothing():
    plan = _plan([_calc("a")], ["a"], molecules=[_Mol("m1", "One"), _Mol("m2", "Empty", molblock="")])
    assert plan.scope_uuids == ("m1", "m2"), "the service must still be handed it, so it gets a failed row"
    assert plan.molecule_uuids == ("m1",)
    assert plan.job_count == 1
    assert plan.unrunnable_molecules[0].kind == NO_STRUCTURE
    assert "Empty" in plan.describe_exclusions()


def test_duplicates_are_collapsed_and_order_is_kept():
    plan = _plan([_calc("a"), _calc("b")], ["b", "a", "b"])
    assert plan.calculator_ids == ("b", "a")


def test_a_plan_cannot_be_changed_after_it_is_made():
    plan = _plan([_calc("a")], ["a"])
    with pytest.raises(Exception):
        plan.calculator_ids = ()  # frozen dataclass
    with pytest.raises(TypeError):
        plan.parameters["a"] = {}  # read-only mapping
    with pytest.raises(TypeError):
        plan.parameters["a"]["x"] = 1


def test_each_plan_has_its_own_run_id_unless_one_is_given():
    a, b = _plan([_calc("a")], ["a"]), _plan([_calc("a")], ["a"])
    assert a.run_id != b.run_id
    assert _plan([_calc("a")], ["a"], run_id="fixed").run_id == "fixed"


def test_the_module_imports_no_qt():
    import inspect

    from openchem.domain import execution_plan

    assert "PySide6" not in inspect.getsource(execution_plan)
