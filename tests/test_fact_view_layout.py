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
from PySide6.QtWidgets import QLabel

from openchem.domain.report import Fact, FactCategory, FactLink, StructureReport
from openchem.domain.structure_issue import Basis
from openchem.ui.widgets.fact_view import (
    _FACT_PROPERTY,
    MIN_VISIBLE_FACT_ROWS,
    NOTE_LINES,
    FactView,
    _FactRow,
)

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


# --- a value row is exactly as tall as its text --------------------------------
#
# Seen in the running app on the pH-dependent charges' Finding row, Results
# docked at its default width: six lines of text in a 272 px row, then blank to
# the next fact. Measured with `fact_rows_report`: the row held the height its
# text needs at 100 px -- the width Qt gives a child widget before any layout
# pass -- and "Keyed to", a one-line value, held three lines the same way.

#: The reported note, as the charges calculator wrote it for fentanyl.
FINDING = (
    "Computed on the dominant microspecies at pH 7.4, which carries a net charge "
    "of +1 -- the structure as drawn is +0. An amide-like nitrogen reported as "
    "protonated was corrected: its lone pair is delocalised into the adjacent "
    "carbonyl, so it is not a base at this pH."
)
#: Short, but wraps at 100 px: the reported row whose caption sat below its value.
KEYED_TO = "heavy atoms (hydrogens implicit)"


def _charges_report() -> StructureReport:
    def fact(label: str, text: str, link: FactLink | None = None) -> Fact:
        return Fact(
            category=FactCategory.ELECTRONIC, label=label, value=text,
            display_value=text, source="test", basis=Basis.DETERMINISTIC, link=link,
        )

    return StructureReport(
        molecule_uuid="m1",
        facts=(
            fact("Net calculated charge", "1.00 e"),
            fact("Finding", FINDING),
            fact("Keyed to", KEYED_TO),
            # The other shape `_add_row` builds: the value in a row widget
            # beside its ">" button, so its height reaches the form one
            # layout further up.
            fact("Linked", FINDING, link=FactLink(target="calculator_inspector")),
        ),
    )


def _settle() -> None:
    for _ in range(8):
        QCoreApplication.processEvents()


def _charges_view(width: int) -> FactView:
    view = FactView()
    view.resize(width, 900)
    view.show()
    view.set_report(_charges_report(), "Partial Charge", "", expanded=[FactCategory.ELECTRONIC])
    _settle()
    return view


def _value_rows(view: FactView) -> dict[str, _FactRow]:
    return {
        row.property(_FACT_PROPERTY).label: row
        for row in view._container.findChildren(_FactRow)
    }


def _text_height(row: _FactRow, width: int | None = None) -> int:
    """What the row's TEXT needs at `width`, by default the width it has.

    **NEVER THE ROW'S OWN `heightForWidth`.** `QLabel` never answers that below
    its own minimum height, so a row holding a stale fixed height answers with
    that same height and a comparison against it passes on exactly this bug --
    the circular probe docs/ARCHITECTURE.md already records for the Properties
    panel. A fresh label has no minimum to floor it.
    """
    fresh = QLabel()
    fresh.setWordWrap(True)
    fresh.setFont(row.font())
    fresh.setTextFormat(row.textFormat())
    fresh.setText(row.text())
    return fresh.heightForWidth(row.width() if width is None else width)


def test_a_value_row_is_as_tall_as_its_text_and_no_taller(qapp):
    """THE REGRESSION ITSELF, on both row shapes and on a short value too."""
    view = _charges_view(width=420)
    try:
        rows = _value_rows(view)
        assert set(rows) == {"Net calculated charge", "Finding", "Keyed to", "Linked"}
        finding = rows["Finding"]
        assert _text_height(finding, 100) > _text_height(finding), (
            "setup: at this width the note must need fewer lines than at 100 px, "
            "or a height left over from the first pass cannot show"
        )
        for label, row in rows.items():
            assert row.height() == _text_height(row), (
                label, row.width(), row.height(), _text_height(row)
            )
    finally:
        conftest.dispose(view)


def test_a_value_row_comes_back_down_when_the_reader_widens(qapp):
    """THE ADJACENT GESTURE: narrow the dock, then widen it again.

    A height that may only grow is right on the way in and wrong on the way
    back, whatever width the row started at -- so a fix that only corrected
    the first layout pass passes the test above and fails here.

    Every row, and wide as well as narrow: `QLabel`'s own size hint is made
    for a width it picks itself, so a label whose hint stops carrying the
    stated height can be right at one width and wrong at the next. An earlier
    version checked only Finding at 700 px, and such a label passed it.
    """
    view = _charges_view(width=1200)
    try:
        heights = []
        for width in (1200, 360, 1200):
            view.resize(width, 900)
            _settle()
            for label, row in _value_rows(view).items():
                assert row.height() == _text_height(row), (
                    width, label, row.width(), row.height(), _text_height(row)
                )
            heights.append(_value_rows(view)["Finding"].height())
        assert heights[1] > heights[0], f"setup: narrowing did not add a line {heights}"
        assert heights[2] == heights[0], heights
    finally:
        conftest.dispose(view)
