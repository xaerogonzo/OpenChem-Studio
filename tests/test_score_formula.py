"""The grammar, the units and the checked evaluator of a derived score (`docs/DERIVED_SCORES_DESIGN.md` sections 4 and 10).

Each rejection is its own case, because a grammar is only as closed as its worst unlisted construct. The independent oracle is
`test_score_formula_oracle.py`; the rule that nothing here evaluates Python is `test_score_formula_guard.py`.
"""

from __future__ import annotations

import math

import pytest

from openchem.domain.score_formula import (
    FUNCTIONS,
    MAX_CHARACTERS,
    MAX_DEPTH,
    MAX_EXPONENT,
    MAX_INPUTS,
    MAX_NODES,
    Binary,
    Call,
    FormulaError,
    Name,
    Neg,
    Number,
    Power,
    Problem,
    Refusal,
    check_definition,
    check_input_names,
    check_units,
    evaluate,
    infer_unit,
    measure,
    parse_formula,
    render,
    unused_inputs,
)
from openchem.domain.score_units import DIMENSIONLESS, parse_unit

AB = ("a", "b")


def _parse(text: str, names=AB):
    return parse_formula(text, names)


def _value(text: str, **values) -> float:
    return evaluate(_parse(text, list(values)), values)


def _problem(text: str, names=AB) -> FormulaError:
    with pytest.raises(FormulaError) as caught:
        _parse(text, names)
    return caught.value


# --- what the grammar accepts: precedence, associativity, and the tree it makes ----------------------------------------------


def test_multiplication_binds_tighter_than_addition():
    assert _value("1 + 2 * 3") == 7 and _value("(1 + 2) * 3") == 9


def test_subtraction_and_division_are_left_associative():
    assert _value("10 - 3 - 2") == 5 and _value("10 - (3 - 2)") == 9
    assert _value("100 / 10 / 5") == 2 and _value("100 / (10 / 5)") == 50


def test_unary_minus_binds_looser_than_a_power_and_tighter_than_a_product():
    assert _value("-2^2") == -4, "-(2^2), as it is written in algebra"
    assert _value("(-2)^2") == 4
    assert _value("-2 * 3") == -6 and _value("2 * -3") == -6 and _value("2 - -3") == 5


def test_a_power_is_one_literal_whole_number_and_may_be_negative():
    assert _value("2^3") == 8 and _value("2^-2") == 0.25 and _value("2^0") == 1
    assert _value("a^2", a=-3.0) == 9.0 and _value("a^-1", a=4.0) == 0.25


def test_the_tree_is_built_as_written():
    tree = _parse("a + b * 2").tree
    assert tree == Binary("+", Name("a"), Binary("*", Name("b"), Number(2.0)))
    assert _parse("-a^2").tree == Neg(Power(Name("a"), 2))
    assert _parse("max(a, 1)").tree == Call("max", (Name("a"), Number(1.0)))


def test_two_trees_that_differ_only_in_spacing_or_position_are_equal():
    assert _parse("a+b").tree == _parse("  a   +\n b ").tree


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1", 1.0), ("1.5", 1.5), ("0.25", 0.25), ("1e3", 1000.0), ("1E3", 1000.0), ("1.5e-2", 0.015), ("2e+2", 200.0), ("007", 7.0)],
)
def test_numbers_are_decimal_with_an_optional_fraction_and_exponent(text, expected):
    assert _value(text) == expected


@pytest.mark.parametrize("text", ["a + b", "a+b", "a\t+\tb", "a\n+\nb", "  a + b  ", "a +\r\nb"])
def test_whitespace_is_free(text):
    assert _value(text, a=1.0, b=2.0) == 3.0


# --- the rejection matrix: every construct the grammar does not have --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("a.b", "'.' is not allowed"),
        ("a[0]", "'[' is not allowed"),
        ("a[0:1]", "'[' is not allowed"),
        ("'text'", "\"'\" is not allowed"),
        ('"text"', "'\"' is not allowed"),
        ("a == b", "'=' is not allowed"),
        ("a = b", "'=' is not allowed"),
        ("a < b", "'<' is not allowed"),
        ("a > b", "'>' is not allowed"),
        ("a != b", "'!' is not allowed"),
        ("a and b", "unexpected 'and'"),
        ("a if b else a", "unexpected 'if'"),
        ("lambda: a", "':' is not allowed"),
        ("a; b", "';' is not allowed"),
        ("a % b", "'%' is not allowed"),
        ("a // b", "found '/'"),
        ("a ** 2", "expected a number, an input, a function or '(', found '*'"),
        ("a if", "unexpected 'if'"),
        ("__import__('os')", "'_' is not allowed"),
        ("a$", "'$' is not allowed"),
        ("a#comment", "'#' is not allowed"),
        ("a @ b", "'@' is not allowed"),
        ("{a}", "'{' is not allowed"),
        ("a if b", "unexpected 'if'"),
    ],
)
def test_a_construct_the_grammar_does_not_have_is_a_syntax_error(text, why):
    error = _problem(text)
    assert error.problem in (Problem.SYNTAX, Problem.NAME), error.message
    assert why in error.message, error.message


@pytest.mark.parametrize("text", ["abs", "min", "ramp", "ln"])
def test_a_function_name_is_not_a_value(text):
    error = _problem(text)
    assert error.problem is Problem.NAME and "is a function; write" in error.message


@pytest.mark.parametrize("text", ["open(a)", "print(a)", "len(a)", "pow(a, 2)", "round(a)", "float(a)", "int(a)", "sum(a, b)", "getattr(a, b)", "eval(a)", "exec(a)"])
def test_a_call_to_anything_but_the_nine_functions_is_refused(text):
    error = _problem(text)
    assert error.problem is Problem.FUNCTION and "is not a function" in error.message


def test_a_name_that_is_not_an_input_is_refused_and_the_inputs_are_listed():
    error = _problem("a + c")
    assert error.problem is Problem.NAME and "'c' is not one of the inputs (a, b)" in error.message and error.position == 4


def test_a_formula_over_no_inputs_says_so():
    assert "none" in _problem("x", names=()).message


@pytest.mark.parametrize("text", ["A", "Mw", "aB", "a-B"])
def test_names_are_lowercase_and_an_uppercase_letter_says_why(text):
    error = _problem(text)
    assert error.problem is Problem.SYNTAX and "lowercase letters, digits and underscores" in error.message


def test_a_unicode_digit_or_a_look_alike_operator_is_not_a_number_or_an_operator():
    for text in ("٣", "a + ٣", "a − b", "a × b", "a ÷ b", "a ∗ b", "１", "a ⁄ b", "a ˆ 2", "²"):
        error = _problem(text)
        assert error.problem is Problem.SYNTAX and "is not allowed in a formula" in error.message, text


def test_an_empty_formula_is_refused():
    for text in ("", "   ", "\n\t"):
        assert _problem(text).message == "the formula is empty"


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("a +", "found the end of the formula"),
        ("+ a", "found '+'"),
        ("a + * b", "found '*'"),
        ("(a", "a parenthesis is never closed"),
        ("a)", "unexpected ')'"),
        ("()", "found ')'"),
        ("(a + b", "never closed"),
        ("a b", "unexpected 'b'"),
        ("2 a", "unexpected 'a'"),
        ("a 2", "unexpected '2'"),
        ("a, b", "unexpected ','"),
        ("min(a,)", "found ')'"),
        ("min(a b)", "never closed"),
        ("abs(", "found the end of the formula"),
        ("max(a, b", "never closed"),
        ("1.", "a decimal point needs digits after it"),
        ("1.e3", "a decimal point needs digits after it"),
        ("1e", "needs digits after the e"),
        ("1e+", "needs digits after the e"),
        ("a ^", "an exponent is a whole number"),
    ],
)
def test_malformed_text_is_a_syntax_error_that_says_what_was_found(text, why):
    error = _problem(text)
    assert error.problem in (Problem.SYNTAX, Problem.EXPONENT) and why in error.message, error.message


def test_a_leading_decimal_point_is_not_a_number():
    assert "'.' is not allowed" in _problem(".5").message


def test_implicit_multiplication_is_not_in_the_grammar():
    for text in ("2a", "a b", "2(a)", "(a)(b)", "a(b)"):
        assert _problem(text).problem in (Problem.SYNTAX, Problem.FUNCTION, Problem.NAME), text


def test_a_number_out_of_range_is_refused_at_parse_time():
    assert "out of range" in _problem("1e999").message


# --- exponents -----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("text", [f"a^{MAX_EXPONENT + 1}", f"a^-{MAX_EXPONENT + 1}", "a^100", "2^7"])
def test_an_exponent_beyond_the_largest_is_refused(text):
    error = _problem(text)
    assert error.problem is Problem.EXPONENT and f"at most {MAX_EXPONENT}" in error.message


def test_the_largest_exponent_is_accepted_both_ways():
    assert _value(f"2^{MAX_EXPONENT}") == 64 and _value(f"2^-{MAX_EXPONENT}") == 1 / 64


@pytest.mark.parametrize("text", ["a^b", "a^2.5", "a^1e1", "a^(2)", "a^-b", "a^ -", "a^a", "a^sqrt(4)", "a^--2", "a^+2"])
def test_an_exponent_is_a_literal_whole_number_and_nothing_else(text):
    assert _problem(text).problem is Problem.EXPONENT


@pytest.mark.parametrize("text", ["a^2^3", "2^2^2", "a^2^-1", "a^1^1^1"])
def test_a_power_cannot_be_chained_so_no_expression_builds_a_huge_number(text):
    error = _problem(text)
    assert error.problem is Problem.EXPONENT and "use parentheses to power a power" in error.message


def test_nine_to_the_nine_to_the_nine_is_refused_for_the_size_of_its_first_exponent():
    error = _problem("9^9^9")
    assert error.problem is Problem.EXPONENT and f"at most {MAX_EXPONENT}" in error.message


def test_a_power_of_a_parenthesised_power_is_the_written_way():
    assert _value("(2^3)^2") == 64


# --- limits ----------------------------------------------------------------------------------------------------------------------


def test_the_longest_formula_is_accepted_and_one_more_character_is_refused():
    at_limit = "1" + " " * (MAX_CHARACTERS - 1)
    assert _parse(at_limit).tree == Number(1.0)
    error = _problem(at_limit + " ")
    assert error.problem is Problem.LIMIT and f"at most {MAX_CHARACTERS} characters" in error.message


def _sum_of(count: int) -> str:
    return " + ".join(["a"] * count)


def _balanced(leaves: int) -> str:
    """A sum of `leaves` names, as shallow as it can be: n names and n-1 additions are 2n-1 nodes, and a balanced shape keeps the depth small."""
    if leaves == 1:
        return "a"
    half = leaves // 2
    return f"({_balanced(half)}+{_balanced(leaves - half)})"


def test_the_most_nodes_is_accepted_and_one_more_is_refused():
    assert measure(_parse(_balanced(100)).tree)[0] == 199
    assert measure(_parse("-" + _balanced(100)).tree)[0] == MAX_NODES
    error = _problem("--" + _balanced(100))
    assert error.problem is Problem.LIMIT and f"at most {MAX_NODES} nodes" in error.message
    assert _problem(_balanced(101)).problem is Problem.LIMIT


def test_a_long_chain_of_sums_is_refused_for_its_depth_after_it_is_built():
    error = _problem(_sum_of(MAX_DEPTH + 1))
    assert error.problem is Problem.LIMIT and f"nests at most {MAX_DEPTH} levels" in error.message
    assert measure(_parse(_sum_of(MAX_DEPTH - 1)).tree) == (2 * (MAX_DEPTH - 1) - 1, MAX_DEPTH - 1)


def test_the_deepest_tree_is_accepted_and_one_level_more_is_refused():
    assert measure(_parse("-" * (MAX_DEPTH - 1) + "a").tree)[1] == MAX_DEPTH
    error = _problem("-" * MAX_DEPTH + "a")
    assert error.problem is Problem.LIMIT and "levels deep" in error.message


def test_every_parenthesis_counts_as_a_level_so_none_hides_depth():
    assert _parse("(" * (MAX_DEPTH - 1) + "a" + ")" * (MAX_DEPTH - 1)).tree == Name("a")
    assert _problem("(" * MAX_DEPTH + "a" + ")" * MAX_DEPTH).problem is Problem.LIMIT


def test_call_arguments_count_as_a_level():
    nested = "abs(" * (MAX_DEPTH - 1) + "a" + ")" * (MAX_DEPTH - 1)
    assert measure(_parse(nested).tree)[1] == MAX_DEPTH
    assert _problem("abs(" * MAX_DEPTH + "a" + ")" * MAX_DEPTH).problem is Problem.LIMIT


def test_the_limits_hold_before_python_could_run_out_of_stack():
    """500 open parentheses would be a RecursionError if the depth were only checked afterwards."""
    error = _problem("(" * 245 + "a" + ")" * 245)
    assert error.problem is Problem.LIMIT


# --- functions -------------------------------------------------------------------------------------------------------------------


def test_there_are_nine_functions():
    assert set(FUNCTIONS) == {"abs", "min", "max", "clamp", "ramp", "sqrt", "ln", "log10", "exp"}


@pytest.mark.parametrize(
    ("text", "wanted"),
    [
        ("abs()", "found ')'"),
        ("abs(a, b)", "abs takes 1 argument(s), not 2"),
        ("min(a)", "min takes at least 2 argument(s), not 1"),
        ("max(a)", "max takes at least 2 argument(s), not 1"),
        ("clamp(a, 1)", "clamp takes 3 argument(s), not 2"),
        ("clamp(a, 1, 2, 3)", "clamp takes 3 argument(s), not 4"),
        ("ramp(a, 1)", "ramp takes 3 argument(s), not 2"),
        ("sqrt(a, b)", "sqrt takes 1 argument(s), not 2"),
        ("ln(a, b)", "ln takes 1 argument(s), not 2"),
        ("log10(a, b)", "log10 takes 1 argument(s), not 2"),
        ("exp(a, b)", "exp takes 1 argument(s), not 2"),
    ],
)
def test_a_function_takes_exactly_its_arguments(text, wanted):
    assert wanted in _problem(text).message


def test_min_and_max_take_any_number_of_arguments_from_two():
    assert _value("min(3, 1, 2, 5, 4)") == 1 and _value("max(3, 1, 2, 5, 4)") == 5


def test_each_function_gives_its_value():
    assert _value("abs(-3)") == 3 and _value("sqrt(9)") == 3 and _value("exp(0)") == 1
    assert _value("ln(1)") == 0 and _value("log10(1000)") == pytest.approx(3.0)
    assert _value("clamp(5, 0, 3)") == 3 and _value("clamp(-1, 0, 3)") == 0 and _value("clamp(2, 0, 3)") == 2


def test_a_ramp_is_zero_at_a_one_at_b_linear_between_and_clamped_outside():
    assert _value("ramp(1, 1, 5)") == 0 and _value("ramp(5, 1, 5)") == 1 and _value("ramp(3, 1, 5)") == 0.5
    assert _value("ramp(0, 1, 5)") == 0 and _value("ramp(9, 1, 5)") == 1


def test_a_ramp_written_the_other_way_round_is_a_falling_desirability():
    assert _value("ramp(5, 5, 1)") == 0 and _value("ramp(1, 5, 1)") == 1 and _value("ramp(3, 5, 1)") == 0.5
    assert _value("ramp(9, 5, 1)") == 0 and _value("ramp(0, 5, 1)") == 1


def test_a_weighted_sum_of_desirabilities_is_writable():
    """The shape the application's own multiparameter scores (`chem/mpo_scores.py`) have."""
    text = "0.5 * ramp(a, 5, 3) + 0.5 * ramp(b, 0, 90)"
    assert _value(text, a=4.0, b=45.0) == 0.5 * 0.5 + 0.5 * 0.5


# --- inputs ------------------------------------------------------------------------------------------------------------------------


def test_the_inputs_a_formula_uses_are_recorded_in_order_of_first_appearance():
    assert _parse("b + a * b").inputs_used == ("b", "a")
    assert _parse("2 + 3").inputs_used == ()


def test_declared_inputs_the_formula_never_uses_are_found():
    formula = _parse("a + 1")
    assert unused_inputs(formula, AB) == ("b",) and unused_inputs(formula, ["a"]) == ()


@pytest.mark.parametrize(
    ("names", "why"),
    [
        (["a", "a"], "used twice"),
        (["A"], "not a usable input name"),
        (["1a"], "not a usable input name"),
        (["_a"], "not a usable input name"),
        (["a-b"], "not a usable input name"),
        (["a b"], "not a usable input name"),
        ([""], "not a usable input name"),
        (["min"], "name of a function"),
        (["ramp"], "name of a function"),
        ([f"x{i}" for i in range(MAX_INPUTS + 1)], f"at most {MAX_INPUTS} inputs"),
    ],
)
def test_bad_input_names_are_refused(names, why):
    with pytest.raises(FormulaError, match=why) as caught:
        check_input_names(names)
    assert caught.value.problem is Problem.INPUTS


def test_the_most_inputs_are_accepted():
    names = [f"x{i}" for i in range(MAX_INPUTS)]
    assert check_input_names(names) == tuple(names)


# --- units -----------------------------------------------------------------------------------------------------------------------


def _units(**kw):
    return {name: parse_unit(unit) for name, unit in kw.items()}


def _check(text: str, result: str, **units):
    return check_units(_parse(text, list(units)), _units(**units), parse_unit(result))


def test_addition_and_subtraction_need_identical_units():
    assert _check("a + b", "eV", a="eV", b="eV") == parse_unit("eV")
    assert _check("a - b", "eV", a="eV", b="eV") == parse_unit("eV")
    for op, verb in (("+", "add"), ("-", "subtract")):
        with pytest.raises(FormulaError, match=f"cannot {verb} eV and kcal") as caught:
            _check(f"a {op} b", "eV", a="eV", b="kcal")
        assert caught.value.problem is Problem.UNIT


def test_two_energies_in_different_units_are_never_converted():
    with pytest.raises(FormulaError, match="no conversions"):
        _check("a + b", "kJ", a="kcal", b="kJ")


def test_a_percent_and_a_plain_ratio_do_not_add():
    with pytest.raises(FormulaError, match="cannot add % and 1"):
        _check("a + b", "%", a="%", b="1")


def test_multiplication_and_division_combine_exponents():
    assert _check("a * b", "eV*mol", a="eV", b="mol") == parse_unit("eV*mol")
    assert _check("a / b", "kcal/mol", a="kcal", b="mol") == parse_unit("kcal/mol")
    assert _check("a / a", "1", a="eV") == DIMENSIONLESS
    assert _check("a * b", "kcal", a="kcal/mol", b="mol") == parse_unit("kcal")


def test_a_power_multiplies_the_exponents_of_its_base():
    assert _check("a^2", "eV^2", a="eV") == parse_unit("eV^2")
    assert _check("a^-1", "1/eV", a="eV") == parse_unit("1/eV")
    assert _check("a^0", "1", a="eV") == DIMENSIONLESS


def test_a_number_is_dimensionless_so_scaling_keeps_the_unit_and_adding_one_does_not():
    assert _check("2 * a", "eV", a="eV") == parse_unit("eV")
    with pytest.raises(FormulaError, match="cannot add eV and 1"):
        _check("a + 1", "eV", a="eV")


def test_a_negation_and_an_abs_keep_the_unit():
    assert _check("-a", "eV", a="eV") == parse_unit("eV") and _check("abs(a)", "eV", a="eV") == parse_unit("eV")


@pytest.mark.parametrize("function", ["min", "max"])
def test_min_and_max_need_every_argument_in_one_unit(function):
    assert _check(f"{function}(a, b)", "eV", a="eV", b="eV") == parse_unit("eV")
    with pytest.raises(FormulaError, match=f"{function} needs every argument in one unit, found eV, kcal"):
        _check(f"{function}(a, b)", "eV", a="eV", b="kcal")


def test_clamp_needs_all_three_in_one_unit_and_keeps_it():
    assert _check("clamp(a, b, c)", "eV", a="eV", b="eV", c="eV") == parse_unit("eV")
    with pytest.raises(FormulaError, match="clamp needs every argument in one unit"):
        _check("clamp(a, 0, 1)", "eV", a="eV")


def test_a_ramp_needs_x_a_and_b_in_one_unit_and_is_dimensionless():
    assert _check("ramp(a, b, c)", "1", a="eV", b="eV", c="eV") == DIMENSIONLESS
    with pytest.raises(FormulaError, match="ramp needs x, a and b in one unit, found eV, 1, 1"):
        _check("ramp(a, 1, 5)", "1", a="eV")


@pytest.mark.parametrize("function", ["sqrt", "ln", "log10", "exp"])
def test_sqrt_ln_log10_and_exp_need_a_dimensionless_argument_and_give_one(function):
    assert _check(f"{function}(a)", "1", a="1") == DIMENSIONLESS
    with pytest.raises(FormulaError, match=f"{function} needs a dimensionless argument, found eV"):
        _check(f"{function}(a)", "1", a="eV")


def test_a_ratio_of_two_like_quantities_is_dimensionless_and_may_be_logged():
    assert _check("ln(a / b)", "1", a="eV", b="eV") == DIMENSIONLESS


def test_the_unit_the_formula_works_out_to_must_equal_the_declared_one():
    with pytest.raises(FormulaError, match="works out to kcal/mol, and the definition declares eV") as caught:
        _check("a / b", "eV", a="kcal", b="mol")
    assert caught.value.problem is Problem.UNIT and caught.value.position is None


def test_a_unit_error_names_the_part_of_the_formula_and_where_it_is():
    with pytest.raises(FormulaError) as caught:
        _check("2 * (a + b)", "eV", a="eV", b="kcal")
    assert "(in a + b)" in caught.value.message and caught.value.position == 7


def test_infer_unit_agrees_with_check_units():
    formula = _parse("a / b + c", ["a", "b", "c"])
    assert infer_unit(formula.tree, _units(a="kcal", b="mol", c="kcal/mol")) == parse_unit("kcal/mol")


# --- definitions ---------------------------------------------------------------------------------------------------------------


def test_a_definition_is_checked_whole():
    formula = check_definition("a / b", _units(a="kcal", b="mol"), parse_unit("kcal/mol"))
    assert formula.inputs_used == ("a", "b")


def test_a_definition_with_an_unused_input_is_refused_and_says_why():
    with pytest.raises(FormulaError, match=r"the input\(s\) b are declared and not used") as caught:
        check_definition("a + a", _units(a="eV", b="eV"), parse_unit("eV"))
    assert caught.value.problem is Problem.INPUTS


def test_a_definition_is_refused_for_a_name_a_syntax_a_unit_and_a_result_unit_in_turn():
    units = _units(a="eV", b="kcal")
    for text, problem in (("a + c", Problem.NAME), ("a +", Problem.SYNTAX), ("a + b", Problem.UNIT)):
        with pytest.raises(FormulaError) as caught:
            check_definition(text, units, parse_unit("eV"))
        assert caught.value.problem is problem, text
    with pytest.raises(FormulaError) as caught:
        check_definition("a * b", units, parse_unit("eV"))
    assert caught.value.problem is Problem.UNIT


# --- evaluation: the value, and every way it is refused --------------------------------------------------------------------------


def _refused(text: str, **values) -> Refusal:
    with pytest.raises(Refusal) as caught:
        _value(text, **values)
    return caught.value


def test_a_division_by_zero_is_refused_with_the_step_named():
    refusal = _refused("1 / a", a=0.0)
    assert refusal.reason == "division by zero" and refusal.step == "1 / a"
    assert _refused("a / (b - b)", a=1.0, b=2.0).step == "a / (b - b)"
    assert _refused("1 / a", a=-0.0).reason == "division by zero"


def test_a_zero_to_a_negative_power_is_refused():
    assert _refused("a^-2", a=0.0).reason == "zero cannot be raised to -2"


@pytest.mark.parametrize(
    ("text", "values", "reason"),
    [
        ("sqrt(a)", {"a": -1.0}, "the square root of -1.0 is not a real number"),
        ("ln(a)", {"a": 0.0}, "the logarithm of 0.0 is undefined"),
        ("ln(a)", {"a": -3.0}, "the logarithm of -3.0 is undefined"),
        ("log10(a)", {"a": 0.0}, "the logarithm of 0.0 is undefined"),
        ("log10(a)", {"a": -1.0}, "the logarithm of -1.0 is undefined"),
        ("exp(a)", {"a": 1000.0}, "the result is too large to represent"),
        ("a * b", {"a": 1e200, "b": 1e200}, "the result is not a finite number"),
        ("a + b", {"a": 1.7e308, "b": 1.7e308}, "the result is not a finite number"),
        ("a - b", {"a": 1.7e308, "b": -1.7e308}, "the result is not a finite number"),
        ("a^6", {"a": 1e100}, "the result is too large to represent"),
        ("a / b", {"a": 1e300, "b": 1e-300}, "the result is not a finite number"),
        ("clamp(a, 5, 1)", {"a": 3.0}, "the bounds are the wrong way round"),
        ("ramp(a, 2, 2)", {"a": 3.0}, "a ramp needs two different ends"),
    ],
)
def test_every_domain_error_and_overflow_refuses_the_value(text, values, reason):
    assert reason in _refused(text, **values).reason


def test_a_refusal_in_an_inner_step_is_not_hidden_by_an_outer_one_that_would_have_been_finite():
    """`min(1, 1/0)` has a finite value if the division is skipped. It is not skipped."""
    assert _refused("min(1, 1 / a)", a=0.0).reason == "division by zero"
    assert _refused("max(0, ln(a))", a=0.0).step == "ln(a)"


def test_an_overflow_in_an_intermediate_refuses_even_when_the_final_value_would_be_finite():
    assert _refused("1 / (a * a)", a=1e200).reason == "the result is not a finite number"


def test_the_first_refusal_in_left_to_right_order_is_the_one_reported():
    assert _refused("ln(a) + 1 / b", a=0.0, b=0.0).step == "ln(a)"


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_a_non_finite_input_refuses_the_score_and_names_the_input(bad):
    refusal = _refused("a + b", a=1.0, b=bad)
    assert refusal.step == "b" and "is not a finite number" in refusal.reason


@pytest.mark.parametrize("bad", ["1.0", None, True, [1.0]])
def test_an_input_that_is_not_a_number_refuses_the_score(bad):
    formula = _parse("a")
    with pytest.raises(Refusal, match="is not a number"):
        evaluate(formula, {"a": bad})


def test_a_missing_input_refuses_the_score_and_never_becomes_zero():
    formula = _parse("a + b")
    with pytest.raises(Refusal, match="the input b has no value") as caught:
        evaluate(formula, {"a": 1.0})
    assert caught.value.step == "b"


def test_an_input_the_formula_does_not_use_need_not_be_given():
    assert evaluate(_parse("a * 2"), {"a": 4.0, "unrelated": float("nan")}) == 8.0


def test_integers_are_accepted_as_inputs_and_the_value_is_a_float():
    value = evaluate(_parse("a * 2"), {"a": 4})
    assert value == 8.0 and isinstance(value, float)


def test_evaluation_is_double_precision_arithmetic():
    assert _value("0.1 + 0.2") == 0.1 + 0.2 and _value("1 / 3") == 1 / 3


def test_the_same_formula_gives_the_same_value_every_time():
    formula = _parse("ramp(a, 5, 1) * 0.3 + b^2 / 7")
    assert len({evaluate(formula, {"a": 2.5, "b": 3.0}) for _ in range(50)}) == 1


# --- the text of a tree --------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "canonical"),
    [
        ("a+b", "a + b"),
        ("a + (b * 2)", "a + b * 2"),
        ("(a + b) * 2", "(a + b) * 2"),
        ("a - (b - 1)", "a - (b - 1)"),
        ("a - b - 1", "a - b - 1"),
        ("a + (b + 1)", "a + (b + 1)"),
        ("a / (b * 2)", "a / (b * 2)"),
        ("a * b / 2", "a * b / 2"),
        ("-a^2", "-a^2"),
        ("(-a)^2", "(-a)^2"),
        ("-(a + b)", "-(a + b)"),
        ("- - a", "--a"),
        ("a * -b", "a * -b"),
        ("(a + b)^2", "(a + b)^2"),
        ("ramp( a ,1,5 )", "ramp(a, 1, 5)"),
        ("2.50", "2.5"),
        ("1e3", "1000"),
        ("1E-7", "1e-07"),
        ("0.5", "0.5"),
    ],
)
def test_the_canonical_text_has_one_spacing_and_the_fewest_parentheses_that_mean_the_same(text, canonical):
    assert render(_parse(text).tree) == canonical


@pytest.mark.parametrize("text", ["a + b * 2", "(a + b) * 2", "a - (b - 1)", "-a^2", "(-a)^2", "ramp(a, 1, 5) / 3 - b", "max(a, b, 3)^2", "a * -b", "--a"])
def test_the_canonical_text_parses_back_to_the_same_tree(text):
    tree = _parse(text).tree
    assert _parse(render(tree)).tree == tree


# --- the registry of problems is closed ---------------------------------------------------------------------------------------------


def test_every_problem_a_parse_can_report_is_one_of_the_closed_set():
    assert {p.value for p in Problem} == {"syntax", "limit", "name", "function", "exponent", "inputs", "unit"}


def test_a_syntax_error_carries_the_position_of_what_was_wrong():
    assert _problem("a + $").position == 4
    assert _problem("a + * b").position == 4
    assert _problem("(a").position == 2


# --- the numbers the design states, pinned as numbers ---------------------------------------------------------------------------
#
# Every test above reads the limits through their names, so a limit moved by one would move the tests with it. The design
# (`docs/DERIVED_SCORES_DESIGN.md` section 4) states them, and these are what it states.


def test_the_limits_are_the_numbers_the_design_states():
    assert (MAX_CHARACTERS, MAX_NODES, MAX_DEPTH, MAX_EXPONENT, MAX_INPUTS) == (500, 200, 24, 6, 12)


def test_the_formula_depth_limit_is_twenty_four_levels_in_numbers():
    assert measure(_parse("-" * 23 + "a").tree)[1] == 24
    assert _problem("-" * 24 + "a").problem is Problem.LIMIT


def test_twelve_inputs_are_accepted_and_thirteen_are_not_in_numbers():
    assert len(check_input_names([f"x{i}" for i in range(12)])) == 12
    with pytest.raises(FormulaError, match="at most 12 inputs"):
        check_input_names([f"x{i}" for i in range(13)])


def test_a_formula_of_five_hundred_characters_is_accepted_and_five_hundred_and_one_is_not_in_numbers():
    assert _parse("1" + " " * 499).tree == Number(1.0)
    assert _problem("1" + " " * 500).problem is Problem.LIMIT


# --- names ----------------------------------------------------------------------------------------------------------------------------


def test_an_input_name_may_hold_underscores_and_digits():
    assert _value("log_p + x2 + a_1_b", log_p=1.0, x2=2.0, a_1_b=4.0) == 7.0


def test_a_name_may_not_start_with_an_underscore_or_a_digit():
    assert _problem("_a").problem is Problem.SYNTAX
    assert _problem("2a").problem is Problem.SYNTAX


# --- what the three corners the first mutation pass found were ---------------------------------------------------------------------


def test_a_clamp_with_equal_bounds_is_a_constant_and_is_not_refused():
    assert _value("clamp(5, 2, 2)") == 2 and _value("clamp(-5, 2, 2)") == 2


def test_the_depth_of_a_unary_chain_and_of_parentheses_is_refused_where_it_is_met_with_a_position():
    """Refused while parsing, at the character that went too deep, not only after the tree exists: that is what keeps a
    long run of minus signs from recursing far on its way to a refusal."""
    for text in ("-" * MAX_DEPTH + "a", "(" * MAX_DEPTH + "a" + ")" * MAX_DEPTH, "abs(" * MAX_DEPTH + "a" + ")" * MAX_DEPTH):
        error = _problem(text)
        assert error.problem is Problem.LIMIT and error.position is not None, text


def test_a_right_nested_tree_is_measured_by_its_deepest_branch():
    a = Name("a")
    right_deep = Binary("+", a, Binary("+", a, Binary("+", a, a)))
    assert measure(right_deep) == (7, 4)
    left_deep = Binary("+", Binary("+", Binary("+", a, a), a), a)
    assert measure(left_deep) == (7, 4)
    lopsided = Binary("+", Neg(Neg(Neg(a))), a)
    assert measure(lopsided) == (6, 5)


@pytest.mark.parametrize(
    ("tree", "expected"),
    [
        (Number(1.0), (1, 1)),
        (Name("a"), (1, 1)),
        (Neg(Name("a")), (2, 2)),
        (Power(Name("a"), 2), (2, 2)),
        (Power(Neg(Name("a")), 2), (3, 3)),
        (Call("abs", (Name("a"),)), (2, 2)),
        (Call("clamp", (Name("a"), Number(0.0), Number(1.0))), (4, 2)),
        (Call("max", (Name("a"), Power(Name("a"), 2))), (4, 3)),
        (Binary("*", Name("a"), Name("a")), (3, 2)),
    ],
)
def test_every_kind_of_node_is_counted_with_its_children(tree, expected):
    assert measure(tree) == expected
