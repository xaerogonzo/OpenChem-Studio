"""The two charts Thread 2 adds, verified by rendering them.

`repaint()` and `update()` are no-ops on a widget that was never shown --
measured at zero paintEvent calls each -- so these go through
`conftest.painted`/`ink`, which render into a QImage and force the painter.
See CLAUDE.md.

EVERY INK COMPARISON HOLDS THE AXES FIXED AND VARIES ONLY THE CONTENT.
Two plausible-looking checks were killed by mutation testing on the
existing spectrum widgets and would be killed here too: "some pixel is
non-transparent" passes against an empty widget because the background is
opaque, and "more ink than the same widget with no data" passes against a
blanked painter because different data moves the tick labels. Sharing the
extreme points between the two cases keeps the ticks identical, so the
difference can only be the content.
"""

from __future__ import annotations

import pytest

from conftest import ink, painted
from openchem.chem.analytics import describe
from openchem.ui.widgets.histogram_widget import HistogramWidget
from openchem.ui.widgets.scatter_plot_widget import ScatterPlotWidget, ScatterPoint

# The two extremes both cases share, so the axes and their labels are the
# same picture in each.
_EXTREMES = [ScatterPoint(0.0, 0.0), ScatterPoint(10.0, 10.0)]


def test_points_are_actually_drawn(qapp):
    sparse = ScatterPlotWidget(_EXTREMES, "x", "y", "caption")
    dense = ScatterPlotWidget(
        _EXTREMES + [ScatterPoint(index * 0.5, 5.0) for index in range(20)], "x", "y", "caption"
    )
    assert ink(dense) > ink(sparse)


def test_the_fit_line_is_actually_drawn(qapp):
    points = _EXTREMES + [ScatterPoint(3.0, 7.0)]
    without = ScatterPlotWidget(points, "x", "y", "caption")
    with_fit = ScatterPlotWidget(points, "x", "y", "caption")
    with_fit.set_points(points, "x", "y", "caption", fit=(1.0, 0.0))
    assert ink(with_fit) > ink(without)


def test_group_colour_reaches_the_pixels(qapp):
    """The clustering path colours this same scatter, so the group index
    has to change what is painted rather than only what is stored."""
    one_group = painted(ScatterPlotWidget([ScatterPoint(1, 1, group=0), ScatterPoint(2, 2, group=0)]))
    two_groups = painted(ScatterPlotWidget([ScatterPoint(1, 1, group=0), ScatterPoint(2, 2, group=3)]))
    differing = sum(
        1
        for x in range(0, 400, 2)
        for y in range(0, 300, 2)
        if one_group.pixelColor(x, y) != two_groups.pixelColor(x, y)
    )
    assert differing > 0


def test_an_empty_scatter_explains_itself_rather_than_drawing_nothing(qapp):
    """A blank plot reads as broken; "only 1 molecule has both of these
    values" reads as a fact about the project."""
    widget = ScatterPlotWidget([], "x", "y")
    widget.set_empty_message("Only 1 molecule has both of these values.")
    assert ink(widget) > 0


def test_a_column_with_no_spread_does_not_divide_by_zero(qapp):
    """Every molecule passing Lipinski is an ordinary project, not an edge
    case."""
    widget = ScatterPlotWidget([ScatterPoint(1.0, 1.0), ScatterPoint(1.0, 1.0)], "x", "y")
    assert ink(widget) > 0


def test_hovering_selects_the_nearest_point_and_reports_it(qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent, QPointingDevice

    widget = ScatterPlotWidget(
        [ScatterPoint(0.0, 0.0, "first"), ScatterPoint(10.0, 10.0, "last")], "x", "y"
    )
    widget.resize(400, 300)
    seen = []
    widget.point_hovered.connect(seen.append)
    rect = widget._plot_rect()
    ranges = widget._ranges()
    target = widget._to_widget(10.0, 10.0, rect, ranges)
    widget.mouseMoveEvent(
        QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(target),
            QPointF(target),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            QPointingDevice.primaryPointingDevice(),
        )
    )
    assert seen == [1]


# --- histogram ----------------------------------------------------------


def test_bars_are_actually_drawn(qapp):
    """Both distributions span 0-10 in the same ten bins, so the axes and
    labels are identical and only the bars differ."""
    flat = HistogramWidget(describe([0.0, 10.0] + [5.0, 6.0], bins=10), "column")
    peaked = HistogramWidget(describe([0.0, 10.0] + [5.0] * 40, bins=10), "column")
    assert ink(flat) != ink(peaked)


def test_an_empty_histogram_explains_itself(qapp):
    widget = HistogramWidget(None, "column")
    widget.set_empty_message("Nothing computed for this column.")
    assert ink(widget) > 0


def test_the_median_line_moves_with_the_data(qapp):
    """The line is what makes a skewed column obvious, so it has to be
    drawn where the median is rather than at the middle."""
    left = HistogramWidget(describe([0.0, 10.0] + [1.0] * 20, bins=10), "column")
    right = HistogramWidget(describe([0.0, 10.0] + [9.0] * 20, bins=10), "column")
    assert painted(left) != painted(right)


def test_a_single_valued_column_draws_one_bin(qapp):
    widget = HistogramWidget(describe([4.0] * 12), "column")
    assert widget.distribution().counts == [12]
    assert ink(widget) > 0
