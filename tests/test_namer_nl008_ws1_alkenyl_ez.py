"""NL-008 (WS1): E/Z on a methyl-branched alkenyl substituent — re-measured 2026-11-10.

Round 44 (D-231) fixed the carve path so ``N-(2-methylbut-2-en-1-yl)acetamide`` no longer
collides between stereoisomers. Pins are in ``tests/test_namer_round44_parent_anion_and_stereo.py``;
this module records the programme closure for NL-008.
"""

from __future__ import annotations

import shutil

import pytest

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

CASES = [
    ("E", "C/C=C(C)/CNC(=O)C", "N-[(2E)-2-methylbut-2-en-1-yl]acetamide"),
    ("Z", "C/C=C(/C)CNC(=O)C", "N-[(2Z)-2-methylbut-2-en-1-yl]acetamide"),
]


@pytest.mark.parametrize("which,smiles,expected", CASES, ids=[c[0] for c in CASES])
def test_nl008_distinct_e_and_z_names(which, smiles, expected):
    del which
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("which,smiles,expected", CASES, ids=[c[0] for c in CASES])
def test_nl008_opsin_read_back_pins_each_isomer(which, smiles, expected):
    del which, expected
    from py2opsin import py2opsin
    from rdkit import Chem
    from rdkit.Chem import inchi

    back = py2opsin(name_smiles(smiles))
    assert back
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))
