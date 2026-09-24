"""The Settings page where a menu command's shortcut is changed.

**EVERY ROW IS A COMMAND THE MENUS OFFER, NOT A LIST WRITTEN HERE.** The rows come from the
`ShortcutRegistry` the main window filled as it built its menus, so a command added to a menu
appears on this page with no edit to it, and a command cannot be on the page without being in a menu.

**A REFUSED CHANGE SAYS WHY AND CHANGES NOTHING.** A shortcut another command already holds is not
taken from it: the page names the command, and the person clears that one first. A silent steal
would leave a command with no way in and no sign of why. A combination with no Ctrl, Alt or Meta
(and not a function key) is refused too, because the drawing canvas owns the bare letters and digits
(`shortcut_registry.refusal_for`). The row goes back to what it held.

**IT CHANGES THE WINDOW'S SHORTCUTS, NEVER THE CANVAS'S.** The keys typed while the drawing has
focus (element letters, bond digits, Delete) belong to the editor; whether they can be remapped is
what the drawing spike measured (`docs/KETCHER_SPIKE.md`), and this page does not promise it.
"""

from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from openchem.app.shortcut_registry import PORTABLE, ShortcutRegistry, portable
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: Qt property naming which command a row's control belongs to. It travels on the control and
#: comes back through `sender()`, because a lambda capturing `self` in `connect()` roots the dialog
#: for the life of the process.
_COMMAND_PROPERTY = "openchem_command_id"

#: The contracts, one per concept. Every row's box shares one and every row's Reset another: which
#: command is what `instance_path` already says.
_HELP = {
    "search": HelpTooltip(
        text=(
            "Narrows the list to commands whose name, or whose shortcut, contains what you "
            "type. Nothing is changed by searching."
        ),
        tier=1,
        help_id="settings.shortcut_search",
        topic="settings",
        help_anchor="settings",
    ),
    "edit": HelpTooltip(
        text=(
            "Click, then press the combination you want for this command; the x clears it. "
            "It applies at once.\n\n"
            "A shortcut needs Ctrl, Alt or Meta, or is a function key, because the drawing "
            "canvas uses the bare letters and digits. One that another command already holds "
            "is refused and the page names that command -- clear it first. These are the "
            "window's shortcuts only; the keys typed while drawing are the editor's."
        ),
        tier=2,
        help_id="settings.shortcut_edit",
        topic="settings",
        help_anchor="settings",
    ),
    "reset": HelpTooltip(
        text=(
            "Puts this command back to the shortcut it shipped with. Refused, saying why, if "
            "another command has taken that combination since."
        ),
        tier=1,
        help_id="settings.shortcut_reset",
        topic="settings",
        help_anchor="settings",
    ),
    "reset_all": HelpTooltip(
        text=(
            "Puts every command back to the shortcut it shipped with and forgets every "
            "choice of your own. Nothing else is changed."
        ),
        tier=1,
        help_id="settings.shortcut_reset_all",
        topic="settings",
        help_anchor="settings",
    ),
}


class KeyboardShortcutsPage(QWidget):
    """See the module docstring."""

    def __init__(self, registry: ShortcutRegistry | None, parent: QWidget | None = None) -> None:
        """`registry` is the main window's; None (a Settings window opened without one) gives an
        empty page that says so, rather than a page that pretends."""
        super().__init__(parent)
        self._registry = registry
        #: command id -> (row frame, the recorder, its Reset button)
        self._rows: dict[str, tuple[QFrame, QKeySequenceEdit, QPushButton]] = {}

        self._search = QLineEdit(self)
        self._search.setObjectName("shortcutSearch")
        self._search.setPlaceholderText("Search commands or shortcuts")
        self._search.setClearButtonEnabled(True)
        apply_help_tooltip(self._search, _HELP["search"])
        self._search.textChanged.connect(self._apply_filter)

        self._reset_all = QPushButton("Reset all to defaults", self)
        self._reset_all.setObjectName("resetShortcuts")
        self._reset_all.setAutoDefault(False)
        apply_help_tooltip(self._reset_all, _HELP["reset_all"])
        self._reset_all.clicked.connect(self._on_reset_all_clicked)

        #: What the last change did, or why it was refused. Public so a test can read it.
        self.status = QLabel("", self)
        self.status.setObjectName("shortcutStatus")
        self.status.setWordWrap(True)

        rows = QWidget(self)
        grid = QGridLayout(rows)
        grid.setContentsMargins(0, 0, 0, 0)
        entries = registry.entries() if registry is not None else []
        for number, entry in enumerate(entries):
            grid.addWidget(self._build_row(entry, rows), number, 0)
        grid.setRowStretch(len(entries), 1)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(rows)

        heading = QLabel("<b>Keyboard</b>", self)
        note = QLabel(
            "Every menu command and its shortcut. Click a box and press a new combination; "
            "changes apply at once. These are the window's shortcuts: the keys typed while "
            "drawing belong to the editor.",
            self,
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666666;")
        empty = QLabel("No commands are available in this window.", self)
        empty.setVisible(not entries)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(note)
        layout.addWidget(self._search)
        layout.addWidget(empty)
        layout.addWidget(scroll, 1)
        layout.addWidget(self.status)
        layout.addWidget(self._reset_all)
        self._refresh()

    # --- rows ----------------------------------------------------------------

    def _build_row(self, entry, parent: QWidget) -> QFrame:
        row = QFrame(parent)
        row.setObjectName(f"shortcutRow:{entry.command_id}")

        name = QLabel(entry.label, row)
        name.setObjectName(f"shortcutName:{entry.command_id}")

        edit = QKeySequenceEdit(row)
        edit.setObjectName(f"shortcutEdit:{entry.command_id}")
        edit.setProperty(_COMMAND_PROPERTY, entry.command_id)
        # One combination: the registry refuses a sequence of them, so do not let the box record one.
        edit.setMaximumSequenceLength(1)
        edit.setClearButtonEnabled(True)
        apply_help_tooltip(edit, _HELP["edit"])
        edit.editingFinished.connect(self._on_edit_finished)

        reset = QPushButton("Reset", row)
        reset.setObjectName(f"shortcutReset:{entry.command_id}")
        reset.setProperty(_COMMAND_PROPERTY, entry.command_id)
        reset.setAutoDefault(False)
        apply_help_tooltip(reset, _HELP["reset"])
        reset.clicked.connect(self._on_reset_clicked)

        layout = QGridLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(name, 0, 0)
        layout.addWidget(edit, 0, 1)
        layout.addWidget(reset, 0, 2)
        layout.setColumnStretch(0, 1)
        layout.setColumnMinimumWidth(1, 180)
        self._rows[entry.command_id] = (row, edit, reset)
        return row

    def shortcut_of(self, command_id: str) -> str:
        """What the row's box shows, as portable text, for a test or a caller."""
        return portable(self._rows[command_id][1].keySequence())

    # --- changes -------------------------------------------------------------

    def assign(self, command_id: str, sequence: str) -> str | None:
        """Give a command `sequence` ("" clears it). Returns None, or why it was refused.

        The whole path a recorded key takes, so a test drives it without a keyboard, and the
        box is put back to what the command really holds whichever way it ended.
        """
        if self._registry is None:
            return "There are no commands to change."
        reason = self._registry.set_shortcut(command_id, sequence)
        self.status.setText(f"Not changed: {reason}" if reason else "")
        self._refresh()
        return reason

    def _on_edit_finished(self) -> None:
        edit = self.sender()
        if edit is None or self._registry is None:
            return
        self.assign(str(edit.property(_COMMAND_PROPERTY)), portable(edit.keySequence()))

    def _on_reset_clicked(self, _checked: bool = False) -> None:
        button = self.sender()
        if button is None or self._registry is None:
            return
        reason = self._registry.reset(str(button.property(_COMMAND_PROPERTY)))
        self.status.setText(f"Not reset: {reason}" if reason else "")
        self._refresh()

    def _on_reset_all_clicked(self, _checked: bool = False) -> None:
        if self._registry is None:
            return
        self._registry.reset_all()
        self.status.setText("")
        self._refresh()

    def _refresh(self) -> None:
        """Put every box in step with what the commands hold, without storing anything."""
        if self._registry is None:
            self._reset_all.setEnabled(False)
            return
        entries = self._registry.entries()
        for entry in entries:
            _row, edit, reset = self._rows[entry.command_id]
            edit.blockSignals(True)
            edit.setKeySequence(QKeySequence.fromString(entry.current, PORTABLE))
            edit.blockSignals(False)
            reset.setEnabled(not entry.is_default)
        self._reset_all.setEnabled(any(not entry.is_default for entry in entries))
        self._apply_filter(self._search.text())

    def _apply_filter(self, text: str) -> None:
        """Show the rows whose command name, id or shortcut contains `text`."""
        if self._registry is None:
            return
        wanted = text.strip().lower()
        for entry in self._registry.entries():
            haystack = f"{entry.label} {entry.command_id} {entry.current}".lower()
            self._rows[entry.command_id][0].setVisible(not wanted or wanted in haystack)
