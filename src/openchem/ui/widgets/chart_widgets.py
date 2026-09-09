"""Which widget draws which chart kind, and what happens when none does.

One function, dispatching by TYPE. `ChartAnnotation` is a union and every
consumer of it dispatches by `isinstance` from the first line, so a third
kind costs a `|` on the union and an entry here. A `chart.kind == "stick"`
string ladder would be a second, weaker vocabulary beside the types the
domain already has -- and a typo in it fails open, which is the one thing
this channel is built not to do.

**AN UNSUPPORTED KIND GETS A VISIBLE DIAGNOSTIC, NOT SILENCE.** Refusing
with a log line alone leaves an empty section, and an empty section is
indistinguishable from `charts == ()` -- the producer saying it has no
picture. Those are opposite facts about the producer, and telling them
apart is the `n/a is not 0` rule that the Properties panel already
applies between FAILED and INAPPLICABLE.

The two failures are DIFFERENT and are reported differently:

    malformed annotation      the widget's own `set_annotation` refuses
                              it, draws nothing and logs. The producer
                              declared something structurally invalid.
    valid, no widget for it   this module says so on screen. The
                              producer declared something fine that this
                              build cannot draw.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QLabel, QWidget

from openchem.domain.report import (
    DepictionAnnotation,
    LineChartAnnotation,
    StickChartAnnotation,
)
from openchem.ui.widgets.depiction_widget import DepictionWidget
from openchem.ui.widgets.line_chart_widget import LineChartWidget
from openchem.ui.widgets.stick_chart_widget import StickChartWidget

logger = logging.getLogger("openchem.ui")

#: What the diagnostic says. A named constant so a test can assert the
#: state without pinning the sentence, and so the words are in one place
#: rather than at a call site.
UNRENDERABLE_CHART = (
    "This result declared a chart of a kind this view cannot draw. "
    "The facts below are unaffected."
)


class _UnrenderableChartLabel(QLabel):
    """The visible half of "declared, and this build cannot draw it".

    Its own type rather than a bare `QLabel`, so a consumer can tell this
    state apart from a chart without matching on the sentence -- and so
    `CHART_WIDGET_TYPES` can name it.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(UNRENDERABLE_CHART, parent)
        self.setWordWrap(True)


#: Every widget type `chart_widget_for` can hand back, INCLUDING the
#: diagnostic label. Declared beside the factory so a consumer reading the
#: charts off a rendered view cannot disagree with it about what a chart
#: widget is -- `FactView.chart_widgets` filtered on `StickChartWidget`
#: alone, which was right while that was the only kind and became a silent
#: undercount the moment a second arrived.
CHART_WIDGET_TYPES: tuple[type[QWidget], ...] = (
    StickChartWidget,
    LineChartWidget,
    DepictionWidget,
    _UnrenderableChartLabel,
)


def chart_widget_for(
    annotation, parent: QWidget | None = None, molblock: str = ""
) -> QWidget:
    """The widget that draws `annotation`, or a label saying none does.

    Always returns something, so a caller never has to decide what an
    absent widget means -- which is how "no chart declared" and "chart
    declared and unrenderable" became the same empty box.

    `molblock` is the RENDER CONTEXT, and only a depiction uses it. A
    chart on axes needs no structure; a picture drawn ON one does, and
    the annotation deliberately carries no geometry. A caller that cannot
    resolve the molecule passes nothing and the depiction says so rather
    than drawing an empty frame.
    """
    if isinstance(annotation, DepictionAnnotation):
        return DepictionWidget(annotation, parent, molblock=molblock)
    if isinstance(annotation, StickChartAnnotation):
        # `show_title=False`: the section header above IS the chart's
        # title, and painting it again put the same words twice on screen
        # with the second copy landing on the tallest stick's label.
        return StickChartWidget(annotation, parent, show_title=False)
    if isinstance(annotation, LineChartAnnotation):
        return LineChartWidget(annotation, parent)

    logger.warning("No widget for chart annotation of type %s", type(annotation).__name__)
    return _UnrenderableChartLabel(parent)
