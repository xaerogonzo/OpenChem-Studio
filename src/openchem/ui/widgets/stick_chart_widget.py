"""A declared stick chart, drawn. Knows no chemistry.

The third stick plot in this application and the first that renders a
DECLARED ANNOTATION rather than a domain result. `NmrSpectrumWidget` takes
`NMRSignal`s and knows about multiplets and residual solvent peaks;
`IrSpectrumWidget` takes `VibrationalMode`s and knows about silent modes
and imaginary frequencies. This one takes positions, heights and labels
somebody else computed, and its whole job is to put them on screen without
changing them.

**IT NEVER RENORMALISES, REORDERS OR RELABELS.** The producer decided what
`y` means and `y_units` says so; the tallest stick is mapped to the plot
height for display and the REAL maximum is printed beside it, which is what
stops a display scaling from reading as a calibrated axis. Producer order
is preserved so a hit test resolves first-match-wins.

**A MALFORMED ANNOTATION IS REFUSED, NEVER REPAIRED.** `set_annotation`
runs `valid_chart_annotation` and, on failure, draws nothing and logs --
sorting, clamping or normalising it into shape would put a picture built
from repaired nonsense on the screen, and a picture reads as a result.

The axis mechanics come from `plot_axis`, shared with nothing yet: NMR and
IR are deliberately left alone -- see that module's header for why.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from openchem.domain.report import StickChartAnnotation, valid_chart_annotation
from openchem.ui.widgets.plot_axis import (
    LABEL_HEIGHT,
    MARGIN,
    hit_regions,
    padded_range,
    plot_rect,
    to_widget_x,
)

logger = logging.getLogger("openchem.ui")

#: The axis, its ticks and its labels. The same grey both existing spectrum
#: widgets use, so a third plot reads as their sibling.
_AXIS_COLOR = QColor(120, 120, 120)

#: The sticks themselves, and the same blue for the same reason.
_STICK_COLOR = QColor(30, 100, 200)

#: The producer's caption under the plot. Deliberately quieter than the
#: data: it qualifies the picture rather than competing with it.
_CAPTION_COLOR = QColor(110, 110, 110)

#: How tall a stick must be before its own label is drawn on it, as a
#: multiple of `LABEL_HEIGHT`. Below this the text would overlap the axis
#: or its neighbours, and a label sitting on the wrong stick is worse than
#: no label -- `IrSpectrumWidget` draws the line in the same place.
_LABEL_CLEARANCE = 1.5

#: Lines of room reserved under the plot for the caption when there is one.
#: Two, because every caption written for this so far is a sentence rather
#: than a phrase.
_CAPTION_LINES = 2

#: How far apart a single stick's axis is opened out, so a one-peak chart
#: is not a zero-width axis. In m/z this is about one isotope spacing,
#: which keeps such a chart looking like a spectrum rather than one bar.
_MINIMUM_SPAN = 2.0


class StickChartWidget(QWidget):
    """One `StickChartAnnotation`, painted."""

    #: The index of the stick that was clicked, into `annotation.sticks`.
    #: An INDEX rather than the `Stick` itself, because two sticks can be
    #: equal by value and a consumer usually wants to know which one.
    stick_clicked = Signal(int)

    def __init__(
        self,
        annotation: StickChartAnnotation | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._annotation: StickChartAnnotation | None = None
        # Enough for the plot, its margins and a caption. NOT a
        # `heightForWidth`: this is embedded in a `QScrollArea` with
        # `setWidgetResizable(True)`, and those two mechanisms fighting is
        # a defect this project has now paid for three times.
        self.setMinimumSize(240, 160)
        if annotation is not None:
            self.set_annotation(annotation)

    # --- what it is showing --------------------------------------------------

    def set_annotation(self, annotation: StickChartAnnotation | None) -> None:
        if annotation is not None and not valid_chart_annotation(annotation):
            logger.warning("Refusing to draw a malformed chart annotation: %r", annotation)
            annotation = None
        self._annotation = annotation
        self.updateGeometry()
        self.update()

    def annotation(self) -> StickChartAnnotation | None:
        return self._annotation

    def is_drawing(self) -> bool:
        """Whether there is an annotation this widget accepted.

        Exposed so a caller (and a test) can tell "nothing was declared"
        from "something was declared and refused" without reading the log.
        """
        return self._annotation is not None

    # --- geometry ------------------------------------------------------------

    def _caption_height(self) -> float:
        if self._annotation is None or not self._annotation.caption:
            return 0.0
        return _CAPTION_LINES * self.fontMetrics().height()

    def _plot_rect(self) -> QRectF:
        """The drawing area, shortened by whatever the caption needs.

        Measured from the widget's OWN height rather than clipped against
        it: this project once dropped 22 of polonium's 84 electrons with
        `if y + row_height > self.height(): break`, green the whole time.
        Nothing here truncates -- a widget too short for its content draws
        a short plot, and the scroll area handles the excess.
        """
        rect = plot_rect(float(self.width()), float(self.height()))
        caption = self._caption_height()
        if caption:
            return QRectF(
                rect.left(), rect.top(), rect.width(), max(rect.height() - caption, 1.0)
            )
        return rect

    def _x_range(self) -> tuple[float, float]:
        if self._annotation is None:
            return 0.0, 1.0
        return padded_range(
            [stick.x for stick in self._annotation.sticks], minimum_span=_MINIMUM_SPAN
        )

    def hit_regions(self) -> list[QRectF]:
        """One clickable band per stick, in the producer's order.

        Derived from geometry rather than recorded during `paintEvent`, so
        a click resolves before the first paint and is testable without one
        -- both existing spectrum widgets say the same.
        """
        if self._annotation is None:
            return []
        return hit_regions(
            [stick.x for stick in self._annotation.sticks],
            self._plot_rect(),
            self._x_range(),
            self._annotation.x_descending,
        )

    def stick_index_at(self, x: float, y: float) -> int | None:
        """First match wins, in producer order -- two sticks can share an x
        (two isotopologues in one nominal bin), so the regions do overlap
        and the rule has to be stated rather than left to chance."""
        for index, region in enumerate(self.hit_regions()):
            if region.contains(x, y):
                return index
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        position = event.position()
        index = self.stick_index_at(position.x(), position.y())
        if index is not None:
            self.stick_clicked.emit(index)
        super().mousePressEvent(event)

    # --- painting ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        annotation = self._annotation
        rect = self._plot_rect()

        painter.setPen(QPen(_AXIS_COLOR))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if annotation is None:
            # An axis and nothing on it. A refused annotation and no
            # annotation look the same here deliberately -- the log says
            # which, and inventing an error graphic would be this widget
            # claiming to know why.
            return

        painter.drawText(
            QRectF(0, rect.bottom() + MARGIN / 4, float(self.width()), MARGIN / 2),
            Qt.AlignmentFlag.AlignCenter,
            axis_caption(annotation.x_label, annotation.x_units),
        )
        if annotation.title:
            painter.drawText(
                QRectF(rect.left(), 0, rect.width(), MARGIN / 2),
                Qt.AlignmentFlag.AlignCenter,
                annotation.title,
            )

        low, high = self._x_range()
        left_value, right_value = (high, low) if annotation.x_descending else (low, high)
        painter.drawText(
            QRectF(rect.left(), rect.bottom(), 70, MARGIN / 4),
            Qt.AlignmentFlag.AlignLeft,
            f"{left_value:.4g}",
        )
        painter.drawText(
            QRectF(rect.right() - 70, rect.bottom(), 70, MARGIN / 4),
            Qt.AlignmentFlag.AlignRight,
            f"{right_value:.4g}",
        )

        # **THE REAL MAXIMUM, PRINTED.** The tallest stick is mapped to the
        # plot height so the picture uses the space it has; without the
        # number beside it that mapping reads as a calibrated axis.
        heights = [stick.y for stick in annotation.sticks]
        peak = max(heights)
        scale = max(abs(value) for value in heights) or 1.0
        painter.drawText(
            QRectF(rect.left(), rect.top() - LABEL_HEIGHT, 240, LABEL_HEIGHT),
            Qt.AlignmentFlag.AlignLeft,
            f"max {peak:.4g}"
            + (f" {annotation.y_units}" if annotation.y_units else "")
            + f" -- {annotation.y_label}",
        )

        available = rect.height() - LABEL_HEIGHT
        painter.setPen(QPen(_STICK_COLOR))
        for stick in annotation.sticks:
            x = to_widget_x(stick.x, rect, (low, high), annotation.x_descending)
            height = available * (stick.y / scale)
            painter.drawLine(
                QPointF(x, rect.bottom() - height), QPointF(x, rect.bottom())
            )
            if stick.label and abs(height) > LABEL_HEIGHT * _LABEL_CLEARANCE:
                painter.drawText(
                    QRectF(x - 45, rect.bottom() - height - LABEL_HEIGHT, 90, LABEL_HEIGHT),
                    Qt.AlignmentFlag.AlignCenter,
                    stick.label,
                )

        if annotation.caption:
            painter.setPen(QPen(_CAPTION_COLOR))
            painter.drawText(
                QRectF(
                    MARGIN / 2,
                    rect.bottom() + MARGIN * 0.75,
                    max(self.width() - MARGIN, 1.0),
                    self._caption_height(),
                ),
                int(Qt.AlignmentFlag.AlignHCenter)
                | int(Qt.AlignmentFlag.AlignTop)
                | int(Qt.TextFlag.TextWordWrap),
                annotation.caption,
            )


def axis_caption(label: str, units: str) -> str:
    """`"m/z"`, or `"Relative abundance (%)"` -- the `Fact.value`/`Fact.units`
    split, composed for display in the one place that displays it."""
    return f"{label} ({units})" if units else label
