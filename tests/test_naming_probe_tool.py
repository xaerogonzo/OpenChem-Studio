"""tools/naming_probe.py: the round-8 instrument for naming ordinary molecules, kept working (naming round 8, round end)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_probe as probe  # noqa: E402


def test_the_probe_names_a_molecule_and_reports_no_failed_plan_for_a_clean_one():
    name, failures = probe._name_with_failures("CC(=O)C(C)=O")
    assert name == "butane-2,3-dione"
    assert failures == []


def test_the_probe_shows_a_plan_that_failed_to_execute_and_the_engine_silently_left():
    """D-088b (open): the carbamate plan for a carbazate is TRIED, fails ('leaves heavy atoms unclaimed'), and the engine names the next plan. The probe is how that was seen. If the
    carbazate is fixed this test's molecule must change, not be deleted: the point is that a failed top plan is visible."""
    name, failures = probe._name_with_failures("CCOC(=O)NN")
    assert name
    assert any("unclaimed" in f or "owned by no node" in f for f in failures), failures


def test_the_probe_restores_the_engine_after_it_wraps_it():
    from openchem.vendor.iupac_namer import engine

    before = engine.SubstitutivePath.execute
    probe._name_with_failures("CC")
    assert engine.SubstitutivePath.execute is before
