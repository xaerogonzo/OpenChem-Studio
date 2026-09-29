"""Fits and checks against real ORCA output recorded on this machine (ORCA 6.1.1, B3LYP/def2-SVP) --
see the module docstring in `benchmarks/thermophysical/orca_atom_equivalents.py` for the reproducibility
caveat, the conformer-choice check (negative result), and the escalating-PETN-divergence finding.
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
    [("RDX", 213.3), ("HMX", 265.7), ("PETN", -320.6)],
)
def test_targets_gas_phase_with_the_nine_point_calibration(oae, name, expected_gas):
    """Locks in this session's computed gas-phase DfH (9-point fit) so a future change to the
    calibration set or the ORCA-recorded Etot values is visible."""
    ae = oae.fit_atom_equivalents(oae.CALIBRATION_SET)
    counts, etot = oae.TARGET_ETOT_KJMOL[name]
    gas = oae.compute_gas_hf(counts, etot, ae)
    assert gas == pytest.approx(expected_gas, abs=0.5)


def test_combined_route_rdx_clears_the_sensitivity_bar_more_comfortably_than_before(oae):
    """RDX keeps improving as nitramine-class calibration data grows: 50.1 (no nitramine data) -> 80.4
    (1 nitramine) -> 82.9 (2 nitramines, this fit) kJ/mol, now within 2.1 kJ/mol of Klapoetke's own
    Table 9.6 value and 16.3 of its p.232 prose value -- both comfortably inside SENSITIVITY.md's
    ~21 kJ/mol bar."""
    ae = oae.fit_atom_equivalents(oae.CALIBRATION_SET)
    counts, etot = oae.TARGET_ETOT_KJMOL["RDX"]
    gas = oae.compute_gas_hf(counts, etot, ae)
    hsub_rdx = 130.4  # keshavarz2010_sublimation, this survey's own computed value
    solid = gas - hsub_rdx
    assert solid == pytest.approx(82.9, abs=0.5)
    assert abs(solid - 66.6) <= 21.0
    assert abs(solid - 85.0) <= 21.0


def test_combined_route_petn_diverges_monotonically_as_calibration_data_grows(oae):
    """The concrete evidence this is NOT a validated route: PETN's own error got WORSE across three
    independent refits, in the same direction each time (46.6 -> 72.7 -> 80.4 kJ/mol against Klapoetke
    Table 9.16b's -539 kJ/mol), even after adding a second nitrate ester (ethyl nitrate) specifically
    meant to help it. A one-point fluke does not repeat in the same direction twice -- PETN's own
    quaternary-carbon, four-arm structure is the more likely explanation (see module docstring)."""
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
    out as the source of RDX/HMX's remaining combined-route error."""
    original = {"RDX": -2353293.341, "HMX": -3137743.152}
    best_conformer = {"RDX": -2353297.644, "HMX": -3137737.005}
    assert (best_conformer["RDX"] - original["RDX"]) == pytest.approx(-4.303, abs=0.01)
    assert (best_conformer["HMX"] - original["HMX"]) == pytest.approx(6.147, abs=0.01)
    # both differences are far smaller than the ~25-80 kJ/mol combined-route errors being investigated
    assert abs(best_conformer["RDX"] - original["RDX"]) < 10.0
    assert abs(best_conformer["HMX"] - original["HMX"]) < 10.0
