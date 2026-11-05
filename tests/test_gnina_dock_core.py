"""Frozen decision rules of the gnina default-dock test."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_DIR = pathlib.Path(__file__).parents[1] / "benchmarks" / "docking"
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rescore = _load("gnina_core", "gnina_core.py")
core = _load("gnina_dock_core", "gnina_dock_core.py")


def test_populations_match_the_closed_cnn_rescore_test():
    assert core.TRAINING_OVERLAP == rescore.TRAINING_OVERLAP
    assert core.deciding_ids(["1HSG", "4PE5", "5KIR"]) == ("1HSG", "4PE5")


def test_default_dock_is_rescore_without_score_only():
    assert core.CNN_SCORING == "rescore"
    assert core.SCORE_ONLY is False
    assert core.NUM_MODES == 9
    assert core.SEED == 20261029
    assert core.EXHAUSTIVENESS == 25


def test_help_default_is_rescore_reads_the_measured_help_line():
    text = "  --cnn_scoring arg (=1)             Amount of CNN scoring: none, rescore (default), refinement\n"
    assert core.help_default_is_rescore(text) is True
    assert core.help_default_is_rescore("no flags here") is False


def test_judge_dock_compares_pose_one_not_a_rerank():
    rec = core.DockReceptor("X", (6.0, 1.2), (1.1, 5.0))
    out = core.judge_dock(rec)
    assert (out.before, out.after) == (False, True)


def test_unscored_gnina_search_is_not_a_gain():
    rec = core.DockReceptor("X", (1.0, 5.0), None)
    out = core.judge_dock(rec)
    assert (out.before, out.after) == (True, None)
    t = core.tally([out])
    assert (t.gained, t.lost, t.unscored) == (0, 0, 1)


def test_verdict_grammar_is_the_cnn_rescore_grammar():
    t = core.Tally(29, 0, 3, 2, 20, 21)
    assert core.verdict(t) == "NULL"
    assert core.verdict(core.Tally(29, 0, 5, 0, 20, 25)) == "PASS"
    assert core.verdict(core.Tally(29, 0, 0, 5, 20, 15)) == "HARMFUL"
