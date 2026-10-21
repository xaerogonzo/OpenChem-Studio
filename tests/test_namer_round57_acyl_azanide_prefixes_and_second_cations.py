"""Naming round 57 (D-271 .. D-274): an acyl- or sulfonyl-type group whose nitrogen is the anion, a protonated amidoxime beside a second cation, and N-acyl ureas.

The multi-charge populations of round 55 listed what was still refused; this round names them.

D-271: an acylsulfonamide anion (`S(=O)(=O)[N-]C(N)=O`) beside a CATION. The cation took the parent and the plan search wrote the sulfonamide as the ordinary `N-carbamoylsulfamoyl` prefix, which
  has no charge: the anion was dropped and the guard (round 55) refused the name. When a cation is elsewhere the sulfonyl is a group of the azanide, `carbamoyl[...sulfonyl]azanide`.
D-272: a sulfonamide or amide whose own nitrogen is the anion, cited as a PREFIX because another anion is the parent: `4-[(carbamoylazanidyl)sulfonyl]benzen-1-olate`,
  `4-[(methylazanidyl)carbonyl]benzen-1-olate` (it was refused, the charge having been dropped from the `sulfamoyl` / `carbamoyl` prefix). OPSIN reads `(...azanidyl)sulfonyl` and `(...azanidyl)carbonyl`.
D-273: a protonated amidoxime `=[NH+]OH` beside a second cation was written with a neutral `hydroxyimino` (one of two cations gone from the name, refused by the round 56 guard); its prefix is
  `hydroxyazaniumylidene`.
D-274: an O-protonated or O-alkylated N-ACYL UREA or thiourea (`CCCC(=[OH+])NC(=S)NAr`) was refused: the urea group elsewhere claimed the carbon. The oxonium classifier takes it.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
ACYLSULFONAMIDE_BESIDE_CATION = [
    ("an acylsulfonamide anion beside a thiazolium", "NC(=O)[N-]S(=O)(=O)c1ccc(-c2[nH+]ccs2)cc1", "carbamoyl[4-(1,3-thiazol-3-ium-2-yl)phenylsulfonyl]azanide"),
    ("the same beside an ammonium", "NC(=O)[N-]S(=O)(=O)c1ccc(C[NH3+])cc1", "[4-(azaniumylmethyl)phenylsulfonyl](carbamoyl)azanide"),
    ("a methylsulfonamide anion beside a thiazolium", "CS(=O)(=O)[N-]c1ccc(-c2[nH+]ccs2)cc1", "methanesulfonyl[4-(1,3-thiazol-3-ium-2-yl)phenyl]azanide"),
]

AZANIDYL_ACYL_PREFIX = [
    ("an acylsulfonamide anion beside a phenolate", "NC(=O)[N-]S(=O)(=O)c1ccc([O-])cc1", "4-[(carbamoylazanidyl)sulfonyl]benzen-1-olate"),
    ("an N-acetylsulfonamide anion beside a phenolate", "CC(=O)[N-]S(=O)(=O)c1ccc([O-])cc1", "4-[(acetylazanidyl)sulfonyl]benzen-1-olate"),
    ("a sulfonamide anion beside a phenolate", "C[N-]S(=O)(=O)c1ccc([O-])cc1", "4-[(methylazanidyl)sulfonyl]benzen-1-olate"),
    ("an acylsulfonamide anion beside a thiolate", "NC(=O)[N-]S(=O)(=O)c1ccc([S-])cc1", "4-[(carbamoylazanidyl)sulfonyl]benzene-1-thiolate"),
    ("an amide anion beside a phenolate", "C[N-]C(=O)c1ccc([O-])cc1", "4-[(methylazanidyl)carbonyl]benzen-1-olate"),
]

AMIDOXIME_DICATION = [
    ("a protonated amidoxime beside a piperazinium", "O[NH+]=C(c1ncc(C(F)(F)F)cc1Cl)N1CC[NH+](Cc2ccccc2)CC1",
     "1-benzyl-4-{[3-chloro-5-(trifluoromethyl)pyridin-2-yl](hydroxyazaniumylidene)methyl}piperazin-1-ium"),
    ("a protonated amidoxime beside a pyridinium", "O[NH+]=C(c1[nH+]cc(C(F)(F)F)cc1Cl)N1CCN(Cc2ccccc2)CC1",
     "2-[(4-benzylpiperazin-1-yl)(hydroxyazaniumylidene)methyl]-3-chloro-5-(trifluoromethyl)pyridin-1-ium"),
]

OXONIUM_ACYLUREA = [
    ("an O-protonated acylthiourea", "CCCC(=[OH+])NC(=S)Nc1ccccc1", "{1-[(anilinomethanethioyl)amino]butylidene}oxidanium"),
    ("an O-protonated acylurea", "CCCC(=[OH+])NC(=O)Nc1ccccc1", "{1-{[anilino(oxo)methyl]amino}butylidene}oxidanium"),
    ("an O-methylated acylthiourea", "CCCC(=[O+]C)NC(=S)Nc1ccccc1", "{1-[(anilinomethanethioyl)amino]butylidene}(methyl)oxidanium"),
]

ALL = ACYLSULFONAMIDE_BESIDE_CATION + AZANIDYL_ACYL_PREFIX + AMIDOXIME_DICATION + OXONIUM_ACYLUREA


def _neutral_key(smiles: str) -> str:
    """InChIKey with the anions' charge removed (standard InChI places a proton), cations kept."""
    mol = Chem.RWMol(Chem.MolFromSmiles(smiles))
    for atom in mol.GetAtoms():
        if atom.GetFormalCharge() < 0 and not any(n.GetFormalCharge() > 0 for n in atom.GetNeighbors()):
            atom.SetFormalCharge(0)
            atom.SetNoImplicit(True)
            atom.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
    Chem.SanitizeMol(mol)
    return Chem.MolToInchiKey(mol)


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_ion(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    mol = Chem.MolFromSmiles(back)
    assert Chem.GetFormalCharge(mol) == Chem.GetFormalCharge(Chem.MolFromSmiles(smiles)), (expected, back)
    assert _neutral_key(back) == _neutral_key(smiles), (expected, back)


def test_the_single_anion_acylsulfonamide_is_still_a_sulfonamidate():
    assert name_smiles("NC(=O)[N-]S(=O)(=O)c1ccccc1") == "N-carbamoylbenzenesulfonamidate"
    assert name_smiles("NC(=O)[N-]S(=O)(=O)c1ccc(C(=O)[O-])cc1") == "4-[(carbamoylazanidyl)sulfonyl]benzoate"


def test_a_sulfonamide_anion_beside_a_carboxylate_is_a_prefix_on_the_carboxylate():
    assert name_smiles("C[N-]S(=O)(=O)c1ccc(C(=O)[O-])cc1") == "4-[(methylazanidyl)sulfonyl]benzoate"


def test_a_neutral_sulfonamide_and_amidoxime_are_untouched():
    assert name_smiles("CS(=O)(=O)NC") == "N-methylmethanesulfonamide"
    assert name_smiles("CC(=N)NO") == "N-hydroxyethanimidamide"


def test_a_lone_protonated_amidoxime_keeps_its_old_name():
    assert name_smiles("CC(=[NH+]O)N") == "(1-aminoethylidene)(hydroxy)azanium"


def test_the_ordinary_protonated_amide_is_not_taken_by_the_urea_rule():
    assert name_smiles("CCCC(=[OH+])NC") == "[1-(methylamino)butylidene]oxidanium"
    assert name_smiles("CCCC(=[OH+])NC(C)=O") == "(1-acetamidobutylidene)oxidanium"
