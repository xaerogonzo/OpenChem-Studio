"""Property-execution history is not the result cache."""

from __future__ import annotations

from dataclasses import replace

import pytest

from openchem.domain.history_compare import property_executions_comparable, quantum_runs_comparable
from openchem.domain.property_execution import (
    ExecutionStatus,
    PropertyExecution,
    PropertyExecutionStore,
    execution_from_stored,
    historical_beyond,
    ids_to_drop_historical,
    is_historical,
)
from openchem.domain.quantum_chemistry_run import OutputStatus, QuantumChemistryRun, RunStatus, new_run_id
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.scientific_result import PerAtomDataset


def _stored(*, molecule="m1", result_id="geometry_partial_charge", producer="geometry_partial_charge",
            fingerprint="fp-a", parameters_key="eem", method="eem") -> StoredResult:
    dataset = PerAtomDataset(
        property_id=result_id,
        name="Partial Charge (3D)",
        units="e",
        method=method,
        molecule_uuid=molecule,
        values={0: 0.1, 1: -0.1},
    )
    return StoredResult(
        identity=ResultIdentity(
            molecule_uuid=molecule,
            result_id=result_id,
            calculation_input="geometry",
            input_fingerprint=fingerprint,
            producer=producer,
            parameters_key=parameters_key,
        ),
        result=dataset,
    )


def test_two_methods_occupy_two_slots():
    store = PropertyExecutionStore("project")
    eem = execution_from_stored(_stored(parameters_key="eem", method="eem"))
    qeq = execution_from_stored(_stored(parameters_key="qeq", method="qeq"))
    store.record(eem)
    store.record(qeq)
    held = store.executions_for("m1")
    assert {e.method_model for e in held} == {"eem", "qeq"}
    assert eem.execution_id != qeq.execution_id


def test_identical_repeat_mints_a_new_id():
    first = execution_from_stored(_stored())
    second = execution_from_stored(_stored())
    assert first.execution_id != second.execution_id


def test_delete_one_method_leaves_the_other():
    store = PropertyExecutionStore("project")
    eem = execution_from_stored(_stored(parameters_key="eem", method="eem"))
    qeq = execution_from_stored(_stored(parameters_key="qeq", method="qeq"))
    store.record(eem)
    store.record(qeq)
    assert store.delete(eem.execution_id)
    left = store.executions_for("m1")
    assert [e.method_model for e in left] == ["qeq"]


def test_round_trip_keeps_a_run_after_the_fingerprint_moves():
    store = PropertyExecutionStore("project")
    execution = execution_from_stored(_stored(fingerprint="old-geom"))
    store.record(execution)
    restored = PropertyExecutionStore.from_dict(store.to_dict(), "project")
    held = restored.get(execution.execution_id)
    assert held is not None
    assert held.input_fingerprint == "old-geom"
    assert not held.matches_current({"geometry": "new-geom"})


def test_older_app_ignores_unknown_envelope():
    raw = {"envelope_version": 99, "project_uuid": "project", "executions": [{"execution_id": "x"}]}
    store = PropertyExecutionStore.from_dict(raw, "project")
    assert store.executions_for("m1") == []


def test_per_atom_cross_molecule_compare_is_refused():
    left = execution_from_stored(_stored(molecule="a"))
    right = execution_from_stored(_stored(molecule="b"))
    assert "different molecules" in property_executions_comparable(left, right)


def test_quantum_engines_with_the_same_functional_name_are_comparable():
    def run(provider: str, molecule="m") -> QuantumChemistryRun:
        return QuantumChemistryRun(
            run_id=new_run_id(),
            molecule_uuid=molecule,
            calc_type="sp",
            method_basis="B3LYP def2-SVP",
            charge=0,
            multiplicity=1,
            calculation_input="geometry",
            input_fingerprint="fp",
            input_molblock="",
            provider=provider,
            status=RunStatus.COMPLETED,
            completed_at=1.0,
            results={"descriptors": []},
            output_status={"descriptors": OutputStatus.AVAILABLE},
        )

    assert quantum_runs_comparable(run("orca"), run("psi4")) == ""


def test_project_file_keeps_executions_after_the_fingerprint_moves():
    import json

    from openchem.domain.project import ProjectModel
    from openchem.events.base import EventBus
    from openchem.services.project_service import ProjectService

    project = ProjectModel(name="history")
    store = PropertyExecutionStore(project.uuid)
    execution = execution_from_stored(_stored(fingerprint="old-geom"))
    store.record(execution)
    text = ProjectService(EventBus()).serialise(project, property_executions=store)
    document = ProjectService(EventBus()).parse(json.loads(text))
    held = document.property_executions.get(execution.execution_id)
    assert held is not None
    assert held.input_fingerprint == "old-geom"


def test_newest_current_execution_is_skipped_when_the_live_reader_already_shows_it():
    from openchem.ui.history_entries import history_reader_entries, skip_current_duplicate_ids

    current = execution_from_stored(_stored(parameters_key="eem", method="eem", fingerprint="now"))
    older = execution_from_stored(_stored(parameters_key="qeq", method="qeq", fingerprint="now"))
    historical = execution_from_stored(_stored(parameters_key="eem", method="eem", fingerprint="then"))
    fps = {"geometry": "now"}
    skip = skip_current_duplicate_ids([current, older, historical], fps, {"geometry_partial_charge"})
    assert current.execution_id in skip
    assert older.execution_id not in skip
    assert historical.execution_id not in skip
    entries = history_reader_entries(
        [current, older, historical],
        [],
        fingerprints=fps,
        structure_version=3,
        live_result_ids={"geometry_partial_charge"},
    )
    ids = {getattr(e, "history_id", "") for e in entries}
    assert historical.execution_id in ids
    assert older.execution_id in ids
    assert current.execution_id not in ids
    historical_row = next(e for e in entries if e.history_id == historical.execution_id)
    assert historical_row.historical
    assert historical_row.report_id.startswith("exec:")


def test_quantum_run_is_listed_with_its_run_id():
    from openchem.ui.history_entries import entry_from_quantum_run

    run = QuantumChemistryRun(
        run_id=new_run_id(),
        molecule_uuid="m1",
        calc_type="nmr",
        method_basis="B3LYP def2-SVP",
        charge=0,
        multiplicity=1,
        calculation_input="geometry",
        input_fingerprint="old",
        input_molblock="",
        provider="orca",
        status=RunStatus.COMPLETED,
        completed_at=1.0,
        results={},
        output_status={},
    )
    entry = entry_from_quantum_run(run, {"geometry": "new"}, structure_version=2)
    assert entry.report_id == f"qc:{run.run_id}"
    assert run.run_id[:8] in entry.name
    assert entry.historical
    assert entry.history_kind == "quantum"


def test_cache_put_key_still_omits_parameters_key():
    import inspect

    from openchem.domain.result_store import SessionResultStore

    source = inspect.getsource(SessionResultStore.put)
    key_block = source.split("key =", 1)[1].split("previous", 1)[0]
    assert "parameters_key" not in key_block
    assert "source_run_id" not in key_block


def test_failed_execution_is_persisted():
    stored = _stored()
    execution = execution_from_stored(stored, status=ExecutionStatus.FAILED)
    store = PropertyExecutionStore("project")
    store.record(execution)
    assert store.get(execution.execution_id).status is ExecutionStatus.FAILED


def _recording_service(molecule_uuid="m1"):
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.molecule import MoleculeModel
    from openchem.domain.project import ProjectModel
    from openchem.events.base import EventBus
    from openchem.services.result_store_service import ResultStoreService

    project = ProjectModel(name="history")
    molecule = MoleculeModel(uuid=molecule_uuid, display_name="m")
    project.molecules.append(molecule)
    service = ResultStoreService(EventBus(), ChemistryEngine())
    service.set_project(project)
    return service


def test_identical_cache_hit_still_mints_an_execution():
    from openchem.events.events import ResultRecorded

    service = _recording_service()
    stored = _stored()
    service._event_bus.publish(ResultRecorded(stored=stored))
    service._event_bus.publish(ResultRecorded(stored=stored))
    held = service.property_executions.executions_for("m1")
    assert len(held) == 2
    assert held[0].execution_id != held[1].execution_id


def test_failed_family_row_is_identifiable_by_method():
    from openchem.domain.common import CacheState
    from openchem.domain.property_execution import method_model_of

    method = "eem_ionescu2013_e_mpa_631gs_gas"
    dataset = PerAtomDataset(
        property_id="geometry_partial_charge",
        name="geometry_partial_charge",
        units="",
        method=method,
        molecule_uuid="m1",
        values={},
        cache_state=CacheState.FAILED,
        error="outside the parameter set",
    )
    stored = StoredResult(
        identity=ResultIdentity(
            molecule_uuid="m1",
            result_id="geometry_partial_charge",
            calculation_input="geometry",
            input_fingerprint="fp",
            producer="geometry_partial_charge",
            parameters_key="not-a-blank-hash-only",
        ),
        result=dataset,
    )
    execution = execution_from_stored(stored)
    assert execution.method_model == method
    assert method_model_of(stored) == method
    assert execution.status is ExecutionStatus.FAILED


def test_generic_failed_path_falls_back_to_parameters_key():
    from openchem.domain.common import CacheState
    from openchem.domain.property_execution import method_model_of

    dataset = PerAtomDataset(
        property_id="geometry_partial_charge",
        name="geometry_partial_charge",
        units="",
        method="",
        molecule_uuid="m1",
        values={},
        cache_state=CacheState.FAILED,
        error="crashed",
    )
    stored = StoredResult(
        identity=ResultIdentity(
            molecule_uuid="m1",
            result_id="geometry_partial_charge",
            calculation_input="geometry",
            input_fingerprint="fp",
            producer="geometry_partial_charge",
            parameters_key="method=eem_bultinck2002_part1",
        ),
        result=dataset,
    )
    assert method_model_of(stored) == "method=eem_bultinck2002_part1"


def test_failed_result_is_recorded_as_a_failed_execution():
    from openchem.domain.common import CacheState
    from openchem.events.events import ResultRecorded

    base = _stored()
    stored = StoredResult(
        identity=base.identity,
        result=replace(base.result, cache_state=CacheState.FAILED, error="the method diverged"),
    )
    service = _recording_service()
    service._event_bus.publish(ResultRecorded(stored=stored))
    held = service.property_executions.executions_for("m1")
    assert len(held) == 1
    assert held[0].status is ExecutionStatus.FAILED
    assert "diverged" in held[0].error


def test_always_on_descriptors_are_not_history():
    from openchem.domain.common import CacheState
    from openchem.domain.descriptor import DescriptorValue
    from openchem.domain.property_execution import is_history_worthy
    from openchem.events.events import ResultRecorded

    descriptor = DescriptorValue(
        descriptor_id="MolWt",
        name="Molecular weight",
        units="g/mol",
        category="molecular",
        provider="rdkit",
        molecule_uuid="m1",
        value=18.0,
        cache_state=CacheState.COMPLETED,
    )
    stored = StoredResult(
        identity=ResultIdentity(
            molecule_uuid="m1",
            result_id="MolWt",
            calculation_input="drawing",
            input_fingerprint="fp",
            producer="rdkit",
        ),
        result=descriptor,
    )
    assert not is_history_worthy(stored)
    service = _recording_service()
    service._event_bus.publish(ResultRecorded(stored=stored))
    assert service.property_executions.executions_for("m1") == []
    assert service.store.all_results("m1")


def test_deleting_a_quantum_run_withdraws_its_cache_projection():
    from openchem.domain.descriptor import DescriptorValue
    from openchem.domain.quantum_chemistry_run import OutputStatus, QuantumChemistryRun, RunStatus, new_run_id
    from openchem.events.events import ResultRecorded

    run_id = new_run_id()
    descriptor = DescriptorValue(
        descriptor_id="orca.scf_energy",
        name="SCF energy",
        units="Eh",
        category="quantum",
        provider="orca",
        molecule_uuid="m1",
        value=-76.0,
    )
    stored = StoredResult(
        identity=ResultIdentity(
            molecule_uuid="m1",
            result_id="orca.scf_energy",
            calculation_input="geometry",
            input_fingerprint="fp",
            producer="orca",
            source_run_id=run_id,
        ),
        result=descriptor,
    )
    service = _recording_service()
    service.record_quantum_chemistry_run(
        QuantumChemistryRun(
            run_id=run_id,
            molecule_uuid="m1",
            calc_type="sp",
            method_basis="B3LYP def2-SVP",
            charge=0,
            multiplicity=1,
            calculation_input="geometry",
            input_fingerprint="fp",
            input_molblock="",
            status=RunStatus.COMPLETED,
            completed_at=1.0,
            results={"descriptors": [descriptor]},
            output_status={"descriptors": OutputStatus.AVAILABLE},
        )
    )
    service._event_bus.publish(ResultRecorded(stored=stored))
    assert service.store.all_results("m1")
    assert service.property_executions.executions_for("m1") == []
    assert service.delete_quantum_chemistry_run(run_id)
    assert service.store.all_results("m1") == []
    assert service.qc_runs.get(run_id) is None


def test_named_scalar_compare_is_a_table():
    from openchem.domain.history_compare import named_compare_rows, named_values_from_execution
    from openchem.domain.report import Fact, FactCategory, ReportResult
    from openchem.domain.structure_issue import Basis

    def report(value: float) -> StoredResult:
        result = ReportResult(
            report_id="solubility",
            name="Solubility",
            molecule_uuid="m1",
            facts=(
                Fact(
                    category=FactCategory.STRUCTURE,
                    label="logS",
                    value=value,
                    display_value=str(value),
                    source="solubility",
                    basis=Basis.DETERMINISTIC,
                ),
            ),
        )
        return StoredResult(
            identity=ResultIdentity(
                molecule_uuid="m1",
                result_id="solubility",
                calculation_input="drawing",
                input_fingerprint="fp",
                producer="solubility",
            ),
            result=result,
        )

    left = execution_from_stored(report(-0.5))
    right = execution_from_stored(report(-0.2))
    rows = named_compare_rows(named_values_from_execution(left), named_values_from_execution(right))
    assert rows
    assert rows[0].label == "logS"
    assert rows[0].delta == pytest.approx(0.3)


def test_opening_a_file_without_executions_does_not_invent_ids():
    import json

    from openchem.domain.project import ProjectModel
    from openchem.events.base import EventBus
    from openchem.services.project_service import ProjectService

    text = ProjectService(EventBus()).serialise(ProjectModel(name="old"))
    document = ProjectService(EventBus()).parse(json.loads(text))
    assert "property_executions" not in json.loads(text)
    assert document.property_executions.to_dict()["executions"] == []


def _history(
    *,
    execution_id: str = "x",
    molecule: str = "m1",
    fingerprint: str = "old",
    started_at: float = 1.0,
    calculation_input: str = "geometry",
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
) -> PropertyExecution:
    return PropertyExecution(
        execution_id=execution_id,
        molecule_uuid=molecule,
        producer="geometry_partial_charge",
        method_model="eem",
        parameters_key="k",
        calculation_input=calculation_input,
        input_fingerprint=fingerprint,
        started_at=started_at,
        completed_at=started_at,
        status=status,
    )


def test_missing_fingerprint_key_is_not_historical():
    execution = _history()
    assert not is_historical(execution, {})
    assert is_historical(execution, {"geometry": "new"})
    assert not is_historical(execution, {"geometry": "old"})


def test_current_repeats_are_never_selected_for_the_cap():
    store = PropertyExecutionStore("project")
    for i in range(8):
        store.record(_history(execution_id=f"c{i}", fingerprint="now", started_at=float(i)))
    store.record(_history(execution_id="old-a", fingerprint="was", started_at=0.0))
    store.record(_history(execution_id="old-b", fingerprint="was", started_at=0.5))
    fps = {"m1": {"geometry": "now"}}
    assert historical_beyond(store, fps, 1) == (1, 1)
    assert ids_to_drop_historical(store, fps, 1) == ["old-a"]
    assert ids_to_drop_historical(store, fps, 0) == []
    assert ids_to_drop_historical(store, fps, -1) == []


def test_oldest_historical_ids_are_stable_across_equal_timestamps():
    store = PropertyExecutionStore("project")
    store.record(_history(execution_id="z", fingerprint="was", started_at=1.0))
    store.record(_history(execution_id="a", fingerprint="was", started_at=1.0))
    store.record(_history(execution_id="m", fingerprint="was", started_at=2.0))
    fps = {"m1": {"geometry": "now"}}
    assert ids_to_drop_historical(store, fps, 1) == ["a", "z"]


def test_historical_cap_is_per_molecule_not_per_input():
    store = PropertyExecutionStore("project")
    store.record(_history(execution_id="g1", calculation_input="geometry", fingerprint="g-old", started_at=1.0))
    store.record(_history(execution_id="d1", calculation_input="drawing", fingerprint="d-old", started_at=2.0))
    store.record(_history(execution_id="g2", calculation_input="geometry", fingerprint="g-old", started_at=3.0))
    store.record(
        _history(execution_id="other", molecule="m2", fingerprint="g-old", started_at=0.0)
    )
    fps = {
        "m1": {"geometry": "g-now", "drawing": "d-now"},
        "m2": {"geometry": "g-now"},
    }
    assert ids_to_drop_historical(store, fps, 2) == ["g1"]
    assert historical_beyond(store, fps, 1) == (2, 1)
    assert "other" not in ids_to_drop_historical(store, {"m1": fps["m1"]}, 1)


def test_failed_and_cancelled_terminal_history_is_eligible():
    store = PropertyExecutionStore("project")
    store.record(
        _history(execution_id="fail", fingerprint="was", started_at=1.0, status=ExecutionStatus.FAILED)
    )
    store.record(
        _history(
            execution_id="cancel", fingerprint="was", started_at=2.0, status=ExecutionStatus.CANCELLED
        )
    )
    store.record(_history(execution_id="ok", fingerprint="was", started_at=3.0))
    fps = {"m1": {"geometry": "now"}}
    assert ids_to_drop_historical(store, fps, 1) == ["fail", "cancel"]
