from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from openchem.domain.scientific_result import PhCurveResult

# Distinct, colour-blind-reasonable series colours. Cycled if a result has
# more series than this -- a pKa microspecies distribution can legitimately
# have a dozen curves.
_SERIES_COLORS = [
    QColor(214, 96, 39),  # orange
    QColor(38, 133, 76),  # green
    QColor(49, 91, 173),  # blue
    QColor(146, 62, 156),  # purple
    QColor(191, 47, 47),  # red
    QColor(64, 143, 168),  # teal
    QColor(150, 108, 41),  # brown
]


class PhCurveWidget(QWidget):
    """A multi-series line chart of a property against pH.

    Hand-rolled `QPainter`, no charting dependency -- the third chart in
    this codebase built this way (`nmr_correlation_plot_widget.py` scatter,
    `nmr_spectrum_widget.py` peaks), and consistent with
    `ChemistryEngine.render_2d_svg`'s "generate it ourselves" precedent.

    Unlike the NMR plots, axes here run in the ordinary direction: pH
    increases left to right. NMR's descending convention is specific to
    chemical shift and would be actively wrong for a titration curve.

    Hovering reads out the value of every series at the nearest sampled pH,
    which is what makes a crowded microspecies plot legible -- Marvin shows
    the same thing as a table beside the chart.
    """

    _MARGIN_LEFT = 58.0
    _MARGIN_RIGHT = 12.0
    _MARGIN_TOP = 12.0
    _MARGIN_BOTTOM = 42.0
    _LEGEND_ROW_HEIGHT = 16.0

    ph_hovered = Signal(float)  # nearest sampled pH under the cursor

    def __init__(self, result: PhCurveResult | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result: PhCurveResult | None = None
        self._hover_index: int | None = None
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        if result is not None:
            self.set_result(result)

    def set_result(self, result: PhCurveResult | None) -> None:
        self._result = result
        self._hover_index = None
        self.update()

    def result(self) -> PhCurveResult | None:
        return self._result

    # -- geometry ---------------------------------------------------------

    def _plot_rect(self) -> QRectF:
        legend_height = self._LEGEND_ROW_HEIGHT * len(self._result.series) if self._result else 0.0
        return QRectF(
            self._MARGIN_LEFT,
            self._MARGIN_TOP + legend_height,
            max(self.width() - self._MARGIN_LEFT - self._MARGIN_RIGHT, 1.0),
            max(self.height() - self._MARGIN_TOP - self._MARGIN_BOTTOM - legend_height, 1.0),
        )

    def _value_range(self) -> tuple[float, float]:
        """Y range across every series.

        A result that declares `y_min`/`y_max` gets exactly those -- that
        is how a physically bounded quantity (a microspecies distribution
        is 0-100%) avoids the padding below drawing an axis from -8% to
        108%, which is what it did before this was rendered and looked at.

        Otherwise the observed range is padded by 8% so curves don't sit
        on the frame, and a flat series is widened rather than collapsing
        the plot to zero height.
        """
        values = [v for series in self._result.series.values() for v in series]
        if not values:
            return 0.0, 1.0
        low = self._result.y_min if self._result.y_min is not None else min(values)
        high = self._result.y_max if self._result.y_max is not None else max(values)
        if low == high:
            return low - 1.0, high + 1.0
        # Only pad the ends the result did not pin.
        pad = (high - low) * 0.08
        if self._result.y_min is None:
            low -= pad
        if self._result.y_max is None:
            high += pad
        return low, high

    def _to_widget(self, ph: float, value: float, rect: QRectF) -> QPointF:
        ph_values = self._result.ph_values
        ph_min, ph_max = ph_values[0], ph_values[-1]
        low, high = self._value_range()
        fx = (ph - ph_min) / (ph_max - ph_min) if ph_max != ph_min else 0.5
        fy = (value - low) / (high - low) if high != low else 0.5
        return QPointF(rect.left() + fx * rect.width(), rect.bottom() - fy * rect.height())

    # -- interaction ------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._has_data():
            return
        rect = self._plot_rect()
        ph_values = self._result.ph_values
        ph_min, ph_max = ph_values[0], ph_values[-1]
        fraction = (event.position().x() - rect.left()) / rect.width() if rect.width() else 0.0
        target = ph_min + max(0.0, min(1.0, fraction)) * (ph_max - ph_min)
        index = min(range(len(ph_values)), key=lambda i: abs(ph_values[i] - target))
        if index != self._hover_index:
            self._hover_index = index
            self.ph_hovered.emit(ph_values[index])
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hover_index = None
        self.update()

    def _has_data(self) -> bool:
        return bool(self._result and self._result.ph_values and self._result.series)

    # -- painting ---------------------------------------------------------

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
        ph_values = self._result.ph_values
        ph_min, ph_max = ph_values[0], ph_values[-1]
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
            painter.drawText(
                QRectF(x - 24, rect.bottom() + 2, 48, 16),
                Qt.AlignmentFlag.AlignCenter,
                f"{ph_min + fraction * (ph_max - ph_min):.1f}",
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
            zero_y = self._to_widget(ph_min, 0.0, rect).y()
            painter.setPen(QPen(QColor(70, 70, 70), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(rect.left(), zero_y), QPointF(rect.right(), zero_y))

        painter.setPen(QPen(QColor(60, 60, 60)))
        painter.drawText(
            QRectF(0, self.height() - 20, self.width(), 18),
            Qt.AlignmentFlag.AlignCenter,
            self._result.x_label,
        )
        if self._result.y_label:
            painter.save()
            painter.translate(12, self.height() / 2)
            painter.rotate(-90)
            painter.drawText(
                QRectF(-self.height() / 2, -9, self.height(), 18),
                Qt.AlignmentFlag.AlignCenter,
                self._result.y_label,
            )
            painter.restore()

    def _draw_series(self, painter: QPainter, rect: QRectF) -> None:
        ph_values = self._result.ph_values
        for index, (name, values) in enumerate(self._result.series.items()):
            color = _SERIES_COLORS[index % len(_SERIES_COLORS)]
            painter.setPen(QPen(color, 2))
            # zip() rather than indexing by position: a series shorter than
            # ph_values draws the part it has instead of raising, which
            # matters because a curve can legitimately be truncated where a
            # microspecies stops existing.
            points = [self._to_widget(ph, value, rect) for ph, value in zip(ph_values, values)]
            for start, end in zip(points, points[1:]):
                painter.drawLine(start, end)

    def _draw_legend(self, painter: QPainter) -> None:
        for index, name in enumerate(self._result.series):
            color = _SERIES_COLORS[index % len(_SERIES_COLORS)]
            y = self._MARGIN_TOP + index * self._LEGEND_ROW_HEIGHT
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(self._MARGIN_LEFT, y + 8), QPointF(self._MARGIN_LEFT + 18, y + 8))
            painter.setPen(QPen(QColor(60, 60, 60)))
            painter.drawText(
                QRectF(self._MARGIN_LEFT + 24, y, self.width() - self._MARGIN_LEFT - 30, self._LEGEND_ROW_HEIGHT),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                name,
            )

    def _draw_hover(self, painter: QPainter, rect: QRectF) -> None:
        if self._hover_index is None:
            return
        ph = self._result.ph_values[self._hover_index]
        x = self._to_widget(ph, 0.0, rect).x()
        painter.setPen(QPen(QColor(120, 120, 120), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

        lines = [f"pH {ph:.2f}"]
        for name, values in self._result.series.items():
            if self._hover_index < len(values):
                lines.append(f"{name}: {values[self._hover_index]:.2f}")
        painter.setPen(QPen(QColor(40, 40, 40)))
        painter.drawText(
            QRectF(rect.left() + 6, rect.top() + 4, rect.width() - 12, rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            "\n".join(lines),
        )

    def readout_at(self, ph: float) -> dict[str, float]:
        """Every series' value at the sampled pH nearest `ph`.

        Public because the readout is useful outside painting -- a panel
        can show it as a table beside the chart, which is how Marvin
        presents its pKa and logD results.
        """
        if not self._has_data():
            return {}
        ph_values = self._result.ph_values
        index = min(range(len(ph_values)), key=lambda i: abs(ph_values[i] - ph))
        return {
            name: values[index]
            for name, values in self._result.series.items()
            if index < len(values)
        }
