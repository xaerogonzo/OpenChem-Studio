"""Plans a synthesis for one molecule off the GUI thread (`docs/SYNTHESIS_HELPER_DESIGN.md`, Stage 1 slice 4): the one place the gate, the planner process and the stored result meet.

THE GATE IS ENFORCED HERE, ONCE, BEFORE ANYTHING STARTS. `request_plan` is the only way a planner process is ever started, and it
asks `chem.synthesis_gate.check_target` first: a target that matches CWC Schedule 1 is `refused`, one the gate cannot tell about is
`unscreened`, and in both no job is registered and no process is launched. The GUI, the assistant tool and any later caller go
through this one method; none of them has a path that skips it, and `tests/test_synthesis_planning_service.py` asserts "no child
process was started" with the real service for a request from each.

THE TARGET IS CAPTURED BEFORE THE WORKER STARTS. A `TargetIdentity` (molecule uuid, canonical SMILES, a fingerprint) and the
`PlannerSetup` are frozen on the calling thread and ride with the search, so an edit of the drawing, or a change of the planner
setting, while it runs cannot change what was asked. The finished `RouteSet` is stored per molecule and read back through
`result_for(molecule)`, which compares the structure it was planned for with the one now drawn (`chem.isotopes.same_structure`, which
answers "not the same" when it cannot tell): a plan for an earlier structure is returned labelled as such and is never presented as the
plan for the structure now on screen, and a plan is never returned for a different molecule.

ONE SLOT PER MOLECULE, ONE SEARCH AT A TIME. A second request for a molecule that is being planned is `ALREADY_RUNNING`. The searches
run on a private pool of one thread: the planner's process needs about 2.75 GB with the benchmark's stock and up to 5.3 GB with a ZINC
stock, so two at once is a decision nobody has made, and a request that waits is shown as queued in the Jobs panel and can be cancelled
before it starts.

CANCEL AND SHUTDOWN KILL THE CHILD. `cancel` sets the event `run_planner` watches; `shutdown` (wired to the application quitting)
cancels every search and waits for the pool, so no planner process is left running.

RESULTS ARE SESSION-ONLY in version 1: nothing is written to a project file. A `synthesis_runs` block like `recipe_runs` is the follow-up.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import QRunnable, QThreadPool

from openchem.chem.aizynth_planner import PLANNER_NAME, PlannerSetup, run_planner
from openchem.chem.isotopes import same_structure
from openchem.chem.synthesis_gate import check_target
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.domain.synthesis_gate import GateDecision, GateOutcome
from openchem.domain.synthesis_route import (
    PlannerIdentity,
    RouteSet,
    RouteStatus,
    SearchLimits,
    SearchTermination,
    TargetIdentity,
)
from openchem.events.base import EventBus
from openchem.events.events import SynthesisJobStateChanged, SynthesisRouteReady
from openchem.services.job_manager import JobManager

logger = logging.getLogger("openchem.chemistry")

#: The Jobs panel's kind for a planning request.
JOB_KIND = "synthesis"
#: What the identity of a result says in place of a planner version when no planner ran (the gate refused, the setup is missing, the request was rejected).
NOT_STARTED = "not started"

SetupProvider = Callable[[], PlannerSetup | None]
Gate = Callable[[str], GateDecision]
Runner = Callable[..., RouteSet]


class RequestOutcome(StrEnum):
    """What `request_plan` did, so a caller can tell the user without waiting for an event."""

    #: A search was queued. Its result arrives as `SynthesisRouteReady`.
    STARTED = "started"
    #: Decided without starting a process (refused, unscreened, unavailable, failed to start). The result is already stored and published.
    FINISHED = "finished"
    #: This molecule is already being planned; nothing was started and nothing was published.
    ALREADY_RUNNING = "already_running"
    #: There was nothing to plan (the molecule has no structure). Only a failure state is published: there is no target to identify.
    REJECTED = "rejected"


@dataclass(frozen=True)
class BoundResult:
    """A stored plan read back for a molecule: the plan, and whether it is for the structure now drawn."""

    route_set: RouteSet
    #: True only when the structure planned for is still the structure drawn. When False the plan is the plan for an EARLIER structure and `note` says so.
    is_current: bool
    note: str = ""


def _not_started(setup: PlannerSetup | None) -> PlannerIdentity:
    selection = setup.selection() if setup is not None else ()
    limits = setup.limits if setup is not None else SearchLimits()
    return PlannerIdentity(planner=PLANNER_NAME, version=NOT_STARTED, model_identity=selection, limits=limits)


def _state_for(route_set: RouteSet) -> CacheState:
    return CacheState.COMPLETED if route_set.status in (RouteStatus.FOUND, RouteStatus.NO_ROUTE) else CacheState.FAILED


class SynthesisPlanningService:
    def __init__(
        self,
        event_bus: EventBus,
        *,
        setup_provider: SetupProvider,
        job_manager: JobManager | None = None,
        gate: Gate = check_target,
        runner: Runner = run_planner,
        structure_version_of: Callable[[str], int] | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._setup_provider = setup_provider
        self._job_manager = job_manager if job_manager is not None else JobManager()
        self._gate = gate
        self._runner = runner
        self._structure_version_of = structure_version_of
        # A pool of its own, one thread: see the module docstring. `shutdown` waits on THIS pool, never on the shared one.
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(1)
        self._cancels: dict[str, threading.Event] = {}
        self._results: dict[str, RouteSet] = {}
        self._lock = threading.Lock()

    # --- asking ----------------------------------------------------------------------------------------------------------------

    def request_plan(self, molecule: MoleculeModel, *, requested_by: str = "the user") -> RequestOutcome:
        """Plan a synthesis for `molecule`. Call from the GUI thread; every path, including the assistant's, goes through here."""
        uuid = molecule.uuid
        if self._job_manager.is_active(JOB_KIND, uuid):
            return RequestOutcome.ALREADY_RUNNING
        smiles = (molecule.canonical_smiles or "").strip()
        if not smiles:
            self._event_bus.publish(SynthesisJobStateChanged(molecule_uuid=uuid, state=CacheState.FAILED, message="This molecule has no structure to plan a synthesis for."))
            return RequestOutcome.REJECTED
        target = TargetIdentity(molecule_uuid=uuid, canonical_smiles=smiles, fingerprint=self._fingerprint(uuid, smiles))
        setup, setup_error = self._capture_setup()

        decision = self._decide(smiles)
        if not decision.permits_planning:
            status = RouteStatus.REFUSED if decision.outcome is GateOutcome.REFUSED else RouteStatus.UNSCREENED
            return self._finish_now(RouteSet(status=status, target=target, planner=_not_started(setup), reason=decision.refusal_text()))
        if "." in smiles:
            return self._finish_now(
                RouteSet(status=RouteStatus.FAILED, target=target, planner=_not_started(setup), termination=SearchTermination.FAILED, reason="This structure has several components. Plan one component at a time.")
            )
        if setup is None:
            reason = "The synthesis planner is not set up." if setup_error is None else f"The synthesis planner's setup could not be read ({type(setup_error).__name__})."
            return self._finish_now(RouteSet(status=RouteStatus.UNAVAILABLE, target=target, planner=_not_started(None), reason=reason))

        cancel = threading.Event()
        if not self._job_manager.try_start(JOB_KIND, uuid, cancel_callback=cancel.set):
            return RequestOutcome.ALREADY_RUNNING
        with self._lock:
            self._cancels[uuid] = cancel
        self._event_bus.publish(SynthesisJobStateChanged(molecule_uuid=uuid, state=CacheState.QUEUED, message=f"Waiting to plan {molecule.display_name} (requested by {requested_by})"))
        self._pool.start(_PlanTask(self, target, setup, cancel, molecule.display_name))
        return RequestOutcome.STARTED

    def cancel(self, molecule_uuid: str) -> bool:
        """Stop this molecule's search (or take it out of the queue). False when none is running."""
        return self._job_manager.cancel(JOB_KIND, molecule_uuid)

    def is_planning(self, molecule_uuid: str) -> bool:
        return self._job_manager.is_active(JOB_KIND, molecule_uuid)

    def shutdown(self, wait_ms: int = 20000) -> None:
        """Cancel every search and wait for the pool, so no planner process outlives the application."""
        with self._lock:
            events = list(self._cancels.values())
        for event in events:
            event.set()
        self._pool.waitForDone(wait_ms)

    # --- reading ---------------------------------------------------------------------------------------------------------------

    def result_for(self, molecule: MoleculeModel) -> BoundResult | None:
        """The stored plan for `molecule`, bound to the structure it was made for, or None.

        Never a plan made for another molecule. A plan made for an earlier structure of this one is returned with `is_current` False and a
        note, so a surface must show it as the earlier plan or withhold it; it cannot present it as current by accident.
        """
        with self._lock:
            route_set = self._results.get(molecule.uuid)
        if route_set is None or route_set.target.molecule_uuid != molecule.uuid:
            return None
        if same_structure(route_set.target.canonical_smiles, molecule.canonical_smiles):
            return BoundResult(route_set=route_set, is_current=True)
        return BoundResult(
            route_set=route_set,
            is_current=False,
            note=f"This plan was made for an earlier version of this structure ({route_set.target.canonical_smiles}). It is not the plan for the structure now drawn.",
        )

    def forget(self, molecule_uuid: str) -> None:
        """Drop a stored plan (a molecule removed from the project). Does not stop a running search."""
        with self._lock:
            self._results.pop(molecule_uuid, None)

    # --- internals -------------------------------------------------------------------------------------------------------------

    def _fingerprint(self, uuid: str, smiles: str) -> str:
        version = self._structure_version_of(uuid) if self._structure_version_of is not None else 0
        return f"{smiles}|v{version}"

    def _capture_setup(self) -> tuple[PlannerSetup | None, Exception | None]:
        """The setup as it is NOW, frozen for this request, or why there is none."""
        try:
            return self._setup_provider(), None
        except Exception as exc:  # noqa: BLE001 - an unreadable setting is "unavailable", never a crash
            logger.warning("The synthesis planner's setup could not be read: %s", exc)
            return None, exc

    def _decide(self, smiles: str) -> GateDecision:
        """The gate's decision, with any failure of the gate itself read as `unscreened`: there is no path from an exception to a plan."""
        try:
            return self._gate(smiles)
        except Exception as exc:  # noqa: BLE001 - fail closed
            logger.warning("The synthesis gate raised: %s", exc)
            return GateDecision(outcome=GateOutcome.UNSCREENED, reason=f"the target could not be screened against CWC Schedule 1: the gate failed ({type(exc).__name__}).")

    def _finish_now(self, route_set: RouteSet) -> RequestOutcome:
        """Store and announce a result that needed no process."""
        self._store_and_announce(route_set)
        return RequestOutcome.FINISHED

    def _store_and_announce(self, route_set: RouteSet) -> None:
        uuid = route_set.target.molecule_uuid
        with self._lock:
            self._results[uuid] = route_set
            self._cancels.pop(uuid, None)
        self._job_manager.finish(JOB_KIND, uuid)
        self._event_bus.publish(SynthesisRouteReady(molecule_uuid=uuid, route_set=route_set))
        self._event_bus.publish(SynthesisJobStateChanged(molecule_uuid=uuid, state=_state_for(route_set), message=route_set.message()))


class _PlanTask(QRunnable):
    """One search, on the service's own thread. Reads nothing but what was captured when the request was made."""

    def __init__(self, service: SynthesisPlanningService, target: TargetIdentity, setup: PlannerSetup, cancel: threading.Event, name: str) -> None:
        super().__init__()
        self._service = service
        self._target = target
        self._setup = setup
        self._cancel = cancel
        self._name = name

    def run(self) -> None:
        service, target = self._service, self._target
        if self._cancel.is_set():
            # Cancelled while it was still waiting its turn: no process is started for it.
            service._store_and_announce(RouteSet(status=RouteStatus.CANCELLED, target=target, planner=_not_started(self._setup), termination=SearchTermination.CANCELLED, reason="The request was cancelled before it started."))
            return
        message = f"Planning {self._name} with {PLANNER_NAME}"
        service._job_manager.update_message(JOB_KIND, target.molecule_uuid, message)
        service._event_bus.publish(SynthesisJobStateChanged(molecule_uuid=target.molecule_uuid, state=CacheState.RUNNING, message=message))
        try:
            route_set = service._runner(self._setup.request_for(target.canonical_smiles), target, python=self._setup.python, cancel=self._cancel)
        except Exception as exc:  # noqa: BLE001 - report failure, never crash the pool
            logger.exception("Synthesis planning failed for %s", target.molecule_uuid)
            route_set = RouteSet(status=RouteStatus.FAILED, target=target, planner=_not_started(self._setup), termination=SearchTermination.FAILED, reason=f"The planner run failed unexpectedly ({type(exc).__name__}).")
        service._store_and_announce(route_set)
