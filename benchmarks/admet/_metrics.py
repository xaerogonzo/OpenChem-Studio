"""Scoring metrics, implemented on numpy alone.

Deliberately dependency-free beyond numpy so the scorer runs in the
project's own environment rather than needing the ADMET sidecar's
scikit-learn. A benchmark nobody can run because of its dependencies gets
run once and then quoted forever.
"""

from __future__ import annotations

import numpy as np


def _ranks(values: np.ndarray) -> np.ndarray:
    """Average ranks, so ties do not bias the rank statistics below."""
    order = values.argsort()
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values), dtype=float)
    # Average the ranks within each run of equal values.
    sorted_values = values[order]
    start = 0
    for stop in range(1, len(values) + 1):
        if stop == len(values) or sorted_values[stop] != sorted_values[start]:
            ranks[order[start:stop]] = ranks[order[start:stop]].mean()
            start = stop
    return ranks


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    return pearson(_ranks(x), _ranks(y))


def auroc(labels: np.ndarray, scores: np.ndarray) -> float:
    """Area under the ROC curve via the Mann-Whitney U identity.

    The rank form rather than a swept threshold: it is exact with ties
    (average ranks) and needs no grid.
    """
    positives = labels == 1
    n_pos, n_neg = int(positives.sum()), int((~positives).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = _ranks(scores)
    return float((ranks[positives].sum() - n_pos * (n_pos - 1) / 2) / (n_pos * n_neg))


def auprc(labels: np.ndarray, scores: np.ndarray) -> float:
    """Average precision -- the step-wise area under precision/recall.

    Reported because TDC's own leaderboard uses it for the heavily
    imbalanced classification endpoints, where AUROC flatters a model that
    only ever ranks the majority class well.
    """
    positives = int((labels == 1).sum())
    if positives == 0:
        return float("nan")
    order = np.argsort(-scores)
    hits = labels[order] == 1
    cumulative_hits = np.cumsum(hits)
    precision = cumulative_hits / np.arange(1, len(labels) + 1)
    return float(precision[hits].sum() / positives)


def r2(truth: np.ndarray, prediction: np.ndarray) -> float:
    """Coefficient of determination against the truth's own mean.

    Can go negative, and that is the point: a negative R^2 means the
    prediction is worse than answering with the training mean every time,
    which is a fact worth surfacing rather than clipping to zero.
    """
    residual = float(((truth - prediction) ** 2).sum())
    total = float(((truth - truth.mean()) ** 2).sum())
    if total == 0:
        return float("nan")
    return 1.0 - residual / total


def mae(truth: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.abs(truth - prediction).mean())
