"""A panel's own buttons on its dock's title bar: what they are, and the handle that keeps them current.

A panel declares a button as DATA (`PanelButton`, or `PanelMenuButton` when one press offers a few actions) and the
window hands it to `DockTitleBar.add_button` / `add_menu_button` together with the bound method that does the work.
The title bar builds the control; the panel never learns that it sits in a title bar, so it still works in a window of
its own.

**EVERY ACTION OF A MENU BUTTON HAS ITS OWN CONTRACT AND ITS OWN SLOT.** A menu is not one callback that has to work
out which entry was chosen from state somewhere else.

**A SLOT IS ALWAYS A BOUND METHOD OF A QOBJECT, NEVER A LAMBDA.** PySide6 holds a connected plain callable strongly,
and a closure over the window keeps the whole window alive; this application has paid for that before (see
`DockTitleBar.help_requested`).

The handle is a `QObject` for the same reason: a signal that says "this became available" is connected to its
`set_enabled`, and a bound method of a QObject is held weakly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QStyle, QToolButton

from openchem.ui.widgets.help_tooltip import HelpTooltip


@dataclass(frozen=True)
class PanelButton:
    """One button on a title bar. `name` becomes its objectName (`dockAction_<name>`)."""

    name: str
    accessible: str
    tooltip: HelpTooltip
    #: Shown when there is no `icon`.
    text: str = ""
    icon: QStyle.StandardPixmap | None = None
    #: The state the button starts in. The owner reads the panel's CURRENT state when it registers the button, so a
    #: signal that fired before the title bar existed cannot leave it wrong.
    enabled: bool = True


@dataclass(frozen=True)
class PanelMenuItem:
    """One entry of a `PanelMenuButton`, with its own contract; `key` names it for the slot map."""

    key: str
    text: str
    tooltip: HelpTooltip


@dataclass(frozen=True)
class PanelMenuButton:
    """A title-bar button that opens a menu of a few actions."""

    name: str
    accessible: str
    tooltip: HelpTooltip
    items: tuple[PanelMenuItem, ...]
    text: str = ""
    icon: QStyle.StandardPixmap | None = None
    enabled: bool = True


class PanelActionHandle(QObject):
    """What `add_button` returns: the control, and the one way to change whether it can be pressed."""

    def __init__(self, button: QToolButton, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._button = button

    @property
    def button(self) -> QToolButton:
        return self._button

    @Slot(bool)
    def set_enabled(self, enabled: bool) -> None:
        self._button.setEnabled(bool(enabled))

    def is_enabled(self) -> bool:
        return self._button.isEnabled()


#: What a slot map for a menu button looks like: entry key -> the bound method that runs it.
Slots = dict[str, Callable[[], None]]
