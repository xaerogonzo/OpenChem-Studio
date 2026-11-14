"""A rename is not a structure edit, and a repeated result is not a new one."""

from PySide6.QtGui import QUndoStack
from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.commands.molecule_commands import (
    ChooseComponentCommand,
    EditStructureCommand,
    RenameMoleculeCommand,
)
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.result_store import ResultIdentity, SessionResultStore, StoredResult
from openchem.events.base import EventBus
from openchem.events.events import (
    CHANGE_CALCULATION_INPUT,
    CHANGE_IDENTITY,
    CHANGE_LAYOUT,
    CHANGE_STRUCTURE,
    MoleculeChanged,
)
from openchem.services.structure_check_service import StructureCheckService


def _ethanol(engine: ChemistryEngine) -> MoleculeModel:
    molecule = MoleculeModel(display_name="ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    return molecule


def test_rename_does_not_advance_the_structure_version_or_look_like_chemistry(qapp):
    bus = EventBus()
    service = StructureCheckService(bus)
    engine = ChemistryEngine()
    molecule = _ethanol(engine)
    project = ProjectModel()
    project.molecules.append(molecule)
    seen: list[MoleculeChanged] = []
    bus.subscribe(MoleculeChanged, seen.append)

    stack = QUndoStack()
    stack.push(RenameMoleculeCommand(molecule, "spirit", bus))

    assert molecule.display_name == "spirit"
    assert seen[-1].kind == CHANGE_IDENTITY
    assert service.current_version(molecule.uuid) == 0

    stack.undo()
    assert molecule.display_name == "ethanol"
    assert seen[-1].kind == CHANGE_IDENTITY
    assert service.current_version(molecule.uuid) == 0

    stack.redo()
    assert molecule.display_name == "spirit"
    assert service.current_version(molecule.uuid) == 0


def test_a_real_edit_advances_the_version_and_a_coordinate_move_does_not(qapp):
    bus = EventBus()
    service = StructureCheckService(bus)
    engine = ChemistryEngine()
    molecule = _ethanol(engine)
    kinds: list[str] = []
    bus.subscribe(MoleculeChanged, lambda event: kinds.append(event.kind))
    stack = QUndoStack()

    drawn = Chem.MolFromMolBlock(molecule.molblock, removeHs=False)
    layout = drawn.GetConformer()
    for index in range(drawn.GetNumAtoms()):
        point = layout.GetAtomPosition(index)
        layout.SetAtomPosition(index, (point.x + 1.25, point.y, point.z))
    stack.push(EditStructureCommand(engine, molecule, Chem.MolToMolBlock(drawn), bus))
    assert kinds[-1] == CHANGE_LAYOUT
    assert service.current_version(molecule.uuid) == 0

    other = MoleculeModel()
    engine.set_structure_from_smiles(other, "CCC")
    stack.push(EditStructureCommand(engine, molecule, other.molblock, bus))
    assert kinds[-1] == CHANGE_STRUCTURE
    assert service.current_version(molecule.uuid) == 1


def test_a_component_choice_invalidates_without_being_a_rename(qapp):
    bus = EventBus()
    service = StructureCheckService(bus)
    molecule = MoleculeModel(display_name="salt")
    kinds: list[str] = []
    bus.subscribe(MoleculeChanged, lambda event: kinds.append(event.kind))
    QUndoStack().push(ChooseComponentCommand(molecule, "CCO", bus))
    assert kinds == [CHANGE_CALCULATION_INPUT]
    assert service.current_version(molecule.uuid) == 1
    assert molecule.component_choice == "CCO"


def test_an_identical_stored_result_is_not_a_new_one():
    store = SessionResultStore("project")
    stored = StoredResult(
        identity=ResultIdentity(
            molecule_uuid="m",
            result_id="logp",
            calculation_input="drawing",
            input_fingerprint="abc",
            producer="logp",
        ),
        result="1.2",
    )
    assert store.put(stored) is True
    assert store.put(stored) is False
    replacement = StoredResult(identity=stored.identity, result="9.9")
    assert store.put(replacement) is True
