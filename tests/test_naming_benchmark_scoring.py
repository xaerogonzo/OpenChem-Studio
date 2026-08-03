"""Tests for the naming benchmark's scoring helpers.

The benchmark is the correctness oracle for work on the vendored IUPAC
engine -- "the benchmark outranks the tests" -- so its own machinery needs
to be trustworthy. Two pieces in particular fail silently if they break:

* the **run-to-run delta**, which is the only thing that makes a swap
  visible (one molecule fixed, another broken, headline score unmoved);
* the **second round-trip gate**, which must compare FULL InChIKeys.

`score.py` lives under benchmarks/ rather than in the package, so it is
loaded by path here.
"""

from __future__ import annotations

from types import SimpleNamespace

import importlib.util
from pathlib import Path

import pytest

_SCORE_PY = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "naming" / "score.py"
)


@pytest.fixture(scope="module")
def score():
    spec = importlib.util.spec_from_file_location("_bench_score", _SCORE_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ROWS = [
    {"label": "benzyl cation"},
    {"label": "metformin"},
    {"label": "toluene"},
    {"label": "phenol"},
]


def _scorable_rows(n: int) -> list[dict]:
    """`n` corpus-shaped rows, enough for report() to run over."""
    return [
        {
            "label": f"mol{i}",
            "category": "test",
            "smiles": "C",
            "has_stereo": False,
            "pubchem_name": None,
        }
        for i in range(n)
    ]


class TestDelta:
    def test_classifies_fixed_regressed_and_lateral_moves(self, score):
        previous = ["wrong_structure", "exact", "exact", "equivalent"]
        current = ["exact", "wrong_structure", "exact", "exact"]
        got = score.delta(ROWS, current, previous)

        assert ("FIXED", "benzyl cation", "wrong_structure", "exact") in got
        assert ("REGRESSED", "metformin", "exact", "wrong_structure") in got
        # equivalent -> exact stays inside SUCCESS, so it is neither.
        assert ("changed", "phenol", "equivalent", "exact") in got
        # Unchanged rows are not reported.
        assert not any(row[1] == "toluene" for row in got)

    def test_regressions_are_listed_first(self, score):
        """A regression is the only entry that demands action, so it must
        not be buried under a list of fixes."""
        previous = ["wrong_structure", "exact", "exact", "equivalent"]
        current = ["exact", "wrong_structure", "exact", "exact"]
        got = score.delta(ROWS, current, previous)
        assert got[0][0] == "REGRESSED"

    @pytest.mark.parametrize("previous", [None, [], ["exact"]])
    def test_degrades_quietly_without_a_usable_baseline(self, score, previous):
        """A first run, or a corpus that changed size, must not raise --
        the delta is a convenience and cannot be allowed to fail scoring."""
        current = ["exact"] * len(ROWS)
        assert score.delta(ROWS, current, previous) == []

    def test_identical_runs_report_nothing(self, score):
        current = ["exact", "equivalent", "exact", "exact"]
        assert score.delta(ROWS, current, current) == []


class TestCorpusLengthGuard:
    def test_mismatched_prediction_count_is_refused(self, score):
        """A predictions file written against an older, smaller corpus must
        not be scored against a newer one.

        `zip()` truncates to the shorter list, so 124 predictions against a
        165-row corpus would report a model's 88/124 as "88/165" -- a wrong
        comparison that looks like a real one. The corpus grew when the
        charged-species categories were added, stranding every predictions
        file recorded before that.
        """
        corpus = _scorable_rows(165)
        with pytest.raises(SystemExit, match="124 predictions"):
            score.report("stale run", corpus, ["anything"] * 124)

    def test_matching_counts_are_accepted(self, score):
        corpus = _scorable_rows(5)
        # Empty predictions short-circuit to NO_PREDICTION, so this stays a
        # pure count check and never shells out to OPSIN.
        out = score.report("ok run", corpus, [""] * len(corpus))
        assert out["total"] == len(corpus)
        assert out["correct"] == 0


class TestInChIKeyGate:
    def test_full_key_distinguishes_protonation(self, score):
        """The charge defects this benchmark hunts differ ONLY in the
        InChIKey's final block: guanidinium and guanidine share the
        14-character skeleton `ZRALSGWEFCBTJO`. Comparing skeleton blocks
        would pass exactly the bugs we are looking for."""
        cation = score._key("[NH2+]=C(N)N")
        neutral = score._key("N=C(N)N")
        assert cation is not None and neutral is not None
        assert cation.split("-")[0] == neutral.split("-")[0]
        assert cation != neutral

    def test_returns_none_for_unparsable_input(self, score):
        """A key that cannot be built must not be mistaken for a mismatch;
        classify() falls back to the SMILES verdict alone in that case."""
        assert score._key("not a smiles") is None

    def test_tautomers_share_a_key(self, score):
        """InChI normalises mobile hydrogens, so the two 1,2,3-triazole
        tautomers collapse to one key while canonical SMILES keeps them
        apart. That divergence is real information, which is why the
        scorer surfaces it as `gate_disagreement` rather than deciding."""
        assert score._key("c1cn[nH]n1") == score._key("c1c[nH]nn1")


class TestTautomerOutcome:
    """The `tautomer` class exists for metformin, but the reason it is
    safe is what it REFUSES to accept. Both halves are tested."""

    @staticmethod
    def _row(smiles: str, name: str | None = None) -> dict:
        return {"smiles": smiles, "pubchem_name": name, "category": "t", "has_stereo": False}

    def test_metformin_is_scored_as_a_tautomer_not_a_failure(self, score, monkeypatch):
        """The engine answers `1,1-dimethylbiguanide`, which IS metformin.
        OPSIN parses it back to a different tautomer than the corpus
        stores, so the SMILES gate alone called it a different molecule."""

        monkeypatch.setattr(
            score.n, "opsin_structure_for_name",
            lambda name: SimpleNamespace(smiles="CN(C(=N)NC(=N)N)C"),
        )
        outcome = score.classify(self._row("CN(C)C(=N)N=C(N)N"), "1,1-dimethylbiguanide")

        assert outcome == score.TAUTOMER
        assert outcome in score.SUCCESS

    @pytest.mark.parametrize(
        "expected, parsed_back, what",
        [
            ("NC(N)=N", "NC(N)=[NH2+]", "guanidine vs guanidinium"),
            ("Cc1ccccc1", "[CH2+]c1ccccc1", "toluene vs benzyl cation"),
        ],
    )
    def test_charge_defects_are_still_caught(self, score, monkeypatch, expected, parsed_back, what):
        """These are the defects the corpus was EXTENDED to catch -- the
        engine used to name the benzyl cation as toluene. If the tautomer
        class ever swallowed one of these, the benchmark would stop
        measuring the thing it was built for."""

        monkeypatch.setattr(
            score.n, "opsin_structure_for_name",
            lambda name: SimpleNamespace(smiles=parsed_back),
        )
        outcome = score.classify(self._row(expected), "some name")

        assert outcome not in score.SUCCESS, f"{what} must not be scored as a success"

    def test_an_unadjudicable_tautomer_is_not_treated_as_a_match(self, score, monkeypatch):
        """`_canonical_tautomer` returning None means "cannot tell", which
        must never be read as "same"."""

        monkeypatch.setattr(score, "_canonical_tautomer", lambda smiles: None)
        monkeypatch.setattr(
            score.n, "opsin_structure_for_name",
            lambda name: SimpleNamespace(smiles="CN(C(=N)NC(=N)N)C"),
        )
        assert score.classify(self._row("CN(C)C(=N)N=C(N)N"), "x") == score.GATE_DISAGREE
