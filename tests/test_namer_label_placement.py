"""Naming round 29, phase 2: where an isotopic label goes, so that OPSIN reads it, and a labelled ring that is still the ring it is.

A sample of 400 census molecules with one atom labelled (13C, 15N, 18O, or a deuterium on a heteroatom) had 40 names OPSIN could not read after round 28, and 35 of them
were the LABEL's placement (the name with the bracket removed read fine). They fall into four groups, each fixed by moving the bracket to where the book puts it and OPSIN
reads it, and a fifth cause was found on the way: a nuclide anywhere in a ring made the ring unrecognisable.

* **a suffix whose locant is left out** (`butanamide`, `propanal`, `propanol`, `propanenitrile`): the label goes after the locant the name does not print, `butan-1-(18O)amide`,
  `propan-1-(18O)al`, `propane-1-(15N)nitrile`, `N-phenylbutan-1-(15N)amide`. A retained name that numbers nothing keeps the bare front label, `(18O)acetamide`, and puts it after
  the prefixes, `2-chloro-N-phenyl(15N)acetamide`;
* **hydro prefixes**: the bracket follows them, `3,4-dihydro(4-13C)quinolin-1(2H)-yl`, `5,6,7,8-tetrahydro(2-13C)naphthalene`, `2,3-dihydro(1-15N)-1H-indole`;
* **an amino prefix**: the bracket goes before `amino`, `3-[benzoyl(N-2H)amino]propanoic acid`;
* **a compound alkoxy**: before `oxy` on the uncontracted form, `[(phenylmethyl)(18O)oxy]`, where a bare stem keeps `(18O)methoxy`;
* **a labelled ring** (`ring_naming.common._nuclide_free`): the ring is looked up without its nuclides. Labelled benzene was `cyclohexa-1,3,5-triene`, labelled pyridine `azine`, labelled
  naphthalene a naming error, and labelled tetralin `(9-13C)bicyclo[4.4.0]deca-1,3,5-triene`, a name for another molecule.

Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey.
"""
from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
NAMED = [
    # a suffix whose locant is left out
    ("amide oxygen", "CCCC(=[18O])N", "butan-1-(18O)amide"),
    ("amide nitrogen", "CCCC(=O)[15NH2]", "butan-1-(15N)amide"),
    ("N-substituted amide nitrogen", "CCCC(=O)[15NH]c1ccccc1", "N-phenylbutan-1-(15N)amide"),
    ("amide oxygen with a branch", "CC(C)C(=[18O])N", "2-methylpropan-1-(18O)amide"),
    ("aldehyde oxygen", "CCC=[18O]", "propan-1-(18O)al"),
    ("alcohol oxygen", "CCC[18OH]", "propan-1-(18O)ol"),
    ("nitrile nitrogen", "CCC#[15N]", "propane-1-(15N)nitrile"),
    ("a long chain amide of an aniline", "CCCCCCCCC(=[18O])Nc1ccc(Br)cc1F", "N-(4-bromo-2-fluorophenyl)nonan-1-(18O)amide"),
    ("ketone: unchanged", "[18O]=C(C)c1ccccc1", "1-phenylethan-1-(18O)one"),
    # a retained name keeps the bare label, and cites it after the prefixes
    ("retained acetamide", "CC(=[18O])N", "(18O)acetamide"),
    ("retained acetamide with a prefix", "ClCC(=[18O])N", "2-chloro(18O)acetamide"),
    ("retained acetamide with a prefix and a substituent on N", "ClCC(=O)[15NH]c1ccccc1", "2-chloro-N-phenyl(15N)acetamide"),
    ("retained benzamide", "[15NH2]C(=O)c1ccc(Cl)cc1", "4-chloro(15N)benzamide"),
    # hydro prefixes
    ("a dihydroquinolinyl", "O=C(CCl)N1CC[13CH2]c2ccccc21", "2-chloro-1-[3,4-dihydro(4-13C)quinolin-1(2H)-yl]ethan-1-one"),
    ("tetrahydronaphthalene", "C1CCc2cc[13cH]cc2C1", "1,2,3,4-tetrahydro(6-13C)naphthalene"),
    ("a dihydroindole, no prefix", "C1Cc2ccccc2[15NH]1", "2,3-dihydro(1-15N)-1H-indole"),
    ("a dihydroindole with a prefix", "Clc1ccc2[15NH]CCc2c1", "5-chloro-2,3-dihydro(1-15N)-1H-indole"),
    ("a dihydroquinolinone", "O=C1CCc2cc[13cH]cc2N1", "3,4-dihydro(7-13C)quinolin-2(1H)-one"),
    ("a hydro prefix without locants", "C1CC2CCCCC2[15NH]1", "octahydro(1-15N)-1H-indole"),
    ("a benzimidazolone", "O=c1[nH]c2cc[13cH]cc2[nH]1", "1,3-dihydro(5-13C)-2H-benzimidazol-2-one"),
    # an amino prefix
    ("an acylamino with a deuterium", "[2H]N(C(=O)c1ccccc1)CCC(=O)O", "3-[benzoyl(N-2H)amino]propanoic acid"),
    ("another", "CC(=O)N([2H])CCC(=O)O", "3-[acetyl(N-2H)amino]propanoic acid"),
    # a compound alkoxy
    ("benzyloxy", "COc1cc2c(cc1[18O]Cc1ccccc1)NC(=O)C2", "5-methoxy-6-[(phenylmethyl)(18O)oxy]-1,3-dihydro-2H-indol-2-one"),
    ("a substituted phenoxy", "OC(=O)C[18O]c1ccc(Cl)cc1", "[(4-chlorophenyl)(18O)oxy]acetic acid"),
    ("a branched alkoxy", "CC(C)C[18O]CC(=O)O", "[(2-methylpropyl)(18O)oxy]acetic acid"),
    ("a bare stem keeps the contraction", "C[18O]CC(=O)O", "(18O)methoxyacetic acid"),
    ("two nuclides in a bare stem share a bracket", "[13CH3][18O]CC(=O)O", "[(1-13C,18O)methoxy]acetic acid"),
    # a labelled ring is still the ring it is
    ("benzene", "[13cH]1ccccc1", "(6-13C)benzene"),
    ("naphthalene (was a naming error)", "[13cH]1ccc2ccccc2c1", "(7-13C)naphthalene"),
    ("pyridine (was azine)", "[13cH]1cccnc1", "(5-13C)pyridine"),
    ("tetralin (was a bicyclo name for another molecule)", "c1cc2CCCCc2c[13cH]1", "1,2,3,4-tetrahydro(6-13C)naphthalene"),
    ("a substituted benzene ring", "Clc1cc[13cH]cc1", "chloro(4-13C)benzene"),
    ("a lactone ring (the exo-oxo extractors)", "O=c1ccc2cc[13cH]cc2o1", "(7-13C)-2H-1-benzopyran-2-one"),
    ("an imide ring", "O=C1c2cc[13cH]cc2C(=O)N1", "(5-13C)-1H-isoindole-1,3(2H)-dione"),
    ("an acetophenone's ring", "CC(=O)c1ccc([13cH]c1)Cl", "1-[4-chloro(3-13C)phenyl]ethan-1-one"),
]

# What this round does not change.
UNCHANGED = [
    ("a label on a methyl keeps its locant", "[13CH3]c1ccccc1", "[(1-13C)methyl]benzene"),
    ("indole's own label", "[13cH]1ccc2[nH]ccc2c1", "(5-13C)-1H-indole"),
    ("the parent's front bracket with no prefix", "[13CH3]CC", "(3-13C)propane"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[row[0] for row in NAMED])
def test_the_label_is_where_opsin_reads_it(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_name_reads_back_to_the_labelled_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


@pytest.mark.parametrize("label,smiles,expected", UNCHANGED, ids=[row[0] for row in UNCHANGED])
def test_what_this_round_leaves_alone(label, smiles, expected):
    assert name_smiles(smiles) == expected


def test_a_ring_without_a_nuclide_is_looked_up_as_before():
    """The helper returns the molecule itself when nothing is labelled, so an ordinary molecule pays nothing and keeps every name."""
    from openchem.vendor.iupac_namer.ring_naming.common import _nuclide_free

    plain = Chem.MolFromSmiles("c1ccc2ccccc2c1")
    assert _nuclide_free(plain) is plain
    labelled = Chem.MolFromSmiles("[13cH]1ccc2ccccc2c1")
    stripped = _nuclide_free(labelled)
    assert stripped is not labelled
    assert all(atom.GetIsotope() == 0 for atom in stripped.GetAtoms())
    assert labelled.GetAtomWithIdx(0).GetIsotope() == 13                    # the molecule the caller holds is not changed


def test_a_nuclide_in_a_ring_does_not_change_which_ring_it_is():
    assert name_smiles("[13cH]1ccc2ccccc2c1").endswith("naphthalene")
    assert name_smiles("[13cH]1cccnc1").endswith("pyridine")
    assert "bicyclo" not in name_smiles("C1CCc2cc[13cH]cc2C1")
    assert "triene" not in name_smiles("Cc1cc[13cH]cc1")
