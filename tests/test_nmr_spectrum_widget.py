from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtTest import QTest

from openchem.chem.nmr_signals import NMRSignal
from openchem.ui.widgets.nmr_spectrum_widget import NmrSpectrumWidget


def _signal(shift: float, integration: int = 1, atoms: list[int] | None = None) -> NMRSignal:
    return NMRSignal(
        shift=shift,
        atom_indices=atoms if atoms is not None else [int(shift)],
        integration=integration,
        multiplicity="s",
    )


def test_empty_widget_renders_without_crashing(qapp):
    widget = NmrSpectrumWidget()
    widget.resize(400, 250)
    widget.repaint()  # would raise if paintEvent crashed


def test_signals_render_without_crashing(qapp):
    widget = NmrSpectrumWidget([_signal(7.2, 2, [1, 2]), _signal(1.4, 6, [3, 4, 5, 6, 7, 8])])
    widget.resize(400, 250)
    widget.repaint()


def test_set_signals_replaces_data(qapp):
    widget = NmrSpectrumWidget([_signal(1.0)])
    widget.set_signals([_signal(2.0), _signal(3.0)], x_label="¹H δ (ppm)")

    assert len(widget._signals) == 2
    assert widget._x_label == "¹H δ (ppm)"


def test_axis_range_pads_a_single_peak(qapp):
    widget = NmrSpectrumWidget([_signal(5.0)])
    low, high = widget._axis_range()
    assert low < 5.0 < high


def test_higher_ppm_plots_further_left(qapp):
    """NMR convention: the shift axis descends left to right."""
    widget = NmrSpectrumWidget([_signal(0.0), _signal(10.0)])
    plot_rect = QRectF(0, 0, 100, 100)

    x_low = widget._to_widget_x(0.0, plot_rect, (0.0, 10.0))
    x_high = widget._to_widget_x(10.0, plot_rect, (0.0, 10.0))

    assert x_high < x_low


def test_clicking_a_peak_emits_its_atom_indices(qapp):
    widget = NmrSpectrumWidget([_signal(7.2, 2, [11, 12]), _signal(1.4, 3, [20, 21, 22])])
    widget.resize(400, 250)
    emitted: list[list[int]] = []
    widget.peak_clicked.connect(emitted.append)

    region, _signal_at_region = widget.hit_regions()[0]
    center = region.center()
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(int(center.x()), int(center.y())))

    assert emitted == [[11, 12]]
    assert widget._highlighted_atoms == {11, 12}


def test_hit_regions_exist_before_the_first_paint(qapp):
    """Regions are derived from geometry rather than recorded during
    paintEvent, so a click resolves even on a widget that hasn't painted."""
    widget = NmrSpectrumWidget([_signal(7.2, 2, [11, 12])])
    widget.resize(400, 250)
    assert len(widget.hit_regions()) == 1


def test_a_click_outside_any_peak_resolves_to_nothing(qapp):
    widget = NmrSpectrumWidget([_signal(7.2)])
    widget.resize(400, 250)
    assert widget.signal_at(0.0, 0.0) is None


def test_highlighting_survives_a_repaint(qapp):
    widget = NmrSpectrumWidget([_signal(7.2, 2, [11, 12]), _signal(1.4, 3, [20, 21, 22])])
    widget.resize(400, 250)
    widget.set_highlighted_atoms([21])
    widget.repaint()

    assert widget._highlighted_atoms == {21}


def test_set_signals_clears_a_stale_highlight(qapp):
    """Atom indices from the previous spectrum would otherwise highlight
    unrelated peaks in the new one."""
    widget = NmrSpectrumWidget([_signal(7.2, 2, [11, 12])])
    widget.set_highlighted_atoms([11])
    widget.set_signals([_signal(3.0, 1, [11])])

    assert widget._highlighted_atoms == set()


def test_peaks_at_the_same_shift_both_get_a_region(qapp):
    """Diastereotopic protons split into two signals that share a shift
    whenever the predictor doesn't distinguish them -- both must still be
    present, not collapsed."""
    widget = NmrSpectrumWidget([_signal(2.3, 1, [22]), _signal(2.3, 1, [23])])
    widget.resize(400, 250)
    assert len(widget.hit_regions()) == 2
