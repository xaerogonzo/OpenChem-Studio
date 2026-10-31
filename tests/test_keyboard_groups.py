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
from openchem.ui.dialogs.keyboard_shortcuts_page import CLOSED_GROUPS_KEY, KeyboardShortcutsPage


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


# --- expand all, collapse all, and remembering the arrangement --------------------------------------------------


@pytest.fixture
def remembering(qapp, tmp_path):
    """A window, its Settings, and a way to build pages that remember into those Settings."""
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    settings.remove(CLOSED_GROUPS_KEY)
    window = MainWindow(services, settings, SessionManager())
    pages = []

    def build():
        built = KeyboardShortcutsPage(window._shortcuts, settings=settings)
        pages.append(built)
        return built

    yield build, settings
    for built in pages:
        built.close()
    settings.remove(CLOSED_GROUPS_KEY)
    window.close()


def _open_titles(page):
    return [t for t in page.group_titles() if page.section_of(t).is_expanded()]


def test_expand_all_opens_every_group_and_collapse_all_closes_every_group(remembering):
    build, _settings = remembering
    page = build()
    page._expand_all.click()
    assert _open_titles(page) == page.group_titles()
    page._collapse_all.click()
    assert _open_titles(page) == []


def test_the_arrangement_is_remembered_by_group_id_and_comes_back_on_the_next_page(remembering):
    build, settings = remembering
    first = build()
    first.section_of("Edit").set_expanded(True)
    first.section_of("File").set_expanded(False)
    stored = settings.get(CLOSED_GROUPS_KEY)
    assert "file" in str(stored).split(",") and "Edit" not in str(stored) and ">" not in str(stored)

    again = build()
    assert "Edit" in _open_titles(again) and "File" not in _open_titles(again)


def test_collapse_all_is_remembered_as_none_open(remembering):
    build, _settings = remembering
    build()._collapse_all.click()
    assert _open_titles(build()) == []


def test_an_id_nobody_stored_is_open_and_an_unknown_id_is_ignored(remembering):
    build, settings = remembering
    settings.set(CLOSED_GROUPS_KEY, "edit,no-such-group,")
    page = build()
    assert "Edit" not in _open_titles(page) and "File" in _open_titles(page) and "Structure" in _open_titles(page)


def test_a_settings_store_that_cannot_be_read_gives_the_default_arrangement(remembering, monkeypatch):
    build, settings = remembering

    def broken(*_args, **_kwargs):
        raise OSError("registry unavailable")

    monkeypatch.setattr(settings, "get", broken)
    assert _open_titles(build()) == ["File"]


def test_a_search_never_rewrites_the_remembered_arrangement(remembering):
    build, settings = remembering
    page = build()
    page.show()
    page.section_of("Edit").set_expanded(True)
    before = settings.get(CLOSED_GROUPS_KEY)
    page._search.setText("derived")
    assert page.section_of("Tools > Calculators").is_expanded()
    page.section_of("Tools > Calculators").set_expanded(False)  # by hand, while searching
    assert settings.get(CLOSED_GROUPS_KEY) == before
    page._search.setText("")
    assert not page.section_of("Tools > Calculators").is_expanded()
    assert page.section_of("Edit").is_expanded() and settings.get(CLOSED_GROUPS_KEY) == before


def test_reset_layout_goes_back_to_only_the_first_open_and_forgets_what_was_stored(remembering):
    build, settings = remembering
    page = build()
    page._expand_all.click()
    page._reset_layout.click()
    assert _open_titles(page) == ["File"]
    assert settings.get(CLOSED_GROUPS_KEY, None) is None
    assert _open_titles(build()) == ["File"]


def test_a_page_with_no_settings_still_expands_and_collapses(page):
    page._expand_all.click()
    assert _open_titles(page) == page.group_titles()
    page._reset_layout.click()
    assert _open_titles(page) == ["File"]
