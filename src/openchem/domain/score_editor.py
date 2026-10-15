"""What the definition dialog holds while a person types, and what it says about it (`docs/DERIVED_SCORES_DESIGN.md` section 11, slice 3d).

The dialog knows no rules. It holds a `Draft` (the strings in its fields), asks `check_draft` what is wrong with it after every keystroke, and shows the answer:
one sentence, the field it belongs to, the place in the formula it points at when there is one, and, when the draft checks, the unit the formula works out to. The
rules themselves are `score_definition.check_score_definition`'s, so the dialog cannot disagree with the loader or the service.

**A DRAFT IS STRINGS, NOT A DEFINITION.** A constant's value is whatever has been typed so far (`1.4` is a number, `1.` is a typo, an empty box is nothing yet), and
turning it into a number is part of checking it. Nothing about a draft is stored until the person presses Save.

**THE OUTPUT CHOICES ARE THE APPROVED TABLE, SAID IN WORDS.** A person picks an input by what it measures, with its unit beside it, and never types an output id.

Pure: no Qt, no chemistry.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from openchem.domain.score_constants import Constant
from openchem.domain.score_definition import SCHEMA_VERSION, ScoreDefinition, check_score_definition
from openchem.domain.score_formula import FUNCTIONS, FormulaError, Problem, infer_unit
from openchem.domain.score_outputs import APPROVED, ENDPOINTS, check_inputs, output_title

#: The id a draft has before it is saved. Never stored: the service makes the real one from the label.
DRAFT_ID = "user.draft"

#: Which field of the dialog a problem belongs to, for the problems that do not name one themselves.
_FIELD_OF_PROBLEM = {
    Problem.SYNTAX: "formula",
    Problem.LIMIT: "formula",
    Problem.NAME: "formula",
    Problem.FUNCTION: "formula",
    Problem.EXPONENT: "formula",
    Problem.INPUTS: "inputs",
    Problem.OUTPUT: "inputs",
    Problem.CONSENSUS: "inputs",
    Problem.CONSTANT: "constants",
    Problem.UNIT: "unit",
    Problem.DEFINITION: "label",
}

#: What `check_draft` says when everything checks, before the unit.
OK = "The formula checks"

#: A constant's value as it may be typed: the formula grammar's own number (`digits`, an optional `.digits`, an optional `e[+-]digits`: `.5` and `5.` are errors, not
#: guessed at, so the same spelling is a number in the box and in the formula), with the sign a constant may have. Not `nan`, not `inf`, not `1_000`, and not
#: Arabic-Indic digits, all of which `float` would take (ASCII only, as the formula grammar is).
_NUMBER = re.compile(r"[-+]?\d+(\.\d+)?([eE][-+]?\d+)?", re.ASCII)

#: The words of the plain-language reminder under the label. Stated here so the dialog and the tests read one sentence.
SHOWN_AS = "Shown everywhere as"


@dataclass(frozen=True)
class InputRow:
    """One input as typed: the name the formula uses, and the approved output it reads."""

    name: str = ""
    output_id: str = ""


@dataclass(frozen=True)
class ConstantRow:
    """One named constant as typed. The value is text until it is checked."""

    name: str = ""
    value: str = ""
    unit: str = ""


@dataclass(frozen=True)
class Draft:
    """The fields of the dialog, as strings."""

    label: str = ""
    formula: str = ""
    result_unit: str = "1"
    inputs: tuple[InputRow, ...] = ()
    constants: tuple[ConstantRow, ...] = ()
    owner: str = ""
    note: str = ""

    @classmethod
    def from_definition(cls, definition: ScoreDefinition) -> Draft:
        return cls(
            label=definition.label,
            formula=definition.formula,
            result_unit=definition.result_unit,
            inputs=tuple(InputRow(name, output_id) for name, output_id in definition.inputs),
            constants=tuple(ConstantRow(c.name, f"{c.value:.12g}", c.unit) for c in definition.constants),
            owner=definition.owner,
            note=definition.note,
        )

    def to_definition(self, *, score_id: str = DRAFT_ID, created: str = "") -> ScoreDefinition:
        """The definition this draft says, or a `FormulaError` (`Problem.CONSTANT`) for a constant whose value is not a number yet."""
        constants = []
        for row in self.constants:
            text = row.value.strip()
            if not _NUMBER.fullmatch(text):
                raise FormulaError(Problem.CONSTANT, f"constant {row.name!r}: the value {row.value!r} is not a plain number (digits, then a point with digits after it, then an exponent, each optional after the digits)")
            value = float(text)
            if not math.isfinite(value):
                raise FormulaError(Problem.CONSTANT, f"constant {row.name!r}: the value {row.value!r} is too large to use")
            constants.append(Constant(row.name.strip(), value, row.unit.strip()))
        return ScoreDefinition(
            score_id=score_id,
            label=self.label.strip(),
            formula=self.formula,
            result_unit=self.result_unit.strip(),
            inputs=tuple((row.name.strip(), row.output_id) for row in self.inputs),
            constants=tuple(constants),
            schema_version=SCHEMA_VERSION,
            owner=self.owner.strip(),
            created=created,
            note=self.note.strip(),
        )

    @property
    def is_blank(self) -> bool:
        return not (self.label.strip() or self.formula.strip() or self.inputs or self.constants or self.note.strip())


@dataclass(frozen=True)
class DraftCheck:
    """What is wrong with a draft, or that nothing is."""

    ok: bool
    #: One line for the dialog.
    message: str
    #: `Problem` value, or "" when `ok`.
    problem: str = ""
    #: The dialog's field the message belongs to: "label", "formula", "inputs", "constants", "unit" or "" (nothing wrong, or not placeable).
    where: str = ""
    #: A 0-based character index into the formula, when the problem has one.
    position: int | None = None
    #: The unit the formula works out to, in the language of `score_units`, when that could be worked out (also when it is not the declared one).
    worked_out: str = ""


def _worked_out_unit(definition: ScoreDefinition) -> str:
    """The unit the formula works out to, or "" when the inputs, the constants or the formula do not check far enough to say."""
    from openchem.domain.score_formula import parse_formula

    try:
        units = check_inputs(definition.inputs, definition.constants)
        formula = parse_formula(definition.formula, list(units))
        return str(infer_unit(formula.tree, units))
    except FormulaError:
        return ""


def check_draft(draft: Draft, *, reserved_names: Iterable[str] = ()) -> DraftCheck:
    """Everything that can be said about `draft` without evaluating it: the label, the inputs and constants, the formula, and the unit.

    It reports the FIRST thing wrong, in the order a person fills the form in: the label, then the inputs, the constants, the formula and the unit. Whether
    it is checked against a molecule is `ScoreService.preview`'s, not this.
    """
    if draft.is_blank:
        return DraftCheck(False, "Give the score a name, choose what it reads, and write the formula.")
    try:
        definition = draft.to_definition()
    except FormulaError as exc:
        return DraftCheck(False, exc.message, exc.problem.value, "constants")
    try:
        check_score_definition(definition, reserved_names)
    except FormulaError as exc:
        where = exc.field or _FIELD_OF_PROBLEM.get(exc.problem, "")
        if exc.problem is Problem.UNIT and exc.position is not None:
            # A unit problem inside the formula (adding an area to a mass, a threshold in the wrong unit) points at a place in it; only the declared unit, which
            # has no place in the formula, belongs to the unit field.
            where = "formula"
        return DraftCheck(False, exc.message, exc.problem.value, where, exc.position, _worked_out_unit(definition))
    worked = _worked_out_unit(definition) or definition.result_unit
    return DraftCheck(True, f"{OK}: it works out to {worked}.", worked_out=worked)


# --- pointing at a place in the formula ----------------------------------------------------------------------------------------------------


def pointer_lines(formula: str, position: int, *, width: int = 60) -> str:
    """Two lines for a monospaced label: the formula, or the stretch of it around `position` when it is longer than `width`, and under it a caret at `position`.

    It repeats the formula rather than drawing a caret under the edit, because the edit's own padding and font are the style's and a caret under it is a few pixels
    off; drawn from the same text in the same font, the caret is under the character by construction. Whitespace other than a space is shown as a space (one column
    each), so a tab or a newline in a stored formula cannot shift it.
    """
    flat = "".join(" " if character.isspace() else character for character in formula)
    position = max(0, min(position, len(flat)))
    start = max(0, position - width // 2)
    end = min(len(flat), start + width)
    start = max(0, end - width)
    lead = "..." if start > 0 else ""
    tail = "..." if end < len(flat) else ""
    return f"{lead}{flat[start:end]}{tail}\n{' ' * (len(lead) + position - start)}^"


# --- choosing an input --------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class OutputChoice:
    """One approved output, in words."""

    output_id: str
    #: What the picker shows: what it is, its unit, and what it measures.
    text: str
    #: The name an input of it is offered by default, valid as an input name.
    suggested_name: str
    unit: str
    endpoint: str


def _slug(text: str) -> str:
    # NFKD first, so a subscript two is a two: "CO₂ basis" and "CO basis" must not become the same suggested name.
    folded = unicodedata.normalize("NFKD", text).casefold()
    slug = re.sub(r"[^a-z0-9]+", "_", folded).strip("_")
    if not slug or not slug[0].isalpha():
        slug = "x_" + slug if slug else "x"
    return slug[:30].rstrip("_") or "x"


def output_choices() -> tuple[OutputChoice, ...]:
    """The approved table as a picker's entries, sorted by what they are called."""
    choices = []
    for entry in APPROVED:
        title = output_title(entry.output_id)
        # A title that already says its unit ("Predicted intrinsic solubility (mol/L)") is not given it twice.
        unit = f" ({entry.unit})" if entry.unit != "1" and f"({entry.unit})" not in title else ""
        choices.append(
            OutputChoice(
                output_id=entry.output_id,
                text=f"{title}{unit}: {ENDPOINTS[entry.endpoint]}",
                suggested_name=_slug(title),
                unit=entry.unit,
                endpoint=entry.endpoint,
            )
        )
    return tuple(sorted(choices, key=lambda c: c.text.casefold()))


def suggest_name(output_id: str, taken: Iterable[str]) -> str:
    """A name for a new input reading `output_id`: valid as an input name, not a function, and not in `taken`."""
    taken_names = set(taken) | set(FUNCTIONS)
    base = _slug(output_title(output_id))
    candidate, number = base, 2
    while candidate in taken_names:
        candidate = f"{base}_{number}"
        number += 1
    return candidate
