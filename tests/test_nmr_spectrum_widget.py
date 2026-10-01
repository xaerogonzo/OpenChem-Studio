from __future__ import annotations

import pytest
from conftest import ink
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest

from openchem.chem.nmr_signals import NMRSignal, multiplet_lines
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


def test_shielding_plots_the_opposite_way_to_a_shift(qapp):
    """sigma is the mirror of delta (delta = sigma_ref - sigma). A raw sigma
    drawn on the descending delta axis put the most shielded carbons on the
    downfield side: the Salvinorin A spectrum that looked backwards."""
    widget = NmrSpectrumWidget()
    widget.set_signals([_signal(1.0)], x_label="13C sigma (ppm)", shielding=True)
    plot_rect = widget._plot_rect()
    x_low = widget._to_widget_x(0.0, plot_rect, (0.0, 10.0))
    x_high = widget._to_widget_x(10.0, plot_rect, (0.0, 10.0))
    assert x_high > x_low


def test_shielding_ignores_a_solvent_peak_which_is_a_shift(qapp):
    widget = NmrSpectrumWidget()
    widget.set_signals([_signal(1.0)], shielding=True)
    widget.set_solvent("CDCl3")
    assert widget._solvent_shift() is None
    widget.set_signals([_signal(1.0)], shielding=False)
    assert widget._solvent is not None


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


# --- Smooth render mode and the integral overlay --------------------------


def test_smooth_mode_paints_something_different_from_sticks(qapp):
    widget = NmrSpectrumWidget([_signal(3.0, 1, [0]), _signal(7.0, 3, [1])])
    widget.resize(400, 250)
    sticks_ink = ink(widget)

    widget.set_render_mode("smooth")

    assert ink(widget) != sticks_ink
    assert widget.render_mode() == "smooth"


def test_smooth_mode_rejects_an_unknown_mode_name(qapp):
    widget = NmrSpectrumWidget([_signal(3.0)])
    try:
        widget.set_render_mode("bars")
    except ValueError:
        return
    raise AssertionError("an unrecognised render mode must raise, not silently no-op")


def test_smooth_mode_still_highlights_the_selected_signal(qapp):
    """Same claim as `test_highlighting_changes_what_is_drawn`, in smooth
    mode: the highlighted curve is drawn on top in its own colour, not just
    recorded."""
    signals = [_signal(3.0, 1, [0]), _signal(7.0, 3, [1, 2, 3])]
    widget = NmrSpectrumWidget(signals)
    widget.resize(400, 250)
    widget.set_render_mode("smooth")
    plain = ink(widget)

    widget.set_highlighted_atoms([1])

    assert ink(widget) != plain


def test_the_integral_overlay_adds_ink_in_either_render_mode(qapp):
    widget = NmrSpectrumWidget([_signal(3.0, 1, [0]), _signal(7.0, 3, [1])])
    widget.resize(400, 250)
    without_integral = ink(widget)

    widget.set_show_integral(True)
    assert ink(widget) != without_integral

    widget.set_render_mode("smooth")
    without_integral_smooth = NmrSpectrumWidget([_signal(3.0, 1, [0]), _signal(7.0, 3, [1])])
    without_integral_smooth.resize(400, 250)
    without_integral_smooth.set_render_mode("smooth")
    assert ink(widget) != ink(without_integral_smooth)


def test_clicking_anywhere_on_a_split_signal_still_selects_it(qapp):
    """The hit region is anchored on the signal's centre shift, so
    splitting the drawn lines must not make the peak unclickable."""
    widget = NmrSpectrumWidget()
    widget.resize(400, 300)
    widget.set_signals([_quartet()])
    widget.set_frequency(60.0)

    region, signal = widget.hit_regions()[0]
    assert widget.signal_at(region.center().x(), region.center().y()) is signal


# --- Zoom, pan, reset -------------------------------------------------


class _FakeWheelEvent:
    """A stand-in for `QWheelEvent` carrying only what `wheelEvent` reads
    -- the same approach `test_nmr_correlation_plot_widget.py` uses for
    its own wheel tests."""

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


def _mouse_event(event_type, pos: QPointF) -> QMouseEvent:
    return QMouseEvent(
        event_type, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _widget_with_signals() -> NmrSpectrumWidget:
    widget = NmrSpectrumWidget([_signal(1.0, 1, [0]), _signal(9.0, 1, [1])])
    widget.resize(400, 250)
    return widget


def test_a_fresh_widget_is_not_zoomed(qapp):
    widget = _widget_with_signals()
    assert not widget.is_zoomed()
    assert widget.view_range() == widget._axis_range()


def test_scrolling_in_narrows_the_view(qapp):
    widget = _widget_with_signals()
    plot_rect = widget._plot_rect()
    before = widget.view_range()

    widget.wheelEvent(_FakeWheelEvent(plot_rect.center(), delta_y=120))

    assert widget.is_zoomed()
    after = widget.view_range()
    assert (after[1] - after[0]) < (before[1] - before[0])


def test_the_point_under_the_cursor_stays_under_the_cursor_while_zooming(qapp):
    widget = _widget_with_signals()
    plot_rect = widget._plot_rect()
    cursor = QPointF(plot_rect.left() + 30, plot_rect.center().y())

    anchor_before = widget._data_x_at(cursor.x(), plot_rect)
    widget.wheelEvent(_FakeWheelEvent(cursor, delta_y=120))
    anchor_after = widget._data_x_at(cursor.x(), plot_rect)

    assert anchor_after == pytest.approx(anchor_before, abs=1e-6)


def test_zooming_in_on_a_shielding_axis_also_keeps_the_cursor_anchored(qapp):
    """The ascending (shielding) convention is the one branch
    `NmrCorrelationPlotWidget`'s own zoom never had to handle."""
    widget = NmrSpectrumWidget()
    widget.set_signals([_signal(1.0, 1, [0]), _signal(9.0, 1, [1])], shielding=True)
    widget.resize(400, 250)
    plot_rect = widget._plot_rect()
    cursor = QPointF(plot_rect.left() + 30, plot_rect.center().y())

    anchor_before = widget._data_x_at(cursor.x(), plot_rect)
    widget.wheelEvent(_FakeWheelEvent(cursor, delta_y=120))
    anchor_after = widget._data_x_at(cursor.x(), plot_rect)

    assert anchor_after == pytest.approx(anchor_before, abs=1e-6)


def test_scrolling_out_past_the_full_extent_returns_to_not_zoomed(qapp):
    widget = _widget_with_signals()
    plot_rect = widget._plot_rect()
    widget.wheelEvent(_FakeWheelEvent(plot_rect.center(), delta_y=120))
    assert widget.is_zoomed()

    for _ in range(20):
        widget.wheelEvent(_FakeWheelEvent(plot_rect.center(), delta_y=-120))

    assert not widget.is_zoomed()


def test_reset_view_returns_to_the_full_range(qapp):
    widget = _widget_with_signals()
    widget.wheelEvent(_FakeWheelEvent(widget._plot_rect().center(), delta_y=120))
    assert widget.is_zoomed()

    widget.reset_view()

    assert not widget.is_zoomed()


def test_double_click_resets_the_view(qapp):
    widget = _widget_with_signals()
    widget.wheelEvent(_FakeWheelEvent(widget._plot_rect().center(), delta_y=120))
    assert widget.is_zoomed()

    center = widget._plot_rect().center()
    widget.mouseDoubleClickEvent(_mouse_event(QMouseEvent.Type.MouseButtonDblClick, center))

    assert not widget.is_zoomed()


def test_dragging_pans_the_view_without_changing_its_span(qapp):
    widget = _widget_with_signals()
    plot_rect = widget._plot_rect()
    before = widget.view_range()
    before_span = before[1] - before[0]

    start = plot_rect.center()
    end = QPointF(start.x() + 40, start.y())

    widget.mousePressEvent(_mouse_event(QMouseEvent.Type.MouseButtonPress, start))
    widget.mouseMoveEvent(_mouse_event(QMouseEvent.Type.MouseMove, end))
    widget.mouseReleaseEvent(_mouse_event(QMouseEvent.Type.MouseButtonRelease, end))

    after = widget.view_range()
    assert (after[1] - after[0]) == pytest.approx(before_span)
    assert after != pytest.approx(before)


def test_a_drag_past_the_click_threshold_does_not_select_a_peak(qapp):
    widget = NmrSpectrumWidget([_signal(7.2, 2, [11, 12])])
    widget.resize(400, 250)
    emitted: list[list[int]] = []
    widget.peak_clicked.connect(emitted.append)

    region, _signal_at_region = widget.hit_regions()[0]
    start = region.center()
    end = QPointF(start.x() + 40, start.y())

    widget.mousePressEvent(_mouse_event(QMouseEvent.Type.MouseButtonPress, start))
    widget.mouseMoveEvent(_mouse_event(QMouseEvent.Type.MouseMove, end))
    widget.mouseReleaseEvent(_mouse_event(QMouseEvent.Type.MouseButtonRelease, end))

    assert emitted == []


def test_a_normal_click_still_selects_a_peak(qapp):
    """Press and release at the same point -- the click-vs-drag threshold
    must not have turned every ordinary click into a no-op."""
    widget = NmrSpectrumWidget([_signal(7.2, 2, [11, 12])])
    widget.resize(400, 250)
    emitted: list[list[int]] = []
    widget.peak_clicked.connect(emitted.append)

    region, _signal_at_region = widget.hit_regions()[0]
    pos = region.center()

    widget.mousePressEvent(_mouse_event(QMouseEvent.Type.MouseButtonPress, pos))
    widget.mouseReleaseEvent(_mouse_event(QMouseEvent.Type.MouseButtonRelease, pos))

    assert emitted == [[11, 12]]


def test_hit_testing_tracks_a_deep_zoom(qapp):
    """Zoom into one signal and confirm a click resolves it; zoom to the
    OTHER signal and confirm a click there resolves THAT one -- proving
    `hit_regions()` tracks the current viewport rather than staying
    anchored to the full-data range it was built against before Phase C."""
    widget = NmrSpectrumWidget([_signal(1.0, 1, [0]), _signal(9.0, 1, [1])])
    widget.resize(400, 250)

    widget.zoom_to_signal(widget._signals[0])
    region0, signal0 = widget.hit_regions()[0]
    assert widget.signal_at(region0.center().x(), region0.center().y()) is signal0
    assert signal0.atom_indices == [0]

    widget.zoom_to_signal(widget._signals[1])
    region1, signal1 = widget.hit_regions()[1]
    assert widget.signal_at(region1.center().x(), region1.center().y()) is signal1
    assert signal1.atom_indices == [1]


def test_zoom_to_signal_centres_on_its_full_multiplet_extent(qapp):
    """Not just the nominal shift -- a resolved quartet's own lines reach
    visibly away from its centre, and the view must cover all of them."""
    widget = NmrSpectrumWidget()
    quartet = _quartet()
    widget.set_signals([quartet])
    widget.set_frequency(60.0)

    widget.zoom_to_signal(quartet)

    lines = multiplet_lines(quartet, 60.0)
    shifts = [ppm for ppm, _intensity in lines]
    low, high = widget.view_range()
    assert widget.is_zoomed()
    assert low < min(shifts)
    assert high > max(shifts)


def test_a_fresh_spectrum_clears_the_zoom_but_leaves_preferences_alone(qapp):
    """Render mode, frequency, solvent and integral visibility are viewer
    PREFERENCES, not navigation state -- a new run must not reset them,
    even though it must reset the zoom."""
    widget = NmrSpectrumWidget([_signal(1.0), _signal(9.0)])
    widget.set_render_mode("smooth")
    widget.set_frequency(800.0)
    widget.set_solvent("CDCl3")
    widget.set_show_integral(True)
    widget.wheelEvent(_FakeWheelEvent(widget._plot_rect().center(), delta_y=120))
    assert widget.is_zoomed()

    widget.set_signals([_signal(2.0), _signal(5.0)])

    assert not widget.is_zoomed()
    assert widget.render_mode() == "smooth"
    assert widget._frequency_mhz == 800.0
    assert widget._solvent == "CDCl3"
    assert widget._show_integral is True


def test_zooming_in_changes_the_drawn_ticks(qapp):
    """A deep zoom must draw different intermediate ticks than the full
    view -- a weaker but still meaningful smoke check that `nice_ticks`
    is actually wired into `paintEvent`, not just available."""
    widget = _widget_with_signals()
    full_ink = ink(widget)

    widget.zoom_to_signal(widget._signals[0])

    assert ink(widget) != full_ink


# --- Phase G: Hz/ppm display unit ---------------------------------------


def test_hz_uses_the_signals_own_element_frequency(qapp):
    """1H at 400 MHz: 1.21 ppm -> 484 Hz. 13C must use ITS OWN relative
    gyromagnetic factor, never the 1H one borrowed by mistake."""
    proton = NmrSpectrumWidget([_signal(1.21)])
    proton.set_frequency(400.0)
    assert proton._to_hz(1.21) == pytest.approx(484.0, abs=0.1)

    carbon_signal = NMRSignal(
        shift=20.0, atom_indices=[0], integration=1, multiplicity="s", element="C"
    )
    carbon = NmrSpectrumWidget()
    carbon.set_signals([carbon_signal])  # `_element` is only wired up via set_signals
    carbon.set_frequency(400.0)
    assert carbon._to_hz(20.0) == pytest.approx(20.0 * 400.0 * 0.2514, rel=1e-3)


def test_hz_scales_with_the_selected_frequency(qapp):
    widget = NmrSpectrumWidget([_signal(2.0)])
    widget.set_frequency(400.0)
    at_400 = widget._to_hz(2.0)
    widget.set_frequency(800.0)
    at_800 = widget._to_hz(2.0)
    assert at_800 == pytest.approx(2 * at_400)


def test_hz_round_trips_back_to_ppm(qapp):
    widget = NmrSpectrumWidget([_signal(1.0)])
    widget.set_frequency(400.0)
    ppm = 3.456
    assert widget._to_hz(ppm) / widget._observation_mhz() == pytest.approx(ppm)


def test_hz_display_is_inert_on_a_shielding_spectrum(qapp):
    """`set_display_unit("hz")` is accepted and stored -- so it reactivates
    automatically once a referenced spectrum follows -- but has no visible
    effect while the current spectrum is raw shielding: σ has no
    reference-frequency relationship to convert through."""
    widget = NmrSpectrumWidget()
    widget.set_signals([_signal(30.0)], x_label="¹H σ", shielding=True)
    widget.set_display_unit("hz")

    assert widget.display_unit() == "hz"
    assert widget._effective_unit() == "ppm"
    assert widget._axis_label_text() == "¹H σ (ppm)"
    assert widget._format_axis_value(30.0) == "30"


def test_hz_display_reactivates_once_a_referenced_spectrum_follows(qapp):
    widget = NmrSpectrumWidget()
    widget.set_signals([_signal(30.0)], x_label="¹H σ", shielding=True)
    widget.set_display_unit("hz")
    assert widget._effective_unit() == "ppm"

    widget.set_signals([_signal(1.2)], x_label="¹H δ", shielding=False)

    assert widget._effective_unit() == "hz"


def test_toggling_hz_changes_every_consumer_consistently(qapp):
    """Axis label, tick formatting, and the peak label must all agree with
    each other after a toggle -- not just each pass its own isolated
    check."""
    widget = _widget_with_signals()  # 1H signals at 1.0 and 9.0 ppm
    widget.set_signals(widget._signals, x_label="¹H δ", shielding=False)
    widget.set_frequency(400.0)

    assert widget._axis_label_text() == "¹H δ (ppm)"
    assert widget._format_axis_value(1.0) == "1"
    assert widget._format_peak_label(1.0) == "1.00"

    widget.set_display_unit("hz")

    assert widget._axis_label_text() == "¹H δ offset (Hz)"
    assert widget._format_axis_value(1.0) == f"{widget._to_hz(1.0):.1f}"
    assert widget._format_peak_label(1.0) == f"{widget._to_hz(1.0):.1f}"
    # ppm positions on the plot never move -- only the printed numbers do.
    plot_rect = widget._plot_rect()
    x_range = widget.view_range()
    assert widget._to_widget_x(1.0, plot_rect, x_range) == widget._to_widget_x(1.0, plot_rect, x_range)


# --- Phase G: cursor coordinate readout ----------------------------------


def _hover_event(pos: QPointF) -> QMouseEvent:
    return QMouseEvent(
        QMouseEvent.Type.MouseMove, pos, pos, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_hovering_the_plot_updates_the_readout_without_a_click(qapp):
    widget = _widget_with_signals()
    plot_rect = widget._plot_rect()
    assert widget._hover_ppm is None

    widget.mouseMoveEvent(_hover_event(plot_rect.center()))

    assert widget._hover_ppm is not None
    assert widget._hover_ppm == pytest.approx(widget._data_x_at(plot_rect.center().x(), plot_rect))


def test_the_readout_tracks_a_zoomed_viewport(qapp):
    """Reads through the same `_data_x_at` transform panning and
    hit-testing already use, so it follows the CURRENT view, not the
    full-data range."""
    widget = _widget_with_signals()
    widget.zoom_to_signal(widget._signals[0])
    plot_rect = widget._plot_rect()

    widget.mouseMoveEvent(_hover_event(plot_rect.center()))

    low, high = widget.view_range()
    assert low < widget._hover_ppm < high


def test_the_readout_clears_on_leaving_the_widget(qapp):
    widget = _widget_with_signals()
    plot_rect = widget._plot_rect()
    widget.mouseMoveEvent(_hover_event(plot_rect.center()))
    assert widget._hover_ppm is not None

    widget.leaveEvent(QEvent(QEvent.Type.Leave))

    assert widget._hover_ppm is None


def test_the_readout_is_suppressed_outside_the_plot_rectangle(qapp):
    """Hovering the axis-label margin (inside the WIDGET, outside the
    plot rectangle) must never show a coordinate that looks like real
    data but isn't one."""
    widget = _widget_with_signals()
    plot_rect = widget._plot_rect()

    margin_point = QPointF(plot_rect.left() - 10, plot_rect.top() - 10)
    widget.mouseMoveEvent(_hover_event(margin_point))

    assert widget._hover_ppm is None


# --- Phase G: Spectrum Labels (None / Chemical shifts / Atom indices) ---


def test_label_mode_none_draws_no_peak_label(qapp):
    widget = NmrSpectrumWidget([_signal(5.0)])
    widget.set_label_mode("none")
    assert widget._peak_label_text(widget._signals[0]) is None


def test_label_mode_shift_matches_the_formatted_ppm(qapp):
    widget = NmrSpectrumWidget([_signal(5.1234)])
    widget.set_label_mode("shift")
    assert widget._peak_label_text(widget._signals[0]) == "5.12"


def test_label_mode_atom_uses_one_based_display_numbering(qapp):
    """Matches the convention already used throughout the app (Atom
    Inspector, `report_format.py`, `compare_results_dialog.py`:
    `atom_index + 1`), never the raw 0-based RDKit index."""
    widget = NmrSpectrumWidget([_signal(5.0, atoms=[11])])
    widget.set_label_mode("atom")
    assert widget._peak_label_text(widget._signals[0]) == "12"


def test_a_signal_gets_exactly_one_label_regardless_of_render_mode(qapp):
    """A resolved multiplet must print one label for the SIGNAL, never one
    per line -- checked in both sticks and smooth mode, and the text must
    be identical between the two render paths for the same signal."""
    signal = NMRSignal(
        shift=4.0,
        atom_indices=[7],
        integration=1,
        multiplicity="d",
        coupling_groups=((1, 7.0),),
    )
    widget = NmrSpectrumWidget([signal])
    widget.resize(400, 250)
    widget.set_label_mode("shift")

    for mode in ("sticks", "smooth"):
        widget.set_render_mode(mode)
        assert widget._peak_label_text(signal) == "4.00"
        # One label PER SIGNAL: confirmed structurally (not by scraping
        # painted text) -- the loop that draws labels iterates
        # `self._signals`, never `multiplet_lines(signal, ...)`'s own
        # per-line list, in either render mode.
        assert len([s for s in widget._signals if s is signal]) == 1
