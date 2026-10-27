"""The layout menu on every panel's title bar, built from plain state.

`populate_layout_menu` takes a `DockMenuState` -- everything the menu needs to know about one dock, read by the
window at the moment the menu opens -- and fills a `QMenu`, returning its actions by a stable name. It executes
nothing and reaches no window: the rail's `build_panel_menu` is built the same way, so a test can drive the menu
without a popup (`QMenu.exec` is modal and cannot be patched).

Every action carries `(kind, dock, argument)` in its `data()`, and the window handles the whole menu with ONE
bound method that reads it. A lambda closing over the window here would root it: PySide6 holds a connected plain
callable strongly, and this window has paid for that before (see `DockTitleBar.help_requested`).

**The menu is filled each time it opens**, never kept. The side a dock is on, whether it floats, whether it is
locked, which panels exist (a plugin can unload between two openings) are all facts of the moment.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: The four sides, in the order the Move menu lists them.
SIDES: tuple[str, ...] = ("left", "right", "top", "bottom")

#: What each side is called in the Move to menu.
SIDE_LABELS: dict[str, str] ={"left": "Left", "right": "Right", "top": "Top", "bottom": "Bottom"}

#: Qt's own area for each side, for the window that has to hand one to `addDockWidget`.
SIDE_AREAS: dict[str, Qt.DockWidgetArea] = {
    "left": Qt.DockWidgetArea.LeftDockWidgetArea,
    "right": Qt.DockWidgetArea.RightDockWidgetArea,
    "top": Qt.DockWidgetArea.TopDockWidgetArea,
    "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
}


def side_of(area: Qt.DockWidgetArea) -> str:
    """The side an area names, or "none" for a dock that is not in the layout."""
    for side, value in SIDE_AREAS.items():
        if area == value:
            return side
    return "none"


#: One entry per menu item. Tier 1 -- each says what pressing it does -- and every one shares the panels topic.
_HELP: dict[str, HelpTooltip] = {
    "move": HelpTooltip(
        text=(
            "Moves this panel to the left, right, top or bottom of the window. Where you put it is "
            "remembered, and the panel rail stops hiding it when you pick another panel."
        ),
        tier=1,
        help_id="workspace.panel_move",
        topic="panels",
        help_anchor="properties",
    ),
    "expand": HelpTooltip(
        text=(
            "Makes this panel as large as the window allows along the side it sits on. The editor keeps its "
            "minimum size and the other panels shrink to theirs; Restore size puts every panel back."
        ),
        tier=1,
        help_id="workspace.panel_expand",
        topic="panels",
        help_anchor="properties",
    ),
    "restore": HelpTooltip(
        text="Puts every panel back at the size it had before Expand panel.",
        tier=1,
        help_id="workspace.panel_restore_size",
        topic="panels",
        help_anchor="properties",
    ),
    "alongside": HelpTooltip(
        text=(
            "Shows another panel without hiding this one. It does not arrange the two side by side: they "
            "share the window the way any two panels you have opened do."
        ),
        tier=1,
        help_id="workspace.panel_alongside",
        topic="panels",
        help_anchor="properties",
    ),
    "lock": HelpTooltip(
        text=(
            "Keeps this panel on screen when you pick a different panel in the rail, or lets the rail replace "
            "it again. It does not move the panel."
        ),
        tier=1,
        help_id="workspace.panel_lock",
        topic="panels",
        help_anchor="properties",
    ),
    "float": HelpTooltip(
        text=(
            "Detaches this panel into its own window, or puts it back in the main window. A floating panel "
            "can be moved off the main window entirely, which is what makes two panels visible at once."
        ),
        tier=1,
        help_id="workspace.panel_float",
        topic="panels",
        help_anchor="properties",
    ),
    "return": HelpTooltip(
        text=(
            "Puts this panel back on the side it started on. Its size and its place among other panels are "
            "not restored, and no other panel is touched."
        ),
        tier=1,
        help_id="workspace.panel_default_side",
        topic="panels",
        help_anchor="properties",
    ),
}


@dataclass(frozen=True)
class DockMenuState:
    """What the menu needs to know about one dock, read when the menu opens."""

    dock: str
    floating: bool
    #: "left" / "right" / "top" / "bottom", or "none" for a dock with no place in the layout (floating, hidden).
    side: str
    movable: bool
    floatable: bool
    #: The sides `allowedAreas()` permits.
    allowed: tuple[str, ...]
    #: Other panels this one can be shown beside: (panel id, label). Never the dock itself.
    targets: tuple[tuple[str, str], ...] = ()
    #: Whether the rail treats this panel as locked open; `None` when it is not a rail panel.
    locked: bool | None = None
    default_side: str = "right"
    #: False when the recorded side is no longer one the dock may be docked on.
    default_side_legal: bool = True
    #: False only when returning would change nothing (docked, in its default side, not placed, alone).
    return_enabled: bool = True
    return_reason: str = ""
    #: "expand", "restore" or "" (not offered).
    expand: str = ""
    expand_enabled: bool = True
    expand_reason: str = ""


def populate_layout_menu(menu: QMenu, state: DockMenuState) -> dict[str, QAction]:
    """Fill `menu` for `state`; return its actions by stable name.

    The caller clears the menu first (and deletes the submenus the previous filling made).
    """
    actions: dict[str, QAction] = {}

    def make(parent: QMenu, key: str, text: str, kind: str, argument: str = "", *, enabled: bool = True,
             tip: str = "", contract: str | None = None) -> QAction:
        action = parent.addAction(text)
        action.setObjectName(f"dockMenu_{key.replace(':', '_')}")
        action.setData((kind, state.dock, argument))
        action.setEnabled(enabled)
        if contract is not None:
            apply_help_tooltip(action, _HELP[contract])
        if tip:
            # The reason a disabled entry is disabled, which beats a plain tooltip's description of it.
            action.setToolTip(tip)
            action.setStatusTip(tip)
        actions[key] = action
        return action

    if state.movable and state.allowed:
        move = menu.addMenu("Move to")
        move.setObjectName("dockMenu_move")
        move.menuAction().setObjectName("dockMenu_move_menu")
        apply_help_tooltip(move.menuAction(), _HELP["move"])
        for side in SIDES:
            if side not in state.allowed:
                continue
            here = state.side == side and not state.floating
            make(move, f"move:{side}", SIDE_LABELS[side], "move", side, enabled=not here,
                 tip="It is already on this side." if here else "")
        actions["move"] = move.menuAction()

    if state.expand:
        text = "Restore size" if state.expand == "restore" else "Expand panel"
        make(menu, state.expand, text, state.expand, enabled=state.expand_enabled,
             tip=state.expand_reason, contract=state.expand)

    if state.targets:
        beside = menu.addMenu("Show alongside")
        beside.setObjectName("dockMenu_alongside")
        beside.menuAction().setObjectName("dockMenu_alongside_menu")
        apply_help_tooltip(beside.menuAction(), _HELP["alongside"])
        for panel_id, label in state.targets:
            make(beside, f"alongside:{panel_id}", label, "alongside", panel_id)
        actions["alongside"] = beside.menuAction()

    if state.locked is not None:
        make(menu, "lock", "Unlock" if state.locked else "Lock open", "lock", contract="lock")

    menu.addSeparator()

    if state.floating:
        # Always offered whatever the features say, so a capability change can never leave a floating panel
        # with no way back into the window.
        make(menu, "dock_back", "Dock panel back", "dock_back", contract="float")
    elif state.floatable:
        make(menu, "float", "Float panel", "float", contract="float")

    reason = state.return_reason
    if not state.default_side_legal:
        reason = "This panel can no longer be docked on the side it started on."
    make(menu, "return", "Return to default side", "return",
         enabled=state.default_side_legal and state.return_enabled, tip=reason, contract="return")
    return actions
