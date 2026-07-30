from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class Peak:
    """A single point on a 2D correlation scatter plot -- generic enough
    (x, y, optional label) that a future contour renderer could consume
    the same shape without a data-model change, per Phase 22's plan.
    """

    x: float
    y: float
    label: str | None = None


class NmrCorrelationPlotWidget(QWidget):
    """A plain scatter plot of 2D NMR cross peaks (HSQC/HMBC/COSY) --
    hand-rolled `QPainter`, no charting library. Axes drawn in NMR
    convention (higher ppm toward the top-left corner). Explicitly NOT a
    contour plot: no Gaussian broadening, intensity simulation, or
    marching-squares extraction -- see the Phase 22 plan's "Explicitly
    deferred" section for what a future upgrade would add on top of this
    same `Peak` data.
    """

    _MARGIN = 50.0

    def __init__(
        self,
        peaks: list[Peak] | None = None,
        x_label: str = "",
        y_label: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._peaks: list[Peak] = list(peaks or [])
        self._x_label = x_label
        self._y_label = y_label
        self.setMinimumSize(280, 280)

    def set_peaks(self, peaks: list[Peak], x_label: str = "", y_label: str = "") -> None:
        self._peaks = list(peaks)
        self._x_label = x_label
        self._y_label = y_label
        self.update()

    def _axis_ranges(self) -> tuple[float, float, float, float]:
        if not self._peaks:
            return 0.0, 1.0, 0.0, 1.0
        xs = [p.x for p in self._peaks]
        ys = [p.y for p in self._peaks]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        # Pad a flat/single-point range so it isn't a zero-width plot area.
        if x_min == x_max:
            x_min, x_max = x_min - 1.0, x_max + 1.0
        if y_min == y_max:
            y_min, y_max = y_min - 1.0, y_max + 1.0
        pad_x = (x_max - x_min) * 0.1
        pad_y = (y_max - y_min) * 0.1
        return x_min - pad_x, x_max + pad_x, y_min - pad_y, y_max + pad_y

    def _to_widget_coords(
        self, x: float, y: float, plot_rect: QRectF, x_range: tuple[float, float], y_range: tuple[float, float]
    ) -> tuple[float, float]:
        x_min, x_max = x_range
        y_min, y_max = y_range
        # NMR convention: higher ppm toward the origin (top-left) -- both
        # axes are drawn descending left-to-right / top-to-bottom.
        fx = (x_max - x) / (x_max - x_min) if x_max != x_min else 0.5
        fy = (y_max - y) / (y_max - y_min) if y_max != y_min else 0.5
        px = plot_rect.left() + fx * plot_rect.width()
        py = plot_rect.top() + fy * plot_rect.height()
        return px, py

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        plot_rect = QRectF(
            self._MARGIN,
            self._MARGIN / 2,
            max(self.width() - 1.5 * self._MARGIN, 1.0),
            max(self.height() - 1.5 * self._MARGIN, 1.0),
        )

        painter.setPen(QPen(QColor(120, 120, 120)))
        painter.drawRect(plot_rect)

        painter.drawText(
            QRectF(0, self.height() - self._MARGIN / 2, self.width(), self._MARGIN / 2),
            Qt.AlignmentFlag.AlignCenter,
            self._x_label,
        )
        painter.save()
        painter.translate(self._MARGIN / 4, self.height() / 2)
        painter.rotate(-90)
        painter.drawText(
            QRectF(-self.height() / 2, -self._MARGIN / 4, self.height(), self._MARGIN / 2),
            Qt.AlignmentFlag.AlignCenter,
            self._y_label,
        )
        painter.restore()

        if not self._peaks:
            painter.end()
            return

        x_min, x_max, y_min, y_max = self._axis_ranges()
        painter.setPen(QPen(QColor(30, 100, 200)))
        painter.setBrush(QColor(30, 100, 200))
        for peak in self._peaks:
            px, py = self._to_widget_coords(peak.x, peak.y, plot_rect, (x_min, x_max), (y_min, y_max))
            painter.drawEllipse(QRectF(px - 3, py - 3, 6, 6))
            if peak.label:
                painter.drawText(QRectF(px + 5, py - 8, 60, 16), Qt.AlignmentFlag.AlignLeft, peak.label)
        painter.end()
