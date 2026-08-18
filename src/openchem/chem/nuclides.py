"""Nuclides: what is known about one (Z, A), and about an element's set.

Reads `data/nuclides.json`, which `tools/build_nuclide_table.py` generates
from a committed NUBASE2020 snapshot. **No RDKit and no Qt** -- the
symbol/Z map comes from `elements.json` directly rather than through
`element_reference`, which imports RDKit lazily. That keeps this module
importable from anywhere and costs nothing.

## The granularity is the point

`ElementFacts` answers questions about an ELEMENT and `Nuclide` answers
them about a (Z, A). They are different quantities and neither belongs on
the other -- carbon has an electronegativity and no half-life, C-14 has a
half-life and no electronegativity. So this is a second read model
deliberately, where the melting points in branch 1 were fields on the
existing one.

## A half-life is not a float

Eight states and two dimensions; see `HalfLife`. Anything treating
`seconds` as the whole answer will eventually render a bound as a
measurement, which is the failure the qualifier exists to prevent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import NamedTuple
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data" / "nuclides.json"
_ELEMENTS = Path(__file__).resolve().parent / "data" / "elements.json"

#: The eight states of a half-life, as the generator writes them.
EXACT = "exact"
ESTIMATED = "estimated"
LOWER_BOUND = "lower_bound"
UPPER_BOUND = "upper_bound"
APPROXIMATE = "approximate"
STABLE = "stable"
PARTICLE_UNSTABLE = "particle_unstable"
UNAVAILABLE = "unavailable"

#: Qualifiers that carry a number which is NOT an exact measurement. The
#: UI must mark these; see `HalfLife.is_qualified`.
_INEXACT = frozenset({ESTIMATED, LOWER_BOUND, UPPER_BOUND, APPROXIMATE})


@dataclass(frozen=True)
class HalfLife:
    """A half-life, its qualifier, and its uncertainty -- two dimensions.

    **`seconds` ALONE IS NOT THE ANSWER.** `>4.6 zs` and `4.6 zs` carry
    the same number and mean different things, and a UI that reads only
    the float will render the first as the second. `qualifier` is what
    stops that.

    The two dimensions are independent because NUBASE evaluates them
    independently: 256 rows carry an estimated VALUE beside a measured
    BOUND on its uncertainty, and 38 have no value at all while carrying
    a real bound in the uncertainty column -- for those the bound IS the
    value, which the generator resolves.
    """

    seconds: float | None
    qualifier: str
    uncertainty_s: float | None = None
    uncertainty_qualifier: str | None = None

    @property
    def is_stable(self) -> bool:
        return self.qualifier == STABLE

    @property
    def is_known(self) -> bool:
        """Is there a number at all? Stable is not a number."""
        return self.seconds is not None

    @property
    def is_qualified(self) -> bool:
        """Is the number anything other than an exact measurement?

        The heatmap and the isotope table both ask this: a qualified value
        gets the same colour and an explicit mark, never silent promotion
        to an exact-looking datum.
        """
        return self.qualifier in _INEXACT


@dataclass(frozen=True)
class DecayMode:
    """One decay path and how often it is taken.

    `branching` is a percentage, or None where NUBASE records the mode
    without measuring how often it happens -- 1,755 of them. `qualifier`
    carries `?`, `<`, `>` or `~` where the source did; an unqualified
    entry with a branching is a measurement.
    """

    mode: str
    branching: float | None = None
    qualifier: str | None = None

    @property
    def is_measured(self) -> bool:
        return self.branching is not None and self.qualifier is None


class NuclideKey(NamedTuple):
    """What identifies one nuclear state.

    **`state_index`, NOT "level".** NUBASE's field is an isomer INDEX --
    0 is the ground state, 1 the first metastable state, and so on up to
    9 -- and calling it a level invites a later reader to treat `2` as an
    excitation energy or to compare it numerically as one. It orders the
    states of one nuclide and means nothing else.

    A type rather than a bare tuple because it is the identity contract:
    the SVG carries one of these, a click resolves one, and the write path
    refuses one. Three places reconstructing `(z, a, i)` by hand is where
    a click starts landing on the wrong thing.
    """

    z: int
    a: int
    state_index: int = 0

    @property
    def is_ground_state(self) -> bool:
        return self.state_index == 0


@dataclass(frozen=True)
class Nuclide:
    """One nuclear state -- a ground state unless `state_index` says
    otherwise."""

    z: int
    a: int
    symbol: str
    half_life: HalfLife
    decays: tuple[DecayMode, ...] = ()
    abundance: float | None = None
    jpi: str = ""
    mass_excess_kev: float | None = None
    #: 0 for a ground state; 1..9 for one of NUBASE's isomers.
    state_index: int = 0
    #: The source's OWN suffix for that state -- `m`, `n`, `p`, `q` -- so
    #: the UI writes `Tc-99m` from the data rather than inventing a
    #: notation for "index 1".
    state_label: str = ""

    @property
    def key(self) -> "NuclideKey":
        return NuclideKey(self.z, self.a, self.state_index)

    @property
    def is_ground_state(self) -> bool:
        return self.state_index == 0

    @property
    def name(self) -> str:
        """`U-238`, or `Tc-99m` for a metastable state."""
        return f"{self.symbol}-{self.a}{self.state_label}"

    @property
    def neutrons(self) -> int:
        return self.a - self.z

    @property
    def is_stable(self) -> bool:
        return self.half_life.is_stable

    @property
    def occurs_naturally(self) -> bool:
        """**Natural TERRESTRIAL abundance**, which is a narrower claim
        than "exists in nature" and much narrower than "is stable"."""
        return self.abundance is not None and self.abundance > 0.0


@lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads(_DATA.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _symbol_by_z() -> dict[int, str]:
    elements = json.loads(_ELEMENTS.read_text(encoding="utf-8"))["elements"]
    return {entry["atomic_number"]: symbol for symbol, entry in elements.items()}


@lru_cache(maxsize=1)
def _by_element() -> dict[str, tuple[Nuclide, ...]]:
    symbols = _symbol_by_z()
    grouped: dict[str, list[Nuclide]] = {}
    for entry in _raw()["nuclides"].values():
        symbol = symbols.get(entry["z"])
        if symbol is None:  # pragma: no cover - Z beyond the element table
            continue
        half_life = entry["half_life"]
        grouped.setdefault(symbol, []).append(
            Nuclide(
                z=entry["z"],
                a=entry["a"],
                symbol=symbol,
                half_life=HalfLife(
                    seconds=half_life.get("seconds"),
                    qualifier=half_life["qualifier"],
                    uncertainty_s=half_life.get("uncertainty_s"),
                    uncertainty_qualifier=half_life.get("uncertainty_qualifier"),
                ),
                decays=tuple(
                    DecayMode(d["mode"], d.get("branching"), d.get("qualifier"))
                    for d in entry.get("decays", ())
                ),
                abundance=entry.get("abundance"),
                jpi=entry.get("jpi", ""),
                mass_excess_kev=entry.get("mass_excess_kev"),
            )
        )
    return {
        symbol: tuple(sorted(found, key=lambda n: n.a))
        for symbol, found in grouped.items()
    }


@lru_cache(maxsize=1)
def _by_key() -> dict[tuple[int, int], Nuclide]:
    return {(n.z, n.a): n for group in _by_element().values() for n in group}


def nuclide(z: int, a: int) -> Nuclide | None:
    """One ground state, or None if the table has no such (Z, A)."""
    return _by_key().get((z, a))


def nuclides_for(symbol: str) -> tuple[Nuclide, ...]:
    """Every ground state of an element, by mass number."""
    return _by_element().get(symbol, ())


def attribution() -> str:
    """Who to credit, for anything that displays this data."""
    return _raw()["_about"]["attribution"]


#: Display units, largest first. The same ladder NUBASE writes in, so a
#: value read off the table and a value shown by this application use the
#: same words.
_DISPLAY_UNITS = (
    ("Yy", 3.1556952e31), ("Zy", 3.1556952e28), ("Ey", 3.1556952e25),
    ("Py", 3.1556952e22), ("Ty", 3.1556952e19), ("Gy", 3.1556952e16),
    ("My", 3.1556952e13), ("ky", 3.1556952e10), ("y", 3.1556952e7),
    ("d", 86400.0), ("h", 3600.0), ("m", 60.0), ("s", 1.0),
    ("ms", 1e-3), ("us", 1e-6), ("ns", 1e-9), ("ps", 1e-12),
    ("as", 1e-18), ("zs", 1e-21), ("ys", 1e-24),
)

#: What each qualifier puts in front of the number.
_PREFIX = {LOWER_BOUND: "> ", UPPER_BOUND: "< ", APPROXIMATE: "~"}


def format_half_life(half_life: HalfLife, *, compact: bool = False) -> str:
    """One half-life as text, **carrying its qualifier**.

    `compact` renders an estimated value with NUBASE's own trailing `#`
    instead of the word, for the one caller that has about six characters
    to work with -- a periodic-table cell, where "5 s (estimated)" would
    not fit and eliding it would drop exactly the part that says the
    number is not a measurement. The bounds and the approximation mark are
    already short and are unchanged, so there is one formatter and the two
    forms cannot drift apart on anything but that suffix.

    Written once here rather than in the atom drawing, the isotope table
    and the decay tree separately -- three formatters is three chances for
    "124 y" and "> 124 y" to become the same string somewhere.

    ASCII only, deliberately: this text is copied out, and this project
    has recorded three separate `UnicodeEncodeError`s from result lines
    meeting a cp1252 console.
    """
    if half_life.qualifier == STABLE:
        return "stable"
    if half_life.qualifier == PARTICLE_UNSTABLE:
        return "particle unstable"
    if half_life.seconds is None:
        return "not established"

    value, unit = half_life.seconds, "s"
    for name, size in _DISPLAY_UNITS:
        if half_life.seconds >= size:
            value, unit = half_life.seconds / size, name
            break
    else:
        value, unit = half_life.seconds / _DISPLAY_UNITS[-1][1], _DISPLAY_UNITS[-1][0]

    if value >= 100 or value == int(value):
        number = f"{value:.0f}"
    elif value >= 10:
        number = f"{value:.1f}"
    else:
        number = f"{value:.3g}"

    text = f"{_PREFIX.get(half_life.qualifier, '')}{number} {unit}"
    if half_life.qualifier == ESTIMATED:
        text += "#" if compact else " (estimated)"
    return text


# --- "longest-lived" is two questions -----------------------------------


def longest_lived_isotope(symbol: str) -> Nuclide | None:
    """The nuclide that lasts longest -- **which may be a STABLE one**.

    Carbon's answer is C-12, not C-14. This is what the atom drawing wants
    when it has to name an isotope for an element with no natural
    abundance, and there the two functions agree because such elements
    have no stable isotope by definition.
    """
    found = nuclides_for(symbol)
    if not found:
        return None
    stable = [n for n in found if n.is_stable]
    if stable:
        # Among stable nuclides "longest" is meaningless, so prefer the
        # most abundant -- which is the one anybody means.
        return max(stable, key=lambda n: (n.abundance or 0.0, -n.a))
    return _longest_by_half_life(found)


def longest_radioactive_isotope(symbol: str) -> Nuclide | None:
    """The longest-lived nuclide that actually decays, or None.

    Carbon's answer is C-14. **None is a real answer** -- an element whose
    table holds nothing radioactive has no half-life to plot, and the
    palette turns that into "not established" rather than into a colour.
    """
    decaying = [
        n for n in nuclides_for(symbol) if not n.is_stable and n.half_life.is_known
    ]
    return _longest_by_half_life(decaying) if decaying else None


def _longest_by_half_life(found) -> Nuclide | None:
    """Longest first, with anything unmeasured last.

    A bound ranks on its value: `>4.6 zs` really is at least that long,
    and pretending otherwise would sort it with the unknowns.
    """
    with_value = [n for n in found if n.half_life.is_known]
    if not with_value:
        return None
    return max(with_value, key=lambda n: (n.half_life.seconds or 0.0, -n.a))


def isotope_order(found) -> tuple[Nuclide, ...]:
    """The order an isotope table lists an element's nuclides in.

    **DECLARED AND TESTED, because "abundance then half-life" does not
    order the cases that matter.** A synthetic element has no abundances
    at all, a stable nuclide has no half-life to compare, and a bound is
    not a plain number:

        natural abundance, descending   ABSENT SORTS LAST, not as zero
        then stable before radioactive
        then half-life, descending      a bound ranks on its value; an
                                        unavailable one sorts last
        then mass number, ascending     the deterministic tie-break

    **ABSENT IS NOT ZERO**, and that distinction is the one a later
    convenience breaks: the first `or 0.0` somebody writes to tidy this
    up puts "nobody has measured any" in with "measured, and none".
    Carbon leads with C-12; technetium, which has no abundances at all,
    leads with Tc-97 at 4.21 My.
    """
    return tuple(sorted(found, key=_isotope_sort_key))


def _isotope_sort_key(n: Nuclide):
    has_abundance = n.abundance is not None
    has_half_life = n.half_life.is_known
    return (
        not has_abundance,                      # measured abundances first
        -(n.abundance or 0.0),                  # then the largest
        not n.is_stable,                        # stable before radioactive
        not has_half_life,                      # a number before none
        -(n.half_life.seconds or 0.0),          # then the longest-lived
        n.a,                                    # and finally by mass number
    )


# --- three predicates, and they are not the same question ---------------
#
#     has_natural_isotope    U yes   C yes   Tc no
#     has_stable_isotope     U NO    C yes   Tc no
#     has_radioactive_...    U yes   C yes   Tc yes
#
# Uranium separates the first two and carbon separates the second two, so
# `is_radioactive = not has_natural_isotope` is wrong about both. These
# stay three functions precisely so a later tidy-up cannot merge them.


def has_natural_isotope(symbol: str) -> bool:
    """Does any nuclide of this element occur naturally on Earth?"""
    return any(n.occurs_naturally for n in nuclides_for(symbol))


def has_stable_isotope(symbol: str) -> bool:
    """Does any nuclide of this element not decay at all?

    **Uranium is the case that matters**: naturally abundant and entirely
    radioactive. A radioactivity display built on natural occurrence gets
    it exactly backwards.
    """
    return any(n.is_stable for n in nuclides_for(symbol))


def is_radioactive(n: Nuclide) -> bool | None:
    """Does this ONE nuclide decay? None where nothing establishes it.

    **The classification is per-qualifier, derived from the source rather
    than chosen**, because "non-stable half-life" is too loose once a
    half-life has eight states:

        stable                  not radioactive
        any finite value        radioactive -- bounds and estimates too,
                                since a bound is still a decay
        particle unstable       RADIOACTIVE. Measured: all three rows
                                (3Li, 5Be, 6B) carry a real decay mode,
                                `p ?` and `2p ?` -- unstable with no
                                measured half-life, not unclassifiable
        a recorded decay mode   radioactive, whatever the half-life says
        nothing at all          cannot establish

    **ONE PREDICATE, so three callers cannot each read `qualifier` their
    own way** -- and asserted at THIS level rather than only through the
    element rollup below, which a mutation showed cannot reach it: every
    element owning a particle-unstable nuclide also owns several ordinary
    radioactive ones, so the rollup answers True either way.
    """
    if n.is_stable:
        return False
    if n.half_life.is_known or n.half_life.qualifier == PARTICLE_UNSTABLE:
        return True
    if n.decays:
        return True
    return None


def has_radioactive_isotope(symbol: str) -> bool | None:
    """Does any nuclide of this element decay? None if unknowable."""
    found = nuclides_for(symbol)
    if not found:
        return None
    if any(is_radioactive(n) for n in found):
        return True
    return False if any(n.is_stable for n in found) else None
