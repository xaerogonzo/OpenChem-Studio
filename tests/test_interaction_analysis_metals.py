"""A bond to a metal is not a steric clash inside one molecule either: `find_interactions` must not report a
coordinated metal as a clash.

`tests/test_pose_analysis_metals.py` holds the same rule for a docked pose. This is the intramolecular sibling.
MEASURED 2026-10-11, before the fix: `c1c[nH]cn1.[Zn+2]` (a SEPARATE fragment, the metal placed 2.0 A from the
pyridine-type nitrogen along its lone pair) reported one clash AND one metal coordination for the same pair.
A zinc bonded in the molecule was never affected, because `MIN_SEPARATION['clashes']` excludes it by bond-path
distance; a disconnected fragment has infinite bond-path distance, so nothing excluded it.

Every test calls `find_interactions` on a real embedded molecule, so a helper that is right while the wiring is
not cannot pass. The distances are Harding's CSD means [source:harding1999] (the same ones the pose tests use),
plus the first measurement of the defect.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.interaction_analysis import find_interactions
from openchem.chem.pose_analysis import (
    _METALS,
    _VDW_RADII,
    CLASH_TOLERANCE,
    METAL_COORDINATION_CUTOFF,
    METAL_DONOR_MIN_DISTANCE,
)


def _symbol(element: str) -> str:
    return element.capitalize()


def _imidazole_with_metals(*elements: str) -> tuple[Chem.Mol, int, list[int]]:
    """Imidazole (with hydrogens) plus one SEPARATE fragment per metal. Returns the molecule, the pyridine-type
    nitrogen's index and the metals' indices. The metals start wherever the embedder put them; the caller places
    them. Not force-field optimised: MMFF has no parameters for the metals, and the ring embeds well enough."""
    smiles = "c1c[nH]cn1" + "".join(f".[{_symbol(e)}]" for e in elements)
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=7) == 0
    donor = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "N" and a.GetTotalNumHs(includeNeighbors=True) == 0)
    metals = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol().upper() in _METALS]
    assert len(metals) == len(elements)
    return mol, donor, metals


def _lone_pair_point(mol: Chem.Mol, donor: int, distance: float) -> tuple[float, float, float]:
    conformer = mol.GetConformer()
    n = np.array(conformer.GetAtomPosition(donor))
    neighbours = [np.array(conformer.GetAtomPosition(a.GetIdx())) for a in mol.GetAtomWithIdx(donor).GetNeighbors()]
    direction = n - sum(neighbours) / len(neighbours)
    direction /= np.linalg.norm(direction)
    return tuple(float(x) for x in n + direction * distance)


def _coordinated(element: str, distance: float) -> tuple[Chem.Mol, int, int]:
    mol, donor, (metal,) = _imidazole_with_metals(element)
    mol.GetConformer().SetAtomPosition(metal, _lone_pair_point(mol, donor, distance))
    return mol, donor, metal


def _two_atom_molecule(donor: str, metal: str, distance: float) -> Chem.Mol:
    """A donor atom and a metal, no bond between them, `distance` apart: the smallest molecule with the pair."""
    mol = Chem.RWMol()
    mol.AddAtom(Chem.Atom(donor))
    mol.AddAtom(Chem.Atom(_symbol(metal)))
    conformer = Chem.Conformer(2)
    conformer.SetAtomPosition(0, (0.0, 0.0, 0.0))
    conformer.SetAtomPosition(1, (float(distance), 0.0, 0.0))
    mol.AddConformer(conformer)
    result = mol.GetMol()
    Chem.SanitizeMol(result)
    return result


def _pairs(entries: list[dict]) -> list[tuple[int, int]]:
    return sorted(tuple(sorted(e["atoms"])) for e in entries)


# (metal, distance to the imidazole nitrogen in angstrom, where the distance comes from)
COORDINATED_METALS = [
    ("ZN", 2.0, "first measurement of the defect"),
    ("ZN", 2.00, "Harding 1999 Table 6 mean"),
    ("FE", 2.08, "Harding 1999 Table 6 mean"),
    ("MN", 2.19, "Harding 1999 Table 6 mean"),
    ("CU", 1.99, "Harding 1999 Table 6 mean"),
    ("CA", 2.44, "Harding 1999 Table 6 (one observation)"),
    ("MG", 2.07, "Harding 1999 Table 2 Mg-O(water) mean, used as the Mg donor distance"),
    ("NA", 2.4, "no Harding table for Na; inside the existing 2.8 A cutoff"),
]
_IDS = [f"{element}@{distance}" for element, distance, _ in COORDINATED_METALS]


@pytest.mark.parametrize(("element", "distance", "_origin"), COORDINATED_METALS, ids=_IDS)
def test_a_separate_metal_on_the_lone_pair_is_a_coordination_and_not_a_clash(element, distance, _origin):
    mol, donor, metal = _coordinated(element, distance)

    found = find_interactions(mol)

    assert found["clashes"] == [], found["clashes"]
    assert _pairs(found["metal_coordination"]) == [tuple(sorted((donor, metal)))]
    assert found["metal_coordination"][0]["distance"] == pytest.approx(distance, abs=0.01)


@pytest.mark.parametrize("element", ["CA", "NA"])
def test_the_donors_own_ring_carbons_are_inside_the_bond_not_a_contact(element):
    """Ca and Na at 2.4 A put both ring carbons 3.4 A from the metal, inside the radius-sum threshold (the
    pose-analysis finding). Precondition checked first, so this cannot pass on a geometry that never put them
    there."""
    mol, donor, metal = _coordinated(element, 2.4)
    conformer = mol.GetConformer()
    carbons = [a.GetIdx() for a in mol.GetAtomWithIdx(donor).GetNeighbors() if a.GetSymbol() == "C"]
    assert len(carbons) == 2
    for index in carbons:
        distance = math.dist(tuple(conformer.GetAtomPosition(index)), tuple(conformer.GetAtomPosition(metal)))
        assert 3.0 < distance < _VDW_RADII["C"] + _VDW_RADII[element] - CLASH_TOLERANCE, distance

    assert find_interactions(mol)["clashes"] == []


def test_the_neighbourhood_exemption_is_for_the_metal_the_donor_binds_only():
    """A second calcium pressed against the far ring carbon keeps its clash, while the one on the nitrogen's lone
    pair has none."""
    mol, donor, (bound, other) = _imidazole_with_metals("CA", "CA")
    conformer = mol.GetConformer()
    conformer.SetAtomPosition(bound, _lone_pair_point(mol, donor, 2.4))
    bound_position = np.array(conformer.GetAtomPosition(bound))
    target = max(
        (a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "C" and a.GetIdx() < 5),
        key=lambda i: np.linalg.norm(np.array(conformer.GetAtomPosition(i)) - bound_position),
    )
    hydrogen = next(n.GetIdx() for n in mol.GetAtomWithIdx(target).GetNeighbors() if n.GetSymbol() == "H")
    c, h = (np.array(conformer.GetAtomPosition(i)) for i in (target, hydrogen))
    outward = (h - c) / np.linalg.norm(h - c)
    conformer.SetAtomPosition(other, tuple(float(x) for x in c + outward * 2.9))
    for index in (a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "N"):  # the second metal binds nothing
        assert math.dist(tuple(conformer.GetAtomPosition(index)), tuple(conformer.GetAtomPosition(other))) > METAL_COORDINATION_CUTOFF

    found = find_interactions(mol)

    assert _pairs(found["clashes"]) == [tuple(sorted((target, other)))]
    assert _pairs(found["metal_coordination"]) == [tuple(sorted((donor, bound)))]


def test_a_metal_bonded_in_the_molecule_is_unchanged():
    """The control. A zinc joined to the nitrogen by a bond was never a clash (bond-path separation 1) and is not
    a coordination either (coordination starts at separation 3). The fix must leave that as it was."""
    mol = Chem.AddHs(Chem.MolFromSmiles("[Zn]n1ccnc1"))
    assert AllChem.EmbedMolecule(mol, randomSeed=7) == 0
    zinc = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "Zn")
    bonded_nitrogen = next(n.GetIdx() for n in mol.GetAtomWithIdx(zinc).GetNeighbors())
    assert Chem.GetDistanceMatrix(mol)[zinc][bonded_nitrogen] == 1
    conformer = mol.GetConformer()
    assert math.dist(tuple(conformer.GetAtomPosition(zinc)), tuple(conformer.GetAtomPosition(bonded_nitrogen))) < METAL_COORDINATION_CUTOFF

    found = find_interactions(mol)

    assert not any(zinc in pair for pair in _pairs(found["clashes"]))
    assert not any(zinc in pair for pair in _pairs(found["metal_coordination"]))


def test_an_atom_beyond_the_donors_neighbourhood_keeps_the_ordinary_test():
    """The exemption is for the bond's own geometry, not a licence. A carbon with no donor within two bonds,
    2.0 A from a separate zinc, is a clash as it always was."""
    mol = _two_atom_molecule("C", "ZN", 2.0)

    found = find_interactions(mol)

    assert _pairs(found["clashes"]) == [(0, 1)]
    assert found["metal_coordination"] == []


def test_an_overlap_closer_than_any_observed_bond_is_still_a_clash():
    """Harding's shortest metal-N/O/S distance is 1.81 A [source:harding1999]; below `METAL_DONOR_MIN_DISTANCE`
    the nitrogen is on top of the metal, not bonded to it, and stays in the clash test."""
    mol = _two_atom_molecule("N", "ZN", METAL_DONOR_MIN_DISTANCE - 0.3)

    assert _pairs(find_interactions(mol)["clashes"]) == [(0, 1)]


def test_a_donor_just_outside_the_bonding_range_is_an_ordinary_contact():
    """Calcium is where the two rules differ most: nitrogen 3.0 A from Ca is closer than the radius sum less the
    tolerance (3.46 A) yet outside the coordination cutoff, so it is a clash and not a bond."""
    mol = _two_atom_molecule("N", "CA", METAL_COORDINATION_CUTOFF + 0.2)

    found = find_interactions(mol)

    assert _pairs(found["clashes"]) == [(0, 1)]
    assert found["metal_coordination"] == []


@pytest.mark.parametrize("metal", sorted(_METALS))
@pytest.mark.parametrize("donor", ["N", "O", "S", "F"])
def test_no_distance_is_reported_as_both_a_coordination_and_a_clash(metal, donor):
    """The invariant behind the fix, swept over every distance a bond could have: for a donor above the overlap
    floor, being a coordination excludes being a clash. A pair that is both is the original defect. Sulfur is in
    the sweep because the clash exemption takes `_is_metal_donor`, and an exemption wider than the
    detector would make a Zn--S contact vanish from both lists."""
    steps = round((METAL_COORDINATION_CUTOFF - METAL_DONOR_MIN_DISTANCE) / 0.05)
    distances = [round(METAL_DONOR_MIN_DISTANCE + 0.05 * i, 2) for i in range(steps + 1)]
    assert distances[0] == METAL_DONOR_MIN_DISTANCE and distances[-1] == METAL_COORDINATION_CUTOFF
    for distance in distances:
        found = find_interactions(_two_atom_molecule(donor, metal, distance))
        assert _pairs(found["metal_coordination"]) == [(0, 1)], f"{metal}-{donor} at {distance:.2f} is inside the cutoff"
        assert found["clashes"] == [], f"{metal}-{donor} at {distance:.2f} reported as a clash too"


def test_a_sulfoxide_sulfur_is_not_a_donor_so_it_is_neither_exempt_nor_coordinated():
    """The exemption is exactly the detector's donor set. A sulfoxide sulfur has valence 4 (its oxygen is the
    donor), so a zinc 2.3 A from it is an ordinary contact: no coordination, and the clash stays. An exemption
    wider than the detector would make this contact vanish from both lists."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CS(C)=O.[Zn]"))
    assert AllChem.EmbedMolecule(mol, randomSeed=7) == 0
    sulfur = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "S")
    zinc = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "Zn")
    conformer = mol.GetConformer()
    conformer.SetAtomPosition(zinc, _lone_pair_point(mol, sulfur, 2.3))
    assert _VDW_RADII["S"] + _VDW_RADII["ZN"] - CLASH_TOLERANCE > 2.3, "precondition: 2.3 A is inside the clash threshold"

    found = find_interactions(mol)

    assert (min(sulfur, zinc), max(sulfur, zinc)) in _pairs(found["clashes"])
    assert not any(zinc in pair for pair in _pairs(found["metal_coordination"]))


def test_a_molecule_with_no_metal_is_unchanged():
    """The negative control: an ordinary molecule gets the answers it got before the metal handling existed."""
    mol = Chem.AddHs(Chem.MolFromSmiles("OC(=O)c1ccccc1O"))  # salicylic acid
    assert AllChem.EmbedMolecule(mol, randomSeed=7) == 0
    AllChem.MMFFOptimizeMolecule(mol)

    found = find_interactions(mol)

    assert found["metal_coordination"] == []
    assert found["clashes"] == []
