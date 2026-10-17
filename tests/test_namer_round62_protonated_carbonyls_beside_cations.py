"""Naming round 62 (D-295 .. D-298): an O- or S-protonated carbonyl beside another cation is cited as what it is.

Round 61 ended with the largest class of refusals the pair populations had: 786 of 1930 dications, most of them an O-protonated amide, ester, acid or ketone beside a second cation. The
engine named the carbonyl with the NEUTRAL prefix (`oxo`, `ethoxycarbonyl`, `carboxy`, `carbamoyl`), and the guard refused the name for the cation it had lost; an after-the-fact
restore (round 59) swapped one `oxo` of the NAME for `oxidaniumylidene`, which only worked when the name had exactly one `oxo` and gave the charge to the wrong carbonyl when it did not (D-294).

D-295: the unclaimed-`=O` fallback names the atom it has: `=[OH+]` is `oxidaniumylidene`, `=[SH+]` `sulfaniumylidene`, at the place it stands. 1143 of the dications were named, now 1877.
D-296: an O-protonated ESTER carbonyl is no `alkoxycarbonyl` (the neutral group's prefix): `[ethoxy(oxidaniumylidene)methyl]`.
D-297: the prefix is bracketed on a one-carbon parent in any output form (`(2-azanidylphenyl)(oxidaniumylidene)methanamine`; unbracketed OPSIN reads it as something else).
D-298: a MULTIPLIED one is `bis(oxidaniumylidene)`: OPSIN cannot read `2,3-dioxidaniumylidene`.
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
    ("a protonated amide beside an ammonium", "CC(=[OH+])NCC[NH3+]", "2-[(1-oxidaniumylideneethyl)amino]ethan-1-aminium"),
    ("a protonated thioamide beside an ammonium", "CC(=[SH+])NCC[NH3+]", "2-[(1-sulfaniumylideneethyl)amino]ethan-1-aminium"),
    ("a protonated ester beside an anilinium", "CCOC(=[OH+])c1ccccc1[NH3+]", "2-[ethoxy(oxidaniumylidene)methyl]anilinium"),
    ("a protonated acid beside an ammonium", "OC(=[OH+])c1ccccc1C[NH3+]", "{2-[hydroxy(oxidaniumylidene)methyl]phenyl}methanaminium"),
    ("a protonated primary amide beside an anilide", "NC(=[OH+])c1ccccc1[NH-]", "(2-azanidylphenyl)(oxidaniumylidene)methanamine"),
    ("a protonated tertiary amide beside a piperazinium", "Cc1ccccc1C(=[OH+])N1CC[NH+](CC(=O)O)CC1",
     "1-(carboxymethyl)-4-[(2-methylphenyl)(oxidaniumylidene)methyl]piperazin-1-ium"),
    ("a protonated isatin", "CN(CC(O)C(O)C(O)C(O)CO)CN1C(=[OH+])C(=[OH+])c2ccccc21",
     "6-({[2,3-bis(oxidaniumylidene)-2,3-dihydro-1H-indol-1-yl]methyl}(methyl)amino)hexane-1,2,3,4,5-pentol"),
    ("three cations, one of them a protonated amide", "COc1ccc([C@@H]2C[C@H](C(F)(F)F)n3[nH+]cc(C(=[OH+])Nc4ccccc4SC)c3[NH2+]2)cc1",
     "(5S,7R)-5-(4-methoxyphenyl)-3-({[2-(methylsulfanyl)phenyl]amino}(oxidaniumylidene)methyl)-7-(trifluoromethyl)-4,5,6,7-tetrahydropyrazolo[1,5-a]pyrimidine-1,4-diium"),
]

KEPT = [
    ("a neutral ester keeps alkoxycarbonyl", "CCOC(=O)c1ccccc1C[NH3+]", "[2-(ethoxycarbonyl)phenyl]methanaminium"),
    ("a neutral amide keeps its oxo", "CC(=O)NCC[NH3+]", "2-acetamidoethan-1-aminium"),
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


def test_the_protonated_ester_beside_a_ketone_keeps_the_ketone_neutral():
    name = name_smiles("CCOC(=[OH+])c1[nH]c(C)c(C(=O)[C@@H]2C(=O)C(=O)N(CC[NH+](C)C)[C@@H]2c2ccc(C(C)C)cc2)c1C")
    assert "[ethoxy(oxidaniumylidene)methyl]" in name and "(oxo)methyl" in name
