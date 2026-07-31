"""Schedules ensemble 3D alignment off the GUI thread.

Same shape as `ConformerService`: a `QRunnable` on the shared pool, moved
through Queued -> Running -> Completed|Failed via `JobManager`, with
cancellation through `ProgressHandle`. It exists rather than routing
through `CalculatorRegistry` for the reason Phase 21 already recorded for
docking -- the registry's `compute(mol, molecule_uuid, parameters)`
contract takes ONE molecule, and an ensemble alignment is inherently
N-to-one.

Cancellation is checked between molecules, which is the same best-effort
granularity conformer generation already settles for: a single `GetO3A`
call is not preemptible from outside.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QRunnable, QThreadPool

from openchem.chem.alignment import DEFAULT_ACCURACY, align_ensemble
from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import AlignmentJobStateChanged, EnsembleAlignmentReady
from openchem.services.job_manager import JobManager
from openchem.services.progress import ProgressHandle

_JOB_KIND = "alignment"

logger = logging.getLogger("openchem.chemistry")


class _CancelledError(RuntimeError):
    """Raised out of the progress callback to stop `align_ensemble`
    mid-run. `align_ensemble` records per-molecule failures rather than
    aborting, which is right for a bad structure and wrong for a user
    cancel -- so cancellation has to unwind the whole call instead."""


class _EnsembleAlignmentTask(QRunnable):
    def __init__(
        self,
        engine: ChemistryEngine,
        reference: MoleculeModel,
        probes: list[MoleculeModel],
        method: str,
        accuracy: str,
        event_bus: EventBus,
        job_manager: JobManager,
        progress: ProgressHandle,
    ) -> None:
        super().__init__()
        self._engine = engine
        self._reference = reference
        self._probes = probes
        self._method = method
        self._accuracy = accuracy
        self._event_bus = event_bus
        self._job_manager = job_manager
        self._progress = progress

    def run(self) -> None:
        uuid = self._reference.uuid
        self._event_bus.publish(
            AlignmentJobStateChanged(reference_uuid=uuid, state=CacheState.RUNNING)
        )
        try:
            reference_mol = self._engine.mol_from_model(self._reference)
            probes = [
                (model.display_name, self._engine.mol_from_model(model)) for model in self._probes
            ]
            entries = align_ensemble(
                probes,
                reference_mol,
                reference_label=f"{self._reference.display_name} (reference)",
                method=self._method,
                accuracy=self._accuracy,
                on_progress=self._on_progress,
            )
        except _CancelledError:
            self._fail(uuid, "Cancelled by user")
            return
        except Exception as exc:  # noqa: BLE001 - report failure, never crash the pool
            logger.exception("Ensemble alignment failed against reference %s", uuid)
            self._fail(uuid, str(exc))
            return

        self._event_bus.publish(
            EnsembleAlignmentReady(
                reference_uuid=uuid,
                entries=entries,
                method=self._method,
                accuracy=self._accuracy,
            )
        )
        self._event_bus.publish(
            AlignmentJobStateChanged(reference_uuid=uuid, state=CacheState.COMPLETED)
        )
        self._job_manager.finish(_JOB_KIND, uuid)

    def _fail(self, uuid: str, message: str) -> None:
        self._event_bus.publish(
            AlignmentJobStateChanged(reference_uuid=uuid, state=CacheState.FAILED, message=message)
        )
        self._job_manager.finish(_JOB_KIND, uuid)

    def _on_progress(self, done: int, total: int, label: str) -> None:
        if self._progress.is_cancelled():
            raise _CancelledError
        message = f"Aligning {label} ({done + 1}/{total})"
        self._job_manager.update_message(_JOB_KIND, self._reference.uuid, message)
        self._event_bus.publish(
            AlignmentJobStateChanged(
                reference_uuid=self._reference.uuid, state=CacheState.RUNNING, message=message
            )
        )


class AlignmentService:
    def __init__(
        self,
        event_bus: EventBus,
        engine: ChemistryEngine,
        job_manager: JobManager | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._engine = engine
        self._pool = QThreadPool.globalInstance()
        self._job_manager = job_manager if job_manager is not None else JobManager()

    def request_alignment(
        self,
        reference: MoleculeModel,
        probes: list[MoleculeModel],
        method: str = "atom_types",
        accuracy: str = DEFAULT_ACCURACY,
    ) -> None:
        if not probes:
            self._event_bus.publish(
                AlignmentJobStateChanged(
                    reference_uuid=reference.uuid,
                    state=CacheState.FAILED,
                    message="Select at least one molecule to align onto the reference.",
                )
            )
            return
        progress = ProgressHandle()
        if not self._job_manager.try_start(
            _JOB_KIND, reference.uuid, cancel_callback=progress.cancel
        ):
            self._event_bus.publish(
                AlignmentJobStateChanged(
                    reference_uuid=reference.uuid,
                    state=CacheState.FAILED,
                    message="An alignment job is already running against this reference.",
                )
            )
            return
        self._event_bus.publish(
            AlignmentJobStateChanged(reference_uuid=reference.uuid, state=CacheState.QUEUED)
        )
        self._pool.start(
            _EnsembleAlignmentTask(
                self._engine,
                reference,
                probes,
                method,
                accuracy,
                self._event_bus,
                self._job_manager,
                progress,
            )
        )
