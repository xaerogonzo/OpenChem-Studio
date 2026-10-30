"""Help a reader choose between the poses of one docking run.

Pose 1 is the best-SCORING pose. `benchmarks/docking/PREP_BOX_RESULT.md` measured how often
that is also the right one: on 47 catalogued receptors redocked with real Vina, the top pose
was within 2 A of the crystal pose for 35 (74%), and for 9 more a pose that close was among
the nine but ranked lower. So the honest message is not "pick pose 1" and not "the score is
useless": it is that when two poses score alike and sit in different places, the score cannot
tell them apart, and the reader should look at both.

Pure arithmetic over numbers the table already shows (the score and the RMSD to pose 1), no
Qt and no RDKit. It says which poses the SCORE cannot separate from pose 1; it never says
which pose is correct, because nothing here knows.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: Trott & Olson (2010), the Vina paper's own standard error against experimental free
#: energies (kcal/mol). The panel's score tooltip already quotes it: a gap smaller than this
#: is not a difference the function can be trusted to resolve.
SCORE_RESOLUTION = 2.85

#: The survey's cutoff for a correct pose, reused here as "a different place": RMSD to pose 1
#: above it means the ligand sits somewhere else, not a small shift.
DIFFERENT_PLACEMENT = 2.0

#: How many pose numbers a sentence lists before it says "and N more".
_LISTED = 4

#: The redocking figures the sentence quotes, held to `PREP_BOX_RESULT.md` by
#: `tests/test_pose_choice.py` so a re-run that moves them cannot leave the panel stale.
REDOCK_RECEPTORS = 47
REDOCK_TOP_CORRECT = 35
REDOCK_RANKED_LOWER = 9


@dataclass(frozen=True)
class PoseChoice:
    """Which poses (1-based, as the table numbers them) the score cannot separate from pose 1."""

    #: Within `SCORE_RESOLUTION` of pose 1, in the same place (RMSD to pose 1 within the cutoff).
    same_place: tuple[int, ...]
    #: Within `SCORE_RESOLUTION` of pose 1 but somewhere else: the ones worth opening.
    elsewhere: tuple[int, ...]


def assess(affinities: Sequence[float], rmsd_lower_bounds: Sequence[float]) -> PoseChoice:
    """Classify poses 2.. against pose 1 by score gap and placement.

    `affinities` are kcal/mol, more negative is better, in the table's order (best first).
    The lower RMSD bound is used for "elsewhere" because it is the conservative one: it
    already forgives symmetry-equivalent atoms, so a pose it calls far is far.
    """
    if len(affinities) != len(rmsd_lower_bounds):
        raise ValueError("one RMSD per pose is needed")
    if len(affinities) < 2:
        return PoseChoice((), ())
    best = affinities[0]
    same, other = [], []
    for index in range(1, len(affinities)):
        if affinities[index] - best > SCORE_RESOLUTION:
            continue
        (other if rmsd_lower_bounds[index] > DIFFERENT_PLACEMENT else same).append(index + 1)
    return PoseChoice(tuple(same), tuple(other))


def _numbers(poses: Sequence[int]) -> str:
    shown = ", ".join(str(p) for p in poses[:_LISTED])
    more = len(poses) - _LISTED
    return shown + (f" and {more} more" if more > 0 else "")


def summarize(affinities: Sequence[float], rmsd_lower_bounds: Sequence[float]) -> str:
    """The sentence under the pose table, or "" when there is nothing to choose between."""
    if len(affinities) < 2:
        return ""
    choice = assess(affinities, rmsd_lower_bounds)
    head = (
        "Pose 1 scores best, which is not the same as being right. In a redocking test on "
        f"{REDOCK_RECEPTORS} receptors it was within 2 A of the crystal pose for "
        f"{REDOCK_TOP_CORRECT}, and for {REDOCK_RANKED_LOWER} more a pose that close was among "
        "the nine but ranked lower."
    )
    window = f"{SCORE_RESOLUTION:g} kcal/mol"
    if choice.elsewhere:
        plural = len(choice.elsewhere) > 1
        here = (
            f" In this run pose{'s' if plural else ''} {_numbers(choice.elsewhere)} score"
            f"{'' if plural else 's'} within {window} of pose 1 and sit more than 2 A from it: "
            "the score cannot separate them, so look at "
            f"{'them' if plural else 'it'} too."
        )
    elif choice.same_place:
        here = (
            f" In this run the poses that score within {window} of pose 1 "
            f"({_numbers(choice.same_place)}) all sit within 2 A of it, so they are one "
            "placement and choosing among them matters little."
        )
    else:
        here = f" In this run no other pose scores within {window} of pose 1."
    return head + here


def row_hint(choice: PoseChoice, pose: int, rmsd_lower_bound: float) -> str:
    """Hover text for a pose the score cannot separate from pose 1, else ''."""
    if pose in choice.elsewhere:
        return (
            f"Scores within {SCORE_RESOLUTION:g} kcal/mol of pose 1 but sits "
            f"{rmsd_lower_bound:.1f} A from it. The score cannot say which is better; "
            "open both."
        )
    return ""
