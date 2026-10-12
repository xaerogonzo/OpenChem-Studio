"""Cards, routes and parameter validation: what a model is told, and what it may ask for."""

from __future__ import annotations

import json
import math

import pytest

from openchem.bootstrap import build_service_container
from openchem.domain.calculation_bridge import (
    MAX_TEXT_LENGTH,
    ProblemCode,
    Route,
    build_card,
    route_of,
    validate_parameters,
)
from openchem.domain.calculator import (
    CRYSTAL,
    CalculatorDefinition,
    CalculatorParameter,
    RegistryExecution,
)
from openchem.services.result_cache import parameters_key


@pytest.fixture(scope="module")
def registry():
    return build_service_container().calculator_registry


def _definition(parameters, **kw):
    base = dict(
        calculator_id="probe", display_name="Probe", category="charge", description="",
        execution=RegistryExecution(compute=lambda mol, uuid, params: None), parameters=parameters,
    )
    base.update(kw)
    return CalculatorDefinition(**base)


def _p(name, kind, default, **kw):
    return CalculatorParameter(name=name, label=name.title(), kind=kind, default=default, **kw)


def _codes(validation):
    return [problem.code for problem in validation.problems]


# --- cards and routes -----------------------------------------------------------------------


def test_a_registry_calculator_inside_its_policy_is_automatic(registry):
    card = build_card(registry.get("polar_surface_area"))
    assert card.route is Route.AUTO and card.execution == "registry"
    assert card.resource == "instant"


def test_a_calculator_that_needs_approval_says_so_and_why(registry):
    card = build_card(registry.get("alignment_3d"))
    assert card.route is Route.NEEDS_APPROVAL
    assert "31 s" in card.route_reason


@pytest.mark.parametrize("calculator_id", ["orca.sp", "orca.opt", "docking.vina", "lewis_hsab"])
def test_a_service_run_calculator_is_preview_only_and_never_described_as_runnable(registry, calculator_id):
    card = build_card(registry.get(calculator_id))
    assert card.route is Route.PREVIEW_ONLY and card.execution == "service"
    assert "cannot start it" in card.route_reason


def test_a_calculator_for_another_kind_of_structure_is_blocked():
    definition = _definition([], applies_to=frozenset({CRYSTAL}))
    route, reason = route_of(definition)
    assert route is Route.BLOCKED and "other than a molecule" in reason


def test_an_unclassified_plugin_calculator_needs_approval():
    assert build_card(_definition([])).route is Route.NEEDS_APPROVAL


def test_a_hidden_calculator_is_still_described_and_still_routed_by_its_policy(registry):
    hidden = [d for d in registry._definitions.values() if d.support is not None and d.support.default_visibility.value == "hidden"]
    assert hidden, "the registry holds no hidden calculator to check"
    card = build_card(hidden[0])
    assert card.visibility == "hidden" and card.support_reason


def test_every_registered_calculator_has_a_json_safe_card(registry):
    for definition in registry._definitions.values():
        card = build_card(definition)
        json.dumps(card.to_dict())
        assert card.route in set(Route)


def test_a_card_lists_what_the_caller_must_supply(registry):
    card = build_card(registry.get("lewis_adduct"))
    assert card.needs == ("partner_smiles",)
    assert {p.name: p.kind for p in card.parameters}["partner_smiles"] == "smiles"


def test_a_choice_card_carries_the_stored_codes_and_the_labels_separately(registry):
    parameters = {p.name: p for p in build_card(registry.get("geometry_analysis")).parameters}
    assert parameters["conformer_policy"].choices == ("never", "if_2d", "always")


# --- validation: the refusals -----------------------------------------------------------------


def test_the_measured_regression_an_invalid_choice_is_refused_not_run(registry):
    # `geometry_analysis` accepted this and ran: benchmarks/calculator_cost.
    result = validate_parameters(registry.get("geometry_analysis"), {"conformer_policy": "lowest_energy"})
    assert _codes(result) == [ProblemCode.NOT_A_CHOICE]
    assert "'never'" in result.problems[0].message and "lowest_energy" in result.problems[0].message
    assert result.parameters == {}


def test_an_unknown_parameter_is_refused_and_the_allowed_names_are_listed(registry):
    result = validate_parameters(registry.get("polar_surface_area"), {"colour": "red"})
    assert _codes(result) == [ProblemCode.UNKNOWN_PARAMETER]
    assert "pH" in result.problems[0].message


@pytest.mark.parametrize("value", ["7.4", None, True, [7], math.nan, math.inf])
def test_a_number_that_is_not_a_finite_number_is_the_wrong_type(value):
    result = validate_parameters(_definition([_p("x", "float", 1.0)]), {"x": value})
    assert _codes(result) == [ProblemCode.WRONG_TYPE]


def test_a_whole_number_setting_refuses_a_fraction_and_accepts_a_whole_float():
    definition = _definition([_p("n", "int", 3)])
    assert _codes(validate_parameters(definition, {"n": 2.5})) == [ProblemCode.WRONG_TYPE]
    ok = validate_parameters(definition, {"n": 4.0})
    assert ok.ok and ok.parameters["n"] == 4 and isinstance(ok.parameters["n"], int)


def test_bounds_are_enforced_on_both_sides():
    definition = _definition([_p("x", "float", 5.0, minimum=1.0, maximum=10.0)])
    assert _codes(validate_parameters(definition, {"x": 0.5})) == [ProblemCode.OUT_OF_RANGE]
    assert _codes(validate_parameters(definition, {"x": 10.5})) == [ProblemCode.OUT_OF_RANGE]
    assert validate_parameters(definition, {"x": 1.0}).ok and validate_parameters(definition, {"x": 10.0}).ok


def test_a_boolean_must_be_a_boolean():
    definition = _definition([_p("flag", "bool", False)])
    assert _codes(validate_parameters(definition, {"flag": "true"})) == [ProblemCode.WRONG_TYPE]
    assert _codes(validate_parameters(definition, {"flag": 1})) == [ProblemCode.WRONG_TYPE]
    assert validate_parameters(definition, {"flag": True}).parameters["flag"] is True


def test_text_must_be_text_and_short():
    definition = _definition([_p("t", "text", "")])
    assert _codes(validate_parameters(definition, {"t": 5})) == [ProblemCode.WRONG_TYPE]
    assert _codes(validate_parameters(definition, {"t": "x" * (MAX_TEXT_LENGTH + 1)})) == [ProblemCode.OUT_OF_RANGE]


def test_a_smiles_that_does_not_parse_is_refused_when_a_checker_is_given():
    definition = _definition([_p("partner", "smiles", "")])
    refuse = validate_parameters(definition, {"partner": "C(("}, smiles_ok=lambda s: False)
    assert _codes(refuse) == [ProblemCode.INVALID_STRUCTURE]
    assert validate_parameters(definition, {"partner": "CCO"}, smiles_ok=lambda s: True).ok


def test_every_problem_is_reported_at_once_not_just_the_first():
    definition = _definition([_p("a", "float", 1.0, maximum=2.0), _p("b", "choice", "x", choices=["x", "y"])])
    result = validate_parameters(definition, {"a": 99, "b": "z", "c": 1})
    assert sorted(_codes(result), key=str) == sorted(
        [ProblemCode.OUT_OF_RANGE, ProblemCode.NOT_A_CHOICE, ProblemCode.UNKNOWN_PARAMETER], key=str
    )


# --- validation: required inputs --------------------------------------------------------------


def test_a_required_input_that_was_not_given_is_needs_input_naming_it(registry):
    result = validate_parameters(registry.get("lewis_adduct"), {})
    assert _codes(result) == [ProblemCode.NEEDS_INPUT] and result.problems[0].parameter == "partner_smiles"


def test_a_required_input_left_at_its_placeholder_is_not_a_value(registry):
    # A density of 0.0 is the registered placeholder, and no density.
    result = validate_parameters(
        registry.get("detonation"),
        {"loading_density_g_cm3": 0.0, "enthalpy_of_formation_kcal_mol": -1000.0},
    )
    assert _codes(result) == [ProblemCode.NEEDS_INPUT, ProblemCode.NEEDS_INPUT]
    assert validate_parameters(
        registry.get("detonation"), {"loading_density_g_cm3": 1.64, "enthalpy_of_formation_kcal_mol": -16.0}
    ).ok


def test_a_whitespace_only_required_text_is_missing():
    definition = _definition([_p("ref", "text", "", required=True)])
    assert _codes(validate_parameters(definition, {"ref": "   "})) == [ProblemCode.NEEDS_INPUT]


# --- validation: what is accepted and how it is normalised -------------------------------------


def test_the_normalised_parameters_are_the_dialogs_dict_with_defaults_filled_in(registry):
    definition = registry.get("polar_surface_area")
    result = validate_parameters(definition, {})
    assert result.ok and dict(result.parameters) == {p.name: p.default for p in definition.parameters}
    assert list(result.parameters) == [p.name for p in definition.parameters]


def test_a_float_setting_given_as_an_integer_has_the_same_identity_as_the_dialogs_float(registry):
    definition = registry.get("polar_surface_area")
    from_model = validate_parameters(definition, {"pH": 7}).parameters
    from_dialog = {**{p.name: p.default for p in definition.parameters}, "pH": 7.0}
    assert parameters_key(dict(from_model)) == parameters_key(from_dialog)


def test_a_display_label_is_stored_as_its_code_and_the_change_is_reported():
    definition = _definition([_p("speed", "choice", "slow", choices=["slow", "fast"], choice_labels=["Take your time", "Hurry"])])
    result = validate_parameters(definition, {"speed": "hurry"})
    assert result.ok and result.parameters["speed"] == "fast"
    assert any("'fast'" in note for note in result.adjustments)


def test_a_label_that_matches_nothing_is_not_guessed_at():
    definition = _definition([_p("speed", "choice", "slow", choices=["slow", "fast"], choice_labels=["Take your time", "Hurry"])])
    assert _codes(validate_parameters(definition, {"speed": "Quick"})) == [ProblemCode.NOT_A_CHOICE]


def test_a_value_for_a_switched_off_setting_is_kept_in_the_dict_and_flagged_as_ignored():
    definition = _definition([_p("on", "bool", False), _p("depth", "int", 3, enabled_by="on")])
    result = validate_parameters(definition, {"depth": 5})
    assert result.ok and result.parameters["depth"] == 5
    assert any("depth was ignored" in note and "on" in note for note in result.adjustments)
    assert not validate_parameters(definition, {"on": True, "depth": 5}).adjustments


def test_no_parameters_at_all_is_a_valid_request_for_a_calculator_without_any():
    result = validate_parameters(_definition([]), None)
    assert result.ok and dict(result.parameters) == {}


# --- service previews ---------------------------------------------------------------------------------


def test_a_service_preview_is_ready_only_when_every_requirement_is_met_and_is_never_startable_here():
    from openchem.domain.calculation_bridge import Requirement, ServicePreview

    def preview(*oks):
        return ServicePreview(
            calculator_id="orca.sp", display_name="Single Point", panel_id="Quantum_Chemistry",
            panel_name="Quantum Chemistry panel", summary=("it runs ORCA",),
            requirements=tuple(Requirement(f"r{i}", ok, "" if ok else "do the thing") for i, ok in enumerate(oks)),
        )

    assert preview(True, True).ready is True and preview(True, False).ready is False
    assert preview(True).can_start_here is False
    data = preview(True, False).to_dict()
    json.dumps(data)
    assert data["ready_to_run_there"] is False and data["panel_id"] == "Quantum_Chemistry"
    assert data["requirements"] == [{"what": "r0", "ok": True}, {"what": "r1", "ok": False, "how_to_fix": "do the thing"}]


def test_the_docking_service_and_the_vina_provider_report_availability_without_starting_anything():
    from openchem.chem.docking_providers import VinaDockingProvider
    from openchem.services.docking_service import DockingService
    from openchem.events.base import EventBus
    from openchem.app.settings import Settings

    class _Engine:
        engine_id = "fake"

        def version(self):
            return "0"

    bus = EventBus()
    assert VinaDockingProvider(engine=_Engine()).is_available() is True
    service = DockingService(bus, Settings(bus), providers={"fake": VinaDockingProvider(engine=_Engine())})
    assert service.is_available() is True
    assert DockingService(bus, Settings(bus), providers={}).is_available() is False
