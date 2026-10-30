"""A person can choose which component of a multi-piece drawing a calculator is handed.

The automatic pick (ChEMBL's parent, else the largest component) stays what it was; a choice stored on the
molecule as the component's canonical SMILES overrides it, rides to `components.select` on the Mol that
`ChemistryEngine.mol_from_model` builds, is part of the input fingerprint, and is saved in the project file.
"""

from __future__ import annotations

from rdkit import Chem

from openchem.chem import components
from openchem.chem.calculation_input import DRAWING, resolve_calculation_input
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import Aggregation, CalculatorScope, ComponentSelection, MethodDomain
from openchem.domain.molecule import MoleculeModel

SCOPE = CalculatorScope(ComponentSelection.CHEMBL_PARENT, Aggregation.SCALAR, MethodDomain.METHOD_SPECIFIC)
#: Choline salicylate: ChEMBL's rule leaves both pieces, so the automatic pick is the larger (salicylate).
CHOLINE_SALICYLATE = "C[N+](C)(C)CCO.[O-]C(=O)c1ccccc1O"
CHOLINE = "C[N+](C)(C)CCO"


def _model(smiles: str, choice: str = "") -> MoleculeModel:
    mol = Chem.MolFromSmiles(smiles)
    return MoleculeModel(molblock=Chem.MolToMolBlock(mol), canonical_smiles=Chem.MolToSmiles(mol), component_choice=choice)


def _selected(model: MoleculeModel) -> components.Selection:
    return components.select(ChemistryEngine().mol_from_model(model), SCOPE, "This calculator")


def test_without_a_choice_the_automatic_pick_is_unchanged():
    selection = _selected(_model(CHOLINE_SALICYLATE))
    assert not selection.chosen
    assert "largest" in selection.note
    assert Chem.MolToSmiles(selection.mol) == "O=C(O)c1ccccc1O"


def test_a_choice_overrides_the_automatic_pick_and_says_so():
    selection = _selected(_model(CHOLINE_SALICYLATE, CHOLINE))
    assert selection.chosen
    assert Chem.MolToSmiles(selection.mol) == Chem.MolToSmiles(Chem.MolFromSmiles(CHOLINE))
    assert "you chose" in selection.note
    assert "largest" not in selection.note
    # The atoms map back to the drawing's numbering, whichever piece was taken.
    assert sorted(selection.drawing_atoms) == sorted(
        i for i, a in enumerate(Chem.MolFromSmiles(CHOLINE_SALICYLATE).GetAtoms()) if i < Chem.MolFromSmiles(CHOLINE).GetNumAtoms()
    )


def test_a_choice_no_component_matches_falls_back_to_the_automatic_pick():
    """The drawing was edited since the choice was made: nothing is refused and nothing is guessed from it."""
    selection = _selected(_model(CHOLINE_SALICYLATE, "CCCCCC"))
    assert not selection.chosen
    assert Chem.MolToSmiles(selection.mol) == "O=C(O)c1ccccc1O"


def test_the_result_records_that_the_component_was_chosen():
    selection = _selected(_model(CHOLINE_SALICYLATE, CHOLINE))
    assert components.scope_parameters(SCOPE, selection)["component_choice"] == "chosen"
    assert components.scope_parameters(SCOPE, _selected(_model(CHOLINE_SALICYLATE)))["component_choice"] == "largest"


def test_component_smiles_lists_the_pieces_a_picker_offers():
    mol = ChemistryEngine().mol_from_model(_model(CHOLINE_SALICYLATE))
    assert sorted(components.component_smiles(mol)) == sorted(
        Chem.MolToSmiles(p) for p in Chem.GetMolFrags(Chem.MolFromSmiles(CHOLINE_SALICYLATE), asMols=True)
    )


def test_a_choice_is_part_of_the_input_identity_and_no_choice_changes_nothing():
    engine = ChemistryEngine()
    plain = resolve_calculation_input(engine, _model(CHOLINE_SALICYLATE), DRAWING).fingerprint
    chosen = resolve_calculation_input(engine, _model(CHOLINE_SALICYLATE, CHOLINE), DRAWING).fingerprint
    other = resolve_calculation_input(engine, _model(CHOLINE_SALICYLATE, "[O-]C(=O)c1ccccc1O"), DRAWING).fingerprint
    assert len({plain, chosen, other}) == 3
    # A model with the field left empty fingerprints exactly as a model that never had the field.
    assert plain == resolve_calculation_input(engine, _model(CHOLINE_SALICYLATE, ""), DRAWING).fingerprint


def test_the_choice_is_saved_in_the_project_file_and_only_when_set():
    assert "component_choice" not in _model(CHOLINE_SALICYLATE).to_dict()
    saved = _model(CHOLINE_SALICYLATE, CHOLINE).to_dict()
    assert saved["component_choice"] == CHOLINE
    assert MoleculeModel.from_dict(saved).component_choice == CHOLINE
    # A project written before the field existed opens with the automatic pick.
    del saved["component_choice"]
    assert MoleculeModel.from_dict(saved).component_choice == ""


def test_choosing_a_component_is_an_undoable_command_that_announces_the_molecule_changed():
    from openchem.commands.molecule_commands import ChooseComponentCommand
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeChanged

    model = _model(CHOLINE_SALICYLATE)
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(MoleculeChanged, lambda event: seen.append(event.molecule_uuid))
    command = ChooseComponentCommand(model, CHOLINE, bus)
    command.redo()
    assert model.component_choice == CHOLINE
    command.undo()
    assert model.component_choice == ""
    assert seen == [model.uuid, model.uuid]


def test_the_engine_lists_the_components_and_nothing_for_a_molecule_with_no_drawing():
    engine = ChemistryEngine()
    assert len(engine.component_smiles(_model(CHOLINE_SALICYLATE))) == 2
    assert engine.component_smiles(MoleculeModel()) == []


def test_the_row_offers_distinct_components_and_hides_when_there_is_nothing_to_choose(qapp):
    from openchem.ui.widgets.component_choice_row import ComponentChoiceRow

    row = ComponentChoiceRow()
    picks: list[str] = []
    row.choice_made.connect(picks.append)
    row.set_components([CHOLINE, "[O-]C(=O)c1ccccc1O"], CHOLINE)
    assert not row.isHidden()
    assert row.current_choice() == CHOLINE
    row.set_components(["[Na+]", "[Na+]"], "")  # two identical pieces: nothing to choose between
    assert row.isHidden()
    row.set_components([CHOLINE, "[O-]C(=O)c1ccccc1O"], "CCCC")  # a choice no piece matches reads as Automatic
    assert row.current_choice() == ""
    assert picks == []  # filling the row is not a pick
