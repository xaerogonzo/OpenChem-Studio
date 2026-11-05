"""Decision rules for the gnina CNN pose-ranking test, as pure functions.

`PREREGISTRATION_GNINA.md` fixes what is counted before any catalog pose is
rescored; this module is that text as code. Nothing here knows about WSL, gnina
or files.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

SUCCESS_RMSD = 2.0
MIN_NET = 3
ALPHA = 0.05
MAX_UNSCORED = 5
#: CNNscore is in [0, 1]. Below this median-of-maxima the CNN produced no ranking
#: signal (all-zero / failed loads). Not fitted on a catalog receptor.
CNN_SANITY_MIN = 0.01
SEED = 20261029
EXHAUSTIVENESS = 25
CNN_SCORING = "rescore"
VERSION_NEEDLE = "gnina v1.3.3"
COMMIT_NEEDLE = "6fe1ce2"
GNINA_ASSET = "gnina.cuda12.8.static"
GNINA_ASSET_BYTES = 2_056_131_000
GNINA_ASSET_SHA256 = "3340c1f49cd3c7c84d8699182a1c6af13c7fa2a22448d1204640446106f72172"

#: Unique PDB codes parsed from gnina/models `crossdocked_set_ids.txt` (CrossDocked2020
#: pocket:ligand index, 2026-11-04). Catalog hits are reported apart, never counted.
#: The index is not PDBbind 2020 general PL.
CROSSDOCKED_SET_IDS_SHA256 = (
    "254d543af569d942c9f8cb395e45a1db620ad950d47af2c83240054185ed03b0"
)
CROSSDOCKED_UNIQUE_PDB_COUNT = 25752
TRAINING_OVERLAP: frozenset[str] = frozenset(
    {
        "2RH1",
        "2V5Z",
        "2VT4",
        "3EML",
        "3PBL",
        "3RZE",
        "3SN6",
        "3UON",
        "4DJH",
        "4EA3",
        "4EY7",
        "4IAR",
        "4IB4",
        "5C1M",
        "5CXV",
        "5HK1",
        "5HK2",
        "5KIR",
    }
)


def parse_crossdocked_pdb_ids(text: str) -> set[str]:
    """PDB codes from `crossdocked_set_ids.txt` (skip `--pocket--` headers)."""
    ids: set[str] = set()
    for line in text.splitlines():
        if line.startswith("--") or not line.strip():
            continue
        for tok in line.split(","):
            pdb = tok.strip().split(":")[0].strip()
            if len(pdb) == 4 and pdb[0].isdigit():
                ids.add(pdb.upper())
    return ids


def deciding_ids(measurable: Sequence[str], overlap: frozenset[str] = TRAINING_OVERLAP) -> tuple[str, ...]:
    skip = {x.upper() for x in overlap}
    return tuple(p.upper() for p in measurable if p.upper() not in skip)


_CNN_SCORE = re.compile(r"CNNscore:\s*([0-9]*\.?[0-9]+)", re.I)
_CNN_AFFINITY = re.compile(r"CNNaffinity:\s*([-0-9]*\.?[0-9]+)", re.I)


def parse_cnn_scores(text: str) -> tuple[list[float], list[float]]:
    """CNNscore and CNNaffinity in file order. Empty lists if none (caller fails closed)."""
    scores = [float(m.group(1)) for m in _CNN_SCORE.finditer(text)]
    affs = [float(m.group(1)) for m in _CNN_AFFINITY.finditer(text)]
    return scores, affs


def version_is_pinned(text: str) -> bool:
    return VERSION_NEEDLE in text and COMMIT_NEEDLE in text


def rerank(predicted: Sequence[float]) -> list[int]:
    """Pose indices best-first by CNNscore (higher is better). Ties keep Vina's order."""
    return sorted(range(len(predicted)), key=lambda i: -predicted[i])


def top_is_correct(rmsds: Sequence[float | None], order: Sequence[int]) -> bool | None:
    value = rmsds[order[0]]
    return None if value is None else value <= SUCCESS_RMSD


@dataclass(frozen=True)
class Receptor:
    pdb: str
    rmsds: tuple[float | None, ...]
    predicted: tuple[float, ...] | None


@dataclass(frozen=True)
class Outcome:
    pdb: str
    before: bool | None
    after: bool | None
    promoted: int | None


def judge_receptor(receptor: Receptor) -> Outcome:
    before = top_is_correct(receptor.rmsds, list(range(len(receptor.rmsds))))
    if receptor.predicted is None:
        return Outcome(receptor.pdb, before, None, None)
    order = rerank(receptor.predicted)
    return Outcome(receptor.pdb, before, top_is_correct(receptor.rmsds, order), order[0])


def sign_test_one_sided(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / 2**n


@dataclass(frozen=True)
class Tally:
    measured: int
    unscored: int
    gained: int
    lost: int
    before_correct: int
    after_correct: int


def tally(outcomes: Sequence[Outcome]) -> Tally:
    known = [o for o in outcomes if o.before is not None]
    scored = [o for o in known if o.after is not None]
    return Tally(
        measured=len(known),
        unscored=len(known) - len(scored),
        gained=sum(1 for o in scored if not o.before and o.after),
        lost=sum(1 for o in scored if o.before and not o.after),
        before_correct=sum(1 for o in scored if o.before),
        after_correct=sum(1 for o in scored if o.after),
    )


def median(values: Sequence[float]) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def inputs_are_plausible(receptors: Sequence[Receptor]) -> bool:
    """Whether the CNN produced a ranking signal (median of per-receptor max CNNscore)."""
    best = sorted(max(r.predicted) for r in receptors if r.predicted)
    if not best:
        return False
    mid = median(best)
    return mid is not None and mid >= CNN_SANITY_MIN


def all_scores_tied(predicted: Sequence[float]) -> bool:
    return len(predicted) >= 2 and max(predicted) - min(predicted) <= 1e-12


def verdict(t: Tally, plausible: bool = True) -> str:
    if t.unscored > MAX_UNSCORED or not plausible:
        return "INCONCLUSIVE"
    net = t.gained - t.lost
    if net >= MIN_NET and sign_test_one_sided(t.gained, t.lost) <= ALPHA:
        return "PASS"
    if -net >= MIN_NET and sign_test_one_sided(t.lost, t.gained) <= ALPHA:
        return "HARMFUL"
    return "NULL"
