"""Check a derived-score formula from the command line (`docs/DERIVED_SCORES_DESIGN.md`).

    uv run python tools/check_score_formula.py "2 * a + b" --input a=eV --input b=eV --result eV
    uv run python tools/check_score_formula.py "ramp(x, 5, 1) + y" --input x=1 --input y=1 --result 1 --value x=3 --value y=0.25

`--input NAME=UNIT` declares an input and its unit (`1` is dimensionless), `--result UNIT` is the unit the definition declares, and
`--value NAME=NUMBER` gives a value to evaluate with (without any, only the definition is checked). It prints the formula as the
application will read it, the unit it works out to and the value, or the reason it was refused, and exits 0 when everything asked
for was accepted and 1 when anything was refused.

It exists so a formula can be tried without a project, and it is what reaches `domain/score_formula.py` until the application does.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from openchem.domain.score_constants import Constant, check_constants, constant_values
from openchem.domain.score_formula import FormulaError, Refusal, check_definition, evaluate, render
from openchem.domain.score_units import Unit, UnitError, parse_unit


def _pairs(items: Sequence[str], what: str) -> list[tuple[str, str]]:
    result = []
    for item in items:
        name, equals, rest = item.partition("=")
        if not equals or not name or not rest:
            raise ValueError(f"{what} {item!r} should be NAME=VALUE")
        result.append((name, rest))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("formula")
    parser.add_argument("--input", action="append", default=[], metavar="NAME=UNIT")
    parser.add_argument("--result", required=True, metavar="UNIT")
    parser.add_argument("--value", action="append", default=[], metavar="NAME=NUMBER")
    parser.add_argument("--constant", action="append", default=[], metavar="NAME=NUMBER,UNIT")
    args = parser.parse_args(argv)

    try:
        units: dict[str, Unit] = {name: parse_unit(unit) for name, unit in _pairs(args.input, "--input")}
        result = parse_unit(args.result)
        values = {name: float(number) for name, number in _pairs(args.value, "--value")}
        constants = []
        for name, rest in _pairs(args.constant, "--constant"):
            number, comma, unit = rest.partition(",")
            if not comma:
                raise ValueError(f"--constant {name}={rest!r} should be NAME=NUMBER,UNIT")
            constants.append(Constant(name, float(number), unit))
    except (ValueError, UnitError) as exc:
        print(f"refused: {exc}")
        return 1

    try:
        units.update(check_constants(constants, list(units)))
        formula = check_definition(args.formula, units, result)
    except FormulaError as exc:
        where = f" (at character {exc.position})" if exc.position is not None else ""
        print(f"refused [{exc.problem.value}]: {exc.message}{where}")
        return 1
    print(f"formula: {render(formula.tree)}")
    print(f"unit:    {result}")
    if not values:
        print("definition accepted; give --value NAME=NUMBER to evaluate it")
        return 0
    try:
        print(f"value:   {evaluate(formula, {**values, **constant_values(constants)})!r} {result}")
    except Refusal as exc:
        print(f"refused: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
