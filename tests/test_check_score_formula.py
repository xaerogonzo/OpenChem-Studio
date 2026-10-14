"""The command-line formula checker (`tools/check_score_formula.py`): what it prints and what it exits with.

It is the one thing that reaches `domain/score_formula.py` until the application does, so what it says is what a person trying a formula
sees, and it must never print a number for a definition that was refused.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("check_score_formula", ROOT / "tools" / "check_score_formula.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(tool, capsys, *argv):
    code = tool.main(list(argv))
    return code, capsys.readouterr().out


def test_a_good_definition_with_values_prints_the_formula_the_unit_and_the_value(tool, capsys):
    code, out = _run(tool, capsys, "2*a+b", "--input", "a=eV", "--input", "b=eV", "--result", "eV", "--value", "a=1.5", "--value", "b=3")
    assert code == 0
    assert "formula: 2 * a + b" in out and "unit:    eV" in out and "value:   6.0 eV" in out


def test_a_good_definition_without_values_is_only_checked(tool, capsys):
    code, out = _run(tool, capsys, "a / b", "--input", "a=kcal", "--input", "b=mol", "--result", "kcal/mol")
    assert code == 0 and "definition accepted" in out and "value:" not in out


def test_a_unit_mismatch_is_refused_and_no_value_is_printed(tool, capsys):
    code, out = _run(tool, capsys, "a + b", "--input", "a=eV", "--input", "b=kcal", "--result", "eV", "--value", "a=1", "--value", "b=2")
    assert code == 1 and "refused [unit]" in out and "no conversions" in out and "value:" not in out


def test_a_syntax_error_names_its_position(tool, capsys):
    code, out = _run(tool, capsys, "a + $", "--input", "a=1", "--result", "1")
    assert code == 1 and "refused [syntax]" in out and "(at character 4)" in out


def test_an_unused_input_is_refused(tool, capsys):
    code, out = _run(tool, capsys, "a", "--input", "a=1", "--input", "b=1", "--result", "1")
    assert code == 1 and "refused [inputs]" in out and "b are declared and not used" in out


def test_a_refused_value_says_which_step(tool, capsys):
    code, out = _run(tool, capsys, "1 / b", "--input", "b=1", "--result", "1", "--value", "b=0")
    assert code == 1 and "refused: division by zero (in 1 / b)" in out


def test_a_missing_value_is_refused_and_never_zero(tool, capsys):
    code, out = _run(tool, capsys, "a + b", "--input", "a=1", "--input", "b=1", "--result", "1", "--value", "a=1")
    assert code == 1 and "the input b has no value" in out


def test_a_bad_unit_or_a_malformed_argument_is_refused(tool, capsys):
    assert _run(tool, capsys, "a", "--input", "a=lightyear", "--result", "1")[0] == 1
    assert _run(tool, capsys, "a", "--input", "a", "--result", "1")[0] == 1
    assert _run(tool, capsys, "a", "--input", "a=1", "--result", "1", "--value", "a=notanumber")[0] == 1


def test_a_formula_starting_with_a_minus_is_given_after_a_double_dash(tool, capsys):
    code, out = _run(tool, capsys, "--input", "x=1", "--result", "1", "--value", "x=3", "--", "-x^2")
    assert code == 0 and "value:   -9.0 1" in out
