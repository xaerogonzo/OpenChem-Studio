"""WP2 of docs/HYPERVALENT_COVERAGE_DESIGN.md: a five- or six-coordinate centre is not counted as a stereocentre.

Measured before the fix: topology analysis said "Chiral center count: 1" and the stereo descriptors "1 stereo element(s),
1 undefined" for SF6, PF5, PCl5, IF5, Ph-SF5 and CH3-PF4, while the always-on count and the stereocentre calculators already said 0.
Every control keeps the answer it had.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.bbb_stereo import compute_stereo_descriptors, stereo_descriptors
from openchem.chem.stereo_elements import MAX_STEREO_COORDINATION, perceived_elements, unassessed_centres
from openchem.chem.topology_analysis import compute_topology_analysis, stereo_counts

HIGH = {
    "SF6": "FS(F)(F)(F)(F)F", "PF5": "FP(F)(F)(F)F", "PCl5": "ClP(Cl)(Cl)(Cl)Cl", "IF5": "FI(F)(F)(F)F",
    "PhSF5": "FS(F)(F)(F)(F)c1ccccc1", "CH3PF4": "CP(F)(F)(F)F", "MeSF5": "CS(F)(F)(F)(F)F", "SF5Cl": "FS(F)(F)(F)(F)Cl",
}
#: smiles -> (asymmetric atoms, chiral centres): the numbers these gave before this change, unchanged.
CONTROLS = {
    "CHFClBr": ("C(F)(Cl)Br", 1, 1), "R": ("[C@H](F)(Cl)Br", 1, 1), "sulfoxide": ("C[S@](=O)CC", 1, 1),
    "sulfoximine": ("C[S@](=N)(=O)CC", 1, 1), "phosphine": ("C[P@](CC)c1ccccc1", 1, 1),
    "ammonium": ("C[N+](CC)(CCC)Cc1ccccc1", 1, 1), "ethanol": ("CCO", 0, 0), "XeF4": ("F[Xe](F)(F)F", 0, 0),
    "SF4": ("FS(F)(F)F", 0, 0), "benzene": ("c1ccccc1", 0, 0), "limonene": ("CC1=CCC(CC1)C(C)=C", 1, 1),
    "dimethylcyclohexane": ("CC1CCC(C)CC1", 0, 2),
}


@pytest.mark.parametrize("name", HIGH)
def test_five_and_six_coordinate_centres_are_not_counted(name):
    mol = Chem.MolFromSmiles(HIGH[name])
    assert stereo_counts(mol)["chiral_center_count"] == 0
    assert stereo_descriptors(mol) == []
    assert len(unassessed_centres(mol)) == 1, "reported as not assessed, not as achiral"


@pytest.mark.parametrize("name", HIGH)
def test_the_reports_say_not_assessed_instead_of_one_centre(name):
    mol = Chem.MolFromSmiles(HIGH[name])
    lines = compute_stereo_descriptors(mol, "u").matched
    assert not any("1 stereo element" in line for line in lines)
    assert any("not assessed" in line for line in lines)
    facts = {f.label: f.display_value for f in compute_topology_analysis(mol, "u").facts}
    assert facts["Chiral center count"] == "0"


@pytest.mark.parametrize("name", CONTROLS)
def test_the_controls_keep_their_answers(name):
    smiles, asymmetric, centres = CONTROLS[name]
    mol = Chem.MolFromSmiles(smiles)
    counts = stereo_counts(mol)
    assert (counts["asymmetric_atom_count"], counts["chiral_center_count"]) == (asymmetric, centres)
    assert unassessed_centres(mol) == []
    assert len(perceived_elements(mol)) == len(Chem.FindPotentialStereo(mol))


def test_a_stereo_element_that_is_not_an_atom_is_kept():
    mol = Chem.MolFromSmiles("C/C=C/C")
    assert [str(e.type) for e in perceived_elements(mol)] == [str(e.type) for e in Chem.FindPotentialStereo(mol)] != []


def test_the_limit_is_the_tetrahedral_one():
    assert MAX_STEREO_COORDINATION == 4
    assert unassessed_centres(Chem.MolFromSmiles("C[P@@](F)(Cl)(Br)I")) != [], "a five-coordinate phosphorus is not assessed"
