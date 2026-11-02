"""The drawn menu icons (`ui/menu_icons.py`): every glyph paints, follows the palette, and touches no command."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QPalette

from openchem.ui import menu_icons

from tests.test_menu_layout import window  # noqa: F401 - the real-window fixture, shared


def _ink_pixels(icon: QIcon, mode=QIcon.Mode.Normal) -> int:
    image = icon.pixmap(QSize(32, 32), mode).toImage()
    return sum(1 for x in range(32) for y in range(32) if image.pixelColor(x, y).alpha() > 0)


@pytest.mark.parametrize("glyph", sorted(menu_icons.GLYPHS))
def test_every_glyph_paints_something_and_stays_inside_its_square(qapp, glyph):
    image = menu_icons.icon(glyph).pixmap(QSize(32, 32)).toImage()
    ink = [(x, y) for x in range(32) for y in range(32) if image.pixelColor(x, y).alpha() > 0]
    assert ink, glyph
    # A 1.4 stroke on a 16 grid with round caps: nothing may touch the outer pixel row or column.
    assert all(0 < x < 31 and 0 < y < 31 for x, y in ink), glyph


def test_the_ink_is_the_palettes_and_a_disabled_entry_is_dimmer(qapp):
    palette = QPalette(qapp.palette())
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText, QColor("#ff0000"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#00ff00"))
    previous = QPalette(qapp.palette())
    qapp.setPalette(palette)
    try:
        icon = menu_icons.icon("save")
        normal = icon.pixmap(QSize(32, 32), QIcon.Mode.Normal).toImage()
        disabled = icon.pixmap(QSize(32, 32), QIcon.Mode.Disabled).toImage()
        assert max(normal.pixelColor(x, y).red() for x in range(32) for y in range(32)) == 255
        assert max(disabled.pixelColor(x, y).green() for x in range(32) for y in range(32)) == 255
    finally:
        qapp.setPalette(previous)


def test_a_menu_label_maps_to_a_glyph_only_when_listed():
    assert menu_icons.glyph_for("Save Project") == "save"
    assert menu_icons.glyph_for("Undo Add molecule 'X'") == "undo"
    assert menu_icons.glyph_for("Duplicate Molecule") is None
    assert set(menu_icons.MENU_GLYPHS.values()) <= set(menu_icons.GLYPHS)


def test_an_unknown_glyph_is_refused():
    with pytest.raises(KeyError):
        menu_icons.icon("nope")


def test_the_real_windows_listed_entries_have_icons_and_the_rest_do_not(window):  # noqa: F811
    from openchem.app import menu_layout

    iconed = {
        menu_layout.label_of(action)
        for _path, action in menu_layout.walk(window.menuBar())
        if not action.icon().isNull()
    }
    for expected in ("New Project", "Open Project", "Save Project", "Redo", "Settings", "Exit", "Recalculate Now"):
        assert expected in iconed, expected
    assert not any(label.startswith(("Duplicate", "Paste", "Rename")) for label in iconed)
    # Decoration only: no entry's text, id or shortcut moved (the snapshot test in test_menu_layout holds those).
    assert len(iconed) == 9


def test_builder_made_submenus_are_held_by_the_window_so_a_collection_cannot_destroy_their_commands(window):  # noqa: F811
    """`edit_menu.addMenu(title)` returns a Python-owned wrapper; kept only as a local it was collected, and its four
    commands with it, before `ShortcutRegistry.apply` ran ("QAction already deleted", a flake in whichever test
    constructed the window on a collection boundary; it surfaced as a deterministic failure once unrelated code
    changed the allocation pattern)."""
    import gc

    gc.collect()
    for held in (window._copy_structure_menu, window._structure_display_menu):
        assert held.actions(), held.title()
    assert sorted(a.text() for a in window._copy_structure_menu.actions()) == [
        "InChI",
        "InChIKey",
        "Molfile (MDL molblock)",
        "SMILES",
    ]
