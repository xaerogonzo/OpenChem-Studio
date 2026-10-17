"""A derived score as a column of the project table (`docs/DERIVED_SCORES_DESIGN.md` section 8, slice 3c).

**A SCORE COLUMN IS COMPUTED FROM THE TABLE'S OWN OTHER CELLS WHEN THE TABLE IS SHOWN, AND NEVER RUN.** It reads the cells of the columns its inputs name, row by
row, and evaluates the formula with the same rule the Results reader uses (`score_value.evaluate_score_with`): the only thing that differs is where the numbers
are read from. So a score defined, edited or removed changes the table at once, without a second project run; no value is stored; and the column is in the table's
exports and analytics because it is an ordinary column of the table they are handed.

**WHY READING THE TABLE'S CELLS IS SAFE NOW.** The project run used to hand a conformer to every descriptor, so seven of the seventeen approved descriptors read
differently in the table than in Results. Each column is now computed on the input it declares (the drawing, for every approved output), so a cell and the Results
reader's stored result are one number. `tests/test_score_table.py` runs both over a molecule that HAS a conformer and fails if they ever differ.

**A TABLE IS A SNAPSHOT, AND SO IS THE SCORE COLUMN.** It is exactly as current as the cells it reads: a molecule edited since the run has the old cells and the
old score, as every other column of the table does. Results is where a score is re-evaluated against the structure as it is now.

**A CELL IS READ BY THE RULES OF AN OUTPUT, NEVER BY ITS LOOKS.** An input that is not a column of the table, a molecule it was not computed for, a cell that failed
or refused, a cell with no number, and a cell whose unit is not the approved one each REFUSE the score for that row, and the reason names the input. A refusal is
never a zero and never a skipped term. Nothing is converted.

**THE NUMBER IS THE CELL'S `value`.** For a descriptor it is the typed value; for a calculator's output it is the fact's value, which the reducer takes as a
number when it is one and parses from the displayed text when it is not. An approved output is one whose producer types its number (`tests/test_score_outputs.py`),
so the parse never happens to one; the parity test above is what would show it if a producer ever stopped.

**A CALCULATOR THAT DECLINED OR FAILED HAS NO FACT COLUMN, ONLY A PLACEHOLDER.** The batch files a failed calculator under `calculator:<id>` (one column, for
the rows that failed) and its facts under `calculator:<id>:<label>` (for the rows that worked), so a row whose calculator refused has no cell of the output's own
column. The placeholder's cell is then the answer, and it is read as one: a refusal is told apart from a failure by its provenance, exactly as Results does, and
a score on a table every row of which was refused says why in each row rather than vanishing. Found by the parity test, which saw the table say "not computed" where Results said
"declined".

**THE SCORE COLUMNS ARE THE FIRST COLUMNS, not the last.** A run of calculators makes a table many columns wide, and in the drive the scores sat off the right edge of the dock: a
person who defined a score came to read it, so it is the first thing the table shows after the molecule's name.

**A SCORE WHOSE INPUTS THE RUN DID NOT COMPUTE HAS NO COLUMN.** Every row would say the same thing, so the table says it once instead (`Omission`): which score, and
which of the things it reads are not in the table. An input the definition declares a default for does not count as missing (the second `on_missing` policy), unless no input at all
was computed, which would make every row a number worked out from defaults alone.

**A NUMBER THAT USED A DEFAULT SAYS SO IN THE TABLE, IN THE CSV, AND IN THE GRID.** The cell's text ends in `*` and its hover names the inputs and their defaults; and a score with defaults has
a companion column (`defaults_column`), right after it, that lists for each row the inputs a default stood in for. The companion is a column, not a mark, because a CSV carries the
number whole (`cell.value`), so a `*` would be lost the moment the table is exported, and a number that used a default must not look like one that did not once it has left the window.

Pure: no Qt, no chemistry.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from openchem.domain.batch import SOURCE_SCORE, BatchCell, BatchColumn, BatchTable
from openchem.domain.common import CacheState, Provenance
from openchem.domain.refusal_kinds import REFUSAL_KEY, RefusalKind, refusal_parameters
from openchem.domain.score_answer import LIMITATION, REFUSAL_CODE, SIGNIFICANT_DIGITS
from openchem.domain.score_definition import ON_MISSING_DEFAULT, VALIDATION, ScoreDefinition
from openchem.domain.score_formula import Refusal
from openchem.domain.score_outputs import READ_FROM, accept_value, approved_output, output_title
from openchem.domain.score_value import InputState, OutputRead, ScoreStatus, ScoreValue, evaluate_score_with, geometry_text

#: The column group a score column is listed under in the table's "Columns" menu.
CATEGORY = "Derived scores"

#: Where a score column's numbers come from, said in its cells' provenance.
READ_FROM_TABLE = "the project table's own cells"

#: What a displayed number ends in when it used a default (the cell's hover says which inputs, and what the defaults were).
DEFAULTED_MARK = "*"


def column_id_of(score_id: str) -> str:
    """The id of a score's column. The prefix keeps it from ever equalling a descriptor's or a calculator's."""
    return f"{SOURCE_SCORE}:{score_id}"


def defaults_column_id_of(score_id: str) -> str:
    """The id of the companion column that says which inputs a row's number used a default for."""
    return f"{SOURCE_SCORE}_defaults:{score_id}"


def read_cell_output(output_id: str, table: BatchTable, molecule_uuid: str) -> OutputRead:
    """What an approved output has for one row of `table`, or why it has nothing (the table's version of `score_value.read_output`)."""
    output = approved_output(output_id)
    if output is None:
        return OutputRead(InputState.NOT_APPROVED, note="it is no longer an approved output")
    column = table.column(output_id)
    cell = table.cell(molecule_uuid, output_id)
    if cell is None:
        cell = _declined_cell(table, molecule_uuid, output_id)
    if cell is None:
        note = "it was not computed for this molecule in this run" if column is not None or _is_filed(table, output_id) else "it is not a column of this table: the run did not compute it"
        return OutputRead(InputState.NOT_RUN, note=note)
    if cell.failed:
        refused = isinstance(cell.provenance.parameters.get(REFUSAL_KEY), str) if cell.provenance is not None else False
        return OutputRead(InputState.REFUSED if refused else InputState.FAILED, note=cell.error or "the calculation failed")
    if column is None:
        return OutputRead(InputState.NOT_RUN, note="it is not a column of this table: the run did not compute it")
    if cell.value is None:
        return OutputRead(InputState.NOT_A_NUMBER, note="the cell holds no number")
    try:
        number = accept_value(output, cell.value, column.units)
    except Refusal as exc:
        state = InputState.UNIT if column.units != output.carried_as else InputState.NOT_A_NUMBER
        return OutputRead(state, carried_as=column.units, note=exc.reason)
    # A geometry cell is stamped with the conformer the run measured it on, and the hover says which: a table is a snapshot, so this is the conformer of THAT run.
    where = geometry_text(cell.provenance.parameters if cell.provenance is not None else None) if output.input != READ_FROM else ""
    return OutputRead(InputState.READ, number, column.units, geometry=where)


def _placeholder_id(output_id: str) -> str:
    """Where the batch files a calculator that failed for a row: `calculator:<id>`, for an output named `calculator:<id>:<fact label>`. Empty for a descriptor."""
    kind, _, rest = output_id.partition(":")
    return f"{kind}:{rest.partition(':')[0]}" if kind == "calculator" else ""


def _declined_cell(table: BatchTable, molecule_uuid: str, output_id: str) -> BatchCell | None:
    """The failed cell the batch filed for this row in the calculator's placeholder column, when it filed one."""
    placeholder = _placeholder_id(output_id)
    cell = table.cell(molecule_uuid, placeholder) if placeholder else None
    return cell if cell is not None and cell.failed else None


def _is_filed(table: BatchTable, output_id: str) -> bool:
    """Whether the run said anything about this output: its own column, or the calculator's placeholder column."""
    placeholder = _placeholder_id(output_id)
    return table.column(output_id) is not None or (bool(placeholder) and table.column(placeholder) is not None)


def score_value_in_table(definition: ScoreDefinition, table: BatchTable, molecule_uuid: str) -> ScoreValue:
    """The value of `definition` for one row of `table`, or the reason it has none."""
    return evaluate_score_with(definition, lambda output_id: read_cell_output(output_id, table, molecule_uuid))


def _column_note(definition: ScoreDefinition) -> str:
    """What the column is: the formula and what it reads, so a table that is exported or hovered says it once rather than in every cell."""
    reads = "; ".join(f"{name} = {output_title(output_id) or output_id}" for name, output_id in definition.inputs)
    constants = "".join(f"; {constant.name} = {constant.value:.6g} {constant.unit}" for constant in definition.constants)
    defaults = ""
    if definition.on_missing == ON_MISSING_DEFAULT and definition.defaults:
        said = ", ".join(f"{name} = {value:.6g}" for name, value in definition.defaults)
        defaults = (
            f" Defaults, used only for an input this run did not compute: {said}. A value marked {DEFAULTED_MARK} used at least one, and the column beside this one names which."
        )
    return (
        f"Formula: {definition.formula}. Reads: {reads}{constants}. Declared unit: {definition.result_unit}.{defaults} Definition {definition.digest}. "
        f"Read from {READ_FROM_TABLE}. {LIMITATION}"
    )


def score_column(definition: ScoreDefinition) -> BatchColumn:
    """The column a score is. Its label carries the suffix every surface gives it, so it is in the header of every export, and it is never given a basis: nothing
    here is a prediction."""
    return BatchColumn(
        column_id=column_id_of(definition.score_id),
        label=definition.display_label,
        units="" if definition.result_unit == "1" else definition.result_unit,
        source=SOURCE_SCORE,
        source_id=definition.score_id,
        numeric=True,
        note=_column_note(definition),
    )


def defaults_column(definition: ScoreDefinition) -> BatchColumn:
    """The companion of a score that declares defaults: for each row, the inputs a default stood in for (blank for a row that used none). Text, never numeric."""
    return BatchColumn(
        column_id=defaults_column_id_of(definition.score_id),
        label=f"{definition.display_label}: inputs given a default",
        units="",
        source=SOURCE_SCORE,
        source_id=definition.score_id,
        numeric=False,
        note=(
            f"Which inputs of {definition.display_label} were not computed in this run and were given the default the definition declares. "
            "A number that used one is not the result of a calculation for that input."
        ),
    )


def _number(value: float) -> str:
    return f"{value:.{SIGNIFICANT_DIGITS}g}"


def _inputs_said(value: ScoreValue) -> str:
    return "; ".join(
        f"{item.name} = {item.value:.6g}{' ' + item.carried_as if item.carried_as else ''}{' (a default; not computed in this run)' if item.state is InputState.DEFAULT else ''}"
        f"{' (measured on ' + item.geometry + ')' if item.geometry else ''}"
        for item in value.inputs
        if item.state in (InputState.READ, InputState.DEFAULT)
    )


def score_cell(value: ScoreValue) -> BatchCell:
    """One row's cell: the number with the evidence behind it in its provenance, or a failed cell whose error is the reason, classified as a refusal."""
    definition = value.definition
    # The same for every row of the column, so the report's methods section can say it once; what differs by row (the inputs) is the cell's `detail`.
    parameters: dict[str, object] = {"validation": VALIDATION, "digest": definition.digest, "score_id": definition.score_id, "read_from": READ_FROM_TABLE}
    if value.status is ScoreStatus.VALUE:
        provenance = Provenance(created_by="user", method=f"derived_score:{definition.schema_version}", parameters=parameters)
        mark = DEFAULTED_MARK if value.defaulted else ""
        return BatchCell(value=value.value, text=_number(value.value) + mark, provenance=provenance, detail=f"Inputs: {_inputs_said(value)}")
    parameters.update(refusal_parameters(REFUSAL_CODE, RefusalKind.NEEDS_INPUT))
    provenance = Provenance(created_by="user", method=f"derived_score:{definition.schema_version}", parameters=parameters)
    return BatchCell(text="", cache_state=CacheState.FAILED, error=value.reason, provenance=provenance)


@dataclass(frozen=True)
class Omission:
    """A score with no column in this table, and why."""

    definition: ScoreDefinition
    #: What it reads that the table does not hold, by name.
    missing: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.definition.display_label} reads {', '.join(self.missing)}"


@dataclass(frozen=True)
class ScoredTable:
    """A table with its score columns added, and the scores that could not be."""

    table: BatchTable
    omitted: tuple[Omission, ...] = ()

    def note(self) -> str:
        """One sentence for the table's status area, or empty when nothing is missing."""
        if not self.omitted:
            return ""
        return "Scores not shown, because this run did not compute what they read: " + "; ".join(str(item) for item in self.omitted) + "."


def _missing_inputs(definition: ScoreDefinition, table: BatchTable) -> tuple[str, ...]:
    """What the score reads that the run did not compute and the definition has no default for. When it has one for every input the run did not compute but NOT ONE input
    was computed, every row would be a number worked out from defaults alone, so all of it is missing."""
    defaults = dict(definition.defaults) if definition.on_missing == ON_MISSING_DEFAULT else {}
    unfiled = [(name, output_id) for name, output_id in definition.inputs if not _is_filed(table, output_id)]
    needed = [(name, output_id) for name, output_id in unfiled if name not in defaults]
    if not needed and len(unfiled) == len(definition.inputs):
        needed = unfiled
    return tuple(output_title(output_id) or output_id for _name, output_id in needed)


def _has_any_cell(table: BatchTable, molecule_uuid: str, definition: ScoreDefinition) -> bool:
    return any(
        table.cell(molecule_uuid, output_id) is not None or _declined_cell(table, molecule_uuid, output_id) is not None for _name, output_id in definition.inputs
    )


def table_with_scores(table: BatchTable, definitions: Sequence[ScoreDefinition]) -> ScoredTable:
    """`table` with a column for every score whose inputs are all columns of it. The score columns come FIRST, in the order the scores were defined.

    First, because a run of calculators makes a table many columns wide (one report can be thirty), and a column added at the end would be off the screen: the numbers a
    person asked for by name are the ones they came to read.

    The result is a COPY: the run owns `table` and mutates it as rows arrive, and a score column written into it would be rebuilt from stale cells at the next row.
    A molecule the run has not reached yet (no cell of any input) is left blank, not refused.
    """
    if not definitions or not table.columns:
        return ScoredTable(table)
    cells = dict(table.cells)
    score_columns: list[BatchColumn] = []
    omitted: list[Omission] = []
    for definition in definitions:
        missing = _missing_inputs(definition, table)
        if missing:
            omitted.append(Omission(definition, missing))
            continue
        column = score_column(definition)
        score_columns.append(column)
        companion = defaults_column(definition) if definition.on_missing == ON_MISSING_DEFAULT and definition.defaults else None
        if companion is not None:
            score_columns.append(companion)
        for molecule_uuid in table.row_uuids:
            if not _has_any_cell(table, molecule_uuid, definition):
                continue
            value = score_value_in_table(definition, table, molecule_uuid)
            cells[(molecule_uuid, column.column_id)] = score_cell(value)
            if companion is not None and value.status is ScoreStatus.VALUE and value.defaulted:
                cells[(molecule_uuid, companion.column_id)] = BatchCell(text=", ".join(item.name for item in value.defaulted))
    scored = BatchTable(
        row_uuids=list(table.row_uuids), row_labels=dict(table.row_labels), columns=[*score_columns, *table.columns], cells=cells, per_atom=table.per_atom
    )
    return ScoredTable(scored, tuple(omitted))
