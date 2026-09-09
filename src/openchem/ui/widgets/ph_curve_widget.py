"""A property against pH, drawn by the generic line renderer.

**THIS WAS THE RENDERER AND IS NOW AN ADAPTER**, and the split is the
point. It did multi-series drawing, a legend, gridlines, a zero line and a
hover readout, all of which are true of any curve on any axes -- and its
only coupling to pH was that it took a `PhCurveResult`. That drawing now
lives in `LineChartWidget`, where every calculator that declares a
`LineChartAnnotation` gets it, and what is left here is the conversion.

Its public surface is UNCHANGED: `set_result`, `result`, `ph_hovered` and
`readout_at` all behave as before, so `CalculatorInspectorDialog` is
untouched. The migration is additive or it is a regression.

**NO pH CONCEPT REACHED THE GENERIC ANNOTATION.** No `show_pKa`, no
buffer-region highlight, no chemistry-specific readout. The one thing
that moved is `y_min`/`y_max`, which is an AXIS declaration rather than a
chemistry one -- a quantity with real bounds gets an axis at those
bounds, and that is as true of a quantum yield as of a microspecies
fraction.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from openchem.domain.report import LineChartAnnotation, LineSeries
from openchem.domain.scientific_result import PhCurveResult
from openchem.ui.widgets.line_chart_widget import SERIES_COLORS, LineChartWidget

# Kept as a module attribute under its original private name because it
# was one, and something may import it. `SERIES_COLORS` is the live one.
_SERIES_COLORS = SERIES_COLORS


def annotation_for(result: PhCurveResult | None) -> LineChartAnnotation | None:
    """A `PhCurveResult` as a declared chart, or None if it has no data.

    **PAIRS EACH SERIES WITH THE GRID ONCE, and `zip` is load-bearing.**
    A series shorter than `ph_values` draws the part it has rather than
    raising, which matters because a curve can legitimately be truncated
    where a microspecies stops existing -- the behaviour the widget's own
    `_draw_series` had and the reason it used `zip` rather than indexing.

    **NOTHING IS SORTED, RESCALED OR RENAMED ON THE WAY THROUGH.** The
    adapter is the likeliest place for a double transform to hide: sort
    here and the widget sorts again, or renormalise here and the axis
    range is computed from different numbers than the curve is drawn
    from. It pairs and it stops.
    """
    if result is None or not result.ph_values or not result.series:
        return None
    return LineChartAnnotation(
        series=tuple(
            LineSeries(points=tuple(zip(result.ph_values, values)), name=name)
            for name, values in result.series.items()
        ),
        x_label=result.x_label,
        y_label=result.y_label,
        # pH increases left to right. NMR's descending convention is
        # specific to chemical shift and would be actively wrong for a
        # titration curve.
        x_descending=False,
        y_min=result.y_min,
        y_max=result.y_max,
    )


class PhCurveWidget(LineChartWidget):
    """A multi-series line chart of a property against pH."""

    #: Nearest sampled pH under the cursor. Kept beside the base class's
    #: `x_hovered` rather than replacing it: a consumer that knows it is
    #: looking at a titration wants the pH-shaped name, and one that does
    #: not should still be able to connect the generic signal.
    ph_hovered = Signal(float)

    def __init__(
        self, result: PhCurveResult | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(None, parent)
        self._result: PhCurveResult | None = None
        self.x_hovered.connect(self.ph_hovered)
        if result is not None:
            self.set_result(result)

    def set_result(self, result: PhCurveResult | None) -> None:
        self._result = result
        self.set_annotation(annotation_for(result))

    def result(self) -> PhCurveResult | None:
        return self._result
