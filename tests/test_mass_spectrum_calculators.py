"""The two calculators that show an isotope envelope, and their contract.

One engine, two callers. Elemental Analysis draws the molecular ion's
envelope beside its percentages -- the way MarvinSketch's own window does
-- and the Mass Spectrum calculator is where the ionisation modes live.
The most important test in this file is that they agree.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.elemental_analysis import compute_elemental_analysis
from openchem.chem.mass_spectrum import (
    EXACT_RESOLUTION,
    UNIT_RESOLUTION,
    compute_mass_spectrum,
)
from openchem.domain.common import CacheState
from openchem.domain.mass_spectrum import DEFAULT_ION, SUPPORTED_IONS
from openchem.domain.report import valid_chart_annotation

_DIBROMOBENZOIC = "OC(=O)c1cccc(Br)c1Br"


def _mol(smiles: str = _DIBROMOBENZOIC):
    return Chem.MolFromSmiles(smiles)


# --- one engine, two callers ---------------------------------------------


def test_the_two_calculators_agree_on_the_default_ion():
    """**THE PROOF OF "ONE ENGINE, TWO CALLERS".** Identical rather than
    within a tolerance, because it is the same call: two implementations
    of one arithmetic is the divergence this project has paid for four
    times, and the two would drift silently -- both would keep producing
    plausible envelopes."""
    elemental = compute_elemental_analysis(_mol(), "u")
    spectrum = compute_mass_spectrum(_mol(), "u", {"ion": DEFAULT_ION.label})
    assert elemental.charts and spectrum.charts
    assert [(s.x, s.y) for s in elemental.charts[0].sticks] == [
        (s.x, s.y) for s in spectrum.charts[0].sticks
    ]


def test_elemental_analysis_takes_no_ionisation_parameters():
    """A `[M+Na]+` selector on a composition readout would be an
    ionisation control on the wrong calculator. The modes live one section
    down, and this is what keeps them there."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "elemental_analysis"
    )
    assert not any(p.name in {"ion", "resolution"} for p in definition.parameters)


# --- what Elemental Analysis draws ---------------------------------------


def test_elemental_analysis_declares_the_molecular_ion_envelope():
    report = compute_elemental_analysis(_mol(), "u")
    assert len(report.charts) == 1
    chart = report.charts[0]
    assert valid_chart_annotation(chart)
    assert DEFAULT_ION.label in chart.title


def test_the_envelope_is_the_one_marvin_draws():
    """The screenshot that motivated the feature: 278, 280 and 282 in a
    1:2:1 bromine pattern, with the small odd-mass carbon satellites
    between them."""
    chart = compute_elemental_analysis(_mol(), "u").charts[0]
    by_mz = {int(round(stick.x)): stick.y for stick in chart.sticks}
    assert sorted(by_mz) == [278, 279, 280, 281, 282, 283]
    assert by_mz[280] == pytest.approx(1.0)
    assert by_mz[278] == pytest.approx(0.51, abs=0.01)
    assert by_mz[282] == pytest.approx(0.49, abs=0.01)


def test_m_over_z_runs_low_mass_to_the_left():
    """The opposite of NMR and IR, and declared rather than guessed: a
    mirrored spectrum does not look broken, it looks like a different
    compound."""
    assert compute_elemental_analysis(_mol(), "u").charts[0].x_descending is False


def test_the_nominal_mass_is_reported_beside_the_exact_one():
    """Marvin's own window shows both, and they answer different
    questions."""
    lines = compute_elemental_analysis(_mol(), "u").matched
    assert any(line.startswith("Nominal mass: 278") for line in lines)
    assert any(line.startswith("Exact mass: 277.857") for line in lines)


def test_a_molecule_with_no_natural_isotope_still_reports_its_composition():
    """Technetium has none, so there is no envelope to draw -- which is a
    fact about the molecule rather than a failure of this calculator. The
    percentages are still correct and still worth showing."""
    report = compute_elemental_analysis(Chem.MolFromSmiles("[Tc]"), "u")
    assert report.cache_state is not CacheState.FAILED
    assert report.charts == ()
    assert any("Formula" in line for line in report.matched)


# --- the caption, which is the honesty half ------------------------------


def test_the_caption_says_calculated_and_never_claims_to_be_measured():
    """**CALCULATED, NOT "THEORETICAL SPECTRUM".** A theoretical
    distribution is not what an instrument records -- ion sampling,
    detector response and centroiding all move a real one -- and a picture
    that calls itself a spectrum invites the reader to compare it with
    one. `SpectrumBasis` is the architectural protection; this is the
    wording half, and it has to survive rendering."""
    caption = compute_elemental_analysis(_mol(), "u").charts[0].caption
    assert "CALCULATED" in caption
    assert "not a measured spectrum" in caption
    assert "no fragmentation" in caption.lower()


def test_both_calculators_carry_the_same_caption_text():
    """One string, used twice, so the two cannot drift into saying
    different things about identical arithmetic."""
    elemental = compute_elemental_analysis(_mol(), "u").charts[0].caption
    spectrum = compute_mass_spectrum(_mol(), "u", {}).charts[0].caption
    assert elemental == spectrum


# --- the Mass Spectrum calculator's own modes ----------------------------


@pytest.mark.parametrize("ion", [ion.label for ion in SUPPORTED_IONS])
def test_every_offered_ion_produces_a_real_result(ion):
    """A menu item that fails is worse than one that is absent."""
    report = compute_mass_spectrum(_mol("CCO"), "u", {"ion": ion})
    assert report.cache_state is not CacheState.FAILED
    assert report.charts and report.charts[0].sticks
    assert any(line.startswith(f"Ion: {ion}") for line in report.matched)


def test_the_charge_comes_from_the_ion_and_not_from_a_separate_control():
    """A charge spinbox beside a short species list is how `[M+2H]2+`
    comes to mean "charge 2, and the composition of something else"."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "mass_spectrum"
    )
    assert not any("charge" in p.name for p in definition.parameters)
    doubly = compute_mass_spectrum(_mol("CCO"), "u", {"ion": "[M+2H]2+"})
    assert any("charge +2" in line for line in doubly.matched)


def test_the_resolution_changes_the_reported_masses():
    unit = compute_mass_spectrum(_mol("CCO"), "u", {"resolution": UNIT_RESOLUTION})
    exact = compute_mass_spectrum(_mol("CCO"), "u", {"resolution": EXACT_RESOLUTION})
    unit_first = unit.charts[0].sticks[0].x
    exact_first = exact.charts[0].sticks[0].x
    assert unit_first == pytest.approx(round(unit_first))
    assert exact_first != pytest.approx(round(exact_first), abs=1e-4)


def test_the_minimum_intensity_filters_the_reported_lines():
    generous = compute_mass_spectrum(_mol(), "u", {"minimum_percent": 0.1})
    strict = compute_mass_spectrum(_mol(), "u", {"minimum_percent": 20.0})
    assert len(_peak_lines(strict)) < len(_peak_lines(generous))


def _peak_lines(report):
    return [line for line in report.matched if line.strip().startswith(("M:", "M+"))]


def test_an_unknown_ion_label_falls_back_to_the_default_rather_than_failing():
    """The vocabulary is closed, so an unrecognised label is a stale saved
    parameter rather than a user request -- and losing the whole result
    over one would be worse than showing the molecular ion."""
    report = compute_mass_spectrum(_mol("CCO"), "u", {"ion": "[M+Xe]17+"})
    assert report.cache_state is not CacheState.FAILED
    assert any(line.startswith(f"Ion: {DEFAULT_ION.label}") for line in report.matched)


# --- provenance ----------------------------------------------------------


def test_the_result_records_which_isotope_table_and_which_release():
    """The abundances are RDKit's, so the answer depends on its version.
    "RDKit says it" is not immutable across releases, and a stored
    spectrum that cannot say which table it used cannot be reproduced."""
    parameters = compute_mass_spectrum(_mol("CCO"), "u", {}).provenance.parameters
    assert parameters["isotope_data"] == "rdkit"
    assert parameters["rdkit_version"]
    assert parameters["prune_threshold"] > 0


def test_the_result_records_the_ion_it_was_computed_for():
    parameters = compute_mass_spectrum(
        _mol("CCO"), "u", {"ion": "[M+Cl]-"}
    ).provenance.parameters
    assert parameters["ion"] == "[M+Cl]-"
    assert parameters["charge"] == -1


# --- reachability --------------------------------------------------------


def test_the_calculator_is_registered_where_a_user_can_press_it():
    """A calculator nothing can reach is a module. This project shipped
    four of those once."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    ids = {d.calculator_id for d in CALCULATOR_DEFINITIONS}
    assert "mass_spectrum" in ids


def test_it_opens_no_section_of_its_own():
    """**A CATEGORY HOLDING ONE CALCULATOR IS THE SHAPE THIS PANEL MOVED
    AWAY FROM** -- 26 sections held 49 buttons and eleven of them held
    exactly one, which `docs/NAVIGATION_AUDIT.md` counted and
    `test_no_category_holds_a_single_calculator` now forbids.

    It sits in Identity on the merits rather than by elimination: directly
    beside Elemental Analysis, sharing its engine, answering the same
    question about what a structure is and what it weighs.
    """
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "mass_spectrum"
    )
    assert definition.category == "identity"
    siblings = [d for d in CALCULATOR_DEFINITIONS if d.category == "identity"]
    assert len(siblings) > 1, "it shares its section rather than opening one"
    assert any(d.calculator_id == "elemental_analysis" for d in siblings)
