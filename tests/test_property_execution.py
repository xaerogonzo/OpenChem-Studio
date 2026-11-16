"""Property-execution history is not the result cache."""

from __future__ import annotations

from openchem.domain.history_compare import property_executions_comparable, quantum_runs_comparable
from openchem.domain.property_execution import (
    ExecutionStatus,
    PropertyExecution,
    PropertyExecutionStore,
    execution_from_stored,
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


def test_quantum_engine_mismatch_is_refused_when_functional_name_matches():
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

    message = quantum_runs_comparable(run("orca"), run("psi4"))
    assert "different programs" in message


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


def test_failed_execution_is_persisted():
    stored = _stored()
    execution = execution_from_stored(stored, status=ExecutionStatus.FAILED)
    store = PropertyExecutionStore("project")
    store.record(execution)
    assert store.get(execution.execution_id).status is ExecutionStatus.FAILED
