"""Is a docked pose physically possible? A flag on each pose, not a score.

Vina's number says how well a pose satisfies Vina's scoring function; it says nothing
about whether the pose is a state a molecule can be in. These four checks answer only
that, on the heavy atoms, and each one is a plain distance test that can be read off the
pose by eye:

* ``receptor_clash``    a ligand atom closer to a receptor atom than 0.75 x the sum of
                        their van der Waals radii (the PoseBusters threshold);
* ``internal_clash``    two ligand atoms five or more bonds apart closer than the same
                        ratio, i.e. the ligand has folded through itself;
* ``in_search_box``     every ligand atom inside the search box (1 A of slack: Vina's box
                        is a restraint, and its edge is not a physical wall);
* ``touches_receptor``  at least one ligand atom within 4.5 A of a receptor atom, so the
                        pose is not floating in an empty part of the box.

**WHAT IS NOT CHECKED, AND WHY.** Bond lengths, bond angles and ring planarity. Vina
treats every bond as rigid and moves only torsions, so those are inherited from the
input conformer and cannot be broken by the search; and the pose text arrives through a
PDBQT, so Open Babel re-perceives its bonds from the coordinates, which would make a
bond-length test agree with itself. The pose also carries only its polar hydrogens, so
nothing here looks at hydrogens at all.

**PASSING IS NOT EVIDENCE THE POSE IS RIGHT.** A pose can clear all four and still be in
the wrong place or the wrong orientation; the checks catch the impossible, not the
unlikely. A check that cannot be evaluated is ``None``, never a pass.

This is this project's own implementation of the idea in PoseBusters (Buttenschoen et
al., 2024); it is not that package and does not reproduce its other tests.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

from rdkit import Chem

from openchem.chem.pose_analysis import (
    ReceptorAtom,
    _ligand_heavy_atoms,
    _metal_bonded_pairs,
    _vdw_radius,
)
from openchem.domain.docking import DockingBox

#: A pair closer than this fraction of its van der Waals sum is a clash.
CLASH_RATIO = 0.75

#: Two ligand atoms this many bonds apart or fewer are 1-2, 1-3 or 1-4 neighbours, whose
#: distance is set by bonded geometry (a gauche 1-4 carbon pair is about 2.9 A, under
#: this ratio's 2.55 only with a distorted bond), so only farther pairs are tested.
INTERNAL_MIN_BONDS = 5

#: Beyond the box edge by up to this many Angstrom still counts as inside it.
BOX_SLACK = 1.0

#: A pose with no ligand atom this close to the receptor is not in a pocket.
CONTACT_DISTANCE = 4.5

#: Stored under this key of `DockingPoseModel.metadata`.
METADATA_KEY = "plausibility"

#: Check id -> the label shown beside a failure.
CHECK_LABELS = {
    "receptor_clash": "clashes with the receptor",
    "internal_clash": "folds through itself",
    "in_search_box": "leaves the search box",
    "touches_receptor": "touches no receptor atom",
}


def check_pose(
    pose_molblock: str,
    receptor_atoms: list[ReceptorAtom],
    box: DockingBox | None = None,
) -> dict[str, Any]:
    """The four checks for one pose, as plain JSON-able data for `pose.metadata`.

    ``{"checks": {id: {"passed": bool | None, "detail": str}}, "failed": [id, ...]}``.
    ``passed`` is ``None`` when the check could not be made (no parsable pose, no
    receptor atoms, no box), and such a check is never listed in ``failed``.
    """
    mol, atoms = _ligand_heavy_atoms(pose_molblock)
    heavy_receptor = [(i, a) for i, a in enumerate(receptor_atoms) if a.element != "H"]
    if mol is None or not atoms:
        unknown = {"passed": None, "detail": "the pose could not be read"}
        return _result({check_id: dict(unknown) for check_id in CHECK_LABELS})

    checks = {
        "receptor_clash": _receptor_clash(mol, atoms, heavy_receptor, receptor_atoms),
        "internal_clash": _internal_clash(mol, atoms),
        "in_search_box": _in_search_box(atoms, box),
        "touches_receptor": _touches_receptor(atoms, heavy_receptor),
    }
    return _result(checks)


def _result(checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "checks": checks,
        "failed": [check_id for check_id, c in checks.items() if c["passed"] is False],
    }


def _receptor_clash(
    mol: Chem.Mol,
    atoms: list[tuple[int, str, tuple[float, float, float]]],
    heavy_receptor: list[tuple[int, ReceptorAtom]],
    receptor_atoms: list[ReceptorAtom],
) -> dict[str, Any]:
    if not heavy_receptor:
        return {"passed": None, "detail": "no receptor atoms to compare with"}
    # A bond to a metal is not a contact; the pair is left out exactly as the
    # interaction analysis leaves it out of its own clash list.
    metal_bonded = _metal_bonded_pairs(mol, atoms, receptor_atoms)
    count = 0
    worst = 1.0
    for ligand_index, element, position in atoms:
        ligand_radius = _vdw_radius(element)
        for receptor_index, receptor in heavy_receptor:
            if (ligand_index, receptor_index) in metal_bonded:
                continue
            limit = CLASH_RATIO * (ligand_radius + _vdw_radius(receptor.element))
            distance = math.dist(position, receptor.position)
            if distance < limit:
                count += 1
                worst = min(worst, distance / (ligand_radius + _vdw_radius(receptor.element)))
    if count:
        return {
            "passed": False,
            "detail": f"{count} atom pair(s) closer than {CLASH_RATIO:.2f} of their van der Waals "
            f"sum; the closest is at {worst:.2f} of it",
        }
    return {"passed": True, "detail": "no atom pair closer than the limit"}


def _internal_clash(
    mol: Chem.Mol, atoms: list[tuple[int, str, tuple[float, float, float]]]
) -> dict[str, Any]:
    if len(atoms) < 2:
        return {"passed": True, "detail": "a single heavy atom"}
    paths = Chem.GetDistanceMatrix(mol)
    count = 0
    worst = 1.0
    for a in range(len(atoms)):
        index_a, element_a, position_a = atoms[a]
        for b in range(a + 1, len(atoms)):
            index_b, element_b, position_b = atoms[b]
            # 1e8 is RDKit's value for "not connected": two fragments are not one
            # molecule folded onto itself, and a salt's ions are not bonded.
            if paths[index_a][index_b] < INTERNAL_MIN_BONDS or paths[index_a][index_b] > 1e7:
                continue
            total = _vdw_radius(element_a) + _vdw_radius(element_b)
            distance = math.dist(position_a, position_b)
            if distance < CLASH_RATIO * total:
                count += 1
                worst = min(worst, distance / total)
    if count:
        return {
            "passed": False,
            "detail": f"{count} pair(s) of atoms five or more bonds apart are closer than "
            f"{CLASH_RATIO:.2f} of their van der Waals sum; the closest is at {worst:.2f} of it",
        }
    return {"passed": True, "detail": "no distant pair of atoms is too close"}


def _in_search_box(
    atoms: list[tuple[int, str, tuple[float, float, float]]], box: DockingBox | None
) -> dict[str, Any]:
    if box is None:
        return {"passed": None, "detail": "the search box is not known"}
    outside = 0
    furthest = 0.0
    for _index, _element, position in atoms:
        # How far past the box face along the worst axis (0 when inside).
        over = max(
            abs(position[axis] - box.center[axis]) - box.size[axis] / 2.0 for axis in range(3)
        )
        if over > BOX_SLACK:
            outside += 1
            furthest = max(furthest, over)
    if outside:
        return {
            "passed": False,
            "detail": f"{outside} atom(s) lie outside the search box, the furthest {furthest:.1f} A past its face",
        }
    return {"passed": True, "detail": "every atom is inside the search box"}


def _touches_receptor(
    atoms: list[tuple[int, str, tuple[float, float, float]]],
    heavy_receptor: list[tuple[int, ReceptorAtom]],
) -> dict[str, Any]:
    if not heavy_receptor:
        return {"passed": None, "detail": "no receptor atoms to compare with"}
    nearest = min(
        math.dist(position, receptor.position)
        for _index, _element, position in atoms
        for _i, receptor in heavy_receptor
    )
    if nearest > CONTACT_DISTANCE:
        return {
            "passed": False,
            "detail": f"the nearest receptor atom is {nearest:.1f} A away (more than {CONTACT_DISTANCE:.1f} A)",
        }
    return {"passed": True, "detail": f"the nearest receptor atom is {nearest:.1f} A away"}


def failed_checks(metadata: dict[str, Any]) -> list[str] | None:
    """The ids of the checks a pose failed, or ``None`` when it was never checked."""
    found = metadata.get(METADATA_KEY)
    if not isinstance(found, dict) or "failed" not in found:
        return None
    return [check_id for check_id in found["failed"] if check_id in CHECK_LABELS]


def pose_tooltip(metadata: dict[str, Any]) -> str:
    """One pose's checks in words, for a row's hover text ("" when never checked)."""
    found = metadata.get(METADATA_KEY)
    if failed_checks(metadata) is None:
        return ""
    lines = []
    for check_id, label in CHECK_LABELS.items():
        check = found["checks"].get(check_id)
        if not check:
            continue
        mark = {True: "passed", False: "FAILED", None: "not checked"}[check["passed"]]
        lines.append(f"{label}: {mark} -- {check['detail']}")
    return "\n".join(lines)


def summarize(pose_metadata: Iterable[dict[str, Any]]) -> str:
    """The sentence under the pose table, or "" when no pose was checked.

    It always says what a pass is worth, because "all checks passed" read next to a
    score is taken to mean "this pose is right".
    """
    rows = [failed_checks(m) for m in pose_metadata]
    checked = [(row, failed) for row, failed in enumerate(rows, start=1) if failed is not None]
    if not checked:
        return ""
    bad = [(row, failed) for row, failed in checked if failed]
    if not bad:
        head = f"Physical checks: all {len(checked)} pose(s) passed."
    else:
        parts = [
            f"pose {row} {', '.join(CHECK_LABELS[c] for c in failed)}" for row, failed in bad[:3]
        ]
        more = f" (and {len(bad) - 3} more)" if len(bad) > 3 else ""
        head = f"Physical checks: {len(bad)} of {len(checked)} pose(s) failed -- " + "; ".join(parts) + more + "."
    return (
        head
        + " These catch impossible poses (clashes, folding, leaving the box), not wrong ones: "
        "passing does not mean the pose is where the ligand really binds."
    )
