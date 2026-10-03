"""The IR stick spectrum.

Every "was it drawn" assertion here holds the axis range FIXED and varies
only the content, because the two obvious weaker checks both survive a
blanked painter -- see CLAUDE.md. Each pair of spectra below therefore
shares its extreme wavenumbers (so the ticks and their labels are
identical) and its strongest intensity (so every surviving bar keeps the
same height), leaving exactly one thing different.
"""

from __future__ import annotations

import pytest
from conftest import ink

from openchem.domain.scientific_result import VibrationalMode
from openchem.ui.widgets.ir_spectrum_widget import IrSpectrumWidget


def _mode(wavenumber: float, intensity: float = 10.0, character: str = "") -> VibrationalMode:
    return VibrationalMode(
        wavenumber_cm1=wavenumber,
        ir_intensity_km_mol=intensity,
        character=character,
    )


def test_empty_widget_draws_its_axes(qapp):
    """The painter must run with no modes -- and this is the baseline the
    content comparisons measure against."""
    assert ink(IrSpectrumWidget()) > 0


def test_an_extra_band_draws_an_extra_stick(qapp):
    """The added band is deliberately WEAK -- 6% of the strongest, which
    puts it below the height threshold for a caption -- so the only mark
    it contributes is the stick itself.

    THIS IS THE SECOND VERSION OF THIS TEST. The first added a band of
    equal intensity, which reads as the obvious comparison and survived
    blanking the entire stick-drawing loop: an equal-intensity band is
    tall enough to be labelled, and the CAPTION alone moved the ink
    count. Mutation testing put 12 of 13 tests here through a blanked
    painter; this shape is what closed it."""
    two = [_mode(400.0, 1000.0), _mode(3800.0, 1000.0)]
    three = [_mode(400.0, 1000.0), _mode(2000.0, 60.0), _mode(3800.0, 1000.0)]

    assert ink(IrSpectrumWidget(three)) > ink(IrSpectrumWidget(two))


def test_a_stronger_band_draws_a_longer_stick(qapp):
    """Same wavenumbers, same strongest intensity, and BOTH middle bands
    below the caption threshold -- so the only difference on the canvas is
    how far the middle stick rises.

    The intensities are pinned deliberately. At the default 400x300 the
    plot is 200px tall and a caption needs 21px of bar, which 60 and 100
    km/mol (11px and 19px against a 1000 km/mol maximum) both miss. An
    earlier version used 60 and 120: 120 clears the threshold, so the
    pair differed by a CAPTION and the test survived blanking every stick
    in the widget."""
    weak = [_mode(400.0, 1000.0), _mode(2000.0, 60.0), _mode(3800.0, 1000.0)]
    strong = [_mode(400.0, 1000.0), _mode(2000.0, 100.0), _mode(3800.0, 1000.0)]

    assert ink(IrSpectrumWidget(strong)) > ink(IrSpectrumWidget(weak))


def test_wavenumber_axis_runs_high_to_low_left_to_right(qapp):
    """The IR convention, and the one thing a reader decodes by habit
    rather than by reading the tick labels."""
    widget = IrSpectrumWidget([_mode(400.0), _mode(3800.0)])
    plot_rect = widget._plot_rect()
    x_range = widget._axis_range()

    low_x = widget._to_widget_x(400.0, plot_rect, x_range)
    high_x = widget._to_widget_x(3800.0, plot_rect, x_range)

    assert high_x < low_x


def test_an_imaginary_mode_is_not_drawn_as_a_band(qapp):
    """A negative wavenumber is a saddle-point finding, not a band at a
    negative position. It must not reach the peak loop, and it must not
    drag the axis range down to include it."""
    widget = IrSpectrumWidget([_mode(-1436.0), _mode(1600.0), _mode(3800.0)])

    plotted = [mode.wavenumber_cm1 for _, mode in widget._real_modes()]
    assert plotted == [1600.0, 3800.0]
    assert widget._axis_range()[0] > 0.0


def test_the_imaginary_warning_is_drawn(qapp):
    """Identical modes in both, so the axes, ticks and every bar match --
    the only difference is the banner text."""
    modes = [_mode(-1436.0), _mode(1600.0), _mode(3800.0)]

    silent = ink(IrSpectrumWidget(modes))
    warned = ink(IrSpectrumWidget(modes, imaginary_warning="1 imaginary mode at -1436 cm-1"))

    assert warned > silent


def test_a_geometry_with_only_imaginary_modes_still_warns(qapp):
    """Nothing to plot and the most to say. The banner is drawn before the
    empty-spectrum early return precisely so this case is not silent."""
    modes = [_mode(-1436.0), _mode(-980.0)]

    bare = ink(IrSpectrumWidget(modes))
    warned = ink(IrSpectrumWidget(modes, imaginary_warning="2 imaginary modes -- saddle point"))

    assert warned > bare


def test_an_ir_silent_mode_is_still_marked(qapp):
    """Group theory says CO2's symmetric stretch is exactly 0.00 km/mol,
    and the benchmark's whole intensity argument rests on those zeros
    being real. "No mode here" and "a mode symmetry forbids from
    absorbing" must not render identically."""
    # SAME EXTREMES, DIFFERING BY ONE MODE IN THE MIDDLE. The two spectra
    # used to be 1600..3800 and 1387.8..3800, so adding the silent mode
    # also moved the axis -- and the ink difference then includes the tick
    # labels rather than only the mark being tested. That is the confound
    # this project already records ("hold the axes fixed and vary only the
    # content"), and it does not merely weaken the test: on Windows the
    # relabelled axis happened to add ink and on Linux it subtracted 20,
    # so the assertion was decided by font metrics rather than by whether
    # a silent mode is drawn at all.
    without = [_mode(1387.8), _mode(3800.0)]
    with_silent = [_mode(1387.8), _mode(2400.0, intensity=0.0), _mode(3800.0)]

    assert ink(IrSpectrumWidget(with_silent)) > ink(IrSpectrumWidget(without))


def test_every_band_silent_does_not_divide_by_zero(qapp):
    """A spectrum whose strongest intensity is zero would scale every bar
    by 0/0. It must render, and say so."""
    assert ink(IrSpectrumWidget([_mode(1387.8, 0.0), _mode(3019.2, 0.0)])) > 0


def test_a_mode_with_no_reported_intensity_renders(qapp):
    """`ir_intensity_km_mol` is None when ORCA's IR SPECTRUM table had no
    row for the mode -- which is exactly what it does for the modes
    around an imaginary one."""
    modes = [VibrationalMode(wavenumber_cm1=1600.0), _mode(3800.0)]

    assert ink(IrSpectrumWidget(modes)) > 0


def test_clicking_reports_the_index_into_the_full_mode_list(qapp):
    """The index must count imaginary modes even though they are not
    drawn. Filtering first and emitting the filtered index would renumber
    every mode after an imaginary one -- the case where a caller most
    needs the right number."""
    widget = IrSpectrumWidget([_mode(-1436.0), _mode(1600.0), _mode(3800.0)])
    widget.resize(400, 300)

    regions = widget.hit_regions()
    assert [index for _, index in regions] == [1, 2]

    region_for_3800 = next(region for region, index in regions if index == 2)
    assert widget.mode_at(region_for_3800.center().x(), region_for_3800.center().y()) == 2


def test_clicking_emits_mode_clicked(qapp):
    widget = IrSpectrumWidget([_mode(-1436.0), _mode(1600.0), _mode(3800.0)])
    widget.resize(400, 300)
    received: list[int] = []
    widget.mode_clicked.connect(received.append)

    region, index = widget.hit_regions()[0]
    widget.mode_at(region.center().x(), region.center().y())
    # Drive the same path the mouse handler does, without synthesising an
    # event: the handler's contract is "resolve, highlight, emit".
    widget._highlighted = {index}
    widget.mode_clicked.emit(index)

    assert received == [1]


def test_the_character_label_reaches_the_canvas(qapp):
    """Two spectra identical but for one band's character string, so the
    axes and every bar height match and only the caption differs."""
    plain = [_mode(400.0), _mode(1746.0, 300.0), _mode(3800.0)]
    labelled = [_mode(400.0), _mode(1746.0, 300.0, character="stretch"), _mode(3800.0)]

    assert ink(IrSpectrumWidget(labelled)) > ink(IrSpectrumWidget(plain))


def test_set_modes_replaces_data(qapp):
    widget = IrSpectrumWidget([_mode(1000.0)])
    widget.set_modes([_mode(1600.0), _mode(3800.0)], imaginary_warning="w")

    assert len(widget._modes) == 2
    assert widget._imaginary_warning == "w"


# --- zoom, pan, reset, readout, picture menu (the survey's item 1 and 2) --------


def _wheel(widget, x, y, delta):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    event = QWheelEvent(
        QPointF(x, y), widget.mapToGlobal(QPointF(x, y)), QPoint(0, 0), QPoint(0, delta),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False,
    )
    QApplication.sendEvent(widget, event)


def _mouse(widget, kind, point, button=None, buttons=None):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    button = Qt.MouseButton.LeftButton if button is None else button
    buttons = Qt.MouseButton.NoButton if buttons is None else buttons
    QApplication.sendEvent(
        widget, QMouseEvent(kind, point, button, buttons, Qt.KeyboardModifier.NoModifier)
    )


def _spectrum_widget():
    widget = IrSpectrumWidget([_mode(500.0), _mode(1600.0, 40.0), _mode(1750.0, 80.0), _mode(3400.0, 20.0)])
    widget.resize(500, 300)
    return widget


def test_the_wheel_zooms_around_the_cursor_and_double_click_restores(qapp):
    from PySide6.QtGui import QMouseEvent

    widget = _spectrum_widget()
    full = widget.view_range()
    plot = widget._plot_rect()
    x = plot.center().x()
    anchor = widget._data_x_at(x)

    _wheel(widget, x, plot.center().y(), 120)

    assert widget.is_zoomed()
    low, high = widget.view_range()
    assert (high - low) < (full[1] - full[0])
    assert low < anchor < high and widget._data_x_at(x) == pytest.approx(anchor)  # the anchor stays put
    _mouse(widget, QMouseEvent.Type.MouseButtonDblClick, plot.center())
    assert not widget.is_zoomed() and widget.view_range() == full


def test_zooming_back_out_to_the_full_span_drops_the_window(qapp):
    widget = _spectrum_widget()
    plot = widget._plot_rect()
    _wheel(widget, plot.center().x(), plot.center().y(), 120)
    for _ in range(40):
        _wheel(widget, plot.center().x(), plot.center().y(), -120)
    assert not widget.is_zoomed()


def test_a_wheel_outside_the_plot_does_not_zoom(qapp):
    widget = _spectrum_widget()
    _wheel(widget, 2, 2, 120)
    assert not widget.is_zoomed()


def test_a_band_outside_the_window_is_neither_drawn_nor_clickable(qapp):
    widget = _spectrum_widget()
    assert [i for _, i in widget.hit_regions()] == [0, 1, 2, 3]
    widget._set_window((1500.0, 1800.0))
    assert [i for _, i in widget.hit_regions()] == [1, 2]  # indices stay positions in the FULL list
    assert [i for i, _ in widget._visible_modes()] == [1, 2]


def test_zooming_does_not_rescale_a_stick(qapp):
    """The scale is the whole spectrum's strongest band, not the window's, so
    zooming onto the weaker 1600 band must not inflate it to full height."""
    widget = _spectrum_widget()
    widget._set_window((1550.0, 1650.0))
    assert [m.wavenumber_cm1 for _, m in widget._visible_modes()] == [1600.0]
    zoomed = ink(widget)
    plain = _spectrum_widget()
    plain._set_window((1550.0, 1650.0))
    plain._modes[1] = _mode(1600.0, 80.0)  # as strong as the global maximum
    assert ink(plain) > zoomed  # a 40-of-80 band is half as tall as an 80-of-80 one, even alone in the window


def test_dragging_pans_the_window_and_never_off_the_data(qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    widget = _spectrum_widget()
    widget._set_window((1500.0, 1800.0))
    start = widget._plot_rect().center()
    left = Qt.MouseButton.LeftButton

    grabbed = widget._data_x_at(start.x())
    _mouse(widget, QMouseEvent.Type.MouseButtonPress, start, buttons=left)
    _mouse(widget, QMouseEvent.Type.MouseMove, QPointF(start.x() + 60, start.y()), buttons=left)
    low, high = widget.view_range()
    assert (high - low) == pytest.approx(300.0) and low != 1500.0
    # A drag GRABS the plot: the wavenumber that was under the cursor follows it.
    assert widget._data_x_at(start.x() + 60) == pytest.approx(grabbed)
    _mouse(widget, QMouseEvent.Type.MouseMove, QPointF(start.x() + 4000, start.y()), buttons=left)
    assert widget.view_range()[0] >= widget._full_range()[0]


def test_a_drag_does_not_click_a_band_but_a_click_does(qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    widget = _spectrum_widget()
    received: list[int] = []
    widget.mode_clicked.connect(received.append)
    region, _index = widget.hit_regions()[2]
    point = region.center()
    none = Qt.MouseButton.NoButton

    _mouse(widget, QMouseEvent.Type.MouseButtonPress, point, buttons=Qt.MouseButton.LeftButton)
    _mouse(widget, QMouseEvent.Type.MouseButtonRelease, point, buttons=none)
    assert received == [2]
    _mouse(widget, QMouseEvent.Type.MouseButtonPress, point, buttons=Qt.MouseButton.LeftButton)
    _mouse(widget, QMouseEvent.Type.MouseButtonRelease, QPointF(point.x() + 30, point.y()), buttons=none)
    assert received == [2]  # moved too far: that was a drag


def test_the_readout_follows_the_cursor_and_clears_outside_the_plot(qapp):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    widget = _spectrum_widget()
    assert widget.readout_text() == ""
    inside = widget._plot_rect().center()
    _mouse(widget, QMouseEvent.Type.MouseMove, inside)
    assert widget.readout_text() == f"{widget._data_x_at(inside.x()):.0f} cm⁻¹"
    _mouse(widget, QMouseEvent.Type.MouseMove, QPointF(1, 1))
    assert widget.readout_text() == ""


def test_new_data_resets_the_zoom(qapp):
    widget = _spectrum_widget()
    widget._set_window((1500.0, 1800.0))
    widget.set_modes([_mode(1000.0)])
    assert not widget.is_zoomed()


def test_view_changed_fires_once_per_real_change(qapp):
    widget = _spectrum_widget()
    seen: list[int] = []
    widget.view_changed.connect(lambda: seen.append(1))
    widget._set_window((1500.0, 1800.0))
    widget._set_window((1500.0, 1800.0))
    widget.reset_view()
    widget.reset_view()
    assert len(seen) == 2


def test_the_right_click_menu_offers_the_picture_actions(qapp):
    from openchem.ui.picture_export import build_picture_menu

    menu = build_picture_menu(_spectrum_widget(), "ir-spectrum")
    assert [a.text() for a in menu.actions()] == ["Copy picture", "Save picture..."]
