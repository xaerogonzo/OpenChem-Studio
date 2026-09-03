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


# --- replicates -------------------------------------------------------------
#
# Every guard here runs `_DockingTask.run()` DIRECTLY rather than through the
# thread pool. The loop, the seed derivation and the representative choice are
# all synchronous, so scheduling them would buy nothing but a `_drain` and a
# timeout -- and this project's own record is that a pumped event loop is where
# its crashes land.


class _ReplicateProvider(DockingProvider):
    """Records the seed of every call and returns a scripted affinity per run.

    It MIRRORS the real provider on the one behaviour the service reads back:
    `VinaDockingProvider` chooses a seed itself when the caller pinned none and
    reports it through `_last_run_settings`. A fake that reported nothing would
    make every unpinned replicate record `seed=None` and hide the difference
    between "the provider chose one" and "the provider was never asked".
    """

    provider_id = "replicate"
    engine_id = "replicate-engine"

    def __init__(self, affinities, fail_on=None, cancel_after=None) -> None:
        self._affinities = list(affinities)
        self._fail_on = fail_on
        self._cancel_after = cancel_after
        self.seeds: list[int | None] = []
        self.calls = 0
        self._last_run_settings: dict = {}

    def engine_version(self) -> str:
        return "1.0"

    def dock(
        self,
        receptor_structure_text,
        receptor_source_format,
        ligand_mol,
        box,
        num_poses,
        progress,
        receptor_prep_options=None,
        search_options=None,
    ):
        index = self.calls
        self.calls += 1
        options = search_options or {}
        seed = options.get("seed")
        if seed is None:
            seed = 700000 + index
        self.seeds.append(seed)
        self._last_run_settings = {
            "exhaustiveness": int(options.get("exhaustiveness", 25)),
            "seed": seed,
            "scoring_function": options.get("scoring_function", "vina"),
            "ligand_prep_params": {},
        }
        progress.report(0.5, "Docking")
        if self._fail_on is not None and index == self._fail_on:
            raise RuntimeError(f"run {index} blew up")
        if self._cancel_after is not None and index == self._cancel_after:
            progress.cancel()
        affinity = self._affinities[index]
        if affinity is None:
            return []
        return [
            DockingPoseModel(
                pose_molblock=f"pose from run {index}",
                binding_affinity_kcal_mol=affinity,
                rmsd_lb=0.0,
                rmsd_ub=0.0,
            )
        ]


def _replicate_task(provider, *, replicates, search_options=None, ligand_uuid="lig-1"):
    from openchem.domain.docking import DockingBox as _DockingBox
    from openchem.services.docking_service import _DockingTask
    from openchem.services.progress import ProgressHandle

    bus = EventBus()
    events: list = []
    produced: list = []
    bus.subscribe(DockingJobStateChanged, events.append)
    bus.subscribe(DockingResultReady, lambda e: produced.append(e.result))
    task = _DockingTask(
        provider=provider,
        ligand_molecule_uuid=ligand_uuid,
        ligand_mol=Chem.MolFromSmiles("CCO"),
        receptor_macromolecule_uuid="rec-1",
        receptor_structure_text="ATOM ...",
        receptor_source_format="pdb",
        box=_DockingBox(center=(0.0, 0.0, 0.0), size=(10.0, 10.0, 10.0)),
        num_poses=9,
        event_bus=bus,
        job_manager=JobManager(),
        receptor_prep_options={},
        progress=ProgressHandle(),
        search_options=search_options,
        replicates=replicates,
    )
    return task, events, produced


# --- the seeds --------------------------------------------------------------


def test_three_replicates_run_three_searches_with_three_distinct_seeds():
    """The loop's whole point, and the mutation is reusing one seed.

    Three runs at one seed would return three identical affinities, so the
    spread would read as 0.00 over 3 runs -- a measurement of nothing,
    presented in the same words as a molecule that genuinely reproduces.
    """
    provider = _ReplicateProvider([-8.9, -8.8, -8.7])
    task, _events, produced = _replicate_task(
        provider, replicates=3, search_options={"seed": 4712}
    )
    task.run()

    assert provider.calls == 3
    assert len(set(provider.seeds)) == 3
    assert len(produced) == 1
    assert len(produced[0].replicates.replicates) == 3


def test_a_pinned_protocol_seed_is_not_itself_sent_to_the_engine():
    """The cost of the hierarchy, asserted so nobody discovers it.

    Pinning 4712 no longer makes Vina run at 4712 -- it makes it run at seeds
    DERIVED from 4712, one per replicate. What is preserved is the property
    that matters: the same protocol seed regenerates the same set for this
    ligand. What is lost is that an older result cannot be reproduced by
    re-typing its recorded number, which is why `protocol_seed` and `seed` are
    two fields rather than one.
    """
    provider = _ReplicateProvider([-8.9])
    task, _events, produced = _replicate_task(
        provider, replicates=1, search_options={"seed": 4712}
    )
    task.run()

    assert provider.seeds == [358255849]
    assert 4712 not in provider.seeds
    assert produced[0].replicates.protocol_seed == 4712
    assert produced[0].seed == 358255849


def test_a_pinned_seed_reproduces_the_whole_replicate_set():
    """Every run, not just the first.

    The mutation is seeding replicate 0 and letting the rest fall to the
    provider's own randomness, which reproduces the headline number often
    enough to look right while the SPREAD -- the thing being measured -- is
    different every time.
    """
    first = _ReplicateProvider([-8.9, -8.8, -8.7])
    second = _ReplicateProvider([-8.9, -8.8, -8.7])
    for provider in (first, second):
        task, _events, _produced = _replicate_task(
            provider, replicates=3, search_options={"seed": 4712}
        )
        task.run()

    assert first.seeds == second.seeds
    assert len(set(first.seeds)) == 3


def test_two_ligands_never_share_a_replicate_seed():
    """The statistical precondition, and no numerical test would notice it.

    `domain/affinity_range.py`'s separation rule is an exact rank-sum
    calculation over two INDEPENDENT samples. Deriving replicate seeds from the
    protocol seed alone would hand every ligand in a screen the same set, so
    their values would arrive as correlated pairs and the exact calculation
    would be void -- while every affinity, every range and every verdict on
    screen still looked entirely reasonable.
    """
    from openchem.services.docking_service import replicate_seeds

    a = replicate_seeds(4712, "ligand-a", 5)
    b = replicate_seeds(4712, "ligand-b", 5)

    assert set(a).isdisjoint(b)
    assert len(set(a)) == 5


def test_the_replicate_seed_sequence_is_prefix_stable():
    """Raising the count keeps the runs already performed.

    Seed i depends on i and never on `count`, so a 5-replicate set is the
    3-replicate set plus two more rather than a different experiment. That is
    what lets nested counts be read off one sample -- the benchmark's whole
    n = 3/5/10 design -- and it is not free: drawing from a shared random
    stream sized to `count` would satisfy every other guard here and break it.
    """
    from openchem.services.docking_service import replicate_seeds

    assert replicate_seeds(4712, "lig-a", 5)[:3] == replicate_seeds(4712, "lig-a", 3)


def test_the_seed_derivation_never_calls_the_builtin_hash():
    """A source guard, because this project has already shipped this bug.

    `hash()` of a str is randomised per process, so a protocol advertised as
    reproducible would silently have depended on PYTHONHASHSEED --
    `protonate_at_ph` made a scientific answer a function of it, and eight
    processes gave three different charges. A behavioural test cannot see this
    from inside one process, which is exactly why the check is lexical.

    It is an AST walk and not a text search: `hashlib` contains the word.
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "openchem"
        / "services"
        / "docking_service.py"
    ).read_text(encoding="utf-8")
    offenders = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "hash"
    ]

    assert offenders == []


# --- what the set records ---------------------------------------------------


def test_a_single_run_still_records_a_one_element_replicate_set():
    """Three states, and this is the middle one.

    `None` means the count was never recorded, which is every result saved
    before replicates existed. A one-element set means somebody ran this once
    and we know it. Collapsing them would make the panel unable to tell "no
    spread was measured" from "we have no idea how this was run".
    """
    provider = _ReplicateProvider([-8.9])
    task, _events, produced = _replicate_task(provider, replicates=1)
    task.run()

    assert produced[0].replicates is not None
    assert len(produced[0].replicates.replicates) == 1
    assert produced[0].replicates.affinity_range().width is None


def test_an_unpinned_run_has_no_protocol_seed_and_still_records_every_seed():
    """Fabricating a root the user never chose would make an unpinned run look
    pinned. The individual seeds are still recorded, so the set is reproducible
    after the fact even though it was not reproducible in advance.
    """
    provider = _ReplicateProvider([-8.9, -8.8])
    task, _events, produced = _replicate_task(provider, replicates=2)
    task.run()

    replicate_set = produced[0].replicates
    assert replicate_set.protocol_seed is None
    assert all(r.seed is not None for r in replicate_set.replicates)


def test_a_provider_that_cannot_take_search_options_records_no_seed():
    """The honest record for a run whose seed was never sent anywhere.

    `FakeDockingProvider` predates `search_options`, so the derived seed is not
    passed and the provider reports nothing back. Recording the derived number
    would name a setting the run did not use -- the exact defect that made
    `scoring_function="vina"` and `exhaustiveness=8` literals here once.
    """
    provider = FakeDockingProvider()
    task, _events, produced = _replicate_task(
        provider, replicates=2, search_options={"seed": 4712}
    )
    task.run()

    assert [r.seed for r in produced[0].replicates.replicates] == [None, None]


# --- which run the poses come from ------------------------------------------


def test_the_representative_is_the_median_replicate():
    """End to end, on the fixture that discriminates first, best and last.

    The service half is separate from `median_replicate_index`'s own guard
    because two things can drift: the rule, and whether the poses actually kept
    are the ones the rule chose. Testing the helper is not testing the wiring.
    """
    provider = _ReplicateProvider([-10.0, -9.0, -8.0, -1.0])
    task, _events, produced = _replicate_task(
        provider, replicates=4, search_options={"seed": 4712}
    )
    task.run()

    result = produced[0]
    assert result.replicates.representative_index == 2
    assert result.poses[0].pose_molblock == "pose from run 2"
    assert result.poses[0].binding_affinity_kcal_mol == -8.0
    # The stored seed is the seed of the run behind the stored poses -- read
    # from the representative's snapshot and not from the provider, which by
    # now is holding run 3's.
    assert result.seed == provider.seeds[2]
    assert result.seed != provider.seeds[-1]


def test_the_reported_centre_does_not_improve_with_more_replicates():
    """The behavioural half of refusing best-of-N.

    Both fixtures are centred on -8.0 and the wider one reaches further in both
    directions, so the MEDIAN is unmoved while the MINIMUM drops by 3 kcal/mol.
    A best-scoring representative would report -9.0 at n = 3 and -12.0 at n = 9
    for the same molecule -- an affinity that is a function of the replicate
    count, which is what this whole feature exists to stop.
    """
    narrow = _ReplicateProvider([-9.0, -8.0, -7.0])
    wide = _ReplicateProvider([-12.0, -10.0, -9.0, -8.5, -8.0, -7.5, -7.0, -6.0, -4.0])

    centres = []
    lows = []
    for provider, count in ((narrow, 3), (wide, 9)):
        task, _events, produced = _replicate_task(
            provider, replicates=count, search_options={"seed": 4712}
        )
        task.run()
        spread = produced[0].replicates.affinity_range()
        centres.append(spread.median)
        lows.append(spread.low)

    assert centres == [-8.0, -8.0]
    assert lows == [-9.0, -12.0]


def test_the_pose_table_row_one_equals_the_reported_centre():
    """By construction, so the panel never prints two numbers for one thing.

    The representative IS the median run, so its best pose IS the median of the
    per-replicate bests. A best-scoring or first-run representative breaks this
    silently: the table and the spread label would disagree with nothing on
    screen able to say which was right.
    """
    provider = _ReplicateProvider([-10.0, -9.0, -8.0, -1.0])
    task, _events, produced = _replicate_task(
        provider, replicates=4, search_options={"seed": 4712}
    )
    task.run()

    result = produced[0]
    assert result.poses[0].binding_affinity_kcal_mol == result.replicates.affinity_range().median


# --- failure, cancellation and cost -----------------------------------------


def test_a_failed_replicate_fails_the_whole_run():
    """No partial set, and the mutation is publishing the runs that worked.

    A spread over "the 3 of 5 that finished" is a spread over a SELECTED
    subset, and the selection is not random: a replicate that crashed may well
    be one whose search went somewhere unusual, so dropping it biases the very
    quantity the set exists to measure. The failure names the run, because the
    exception alone cannot say which of five broke.
    """
    provider = _ReplicateProvider([-8.9, -8.8, -8.7], fail_on=1)
    task, events, produced = _replicate_task(
        provider, replicates=3, search_options={"seed": 4712}
    )
    task.run()

    assert produced == []
    assert events[-1].state == CacheState.FAILED
    assert "Run 2 of 3" in events[-1].message
    assert provider.calls == 2


def test_a_single_run_failure_message_is_unchanged():
    """The default path renders exactly as it did before replicates existed.

    "Run 1 of 1 failed" is noise, and a message that changed at N = 1 would be
    a behavioural change shipped to every user who never asked for replicates.
    """
    provider = _ReplicateProvider([-8.9], fail_on=0)
    task, events, _produced = _replicate_task(provider, replicates=1)
    task.run()

    assert events[-1].state == CacheState.FAILED
    assert events[-1].message == "run 0 blew up"


def test_a_cancel_between_replicates_publishes_FAILED():
    """A partial set is not the run the user asked for.

    The provider cancels at the end of its first call, so the loop's check
    fires before the second. The mutation is carrying on: it would publish a
    one-run set labelled as one of three, with a width of None where the user
    asked for a spread.
    """
    provider = _ReplicateProvider([-8.9, -8.8, -8.7], cancel_after=0)
    task, events, produced = _replicate_task(
        provider, replicates=3, search_options={"seed": 4712}
    )
    task.run()

    assert provider.calls == 1
    assert produced == []
    assert events[-1].state == CacheState.FAILED
    assert "cancelled" in events[-1].message.lower()


def test_interaction_analysis_runs_once_not_per_replicate():
    """It annotates the poses that get DISPLAYED, and only one set is kept.

    Running it per replicate would cost N receptor parses to enrich pose sets
    nobody ever sees. Counted on `receptor_atoms_from_structure`, which is the
    expensive half and is called exactly once per annotation pass.
    """
    import openchem.services.docking_service as service_module

    calls = []
    original = service_module.receptor_atoms_from_structure
    service_module.receptor_atoms_from_structure = lambda *a, **k: calls.append(1) or []
    try:
        provider = _ReplicateProvider([-8.9, -8.8, -8.7, -8.6])
        task, _events, produced = _replicate_task(
            provider, replicates=4, search_options={"seed": 4712}
        )
        task.run()
    finally:
        service_module.receptor_atoms_from_structure = original

    assert provider.calls == 4
    assert len(calls) == 1
    assert len(produced) == 1


# --- progress ---------------------------------------------------------------


def test_progress_names_the_replicate_rather_than_appearing_to_restart():
    """The message is the only progress channel this application has.

    `JobHandle`'s own docstring says it reuses the free-text string "rather
    than a second, parallel progress-reporting channel", and `_on_progress` has
    never read `fraction` -- so the design's "map 0..1 into [i/n, (i+1)/n]"
    would have computed a number nothing consumes. Naming the run buys what the
    mapping was for: a long job stops LOOKING like it reset to the first phase
    N times.
    """
    provider = _ReplicateProvider([-8.9, -8.8, -8.7])
    task, events, _produced = _replicate_task(
        provider, replicates=3, search_options={"seed": 4712}
    )
    task.run()

    messages = [e.message for e in events if e.message]
    assert messages == [
        "Run 1 of 3: Docking",
        "Run 2 of 3: Docking",
        "Run 3 of 3: Docking",
    ]


def test_a_single_run_reports_progress_exactly_as_it_did_before_replicates():
    """The narrow half, and it is the load-bearing one.

    "Always prefix the run" satisfies the guard above and ships "Run 1 of 1:"
    to every user who never asked for replicates -- a visible change to the
    default path, in a branch whose whole compatibility claim is that N = 1
    renders as it always did.
    """
    provider = _ReplicateProvider([-8.9])
    task, events, _produced = _replicate_task(provider, replicates=1)
    task.run()

    assert [e.message for e in events if e.message] == ["Docking"]

