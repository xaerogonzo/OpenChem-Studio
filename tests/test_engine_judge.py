"""Deciding-population and report sentences, with no docking."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).parents[1] / "benchmarks" / "docking"
sys.path.insert(0, str(_PATH))

import engine_core as core  # noqa: E402
import engine_judge as judge  # noqa: E402


def _row(pdb: str, arm: str, seed: int, rmsd: float | None, *, commit: str = "abc") -> dict:
    poses = [] if rmsd is None else [{"rmsd": rmsd}]
    return {"pdb": pdb, "arm": arm, "seed": seed, "poses": poses, "commit": commit, "dirty": False}


def _complete(pdb: str, arm: str, correct: bool, commit: str = "abc") -> list[dict]:
    rmsd = 1.0 if correct else 3.0
    return [_row(pdb, arm, seed, rmsd, commit=commit) for seed in core.SEEDS]


def test_g4_dropped_requires_a_passed_gate(tmp_path: Path):
    (tmp_path / "g4_summary.json").write_text(
        json.dumps({"gate": {"name": "G4", "passed": True, "detail": "ok"}, "dropped": ["4PE5"]}),
        encoding="utf-8",
    )
    assert judge.g4_dropped(tmp_path) == ["4PE5"]
    (tmp_path / "g4_summary.json").write_text(
        json.dumps({"gate": {"passed": False, "detail": "fail"}, "dropped": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="G4 did not pass"):
        judge.g4_dropped(tmp_path)


def test_missing_jobs_are_the_5_by_3_grid():
    deciding = ["7E2Y"]
    rows = _complete("7E2Y", "vina", True)
    missing = judge.missing_jobs(rows, deciding)
    assert len(missing) == core.job_count(1) - 3
    assert ("7E2Y", "vina", 20261029) not in missing
    assert ("7E2Y", "smina-ad4", 20261031) in missing


def test_judge_counts_a_gain_under_majority_and_refuses_an_incomplete_grid():
    deciding = ["7E2Y"]
    rows: list[dict] = []
    rows += _complete("7E2Y", "vina", False)
    rows += _complete("7E2Y", "smina-default", False)
    rows += _complete("7E2Y", "smina-vinardo", True)
    rows += _complete("7E2Y", "smina-dkoes_fast", False)
    rows += _complete("7E2Y", "smina-ad4", False)
    judged = judge.judge(rows, deciding, gates=[])
    assert judged["missing"] == []
    assert judged["candidates"]["smina-vinardo"]["vs_vina"]["tally"].gained == 1
    assert judged["candidates"]["smina-vinardo"]["vs_vina"]["verdict"] == "NULL"
    assert judged["control_is_neutral"] is True
    incomplete = judge.judge(rows[:-1], deciding, gates=[])
    assert incomplete["missing"]
    assert incomplete["overall_verdict"] == "NOT EVALUABLE"


def test_mixed_commits_are_unevaluable():
    rows = _complete("7E2Y", "vina", True, commit="aaa") + _complete(
        "7E2Y", "smina-default", True, commit="bbb"
    )
    assert judge.records_evaluable(rows) == "records from 2 commits"


def test_render_names_the_g4_drop_and_empty_overlap():
    deciding = ["7E2Y"]
    rows: list[dict] = []
    for arm in core.G5_ARMS:
        rows += _complete("7E2Y", arm, True)
    text = judge.render_result(judge.judge(rows, deciding, gates=[]), dropped=["4PE5"], overlap=[])
    assert "G4 dropped 4PE5" in text
    assert "training overlap none" in text
    assert "Overall (gates plus primary): **NULL**." in text
