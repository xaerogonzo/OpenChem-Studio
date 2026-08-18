"""Electron configurations as structure, for drawing and for arithmetic.

`element_reference.py` already ships a configuration STRING per element
("[Ar] 3d6 4s2"). A string is the right thing to display and the wrong
thing to compute with, so this turns it into `(n, l, occupancy)` and
everything else works on that. **The string is an output here, never the
state.**

## Filling order and ionisation order are different orders

This is the whole reason the module exists. Electrons fill by increasing
`n + l` (Madelung), so 4s fills before 3d -- but an ion loses its
outermost electrons first, so 4s empties before 3d:

    Fe    [Ar] 3d6 4s2
    Fe2+  [Ar] 3d6          4s went first, though it arrived first
    Fe3+  [Ar] 3d5

The obvious implementation -- take an electron off the end of the
displayed string -- gets this wrong for exactly the elements anyone will
try first on a periodic table with +/- buttons.

## What this module claims, and what it does not

`neutral_configuration` returns a CURATED ground state: the shipped value,
which for the 20 known Aufbau exceptions (Cr, Cu, Mo, Pd, Pt, Au, ...) is
a measurement rather than a prediction.

`ion_configuration` prefers a reference entry and falls back to the
general rule, **and says which it used**. That distinction is not
decoration: a general rule answering confidently for every exotic
transition-metal ion is how a teaching aid starts asserting chemistry
nobody checked. Where neither applies it declines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from openchem.chem.element_reference import facts_for

#: Subshell letters in order of angular momentum quantum number.
_SUBSHELL_LETTERS = "spdfgh"

#: Noble gas cores, for expanding "[Ar] 3d6 4s2" into real occupancies.
_NOBLE_CORES = {"He": 2, "Ne": 10, "Ar": 18, "Kr": 36, "Xe": 54, "Rn": 86}

#: Electron counts that make an ion isoelectronic with a noble gas. Used
#: only as a fast pre-filter -- the real test is configuration equality,
#: because a matching COUNT alone would also call Fe2+ (24 electrons)
#: isoelectronic with chromium, which is true and not what the UI offers.
_NOBLE_ELECTRON_COUNTS = {2: "He", 10: "Ne", 18: "Ar", 36: "Kr", 54: "Xe", 86: "Rn"}

_TOKEN = re.compile(r"(\d)([spdfgh])(\d+)")


class ConfigurationUnavailable(ValueError):
    """No configuration can be given for this species.

    Raised rather than guessed -- an ion stripped past its own electron
    count, or an element with no shipped ground state.
    """


@dataclass(frozen=True, order=True)
class Subshell:
    """One subshell and how many electrons are in it."""

    n: int
    l: int  # noqa: E741 - the physics name; anything else reads worse here
    occupancy: int

    @property
    def label(self) -> str:
        return f"{self.n}{_SUBSHELL_LETTERS[self.l]}"

    @property
    def capacity(self) -> int:
        """2(2l+1) -- s holds 2, p holds 6, d holds 10, f holds 14."""
        return 2 * (2 * self.l + 1)

    @property
    def orbitals(self) -> int:
        return 2 * self.l + 1

    def spins(self) -> list[tuple[bool, bool]]:
        """Per orbital, whether the up and down slots are filled.

        **Hund's rule**: every orbital of a subshell takes one electron
        before any takes a second, which is why nitrogen's 2p draws as
        three separate up-arrows rather than a pair and a single.
        """
        singles = min(self.occupancy, self.orbitals)
        pairs = max(0, self.occupancy - self.orbitals)
        return [(index < singles, index < pairs) for index in range(self.orbitals)]


@dataclass(frozen=True)
class Configuration:
    """A full set of subshells, in filling order."""

    subshells: tuple[Subshell, ...]

    @property
    def electrons(self) -> int:
        return sum(s.occupancy for s in self.subshells)

    def shells(self) -> dict[int, int]:
        """Electrons per principal shell, for the ring diagram."""
        counts: dict[int, int] = {}
        for subshell in self.subshells:
            counts[subshell.n] = counts.get(subshell.n, 0) + subshell.occupancy
        return dict(sorted(counts.items()))

    def in_writing_order(self) -> tuple[Subshell, ...]:
        """The subshells sorted by n, then l -- how tables SPELL them.

        **Not the order they are stored in, and the difference is real
        chemistry rather than formatting.** Electrons fill 4s before 3d
        (Madelung), which is why `subshells` is kept in that order: it is
        what ionisation and Aufbau reason about. Every printed table
        writes iron as [Ar] 3d6 4s2, by shell.

        Storing one order and spelling the other keeps both honest. Using
        the filling order for the string would print [Ar] 4s2 3d6, which
        no reference does.
        """
        return tuple(sorted(self.subshells, key=lambda s: (s.n, s.l)))

    def to_string(self) -> str:
        """The conventional spelling, e.g. "1s2 2s2 2p3"."""
        return " ".join(f"{s.label}{s.occupancy}" for s in self.in_writing_order())

    def with_noble_core(self) -> str:
        """The compact spelling, e.g. "[Ar] 3d6 4s2"."""
        for symbol, count in sorted(_NOBLE_CORES.items(), key=lambda kv: -kv[1]):
            if count >= self.electrons:
                continue
            core = _fill_aufbau(count)
            # The core comparison uses FILLING order, because that is what
            # `_fill_aufbau` produces and what the storage order is.
            if tuple(core) == self.subshells[: len(core)]:
                outer = sorted(self.subshells[len(core) :], key=lambda s: (s.n, s.l))
                rest = " ".join(f"{s.label}{s.occupancy}" for s in outer)
                return f"[{symbol}] {rest}".strip()
        return self.to_string()


@dataclass(frozen=True)
class ConfigurationResult:
    """A configuration and where it came from.

    `source` is shown in the UI. "reference" means a curated ground state;
    "rule" means this module derived it, which is a weaker claim and is
    labelled as one.
    """

    configuration: Configuration
    source: str  # "reference" | "rule"
    charge: int = 0

    @property
    def is_derived(self) -> bool:
        return self.source == "rule"


def _madelung_order() -> list[tuple[int, int]]:
    """(n, l) pairs by increasing n+l, then by increasing n.

    The Madelung rule, which is why 4s (n+l=4) precedes 3d (n+l=5).
    """
    pairs = [(n, l) for n in range(1, 9) for l in range(0, min(n, 4))]
    return sorted(pairs, key=lambda nl: (nl[0] + nl[1], nl[0]))


def _fill_aufbau(electrons: int) -> list[Subshell]:
    """Fill `electrons` into subshells by the Madelung order.

    Used for noble-gas cores and as the fallback for adding electrons. It
    is a MODEL, not a measurement -- the 20 known exceptions are why the
    neutral configurations are read from the shipped table instead.
    """
    filled: list[Subshell] = []
    remaining = electrons
    for n, l in _madelung_order():
        if remaining <= 0:
            break
        capacity = 2 * (2 * l + 1)
        taken = min(capacity, remaining)
        filled.append(Subshell(n, l, taken))
        remaining -= taken
    if remaining > 0:  # pragma: no cover - would need an element past 8s
        raise ConfigurationUnavailable(f"cannot place {electrons} electrons")
    return filled


def _parse(text: str) -> tuple[Subshell, ...]:
    """Expand "[Ar] 3d6 4s2" into explicit subshells, in filling order."""
    subshells: list[Subshell] = []
    core = re.match(r"\[([A-Z][a-z]?)\]", text.strip())
    if core is not None:
        symbol = core.group(1)
        if symbol not in _NOBLE_CORES:
            raise ConfigurationUnavailable(f"unknown core [{symbol}]")
        subshells.extend(_fill_aufbau(_NOBLE_CORES[symbol]))
        text = text[core.end() :]
    for n, letter, count in _TOKEN.findall(text):
        subshells.append(Subshell(int(n), _SUBSHELL_LETTERS.index(letter), int(count)))
    # Filling order, so `with_noble_core` can compare a prefix and the
    # ring diagram sums in a stable order.
    subshells.sort(key=lambda s: (s.n + s.l, s.n))
    return tuple(subshells)


@lru_cache(maxsize=256)
def neutral_configuration(symbol: str) -> Configuration:
    """The curated ground state of a neutral atom.

    Read from the shipped table rather than derived, because 20 elements
    do not follow the Aufbau order and those are measurements. The
    generator that writes that table already asserts the occupancies sum
    to Z; `tests/test_element_reference.py` re-checks it.
    """
    facts = facts_for(symbol)
    if facts is None or not facts.electron_configuration:
        raise ConfigurationUnavailable(f"no shipped configuration for {symbol!r}")
    return Configuration(_parse(facts.electron_configuration))


#: Ion configurations where the general rule below is known to be wrong.
#:
#: **Empty on purpose, and that is a finding rather than an omission.**
#: The rule was checked against the ions people actually meet -- Fe2+/3+,
#: Cu+/2+, Cr2+/3+, Mn2+, Co2+, Ni2+, Zn2+, Ag+, and the main-group ions
#: -- and reproduces every one. An entry belongs here the moment a
#: measured ground state disagrees, and the machinery is in place so
#: adding one is a data change rather than a code change.
ION_REFERENCE: dict[tuple[str, int], str] = {}


def ion_configuration(symbol: str, charge: int) -> ConfigurationResult:
    """The configuration of an ion, preferring a reference entry.

    Cations lose from the highest `n` first, then the highest `l` within
    it -- **not** from the last subshell to be filled. Anions gain by the
    Aufbau order into the neutral atom's configuration.
    """
    key = (symbol, charge)
    if key in ION_REFERENCE:
        return ConfigurationResult(
            Configuration(_parse(ION_REFERENCE[key])), "reference", charge
        )

    neutral = neutral_configuration(symbol)
    if charge == 0:
        return ConfigurationResult(neutral, "reference", 0)

    electrons = neutral.electrons - charge
    if electrons < 0:
        raise ConfigurationUnavailable(
            f"{symbol}{charge:+d} would need {-electrons} electrons it does not have"
        )
    if electrons == 0:
        return ConfigurationResult(Configuration(()), "rule", charge)

    if charge > 0:
        return ConfigurationResult(
            Configuration(_remove(neutral.subshells, charge)), "rule", charge
        )
    return ConfigurationResult(
        Configuration(_add(neutral.subshells, -charge)), "rule", charge
    )


def _remove(subshells: tuple[Subshell, ...], count: int) -> tuple[Subshell, ...]:
    """Strip `count` electrons, outermost shell first.

    Highest `n` first, then highest `l` within that `n`. This is what
    makes Fe2+ come out as [Ar] 3d6 rather than [Ar] 3d4 4s2.
    """
    working = {(s.n, s.l): s.occupancy for s in subshells}
    for _ in range(count):
        occupied = [nl for nl, occ in working.items() if occ > 0]
        if not occupied:  # pragma: no cover - guarded by the caller
            raise ConfigurationUnavailable("no electrons left to remove")
        outermost = max(occupied, key=lambda nl: (nl[0], nl[1]))
        working[outermost] -= 1
    return tuple(
        Subshell(n, l, occ)
        for (n, l), occ in sorted(working.items(), key=lambda kv: (kv[0][0] + kv[0][1], kv[0][0]))
        if occ > 0
    )


def _add(subshells: tuple[Subshell, ...], count: int) -> tuple[Subshell, ...]:
    """Add `count` electrons by the Aufbau order into an existing set."""
    working = {(s.n, s.l): s.occupancy for s in subshells}
    for _ in range(count):
        for n, l in _madelung_order():
            capacity = 2 * (2 * l + 1)
            if working.get((n, l), 0) < capacity:
                working[(n, l)] = working.get((n, l), 0) + 1
                break
        else:  # pragma: no cover
            raise ConfigurationUnavailable("nowhere to put another electron")
    return tuple(
        Subshell(n, l, occ)
        for (n, l), occ in sorted(working.items(), key=lambda kv: (kv[0][0] + kv[0][1], kv[0][0]))
        if occ > 0
    )


def isoelectronic_noble_gas(configuration: Configuration) -> str | None:
    """The noble gas with this exact configuration, or None.

    **Configuration equality, not an electron count.** Counting alone
    would report Fe2+ (24 electrons) as isoelectronic with chromium --
    true, and not what a control offering "isoelectronic noble gas" is
    promising. Na+, F- and O2- all come out as Ne because they really do
    share its configuration; Fe2+ correctly comes out as nothing.
    """
    symbol = _NOBLE_ELECTRON_COUNTS.get(configuration.electrons)
    if symbol is None:
        return None
    return symbol if neutral_configuration(symbol).subshells == configuration.subshells else None


@dataclass(frozen=True)
class Nucleus:
    """What is in the middle of the drawing.

    `isotope` is carried because **a neutron count is not a property of an
    element**. Silicon does not have 14 neutrons; Si-28 does. The drawing
    says which it is showing rather than letting the number read as
    intrinsic.

    **`neutrons` IS OPTIONAL, and that is the whole point of this type.**
    An element with no naturally occurring isotope -- technetium,
    promethium, astatine, polonium, and every synthetic element -- has a
    proton count that is certain and no neutron count that can be named
    without choosing an isotope. Both facts are true at once, and the
    previous version could express neither: it raised, so the drawing had
    no nucleus at all and the caption fell back to a bare
    "Electrons: 84". Reported as part of "our periodic table is rather
    unreliable", with polonium as the screenshot.
    """

    protons: int
    neutrons: int | None
    isotope: str | None
    is_most_abundant: bool

    @property
    def has_neutron_count(self) -> bool:
        return self.neutrons is not None


def nucleus(symbol: str, mass_number: int | None = None) -> Nucleus:
    """Protons and neutrons, for a named isotope or the most abundant one.

    **TWO REFUSALS THAT MUST NOT MERGE**, which is what makes returning a
    partial nucleus safe rather than a widening of the contract:

        nucleus("Si", mass_number=99)   you named an isotope that does not
                                        exist -> RAISES, as it always has
        nucleus("Po")                   this element has no natural
                                        isotope -> a proton-only nucleus

    The first is a caller error about a specific nuclide. The second is a
    fact about the element, and refusing to draw anything for it was the
    bug. Refusing to INVENT a neutron count is still right, and is what
    `neutrons is None` says.
    """
    facts = facts_for(symbol)
    if facts is None:
        raise ConfigurationUnavailable(f"unknown element {symbol!r}")

    chosen = None
    if mass_number is not None:
        chosen = next((i for i in facts.isotopes if i.mass_number == mass_number), None)
        if chosen is None:
            raise ConfigurationUnavailable(f"no isotope {symbol}-{mass_number}")
    elif facts.isotopes:
        chosen = max(facts.isotopes, key=lambda i: i.abundance)

    if chosen is None:
        # No natural-abundance data. The proton count is not in doubt --
        # it IS the atomic number -- so the nucleus is real and only its
        # neutron count is unnameable without picking an isotope.
        return Nucleus(
            protons=facts.atomic_number,
            neutrons=None,
            isotope=None,
            is_most_abundant=False,
        )

    return Nucleus(
        protons=facts.atomic_number,
        neutrons=chosen.mass_number - facts.atomic_number,
        isotope=f"{symbol}-{chosen.mass_number}",
        is_most_abundant=mass_number is None,
    )
