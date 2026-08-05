"""The distribution of one column across a project.

Bars, a median line, and the summary line above them. Small on purpose:
`chem/analytics.describe` decides the bins and computes the statistics, so
this draws a `Distribution` and knows nothing about where it came from --
which is what lets the binning rule be tested without a widget.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from openchem.chem.analytics import Distribution

_BAR_COLOR = QColor(70, 120, 180)
_MEDIAN_COLOR = QColor(200, 70, 70)


class HistogramWidget(QWidget):
    """A histogram with its statistics stated above it.

    THE MEDIAN LINE IS DRAWN, NOT JUST REPORTED, because it is what makes a
    skewed column obvious: a molecular-weight distribution with a long
    upper tail has a median well left of centre, and that gap between the
    line and the middle of the mass is the finding. The mean is in the
    caption rather than on the plot -- two vertical lines close together
    read as an error.
    """

    _MARGIN_LEFT = 46.0
    _MARGIN_RIGHT = 14.0
    _MARGIN_TOP = 26.0
    _MARGIN_BOTTOM = 42.0

    def __init__(
        self,
        distribution: Distribution | None = None,
        label: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._distribution = distribution
        self._label = label
        self._empty_message = "No data"
        self.setMinimumSize(320, 220)

    def set_distribution(self, distribution: Distribution | None, label: str = "") -> None:
        self._distribution = distribution
        self._label = label
        self.update()

    def set_empty_message(self, message: str) -> None:
        self._empty_message = message
        self.update()

    def distribution(self) -> Distribution | None:
        return self._distribution

    def _plot_rect(self) -> QRectF:
        return QRectF(
            self._MARGIN_LEFT,
            self._MARGIN_TOP,
            max(self.width() - self._MARGIN_LEFT - self._MARGIN_RIGHT, 1.0),
            max(self.height() - self._MARGIN_TOP - self._MARGIN_BOTTOM, 1.0),
        )

    def _has_data(self) -> bool:
        return bool(self._distribution and self._distribution.counts)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._plot_rect()
        painter.setPen(QPen(QColor(120, 120, 120)))
        painter.drawRect(rect)
        if not self._has_data():
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._empty_message)
            painter.end()
            return
        distribution = self._distribution
        tallest = max(distribution.counts) or 1
        self._draw_bars(painter, rect, tallest)
        self._draw_axes(painter, rect, tallest)
        self._draw_median(painter, rect)
        painter.setPen(QPen(QColor(40, 40, 40)))
        painter.drawText(
            QRectF(rect.left(), 4, rect.width(), self._MARGIN_TOP - 6),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            distribution.describe(),
        )
        painter.drawText(
            QRectF(0, self.height() - 20, self.width(), 18),
            Qt.AlignmentFlag.AlignCenter,
            self._label,
        )
        painter.end()

    def _draw_bars(self, painter: QPainter, rect: QRectF, tallest: int) -> None:
        counts = self._distribution.counts
        width = rect.width() / len(counts)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.setBrush(_BAR_COLOR)
        for index, count in enumerate(counts):
            if count == 0:
                continue
            height = rect.height() * count / tallest
            painter.drawRect(
                QRectF(rect.left() + index * width, rect.bottom() - height, width, height)
            )
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_axes(self, painter: QPainter, rect: QRectF, tallest: int) -> None:
        edges = self._distribution.bin_edges
        painter.setPen(QPen(QColor(90, 90, 90)))
        # Five x labels regardless of bin count: one per bin edge is
        # unreadable at 30 bins and pointless at 5.
        for step in range(5):
            fraction = step / 4.0
            x = rect.left() + fraction * rect.width()
            value = edges[0] + fraction * (edges[-1] - edges[0])
            painter.drawText(
                QRectF(x - 32, rect.bottom() + 3, 64, 15),
                Qt.AlignmentFlag.AlignCenter,
                f"{value:.4g}",
            )
        for step in range(3):
            fraction = step / 2.0
            y = rect.bottom() - fraction * rect.height()
            painter.drawText(
                QRectF(0, y - 8, self._MARGIN_LEFT - 6, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{int(round(fraction * tallest))}",
            )

    def _draw_median(self, painter: QPainter, rect: QRectF) -> None:
        edges = self._distribution.bin_edges
        span = edges[-1] - edges[0]
        if span <= 0:
            return
        fraction = (self._distribution.median - edges[0]) / span
        x = rect.left() + fraction * rect.width()
        painter.setPen(QPen(_MEDIAN_COLOR, 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
