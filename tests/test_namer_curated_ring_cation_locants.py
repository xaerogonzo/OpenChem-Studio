"""Naming round 35 (D-208): a ring cation on a curated fused parent keeps its -ium.

A curated retained ring (`data_loader._RING_CURATED_SMILES`) lists `atom_locants` for the positions a substituent can take, and six of them left out the ring heteroatoms
and fusion atoms. The engine adds the `-ium` at the locant of the charged ring atom and, finding none, SKIPPED the atom: the cation of `Cc1[nH+]c2c(s1)CCCC2` was named
`2-methyl-4,5,6,7-tetrahydro-1,3-benzothiazole`, the neutral compound, which OPSIN reads as another molecule. 528 of 700 cations of the six parents were wrong and 44 more
unreadable. The six tables now give every ring atom its locant, and a plan whose cationic ring atom has no locant fails (the next plan is tried) instead of dropping the charge.

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
    ("tetrahydrobenzothiazole N3", "CC(=O)C1CCCc2[nH+]csc21", "7-acetyl-4,5,6,7-tetrahydro-1,3-benzothiazol-3-ium"),
    ("2-methyl tetrahydrobenzothiazolium", "Cc1[nH+]c2c(s1)CCCC2", "2-methyl-4,5,6,7-tetrahydro-1,3-benzothiazol-3-ium"),
    ("2-acetamido tetrahydrobenzothiazolium", "CC(=O)Nc1[nH+]c2c(s1)CCCC2", "2-acetamido-4,5,6,7-tetrahydro-1,3-benzothiazol-3-ium"),
    ("pyrazolo[1,5-a]pyrimidine N1", "CC(=O)Nc1c[n+](C)n2cccnc12", "3-acetamido-1-methylpyrazolo[1,5-a]pyrimidin-1-ium"),
    ("pyrazolo[1,5-a]pyrimidine N4", "CC(=O)Nc1c[nH+]c2ccnn2c1", "6-acetamidopyrazolo[1,5-a]pyrimidin-4-ium"),
    ("thiazolo[5,4-d]pyrimidine N1", "CC(=O)Nc1[nH+]c2cncnc2s1", "2-acetamidothiazolo[5,4-d]pyrimidin-1-ium"),
    ("thiazolo[5,4-d]pyrimidine N4", "CC(=O)Nc1nc2cnc[n+](C)c2s1", "2-acetamido-4-methylthiazolo[5,4-d]pyrimidin-4-ium"),
    ("thiazolo[5,4-d]pyrimidine N6", "CC(=O)Nc1[nH+]cnc2scnc12", "7-acetamidothiazolo[5,4-d]pyrimidin-6-ium"),
    ("tetrahydrothieno[3,2-c]pyridine N5", "CC(=O)C1C[NH2+]Cc2ccsc21", "7-acetyl-4,5,6,7-tetrahydrothieno[3,2-c]pyridin-5-ium"),
    ("tetrahydrotriazolopyrazine N1", "CC(=O)C1CNCc2[nH+]ncn21", "5-acetyl-5,6,7,8-tetrahydro-[1,2,4]triazolo[4,3-a]pyrazin-1-ium"),
    ("tetrahydrotriazolopyrazine N2", "CC(=O)C1CNCc2n[n+](C)cn21", "5-acetyl-2-methyl-5,6,7,8-tetrahydro-[1,2,4]triazolo[4,3-a]pyrazin-2-ium"),
    ("tetrahydrotriazolopyrazine N7", "CC(=O)C1C[NH2+]Cc2nncn21", "5-acetyl-5,6,7,8-tetrahydro-[1,2,4]triazolo[4,3-a]pyrazin-7-ium"),
    ("tetrahydrotriazolopyridine N1", "CC(=O)C1CCCc2[nH+]ncn21", "5-acetyl-5,6,7,8-tetrahydro-[1,2,4]triazolo[4,3-a]pyridin-1-ium"),
    ("tetrahydrotriazolopyridine N2", "CC(=O)C1CCCc2n[n+](C)cn21", "5-acetyl-2-methyl-5,6,7,8-tetrahydro-[1,2,4]triazolo[4,3-a]pyridin-2-ium"),
]

# The neutral parents keep their names (the locants added are heteroatoms and fusion atoms, which no substituent takes).
UNCHANGED = [
    ("neutral 2-methyl tetrahydrobenzothiazole", "Cc1nc2c(s1)CCCC2", "2-methyl-4,5,6,7-tetrahydro-1,3-benzothiazole"),
    ("neutral 6-methyl pyrazolo[1,5-a]pyrimidine", "Cc1cnc2ccnn2c1", "6-methylpyrazolo[1,5-a]pyrimidine"),
    ("neutral 2-methyl thiazolo[5,4-d]pyrimidine", "Cc1nc2cncnc2s1", "2-methylthiazolo[5,4-d]pyrimidine"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_ring_cation_is_named(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_name_reads_back_to_the_cation(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[row[0] for row in NAMED])
def test_a_cation_is_never_named_as_its_neutral_parent(label, smiles, expected):
    assert "ium" in name_smiles(smiles)


def test_a_curated_table_names_every_ring_heteroatom_it_can_be_charged_on():
    """The table half of the defect: a ring N/S/O the table gives no locant is a cation that cannot be named. Six are complete now; the rest are listed, so the next one is a deliberate act."""
    from openchem.vendor.iupac_namer.data_loader import _RING_CURATED_SMILES

    fixed = ["c1cnc2ccnn2c1", "c1ncc2ncsc2n1", "c1nnc2n1CCNC2", "c1nnc2n1CCCC2", "c1nc2c(s1)CCCC2", "c1cc2c(s1)CCNC2"]
    for key in fixed:
        locants = _RING_CURATED_SMILES[key]["atom_locants"]
        mol = Chem.MolFromSmiles(key)
        missing = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() in ("N", "S", "O") and a.IsInRing() and a.GetIdx() not in locants]
        assert not missing, (key, missing)


def test_a_plan_whose_cationic_ring_atom_has_no_locant_fails_instead_of_dropping_the_charge():
    # The hexahydropyrido[2,1-a]isoquinoline entry still lists no locant for its nitrogen. Its cation was named as the NEUTRAL ring (a different molecule) until the plan failed
    # instead; the next plan names it as a von Baeyer cation, which OPSIN reads back.
    name = name_smiles("c1ccc2c(c1)CC[NH+]1CCCCC21")
    assert "ium" in name and "hexahydro-2H-pyrido[2,1-a]isoquinoline" not in name
