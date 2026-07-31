from __future__ import annotations

import time

from PySide6.QtCore import QThreadPool

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import AlignmentJobStateChanged, EnsembleAlignmentReady
from openchem.services.alignment_service import AlignmentService
from openchem.services.job_manager import JobManager

IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
NAPROXEN = "COc1ccc2cc(ccc2c1)C(C)C(=O)O"


def _drain(qapp, iterations: int = 50) -> None:
    QThreadPool.globalInstance().waitForDone(20000)
    for _ in range(iterations):
        qapp.processEvents()


def _molecule(engine: ChemistryEngine, smiles: str, name: str) -> MoleculeModel:
    model = MoleculeModel(display_name=name)
    engine.set_structure_from_smiles(model, smiles)
    return model


def test_alignment_job_lifecycle_reaches_completed(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = AlignmentService(bus, engine)

    reference = _molecule(engine, IBUPROFEN, "ibuprofen")
    probe = _molecule(engine, NAPROXEN, "naproxen")

    states: list[CacheState] = []
    results: list[EnsembleAlignmentReady] = []
    bus.subscribe(AlignmentJobStateChanged, lambda e: states.append(e.state))
    bus.subscribe(EnsembleAlignmentReady, results.append)

    service.request_alignment(reference, [probe], accuracy="Fast")
    _drain(qapp)

    assert states[0] == CacheState.QUEUED
    assert states[-1] == CacheState.COMPLETED
    assert len(results) == 1
    assert [entry.label for entry in results[0].entries] == [
        "ibuprofen (reference)",
        "naproxen",
    ]


def test_empty_probe_list_fails_with_a_message_instead_of_running(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = AlignmentService(bus, engine)

    events: list[AlignmentJobStateChanged] = []
    bus.subscribe(AlignmentJobStateChanged, events.append)

    service.request_alignment(_molecule(engine, IBUPROFEN, "ibuprofen"), [], accuracy="Fast")
    _drain(qapp)

    assert [event.state for event in events] == [CacheState.FAILED]
    assert "at least one" in events[0].message


def test_a_second_run_against_the_same_reference_is_refused_while_one_is_active(qapp):
    """JobManager's single-flight guard, exercised through this service --
    the same protection conformer generation and docking already have."""
    bus = EventBus()
    engine = ChemistryEngine()
    job_manager = JobManager()
    service = AlignmentService(bus, engine, job_manager=job_manager)

    reference = _molecule(engine, IBUPROFEN, "ibuprofen")
    # Occupy the slot directly rather than racing a real alignment: the
    # guard is what's under test, not the timing.
    assert job_manager.try_start("alignment", reference.uuid)

    events: list[AlignmentJobStateChanged] = []
    bus.subscribe(AlignmentJobStateChanged, events.append)
    service.request_alignment(reference, [_molecule(engine, NAPROXEN, "naproxen")], accuracy="Fast")

    assert [event.state for event in events] == [CacheState.FAILED]
    assert "already running" in events[0].message


def test_cancelling_stops_the_run_and_reports_it(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    job_manager = JobManager()
    service = AlignmentService(bus, engine, job_manager=job_manager)

    reference = _molecule(engine, IBUPROFEN, "ibuprofen")
    # Enough probes at the slowest accuracy that the run is still going
    # when cancel lands. Cancellation is checked BETWEEN molecules, so a
    # single-probe run would usually finish before the test could cancel.
    probes = [_molecule(engine, NAPROXEN, f"naproxen-{i}") for i in range(6)]

    events: list[AlignmentJobStateChanged] = []
    results: list[EnsembleAlignmentReady] = []
    bus.subscribe(AlignmentJobStateChanged, events.append)
    bus.subscribe(EnsembleAlignmentReady, results.append)

    service.request_alignment(reference, probes, accuracy="Accurate")
    deadline = time.time() + 10
    while time.time() < deadline and not any(e.state == CacheState.RUNNING for e in events):
        qapp.processEvents()
        time.sleep(0.01)
    job_manager.cancel("alignment", reference.uuid)
    _drain(qapp)

    assert events[-1].state == CacheState.FAILED
    assert events[-1].message == "Cancelled by user"
    # A cancelled run reports no partial ensemble, matching the convention
    # conformer generation and docking already follow.
    assert results == []
    assert not job_manager.is_active("alignment", reference.uuid)
