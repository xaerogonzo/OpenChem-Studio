"""The small star that says how far a calculator's result can be trusted.

The meaning is `domain/support_marker.py`; this only draws it. Painted rather than a
font glyph: a glyph depends on whichever font the platform falls back to (a missing
one draws a box, which reads as a rendering bug, not a status -- see
`_STATUS_APPEARANCE` in the Properties panel), and a painted shape is the same at any
DPI.

**IT FOLLOWS THE THEME BY BORROWING THE TEXT COLOUR.** The star is the palette's own
foreground at a reduced alpha, so a light and a dark theme need no second table of
colours, and it stays low-contrast. The two non-stable stages are drawn a little
stronger than STABLE: the exception is what a scrolling eye should catch.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from openchem.domain.support_marker import Fill, SupportMarker
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: ONE contract across every rendering, like the status chip's: "how far can I trust
#: this calculator" is one concept. Which stage THIS calculator is in, and why, is
#: appended after it (`StageMarker.set_marker`), so what the inventory holds and what
#: is read are the same text plus a sentence.
STAGE_MARKER_HELP = HelpTooltip(
    text=(
        "How mature this application's implementation of the calculator is. A full star is "
        "Stable (validated for the scope it declares), a half star is Limited (validated "
        "inside a scope that leaves out much of what people draw), an empty star is "
        "Experimental (not yet validated for everyday use).\n\n"
        "It speaks about this implementation, never about the published method. No star "
        "means nobody has declared a stage for the calculator yet, which is not a claim "
        "either way. It changes nothing and runs nothing."
    ),
    tier=2,
    help_id="properties.support_stage",
    topic="results",
)

#: Side of the star's box, in logical pixels. Small on purpose: 14 px once cost seven
#: calculator names their full text in the docked Properties column.
_SIZE = 12
#: Foreground opacity. STABLE recedes; the stages with a caveat are a little firmer.
_ALPHA = {Fill.FULL: 0.5, Fill.HALF: 0.75, Fill.EMPTY: 0.75}


def _star(box: QRectF) -> QPainterPath:
    """A five-pointed star filling `box`."""
    centre = box.center()
    outer = min(box.width(), box.height()) / 2
    inner = outer * 0.42
    path = QPainterPath()
    for index in range(10):
        radius = outer if index % 2 == 0 else inner
        angle = -math.pi / 2 + index * math.pi / 5
        point = QPointF(centre.x() + radius * math.cos(angle), centre.y() + radius * math.sin(angle))
        if index == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path


class StageMarker(QWidget):
    """Draws a `SupportMarker`, or nothing and hidden when there is none.

    `reserve=True` keeps the room when there is none (blank, not hidden). A list that has a
    star on some of its rows would otherwise have those rows' name buttons and status chips
    sit 18 px left of their neighbours'; the rows of a section that has any star all reserve
    the same room, so a section stays aligned and a section with no star is untouched.
    """

    def __init__(self, parent: QWidget | None = None, reserve: bool = False) -> None:
        super().__init__(parent)
        self._reserve = reserve
        self._marker: SupportMarker | None = None
        self.setFixedSize(QSize(_SIZE, _SIZE))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, False)
        apply_help_tooltip(self, STAGE_MARKER_HELP)
        self.set_marker(None)

    def marker(self) -> SupportMarker | None:
        return self._marker

    def fill(self) -> Fill | None:
        return None if self._marker is None else self._marker.fill

    def set_marker(self, marker: SupportMarker | None) -> None:
        """Show `marker`, or hide the widget for None (it then takes no room)."""
        self._marker = marker
        if marker is None:
            # A blank slot says nothing, so it carries no tooltip either.
            self.setToolTip("" if self._reserve else STAGE_MARKER_HELP.text)
            self.setAccessibleName("")
            self.setVisible(self._reserve)
            return
        self.setToolTip(f"{STAGE_MARKER_HELP.text}\n\n{marker.tooltip}")
        self.setAccessibleName(f"Support level: {marker.label}")
        self.setVisible(True)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt's own casing
        if self._marker is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        colour = QColor(self.palette().color(QPalette.ColorRole.WindowText))
        colour.setAlphaF(_ALPHA[self._marker.fill])
        box = QRectF(1.0, 1.0, _SIZE - 2.0, _SIZE - 2.0)
        star = _star(box)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(colour)
        pen.setWidthF(1.0)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        if self._marker.fill is not Fill.EMPTY:
            painter.save()
            if self._marker.fill is Fill.HALF:
                painter.setClipRect(QRectF(0.0, 0.0, _SIZE / 2.0, float(_SIZE)))
            painter.setBrush(colour)
            painter.drawPath(star)
            painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(star)
