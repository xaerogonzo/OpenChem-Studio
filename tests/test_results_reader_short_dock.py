"""A short dock is a dock of chrome, so the reader gives chrome back first.

Reported with Results docked across the top at 190 px: the reader needed 234
px and was given about 162, so the dock's own scroll area took over. Measured
row by row in the running app (`reader_layout_report`, whose `reader_chrome`
line prints every piece), the 72 px came from a row holding only the pop-out
button (26), a bold title repeating the "Showing" box (22), and air -- 9 px
margins above and below and 6 px between rows. After: 152 against 162, and
the dock does not scroll.

These pin the mechanisms: the title is not drawn but its text is kept; a
short reader gives up its margins and tightens its spacing and a tall one does
not; and a note given a height between whole lines paints only whole lines,
which is the defect the magnified screenshot of the first fix showed.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.ui.widgets.collapsible_section import ClampedLabel
from openchem.ui.widgets.results_view import ResultsView

import conftest

LONG = " ".join(f"Result number {i} with a longish name," for i in range(80))


def _report(report_id: str, name: str) -> ReportResult:
    return ReportResult(
        molecule_uuid="mol-1", report_id=report_id, name=name, category="other",
        facts=tuple(
            Fact(category=FactCategory.IDENTITY, label=f"Fact {i}", value=i,
                 display_value=str(i), source="test", basis=Basis.DETERMINISTIC)
            for i in range(20)
        ),
    )


def _reader(width: int, height: int) -> ResultsView:
    reader = ResultsView("mol-1")
    reader.set_reports((_report("elemental_analysis", "Elemental Analysis"),))
    reader.resize(width, height)
    reader.show()
    for _ in range(5):
        QCoreApplication.processEvents()
    return reader


def test_the_reader_does_not_draw_the_title_the_showing_box_already_names(qapp):
    """Hidden, not emptied: `title_text` and `open_in_window` read the name."""
    reader = _reader(900, 700)
    try:
        reader._focus_box.setCurrentIndex(reader._focus_box.findData("elemental_analysis"))
        QCoreApplication.processEvents()
        view = reader._view
        assert not view._title.isVisible()
        assert view.title_text() == "Elemental Analysis"
        assert reader._focus_box.currentText() == "Elemental Analysis"
    finally:
        conftest.dispose(reader)


def test_a_short_reader_gives_up_its_margins_and_most_of_its_spacing(qapp):
    reader = _reader(1800, 150)
    try:
        assert reader.is_compact()
        margins = reader._layout.contentsMargins()
        assert (margins.top(), margins.bottom()) == (0, 0)
        assert reader._view.is_compact()
    finally:
        conftest.dispose(reader)


def test_a_tall_reader_keeps_the_styles_margins_and_spacing(qapp):
    """The narrow half: 'always compact' passes the guard above and crams
    every ordinary dock."""
    reader = _reader(1800, 700)
    try:
        assert not reader.is_compact()
        assert reader._layout.contentsMargins() == reader._normal_margins
        assert not reader._view.is_compact()
    finally:
        conftest.dispose(reader)


def test_compact_is_what_lowers_the_minimum_and_it_comes_back_when_the_dock_grows(qapp):
    """The point of the mode, measured on the widget: its minimum falls when
    short. And the mode is left again once there is room, so a dock dragged
    taller does not stay cramped."""
    reader = _reader(1800, 700)
    try:
        tall_minimum = reader.minimumSizeHint().height()
        reader.resize(1800, 150)
        for _ in range(5):
            QCoreApplication.processEvents()
        assert reader.is_compact()
        assert reader.minimumSizeHint().height() < tall_minimum, (
            reader.minimumSizeHint().height(), tall_minimum
        )
        reader.resize(1800, 700)
        for _ in range(5):
            QCoreApplication.processEvents()
        assert not reader.is_compact()
    finally:
        conftest.dispose(reader)


def test_a_note_given_a_height_between_lines_paints_only_whole_lines(qapp):
    """The first fix gave the notes 27 px for 18 px lines, and the second line
    was drawn with its bottom half cut off."""
    label = ClampedLabel(LONG, max_lines=3)
    try:
        label.resize(400, 40)
        label.show()
        QCoreApplication.processEvents()
        one = label._lines_height(1, 400)
        two = label._lines_height(2, 400)
        assert one < two, "setup: two lines must be taller than one"
        between = (one + two) // 2
        label.resize(400, between)
        QCoreApplication.processEvents()
        assert not label.mask().isEmpty(), "a height between lines left the partial line painted"
        assert label.mask().boundingRect().height() == one

        # Exactly two lines' height has no partial line to hide.
        label.resize(400, two)
        QCoreApplication.processEvents()
        assert label.mask().isEmpty()
    finally:
        conftest.dispose(label)


def test_a_note_that_fits_is_not_masked(qapp):
    """The narrow half: masking every note would clip a whole one."""
    label = ClampedLabel("One short line.", max_lines=3)
    try:
        label.resize(400, 60)
        label.show()
        QCoreApplication.processEvents()
        assert label.mask().isEmpty()
    finally:
        conftest.dispose(label)
