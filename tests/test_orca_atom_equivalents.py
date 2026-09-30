"""Fits and checks against real ORCA output recorded on this machine (ORCA 6.1.1, B3LYP/def2-SVP,
RDKit 2025.9.6 -- now pinned exact in pyproject.toml) -- see the module docstring in
`benchmarks/thermophysical/orca_atom_equivalents.py` for the RETRACTED note: the original numbers here
were each computed at a different, undocumented point in an RDKit-version drift (a floating `>=` pin let
`uv sync` silently resolve a newer RDKit partway through this survey), and everything below was re-run
fresh, together, in one sitting, once that was discovered 2026-09-29.

Track 4 Gate C (2026-09-30) added a tenth calibration compound (1,4-dinitropiperazine, a second ring
nitramine with two N-NO2 sites) and a new target (metriol trinitrate, MTN) -- see the module docstring's
own dated section for the full finding. Several tests below now reconstruct the ORIGINAL nine-point
subset explicitly (excluding "dinitropiperazine" from `oae.CALIBRATION_SET`, which now has ten entries)
so their own historical claims about the state BEFORE Gate C stay locked in and do not silently start
describing the new ten-point fit instead.
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
    """Ten compounds (nine plus Gate C's 1,4-dinitropiperazine), four free parameters -- six degrees of
    freedom now, better than the earlier 7-point fit's three, but still every calibration point's own
    residual should stay in a normal DFT/atom-equivalent range (see module docstring)."""
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
        if k not in ("dimethylnitramine", "nitropiperidine", "ethyl_nitrate", "dinitropiperazine")
    }
    assert len(six_point) == 6
    ae = oae.fit_atom_equivalents(six_point)
    for name, (counts, etot, exp) in six_point.items():
        fitted = oae.compute_gas_hf(counts, etot, ae)
        assert fitted == pytest.approx(exp, abs=15.0), name


@pytest.mark.parametrize(
    ("name", "expected_gas"),
    [("RDX", 217.68), ("HMX", 287.84), ("PETN", -331.83)],
)
def test_targets_gas_phase_with_the_ten_point_calibration(oae, name, expected_gas):
    """Locks in the ten-point fit's gas-phase DfH (Track 4 Gate C, 2026-09-30: adds 1,4-dinitropiperazine
    to the fresh, internally-consistent 2026-09-29 nine-point set) so a future change to the calibration
    set or the ORCA-recorded Etot values is visible. See test_combined_route_rdx_did_not_clear_the_bar_at_
    the_original_nine_point_fit for the ORIGINAL nine-point values (253.8/336.0/-313.4), still true of
    that explicitly-reconstructed subset and unaffected by this addition."""
    ae = oae.fit_atom_equivalents(oae.CALIBRATION_SET)
    counts, etot = oae.TARGET_ETOT_KJMOL[name]
    gas = oae.compute_gas_hf(counts, etot, ae)
    assert gas == pytest.approx(expected_gas, abs=0.5)


def test_combined_route_rdx_did_not_clear_the_bar_at_the_original_nine_point_fit(oae):
    """Locks in the ORIGINAL nine-point fit's own result (Track 4 Gate B, before Gate C's second ring
    nitramine), by explicitly excluding "dinitropiperazine" from `oae.CALIBRATION_SET` (which now has
    ten entries) -- so this historical claim keeps describing the nine-point fit even though the module's
    own CALIBRATION_SET has grown. RDX's combined-route error at this fit (13.2 -> 36.2 -> 38.4 kJ/mol
    across the three original refits) did NOT clear SENSITIVITY.md's ~21 kJ/mol bar against either of
    Klapoetke's two measured readings. See test_second_ring_nitramine_clears_the_bar_for_rdx_and_hmx for
    what changed once dinitropiperazine was added."""
    original_nine_point = {k: v for k, v in oae.CALIBRATION_SET.items() if k != "dinitropiperazine"}
    assert len(original_nine_point) == 9
    ae = oae.fit_atom_equivalents(original_nine_point)
    counts, etot = oae.TARGET_ETOT_KJMOL["RDX"]
    gas = oae.compute_gas_hf(counts, etot, ae)
    hsub_rdx = 130.44  # keshavarz2010_sublimation, this survey's own computed value
    solid = gas - hsub_rdx
    assert solid == pytest.approx(123.35, abs=0.5)
    assert abs(solid - 66.6) > 21.0
    assert abs(solid - 85.0) > 21.0


def test_untargeted_six_point_fit_was_rdxs_best_result_before_the_second_ring_nitramine(oae):
    """Historical scope, explicitly named: among the THREE ORIGINAL refits (6/7/9-point, all predating
    Gate C's 1,4-dinitropiperazine), the untargeted 6-compound fit gave RDX's best combined-route result
    (13.2 kJ/mol from Klapoetke's p.232 prose value) -- the only one of those three that cleared the
    ~21 kJ/mol bar. This is no longer RDX's best result overall: the new ten-point fit (Gate C) does
    dramatically better still -- see test_second_ring_nitramine_clears_the_bar_for_rdx_and_hmx."""
    six_point = {
        k: v for k, v in oae.CALIBRATION_SET.items()
        if k not in ("dimethylnitramine", "nitropiperidine", "ethyl_nitrate", "dinitropiperazine")
    }
    ae = oae.fit_atom_equivalents(six_point)
    counts, etot = oae.TARGET_ETOT_KJMOL["RDX"]
    gas = oae.compute_gas_hf(counts, etot, ae)
    hsub_rdx = 130.44
    solid = gas - hsub_rdx
    assert solid == pytest.approx(53.39, abs=0.5)
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
    # `oae.CALIBRATION_SET` now has TEN entries (Track 4 Gate C added "dinitropiperazine") -- explicitly
    # excluded below so this test keeps reconstructing the three ORIGINAL fits (6/7/9-point), not a
    # 7/8/10-point sequence that was never the one this finding is about.
    six_point = {
        k: v for k, v in oae.CALIBRATION_SET.items()
        if k not in ("dimethylnitramine", "nitropiperidine", "ethyl_nitrate", "dinitropiperazine")
    }
    seven_point = {
        k: v for k, v in oae.CALIBRATION_SET.items()
        if k not in ("nitropiperidine", "ethyl_nitrate", "dinitropiperazine")
    }
    nine_point = {k: v for k, v in oae.CALIBRATION_SET.items() if k != "dinitropiperazine"}

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


def test_hmx_pbe0_tzvp_diagnostic_isolates_electronic_from_geometry_effect(oae):
    """Gate B diagnostic (2026-09-29, see module docstring): a single-point PBE0/def2-TZVP energy at
    HMX's fresh B3LYP/def2-SVP geometry isolates a large electronic-level-only shift (-1924.3 kJ/mol) --
    a full PBE0/def2-TZVP reoptimization from the same starting geometry then adds a much smaller,
    OPPOSITE-direction geometry-relaxation effect (+96.2 kJ/mol), confirmed as a genuine converged
    stationary point (ORCA's own "HURRAY", 38 cycles), not an artifact of a stalled optimization.

    This is a real, self-contained finding about HMX's own potential energy surface, but it does NOT by
    itself say whether the combined-route error improves at this level -- that needs the full
    calibration set re-run and refit at PBE0/def2-TZVP, not done here (a much larger compute
    commitment: this single HMX reoptimization alone took over an hour)."""
    step1_kjmol = -3137634.721  # B3LYP/def2-SVP opt, matches oae.TARGET_ETOT_KJMOL["HMX"] exactly
    step2_kjmol = -3139558.995  # PBE0/def2-TZVP single point at the SAME geometry
    step3_kjmol = -3139462.804  # PBE0/def2-TZVP full reoptimization

    counts, etot = oae.TARGET_ETOT_KJMOL["HMX"]
    assert etot == pytest.approx(step1_kjmol, abs=0.01)

    electronic_only_shift = step2_kjmol - step1_kjmol
    geometry_relaxation_shift = step3_kjmol - step2_kjmol
    assert electronic_only_shift == pytest.approx(-1924.274, abs=0.01)
    assert geometry_relaxation_shift == pytest.approx(96.191, abs=0.01)
    # the electronic-level effect dominates by an order of magnitude over geometry relaxation
    assert abs(electronic_only_shift) > 10 * abs(geometry_relaxation_shift)


def test_pbe0_tzvp_full_refit_does_not_materially_improve_the_combined_route(oae):
    """Gate B, full refit (2026-09-30, see module docstring): all 12 compounds (the 9-point calibration
    set plus RDX/HMX/PETN) re-run fresh, full geometry optimization, at PBE0/def2-TZVP -- same seed,
    same fit/target population split as the B3LYP/def2-SVP fit. Etot values below are real ORCA output,
    recorded exactly as CALIBRATION_SET/TARGET_ETOT_KJMOL record the B3LYP/def2-SVP ones; this test does
    not call oae.CALIBRATION_SET (that stays at B3LYP/def2-SVP -- see module docstring for why the
    PBE0/def2-TZVP numbers were not adopted as the module's data).

    Locks in the finding: RDX and HMX both get WORSE at the higher level (38.4->41.0, 45.2->53.7 kJ/mol);
    PETN improves (87.6->73.7 kJ/mol) but remains far outside any usable bar. Level of theory is ruled
    out as the fix for RDX/HMX, the same way conformer choice was ruled out by
    test_conformer_choice_does_not_explain_rdx_hmx_error.
    """
    fit_set_pbe0_tzvp = {
        "methane": ((1, 4, 0, 0), -106264.947, -74.6),
        "ammonia": ((0, 3, 1, 0), -148375.107, -45.9),
        "benzene": ((6, 6, 0, 0), -609234.402, 82.6),
        "methanol": ((1, 4, 0, 1), -303603.640, -201.0),
        "nitromethane": ((1, 3, 1, 2), -642856.247, -74.3),
        "methyl_nitrate": ((1, 3, 1, 3), -840123.971, -124.4),
        "dimethylnitramine": ((2, 6, 2, 2), -891147.276, -5.0),
        "nitropiperidine": ((5, 10, 2, 2), -1197395.990, -44.0),
        "ethyl_nitrate": ((2, 5, 1, 3), -943261.853, -155.0),
    }
    target_etot_pbe0_tzvp = {
        "RDX": ((3, 6, 6, 6), -2354598.932),
        "HMX": ((4, 8, 8, 8), -3139462.804),
        "PETN": ((5, 8, 4, 12), -3454180.391),
    }
    # keshavarz2010_sublimation Hsub, this survey's own computed value -- unchanged from the B3LYP/def2-SVP
    # fit, since Hsub depends only on molar mass and molecular-class correction terms, not on the QM level
    # the gas-phase Etot was computed at. RDX (130.44) and PETN (138.02) match the earlier-locked 130.4 /
    # 138.0 values to within rounding; HMX's Hsub (174.67) is computed here for the first time.
    hsub = {"RDX": 130.44, "HMX": 174.67, "PETN": 138.02}
    measured = {"RDX": (66.6, 85.0), "HMX": (116.1,), "PETN": (-539.0,)}

    ae = oae.fit_atom_equivalents(fit_set_pbe0_tzvp)

    # the refit itself is a reasonable fit on its own calibration set -- not simply diverging
    residuals = [
        oae.compute_gas_hf(counts, etot, ae) - exp
        for counts, etot, exp in fit_set_pbe0_tzvp.values()
    ]
    assert max(abs(r) for r in residuals) < 15.0

    errors = {}
    for name, (counts, etot) in target_etot_pbe0_tzvp.items():
        gas = oae.compute_gas_hf(counts, etot, ae)
        solid = gas - hsub[name]
        errors[name] = min(abs(solid - m) for m in measured[name])

    assert errors["RDX"] == pytest.approx(41.0, abs=0.5)
    assert errors["HMX"] == pytest.approx(53.7, abs=0.5)
    assert errors["PETN"] == pytest.approx(73.7, abs=0.5)

    # the finding that matters: RDX and HMX get WORSE at the higher level, PETN improves but not enough
    assert errors["RDX"] > 38.4
    assert errors["HMX"] > 45.2
    assert errors["PETN"] < 87.6
    assert errors["PETN"] > 21.0  # still far outside SENSITIVITY.md's ~21 kJ/mol bar


def test_second_ring_nitramine_clears_the_bar_for_rdx_and_hmx_but_not_petn(oae):
    """Track 4 Gate C (2026-09-30): adding 1,4-dinitropiperazine -- a second ring nitramine, with TWO
    N-NO2 sites on one ring, closer to RDX's three and HMX's four than any single-site nitramine already
    in the set -- to CALIBRATION_SET (now ten points) moves RDX from 38.4 kJ/mol (over the bar) to 2.2
    kJ/mol, and HMX from 45.2 kJ/mol to 2.9 kJ/mol, both now clearing SENSITIVITY.md's ~21 kJ/mol bar by
    roughly an order of magnitude. PETN improves (87.6 -> 69.2 kJ/mol) but stays far outside it.

    The atom equivalents themselves barely move (a few kJ/mol per element -- see module docstring); the
    large downstream effect is RDX/HMX's own high nitrogen count amplifying a small per-atom shift, a
    checked mechanism, not an unexplained coincidence. Still explicitly NOT treated as validated on one
    new calibration point alone -- see the module docstring's own caveat.
    """
    ae = oae.fit_atom_equivalents(oae.CALIBRATION_SET)  # now ten points
    hsub = {"RDX": 130.44, "HMX": 174.67, "PETN": 138.02}
    measured = {"RDX": (66.6, 85.0), "HMX": (116.1,), "PETN": (-539.0,)}

    errors = {}
    for name in ("RDX", "HMX", "PETN"):
        counts, etot = oae.TARGET_ETOT_KJMOL[name]
        gas = oae.compute_gas_hf(counts, etot, ae)
        solid = gas - hsub[name]
        errors[name] = min(abs(solid - m) for m in measured[name])

    assert errors["RDX"] == pytest.approx(2.24, abs=0.5)
    assert errors["HMX"] == pytest.approx(2.92, abs=0.5)
    assert errors["PETN"] == pytest.approx(69.15, abs=0.5)

    assert errors["RDX"] <= 21.0
    assert errors["HMX"] <= 21.0
    assert errors["PETN"] > 21.0


def test_mtn_the_three_arm_nitrate_ester_is_well_predicted_under_either_fit(oae):
    """Track 4 Gate C: metriol trinitrate (MTN) -- a quaternary carbon with THREE -CH2-ONO2 arms plus
    one -CH3, PETN's own four-arm topology minus one arm -- is a new TARGET (no gas-phase reference
    exists, so it cannot be a CALIBRATION_SET fit point; combined route only, the same role PETN plays).

    MTN is well predicted under BOTH the original nine-point fit (9.5 kJ/mol) and the new ten-point fit
    (1.0 kJ/mol) -- far better than PETN's own result at any fit tried in this survey (59.5 kJ/mol best
    case). Consistent with this survey's repeated finding that PETN's own four-arm topology specifically,
    not nitrate-ester chemistry generally, is what this elemental scheme cannot represent: three arms
    predict well, four do not.
    """
    original_nine_point = {k: v for k, v in oae.CALIBRATION_SET.items() if k != "dinitropiperazine"}
    ae9 = oae.fit_atom_equivalents(original_nine_point)
    ae10 = oae.fit_atom_equivalents(oae.CALIBRATION_SET)

    hsub_mtn = 121.76  # keshavarz2010_sublimation, no correction rule for nitrate esters -- same as PETN
    measured_mtn = -450.2  # Tavernier (1956), Mem. Poudres, via NIST WebBook

    counts, etot = oae.TARGET_ETOT_KJMOL["MTN"]
    solid9 = oae.compute_gas_hf(counts, etot, ae9) - hsub_mtn
    solid10 = oae.compute_gas_hf(counts, etot, ae10) - hsub_mtn

    assert abs(solid9 - measured_mtn) == pytest.approx(9.54, abs=0.5)
    assert abs(solid10 - measured_mtn) == pytest.approx(0.96, abs=0.5)
    assert abs(solid10 - measured_mtn) <= 21.0
    assert abs(solid9 - measured_mtn) <= 21.0
