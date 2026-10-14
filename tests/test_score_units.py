"""Units for a derived score (`docs/DERIVED_SCORES_DESIGN.md` section 4): strict, opaque, no conversions."""

from __future__ import annotations

import pytest

from openchem.domain.score_units import DIMENSIONLESS, MAX_UNIT_EXPONENT, SYMBOLS, Unit, UnitError, parse_unit


def _u(text: str) -> Unit:
    return parse_unit(text)


# --- what a unit is ---------------------------------------------------------------------------------------------------------


def test_dimensionless_is_the_empty_product_and_is_written_1():
    assert DIMENSIONLESS.is_dimensionless and str(DIMENSIONLESS) == "1" and _u("1") == DIMENSIONLESS


@pytest.mark.parametrize("text", ["eV", "kcal/mol", "mg/mL", "1/eV", "eV^2", "kcal*mol", "eV^2/mol^3", "%", "Å", "ppm"])
def test_a_unit_prints_back_as_the_canonical_text_that_parses_to_the_same_unit(text):
    unit = _u(text)
    assert _u(str(unit)) == unit


def test_equality_is_structural_so_the_order_of_a_product_does_not_matter():
    assert _u("kcal*mol") == _u("mol*kcal") and str(_u("mol*kcal")) == "kcal*mol"


def test_the_canonical_text_puts_the_numerator_first_and_a_lone_denominator_over_1():
    assert str(_u("mol^-1")) == "1/mol" and str(_u("kcal/mol")) == "kcal/mol" and str(_u("eV^2/mol")) == "eV^2/mol"


def test_a_unit_with_a_zero_exponent_part_is_not_representable():
    with pytest.raises(ValueError):
        Unit((("eV", 0),))
    with pytest.raises(ValueError):
        Unit((("mol", 1), ("eV", 1)))  # not in canonical order


def test_unit_of_drops_zeros_and_sorts():
    assert Unit.of({"mol": 1, "eV": 0, "kcal": -1}).parts == (("kcal", -1), ("mol", 1))


# --- the symbols are opaque and unrelated -----------------------------------------------------------------------------------


def test_two_energy_units_are_two_different_units_and_nothing_converts_them():
    assert _u("eV") != _u("kcal") != _u("kJ") != _u("Hartree")


def test_a_percent_is_not_dimensionless_and_a_ratio_is_not_a_percent():
    assert _u("%") != DIMENSIONLESS and _u("%").parts == (("%", 1),)


def test_an_unapproved_symbol_is_refused_and_the_approved_ones_are_named():
    with pytest.raises(UnitError, match="'lightyear' is not an approved unit symbol"):
        _u("lightyear")
    with pytest.raises(UnitError, match="eV"):
        _u("kcal/furlong")


def test_the_closed_list_can_be_narrowed_by_the_caller():
    assert parse_unit("eV", symbols={"eV"}) == _u("eV")
    with pytest.raises(UnitError):
        parse_unit("kcal", symbols={"eV"})


def test_every_starter_symbol_parses():
    for symbol in SYMBOLS:
        assert parse_unit(symbol).parts == ((symbol, 1),)


# --- arithmetic ---------------------------------------------------------------------------------------------------------------


def test_multiplying_adds_exponents_and_dividing_subtracts_them():
    assert _u("kcal/mol") * _u("mol") == _u("kcal")
    assert _u("kcal") / _u("kcal") == DIMENSIONLESS
    assert _u("eV") * _u("eV") == _u("eV^2")
    assert _u("eV") / _u("mol") == _u("eV/mol")


def test_a_power_multiplies_the_exponents_and_a_zero_power_is_dimensionless():
    assert _u("eV/mol") ** 2 == _u("eV^2/mol^2")
    assert _u("eV") ** 0 == DIMENSIONLESS
    assert _u("eV") ** -1 == _u("1/eV")


# --- what is refused ------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("", "write 1 for a dimensionless unit"),
        ("   ", "write 1 for a dimensionless unit"),
        ("eV/mol/g", "at most one '/'"),
        ("(eV)", "no parentheses"),
        ("eV/(mol*g)", "no parentheses"),
        ("eV*", "empty factor"),
        ("*eV", "empty factor"),
        ("eV**2", "empty factor"),
        ("eV/", "empty factor"),
        ("eV/1", "dividing by 1"),
        ("eV^x", "must be a whole number"),
        ("eV^1.5", "must be a whole number"),
        ("eV^0", "non-zero whole number"),
        (f"eV^{MAX_UNIT_EXPONENT + 1}", "non-zero whole number"),
        ("eV*1", "'1' is not an approved unit symbol"),
    ],
)
def test_a_badly_written_unit_is_refused_with_its_reason(text, why):
    with pytest.raises(UnitError, match=why):
        _u(text)


def test_an_empty_unit_never_means_dimensionless_by_accident():
    """The application's own results write "" for no unit. A definition must say 1."""
    with pytest.raises(UnitError):
        _u("")


def test_the_largest_exponent_is_accepted_and_a_negative_one_too():
    assert _u(f"eV^{MAX_UNIT_EXPONENT}").parts == (("eV", MAX_UNIT_EXPONENT),)
    assert _u(f"eV^-{MAX_UNIT_EXPONENT}").parts == (("eV", -MAX_UNIT_EXPONENT),)


def test_whitespace_around_parts_is_ignored():
    assert _u("  kcal / mol ") == _u("kcal/mol") and _u("eV ^ 2") == _u("eV^2")
