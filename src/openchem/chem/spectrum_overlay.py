"""Putting a measured IR spectrum and a computed one on the same axes.

WHY THIS IS NOT JUST PLOTTING TWO LINES. The two sides are different
physical quantities measured in different ways, and three things have to be
reconciled before they can share a plot. Each is a decision with a wrong
answer available, so they live here -- testable, no Qt -- rather than being
made inline in a paint method.

1. TRANSMITTANCE -> ABSORBANCE, AND IN THAT DIRECTION ONLY.

`IrSpectrumWidget` already documents why the computed spectrum cannot be
turned into transmittance: ORCA gives an integrated intensity in km/mol,
and Beer-Lambert needs a path length and a concentration belonging to a
sample nobody prepared. Inventing them would put a calibrated-looking axis
on made-up numbers.

Going the other way has no such problem. A = -log10(T) is the DEFINITION of
absorbance, not a model -- it introduces no parameter, because the sample
that produced T is the sample. So the measurement is converted to match the
prediction, which is the only direction that costs nothing.

2. PERCENT VERSUS FRACTION, WHICH IS A SILENT FACTOR OF 100.

JCAMP files write transmittance either as 0-1 or as 0-100, and `##YUNITS`
frequently says only "TRANSMITTANCE" for both. Guessing wrong does not
produce an error, it produces a spectrum offset by exactly 2 absorbance
units with its peaks in the right places -- which looks like a baseline
problem rather than a units problem. The scale is therefore inferred from
the DATA (a maximum above 1.5 can only be percent) rather than from the
header, and the inference is reported on the result so a caller can say
which was used.

3. STICKS VERSUS A CURVE, AND WHY NO LINESHAPE IS INVENTED.

A harmonic calculation gives discrete lines; a measurement gives a
continuous curve whose widths come from rotational structure, collisions
and instrument resolution. Broadening the sticks with a Lorentzian would
make the pictures superficially more alike and would encode a linewidth
this calculation has no basis to choose -- and the eye reads band WIDTH as
information. So the measurement is drawn as the curve it is, the prediction
as the sticks it is, and the comparison the plot supports is of POSITION
and RELATIVE HEIGHT, which are the two things both sides actually have.

4. THE Y AXES CANNOT BE SHARED, so both are normalised to their own maximum
and the axis is labelled relative. km/mol and absorbance are not
convertible without the sample parameters above. Normalising is honest
provided nothing then claims the heights are comparable in absolute terms;
`relative` in the field names is doing that work.

Harmonic frequencies also run systematically high -- `benchmarks/ir/`
measures 64.7 cm-1 mean error unscaled, 27.6 after a fitted 0.9666 factor.
`scale_factor` is offered so a caller can apply that when overlaying, and
defaults to 1.0 so nothing is scaled behind anyone's back.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from openchem.chem.jcamp import JcampSpectrum
from openchem.domain.scientific_result import VibrationalMode

#: Above this, a transmittance column can only be percent. Chosen well
#: clear of 1.0 because a noisy baseline genuinely reaches slightly above
#: unity, and treating 1.02 as percent would divide a real spectrum by 100.
_PERCENT_THRESHOLD = 1.5

#: Absorbance assigned where transmittance is zero or negative. -log10(0)
#: is infinite, and a detector reading zero through an opaque band is an
#: ordinary occurrence rather than an error, so it is clamped to a finite
#: "fully absorbing" value instead of propagating an infinity into the
#: normalisation and flattening every other band to nothing.
_MAX_ABSORBANCE = 6.0


@dataclass(frozen=True)
class OverlaySeries:
    """A measured spectrum prepared to sit under a computed one."""

    wavenumbers: list[float]
    #: Absorbance, normalised so the strongest band is 1.0.
    relative_absorbance: list[float]
    #: True when the source was read as percent transmittance.
    was_percent: bool
    #: What the source y-axis was, before conversion.
    source_units: str
    title: str = ""

    @property
    def point_count(self) -> int:
        return len(self.wavenumbers)


@dataclass(frozen=True)
class OverlayPeak:
    """One computed band, on the same relative scale as the measurement."""

    wavenumber_cm1: float
    relative_intensity: float
    character: str = ""


def prepare_measured(
    spectrum: JcampSpectrum, scale_factor: float = 1.0
) -> OverlaySeries:
    """A JCAMP spectrum converted to normalised absorbance.

    `scale_factor` multiplies the WAVENUMBERS and is here for symmetry with
    `prepare_computed`; it defaults to 1.0 and a measurement should almost
    never be scaled -- it is the thing being compared against.
    """
    units = (spectrum.y_units or "").strip().upper()
    is_transmittance = "TRANS" in units or units in ("T", "%T")
    is_absorbance = "ABSORB" in units or units == "A"

    values = list(spectrum.y)
    was_percent = False

    if is_transmittance or (not is_absorbance and _looks_like_transmittance(values)):
        was_percent = max(values, default=0.0) > _PERCENT_THRESHOLD
        divisor = 100.0 if was_percent else 1.0
        absorbance = [_absorbance_from_transmittance(v / divisor) for v in values]
    else:
        absorbance = values

    peak = max(absorbance, default=0.0)
    # `+ 0.0` normalises the sign: -log10(1.0) is -0.0, which compares
    # equal to zero but prints as "-0.0" in a tooltip or a table cell.
    relative = (
        [v / peak + 0.0 for v in absorbance] if peak > 0 else [0.0] * len(absorbance)
    )

    return OverlaySeries(
        wavenumbers=[x * scale_factor for x in spectrum.x],
        relative_absorbance=relative,
        was_percent=was_percent,
        source_units=spectrum.y_units,
        title=spectrum.title,
    )


def prepare_computed(
    modes: list[VibrationalMode] | tuple[VibrationalMode, ...],
    scale_factor: float = 1.0,
) -> list[OverlayPeak]:
    """Computed modes as normalised sticks.

    Imaginary modes are dropped, for the reason `IrSpectrumWidget` gives:
    a negative wavenumber is not a band at a negative position, it is the
    finding that the geometry is a saddle point. Plotting one against a
    measurement would be worse than plotting it alone, because the
    measurement lends it credibility.

    `scale_factor` is where `benchmarks/ir/`'s fitted 0.9666 belongs when a
    caller wants it. Default 1.0 -- nothing is scaled silently.
    """
    real = [mode for mode in modes if not mode.is_imaginary]
    intensities = [float(mode.ir_intensity_km_mol or 0.0) for mode in real]
    peak = max(intensities, default=0.0)
    return [
        OverlayPeak(
            wavenumber_cm1=mode.wavenumber_cm1 * scale_factor,
            relative_intensity=(intensity / peak) if peak > 0 else 0.0,
            character=mode.character,
        )
        for mode, intensity in zip(real, intensities)
    ]


def common_range(
    series: OverlaySeries | None, peaks: list[OverlayPeak]
) -> tuple[float, float]:
    """The wavenumber span that shows both, or a sane default for neither.

    The UNION rather than the intersection: a measurement typically starts
    at 400 cm-1 while a calculation reports modes below that, and clipping
    to the overlap would silently hide computed bands the measurement
    simply did not cover. A band with no counterpart is information.
    """
    values: list[float] = []
    if series and series.wavenumbers:
        values.extend((min(series.wavenumbers), max(series.wavenumbers)))
    if peaks:
        numbers = [peak.wavenumber_cm1 for peak in peaks]
        values.extend((min(numbers), max(numbers)))
    if not values:
        return (0.0, 4000.0)
    low, high = min(values), max(values)
    if low == high:
        return (low - 50.0, high + 50.0)
    padding = (high - low) * 0.05
    return (low - padding, high + padding)


def _looks_like_transmittance(values: list[float]) -> bool:
    """Whether an unlabelled y-column is transmittance rather than absorbance.

    Used only when `##YUNITS` says neither. Transmittance is bounded and
    sits near its maximum for most of a spectrum (a baseline of clear
    sample with absorption dips); absorbance sits near zero and spikes up.
    Comparing the mean to the midpoint separates them without needing a
    threshold on the values themselves.
    """
    if not values:
        return False
    low, high = min(values), max(values)
    if high <= low:
        return False
    mean = sum(values) / len(values)
    return mean > (low + high) / 2.0


def _absorbance_from_transmittance(transmittance: float) -> float:
    if transmittance <= 0.0:
        return _MAX_ABSORBANCE
    return min(-math.log10(transmittance), _MAX_ABSORBANCE)
