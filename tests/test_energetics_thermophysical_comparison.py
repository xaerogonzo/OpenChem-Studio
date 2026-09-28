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


# --- Track 1: the diagnostic extension from tests/fixtures/census_panel.toml -------------------------
# Not a blind holdout -- see this file's and compare_energetics.py's module docstrings. These tests guard
# the extension's own claims: clean decompositions where expected, genuine refusals where expected, and
# that a decomposition or "estimated" transition is never silently scored as a melting point.


def test_every_diagnostic_row_is_covered_by_the_regression_corpus(compare_module):
    """Every row in compare_energetics.py's diagnostic set really does come from census_panel.toml --
    guards against silently drifting away from the pre-existing, non-cherry-picked corpus the plan
    calls for reusing."""
    import tomllib

    panel = tomllib.loads((ROOT / "tests" / "fixtures" / "census_panel.toml").read_text(encoding="utf-8"))
    panel_ids = {row["id"] for row in panel["row"]}
    diagnostic_names = {
        name for name, spec in compare_module.MOLECULES.items() if spec["role"] == "diagnostic"
    }
    assert diagnostic_names <= panel_ids


def test_four_diagnostic_rows_decompose_cleanly(rows):
    for name in ("dinitrodiazetidine", "tetryl", "tatb", "nitroglycerin"):
        assert rows[name]["groups"] is not None, name


def test_nitroguanidine_and_ammonium_nitrate_refuse(rows):
    """Genuine coverage gaps (a guanidine core; an ionic inorganic salt), not missing SMARTS patterns --
    tests/test_energetics_groups.py checks the atom-level reason directly."""
    assert rows["nitroguanidine"]["groups"] is None
    assert rows["ammonium_nitrate"]["groups"] is None


def test_tatb_is_never_scored_numerically(rows):
    """TATB has no measured Tm (Klapoetke: its melting point is an unreached ESTIMATE, not a
    measurement) -- it must stay out of the scored set rather than being silently compared against
    Joback's Tf or Marrero-Gani's estimate as if a real measurement existed."""
    assert rows["tatb"]["scoreable"] is False


def test_nitroglycerin_is_now_scored_against_a_found_measured_value(rows):
    """A later session found nitroglycerin's Tm (285.5 K, NIST WebBook citing Acree 1991) where the
    original pass had come up empty -- Marrero-Gani overestimates it by +19.7 K, a smaller error than
    PETN's (the other nitrate ester in this corpus), and the row is now scoreable rather than deferred."""
    assert rows["nitroglycerin"]["scoreable"] is True
    assert rows["nitroglycerin"]["marrero_gani_error_k"] == pytest.approx(19.7, abs=0.1)


def test_tetryls_error_is_positive_unlike_the_ring_nitramines(rows):
    """Track 2b's actual descriptive finding: tetryl is labelled 'nitramine' in census_panel.toml (for
    a different reason -- it was chosen to test that an aromatic N-N doesn't get mistaken for a ring
    N-N), but its Marrero-Gani error runs the OPPOSITE direction from RDX/HMX/dinitrodiazetidine's
    consistent underestimate, and closer in sign and size to the nitroaromatic stratum (TNT). This is
    exactly why 'nitramine' as a single reporting stratum is misleading here: tetryl's N-NO2 is
    aromatic-carbon-attached, not ring-nitrogen-attached, and behaves like a different chemical class
    for this property. Recorded descriptively, not explained -- see the module docstring's caution
    against inferring a causal correction from a handful of confounded points."""
    assert rows["tetryl"]["marrero_gani_error_k"] > 0
    assert rows["RDX"]["marrero_gani_error_k"] < 0
    assert rows["HMX"]["marrero_gani_error_k"] < 0


def test_stratified_report_separates_coverage_from_accuracy(compare_module, rows):
    report = compare_module.stratified_report(list(rows.values()))
    # "energetic" stratum (nitroguanidine, ammonium_nitrate): fully refused, zero scoreable -- coverage
    # failure, not an accuracy number of exactly 0 that would misleadingly look like a perfect score.
    assert report["energetic"]["total"] == 2
    assert report["energetic"]["mg_covered"] == 0
    assert report["energetic"]["mg_scoreable"] == 0
    assert report["energetic"]["mg_errors"] == []
    # nitramine stratum has 4 rows but only 3 scoreable (dinitrodiazetidine has no measured Tm yet).
    assert report["nitramine"]["total"] == 4
    assert report["nitramine"]["mg_scoreable"] == 3
