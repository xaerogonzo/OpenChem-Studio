"""Frozen decision rules for the smina engine pose-ranking test."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).parents[1] / "benchmarks" / "docking" / "engine_core.py"
_spec = importlib.util.spec_from_file_location("engine_core", _PATH)
core = importlib.util.module_from_spec(_spec)
sys.modules["engine_core"] = core
_spec.loader.exec_module(core)


def test_the_seed_majority_rule_needs_two_of_three():
    assert core.arm_correct((True, True, False)) is True
    assert core.arm_correct((True, False, False)) is False
    assert core.arm_correct((True, None, True)) is None


def test_sign_test_values_match_the_preregistration_examples():
    assert core.sign_test_one_sided(6, 0) == pytest.approx(1 / 64)
    assert core.sign_test_one_sided(9, 1) == pytest.approx(11 / 1024)


def test_candidate_verdict_boundaries_use_bonferroni_alpha():
    assert core.candidate_verdict(core.Tally(10, 6, 0, 4)) == "PASS"
    assert core.candidate_verdict(core.Tally(10, 5, 0, 5)) == "NULL"
    assert core.candidate_verdict(core.Tally(10, 9, 1, 0)) == "PASS"
    assert core.candidate_verdict(core.Tally(10, 0, 6, 4)) == "HARMFUL"
    assert core.candidate_verdict(core.Tally(4, 3, 0, 1)) == "NULL"


def test_tally_counts_gained_and_lost_under_the_majority_rule():
    before = core.ReceptorArm("1HSG", "vina", (False, False, False))
    after = core.ReceptorArm("1HSG", "smina-vinardo", (True, True, False))
    pair = core.compare_arms(before, after)
    assert (pair.before, pair.after) == (False, True)
    t = core.tally_pairs([pair])
    assert (t.gained, t.lost) == (1, 0)


def test_g1_tolerance_matches_the_preregistered_ceiling():
    assert core.G1_DISTANCE_TOL == 0.05


def test_g2_same_function_uses_the_preregistered_score_tolerance():
    assert core.G2_SCORE_TOL == 0.01
    assert core.G2_RECEPTOR_COUNT == 5
    ok = core.gate_g2_same_function([0.004, -0.01, 0.0])
    bad = core.gate_g2_same_function([0.004, 0.011])
    empty = core.gate_g2_same_function([])
    assert ok.passed is True
    assert bad.passed is False
    assert empty.passed is False


def test_g1_reproduces_the_survey_within_tolerance():
    recorded = [("1HSG", 0.18), ("7B6W", 1.41)]
    ok = core.gate_g1_reproduces_survey(recorded, [("1HSG", 0.22), ("7B6W", 1.46)])
    bad = core.gate_g1_reproduces_survey(recorded, [("1HSG", 0.18), ("7B6W", 1.47)])
    assert ok.passed is True
    assert bad.passed is False


def test_g4_fails_when_an_arm_docks_too_few():
    assert core.gate_g4_coverage({"vina": 47, "smina-default": 43}).passed is False
    assert core.gate_g4_coverage({"vina": 47, "smina-default": 44}).passed is True


def test_overall_verdict_is_inconclusive_when_a_gate_fails():
    gates = [core.GateResult("G1", False, "bad")]
    assert core.overall_verdict(gates, {"smina-vinardo": "PASS"}) == "INCONCLUSIVE"


def test_g5_min_fraction_pinned_from_pilot():
    assert core.G5_MIN_FRACTION["vina"] == pytest.approx(16 / 17)
    assert core.G5_MIN_FRACTION["smina-ad4"] == pytest.approx(15 / 17)
    assert set(core.G5_MIN_FRACTION) == set(core.G5_ARMS)


def test_g5_gate_uses_per_arm_threshold():
    assert core.gate_g5_for_arm("vina", 16 / 17).passed is True
    assert core.gate_g5_for_arm("vina", 15 / 17).passed is False
    assert core.gate_g5_for_arm("smina-ad4", 15 / 17).passed is True
    assert core.gate_g5_for_arm("smina-ad4", 14 / 17).passed is False


def test_crystal_score_favorable():
    assert core.crystal_score_favorable(-1.0) is True
    assert core.crystal_score_favorable(15.8) is False
    assert core.crystal_score_favorable(None) is False
    assert core.crystal_score_favorable(float("nan")) is False


def test_gate_g5_all_arms_lists_every_arm():
    fractions = {arm: 1.0 for arm in core.G5_ARMS}
    results = core.gate_g5_all_arms(fractions)
    assert len(results) == len(core.G5_ARMS)
    assert all(r.passed for r in results)
