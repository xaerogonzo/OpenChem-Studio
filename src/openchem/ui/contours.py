"""Contour extraction for 2D spectra: broaden points, then trace levels.

WHY THIS IS SEPARATE FROM THE WIDGET. None of it needs Qt -- it is a
density grid and a marching-squares trace over that grid, both testable
against shapes whose answer is known in closed form (a single Gaussian
must contour to circles about its centre). Keeping it out of `paintEvent`
means the geometry can be checked without a QApplication, which is the
same split `chem/nmr_signals.py` already has from the widget that draws
its output.

WHAT THE CONTOURS DO AND DO NOT MEAN. A real 2D NMR contour plot encodes
intensity: peak volume is information, and the innermost contour of a
strong peak sits higher than that of a weak one. WE HAVE NO INTENSITIES.
Cross peaks here come from `chem/nmr_correlation.py`, which derives them
from the molecular graph -- which correlations should exist, not how
strong they are. So every peak is given the SAME amplitude and the same
width, and the contour rings are identical for all of them.

That makes the shape a drawing convention, not a measurement. Position is
the data; the rings are how a chemist expects to read position. Anything
else would be inventing intensity, which this project has refused
elsewhere for exactly the reasons it would be wrong here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: A peak is drawn this wide, as a fraction of the axis range it sits on.
#: A display parameter, NOT a measured linewidth -- see the module note.
#: Chosen so that neighbouring peaks in a typical HSQC stay visually
#: separate while a lone peak still reads as a rounded blob rather than a
#: dot.
DEFAULT_WIDTH_FRACTION = 0.012

#: Grid resolution per axis. 200 keeps a contour smooth at normal widget
#: sizes; the cost is quadratic and the trace below only visits cells the
#: level actually crosses, so this is not the expensive part.
DEFAULT_RESOLUTION = 200


@dataclass(frozen=True)
class DensityGrid:
    """Broadened peak intensity sampled on a regular grid.

    `values[j][i]` is the density at x = `xs[i]`, y = `ys[j]`, so the
    array is indexed row-major in (y, x) like an image -- but in DATA
    coordinates throughout. Flipping for the NMR convention is the
    widget's job, not this module's.
    """

    values: np.ndarray
    xs: np.ndarray
    ys: np.ndarray

    @property
    def peak_value(self) -> float:
        return float(self.values.max()) if self.values.size else 0.0


def density_grid(
    points: list[tuple[float, float]],
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    resolution: int = DEFAULT_RESOLUTION,
    width_fraction: float = DEFAULT_WIDTH_FRACTION,
) -> DensityGrid:
    """Sum an identical 2D Gaussian at each point.

    Only the window within four standard deviations of each peak is
    touched. Beyond that a Gaussian contributes less than 1e-4 of its
    height, far below the lowest contour, so evaluating the whole grid per
    peak would be spending time to change nothing.
    """
    x_min, x_max = x_range
    y_min, y_max = y_range
    xs = np.linspace(x_min, x_max, resolution)
    ys = np.linspace(y_min, y_max, resolution)
    values = np.zeros((resolution, resolution), dtype=float)
    if not points:
        return DensityGrid(values=values, xs=xs, ys=ys)

    sigma_x = max((x_max - x_min) * width_fraction, 1e-9)
    sigma_y = max((y_max - y_min) * width_fraction, 1e-9)
    step_x = (x_max - x_min) / (resolution - 1) if resolution > 1 else 1.0
    step_y = (y_max - y_min) / (resolution - 1) if resolution > 1 else 1.0
    reach_x = max(int(4 * sigma_x / step_x), 1)
    reach_y = max(int(4 * sigma_y / step_y), 1)

    for px, py in points:
        i = int(round((px - x_min) / step_x)) if step_x else 0
        j = int(round((py - y_min) / step_y)) if step_y else 0
        i0, i1 = max(i - reach_x, 0), min(i + reach_x + 1, resolution)
        j0, j1 = max(j - reach_y, 0), min(j + reach_y + 1, resolution)
        if i0 >= i1 or j0 >= j1:
            continue
        dx = (xs[i0:i1] - px) / sigma_x
        dy = (ys[j0:j1] - py) / sigma_y
        values[j0:j1, i0:i1] += np.exp(-0.5 * (dy[:, None] ** 2 + dx[None, :] ** 2))
    return DensityGrid(values=values, xs=xs, ys=ys)


def contour_levels(count: int = 6, lowest: float = 0.08, peak: float = 1.0) -> list[float]:
    """Levels in geometric progression, as NMR software draws them.

    Evenly spaced levels waste most of their lines on the flanks of a
    Gaussian, where the surface is steep and the rings crowd together.
    A geometric series spreads them across the height instead, which is
    why every real spectrometer package uses one.
    """
    if count < 1 or peak <= 0:
        return []
    lowest = max(min(lowest, 0.99), 1e-6)
    if count == 1:
        return [lowest * peak]
    ratio = (1.0 / lowest) ** (1.0 / (count - 1))
    return [lowest * peak * ratio**k for k in range(count)]


#: Which cell edges a contour crosses, per marching-squares case.
#: The index is a 4-bit corner mask: 1 = lower-left, 2 = lower-right,
#: 4 = upper-right, 8 = upper-left, set when that corner is at or above
#: the level. Cases 5 and 10 are the saddles -- the surface is ambiguous
#: there and both crossings are drawn, which is the standard choice and
#: cannot mislead when the output is line segments rather than filled
#: regions.
_EDGE_CASES: dict[int, tuple[tuple[str, str], ...]] = {
    1: (("left", "bottom"),),
    2: (("bottom", "right"),),
    3: (("left", "right"),),
    4: (("right", "top"),),
    5: (("left", "bottom"), ("right", "top")),
    6: (("bottom", "top"),),
    7: (("left", "top"),),
    8: (("top", "left"),),
    9: (("top", "bottom"),),
    10: (("top", "right"), ("left", "bottom")),
    11: (("top", "right"),),
    12: (("left", "right"),),
    13: (("bottom", "right"),),
    14: (("bottom", "left"),),
}


def _crossing(edge: str, x0: float, x1: float, y0: float, y1: float,
              bl: float, br: float, tr: float, tl: float, level: float) -> tuple[float, float]:
    """Where the level crosses one edge of a cell, by linear interpolation.

    Interpolating rather than taking the midpoint is what makes a contour
    smooth instead of stair-stepped, and it costs one division.
    """
    def between(a: float, b: float, va: float, vb: float) -> float:
        if abs(vb - va) < 1e-12:
            return a
        return a + (level - va) / (vb - va) * (b - a)

    if edge == "bottom":
        return between(x0, x1, bl, br), y0
    if edge == "top":
        return between(x0, x1, tl, tr), y1
    if edge == "left":
        return x0, between(y0, y1, bl, tl)
    return x1, between(y0, y1, br, tr)


def trace(grid: DensityGrid, level: float) -> list[tuple[float, float, float, float]]:
    """Line segments where `grid` crosses `level`, in data coordinates.

    Returns loose segments rather than joined polylines: the widget draws
    them individually, and stitching them into closed rings would be work
    with no visible effect at these sizes.
    """
    values = grid.values
    if values.size == 0 or values.shape[0] < 2 or values.shape[1] < 2:
        return []

    above = values >= level
    # Corner masks for every cell at once; only cells whose corners
    # disagree can contain a crossing, and for a handful of small blobs
    # that is a few hundred cells out of forty thousand.
    case = (
        above[:-1, :-1].astype(np.uint8)
        | (above[:-1, 1:].astype(np.uint8) << 1)
        | (above[1:, 1:].astype(np.uint8) << 2)
        | (above[1:, :-1].astype(np.uint8) << 3)
    )
    segments: list[tuple[float, float, float, float]] = []
    for j, i in np.argwhere((case != 0) & (case != 15)):
        edges = _EDGE_CASES.get(int(case[j, i]))
        if not edges:
            continue
        x0, x1 = float(grid.xs[i]), float(grid.xs[i + 1])
        y0, y1 = float(grid.ys[j]), float(grid.ys[j + 1])
        bl, br = float(values[j, i]), float(values[j, i + 1])
        tr, tl = float(values[j + 1, i + 1]), float(values[j + 1, i])
        for start, end in edges:
            ax, ay = _crossing(start, x0, x1, y0, y1, bl, br, tr, tl, level)
            bx, by = _crossing(end, x0, x1, y0, y1, bl, br, tr, tl, level)
            segments.append((ax, ay, bx, by))
    return segments
