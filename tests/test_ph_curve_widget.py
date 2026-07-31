from __future__ import annotations

import pytest

from openchem.domain.common import CacheState
from openchem.domain.scientific_result import PhCurveResult
from openchem.ui.widgets.ph_curve_widget import PhCurveWidget


def _curve(**overrides) -> PhCurveResult:
    defaults = dict(
        curve_id="logd_vs_ph",
        name="LogD vs pH",
        method="henderson_hasselbalch",
        molecule_uuid="mol-1",
        ph_values=[0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0],
        series={"logD": [3.1, 3.1, 2.7, 1.4, -0.6, -2.1, -2.6, -2.6]},
        y_label="logD",
        cache_state=CacheState.COMPLETED,
    )
    defaults.update(overrides)
    return PhCurveResult(**defaults)


def test_widget_holds_the_result_it_was_given(qapp):
    widget = PhCurveWidget(_curve())
    assert widget.result().curve_id == "logd_vs_ph"


def test_empty_result_does_not_crash_on_paint(qapp):
    """A calculator can legitimately produce no curve (no ionizable group,
    or pkasolver not configured) -- that must render as 'No data', not
    raise inside paintEvent where the traceback would be swallowed by Qt."""
    widget = PhCurveWidget(PhCurveResult(curve_id="x", name="X", method="m", molecule_uuid="mol-1"))
    widget.resize(400, 300)
    widget.grab()  # forces a real paintEvent


def test_no_result_at_all_does_not_crash_on_paint(qapp):
    widget = PhCurveWidget()
    widget.resize(400, 300)
    widget.grab()


def test_paints_a_real_multi_series_curve(qapp):
    widget = PhCurveWidget(
        _curve(
            series={
                "neutral": [100.0, 90.0, 50.0, 10.0, 1.0, 0.0, 0.0, 0.0],
                "anion": [0.0, 10.0, 50.0, 90.0, 99.0, 100.0, 100.0, 100.0],
            }
        )
    )
    widget.resize(500, 360)
    widget.grab()


def test_more_series_than_palette_colors_still_paints(qapp):
    """A pKa microspecies distribution can legitimately have a dozen
    curves; the palette has seven and must cycle rather than IndexError."""
    widget = PhCurveWidget(
        _curve(series={f"species{i}": [float(i)] * 8 for i in range(12)})
    )
    widget.resize(500, 360)
    widget.grab()


def test_readout_returns_every_series_at_the_nearest_sampled_ph(qapp):
    widget = PhCurveWidget(
        _curve(series={"a": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0], "b": [7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0, 0.0]})
    )

    # 7.4 is nearest the pH=8.0 sample (index 4).
    assert widget.readout_at(7.4) == {"a": 4.0, "b": 3.0}


def test_readout_on_an_empty_widget_is_empty_not_an_error(qapp):
    assert PhCurveWidget().readout_at(7.4) == {}


def test_a_series_shorter_than_ph_values_draws_what_it_has(qapp):
    """A microspecies curve can stop partway through the pH range. zip()
    truncates rather than raising, so the partial curve still renders."""
    widget = PhCurveWidget(_curve(series={"partial": [1.0, 2.0, 3.0]}))
    widget.resize(400, 300)
    widget.grab()

    assert widget.readout_at(0.0) == {"partial": 1.0}
    # Index 7 is past the end of the series -- omitted, not zero-filled,
    # since a fabricated zero would read as a real measured value.
    assert widget.readout_at(14.0) == {}


def test_flat_series_does_not_collapse_the_plot(qapp):
    """A constant curve (a molecule with no ionizable group) would give a
    zero-height value range and divide by zero without the padding."""
    widget = PhCurveWidget(_curve(series={"logD": [2.5] * 8}))
    widget.resize(400, 300)
    widget.grab()


def test_hover_emits_the_nearest_sampled_ph(qapp):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    widget = PhCurveWidget(_curve())
    widget.resize(500, 360)
    widget.show()
    received: list[float] = []
    widget.ph_hovered.connect(received.append)

    rect = widget._plot_rect()
    event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(rect.left() + rect.width() / 2.0, rect.center().y()),
        QPointF(0, 0),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.mouseMoveEvent(event)

    assert received, "hovering inside the plot must emit a pH"
    assert received[-1] == pytest.approx(7.0, abs=1.5)
    widget.close()


def test_declared_axis_bounds_are_used_exactly(qapp):
    """A microspecies distribution is 0-100% by construction. Without
    pinned bounds the generic 8% padding drew the axis from -8% to 108% --
    physically impossible, and caught by rendering one and looking at it."""
    widget = PhCurveWidget(_curve(series={"pct": [0.0, 20.0, 50.0, 80.0, 100.0, 100.0, 100.0, 100.0]},
                                  y_min=0.0, y_max=100.0))
    assert widget._value_range() == (0.0, 100.0)


def test_one_pinned_bound_still_pads_the_other(qapp):
    """A percentage that never reaches 100 still wants a hard floor at 0
    but headroom above the highest curve."""
    widget = PhCurveWidget(_curve(series={"pct": [0.0, 10.0, 20.0, 30.0, 40.0, 40.0, 40.0, 40.0]}, y_min=0.0))
    low, high = widget._value_range()
    assert low == 0.0
    assert high > 40.0


def test_unpinned_bounds_keep_padding(qapp):
    """logD is unbounded, so it must keep the padding that stops curves
    being drawn on the frame."""
    widget = PhCurveWidget(_curve(series={"logD": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]}))
    low, high = widget._value_range()
    assert low < 0.0
    assert high > 7.0
