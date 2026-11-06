"""Decision rules for the CNNaffinity ranking-power test, as pure functions.

`PREREGISTRATION_CNN_AFFINITY.md` is that text as code. Populations reuse
`gnina_core.TRAINING_OVERLAP`. Spearman and the shipped median live in
`_stats` / `AffinityRange`. Nothing here knows about WSL or files.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

import gnina_core as pose_core
from _stats import spearman

TRAINING_OVERLAP = pose_core.TRAINING_OVERLAP
CROSSDOCKED_SET_IDS_SHA256 = pose_core.CROSSDOCKED_SET_IDS_SHA256
VERSION_NEEDLE = pose_core.VERSION_NEEDLE
COMMIT_NEEDLE = pose_core.COMMIT_NEEDLE
GNINA_ASSET_BYTES = pose_core.GNINA_ASSET_BYTES
GNINA_ASSET_SHA256 = pose_core.GNINA_ASSET_SHA256
CNN_SCORING = "rescore"
SCORE_ONLY = True
MIN_SERIES = 5
MAX_DROPPED_DECIDING = 5
BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20260905
CNN_AFFINITY_HIGHER_IS_BETTER = True
CNN_ENSEMBLE = (
    "dense_1_3",
    "dense_1_3_PT_KD_3",
    "crossdock_default2018_KD_4",
)

#: Frozen ranking-benchmark receptors (`docs/DOCKING_RANKING_BENCHMARK.md`).
RANKING_PDBS: frozenset[str] = frozenset(
    {
        "1ERE",
        "2RH1",
        "2V5Z",
        "3EML",
        "3HS4",
        "3PBL",
        "4EY7",
        "5C1M",
        "5HK1",
        "5I6X",
        "5TGZ",
        "6WGT",
    }
)
SERIES_PER_PDB: dict[str, int] = {
    "1ERE": 3,
    "2RH1": 1,
    "2V5Z": 8,
    "3EML": 8,
    "3HS4": 8,
    "3PBL": 8,
    "4EY7": 2,
    "5C1M": 7,
    "5HK1": 8,
    "5I6X": 8,
    "5TGZ": 8,
    "6WGT": 8,
}


def deciding_pdbs(pdbs: Sequence[str] = ()) -> tuple[str, ...]:
    pool = pdbs or sorted(RANKING_PDBS)
    return tuple(p for p in pool if p not in TRAINING_OVERLAP)


def overlap_pdbs(pdbs: Sequence[str] = ()) -> tuple[str, ...]:
    pool = pdbs or sorted(RANKING_PDBS)
    return tuple(p for p in pool if p in TRAINING_OVERLAP)


def n_series(pdbs: Sequence[str]) -> int:
    return sum(SERIES_PER_PDB[p] for p in pdbs)


def representative_value(vina_bests: Sequence[float]) -> float:
    """Shipped median: `sorted(values)[n // 2]` (`AffinityRange.median`)."""
    ordered = sorted(vina_bests)
    return ordered[len(ordered) // 2]


def representative_replicate(runs: Sequence[tuple[int, float]]) -> int:
    """Lowest replicate index whose vina_best equals the shipped median."""
    values = [score for _, score in runs]
    target = representative_value(values)
    matches = [index for index, score in runs if score == target]
    if not matches:
        raise ValueError("no replicate has the representative vina_best")
    return min(matches)


def paired_delta_rho(
    vina: Sequence[float],
    cnn: Sequence[float | None],
    pchembl: Sequence[float],
) -> float | None:
    """ρ(CNNaffinity, pChEMBL) − ρ(−Vina, pChEMBL) on the same ligands."""
    keep_v: list[float] = []
    keep_c: list[float] = []
    keep_p: list[float] = []
    for v, c, p in zip(vina, cnn, pchembl, strict=True):
        if c is None:
            continue
        keep_v.append(v)
        keep_c.append(c)
        keep_p.append(p)
    if len(keep_v) < MIN_SERIES:
        return None
    rho_c = spearman(keep_c, keep_p)
    rho_v = spearman([-x for x in keep_v], keep_p)
    if rho_c is None or rho_v is None:
        return None
    return rho_c - rho_v


def bootstrap_interval(values: Sequence[float], *, seed: int = BOOTSTRAP_SEED) -> tuple[float, float] | None:
    if len(values) < 3:
        return None
    rng = random.Random(seed)
    medians = []
    for _ in range(BOOTSTRAP):
        sample = [rng.choice(list(values)) for _ in values]
        medians.append(sorted(sample)[len(sample) // 2])
    medians.sort()
    return medians[int(0.025 * BOOTSTRAP)], medians[int(0.975 * BOOTSTRAP)]


def clustered_interval(
    by_pdb: dict[str, Sequence[float]],
    *,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float] | None:
    pdbs = [p for p, vals in by_pdb.items() if vals]
    if len(pdbs) < 3:
        return None
    rng = random.Random(seed)
    medians = []
    for _ in range(BOOTSTRAP):
        drawn = [rng.choice(pdbs) for _ in pdbs]
        sample = [v for pdb in drawn for v in by_pdb[pdb]]
        if not sample:
            continue
        medians.append(sorted(sample)[len(sample) // 2])
    if len(medians) < 3:
        return None
    medians.sort()
    return medians[int(0.025 * BOOTSTRAP)], medians[int(0.975 * BOOTSTRAP)]


def median_of(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def verdict(interval: tuple[float, float] | None, *, dropped: int, n_deciding: int) -> str:
    if dropped > MAX_DROPPED_DECIDING or n_deciding - dropped < 3 or interval is None:
        return "NULL"
    lo, hi = interval
    if lo > 0:
        return "PASS"
    if hi < 0:
        return "HARMFUL"
    return "NULL"


def integration_eligible(series_verdict: str, clustered: tuple[float, float] | None) -> bool:
    return series_verdict == "PASS" and clustered is not None and clustered[0] > 0


def help_names_default_ensemble(text: str) -> bool:
    lowered = text.lower()
    return all(name.lower() in lowered for name in CNN_ENSEMBLE)


def cnn_sign_is_predeclared(higher_is_better: bool) -> bool:
    return higher_is_better is CNN_AFFINITY_HIGHER_IS_BETTER


@dataclass(frozen=True)
class LigandScore:
    series_id: str
    pdb: str
    molecule_id: str
    replicate: int
    vina: float
    cnn: float | None
    pchembl: float
