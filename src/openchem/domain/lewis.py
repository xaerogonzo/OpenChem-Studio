"""Lewis acid/base findings: the data, with no engine attached.

Split from `chem/lewis.py` for the reason `domain/structure_issue.py` and
`domain/docking.py` are split from their engines -- a result travels
further than the thing that produced it.

**Why this is one result rather than five calculators.** Lewis character
lives in two worlds at once: hardness and electrophilicity are properties
of the whole molecule, while donor and acceptor roles belong to particular
atoms, and the interesting statements join them ("this soft molecule
donates through its carbon"). `CheckerResult` set the precedent for a
single result carrying heterogeneous findings, and this follows it.

The shape also has room for what is coming -- donor and acceptor numbers,
sigma donation and pi backbonding, NBO populations, energy-decomposition
terms -- without any consumer changing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from openchem.domain.common import ScientificResult
from openchem.domain.structure_issue import Basis


class LewisRole(str, Enum):
    """What an atom does with an electron pair.

    `AMBIPHILIC` is here from the first commit rather than added later,
    because the cases that need it are not exotic: a singlet carbene has a
    lone pair AND an empty p orbital, and carbon monoxide is a sigma donor
    AND a pi acceptor. Retrofitting a fourth value would touch every
    consumer, and every one of them would have been written assuming three.
    """

    DONOR = "donor"
    ACCEPTOR = "acceptor"
    AMBIPHILIC = "ambiphilic"
    NEITHER = "neither"


class LewisStrength(str, Enum):
    """How strongly, kept SEPARATE from the role.

    Role and strength are different questions and conflating them loses
    the answer to both: carbon monoxide is a strong sigma donor toward
    borane and a negligible Brønsted base, and "CO is a weak base" is only
    true of one of those.

    `UNKNOWN` is the honest default. Nothing offline can rank donor
    strength, and saying so is better than implying a ranking exists.
    """

    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    UNKNOWN = "unknown"


class AcceptorMechanism(str, Enum):
    """HOW an atom accepts a pair, not what kind of atom it is.

    "Lewis acid = empty p orbital" fits BF3 and AlCl3 and then fails on
    Fe(III), Zn(II), TiCl4, SO3, protonated carbonyls and essentially all
    of coordination chemistry. The mechanism is the durable abstraction;
    an empty p orbital is one member of it.
    """

    EMPTY_ORBITAL = "empty_orbital"
    LOW_LYING_PI_STAR = "low_lying_pi_star"
    LOW_LYING_SIGMA_STAR = "low_lying_sigma_star"
    VACANT_COORDINATION_SITE = "vacant_coordination_site"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LewisEvidence:
    """One reason an atom was classified as it was.

    A site collects a LIST of these because several independent rules
    routinely agree: boron in BF3 has an empty p orbital, a low-lying LUMO
    and a high electrophilicity index, and all three are separately true.
    Collapsing that to the word "acceptor" throws away the answer to the
    question people actually ask, which is why.

    There is no confidence percentage, for the reason the structure
    checker has none: it would be a number nobody measured. `basis` says
    whether the rule is arithmetic or judgement, in the vocabulary this
    project already uses.
    """

    rule: str
    basis: Basis
    mechanism: AcceptorMechanism | None = None
    #: Named quantities behind the rule -- LUMO energy, hardness, a Fukui
    #: value. Empty for a purely structural rule.
    supporting: dict[str, float] = field(default_factory=dict)
    note: str = ""


@dataclass(frozen=True)
class LewisSite:
    """One atom's Lewis character."""

    atom_index: int
    symbol: str
    role: LewisRole
    strength: LewisStrength = LewisStrength.UNKNOWN
    lone_pairs: int | None = None
    evidence: tuple[LewisEvidence, ...] = ()

    @property
    def mechanisms(self) -> tuple[AcceptorMechanism, ...]:
        seen = [e.mechanism for e in self.evidence if e.mechanism is not None]
        return tuple(dict.fromkeys(seen))


@dataclass(frozen=True, kw_only=True)
class LewisAnalysis(ScientificResult):
    """Everything known about a structure's Lewis character.

    `refused` works the way `OxidationStates` does: when the model does not
    apply, there is a reason and no numbers, rather than numbers nobody
    should trust.

    `summary`, `assumptions` and `limitations` are STORED TEXT rather than
    something a reader regenerates. This project is becoming
    explanation-heavy, and an explanation written where the analysis
    happened is the only one guaranteed to describe what the analysis
    actually did -- which is also what lets the AI assistant plugin quote
    rather than invent.
    """

    molecule_uuid: str
    sites: tuple[LewisSite, ...] = ()
    #: Whole-molecule conceptual-DFT quantities, in eV where they have
    #: units. Empty until a QM run has happened; Phase A fills nothing here.
    descriptors: dict[str, float] = field(default_factory=dict)
    refused: bool = False
    reason: str = ""
    summary: str = ""
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return not self.refused

    def donors(self) -> tuple[LewisSite, ...]:
        return tuple(
            s for s in self.sites if s.role in (LewisRole.DONOR, LewisRole.AMBIPHILIC)
        )

    def acceptors(self) -> tuple[LewisSite, ...]:
        return tuple(
            s for s in self.sites if s.role in (LewisRole.ACCEPTOR, LewisRole.AMBIPHILIC)
        )

    def site_for(self, atom_index: int) -> LewisSite | None:
        return next((s for s in self.sites if s.atom_index == atom_index), None)


@dataclass(frozen=True)
class AdductEvidence:
    """One line of evidence about a specific acid-base pair.

    Deliberately NOT ranked. The three lines answer different questions --
    how much enthalpy, whether the pairing is favoured at all, and how
    strong the orbital interaction is -- and which one is informative
    depends on the pair. Collapsing them into a single score would force
    an ordering that does not exist, and would also make it impossible to
    add electrostatic, dispersion, Pauli and charge-transfer terms later
    without changing what the number means.
    """

    #: Short id: "drago_wayland", "frontier_gap", "hsab_match".
    line: str
    label: str
    basis: Basis
    #: The number, in `units`. None when the line applies but could not be
    #: evaluated -- `note` says why.
    value: float | None = None
    units: str = ""
    note: str = ""

    def __bool__(self) -> bool:
        return self.value is not None


@dataclass(frozen=True, kw_only=True)
class LewisAdduct(ScientificResult):
    """What can be said about one acid binding one base.

    There is no `score` field and that is the point. `evidence` holds
    every line that could be evaluated, each with its own units and
    basis, and a reader compares them rather than trusting an aggregate
    nobody defined.
    """

    acid_uuid: str = ""
    base_uuid: str = ""
    acid_label: str = ""
    base_label: str = ""
    evidence: tuple[AdductEvidence, ...] = ()
    refused: bool = False
    reason: str = ""
    summary: str = ""
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return not self.refused

    def line(self, name: str) -> AdductEvidence | None:
        return next((e for e in self.evidence if e.line == name), None)

    def available(self) -> tuple[AdductEvidence, ...]:
        """Only the lines that produced a number."""
        return tuple(e for e in self.evidence if e.value is not None)
