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


def _ethanol_molblock() -> str:
    """Ethanol as the 2D editor holds it: three heavy atoms, hydrogens
    implicit. The molecule the crash below was measured on."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles("CCO")
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


def test_render_2d_svg_ignores_out_of_range_atom_indices():
    """An out-of-range highlight index used to lose the WHOLE depiction.

    `atom_colors` went to `PrepareAndDrawMolecule(highlightAtoms=...)`
    unguarded while `atom_labels` was already range-checked, so a single
    surplus index raised `ValueError: list element larger than allowed
    value` and nothing rendered at all.

    Equality against the in-range-only rendering is the assertion, rather
    than "no exception": it pins down that the surplus indices are dropped
    and the legitimate ones still take effect, which "it didn't crash"
    would also pass if the guard threw the highlights away entirely.
    """
    engine = ChemistryEngine()
    molblock = _ethanol_molblock()  # 3 atoms, valid indices 0-2

    plain = engine.render_2d_svg(molblock)
    in_range_only = engine.render_2d_svg(molblock, {1: "#ff0000"}, {1: "1.23"})
    with_surplus = engine.render_2d_svg(
        molblock,
        {1: "#ff0000", 8: "#00ff00", -1: "#0000ff"},
        {1: "1.23", 8: "9.99", -1: "0.00"},
    )

    assert with_surplus == in_range_only
    assert in_range_only != plain  # the in-range highlight/label did land


def test_render_2d_svg_survives_a_hydrogen_bearing_calculator_result():
    """The real path this guard exists for, end to end.

    `compute_atomic_polarizability` runs on `Chem.AddHs(mol)` and returns a
    value for every hydrogen -- measured: 9 values for ethanol's 3 drawable
    atoms -- and the Calculator Inspector feeds that dataset's layer
    straight into `render_2d_svg` alongside the editor molblock. Built from
    the live calculator rather than a hand-written dict so the test fails if
    that producer's index space ever changes.
    """
    from rdkit import Chem

    from openchem.chem.electronic_properties import compute_atomic_polarizability
    from openchem.ui.visualization import build_visualization_layer

    engine = ChemistryEngine()
    molblock = _ethanol_molblock()
    dataset = compute_atomic_polarizability(
        Chem.MolFromMolBlock(molblock, removeHs=False), "uuid", {}
    )
    assert max(dataset.values) >= 3  # the overrun is real, not assumed

    layer = build_visualization_layer(dataset, include_labels=True)
    svg = engine.render_2d_svg(molblock, layer.atom_colors, layer.atom_labels)

    assert svg.startswith("<?xml")
