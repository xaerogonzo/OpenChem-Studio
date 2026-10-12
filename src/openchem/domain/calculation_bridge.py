"""What a plugin may know about a calculator, and what it may ask of one.

The pure half of the assistant's calculator bridge (`docs/AI_CALCULATION_BRIDGE.md`): the typed
vocabulary the plugin handle speaks, the card that describes a calculator, and the validation that
stands between a model's request and a calculator. No Qt, no RDKit: the one thing validation needs
from a chemistry toolkit (does this SMILES parse) is handed in.

**A CARD SAYS WHAT THIS ROUTE CAN DO WITH A CALCULATOR, NOT ONLY THAT IT EXISTS.** Registered is
not the same as runnable here. A service-run calculator (Docking, the ORCA types) is registered and
cannot be started through the registry; a hidden one is still searchable and runnable; one that
needs approval is runnable only after a person looks at a preview. `Route` is that distinction, and
a card never describes a calculator as immediately runnable when it is not.

**VALIDATION REFUSES; IT DOES NOT CORRECT.** A calculator does not check what it is given: measured
2026-10-12, `geometry_analysis` ran with `conformer_policy="lowest_energy"`, which is not one of its
choices (`benchmarks/calculator_cost`). So a request is validated against the definition itself --
unknown names, kinds, bounds, choice codes, required inputs -- and a value that fails is a typed
problem naming the parameter, never silently replaced by one that works. The single translation it
makes is a choice's DISPLAY label to its stored code (the stored code is what identifies a result),
and it says so in `adjustments`.

**THE NORMALISED PARAMETERS ARE THE DIALOG'S, NOT A NEW SHAPE.** Every declared parameter, in order,
with the registered default where the caller said nothing -- exactly the dict the settings dialog
and `build_execution_plan` hand `DescriptorService.run_calculator`. The result's identity
(`parameters_key`) is built from it, so an AI run and a person's run with the same settings are the
same calculation and cannot be told apart in the store.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from openchem.domain.calculator import (
    MOLECULE,
    CalculatorDefinition,
    CalculatorParameter,
    RegistryExecution,
    active_parameters,
)
from openchem.domain.calculator_support import SupportStage, Visibility, support_of
from openchem.domain.calculator_taxonomy import category_label
from openchem.domain.execution_policy import AiRun, policy_of


class ProblemCode(str, Enum):
    """Why a request was refused before anything ran. Closed: a caller can be total over it."""

    #: The host that would answer is not there (a headless run, a test context).
    UNAVAILABLE = "unavailable"
    NO_MOLECULE = "no_molecule"
    NO_STRUCTURE = "no_structure"
    UNKNOWN_CALCULATOR = "unknown_calculator"
    #: Registered, and run by its own service: not startable through the registry.
    SERVICE_RUN = "service_run"
    NOT_FOR_MOLECULES = "not_for_molecules"
    UNKNOWN_PARAMETER = "unknown_parameter"
    WRONG_TYPE = "wrong_type"
    OUT_OF_RANGE = "out_of_range"
    NOT_A_CHOICE = "not_a_choice"
    #: A required input with no usable value. Not a fault: it says what to supply.
    NEEDS_INPUT = "needs_input"
    INVALID_STRUCTURE = "invalid_structure"
    NO_SUCH_RUN = "no_such_run"
    WRONG_TURN = "wrong_turn"


@dataclass(frozen=True)
class Problem:
    """One reason a request cannot go ahead, with the parameter it is about."""

    code: ProblemCode
    message: str
    #: The calculator's own `CalculatorParameter.name`, or "" for a problem with the request.
    parameter: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "parameter": self.parameter, "message": self.message}


class Route(str, Enum):
    """What THIS route can do with a calculator right now."""

    #: Runs when asked, inside the policy's bounds.
    AUTO = "auto"
    #: Runs only after a person approves a preview.
    NEEDS_APPROVAL = "needs_approval"
    #: Run by its own service. The assistant can describe what it would do and cannot start it.
    PREVIEW_ONLY = "preview_only"
    #: Cannot be run here at all, with the reason.
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ParameterCard:
    """One setting a calculator takes, as a model needs to know it."""

    name: str
    label: str
    kind: str
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    #: The STORED codes. What a request must say, never the display labels.
    choices: tuple[str, ...] = ()
    choice_labels: tuple[str, ...] = ()
    required: bool = False
    #: The bool parameter that must be on for this one to mean anything, or "".
    enabled_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name, "label": self.label, "kind": self.kind, "default": self.default}
        if self.minimum is not None:
            data["minimum"] = self.minimum
        if self.maximum is not None:
            data["maximum"] = self.maximum
        if self.choices:
            data["choices"] = list(self.choices)
        if self.choice_labels:
            data["choice_labels"] = list(self.choice_labels)
        if self.required:
            data["required"] = True
        if self.enabled_by:
            data["enabled_by"] = self.enabled_by
        return data


@dataclass(frozen=True)
class CalculatorCard:
    """Everything a model is told about one calculator, from the registry and nowhere else."""

    calculator_id: str
    display_name: str
    category: str
    category_label: str
    description: str
    tags: tuple[str, ...]
    #: `SupportStage.value`: the maturity of THIS APPLICATION'S implementation.
    stage: str
    #: `Visibility.value`. Hidden calculators are still discoverable and runnable.
    visibility: str
    support_reason: str
    #: "registry" or "service".
    execution: str
    route: Route
    route_reason: str
    #: `ResourceClass.value` and the programs it starts: separate facts from the route.
    resource: str
    external_tools: tuple[str, ...]
    parameters: tuple[ParameterCard, ...]
    #: Names of the parameters with no usable default, which a request must supply.
    needs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "calculator_id": self.calculator_id,
            "name": self.display_name,
            "category": self.category_label,
            "description": self.description,
            "tags": list(self.tags),
            "stage": self.stage,
            "visibility": self.visibility,
            "support_reason": self.support_reason,
            "execution": self.execution,
            "route": self.route.value,
            "route_reason": self.route_reason,
            "resource": self.resource,
            "external_tools": list(self.external_tools),
            "needs": list(self.needs),
            "parameters": [p.to_dict() for p in self.parameters],
        }


def route_of(definition: CalculatorDefinition) -> tuple[Route, str]:
    """Which `Route` a definition is on, and the sentence that says why."""
    if MOLECULE not in definition.applies_to:
        return Route.BLOCKED, "it applies to structures other than a molecule, which this route does not offer"
    if not isinstance(definition.execution, RegistryExecution):
        return (
            Route.PREVIEW_ONLY,
            f"it is run from the {definition.execution.panel_name}; the assistant can describe what it "
            f"would do but cannot start it",
        )
    policy = policy_of(definition)
    if policy.ai_run is AiRun.CONFIRM:
        return Route.NEEDS_APPROVAL, policy.why_confirm
    return Route.AUTO, "it runs when asked, unless a setting or the molecule is outside what its cost was measured for"


def parameter_card(parameter: CalculatorParameter) -> ParameterCard:
    return ParameterCard(
        name=parameter.name,
        label=parameter.label,
        kind=parameter.kind,
        default=parameter.default,
        minimum=parameter.minimum,
        maximum=parameter.maximum,
        choices=tuple(parameter.choices or ()),
        choice_labels=tuple(parameter.choice_labels or ()),
        required=parameter.required,
        enabled_by=parameter.enabled_by or "",
    )


def build_card(definition: CalculatorDefinition) -> CalculatorCard:
    support = support_of(definition)
    route, reason = route_of(definition)
    policy = policy_of(definition)
    return CalculatorCard(
        calculator_id=definition.calculator_id,
        display_name=definition.display_name,
        category=definition.category,
        category_label=category_label(definition.category),
        description=definition.description or "",
        tags=tuple(definition.tags or ()),
        stage=support.stage.value if isinstance(support.stage, SupportStage) else str(support.stage),
        visibility=support.default_visibility.value if isinstance(support.default_visibility, Visibility) else str(support.default_visibility),
        support_reason=support.support_reason,
        execution="registry" if isinstance(definition.execution, RegistryExecution) else "service",
        route=route,
        route_reason=reason,
        resource=policy.resource.value,
        external_tools=tuple(sorted(policy.external_tools)),
        parameters=tuple(parameter_card(p) for p in definition.parameters),
        needs=tuple(p.name for p in definition.parameters if p.required),
    )


# --- validation -----------------------------------------------------------------------------

#: A free-text parameter longer than this is refused rather than passed on. Generous for a SMARTS
#: or a substituent table, small enough that a model cannot use a parameter as a payload.
MAX_TEXT_LENGTH = 4000


@dataclass(frozen=True)
class Validation:
    """The outcome of checking a request's parameters against a definition."""

    #: Every declared parameter, in order, defaults filled in -- the dialog's dict. Empty when
    #: there are problems, so a caller cannot run on a half-checked one.
    parameters: Mapping[str, Any] = field(default_factory=dict)
    problems: tuple[Problem, ...] = ()
    #: What was changed on the way through, in words: a display label stored as its code, or a
    #: value given for a setting that is switched off and so ignored.
    adjustments: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.problems


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _check_number(parameter: CalculatorParameter, value: Any) -> tuple[Any, Problem | None]:
    name = parameter.name
    if not _is_number(value):
        return None, Problem(ProblemCode.WRONG_TYPE, f"{name} must be a number, not {value!r}", name)
    if parameter.kind == "int":
        if isinstance(value, float):
            if not value.is_integer():
                return None, Problem(ProblemCode.WRONG_TYPE, f"{name} must be a whole number, not {value!r}", name)
            value = int(value)
    else:
        # The dialog stores a float setting as a float, and `parameters_key` serialises 7 and 7.0
        # differently, so an AI run would otherwise be a different calculation from a person's.
        value = float(value)
    if parameter.minimum is not None and value < parameter.minimum:
        return None, Problem(
            ProblemCode.OUT_OF_RANGE, f"{name} is {value:g}, below its minimum of {parameter.minimum:g}", name
        )
    if parameter.maximum is not None and value > parameter.maximum:
        return None, Problem(
            ProblemCode.OUT_OF_RANGE, f"{name} is {value:g}, above its maximum of {parameter.maximum:g}", name
        )
    return value, None


def _check_choice(parameter: CalculatorParameter, value: Any, adjustments: list[str]) -> tuple[Any, Problem | None]:
    name = parameter.name
    choices = list(parameter.choices or [])
    if isinstance(value, str) and value in choices:
        return value, None
    labels = list(parameter.choice_labels or [])
    if isinstance(value, str) and labels:
        matches = [code for code, label in zip(choices, labels) if label.casefold() == value.strip().casefold()]
        if len(matches) == 1:
            adjustments.append(f"{name}: {value!r} is the label of the stored choice {matches[0]!r}, which was used")
            return matches[0], None
    shown = ", ".join(repr(c) for c in choices)
    return None, Problem(ProblemCode.NOT_A_CHOICE, f"{name} must be one of {shown}, not {value!r}", name)


def _check_text(parameter: CalculatorParameter, value: Any, smiles_ok: Callable[[str], bool] | None) -> tuple[Any, Problem | None]:
    name = parameter.name
    if not isinstance(value, str):
        return None, Problem(ProblemCode.WRONG_TYPE, f"{name} must be text, not {value!r}", name)
    if len(value) > MAX_TEXT_LENGTH:
        return None, Problem(ProblemCode.OUT_OF_RANGE, f"{name} is {len(value)} characters; the limit is {MAX_TEXT_LENGTH}", name)
    if parameter.kind == "smiles" and value.strip() and smiles_ok is not None and not smiles_ok(value.strip()):
        return None, Problem(ProblemCode.INVALID_STRUCTURE, f"{name} is not a SMILES that can be read: {value!r}", name)
    return value, None


def validate_parameters(
    definition: CalculatorDefinition,
    supplied: Mapping[str, Any] | None,
    *,
    smiles_ok: Callable[[str], bool] | None = None,
) -> Validation:
    """Check `supplied` against `definition`; see the module docstring for the rules.

    Every problem is reported at once, not just the first: a model that fixes one and resubmits
    to find the next burns turns. `needs_input` is reported for a required parameter that was not
    given or was given its own placeholder default -- a density of 0.0 is no density.
    """
    supplied = dict(supplied or {})
    by_name = {p.name: p for p in definition.parameters}
    problems: list[Problem] = []
    adjustments: list[str] = []

    for name in supplied:
        if name not in by_name:
            allowed = ", ".join(by_name) or "none"
            problems.append(Problem(ProblemCode.UNKNOWN_PARAMETER, f"{definition.calculator_id} has no parameter {name!r}; it takes: {allowed}", name))

    normalised: dict[str, Any] = {}
    for parameter in definition.parameters:
        name = parameter.name
        if name not in supplied:
            normalised[name] = parameter.default
            if parameter.required:
                problems.append(Problem(ProblemCode.NEEDS_INPUT, f"{name} ({parameter.label}) has no usable default; a value is needed", name))
            continue
        value = supplied[name]
        problem: Problem | None = None
        if parameter.kind in ("int", "float"):
            value, problem = _check_number(parameter, value)
        elif parameter.kind == "choice":
            value, problem = _check_choice(parameter, value, adjustments)
        elif parameter.kind == "bool":
            if not isinstance(value, bool):
                problem = Problem(ProblemCode.WRONG_TYPE, f"{name} must be true or false, not {value!r}", name)
        else:  # "text" and "smiles"
            value, problem = _check_text(parameter, value, smiles_ok)
        if problem is not None:
            problems.append(problem)
            continue
        if parameter.required and (value == parameter.default or (isinstance(value, str) and not value.strip())):
            problems.append(Problem(ProblemCode.NEEDS_INPUT, f"{name} ({parameter.label}) was left at its placeholder; a real value is needed", name))
            continue
        normalised[name] = value

    if problems:
        return Validation(problems=tuple(problems), adjustments=tuple(adjustments))

    inactive = set(by_name) - set(active_parameters(definition, normalised))
    for name in supplied:
        if name in inactive:
            controller = by_name[name].enabled_by
            adjustments.append(f"{name} was ignored: it only applies while {controller} is on")
    return Validation(parameters=normalised, adjustments=tuple(adjustments))
