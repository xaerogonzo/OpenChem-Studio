"""tools/naming_app_check.py: the release-candidate driven check's table stays honest (naming round 8). The check itself needs a JRE and is run by hand at the
round's end; this keeps its ROWS from rotting between rounds."""

from __future__ import annotations

import sys
from pathlib import Path

from rdkit import Chem

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_app_check as check  # noqa: E402


def test_every_row_states_the_structure_it_is_about():
    for label, smiles, _name, _basis, _verdict, charge, components in check.ROWS:
        mol = Chem.MolFromSmiles(smiles)
        assert mol is not None, label
        assert Chem.GetFormalCharge(mol) == charge, f"{label}: charge"
        assert len(Chem.GetMolFrags(mol)) == components, f"{label}: components"


def test_the_rows_are_distinct_and_carry_a_basis():
    assert len({row[1] for row in check.ROWS}) == len(check.ROWS), "a structure is listed twice"
    assert all(row[3].strip() for row in check.ROWS), "a row with no basis for its name"
    assert {row[4] for row in check.ROWS} <= {"MATCH", "TAUTOMER"}
