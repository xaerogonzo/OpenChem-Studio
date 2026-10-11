"""A bond to a metal is not a steric contact: `analyze_pose` must not report a coordinated metal as a clash.

MEASURED 2026-10-11, before the fix: an imidazole whose pyridine-type nitrogen was given a metal along its
lone pair at a typical coordination distance reported one clash AND one metal coordination for Zn (2.1 A),
Fe (2.0) and Mg (2.1), and three clashes AND one coordination for Ca and Na (2.4). The two extra clashes
were the nitrogen's own ring carbons, 3.39 and 3.40 A from the metal: bond geometry (the M-N-C angle is
126-131 degrees, Harding 1999 Table 6), not a contact. A larger radius, which is the more correct one
(Alvarez 2013: Fe 2.44), only makes it worse.

Every test here calls `analyze_pose` on a real pose and real receptor atoms, so a helper that is right while
the wiring is not (the project has been bitten by that more than once) cannot pass.

The distances are Harding's CSD means for the donor and metal in question, not remembered numbers
[source:harding1999]: Zn-N(imidazole) 2.00, Fe-N 2.08, Mn-N 2.19, Cu-N 1.99, Ca-N 2.44 (one observation),
Mg-O(water) 2.07. The first five metals are also run at the distances the defect was first measured at.
Na (and K, Co, Ni) have no table in Harding; their cases use the existing 2.8 A cutoff and say so.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolTransforms

from openchem.chem.pose_analysis import (
    _METALS,
    METAL_COORDINATION_CUTOFF,
    METAL_DONOR_MIN_DISTANCE,
    ReceptorAtom,
    analyze_pose,
)


def _imidazole() -> tuple[Chem.Mol, int]:
    """Imidazole with hydrogens, MMFF94-optimised, and the index of its pyridine-type nitrogen."""
    mol = Chem.AddHs(Chem.MolFromSmiles("c1c[nH]cn1"))
    assert AllChem.EmbedMolecule(mol, randomSeed=7) == 0
    AllChem.MMFFOptimizeMolecule(mol)
    donor = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "N" and a.GetTotalNumHs(includeNeighbors=True) == 0)
    return mol, donor


def _lone_pair_direction(mol: Chem.Mol, donor: int) -> np.ndarray:
    conformer = mol.GetConformer()
    n = np.array(conformer.GetAtomPosition(donor))
    neighbours = [np.array(conformer.GetAtomPosition(a.GetIdx())) for a in mol.GetAtomWithIdx(donor).GetNeighbors()]
    direction = n - sum(neighbours) / len(neighbours)
    return direction / np.linalg.norm(direction)


def _metal_along_lone_pair(mol: Chem.Mol, donor: int, element: str, distance: float, label: str = "MET") -> ReceptorAtom:
    n = np.array(mol.GetConformer().GetAtomPosition(donor))
    position = tuple(float(x) for x in n + _lone_pair_direction(mol, donor) * distance)
    return ReceptorAtom(element, position, label, 1, atom_name=element)


def _analyse(mol: Chem.Mol, receptor: list[ReceptorAtom]) -> dict:
    return analyze_pose(Chem.MolToMolBlock(mol), receptor)


def _single_atom_pose(symbol: str, position=(0.0, 0.0, 0.0)) -> str:
    """One bondless ligand atom: pose_analysis reads element and position, so this is a complete pose."""
    mol = Chem.RWMol()
    mol.AddAtom(Chem.Atom(symbol.capitalize()))
    conformer = Chem.Conformer(1)
    conformer.SetAtomPosition(0, position)
    mol.AddConformer(conformer)
    return Chem.MolToMolBlock(mol.GetMol(), kekulize=False)


# (metal, distance to the imidazole nitrogen in angstrom, where the distance comes from)
COORDINATED_METALS = [
    ("ZN", 2.1, "first measurement of the defect"),
    ("FE", 2.0, "first measurement of the defect"),
    ("MG", 2.1, "first measurement of the defect"),
    ("CA", 2.4, "first measurement of the defect (three clashes)"),
    ("NA", 2.4, "first measurement of the defect (three clashes); no Harding table for Na"),
    ("ZN", 2.00, "Harding 1999 Table 6 mean"),
    ("FE", 2.08, "Harding 1999 Table 6 mean"),
    ("MN", 2.19, "Harding 1999 Table 6 mean"),
    ("CU", 1.99, "Harding 1999 Table 6 mean"),
    ("CA", 2.44, "Harding 1999 Table 6 (one observation)"),
    ("MG", 2.07, "Harding 1999 Table 2 Mg-O(water) mean, used as the Mg donor distance"),
]
_IDS = [f"{element}@{distance}" for element, distance, _ in COORDINATED_METALS]


@pytest.mark.parametrize(("element", "distance", "_origin"), COORDINATED_METALS, ids=_IDS)
def test_a_coordinated_metal_is_not_a_clash_and_stays_a_coordination(element, distance, _origin):
    mol, donor = _imidazole()
    result = _analyse(mol, [_metal_along_lone_pair(mol, donor, element, distance)])

    assert result["clashes"] == [], result["clashes"]
    assert len(result["metal_coordination"]) == 1
    entry = result["metal_coordination"][0]
    assert entry["ligand_element"] == "N"
    assert entry["receptor_residue"] == "MET1"
    assert entry["distance"] == pytest.approx(distance, abs=0.01)


@pytest.mark.parametrize("element", ["CA", "NA"])
def test_the_donors_own_ring_carbons_are_inside_the_bond_not_a_contact(element):
    """The two extra clashes of the original finding. Precondition checked first, so the test cannot pass
    vacuously on a geometry that never put the carbons inside the clash threshold."""
    from openchem.chem.pose_analysis import _VDW_RADII

    mol, donor = _imidazole()
    metal = _metal_along_lone_pair(mol, donor, element, 2.4)
    conformer = mol.GetConformer()
    carbons = [a.GetIdx() for a in mol.GetAtomWithIdx(donor).GetNeighbors() if a.GetSymbol() == "C"]
    assert len(carbons) == 2
    for index in carbons:
        distance = math.dist(tuple(conformer.GetAtomPosition(index)), metal.position)
        assert 3.0 < distance < 3.6
        assert distance < _VDW_RADII["C"] + _VDW_RADII[element] - 0.4, "the carbon must be inside the old threshold"

    assert _analyse(mol, [metal])["clashes"] == []


def test_a_chelate_ring_atom_two_bonds_from_each_donor_is_not_a_contact():
    """Acetylacetonate on calcium. The central carbon is two bonds from BOTH oxygens and sits about 3.3 A from
    the metal, fixed by the six-membered chelate ring; depth 1 would call it a clash, which is why the depth
    is 2."""
    from openchem.chem.pose_analysis import _VDW_RADII

    mol = Chem.AddHs(Chem.MolFromSmiles("CC([O-])=CC(C)=O"))
    assert AllChem.EmbedMolecule(mol, randomSeed=11) == 0
    AllChem.MMFFOptimizeMolecule(mol)
    # The embedder only ever returns extended conformers (O...O 4.3 A at the smallest over 60 tries), which are
    # not a chelate. Turn the molecule into the U-shape a chelate needs by setting the two O-C-C-C dihedrals to
    # zero, then check the oxygens really are a chelate's bite apart.
    atoms = mol.GetAtoms()
    central = next(
        a.GetIdx() for a in atoms
        if a.GetSymbol() == "C" and a.GetTotalNumHs(includeNeighbors=True) == 1
        and sum(1 for n in a.GetNeighbors() if n.GetSymbol() == "C") == 2
    )
    enolate_o = next(a.GetIdx() for a in atoms if a.GetSymbol() == "O" and a.GetFormalCharge() == -1)
    ketone_o = next(a.GetIdx() for a in atoms if a.GetSymbol() == "O" and a.GetFormalCharge() == 0)
    enolate_c = next(n.GetIdx() for n in mol.GetAtomWithIdx(enolate_o).GetNeighbors())
    ketone_c = next(n.GetIdx() for n in mol.GetAtomWithIdx(ketone_o).GetNeighbors())
    conformer = mol.GetConformer()
    rdMolTransforms.SetDihedralDeg(conformer, enolate_o, enolate_c, central, ketone_c, 0.0)
    rdMolTransforms.SetDihedralDeg(conformer, enolate_c, central, ketone_c, ketone_o, 0.0)
    oxygens = [enolate_o, ketone_o]
    bite = math.dist(tuple(conformer.GetAtomPosition(enolate_o)), tuple(conformer.GetAtomPosition(ketone_o)))
    assert 2.4 < bite < 3.1, f"not a chelate-shaped conformer (O...O {bite:.2f})"
    molblock = Chem.MolToMolBlock(mol)
    o1, o2 = (np.array(conformer.GetAtomPosition(i)) for i in oxygens)
    c = np.array(conformer.GetAtomPosition(central))
    midpoint = (o1 + o2) / 2
    axis = (midpoint - c) / np.linalg.norm(midpoint - c)
    half = np.linalg.norm(o1 - o2) / 2
    t = math.sqrt(2.3**2 - half**2)  # each Ca-O 2.3 A
    metal = ReceptorAtom("CA", tuple(float(x) for x in midpoint + axis * t), "CA", 1, atom_name="CA")

    central_distance = math.dist(tuple(c), metal.position)
    assert 3.0 < central_distance < _VDW_RADII["C"] + _VDW_RADII["CA"] - 0.4, central_distance  # inside the old threshold
    result = analyze_pose(molblock, [metal])

    assert result["clashes"] == [], result["clashes"]
    assert len(result["metal_coordination"]) == 2


def test_an_atom_beyond_the_donors_neighbourhood_keeps_the_ordinary_test():
    """The exemption is for the bond's own geometry, not a licence. A bondless carbon, so three or more bonds
    from any donor, 2.0 A from a zinc is a clash as it always was."""
    receptor = [ReceptorAtom("ZN", (2.0, 0.0, 0.0), "ZN", 1, atom_name="ZN")]
    carbon = analyze_pose(_single_atom_pose("C"), receptor)

    assert len(carbon["clashes"]) == 1
    assert carbon["metal_coordination"] == []


def test_an_overlap_closer_than_any_observed_bond_is_still_a_clash():
    """Harding's shortest metal-N/O/S distance is 1.81 A; below `METAL_DONOR_MIN_DISTANCE` the nitrogen is on
    top of the metal, not bonded to it, and stays in the clash test."""
    below = METAL_DONOR_MIN_DISTANCE - 0.3
    result = analyze_pose(_single_atom_pose("N"), [ReceptorAtom("ZN", (below, 0.0, 0.0), "ZN", 1, atom_name="ZN")])

    assert len(result["clashes"]) == 1


def test_a_donor_just_outside_the_bonding_range_is_an_ordinary_contact():
    """Calcium is the case where the two rules differ most: nitrogen 3.0 A from Ca is closer than the radius
    sum less the tolerance (3.46 A) yet outside the coordination cutoff, so it is a clash and not a bond."""
    distance = METAL_COORDINATION_CUTOFF + 0.2
    result = analyze_pose(_single_atom_pose("N"), [ReceptorAtom("CA", (distance, 0.0, 0.0), "CA", 1, atom_name="CA")])

    assert len(result["clashes"]) == 1
    assert result["metal_coordination"] == []


def test_the_neighbourhood_exemption_is_for_the_metal_the_donor_binds_only():
    """A second metal pressed against the ring on the far side keeps its clash with the ring carbon it touches,
    while the metal on the nitrogen's lone pair has none."""
    mol, donor = _imidazole()
    bound = _metal_along_lone_pair(mol, donor, "CA", 2.4, label="BND")
    conformer = mol.GetConformer()
    donors = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "N"]
    # Out along the C-H bond of the carbon furthest from the bound metal.
    target = max(
        (a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "C"),
        key=lambda i: math.dist(tuple(conformer.GetAtomPosition(i)), bound.position),
    )
    hydrogen = next(n.GetIdx() for n in mol.GetAtomWithIdx(target).GetNeighbors() if n.GetSymbol() == "H")
    c, h = (np.array(conformer.GetAtomPosition(i)) for i in (target, hydrogen))
    outward = (h - c) / np.linalg.norm(h - c)
    other = ReceptorAtom("CA", tuple(float(x) for x in c + outward * 2.9), "OTH", 2, atom_name="CA")
    for index in donors:  # precondition: the second metal is not in bonding range of any donor
        assert math.dist(tuple(conformer.GetAtomPosition(index)), other.position) > METAL_COORDINATION_CUTOFF

    result = _analyse(mol, [bound, other])

    assert [c["receptor_residue"] for c in result["clashes"]] == ["OTH2"]
    assert [m["receptor_residue"] for m in result["metal_coordination"]] == ["BND1"]


@pytest.mark.parametrize("metal", sorted(_METALS))
@pytest.mark.parametrize("donor", ["N", "O", "S", "F"])
def test_no_distance_is_reported_as_both_a_coordination_and_a_clash(metal, donor):
    """The invariant behind the whole fix, swept over every distance a bond could have: for a donor above the
    overlap floor, being a coordination excludes being a clash. A pair that is both is the original defect."""
    steps = round((METAL_COORDINATION_CUTOFF - METAL_DONOR_MIN_DISTANCE) / 0.05)
    distances = [round(METAL_DONOR_MIN_DISTANCE + 0.05 * i, 2) for i in range(steps + 1)]
    assert distances[0] == METAL_DONOR_MIN_DISTANCE and distances[-1] == METAL_COORDINATION_CUTOFF
    for distance in distances:
        found = analyze_pose(
            _single_atom_pose(donor),
            [ReceptorAtom(metal, (float(distance), 0.0, 0.0), metal, 1, atom_name=metal)],
        )
        assert found["metal_coordination"], f"{metal}-{donor} at {distance:.2f} is inside the cutoff"
        assert found["clashes"] == [], f"{metal}-{donor} at {distance:.2f} reported as a clash too"


def test_a_ligand_metal_bound_by_a_receptor_donor_is_a_coordination_and_not_a_clash():
    """The other direction: the metal belongs to the ligand. Exempting the pair from the clash test without
    reporting it would make the contact vanish from both lists."""
    receptor = [ReceptorAtom("N", (2.0, 0.0, 0.0), "HIS", 94, atom_name="NE2", chain="A")]
    found = analyze_pose(_single_atom_pose("ZN"), receptor)

    assert found["clashes"] == []
    assert len(found["metal_coordination"]) == 1
    entry = found["metal_coordination"][0]
    assert entry["ligand_element"] == "ZN"
    assert entry["receptor_element"] == "N"
    assert entry["receptor_residue"] == "HIS94"
    assert entry["receptor_chain"] == "A"


def test_a_ligand_metal_overlapping_a_receptor_atom_is_still_a_clash():
    receptor = [ReceptorAtom("N", (METAL_DONOR_MIN_DISTANCE - 0.3, 0.0, 0.0), "HIS", 94, atom_name="NE2")]

    found = analyze_pose(_single_atom_pose("ZN"), receptor)

    assert len(found["clashes"]) == 1


def test_a_receptor_carbon_beside_a_ligand_metal_is_not_made_a_coordination():
    """Only N, O, F and S donate. A receptor carbon 2.0 A from a ligand zinc is a clash, as before."""
    receptor = [ReceptorAtom("C", (2.0, 0.0, 0.0), "LEU", 1, atom_name="CD1")]

    found = analyze_pose(_single_atom_pose("ZN"), receptor)

    assert len(found["clashes"]) == 1
    assert found["metal_coordination"] == []


def test_a_pose_with_no_metal_anywhere_is_unchanged():
    """The negative control: an ordinary hydrogen-bonded, clashing pose gets exactly the answers it got before
    the metal handling existed."""
    receptor = [
        ReceptorAtom("O", (2.7, 0.0, 0.0), "SER", 1, atom_name="OG"),
        ReceptorAtom("C", (1.5, 1.5, 0.0), "LEU", 2, atom_name="CD1"),
    ]
    found = analyze_pose(_single_atom_pose("N"), receptor)

    assert len(found["hbonds"]) == 1
    assert len(found["clashes"]) == 1 and found["clashes"][0]["receptor_residue"] == "LEU2"
    assert found["metal_coordination"] == []
