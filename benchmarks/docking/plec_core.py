"""The decision rules of the PLECscore pose-ranking test, as pure functions.

`PREREGISTRATION_PLEC.md` fixes what is counted and what each count means BEFORE any
rescoring is run; this module is that text as code, so the runner cannot choose a rule after
seeing a number and `tests/test_plec_core.py` can hold the boundaries.

The question: if the nine poses Vina returns are re-ordered by PLECscore's predicted affinity,
does the pose within 2 A of the crystal pose land on top more often? Nothing here knows about
ODDT, Vina or files.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

#: A pose within this assignment RMSD (A) of the crystal pose counts as correct. Same cutoff
#: as the prep-and-box survey (`prep_box_core.SUCCESS_RMSD`), restated rather than imported
#: so a later change to the survey cannot move this frozen test.
SUCCESS_RMSD = 2.0

#: Net receptors gained needed for a PASS or a HARMFUL reading, with the significance below.
MIN_NET = 3
#: One-sided exact sign-test level for the same.
ALPHA = 0.05
#: If more than this many deciding receptors cannot be rescored the test says nothing.
MAX_UNSCORED = 5

#: Catalogued receptors that are entries of PLECscore's own training set (PDBbind v2016, read
#: from ODDT's `plecscore_descs_p5_l1.csv.gz`, 13,232 complexes, on 2026-10-30). They are
#: reported apart and never counted toward the verdict: the model has seen their crystal
#: complexes and affinities.
TRAINED_ON = frozenset({"1HSG", "3EML", "3HS4", "4DJH", "4EA3", "4M48", "4N6H", "5C1M"})


def rerank(predicted: Sequence[float]) -> list[int]:
    """Pose indices ordered best first by predicted affinity (a higher pKd is better).

    Ties keep Vina's order, because the sort is stable: a rescorer that cannot separate two
    poses must not reshuffle them.
    """
    return sorted(range(len(predicted)), key=lambda i: -predicted[i])


def top_is_correct(rmsds: Sequence[float | None], order: Sequence[int]) -> bool | None:
    """Whether the pose placed first is within `SUCCESS_RMSD`; None when its RMSD is unknown."""
    value = rmsds[order[0]]
    return None if value is None else value <= SUCCESS_RMSD


@dataclass(frozen=True)
class Receptor:
    """One receptor's nine poses: Vina's RMSDs in Vina's order, and the rescorer's numbers."""

    pdb: str
    rmsds: tuple[float | None, ...]
    predicted: tuple[float, ...] | None  # None: the poses could not be rescored


@dataclass(frozen=True)
class Outcome:
    pdb: str
    before: bool | None
    after: bool | None
    #: Zero-based index in Vina's order of the pose the rescorer placed first.
    promoted: int | None


def judge_receptor(receptor: Receptor) -> Outcome:
    before = top_is_correct(receptor.rmsds, list(range(len(receptor.rmsds))))
    if receptor.predicted is None:
        return Outcome(receptor.pdb, before, None, None)
    order = rerank(receptor.predicted)
    return Outcome(receptor.pdb, before, top_is_correct(receptor.rmsds, order), order[0])


def sign_test_one_sided(wins: int, losses: int) -> float:
    """P(at least `wins` of wins+losses discordant receptors fall one way) under a fair coin."""
    n = wins + losses
    if n == 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / 2**n


@dataclass(frozen=True)
class Tally:
    measured: int  # receptors with a known Vina-order result
    unscored: int  # of those, how many could not be rescored
    gained: int  # wrong on top before, right after
    lost: int  # right on top before, wrong after
    before_correct: int
    after_correct: int  # among the scored


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


#: Input sanity. PLECscore predicts a pKd, and drug-like binders sit around 5 to 8. The first
#: smoke receptor (4IAR) came out at 0 to 2.5, which says the model is being shown input unlike
#: what it was trained on (poses that arrive through a charge-free PDBQT, a receptor rebuilt
#: from one) and an ordering of such numbers is not a finding. Fixed BEFORE the full run: if the
#: median over deciding receptors of the highest predicted pKd among a receptor's nine poses is
#: below this, the verdict is INCONCLUSIVE whatever the gains and losses are.
SANITY_MIN_MEDIAN_PKD = 4.0


def inputs_are_plausible(receptors: Sequence[Receptor]) -> bool:
    best = sorted(max(r.predicted) for r in receptors if r.predicted)
    if not best:
        return False
    mid = len(best) // 2
    median = best[mid] if len(best) % 2 else (best[mid - 1] + best[mid]) / 2
    return median >= SANITY_MIN_MEDIAN_PKD


def verdict(t: Tally, plausible: bool = True) -> str:
    """PASS, HARMFUL, NULL or INCONCLUSIVE for the deciding receptors."""
    if t.unscored > MAX_UNSCORED or not plausible:
        return "INCONCLUSIVE"
    net = t.gained - t.lost
    if net >= MIN_NET and sign_test_one_sided(t.gained, t.lost) <= ALPHA:
        return "PASS"
    if -net >= MIN_NET and sign_test_one_sided(t.lost, t.gained) <= ALPHA:
        return "HARMFUL"
    return "NULL"
