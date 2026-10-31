"""The nine tools that let the assistant read and run the application's calculators, read the ORCA jobs a person ran, read the user's own scores, and PROPOSE a score for the user to approve.

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

READ_QUANTUM_RUNS = ToolDefinition(
    name="read_quantum_runs",
    description=(
        "Read the ORCA jobs (quantum-chemistry runs) a person has ALREADY run for the molecule the user had selected when they sent their message: which calculation, method and basis, charge and multiplicity, "
        "how it ended ('computed', 'computed_with_warnings', 'failed' or 'cancelled'), what it warned about, and which outputs it produced. This is the history, so it covers what read_results cannot: a job that "
        "failed or was cancelled, the warnings a finished job came back with, and spectra and vibrational analyses. With no arguments it lists the current runs as headers only, newest first, with no numbers; call it "
        "again with run_ids to read the numbers of at most three runs at a time. Each run has a 'freshness': 'current' means it was run on the structure now drawn; 'historical' or 'unverifiable' do not describe it, are listed only "
        "when include_not_current is true, and must never be reported as the answer for this molecule. A 'failed' or 'cancelled' run has no numbers: say how it ended and quote its warnings. An output with status "
        "'not_produced' or 'inapplicable' means that job could not give it: say so, never treat it as zero. You cannot stop or approve a job. You can ask for a new one with run_calculator (an orca.* calculator): that leaves a card with its settings, and the job starts only if the user approves it."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "run_ids": {"type": "array", "items": {"type": "string"}, "description": "Run ids from an earlier list, to read those runs in full; omit to list the runs."},
            "include_not_current": {"type": "boolean", "description": "Also list runs made on an earlier structure of this molecule."},
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

LIST_SCORE_OUTPUTS = ToolDefinition(
    name="list_score_outputs",
    description=(
        "List the outputs a score's formula may read: each with its output_id, what it measures, the unit to write for it and its endpoint. Use it before propose_score, and never invent an "
        "output id. Read-only; it does not read the user's molecule. Two outputs with the same endpoint cannot be in one score."
    ),
    input_schema={"type": "object", "properties": {}},
)

PROPOSE_SCORE = ToolDefinition(
    name="propose_score",
    description=(
        "Propose a user-defined SCORE for the user to approve: a formula over numbers this application computes, such as a weighted blend of desirabilities. You CANNOT save it. It is checked by "
        "the rules a score the user typed meets, and if it passes, a card with the formula, its inputs and the value it gives for the selected molecule appears for the user to Approve or "
        "Cancel; nothing is saved unless they approve, and you are told what they decided with their next message. Never say it is saved or that you created it. "
        "Inputs are outputs from list_score_outputs, each given a lowercase name. The formula uses numbers, those names, constant names, + - * / and ^ with a whole-number exponent, "
        "parentheses, and abs, min, max, clamp, ramp, sqrt, ln, log10, exp, and nothing else (no comparisons, no conditionals). ramp(x, bad, good) is 0 at bad, 1 at good and linear between. "
        "Units are checked and never converted: add only like units, and result_unit must equal the unit the formula works out to ('1' for a plain number). A bare number takes the unit of "
        "what it is added to or compared with; a named constant carries its own unit. The label may not be close to a name the application gives, so do not call a score 'CNS MPO' or 'QED'. "
        "It is shown as '<label> (user-defined, unvalidated)': an unvalidated formula, never a prediction, so offer weights and thresholds as a starting point the user can change, and say "
        "where each came from. A refused request says which field and why: fix it and try again. At most 5 proposals wait at once."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "What the score is called, at most 80 characters."},
            "formula": {"type": "string", "description": "The formula, at most 500 characters."},
            "result_unit": {"type": "string", "description": "The unit the formula works out to; '1' for a plain number."},
            "inputs": {
                "type": "array", "items": {"type": "object"},
                "description": "Each {\"name\": \"psa\", \"output\": \"descriptor:tpsa\"}: the name the formula uses and an output_id from list_score_outputs.",
            },
            "constants": {
                "type": "array", "items": {"type": "object"},
                "description": "Optional. Each {\"name\": \"hi\", \"value\": 140, \"unit\": \"Å^2\"}: a named number with a unit.",
            },
            "note": {"type": "string", "description": "Optional. Why these weights and thresholds, at most 500 characters."},
        },
        "required": ["label", "formula", "result_unit", "inputs"],
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
        "that you did. An ORCA calculator (orca.sp, orca.opt, orca.opt_freq, orca.nmr, orca.nmr_coupling, orca.delta_scf, orca.led, orca.proton_affinity, orca.bond_dissociation_enthalpy) is always "
        "'awaiting_approval': the card shows its settings, ORCA starts only if the user approves it, and a job can run for minutes to hours. When it ends you are told with the "
        "user's next message; then read it with read_quantum_runs, never from memory."
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
CALCULATION_TOOLS: list[ToolDefinition] = [FIND_CALCULATORS, LIST_GOALS, DESCRIBE_CALCULATOR, READ_RESULTS, READ_QUANTUM_RUNS, READ_SCORES, LIST_SCORE_OUTPUTS, PROPOSE_SCORE, RUN_CALCULATOR]


def _find(bridge: ToolBridge, query: str = "", limit: int = 10) -> str:
    return bridge.find_calculators(query, limit)


def _goals(bridge: ToolBridge, goal_id: str = "") -> str:
    return bridge.list_goals(goal_id)


def _describe(bridge: ToolBridge, calculator_id: str) -> str:
    return bridge.describe_calculator(calculator_id)


def _read(bridge: ToolBridge, calculators: list[str] | None = None, include_not_current: bool = False) -> str:
    return bridge.read_results(calculators, include_not_current)


def _runs(bridge: ToolBridge, run_ids: list[str] | None = None, include_not_current: bool = False) -> str:
    return bridge.read_quantum_runs(run_ids, include_not_current)


def _scores(bridge: ToolBridge, scores: list[str] | None = None) -> str:
    return bridge.read_scores(scores)


def _score_outputs(bridge: ToolBridge) -> str:
    return bridge.list_score_outputs()


def _propose(bridge: ToolBridge, **request: Any) -> str:
    return bridge.propose_score(request)


def _run(bridge: ToolBridge, calculator_id: str, parameters: dict[str, Any] | None = None) -> str:
    return bridge.run_calculator(calculator_id, parameters)


#: Handler by tool name; every one takes the turn's `ToolBridge` first.
CALCULATION_HANDLERS: dict[str, Callable[..., str]] = {
    "find_calculators": _find,
    "list_goals": _goals,
    "describe_calculator": _describe,
    "read_results": _read,
    "read_quantum_runs": _runs,
    "read_scores": _scores,
    "list_score_outputs": _score_outputs,
    "propose_score": _propose,
    "run_calculator": _run,
}
