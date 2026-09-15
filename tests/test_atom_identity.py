"""Round 3 Track 2: which conformer atom is which drawn atom (preregistration.md E1).

The failure these guard against was measured in the running app before any of
this existed: after an erase-and-redraw kept the conformer, ethanol's oxygen
showed carbon C1's EEM 3D charge (-0.4258 e where its own is -0.5818 e), with
the result reading fresh. Every fixture here uses the real conformer provider,
so the atom-tag route is the one the app runs.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import atom_identity as ai
from openchem.chem.calculation_input import input_fingerprint
from openchem.chem.conformer_providers import RDKitConformerProvider
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import DRAWING
from openchem.domain.common import Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import PerAtomDataset


@pytest.fixture(scope="module")
def engine():
    return ChemistryEngine()


def _model(engine, smiles: str) -> MoleculeModel:
    model = MoleculeModel(display_name=smiles)
    engine.set_structure_from_smiles(model, smiles)
    return model


def _conformer_via_provider(engine, model, *, record=True) -> ConformerModel:
    """The service's own route: tag, generate with the real provider, read the tags back."""
    mol = ai.tag_drawing_atoms(engine.mol_from_model(model))
    provider = RDKitConformerProvider(random_seed=20260915)
    (conf_mol, _energy), *_ = provider.generate_conformers(mol, num_conformers=1, optimize=True)
    ids = ai.recorded_drawing_ids(conf_mol) if record else None
    return ConformerModel(molblock=engine.mol_to_molblock(conf_mol), drawing_atom_ids=ids,
                          drawing_fingerprint=input_fingerprint(engine, model, DRAWING) if ids is not None else None)


def _dataset_on(conformer: ConformerModel, values: dict[int, float]) -> PerAtomDataset:
    return PerAtomDataset(property_id="geometry_partial_charge", name="charge", units="e", method="test", molecule_uuid="m",
                          values=values, provenance=Provenance(created_by="core", method="test", parameters={
                              "input_source": "automatic_lowest_energy", "input_conformer_id": conformer.conformer_id}))


def _values_by_element(engine, conformer) -> dict[int, float]:
    """A distinct value per conformer atom, so any wrong pairing changes a number."""
    mol = engine.mol_from_molblock(conformer.molblock)
    return {a.GetIdx(): 10.0 * a.GetAtomicNum() + a.GetIdx() / 100.0 for a in mol.GetAtoms()}


def test_atom_tags_survive_the_real_provider_and_hydrogens_get_none(engine):
    model = _model(engine, "CCO")
    conformer = _conformer_via_provider(engine, model)
    mol = engine.mol_from_molblock(conformer.molblock)
    assert conformer.drawing_atom_ids[:3] == [0, 1, 2]
    assert all(conformer.drawing_atom_ids[i] == -1 for i in range(3, mol.GetNumAtoms()))
    assert all(mol.GetAtomWithIdx(i).GetAtomicNum() == 1 for i in range(3, mol.GetNumAtoms()))


def test_a_drawing_keyed_dataset_is_left_as_it_is(engine):
    model = _model(engine, "CCO")
    dataset = PerAtomDataset(property_id="gasteiger_charge", name="g", units="e", method="rdkit", molecule_uuid="m", values={0: 1.0})
    assert ai.project_to_drawing(engine, model, dataset) == ai.DrawingProjection({0: 1.0}, ai.POLICY_SAME_SPACE)


def test_the_recorded_map_is_used_while_the_drawing_is_unchanged(engine):
    model = _model(engine, "CCO")
    conformer = _conformer_via_provider(engine, model)
    model.conformers = [conformer]
    values = _values_by_element(engine, conformer)
    projection = ai.project_to_drawing(engine, model, _dataset_on(conformer, values))
    assert projection.policy == ai.POLICY_RECORDED
    assert projection.values == {0: values[0], 1: values[1], 2: values[2]}


def test_the_measured_defect_a_reordered_drawing_gets_each_atoms_own_value(engine):
    """E1: the drawing is renumbered, the conformer is kept. O must show O's value."""
    model = _model(engine, "CCO")
    conformer = _conformer_via_provider(engine, model)
    model.conformers = [conformer]
    values = _values_by_element(engine, conformer)
    model.molblock = ai.renumbered_molblock(model.molblock, "reverse")  # now O, C, C
    projection = ai.project_to_drawing(engine, model, _dataset_on(conformer, values))
    assert projection.policy == ai.POLICY_GRAPH_UNIQUE  # the recorded map is no longer trusted
    drawn = engine.mol_from_model(model)
    for index, value in projection.values.items():
        assert int(value // 10) == drawn.GetAtomWithIdx(index).GetAtomicNum(), (index, value)


def test_reading_the_index_as_is_would_have_been_wrong_here(engine):
    """Guard on the guard: the fixture above must actually reorder heavy atoms."""
    model = _model(engine, "CCO")
    reordered = ai.renumbered_molblock(model.molblock, "reverse")
    assert ai.element_order(reordered)[0] != ai.element_order(model.molblock)[0]


def test_isopropanol_after_a_reorder_refuses_when_the_methyls_differ(engine):
    model = _model(engine, "CC(C)O")
    conformer = _conformer_via_provider(engine, model)
    model.conformers = [conformer]
    values = _values_by_element(engine, conformer)  # distinct values on the two methyl carbons
    model.molblock = ai.renumbered_molblock(model.molblock, [3, 2, 1, 0])
    projection = ai.project_to_drawing(engine, model, _dataset_on(conformer, values))
    assert projection.values is None and projection.refusal == ai.REFUSE_AMBIGUOUS_IDENTITY


def test_isopropanol_with_its_recorded_map_places_each_methyls_own_value(engine):
    model = _model(engine, "CC(C)O")
    conformer = _conformer_via_provider(engine, model)
    model.conformers = [conformer]
    values = _values_by_element(engine, conformer)
    projection = ai.project_to_drawing(engine, model, _dataset_on(conformer, values))
    assert projection.policy == ai.POLICY_RECORDED
    assert projection.values[0] == values[0] and projection.values[2] == values[2]


def test_equal_values_on_equivalent_atoms_are_projectable_and_say_why(engine):
    model = _model(engine, "CC(C)O")
    conformer = _conformer_via_provider(engine, model)
    model.conformers = [conformer]
    values = _values_by_element(engine, conformer)
    values[2] = values[0]  # the two methyl carbons now agree, and their hydrogens are not drawn
    model.molblock = ai.renumbered_molblock(model.molblock, [3, 2, 1, 0])
    projection = ai.project_to_drawing(engine, model, _dataset_on(conformer, values))
    assert projection.policy == ai.POLICY_GRAPH_VALUE_INVARIANT
    # New position k holds old atom order[k]: O, methyl, central C, methyl.
    assert projection.values[2] == values[1]
    assert projection.values[1] == projection.values[3] == values[0]


def test_value_uniqueness_is_judged_at_the_consumers_printed_precision(engine):
    """preregistration.md E1: "the same value" is the same PRINTED value. The app measured
    isopropanol's methyls at -0.45880x and -0.45881x: identical on screen, different numbers."""
    from openchem.chem.atom_report import per_atom_display

    model = _model(engine, "CC(C)O")
    conformer = _conformer_via_provider(engine, model)
    model.conformers = [conformer]
    values = _values_by_element(engine, conformer)
    values[0], values[2] = -0.458801, -0.458812  # print alike at .4g
    model.molblock = ai.renumbered_molblock(model.molblock, [3, 2, 1, 0])
    dataset = _dataset_on(conformer, values)
    assert per_atom_display(values[0]) == per_atom_display(values[2])
    assert ai.project_to_drawing(engine, model, dataset).refusal == ai.REFUSE_AMBIGUOUS_IDENTITY
    shown = ai.project_to_drawing(engine, model, dataset, display=per_atom_display)
    assert shown.policy == ai.POLICY_GRAPH_VALUE_INVARIANT
    values[2] = -0.4591  # now prints differently
    assert ai.project_to_drawing(engine, model, _dataset_on(conformer, values), display=per_atom_display).refusal == ai.REFUSE_AMBIGUOUS_IDENTITY


def test_a_conformer_with_hydrogens_first_and_no_record_projects_by_graph(engine):
    model = _model(engine, "CCO")
    provider_mol = Chem.AddHs(engine.mol_from_model(model))
    AllChem.EmbedMolecule(provider_mol, randomSeed=7)
    order = [a.GetIdx() for a in provider_mol.GetAtoms() if a.GetAtomicNum() == 1] + [0, 1, 2]
    shuffled = Chem.RenumberAtoms(provider_mol, order)
    conformer = ConformerModel(molblock=Chem.MolToMolBlock(shuffled))
    model.conformers = [conformer]
    values = _values_by_element(engine, conformer)
    projection = ai.project_to_drawing(engine, model, _dataset_on(conformer, values))
    assert projection.policy == ai.POLICY_GRAPH_UNIQUE
    drawn = engine.mol_from_model(model)
    assert all(int(v // 10) == drawn.GetAtomWithIdx(i).GetAtomicNum() for i, v in projection.values.items())


def test_a_stale_recorded_map_is_not_trusted_even_if_its_length_fits(engine):
    """Mutation guard for trusting the map after the drawing changed."""
    model = _model(engine, "CCO")
    conformer = _conformer_via_provider(engine, model)
    model.conformers = [conformer]
    model.molblock = ai.renumbered_molblock(model.molblock, "reverse")
    projection = ai.project_to_drawing(engine, model, _dataset_on(conformer, _values_by_element(engine, conformer)))
    assert projection.policy != ai.POLICY_RECORDED


def test_opposite_stereo_has_no_correspondence(engine):
    model = _model(engine, "C[C@@H](O)CC")
    other = _model(engine, "C[C@H](O)CC")
    conformer = _conformer_via_provider(engine, other, record=False)
    model.conformers = [conformer]
    projection = ai.project_to_drawing(engine, model, _dataset_on(conformer, _values_by_element(engine, conformer)))
    assert projection.values is None and projection.refusal == ai.REFUSE_NO_CORRESPONDENCE


def test_an_isotope_label_is_part_of_identity(engine):
    model = _model(engine, "[13CH3]CO")
    conformer = _conformer_via_provider(engine, _model(engine, "CCO"), record=False)
    model.conformers = [conformer]
    projection = ai.project_to_drawing(engine, model, _dataset_on(conformer, _values_by_element(engine, conformer)))
    assert projection.refusal == ai.REFUSE_NO_CORRESPONDENCE


def test_a_conformer_that_is_no_longer_stored_is_named(engine):
    model = _model(engine, "CCO")
    conformer = _conformer_via_provider(engine, model)
    projection = ai.project_to_drawing(engine, model, _dataset_on(conformer, {0: 1.0}))
    assert projection.refusal == ai.REFUSE_CONFORMER_GONE


def test_the_conformer_map_round_trips_through_a_saved_project():
    conformer = ConformerModel(molblock="x", drawing_atom_ids=[0, 2, 1, -1], drawing_fingerprint="abc")
    back = ConformerModel.from_dict(conformer.to_dict())
    assert back.drawing_atom_ids == [0, 2, 1, -1] and back.drawing_fingerprint == "abc"
    old = conformer.to_dict()
    del old["drawing_atom_ids"], old["drawing_fingerprint"]
    assert ConformerModel.from_dict(old).drawing_atom_ids is None
