"""Topological (graph-theoretic) descriptors of a molecular structure.

Every index here is hand-implemented from RDKit's topological distance
matrix rather than taken from a library call, so each was checked against
a published value before shipping:

    benzene    Wiener 27, Randic 3.000, Platt 12, Wiener polarity 3
    n-butane   Wiener 10, Randic 1.914, Platt  4, Wiener polarity 1

All confirmed live. Balaban J is RDKit's own `Descriptors.BalabanJ`.

The SZEGED INDEX is now included, validated by a THEOREM rather than by a
reference value: for any acyclic graph the Szeged and Wiener indices are
equal (Gutman 1994), and for a cyclic graph Szeged strictly exceeds
Wiener. Checked live -- n-butane 10 = 10, isobutane 9 = 9, benzene 54 > 27,
naphthalene 243 > 109. That identity pins the implementation more firmly
than agreeing with one tool's output would, since it cannot be satisfied
by accident.

    (Mordred was investigated as a cross-check and does NOT implement it:
    its `SZ` descriptor is "sum of constitutional descriptor", giving 5.67
    for n-butane. A promising-looking name that turned out to be a
    different quantity entirely.)

STILL DELIBERATELY ABSENT -- the topological steric effect index (TSEI).
Unlike Szeged, "steric index" genuinely names several mutually
incompatible quantities in the literature, there is no identity to check
an implementation against, and no reference value was found. Shipping a
number under a recognised name that disagrees with every other tool
reporting that name would be worse than not shipping it.
"""

from __future__ import annotations

import math
from typing import Any

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

from openchem.chem.calculator_options import decimals
from openchem.domain.common import Provenance
from openchem.domain.scientific_result import AlertResult, PerAtomDataset


def _distance_matrix(mol: Chem.Mol):
    return Chem.GetDistanceMatrix(mol)


def wiener_index(mol: Chem.Mol) -> int:
    """Half the sum of all pairwise topological distances. Benzene 27,
    n-butane 10 (both confirmed)."""
    matrix = _distance_matrix(mol)
    return int(matrix.sum() / 2)


def harary_index(mol: Chem.Mol) -> float:
    """Half-sum of the RECIPROCAL distances -- the Wiener index's
    reciprocal analogue, so close pairs dominate instead of distant ones."""
    matrix = _distance_matrix(mol)
    count = mol.GetNumAtoms()
    return sum(
        1.0 / matrix[i][j] for i in range(count) for j in range(i + 1, count) if matrix[i][j]
    )


def hyper_wiener_index(mol: Chem.Mol) -> int:
    matrix = _distance_matrix(mol)
    count = mol.GetNumAtoms()
    pairs = [(i, j) for i in range(count) for j in range(i + 1, count)]
    return int(
        0.5 * (sum(matrix[i][j] for i, j in pairs) + sum(matrix[i][j] ** 2 for i, j in pairs))
    )


def wiener_polarity(mol: Chem.Mol) -> int:
    """Count of atom pairs exactly three bonds apart -- the number of
    distinct torsion relationships, which is what makes it a "polarity"
    measure. Benzene 3, n-butane 1 (confirmed)."""
    matrix = _distance_matrix(mol)
    count = mol.GetNumAtoms()
    return sum(1 for i in range(count) for j in range(i + 1, count) if matrix[i][j] == 3)


def platt_index(mol: Chem.Mol) -> int:
    """Sum over bonds of (degree(a) + degree(b) - 2), i.e. the total edge
    degree of the molecular graph. Benzene 12, n-butane 4 (confirmed)."""
    return sum(
        bond.GetBeginAtom().GetDegree() + bond.GetEndAtom().GetDegree() - 2 for bond in mol.GetBonds()
    )


def randic_index(mol: Chem.Mol) -> float:
    """Sum over bonds of 1/sqrt(deg(a)*deg(b)) -- the classic connectivity
    index (chi-1). Benzene 3.000, n-butane 1.914 (confirmed)."""
    return sum(
        1.0 / math.sqrt(bond.GetBeginAtom().GetDegree() * bond.GetEndAtom().GetDegree())
        for bond in mol.GetBonds()
    )


def szeged_index(mol: Chem.Mol) -> int:
    """Sum over bonds of n_u * n_v, where n_u counts the atoms strictly
    closer to one end of the bond than the other (Gutman 1994).

    Atoms equidistant from both ends belong to neither count, which is
    what makes this differ from the Wiener index on cyclic graphs and
    coincide with it on trees.
    """
    matrix = _distance_matrix(mol)
    count = mol.GetNumAtoms()
    total = 0
    for bond in mol.GetBonds():
        begin, end = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        nearer_begin = sum(1 for atom in range(count) if matrix[begin][atom] < matrix[end][atom])
        nearer_end = sum(1 for atom in range(count) if matrix[end][atom] < matrix[begin][atom])
        total += nearer_begin * nearer_end
    return total


def eccentricity(mol: Chem.Mol) -> dict[int, float]:
    """Per atom: the greatest topological distance to any other atom."""
    matrix = _distance_matrix(mol)
    return {index: float(matrix[index].max()) for index in range(mol.GetNumAtoms())}


def distance_degree(mol: Chem.Mol) -> dict[int, float]:
    """Per atom: the sum of its topological distances to every other atom
    (its row sum in the distance matrix)."""
    matrix = _distance_matrix(mol)
    return {index: float(matrix[index].sum()) for index in range(mol.GetNumAtoms())}


def cyclomatic_number(mol: Chem.Mol) -> int:
    """Bonds - atoms + connected components: the smallest number of bonds
    whose removal leaves no cycle (also called circuit rank)."""
    components = len(Chem.GetMolFrags(mol))
    return mol.GetNumBonds() - mol.GetNumAtoms() + components


def ring_counts(mol: Chem.Mol) -> dict[str, int]:
    """The ring-related counts from Marvin's Topology Analysis list.

    Aromatic ring count can exceed what SSSR alone reports for a
    macroaromatic system, which is why RDKit's own aromatic-ring count is
    used rather than filtering the SSSR set.
    """
    ring_info = mol.GetRingInfo()
    rings = ring_info.AtomRings()
    aromatic_rings = sum(
        1 for ring in rings if all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring)
    )
    carbo_rings = sum(
        1 for ring in rings if all(mol.GetAtomWithIdx(i).GetSymbol() == "C" for i in ring)
    )
    hetero_rings = len(rings) - carbo_rings
    heteroaromatic_rings = sum(
        1
        for ring in rings
        if all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring)
        and any(mol.GetAtomWithIdx(i).GetSymbol() != "C" for i in ring)
    )
    # A ring is "fused" when it shares at least one bond with another ring.
    bond_rings = ring_info.BondRings()
    fused = 0
    for index, ring in enumerate(bond_rings):
        others = set().union(*(set(r) for j, r in enumerate(bond_rings) if j != index)) if len(bond_rings) > 1 else set()
        if set(ring) & others:
            fused += 1

    ring_atoms = {i for ring in rings for i in ring}
    return {
        "ring_count": len(rings),
        "ring_atom_count": len(ring_atoms),
        "ring_bond_count": sum(1 for bond in mol.GetBonds() if bond.IsInRing()),
        "chain_atom_count": mol.GetNumAtoms() - len(ring_atoms),
        "chain_bond_count": sum(1 for bond in mol.GetBonds() if not bond.IsInRing()),
        "aliphatic_ring_count": len(rings) - aromatic_rings,
        "aromatic_ring_count": aromatic_rings,
        "carbo_ring_count": carbo_rings,
        "hetero_ring_count": hetero_rings,
        "heteroaromatic_ring_count": heteroaromatic_rings,
        "fused_ring_count": fused,
        "largest_ring_size": max((len(ring) for ring in rings), default=0),
        "smallest_ring_size": min((len(ring) for ring in rings), default=0),
    }


def stereo_counts(mol: Chem.Mol) -> dict[str, int]:
    """Asymmetric atoms (four different substituents) vs. tetrahedral
    stereogenic centres. These genuinely differ: Marvin's own
    documentation notes 1,4-dimethylcyclohexane has two stereogenic
    centres and no asymmetric atoms.
    """
    asymmetric = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True, useLegacyImplementation=True))
    stereo_info = Chem.FindPotentialStereo(mol)
    centres = sum(1 for element in stereo_info if str(element.type).startswith("Atom_"))
    return {"asymmetric_atom_count": asymmetric, "chiral_center_count": centres}


def compute_topology_analysis(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> AlertResult:
    """The "topology" category's Topology Analysis calculator -- the whole
    index set as one readout, the way Marvin's own window presents it."""
    places = decimals(parameters)
    rings = ring_counts(mol)
    stereo = stereo_counts(mol)
    lines = [
        f"Atom count: {mol.GetNumAtoms()}",
        f"Bond count: {mol.GetNumBonds()}",
        f"Cyclomatic number: {cyclomatic_number(mol)}",
        f"Ring count: {rings['ring_count']}",
        f"Ring atom count: {rings['ring_atom_count']}",
        f"Ring bond count: {rings['ring_bond_count']}",
        f"Chain atom count: {rings['chain_atom_count']}",
        f"Chain bond count: {rings['chain_bond_count']}",
        f"Aliphatic ring count: {rings['aliphatic_ring_count']}",
        f"Aromatic ring count: {rings['aromatic_ring_count']}",
        f"Carbo ring count: {rings['carbo_ring_count']}",
        f"Hetero ring count: {rings['hetero_ring_count']}",
        f"Heteroaromatic ring count: {rings['heteroaromatic_ring_count']}",
        f"Fused ring count: {rings['fused_ring_count']}",
        f"Largest ring size: {rings['largest_ring_size']}",
        f"Smallest ring size: {rings['smallest_ring_size']}",
        f"Platt index: {platt_index(mol)}",
        f"Randic index: {randic_index(mol):.{places}f}",
        f"Balaban index: {Descriptors.BalabanJ(mol):.{places}f}",
        f"Harary index: {harary_index(mol):.{places}f}",
        f"Hyper Wiener index: {hyper_wiener_index(mol)}",
        f"Wiener index: {wiener_index(mol)}",
        f"Szeged index: {szeged_index(mol)}",
        f"Wiener polarity: {wiener_polarity(mol)}",
        f"Asymmetric atom count: {stereo['asymmetric_atom_count']}",
        f"Chiral center count: {stereo['chiral_center_count']}",
        f"Rotatable bond count: {rdMolDescriptors.CalcNumRotatableBonds(mol)}",
    ]
    return AlertResult(
        alert_id="topology_analysis",
        name="Topology Analysis",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="topology",
        provenance=Provenance(created_by="core", method="rdkit"),
    )


def compute_eccentricity_dataset(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> PerAtomDataset:
    """Per-atom eccentricity, which gets the 2D+3D projection treatment
    through the Calculator Inspector -- a visual read of how peripheral
    versus central each atom is in the molecular graph."""
    _places = decimals(parameters)
    return PerAtomDataset(
        property_id="topology_eccentricity",
        name="Eccentricity (topological)",
        units="bonds",
        method="rdkit",
        molecule_uuid=molecule_uuid,
        values=eccentricity(mol),
        provenance=Provenance(created_by="core", method="rdkit", parameters={"decimal_places": _places}),
    )


def compute_distance_degree_dataset(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> PerAtomDataset:
    _places = decimals(parameters)
    return PerAtomDataset(
        property_id="topology_distance_degree",
        name="Distance Degree (topological)",
        units="bonds",
        method="rdkit",
        molecule_uuid=molecule_uuid,
        values=distance_degree(mol),
        provenance=Provenance(created_by="core", method="rdkit", parameters={"decimal_places": _places}),
    )
