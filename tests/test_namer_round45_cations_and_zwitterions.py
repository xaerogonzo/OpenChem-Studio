"""Naming round 45 (D-233, D-234): a ring cation keeps its curated ketone suffix after the cation suffix, and an amidinium zwitterion with a second acid is named.

D-233: camptothecin's pentacycle is a curated ring whose NAME carries its ketone (`...quinoline-3,14(4H)-dione`). A ring cation has no suffix group to put `-ium` before, so it was
appended after the `dione`: `...-3,14(4H)-dion-6-ium`, which OPSIN cannot read (round 41's "a curated ring cation OPSIN cannot check"). It goes before the ketone suffix, as it does
before any other suffix (P-74): `...quinolin-6-ium-3,14(4H)-dione`, which reads back, camptothecin itself included.

D-234: an amidinium with a carboxylate AND a neutral carboxylic acid was refused (round 44's open item): protonating the carboxylate left two `carboxy` words, and a count cannot say
which was the anion. The neutral acid is named as its methyl ester, whose prefix cannot be confused, and the two are mapped back: `3-carboxylato-4-hydroxy-4-oxobutanamidinium`,
`3-carboxylato-5-carboxybenzamidinium`. (A quaternary carbon carrying both acids was refused until naming round 49; a carboxylate beside TWO neutral acids still is.)

The census scan's read-back now tries the application's OPSIN-readable respellings for a name OPSIN failed to parse (`N1,N2-...oxamide`, `oxobis[...]phosphanyl`, `bis([1,3]dioxolo)...`, a
CIP descriptor OPSIN cannot assign on a cage), so the four names whose engine form is the book's are no longer counted as unparsable.

Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
CAMPTOTHECIN = [
    ('the camptothecin pentacycle, protonated', 'O=C1Cc2cc3n(c(=O)c2CO1)Cc1cc2ccccc2[nH+]c1-3', "1,12-dihydro-14H-pyrano[3',4':6,7]indolizino[1,2-b]quinolin-6-ium-3,14(4H)-dione"),
    ('camptothecin itself, protonated', 'CCC1(O)C(=O)OCc2c1cc1n(c2=O)Cc2cc3ccccc3[nH+]c2-1', "4-ethyl-4-hydroxy-1,12-dihydro-14H-pyrano[3',4':6,7]indolizino[1,2-b]quinolin-6-ium-3,14(4H)-dione"),
    ('the N-methyl cation of the pentacycle', 'C[n+]1c2ccccc2cc2c1-c1cc3c(c(=O)n1C2)COC(=O)C3', "6-methyl-1,12-dihydro-14H-pyrano[3',4':6,7]indolizino[1,2-b]quinolin-6-ium-3,14(4H)-dione"),
]

KETONE_CATION_UNCHANGED = [
    ('an indolizidinone cation (an oxo prefix)', 'O=C1CC[NH+]2CCCC2C1', '7-oxoindolizidin-4-ium'),
    ('a 4-pyridinone cation', 'O=C1C=C[NH+]=CC1', '4-oxo-3,4-dihydropyridin-1-ium'),
]

SECOND_ACID = [
    ('a zwitterion beside a carboxylic acid, one carbon', 'NC(=[NH2+])CC(C(=O)[O-])C(=O)O', '3-carboxylato-4-hydroxy-4-oxobutanamidinium'),
    ('the carboxylic acid and the carboxylate swapped', 'NC(=[NH2+])CC(C(=O)O)C(=O)[O-]', '3-carboxylato-4-hydroxy-4-oxobutanamidinium'),
    ('two carbons between', 'NC(=[NH2+])CCC(C(=O)[O-])C(=O)O', '4-carboxylato-5-hydroxy-5-oxopentanamidinium'),
    ('the acid and the carboxylate on separate arms', 'NC(=[NH2+])C(CC(=O)[O-])CC(=O)O', '2-(carboxylatomethyl)-4-hydroxy-4-oxobutanamidinium'),
    ('an isophthalate on a benzamidinium', 'NC(=[NH2+])c1cc(C(=O)[O-])cc(C(=O)O)c1', '3-carboxylato-5-carboxybenzamidinium'),
    ('an ortho carboxylate on a benzamidinium', 'NC(=[NH2+])c1ccc(C(=O)O)cc1C(=O)[O-]', '2-carboxylato-4-carboxybenzamidinium'),
]

ALL = CAMPTOTHECIN + KETONE_CATION_UNCHANGED + SECOND_ACID


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_the_cation_suffix_comes_before_a_curated_ketone_suffix():
    for _label, _smiles, expected in CAMPTOTHECIN:
        assert "-6-ium-3,14(4H)-dione" in expected and "dion-6-ium" not in expected, expected


def test_a_carboxylate_beside_a_neutral_acid_is_cited_once_as_carboxylato():
    for _label, smiles, expected in SECOND_ACID:
        assert expected.count("carboxylato") == 1, expected
        assert "methoxy" not in expected, expected


def test_a_carboxylate_beside_two_neutral_acids_is_still_refused_not_named_wrongly():
    with pytest.raises(ValueError):
        name_smiles("NC(=[NH2+])C(C(=O)O)(C(=O)O)C(=O)[O-]")  # round 49 names the quaternary carbon with two acids; three acids is still refused


@needs_opsin
def test_the_census_read_back_tries_the_respellings_opsin_reads():
    import naming_census_scan as scan

    names = ["N1,N2-bis(cyanomethyl)oxamide", "ethanol"]
    back = scan.read_back(names)
    assert back[0], "the oxamide PIN is read through its respelling"
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back[0])) == Chem.MolToInchiKey(Chem.MolFromSmiles("N#CCNC(=O)C(=O)NCC#N"))
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back[1])) == Chem.MolToInchiKey(Chem.MolFromSmiles("CCO"))
