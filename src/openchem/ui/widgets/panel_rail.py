"""Navigation for the right-hand panels: icons for groups, names for panels.

WHY THIS EXISTS, measured rather than felt. Twelve panels shared one
tabified dock group, and Qt gives such a group a single `QTabBar`.
**That bar needs 1992 px and had about 920**, so every label was elided
to two or three characters -- `"Qu..."`, `"J..."`, `"B..."` -- and
dragging the dock wider could not fix it, because a bar wide enough for
twelve labels is wider than the whole window.

What it costs, measured on the real window at 1900x1000:

    tab bar, twelve panels          wanted 1992 px, had ~920
    rail, first attempt             412 px  (icon column 156, list 256)
    rail, icons only + heading      264 px  (icon column  34, list 230)

The first attempt put each group's name under its icon, and "Extensions"
set the column width -- 22% of the window given to navigation. The name
is not lost: it is the heading above the list, which is where somebody
looks to know where they are, and it is still the tooltip. Every panel
name now fits with room to spare; the longest, "Quantum Chemistry", needs
204 px of the 228 available.

THE TAB BAR IS GONE, NOT HIDDEN. `tabifyDockWidget` is what creates it,
so the panels are no longer tabified at all; one right-hand dock is
visible at a time and this widget chooses which. Hiding Qt's bar was
tried first and does not stick -- `setVisible(False)` on the live bar
reads back `True` after the next relayout, because the dock area re-shows
it. Removing the cause beats fighting the symptom, and it also removes
the reason the group was tabified in the first place: with one panel
visible it gets the whole column, which is what tabifying was working
around.

**It knows nothing about panels.** It is told (id, title, group) and
emits an id when something is chosen. MainWindow owns the docks; this
owns the navigation, and the two meet at a string.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

#: Group id -> label. The order here is the order down the rail.
#:
#: "Compute" rather than "Quantum", deliberately: the group holds Docking
#: and 3D Alignment as well as Quantum Chemistry, and filing a docking run
#: under "Quantum" would be a chemistry error on the one label a new user
#: reads first. Same slot, honest name.
GROUP_LABELS: dict[str, str] = {
    "analysis": "Analysis",
    "compute": "Compute",
    "compare": "Compare",
    "assist": "AI",
    "extensions": "Extensions",
}

#: Where a panel goes when nothing says otherwise. Plugins land here, so a
#: third-party panel is reachable the moment it loads without the plugin
#: having to know this vocabulary exists.
DEFAULT_GROUP = "extensions"

#: Carried on a list row so a chosen row resolves back to its panel.
_PANEL_ID_ROLE = Qt.ItemDataRole.UserRole
#: Carried on a rail button, read back through `sender()` -- never a
#: lambda closing over `self`, which PySide6 holds strongly and which
#: leaked a whole window the last time it was used here.
_GROUP_PROPERTY = "openchem_group"

_ICON_SIZE = 22


def _group_icon(group: str) -> QIcon:
    """A small monochrome glyph per group, drawn rather than shipped.

    No icon set exists in this repo and Qt's standard icons are
    file-manager glyphs -- a folder and a floppy disk say nothing about
    quantum chemistry. These are drawn with primitives so they stay sharp
    at rail size and carry no licence.

    Shape does the work, not colour: at 22 px a detailed picture is mud,
    and colour alone is no use to a colour-blind reader. Every button also
    carries its group name as text and tooltip, so the icon is a
    scanning aid rather than the only label.
    """
    pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(70, 70, 70), 1.6))
    m, s = 3, _ICON_SIZE - 6
    if group == "analysis":
        # A magnifier: looking closely at one thing.
        painter.drawEllipse(m, m, s - 5, s - 5)
        painter.drawLine(m + s - 6, m + s - 6, m + s, m + s)
    elif group == "compute":
        # Two crossed orbitals.
        painter.drawEllipse(m, m + s // 4, s, s // 2)
        painter.save()
        painter.translate(_ICON_SIZE / 2, _ICON_SIZE / 2)
        painter.rotate(60)
        painter.drawEllipse(-s // 2, -s // 4, s, s // 2)
        painter.restore()
    elif group == "compare":
        # Two bars of different height, side by side.
        painter.drawRect(m, m + s // 3, s // 3, s - s // 3)
        painter.drawRect(m + s // 2, m, s // 3, s)
    elif group == "assist":
        # A four-pointed spark.
        c = _ICON_SIZE / 2
        painter.drawLine(c, m, c, m + s)
        painter.drawLine(m, c, m + s, c)
        painter.drawLine(m + s // 4, m + s // 4, m + 3 * s // 4, m + 3 * s // 4)
        painter.drawLine(m + 3 * s // 4, m + s // 4, m + s // 4, m + 3 * s // 4)
    else:
        # Extensions: a square with a piece out of it.
        painter.drawRect(m, m, s, s)
        painter.drawRect(m + s // 2, m + s // 2, s // 2, s // 2)
    painter.end()
    return QIcon(pixmap)


class PanelRail(QWidget):
    """Group icons in a column, the chosen group's panel names beside them.

    Two levels because one was not enough either way round: twelve flat
    names do not fit, and five group names alone do not say what is in
    them.
    """

    #: A panel was chosen. Carries the panel id MainWindow registered.
    panel_chosen = Signal(str)
    #: A panel's favourite state was toggled, so the caller can persist it.
    favourite_toggled = Signal(str, bool)
    #: The name list was folded or unfolded, so the caller can persist it.
    #: Carries VISIBLE rather than collapsed, matching `set_list_visible`,
    #: because a signal whose sense is the inverse of the method that
    #: raises it is a place for somebody to drop a `not`.
    list_visibility_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        #: panel id -> (title, group). Plain data, never widgets: a dict
        #: KEYED BY a QWidget has to hash it, and PySide hashes on the C++
        #: pointer, which Qt frees with the parent. See
        #: `ui/widgets/empty_state.py` for what that cost.
        self._panels: dict[str, tuple[str, str]] = {}
        self._favourites: list[str] = []
        self._group = next(iter(GROUP_LABELS))

        self._buttons = QWidget(self)
        self._buttons_layout = QVBoxLayout(self._buttons)
        self._buttons_layout.setContentsMargins(2, 2, 2, 2)
        self._buttons_layout.setSpacing(2)
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        for group, label in GROUP_LABELS.items():
            button = QToolButton(self._buttons)
            button.setIcon(_group_icon(group))
            button.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
            button.setText(label)
            button.setToolTip(label)
            button.setCheckable(True)
            # ICON ONLY. With the label under each icon the column was 156
            # px wide -- "Extensions" sets it -- and the whole rail 412,
            # which is 22% of a 1900px window given over to navigation
            # chrome. The group name is not lost: it is the heading above
            # the list, which is where somebody looks to know where they
            # are, and it is still the tooltip.
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setAutoRaise(True)
            button.setProperty(_GROUP_PROPERTY, group)
            button.clicked.connect(self._on_group_clicked)
            self._button_group.addButton(button)
            self._buttons_layout.addWidget(button)
        self._buttons_layout.addStretch(1)

        self._heading = QLabel("")
        self._heading.setStyleSheet("font-weight: bold; padding: 4px 6px;")

        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        # Wide enough for "Quantum Chemistry", which needs 204 px measured
        # -- the longest panel name there is. Capped so the rail cannot
        # grow without bound as panels are added; a longer name than that
        # elides, which is the thing this whole phase exists to avoid, so
        # a new panel with a longer name should be renamed rather than
        # this widened.
        self._list.setMaximumWidth(230)
        self._list.setMinimumWidth(210)
        self._list.itemActivated.connect(self._on_item_chosen)
        self._list.itemClicked.connect(self._on_item_chosen)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_list_menu)

        # The heading and the list live in ONE container so collapsing the
        # rail is a single `setVisible` on it -- rather than hiding two
        # widgets and hoping they stay in step.
        self._names = QWidget(self)
        names = QVBoxLayout(self._names)
        names.setContentsMargins(0, 0, 0, 0)
        names.setSpacing(0)
        names.addWidget(self._heading)
        names.addWidget(self._list, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._buttons)
        layout.addWidget(self._names, 1)

        self._select_group(self._group)

    # --- registration --------------------------------------------------------

    def register(self, panel_id: str, title: str, group: str = DEFAULT_GROUP) -> None:
        """Tell the rail a panel exists. Idempotent, so a plugin that
        reloads does not double up."""
        self._panels[panel_id] = (title, group if group in GROUP_LABELS else DEFAULT_GROUP)
        self._rebuild()

    def unregister(self, panel_id: str) -> None:
        self._panels.pop(panel_id, None)
        if panel_id in self._favourites:
            self._favourites.remove(panel_id)
        self._rebuild()

    def set_favourites(self, panel_ids: list[str]) -> None:
        self._favourites = [p for p in panel_ids if p]
        self._rebuild()

    def favourites(self) -> list[str]:
        return list(self._favourites)

    def panel_ids(self) -> list[str]:
        return list(self._panels)

    def current_group(self) -> str:
        return self._group

    def visible_panel_ids(self) -> list[str]:
        """What the list is showing, in order -- the guard in
        `tests/test_panel_rail.py` reads this rather than a stored copy."""
        return [
            self._list.item(row).data(_PANEL_ID_ROLE)
            for row in range(self._list.count())
            if self._list.item(row).data(_PANEL_ID_ROLE)
        ]

    def select_panel(self, panel_id: str) -> None:
        """Show `panel_id`'s group and highlight it, without re-emitting.

        Called when something OTHER than a click changed which panel is in
        front -- a plugin revealing its own panel, or the window restoring
        a layout -- so the rail agrees with the screen.
        """
        entry = self._panels.get(panel_id)
        if entry is None:
            return
        if panel_id not in self._favourites:
            self._select_group(entry[1])
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(_PANEL_ID_ROLE) == panel_id:
                self._list.setCurrentItem(item)
                return

    # --- internals -----------------------------------------------------------

    def _on_group_clicked(self, _checked: bool = False) -> None:
        """Choose a group -- or, on the group already showing, collapse.

        The name list costs 230 px of a column the panels need: with it
        open, the Quantum Chemistry form truncates its own controls and
        falls back to a horizontal scrollbar. Clicking the active group
        again folds the rail down to its 34 px of icons and hands that
        width back, and clicking any group opens it again.

        Collapsing on a SECOND click of the same button, rather than
        adding a separate collapse control: it is the gesture people
        already expect from a sidebar, and it needs no widget of its own.
        """
        button = self.sender()
        if button is None:
            return
        group = str(button.property(_GROUP_PROPERTY) or "")
        if not group:
            return
        if group == self._group and not self._names.isHidden():
            self.set_list_visible(False)
            # Qt unchecks a checked button in an exclusive group on click;
            # put it back, because the group is still the current one and
            # the rail should say so.
            button.setChecked(True)
            return
        self.set_list_visible(True)
        self._select_group(group)

    def set_list_visible(self, visible: bool) -> None:
        """Fold or unfold the name list, announcing a real change.

        Emits only on a TRANSITION, so restoring the state the rail is
        already in does not write a settings key during construction --
        and so a caller that persists on this signal cannot be woken by
        its own restore.
        """
        if visible == self.is_list_visible():
            self._names.setVisible(visible)
            return
        self._names.setVisible(visible)
        self.list_visibility_changed.emit(visible)

    def is_list_visible(self) -> bool:
        return not self._names.isHidden()

    def _select_group(self, group: str) -> None:
        self._group = group
        for button in self._button_group.buttons():
            button.setChecked(button.property(_GROUP_PROPERTY) == group)
        self._rebuild()

    def _rebuild(self) -> None:
        """Redraw the list for the current group, favourites first.

        Rebuilt wholesale rather than diffed: there are a dozen rows, and
        a diff is a second source of truth about what is on screen.
        """
        self._heading.setText(GROUP_LABELS.get(self._group, ""))
        self._list.clear()
        for panel_id in self._favourites:
            entry = self._panels.get(panel_id)
            if entry is not None:
                self._add_row(panel_id, f"★ {entry[0]}")
        for panel_id, (title, group) in self._panels.items():
            if group == self._group and panel_id not in self._favourites:
                self._add_row(panel_id, title)

    def _add_row(self, panel_id: str, label: str) -> None:
        item = QListWidgetItem(label, self._list)
        item.setData(_PANEL_ID_ROLE, panel_id)
        item.setToolTip(label)

    def _on_item_chosen(self, item: QListWidgetItem) -> None:
        panel_id = item.data(_PANEL_ID_ROLE)
        if panel_id:
            self.panel_chosen.emit(str(panel_id))

    def _on_list_menu(self, position) -> None:
        from PySide6.QtWidgets import QMenu

        item = self._list.itemAt(position)
        if item is None:
            return
        panel_id = str(item.data(_PANEL_ID_ROLE) or "")
        if not panel_id:
            return
        pinned = panel_id in self._favourites
        menu = QMenu(self)
        action = menu.addAction("Unpin from top" if pinned else "Pin to top")
        chosen = menu.exec(self._list.mapToGlobal(position))
        if chosen is action:
            self.toggle_favourite(panel_id)

    def toggle_favourite(self, panel_id: str) -> None:
        if panel_id in self._favourites:
            self._favourites.remove(panel_id)
            self.favourite_toggled.emit(panel_id, False)
        else:
            self._favourites.append(panel_id)
            self.favourite_toggled.emit(panel_id, True)
        self._rebuild()
