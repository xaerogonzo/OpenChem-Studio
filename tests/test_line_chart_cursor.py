"""Reading a curve at a pH: the nearest SAMPLE, never an interpolation.

The request was to stop somewhere on the LogD curve and read the numbers
there. A hover readout already existed and vanished when the pointer left;
a click now keeps it. What it reads is pinned here, because the tempting
alternative -- interpolating between samples -- produces a number the
calculation never made.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent

from openchem.domain.report import LineChartAnnotation, LineSeries, chart_in_rendering
from openchem.ui.widgets.line_chart_widget import LineChartWidget, nearest_sampled_x

import conftest

GRID = [0.0, 0.25, 0.5, 7.25, 7.4, 7.5, 14.0]


def test_exactly_on_a_sample_reads_that_sample():
    assert nearest_sampled_x(GRID, 7.4) == 7.4


def test_halfway_between_two_samples_reads_the_lower():
    assert nearest_sampled_x(GRID, 0.125) == 0.0
    assert nearest_sampled_x(GRID, 7.45) == pytest.approx(7.4)


def test_below_the_range_clamps_to_the_first_sample():
    assert nearest_sampled_x(GRID, -3.0) == 0.0


def test_above_the_range_clamps_to_the_last_sample():
    assert nearest_sampled_x(GRID, 99.0) == 14.0


def _chart(y_units: str = "") -> LineChartAnnotation:
    return LineChartAnnotation(
        series=(LineSeries(points=tuple((x, x * 2.0) for x in GRID), name="logD"),),
        x_label="pH", y_label="logD", y_units=y_units, x_descending=False,
    )


def test_a_click_keeps_the_reading_and_a_second_click_releases_it(qapp):
    widget = LineChartWidget(_chart())
    widget.resize(400, 300)
    widget.show()
    try:
        rect = widget._plot_rect()
        position = QPointF(rect.left() + rect.width() * (7.4 / 14.0), rect.center().y())
        press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress, position, position,
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        )
        widget.mousePressEvent(press)
        assert widget.pinned_x() == 7.4
        widget.leaveEvent(None)
        assert widget.pinned_x() == 7.4, "leaving must not drop a kept reading"
        widget.mousePressEvent(press)
        assert widget.pinned_x() is None
    finally:
        conftest.dispose(widget)


def test_the_readout_names_the_units_of_the_rendering_on_screen(qapp):
    """Resolves through the chart AS SHOWN -- a Solubility reading after a
    switch to mg/mL must say mg/mL, with the same x."""
    from rdkit import Chem

    from openchem.chem.solubility import MG_PER_ML, UNIT_KEYS, compute_solubility

    report = compute_solubility(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"), "u", {"pka_values": "3.49"})
    base = report.charts[0]
    widget = LineChartWidget(base)
    try:
        before = widget.readout_lines(7.0)
        widget.set_annotation(chart_in_rendering(base, UNIT_KEYS[MG_PER_ML]))
        after = widget.readout_lines(7.0)
        assert before[0] == after[0], "the x of the reading moved with the unit"
        assert before[1] != after[1]
        assert "mg/mL" in after[1] or "mg/mL" in widget.annotation().y_label
    finally:
        conftest.dispose(widget)


def test_the_readout_carries_declared_units(qapp):
    widget = LineChartWidget(_chart(y_units="log mol/L"))
    try:
        assert widget.readout_lines(7.4)[1] == "logD: 14.8 log mol/L"
    finally:
        conftest.dispose(widget)
