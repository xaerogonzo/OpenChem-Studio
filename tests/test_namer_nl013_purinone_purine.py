"""NL-013 (WS2): purinone + purine, ``3H-purin-3-yl`` arm reads back; ``1H`` arm not in round-81 data."""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# Matrix / NAMING_COVERAGE_MATRIX.md: fused hypoxanthine-purine 6-one, two ring N-H (tautomer as drawn).
SMILES = "O=c1[nH]cnc2[nH]c(-n3cncc4ncnc3-4)nc12"
EXPECTED_NAME = "8-(3H-purin-3-yl)-1,9-dihydro-6H-purin-6-one"
EXPECTED_FULL_INCHIKEY = "ATROGWFAUZSSNI-UHFFFAOYSA-N"


def test_nl013_purinone_purine_expected_name():
    assert name_smiles(SMILES) == EXPECTED_NAME


@needs_opsin
def test_nl013_purinone_purine_opsin_read_back_full_key():
    from py2opsin import py2opsin

    assert name_smiles(SMILES) == EXPECTED_NAME
    back = py2opsin(EXPECTED_NAME)
    assert back, EXPECTED_NAME
    want = inchi.MolToInchiKey(Chem.MolFromSmiles(SMILES))
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == want
    assert want == EXPECTED_FULL_INCHIKEY
