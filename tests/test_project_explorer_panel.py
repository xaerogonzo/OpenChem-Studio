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


# --- Copying identifiers --------------------------------------------------


def test_copy_smiles_puts_the_structure_on_the_clipboard(qapp):
    """The direct ask. Right-click a molecule, get its SMILES."""
    from PySide6.QtGui import QGuiApplication
    from rdkit import Chem

    panel = ProjectExplorerPanel(EventBus(), QUndoStack())
    molecule = MoleculeModel(display_name="aspirin")
    molecule.molblock = Chem.MolToMolBlock(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    panel.set_project(ProjectModel(molecules=[molecule]))

    QGuiApplication.clipboard().setText("")
    panel._copy_identifier(panel._list.item(0), "smiles")

    pasted = QGuiApplication.clipboard().text()
    assert Chem.MolFromSmiles(pasted) is not None
    assert Chem.MolToSmiles(Chem.MolFromSmiles(pasted)) == Chem.MolToSmiles(
        Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
    )


def test_copying_a_molecule_with_no_structure_leaves_the_clipboard_alone(qapp):
    """Better than clearing it: someone who copied something else and
    then right-clicked an empty molecule should not lose it."""
    from PySide6.QtGui import QGuiApplication

    panel = ProjectExplorerPanel(EventBus(), QUndoStack())
    panel.set_project(ProjectModel(molecules=[MoleculeModel(display_name="empty")]))

    QGuiApplication.clipboard().setText("something the user already had")
    panel._copy_identifier(panel._list.item(0), "smiles")

    assert QGuiApplication.clipboard().text() == "something the user already had"
