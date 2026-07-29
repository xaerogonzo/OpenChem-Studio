from __future__ import annotations

import logging

from PySide6.QtCore import QRunnable, QThreadPool
from rdkit import Chem

from openchem.chem.docking_providers import VinaDockingProvider
from openchem.domain.common import CacheState, Provenance
from openchem.domain.docking import DockingBox, DockingResultModel
from openchem.events.base import EventBus
from openchem.events.events import DockingJobStateChanged, DockingResultReady
from openchem.plugins.interfaces import DockingProvider
from openchem.services.progress import ProgressHandle

logger = logging.getLogger("openchem.chemistry")

DEFAULT_NUM_POSES = 9


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

    def run(self) -> None:
        self._event_bus.publish(
            DockingJobStateChanged(
                ligand_molecule_uuid=self._ligand_molecule_uuid,
                receptor_macromolecule_uuid=self._receptor_macromolecule_uuid,
                state=CacheState.RUNNING,
            )
        )
        progress = ProgressHandle(on_progress=self._on_progress)
        try:
            poses = self._provider.dock(
                self._receptor_structure_text,
                self._receptor_source_format,
                self._ligand_mol,
                self._box,
                self._num_poses,
                progress,
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
            return

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
        )
        self._event_bus.publish(DockingResultReady(result=result))
        self._event_bus.publish(
            DockingJobStateChanged(
                ligand_molecule_uuid=self._ligand_molecule_uuid,
                receptor_macromolecule_uuid=self._receptor_macromolecule_uuid,
                state=CacheState.COMPLETED,
            )
        )

    def _on_progress(self, fraction: float, message: str) -> None:
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

    def __init__(self, event_bus: EventBus, providers: dict[str, DockingProvider] | None = None) -> None:
        self._event_bus = event_bus
        default_provider = VinaDockingProvider()
        self._providers: dict[str, DockingProvider] = (
            providers if providers is not None else {default_provider.provider_id: default_provider}
        )
        self._pool = QThreadPool.globalInstance()

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
            )
        )
