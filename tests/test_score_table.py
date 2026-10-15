"""A derived score as a column of the project table (`domain/score_table.py`; `docs/DERIVED_SCORES_DESIGN.md` slice 3c).

Hand-built tables, so each way a cell can fail to be a number is one row; the real run, the real window and the parity with the Results reader are in
`test_main_window_scores.py` and `test_project_table_scores.py`.
"""

from __future__ import annotations

import math

import pytest

from openchem.domain.batch import SOURCE_SCORE, BatchCell, BatchColumn, BatchTable
from openchem.domain.common import CacheState, Provenance
from openchem.domain.refusal_kinds import REFUSAL_KEY, REFUSAL_KIND_KEY, RefusalKind, refusal_parameters
from openchem.domain.score_answer import LIMITATION, REFUSAL_CODE
from openchem.domain.score_constants import Constant
from openchem.domain.score_definition import DISPLAY_SUFFIX, FORMAT_DEFAULTS, ON_MISSING_DEFAULT, ScoreDefinition
from openchem.domain.score_outputs import approved_output
from openchem.domain.score_table import (
    CATEGORY,
    DEFAULTED_MARK,
    READ_FROM_TABLE,
    column_id_of,
    defaults_column,
    defaults_column_id_of,
    read_cell_output,
    score_cell,
    score_column,
    score_value_in_table,
    table_with_scores,
)
from openchem.domain.score_value import InputState, ScoreStatus

_TPSA = "descriptor:tpsa"
_LOGP = "descriptor:mol_logp"
_ROWS = ("aspirin-uuid", "ethanol-uuid")


def _column(output_id: str, *, units: str | None = None) -> BatchColumn:
    kind, _, rest = output_id.partition(":")
    carried = approved_output(output_id).carried_as if units is None else units
    return BatchColumn(column_id=output_id, label=rest, units=carried, source=kind, source_id=rest.partition(":")[0], numeric=True)


def _cell(value: float) -> BatchCell:
    return BatchCell(value=value, text=f"{value:.4g}")


def _table(*, tpsa=(63.6, 20.2), logp=(1.31, -0.0014), extra=()) -> BatchTable:
    table = BatchTable()
    for uuid, label in zip(_ROWS, ("Aspirin", "Ethanol")):
        table.add_row(uuid, label)
    for output_id, values in ((_TPSA, tpsa), (_LOGP, logp)):
        if values is None:
            continue
        table.add_column(_column(output_id))
        for uuid, value in zip(_ROWS, values):
            table.set_cell(uuid, output_id, _cell(value))
    for column, cells in extra:
        table.add_column(column)
        for uuid, cell in zip(_ROWS, cells):
            table.set_cell(uuid, column.column_id, cell)
    return table


def _definition(**changes) -> ScoreDefinition:
    base = dict(
        score_id="user.window", label="Window", formula="ramp(psa, 140, 60) * ramp(logp, 5, 2)", result_unit="1",
        inputs=(("psa", _TPSA), ("logp", _LOGP)), schema_version=1, owner="", created="2026-10-15", note="",
    )
    base.update(changes)
    return ScoreDefinition(**base)


# --- reading one cell --------------------------------------------------------------------------------------------------------------------


def test_a_cell_with_a_number_and_the_approved_unit_is_read():
    read = read_cell_output(_TPSA, _table(), _ROWS[0])
    assert read.state is InputState.READ and read.value == 63.6 and read.carried_as == approved_output(_TPSA).carried_as


def test_an_output_that_is_no_longer_approved_is_not_read():
    assert read_cell_output("descriptor:nothing", _table(), _ROWS[0]).state is InputState.NOT_APPROVED


def test_an_output_that_is_not_a_column_of_the_table_says_the_run_did_not_compute_it():
    read = read_cell_output(_LOGP, _table(logp=None), _ROWS[0])
    assert read.state is InputState.NOT_RUN and "not a column of this table" in read.note


def test_a_molecule_the_run_has_no_cell_for_is_not_run():
    table = _table()
    del table.cells[(_ROWS[0], _TPSA)]
    read = read_cell_output(_TPSA, table, _ROWS[0])
    assert read.state is InputState.NOT_RUN and "not computed for this molecule" in read.note


def test_a_failed_cell_is_a_failure_with_the_calculation_s_reason():
    table = _table()
    table.set_cell(_ROWS[0], _TPSA, BatchCell(text="", cache_state=CacheState.FAILED, error="Could not read this structure: boom"))
    read = read_cell_output(_TPSA, table, _ROWS[0])
    assert read.state is InputState.FAILED and read.note == "Could not read this structure: boom"


def test_a_failed_cell_with_no_reason_still_says_it_failed():
    table = _table()
    table.set_cell(_ROWS[0], _TPSA, BatchCell(text="", cache_state=CacheState.FAILED))
    assert read_cell_output(_TPSA, table, _ROWS[0]).note == "the calculation failed"


def test_a_cell_the_method_declined_is_a_refusal_not_a_failure():
    table = _table()
    provenance = Provenance(created_by="core", method="x", parameters=refusal_parameters("REFUSE_X", None))
    table.set_cell(_ROWS[0], _TPSA, BatchCell(text="", cache_state=CacheState.FAILED, error="declined", provenance=provenance))
    read = read_cell_output(_TPSA, table, _ROWS[0])
    assert read.state is InputState.REFUSED and read.note == "declined"
    plain = Provenance(created_by="core", method="x", parameters={"other": 1})
    table.set_cell(_ROWS[0], _TPSA, BatchCell(text="", cache_state=CacheState.FAILED, error="declined", provenance=plain))
    assert REFUSAL_KEY not in plain.parameters and read_cell_output(_TPSA, table, _ROWS[0]).state is InputState.FAILED


def test_a_cell_with_text_and_no_number_is_not_a_number():
    table = _table()
    table.set_cell(_ROWS[0], _TPSA, BatchCell(text="n/a"))
    read = read_cell_output(_TPSA, table, _ROWS[0])
    assert read.state is InputState.NOT_A_NUMBER and "no number" in read.note


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_a_value_that_is_not_finite_is_not_a_number(value):
    table = _table()
    table.set_cell(_ROWS[0], _TPSA, BatchCell(value=value, text="x"))
    assert read_cell_output(_TPSA, table, _ROWS[0]).state is InputState.NOT_A_NUMBER


def test_a_column_carrying_another_unit_is_refused_and_nothing_is_converted():
    table = _table()
    table.columns[0] = _column(_TPSA, units="nm^2")
    read = read_cell_output(_TPSA, table, _ROWS[0])
    assert read.state is InputState.UNIT and read.value is None and "nm^2" in read.note and "nothing is converted" in read.note


# --- evaluating --------------------------------------------------------------------------------------------------------------------------


def test_a_score_is_the_formula_over_the_cells_of_its_row():
    value = score_value_in_table(_definition(), _table(), _ROWS[0])
    assert value.status is ScoreStatus.VALUE
    assert value.value == pytest.approx(min(1, max(0, (63.6 - 140) / (60 - 140))) * min(1, max(0, (1.31 - 5) / (2 - 5))))


def test_each_row_has_its_own_value():
    table = _table()
    assert score_value_in_table(_definition(), table, _ROWS[0]).value != score_value_in_table(_definition(), table, _ROWS[1]).value


def test_an_input_that_cannot_be_read_refuses_the_score_naming_the_input_and_never_gives_a_zero():
    table = _table()
    table.set_cell(_ROWS[1], _LOGP, BatchCell(text="", cache_state=CacheState.FAILED, error="boom"))
    value = score_value_in_table(_definition(), table, _ROWS[1])
    assert value.status is ScoreStatus.REFUSED and value.value is None
    assert "logp (descriptor:mol_logp): boom" in value.reason


def test_a_named_constant_is_used_in_a_table_score():
    definition = _definition(formula="ramp(psa, hi, 60)", inputs=(("psa", _TPSA),), constants=(Constant("hi", 140.0, "Å^2"),))
    assert score_value_in_table(definition, _table(), _ROWS[0]).value == pytest.approx((63.6 - 140) / (60 - 140))


# --- the column and its cells ------------------------------------------------------------------------------------------------------------


def test_the_column_is_a_score_column_with_the_suffix_in_its_header_and_no_basis():
    column = score_column(_definition())
    assert column.column_id == column_id_of("user.window") == "score:user.window" and column.source == SOURCE_SCORE
    assert column.source_id == "user.window" and column.numeric and column.prediction_basis is None
    assert column.label == "Window " + DISPLAY_SUFFIX and column.header == column.label
    assert column.note == (
        f"Formula: {_definition().formula}. Reads: psa = tpsa; logp = mol_logp. Declared unit: 1. Definition {_definition().digest}. "
        f"Read from {READ_FROM_TABLE}. {LIMITATION}"
    )


def test_the_note_names_a_named_constant_with_its_unit():
    definition = _definition(formula="ramp(psa, hi, 60)", inputs=(("psa", _TPSA),), constants=(Constant("hi", 140.0, "\u00c5^2"),))
    assert "Reads: psa = tpsa; hi = 140 \u00c5^2." in score_column(definition).note


def test_a_unit_other_than_one_is_in_the_header():
    column = score_column(_definition(formula="psa", inputs=(("psa", _TPSA),), result_unit="Å^2"))
    assert column.units == "Å^2" and column.header == f"Window {DISPLAY_SUFFIX} (Å^2)"


def test_a_cell_with_a_number_carries_its_evidence_in_its_provenance():
    table = _table()
    value = score_value_in_table(_definition(), table, _ROWS[0])
    cell = score_cell(value)
    assert cell.value == value.value and cell.text == f"{value.value:.4g}" and not cell.failed and cell.error is None
    provenance = cell.provenance
    assert provenance.created_by == "user" and provenance.method == "derived_score:1"
    parameters = provenance.parameters
    assert parameters == {"validation": "user_defined_unvalidated", "digest": _definition().digest, "score_id": "user.window", "read_from": READ_FROM_TABLE}
    assert cell.detail == f"Inputs: psa = 63.6 {approved_output(_TPSA).carried_as}; logp = 1.31"
    assert REFUSAL_KEY not in parameters


def test_a_cell_with_no_number_is_a_failed_cell_whose_error_is_the_reason_classified_as_a_refusal():
    table = _table(logp=None)
    cell = score_cell(score_value_in_table(_definition(), table, _ROWS[0]))
    assert cell.failed and cell.value is None and cell.text == "" and "not a column of this table" in cell.error
    assert cell.provenance.parameters[REFUSAL_KEY] == REFUSAL_CODE and cell.provenance.parameters["validation"] == "user_defined_unvalidated" and cell.detail == ""


# --- the table ---------------------------------------------------------------------------------------------------------------------------


def test_with_no_scores_the_table_is_handed_back_as_it_is():
    table = _table()
    assert table_with_scores(table, ()).table is table
    assert table_with_scores(BatchTable(), [_definition()]).table.columns == []


def test_a_score_column_comes_before_the_runs_columns_and_the_run_s_table_is_not_touched():
    table = _table()
    before = (list(table.columns), dict(table.cells))
    scored = table_with_scores(table, [_definition()])
    assert [c.column_id for c in scored.table.columns] == ["score:user.window", _TPSA, _LOGP]
    assert scored.table is not table and (list(table.columns), dict(table.cells)) == before
    assert scored.table.row_uuids == table.row_uuids and scored.table.row_labels == table.row_labels
    assert scored.omitted == () and scored.note() == ""


def test_every_row_has_its_cell_and_it_is_the_value_the_row_s_cells_give():
    table = _table()
    scored = table_with_scores(table, [_definition()]).table
    for uuid in _ROWS:
        assert scored.cell(uuid, "score:user.window").value == pytest.approx(score_value_in_table(_definition(), table, uuid).value)


def test_scores_come_in_the_order_they_were_defined():
    first, second = _definition(score_id="user.a", label="A"), _definition(score_id="user.b", label="B", formula="psa", inputs=(("psa", _TPSA),), result_unit="Å^2")
    scored = table_with_scores(_table(), [first, second]).table
    assert [c.column_id for c in scored.columns][:2] == ["score:user.a", "score:user.b"]


def test_a_score_whose_input_the_run_did_not_compute_has_no_column_and_the_table_says_why():
    scored = table_with_scores(_table(logp=None), [_definition()])
    assert [c.column_id for c in scored.table.columns] == [_TPSA]
    (omission,) = scored.omitted
    assert omission.definition == _definition() and omission.missing == ("mol_logp",)
    assert scored.note() == "Scores not shown, because this run did not compute what they read: Window (user-defined, unvalidated) reads mol_logp."


def test_one_missing_input_does_not_hide_the_scores_that_can_be_shown():
    only_psa = _definition(score_id="user.psa", label="Only psa", formula="ramp(psa, 140, 60)", inputs=(("psa", _TPSA),))
    scored = table_with_scores(_table(logp=None), [_definition(), only_psa])
    assert "score:user.psa" in [c.column_id for c in scored.table.columns] and len(scored.omitted) == 1


def test_a_calculators_missing_output_is_named_by_its_fact_label():
    definition = _definition(formula="ob", inputs=(("ob", "calculator:oxygen_balance:Oxygen balance (CO basis)"),), result_unit="%")
    (omission,) = table_with_scores(_table(), [definition]).omitted
    assert omission.missing == ("Oxygen balance (CO basis)",)


def test_a_molecule_the_run_has_not_reached_is_left_blank_and_not_refused():
    table = _table()
    for output_id in (_TPSA, _LOGP):
        del table.cells[(_ROWS[1], output_id)]
    scored = table_with_scores(table, [_definition()]).table
    assert scored.cell(_ROWS[0], "score:user.window") is not None and scored.cell(_ROWS[1], "score:user.window") is None


def test_a_molecule_with_one_input_cell_and_not_the_other_is_refused_for_the_one_it_lacks():
    table = _table()
    del table.cells[(_ROWS[1], _LOGP)]
    cell = table_with_scores(table, [_definition()]).table.cell(_ROWS[1], "score:user.window")
    assert cell.failed and "logp (descriptor:mol_logp): it was not computed for this molecule in this run" in cell.error


def test_a_row_that_failed_before_anything_ran_has_a_refused_score_not_a_blank_one():
    table = _table()
    for output_id in (_TPSA, _LOGP):
        table.set_cell(_ROWS[1], output_id, BatchCell(text="", cache_state=CacheState.FAILED, error="This molecule has no structure yet."))
    cell = table_with_scores(table, [_definition()]).table.cell(_ROWS[1], "score:user.window")
    assert cell.failed and "This molecule has no structure yet." in cell.error


def test_a_definition_that_no_longer_checks_is_a_column_of_refusals_saying_so():
    broken = _definition(formula="ramp(psa, 140")
    scored = table_with_scores(_table(), [broken]).table
    cell = scored.cell(_ROWS[0], "score:user.window")
    assert cell.failed and "the definition no longer checks" in cell.error


def test_the_category_is_derived_scores():
    assert CATEGORY == "Derived scores"


# --- a calculator that declined or failed is filed in a placeholder column -------------------------------------------------------------------


_OB = "calculator:oxygen_balance:Oxygen balance (CO basis)"
_OB_PLACEHOLDER = "calculator:oxygen_balance"


def _declined(error="declined by the method") -> BatchCell:
    provenance = Provenance(created_by="core", method="oxygen_balance", parameters=refusal_parameters("REFUSE_X", None))
    return BatchCell(text="", cache_state=CacheState.FAILED, error=error, provenance=provenance)


def _placeholder_column() -> BatchColumn:
    return BatchColumn(column_id=_OB_PLACEHOLDER, label="Oxygen balance", source="calculator", source_id="oxygen_balance", numeric=False)


def test_a_row_whose_calculator_declined_is_a_refusal_read_from_the_placeholder_column():
    table = _table(extra=[(_placeholder_column(), (_declined(), _declined()))])
    read = read_cell_output(_OB, table, _ROWS[0])
    assert read.state is InputState.REFUSED and read.note == "declined by the method"


def test_a_row_whose_calculator_failed_outright_is_a_failure_read_from_the_placeholder_column():
    failed = BatchCell(text="", cache_state=CacheState.FAILED, error="boom")
    table = _table(extra=[(_placeholder_column(), (failed, failed))])
    read = read_cell_output(_OB, table, _ROWS[1])
    assert read.state is InputState.FAILED and read.note == "boom"


def test_a_row_the_calculator_worked_for_is_read_from_its_own_column_and_a_row_it_declined_from_the_placeholder():
    ok_column = _column(_OB)
    table = _table(extra=[(ok_column, (_cell(-79.9), None)), (_placeholder_column(), (None, _declined("not for this molecule")))])
    assert read_cell_output(_OB, table, _ROWS[0]).state is InputState.READ
    declined = read_cell_output(_OB, table, _ROWS[1])
    assert declined.state is InputState.REFUSED and declined.note == "not for this molecule"


def test_a_calculator_that_declined_for_every_row_is_filed_so_its_score_is_a_column_of_refusals_and_not_omitted():
    definition = _definition(formula="ob", inputs=(("ob", _OB),), result_unit="%")
    table = _table(extra=[(_placeholder_column(), (_declined(), _declined()))])
    scored = table_with_scores(table, [definition])
    assert scored.omitted == () and "score:user.window" in [c.column_id for c in scored.table.columns]
    cell = scored.table.cell(_ROWS[0], "score:user.window")
    assert cell.failed and "ob (calculator:oxygen_balance:Oxygen balance (CO basis)): declined by the method" in cell.error


def test_a_calculator_the_run_never_ran_is_still_omitted():
    definition = _definition(formula="ob", inputs=(("ob", _OB),), result_unit="%")
    assert len(table_with_scores(_table(), [definition]).omitted) == 1


def test_a_cell_filed_without_a_column_is_a_failure_and_not_a_number():
    table = _table(logp=None)
    table.set_cell(_ROWS[0], _LOGP, BatchCell(text="", cache_state=CacheState.FAILED, error="provider failed"))
    read = read_cell_output(_LOGP, table, _ROWS[0])
    assert read.state is InputState.FAILED and read.note == "provider failed"
    assert read_cell_output(_LOGP, table, _ROWS[1]).note == "it is not a column of this table: the run did not compute it"


# --- what the first mutation round found missing (slice 3c) -------------------------------------------------------------------------------------


def test_a_row_the_run_never_reached_says_it_was_not_computed_even_when_only_a_placeholder_column_exists():
    """The calculator failed for another row, so its placeholder column is in the table, but this row has no cell anywhere: not 'not a column'."""
    table = _table(extra=[(_placeholder_column(), (None, _declined()))])
    read = read_cell_output(_OB, table, _ROWS[0])
    assert read.state is InputState.NOT_RUN and read.note == "it was not computed for this molecule in this run"


def test_a_cell_filed_under_no_column_at_all_is_not_run_and_never_a_number():
    table = _table()
    table.set_cell(_ROWS[0], _OB, BatchCell(value=-79.9, text="-79.9"))
    read = read_cell_output(_OB, table, _ROWS[0])
    assert read.state is InputState.NOT_RUN and read.value is None and "not a column of this table" in read.note


def test_a_placeholder_cell_that_did_not_fail_is_not_a_refusal():
    table = _table(extra=[(_placeholder_column(), (_cell(1.0), None))])
    read = read_cell_output(_OB, table, _ROWS[0])
    assert read.state is InputState.NOT_RUN and read.note == "it was not computed for this molecule in this run"


def test_a_unit_refusal_says_which_unit_the_column_carried():
    table = _table()
    table.columns[0] = _column(_TPSA, units="nm^2")
    assert read_cell_output(_TPSA, table, _ROWS[0]).carried_as == "nm^2"


def test_the_cell_shows_four_significant_digits_and_keeps_the_whole_number():
    table = _table(tpsa=(61.82, 20.2))
    cell = score_cell(score_value_in_table(_definition(formula="ramp(psa, 140, 60)", inputs=(("psa", _TPSA),)), table, _ROWS[0]))
    assert cell.text == "0.9773" and cell.value == pytest.approx(0.97725)


def test_a_refusal_is_classified_as_one_that_needs_an_input():
    cell = score_cell(score_value_in_table(_definition(), _table(logp=None), _ROWS[0]))
    assert cell.provenance.parameters[REFUSAL_KIND_KEY] == RefusalKind.NEEDS_INPUT.value


def test_a_score_reading_two_things_the_run_did_not_compute_names_both():
    scored = table_with_scores(_table(tpsa=None, logp=None, extra=[(_column(_OB), (_cell(-79.9), _cell(-206.0)))]), [_definition()])
    (omission,) = scored.omitted
    assert omission.missing == ("tpsa", "mol_logp") and str(omission) == "Window (user-defined, unvalidated) reads tpsa, mol_logp"


def test_two_scores_the_run_could_not_compute_are_both_named_in_the_note():
    other = _definition(score_id="user.other", label="Other", formula="ramp(logp, 5, 2)", inputs=(("logp", _LOGP),))
    scored = table_with_scores(_table(tpsa=None, logp=None, extra=[(_column(_OB), (_cell(-79.9), _cell(-206.0)))]), [_definition(), other])
    assert scored.note() == (
        "Scores not shown, because this run did not compute what they read: "
        "Window (user-defined, unvalidated) reads tpsa, mol_logp; Other (user-defined, unvalidated) reads mol_logp."
    )


def test_a_table_with_no_columns_yet_has_nothing_to_say_about_scores():
    scored = table_with_scores(BatchTable(), [_definition()])
    assert scored.omitted == () and scored.note() == ""


def test_the_scored_table_keeps_the_per_atom_data_and_owns_its_rows():
    table = _table()
    table.set_per_atom(_ROWS[0], "gasteiger", object())
    scored = table_with_scores(table, [_definition()]).table
    assert scored.per_atom == table.per_atom and scored.per_atom_for(_ROWS[0], "gasteiger") is table.per_atom_for(_ROWS[0], "gasteiger")
    assert scored.row_uuids is not table.row_uuids and scored.row_labels is not table.row_labels
    scored.add_row("new-uuid", "New")
    assert "new-uuid" not in table.row_uuids and "new-uuid" not in table.row_labels


# --- the second policy: a number that used a default is marked, and the table says which input --------------------------------------------


def _defaulting(**defaults) -> ScoreDefinition:
    return _definition(on_missing=ON_MISSING_DEFAULT, schema_version=FORMAT_DEFAULTS, defaults=tuple(defaults.items()))


def test_a_cell_that_used_a_default_ends_in_the_mark_keeps_its_number_whole_and_its_hover_says_which_input():
    table = _table(logp=None)
    value = score_value_in_table(_defaulting(logp=3.5), table, _ROWS[0])
    cell = score_cell(value)
    assert cell.value == value.value and cell.text == f"{value.value:.4g}{DEFAULTED_MARK}" and DEFAULTED_MARK == "*"
    assert isinstance(cell.value, float) and not cell.failed
    assert cell.detail == f"Inputs: psa = 63.6 {approved_output(_TPSA).carried_as}; logp = 3.5 (a default; not computed in this run)"


def test_a_cell_that_used_no_default_is_exactly_as_it_was():
    cell = score_cell(score_value_in_table(_defaulting(logp=3.5), _table(), _ROWS[0]))
    assert not cell.text.endswith(DEFAULTED_MARK) and "default" not in cell.detail


def test_the_column_says_what_its_defaults_are_and_what_the_mark_means():
    note = score_column(_defaulting(logp=3.5)).note
    assert "Defaults, used only for an input this run did not compute: logp = 3.5" in note and f"marked {DEFAULTED_MARK}" in note
    assert "Defaults" not in score_column(_definition()).note


def test_a_score_whose_defaulted_input_the_run_did_not_compute_still_gets_its_column_and_a_companion_right_after_it():
    scored = table_with_scores(_table(logp=None), [_defaulting(logp=3.5)])
    assert scored.omitted == () and scored.note() == ""
    assert [c.column_id for c in scored.table.columns] == ["score:user.window", "score_defaults:user.window", _TPSA]
    value_column, companion = scored.table.columns[:2]
    assert companion.numeric is False and companion.source == SOURCE_SCORE and companion.units == "" and value_column.numeric is True
    assert companion.label == f"Window {DISPLAY_SUFFIX}: inputs given a default" and companion.column_id == defaults_column_id_of("user.window")
    for uuid in _ROWS:
        assert scored.table.cell(uuid, companion.column_id).text == "logp" and scored.table.cell(uuid, value_column.column_id).text.endswith(DEFAULTED_MARK)


def test_a_row_that_used_no_default_has_no_companion_cell_and_no_mark():
    table = _table()
    scored = table_with_scores(table, [_defaulting(logp=3.5)]).table
    assert scored.cell(_ROWS[0], "score_defaults:user.window") is None
    assert not scored.cell(_ROWS[0], "score:user.window").text.endswith(DEFAULTED_MARK)


def test_a_score_with_no_defaults_has_no_companion_column():
    scored = table_with_scores(_table(), [_definition()]).table
    assert [c.column_id for c in scored.columns] == ["score:user.window", _TPSA, _LOGP]


def test_an_input_the_run_did_not_compute_and_the_definition_gave_no_default_for_still_omits_the_score():
    scored = table_with_scores(_table(logp=None), [_defaulting(psa=100.0)])
    assert [c.column_id for c in scored.table.columns] == [_TPSA]
    (omission,) = scored.omitted
    assert omission.missing == ("mol_logp",) and "mol_logp" in scored.note()


def test_a_run_that_computed_none_of_what_the_score_reads_has_no_column_even_when_every_input_has_a_default():
    other = (_column("descriptor:mol_wt"), (_cell(180.0), _cell(46.0)))
    scored = table_with_scores(_table(tpsa=None, logp=None, extra=[other]), [_defaulting(psa=100.0, logp=3.5)])
    assert [c.column_id for c in scored.table.columns] == ["descriptor:mol_wt"], "every row would be a number worked out from defaults alone"
    (omission,) = scored.omitted
    assert omission.missing == ("tpsa", "mol_logp")


def test_a_refused_row_has_no_companion_cell_and_a_defaults_column_is_text():
    table = _table(logp=None)
    table.set_cell(_ROWS[0], _TPSA, BatchCell(text="", cache_state=CacheState.FAILED, error="boom"))
    scored = table_with_scores(table, [_defaulting(logp=3.5)]).table
    assert scored.cell(_ROWS[0], "score:user.window").failed and scored.cell(_ROWS[0], "score_defaults:user.window") is None
    assert defaults_column(_defaulting(logp=3.5)).numeric is False


def test_defaults_on_a_definition_whose_policy_is_not_the_second_one_are_never_used_to_show_a_column():
    """The evaluator reads a policy this build does not know as the first one, so the table must not give such a score a column on the strength of a default the evaluator would not use."""
    odd = _definition(on_missing="zero", defaults=(("logp", 3.5),))
    scored = table_with_scores(_table(logp=None), [odd])
    assert [c.column_id for c in scored.table.columns] == [_TPSA] and scored.omitted[0].missing == ("mol_logp",)
