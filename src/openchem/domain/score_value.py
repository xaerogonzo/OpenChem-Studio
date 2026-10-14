"""The value of a derived score for one molecule: read the inputs, check them, evaluate, or refuse and say why (`docs/DERIVED_SCORES_DESIGN.md` sections 7 and 8).

**A VALUE IS A FUNCTION OF A DEFINITION AND THE MOLECULE'S CURRENT RESULTS, COMPUTED WHEN READ AND NEVER STORED.** A stored copy could only disagree
with its inputs. What a read produces is the number and the evidence behind it: every input with its output id, value, unit and the result it came
from, and the definition's digest. Evaluating never runs a calculator, so a score has no execution policy to decide.

**AN INPUT IS READ FROM THE MOLECULE'S CURRENT RESULTS ONLY.** A result computed on an earlier structure, or one the application has superseded, is not
used, and the refusal says so. A refused, failed or absent input refuses the score, naming the input and why. **Never a zero, and never a skipped term:**
dropping a term from a sum silently changes what the sum is. The classification is the assistant's (`turn_snapshot.classify_results`), so there is one
rule for what "current" means.

**TWO CURRENT RESULTS THAT DISAGREE ARE NOT GUESSED BETWEEN.** The same output computed with two sets of settings (two pH values, say) can both be current;
if they give different numbers the score cannot know which was meant, and it refuses. If they agree it reads either.

Pure: no Qt, no chemistry.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from openchem.domain.descriptor import DescriptorValue
from openchem.domain.report import ReportResult
from openchem.domain.score_constants import constant_values
from openchem.domain.score_definition import ScoreDefinition, check_computation
from openchem.domain.score_formula import FormulaError, Refusal, evaluate, render
from openchem.domain.score_outputs import READ_FROM, accept_value, approved_output
from openchem.domain.turn_snapshot import Freshness, Outcome, ResultEntry


class ScoreStatus(str, Enum):
    #: A number.
    VALUE = "value"
    #: No number, and the reason says why: an input that cannot be read, or a step the evaluator refused.
    REFUSED = "refused"


class InputState(str, Enum):
    """What happened when one input was read. `READ` is the only one that yields a number."""

    READ = "read"
    #: The output is no longer in the approved table.
    NOT_APPROVED = "not_approved"
    #: Nothing was ever calculated for this molecule.
    NOT_RUN = "not_run"
    #: Something was, but none of it describes the molecule as it is now (an earlier structure, or a superseded method).
    NOT_CURRENT = "not_current"
    #: The current result is a refusal: the method declined this molecule.
    REFUSED = "refused"
    #: The current result is a failure.
    FAILED = "failed"
    #: The current result does not hold the fact, or holds it twice.
    MISSING_FACT = "missing_fact"
    #: The producer did not type it as a finite number.
    NOT_A_NUMBER = "not_a_number"
    #: The result carries a unit other than the one approved. Nothing is converted.
    UNIT = "unit"
    #: Two current results give different numbers.
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class InputEvidence:
    """One input, as it was read."""

    name: str
    output_id: str
    state: InputState
    #: The number, when `state` is `READ`.
    value: float | None = None
    #: The unit the output is approved in (the language of `score_units`), and the string the result carried.
    unit: str = ""
    carried_as: str = ""
    #: The stored result it came from, when one was read.
    result_id: str = ""
    parameters_key: str = ""
    #: Why not, when it was not read.
    note: str = ""


@dataclass(frozen=True)
class ScoreValue:
    """A score's value for one molecule, or the reason it has none, with the evidence either way."""

    definition: ScoreDefinition
    status: ScoreStatus
    #: The number, when `status` is `VALUE`.
    value: float | None
    #: The unit the definition declares, which the evaluator has checked the formula works out to.
    unit: str
    #: Why there is no number, when there is none.
    reason: str
    inputs: tuple[InputEvidence, ...]
    #: The formula as the application reads it (`render`), empty when the definition no longer checks.
    formula: str

    @property
    def digest(self) -> str:
        return self.definition.digest


@dataclass(frozen=True)
class OutputRead:
    """One approved output, read from a molecule's classified results."""

    state: InputState
    value: float | None = None
    carried_as: str = ""
    result_id: str = ""
    parameters_key: str = ""
    note: str = ""


def _records_of(output_id: str, entries: Iterable[ResultEntry]) -> list[ResultEntry]:
    """The stored results made by whatever produces `output_id`, of the input approved outputs are read from, in any state."""
    kind, _, rest = output_id.partition(":")
    found = []
    for entry in entries:
        identity = entry.stored.identity
        if identity.calculation_input != READ_FROM:
            continue
        result = entry.stored.result
        if kind == "descriptor":
            if isinstance(result, DescriptorValue) and result.descriptor_id == rest:
                found.append(entry)
        elif identity.producer == rest.partition(":")[0]:
            found.append(entry)
    return found


def _why(entry: ResultEntry) -> str:
    result = entry.stored.result
    return str(getattr(result, "error_summary", None) or getattr(result, "error", None) or "the method declined this molecule")


def _typed_value(output_id: str, entry: ResultEntry) -> tuple[bool, object, str, str]:
    """`(found exactly once, the value, its units, a note)` for the fact `output_id` names in one computed record."""
    result = entry.stored.result
    kind, _, rest = output_id.partition(":")
    if kind == "descriptor":
        return True, result.value, result.units, ""
    label = rest.partition(":")[2]
    if not isinstance(result, ReportResult):
        return False, None, "", f"the result is not a report with a fact {label!r}"
    matching = [fact for fact in result.facts if fact.label == label]
    if len(matching) != 1:
        return False, None, "", f"the result holds the fact {label!r} {len(matching)} times"
    return True, matching[0].value, matching[0].units, ""


def read_output(output_id: str, entries: Iterable[ResultEntry]) -> OutputRead:
    """The number an approved output has for a molecule whose results are `entries` (`turn_snapshot.classify_results`), or why it has none."""
    output = approved_output(output_id)
    if output is None:
        return OutputRead(InputState.NOT_APPROVED, note="it is no longer an approved output")
    records = _records_of(output_id, entries)
    if not records:
        return OutputRead(InputState.NOT_RUN, note="it has not been calculated for this molecule")
    current = [entry for entry in records if entry.freshness is Freshness.CURRENT]
    if not current:
        reasons = sorted({entry.note or f"its result is {entry.freshness.value}" for entry in records})
        return OutputRead(InputState.NOT_CURRENT, note="only results that no longer describe this molecule exist: " + "; ".join(reasons))
    computed = [entry for entry in current if entry.outcome is Outcome.COMPUTED]
    if not computed:
        refused = [entry for entry in current if entry.outcome is Outcome.REFUSED]
        entry = (refused or current)[0]
        state = InputState.REFUSED if refused else InputState.FAILED
        return OutputRead(state, result_id=entry.result_id, parameters_key=entry.stored.identity.parameters_key, note=_why(entry))
    reads: list[OutputRead] = []
    for entry in computed:
        identity = entry.stored.identity
        found, value, carried, note = _typed_value(output_id, entry)
        if not found:
            reads.append(OutputRead(InputState.MISSING_FACT, result_id=entry.result_id, parameters_key=identity.parameters_key, note=note))
            continue
        # The two ways a found fact can be unusable are told apart HERE, by looking, and `accept_value` is then the one place the number is made.
        typed = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
        state = InputState.READ if typed and carried == output.carried_as else InputState.UNIT if typed else InputState.NOT_A_NUMBER
        try:
            number = accept_value(output, value, carried)
        except Refusal as exc:
            reads.append(OutputRead(state, carried_as=carried, result_id=entry.result_id, parameters_key=identity.parameters_key, note=exc.reason))
            continue
        reads.append(OutputRead(InputState.READ, number, carried, entry.result_id, identity.parameters_key))
    good = [read for read in reads if read.state is InputState.READ]
    if not good:
        return reads[0]
    if len({(read.value, read.carried_as) for read in good}) > 1:
        return OutputRead(
            InputState.AMBIGUOUS, note=f"{len(good)} current results, computed with different settings, give different numbers; the score cannot tell which was meant"
        )
    return good[0]


def _evidence(name: str, output_id: str, read: OutputRead) -> InputEvidence:
    output = approved_output(output_id)
    return InputEvidence(
        name=name, output_id=output_id, state=read.state, value=read.value, unit=output.unit if output else "",
        carried_as=read.carried_as, result_id=read.result_id, parameters_key=read.parameters_key, note=read.note,
    )


def evaluate_score(definition: ScoreDefinition, entries: Sequence[ResultEntry]) -> ScoreValue:
    """The value of `definition` for a molecule whose results are `entries`, or the reason there is none.

    Three things can refuse, in order: the definition (it no longer checks: an output left the approved table, say), an input (it cannot be read), and
    the evaluation (a division by zero, a domain error, an overflow, any non-finite step). None of them returns a number.
    """
    try:
        formula = check_computation(definition)
    except FormulaError as exc:
        return ScoreValue(definition, ScoreStatus.REFUSED, None, definition.result_unit, f"the definition no longer checks: {exc.message}", (), "")
    shown = render(formula.tree)
    evidence = tuple(_evidence(name, output_id, read_output(output_id, entries)) for name, output_id in definition.inputs)
    unread = [item for item in evidence if item.state is not InputState.READ]
    if unread:
        reason = "; ".join(f"{item.name} ({item.output_id}): {item.note}" for item in unread)
        return ScoreValue(definition, ScoreStatus.REFUSED, None, definition.result_unit, reason, evidence, shown)
    values: Mapping[str, float] = {**{item.name: float(item.value) for item in evidence}, **constant_values(definition.constants)}
    try:
        number = evaluate(formula, values)
    except Refusal as exc:
        return ScoreValue(definition, ScoreStatus.REFUSED, None, definition.result_unit, str(exc), evidence, shown)
    return ScoreValue(definition, ScoreStatus.VALUE, number, definition.result_unit, "", evidence, shown)
