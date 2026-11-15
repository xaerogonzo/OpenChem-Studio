import json

import pytest
from rdkit import Chem

from openchem.chem import ionic_species
from openchem.chem.ionic_species import load_ionic_species, row_by_id
from openchem.chem.salt_components import fragment_formal_charge, fragment_key


def test_hydrogen_sulfate_and_sulfate_are_different_rows() -> None:
    hso4 = row_by_id("hydrogen_sulfate")
    so4 = row_by_id("sulfate")
    assert hso4 is not None and so4 is not None
    assert hso4.ion_smiles != so4.ion_smiles
    assert hso4.charge == -1
    assert so4.charge == -2


def test_every_row_round_trips_to_its_charge_and_key() -> None:
    for row in load_ionic_species():
        mol = Chem.MolFromSmiles(row.ion_smiles)
        assert mol is not None, row.ion_id
        assert fragment_formal_charge(mol) == row.charge, row.ion_id
        assert fragment_key(mol) == row.ion_smiles, row.ion_id


def test_catalog_is_not_a_pharma_whitelist() -> None:
    ids = {row.ion_id for row in load_ionic_species()}
    assert "chloride" in ids
    # An unusual ion is simply absent, not forbidden.
    assert row_by_id("hexafluorophosphate") is None


def test_load_refuses_a_charge_that_disagrees_with_the_graph(tmp_path, monkeypatch) -> None:
    payload = json.loads(ionic_species._catalog_path().read_text(encoding="utf-8"))
    for ion in payload["ions"]:
        if ion["id"] == "chloride":
            ion["charge"] = 0
    path = tmp_path / "ionic_species.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(ionic_species, "_catalog_path", lambda: path)
    with pytest.raises(ValueError, match="chloride"):
        load_ionic_species()
