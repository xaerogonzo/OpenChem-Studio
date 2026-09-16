"""Round 3 Track 2: the charge models reach the dipole (preregistration.md, architecture and tests).

The rule under test above all: a model that declines a molecule is reported
as declining, and no other model's charges ever stand in for it -- neither in
the computation nor in what gets stored.
"""

from __future__ import annotations

from unittest import mock

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem, rdPartialCharges

from openchem.chem import charge_evaluation as cev
from openchem.chem.dipole import compute_dipole_moment
from openchem.services.result_cache import parameters_key


def _conformer(smiles: str, seed: int = 11) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=seed) == 0
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _registry():
    from openchem.bootstrap import build_service_container

    return build_service_container().calculator_registry


def test_gasteiger_charges_are_exactly_what_the_dipole_used_before():
    mol = _conformer("O=C(O)c1ccccc1O")
    charged = Chem.Mol(mol)
    rdPartialCharges.ComputeGasteigerCharges(charged)
    before = np.nan_to_num([a.GetDoubleProp("_GasteigerCharge") for a in charged.GetAtoms()])
    evaluation = cev.evaluate_charges(mol, cev.GASTEIGER)
    assert [evaluation.charges[i] for i in range(mol.GetNumAtoms())] == list(before)


@pytest.mark.parametrize("model", cev.CHARGE_MODELS)
def test_a_symmetric_molecule_has_no_dipole_under_any_model(model):
    mol = _conformer("FC(F)(F)F")
    result = compute_dipole_moment(mol, "u", {"charge_model": model, "decimal_places": 3})
    assert result.provenance.parameters["debye"] < 0.01


@pytest.mark.parametrize("model", [cev.EEM, cev.QEQ])
def test_every_non_default_result_names_its_model(model):
    result = compute_dipole_moment(_conformer("CCO"), "u", {"charge_model": model})
    label = cev.CHARGE_MODEL_LABELS[model]
    assert label in result.name
    assert any(label in str(getattr(f, "value", f)) or label in str(f) for f in result.facts)
    assert result.provenance.parameters["charge_model"] == model


def test_eem_on_chlorobenzene_is_refused_and_named_not_computed_with_gasteiger():
    result = compute_dipole_moment(_conformer("Clc1ccccc1"), "u", {"charge_model": cev.EEM})
    assert result.inapplicable
    assert "EEM" in result.name and "declined" in result.error
    assert "debye" not in result.provenance.parameters
    assert result.provenance.parameters["refusal"] == "REFUSE_ELEMENT_NOT_PARAMETERISED"


def test_a_refusal_never_invokes_another_charge_model():
    """The architectural no-fallback test: spy on Gasteiger while EEM declines."""
    with mock.patch.object(cev, "_gasteiger", wraps=cev._gasteiger) as gasteiger:
        compute_dipole_moment(_conformer("Clc1ccccc1"), "u", {"charge_model": cev.EEM})
    gasteiger.assert_not_called()


def test_qeq_refuses_the_bound_active_dianion_through_the_dipole():
    """propane-1,3-diide, the one bound-active molecule of amendment A9's corpus."""
    mol = _conformer("[CH2-]C[CH2-]")
    result = compute_dipole_moment(mol, "u", {"charge_model": cev.QEQ})
    assert result.inapplicable and result.provenance.parameters["refusal"] == "REFUSE_BOUND_ACTIVE"


def test_qeq_refuses_lih_through_the_dipole():
    mol = Chem.AddHs(Chem.MolFromSmiles("[LiH]"))
    conformer = Chem.Conformer(mol.GetNumAtoms())
    conformer.Set3D(True)
    conformer.SetAtomPosition(1, (1.5957, 0.0, 0.0))
    mol.AddConformer(conformer, assignId=True)
    result = compute_dipole_moment(mol, "u", {"charge_model": cev.QEQ})
    assert result.inapplicable and result.provenance.parameters["refusal"] == "REFUSE_NOT_CONVERGED"


def test_no_conformer_is_the_existing_fault_not_a_model_refusal():
    result = compute_dipole_moment(Chem.MolFromSmiles("CCO"), "u", {"charge_model": cev.EEM})
    assert not result.inapplicable and "3D conformer" in result.error


def test_the_model_is_part_of_the_recorded_parameters_key_and_a_repeat_is_stable():
    defaults = {p.name: p.default for p in _registry().get("dipole_moment").parameters}
    assert defaults["charge_model"] == cev.GASTEIGER
    assert parameters_key({**defaults, "charge_model": cev.EEM}) != parameters_key(defaults)
    assert parameters_key(dict(defaults)) == parameters_key(defaults)


def test_the_choice_stores_codes_and_shows_labels():
    (param,) = [p for p in _registry().get("dipole_moment").parameters if p.name == "charge_model"]
    assert param.choices == list(cev.CHARGE_MODELS)
    assert param.choice_labels == [cev.CHARGE_MODEL_LABELS[m] for m in cev.CHARGE_MODELS]


def test_parameter_checksums_are_recomputed_from_the_shipped_tables():
    """A silent edit to a shipped number must change the recorded checksum."""
    from openchem.chem import charge_equilibration as ce

    eem = cev.evaluate_charges(_conformer("CCO"), cev.EEM)
    assert eem.parameter_checksum == cev._payload_checksum(cev.parameter_payload(cev.EEM))
    with mock.patch.dict(ce.EEM_BULTINCK2002_PART1, {"C": (ce.EEM_BULTINCK2002_PART1["C"][0] + 0.01, ce.EEM_BULTINCK2002_PART1["C"][1])}):
        assert cev._payload_checksum(cev.parameter_payload(cev.EEM)) != eem.parameter_checksum


def test_each_model_declares_its_own_input_requirement():
    from openchem.domain.calculator import DRAWING, GEOMETRY

    assert cev.INPUT_REQUIREMENT == {cev.GASTEIGER: DRAWING, cev.EEM: GEOMETRY, cev.QEQ: GEOMETRY}


def test_the_benchmark_sentences_state_what_the_committed_benchmark_measured():
    """Each dipole result quotes E2 B for its model; the quote must match the CSV it came from."""
    import csv
    import io
    import pathlib
    import re

    from openchem.chem.dipole import DIPOLE_BENCHMARK

    path = pathlib.Path(__file__).resolve().parent.parent / "benchmarks" / "charges" / "consumers" / "dipole_benchmark.csv"
    text = path.read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO(text.split("\n", 1)[1])))
    for model in cev.CHARGE_MODELS:
        errors = [abs(float(r["error"])) for r in rows if r["charge_model"] == model and r["error"]]
        sentence = DIPOLE_BENCHMARK[model]
        assert f"{sum(errors) / len(errors):.2f} D" in sentence, (model, sentence)
        assert re.search(rf"\b{len(errors)}\b", sentence), (model, sentence)


def test_a_project_saved_by_master_reopens_with_its_gasteiger_dipole_unchanged():
    """preregistration.md: Gasteiger's behaviour against a project MASTER saved (62e2c18,
    `tests/fixtures/projects/master_charge_consumers.ocsproj`), not against a pinned string."""
    import pathlib

    from openchem.chem.atom_identity import POLICY_GRAPH_UNIQUE, project_to_drawing
    from openchem.chem.calculation_input import input_fingerprint, resolve_calculation_input
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.calculator import DRAWING, GEOMETRY
    from openchem.events.base import EventBus
    from openchem.services.project_service import ProjectService

    path = pathlib.Path(__file__).resolve().parent / "fixtures" / "projects" / "master_charge_consumers.ocsproj"
    project, store = ProjectService(EventBus()).load_document(path)
    engine = ChemistryEngine()
    (molecule,) = project.molecules
    (conformer,) = molecule.conformers
    assert conformer.drawing_atom_ids is None  # an older project records no map, and says nothing false

    current = {kind: input_fingerprint(engine, molecule, kind) for kind in (DRAWING, GEOMETRY)}
    stored = {s.identity.producer: s for s in store.fresh_results(molecule.uuid, current)}
    assert set(stored) == {"dipole_moment", "geometry_partial_charge"}  # both still fresh on this branch
    dipole = stored["dipole_moment"]

    defaults = {p.name: p.default for p in _registry().get("dipole_moment").parameters}
    rerun = compute_dipole_moment(resolve_calculation_input(engine, molecule, GEOMETRY).mol, molecule.uuid, defaults)
    old = dipole.result
    assert rerun.provenance.parameters["debye"] == old.provenance.parameters["debye"]
    assert rerun.provenance.parameters["vector"] == old.provenance.parameters["vector"]
    assert rerun.name == old.name and rerun.provenance.method == old.provenance.method
    assert [f.display_value for f in rerun.facts][: len(old.facts)] == [f.display_value for f in old.facts]
    assert len(rerun.facts) == len(old.facts) + 1  # the pre-registered benchmark sentence, and nothing else

    charges = stored["geometry_partial_charge"].result
    projection = project_to_drawing(engine, molecule, charges)
    assert projection.policy == POLICY_GRAPH_UNIQUE
    drawn = engine.mol_from_model(molecule)
    assert projection.values == {i: charges.values[i] for i in range(drawn.GetNumAtoms())}


@pytest.mark.parametrize("model", cev.CHARGE_MODELS)
def test_every_dipole_through_the_dispatcher_has_complete_provenance(model):
    """The persistence-side rule: what the dispatcher stores is attributable, per model."""
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.molecule import MoleculeModel
    from openchem.services.descriptor_service import _with_geometry_provenance
    from openchem.domain.calculator import GEOMETRY
    from openchem.domain.conformer import ConformerModel

    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    molecule.conformers = [ConformerModel(molblock=Chem.MolToMolBlock(_conformer("CCO")), energy=0.0)]
    parameters = {"charge_model": model, "decimal_places": 2}
    mol = engine.mol_from_molblock(molecule.conformers[0].molblock)
    result = _with_geometry_provenance(compute_dipole_moment(mol, molecule.uuid, parameters), molecule, GEOMETRY, parameters)
    assert cev.provenance_problems(result) == []


def test_a_refused_request_stores_an_inapplicable_result_with_no_values():
    from openchem.domain.result_status import INAPPLICABLE, status_of

    result = compute_dipole_moment(_conformer("Clc1ccccc1"), "u", {"charge_model": cev.EEM})
    assert status_of(result) == INAPPLICABLE
    assert cev.provenance_problems(result) == []


def test_the_completeness_predicate_catches_a_missing_field_and_a_value_on_a_refusal():
    """Guard on the guard: it must be able to fail."""
    import dataclasses

    from openchem.domain.common import Provenance

    good = compute_dipole_moment(_conformer("CCO"), "u", {"charge_model": cev.EEM})
    stripped = dict(good.provenance.parameters)
    del stripped["charge_parameter_checksum"]
    assert "charge_parameter_checksum" in cev.provenance_problems(dataclasses.replace(good, provenance=Provenance(created_by="core", method="x", parameters=stripped)))
    refused = compute_dipole_moment(_conformer("Clc1ccccc1"), "u", {"charge_model": cev.EEM})
    leaked = {**refused.provenance.parameters, "debye": 1.23}
    assert cev.provenance_problems(dataclasses.replace(refused, provenance=Provenance(created_by="core", method="x", parameters=leaked)))


def test_an_unknown_model_is_an_error_not_a_default():
    with pytest.raises(ValueError):
        cev.evaluate_charges(_conformer("CCO"), "Gasteiger (PEOE)")
