from __future__ import annotations

import logging
import time
from dataclasses import replace

from PySide6.QtCore import QRunnable, QThreadPool

from openchem.chem.calculation_input import (
    INPUT_PREFIX,
    geometry_provenance,
    input_fingerprint,
    recordable_parameters,
    resolve_calculation_input,
)
from openchem.chem.descriptor_providers import DescriptorProvider, RDKitDescriptorProvider
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import DRAWING, CalculationRefusal, CalculationRequest
from openchem.domain.refusal_kinds import MissingInput, RefusalKind, refusal_parameters
from openchem.domain.common import CacheState, Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.report import ReportResult, StructureReport
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureSetResult,
    TrajectoryResult,
)
from openchem.domain.result_store import BundlePart, StoredResult, is_failure
from openchem.events.base import EventBus
from openchem.events.events import (
    AutomaticPartFinished,
    ResultRecorded,
    AlertComputed,
    CalculationFinished,
    ReportComputed,
    DescriptorComputed,
    PerAtomDataComputed,
    PhCurveComputed,
    SpectrumComputed,
    StructureSetComputed,
    TrajectoryComputed,
)
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.result_identity import application_version, make_identity

logger = logging.getLogger("openchem.chemistry")

#: Registry calculators that belong to the always-on set a selection runs,
#: beside the descriptor providers. See
#: `PropertyPanel._request_substance_perception` for why it is the only one.
AUTOMATIC_CALCULATOR_IDS = frozenset({"substance_analysis"})


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
        #: What this run produced, for the manifest. See `_finish_part`.
        self._produced: list[str] = []
        self._part_failed = False
        # The fingerprint is taken from the SAME resolution that picks the
        # molecule, and before anything can fail: a failure is recorded
        # against the input it failed on.
        self._fingerprint = input_fingerprint(self._engine, self._model, DRAWING)
        try:
            resolved = resolve_calculation_input(self._engine, self._model, self._calculation_input)
            self._fingerprint = resolved.fingerprint
            mol = resolved.mol
        except Exception as exc:  # noqa: BLE001 - a bad provider must not kill the pool
            # No molecule, so nothing below has anything to run on.
            self._fail_descriptors(exc, categories)
            self._finish_part()
            return
        # **A DESCRIPTOR FAILURE NO LONGER TAKES THE ALERTS AND PER-ATOM DATA
        # WITH IT.** This returned early from here too, so one descriptor
        # raising (the McGowan volume on any sodium salt, measured) cost the
        # structure every alert and every per-atom dataset, which do not use
        # the descriptors at all. The two blocks below already refused to let
        # THEIR failures drop the descriptors; the rule now runs both ways.
        try:
            values = self._provider.compute(mol, self._model.uuid)
        except Exception as exc:  # noqa: BLE001 - a bad provider must not kill the pool
            self._fail_descriptors(exc, categories)
        else:
            for value in values:
                self._event_bus.publish(DescriptorComputed(descriptor=value))
                self._record(value)

        try:
            alerts = self._provider.compute_alerts(mol, self._model.uuid)
        except Exception:  # noqa: BLE001 - alerts are an enhancement, must not drop the descriptors above
            logger.exception("Alert computation failed for provider %s", self._provider.provider_id)
            self._part_failed = True
        else:
            for alert in alerts:
                self._event_bus.publish(AlertComputed(alert=alert))
                self._record(alert)

        try:
            datasets = self._provider.compute_per_atom(mol, self._model.uuid)
        except Exception:  # noqa: BLE001 - per-atom data is an enhancement, must not drop the descriptors above
            logger.exception("Per-atom data computation failed for provider %s", self._provider.provider_id)
            self._part_failed = True
        else:
            for dataset in datasets:
                self._event_bus.publish(PerAtomDataComputed(
                    dataset=dataset,
                    input_fingerprint=self._fingerprint,
                    calculation_input=self._calculation_input,
                ))
                self._record(dataset)
        self._finish_part()

    def _fail_descriptors(self, exc: Exception, categories: dict[str, str]) -> None:
        logger.exception("Descriptor provider %s failed", self._provider.provider_id)
        self._part_failed = True
        for descriptor_id in self._provider.descriptor_ids():
            self._publish(
                descriptor_id, CacheState.FAILED, error=str(exc), category=categories.get(descriptor_id, ""),
                record=True,
            )

    def _record(self, result) -> None:
        """Hand the result, with its identity, to whoever retains results."""
        try:
            stored = StoredResult(
                identity=make_identity(
                    molecule_uuid=self._model.uuid,
                    result=result,
                    calculation_input=self._calculation_input,
                    input_fingerprint=self._fingerprint,
                    producer=self._provider.provider_id,
                ),
                result=result,
                application_version=application_version(),
            )
        except Exception:  # noqa: BLE001 - retaining a result must never cost the result
            logger.exception("Could not record a result from %s", self._provider.provider_id)
            self._part_failed = True
            return
        self._produced.append(stored.identity.result_id)
        self._event_bus.publish(ResultRecorded(stored=stored))

    def _finish_part(self) -> None:
        """Say this producer is done, and exactly what it made.

        Only a DRAWING run is part of the always-on set: that is the run a
        selection triggers and the one a replay would stand in for. A
        GEOMETRY run's results are still recorded -- they are replayed on
        top when the conformer is unchanged -- but they vouch for nothing.
        """
        if self._calculation_input != DRAWING:
            return
        self._event_bus.publish(
            AutomaticPartFinished(
                molecule_uuid=self._model.uuid,
                part=BundlePart(
                    part_id=self._provider.provider_id,
                    input_fingerprint=self._fingerprint,
                    result_ids=tuple(self._produced),
                    failed=self._part_failed,
                ),
            )
        )

    def _publish(
        self, descriptor_id: str, state: CacheState, error: str | None = None, category: str = "",
        record: bool = False,
    ) -> None:
        descriptor = DescriptorValue(
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
        self._event_bus.publish(DescriptorComputed(descriptor=descriptor))
        # RUNNING placeholders are never recorded: they are a statement about
        # a run in progress, and replaying one would claim work is happening.
        if record:
            self._record(descriptor)


def _with_geometry_provenance(
    result, model: MoleculeModel, calculation_input: str, parameters: dict | None = None,
    geometry: dict | None = None,
):
    """`result` with which-geometry-was-used merged into its provenance.

    `parameters` records WHAT IT WAS RUN WITH, under the same prefix and
    for the same reason the geometry keys are here: the calculator knows
    what it computed, and only this layer knows what it was asked for.
    Without it a result cannot be replayed -- anything recomputing it
    (the 3D overlay, for the conformer actually on screen) would use
    today's defaults and quietly produce a different calculation under
    the original's name. Defaulted so every existing caller and test
    keeps working; see `recordable_parameters` for why unpersistable
    values are dropped rather than stringified.

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
        merged = dict(geometry if geometry is not None else geometry_provenance(model, calculation_input))
        merged[f"{INPUT_PREFIX}parameters"] = recordable_parameters(parameters)
        merged.update(provenance.parameters)
        return replace(result, provenance=replace(provenance, parameters=merged))
    except Exception:  # noqa: BLE001 - never lose a result over its metadata
        logger.exception("Could not record geometry provenance for %s", model.uuid)
        return result


def _with_structure_version(result, structure_version_of):
    """`result` stamped with the structure revision it describes.

    **REPORT-LEVEL, NEVER PER FACT.** A fact belongs to a report and a
    report belongs to one revision of one molecule; making every fact
    independently responsible for molecule-version state would be dozens
    of copies of one number, all of which have to agree.

    Only a `StructureReport` has the field -- a per-atom dataset, a
    spectrum and a pH curve do not -- so anything else is returned
    untouched rather than grown a field it has no meaning for.

    A calculator that set the version ITSELF is left alone: it knows what
    it computed, and this only knows what the checker's counter said when
    the result came back. Same precedence `_with_geometry_provenance`
    uses, and for the same reason.

    Never lose a result over its metadata -- if the counter cannot be
    consulted, the result comes back exactly as the calculator made it.
    """
    if structure_version_of is None or not isinstance(result, StructureReport):
        return result
    if result.structure_version:
        return result
    try:
        return replace(
            result, structure_version=int(structure_version_of(result.molecule_uuid))
        )
    except Exception:  # noqa: BLE001 - never lose a result over its metadata
        logger.exception("Could not record the structure version for %s", result.molecule_uuid)
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
        structure_version_of=None,
        bundle_part: bool = False,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._engine = engine
        self._model = model
        self._request = request
        self._event_bus = event_bus
        self._structure_version_of = structure_version_of
        #: Whether this calculation is one producer of the always-on set, so
        #: its completion is recorded in the manifest. Only substance
        #: perception is, today.
        self._bundle_part = bundle_part
        self._calculation_input = DRAWING
        self._fingerprint = ""

    def run(self) -> None:
        """Compute, publish, and ALWAYS say when the run is over.

        The `finally` is load-bearing: `CalculationFinished` is what lets
        a caller stop showing "Running..." for a calculator, and the runs
        that most need it are the ones that end badly -- a failure, a
        raise, or a result type nothing knows how to publish. Announcing
        completion only on the happy path would leave exactly those
        spinning forever.
        """
        try:
            self._run()
        finally:
            self._event_bus.publish(
                CalculationFinished(
                    calculator_id=self._request.calculator_id,
                    molecule_uuid=self._model.uuid,
                )
            )

    def _run(self) -> None:
        definition = self._registry.get(self._request.calculator_id)
        if definition is None:
            logger.error("Unknown calculator_id: %s", self._request.calculator_id)
            self._publish_failed(f"Unknown calculator: {self._request.calculator_id}")
            return
        self._calculation_input = definition.calculation_input
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
            #
            # Resolved WITH its fingerprint, so the result is recorded
            # against exactly the input it was computed on.
            self._fingerprint = input_fingerprint(self._engine, self._model, DRAWING)
            resolved = resolve_calculation_input(self._engine, self._model, definition.calculation_input)
            self._fingerprint = resolved.fingerprint
            mol = resolved.mol
            # WHICH CONFORMER, READ WITH THE RESOLUTION, NOT AFTER THE RUN. It
            # used to be read off the live model once the calculator returned,
            # so a conformer search finishing mid-run filed the result under
            # the NEW conformer's id beside the OLD one's fingerprint.
            geometry = geometry_provenance(self._model, definition.calculation_input)
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
                result, self._model, definition.calculation_input, self._request.parameters, geometry=geometry
            )
            # WHICH STRUCTURE this describes, recorded on the way out for
            # the same reason the geometry is: a calculator is handed a
            # molecule and has no idea which revision of it that was.
            #
            # `StructureReport.structure_version` has existed since the
            # report types were written -- "what makes a cached report safe
            # to reuse" -- and was 0 on EVERY calculator result, because
            # `report_from_fields` never set it. The field was there; the
            # plumbing was not. Stamped HERE, once, rather than in each of
            # the sixty calculators or in each panel that displays one.
            result = _with_structure_version(result, self._structure_version_of)
        except CalculationRefusal as refusal:
            # A DECLINE, not a crash: no traceback in the log, and the code,
            # both sentences and the KIND reach the result (round 5, branch
            # S2). A refusal with no kind is a FAULT (`CalculationRefusal`),
            # so it is logged as one: a code nobody classified must surface
            # in a driven run's ledger rather than read as a quiet limit.
            log = logger.info if refusal.kind is not None else logger.warning
            log(
                "Calculator %s refused: %s%s", self._request.calculator_id, refusal.code,
                "" if refusal.kind is not None else " (no refusal kind -- unclassified code)",
            )
            self._publish_failed(
                refusal.detail, summary=refusal.summary, code=refusal.code,
                inapplicable=refusal.inapplicable, kind=refusal.kind,
                missing_inputs=refusal.missing_inputs,
            )
            return
        except Exception as exc:  # noqa: BLE001 - a bad calculator must not kill the pool
            logger.exception("Calculator %s failed", self._request.calculator_id)
            self._publish_failed(str(exc))
            return
        if isinstance(result, PerAtomDataset):
            self._event_bus.publish(PerAtomDataComputed(
                dataset=result,
                input_fingerprint=self._fingerprint,
                calculation_input=self._calculation_input,
            ))
        elif isinstance(result, ReportResult):
            # BEFORE AlertResult, not after: nothing subclasses the other
            # today, but the ordering says which is the specific case if
            # one ever does.
            self._event_bus.publish(ReportComputed(report=result))
        elif isinstance(result, AlertResult):
            self._event_bus.publish(AlertComputed(alert=result))
        elif isinstance(result, SpectrumResult):
            self._event_bus.publish(SpectrumComputed(
                spectrum=result,
                input_fingerprint=self._fingerprint,
                calculation_input=self._calculation_input,
            ))
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
            self._finish_part(None)
            return
        self._record_and_finish(result)

    def _record_and_finish(self, result) -> None:
        """Record the published result with its identity, then close the part.

        EVERY exit of `_run` that published something comes through here or
        through `_finish_part(None)` -- a part left unfinished would read as
        missing forever and rerun on every selection.
        """
        try:
            stored = StoredResult(
                identity=make_identity(
                    molecule_uuid=self._model.uuid,
                    result=result,
                    calculation_input=self._calculation_input,
                    input_fingerprint=self._fingerprint,
                    producer=self._request.calculator_id,
                    parameters=self._request.parameters,
                ),
                result=result,
                application_version=application_version(),
            )
        except Exception:  # noqa: BLE001 - retaining a result must never cost the result
            logger.exception("Could not record the result of %s", self._request.calculator_id)
            self._finish_part(None)
            return
        self._event_bus.publish(ResultRecorded(stored=stored))
        self._finish_part(stored)

    def _finish_part(self, stored: StoredResult | None) -> None:
        if not self._bundle_part or self._calculation_input != DRAWING:
            return
        failed = stored is None or is_failure(stored.result)
        self._event_bus.publish(
            AutomaticPartFinished(
                molecule_uuid=self._model.uuid,
                part=BundlePart(
                    part_id=self._request.calculator_id,
                    input_fingerprint=self._fingerprint,
                    result_ids=(stored.identity.result_id,) if stored is not None else (),
                    failed=failed,
                ),
            )
        )

    def _publish_failed(
        self,
        message: str,
        *,
        summary: str | None = None,
        code: str = "",
        inapplicable: bool = False,
        kind: RefusalKind | None = None,
        missing_inputs: tuple[MissingInput, ...] = (),
    ) -> None:
        # Empty PerAtomDataset is the only "there was a problem" shape
        # every current consumer (PropertyPanel, Calculator Inspector)
        # already knows how to render via ScientificResult.error -- no new
        # event type needed for a calculator-not-found/crashed report.
        dataset = PerAtomDataset(
            property_id=self._request.calculator_id,
            name=self._request.calculator_id,
            units="",
            method="",
            molecule_uuid=self._model.uuid,
            values={},
            cache_state=CacheState.FAILED,
            error=message,
            error_summary=summary,
            inapplicable=inapplicable,
            # The refusal CODE where `debug_drive.result_report` and the
            # multicomponent guard read every other calculator's -- and its
            # KIND and any named inputs beside it, assembled by
            # `refusal_parameters` so a batch cell says the same thing.
            provenance=(
                Provenance(
                    created_by="core", method=self._request.calculator_id,
                    parameters=refusal_parameters(code, kind, missing_inputs),
                )
                if code else None
            ),
        )
        # The fingerprint BEFORE publishing, so the event carries it: a failure
        # is as structure-bound as a success, and a stale one must not read as
        # current.
        if not self._fingerprint:
            self._fingerprint = input_fingerprint(self._engine, self._model, DRAWING)
        self._event_bus.publish(PerAtomDataComputed(
            dataset=dataset,
            input_fingerprint=self._fingerprint,
            calculation_input=self._calculation_input,
        ))
        # Recorded, so the session does not retry a failure on every
        # selection; `SessionResultStore.to_dict` never writes it to a file.
        self._record_and_finish(dataset)


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
        structure_version_of=None,
    ) -> None:
        self._event_bus = event_bus
        self._engine = engine
        self._providers = providers if providers is not None else [RDKitDescriptorProvider()]
        self._calculator_registry = calculator_registry or CalculatorRegistry()
        #: `StructureCheckService.current_version`, or None in a fixture
        #: that has no checker. A CALLABLE rather than the service itself:
        #: this needs one number about one molecule, and taking the whole
        #: service would make every test that builds a DescriptorService
        #: build a checker too.
        self._structure_version_of = structure_version_of
        self._pool = QThreadPool.globalInstance()

    def run_calculator(self, model: MoleculeModel, request: CalculationRequest) -> None:
        """On-demand (not eager) calculator dispatch (Phase 18) -- looks up
        `request.calculator_id` in the injected `CalculatorRegistry` and
        runs it off the GUI thread, publishing the result via the existing
        `PerAtomDataComputed`/`AlertComputed` events based on the result's
        type. Named to avoid colliding with
        `QuantumChemistryService.request_calculation`, an unrelated
        existing ORCA-specific method."""
        self._pool.start(
            _CalculationTask(
                self._calculator_registry, self._engine, model, request,
                self._event_bus, self._structure_version_of,
                # BY ID, not by a flag from the caller: seventeen test doubles
                # implement `run_calculator(model, request)` exactly, and the
                # fact "this calculator is part of the always-on set" belongs
                # to the calculator rather than to whoever happened to ask.
                request.calculator_id in AUTOMATIC_CALCULATOR_IDS,
            )
        )

    def register_provider(self, provider: DescriptorProvider) -> None:
        """Register a plugin-supplied descriptor provider. Its descriptors
        run alongside the built-in ones for every future request."""
        self._providers.append(provider)

    def unregister_provider(self, provider_id: str) -> None:
        self._providers = [p for p in self._providers if p.provider_id != provider_id]

    def provider_ids(self) -> list[str]:
        """Every registered provider, which is what the always-on set holds."""
        return [p.provider_id for p in self._providers]

    def request_descriptors(
        self,
        model: MoleculeModel,
        calculation_input: str = DRAWING,
        only_providers: set[str] | None = None,
    ) -> None:
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
            # `only_providers` is how a partial restore reruns just the part
            # that did not come back, rather than the whole set.
            if only_providers is not None and provider.provider_id not in only_providers:
                continue
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
