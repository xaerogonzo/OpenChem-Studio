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
from openchem.domain.common import CacheState

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


class TestAdmetEndpointsResult:
    """`compute_admet_endpoints` wraps `compute_admet` into an AlertResult.

    Every one of its three return paths shipped passing a `description=`
    keyword that `AlertResult` does not define, so all three raised
    `TypeError` on construction -- swallowed by the broad `except` in
    `_CalculatorRunnable.run`, which turned it into a generic "calculator
    failed". The calculator was 100% broken with a green suite, so these
    tests exist mainly to construct each path at all.
    """

    def _endpoints(self, mol, parameters=None, interpreter_path="python.exe"):
        from openchem.chem.descriptor_providers import compute_admet_endpoints

        return compute_admet_endpoints(mol, "uuid-1", parameters, interpreter_path)

    def test_all_three_paths_construct(self, monkeypatch):
        """The regression guard. Each path is exercised separately below;
        this one asserts only that none of them raises, which is the exact
        thing that was broken."""
        from openchem.domain.scientific_result import AlertResult

        def broken(*a, **k):
            raise RuntimeError("torch is not installed")

        cases = {
            "raised": broken,
            "unconfigured": lambda *a, **k: None,
            "success": lambda *a, **k: {"hERG": 0.9},
        }
        for label, fake in cases.items():
            monkeypatch.setattr(ap, "compute_admet", fake)
            result = self._endpoints(_mol())
            assert isinstance(result, AlertResult), label
            assert result.molecule_uuid == "uuid-1", label
            assert result.matched, f"{label} produced nothing to show"

    def test_a_broken_environment_reports_the_real_reason(self, monkeypatch):
        monkeypatch.setattr(
            ap, "compute_admet",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("torch is not installed")),
        )
        result = self._endpoints(_mol())

        assert result.cache_state is CacheState.FAILED
        assert "torch is not installed" in result.matched[0]
        assert result.error == "torch is not installed"

    def test_an_unconfigured_environment_offers_the_install_guidance(self, monkeypatch):
        """The reason this path exists: with nothing set up the user must
        get the "here is what ADMET-AI is and why it ships separately"
        text, not a bare failure. That guidance was unreachable while the
        constructor raised."""
        monkeypatch.setattr(ap, "compute_admet", lambda *a, **k: None)
        result = self._endpoints(_mol(), interpreter_path=None)

        assert result.cache_state is CacheState.FAILED
        assert "Not configured" in result.matched[0]
        assert "installed separately" in result.matched[0]

    def test_predictions_are_sorted_worst_first(self, monkeypatch):
        monkeypatch.setattr(
            ap, "compute_admet",
            lambda *a, **k: {"CYP3A4_Veith": 0.11, "hERG": 0.93, "AMES": 0.52},
        )
        result = self._endpoints(_mol(), {"decimal_places": 2})

        assert result.cache_state is CacheState.COMPLETED
        assert result.error is None
        assert result.matched[:3] == [
            "hERG blockade: 0.93",
            "Ames mutagenicity: 0.52",
            "CYP3A4 inhibition: 0.11",
        ]

    def test_the_model_output_caveat_reaches_the_rendered_text(self, monkeypatch):
        """The whole reason the caveat lives in `matched` rather than in a
        new `description` field: `matched` is what both consumers render
        (PropertyPanel and the clipboard). A description field would have
        been read by neither, so the "predictions, not measurements"
        warning would have sat in the object unseen."""
        from openchem.ui.result_clipboard import result_to_text

        monkeypatch.setattr(ap, "compute_admet", lambda *a, **k: {"hERG": 0.93})
        result = self._endpoints(_mol())

        assert "not measurements" in result.matched[-1], "the caveat must be last"
        assert "not measurements" in result_to_text(result)

    def test_no_endpoints_says_so_and_skips_the_caveat(self, monkeypatch):
        """An empty dict is not None -- it means the runner answered but
        nothing it returned was in REPORTED_ENDPOINTS. There are no
        probabilities to caveat, so the caveat would be noise."""
        monkeypatch.setattr(ap, "compute_admet", lambda *a, **k: {})
        result = self._endpoints(_mol())

        assert result.matched == ["The model returned no reported endpoint."]


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
