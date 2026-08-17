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


def test_an_edit_that_changes_no_structure_KEEPS_the_conformers(qapp):
    """**NOT EVERY `change` FROM THE EDITOR IS A STRUCTURE CHANGE.**

    Ketcher emits one for actions that annotate or tidy rather than edit,
    and Calculate CIP is the sharpest case: its entire purpose is to
    display R/S and E/Z, and it alters nothing. Measured in the running
    app before this check existed -- import, generate, press "Calculate
    CIP (Stereo Descriptors)":

        conformers 4 -> 0,  canonical SMILES identical either side

    A read-only annotation destroyed the geometry it was annotating.
    Layout and Clean Up have the same shape; so does dragging an atom.

    CIP itself no longer arrives this way -- the descriptors go through
    `ketcher.indigo.calculateCip`, which fires no `change` -- so it is the
    clearest illustration rather than a live path. The other three are
    live, which is what this still guards.

    The fixture re-serialises through the engine so the molblock TEXT
    differs while the constitution does not -- which is exactly the case
    a byte comparison would get wrong, and the case the editor really
    produces.
    """
    bus = EventBus()
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Test")
    engine.set_structure_from_smiles(molecule, "C[C@H](N)C(=O)O")
    conformer = ConformerModel(molblock="geometry", energy=1.0, method="rdkit")
    molecule.conformers = [conformer]
    stack = QUndoStack()

    # The same structure, drawn somewhere else: coordinates shifted, so
    # the molblock is different text for the same molecule.
    from rdkit import Chem

    drawn = Chem.MolFromMolBlock(molecule.molblock, removeHs=False)
    layout = drawn.GetConformer()
    for index in range(drawn.GetNumAtoms()):
        point = layout.GetAtomPosition(index)
        layout.SetAtomPosition(index, (point.x + 1.25, point.y, point.z))
    moved = Chem.MolToMolBlock(drawn)
    assert moved != molecule.molblock

    invalidated = []
    bus.subscribe(ConformersInvalidated, lambda e: invalidated.append(e.molecule_uuid))

    stack.push(EditStructureCommand(engine, molecule, moved, bus))

    assert molecule.conformers == [conformer], "a no-op edit threw the geometry away"
    assert invalidated == []


def test_an_edit_that_changes_STEREOCHEMISTRY_still_invalidates(qapp):
    """The complement, and the one a constitution-only comparison fails.

    Flipping a wedge leaves every atom and bond in place, so anything
    comparing formulas or heavy-atom graphs would call it a no-op -- and
    a conformer of the R enantiomer is not a conformer of the S one.
    Canonical SMILES carries stereochemistry, which is why the check is
    on that rather than on something cheaper.
    """
    bus = EventBus()
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Test")
    engine.set_structure_from_smiles(molecule, "C[C@H](N)C(=O)O")
    molecule.conformers = [ConformerModel(molblock="geometry", method="rdkit")]

    flipped = MoleculeModel()
    engine.set_structure_from_smiles(flipped, "C[C@@H](N)C(=O)O")
    assert flipped.canonical_smiles != molecule.canonical_smiles

    invalidated = []
    bus.subscribe(ConformersInvalidated, lambda e: invalidated.append(e.molecule_uuid))

    QUndoStack().push(EditStructureCommand(engine, molecule, flipped.molblock, bus))

    assert molecule.conformers == []
    assert invalidated == [molecule.uuid]
