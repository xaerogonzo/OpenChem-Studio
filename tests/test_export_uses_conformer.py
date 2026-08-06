"""Exporting must write the computed 3D geometry, and undo must restore position.

Two defects found by exercising basic functions rather than features.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.engine import ChemistryEngine
from openchem.commands.molecule_commands import DeleteMoleculeCommand
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.services.export_service import ExportService
from openchem.services.import_service import ImportService

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


@pytest.fixture
def engine():
    return ChemistryEngine()


def _aspirin(engine, *, with_conformer: bool) -> MoleculeModel:
    model = MoleculeModel(display_name="Aspirin")
    engine.set_structure_from_smiles(model, ASPIRIN)
    if with_conformer:
        mol = Chem.AddHs(Chem.MolFromSmiles(ASPIRIN))
        AllChem.EmbedMolecule(mol, randomSeed=3)
        AllChem.MMFFOptimizeMolecule(mol)
        model.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol), energy=0.0))
    return model


def _z_coordinates(xyz_text: str) -> list[float]:
    return [
        float(line.split()[3])
        for line in xyz_text.splitlines()[2:]
        if len(line.split()) == 4
    ]


def test_xyz_export_writes_the_conformers_real_coordinates(engine, tmp_path):
    """`.xyz` exists to carry 3D coordinates into another program.

    The exporters built from `MoleculeModel.molblock`, which is the 2D
    structure the editor drew, so this wrote a planar molecule -- measured:
    all 13 atoms of aspirin at z = 0.0 -- even with an MMFF-optimised
    conformer sitting on the model.
    """
    model = _aspirin(engine, with_conformer=True)
    path = tmp_path / "aspirin.xyz"

    ExportService(engine).export_file(model, path)

    z_values = _z_coordinates(path.read_text(encoding="utf-8"))
    assert any(z != 0.0 for z in z_values), "exported a flat molecule as a 3D format"


def test_xyz_export_includes_explicit_hydrogens(engine, tmp_path):
    """Falls out of using the conformer, and matters on its own.

    Conformers are embedded after `AddHs`, so the file has aspirin's 21
    atoms rather than its 13 heavy ones -- which is what any downstream QM
    or docking tool needs.
    """
    model = _aspirin(engine, with_conformer=True)
    path = tmp_path / "aspirin.xyz"

    ExportService(engine).export_file(model, path)

    assert len(_z_coordinates(path.read_text(encoding="utf-8"))) == 21


@pytest.mark.parametrize("fmt", ["xyz", "pdb", "mol", "sdf"])
def test_the_exported_structure_survives_a_round_trip(engine, tmp_path, fmt):
    """Hydrogens are collapsed before comparing: an explicit-H SMILES is a
    different STRING for the same molecule, and the question here is
    whether the structure survived, not how it was written."""
    model = _aspirin(engine, with_conformer=True)
    path = tmp_path / f"aspirin.{fmt}"
    ExportService(engine).export_file(model, path)

    reimported = ImportService(engine).import_file(path)
    assert reimported
    mol = Chem.MolFromSmiles(reimported[0].canonical_smiles)
    assert Chem.MolToSmiles(Chem.RemoveHs(mol)) == model.canonical_smiles


def test_a_molecule_with_no_conformer_still_exports(engine, tmp_path):
    """No 3D data to write is not a reason to refuse.

    The file is planar, which is inherent rather than a defect -- there is
    no geometry to put in it. Generating one silently would be a surprising
    side effect of pressing Export.
    """
    model = _aspirin(engine, with_conformer=False)
    path = tmp_path / "flat.xyz"

    ExportService(engine).export_file(model, path)

    assert path.is_file() and path.stat().st_size > 0


def test_undoing_a_delete_restores_the_molecules_position():
    """Undo has to be a true inverse.

    `undo` appended, so deleting a molecule from the middle of a project
    and pressing Ctrl+Z moved it to the bottom of the Project Explorer --
    and reordered every saved file and batch table built from it.
    """
    project = ProjectModel(name="p")
    for name in "ABCD":
        project.molecules.append(MoleculeModel(display_name=name))
    original = [m.display_name for m in project.molecules]
    command = DeleteMoleculeCommand(project, project.molecules[1], EventBus())

    command.redo()
    assert [m.display_name for m in project.molecules] == ["A", "C", "D"]
    command.undo()

    assert [m.display_name for m in project.molecules] == original


def test_position_survives_repeated_undo_and_redo():
    """The index is captured on every redo, not once at construction, so a
    command cycled several times keeps restoring to the right place."""
    project = ProjectModel(name="p")
    for name in "ABCD":
        project.molecules.append(MoleculeModel(display_name=name))
    original = [m.display_name for m in project.molecules]
    command = DeleteMoleculeCommand(project, project.molecules[2], EventBus())

    for _ in range(3):
        command.redo()
        command.undo()

    assert [m.display_name for m in project.molecules] == original
