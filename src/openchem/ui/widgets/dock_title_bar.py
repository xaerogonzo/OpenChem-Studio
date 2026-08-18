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

from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip


#: THREE CONCEPTS, TWELVE RENDERINGS EACH.
#:
#: Every dock builds one of these, so the same three buttons appear
#: thirty-six times. "Close this panel" means one thing whichever dock it
#: sits on, and WHICH dock is what `DocumentableControl.instance_path`
#: already records -- the same call as the sixty batch tick boxes and the
#: thirteen View-menu toggles.
_HELP = {
    "help": HelpTooltip(
        text=(
            "Opens the manual at this panel's own topic.\n\n"
            "F1 does the same for whichever panel is in front, so this button "
            "is the way to ask about a panel without focusing it first."
        ),
        tier=1,
        help_id="workspace.panel_help",
        topic="panels",
        help_anchor="in-app-help",
    ),
    "float": HelpTooltip(
        text=(
            "Detaches this panel into its own window, or puts it back.\n\n"
            "A floating panel can be moved off the main window entirely, which "
            "is what makes two panels visible at once -- docked, one right-hand "
            "panel shows at a time."
        ),
        tier=1,
        help_id="workspace.panel_float",
        topic="panels",
        help_anchor="properties",
    ),
    "close": HelpTooltip(
        text=(
            "Hides this panel. Nothing is discarded -- results already computed "
            "stay with their molecule -- and the panel comes back from the rail "
            "or the View menu."
        ),
        tier=1,
        help_id="workspace.panel_close",
        topic="panels",
        help_anchor="properties",
    ),
}


class DockTitleBar(QWidget):
    """Title text, a help button, and the float/close buttons put back."""

    #: Carries the help topic, so the listener needs no closure over it.
    #: A `lambda topic=topic: self._show_help(topic)` in MainWindow leaked
    #: the whole window: PySide6 holds a connected plain callable strongly
    #: and a QObject's bound method weakly, so the lambda form survives both
    #: refcounting and the cyclic collector. Putting the payload in the
    #: signal is what lets the receiver connect a bound method.
    help_requested = Signal(str)

    def __init__(self, dock: QDockWidget, show_help: bool = True, help_topic: str = "") -> None:
        super().__init__(dock)
        self._dock = dock
        self._help_topic = help_topic

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
                _HELP["help"],
                self._emit_help_requested,
            )
            layout.addWidget(self._help_button)

        style = self.style()
        self._float_button = self._make_button(
            "",
            _HELP["float"],
            self._toggle_floating,
            icon=style.standardIcon(QStyle.StandardPixmap.SP_TitleBarNormalButton),
        )
        layout.addWidget(self._float_button)

        self._close_button = self._make_button(
            "",
            _HELP["close"],
            dock.close,
            icon=style.standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton),
        )
        layout.addWidget(self._close_button)

        # A dock whose features change (a plugin panel pinned open, say)
        # must not keep offering buttons that no longer do anything.
        dock.featuresChanged.connect(self._sync_features)
        self._sync_features(dock.features())

    def _emit_help_requested(self) -> None:
        self.help_requested.emit(self._help_topic)

    def _make_button(self, text, help_tooltip: HelpTooltip, slot, icon=None) -> QToolButton:
        """Takes a CONTRACT rather than a string.

        The float and close buttons carry an icon and no text, so a user
        with no tooltip has nothing at all to go on -- which is why these
        three were among the first things given raw tooltips, and why the
        contract has to reach them rather than stopping at the panels.
        """
        button = QToolButton(self)
        if icon is not None:
            button.setIcon(icon)
            button.setIconSize(QSize(12, 12))
        else:
            button.setText(text)
        apply_help_tooltip(button, help_tooltip)
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
