"""A recipe: an ordered plan whose steps read each other's typed outputs.

The model half of `docs/RECIPES_DESIGN.md` (sections 2 and 3). Pure: no Qt, no RDKit, no ORCA. It describes a
plan and checks that the plan is well formed; it does not run one, look at a molecule, or read a quantum-chemistry
run. Evaluating a recipe over a project is a later slice, and so is the first recipe.

**A RECIPE IS CODE WITH DATA, SHIPPED WITH THE APPLICATION.** No person and no model writes one in this phase, which
is why there is no expression language here and no way to register one from a plugin. A user-defined formula is a
different feature with a different safety argument (`docs/DERIVED_SCORES_DESIGN.md`).

**A BINDING NAMES ITS SOURCE, AND THE SOURCE IS EARLIER OR NOT A STEP.** A step reads a slot (a project molecule), a
recipe parameter (a choice made once, such as the one method every step must share), or a named output of an
EARLIER step. A reference to the same step or a later one is a validation error, so a cycle cannot be written.

**EVERY VALUE HAS A TYPE, AND A UNIT IS PART OF IT.** Two scalars in different units are different types, and this
module never converts between them: a conversion would be its own reviewed entry in `TRANSFORMS` with the constant
it uses and a test, and the table starts with `identity` alone. An opaque unit string is compared for equality,
exactly as `DERIVED_SCORES_DESIGN.md` does for a score's inputs, so "eV" and "electronvolt" are different and the
author fixes the spelling.

**A RECIPE THAT FAILS VALIDATION IS A FAILING TEST, NOT A RECIPE THAT RUNS AND REFUSES.** `validate_recipe` reports
every problem at once, each naming where it is, so an author fixes them in one pass. It is called by a test over
`recipe_catalogue.SHIPPED_RECIPES` against the real calculator registry; the lookup that finds a calculator by id is handed in, so
this module imports no registry.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from openchem.domain.calculation_bridge import ProblemCode as ParameterProblem
from openchem.domain.calculation_bridge import validate_parameters
from openchem.domain.calculator import CalculatorDefinition, RegistryExecution
from openchem.domain.execution_policy import HEAVY_TOOLS, ExecutionPolicy, ResourceClass

#: The reserved name of the input every step that works on a molecule takes. A REGISTRY or SERVICE step has exactly
#: one binding with this target, and it must be of type `MOLECULE`.
MOLECULE_INPUT = "molecule"


class ValueKind(str, Enum):
    """The closed set of things a value can be."""

    #: A number with a unit. The unit is part of the type.
    SCALAR = "scalar"
    #: One of a declared set of codes (a role, a method preset).
    CODE = "code"
    #: A reference to a stored run, by id.
    RUN_REFERENCE = "run_reference"
    #: A report: what a recipe ends in.
    REPORT = "report"
    #: A project molecule. Only a slot has this type; no step produces one.
    MOLECULE = "molecule"


@dataclass(frozen=True)
class ValueType:
    """What a value is. Build it with `scalar`, `code` and the constants below, not by hand."""

    kind: ValueKind
    unit: str = ""
    codes: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.kind is ValueKind.SCALAR:
            if not self.unit.strip():
                raise ValueError("a scalar needs a unit; a count is '1'")
            if self.codes:
                raise ValueError("a scalar has no codes")
        elif self.kind is ValueKind.CODE:
            if not self.codes:
                raise ValueError("a code type needs at least one code")
            if self.unit:
                raise ValueError("a code has no unit")
        elif self.unit or self.codes:
            raise ValueError(f"a {self.kind.value} type has neither a unit nor codes")

    def accepts(self, offered: ValueType) -> bool:
        """Whether a value of type `offered` may be used where this type is needed.

        A unit must match exactly. A code type accepts a source whose codes are all among its own: a source that can
        say something this type has no word for is not accepted, because the step could not interpret it.
        """
        if self.kind is not offered.kind:
            return False
        if self.kind is ValueKind.SCALAR:
            return self.unit == offered.unit
        if self.kind is ValueKind.CODE:
            return offered.codes <= self.codes
        return True

    def describe(self) -> str:
        if self.kind is ValueKind.SCALAR:
            return f"a scalar in {self.unit}"
        if self.kind is ValueKind.CODE:
            return "a code from {" + ", ".join(sorted(self.codes)) + "}"
        return {
            ValueKind.RUN_REFERENCE: "a reference to a stored run",
            ValueKind.REPORT: "a report",
            ValueKind.MOLECULE: "a project molecule",
        }[self.kind]


def scalar(unit: str) -> ValueType:
    return ValueType(ValueKind.SCALAR, unit=unit)


def code(*codes: str) -> ValueType:
    return ValueType(ValueKind.CODE, codes=frozenset(codes))


#: A stored run, by id: what a step that starts a job hands on so a later step can name the run it came from.
RUN_REFERENCE = ValueType(ValueKind.RUN_REFERENCE)
#: What a recipe ends in. The result of a recipe is a step output of this type.
REPORT = ValueType(ValueKind.REPORT)
#: A project molecule. Only a slot has this type; the validator refuses a step output of it.
MOLECULE = ValueType(ValueKind.MOLECULE)


@dataclass(frozen=True)
class Transform:
    """One reviewed way to turn a value into another. Never supplied by a recipe author."""

    name: str
    description: str
    #: The type this transform gives for an input of the given type, or None when it does not accept that type.
    result_type: Callable[[ValueType], ValueType | None]
    apply: Callable[[Any], Any]


#: **THE CLOSED TABLE, AND IT STARTS WITH ONE MEMBER.** Adding a unit conversion is a reviewed change here with
#: its constant and its test, never a function a recipe brings along. `tests/test_recipe_model.py` pins the keys,
#: so growing the table is a visible edit to a test and not a side effect.
TRANSFORMS: Mapping[str, Transform] = MappingProxyType({
    "identity": Transform("identity", "the value, unchanged", lambda offered: offered, lambda value: value),
})


class Origin(str, Enum):
    SLOT = "slot"
    PARAMETER = "parameter"
    STEP = "step"


@dataclass(frozen=True)
class Source:
    """Where a binding reads from: a slot, a recipe parameter, or a named output of a step."""

    origin: Origin
    name: str
    #: The step's output name. Only for `Origin.STEP`.
    output: str = ""

    def __str__(self) -> str:
        return f"{self.name}.{self.output}" if self.origin is Origin.STEP else f"{self.origin.value} {self.name}"


def from_slot(name: str) -> Source:
    return Source(Origin.SLOT, name)


def from_parameter(name: str) -> Source:
    return Source(Origin.PARAMETER, name)


def from_step(step_id: str, output: str) -> Source:
    return Source(Origin.STEP, step_id, output)


@dataclass(frozen=True)
class Binding:
    """One input of a step: the name the step reads it under, the type it needs, and where it comes from."""

    target: str
    needs: ValueType
    source: Source
    transform: str = "identity"
    #: True only where the step's own contract says this input may be absent. The step then runs with `None`
    #: for it, whatever state the binding ended in, and the state is still recorded; see
    #: `recipe_run.BindingState.blocks`.
    optional: bool = False


@dataclass(frozen=True)
class StepOutput:
    name: str
    type: ValueType


class StepKind(str, Enum):
    #: A registered calculator, started as the assistant's bridge starts one, with its own execution policy.
    REGISTRY = "registry"
    #: One ORCA job. Always approved by a person: `ExecutionPolicy` refuses `AUTO` for any program in `HEAVY_TOOLS`.
    SERVICE = "service"
    #: A pure function over bound values. In process, instant, no external program.
    EVALUATE = "evaluate"


@dataclass(frozen=True)
class Step:
    step_id: str
    kind: StepKind
    #: REGISTRY: the calculator id. SERVICE: the job's calculation type. EVALUATE: the name of the pure function.
    action: str
    bindings: tuple[Binding, ...] = ()
    outputs: tuple[StepOutput, ...] = ()
    #: The constants of a REGISTRY step, checked by `validate_parameters`. A parameter that comes from a binding is
    #: not listed here.
    parameters: tuple[tuple[str, Any], ...] = ()
    #: Stated by a SERVICE or EVALUATE step. A REGISTRY step has none of its own: it takes its calculator's.
    policy: ExecutionPolicy | None = None
    #: What the step does, for the plan shown to a person.
    label: str = ""


@dataclass(frozen=True)
class RecipeParameter:
    """A choice made once for the whole recipe, such as the one method every step shares."""

    name: str
    label: str
    choices: tuple[str, ...]
    default: str

    def __post_init__(self) -> None:
        if not self.choices:
            raise ValueError(f"recipe parameter {self.name!r} has no choices")
        if self.default not in self.choices:
            raise ValueError(f"recipe parameter {self.name!r}: default {self.default!r} is not one of its choices")


@dataclass(frozen=True)
class Slot:
    """A named molecule input. It is a project molecule by uuid, recorded with its fingerprints; never a SMILES."""

    name: str
    label: str


@dataclass(frozen=True)
class Recipe:
    recipe_id: str
    #: Never repointed: a change of meaning is a new string, the rule `CURRENT_METHOD_VERSIONS` already follows.
    version: str
    #: The question it answers, in a sentence.
    question: str
    slots: tuple[Slot, ...]
    steps: tuple[Step, ...]
    #: The output that is the answer: a report-typed output of a step.
    result: Source
    parameters: tuple[RecipeParameter, ...] = ()
    #: Stated limits of the answer, shown with it.
    caveats: tuple[str, ...] = ()


class RecipeProblemCode(str, Enum):
    """Why a recipe is not well formed. Closed, so a test can be total over it."""

    MISSING_FIELD = "missing_field"
    DUPLICATE_NAME = "duplicate_name"
    DUPLICATE_VERSION = "duplicate_version"
    UNKNOWN_SOURCE = "unknown_source"
    FORWARD_REFERENCE = "forward_reference"
    UNKNOWN_OUTPUT = "unknown_output"
    UNKNOWN_TRANSFORM = "unknown_transform"
    TYPE_MISMATCH = "type_mismatch"
    UNIT_MISMATCH = "unit_mismatch"
    UNKNOWN_TARGET = "unknown_target"
    MISSING_MOLECULE = "missing_molecule"
    BAD_OUTPUT_TYPE = "bad_output_type"
    UNKNOWN_CALCULATOR = "unknown_calculator"
    NOT_A_REGISTRY_CALCULATOR = "not_a_registry_calculator"
    BAD_PARAMETERS = "bad_parameters"
    UNCLASSIFIED_STEP = "unclassified_step"
    POLICY_CONTRADICTS_KIND = "policy_contradicts_kind"
    BAD_RESULT = "bad_result"


@dataclass(frozen=True)
class RecipeProblem:
    code: RecipeProblemCode
    #: Where: "step sp_first, input molecule", "recipe", "result".
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.where}: {self.message}"


#: Finds a calculator definition by id, or None. The application hands `CalculatorRegistry.get`.
DefinitionLookup = Callable[[str], CalculatorDefinition | None]


class InvalidRecipe(ValueError):
    def __init__(self, problems: Iterable[RecipeProblem]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(str(p) for p in self.problems))


def validate_recipe(recipe: Recipe, definitions: DefinitionLookup) -> tuple[RecipeProblem, ...]:
    """Every way `recipe` is not well formed, or `()` when it is.

    Checked: names are unique and present; every binding resolves to a slot, a parameter or an EARLIER step's
    output; its transform is in the closed table; the offered type is accepted by the needed one (with the unit
    mismatch named as such); a REGISTRY step names a registered, registry-run, classified calculator whose
    constants pass `validate_parameters`; a SERVICE step starts a heavy program and a person approves it; an
    EVALUATE step starts nothing; every step that works on a molecule binds one; and the result is a report.
    """
    problems: list[RecipeProblem] = []

    def add(code_: RecipeProblemCode, where: str, message: str) -> None:
        problems.append(RecipeProblem(code_, where, message))

    for label, value in (("recipe_id", recipe.recipe_id), ("version", recipe.version), ("question", recipe.question)):
        if not value.strip():
            add(RecipeProblemCode.MISSING_FIELD, "recipe", f"{label} is empty")
    if not recipe.slots:
        add(RecipeProblemCode.MISSING_FIELD, "recipe", "a recipe needs at least one molecule slot")
    if not recipe.steps:
        add(RecipeProblemCode.MISSING_FIELD, "recipe", "a recipe needs at least one step")

    _check_unique("slot", [s.name for s in recipe.slots], add)
    _check_unique("recipe parameter", [p.name for p in recipe.parameters], add)
    _check_unique("step", [s.step_id for s in recipe.steps], add)

    slots = {s.name for s in recipe.slots}
    parameters = {p.name: p for p in recipe.parameters}
    step_index = {s.step_id: i for i, s in enumerate(recipe.steps)}
    #: step id -> output name -> type, for the steps already walked: the only legal step sources.
    earlier: dict[str, dict[str, ValueType]] = {}

    for step in recipe.steps:
        where_step = f"step {step.step_id}"
        if not step.step_id.strip() or not step.action.strip():
            add(RecipeProblemCode.MISSING_FIELD, where_step, "a step needs an id and an action")
        _check_unique(f"output of {where_step}", [o.name for o in step.outputs], add)
        _check_unique(f"input of {where_step}", [b.target for b in step.bindings], add)
        for output in step.outputs:
            if output.type.kind is ValueKind.MOLECULE:
                add(RecipeProblemCode.BAD_OUTPUT_TYPE, f"{where_step}, output {output.name}",
                    "no step produces a molecule; only a slot has that type")

        for binding in step.bindings:
            _check_binding(step, binding, slots, parameters, earlier, step_index, add)

        if step.kind is StepKind.REGISTRY:
            _check_registry_step(step, definitions, add)
        elif step.kind is StepKind.SERVICE:
            _check_service_step(step, add)
        else:
            _check_evaluate_step(step, add)

        earlier[step.step_id] = {o.name: o.type for o in step.outputs}

    _check_result(recipe, earlier, add)
    return tuple(problems)


def validate_recipes(recipes: Iterable[Recipe], definitions: DefinitionLookup) -> tuple[RecipeProblem, ...]:
    """`validate_recipe` for each, plus: no two recipes share an id AND a version."""
    recipes = tuple(recipes)
    problems: list[RecipeProblem] = []
    seen: set[tuple[str, str]] = set()
    for recipe in recipes:
        key = (recipe.recipe_id, recipe.version)
        if key in seen:
            problems.append(RecipeProblem(
                RecipeProblemCode.DUPLICATE_VERSION, f"recipe {recipe.recipe_id}",
                f"version {recipe.version!r} is used twice; a change of meaning is a new version string",
            ))
        seen.add(key)
        problems.extend(RecipeProblem(p.code, f"{recipe.recipe_id} {recipe.version}: {p.where}", p.message)
                        for p in validate_recipe(recipe, definitions))
    return tuple(problems)


def require_valid(recipes: Iterable[Recipe], definitions: DefinitionLookup) -> None:
    problems = validate_recipes(recipes, definitions)
    if problems:
        raise InvalidRecipe(problems)


# --- the checks ---------------------------------------------------------------------------------------------


def _check_unique(what: str, names: list[str], add) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            add(RecipeProblemCode.DUPLICATE_NAME, "recipe", f"two {what}s are named {name!r}")
        seen.add(name)


def _resolve_source(
    source: Source,
    slots: set[str],
    parameters: Mapping[str, RecipeParameter],
    earlier: Mapping[str, Mapping[str, ValueType]],
    step_index: Mapping[str, int],
    where: str,
    add,
) -> ValueType | None:
    """The type `source` offers, or None after recording why it offers none."""
    if source.origin is Origin.SLOT:
        if source.name in slots:
            return MOLECULE
        add(RecipeProblemCode.UNKNOWN_SOURCE, where, f"there is no slot {source.name!r}")
    elif source.origin is Origin.PARAMETER:
        if source.name in parameters:
            return code(*parameters[source.name].choices)
        add(RecipeProblemCode.UNKNOWN_SOURCE, where, f"there is no recipe parameter {source.name!r}")
    else:
        outputs = earlier.get(source.name)
        if outputs is None:
            if source.name in step_index:
                add(RecipeProblemCode.FORWARD_REFERENCE, where,
                    f"{source} is not available here: a step reads only EARLIER steps' outputs")
            else:
                add(RecipeProblemCode.UNKNOWN_SOURCE, where, f"there is no step {source.name!r}")
        elif source.output not in outputs:
            add(RecipeProblemCode.UNKNOWN_OUTPUT, where,
                f"step {source.name!r} has no output {source.output!r}; it has: {', '.join(outputs) or 'none'}")
        else:
            return outputs[source.output]
    return None


def _check_binding(step: Step, binding: Binding, slots, parameters, earlier, step_index, add) -> None:
    where = f"step {step.step_id}, input {binding.target}"
    offered = _resolve_source(binding.source, slots, parameters, earlier, step_index, where, add)
    transform = TRANSFORMS.get(binding.transform)
    if transform is None:
        add(RecipeProblemCode.UNKNOWN_TRANSFORM, where,
            f"transform {binding.transform!r} is not in the closed table: {', '.join(TRANSFORMS)}")
        return
    if offered is None:
        return
    transformed = transform.result_type(offered)
    if transformed is None:
        add(RecipeProblemCode.TYPE_MISMATCH, where,
            f"transform {transform.name!r} does not accept {offered.describe()}")
        return
    if binding.needs.accepts(transformed):
        return
    if binding.needs.kind is ValueKind.SCALAR and transformed.kind is ValueKind.SCALAR:
        add(RecipeProblemCode.UNIT_MISMATCH, where,
            f"needs {binding.needs.unit!r} but {binding.source} is in {transformed.unit!r}; "
            "units are never converted implicitly")
    else:
        add(RecipeProblemCode.TYPE_MISMATCH, where,
            f"needs {binding.needs.describe()} but {binding.source} is {transformed.describe()}")


def _check_molecule_binding(step: Step, add) -> None:
    molecule = [b for b in step.bindings if b.target == MOLECULE_INPUT]
    if len(molecule) != 1 or molecule[0].needs.kind is not ValueKind.MOLECULE:
        add(RecipeProblemCode.MISSING_MOLECULE, f"step {step.step_id}",
            f"a {step.kind.value} step binds exactly one input named {MOLECULE_INPUT!r}, of type molecule")


def _check_registry_step(step: Step, definitions: DefinitionLookup, add) -> None:
    where = f"step {step.step_id}"
    if step.policy is not None:
        add(RecipeProblemCode.POLICY_CONTRADICTS_KIND, where,
            "a registry step takes its calculator's execution policy and states none of its own")
    definition = definitions(step.action)
    if definition is None:
        add(RecipeProblemCode.UNKNOWN_CALCULATOR, where, f"no calculator is registered as {step.action!r}")
        return
    if not isinstance(definition.execution, RegistryExecution):
        add(RecipeProblemCode.NOT_A_REGISTRY_CALCULATOR, where,
            f"{step.action!r} is run by its own service, not through the registry; use a service step")
        return
    if definition.execution_policy is None:
        add(RecipeProblemCode.UNCLASSIFIED_STEP, where,
            f"{step.action!r} has no execution policy, so nobody decided whether it may run unattended")
    _check_molecule_binding(step, add)

    declared = {p.name for p in definition.parameters}
    bound = {b.target for b in step.bindings if b.target != MOLECULE_INPUT}
    constants = dict(step.parameters)
    for target in sorted(bound - declared):
        add(RecipeProblemCode.UNKNOWN_TARGET, f"{where}, input {target}",
            f"{step.action!r} has no parameter {target!r}; it takes: {', '.join(sorted(declared)) or 'none'}")
    for name in sorted(bound & constants.keys()):
        add(RecipeProblemCode.DUPLICATE_NAME, where, f"parameter {name!r} is both a constant and a binding")
    for problem in validate_parameters(definition, constants).problems:
        # A required parameter supplied by a binding has no constant here, and that is not a gap.
        if problem.code is ParameterProblem.NEEDS_INPUT and problem.parameter in bound:
            continue
        add(RecipeProblemCode.BAD_PARAMETERS, where, problem.message)


def _check_service_step(step: Step, add) -> None:
    where = f"step {step.step_id}"
    if not step.action.strip():
        return
    _check_molecule_binding(step, add)
    policy = step.policy
    if policy is None:
        add(RecipeProblemCode.UNCLASSIFIED_STEP, where, "a service step states its execution policy")
        return
    # Naming a heavy program is the whole check: `ExecutionPolicy` refuses `AUTO` for any program in `HEAVY_TOOLS`
    # when it is built, so a policy that names one is already one a person must approve.
    if not (policy.external_tools & HEAVY_TOOLS):
        add(RecipeProblemCode.POLICY_CONTRADICTS_KIND, where,
            "a service step starts a heavy external program (ORCA) and its policy names none")


def _check_evaluate_step(step: Step, add) -> None:
    where = f"step {step.step_id}"
    policy = step.policy
    if policy is None:
        add(RecipeProblemCode.UNCLASSIFIED_STEP, where, "an evaluate step states its execution policy")
        return
    if policy.external_tools or policy.writes_outside_results or policy.resource is not ResourceClass.INSTANT:
        add(RecipeProblemCode.POLICY_CONTRADICTS_KIND, where,
            "an evaluate step is a pure, instant, in-process function: no external program, no files, INSTANT")


def _check_result(recipe: Recipe, earlier: Mapping[str, Mapping[str, ValueType]], add) -> None:
    result = recipe.result
    if result.origin is not Origin.STEP:
        add(RecipeProblemCode.BAD_RESULT, "result", "the result is an output of a step")
        return
    outputs = earlier.get(result.name)
    if outputs is None or result.output not in outputs:
        add(RecipeProblemCode.BAD_RESULT, "result", f"{result} is not an output of any step")
    elif outputs[result.output].kind is not ValueKind.REPORT:
        add(RecipeProblemCode.BAD_RESULT, "result", f"{result} is {outputs[result.output].describe()}, not a report")
