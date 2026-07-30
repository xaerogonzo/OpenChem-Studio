from __future__ import annotations

from PySide6.QtGui import QUndoStack

from openchem.chem.engine import ChemistryEngine
from openchem.commands.molecule_commands import AddMoleculeCommand, EditStructureCommand
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import ConformersChanged, ConformersInvalidated, MoleculeChanged


def test_add_molecule_undo_redo(qapp):
    bus = EventBus()
    project = ProjectModel()
    molecule = MoleculeModel(display_name="Test")
    stack = QUndoStack()

    events = []
    bus.subscribe(MoleculeChanged, lambda e: events.append(e.molecule_uuid))

    stack.push(AddMoleculeCommand(project, molecule, bus))
    assert molecule in project.molecules
    assert events == [molecule.uuid]

    stack.undo()
    assert molecule not in project.molecules

    stack.redo()
    assert molecule in project.molecules


def test_edit_structure_undo_redo(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Test")
    stack = QUndoStack()

    scratch = MoleculeModel()
    engine.set_structure_from_smiles(scratch, "CCO")
    ethanol_molblock = scratch.molblock

    events = []
    bus.subscribe(MoleculeChanged, lambda e: events.append(e.molecule_uuid))

    stack.push(EditStructureCommand(engine, molecule, ethanol_molblock, bus))
    assert molecule.canonical_smiles == scratch.canonical_smiles
    assert events == [molecule.uuid]

    stack.undo()
    assert molecule.molblock is None
    assert molecule.canonical_smiles is None

    stack.redo()
    assert molecule.canonical_smiles == scratch.canonical_smiles


def test_edit_structure_invalidates_conformers(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Test")
    engine.set_structure_from_smiles(molecule, "CCO")
    old_conformer = ConformerModel(molblock="old", energy=1.0, method="rdkit")
    molecule.conformers = [old_conformer]
    stack = QUndoStack()

    scratch = MoleculeModel()
    engine.set_structure_from_smiles(scratch, "CCC")
    new_molblock = scratch.molblock

    invalidated = []
    changed = []
    bus.subscribe(ConformersInvalidated, lambda e: invalidated.append(e.molecule_uuid))
    bus.subscribe(ConformersChanged, lambda e: changed.append(e.molecule_uuid))

    stack.push(EditStructureCommand(engine, molecule, new_molblock, bus))
    assert molecule.conformers == []
    assert invalidated == [molecule.uuid]
    assert changed == [molecule.uuid]

    stack.undo()
    assert molecule.conformers == [old_conformer]
    assert changed == [molecule.uuid, molecule.uuid]
    # Undo restores, it doesn't invalidate.
    assert invalidated == [molecule.uuid]
