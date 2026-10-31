"""Where each command sits in the menu bar: one table, ordered, grouped, A-Z.

**THE BUILDERS CREATE THE ACTIONS; THIS DECIDES WHERE THEY GO.** `MainWindow._build_*_menu` still makes
every action and documents it (`_document`), with the comments saying why each is wired as it is. Once
all seven menus exist, `arrange` takes each menu's actions and puts them in the order below, so the order
of a menu is a statement in one place that a test can check, not a side effect of the order lines were
written in.

A menu reads, top to bottom: the **first** block (the conventional commands, in the order given), then its
**submenus** (a group named here, or one the builder already made) A-Z by title, then every **loose**
entry no spec named, A-Z, then the **last** block (Exit, Settings, About). Sections are divided by a
separator. Sorting ignores case, the mnemonic `&` and a trailing ellipsis, the rule the Keyboard page
already uses for a command's name.

A label a spec names that no menu holds is logged and skipped, never raised: a renamed entry must not stop
the window opening. `tests/test_menu_layout.py` is what notices.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMenuBar

logger = logging.getLogger("openchem.app")


def label_of(action: QAction) -> str:
    """An action's name as ordering and the specs see it: no mnemonic, no trailing ellipsis."""
    return action.text().replace("&", "").rstrip(".…").strip()


def _sort_key(text: str) -> str:
    return text.casefold()


def _keep_alive(action: QAction) -> None:
    """Give a removed action back to its C++ parent.

    `removeAction` hands the wrapper it is given ownership of the action; setting the parent it already
    has makes it C++-owned again, so collecting the wrapper cannot destroy an action the menu holds.
    """
    parent = action.parent()
    if parent is not None:
        action.setParent(parent)


@dataclass(frozen=True)
class MenuSpec:
    """How one top-level menu is laid out. Every name is a `label_of` value."""

    #: The conventional commands, in this order. A name ending in `*` matches by prefix (Undo's text
    #: follows the undo stack: "Undo Add molecule").
    first: tuple[str, ...] = ()
    #: Submenu title -> the labels that go in it (shown A-Z).
    groups: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    #: Submenu titles whose own entries are sorted A-Z (a builder-made submenu is otherwise left as built).
    sorted_submenus: tuple[str, ...] = ()
    #: Always at the bottom, in this order.
    last: tuple[str, ...] = ()
    #: Keep a separator at the very end, for a menu plugins append to.
    trailing_separator: bool = False


def _find(pool: list[QAction], name: str) -> QAction | None:
    prefix = name.endswith("*")
    wanted = name[:-1] if prefix else name
    for action in pool:
        text = label_of(action)
        if (text.startswith(wanted) if prefix else text == wanted):
            return action
    return None


def sort_menu(menu: QMenu) -> None:
    """Put a flat menu's entries A-Z by label, dropping its separators. Submenus sort by title."""
    actions = [a for a in menu.actions() if not a.isSeparator()]
    for action in menu.actions():
        menu.removeAction(action)
        _keep_alive(action)
    for action in sorted(actions, key=lambda a: _sort_key(label_of(a))):
        menu.addAction(action)


def insert_sorted(menu: QMenu, action: QAction) -> None:
    """Add `action` to an A-Z menu at its place (a plugin panel joining View > Panels)."""
    key = _sort_key(label_of(action))
    for existing in menu.actions():
        if not existing.isSeparator() and _sort_key(label_of(existing)) > key:
            menu.insertAction(existing, action)
            return
    menu.addAction(action)


def arrange(
    menu: QMenu,
    spec: MenuSpec,
    extra_groups: Mapping[str, Iterable[QAction]] | None = None,
) -> dict[str, QMenu]:
    """Re-order one menu by `spec`. Returns the group submenus it made, by title.

    `extra_groups` are submenus whose members are actions the caller holds (the docks' View entries have
    no stable label to name).
    """
    trailing = bool(spec.trailing_separator and menu.actions() and menu.actions()[-1].isSeparator())
    pool = [a for a in menu.actions() if not a.isSeparator()]
    for action in menu.actions():
        menu.removeAction(action)
        _keep_alive(action)

    def take(names: tuple[str, ...]) -> list[QAction]:
        taken = []
        for name in names:
            action = _find(pool, name)
            if action is None:
                logger.warning("Menu layout: %r is named for %s but no such entry exists", name, menu.title())
                continue
            pool.remove(action)
            taken.append(action)
        return taken

    first = take(spec.first)
    last = take(spec.last)
    members: dict[str, list[QAction]] = {title: take(labels) for title, labels in spec.groups.items()}
    for title, actions in (extra_groups or {}).items():
        members.setdefault(title, []).extend(a for a in actions if a in pool)
        for action in actions:
            if action in pool:
                pool.remove(action)

    made: dict[str, QMenu] = {}
    submenu_actions: list[tuple[str, QAction]] = []
    for title, actions in members.items():
        if not actions:
            continue
        # Created WITH its parent, then added: `menu.addMenu(title)` hands back a Python-owned wrapper
        # whose C++ object goes when the caller returns (see `MainWindow._add_theme_menu`).
        sub = QMenu(title, menu)
        for action in sorted(actions, key=lambda a: _sort_key(label_of(a))):
            sub.addAction(action)
            _keep_alive(action)
        made[title] = sub
        submenu_actions.append((title, sub.menuAction()))
    loose: list[QAction] = []
    for action in pool:
        if action.menu() is not None:
            submenu_actions.append((label_of(action), action))
            if label_of(action) in spec.sorted_submenus:
                sort_menu(action.menu())
        else:
            loose.append(action)
    submenu_actions.sort(key=lambda pair: _sort_key(pair[0]))
    loose.sort(key=lambda a: _sort_key(label_of(a)))

    sections = [first, [a for _t, a in submenu_actions], loose, last]
    placed = False
    for section in sections:
        if not section:
            continue
        if placed:
            menu.addSeparator()
        for action in section:
            submenu = action.menu()
            if submenu is not None:
                # `addMenu(QMenu)`, not `addAction(menuAction)`: it is the call whose ownership rules keep the
                # submenu's C++ object with this menu once the wrapper in `made` is collected.
                menu.addMenu(submenu)
                _keep_alive(submenu)
            else:
                menu.addAction(action)
            _keep_alive(action)
        placed = True
    if trailing:
        menu.addSeparator()
    return made


#: Each top-level menu's layout, by its title. The wording of every name is the menu entry's own.
MENU_SPECS: dict[str, MenuSpec] = {
    "File": MenuSpec(
        first=("New Project", "Open Project", "Save Project"),
        groups={
            "Macromolecules and Crystals": ("Import Crystal Structure", "Import Macromolecule", "Receptor Library"),
            "Molecules": ("Energetic Formulation", "Export Molecule", "Import Molecule", "New Molecule"),
        },
        last=("Exit",),
    ),
    "Edit": MenuSpec(
        first=("Undo*", "Redo"),
        sorted_submenus=("Copy Structure As",),
        last=("Settings",),
    ),
    "Structure": MenuSpec(
        groups={
            "Aromaticity and Hydrogens": ("Add/Remove Explicit Hydrogens", "Aromatize", "Dearomatize"),
            "Check": ("Check Structure", "Check Structure in the Editor (Indigo)"),
            "Layout and Clean-up": ("Clean Up", "Layout (Recalculate Coordinates)", "Redraw in 2D"),
        },
    ),
    "View": MenuSpec(
        sorted_submenus=("2D Structure Display",),
        last=("Reset Panel Layout",),
    ),
    "Tools": MenuSpec(
        first=("Recalculate Now",),
        groups={
            "Calculators": (
                "Derived Scores",
                "Lewis Acid-Base Pairing",
                "ORCA Geometry Optimization",
                "Run Calculators by Goal",
                "Virtual Screening",
            ),
            "Reference": ("Identify Structure Online", "Periodic Table", "Quarks and Hadrons"),
        },
        last=("External Tools",),
    ),
    "Plugins": MenuSpec(trailing_separator=True),
    "Help": MenuSpec(
        first=("Help for the Current Panel",),
        groups={"Manual": ("Getting Started", "Scientific Limitations", "User Guide")},
        last=("About OpenChem Studio",),
    ),
}


def menus_of(menu_bar: QMenuBar) -> list[QMenu]:
    """Every menu in the bar, top level and nested, for a caller that must keep their wrappers alive."""
    found: list[QMenu] = []

    def visit(menu: QMenu) -> None:
        found.append(menu)
        for action in menu.actions():
            if action.menu() is not None:
                visit(action.menu())

    for top in menu_bar.actions():
        if top.menu() is not None:
            visit(top.menu())
    return found


def walk(menu_bar: QMenuBar) -> list[tuple[str, QAction]]:
    """Every command in the bar, in the order a person meets it, with its menu path ("Tools > Reference").

    An action offered from two menus is reported at its FIRST home only.
    """
    found: list[tuple[str, QAction]] = []
    seen: set[int] = set()

    def visit(menu: QMenu, path: str) -> None:
        for action in menu.actions():
            if action.isSeparator():
                continue
            sub = action.menu()
            if sub is not None:
                visit(sub, f"{path} > {label_of(action)}")
            elif id(action) not in seen:
                seen.add(id(action))
                found.append((path, action))

    for top in menu_bar.actions():
        if top.menu() is not None:
            visit(top.menu(), label_of(top))
    return found
