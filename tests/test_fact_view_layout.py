"""The facts are what a reader is for, so they give way LAST.

Reported with Results docked beside Properties at about 380 px: the "35
result(s): ..." summary above the facts and the caveat paragraph below them
were both unbounded, and the fact list between them was squeezed to about two
rows. Measured in the running app before the change, the reader's minimum
height was 1634 px -- taller than the screen -- so the dock's own scroll area
took over and clipped it; after, 277 px.

These pin the mechanism rather than the pixels: that a long note folds and
says so, that the fold survives the note being rewritten, that the reader's
minimum does not include a note's full text, and that the controls row stops
squeezing the filter box.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from openchem.domain.report import Fact, FactCategory, StructureReport
from openchem.domain.structure_issue import Basis
from openchem.ui.widgets.fact_view import MIN_VISIBLE_FACT_ROWS, NOTE_LINES, FactView

import conftest

LONG = " ".join(f"Result number {i} with a longish name," for i in range(60))


def _report() -> StructureReport:
    return StructureReport(
        molecule_uuid="m1",
        facts=tuple(
            Fact(category=FactCategory.IDENTITY, label=f"Fact {i}", value=i,
                 display_value=str(i), source="test", basis=Basis.DETERMINISTIC)
            for i in range(30)
        ),
    )


def _shown(width: int = 380, height: int = 700) -> FactView:
    view = FactView()
    view.resize(width, height)
    view.show()
    view.set_report(_report(), "All results", LONG)
    view.set_status(LONG)
    for _ in range(5):
        QCoreApplication.processEvents()
    return view


def test_a_long_summary_folds_and_offers_the_rest(qapp):
    view = _shown()
    try:
        note = view._summary
        lines = note.label.height() / note.label.fontMetrics().lineSpacing()
        assert lines <= NOTE_LINES + 1, lines
        assert note.is_truncated()
        assert note.toggle.isVisible() and note.toggle.text() == "More"
        assert note.text() == LONG, "folding must never shorten the text itself"
    finally:
        conftest.dispose(view)


def test_more_shows_all_of_it_and_the_choice_survives_a_rewrite(qapp):
    """The fold belongs to the NOTE: the status line is rewritten on every
    search keystroke, and somebody who opened it should find it still open."""
    view = _shown()
    try:
        note = view._status
        note.toggle.click()
        for _ in range(5):
            QCoreApplication.processEvents()
        assert note.label.height() >= note.label.full_height(note.label.width())
        assert note.toggle.text() == "Less"

        view.set_status(LONG + " And a keystroke later.")
        for _ in range(5):
            QCoreApplication.processEvents()
        assert note.label.is_expanded()
    finally:
        conftest.dispose(view)


def test_a_short_note_offers_no_control(qapp):
    """The narrow half: 'always show More' passes the guards above and puts a
    button that does nothing under every one-line note."""
    view = _shown()
    try:
        view.set_status("12 facts.")
        for _ in range(5):
            QCoreApplication.processEvents()
        assert not view._status.toggle.isVisible()
    finally:
        conftest.dispose(view)


def test_the_readers_minimum_does_not_include_a_notes_full_text(qapp):
    """THE REGRESSION ITSELF, at the size it was reported. A binding full
    height was what made the reader taller than its dock."""
    view = _shown()
    try:
        full = view._summary.label.full_height(view._summary.label.width())
        assert full > 200, "setup: the note is not long enough to test anything"
        assert view.minimumSizeHint().height() < full, (
            view.minimumSizeHint().height(), full
        )
    finally:
        conftest.dispose(view)


def test_the_facts_keep_a_floor_measured_in_rows(qapp):
    view = _shown(height=120)
    try:
        floor = view.fontMetrics().lineSpacing() * MIN_VISIBLE_FACT_ROWS
        assert view._area.minimumHeight() >= floor
    finally:
        conftest.dispose(view)


def test_a_narrow_reader_gives_the_filter_its_own_row(qapp):
    view = _shown(width=360)
    try:
        assert view.controls_are_stacked()
        search = view.search_box()
        assert search.width() >= search.fontMetrics().averageCharWidth() * 18
    finally:
        conftest.dispose(view)


def test_a_wide_reader_keeps_one_row(qapp):
    """The narrow half: 'always stack' passes the guard above and spends a
    line of facts in every wide dock."""
    view = _shown(width=1200)
    try:
        assert not view.controls_are_stacked()
    finally:
        conftest.dispose(view)
