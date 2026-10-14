"""Named constants of a derived score: the strict alternative to a bare number (`domain/score_constants.py`).

A bare number takes the unit of what it is combined with, which makes thresholds writable and loses two things. These tests are about those two:
a threshold in the wrong unit IS caught when it is a named constant, and a logarithm of a dimensioned quantity CAN be written when it is divided
by a constant that carries the unit. They also hold the constants' own rules (a usable name, a finite value, a unit written correctly, a name
nothing else has, at most `MAX_CONSTANTS`) and that a constant nothing uses is refused like an input nothing uses.
"""

from __future__ import annotations

import math

import pytest

from openchem.domain.score_constants import (
    MAX_CONSTANTS,
    Constant,
    check_constants,
    constant_values,
)
from openchem.domain.score_formula import (
    FormulaError,
    Problem,
    check_definition,
    evaluate,
)
from openchem.domain.score_outputs import check_inputs, values_by_name
from openchem.domain.score_units import DIMENSIONLESS, parse_unit

_INPUTS = [("psa", "descriptor:tpsa"), ("mw", "descriptor:mol_wt"), ("logp", "descriptor:mol_logp")]


def _define(text, constants, inputs=_INPUTS, result="1"):
    units = check_inputs(inputs, constants)
    return check_definition(text, units, parse_unit(result))


# --- what a constant buys --------------------------------------------------------------------------------------------------------


def test_a_threshold_in_the_right_unit_is_accepted_and_evaluates():
    constants = [Constant("hi", 140, "Å^2"), Constant("lo", 60, "Å^2")]
    formula = _define("ramp(psa, hi, lo)", constants, _INPUTS[:1])
    values = values_by_name(_INPUTS[:1], {"descriptor:tpsa": (100.0, "Å²")}, constants)
    assert evaluate(formula, values) == pytest.approx(0.5)


def test_a_threshold_in_the_wrong_unit_is_refused_though_a_bare_number_would_pass():
    """The check a bare number could never make: the same threshold, 140, written as a bare number is accepted (it adopts the unit)."""
    _define("ramp(psa, 140, 60)", [], _INPUTS[:1])
    with pytest.raises(FormulaError, match="ramp needs x, a and b in one unit, found Å\\^2, nm\\^2, Å\\^2") as caught:
        _define("ramp(psa, hi, lo)", [Constant("hi", 140, "nm^2"), Constant("lo", 60, "Å^2")], _INPUTS[:1])
    assert caught.value.problem is Problem.UNIT


def test_a_dimensionless_constant_does_not_adopt_a_unit_either():
    with pytest.raises(FormulaError, match="cannot add g/mol and 1"):
        _define("mw + weight", [Constant("weight", 5, "1")], _INPUTS[1:2], "g/mol")


def test_a_logarithm_of_a_dimensioned_quantity_is_writable_with_a_constant_that_carries_the_unit():
    with pytest.raises(FormulaError, match="log10 needs a dimensionless argument, found g/mol"):
        _define("log10(mw / 100)", [], _INPUTS[1:2])
    constants = [Constant("one", 1, "g/mol")]
    formula = _define("log10(mw / one)", constants, _INPUTS[1:2])
    values = values_by_name(_INPUTS[1:2], {"descriptor:mol_wt": (180.0, "g/mol")}, constants)
    assert evaluate(formula, values) == pytest.approx(math.log10(180.0))


def test_a_constant_scales_like_any_other_name():
    constants = [Constant("k", 2.5, "1")]
    formula = _define("k * logp", constants, _INPUTS[2:])
    assert evaluate(formula, values_by_name(_INPUTS[2:], {"descriptor:mol_logp": (2.0, "")}, constants)) == pytest.approx(5.0)


# --- the units come back as the language's units ------------------------------------------------------------------------------------


def test_check_constants_returns_each_constants_unit():
    units = check_constants([Constant("a", 1, "eV"), Constant("b", 2, "kcal/mol"), Constant("c", 3, "1")], [])
    assert units == {"a": parse_unit("eV"), "b": parse_unit("kcal/mol"), "c": DIMENSIONLESS}


def test_constant_values_are_floats_in_order():
    assert constant_values([Constant("a", 1, "eV"), Constant("b", 2.5, "1")]) == {"a": 1.0, "b": 2.5}
    assert all(isinstance(v, float) for v in constant_values([Constant("a", 1, "eV")]).values())


def test_no_constants_changes_nothing():
    assert check_inputs(_INPUTS[:1]) == check_inputs(_INPUTS[:1], [])
    assert values_by_name(_INPUTS[:1], {"descriptor:tpsa": (1.0, "Å²")}) == {"psa": 1.0}


# --- what a constant may be ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Hi", "1x", "a b", "", "x-y", "é", "ramp", "min", "log10"])
def test_a_constant_name_follows_the_rule_for_input_names(name):
    with pytest.raises(FormulaError) as caught:
        check_constants([Constant(name, 1, "1")], [])
    assert caught.value.problem is Problem.CONSTANT and f"constant {name!r}" in caught.value.message


def test_a_name_an_input_has_is_refused():
    with pytest.raises(FormulaError, match="already used by an input") as caught:
        check_inputs(_INPUTS[:1], [Constant("psa", 1, "1")])
    assert caught.value.problem is Problem.CONSTANT


def test_a_name_an_earlier_constant_has_is_refused():
    with pytest.raises(FormulaError, match="already used by another constant"):
        check_constants([Constant("a", 1, "1"), Constant("a", 2, "1")], [])


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True, False, "5", None, [1.0], 1 + 2j])
def test_a_value_that_is_not_a_finite_number_is_refused(value):
    with pytest.raises(FormulaError, match="must be a finite number") as caught:
        check_constants([Constant("a", value, "1")], [])
    assert caught.value.problem is Problem.CONSTANT


@pytest.mark.parametrize("value", [0, 0.0, -3, 1e300, -1e-300, 7])
def test_any_finite_number_is_a_value(value):
    assert check_constants([Constant("a", value, "1")], []) == {"a": DIMENSIONLESS}


@pytest.mark.parametrize(
    "unit, why",
    [
        ("", "write 1 for a dimensionless unit"),
        ("furlong", "not an approved unit symbol"),
        ("eV/kcal/mol", "at most one '/'"),
        ("eV^0", "non-zero whole number"),
        ("(eV)", "no parentheses"),
        ("eV*", "empty factor"),
    ],
)
def test_a_unit_that_is_not_written_correctly_is_refused_with_the_units_own_reason(unit, why):
    with pytest.raises(FormulaError, match=why) as caught:
        check_constants([Constant("a", 1, unit)], [])
    assert caught.value.problem is Problem.CONSTANT and "constant 'a'" in caught.value.message


def test_at_most_the_limit_is_accepted_and_one_more_is_refused():
    names = [f"c{i}" for i in range(MAX_CONSTANTS + 1)]
    assert len(check_constants([Constant(n, 1, "1") for n in names[:MAX_CONSTANTS]], [])) == MAX_CONSTANTS
    with pytest.raises(FormulaError, match=f"at most {MAX_CONSTANTS} constants, not {MAX_CONSTANTS + 1}"):
        check_constants([Constant(n, 1, "1") for n in names], [])


def test_the_limit_is_twelve_and_is_separate_from_the_inputs_limit():
    assert MAX_CONSTANTS == 12


def test_constants_do_not_count_against_the_inputs_limit():
    from openchem.domain.score_formula import MAX_INPUTS

    many = [(f"x{i}", e.output_id) for i, e in enumerate(_distinct_endpoint_entries()[:MAX_INPUTS])]
    constants = [Constant(f"k{i}", 1, "1") for i in range(MAX_CONSTANTS)]
    assert len(check_inputs(many, constants)) == MAX_INPUTS + MAX_CONSTANTS


def _distinct_endpoint_entries():
    from openchem.domain.score_outputs import APPROVED

    seen, chosen = set(), []
    for entry in APPROVED:
        if entry.endpoint not in seen:
            seen.add(entry.endpoint)
            chosen.append(entry)
    return chosen


# --- a constant nothing uses is refused ----------------------------------------------------------------------------------------------


def test_a_constant_the_formula_never_uses_is_refused_like_an_unused_input():
    with pytest.raises(FormulaError, match="declared and not used") as caught:
        _define("logp / 2", [Constant("spare", 1, "1")], _INPUTS[2:])
    assert caught.value.problem is Problem.INPUTS and "spare" in caught.value.message


def test_an_unknown_name_is_still_unknown_when_constants_exist():
    with pytest.raises(FormulaError) as caught:
        _define("logp + nothing", [Constant("k", 1, "1")], _INPUTS[2:])
    assert caught.value.problem is Problem.NAME
