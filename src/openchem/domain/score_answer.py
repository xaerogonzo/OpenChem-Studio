"""A user-defined score, as the Results reader holds it (`docs/DERIVED_SCORES_DESIGN.md` sections 5 and 8; slice 3b).

**A PROJECTION OF THE DEFINITION AND THE MOLECULE'S CURRENT RESULTS, NEVER STORED.** The definitions are kept in `ScoreDefinitionStore`; a value is computed when
the reader asks (`score_value.evaluate_score`), so the reader is handed these entries built at the moment it refreshes, the way it is handed the descriptor aggregate
and the kept recipe answers. A score is not a registered calculator, so it has no `calculator_id`, is not in the calculator reference or the launcher, and never
enters a cache key.

**IT IS ONE FACT, AND IT SAYS WHAT IT IS.** Its label is `<label> (user-defined, unvalidated)`, its basis is HEURISTIC, its evidence is the formula and every input
(name, value, unit, the output and the stored result it was read from) and the definition's digest, and its one fixed limitation is that a person wrote the
formula and nothing has checked it against measurements. Nothing here calls a score a prediction of anything. `Provenance` says `created_by="user"`,
`method="derived_score:<format>"` and carries `validation="user_defined_unvalidated"`, the formula and the digest.

**A SCORE WITH NO NUMBER IS A REFUSAL, IN THE APPLICATION'S OWN VOCABULARY.** It is a failed report with the `NEEDS_INPUT` kind, so it counts and reads as every other
refusal does, and the reason names each input that could not be read and why. The inputs and the formula are still shown, because "what would it have read" is
the question a person asks next.

**IT IS NEVER STALE.** It is evaluated against the structure as it is now, so it is stamped with the current structure version; if the structure was edited the
inputs are no longer current and the score refuses, which says so.

Pure: no Qt, no chemistry.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from openchem.domain.common import CacheState, Provenance
from openchem.domain.refusal_kinds import RefusalKind, refusal_parameters
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.domain.score_definition import VALIDATION
from openchem.domain.score_outputs import READ_FROM
from openchem.domain.score_value import InputEvidence, InputState, ScoreStatus, ScoreValue

#: The one limitation every score carries, in these words, because it is what a person reading the number most needs to be told.
LIMITATION = "A formula a person wrote. Nothing has checked it against measurements."

#: What a number that used a default says, beside the limitation every score carries. `{names}` are the inputs it used one for.
DEFAULTED = "A default stood in for an input nobody calculated for this molecule ({names}); it is a number the definition declares, not the result of a calculation."

#: The refusal code of a score with no number; classified, so the census-style guards do not report it as a fault.
REFUSAL_CODE = "SCORE_NO_VALUE"

#: What the one fact says when there is no number.
NO_VALUE = "no value"

#: Digits shown for a score's value. The number itself is kept whole in `Fact.value`.
SIGNIFICANT_DIGITS = 4


@dataclass(frozen=True, kw_only=True)
class ScoreAnswer(ReportResult):
    """A score read for one molecule, as a report. Every `ReportResult` rule applies to it (ordering, search, copy, export).

    Never encoded: it is built to be read and discarded, and the project file holds the definition it came from.
    """

    #: The definition it was made from.
    score_id: str = ""
    #: Identifies the computation (`ScoreDefinition.digest`), so two reads of one definition can be told to agree.
    digest: str = ""


def report_id_of(score_id: str) -> str:
    """The id an answer is filed under. The prefix keeps it from ever equalling a calculator's id."""
    return f"score:{score_id}"


def _number(value: float) -> str:
    return f"{value:.{SIGNIFICANT_DIGITS}g}"


def _input_line(item: InputEvidence) -> str:
    """One input that was read, or that a default stood in for: only a score with a value has evidence lines, and it has a value only when every input is one of the two."""
    unit = f" {item.carried_as}" if item.carried_as else ""
    if item.state is InputState.DEFAULT:
        return f"{item.name} = {item.value:.6g}{unit}   [A DEFAULT of this definition: {item.output_id} was not calculated for this molecule, so this is not a result]"
    # Which structure is said because the same descriptor can have a number of the drawing and of a conformer (the always-on descriptors were stored for both, and 7 of the 17
    # approved ones differed between the two), and a person comparing the reader beside it should know which this score read.
    return f"{item.name} = {item.value:.6g}{unit}   [{item.output_id}; read from the stored result {item.result_id}, computed on {_computed_on(item)}]"


def _computed_on(item: InputEvidence) -> str:
    """The structure an input was measured on: the drawing, or the conformer (named when the result recorded which)."""
    if item.calculation_input != READ_FROM:
        return item.geometry or "the conformer every calculation uses (which one was not recorded)"
    return "the drawing"


def _defaulted_said(value: ScoreValue) -> str:
    return DEFAULTED.format(names=", ".join(item.name for item in value.defaulted))


def _evidence(value: ScoreValue) -> tuple[str, ...]:
    definition = value.definition
    lines = [f"Formula: {value.formula or definition.formula}"]
    if value.defaulted:
        lines.append(_defaulted_said(value))
    lines.extend(_input_line(item) for item in value.inputs)
    lines.extend(f"{constant.name} = {constant.value:.6g} {constant.unit}   [a constant of this definition]" for constant in definition.constants)
    lines.append(f"Declared unit: {definition.result_unit}.   Definition {definition.digest}.")
    return tuple(lines)


def _provenance(value: ScoreValue, *, refused: bool) -> Provenance:
    definition = value.definition
    parameters = {
        "validation": VALIDATION,
        "formula": definition.formula,
        "schema_version": definition.schema_version,
        "digest": definition.digest,
        "score_id": definition.score_id,
    }
    if value.defaulted and not refused:
        # Only a number used a default: a refusal has none, though its evidence still says which inputs a default WOULD have stood in for.
        parameters["defaulted"] = [item.name for item in value.defaulted]
    if refused:
        parameters.update(refusal_parameters(REFUSAL_CODE, RefusalKind.NEEDS_INPUT))
    return Provenance(created_by="user", method=f"derived_score:{definition.schema_version}", parameters=parameters)


def _answer(value: ScoreValue, viewing: str, structure_version: int) -> ScoreAnswer:
    definition = value.definition
    common = dict(
        molecule_uuid=viewing, report_id=report_id_of(definition.score_id), name=definition.display_label, category="derived",
        structure_version=structure_version, score_id=definition.score_id, digest=definition.digest,
    )
    if value.status is ScoreStatus.VALUE:
        evidence = _evidence(value)
        shown = _number(value.value)
        limitations = (LIMITATION,)
        if value.defaulted:
            shown = f"{shown} (default used for {', '.join(item.name for item in value.defaulted)})"
            limitations = (LIMITATION, _defaulted_said(value))
        fact = Fact(
            category=FactCategory.DERIVED, label=definition.display_label, value=value.value, display_value=shown,
            source="derived score", basis=Basis.HEURISTIC, evidence=evidence, limitations=limitations,
            units="" if definition.result_unit == "1" else definition.result_unit,
        )
        return ScoreAnswer(**common, facts=(fact,), limitations=limitations, provenance=_provenance(value, refused=False))
    # No fact means no value row to hover, so the footer is where the formula is said, as one sentence: the reader joins the limitations with spaces, and the
    # per-input lines that belong on a value's tooltip would read as one run-on paragraph there. The reason (the line above) already names each unread input.
    described = f"Formula {value.formula or definition.formula} (declared unit {definition.result_unit}; definition {definition.digest})."
    return ScoreAnswer(
        **common, facts=(), cache_state=CacheState.FAILED, error=value.reason, error_summary=f"{NO_VALUE}: an input cannot be read",
        limitations=(described, LIMITATION), provenance=_provenance(value, refused=True),
    )


def project_score_answers(values: Sequence[ScoreValue], *, viewing: str, structure_version: int) -> tuple[ScoreAnswer, ...]:
    """The reader entries for `values`, in the order the definitions were made, re-stamped with the molecule being looked at."""
    return tuple(_answer(value, viewing, structure_version) for value in values)
