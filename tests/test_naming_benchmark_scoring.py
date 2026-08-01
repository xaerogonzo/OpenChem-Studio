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
