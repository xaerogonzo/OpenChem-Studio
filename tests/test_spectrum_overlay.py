"""Reconciling a measured IR spectrum with a computed one.

The reconciliation decisions are tested here without Qt; the fact that the
measured curve is actually DRAWN is tested at the bottom by rendering,
because a widget that computes a perfect overlay and paints nothing would
pass every other test in this file.
"""

from __future__ import annotations

import pytest

from openchem.chem.jcamp import JcampSpectrum
from openchem.chem.spectrum_overlay import (
    common_range,
    prepare_computed,
    prepare_measured,
)
from openchem.domain.scientific_result import VibrationalMode

import conftest


def _measured(y, units="TRANSMITTANCE", x=None):
    return JcampSpectrum(
        x=x or [1000.0 + 100 * i for i in range(len(y))], y=list(y), y_units=units
    )


@pytest.fixture
def widgets():
    """Every widget a test builds, destroyed deterministically after it.

    Copied from `tests/test_batch_panel.py`, whose docstring records why:
    left to Python's collector, an unparented widget from an earlier test
    dies at an arbitrary later moment, and a LATER test's `processEvents()`
    then drains a `DeferredDelete` posted against an object whose wrapper
    has gone -- an access violation, in a file that never called
    processEvents itself. Flushed PER WIDGET, never globally.
    """

    built = []
    yield built
    for widget in built:
        conftest.dispose(widget)


# --- Transmittance to absorbance, and only in that direction ------------


def test_transmittance_becomes_absorbance():
    """A = -log10(T) is the DEFINITION of absorbance, not a model -- it
    introduces no parameter, which is why the conversion runs this way and
    not the other. Turning km/mol into transmittance would need a path
    length and concentration belonging to a sample nobody prepared."""
    series = prepare_measured(_measured([1.0, 0.1, 1.0]))
    assert series.relative_absorbance == [0.0, 1.0, 0.0]


def test_percent_and_fraction_reconcile_to_the_same_spectrum():
    """THE SILENT FACTOR OF 100. JCAMP files write transmittance as 0-1 or
    as 0-100 and `##YUNITS` says "TRANSMITTANCE" for both. Guessing wrong
    offsets the result by exactly 2 absorbance units with every peak still
    in the right place, which reads as a baseline problem rather than a
    units problem."""
    percent = prepare_measured(_measured([100.0, 10.0, 100.0]))
    fraction = prepare_measured(_measured([1.0, 0.1, 1.0]))

    assert percent.was_percent is True
    assert fraction.was_percent is False
    assert percent.relative_absorbance == fraction.relative_absorbance


def test_absorbance_input_passes_through_unconverted():
    series = prepare_measured(_measured([0.0, 2.0, 1.0], units="ABSORBANCE"))
    assert series.relative_absorbance == [0.0, 1.0, 0.5]
    assert series.was_percent is False


def test_an_opaque_band_is_clamped_rather_than_made_infinite():
    """-log10(0) is infinite, and a detector reading zero through a strong
    band is ordinary. Left as an infinity it would flatten every other band
    to nothing during normalisation."""
    series = prepare_measured(_measured([100.0, 0.0], units="%T"))
    assert series.relative_absorbance == [0.0, 1.0]
    assert all(v == v for v in series.relative_absorbance)  # not NaN


def test_unlabelled_units_are_inferred_from_the_data_shape():
    """Transmittance sits near its maximum with dips; absorbance sits near
    zero with spikes. Compared against the midpoint, which needs no
    threshold on the values themselves."""
    assert prepare_measured(_measured([1.0, 1.0, 0.1, 1.0], units="")).was_percent is False
    looks_absorbing = prepare_measured(_measured([0.0, 0.0, 2.0, 0.0], units=""))
    assert looks_absorbing.relative_absorbance == [0.0, 0.0, 1.0, 0.0]


# --- Computed side ------------------------------------------------------


def test_imaginary_modes_are_dropped_from_an_overlay():
    """A negative wavenumber is not a band at a negative position; it is
    the finding that the geometry is a saddle point. Plotting one against a
    measurement is worse than plotting it alone, because the measurement
    lends it credibility."""
    peaks = prepare_computed(
        [
            VibrationalMode(wavenumber_cm1=-1436.0, ir_intensity_km_mol=None),
            VibrationalMode(wavenumber_cm1=1637.7, ir_intensity_km_mol=55.3),
        ]
    )
    assert [round(p.wavenumber_cm1, 1) for p in peaks] == [1637.7]


def test_computed_peaks_are_normalised_to_their_own_strongest():
    peaks = prepare_computed(
        [
            VibrationalMode(wavenumber_cm1=1637.7, ir_intensity_km_mol=55.3),
            VibrationalMode(wavenumber_cm1=3882.1, ir_intensity_km_mol=27.65),
        ]
    )
    assert [round(p.relative_intensity, 3) for p in peaks] == [1.0, 0.5]


def test_the_scale_factor_is_opt_in():
    """`benchmarks/ir/` fits 0.9666 for B3LYP harmonic frequencies. It is
    offered, never applied silently."""
    modes = [VibrationalMode(wavenumber_cm1=1000.0, ir_intensity_km_mol=1.0)]
    assert prepare_computed(modes)[0].wavenumber_cm1 == 1000.0
    assert round(prepare_computed(modes, 0.9666)[0].wavenumber_cm1, 1) == 966.6


def test_all_silent_bands_do_not_divide_by_zero():
    peaks = prepare_computed(
        [VibrationalMode(wavenumber_cm1=1000.0, ir_intensity_km_mol=0.0)]
    )
    assert peaks[0].relative_intensity == 0.0


# --- Shared axis --------------------------------------------------------


def test_the_shared_range_is_the_union_not_the_intersection():
    """A measurement typically starts at 400 cm-1 while a calculation
    reports modes below it. Clipping to the overlap would silently hide
    computed bands the measurement did not cover -- and a band with no
    counterpart is exactly what an overlay exists to reveal."""
    series = prepare_measured(_measured([1.0, 0.5], x=[400.0, 4000.0]))
    peaks = prepare_computed(
        [VibrationalMode(wavenumber_cm1=36.4, ir_intensity_km_mol=1.0)]
    )
    low, high = common_range(series, peaks)
    assert low < 36.4
    assert high > 4000.0


def test_the_range_survives_having_neither_side():
    assert common_range(None, []) == (0.0, 4000.0)


# --- It is actually drawn ------------------------------------------------


def test_the_measured_curve_reaches_the_painted_widget(qapp, widgets):
    """THE CHECK THAT SURVIVES A BLANKED PAINTER. Per CLAUDE.md, asserting
    "some pixel is non-transparent" passes for an empty widget, and "more
    ink than before" passes because changing the data moves the axis
    labels. So the AXES ARE HELD FIXED -- identical computed modes in both
    renders, so identical ticks and labels -- and only the measured overlay
    varies. Any difference in ink can then only be the curve.
    """
    from tests.conftest import ink

    from openchem.ui.widgets.ir_spectrum_widget import IrSpectrumWidget

    modes = [
        VibrationalMode(wavenumber_cm1=1000.0, ir_intensity_km_mol=10.0),
        VibrationalMode(wavenumber_cm1=3000.0, ir_intensity_km_mol=5.0),
    ]
    # Spans exactly the computed range, so the axis is identical either way.
    series = prepare_measured(
        _measured([1.0, 0.2, 1.0, 0.3, 1.0], x=[1000, 1500, 2000, 2500, 3000])
    )

    without = IrSpectrumWidget(modes=modes)
    with_overlay = IrSpectrumWidget(modes=modes)
    widgets.extend((without, with_overlay))
    without.resize(400, 240)
    with_overlay.resize(400, 240)
    with_overlay.set_measured(series)

    assert with_overlay.measured() is series
    assert ink(with_overlay) > ink(without)


def test_a_measurement_alone_still_renders(qapp, widgets):
    """A user may load a spectrum before running any calculation. The
    widget used to return early whenever there were no computed modes."""
    from tests.conftest import ink

    from openchem.ui.widgets.ir_spectrum_widget import IrSpectrumWidget

    widget = IrSpectrumWidget(modes=[])
    widgets.append(widget)
    widget.resize(400, 240)
    empty = ink(widget)

    widget.set_measured(
        prepare_measured(_measured([1.0, 0.1, 1.0], x=[1000, 2000, 3000]))
    )
    assert ink(widget) > empty
