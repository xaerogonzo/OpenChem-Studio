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

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
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

#: The shortest the plot itself may be, in pixels, before a caption is
#: accounted for. `minimumSizeHint` adds the caption's own measured height
#: to this rather than taking it out of the plot.
_MINIMUM_PLOT_HEIGHT = 160

#: Least room reserved under the plot for a caption, in lines. The real
#: height is MEASURED against the available width -- see `_caption_height`
#: -- because assuming a line count truncates the sentence, and a caption
#: that says a spectrum is CALCULATED is the wrong thing to cut in half.
_MINIMUM_CAPTION_LINES = 2

#: Most room a caption may take, as a fraction of the widget's height. A
#: long caption must not squeeze the plot to nothing; past this it is
#: elided, which is visibly different from being silently clipped.
_MAXIMUM_CAPTION_FRACTION = 0.4

#: How far apart a single stick's axis is opened out, so a one-peak chart
#: is not a zero-width axis. In m/z this is about one isotope spacing,
#: which keeps such a chart looking like a spectrum rather than one bar.
_MINIMUM_SPAN = 2.0


def minimum_height(base_height: float, caption_height: float) -> float:
    """The plot's minimum floor, PLUS the caption, never absorbing it.

    Pure, and separated from the widget for one reason: the two ways to
    write this differ only when `base_height` exceeds the floor, and a
    painted widget with no children reports a `base_height` near zero --
    so `max(base, FLOOR + caption)` is INDISTINGUISHABLE from the correct
    form through the widget today, and would silently reinstate the
    collapsed plot the day this gains a child or a layout.

    An unreachable branch is a question about where to assert, so it is
    asserted here over a table that includes a large base.
    """
    return max(base_height, _MINIMUM_PLOT_HEIGHT) + caption_height


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
        show_title: bool = True,
    ) -> None:
        super().__init__(parent)
        #: **OFF WHERE SOMETHING ELSE ALREADY SHOWS THE TITLE.** Inside a
        #: `FactView` the collapsible section's own header IS the chart's
        #: title, so painting it again put the same words twice on screen
        #: -- and the in-plot copy landed on top of the tallest stick's
        #: label. Found by magnifying the shot; nothing asserts that two
        #: pieces of text do not occupy one rectangle.
        self._show_title = show_title
        self._annotation: StickChartAnnotation | None = None
        # Enough for the plot and its margins. The CAPTION is added on top
        # of this in `minimumSizeHint` -- see there.
        self.setMinimumSize(240, _MINIMUM_PLOT_HEIGHT)
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

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt's own casing
        """The plot's minimum PLUS whatever the caption needs.

        **A WIDGET THAT DOES NOT ADD ITS CAPTION IS A WIDGET WHOSE PLOT
        DISAPPEARS.** Measured by driving the app: once the caption was
        fixed to render in full it wrapped to three lines, and with the
        minimum still at a flat 160 the section handed over exactly that
        -- so the caption took most of it and the sticks collapsed onto
        the axis. Every test stayed green, because none of them asserts
        that a plot has room to be a plot.

        Same shape as `WrappedLabel`, which exists in this codebase
        because a wrapped `QLabel` reports a one-line minimum however much
        text it holds.

        **STILL NO `heightForWidth`.** This is a plain minimum, so the
        scroll area's `setWidgetResizable(True)` has nothing to fight
        with -- which is the mechanism this project has lost three times.
        """
        base = super().minimumSizeHint()
        return QSize(
            max(base.width(), 240),
            int(minimum_height(float(base.height()), self._caption_height())),
        )

    def _caption_height(self) -> float:
        """How tall the caption really is at this width.

        **MEASURED, NOT ASSUMED.** A fixed two-line reservation cut the
        mass-spectrum caption mid-sentence -- "...what an instrument
        records: ion" -- with every test green, because nothing asserts
        where a wrapped string ends. Found by magnifying the shot.

        Bounded above so a long caption cannot squeeze the plot away, and
        below so a one-line caption still sits clear of the axis label.
        """
        if self._annotation is None or not self._annotation.caption:
            return 0.0
        metrics = self.fontMetrics()
        width = max(self.width() - MARGIN, 1.0)
        needed = metrics.boundingRect(
            QRectF(0, 0, width, 10_000).toRect(),
            int(Qt.TextFlag.TextWordWrap),
            self._annotation.caption,
        ).height()
        return max(float(needed), _MINIMUM_CAPTION_LINES * metrics.height())

    def _plot_rect(self) -> QRectF:
        """The drawing area, shortened by whatever the caption needs.

        Measured from the widget's OWN height rather than clipped against
        it: this project once dropped 22 of polonium's 84 electrons with
        `if y + row_height > self.height(): break`, green the whole time.
        Nothing here truncates -- a widget too short for its content draws
        a short plot, and the scroll area handles the excess.
        """
        rect = plot_rect(float(self.width()), float(self.height()))
        caption = self._room_for_caption()
        if caption:
            return QRectF(
                rect.left(), rect.top(), rect.width(), max(rect.height() - caption, 1.0)
            )
        return rect

    def _room_for_caption(self) -> float:
        """What the caption is GIVEN, which is not always what it asked for.

        **THE CAP IS A RUNTIME SAFETY, NOT PART OF THE MINIMUM.**
        `minimumSizeHint` asks for the caption's full measured height ON
        TOP of the plot's, so at or above that height this returns the
        measurement unchanged. It only bites when a caller has squeezed
        the widget below its own minimum, and then it stops a long caption
        taking the whole surface.

        Capping inside `_caption_height` instead made the two chase each
        other -- the hint set a height, the height capped the caption, the
        smaller caption changed the hint. Separating the MEASUREMENT from
        the ALLOCATION is what breaks that loop.

        One place, so painting and hit-testing cannot disagree about where
        the axis is.
        """
        return min(
            self._caption_height(),
            _MAXIMUM_CAPTION_FRACTION * max(float(self.height()), 1.0),
        )

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
        if annotation.title and self._show_title:
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
        # **"max 1" IS NOT A READOUT.** A base-peak-normalised chart has a
        # maximum of exactly 1 by definition, so printing it told the
        # reader nothing and used the space the axis name wanted. The
        # number appears only when it carries information -- which is when
        # the producer did NOT normalise.
        readout = axis_caption(annotation.y_label, annotation.y_units)
        if abs(peak - 1.0) > 1e-9:
            readout = f"max {peak:.4g} -- " + readout
        painter.drawText(
            QRectF(rect.left(), rect.top() - LABEL_HEIGHT, 300, LABEL_HEIGHT),
            Qt.AlignmentFlag.AlignLeft,
            readout,
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
                    max(float(self.height()) - rect.bottom() - MARGIN * 0.75, 1.0),
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
