"""Expand panel / Restore size: grow one dock as far as the window allows, and put every dock back.

**WHAT IT IS, AND IS NOT.** A dock grows along the axis it docks on -- width for a left or right dock, height for a top
or bottom one -- until the editor in the middle reaches its own minimum and the other docks reach theirs. It is a
resize, not a mode: nothing is hidden, so there is nothing to un-hide. A full-window focus mode is a different
feature.

**MEASURED, NOT ASSUMED** (the real Windows platform, a 1366 px window, the default layout; kept in
`docs/DOCK_LAYOUT_DESIGN.md`):

* `resizeDocks` on ONE dock moves OTHERS too. Expanding Properties from 420 to 563 px took the Project Explorer from
  264 to its 161 px minimum; restoring only Properties left the explorer at 161. So the snapshot holds every docked
  dock's size along its axis, and a restore puts them all back TOGETHER (one `resizeDocks` call per orientation,
  which returned the explorer to 264 and the centre to 440 exactly).
* The centre refuses to go below 400 px and the rail takes 234, so at 1366 px the gain is 143 px (+34%); on a 1920 px
  screen it is about 700. A gain under `MIN_GAIN` is undone and reported, not kept.
* Qt does not keep an expansion through a window resize: shrinking to 1100 px left Properties at 297 and growing back
  left it there. Re-applying the same call after the resize gave 563 again, so a window that is expanded re-applies
  it when it is resized; the menu, the state and the geometry then agree.
* Restoring by FRACTIONS into a smaller window is clamped by the minimums (166 and 292 where 264 and 420 scaled),
  so a restore is exact only for the window size it was captured at and proportional, within the constraints, for
  any other.

Everything here takes the window as an argument and keeps no state of its own: the window owns the one
`ExpandState` it may hold.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QMainWindow

#: A growth smaller than this is no growth: the panel was already as large as the layout lets it be.
MIN_GAIN = 24

_HORIZONTAL = Qt.Orientation.Horizontal
_VERTICAL = Qt.Orientation.Vertical
_SIDES = (Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.RightDockWidgetArea)
_ENDS = (Qt.DockWidgetArea.TopDockWidgetArea, Qt.DockWidgetArea.BottomDockWidgetArea)


@dataclass(frozen=True)
class ExpandState:
    """Everything needed to put the layout back, captured before the expansion."""

    dock: str
    orientation: Qt.Orientation
    #: The window's size when this was captured; an exact restore needs the window unchanged.
    window_size: tuple[int, int]
    #: Width of every docked left/right dock, by name.
    widths: dict[str, int]
    #: Height of every docked top/bottom dock, by name.
    heights: dict[str, int]


def docked(window: QMainWindow) -> list[QDockWidget]:
    """The docks that are in the layout and showing: not floating, not hidden, not outside it."""
    return [
        dock for dock in window.findChildren(QDockWidget)
        if dock.parent() is window and not dock.isHidden() and not dock.isFloating()
        and window.dockWidgetArea(dock) != Qt.DockWidgetArea.NoDockWidgetArea
    ]


def _representatives(window: QMainWindow, docks: list[QDockWidget]) -> list[QDockWidget]:
    """One dock per tab group: `resizeDocks` is documented to want only one per group."""
    seen: set[str] = set()
    kept = []
    for dock in docks:
        if dock.objectName() in seen:
            continue
        kept.append(dock)
        seen.add(dock.objectName())
        seen.update(other.objectName() for other in window.tabifiedDockWidgets(dock))
    return kept


def is_tabified_with_a_visible_dock(window: QMainWindow, dock: QDockWidget) -> bool:
    return any(not other.isHidden() for other in window.tabifiedDockWidgets(dock))


def orientation_of(window: QMainWindow, dock: QDockWidget) -> Qt.Orientation | None:
    """The axis a docked dock grows along, or None for one that is not in the layout."""
    area = window.dockWidgetArea(dock)
    if area in _SIDES:
        return _HORIZONTAL
    if area in _ENDS:
        return _VERTICAL
    return None


def can_expand(window: QMainWindow, dock: QDockWidget) -> tuple[bool, str]:
    """Whether Expand panel is offered for `dock`, and the reason when it is not."""
    if dock.isFloating() or orientation_of(window, dock) is None:
        return False, "Only a panel that is docked in the window can be expanded."
    if is_tabified_with_a_visible_dock(window, dock):
        return False, "This panel shares a tab group with another panel; separate them first."
    return True, ""


def capture(window: QMainWindow, dock: QDockWidget) -> ExpandState:
    docks = _representatives(window, docked(window))
    return ExpandState(
        dock=dock.objectName(),
        orientation=orientation_of(window, dock) or _HORIZONTAL,
        window_size=(window.width(), window.height()),
        widths={d.objectName(): d.width() for d in docks if window.dockWidgetArea(d) in _SIDES},
        heights={d.objectName(): d.height() for d in docks if window.dockWidgetArea(d) in _ENDS},
    )


def _size_along(dock: QDockWidget, orientation: Qt.Orientation) -> int:
    return dock.width() if orientation == _HORIZONTAL else dock.height()


def _grow(window: QMainWindow, dock: QDockWidget, orientation: Qt.Orientation) -> None:
    """Ask for more than any window can give; Qt clamps to what the layout allows."""
    target = window.width() if orientation == _HORIZONTAL else window.height()
    window.resizeDocks([dock], [target], orientation)
    layout = window.layout()
    if layout is not None:
        layout.activate()


def expand(window: QMainWindow, dock: QDockWidget) -> ExpandState | None:
    """Expand `dock`. Returns the state to restore from, or None when there was nothing to expand into.

    A growth under `MIN_GAIN` is put back at once so a no-op leaves the layout exactly as it was.
    """
    allowed, _reason = can_expand(window, dock)
    if not allowed:
        return None
    state = capture(window, dock)
    before = _size_along(dock, state.orientation)
    _grow(window, dock, state.orientation)
    if _size_along(dock, state.orientation) - before < MIN_GAIN:
        restore(window, state)
        return None
    return state


def reapply(window: QMainWindow, state: ExpandState) -> bool:
    """Expand the same dock again, after the window changed size. False when it can no longer be expanded."""
    dock = next((d for d in docked(window) if d.objectName() == state.dock), None)
    if dock is None or orientation_of(window, dock) != state.orientation:
        return False
    _grow(window, dock, state.orientation)
    return True


def _apply(window: QMainWindow, sizes: dict[str, int], orientation: Qt.Orientation, scale: float) -> None:
    pairs = [
        (dock, max(1, round(sizes[dock.objectName()] * scale)))
        for dock in _representatives(window, docked(window))
        if dock.objectName() in sizes and orientation_of(window, dock) == orientation
    ]
    if pairs:
        window.resizeDocks([d for d, _ in pairs], [s for _, s in pairs], orientation)


def restore(window: QMainWindow, state: ExpandState) -> None:
    """Put every dock back together, in one `resizeDocks` call per orientation.

    Pixel-exact when the window is the size it was; otherwise each size is scaled by how the window changed, and
    Qt's minimums may bend it.
    """
    width, height = state.window_size
    same = (window.width(), window.height()) == (width, height)
    _apply(window, state.widths, _HORIZONTAL, 1.0 if same else window.width() / max(width, 1))
    _apply(window, state.heights, _VERTICAL, 1.0 if same else window.height() / max(height, 1))
    layout = window.layout()
    if layout is not None:
        layout.activate()
