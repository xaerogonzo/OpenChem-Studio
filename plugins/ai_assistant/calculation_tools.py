"""The six tools that let the assistant read and run the application's calculators and read the user's own scores.

Each takes the turn's `ToolBridge` as its first argument, unlike the two older tools in `tools.py`, which
take only what the model sent. The descriptions below are the model's whole understanding of what each
tool is for, so they say what a result may and may not be used for, in the words the application itself
uses: `route` (auto, needs_approval, preview_only), `freshness` (current, historical, unverifiable) and
`outcome` (computed, refused, failed).

**NONE OF THEM CAN APPROVE.** `run_calculator` prepares a request and, if the calculator may run on its own
and the request is inside what its cost was measured for, runs it; otherwise it leaves a preview on the
user's screen for the user to approve. See `bridge.py` and `docs/AI_CALCULATION_BRIDGE.md`.
"""

from __future__ import annotations

from typing import Any, Callable

from openchem.domain.calculator_goals import GOALS

from .bridge import MAX_SEARCH, ToolBridge
from .tools import ToolDefinition

FIND_CALCULATORS = ToolDefinition(
    name="find_calculators",
    description=(
        "Search this application's calculators. Every word of `query` must appear in a calculator's name, "
        "description, heading or tags, in any order; an empty query lists them in the order Properties shows them. "
        "Each result says what YOU can do with it: route 'auto' means you may run it with run_calculator; "
        "'needs_approval' means run_calculator will prepare a preview that the user must approve; 'preview_only' "
        "means it runs from its own panel and you cannot start it. 'needs' lists inputs only the user can give. "
        "Use this to find a calculator id before describing or running it, rather than guessing one."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Words to look for, for example 'solubility' or 'lewis adduct'."},
            "limit": {"type": "integer", "minimum": 1, "maximum": MAX_SEARCH, "description": "At most this many (default 10)."},
        },
    },
)

LIST_GOALS = ToolDefinition(
    name="list_goals",
    description=(
        "The questions this application's own 'goal wizard' offers (identity, charge, solubility, shape, drug-likeness "
        "...) and the calculators it chose to answer each, with the reason each is there. Call it with no argument to "
        "see every goal; call it with a goal_id to see that goal's calculators in full, each with what YOU can do with "
        "it (you_may_run, needs_user_approval, cannot_start_here) and the settings the goal uses. Use it when the "
        "question is 'what should I look at for X' rather than about one named calculator. The lists are editorial, "
        "not a validated protocol; it starts nothing, so run the calculators you choose with run_calculator."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "goal_id": {"type": "string", "enum": [goal.goal_id for goal in GOALS], "description": "A goal to list in full."},
        },
    },
)

DESCRIBE_CALCULATOR = ToolDefinition(
    name="describe_calculator",
    description=(
        "Everything this application says about one calculator: what it measures, its stage of maturity and why, "
        "whether you may run it ('route'), what it costs and what external program it starts, and every setting it "
        "takes with its kind, default, bounds and the exact stored CHOICES (not their display labels). Call this "
        "before run_calculator when you intend to pass settings, so that you use values the calculator accepts."
    ),
    input_schema={
        "type": "object",
        "properties": {"calculator_id": {"type": "string", "description": "An id from find_calculators."}},
        "required": ["calculator_id"],
    },
)

READ_RESULTS = ToolDefinition(
    name="read_results",
    description=(
        "Read what this application has ALREADY computed and stored for the molecule the user had selected when "
        "they sent their message. You cannot name another molecule. Every result carries its method, settings, the "
        "structure it was computed on (drawing or a stored conformer), its units, and a 'freshness': 'current' means "
        "it still describes the molecule; 'historical' or 'unverifiable' do not and are returned only when "
        "include_not_current is true, and must never be reported as the current answer. A calculator listed under "
        "'not_run' has no result at all: say so, and never state a value for it or treat it as zero. A result with "
        "outcome 'refused' or 'failed' has no numbers; quote its refusal. If you need a value that is not here, "
        "use run_calculator rather than answering from memory."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "calculators": {
                "type": "array", "items": {"type": "string"},
                "description": "Calculator ids (or result ids) to read; omit for everything stored.",
            },
            "include_not_current": {"type": "boolean", "description": "Also return historical and unverifiable results."},
        },
    },
)

READ_SCORES = ToolDefinition(
    name="read_scores",
    description=(
        "Read the user-defined SCORES of this project for the molecule the user had selected when they sent their message: formulas a person wrote over numbers this application "
        "computes, such as a weighted sum of desirabilities. A score is not stored with the results, so read_results never shows one. Each score has its label (always ending "
        "'(user-defined, unvalidated)'), its formula, its declared units, every input with the state it was read in, and a value only when every input could be read from the "
        "molecule's CURRENT results. A score with outcome 'refused' has no value: say which input could not be read and why, and never state a value or treat it as zero. A score with outcome 'computed_with_defaults' used a default its definition declares for an input nobody calculated: name those inputs (defaults_used) and never present the number as the result of calculating them. A score "
        "is not a prediction and nothing has validated it, so never present one as an experimental or predicted property. Omit `scores` to read every score, or name some by id "
        "or label; a name that matches nothing is returned under 'not_found'. You cannot create, change or delete a score; you may suggest formula text for the person to enter "
        "in Tools > Derived Scores. A score whose input has not been calculated gets its value when the calculator has run (run_calculator)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "scores": {"type": "array", "items": {"type": "string"}, "description": "Score ids (such as user.polar_window) or labels to read; omit for every score."},
        },
    },
)

RUN_CALCULATOR = ToolDefinition(
    name="run_calculator",
    description=(
        "Run one calculator on the molecule the user had selected when they sent their message. The run is recorded "
        "in the user's project and appears in their Results exactly like one they ran themselves, so run only what the "
        "question needs. Settings are checked against the calculator's definition before anything starts, and every "
        "problem is returned at once; an invalid setting is refused, never corrected. Outcomes: 'completed' (a result, "
        "with its method, units and freshness), 'refused' (the method declined; quote the reason), 'failed', "
        "'awaiting_approval' (a preview is on the user's screen and nothing has started: tell the user it needs "
        "their approval, do not call this again for it, and state no result), or 'timed_out' (still running; its "
        "result will appear in Results, do not ask again). You cannot approve a preview and must never imply "
        "that you did."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "calculator_id": {"type": "string", "description": "An id from find_calculators."},
            "parameters": {
                "type": "object",
                "description": "Settings by name, using the choices and bounds describe_calculator reports. Omit for the defaults.",
            },
        },
        "required": ["calculator_id"],
    },
)

#: The definitions offered to a provider when a molecule is selected and the calculators are reachable.
CALCULATION_TOOLS: list[ToolDefinition] = [FIND_CALCULATORS, LIST_GOALS, DESCRIBE_CALCULATOR, READ_RESULTS, READ_SCORES, RUN_CALCULATOR]


def _find(bridge: ToolBridge, query: str = "", limit: int = 10) -> str:
    return bridge.find_calculators(query, limit)


def _goals(bridge: ToolBridge, goal_id: str = "") -> str:
    return bridge.list_goals(goal_id)


def _describe(bridge: ToolBridge, calculator_id: str) -> str:
    return bridge.describe_calculator(calculator_id)


def _read(bridge: ToolBridge, calculators: list[str] | None = None, include_not_current: bool = False) -> str:
    return bridge.read_results(calculators, include_not_current)


def _scores(bridge: ToolBridge, scores: list[str] | None = None) -> str:
    return bridge.read_scores(scores)


def _run(bridge: ToolBridge, calculator_id: str, parameters: dict[str, Any] | None = None) -> str:
    return bridge.run_calculator(calculator_id, parameters)


#: Handler by tool name; every one takes the turn's `ToolBridge` first.
CALCULATION_HANDLERS: dict[str, Callable[..., str]] = {
    "find_calculators": _find,
    "list_goals": _goals,
    "describe_calculator": _describe,
    "read_results": _read,
    "read_scores": _scores,
    "run_calculator": _run,
}
