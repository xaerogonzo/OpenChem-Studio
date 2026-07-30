from __future__ import annotations

from PySide6.QtCore import QThreadPool

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformerJobStateChanged, ConformersReady
from openchem.services.conformer_service import ConformerService
from openchem.services.job_manager import JobManager


def _drain(qapp, iterations: int = 50) -> None:
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(iterations):
        qapp.processEvents()


def test_conformer_job_lifecycle_reaches_completed(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(bus, engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    states: list[CacheState] = []
    bus.subscribe(ConformerJobStateChanged, lambda e: states.append(e.state))

    ready_payload = {}
    bus.subscribe(ConformersReady, lambda e: ready_payload.setdefault("conformers", e.conformers))

    service.request_conformers(model, num_conformers=3, optimize=True)
    _drain(qapp)

    assert CacheState.QUEUED in states
    assert CacheState.RUNNING in states
    assert states[-1] == CacheState.COMPLETED

    conformers = ready_payload["conformers"]
    assert len(conformers) == 3
    assert all(c.energy is not None for c in conformers)
    assert all(c.molblock for c in conformers)

    # The service must not have mutated the model directly.
    assert model.conformers == []


def test_conformer_job_failure_when_no_structure(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(bus, engine)
    model = MoleculeModel()  # no molblock

    states: list[CacheState] = []
    bus.subscribe(ConformerJobStateChanged, lambda e: states.append(e.state))

    service.request_conformers(model, num_conformers=2, optimize=False)
    _drain(qapp)

    assert states[-1] == CacheState.FAILED


def test_conformer_request_rejected_while_one_already_running(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    job_manager = JobManager()
    service = ConformerService(bus, engine, job_manager=job_manager)
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    # Simulate a job already in flight for this molecule without actually
    # scheduling one -- exercises the guard deterministically, no QRunnable
    # timing race needed.
    job_manager.try_start("conformer", model.uuid)

    states: list[CacheState] = []
    bus.subscribe(ConformerJobStateChanged, lambda e: states.append(e.state))

    service.request_conformers(model, num_conformers=3, optimize=True)

    assert states == [CacheState.FAILED]


def test_conformer_results_carry_provenance_and_round_trip(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(bus, engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    ready_payload = {}
    bus.subscribe(ConformersReady, lambda e: ready_payload.setdefault("conformers", e.conformers))

    service.request_conformers(model, num_conformers=2, optimize=True)
    _drain(qapp)

    conformers = ready_payload["conformers"]
    assert conformers
    for conformer in conformers:
        assert conformer.provenance is not None
        assert conformer.provenance.created_by == "core"
        assert conformer.provenance.method == "rdkit"
        assert conformer.provenance.parameters == {"num_conformers": 2, "optimize": True}

        round_tripped = type(conformer).from_dict(conformer.to_dict())
        assert round_tripped.provenance == conformer.provenance
