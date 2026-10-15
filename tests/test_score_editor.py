"""The definition dialog's view model: what a draft says, and what is wrong with it (`domain/score_editor.py`).

The dialog holds strings and asks `check_draft` after every keystroke, so these are the sentences a person reads while typing. Each problem is checked for the FIELD it
belongs to (so the dialog marks the right box) and, for the formula, the position it points at.
"""

from __future__ import annotations

import pytest

from openchem.domain.score_editor import (
    DRAFT_ID,
    OK,
    ConstantRow,
    Draft,
    InputRow,
    check_draft,
    output_choices,
    pointer_lines,
    suggest_name,
)
from openchem.domain.score_formula import MAX_CHARACTERS, FormulaError, Problem, check_input_names
from openchem.domain.score_outputs import APPROVED, ENDPOINTS

_TPSA = "descriptor:tpsa"
_LOGP = "descriptor:mol_logp"


def _draft(**changes) -> Draft:
    base = Draft(
        label="Polar window",
        formula="ramp(psa, hi, 60) * ramp(logp, 5, 2)",
        result_unit="1",
        inputs=(InputRow("psa", _TPSA), InputRow("logp", _LOGP)),
        constants=(ConstantRow("hi", "140", "Å^2"),),
        owner="Alex",
        note="a first try",
    )
    from dataclasses import replace

    return replace(base, **changes)


# --- turning a draft into a definition --------------------------------------------------------------------------------------------


def test_a_good_draft_is_a_definition_with_the_fields_trimmed():
    definition = _draft(label="  Polar window ", result_unit=" 1 ", owner=" Alex ").to_definition(score_id="user.x", created="2026-10-14")
    assert definition.score_id == "user.x" and definition.created == "2026-10-14"
    assert definition.label == "Polar window" and definition.result_unit == "1" and definition.owner == "Alex"
    assert definition.inputs == (("psa", _TPSA), ("logp", _LOGP)) and definition.constants[0].value == 140.0 and definition.constants[0].unit == "Å^2"


def test_a_draft_has_the_id_it_is_given_before_it_is_saved():
    assert _draft().to_definition().score_id == DRAFT_ID == "user.draft"


def test_a_definition_and_the_draft_made_from_it_say_the_same_thing():
    definition = _draft().to_definition(score_id="user.x", created="2026-10-14")
    assert Draft.from_definition(definition).to_definition(score_id="user.x", created="2026-10-14") == definition


@pytest.mark.parametrize("text", ["140", "1.4", "0.5", "1e3", "1.5e3", "-2", "+3.5", "1E-2", " 7 "])
def test_a_constant_may_be_typed_as_any_plain_number(text):
    assert _draft(constants=(ConstantRow("hi", text, "Å^2"),)).to_definition().constants[0].value == float(text)


@pytest.mark.parametrize(
    "text", ["", " ", "abc", "nan", "inf", "-inf", "1_000", "1,5", "1.2.3", "1e", "e3", "0x10", "1 2", "١٢", ".5", "1.", "1.e3", "--2"]
)
def test_a_constant_that_is_not_a_plain_number_is_a_constant_problem_naming_it(text):
    with pytest.raises(FormulaError, match="constant 'hi'") as caught:
        _draft(constants=(ConstantRow("hi", text, "Å^2"),)).to_definition()
    assert caught.value.problem is Problem.CONSTANT


def test_a_constant_too_large_to_use_is_refused():
    with pytest.raises(FormulaError, match="too large"):
        _draft(constants=(ConstantRow("hi", "1e999", "Å^2"),)).to_definition()


def test_a_blank_draft_is_blank_and_one_with_anything_in_it_is_not():
    assert Draft().is_blank and not Draft(label="x").is_blank and not Draft(formula="x").is_blank
    assert not Draft(inputs=(InputRow(),)).is_blank and not Draft(constants=(ConstantRow(),)).is_blank and not Draft(note="n").is_blank


# --- what is said about a draft ------------------------------------------------------------------------------------------------------


def test_a_draft_that_checks_says_what_it_works_out_to():
    result = check_draft(_draft())
    assert result.ok and result.message == f"{OK}: it works out to 1." and result.worked_out == "1"
    assert result.problem == "" and result.where == "" and result.position is None


def test_a_blank_draft_says_what_to_do_and_is_not_an_error_in_any_field():
    result = check_draft(Draft())
    assert not result.ok and result.where == "" and result.problem == "" and "choose what it reads" in result.message


@pytest.mark.parametrize(
    "changes, problem, where",
    [
        ({"label": ""}, "definition", "label"),
        ({"label": "x" * 81}, "definition", "label"),
        ({"label": "!!!"}, "definition", "label"),
        ({"owner": "o" * 81}, "definition", "owner"),
        ({"note": "n" * 501}, "definition", "note"),
        ({"inputs": (), "formula": "1 + 1", "constants": ()}, "definition", "inputs"),
        ({"inputs": (InputRow("psa", "descriptor:nothing"), InputRow("logp", _LOGP))}, "output", "inputs"),
        ({"inputs": (InputRow("Bad Name", _TPSA), InputRow("logp", _LOGP))}, "inputs", "inputs"),
        ({"inputs": (InputRow("psa", _TPSA), InputRow("psa", _LOGP))}, "inputs", "inputs"),
        ({"constants": (ConstantRow("hi", "abc", "Å^2"),)}, "constant", "constants"),
        ({"constants": (ConstantRow("hi", "140", "furlong"),)}, "constant", "constants"),
        ({"constants": (ConstantRow("psa", "140", "Å^2"),)}, "constant", "constants"),
        ({"formula": "ramp(psa, hi, 60) *"}, "syntax", "formula"),
        ({"formula": "ramp(psa, hi, 60) * ramp(logp, 5, 2) * nothing"}, "name", "formula"),
        ({"formula": "ramp(psa, hi)"}, "function", "formula"),
        ({"formula": "ramp(psa, hi, 60) * ramp(logp, 5, 2) ^ 9"}, "exponent", "formula"),
        ({"formula": "ramp(psa, hi, 60)"}, "inputs", "inputs"),
        ({"result_unit": "%"}, "unit", "unit"),
        ({"result_unit": "furlong"}, "unit", "unit"),
        ({"result_unit": ""}, "unit", "unit"),
    ],
)
def test_each_problem_is_said_with_its_code_and_the_field_it_belongs_to(changes, problem, where):
    result = check_draft(_draft(**changes))
    assert not result.ok and result.problem == problem and result.where == where, (result.problem, result.where, result.message)
    assert result.message


def test_two_estimates_of_one_quantity_are_a_consensus_problem_on_the_inputs():
    draft = _draft(
        formula="a + b",
        inputs=(InputRow("a", "descriptor:esol_logs"), InputRow("b", "calculator:solubility:Predicted intrinsic solubility (mol/L)")),
        constants=(),
    )
    result = check_draft(draft)
    assert result.problem == "consensus" and result.where == "inputs" and "consensus predictor" in result.message


def test_a_syntax_error_carries_the_position_it_points_at():
    result = check_draft(_draft(formula="ramp(psa, hi, 60) * $"))
    assert result.problem == "syntax" and result.position == 20


def test_a_unit_that_does_not_match_still_says_what_the_formula_works_out_to():
    result = check_draft(_draft(result_unit="%"))
    assert result.where == "unit" and result.worked_out == "1" and "works out to 1" in result.message


def test_a_wrong_unit_constant_is_a_unit_problem_in_the_formula_and_says_which_units_met():
    result = check_draft(_draft(constants=(ConstantRow("hi", "140", "nm^2"),)))
    assert result.problem == "unit" and "Å^2" in result.message and "nm^2" in result.message
    assert result.where == "formula" and result.position is not None, "it is in the formula, so the formula is marked and the caret points at the call"


def test_a_unit_clash_inside_the_formula_is_marked_on_the_formula_and_not_on_the_unit_box():
    draft = _draft(formula="psa + logp", constants=(), inputs=(InputRow("psa", _TPSA), InputRow("logp", _LOGP)))
    result = check_draft(draft)
    assert result.problem == "unit" and result.where == "formula" and result.position is not None
    declared = check_draft(_draft(result_unit="%"))
    assert declared.problem == "unit" and declared.where == "unit" and declared.position is None, "a declared unit that is wrong has no place in the formula"


def test_the_label_is_reported_before_a_formula_that_is_also_wrong():
    result = check_draft(_draft(label="", formula="ramp("))
    assert result.where == "label"


def test_a_label_close_to_a_reserved_name_is_reported_on_the_label():
    result = check_draft(_draft(label="CNS MPO v2"), reserved_names=["cns_mpo"])
    assert result.where == "label" and "too close to 'cns_mpo'" in result.message


def test_the_work_out_unit_is_empty_when_the_inputs_do_not_check():
    assert check_draft(_draft(inputs=(InputRow("psa", "descriptor:nothing"), InputRow("logp", _LOGP)))).worked_out == ""


# --- choosing an input ---------------------------------------------------------------------------------------------------------------------


def test_there_is_one_choice_for_every_approved_output_sorted_by_what_it_is_called():
    choices = output_choices()
    assert [c.output_id for c in choices].sort() == [e.output_id for e in APPROVED].sort()
    assert {c.output_id for c in choices} == {e.output_id for e in APPROVED}
    texts = [c.text.casefold() for c in choices]
    assert texts == sorted(texts) and len(set(texts)) == len(texts)


def test_a_choice_says_what_it_measures_and_its_unit_when_it_has_one():
    by_id = {c.output_id: c for c in output_choices()}
    assert by_id[_TPSA].text == f"tpsa (Å^2): {ENDPOINTS['polar_surface_area']}"
    assert by_id[_LOGP].text == f"mol_logp: {ENDPOINTS['logp_octanol_water']}", "a dimensionless output shows no unit"
    assert by_id["calculator:oxygen_balance:Oxygen balance (CO basis)"].text.startswith("Oxygen balance (CO basis) (%):")


def test_every_suggested_name_is_usable_as_an_input_name():
    for choice in output_choices():
        check_input_names([choice.suggested_name])


def test_the_two_oxygen_balances_do_not_suggest_the_same_name():
    by_id = {c.output_id: c.suggested_name for c in output_choices()}
    assert by_id["calculator:oxygen_balance:Oxygen balance (CO basis)"] == "oxygen_balance_co_basis"
    assert by_id["calculator:oxygen_balance:Oxygen balance (CO₂ basis)"] == "oxygen_balance_co2_basis"


def test_a_suggested_name_avoids_the_names_taken_and_the_functions():
    assert suggest_name(_TPSA, []) == "tpsa"
    assert suggest_name(_TPSA, ["tpsa"]) == "tpsa_2"
    assert suggest_name(_TPSA, ["tpsa", "tpsa_2"]) == "tpsa_3"
    assert suggest_name("descriptor:abs", []) == "abs_2" and suggest_name("descriptor:ln", ["x"]) == "ln_2"


def test_a_suggested_name_is_valid_for_an_output_with_a_awkward_title():
    name = suggest_name("calculator:c:123 (strange) title!", [])
    assert name == "x_123_strange_title"
    check_input_names([name])


def test_a_title_that_already_says_its_unit_is_not_given_it_twice():
    by_id = {c.output_id: c for c in output_choices()}
    text = by_id["calculator:solubility:Predicted intrinsic solubility (mol/L)"].text
    assert text.startswith("Predicted intrinsic solubility (mol/L):") and "(mol/L) (mol/L)" not in text


def test_no_choice_says_a_unit_twice():
    for choice in output_choices():
        assert choice.text.count(f"({choice.unit})") <= 1, choice.text


# --- pointing at a place in the formula ----------------------------------------------------------------------------------------------------


def _lines(formula, position, **kwargs):
    excerpt, caret = pointer_lines(formula, position, **kwargs).split("\n")
    return excerpt, caret


def test_the_caret_is_under_the_character_it_points_at():
    excerpt, caret = _lines("ramp(psa, 140, 60) * $", 21)
    assert excerpt == "ramp(psa, 140, 60) * $" and caret == " " * 21 + "^" and excerpt[len(caret) - 1] == "$"


def test_a_position_at_the_end_points_one_past_the_last_character():
    excerpt, caret = _lines("ramp(psa, 140, 60) *", 20)
    assert caret.index("^") == len(excerpt)


def test_a_long_formula_is_shown_around_the_place_with_dots_and_the_caret_still_lines_up():
    formula = "a + " * 40 + "$" + " + b" * 40
    position = formula.index("$")
    excerpt, caret = _lines(formula, position, width=40)
    assert excerpt.startswith("...") and excerpt.endswith("...") and len(excerpt) == 46
    assert excerpt[caret.index("^")] == "$"


def test_a_position_near_either_end_does_not_shift_the_excerpt():
    formula = "x" * 100
    excerpt, caret = _lines(formula, 0, width=40)
    assert not excerpt.startswith("...") and excerpt.endswith("...") and caret.index("^") == 0
    excerpt, caret = _lines(formula, 100, width=40)
    assert excerpt.startswith("...") and not excerpt.endswith("...") and caret.index("^") == len(excerpt)


def test_whitespace_other_than_a_space_is_one_column_each_so_it_cannot_shift_the_caret():
    excerpt, caret = _lines("a\t+\nb $", 6)
    assert excerpt == "a + b $" and excerpt[caret.index("^")] == "$"


def test_a_position_outside_the_formula_is_pulled_in():
    assert _lines("abc", 99)[1] == "   ^" and _lines("abc", -4)[1] == "^"


# --- what the mutation run found missing (slice 3d) -----------------------------------------------------------------------------------------


def test_a_formula_over_a_limit_is_a_problem_of_the_formula():
    result = check_draft(_draft(formula="ramp(psa, hi, 60) * ramp(logp, 5, 2)" + " " * MAX_CHARACTERS))
    assert not result.ok and result.problem == "limit" and result.where == "formula"


def test_a_unit_spelled_another_way_is_said_the_way_it_works_out():
    """`Å*Å` is accepted as `Å^2`, and the line under the formula says what it works out to, not how it was typed."""
    result = check_draft(Draft(label="Area", formula="psa", result_unit="Å*Å", inputs=(InputRow("psa", _TPSA),)))
    assert result.ok and result.worked_out == "Å^2" and result.message == f"{OK}: it works out to Å^2."


def test_every_string_of_a_draft_is_stripped_but_the_formula_which_the_caret_indexes():
    draft = Draft(
        label=" Area ", formula="  psa  ", result_unit=" Å^2 ", inputs=(InputRow(" psa ", _TPSA),),
        constants=(ConstantRow(" hi ", " 140 ", " Å^2 "),), owner=" Alex ", note=" a note \n",
    )
    definition = draft.to_definition()
    assert (definition.label, definition.result_unit, definition.owner, definition.note) == ("Area", "Å^2", "Alex", "a note")
    assert definition.inputs == (("psa", _TPSA),) and definition.constants[0].name == "hi" and definition.constants[0].unit == "Å^2"
    assert definition.formula == "  psa  ", "a position in the formula points into the text as typed"


def test_a_constant_comes_back_to_the_form_as_the_number_it_was():
    definition = _draft(constants=(ConstantRow("hi", "140.123456789", "Å^2"),)).to_definition()
    assert Draft.from_definition(definition).constants[0].value == "140.123456789"


def test_a_suggested_name_is_cut_at_thirty_characters_without_a_trailing_underscore():
    from openchem.domain.score_editor import _slug

    assert _slug("x" * 100) == "x" * 30
    assert _slug("a" * 29 + " b") == "a" * 29, "the cut falls on the separator, which is not kept"


def test_the_excerpt_has_its_full_width_at_the_end_of_a_long_formula():
    excerpt, caret = _lines("x" * 100, 100, width=40)
    assert excerpt == "..." + "x" * 40 and caret.index("^") == len(excerpt)


def test_the_default_excerpt_is_sixty_characters_wide():
    excerpt, _ = _lines("x" * 200, 100)
    assert excerpt == "..." + "x" * 60 + "..."


# --- a default for an input nobody calculated -------------------------------------------------------------------------------------------


def _defaulting(**defaults) -> Draft:
    rows = tuple(InputRow(row.name, row.output_id, str(defaults.get(row.name, ""))) for row in _draft().inputs)
    return _draft(inputs=rows)


def test_a_draft_with_no_default_is_the_first_policy_and_format_one():
    definition = _draft().to_definition()
    assert (definition.on_missing, definition.schema_version, definition.defaults) == ("refuse", 1, ())


def test_a_default_typed_makes_a_definition_with_it_the_second_policy_and_format_two():
    definition = _defaulting(logp="3.5").to_definition()
    assert (definition.on_missing, definition.schema_version, definition.defaults) == ("default", 2, (("logp", 3.5),))
    assert check_draft(_defaulting(logp="3.5")).ok


def test_a_default_is_trimmed_may_be_negative_and_an_empty_one_is_none():
    assert _defaulting(psa=" -2.5 ").to_definition().defaults == (("psa", -2.5),)
    assert _defaulting(psa="   ").to_definition().defaults == ()


@pytest.mark.parametrize("text", ["abc", "1.", ".5", "1,5", "nan", "inf", "1_0", "١٢", "1e999"])
def test_a_default_that_is_not_a_plain_number_is_refused_in_the_inputs_box(text):
    result = check_draft(_defaulting(logp=text))
    assert not result.ok and result.where == "inputs" and result.problem == "inputs" and "default" in result.message and "logp" in result.message


def test_a_definition_and_the_draft_made_from_it_say_the_same_thing_with_defaults_too():
    definition = _defaulting(logp="3.5", psa="0").to_definition(score_id="user.x", created="2026-10-15")
    assert Draft.from_definition(definition).to_definition(score_id="user.x", created="2026-10-15") == definition
    assert [row.default for row in Draft.from_definition(definition).inputs] == ["0", "3.5"]


def test_a_default_for_an_input_whose_name_was_then_changed_is_still_a_default_for_that_row():
    """The default belongs to the row, so renaming the input does not strand it (the definition names inputs, and the row's name is what it is saved under)."""
    renamed = _draft(inputs=(InputRow("psa", _TPSA), InputRow("lp", _LOGP, "3.5")), formula="ramp(psa, hi, 60) * ramp(lp, 5, 2)")
    assert renamed.to_definition().defaults == (("lp", 3.5),) and check_draft(renamed).ok


def test_a_default_with_many_digits_comes_back_to_the_draft_as_typed_to_twelve_figures():
    definition = _defaulting(logp="3.14159265358").to_definition(score_id="user.x", created="2026-10-15")
    assert [row.default for row in Draft.from_definition(definition).inputs] == ["", "3.14159265358"]
