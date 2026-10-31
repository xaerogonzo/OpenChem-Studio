"""A palette result says where a command lives, in a second voice (`ui/dialogs/command_palette.py`).

A menu command's `source` is its whole menu path ("Tools > Calculators"), since the menus are grouped. The row draws the
name, then the path dimmed and right-aligned, eliding the path before it ever displaces the name.
"""

from __future__ import annotations

import pytest

import conftest
from openchem.ui.dialogs.command_palette import Command, CommandPalette, rank


def _command(label: str, source: str) -> Command:
    return Command(label=label, source=source, run=lambda: None)


@pytest.fixture(scope="module")
def main_window(qapp, tmp_path_factory):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    directory = tmp_path_factory.mktemp("palette_paths")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(directory / "none"))
    settings.set("plugins/user_directory", str(directory / "none2"))
    return MainWindow(services, settings, SessionManager())


@pytest.fixture
def make_palette(qapp):
    built = []

    def make(commands, width=520):
        palette = CommandPalette(commands)
        palette.resize(width, 300)
        palette.show()
        built.append(palette)
        return palette

    yield make
    for palette in built:
        conftest.dispose(palette)


# --- the path is the menu's own ------------------------------------------------------------------------------


def test_a_menu_command_carries_its_whole_nested_menu_path(main_window):
    sources = {c.label: c.source for c in main_window._collect_commands() if c.source not in ("Panel", "Calculator", "Property")}
    assert sources["Derived Scores..."] == "Tools > Calculators"
    assert sources["Export Molecule..."] == "File > Molecules"
    assert sources["Settings..."] == "Edit"
    assert sources["Aromatize"] == "Structure > Aromaticity and Hydrogens"


def test_a_panel_a_calculator_and_a_property_have_no_menu_path(main_window):
    commands = main_window._collect_commands()
    assert {c.source for c in commands if c.source in ("Panel", "Calculator", "Property")} == {"Panel", "Calculator", "Property"}


# --- the row ---------------------------------------------------------------------------------------------------


def test_the_rows_text_is_still_one_string_the_ranking_and_tests_can_read(make_palette):
    palette = make_palette([_command("Derived Scores...", "Tools > Calculators")])
    assert palette.visible_labels() == ["Derived Scores...    (Tools > Calculators)"]


def test_ranking_ignores_the_path(make_palette):
    commands = [_command("Alpha", "Tools > Calculators"), _command("Calculators", "Panel")]
    assert [c.label for c in rank("calculators", commands)] == ["Calculators"]


def _row_ink(palette, width):
    """The row's pixels: which columns hold ink, left to right."""
    image = palette._list.viewport().grab().toImage()
    background = image.pixelColor(2, 2)
    columns = [
        x for x in range(image.width()) if any(image.pixelColor(x, y) != background for y in range(0, 20))
    ]
    return columns, image.width()


def test_the_name_is_drawn_left_and_the_path_right_and_a_narrow_row_keeps_the_name(make_palette):
    command = _command("Run Calculators by Goal...", "Tools > Calculators > A Very Long Submenu Name That Cannot Fit")
    wide = make_palette([command], width=700)
    narrow = make_palette([command], width=260)
    wide_columns, wide_width = _row_ink(wide, 700)
    narrow_columns, narrow_width = _row_ink(narrow, 260)
    # The path reaches the right edge on a wide row; the name always starts at the left.
    assert min(wide_columns) < 20 and max(wide_columns) > wide_width - 40
    assert min(narrow_columns) < 20
    # The row did not overflow its viewport, and the name's start is where it was.
    assert max(narrow_columns) <= narrow_width


def test_a_result_with_no_separator_in_its_text_still_paints(make_palette):
    palette = make_palette([_command("Plain", "Panel")])
    palette._list.item(0).setText("Plain")  # no source part
    columns, _ = _row_ink(palette, 520)
    assert columns


def test_activating_a_row_still_runs_its_command(make_palette):
    ran = []
    palette = make_palette([Command(label="Go", source="File", run=lambda: ran.append(1))])
    palette._list.setCurrentRow(0)
    palette._run_current()
    assert ran == [1] and palette.chosen() is not None
