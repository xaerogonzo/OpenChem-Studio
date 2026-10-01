"""Pure zoom/pan arithmetic for a data<->pixel plot, with no Qt types in
any signature.

Factored out of `NmrCorrelationPlotWidget`'s own wheel/drag handling,
which adopts these functions rather than keeping a duplicate copy, and
shared with `NmrSpectrumWidget`'s own new 1D zoom/pan -- the one axis
that needs BOTH directions `NmrCorrelationPlotWidget` never had to
support (ppm shift runs high-to-low by convention; shielding sigma runs
the other way, see `NmrSpectrumWidget.set_signals`).

A "window" is always `(low, high)` with `low <= high`, in DATA units --
never pixels, and never ordered by which end is drawn on the left (that
is `descending`'s job, and the caller's -- `plot_axis.to_widget_x` works
the same way and for the same reason: a helper that guessed the
direction from the data would silently mirror a plot that happens to
look fine either way).
"""

from __future__ import annotations


def zoomed_window(
    window: tuple[float, float],
    full_range: tuple[float, float],
    anchor: float,
    factor: float,
    min_fraction: float,
) -> tuple[float, float]:
    """`window` zoomed by `factor` (less than 1 zooms in) around `anchor`,
    the data value that must stay under the cursor.

    No `descending` parameter, unlike `panned_window` below -- and that
    is not an oversight. Keeping the anchor's FRACTIONAL position within
    the window constant is direction-symmetric: computing the new window
    from "distance from the high end" or from "distance from the low
    end" gives the identical `(low, high)` pair either way (the two
    fractions are complementary and the span-preserving construction
    satisfies both at once), so the result already keeps the anchor fixed
    on screen under EITHER drawing convention without needing to know
    which one is in play. Panning has no such symmetry -- see there.

    Clamped to `min_fraction` of `full_range` at the narrow end and to
    `full_range` itself at the wide end, so zooming in never collapses to
    a meaningless sliver and zooming out never exceeds the data.
    """
    low, high = window
    full_low, full_high = full_range
    full_span = full_high - full_low
    old_span = high - low
    if old_span <= 0 or full_span <= 0:
        return window
    min_span = full_span * min_fraction
    new_span = min(max(old_span * factor, min_span), full_span)
    fraction = (high - anchor) / old_span
    new_high = anchor + fraction * new_span
    new_low = new_high - new_span
    return new_low, new_high


def is_full_span(window: tuple[float, float], full_range: tuple[float, float]) -> bool:
    """True once a zoomed window has widened back out to the full data
    span -- the point at which "zoomed" and "not zoomed" are the same
    thing, and a caller should drop back to `None`/fit-to-data rather
    than keep tracking a window that no longer means anything."""
    low, high = window
    full_low, full_high = full_range
    return (high - low) >= (full_high - full_low)


def panned_window(
    window: tuple[float, float], pixel_delta: float, pixel_span: float, descending: bool = True
) -> tuple[float, float]:
    """`window` shifted so the data point under the OLD cursor position
    ends up under the NEW one -- a drag grabs the plot, not the axes.

    `pixel_delta` is the mouse's on-screen movement (positive = right or
    down); `pixel_span` is the plot's width or height in the same
    direction. `descending` flips the sign the way `zoomed_window` does:
    on a descending axis the window must shift the SAME way the cursor
    moved to keep a point fixed under it, and the opposite way on an
    ascending one.
    """
    low, high = window
    if pixel_span <= 0:
        return window
    delta = pixel_delta / pixel_span * (high - low)
    if not descending:
        delta = -delta
    return low + delta, high + delta


def drift(dx: float, dy: float) -> float:
    """Euclidean distance between a press and a release, in pixels -- the
    click-vs-drag test every pannable plot here uses: close together is a
    CLICK (resolve the nearest item), further apart is a PAN (the view
    already moved, and resolving a click there would surprise whoever
    just dragged the plot)."""
    return (dx * dx + dy * dy) ** 0.5
