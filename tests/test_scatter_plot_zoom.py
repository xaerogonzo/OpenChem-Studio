"""Zooming the scatter plot with Ctrl+wheel, without trapping the reader's scrolling."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from openchem.ui.widgets.scatter_plot_widget import ScatterPlotWidget, ScatterPoint

CTRL = Qt.KeyboardModifier.ControlModifier
NONE = Qt.KeyboardModifier.NoModifier


def _widget():
    points = [ScatterPoint(x=float(i), y=float(i * i), label=f"p{i}") for i in range(11)]
    widget = ScatterPlotWidget(points, "x", "y")
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


def test_a_plain_wheel_is_not_taken(qapp):
    widget = _widget()
    c = widget._plot_rect().center()
    event = _wheel(widget, c.x(), c.y(), 120, NONE)
    assert not event.isAccepted() and not widget.is_zoomed()


def test_ctrl_wheel_zooms_both_axes_around_the_cursor(qapp):
    widget = _widget()
    rect = widget._plot_rect()
    x, y = rect.left() + rect.width() * 0.3, rect.top() + rect.height() * 0.6
    x0, x1, y0, y1 = widget._ranges()
    anchor_x = x0 + 0.3 * (x1 - x0)
    anchor_y = y0 + 0.4 * (y1 - y0)  # y runs bottom-up

    event = _wheel(widget, x, y, 120, CTRL)

    assert event.isAccepted() and widget.is_zoomed()
    a, b, c, d = widget._ranges()
    assert (b - a) < (x1 - x0) and (d - c) < (y1 - y0)
    assert a + 0.3 * (b - a) == pytest.approx(anchor_x)
    assert c + 0.4 * (d - c) == pytest.approx(anchor_y)


def test_a_wheel_outside_the_plot_does_not_zoom(qapp):
    widget = _widget()
    assert not _wheel(widget, 2, 2, 120, CTRL).isAccepted() and not widget.is_zoomed()


def test_zooming_all_the_way_out_drops_the_window(qapp):
    widget = _widget()
    c = widget._plot_rect().center()
    _wheel(widget, c.x(), c.y(), 120, CTRL)
    for _ in range(40):
        _wheel(widget, c.x(), c.y(), -120, CTRL)
    assert not widget.is_zoomed()


def test_double_click_restores_every_point(qapp):
    widget = _widget()
    c = widget._plot_rect().center()
    _wheel(widget, c.x(), c.y(), 120, CTRL)
    full = widget._full_ranges()
    QApplication.sendEvent(widget, QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick, c, c, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, NONE))
    assert not widget.is_zoomed() and widget._ranges() == full


def test_only_points_inside_the_window_can_be_hovered(qapp):
    widget = _widget()
    widget._set_window((4.5, 6.5, 20.0, 45.0))
    assert [widget.points()[i].label for i in widget._visible_indices()] == ["p5", "p6"]
    rect = widget._plot_rect()
    # the cursor just inside the plot edge, next to where p0 WOULD be if it were not off screen
    widget.mouseMoveEvent(QMouseEvent(
        QMouseEvent.Type.MouseMove, QPointF(rect.left() + 2, rect.bottom() - 2),
        QPointF(rect.left() + 2, rect.bottom() - 2), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, NONE))
    assert widget._hover_index is None


def test_new_points_reset_the_zoom(qapp):
    widget = _widget()
    widget._set_window((4.5, 6.5, 20.0, 45.0))
    widget.set_points([ScatterPoint(x=1.0, y=2.0)])
    assert not widget.is_zoomed()


def test_a_zoomed_plot_clips_points_to_the_plot_area(qapp):
    widget = _widget()
    widget._set_window((4.1, 6.5, 0.0, 100.0))  # p4 sits just left of the plot, in the margin
    image = widget.grab().toImage()
    rect = widget._plot_rect()
    strip = image.copy(0, int(rect.top()) + 5, int(rect.left()) - 2, int(rect.height()) - 10)
    dots = [
        1 for x in range(strip.width()) for y in range(strip.height())
        if strip.pixelColor(x, y).blue() > strip.pixelColor(x, y).red() + 50
    ]
    assert not dots
