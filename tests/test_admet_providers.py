"""hERG / CYP prediction via the ADMET-AI sidecar.

The endpoint itself was deferred three times as impossible, so the tests
that matter most here are the ones about DEGRADING HONESTLY: with no
environment configured this must offer to install one, not error, and it
must never present a model output as a measurement.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from rdkit import Chem

from openchem.chem import admet_providers as ap

METFORMIN = "CN(C)C(=N)N=C(N)N"


def _mol():
    return Chem.MolFromSmiles(METFORMIN)


class TestAvailability:
    def test_unconfigured_is_not_available(self):
        for value in (None, "", "   "):
            assert ap.admet_available(value) is False

    def test_a_missing_path_is_not_available(self, tmp_path):
        assert ap.admet_available(str(tmp_path / "nope" / "python.exe")) is False

    def test_availability_does_not_spawn_a_subprocess(self, tmp_path, monkeypatch):
        """Greying out a menu item must not cost a torch import. This is
        called from UI code paths, so it stays existence-only."""
        interpreter = tmp_path / "python.exe"
        interpreter.write_text("", encoding="utf-8")

        def explode(*a, **k):
            raise AssertionError("admet_available must not run a subprocess")

        monkeypatch.setattr(ap.subprocess, "run", explode)
        assert ap.admet_available(str(interpreter)) is True


class TestComputeAdmet:
    def test_unconfigured_returns_none_rather_than_raising(self):
        """None means "not set up", which the UI turns into an offer to
        install. An exception would read as a fault the user caused."""
        assert ap.compute_admet(_mol(), None) is None

    def test_only_reported_endpoints_survive(self, tmp_path, monkeypatch):
        """The model emits 104 columns, including a percentile twin for
        every endpoint. Showing all of them would bury hERG."""
        interpreter = tmp_path / "python.exe"
        interpreter.write_text("", encoding="utf-8")
        payload = {"endpoints": {
            "hERG": 0.9, "CYP3A4_Veith": 0.4,
            "hERG_drugbank_approved_percentile": 88.0,   # noise
            "Lipophilicity_AstraZeneca": 2.1,            # we compute this better
        }}
        monkeypatch.setattr(
            ap.subprocess, "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
        )
        got = ap.compute_admet(_mol(), str(interpreter))

        assert set(got) == {"hERG", "CYP3A4_Veith"}
        assert all(k in ap.REPORTED_ENDPOINTS for k in got)

    def test_a_runner_error_is_raised_not_silently_empty(self, tmp_path, monkeypatch):
        interpreter = tmp_path / "python.exe"
        interpreter.write_text("", encoding="utf-8")
        monkeypatch.setattr(
            ap.subprocess, "run",
            lambda *a, **k: SimpleNamespace(
                returncode=1, stdout=json.dumps({"error": "no model"}), stderr=""),
        )
        with pytest.raises(RuntimeError, match="no model"):
            ap.compute_admet(_mol(), str(interpreter))

    def test_progress_bar_noise_on_stdout_is_reported_clearly(self, tmp_path, monkeypatch):
        """pytorch-lightning prints its progress bar to stdout, which used
        to land mid-JSON and fail at column 1. The runner redirects it to
        stderr; if that regresses, the message must name the problem
        rather than surfacing a bare JSONDecodeError."""
        interpreter = tmp_path / "python.exe"
        interpreter.write_text("", encoding="utf-8")
        monkeypatch.setattr(
            ap.subprocess, "run",
            lambda *a, **k: SimpleNamespace(
                returncode=0, stdout='Predicting --- 1/1\n{"endpoints": {}}', stderr=""),
        )
        with pytest.raises(RuntimeError, match="Unreadable output"):
            ap.compute_admet(_mol(), str(interpreter))


def test_the_rule_based_herg_checklist_still_exists():
    """The model complements the rule-based checklist; it does not
    replace it. The checklist is free, offline, and states which
    structural correlates are present rather than guessing a probability."""
    from openchem.chem.descriptor_providers import _HERG_RISK_NAME

    assert "hERG" in _HERG_RISK_NAME
    assert "not a prediction" in _HERG_RISK_NAME


def test_reported_endpoints_cover_what_was_asked_for():
    labels = " ".join(ap.REPORTED_ENDPOINTS.values()).lower()
    assert "herg" in labels
    for iso in ("1a2", "2c9", "2c19", "2d6", "3a4"):
        assert iso in labels, f"CYP{iso} missing from the reported set"
