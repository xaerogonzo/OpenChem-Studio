"""Quarks, the quantum numbers they add up to, and what that does NOT prove.

A hadron as its quark content, with the additive quantum numbers derived
from that content and an identification against the Particle Data Group's
summary tables [source:pdg2024].

## THIS IS A DELIBERATE REVERSAL, AND THE RECORD SAYS SO

`docs/ARCHITECTURE.md` carried this as a **DECISION** -- out of scope,
because "nothing in this application consumes a particle" and every layer
below the UI is built on atoms as the smallest unit. Its stated expiry was
"the day something downstream can read a baryon".

**THAT CONDITION IS NOT MET AND THIS DOES NOT MEET IT.** Nothing here
reaches a molecule, a property or a report; it was built because it was
wanted. The architecture entry now says exactly that rather than
pretending a gap was closed, because a DECISION vocabulary that can be
retired by doing the thing anyway is worth nothing to the next reader.

## DERIVED, NEVER ASSERTED

Charge, baryon number, strangeness, charm, bottomness, topness and the
third component of isospin are SUMS over the quark content. Not one of
them is stored on a particle row and read back: a row states what the PDG
prints, and the arithmetic is computed from the quarks, so the two can
disagree -- and `test_particle.py` asserts they do not, for every shipped
state. A table that carried its own charges could not be checked against
anything.

## GELL-MANN--NISHIJIMA IS THE CHECKSUM ON THE QUARK TABLE

    Q = I3 + (B + S + C + B' + T) / 2

It holds per quark, and both sides are additive, so it holds for any
composition by construction. That makes it useless as a test of the
composition logic and valuable as a test of the six-row table this module
hand-enters: a wrong sign or a mistyped third in ANY flavour breaks it.
The sign conventions it catches are the classic traps --

    s carries S = -1        c carries C = +1
    b carries B' = -1       t carries T = +1

-- the negatively-charged quarks carry NEGATIVE flavour numbers. Read off
the PDG's own section headers rather than recalled: the baryon tables
print "Λ BARYONS (S = -1, I = 0)" above "Λ0 = uds", and "Ω BARYONS
(S = -3, I = 0)" above "Ω- = sss".

## MATCHING QUANTUM NUMBERS IS NECESSARY AND NOT SUFFICIENT

**AND THE PDG SUPPLIES THE COUNTEREXAMPLE ITSELF.** Λ and Σ0 have the
SAME quark content:

    Λ BARYONS (S = -1, I = 0)   Λ0 = uds     1115.683 MeV
    Σ BARYONS (S = -1, I = 1)   Σ0 = uds     1192.642 MeV

Identical Q, B, S and I3 -- they differ in TOTAL isospin, which is not a
sum over quark content the way I3 is. So the derived numbers PROVABLY
cannot tell them apart, and `identify` reports `uds` as valid and not
uniquely identified rather than picking the lighter one.

Identity is a PDG row. The arithmetic is a consistency check on a claim,
never the claim itself -- the same split `valid_total_declaration` draws
between a shape a validator owns and a meaning a source owns.

## A NEUTRAL LIGHT MESON IS A SUPERPOSITION, WHICH THE SOURCE PRINTS

The meson tables head their light-unflavoured section with

    for I = 1 (pi, b, rho, a):  ud, (uu-dd)/sqrt(2), du
    for I = 0 (eta, eta', ...): c1(uu + dd) + c2(ss)

so pi0 is not a quark-antiquark PAIR at all, and the I = 0 states carry
mixing coefficients the table does not fix. A bare `u ubar` therefore
composes to a valid combination that this module refuses to name -- that
refusal is the PDG's own position, not a limitation of the arithmetic.

## NO PATH INTO CHEMISTRY

This module imports nothing from `openchem.chem`, touches no molecular
type, and no particle is reachable from `ProjectModel`. A particle must
never be serialised as a molecule, a crystal or a formulation, and
`test_particle.py` asserts all of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

#: The PDG edition every number here was read from. One constant rather
#: than the string repeated per row: a table where half the rows silently
#: came from a different edition is the drift this avoids.
PDG_EDITION = "S. Navas et al. (Particle Data Group), Phys. Rev. D 110, 030001 (2024)"


class Flavour(Enum):
    """The six quark flavours, by their PDG letters."""

    UP = "u"
    DOWN = "d"
    STRANGE = "s"
    CHARM = "c"
    BOTTOM = "b"
    TOP = "t"


@dataclass(frozen=True)
class FlavourNumbers:
    """One quark's additive quantum numbers, for a QUARK not an antiquark.

    **`Fraction`, never float.** A proton's charge is 2/3 + 2/3 - 1/3, and
    in binary floating point that is 0.9999999999999999 -- so an equality
    test against the PDG's +1 fails, and a tolerance would be a tolerance
    on a number that is exactly an integer. Thirds are exact here.
    """

    charge: Fraction
    isospin_3: Fraction
    strangeness: int = 0
    charm: int = 0
    bottomness: int = 0
    topness: int = 0

    #: Every quark carries B = +1/3. A field rather than a constant so an
    #: antiquark's -1/3 falls out of the same negation as everything else.
    baryon_number: Fraction = Fraction(1, 3)


_THIRD = Fraction(1, 3)
_TWO_THIRDS = Fraction(2, 3)
_HALF = Fraction(1, 2)

#: **HAND-ENTERED, AND GUARDED BY GELL-MANN--NISHIJIMA.** Six rows is
#: small enough to type and exactly large enough for a sign to go
#: unnoticed, which is why the identity above is asserted over every row
#: rather than spot-checked.
QUARK_FLAVOUR_NUMBERS: dict[Flavour, FlavourNumbers] = {
    Flavour.UP: FlavourNumbers(charge=_TWO_THIRDS, isospin_3=_HALF),
    Flavour.DOWN: FlavourNumbers(charge=-_THIRD, isospin_3=-_HALF),
    Flavour.STRANGE: FlavourNumbers(
        charge=-_THIRD, isospin_3=Fraction(0), strangeness=-1
    ),
    Flavour.CHARM: FlavourNumbers(charge=_TWO_THIRDS, isospin_3=Fraction(0), charm=1),
    Flavour.BOTTOM: FlavourNumbers(
        charge=-_THIRD, isospin_3=Fraction(0), bottomness=-1
    ),
    Flavour.TOP: FlavourNumbers(charge=_TWO_THIRDS, isospin_3=Fraction(0), topness=1),
}


@dataclass(frozen=True)
class Quark:
    """One quark or antiquark."""

    flavour: Flavour
    anti: bool = False

    @property
    def symbol(self) -> str:
        """`u` or `ubar`. ASCII, because this reaches result strings and a
        combining overbar has already cost this project a console."""
        return f"{self.flavour.value}bar" if self.anti else self.flavour.value

    @property
    def numbers(self) -> FlavourNumbers:
        """This quark's own contribution -- NEGATED throughout for an
        antiquark, which is what makes charge, baryon number and every
        flavour number come out right from one rule instead of six."""
        base = QUARK_FLAVOUR_NUMBERS[self.flavour]
        if not self.anti:
            return base
        return FlavourNumbers(
            charge=-base.charge,
            isospin_3=-base.isospin_3,
            strangeness=-base.strangeness,
            charm=-base.charm,
            bottomness=-base.bottomness,
            topness=-base.topness,
            baryon_number=-base.baryon_number,
        )


@dataclass(frozen=True)
class QuantumNumbers:
    """What a quark content adds up to. Every field is a SUM."""

    charge: Fraction
    baryon_number: Fraction
    strangeness: int
    charm: int
    bottomness: int
    topness: int
    isospin_3: Fraction

    @property
    def hypercharge(self) -> Fraction:
        """Y = B + S + C + B' + T."""
        return (
            self.baryon_number
            + self.strangeness
            + self.charm
            + self.bottomness
            + self.topness
        )

    @property
    def obeys_gell_mann_nishijima(self) -> bool:
        return self.charge == self.isospin_3 + self.hypercharge / 2


def derive(content: tuple[Quark, ...]) -> QuantumNumbers:
    """Add up a quark content. No table is consulted."""
    numbers = [quark.numbers for quark in content]
    return QuantumNumbers(
        charge=sum((n.charge for n in numbers), Fraction(0)),
        baryon_number=sum((n.baryon_number for n in numbers), Fraction(0)),
        strangeness=sum(n.strangeness for n in numbers),
        charm=sum(n.charm for n in numbers),
        bottomness=sum(n.bottomness for n in numbers),
        topness=sum(n.topness for n in numbers),
        isospin_3=sum((n.isospin_3 for n in numbers), Fraction(0)),
    )


class Composition(Enum):
    """What KIND of hadron a content is, before asking which one."""

    BARYON = "baryon"
    ANTIBARYON = "antibaryon"
    MESON = "meson"
    INVALID = "invalid"


def classify(content: tuple[Quark, ...]) -> Composition:
    """Three quarks, three antiquarks, or a quark-antiquark pair.

    **Anything else is INVALID rather than merely unusual.** Exotic
    hadrons -- tetraquarks, pentaquarks, glueballs -- are real and are out
    of scope here; calling them invalid would be wrong, so the refusal
    message says "not a baryon or a meson" rather than "not a particle".
    A mixed pair like `u d` is genuinely not a colour singlet.
    """
    if len(content) == 3 and all(not q.anti for q in content):
        return Composition.BARYON
    if len(content) == 3 and all(q.anti for q in content):
        return Composition.ANTIBARYON
    if len(content) == 2 and sum(1 for q in content if q.anti) == 1:
        return Composition.MESON
    return Composition.INVALID


@dataclass(frozen=True)
class ParticleState:
    """One PDG summary-table row, as printed.

    **The quantum numbers are NOT stored.** `content` is what the PDG
    prints beside the name, and everything additive is derived from it --
    see the module docstring. What IS stored is what arithmetic cannot
    give: the name, the total isospin, J and parity, and the measured
    mass and mean life.
    """

    name: str
    #: ASCII, for the reason `Quark.symbol` gives.
    symbol: str
    content: tuple[Quark, ...]
    #: TOTAL isospin. **NOT derivable from the content** -- that is the
    #: whole Lambda/Sigma0 point, and the reason this field exists.
    isospin: Fraction
    #: Spin J and parity P, as the PDG's `I(J^P)` column prints them.
    spin: Fraction
    parity: int
    #: MeV, with the PDG's stated uncertainty. Measured values, read from
    #: the summary tables rather than recalled.
    mass_mev: float
    mass_uncertainty_mev: float
    #: Seconds. None where the PDG prints a LIMIT rather than a value --
    #: the proton's entry is a lower bound on a lifetime nobody has
    #: measured, and storing 9e29 as though it were a measurement would
    #: turn "we have never seen one decay" into "it decays".
    mean_life_s: float | None
    #: What the PDG prints when there is no measured mean life.
    mean_life_note: str = ""

    @property
    def derived(self) -> QuantumNumbers:
        return derive(self.content)

    @property
    def content_symbol(self) -> str:
        return " ".join(quark.symbol for quark in self.content)


def _q(letter: str) -> Quark:
    return Quark(Flavour(letter))


def _qbar(letter: str) -> Quark:
    return Quark(Flavour(letter), anti=True)


#: The states this editor can name, every value read from the PDG 2024
#: summary tables [source:pdg2024] rather than recalled.
#:
#: **THE SPIN-1/2 BARYON OCTET PLUS OMEGA-MINUS, AND FOUR MESONS.** Not a
#: complete PDG mirror and not trying to be: this is the set whose quark
#: content the tables print unambiguously beside the name. The excited
#: states, and every neutral light meson, are deliberately absent -- see
#: `identify` for what happens when a composition reaches one.
PDG_STATES: tuple[ParticleState, ...] = (
    ParticleState(
        name="proton", symbol="p",
        content=(_q("u"), _q("u"), _q("d")),
        isospin=_HALF, spin=_HALF, parity=+1,
        mass_mev=938.27208816, mass_uncertainty_mev=0.00000029,
        mean_life_s=None,
        mean_life_note="no decay observed; the PDG prints a limit of "
                       "> 9 x 10^29 years (CL 90%)",
    ),
    ParticleState(
        name="neutron", symbol="n",
        content=(_q("u"), _q("d"), _q("d")),
        isospin=_HALF, spin=_HALF, parity=+1,
        mass_mev=939.5654205, mass_uncertainty_mev=0.0000005,
        mean_life_s=878.4,
    ),
    ParticleState(
        name="Lambda", symbol="Lambda0",
        content=(_q("u"), _q("d"), _q("s")),
        isospin=Fraction(0), spin=_HALF, parity=+1,
        mass_mev=1115.683, mass_uncertainty_mev=0.006,
        mean_life_s=2.617e-10,
    ),
    ParticleState(
        name="Sigma plus", symbol="Sigma+",
        content=(_q("u"), _q("u"), _q("s")),
        isospin=Fraction(1), spin=_HALF, parity=+1,
        mass_mev=1189.37, mass_uncertainty_mev=0.07,
        mean_life_s=0.8018e-10,
    ),
    ParticleState(
        name="Sigma zero", symbol="Sigma0",
        content=(_q("u"), _q("d"), _q("s")),
        isospin=Fraction(1), spin=_HALF, parity=+1,
        mass_mev=1192.642, mass_uncertainty_mev=0.024,
        mean_life_s=7.4e-20,
    ),
    ParticleState(
        name="Sigma minus", symbol="Sigma-",
        content=(_q("d"), _q("d"), _q("s")),
        isospin=Fraction(1), spin=_HALF, parity=+1,
        mass_mev=1197.449, mass_uncertainty_mev=0.029,
        mean_life_s=1.479e-10,
    ),
    ParticleState(
        name="Xi zero", symbol="Xi0",
        content=(_q("u"), _q("s"), _q("s")),
        isospin=_HALF, spin=_HALF, parity=+1,
        mass_mev=1314.86, mass_uncertainty_mev=0.20,
        mean_life_s=2.90e-10,
    ),
    ParticleState(
        name="Xi minus", symbol="Xi-",
        content=(_q("d"), _q("s"), _q("s")),
        isospin=_HALF, spin=_HALF, parity=+1,
        mass_mev=1321.71, mass_uncertainty_mev=0.07,
        mean_life_s=1.639e-10,
    ),
    ParticleState(
        name="Omega minus", symbol="Omega-",
        content=(_q("s"), _q("s"), _q("s")),
        isospin=Fraction(0), spin=Fraction(3, 2), parity=+1,
        mass_mev=1672.45, mass_uncertainty_mev=0.29,
        mean_life_s=0.821e-10,
    ),
    ParticleState(
        name="pion plus", symbol="pi+",
        content=(_q("u"), _qbar("d")),
        isospin=Fraction(1), spin=Fraction(0), parity=-1,
        mass_mev=139.57039, mass_uncertainty_mev=0.00018,
        mean_life_s=2.6033e-8,
    ),
    ParticleState(
        name="pion minus", symbol="pi-",
        content=(_q("d"), _qbar("u")),
        isospin=Fraction(1), spin=Fraction(0), parity=-1,
        mass_mev=139.57039, mass_uncertainty_mev=0.00018,
        mean_life_s=2.6033e-8,
    ),
    ParticleState(
        name="kaon plus", symbol="K+",
        content=(_q("u"), _qbar("s")),
        isospin=_HALF, spin=Fraction(0), parity=-1,
        mass_mev=493.677, mass_uncertainty_mev=0.015,
        mean_life_s=1.2380e-8,
    ),
    ParticleState(
        name="kaon minus", symbol="K-",
        content=(_q("s"), _qbar("u")),
        isospin=_HALF, spin=Fraction(0), parity=-1,
        mass_mev=493.677, mass_uncertainty_mev=0.015,
        mean_life_s=1.2380e-8,
    ),
)


class Verdict(Enum):
    """**THREE STATES, AND THE MIDDLE ONE IS THE POINT.**

    Forcing this into known/not-known is what would push the editor into
    guessing an identity for a valid combination that simply has no
    unique named state -- which `uds` genuinely does not.
    """

    INVALID = "invalid"
    VALID_UNIDENTIFIED = "valid_unidentified"
    IDENTIFIED = "identified"


@dataclass(frozen=True)
class Identification:
    """What a composition is, and what it is not."""

    verdict: Verdict
    composition: Composition
    numbers: QuantumNumbers | None
    #: Every PDG state whose content matches. One means identified; more
    #: than one means the arithmetic cannot choose, and NAMING them is the
    #: honest answer.
    candidates: tuple[ParticleState, ...] = ()
    reason: str = ""

    @property
    def state(self) -> ParticleState | None:
        return self.candidates[0] if self.verdict is Verdict.IDENTIFIED else None


def _same_content(left: tuple[Quark, ...], right: tuple[Quark, ...]) -> bool:
    """Order-insensitive: `uud` and `udu` are one content."""
    return sorted(q.symbol for q in left) == sorted(q.symbol for q in right)


def identify(content: tuple[Quark, ...]) -> Identification:
    """Classify a composition, then look for a PDG row -- in that order.

    **THE LOOKUP IS BY QUARK CONTENT, NEVER BY QUANTUM-NUMBER TUPLE.**
    Searching the table for a row whose (Q, B, S) happens to match is how
    "known particle" would quietly become "whatever came back": a
    tetraquark's numbers can coincide with a meson's, and `uds` matches
    two rows on every derived number there is. Content is the claim the
    PDG actually prints beside a name.
    """
    composition = classify(content)
    if composition is Composition.INVALID:
        return Identification(
            verdict=Verdict.INVALID,
            composition=composition,
            numbers=None,
            reason=(
                "not a baryon or a meson: this editor composes three quarks, "
                "three antiquarks, or one quark with one antiquark. Exotic "
                "hadrons are real and are out of scope here."
            ),
        )

    numbers = derive(content)
    candidates = tuple(
        state for state in PDG_STATES if _same_content(state.content, content)
    )

    if len(candidates) == 1:
        return Identification(
            verdict=Verdict.IDENTIFIED,
            composition=composition,
            numbers=numbers,
            candidates=candidates,
            reason=f"matches the PDG summary-table row for {candidates[0].name}.",
        )

    if len(candidates) > 1:
        names = ", ".join(state.name for state in candidates)
        return Identification(
            verdict=Verdict.VALID_UNIDENTIFIED,
            composition=composition,
            numbers=numbers,
            candidates=candidates,
            reason=(
                f"a valid {composition.value}, and this content is shared by "
                f"{names}. They differ in TOTAL isospin, which is not a sum "
                "over quark content the way the third component is, so the "
                "derived numbers cannot choose between them."
            ),
        )

    return Identification(
        verdict=Verdict.VALID_UNIDENTIFIED,
        composition=composition,
        numbers=numbers,
        reason=_no_candidate_reason(content, composition),
    )


def _no_candidate_reason(content: tuple[Quark, ...], composition: Composition) -> str:
    """Why nothing was named -- and the neutral-meson case is not a gap.

    A quark and its own antiquark is not a particle this table omits: the
    PDG heads its light-unflavoured section by stating that pi0 is
    `(uu - dd)/sqrt(2)` and the I = 0 mesons are `c1(uu + dd) + c2(ss)`.
    Those states are SUPERPOSITIONS, so no single pair names one, and
    saying so is the source's own position rather than a limitation here.
    """
    if composition is Composition.MESON:
        flavours = {quark.flavour for quark in content}
        if len(flavours) == 1:
            return (
                "a valid meson, and deliberately not named. A quark with its "
                "own antiquark is not a single physical state: the PDG prints "
                "pi0 as (u ubar - d dbar)/sqrt(2), and the I = 0 mesons as a "
                "mixture c1(u ubar + d dbar) + c2(s sbar). No one pair names "
                "any of them."
            )
    return (
        f"a valid {composition.value}, with no matching row in the states this "
        "editor carries. That set is the spin-1/2 baryon octet, Omega minus "
        "and four charged mesons -- not a complete PDG mirror, so this is not "
        "a claim that no such particle exists."
    )
