"""Non-covalent interaction detection within a single 3D structure.

`pose_analysis.py` already detects hydrogen bonds and steric clashes, but
only BETWEEN a docked ligand and a receptor. This module answers the same
kinds of question within one molecule's own conformer, and adds the
interaction types that analysis never needed: salt bridges, pi-pi
stacking, cation-pi, hydrophobic contacts and metal coordination.

Geometric constants are IMPORTED from `pose_analysis` rather than
redefined, so "what counts as a hydrogen bond" has one answer in this
codebase instead of two that drift apart.

Every criterion here is a distance (and, for pi systems, a centroid)
threshold drawn from commonly-used ranges in structural-biology tooling.
They are deliberately simple and symmetric -- no donor/acceptor angle
term, matching the convention `pose_analysis` already documents for its
own hydrogen bonds. This finds candidate contacts worth looking at; it is
not a scoring function and does not claim to be.
"""

from __future__ import annotations

import itertools
from typing import Any

from rdkit import Chem

from openchem.chem.geometry_analysis import NoConformerError, _require_conformer
from openchem.chem.pose_analysis import (
    CATION_PI_CUTOFF,
    CLASH_TOLERANCE,
    HBOND_DISTANCE_CUTOFF,
    HYDROPHOBIC_CUTOFF,
    METAL_COORDINATION_CUTOFF,
    METAL_DONOR_MIN_DISTANCE,
    PI_STACKING_CUTOFF,
    SALT_BRIDGE_CUTOFF,
    _BONDED_NEIGHBOUR_DEPTH,
    _DEFAULT_VDW_RADIUS,
    _METAL_DONOR_ELEMENTS,
    _METALS,
    _POLAR_ELEMENTS,
    _VDW_RADII,
)
from openchem.chem.calculator_options import decimals
from openchem.domain.common import CacheState, Provenance
from openchem.domain.report import ReportResult
from openchem.chem.report_adapter import report_from_fields

# Interaction-specific cutoffs, in Angstrom.
# The interaction cutoffs and the metals list are OWNED by
# `pose_analysis` and imported above -- see the note there on why that
# direction and not this one. Re-exported through this module's namespace
# so existing importers of `interaction_analysis.SALT_BRIDGE_CUTOFF`
# keep working.

# Minimum bond-path separation for a heavy-atom pair to count, PER
# INTERACTION TYPE. A single blanket value is wrong, which probing real
# geometries showed directly:
#
#   salicylic acid  O0-O2  separation 2, 2.23 A  <- the two carboxyl
#       oxygens on one carbon. Geminal geometry, not a contact. Must be
#       excluded, and at 2.23 A it would otherwise register as a clash.
#   ethylene glycol O0-O3  separation 3, 2.81 A  <- a REAL 5-membered-ring
#       intramolecular hydrogen bond. A blanket threshold of 4 silently
#       dropped it.
#   salicylic acid  O0-O9  separation 4, 2.56 A  <- the textbook 6-ring
#       intramolecular hydrogen bond.
#
# So hydrogen bonding and metal coordination start at 3 (they legitimately
# form 5-membered rings), while contacts whose whole point is "these two
# are non-bonded neighbours in space" start at 4, where a 1,3 relationship
# through the chain would otherwise masquerade as a finding.
MIN_SEPARATION = {
    "hydrogen_bonds": 3,
    "metal_coordination": 3,
    "salt_bridges": 4,
    "hydrophobic": 4,
    "clashes": 4,
}


def _vdw_radius(element: str) -> float:
    return _VDW_RADII.get(element.upper(), _DEFAULT_VDW_RADIUS)


def _distance(positions, i: int, j: int) -> float:
    a, b = positions[i], positions[j]
    return float(((a - b) ** 2).sum() ** 0.5)


def _centroid(positions, indices):
    return sum((positions[i] for i in indices)) / len(indices)


def _aromatic_rings(mol: Chem.Mol) -> list[tuple[int, ...]]:
    return [
        ring
        for ring in mol.GetRingInfo().AtomRings()
        if all(mol.GetAtomWithIdx(index).GetIsAromatic() for index in ring)
    ]


def _formal_charge_sites(mol: Chem.Mol) -> tuple[list[int], list[int]]:
    """Atoms carrying a formal positive / negative charge."""
    positive = [a.GetIdx() for a in mol.GetAtoms() if a.GetFormalCharge() > 0]
    negative = [a.GetIdx() for a in mol.GetAtoms() if a.GetFormalCharge() < 0]
    return positive, negative


def _metal_bonded_pairs(mol: Chem.Mol, positions, topological) -> set[tuple[int, int]]:
    """`(lower index, higher index)` pairs inside one molecule that are a bond to a metal, and so not a clash.

    The same rule `pose_analysis._metal_bonded_pairs` applies to a docked pose, for a metal that is NOT joined
    to its donor by a bond in the molecule (a separate fragment, as in `c1c[nH]cn1.[Zn+2]`). Topological
    separation cannot exclude those: the distance between fragments is infinite, so `MIN_SEPARATION['clashes']`
    lets every such pair through and the donor was reported as a clash AND as `metal_coordination`.

    A donor (`_METAL_DONOR_ELEMENTS`) between `METAL_DONOR_MIN_DISTANCE` and `METAL_COORDINATION_CUTOFF` of a
    metal is bonded to it, and so is every atom within `_BONDED_NEIGHBOUR_DEPTH` bonds of that donor, against
    THAT metal only (their distance to it is fixed by the M-D-X angle, not a contact). Closer than the floor
    the two atoms overlap and the pair stays in the clash test.
    """
    metals = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol().upper() in _METALS]
    bonded: set[tuple[int, int]] = set()
    for metal in metals:
        for donor in (a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() in _METAL_DONOR_ELEMENTS):
            if not METAL_DONOR_MIN_DISTANCE <= _distance(positions, metal, donor) <= METAL_COORDINATION_CUTOFF:
                continue
            for other in range(mol.GetNumAtoms()):
                if other != metal and topological[donor][other] <= _BONDED_NEIGHBOUR_DEPTH:
                    bonded.add((min(metal, other), max(metal, other)))
    return bonded


def find_interactions(mol: Chem.Mol) -> dict[str, list[dict[str, Any]]]:
    """Every detected intramolecular interaction, grouped by kind.

    Each entry carries the participating atom indices and the measured
    distance, so a caller can highlight them or report the number.
    """
    conformer = _require_conformer(mol)
    positions = conformer.GetPositions()
    topological = Chem.GetDistanceMatrix(mol)
    found: dict[str, list[dict[str, Any]]] = {
        "hydrogen_bonds": [],
        "salt_bridges": [],
        "pi_stacking": [],
        "cation_pi": [],
        "hydrophobic": [],
        "metal_coordination": [],
        "clashes": [],
    }

    def separated(kind: str, i: int, j: int) -> bool:
        return topological[i][j] >= MIN_SEPARATION[kind]

    metal_bonded = _metal_bonded_pairs(mol, positions, topological)

    heavy = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() != "H"]
    for i, j in itertools.combinations(heavy, 2):
        atom_i, atom_j = mol.GetAtomWithIdx(i), mol.GetAtomWithIdx(j)
        element_i, element_j = atom_i.GetSymbol(), atom_j.GetSymbol()
        distance = _distance(positions, i, j)

        is_hydrogen_bond = (
            element_i in _POLAR_ELEMENTS
            and element_j in _POLAR_ELEMENTS
            and distance <= HBOND_DISTANCE_CUTOFF
            and separated("hydrogen_bonds", i, j)
        )
        if is_hydrogen_bond:
            found["hydrogen_bonds"].append({"atoms": (i, j), "distance": distance})

        # A hydrogen bond is SHORTER than the summed van der Waals radii --
        # that closeness is the interaction, not a problem with it. Without
        # this exclusion every H-bond was also reported as a steric clash
        # (salicylic acid's textbook 2.56 A intramolecular bond showed up
        # as both), which would train a user to ignore the clash list.
        if (
            not is_hydrogen_bond
            and distance < (_vdw_radius(element_i) + _vdw_radius(element_j) - CLASH_TOLERANCE)
            and separated("clashes", i, j)
            # A bond to a metal is not a contact. Same reason as the hydrogen bond above: coordination is
            # reported below, and a pair in both lists teaches the reader to ignore the clash list.
            and (i, j) not in metal_bonded
        ):
            found["clashes"].append({"atoms": (i, j), "distance": distance})

        if (
            element_i == "C"
            and element_j == "C"
            and not atom_i.GetIsAromatic()
            and not atom_j.GetIsAromatic()
            and _is_apolar_carbon(atom_i)
            and _is_apolar_carbon(atom_j)
            and distance <= HYDROPHOBIC_CUTOFF
            and separated("hydrophobic", i, j)
        ):
            found["hydrophobic"].append({"atoms": (i, j), "distance": distance})

        if (element_i.upper() in _METALS) != (element_j.upper() in _METALS):
            donor = j if element_i.upper() in _METALS else i
            if (
                mol.GetAtomWithIdx(donor).GetSymbol() in _METAL_DONOR_ELEMENTS
                and distance <= METAL_COORDINATION_CUTOFF
                and separated("metal_coordination", i, j)
            ):
                found["metal_coordination"].append({"atoms": (i, j), "distance": distance})

    positive, negative = _formal_charge_sites(mol)
    for i in positive:
        for j in negative:
            if not separated("salt_bridges", i, j):
                continue
            distance = _distance(positions, i, j)
            if distance <= SALT_BRIDGE_CUTOFF:
                found["salt_bridges"].append({"atoms": (i, j), "distance": distance})

    rings = _aromatic_rings(mol)
    for ring_a, ring_b in itertools.combinations(rings, 2):
        if set(ring_a) & set(ring_b):
            continue  # fused rings are one system, not a stacking pair
        centroid_a, centroid_b = _centroid(positions, ring_a), _centroid(positions, ring_b)
        distance = float((((centroid_a - centroid_b) ** 2).sum()) ** 0.5)
        if distance <= PI_STACKING_CUTOFF:
            found["pi_stacking"].append({"rings": (ring_a, ring_b), "distance": distance})

    for ring in rings:
        centroid = _centroid(positions, ring)
        for index in positive:
            if index in ring:
                continue
            distance = float((((positions[index] - centroid) ** 2).sum()) ** 0.5)
            if distance <= CATION_PI_CUTOFF:
                found["cation_pi"].append({"atom": index, "ring": ring, "distance": distance})

    return found


def _is_apolar_carbon(atom: Chem.Atom) -> bool:
    """A carbon with no polar neighbour -- the usual working definition of
    a hydrophobic contact partner."""
    return all(neighbor.GetSymbol() not in _POLAR_ELEMENTS for neighbor in atom.GetNeighbors())


_LABELS = {
    "hydrogen_bonds": "Hydrogen bond",
    "salt_bridges": "Salt bridge",
    "pi_stacking": "π-π stacking",
    "cation_pi": "Cation-π",
    "hydrophobic": "Hydrophobic contact",
    "metal_coordination": "Metal coordination",
    "clashes": "Steric clash",
}


def compute_interaction_analysis(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """The "interactions" category's calculator -- intramolecular contacts
    in the current conformer."""
    try:
        interactions = find_interactions(mol)
    except NoConformerError as exc:
        return report_from_fields(
            alert_id="interaction_analysis",
            name="Interaction Analysis",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="geometry",
            cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=Provenance(created_by="core", method="rdkit"),
        )

    places = decimals(parameters)
    lines: list[str] = []
    for kind, entries in interactions.items():
        for entry in entries:
            if "rings" in entry:
                ring_a, ring_b = entry["rings"]
                where = f"rings {sorted(ring_a)} / {sorted(ring_b)}"
            elif "ring" in entry:
                where = f"atom {entry['atom']} / ring {sorted(entry['ring'])}"
            else:
                where = f"atoms {entry['atoms'][0]}-{entry['atoms'][1]}"
            lines.append(
                f"{_LABELS[kind]}: {where} ({entry['distance']:.{places}f} Å)"
            )

    if not lines:
        # An empty result is a real finding ("nothing contacts anything"),
        # not a failure -- said explicitly so it doesn't read as broken.
        lines = ["No intramolecular interactions detected in this conformer."]

    return report_from_fields(
        alert_id="interaction_analysis",
        name="Interaction Analysis",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="geometry",
        provenance=Provenance(created_by="core", method="rdkit"),
    )
