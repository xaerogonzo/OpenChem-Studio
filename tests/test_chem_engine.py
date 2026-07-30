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


def test_mol_from_molblock_preserves_explicit_hydrogen_positions():
    """Regression test: confirmed live against a real ORCA install that
    RDKit's Chem.MolFromMolBlock defaults to removeHs=True, which folds
    every explicit hydrogen into implicit H-count on its neighbor -- correct
    for the molecular formula, but it silently discards that hydrogen's own
    3D position. A conformer molblock built via Chem.AddHs() + embedding
    (RDKitConformerProvider's normal path for real 3D geometry) round-
    tripped through the old default came back as a bare heavy-atom-only mol
    with NO hydrogen atoms at all -- for water, an oxygen atom instead of
    H2O -- which OrcaQuantumEngineProvider then silently sent to ORCA as-is,
    computing the wrong molecule's energy instead of failing loudly.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol_3d = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=42)
    molblock = Chem.MolToMolBlock(mol_3d)

    engine = ChemistryEngine()
    roundtripped = engine.mol_from_molblock(molblock)

    assert roundtripped.GetNumAtoms() == 3  # O + 2 H, not just O
    symbols = sorted(atom.GetSymbol() for atom in roundtripped.GetAtoms())
    assert symbols == ["H", "H", "O"]
