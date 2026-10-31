"""The Settings section list has a heading over each group, and a heading is never a page.

With headings in the list a row number is no longer a section's place in `SECTIONS`, so every lookup goes through the id a row
carries. These tests hold that: the groups and the pages describe the same ids, the arrow keys step over a heading, clicking
one changes nothing, and the selected id and the displayed page always agree.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

import conftest
from openchem.app.settings import Settings
from openchem.events.base import EventBus
from openchem.ui.dialogs.settings_dialog import (
    APPEARANCE_SECTION,
    SECTION_GROUPS,
    SECTION_ID_ROLE,
    SECTIONS,
    SettingsDialog,
)


@pytest.fixture
def dialog(qapp):
    built = SettingsDialog(Settings(EventBus()), section=APPEARANCE_SECTION)
    built.show()
    yield built
    conftest.dispose(built)


def _rows(dialog):
    lst = dialog._sections
    return [lst.item(i) for i in range(lst.count())]


def _agree(dialog) -> None:
    """The selected id and the page in front are one thing."""
    section = dialog.current_section()
    assert dialog._pages.currentIndex() == [s for s, _l in SECTIONS].index(section)


# --- the groups and the pages describe the same ids ------------------------------------------------------------


def test_every_section_is_in_exactly_one_group_and_no_group_names_a_stranger():
    grouped = [section for _heading, ids in SECTION_GROUPS for section in ids]
    page_ids = [section for section, _label in SECTIONS]
    assert sorted(grouped) == sorted(page_ids)
    assert len(grouped) == len(set(grouped))
    assert all(ids for _heading, ids in SECTION_GROUPS), "an empty group would be a heading over nothing"


def test_the_list_is_each_heading_then_its_sections_and_appearance_is_first(dialog):
    rows = _rows(dialog)
    expected = []
    for heading, ids in SECTION_GROUPS:
        expected.append((heading, None))
        expected.extend((dict(SECTIONS)[section], section) for section in ids)
    assert [(row.text(), row.data(SECTION_ID_ROLE)) for row in rows] == expected
    assert rows[1].data(SECTION_ID_ROLE) == APPEARANCE_SECTION


def test_a_heading_is_neither_selectable_nor_enabled(dialog):
    for row in _rows(dialog):
        if row.data(SECTION_ID_ROLE) is None:
            assert not row.flags() & Qt.ItemFlag.ItemIsSelectable
            assert not row.flags() & Qt.ItemFlag.ItemIsEnabled


# --- opening by id, the way every caller does ------------------------------------------------------------------


@pytest.mark.parametrize("section", [s for s, _l in SECTIONS])
def test_every_section_opens_by_id_and_shows_its_own_page(dialog, section):
    dialog.show_section(section)
    assert dialog.current_section() == section
    _agree(dialog)
    assert dialog._sections.currentItem().data(SECTION_ID_ROLE) == section


def test_moving_back_and_forth_across_the_group_boundary_keeps_the_page_in_step(dialog):
    last_of_first = SECTION_GROUPS[0][1][-1]
    first_of_second = SECTION_GROUPS[1][1][0]
    for _ in range(3):
        for section in (last_of_first, first_of_second):
            dialog.show_section(section)
            _agree(dialog)


# --- the keyboard ----------------------------------------------------------------------------------------------


def test_arrow_keys_step_over_a_heading(dialog):
    last_of_first = SECTION_GROUPS[0][1][-1]
    first_of_second = SECTION_GROUPS[1][1][0]
    dialog.show_section(last_of_first)
    dialog._sections.setFocus()
    QTest.keyClick(dialog._sections, Qt.Key.Key_Down)
    assert dialog.current_section() == first_of_second
    _agree(dialog)
    QTest.keyClick(dialog._sections, Qt.Key.Key_Up)
    assert dialog.current_section() == last_of_first
    _agree(dialog)


def test_home_and_end_land_on_sections_not_headings(dialog):
    dialog._sections.setFocus()
    QTest.keyClick(dialog._sections, Qt.Key.Key_End)
    assert dialog.current_section() == SECTION_GROUPS[-1][1][-1]
    _agree(dialog)
    QTest.keyClick(dialog._sections, Qt.Key.Key_Home)
    assert dialog.current_section() == SECTION_GROUPS[0][1][0]
    _agree(dialog)


# --- the pointer, and code that tries to make a heading current --------------------------------------------------


def test_clicking_a_heading_changes_nothing(dialog):
    before = dialog.current_section()
    heading = next(row for row in _rows(dialog) if row.data(SECTION_ID_ROLE) is None)
    centre = dialog._sections.visualItemRect(heading).center()
    QTest.mouseClick(dialog._sections.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(centre.x(), centre.y()))
    assert dialog.current_section() == before
    _agree(dialog)


def test_clicking_every_section_opens_it(dialog):
    for row in _rows(dialog):
        section = row.data(SECTION_ID_ROLE)
        if section is None:
            continue
        centre = dialog._sections.visualItemRect(row).center()
        QTest.mouseClick(dialog._sections.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(centre.x(), centre.y()))
        assert dialog.current_section() == section
        _agree(dialog)


def test_code_that_makes_a_heading_current_leaves_the_list_on_its_section(dialog):
    dialog.show_section(SECTION_GROUPS[1][1][0])
    heading = next(row for row in _rows(dialog) if row.data(SECTION_ID_ROLE) is None)
    dialog._sections.setCurrentItem(heading)
    assert dialog.current_section() == SECTION_GROUPS[1][1][0]
    _agree(dialog)
