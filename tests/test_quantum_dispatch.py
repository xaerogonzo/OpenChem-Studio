"""`domain/quantum_dispatch`: which ORCA calculators an assistant's card can ask a person to start, held to the registry and to the three settings a card can carry (dispatch, step 2).

The table is the one place that says "this calculator is one ORCA job whose whole description is the Run button's calculation type, method and basis, charge and multiplicity". These pin it to what the
registry actually declares, so a calculator that grows a fourth setting stops being startable by a card until the card can state it, rather than being started with that setting dropped.
"""

from __future__ import annotations

import pytest

from openchem.bootstrap import build_service_container
from openchem.chem.orca_engine import CALC_TYPE_LABELS
from openchem.domain.calculation_bridge import Route, build_card, route_of
from openchem.domain.calculator import MOLECULE, ServiceExecution
from openchem.domain.execution_policy import AiRun, policy_of
from openchem.chem.quantum_run_request import PROTON_AFFINITY
from openchem.domain.quantum_dispatch import FIXED_PROTOCOL, STARTABLE, calc_type_of


@pytest.fixture(scope="module")
def registry():
    return build_service_container().calculator_registry


def test_every_startable_calculator_is_a_registered_orca_job_run_by_the_quantum_chemistry_service(registry):
    for calculator_id, code in STARTABLE.items():
        definition = registry.get(calculator_id)
        assert definition is not None, calculator_id
        assert isinstance(definition.execution, ServiceExecution) and definition.execution.service_name == "quantum_chemistry_service"
        assert MOLECULE in definition.applies_to and calculator_id == f"orca.{code}"


def test_each_code_is_a_calculation_type_the_panel_offers_or_the_fixed_protocol_it_is_recorded_under(registry):
    assert {STARTABLE[c] for c in STARTABLE if c not in FIXED_PROTOCOL} <= set(CALC_TYPE_LABELS.values())
    assert {STARTABLE[c] for c in FIXED_PROTOCOL} == {PROTON_AFFINITY}


def test_a_startable_calculator_takes_exactly_the_three_settings_a_card_hands_over(registry):
    for calculator_id in set(STARTABLE) - FIXED_PROTOCOL:
        names = [p.name for p in registry.get(calculator_id).parameters]
        assert names == ["charge", "multiplicity", "method_basis"], (calculator_id, "a card hands over only these; a new setting needs the card and the hand-over to carry it first")


def test_a_fixed_protocol_offers_nothing_to_choose_and_a_card_has_nothing_to_add(registry):
    for calculator_id in FIXED_PROTOCOL:
        (parameter,) = registry.get(calculator_id).parameters
        assert parameter.name == "method_basis" and len(parameter.choices) == 1, "the one choice only names the protocol that was benchmarked"
    assert FIXED_PROTOCOL <= set(STARTABLE) and FIXED_PROTOCOL == {"orca.proton_affinity"}


def test_every_startable_calculator_asks_a_person_and_says_what_it_starts(registry):
    for calculator_id in STARTABLE:
        policy = policy_of(registry.get(calculator_id))
        assert policy.ai_run is AiRun.CONFIRM and "orca" in policy.external_tools and policy.why_confirm


def test_what_is_not_one_job_with_those_settings_is_not_startable(registry):
    left_out = {"orca.fukui", "orca.bond_dissociation_enthalpy", "orca.tautomer_distribution", "docking.vina", "lewis_hsab"}
    assert not left_out & set(STARTABLE)
    assert all(calc_type_of(calculator_id) is None for calculator_id in left_out)
    # Every other ORCA calculation type the panel offers is one a card can ask for, so a new type has to be decided about, not forgotten.
    assert {f"orca.{code}" for code in CALC_TYPE_LABELS.values()} - set(STARTABLE) == {"orca.fukui"}


def test_the_table_cannot_be_changed_from_outside():
    with pytest.raises(TypeError):
        STARTABLE["orca.fukui"] = "fukui"  # type: ignore[index]


def test_a_card_promises_an_approval_only_where_the_host_can_start_one(registry):
    definition = registry.get("orca.sp")
    assert route_of(definition)[0] is Route.PREVIEW_ONLY and build_card(definition).route is Route.PREVIEW_ONLY
    route, reason = route_of(definition, STARTABLE)
    assert route is Route.NEEDS_APPROVAL and "same rules as that panel's Run button" in reason and "ORCA runs for minutes to hours" in reason
    assert build_card(definition, STARTABLE).route is Route.NEEDS_APPROVAL
    # A host that can start only some of them promises only those.
    assert build_card(registry.get("orca.opt"), {"orca.sp"}).route is Route.PREVIEW_ONLY


def test_a_registry_calculator_is_unaffected_by_what_a_host_can_start(registry):
    definition = registry.get("polar_surface_area")
    assert route_of(definition) == route_of(definition, STARTABLE)
