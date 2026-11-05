"""Frozen decision rules of the gnina CNN pose-ranking test."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).parents[1] / "benchmarks" / "docking" / "gnina_core.py"
_spec = importlib.util.spec_from_file_location("gnina_core", _PATH)
core = importlib.util.module_from_spec(_spec)
sys.modules["gnina_core"] = core
_spec.loader.exec_module(core)


def test_training_overlap_is_eighteen_catalog_hits_not_pdbbind_2020():
    assert len(core.TRAINING_OVERLAP) == 18
    assert "1HSG" not in core.TRAINING_OVERLAP
    assert "4PE5" not in core.TRAINING_OVERLAP
    assert core.CROSSDOCKED_UNIQUE_PDB_COUNT == 25752


def test_deciding_ids_drop_overlap_and_keep_four_pe5():
    meas = ["1HSG", "4PE5", "5KIR", "7E2Y"]
    assert core.deciding_ids(meas) == ("1HSG", "4PE5", "7E2Y")


def test_rerank_uses_cnnscore_and_keeps_vina_ties():
    assert core.rerank([0.2, 0.9, 0.9, 0.1]) == [1, 2, 0, 3]


def test_parse_cnn_scores_reads_pose_order():
    text = "CNNscore: 0.10 CNNaffinity: 5.0\nCNNscore: 0.80 CNNaffinity: 6.2\n"
    scores, affs = core.parse_cnn_scores(text)
    assert scores == [0.10, 0.80]
    assert affs == [5.0, 6.2]


def test_version_pin_needs_tag_and_commit():
    assert core.version_is_pinned("gnina v1.3.3 master:6fe1ce2   Built Jun 30 2026.")
    assert not core.version_is_pinned("gnina v1.3.2 master:f23dd2b")


def test_a_gain_promotes_the_correct_pose():
    rec = core.Receptor("X", (6.0, 1.2, 8.0), (0.2, 0.9, 0.1))
    out = core.judge_receptor(rec)
    assert (out.before, out.after, out.promoted) == (False, True, 1)


def test_verdict_boundaries_match_plec():
    def t(gained, lost, unscored=0):
        return core.Tally(29, unscored, gained, lost, 20, 20 + gained - lost)

    assert core.verdict(t(5, 0)) == "PASS"
    assert core.verdict(t(4, 0)) == "NULL"
    assert core.verdict(t(0, 5)) == "HARMFUL"
    assert core.verdict(t(5, 0, unscored=6)) == "INCONCLUSIVE"
    assert core.verdict(t(5, 0), plausible=False) == "INCONCLUSIVE"


def test_sanity_rejects_all_zero_cnn_scores():
    low = [core.Receptor("A", (1.0, 5.0), (0.0, 0.0)), core.Receptor("B", (1.0, 5.0), (0.0, 0.0))]
    ok = [core.Receptor("A", (1.0, 5.0), (0.4, 0.7)), core.Receptor("B", (1.0, 5.0), (0.2, 0.3))]
    assert core.inputs_are_plausible(low) is False
    assert core.inputs_are_plausible(ok) is True
    assert core.all_scores_tied((0.5, 0.5, 0.5)) is True
    assert core.all_scores_tied((0.5, 0.51)) is False


def test_crossdocked_parser_skips_pocket_headers(tmp_path: pathlib.Path):
    text = "--POCKET--\n5kir:rcx,1hsg:foo\n"
    assert core.parse_crossdocked_pdb_ids(text) == {"5KIR", "1HSG"}
