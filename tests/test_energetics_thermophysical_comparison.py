"""The RDX/HMX/TNT/PETN comparison benchmarks/thermophysical/compare_energetics.py runs.

This is NOT a promotion gate for a new calculator -- see docs/CALCULATOR_MATURITY.md for what that
would require. It guards the comparison's own claims: that Joback refuses the two nitramines and is
badly wrong on the two it does run, and that Marrero-Gani's first-order Tm answers all four (with
error sizes recorded, not hidden behind a pass/fail threshold that would overstate confidence four
molecules can't earn).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def compare_module():
    path = ROOT / "benchmarks" / "thermophysical" / "compare_energetics.py"
    spec = importlib.util.spec_from_file_location("compare_energetics", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rows(compare_module):
    return {row["name"]: row for row in compare_module.compare()}


def test_joback_refuses_both_nitramines(rows):
    assert rows["RDX"]["joback_refusal"] == "UNCOVERED_ATOM"
    assert rows["HMX"]["joback_refusal"] == "UNCOVERED_ATOM"


def test_marrero_gani_answers_where_joback_refuses(rows):
    assert rows["RDX"]["marrero_gani_tm_k"] is not None
    assert rows["HMX"]["marrero_gani_tm_k"] is not None
    # Sanity range, not accuracy: a real Kelvin melting point, not a parsing accident.
    assert 250 < rows["RDX"]["marrero_gani_tm_k"] < 700
    assert 250 < rows["HMX"]["marrero_gani_tm_k"] < 700


def test_joback_runs_tnt_and_petn_but_its_freezing_point_is_badly_wrong(rows):
    """Both run (Joback already claims coverage here), but Tf overshoots by 300+ K on both --
    the paper's own 'not accurate... only very approximate' caveat on Tf, worse for nitro esters
    than for whatever compounds proved that average error."""
    assert rows["TNT"]["joback_refusal"] is None
    assert rows["PETN"]["joback_refusal"] is None
    assert abs(rows["TNT"]["joback_error_k"]) > 300
    assert abs(rows["PETN"]["joback_error_k"]) > 300


def test_marrero_gani_first_order_is_much_closer_on_tnt_and_petn(rows):
    assert abs(rows["TNT"]["marrero_gani_error_k"]) < abs(rows["TNT"]["joback_error_k"])
    assert abs(rows["PETN"]["marrero_gani_error_k"]) < abs(rows["PETN"]["joback_error_k"])
    # Recorded, not just "better than Joback": under 60 K on both, first-order only.
    assert abs(rows["TNT"]["marrero_gani_error_k"]) < 60
    assert abs(rows["PETN"]["marrero_gani_error_k"]) < 60


def test_marrero_gani_is_a_real_underestimate_on_the_nitramines(rows):
    """Recorded as a genuine limit, not swept under a threshold: the ring-N + generic-NO2
    decomposition underestimates RDX and HMX by 100-130 K, first-order only. No second-order group
    in Table 7 corrects a nitramine (checked while transcribing it -- literature.toml's note), so
    this is not a missing refinement, it is what the first-order groups alone give for this motif."""
    assert rows["RDX"]["marrero_gani_error_k"] < -80
    assert rows["HMX"]["marrero_gani_error_k"] < -100


def test_hmx_does_have_a_measured_melting_point(rows):
    """Corrected 2026-09-27, at the user's request to verify RDX's mp against a primary source:
    Agrawal (2010) Table 3.6 p. 189 (docs/research/literature.toml's agrawal2010 entry) gives HMX a
    specific, separately-measured mp of 275 C -- not the 'no clean value' this test originally
    asserted from an over-hasty reading of Klapoetke's vaguer prose alone. HMX's gap to its own
    ignition temperature (4-6 C) IS the smallest of the four compounds here, which is what
    Klapoetke's remark was pointing at -- but that is a small gap, not an absent measurement."""
    assert rows["HMX"]["measured_tm_k"] == pytest.approx(548.15)
    assert rows["HMX"]["marrero_gani_error_k"] is not None
