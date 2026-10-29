"""The pure part of the prep-and-box survey: how close a pose is, and what a miss was.

No Vina, no network, no Qt, so the rules are tested (`tests/test_prep_box_core.py`)
and cannot drift while the slow runner is being changed.

**THE DISTANCE IS AN ASSIGNMENT RMSD, A LOWER BOUND, AND THE REPORT SAYS SO.** The
crystal ligand arrives as elements and positions with no bonds, so there is no atom
correspondence for a symmetry-corrected RMSD. Instead each element's atoms are paired
by the assignment that minimises the summed squared distance (Hungarian), which is
the best any correspondence could do. It therefore never OVERSTATES the distance, and
it can UNDERSTATE one: a ligand flipped end for end can overlay its own atoms by
element and score low. The centroid shift is reported beside it for that reason, and a
"success" here means "at least this close", never "exactly right".
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

#: The usual docking-power cut: a pose within 2 A heavy-atom RMSD is "correct".
SUCCESS_RMSD = 2.0
#: A pose whose centroid is within this of the crystal ligand's is in the right pocket.
POCKET_CENTROID = 3.0

Atom = tuple[str, tuple[float, float, float]]

# Outcomes, in the order the report prints them.
SETUP_NO_SITE = "setup: no site"
SETUP_LIGAND = "setup: ligand could not be built"
SETUP_DOCK = "setup: docking failed"
SETUP_UNMEASURABLE = "setup: crystal ligand incomplete"
TOP1_CORRECT = "top pose correct"
RANKED_LOWER = "correct pose found, ranked lower"
RIGHT_POCKET = "right pocket, no correct pose"
WRONG_POCKET = "wrong pocket"

ORDER = (
    TOP1_CORRECT, RANKED_LOWER, RIGHT_POCKET, WRONG_POCKET,
    SETUP_NO_SITE, SETUP_LIGAND, SETUP_DOCK, SETUP_UNMEASURABLE,
)


def centroid(atoms: Sequence[Atom]) -> tuple[float, float, float]:
    n = len(atoms)
    return (
        sum(p[0] for _e, p in atoms) / n,
        sum(p[1] for _e, p in atoms) / n,
        sum(p[2] for _e, p in atoms) / n,
    )


def assignment_rmsd(docked: Sequence[Atom], crystal: Sequence[Atom]) -> float | None:
    """Lower-bound heavy-atom RMSD, or ``None`` when it cannot be measured.

    ``None`` when the two sides do not hold the same heavy atoms by element: a crystal
    ligand with missing atoms would otherwise be compared on a subset and look better
    than it is.
    """
    docked = [a for a in docked if a[0] != "H"]
    crystal = [a for a in crystal if a[0] != "H"]
    if not docked or len(docked) != len(crystal):
        return None
    total = 0.0
    for element in {e for e, _p in docked}:
        d = np.array([p for e, p in docked if e == element], dtype=float)
        c = np.array([p for e, p in crystal if e == element], dtype=float)
        if len(d) != len(c):
            return None
        cost = ((d[:, None, :] - c[None, :, :]) ** 2).sum(axis=2)
        rows, cols = linear_sum_assignment(cost)
        total += float(cost[rows, cols].sum())
    return math.sqrt(total / len(docked))


@dataclass(frozen=True)
class PoseMeasure:
    """One pose against the crystal ligand."""

    rmsd: float | None
    centroid_shift: float


def classify(poses: Sequence[PoseMeasure]) -> str:
    """What a docking that DID produce poses amounted to, best-ranked pose first.

    A pose whose RMSD could not be measured is judged on its centroid alone and can
    never count as correct.
    """
    if not poses:
        return SETUP_DOCK
    if all(p.rmsd is None for p in poses):
        return SETUP_UNMEASURABLE
    correct = [i for i, p in enumerate(poses) if p.rmsd is not None and p.rmsd <= SUCCESS_RMSD]
    if correct:
        return TOP1_CORRECT if correct[0] == 0 else RANKED_LOWER
    if min(p.centroid_shift for p in poses) <= POCKET_CENTROID:
        return RIGHT_POCKET
    return WRONG_POCKET


def tally(outcomes: Sequence[str]) -> dict[str, int]:
    """Counts in report order, every outcome present even at zero."""
    return {name: sum(1 for o in outcomes if o == name) for name in ORDER}
