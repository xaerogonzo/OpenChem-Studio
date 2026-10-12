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
from openchem.domain.turn_snapshot import DEFAULT_READ_LIMIT, ResultsView, TurnContext, read_results


class CalculationHost(Protocol):
    """What the window provides. Structural, so a test double needs no base class."""

    def begin_turn(self) -> TurnContext | None: ...

    def catalog(self, query: str = "", limit: int = 20) -> tuple[CalculatorCard, ...]: ...

    def describe(self, calculator_id: str) -> CalculatorCard | None: ...

    def goals(self) -> tuple[GoalCard, ...]: ...

    def prepare(self, turn: TurnContext, calculator_id: str, parameters: dict[str, Any] | None = None) -> PrepareResult: ...

    def run(self, turn: TurnContext, run_id: str, *, timeout: float | None = None) -> RunOutcome: ...


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

    def pending(self) -> tuple[Preparation, ...]: ...

    def approve(self, run_id: str) -> RunState | None: ...

    def cancel(self, run_id: str) -> bool: ...

    def state_of(self, run_id: str) -> RunState | None: ...

    def outcome_of(self, run_id: str) -> RunOutcome | None: ...


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
