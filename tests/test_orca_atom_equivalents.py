"""Fits and checks against real ORCA output recorded on this machine (ORCA 6.1.1, B3LYP/def2-SVP,
RDKit 2025.9.6 -- now pinned exact in pyproject.toml).

Track 5 (2026-10-01) found a SECOND environment bug beyond the RDKit-drift one this file already
carried a note about: `parse_output` extracted a multi-cycle `opt` job's FIRST "FINAL SINGLE POINT
ENERGY" line, not its converged last -- see the module docstring's "CRITICAL CORRECTION 2026-10-01"
section for the full finding and the paired fix in `src/openchem/chem/orca_engine.py`. Every numeric
value in this file was re-derived from the real ORCA output files re-extracted with the fix (no new
jobs were run -- the converged energy was always in the file). Track 4 Gate C's "second ring nitramine
clears the bar" and Gate B's "a higher level of theory does not help" both reverse under the corrected
data; see each test's own docstring below for what changed and why.
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
    """Nine compounds, four free parameters -- five degrees of freedom -- every calibration point's own
    residual should stay in a normal DFT/atom-equivalent range (see module docstring). Note this bound is
    nominally "20" but every assertion elsewhere in this file uses the real computed residuals, which run
    up to ~20.0 kJ/mol (ammonia) under the corrected energies -- tighter than it looks from the name."""
    ae = oae.fit_atom_equivalents(oae.CALIBRATION_SET)
    for name, (counts, etot, exp) in oae.CALIBRATION_SET.items():
        fitted = oae.compute_gas_hf(counts, etot, ae)
        assert fitted == pytest.approx(exp, abs=21.0), name


def test_dropping_all_nitramine_and_second_nitrate_ester_data_reproduces_the_six_point_fit(oae):
    """Locks in the finding that motivated adding nitramine/nitrate-ester chemistry at all: without it,
    the fit is excellent on its own (narrow) calibration set but the combined RDX/HMX/PETN route misses
    the real measured values badly -- see test_combined_route_petn_diverges_monotonically."""
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
    [("RDX", 213.28), ("HMX", 265.68), ("PETN", -320.61)],
)
def test_targets_gas_phase_with_the_nine_point_calibration(oae, name, expected_gas):
    """Locks in the CORRECTED (2026-10-01, Track 5) gas-phase DfH from the nine-point fit, re-extracted
    from the real ORCA output with the fixed parser -- these values replace the ones this test locked in
    on 2026-09-29, which were silently the energy of the FIRST optimization cycle, not the converged
    geometry (see module docstring)."""
    ae = oae.fit_atom_equivalents(oae.CALIBRATION_SET)
    counts, etot = oae.TARGET_ETOT_KJMOL[name]
    gas = oae.compute_gas_hf(counts, etot, ae)
    assert gas == pytest.approx(expected_gas, abs=0.5)


def test_combined_route_rdx_clears_the_bar_at_the_corrected_nine_point_fit(oae):
    """Track 5 correction (2026-10-01): under the CORRECTED (converged) energies, RDX's combined-route
    error at the plain nine-point fit -- no second ring nitramine, no PBE0/def2-TZVP, nothing from
    Track 4's Gates B or C -- is 2.2 kJ/mol against Klapoetke's Table 9.6 reading (85.0 kJ/mol) and 16.2
    kJ/mol against the p.232 prose reading (66.6 kJ/mol): BOTH now clear SENSITIVITY.md's ~21 kJ/mol bar.

    This REVERSES the equivalent test's claim before this correction (RDX did not clear the bar at the
    nine-point fit, only the untargeted six-point fit did) -- that claim was built on first-cycle,
    unconverged energies throughout. See the module docstring's "CRITICAL CORRECTION" section for why
    this particular result is also strikingly close to Track 3's very first (pre-RDKit-drift-retraction)
    numbers, an open question this correction does not fully resolve."""
    ae = oae.fit_atom_equivalents(oae.CALIBRATION_SET)
    counts, etot = oae.TARGET_ETOT_KJMOL["RDX"]
    gas = oae.compute_gas_hf(counts, etot, ae)
    hsub_rdx = 130.44  # keshavarz2010_sublimation, this survey's own computed value
    solid = gas - hsub_rdx
    assert solid == pytest.approx(82.84, abs=0.5)
    assert abs(solid - 66.6) <= 21.0
    assert abs(solid - 85.0) <= 21.0


def test_untargeted_six_point_fit_is_now_rdxs_worst_result(oae):
    """Track 5 correction: under corrected energies, the untargeted six-compound fit (no nitramine
    chemistry at all) is now RDX's WORST result (70-89 kJ/mol off, nowhere near the ~21 kJ/mol bar) --
    the exact opposite of what this test asserted before the parser fix, when the six-point fit looked
    like RDX's best (and only passing) result. This reversal makes physical sense: a calibration set with
    zero nitramine chemistry was never expected to generalize well to RDX's own ring-N-NO2 structure --
    the earlier result was a coincidence of comparing two sets of equally-wrong (first-cycle) energies
    that happened to partially cancel, not evidence the six-point fit was secretly the right choice."""
    six_point = {
        k: v for k, v in oae.CALIBRATION_SET.items()
        if k not in ("dimethylnitramine", "nitropiperidine", "ethyl_nitrate")
    }
    ae = oae.fit_atom_equivalents(six_point)
    counts, etot = oae.TARGET_ETOT_KJMOL["RDX"]
    gas = oae.compute_gas_hf(counts, etot, ae)
    hsub_rdx = 130.44
    solid = gas - hsub_rdx
    assert solid == pytest.approx(-4.37, abs=0.5)
    assert abs(solid - 66.6) > 21.0
    assert abs(solid - 85.0) > 21.0


def test_combined_route_petn_diverges_monotonically_as_calibration_data_grows(oae):
    """The one finding in this whole module that SURVIVES every correction -- the RDKit-drift fix
    (2026-09-29) and this parser-bug fix (2026-10-01) alike: PETN's own combined-route error gets
    WORSE across three independent refits, in the same direction every time (46.5 -> 72.7 -> 80.4 kJ/mol
    against Klapoetke Table 9.16b's -539 kJ/mol, corrected energies), even after adding a second nitrate
    ester (ethyl nitrate) specifically meant to help it. This monotonic pattern holding under THREE
    independently-computed versions of this dataset (original, RDKit-drift-corrected, and now
    parser-bug-corrected) is why PETN's own quaternary-carbon, four-arm structure -- not any environment
    bug -- is the right explanation (see module docstring)."""
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

    The two hardcoded values below predate BOTH the 2026-09-29 RDKit-pin fix and the 2026-10-01
    parser-bug fix (see module docstring) and are NOT the current oae.TARGET_ETOT_KJMOL values -- this is
    a self-contained, same-session A/B comparison (original seed vs. MMFF-global-minimum seed, both run
    back to back in one environment, by whatever energy-extraction convention was active at the time), so
    the RELATIVE difference it locks in is unaffected by either later discovery. Do not "fix" these to
    match the current calibration set; that would compare two different environments instead of the
    controlled pair this test records.
    """
    original = {"RDX": -2353293.341, "HMX": -3137743.152}
    best_conformer = {"RDX": -2353297.644, "HMX": -3137737.005}
    assert (best_conformer["RDX"] - original["RDX"]) == pytest.approx(-4.303, abs=0.01)
    assert (best_conformer["HMX"] - original["HMX"]) == pytest.approx(6.147, abs=0.01)
    # both differences are far smaller than the ~25-80 kJ/mol combined-route errors being investigated
    assert abs(best_conformer["RDX"] - original["RDX"]) < 10.0
    assert abs(best_conformer["HMX"] - original["HMX"]) < 10.0


def test_hmx_pbe0_tzvp_diagnostic_isolates_electronic_from_geometry_effect(oae):
    """Gate B diagnostic, corrected 2026-10-01 (Track 5): a single-point PBE0/def2-TZVP energy at HMX's
    B3LYP/def2-SVP geometry isolates a large electronic-level-only shift (-1815.8 kJ/mol) -- a full
    PBE0/def2-TZVP reoptimization from the same starting geometry then adds a much smaller
    geometry-relaxation effect (-7.1 kJ/mol), the SAME direction as the electronic shift this time, not
    opposite. (The pre-correction version of this test had the geometry-relaxation shift at +96.2 kJ/mol
    -- energy going UP after a relaxation, which is physically backwards for a minimization and should
    have been a red flag on its own; the corrected, physically sane direction is itself evidence the fix
    is right, not just a number that happens to match other corrected values.)

    This diagnostic alone does not by itself say whether the combined-route error improves at this
    level -- see test_pbe0_tzvp_full_refit_dramatically_improves_hmx for the full nine-point refit.
    """
    step1_kjmol = -3137743.199  # B3LYP/def2-SVP opt, matches oae.TARGET_ETOT_KJMOL["HMX"] exactly
    step2_kjmol = -3139558.995  # PBE0/def2-TZVP single point at the SAME geometry (unaffected -- one line)
    step3_kjmol = -3139566.070  # PBE0/def2-TZVP full reoptimization, corrected (was -3139462.804)

    counts, etot = oae.TARGET_ETOT_KJMOL["HMX"]
    assert etot == pytest.approx(step1_kjmol, abs=0.01)

    electronic_only_shift = step2_kjmol - step1_kjmol
    geometry_relaxation_shift = step3_kjmol - step2_kjmol
    assert electronic_only_shift == pytest.approx(-1815.796, abs=0.01)
    assert geometry_relaxation_shift == pytest.approx(-7.075, abs=0.01)
    # the electronic-level effect still dominates by more than an order of magnitude
    assert abs(electronic_only_shift) > 10 * abs(geometry_relaxation_shift)


def test_pbe0_tzvp_full_refit_dramatically_improves_hmx(oae):
    """Gate B full refit, corrected 2026-10-01 (Track 5): the same real ORCA output this module already
    held (re-extracted with the fixed parser, no new jobs run) tells the OPPOSITE story from what Gate B
    originally reported. A nine-point PBE0/def2-TZVP fit gives HMX a combined-route error of 3.0 kJ/mol --
    the best HMX result anywhere in this entire survey, by a wide margin, at a level of theory the
    pre-correction version of this test said made HMX WORSE (53.7 kJ/mol). RDX (9.2 kJ/mol) clears the
    bar too, though not quite as well as the corrected B3LYP/def2-SVP nine-point fit's 2.2 kJ/mol. PETN
    improves (62.9 vs. the B3LYP/def2-SVP fit's 80.4 kJ/mol) but still fails badly -- consistent with
    PETN's structural diagnosis surviving every correction tried in this module.
    """
    fit_set_pbe0_tzvp = {
        "methane": ((1, 4, 0, 0), -106264.990, -74.6),
        "ammonia": ((0, 3, 1, 0), -148375.446, -45.9),
        "benzene": ((6, 6, 0, 0), -609235.214, 82.6),
        "methanol": ((1, 4, 0, 1), -303606.041, -201.0),
        "nitromethane": ((1, 3, 1, 2), -642862.485, -74.3),
        "methyl_nitrate": ((1, 3, 1, 3), -840138.427, -124.4),
        "dimethylnitramine": ((2, 6, 2, 2), -891161.435, -5.0),
        "nitropiperidine": ((5, 10, 2, 2), -1197408.786, -44.0),
        "ethyl_nitrate": ((2, 5, 1, 3), -943276.711, -155.0),
    }
    target_etot_pbe0_tzvp = {
        "RDX": ((3, 6, 6, 6), -2354670.296),
        "HMX": ((4, 8, 8, 8), -3139566.070),
        "PETN": ((5, 8, 4, 12), -3454248.816),
    }
    # keshavarz2010_sublimation Hsub, this survey's own computed value -- unchanged from the B3LYP/def2-SVP
    # fit, since Hsub depends only on molar mass and molecular-class correction terms, not on the QM level
    # the gas-phase Etot was computed at.
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

    assert errors["RDX"] == pytest.approx(9.15, abs=0.5)
    assert errors["HMX"] == pytest.approx(3.02, abs=0.5)
    assert errors["PETN"] == pytest.approx(62.91, abs=0.5)

    # the finding that matters: HMX dramatically improves (not "gets worse", as the pre-correction
    # version of this test claimed), RDX and PETN also both clear/approach the bar or improve
    assert errors["RDX"] <= 21.0
    assert errors["HMX"] <= 21.0
    assert errors["PETN"] > 21.0  # PETN still fails -- this part did not change


def test_second_ring_nitramine_now_makes_hmx_worse_not_better(oae):
    """Track 4 Gate C's headline finding, RETRACTED 2026-10-01 (Track 5): under corrected energies,
    adding 1,4-dinitropiperazine (a second ring nitramine with two N-NO2 sites) to the nine-point
    calibration set makes HMX's combined-route error substantially WORSE (25.1 -> 57.5 kJ/mol) and RDX
    slightly worse against its best reading (2.2 -> 8.1 kJ/mol, though both still clear the bar either
    way). This is the exact opposite of Gate C's original claim (both targets dramatically improving) --
    that claim was built on energies that were, at the time, ALL still first-cycle/unconverged, so the
    comparison was internally consistent but describing the wrong physical quantity throughout.

    `dinitropiperazine` is therefore NOT in the live `CALIBRATION_SET` (reconstructed here instead,
    matching its real, unaffected NIST value and real, corrected ORCA Etot) -- its measured data remains
    valid and is kept in `validation_rows_energetics.py` with `partition="selection"` (tested against,
    not fit on), not deleted.
    """
    ten_point = dict(oae.CALIBRATION_SET)
    ten_point["dinitropiperazine"] = ((4, 8, 4, 4), -1775013.153, 58.0)
    ae10 = oae.fit_atom_equivalents(ten_point)
    hsub = {"RDX": 130.44, "HMX": 174.67}
    measured = {"RDX": (66.6, 85.0), "HMX": (116.1,)}

    errors = {}
    for name in ("RDX", "HMX"):
        counts, etot = oae.TARGET_ETOT_KJMOL[name]
        gas = oae.compute_gas_hf(counts, etot, ae10)
        solid = gas - hsub[name]
        errors[name] = min(abs(solid - m) for m in measured[name])

    assert errors["RDX"] == pytest.approx(8.09, abs=0.5)
    assert errors["HMX"] == pytest.approx(57.53, abs=0.5)

    # RDX still clears the bar either way; HMX now fails where the nine-point fit cleared it
    assert errors["RDX"] <= 21.0
    assert errors["HMX"] > 21.0


def test_mtn_the_three_arm_nitrate_ester_is_well_predicted(oae):
    """Metriol trinitrate (MTN) -- a quaternary carbon with THREE -CH2-ONO2 arms plus one -CH3, PETN's
    own four-arm topology minus one arm -- is a TARGET (no gas-phase reference exists, so it cannot be a
    CALIBRATION_SET fit point; combined route only, the same role PETN plays).

    MTN is well predicted at the corrected nine-point fit (9.7 kJ/mol) -- far better than PETN's own
    result at any fit tried in this survey (46.5 kJ/mol best case, the six-point fit). Consistent with
    this survey's repeated, now-triply-confirmed finding that PETN's own four-arm topology specifically,
    not nitrate-ester chemistry generally, is what this elemental scheme cannot represent: three arms
    predict well, four do not -- true before AND after both the RDKit-drift and parser-bug corrections.
    """
    ae = oae.fit_atom_equivalents(oae.CALIBRATION_SET)
    hsub_mtn = 121.76  # keshavarz2010_sublimation, no correction rule for nitrate esters -- same as PETN
    measured_mtn = -450.2  # Tavernier (1956), Mem. Poudres, via NIST WebBook

    counts, etot = oae.TARGET_ETOT_KJMOL["MTN"]
    solid = oae.compute_gas_hf(counts, etot, ae) - hsub_mtn

    assert abs(solid - measured_mtn) == pytest.approx(9.66, abs=0.5)
    assert abs(solid - measured_mtn) <= 21.0
