from __future__ import annotations

from PySide6.QtCore import QThreadPool
from rdkit import Chem

from openchem.domain.common import CacheState
from openchem.domain.docking import DockingBox, DockingPoseModel
from openchem.events.base import EventBus
from openchem.events.events import DockingJobStateChanged, DockingResultReady
from openchem.plugins.interfaces import DockingProvider
from openchem.services.docking_service import DockingService


class FakeDockingProvider(DockingProvider):
    provider_id = "fake"
    engine_id = "fake-engine"

    def __init__(self, raise_error: bool = False) -> None:
        self._raise_error = raise_error

    def engine_version(self) -> str:
        return "0.0.1"

    def dock(self, receptor_structure_text, receptor_source_format, ligand_mol, box, num_poses, progress):
        if self._raise_error:
            raise RuntimeError("docking blew up")
        progress.report(0.5, "Docking")
        return [
            DockingPoseModel(pose_molblock="fake molblock", binding_affinity_kcal_mol=-5.0, rmsd_lb=0.0, rmsd_ub=0.0)
        ]


def _drain(qapp, timeout_ms: int = 5000) -> None:
    QThreadPool.globalInstance().waitForDone(timeout_ms)
    for _ in range(50):
        qapp.processEvents()


def test_docking_job_lifecycle_reaches_completed(qapp):
    bus = EventBus()
    provider = FakeDockingProvider()
    service = DockingService(bus, providers={provider.provider_id: provider})

    states: list[CacheState] = []
    bus.subscribe(DockingJobStateChanged, lambda e: states.append(e.state))
    results = []
    bus.subscribe(DockingResultReady, lambda e: results.append(e.result))

    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))
    service.request_docking(
        ligand_molecule_uuid="lig-1",
        ligand_mol=Chem.MolFromSmiles("CCO"),
        receptor_macromolecule_uuid="rec-1",
        receptor_structure_text="ATOM ...",
        receptor_source_format="pdb",
        box=box,
        num_poses=9,
        provider_id="fake",
    )
    _drain(qapp)

    assert CacheState.QUEUED in states
    assert CacheState.RUNNING in states
    assert states[-1] == CacheState.COMPLETED

    assert len(results) == 1
    result = results[0]
    assert result.ligand_molecule_uuid == "lig-1"
    assert result.receptor_macromolecule_uuid == "rec-1"
    assert len(result.poses) == 1
    assert result.engine == "fake-engine"
    assert result.engine_version == "0.0.1"
    assert result.provenance.method == "fake"


def test_docking_job_failure_is_reported(qapp):
    bus = EventBus()
    provider = FakeDockingProvider(raise_error=True)
    service = DockingService(bus, providers={provider.provider_id: provider})

    states: list[CacheState] = []
    bus.subscribe(DockingJobStateChanged, lambda e: states.append(e.state))
    results = []
    bus.subscribe(DockingResultReady, lambda e: results.append(e.result))

    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))
    service.request_docking(
        ligand_molecule_uuid="lig-1",
        ligand_mol=Chem.MolFromSmiles("CCO"),
        receptor_macromolecule_uuid="rec-1",
        receptor_structure_text="ATOM ...",
        receptor_source_format="pdb",
        box=box,
        provider_id="fake",
    )
    _drain(qapp)

    assert states[-1] == CacheState.FAILED
    assert results == []


def test_docking_unknown_provider_fails_immediately(qapp):
    bus = EventBus()
    service = DockingService(bus, providers={})

    states: list[CacheState] = []
    bus.subscribe(DockingJobStateChanged, lambda e: states.append(e.state))

    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))
    service.request_docking(
        ligand_molecule_uuid="lig-1",
        ligand_mol=Chem.MolFromSmiles("CCO"),
        receptor_macromolecule_uuid="rec-1",
        receptor_structure_text="ATOM ...",
        receptor_source_format="pdb",
        box=box,
        provider_id="does_not_exist",
    )

    assert states == [CacheState.FAILED]


def test_register_and_unregister_provider(qapp):
    bus = EventBus()
    service = DockingService(bus, providers={})
    provider = FakeDockingProvider()

    service.register_provider(provider)
    assert "fake" in service._providers

    service.unregister_provider("fake")
    assert "fake" not in service._providers
