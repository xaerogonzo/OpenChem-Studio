"""A layout that wraps onto a new line instead of forcing its parent wide.

**WHY THIS EXISTS, measured.** `MoleculeViewer3DWidget` packed fourteen
controls into one `QHBoxLayout`, and a horizontal layout's minimum width
is the SUM of its children -- 1252 px of controls plus thirteen gaps came
to **1330 px**. That propagated straight up: the central `QStackedWidget`
inherited it, and the main window's own minimum width became 1877-2055 px
depending on which right-hand panel was showing, against a **1920 px**
screen. The window therefore could not be made narrow enough to fit, the
panel rail sat at x=1785..2055 with 135 px past the edge, and switching
panels changed the window's width. Reported as "it will change size, and
even became pretty much inaccessible until I got out of fullscreen".

**`QToolBar` IS NOT THE ANSWER HERE, and it looks like it is.** Its
overflow (`>>`) button only exists for a toolbar in a `QMainWindow`
toolbar area. Used as a plain child widget it drops the items that do not
fit and shows nothing to reach them by -- measured, 8 controls at 320 px
left **1 visible and no extension button**, while the minimum width fell
from 2410 to 115. A 20x improvement that silently loses seven controls is
not an improvement.

Wrapping keeps every control on screen and reachable at any width, which
is the property that matters.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QSizePolicy, QWidget

#: Gaps between items and between wrapped lines. Fixed rather than asked
#: of the style, because `QStyle.layoutSpacing` needs the two widgets'
#: control types and gets consulted from `minimumSize`, where the answer
#: has to be cheap and stable.
_H_SPACING = 6
_V_SPACING = 4


class FlowLayout(QLayout):
    """Left-to-right, wrapping onto a new line when it runs out of width.

    The load-bearing difference from `QHBoxLayout` is `minimumSize`: it
    returns the widest SINGLE item rather than the sum of all of them, so
    a container using it can be made as narrow as its largest control and
    no narrower. Nothing is hidden or clipped -- the content grows
    downwards instead.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list = []
        self.setContentsMargins(0, 0, 0, 0)

    # --- QLayout plumbing ----------------------------------------------

    def addItem(self, item) -> None:  # noqa: N802 - Qt's name
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802 - Qt's name
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):  # noqa: N802 - Qt's name
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:  # noqa: N802
        return Qt.Orientations(Qt.Orientation(0))

    # --- the part that stops the parent being forced wide ---------------

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt's name
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt's name
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt's name
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt's name
        """One line, everything on it -- what the row wants when it can."""
        margins = self.contentsMargins()
        width = height = 0
        for index, item in enumerate(self._items):
            hint = item.sizeHint()
            width += hint.width() + (_H_SPACING if index else 0)
            height = max(height, hint.height())
        return QSize(
            width + margins.left() + margins.right(),
            height + margins.top() + margins.bottom(),
        )

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt's name
        """**The widest single item, NOT the sum.** This one method is the
        whole point of the class -- it is what lets the window shrink."""
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )

    def _arrange(self, rect: QRect, apply: bool) -> int:
        """Place the items, or just compute the height they would need."""
        margins = self.contentsMargins()
        area = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x = area.x()
        y = area.y()
        line_height = 0

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + _H_SPACING
            if next_x - _H_SPACING > area.right() and line_height > 0:
                x = area.x()
                y = y + line_height + _V_SPACING
                next_x = x + hint.width() + _H_SPACING
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()


def flow_row(parent: QWidget | None = None) -> QWidget:
    """A container widget whose children wrap, ready to `addWidget` into.

    Returned as a WIDGET rather than a bare layout because a nested
    layout's `heightForWidth` is not honoured by `QVBoxLayout` -- the
    height policy has to live on a widget for the parent to ask it
    anything. `setHeightForWidth(True)` is what makes the parent grow the
    row taller when it wraps instead of overlapping the widget below.
    """
    row = QWidget(parent)
    row.setLayout(FlowLayout(row))
    policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
    policy.setHeightForWidth(True)
    row.setSizePolicy(policy)
    return row
