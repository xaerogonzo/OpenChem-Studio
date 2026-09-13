"""Take a widget out of a layout without it opening as a window.

**HIDE BEFORE DETACHING, AND THE ORDER IS THE WHOLE FIX.** Adding a widget
to a layout does not show it; `QLayout.addChildWidget` queues
`_q_showIfNotHidden` for the next event-loop turn. A widget detached with
`setParent(None)` before that turn is a parentless widget with a show still
pending -- and a parentless widget that shows is a top-level WINDOW.

That is what the white windows were: the results reader re-renders once per
arriving result, so every section built by one render was detached by the
next before its queued show ran. 1801 of them in one select-0-1-0 run,
caught by `OPENCHEM_TRACE_WINDOWS`.

An explicit `hide()` sets `WA_WState_ExplicitShowHide`, which is precisely
what `_q_showIfNotHidden` checks, so the pending show becomes a no-op.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


def discard_widget(widget: QWidget) -> None:
    widget.hide()
    widget.setParent(None)
    widget.deleteLater()
