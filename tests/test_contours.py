"""Contour geometry, checked against shapes whose answer is known.

None of this needs Qt, which is the point of keeping it out of the
widget: a single Gaussian must contour to circles about its own centre,
and that is checkable arithmetic rather than a pixel comparison.
"""

from __future__ import annotations

import math

import pytest

from openchem.ui.contours import contour_levels, density_grid, trace


def test_a_single_peak_is_highest_at_its_own_position():
    grid = density_grid([(5.0, 5.0)], (0.0, 10.0), (0.0, 10.0), resolution=101)
    j, i = divmod(int(grid.values.argmax()), grid.values.shape[1])

    assert grid.xs[i] == pytest.approx(5.0, abs=0.1)
    assert grid.ys[j] == pytest.approx(5.0, abs=0.1)
    assert grid.peak_value == pytest.approx(1.0, abs=1e-3)


def test_two_separated_peaks_both_appear():
    grid = density_grid([(2.0, 2.0), (8.0, 8.0)], (0.0, 10.0), (0.0, 10.0), resolution=101)
    near = lambda x, y: grid.values[  # noqa: E731
        int(round(y / 10 * 100)), int(round(x / 10 * 100))
    ]

    assert near(2.0, 2.0) == pytest.approx(1.0, abs=1e-2)
    assert near(8.0, 8.0) == pytest.approx(1.0, abs=1e-2)
    assert near(5.0, 5.0) < 0.01  # the gap between them stays empty


def test_a_contour_of_one_peak_is_a_ring_about_its_centre():
    """The closed-form check. Every traced point of a single Gaussian's
    contour must sit the same distance from the centre, and that distance
    must be the one the Gaussian's own equation predicts."""
    span, centre, width = 10.0, 5.0, 0.02
    grid = density_grid([(centre, centre)], (0.0, span), (0.0, span),
                        resolution=301, width_fraction=width)
    level = 0.5
    segments = trace(grid, level)

    assert segments, "a level below the peak must produce a contour"
    sigma = span * width
    # exp(-r^2 / 2 sigma^2) = level  =>  r = sigma * sqrt(-2 ln level)
    expected = sigma * math.sqrt(-2 * math.log(level))
    radii = [math.hypot(x - centre, y - centre) for x, y, _bx, _by in segments]
    assert min(radii) == pytest.approx(expected, rel=0.05)
    assert max(radii) == pytest.approx(expected, rel=0.05)


def test_a_level_above_the_peak_produces_nothing():
    grid = density_grid([(5.0, 5.0)], (0.0, 10.0), (0.0, 10.0), resolution=81)

    assert trace(grid, 1.5) == []


def test_an_empty_spectrum_produces_an_empty_grid_and_no_contour():
    grid = density_grid([], (0.0, 10.0), (0.0, 10.0), resolution=41)

    assert grid.peak_value == 0.0
    assert trace(grid, 0.1) == []


def test_levels_are_geometric_and_span_the_height():
    levels = contour_levels(count=6, lowest=0.05, peak=1.0)

    assert len(levels) == 6
    assert levels[0] == pytest.approx(0.05)
    assert levels[-1] == pytest.approx(1.0)
    # Deliberately offset by one, so the lengths differ -- not strict.
    ratios = [b / a for a, b in zip(levels, levels[1:], strict=False)]
    assert all(r == pytest.approx(ratios[0]) for r in ratios), "must be geometric"


def test_levels_scale_with_the_peak_height():
    """Levels are fractions of the tallest peak, so a spectrum whose
    density happens to overlap into taller blobs still gets rings in the
    same relative places."""
    assert contour_levels(count=3, lowest=0.1, peak=4.0)[0] == pytest.approx(0.4)


def test_a_degenerate_request_returns_no_levels():
    assert contour_levels(count=0) == []
    assert contour_levels(count=3, peak=0.0) == []


def test_overlapping_peaks_merge_into_one_taller_feature():
    """Two peaks closer than their width should not be drawn as two
    separate rings at a low level -- the density genuinely joins, and the
    contour must show that rather than hiding it."""
    grid = density_grid([(5.0, 5.0), (5.1, 5.0)], (0.0, 10.0), (0.0, 10.0),
                        resolution=301, width_fraction=0.02)
    midpoint = grid.values[int(round(5.0 / 10 * 300)), int(round(5.05 / 10 * 300))]

    assert midpoint > 1.0, "the two Gaussians must sum where they overlap"


def test_segments_stay_inside_the_requested_range():
    grid = density_grid([(1.0, 9.0)], (0.0, 10.0), (0.0, 10.0), resolution=121)

    for x0, y0, x1, y1 in trace(grid, 0.2):
        assert 0.0 <= x0 <= 10.0 and 0.0 <= x1 <= 10.0
        assert 0.0 <= y0 <= 10.0 and 0.0 <= y1 <= 10.0
