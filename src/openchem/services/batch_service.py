"""Running the whole registry across the whole project.

Every other service here computes for ONE molecule. This one takes a set
of molecules and a set of properties and fills a table, which is the
capability the rest of Thread 2 is built on -- correlation, PCA,
clustering, statistics and virtual screening all read a `BatchTable`.

ONE TASK FOR THE WHOLE RUN, not one per molecule. Two reasons, and the
second is the real one. Progress: "molecule 47 of 200" is the only useful
report, and N independent tasks completing out of order cannot produce it.
Cancellation: a user who cancels a 200-molecule run wants it to stop, and
with N queued tasks that means cancelling each of them, where the pool has
already started an unknown number. One task checks one flag between
molecules and stops.

The cost of that choice is that the run is single-threaded. Measured on
the reference machine, the whole registry over one molecule is dominated
by two out-of-process sidecars, so parallelism across molecules would
help; it is not done here because the sidecars are themselves serialised
by their own single interpreter, and a 4x fan-out over calculators that
are milliseconds each buys nothing. If a project of thousands ever makes
this hurt, the shape to change is this task, not its callers.

PARTIAL RESULTS ARE PUBLISHED AS THEY ARRIVE. A 200-molecule run is
minutes long, and a table that appears only at the end is indistinguishable
from one that is broken. `BatchProgress` carries the table as it stands,
so the panel fills row by row.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace

from PySide6.QtCore import QRunnable, QThreadPool

from openchem.chem.descriptor_providers import RDKitDescriptorProvider, geometric_descriptor_ids_of
from openchem.chem.calculation_input import geometry_provenance, resolve_calculation_input
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import DRAWING, GEOMETRY, CalculationRefusal
from openchem.domain.refusal_kinds import refusal_parameters
from openchem.chem.result_reduction import (
    alert_catalog_columns,
    descriptor_cell,
    descriptor_column,
    reduce_result,
)
from openchem.domain.batch import (
    BatchCell,
    BatchColumn,
    BatchRequest,
    BatchResultStore,
    BatchTable,
    ResultKey,
    SOURCE_CALCULATOR,
    SOURCE_DERIVED,
)
from openchem.domain.common import CacheState, Provenance
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import PerAtomDataset
from openchem.events.base import Event, EventBus
from openchem.plugins.interfaces import DescriptorProvider
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.result_cache import parameters_key
from openchem.services.job_manager import JobManager
from openchem.services.progress import ProgressHandle

logger = logging.getLogger("openchem.chemistry")

BATCH_JOB_KIND = "batch"

#: Only one batch run at a time, project-wide. `JobManager` keys on
#: (kind, key), and a second concurrent run would compete for the same
#: sidecar interpreters and produce a second table nothing would know what
#: to do with. A single fixed key makes "is a batch running" answerable
#: without the caller knowing which one.
BATCH_JOB_KEY = "project"


@dataclass(frozen=True)
class BatchProgress(Event):
    """One step of a run: how far it has got, and the table so far.

    `table` is the SAME object throughout a run, mutated between
    publications rather than copied. Copying a 200x100 table once per
    molecule is real work for no benefit -- the bus delivers synchronously
    onto the GUI thread, and no consumer keeps a reference expecting an
    earlier snapshot.
    """

    state: CacheState
    completed: int
    total: int
    message: str = ""
    table: BatchTable | None = None
    error: str | None = None
    #: The un-reduced results, keyed by identity.
    #:
    #: **THE TABLE IS A PROJECTION OF THIS, NOT THE OTHER WAY ROUND.**
    #: `reduce_result` recovers 73 numeric columns from the real registry
    #: and refuses 25 real lines outright, so a panel reading only `table`
    #: cannot offer the Details view, the inspector or the comparison that
    #: Properties has offered for the same calculators all along. Carried
    #: on the same event and mutated in place for the same reason `table`
    #: is: copying it once per molecule is real work for no benefit.
    store: BatchResultStore | None = None


class _BatchTask(QRunnable):
    def __init__(
        self,
        request: BatchRequest,
        molecules: list[MoleculeModel],
        registry: CalculatorRegistry,
        engine: ChemistryEngine,
        providers: list[DescriptorProvider],
        event_bus: EventBus,
        job_manager: JobManager,
        progress: ProgressHandle,
    ) -> None:
        super().__init__()
        self._request = request
        self._molecules = molecules
        self._registry = registry
        self._engine = engine
        self._providers = providers
        self._event_bus = event_bus
        self._job_manager = job_manager
        self._progress = progress
        self._store = BatchResultStore()

    def run(self) -> None:
        table = BatchTable()
        # **THE REQUEST IS THE AUTHORITY ON SCOPE.** `molecule_uuids` was
        # written by every caller and READ BY NOTHING -- the task iterated
        # whatever list it was handed, so a request naming two molecules
        # while the caller passed twenty would run twenty and nobody would
        # notice. Found by mutation: changing the request's scope to the
        # whole project changed no behaviour at all.
        #
        # An empty list still means "everything given", which is what the
        # older callers and fixtures rely on -- a request that names
        # nothing is not a request to compute nothing.
        wanted = set(self._request.molecule_uuids)
        if wanted:
            self._molecules = [m for m in self._molecules if m.uuid in wanted]
        total = len(self._molecules)
        try:
            for index, molecule in enumerate(self._molecules):
                if self._progress.is_cancelled():
                    self._publish(
                        CacheState.FAILED,
                        index,
                        total,
                        table,
                        message=f"Cancelled after {index} of {total} molecules.",
                    )
                    return
                table.add_row(molecule.uuid, molecule.display_name)
                self._fill_row(table, molecule)
                self._publish(
                    CacheState.RUNNING,
                    index + 1,
                    total,
                    table,
                    message=f"{index + 1}/{total}: {molecule.display_name}",
                )
        except Exception as exc:  # noqa: BLE001 - a bad run must not kill the pool
            logger.exception("Batch run failed")
            self._publish(CacheState.FAILED, 0, total, table, error=str(exc))
            return
        finally:
            self._job_manager.finish(BATCH_JOB_KIND, BATCH_JOB_KEY)
        self._publish(CacheState.COMPLETED, total, total, table, message=f"{total} molecules.")

    def _publish(
        self,
        state: CacheState,
        completed: int,
        total: int,
        table: BatchTable,
        message: str = "",
        error: str | None = None,
    ) -> None:
        self._job_manager.update_message(BATCH_JOB_KIND, BATCH_JOB_KEY, message)
        self._event_bus.publish(
            BatchProgress(
                state=state,
                completed=completed,
                total=total,
                message=message,
                table=table,
                error=error,
                store=self._store,
            )
        )

    def _fill_row(self, table: BatchTable, molecule: MoleculeModel) -> None:
        """Every requested column for one molecule.

        A molecule with no structure yet still gets a row, with every cell
        FAILED and a reason. Skipping it would silently shorten the table
        and leave the user counting rows to work out which one is missing.
        """
        # Checked before calling, not caught afterwards: `mol_from_model`
        # raises `InvalidStructureError("Molecule <uuid> has no molblock")`,
        # and a uuid in a table cell is not an explanation for someone who
        # simply has not drawn that molecule yet.
        if not molecule.molblock:
            self._fail_row(table, molecule, "This molecule has no structure yet.")
            return
        try:
            drawing = self._engine.mol_from_model(molecule)
        except Exception as exc:  # noqa: BLE001 - one bad structure must not end the run
            logger.exception("Batch could not read molecule %s", molecule.uuid)
            self._fail_row(table, molecule, f"Could not read this structure: {exc}")
            return
        # **EACH PROPERTY IS COMPUTED ON THE INPUT THAT BELONGS TO IT, as the Properties
        # panel does -- not on a conformer wherever one exists.** This used to resolve
        # `GEOMETRY` once and hand that molecule to every descriptor and every
        # calculator, so a molecule with a conformer had its Synthetic Accessibility,
        # Bertz CT and H-bond acceptor columns computed on the explicit-hydrogen
        # conformer (aspirin: 1.58 -> 6.445, 343 -> 609, 3 -> 4) while the same
        # molecule's Properties reader showed the drawing's. The geometric descriptors
        # (the shape family) are the only always-on ones that need the conformer; a
        # registered calculator gets what its definition declares.
        # `resolve_calculation_input` owns the choice and the fallback.
        self._run_descriptors(table, molecule, drawing)
        self._run_calculators(table, molecule, drawing)

    def _fail_row(self, table: BatchTable, molecule: MoleculeModel, reason: str) -> None:
        """Mark every column of this row as failed, with the reason.

        Falls back to a single Status column when the failure lands on the
        first molecule, since there are no columns yet to hang the reason
        on and a row of nothing explains nothing.
        """
        columns = table.columns or [_status_column()]
        for column in columns:
            table.add_column(column)
            table.set_cell(
                molecule.uuid,
                column.column_id,
                BatchCell(text="", cache_state=CacheState.FAILED, error=reason),
            )

    def _run_descriptors(self, table: BatchTable, molecule: MoleculeModel, drawing) -> None:
        wanted = set(self._request.descriptor_ids)
        if not wanted:
            return
        for provider in self._providers:
            provided = set(provider.descriptor_ids())
            if wanted & provided:
                self._run_one_provider(table, molecule, drawing, provider, wanted)
            # Alert catalogs are requested through the SAME `descriptor_ids`
            # list -- from the user's side PAINS and TPSA are the same kind
            # of thing, a per-molecule property this provider computes, and
            # a second parallel selection list would have to be explained.
            # Only run them when one was actually asked for: the built-in
            # catalogs are 585 SMARTS patterns per molecule.
            if wanted & set(provider.alert_ids()):
                self._run_alerts(table, molecule, drawing, provider, wanted)

    def _run_one_provider(self, table: BatchTable, molecule: MoleculeModel, drawing, provider, wanted: set[str]) -> None:
        try:
            values = provider.compute(drawing, molecule.uuid)
        except Exception as exc:  # noqa: BLE001 - one provider must not end the run
            logger.exception("Descriptor provider %s failed in batch", provider.provider_id)
            for descriptor_id in sorted(wanted & set(provider.descriptor_ids())):
                table.set_cell(
                    molecule.uuid,
                    f"descriptor:{descriptor_id}",
                    BatchCell(text="", cache_state=CacheState.FAILED, error=str(exc)),
                )
            return
        values = self._with_geometric_values(molecule, provider, values, wanted)
        for value in values:
            if value.descriptor_id not in wanted:
                continue
            column = descriptor_column(value)
            table.add_column(column)
            table.set_cell(molecule.uuid, column.column_id, descriptor_cell(value))

    def _with_geometric_values(self, molecule: MoleculeModel, provider, values, wanted: set[str]):
        """`values` with the provider's GEOMETRIC descriptors measured on the conformer.

        The same split the Properties panel makes (`DescriptorService.request_descriptors`):
        every other descriptor is a property of the structure graph and keeps the DRAWING's
        value. Costs a second `compute` only for a molecule that has a usable conformer and a
        request that names a geometric descriptor; a molecule without one keeps the drawing's
        honest "needs a 3D conformer".
        """
        geometric = geometric_descriptor_ids_of(provider) & wanted
        if not geometric:
            return values
        resolved = resolve_calculation_input(self._engine, molecule, GEOMETRY)
        if resolved.used != GEOMETRY:
            return values
        try:
            measured = {v.descriptor_id: v for v in provider.compute(resolved.mol, molecule.uuid)}
        except Exception as exc:  # noqa: BLE001 - the structure-level columns do not depend on it
            logger.exception("Descriptor provider %s failed on the conformer in batch", provider.provider_id)
            return [
                replace(v, value=None, cache_state=CacheState.FAILED, error=str(exc), error_summary=None)
                if v.descriptor_id in geometric else v
                for v in values
            ]
        # Stamped with the conformer it was measured on, as a stored geometry result is (`geometry_provenance`), so the table's score hover can name it. The provider's own keys win a collision.
        stamp = geometry_provenance(molecule, GEOMETRY)
        return [_stamped(measured[v.descriptor_id], stamp) if v.descriptor_id in geometric and v.descriptor_id in measured else v for v in values]

    def _run_alerts(self, table: BatchTable, molecule: MoleculeModel, drawing, provider, wanted: set[str]) -> None:
        try:
            alerts = provider.compute_alerts(drawing, molecule.uuid)
        except Exception:  # noqa: BLE001 - alerts are an enhancement here too
            logger.exception("Alert computation failed in batch for %s", provider.provider_id)
            return
        for alert in alerts:
            if alert.alert_id not in wanted:
                continue
            for column, cell in alert_catalog_columns(alert):
                table.add_column(column)
                table.set_cell(molecule.uuid, column.column_id, cell)

    def _run_calculators(self, table: BatchTable, molecule: MoleculeModel, drawing) -> None:
        #: The molecule each declared input resolves to, resolved once per row.
        inputs = {DRAWING: drawing}
        #: Whether a calculator that declares GEOMETRY was really handed a conformer (it is handed the drawing when the molecule has none).
        handed_conformer = False
        for calculator_id in self._request.calculator_ids:
            if self._progress.is_cancelled():
                return
            definition = self._registry.get(calculator_id)
            if definition is None:
                continue
            parameters = self._request.parameters.get(
                calculator_id, {p.name: p.default for p in definition.parameters}
            )
            started = time.time()
            try:
                # What its definition DECLARES, as `DescriptorService.run_calculator` hands it.
                # Measured over the 29-molecule census panel with every molecule given a
                # conformer: 22 of the 51 drawing-declared calculators changed their answer
                # when handed it (234 of 1479 cells; none was unstable on its own input),
                # purely because the conformer's hydrogens are atoms. A batch must not differ
                # from the Properties panel it is the table form of.
                declared = definition.calculation_input
                if declared not in inputs:
                    resolved = resolve_calculation_input(self._engine, molecule, declared)
                    inputs[declared] = resolved.mol
                    handed_conformer = handed_conformer or (declared == GEOMETRY and resolved.used == GEOMETRY)
                result = self._registry.compute(calculator_id, inputs[declared], molecule.uuid, parameters)
                # Stamped with the conformer it was handed, as `DescriptorService.run_calculator` stamps a stored result (`geometry_provenance`), so a derived score that reads this cell names the conformer and
                # can refuse a structure of several fragments. The calculator's own keys win a collision.
                if declared == GEOMETRY and handed_conformer and getattr(result, "provenance", None) is not None:
                    result = _stamped(result, geometry_provenance(molecule, GEOMETRY))
            except Exception as exc:  # noqa: BLE001 - one calculator must not end the run
                refused = isinstance(exc, CalculationRefusal)
                if refused:
                    logger.info("Calculator %s refused in batch: %s", calculator_id, exc.code)
                else:
                    logger.exception("Calculator %s failed in batch", calculator_id)
                column_id = f"calculator:{calculator_id}"
                if table.column(column_id) is None:
                    table.add_column(_failed_column(calculator_id, definition.display_name))
                table.set_cell(
                    molecule.uuid,
                    column_id,
                    BatchCell(
                        text="", cache_state=CacheState.FAILED, error=str(exc),
                        # The same code Properties records, so a batch cell
                        # and a Properties row say WHICH refusal alike.
                        provenance=(
                            Provenance(created_by="core", method=calculator_id,
                                       parameters=refusal_parameters(
                                           exc.code, exc.kind, exc.missing_inputs,
                                           classified=exc.classified))
                            if refused else None
                        ),
                    ),
                )
                continue
            logger.debug("batch %s on %s took %.3fs", calculator_id, molecule.uuid, time.time() - started)
            # Keep the un-reduced per-atom result before `reduce_result`
            # collapses it to one number. The comparison view is built from
            # this; without it, asking a per-atom follow-up means running
            # every calculator again.
            if isinstance(result, PerAtomDataset):
                table.set_per_atom(molecule.uuid, calculator_id, result)
            # RETAINED, NOT REDUCED-AND-DROPPED. The whole object is in
            # hand here and used to be discarded the moment
            # `reduce_result` had taken its numbers out of it -- which is
            # why a batch row could not offer the Details view, the
            # inspector or the comparison that Properties has offered for
            # the same calculators all along.
            self._store.put(
                ResultKey(
                    molecule_uuid=molecule.uuid,
                    calculator_id=calculator_id,
                    parameters_key=parameters_key(parameters),
                    structure_version=self._request.structure_versions.get(
                        molecule.uuid, self._request.structure_version
                    ),
                ),
                result,
            )
            for column, cell in reduce_result(
                result,
                calculator_id,
                definition.display_name,
                definition.prediction_basis,
                self._request.per_atom_aggregate,
            ):
                table.add_column(column)
                table.set_cell(molecule.uuid, column.column_id, cell)


def _stamped(value, stamp: dict):
    """`value` with `stamp` merged into its provenance, the provider's own keys winning a collision. A value with no provenance is returned as it is."""
    if value.provenance is None:
        return value
    return replace(value, provenance=replace(value.provenance, parameters={**stamp, **value.provenance.parameters}))


def _status_column() -> BatchColumn:
    return BatchColumn(
        column_id="derived:status",
        label="Status",
        source=SOURCE_DERIVED,
        source_id="status",
        numeric=False,
    )


def _failed_column(calculator_id: str, display_name: str) -> BatchColumn:
    return BatchColumn(
        column_id=f"calculator:{calculator_id}",
        label=display_name,
        source=SOURCE_CALCULATOR,
        source_id=calculator_id,
        numeric=False,
    )


class BatchService:
    """Schedules one batch run at a time, through the shared `JobManager`.

    Takes molecules as an argument rather than holding a project, matching
    every other service here: services compute, they do not own document
    state. The caller decides whether "the project" means all of it or a
    selection.
    """

    def __init__(
        self,
        event_bus: EventBus,
        engine: ChemistryEngine,
        calculator_registry: CalculatorRegistry,
        providers: list[DescriptorProvider] | None = None,
        job_manager: JobManager | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._engine = engine
        self._registry = calculator_registry
        self._providers = providers if providers is not None else [RDKitDescriptorProvider()]
        self._pool = QThreadPool.globalInstance()
        self._job_manager = job_manager if job_manager is not None else JobManager()

    def register_provider(self, provider: DescriptorProvider) -> None:
        self._providers.append(provider)

    def unregister_provider(self, provider_id: str) -> None:
        self._providers = [p for p in self._providers if p.provider_id != provider_id]

    def is_running(self) -> bool:
        return self._job_manager.is_active(BATCH_JOB_KIND, BATCH_JOB_KEY)

    def request_batch(self, request: BatchRequest, molecules: list[MoleculeModel]) -> None:
        """Start a run, or report why it cannot start.

        Refusing loudly rather than silently: an empty selection and an
        already-running job both look identical from a panel that just
        greys a button, and both are worth a sentence.
        """
        if not molecules:
            self._reject("No molecules to run -- add or select some first.")
            return
        if not request.descriptor_ids and not request.calculator_ids:
            self._reject("Nothing selected to compute -- choose at least one property.")
            return
        progress = ProgressHandle()
        if not self._job_manager.try_start(BATCH_JOB_KIND, BATCH_JOB_KEY, cancel_callback=progress.cancel):
            self._reject("A batch run is already in progress.")
            return
        self._event_bus.publish(
            BatchProgress(state=CacheState.QUEUED, completed=0, total=len(molecules), table=BatchTable())
        )
        self._pool.start(
            _BatchTask(
                request,
                molecules,
                self._registry,
                self._engine,
                self._providers,
                self._event_bus,
                self._job_manager,
                progress,
            )
        )

    def cancel(self) -> bool:
        return self._job_manager.cancel(BATCH_JOB_KIND, BATCH_JOB_KEY)

    def _reject(self, message: str) -> None:
        self._event_bus.publish(
            BatchProgress(state=CacheState.FAILED, completed=0, total=0, message=message, error=message)
        )
