"""Copying ONE fact out of a report, rather than the whole of it.

Two facts can share a label -- an IUPAC name from PubChem and one from our
own engine -- and the only copy that existed took every fact. These go
through a real `QContextMenuEvent` into the value label, because a test that
called the handler directly would pass while the event never reached it.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QPushButton

from openchem.domain.report import Fact, FactCategory, FactLink, StructureReport
from openchem.domain.structure_issue import Basis
from openchem.ui.widgets.fact_view import FactView, _FactRow

import conftest

NAME_A = "[(4R,4aS)-4a-acetyloxy-3-methyl]acetate"
NAME_B = "(5R,9R,13S)-4,5-epoxy-17-methyl-diyl diacetate"


def _fact(label, display, **overrides) -> Fact:
    defaults = dict(
        category=FactCategory.IDENTITY,
        label=label,
        value=display,
        display_value=display,
        source="test",
        basis=Basis.DETERMINISTIC,
    )
    defaults.update(overrides)
    return Fact(**defaults)


def _view(*facts) -> FactView:
    view = FactView()
    view.set_report(StructureReport(molecule_uuid="m1", facts=tuple(facts)), "Subject")
    return view


def _row(view: FactView, text: str) -> _FactRow:
    rows = [r for s in view._sections.values() for r in s.content.findChildren(_FactRow)]
    return next(r for r in rows if r.text() == text)


def _fact_of(row) -> Fact:
    return row.property("openchem_fact")


def _offered(menu) -> list[str]:
    return [a.text() for a in menu.actions() if a.text()]


def _choose(view, row, text: str) -> list[str]:
    """Build the row's menu (never exec it: `QMenu.exec` is modal and cannot
    be patched), apply the action named `text`, and return what it offered."""
    QApplication.clipboard().clear()
    menu, choose = view._row_menu(_fact_of(row), row.selectedText())
    offered = _offered(menu)
    choose(next((a for a in menu.actions() if a.text() == text), None))
    return offered


def test_value_is_selectable_and_keeps_its_height(qapp):
    view = _view(_fact("IUPAC Name", NAME_A))
    row = _row(view, NAME_A)
    # Lazy: building a report must stay cheap, so a row becomes selectable
    # when the pointer first reaches it.
    assert not row.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    before = row.height()
    QApplication.sendEvent(row, QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)))
    assert row.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    assert row.height() == before
    assert row.wordWrap()
    conftest.dispose(view)


def test_same_label_rows_each_copy_their_own_value(qapp):
    view = _view(_fact("IUPAC Name", NAME_A), _fact("IUPAC Name", NAME_B))
    for name in (NAME_A, NAME_B):
        _choose(view, _row(view, name), "Copy value")
        assert QApplication.clipboard().text() == name
        _choose(view, _row(view, name), 'Copy "IUPAC Name: value"')
        assert QApplication.clipboard().text() == f"IUPAC Name: {name}"
    assert "Copied IUPAC Name." in view._status.text()
    conftest.dispose(view)


def test_row_menu_offers_the_report_actions_after_the_row_ones(qapp):
    view = _view(_fact("IUPAC Name", NAME_A))
    offered = _choose(view, _row(view, NAME_A), None)
    assert [t for t in offered if t] == [
        "Copy value",
        'Copy "IUPAC Name: value"',
        "Copy report",
        "Export report...",
        "Compare with...",
        "Open in window",
    ]
    assert QApplication.clipboard().text() == ""
    conftest.dispose(view)


def test_row_menu_still_reaches_the_report_actions(qapp, monkeypatch):
    view = _view(_fact("IUPAC Name", NAME_A), _fact("IUPAC Name", NAME_B))
    called = []
    monkeypatch.setattr(view, "_on_copy_clicked", lambda *a: called.append("report"))
    _choose(view, _row(view, NAME_A), "Copy report")
    assert called == ["report"]
    conftest.dispose(view)


def test_a_partial_selection_is_what_copy_value_copies(qapp):
    view = _view(_fact("IUPAC Name", NAME_A))
    view.resize(900, 300)
    view.show()
    row = _row(view, NAME_A)
    QApplication.sendEvent(row, QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)))
    # Drag across the start of the text: a REAL selection, not a stubbed one.
    QTest.mousePress(row, Qt.MouseButton.LeftButton, pos=QPoint(2, 6))
    QTest.mouseMove(row, QPoint(60, 6))
    QTest.mouseRelease(row, Qt.MouseButton.LeftButton, pos=QPoint(60, 6))
    selected = row.selectedText()
    assert selected and selected != NAME_A and NAME_A.startswith(selected.strip())

    _choose(view, row, "Copy value")
    assert QApplication.clipboard().text() == selected
    # The pair copy ignores the selection entirely.
    _choose(view, row, 'Copy "IUPAC Name: value"')
    assert QApplication.clipboard().text() == f"IUPAC Name: {NAME_A}"
    conftest.dispose(view)


def test_outside_a_value_the_report_wide_menu_is_unchanged(qapp):
    view = _view(_fact("IUPAC Name", NAME_A))
    menu = QMenu()
    view._add_report_actions(menu)
    assert _offered(menu) == [
        "Copy report",
        "Export report...",
        "Compare with...",
        "Open in window",
    ]
    conftest.dispose(view)


def test_a_real_context_event_on_the_value_reaches_the_view(qapp, monkeypatch):
    """The event path itself: a QContextMenuEvent sent to the value label
    must arrive at the view carrying THAT row's fact."""
    seen = []
    monkeypatch.setattr(FactView, "_on_row_context_menu", lambda self, fact, pos: seen.append(fact))
    view = _view(_fact("IUPAC Name", NAME_A), _fact("IUPAC Name", NAME_B))
    row = _row(view, NAME_B)
    pos = QPoint(5, 5)
    QApplication.sendEvent(
        row, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pos, row.mapToGlobal(pos))
    )
    assert [f.value for f in seen] == [NAME_B]
    conftest.dispose(view)


def test_a_linked_row_still_activates_and_its_value_is_copyable(qapp):
    link = FactLink(target="interactions", label="Open")
    view = _view(_fact("Docking", "-7.1 kcal/mol", link=link))
    received = []
    view.link_activated.connect(received.append)
    button = view.findChildren(QPushButton)
    open_button = next(b for b in button if b.text() == ">")
    open_button.click()
    assert received == [link]
    _choose(view, _row(view, "-7.1 kcal/mol"), "Copy value")
    assert QApplication.clipboard().text() == "-7.1 kcal/mol"
    conftest.dispose(view)
