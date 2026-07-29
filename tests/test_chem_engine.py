from __future__ import annotations

import pytest

from openchem.chem.engine import ChemistryEngine, InvalidStructureError
from openchem.domain.molecule import MoleculeModel


def test_set_structure_from_smiles_canonicalizes():
    engine = ChemistryEngine()
    model = MoleculeModel()

    engine.set_structure_from_smiles(model, "C1=CC=CC=C1")

    assert model.canonical_smiles == "c1ccccc1"
    assert model.inchikey == "UHOVQNZJYSORNB-UHFFFAOYSA-N"
    assert model.molblock is not None


def test_molblock_roundtrip_preserves_identity():
    engine = ChemistryEngine()
    original = MoleculeModel()
    engine.set_structure_from_smiles(original, "CCO")

    reloaded = MoleculeModel()
    engine.set_structure_from_molblock(reloaded, original.molblock)

    assert reloaded.canonical_smiles == original.canonical_smiles
    assert reloaded.inchikey == original.inchikey


def test_invalid_smiles_raises():
    engine = ChemistryEngine()
    model = MoleculeModel()

    with pytest.raises(InvalidStructureError):
        engine.set_structure_from_smiles(model, "not a smiles!!")


def test_mol_from_model_without_molblock_raises():
    engine = ChemistryEngine()
    model = MoleculeModel()

    with pytest.raises(InvalidStructureError):
        engine.mol_from_model(model)
