from __future__ import annotations

from openchem.ui.widgets.nmr_correlation_plot_widget import NmrCorrelationPlotWidget, Peak


def test_empty_widget_renders_without_crashing(qapp):
    widget = NmrCorrelationPlotWidget()
    widget.resize(300, 300)
    widget.repaint()  # would raise if paintEvent crashed


def test_single_peak_renders_without_crashing(qapp):
    widget = NmrCorrelationPlotWidget([Peak(x=5.0, y=5.0)])
    widget.resize(300, 300)
    widget.repaint()


def test_many_peaks_render_without_crashing(qapp):
    peaks = [Peak(x=float(i), y=float(i) * 2, label=f"p{i}") for i in range(20)]
    widget = NmrCorrelationPlotWidget(peaks, x_label="1H (ppm)", y_label="13C (ppm)")
    widget.resize(400, 400)
    widget.repaint()


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
