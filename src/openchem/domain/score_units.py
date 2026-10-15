"""Units for a derived score: strict, small, and with no conversions (`docs/DERIVED_SCORES_DESIGN.md` section 4).

A unit here is a product of symbols with integer exponents, and **the symbols are opaque and unrelated to each other**:
`eV` and `kcal` are different symbols, and `%` and `1` are different symbols. Two units are the same only when they are the
same product of the same symbols. That is deliberately less than a units library: a quiet conversion is the silent change of
meaning this project keeps meeting, so a formula that adds an energy in one unit to an energy in another is refused and the
person converts by hand. A conversion becomes possible only as a named, tested entry in a table that starts empty.

What this cannot do, stated so nobody trusts it for more: it catches adding an energy to a length, or taking the logarithm of
a dimensioned number. It cannot catch a wrong constant, because a literal is dimensionless.

Pure: no Qt, no chemistry.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass

#: The symbols a unit may be made of. CLOSED: a symbol not here is a typo or a unit nobody approved, and either way the definition
#: is refused rather than guessed at. This is a STARTER set, read off the unit strings the application's results carry today
#: (`units="eV"`, `"kcal/mol"`, `"g/mol"`, `"ppm"`, `"%"`, and so on). A symbol is added when an approved output (`score_outputs`) or a
#: result a person needs to declare calls for it; the spellings the results use (`A` and `Å`, `deg` and `degrees`, `""` and `dimensionless`)
#: are reconciled per approved output, in its `carried_as`, and not here.
SYMBOLS: frozenset[str] = frozenset(
    {"eV", "Hartree", "kcal", "kJ", "mol", "g", "mg", "mL", "L", "cm", "nm", "Å", "K", "e", "%", "ppm", "D", "deg", "ps", "kbar"}
)

#: The largest exponent a unit may carry. A unit like `eV^40` is a typo, and it keeps every product small.
MAX_UNIT_EXPONENT = 12


class UnitError(ValueError):
    """A unit that is not written correctly, or whose symbols are not approved."""


@dataclass(frozen=True)
class Unit:
    """A product of symbols with non-zero integer exponents, in one canonical order, so equality is structural."""

    #: `(symbol, exponent)` pairs, sorted by symbol, exponents never zero. Build one with `parse_unit`, or by multiplying others.
    parts: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        canonical = tuple(sorted((s, e) for s, e in self.parts if e != 0))
        if canonical != self.parts:
            raise ValueError("a Unit's parts are sorted by symbol and never carry a zero exponent; use `Unit.of`")

    @staticmethod
    def of(exponents: dict[str, int]) -> Unit:
        merged = {s: e for s, e in exponents.items() if e != 0}
        return Unit(tuple(sorted(merged.items())))

    @property
    def is_dimensionless(self) -> bool:
        return not self.parts

    def _as_dict(self) -> dict[str, int]:
        return dict(self.parts)

    def __mul__(self, other: Unit) -> Unit:
        total = self._as_dict()
        for symbol, exponent in other.parts:
            total[symbol] = total.get(symbol, 0) + exponent
        return Unit.of(total)

    def __truediv__(self, other: Unit) -> Unit:
        total = self._as_dict()
        for symbol, exponent in other.parts:
            total[symbol] = total.get(symbol, 0) - exponent
        return Unit.of(total)

    def __pow__(self, n: int) -> Unit:
        return Unit.of({symbol: exponent * n for symbol, exponent in self.parts})

    def __str__(self) -> str:
        if not self.parts:
            return "1"

        def side(items: list[tuple[str, int]]) -> str:
            return "*".join(s if e == 1 else f"{s}^{e}" for s, e in items)

        numerator = [(s, e) for s, e in self.parts if e > 0]
        denominator = [(s, -e) for s, e in self.parts if e < 0]
        top = side(numerator) if numerator else "1"
        return top if not denominator else f"{top}/{side(denominator)}"


#: Dimensionless: what a number literal is, what `ramp` gives, and what `sqrt`, `ln`, `log10` and `exp` require of their argument.
DIMENSIONLESS = Unit()

#: A unit's exponent: a whole number, with an optional minus sign. ASCII digits only.
_EXPONENT = re.compile(r"-?[0-9]+")


def _factor(text: str, symbols: Collection[str]) -> Unit:
    """`SYMBOL` or `SYMBOL^n`."""
    symbol, caret, exponent_text = text.partition("^")
    symbol = symbol.strip()
    if not symbol:
        raise UnitError(f"a unit factor needs a symbol: {text!r}")
    if symbol not in symbols:
        raise UnitError(f"{symbol!r} is not an approved unit symbol (the approved ones are {', '.join(sorted(symbols))})")
    exponent = 1
    if caret:
        exponent_text = exponent_text.strip()
        if not _EXPONENT.fullmatch(exponent_text):
            raise UnitError(f"the exponent of {symbol} must be a whole number, not {exponent_text!r}")
        exponent = int(exponent_text)
        if exponent == 0 or abs(exponent) > MAX_UNIT_EXPONENT:
            raise UnitError(f"the exponent of {symbol} must be a non-zero whole number up to {MAX_UNIT_EXPONENT}, not {exponent}")
    return Unit.of({symbol: exponent})


def _side(text: str, symbols: Collection[str]) -> Unit:
    factors = text.split("*")
    if any(not part.strip() for part in factors):
        raise UnitError(f"a unit has an empty factor: {text!r}")
    result = DIMENSIONLESS
    for part in factors:
        result = result * _factor(part, symbols)
    return result


def parse_unit(text: str, symbols: Collection[str] = SYMBOLS) -> Unit:
    """The unit written as `text`: `1`, `eV`, `kcal/mol`, `mg/mL`, `eV^2`, `1/eV`.

    The form is `numerator` or `numerator/denominator`, each a `*`-separated product of `SYMBOL` or `SYMBOL^n`, and at most one `/`, so
    there is one reading of every unit. `1` alone is the dimensionless unit, and an empty string is refused (write `1`), because
    "no unit written" must not be able to mean "dimensionless" by accident.
    """
    stripped = text.strip()
    if not stripped:
        raise UnitError("write 1 for a dimensionless unit; an empty unit is not one")
    if stripped.count("/") > 1:
        raise UnitError(f"a unit has at most one '/', so it has one reading: {text!r}")
    if "(" in stripped or ")" in stripped:
        raise UnitError(f"a unit has no parentheses: {text!r}")
    numerator_text, slash, denominator_text = stripped.partition("/")
    numerator = DIMENSIONLESS if numerator_text.strip() == "1" else _side(numerator_text, symbols)
    if not slash:
        return numerator
    if denominator_text.strip() == "1":
        raise UnitError(f"dividing by 1 is not a unit: {text!r}")
    return numerator / _side(denominator_text, symbols)
