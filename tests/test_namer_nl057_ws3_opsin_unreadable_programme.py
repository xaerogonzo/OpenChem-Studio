"""NL-057 (WS3): names the engine may emit as the book prints them but OPSIN cannot parse as written.

The application respells several for read-back verification (`opsin_readable_spellings`, round 41/45).
Census and benchmark scans still treat the engine form as unparsable without respelling.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.chem.naming_providers import RoundTrip, opsin_readable_spellings, verify_name_round_trip
from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN)")

CAMPTOTHECIN_PROTONATED = (
    "CCC1(O)C(=O)OCc2c1cc1n(c2=O)Cc2cc3ccccc3[nH+]c2-1",
    "4-ethyl-4-hydroxy-1,12-dihydro-14H-pyrano[3',4':6,7]indolizino[1,2-b]quinolin-6-ium-3,14(4H)-dione",
)

OXAMIDE_SMILES = "N#CCNC(=O)C(=O)NCC#N"
OXAMIDE_ENGINE = "N1,N2-bis(cyanomethyl)oxamide"


def test_nl057_engine_emits_book_oxamide_pin():
    assert name_smiles(OXAMIDE_SMILES) == OXAMIDE_ENGINE


@pytest.mark.parametrize(
    "written,readable",
    [
        ("N1-benzyl-N2-phenyloxamide", "N1-benzyl-N2-phenylethanediamide"),
        ("(oxobis{[a]oxy}phosphanyl)benzene", "(bis{[a]oxy}(oxo)phosphanyl)benzene"),
        ("2H-bis([1,3]dioxolo)[4,5-b:4',5'-d]pyran", "2H-bis[1,3]dioxolo[4,5-b:4',5'-d]pyran"),
    ],
)
def test_nl057_respelling_maps_opsin_unreadable_to_readable(written, readable):
    assert opsin_readable_spellings(written)[1] == readable


@needs_opsin
def test_nl057_app_verifies_oxamide_through_respelling():
    mol = Chem.MolFromSmiles("Cc1c(Cl)cccc1NC(=O)C(=O)NCc1ccccc1")
    assert verify_name_round_trip("N1-benzyl-N2-(3-chloro-2-methylphenyl)oxamide", mol) == RoundTrip.MATCH


def test_nl057_camptothecin_cation_uses_readable_suffix_order():
    smiles, expected = CAMPTOTHECIN_PROTONATED
    assert name_smiles(smiles) == expected