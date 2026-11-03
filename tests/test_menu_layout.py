"""The menu bar's order, and that reordering it moved nothing a person had set (`app/menu_layout.py`).

A real `MainWindow`, because the thing under test is where the real actions ended up. The snapshot in
`tests/fixtures/menu_commands.json` was taken from the window BEFORE the layout existed: every command id,
its label and its default shortcut. A saved shortcut is stored under the id, so a changed id loses it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openchem.app import menu_layout
from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container

SNAPSHOT = Path(__file__).parent / "fixtures" / "menu_commands.json"

#: Alive for the whole module: an action is destroyed when its last wrapper is collected.
_KEEP_ALIVE: list = []


@pytest.fixture
def window(qapp, tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    built = MainWindow(services, settings, SessionManager())
    yield built
    built.close()


def _key(text: str) -> str:
    return text.replace("&", "").rstrip(".…").strip().casefold()


def _children(menu):
    return [a for a in menu.actions() if not a.isSeparator()]


def _blocks(menu):
    """The menu's entries split at its separators: [[first block], [submenus], [loose], [last]]."""
    blocks, current = [], []
    for action in menu.actions():
        if action.isSeparator():
            blocks.append(current)
            current = []
        else:
            current.append(action)
    blocks.append(current)
    return [b for b in blocks if b]


def _top(window, title):
    [top] = [a for a in window.menuBar().actions() if _key(a.text()) == title.casefold()]
    _KEEP_ALIVE.append(top)
    return top.menu()


# --- nothing a person set moved ---------------------------------------------------------------------------------------------------------------------


def test_every_command_id_label_and_default_shortcut_is_what_it_was_before_the_layout(window):
    registry = window._shortcuts
    now = sorted(
        ({"id": c, "label": registry._labels[c], "default": registry._defaults[c]} for c in registry._actions),
        key=lambda r: r["id"],
    )
    assert now == json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_no_command_action_is_destroyed_by_the_rearranging(window):
    import shiboken6

    assert all(shiboken6.isValid(a) for a in window._shortcuts._actions.values())
    assert window._shortcuts.entries()


def test_no_menu_or_entry_is_lost_when_the_wrappers_the_builders_dropped_are_collected(window):
    """A submenu whose Python wrapper was collected took its entries with it (measured: after one collection every
    grouped submenu, Theme and 2D Structure Display were gone, and the palette lost every command in them)."""
    import gc

    def entries():
        return sorted(path + " | " + a.text() for path, a in menu_layout.walk(window.menuBar()))

    before = entries()
    gc.collect()
    assert entries() == before and len(before) >= 80


def test_no_two_commands_share_a_default_shortcut(window):
    held = [e.default for e in window._shortcuts.entries() if e.default]
    assert len(held) == len(set(held))


# --- the order ----------------------------------------------------------------------------------------------------------------------------------


def test_every_name_the_layout_table_uses_is_a_real_menu_entry(window):
    """A renamed entry would otherwise just stop being placed (the builder only logs it)."""
    present = {_key(a.text()) for _p, a in menu_layout.walk(window.menuBar())}
    for title, spec in menu_layout.MENU_SPECS.items():
        names = list(spec.first) + list(spec.last) + [n for labels in spec.groups.values() for n in labels]
        for name in names:
            if name.endswith("*"):
                assert any(p.startswith(_key(name[:-1])) for p in present), (title, name)
            else:
                assert _key(name) in present, (title, name)


@pytest.mark.parametrize("title", list(menu_layout.MENU_SPECS))
def test_a_menus_submenus_and_loose_entries_are_each_a_to_z(window, title):
    menu = _top(window, title)
    for block in _blocks(menu):
        names = [_key(a.text()) for a in block]
        pinned = {_key(n.rstrip("*")) for n in list(menu_layout.MENU_SPECS[title].first) + list(menu_layout.MENU_SPECS[title].last)}
        if any(any(n.startswith(p) for p in pinned) for n in names):
            continue  # the conventional blocks keep their own order
        assert names == sorted(names), (title, names)


def test_a_group_submenu_is_a_to_z(window):
    for path, group in (("Tools", "Calculators"), ("Tools", "Reference"), ("File", "Molecules"), ("Help", "Manual")):
        [sub] = [a for a in _children(_top(window, path)) if a.menu() is not None and _key(a.text()) == group.casefold()]
        _KEEP_ALIVE.append(sub)
        names = [_key(a.text()) for a in _children(sub.menu())]
        assert names == sorted(names) and len(names) >= 2


def test_the_conventional_commands_stay_where_people_look(window):
    file_names = [_key(a.text()) for a in _children(_top(window, "File"))]
    assert file_names[:3] == ["new project", "open project", "save project"] and file_names[-1] == "exit"
    edit_names = [_key(a.text()) for a in _children(_top(window, "Edit"))]
    assert edit_names[0].startswith("undo") and edit_names[1] == "redo" and edit_names[-1] == "settings"
    help_names = [_key(a.text()) for a in _children(_top(window, "Help"))]
    assert help_names[0] == "help for the current panel" and help_names[-1] == "about openchem studio"


def test_every_panel_is_in_view_panels_a_to_z_and_a_plugin_panel_joins_in_its_place(window, qapp):
    [panels] = [a for a in _children(_top(window, "View")) if _key(a.text()) == "panels"]
    _KEEP_ALIVE.append(panels)
    before = [_key(a.text()) for a in _children(panels.menu())]
    assert before == sorted(before) and len(before) >= 12
    from PySide6.QtWidgets import QLabel

    window.add_panel("Zeta Plugin Panel", lambda: QLabel("x"))
    window.add_panel("Alpha Plugin Panel", lambda: QLabel("x"))
    after = [_key(a.text()) for a in _children(panels.menu())]
    assert after == sorted(after) and "alpha plugin panel" in after and "zeta plugin panel" in after


def test_a_command_in_two_menus_is_reported_at_its_first_home_only(window):
    paths = [p for p, a in menu_layout.walk(window.menuBar()) if "CIP" in a.text()]
    assert paths == ["Structure"] and len(paths) == 1


# --- the Keyboard page's groups come from the menus ------------------------------------------------------------------------------------


def test_each_command_knows_its_menu_and_the_page_lists_them_in_menu_order(window):
    entries = window._shortcuts.entries()
    # In the menus' order. A menu's own commands can come on both sides of its submenus (File: New
    # Project ... then Molecules, then Exit); the page puts them under one heading, at its first.
    groups = list(dict.fromkeys(entry.group for entry in entries))
    assert groups[0] == "File" and groups.index("File") < groups.index("File > Molecules") < groups.index("Edit") and "Tools > Calculators" in groups and "View > Panels" in groups
    assert [e for e in entries if e.command_id == "settings"][0].group == "Edit"
    assert [e for e in entries if e.command_id == "command_palette"][0].group == "Window"
