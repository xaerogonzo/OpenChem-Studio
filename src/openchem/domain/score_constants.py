"""Named constants of a derived score: a value with a declared unit, used in a formula as a name (`docs/DERIVED_SCORES_DESIGN.md` section 11, slice 2).

A bare number in a formula has no unit of its own, and in `+`, `-`, `min`, `max`, `clamp` and `ramp` it takes the unit of what it is combined
with (`score_formula._adopt`). That is what makes `ramp(tpsa, 140, 60)` writable, and it costs two things: a threshold written in the wrong
unit is not caught, and a logarithm of a dimensioned quantity cannot be written at all, because there is no way to divide by a unit.

A named constant is the explicit alternative, and it is checked strictly. It has a name, a finite value and a unit in the same language as
every other unit (`score_units`), and the formula uses it as a NAME, which is not a number and so adopts nothing: `ramp(tpsa, hi, lo)` with
`hi = 140 Å^2` is accepted and with `hi = 140 nm^2` is refused, and `log10(mw / one)` with `one = 1 g/mol` is dimensionless. A constant shares the
names of the inputs, so a formula never has to decide which a name means, and one that nothing uses is refused like an input that nothing uses.

Pure: no Qt, no chemistry.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from openchem.domain.score_formula import FormulaError, Problem, check_input_names
from openchem.domain.score_units import Unit, UnitError, parse_unit

#: The most constants a definition may declare, separate from the inputs' limit: a score with a dozen thresholds is already a long definition.
MAX_CONSTANTS = 12


@dataclass(frozen=True)
class Constant:
    """One named constant of a definition."""

    #: The name the formula uses, under the rule for input names.
    name: str
    #: What it is worth. Finite, and a number the person typed: never a bool.
    value: float
    #: Its unit, in the language of `score_units` (`1` for a dimensionless weight).
    unit: str


def _refuse(name: str, message: str) -> FormulaError:
    return FormulaError(Problem.CONSTANT, f"constant {name!r}: {message}")


def check_constants(constants: Sequence[Constant], input_names: Collection[str]) -> dict[str, Unit]:
    """The units of the constants, by name, or a `FormulaError` (`Problem.CONSTANT`).

    Refused: more than `MAX_CONSTANTS`; a name that is not usable as one (the rule for inputs); a name an input or an earlier constant already
    has; a value that is not a finite number; and a unit that is not written correctly or names a symbol nobody approved. The mapping goes
    to `score_formula.check_definition` beside the inputs' units, which is also what refuses a constant the formula never uses.
    """
    if len(constants) > MAX_CONSTANTS:
        raise FormulaError(Problem.CONSTANT, f"a definition has at most {MAX_CONSTANTS} constants, not {len(constants)}")
    taken = set(input_names)
    units: dict[str, Unit] = {}
    for constant in constants:
        try:
            check_input_names([constant.name])
        except FormulaError as exc:
            raise _refuse(constant.name, exc.message) from None
        if constant.name in taken:
            kind = "an input" if constant.name not in units else "another constant"
            raise _refuse(constant.name, f"the name is already used by {kind}")
        if isinstance(constant.value, bool) or not isinstance(constant.value, (int, float)) or not math.isfinite(constant.value):
            raise _refuse(constant.name, f"the value must be a finite number, not {constant.value!r}")
        try:
            units[constant.name] = parse_unit(constant.unit)
        except UnitError as exc:
            raise _refuse(constant.name, str(exc)) from None
        taken.add(constant.name)
    return units


def constant_values(constants: Sequence[Constant]) -> dict[str, float]:
    """The values to evaluate a formula with, one per constant name."""
    return {constant.name: float(constant.value) for constant in constants}
