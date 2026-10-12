"""One requested calculation, from "prepared" to "recorded" -- as a state machine nothing can skip.

The pure core of the assistant's execution boundary (`docs/AI_CALCULATION_BRIDGE.md`, sections 3 and
5). It decides nothing about chemistry and starts nothing; it is the record of what was asked, what
state that request is in, and which transitions are legal. The host that actually dispatches work
asks it before every step.

**THE RULES THIS ENFORCES ARE THE ONES A PROMPT CANNOT.**

* A `run_id` exists only because `prepare` made one. A request for any other is `NO_SUCH_RUN`.
* A run is DISPATCHED ONCE: `claim_dispatch` is atomic and answers True to exactly one caller, so
  two tool calls naming one run -- a model repeating itself, a result arriving while a retry is
  made -- start one calculation.
* A preview that needs a person (`PREVIEWED`) cannot be started by `claim_dispatch` at all. The
  only way out of it is `approve`, which is a method the tool side never receives; that is a property
  of which object a caller holds, not of a check somebody must remember.
* A terminal state is final. A cancelled or invalidated run cannot be approved, and a completed one
  cannot be re-run: asking again returns the recorded outcome.
* A run is bound to the molecule and the input fingerprint it was prepared for. The host
  `invalidate`s it when either changes; an invalidated preview cannot be approved.

Thread-safe: `prepare` runs on the provider's worker thread, `approve` and `cancel` on the GUI thread.

Pure: no Qt, no RDKit.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from openchem.domain.calculation_bridge import Problem, Route
from openchem.domain.execution_policy import RunDecision
from openchem.domain.result_store import StoredResult


class RunState(str, Enum):
    #: Validated, inside the policy's bounds, ready to dispatch.
    PREPARED = "prepared"
    #: Validated and needing a person: waiting on Approve or Cancel.
    PREVIEWED = "previewed"
    #: A person approved it; not yet dispatched.
    APPROVED = "approved"
    RUNNING = "running"
    #: Finished and produced a result. The only state that carries a number.
    COMPLETED = "completed"
    #: The calculator declined (a limit, a missing input, a missing setup), with its kind.
    REFUSED = "refused"
    FAILED = "failed"
    CANCELLED = "cancelled"
    #: The structure or the project changed after the plan was made, so the plan is void.
    INVALIDATED = "invalidated"
    #: Never a ledger state: what a caller is told when it stopped waiting for a run that is still
    #: going. The run's own state stays `RUNNING` and its result arrives by the normal path.
    TIMED_OUT = "timed_out"
    #: Never a ledger state either: the request named no run it may use (one nobody prepared, or
    #: one prepared in another turn). Nothing was started and nothing was changed.
    REJECTED = "rejected"


#: The states a run never leaves. A run in one of them is not dispatched, approved or cancelled again.
TERMINAL = frozenset({
    RunState.COMPLETED, RunState.REFUSED, RunState.FAILED, RunState.CANCELLED, RunState.INVALIDATED,
})

#: Legal moves. Anything else is refused, and a test pins each absence.
_ALLOWED: dict[RunState, frozenset[RunState]] = {
    RunState.PREPARED: frozenset({RunState.RUNNING, RunState.CANCELLED, RunState.INVALIDATED}),
    RunState.PREVIEWED: frozenset({RunState.APPROVED, RunState.CANCELLED, RunState.INVALIDATED}),
    RunState.APPROVED: frozenset({RunState.RUNNING, RunState.CANCELLED, RunState.INVALIDATED}),
    RunState.RUNNING: frozenset({RunState.COMPLETED, RunState.REFUSED, RunState.FAILED}),
}

#: A preview nobody answered is void after this long, so an old approval cannot start work the person
#: no longer remembers asking for.
PREVIEW_TTL_SECONDS = 1800.0

#: Finished runs kept for "what happened to that request" before the oldest are forgotten.
MAX_FINISHED_RUNS = 200


@dataclass(frozen=True)
class Preparation:
    """A validated request, bound to the molecule and structure it was prepared against."""

    run_id: str
    turn_id: str
    calculator_id: str
    display_name: str
    molecule_uuid: str
    molecule_name: str
    #: The project it was prepared in: a plan for one project is void in another.
    project_uuid: str
    #: `drawing` or `geometry`, and the fingerprint of that input when the plan was made.
    calculation_input: str
    input_fingerprint: str
    #: The dialog's dict: every declared parameter, defaults filled in.
    parameters: Mapping[str, Any]
    route: Route
    decision: RunDecision
    #: What approving would start, in sentences, for a preview.
    preview: tuple[str, ...] = ()
    adjustments: tuple[str, ...] = ()
    resource: str = ""
    external_tools: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "calculator_id": self.calculator_id,
            "name": self.display_name,
            "molecule": self.molecule_name,
            "route": self.route.value,
            "needs_approval": self.decision.ai_run.value == "confirm",
            "why_approval": self.decision.reason,
            "parameters": dict(self.parameters),
            "adjustments": list(self.adjustments),
            "preview": list(self.preview),
            "resource": self.resource,
            "external_tools": list(self.external_tools),
        }


@dataclass(frozen=True)
class PrepareResult:
    """A `Preparation`, or the problems that stopped one being made. Never both."""

    preparation: Preparation | None = None
    problems: tuple[Problem, ...] = ()

    @property
    def ok(self) -> bool:
        return self.preparation is not None

    def to_dict(self) -> dict[str, Any]:
        if self.preparation is not None:
            return {"ok": True, **self.preparation.to_dict()}
        return {"ok": False, "problems": [p.to_dict() for p in self.problems]}


@dataclass(frozen=True)
class RunOutcome:
    """What became of a requested run, in the words a model is told."""

    run_id: str
    calculator_id: str
    state: RunState
    message: str = ""
    #: `domain.result_status` value of the result, "" when there is none.
    status: str = ""
    stored: StoredResult | None = None
    problems: tuple[Problem, ...] = ()

    @property
    def has_number(self) -> bool:
        """Only a completed run carries computed numerical evidence."""
        return self.state is RunState.COMPLETED and self.stored is not None


class RunLedger:
    """Every prepared run and where it stands. See the module docstring."""

    def __init__(self, *, clock=time.time) -> None:
        self._lock = threading.RLock()
        self._clock = clock
        self._preparations: dict[str, Preparation] = {}
        self._states: dict[str, RunState] = {}
        self._outcomes: dict[str, RunOutcome] = {}
        self._finished: OrderedDict[str, None] = OrderedDict()

    # --- registering and reading ----------------------------------------------------------

    def register(self, preparation: Preparation) -> RunState:
        """Record a new run in the state its route implies; returns that state."""
        state = RunState.PREPARED if preparation.route is Route.AUTO else RunState.PREVIEWED
        with self._lock:
            self.sweep()
            if preparation.run_id in self._preparations:
                raise ValueError(f"run {preparation.run_id} is already registered")
            self._preparations[preparation.run_id] = preparation
            self._states[preparation.run_id] = state
        return state

    def get(self, run_id: str) -> Preparation | None:
        with self._lock:
            return self._preparations.get(run_id)

    def state_of(self, run_id: str) -> RunState | None:
        with self._lock:
            return self._states.get(run_id)

    def outcome_of(self, run_id: str) -> RunOutcome | None:
        with self._lock:
            return self._outcomes.get(run_id)

    def pending(self) -> tuple[Preparation, ...]:
        """Previews waiting on a person, oldest first."""
        with self._lock:
            return tuple(
                p for run_id, p in self._preparations.items() if self._states[run_id] is RunState.PREVIEWED
            )

    def sweep(self) -> int:
        """Void every run that was prepared and never started within `PREVIEW_TTL_SECONDS`.

        A prepared run nobody dispatched, or a preview nobody answered, is not left to be started
        by a stale approval hours later. Returns how many were withdrawn.
        """
        now = self._clock()
        with self._lock:
            old = [
                run_id for run_id, prep in self._preparations.items()
                if self._states[run_id] in (RunState.PREPARED, RunState.PREVIEWED, RunState.APPROVED)
                and now - prep.created_at > PREVIEW_TTL_SECONDS
            ]
            return sum(
                1 for run_id in old
                if self.invalidate(run_id, "it was prepared and never started, so it was withdrawn")
            )

    # --- transitions ----------------------------------------------------------------------

    def _move(self, run_id: str, new: RunState) -> bool:
        current = self._states.get(run_id)
        if current is None or new not in _ALLOWED.get(current, frozenset()):
            return False
        self._states[run_id] = new
        if new in TERMINAL:
            self._finished[run_id] = None
            self._forget_oldest()
        return True

    def _forget_oldest(self) -> None:
        while len(self._finished) > MAX_FINISHED_RUNS:
            old, _ = self._finished.popitem(last=False)
            self._preparations.pop(old, None)
            self._states.pop(old, None)
            self._outcomes.pop(old, None)

    def claim_dispatch(self, run_id: str) -> bool:
        """Atomically start a run. True for exactly one caller, and only from PREPARED or APPROVED.

        A PREVIEWED run is not claimable: a person has not looked at it.
        """
        with self._lock:
            return self._move(run_id, RunState.RUNNING)

    def approve(self, run_id: str) -> bool:
        """PREVIEWED -> APPROVED, unless the preview has expired (which voids it instead)."""
        with self._lock:
            prep = self._preparations.get(run_id)
            if prep is None or self._states.get(run_id) is not RunState.PREVIEWED:
                return False
            if self._clock() - prep.created_at > PREVIEW_TTL_SECONDS:
                self._move(run_id, RunState.INVALIDATED)
                self._outcomes[run_id] = RunOutcome(
                    run_id, prep.calculator_id, RunState.INVALIDATED,
                    "the preview was not answered in time, so it was withdrawn",
                )
                return False
            return self._move(run_id, RunState.APPROVED)

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            prep = self._preparations.get(run_id)
            if prep is None or not self._move(run_id, RunState.CANCELLED):
                return False
            self._outcomes[run_id] = RunOutcome(run_id, prep.calculator_id, RunState.CANCELLED, "cancelled before it started")
            return True

    def invalidate(self, run_id: str, reason: str) -> bool:
        """Void a run that has not started because what it was prepared against has changed."""
        with self._lock:
            prep = self._preparations.get(run_id)
            if prep is None or not self._move(run_id, RunState.INVALIDATED):
                return False
            self._outcomes[run_id] = RunOutcome(run_id, prep.calculator_id, RunState.INVALIDATED, reason)
            return True

    def invalidate_for(self, molecule_uuid: str, reason: str) -> int:
        """Void every run not yet started for a molecule. Returns how many."""
        with self._lock:
            targets = [
                run_id for run_id, prep in self._preparations.items()
                if prep.molecule_uuid == molecule_uuid
                and self._states[run_id] in (RunState.PREPARED, RunState.PREVIEWED, RunState.APPROVED)
            ]
            return sum(1 for run_id in targets if self.invalidate(run_id, reason))

    def finish(self, outcome: RunOutcome) -> bool:
        """RUNNING -> its final state, recording the outcome. False if the run was not running."""
        if outcome.state not in (RunState.COMPLETED, RunState.REFUSED, RunState.FAILED):
            raise ValueError(f"a running run finishes as completed, refused or failed, not {outcome.state.value}")
        with self._lock:
            if not self._move(outcome.run_id, outcome.state):
                return False
            self._outcomes[outcome.run_id] = outcome
            return True
