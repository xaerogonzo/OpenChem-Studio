"""A declared continuous curve, drawn. Knows no chemistry.

The sibling of `StickChartWidget` and the second renderer of the
producer-declared chart channel. Generalised OUT OF `PhCurveWidget`
rather than written beside it: that widget already did multi-series
drawing, a legend, gridlines, a zero line and a hover readout, and its
only coupling to pH was that it took a `PhCurveResult`. Two
implementations of "draw some curves on a pair of axes" is the drift this
repository has paid for five times.

**IT NEVER SORTS, RESCALES OR RE-PAIRS.** `valid_chart_annotation`
refuses a series whose x is not monotonic, and the answer to a refused
annotation is to draw NOTHING and log -- never to sort it into shape.
Sorting here would move a refusal into a repair and put a picture built
from repaired nonsense on the screen, which reads as a result.

**EACH SERIES CARRIES ITS OWN POINTS**, so two curves need not share an x
grid. `PhCurveResult` samples one `ph_grid` for all of them and that is
still the common case; a computed curve against a measured one, sampled
where the instrument sampled, is the case a shared-grid renderer could
not draw at all.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from openchem.domain.report import LineChartAnnotation, valid_chart_annotation

logger = logging.getLogger("openchem.ui")

#: Distinct, colour-blind-reasonable series colours. Cycled if a chart has
#: more series than this -- a pKa microspecies distribution can
#: legitimately have a dozen curves. Moved here from `PhCurveWidget` with
#: the widget; the palette is a property of drawing several curves at
#: once, not of pH.
SERIES_COLORS = [
    QColor(214, 96, 39),  # orange
    QColor(38, 133, 76),  # green
    QColor(49, 91, 173),  # blue
    QColor(146, 62, 156),  # purple
    QColor(191, 47, 47),  # red
    QColor(64, 143, 168),  # teal
    QColor(150, 108, 41),  # brown
]

#: How far past the observed extremes an UNPINNED axis end is padded, as a
#: fraction of the range, so a curve does not sit on the frame. An end the
#: producer pinned through `y_min`/`y_max` is not padded at all -- that is
#: the whole point of pinning it.
_AXIS_PAD = 0.08


class LineChartWidget(QWidget):
    """One `LineChartAnnotation`, painted."""

    _MARGIN_LEFT = 58.0
    _MARGIN_RIGHT = 12.0
    _MARGIN_TOP = 12.0
    _MARGIN_BOTTOM = 42.0
    _LEGEND_ROW_HEIGHT = 16.0

    #: The x under the cursor, snapped to the nearest sampled point.
    x_hovered = Signal(float)

    def __init__(
        self,
        annotation: LineChartAnnotation | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._annotation: LineChartAnnotation | None = None
        self._hover_x: float | None = None
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        if annotation is not None:
            self.set_annotation(annotation)

    # -- what it is showing ------------------------------------------------

    def set_annotation(self, annotation: LineChartAnnotation | None) -> None:
        """Adopt `annotation`, or refuse it and draw nothing.

        The same contract `StickChartWidget.set_annotation` has: a
        malformed annotation is REFUSED with a log line rather than
        repaired, because a picture assembled from repaired nonsense is
        indistinguishable from a result.
        """
        if annotation is not None and not valid_chart_annotation(annotation):
            logger.warning("Refusing to draw a malformed line annotation: %r", annotation)
            annotation = None
        self._annotation = annotation
        self._hover_x = None
        self.update()

    def annotation(self) -> LineChartAnnotation | None:
        return self._annotation

    def is_drawing(self) -> bool:
        """"Nothing declared" and "declared and refused", told apart.

        Exposed for the reason `StickChartWidget.is_drawing` is: without
        it a caller cannot distinguish the two without reading the log,
        and they look identical on screen.
        """
        return self._annotation is not None

    # -- geometry ----------------------------------------------------------

    def _series(self):
        return self._annotation.series if self._annotation else ()

    def _plot_rect(self) -> QRectF:
        legend_height = self._LEGEND_ROW_HEIGHT * len(self._series())
        return QRectF(
            self._MARGIN_LEFT,
            self._MARGIN_TOP + legend_height,
            max(self.width() - self._MARGIN_LEFT - self._MARGIN_RIGHT, 1.0),
            max(self.height() - self._MARGIN_TOP - self._MARGIN_BOTTOM - legend_height, 1.0),
        )

    def _x_range(self) -> tuple[float, float]:
        """The extremes across EVERY series, not the first one's.

        A shared grid makes these the same; different grids do not, and
        taking one series' ends would silently crop the others.
        """
        xs = [x for series in self._series() for x, _y in series.points]
        if not xs:
            return 0.0, 1.0
        low, high = min(xs), max(xs)
        return (low - 1.0, high + 1.0) if low == high else (low, high)

    def _value_range(self) -> tuple[float, float]:
        """The y range, honouring whichever end the producer pinned.

        A pinned end is used EXACTLY and never padded, which is how a
        bounded quantity avoids an axis drawn past its own limits. An
        unpinned end fits the data and is padded so curves do not sit on
        the frame; a flat series is widened rather than collapsing the
        plot to zero height.
        """
        values = [y for series in self._series() for _x, y in series.points]
        if not values:
            return 0.0, 1.0
        annotation = self._annotation
        low = annotation.y_min if annotation.y_min is not None else min(values)
        high = annotation.y_max if annotation.y_max is not None else max(values)
        if low == high:
            return low - 1.0, high + 1.0
        pad = (high - low) * _AXIS_PAD
        if annotation.y_min is None:
            low -= pad
        if annotation.y_max is None:
            high += pad
        return low, high

    def _to_widget(self, x: float, y: float, rect: QRectF) -> QPointF:
        """Model coordinates to widget coordinates.

        **`x_descending` IS APPLIED HERE AND NOWHERE ELSE.** It is a
        coordinate transform, so it belongs in the transform: the points
        are never reversed or reordered, and a hit test, a readout and an
        export all see what the producer handed over.
        """
        x_min, x_max = self._x_range()
        low, high = self._value_range()
        fx = (x - x_min) / (x_max - x_min) if x_max != x_min else 0.5
        if self._annotation is not None and self._annotation.x_descending:
            fx = 1.0 - fx
        fy = (y - low) / (high - low) if high != low else 0.5
        return QPointF(rect.left() + fx * rect.width(), rect.bottom() - fy * rect.height())

    # -- interaction -------------------------------------------------------

    def _sampled_x(self) -> list[float]:
        """Every x any series was sampled at, once, in order."""
        return sorted({x for series in self._series() for x, _y in series.points})

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._has_data():
            return
        rect = self._plot_rect()
        x_min, x_max = self._x_range()
        fraction = (event.position().x() - rect.left()) / rect.width() if rect.width() else 0.0
        fraction = max(0.0, min(1.0, fraction))
        if self._annotation.x_descending:
            fraction = 1.0 - fraction
        target = x_min + fraction * (x_max - x_min)
        sampled = self._sampled_x()
        nearest = min(sampled, key=lambda value: abs(value - target))
        if nearest != self._hover_x:
            self._hover_x = nearest
            self.x_hovered.emit(nearest)
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hover_x = None
        self.update()

    def _has_data(self) -> bool:
        return bool(self._annotation and any(s.points for s in self._series()))

    def readout_at(self, x: float) -> dict[str, float]:
        """Every series' value at the sampled x nearest `x`.

        Public because the readout is useful outside painting -- a panel
        can show it as a table beside the chart.

        **A SERIES THAT DOES NOT COVER `x` IS OMITTED**, rather than
        given the nearest value it does have. A microspecies curve stops
        where that species stops existing, and reporting its last value
        for a query past the end states a measurement nobody made -- the
        same reason it is not zero-filled either, since a fabricated zero
        reads as a real measured value.

        Within a series' range the nearest sampled point is used, which
        on the ordinary shared grid is exactly the value at that grid
        position.
        """
        if not self._has_data():
            return {}
        out: dict[str, float] = {}
        for series in self._series():
            if not series.points:
                continue
            xs = [px for px, _py in series.points]
            if not min(xs) <= x <= max(xs):
                continue
            out[series.name] = min(series.points, key=lambda p: abs(p[0] - x))[1]
        return out

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._plot_rect()

        painter.setPen(QPen(QColor(120, 120, 120)))
        painter.drawRect(rect)

        if not self._has_data():
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No data")
            painter.end()
            return

        self._draw_axes(painter, rect)
        self._draw_series(painter, rect)
        self._draw_legend(painter)
        self._draw_hover(painter, rect)
        painter.end()

    def _draw_axes(self, painter: QPainter, rect: QRectF) -> None:
        annotation = self._annotation
        x_min, x_max = self._x_range()
        low, high = self._value_range()

        painter.setPen(QPen(QColor(205, 205, 205)))
        # Six gridlines each way: enough to read against, few enough not to
        # compete with the curves themselves.
        for step in range(7):
            fraction = step / 6.0
            x = rect.left() + fraction * rect.width()
            y = rect.bottom() - fraction * rect.height()
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        painter.setPen(QPen(QColor(90, 90, 90)))
        for step in range(7):
            fraction = step / 6.0
            x = rect.left() + fraction * rect.width()
            y = rect.bottom() - fraction * rect.height()
            # The tick reads the value at that POSITION, so a descending
            # axis labels its left end with the high value.
            along = 1.0 - fraction if annotation.x_descending else fraction
            painter.drawText(
                QRectF(x - 24, rect.bottom() + 2, 48, 16),
                Qt.AlignmentFlag.AlignCenter,
                f"{x_min + along * (x_max - x_min):.1f}",
            )
            painter.drawText(
                QRectF(0, y - 8, self._MARGIN_LEFT - 5, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{low + fraction * (high - low):.2f}",
            )

        # A zero line, when the range straddles it -- an isoelectric-point
        # curve is read by where it crosses zero, so that crossing needs to
        # be visible rather than inferred from the tick labels.
        if low < 0.0 < high:
            zero_y = self._to_widget(x_min, 0.0, rect).y()
            painter.setPen(QPen(QColor(70, 70, 70), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(rect.left(), zero_y), QPointF(rect.right(), zero_y))

        painter.setPen(QPen(QColor(60, 60, 60)))
        painter.drawText(
            QRectF(0, self.height() - 20, self.width(), 18),
            Qt.AlignmentFlag.AlignCenter,
            axis_caption(annotation.x_label, annotation.x_units),
        )
        if annotation.y_label:
            painter.save()
            painter.translate(12, self.height() / 2)
            painter.rotate(-90)
            painter.drawText(
                QRectF(-self.height() / 2, -9, self.height(), 18),
                Qt.AlignmentFlag.AlignCenter,
                axis_caption(annotation.y_label, annotation.y_units),
            )
            painter.restore()

    def _draw_series(self, painter: QPainter, rect: QRectF) -> None:
        for index, series in enumerate(self._series()):
            color = SERIES_COLORS[index % len(SERIES_COLORS)]
            painter.setPen(QPen(color, 2))
            points = [self._to_widget(x, y, rect) for x, y in series.points]
            for start, end in zip(points, points[1:]):
                painter.drawLine(start, end)

    def _draw_legend(self, painter: QPainter) -> None:
        for index, series in enumerate(self._series()):
            color = SERIES_COLORS[index % len(SERIES_COLORS)]
            y = self._MARGIN_TOP + index * self._LEGEND_ROW_HEIGHT
            painter.setPen(QPen(color, 2))
            painter.drawLine(
                QPointF(self._MARGIN_LEFT, y + 8), QPointF(self._MARGIN_LEFT + 18, y + 8)
            )
            painter.setPen(QPen(QColor(60, 60, 60)))
            painter.drawText(
                QRectF(
                    self._MARGIN_LEFT + 24,
                    y,
                    self.width() - self._MARGIN_LEFT - 30,
                    self._LEGEND_ROW_HEIGHT,
                ),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                series.name,
            )

    def _draw_hover(self, painter: QPainter, rect: QRectF) -> None:
        if self._hover_x is None:
            return
        x = self._to_widget(self._hover_x, 0.0, rect).x()
        painter.setPen(QPen(QColor(120, 120, 120), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

        label = self._annotation.x_label or "x"
        lines = [f"{label} {self._hover_x:.2f}"]
        lines.extend(
            f"{name}: {value:.2f}" for name, value in self.readout_at(self._hover_x).items()
        )
        painter.setPen(QPen(QColor(40, 40, 40)))
        painter.drawText(
            QRectF(rect.left() + 6, rect.top() + 4, rect.width() - 12, rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            "\n".join(lines),
        )


def axis_caption(label: str, units: str) -> str:
    """`label (units)`, or the bare label when there are none.

    The same composition `StickChartWidget` uses, and the same one
    `Fact.value_with_units` makes for a report row: the producer keeps the
    two apart and a view joins them.
    """
    return f"{label} ({units})" if units else label
