"""The coordinates: as coordinates (GEOMETRY) and as a drawing (LAYOUT).

Nothing here is measured in angstroms. A 2D depiction's units are whatever
the program that wrote it chose, so every threshold below is a ratio
against the drawing's OWN median bond length. That is what lets the same
code read a Ketcher molblock, an imported SDF and a 3D conformer without a
scale factor per source.

Which of these are deterministic and which are judgement is not decoration.
Two atoms at the same point, and two bonds that cross, are facts about the
coordinates -- segment intersection has no threshold in it. "This bond
looks short" and "these atoms are crowded" are opinions with a number
somebody picked, and they say so.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Any

from openchem.chem.structure_check import (
    COORDINATES,
    Basis,
    Category,
    CheckContext,
    CheckerDefinition,
    Severity,
    StructureIssue,
)
from openchem.domain.common import Provenance

#: Below this fraction of the median bond length, two atoms are not
#: "close", they are in the same place -- drawing noise, or genuinely two
#: atoms where one was meant. Not a judgement threshold; it exists only to
#: absorb float rounding in the file.
COINCIDENT_FRACTION = 0.01

#: Crowding, by contrast, IS a judgement. Atoms this close relative to a
#: bond length are legible only sometimes, and plenty of correct drawings
#: of fused polycyclics will trip it.
CROWDED_FRACTION = 0.25

#: A bond outside this band relative to the median for its own bond order.
SHORT_BOND_RATIO = 0.5
LONG_BOND_RATIO = 2.0

#: Below this, two bonds at an atom are hard to tell apart on screen.
ACUTE_ANGLE_DEGREES = 30.0

_PROVENANCE = Provenance(created_by="core", method="coordinate geometry, ratios to the drawing's own median")


def _positions(mol: Any) -> list[tuple[float, float, float]]:
    conformer = mol.GetConformer()
    return [
        (p.x, p.y, p.z)
        for p in (conformer.GetAtomPosition(i) for i in range(mol.GetNumAtoms()))
    ]


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.dist(a, b)


def _median_bond_length(mol: Any, points: list[tuple[float, float, float]]) -> float:
    lengths = [
        _distance(points[b.GetBeginAtomIdx()], points[b.GetEndAtomIdx()]) for b in mol.GetBonds()
    ]
    lengths = [length for length in lengths if length > 0]
    return median(lengths) if lengths else 0.0


def _check_coincident_atoms(context: CheckContext) -> list[StructureIssue]:
    mol = context.mol
    points = _positions(mol)
    scale = _median_bond_length(mol, points)
    if scale <= 0:
        return []

    limit = scale * COINCIDENT_FRACTION
    issues: list[StructureIssue] = []
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            if _distance(points[i], points[j]) <= limit:
                a = mol.GetAtomWithIdx(i).GetSymbol()
                b = mol.GetAtomWithIdx(j).GetSymbol()
                bonded = mol.GetBondBetweenAtoms(i, j) is not None
                issues.append(
                    StructureIssue(
                        checker_id="overlapping_atoms",
                        category=Category.GEOMETRY,
                        severity=Severity.ERROR if not bonded else Severity.WARNING,
                        basis=Basis.DETERMINISTIC,
                        message=(
                            f"{a}{i + 1} and {b}{j + 1} occupy the same point. "
                            + (
                                "They are not bonded, so this is almost certainly one atom "
                                "drawn twice."
                                if not bonded
                                else "They are bonded, so the bond has zero length."
                            )
                        ),
                        atom_indices=(i, j),
                        fix_id="merge_coincident_atoms" if not bonded else "",
                    )
                )
    return issues


def _segments_cross(
    p1: tuple[float, float], p2: tuple[float, float],
    p3: tuple[float, float], p4: tuple[float, float],
) -> bool:
    """Proper intersection only -- segments that merely touch at an
    endpoint do not count, which is every pair of bonds meeting at an atom.
    """

    def orientation(a, b, c) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1 = orientation(p3, p4, p1)
    d2 = orientation(p3, p4, p2)
    d3 = orientation(p1, p2, p3)
    d4 = orientation(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _check_overlapping_bonds(context: CheckContext) -> list[StructureIssue]:
    mol = context.mol
    conformer = mol.GetConformer()
    if conformer.Is3D():
        # Bonds crossing in projection is what a 3D structure looks like
        # from most angles. The check is about a 2D depiction.
        return []

    points = _positions(mol)
    flat = [(x, y) for x, y, _ in points]
    bonds = [(b.GetIdx(), b.GetBeginAtomIdx(), b.GetEndAtomIdx()) for b in mol.GetBonds()]

    issues: list[StructureIssue] = []
    for i in range(len(bonds)):
        idx_a, a1, a2 = bonds[i]
        for j in range(i + 1, len(bonds)):
            idx_b, b1, b2 = bonds[j]
            if {a1, a2} & {b1, b2}:
                continue
            if _segments_cross(flat[a1], flat[a2], flat[b1], flat[b2]):
                issues.append(
                    StructureIssue(
                        checker_id="overlapping_bonds",
                        category=Category.GEOMETRY,
                        severity=Severity.WARNING,
                        basis=Basis.DETERMINISTIC,
                        message=(
                            "Two bonds cross with no atom at the intersection. Legitimate in a "
                            "macrocycle or a drawn-through ring; otherwise the drawing is "
                            "showing a connection that is not there."
                        ),
                        atom_indices=(a1, a2, b1, b2),
                        bond_indices=(idx_a, idx_b),
                        fix_id="recompute_layout",
                    )
                )
    return issues


def _check_bond_lengths(context: CheckContext) -> list[StructureIssue]:
    """Length against the median for the bond's OWN order.

    Per order rather than overall because in a 3D structure a C=C is
    genuinely shorter than a C-C and comparing them to one median flags
    every double bond in the molecule. In a 2D depiction every order is
    drawn the same length, so the per-order medians coincide and this
    degenerates to the plain comparison -- correct in both cases without a
    2D/3D branch.
    """
    mol = context.mol
    points = _positions(mol)
    by_order: dict[float, list[float]] = {}
    measurements: list[tuple[Any, float, float]] = []
    for bond in mol.GetBonds():
        length = _distance(points[bond.GetBeginAtomIdx()], points[bond.GetEndAtomIdx()])
        order = bond.GetBondTypeAsDouble()
        by_order.setdefault(order, []).append(length)
        measurements.append((bond, length, order))

    overall = _median_bond_length(mol, points)
    if overall <= 0:
        return []

    issues: list[StructureIssue] = []
    for bond, length, order in measurements:
        samples = by_order.get(order, [])
        # Under three examples a "median" is one or two bonds voting on
        # themselves; fall back to the whole drawing rather than compare a
        # lone double bond against itself and never flag it.
        reference = median(samples) if len(samples) >= 3 else overall
        if reference <= 0:
            continue
        ratio = length / reference
        if SHORT_BOND_RATIO < ratio < LONG_BOND_RATIO:
            continue
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        issues.append(
            StructureIssue(
                checker_id="bond_length",
                category=Category.LAYOUT,
                severity=Severity.WARNING,
                basis=Basis.HEURISTIC,
                message=(
                    f"The bond between atoms {i + 1} and {j + 1} is "
                    f"{ratio:.1f}x the typical length for its bond order in this drawing. "
                    "Uneven bond lengths are a drawing artefact, not a chemistry error."
                ),
                atom_indices=(i, j),
                bond_indices=(bond.GetIdx(),),
                fix_id="recompute_layout",
            )
        )
    return issues


def _check_acute_angles(context: CheckContext) -> list[StructureIssue]:
    mol = context.mol
    points = _positions(mol)
    issues: list[StructureIssue] = []
    for atom in mol.GetAtoms():
        neighbours = [n.GetIdx() for n in atom.GetNeighbors()]
        if len(neighbours) < 2:
            continue
        centre = points[atom.GetIdx()]
        for a in range(len(neighbours)):
            for b in range(a + 1, len(neighbours)):
                angle = _angle_degrees(points[neighbours[a]], centre, points[neighbours[b]])
                if angle is None or angle >= ACUTE_ANGLE_DEGREES:
                    continue
                issues.append(
                    StructureIssue(
                        checker_id="acute_bond_angle",
                        category=Category.LAYOUT,
                        severity=Severity.WARNING,
                        basis=Basis.HEURISTIC,
                        message=(
                            f"Two bonds at {atom.GetSymbol()}{atom.GetIdx() + 1} meet at "
                            f"{angle:.0f} degrees and will be hard to tell apart. "
                            "Three-membered rings look like this legitimately."
                        ),
                        atom_indices=(neighbours[a], atom.GetIdx(), neighbours[b]),
                        fix_id="recompute_layout",
                    )
                )
    return issues


def _angle_degrees(
    a: tuple[float, float, float],
    centre: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float | None:
    v1 = (a[0] - centre[0], a[1] - centre[1], a[2] - centre[2])
    v2 = (b[0] - centre[0], b[1] - centre[1], b[2] - centre[2])
    n1 = math.sqrt(sum(c * c for c in v1))
    n2 = math.sqrt(sum(c * c for c in v2))
    if n1 == 0 or n2 == 0:
        return None
    cosine = sum(x * y for x, y in zip(v1, v2)) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _check_crowding(context: CheckContext) -> list[StructureIssue]:
    """Unbonded atoms drawn closer together than a quarter of a bond.

    Distinct from `overlapping_atoms`, which is about atoms in the same
    place. This one is about legibility, it has a threshold somebody chose,
    and it says so.
    """
    mol = context.mol
    points = _positions(mol)
    scale = _median_bond_length(mol, points)
    if scale <= 0:
        return []

    lower = scale * COINCIDENT_FRACTION
    upper = scale * CROWDED_FRACTION
    crowded: list[tuple[int, int]] = []
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            if mol.GetBondBetweenAtoms(i, j) is not None:
                continue
            if lower < _distance(points[i], points[j]) < upper:
                crowded.append((i, j))

    if not crowded:
        return []
    return [
        StructureIssue(
            checker_id="crowding",
            category=Category.LAYOUT,
            severity=Severity.INFO,
            basis=Basis.HEURISTIC,
            message=(
                f"{len(crowded)} pairs of unbonded atoms are drawn close enough to read as "
                "touching. A layout pass usually separates them."
            ),
            atom_indices=tuple(sorted({i for pair in crowded for i in pair})),
            fix_id="recompute_layout",
        )
    ]


def _crossing_count(mol: Any, points: list[tuple[float, float, float]]) -> int:
    flat = [(x, y) for x, y, _ in points]
    bonds = [(b.GetBeginAtomIdx(), b.GetEndAtomIdx()) for b in mol.GetBonds()]
    total = 0
    for i in range(len(bonds)):
        a1, a2 = bonds[i]
        for j in range(i + 1, len(bonds)):
            b1, b2 = bonds[j]
            if {a1, a2} & {b1, b2}:
                continue
            if _segments_cross(flat[a1], flat[a2], flat[b1], flat[b2]):
                total += 1
    return total


def _check_layout_suggestion(context: CheckContext) -> list[StructureIssue]:
    """Offer a redraw only when a redraw has been shown to help.

    Every other complaint in this module says a drawing looks wrong. This
    one generates the alternative and compares, so it can tell "your
    drawing is bad" from "your drawing is bad AND I can do better" -- and
    those are genuinely different. Measured: morphine's own RDKit
    depiction has one bond crossing, and regenerating it still has one, so
    `overlapping_bonds` fires and this stays silent. Offering a redraw
    there would waste somebody's time and their layout.

    No score is attached, and none is implied. The reported numbers are
    two counts of the same exact quantity; the offer is the signal.

    Costs a `Compute2DCoords` per check -- measured at 0.36 ms for a
    45-atom peptide, which is why it runs on every edit rather than
    behind a button.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = context.mol
    conformer = mol.GetConformer()
    if conformer.Is3D():
        # A 3D structure's bonds cross in projection from most angles, and
        # replacing its coordinates with a flat depiction would destroy the
        # geometry rather than tidy it.
        return []

    current = _crossing_count(mol, _positions(mol))
    if current == 0:
        # A cost shortcut, NOT a guard: the comparison below already
        # returns nothing when there is nothing to improve on. It is here
        # because most drawings are clean, and this is what stops a
        # `Compute2DCoords` running on every one of them after every edit.
        # Mutation testing correctly cannot tell it from its absence --
        # that is the point.
        return []

    fresh = Chem.Mol(mol)
    try:
        AllChem.Compute2DCoords(fresh)
    except Exception:
        return []
    regenerated = _crossing_count(fresh, _positions(fresh))
    if regenerated >= current:
        return []

    return [
        StructureIssue(
            checker_id="layout_suggestion",
            category=Category.LAYOUT,
            severity=Severity.INFO,
            basis=Basis.DETERMINISTIC,
            message=(
                f"A fresh layout would draw this with {regenerated} crossing bond"
                f"{'' if regenerated == 1 else 's'} instead of {current}. "
                "Nothing about the chemistry changes; only where things are drawn."
            ),
            fix_id="recompute_layout",
        )
    ]


_CHECKERS = (
    ("overlapping_atoms", "Overlapping atoms", Category.GEOMETRY, _check_coincident_atoms),
    ("overlapping_bonds", "Crossing bonds", Category.GEOMETRY, _check_overlapping_bonds),
    ("bond_length", "Bond lengths", Category.LAYOUT, _check_bond_lengths),
    ("acute_bond_angle", "Bond angles", Category.LAYOUT, _check_acute_angles),
    ("crowding", "Crowding", Category.LAYOUT, _check_crowding),
    ("layout_suggestion", "Layout suggestion", Category.LAYOUT, _check_layout_suggestion),
)


def register(registry: Any) -> None:
    for checker_id, display_name, category, run in _CHECKERS:
        registry.register(
            CheckerDefinition(
                checker_id=checker_id,
                display_name=display_name,
                category=category,
                run=run,
                requires=frozenset({COORDINATES}),
                provenance=_PROVENANCE,
            )
        )
