"""The judge of the xtb comparison (`benchmarks/xtb_comparison/judge.py`, `PREREGISTRATION.md` section 8): the same-minimum tolerance from the floor, and each line of each claim's reading rule, on synthetic records.

The rule is tested before any job runs, so it cannot be bent to fit a result: every verdict below is one of the preregistration's lines, with numbers that make it unambiguous.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).parent.parent / "benchmarks" / "xtb_comparison" / "judge.py"
_spec = importlib.util.spec_from_file_location("xtb_comparison_judge", _PATH)
judge = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = judge  # a dataclass looks its own module up by name
_spec.loader.exec_module(judge)

FLOORS = judge.Floors(orca_opt_energy_meh=0.02, orca_opt_rmsd_angstrom=0.002)


# --- the floor and the tolerance --------------------------------------------------------------------------------------------


def test_the_same_minimum_tolerance_is_twice_the_floor_and_never_below_its_resolution():
    assert judge.Floors(0.02, 0.002).same_minimum_meh == pytest.approx(0.04)
    assert judge.Floors(0.001, 0.002).same_minimum_meh == pytest.approx(0.01)
    assert judge.Floors(0.0, 0.0).same_minimum_meh == pytest.approx(0.01)


def test_a_floor_that_is_too_loud_breaks_the_ceiling_and_is_named():
    assert FLOORS.broken() is None
    assert "RMSD" in judge.Floors(0.02, 0.05).broken()
    assert "same-minimum tolerance" in judge.Floors(0.3, 0.002).broken()  # 2 x 0.3 = 0.6 mEh > 0.5
    assert judge.Floors(0.25, 0.002).broken() is None  # exactly at the ceiling is allowed


def test_a_floor_needs_a_measurement():
    assert judge.floor([0.1, -0.4, 0.2]) == pytest.approx(0.4)
    with pytest.raises(ValueError):
        judge.floor([])


# --- C1: geometry -----------------------------------------------------------------------------------------------------------


def _geo(rmsds, bond=0.01):
    return [{"molecule": f"m{i}", "heavy_rmsd": r, "bond_mad": bond} for i, r in enumerate(rmsds)]


def test_c1_passes_when_the_structures_overlay_closely():
    verdict = judge.judge_geometry(_geo([0.01, 0.03, 0.04, 0.05, 0.14]), FLOORS)
    assert verdict.verdict == judge.PASS and verdict.numbers["median_heavy_rmsd"] == pytest.approx(0.04)


def test_c1_is_partial_between_the_pass_and_fail_lines():
    # median 0.08 is above the pass line (0.05) and below the fail line (0.10)
    assert judge.judge_geometry(_geo([0.06, 0.08, 0.09]), FLOORS).verdict == judge.PARTIAL
    # a maximum above 0.15 (but below 0.30) also stops a pass
    assert judge.judge_geometry(_geo([0.01, 0.02, 0.03, 0.04, 0.20]), FLOORS).verdict == judge.PARTIAL
    # and so does a bond deviation above 0.015
    assert judge.judge_geometry(_geo([0.01, 0.02, 0.03], bond=0.02), FLOORS).verdict == judge.PARTIAL


def test_c1_fails_on_one_molecule_beyond_the_gross_line_or_a_median_beyond_the_fail_line():
    assert judge.judge_geometry(_geo([0.01, 0.02, 0.03, 0.04, 0.35]), FLOORS).verdict == judge.FAIL
    assert judge.judge_geometry(_geo([0.11, 0.12, 0.13]), FLOORS).verdict == judge.FAIL
    # exactly on the lines is not beyond them
    assert judge.judge_geometry(_geo([0.30, 0.01, 0.01, 0.01, 0.01]), FLOORS).verdict != judge.FAIL


def test_c1_missing_cells_make_it_not_evaluable_beyond_ten_percent():
    rows = _geo([0.01] * 9) + [{"molecule": "gone", "heavy_rmsd": None, "bond_mad": None}]
    assert judge.judge_geometry(rows, FLOORS).verdict == judge.PASS  # exactly 10% is allowed
    rows += [{"molecule": "gone2", "heavy_rmsd": None, "bond_mad": None}]
    assert judge.judge_geometry(rows, FLOORS).verdict == judge.NOT_EVALUABLE
    # a missing REFERENCE job leaves no row at all: the runner counts it
    assert judge.judge_geometry(_geo([0.01] * 9), FLOORS, missing_cells=2, total_cells=11).verdict == judge.NOT_EVALUABLE
    assert judge.judge_geometry([], FLOORS).verdict == judge.NOT_EVALUABLE


def test_c1_is_not_evaluable_when_the_reference_optimizer_floor_is_louder_than_the_ceiling():
    assert judge.judge_geometry(_geo([0.01, 0.02]), judge.Floors(0.02, 0.05)).verdict == judge.NOT_EVALUABLE


# --- C2: relative energies --------------------------------------------------------------------------------------------------


def _pairs(errors, reference=3.0):
    """Pairs whose reference difference is `reference` kcal/mol and whose xtb difference is off by each error."""
    return [{"label": f"p{i}", "xtb_kcal": reference + e, "reference_kcal": reference} for i, e in enumerate(errors)]


def test_c2_tiers_follow_the_mean_absolute_error():
    assert judge.judge_relative(_pairs([0.5, -0.8, 0.9] * 5), 15).verdict == judge.TIER_A
    assert judge.judge_relative(_pairs([1.5, -2.0, 2.5] * 5), 15).verdict == judge.TIER_B
    assert judge.judge_relative(_pairs([4.0, -3.5, 5.0] * 5), 15).verdict == judge.TIER_C
    # the bounds belong to the better tier
    assert judge.judge_relative(_pairs([1.0] * 15), 15).verdict == judge.TIER_A
    assert judge.judge_relative(_pairs([3.0] * 15), 15).verdict == judge.TIER_B


def test_c2_the_ordering_test_lowers_a_tier_by_one_level():
    # small errors, but a third of the well-separated pairs are ordered the wrong way (xtb says the opposite sign)
    wrong = [{"label": f"w{i}", "xtb_kcal": -1.2, "reference_kcal": 1.1} for i in range(5)]
    right = [{"label": f"r{i}", "xtb_kcal": 1.0, "reference_kcal": 1.1} for i in range(10)]
    verdict = judge.judge_relative(wrong + right, 15)
    assert verdict.numbers["ranking_share"] == pytest.approx(10 / 15)
    # MAE = (5 x 2.3 + 10 x 0.1) / 15 = 0.8: tier A by error, lowered to B by the ordering
    assert verdict.verdict == judge.TIER_B
    # tier C cannot go lower
    awful = [{"label": f"a{i}", "xtb_kcal": -5.0, "reference_kcal": 2.0} for i in range(15)]
    assert judge.judge_relative(awful, 15).verdict == judge.TIER_C


def test_c2_exactly_ninety_percent_ordered_keeps_the_tier():
    right = [{"label": f"r{i}", "xtb_kcal": 1.4, "reference_kcal": 1.5} for i in range(9)]
    wrong = [{"label": "w", "xtb_kcal": -1.4, "reference_kcal": 1.5}]
    # MAE = (9 x 0.1 + 2.9) / 10 = 0.38 -> A, and 9/10 is exactly the share needed
    assert judge.judge_relative(right + wrong, 12).verdict == judge.TIER_A


def test_c2_with_no_well_separated_pair_the_tier_stands_and_says_so():
    small = [{"label": f"s{i}", "xtb_kcal": 0.4, "reference_kcal": 0.5} for i in range(15)]
    verdict = judge.judge_relative(small, 15)
    assert verdict.verdict == judge.TIER_A and verdict.numbers["ranking_share"] is None and "could not be applied" in verdict.reason


def test_c2_is_not_evaluable_with_too_few_conformer_pairs_or_too_many_missing_cells():
    assert judge.judge_relative(_pairs([0.1] * 20), 11).verdict == judge.NOT_EVALUABLE
    assert judge.judge_relative(_pairs([0.1] * 20), 12).verdict == judge.TIER_A
    missing = _pairs([0.1] * 18) + [{"label": "x", "xtb_kcal": None, "reference_kcal": 1.0}] * 3
    assert judge.judge_relative(missing, 15).verdict == judge.NOT_EVALUABLE  # 3 of 21 missing
    assert judge.judge_relative(_pairs([0.1] * 18) + missing[-2:], 15).verdict == judge.TIER_A  # 2 of 20: exactly 10%
    assert judge.judge_relative([], 15).verdict == judge.NOT_EVALUABLE


def test_c2_reports_the_signed_error_beside_the_absolute_one():
    verdict = judge.judge_relative(_pairs([1.0, 1.0, 1.0] * 5), 15)
    assert verdict.numbers["mean_signed_error_kcal"] == pytest.approx(1.0) and verdict.numbers["mae_kcal"] == pytest.approx(1.0)


# --- C3: the pre-optimizer ---------------------------------------------------------------------------------------------------


def _pre(n=10, mmff=20, xtb=10, de_meh=0.0, s_mmff=100.0, s_xtb=60.0):
    return [
        {"molecule": f"m{i}", "cycles_mmff": mmff, "cycles_xtb": xtb - (i % 2), "energy_mmff": -100.0, "energy_xtb": -100.0 + de_meh / 1000.0,
         "seconds_mmff": s_mmff, "seconds_xtb_total": s_xtb}
        for i in range(n)
    ]


def test_c3_passes_when_the_xtb_start_saves_cycles_and_time_and_lands_in_the_same_minimum():
    verdict = judge.judge_preoptimizer(_pre(n=12), FLOORS)
    assert verdict.verdict == judge.PASS
    assert verdict.numbers["median_cycle_ratio"] <= 0.8 and verdict.numbers["wilcoxon_p"] < 0.05 and verdict.numbers["same_minimum_share"] == 1.0


def test_c3_fails_when_the_start_changes_where_orca_ends():
    # tolerance is 0.04 mEh; 0.1 mEh apart is a different minimum for every pair
    assert judge.judge_preoptimizer(_pre(de_meh=0.1), FLOORS).verdict == judge.FAIL
    rows = _pre(n=10)
    rows[0]["energy_xtb"] += 0.001  # one of ten differs: 90% is exactly enough
    assert judge.judge_preoptimizer(rows, FLOORS).verdict == judge.PASS
    rows[1]["energy_xtb"] += 0.001  # two of ten: 80% is not
    assert judge.judge_preoptimizer(rows, FLOORS).verdict == judge.FAIL


def test_c3_the_same_minimum_tolerance_comes_from_the_floor():
    rows = _pre(de_meh=0.03)
    assert judge.judge_preoptimizer(rows, judge.Floors(0.02, 0.002)).verdict == judge.PASS  # tolerance 0.04 mEh
    assert judge.judge_preoptimizer(rows, judge.Floors(0.001, 0.002)).verdict == judge.FAIL  # tolerance 0.01 mEh


def test_c3_is_partial_when_it_is_safe_but_saves_nothing():
    # cycles equal in every pair: ratio 1.0, no saving
    rows = _pre(mmff=20, xtb=20)
    for r in rows:
        r["cycles_xtb"] = 20
    verdict = judge.judge_preoptimizer(rows, FLOORS)
    assert verdict.verdict == judge.PARTIAL and verdict.numbers["wilcoxon_p"] == 1.0
    # fewer cycles but slower overall (xtb time included) in most molecules is also not a saving
    slow = _pre(n=12, s_mmff=50.0, s_xtb=80.0)
    assert judge.judge_preoptimizer(slow, FLOORS).verdict == judge.PARTIAL
    # a saving that is not statistically clear (three pairs cannot reach p below 0.05 one-sided)
    assert judge.judge_preoptimizer(_pre(n=3), FLOORS).verdict == judge.PARTIAL


def test_c3_a_small_but_certain_saving_is_not_enough():
    # every pair saves two cycles (ratio 0.9 > 0.8), certainly (p tiny) and in time: still PARTIAL, because the preregistered saving is a fifth
    rows = _pre(n=12, mmff=20)
    for r in rows:
        r["cycles_xtb"] = 18
    verdict = judge.judge_preoptimizer(rows, FLOORS)
    assert verdict.verdict == judge.PARTIAL and verdict.numbers["wilcoxon_p"] < 0.05 and verdict.numbers["median_cycle_ratio"] == pytest.approx(0.9)
    for r in rows:
        r["cycles_xtb"] = 16  # exactly 0.8 is enough
    assert judge.judge_preoptimizer(rows, FLOORS).verdict == judge.PASS


def test_c3_at_least_half_the_molecules_must_be_faster_in_total():
    rows = _pre(n=12)
    for r in rows[:6]:
        r["seconds_xtb_total"] = 120.0  # slower
    assert judge.judge_preoptimizer(rows, FLOORS).verdict == judge.PASS  # exactly half is faster
    rows[6]["seconds_xtb_total"] = 120.0
    assert judge.judge_preoptimizer(rows, FLOORS).verdict == judge.PARTIAL


def test_c3_not_evaluable_on_a_broken_floor_or_too_many_missing_pairs():
    assert judge.judge_preoptimizer(_pre(), judge.Floors(0.02, 0.05)).verdict == judge.NOT_EVALUABLE
    assert judge.judge_preoptimizer(_pre(), judge.Floors(0.4, 0.002)).verdict == judge.NOT_EVALUABLE
    rows = _pre(n=12)
    rows[0]["cycles_xtb"] = None
    assert judge.judge_preoptimizer(rows, FLOORS).verdict == judge.PASS  # 1 of 12 missing
    rows[1]["energy_mmff"] = None
    assert judge.judge_preoptimizer(rows, FLOORS).verdict == judge.NOT_EVALUABLE  # 2 of 12 > 10%
    assert judge.judge_preoptimizer([], FLOORS).verdict == judge.NOT_EVALUABLE


def test_the_wilcoxon_helper_is_one_sided_and_drops_zero_differences():
    assert judge.wilcoxon_less([5, 6, 7, 8, 9, 10], [10, 11, 12, 13, 14, 15]) < 0.05
    assert judge.wilcoxon_less([10, 11, 12, 13, 14, 15], [5, 6, 7, 8, 9, 10]) > 0.9  # the wrong direction is not evidence
    assert judge.wilcoxon_less([4, 4, 4], [4, 4, 4]) == 1.0


def test_there_is_no_overall_verdict():
    assert not hasattr(judge, "judge_all") and not hasattr(judge, "overall")
