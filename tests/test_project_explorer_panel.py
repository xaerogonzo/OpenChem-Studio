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


# --- crystals in the tree, and the molecule-only actions that must not fire --


def _panel_with_a_crystal(qapp):
    from openchem.domain.crystal import CrystalModel

    bus = EventBus()
    undo_stack = QUndoStack()
    panel = ProjectExplorerPanel(bus, undo_stack)
    project = ProjectModel(
        molecules=[MoleculeModel(display_name="Codeine")],
        crystals=[CrystalModel(display_name="Halite", cif_text="data_x")],
    )
    panel.set_project(project)
    return panel, project, undo_stack, bus


def test_a_crystal_appears_in_the_tree_and_is_labelled_as_one(qapp):
    """One flat list, so an unlabelled crystal row would read as a
    molecule -- and every molecule-only action would then look broken
    rather than inapplicable."""
    panel, project, _undo, _bus = _panel_with_a_crystal(qapp)

    assert panel._list.count() == 2
    labels = [panel._list.item(i).text() for i in range(panel._list.count())]
    assert labels[0] == "Codeine"
    assert "Halite" in labels[1] and "crystal" in labels[1]


def test_selecting_a_crystal_publishes_its_own_event(qapp):
    """**Not `MoleculeSelected` with a crystal uuid.** Every subscriber
    would look that up in `project.molecules`, find nothing, and leave
    its panel showing the previous molecule beside a crystal's name."""
    from openchem.events.events import CrystalSelected

    panel, project, _undo, bus = _panel_with_a_crystal(qapp)
    molecule_events: list[object] = []
    crystal_events: list[object] = []
    bus.subscribe(MoleculeSelected, molecule_events.append)
    bus.subscribe(CrystalSelected, crystal_events.append)

    panel._list.setCurrentRow(1)  # the crystal

    assert [e.crystal_uuid for e in crystal_events] == [project.crystals[0].uuid]
    assert all(e.molecule_uuid != project.crystals[0].uuid for e in molecule_events)


def test_a_crystal_row_can_be_renamed_through_its_own_command(qapp):
    """It could NOT be, until `RenameCrystalCommand` existed: rename went
    through `RenameMoleculeCommand`, which resolves its uuid against
    `project.molecules`, so an editable crystal row would either do
    nothing or rename an unrelated molecule. The flag was the guard; the
    command is the fix."""
    panel, project, undo, _bus = _panel_with_a_crystal(qapp)
    row = panel._list.item(1)
    assert row.flags() & Qt.ItemFlag.ItemIsEditable

    row.setText("Rock salt  [crystal]")

    assert project.crystals[0].display_name == "Rock salt"
    assert project.molecules[0].display_name == "Codeine"  # untouched
    undo.undo()
    assert project.crystals[0].display_name == "Halite"


def test_the_crystal_suffix_is_chrome_and_never_becomes_part_of_the_name(qapp):
    """The row reads "Halite  [crystal]" and editing hands that whole
    string back. Storing it would grow one suffix per rename."""
    panel, project, _undo, _bus = _panel_with_a_crystal(qapp)

    panel._list.item(1).setText("Rock salt  [crystal]")
    panel.refresh()
    panel._list.item(1).setText(panel._list.item(1).text())  # a no-op edit

    assert project.crystals[0].display_name == "Rock salt"


def test_deleting_a_crystal_removes_only_it_and_is_undoable(qapp):
    """Its own command, so the molecules are untouched -- and undo puts
    it back WHERE IT WAS, the lesson `DeleteMoleculeCommand` records."""
    from openchem.domain.crystal import CrystalModel

    panel, project, undo, _bus = _panel_with_a_crystal(qapp)
    project.crystals.insert(0, CrystalModel(display_name="Quartz", cif_text="data_q"))
    panel.refresh()
    panel._list.setCurrentRow(2)  # row 0 is the molecule, 1 Quartz, 2 Halite

    panel._delete_selected()

    assert [c.display_name for c in project.crystals] == ["Quartz"]
    assert len(project.molecules) == 1

    undo.undo()

    assert [c.display_name for c in project.crystals] == ["Quartz", "Halite"]


def test_undo_restores_a_crystal_to_its_ORIGINAL_position(qapp):
    """Undo has to be a true inverse. Appending would move a crystal
    deleted from the middle to the bottom, which is also a diff in every
    saved project file."""
    from openchem.domain.crystal import CrystalModel

    panel, project, undo, _bus = _panel_with_a_crystal(qapp)
    project.crystals[:] = [
        CrystalModel(display_name=name, cif_text="data_x")
        for name in ("First", "Middle", "Last")
    ]
    panel.refresh()
    panel._list.setCurrentRow(2)  # one molecule row, then "Middle"

    panel._delete_selected()
    undo.undo()

    assert [c.display_name for c in project.crystals] == ["First", "Middle", "Last"]
