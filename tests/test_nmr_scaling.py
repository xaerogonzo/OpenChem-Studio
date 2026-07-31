"""Empirical scaling of computed shieldings onto real ppm.

The regression is tested against synthetic shieldings built from a known
line, so the test knows the right answer exactly -- unlike a test against
real ORCA output, which could only check that the numbers look
plausible.
"""

from __future__ import annotations

import pytest

from openchem.chem.nmr_scaling import (
    MIN_POINTS,
    REFERENCE_COMPOUNDS,
    CalibrationError,
    ScalingFactors,
    fit_scaling,
    reference_points,
    scale_spectrum,
)


def _points_from_line(slope: float, intercept: float, shieldings: list[float]):
    return [(sigma, slope * sigma + intercept) for sigma in shieldings]


def test_a_perfect_line_is_recovered_exactly():
    points = _points_from_line(-1.05, 185.0, [180.0, 150.0, 100.0, 60.0, 20.0])

    factors = fit_scaling(points)

    assert factors.slope == pytest.approx(-1.05)
    assert factors.intercept == pytest.approx(185.0)
    assert factors.r_squared == pytest.approx(1.0)
    assert factors.sample_count == 5


def test_applying_the_factors_inverts_the_line():
    factors = ScalingFactors(slope=-1.05, intercept=185.0, r_squared=1.0, sample_count=5)

    assert factors.apply(180.0) == pytest.approx(-1.05 * 180.0 + 185.0)


def test_a_noisy_but_real_trend_still_fits():
    points = _points_from_line(-1.02, 190.0, [190.0, 160.0, 120.0, 80.0, 30.0])
    jittered = [(x, y + offset) for (x, y), offset in zip(points, [0.4, -0.3, 0.5, -0.4, 0.2])]

    factors = fit_scaling(jittered)

    assert factors.slope == pytest.approx(-1.02, abs=0.02)
    assert factors.r_squared > 0.99


def test_too_few_points_is_refused_rather_than_fitted():
    """Two points define any line exactly, so an R^2 of 1.0 from two
    points is evidence of nothing."""
    with pytest.raises(CalibrationError, match="at least"):
        fit_scaling(_points_from_line(-1.0, 180.0, [180.0, 100.0]))


def test_a_meaningless_fit_raises_instead_of_silently_scaling_everything():
    """A calibration that quietly succeeds with a junk slope is worse than
    none: every shift downstream inherits it while looking MORE precise
    than the raw shielding it replaced."""
    scattered = [(180.0, 10.0), (150.0, 120.0), (100.0, 30.0), (60.0, 150.0), (20.0, 40.0)]

    with pytest.raises(CalibrationError, match="too poor"):
        fit_scaling(scattered)


def test_identical_shieldings_are_refused_with_a_clear_reason():
    with pytest.raises(CalibrationError, match="no line to fit"):
        fit_scaling([(100.0, 10.0), (100.0, 20.0), (100.0, 30.0), (100.0, 40.0)])


# --- Reference set -------------------------------------------------------


def test_every_reference_compound_has_at_least_a_carbon_value():
    assert all("C" in compound.shifts for compound in REFERENCE_COMPOUNDS)


def test_the_carbon_reference_range_is_wide_enough_to_fit_a_slope():
    """A calibration set clumped into ten ppm would give a slope that is
    an extrapolation everywhere it matters."""
    carbons = [compound.shifts["C"] for compound in REFERENCE_COMPOUNDS]

    assert max(carbons) - min(carbons) > 150
    assert len(carbons) >= MIN_POINTS


def test_reference_points_average_a_compounds_equivalent_nuclei():
    """Benzene's six carbons should agree; where they differ it is
    numerical noise, which averaging removes."""
    points = reference_points({"Benzene": [56.0, 58.0, 57.0, 57.0, 57.0, 57.0]}, "C")

    assert points == [(57.0, 128.4)]


def test_a_compound_that_did_not_run_is_skipped_not_defaulted():
    """A zero shielding for a missing run would drag the whole line."""
    points = reference_points({"Benzene": [57.0], "Chloroform": []}, "C")

    assert points == [(57.0, 128.4)]


def test_a_compound_with_no_literature_value_for_that_element_is_skipped():
    """Tetrachloromethane has no protons; asking for H must not invent
    one."""
    points = reference_points({"Tetrachloromethane": [100.0], "Benzene": [24.0]}, "H")

    assert points == [(24.0, 7.26)]


# --- Applying to a spectrum ---------------------------------------------


def test_scaling_a_spectrum_converts_shieldings_to_shifts_per_element():
    factors = {
        "C": ScalingFactors(slope=-1.0, intercept=185.0, r_squared=1.0, sample_count=5),
        "H": ScalingFactors(slope=-1.0, intercept=31.5, r_squared=1.0, sample_count=5),
    }

    scaled = scale_spectrum(
        {0: 57.0, 1: 24.3}, {0: "C", 1: "H"}, factors
    )

    assert scaled[0] == pytest.approx(128.0)
    assert scaled[1] == pytest.approx(7.2)


def test_an_uncalibrated_element_is_dropped_rather_than_passed_through_raw():
    """A raw carbon shielding near 57 sitting in a column of real ppm
    shifts reads as a chemical shift and is wrong by seventy ppm."""
    factors = {"H": ScalingFactors(slope=-1.0, intercept=31.5, r_squared=1.0, sample_count=5)}

    scaled = scale_spectrum({0: 57.0, 1: 24.3}, {0: "C", 1: "H"}, factors)

    assert 0 not in scaled
    assert scaled[1] == pytest.approx(7.2)


# --- Heavy-atom exclusions ----------------------------------------------
# Measured at B3LYP/def2-SVP against a real ORCA install; see the module
# docstring. These pin the decision so a future edit to the reference set
# cannot silently reintroduce the outliers.

_MEASURED_CARBON_SHIELDINGS = {
    "Methane": [194.92],
    "Tetramethylsilane": [191.06],
    "Cyclohexane": [163.67],
    "Dichloromethane": [126.72],
    "Nitromethane": [131.12],
    "Acetylene": [125.22],
    "Chloroform": [86.36],
    "Tetrachloromethane": [45.04],
    "Ethylene": [68.19],
    "Benzene": [65.17],
    "Carbon disulfide": [-119.41],
}


def test_carbon_excludes_the_heavy_atom_bonded_compounds():
    used = {
        compound.name
        for compound in REFERENCE_COMPOUNDS
        if "C" not in compound.unsuitable_for and "C" in compound.shifts
    }

    assert "Chloroform" not in used
    assert "Dichloromethane" not in used
    assert "Tetrachloromethane" not in used
    assert "Carbon disulfide" not in used
    assert {"Benzene", "Methane", "Cyclohexane", "Ethylene"} <= used


def test_protons_keep_the_chlorinated_compounds():
    """The spin-orbit effect is on the directly bonded nucleus. Measured:
    protons fit slightly BETTER with these included, so excluding them per
    compound rather than per element would have thrown away good data."""
    used = {
        compound.name
        for compound in REFERENCE_COMPOUNDS
        if "H" not in compound.unsuitable_for and "H" in compound.shifts
    }

    assert {"Chloroform", "Dichloromethane"} <= used


def test_the_real_measured_carbon_shieldings_now_fit():
    """The exact numbers from the ORCA run, which the full set fails on
    (R^2 0.902) and the filtered set passes."""
    points = reference_points(_MEASURED_CARBON_SHIELDINGS, "C")
    factors = fit_scaling(points)

    assert factors.r_squared > 0.99
    errors = [abs(factors.apply(sigma) - delta) for sigma, delta in points]
    assert sum(errors) / len(errors) < 2.5


def test_the_unfiltered_carbon_set_would_have_been_refused():
    """Proves the exclusions are load-bearing rather than cosmetic: the
    same measured shieldings without them do not fit."""
    unfiltered = [
        (sum(values) / len(values), compound.shifts["C"])
        for compound in REFERENCE_COMPOUNDS
        for values in [_MEASURED_CARBON_SHIELDINGS.get(compound.name, [])]
        if values and "C" in compound.shifts
    ]

    with pytest.raises(CalibrationError, match="too poor"):
        fit_scaling(unfiltered)
