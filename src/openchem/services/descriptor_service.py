from __future__ import annotations

import logging
import time
from dataclasses import replace

from PySide6.QtCore import QRunnable, QThreadPool

from openchem.chem.calculation_input import geometry_provenance, select_calculation_input
from openchem.chem.descriptor_providers import DescriptorProvider, RDKitDescriptorProvider
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import DRAWING, CalculationRequest
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.report import ReportResult
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureSetResult,
    TrajectoryResult,
)
from openchem.events.base import EventBus
from openchem.events.events import (
    AlertComputed,
    ReportComputed,
    DescriptorComputed,
    PerAtomDataComputed,
    PhCurveComputed,
    SpectrumComputed,
    StructureSetComputed,
    TrajectoryComputed,
)
from openchem.services.calculator_registry import CalculatorRegistry

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
        calculation_input: str = DRAWING,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._engine = engine
        self._model = model
        self._event_bus = event_bus
        # WHICH STRUCTURE, stated as a POLICY rather than handed in as a
        # resolved molblock. See DescriptorService.request_descriptors.
        self._calculation_input = calculation_input

    def run(self) -> None:
        categories = self._provider.descriptor_categories()
        for descriptor_id in self._provider.descriptor_ids():
            self._publish(descriptor_id, CacheState.RUNNING, category=categories.get(descriptor_id, ""))
        try:
            mol = select_calculation_input(self._engine, self._model, self._calculation_input)
            values = self._provider.compute(mol, self._model.uuid)
        except Exception as exc:  # noqa: BLE001 - a bad provider must not kill the pool
            logger.exception("Descriptor provider %s failed", self._provider.provider_id)
            for descriptor_id in self._provider.descriptor_ids():
                self._publish(
                    descriptor_id, CacheState.FAILED, error=str(exc), category=categories.get(descriptor_id, "")
                )
            return
        for value in values:
            self._event_bus.publish(DescriptorComputed(descriptor=value))

        try:
            alerts = self._provider.compute_alerts(mol, self._model.uuid)
        except Exception:  # noqa: BLE001 - alerts are an enhancement, must not drop the descriptors above
            logger.exception("Alert computation failed for provider %s", self._provider.provider_id)
        else:
            for alert in alerts:
                self._event_bus.publish(AlertComputed(alert=alert))

        try:
            datasets = self._provider.compute_per_atom(mol, self._model.uuid)
        except Exception:  # noqa: BLE001 - per-atom data is an enhancement, must not drop the descriptors above
            logger.exception("Per-atom data computation failed for provider %s", self._provider.provider_id)
            return
        for dataset in datasets:
            self._event_bus.publish(PerAtomDataComputed(dataset=dataset))

    def _publish(
        self, descriptor_id: str, state: CacheState, error: str | None = None, category: str = ""
    ) -> None:
        self._event_bus.publish(
            DescriptorComputed(
                descriptor=DescriptorValue(
                    descriptor_id=descriptor_id,
                    name=descriptor_id,
                    units="",
                    category=category,
                    provider=self._provider.provider_id,
                    molecule_uuid=self._model.uuid,
                    cache_state=state,
                    error=error,
                    timestamp=time.time(),
                )
            )
        )


def _with_geometry_provenance(result, model: MoleculeModel, calculation_input: str):
    """`result` with which-geometry-was-used merged into its provenance.

    THE KEYS DO NOT COLLIDE BY CONSTRUCTION -- `geometry_provenance`
    prefixes all of its own (see `INPUT_PREFIX`), because this layer
    records what a calculator was HANDED while the calculator records
    what it DID, and the two want the same words. Two really did collide
    before the prefix: `steric_analysis.geometry_source` and
    `molecular_dynamics.force_field`.

    The calculator still wins on any collision that somehow remains --
    it knows what it computed and this only knows what it was computed
    ON -- but that is now a safety net rather than the mechanism, and
    `test_no_calculator_provenance_key_collides_with_the_routing_layer`
    fails if it ever becomes load-bearing again.

    A result whose provenance cannot be replaced (no `provenance` field,
    or a shape that will not take it) is returned untouched -- recording
    where a number came from must never be able to lose the number.
    """
    provenance = getattr(result, "provenance", None)
    if provenance is None:
        return result
    try:
        merged = dict(geometry_provenance(model, calculation_input))
        merged.update(provenance.parameters)
        return replace(result, provenance=replace(provenance, parameters=merged))
    except Exception:  # noqa: BLE001 - never lose a result over its metadata
        logger.exception("Could not record geometry provenance for %s", model.uuid)
        return result


class _CalculationTask(QRunnable):
    """Runs one registered calculator's `compute` off the GUI thread --
    Phase 18's on-demand path, separate from `_DescriptorComputeTask`'s
    always-eager batch (calculator requests are parameter-dependent and
    user-triggered, not something that should recompute on every
    structure edit).
    """

    def __init__(
        self,
        registry: CalculatorRegistry,
        engine: ChemistryEngine,
        model: MoleculeModel,
        request: CalculationRequest,
        event_bus: EventBus,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._engine = engine
        self._model = model
        self._request = request
        self._event_bus = event_bus

    def run(self) -> None:
        definition = self._registry.get(self._request.calculator_id)
        if definition is None:
            logger.error("Unknown calculator_id: %s", self._request.calculator_id)
            self._publish_failed(f"Unknown calculator: {self._request.calculator_id}")
            return
        try:
            # THE GAP THIS CLOSES: every registered calculator ran on the
            # 2D DRAWING, so the Properties panel reported "The available
            # conformer is 2D" while the 3D viewer showed "Conformer 3/3".
            # `_DescriptorComputeTask` 78 lines above has supported a
            # conformer override since Phase 14; this path never did.
            #
            # Only calculators that DECLARE they want geometry get it --
            # eight of the 49 return a different number when handed a
            # conformer purely because it carries explicit hydrogens.
            mol = select_calculation_input(self._engine, self._model, definition.calculation_input)
            result = self._registry.compute(
                self._request.calculator_id, mol, self._model.uuid, self._request.parameters
            )
            # Which geometry produced this, recorded on the way out rather
            # than asked of each calculator -- they are handed a molecule
            # and have no idea where it came from. Without it a steric
            # number cannot answer "which of my 23 conformers is this",
            # and the answer has to be an ID: index 0 today is index 3
            # after the next regeneration.
            result = _with_geometry_provenance(
                result, self._model, definition.calculation_input
            )
        except Exception as exc:  # noqa: BLE001 - a bad calculator must not kill the pool
            logger.exception("Calculator %s failed", self._request.calculator_id)
            self._publish_failed(str(exc))
            return
        if isinstance(result, PerAtomDataset):
            self._event_bus.publish(PerAtomDataComputed(dataset=result))
        elif isinstance(result, ReportResult):
            # BEFORE AlertResult, not after: nothing subclasses the other
            # today, but the ordering says which is the specific case if
            # one ever does.
            self._event_bus.publish(ReportComputed(report=result))
        elif isinstance(result, AlertResult):
            self._event_bus.publish(AlertComputed(alert=result))
        elif isinstance(result, SpectrumResult):
            self._event_bus.publish(SpectrumComputed(spectrum=result))
        elif isinstance(result, StructureSetResult):
            self._event_bus.publish(StructureSetComputed(structure_set=result))
        elif isinstance(result, PhCurveResult):
            self._event_bus.publish(PhCurveComputed(curve=result))
        elif isinstance(result, TrajectoryResult):
            self._event_bus.publish(TrajectoryComputed(trajectory=result))
        else:
            logger.error(
                "Calculator %s produced an unpublishable result type: %s",
                self._request.calculator_id,
                type(result).__name__,
            )

    def _publish_failed(self, message: str) -> None:
        # Empty PerAtomDataset is the only "there was a problem" shape
        # every current consumer (PropertyPanel, Calculator Inspector)
        # already knows how to render via ScientificResult.error -- no new
        # event type needed for a calculator-not-found/crashed report.
        self._event_bus.publish(
            PerAtomDataComputed(
                dataset=PerAtomDataset(
                    property_id=self._request.calculator_id,
                    name=self._request.calculator_id,
                    units="",
                    method="",
                    molecule_uuid=self._model.uuid,
                    values={},
                    cache_state=CacheState.FAILED,
                    error=message,
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
        calculator_registry: CalculatorRegistry | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._engine = engine
        self._providers = providers if providers is not None else [RDKitDescriptorProvider()]
        self._calculator_registry = calculator_registry or CalculatorRegistry()
        self._pool = QThreadPool.globalInstance()

    def run_calculator(self, model: MoleculeModel, request: CalculationRequest) -> None:
        """On-demand (not eager) calculator dispatch (Phase 18) -- looks up
        `request.calculator_id` in the injected `CalculatorRegistry` and
        runs it off the GUI thread, publishing the result via the existing
        `PerAtomDataComputed`/`AlertComputed` events based on the result's
        type. Named to avoid colliding with
        `QuantumChemistryService.request_calculation`, an unrelated
        existing ORCA-specific method."""
        self._pool.start(_CalculationTask(self._calculator_registry, self._engine, model, request, self._event_bus))

    def register_provider(self, provider: DescriptorProvider) -> None:
        """Register a plugin-supplied descriptor provider. Its descriptors
        run alongside the built-in ones for every future request."""
        self._providers.append(provider)

    def unregister_provider(self, provider_id: str) -> None:
        self._providers = [p for p in self._providers if p.provider_id != provider_id]

    def request_descriptors(self, model: MoleculeModel, calculation_input: str = DRAWING) -> None:
        """Computes descriptors for `model` against `calculation_input`.

        **SAY WHICH STRUCTURE YOU WANT, DO NOT RESOLVE ONE AND HAND IT
        OVER.** This used to take a raw `molblock` override, and the only
        production caller built it by doing half of
        `select_calculation_input` inline -- `canonical_conformer(model)`
        then `.molblock` -- which is exactly the duplication
        `chem/calculation_input.py` exists to end. The sibling path
        (`run_calculator`, 100 lines up) had already moved.

        It is not only tidier, and the difference is what the caller's
        copy left out:

        - a conformer whose molblock will not parse now falls back to the
          drawing with a log line, where before it raised and took every
          descriptor from that provider down with it as FAILED;
        - a stored conformer that is not actually 3D is refused, because
          a 2D molblock parses into a conformer with flat z, so
          `GetNumConformers() > 0` is true and useless as a check.

        `DRAWING` is the default and is byte-for-byte the old
        no-override behaviour: `mol_from_model` is
        `mol_from_molblock(model.molblock)` with a clearer error when
        there is none.
        """
        if not model.molblock and not model.conformers:
            # No structure of ANY kind -- neither a drawing nor a
            # conformer. A freshly-created molecule can't produce
            # descriptors -- publishing QUEUED/FAILED for it would just show
            # a permanent "failed" row in the Properties panel before the
            # user has drawn anything. Silently do nothing instead; a real
            # request follows once the molecule actually has a structure
            # (see MoleculeEditorWidget -> EditStructureCommand -> the
            # MoleculeChanged handler that re-requests descriptors).
            return
        for provider in self._providers:
            categories = provider.descriptor_categories()
            for descriptor_id in provider.descriptor_ids():
                self._event_bus.publish(
                    DescriptorComputed(
                        descriptor=DescriptorValue(
                            descriptor_id=descriptor_id,
                            name=descriptor_id,
                            units="",
                            category=categories.get(descriptor_id, ""),
                            provider=provider.provider_id,
                            molecule_uuid=model.uuid,
                            cache_state=CacheState.QUEUED,
                        )
                    )
                )
            self._pool.start(
                _DescriptorComputeTask(provider, self._engine, model, self._event_bus, calculation_input)
            )
