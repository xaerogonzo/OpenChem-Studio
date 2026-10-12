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
    CLASH_TOLERANCE,
    METAL_DONOR_MIN_DISTANCE,
    METAL_DONOR_TARGETS,
    ReceptorAtom,
    _vdw_radius,
    analyze_pose,
    is_metal_bond,
    is_metal_contact,
    metal_bond_window,
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
    distance = metal_bond_window("CA", "N")[1] + 0.12
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
        assert math.dist(tuple(conformer.GetAtomPosition(index)), other.position) > metal_bond_window("CA", "N")[1]

    result = _analyse(mol, [bound, other])

    assert [c["receptor_residue"] for c in result["clashes"]] == ["OTH2"]
    assert [m["receptor_residue"] for m in result["metal_coordination"]] == ["BND1"]


@pytest.mark.parametrize("metal", sorted(_METALS))
@pytest.mark.parametrize("donor", ["N", "O", "S", "F"])
def test_no_distance_is_reported_as_both_a_coordination_and_a_clash(metal, donor):
    """The invariant behind the whole fix, swept over every distance a bond could have: inside THIS metal's window for
    THIS donor, being a coordination excludes being a clash. A pair that is both is the original defect."""
    low, high = metal_bond_window(metal, donor)
    edge = 1e-9  # the window's ends are floats (2.41 - 0.5 is 1.9100000000000001): test just inside them
    distances = [d for d in (low + edge + 0.05 * i for i in range(int((high - low) / 0.05) + 2)) if d < high - edge]
    distances.append(high - edge)
    for distance in distances:
        found = analyze_pose(
            _single_atom_pose(donor),
            [ReceptorAtom(metal, (float(distance), 0.0, 0.0), metal, 1, atom_name=metal)],
        )
        assert found["metal_coordination"], f"{metal}-{donor} at {distance:.3f} is inside its window {low:.2f}-{high:.2f}"
        assert found["clashes"] == [], f"{metal}-{donor} at {distance:.3f} reported as a clash too"


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


# --- per-metal bond windows (the follow-up to the single 1.8-2.8 A window) -----------------------------------------------

#: Harding 2006 Table 4, transcribed from the page image: O water, O Asp or Glu monodentate, O main-chain carbonyl,
#: N histidine, S cysteine; None where the paper gives no value [source:harding2006].
HARDING_2006_TABLE_4 = {
    "NA": (2.41, 2.41, 2.38, None, None),
    "MG": (2.07, 2.07, 2.26, None, None),
    "K": (2.81, 2.82, 2.74, None, None),
    "CA": (2.39, 2.36, 2.36, None, None),
    "MN": (2.19, 2.15, 2.19, 2.21, 2.35),
    "FE": (2.09, 2.04, 2.04, 2.16, 2.30),
    "CO": (2.09, 2.05, 2.08, 2.14, 2.25),
    "CU": (2.13, 1.99, 2.04, 2.02, 2.15),
    "ZN": (2.09, 1.99, 2.07, 2.03, 2.31),
}
#: N and S entries Harding marks as estimates for want of data (2001 Table 1 for Mg and Ca; 2002 Table 2a for Na and K).
HARDING_ESTIMATES = {"MG": (2.05, 2.23), "CA": (2.38, 2.56), "NA": (2.38, 2.56), "K": (2.80, 2.98)}
#: Zheng et al. 2017 Table 3 (CSD means), the larger where two values are printed [source:zheng2017].
ZHENG_NICKEL = {"O": 2.08, "N": 2.09, "S": 2.46}


def test_every_metal_the_detector_knows_has_a_target_for_every_donor():
    assert set(METAL_DONOR_TARGETS) == _METALS
    assert all(set(targets) == {"O", "N", "S"} for targets in METAL_DONOR_TARGETS.values())


@pytest.mark.parametrize("metal", sorted(HARDING_2006_TABLE_4))
def test_the_targets_are_harding_2006_table_4(metal):
    water, carboxylate, carbonyl, nitrogen, sulfur = HARDING_2006_TABLE_4[metal]
    targets = METAL_DONOR_TARGETS[metal]

    assert targets["O"] == max(water, carboxylate, carbonyl)
    if nitrogen is not None:
        assert (targets["N"], targets["S"]) == (nitrogen, sulfur)
    else:
        assert (targets["N"], targets["S"]) == HARDING_ESTIMATES[metal]


def test_nickel_is_zhengs_csd_means_because_harding_has_none():
    assert METAL_DONOR_TARGETS["NI"] == ZHENG_NICKEL


@pytest.mark.parametrize(("metal", "donor", "low", "high"), [
    ("ZN", "N", 1.80, 2.53),   # 2.03 + 0.5; 2.03 - 0.5 is under the 1.8 floor
    ("ZN", "S", 1.81, 2.81),   # 2.31 -/+ 0.5
    ("FE", "N", 1.80, 2.66),
    ("MG", "O", 1.80, 2.76),   # carbonyl 2.26 is the longest Mg-O
    ("CU", "N", 1.80, 2.52),
    ("CA", "O", 1.89, 2.89),
    ("NI", "S", 1.96, 2.96),
    ("NA", "O", 1.91, 3.16),   # + 0.75 for sodium and potassium
    ("K", "O", 2.32, 3.57),
    ("K", "N", 2.30, 3.55),
    ("CA", "F", 1.89, 2.89),   # fluorine reads the oxygen entry of the hard cations (and of no other metal)
])
def test_the_window_is_the_target_less_and_plus_the_margins(metal, donor, low, high):
    assert metal_bond_window(metal, donor) == pytest.approx((low, high), abs=1e-9)


def test_an_unknown_metal_or_donor_has_no_window():
    assert metal_bond_window("PB", "O") is None and metal_bond_window("ZN", "C") is None
    assert not is_metal_bond("PB", "O", 2.3) and not is_metal_contact("ZN", "C", 2.0)


def test_a_metal_the_old_window_called_bonded_is_no_longer_when_it_is_too_far_for_that_donor():
    """Zinc to a histidine nitrogen at 2.7 A was inside the single 2.8 A window. Harding's bond is 2.03 A (window to
    2.53); 2.7 A is the weak-interaction range he describes for zinc (2.4-3.0), not a bond, and with zinc's 1.39 A
    radius it is not a clash either."""
    found = analyze_pose(_single_atom_pose("N"), [ReceptorAtom("ZN", (2.7, 0.0, 0.0), "ZN", 1, atom_name="ZN")])

    assert found["metal_coordination"] == []
    assert found["clashes"] == []


@pytest.mark.parametrize(("distance", "bond", "clash"), [
    (3.50, True, False),    # inside the primary sphere, 2.82 + 0.75 = 3.57: a bond, as Harding counts potassium
    (3.70, False, False),   # his secondary sphere runs to 2.82 + 0.95 = 3.77: a normal contact of the ion, no clash
    (3.80, False, True),    # past it, and still inside the radius rule's 3.87: ordinary again
    (3.95, False, False),   # past that too
])
def test_potassium_contacts_run_on_past_the_bond_and_are_not_clashes(distance, bond, clash):
    """With one 2.8 A window every real K+...O contact beyond it was a clash: 3.5 A is inside 2.75 + 1.52 - 0.4 = 3.87.
    The fixture is checked against the old rule first, so the test cannot pass on a geometry that never mattered."""
    assert distance < 3.87 or not clash
    found = analyze_pose(_single_atom_pose("O"), [ReceptorAtom("K", (distance, 0.0, 0.0), "K", 1, atom_name="K")])

    assert bool(found["metal_coordination"]) is bond
    assert bool(found["clashes"]) is clash


@pytest.mark.parametrize(("distance", "bond", "clash"), [
    (3.10, True, False),    # 2.41 + 0.75 = 3.16
    (3.25, False, False),   # secondary sphere to 2.41 + 0.95 = 3.36
    (3.38, False, True),    # sodium's radius rule is 2.27 + 1.52 - 0.4 = 3.39
])
def test_sodium_contacts_run_on_past_the_bond_and_are_not_clashes(distance, bond, clash):
    found = analyze_pose(_single_atom_pose("O"), [ReceptorAtom("NA", (distance, 0.0, 0.0), "NA", 1, atom_name="NA")])

    assert bool(found["metal_coordination"]) is bond
    assert bool(found["clashes"]) is clash


def test_only_sodium_and_potassium_get_a_contact_zone_beyond_the_bond():
    """For Ca, Mg and the transition metals a donor past the primary sphere (Harding: usually refinement error or
    weak bonding) stays an ordinary contact."""
    for metal in sorted(_METALS - {"NA", "K"}):
        low, high = metal_bond_window(metal, "O")
        assert is_metal_bond(metal, "O", high) and not is_metal_bond(metal, "O", high + 0.05)
        assert not is_metal_contact(metal, "O", high + 0.05)
    assert is_metal_contact("K", "O", 3.70) and not is_metal_bond("K", "O", 3.70)


def test_sodium_and_potassium_have_a_floor_harding_states_the_others_the_survey_minimum():
    """Harding 2002: a K+ or Na+ distance 0.5 A under the target is not acceptable. Na-O at 1.85 A is above the
    survey floor of 1.8 and below Na's own 1.91, so it is overlap and stays a clash."""
    found = analyze_pose(_single_atom_pose("O"), [ReceptorAtom("NA", (1.85, 0.0, 0.0), "NA", 1, atom_name="NA")])

    assert found["metal_coordination"] == []
    assert len(found["clashes"]) == 1
    assert metal_bond_window("K", "O")[0] == pytest.approx(2.82 - 0.5)
    assert metal_bond_window("ZN", "O")[0] == METAL_DONOR_MIN_DISTANCE


def test_a_ligand_carried_potassium_bound_by_a_receptor_oxygen_follows_the_same_window():
    receptor = [ReceptorAtom("O", (3.5, 0.0, 0.0), "HOH", 1, atom_name="O")]
    found = analyze_pose(_single_atom_pose("K"), receptor)

    assert found["clashes"] == []
    assert len(found["metal_coordination"]) == 1


# --- fluorine: a donor to Na, K and Ca when it is on carbon, to every metal when it is a fluoride ion -----------------------
# Plenio 1997, Murray-Rust 1983 and the PDB survey (`benchmarks/fluorine_pdb_survey/`) for the carbon-bound fluorine; Bakewell 2016
# for magnesium (3.2-3.5 A to a C-F, 1.95 A to a fluoride).

ORGANIC_FLUORINE_DONOR_METALS = ["CA", "K", "NA"]
NOT_ORGANIC_FLUORINE_DONOR_METALS = ["CO", "CU", "FE", "MG", "MN", "NI", "ZN"]


def _fluoromethane_pose(partner: str = "C") -> str:
    """A fluorine at the origin bonded to `partner` (carbon by default), which sits 1.38 A away on the far side from the metal."""
    mol = Chem.RWMol()
    mol.AddAtom(Chem.Atom(partner))
    mol.AddAtom(Chem.Atom("F"))
    mol.AddBond(0, 1, Chem.BondType.SINGLE)
    conformer = Chem.Conformer(2)
    conformer.SetAtomPosition(0, (-1.38, 0.0, 0.0))
    conformer.SetAtomPosition(1, (0.0, 0.0, 0.0))
    mol.AddConformer(conformer)
    return Chem.MolToMolBlock(mol.GetMol(), kekulize=False)


def _metal_at(metal: str, distance: float) -> list[ReceptorAtom]:
    return [ReceptorAtom(metal, (distance, 0.0, 0.0), metal, 1, atom_name=metal)]


def test_every_metal_is_either_an_organic_fluorine_donor_or_not_and_the_two_lists_cover_them_all():
    assert set(ORGANIC_FLUORINE_DONOR_METALS) | set(NOT_ORGANIC_FLUORINE_DONOR_METALS) == _METALS
    assert not set(ORGANIC_FLUORINE_DONOR_METALS) & set(NOT_ORGANIC_FLUORINE_DONOR_METALS)


@pytest.mark.parametrize("metal", sorted(_METALS))
def test_a_fluoride_ion_reads_the_oxygen_window_of_every_metal(metal):
    assert metal_bond_window(metal, "F") == metal_bond_window(metal, "O")


@pytest.mark.parametrize("metal", ORGANIC_FLUORINE_DONOR_METALS)
def test_a_carbon_bound_fluorine_reads_the_oxygen_window_of_sodium_potassium_and_calcium(metal):
    assert metal_bond_window(metal, "CF") == metal_bond_window(metal, "O")


@pytest.mark.parametrize("metal", NOT_ORGANIC_FLUORINE_DONOR_METALS)
def test_a_carbon_bound_fluorine_has_no_window_to_any_other_metal_magnesium_included(metal):
    assert metal_bond_window(metal, "CF") is None
    for distance in (1.9, 2.1, 2.5, 3.0):
        assert not is_metal_bond(metal, "CF", distance) and not is_metal_contact(metal, "CF", distance)
    assert metal_bond_window(metal, "O") is not None  # the restriction is about this fluorine, not the metal


@pytest.mark.parametrize("metal", NOT_ORGANIC_FLUORINE_DONOR_METALS)
def test_a_carbon_bound_fluorine_inside_the_old_oxygen_window_is_a_clash_and_not_a_coordination(metal):
    """Before: fluorine at 2.3 A of any of these metals was a bond and exempt from the clash test. The precondition is
    checked, so the test cannot pass on a distance the radius rule never reached."""
    distance = 2.3
    assert distance < _vdw_radius("F") + _vdw_radius(metal) - CLASH_TOLERANCE

    found = analyze_pose(_fluoromethane_pose(), _metal_at(metal, distance))

    assert found["metal_coordination"] == []
    assert len(found["clashes"]) == 1


@pytest.mark.parametrize("partner", ["B", "C"])
def test_a_boron_bound_fluorine_is_restricted_like_a_carbon_bound_one(partner):
    found = analyze_pose(_fluoromethane_pose(partner), _metal_at("ZN", 2.3))

    assert found["metal_coordination"] == []


def test_a_fluorine_at_the_zinc_contact_distances_plenio_lists_is_neither_a_bond_nor_a_clash():
    """Zn...F 2.53-2.73 A occurs in crowded organometallics [source:plenio1997]: an ordinary contact."""
    found = analyze_pose(_fluoromethane_pose(), _metal_at("ZN", 2.55))

    assert found["metal_coordination"] == []
    assert found["clashes"] == []


@pytest.mark.parametrize(("metal", "distance"), [("NA", 2.47), ("K", 2.80), ("CA", 2.52)])
def test_a_carbon_bound_fluorine_at_a_measured_hard_cation_distance_is_a_coordination_and_not_a_clash(metal, distance):
    """Na...F 2.470 and K...F 2.80 are Murray-Rust's [source:murrayrust1983], Ca...F 2.524 is Plenio's
    [source:plenio1997] and 2.57 is the PDB survey's (7ZLU)."""
    found = analyze_pose(_fluoromethane_pose(), _metal_at(metal, distance))

    assert len(found["metal_coordination"]) == 1
    assert found["metal_coordination"][0]["ligand_element"] == "F"
    assert found["clashes"] == []


@pytest.mark.parametrize("metal", sorted(_METALS))
def test_a_fluoride_ion_at_a_bonding_distance_from_any_metal_is_a_coordination_and_not_a_clash(metal):
    """A bare fluorine has no carbon or boron, so it is a fluoride ion: Mg-F 1.953 A in the fluoride-bridged dimer of
    [source:bakewell2016]. Two angstrom for every metal, but potassium, whose oxygen window starts at 2.32."""
    found = analyze_pose(_single_atom_pose("F"), _metal_at(metal, 2.8 if metal == "K" else 2.0))

    assert len(found["metal_coordination"]) == 1
    assert found["clashes"] == []


def test_a_receptor_fluorine_beside_a_ligand_zinc_is_a_coordination_because_it_arrives_without_bonds():
    """Documented limit: the receptor is coordinates, so a fluoride ion cannot be told from a cofactor's C-F, and it is read
    as a fluoride ion."""
    found = analyze_pose(_single_atom_pose("Zn"), [ReceptorAtom("F", (2.0, 0.0, 0.0), "F", 1, atom_name="F")])

    assert len(found["metal_coordination"]) == 1
    assert found["clashes"] == []
