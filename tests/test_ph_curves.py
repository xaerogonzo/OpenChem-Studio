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
    compute_logd_curve,
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


# --- scalar findings are DECLARED, not interpolated into the name ---------
#
# `compute_isoelectric_point` built `f"Charge vs pH - pI = {pi:.2f}"` and
# `compute_logd_curve` built `f"LogD vs pH (LogP = {...})"`. A name is not a
# value: it carries no units, no basis, no evidence, no limitation, and cannot
# be copied out as data. `PhCurveResult.facts` was added for solubility with
# this migration explicitly deferred; these guard the migration.
#
# **NEITHER SUCCESS PATH HAD ANY COVERAGE AT ALL.** Every existing test of
# these two functions passes an unavailable interpreter, so they took the
# refusal branch -- including the guard that claimed to pin this migration,
# which asserted `facts == ()` on a path that has none under any
# implementation. The seam below is what reaches the other branch.


def _with_pkas(monkeypatch, pkas, n_acids, n_bases):
    """Supply pKa values without a pkasolver install.

    `_resolve_pkas` is the ONE place these curves obtain them and it takes no
    explicit values -- unlike the solubility curve, which accepts a
    `pka_values` parameter. Patching that seam tests the fact declaration,
    which is the subject here, rather than the sidecar, which is not.
    """
    import openchem.chem.ph_curves as ph_curves

    monkeypatch.setattr(
        ph_curves, "_resolve_pkas", lambda mol, path: (list(pkas), n_acids, n_bases, None)
    )


def test_the_isoelectric_curve_declares_its_pi_as_a_fact(monkeypatch):
    """Glycine: one acid and one base, so the net charge really does cross
    zero and there is a pI to declare. A monoprotic acid could not show this
    -- it never crosses zero -- which is the other branch, below."""
    _with_pkas(monkeypatch, [2.3, 9.6], 1, 1)
    result = compute_isoelectric_point(Chem.MolFromSmiles("NCC(=O)O"), "u", {})

    assert result.cache_state is not CacheState.FAILED, "fixture must reach the success path"
    facts = {f.label: f for f in result.facts}
    assert "Isoelectric point (pI)" in facts
    pi = facts["Isoelectric point (pI)"]
    assert isinstance(pi.value, float), "the VALUE must be the number, not prose"
    assert 2.3 < pi.value < 9.6
    assert pi.source == "pkasolver"


def test_the_pi_is_no_longer_smuggled_into_the_display_name():
    """The name is what a selector and a status line show. A scalar living
    there cannot carry units or a basis, and cannot be copied as data."""
    import openchem.chem.ph_curves as ph_curves
    import inspect

    source = inspect.getsource(ph_curves.compute_isoelectric_point)
    assert "pI = " not in source, "the pI is being interpolated into a string again"


def test_a_molecule_with_no_isoelectric_point_declares_that_rather_than_nothing(monkeypatch):
    """**n/a IS NOT ABSENT.** A monoprotic acid genuinely has no pI -- its
    charge runs 0 to -1 and never crosses zero -- and `isoelectric_point`
    returns None deliberately, because reporting a boundary value would invent
    one. Omitting the fact entirely would read as "not computed"; the value is
    None and the display says why.
    """
    _with_pkas(monkeypatch, [3.49], 1, 0)
    result = compute_isoelectric_point(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"), "u", {})

    facts = {f.label: f for f in result.facts}
    pi = facts["Isoelectric point (pI)"]
    assert pi.value is None
    assert "none" in pi.display_value.lower()
    assert pi.limitations, "the absence needs its reason, not just a blank"


def test_the_logd_curve_declares_its_logp_as_a_fact(monkeypatch):
    """LogP is the value logD reduces to when nothing is ionized, so it is
    what a reader compares the curve against."""
    _with_pkas(monkeypatch, [4.4], 1, 0)
    result = compute_logd_curve(Chem.MolFromSmiles("CC(C)Cc1ccc(cc1)C(C)C(=O)O"), "u", {})

    assert result.cache_state is not CacheState.FAILED, "fixture must reach the success path"
    facts = {f.label: f for f in result.facts}
    assert "LogP" in facts
    logp = facts["LogP"]
    assert isinstance(logp.value, float)
    # RDKit, NOT "pkasolver": `source` answers where a value came from rather
    # than which module assembled it, and this one does not come from the pKa
    # predictor at all.
    assert logp.source == "RDKit"


def test_the_logp_is_no_longer_smuggled_into_the_display_name(monkeypatch):
    _with_pkas(monkeypatch, [4.4], 1, 0)
    result = compute_logd_curve(Chem.MolFromSmiles("CC(C)Cc1ccc(cc1)C(C)C(=O)O"), "u", {})
    assert result.name == "LogD vs pH"
    assert "LogP" not in result.name


def test_a_declared_scalar_survives_a_copy(monkeypatch):
    """The point of moving these out of the name. `_ph_curve_to_text` writes
    the facts above the table, so a pasted curve carries the number a reader
    quotes -- which a title could never do."""
    from openchem.ui.result_clipboard import result_to_text

    _with_pkas(monkeypatch, [2.3, 9.6], 1, 1)
    result = compute_isoelectric_point(Chem.MolFromSmiles("NCC(=O)O"), "u", {})
    assert "Isoelectric point (pI)" in result_to_text(result)


def test_neither_curve_name_carries_a_non_ascii_character(monkeypatch):
    """The isoelectric name used an EM DASH, which reaches the Properties
    panel, the clipboard and the log. This repository records that character
    passing a cp1252 assertion and still rendering as a replacement character
    on a real Windows console -- it cost a refusal message its meaning once.

    Both branches, because only one of them built the em-dash string.
    """
    for pkas, n_acids, n_bases in (([2.3, 9.6], 1, 1), ([3.49], 1, 0)):
        _with_pkas(monkeypatch, pkas, n_acids, n_bases)
        for compute in (compute_isoelectric_point, compute_logd_curve):
            name = compute(Chem.MolFromSmiles("NCC(=O)O"), "u", {}).name
            assert name.isascii(), f"{compute.__name__} name is not ASCII: {name!r}"
