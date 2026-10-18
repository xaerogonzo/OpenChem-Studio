"""The value of a derived score for one molecule: read the inputs, check them, evaluate, or refuse and say why (`docs/DERIVED_SCORES_DESIGN.md` sections 7 and 8).

**A VALUE IS A FUNCTION OF A DEFINITION AND THE MOLECULE'S CURRENT RESULTS, COMPUTED WHEN READ AND NEVER STORED.** A stored copy could only disagree
with its inputs. What a read produces is the number and the evidence behind it: every input with its output id, value, unit and the result it came
from, and the definition's digest. Evaluating never runs a calculator, so a score has no execution policy to decide.

**AN OUTPUT HAS ONE INPUT, AND ONLY A RESULT OF THAT INPUT IS READ FOR IT** (`score_outputs.ApprovedOutput.input`). Nearly all are read from the drawing; the shape descriptors and Geometry Analysis's eight sizes are read from the
GEOMETRY of the conformer every calculation uses (`chem/calculation_input.canonical_conformer`), so a score cannot disagree with Properties or the project table about which structure it means.
A geometry result is current only while its fingerprint is that conformer's CURRENT one: when the conformers are generated again or an ORCA optimisation lands, the conformer every calculation uses
changes, the old result reads "calculated for an earlier geometry of this molecule", and a number of another conformer is never offered in its place. A molecule with no conformer says it needs one.

**A CURRENT GEOMETRY RESULT IS STILL NOT READ WHEN IT IS NOT A NUMBER OF THAT CONFORMER, OR NOT OF ONE COMPOUND** (`not_applicable_reason`, state `NOT_APPLICABLE`). Geometry Analysis measures the WHOLE structure, and a
structure of several fragments (a salt, a hydrate) has no 3D shape of its own: the embedder packs the pieces together at an arbitrary offset, which the calculator's own caveat says (every one of the five multi-fragment
census structures carries "every figure here is smaller than the true one"). The always-on shape descriptors need no such rule, because they are computed on the ChEMBL parent compound and refused when there is no single
parent. And Geometry Analysis can be set to measure another geometry than the one it was handed (the lowest of several it generates, or a copy it relaxed) or to scale its radii, which its record says: a number
measured that way is not the conformer's, so it is refused naming the setting, and a result whose record does not say is refused as unknown. Both come from the result's own provenance, so Results, the project table
and the assistant read one rule.

**AN INPUT IS READ FROM THE MOLECULE'S CURRENT RESULTS ONLY.** A result computed on an earlier structure, or one the application has superseded, is not
used, and the refusal says so. A refused, failed or absent input refuses the score, naming the input and why. **Never a zero, and never a skipped term:**
dropping a term from a sum silently changes what the sum is. The classification is the assistant's (`turn_snapshot.classify_results`), so there is one
rule for what "current" means.

**A DEFAULT STANDS IN FOR AN INPUT NOBODY CALCULATED, AND FOR NOTHING ELSE** (the second `on_missing` policy, `score_definition`). When the definition declares a default for an input
and that input was NEVER CALCULATED for this molecule, the default is read in its place and the input's state is `DEFAULT`, which no surface can mistake for `READ`. An input that was
calculated and refused, failed, belongs to an earlier structure, carries another unit or is ambiguous still refuses the score: each of those is an answer about this molecule, and a
default would hide it. **A score worked out from defaults alone is refused**, because that number says nothing about the molecule. The score's value then carries `defaulted`, the
inputs it used one for, and every surface that shows the number shows that too.

**TWO CURRENT RESULTS THAT DISAGREE ARE NOT GUESSED BETWEEN.** The same output computed with two sets of settings (two pH values, say) can both be current;
if they give different numbers the score cannot know which was meant, and it refuses. If they agree it reads either.

Pure: no Qt, no chemistry.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from openchem.domain.calculator import GEOMETRY
from openchem.domain.conformer import QUANTUM_OPTIMIZED_METHODS
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.report import ReportResult
from openchem.domain.score_constants import constant_values
from openchem.domain.score_definition import ON_MISSING_DEFAULT, ScoreDefinition, check_computation
from openchem.domain.score_formula import FormulaError, Refusal, evaluate, render
from openchem.domain.score_outputs import AS_STORED_UNSCALED, READ_FROM, ApprovedOutput, accept_value, approved_output
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
    #: Nothing was calculated and the definition declares a default for this input, which is what `value` is. It yields a number, and is never a `READ`.
    DEFAULT = "default"
    #: A current result of a geometry output that the application declines to read: the structure it was measured on is several fragments, the calculator measured something other than the stored conformer
    #: (or with scaled radii), or its record does not say which. The note names which.
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class InputEvidence:
    """One input, as it was read."""

    name: str
    output_id: str
    state: InputState
    #: The number, when `state` is `READ` or `DEFAULT`.
    value: float | None = None
    #: The unit the output is approved in (the language of `score_units`), and the string the result carried.
    unit: str = ""
    carried_as: str = ""
    #: The stored result it came from, when one was read.
    result_id: str = ""
    parameters_key: str = ""
    #: Why not, when it was not read.
    note: str = ""
    #: The calculation input the output is read from (`drawing` or `geometry`), and, for a geometry result that was read, which conformer it was measured on (`geometry_text`).
    calculation_input: str = READ_FROM
    geometry: str = ""


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

    @property
    def defaulted(self) -> tuple[InputEvidence, ...]:
        """The inputs this value used a default for, in the order the definition lists them. Empty for a value worked out from results alone."""
        return tuple(item for item in self.inputs if item.state is InputState.DEFAULT)


@dataclass(frozen=True)
class OutputRead:
    """One approved output, read from a molecule's classified results."""

    state: InputState
    value: float | None = None
    carried_as: str = ""
    result_id: str = ""
    parameters_key: str = ""
    note: str = ""
    #: Which conformer a geometry result was measured on, in words; empty for the drawing.
    geometry: str = ""


#: The keys `chem.calculation_input.geometry_provenance` merges into a result's provenance (prefix `INPUT_PREFIX`), written as the literals they are because this module reads no chemistry layer;
#: `tests/test_score_geometry.py` holds both to each other.
_GEOMETRY_KEYS = ("input_conformer_id", "input_conformer_index", "input_conformer_energy", "input_force_field")

#: What made the conformer a result was measured on (`ConformerModel.method`), and the level of theory of a quantum-optimised one: `chem.calculation_input.CONFORMER_METHOD_KEY` and `LEVEL_OF_THEORY_KEY`.
CONFORMER_METHOD_KEY = "input_conformer_method"
LEVEL_OF_THEORY_KEY = "input_level_of_theory"


def geometry_text(parameters: Mapping[str, object] | None) -> str:
    """The conformer a result was measured on, from the provenance a geometry run records (id, position, energy, force field), or empty when it names none.

    `conformer 3 (id 1a2b3c4d, MMFF94 energy -12.35 kcal/mol)`; an ORCA-optimised conformer has no force-field energy and says its level of theory instead (`ORCA-optimised at B3LYP def2-SVP`, or only
    `ORCA-optimised` when the level was not recorded). The position is the one it had when the result was made, which is the conformer's own as long as the result is current (its fingerprint is the conformer's).
    """
    if not parameters:
        return ""
    conformer_id = parameters.get("input_conformer_id")
    if not conformer_id:
        return ""
    index = parameters.get("input_conformer_index")
    energy = parameters.get("input_conformer_energy")
    field = parameters.get("input_force_field")
    where = f"conformer {index + 1}" if isinstance(index, int) and not isinstance(index, bool) else "a conformer"
    details = [f"id {str(conformer_id)[:8]}"]
    if isinstance(energy, (int, float)) and not isinstance(energy, bool) and math.isfinite(energy):
        details.append(f"{field + ' ' if field else 'force-field '}energy {energy:.2f} kcal/mol")
    if parameters.get(CONFORMER_METHOD_KEY) in QUANTUM_OPTIMIZED_METHODS:
        level = parameters.get(LEVEL_OF_THEORY_KEY)
        details.append(f"ORCA-optimised at {level}" if isinstance(level, str) and level else "ORCA-optimised")
    return f"{where} ({', '.join(details)})"


#: The provenance key `chem.calculation_input.geometry_provenance` writes (domain cannot import it): how many separate pieces the conformer a result was measured on is made of.
FRAGMENTS_KEY = "input_fragments"

#: What a refusal for a result whose record does not say names, so a person knows the cure.
_RERUN = "run it again"


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def not_applicable_reason(output: ApprovedOutput, parameters: Mapping[str, object] | None) -> str:
    """Why a number of a GEOMETRY output may not be read from a result recorded with these provenance `parameters`, or `""` when it may.

    Three questions, in this order, each answered from what the result says about itself and never guessed:

    1. **Is the structure one compound?** Only for an output the producer measures on the whole structure (`whole_structure`). `input_fragments` (`geometry_provenance`) counts the separate pieces of the conformer.
       More than one is refused, and a result with no count (one an earlier build made) is refused as unknown, because reading it as one piece would let a salt through.
    2. **Did the calculator measure the stored conformer?** Only for an output with `measured_as`: Geometry Analysis records the fingerprint of the geometry it was handed (`input_geometry`) and of the one it
       measured (`measured_geometry`), and they differ when it chose a conformer of its own or relaxed a copy.
    3. **Were the radii unscaled?** Only for `AS_STORED_UNSCALED`: the six projection numbers rescale with `radius_scale`.

    A drawing output has none of these questions.
    """
    if output.input != GEOMETRY:
        return ""
    values = parameters or {}
    if output.whole_structure:
        fragments = values.get(FRAGMENTS_KEY)
        if not _is_count(fragments):
            return f"its record does not say how many separate pieces the structure it was measured on is made of (an earlier build made it), so it cannot be told from a salt: {_RERUN}"
        if fragments > 1:
            return (
                f"it was measured on the whole structure, which is {fragments} separate fragments (a salt, a hydrate, a complex), and where one fragment sits beside another in 3D is arbitrary, "
                "so a shape number of it says nothing about the compound: score the parent structure"
            )
    if output.needs_quantum_geometry:
        made_by = values.get(CONFORMER_METHOD_KEY)
        if not isinstance(made_by, str):
            return f"its record does not say what made the geometry it was measured on, so it cannot be told from a force-field conformer's: {_RERUN}"
        if made_by not in QUANTUM_OPTIMIZED_METHODS:
            return (
                "it was measured on a conformer that ORCA did not optimise, whose bond lengths are the force field's own and not a measurement of the rings: "
                f"optimise the molecule in ORCA, then {_RERUN}"
            )
    if not output.measured_as:
        return ""
    measured, handed = values.get("measured_geometry"), values.get("input_geometry")
    if not isinstance(measured, str) or not isinstance(handed, str):
        return f"its record does not say which geometry the calculator measured, so it cannot be told from the stored conformer: {_RERUN} with its default settings"
    if measured != handed:
        how = (
            "a copy of the conformer that it relaxed with MMFF94 first" if values.get("optimise_projection") is True
            else "a conformer it generated itself (the lowest of several)" if values.get("conformer_policy") == "always"
            else "another geometry than the stored conformer"
        )
        return f"it was measured on {how}, and a score reads only a number measured on the conformer every calculation uses, as it is: {_RERUN} with its default settings"
    if output.measured_as == AS_STORED_UNSCALED:
        scale = values.get("radius_scale")
        if isinstance(scale, bool) or not isinstance(scale, (int, float)):
            return f"its record does not say how the van der Waals radii were scaled: {_RERUN} with its default settings"
        if float(scale) != 1.0:
            return f"its projections used van der Waals radii scaled by {float(scale):g}, and a score reads only unscaled ones: {_RERUN} with its default settings"
    return ""


def _parameters_of(result: object) -> Mapping[str, object] | None:
    """The provenance parameters a stored result records, or None when it records none."""
    return getattr(getattr(result, "provenance", None), "parameters", None)


def _records_of(output: ApprovedOutput, entries: Iterable[ResultEntry]) -> list[ResultEntry]:
    """The stored results made by whatever produces `output`, of the input the entry says it is read from, in any state."""
    kind, _, rest = output.output_id.partition(":")
    found = []
    for entry in entries:
        identity = entry.stored.identity
        if identity.calculation_input != output.input:
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


#: What a geometry output says when the molecule has no conformer to measure.
NEEDS_A_CONFORMER = "it needs a conformer: this molecule has none, so there is no geometry to measure (generate conformers first)"

#: What an output that reads bond lengths says when the molecule has no conformer: the conformer must also be one ORCA optimised.
NEEDS_AN_ORCA_GEOMETRY = "it needs a conformer optimised in ORCA: this molecule has no conformer yet (generate conformers, optimise one in ORCA, then run the calculator)"

#: What a geometry output says when it was measured, but not on the conformer every calculation uses now.
EARLIER_GEOMETRY = "calculated for an earlier geometry of this molecule: the conformer every calculation uses has changed since, and a number of another conformer is never read in its place"


def read_output(output_id: str, entries: Iterable[ResultEntry], conformers: int | None = None) -> OutputRead:
    """The number an approved output has for a molecule whose results are `entries` (`turn_snapshot.classify_results`), or why it has none.

    `conformers` is how many conformers the molecule holds, when the caller knows (None: it does not). Only a geometry output asks: with none stored and none to measure, the reason is that it
    needs a conformer, which is a different sentence from "not calculated yet".
    """
    output = approved_output(output_id)
    if output is None:
        return OutputRead(InputState.NOT_APPROVED, note="it is no longer an approved output")
    on_geometry = output.input == GEOMETRY
    records = _records_of(output, entries)
    if not records:
        if on_geometry and conformers == 0:
            return OutputRead(InputState.NOT_RUN, note=NEEDS_AN_ORCA_GEOMETRY if output.needs_quantum_geometry else NEEDS_A_CONFORMER)
        note = "it has not been calculated on this molecule's conformer yet" if on_geometry and conformers else "it has not been calculated for this molecule"
        if on_geometry and conformers and output.needs_quantum_geometry:
            note += ", and it reads only a conformer that ORCA optimised (a force-field conformer is declined)"
        return OutputRead(InputState.NOT_RUN, note=note)
    current = [entry for entry in records if entry.freshness is Freshness.CURRENT]
    if not current:
        # No shape descriptor carries a method version, so a historical geometry result is one whose fingerprint is not the conformer's now. An unverifiable one (no fingerprint to compare) says its own reason.
        if on_geometry and all(entry.freshness is Freshness.HISTORICAL for entry in records):
            return OutputRead(InputState.NOT_CURRENT, note=EARLIER_GEOMETRY)
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
        recorded = _parameters_of(entry.stored.result)
        declined = not_applicable_reason(output, recorded)
        if declined:
            reads.append(OutputRead(InputState.NOT_APPLICABLE, result_id=entry.result_id, parameters_key=identity.parameters_key, note=declined))
            continue
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
        where = geometry_text(recorded) if on_geometry else ""
        reads.append(OutputRead(InputState.READ, number, carried, entry.result_id, identity.parameters_key, geometry=where))
    good = [read for read in reads if read.state is InputState.READ]
    if not good:
        return reads[0]
    if len({read.value for read in good}) > 1:
        return OutputRead(
            InputState.AMBIGUOUS,
            note=f"{len(good)} current results, computed with different settings, give different numbers; the score cannot tell which was meant",
        )
    return good[0]


def _with_default(definition: ScoreDefinition, item: InputEvidence) -> InputEvidence:
    """`item` as the second policy reads it: an input that was never calculated, for which the definition declares a default, is that default. Anything else is `item`."""
    if definition.on_missing != ON_MISSING_DEFAULT or item.state is not InputState.NOT_RUN:
        return item
    declared = dict(definition.defaults).get(item.name)
    if declared is None:
        return item
    output = approved_output(item.output_id)
    return InputEvidence(
        name=item.name, output_id=item.output_id, state=InputState.DEFAULT, value=float(declared), unit=item.unit,
        carried_as=output.carried_as if output else "", note=f"not calculated for this molecule; this score's default of {declared:.6g} is used in its place",
    )


def _evidence(name: str, output_id: str, read: OutputRead) -> InputEvidence:
    output = approved_output(output_id)
    return InputEvidence(
        name=name, output_id=output_id, state=read.state, value=read.value, unit=output.unit if output else "",
        carried_as=read.carried_as, result_id=read.result_id, parameters_key=read.parameters_key, note=read.note,
        calculation_input=output.input if output else READ_FROM, geometry=read.geometry,
    )


#: A definition's parsed formula, kept: a project table asks for the same few formulas once per row, and a parse is not free. A definition that does not check raises, and
#: an exception is never cached, so it is checked afresh each time and says the same thing.
_computation = lru_cache(maxsize=512)(check_computation)


def evaluate_score(definition: ScoreDefinition, entries: Sequence[ResultEntry], conformers: int | None = None) -> ScoreValue:
    """The value of `definition` for a molecule whose results are `entries` (`turn_snapshot.classify_results`), or the reason there is none.

    `conformers` is how many conformers the molecule holds, when the caller knows, so a score over a shape descriptor can say "it needs a conformer" and not only "not calculated".
    """
    return evaluate_score_with(definition, lambda output_id: read_output(output_id, entries, conformers))


def evaluate_score_with(definition: ScoreDefinition, read: Callable[[str], OutputRead]) -> ScoreValue:
    """The value of `definition` when `read(output_id)` says what each approved output has, or the reason there is none.

    `read` is the only thing that differs between the places a score is shown: the Results reader reads a molecule's stored results (`read_output`), a project table
    reads its own cells (`score_table.read_cell_output`). Everything after the reading is one rule.

    Three things can refuse, in order: the definition (it no longer checks: an output left the approved table, say), an input (it cannot be read), and
    the evaluation (a division by zero, a domain error, an overflow, any non-finite step). None of them returns a number.
    """
    try:
        formula = _computation(definition)
    except FormulaError as exc:
        return ScoreValue(definition, ScoreStatus.REFUSED, None, definition.result_unit, f"the definition no longer checks: {exc.message}", (), "")
    shown = render(formula.tree)
    evidence = tuple(_with_default(definition, _evidence(name, output_id, read(output_id))) for name, output_id in definition.inputs)
    unread = [item for item in evidence if item.state not in (InputState.READ, InputState.DEFAULT)]
    if unread:
        reason = "; ".join(f"{item.name} ({item.output_id}): {item.note}" for item in unread)
        return ScoreValue(definition, ScoreStatus.REFUSED, None, definition.result_unit, reason, evidence, shown)
    if not any(item.state is InputState.READ for item in evidence):
        # Every input would be a default: a number that says nothing about this molecule, so it is not given.
        reason = "no input was calculated for this molecule, so the score would be worked out from defaults alone: " + "; ".join(f"{item.name} ({item.output_id})" for item in evidence)
        return ScoreValue(definition, ScoreStatus.REFUSED, None, definition.result_unit, reason, evidence, shown)
    values: Mapping[str, float] = {**{item.name: float(item.value) for item in evidence}, **constant_values(definition.constants)}
    try:
        number = evaluate(formula, values)
    except Refusal as exc:
        return ScoreValue(definition, ScoreStatus.REFUSED, None, definition.result_unit, str(exc), evidence, shown)
    return ScoreValue(definition, ScoreStatus.VALUE, number, definition.result_unit, "", evidence, shown)
