from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtTest import QTest

from conftest import ink

from openchem.chem.nmr_signals import NMRSignal
from openchem.ui.widgets.nmr_spectrum_widget import NmrSpectrumWidget


def _paint(widget) -> None:
    """Force a real paint.

    `repaint()` and `update()` are BOTH no-ops on a widget that was never
    shown -- measured: zero paintEvent calls either way, against one for
    `grab()`. Three tests here used to call `repaint()` and were passing
    without the painter ever running, including one named "survives a
    repaint". `grab()` renders into a pixmap, which really executes
    paintEvent, and is what `test_ph_curve_widget.py` already uses.
    """
    widget.grab()


def _signal(shift: float, integration: int = 1, atoms: list[int] | None = None) -> NMRSignal:
    return NMRSignal(
        shift=shift,
        atom_indices=atoms if atoms is not None else [int(shift)],
        integration=integration,
        multiplicity="s",
    )


def test_empty_widget_draws_its_axes(qapp):
    """The painter must run even with no signals -- and this is the
    baseline the content tests below measure against."""
    assert ink(NmrSpectrumWidget()) > 0


def test_an_extra_signal_puts_more_ink_on_the_canvas(qapp):
    """Both spectra share their extreme shifts, so the axis range, ticks
    and labels are identical and the only difference is the middle peak.

    Two weaker checks were tried and rejected by mutation testing.
    "Some pixel has alpha" holds for an EMPTY spectrum, because the widget
    fills an opaque background before drawing a mark. "More ink than an
    empty spectrum" also survives blanking the peak loop, because signals
    change the axis range and therefore the tick labels."""
    two = [_signal(1.0, 2, [1]), _signal(9.0, 2, [2])]
    three = [_signal(1.0, 2, [1]), _signal(5.0, 2, [3]), _signal(9.0, 2, [2])]

    assert ink(NmrSpectrumWidget(three)) > ink(NmrSpectrumWidget(two))


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


def test_highlighting_changes_what_is_drawn_and_survives_a_repaint(qapp):
    """Two claims, and the old test made neither. It called `repaint()`,
    which never reaches paintEvent on an unshown widget, then asserted an
    attribute a no-op leaves untouched -- so it passed even against a
    painter that raised on its first line."""
    signals = [_signal(7.2, 2, [11, 12]), _signal(1.4, 3, [20, 21, 22])]
    plain = ink(NmrSpectrumWidget(signals))

    widget = NmrSpectrumWidget(signals)
    widget.set_highlighted_atoms([21])

    assert ink(widget) != plain, "a highlight must be visible, not just recorded"
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


# --- Frequency and solvent peak ------------------------------------------


def _quartet() -> NMRSignal:
    return NMRSignal(
        shift=3.70, atom_indices=[0, 1], integration=2, multiplicity="q", coupling_hz=[7.0]
    )


def test_the_solvent_peak_widens_the_axis_so_it_stays_on_screen(qapp):
    """DMSO's residual peak at 2.50 sits well outside an aromatics-only
    spectrum -- drawing it off the edge of the plot would be worse than
    not drawing it."""
    widget = NmrSpectrumWidget()
    widget.set_signals(
        [NMRSignal(shift=7.2, atom_indices=[0], integration=1, multiplicity="s")]
    )
    without = widget._axis_range()

    widget.set_solvent("DMSO-d6")

    low, high = widget._axis_range()
    assert low < 2.50 < high
    assert low < without[0]


def test_no_solvent_selected_leaves_the_axis_alone(qapp):
    widget = NmrSpectrumWidget()
    widget.set_signals([NMRSignal(shift=7.2, atom_indices=[0], integration=1, multiplicity="s")])
    before = widget._axis_range()

    widget.set_solvent(None)

    assert widget._axis_range() == before


def test_a_solvent_with_no_entry_for_the_active_nucleus_draws_nothing(qapp):
    """D2O has no carbon to observe. Its missing 13C value must read as
    "no peak", not as 0 ppm."""
    widget = NmrSpectrumWidget()
    widget.set_signals(
        [NMRSignal(shift=40.0, atom_indices=[0], integration=1, multiplicity="s", element="C")]
    )
    widget.set_solvent("D2O")

    assert widget._solvent_shift() is None


def test_the_widget_paints_a_split_multiplet(qapp):
    """The paint path has to survive multiplet splitting, a solvent line
    and a highlight together, and a QPainter error only shows up when
    something actually paints.

    The old assertion here was "some pixel has alpha", which this widget
    satisfies by filling an opaque background before drawing a single
    mark -- it held for an EMPTY spectrum too. What this checks instead is
    that splitting actually draws MORE than the same signal unsplit, with
    the axis range pinned by identical shifts either way."""
    split = NmrSpectrumWidget()
    split.set_signals([_quartet()])
    split.set_solvent("CDCl3")
    split.set_frequency(60.0)
    split.set_highlighted_atoms([0])

    unsplit = NmrSpectrumWidget()
    unsplit.set_signals([_quartet()])
    unsplit.set_solvent("CDCl3")
    unsplit.set_frequency(0.0)  # no frequency -> no multiplet splitting

    assert ink(split) > ink(unsplit)


def test_clicking_anywhere_on_a_split_signal_still_selects_it(qapp):
    """The hit region is anchored on the signal's centre shift, so
    splitting the drawn lines must not make the peak unclickable."""
    widget = NmrSpectrumWidget()
    widget.resize(400, 300)
    widget.set_signals([_quartet()])
    widget.set_frequency(60.0)

    region, signal = widget.hit_regions()[0]
    assert widget.signal_at(region.center().x(), region.center().y()) is signal
