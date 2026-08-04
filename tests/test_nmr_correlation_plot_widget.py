from __future__ import annotations

from conftest import ink

from openchem.ui.widgets.nmr_correlation_plot_widget import NmrCorrelationPlotWidget, Peak


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


def test_contour_rendering_survives_every_degenerate_case(qapp):
    """Empty, single-peak and identical-position spectra all reach the
    grid code, and a zero-width axis range is the one that would divide
    by zero if `_axis_ranges` had not padded it."""
    for peaks in ([], [Peak(x=5.0, y=5.0)], [Peak(x=3.0, y=3.0), Peak(x=3.0, y=3.0)]):
        widget = NmrCorrelationPlotWidget(peaks)
        widget.resize(260, 260)
        _paint(widget)
