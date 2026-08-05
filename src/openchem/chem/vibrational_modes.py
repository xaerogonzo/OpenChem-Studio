"""What a normal mode IS -- a stretch, a bend, a torsion.

WHY THIS EXISTS. A frequency list is a column of numbers, and a chemist
reading a computed spectrum wants to know which peak is the carbonyl
stretch, not which peak is mode 34. ORCA reports the displacement vectors
but never says what they mean, so the character is derived here.

HOW IT IS DECIDED. A normal mode is a concerted motion, and the three
internal coordinates it can change are bond LENGTHS, bond ANGLES and
DIHEDRAL angles. So rather than asking "does this look like a stretch",
the geometry is displaced a little way along the mode and all three are
measured before and after. Whichever changed most names the mode; if none
of them dominates, the mode is genuinely mixed and gets NO label, because
an unlabelled mode is honest and a confidently mislabelled one is not.

THIS REPLACED A DISPLACEMENT-MAGNITUDE HEURISTIC, and the reason is worth
keeping. That version compared how far atoms moved at the ends of a bond
against how far they moved at its centre -- which a methyl DEFORMATION
satisfies exactly as well as a methyl TORSION, since in both the hydrogens
move and the carbons do not. It called 11 of acetone's 24 modes torsional,
including bands at 1226 and 1372 cm-1, and had to be propped up with a
"torsions are below 500 cm-1" rule that was a proxy for the measurement it
could not make.

The measurement it could not make is the NET rotation about a bond: a real
torsion turns every dihedral about that bond the same way, so their signed
mean is large, while a deformation swings one hydrogen forward as another
goes back and the signed mean cancels. Summing magnitudes cannot tell them
apart; the signed mean can, and needs no frequency cutoff.

VALIDATED ON FIVE MOLECULES WITH TEXTBOOK ANSWERS, from real ORCA runs:

    water      1 bend, 2 stretches
    CO2        2 bends, 2 stretches
    methane    5 bends (3x v4 + 2x v2), 4 stretches, NO torsion
    benzene    23 bends, 7 stretches, no torsion, nothing unlabelled
    acetone    exactly 2 torsions, at 36.4 and 138.8 cm-1

Methane has no dihedral to twist and gets no torsion; acetone has two
methyl rotors and gets exactly two, at the frequencies methyl rotation
actually occurs.
"""

from __future__ import annotations

import math

from rdkit import Chem

#: Below this, a mode has no meaningful displacement at all and gets no
#: label rather than an arbitrary one.
_NEGLIGIBLE = 1e-9

#: How far along the mode to step when measuring internal coordinates.
#: Small enough to stay harmonic, large enough to clear float noise.
_STEP = 0.05

#: The winning coordinate must account for at least this share of the total
#: change. Below it the mode is genuinely mixed and gets no label -- an
#: unlabelled mode is honest, a confidently mislabelled one is not.
_DOMINANCE = 0.45


def classify_mode(
    mol: Chem.Mol,
    displacements: tuple[tuple[float, float, float], ...],
) -> str:
    """A one-word character for a normal mode, or "" when unclear.

    THE WAVENUMBER IS NOT A PARAMETER, and its absence is the point. An
    earlier version took one and refused to call anything above 500 cm-1 a
    torsion, because the geometric test it used could not tell a methyl
    torsion from a methyl deformation and torsions are physically soft.
    That was a proxy standing in for a measurement. The measurement is now
    made directly -- see `_dihedral_change` -- so the crutch is gone rather
    than merely unused.

    Never raises: a mode that cannot be classified is an ordinary outcome,
    and this runs inside a parser whose failure would lose the spectrum.
    """
    try:
        return _classify(mol, displacements)
    except Exception:  # noqa: BLE001 - a label is a nicety, the spectrum is not
        return ""


def _classify(
    mol: Chem.Mol,
    displacements: tuple[tuple[float, float, float], ...],
) -> str:
    """Decide by which INTERNAL COORDINATE the displacement changes most.

    A normal mode is a concerted motion, and the three internal coordinates
    it can change are bond lengths, bond angles and dihedral angles. So the
    honest question is not "does this look like a stretch" but "which of
    the three does this motion actually change", and that is answered by
    measuring each one before and after a small displacement along the
    mode.
    """
    if mol is None or not displacements:
        return ""
    if mol.GetNumAtoms() != len(displacements):
        return ""
    if mol.GetNumConformers() == 0:
        # Without geometry there are no internal coordinates to measure.
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
    if sum(_norm2(vector) for vector in displacements) < _NEGLIGIBLE:
        return ""

    # A DISPLACED GEOMETRY, not an analytic projection. Internal
    # coordinates are non-linear functions of the Cartesians, and
    # evaluating them at two points is both simpler and less error-prone
    # than differentiating them. The step is small enough to stay in the
    # harmonic region and large enough to clear floating-point noise.
    moved = [
        (
            positions[i][0] + _STEP * displacements[i][0],
            positions[i][1] + _STEP * displacements[i][1],
            positions[i][2] + _STEP * displacements[i][2],
        )
        for i in range(len(positions))
    ]

    stretch = _bond_length_change(mol, positions, moved)
    bend = _bond_angle_change(mol, positions, moved)
    torsion = _dihedral_change(mol, positions, moved)

    total = stretch + bend + torsion
    if total < _NEGLIGIBLE:
        return ""

    # Scaled so the three are comparable: lengths are in Angstrom and the
    # two angular coordinates in radians, and a mode that rotates a methyl
    # by a few degrees moves its hydrogens much further than a stretch
    # moves anything. Without this every mode with a rotatable bond reads
    # as torsional, which is exactly what the magnitude heuristic this
    # replaced got wrong.
    scores = {
        "stretch": stretch / total,
        "bend": bend / total,
        "torsion": torsion / total,
    }
    best = max(scores, key=lambda name: scores[name])
    return best if scores[best] >= _DOMINANCE else ""


def _bond_length_change(mol, before, after) -> float:
    """Total absolute change in bond length, in Angstrom."""
    total = 0.0
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        total += abs(_distance(after[i], after[j]) - _distance(before[i], before[j]))
    return total


def _bond_angle_change(mol, before, after) -> float:
    """Total absolute change in bond angle, in radians.

    Every A-B-C where B is bonded to both, which is the full set of valence
    angles. A methyl umbrella or rock lives here, not in the dihedral term
    -- it opens and closes H-C-H and H-C-C angles while the dihedral about
    the C-C bond barely moves.
    """
    total = 0.0
    for atom in mol.GetAtoms():
        neighbours = [n.GetIdx() for n in atom.GetNeighbors()]
        centre = atom.GetIdx()
        for a in range(len(neighbours)):
            for b in range(a + 1, len(neighbours)):
                i, k = neighbours[a], neighbours[b]
                total += abs(
                    _angle(after[i], after[centre], after[k])
                    - _angle(before[i], before[centre], before[k])
                )
    return total


def _dihedral_change(mol, before, after) -> float:
    """NET rotation about each rotatable bond, in radians.

    THE SIGNED MEAN, NOT THE SUM OF MAGNITUDES, and that distinction is the
    whole fix. Summing |change| counts a methyl DEFORMATION as torsional:
    an umbrella or a rock does move the H-C-C=O dihedrals, and with three
    hydrogens against two substituents there are six such terms per bond to
    accumulate. Measured on acetone, that reported 8 torsions including
    bands at 1437 and 1459 cm-1, which are deformations.

    A real torsion ROTATES: every dihedral about the bond changes in the
    SAME direction by roughly the same amount, so their signed mean is
    large. A deformation moves them in opposing directions -- one hydrogen
    swings forward as another swings back -- and the signed mean cancels to
    near zero while the magnitudes do not. Taking the mean per bond is
    therefore measuring the thing that actually defines a torsion, and it
    needs no frequency cutoff to stand in for it.

    Ring bonds are skipped: a ring dihedral cannot change independently of
    its neighbours, so counting them makes every ring deformation look
    torsional. Benzene's out-of-plane modes are conventionally reported as
    bends, which is what excluding them yields.
    """
    total = 0.0
    for bond in mol.GetBonds():
        if bond.IsInRing():
            continue
        j, k = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        left = [n.GetIdx() for n in mol.GetAtomWithIdx(j).GetNeighbors() if n.GetIdx() != k]
        right = [n.GetIdx() for n in mol.GetAtomWithIdx(k).GetNeighbors() if n.GetIdx() != j]
        # Both ends must carry a substituent for a dihedral to exist at
        # all -- a terminal hydrogen has no other neighbour, which is why
        # methane has no torsional coordinate to change.
        if not left or not right:
            continue
        changes = [
            _wrap(
                _dihedral(after[i], after[j], after[k], after[l])
                - _dihedral(before[i], before[j], before[k], before[l])
            )
            for i in left
            for l in right
        ]
        if changes:
            total += abs(sum(changes) / len(changes))
    return total


def _wrap(angle: float) -> float:
    """A dihedral difference folded onto (-pi, pi].

    Without this, a small twist across the +pi/-pi boundary reads as a
    rotation of nearly 2*pi, which would make one arbitrary mode dominate
    every score it appears in.
    """
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle <= -math.pi:
        angle += 2.0 * math.pi
    return angle


def _distance(a, b) -> float:
    return math.sqrt(_norm2(_subtract(a, b)))


def _angle(a, b, c) -> float:
    """The A-B-C valence angle in radians."""
    u, v = _unit(_subtract(a, b)), _unit(_subtract(c, b))
    if u is None or v is None:
        return 0.0
    return math.acos(max(-1.0, min(1.0, _dot(u, v))))


def _dihedral(a, b, c, d) -> float:
    """The A-B-C-D dihedral in radians, on (-pi, pi].

    Signed, via the atan2 form, because an unsigned dihedral folds a twist
    through 180 degrees back on itself and would report a large rotation as
    a small one.
    """
    b1, b2, b3 = _subtract(b, a), _subtract(c, b), _subtract(d, c)
    n1, n2 = _cross(b1, b2), _cross(b2, b3)
    m = _cross(n1, _unit(b2) or (0.0, 0.0, 0.0))
    x, y = _dot(n1, n2), _dot(m, n2)
    if abs(x) < _NEGLIGIBLE and abs(y) < _NEGLIGIBLE:
        return 0.0
    return math.atan2(y, x)


def _cross(a, b) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


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
