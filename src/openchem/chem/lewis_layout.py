"""Which 2D layout to draw a Lewis diagram from.

RDKit ships two layout engines and **neither one wins.** Measured as
closest non-bonded approach in bond lengths -- the `crowding` metric the
builder already uses, where higher is better:

    molecule      atoms   Compute2DCoords   rdCoordGen
    methane           5             1.414        1.000   coordgen WORSE
    benzene          12             1.732        1.732
    aspirin          21             1.000        1.000
    caffeine         24             1.177        1.000   coordgen WORSE
    glucose          24             0.524        0.805   coordgen better
    morphine         40             0.303        0.186   coordgen WORSE
    cholesterol      74             0.036        0.565   coordgen better, 16x

Morphine is essentially the structure this work was reported for, and it
is one CoordGen loses. So "use the newer engine" would have made the
reported case worse, and the answer is to lay out BOTH and keep whichever
scores better. Both are deterministic and together cost about 20 ms on
the largest case, so this cannot regress **according to the measured
metric** -- which is a weaker and more honest claim than "cannot regress":
a layout can win on closest approach and still read worse through bond
crossings, label overlap or ring orientation.

Bond crossings therefore join the score, and the two are compared as a
TUPLE rather than summed. `lewis_svg._lone_pair_slots` already does this,
for a reason worth repeating: scoring clearance and spread as a sum put
water's lone pairs between its two hydrogens, because 180 degrees of
spread outweighed the loss of clearance. Inventing a weight between
"crossings" and "crowding" would be the same mistake in a new place.

Which of the two LEADS was chosen on a design set and frozen before the
holdout was scored -- see `LayoutScore`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Two points closer than this are the same point, in layout units.
_EPSILON = 1e-9

#: How near a segment must pass to a non-endpoint atom to count as
#: running through it, as a fraction of the mean bond length.
ATOM_HIT_FRACTION = 0.20


@dataclass(frozen=True, order=True)
class LayoutScore:
    """How good a layout is, **compared lexicographically**.

    A dataclass with `order=True`, so the comparison IS the field order
    and there is no weighting anywhere to get wrong. `max()` picks the
    better layout.

    **WHICH FIELD LEADS WAS CHOSEN ON A DESIGN SET AND THEN FROZEN**,
    because deciding it on the same molecules used to claim the chooser
    works is tuning and evaluating on one dataset. Two candidates, a
    42-molecule corpus split alphabetically before anything was scored,
    the ordering fixed on one half and evaluated on the other --
    `benchmarks/lewis_layout/choose.py` carries the criteria, which were
    written before it was first run.

        ordering              design            holdout
        A (-crossings, crowding)   19/21 not worse    -- rejected
        B (crowding, -crossings)   21/21 not worse    21/21 not worse,
                                                      8 strictly better,
                                                      38 crossings removed

    **CLEARANCE LEADS, WHICH IS NOT THE INTUITIVE ANSWER.** Putting
    crossings first makes two of the twenty-one design molecules WORSE on
    clearance in order to remove a crossing, and a Lewis diagram whose
    dots have run together is harder to read than one with a line
    crossing it -- there are no bond lines to speak of in the first
    place.
    """

    crowding: float
    negated_crossings: int

    @property
    def crossings(self) -> int:
        return -self.negated_crossings


def score(positions, bonds) -> LayoutScore:
    """Score one layout. `positions` is index -> (x, y); `bonds` is pairs."""
    return LayoutScore(crowding(positions, bonds), -count_crossings(positions, bonds))


def crowding(positions, bonds) -> float:
    """Closest non-bonded approach, in bond lengths. Small means crowded.

    **A LEGIBILITY NUMBER, NEVER A CHEMISTRY ONE**, exactly as
    `lewis_builder.crowding` says of the same quantity -- a molecule whose
    diagram is hard to read still has a correct diagram.
    """
    bonded = {tuple(sorted(pair)) for pair in bonds}
    unit = _mean_bond_length(positions, bonded)
    indices = sorted(positions)
    closest = math.inf
    for i, a in enumerate(indices):
        for b in indices[i + 1 :]:
            if (a, b) in bonded:
                continue
            closest = min(closest, math.dist(positions[a], positions[b]))
    if closest is math.inf:
        return math.inf
    return closest / unit


def count_crossings(positions, bonds) -> int:
    """How many times the drawing crosses itself.

    **THE SEMANTICS ARE PINNED HERE**, because two readings can both look
    reasonable and the last two rows are the ones that otherwise accrete
    as special cases during implementation, one bug report at a time:

        one segment per BOND, whatever its order   a double bond is one
                                                   line, not two
        edges sharing an endpoint                  never counted -- they
                                                   meet at an atom
        a proper crossing                          interiors intersect: 1
        a segment through a NON-ENDPOINT atom      counted. Evaluated
                                                   only against atoms
                                                   that are not its own
                                                   endpoints, or every
                                                   bond would "pass
                                                   through" both of them
        collinear overlap                          counted -- two bonds
                                                   drawn on top of each
                                                   other is worse than a
                                                   crossing. Caught by
                                                   the atom pass, not the
                                                   segment pass; see
                                                   `_segments_cross`
        two bonds sharing an endpoint and running  NOT an overlap. That is
        collinearly in OPPOSITE directions         a 180-degree angle at
                                                   an atom, and ordinary
    """
    segments = sorted({tuple(sorted(pair)) for pair in bonds})
    unit = _mean_bond_length(positions, set(segments))
    radius = ATOM_HIT_FRACTION * unit

    total = 0
    for index, (a, b) in enumerate(segments):
        if a not in positions or b not in positions:
            continue
        p1, p2 = positions[a], positions[b]
        for c, d in segments[index + 1 :]:
            if c not in positions or d not in positions:
                continue
            # Sharing an endpoint is an ANGLE, not a crossing -- including
            # the straight-through case, where two bonds leave one atom in
            # opposite directions and are collinear by construction.
            if {a, b} & {c, d}:
                continue
            if _segments_cross(p1, p2, positions[c], positions[d]):
                total += 1

    for a, b in segments:
        if a not in positions or b not in positions:
            continue
        for atom, point in positions.items():
            if atom in (a, b):
                continue
            if _distance_to_segment(point, positions[a], positions[b]) < radius:
                total += 1
    return total


def _mean_bond_length(positions, bonded) -> float:
    lengths = [
        math.dist(positions[a], positions[b])
        for a, b in bonded
        if a in positions and b in positions
    ]
    return (sum(lengths) / len(lengths)) if lengths else 1.0


def _orientation(p, q, r) -> float:
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def _segments_cross(p1, p2, p3, p4) -> bool:
    """A PROPER crossing: the two interiors intersect.

    **COLLINEAR OVERLAP IS NOT TESTED HERE, AND A MUTATION IS WHY.** The
    first version had a second branch for it, on the reasoning that two
    bonds drawn on top of each other is worse than a crossing rather than
    better. Removing that branch changed no test and no benchmark number,
    which is the tell: overlap is caught anyway, one loop down.

    Two collinear segments that overlap must put an endpoint of one
    strictly inside the other -- sharing an endpoint is exempted as an
    angle -- and an endpoint inside a segment is an atom at distance zero
    from it, which is exactly what the atom-through-segment pass counts.
    So the branch was not merely redundant, it DOUBLE-COUNTED every
    overlap it found.

    `test_two_bonds_drawn_on_top_of_each_other_are_counted` still holds,
    through the other mechanism, and says so.
    """
    d1 = _orientation(p3, p4, p1)
    d2 = _orientation(p3, p4, p2)
    d3 = _orientation(p1, p2, p3)
    d4 = _orientation(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _distance_to_segment(point, start, end) -> float:
    length_squared = (end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2
    if length_squared < _EPSILON:
        return math.dist(point, start)
    t = (
        (point[0] - start[0]) * (end[0] - start[0])
        + (point[1] - start[1]) * (end[1] - start[1])
    ) / length_squared
    t = max(0.0, min(1.0, t))
    nearest = (start[0] + t * (end[0] - start[0]), start[1] + t * (end[1] - start[1]))
    return math.dist(point, nearest)
