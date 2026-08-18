"""What a periodic-table cell's colour is allowed to mean.

**PURE. NO Qt, NO COLOURS.** A palette answers "where does this element
sit on this scale" and "what does that scale claim"; the dialog turns a
position into a fill. That split is what makes "what does this colour
mean" testable without building a window, the same reason
`periodic_table_dialog.describe()` is a plain function -- and
`tests/test_layering.py` requires it anyway, since `ui/` may not import
RDKit and these values come from `element_reference`.

## The range is DECLARED, never derived from the elements that have a value

A scale recomputed from "whichever elements happen to carry a number"
changes every other element's colour the day one entry is filled in, and
two screenshots of the same table stop being comparable. Every continuous
palette therefore carries its own `minimum`, `maximum` and `transform`,
and the legend prints all three.

`transform` exists because atomic weight is the case that forces it:
linear over 1..295 puts the whole of periods 1-4 in the bottom sixth of
the scale, so hydrogen through krypton are one colour. It is a declared
curve rather than a silent one.

## "Not established" is never the bottom of a scale

`position_for` returns None for an absent value and the dialog gives it
its own swatch. Several elements genuinely have no accepted
electronegativity, and fifteen have no measured melting point; colouring
those as "very low" would be the table inventing data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from openchem.chem.element_reference import ElementFacts, facts_for

#: The reference conditions the state-at-room-temperature palette means.
#: **Written down because "room temperature" is a convention**, and a
#: reader arriving with a boiling point that disagrees deserves to know
#: which one the table used.
REFERENCE_TEMPERATURE_C = 25.0
REFERENCE_PRESSURE = "1 bar"

_LINEAR = "linear"
_SQRT = "square root"


@dataclass(frozen=True)
class PaletteSpec:
    """A continuous scale, and everything the legend has to say about it."""

    key: str
    label: str
    units: str
    minimum: float
    maximum: float
    transform: str = _LINEAR

    def legend(self) -> str:
        """Self-contained, so a screenshot needs no memory of the combo."""
        units = self.units or "dimensionless"
        return (
            f"{self.label} · {_number(self.minimum)}–{_number(self.maximum)} "
            f"· {self.transform} · {units} · not established shown separately"
        )


@dataclass(frozen=True)
class ClassPalette:
    """A discrete scale: a closed set of named classes."""

    key: str
    label: str
    classes: tuple[str, ...]

    def legend(self) -> str:
        return f"{self.label} · " + ", ".join(self.classes)


def position_for(spec: PaletteSpec, value: float | None) -> float | None:
    """Where `value` sits on `spec`, as 0.0..1.0, or None if not established.

    Clamped at both ends, deliberately and testably: a value outside the
    declared range resolves to an endpoint rather than running off the
    colour ramp or raising. The alternative -- widening the range to fit --
    is the derived-range behaviour this module exists to avoid.
    """
    if value is None:
        return None
    low, high = spec.minimum, spec.maximum
    if high <= low:  # pragma: no cover - a malformed spec
        return 0.0
    fraction = (value - low) / (high - low)
    fraction = max(0.0, min(1.0, fraction))
    if spec.transform == _SQRT:
        return math.sqrt(fraction)
    return fraction


#: Continuous palettes over data this project already ships. The bounds
#: are the real extremes of each quantity, rounded outwards, so they do
#: not move when a value is added.
CONTINUOUS: dict[str, PaletteSpec] = {
    "electronegativity": PaletteSpec(
        "electronegativity", "Pauling electronegativity", "", 0.7, 4.0
    ),
    # Helium's 0.28 is the floor and francium's 2.60 the ceiling. A
    # declared 0.3 clipped helium against hydrogen's 0.31 -- caught by
    # the guard that checks a declared range against the shipped data,
    # which is the check that keeps "declared" from meaning "invented".
    "covalent_radius": PaletteSpec(
        "covalent_radius", "Covalent radius", "Å", 0.25, 2.65
    ),
    "van_der_waals_radius": PaletteSpec(
        "van_der_waals_radius", "Van der Waals radius", "Å", 1.1, 3.1
    ),
    # **THE CASE THAT FORCED `transform` TO EXIST.** Linear over this
    # range gives hydrogen 0.000 and krypton 0.28, so four whole periods
    # share the bottom of the ramp.
    "atomic_weight": PaletteSpec(
        "atomic_weight", "Relative atomic mass", "", 1.0, 295.0, _SQRT
    ),
    "melting_point": PaletteSpec(
        "melting_point", "Melting point", "°C", -260.0, 3500.0
    ),
}

#: Discrete palettes. `category` reproduces the colouring the table has
#: always had, and is the default.
DISCRETE: dict[str, ClassPalette] = {
    "category": ClassPalette(
        "category",
        "Element category",
        (
            "nonmetal", "noble_gas", "halogen", "alkali", "alkaline_earth",
            "metalloid", "transition", "post_transition", "lanthanide", "actinide",
        ),
    ),
    "block": ClassPalette("block", "Block", ("s", "p", "d", "f")),
    "state": ClassPalette(
        "state",
        f"State at {REFERENCE_TEMPERATURE_C:g} °C, {REFERENCE_PRESSURE}",
        ("solid", "liquid", "gas", "sublimes", "not established"),
    ),
}

#: The order the dialog offers them in. Category first because it is what
#: the table has always shown.
PALETTE_ORDER: tuple[str, ...] = (
    "category",
    "block",
    "state",
    "electronegativity",
    "covalent_radius",
    "van_der_waals_radius",
    "atomic_weight",
    "melting_point",
)


def label_for(key: str) -> str:
    if key in DISCRETE:
        return DISCRETE[key].label
    return CONTINUOUS[key].label


def legend_for(key: str) -> str:
    if key in DISCRETE:
        return DISCRETE[key].legend()
    return CONTINUOUS[key].legend()


def value_for(key: str, symbol: str) -> float | None:
    """The raw number a continuous palette reads, or None."""
    facts = facts_for(symbol)
    if facts is None:
        return None
    return {
        "electronegativity": facts.electronegativity,
        "covalent_radius": facts.covalent_radius,
        "van_der_waals_radius": facts.van_der_waals_radius,
        "atomic_weight": facts.atomic_weight,
        "melting_point": facts.melting_point_c,
    }.get(key)


def class_for(key: str, symbol: str) -> str | None:
    """The class a discrete palette puts this element in, or None."""
    facts = facts_for(symbol)
    if facts is None:
        return None
    if key == "category":
        return facts.category
    if key == "block":
        return facts.block
    if key == "state":
        return state_at_reference(facts)
    return None


def state_at_reference(facts: ElementFacts) -> str:
    """Solid, liquid, gas, sublimes -- or an admission.

    **DERIVED FROM THE TWO NUMBERS, EXCEPT WHERE IT CANNOT BE.** Melting
    and boiling points alone cannot tell you that arsenic sublimes: that
    is a fact about the phase diagram, and inferring it from a MISSING
    boiling point would put every superheavy in the same class. So
    sublimation is carried as source-stated data and everything else is
    derived here.

    Each branch needs only the number that decides it. An element that
    boils below the reference temperature is a gas whether or not anyone
    has measured its melting point -- helium, which has no melting point
    at 1 atm at all. One that melts above it is a solid whether or not
    its boiling point is known -- radium and protactinium.
    """
    if facts.sublimes_at_1_bar:
        return "sublimes"
    melting, boiling = facts.melting_point_c, facts.boiling_point_c
    if boiling is not None and boiling <= REFERENCE_TEMPERATURE_C:
        return "gas"
    if melting is not None and melting > REFERENCE_TEMPERATURE_C:
        return "solid"
    if melting is not None and boiling is not None:
        return "liquid"
    return "not established"


def display_value(key: str, symbol: str) -> str:
    """The number written under the symbol in a heatmap cell.

    A heatmap carries a fact by COLOUR, which this table's own rule
    forbids doing alone -- a grid distinguishing ten hues is unreadable to
    a fair number of people. So the value is printed as well.
    """
    value = value_for(key, symbol)
    if value is None:
        return "—"
    return _number(value)


def _number(value: float) -> str:
    if abs(value) >= 100 or value == int(value):
        return f"{value:g}"
    return f"{value:.2f}".rstrip("0").rstrip(".")
