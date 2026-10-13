"""Naming round 47 (D-239): a protonated ring cation with a ring ketone keeps every sp3 position in its hydro prefixes.

`O=C1CCC=C2[NH2+]C=CCC12` was `5-oxo-1,4,6,7-tetrahydroquinolin-1-ium`: the sp3 fusion carbon 4a and the ketone carbon 5 were in no hydro locant, so OPSIN could not read the name
(the Hantzsch hexahydroquinolinones: 3 of 5 flagged names in the protonated-census population) or read it as a different molecule (`5-oxo-6,7-dihydroquinolin-1-ium` for a 4a-H
structure). The NEUTRAL route was right (`5-oxo-1,4,4a,5,6,7-hexahydroquinoline-4-carboxylic acid`): `indicated_hydrogen_p58` plans the hydrogens, treating an exocyclic C=O as the saturated
ring carbon it is once the ketone is a prefix, but it declined a charged ring atom, so a cation fell to the retained route's own count. A ring cation is named for its NEUTRAL skeleton plus
`-ium` (P-73.1.1), so the plan now runs on the deprotonated twin of a protonated ring N+.

Every name pinned here is read back through OPSIN to its input, charge and stereo included.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.ring_naming.indicated_hydrogen_p58 import _deprotonated_twin

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
ROWS = [
    ("a quinolinone, 4a-H and a ring CH2", "O=C1CCC=C2[NH2+]C=CCC12", "5-oxo-1,4,4a,5,6,7-hexahydroquinolin-1-ium"),
    ("the 2,3-dihydro form", "O=C1CCC=C2[NH2+]CC=CC12", "5-oxo-1,2,4a,5,6,7-hexahydroquinolin-1-ium"),
    ("an iminium N1=C8a with 4a-H", "O=C1CCCC2=[NH+]C=CCC12", "5-oxo-4,4a,5,6,7,8-hexahydroquinolin-1-ium"),
    ("an N1=C2 pyridinium type with 4a-H", "O=C1CCC=C2[NH+]=CC=CC12", "5-oxo-4a,5,6,7-tetrahydroquinolin-1-ium"),
    ("a cross-conjugated dienone cation", "O=C1C=CC=C2C1C=CC=[NH+]2", "5-oxo-4a,5-dihydroquinolin-1-ium"),
    ("a Hantzsch 4-phenyl 4a-H cation", "CC1=C(C(=O)OC)C(c2ccccc2)C2C(=O)CCC=C2[NH2+]1",
     "3-(methoxycarbonyl)-2-methyl-5-oxo-4-phenyl-1,4,4a,5,6,7-hexahydroquinolin-1-ium"),
    ("a Hantzsch cation with no 4a-H", "CC1=C(C(=O)OC)C(c2ccccc2)C2=C([NH2+]1)CCCC2=O",
     "3-(methoxycarbonyl)-2-methyl-5-oxo-4-phenyl-1,4,5,6,7,8-hexahydroquinolin-1-ium"),
    ("octahydro, no 4a-H", "O=C1CCCC2=C1CCC[NH2+]2", "5-oxo-1,2,3,4,5,6,7,8-octahydroquinolin-1-ium"),
    ("a five-membered fused cation", "O=C1CCC=C2[NH2+]CCC12", "4-oxo-2,3,3a,4,5,6-hexahydro-1H-indol-1-ium"),
    ("a plain pyridinium with a ketone prefix (unchanged)", "CC(=O)C1=CC=C[NH+]=C1", "3-acetylpyridin-1-ium"),
    ("a 4-pyridinone cation, the oxo carbon is cited (round 45 pinned the loose form)", "O=C1C=C[NH+]=CC1", "4-oxo-3,4-dihydropyridin-1-ium"),
    ("a saturated parent keeps its saturated name", "O=C1CC[NH+]2CCCC2C1", "7-oxoindolizidin-4-ium"),
]

#: A census structure with two stereocentres; its name was unparsable before.
STEREO = ("CC1=C(C(=O)OCCOc2ccccc2)[C@H](c2ccc(Cl)cc2Cl)[C@H]2C(=O)CCC=C2[NH2+]1",)


@pytest.mark.parametrize("label,smiles,expected", ROWS, ids=[row[0] for row in ROWS])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ROWS, ids=[row[0] for row in ROWS])
def test_the_name_reads_back_to_the_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


@needs_opsin
def test_a_stereo_census_structure_reads_back_with_its_stereo():
    from py2opsin import py2opsin

    smiles = STEREO[0]
    name = name_smiles(smiles)
    back = py2opsin(name)
    assert back, name
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), name


def test_a_quaternary_ring_cation_is_not_touched():
    """No hydrogen to give back: the twin is None and the old route names it, as before."""
    assert _deprotonated_twin(Chem.MolFromSmiles("C[n+]1ccccc1"), frozenset(range(1, 7))) is None
    assert name_smiles("C[n+]1ccccc1") == "1-methylpyridin-1-ium"


def test_the_deprotonated_twin_gives_the_proton_back():
    mol = Chem.MolFromSmiles("O=C1CCC=C2[NH2+]C=CCC12")
    ring = frozenset(a.GetIdx() for a in mol.GetAtoms() if a.IsInRing())
    twin = _deprotonated_twin(mol, ring)
    assert twin is not None and Chem.GetFormalCharge(twin) == 0
    assert Chem.MolToSmiles(twin) == Chem.MolToSmiles(Chem.MolFromSmiles("O=C1CCC=C2NC=CCC12"))
