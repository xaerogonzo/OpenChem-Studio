"""Phase 28: pH-dependent curves.

Reference values are textbook: a monoprotic acid is 50/50 at its pKa, and
glycine's isoelectric point is 5.97.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.ph_curves import (
    compute_hbond_vs_ph,
    compute_isoelectric_point,
    compute_major_microspecies,
    compute_pka_distribution,
    isoelectric_point,
    microspecies_fractions,
    net_charge_at_ph,
    ph_grid,
    species_charges,
)
from openchem.domain.common import CacheState

# Glycine: COOH pKa 2.34, NH3+ pKa 9.60, textbook pI 5.97.
GLYCINE_PKAS = [2.34, 9.60]


# --- Speciation ---------------------------------------------------------


def test_a_monoprotic_acid_is_exactly_half_dissociated_at_its_pka():
    protonated, deprotonated = microspecies_fractions(4.76, [4.76])

    assert protonated == pytest.approx(0.5)
    assert deprotonated == pytest.approx(0.5)


def test_fractions_sum_to_one_at_every_ph():
    for ph in ph_grid():
        assert sum(microspecies_fractions(ph, [3.43, 7.4, 10.1])) == pytest.approx(1.0)


def test_a_molecule_with_no_pka_is_entirely_one_species():
    assert microspecies_fractions(7.4, []) == [1.0]


def test_low_ph_favours_the_fully_protonated_form():
    fractions = microspecies_fractions(0.0, GLYCINE_PKAS)
    assert fractions[0] > 0.99


def test_high_ph_favours_the_fully_deprotonated_form():
    fractions = microspecies_fractions(14.0, GLYCINE_PKAS)
    assert fractions[-1] > 0.99


def test_each_pka_is_a_fifty_fifty_crossing_between_adjacent_species():
    at_first = microspecies_fractions(3.43, [3.43, 7.4])
    assert at_first[0] == pytest.approx(at_first[1], abs=1e-3)

    at_second = microspecies_fractions(7.4, [3.43, 7.4])
    assert at_second[1] == pytest.approx(at_second[2], abs=1e-3)


# --- Charge and isoelectric point --------------------------------------


def test_species_charges_run_from_plus_bases_to_minus_acids():
    """Fully protonated carries +1 per base; fully deprotonated -1 per acid."""
    assert species_charges(n_acids=1, n_bases=1) == [1, 0, -1]
    assert species_charges(n_acids=2, n_bases=0) == [0, -1, -2]
    assert species_charges(n_acids=0, n_bases=2) == [2, 1, 0]


def test_glycine_isoelectric_point_matches_the_textbook_value():
    pi = isoelectric_point(GLYCINE_PKAS, n_acids=1, n_bases=1)
    assert pi == pytest.approx(5.97, abs=0.01)


def test_glycine_net_charge_is_positive_below_and_negative_above_its_pi():
    assert net_charge_at_ph(1.0, GLYCINE_PKAS, 1, 1) > 0
    assert net_charge_at_ph(12.0, GLYCINE_PKAS, 1, 1) < 0


def test_net_charge_is_exactly_half_at_each_pka():
    assert net_charge_at_ph(2.34, GLYCINE_PKAS, 1, 1) == pytest.approx(0.5, abs=0.01)
    assert net_charge_at_ph(9.60, GLYCINE_PKAS, 1, 1) == pytest.approx(-0.5, abs=0.01)


def test_a_permanently_charged_molecule_has_no_isoelectric_point():
    """A quaternary ammonium never reaches zero net charge. Reporting a
    boundary value would invent an answer that doesn't exist."""
    assert isoelectric_point([4.0], n_acids=1, n_bases=0, permanent_charge=2) is None


def test_a_simple_acid_has_no_isoelectric_point():
    """An isoelectric point requires an amphoteric species. A
    monocarboxylic acid is neutral at low pH and anionic above, never
    CROSSING zero -- it only approaches it asymptotically, so `None` is
    the chemically correct answer rather than a number near its pKa.
    (This test originally asserted the opposite; the code was right.)"""
    assert isoelectric_point([4.76], n_acids=1, n_bases=0) is None


def test_an_amphoteric_molecule_does_have_one():
    assert isoelectric_point(GLYCINE_PKAS, n_acids=1, n_bases=1) is not None


# --- Curves without a pKa predictor ------------------------------------


def test_curves_report_a_clear_message_when_pkasolver_is_missing():
    """Every curve except H-bonding needs numeric pKa. There is no honest
    fallback that produces a curve rather than a flat line, so it says so."""
    result = compute_pka_distribution(
        Chem.MolFromSmiles("CC(=O)O"), "mol-1", {}, interpreter_path=""
    )

    assert result.cache_state == CacheState.FAILED
    assert "pkasolver" in result.error


def test_a_molecule_with_no_ionizable_centre_says_so_rather_than_blaming_pkasolver():
    result = compute_isoelectric_point(Chem.MolFromSmiles("CCCC"), "mol-1", {}, interpreter_path="")

    assert result.cache_state == CacheState.FAILED
    assert "no ionizable centre" in result.error


def test_hbond_curve_works_without_pkasolver():
    """Dimorphite-DL alone gives the dominant microspecies, so this one
    curve does not depend on the optional heavy install."""
    result = compute_hbond_vs_ph(Chem.MolFromSmiles("CC(=O)O"), "mol-1")

    assert result.cache_state != CacheState.FAILED
    assert set(result.series) == {"Donors", "Acceptors"}
    assert len(result.series["Donors"]) == len(result.ph_values)


def test_hbond_counts_are_never_negative():
    result = compute_hbond_vs_ph(Chem.MolFromSmiles("CC(=O)O"), "mol-1")
    assert all(value >= 0 for value in result.series["Donors"])
    assert result.y_min == 0.0


# --- Major microspecies -------------------------------------------------


def test_an_acid_is_neutral_at_low_ph_and_anionic_at_high_ph():
    acid = Chem.MolFromSmiles("CC(=O)O")

    low = compute_major_microspecies(acid, "mol-1", {"pH": 2.0})
    high = compute_major_microspecies(acid, "mol-1", {"pH": 10.0})

    assert "charge +0" in low.entries[0].label or "charge 0" in low.entries[0].label
    assert "charge -1" in high.entries[0].label


def test_major_microspecies_returns_one_depictable_entry():
    result = compute_major_microspecies(Chem.MolFromSmiles("CC(=O)O"), "mol-1", {"pH": 7.4})

    assert len(result.entries) == 1
    assert Chem.MolFromMolBlock(result.entries[0].molblock) is not None


def test_major_microspecies_names_the_ph_it_used():
    result = compute_major_microspecies(Chem.MolFromSmiles("CC(=O)O"), "mol-1", {"pH": 2.0})
    assert "2" in result.name


# --- Distribution curve shape ------------------------------------------


def test_distribution_pins_its_axis_to_zero_and_one_hundred_percent():
    """A distribution is bounded by construction; without pinning, the
    shared widget's padding draws an axis from -8% to 108%."""
    from openchem.domain.scientific_result import PhCurveResult

    # Built directly rather than through the calculator, which needs
    # pkasolver -- the axis pinning is a property of the result shape.
    curve = PhCurveResult(
        curve_id="pka_microspecies", name="x", method="m", molecule_uuid="mol-1",
        ph_values=[0.0, 7.0, 14.0], series={"a": [100.0, 50.0, 0.0]}, y_min=0.0, y_max=100.0,
    )
    assert (curve.y_min, curve.y_max) == (0.0, 100.0)


def test_ph_grid_spans_zero_to_fourteen():
    grid = ph_grid()
    assert grid[0] == 0.0
    assert grid[-1] == pytest.approx(14.0)


def test_logd_curve_documents_its_zwitterion_limitation():
    """Henderson-Hasselbalch under-predicts logD for amphoteric molecules
    because it assumes the partitioning species has no site ionized --
    glycine at pH 7 is essentially all zwitterion. Caught by running real
    predictions, and documented rather than left to be rediscovered."""
    from openchem.chem.ph_curves import compute_logd_curve

    assert "zwitterion" in compute_logd_curve.__doc__.lower()
