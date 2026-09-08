"""The axis mechanics a stick plot needs, without the chemistry.

**EXTRACTED FOR A THIRD WIDGET, NOT TO REFACTOR THE FIRST TWO.**
`NmrSpectrumWidget` and `IrSpectrumWidget` are already near-duplicates and
the IR one says so outright -- "deliberately its sibling: the axis/peak/
hit-region structure below is that widget's". Shared essentially verbatim
between them: the margin, the hit half-width, the label height,
`_plot_rect`, `_to_widget_x` (identical), `_axis_range` and
`hit_regions`. What is NOT shared is genuinely chemistry -- multiplet
expansion, residual solvent peaks, imaginary-mode banners, silent-mode
stubs, the measured overlay.

So generalising either of them would drag `NMRSignal`, `VibrationalMode`
and `OverlaySeries` into one widget that then knows three chemistries,
and writing the geometry a third time for `StickChartWidget` would be the
fifth duplication this project has paid for (`is_stripped_residue`,
`filter_altlocs`, `is_symmetry_generated`, `normalise_element_symbols`).
Extracting the mechanics is the third option and the only one that costs
nothing.

**NMR AND IR ARE DELIBERATELY NOT MIGRATED ONTO THIS.** They work, they
are heavily commented, and their 36 tests are the net for a
behaviour-preserving change that belongs in its own commit rather than
riding along with a feature branch.

Qt-only (`QRectF`), no RDKit, no domain types -- `ui/` is the right home
and `tests/test_layering.py` is what says so.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF

#: Space around the plot for axis labels, in pixels. 50.0 in both existing
#: spectrum widgets; kept identical so a third plot reads as their sibling
#: rather than as a differently-proportioned stranger.
MARGIN = 50.0

#: Half-width of a stick's clickable region, in pixels. A stick is drawn
#: as a 1px line, which is not hittable with a mouse -- and two sticks can
#: legitimately share an x (two isotopologues in one nominal bin, two
#: diastereotopic protons at one shift), so the regions do overlap and the
#: first match wins, deterministically ordered by the caller's own order.
HIT_HALF_WIDTH = 6.0

#: Room reserved above the tallest stick for a value label, in pixels.
LABEL_HEIGHT = 14.0


def plot_rect(width: float, height: float, top_margin: float | None = None) -> QRectF:
    """The drawing area inside `width` x `height`.

    `top_margin` defaults to half `MARGIN` -- the NMR widget's proportions.
    A caller that needs a banner above the plot passes a full `MARGIN`, as
    the IR widget does.

    Both dimensions are floored at 1.0 rather than allowed to go negative:
    a widget narrower than its own margins is a transient state during
    layout, not an error, and a negative rectangle makes every derived
    coordinate nonsense.
    """
    top = MARGIN / 2 if top_margin is None else top_margin
    return QRectF(
        MARGIN,
        top,
        max(width - 1.5 * MARGIN, 1.0),
        max(height - MARGIN - top, 1.0),
    )


def padded_range(
    values, minimum_span: float = 1.0, fraction: float = 0.1
) -> tuple[float, float]:
    """`(low, high)` covering `values`, with room at each end.

    A single value -- or several at one x -- would otherwise be a
    zero-width axis, so a degenerate range is opened out to `minimum_span`
    FIRST and padded afterwards. `minimum_span` is the TOTAL width, not the
    half-width: the two existing widgets open a single peak by plus and
    minus 1.0 ppm and 50.0 cm-1 respectively, which is a span of 2.0 and
    100.0. They differ, which is why it is an argument and not a constant.

    An empty input gives `(0.0, 1.0)`: a caller with nothing to draw still
    needs an axis to draw nothing against.
    """
    numbers = [float(value) for value in values]
    if not numbers:
        return 0.0, 1.0
    low, high = min(numbers), max(numbers)
    if low == high:
        half = minimum_span / 2.0
        low, high = low - half, high + half
    padding = (high - low) * fraction
    return low - padding, high + padding


def to_widget_x(
    value: float, rect: QRectF, x_range: tuple[float, float], descending: bool
) -> float:
    """Where `value` falls across `rect`, in widget coordinates.

    **THE DIRECTION IS THE CALLER'S AND IS NEVER GUESSED HERE.** NMR and
    IR both run high-to-left by published convention; m/z runs low-to-left.
    A helper that picked by sniffing a units string would mirror one of
    them silently, and a mirrored spectrum does not look broken -- it looks
    like a different compound.

    A zero-width range maps to the middle rather than dividing by zero.
    """
    low, high = x_range
    if high == low:
        fraction = 0.5
    elif descending:
        fraction = (high - value) / (high - low)
    else:
        fraction = (value - low) / (high - low)
    return rect.left() + fraction * rect.width()


def hit_regions(
    xs, rect: QRectF, x_range: tuple[float, float], descending: bool,
    half_width: float = HIT_HALF_WIDTH,
) -> list[QRectF]:
    """One full-height clickable band per x, in the order given.

    Derived from geometry rather than recorded during `paintEvent`, so a
    click resolves correctly before the first paint -- and so it is
    testable without one, which is what both existing widgets' own
    hit-region tests rely on.
    """
    return [
        QRectF(
            to_widget_x(x, rect, x_range, descending) - half_width,
            rect.top(),
            2 * half_width,
            rect.height(),
        )
        for x in xs
    ]
