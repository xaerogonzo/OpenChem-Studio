"""A scatter of one column against another.

The fourth hand-rolled `QPainter` chart in this codebase, after the NMR
spectrum, the NMR correlation plot and the pH curve. Consistent with them
deliberately: no charting dependency, and the axis/tick/label idiom is the
one already established in `ph_curve_widget.py`.

Generic rather than correlation-specific because two features need exactly
this picture -- descriptor A against descriptor B, and PC1 against PC2 --
and they differ only in what the axes are called and whether a fit line is
drawn. `groups` exists so a clustering result can colour the same scatter
without a third widget.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

#: Same Okabe-Ito set the per-atom categorical palette uses, and for the
#: same reason: these are group identities, not a ramp, and they have to be
#: distinguishable under the common colour-vision deficiencies.
_GROUP_COLORS = [
    QColor(0, 114, 178),
    QColor(230, 159, 0),
    QColor(0, 158, 115),
    QColor(204, 121, 167),
    QColor(86, 180, 233),
    QColor(213, 94, 0),
    QColor(180, 170, 40),
]
_UNGROUPED = QColor(60, 90, 150)


@dataclass(frozen=True)
class ScatterPoint:
    x: float
    y: float
    label: str = ""
    #: Cluster or class index, or None. Coloured from `_GROUP_COLORS`,
    #: cycled -- a 30-cluster project repeats colours, which is honest
    #: (they ARE hard to tell apart) rather than inventing 30 distinct ones.
    group: int | None = None


class ScatterPlotWidget(QWidget):
    """Points, axes, an optional least-squares line, and a caption.

    THE CAPTION IS NOT DECORATION. This widget's main use is answering "is
    this correlation real", and a scatter without its r and its n invites
    exactly the eyeballing that the hERG size-confound survived. The caption
    is drawn inside the plot, always, and the widget has no mode that hides
    it.
    """

    _MARGIN_LEFT = 64.0
    _MARGIN_RIGHT = 14.0
    _MARGIN_TOP = 26.0
    _MARGIN_BOTTOM = 46.0
    _POINT_RADIUS = 3.5

    point_hovered = Signal(int)  # index into points(), -1 when none

    def __init__(
        self,
        points: list[ScatterPoint] | None = None,
        x_label: str = "",
        y_label: str = "",
        caption: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._points: list[ScatterPoint] = list(points or [])
        self._x_label = x_label
        self._y_label = y_label
        self._caption = caption
        self._fit: tuple[float, float] | None = None
        self._hover_index: int | None = None
        self._empty_message = "No data"
        self.setMinimumSize(340, 260)
        self.setMouseTracking(True)

    def set_points(
        self,
        points: list[ScatterPoint],
        x_label: str = "",
        y_label: str = "",
        caption: str = "",
        fit: tuple[float, float] | None = None,
    ) -> None:
        self._points = list(points)
        self._x_label = x_label
        self._y_label = y_label
        self._caption = caption
        self._fit = fit
        self._hover_index = None
        self.update()

    def set_empty_message(self, message: str) -> None:
        """What to draw instead of points when there are none.

        An empty plot that says "No data" reads as broken; one that says
        "Only 1 molecule has both of these values" reads as a fact about
        the project. Same convention as the calculator results that explain
        their own emptiness rather than rendering blank.
        """
        self._empty_message = message
        self.update()

    def points(self) -> list[ScatterPoint]:
        return list(self._points)

    # -- geometry ---------------------------------------------------------

    def _plot_rect(self) -> QRectF:
        return QRectF(
            self._MARGIN_LEFT,
            self._MARGIN_TOP,
            max(self.width() - self._MARGIN_LEFT - self._MARGIN_RIGHT, 1.0),
            max(self.height() - self._MARGIN_TOP - self._MARGIN_BOTTOM, 1.0),
        )

    def _ranges(self) -> tuple[float, float, float, float]:
        """Padded data bounds. A column with no spread is widened rather
        than collapsing the axis to zero width, which would divide by zero
        in `_to_widget` and stack every point on one pixel."""
        xs = [point.x for point in self._points]
        ys = [point.y for point in self._points]
        return (*_padded(min(xs), max(xs)), *_padded(min(ys), max(ys)))

    def _to_widget(self, x: float, y: float, rect: QRectF, ranges) -> QPointF:
        x_min, x_max, y_min, y_max = ranges
        fx = (x - x_min) / (x_max - x_min)
        fy = (y - y_min) / (y_max - y_min)
        return QPointF(rect.left() + fx * rect.width(), rect.bottom() - fy * rect.height())

    # -- interaction ------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._points:
            return
        rect = self._plot_rect()
        ranges = self._ranges()
        position = event.position()
        nearest = min(
            range(len(self._points)),
            key=lambda index: _distance_squared(
                self._to_widget(self._points[index].x, self._points[index].y, rect, ranges), position
            ),
        )
        found = self._to_widget(self._points[nearest].x, self._points[nearest].y, rect, ranges)
        # A generous radius: these are 3.5px dots, and requiring the cursor
        # to land on one makes the readout effectively unreachable.
        index = nearest if _distance_squared(found, position) <= 15.0**2 else None
        if index != self._hover_index:
            self._hover_index = index
            self.point_hovered.emit(-1 if index is None else index)
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hover_index = None
        self.update()

    # -- painting ---------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._plot_rect()
        painter.setPen(QPen(QColor(120, 120, 120)))
        painter.drawRect(rect)
        if not self._points:
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._empty_message)
            painter.end()
            return
        ranges = self._ranges()
        self._draw_axes(painter, rect, ranges)
        self._draw_fit(painter, rect, ranges)
        self._draw_points(painter, rect, ranges)
        self._draw_caption(painter, rect)
        self._draw_hover(painter, rect, ranges)
        painter.end()

    def _draw_axes(self, painter: QPainter, rect: QRectF, ranges) -> None:
        x_min, x_max, y_min, y_max = ranges
        painter.setPen(QPen(QColor(226, 226, 226)))
        for step in range(6):
            fraction = step / 5.0
            x = rect.left() + fraction * rect.width()
            y = rect.bottom() - fraction * rect.height()
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        painter.setPen(QPen(QColor(90, 90, 90)))
        for step in range(6):
            fraction = step / 5.0
            x = rect.left() + fraction * rect.width()
            y = rect.bottom() - fraction * rect.height()
            painter.drawText(
                QRectF(x - 32, rect.bottom() + 3, 64, 15),
                Qt.AlignmentFlag.AlignCenter,
                _tick(x_min + fraction * (x_max - x_min)),
            )
            painter.drawText(
                QRectF(0, y - 8, self._MARGIN_LEFT - 6, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                _tick(y_min + fraction * (y_max - y_min)),
            )
        painter.setPen(QPen(QColor(55, 55, 55)))
        painter.drawText(
            QRectF(0, self.height() - 21, self.width(), 18),
            Qt.AlignmentFlag.AlignCenter,
            self._x_label,
        )
        if self._y_label:
            painter.save()
            painter.translate(13, self.height() / 2)
            painter.rotate(-90)
            painter.drawText(
                QRectF(-self.height() / 2, -9, self.height(), 18),
                Qt.AlignmentFlag.AlignCenter,
                self._y_label,
            )
            painter.restore()

    def _draw_fit(self, painter: QPainter, rect: QRectF, ranges) -> None:
        if self._fit is None:
            return
        slope, intercept = self._fit
        x_min, x_max, _y_min, _y_max = ranges
        painter.setPen(QPen(QColor(200, 60, 60), 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(
            self._to_widget(x_min, slope * x_min + intercept, rect, ranges),
            self._to_widget(x_max, slope * x_max + intercept, rect, ranges),
        )

    def _draw_points(self, painter: QPainter, rect: QRectF, ranges) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        for point in self._points:
            colour = (
                _UNGROUPED if point.group is None else _GROUP_COLORS[point.group % len(_GROUP_COLORS)]
            )
            painter.setBrush(colour)
            painter.drawEllipse(
                self._to_widget(point.x, point.y, rect, ranges), self._POINT_RADIUS, self._POINT_RADIUS
            )
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_caption(self, painter: QPainter, rect: QRectF) -> None:
        if not self._caption:
            return
        painter.setPen(QPen(QColor(40, 40, 40)))
        painter.drawText(
            QRectF(rect.left(), 4, rect.width(), self._MARGIN_TOP - 6),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._caption,
        )

    def _draw_hover(self, painter: QPainter, rect: QRectF, ranges) -> None:
        if self._hover_index is None:
            return
        point = self._points[self._hover_index]
        centre = self._to_widget(point.x, point.y, rect, ranges)
        painter.setPen(QPen(QColor(30, 30, 30), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(centre, self._POINT_RADIUS + 3, self._POINT_RADIUS + 3)
        text = point.label or f"({point.x:.4g}, {point.y:.4g})"
        # Flipped to the left of the point near the right edge, so a label
        # on the last molecule is not clipped off the plot.
        width = 200.0
        left = centre.x() + 10 if centre.x() + 10 + width < rect.right() else centre.x() - 10 - width
        painter.setPen(QPen(QColor(20, 20, 20)))
        painter.drawText(
            QRectF(left, centre.y() - 9, width, 18),
            Qt.AlignmentFlag.AlignVCenter
            | (Qt.AlignmentFlag.AlignLeft if left > centre.x() else Qt.AlignmentFlag.AlignRight),
            f"{text}  ({point.x:.4g}, {point.y:.4g})" if point.label else text,
        )


def _padded(low: float, high: float) -> tuple[float, float]:
    if low == high:
        return low - 1.0, high + 1.0
    pad = (high - low) * 0.06
    return low - pad, high + pad


def _tick(value: float) -> str:
    """Four significant figures, which keeps a Wiener index (2534) and a
    QED score (0.5501) both readable on the same kind of axis."""
    return f"{value:.4g}"


def _distance_squared(a: QPointF, b) -> float:
    dx = a.x() - b.x()
    dy = a.y() - b.y()
    return dx * dx + dy * dy
