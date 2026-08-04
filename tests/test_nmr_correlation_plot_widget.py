from __future__ import annotations

from PySide6.QtGui import QPixmap

from openchem.ui.widgets.nmr_correlation_plot_widget import NmrCorrelationPlotWidget, Peak


def _paint(widget) -> None:
    """Force a real paint.

    `repaint()` is a no-op on a widget that was never shown, so the
    "renders without crashing" tests below were passing without the
    painter ever running. Rendering into a pixmap actually executes
    `paintEvent`, which is the thing under test.
    """
    widget.render(QPixmap(widget.size()))


def test_empty_widget_renders_without_crashing(qapp):
    widget = NmrCorrelationPlotWidget()
    widget.resize(300, 300)
    _paint(widget)  # would raise if paintEvent crashed


def test_single_peak_renders_without_crashing(qapp):
    widget = NmrCorrelationPlotWidget([Peak(x=5.0, y=5.0)])
    widget.resize(300, 300)
    _paint(widget)


def test_many_peaks_render_without_crashing(qapp):
    peaks = [Peak(x=float(i), y=float(i) * 2, label=f"p{i}") for i in range(20)]
    widget = NmrCorrelationPlotWidget(peaks, x_label="1H (ppm)", y_label="13C (ppm)")
    widget.resize(400, 400)
    _paint(widget)


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
    widget = NmrCorrelationPlotWidget([Peak(x=1.0, y=1.0)])
    assert widget._show_contours is True

    widget.set_show_contours(False)
    widget.resize(300, 300)
    _paint(widget)  # the scatter path must still render
    assert widget._show_contours is False


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
