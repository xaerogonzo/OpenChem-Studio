from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QUndoStack

from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected
from openchem.ui.panels.project_explorer_panel import ProjectExplorerPanel


def _panel_with_project(qapp) -> tuple[ProjectExplorerPanel, ProjectModel, QUndoStack]:
    bus = EventBus()
    undo_stack = QUndoStack()
    panel = ProjectExplorerPanel(bus, undo_stack)
    project = ProjectModel(molecules=[MoleculeModel(display_name="Codeine")])
    panel.set_project(project)
    return panel, project, undo_stack


def test_delete_via_shortcut_removes_the_molecule_and_is_undoable(qapp):
    panel, project, undo_stack = _panel_with_project(qapp)
    molecule = project.molecules[0]
    panel._list.setCurrentRow(0)

    panel._delete_selected()

    assert project.find_molecule(molecule.uuid) is None
    assert panel._list.count() == 0

    undo_stack.undo()

    assert project.find_molecule(molecule.uuid) is molecule
    assert panel._list.count() == 1


def test_delete_with_no_selection_is_a_no_op(qapp):
    bus = EventBus()
    undo_stack = QUndoStack()
    panel = ProjectExplorerPanel(bus, undo_stack)
    panel.set_project(ProjectModel())

    panel._delete_selected()  # must not raise

    assert undo_stack.count() == 0


def test_rename_via_item_edit_updates_display_name_and_is_undoable(qapp):
    panel, project, undo_stack = _panel_with_project(qapp)
    molecule = project.molecules[0]
    item = panel._list.item(0)

    item.setText("Renamed molecule")

    assert molecule.display_name == "Renamed molecule"

    undo_stack.undo()

    assert molecule.display_name == "Codeine"
    assert panel._list.item(0).text() == "Codeine"


def test_rename_to_the_same_or_empty_name_pushes_no_command(qapp):
    panel, project, undo_stack = _panel_with_project(qapp)
    item = panel._list.item(0)

    item.setText("Codeine")  # unchanged
    assert undo_stack.count() == 0

    item.setText("   ")  # blank after strip
    assert undo_stack.count() == 0
    assert panel._list.item(0).text() == "Codeine"  # restored, not left blank


def test_selecting_an_item_still_publishes_molecule_selected(qapp):
    bus = EventBus()
    undo_stack = QUndoStack()
    panel = ProjectExplorerPanel(bus, undo_stack)
    molecule = MoleculeModel(display_name="Aspirin")
    project = ProjectModel(molecules=[molecule])
    panel.set_project(project)

    selected: list[str | None] = []
    bus.subscribe(MoleculeSelected, lambda e: selected.append(e.molecule_uuid))

    panel._list.setCurrentRow(0)

    assert selected == [molecule.uuid]
