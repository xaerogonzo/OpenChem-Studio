from __future__ import annotations

import logging
import time

from PySide6.QtCore import QRunnable, QThreadPool

from openchem.chem.conformer_providers import RDKitConformerProvider
from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformerJobStateChanged, ConformersReady
from openchem.plugins.interfaces import ConformerProvider
from openchem.services.job_manager import JobManager

_JOB_KIND = "conformer"

logger = logging.getLogger("openchem.chemistry")


class _ConformerGenerationTask(QRunnable):
    """Runs one provider's `generate_conformers()` off the GUI thread.

    Publishes RUNNING progress via ConformerJobStateChanged and, on success,
    the results as data via ConformersReady — it never mutates MoleculeModel
    itself. Applying the results to the model is a command's job (see
    commands/conformer_commands.py), the same separation DescriptorService
    keeps for descriptor values.
    """

    def __init__(
        self,
        provider: ConformerProvider,
        engine: ChemistryEngine,
        model: MoleculeModel,
        num_conformers: int,
        optimize: bool,
        event_bus: EventBus,
        job_manager: JobManager,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._engine = engine
        self._model = model
        self._num_conformers = num_conformers
        self._optimize = optimize
        self._event_bus = event_bus
        self._job_manager = job_manager

    def run(self) -> None:
        self._event_bus.publish(
            ConformerJobStateChanged(molecule_uuid=self._model.uuid, state=CacheState.RUNNING)
        )
        try:
            mol = self._engine.mol_from_model(self._model)
            results = self._provider.generate_conformers(
                mol, self._num_conformers, self._optimize, on_progress=self._on_progress
            )
        except Exception as exc:  # noqa: BLE001 - report failure, never crash the pool
            logger.exception("Conformer generation failed for molecule %s", self._model.uuid)
            self._event_bus.publish(
                ConformerJobStateChanged(
                    molecule_uuid=self._model.uuid, state=CacheState.FAILED, message=str(exc)
                )
            )
            self._job_manager.finish(_JOB_KIND, self._model.uuid)
            return

        method = (
            f"{self._provider.provider_id}+MMFF94/UFF" if self._optimize else self._provider.provider_id
        )
        now = time.time()
        provenance = Provenance(
            created_by="core",
            method=self._provider.provider_id,
            parameters={"num_conformers": self._num_conformers, "optimize": self._optimize},
            timestamp=now,
        )
        conformers = [
            ConformerModel(
                molblock=self._engine.mol_to_molblock(conf_mol),
                energy=energy,
                method=method,
                timestamp=now,
                provenance=provenance,
            )
            for conf_mol, energy in results
        ]
        self._event_bus.publish(ConformersReady(molecule_uuid=self._model.uuid, conformers=conformers))
        self._event_bus.publish(
            ConformerJobStateChanged(molecule_uuid=self._model.uuid, state=CacheState.COMPLETED)
        )
        self._job_manager.finish(_JOB_KIND, self._model.uuid)

    def _on_progress(self, done: int, total: int) -> None:
        self._event_bus.publish(
            ConformerJobStateChanged(
                molecule_uuid=self._model.uuid,
                state=CacheState.RUNNING,
                message=f"{done}/{total} conformers",
            )
        )


class ConformerService:
    """Schedules conformer generation (+ optional geometry optimization) on a
    QThreadPool, moving each request through Queued -> Running ->
    Completed|Failed, same contract as DescriptorService.

    Supports multiple registered providers (keyed by `provider_id`) for
    plugin extensibility, even though only the built-in "rdkit" one is
    exposed through the UI today — the "Generate Conformers" dialog picking
    a provider is a fast-follow, not part of this phase.
    """

    def __init__(
        self,
        event_bus: EventBus,
        engine: ChemistryEngine,
        providers: dict[str, ConformerProvider] | None = None,
        job_manager: JobManager | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._engine = engine
        default_provider = RDKitConformerProvider()
        self._providers: dict[str, ConformerProvider] = (
            providers if providers is not None else {default_provider.provider_id: default_provider}
        )
        self._pool = QThreadPool.globalInstance()
        self._job_manager = job_manager if job_manager is not None else JobManager()

    def register_provider(self, provider: ConformerProvider) -> None:
        self._providers[provider.provider_id] = provider

    def unregister_provider(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)

    def request_conformers(
        self, model: MoleculeModel, num_conformers: int, optimize: bool, provider_id: str = "rdkit"
    ) -> None:
        provider = self._providers.get(provider_id)
        if provider is None:
            self._event_bus.publish(
                ConformerJobStateChanged(
                    molecule_uuid=model.uuid,
                    state=CacheState.FAILED,
                    message=f"Unknown conformer provider: {provider_id}",
                )
            )
            return
        if not self._job_manager.try_start(_JOB_KIND, model.uuid):
            self._event_bus.publish(
                ConformerJobStateChanged(
                    molecule_uuid=model.uuid,
                    state=CacheState.FAILED,
                    message="A conformer generation job is already running for this molecule.",
                )
            )
            return
        self._event_bus.publish(
            ConformerJobStateChanged(molecule_uuid=model.uuid, state=CacheState.QUEUED)
        )
        self._pool.start(
            _ConformerGenerationTask(
                provider, self._engine, model, num_conformers, optimize, self._event_bus, self._job_manager
            )
        )
