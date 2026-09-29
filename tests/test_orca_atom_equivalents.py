"""Fits and checks against real ORCA output recorded on this machine (ORCA 6.1.1, B3LYP/def2-SVP,
RDKit 2025.9.6 -- now pinned exact in pyproject.toml) -- see the module docstring in
`benchmarks/thermophysical/orca_atom_equivalents.py` for the RETRACTED note: the original numbers here
were each computed at a different, undocumented point in an RDKit-version drift (a floating `>=` pin let
`uv sync` silently resolve a newer RDKit partway through this survey), and everything below was re-run
fresh, together, in one sitting, once that was discovered 2026-09-29.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def oae():
    path = ROOT / "benchmarks" / "thermophysical" / "orca_atom_equivalents.py"
    spec = importlib.util.spec_from_file_location("orca_atom_equivalents", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_full_calibration_set_fits_within_20_kjmol(oae):
    """Nine compounds, four free parameters -- five degrees of freedom now, better than the earlier
    7-point fit's three, but still every calibration point's own residual should stay in a normal
    DFT/atom-equivalent range (see module docstring)."""
    ae = oae.fit_atom_equivalents(oae.CALIBRATION_SET)
    for name, (counts, etot, exp) in oae.CALIBRATION_SET.items():
        fitted = oae.compute_gas_hf(counts, etot, ae)
        assert fitted == pytest.approx(exp, abs=21.0), name


def test_dropping_all_nitramine_and_second_nitrate_ester_data_reproduces_the_six_point_fit(oae):
    """Locks in the finding that motivated adding nitramine/nitrate-ester chemistry at all: without it,
    the fit is excellent on its own (narrow) calibration set but the combined RDX/HMX/PETN route misses
    the real measured values by 71-141 kJ/mol -- see test_combined_route_petn_diverges_monotonically."""
    six_point = {
        k: v for k, v in oae.CALIBRATION_SET.items()
        if k not in ("dimethylnitramine", "nitropiperidine", "ethyl_nitrate")
    }
    assert len(six_point) == 6
    ae = oae.fit_atom_equivalents(six_point)
    for name, (counts, etot, exp) in six_point.items():
        fitted = oae.compute_gas_hf(counts, etot, ae)
        assert fitted == pytest.approx(exp, abs=15.0), name


@pytest.mark.parametrize(
    ("name", "expected_gas"),
    [("RDX", 253.8), ("HMX", 336.0), ("PETN", -313.4)],
)
def test_targets_gas_phase_with_the_nine_point_calibration(oae, name, expected_gas):
    """Locks in the fresh, internally-consistent (2026-09-29) gas-phase DfH (9-point fit) so a future
    change to the calibration set or the ORCA-recorded Etot values is visible."""
    ae = oae.fit_atom_equivalents(oae.CALIBRATION_SET)
    counts, etot = oae.TARGET_ETOT_KJMOL[name]
    gas = oae.compute_gas_hf(counts, etot, ae)
    assert gas == pytest.approx(expected_gas, abs=0.5)


def test_combined_route_rdx_no_longer_clears_the_bar_once_data_is_internally_consistent(oae):
    """RDX's apparent improvement as nitramine-class calibration data grew (50.1 -> 80.4 -> 82.9 kJ/mol,
    the pre-2026-09-29 numbers) was an artifact of an RDKit-version drift across sessions, not real
    signal -- see the module docstring's RETRACTED note. Under fresh, internally-consistent data the
    direction REVERSES: RDX's combined-route error gets WORSE as nitramine data is added (13.2 -> 36.2
    -> 38.4 kJ/mol against Klapoetke's two measured readings), and the 9-point fit no longer clears
    SENSITIVITY.md's ~21 kJ/mol bar. Only the untargeted 6-point fit (no nitramine chemistry at all)
    still does -- see test_untargeted_six_point_fit_is_now_rdxs_best_result."""
    ae = oae.fit_atom_equivalents(oae.CALIBRATION_SET)
    counts, etot = oae.TARGET_ETOT_KJMOL["RDX"]
    gas = oae.compute_gas_hf(counts, etot, ae)
    hsub_rdx = 130.4  # keshavarz2010_sublimation, this survey's own computed value
    solid = gas - hsub_rdx
    assert solid == pytest.approx(123.4, abs=0.5)
    assert abs(solid - 66.6) > 21.0
    assert abs(solid - 85.0) > 21.0


def test_untargeted_six_point_fit_is_now_rdxs_best_result(oae):
    """The reversal in one number: with fresh, internally-consistent data, the 6-compound fit that
    predates any nitramine-specific calibration chemistry gives RDX's best combined-route result
    (13.2 kJ/mol from Klapoetke's p.232 prose value), the only one of the three fits that clears the
    ~21 kJ/mol bar -- see the module docstring's RETRACTED note for why this is the opposite of what
    was previously reported."""
    six_point = {
        k: v for k, v in oae.CALIBRATION_SET.items()
        if k not in ("dimethylnitramine", "nitropiperidine", "ethyl_nitrate")
    }
    ae = oae.fit_atom_equivalents(six_point)
    counts, etot = oae.TARGET_ETOT_KJMOL["RDX"]
    gas = oae.compute_gas_hf(counts, etot, ae)
    hsub_rdx = 130.4
    solid = gas - hsub_rdx
    assert solid == pytest.approx(53.4, abs=0.5)
    assert abs(solid - 66.6) <= 21.0


def test_combined_route_petn_diverges_monotonically_as_calibration_data_grows(oae):
    """The one part of the original writeup that SURVIVES the RDKit-drift correction (see module
    docstring's RETRACTED note): PETN's own error still gets WORSE across three independent refits, in
    the same direction each time, now 59.5 -> 80.5 -> 87.6 kJ/mol against Klapoetke Table 9.16b's -539
    kJ/mol (previously 46.6 -> 72.7 -> 80.4 kJ/mol on the drifted data -- same direction, different
    numbers), even after adding a second nitrate ester (ethyl nitrate) specifically meant to help it.
    This monotonic pattern holding under BOTH the drifted and the corrected data is why PETN's own
    quaternary-carbon, four-arm structure -- not environment noise -- is the more likely explanation
    (see module docstring)."""
    six_point = {
        k: v for k, v in oae.CALIBRATION_SET.items()
        if k not in ("dimethylnitramine", "nitropiperidine", "ethyl_nitrate")
    }
    seven_point = {k: v for k, v in oae.CALIBRATION_SET.items() if k != "nitropiperidine" and k != "ethyl_nitrate"}
    seven_point["dimethylnitramine"] = oae.CALIBRATION_SET["dimethylnitramine"]
    nine_point = oae.CALIBRATION_SET

    counts, etot = oae.TARGET_ETOT_KJMOL["PETN"]
    hsub_petn = 138.0  # keshavarz2010_sublimation, this survey's own computed value
    measured = -539.0

    errors = []
    for calibration in (six_point, seven_point, nine_point):
        ae = oae.fit_atom_equivalents(calibration)
        solid = oae.compute_gas_hf(counts, etot, ae) - hsub_petn
        errors.append(abs(solid - measured))

    assert errors[0] < errors[1] < errors[2]


def test_conformer_choice_does_not_explain_rdx_hmx_error(oae):
    """A wider conformer search (80 embeds, MMFF94-ranked) found RDX's and HMX's original single-seed
    ORCA starting geometry ranked mediocre-to-poor (18th of 35; 30th of 50) -- but re-running ORCA's own
    B3LYP/def2-SVP Opt from each molecule's MMFF94 global minimum moved the CONVERGED DFT energy by only
    -4.3 kJ/mol for RDX and, counter to the MMFF94 ranking, +6.1 kJ/mol (WORSE) for HMX. Locked in here
    so this investigation is not silently redone: conformer choice, within this search's range, is ruled
    out as the source of RDX/HMX's remaining combined-route error.

    The two hardcoded values below predate the 2026-09-29 RDKit-pin fix (see module docstring's
    RETRACTED note) and are NOT the current oae.TARGET_ETOT_KJMOL values -- this is a self-contained,
    same-session A/B comparison (original seed vs. MMFF-global-minimum seed, both run back to back in
    one environment), so the RELATIVE difference it locks in is unaffected by the later discovery that
    the ABSOLUTE values drifted across sessions. Do not "fix" these to match the current calibration
    set; that would compare two different environments instead of the controlled pair this test records.
    """
    original = {"RDX": -2353293.341, "HMX": -3137743.152}
    best_conformer = {"RDX": -2353297.644, "HMX": -3137737.005}
    assert (best_conformer["RDX"] - original["RDX"]) == pytest.approx(-4.303, abs=0.01)
    assert (best_conformer["HMX"] - original["HMX"]) == pytest.approx(6.147, abs=0.01)
    # both differences are far smaller than the ~25-80 kJ/mol combined-route errors being investigated
    assert abs(best_conformer["RDX"] - original["RDX"]) < 10.0
    assert abs(best_conformer["HMX"] - original["HMX"]) < 10.0
