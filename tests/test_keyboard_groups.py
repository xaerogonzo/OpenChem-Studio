"""The Keyboard page's collapsible groups (`ui/dialogs/keyboard_shortcuts_page.py`).

The page used to be one flat list in the order lines were written. It is now one section per menu a command
lives in, in the menus' own order, closed except the first, and a search opens what it finds.
"""

from __future__ import annotations

import pytest

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.ui.dialogs.keyboard_shortcuts_page import KeyboardShortcutsPage


@pytest.fixture
def page(qapp, tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    window = MainWindow(services, settings, SessionManager())
    built = KeyboardShortcutsPage(window._shortcuts)
    yield built
    built.close()
    window.close()


def test_there_is_a_section_per_menu_in_menu_order_and_only_the_first_is_open(page):
    titles = page.group_titles()
    assert titles[0] == "File" and "Tools > Calculators" in titles and "View > Panels" in titles
    assert titles.index("File") < titles.index("Edit") < titles.index("Structure") < titles.index("Tools")
    opened = [t for t in titles if page.section_of(t).is_expanded()]
    assert opened == ["File"]


def test_a_sections_heading_says_how_many_commands_it_holds(page):
    assert page.section_of("Tools > Calculators").title() == "Tools > Calculators (5)"


def test_within_a_section_the_commands_read_as_the_menu_does(page):
    section = page.section_of("Tools > Calculators")
    layout = section.content_layout()
    labels = [layout.itemAt(i, layout.ItemRole.SpanningRole).widget().findChildren(type(page.status))[0].text() for i in range(layout.rowCount())]
    assert labels == sorted(labels, key=str.casefold)


def test_a_search_opens_the_sections_with_a_match_and_hides_the_rest(page):
    page.show()
    page._search.setText("derived")
    assert page.section_of("Tools > Calculators").is_expanded()
    assert page.section_of("Tools > Calculators").isVisibleTo(page)
    assert not page.section_of("File").isVisibleTo(page)
    assert page.section_of("Tools > Calculators").title() == "Tools > Calculators (1 of 5)"


def test_clearing_the_search_puts_every_section_back_as_the_person_left_it(page):
    page.show()
    page.section_of("Edit").set_expanded(True)
    page.section_of("File").set_expanded(False)
    page._search.setText("derived")
    page._search.setText("")
    assert page.section_of("Edit").is_expanded() and not page.section_of("File").is_expanded()
    assert not page.section_of("Tools > Calculators").is_expanded()
    assert all(page.section_of(t).isVisibleTo(page) for t in page.group_titles())
    assert page.section_of("Tools > Calculators").title() == "Tools > Calculators (5)"


def test_rows_are_still_found_by_their_command_id_inside_a_section(page):
    assert page.shortcut_of("settings") == "Ctrl+,"
    assert page.assign("derived_scores", "Ctrl+Alt+F9") is None
    assert page.shortcut_of("derived_scores") == "Ctrl+Alt+F9"
