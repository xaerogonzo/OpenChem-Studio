"""Zooming the plain line chart without trapping the reader's scrolling.

These charts sit in a scrolling reader, so a plain wheel must keep scrolling the
page; zoom is Ctrl+wheel and pan is Shift+wheel.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

import conftest
from openchem.domain.report import LineChartAnnotation, LineSeries
from openchem.ui.widgets.line_chart_widget import LineChartWidget

GRID = [float(x) for x in range(0, 15)]


def _chart(descending=False):
    return LineChartAnnotation(
        series=(LineSeries(points=tuple((x, x * 2.0) for x in GRID), name="logD"),),
        x_label="pH", y_label="logD", x_descending=descending,
    )


def _widget(descending=False):
    widget = LineChartWidget(_chart(descending))
    widget.resize(400, 300)
    return widget


def _wheel(widget, x, y, delta, modifiers):
    event = QWheelEvent(
        QPointF(x, y), widget.mapToGlobal(QPointF(x, y)), QPoint(0, 0), QPoint(0, delta),
        Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False,
    )
    event.ignore()
    QApplication.sendEvent(widget, event)
    return event


CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
NONE = Qt.KeyboardModifier.NoModifier


def test_a_plain_wheel_is_not_taken_so_the_reader_still_scrolls(qapp):
    widget = _widget()
    c = widget._plot_rect().center()
    event = _wheel(widget, c.x(), c.y(), 120, NONE)
    assert not event.isAccepted() and not widget.is_zoomed()


def test_ctrl_wheel_zooms_around_the_cursor_and_keeps_that_x_fixed(qapp):
    widget = _widget()
    rect = widget._plot_rect()
    x = rect.left() + rect.width() * 0.25
    before = widget._x_range()
    anchor = before[0] + 0.25 * (before[1] - before[0])

    event = _wheel(widget, x, rect.center().y(), 120, CTRL)

    assert event.isAccepted() and widget.is_zoomed()
    low, high = widget.view_range()
    assert (high - low) < (before[1] - before[0])
    assert low + 0.25 * (high - low) == pytest.approx(anchor)


def test_it_zooms_the_same_way_on_a_descending_axis(qapp):
    widget = _widget(descending=True)
    rect = widget._plot_rect()
    x = rect.left() + rect.width() * 0.25  # the HIGH end is on the left here
    full = widget._x_range()
    anchor = full[1] - 0.25 * (full[1] - full[0])
    _wheel(widget, x, rect.center().y(), 120, CTRL)
    low, high = widget.view_range()
    assert high - 0.25 * (high - low) == pytest.approx(anchor)


def test_zooming_all_the_way_out_drops_back_to_the_whole_curve(qapp):
    widget = _widget()
    c = widget._plot_rect().center()
    _wheel(widget, c.x(), c.y(), 120, CTRL)
    for _ in range(40):
        _wheel(widget, c.x(), c.y(), -120, CTRL)
    assert not widget.is_zoomed()


def test_shift_wheel_pans_a_zoomed_chart_and_never_off_the_data(qapp):
    widget = _widget()
    c = widget._plot_rect().center()
    _wheel(widget, c.x(), c.y(), 120, CTRL)
    first = widget.view_range()
    _wheel(widget, c.x(), c.y(), -120, SHIFT)
    moved = widget.view_range()
    assert moved[0] > first[0] and (moved[1] - moved[0]) == pytest.approx(first[1] - first[0])
    for _ in range(100):
        _wheel(widget, c.x(), c.y(), -120, SHIFT)
    assert widget.view_range()[1] <= GRID[-1] + 1e-9


def test_shift_wheel_does_nothing_when_not_zoomed(qapp):
    widget = _widget()
    c = widget._plot_rect().center()
    _wheel(widget, c.x(), c.y(), 120, SHIFT)
    assert not widget.is_zoomed()


def test_double_click_restores_the_whole_curve(qapp):
    widget = _widget()
    c = widget._plot_rect().center()
    _wheel(widget, c.x(), c.y(), 120, CTRL)
    full = widget._full_x_range()
    QApplication.sendEvent(widget, QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick, c, c, Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, NONE,
    ))
    assert not widget.is_zoomed() and widget.view_range() == full


def test_a_reading_only_lands_on_a_sample_that_is_on_screen(qapp):
    widget = _widget()
    widget._set_x_window((3.2, 4.8))
    assert widget._sampled_x() == [4.0]
    widget._set_x_window((3.2, 3.4))  # narrower than the sampling: fall back, never nothing
    assert widget._sampled_x() == GRID


def test_a_new_annotation_resets_the_zoom(qapp):
    widget = _widget()
    widget._set_x_window((3.0, 5.0))
    widget.set_annotation(_chart())
    assert not widget.is_zoomed()


def test_view_changed_fires_once_per_real_change(qapp):
    widget = _widget()
    seen: list[int] = []
    widget.view_changed.connect(lambda: seen.append(1))
    widget._set_x_window((3.0, 5.0))
    widget._set_x_window((3.0, 5.0))
    widget.reset_view()
    widget.reset_view()
    assert len(seen) == 2


def test_a_zoomed_chart_clips_the_curve_to_the_plot(qapp):
    """Nothing is drawn left of the plot: the margin that holds the y labels must
    be identical for a zoomed chart and one with the curve entirely off screen."""
    zoomed = _widget()
    zoomed._set_x_window((6.0, 8.0))
    image = zoomed.grab().toImage()
    rect = zoomed._plot_rect()
    strip = image.copy(0, int(rect.top()) + 5, int(rect.left()) - 2, int(rect.height()) - 10)
    def is_curve(colour):  # the first series is orange (214, 96, 39); allow anti-aliasing
        return colour.red() > 170 and colour.green() < 150 and colour.blue() < 100

    curve_pixels = [
        (x, y) for x in range(strip.width()) for y in range(strip.height()) if is_curve(strip.pixelColor(x, y))
    ]
    assert not curve_pixels  # no curve pixels in the left margin
    conftest.dispose(zoomed)
