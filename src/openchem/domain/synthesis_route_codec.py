"""A synthesis plan as plain data, for the project file (`docs/SYNTHESIS_HELPER_DESIGN.md`, "Saving plans in the project").

PURE: dicts, lists, strings and numbers in and out; no RDKit, no Qt, no process. `encode_route_set` writes what a plan IS; `decode_route_set` reads it back through the same constructors that built it,
so a stored plan that is not a tree, has a rank out of order or carries a probability outside 0 to 1 is refused exactly as the planner's own output would have been.

WHAT IS WRITTEN, AND WHAT IS NOT. Written: the status and how the search ended, the target, the planner's identity and limits, its statistics, every route (steps, reaction strings, template ids,
policy probabilities, starting materials with their stock flags), the regulatory screening of each molecule and the one added sentence about routes the parser left out. NOT written, each
for its own reason:

* **`reason`**, because only a plan that found routes or found none is kept (`STORABLE`), and neither has one. A refusal, a failure, a cancellation, an unavailable planner and an unscreened target
  are the outcome of one request, not a result: a stored refusal would outlive the ruleset that made it, and re-asking costs nothing.
* **`limitations`**, because the standing sentences are the reading build's to say, not the file's. A file is data a person can edit or send; a sentence in it that the application then shows,
  and that an assistant may read, is text from outside. The reader re-derives the standing sentences, the planner's measured result and the note on the age of the screening, and keeps only a
  sentence that begins `LEFT_OUT_PREFIX`.
* **each route's `validation`**, because it is a function of the route alone and the build that reads the file recomputes it (`chem/route_validation.py`): a validator improved since is then
  what a person sees, and the file cannot claim a check passed.

NOTHING A FILE SAYS IS TRUSTED TO BE WELL FORMED. A string is bounded in length and must be printable (no control characters, so no line that could pass for a new paragraph), a SMILES or an
identifier holds no white space, and the number of routes, steps and screenings is capped, so a file cannot make a build allocate without end. Anything wrong raises `PlanDecodeError`; the
store (`domain/synthesis_plan_store.py`) turns that into "this plan was not restored" and carries on with the others.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from openchem.domain.synthesis_gate import AlertFinding, NodeScreening
from openchem.domain.synthesis_route import (
    LEFT_OUT_PREFIX,
    STANDARD_LIMITATIONS,
    SYNTHESIS_ROUTE_FORMAT,
    PlannerIdentity,
    Route,
    RouteMolecule,
    RouteSet,
    RouteStatus,
    RouteStep,
    SearchLimits,
    SearchStatistics,
    SearchTermination,
    TargetIdentity,
)

#: The statuses a project file keeps: a search that ran to an end and either found routes or did not. Every other status is the outcome of one request and is asked again (see the module docstring).
STORABLE = frozenset({RouteStatus.FOUND, RouteStatus.NO_ROUTE})

#: Caps on what a file may make a build hold. A real plan is a dozen routes of a few steps; these are far above that and far below "without end".
MAX_ROUTES = 200
MAX_STEPS = 100
MAX_REACTANTS = 50
MAX_STARTING_MATERIALS = 200
MAX_SCREENINGS = 5000
MAX_FINDINGS = 200
MAX_MODEL_ENTRIES = 20
MAX_SENTENCE = 2000
_TOKEN = 20000
_WORDS = 500
_REACTION = 40000


class PlanDecodeError(ValueError):
    """A stored plan this build cannot read. The message says what was wrong and never repeats the offending text."""


def encode_route_set(route_set: RouteSet) -> dict[str, Any]:
    """The plan as JSON-ready data. Raises `ValueError` for a status the file does not keep."""
    if route_set.status not in STORABLE:
        raise ValueError(f"a plan with status '{route_set.status}' is not kept in a project file")
    limits = route_set.planner.limits
    stats = route_set.statistics
    data: dict[str, Any] = {
        "format": route_set.format,
        "status": route_set.status.value,
        "termination": route_set.termination.value,
        "target": {
            "molecule_uuid": route_set.target.molecule_uuid,
            "canonical_smiles": route_set.target.canonical_smiles,
            "fingerprint": route_set.target.fingerprint,
        },
        "planner": {
            "planner": route_set.planner.planner,
            "version": route_set.planner.version,
            "model_identity": [[key, value] for key, value in route_set.planner.model_identity],
            "config_sha256": route_set.planner.config_sha256,
            "limits": {
                "iteration_limit": limits.iteration_limit,
                "time_limit_seconds": limits.time_limit_seconds,
                "max_transforms": limits.max_transforms,
            },
        },
        "statistics": {
            "iterations": stats.iterations,
            "search_seconds": stats.search_seconds,
            "first_solution_iteration": stats.first_solution_iteration,
            "nodes": stats.nodes,
            "routes_returned": stats.routes_returned,
            "solved_routes": stats.solved_routes,
        },
        "routes": [_encode_route(route) for route in route_set.routes],
        "left_out": [s for s in route_set.limitations if s.startswith(LEFT_OUT_PREFIX)],
    }
    if route_set.node_screenings:
        data["node_screenings"] = [_encode_screening(s) for s in route_set.node_screenings]
    return data


def decode_route_set(data: Any) -> tuple[RouteSet, tuple[str, ...]]:
    """The plan a block describes, and what had to be left out of it (the screening, when it could not be read).

    Raises `PlanDecodeError` for anything else wrong. The routes come back with no `validation`, and the limitations are the standing ones plus a kept left-out sentence: the reader adds the rest.
    """
    root = _mapping(data, "the plan")
    fmt = _int(root.get("format"), "format", minimum=1)
    # A format this build does not know is not read at all: it may mean what these fields mean, or something else.
    if fmt != SYNTHESIS_ROUTE_FORMAT:
        raise PlanDecodeError(f"the plan is in format {fmt}; this build reads format {SYNTHESIS_ROUTE_FORMAT}")
    status = _enum(RouteStatus, root.get("status"), "status")
    if status not in STORABLE:
        raise PlanDecodeError(f"a plan with status '{status.value}' is not kept in a project file")
    termination = _enum(SearchTermination, root.get("termination"), "termination")
    target_data = _mapping(root.get("target"), "target")
    planner_data = _mapping(root.get("planner"), "planner")
    limits_data = _mapping(planner_data.get("limits"), "planner limits")
    stats_data = _mapping(root.get("statistics"), "statistics")
    try:
        target = TargetIdentity(
            molecule_uuid=_words(target_data.get("molecule_uuid"), "target molecule", _WORDS),
            canonical_smiles=_token(target_data.get("canonical_smiles"), "target SMILES", _TOKEN),
            fingerprint=_words(target_data.get("fingerprint"), "target fingerprint", _TOKEN),
        )
        planner = PlannerIdentity(
            planner=_words(planner_data.get("planner"), "planner", _WORDS),
            version=_words(planner_data.get("version"), "planner version", _WORDS),
            model_identity=_model_identity(planner_data.get("model_identity")),
            config_sha256=_optional(planner_data.get("config_sha256"), _token, "configuration hash", 128),
            limits=SearchLimits(
                iteration_limit=_optional(limits_data.get("iteration_limit"), _int, "iteration limit"),
                time_limit_seconds=_optional(limits_data.get("time_limit_seconds"), _number, "time limit"),
                max_transforms=_optional(limits_data.get("max_transforms"), _int, "maximum transforms"),
            ),
        )
        statistics = SearchStatistics(
            iterations=_optional(stats_data.get("iterations"), _int, "iterations"),
            search_seconds=_optional(stats_data.get("search_seconds"), _number, "search seconds"),
            first_solution_iteration=_optional(stats_data.get("first_solution_iteration"), _int, "first solution iteration"),
            nodes=_optional(stats_data.get("nodes"), _int, "nodes"),
            routes_returned=_optional(stats_data.get("routes_returned"), _int, "routes returned"),
            solved_routes=_optional(stats_data.get("solved_routes"), _int, "solved routes"),
        )
        routes = tuple(_decode_route(r) for r in _list(root.get("routes"), "routes", MAX_ROUTES))
        left_out = tuple(
            s
            for s in (_words(item, "a left-out sentence", MAX_SENTENCE) for item in _list(root.get("left_out", []), "left_out", 4))
            if s.startswith(LEFT_OUT_PREFIX)
        )
        screenings: tuple[NodeScreening, ...] = ()
        notes: list[str] = []
        raw_screenings = root.get("node_screenings")
        if raw_screenings is not None:
            try:
                screenings = tuple(_decode_screening(s) for s in _list(raw_screenings, "node_screenings", MAX_SCREENINGS))
                # Built with the routes, so a screening of the wrong molecules is found now, not at the first use.
                RouteSet(status=status, target=target, planner=planner, routes=routes, termination=termination, node_screenings=screenings)
            except (PlanDecodeError, ValueError, TypeError) as exc:
                # An annotation is not worth the plan: the plan is read without it and says its molecules were not checked.
                screenings = ()
                notes.append(f"the regulatory screening of the plan was not readable and is left out ({_short(exc)})")
        route_set = RouteSet(
            status=status,
            target=target,
            planner=planner,
            routes=routes,
            termination=termination,
            statistics=statistics,
            limitations=STANDARD_LIMITATIONS + left_out,
            node_screenings=screenings,
        )
    except PlanDecodeError:
        raise
    except (ValueError, TypeError) as exc:
        raise PlanDecodeError(f"the plan is not one a route set can be built from ({_short(exc)})") from exc
    return route_set, tuple(notes)


# --- routes ------------------------------------------------------------------------------------------------------------------------------


def _encode_route(route: Route) -> dict[str, Any]:
    return {
        "target_smiles": route.target_smiles,
        "rank": route.rank,
        "score": route.score,
        "steps": [
            {
                "product": step.product,
                "reactants": list(step.reactants),
                "reaction_smiles": step.reaction_smiles,
                "template_id": step.template_id,
                "policy_name": step.policy_name,
                "policy_probability": step.policy_probability,
            }
            for step in route.steps
        ],
        "starting_materials": [{"smiles": m.smiles, "in_stock": m.in_stock} for m in route.starting_materials],
    }


def _decode_route(data: Any) -> Route:
    item = _mapping(data, "a route")
    steps = tuple(_decode_step(s) for s in _list(item.get("steps"), "steps", MAX_STEPS))
    materials = tuple(_decode_material(m) for m in _list(item.get("starting_materials"), "starting materials", MAX_STARTING_MATERIALS))
    return Route(
        target_smiles=_token(item.get("target_smiles"), "route target", _TOKEN),
        steps=steps,
        starting_materials=materials,
        rank=_int(item.get("rank"), "rank", minimum=1),
        score=_optional(item.get("score"), _number, "score"),
    )


def _decode_step(data: Any) -> RouteStep:
    item = _mapping(data, "a step")
    return RouteStep(
        product=_token(item.get("product"), "step product", _TOKEN),
        reactants=tuple(_token(r, "step reactant", _TOKEN) for r in _list(item.get("reactants"), "reactants", MAX_REACTANTS)),
        reaction_smiles=_optional(item.get("reaction_smiles"), _token, "reaction", _REACTION),
        template_id=_optional(item.get("template_id"), _token, "template id", _WORDS),
        policy_name=_optional(item.get("policy_name"), _token, "policy name", _WORDS),
        policy_probability=_optional(item.get("policy_probability"), _number, "policy probability"),
    )


def _decode_material(data: Any) -> RouteMolecule:
    item = _mapping(data, "a starting material")
    return RouteMolecule(smiles=_token(item.get("smiles"), "starting material", _TOKEN), in_stock=_optional(item.get("in_stock"), _bool, "stock flag"))


# --- screenings --------------------------------------------------------------------------------------------------------------------------


def _encode_screening(screening: NodeScreening) -> dict[str, Any]:
    return {
        "smiles": screening.smiles,
        "screened": screening.screened,
        "findings": [
            {
                "ruleset_id": f.ruleset_id,
                "rule_id": f.rule_id,
                "display_name": f.display_name,
                "domain": f.domain,
                "jurisdiction": f.jurisdiction,
                "section": f.section,
                "confidence": f.confidence,
                "match_type": f.match_type,
                "user_supplied": f.user_supplied,
            }
            for f in screening.findings
        ],
        "rulesets_consulted": list(screening.rulesets_consulted),
        "screened_on": screening.screened_on,
        "reason": screening.reason,
    }


def _decode_screening(data: Any) -> NodeScreening:
    item = _mapping(data, "a screening")
    return NodeScreening(
        smiles=_token(item.get("smiles"), "screened molecule", _TOKEN),
        screened=_bool(item.get("screened"), "screened"),
        findings=tuple(_decode_finding(f) for f in _list(item.get("findings", []), "findings", MAX_FINDINGS)),
        rulesets_consulted=tuple(_words(r, "a ruleset id", _WORDS) for r in _list(item.get("rulesets_consulted", []), "rulesets", MAX_FINDINGS)),
        screened_on=_text(item.get("screened_on", ""), "screening date", _WORDS, blank_ok=True),
        reason=_text(item.get("reason", ""), "screening reason", MAX_SENTENCE, blank_ok=True),
    )


def _decode_finding(data: Any) -> AlertFinding:
    item = _mapping(data, "a finding")

    def field(key: str, *, blank_ok: bool = True) -> str:
        return _text(item.get(key, ""), key, _WORDS, blank_ok=blank_ok)

    return AlertFinding(
        ruleset_id=field("ruleset_id", blank_ok=False),
        rule_id=field("rule_id", blank_ok=False),
        display_name=field("display_name", blank_ok=False),
        domain=field("domain"),
        jurisdiction=field("jurisdiction"),
        section=field("section"),
        confidence=field("confidence"),
        match_type=field("match_type"),
        user_supplied=_bool(item.get("user_supplied", False), "user_supplied"),
    )


# --- reading one value, strictly ---------------------------------------------------------------------------------------------------------


def _short(exc: BaseException) -> str:
    """What went wrong, bounded and without the offending value's text beyond a short head, so a message cannot carry a file's own prose."""
    text = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    return text[:160]


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PlanDecodeError(f"{name} is not an object")
    return value


def _list(value: Any, name: str, cap: int) -> list[Any]:
    if not isinstance(value, list):
        raise PlanDecodeError(f"{name} is not a list")
    if len(value) > cap:
        raise PlanDecodeError(f"{name} has {len(value)} entries; this build reads at most {cap}")
    return value


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise PlanDecodeError(f"{name} is not true or false")
    return value


def _int(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PlanDecodeError(f"{name} is not a whole number of at least {minimum}")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PlanDecodeError(f"{name} is not a finite number")
    return value


def _enum(kind: Any, value: Any, name: str) -> Any:
    try:
        return kind(value)
    except ValueError:
        raise PlanDecodeError(f"{name} is not one this build knows") from None


def _text(value: Any, name: str, cap: int, *, blank_ok: bool = False) -> str:
    """A bounded, printable string. Control characters (newlines among them) are refused: a value read from a file is never allowed to be a paragraph."""
    if not isinstance(value, str):
        raise PlanDecodeError(f"{name} is not text")
    if len(value) > cap:
        raise PlanDecodeError(f"{name} is longer than {cap} characters")
    if value and not value.isprintable():
        raise PlanDecodeError(f"{name} holds a character that is not printable")
    if not blank_ok and not value.strip():
        raise PlanDecodeError(f"{name} is blank")
    return value


def _words(value: Any, name: str, cap: int = _WORDS) -> str:
    return _text(value, name, cap)


def _token(value: Any, name: str, cap: int = _TOKEN) -> str:
    """A SMILES or an identifier: printable, bounded and without any white space."""
    text = _text(value, name, cap)
    if any(ch.isspace() for ch in text):
        raise PlanDecodeError(f"{name} holds white space")
    return text


def _optional(value: Any, reader: Any, name: str, *extra: Any) -> Any:
    """`None` stays `None` (a field the planner did not supply); anything else is read by `reader`."""
    if value is None:
        return None
    return reader(value, name, *extra)


def _model_identity(value: Any) -> tuple[tuple[str, str], ...]:
    pairs = []
    for entry in _list(value, "model identity", MAX_MODEL_ENTRIES):
        if not isinstance(entry, list) or len(entry) != 2:
            raise PlanDecodeError("a model identity entry is not a pair")
        pairs.append((_words(entry[0], "a model name", _WORDS), _words(entry[1], "a model value", _WORDS)))
    return tuple(pairs)
