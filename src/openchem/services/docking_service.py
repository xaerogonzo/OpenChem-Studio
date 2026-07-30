from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QRunnable, QThreadPool
from rdkit import Chem

from openchem.app.settings import Settings
from openchem.chem.docking_providers import VinaDockingProvider
from openchem.chem.pose_analysis import analyze_pose, receptor_atoms_from_structure
from openchem.domain.common import CacheState, Provenance
from openchem.domain.docking import DockingBox, DockingPoseModel, DockingResultModel
from openchem.events.base import EventBus
from openchem.events.events import DockingJobStateChanged, DockingResultReady
from openchem.plugins.interfaces import DockingProvider
from openchem.services.job_manager import JobManager
from openchem.services.progress import ProgressHandle

logger = logging.getLogger("openchem.chemistry")

DEFAULT_NUM_POSES = 9
_JOB_KIND = "docking"


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
        # Constructed by DockingService BEFORE this task is scheduled (see
        # request_docking) so its cancel() can be registered with
        # JobManager as this job's cancel_callback ahead of time -- not
        # constructed here, since by the time run() starts on the worker
        # thread it would already be too late for a Jobs panel to have
        # anything to cancel.
        self._progress = progress
        self._progress.on_progress = self._on_progress

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
            poses = self._provider.dock(
                self._receptor_structure_text,
                self._receptor_source_format,
                self._ligand_mol,
                self._box,
                self._num_poses,
                progress,
                self._receptor_prep_options,
            )
        except Exception as exc:  # noqa: BLE001 - report failure, never crash the pool
            logger.exception("Docking failed for ligand %s", self._ligand_molecule_uuid)
            self._event_bus.publish(
                DockingJobStateChanged(
                    ligand_molecule_uuid=self._ligand_molecule_uuid,
                    receptor_macromolecule_uuid=self._receptor_macromolecule_uuid,
                    state=CacheState.FAILED,
                    message=str(exc),
                )
            )
            self._job_manager.finish(
                _JOB_KIND, _job_key(self._ligand_molecule_uuid, self._receptor_macromolecule_uuid)
            )
            return

        self._annotate_poses_with_interactions(poses)

        result = DockingResultModel(
            ligand_molecule_uuid=self._ligand_molecule_uuid,
            receptor_macromolecule_uuid=self._receptor_macromolecule_uuid,
            box=self._box,
            poses=poses,
            provenance=Provenance(
                created_by="core",
                method=self._provider.provider_id,
                parameters={"num_poses": self._num_poses},
            ),
            engine=getattr(self._provider, "engine_id", self._provider.provider_id),
            engine_version=(
                self._provider.engine_version() if hasattr(self._provider, "engine_version") else "unknown"
            ),
            scoring_function="vina",
            exhaustiveness=8,
            seed=None,
            receptor_prep_params=dict(self._receptor_prep_options),
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

    def _annotate_poses_with_interactions(self, poses: list[DockingPoseModel]) -> None:
        """Populates each pose's `metadata` with H-bond/clash data (see
        `chem/pose_analysis.py`) -- an enhancement, not part of the
        docking result's critical path, so a parsing failure here (e.g. an
        unusual receptor structure) logs and leaves `metadata` empty
        rather than failing the whole docking job that already succeeded.
        """
        try:
            receptor_atoms = receptor_atoms_from_structure(
                self._receptor_structure_text, self._receptor_source_format
            )
            for pose in poses:
                pose.metadata.update(analyze_pose(pose.pose_molblock, receptor_atoms))
        except Exception:  # noqa: BLE001 - enhancement only, must never fail the job
            logger.exception(
                "Pose interaction analysis failed for ligand %s -- poses still returned without it",
                self._ligand_molecule_uuid,
            )

    def _on_progress(self, fraction: float, message: str) -> None:
        job_key = _job_key(self._ligand_molecule_uuid, self._receptor_macromolecule_uuid)
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
            )
        )
