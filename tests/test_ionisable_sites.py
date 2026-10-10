"""The ionisable-site summary: acid or base, and how much of each site is ionised at a pH.

What is guarded:

* **acid or base is read from the model's own protonation state**, by the charge of the form that
  holds the proton (neutral or anionic: an acid; cationic: a base), never from a name;
* **the fraction is Henderson-Hasselbalch for one site** and is checked against its closed forms: half
  at pH = pKa, a tenth decade away at one unit, the two forms of a site summing to one;
* **it reads the same predictions `pKa` does** -- same values, same atoms, same refusals -- so the two
  cannot disagree about a site;
* **atoms are named by the number on the canvas** (counting from 1), the same spelling the pKa line uses.
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem

from openchem.chem import pka_providers
from openchem.chem.descriptor_providers import _pka_line, compute_ionisable_sites, compute_pka_dataset
from openchem.chem.ionisable_sites import (
    ACID,
    BASE,
    UNKNOWN,
    fraction_ionised,
    kind_of,
    read_site,
    read_sites,
)
from openchem.chem.pka_providers import PkaPrediction

#: 4-aminobutanoic acid: atom 0 is the amine nitrogen and atom 6 the hydroxyl oxygen, so the canvas
#: names them N1 and O7.
GABA = "NCCCC(=O)O"

ACID_SITE = PkaPrediction(atom_index=6, value=4.2, stddev=0.3, protonated_site=(1, 0), deprotonated_site=(0, -1))
BASE_SITE = PkaPrediction(atom_index=0, value=10.4, stddev=0.0, protonated_site=(3, 1), deprotonated_site=(2, 0))


@pytest.fixture
def predictor(monkeypatch):
    """A configured pkasolver that answers with whatever the test hands it."""

    def answer(predictions=None, *, error: str | None = None, available: bool = True):
        monkeypatch.setattr(pka_providers, "pka_predictor_available", lambda _path: available)

        def fake(_mol, _path, **_kwargs):
            if error:
                raise RuntimeError(error)
            return list(predictions or [])

        monkeypatch.setattr(pka_providers, "compute_pka", fake)

    return answer


def _facts(report) -> dict:
    return {fact.label: fact for fact in report.facts}


# --- acid or base ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "protonated, expected",
    [((1, 0), ACID), ((0, -1), ACID), ((1, -1), ACID), ((3, 1), BASE), ((2, 1), BASE), ((2, 2), BASE), (None, UNKNOWN)],
)
def test_the_charge_of_the_proton_holding_form_decides(protonated, expected):
    assert kind_of(protonated) == expected


def test_a_carboxylic_acid_and_an_ammonium_are_read_as_what_they_are():
    assert read_site(ACID_SITE, 7.4).kind == ACID
    assert read_site(BASE_SITE, 7.4).kind == BASE


# --- the fraction, against closed forms ----------------------------------------------------------------------------


@pytest.mark.parametrize("kind", [ACID, BASE])
def test_half_of_a_site_is_ionised_when_the_ph_equals_its_pka(kind):
    assert fraction_ionised(kind, 6.3, 6.3) == pytest.approx(0.5, abs=1e-12)


def test_an_acid_one_unit_above_its_pka_is_ten_elevenths_deprotonated():
    assert fraction_ionised(ACID, 5.0, 6.0) == pytest.approx(10 / 11, rel=1e-12)
    assert fraction_ionised(ACID, 5.0, 4.0) == pytest.approx(1 / 11, rel=1e-12)


def test_a_base_one_unit_below_its_pka_is_ten_elevenths_protonated():
    assert fraction_ionised(BASE, 9.0, 8.0) == pytest.approx(10 / 11, rel=1e-12)
    assert fraction_ionised(BASE, 9.0, 10.0) == pytest.approx(1 / 11, rel=1e-12)


def test_an_acid_and_a_base_of_the_same_pka_are_mirror_images_about_it():
    for offset in (-3.0, -1.0, 0.5, 2.0):
        assert fraction_ionised(ACID, 7.0, 7.0 + offset) == pytest.approx(
            fraction_ionised(BASE, 7.0, 7.0 - offset), rel=1e-12
        )


def test_the_fraction_moves_the_right_way_with_ph():
    acid = [fraction_ionised(ACID, 5.0, ph) for ph in range(0, 15)]
    base = [fraction_ionised(BASE, 9.0, ph) for ph in range(0, 15)]

    assert acid == sorted(acid) and base == sorted(base, reverse=True)
    assert all(0.0 <= value <= 1.0 for value in acid + base)


def test_an_unknown_direction_has_no_fraction_not_a_guess():
    assert fraction_ionised(UNKNOWN, 5.0, 7.4) is None


def test_the_models_spread_gives_a_range_that_brackets_the_value():
    site = read_site(ACID_SITE, 4.5)
    low, high = site.fraction_range

    assert low < site.fraction_ionised < high
    assert low == pytest.approx(fraction_ionised(ACID, 4.2 + 0.3, 4.5))
    assert high == pytest.approx(fraction_ionised(ACID, 4.2 - 0.3, 4.5))


def test_no_spread_means_no_range_and_an_unknown_kind_means_neither():
    assert read_site(BASE_SITE, 7.4).fraction_range is None
    unknown = read_site(PkaPrediction(atom_index=1, value=5.0, stddev=0.4), 7.4)
    assert unknown.fraction_ionised is None and unknown.fraction_range is None


def test_the_sites_come_lowest_pka_first():
    assert [s.pka for s in read_sites([BASE_SITE, ACID_SITE], 7.4)] == [4.2, 10.4]


# --- the calculator ----------------------------------------------------------------------------------------------------


def test_gaba_at_ph_74_has_one_acid_and_one_base_both_mostly_ionised(predictor):
    predictor([BASE_SITE, ACID_SITE])
    mol = Chem.MolFromSmiles(GABA)

    facts = _facts(compute_ionisable_sites(mol, "m", {}, "x"))

    assert facts["Ionisable sites"].display_value == "2 (1 acidic, 1 basic)"
    assert facts["Mostly ionised at pH 7.4"].display_value == "2 of 2"
    assert facts["Acid 1 at O7"].value == 4.2 and "deprotonated" in facts["Acid 1 at O7"].display_value
    assert facts["Base 2 at N1"].value == 10.4 and "protonated" in facts["Base 2 at N1"].display_value


def test_the_percentages_are_the_closed_form_at_the_requested_ph(predictor):
    predictor([ACID_SITE])

    shown = compute_ionisable_sites(Chem.MolFromSmiles(GABA), "m", {"pH": 4.2, "decimal_places": 1}, "x").facts[2].display_value

    assert "50.0% deprotonated" in shown


def test_the_ph_is_clamped_into_the_scale_and_recorded(predictor):
    predictor([ACID_SITE])

    report = compute_ionisable_sites(Chem.MolFromSmiles(GABA), "m", {"pH": 99}, "x")

    assert report.provenance.parameters["pH"] == 14.0 and "Mostly ionised at pH 14" in _facts(report)


def test_it_reports_the_same_value_and_the_same_atom_as_pka_does(predictor):
    predictor([ACID_SITE])
    mol = Chem.MolFromSmiles(GABA)

    summary = compute_ionisable_sites(mol, "m", {}, "x").facts[2]
    line = _pka_line(ACID_SITE, {}, mol)

    assert "at O7" in summary.label and "at O7" in line
    assert summary.value == ACID_SITE.value and f"{ACID_SITE.value:.2f}" in line
    assert compute_pka_dataset(mol, "m", {}, "x").matched[0].startswith("pKa 4.20 at O7")


def test_the_spread_is_shown_and_its_effect_is_stated(predictor):
    predictor([ACID_SITE])

    row = compute_ionisable_sites(Chem.MolFromSmiles(GABA), "m", {}, "x").facts[2]

    assert "+/- 0.30" in row.display_value
    assert any("ranges from" in line and "not a confidence interval" in line for line in row.limitations)


def test_every_site_says_it_is_judged_alone(predictor):
    predictor([ACID_SITE, BASE_SITE])

    report = compute_ionisable_sites(Chem.MolFromSmiles(GABA), "m", {}, "x")

    for fact in report.facts[1:]:
        assert any("ALONE" in line for line in fact.limitations)


def test_a_site_whose_direction_was_not_reported_says_so(predictor):
    predictor([PkaPrediction(atom_index=6, value=4.2)])

    row = compute_ionisable_sites(Chem.MolFromSmiles(GABA), "m", {}, "x").facts[2]

    assert row.display_value == "pKa 4.20; direction not known" and row.label.startswith("Site 1")
    assert any("acid or a base was not read" in line for line in row.limitations)


def test_a_site_pkasolver_could_not_place_names_no_atom(predictor):
    predictor([PkaPrediction(atom_index=None, value=4.2, protonated_site=(1, 0))])

    assert compute_ionisable_sites(Chem.MolFromSmiles(GABA), "m", {}, "x").facts[2].label == "Acid 1"


# --- the three ways there is nothing to show ----------------------------------------------------------------------------


def test_with_no_pkasolver_configured_it_refuses_in_pkas_own_words(predictor):
    predictor(available=False)
    mol = Chem.MolFromSmiles(GABA)

    summary = compute_ionisable_sites(mol, "m", {}, "")
    pka = compute_pka_dataset(mol, "m", {}, "")

    assert summary.cache_state.name == "FAILED" and summary.error == pka.error
    assert summary.error_summary == pka.error_summary
    assert summary.provenance.parameters == pka.provenance.parameters


def test_a_failed_run_is_reported_not_swallowed(predictor):
    predictor(error="pkasolver blew up")

    report = compute_ionisable_sites(Chem.MolFromSmiles(GABA), "m", {}, "x")

    assert report.cache_state.name == "FAILED" and "blew up" in report.error


def test_a_run_that_worked_and_found_nothing_is_an_answer_with_its_limit_not_a_failure(predictor):
    predictor([])

    report = compute_ionisable_sites(Chem.MolFromSmiles("CCCC"), "m", {}, "x")

    assert report.cache_state.name != "FAILED"
    (fact,) = report.facts
    assert fact.display_value == "None predicted" and "limited domain" in fact.limitations[0]


# --- registration -------------------------------------------------------------------------------------------------------


def test_it_is_registered_in_the_pka_category_and_given_the_pkasolver_interpreter():
    from openchem.bootstrap import _CALCULATOR_INTERPRETER_SETTING, build_service_container

    registry = build_service_container().calculator_registry
    definition = registry.get("ionisable_sites")

    assert definition.category == "pka" and "ionisable_sites" in _CALCULATOR_INTERPRETER_SETTING
    assert [p.name for p in definition.parameters] == ["decimal_places", "pH"]
    assert definition.support.stage.value == "limited" and definition.support.support_reason


def test_through_the_registry_with_nothing_configured_it_refuses_cleanly(qapp):
    from openchem.bootstrap import build_service_container

    registry = build_service_container().calculator_registry

    result = registry.compute("ionisable_sites", Chem.MolFromSmiles(GABA), "m", {})

    assert result.cache_state.name == "FAILED" and math.isfinite(1.0)
