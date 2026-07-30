from __future__ import annotations

from PySide6.QtGui import QUndoStack

from openchem.commands.macromolecule_commands import AddMacromoleculeCommand
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.project import ProjectModel


def test_add_macromolecule_undo_redo(qapp):
    project = ProjectModel()
    macromolecule = MacromoleculeModel(display_name="Test structure", structure_text="ATOM ...")
    stack = QUndoStack()

    stack.push(AddMacromoleculeCommand(project, macromolecule))
    assert macromolecule in project.macromolecules
    assert len(project.history) == 1

    stack.undo()
    assert macromolecule not in project.macromolecules

    stack.redo()
    assert macromolecule in project.macromolecules
