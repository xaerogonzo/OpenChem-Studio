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

    def _run_returning(self, monkeypatch, payload):
        monkeypatch.setattr(
            ap.subprocess, "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
        )

    def test_only_reported_endpoints_survive(self, tmp_path, monkeypatch):
        """The model emits 104 columns. The physicochemical block is
        dropped -- RDKit computes it better and locally -- while a reported
        endpoint's percentile twin is KEPT, because "88th percentile among
        approved drugs" is the context that makes 0.9 mean something."""
        interpreter = tmp_path / "python.exe"
        interpreter.write_text("", encoding="utf-8")
        self._run_returning(monkeypatch, {"endpoints": {
            "hERG": 0.9, "CYP3A4_Veith": 0.4,
            "hERG_drugbank_approved_percentile": 88.0,
            "Lipophilicity_AstraZeneca": 2.1,            # we compute this better
            "molecular_weight": 129.2,                   # so is this
        }})
        got = ap.compute_admet(_mol(), str(interpreter))

        assert set(got) == {"hERG", "CYP3A4_Veith", "hERG_drugbank_approved_percentile"}

    def test_a_percentile_without_its_endpoint_is_still_dropped(self, tmp_path, monkeypatch):
        """The twin is kept for its endpoint's sake, not on its own merits.
        A percentile for something we do not report is just a number with
        no row to sit on."""
        interpreter = tmp_path / "python.exe"
        interpreter.write_text("", encoding="utf-8")
        self._run_returning(monkeypatch, {"endpoints": {
            "hERG": 0.9,
            "molecular_weight_drugbank_approved_percentile": 12.0,
        }})
        assert set(ap.compute_admet(_mol(), str(interpreter))) == {"hERG"}

    def test_the_tier_decides_which_endpoints_come_back(self, tmp_path, monkeypatch):
        """Basic must stay exactly what it has always been -- promoting
        endpoints must not change anyone's existing answer."""
        interpreter = tmp_path / "python.exe"
        interpreter.write_text("", encoding="utf-8")
        self._run_returning(monkeypatch, {"endpoints": {
            "hERG": 0.9, "Caco2_Wang": 1.2, "VDss_Lombardo": 3.4,
        }})

        basic = ap.compute_admet(_mol(), str(interpreter), ap.BASIC)
        advanced = ap.compute_admet(_mol(), str(interpreter), ap.ADVANCED)
        research = ap.compute_admet(_mol(), str(interpreter), ap.RESEARCH)

        assert set(basic) == {"hERG"}
        assert set(advanced) == {"hERG", "Caco2_Wang"}
        assert set(research) == {"hERG", "Caco2_Wang", "VDss_Lombardo"}

    def test_an_unknown_tier_falls_back_to_basic(self, tmp_path, monkeypatch):
        """This value arrives from a saved calculator parameter. A stale
        settings file should degrade to the conservative set, not raise."""
        interpreter = tmp_path / "python.exe"
        interpreter.write_text("", encoding="utf-8")
        self._run_returning(monkeypatch, {"endpoints": {"hERG": 0.9, "Caco2_Wang": 1.2}})

        assert set(ap.compute_admet(_mol(), str(interpreter), "nonsense")) == {"hERG"}

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
        assert result.matched[:4] == [
            "[Toxicity and metabolism]",
            "  hERG blockade: 0.93",
            "  Ames mutagenicity: 0.52",
            "  CYP3A4 inhibition: 0.11",
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
    labels = " ".join(e.label for e in ap.REPORTED_ENDPOINTS.values()).lower()
    assert "herg" in labels
    for iso in ("1a2", "2c9", "2c19", "2d6", "3a4"):
        assert iso in labels, f"CYP{iso} missing from the reported set"


class TestTiers:
    """The tiering is a claim about how much each number can be believed,
    so these guard the claim rather than the plumbing."""

    def test_the_basic_tier_is_exactly_the_ten_that_shipped(self):
        """Promoting endpoints must not quietly move what a user who never
        touches the setting sees."""
        assert set(ap.endpoints_for_tier(ap.BASIC)) == {
            "hERG", "AMES",
            "CYP1A2_Veith", "CYP2C9_Veith", "CYP2C19_Veith",
            "CYP2D6_Veith", "CYP3A4_Veith",
            "CYP2C9_Substrate_CarbonMangels",
            "CYP2D6_Substrate_CarbonMangels",
            "CYP3A4_Substrate_CarbonMangels",
        }

    def test_each_tier_includes_the_ones_before_it(self):
        basic = set(ap.endpoints_for_tier(ap.BASIC))
        advanced = set(ap.endpoints_for_tier(ap.ADVANCED))
        research = set(ap.endpoints_for_tier(ap.RESEARCH))

        assert basic < advanced < research

    def test_the_promoted_endpoints_are_the_ones_the_benchmark_cleared(self):
        """benchmarks/admet/README.md is the record; this is the assertion
        that the code agrees with it. Pgp and bioavailability are absent on
        purpose -- both failed the ruler check."""
        promoted = {
            column for column, endpoint in ap.REPORTED_ENDPOINTS.items()
            if endpoint.tier == ap.ADVANCED
        }
        assert promoted == {
            "Caco2_Wang", "Solubility_AqSolDB", "HIA_Hou", "BBB_Martins",
            "PPBR_AZ", "DILI", "LD50_Zhu",
        }

    def test_the_endpoints_that_failed_the_benchmark_are_labelled_not_hidden(self):
        """An absent endpoint reads as "the model cannot do this", which is
        a different and false claim. They are shown, with the reason."""
        for column in ("Pgp_Broccatelli", "VDss_Lombardo", "Half_Life_Obach",
                       "Bioavailability_Ma", "Clearance_Hepatocyte_AZ"):
            endpoint = ap.REPORTED_ENDPOINTS[column]
            assert endpoint.tier == ap.RESEARCH, column
            assert "Not validated here" in endpoint.evidence, column

    def test_every_advanced_endpoint_carries_its_evidence(self):
        """A promoted endpoint without a measurement behind it is the exact
        thing the benchmark exists to prevent."""
        for column, endpoint in ap.REPORTED_ENDPOINTS.items():
            if endpoint.tier == ap.ADVANCED:
                assert "Vendor" in endpoint.evidence, column
                assert "beats molecular weight and logP" in endpoint.evidence, column


class TestThroughTheRegistry:
    """Exercised the way `CalculatorRegistry.compute` calls it, not by
    direct import. `tests/test_calculator_registry.py` carries the arity
    guard for the same reason: a calculator once shipped bound to a
    shadowed same-named function while every direct-import test passed.
    """

    def _registry(self):
        from openchem.bootstrap import build_service_container

        return build_service_container().calculator_registry

    def test_the_tier_option_exists_and_offers_all_three(self, qapp):
        definition = self._registry().get("admet_ml")
        tier = next(p for p in definition.parameters if p.name == "tier")

        assert tier.kind == "choice"
        assert tier.choices == [ap.BASIC, ap.ADVANCED, ap.RESEARCH]
        assert tier.default == ap.BASIC

    def test_the_tier_option_actually_changes_the_result(self, qapp, monkeypatch):
        """An inert option is worse than a missing one -- it looks like a
        working control. This drives the tier through the registry and
        checks the rendered text differs."""
        monkeypatch.setattr(
            ap, "compute_admet",
            lambda mol, path, tier=ap.BASIC: {
                column: 0.5 for column in ap.endpoints_for_tier(tier)
            },
        )
        registry = self._registry()
        mol = _mol()

        basic = registry.compute("admet_ml", mol, "m", {"tier": ap.BASIC})
        advanced = registry.compute("admet_ml", mol, "m", {"tier": ap.ADVANCED})

        assert any("Caco-2" in line for line in advanced.matched)
        assert not any("Caco-2" in line for line in basic.matched)
        assert len(advanced.matched) > len(basic.matched)


class TestEndpointLines:
    def test_a_percentile_rides_with_its_endpoint_rather_than_as_a_row(self):
        lines = ap.endpoint_lines(
            {"hERG": 0.93, "hERG_drugbank_approved_percentile": 88.0},
            {"decimal_places": 2},
        )

        assert lines == ["[Toxicity and metabolism]",
                         "  hERG blockade: 0.93  (88th percentile among approved drugs)"]

    @pytest.mark.parametrize(
        "percentile,expected",
        [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"),
         (11, "11th"), (12, "12th"), (13, "13th"),
         (21, "21st"), (92, "92nd"), (91, "91st"), (100, "100th")],
    )
    def test_percentiles_read_as_english(self, percentile, expected):
        """A first pass rendered every one of these as "Nth" -- "92th",
        "91th" -- which is the kind of thing that makes a number look
        machine-generated and therefore unconsidered."""
        lines = ap.endpoint_lines({"hERG": 0.5, "hERG_drugbank_approved_percentile": percentile})

        assert f"({expected} percentile" in lines[1]

    def test_units_are_shown_for_the_endpoints_that_have_them(self):
        """A Caco-2 number without its units is not a permeability, and
        these are not all probabilities any more."""
        lines = ap.endpoint_lines({"Caco2_Wang": -4.16}, {"decimal_places": 2})

        assert any("log(10⁻⁶ cm/s)" in line for line in lines)

    def test_each_tier_gets_its_own_heading(self):
        lines = ap.endpoint_lines({"hERG": 0.9, "Caco2_Wang": -4.2, "VDss_Lombardo": 3.0})
        headings = [line for line in lines if line.startswith("[")]

        assert len(headings) == 3
        assert "NOT validated" in headings[-1]

    def test_a_research_number_never_appears_without_its_caveat(self):
        lines = ap.endpoint_lines({"VDss_Lombardo": 3.0})
        value_line = next(i for i, line in enumerate(lines) if "Volume of distribution" in line)

        assert "Not validated here" in lines[value_line + 1]
