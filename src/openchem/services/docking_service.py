from __future__ import annotations

import hashlib
import inspect
import logging
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QRunnable, QThreadPool
from rdkit import Chem

from openchem.app.settings import Settings
from openchem.chem.docking_providers import VinaDockingProvider
from openchem.chem.pose_analysis import analyze_pose, receptor_atoms_from_structure
from openchem.chem.structure_assembly import PRIMARY_ASSEMBLY_ID
from openchem.domain.common import CacheState, Provenance
from openchem.domain.docking import (
    DockingBox,
    DockingPoseModel,
    DockingReplicate,
    DockingReplicateSet,
    DockingResultModel,
    median_replicate_index,
)
from openchem.events.base import EventBus
from openchem.events.events import DockingJobStateChanged, DockingResultReady
from openchem.plugins.interfaces import DockingProvider
from openchem.services.job_manager import JobManager
from openchem.services.progress import ProgressHandle

logger = logging.getLogger("openchem.chemistry")

DEFAULT_NUM_POSES = 9
_JOB_KIND = "docking"

#: How many searches one docking request performs unless the caller asks for
#: more.
#:
#: ONE, AND THE HARM IS STILL FIXED AT ZERO RUNTIME COST. Anything above 1
#: would multiply every existing user's docking wall clock with no
#: announcement, and multiply every virtual-screening budget (50 ligands x 4 =
#: 200 Vina runs). At 1 the fix is behavioural rather than statistical: the
#: panel reports "1 run, seed 4712 -- no spread measured" instead of a bare
#: -8.88, so the number stops presenting itself as a measurement, and the
#: screening table stops numbering an ordering it cannot support.
#:
#: It is also what makes this branch's own build safe: at 1 the call count, the
#: recorded settings and the progress text are byte-identical to before
#: replicates existed, so a red docking test is unambiguously a fault rather
#: than a re-baselining exercise.
DEFAULT_REPLICATES = 1

#: The top of the seed range this module derives into.
#:
#: Matches the `random.randrange(1, 2**31 - 1)` that `VinaDockingProvider`
#: already draws an UNPINNED seed from, so a derived seed and a
#: provider-chosen one come from the same space -- neither is distinguishable
#: from the other by its magnitude, and a stored result reads the same either
#: way.
_MAX_DERIVED_SEED = 2**31 - 2


def replicate_seeds(protocol_seed: int, ligand_molecule_uuid: str, count: int) -> list[int]:
    """`count` distinct Vina seeds, derived from the pinned protocol seed AND
    the ligand's uuid.

    PER LIGAND, WHICH IS A STATISTICAL REQUIREMENT RATHER THAN A CONVENIENCE.
    The separation rule in `domain/affinity_range.py` is an exact rank-sum
    calculation, which needs the two ligands' replicate sets to be INDEPENDENT.
    Deriving from the protocol seed alone would hand every ligand in a screen
    the same seed set, so their values would arrive as correlated pairs and the
    exact calculation would be void -- while every number on screen still
    looked entirely fine. No numerical test notices that; only a test that
    compares two ligands' seed sets does.

    SHA-256, NEVER `hash()`, AND NEVER A TUPLE SEED. `hash()` of a str is
    randomised per process, so a protocol advertised as reproducible would in
    fact have depended on PYTHONHASHSEED -- this project has already shipped
    exactly that defect once, in `protonate_at_ph`, where a scientific answer
    became a function of the hash seed. And `random.Random((seed, uuid))`
    raises outright: `random.seed` accepts only None, int, float, str, bytes
    and bytearray.

    THE SEQUENCE IS PREFIX-STABLE. Seed i depends on i and never on `count`, so
    raising the replicate count from 3 to 5 keeps the first three runs
    unchanged. That is what lets a longer run be read as a superset of a
    shorter one instead of a different experiment. It holds even when a
    collision is skipped, because the skip depends only on entries already
    drawn.

    Distinctness is enforced rather than assumed. A 4-byte collision inside one
    set is astronomically unlikely, and "N distinct seeds" is the claim the
    whole protocol makes, so it is checked instead of argued.
    """
    if count < 1:
        raise ValueError("A replicate count is at least 1")
    seeds: list[int] = []
    seen: set[int] = set()
    nonce = 0
    while len(seeds) < count:
        material = f"{protocol_seed}:{ligand_molecule_uuid}:{nonce}".encode("utf-8")
        candidate = 1 + int.from_bytes(hashlib.sha256(material).digest()[:4], "big") % _MAX_DERIVED_SEED
        nonce += 1
        if candidate not in seen:
            seen.add(candidate)
            seeds.append(candidate)
    return seeds


@dataclass(slots=True)
class _ReplicateOutcome:
    """What one replicate produced, held until the representative is chosen.

    THE SETTINGS ARE SNAPSHOTTED PER REPLICATE, and that is the load-bearing
    part. `_recorded_settings` reads the provider's `_last_run_settings`, which
    by the end of the loop describes the LAST run -- so a result built from it
    after the loop would report the final replicate's seed beside the MEDIAN
    replicate's poses. Two different runs in one row, with nothing on screen
    able to say so.
    """

    poses: list[DockingPoseModel]
    settings: dict[str, Any]

    @property
    def best_affinity(self) -> float | None:
        """The best (most negative) affinity this run found, or None when it
        found nothing.

        None rather than a sentinel: a run that returned no poses measured no
        affinity, and `AffinityRange` is built only over the runs that did.
        """
        if not self.poses:
            return None
        return min(pose.binding_affinity_kcal_mol for pose in self.poses)


def _provider_accepts(provider: DockingProvider, name: str) -> bool:
    """Whether `provider.dock` takes a keyword argument named `name`.

    ASKED, not attempted. Passing the argument and catching `TypeError`
    would also swallow a `TypeError` raised from INSIDE a provider that does
    accept it, turning a real bug into "this provider is old". Same shape as
    `ConformerProvider.generate_conformer_batch(options)`, which reached the
    identical problem first.
    """
    try:
        parameters = inspect.signature(provider.dock).parameters
    except (TypeError, ValueError):
        # A C-implemented or otherwise unintrospectable callable. Assume the
        # older contract, which is the one that cannot fail.
        return False
    if name in parameters:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())


def _recorded_settings(
    provider: DockingProvider, receptor_prep_options: dict[str, Any]
) -> dict[str, Any]:
    """The protocol fields for `DockingResultModel`, read back from whatever
    actually ran.

    A run is reproducible only under the SAME engine, version and settings --
    a recorded seed does not pin a result across a Vina upgrade or a different
    backend, which is why the version travels with it. This does not claim
    determinism.

    `getattr` throughout, deliberately: a third-party `DockingProvider` need
    not expose any of this, and the honest record for one that does not is
    "unknown" rather than this file's own defaults wearing the provider's
    name.
    """
    settings = dict(getattr(provider, "_last_run_settings", {}) or {})
    return {
        "engine": getattr(provider, "engine_id", provider.provider_id),
        "engine_version": (
            provider.engine_version() if hasattr(provider, "engine_version") else "unknown"
        ),
        "scoring_function": settings.get("scoring_function", "unknown"),
        "exhaustiveness": int(settings.get("exhaustiveness", 0)),
        "seed": settings.get("seed"),
        "receptor_prep_params": dict(receptor_prep_options),
        "ligand_prep_params": dict(settings.get("ligand_prep_params", {})),
    }



class AssemblyRefused(RuntimeError):
    """The requested biological assembly could not be built.

    Its own type rather than a bare RuntimeError so the no-fallback rule
    is enforceable rather than conventional: a caller cannot mistake it
    for a docking failure and retry with the deposited structure.
    """


#: Prefix for the assembly keys merged into a docking result's provenance.
#:
#: PREFIXED FOR THE REASON `chem/calculation_input.INPUT_PREFIX` records:
#: these keys join a dict the provider also writes, and two layers
#: describing different things in the same words collided silently there
#: twice before anybody noticed.
_ASSEMBLY_PREFIX = "assembly_"


def _job_key(ligand_molecule_uuid: str, receptor_macromolecule_uuid: str) -> str:
    return f"{ligand_molecule_uuid}:{receptor_macromolecule_uuid}"


class _DockingTask(QRunnable):
    """Runs one provider's `dock()` off the GUI thread — same shape as
    `ConformerService`'s `_ConformerGenerationTask`. Publishes RUNNING
    progress via `DockingJobStateChanged` and, on success, the full
    `DockingResultModel` (not just bare poses, unlike conformers) as data
    via `DockingResultReady` — it never mutates `ProjectModel` itself.
    Applying the result is `SetDockingResultCommand`'s job.
    """

    def __init__(
        self,
        provider: DockingProvider,
        ligand_molecule_uuid: str,
        ligand_mol: Chem.Mol,
        receptor_macromolecule_uuid: str,
        receptor_structure_text: str,
        receptor_source_format: str,
        box: DockingBox,
        num_poses: int,
        event_bus: EventBus,
        job_manager: JobManager,
        receptor_prep_options: dict[str, Any],
        progress: ProgressHandle,
        search_options: dict[str, Any] | None = None,
        replicates: int = DEFAULT_REPLICATES,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._ligand_molecule_uuid = ligand_molecule_uuid
        self._ligand_mol = ligand_mol
        self._receptor_macromolecule_uuid = receptor_macromolecule_uuid
        self._receptor_structure_text = receptor_structure_text
        self._receptor_source_format = receptor_source_format
        self._box = box
        self._num_poses = num_poses
        self._event_bus = event_bus
        self._job_manager = job_manager
        self._receptor_prep_options = receptor_prep_options
        self._search_options = dict(search_options or {})
        #: How many searches to run. THE LOOP IS HERE AND NOT IN THE PANEL:
        #: N panel-issued requests would be refused one after another by
        #: `JobManager`'s duplicate-key guard, and any that got through would
        #: publish N separate `DockingResultReady` events, so the panel would
        #: show only the last -- a single run wearing a replicate count.
        self._replicate_count = max(1, int(replicates))
        #: Which replicate is running, read by `_on_progress` so a long job
        #: says which run it is on instead of appearing to restart.
        self._replicate_index = 0
        # Constructed by DockingService BEFORE this task is scheduled (see
        # request_docking) so its cancel() can be registered with
        # JobManager as this job's cancel_callback ahead of time -- not
        # constructed here, since by the time run() starts on the worker
        # thread it would already be too late for a Jobs panel to have
        # anything to cancel.
        self._progress = progress
        self._progress.on_progress = self._on_progress
        #: What happened to the assembly request, merged into the
        #: result's provenance. Set before any early return so a
        #: result is always able to say which object it docked.
        self._assembly_provenance: dict[str, Any] = {f"{_ASSEMBLY_PREFIX}requested": False}

    def run(self) -> None:
        self._event_bus.publish(
            DockingJobStateChanged(
                ligand_molecule_uuid=self._ligand_molecule_uuid,
                receptor_macromolecule_uuid=self._receptor_macromolecule_uuid,
                state=CacheState.RUNNING,
            )
        )
        progress = self._progress
        try:
            self._build_requested_assembly()
        except AssemblyRefused as exc:
            # **NO SILENT FALLBACK.** The asymmetric unit is a perfectly
            # dockable structure and docking it here would return a
            # plausible, scientifically wrong answer to a question the
            # user did not ask -- the same shape as this codebase's
            # 40619 kcal/mol interaction energy and its crystal click
            # reaching the molecular measurement. Someone who asked for
            # the biological assembly gets it or gets nothing.
            logger.error("Assembly build refused for ligand %s: %s", self._ligand_molecule_uuid, exc)
            self._fail(str(exc))
            return

        protocol_seed = self._protocol_seed()
        seeds = self._replicate_seeds(protocol_seed)
        outcomes: list[_ReplicateOutcome] = []
        for index, seed in enumerate(seeds):
            self._replicate_index = index
            if progress.is_cancelled():
                # **A PARTIAL SET IS NOT THE RUN THE USER ASKED FOR.**
                # Publishing the replicates that did finish would report a
                # spread over a truncated sample, and the truncation is not
                # random -- it is "however far we got before somebody pressed
                # cancel". A cancelled docking run has always produced FAILED;
                # a cancel between replicates does the same thing.
                self._fail(f"Docking cancelled before run {index + 1} of {len(seeds)}.")
                return
            try:
                poses = self._provider.dock(
                    self._receptor_structure_text,
                    self._receptor_source_format,
                    self._ligand_mol,
                    self._box,
                    self._num_poses,
                    progress,
                    self._receptor_prep_options,
                    **self._search_options_kwarg(seed),
                )
            except Exception as exc:  # noqa: BLE001 - report failure, never crash the pool
                logger.exception(
                    "Docking failed for ligand %s on run %d of %d",
                    self._ligand_molecule_uuid,
                    index + 1,
                    len(seeds),
                )
                # **A FAILED REPLICATE FAILS THE WHOLE RUN.** Reporting a
                # spread over "the 3 of 5 that worked" is a spread over a
                # SELECTED subset, and the selection is not random -- a
                # replicate that crashed may well be one whose search went
                # somewhere unusual, so dropping it biases the very quantity
                # the set exists to measure.
                self._fail(self._failure_message(index, len(seeds), exc))
                return
            outcomes.append(
                _ReplicateOutcome(
                    poses=poses,
                    # Snapshotted HERE rather than after the loop: this is the
                    # only moment `_last_run_settings` describes THIS run.
                    settings=_recorded_settings(self._provider, self._receptor_prep_options),
                )
            )

        replicates = [
            DockingReplicate(
                # Read BACK from what the provider reports it used, never from
                # what was derived above. One rule covers all three cases: a
                # pinned seed the provider echoes, an unpinned one it chose for
                # itself, and a provider that does not take `search_options` at
                # all and so ran on its own defaults -- where the honest record
                # is None rather than a seed that was derived and never sent.
                seed=outcome.settings.get("seed"),
                best_affinity_kcal_mol=outcome.best_affinity,
                error=None if outcome.poses else "This run returned no poses.",
            )
            for outcome in outcomes
        ]
        representative = median_replicate_index(replicates)
        poses = outcomes[representative].poses

        # ONCE, on the representative's poses. Interaction analysis is per-pose
        # enrichment of the pose set that gets DISPLAYED, and only the
        # representative's are kept -- running it per replicate would cost N
        # times as much to annotate pose sets nobody ever sees.
        self._annotate_poses_with_interactions(poses)

        result = DockingResultModel(
            ligand_molecule_uuid=self._ligand_molecule_uuid,
            receptor_macromolecule_uuid=self._receptor_macromolecule_uuid,
            box=self._box,
            poses=poses,
            provenance=Provenance(
                created_by="core",
                method=self._provider.provider_id,
                parameters={"num_poses": self._num_poses, **self._assembly_provenance},
            ),
            replicates=DockingReplicateSet(
                protocol_seed=protocol_seed,
                representative_index=representative,
                replicates=replicates,
            ),
            # Read back from the provider rather than restated here. These
            # used to be the literals `"vina"`, `8` and `None`, which were true
            # only by coincidence: they described the defaults this file
            # happened to believe in, not the run. A stored result that names
            # settings it did not use is worse than one that names none, since
            # nothing distinguishes it from a measurement.
            #
            # THE REPRESENTATIVE'S SNAPSHOT, never the provider's current
            # state: `seed` on the result means "the seed of the run that
            # produced these poses", and after N replicates the provider is
            # holding the LAST run's.
            **outcomes[representative].settings,
        )
        self._event_bus.publish(DockingResultReady(result=result))
        self._event_bus.publish(
            DockingJobStateChanged(
                ligand_molecule_uuid=self._ligand_molecule_uuid,
                receptor_macromolecule_uuid=self._receptor_macromolecule_uuid,
                state=CacheState.COMPLETED,
            )
        )
        self._job_manager.finish(
            _JOB_KIND, _job_key(self._ligand_molecule_uuid, self._receptor_macromolecule_uuid)
        )

    def _build_requested_assembly(self) -> None:
        """Replace the receptor with its biological assembly, ONCE.

        **Built here and assigned back, so `dock()` and
        `receptor_atoms_from_structure()` are handed the identical text.**
        Two callers each building their own would be the same split that
        `is_stripped_residue`, `filter_altlocs` and `is_symmetry_generated`
        each exist to close -- and it would be the worst version of it,
        because the analysis would be describing a different oligomer from
        the one Vina searched.

        Records what happened either way. "I asked for the biological
        assembly" and "the assembly actually differed from what I had" are
        different facts, and a result nobody can distinguish between them
        six months later cannot say which object it docked against --
        especially with the option off by default.
        """
        from openchem.chem.structure_assembly import build_assembly

        self._assembly_provenance = {f"{_ASSEMBLY_PREFIX}requested": False}
        if not self._receptor_prep_options.get("build_assembly"):
            return

        assembly_id = str(self._receptor_prep_options.get("assembly_id") or PRIMARY_ASSEMBLY_ID)
        result = build_assembly(
            self._receptor_structure_text, self._receptor_source_format, assembly_id
        )
        if not result.ok:
            raise AssemblyRefused(
                f"The biological assembly could not be built, so nothing was docked: "
                f"{result.failure_reason}"
            )

        self._receptor_structure_text = result.output_text
        self._assembly_provenance = {
            f"{_ASSEMBLY_PREFIX}requested": True,
            f"{_ASSEMBLY_PREFIX}id": result.assembly_id,
            # Whether building CHANGED anything, kept apart from whether it
            # was asked for: an assembly the file already held is a no-op,
            # not a different receptor.
            f"{_ASSEMBLY_PREFIX}built": result.changed_the_structure,
            f"{_ASSEMBLY_PREFIX}instances": len(result.instances),
            f"{_ASSEMBLY_PREFIX}generated_copies": result.generated_copies,
            f"{_ASSEMBLY_PREFIX}chains": ",".join(i.generated_chain_id for i in result.instances),
        }
        for warning in result.warnings:
            logger.warning("Assembly %s: %s", assembly_id, warning)


    def _protocol_seed(self) -> int | None:
        """The seed the USER pinned, or None when they pinned nothing.

        TWO SEED CONCEPTS, AND THIS IS THE ROOT ONE. It is not the seed any
        single Vina run receives -- those are derived from it per ligand. None
        stays None: fabricating a root the user never chose would make an
        unpinned run look pinned, and the per-replicate seeds are recorded
        individually either way, so an unpinned set is still reproducible after
        the fact.
        """
        seed = self._search_options.get("seed")
        return None if seed is None else int(seed)

    def _replicate_seeds(self, protocol_seed: int | None) -> list[int | None]:
        """One seed per replicate, or `None` per replicate when unpinned.

        A PINNED SEED NO LONGER REACHES VINA VERBATIM, and that is a real
        change worth stating rather than discovering. Pin 4712 and the runs
        use derived seeds, not 4712 -- so a result recorded before this
        existed cannot be reproduced by re-typing its number. What IS preserved
        is the property that matters: one protocol seed regenerates the whole
        set, for this ligand, forever.

        The alternative -- letting replicate 0 keep the protocol seed and
        deriving only 1..N-1 -- looks strictly friendlier and is disqualified
        by one line: every ligand in a screen would then share seed 4712 as its
        first run, which is exactly the paired dependence
        `domain/affinity_range.py`'s exact rank-sum calculation forbids.

        Unpinned, each element is None and the provider chooses its own seed
        per call, exactly as it does today. It is recorded per replicate on the
        way back out.
        """
        if protocol_seed is None:
            return [None] * self._replicate_count
        return list(
            replicate_seeds(protocol_seed, self._ligand_molecule_uuid, self._replicate_count)
        )

    def _failure_message(self, index: int, count: int, exc: Exception) -> str:
        """What a crashed replicate reports.

        AT N == 1 THIS IS `str(exc)`, byte for byte what a failed dock has
        always said -- the default path must not gain a "run 1 of 1" nobody
        asked for. Above 1 the run is named, because "which of the five broke"
        is the first thing a reader needs and the exception alone cannot say.
        """
        if count < 2:
            return str(exc)
        return f"Run {index + 1} of {count} failed, so no replicate set was produced: {exc}"

    def _fail(self, message: str) -> None:
        """Publish FAILED and release the job, in ONE place.

        Three call sites now -- a refused assembly, a crashed replicate, and a
        cancel between replicates -- where there were two, and every one has to
        do BOTH halves. A publish without the `finish` leaves this
        ligand/receptor pair permanently unstartable behind `JobManager`'s
        single-flight guard, which reads as the panel ignoring the button.
        """
        self._event_bus.publish(
            DockingJobStateChanged(
                ligand_molecule_uuid=self._ligand_molecule_uuid,
                receptor_macromolecule_uuid=self._receptor_macromolecule_uuid,
                state=CacheState.FAILED,
                message=message,
            )
        )
        self._job_manager.finish(
            _JOB_KIND, _job_key(self._ligand_molecule_uuid, self._receptor_macromolecule_uuid)
        )

    def _search_options_kwarg(self, seed: int | None = None) -> dict[str, Any]:
        """`{"search_options": ...}` when the provider takes it, `{}` otherwise.

        A `DockingProvider` written against the earlier signature keeps
        working, and its result records `scoring_function="unknown"` with
        exhaustiveness 0 rather than this file guessing on its behalf. Its
        replicates then record `seed=None`, which is the honest answer: the
        seed derived for that run was never sent anywhere.

        `seed` overrides only when it is not None, so an UNPINNED run passes
        `self._search_options` through unchanged -- the dict the provider sees
        is identical to the one it saw before replicates existed.
        """
        if not self._search_options:
            return {}
        if not _provider_accepts(self._provider, "search_options"):
            logger.info(
                "Provider %s does not accept search_options; the run uses its own defaults.",
                getattr(self._provider, "provider_id", type(self._provider).__name__),
            )
            return {}
        options = dict(self._search_options)
        if seed is not None:
            options["seed"] = seed
        return {"search_options": options}

    def _annotate_poses_with_interactions(self, poses: list[DockingPoseModel]) -> None:
        """Populates each pose's `metadata` with H-bond/clash data (see
        `chem/pose_analysis.py`) -- an enhancement, not part of the
        docking result's critical path, so a parsing failure here (e.g. an
        unusual receptor structure) logs and leaves `metadata` empty
        rather than failing the whole docking job that already succeeded.

        The SAME prep options the docking used are passed on, so the
        analysis sees the receptor Vina saw. Without that it parsed the
        raw file and reported contacts with stripped waters and
        co-crystallised ligands -- see `receptor_atoms_from_structure`.
        """
        try:
            receptor_atoms = receptor_atoms_from_structure(
                self._receptor_structure_text,
                self._receptor_source_format,
                self._receptor_prep_options,
            )
            for pose in poses:
                pose.metadata.update(analyze_pose(pose.pose_molblock, receptor_atoms))
        except Exception:  # noqa: BLE001 - enhancement only, must never fail the job
            logger.exception(
                "Pose interaction analysis failed for ligand %s -- poses still returned without it",
                self._ligand_molecule_uuid,
            )

    def _replicate_message(self, message: str) -> str:
        """The provider's own phase text, prefixed with which run it belongs to.

        THE MESSAGE IS THE ONLY PROGRESS CHANNEL THIS APPLICATION HAS, and the
        design this implements assumed a numeric one -- "replicate i of n maps
        its 0..1 into [i/n, (i+1)/n]". There is nothing to map it into.
        `_on_progress` has never read `fraction` at all, and `JobHandle`'s own
        docstring says it reuses the free-text string "rather than a second,
        parallel progress-reporting channel". Computing a mapped fraction here
        would be a number nothing consumes, which this project has already
        recorded as a defect in its own right.

        Naming the run buys what the mapping was for: a three-minute job stops
        LOOKING like it reset to "Preparing receptor" three times.

        AT N == 1 THE TEXT IS UNCHANGED, deliberately. "Run 1 of 1:" is noise,
        and the default path has to render exactly as it did before.
        """
        if self._replicate_count < 2:
            return message
        return f"Run {self._replicate_index + 1} of {self._replicate_count}: {message}"

    def _on_progress(self, fraction: float, message: str) -> None:
        job_key = _job_key(self._ligand_molecule_uuid, self._receptor_macromolecule_uuid)
        message = self._replicate_message(message)
        self._job_manager.update_message(_JOB_KIND, job_key, message)
        self._event_bus.publish(
            DockingJobStateChanged(
                ligand_molecule_uuid=self._ligand_molecule_uuid,
                receptor_macromolecule_uuid=self._receptor_macromolecule_uuid,
                state=CacheState.RUNNING,
                message=message,
            )
        )


class DockingService:
    """Schedules docking runs on a `QThreadPool`, moving each request
    through Queued->Running->Completed|Failed, same contract as
    `ConformerService`/`DescriptorService`.

    Supports multiple registered providers (keyed by `provider_id`) for
    plugin extensibility, even though only the built-in "vina" one exists
    today — same shape as `ConformerService`.
    """

    def __init__(
        self,
        event_bus: EventBus,
        settings: Settings,
        providers: dict[str, DockingProvider] | None = None,
        job_manager: JobManager | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._settings = settings
        default_provider = VinaDockingProvider(
            executable_path_resolver=lambda: settings.get("docking/vina_executable_path", "")
        )
        self._providers: dict[str, DockingProvider] = (
            providers if providers is not None else {default_provider.provider_id: default_provider}
        )
        self._pool = QThreadPool.globalInstance()
        self._job_manager = job_manager if job_manager is not None else JobManager()

    def register_provider(self, provider: DockingProvider) -> None:
        self._providers[provider.provider_id] = provider

    def unregister_provider(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)

    def request_docking(
        self,
        ligand_molecule_uuid: str,
        ligand_mol: Chem.Mol,
        receptor_macromolecule_uuid: str,
        receptor_structure_text: str,
        receptor_source_format: str,
        box: DockingBox,
        num_poses: int = DEFAULT_NUM_POSES,
        provider_id: str = "vina",
        receptor_prep_options: dict[str, Any] | None = None,
        search_options: dict[str, Any] | None = None,
        replicates: int = DEFAULT_REPLICATES,
    ) -> None:
        provider = self._providers.get(provider_id)
        if provider is None:
            self._event_bus.publish(
                DockingJobStateChanged(
                    ligand_molecule_uuid=ligand_molecule_uuid,
                    receptor_macromolecule_uuid=receptor_macromolecule_uuid,
                    state=CacheState.FAILED,
                    message=f"Unknown docking provider: {provider_id}",
                )
            )
            return
        job_key = _job_key(ligand_molecule_uuid, receptor_macromolecule_uuid)
        # Constructed here (main thread, before scheduling) rather than
        # inside _DockingTask.run() (worker thread) so its cancel() can be
        # registered with JobManager up front -- a Jobs panel calling
        # cancel() before the task even starts running must still reach
        # it. VinaDockingProvider checks progress.is_cancelled() at its
        # own phase boundaries (best-effort: the actual Vina search itself
        # is one blocking call neither Vina backend exposes a mid-run
        # cancellation hook for).
        progress = ProgressHandle()
        if not self._job_manager.try_start(_JOB_KIND, job_key, cancel_callback=progress.cancel):
            self._event_bus.publish(
                DockingJobStateChanged(
                    ligand_molecule_uuid=ligand_molecule_uuid,
                    receptor_macromolecule_uuid=receptor_macromolecule_uuid,
                    state=CacheState.FAILED,
                    message="A docking job is already running for this ligand/receptor pair.",
                )
            )
            return
        self._event_bus.publish(
            DockingJobStateChanged(
                ligand_molecule_uuid=ligand_molecule_uuid,
                receptor_macromolecule_uuid=receptor_macromolecule_uuid,
                state=CacheState.QUEUED,
            )
        )
        self._pool.start(
            _DockingTask(
                provider,
                ligand_molecule_uuid,
                ligand_mol,
                receptor_macromolecule_uuid,
                receptor_structure_text,
                receptor_source_format,
                box,
                num_poses,
                self._event_bus,
                self._job_manager,
                receptor_prep_options or {},
                progress,
                search_options,
                # A SIBLING OF `num_poses`, NOT A `search_options` KEY. The
                # provider never sees more than one run at a time, so a
                # replicate count in the dict it receives would name something
                # it cannot act on -- and `search_options` is asserted as an
                # exact dict by `tests/test_ligand_extent_warning.py`.
                replicates,
            )
        )
