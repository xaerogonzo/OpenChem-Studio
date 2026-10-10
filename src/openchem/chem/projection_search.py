"""The smallest and largest shadow a molecule casts, over every orientation.

`projection_geometry` used to measure the shadow along the three principal axes and call the
smaller "minimal" and the larger "maximal". That is the smallest and largest of THREE, not of
all orientations: a flat molecule's true minimum can lie off the principal axes, and the
figure read slightly high. This searches the sphere of viewing directions instead.

**WHAT IS EXACT AND WHAT IS SEARCHED.** The area at ONE orientation is exact
(`disc_union.union_area`); which orientation is the extreme is found by sampling the
hemisphere of directions and refining the best few samples with a shrinking local search.
The area is a smooth function of the direction, so the refinement converges on a real local
extreme, but a local search can in principle end on a local extreme that is not the global
one. The sampling is dense enough that this has not happened in measurement (see
`tests/test_projection_search.py`, which compares against a far denser sweep), and the result
says how many orientations it looked at rather than claiming a proof.

**THREE QUANTITIES PER ORIENTATION, EACH DEFINED HERE** because ChemAxon's documentation
defines none of them:

* *area* -- the area of the union of the atoms' circles, projected along the direction;
* *radius* -- the radius of the smallest circle that encloses that shadow, i.e. the round
  hole the molecule would pass through when viewed along the direction;
* *size* -- the extent of the molecule ALONG the direction (perpendicular to the shadow's
  plane), from the surface of the nearest sphere to the surface of the furthest.

All three use the radii they are given, so a scale factor on the van der Waals radii scales
all three consistently.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from openchem.chem.disc_union import union_area

#: Viewing directions sampled over the hemisphere before refining, by atom count. The cost of
#: one orientation grows with the square of the atom count (every pair of circles is
#: compared), so a larger molecule gets fewer samples: its shadow is also a smoother function
#: of the direction, and the refinement does the precise work.
_SAMPLES_SMALL = 240
_SAMPLES_MEDIUM = 160
_SAMPLES_LARGE = 100
_MEDIUM_ATOMS = 60
_LARGE_ATOMS = 150

#: How many of the best samples (of each kind) are refined. The area can have more than one
#: local extreme, and the best sample is not always in the basin of the best extreme.
_REFINED_STARTS = 3

#: The local search stops when its step falls below this, in radians (about 0.006 degree).
#:
#: **NOT A QUADRATIC MINIMUM, AND AN EARLIER VALUE ASSUMED IT WAS.** The shadow of two spheres
#: viewed end-on is one circle; tilt the view by `t` and the circles part by `d sin t`, so the
#: area grows LINEARLY in `t` -- a cusp, not a bowl. Minimum shadows sit at such alignments (the
#: most overlap), so the error in the area is about `2 r d` times the angular error: 0.0068 A^2
#: at the first tolerance tried (2e-3), 3e-4 A^2 at this one. A maximum is usually smooth, a
#: minimum usually is not.
_REFINE_TOLERANCE = 1e-4

#: Iterations of each of the two nested ternary searches for the enclosing circle. The range
#: shrinks by 2/3 each time, so 60 take it far below floating-point resolution.
_CIRCLE_ITERATIONS = 60


@dataclass(frozen=True)
class Projection:
    """One orientation: the shadow cast when looking along `direction`."""

    direction: tuple[float, float, float]
    area: float
    radius: float
    size: float


@dataclass(frozen=True)
class ProjectionExtremes:
    """The smallest- and largest-shadow orientations found, and how hard they were looked for."""

    minimum: Projection
    maximum: Projection
    #: Orientations whose area was computed in total (the sampling plus the refinement).
    orientations: int


def _plane_basis(direction: np.ndarray) -> np.ndarray:
    """Two orthonormal vectors spanning the plane perpendicular to `direction`."""
    seed = np.eye(3)[int(np.argmin(np.abs(direction)))]
    first = seed - np.dot(seed, direction) * direction
    first /= np.linalg.norm(first)
    second = np.cross(direction, first)
    return np.array([first, second / np.linalg.norm(second)])


def _hemisphere(count: int) -> np.ndarray:
    """`count` roughly evenly spread unit vectors on the z >= 0 hemisphere (Fibonacci spiral)."""
    index = np.arange(count) + 0.5
    z = 1.0 - index / count  # from the pole down to the equator
    ring = np.sqrt(np.clip(1.0 - z * z, 0.0, None))
    angle = index * math.pi * (3.0 - math.sqrt(5.0))
    return np.stack([ring * np.cos(angle), ring * np.sin(angle), z], axis=1)


def _area(positions: np.ndarray, radii: np.ndarray, direction: np.ndarray) -> float:
    flat = positions @ _plane_basis(direction).T
    return union_area(flat, radii)


def enclosing_radius(centres: np.ndarray, radii: np.ndarray) -> float:
    """The radius of the smallest circle containing every disc.

    `f(c) = max_i(|c - c_i| + r_i)` is the radius needed round the point `c`, and it is convex,
    so its minimum over `c` is found by a ternary search over x nested in one over y.
    """
    centres = np.asarray(centres, dtype=float)
    radii = np.asarray(radii, dtype=float)
    if len(radii) == 1:
        return float(radii[0])

    def needed(x: float, y: float) -> float:
        return float((np.hypot(centres[:, 0] - x, centres[:, 1] - y) + radii).max())

    def best_for_x(x: float) -> float:
        low, high = float((centres[:, 1] - radii).min()), float((centres[:, 1] + radii).max())
        for _ in range(_CIRCLE_ITERATIONS):
            a = low + (high - low) / 3.0
            b = high - (high - low) / 3.0
            if needed(x, a) < needed(x, b):
                high = b
            else:
                low = a
        return needed(x, 0.5 * (low + high))

    low, high = float((centres[:, 0] - radii).min()), float((centres[:, 0] + radii).max())
    for _ in range(_CIRCLE_ITERATIONS):
        a = low + (high - low) / 3.0
        b = high - (high - low) / 3.0
        if best_for_x(a) < best_for_x(b):
            high = b
        else:
            low = a
    return best_for_x(0.5 * (low + high))


def projection_at(positions: np.ndarray, radii: np.ndarray, direction) -> Projection:
    """Area, enclosing radius and size for one viewing direction (normalised here)."""
    positions = np.asarray(positions, dtype=float)
    radii = np.asarray(radii, dtype=float)
    unit = np.asarray(direction, dtype=float)
    unit = unit / np.linalg.norm(unit)
    flat = positions @ _plane_basis(unit).T
    along = positions @ unit
    return Projection(
        direction=tuple(float(v) for v in unit),
        area=union_area(flat, radii),
        radius=enclosing_radius(flat, radii),
        size=float((along + radii).max() - (along - radii).min()),
    )


def _refine(positions, radii, start: np.ndarray, step: float, sign: float, budget: list[int]) -> np.ndarray:
    """Walk from `start` to a local extreme of the area (`sign` -1 for a minimum, +1 for a maximum).

    A shrinking compass search on the sphere: try eight neighbours at the current step, move to
    the best one if it improves, otherwise halve the step.
    """
    current = start / np.linalg.norm(start)
    value = sign * _area(positions, radii, current)
    budget[0] += 1
    while step > _REFINE_TOLERANCE:
        first, second = _plane_basis(current)
        best, best_value = None, value
        for angle in np.arange(8) * (math.pi / 4.0):
            candidate = current * math.cos(step) + math.sin(step) * (
                math.cos(angle) * first + math.sin(angle) * second
            )
            candidate_value = sign * _area(positions, radii, candidate)
            budget[0] += 1
            if candidate_value > best_value:
                best, best_value = candidate, candidate_value
        if best is None:
            step *= 0.5
        else:
            current, value = best / np.linalg.norm(best), best_value
    return current


def projection_extremes(positions: np.ndarray, radii: np.ndarray) -> ProjectionExtremes:
    """The minimum- and maximum-area orientations of the shadow of spheres of `radii` at `positions`."""
    positions = np.asarray(positions, dtype=float)
    radii = np.asarray(radii, dtype=float)
    count = len(radii)
    if count == 0:
        raise ValueError("A projection needs at least one atom.")
    if count == 1:
        only = projection_at(positions, radii, (0.0, 0.0, 1.0))
        return ProjectionExtremes(minimum=only, maximum=only, orientations=1)

    samples = _SAMPLES_SMALL if count <= _MEDIUM_ATOMS else (_SAMPLES_MEDIUM if count <= _LARGE_ATOMS else _SAMPLES_LARGE)
    directions = _hemisphere(samples)
    areas = np.array([_area(positions, radii, direction) for direction in directions])
    budget = [samples]
    # The sampling's own spacing is the first step of the refinement: a neighbour that close is
    # the farthest the true extreme can be from its best sample.
    step = math.sqrt(2.0 * math.pi / samples)

    found = []
    for sign, order in ((-1.0, np.argsort(areas)), (1.0, np.argsort(-areas))):
        starts: list[np.ndarray] = []
        for index in order:
            candidate = directions[index]
            # Distinct basins only: skip a start within a step of one already refined.
            if all(float(np.dot(candidate, other)) < math.cos(2.0 * step) for other in starts):
                starts.append(candidate)
            if len(starts) == _REFINED_STARTS:
                break
        refined = [_refine(positions, radii, start, step, sign, budget) for start in starts]
        best = max(refined, key=lambda direction: sign * _area(positions, radii, direction))
        found.append(best)
    minimum, maximum = (projection_at(positions, radii, direction) for direction in found)
    return ProjectionExtremes(minimum=minimum, maximum=maximum, orientations=budget[0])
