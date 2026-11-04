"""Recorded survey distances used by the G1 gate."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_PATH = pathlib.Path(__file__).parents[1] / "benchmarks" / "docking"
sys.path.insert(0, str(_PATH))

import engine_g1_survey as g1  # noqa: E402
import engine_pilot as pilot  # noqa: E402


def _load_run_engine_test():
    spec = importlib.util.spec_from_file_location(
        "run_engine_test", _PATH / "run_engine_test.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_recorded_g1_matches_measurable_catalog():
    run = _load_run_engine_test()
    recorded = g1.recorded_g1_distances()
    measurable = run.measurable_receptors()
    assert set(recorded) == set(measurable)
    assert len(recorded) == 47


def test_recorded_g1_uses_the_pinned_seed():
    for row in pilot.recorded_rows():
        if row.get("arm") != pilot.ARM_NAME:
            continue
        if row["pdb"] not in g1.recorded_g1_distances():
            continue
        assert row.get("seed") == g1.G1_SEED
