from __future__ import annotations

from PySide6.QtCore import QThreadPool

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformerJobStateChanged, ConformersReady
from openchem.services.conformer_service import ConformerService


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
