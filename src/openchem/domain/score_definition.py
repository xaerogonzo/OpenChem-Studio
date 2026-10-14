"""A derived score's definition: the data a person authors, and the rules it must meet (`docs/DERIVED_SCORES_DESIGN.md` sections 2, 5 and 8).

A definition is DATA, owned by a project: a label, a formula over named inputs (each bound to an approved output, `score_outputs`), named constants
with units (`score_constants`), and the unit the formula is declared to work out to. It is not a calculator and is not in the registry; its value
is a function of the definition and the molecule's current results, computed when read and never stored (`score_value`).

**THE LABEL IS THE PERSON'S, AND THE SUFFIX IS NOT.** Every surface shows `<label> (user-defined, unvalidated)` (`display_label`), and the suffix is
not part of the stored text, so it cannot be edited away. The label may not be close to the name of any calculator or approved output, because a
number the person defined must not read as one the application provides; the comparison is made against names read from the registry, so it cannot rot
as a hand-kept list of published names would. It cannot know a published score the application lacks, and for those the suffix and the provenance carry
the burden.

**A STORED DEFINITION IS NEVER SILENTLY DROPPED.** One written by a newer build, or damaged, is kept as it was read (`ScoreDefinitionStore`), because a
formula is authored work: discarding it with a warning on the next save would delete it.

Pure: no Qt, no chemistry.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from openchem.domain.score_constants import Constant
from openchem.domain.score_formula import (
    Formula,
    FormulaError,
    Problem,
    check_definition,
)
from openchem.domain.score_outputs import APPROVED, check_inputs
from openchem.domain.score_units import UnitError, parse_unit

#: The version of the definition format. A build refuses (and carries through) a definition with a higher one.
SCHEMA_VERSION = 1

#: Shown after every score's label on every surface. Not part of the stored label, so it cannot be removed by editing it.
DISPLAY_SUFFIX = "(user-defined, unvalidated)"

#: What `Provenance.parameters["validation"]` says of a score's value, beside the formula and the digest.
VALIDATION = "user_defined_unvalidated"

#: Every score id starts with this, so it can never be taken for a registry calculator's id.
SCORE_ID_PREFIX = "user."

#: The only missing-value policy in this phase: an absent, refused or historical input refuses the score. A second one changes the meaning of the number
#: without changing its label, so it needs a reason in writing first.
ON_MISSING_REFUSE = "refuse"

#: The longest label, in characters.
MAX_LABEL = 80

#: The longest owner, in characters.
MAX_OWNER = 80

#: The longest note, in characters.
MAX_NOTE = 500

#: The most definitions one project may hold; the block lives in the project file.
MAX_DEFINITIONS = 100

#: The shortest normalised name that can collide with a label. A shorter one would block everything.
MIN_NAME_CHARACTERS = 3

#: The part of a score id after the prefix.
_SLUG = re.compile(r"[a-z][a-z0-9_]{0,39}")

#: `YYYY-MM-DD`, or empty.
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class DefinitionError(ValueError):
    """A stored definition that cannot be read as one. `reason` is for the person who opens the file."""


class NewerDefinition(DefinitionError):
    """Written by a build that knows a later format than this one: kept, not evaluated, never edited."""


class DamagedDefinition(DefinitionError):
    """Not a definition this format can describe: kept as it was read, so a person can mend the file."""


@dataclass(frozen=True)
class ScoreDefinition:
    """One user-defined score."""

    #: `user.<slug>`; immutable once made, so a label can change without losing the score's identity.
    score_id: str
    #: The person's text, shown as `<label> (user-defined, unvalidated)`.
    label: str
    #: The formula, in the grammar of `score_formula`.
    formula: str
    #: The unit the formula is declared to work out to, in the language of `score_units`. Checked, not trusted.
    result_unit: str
    #: `(name, output id)` in order: the name the formula uses, and the approved output it reads (`score_outputs.APPROVED`).
    inputs: tuple[tuple[str, str], ...]
    #: Named numbers with units (`score_constants`).
    constants: tuple[Constant, ...] = ()
    schema_version: int = SCHEMA_VERSION
    on_missing: str = ON_MISSING_REFUSE
    #: Who wrote it, free text.
    owner: str = ""
    #: `YYYY-MM-DD`, or empty.
    created: str = ""
    note: str = ""

    @property
    def display_label(self) -> str:
        """The label as every surface shows it."""
        return f"{self.label} {DISPLAY_SUFFIX}"

    @property
    def digest(self) -> str:
        """Identifies the computation: the format, the formula, the inputs and constants, and the units. Not the label, owner, note or date, which change
        nothing about the number. Sixteen hex digits of SHA-256 over a canonical encoding."""
        payload = {
            "schema_version": self.schema_version,
            "formula": self.formula,
            "result_unit": self.result_unit,
            "on_missing": self.on_missing,
            "inputs": [list(pair) for pair in self.inputs],
            "constants": [[c.name, float(c.value), c.unit] for c in self.constants],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("ascii")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_id": self.score_id,
            "label": self.label,
            "schema_version": self.schema_version,
            "formula": self.formula,
            "result_unit": self.result_unit,
            "inputs": [[name, output_id] for name, output_id in self.inputs],
            "constants": [{"name": c.name, "value": float(c.value), "unit": c.unit} for c in self.constants],
            "on_missing": self.on_missing,
            "owner": self.owner,
            "created": self.created,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: object) -> ScoreDefinition:
        """The definition `data` describes, or a `DefinitionError` saying why not.

        This reads the SHAPE (the right keys, the right types); whether the definition is acceptable (its formula, its units, its label) is
        `check_score_definition`'s, which runs when it is used. A definition that reads but no longer checks is kept and shown refused.
        """
        if not isinstance(data, Mapping):
            raise DamagedDefinition(f"a definition is an object, not {type(data).__name__}")
        version = data.get("schema_version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise DamagedDefinition(f"schema_version is {version!r}, not a whole number from 1")
        if version > SCHEMA_VERSION:
            raise NewerDefinition(f"written by a newer version of the application (definition format {version}; this one reads {SCHEMA_VERSION})")
        text = {}
        for key in ("score_id", "label", "formula", "result_unit", "on_missing"):
            value = data.get(key)
            if not isinstance(value, str):
                raise DamagedDefinition(f"{key} is missing or is not text")
            text[key] = value
        optional = {}
        for key in ("owner", "created", "note"):
            value = data.get(key, "")
            if not isinstance(value, str):
                raise DamagedDefinition(f"{key} is not text")
            optional[key] = value
        raw_inputs = data.get("inputs")
        if not isinstance(raw_inputs, list):
            raise DamagedDefinition("inputs is missing or is not a list")
        inputs = []
        for item in raw_inputs:
            if not (isinstance(item, (list, tuple)) and len(item) == 2 and all(isinstance(part, str) for part in item)):
                raise DamagedDefinition(f"an input is {item!r}, not [name, output id]")
            inputs.append((item[0], item[1]))
        raw_constants = data.get("constants", [])
        if not isinstance(raw_constants, list):
            raise DamagedDefinition("constants is not a list")
        constants = []
        for item in raw_constants:
            if not isinstance(item, Mapping):
                raise DamagedDefinition(f"a constant is {item!r}, not an object")
            name, value, unit = item.get("name"), item.get("value"), item.get("unit")
            if not isinstance(name, str) or not isinstance(unit, str):
                raise DamagedDefinition(f"a constant needs a text name and a text unit: {dict(item)!r}")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise DamagedDefinition(f"the constant {name!r} has the value {value!r}, which is not a finite number")
            constants.append(Constant(name, float(value), unit))
        return cls(
            score_id=text["score_id"], label=text["label"], formula=text["formula"], result_unit=text["result_unit"],
            inputs=tuple(inputs), constants=tuple(constants), schema_version=version, on_missing=text["on_missing"], **optional,
        )


# --- names ----------------------------------------------------------------------------------------------------------------


def normalise_name(text: str) -> str:
    """A name with case, accents, spaces and punctuation taken out, for comparing a label with the application's names."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed.casefold() if ch.isalnum())


def output_names() -> tuple[str, ...]:
    """The names the approved outputs go by: a descriptor's id, and a fact's label. Read from the table, so they cannot drift from it."""
    names = []
    for entry in APPROVED:
        kind, _, rest = entry.output_id.partition(":")
        names.append(rest if kind == "descriptor" else rest.partition(":")[2])
    return tuple(names)


def name_collision(label: str, reserved_names: Iterable[str]) -> str | None:
    """The first reserved name `label` is equal to, contains or is contained by (compared by `normalise_name`, three characters or more), or None."""
    wanted = normalise_name(label)
    for name in sorted(set(reserved_names)):
        other = normalise_name(name)
        if len(other) < MIN_NAME_CHARACTERS:
            continue
        if wanted == other or other in wanted or wanted in other:
            return name
    return None


def slugify(label: str) -> str:
    """The part of a score id a label makes: ASCII, lowercase, underscores, starting with a letter, at most 40 characters."""
    folded = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", folded).strip("_")
    if not slug:
        return "score"
    if not slug[0].isalpha():
        slug = "score_" + slug
    return slug[:40].rstrip("_")


def new_score_id(label: str, taken: Iterable[str]) -> str:
    """`user.<slug>` for `label`, with `_2`, `_3`... added until it is not in `taken`."""
    taken_ids = set(taken)
    slug = slugify(label)
    candidate = SCORE_ID_PREFIX + slug
    number = 2
    while candidate in taken_ids:
        suffix = f"_{number}"
        candidate = SCORE_ID_PREFIX + slug[: 40 - len(suffix)].rstrip("_") + suffix
        number += 1
    return candidate


# --- the rules a definition must meet -------------------------------------------------------------------------------------------


def _refuse(message: str) -> FormulaError:
    return FormulaError(Problem.DEFINITION, message)


def _check_fields(definition: ScoreDefinition, reserved_names: Iterable[str]) -> None:
    if not (definition.score_id.startswith(SCORE_ID_PREFIX) and _SLUG.fullmatch(definition.score_id[len(SCORE_ID_PREFIX):])):
        raise _refuse(f"the score id {definition.score_id!r} must be {SCORE_ID_PREFIX} then a lowercase name of at most 40 letters, digits and underscores")
    if definition.schema_version != SCHEMA_VERSION:
        raise _refuse(f"this build reads definition format {SCHEMA_VERSION}, not {definition.schema_version}")
    if definition.on_missing != ON_MISSING_REFUSE:
        raise _refuse(f"on_missing is {definition.on_missing!r}; the only policy is {ON_MISSING_REFUSE!r}: a missing input refuses the score")
    label = definition.label
    if not label.strip() or label != label.strip():
        raise _refuse("the label is empty or has spaces at either end")
    if len(label) > MAX_LABEL:
        raise _refuse(f"the label has at most {MAX_LABEL} characters, not {len(label)}")
    if not label.isprintable():
        raise _refuse("the label has a character that cannot be shown (a line break, a tab or a control character)")
    if not normalise_name(label):
        raise _refuse("the label needs at least one letter or digit")
    collision = name_collision(label, reserved_names)
    if collision is not None:
        raise _refuse(
            f"the label {label!r} is too close to {collision!r}, the name of a calculator or an output the application provides. "
            "A number a person defined must not read as one the application computes; choose a different name."
        )
    if len(definition.owner) > MAX_OWNER or not definition.owner.isprintable():
        raise _refuse(f"the owner has at most {MAX_OWNER} printable characters")
    if len(definition.note) > MAX_NOTE or not all(ch.isprintable() or ch == "\n" for ch in definition.note):
        raise _refuse(f"the note has at most {MAX_NOTE} characters")
    if definition.created and not _DATE.fullmatch(definition.created):
        raise _refuse(f"created is {definition.created!r}, not YYYY-MM-DD")
    if not definition.inputs:
        raise _refuse("a score reads at least one approved output")


def check_computation(definition: ScoreDefinition) -> Formula:
    """The parsed formula, or a `FormulaError`: the inputs (each an approved output, no two of one endpoint), the constants, the syntax, the names,
    and the unit the formula works out to against the declared one. What a number depends on, and nothing about how the score is presented.

    This is what runs when a score is READ. The label is not checked then: a calculator registered after the score was written can make its label
    look like a name, and that is a reason to ask the person to rename it, not to refuse its value.
    """
    units = check_inputs(definition.inputs, definition.constants)
    try:
        result_unit = parse_unit(definition.result_unit)
    except UnitError as exc:
        raise FormulaError(Problem.UNIT, f"the result unit {definition.result_unit!r}: {exc}") from None
    return check_definition(definition.formula, units, result_unit)


def check_score_definition(definition: ScoreDefinition, reserved_names: Iterable[str] = ()) -> Formula:
    """The parsed formula, or a `FormulaError` saying what is wrong: the fields, the label against `reserved_names`, then `check_computation`.

    `Problem.DEFINITION` for a field, and the formula's and the table's own codes for the rest, so a dialog can show one message and one place.
    `reserved_names` are the registry's calculator ids and display names (the caller reads them); the approved outputs' names are added here.
    This is what runs when a definition is made or edited.
    """
    _check_fields(definition, [*reserved_names, *output_names()])
    return check_computation(definition)

