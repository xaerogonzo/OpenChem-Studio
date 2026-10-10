"""What a workflow section holds in Properties: the workflow itself, or where it went.

A workflow (docking, alignment) is ONE widget with two possible homes: its own tab in
the right-hand rail, or a section of the Properties list. It is never built twice, so
there is one set of inputs, one result, and one 3D view -- which is the whole point of
moving it rather than copying it. This body is the Properties half of that:

* while the workflow is HERE, it holds the widget (inside a `HeightStatingHost`, which is
  what stops the list squeezing it) under a one-line bar with **Move to its own tab**;
* while it is in its TAB, it holds a short note saying so, with **Open the tab** and
  **Move here**, so the section is still where the person looks for it and still a way
  to bring it back.

It owns no workflow logic and does not touch the window. It emits what the person asked
for and the window, which owns the rail and the docks, does the moving.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.ui.widgets.height_stating_host import HeightStatingHost
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: Where a workflow lives: in the Properties list.
HOME_PROPERTIES = "properties"

#: Where a workflow lives: in its own tab in the rail (what it always had).
HOME_TAB = "tab"

#: The contract for "Move to its own tab", on the section and on the note a tab shows.
_MOVE_TO_TAB_HELP = HelpTooltip(
    text=(
        "Move this workflow out of the Properties list into its own tab in the right-hand "
        "rail, the way it used to be.\n\n"
        "It is the same workflow, not a copy: everything you have set, and any result on "
        "screen, comes with it. Use it when the workflow needs more room than a section "
        "has. You can move it back at any time."
    ),
    tier=1,
    help_id="workflows.move_to_tab",
    topic="properties",
    help_anchor="properties",
)

#: The contract for "Move here", the button that brings a workflow into Properties.
_MOVE_HERE_HELP = HelpTooltip(
    text=(
        "Bring this workflow back into the Properties list, as a section.\n\n"
        "It is the same workflow, not a copy: everything you have set, and any result on "
        "screen, comes with it. Its tab then says where it went."
    ),
    tier=1,
    help_id="workflows.move_here",
    topic="properties",
    help_anchor="properties",
)

#: The contract for "Open the tab", shown while the workflow lives in its tab.
_OPEN_TAB_HELP = HelpTooltip(
    text="Show this workflow's own tab in the right-hand rail.",
    tier=1,
    help_id="workflows.open_tab",
    topic="properties",
    help_anchor="properties",
)


class WorkflowBody(QWidget):
    """The content of one workflow section."""

    #: The person asked to move the workflow to this home (`HOME_PROPERTIES` / `HOME_TAB`).
    move_requested = Signal(str)
    #: The person asked to see the workflow's own tab while it lives there.
    open_tab_requested = Signal()

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._home = HOME_TAB
        self._host: HeightStatingHost | None = None

        self._note = QLabel("", self)
        self._note.setWordWrap(True)
        self._move_to_tab = QPushButton("Move to its own tab", self)
        apply_help_tooltip(self._move_to_tab, _MOVE_TO_TAB_HELP)
        self._move_to_tab.clicked.connect(self._on_move_to_tab)
        self._move_here = QPushButton("Move here", self)
        apply_help_tooltip(self._move_here, _MOVE_HERE_HELP)
        self._move_here.clicked.connect(self._on_move_here)
        self._open_tab = QPushButton("Open the tab", self)
        apply_help_tooltip(self._open_tab, _OPEN_TAB_HELP)
        self._open_tab.clicked.connect(self.open_tab_requested)

        self._bar = QWidget(self)
        bar = QHBoxLayout(self._bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addStretch(1)
        bar.addWidget(self._open_tab)
        bar.addWidget(self._move_here)
        bar.addWidget(self._move_to_tab)

        self._slot = QVBoxLayout()
        self._slot.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._bar)
        layout.addWidget(self._note)
        layout.addLayout(self._slot)
        self._show_home(HOME_TAB)

    # -- the two states ----------------------------------------------------------------

    def home(self) -> str:
        return self._home

    def adopt(self, widget: QWidget) -> None:
        """The workflow arrives (or starts) here."""
        self._host = HeightStatingHost(widget, self)
        self._slot.addWidget(self._host)
        self._show_home(HOME_PROPERTIES)

    def release(self) -> QWidget | None:
        """The workflow leaves, to its tab. Returns the same widget, or None if it was not here."""
        widget = None
        if self._host is not None:
            widget = self._host.release()
            self._slot.removeWidget(self._host)
            self._host.setParent(None)
            self._host.deleteLater()
            self._host = None
        self._show_home(HOME_TAB)
        return widget

    def widget(self) -> QWidget | None:
        """The workflow's widget while it is here, else None."""
        return self._host.child if self._host is not None else None

    def _show_home(self, home: str) -> None:
        self._home = home
        here = home == HOME_PROPERTIES
        self._move_to_tab.setVisible(here)
        self._move_here.setVisible(not here)
        self._open_tab.setVisible(not here)
        self._note.setVisible(not here)
        self._note.setText("" if here else f"{self._title} is open in its own tab.")

    def _on_move_to_tab(self) -> None:
        self.move_requested.emit(HOME_TAB)

    def _on_move_here(self) -> None:
        self.move_requested.emit(HOME_PROPERTIES)


#: The contract for "Show it in Properties", on the note a tab shows while the workflow is elsewhere.
_SHOW_IN_PROPERTIES_HELP = HelpTooltip(
    text="Go to Properties and open this workflow's section, where it is now.",
    tier=1,
    help_id="workflows.show_in_properties",
    topic="properties",
    help_anchor="properties",
)


class WorkflowPlaceholder(QWidget):
    """What a workflow's own tab shows while the workflow lives in Properties.

    The tab stays in the rail, so the place a person has always looked for it still
    answers, and says where it went and how to bring it back. (A click on the rail entry
    goes straight to the section; this is for every other way a dock can be shown, such
    as a restored layout or the View menu.)
    """

    #: The person asked to be taken to the workflow's section in Properties.
    show_requested = Signal()
    #: The person asked to move the workflow back into this tab.
    move_back_requested = Signal()

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        note = QLabel(f"{title} is open in Properties.", self)
        note.setWordWrap(True)
        show = QPushButton("Show it in Properties", self)
        apply_help_tooltip(show, _SHOW_IN_PROPERTIES_HELP)
        show.clicked.connect(self.show_requested)
        move_back = QPushButton("Move it back to this tab", self)
        apply_help_tooltip(move_back, _MOVE_TO_TAB_HELP)
        move_back.clicked.connect(self.move_back_requested)
        layout = QVBoxLayout(self)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.addWidget(show)
        row.addWidget(move_back)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
