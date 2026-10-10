"""A host that states the height its content needs at the width it has.

**WHY A WORKFLOW CANNOT SIT IN THE PROPERTIES LIST WITHOUT ONE.** The list is a
`QScrollArea` with `setWidgetResizable`, which sizes its content to
`max(viewport, minimumSizeHint)`. A whole workflow panel (forms that wrap, rows
that flow, labels that wrap, tables, a picture) is height-for-width all the way
down, and for such a chain the minimum a layout READS and the height it
ACTUALLY needs at the width it will get are two different numbers. Measured in
the running app on the alignment section: the section asked for 1102 px, was
given 551, and the layout squeezed its rows to a few pixels to make the content
fit -- the rows overlapped and the picture was cut off, with every individual
widget reporting a perfectly sensible size.

The remedy this repository already settled on for the same family of defect
(`ExplicitHeightLabel`, whose docstring records nine narrower fixes) is to stop
offering height-for-width to the layout above and instead STATE the height as a
plain size hint under a `Fixed` vertical policy, where a hint binds as the
item's minimum, maximum and hint alike. This does it for a whole widget:

* the child keeps all of its own height-for-width behaviour, because it is asked
  for its height at the width this host has been given;
* everything above the host sees a fixed height and no height-for-width flag;
* the stated height is restated whenever the host is resized or the child's
  layout changes (a row shown, a group opened, a label given new text).

It is deliberately dumb: no caching beyond "did the number change", because a
cache here is how a stale height gets stuck.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget


class HeightStatingHost(QWidget):
    """Holds `child` and tells its layout, plainly, how tall `child` needs to be."""

    def __init__(self, child: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._child = child
        self._stated_height = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(child)
        # Fixed vertically: the stated hint is then the item's minimum AND maximum, which
        # is what makes it binding rather than a suggestion the layout may shrink past.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # The child's layout asks to be redone when its content changes; that is the moment
        # the height it needs may have changed, and nothing else tells this host.
        child.installEventFilter(self)

    @property
    def child(self) -> QWidget:
        return self._child

    def stated_height(self) -> int:
        return self._stated_height

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt override
        if watched is self._child and event.type() == QEvent.Type.LayoutRequest:
            self._restate()
        return False

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._restate()

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt override
        """NO -- and this is the line that makes the rest work.

        A widget answers this from its LAYOUT, so a host around a height-for-width
        child would pass the flag straight up, and every layout above would go on
        substituting `heightForWidth` for the minimum -- the squeeze this class exists
        to end. The height is stated instead (`sizeHint`), as a plain number.
        """
        return False

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt override
        return -1

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        hint = super().sizeHint()
        if self._stated_height > 0:
            hint.setHeight(self._stated_height)
        return hint

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        # The child's own minimum WIDTH (so a narrow dock scrolls rather than clips), and
        # the stated height for the height, which a `Fixed` policy would take anyway.
        hint = self._child.minimumSizeHint()
        return QSize(hint.width(), self._stated_height if self._stated_height > 0 else hint.height())

    def _needed_height(self) -> int:
        """The height the child needs at the width this host has, never below its minimum."""
        width = self.width()
        layout = self._child.layout()
        if layout is None:
            return self._child.sizeHint().height()
        floor = layout.minimumSize().height()
        if layout.hasHeightForWidth() and width > 0:
            return max(floor, layout.heightForWidth(width), layout.minimumHeightForWidth(width))
        return max(floor, layout.sizeHint().height())

    def _restate(self) -> None:
        wanted = self._needed_height()
        # Guarded because a new hint makes the layout resize this host, which restates again;
        # with the width unchanged the second pass agrees and it settles.
        if wanted > 0 and wanted != self._stated_height:
            self._stated_height = wanted
            self.updateGeometry()
