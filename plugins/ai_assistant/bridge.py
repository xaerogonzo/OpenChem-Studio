"""What a tool is handed: one frozen turn and the tool-facing handle, and nothing else.

**A TOOL NEVER RECEIVES THE APPROVALS FACE.** `ToolBridge` is built from `context.calculations` (find,
describe, read, prepare, run) and the `TurnContext` captured when the user pressed Send. It has no
`approve`, no `cancel`, no `pending` and no way to reach the object that has them, so a model that asks
for a run that needs a person gets a preview on the user's screen and a message saying so, and has no
call that could press the button for itself. `tests/test_ai_assistant_bridge.py` pins that.

**IT SPEAKS PLAIN DICTS.** Everything here returns JSON-plain values built by the core's own
serialisers (`openchem.domain.result_envelope`, the cards and the run outcomes), so the plugin adds no
interpretation of a result: the application's words are the ones the model is given.

**SIZE.** A reply the model reads is bounded. `bounded_json` renders at full detail and, while the text is
over budget, at each smaller `Caps` step, ending at the header of every result; it never drops a header,
a unit or a caveat to make room, and says when it shortened anything.

Worker-thread code: the calls below run on the provider's worker, which is why a preview is reported
through `on_event` (a queued Qt signal on the panel) and never by touching a widget.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from openchem.domain.result_envelope import CAP_STEPS, Caps, outcome_envelope, results_view_envelope, scores_view_envelope
from openchem.domain.run_lifecycle import RunState
from openchem.domain.turn_snapshot import TurnContext
from openchem.plugins.calculation_access import PluginCalculations

#: The most characters a tool reply may have. A model reads every one of them on every later request.
REPLY_BUDGET = 12000

#: How many calculators one search returns at most, whatever the model asks for.
MAX_SEARCH = 30

#: The wizard's own caveat about its goal lists, sent with every one so a model does not present a
#: judgement as a protocol.
GOALS_ARE_EDITORIAL = (
    "These lists are editorial: the application's authors chose which calculators answer each question. "
    "They are not a validated protocol, so do not present one as the established way to answer it."
)

#: What a model may do with a goal, which is not "run it".
HOW_TO_USE_A_GOAL = (
    "To act on a goal, run its recommended calculators one at a time with run_calculator, passing 'parameters' "
    "where an entry gives some. Each is checked, gated and recorded on its own: 'you_may_run' runs when asked, "
    "'needs_user_approval' leaves a preview the user must approve, and 'cannot_start_here' is run from its own "
    "panel. Run an optional entry only when the question needs what it adds."
)


@dataclass(frozen=True)
class BridgeEvent:
    """Something the panel's ledger should show about a request, said once and in plain words."""

    #: "refused" (nothing was started), "previewed" (waiting for a person), "service_preview"
    #: (described but not startable here), "finished" (a run reached a final state).
    kind: str
    calculator: str
    molecule: str
    run_id: str = ""
    #: A `RunState.value` for "finished", otherwise empty.
    state: str = ""
    detail: str = ""
    #: `Preparation.to_dict()` for a preview, so the panel can draw the card without asking again.
    preparation: dict[str, Any] = field(default_factory=dict)


def bounded_json(build: Callable[[Caps], dict[str, Any]], budget: int = REPLY_BUDGET) -> str:
    """`build(caps)` as JSON, at the largest cap step that fits `budget`.

    The smallest step is still returned if nothing fits, with `shortened_for_length` set: a reply that
    cannot be made short is the model's to be told so about, not silently cut mid-structure.
    """
    text = ""
    for index, caps in enumerate(CAP_STEPS):
        payload = build(caps)
        if index:
            payload = {**payload, "shortened_for_length": True}
        text = json.dumps(payload, ensure_ascii=False)
        if len(text) <= budget:
            return text
    return text


def _plain(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


class ToolBridge:
    """One turn's worth of access to the calculators. See the module docstring."""

    def __init__(
        self,
        calculations: PluginCalculations,
        turn: TurnContext | None,
        on_event: Callable[[BridgeEvent], None] | None = None,
    ) -> None:
        self._calculations = calculations
        self._turn = turn
        self._on_event = on_event or (lambda event: None)

    @property
    def available(self) -> bool:
        """True when there is a host to ask and a molecule selected to ask about."""
        return self._calculations.available and self._turn is not None

    @property
    def turn(self) -> TurnContext | None:
        return self._turn

    def _emit(self, event: BridgeEvent) -> None:
        try:
            self._on_event(event)
        except Exception:  # noqa: BLE001 - a panel that cannot draw a ledger line must not break a tool
            pass

    def _unavailable(self) -> str:
        if not self._calculations.available:
            why = "this application did not give the assistant access to its calculators"
        else:
            why = "no molecule is selected, so there is nothing to read or calculate"
        return _plain({"ok": False, "problem": "unavailable", "message": why})

    # --- the tools --------------------------------------------------------------------------------

    def find_calculators(self, query: str = "", limit: int = 10) -> str:
        if not self._calculations.available:
            return self._unavailable()
        cards = self._calculations.catalog(query, max(1, min(int(limit), MAX_SEARCH)))
        return _plain({
            "ok": True,
            "query": query,
            "found": len(cards),
            "calculators": [
                {k: card.to_dict()[k] for k in ("calculator_id", "name", "category", "route", "route_reason", "needs", "stage")}
                for card in cards
            ],
            "how_to_read_route": {
                "auto": "you may run it with run_calculator",
                "needs_approval": "run_calculator prepares a preview and the user must approve it; you cannot",
                "preview_only": "it is run from its own panel; you cannot start it",
                "blocked": "it cannot be run here",
            },
        })

    def list_goals(self, goal_id: str = "") -> str:
        """The wizard's questions and the calculators that answer them. Read-only; starts nothing."""
        if not self._calculations.available:
            return self._unavailable()
        goals = self._calculations.goals()
        if not goal_id:
            return _plain({
                "ok": True,
                "goals": [goal.summary_dict() for goal in goals],
                "next": "call list_goals with a goal_id to see each entry's reason, route and settings",
                "note": GOALS_ARE_EDITORIAL,
            })
        goal = next((g for g in goals if g.goal_id == goal_id), None)
        if goal is None:
            return _plain({"ok": False, "problem": "unknown_goal", "known": [g.goal_id for g in goals],
                           "message": f"there is no goal {goal_id!r}; call list_goals with no argument to see them"})
        return _plain({"ok": True, "goal": goal.to_dict(), "how_to_use": HOW_TO_USE_A_GOAL, "note": GOALS_ARE_EDITORIAL})

    def describe_calculator(self, calculator_id: str) -> str:
        if not self._calculations.available:
            return self._unavailable()
        card = self._calculations.describe(calculator_id)
        if card is None:
            return _plain({"ok": False, "problem": "unknown_calculator",
                           "message": f"there is no calculator {calculator_id!r}; use find_calculators"})
        return _plain({"ok": True, "calculator": card.to_dict()})

    def read_results(self, calculators: list[str] | None = None, include_not_current: bool = False) -> str:
        if not self.available:
            return self._unavailable()
        view = self._calculations.read_results(
            self._turn, list(calculators) if calculators else None, include_not_current=bool(include_not_current)
        )
        return bounded_json(lambda caps: results_view_envelope(view, caps))

    def read_scores(self, scores: list[str] | None = None) -> str:
        """The user-defined scores of the selected molecule, worked out from what was stored and defined when the turn began. Read-only: a score cannot be made here."""
        if not self.available:
            return self._unavailable()
        view = self._calculations.read_scores(self._turn, list(scores) if scores else None)
        return bounded_json(lambda caps: scores_view_envelope(view, caps))

    def run_calculator(self, calculator_id: str, parameters: dict[str, Any] | None = None) -> str:
        if not self.available:
            return self._unavailable()
        turn = self._turn
        prepared = self._calculations.prepare(turn, calculator_id, dict(parameters or {}))
        if prepared.service_preview is not None:
            preview = prepared.service_preview
            self._emit(BridgeEvent(
                "service_preview", calculator_id, turn.display_name, detail=f"run it from the {preview.panel_name}",
                preparation=preview.to_dict(),
            ))
            return _plain({
                "ok": False, "started": False, "state": "preview_only", "service_preview": preview.to_dict(),
                "message": (
                    f"You cannot start this: it runs from the {preview.panel_name}. The user has been shown what it would "
                    f"take and whether this machine is ready. Tell them what you found there, and that they can run it "
                    f"from that panel. State no result: nothing was computed."
                ),
            })
        if not prepared.ok:
            self._emit(BridgeEvent(
                "refused", calculator_id, turn.display_name,
                detail="; ".join(p.message for p in prepared.problems),
            ))
            return _plain({**prepared.to_dict(), "started": False,
                           "message": "nothing was started; fix the problems named and ask again"})
        preparation = prepared.preparation
        outcome = self._calculations.run(turn, preparation.run_id)
        if outcome.state is RunState.PREVIEWED:
            self._emit(BridgeEvent(
                "previewed", calculator_id, turn.display_name, run_id=preparation.run_id,
                detail=preparation.decision.reason, preparation=preparation.to_dict(),
            ))
            return _plain({
                "ok": True, "started": False, "state": "awaiting_approval", "run_id": preparation.run_id,
                "why_approval_is_needed": preparation.decision.reason,
                "message": (
                    "A preview is on the user's screen and nothing has started. Tell the user it is waiting for "
                    "their approval; do not call run_calculator for it again, and do not state any result."
                ),
            })
        self._emit(BridgeEvent(
            "finished", calculator_id, turn.display_name, run_id=preparation.run_id, state=outcome.state.value,
            detail=outcome.message,
        ))
        return bounded_json(lambda caps: outcome_envelope(outcome, caps))
