"""Naming round 52 (D-250 .. D-252): a second acid in an azanide's acyl group, the thioamide anion, and a positive chalcogen taken for a carbonyl.

D-250: the acyl group of an amide anion is named by cutting the nitrogen off, naming the acid and turning its name into the acyl name. When the same fragment held a SECOND acid (a glutaric or
maleic half-amide) the name became a DIACYL group, `(pentanedioyl)(...)azanide`, which silently dropped the free acid. Such a group is now written by the branch namer, with the carboxy as a prefix.
D-251: a thioamide / thiourea anion (`CC(=S)[N-]C`) was claimed by the amine-anion classifier, which could not render it, so it was refused; the azanide route names it, `ethanethioyl(methyl)azanide`.
D-252: S-protonated thiourea `NC(N)=[SH+]` matched the `thioamide` suffix group through its sulfonium sulfur, so the sulfonium parent and the group both claimed that atom and a nitrogen fell out
of the name: `thiocarbamoylsulfanium`, a different molecule and no refusal. A suffix group never names a positive chalcogen now. The same hole made `carbamoyloxidanium` of a protonated urea.

Found by `tools/naming_ion_populations.py` with ten site patterns it had not tried (an acyclic amide, a urea, a thioamide, an oxime, a phosphonic and a sulfinic acid; a thiocarbonyl sulfur, a sulfoxide
oxygen, a phosphine, a nitrile nitrogen).
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
DIACID = [
    ("a maleic half-amide anion", "O=C(O)C=CC(=O)[N-]c1ccc2c(c1)Cc1ccccc1-2", "(3-carboxy-1-oxoprop-2-en-1-yl)(9H-fluoren-2-yl)azanide"),
    ("a glutaric half-amide anion", "OC(=O)CCCC(=O)[N-]c1nccs1", "(4-carboxy-1-oxobutyl)(1,3-thiazol-2-yl)azanide"),
    ("a cyclohexane half-amide anion", "O=C(O)[C@@H]1CCCC[C@H]1C(=O)[N-]c1cccc(Cl)c1Cl", "(2,3-dichlorophenyl)[[(1R,2R)-2-carboxycyclohexyl](oxo)methyl]azanide"),
    ("an acylthiourea anion with an acid on the other side", "COc1cccc(C(=O)[N-]C(=S)Nc2cccc(C(=O)O)c2C)c1",
     "[(3-carboxy-2-methylanilino)(thioxo)methyl](3-methoxybenzoyl)azanide"),
]

THIOAMIDE_ANION = [
    ("a thioacetamide anion", "CC(=S)[N-]C", "ethanethioyl(methyl)azanide"),
    ("a thiourea anion", "NC(=S)[N-]c1ccccc1", "aminomethanethioyl(phenyl)azanide"),
    ("an N-methylthiourea anion", "CNC(=S)[N-]c1ccccc1", "[(methylamino)methanethioyl](phenyl)azanide"),
    ("a ring thiourea anion", "S=C1[N-]CCN1", "2-sulfanylideneimidazolidin-1-ide"),
]

CHALCOGEN_CATION = [
    ("S-protonated thiourea", "NC(N)=[SH+]", "(diaminomethylidene)sulfanium"),
    ("S-protonated aminothiourea", "NNC(N)=[SH+]", "[amino(hydrazinyl)methylidene]sulfanium"),
    ("O-protonated bis-isobutyl hydrazine urea", "CC(C)CNN(CC(C)C)C(N)=[OH+]", "{amino[1,2-bis(2-methylpropyl)hydrazinyl]methylidene}oxidanium"),
]

ALL = DIACID + THIOAMIDE_ANION + CHALCOGEN_CATION


def _neutral_key(smiles: str) -> str:
    """The InChIKey with every negative charge not beside a positive one removed: standard InChI places a proton, so the question is the connectivity."""
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


def test_the_diacyl_name_that_dropped_the_acid_is_gone():
    assert "pentanedioyl" not in name_smiles("OC(=O)CCCC(=O)[N-]c1nccs1")


def test_an_ordinary_amide_anion_keeps_the_acid_route():
    assert name_smiles("CC(=O)[N-]c1ccccc1") == "acetyl(phenyl)azanide"
    assert name_smiles("CC(=O)[N-]C") == "acetyl(methyl)azanide"


def test_a_neutral_thioamide_and_thiourea_are_untouched():
    assert name_smiles("CC(=S)NC") == "N-methylethanethioamide"
    assert name_smiles("NC(N)=S") == "thiourea"


def test_a_protonated_amide_is_still_the_ylidene_cation():
    assert name_smiles("CC(N)=[OH+]") == "(1-aminoethylidene)oxidanium"
    assert name_smiles("CSC(N)=[NH2+]") == "[amino(methylsulfanyl)methylidene]azanium"


def test_a_sulfoxide_and_a_neutral_amide_are_untouched():
    assert name_smiles("CC(=O)N") == "acetamide"
    assert name_smiles("CS(C)=O") == "(methanesulfinyl)methane"
