"""Deciding population for the CNNaffinity ranking freeze (no catalog CNN)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "benchmarks" / "docking" / "run_cnn_affinity_test.py"


def test_list_prints_the_frozen_35_and_starts_nothing():
    proc = subprocess.run(
        [sys.executable, str(RUNNER), "list"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    lines = proc.stdout.strip().splitlines()
    plan = json.loads("\n".join(lines[:-1]))
    assert plan["n_ranking_series"] == 77
    assert plan["n_deciding_series"] == 35
    assert plan["n_overlap_series"] == 42
    assert plan["deciding_pdbs"] == ["1ERE", "3HS4", "5I6X", "5TGZ", "6WGT"]
    assert plan["score_only"] is True
    assert plan["cnn_higher_is_better"] is True
    assert "rescore is the first" not in proc.stdout
