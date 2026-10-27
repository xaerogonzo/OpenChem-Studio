"""A dock title bar with a help button and a layout menu, and the native behaviour kept.

`QDockWidget.setTitleBarWidget` REPLACES the built-in title bar rather
than adding to it, so everything the native one did has to be put back by
hand. That is the whole risk in this file, and each piece is restored
below and covered by tests/test_dock_title_bar.py:

  * the float and close buttons, which simply stop existing (float now
    lives in the layout menu beside the other ways to place a panel);
  * double-click to float, which is a title-bar behaviour;
  * drag to undock, which works only because the label and the widget
    itself ignore mouse presses and let them reach the QDockWidget.

That last one is the subtle one. A `QLabel` does not accept mouse events,
so a press on the title text propagates to the dock and starts a drag. Put
anything that DOES accept them across the full width -- a frame, a styled
container, a stretch made of a clickable widget -- and the dock silently
stops being draggable while looking completely normal.

**EVERY CONTROL HAS A STABLE `objectName`** (`dockTitleLabel`,
`dockHelpButton`, `dockLayoutButton`, `dockCloseButton`, and a panel's own
buttons under the name they were added with). Tests and the drive harness find
a control by that name: the order of the children changes whenever a panel
adds a button, so a position is not an identity.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QStyle,
    QToolButton,
    QWidget,
)

from openchem.ui.widgets.dock_panel_actions import (
    PanelActionHandle,
    PanelButton,
    PanelMenuButton,
    Slots,
)
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip


#: THREE CONCEPTS, TWELVE RENDERINGS EACH.
#:
#: Every dock builds one of these, so the same buttons appear dozens of
#: times. "Close this panel" means one thing whichever dock it sits on, and
#: WHICH dock is what `DocumentableControl.instance_path` already records --
#: the same call as the sixty batch tick boxes and the thirteen View-menu
#: toggles.
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
    "layout": HelpTooltip(
        text=(
            "Opens this panel's layout menu: move it to another side, show another panel alongside it, "
            "float it into its own window, or put it back on the side it started on."
        ),
        tier=1,
        help_id="workspace.panel_layout",
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


class _ElidingLabel(QLabel):
    """A title that shortens itself with an ellipsis instead of being clipped, and keeps the whole text.

    `QLabel` clips: an Expanding size policy changes how much room it asks for, not what it draws when it gets
    less. The full title stays in `fullText()` for the tooltip and the accessible name. Mouse-transparent, so a
    press on the title still starts a drag of the dock.
    """

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self._full = text
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # Ignored: the layout gives it whatever is left and never asks for the width of the whole title, which
        # is what lets the bar be narrower than its text.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._apply()

    def fullText(self) -> str:  # noqa: N802 - Qt-style, beside text()
        return self._full

    def set_full_text(self, text: str) -> None:
        self._full = text
        self._apply()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(0, super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(QFontMetrics(self.font()).horizontalAdvance(self._full), super().sizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._apply()

    def _apply(self) -> None:
        shown = QFontMetrics(self.font()).elidedText(self._full, Qt.TextElideMode.ElideRight, max(self.width(), 0))
        # Before the first layout the width is 0 and everything would elide to nothing; show the text whole.
        super().setText(self._full if self.width() <= 1 else shown)


class DockTitleBar(QWidget):
    """Title text, the panel's own buttons, a layout menu, a help button and close."""

    #: Carries the help topic, so the listener needs no closure over it.
    #: A `lambda topic=topic: self._show_help(topic)` in MainWindow leaked
    #: the whole window: PySide6 holds a connected plain callable strongly
    #: and a QObject's bound method weakly, so the lambda form survives both
    #: refcounting and the cyclic collector. Putting the payload in the
    #: signal is what lets the receiver connect a bound method.
    help_requested = Signal(str)

    #: Asks whoever owns the layout to fill the menu for `(dock, menu)`, each time it is about to open. With no
    #: listener the menu offers only Float panel, which is all a dock on its own can do.
    layout_menu_requested = Signal(object, object)

    def __init__(self, dock: QDockWidget, show_help: bool = True, help_topic: str = "") -> None:
        super().__init__(dock)
        self._dock = dock
        self._help_topic = help_topic
        self.setObjectName("dockTitleBar")

        self._label = _ElidingLabel(dock.windowTitle(), self)
        self._label.setObjectName("dockTitleLabel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 2, 2)
        layout.setSpacing(2)
        layout.addWidget(self._label, 1)
        #: Where `add_control` inserts: after the title, before the dock's
        #: own buttons, so a panel's controls never separate the layout
        #: menu, help and close.
        self._layout = layout
        self._controls_end = 1

        style = self.style()
        # A TEXT ellipsis, not a standard icon. `SP_TitleBarMenuButton` is the WINDOW's own icon on Windows -- in the
        # real window it drew the Qt logo, which no offscreen test could have shown -- and text follows the palette
        # in a light or a dark window without painting anything.
        self._layout_button = self._make_button(
            "…",
            _HELP["layout"],
            None,
            name="dockLayoutButton",
            accessible="Panel layout",
        )
        self._menu = QMenu(self)
        self._menu.setObjectName("dockLayoutMenu")
        self._menu.aboutToShow.connect(self._fill_menu)
        self._layout_button.setMenu(self._menu)
        self._layout_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        layout.addWidget(self._layout_button)

        self._help_button: QToolButton | None = None
        if show_help:
            self._help_button = self._make_button(
                "?",
                _HELP["help"],
                self._emit_help_requested,
                name="dockHelpButton",
                accessible="Help for this panel",
            )
            layout.addWidget(self._help_button)

        self._close_button = self._make_button(
            "",
            _HELP["close"],
            dock.close,
            icon=style.standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton),
            name="dockCloseButton",
            accessible="Close this panel",
        )
        layout.addWidget(self._close_button)

        # A dock whose features change (a plugin panel pinned open, say)
        # must not keep offering buttons that no longer do anything.
        dock.featuresChanged.connect(self._sync_features)
        self._sync_features(dock.features())
        self._announce_title(dock.windowTitle())

    # --- the panel's own controls ----------------------------------------------------------------

    def add_control(self, widget: QWidget) -> None:
        """Put one of the PANEL's controls in its title bar, before the dock's own.

        For an action on the panel's whole view that would otherwise cost a
        row inside it -- the Results reader's pop-out button, measured at 26
        of the 190 px a top-docked reader had. The widget is reparented here
        and keeps its own contract and handler. Like the dock's own buttons
        it takes no focus, so a click does not pull focus out of whatever
        the user was typing in.
        """
        widget.setParent(self)
        widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._layout.insertWidget(self._controls_end, widget)
        self._controls_end += 1

    def add_button(self, spec: PanelButton, slot) -> PanelActionHandle:
        """Put a panel's button in the bar (see `dock_panel_actions`). `slot` is a bound method of a QObject."""
        button = self._make_button(
            spec.text, spec.tooltip, slot, name=f"dockAction_{spec.name}", accessible=spec.accessible,
            icon=self.style().standardIcon(spec.icon) if spec.icon is not None else None,
        )
        button.setEnabled(spec.enabled)
        self.add_control(button)
        return PanelActionHandle(button, self)

    def add_menu_button(self, spec: PanelMenuButton, slots: Slots) -> PanelActionHandle:
        """Put a panel's menu button in the bar; each entry has its own contract and its own slot."""
        button = self._make_button(
            spec.text, spec.tooltip, None, name=f"dockAction_{spec.name}", accessible=spec.accessible,
            icon=self.style().standardIcon(spec.icon) if spec.icon is not None else None,
        )
        menu = QMenu(button)
        menu.setObjectName(f"dockActionMenu_{spec.name}")
        for item in spec.items:
            action = menu.addAction(item.text)
            action.setObjectName(f"dockActionItem_{spec.name}_{item.key}")
            apply_help_tooltip(action, item.tooltip)
            action.triggered.connect(slots[item.key])
        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setEnabled(spec.enabled)
        self.add_control(button)
        return PanelActionHandle(button, self)

    def layout_menu(self) -> QMenu:
        """The menu behind the layout button, for the window that connects to its `triggered`."""
        return self._menu

    def close_button(self) -> QToolButton:
        return self._close_button

    def help_button(self) -> QToolButton | None:
        return self._help_button

    def layout_button(self) -> QToolButton:
        return self._layout_button

    # --- the layout menu -------------------------------------------------------------------------

    def _fill_menu(self) -> None:
        """Empty the menu, including the submenus the last filling made, and ask for the current one.

        `QMenu.clear` removes the actions but leaves a submenu made with `addMenu` parented to the menu, so
        without this each opening would leave one more behind.
        """
        for child in self._menu.findChildren(QMenu, options=Qt.FindChildOption.FindDirectChildrenOnly):
            child.setParent(None)
            child.deleteLater()
        self._menu.clear()
        self.layout_menu_requested.emit(self._dock, self._menu)
        if self._menu.isEmpty():
            action = self._menu.addAction("Dock panel back" if self._dock.isFloating() else "Float panel")
            action.setObjectName("dockMenu_float")
            action.triggered.connect(self._toggle_floating)

    def _emit_help_requested(self) -> None:
        self.help_requested.emit(self._help_topic)

    def _make_button(
        self, text, help_tooltip: HelpTooltip, slot, icon=None, name: str = "", accessible: str = ""
    ) -> QToolButton:
        """Takes a CONTRACT rather than a string.

        The layout and close buttons carry an icon and no text, so a user
        with no tooltip has nothing at all to go on -- which is why these
        were among the first things given raw tooltips, and why the
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
        if name:
            button.setObjectName(name)
        if accessible:
            button.setAccessibleName(accessible)
        if slot is not None:
            button.clicked.connect(slot)
        return button

    def _toggle_floating(self) -> None:
        self._dock.setFloating(not self._dock.isFloating())

    def _sync_features(self, features: QDockWidget.DockWidgetFeature) -> None:
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
        self._label.set_full_text(title)
        self._announce_title(title)
        super().setWindowTitle(title)

    def _announce_title(self, title: str) -> None:
        """The whole title, for a screen reader and for a hover when it has been shortened."""
        self.setAccessibleName(title)
        self.setToolTip(title)
