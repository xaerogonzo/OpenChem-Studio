"""The "Showing" list is as wide as its longest entry, and says each one in full.

Its popup took the combo's own width and the combo lives in a docked column, so
"Thermophysical Properties (Joback)" and "Interaction energy breakdown (LED)" were
elided to fragments in a list with all the room in the world. Reported from a live
session.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics

from openchem.domain.report import ReportResult
from openchem.ui.widgets.results_view import ResultsView

LONG = "Interaction energy breakdown (LED) computed with a deliberately long method name"


def _reader() -> ResultsView:
    reader = ResultsView("mol-1")
    reader.set_reports([
        ReportResult(molecule_uuid="mol-1", report_id="a", name="Short", facts=(), category="identity"),
        ReportResult(molecule_uuid="mol-1", report_id="b", name=LONG, facts=(), category="quantum_chemistry"),
    ])
    return reader


def test_the_popup_is_at_least_as_wide_as_the_longest_entry(qapp):
    reader = _reader()
    box = reader._focus_box
    box.resize(150, 24)  # a docked column
    reader._fit_focus_popup()
    metrics = QFontMetrics(box.font())
    widest = max(metrics.horizontalAdvance(box.itemText(i)) for i in range(box.count()))
    assert widest > box.width(), "setup: the longest entry really is wider than the control"
    assert box.view().minimumWidth() >= widest


def test_the_closed_control_is_not_widened(qapp):
    """Only the POPUP grows: a wide combo would push the docked column's minimum up."""
    reader = _reader()
    box = reader._focus_box
    box.resize(150, 24)
    reader._fit_focus_popup()
    assert box.minimumSizeHint().width() < box.view().minimumWidth()


def test_every_entry_carries_its_full_text_as_a_tooltip(qapp):
    reader = _reader()  # held: the box is a child of it and dies with it
    box = reader._focus_box
    for index in range(box.count()):
        assert box.itemData(index, Qt.ItemDataRole.ToolTipRole) == box.itemText(index)
    assert LONG in [box.itemData(i, Qt.ItemDataRole.ToolTipRole) for i in range(box.count())]


def test_a_narrower_popup_is_never_asked_for(qapp):
    """It never narrows below the control that opened it."""
    reader = _reader()
    box = reader._focus_box
    box.resize(900, 24)
    reader._fit_focus_popup()
    assert box.view().minimumWidth() >= 900
