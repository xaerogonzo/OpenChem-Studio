"""Settings cap for fingerprint-mismatched property executions."""

from __future__ import annotations

from openchem.app.settings import (
    MAX_HISTORICAL_PROPERTY_EXECUTIONS,
    MAX_REVISIONS_KEPT,
    Settings,
)
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import DRAWING, GEOMETRY
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.property_execution import (
    ExecutionStatus,
    PropertyExecution,
    PropertyExecutionStore,
)
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, QuantumChemistryRunStore, RunStatus, new_run_id
from openchem.domain.result_store import ResultIdentity, SessionResultStore, StoredResult
from openchem.domain.scientific_result import PerAtomDataset
from openchem.events.base import EventBus
from openchem.events.events import (
    CHANGE_CALCULATION_INPUT,
    CHANGE_IDENTITY,
    CHANGE_LAYOUT,
    CHANGE_STRUCTURE,
    ConformersChanged,
    MoleculeChanged,
    PropertyExecutionDeleted,
    ResultRecorded,
)
from openchem.services.result_store_service import ResultStoreService


def _history(
    *,
    execution_id: str,
    molecule: str = "m1",
    fingerprint: str = "old",
    started_at: float = 1.0,
    calculation_input: str = "drawing",
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
        status=ExecutionStatus.COMPLETED,
    )


def _cache_row(fingerprint: str, molecule_uuid: str = "m1") -> StoredResult:
    return StoredResult(
        identity=ResultIdentity(molecule_uuid, "shape", DRAWING, fingerprint, "producer"),
        result=PerAtomDataset(
            property_id="shape", name="shape", units="", method="",
            molecule_uuid=molecule_uuid, values={0: 1.0}, cache_state=CacheState.COMPLETED,
        ),
    )


def _qc_run(molecule_uuid: str = "m1") -> QuantumChemistryRun:
    return QuantumChemistryRun(
        run_id=new_run_id(),
        molecule_uuid=molecule_uuid,
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


def _capped_service(limit=1, molecules=("m1",)):
    bus = EventBus()
    settings = Settings(bus)
    settings.set_preference(MAX_HISTORICAL_PROPERTY_EXECUTIONS, limit)
    service = ResultStoreService(bus, ChemistryEngine(), settings)
    project = ProjectModel(name="cap")
    for uuid in molecules:
        project.molecules.append(MoleculeModel(uuid=uuid, display_name=uuid))
    service.set_project(project)
    service.fingerprints_for = lambda _model: {DRAWING: "now", GEOMETRY: "now"}
    return service, settings, bus


def test_set_project_does_not_trim_historical_executions():
    service, _settings, _bus = _capped_service(1)
    store = PropertyExecutionStore(service._project.uuid)
    for index in range(3):
        store.record(_history(execution_id=f"h{index}", started_at=float(index)))
    service.set_project(service._project, property_executions=store)
    service.fingerprints_for = lambda _model: {DRAWING: "now", GEOMETRY: "now"}
    assert len(service.property_executions.executions_for("m1")) == 3
    dropped = service.trim_historical_property_executions()
    assert dropped == ["h0", "h1"]
    assert [e.execution_id for e in service.property_executions.executions_for("m1")] == ["h2"]


def test_structure_and_calculation_input_trim_that_molecule():
    service, _settings, bus = _capped_service(1, molecules=("m1", "m2"))
    for index in range(3):
        service.property_executions.record(
            _history(execution_id=f"a{index}", started_at=float(index))
        )
        service.property_executions.record(
            _history(execution_id=f"b{index}", molecule="m2", started_at=float(index))
        )
    bus.publish(MoleculeChanged(molecule_uuid="m1", kind=CHANGE_IDENTITY))
    bus.publish(MoleculeChanged(molecule_uuid="m1", kind=CHANGE_LAYOUT))
    assert len(service.property_executions.executions_for("m1")) == 3
    bus.publish(MoleculeChanged(molecule_uuid="m1", kind=CHANGE_STRUCTURE))
    assert [e.execution_id for e in service.property_executions.executions_for("m1")] == ["a2"]
    assert len(service.property_executions.executions_for("m2")) == 3
    bus.publish(MoleculeChanged(molecule_uuid="m2", kind=CHANGE_CALCULATION_INPUT))
    assert [e.execution_id for e in service.property_executions.executions_for("m2")] == ["b2"]


def test_conformers_changed_trims_geometry_history():
    service, _settings, bus = _capped_service(1)
    service.property_executions.record(
        _history(execution_id="g0", calculation_input="geometry", started_at=0.0)
    )
    service.property_executions.record(
        _history(execution_id="g1", calculation_input="geometry", started_at=1.0)
    )
    service.property_executions.record(
        _history(execution_id="d0", calculation_input="drawing", fingerprint="now", started_at=2.0)
    )
    bus.publish(ConformersChanged(molecule_uuid="m1"))
    ids = {e.execution_id for e in service.property_executions.executions_for("m1")}
    assert ids == {"g1", "d0"}


def test_late_recorded_result_is_eligible_for_the_cap():
    service, _settings, bus = _capped_service(1)
    service.property_executions.record(_history(execution_id="old-a", started_at=0.0))
    service.property_executions.record(_history(execution_id="old-b", started_at=1.0))
    stored = StoredResult(
        identity=ResultIdentity(
            molecule_uuid="m1",
            result_id="geometry_partial_charge",
            calculation_input="drawing",
            input_fingerprint="old",
            producer="geometry_partial_charge",
            parameters_key="eem",
        ),
        result=PerAtomDataset(
            property_id="geometry_partial_charge",
            name="Partial Charge",
            units="e",
            method="eem",
            molecule_uuid="m1",
            values={0: 0.1},
        ),
    )
    bus.publish(ResultRecorded(stored=stored))
    held = service.property_executions.executions_for("m1")
    assert len(held) == 1
    assert held[0].execution_id != "old-a"


def test_missing_live_fingerprint_preserves_that_input():
    service, _settings, _bus = _capped_service(1)
    service.fingerprints_for = lambda _model: {DRAWING: "now"}
    for index in range(3):
        service.property_executions.record(
            _history(
                execution_id=f"g{index}",
                calculation_input="geometry",
                started_at=float(index),
            )
        )
    assert service.trim_historical_property_executions("m1") == []
    assert len(service.property_executions.executions_for("m1")) == 3


def test_one_deleted_event_per_id_and_one_listener_per_molecule():
    service, _settings, bus = _capped_service(1, molecules=("m1", "m2"))
    deleted = []
    recorded = []
    bus.subscribe(PropertyExecutionDeleted, lambda event: deleted.append(event.execution_id))
    service.add_recorded_listener(recorded.append)
    for index in range(3):
        service.property_executions.record(
            _history(execution_id=f"a{index}", started_at=float(index))
        )
        service.property_executions.record(
            _history(execution_id=f"b{index}", molecule="m2", started_at=float(index))
        )
    dropped = service.trim_historical_property_executions()
    assert set(dropped) == {"a0", "a1", "b0", "b1"}
    assert deleted == dropped
    assert set(recorded) == {"m1", "m2"}
    assert recorded.count("m1") == 1 and recorded.count("m2") == 1


def test_cache_and_quantum_stores_are_untouched_by_the_historical_cap():
    service, settings, _bus = _capped_service(1)
    for index in range(6):
        service.store.put(_cache_row(f"d{index}"))
    run = _qc_run()
    service.qc_runs.record(run)
    service.property_executions.record(_history(execution_id="h0", started_at=0.0))
    service.property_executions.record(_history(execution_id="h1", started_at=1.0))
    cache_before = service.store.revisions_beyond(0)
    service.trim_historical_property_executions()
    assert service.store.revisions_beyond(0) == cache_before
    assert service.qc_runs.get(run.run_id) is not None
    assert len(service.property_executions.executions_for("m1")) == 1

    settings.set_preference(MAX_REVISIONS_KEPT, 2)
    assert service.store.revisions_beyond(0)[0] == 2
    assert len(service.property_executions.executions_for("m1")) == 1
    settings.set_preference(MAX_HISTORICAL_PROPERTY_EXECUTIONS, 1)
    assert service.store.revisions_beyond(0)[0] == 2


def test_trim_pushes_nothing_onto_undo(qapp, tmp_path):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none"))
    settings.set_preference(MAX_HISTORICAL_PROPERTY_EXECUTIONS, 1)
    window = MainWindow(services, settings, SessionManager())
    window.hide()
    project = ProjectModel(name="loaded")
    molecule = MoleculeModel(uuid="m1", display_name="m")
    project.molecules.append(molecule)
    store = PropertyExecutionStore(project.uuid)
    for index in range(3):
        store.record(_history(execution_id=f"h{index}", started_at=float(index)))
    window._set_project(project, property_executions=store)
    held = services.result_store_service.property_executions.executions_for("m1")
    assert len(held) == 1
    assert window._session.is_dirty
    assert window._undo_stack.count() == 0
    window.close()
