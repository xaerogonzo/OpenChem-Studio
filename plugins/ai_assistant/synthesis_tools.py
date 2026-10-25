"""The assistant's two synthesis tools: ask for a plan (a person decides) and read the plan that exists (`docs/SYNTHESIS_HELPER_DESIGN.md`, Stage 1 slice 9).

**A MODEL CAN ASK FOR A SEARCH AND CANNOT START ONE.** `SynthesisBridge` is built from `context.synthesis` (reads) and the target frozen when the user pressed Send. It is never handed
`context.synthesis_requests`, the object that starts, stops and configures a plan, so the tool has no call that could start a planner: `plan_synthesis` leaves a card on the user's screen, and
the panel's own Approve button is the only path to `request_plan`. Whoever asks, the regulatory gate runs inside `SynthesisPlanningService.request_plan`, so an approval of a card for a target
the gate refuses still starts nothing. `tests/test_ai_assistant_synthesis.py` pins which object the bridge holds and that nothing starts before Approve.

**THE TURN IS FROZEN.** What the tools read (the target, the stored plan, whether a search is under way) is captured on the GUI thread at Send, like the calculator tools' turn, because a tool runs
on the provider's worker and the live project belongs to the GUI thread. A model cannot name another molecule.

**WHAT THE MODEL IS TOLD, AND WHAT IT IS NOT.** Every sentence is the application's own: the status, the planner's identity, the standing limitations (`RouteSet.all_limitations`, always), and per
route the planner's steps with a field the planner did not supply as `null`. A plan the gate declined, or could not screen, comes back as a fixed sentence and never the reason text, which names the
rule that matched; an alert is given as its rule id, ruleset, domain, jurisdiction, section and confidence and never the name of the listing; a failed search is given as its status and never the
planner's message, which can hold paths on the user's machine. The person sees all of those in the Synthesis panel. A plan made for an earlier structure of the molecule is reported as such, with no
routes, so a route is never described as belonging to a structure it was not made for.

Worker-thread code: the calls below run on the provider's worker, which is why a request is reported through `on_event` (a queued Qt signal on the panel) and never by touching a widget.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from openchem.domain.result_envelope import CAP_STEPS
from openchem.domain.synthesis_gate import NodeScreening
from openchem.domain.synthesis_route import Route, RouteSet, RouteStatus, RouteStep, ValidationReport
from openchem.plugins.synthesis_access import PluginSynthesis, SynthesisTarget
from openchem.services.synthesis_planning_service import BoundResult

from .bridge import REPLY_BUDGET, BridgeEvent, bounded_json
from .tools import ToolDefinition

#: What the ledger and the card call a request for a plan.
REQUEST_NAME = "synthesis plan"


def card_key(molecule_uuid: str) -> str:
    """The key of the card for a molecule: one card per molecule, whatever the model asks."""
    return f"synthesis-{molecule_uuid}"


#: Said for a plan the gate did not allow. Fixed on purpose: the application's reason names the rule that matched, and the person is shown it in the panel.
GATE_DECLINED = (
    "The application's regulatory check did not allow a plan for this structure, so nothing was searched. The user has been shown why in the Synthesis panel. "
    "Do not try to obtain routes to this molecule another way."
)

#: Said for a search that did not produce a plan. The planner's own message is for the person in the panel.
NOT_PRODUCED = "The planner did not produce a plan ({status}); the Synthesis panel shows its message. There are no routes to read."

#: How to read the fields that are not covered by the standing limitations, sent with every plan.
HOW_TO_READ = {
    "null": "The planner did not supply that field. It is not zero and not 'none'; say it was not provided.",
    "alerts": (
        "An alert is a listing in a regulatory ruleset (a controlled substance, a precursor list, a workplace exposure limit ...), named here by its rule id, ruleset and domain. "
        "It is not a legal determination, and ordinary solvents and reagents often match an exposure listing. A molecule with no alert is not thereby free of obligations, and a "
        "molecule marked not screened is not a molecule without an alert."
    ),
    "consistency": "The 'consistency' fields are the route's own bookkeeping (do the molecules parse, are atoms conserved where the mapping allows). They say nothing about whether the chemistry is right.",
}


@dataclass(frozen=True)
class SynthesisTurn:
    """What a turn may read about synthesis planning, captured once on the GUI thread at Send."""

    target: SynthesisTarget
    #: The stored plan for the target, bound to the structure it was made for; None when there is none.
    plan: BoundResult | None
    #: True when a search for the target was queued or running at Send.
    planning: bool


def begin_synthesis_turn(synthesis: PluginSynthesis) -> SynthesisTurn | None:
    """Freeze the selected molecule and its plan. **GUI thread only.** None when there is no host or nothing plannable is selected."""
    target = synthesis.target()
    if target is None:
        return None
    return SynthesisTurn(target, synthesis.result_for(target.molecule_uuid), synthesis.is_planning(target.molecule_uuid))


def card_lines(card: dict[str, Any]) -> list[str]:
    """What the request card says, from the application's own record of the target and the planner's choices; nothing in it is text a model wrote."""
    chosen = f"policy {card.get('expansion') or 'not chosen'}, stock {card.get('stock') or 'not chosen'}, filter {card.get('filter') or 'none'}"
    version = f" {card['planner_version']}" if card.get("planner_version") else ""
    return [
        f"{card.get('name', '')}",
        f"Structure: {card.get('smiles', '')}",
        f"It would start the planning program you set up on this computer (AiZynthFinder{version}; {chosen}). A search can take a minute or more, and the program can use several GB of memory.",
        "The application's regulatory check on this structure runs first and can decline to plan.",
        "Routes it proposes are hypotheses from a program, not validated syntheses; it gives no conditions, reagents or yields.",
        "Proposed by the assistant. Nothing starts unless you approve.",
    ]


def _plain(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


class SynthesisBridge:
    """One turn's worth of access to the synthesis planner: read a plan, ask for one. See the module docstring."""

    def __init__(self, synthesis: PluginSynthesis, turn: SynthesisTurn | None, on_event: Callable[[BridgeEvent], None] | None = None) -> None:
        self._synthesis = synthesis
        self._turn = turn
        self._on_event = on_event or (lambda event: None)

    @property
    def available(self) -> bool:
        """True when there is a host to ask and a molecule with a structure selected to ask about."""
        return self._synthesis.available and self._turn is not None

    @property
    def turn(self) -> SynthesisTurn | None:
        return self._turn

    def _emit(self, event: BridgeEvent) -> None:
        try:
            self._on_event(event)
        except Exception:  # noqa: BLE001 - a panel that cannot draw a ledger line must not break a tool
            pass

    def _unavailable(self) -> str:
        if not self._synthesis.available:
            why = "this application did not give the assistant access to the synthesis planner"
        else:
            why = "no molecule with a structure is selected, so there is nothing to plan"
        return _plain({"ok": False, "problem": "unavailable", "message": why})

    # --- the tools --------------------------------------------------------------------------------

    def plan_synthesis(self) -> str:
        """Leave a request for a plan of the turn's molecule for the user to approve. **Starts nothing**, and has no way to: the approving is on an object this bridge is never given."""
        if not self.available:
            return self._unavailable()
        turn = self._turn
        target = turn.target
        stored = turn.plan.route_set.status if turn.plan is not None and turn.plan.is_current else None
        if stored in (RouteStatus.FOUND, RouteStatus.NO_ROUTE):
            return _plain({
                "ok": True, "started": False, "state": "plan_exists",
                "message": "A plan for this exact structure is already stored. Read it with read_synthesis_plan. A new search is started by the person from the Synthesis panel.",
            })
        if self._synthesis.is_planning(target.molecule_uuid):  # live, not as of Send: a search that ended since is not 'running'
            return _plain({
                "ok": True, "started": False, "state": "already_running",
                "message": "A search for this molecule is already running. Do not ask again; when it finishes you are told with the user's next message.",
            })
        options = self._synthesis.options()
        if not options.ok:
            self._emit(BridgeEvent(kind="refused", calculator=REQUEST_NAME, molecule=target.display_name, detail=options.problem or "the planner is not set up"))
            return _plain({
                "ok": False, "started": False, "problem": "planner_not_set_up",
                "message": "The synthesis planner is not set up on this computer, so nothing can be searched. The user can set it up under External Tools; do not describe routes from memory.",
            })
        card = {
            "molecule_uuid": target.molecule_uuid,
            "name": target.display_name,
            "smiles": target.canonical_smiles,
            "planner_version": options.version or "",
            "expansion": options.chosen_expansion or "",
            "stock": options.chosen_stock or "",
            "filter": options.chosen_filter or "none",
        }
        self._emit(BridgeEvent(kind="synthesis_proposed", calculator=REQUEST_NAME, molecule=target.display_name, run_id=card_key(target.molecule_uuid), preparation=card))
        return _plain({
            "ok": True, "started": False, "state": "awaiting_approval",
            "message": (
                "A request is on the user's screen and nothing has started. A planning program runs only if the user approves it, and the application's regulatory check runs first "
                "and can decline. Tell the user it is waiting for their approval; do not call plan_synthesis again for it, do not state or guess any route, and do not say it was started. "
                "When it ends you are told with the user's next message; then read the plan with read_synthesis_plan."
            ),
        })

    def read_synthesis_plan(self, route: int = 0) -> str:
        """The stored plan for the turn's molecule as it was when the turn began: a summary of every route, or one route in full. Read-only."""
        if not self.available:
            return self._unavailable()
        turn = self._turn
        if turn.plan is None:
            return _plain({
                "ok": True, "has_plan": False, "planning": turn.planning,
                "message": "No plan is stored for this molecule. " + ("A search is running." if turn.planning else "plan_synthesis asks the user for one."),
            })
        return bounded_json(lambda caps: plan_envelope(turn.target, turn.plan, int(route), CAP_STEPS.index(caps)), REPLY_BUDGET)


# --- what a plan looks like to a model -------------------------------------------------------------------


def _alert(finding) -> dict[str, Any]:
    """A match by its rule, not by the name of what it lists."""
    return {
        "rule_id": finding.rule_id, "ruleset_id": finding.ruleset_id, "domain": finding.domain, "jurisdiction": finding.jurisdiction,
        "section": finding.section or None, "confidence": finding.confidence or None, "user_supplied": finding.user_supplied,
    }


def _consistency(report: ValidationReport | None) -> dict[str, Any]:
    if report is None:
        return {"checked": False}
    return {
        "checked": True, "molecules_parse": report.molecules.value, "reactions_parse": report.reactions.value, "atom_mapping": report.mapping.value,
        "atoms_conserved": report.conservation.value, "starting_materials_in_stock": report.stock.value, "diagnostics": list(report.diagnostics), "missing": list(report.missing),
    }


def _step(step: RouteStep, level: int) -> dict[str, Any]:
    data: dict[str, Any] = {"makes": step.product, "from": list(step.reactants)}
    if level <= 2:
        data.update({"template_id": step.template_id, "policy_name": step.policy_name, "policy_probability": step.policy_probability})
    if level <= 1:
        data["reaction_smiles"] = step.reaction_smiles
    return data


def _screening(route: Route, screening: NodeScreening, level: int) -> dict[str, Any]:
    role = "target" if screening.smiles == route.target_smiles else "intermediate" if any(s.product == screening.smiles for s in route.steps) else "starting_material"
    data: dict[str, Any] = {"smiles": screening.smiles, "role": role, "screened": screening.screened}
    if not screening.screened:
        data["why_not"] = screening.reason
    elif level <= 2:
        data["alerts"] = [_alert(f) for f in screening.findings]
    else:
        data["alert_count"] = len(screening.findings)
    return data


def _route_summary(route_set: RouteSet, route: Route, level: int) -> dict[str, Any]:
    screenings = route_set.screenings_for(route)
    data: dict[str, Any] = {
        "route": route.rank, "steps": route.length, "starting_materials": len(route.starting_materials), "score": route.score,
        "molecules_with_alert": sum(1 for s in screenings if s.has_alert),
        "molecules_not_screened": sum(1 for s in screenings if not s.screened) if screenings else None,
        "alerts_checked": bool(screenings),
    }
    if level <= 1:
        data["consistency"] = _consistency(route.validation)
    elif level == 2:
        data["consistency"] = {"checked": route.validation is not None, "fully_validated": route.validation.fully_validated if route.validation is not None else None}
    return data


def _route_detail(route_set: RouteSet, route: Route, level: int) -> dict[str, Any]:
    screenings = route_set.screenings_for(route)
    return {
        "route": route.rank, "score": route.score,
        "steps_in_the_order_they_would_be_run": [_step(step, level) for step in route.steps],
        "starting_materials": [{"smiles": m.smiles, "in_stock": m.in_stock} for m in route.starting_materials],
        "consistency": _consistency(route.validation),
        "regulatory_alerts": {"checked": bool(screenings), "molecules": [_screening(route, s, level) for s in screenings]},
    }


def _statistics(route_set: RouteSet) -> dict[str, Any]:
    stats = route_set.statistics
    values = {"iterations": stats.iterations, "search_seconds": stats.search_seconds, "nodes": stats.nodes, "routes_returned": stats.routes_returned, "solved_routes": stats.solved_routes}
    return {name: value for name, value in values.items() if value is not None}


def plan_envelope(target: SynthesisTarget, bound: BoundResult, route: int, level: int) -> dict[str, Any]:
    """The stored plan as the model reads it. `route` 0 is the summary of every route, otherwise that route in full; `level` (0 to 3) drops detail as a reply grows."""
    route_set = bound.route_set
    header: dict[str, Any] = {
        "ok": True, "has_plan": True,
        "molecule": {"name": target.display_name, "smiles": target.canonical_smiles},
        "status": route_set.status.value,
        "current": bound.is_current,
        "limitations": list(route_set.all_limitations()),
        "how_to_read": HOW_TO_READ,
    }
    if not bound.is_current:
        return {**header, "message": "This plan was made for an EARLIER structure of this molecule, so its routes are not returned and must not be described as routes to the structure now drawn."}
    if route_set.status in (RouteStatus.REFUSED, RouteStatus.UNSCREENED):
        return {**header, "message": GATE_DECLINED}
    if route_set.status not in (RouteStatus.FOUND, RouteStatus.NO_ROUTE):
        return {**header, "message": NOT_PRODUCED.format(status=route_set.status.value)}
    header.update({
        "message": route_set.message(), "planner": route_set.planner.label(), "stopped_by": route_set.termination.value, "statistics": _statistics(route_set),
    })
    if route_set.status is RouteStatus.NO_ROUTE:
        return header
    if route == 0:
        return {**header, "routes": [_route_summary(route_set, r, level) for r in route_set.routes], "next": "call read_synthesis_plan with route=N to read one route's steps in full"}
    chosen = next((r for r in route_set.routes if r.rank == route), None)
    if chosen is None:
        return {**header, "ok": False, "problem": "unknown_route", "message": f"there is no route {route}; the routes are numbered 1 to {len(route_set.routes)}"}
    return {**header, "detail": _route_detail(route_set, chosen, level)}


# --- the definitions the model is given -----------------------------------------------------------------


PLAN_SYNTHESIS = ToolDefinition(
    name="plan_synthesis",
    description=(
        "Ask the user to let this application search for synthesis routes to the molecule they had selected when they sent their message. You CANNOT start the search: this puts a request "
        "with Approve and Cancel on the user's screen, and a planning program runs only if they approve. The application's regulatory check runs first when they do and can decline to plan; "
        "you are told the outcome with the user's next message. Never say a search has started or finished, and never describe routes before you have read them with read_synthesis_plan. "
        "It takes no arguments: you cannot name another molecule. If a plan for this exact structure is already stored it says so instead of asking again."
    ),
    input_schema={"type": "object", "properties": {}},
)

READ_SYNTHESIS_PLAN = ToolDefinition(
    name="read_synthesis_plan",
    description=(
        "Read the synthesis plan stored for the molecule the user had selected when they sent their message, as it was then. With no argument it summarises every route (steps, starting "
        "materials, the planner's score, the route's own consistency checks and how many of its molecules carry a regulatory alert); with route=N it gives that route's steps in the order "
        "they would be run. A route is a hypothesis from a program, not a validated or feasible synthesis, and the planner supplies no conditions, reagents, solvents or yields: say so, and "
        "do not supply them from memory. A policy probability is the model's score for a template, not a yield and not a chance that a step works. 'null' means not provided, never zero. "
        "A plan marked not current was made for an earlier structure and has no routes here. A refused or failed plan has no routes: say that and nothing more. An alert is a listing in a "
        "ruleset, not a legal determination, and no alert is not clearance. Report the limitations the reply carries."
    ),
    input_schema={
        "type": "object",
        "properties": {"route": {"type": "integer", "minimum": 0, "maximum": 50, "description": "A route number to read in full; 0 or omitted for the summary of every route."}},
    },
)

#: Offered with the calculator tools when a molecule with a structure is selected and the planner is reachable.
SYNTHESIS_TOOLS: list[ToolDefinition] = [PLAN_SYNTHESIS, READ_SYNTHESIS_PLAN]


def _plan(bridge: SynthesisBridge) -> str:
    return bridge.plan_synthesis()


def _read(bridge: SynthesisBridge, route: int = 0) -> str:
    return bridge.read_synthesis_plan(route)


#: Handler by tool name; every one takes the turn's `SynthesisBridge` first.
SYNTHESIS_HANDLERS: dict[str, Callable[..., str]] = {"plan_synthesis": _plan, "read_synthesis_plan": _read}

__all__ = [
    "GATE_DECLINED", "HOW_TO_READ", "NOT_PRODUCED", "PLAN_SYNTHESIS", "READ_SYNTHESIS_PLAN", "REQUEST_NAME", "SYNTHESIS_HANDLERS", "SYNTHESIS_TOOLS", "SynthesisBridge",
    "SynthesisTurn", "begin_synthesis_turn", "card_key", "card_lines", "plan_envelope",
]
