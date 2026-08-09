"""The conformer benchmark's set-overlap metric, against known answers.

Counts alone hide the interesting instability: five seeds each returning
14 conformers looks stable and is not, if they are 14 DIFFERENT
conformers every time. `_set_overlap` is what tells those apart, so it
has to be trustworthy -- and a similarity metric is exactly the kind of
thing that can return plausible numbers while measuring nothing.

Both ends are pinned here. Identical runs must score 1.0; runs that share
nothing must score the floor of 1/nseeds. A metric that cannot reach both
is not measuring overlap.

`build_predictions.py` lives under benchmarks/ rather than in the
package, so it is loaded by path -- same as
`test_naming_benchmark_scoring.py`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem.conformer_providers import RDKitConformerProvider, distinct_conformers

_BUILD_PY = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "conformers" / "build_predictions.py"
)


@pytest.fixture(scope="module")
def build():
    spec = importlib.util.spec_from_file_location("_bench_build_conformers", _BUILD_PY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pool():
    """A set of genuinely distinct conformers to slice up.

    Seeded, so the two known-answer cases below are reproducible rather
    than depending on what the embedder happened to find.
    """
    batch = RDKitConformerProvider(random_seed=0).generate_conformer_batch(
        Chem.MolFromSmiles("OCCO"), 40, optimize=True
    )
    kept = distinct_conformers(batch.results)
    assert len(kept) >= 5, f"need at least 5 to slice into 5 disjoint runs, got {len(kept)}"
    return kept


def test_identical_runs_score_perfect_overlap(build, pool):
    """The ceiling. Five copies of one run share everything."""
    overlap = build._set_overlap([list(pool)] * 5)
    assert overlap["union"] == len(pool)
    assert overlap["coverage"] == pytest.approx(1.0)
    assert overlap["jaccard_mean"] == pytest.approx(1.0)
    assert overlap["jaccard_min"] == pytest.approx(1.0)


def test_disjoint_runs_score_the_floor(build, pool):
    """The floor, and the case the metric exists to detect.

    Five runs that share NOTHING must score coverage 1/5 and jaccard 0 --
    each run finding its own private slice of the space. Without this
    end pinned, a metric that always returned a comfortable number would
    look identical to a working one on real data.
    """
    usable = len(pool) // 5 * 5
    slices = [pool[start:usable:5] for start in range(5)]
    assert all(slices), "a slice came out empty -- the split is not exercising the floor"

    overlap = build._set_overlap(slices)
    assert overlap["coverage"] == pytest.approx(0.2, abs=0.06)
    assert overlap["jaccard_mean"] == pytest.approx(0.0, abs=0.02)


def test_the_union_is_never_smaller_than_any_single_run(build, pool):
    """A sanity property that a broken implementation breaks first: the
    pooled set cannot be smaller than the largest run that went into it."""
    runs = [pool[:3], pool[1:], pool[:1]]
    overlap = build._set_overlap(runs)
    assert overlap["union"] >= max(len(run) for run in runs)


def test_a_single_run_reports_nothing_rather_than_a_fake_perfect_score(build, pool):
    """One seed has no other seed to agree with. Reporting 1.0 there would
    read as "perfectly stable" for a measurement never made."""
    assert build._set_overlap([list(pool)]) == {}
    assert build._set_overlap([]) == {}
