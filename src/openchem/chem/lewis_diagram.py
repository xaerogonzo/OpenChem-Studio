"""What a Lewis structure says, as data. No chemistry, no drawing, no Qt.

This module is the contract between the two halves of the full Lewis
feature: `chem/lewis_builder.py` fills it in from RDKit, and
`chem/lewis_svg.py` draws it. **Neither is imported here, and that is the
point** -- a `LewisDiagram` can be built by hand in three lines, so a
renderer bug can never masquerade as a chemistry bug or the reverse.

**ZERO IS NOT UNKNOWN.** Every count is a `Known(n)` -- including
`Known(0)`, which is an ANSWER -- or an `Unknown(reason)`, which has no
`value` attribute at all and therefore cannot be summed, printed or drawn
as a number by accident. That is the type doing the work rather than a
convention someone has to remember.

The lone-pair overlay shipped exactly that bug and it took driving the app
to find: iron(III) drew no dots, was not refused, and the status bar said
"No lone pairs" -- the one claim the analysis had explicitly declined to
make. Here the arithmetic cannot reach that state, because `total()` is
contagious: one `Unknown` in a sum makes the sum `Unknown`.

**THE ELECTRON EQUATION, written down before it is asserted.** "Valence
electrons" is ambiguous between at least five populations and charged
species are where the ambiguity bites, so exactly one definition is used
here and the tests use the same one:

    sum over atoms of (group valence electrons)
      - total formal charge
    = 2 x localised bonding pairs
      + delocalised region electrons
      + 2 x lone pairs

Subtracting the charge is the part worth checking: an anion has MORE
electrons than its neutral atoms provide, so acetate is 23 - (-1) = 24 and
ammonium is 9 - (+1) = 8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class Known:
    """A count that was determined. `Known(0)` is an answer."""

    value: int

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class Unknown:
    """A count that could not be determined, and why.

    **Deliberately has no `value`.** Anything that tries to treat it as a
    number raises instead of quietly contributing zero, which is the
    failure this whole type exists to prevent.
    """

    reason: str

    def __str__(self) -> str:
        return "unknown"


#: Either of the two. Written as a union rather than one class with an
#: optional field so that reading `.value` off an unknown is an error at
#: the point of the mistake.
Quantity = Known | Unknown


def total(quantities) -> Quantity:
    """Sum, with UNKNOWN contagious.

    One undetermined part makes the whole undetermined -- never a total
    that silently omits it. The reasons are collected so the result can
    say which parts it could not account for.
    """
    reasons: list[str] = []
    running = 0
    for quantity in quantities:
        if isinstance(quantity, Unknown):
            if quantity.reason not in reasons:
                reasons.append(quantity.reason)
        else:
            running += quantity.value
    if reasons:
        return Unknown("; ".join(reasons))
    return Known(running)


class Status(Enum):
    """Four outcomes, because two would conflate different problems.

    **`CHEMISTRY_REFUSED` and `RENDERING_FAILED` must never share a
    message.** "I do not know how to represent this metal coordination"
    and "I know the answer and could not place a dot without a collision"
    have different causes and different fixes, and telling a user the
    second when it is the first sends them looking in the wrong place.
    """

    SUPPORTED = "supported"
    SUPPORTED_WITH_ABSTENTIONS = "supported with abstentions"
    CHEMISTRY_REFUSED = "chemistry refused"
    RENDERING_FAILED = "rendering failed"


@dataclass(frozen=True)
class Atom:
    """One atom of the diagram, in diagram coordinates.

    `valence_electrons` is the free atom's group count, carried as data
    rather than looked up, so this module needs no periodic table and no
    RDKit. The builder supplies it.
    """

    index: int
    symbol: str
    x: float
    y: float
    lone_pairs: Quantity
    valence_electrons: int
    formal_charge: int = 0
    isotope: int = 0

    @property
    def label(self) -> str:
        """What is written at the atom. Isotope, symbol, then charge.

        A Lewis structure draws hydrogens as their own atoms, so there is
        deliberately no implicit-hydrogen suffix here -- that is the
        canvas's convention, and it is the thing that makes this a
        different picture rather than the same one annotated.
        """
        text = f"{self.isotope}{self.symbol}" if self.isotope else self.symbol
        if self.formal_charge:
            magnitude = abs(self.formal_charge)
            sign = "+" if self.formal_charge > 0 else "-"
            text += sign if magnitude == 1 else f"{magnitude}{sign}"
        return text


@dataclass(frozen=True)
class BondPairs:
    """The LOCALISED bonding pairs of one connection.

    `Known(1)` for an ordinary single bond, `Known(2)` for a localised
    double. A bond inside a delocalised system carries only its localised
    part -- benzene's ring bonds are `Known(1)` each, and the remaining
    electrons live in a `Region`.
    """

    begin: int
    end: int
    pairs: Quantity


@dataclass(frozen=True)
class Region:
    """A delocalised system: which atoms, how many electrons, and its shape.

    **A REGION IS A RESULT, NOT AN ABSTENTION.** "pi system: 6 electrons"
    is the feature working; filing it under "bonds we could not draw"
    would report the best answer it has as a failure.

    `electrons` may still be `Unknown` -- pyrrole's sextet is completed by
    a nitrogen lone pair rather than by a varying bond order, and the
    resonance enumeration cannot see it. The region is real, the count is
    not determined, and those are different statements.
    """

    atom_indices: tuple[int, ...]
    electrons: Quantity
    is_ring: bool
    bonds: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class Abstention:
    """Something the diagram declined to represent, and why.

    Carries the subject so the UI can say *which* bond, rather than "some
    bonds were omitted" -- a message that tells nobody anything.
    """

    subject: str
    reason: str


@dataclass(frozen=True)
class Provenance:
    """Which molecule this diagram is of, and what produced it.

    The dialog is a SNAPSHOT: it shows the structure it was opened for
    and does not follow the editor. This is what lets it say so, and what
    makes a stale diagram diagnosable rather than merely wrong.
    """

    molblock_sha: str = ""
    structure_revision: int = 0
    analysis_version: str = ""
    rdkit_version: str = ""


@dataclass(frozen=True)
class Accounting:
    """The electron budget, in full, so a failure is diagnosable.

    A balance test that prints `assert 30 == 28` says nothing about which
    half is wrong. `describe()` prints all of it.
    """

    valence_electrons: Quantity
    localised_bonding_electrons: Quantity
    delocalised_electrons: Quantity
    lone_pair_electrons: Quantity

    @property
    def accounted(self) -> Quantity:
        return total(
            [
                self.localised_bonding_electrons,
                self.delocalised_electrons,
                self.lone_pair_electrons,
            ]
        )

    @property
    def balances(self) -> bool:
        """True only when BOTH sides are known and equal.

        An unknown never balances. Treating "could not tell" as agreement
        is the same mistake as treating it as zero.
        """
        accounted = self.accounted
        if isinstance(self.valence_electrons, Unknown) or isinstance(accounted, Unknown):
            return False
        return self.valence_electrons.value == accounted.value

    def describe(self) -> str:
        return (
            f"valence {self.valence_electrons} = "
            f"localised {self.localised_bonding_electrons} + "
            f"delocalised {self.delocalised_electrons} + "
            f"lone pairs {self.lone_pair_electrons} "
            f"(accounted {self.accounted})"
        )


@dataclass(frozen=True)
class LewisDiagram:
    """Everything needed to draw one Lewis structure, and nothing else."""

    status: Status
    atoms: tuple[Atom, ...] = ()
    bond_pairs: tuple[BondPairs, ...] = ()
    regions: tuple[Region, ...] = ()
    abstentions: tuple[Abstention, ...] = ()
    provenance: Provenance = field(default_factory=Provenance)
    #: Why the whole molecule was declined. Only set for
    #: `CHEMISTRY_REFUSED` and `RENDERING_FAILED`, and they are separate
    #: statuses precisely so this text can differ.
    reason: str = ""

    @property
    def accounting(self) -> Accounting:
        return Accounting(
            valence_electrons=Known(
                sum(atom.valence_electrons for atom in self.atoms)
                - sum(atom.formal_charge for atom in self.atoms)
            ),
            localised_bonding_electrons=_doubled(
                total([bond.pairs for bond in self.bond_pairs])
            ),
            delocalised_electrons=total([region.electrons for region in self.regions]),
            lone_pair_electrons=_doubled(total([atom.lone_pairs for atom in self.atoms])),
        )

    @property
    def drawable(self) -> bool:
        return self.status in (Status.SUPPORTED, Status.SUPPORTED_WITH_ABSTENTIONS)

    @property
    def formula(self) -> str:
        """Hill notation, from the atoms this diagram holds.

        Derived here rather than fetched from RDKit so the dialog can
        show it without `ui/` importing a chemistry toolkit -- the rule
        `tests/test_layering.py` enforces. It is also the honest source:
        this is the formula of the molecule as DRAWN, explicit hydrogens
        and all, which is what the reader is looking at.
        """
        counts: dict[str, int] = {}
        for atom in self.atoms:
            counts[atom.symbol] = counts.get(atom.symbol, 0) + 1
        if not counts:
            return ""
        order: list[str] = []
        # Hill: carbon first, then hydrogen, then everything alphabetically.
        for symbol in ("C", "H"):
            if symbol in counts:
                order.append(symbol)
        order += sorted(symbol for symbol in counts if symbol not in ("C", "H"))
        text = "".join(
            symbol + (str(counts[symbol]) if counts[symbol] > 1 else "") for symbol in order
        )
        charge = sum(atom.formal_charge for atom in self.atoms)
        if charge:
            magnitude = abs(charge)
            sign = "+" if charge > 0 else "-"
            text += sign if magnitude == 1 else f"{magnitude}{sign}"
        return text

    def summary(self) -> str:
        """One line for the dialog, saying which of the four this is."""
        if self.status is Status.CHEMISTRY_REFUSED:
            return f"Lewis structure unavailable: {self.reason}"
        if self.status is Status.RENDERING_FAILED:
            return f"Lewis structure could not be drawn: {self.reason}"
        if self.status is Status.SUPPORTED_WITH_ABSTENTIONS:
            return f"Lewis structure, with {len(self.abstentions)} abstention(s)."
        return "Lewis structure."


def _doubled(quantity: Quantity) -> Quantity:
    """Pairs to electrons, preserving an unknown rather than zeroing it."""
    if isinstance(quantity, Unknown):
        return quantity
    return Known(quantity.value * 2)
