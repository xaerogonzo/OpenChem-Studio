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

from openchem.chem import nuclides as nuclide_data
from openchem.chem.element_reference import ElementFacts, facts_for

#: The reference conditions the state-at-room-temperature palette means.
#: **Written down because "room temperature" is a convention**, and a
#: reader arriving with a boiling point that disagrees deserves to know
#: which one the table used.
REFERENCE_TEMPERATURE_C = 25.0
REFERENCE_PRESSURE = "1 bar"

_LINEAR = "linear"
_SQRT = "square root"
_LOG10 = "log10"


@dataclass(frozen=True)
class PaletteSpec:
    """A continuous scale, and everything the legend has to say about it."""

    key: str
    label: str
    units: str
    minimum: float
    maximum: float
    transform: str = _LINEAR

    def scale_text(self) -> str:
        """The scale itself, without what happens to values off it.

        Split out so `HybridPalette` can name its OWN terminal classes
        rather than inheriting a sentence about "not established" that is
        only half its story.
        """
        units = self.units or "dimensionless"
        return (
            f"{self.label} · {_number(self.minimum)}–{_number(self.maximum)} "
            f"· {self.transform} · {units}"
        )

    def legend(self) -> str:
        """Self-contained, so a screenshot needs no memory of the combo."""
        return f"{self.scale_text()} · not established shown separately"


@dataclass(frozen=True)
class ClassPalette:
    """A discrete scale: a closed set of named classes."""

    key: str
    label: str
    classes: tuple[str, ...]

    def legend(self) -> str:
        return f"{self.label} · " + ", ".join(self.classes)


#: The half-life palette's two terminal classes.
#:
#: **A STABLE ISOTOPE IS NOT A VERY LARGE NUMBER.** What is carbon's
#: longest half-life? C-12 and C-13 do not decay, so the answer is not a
#: number at all -- and encoding it as 10^30 years would make the top of
#: the scale a lie while quietly reducing "has a stable isotope" to a
#: colour somebody has to interpret. It is a class, named in the legend.
#:
#: That is branch 1's rule at the BOTTOM of every scale -- "not
#: established is never the bottom" -- reaching the top, where it needs a
#: third state rather than `float | None`.
STABLE_CLASS = "has a stable isotope"
UNESTABLISHED_CLASS = "not established"


@dataclass(frozen=True)
class HybridPalette:
    """A continuous ramp with named terminal classes beside it.

    The classes belong to the PALETTE rather than being inferred by the
    dialog from a None, because "nothing this element is made of decays"
    and "nobody has measured one" are different claims and must not share
    a swatch.
    """

    spec: PaletteSpec
    terminal_classes: tuple[str, ...]
    #: What any marks printed in a cell mean. **A MARK THE LEGEND DOES
    #: NOT EXPLAIN IS NO BETTER THAN THE COLOUR IT REPLACED**: the whole
    #: reason a qualified value carries one is that a ramp colour cannot
    #: say "estimated", and a reader who cannot decode `#` is back where
    #: they started. Found by magnifying the rendered grid, with every
    #: test green -- the tooltip said it and a screenshot could not.
    marks: str = ""

    @property
    def key(self) -> str:
        return self.spec.key

    @property
    def label(self) -> str:
        return self.spec.label

    def legend(self) -> str:
        # "has a stable isotope, not established shown separately" reads
        # as though only the second one is, which is what the rendered
        # legend actually said.
        parts = [
            self.spec.scale_text(),
            f"shown separately: {', '.join(self.terminal_classes)}",
        ]
        if self.marks:
            parts.append(self.marks)
        return " · ".join(parts)


@dataclass(frozen=True)
class Shading:
    """What one cell of a hybrid palette shows.

    **EXACTLY ONE of `position` and `terminal` is ever set**, asserted
    over every element rather than left as a comment: a cell holding both
    would be on the ramp and off it at once, and the dialog would silently
    take whichever branch it tested first.

    `qualified` is the part a ramp would otherwise lose. Without it,
    `~1 s`, `<10 ps` and an estimated `2# ms` get the same cell as a
    measured value and read as measurements. Five colours for five
    qualifiers would be worse, so the numeric colour is unchanged and the
    mark rides with the text -- this table's existing rule that colour
    never carries a fact alone, applied to PRECISION rather than to
    magnitude.
    """

    position: float | None
    terminal: str | None
    display: str
    note: str
    qualified: bool = False


def position_for(spec: PaletteSpec, value: float | None) -> float | None:
    """Where `value` sits on `spec`, as 0.0..1.0, or None if not established.

    Clamped at both ends, deliberately and testably: a value outside the
    declared range resolves to an endpoint rather than running off the
    colour ramp or raising. The alternative -- widening the range to fit --
    is the derived-range behaviour this module exists to avoid.

    **THE TWO TRANSFORMS ACT AT DIFFERENT POINTS, AND THAT IS NOT AN
    OVERSIGHT.** `square root` bends the FRACTION -- a display curve that
    spreads out a crowded low end. `log10` is a CHANGE OF VARIABLE applied
    to the value and to both endpoints, because half-life spans
    twenty-eight orders of magnitude and no curve on a linear fraction
    reaches that: on a 0.01..1e28 range every element below thorium would
    round to the same 0.000. Both are pinned by
    `test_the_two_transforms_act_at_different_points`, so a later tidying
    pass that "unifies" them fails rather than silently recolouring the
    table.

    Both still map the declared endpoints to exactly 0.0 and 1.0, which is
    the property every caller actually depends on.
    """
    if value is None:
        return None
    low, high = spec.minimum, spec.maximum
    if spec.transform == _LOG10:
        if value <= 0:  # pragma: no cover - no shipped quantity reaches it
            return 0.0
        value, low, high = math.log10(value), math.log10(low), math.log10(high)
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
    # **DRIVEN BY EVALUATED STABILITY, NEVER BY NATURAL ABUNDANCE.** The
    # obvious shortcut -- colour anything carrying an abundance as stable
    # -- makes uranium and thorium stable, which is why branch 1 left this
    # mode out of the combo rather than shipping it wrong.
    "stability": ClassPalette(
        "stability",
        "Radioactivity",
        (STABLE_CLASS, "radioactive only", UNESTABLISHED_CLASS),
    ),
}

#: Ramps that also need terminal classes. Today there is one; the type
#: exists because the alternative was the dialog inferring the classes.
HYBRID: dict[str, HybridPalette] = {
    # **THE RANGE IS THE MEASURED ONE, ROUNDED OUTWARDS**, like every
    # other declared range here: livermorium's Lv-293 at 0.07 s is the
    # floor (log10 -1.155) and bismuth's Bi-209 at 2.01e19 y the ceiling
    # (log10 26.802). Bismuth alone occupies the top third, which is a
    # property of the data rather than a defect -- it was called stable
    # until its alpha decay was measured in 2003.
    #
    # log10 is DECLARED, for the reason atomic weight declares its square
    # root: the values span twenty-eight orders of magnitude, so a linear
    # ramp would give every element but bismuth and thorium one colour.
    "longest_half_life": HybridPalette(
        PaletteSpec(
            "longest_half_life",
            "Longest-lived radioactive isotope",
            "s",
            1e-2,
            1e28,
            _LOG10,
        ),
        (STABLE_CLASS, UNESTABLISHED_CLASS),
        marks="# = estimated from systematics; > < ~ = bounds and approximations",
    ),
}

#: The order the dialog offers them in. Category first because it is what
#: the table has always shown.
PALETTE_ORDER: tuple[str, ...] = (
    "category",
    "block",
    "state",
    # The two radioactivity modes sit together, and before the heatmaps:
    # they are two answers to one question, and reading them against each
    # other is what the second one exists for.
    "stability",
    "longest_half_life",
    "electronegativity",
    "covalent_radius",
    "van_der_waals_radius",
    "atomic_weight",
    "melting_point",
)


def label_for(key: str) -> str:
    if key in DISCRETE:
        return DISCRETE[key].label
    if key in HYBRID:
        return HYBRID[key].label
    return CONTINUOUS[key].label


def legend_for(key: str) -> str:
    if key in DISCRETE:
        return DISCRETE[key].legend()
    if key in HYBRID:
        return HYBRID[key].legend()
    return CONTINUOUS[key].legend()


def value_for(key: str, symbol: str) -> float | None:
    """The raw number a continuous palette reads, or None.

    None means "this element is not on the ramp", which for the half-life
    palette covers BOTH terminal classes -- the caller that needs to tell
    them apart is `half_life_shading`, and everything generic (the legend,
    the declared-range guard) only needs to know which values are plotted.
    """
    if key in HYBRID:
        best = _plotted_half_life(symbol)
        return None if best is None else best.half_life.seconds
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
    if key == "stability":
        return stability_class(symbol)
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


def stability_class(symbol: str) -> str:
    """Has a stable isotope, radioactive only, or cannot be established.

    **THE PREDICATES ARE ASKED IN ORDER AND NONE OF THEM IS
    `not has_natural_isotope`.** Uranium has a natural abundance and no
    stable isotope; technetium has neither. Reading abundance puts uranium
    in the wrong class and technetium in the right one by accident, which
    is the wrong kind of test passing.

    `has_radioactive_isotope` answers None where the table cannot say, and
    that becomes the third class rather than a guess in either direction.
    """
    if nuclide_data.has_stable_isotope(symbol):
        return STABLE_CLASS
    radioactive = nuclide_data.has_radioactive_isotope(symbol)
    if radioactive is None:
        return UNESTABLISHED_CLASS
    return "radioactive only" if radioactive else UNESTABLISHED_CLASS


def _plotted_half_life(symbol: str):
    """The nuclide the half-life ramp plots, or None for a terminal class.

    **ONE definition of "is this element on the ramp"**, so `value_for`
    and `half_life_shading` cannot come to disagree about it -- which
    would show up as an element the declared-range guard never checks
    while the grid happily colours it.
    """
    if nuclide_data.has_stable_isotope(symbol):
        return None
    best = nuclide_data.longest_radioactive_isotope(symbol)
    if best is None or best.half_life.seconds is None:
        return None
    return best


def half_life_shading(symbol: str) -> Shading:
    """Where an element sits on the half-life ramp, or which class it is in.

    Both "longest-lived" questions are asked here, which is why
    `chem/nuclides.py` keeps them as two functions: whether a STABLE
    isotope exists decides between the ramp and a terminal class, and only
    then does the longest RADIOACTIVE one supply a number.
    """
    spec = HYBRID["longest_half_life"].spec
    if nuclide_data.has_stable_isotope(symbol):
        return Shading(None, STABLE_CLASS, "stable", f"{spec.label}: {STABLE_CLASS}")
    best = _plotted_half_life(symbol)
    if best is None:
        return Shading(
            None,
            UNESTABLISHED_CLASS,
            "—",
            f"{spec.label}: {UNESTABLISHED_CLASS}",
        )
    return Shading(
        position_for(spec, best.half_life.seconds),
        None,
        nuclide_data.format_half_life(best.half_life, compact=True),
        f"{best.name}: {nuclide_data.format_half_life(best.half_life)}",
        qualified=best.half_life.is_qualified,
    )


def display_value(key: str, symbol: str) -> str:
    """The number written under the symbol in a heatmap cell.

    A heatmap carries a fact by COLOUR, which this table's own rule
    forbids doing alone -- a grid distinguishing ten hues is unreadable to
    a fair number of people. So the value is printed as well.
    """
    if key in HYBRID:
        return half_life_shading(symbol).display
    value = value_for(key, symbol)
    if value is None:
        return "—"
    return _number(value)


def _number(value: float) -> str:
    if abs(value) >= 100 or value == int(value):
        return f"{value:g}"
    return f"{value:.2f}".rstrip("0").rstrip(".")
