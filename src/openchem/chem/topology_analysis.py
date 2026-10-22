"""Topological (graph-theoretic) descriptors of a molecular structure.

Every index here is hand-implemented from RDKit's topological distance
matrix rather than taken from a library call, so each was checked against
a published value before shipping:

    benzene    Wiener 27, Randic 3.000, Platt 12, Wiener polarity 3
    n-butane   Wiener 10, Randic 1.914, Platt  4, Wiener polarity 1

All confirmed live. Balaban J is RDKit's own `Descriptors.BalabanJ`.

The SZEGED INDEX is now included, validated by a THEOREM rather than by a
reference value: for any acyclic graph the Szeged and Wiener indices are
equal (Gutman 1994). Checked live -- n-butane 10 = 10, isobutane 9 = 9.
That identity pins the implementation more firmly than agreeing with one
tool's output would, since it cannot be satisfied by accident.

THE OTHER HALF OF THAT SENTENCE CLAIMED MORE THAN HAD BEEN MEASURED. It said
that on a cyclic graph Szeged "strictly exceeds" Wiener. It does on every
molecule with a ring of four or more atoms that was tried (cyclobutane 16 >
8, cyclopentane 20 > 15, benzene 54 > 27, cycloheptane 63 > 42,
bicyclobutane 9 > 7), and it does NOT where every ring is a triangle:
cyclopropane, oxirane, aziridine and spiropentane are equal (3 = 3, 3 = 3,
3 = 3, 14 = 14). Found 2026-10-15 by a test that asserted the old sentence
on cyclopropane.

    (Mordred was investigated as a cross-check and does NOT implement it:
    its `SZ` descriptor is "sum of constitutional descriptor", giving 5.67
    for n-butane. A promising-looking name that turned out to be a
    different quantity entirely.)

THE TOPOLOGICAL STERIC EFFECT INDEX HAS SINCE SHIPPED, in
`chem/tsei.py`, and this paragraph used to say it never would. The reason
recorded here was that "steric index" names several incompatible
quantities and that "no reference value was found" -- the first half is
still true and is why that module ships under the name **Cao-Liu TSEI**
and never the bare one; the second half was simply out of date. Cao & Liu
2004 print exact values for twenty normal alkyls and for the halogens,
ethers and branched alkyls, and 18 of the 19 reachable ones reproduce.

A deferral's REASONS rot independently of its verdict, which is a lesson
this project has now paid for six times.

IT IS STILL NOT PART OF THIS REPORT, and that is a scoping decision
rather than a leftover. Szeged counts atoms by which end of a bond they
are nearer -- pure connectivity, no chemistry, one number per molecule.
TSEI weights paths by atomic radii toward a NAMED REACTION CENTRE, so it
is not defined without one and is per-atom by nature; it is registered as
its own per-atom calculator ("Cao-Liu TSEI projection") rather than as a
line here. The 3D steric measures are a separate question again, and
further along -- see `geometry_analysis`, which records live results for
the Tolman cone angle and percent buried volume against their published
values.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

from openchem.chem.calculator_options import atom_basis_of, decimals
from openchem.domain.common import ATOM_BASIS, TOTAL, Provenance, declare_total, decline_total
from openchem.domain.report import ReportResult
from openchem.chem.report_adapter import report_from_fields
from openchem.domain.scientific_result import PerAtomDataset


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
    # `float(...)`: the sum of an empty generator is the int 0 and the sum of NumPy elements is a NumPy float, and the project file's codec takes only an exact `float`.
    return float(
        sum(1.0 / matrix[i][j] for i in range(count) for j in range(i + 1, count) if matrix[i][j])
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
    # `float(...)` for the reason `harary_index` gives: a molecule with no bond summed to the int 0.
    return float(
        sum(
            1.0 / math.sqrt(bond.GetBeginAtom().GetDegree() * bond.GetEndAtom().GetDegree())
            for bond in mol.GetBonds()
        )
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


#: RDKit's distance for an UNREACHABLE pair (atoms in different components)
#: is 1e8, not infinity. Anything at or above this is "no path".
_UNREACHABLE = 1e7


def eccentricity(mol: Chem.Mol) -> dict[int, float]:
    """Per atom: the greatest topological distance to any other atom OF ITS
    OWN COMPONENT.

    Within its component because that is where the graph-theoretic
    definition lives: across components there is no path. Taking the row
    maximum as-is printed RDKit's 1e8 sentinel as every atom's eccentricity
    on any salt (round 5 multicomponent sweep, sodium acetate).
    """
    matrix = _distance_matrix(mol)
    return {
        index: float(max((d for d in matrix[index] if d < _UNREACHABLE), default=0.0))
        for index in range(mol.GetNumAtoms())
    }


def distance_degree(mol: Chem.Mol) -> dict[int, float]:
    """Per atom: the sum of its topological distances to every other atom of
    its own component (its row sum over reachable atoms), for the reason
    `eccentricity` gives."""
    matrix = _distance_matrix(mol)
    return {
        index: float(sum(d for d in matrix[index] if d < _UNREACHABLE))
        for index in range(mol.GetNumAtoms())
    }


def cyclomatic_number(mol: Chem.Mol) -> int:
    """Bonds - atoms + connected components: the smallest number of bonds
    whose removal leaves no cycle (also called circuit rank)."""
    components = len(Chem.GetMolFrags(mol))
    return mol.GetNumBonds() - mol.GetNumAtoms() + components


def ring_counts(mol: Chem.Mol) -> dict[str, int]:
    """The ring-related counts from the reference editor's Topology Analysis list.

    The aromatic ring count here FILTERS the SSSR rings to those whose atoms
    are all aromatic. This docstring used to say RDKit's own aromatic-ring
    count was used instead, which it is not: RDKit's `CalcNumAromaticRings`
    wants a ring's BONDS aromatic, and the two differ on biphenylene (3 here,
    2 there) and azulene (2 here, 0 there), measured 2026-10-16 and pinned by
    `tests/test_bbb_descriptors_typed.py`. The BBB Score Descriptors calculator
    reports RDKit's count, and that is the one a derived score may read.
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
    stereogenic centres. These genuinely differ: the reference editor's own
    documentation notes 1,4-dimethylcyclohexane has two stereogenic
    centres and no asymmetric atoms.
    """
    asymmetric = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True, useLegacyImplementation=True))
    stereo_info = Chem.FindPotentialStereo(mol)
    centres = sum(1 for element in stereo_info if str(element.type).startswith("Atom_"))
    return {"asymmetric_atom_count": asymmetric, "chiral_center_count": centres}


def compute_topology_analysis(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """The "topology" category's Topology Analysis calculator -- the whole
    index set as one readout, the way the reference editor's own window presents it."""
    places = decimals(parameters)
    rings = ring_counts(mol)
    stereo = stereo_counts(mol)
    # The eight graph indices, computed once: the line shows each rounded to the person's decimal places and the fact keeps the number itself (below).
    indices = {
        "Platt index": platt_index(mol),
        "Randic index": randic_index(mol),
        "Balaban index": float(Descriptors.BalabanJ(mol)),
        "Harary index": harary_index(mol),
        "Hyper Wiener index": hyper_wiener_index(mol),
        "Wiener index": wiener_index(mol),
        "Szeged index": szeged_index(mol),
        "Wiener polarity": wiener_polarity(mol),
    }
    # Ten of the report's counts also carry their number. Each line prints the count and the fact keeps it, so the two cannot drift (the lines are held to a recording made before any of this was typed).
    counts = {
        "Bond count": mol.GetNumBonds(),
        "Cyclomatic number": cyclomatic_number(mol),
        "Ring atom count": rings["ring_atom_count"],
        "Ring bond count": rings["ring_bond_count"],
        "Chain atom count": rings["chain_atom_count"],
        "Chain bond count": rings["chain_bond_count"],
        "Carbo ring count": rings["carbo_ring_count"],
        "Hetero ring count": rings["hetero_ring_count"],
        "Fused ring count": rings["fused_ring_count"],
        "Asymmetric atom count": stereo["asymmetric_atom_count"],
    }
    lines = [
        f"Atom count: {mol.GetNumAtoms()}",
        f"Bond count: {counts['Bond count']}",
        f"Cyclomatic number: {counts['Cyclomatic number']}",
        f"Ring count: {rings['ring_count']}",
        f"Ring atom count: {counts['Ring atom count']}",
        f"Ring bond count: {counts['Ring bond count']}",
        f"Chain atom count: {counts['Chain atom count']}",
        f"Chain bond count: {counts['Chain bond count']}",
        f"Aliphatic ring count: {rings['aliphatic_ring_count']}",
        f"Aromatic ring count: {rings['aromatic_ring_count']}",
        f"Carbo ring count: {counts['Carbo ring count']}",
        f"Hetero ring count: {counts['Hetero ring count']}",
        f"Heteroaromatic ring count: {rings['heteroaromatic_ring_count']}",
        f"Fused ring count: {counts['Fused ring count']}",
        f"Largest ring size: {rings['largest_ring_size']}",
        f"Smallest ring size: {rings['smallest_ring_size']}",
        f"Platt index: {indices['Platt index']}",
        f"Randic index: {indices['Randic index']:.{places}f}",
        f"Balaban index: {indices['Balaban index']:.{places}f}",
        f"Harary index: {indices['Harary index']:.{places}f}",
        f"Hyper Wiener index: {indices['Hyper Wiener index']}",
        f"Wiener index: {indices['Wiener index']}",
        f"Szeged index: {indices['Szeged index']}",
        f"Wiener polarity: {indices['Wiener polarity']}",
        f"Asymmetric atom count: {counts['Asymmetric atom count']}",
        f"Chiral center count: {stereo['chiral_center_count']}",
        f"Rotatable bond count: {rdMolDescriptors.CalcNumRotatableBonds(mol)}",
    ]
    report = report_from_fields(
        alert_id="topology_analysis",
        name="Topology Analysis",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="topology",
        provenance=Provenance(created_by="core", method="rdkit"),
    )
    # **EIGHTEEN FACTS OF THE REPORT CARRY THEIR NUMBER: THE EIGHT INDICES AND TEN OF THE COUNTS.** Each fact's value was the text its line shows (`'6.11'`, `'7'`), which a derived score must not rest on: it
    # would move with the decimal-places setting. The producer holds the number, so it hands it over, and the line, the label, the units and the cell's text do not move
    # (`tests/test_topology_analysis_typed.py` holds them to a recording made before any of this was typed). **The counts typed are the ones that are neither an always-on descriptor nor ambiguous.** Four are the
    # always-on descriptors under other labels, identical on all 34 molecules compared (atoms, rings, rotatable bonds, chiral centres); the largest and smallest ring size read 0 when there is no ring, which a score
    # would take for a tiny ring; and the aromatic, aliphatic and heteroaromatic ring counts test the ATOMS for aromaticity, which is not RDKit's count (biphenylene 3 here, 2 there). Those seven stay text. An integer
    # stays an `int`, since every one of these is a count of atoms, bonds, rings or paths; a rounded Randic index reading `6` is not, which is why this types at the producer and no parser could do it.
    typed = {**indices, **counts}
    facts = tuple(replace(fact, value=typed[fact.label]) if fact.label in typed else fact for fact in report.facts)
    return replace(report, facts=facts)


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
        provenance=Provenance(
            created_by="core",
            method="rdkit",
            parameters={
                "decimal_places": _places,
                ATOM_BASIS: atom_basis_of(mol),
                # DECLINED. An eccentricity is the greatest distance from
                # one atom to any other; adding thirteen of them together
                # gives 65 for aspirin, which is not a graph invariant, not
                # a molecular property, and not anything. The graph HAS
                # aggregate eccentricity measures -- the radius (minimum)
                # and the diameter (maximum) -- and the Topology Analysis
                # report already gives both, so nothing is lost by refusing
                # here.
                TOTAL: decline_total(
                    "Eccentricity is a per-atom graph distance; a sum over atoms is not "
                    "a molecular quantity. The graph-level measures are the radius and "
                    "the diameter, which Topology Analysis reports."
                ),
            },
        ),
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
        provenance=Provenance(
            created_by="core",
            method="rdkit",
            parameters={
                "decimal_places": _places,
                ATOM_BASIS: atom_basis_of(mol),
                # This one DOES have a molecular meaning, and it is not the
                # sum. Each atom's distance degree counts every path from
                # it, so summing counts each pair from both ends: the sum
                # is TWICE the Wiener index. Declaring the raw sum would
                # have been the "correct but unnamed" failure -- aspirin's
                # 492 is a real number belonging to a quantity nobody
                # names, while its Wiener index is 246.
                TOTAL: declare_total(
                    sum(distance_degree(mol).values()) / 2.0,
                    "Wiener index",
                    units="",
                    basis=atom_basis_of(mol),
                ),
            },
        ),
    )
