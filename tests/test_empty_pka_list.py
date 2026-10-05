"""What logD, CNS MPO and the BBB inputs do when the pKa predictor has nothing.

`compute_pka(...) or []` made three different situations one: nothing configured,
a run that errored, and a run that worked and had no value for THIS structure. The
third is the one that did damage -- logD fell into Henderson-Hasselbalch with an
empty list and reported logP, labelled "Henderson-Hasselbalch on the predicted pKa
values", for an amine that is mostly protonated at pH 7.4. CNS MPO and the BBB inputs
told the person to configure an environment that was configured.

`predicted_pkas` (chem/pka_providers.py) is the one definition of the three states;
each calculator keeps its own decision about what to do with them.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

import openchem.chem.pka_providers as pka_providers
from openchem.chem.bbb_stereo import compute_bbb_descriptors
from openchem.chem.descriptor_providers import compute_logd
from openchem.chem.mpo_scores import compute_cns_mpo
from openchem.chem.pka_providers import PKaStatus, predicted_pkas
from openchem.domain.common import CacheState

#: A tertiary amine: one basic centre, so logD at pH 7.4 must sit below logP.
AMINE = "CCN(CC)CCCc1ccccc1"


@pytest.fixture
def predictor(monkeypatch):
    """`predictor("none" | "error" | "values")` -- a configured pkasolver that answers so."""

    def set_to(behaviour: str):
        monkeypatch.setattr(pka_providers, "pka_predictor_available", lambda _path: True)

        def fake(_mol, _path):
            if behaviour == "error":
                raise RuntimeError("pkasolver blew up")
            if behaviour == "none":
                return []
            return [pka_providers.PkaPrediction(atom_index=None, value=10.1)]

        monkeypatch.setattr(pka_providers, "compute_pka", fake)

    return set_to


def test_the_three_empty_cases_are_three_statuses(monkeypatch, predictor):
    mol = Chem.MolFromSmiles(AMINE)
    monkeypatch.setattr(pka_providers, "pka_predictor_available", lambda _path: False)
    assert predicted_pkas(mol, "").status is PKaStatus.UNAVAILABLE
    predictor("error")
    erred = predicted_pkas(mol, "x")
    assert erred.status is PKaStatus.FAILED and "blew up" in erred.reason
    predictor("none")
    assert predicted_pkas(mol, "x").status is PKaStatus.NO_PREDICTION
    predictor("values")
    found = predicted_pkas(mol, "x")
    assert found.status is PKaStatus.FOUND and found.values == (10.1,)


def test_logd_does_not_call_logp_henderson_hasselbalch_when_the_predictor_had_nothing(predictor):
    """The wrong answer this fixes: 2.96 (= logP) with an empty pKa row, for an amine."""
    mol = Chem.MolFromSmiles(AMINE)
    predictor("none")
    report = compute_logd(mol, "u", {"pH": 7.4}, "x")

    logd = next(f for f in report.facts if f.label.startswith("LogD at pH"))
    logp = next(f for f in report.facts if f.label == "LogP")
    assert "(approximation)" in logd.label, "it must say it is not the real thing"
    assert logd.value < logp.value - 0.5, "a basic amine at pH 7.4 is mostly protonated"
    assert report.provenance.method == "rdkit+dimorphite_dl"
    assert report.charts == ()
    assert any("pkasolver ran but has no pKa for this structure" in line for line in report.limitations)
    assert not any("configure a pkasolver environment" in line for line in report.limitations), (
        "the environment IS configured; telling them to configure it sends them to look for nothing"
    )


def test_logd_still_says_to_configure_when_nothing_is_configured(monkeypatch):
    monkeypatch.setattr(pka_providers, "pka_predictor_available", lambda _path: False)
    report = compute_logd(Chem.MolFromSmiles(AMINE), "u", {"pH": 7.4}, "")
    assert any("configure a pkasolver environment" in line for line in report.limitations)


def test_logd_still_fails_loudly_when_the_predictor_errors(predictor):
    predictor("error")
    report = compute_logd(Chem.MolFromSmiles(AMINE), "u", {"pH": 7.4}, "x")
    assert report.cache_state is CacheState.FAILED and "blew up" in report.error


def test_a_molecule_with_nothing_to_ionise_does_not_ask_the_predictor(monkeypatch):
    def boom(*_args):
        raise AssertionError("asked the predictor about a molecule with no ionizable centre")

    monkeypatch.setattr(pka_providers, "pka_predictor_available", boom)
    report = compute_logd(Chem.MolFromSmiles("c1ccccc1"), "u", {"pH": 7.4}, "x")
    assert report.cache_state is not CacheState.FAILED


def test_cns_mpo_says_why_the_pka_term_is_missing(predictor, monkeypatch):
    mol = Chem.MolFromSmiles(AMINE)
    predictor("none")
    declined = "\n".join(compute_cns_mpo(mol, "u", {}, "x").matched)
    assert "pkasolver ran but has no prediction for this structure" in declined
    assert "needs a configured pkasolver environment" not in declined
    assert "/ 5.00" in declined, "the term is still omitted, never assumed favourable"

    monkeypatch.setattr(pka_providers, "pka_predictor_available", lambda _path: False)
    unconfigured = "\n".join(compute_cns_mpo(mol, "u", {}, "").matched)
    assert "needs a configured pkasolver environment" in unconfigured


def test_bbb_inputs_say_why_the_pka_is_missing(predictor):
    mol = Chem.MolFromSmiles(AMINE)
    predictor("none")
    result = compute_bbb_descriptors(mol, "u", None, "x")
    line = next(line for line in result.matched if line.startswith("pKa (most basic)"))
    assert "pkasolver ran but has no prediction for this structure" in line
    assert any("Heavy atoms" in other for other in result.matched), "the other four still compute"

    predictor("values")
    found = compute_bbb_descriptors(mol, "u", None, "x")
    assert any("pKa (most basic): 10.1" in line for line in found.matched)
