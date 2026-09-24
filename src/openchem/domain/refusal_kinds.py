"""WHY a calculator declined, in the three senses a person can act on.

**"DID NOT PRODUCE AN ANSWER" WAS BEING READ AS ONE THING, AND IT IS FOUR.**
A calculator that ran and got nothing is, for the person looking at it:

    LIMIT        the method does not cover this molecule. Correct and
                 permanent; nothing to do (Joback has no group for a ring
                 tertiary amine; Kamlet-Jacobs is stated for C/H/N/O).
    NEEDS_INPUT  the method covers it and is missing a NUMBER only the
                 person can supply (Kamlet-Jacobs needs a loading density and
                 a condensed-phase enthalpy of formation). Actionable, and
                 the calculator can say exactly which.
    NEEDS_SETUP  the method covers it and this MACHINE lacks something (a
                 sidecar interpreter that is not configured). Actionable,
                 somewhere else.
    (a fault)    something broke. The absence of a kind, deliberately: there
                 is no `FAULT` member, because "not one of the three named
                 things" is exactly what makes a refusal a fault.

The Properties panel painted the first three all as "Not applicable" or all as
a red "Failed". A user standing in front of Detonation was told a method that
works "does not apply", when the truth was "type in two numbers".

**A CODE THAT IS NOT IN `REFUSAL_KINDS` IS NOT A LIMIT.** The rule is
fail-closed for the same reason `RESULT_KINDS` and `RESULT_STATUSES` are: a
new refusal code that nobody classified must surface as a fault somebody looks
at, never quietly as a permanent, ignorable limit. A producer that already
knows what it is declares the kind itself (`CalculationRefusal(kind=...)`);
this table is for the codes shared across producers, and it is what the
calculator census (PR-4) reports unknown codes against.

**THE KIND TRAVELS IN `provenance.parameters`, NEVER IN A NEW FIELD ON EVERY
RESULT TYPE.** A refusal already reaches the reader as a FAILED result whose
`provenance.parameters["refusal"]` is the code; the kind and the named inputs
travel beside it, so nothing that persists, copies or serialises a result had
to learn a new field. `status_of` is the ONE place they are combined into the
word a launcher shows.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

#: Refusal codes the scope layer itself raises. A calculator's own refusals
#: keep their own enums (`HansenRefusal`, `AromaticityRefusal`, ...); all of
#: them reach `provenance.parameters["refusal"]`, the key
#: `debug_drive.result_report` and the multicomponent guard read.
MULTICOMPONENT_UNSUPPORTED = "MULTICOMPONENT_UNSUPPORTED"
#: ChEMBL's exclusion flag: a transition metal or more than seven borons,
#: so there is no parent molecule to hand a compound-property calculator.
METAL_CONTAINING_UNSUPPORTED = "METAL_CONTAINING_UNSUPPORTED"
#: A `MethodDomain.ORGANIC` calculator handed a structure with no carbon.
NO_ORGANIC_COMPONENT = "NO_ORGANIC_COMPONENT"
#: An element the method's own table has no parameter for (Jensen's
#: increments, McGowan's volumes, MMFF/UFF, Lange's radii).
ELEMENT_OUTSIDE_PARAMETER_SET = "ELEMENT_OUTSIDE_PARAMETER_SET"
#: Not a limit of the method: the user has to supply something (a reference
#: structure, a partner molecule). Its kind is `NEEDS_INPUT`, so it is not a
#: limit and not a fault either.
INPUT_REQUIRED = "INPUT_REQUIRED"
#: A sidecar model whose interpreter is not configured on this machine.
SIDECAR_NOT_CONFIGURED = "SIDECAR_NOT_CONFIGURED"
#: Kamlet-Jacobs' two required inputs (`chem.energetics`). Each is named on
#: its own so a refusal can say WHICH is missing; when both are, both are
#: listed in `missing_inputs` under whichever code came first.
NO_LOADING_DENSITY = "NO_LOADING_DENSITY"
#: The condensed-phase enthalpy of formation, the other required input.
NO_ENTHALPY_OF_FORMATION = "NO_ENTHALPY_OF_FORMATION"
#: A pKa predictor ran cleanly and returned nothing for a centre the
#: calculator needs (`chem.solubility`). Not a crash and not a missing setup:
#: the model has no prediction for this structure, which is a limit of the
#: model.
NO_PKA_PREDICTION = "NO_PKA_PREDICTION"


class RefusalKind(str, Enum):
    """What a refusal means to somebody reading it. See the module docstring."""

    LIMIT = "limit"
    NEEDS_INPUT = "needs_input"
    NEEDS_SETUP = "needs_setup"


#: The codes that carry a kind with no producer declaring it. Deliberately
#: SMALL: only codes whose meaning is the same wherever they are raised.
#: A calculator-specific enum member (`HansenRefusal.NO_SOLVENT`, ...) is
#: declared by its producer with `kind=` rather than added here, because a
#: global table keyed on a bare string would let two calculators' unrelated
#: codes collide.
REFUSAL_KINDS: dict[str, RefusalKind] = {
    MULTICOMPONENT_UNSUPPORTED: RefusalKind.LIMIT,
    METAL_CONTAINING_UNSUPPORTED: RefusalKind.LIMIT,
    NO_ORGANIC_COMPONENT: RefusalKind.LIMIT,
    ELEMENT_OUTSIDE_PARAMETER_SET: RefusalKind.LIMIT,
    NO_PKA_PREDICTION: RefusalKind.LIMIT,
    INPUT_REQUIRED: RefusalKind.NEEDS_INPUT,
    NO_LOADING_DENSITY: RefusalKind.NEEDS_INPUT,
    NO_ENTHALPY_OF_FORMATION: RefusalKind.NEEDS_INPUT,
    SIDECAR_NOT_CONFIGURED: RefusalKind.NEEDS_SETUP,
}


def refusal_kind_of(code: str | None) -> RefusalKind | None:
    """The kind `REFUSAL_KINDS` gives `code`, or None -- which is a FAULT."""
    if not code:
        return None
    return REFUSAL_KINDS.get(code)


class InputProblem(str, Enum):
    """What is wrong with an input a refusal names."""

    #: Nothing was supplied.
    MISSING = "missing"
    #: Something was supplied and it cannot be used (not a number, negative
    #: where a positive is required).
    INVALID = "invalid"
    #: A usable number outside the range the method is stated for.
    OUT_OF_DOMAIN = "out_of_domain"


@dataclass(frozen=True)
class MissingInput:
    """One input a calculator needs, named so no view has to read prose.

    `parameter` is the calculator's OWN `CalculatorParameter.name`, so a view
    can focus that field in the settings dialog; `tests/test_refusal_kinds.py`
    checks it resolves. `units` is what the value must be given in -- kept
    separate from the parameter's label because a refusal is also read where
    no dialog is open (a batch cell, the reader, a driven-run report).
    """

    parameter: str
    units: str = ""
    problem: InputProblem = InputProblem.MISSING

    def to_dict(self) -> dict[str, str]:
        return {"parameter": self.parameter, "units": self.units, "problem": self.problem.value}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MissingInput:
        return cls(
            parameter=str(data["parameter"]),
            units=str(data.get("units", "")),
            problem=InputProblem(data.get("problem", InputProblem.MISSING.value)),
        )


#: The three keys a refusal writes into `provenance.parameters`. `refusal`
#: is the one every producer already wrote and every reader already reads.
REFUSAL_KEY = "refusal"
#: The kind the producer declared, as `RefusalKind.value`.
REFUSAL_KIND_KEY = "refusal_kind"
#: The inputs a NEEDS_INPUT refusal named, as `MissingInput.to_dict()` rows.
MISSING_INPUTS_KEY = "missing_inputs"


def refusal_parameters(
    code: str,
    kind: RefusalKind | None,
    missing_inputs: tuple[MissingInput, ...] = (),
) -> dict[str, Any]:
    """What a refusal puts in `Provenance.parameters`, assembled in ONE place.

    A batch cell and a Properties result must say the same thing about the
    same refusal, and both used to hand-write `{"refusal": code}`. JSON-plain
    on purpose: provenance is persisted with the project.
    """
    parameters: dict[str, Any] = {REFUSAL_KEY: code}
    if kind is not None:
        parameters[REFUSAL_KIND_KEY] = kind.value
    if missing_inputs:
        parameters[MISSING_INPUTS_KEY] = [item.to_dict() for item in missing_inputs]
    return parameters


def _parameters_of(result: object) -> dict[str, Any]:
    provenance = getattr(result, "provenance", None)
    parameters = getattr(provenance, "parameters", None)
    return parameters if isinstance(parameters, dict) else {}


def refusal_kind_of_result(result: object) -> RefusalKind | None:
    """The kind a RESULT carries, or None -- which is no claim at all.

    In the order `CalculationRefusal` resolves one: the kind the result
    DECLARED, then the kind `REFUSAL_KINDS` gives the code it names. The
    second is what lets the producers that build their result directly
    (`alignment`, `markush`, the pKa sidecar path, all of which write only
    `{"refusal": INPUT_REQUIRED}`) read as what they are without a line of
    change in any of them.

    Read with `getattr` for the reason `status_of` reads everything that way:
    it is asked of every result kind the reader admits, most of which carry
    no provenance parameters at all. A value that is not a `RefusalKind` is
    treated as absent -- a corrupted kind must not be trusted as a limit --
    and falls through to the code.
    """
    parameters = _parameters_of(result)
    raw = parameters.get(REFUSAL_KIND_KEY)
    if raw is not None:
        try:
            return RefusalKind(raw)
        except ValueError:
            pass
    code = parameters.get(REFUSAL_KEY)
    return refusal_kind_of(code) if isinstance(code, str) else None


def missing_inputs_of(result: object) -> tuple[MissingInput, ...]:
    """The inputs a NEEDS_INPUT result named, in the order they were raised."""
    raw = _parameters_of(result).get(MISSING_INPUTS_KEY)
    if not isinstance(raw, (list, tuple)):
        return ()
    items = []
    for entry in raw:
        try:
            items.append(MissingInput.from_dict(entry))
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(items)
