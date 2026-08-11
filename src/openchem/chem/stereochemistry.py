"""What a geometry did to a structure's stereochemistry.

Adopting a conformer, or rotating one into the drawing, replaces flat
coordinates with real ones -- and `AssignStereochemistryFrom3D` will then
label centres the drawing left open. Reported from the running app on a
benzobicyclo[2.2.2]octane:

    as drawn         [(6, 'R'), (14, '?'), (17, '?')]
    after adopting   [(6, 'R'), (14, 'S'), (17, 'S')]

**A CONFORMER CAN MAKE STEREOCHEMISTRY ASSIGNABLE; THAT IS NOT THE SAME
AS THE MOLECULE BEING STEREOCHEMICALLY SPECIFIED.** The label is a
consequence of the geometry that happened to be generated, not evidence
that the drawn structure specified it. Interconverting conformations,
symmetric environments, pseudoasymmetric centres and stereogenic
axes/planes all sit outside what one embedded conformer can settle. This
module exists so the application can SAY when a geometry has done this,
not because the perception is authoritative.

Four outcomes, and two of them are refusals:

    unchanged                commit silently, however far the atoms moved
    unspecified -> assigned  commit, and say so
    assigned -> DIFFERENT    refuse: that is a different compound
    assigned -> unspecified  refuse: perception going backwards after a
                             transform is a bug, not a result
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem

#: RDKit's marker for a centre it can see but cannot assign.
UNSPECIFIED = "?"


class StereochemistryConflict(ValueError):
    """A geometry would change stereochemistry the structure had specified.

    Raised rather than reported, because there is no presentation of "your
    R centre is now S" that makes committing it acceptable. The caller
    shows the message; nothing reaches the undo stack.
    """


@dataclass(frozen=True)
class StereoChange:
    """The difference between two structures' stereochemistry.

    Entries are `(kind, index, ...)` where kind is `"atom"` or `"bond"`,
    so a caller can report "2 stereocentres" and "1 double bond"
    separately -- they read differently to a chemist and collapsing them
    into one count loses that.
    """

    #: (kind, index, now) -- was unspecified, the geometry assigned it.
    newly_assigned: tuple[tuple[str, int, str], ...] = ()
    #: (kind, index, before, now) -- was assigned, and is now DIFFERENT.
    reassigned: tuple[tuple[str, int, str, str], ...] = ()
    #: (kind, index, before) -- was assigned, and is now unspecified.
    lost: tuple[tuple[str, int, str], ...] = ()
    #: False when the two structures are not the same graph, so no
    #: per-index comparison means anything. Treated as unsafe by
    #: `safe`, because it means something larger than coordinates moved.
    comparable: bool = True

    @property
    def safe(self) -> bool:
        """May this change be committed without asking anybody?

        Newly assigned stereochemistry is safe but not silent -- see
        `describe`. A reassignment is never safe: an explicitly drawn `R`
        that embeds as `S` is a different compound, and no status line
        makes that acceptable.
        """
        return self.comparable and not self.reassigned and not self.lost

    @property
    def quiet(self) -> bool:
        """Nothing happened worth telling anybody about."""
        return self.safe and not self.newly_assigned

    def describe(self) -> str:
        """One sentence for a status bar, or "" when there is nothing to say."""
        if not self.comparable:
            return "the structure changed in a way that could not be compared"
        if self.reassigned or self.lost:
            return self._describe_conflict()
        if not self.newly_assigned:
            return ""
        return f"defined {_count(self.newly_assigned)} your drawing left open"

    def _describe_conflict(self) -> str:
        parts = []
        if self.reassigned:
            worst = ", ".join(
                f"{kind} {index} {before}->{now}"
                for kind, index, before, now in self.reassigned[:3]
            )
            parts.append(f"would CHANGE {_count(self.reassigned)} ({worst})")
        if self.lost:
            parts.append(f"would leave {_count(self.lost)} unspecified")
        return " and ".join(parts)


def _count(entries) -> str:
    atoms = sum(1 for entry in entries if entry[0] == "atom")
    bonds = len(entries) - atoms
    parts = []
    if atoms:
        parts.append(f"{atoms} stereocentre{'s' if atoms != 1 else ''}")
    if bonds:
        parts.append(f"{bonds} double bond{'s' if bonds != 1 else ''}")
    return " and ".join(parts) or "nothing"


def _atom_labels(mol: Chem.Mol) -> dict[int, str]:
    """Every stereocentre RDKit can SEE, assigned or not.

    `includeUnassigned=True` says what is meant: a centre that is present
    and unlabelled is the case this module exists for.

    **It is not load-bearing, and a mutation proved it.** `compare_*`
    reads these dicts with `.get(index, UNSPECIFIED)`, so an atom that is
    simply absent already compares as unspecified and every outcome is
    identical with the flag off. Kept for readability rather than
    behaviour -- and recorded here so nobody re-derives that the hard way.
    """
    return {
        index: label
        for index, label in Chem.FindMolChiralCenters(
            mol, includeUnassigned=True, useLegacyImplementation=False
        )
    }


def _bond_labels(mol: Chem.Mol) -> dict[int, str]:
    """Double-bond stereo, by bond index.

    Only bonds that could carry it: `STEREONONE` on a single bond is not
    an unspecified double bond and counting it would drown the real ones.
    """
    labels: dict[int, str] = {}
    for bond in mol.GetBonds():
        if bond.GetBondType() != Chem.BondType.DOUBLE:
            continue
        stereo = bond.GetStereo()
        if stereo == Chem.BondStereo.STEREONONE:
            # A double bond with no possible geometry (terminal, or in a
            # small ring) is not "unspecified" -- it has nothing to
            # specify. RDKit reports both as STEREONONE, so the potential
            # is what tells them apart.
            if not bond.GetStereoAtoms():
                continue
            labels[bond.GetIdx()] = UNSPECIFIED
        elif stereo == Chem.BondStereo.STEREOANY:
            labels[bond.GetIdx()] = UNSPECIFIED
        else:
            labels[bond.GetIdx()] = str(stereo).replace("STEREO", "")
    return labels


def compare_stereochemistry(before: Chem.Mol, after: Chem.Mol) -> StereoChange:
    """What changed between two versions of the same structure.

    **The graphs are checked first.** Per-index comparison is meaningless
    across different molecules, and silently comparing them would produce
    a confident, wrong verdict -- so a mismatch returns `comparable=False`
    rather than a list of differences.
    """
    if _skeleton(before) != _skeleton(after):
        return StereoChange(comparable=False)

    newly_assigned: list[tuple[str, int, str]] = []
    reassigned: list[tuple[str, int, str, str]] = []
    lost: list[tuple[str, int, str]] = []

    for kind, first, second in (
        ("atom", _atom_labels(before), _atom_labels(after)),
        ("bond", _bond_labels(before), _bond_labels(after)),
    ):
        for index in sorted(set(first) | set(second)):
            was = first.get(index, UNSPECIFIED)
            now = second.get(index, UNSPECIFIED)
            if was == now:
                continue
            if was == UNSPECIFIED:
                newly_assigned.append((kind, index, now))
            elif now == UNSPECIFIED:
                lost.append((kind, index, was))
            else:
                reassigned.append((kind, index, was, now))

    return StereoChange(
        newly_assigned=tuple(newly_assigned),
        reassigned=tuple(reassigned),
        lost=tuple(lost),
    )


def _skeleton(mol: Chem.Mol) -> str:
    """The molecule with every stereo annotation removed.

    Two structures share a skeleton when they differ only in
    stereochemistry, which is precisely when a per-index comparison of
    that stereochemistry is meaningful.
    """
    flat = Chem.Mol(mol)
    Chem.RemoveStereochemistry(flat)
    return Chem.MolToSmiles(flat)
