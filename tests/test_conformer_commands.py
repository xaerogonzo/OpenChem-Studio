from __future__ import annotations

from PySide6.QtGui import QUndoStack

from openchem.commands.conformer_commands import SetConformersCommand
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformersChanged


def test_set_conformers_undo_redo(qapp):
    bus = EventBus()
    molecule = MoleculeModel(display_name="Test")
    stack = QUndoStack()

    events = []
    bus.subscribe(ConformersChanged, lambda e: events.append(e.molecule_uuid))

    new_conformers = [ConformerModel(molblock="mock-1"), ConformerModel(molblock="mock-2")]
    stack.push(SetConformersCommand(molecule, new_conformers, bus))

    assert molecule.conformers == new_conformers
    assert events == [molecule.uuid]

    stack.undo()
    assert molecule.conformers == []

    stack.redo()
    assert molecule.conformers == new_conformers


def test_set_conformers_undo_restores_previous_set(qapp):
    bus = EventBus()
    original = [ConformerModel(molblock="original")]
    molecule = MoleculeModel(display_name="Test", conformers=list(original))
    stack = QUndoStack()

    replacement = [ConformerModel(molblock="replacement")]
    stack.push(SetConformersCommand(molecule, replacement, bus))
    assert molecule.conformers == replacement

    stack.undo()
    assert molecule.conformers == original
