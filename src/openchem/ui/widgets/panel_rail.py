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
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
from PySide6.QtWidgets import (
    QButtonGroup,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

#: Group id -> label. The order here is the order down the rail.
#:
#: THREE GROUPS, NOT FIVE, AND EACH NAME SAYS WHAT IT HOLDS. Five icon buttons
#: ("Analysis", "Compute", "Compare", "AI", "Extensions") were reported as
#: "I click all of them to find what I need": two of the five held one panel
#: and a third held none until a plugin loaded. What somebody wants is to read
#: a result, start heavy work, or step outside the molecule on screen.
#:
#: "Compute" rather than "Quantum", deliberately: the group holds Docking
#: and 3D Alignment as well as Quantum Chemistry, and filing a docking run
#: under "Quantum" would be a chemistry error on the one label a new user
#: reads first.
GROUP_LABELS: dict[str, str] = {
    "analyze": "Analyze",
    "compute": "Compute",
    "extend": "Compare and Extend",
}

#: One sentence per group, shown under the heading and in the tooltip, so a
#: group is explained where it is chosen rather than by opening each in turn.
GROUP_DESCRIPTIONS: dict[str, str] = {
    "analyze": "Run calculators and read what they found.",
    "compute": "Start heavy jobs: quantum chemistry, docking, alignment.",
    "extend": "Compare molecules, and panels added by plugins.",
}

#: Where a panel goes when nothing says otherwise. Plugins land here, so a
#: third-party panel is reachable the moment it loads without the plugin
#: having to know this vocabulary exists.
DEFAULT_GROUP = "extend"

#: The group ids this rail used to have, mapped onto the three it has now. A
#: plugin written against the old vocabulary keeps working and is filed, not
#: lost: `register` reads this before it falls back to DEFAULT_GROUP.
LEGACY_GROUPS: dict[str, str] = {
    "analysis": "analyze",
    "compare": "extend",
    "assist": "extend",
    "extensions": "extend",
}

#: EVERY BUILT-IN PANEL, ITS GROUP AND ITS PLACE, in the order they are listed.
#: The order is explicit rather than a side effect of construction: the primary
#: pair (Properties starts work, Results reads it) lead Analyze and the rest
#: run A to Z, which is how a list is scanned. Panel ids are the dock object
#: names.
#:
#: **BATCH SITS IN COMPUTE ONLY UNTIL IT MERGES INTO PROPERTIES.** That is a
#: later stage of the same work; moving it now would put it in a group that
#: describes it no better, and its removal is a one-line change here.
#:
#: A guard (`tests/test_panel_rail.py`) compares this table with the docks the
#: window actually builds, so a new panel cannot fall into the default group
#: and pass.
BUILTIN_PANELS: tuple[tuple[str, str], ...] = (
    ("Properties", "analyze"),
    ("Results", "analyze"),
    ("Atom_Inspector", "analyze"),
    ("Interactions", "analyze"),
    ("Structure_Check", "analyze"),
    ("3D_Alignment", "compute"),
    ("Batch", "compute"),
    ("Docking", "compute"),
    ("Jobs", "compute"),
    ("Quantum_Chemistry", "compute"),
    ("Compare", "extend"),
)


def builtin_group_of(panel_id: str) -> str | None:
    """The group a built-in panel belongs to, or None for one not in the table."""
    return next((group for pid, group in BUILTIN_PANELS if pid == panel_id), None)


def builtin_order_of(panel_id: str) -> int | None:
    return next((index for index, (pid, _g) in enumerate(BUILTIN_PANELS) if pid == panel_id), None)


#: Carried on a list row so a chosen row resolves back to its panel.
_PANEL_ID_ROLE = Qt.ItemDataRole.UserRole
#: Carried on a rail button, read back through `sender()` -- never a
#: lambda closing over `self`, which PySide6 holds strongly and which
#: leaked a whole window the last time it was used here.
_GROUP_PROPERTY = "openchem_group"
#: The group's label, kept on its button so the text can be taken off when the
#: list is folded and put back when it opens.
_LABEL_PROPERTY = "openchem_label"

#: ONE CONCEPT, FIVE RENDERINGS. Every group button means the same thing --
#: "show this group's panels in the list below me" -- and what differs is
#: only WHICH group, which is a property of the button and not of the
#: control's meaning. `instance_path` tells the five apart. Giving them an
#: id each would be the batch-tick-box mutation shipped on purpose.
#:
#: They previously carried `setToolTip(label)`, i.e. the button's own text
#: restated as its explanation -- the exact degeneracy
#: `test_no_contract_is_a_placeholder` refuses in a contract.
_GROUP_HELP = HelpTooltip(
    text=(
        "Show this group's panels in the list below it.\n\n"
        "One right-hand panel is visible at a time, so choosing a name "
        "here replaces what is on screen rather than adding to it. Right-click "
        "a name to open it beside what is showing instead, or to lock it "
        "open so a click elsewhere leaves it. "
        "Clicking the group already showing folds the list away and "
        "hands its width back to the panel."
    ),
    tier=1,
    help_id="workspace.panel_group",
    topic="workspace",
)

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
    if group == "analyze":
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
    else:
        # Compare and Extend: two bars of different height, with a plus
        # beside them -- the "more of it, side by side" shape.
        painter.drawRect(m, m + s // 3, s // 3, s - s // 3)
        painter.drawRect(m + s // 2, m, s // 3, s)
    painter.end()
    return QIcon(pixmap)


class PanelRail(QWidget):
    """Three labelled groups stacked above the chosen group's panel names.

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
    #: A panel was asked for ALONGSIDE what is showing (right-click > Open beside), so nothing else is hidden.
    panel_chosen_alongside = Signal(str)
    #: A panel's lock was toggled from its menu. The rail only asks; MainWindow owns which panels are locked
    #: and tells the rail back through `set_locked_panels`.
    panel_lock_toggled = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        #: panel id -> (title, group). Plain data, never widgets: a dict
        #: KEYED BY a QWidget has to hash it, and PySide hashes on the C++
        #: pointer, which Qt frees with the parent. See
        #: `ui/widgets/empty_state.py` for what that cost.
        self._panels: dict[str, tuple[str, str]] = {}
        #: panel id -> place in its group, for the built-in ones. Absent means a
        #: plugin's, which is listed after them, A to Z, whatever order it loaded in.
        self._order: dict[str, int] = {}
        self._favourites: list[str] = []
        #: Panels a rail click will not hide. Plain ids, set by MainWindow.
        self._locked: set[str] = set()
        self._group = next(iter(GROUP_LABELS))

        self._buttons = QWidget(self)
        self._buttons_layout = QVBoxLayout(self._buttons)
        self._buttons_layout.setContentsMargins(2, 2, 2, 2)
        self._buttons_layout.setSpacing(2)
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        for group, label in GROUP_LABELS.items():
            button = QPushButton(self._buttons)
            button.setIcon(_group_icon(group))
            button.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
            button.setText(label)
            apply_help_tooltip(button, _GROUP_HELP)
            button.setCheckable(True)
            # TEXT BESIDE THE ICON WHILE THE LIST IS OPEN, ICON ONLY WHEN IT
            # IS FOLDED (`_apply_button_style`). Icon-only was the fix for a
            # 412 px rail, but it left five unlabelled glyphs that people
            # clicked one by one to find what they wanted. The buttons now
            # stack ABOVE the list instead of beside it, so the labels cost
            # no width: the rail is as wide as its list, and folds to the
            # icons alone.
            button.setFlat(True)
            # Left-aligned: a centred label under a left-hung icon reads as two
            # unrelated things. A push button honours `text-align`; a tool
            # button does not, and its hint put "Compare and Extend" at 274 px
            # (measured) in a 230 px list.
            button.setStyleSheet(
                "QPushButton { text-align: left; padding: 5px 8px; }"
                "QPushButton:checked { font-weight: bold; }"
            )
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setProperty(_LABEL_PROPERTY, label)
            button.setToolTip(f"{label}: {GROUP_DESCRIPTIONS[group]}")
            button.setProperty(_GROUP_PROPERTY, group)
            button.clicked.connect(self._on_group_clicked)
            self._button_group.addButton(button)
            self._buttons_layout.addWidget(button)

        self._heading = QLabel("")
        self._heading.setStyleSheet("font-weight: bold; padding: 4px 6px 0 6px;")
        #: The one-line "what is in this group", where the group is chosen.
        self._description = QLabel("")
        self._description.setWordWrap(True)
        self._description.setStyleSheet("padding: 0 6px 4px 6px; color: palette(mid);")

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
        names.addWidget(self._description)
        names.addWidget(self._list, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # Pinned to the top: a folded rail has no list to take the spare height,
        # and the icons would otherwise spread down the whole column.
        layout.addWidget(self._buttons, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._names, 1)

        self._apply_button_style()
        self._select_group(self._group)

    # --- registration --------------------------------------------------------

    def register(
        self, panel_id: str, title: str, group: str = DEFAULT_GROUP, order: int | None = None
    ) -> None:
        """Tell the rail a panel exists. Idempotent, so a plugin that
        reloads does not double up.

        `order` is a built-in panel's place in its group; a plugin gives none
        and is listed after them by title, so load order never decides what
        somebody sees. A group id from the old five-group vocabulary is filed
        under the group that replaced it, and an unknown one under
        DEFAULT_GROUP: a panel nobody can open is worse than a misfiled one.
        """
        group = LEGACY_GROUPS.get(group, group)
        self._panels[panel_id] = (title, group if group in GROUP_LABELS else DEFAULT_GROUP)
        if order is None:
            self._order.pop(panel_id, None)
        else:
            self._order[panel_id] = order
        self._rebuild()

    def unregister(self, panel_id: str) -> None:
        self._panels.pop(panel_id, None)
        self._order.pop(panel_id, None)
        if panel_id in self._favourites:
            self._favourites.remove(panel_id)
        self._rebuild()

    def set_favourites(self, panel_ids: list[str]) -> None:
        self._favourites = [p for p in panel_ids if p]
        self._rebuild()

    def favourites(self) -> list[str]:
        return list(self._favourites)

    def set_locked_panels(self, panel_ids) -> None:
        """Which panels a rail click will leave on screen; shown with a lock in the list."""
        self._locked = {p for p in panel_ids if p}
        self._rebuild()

    def locked_panels(self) -> set[str]:
        return set(self._locked)

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
            self._apply_button_style()
            return
        self._names.setVisible(visible)
        self._apply_button_style()
        self.list_visibility_changed.emit(visible)

    def _apply_button_style(self) -> None:
        """Name beside the icon while the list is open; the icon alone when folded."""
        open_ = not self._names.isHidden()
        for button in self._button_group.buttons():
            label = str(button.property(_LABEL_PROPERTY) or "")
            button.setText(label if open_ else "")
            button.updateGeometry()
        # Qt caches a layout's size hint until it is told it is stale; without
        # this a fold reads as the same width until the next event-loop turn.
        self._buttons.updateGeometry()
        self._buttons_layout.invalidate()
        self.layout().invalidate()
        self.updateGeometry()

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
        self._description.setText(GROUP_DESCRIPTIONS.get(self._group, ""))
        self._list.clear()
        for panel_id in self._favourites:
            entry = self._panels.get(panel_id)
            if entry is not None:
                self._add_row(panel_id, f"★ {entry[0]}")
        # Built-in panels in their declared order, then plugins A to Z; the id
        # is the last tie-break so the order is total.
        in_group = [
            (panel_id, title)
            for panel_id, (title, group) in self._panels.items()
            if group == self._group and panel_id not in self._favourites
        ]
        in_group.sort(
            key=lambda row: (
                0 if row[0] in self._order else 1,
                self._order.get(row[0], 0),
                row[1].casefold(),
                row[0],
            )
        )
        for panel_id, title in in_group:
            self._add_row(panel_id, title)

    def _add_row(self, panel_id: str, label: str) -> None:
        locked = panel_id in self._locked
        item = QListWidgetItem(f"\U0001F512 {label}" if locked else label, self._list)
        item.setData(_PANEL_ID_ROLE, panel_id)
        item.setToolTip(
            f"{label} -- locked: choosing another panel leaves it on screen. Right-click to unlock."
            if locked else label
        )

    def _on_item_chosen(self, item: QListWidgetItem) -> None:
        panel_id = item.data(_PANEL_ID_ROLE)
        if panel_id:
            self.panel_chosen.emit(str(panel_id))

    def _on_list_menu(self, position) -> None:
        item = self._list.itemAt(position)
        if item is None:
            return
        panel_id = str(item.data(_PANEL_ID_ROLE) or "")
        if not panel_id:
            return
        menu, _actions = self.build_panel_menu(panel_id)
        menu.exec(self._list.mapToGlobal(position))

    def build_panel_menu(self, panel_id: str):
        """The right-click menu for one panel, and its actions by name.

        A left click REPLACES what is showing (the rail's whole design: one right-hand panel at a time). Right-click is
        the way to ask for the other things: a panel BESIDE the current one, or a lock so a click elsewhere leaves it
        on screen. Built apart from `exec` so it can be driven without a real popup, which `QMenu.exec` cannot.
        """
        from PySide6.QtWidgets import QMenu

        pinned = panel_id in self._favourites
        locked = panel_id in self._locked
        menu = QMenu(self)
        alongside = menu.addAction("Open beside what is showing")
        lock = menu.addAction("Unlock (a click elsewhere may replace it)" if locked else "Lock open (a click elsewhere leaves it)")
        menu.addSeparator()
        pin = menu.addAction("Unpin from top" if pinned else "Pin to top")
        # ONE bound method for the whole menu, the action carrying (what, which panel): a lambda closing over `self` here
        # is the leak this window has paid for before (PySide6 holds a plain callable strongly).
        for kind, action in (("alongside", alongside), ("lock", lock), ("pin", pin)):
            action.setData((kind, panel_id))
        menu.triggered.connect(self._on_panel_menu_triggered)
        return menu, {"alongside": alongside, "lock": lock, "pin": pin}

    def _on_panel_menu_triggered(self, action) -> None:
        kind, panel_id = action.data()
        if kind == "alongside":
            self.panel_chosen_alongside.emit(panel_id)
        elif kind == "lock":
            self.panel_lock_toggled.emit(panel_id)
        elif kind == "pin":
            self.toggle_favourite(panel_id)

    def toggle_favourite(self, panel_id: str) -> None:
        if panel_id in self._favourites:
            self._favourites.remove(panel_id)
            self.favourite_toggled.emit(panel_id, False)
        else:
            self._favourites.append(panel_id)
            self.favourite_toggled.emit(panel_id, True)
        self._rebuild()
