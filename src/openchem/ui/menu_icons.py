"""Small drawn icons for the menu entries a person reaches for most.

**DRAWN, NOT SHIPPED, AND NOT A FONT.** Each glyph is a vector path on a 16-unit grid, stroked at one width
with round caps, so the set has one weight and one visual size. Text glyphs and emoji fall back to whichever
font the machine has, and `QStyle`'s standard pixmaps are the window's own (the Qt logo on Windows, the
lesson of the dock layout button), so neither is used.

**THE INK IS READ WHEN THE ICON IS PAINTED.** `GlyphIconEngine` takes the colour from the application
palette at that moment (text, the disabled text, or the highlighted text for a selected entry), so a switch
between Light and Dark needs no rebuild and a disabled command greys by itself.

An icon is decoration on a command that already has a text label. It is never the only name of anything
and nothing here changes a command's id, text or shortcut.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QGuiApplication,
    QIcon,
    QIconEngine,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)

#: The grid every glyph is drawn on.
GRID = 16.0
#: Stroke width on that grid; at the usual 16 px menu icon this is a 1.4 px line.
STROKE = 1.4


def _poly(path: QPainterPath, *points: tuple[float, float]) -> None:
    path.moveTo(*points[0])
    for x, y in points[1:]:
        path.lineTo(x, y)


def _arc(path: QPainterPath, cx: float, cy: float, r: float, start: float, sweep: float) -> None:
    path.arcMoveTo(QRectF(cx - r, cy - r, 2 * r, 2 * r), start)
    path.arcTo(QRectF(cx - r, cy - r, 2 * r, 2 * r), start, sweep)


def _new() -> QPainterPath:
    path = QPainterPath()
    _poly(path, (3.5, 1.5), (9.5, 1.5), (12.5, 4.5), (12.5, 14.5), (3.5, 14.5), (3.5, 1.5))
    _poly(path, (9.5, 1.5), (9.5, 4.5), (12.5, 4.5))
    return path


def _open() -> QPainterPath:
    path = QPainterPath()
    _poly(path, (2, 13.5), (2, 3.5), (6, 3.5), (7.5, 5.5), (13, 5.5), (13, 7))
    _poly(path, (2, 13.5), (3.8, 7), (14.2, 7), (12.5, 13.5), (2, 13.5))
    return path


def _save() -> QPainterPath:
    path = QPainterPath()
    _poly(path, (2.5, 2.5), (11.5, 2.5), (13.5, 4.5), (13.5, 13.5), (2.5, 13.5), (2.5, 2.5))
    _poly(path, (5, 2.5), (5, 6), (10, 6), (10, 2.5))
    _poly(path, (5, 13.5), (5, 9.5), (11, 9.5), (11, 13.5))
    return path


def _turn(direction: int) -> QPainterPath:
    """Undo (-1) and redo (+1): a hook of an arc ending in an arrow head, mirrored."""
    path = QPainterPath()
    x = (lambda v: v) if direction < 0 else (lambda v: GRID - v)
    path.moveTo(x(6.5), 3)
    path.lineTo(x(2.5), 6.5)
    path.lineTo(x(6.5), 10)
    path.moveTo(x(2.5), 6.5)
    path.lineTo(x(9.5), 6.5)
    path.cubicTo(x(13), 6.5, x(13.5), 12, x(9.5), 12.5)
    return path


def _recalculate() -> QPainterPath:
    path = QPainterPath()
    _arc(path, 8, 8.5, 5, 40, 280)
    _poly(path, (9.5, 2.2), (12, 4.2), (8.8, 5.4))
    return path


def _settings() -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(8, 8), 2.2, 2.2)
    path.addEllipse(QPointF(8, 8), 4.4, 4.4)
    for k in range(8):
        # Eight teeth, as short radial strokes outside the ring.
        angle = math.radians(45 * k)
        c, s = math.cos(angle), math.sin(angle)
        path.moveTo(8 + 4.4 * c, 8 + 4.4 * s)
        path.lineTo(8 + 6.4 * c, 8 + 6.4 * s)
    return path


def _exit() -> QPainterPath:
    path = QPainterPath()
    _poly(path, (7, 2.5), (2.5, 2.5), (2.5, 13.5), (7, 13.5))
    _poly(path, (6, 8), (13.5, 8))
    _poly(path, (10.5, 5), (13.5, 8), (10.5, 11))
    return path


def _help() -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(8, 8), 6.5, 6.5)
    path.moveTo(6, 6.3)
    path.cubicTo(6, 3.8, 10, 3.8, 10, 6.3)
    path.cubicTo(10, 8, 8, 8, 8, 9.8)
    path.moveTo(8, 11.6)
    path.lineTo(8, 11.7)
    return path


#: Glyph name -> its path on the 16-unit grid.
GLYPHS = {
    "new": _new,
    "open": _open,
    "save": _save,
    "undo": lambda: _turn(-1),
    "redo": lambda: _turn(+1),
    "recalculate": _recalculate,
    "settings": _settings,
    "exit": _exit,
    "help": _help,
}

#: Menu entry (as `menu_layout.label_of` reads it; a trailing `*` is a prefix, Undo's text follows the stack)
#: -> glyph. Only the commands used most often: the rest stay text-only on purpose.
MENU_GLYPHS = {
    "New Project": "new",
    "Open Project": "open",
    "Save Project": "save",
    "Undo*": "undo",
    "Redo": "redo",
    "Recalculate Now": "recalculate",
    "Settings": "settings",
    "Exit": "exit",
    "Help for the Current Panel": "help",
}


def glyph_for(label: str) -> str | None:
    """The glyph name for a menu label, or None when the entry has no icon."""
    for name, glyph in MENU_GLYPHS.items():
        if name.endswith("*"):
            if label.startswith(name[:-1]):
                return glyph
        elif label == name:
            return glyph
    return None


def _ink(mode: QIcon.Mode) -> QColor:
    palette = QGuiApplication.palette()
    if mode == QIcon.Mode.Disabled:
        return palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText)
    if mode == QIcon.Mode.Selected:
        return palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText)
    return palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText)


class GlyphIconEngine(QIconEngine):
    """Paints one named glyph in the palette's ink at whatever size and pixel ratio it is asked for."""

    def __init__(self, glyph: str) -> None:
        super().__init__()
        self._glyph = glyph

    def clone(self) -> "GlyphIconEngine":
        return GlyphIconEngine(self._glyph)

    def paint(self, painter: QPainter, rect, mode, state) -> None:  # noqa: ANN001 - Qt signature
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(rect.width(), rect.height())
        scale = side / GRID
        painter.translate(rect.x() + (rect.width() - side) / 2, rect.y() + (rect.height() - side) / 2)
        painter.scale(scale, scale)
        pen = QPen(_ink(mode), STROKE)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(GLYPHS[self._glyph]())
        painter.restore()

    def pixmap(self, size: QSize, mode, state) -> QPixmap:  # noqa: ANN001 - Qt signature
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        self.paint(painter, pixmap.rect(), mode, state)
        painter.end()
        return pixmap


def icon(glyph: str) -> QIcon:
    """The icon for a glyph name."""
    if glyph not in GLYPHS:
        raise KeyError(f"no menu glyph named {glyph!r}")
    return QIcon(GlyphIconEngine(glyph))


def apply_to_actions(entries: Iterable[tuple[str, QAction]]) -> int:
    """Give the listed entries their icons. `entries` are (label, action) pairs; returns how many were set."""
    count = 0
    for label, action in entries:
        glyph = glyph_for(label)
        if glyph is not None:
            action.setIcon(icon(glyph))
            count += 1
    return count
