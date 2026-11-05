"""Deciding population for the gnina preregistration (no gnina, no docking)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PATH = Path(__file__).parents[1] / "benchmarks" / "docking"
sys.path.insert(0, str(_PATH))

import gnina_core as core  # noqa: E402

SURVEY = _PATH / "artifacts_prep_box" / "results.jsonl"


def test_list_population_is_29_after_crossdocked_holdout():
    rows = [json.loads(line) for line in SURVEY.read_text(encoding="utf-8").splitlines() if line.strip()]
    meas = sorted(
        {r["pdb"] for r in rows if r.get("arm") == "app" and not str(r.get("outcome", "")).startswith("setup")}
    )
    deciding = core.deciding_ids(meas)
    assert len(meas) == 47
    assert len(deciding) == 29
    assert "4PE5" in deciding
    assert "5KIR" not in deciding
    assert set(deciding).isdisjoint(core.TRAINING_OVERLAP)
