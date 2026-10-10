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
    crossing = not_self & ~(i_in_j | j_in_i | (mutual & ~i_in_j)) & (distance < ri + rj - _EPS)
    crossing &= ~covered[:, None]

    safe_distance = np.where(crossing, distance, 1.0)
    cosine = (safe_distance**2 + ri**2 - rj**2) / (2.0 * safe_distance * ri)
    half_width = np.arccos(np.clip(cosine, -1.0, 1.0))
    direction = np.arctan2(delta[..., 1], delta[..., 0])

    start = direction - half_width
    end = direction + half_width
    # Bring `start` into [0, 2 pi); an arc that then runs past 2 pi wraps round to the start.
    start = np.mod(start, _TWO_PI)
    end = start + 2.0 * half_width
    wraps = end > _TWO_PI
    first_start = np.where(crossing, start, 0.0)
    first_end = np.where(crossing, np.where(wraps, _TWO_PI, end), 0.0)
    second_start = np.zeros_like(first_start)
    second_end = np.where(crossing & wraps, end - _TWO_PI, 0.0)

    starts = np.concatenate([first_start, second_start], axis=1)
    ends = np.concatenate([first_end, second_end], axis=1)
    order = np.argsort(starts, axis=1)
    starts = np.take_along_axis(starts, order, axis=1)
    ends = np.take_along_axis(ends, order, axis=1)
    running_end = np.maximum.accumulate(ends, axis=1)

    # The arcs left uncovered: from where the coverage so far stops, to where the next one starts.
    lower = np.concatenate([np.zeros((count, 1)), running_end], axis=1)
    upper = np.concatenate([starts, np.full((count, 1), _TWO_PI)], axis=1)
    open_arc = upper > lower
    # A circle wholly inside another disc has no boundary on the union.
    open_arc &= ~covered[:, None]
    lower = np.where(open_arc, lower, 0.0)
    upper = np.where(open_arc, upper, 0.0)

    cx = centres[:, 0:1]
    cy = centres[:, 1:2]
    r = radii[:, None]
    integral = (
        r**2 * (upper - lower)
        + cx * r * (np.sin(upper) - np.sin(lower))
        - cy * r * (np.cos(upper) - np.cos(lower))
    )
    return float(0.5 * integral.sum())
