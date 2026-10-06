"""Zooming the histogram and the stick chart without trapping the reader's scrolling.

The gestures are the line chart's (`tests/test_line_chart_zoom.py`): Ctrl+wheel zooms around the
cursor, Shift+wheel pans, a double-click resets, and a PLAIN wheel is not taken because these sit
in a scrolling reader. What these tests pin is what is specific to each drawing: a stick outside
the window is neither drawn nor clickable, and a histogram rescales its count axis to the bins in
view.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from openchem.chem.analytics import describe
from openchem.domain.report import Stick, StickChartAnnotation
from openchem.ui.widgets.histogram_widget import HistogramWidget
from openchem.ui.widgets.stick_chart_widget import StickChartWidget

CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
NONE = Qt.KeyboardModifier.NoModifier


def _wheel(widget, x, y, delta, modifiers):
    event = QWheelEvent(
        QPointF(x, y), widget.mapToGlobal(QPointF(x, y)), QPoint(0, 0), QPoint(0, delta),
        Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False,
    )
    event.ignore()
    QApplication.sendEvent(widget, event)
    return event


def _double_click(widget, x, y):
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick, QPointF(x, y), widget.mapToGlobal(QPointF(x, y)),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, NONE,
    )
    QApplication.sendEvent(widget, event)


def _sticks(descending=False):
    # A cluster of weak lines at low x and one strong line far away, like a powder pattern.
    sticks = tuple(Stick(10.0 + i * 0.5, 0.1 * (i + 1), f"l{i}") for i in range(6)) + (Stick(90.0, 1.0, "big"),)
    return StickChartAnnotation(
        sticks=sticks, x_label="2theta", y_label="I", x_units="deg", x_descending=descending
    )


def _stick_widget(descending=False):
    widget = StickChartWidget(_sticks(descending))
    widget.resize(500, 300)
    return widget


def _histogram():
    # Most of the mass in [0, 10), a thin tail out to 100.
    values = [float(v) for v in range(0, 10)] * 6 + [40.0, 55.0, 70.0, 100.0]
    widget = HistogramWidget(describe(values, bins=20), "column")
    widget.resize(500, 300)
    return widget


@pytest.mark.parametrize("make", [_stick_widget, _histogram], ids=["stick", "histogram"])
def test_a_plain_wheel_is_not_taken_so_the_reader_still_scrolls(qapp, make):
    widget = make()
    c = widget._plot_rect().center()
    event = _wheel(widget, c.x(), c.y(), 120, NONE)
    assert not event.isAccepted() and not widget.is_zoomed()


@pytest.mark.parametrize("make", [_stick_widget, _histogram], ids=["stick", "histogram"])
def test_ctrl_wheel_zooms_in_around_the_cursor_and_double_click_resets(qapp, make):
    widget = make()
    rect = widget._plot_rect()
    full = widget._full_x_range()
    seen = []
    widget.view_changed.connect(lambda: seen.append(widget.view_range()))
    event = _wheel(widget, rect.left() + rect.width() * 0.2, rect.center().y(), 120, CTRL)
    assert event.isAccepted() and widget.is_zoomed()
    low, high = widget.view_range()
    assert (high - low) < (full[1] - full[0]) and full[0] <= low and high <= full[1]
    assert seen, "a zoom announces itself"
    _double_click(widget, rect.center().x(), rect.center().y())
    assert not widget.is_zoomed() and widget.view_range() == full


@pytest.mark.parametrize("make", [_stick_widget, _histogram], ids=["stick", "histogram"])
def test_shift_wheel_pans_only_a_zoomed_view_and_stays_inside_the_data(qapp, make):
    widget = make()
    rect = widget._plot_rect()
    c = rect.center()
    assert _wheel(widget, c.x(), c.y(), 120, SHIFT).isAccepted() is True
    assert not widget.is_zoomed(), "panning an unzoomed chart changes nothing"
    for _ in range(4):
        _wheel(widget, rect.left() + 10, c.y(), 120, CTRL)
    before = widget.view_range()
    _wheel(widget, c.x(), c.y(), -120, SHIFT)
    after = widget.view_range()
    full = widget._full_x_range()
    assert after != before and full[0] <= after[0] and after[1] <= full[1]
    assert after[1] - after[0] == pytest.approx(before[1] - before[0])


def _margin_sticks():
    # 10, 20, 30, 40 -- and a window (11, 29) that leaves 10 and 30 just outside it, close enough
    # that their un-hidden position would land INSIDE the widget's margin rather than off it.
    return StickChartAnnotation(
        sticks=tuple(Stick(x, 1.0, str(int(x))) for x in (10.0, 20.0, 30.0, 40.0)),
        x_label="2theta", y_label="I", x_units="deg", x_descending=False,
    )


def _margin_widget():
    widget = StickChartWidget(_margin_sticks())
    widget.resize(500, 300)
    widget._set_x_window((11.0, 29.0))
    return widget


def test_a_stick_outside_the_window_is_not_clickable_from_where_its_band_would_be(qapp):
    widget = _margin_widget()
    sticks = widget.annotation().sticks
    outside = [i for i, s in enumerate(sticks) if not widget.in_view(s.x)]
    assert outside == [0, 2, 3], "setup: 10, 30 and 40 are outside the (11, 29) window"
    for index in outside:
        band = widget.hit_regions()[index]
        assert widget.stick_index_at(band.center().x(), band.center().y()) is None
    inside = next(i for i, s in enumerate(sticks) if widget.in_view(s.x))
    band = widget.hit_regions()[inside]
    assert widget.stick_index_at(band.center().x(), band.center().y()) == inside


def test_a_stick_out_of_view_is_not_painted_into_the_margin(qapp):
    widget = _margin_widget()
    stick_blue = QColor(30, 100, 200).rgb()
    rect = widget._plot_rect()

    def blue_columns():
        image = QImage(widget.size(), QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        widget.render(image)
        return {
            x
            for x in range(widget.width())
            for y in range(int(rect.top()), int(rect.bottom()))
            if image.pixel(x, y) == stick_blue
        }

    columns = blue_columns()
    assert columns, "setup: the stick in view is drawn"
    assert all(rect.left() <= x <= rect.right() for x in columns), (
        "ink outside the plot is a stick that was out of view and was drawn anyway"
    )


def test_a_new_annotation_clears_a_window_left_by_the_last_one(qapp):
    widget = _stick_widget()
    rect = widget._plot_rect()
    for _ in range(3):
        _wheel(widget, rect.left() + 5, rect.center().y(), 120, CTRL)
    assert widget.is_zoomed()
    widget.set_annotation(_sticks())
    assert not widget.is_zoomed()


def test_a_zoomed_histogram_rescales_its_count_axis_to_the_bins_in_view(qapp):
    widget = _histogram()
    distribution = widget._distribution
    rect = widget._plot_rect()
    whole_tallest = max(distribution.counts)
    # Zoom toward the thin right-hand tail.
    for _ in range(8):
        _wheel(widget, rect.right() - 5, rect.center().y(), 120, CTRL)
    visible = [distribution.counts[i] for i, _l, _r in widget._visible_bins()]
    assert visible and max(visible) < whole_tallest
    low, high = widget.view_range()
    assert low > distribution.bin_edges[0]
    # A bin cut by the window is drawn only to the window's edge.
    assert widget._x_of(rect, low) == pytest.approx(rect.left())
    assert widget._x_of(rect, high) == pytest.approx(rect.right())


def test_the_median_line_is_not_drawn_when_it_is_out_of_view(qapp):
    widget = _histogram()
    rect = widget._plot_rect()
    assert widget.in_view(widget._distribution.median)
    for _ in range(8):
        _wheel(widget, rect.right() - 5, rect.center().y(), 120, CTRL)
    assert not widget.in_view(widget._distribution.median)


def test_the_painted_bars_use_the_bins_in_view_for_their_height(qapp):
    """The tallest bar in view reaches the top of the plot; against the whole column's maximum
    the thin tail would be a row of slivers."""
    widget = _histogram()
    rect = widget._plot_rect()
    bar = QColor(70, 120, 180).rgb()

    def reaches_top():
        image = QImage(widget.size(), QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        widget.render(image)
        row = int(rect.top()) + 2
        return any(image.pixel(x, row) == bar for x in range(int(rect.left()), int(rect.right())))

    assert reaches_top(), "setup: unzoomed, the tallest bin reaches the top"
    for _ in range(8):
        _wheel(widget, rect.right() - 5, rect.center().y(), 120, CTRL)
    assert max(widget._distribution.counts[i] for i, _l, _r in widget._visible_bins()) == 1
    assert reaches_top()


def test_the_count_axis_never_repeats_a_label(qapp):
    """A tallest bin of 1 has a half of 0.5, which rounds to 0: three evenly spaced labels read
    "1, 0, 0". Drawn here by recording what the painter is asked to write."""
    from PySide6.QtGui import QPainter

    widget = _histogram()
    rect = widget._plot_rect()
    for _ in range(8):
        _wheel(widget, rect.right() - 5, rect.center().y(), 120, CTRL)
    drawn: list[str] = []
    real = QPainter.drawText

    def spy(self, *args):
        if args and isinstance(args[-1], str):
            drawn.append(args[-1])
        return real(self, *args)

    QPainter.drawText = spy
    try:
        widget.grab()
    finally:
        QPainter.drawText = real
    counts = [t for t in drawn if t in {"0", "1", "2"}]
    assert counts == ["0", "1"], counts
