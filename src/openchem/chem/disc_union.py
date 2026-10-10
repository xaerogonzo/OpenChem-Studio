"""The exact area of a union of discs: the shadow a molecule's van der Waals spheres cast.

**WHY THIS EXISTS RATHER THAN THE GRID IN `projection_geometry`.** The shadow of a molecule
is the union of its atoms' circles, and summing pi r^2 over atoms counts every overlap twice.
The grid there is a Riemann sum: fine for a number, wrong for a SEARCH. A minimum over
orientations is found by comparing areas that differ by a fraction of a percent, and a
grid's error is not smooth in the orientation -- it is a different quantisation at every
angle -- so the search ends on the grid's noise. Here the boundary is integrated exactly
(Green's theorem over the arcs of each circle that no other disc covers), so the area is a
smooth function of the orientation and its extremes are real ones.

Vectorised over all pairs, with no Python loop over the discs, because the orientation
search calls it hundreds of times.

The method, for each disc i: every other disc j that crosses its circle covers one arc of
it, centred on the direction to j with half-width acos((d^2 + r_i^2 - r_j^2) / (2 d r_i)).
The arcs of circle i left uncovered by all of them are the part of its boundary that is on
the boundary of the union, and the union's area is half the sum, over those arcs, of the
integral of (x dy - y dx). A disc lying wholly inside another contributes nothing; two
identical discs contribute once.
"""

from __future__ import annotations

import numpy as np

#: Distances and radii closer than this are the same number. Angstrom scale, so well below any
#: structure that could be drawn, and large against floating-point noise in a coordinate.
_EPS = 1e-9

_TWO_PI = 2.0 * np.pi


def union_area(centres: np.ndarray, radii: np.ndarray) -> float:
    """The area covered by discs of `radii` centred on the rows of `centres` (shape (n, 2))."""
    centres = np.asarray(centres, dtype=float)
    radii = np.asarray(radii, dtype=float)
    count = len(radii)
    if count == 0:
        return 0.0
    if count == 1:
        return float(np.pi * radii[0] ** 2)

    delta = centres[None, :, :] - centres[:, None, :]  # delta[i, j] = c_j - c_i
    distance = np.hypot(delta[..., 0], delta[..., 1])
    ri = radii[:, None]
    rj = radii[None, :]
    index = np.arange(count)
    not_self = index[:, None] != index[None, :]

    i_in_j = (distance + ri <= rj + _EPS) & not_self
    j_in_i = (distance + rj <= ri + _EPS) & not_self
    # Two discs that contain each other are identical: the lower index survives.
    mutual = i_in_j & j_in_i
    i_in_j = i_in_j & (~mutual | (index[None, :] < index[:, None]))

    covered = i_in_j.any(axis=1)  # the whole circle i lies inside another disc
    # Discs whose circles genuinely cross: neither contains the other, and they are close enough.
    crossing = not_self & ~(i_in_j | j_in_i) & (distance < ri + rj - _EPS)
    crossing &= ~covered[:, None]

    # EVERYTHING BELOW RUNS ON THE CROSSING PAIRS ONLY. A typical atom's circle is crossed by about
    # ten others, so the trigonometry and the sorting touch a tenth of the n x n pairs.
    row, column = np.nonzero(crossing)
    pair_distance = distance[row, column]
    cosine = (pair_distance**2 + radii[row] ** 2 - radii[column] ** 2) / (2.0 * pair_distance * radii[row])
    half_width = np.arccos(np.clip(cosine, -1.0, 1.0))
    direction = np.arctan2(delta[row, column, 1], delta[row, column, 0])

    # Bring each arc's start into [0, 2 pi); one that then runs past 2 pi is split at the wrap.
    arc_start = np.mod(direction - half_width, _TWO_PI)
    arc_end = arc_start + 2.0 * half_width
    wraps = arc_end > _TWO_PI
    circle = np.concatenate([row, row[wraps]])
    starts = np.concatenate([arc_start, np.zeros(int(wraps.sum()))])
    ends = np.concatenate([np.minimum(arc_end, _TWO_PI), arc_end[wraps] - _TWO_PI])

    order = np.lexsort((starts, circle))
    circle, starts, ends = circle[order], starts[order], ends[order]
    # A running maximum of the ends, kept apart per circle by lifting each circle clear of the last.
    lift = circle * 8.0
    running = np.maximum.accumulate(ends + lift) - lift

    first = np.ones(len(circle), dtype=bool)
    last = np.ones(len(circle), dtype=bool)
    first[1:] = circle[1:] != circle[:-1]
    last[:-1] = first[1:]
    inner = ~first
    inner_at = np.nonzero(inner)[0]
    # A circle nothing crosses (and nothing contains) has its whole boundary on the union.
    bare = np.setdiff1d(index[~covered], circle)

    arc_circle = np.concatenate([circle[first], circle[inner], circle[last], bare])
    lower = np.concatenate(
        [np.zeros(int(first.sum())), running[inner_at - 1], running[last], np.zeros(len(bare))]
    )
    upper = np.concatenate(
        [starts[first], starts[inner], np.full(int(last.sum()), _TWO_PI), np.full(len(bare), _TWO_PI)]
    )
    open_arc = upper > lower
    arc_circle, lower, upper = arc_circle[open_arc], lower[open_arc], upper[open_arc]

    cx = centres[arc_circle, 0]
    cy = centres[arc_circle, 1]
    r = radii[arc_circle]
    integral = (
        r**2 * (upper - lower)
        + cx * r * (np.sin(upper) - np.sin(lower))
        - cy * r * (np.cos(upper) - np.cos(lower))
    )
    return float(0.5 * integral.sum())
