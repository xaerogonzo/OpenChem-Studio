"""Confidence intervals for per-atom NMR statistics.

RESAMPLE MOLECULES, NOT ATOMS. This is the whole point and it was reasoned
out once already in `significance.py`: atoms of one molecule share a
structure, a geometry and one person's assignment, so their errors are
correlated. Resampling them independently pretends there is more evidence
than there is and produces intervals that are too narrow -- exactly the
mistake that would let a 0.1 ppm difference look real.

With a benchmark of tens of molecules the intervals come out wide. That is
the honest answer, not a defect: "not distinguishable" is a legitimate
result to report and this project has shipped it before.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np


def resample(
    by_molecule: Sequence[Sequence[float]],
    statistic: Callable[[np.ndarray], float],
    draws: int = 4000,
    seed: int = 0,
    percentiles: tuple[float, float] = (2.5, 97.5),
) -> tuple[float, float]:
    """A percentile interval for `statistic`, resampling whole molecules.

    `by_molecule` is one sequence of per-atom values per molecule. Empty
    molecules are allowed (a strategy may decline a whole spectrum) but a
    draw that lands on nothing but empties is skipped rather than counted
    as zero.
    """
    groups = [np.asarray(g, dtype=float) for g in by_molecule if len(g)]
    if not groups:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    values = np.empty(draws)
    for i in range(draws):
        pick = rng.integers(0, len(groups), len(groups))
        sample = np.concatenate([groups[j] for j in pick])
        values[i] = statistic(sample)
    low, high = np.percentile(values, percentiles)
    return float(low), float(high)


def paired_verdict(low: float, high: float, better_when: str = "negative") -> str:
    """Read a paired-difference interval out loud.

    `low`/`high` bound (challenger - baseline), so an interval entirely
    below zero means the challenger is better.
    """
    if np.isnan(low) or np.isnan(high):
        return "no data"
    if high < 0:
        return "better" if better_when == "negative" else "worse"
    if low > 0:
        return "worse" if better_when == "negative" else "better"
    return "not distinguishable"


def mean(values: np.ndarray) -> float:
    return float(values.mean())
