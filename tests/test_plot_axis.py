"""The shared stick-plot geometry, tested on constructed numbers.

No QApplication and no widget: these are pure functions over rectangles,
which is the whole reason they were worth extracting. The widgets that use
them are tested separately, where a paint can actually happen.
"""

from __future__ import annotations

import pytest

from openchem.ui.widgets.plot_axis import (
    HIT_HALF_WIDTH,
    MARGIN,
    hit_regions,
    padded_range,
    plot_rect,
    to_widget_x,
)


def test_the_default_proportions_are_the_nmr_widgets():
    """Asserted as numbers rather than by importing `NmrSpectrumWidget`,
    which would need a QApplication. 50 across, 25 down, and both extents
    reduced by 1.5x and 3x the half-margin respectively -- which is what
    `NmrSpectrumWidget._plot_rect` computes for the same input."""
    rect = plot_rect(400.0, 300.0)
    assert (rect.left(), rect.top()) == (MARGIN, MARGIN / 2)
    assert rect.width() == 400.0 - 1.5 * MARGIN
    assert rect.height() == 300.0 - 1.5 * MARGIN


def test_a_caller_that_needs_a_banner_asks_for_a_full_top_margin():
    """`IrSpectrumWidget` reserves a full margin above the plot for its
    imaginary-frequency banner. The parameter is what lets one helper serve
    both without either widget's proportions changing."""
    rect = plot_rect(400.0, 300.0, top_margin=MARGIN)
    assert rect.top() == MARGIN
    assert rect.height() == 300.0 - 2.0 * MARGIN


def test_a_widget_smaller_than_its_own_margins_still_has_a_real_rectangle():
    """Transient during layout, not an error -- and a negative rectangle
    makes every coordinate derived from it nonsense."""
    rect = plot_rect(10.0, 10.0)
    assert rect.width() == 1.0
    assert rect.height() == 1.0


def test_an_empty_series_still_gets_an_axis():
    assert padded_range([]) == (0.0, 1.0)


def test_a_single_value_is_opened_out_before_it_is_padded():
    """Otherwise one stick is a zero-width axis and every x maps to the
    same pixel. The span is an argument because the two existing widgets
    disagree about it -- plus/minus 1.0 ppm against plus/minus 50.0 cm-1."""
    low, high = padded_range([7.26], minimum_span=2.0)
    assert low < 7.26 < high
    # Opened to [6.26, 8.26], then padded by 10% of that width.
    assert low == pytest.approx(6.06)
    assert high == pytest.approx(8.46)


def test_a_real_range_is_padded_by_a_tenth_at_each_end():
    assert padded_range([0.0, 10.0]) == pytest.approx((-1.0, 11.0))


def test_descending_puts_the_high_value_on_the_left():
    """NMR and IR convention: high shift, high wavenumber, left edge."""
    rect = plot_rect(400.0, 300.0)
    left = to_widget_x(10.0, rect, (0.0, 10.0), descending=True)
    right = to_widget_x(0.0, rect, (0.0, 10.0), descending=True)
    assert left == pytest.approx(rect.left())
    assert right == pytest.approx(rect.right())


def test_ascending_puts_the_high_value_on_the_right():
    """**THE LOAD-BEARING HALF.** A helper hard-coded to descending passes
    every NMR- and IR-shaped test and then silently mirrors every mass
    spectrum, which runs low m/z to the left. A mirrored spectrum does not
    look broken; it looks like a different compound."""
    rect = plot_rect(400.0, 300.0)
    left = to_widget_x(0.0, rect, (0.0, 10.0), descending=False)
    right = to_widget_x(10.0, rect, (0.0, 10.0), descending=False)
    assert left == pytest.approx(rect.left())
    assert right == pytest.approx(rect.right())


def test_the_two_directions_are_mirror_images_of_each_other():
    """Stronger than testing either alone: it pins the relationship rather
    than two independent placements that happen to look right."""
    rect = plot_rect(400.0, 300.0)
    for value in (0.0, 2.5, 7.5, 10.0):
        down = to_widget_x(value, rect, (0.0, 10.0), descending=True)
        up = to_widget_x(value, rect, (0.0, 10.0), descending=False)
        assert down + up == pytest.approx(rect.left() + rect.right())


def test_a_zero_width_range_lands_in_the_middle_rather_than_dividing_by_zero():
    rect = plot_rect(400.0, 300.0)
    x = to_widget_x(5.0, rect, (5.0, 5.0), descending=True)
    assert x == pytest.approx(rect.left() + rect.width() / 2)


def test_a_hit_region_spans_the_full_plot_height_around_its_stick():
    rect = plot_rect(400.0, 300.0)
    regions = hit_regions([2.0], rect, (0.0, 10.0), descending=False)
    assert len(regions) == 1
    region = regions[0]
    assert region.width() == 2 * HIT_HALF_WIDTH
    assert region.top() == rect.top()
    assert region.height() == rect.height()
    centre = to_widget_x(2.0, rect, (0.0, 10.0), descending=False)
    assert region.center().x() == pytest.approx(centre)


def test_regions_come_back_in_the_order_they_were_asked_for():
    """Two sticks can share an x, so the caller's order is what makes
    first-match-wins deterministic. Asked for deliberately unsorted, so a
    helper that sorted internally would fail rather than coincide."""
    rect = plot_rect(400.0, 300.0)
    values = [9.0, 1.0, 5.0]
    regions = hit_regions(values, rect, (0.0, 10.0), descending=False)
    for value, region in zip(values, regions):
        expected = to_widget_x(value, rect, (0.0, 10.0), descending=False)
        assert region.center().x() == pytest.approx(expected)
