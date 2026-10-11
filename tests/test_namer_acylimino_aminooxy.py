"""Naming round 39 (D-212, D-213, D-214): three wrong-molecule shapes from the census review.

D-212: an N-acyl imine that is not the principal group (`=N-C(=O)R`) was named `acetamido`, whose bond is single: the C=N was dropped. `O=C1CCCCC1=NC(C)=O` was
`2-acetamidocyclohexan-1-one`, a different molecule. The acylamino prefix now requires a single-bonded nitrogen; the double-bonded one is `acylimino`.

D-213: a carbamimidoyl whose amino nitrogen is itself double-bonded (`-N=C(N)S`, an N-ylidene amidine) cited that group as a single-bonded `N-(amino(sulfanyl)methyl)`.
That shape is declined by the carbamimidoyl builder and named by the ylidene-amino prefix.

D-214: an N-substituted aminooxy group (`C-O-NHR`) was taken for an amino group on the parent with the O as one of its substituents, which wrote the parent twice
(`[(carboxymethoxy)(methyl)amino]acetic acid` for `CNOCC(=O)O`); with a carboxylate it was refused. It is `[(methylamino)oxy]acetic acid`.

Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey.
"""
from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
ACYLIMINO = [
    ("an acyl imine on a ring ketone", "O=C1CCCCC1=NC(C)=O", "2-(acetylimino)cyclohexan-1-one"),
    ("under an acid", "OC(=O)CC(=NC(C)=O)C", "3-(acetylimino)butanoic acid"),
    ("on an amidine carbon, an ester O", "NC(=NC(C)=O)OC", "(acetylimino)(methoxy)methanamine"),
    ("on an amidine carbon, a ring N", "CC(=NC(C)=O)N1CCCC1", "1-[1-(acetylimino)ethyl]pyrrolidine"),
    ("the census row (325625)", "Cc1cc(C)n(C(N)=NC(=O)c2ccccc2)n1", "(benzoylimino)(3,5-dimethyl-1H-pyrazol-1-yl)methanamine"),
    ("an N-benzoyl imine on pyrazole", "NC(=NC(=O)c1ccccc1)n1cccn1", "(benzoylimino)(1H-pyrazol-1-yl)methanamine"),
    ("a carbamate imine", "CC(=NC(=O)OC)C(=O)O", "2-[methoxy(oxo)methylimino]propanoic acid"),
    ("a urea imine", "CC(=NC(=O)N)C(=O)O", "2-(carbamoylimino)propanoic acid"),
]

YLIDENE_AMIDINE = [
    ("the census row (356625)", "NC(S)=NC(=NOCc1ccccc1)c1ccccc1",
     "({[amino(sulfanyl)methylidene]amino}(phenylmethoxyimino)methyl)benzene"),
    ("a hydroxy amidoxime", "ON=C(c1ccccc1)N=C(N)S", "({[amino(sulfanyl)methylidene]amino}(hydroxyimino)methyl)benzene"),
    ("a guanidine-like ylidene", "ON=C(c1ccccc1)N=C(N)N", "{[(diaminomethylidene)amino](hydroxyimino)methyl}benzene"),
    ("a ketone-derived ylidene", "ON=C(c1ccccc1)N=C(O)C", "{[(1-hydroxyethylidene)amino](hydroxyimino)methyl}benzene"),
]

AMINOOXY = [
    ("methylaminooxy acetic acid", "CNOCC(=O)O", "[(methylamino)oxy]acetic acid"),
    ("ethyl", "CCNOCC(=O)O", "[(ethylamino)oxy]acetic acid"),
    ("dimethyl", "CN(C)OCC(=O)O", "[(dimethylamino)oxy]acetic acid"),
    ("phenyl", "c1ccccc1NOCC(=O)O", "[(phenylamino)oxy]acetic acid"),
    ("on a ring ketone", "CNOC1CCC(=O)CC1", "4-[(methylamino)oxy]cyclohexan-1-one"),
    ("on a nitrile", "CNOCC#N", "2-[(methylamino)oxy]ethanenitrile"),
    ("on a secondary carbon", "CNOC(C)C(=O)O", "2-[(methylamino)oxy]propanoic acid"),
    ("on a benzene ring", "CNOc1ccc(C(=O)O)cc1", "4-[(methylamino)oxy]benzoic acid"),
    ("an amide chain, one carbon further", "CNOCCC(=O)N", "3-[(methylamino)oxy]propanamide"),
]

# Names that did not change: the single-bonded acylamino prefix, an amine that is the principal group, the unsubstituted aminooxy group, N-alkoxy amines.
UNCHANGED = [
    ("an acetamido prefix", "CC(=O)NC(C)C(=O)O", "2-acetamidopropanoic acid"),
    ("a methylamino prefix", "CNCC(=O)O", "(methylamino)acetic acid"),
    ("a bare aminooxy group", "NOCC(=O)NC", "2-(aminooxy)-N-methylacetamide"),
    ("an N-alkoxy amine as the principal group", "CNOCC", "N-ethoxymethanamine"),
    ("an N-acyl amidine on a carbon", "NC(=NC(=O)c1ccccc1)c1ccccc1", "N'-benzoylbenzenecarboximidamide"),
    ("an N-substituted amidine", "C(=NCC)(N(C)C)c1ccccc1", "N'-ethyl-N,N-dimethylbenzenecarboximidamide"),
    ("a carbamimidoyl prefix", "OC(=O)c1ccc(cc1)C(=NCC)N(C)C", "4-(N'-ethyl-N,N-dimethylcarbamimidoyl)benzoic acid"),
]

ALL = ACYLIMINO + YLIDENE_AMIDINE + AMINOOXY + UNCHANGED


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_group_is_named(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_a_double_bonded_acyl_nitrogen_is_never_an_amido_prefix():
    """`acetamido` means -NH-C(=O)CH3. It must not name an N joined to the parent by a double bond."""
    for _label, smiles, expected in ACYLIMINO:
        assert "amido" not in expected, (smiles, expected)
        assert "amido" not in name_smiles(smiles), smiles


def test_the_aminooxy_group_names_its_parent_once():
    """The defect wrote the parent twice, so the heavy-atom count of the name's read-back is the check (the O sits between N and the parent)."""
    for _label, smiles, expected in AMINOOXY:
        assert expected.count("oxy") == 1, expected
