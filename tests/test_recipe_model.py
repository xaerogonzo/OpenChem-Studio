"""The recipe model: value types, the closed transform table, and the validator (`docs/RECIPES_DESIGN.md` 2-3).

No Qt and no ORCA. A recipe that fails validation is a failing test, so every rule here has a recipe that breaks
exactly that rule and nothing else, and the one well-formed recipe the rest are mutations of.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from openchem.bootstrap import build_service_container
from openchem.domain.calculator import (
    CalculatorDefinition,
    CalculatorParameter,
    RegistryExecution,
    ServiceExecution,
)
from openchem.domain.execution_policy import AiRun, ExecutionPolicy, ResourceClass
from openchem.domain import recipe as rc
from openchem.domain.recipe import (
    MOLECULE,
    MOLECULE_INPUT,
    REPORT,
    RUN_REFERENCE,
    TRANSFORMS,
    Binding,
    InvalidRecipe,
    Recipe,
    RecipeParameter,
    RecipeProblemCode as P,
    Slot,
    Step,
    StepKind,
    StepOutput,
    ValueKind,
    ValueType,
    code,
    from_parameter,
    from_slot,
    from_step,
    scalar,
    shipped_versions,
    validate_recipe,
    validate_recipes,
)

METHODS = ("B3LYP def2-SVP", "HF STO-3G")
EV = scalar("eV")


@pytest.fixture(scope="module")
def registry():
    return build_service_container().calculator_registry


def _orca_policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        ResourceClass.LONG, AiRun.CONFIRM, external_tools=frozenset({"orca"}), why_confirm="starts an ORCA job"
    )


def _instant_policy() -> ExecutionPolicy:
    return ExecutionPolicy(ResourceClass.INSTANT, AiRun.AUTO, measured="pure arithmetic over bound values")


def _service_step(step_id: str, slot: str) -> Step:
    return Step(
        step_id, StepKind.SERVICE, "sp",
        bindings=(
            Binding(MOLECULE_INPUT, MOLECULE, from_slot(slot)),
            Binding("method_basis", code(*METHODS), from_parameter("method_basis")),
        ),
        outputs=(StepOutput("homo", EV), StepOutput("run", RUN_REFERENCE)),
        policy=_orca_policy(),
    )


def _recipe() -> Recipe:
    """Two molecules, one shared method, an ORCA job for each, and an evaluation over both."""
    return Recipe(
        recipe_id="probe_pair",
        version="1",
        question="Which of the two has the higher HOMO?",
        slots=(Slot("first", "First molecule"), Slot("second", "Second molecule")),
        parameters=(RecipeParameter("method_basis", "Method and basis", METHODS, METHODS[0]),),
        steps=(
            _service_step("sp_first", "first"),
            _service_step("sp_second", "second"),
            Step(
                "compare", StepKind.EVALUATE, "compare_homo",
                bindings=(
                    Binding("first_homo", EV, from_step("sp_first", "homo")),
                    Binding("second_homo", EV, from_step("sp_second", "homo"), optional=True),
                ),
                outputs=(StepOutput("report", REPORT),),
                policy=_instant_policy(),
            ),
        ),
        result=from_step("compare", "report"),
    )


def _lookup(*definitions: CalculatorDefinition):
    by_id = {d.calculator_id: d for d in definitions}
    return by_id.get


def _registry_definition(**kw) -> CalculatorDefinition:
    base = dict(
        calculator_id="probe_calc", display_name="Probe", category="charge", description="",
        execution=RegistryExecution(compute=lambda mol, uuid, params: None),
        parameters=[
            CalculatorParameter(name="mode", label="Mode", kind="choice", default="a", choices=["a", "b"]),
            CalculatorParameter(name="depth", label="Depth", kind="int", default=2, minimum=1, maximum=5),
        ],
        execution_policy=_instant_policy(),
    )
    base.update(kw)
    return CalculatorDefinition(**base)


def _registry_recipe(step: Step) -> Recipe:
    return Recipe(
        recipe_id="probe_registry", version="1", question="q",
        slots=(Slot("a", "A"),),
        steps=(replace(step, outputs=(StepOutput("report", REPORT),)),),
        result=from_step(step.step_id, "report"),
    )


def _registry_step(**kw) -> Step:
    base = dict(
        step_id="calc", kind=StepKind.REGISTRY, action="probe_calc",
        bindings=(Binding(MOLECULE_INPUT, MOLECULE, from_slot("a")),),
    )
    base.update(kw)
    return Step(**base)


def _codes(recipe: Recipe, *definitions: CalculatorDefinition) -> list[P]:
    return [p.code for p in validate_recipe(recipe, _lookup(*definitions))]


def _replace_step(recipe: Recipe, step_id: str, **changes) -> Recipe:
    return replace(
        recipe, steps=tuple(replace(s, **changes) if s.step_id == step_id else s for s in recipe.steps)
    )


# --- value types and units ------------------------------------------------------------------------


def test_a_scalar_needs_a_unit_and_a_code_needs_codes():
    with pytest.raises(ValueError, match="needs a unit"):
        ValueType(ValueKind.SCALAR)
    with pytest.raises(ValueError, match="at least one code"):
        ValueType(ValueKind.CODE)
    with pytest.raises(ValueError, match="neither a unit nor codes"):
        ValueType(ValueKind.REPORT, unit="eV")


def test_two_scalars_are_the_same_type_only_in_the_same_unit_spelled_the_same_way():
    assert EV.accepts(scalar("eV"))
    assert not EV.accepts(scalar("hartree"))
    assert not EV.accepts(scalar("electronvolt")), "a unit is opaque; the author fixes the spelling"
    assert not EV.accepts(code("a")), "a kind mismatch"


def test_a_code_type_accepts_a_source_whose_codes_it_has_a_word_for():
    needed = code("auto", "acid", "base")
    assert needed.accepts(code("acid"))
    assert needed.accepts(code("auto", "acid", "base"))
    assert not needed.accepts(code("acid", "neutral")), "the step could not interpret 'neutral'"


# --- the closed transform table --------------------------------------------------------------------


def test_the_transform_table_starts_with_identity_alone():
    """Growing it must be a visible edit to this test, with the constant and the test of the conversion added."""
    assert set(TRANSFORMS) == {"identity"}


def test_identity_changes_neither_the_type_nor_the_value():
    transform = TRANSFORMS["identity"]
    value = object()
    assert transform.apply(value) is value
    assert transform.result_type(EV) == EV


# --- a well-formed recipe, and the faults that break it ---------------------------------------------


def test_a_well_formed_recipe_has_no_problems():
    assert validate_recipe(_recipe(), _lookup()) == ()


def test_every_problem_is_reported_not_just_the_first():
    recipe = _recipe()
    broken = _replace_step(
        recipe, "compare",
        bindings=(
            Binding("first_homo", EV, from_step("sp_first", "nope")),
            Binding("second_homo", scalar("hartree"), from_step("sp_second", "homo")),
        ),
    )
    assert sorted(c.value for c in _codes(broken)) == sorted([P.UNKNOWN_OUTPUT.value, P.UNIT_MISMATCH.value])


def test_a_problem_names_where_it_is():
    broken = _replace_step(
        _recipe(), "compare", bindings=(Binding("first_homo", EV, from_step("sp_first", "nope")),)
    )
    [problem] = validate_recipe(broken, _lookup())
    assert problem.where == "step compare, input first_homo"
    assert "sp_first" in problem.message and "nope" in problem.message


@pytest.mark.parametrize(
    ("label", "mutate", "expected"),
    [
        ("an unknown slot", lambda r: _replace_step(r, "sp_first", bindings=(
            Binding(MOLECULE_INPUT, MOLECULE, from_slot("third")),
            Binding("method_basis", code(*METHODS), from_parameter("method_basis")))), P.UNKNOWN_SOURCE),
        ("an unknown recipe parameter", lambda r: _replace_step(r, "sp_first", bindings=(
            Binding(MOLECULE_INPUT, MOLECULE, from_slot("first")),
            Binding("method_basis", code(*METHODS), from_parameter("basis")))), P.UNKNOWN_SOURCE),
        ("an unknown step", lambda r: _replace_step(r, "compare", bindings=(
            Binding("first_homo", EV, from_step("ghost", "homo")),)), P.UNKNOWN_SOURCE),
        ("a later step", lambda r: _replace_step(r, "sp_first", bindings=(
            Binding(MOLECULE_INPUT, MOLECULE, from_slot("first")),
            Binding("method_basis", code(*METHODS), from_parameter("method_basis")),
            Binding("hint", EV, from_step("compare", "report")))), P.FORWARD_REFERENCE),
        ("its own step", lambda r: _replace_step(r, "sp_first", bindings=(
            Binding(MOLECULE_INPUT, MOLECULE, from_slot("first")),
            Binding("self", EV, from_step("sp_first", "homo")))), P.FORWARD_REFERENCE),
        ("an unknown output", lambda r: _replace_step(r, "compare", bindings=(
            Binding("first_homo", EV, from_step("sp_first", "lumo")),)), P.UNKNOWN_OUTPUT),
        ("an unknown transform", lambda r: _replace_step(r, "compare", bindings=(
            Binding("first_homo", EV, from_step("sp_first", "homo"), transform="hartree_to_ev"),)), P.UNKNOWN_TRANSFORM),
        ("a unit mismatch", lambda r: _replace_step(r, "compare", bindings=(
            Binding("first_homo", scalar("hartree"), from_step("sp_first", "homo")),)), P.UNIT_MISMATCH),
        ("a type mismatch", lambda r: _replace_step(r, "compare", bindings=(
            Binding("first_homo", code("a"), from_step("sp_first", "homo")),)), P.TYPE_MISMATCH),
        ("a code the step has no word for", lambda r: _replace_step(r, "sp_first", bindings=(
            Binding(MOLECULE_INPUT, MOLECULE, from_slot("first")),
            Binding("method_basis", code(METHODS[0]), from_parameter("method_basis")))), P.TYPE_MISMATCH),
        ("two slots of one name", lambda r: replace(r, slots=(*r.slots, Slot("first", "again"))), P.DUPLICATE_NAME),
        ("two steps of one id", lambda r: replace(r, steps=(*r.steps, r.steps[0])), P.DUPLICATE_NAME),
        ("two outputs of one name", lambda r: _replace_step(r, "sp_first", outputs=(
            StepOutput("homo", EV), StepOutput("homo", EV))), P.DUPLICATE_NAME),
        ("two inputs of one name", lambda r: _replace_step(r, "compare", bindings=(
            Binding("x", EV, from_step("sp_first", "homo")), Binding("x", EV, from_step("sp_second", "homo")))),
         P.DUPLICATE_NAME),
        ("a step that produces a molecule", lambda r: _replace_step(r, "sp_first", outputs=(
            *r.steps[0].outputs, StepOutput("mol", MOLECULE))), P.BAD_OUTPUT_TYPE),
        ("a service step with no molecule", lambda r: _replace_step(r, "sp_first", bindings=(
            Binding("method_basis", code(*METHODS), from_parameter("method_basis")),)), P.MISSING_MOLECULE),
        ("a service step with a non-molecule 'molecule'", lambda r: _replace_step(r, "sp_first", bindings=(
            Binding(MOLECULE_INPUT, code(*METHODS), from_parameter("method_basis")),)), P.MISSING_MOLECULE),
        ("a service step with no stated policy", lambda r: _replace_step(r, "sp_first", policy=None), P.UNCLASSIFIED_STEP),
        ("a service step that starts nothing heavy", lambda r: _replace_step(r, "sp_first", policy=ExecutionPolicy(
            ResourceClass.SHORT, AiRun.CONFIRM, external_tools=frozenset({"network"}), why_confirm="x")),
         P.POLICY_CONTRADICTS_KIND),
        ("an evaluate step with no stated policy", lambda r: _replace_step(r, "compare", policy=None), P.UNCLASSIFIED_STEP),
        ("an evaluate step that starts ORCA", lambda r: _replace_step(r, "compare", policy=_orca_policy()),
         P.POLICY_CONTRADICTS_KIND),
        ("an evaluate step that is not instant", lambda r: _replace_step(r, "compare", policy=ExecutionPolicy(
            ResourceClass.SHORT, AiRun.AUTO, measured="x")), P.POLICY_CONTRADICTS_KIND),
        ("an evaluate step that reaches the network", lambda r: _replace_step(r, "compare", policy=ExecutionPolicy(
            ResourceClass.INSTANT, AiRun.AUTO, external_tools=frozenset({"network"}), measured="x")),
         P.POLICY_CONTRADICTS_KIND),
        ("an evaluate step that writes files", lambda r: _replace_step(r, "compare", policy=ExecutionPolicy(
            ResourceClass.INSTANT, AiRun.CONFIRM, writes_outside_results=True, why_confirm="x")),
         P.POLICY_CONTRADICTS_KIND),
        ("a result that is not a step output", lambda r: replace(r, result=from_slot("first")), P.BAD_RESULT),
        ("a result that no step has", lambda r: replace(r, result=from_step("compare", "other")), P.BAD_RESULT),
        ("a result that is not a report", lambda r: replace(r, result=from_step("sp_first", "homo")), P.BAD_RESULT),
        ("no question", lambda r: replace(r, question=" "), P.MISSING_FIELD),
    ],
)
def test_each_rule_has_a_recipe_that_breaks_exactly_it(label, mutate, expected):
    codes = _codes(mutate(_recipe()))
    assert codes, f"{label}: nothing was reported"
    assert set(codes) == {expected}, f"{label}: {codes}"


def test_a_slot_is_not_a_result_and_the_message_says_what_a_result_is():
    [problem] = validate_recipe(replace(_recipe(), result=from_slot("first")), _lookup())
    assert problem.code is P.BAD_RESULT and "output of a step" in problem.message


def test_a_service_step_cannot_be_made_automatic_in_the_first_place():
    """Why `_check_service_step` needs no test for 'approved by a person': the policy cannot be built otherwise."""
    with pytest.raises(ValueError, match="cannot run automatically"):
        ExecutionPolicy(ResourceClass.SHORT, AiRun.AUTO, external_tools=frozenset({"orca"}), measured="x")


def test_a_recipe_with_no_slots_is_reported_as_such():
    """Its steps' bindings to the slots that are not there are reported too, which is why this is not in the table."""
    assert P.MISSING_FIELD in _codes(replace(_recipe(), slots=()))


def test_a_recipe_parameter_must_have_a_default_among_its_choices():
    with pytest.raises(ValueError, match="not one of its choices"):
        RecipeParameter("method_basis", "Method", METHODS, "PBE0 def2-TZVP")
    with pytest.raises(ValueError, match="no choices"):
        RecipeParameter("method_basis", "Method", (), "")


def test_an_optional_binding_is_still_checked_for_type():
    """Optional relaxes what happens when no value is found, never what a value may be."""
    broken = _replace_step(
        _recipe(), "compare",
        bindings=(Binding("second_homo", scalar("hartree"), from_step("sp_second", "homo"), optional=True),),
    )
    assert _codes(broken) == [P.UNIT_MISMATCH]


def test_a_unit_mismatch_names_both_units_and_says_nothing_is_converted():
    broken = _replace_step(
        _recipe(), "compare", bindings=(Binding("first_homo", scalar("hartree"), from_step("sp_first", "homo")),)
    )
    [problem] = validate_recipe(broken, _lookup())
    assert "hartree" in problem.message and "eV" in problem.message and "never converted" in problem.message


# --- registry steps, against definitions ---------------------------------------------------------------


def test_a_registry_step_over_a_well_formed_definition_passes():
    step = _registry_step(parameters=(("mode", "b"), ("depth", 3)))
    assert validate_recipe(_registry_recipe(step), _lookup(_registry_definition())) == ()


def test_an_unregistered_calculator_is_reported():
    assert _codes(_registry_recipe(_registry_step())) == [P.UNKNOWN_CALCULATOR]


def test_a_service_run_calculator_cannot_be_a_registry_step():
    service_run = _registry_definition(execution=ServiceExecution(service_name="s", panel_name="p"))
    assert _codes(_registry_recipe(_registry_step()), service_run) == [P.NOT_A_REGISTRY_CALCULATOR]


def test_a_calculator_nobody_classified_is_an_unclassified_step():
    unclassified = _registry_definition(execution_policy=None)
    assert _codes(_registry_recipe(_registry_step()), unclassified) == [P.UNCLASSIFIED_STEP]


def test_a_registry_step_takes_its_calculators_policy_and_states_none_of_its_own():
    codes = _codes(_registry_recipe(_registry_step(policy=_instant_policy())), _registry_definition())
    assert codes == [P.POLICY_CONTRADICTS_KIND]


@pytest.mark.parametrize(
    "constants",
    [(("mode", "c"),), (("depth", 9),), (("depth", "deep"),), (("colour", "red"),)],
    ids=["not a choice", "out of range", "wrong type", "unknown parameter"],
)
def test_a_registry_steps_constants_go_through_the_same_validator_the_bridge_uses(constants):
    assert _codes(_registry_recipe(_registry_step(parameters=constants)), _registry_definition()) == [P.BAD_PARAMETERS]


def test_a_required_parameter_supplied_by_a_binding_is_not_a_gap():
    required = _registry_definition(parameters=[
        CalculatorParameter(name="density", label="Density", kind="float", default=0.0, required=True),
    ])
    bound = _registry_step(bindings=(
        Binding(MOLECULE_INPUT, MOLECULE, from_slot("a")),
        Binding("density", scalar("g/cm3"), from_slot("a")),
    ))
    # The slot offers a molecule, so the type is wrong -- but NEEDS_INPUT must not be what is reported.
    assert P.BAD_PARAMETERS not in _codes(_registry_recipe(bound), required)
    unbound = _registry_step()
    assert _codes(_registry_recipe(unbound), required) == [P.BAD_PARAMETERS]


def test_a_binding_for_a_parameter_the_calculator_does_not_have_is_reported():
    step = _registry_step(bindings=(
        Binding(MOLECULE_INPUT, MOLECULE, from_slot("a")),
        Binding("colour", code("red"), from_slot("a")),
    ))
    assert P.UNKNOWN_TARGET in _codes(_registry_recipe(step), _registry_definition())


def test_a_parameter_cannot_be_both_a_constant_and_a_binding():
    step = _registry_step(
        parameters=(("mode", "a"),),
        bindings=(
            Binding(MOLECULE_INPUT, MOLECULE, from_slot("a")),
            Binding("mode", code("a", "b"), from_slot("a")),
        ),
    )
    assert P.DUPLICATE_NAME in _codes(_registry_recipe(step), _registry_definition())


def test_a_registry_step_needs_exactly_one_molecule():
    none = _registry_step(bindings=())
    assert _codes(_registry_recipe(none), _registry_definition()) == [P.MISSING_MOLECULE]


def test_against_the_real_registry_a_service_run_calculator_is_refused_as_a_registry_step(registry):
    service_run = next(d.calculator_id for d in registry.definitions() if isinstance(d.execution, ServiceExecution))
    recipe = _registry_recipe(_registry_step(action=service_run))
    assert [p.code for p in validate_recipe(recipe, registry.get)] == [P.NOT_A_REGISTRY_CALCULATOR]


def test_against_the_real_registry_a_registered_calculator_passes_and_a_typo_does_not(registry):
    real = next(
        d.calculator_id for d in registry.definitions()
        if isinstance(d.execution, RegistryExecution) and d.execution_policy is not None
        and not any(p.required for p in d.parameters)
    )
    assert validate_recipe(_registry_recipe(_registry_step(action=real)), registry.get) == ()
    assert _codes_with(registry, _registry_recipe(_registry_step(action=real + "_x"))) == [P.UNKNOWN_CALCULATOR]


def _codes_with(registry, recipe):
    return [p.code for p in validate_recipe(recipe, registry.get)]


# --- the shipped set -----------------------------------------------------------------------------------


def test_two_recipes_may_not_share_an_id_and_a_version():
    twin = replace(_recipe(), question="another question")
    problems = validate_recipes([_recipe(), twin], _lookup())
    assert [p.code for p in problems] == [P.DUPLICATE_VERSION]
    assert validate_recipes([_recipe(), replace(_recipe(), version="2")], _lookup()) == ()


def test_the_problems_of_a_catalogue_say_which_recipe_they_are_in():
    broken = replace(_recipe(), question="")
    [problem] = validate_recipes([broken], _lookup())
    assert problem.where.startswith("probe_pair 1: ")


def test_require_valid_raises_with_every_problem():
    broken = replace(_recipe(), question="", version="")
    with pytest.raises(InvalidRecipe) as caught:
        rc.require_valid([broken], _lookup())
    assert len(caught.value.problems) == 2


def test_the_shipped_recipes_are_valid_against_the_real_registry(registry):
    """EMPTY UNTIL THE FIRST RECIPE LANDS, so today this proves only that the machinery runs on a real registry.
    The day a recipe is added it is validated here, and a malformed one is a failing test."""
    assert validate_recipes(rc.SHIPPED_RECIPES, registry.get) == ()


def test_shipped_versions_lists_each_version_by_recipe():
    assert shipped_versions([_recipe(), replace(_recipe(), version="2")]) == {"probe_pair": frozenset({"1", "2"})}
    assert shipped_versions([]) == {}
