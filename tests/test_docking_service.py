from __future__ import annotations

import time

from PySide6.QtCore import QThreadPool
from rdkit import Chem

from openchem.app.settings import Settings
from openchem.domain.common import CacheState
from openchem.domain.docking import DockingBox, DockingPoseModel
from openchem.events.base import EventBus
from openchem.events.events import DockingJobStateChanged, DockingResultReady
from openchem.plugins.interfaces import DockingProvider
from openchem.services.docking_service import DockingService
from openchem.services.job_manager import JobManager


def _wait_until(qapp, predicate, timeout_seconds: float = 10) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _SlowDockingProvider(DockingProvider):
    """Sleeps in short steps, checking progress.is_cancelled() between
    them -- gives a test real wall-clock time to call job_manager.cancel()
    while docking is genuinely still in progress."""

    provider_id = "slow"

    def dock(self, receptor_structure_text, receptor_source_format, ligand_mol, box, num_poses, progress, receptor_prep_options=None):
        for _ in range(100):
            if progress.is_cancelled():
                raise RuntimeError("Docking cancelled by user")
            time.sleep(0.02)
        return [
            DockingPoseModel(pose_molblock="fake molblock", binding_affinity_kcal_mol=-5.0, rmsd_lb=0.0, rmsd_ub=0.0)
        ]


def _make_settings(bus: EventBus) -> Settings:
    return Settings(bus)


class FakeDockingProvider(DockingProvider):
    provider_id = "fake"
    engine_id = "fake-engine"

    def __init__(self, raise_error: bool = False) -> None:
        self._raise_error = raise_error

    def engine_version(self) -> str:
        return "0.0.1"

    def dock(
        self,
        receptor_structure_text,
        receptor_source_format,
        ligand_mol,
        box,
        num_poses,
        progress,
        receptor_prep_options=None,
    ):
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
    service = DockingService(bus, _make_settings(bus), providers={provider.provider_id: provider})

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
    service = DockingService(bus, _make_settings(bus), providers={provider.provider_id: provider})

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
    service = DockingService(bus, _make_settings(bus), providers={})

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


_RECEPTOR_PDB_FOR_ANALYSIS = """HEADER    TEST
ATOM      1  N   ALA A   1      11.104  13.207   2.845  1.00 20.00           N
ATOM      2  CA  ALA A   1      11.999  12.040   2.945  1.00 20.00           C
ATOM      3  C   ALA A   1      13.398  12.442   2.508  1.00 20.00           C
ATOM      4  O   ALA A   1      13.598  13.601   2.128  1.00 20.00           O
END
"""


def _molblock_with_nitrogen_near_receptor_oxygen() -> str:
    # 3.0 A from the receptor oxygen at (13.598, 13.601, 2.128) above --
    # inside the 3.5 A polar-contact cutoff, a guaranteed hbond.
    mol = Chem.RWMol()
    mol.AddAtom(Chem.Atom("N"))
    conformer = Chem.Conformer(1)
    conformer.SetAtomPosition(0, (16.598, 13.601, 2.128))
    mol.AddConformer(conformer)
    return Chem.MolToMolBlock(mol.GetMol(), kekulize=False)


class _AnalyzablePoseDockingProvider(DockingProvider):
    provider_id = "analyzable"

    def dock(self, receptor_structure_text, receptor_source_format, ligand_mol, box, num_poses, progress, receptor_prep_options=None):
        return [
            DockingPoseModel(
                pose_molblock=_molblock_with_nitrogen_near_receptor_oxygen(),
                binding_affinity_kcal_mol=-5.0,
                rmsd_lb=0.0,
                rmsd_ub=0.0,
            )
        ]


def test_docking_result_poses_are_annotated_with_interactions(qapp):
    bus = EventBus()
    provider = _AnalyzablePoseDockingProvider()
    service = DockingService(bus, _make_settings(bus), providers={provider.provider_id: provider})

    results = []
    bus.subscribe(DockingResultReady, lambda e: results.append(e.result))

    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))
    service.request_docking(
        ligand_molecule_uuid="lig-1",
        ligand_mol=Chem.MolFromSmiles("CCO"),
        receptor_macromolecule_uuid="rec-1",
        receptor_structure_text=_RECEPTOR_PDB_FOR_ANALYSIS,
        receptor_source_format="pdb",
        box=box,
        provider_id="analyzable",
    )
    _drain(qapp)

    assert len(results) == 1
    metadata = results[0].poses[0].metadata
    assert len(metadata["hbonds"]) == 1
    assert metadata["hbonds"][0]["receptor_element"] == "O"
    assert metadata["clashes"] == []


def test_docking_request_rejected_while_one_already_running(qapp):
    bus = EventBus()
    provider = FakeDockingProvider()
    job_manager = JobManager()
    service = DockingService(
        bus, _make_settings(bus), providers={provider.provider_id: provider}, job_manager=job_manager
    )

    # Simulate a job already in flight for this (ligand, receptor) pair
    # without actually scheduling one -- exercises the guard
    # deterministically, no QRunnable timing race needed.
    job_manager.try_start("docking", "lig-1:rec-1")

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
        provider_id="fake",
    )

    assert states == [CacheState.FAILED]


def test_register_and_unregister_provider(qapp):
    bus = EventBus()
    service = DockingService(bus, _make_settings(bus), providers={})
    provider = FakeDockingProvider()

    service.register_provider(provider)
    assert "fake" in service._providers

    service.unregister_provider("fake")
    assert "fake" not in service._providers


def test_default_provider_reads_executable_path_from_settings(qapp):
    """The default "vina" provider constructed by DockingService (when no
    `providers` override is given) must resolve its executable path from
    live Settings, not a value frozen at construction time -- otherwise a
    path configured via the docking panel's "Configure Vina..." dialog
    after startup would never take effect without an app restart. Doesn't
    assert a blank starting value: `isolated_settings`'s per-test QSettings
    IniFormat file lives under `tmp_path`, whose directory naming pytest
    can reuse across separate invocations, so a previous run's value can
    genuinely still be on disk -- only the "does a fresh write take effect
    immediately" behavior is asserted here.
    """
    bus = EventBus()
    settings = _make_settings(bus)
    service = DockingService(bus, settings)

    vina_provider = service._providers["vina"]

    settings.set("docking/vina_executable_path", "C:/fake/vina.exe")
    assert vina_provider._executable_path_resolver() == "C:/fake/vina.exe"

    settings.set("docking/vina_executable_path", "D:/other/vina2.exe")
    assert vina_provider._executable_path_resolver() == "D:/other/vina2.exe"


def test_cancel_via_job_manager_stops_docking(qapp):
    bus = EventBus()
    provider = _SlowDockingProvider()
    job_manager = JobManager()
    service = DockingService(
        bus, _make_settings(bus), providers={provider.provider_id: provider}, job_manager=job_manager
    )

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
        provider_id="slow",
    )
    assert _wait_until(qapp, lambda: CacheState.RUNNING in states)

    cancelled = job_manager.cancel("docking", "lig-1:rec-1")
    assert cancelled is True

    assert _wait_until(qapp, lambda: states and states[-1] == CacheState.FAILED)

    assert results == []
    assert not job_manager.is_active("docking", "lig-1:rec-1")


# --- biological assembly ----------------------------------------------------

_ASSEMBLY_PDB = (
    "HEADER    TEST\n"
    "REMARK 350 BIOMOLECULE: 1\n"
    "REMARK 350 APPLY THE FOLLOWING TO CHAINS: A\n"
    "REMARK 350   BIOMT1   1  1.000000  0.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT2   1  0.000000  1.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT3   1  0.000000  0.000000  1.000000        0.00000\n"
    "REMARK 350   BIOMT1   2 -1.000000  0.000000  0.000000       10.00000\n"
    "REMARK 350   BIOMT2   2  0.000000  1.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT3   2  0.000000  0.000000 -1.000000        0.00000\n"
    "ATOM      1  N   ALA A   1       1.000   2.000   3.000  1.00 20.00           N\n"
    "ATOM      2  CA  ALA A   1       4.000   5.000   6.000  1.00 20.00           C\n"
    "END\n"
)


class _RecordingProvider:
    """A provider that records exactly what receptor text it was handed."""

    provider_id = "recording"
    engine_id = "recording"

    def __init__(self) -> None:
        self.seen_text: str | None = None

    def dock(self, receptor_structure_text, receptor_source_format, ligand_mol, box,
             num_poses, progress, receptor_prep_options=None):
        self.seen_text = receptor_structure_text
        return []

    def engine_version(self) -> str:
        return "test"


def _task(provider, prep_options):
    from openchem.domain.docking import DockingBox
    from openchem.services.docking_service import _DockingTask
    from openchem.services.job_manager import JobManager
    from openchem.services.progress import ProgressHandle

    bus = EventBus()
    return bus, _DockingTask(
        provider=provider,
        ligand_molecule_uuid="lig-1",
        ligand_mol=Chem.MolFromSmiles("CCO"),
        receptor_macromolecule_uuid="rec-1",
        receptor_structure_text=_ASSEMBLY_PDB,
        receptor_source_format="pdb",
        box=DockingBox(center=(0.0, 0.0, 0.0), size=(10.0, 10.0, 10.0)),
        num_poses=1,
        event_bus=bus,
        job_manager=JobManager(),
        receptor_prep_options=prep_options,
        progress=ProgressHandle(),
    )


def test_docking_uses_the_deposited_structure_by_default(qapp):
    """Default-off, asserted on the TEXT the provider receives.

    This is what protects the 49-receptor catalogue: every existing
    result was produced against the deposited asymmetric unit, and
    nothing about adding a builder may change that silently.
    """
    provider = _RecordingProvider()
    _bus, task = _task(provider, {})
    task.run()

    assert provider.seen_text == _ASSEMBLY_PDB


def test_asking_for_the_assembly_docks_the_built_one(qapp):
    provider = _RecordingProvider()
    _bus, task = _task(provider, {"build_assembly": True})
    task.run()

    assert provider.seen_text is not None
    atoms = [l for l in provider.seen_text.splitlines() if l.startswith(("ATOM  ", "HETATM"))]
    assert len(atoms) == 4, "the dimer was not built"
    assert {l[21] for l in atoms} == {"A", "B"}


def test_a_refused_assembly_fails_the_job_and_docks_nothing(qapp):
    """**NO SILENT FALLBACK**, and this is the test that enforces it.

    The asymmetric unit is a perfectly dockable structure, so falling
    back to it would return a plausible, scientifically wrong answer to
    a question the user did not ask -- the same shape as this codebase's
    40619 kcal/mol interaction energy. Someone who asked for the
    biological assembly gets it or gets nothing.
    """
    states: list[tuple[CacheState, str]] = []
    provider = _RecordingProvider()
    bus, task = _task(provider, {"build_assembly": True, "assembly_id": "7"})
    bus.subscribe(DockingJobStateChanged, lambda e: states.append((e.state, e.message or "")))
    task.run()

    assert provider.seen_text is None, "it docked the deposited structure after refusing to build"
    assert CacheState.FAILED in [s for s, _ in states]
    message = next(m for s, m in states if s is CacheState.FAILED)
    assert "declares no assembly" in message, message


def test_the_result_records_which_object_was_docked(qapp):
    """With the option off by default, "I asked for the assembly" and "the
    assembly differed from what I had" have to be separable facts, or a
    result cannot say what it was computed against."""
    results: list = []
    provider = _RecordingProvider()
    bus, task = _task(provider, {"build_assembly": True})
    bus.subscribe(DockingResultReady, lambda e: results.append(e.result))
    task.run()

    parameters = results[0].provenance.parameters
    assert parameters["assembly_requested"] is True
    assert parameters["assembly_built"] is True
    assert parameters["assembly_id"] == "1"
    assert parameters["assembly_generated_copies"] == 1
    assert parameters["assembly_chains"] == "A,B"


def test_a_default_run_says_it_did_not_use_an_assembly(qapp):
    results: list = []
    provider = _RecordingProvider()
    bus, task = _task(provider, {})
    bus.subscribe(DockingResultReady, lambda e: results.append(e.result))
    task.run()

    assert results[0].provenance.parameters["assembly_requested"] is False
