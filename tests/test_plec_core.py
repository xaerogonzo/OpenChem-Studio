"""The frozen decision rules of the PLECscore pose-ranking test."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).parents[1] / "benchmarks" / "docking" / "plec_core.py"
_spec = importlib.util.spec_from_file_location("plec_core", _PATH)
core = importlib.util.module_from_spec(_spec)
sys.modules["plec_core"] = core
_spec.loader.exec_module(core)


def _outcome(before, after):
    return core.Outcome("X", before, after, 0)


def test_rerank_puts_the_highest_predicted_affinity_first_and_keeps_ties_in_vina_order():
    assert core.rerank([6.0, 7.5, 7.5, 5.0]) == [1, 2, 0, 3]


def test_the_cutoff_is_inclusive():
    assert core.top_is_correct([2.0, 9.0], [0, 1]) is True
    assert core.top_is_correct([2.01, 9.0], [0, 1]) is False
    assert core.top_is_correct([None, 1.0], [0, 1]) is None


def test_a_receptor_gains_when_the_rescorer_promotes_the_correct_pose():
    receptor = core.Receptor("X", (6.0, 1.2, 8.0), (5.0, 7.0, 4.0))
    outcome = core.judge_receptor(receptor)
    assert (outcome.before, outcome.after, outcome.promoted) == (False, True, 1)


def test_a_receptor_that_could_not_be_rescored_has_no_after():
    outcome = core.judge_receptor(core.Receptor("X", (1.0, 6.0), None))
    assert outcome.before is True and outcome.after is None


def test_sign_test_values():
    assert core.sign_test_one_sided(5, 0) == pytest.approx(1 / 32)
    assert core.sign_test_one_sided(4, 0) == pytest.approx(1 / 16)
    assert core.sign_test_one_sided(0, 0) == 1.0
    assert core.sign_test_one_sided(7, 2) == pytest.approx(46 / 512)


def test_tally_counts_gains_losses_and_unscored():
    t = core.tally([
        _outcome(False, True), _outcome(True, False), _outcome(True, True),
        _outcome(False, False), _outcome(True, None), _outcome(None, None),
    ])
    assert (t.measured, t.unscored, t.gained, t.lost) == (5, 1, 1, 1)
    assert (t.before_correct, t.after_correct) == (2, 2)


def _t(gained, lost, unscored=0):
    return core.Tally(39, unscored, gained, lost, 30, 30 + gained - lost)


def test_the_verdict_boundaries():
    assert core.verdict(_t(5, 0)) == "PASS"  # p = 1/32
    assert core.verdict(_t(4, 0)) == "NULL"  # p = 1/16 misses alpha
    assert core.verdict(_t(3, 0)) == "NULL"
    assert core.verdict(_t(6, 3)) == "NULL"  # net 3 but p = 0.254
    assert core.verdict(_t(0, 5)) == "HARMFUL"
    assert core.verdict(_t(2, 2)) == "NULL"
    assert core.verdict(_t(5, 0, unscored=6)) == "INCONCLUSIVE"
    assert core.verdict(_t(5, 0, unscored=5)) == "PASS"


def test_implausible_predicted_affinities_make_the_verdict_inconclusive():
    low = [core.Receptor("A", (1.0, 5.0), (1.0, 2.0)), core.Receptor("B", (1.0, 5.0), (0.5, 3.9))]
    ok = [core.Receptor("A", (1.0, 5.0), (5.0, 6.0)), core.Receptor("B", (1.0, 5.0), (4.0, 7.0))]
    assert core.inputs_are_plausible(low) is False
    assert core.inputs_are_plausible(ok) is True
    assert core.inputs_are_plausible([core.Receptor("A", (1.0,), None)]) is False
    assert core.verdict(_t(5, 0), plausible=False) == "INCONCLUSIVE"


def test_the_trained_on_list_is_the_eight_entries_found_in_the_training_ids():
    assert core.TRAINED_ON == {"1HSG", "3EML", "3HS4", "4DJH", "4EA3", "4M48", "4N6H", "5C1M"}
