"""A score the assistant PROPOSES, and a person approves or does not (`docs/DERIVED_SCORES_DESIGN.md` section 9, slice 4d).

**A MODEL CAN PROPOSE A SCORE AND CANNOT SAVE ONE.** The design record's decision 9 said the assistant cannot author a definition, because "a model that can write a formula can also
write one that happens to confirm what the person hoped". This keeps what that was protecting, which is that a person decides: a proposal is checked by exactly the rules a typed
definition meets (`score_definition.check_score_definition`), shown to the person as a card with its formula, its inputs with their units, its declared unit and the value it would give
for the molecule they have selected, and **stored only when they press Approve**, through the same `ScoreService.create` the Derived Scores window uses. Nothing here stores anything:
it parses a request, checks it, and holds a proposal until it is decided. The approval is on an object a tool is never handed (`plugins/calculation_access.PluginCalculationApprovals`),
as a run's is.

**THE MODEL CHOOSES NOTHING ABOUT WHO WROTE IT.** The owner of an approved score is `ASSISTANT_OWNER`, set here; a request that names an owner, a score id, a format, a policy or a
default is refused, because those are not the model's to say. The label is shown as always with "(user-defined, unvalidated)", and is checked against the application's own names, so a
model cannot call its formula "CNS MPO" or "QED".

**A REQUEST IS CHECKED STRICTLY AND NEVER COERCED.** A string where a number belongs is a refusal, not a conversion; so is a bool, a non-finite number, an input that is not an object,
a key nobody declared. The refusal says what and where, in the model's own terms (the request's field names), so it can fix the request and try again.

**A PROPOSAL IS BOUND TO THE PROJECT IT WAS MADE IN, AND WAITS AT MOST A FEW AT A TIME.** Approving it in another project is refused; at most `MAX_PENDING` wait together, so a model
cannot bury a person in cards; and asking for the same score again while it waits returns the one that is waiting.

Pure: no Qt, no chemistry. The thread-safety is a lock, because a tool proposes on a worker thread and the panel decides on the GUI thread.
"""

from __future__ import annotations

import math
import threading
import uuid
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from openchem.domain.score_constants import Constant
from openchem.domain.score_definition import ScoreDefinition, check_score_definition
from openchem.domain.score_formula import FormulaError
from openchem.domain.score_outputs import output_title
from openchem.domain.score_value import ScoreStatus, ScoreValue

#: Who an approved score says wrote it. Fixed here: a model cannot choose it, and a person reading the owner in the Derived Scores window sees where the formula came from.
ASSISTANT_OWNER = "AI assistant (you approved it)"

#: The id a proposal's definition has until a person approves it. Never stored: the service makes the real one from the label.
DRAFT_ID = "user.draft"

#: The most proposals waiting at once. A card is a thing a person must read; a model must not be able to bury them in cards.
MAX_PENDING = 5

#: How many settled proposals are remembered, so a repeated approve or cancel can say what became of one.
_REMEMBERED = 50

#: The request's keys. Only these: owner, id, format, policy and defaults are not the model's to give.
REQUEST_KEYS = ("label", "formula", "result_unit", "inputs", "constants", "note")
_REQUIRED = ("label", "formula", "result_unit", "inputs")


class ProposalProblem(str, Enum):
    """Why a proposal was not made."""

    #: The request is not shaped as a score (a missing field, a wrong type, a key nobody declared).
    NOT_A_REQUEST = "not_a_request"
    #: The request is shaped as a score and does not check: the definition rules refused it.
    DOES_NOT_CHECK = "does_not_check"
    #: Too many proposals are already waiting for the person.
    TOO_MANY_WAITING = "too_many_waiting"
    #: There is no project to hold a score, or the score service is holding another one.
    NO_PROJECT = "no_project"
    #: The project already holds as many scores as one may.
    PROJECT_FULL = "project_full"


@dataclass(frozen=True)
class ProposalRefusal:
    """A request that was not turned into a proposal, and why. Nothing is shown to the person for one."""

    problem: ProposalProblem
    message: str
    #: The request's field the message is about (`label`, `formula`, `result_unit`, `inputs`, `constants`, `note`), or "".
    where: str = ""
    #: A 0-based character index into the formula, when the rules found one.
    position: int | None = None
    #: The definition rules' own code (`score_formula.Problem` value) when `problem` is `DOES_NOT_CHECK`.
    rule: str = ""


class ProposalState(str, Enum):
    PENDING = "pending"
    SAVED = "saved"
    CANCELLED = "cancelled"
    #: It can no longer be saved as it was proposed (the project changed or was closed).
    VOID = "void"
    #: The person approved it and it could not be saved (the rules now refuse it, or the project is full).
    FAILED = "failed"


@dataclass(frozen=True)
class ScoreProposal:
    """One proposed score, waiting for a person."""

    proposal_id: str
    #: The project it was proposed in; it can only be saved there.
    project_uuid: str
    #: The molecule that was selected when the model asked, and its name, for the card.
    molecule_uuid: str
    molecule_name: str
    #: The definition exactly as it will be stored (owner `ASSISTANT_OWNER`, a draft id the service replaces).
    definition: ScoreDefinition
    #: What it gives for that molecule, from the turn's frozen results: a number or the reason there is none.
    preview: ScoreValue


@dataclass(frozen=True)
class ProposalOutcome:
    """What became of a proposal, said once."""

    proposal_id: str
    state: ProposalState
    label: str
    molecule_name: str
    message: str
    #: The stored score's id, when `state` is `SAVED`.
    score_id: str = ""


@dataclass(frozen=True)
class Registered:
    """A proposal in the book, and whether this call made it or found it already waiting."""

    proposal: ScoreProposal
    already_waiting: bool = False


# --- the request -----------------------------------------------------------------------------------------------------------------------------


def _not_a_request(message: str, where: str = "") -> ProposalRefusal:
    return ProposalRefusal(ProposalProblem.NOT_A_REQUEST, message, where)


def _text(request: Mapping[str, Any], key: str) -> str | ProposalRefusal:
    value = request.get(key)
    if not isinstance(value, str):
        return _not_a_request(f"{key} must be text, not {type(value).__name__ if key in request else 'missing'}", key)
    return value


def _number(value: Any, where: str) -> float | ProposalRefusal:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return _not_a_request(f"{where} must be a finite number, not {value!r}", where.split("[")[0])
    return float(value)


def definition_from_request(request: Mapping[str, Any]) -> ScoreDefinition | ProposalRefusal:
    """The definition `request` describes, or why it is not a score. Shape only: whether the definition is acceptable is `check_score_definition`'s.

    `{"label": "Polar window", "formula": "ramp(psa, 140, 60)", "result_unit": "1", "inputs": [{"name": "psa", "output": "descriptor:tpsa"}],
    "constants": [{"name": "hi", "value": 140, "unit": "Å^2"}], "note": "why"}`.
    """
    if not isinstance(request, Mapping):
        return _not_a_request(f"the request must be an object, not {type(request).__name__}")
    unknown = sorted(str(key) for key in request if key not in REQUEST_KEYS)
    if unknown:
        return _not_a_request(f"{', '.join(unknown)} {'is' if len(unknown) == 1 else 'are'} not part of a score request; it takes: {', '.join(REQUEST_KEYS)}")
    missing = [key for key in _REQUIRED if key not in request]
    if missing:
        return _not_a_request(f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} required", missing[0])
    texts = {}
    for key in ("label", "formula", "result_unit"):
        value = _text(request, key)
        if isinstance(value, ProposalRefusal):
            return value
        texts[key] = value
    note = request.get("note", "")
    if not isinstance(note, str):
        return _not_a_request(f"note must be text, not {type(note).__name__}", "note")
    raw_inputs = request["inputs"]
    if not isinstance(raw_inputs, list) or not raw_inputs:
        return _not_a_request("inputs must be a list with at least one input", "inputs")
    inputs = []
    for index, item in enumerate(raw_inputs):
        if not isinstance(item, Mapping) or set(item) != {"name", "output"} or not all(isinstance(item[key], str) for key in item):
            return _not_a_request(f"inputs[{index}] must be an object with a text name and a text output (an id from list_score_outputs), and nothing else", "inputs")
        inputs.append((item["name"], item["output"]))
    raw_constants = request.get("constants", [])
    if not isinstance(raw_constants, list):
        return _not_a_request("constants must be a list", "constants")
    constants = []
    for index, item in enumerate(raw_constants):
        if not isinstance(item, Mapping) or set(item) != {"name", "value", "unit"} or not isinstance(item["name"], str) or not isinstance(item["unit"], str):
            return _not_a_request(f"constants[{index}] must be an object with a text name, a number value and a text unit, and nothing else", "constants")
        number = _number(item["value"], f"constants[{index}].value")
        if isinstance(number, ProposalRefusal):
            return number
        constants.append(Constant(item["name"], number, item["unit"]))
    # No format, policy or default is given: the definition is made the way a typed one with none is, whatever formats this build reads.
    return ScoreDefinition(
        score_id=DRAFT_ID, label=texts["label"], formula=texts["formula"], result_unit=texts["result_unit"], inputs=tuple(inputs), constants=tuple(constants),
        owner=ASSISTANT_OWNER, created="", note=note,
    )


def check_request(request: Mapping[str, Any], reserved_names: Iterable[str] = ()) -> ScoreDefinition | ProposalRefusal:
    """The definition `request` describes once it has met every rule a typed definition meets, or the refusal that says which one it broke."""
    definition = definition_from_request(request)
    if isinstance(definition, ProposalRefusal):
        return definition
    try:
        check_score_definition(definition, reserved_names)
    except FormulaError as exc:
        return ProposalRefusal(ProposalProblem.DOES_NOT_CHECK, exc.message, exc.field or _where_of(exc), exc.position, exc.problem.value)
    return definition


def _where_of(exc: FormulaError) -> str:
    """The request's field a rule problem belongs to, for the problems that do not name one themselves. A unit problem that has a place in the formula (adding an area to a mass, a
    threshold in the wrong unit) is the formula's; only the declared result unit, which has no place in it, is `result_unit`'s."""
    if exc.problem.value == "unit" and exc.position is not None:
        return "formula"
    return {
        "syntax": "formula", "limit": "formula", "name": "formula", "function": "formula", "exponent": "formula",
        "inputs": "inputs", "output": "inputs", "consensus": "inputs", "constant": "constants", "unit": "result_unit", "definition": "label",
    }.get(exc.problem.value, "")


# --- the card --------------------------------------------------------------------------------------------------------------------------------


def card_of(proposal: ScoreProposal) -> dict[str, Any]:
    """What a person is shown to decide on a proposal, as plain text: the label as it will be shown, the formula, each input and constant with its unit, the declared unit, what
    it gives for the molecule that was selected, and who it will say wrote it. Nothing a model could dress up: every line is the definition's own."""
    definition = proposal.definition
    value = proposal.preview
    inputs = [f"{name} = {output_title(output_id) or output_id}" for name, output_id in definition.inputs]
    constants = [f"{constant.name} = {constant.value:.6g} {constant.unit}" for constant in definition.constants]
    unit = "" if definition.result_unit == "1" else f" {definition.result_unit}"
    if value.status is ScoreStatus.VALUE:
        preview = f"For {proposal.molecule_name}: {value.value:.4g}{unit}"
    else:
        preview = f"For {proposal.molecule_name}: no value yet. {value.reason}"
    return {
        "proposal_id": proposal.proposal_id,
        "label": definition.display_label,
        "formula": definition.formula,
        "inputs": inputs,
        "constants": constants,
        "declared_unit": definition.result_unit,
        "preview": preview,
        "molecule": proposal.molecule_name,
        "owner": definition.owner,
        "note": definition.note,
    }


# --- the book --------------------------------------------------------------------------------------------------------------------------------


class ProposalBook:
    """The proposals waiting for a person, and what became of the ones decided. Thread-safe: a tool adds on a worker thread, a button decides on the GUI thread."""

    def __init__(self, limit: int = MAX_PENDING) -> None:
        self._limit = limit
        self._lock = threading.RLock()
        self._pending: OrderedDict[str, ScoreProposal] = OrderedDict()
        self._settled: OrderedDict[str, ProposalOutcome] = OrderedDict()

    @staticmethod
    def new_id() -> str:
        return f"score-proposal-{uuid.uuid4().hex[:10]}"

    def register(self, candidate: ScoreProposal) -> Registered | ProposalRefusal:
        """Hold `candidate` for a person, or say why not. The same score proposed again in the same project while it waits is the one that is waiting."""
        with self._lock:
            for waiting in self._pending.values():
                if waiting.project_uuid == candidate.project_uuid and waiting.definition.digest == candidate.definition.digest and waiting.definition.label == candidate.definition.label:
                    return Registered(waiting, already_waiting=True)
            if len(self._pending) >= self._limit:
                return ProposalRefusal(
                    ProposalProblem.TOO_MANY_WAITING,
                    f"{len(self._pending)} proposals are already waiting for the person to approve or cancel them. Wait for them to decide before proposing another.",
                )
            self._pending[candidate.proposal_id] = candidate
            return Registered(candidate)

    def pending(self) -> tuple[ScoreProposal, ...]:
        """The proposals waiting, oldest first."""
        with self._lock:
            return tuple(self._pending.values())

    def get(self, proposal_id: str) -> ScoreProposal | None:
        """A WAITING proposal, or None (it was decided, or never existed)."""
        with self._lock:
            return self._pending.get(proposal_id)

    def outcome_of(self, proposal_id: str) -> ProposalOutcome | None:
        with self._lock:
            return self._settled.get(proposal_id)

    def state_of(self, proposal_id: str) -> ProposalState | None:
        with self._lock:
            if proposal_id in self._pending:
                return ProposalState.PENDING
            outcome = self._settled.get(proposal_id)
            return outcome.state if outcome is not None else None

    def settle(self, proposal_id: str, state: ProposalState, message: str, score_id: str = "") -> ProposalOutcome | None:
        """Decide a waiting proposal, once. None when it is not waiting (already decided, or unknown): a repeated button press changes nothing."""
        if state is ProposalState.PENDING:
            raise ValueError("a proposal is settled into a final state")
        with self._lock:
            proposal = self._pending.pop(proposal_id, None)
            if proposal is None:
                return None
            outcome = ProposalOutcome(proposal_id, state, proposal.definition.label, proposal.molecule_name, message, score_id)
            self._settled[proposal_id] = outcome
            while len(self._settled) > _REMEMBERED:
                self._settled.popitem(last=False)
            return outcome

    def void_outside(self, project_uuid: str, message: str) -> tuple[ProposalOutcome, ...]:
        """Settle every waiting proposal that was made in a project other than `project_uuid` as void."""
        with self._lock:
            stale = [p.proposal_id for p in self._pending.values() if p.project_uuid != project_uuid]
            return tuple(o for o in (self.settle(pid, ProposalState.VOID, message) for pid in stale) if o is not None)
