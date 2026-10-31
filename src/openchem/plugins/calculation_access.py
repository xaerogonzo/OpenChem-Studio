"""`context.calculations`: what a plugin may do with the application's calculators, and nothing else.

A plugin never receives the service container, the registry, the result store, the event bus or the
window -- `PluginContext` hides all of them on purpose (a plugin subscribing to the bus directly
would leak on unload). The assistant needs to find a calculator, read what has been computed, and
ask for a run; this is exactly that, as seven calls that take and return plain values.

**THE HANDLE HAS NO WAY TO APPROVE ANYTHING.** A request that needs a person is prepared here and
decided on the panel's own Approve button, through `PluginCalculationApprovals` below -- a different
object, which a plugin's PANEL is given and its TOOLS are not. That a model cannot approve its own
request is therefore a fact about which object a tool is handed, not a check somebody must remember
to write.

**A MODEL CAN PROPOSE A SCORE AND CANNOT SAVE ONE** (slice 4d): `propose_score` checks a request against the rules a typed definition meets and leaves a proposal for a person; it stores
nothing. Approving it is `PluginCalculationApprovals.approve_score`, the same split as a run's.

**A CONTEXT BUILT WITHOUT A HOST IS NOT AN ERROR.** A headless run or a test has none, and every call
then answers with a typed `UNAVAILABLE` rather than raising -- the same behaviour a plugin gets for
any capability the host did not provide. See `docs/AI_CALCULATION_BRIDGE.md` for the contract and the
thread each call belongs to.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from openchem.domain.calculation_bridge import CalculatorCard, GoalCard, Problem, ProblemCode
from openchem.domain.run_lifecycle import Preparation, PrepareResult, RunOutcome, RunState
from openchem.domain.score_outputs import APPROVED, ApprovedOutput
from openchem.domain.score_proposal import ProposalOutcome, ProposalProblem, ProposalRefusal, ProposalState, Registered, ScoreProposal
from openchem.domain.score_reading import ScoresView, read_scores
from openchem.domain.quantum_run_snapshot import DEFAULT_RUN_LIMIT, RunsView, read_runs
from openchem.domain.turn_snapshot import DEFAULT_READ_LIMIT, ResultsView, TurnContext, read_results


class CalculationHost(Protocol):
    """What the window provides. Structural, so a test double needs no base class."""

    def begin_turn(self) -> TurnContext | None: ...

    def catalog(self, query: str = "", limit: int = 20) -> tuple[CalculatorCard, ...]: ...

    def describe(self, calculator_id: str) -> CalculatorCard | None: ...

    def goals(self) -> tuple[GoalCard, ...]: ...

    def prepare(self, turn: TurnContext, calculator_id: str, parameters: dict[str, Any] | None = None) -> PrepareResult: ...

    def run(self, turn: TurnContext, run_id: str, *, timeout: float | None = None) -> RunOutcome: ...

    def propose_score(self, turn: TurnContext, request: Any) -> Registered | ProposalRefusal: ...


_UNAVAILABLE = "the application did not provide calculator access to this plugin (a headless run or a test)"


class PluginCalculations:
    """The tool-facing face of the calculator bridge. See the module docstring."""

    def __init__(self, host: CalculationHost | None) -> None:
        self._host = host

    @property
    def available(self) -> bool:
        return self._host is not None

    def begin_turn(self) -> TurnContext | None:
        """Freeze the selected molecule and what is stored about it. **GUI thread only**, at Send.

        `None` when nothing is selected, or when no host is present.
        """
        return self._host.begin_turn() if self._host is not None else None

    def catalog(self, query: str = "", limit: int = 20) -> tuple[CalculatorCard, ...]:
        """Calculators matching every word of `query`, in browse order. Any thread."""
        return self._host.catalog(query, limit) if self._host is not None else ()

    def describe(self, calculator_id: str) -> CalculatorCard | None:
        """One calculator's card, or None for an id nothing registers. Any thread."""
        return self._host.describe(calculator_id) if self._host is not None else None

    def goals(self) -> tuple[GoalCard, ...]:
        """The questions the wizard offers and the calculators that answer each, with what this route can do
        with every one. Read-only knowledge, not a way to run a goal. Any thread."""
        return self._host.goals() if self._host is not None else ()

    def read_results(
        self,
        turn: TurnContext,
        calculator_ids: list[str] | None = None,
        *,
        include_not_current: bool = False,
        limit: int = DEFAULT_READ_LIMIT,
    ) -> ResultsView:
        """What was stored when `turn` began, never what is stored now. Needs no host."""
        return read_results(turn, calculator_ids, include_not_current=include_not_current, limit=limit)

    def read_quantum_runs(
        self,
        turn: TurnContext,
        run_ids: list[str] | None = None,
        *,
        include_not_current: bool = False,
        limit: int = DEFAULT_RUN_LIMIT,
    ) -> RunsView:
        """The ORCA runs stored for the turn's molecule when `turn` began: a list of headers, or the runs named by id with their numbers. Needs no host, and starts nothing."""
        return read_runs(turn, run_ids, include_not_current=include_not_current, limit=limit)

    def read_scores(self, turn: TurnContext, names: list[str] | None = None) -> ScoresView:
        """The user-defined scores of the turn's molecule, worked out from what was stored and defined when `turn` began. Needs no host, and can only READ: there is no
        call here that makes, changes or removes a score."""
        return read_scores(turn, names)

    def list_score_outputs(self) -> tuple[ApprovedOutput, ...]:
        """The outputs a score's formula may read: ids, units and what each is. Fixed knowledge, so it needs no host."""
        return APPROVED

    def propose_score(self, turn: TurnContext, request: Any) -> Registered | ProposalRefusal:
        """Check a request for a score against every rule a typed definition meets and leave it for a person to approve. **Stores nothing**, and is the only score call here that can
        lead to a score existing at all: the saving is `PluginCalculationApprovals.approve_score`. Any thread."""
        if self._host is None:
            return ProposalRefusal(ProposalProblem.NO_PROJECT, _UNAVAILABLE)
        return self._host.propose_score(turn, request)

    def prepare(self, turn: TurnContext, calculator_id: str, parameters: dict[str, Any] | None = None) -> PrepareResult:
        """Validate a request and decide who may start it. Starts nothing. Any thread."""
        if self._host is None:
            return PrepareResult(problems=(Problem(ProblemCode.UNAVAILABLE, _UNAVAILABLE),))
        return self._host.prepare(turn, calculator_id, parameters)

    def run(self, turn: TurnContext, run_id: str, *, timeout: float | None = None) -> RunOutcome:
        """Start a prepared automatic run and wait for it. **A worker thread only.**"""
        if self._host is None:
            return RunOutcome(run_id, "", RunState.REJECTED, _UNAVAILABLE, problems=(Problem(ProblemCode.UNAVAILABLE, _UNAVAILABLE),))
        return self._host.run(turn, run_id, timeout=timeout)


class ApprovalHost(Protocol):
    """The window's side of approval. Structural, like `CalculationHost`."""

    #: A Qt signal carrying a `RunOutcome` whenever a run reaches a final state.
    finished: Any

    #: A Qt signal carrying a `ProposalOutcome` whenever a proposed score is decided.
    score_finished: Any

    def pending(self) -> tuple[Preparation, ...]: ...

    def approve(self, run_id: str) -> RunState | None: ...

    def cancel(self, run_id: str) -> bool: ...

    def state_of(self, run_id: str) -> RunState | None: ...

    def outcome_of(self, run_id: str) -> RunOutcome | None: ...

    def pending_scores(self) -> tuple[ScoreProposal, ...]: ...

    def approve_score(self, proposal_id: str) -> ProposalOutcome | None: ...

    def cancel_score(self, proposal_id: str) -> bool: ...

    def score_state_of(self, proposal_id: str) -> ProposalState | None: ...

    def score_outcome_of(self, proposal_id: str) -> ProposalOutcome | None: ...


class PluginCalculationApprovals:
    """`context.calculation_approvals`: a person's decision on a preview. **For a panel, never a tool.**

    Every call here is a GUI-thread call, made from a button's slot. It is a separate object from
    `PluginCalculations` for the reason in that module's docstring, and a plugin must hand its tools
    only the latter. With no host, nothing is pending and no decision does anything.
    """

    def __init__(self, host: ApprovalHost | None, rollbacks: list[Callable[[], None]] | None = None) -> None:
        self._host = host
        self._rollbacks = rollbacks if rollbacks is not None else []

    @property
    def available(self) -> bool:
        return self._host is not None

    def pending(self) -> tuple[Preparation, ...]:
        """Previews waiting on a person, oldest first."""
        return self._host.pending() if self._host is not None else ()

    def approve(self, run_id: str) -> RunState | None:
        """Start a pending preview if it still describes the live structure; returns the run's state."""
        return self._host.approve(run_id) if self._host is not None else None

    def cancel(self, run_id: str) -> bool:
        """Drop a pending preview. Nothing is started."""
        return self._host.cancel(run_id) if self._host is not None else False

    def state_of(self, run_id: str) -> RunState | None:
        return self._host.state_of(run_id) if self._host is not None else None

    def outcome_of(self, run_id: str) -> RunOutcome | None:
        return self._host.outcome_of(run_id) if self._host is not None else None

    def pending_scores(self) -> tuple[ScoreProposal, ...]:
        """Scores the assistant proposed that wait for a person, oldest first."""
        return self._host.pending_scores() if self._host is not None else ()

    def approve_score(self, proposal_id: str) -> ProposalOutcome | None:
        """Make the score a person approved, if the project is still the one it was proposed in and the rules still accept it. The ONLY way a proposal becomes a score."""
        return self._host.approve_score(proposal_id) if self._host is not None else None

    def cancel_score(self, proposal_id: str) -> bool:
        """Drop a proposed score. Nothing is saved."""
        return self._host.cancel_score(proposal_id) if self._host is not None else False

    def score_state_of(self, proposal_id: str) -> ProposalState | None:
        return self._host.score_state_of(proposal_id) if self._host is not None else None

    def score_outcome_of(self, proposal_id: str) -> ProposalOutcome | None:
        return self._host.score_outcome_of(proposal_id) if self._host is not None else None

    def on_score_finished(self, callback: Callable[[ProposalOutcome], None]) -> None:
        """Call `callback(outcome)` on the GUI thread whenever a proposed score is decided. Undone when the plugin unloads, like `on_finished`."""
        if self._host is None:
            return
        self._host.score_finished.connect(callback)
        self._rollbacks.append(lambda: _disconnect(self._host.score_finished, callback))

    def on_finished(self, callback: Callable[[RunOutcome], None]) -> None:
        """Call `callback(outcome)` on the GUI thread whenever a run reaches a final state.

        Undone automatically when the plugin unloads, like every other subscription made through the
        context: a callback left connected would run against a panel that no longer exists.
        """
        if self._host is None:
            return
        self._host.finished.connect(callback)
        self._rollbacks.append(lambda: _disconnect(self._host.finished, callback))


def _disconnect(signal: Any, callback: Callable[..., None]) -> None:
    try:
        signal.disconnect(callback)
    except (RuntimeError, TypeError):
        pass  # already gone (the host or the receiver was destroyed first)
