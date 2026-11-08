"""NL-097 (WS2): ownership audit scope — five matrix drawings name correctly but strict audit is substitutive-only."""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles, ownership

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# Matrix run 2026-11-03 (`docs/NAMING_COVERAGE_MATRIX.md` § NL-097).
CASES = (
    ("carbamimidoyl chain", "NC(=N)CCCC(=O)O", "5-amino-5-iminopentanoic acid", "MKXDCLLPQDWCDQ-UHFFFAOYSA-N"),
    ("functional class", "CC(=O)OC", "methyl acetate", "KXKVLQRXCPHEJC-UHFFFAOYSA-N"),
    ("multiplicative", "ClCCOCCCl", "1-chloro-2-(2-chloroethoxy)ethane", "ZNSMNVMLTJELDZ-UHFFFAOYSA-N"),
    ("ring assembly", "c1ccc(-c2ccccc2)cc1", "1,1'-biphenyl", "ZUOUZKKEUPVFJK-UHFFFAOYSA-N"),
    ("additive salt", "[Na+].CC(=O)[O-]", "sodium acetate", "VMHLLURERBWHNL-UHFFFAOYSA-M"),
)


@pytest.fixture
def record_ownership(monkeypatch):
    monkeypatch.setenv("OPENCHEM_NAMER_OWNERSHIP", "record")
    ownership.RECORDED.clear()
    yield
    ownership.RECORDED.clear()


@pytest.mark.parametrize("label,smiles,expected_name,expected_key", CASES, ids=[c[0] for c in CASES])
def test_nl097_names_match_matrix(label, smiles, expected_name, expected_key):
    del label
    assert name_smiles(smiles) == expected_name
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(smiles)) == expected_key


@pytest.mark.parametrize("label,smiles,expected_name,expected_key", CASES, ids=[c[0] for c in CASES])
def test_nl097_record_mode_writes_no_ownership_diagnostic(
    record_ownership, label, smiles, expected_name, expected_key,
):
    del label, expected_name, expected_key
    before = len(ownership.RECORDED)
    name_smiles(smiles)
    assert len(ownership.RECORDED) == before, (
        "substitutive-only audit: see `KNOWN_LIMITATIONS.md` audit-reach row (round 5 N2)"
    )


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected_name,expected_key", CASES, ids=[c[0] for c in CASES])
def test_nl097_opsin_read_back(label, smiles, expected_name, expected_key):
    del label
    from py2opsin import py2opsin

    assert name_smiles(smiles) == expected_name
    back = py2opsin(expected_name)
    assert back
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == expected_key
