"""The IR stick spectrum.

Every "was it drawn" assertion here holds the axis range FIXED and varies
only the content, because the two obvious weaker checks both survive a
blanked painter -- see CLAUDE.md. Each pair of spectra below therefore
shares its extreme wavenumbers (so the ticks and their labels are
identical) and its strongest intensity (so every surviving bar keeps the
same height), leaving exactly one thing different.
"""

from __future__ import annotations

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
