"""A dock title bar with a help button, and the native behaviour kept.

`QDockWidget.setTitleBarWidget` REPLACES the built-in title bar rather
than adding to it, so everything the native one did has to be put back by
hand. That is the whole risk in this file, and each piece is restored
below and covered by tests/test_dock_title_bar.py:

  * the float and close buttons, which simply stop existing;
  * double-click to float, which is a title-bar behaviour;
  * drag to undock, which works only because the label and the widget
    itself ignore mouse presses and let them reach the QDockWidget.

That last one is the subtle one. A `QLabel` does not accept mouse events,
so a press on the title text propagates to the dock and starts a drag. Put
anything that DOES accept them across the full width -- a frame, a styled
container, a stretch made of a clickable widget -- and the dock silently
stops being draggable while looking completely normal.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStyle,
    QToolButton,
    QWidget,
)


class DockTitleBar(QWidget):
    """Title text, a help button, and the float/close buttons put back."""

    help_requested = Signal()

    def __init__(self, dock: QDockWidget, show_help: bool = True) -> None:
        super().__init__(dock)
        self._dock = dock

        self._label = QLabel(dock.windowTitle(), self)
        # Mouse-transparent so a press on the title reaches the dock and
        # starts a drag, exactly as it does on the native title bar.
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 2, 2)
        layout.setSpacing(2)
        layout.addWidget(self._label, 1)

        if show_help:
            self._help_button = self._make_button(
                "?",
                "Help for this panel (F1)",
                self.help_requested.emit,
            )
            layout.addWidget(self._help_button)

        style = self.style()
        self._float_button = self._make_button(
            "",
            "Float or dock this panel",
            self._toggle_floating,
            icon=style.standardIcon(QStyle.StandardPixmap.SP_TitleBarNormalButton),
        )
        layout.addWidget(self._float_button)

        self._close_button = self._make_button(
            "",
            "Close this panel",
            dock.close,
            icon=style.standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton),
        )
        layout.addWidget(self._close_button)

        # A dock whose features change (a plugin panel pinned open, say)
        # must not keep offering buttons that no longer do anything.
        dock.featuresChanged.connect(self._sync_features)
        self._sync_features(dock.features())

    def _make_button(self, text, tooltip, slot, icon=None) -> QToolButton:
        button = QToolButton(self)
        if icon is not None:
            button.setIcon(icon)
            button.setIconSize(QSize(12, 12))
        else:
            button.setText(text)
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(slot)
        return button

    def _toggle_floating(self) -> None:
        self._dock.setFloating(not self._dock.isFloating())

    def _sync_features(self, features: QDockWidget.DockWidgetFeature) -> None:
        self._float_button.setVisible(bool(features & QDockWidget.DockWidgetFeature.DockWidgetFloatable))
        self._close_button.setVisible(bool(features & QDockWidget.DockWidgetFeature.DockWidgetClosable))

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Double-click floats and re-docks, as the native title bar does.

        Only when the dock is floatable, or this silently overrides a
        restriction the dock deliberately set.
        """
        if self._dock.features() & QDockWidget.DockWidgetFeature.DockWidgetFloatable:
            self._toggle_floating()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def setWindowTitle(self, title: str) -> None:  # noqa: N802 - Qt override
        self._label.setText(title)
        super().setWindowTitle(title)
