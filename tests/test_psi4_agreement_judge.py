"""The judge of the Psi4 agreement check (`benchmarks/psi4_agreement/judge.py`, `PLAN.md`): the tolerances from the floors, and each line of the reading rule, on synthetic records.

The rule is tested before any job runs, so it cannot be bent to fit a result: every verdict below is one of the plan's lines, with numbers that make it unambiguous.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).parent.parent / "benchmarks" / "psi4_agreement" / "judge.py"
_spec = importlib.util.spec_from_file_location("psi4_agreement_judge", _PATH)
judge = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = judge  # a dataclass looks its own module up by name
_spec.loader.exec_module(judge)

TOL = judge.tolerances(floor_hf_meh=0.005, floor_dft_meh=0.05, floor_opt_energy_meh=0.02, floor_rmsd_angstrom=0.002)
PAIRS = [("a", "b")]


def _sp(d_meh: float, molecule="a", functional="B3LYP", basis="def2-SVP", orca=-100.0) -> dict:
    return {"molecule": molecule, "functional": functional, "basis": basis, "orca": orca, "psi4": orca + d_meh / 1000.0}


def _grid(d_for) -> list[dict]:
    """Twenty molecules x two combinations, each difference from `d_for(index)`."""
    return [_sp(d_for(i), molecule=f"m{i}", basis=basis) for i in range(20) for basis in ("def2-SVP", "def2-TZVP")]


def _opt(d_meh: float, rmsd: float, molecule="a") -> dict:
    return {"molecule": molecule, "orca": -50.0, "psi4": -50.0 + d_meh / 1000.0, "rmsd": rmsd}


# --- the tolerances ---------------------------------------------------------------------------------------------------------


def test_the_tolerances_are_twice_the_floors_with_a_resolution_below_which_they_do_not_fall():
    assert TOL.hf_meh == pytest.approx(0.01)  # 2 x 0.005 = 0.01, exactly the resolution
    assert TOL.dft_meh == pytest.approx(0.10)
    assert TOL.opt_energy_meh == pytest.approx(0.10)  # max(T_DFT, 2 x 0.02)
    assert TOL.geometry_angstrom == pytest.approx(0.004)
    tiny = judge.tolerances(0.0, 0.0, 0.0, 0.0)
    # the literals of PLAN.md, not the module's own constants: a test that reads the constant cannot see it change
    assert (tiny.hf_meh, tiny.dft_meh, tiny.geometry_angstrom) == (0.01, 0.01, 0.001)
    loud_opt = judge.tolerances(0.0, 0.05, 0.2, 0.0)
    assert loud_opt.opt_energy_meh == pytest.approx(0.4)  # the optimization floor dominates when it is louder


def test_a_relative_tolerance_is_twice_the_class_tolerance_in_kcal():
    assert TOL.relative_kcal("B3LYP") == pytest.approx(2 * 0.10 * judge.KCAL_PER_MEH)
    assert TOL.relative_kcal("HF") == pytest.approx(2 * 0.01 * judge.KCAL_PER_MEH)


def test_a_floor_is_the_largest_absolute_change_and_needs_a_measurement():
    assert judge.floor([0.01, -0.07, 0.03]) == pytest.approx(0.07)
    with pytest.raises(ValueError):
        judge.floor([])


# --- single points ---------------------------------------------------------------------------------------------------------


def test_every_cell_within_tolerance_passes():
    part = judge.judge_single_points(_grid(lambda i: 0.05 if i % 2 else -0.05), TOL)

    assert part.verdict == judge.PASS


def test_a_systematic_offset_above_the_fixed_threshold_fails_even_when_every_cell_agrees_with_the_others():
    """THE VWN TRAP'S SIGNATURE (amended rule): every molecule off by the same large amount, so no cell scatters from its combination's median, but the median is above 0.5 mEh."""
    records = _grid(lambda i: 0.0) + [_sp(0.8, molecule=f"x{i}", functional="PBE0", basis="def2-SVP") for i in range(10)]

    part = judge.judge_single_points(records, TOL)

    assert part.verdict == judge.FAIL
    assert "PBE0 def2-SVP" in part.why[0]


def test_a_steady_cross_engine_difference_below_the_threshold_is_reported_and_not_judged():
    """THE AMENDMENT'S POINT: two programs' B3LYP differ by a steady 0.1 to 0.3 mEh. It is not a FAIL (it was 0.11 to 0.17 in the smoke run), and the scatter around it is still judged."""
    records = [_sp(0.3 + (0.02 if i % 2 else -0.02), molecule=f"m{i}") for i in range(20)]

    assert judge.judge_single_points(records, TOL).verdict == judge.PASS
    assert judge.SYSTEMATIC_MEH == 0.5  # the literal of PLAN.md's amendment


def test_scatter_around_a_steady_offset_is_still_judged_against_t():
    records = [_sp(0.3 + (0.3 if i % 2 else -0.3), molecule=f"m{i}") for i in range(20)]  # +-0.3 around a 0.3 median: 3 T, not 5

    assert judge.judge_single_points(records, TOL).verdict == judge.PARTIAL


def test_a_single_gross_outlier_fails():
    records = _grid(lambda i: 0.0)
    records[3] = _sp(0.6, molecule="outlier")  # beyond 5 x 0.10

    assert judge.judge_single_points(records, TOL).verdict == judge.FAIL


def test_a_few_cells_between_t_and_five_t_without_an_offset_is_partial_below_ninety_five_percent():
    records = _grid(lambda i: 0.2 if i in (1, 2, 3) else 0.0)  # 6 of 40 cells at 2 T: 85% within; the median of each combination is 0

    assert judge.judge_single_points(records, TOL).verdict == judge.PARTIAL


def test_the_hf_class_judges_its_scatter_against_its_own_tighter_tolerance():
    pattern = [0.06 if i % 2 else -0.06 for i in range(10)]  # +-0.06 mEh around a zero median: 6 x T_HF (0.01), 0.6 x T_DFT (0.10)

    assert judge.judge_single_points([_sp(d, molecule=f"m{i}", functional="HF") for i, d in enumerate(pattern)], TOL).verdict == judge.FAIL
    assert judge.judge_single_points([_sp(d, molecule=f"m{i}") for i, d in enumerate(pattern)], TOL).verdict == judge.PASS


# --- relative energies -----------------------------------------------------------------------------------------------------


def test_relative_energies_pass_when_the_two_engines_agree_on_the_difference_whatever_the_totals_do():
    records = [_sp(0.04, molecule="a"), _sp(0.04, molecule="b")]  # both members shifted equally: the difference is untouched

    cells = judge.relative_cells(records, PAIRS)
    assert judge.judge_relative(cells, TOL).verdict == judge.PASS
    assert cells[0]["psi4"] == pytest.approx(cells[0]["orca"])


def test_relative_energies_fail_beyond_five_tolerances():
    records = [_sp(0.0, molecule="a"), _sp(-3.0, molecule="b")]  # a 3 mEh error in one member = 1.9 kcal/mol

    assert judge.judge_relative(judge.relative_cells(records, PAIRS), TOL).verdict == judge.FAIL


def test_a_pair_with_a_missing_member_forms_no_cell_value():
    records = [_sp(0.0, molecule="a"), {"molecule": "b", "functional": "B3LYP", "basis": "def2-SVP", "orca": -100.0, "psi4": None}]

    cells = judge.relative_cells(records, PAIRS)

    assert cells[0]["orca"] is None
    assert judge.judge_relative(cells, TOL).verdict == judge.NOT_EVALUABLE


# --- optimizations ---------------------------------------------------------------------------------------------------------


def test_optimizations_pass_fail_and_partial_by_energy_and_geometry():
    assert judge.judge_optimizations([_opt(0.05, 0.002)], TOL).verdict == judge.PASS
    assert judge.judge_optimizations([_opt(0.05, 0.002), _opt(0.2, 0.002, molecule="b")], TOL).verdict == judge.PARTIAL  # 2 x T_E, under 5 x
    assert judge.judge_optimizations([_opt(0.05, 0.006)], TOL).verdict == judge.PARTIAL  # 1.5 x T_geom
    assert judge.judge_optimizations([_opt(0.05, 0.05)], TOL).verdict == judge.FAIL  # a different structure: 12 x T_geom
    assert judge.judge_optimizations([_opt(2.0, 0.002)], TOL).verdict == judge.FAIL  # 20 x T_E


# --- the whole ---------------------------------------------------------------------------------------------------------------


def _clean_inputs():
    single_points = [_sp(0.01, molecule=m) for m in ("a", "b")]
    return single_points, [_opt(0.01, 0.001)]


def test_the_overall_verdict_is_the_worst_arm():
    single_points, optimizations = _clean_inputs()
    assert judge.judge(single_points, optimizations, PAIRS, TOL)[0] == judge.PASS

    optimizations = [_opt(0.01, 0.05)]  # one arm fails
    assert judge.judge(single_points, optimizations, PAIRS, TOL)[0] == judge.FAIL


def test_a_floor_above_the_ceiling_is_not_evaluable_whatever_the_cells_say():
    loud = judge.tolerances(0.0, 0.4, 0.0, 0.0)  # T_DFT = 0.8 mEh > 0.5
    single_points, optimizations = _clean_inputs()

    verdict, why = judge.judge(single_points, optimizations, PAIRS, loud)

    assert verdict == judge.NOT_EVALUABLE and "ceiling" in why[0]


def test_more_than_five_percent_missing_is_not_evaluable_and_exactly_five_is_not():
    present = [_sp(0.0, molecule=f"m{i}") for i in range(19)]
    missing = [{"molecule": "gone", "functional": "B3LYP", "basis": "def2-SVP", "orca": -100.0, "psi4": None}]
    optimizations = [_opt(0.0, 0.0)]

    pairs = [("m0", "m1")]
    assert judge.judge(present + missing, optimizations, pairs, TOL)[0] == judge.PASS  # 1 of 20 = 5%: allowed, and the rest agree exactly
    assert judge.judge(present[:18] + missing * 2, optimizations, pairs, TOL)[0] == judge.NOT_EVALUABLE  # 2 of 20 = 10%
