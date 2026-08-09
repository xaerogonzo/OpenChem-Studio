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
from dataclasses import dataclass

from PySide6.QtCore import QRunnable, QThreadPool

from openchem.chem.descriptor_providers import RDKitDescriptorProvider
from openchem.chem.calculation_input import select_calculation_input
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import GEOMETRY
from openchem.chem.result_reduction import (
    alert_catalog_columns,
    descriptor_cell,
    descriptor_column,
    reduce_result,
)
from openchem.domain.batch import (
    SOURCE_CALCULATOR,
    SOURCE_DERIVED,
    BatchCell,
    BatchColumn,
    BatchRequest,
    BatchTable,
)
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import PerAtomDataset
from openchem.events.base import Event, EventBus
from openchem.plugins.interfaces import DescriptorProvider
from openchem.services.calculator_registry import CalculatorRegistry
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

    def run(self) -> None:
        table = BatchTable()
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
                state=state, completed=completed, total=total, message=message, table=table, error=error
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
            mol = self._engine.mol_from_model(molecule)
        except Exception as exc:  # noqa: BLE001 - one bad structure must not end the run
            logger.exception("Batch could not read molecule %s", molecule.uuid)
            self._fail_row(table, molecule, f"Could not read this structure: {exc}")
            return
        # A 3D conformer where one exists, for the same reason MainWindow
        # passes one to `request_descriptors`: shape and surface descriptors
        # compute for real against a real conformer and report "needs a
        # conformer" against the flat 2D molblock.
        # `select_calculation_input` owns the choice and the fallback,
        # including the unusable-molblock case this used to handle inline.
        mol = select_calculation_input(self._engine, molecule, GEOMETRY)
        self._run_descriptors(table, molecule, mol)
        self._run_calculators(table, molecule, mol)

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

    def _run_descriptors(self, table: BatchTable, molecule: MoleculeModel, mol) -> None:
        wanted = set(self._request.descriptor_ids)
        if not wanted:
            return
        for provider in self._providers:
            provided = set(provider.descriptor_ids())
            if wanted & provided:
                self._run_one_provider(table, molecule, mol, provider, wanted)
            # Alert catalogs are requested through the SAME `descriptor_ids`
            # list -- from the user's side PAINS and TPSA are the same kind
            # of thing, a per-molecule property this provider computes, and
            # a second parallel selection list would have to be explained.
            # Only run them when one was actually asked for: the built-in
            # catalogs are 585 SMARTS patterns per molecule.
            if wanted & set(provider.alert_ids()):
                self._run_alerts(table, molecule, mol, provider, wanted)

    def _run_one_provider(self, table: BatchTable, molecule: MoleculeModel, mol, provider, wanted: set[str]) -> None:
        try:
            values = provider.compute(mol, molecule.uuid)
        except Exception as exc:  # noqa: BLE001 - one provider must not end the run
            logger.exception("Descriptor provider %s failed in batch", provider.provider_id)
            for descriptor_id in sorted(wanted & set(provider.descriptor_ids())):
                table.set_cell(
                    molecule.uuid,
                    f"descriptor:{descriptor_id}",
                    BatchCell(text="", cache_state=CacheState.FAILED, error=str(exc)),
                )
            return
        for value in values:
            if value.descriptor_id not in wanted:
                continue
            column = descriptor_column(value)
            table.add_column(column)
            table.set_cell(molecule.uuid, column.column_id, descriptor_cell(value))

    def _run_alerts(self, table: BatchTable, molecule: MoleculeModel, mol, provider, wanted: set[str]) -> None:
        try:
            alerts = provider.compute_alerts(mol, molecule.uuid)
        except Exception:  # noqa: BLE001 - alerts are an enhancement here too
            logger.exception("Alert computation failed in batch for %s", provider.provider_id)
            return
        for alert in alerts:
            if alert.alert_id not in wanted:
                continue
            for column, cell in alert_catalog_columns(alert):
                table.add_column(column)
                table.set_cell(molecule.uuid, column.column_id, cell)

    def _run_calculators(self, table: BatchTable, molecule: MoleculeModel, mol) -> None:
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
                result = self._registry.compute(calculator_id, mol, molecule.uuid, parameters)
            except Exception as exc:  # noqa: BLE001 - one calculator must not end the run
                logger.exception("Calculator %s failed in batch", calculator_id)
                column_id = f"calculator:{calculator_id}"
                if table.column(column_id) is None:
                    table.add_column(_failed_column(calculator_id, definition.display_name))
                table.set_cell(
                    molecule.uuid,
                    column_id,
                    BatchCell(text="", cache_state=CacheState.FAILED, error=str(exc)),
                )
                continue
            logger.debug("batch %s on %s took %.3fs", calculator_id, molecule.uuid, time.time() - started)
            # Keep the un-reduced per-atom result before `reduce_result`
            # collapses it to one number. The comparison view is built from
            # this; without it, asking a per-atom follow-up means running
            # every calculator again.
            if isinstance(result, PerAtomDataset):
                table.set_per_atom(molecule.uuid, calculator_id, result)
            for column, cell in reduce_result(
                result,
                calculator_id,
                definition.display_name,
                definition.prediction_basis,
                self._request.per_atom_aggregate,
            ):
                table.add_column(column)
                table.set_cell(molecule.uuid, column.column_id, cell)


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
