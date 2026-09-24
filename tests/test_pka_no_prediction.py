"""A predictor that RAN and returned nothing is a limit of the model, not a crash.

`resolve_pkas` reported "the pKa predictor ran but returned no values" as
`PKaStatus.FAILED` -- the same status as a predictor that raised -- so
solubility said "Failed" for a molecule the predictor merely had no answer for,
and sent the person looking for a broken installation. The pH curves were
worse: they treated the empty answer as a real one and drew a one-species
"curve". Three outcomes, three words: nothing configured (NEEDS_SETUP), a
working predictor with no answer (a limit), a predictor that errored (a fault).
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem import ph_curves, pka_providers
from openchem.chem.pka_providers import PKaStatus
from openchem.chem.solubility import compute_solubility, resolve_pkas
from openchem.domain.common import CacheState
from openchem.domain.refusal_kinds import NO_PKA_PREDICTION, SIDECAR_NOT_CONFIGURED
from openchem.domain.result_status import FAILED, INAPPLICABLE, NEEDS_SETUP, status_of

ACETIC_ACID = "CC(=O)O"
#: The path is never used -- the predictor itself is replaced -- but it must be
#: truthy for the code that gates on "is a sidecar configured".
_INTERPRETER = "predictor-stub"


def _predictor(monkeypatch, *, returns=None, raises=None):
    monkeypatch.setattr(pka_providers, "pka_predictor_available", lambda path: True)

    def compute_pka(mol, path):
        if raises is not None:
            raise raises
        return returns

    monkeypatch.setattr(pka_providers, "compute_pka", compute_pka)


def test_a_predictor_that_returns_nothing_is_no_prediction_not_failed(monkeypatch):
    _predictor(monkeypatch, returns=[])
    resolution = resolve_pkas(Chem.MolFromSmiles(ACETIC_ACID), "", _INTERPRETER)
    assert resolution.status is PKaStatus.NO_PREDICTION
    assert "no prediction" in resolution.reason


def test_a_predictor_that_errored_is_still_a_failure(monkeypatch):
    """The narrow half: "an empty answer is no prediction" must not swallow a
    real crash."""
    _predictor(monkeypatch, raises=RuntimeError("the sidecar exploded"))
    resolution = resolve_pkas(Chem.MolFromSmiles(ACETIC_ACID), "", _INTERPRETER)
    assert resolution.status is PKaStatus.FAILED
    assert "exploded" in resolution.reason


def test_solubility_reports_no_prediction_as_a_limit(monkeypatch):
    _predictor(monkeypatch, returns=[])
    result = compute_solubility(
        Chem.MolFromSmiles(ACETIC_ACID), "u", {"model": "esol"}, interpreter_path=_INTERPRETER
    )
    assert result.cache_state is CacheState.FAILED
    assert result.provenance.parameters["refusal"] == NO_PKA_PREDICTION
    assert result.inapplicable is True
    assert status_of(result, structure_version=0) == INAPPLICABLE


def test_solubility_still_reports_a_crashed_predictor_as_a_fault(monkeypatch):
    _predictor(monkeypatch, raises=RuntimeError("boom"))
    result = compute_solubility(
        Chem.MolFromSmiles(ACETIC_ACID), "u", {"model": "esol"}, interpreter_path=_INTERPRETER
    )
    assert result.provenance.parameters["refusal"] == "PKA_FAILED"
    assert result.inapplicable is False
    assert status_of(result, structure_version=0) == FAILED


def test_solubility_with_no_predictor_configured_needs_setup(monkeypatch):
    """`SIDECAR_NOT_CONFIGURED` is a NEEDS_SETUP refusal, and reaches the
    launcher as one from a producer that never declared a kind."""
    monkeypatch.setattr(pka_providers, "pka_predictor_available", lambda path: False)
    result = compute_solubility(
        Chem.MolFromSmiles(ACETIC_ACID), "u", {"model": "esol"}, interpreter_path=""
    )
    assert result.provenance.parameters["refusal"] == SIDECAR_NOT_CONFIGURED
    assert status_of(result, structure_version=0) == NEEDS_SETUP


def test_a_typed_pka_beats_a_predictor_with_nothing_to_say(monkeypatch):
    """Manual values are consulted before the predictor is, so the empty
    answer never even happens -- the message the refusal gives has to be true."""
    _predictor(monkeypatch, returns=[])
    resolution = resolve_pkas(Chem.MolFromSmiles(ACETIC_ACID), "4.76", _INTERPRETER)
    assert resolution.status is PKaStatus.FOUND and resolution.values == (4.76,)


@pytest.mark.parametrize("smiles", [ACETIC_ACID, "CCN"])
def test_a_ph_curve_refuses_rather_than_drawing_a_flat_line(monkeypatch, smiles):
    """The predictor has no value, so there is nothing to plot: this used to
    return an empty pKa list and draw a one-species distribution."""
    _predictor(monkeypatch, returns=[])
    result = ph_curves.compute_pka_distribution(
        Chem.MolFromSmiles(smiles), "u", {}, interpreter_path=_INTERPRETER
    )
    assert result.cache_state is CacheState.FAILED
    assert result.provenance.parameters["refusal"] == NO_PKA_PREDICTION
    assert result.inapplicable is True
    assert not result.series, "no curve was drawn"
    assert status_of(result, structure_version=0) == INAPPLICABLE
