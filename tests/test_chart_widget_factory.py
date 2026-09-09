"""Which widget draws which kind, and what a kind with no widget looks like.

The dispatch is by TYPE and the two failure modes are DIFFERENT, which is
what this file holds:

    malformed annotation      the widget refuses it, draws nothing, logs.
                              The producer declared something invalid.
    valid, no widget for it   a visible diagnostic. The producer declared
                              something fine that this build cannot draw.

Silence for the second is the defect: an empty section is
indistinguishable from `charts == ()`, which is the producer saying it
has no picture. Opposite facts, same rectangle -- the `n/a is not 0` rule
that the Properties panel already applies between FAILED and INAPPLICABLE.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from openchem.domain.report import (
    LineChartAnnotation,
    LineSeries,
    Stick,
    StickChartAnnotation,
)
from openchem.ui.widgets.chart_widgets import (
    CHART_WIDGET_TYPES,
    UNRENDERABLE_CHART,
    chart_widget_for,
)
from openchem.ui.widgets.line_chart_widget import LineChartWidget
from openchem.ui.widgets.stick_chart_widget import StickChartWidget

import conftest

_FACTORY_SOURCE = (
    Path(__file__).resolve().parent.parent
    / "src" / "openchem" / "ui" / "widgets" / "chart_widgets.py"
)


@dataclass(frozen=True)
class _UnknownKind:
    """A chart kind this build has never heard of.

    A local type rather than a real future annotation, so this test keeps
    meaning the same thing on the day a third kind ships: it is about the
    FALLBACK, not about any particular kind being missing.
    """

    title: str = ""


def _sticks() -> StickChartAnnotation:
    return StickChartAnnotation(
        sticks=(Stick(1.0, 1.0), Stick(2.0, 0.5)),
        x_label="m/z",
        y_label="Relative abundance",
        x_descending=False,
    )


def _curve() -> LineChartAnnotation:
    return LineChartAnnotation(
        series=(LineSeries(points=((0.0, 1.0), (1.0, 0.5)), name="HA"),),
        x_label="pH",
        y_label="Fraction",
        x_descending=False,
    )


def test_each_kind_reaches_its_own_widget(qapp):
    stick = chart_widget_for(_sticks())
    line = chart_widget_for(_curve())
    assert isinstance(stick, StickChartWidget)
    assert isinstance(line, LineChartWidget)
    conftest.dispose(stick)
    conftest.dispose(line)


def test_a_kind_with_no_widget_gets_a_VISIBLE_diagnostic(qapp):
    """Not an empty box, which is what `charts == ()` already looks like."""
    widget = chart_widget_for(_UnknownKind())
    assert widget is not None, "the factory always returns something to show"
    assert UNRENDERABLE_CHART in widget.text()
    assert type(widget) in CHART_WIDGET_TYPES, (
        "the diagnostic is a chart widget too, or a view reading the charts "
        "off the screen reports none while one is plainly there"
    )
    conftest.dispose(widget)


def test_the_two_failure_modes_are_told_apart(qapp):
    """A malformed annotation and an undrawable kind are different facts.

    The first is a producer bug; the second is this build's limit. A
    reader seeing one rectangle for both learns neither.
    """
    malformed = StickChartAnnotation(
        sticks=(), x_label="m/z", y_label="I", x_descending=False
    )
    refused = chart_widget_for(malformed)
    assert isinstance(refused, StickChartWidget)
    assert not refused.is_drawing(), "declared and invalid: the widget refuses it"

    unknown = chart_widget_for(_UnknownKind())
    assert not isinstance(unknown, (StickChartWidget, LineChartWidget))
    conftest.dispose(refused)
    conftest.dispose(unknown)


def test_the_dispatch_is_by_TYPE_and_not_by_a_string_kind():
    """The `isinstance`-first design is a strength of this channel.

    A `chart.kind == "stick"` ladder would be a second, weaker vocabulary
    beside the types the domain already has -- and a typo in it fails
    OPEN, silently taking the fallback, which is the one thing this
    channel is built not to do. Asserted on the SOURCE because a string
    ladder that happens to be correct today behaves identically.
    """
    tree = ast.parse(_FACTORY_SOURCE.read_text(encoding="utf-8"))
    factory = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "chart_widget_for"
    )
    tests = [node.test for node in ast.walk(factory) if isinstance(node, ast.If)]
    assert tests, "the factory dispatches on something"
    for test in tests:
        assert isinstance(test, ast.Call) and getattr(test.func, "id", "") == "isinstance", (
            f"dispatch by isinstance, not {ast.dump(test)[:80]}"
        )


def test_every_type_the_factory_returns_is_declared(qapp):
    """`CHART_WIDGET_TYPES` and the factory cannot drift.

    `FactView.chart_widgets` reads that tuple to find the charts on
    screen. It filtered on `StickChartWidget` alone before this existed,
    which was right while that was the only kind and became a silent
    undercount the moment a second arrived -- a guard reading it would
    have reported "no chart" for a chart plainly on screen.
    """
    produced = [
        chart_widget_for(_sticks()),
        chart_widget_for(_curve()),
        chart_widget_for(_UnknownKind()),
    ]
    for widget in produced:
        assert type(widget) in CHART_WIDGET_TYPES, type(widget).__name__
        conftest.dispose(widget)
