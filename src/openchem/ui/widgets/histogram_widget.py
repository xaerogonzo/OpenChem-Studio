"""The distribution of one column across a project.

Bars, a median line, and the summary line above them. Small on purpose:
`chem/analytics.describe` decides the bins and computes the statistics, so
this draws a `Distribution` and knows nothing about where it came from --
which is what lets the binning rule be tested without a widget.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from openchem.ui.picture_export import show_picture_menu

from openchem.chem.analytics import Distribution
from openchem.ui.widgets.x_zoomable import XZoomable

_BAR_COLOR = QColor(70, 120, 180)
_MEDIAN_COLOR = QColor(200, 70, 70)


class HistogramWidget(XZoomable, QWidget):
    """A histogram with its statistics stated above it.

    Ctrl+wheel zooms along x, Shift+wheel pans, a double-click resets: a long thin tail is
    invisible at full span. The bars rescale to the tallest bin IN VIEW and the count axis says
    so, since a zoomed histogram drawn against the whole column's maximum would be a row of
    slivers.

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

    #: The visible x window changed (zoom, pan or reset).
    view_changed = Signal()

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
        if distribution is not self._distribution:
            self._x_window = None
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

    def _zoom_has_data(self) -> bool:
        return self._has_data()

    def _full_x_range(self) -> tuple[float, float]:
        edges = self._distribution.bin_edges
        return edges[0], edges[-1]

    def _visible_bins(self) -> list[tuple[int, float, float]]:
        """(index, left edge, right edge) of every bin that reaches into the window."""
        edges = self._distribution.bin_edges
        low, high = self._x_range()
        return [
            (index, edges[index], edges[index + 1])
            for index in range(len(self._distribution.counts))
            if edges[index + 1] > low and edges[index] < high
        ]

    def _x_of(self, rect: QRectF, value: float) -> float:
        low, high = self._x_range()
        span = high - low
        return rect.left() + ((value - low) / span if span > 0 else 0.0) * rect.width()

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        # A reader chart has its own menu installed (CustomContextMenu), which
        # takes over; this is for the same plot anywhere else it is shown.
        show_picture_menu(self, event, "histogram")

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
        tallest = max((distribution.counts[i] for i, _l, _r in self._visible_bins()), default=0) or 1
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
        low, high = self._x_range()
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.setBrush(_BAR_COLOR)
        for index, left, right in self._visible_bins():
            count = counts[index]
            if count == 0:
                continue
            height = rect.height() * count / tallest
            # A bin cut by the window is drawn to the window's edge, never past the plot.
            x0 = self._x_of(rect, max(left, low))
            x1 = self._x_of(rect, min(right, high))
            painter.drawRect(QRectF(x0, rect.bottom() - height, x1 - x0, height))
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_axes(self, painter: QPainter, rect: QRectF, tallest: int) -> None:
        low, high = self._x_range()
        painter.setPen(QPen(QColor(90, 90, 90)))
        # Five x labels regardless of bin count: one per bin edge is
        # unreadable at 30 bins and pointless at 5.
        for step in range(5):
            fraction = step / 4.0
            x = rect.left() + fraction * rect.width()
            value = low + fraction * (high - low)
            painter.drawText(
                QRectF(x - 32, rect.bottom() + 3, 64, 15),
                Qt.AlignmentFlag.AlignCenter,
                f"{value:.4g}",
            )
        # DISTINCT counts, each drawn at its own height. Half of a tallest bin of 1 rounds to 0, so
        # three evenly spaced labels read "1, 0, 0" -- a zoomed view onto a thin tail hits this.
        for value in sorted({int(round(fraction * tallest)) for fraction in (0.0, 0.5, 1.0)}):
            y = rect.bottom() - (value / tallest) * rect.height()
            painter.drawText(
                QRectF(0, y - 8, self._MARGIN_LEFT - 6, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{value}",
            )

    def _draw_median(self, painter: QPainter, rect: QRectF) -> None:
        edges = self._distribution.bin_edges
        if edges[-1] - edges[0] <= 0 or not self.in_view(self._distribution.median):
            return
        x = self._x_of(rect, self._distribution.median)
        painter.setPen(QPen(_MEDIAN_COLOR, 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
