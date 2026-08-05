"""What a normal mode IS -- a stretch, a bend, a torsion.

WHY THIS EXISTS. A frequency list is a column of numbers, and a chemist
reading a computed spectrum wants to know which peak is the carbonyl
stretch, not which peak is mode 34. ORCA reports the displacement vectors
but never says what they mean, so the character is derived here.

HOW IT IS DECIDED, and the honest limits of it. A normal mode is a
concerted motion of the whole molecule; calling it "a stretch" is already
an approximation, and for a large molecule most modes are genuinely mixed.
So this classifies by which internal coordinate the displacement dominates
and REFUSES to label anything ambiguous, returning "" rather than guessing.
An unlabelled mode is honest; a mode labelled "stretch" when it is a
coupled ring deformation is worse than no label at all.

The rule, in order:

  stretch   the motion is mostly ALONG bonds -- displacement of bonded
            atoms is anti-parallel and aligned with the bond axis
  bend      bonded atoms move mostly PERPENDICULAR to their bond, and the
            motion is concentrated on a few atoms
  torsion   perpendicular motion spread across four-atom dihedrals rather
            than concentrated at one centre
  ""        none of the above dominated

Validated against water, whose three modes are textbook and unambiguous:
1637 cm-1 bend, 3787 and 3882 cm-1 stretches. That is a real check but a
small one, and it is the reason the thresholds are deliberately
conservative -- this labels the clear cases and stays quiet otherwise.
"""

from __future__ import annotations

import math

from rdkit import Chem

#: Fraction of the total motion that must lie along bond axes before a mode
#: is called a stretch. Conservative on purpose: the cost of a missing
#: label is a blank cell, the cost of a wrong one is a chemist trusting it.
_STRETCH_THRESHOLD = 0.60

#: The mirror threshold for perpendicular motion.
_BEND_THRESHOLD = 0.60

#: Below this, a mode has no meaningful displacement at all and gets no
#: label rather than an arbitrary one.
_NEGLIGIBLE = 1e-9

#: Above this, a perpendicular mode is reported as a bend rather than a
#: torsion. See `_is_soft` for the measurement that set it.
_TORSION_MAX_WAVENUMBER = 500.0


def classify_mode(
    mol: Chem.Mol,
    displacements: tuple[tuple[float, float, float], ...],
    wavenumber_cm1: float | None = None,
) -> str:
    """A one-word character for a normal mode, or "" when unclear.

    Never raises: a mode that cannot be classified is an ordinary outcome,
    and this runs inside a parser whose failure would lose the spectrum.
    """
    try:
        return _classify(mol, displacements, wavenumber_cm1)
    except Exception:  # noqa: BLE001 - a label is a nicety, the spectrum is not
        return ""


def _classify(
    mol: Chem.Mol,
    displacements: tuple[tuple[float, float, float], ...],
    wavenumber_cm1: float | None,
) -> str:
    if mol is None or not displacements:
        return ""
    if mol.GetNumAtoms() != len(displacements):
        return ""
    if mol.GetNumConformers() == 0:
        # Without geometry there are no bond axes to project onto, so the
        # question cannot be asked. Silence beats a guess.
        return ""

    conformer = mol.GetConformer()
    positions = [
        (
            conformer.GetAtomPosition(i).x,
            conformer.GetAtomPosition(i).y,
            conformer.GetAtomPosition(i).z,
        )
        for i in range(mol.GetNumAtoms())
    ]

    total = sum(_norm2(vector) for vector in displacements)
    if total < _NEGLIGIBLE:
        return ""

    along = 0.0
    across = 0.0
    for bond in mol.GetBonds():
        i = bond.GetBeginAtomIdx()
        j = bond.GetEndAtomIdx()
        axis = _unit(_subtract(positions[j], positions[i]))
        if axis is None:
            continue
        # The RELATIVE displacement of the two bonded atoms is what changes
        # a bond: two atoms moving together in the same direction is the
        # molecule translating, not the bond stretching.
        relative = _subtract(displacements[j], displacements[i])
        parallel = _dot(relative, axis)
        along += parallel * parallel
        across += max(_norm2(relative) - parallel * parallel, 0.0)

    motion = along + across
    if motion < _NEGLIGIBLE:
        return ""

    stretch_fraction = along / motion
    if stretch_fraction >= _STRETCH_THRESHOLD:
        return "stretch"
    if (1.0 - stretch_fraction) >= _BEND_THRESHOLD:
        # Perpendicular motion. A torsion twists about a central bond, so
        # it shows up as perpendicular motion at the ENDS of dihedrals with
        # comparatively little at the middle two atoms; a bend concentrates
        # at the apex atom instead.
        torsional = _looks_like_torsion(mol, displacements) and _is_soft(
            wavenumber_cm1
        )
        return "torsion" if torsional else "bend"
    return ""


def _is_soft(wavenumber_cm1: float | None) -> bool:
    """Whether a mode is low enough in frequency to be a real torsion.

    MEASURED, and the reason this bound exists. The geometric test alone
    labelled 11 of acetone's 24 modes torsional, including bands at 1226
    and 1372 cm-1 -- and acetone has exactly two methyl rotors. A methyl
    DEFORMATION (rock, umbrella) produces almost the same displacement
    pattern as a methyl torsion: the hydrogens move, the carbons barely do.
    Telling them apart properly needs the change in dihedral ANGLE, which
    this module does not compute.

    Rather than claim a distinction it cannot make, the label is restricted
    to where it is physically defensible. Torsional modes are SOFT --
    hindered internal rotation is a shallow potential, and methyl torsions
    sit near 100-300 cm-1 (acetone's are at 36 and 139 cm-1 in this very
    run). A 1372 cm-1 "torsion" is not one. Above the bound the mode is
    reported as a bend, which is the honest fallback.
    """
    if wavenumber_cm1 is None:
        return False
    return abs(wavenumber_cm1) <= _TORSION_MAX_WAVENUMBER


def _looks_like_torsion(
    mol: Chem.Mol, displacements: tuple[tuple[float, float, float], ...]
) -> bool:
    """Whether perpendicular motion sits at dihedral ENDS rather than an apex.

    Requires a rotatable four-atom path. A molecule with none -- water,
    every triatomic -- cannot be torsional, so this answers False and the
    caller says "bend", which is the correct answer for water's 1637 cm-1
    mode.
    """
    magnitudes = [math.sqrt(_norm2(vector)) for vector in displacements]
    if not magnitudes:
        return False

    best_ratio = 0.0
    for bond in mol.GetBonds():
        if bond.IsInRing() or bond.GetBondType() != Chem.BondType.SINGLE:
            continue
        i = bond.GetBeginAtom()
        j = bond.GetEndAtom()
        ends_i = [n.GetIdx() for n in i.GetNeighbors() if n.GetIdx() != j.GetIdx()]
        ends_j = [n.GetIdx() for n in j.GetNeighbors() if n.GetIdx() != i.GetIdx()]
        # BOTH ends must carry substituents for a dihedral to exist at all.
        # Requiring only two substituents TOTAL was wrong, and physics
        # caught it: every C-H bond qualified, so methane's v4 bends came
        # back as "torsion" -- and methane has no dihedral to twist. The
        # hydrogen end has no other neighbour, which is exactly the test.
        if not ends_i or not ends_j:
            continue
        ends = ends_i + ends_j
        centre = magnitudes[i.GetIdx()] + magnitudes[j.GetIdx()]
        periphery = sum(magnitudes[idx] for idx in ends) / len(ends)
        if centre < _NEGLIGIBLE:
            continue
        best_ratio = max(best_ratio, periphery / (centre / 2.0 + _NEGLIGIBLE))
    return best_ratio > 2.0


def _subtract(a, b) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm2(a) -> float:
    return _dot(a, a)


def _unit(a) -> tuple[float, float, float] | None:
    length = math.sqrt(_norm2(a))
    if length < _NEGLIGIBLE:
        return None
    return (a[0] / length, a[1] / length, a[2] / length)
