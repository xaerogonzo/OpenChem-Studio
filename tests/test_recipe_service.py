"""The recipe service over a real project: real molecules, real conformers, real fingerprints (`RECIPES_DESIGN.md` 5-8).

What makes a stored run 'current', 'at an earlier geometry' or 'of an edited structure' is the molecule changing
for real: a conformer added, the structure redrawn, a run deleted. No Qt window is needed (the service reads the
project through the result store), and no ORCA: the runs carry the documented B3LYP/def2-SVP numbers.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.bootstrap import build_service_container
from openchem.domain.calculator import GEOMETRY
from openchem.domain.common import CacheState
from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus
from openchem.domain.recipe_run import BindingState, RecipeRunStatus, StaleCause

M = "B3LYP def2-SVP"
GAP, HSAB = "Frontier orbital gap", "HSAB hardness match"

CO = dict(homo=-10.17, lumo=99.0, hardness=8.40)
BH3 = dict(homo=-99.0, lumo=-2.04, hardness=6.77)


@pytest.fixture()
def services():
    return build_service_container()


def _molecule(engine, smiles: str, name: str) -> MoleculeModel:
    model = MoleculeModel(display_name=name)
    engine.set_structure_from_smiles(model, smiles)
    return model


def _conformer(engine, model: MoleculeModel, seed: int = 11) -> ConformerModel:
    mol = Chem.AddHs(engine.mol_from_model(model))
    assert AllChem.EmbedMolecule(mol, randomSeed=seed) == 0
    return ConformerModel(molblock=Chem.MolToMolBlock(mol), energy=float(seed))


def _descriptor(model, descriptor_id, value):
    return DescriptorValue(
        descriptor_id=descriptor_id, name=descriptor_id, units="eV", category="quantum_chemistry", provider="orca",
        molecule_uuid=model.uuid, value=value, cache_state=CacheState.COMPLETED,
    )


def _record_runs(services, model: MoleculeModel, numbers: dict, tag: str, *, completed_at: float = 2.0, hardness=True):
    """Stored runs of `model` at its geometry as it is NOW: the fingerprint the resolver gives and the conformer's
    molblock, exactly what the Quantum Chemistry service records."""
    store = services.result_store_service
    fingerprint = store.fingerprints_for(model)[GEOMETRY]
    molblock = next(c for c in model.conformers).molblock
    made = []
    for suffix, calc, values in (
        ("sp", "sp", {"orca.homo_energy": numbers["homo"], "orca.lumo_energy": numbers["lumo"]}),
        ("dscf", "delta_scf", {"orca.dscf_hardness": numbers["hardness"]}),
    ):
        if calc == "delta_scf" and not hardness:
            continue
        run = QuantumChemistryRun(
            run_id=f"{tag}-{suffix}", molecule_uuid=model.uuid, calc_type=calc, method_basis=M, charge=0, multiplicity=1,
            calculation_input=GEOMETRY, input_fingerprint=fingerprint, input_molblock=molblock,
            started_at=1.0, completed_at=completed_at, status=RunStatus.COMPLETED,
        )
        run.results["descriptors"] = [_descriptor(model, k, v) for k, v in values.items()]
        store.record_quantum_chemistry_run(run)
        assert store.qc_runs.get(run.run_id) is run, "the store refused the run: is its molecule in the open project?"
        made.append(run)
    return made


@pytest.fixture()
def pair(services):
    """Borane and carbon monoxide in an open project, each with a conformer and current stored runs."""
    engine = services.chemistry_engine
    project = ProjectModel(name="pairing")
    borane, mono = _molecule(engine, "B", "BH3"), _molecule(engine, "[C-]#[O+]", "CO")
    for model in (borane, mono):
        model.conformers.append(_conformer(engine, model))
        project.molecules.append(model)
    services.result_store_service.set_project(project)
    _record_runs(services, borane, BH3, "bh3")
    _record_runs(services, mono, CO, "co")
    return project, borane, mono


def _lines(run, label):
    import re

    found = []
    for text in run.result.matched:
        match = re.match(rf"\s*{re.escape(label)}: (?:(-?\d+\.\d+) eV|not available)", text)
        if match:
            found.append(float(match.group(1)) if match.group(1) else None)
    return found


# --- the wiring ---------------------------------------------------------------------------------------------------


def test_the_container_has_a_recipe_service_over_the_same_result_store(services):
    assert services.recipe_service is not None
    assert services.recipe_service._store is services.result_store_service


# --- evaluating over a real project ------------------------------------------------------------------------------


def test_the_documented_pair_reproduces_over_a_real_project(services, pair):
    _, borane, mono = pair
    run = services.recipe_service.evaluate_lewis_pairing(borane.uuid, mono.uuid, method_basis=M, role="acid")
    assert run.status is RecipeRunStatus.COMPLETED
    assert _lines(run, GAP) == [pytest.approx(8.13)] and _lines(run, HSAB) == [pytest.approx(1.63)]
    assert [i.molecule_uuid for i in run.inputs] == [borane.uuid, mono.uuid]
    assert run.inputs[0].constitution_key and run.inputs[0].drawing_fingerprint


def test_a_gap_names_the_molecule_by_its_name_in_the_project(services, pair):
    _, borane, mono = pair
    services.result_store_service.qc_runs.delete("co-dscf")
    run = services.recipe_service.evaluate_lewis_pairing(borane.uuid, mono.uuid, method_basis=M, role="acid")
    gap = next(b for b in run.bindings if b.state is BindingState.MISSING)
    assert gap.reason.startswith("CO has no delta-SCF run")


def test_the_runs_the_numbers_came_from_are_named(services, pair):
    _, borane, mono = pair
    run = services.recipe_service.evaluate_lewis_pairing(borane.uuid, mono.uuid, method_basis=M, role="acid")
    assert {b.target: b.evidence.run_id for b in run.bindings} == {
        "first_homo": "bh3-sp", "first_lumo": "bh3-sp", "first_hardness": "bh3-dscf",
        "second_homo": "co-sp", "second_lumo": "co-sp", "second_hardness": "co-dscf",
    }


def test_evaluating_records_nothing_and_does_not_mark_the_project_unsaved(services, pair):
    _, borane, mono = pair
    seen = []
    services.result_store_service.add_recorded_listener(seen.append)
    services.recipe_service.evaluate_lewis_pairing(borane.uuid, mono.uuid, method_basis=M, role="acid")
    assert services.result_store_service.recipe_runs.all_runs() == [] and seen == []


def test_a_molecule_that_is_not_in_the_project_is_a_caller_error(services, pair):
    _, borane, _ = pair
    with pytest.raises(ValueError, match="not in the open project"):
        services.recipe_service.evaluate_lewis_pairing(borane.uuid, "elsewhere", method_basis=M)


def test_with_no_project_open_nothing_can_be_evaluated(services):
    services.result_store_service.set_project(None)
    with pytest.raises(ValueError, match="no project is open"):
        services.recipe_service.evaluate_lewis_pairing("a", "b", method_basis=M)


# --- the molecule changing under its runs ------------------------------------------------------------------------


def test_a_second_conformer_that_becomes_the_input_puts_the_runs_at_an_earlier_geometry(services, pair):
    """The runs were made at the first conformer. A lower-energy one is added, so a run now gets that geometry, and
    the stored runs are of the same molecule at a geometry it no longer uses: not current, and not used unasked."""
    _, borane, mono = pair
    engine = services.chemistry_engine
    better = _conformer(engine, mono, seed=99)
    better.energy = -50.0
    mono.conformers.append(better)
    run = services.recipe_service.evaluate_lewis_pairing(borane.uuid, mono.uuid, method_basis=M, role="acid")
    states = {b.target: b.state for b in run.bindings}
    assert states["first_lumo"] is BindingState.BOUND, "borane was not touched"
    assert states["second_homo"] is states["second_hardness"] is BindingState.AMBIGUOUS
    assert run.status is RecipeRunStatus.PARTIAL


def test_removing_the_new_conformer_makes_the_old_runs_current_again(services, pair):
    """Staleness is read, so there is nothing stored to put back."""
    _, borane, mono = pair
    added = _conformer(services.chemistry_engine, mono, seed=99)
    added.energy = -50.0
    mono.conformers.append(added)
    assert services.recipe_service.evaluate_lewis_pairing(borane.uuid, mono.uuid, method_basis=M, role="acid").result is None
    mono.conformers.remove(added)
    again = services.recipe_service.evaluate_lewis_pairing(borane.uuid, mono.uuid, method_basis=M, role="acid")
    assert again.status is RecipeRunStatus.COMPLETED


def test_an_earlier_geometry_can_be_chosen_by_run_id(services, pair):
    _, borane, mono = pair
    better = _conformer(services.chemistry_engine, mono, seed=99)
    better.energy = -50.0
    mono.conformers.append(better)
    run = services.recipe_service.evaluate_lewis_pairing(
        borane.uuid, mono.uuid, method_basis=M, role="acid",
        picks={"second": {"sp": "co-sp", "delta_scf": "co-dscf"}},
    )
    assert run.status is RecipeRunStatus.COMPLETED
    assert _lines(run, GAP) == [pytest.approx(8.13)]
    assert "earlier geometry" in next(b for b in run.bindings if b.target == "second_homo").reason


def test_redrawing_a_molecule_makes_its_runs_stale_and_unused(services, pair):
    _, borane, mono = pair
    services.chemistry_engine.set_structure_from_smiles(mono, "C=O")  # formaldehyde, not carbon monoxide
    mono.conformers.clear()
    run = services.recipe_service.evaluate_lewis_pairing(borane.uuid, mono.uuid, method_basis=M, role="acid")
    states = {b.target: b.state for b in run.bindings}
    assert states["second_homo"] is states["second_hardness"] is BindingState.STALE
    assert run.result is None


def test_a_formal_charge_the_runs_do_not_share_is_a_different_species(services, pair):
    _, borane, mono = pair
    ion = _molecule(services.chemistry_engine, "C[N+](C)(C)C", "tetramethylammonium")
    ion.conformers.append(_conformer(services.chemistry_engine, ion))
    services.result_store_service.project.molecules.append(ion)
    _record_runs(services, ion, dict(homo=-5.0, lumo=1.0, hardness=4.0), "ion")  # recorded at charge 0
    run = services.recipe_service.evaluate_lewis_pairing(borane.uuid, ion.uuid, method_basis=M, role="acid")
    assert {b.target: b.state for b in run.bindings}["second_homo"] is BindingState.INCOMPATIBLE


# --- staleness of a recorded run, read when asked -----------------------------------------------------------------


def _recorded(services, borane, mono):
    run = services.recipe_service.evaluate_lewis_pairing(borane.uuid, mono.uuid, method_basis=M, role="acid")
    assert services.result_store_service.record_recipe_run(run)
    return run


def test_a_recorded_run_over_an_unchanged_project_is_not_stale(services, pair):
    _, borane, mono = pair
    run = _recorded(services, borane, mono)
    assert not services.recipe_service.assess(run).stale


def test_editing_a_structure_makes_the_recorded_answer_stale_and_undoing_it_does_not(services, pair):
    _, borane, mono = pair
    run = _recorded(services, borane, mono)
    original = mono.molblock
    services.chemistry_engine.set_structure_from_smiles(mono, "C=O")
    edited = services.recipe_service.assess(run)
    assert edited.causes == (StaleCause.STRUCTURE_EDITED,) and "second" in edited.details[0]
    mono.molblock = original
    assert not services.recipe_service.assess(run).stale, "the record never changed, so there is nothing to put back"


def test_deleting_a_quantum_chemistry_run_makes_the_answer_stale_and_the_numbers_stay(services, pair):
    _, borane, mono = pair
    run = _recorded(services, borane, mono)
    assert services.result_store_service.qc_runs.delete("co-dscf")
    assessment = services.recipe_service.assess(run)
    assert assessment.causes == (StaleCause.EVIDENCE_REMOVED,) and "co-dscf" in assessment.details[0]
    assert [e.value for e in run.evidence() if e.run_id == "co-dscf"] == [8.40]


def test_removing_a_molecule_from_the_project_is_its_own_cause(services, pair):
    project, borane, mono = pair
    run = _recorded(services, borane, mono)
    project.molecules.remove(mono)
    assert StaleCause.MOLECULE_REMOVED in services.recipe_service.assess(run).causes


def test_a_molecule_whose_drawing_cannot_be_read_has_no_key_and_its_slot_is_unverifiable(services, pair):
    """Not 'unchanged' and not 'edited': the comparison could not be made, and the answer says so."""
    project, borane, mono = pair
    run = _recorded(services, borane, mono)
    mono.molblock = "this is not a molblock"
    view = services.recipe_service.project_view()
    assert view.constitution_keys[mono.uuid] is None and view.constitution_keys[borane.uuid]
    assessment = services.recipe_service.assess(run)
    assert assessment.unverifiable_slots == ("second",) and not assessment.stale


def test_the_view_has_a_key_for_every_molecule_and_every_run(services, pair):
    project, borane, mono = pair
    view = services.recipe_service.project_view()
    assert set(view.constitution_keys) == {borane.uuid, mono.uuid}
    assert all(key for key in view.constitution_keys.values())
    assert set(view.qc_run_ids) == {"bh3-sp", "bh3-dscf", "co-sp", "co-dscf"}


def test_a_recipe_run_of_a_version_this_build_does_not_have_cannot_be_reevaluated(services, pair):
    from dataclasses import replace

    _, borane, mono = pair
    run = replace(_recorded(services, borane, mono), recipe_version="99")
    assessment = services.recipe_service.assess(run)
    assert StaleCause.RECIPE_VERSION_UNKNOWN in assessment.causes and not assessment.can_reevaluate


# --- the kept answers, as Results entries (slice 3b) --------------------------------------------------------------


def _version(services, model) -> int:
    return services.structure_check_service.current_version(model.uuid)


def test_a_kept_answer_is_a_results_entry_under_each_molecule_that_took_part(services, pair):
    _, borane, mono = pair
    run = _recorded(services, borane, mono)
    for model in (borane, mono):
        [answer] = services.recipe_service.answers_for(model.uuid, _version(services, model))
        assert answer.run_id == run.run_id and answer.molecule_uuid == model.uuid
        assert answer.name == "Lewis pairing: BH3 + CO at B3LYP def2-SVP (gas phase)"
        assert answer.facts == run.result.facts and answer.stale_note == ""


def test_nothing_kept_means_no_entries_and_no_drawing_is_parsed(services, pair, monkeypatch):
    _, borane, _ = pair
    parsed = []
    monkeypatch.setattr(
        type(services.recipe_service), "project_view", lambda self, only=None: parsed.append(only) or None
    )
    assert services.recipe_service.answers_for(borane.uuid, 3) == () and parsed == []


def test_a_molecule_that_took_no_part_has_no_entries(services, pair):
    project, borane, mono = pair
    _recorded(services, borane, mono)
    other = _molecule(services.chemistry_engine, "N", "NH3")
    project.molecules.append(other)
    assert services.recipe_service.answers_for(other.uuid, 1) == ()


def test_only_the_molecules_of_the_kept_runs_are_parsed(services, pair):
    project, borane, mono = pair
    _recorded(services, borane, mono)
    other = _molecule(services.chemistry_engine, "N", "NH3")
    project.molecules.append(other)
    limited = services.recipe_service.project_view({borane.uuid, mono.uuid})
    assert set(limited.constitution_keys) == {borane.uuid, mono.uuid}
    assert set(services.recipe_service.project_view().constitution_keys) == {borane.uuid, mono.uuid, other.uuid}


def test_editing_either_molecule_makes_the_entry_stale_under_both(services, pair):
    _, borane, mono = pair
    _recorded(services, borane, mono)
    services.chemistry_engine.set_structure_from_smiles(mono, "C=O")
    for model in (borane, mono):
        [answer] = services.recipe_service.answers_for(model.uuid, _version(services, model))
        assert answer.structure_version == -1
        assert "The structure of CO was edited after this answer was made." in answer.stale_note


def test_deleting_a_consumed_run_makes_the_entry_stale_and_the_numbers_stay(services, pair):
    _, borane, mono = pair
    _recorded(services, borane, mono)
    assert services.result_store_service.delete_quantum_chemistry_run("co-dscf")
    [answer] = services.recipe_service.answers_for(borane.uuid, _version(services, borane))
    assert answer.structure_version == -1 and "co-dscf" in answer.stale_note
    assert any("HSAB" in fact.label or "HSAB" in fact.display_value for fact in answer.facts)


def test_a_removed_molecule_leaves_the_other_one_showing_the_answer_as_stale(services, pair):
    project, borane, mono = pair
    _recorded(services, borane, mono)
    project.molecules.remove(mono)
    [answer] = services.recipe_service.answers_for(borane.uuid, _version(services, borane))
    assert "no longer in the project" in answer.stale_note and "BH3 + a molecule" in answer.name


def test_undoing_the_edit_makes_the_entry_current_again_because_staleness_is_read(services, pair):
    _, borane, mono = pair
    _recorded(services, borane, mono)
    original = mono.molblock
    services.chemistry_engine.set_structure_from_smiles(mono, "C=O")
    assert services.recipe_service.answers_for(borane.uuid, 5)[0].structure_version == -1
    mono.molblock = original
    assert services.recipe_service.answers_for(borane.uuid, 5)[0].structure_version == 5


def test_the_entry_is_never_in_the_session_result_store(services, pair):
    """The design's decision: a recipe answer is NOT also a result, so there is no second copy to disagree."""
    _, borane, mono = pair
    store = services.result_store_service.store
    before = {uuid: len(store.all_results(uuid)) for uuid in (borane.uuid, mono.uuid)}
    _recorded(services, borane, mono)
    services.recipe_service.answers_for(borane.uuid, 1)
    assert {uuid: len(store.all_results(uuid)) for uuid in (borane.uuid, mono.uuid)} == before
    assert store.molecule_uuids() == [] and store.to_dict()["molecules"] == {}
