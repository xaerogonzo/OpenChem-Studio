"""Naming round 94 (NL-011 bucket C): N-methyl on the tropane partner inside dispiro.

Seed 8901 chain #13: the methyl must appear on the ``8-azabicyclo[3.2.1]octane``
partner citation inside ``dispiro[...]``, not as a ``1-methyldispiro[...]`` prefix
on the whole name.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

SMILES = "CN1C2CCC1CC1(C2)C2CC3CC(C2)C2(C4CCC2C4)C1CN3"
EXPECTED = (
    "dispiro[bicyclo[2.1.1]hexane-5,10'-4-azatricyclo[4.3.1.1^{3,8}]undecane-7',"
    "3''-8-methyl-8-azabicyclo[3.2.1]octane]"
)


def test_nl011_seed8901_chain13_methyl_on_tropane_partner():
    got = name_smiles(SMILES)
    assert got == EXPECTED
    assert not got.startswith("1-methyl")


@needs_opsin
@pytest.mark.xfail(
    strict=True,
    reason="OPSIN 2.9.0 unparsable on methyl cited inside dispiro partner (NL-011 bucket B probe)",
)
def test_nl011_seed8901_chain13_opsin_read_back():
    from py2opsin import py2opsin

    assert name_smiles(SMILES) == EXPECTED
    back = py2opsin(EXPECTED)
    assert back, EXPECTED
    want = inchi.MolToInchiKey(Chem.MolFromSmiles(SMILES))
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == want
