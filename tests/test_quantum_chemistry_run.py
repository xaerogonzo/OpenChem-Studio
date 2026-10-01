"""QuantumChemistryRun / QuantumChemistryRunStore -- the durable, per-run
QC history collection, deliberately separate from SessionResultStore.

Its own module docstring explains why it exists at all: SessionResultStore
is a bounded revision cache that prunes anything whose fingerprint no longer
matches the molecule's current structure, and its storage key has no room
for a calculation's method/basis. These tests are about the two properties
that store cannot give a QC run: surviving a structure edit, and keeping two
executions of the identical calculation as two separate history entries.
"""

from __future__ import annotations

from openchem.domain.descriptor import DescriptorValue
from openchem.domain.quantum_chemistry_run import (
    OutputStatus,
    QuantumChemistryRun,
    QuantumChemistryRunStore,
    RunStatus,
    new_run_id,
)
from openchem.domain.scientific_result import NMRSpectrumResult


def _descriptor(descriptor_id: str, value: float) -> DescriptorValue:
    return DescriptorValue(
        descriptor_id=descriptor_id,
        name=descriptor_id,
        units="eV",
        category="quantum_chemistry",
        provider="orca",
        molecule_uuid="mol-1",
        value=value,
    )


def _spectrum(values: dict[int, float]) -> NMRSpectrumResult:
    return NMRSpectrumResult(
        spectrum_type="nmr_1h",
        name="1H NMR",
        units="ppm",
        method="orca",
        molecule_uuid="mol-1",
        values=values,
    )


def _completed_run(
    run_id: str | None = None,
    *,
    method_basis: str = "B3LYP def2-SVP",
    molblock: str = "mol A",
    fingerprint: str = "fp-a",
    status: RunStatus = RunStatus.COMPLETED,
) -> QuantumChemistryRun:
    run = QuantumChemistryRun(
        run_id=run_id or new_run_id(),
        molecule_uuid="mol-1",
        calc_type="nmr",
        method_basis=method_basis,
        charge=0,
        multiplicity=1,
        calculation_input="geometry",
        input_fingerprint=fingerprint,
        input_molblock=molblock,
        status=RunStatus.RUNNING,
    )
    run.results["spectrum"] = _spectrum({0: 1.23})
    run.results["descriptors"] = [_descriptor("orca.scf_energy", -154.9)]
    run.output_status["spectrum"] = OutputStatus.AVAILABLE
    run.status = status
    run.completed_at = run.started_at + 1.0
    return run


def test_a_run_round_trips_through_to_dict_and_from_dict():
    run = _completed_run()

    restored = QuantumChemistryRun.from_dict(run.to_dict())

    assert restored is not None
    assert restored.run_id == run.run_id
    assert restored.status is RunStatus.COMPLETED
    assert restored.method_basis == "B3LYP def2-SVP"
    assert isinstance(restored.results["spectrum"], NMRSpectrumResult)
    assert restored.results["spectrum"].values == {0: 1.23}
    assert restored.results["descriptors"][0].descriptor_id == "orca.scf_energy"
    assert restored.output_status["spectrum"] is OutputStatus.AVAILABLE


def test_the_store_refuses_a_non_terminal_run():
    store = QuantumChemistryRunStore("proj-1")
    running = _completed_run(status=RunStatus.RUNNING)

    store.record(running)

    assert store.runs_for("mol-1") == []


def test_the_store_persists_a_run_whose_fingerprint_no_longer_matches_the_molecule():
    """The exact case SessionResultStore.to_dict()'s current-fingerprint
    pruning would drop: run NMR on structure A, edit to structure B, run IR
    on B, save/reload -- both runs must still be there. This store never
    takes a current_fingerprints argument at all, unlike that one."""
    store = QuantumChemistryRunStore("proj-1")
    run_a = _completed_run(molblock="benzene", fingerprint="fp-benzene")
    run_b = _completed_run(molblock="toluene", fingerprint="fp-toluene")
    store.record(run_a)
    store.record(run_b)

    restored = QuantumChemistryRunStore.from_dict(store.to_dict(), "proj-1")

    runs = {r.run_id: r for r in restored.runs_for("mol-1")}
    assert set(runs) == {run_a.run_id, run_b.run_id}
    assert runs[run_a.run_id].input_molblock == "benzene"
    assert runs[run_b.run_id].input_molblock == "toluene"


def test_the_same_calculation_run_twice_is_two_history_entries():
    """parameters_key/input_fingerprint alone cannot tell two executions of
    the identical calculation apart -- run_id is what does, and it must be
    minted per submission (see QuantumChemistryRun's docstring), not
    derived from the calculation's inputs."""
    store = QuantumChemistryRunStore("proj-1")
    run_1 = _completed_run(method_basis="B3LYP def2-SVP")
    run_2 = _completed_run(method_basis="B3LYP def2-SVP")

    store.record(run_1)
    store.record(run_2)

    assert run_1.run_id != run_2.run_id
    assert {r.run_id for r in store.runs_for("mol-1")} == {run_1.run_id, run_2.run_id}


def test_runs_for_orders_newest_first():
    store = QuantumChemistryRunStore("proj-1")
    older = _completed_run()
    older.started_at = 100.0
    newer = _completed_run()
    newer.started_at = 200.0
    store.record(older)
    store.record(newer)

    ordered = store.runs_for("mol-1")

    assert [r.run_id for r in ordered] == [newer.run_id, older.run_id]


def test_delete_removes_only_the_named_run():
    store = QuantumChemistryRunStore("proj-1")
    keep = _completed_run()
    remove = _completed_run()
    store.record(keep)
    store.record(remove)

    deleted = store.delete(remove.run_id)

    assert deleted is True
    assert {r.run_id for r in store.runs_for("mol-1")} == {keep.run_id}
    assert store.get(remove.run_id) is None


def test_delete_of_an_unknown_run_id_reports_false():
    store = QuantumChemistryRunStore("proj-1")

    assert store.delete("does-not-exist") is False


def test_get_finds_a_run_across_molecules():
    store = QuantumChemistryRunStore("proj-1")
    run = _completed_run()
    store.record(run)

    assert store.get(run.run_id) is run


def test_a_run_saved_by_a_newer_envelope_version_is_ignored():
    store = QuantumChemistryRunStore("proj-1")
    store.record(_completed_run())
    data = store.to_dict()
    data["envelope_version"] = 999

    restored = QuantumChemistryRunStore.from_dict(data, "proj-1")

    assert restored.runs_for("mol-1") == []


def test_a_foreign_project_block_is_ignored():
    store = QuantumChemistryRunStore("proj-1")
    store.record(_completed_run())
    data = store.to_dict()

    restored = QuantumChemistryRunStore.from_dict(data, "proj-2")

    assert restored.runs_for("mol-1") == []


def test_a_damaged_entry_does_not_break_loading_the_rest():
    store = QuantumChemistryRunStore("proj-1")
    good = _completed_run()
    store.record(good)
    data = store.to_dict()
    data["runs"].append({"run_id": "broken", "status": "completed"})  # missing required fields

    restored = QuantumChemistryRunStore.from_dict(data, "proj-1")

    assert {r.run_id for r in restored.runs_for("mol-1")} == {good.run_id}


def test_from_dict_with_no_data_gives_an_empty_store():
    store = QuantumChemistryRunStore.from_dict(None, "proj-1")

    assert store.runs_for("mol-1") == []


def test_a_run_saved_with_a_non_terminal_status_does_not_load():
    """RUNNING is never written to a project file, but a hand-edited or
    future-version file could contain one -- it must not resurrect as a
    live-looking job on load."""
    run = _completed_run()
    data = run.to_dict()
    data["status"] = "running"

    assert QuantumChemistryRun.from_dict(data) is None


def test_warnings_and_completed_with_warnings_status_round_trip():
    run = _completed_run(status=RunStatus.COMPLETED_WITH_WARNINGS)
    run.warnings.append("Spin-spin coupling output could not be parsed")

    restored = QuantumChemistryRun.from_dict(run.to_dict())

    assert restored is not None
    assert restored.status is RunStatus.COMPLETED_WITH_WARNINGS
    assert restored.warnings == ["Spin-spin coupling output could not be parsed"]


def test_log_is_never_retained_by_default():
    run = _completed_run()

    assert run.log_retained is False
    restored = QuantumChemistryRun.from_dict(run.to_dict())
    assert restored is not None
    assert restored.log_retained is False


def test_output_conformer_and_surface_cache_reference_round_trip():
    run = _completed_run()
    run.output_conformer_id = "conf-42"
    run.surface_cache_key = "cache-key-abc"

    restored = QuantumChemistryRun.from_dict(run.to_dict())

    assert restored is not None
    assert restored.output_conformer_id == "conf-42"
    assert restored.surface_cache_key == "cache-key-abc"
