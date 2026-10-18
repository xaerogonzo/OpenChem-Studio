"""Naming round 63 (D-299 .. D-302): a guanidinium, an amidinium or a carbon acid beside another charge.

Round 62 left about 50 refusals per pair mode. Their biggest share was three classifiers that claim a motif only when it is the molecule's ONLY charge, so any second charge made detection
refuse the whole molecule ('partial_claim'): arginine drawn as the zwitterion (a guanidinium, an ammonium and a carboxylate) was refused.

D-299: a guanidinium beside another charge declines the classifier and the plan search names it, the group a `(diaminomethylidene)azaniumyl` prefix: `(2S)-2-azaniumyl-5-[(diaminomethylidene)azaniumyl]pentanoate`.
D-300: an amidinium beside another charge declines the same way (the lone carboxylate of round 43 stays its own case), and its `=[NH2+]` is `azaniumylidene` where the neutral `imino` lost the cation.
D-301: an O-protonated amide on a RING nitrogen was cited as the neutral `morpholine-4-carbonyl`: `(morpholin-4-yl)(oxidaniumylidene)methyl`.
D-302: a carbon acid (a 1,3-dicarbonyl carbanion) beside a cation was refused in every case (57 of 57 in the zwitterion population); the cations ride in the claim and are prefixes: `6-azaniumyl-2,4-dioxohexan-3-ide`.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import naming_ion_populations as pop  # noqa: E402

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NAMED = [
    ("arginine as the zwitterion", "NC(N)=[NH+]CCC[C@H]([NH3+])C(=O)[O-]", "(2S)-2-azaniumyl-5-[(diaminomethylidene)azaniumyl]pentanoate"),
    ("a guanidinium beside a protonated amide", "NC(N)=[NH+]CCCC(=[OH+])N", "(4-amino-4-oxidaniumylidenebutyl)(diaminomethylidene)azanium"),
    ("an amidinium beside an ammonium", "NC(=[NH2+])c1ccccc1C[NH3+]", "{2-[amino(azaniumylidene)methyl]phenyl}methanaminium"),
    ("a protonated amide on a pyrrolidine nitrogen beside a quinolinium", "COc1ccc(-c2cc(C(=[OH+])N3CCCC3)c3ccccc3[nH+]2)c(OC)c1",
     "2-(2,4-dimethoxyphenyl)-4-[(oxidaniumylidene)(pyrrolidin-1-yl)methyl]quinolin-1-ium"),
    ("a diketone carbanion beside an ammonium", "CC(=O)[CH-]C(=O)CC[NH3+]", "6-azaniumyl-2,4-dioxohexan-3-ide"),
    ("a ring dione carbanion beside an ammonium", "O=C1[CH-]C(=O)NCC1[NH3+]", "5-azaniumyl-2,4-dioxopiperidin-3-ide"),
]

KEPT = [
    ("a lone guanidinium", "NC(=[NH2+])N", "guanidinium"),
    ("a substituted guanidinium", "NC(N)=[NH+]CCCC", "butylguanidinium"),
    ("an amidinium with its carboxylate", "NC(=[NH2+])CC(=O)[O-]", "carboxylatoacetamidinium"),
    ("a lone diketone carbanion", "CC(=O)[CH-]C(=O)C", "2,4-dioxopentan-3-ide"),
    ("a neutral ring-nitrogen amide keeps its carbonyl", "O=C(N1CCOCC1)c1ccc(C[NH3+])cc1", "[4-(morpholine-4-carbonyl)phenyl]methanaminium"),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_ion(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.GetFormalCharge(Chem.MolFromSmiles(back)) == Chem.GetFormalCharge(Chem.MolFromSmiles(smiles)), (expected, back)
    assert pop._inchikey(back, neutral=True) == pop._inchikey(smiles, neutral=True), (expected, back)


def test_a_second_anion_beside_a_carbon_acid_is_still_not_this_classifier_s():
    # only CATIONS ride along; a carbanion beside another anion keeps the route it had (no claim here, so a visible refusal or the other classifier's name)
    from openchem.vendor.iupac_namer.perception.charge_perception import _classify_stabilised_carbanion

    assert list(_classify_stabilised_carbanion(Chem.MolFromSmiles("CC(=O)[CH-]C(=O)CC(=O)[O-]"))) == []
