"""LogD, with the curve it lies on, as one result.

`logd_curve` was a second calculator sampling the same Henderson-Hasselbalch
function across pH, so reading logD at one pH and seeing the curve meant two
runs. The curve is declared on LogD's report now and `logd_curve` is retired.

**THE SCALAR MUST NOT MOVE.** The values below were recorded from the
previous implementation (which returned the lines "logD = 0.58 at pH 7.4
(Henderson-Hasselbalch)" and so on) before any of this changed, at full
precision from the same functions it called; each branch is pinned.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from rdkit import Chem

import openchem.chem.pka_providers as pka_providers
from openchem.chem.descriptor_providers import compute_logd

IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
PROPRANOLOL = "CC(C)NCC(O)COc1cccc2ccccc12"
CAFFEINE = "Cn1cnc2c1c(=O)n(C)c(=O)n2C"

#: (smiles, pKa list, pH) -> the previous implementation's scalar.
RECORDED_HH = {
    (IBUPROFEN, 2.0): 3.072666029457912,
    (IBUPROFEN, 7.4): 0.58179691952152,
    (PROPRANOLOL, 2.0): -4.842500016511415,
    (PROPRANOLOL, 7.4): 0.5533721987714104,
}
RECORDED_DIMORPHITE = {
    (IBUPROFEN, 2.0): 3.073200000000001,
    (IBUPROFEN, 7.4): 1.7384999999999997,
    (PROPRANOLOL, 2.0): 1.5513000000000006,
    (PROPRANOLOL, 7.4): 1.5513000000000006,
}
PKAS = {IBUPROFEN: [4.91], PROPRANOLOL: [9.42]}


@pytest.fixture
def pkasolver(monkeypatch):
    def configure(available: bool, smiles: str = IBUPROFEN):
        monkeypatch.setattr(pka_providers, "pka_predictor_available", lambda _path: available)
        monkeypatch.setattr(
            pka_providers, "compute_pka",
            lambda _mol, _path: [SimpleNamespace(value=v) for v in PKAS.get(smiles, [])],
        )
    return configure


def _scalar(report):
    return next(f for f in report.facts if f.label.startswith("LogD at pH")).value


@pytest.mark.parametrize(("smiles", "ph"), sorted(RECORDED_HH))
def test_the_henderson_hasselbalch_scalar_is_unchanged(pkasolver, smiles, ph):
    pkasolver(True, smiles)
    report = compute_logd(Chem.MolFromSmiles(smiles), "u", {"pH": ph}, "x")
    assert _scalar(report) == pytest.approx(RECORDED_HH[(smiles, ph)], abs=1e-12)


@pytest.mark.parametrize(("smiles", "ph"), sorted(RECORDED_DIMORPHITE))
def test_the_approximation_scalar_is_unchanged_and_draws_no_curve(pkasolver, smiles, ph):
    pkasolver(False, smiles)
    report = compute_logd(Chem.MolFromSmiles(smiles), "u", {"pH": ph}, "x")
    assert _scalar(report) == pytest.approx(RECORDED_DIMORPHITE[(smiles, ph)], abs=1e-12)
    assert report.charts == ()
    assert any("No LogD-vs-pH curve" in text for text in report.limitations)


def test_no_ionizable_centre_is_logp_everywhere_and_says_why(pkasolver):
    pkasolver(True, CAFFEINE)
    report = compute_logd(Chem.MolFromSmiles(CAFFEINE), "u", {"pH": 7.4}, "x")
    assert _scalar(report) == pytest.approx(-1.0293, abs=1e-12)
    (chart,) = report.charts
    assert "pH-independent" in chart.title
    assert all(y == pytest.approx(-1.0293, abs=1e-12) for _x, y in chart.series[0].points)


@pytest.mark.parametrize("ph", [7.4, 5.13, 2.0])
def test_the_curve_at_the_chosen_ph_is_the_scalar_itself(pkasolver, ph):
    """The chosen pH is a SAMPLE, so the reading there is the number above
    rather than its nearest neighbour -- compared as numbers, not strings."""
    pkasolver(True, IBUPROFEN)
    report = compute_logd(Chem.MolFromSmiles(IBUPROFEN), "u", {"pH": ph}, "x")
    (chart,) = report.charts
    at = dict(chart.series[0].points)
    assert ph in at, "the chosen pH was not sampled"
    assert at[ph] == _scalar(report)


def test_the_curve_honours_the_range_parameters(pkasolver):
    pkasolver(True, IBUPROFEN)
    report = compute_logd(
        Chem.MolFromSmiles(IBUPROFEN), "u", {"pH": 7.4, "ph_min": 6.0, "ph_max": 8.0, "ph_step": 0.5}, "x"
    )
    xs = [x for x, _y in report.charts[0].series[0].points]
    assert xs == [6.0, 6.5, 7.0, 7.4, 7.5, 8.0]


def test_the_scalar_does_not_come_from_the_curve(pkasolver, monkeypatch):
    """The scalar is computed ON ITS OWN, at the chosen pH, before the curve
    is sampled. Rerouting it through the curve would give the same number
    today by construction -- so the ORDER of calls is what is pinned, since a
    value comparison could not see that mutation."""
    import openchem.chem.logd as logd

    pkasolver(True, IBUPROFEN)
    real = logd.logd_from_pkas
    calls = []

    def recording(mol, ph, pkas):
        calls.append(ph)
        return real(mol, ph, pkas)

    monkeypatch.setattr(logd, "logd_from_pkas", recording)
    report = compute_logd(Chem.MolFromSmiles(IBUPROFEN), "u", {"pH": 7.4}, "x")
    assert calls[0] == 7.4, "the scalar is no longer computed first, at the chosen pH, on its own"
    assert _scalar(report) == pytest.approx(RECORDED_HH[(IBUPROFEN, 7.4)], abs=1e-12)


def test_logd_curve_is_retired_and_still_findable():
    from openchem.bootstrap import build_service_container
    from openchem.domain.calculator_taxonomy import RETIREMENTS

    registry = build_service_container().calculator_registry
    assert registry.get("logd_curve") is None
    retired = RETIREMENTS["logd_curve"]
    assert retired.replaced_by == "logd" and retired.display_name == "LogD vs pH"
    assert {"ph_min", "ph_max", "ph_step"} <= {p.name for p in registry.get("logd").parameters}
