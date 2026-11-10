"""Even-cumulene (allene) axial stereo restored from SMILES.

RDKit's parser drops the chiral tag on ``=[C@]=`` / ``=[C@@]=`` even with
non-legacy stereo perception, and ``rdCIPLabeler`` does not assign P/M (or
p/m) on an allene. CIP Validation Suite VS231 is the measured case: labels
``2p 4p 7s``, engine name previously flat.

The helical letter is taken from the SMILES winding on an even-cumulene
centre (two or more cumulative double bonds, even count: P-93.5.1.4).
``@`` → P/p and ``@@`` → M/m. Lowercase is used when another specified
tetrahedral centre is present (the suite's TH+TH3 shape); that is a
stand-in for a full CIP pseudoasymmetry test, not a general CIP engine.

A tetrahedral ``@``/``@@`` that RDKit leaves as ``?`` (VS231's cyclohexyl
``7s``) is paired with that one helix: ``p`` with ``@`` is ``s`` (the
suite's one labelled point); flipping either bit flips the letter. That
is the pseudoasymmetric inversion, not a ranking of the extended
tetrahedron.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

HELIX_PROP = "_CumuleneHelix"
PAIRED_TETRA_PROP = "_CumulenePairedTetra"
AXIAL_LETTERS = frozenset({"p", "P", "m", "M"})
PAIRED_TETRA_LETTERS = frozenset({"r", "s", "R", "S"})

_TWO_LETTER_ORGANIC = frozenset({"Cl", "Br"})


def smiles_atom_windings(smiles: str) -> list[str | None]:
    """One winding per atom in SMILES order: ``@``, ``@@``, or None.

    Bracket atoms carry the winding; organic-subset atoms are None. Ring
    digits, bonds, dots and parentheses are skipped. The length must match
    ``Mol.GetNumAtoms()`` or the stamp is refused.
    """
    out: list[str | None] = []
    i = 0
    n = len(smiles)
    while i < n:
        ch = smiles[i]
        if ch == "[":
            close = smiles.find("]", i)
            if close < 0:
                break
            body = smiles[i + 1 : close]
            if "@@" in body:
                out.append("@@")
            elif "@" in body:
                out.append("@")
            else:
                out.append(None)
            i = close + 1
            continue
        if ch == "%":
            i += 3 if i + 2 < n and smiles[i + 1 : i + 3].isdigit() else 1
            continue
        if i + 1 < n and smiles[i : i + 2] in _TWO_LETTER_ORGANIC:
            out.append(None)
            i += 2
            continue
        if ch.isalpha() or ch == "*":
            out.append(None)
            i += 1
            continue
        i += 1
    return out


def is_even_cumulene_center(atom) -> bool:
    """True if *atom* is the interior of an even-length cumulated double-bond chain."""
    from rdkit import Chem

    if atom.GetDegree() != 2:
        return False
    bonds = list(atom.GetBonds())
    if len(bonds) != 2:
        return False
    if any(bond.GetBondType() != Chem.BondType.DOUBLE for bond in bonds):
        return False
    span = _cumulene_double_count(atom)
    return span >= 2 and span % 2 == 0


def _cumulene_double_count(center) -> int:
    """How many consecutive double bonds meet at *center*, walking both ways."""
    from rdkit import Chem

    neighbours = list(center.GetNeighbors())
    if len(neighbours) != 2:
        return 0

    def away(start, coming_from) -> int:
        count = 0
        atom = start
        prev = coming_from
        while True:
            nxt = None
            for bond in atom.GetBonds():
                other = bond.GetOtherAtom(atom)
                if other.GetIdx() == prev.GetIdx():
                    continue
                if bond.GetBondType() != Chem.BondType.DOUBLE:
                    continue
                nxt = other
                count += 1
                break
            if nxt is None:
                return count
            prev = atom
            atom = nxt

    return 2 + away(neighbours[0], center) + away(neighbours[1], center)


def _has_other_specified_tetrahedral(mol, center_idx: int) -> bool:
    from rdkit import Chem

    unspecified = Chem.ChiralType.CHI_UNSPECIFIED
    for atom in mol.GetAtoms():
        if atom.GetIdx() == center_idx:
            continue
        if atom.GetChiralTag() != unspecified:
            return True
    return False


def stamp_cumulene_helix_from_smiles(mol, smiles: str) -> None:
    """Stamp ``_CumuleneHelix`` / ``_CIPCode`` on even-cumulene centres tagged in *smiles*.

    Does not set an RDKit chiral tag: ``CHI_TETRAHEDRAL_*`` on an allene makes
    ``AssignCIPLabels`` raise, and ``CHI_ALLENE`` is not labelled. Atom
    properties survive ``AssignStereochemistry``.
    """
    windings = smiles_atom_windings(smiles)
    if len(windings) != mol.GetNumAtoms():
        return
    for idx, winding in enumerate(windings):
        if winding is None:
            continue
        atom = mol.GetAtomWithIdx(idx)
        if not is_even_cumulene_center(atom):
            continue
        other_in_smiles = any(
            other is not None for i, other in enumerate(windings) if i != idx
        )
        lowercase = other_in_smiles or _has_other_specified_tetrahedral(mol, idx)
        if winding == "@@":
            helix = "m" if lowercase else "M"
        else:
            helix = "p" if lowercase else "P"
        atom.SetProp(HELIX_PROP, helix)
        atom.SetProp("_CIPCode", helix)
    stamp_axis_paired_tetrahedral(mol, windings)


def stamp_axis_paired_tetrahedral(mol, windings: list[str | None]) -> None:
    """Stamp ``r``/``s`` on a SMILES-tagged tetrahedral that RDKit left unassigned.

    Needs exactly one even-cumulene helix already on the mol. Measured on
    CIP suite VS231: ``p`` and ``[C@H]`` → ``s``. Either bit flipped → ``r``.
    """
    if len(windings) != mol.GetNumAtoms():
        return
    helices = [atom.GetProp(HELIX_PROP) for atom in mol.GetAtoms() if atom.HasProp(HELIX_PROP)]
    if len(helices) != 1:
        return
    helix_m = helices[0].lower() == "m"
    for idx, winding in enumerate(windings):
        if winding is None:
            continue
        atom = mol.GetAtomWithIdx(idx)
        if atom.HasProp(HELIX_PROP):
            continue
        tetra_at = winding == "@@"
        letter = "r" if helix_m ^ tetra_at else "s"
        atom.SetProp(PAIRED_TETRA_PROP, letter)
        atom.SetProp("_CIPCode", letter)


def restore_cumulene_cip_after_labeller(mol) -> None:
    """Put helical and axis-paired tetrahedral letters back after ``AssignCIPLabels``."""
    for atom in mol.GetAtoms():
        if atom.HasProp(HELIX_PROP):
            atom.SetProp("_CIPCode", atom.GetProp(HELIX_PROP))
        elif atom.HasProp(PAIRED_TETRA_PROP):
            atom.SetProp("_CIPCode", atom.GetProp(PAIRED_TETRA_PROP))
