"""The generic curve renderer, and the pH widget that is now an adapter.

**THE MIGRATION IS ADDITIVE OR IT IS A REGRESSION**, so the pH half of
this file is a golden check rather than a coverage exercise: plot bounds,
axis labels, direction, legend names, curve positions and the hover
readout must all be what they were when `PhCurveWidget` did its own
drawing. `tests/test_ph_curve_widget.py` is the other half and passes
unchanged, which is the real proof.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QMouseEvent

from openchem.domain.report import LineChartAnnotation, LineSeries
from openchem.domain.scientific_result import PhCurveResult
from openchem.ui.widgets.line_chart_widget import LineChartWidget
from openchem.ui.widgets.ph_curve_widget import PhCurveWidget, annotation_for

# ONE spelling of the conftest import, never two. `tests/` has no
# `__init__.py`, so `import conftest` and `from tests.conftest import ...`
# load the SAME FILE under two module names and re-execute it -- the trap
# CLAUDE.md records reddening four tests the moment the widget census was
# switched on.
import conftest


def _dispose(widget) -> None:
    conftest.dispose(widget)


def ink(widget, **kwargs) -> int:
    return conftest.ink(widget, **kwargs)


def _line(series, **overrides) -> LineChartAnnotation:
    fields = {
        "series": tuple(LineSeries(points=points, name=name) for name, points in series),
        "x_label": "pH",
        "y_label": "Fraction",
        "x_descending": False,
    }
    fields.update(overrides)
    return LineChartAnnotation(**fields)


_RISING = (("HA", ((0.0, 0.0), (7.0, 0.5), (14.0, 1.0))),)


# --- the generic renderer ---------------------------------------------------


def test_a_declared_curve_is_drawn(qapp):
    widget = LineChartWidget(_line(_RISING))
    assert widget.is_drawing()
    assert ink(widget) > ink(LineChartWidget()), "a curve puts ink on the widget"
    _dispose(widget)


def test_a_malformed_annotation_is_refused_and_nothing_is_drawn(qapp):
    """REFUSED, never repaired.

    A scrambled series is exactly the case: the renderer must not quietly
    sort it, because that would turn a refusal into a repair and put a
    picture built from repaired nonsense on the screen.
    """
    scrambled = _line((("s", ((0.0, 1.0), (14.0, 0.0), (7.0, 0.5))),))
    widget = LineChartWidget(scrambled)
    assert not widget.is_drawing()
    assert widget.annotation() is None
    _dispose(widget)


def test_series_need_not_share_an_x_grid(qapp):
    """The case a shared-grid renderer could not draw at all.

    `PhCurveResult` samples one `ph_grid` for every series and that is
    still the common case; a computed curve against a measured one,
    sampled where the instrument sampled, is not.
    """
    overlay = _line((
        ("computed", ((0.0, 1.0), (1.0, 0.6), (2.0, 0.2))),
        ("measured", ((0.3, 0.9), (1.7, 0.3))),
    ))
    widget = LineChartWidget(overlay)
    assert widget.is_drawing()
    assert widget.readout_at(0.3) == {"computed": 1.0, "measured": 0.9}
    _dispose(widget)


def test_a_series_that_does_not_cover_x_is_omitted_from_the_readout(qapp):
    """Not given its nearest value, and not zero-filled.

    A microspecies curve stops where that species stops existing.
    Reporting its last value for a query past the end states a
    measurement nobody made -- the same reason a fabricated zero would.
    """
    partial = _line((
        ("full", ((0.0, 1.0), (5.0, 0.5), (10.0, 0.0))),
        ("short", ((0.0, 0.2), (2.0, 0.4))),
    ))
    widget = LineChartWidget(partial)
    assert widget.readout_at(1.0) == {"full": 1.0, "short": 0.2}
    assert widget.readout_at(9.0) == {"full": 0.0}, "the short curve does not reach here"
    _dispose(widget)


def test_a_pinned_axis_end_is_used_exactly_and_never_padded(qapp):
    """A bounded quantity gets an axis at its bounds.

    Found by rendering one and looking at it: a distribution that cannot
    leave 0-100 was drawn on an axis running -8% to 108%, which reads as
    headroom the quantity does not have. Only the pinned end is pinned --
    a curve bounded below and unbounded above still fits its top.
    """
    both = LineChartWidget(_line((("s", ((0.0, 10.0), (1.0, 90.0))),), y_min=0.0, y_max=100.0))
    assert both._value_range() == (0.0, 100.0)

    low_only = LineChartWidget(_line((("s", ((0.0, 10.0), (1.0, 90.0))),), y_min=0.0))
    low, high = low_only._value_range()
    assert low == 0.0, "the pinned end is exact"
    assert high > 90.0, "the free end still pads"

    neither = LineChartWidget(_line((("s", ((0.0, 10.0), (1.0, 90.0))),)))
    low, high = neither._value_range()
    assert low < 10.0 and high > 90.0
    for widget in (both, low_only, neither):
        _dispose(widget)


def test_x_descending_is_a_TRANSFORM_and_never_reorders_the_points(qapp):
    """A coordinate transform belongs in the transform.

    The producer's points are what a hit test, a readout and an export
    all see, so `x_descending` may only change WHERE a point is painted.
    Asserted both ways: the stored order is identical, and the painted x
    really does mirror.
    """
    rising = _line(_RISING)
    falling = _line(_RISING, x_descending=True)

    a, b = LineChartWidget(rising), LineChartWidget(falling)
    assert a.annotation().series[0].points == b.annotation().series[0].points

    rect = QRectF(0.0, 0.0, 100.0, 100.0)
    assert a._to_widget(0.0, 0.0, rect).x() == pytest.approx(0.0)
    assert b._to_widget(0.0, 0.0, rect).x() == pytest.approx(100.0)
    _dispose(a)
    _dispose(b)


def test_the_hover_snaps_to_a_SAMPLED_x_and_reaches_the_signal(qapp):
    widget = LineChartWidget(_line(_RISING))
    widget.resize(400, 300)
    seen: list[float] = []
    widget.x_hovered.connect(seen.append)

    event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(200.0, 150.0),
        QPointF(200.0, 150.0),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.mouseMoveEvent(event)
    assert seen, "moving over the plot reports an x"
    assert seen[0] in (0.0, 7.0, 14.0), "and it is a SAMPLED x, not an arbitrary one"
    _dispose(widget)


# --- the pH adapter ----------------------------------------------------------


def _curve(**overrides) -> PhCurveResult:
    fields = {
        "curve_id": "probe",
        "name": "Probe",
        "method": "probe",
        "molecule_uuid": "m1",
        "ph_values": [0.0, 2.0, 4.0, 6.0],
        "series": {"HA": [1.0, 0.8, 0.4, 0.1], "A-": [0.0, 0.2, 0.6, 0.9]},
        "x_label": "pH",
        "y_label": "Fraction",
    }
    fields.update(overrides)
    return PhCurveResult(**fields)


def test_the_adapter_pairs_the_grid_with_each_series_and_changes_nothing_else():
    """THE LIKELIEST PLACE FOR A DOUBLE TRANSFORM TO HIDE.

    Sort here and the widget sorts again; renormalise here and the axis
    range is computed from different numbers than the curve is drawn
    from. The fixture's values are deliberately out of order in y so a
    sort could not pass as the identity.
    """
    result = _curve(ph_values=[0.0, 2.0, 4.0], series={"only": [0.9, 0.1, 0.5]})
    annotation = annotation_for(result)
    assert annotation.series[0].points == ((0.0, 0.9), (2.0, 0.1), (4.0, 0.5))
    assert annotation.series[0].name == "only"
    assert annotation.x_label == "pH"
    assert annotation.x_descending is False, "pH increases left to right"


def test_the_adapter_truncates_with_zip_rather_than_raising():
    """A curve can legitimately stop where a microspecies stops existing."""
    annotation = annotation_for(_curve(series={"partial": [1.0, 2.0]}))
    assert annotation.series[0].points == ((0.0, 1.0), (2.0, 2.0))


def test_an_empty_result_declares_no_annotation():
    assert annotation_for(None) is None
    assert annotation_for(_curve(ph_values=[], series={})) is None


def test_the_ph_widget_keeps_its_own_signal_and_its_result_accessor(qapp):
    """The inspector's API is unchanged or the migration is a regression."""
    widget = PhCurveWidget(_curve())
    seen: list[float] = []
    widget.ph_hovered.connect(seen.append)
    widget.x_hovered.emit(4.0)
    assert seen == [4.0], "ph_hovered still fires, forwarded from the generic signal"
    assert widget.result() is not None
    assert widget.readout_at(4.0) == {"HA": 0.4, "A-": 0.6}
    _dispose(widget)


def test_no_ph_concept_reached_the_generic_annotation():
    """No show_pKa, no buffer highlight, no chemistry-specific readout.

    The one thing that moved is `y_min`/`y_max`, which is an AXIS
    declaration -- a quantity with real bounds gets an axis at those
    bounds, and that is as true of a quantum yield as of a microspecies
    fraction.
    """
    fields = set(LineChartAnnotation.__dataclass_fields__)
    assert not {f for f in fields if "ph" in f.lower() or "pka" in f.lower()}
    assert {"y_min", "y_max"} <= fields
