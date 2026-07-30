from __future__ import annotations

import logging
import time

from PySide6.QtCore import QRunnable, QThreadPool

from openchem.chem.descriptor_providers import DescriptorProvider, RDKitDescriptorProvider
from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import DescriptorComputed

logger = logging.getLogger("openchem.chemistry")


class _DescriptorComputeTask(QRunnable):
    """Runs one provider's `compute()` off the GUI thread.

    Publishes RUNNING placeholders before the call and COMPLETED/FAILED
    results after, via the EventBus — safe to call from a worker thread
    because EventBus.publish is a Qt signal emit, queued onto the bus's own
    (GUI) thread.
    """

    def __init__(
        self,
        provider: DescriptorProvider,
        engine: ChemistryEngine,
        model: MoleculeModel,
        event_bus: EventBus,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._engine = engine
        self._model = model
        self._event_bus = event_bus

    def run(self) -> None:
        for descriptor_id in self._provider.descriptor_ids():
            self._publish(descriptor_id, CacheState.RUNNING)
        try:
            mol = self._engine.mol_from_model(self._model)
            values = self._provider.compute(mol, self._model.uuid)
        except Exception as exc:  # noqa: BLE001 - a bad provider must not kill the pool
            logger.exception("Descriptor provider %s failed", self._provider.provider_id)
            for descriptor_id in self._provider.descriptor_ids():
                self._publish(descriptor_id, CacheState.FAILED, error=str(exc))
            return
        for value in values:
            self._event_bus.publish(DescriptorComputed(descriptor=value))

    def _publish(self, descriptor_id: str, state: CacheState, error: str | None = None) -> None:
        self._event_bus.publish(
            DescriptorComputed(
                descriptor=DescriptorValue(
                    descriptor_id=descriptor_id,
                    name=descriptor_id,
                    units="",
                    category="",
                    provider=self._provider.provider_id,
                    molecule_uuid=self._model.uuid,
                    cache_state=state,
                    error=error,
                    timestamp=time.time(),
                )
            )
        )


class DescriptorService:
    """Schedules descriptor computation on a QThreadPool.

    Every request moves each descriptor through Queued -> Running ->
    Completed|Failed, published as DescriptorComputed events — even though
    today's RDKit descriptors finish in milliseconds, so slower future
    providers (docking, ORCA, AI) share the same contract with no new code
    path in the property panel.
    """

    def __init__(
        self,
        event_bus: EventBus,
        engine: ChemistryEngine,
        providers: list[DescriptorProvider] | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._engine = engine
        self._providers = providers if providers is not None else [RDKitDescriptorProvider()]
        self._pool = QThreadPool.globalInstance()

    def register_provider(self, provider: DescriptorProvider) -> None:
        """Register a plugin-supplied descriptor provider. Its descriptors
        run alongside the built-in ones for every future request."""
        self._providers.append(provider)

    def unregister_provider(self, provider_id: str) -> None:
        self._providers = [p for p in self._providers if p.provider_id != provider_id]

    def request_descriptors(self, model: MoleculeModel) -> None:
        if not model.molblock:
            # A freshly-created molecule with no structure yet can't produce
            # descriptors -- publishing QUEUED/FAILED for it would just show
            # a permanent "failed" row in the Properties panel before the
            # user has drawn anything. Silently do nothing instead; a real
            # request follows once the molecule actually has a structure
            # (see MoleculeEditorWidget -> EditStructureCommand -> the
            # MoleculeChanged handler that re-requests descriptors).
            return
        for provider in self._providers:
            for descriptor_id in provider.descriptor_ids():
                self._event_bus.publish(
                    DescriptorComputed(
                        descriptor=DescriptorValue(
                            descriptor_id=descriptor_id,
                            name=descriptor_id,
                            units="",
                            category="",
                            provider=provider.provider_id,
                            molecule_uuid=model.uuid,
                            cache_state=CacheState.QUEUED,
                        )
                    )
                )
            self._pool.start(_DescriptorComputeTask(provider, self._engine, model, self._event_bus))
