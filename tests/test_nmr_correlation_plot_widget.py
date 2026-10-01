from __future__ import annotations

import pytest

from PySide6.QtCore import QPoint, QPointF

from conftest import ink

from openchem.ui.widgets.nmr_correlation_plot_widget import NmrCorrelationPlotWidget, Peak


class _FakeWheelEvent:
    """A stand-in for `QWheelEvent` carrying only what `wheelEvent` reads.

    Constructed directly and passed straight to `widget.wheelEvent(...)`,
    bypassing Qt's own event dispatch entirely -- the same "call the
    handler" approach `test_ph_curve_widget.py` uses for mouse events, just
    without fighting `QWheelEvent`'s several overloaded constructors for a
    handler that only ever reads three things off it.
    """

    def __init__(self, pos: QPointF, delta_y: int) -> None:
        self._pos = pos
        self._delta_y = delta_y
        self.accepted = False

    def position(self) -> QPointF:
        return self._pos

    def angleDelta(self) -> QPoint:  # noqa: N802 - Qt naming
        return QPoint(0, self._delta_y)

    def accept(self) -> None:
        self.accepted = True


def _paint(widget) -> None:
    """Force a real paint.

    `repaint()` and `update()` are BOTH no-ops on a widget that was never
    shown -- measured: zero paintEvent calls either way, against one for
    `grab()`. The "renders without crashing" tests below were passing
    without the painter ever running. `grab()` renders into a pixmap,
    which really executes paintEvent.
    """
    widget.grab()


def test_empty_widget_draws_its_frame_and_nothing_else(qapp):
    """Even with no peaks the painter must run and draw the chrome --
    which is also the baseline every content test below measures against."""
    assert ink(NmrCorrelationPlotWidget()) > 0


def test_an_extra_peak_puts_more_ink_on_the_canvas(qapp):
    """Both plots share their extreme peaks, so the axes, ticks and labels
    are identical and the ONLY difference is the peak in the middle.

    Comparing against an empty plot instead would not prove this:
    different data changes the axis range, so the tick labels alone move
    the ink count. Verified by mutation -- blanking the peak-drawing loop
    leaves this failing and the empty-plot comparison passing."""
    two = [Peak(x=1.0, y=1.0), Peak(x=9.0, y=9.0)]
    three = [Peak(x=1.0, y=1.0), Peak(x=5.0, y=5.0), Peak(x=9.0, y=9.0)]

    assert ink(NmrCorrelationPlotWidget(three)) > ink(NmrCorrelationPlotWidget(two))


def test_a_crowded_plot_with_labels_renders(qapp):
    """Twenty labelled peaks exercise the label path and the density grid
    at a size the other tests do not reach. A smoke test on purpose --
    the ink comparison that would prove content here is the one above,
    which holds the axes fixed."""
    peaks = [Peak(x=float(i), y=float(i) * 2, label=f"p{i}") for i in range(20)]

    assert ink(NmrCorrelationPlotWidget(peaks, x_label="1H", y_label="13C")) > 0


def test_set_peaks_replaces_data(qapp):
    widget = NmrCorrelationPlotWidget([Peak(x=1.0, y=1.0)])
    widget.set_peaks([Peak(x=2.0, y=2.0), Peak(x=3.0, y=3.0)], x_label="x", y_label="y")

    assert len(widget._peaks) == 2
    assert widget._x_label == "x"


def test_axis_ranges_pads_a_flat_single_point():
    widget = NmrCorrelationPlotWidget([Peak(x=5.0, y=5.0)])
    x_min, x_max, y_min, y_max = widget._axis_ranges()
    assert x_min < 5.0 < x_max
    assert y_min < 5.0 < y_max


def test_higher_ppm_maps_toward_the_origin_corner():
    """NMR convention: higher shift values plot toward the top-left, not
    the bottom-right -- verified via the coordinate-mapping math directly
    rather than a pixel-diff test."""
    widget = NmrCorrelationPlotWidget([Peak(x=0.0, y=0.0), Peak(x=10.0, y=10.0)])
    from PySide6.QtCore import QRectF

    plot_rect = QRectF(0, 0, 100, 100)
    x_low, y_low = widget._to_widget_coords(0.0, 0.0, plot_rect, (0.0, 10.0), (0.0, 10.0))
    x_high, y_high = widget._to_widget_coords(10.0, 10.0, plot_rect, (0.0, 10.0), (0.0, 10.0))

    assert x_high < x_low  # higher ppm plots further left
    assert y_high < y_low  # higher ppm plots further up


def test_contours_are_on_by_default_and_can_be_turned_off(qapp):
    """Contours are the default because that is how a 2D spectrum is read;
    the dot view stays reachable because it is genuinely clearer when the
    peaks are few and far apart."""
    peaks = [Peak(x=1.0, y=1.0), Peak(x=2.0, y=2.5)]
    assert NmrCorrelationPlotWidget(peaks)._show_contours is True

    # Rings put down more ink than two dots, which is the visible
    # difference between the modes rather than just a flag being flipped.
    contoured = ink(NmrCorrelationPlotWidget(peaks))
    dots = ink(NmrCorrelationPlotWidget(peaks, show_contours=False))
    assert contoured > dots

    widget = NmrCorrelationPlotWidget(peaks)
    widget.set_show_contours(False)
    assert widget._show_contours is False
    assert ink(widget) == dots, "the setter must match construction"


def test_the_density_grid_is_cached_until_the_peaks_change(qapp):
    """The grid is in data coordinates, so a resize does not invalidate
    it. Rebuilding a 200x200 grid on every repaint would be work that
    changes nothing on screen."""
    widget = NmrCorrelationPlotWidget([Peak(x=1.0, y=1.0), Peak(x=2.0, y=2.0)])
    widget.resize(300, 300)
    _paint(widget)
    first = widget._grid
    assert first is not None

    widget.resize(420, 380)
    _paint(widget)
    assert widget._grid is first, "a resize must not rebuild the grid"

    widget.set_peaks([Peak(x=5.0, y=5.0)])
    assert widget._grid is None, "new peaks must invalidate it"


# --- Zoom, pan, reset ------------------------------------------------------


def _widget_with_peaks() -> NmrCorrelationPlotWidget:
    widget = NmrCorrelationPlotWidget([Peak(x=1.0, y=1.0), Peak(x=9.0, y=9.0)])
    widget.resize(400, 400)
    return widget


def test_a_fresh_widget_is_not_zoomed(qapp):
    widget = _widget_with_peaks()
    assert not widget.is_zoomed()
    assert widget.view_ranges() == (widget._axis_ranges()[0:2], widget._axis_ranges()[2:4])


def test_scrolling_in_narrows_the_view_around_the_cursor(qapp):
    widget = _widget_with_peaks()
    plot_rect = widget._plot_rect()

    before_x, before_y = widget.view_ranges()
    widget.wheelEvent(_FakeWheelEvent(plot_rect.center(), delta_y=120))

    assert widget.is_zoomed()
    after_x, after_y = widget.view_ranges()
    assert (after_x[1] - after_x[0]) < (before_x[1] - before_x[0])
    assert (after_y[1] - after_y[0]) < (before_y[1] - before_y[0])


def test_the_point_under_the_cursor_stays_under_the_cursor_while_zooming(qapp):
    widget = _widget_with_peaks()
    plot_rect = widget._plot_rect()
    cursor = QPointF(plot_rect.left() + 30, plot_rect.top() + 40)

    anchor_before = widget._data_point_at(cursor, plot_rect)
    widget.wheelEvent(_FakeWheelEvent(cursor, delta_y=120))
    anchor_after = widget._data_point_at(cursor, plot_rect)

    assert anchor_after[0] == pytest.approx(anchor_before[0], abs=1e-6)
    assert anchor_after[1] == pytest.approx(anchor_before[1], abs=1e-6)


def test_scrolling_out_past_the_full_extent_returns_to_not_zoomed(qapp):
    widget = _widget_with_peaks()
    plot_rect = widget._plot_rect()
    widget.wheelEvent(_FakeWheelEvent(plot_rect.center(), delta_y=120))
    assert widget.is_zoomed()

    for _ in range(20):
        widget.wheelEvent(_FakeWheelEvent(plot_rect.center(), delta_y=-120))

    assert not widget.is_zoomed()


def test_zooming_does_not_rebuild_the_cached_density_grid(qapp):
    """Zoom changes what WINDOW of the grid is drawn, not the grid itself
    -- see `_the_density_grid_is_cached_until_the_peaks_change` for why
    rebuilding it is the thing to avoid."""
    widget = _widget_with_peaks()
    _paint(widget)
    grid = widget._grid
    assert grid is not None

    widget.wheelEvent(_FakeWheelEvent(widget._plot_rect().center(), delta_y=120))
    _paint(widget)

    assert widget._grid is grid


def test_reset_view_returns_to_fit_the_data(qapp):
    widget = _widget_with_peaks()
    widget.wheelEvent(_FakeWheelEvent(widget._plot_rect().center(), delta_y=120))
    assert widget.is_zoomed()

    widget.reset_view()

    assert not widget.is_zoomed()


def test_double_click_resets_the_view(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QMouseEvent

    widget = _widget_with_peaks()
    widget.wheelEvent(_FakeWheelEvent(widget._plot_rect().center(), delta_y=120))
    assert widget.is_zoomed()

    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        widget._plot_rect().center(),
        widget._plot_rect().center(),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.mouseDoubleClickEvent(event)

    assert not widget.is_zoomed()


def test_dragging_pans_the_view_without_changing_its_span(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QMouseEvent

    widget = _widget_with_peaks()
    plot_rect = widget._plot_rect()
    before_x, before_y = widget.view_ranges()
    before_span = (before_x[1] - before_x[0], before_y[1] - before_y[0])

    start = plot_rect.center()
    end = QPointF(start.x() + 40, start.y() + 20)

    def _press_event(button_type, pos):
        return QMouseEvent(
            button_type, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

    widget.mousePressEvent(_press_event(QMouseEvent.Type.MouseButtonPress, start))
    widget.mouseMoveEvent(_press_event(QMouseEvent.Type.MouseMove, end))
    widget.mouseReleaseEvent(_press_event(QMouseEvent.Type.MouseButtonRelease, end))

    after_x, after_y = widget.view_ranges()
    after_span = (after_x[1] - after_x[0], after_y[1] - after_y[0])

    assert after_span[0] == pytest.approx(before_span[0])
    assert after_span[1] == pytest.approx(before_span[1])
    assert (after_x[0], after_x[1]) != (before_x[0], before_x[1])


# --- Click-to-select -------------------------------------------------------


def _click_event(pos: QPointF, event_type=None):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QMouseEvent

    if event_type is None:
        event_type = QMouseEvent.Type.MouseButtonPress
    return QMouseEvent(
        event_type, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_clicking_a_peak_emits_its_atom_pair(qapp):
    from PySide6.QtGui import QMouseEvent

    widget = NmrCorrelationPlotWidget(
        [Peak(x=1.0, y=1.0, atom_a=0, atom_b=1), Peak(x=9.0, y=9.0, atom_a=2, atom_b=3)],
        show_contours=False,
    )
    widget.resize(400, 400)
    plot_rect = widget._plot_rect()
    (x_min, x_max), (y_min, y_max) = widget.view_ranges()
    px, py = widget._to_widget_coords(9.0, 9.0, plot_rect, (x_min, x_max), (y_min, y_max))
    pos = QPointF(px, py)

    emitted: list[tuple[int, int]] = []
    widget.peak_selected.connect(lambda a, b: emitted.append((a, b)))

    widget.mousePressEvent(_click_event(pos, QMouseEvent.Type.MouseButtonPress))
    widget.mouseReleaseEvent(_click_event(pos, QMouseEvent.Type.MouseButtonRelease))

    assert emitted == [(2, 3)]
    assert widget._highlighted_pair == (2, 3)


def test_a_drag_past_the_click_threshold_does_not_select_a_peak(qapp):
    """The same press-drag-release a pan uses must not ALSO fire a peak
    selection -- `_CLICK_MAX_DRIFT` is what tells the two apart."""
    from PySide6.QtGui import QMouseEvent

    widget = NmrCorrelationPlotWidget([Peak(x=1.0, y=1.0, atom_a=0, atom_b=1)])
    widget.resize(400, 400)
    plot_rect = widget._plot_rect()
    start = plot_rect.center()
    end = QPointF(start.x() + 40, start.y())

    emitted: list[tuple[int, int]] = []
    widget.peak_selected.connect(lambda a, b: emitted.append((a, b)))

    widget.mousePressEvent(_click_event(start, QMouseEvent.Type.MouseButtonPress))
    widget.mouseMoveEvent(_click_event(end, QMouseEvent.Type.MouseMove))
    widget.mouseReleaseEvent(_click_event(end, QMouseEvent.Type.MouseButtonRelease))

    assert emitted == []


def test_clicking_empty_space_selects_nothing(qapp):
    widget = NmrCorrelationPlotWidget([Peak(x=1.0, y=1.0, atom_a=0, atom_b=1)])
    widget.resize(400, 400)
    far_corner = QPointF(5.0, 5.0)

    emitted: list[tuple[int, int]] = []
    widget.peak_selected.connect(lambda a, b: emitted.append((a, b)))

    widget.mousePressEvent(_click_event(far_corner))
    widget.mouseReleaseEvent(_click_event(far_corner, type(_click_event(far_corner)).Type.MouseButtonRelease))

    assert emitted == []
    assert widget._highlighted_pair is None


def test_set_highlighted_pair_is_the_inbound_half_of_the_link(qapp):
    """A table-row selection drives this directly -- no click involved."""
    widget = NmrCorrelationPlotWidget([Peak(x=1.0, y=1.0, atom_a=0, atom_b=1)])
    widget.set_highlighted_pair(0, 1)
    assert widget._highlighted_pair == (0, 1)

    widget.set_highlighted_pair(None, None)
    assert widget._highlighted_pair is None


def test_contour_rendering_survives_every_degenerate_case(qapp):
    """Empty, single-peak and identical-position spectra all reach the
    grid code, and a zero-width axis range is the one that would divide
    by zero if `_axis_ranges` had not padded it."""
    for peaks in ([], [Peak(x=5.0, y=5.0)], [Peak(x=3.0, y=3.0), Peak(x=3.0, y=3.0)]):
        widget = NmrCorrelationPlotWidget(peaks)
        widget.resize(260, 260)
        _paint(widget)
