"""Docking N ligands into one receptor, in order, and ranking them.

`DockingService` docks ONE ligand into ONE receptor. Virtual screening is
that N times, and the only genuinely new thing it needs is a queue --
which is not a detail. Handing N requests to `DockingService` at once
would start N Vina processes on the thread pool simultaneously; measured
runtimes for a single ligand are seconds to minutes, so a 50-ligand screen
would launch 50 concurrent Vina runs and compete for every core on the
machine at once. This runs them one at a time.

SEQUENCED BY LISTENING, NOT BY BLOCKING. The next ligand is submitted from
the handler for the previous one's terminal event, so nothing here holds a
thread waiting. `EventBus.publish` is a queued Qt signal, so those handlers
run on the GUI thread even though the docking task that published them ran
on a worker -- which is exactly where the next `request_docking` should be
made from.

WHY THE RECEPTOR IS ONE AND THE LIGANDS ARE MANY. That asymmetry is the
whole point of a screen and it is also what makes the result comparable:
every score comes from the same receptor, the same box and the same
scoring function, so the RANKING means something even though the absolute
kcal/mol do not. This project has already been bitten by the opposite --
a docking result and its analysis reading different receptors -- so the
receptor is captured once, at request time, and never re-resolved per
ligand.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.docking import DockingBox
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import Event, EventBus
from openchem.events.events import DockingJobStateChanged, DockingResultReady
from openchem.services.docking_service import DEFAULT_NUM_POSES, DockingService
from openchem.services.job_manager import JobManager

logger = logging.getLogger("openchem.chemistry")

SCREENING_JOB_KIND = "screening"
SCREENING_JOB_KEY = "project"


@dataclass(frozen=True, kw_only=True)
class ScreeningEntry:
    """One ligand's outcome.

    `best_affinity_kcal_mol` is the MINIMUM over the poses, because Vina
    reports affinities as negative numbers where more negative is better --
    a max would rank the worst pose of each ligand, which is a mistake that
    produces a plausible-looking and exactly inverted table.

    A failed ligand keeps its row with an `error`. A screen where 3 of 50
    ligands failed to prepare is a normal outcome, and dropping them would
    make the screen look like it covered a library it did not.
    """

    molecule_uuid: str
    display_name: str
    best_affinity_kcal_mol: float | None = None
    pose_count: int = 0
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None


@dataclass(frozen=True)
class ScreeningProgress(Event):
    """How far a screen has got, and every result so far, best first."""

    state: CacheState
    completed: int
    total: int
    receptor_macromolecule_uuid: str = ""
    message: str = ""
    entries: list[ScreeningEntry] = field(default_factory=list)
    error: str | None = None


class ScreeningService:
    """One screen at a time, tracked through the shared `JobManager`."""

    def __init__(
        self,
        event_bus: EventBus,
        docking_service: DockingService,
        engine: ChemistryEngine,
        job_manager: JobManager | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._docking_service = docking_service
        self._engine = engine
        self._job_manager = job_manager if job_manager is not None else JobManager()
        self._queue: list[MoleculeModel] = []
        self._names: dict[str, str] = {}
        self._entries: list[ScreeningEntry] = []
        self._receptor: MacromoleculeModel | None = None
        self._box: DockingBox | None = None
        self._num_poses = DEFAULT_NUM_POSES
        self._prep_options: dict[str, Any] = {}
        self._total = 0
        self._current_uuid: str | None = None
        self._cancelled = False
        event_bus.subscribe(DockingResultReady, self._on_docking_result)
        event_bus.subscribe(DockingJobStateChanged, self._on_docking_state)

    def is_running(self) -> bool:
        return self._job_manager.is_active(SCREENING_JOB_KIND, SCREENING_JOB_KEY)

    def request_screen(
        self,
        ligands: list[MoleculeModel],
        receptor: MacromoleculeModel,
        box: DockingBox,
        num_poses: int = DEFAULT_NUM_POSES,
        receptor_prep_options: dict[str, Any] | None = None,
    ) -> None:
        if not ligands:
            self._reject("No ligands selected to screen.")
            return
        if not self._job_manager.try_start(
            SCREENING_JOB_KIND, SCREENING_JOB_KEY, cancel_callback=self.cancel
        ):
            self._reject("A virtual screen is already in progress.")
            return
        self._queue = list(ligands)
        self._names = {molecule.uuid: molecule.display_name for molecule in ligands}
        self._entries = []
        self._receptor = receptor
        self._box = box
        self._num_poses = num_poses
        self._prep_options = dict(receptor_prep_options or {})
        self._total = len(ligands)
        self._cancelled = False
        self._publish(CacheState.QUEUED, f"{self._total} ligands against {receptor.display_name}")
        self._submit_next()

    def cancel(self) -> None:
        """Stop after the ligand currently in Vina.

        Best-effort, and the limit is inherited rather than introduced:
        `VinaDockingProvider` checks for cancellation at its own phase
        boundaries, and the search itself is one blocking call neither Vina
        backend interrupts. So a cancelled screen stops submitting; it does
        not kill the run already in flight.
        """
        self._cancelled = True
        self._queue.clear()

    # -- the queue --------------------------------------------------------

    def _submit_next(self) -> None:
        if self._cancelled or not self._queue:
            self._finish()
            return
        molecule = self._queue.pop(0)
        self._current_uuid = molecule.uuid
        # Checked before calling, not caught afterwards: `mol_from_model`
        # raises `InvalidStructureError("Molecule <uuid> has no molblock")`,
        # and a uuid is not something to show a user who simply has not
        # drawn the molecule yet.
        if not molecule.molblock:
            self._record(molecule.uuid, molecule.display_name, error="This molecule has no structure yet.")
            self._submit_next()
            return
        try:
            mol = self._engine.mol_from_model(molecule)
        except Exception as exc:  # noqa: BLE001 - one bad ligand must not end the screen
            logger.exception("Screening could not read ligand %s", molecule.uuid)
            self._record(molecule.uuid, molecule.display_name, error=f"Could not read this structure: {exc}")
            self._submit_next()
            return
        self._publish(
            CacheState.RUNNING,
            f"{len(self._entries) + 1}/{self._total}: docking {molecule.display_name}",
        )
        self._docking_service.request_docking(
            ligand_molecule_uuid=molecule.uuid,
            ligand_mol=mol,
            receptor_macromolecule_uuid=self._receptor.uuid,
            receptor_structure_text=self._receptor.structure_text,
            receptor_source_format=self._receptor.source_format,
            box=self._box,
            num_poses=self._num_poses,
            receptor_prep_options=self._prep_options,
        )

    def _on_docking_result(self, event: DockingResultReady) -> None:
        if not self._is_ours(event.result.ligand_molecule_uuid):
            return
        poses = event.result.poses
        best = min((pose.binding_affinity_kcal_mol for pose in poses), default=None)
        self._record(
            event.result.ligand_molecule_uuid,
            self._name_of(event.result.ligand_molecule_uuid),
            best_affinity_kcal_mol=best,
            pose_count=len(poses),
            error=None if poses else "Docking produced no poses.",
        )

    def _on_docking_state(self, event: DockingJobStateChanged) -> None:
        """Advance the queue on a terminal docking state.

        COMPLETED is where the queue moves, not `DockingResultReady`:
        the result event fires first and carries the poses, but only the
        state event is guaranteed for BOTH outcomes. Advancing on the
        result alone would leave a screen wedged forever on the first
        ligand Vina refused.
        """
        if not self._is_ours(event.ligand_molecule_uuid):
            return
        if event.state is CacheState.FAILED:
            if not self._already_recorded(event.ligand_molecule_uuid):
                self._record(
                    event.ligand_molecule_uuid,
                    self._name_of(event.ligand_molecule_uuid),
                    error=event.message or "Docking failed.",
                )
            self._current_uuid = None
            self._submit_next()
        elif event.state is CacheState.COMPLETED:
            self._current_uuid = None
            self._submit_next()

    def _is_ours(self, ligand_uuid: str) -> bool:
        """Only react to the docking job THIS screen submitted.

        `DockingService` is shared, and a user is free to run a one-off
        docking from the Docking panel while a screen is going. Without
        this check that unrelated result would be recorded into the screen
        and would advance its queue, skipping a ligand.
        """
        return self.is_running() and ligand_uuid == self._current_uuid

    def _already_recorded(self, molecule_uuid: str) -> bool:
        return any(entry.molecule_uuid == molecule_uuid for entry in self._entries)

    def _name_of(self, molecule_uuid: str) -> str:
        """Captured at request time, not looked up later.

        The docking events carry only uuids, and the service holds no
        project -- so the names have to be taken when the ligands are
        handed in or they are not recoverable at all, and a results table
        of uuids is not a results table.
        """
        return self._names.get(molecule_uuid, molecule_uuid)

    def _record(self, molecule_uuid: str, display_name: str, **fields) -> None:
        self._entries.append(
            ScreeningEntry(molecule_uuid=molecule_uuid, display_name=display_name, **fields)
        )

    def _finish(self) -> None:
        self._job_manager.finish(SCREENING_JOB_KIND, SCREENING_JOB_KEY)
        state = CacheState.FAILED if self._cancelled else CacheState.COMPLETED
        message = (
            f"Cancelled after {len(self._entries)} of {self._total} ligands."
            if self._cancelled
            else f"{len(self._entries)} ligands screened."
        )
        self._current_uuid = None
        self._publish(state, message)

    def _publish(self, state: CacheState, message: str) -> None:
        self._job_manager.update_message(SCREENING_JOB_KIND, SCREENING_JOB_KEY, message)
        self._event_bus.publish(
            ScreeningProgress(
                state=state,
                completed=len(self._entries),
                total=self._total,
                receptor_macromolecule_uuid=self._receptor.uuid if self._receptor else "",
                message=message,
                entries=rank(self._entries),
            )
        )

    def _reject(self, message: str) -> None:
        self._event_bus.publish(
            ScreeningProgress(
                state=CacheState.FAILED, completed=0, total=0, message=message, error=message
            )
        )


def rank(entries: list[ScreeningEntry]) -> list[ScreeningEntry]:
    """Best binder first; failures last, in the order they were attempted.

    "Best" is the most NEGATIVE affinity. Sorting these ascending is the
    correct ranking and reads as backwards, which is why it is one function
    with one comment rather than a `sorted()` at each call site.
    """
    scored = [entry for entry in entries if entry.best_affinity_kcal_mol is not None]
    unscored = [entry for entry in entries if entry.best_affinity_kcal_mol is None]
    return sorted(scored, key=lambda entry: entry.best_affinity_kcal_mol) + unscored
