"""The one renderer every report goes through.

Extracted from `AtomInspectorPanel`, which had grown it inline. The proof
that the extraction is honest is that `tests/test_atom_inspector_panel.py`
still passes against the shared widget; these cover what that panel never
exercised, and what the other report surfaces will depend on.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QPushButton

from openchem.domain.report import (
    CATEGORY_ORDER,
    Detail,
    Fact,
    FactCategory,
    FactLink,
    StructureReport,
)
from openchem.domain.structure_issue import Basis
from openchem.ui.widgets.fact_view import FactView, _FactRow


def _dispose(widget) -> None:
    widget.setParent(None)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


def _fact(label, category=FactCategory.IDENTITY, **overrides) -> Fact:
    defaults = dict(
        category=category,
        label=label,
        value=1.0,
        display_value=f"{label} value",
        source="test",
        basis=Basis.DETERMINISTIC,
    )
    defaults.update(overrides)
    return Fact(**defaults)


def _report(*facts) -> StructureReport:
    return StructureReport(molecule_uuid="m1", facts=tuple(facts))


def _view(report) -> FactView:
    view = FactView()
    view.set_report(report, "Subject")
    return view


def _rows(view: FactView) -> list[_FactRow]:
    return [row for s in view._sections.values() for row in s.content.findChildren(_FactRow)]


def test_it_renders_a_section_per_category(qapp):
    view = _view(_report(
        _fact("Element"),
        _fact("Charge", FactCategory.ELECTRONIC),
        _fact("Ring", FactCategory.STRUCTURE),
    ))
    assert set(view._sections) == {"identity", "electronic", "structure"}
    _dispose(view)


def test_sections_come_out_in_the_declared_order(qapp):
    """A report whose headings shuffle between subjects is unreadable."""
    view = _view(_report(
        _fact("Regulatory", FactCategory.REGULATORY),
        _fact("Element"),
        _fact("Charge", FactCategory.ELECTRONIC),
    ))
    expected = [c.value for c in CATEGORY_ORDER if c.value in view._sections]
    assert list(view._sections) == expected
    _dispose(view)


# --- the depth filter -------------------------------------------------------


def test_advanced_facts_are_hidden_by_default(qapp):
    """A beginner should not be handed Fukui indices, the dual descriptor
    and local softness at once. They are real; they are just not what most
    people opened the panel for."""
    view = _view(_report(
        _fact("Charge", FactCategory.ELECTRONIC),
        _fact("Dual descriptor", FactCategory.ELECTRONIC, detail=Detail.ADVANCED),
    ))
    assert view.visible_fact_labels() == ["Charge"]
    _dispose(view)


def test_choosing_everything_shows_them(qapp):
    view = _view(_report(
        _fact("Charge", FactCategory.ELECTRONIC),
        _fact("Dual descriptor", FactCategory.ELECTRONIC, detail=Detail.ADVANCED),
    ))
    view._detail.setCurrentIndex(1)
    assert sorted(view.visible_fact_labels()) == ["Charge", "Dual descriptor"]
    _dispose(view)


def test_hiding_advanced_facts_says_so_rather_than_dropping_them_quietly(qapp):
    """A filter that hides without admitting it reads as missing data --
    which is the complaint this whole phase started from."""
    view = _view(_report(
        _fact("Charge", FactCategory.ELECTRONIC),
        _fact("Dual descriptor", FactCategory.ELECTRONIC, detail=Detail.ADVANCED),
    ))
    assert "advanced hidden" in view.status_text()
    _dispose(view)


def test_a_category_with_only_advanced_facts_disappears_entirely(qapp):
    """Rather than leaving an empty heading, which reads as a broken
    section rather than a filtered one."""
    view = _view(_report(
        _fact("Charge", FactCategory.ELECTRONIC),
        _fact("Fukui", FactCategory.QUANTUM, detail=Detail.ADVANCED),
    ))
    assert "quantum" not in view._sections
    _dispose(view)


# --- search -----------------------------------------------------------------


def test_search_narrows_to_matching_facts(qapp):
    view = _view(_report(_fact("Element"), _fact("Charge", FactCategory.ELECTRONIC)))
    view._search.setText("charge")
    assert view.visible_fact_labels() == ["Charge"]
    _dispose(view)


def test_search_and_the_depth_filter_compose(qapp):
    """Two axes, two controls. A search that ignored the depth filter would
    surface exactly the facts the reader asked not to see."""
    view = _view(_report(
        _fact("Charge", FactCategory.ELECTRONIC),
        _fact("Charge transfer", FactCategory.ELECTRONIC, detail=Detail.ADVANCED),
    ))
    view._search.setText("charge")
    assert view.visible_fact_labels() == ["Charge"]

    view._detail.setCurrentIndex(1)
    assert sorted(view.visible_fact_labels()) == ["Charge", "Charge transfer"]
    _dispose(view)


def test_a_fact_carrying_a_link_survives_search(qapp):
    """`Fact` is a frozen dataclass and looks hashable, but one holding a
    `FactLink` carries a dict of parameters, and hashing that raises
    TypeError -- so the filter matches by identity. Every fact with a
    cross-link is exactly the kind that has one."""
    view = _view(_report(
        _fact("Element", link=FactLink(target="periodic_table", params={"symbol": "C"})),
    ))
    view._search.setText("element")
    assert view.visible_fact_labels() == ["Element"]
    _dispose(view)


# --- hovering ---------------------------------------------------------------


def test_hovering_a_fact_asks_for_its_atoms(qapp):
    """The third consumer of keeping `Fact.value` structured. That field's
    docstring argued a plugin and the AI assistant would want the
    structure; a viewer wants it too."""
    view = _view(_report(_fact("Ring system", highlight=(2, 3, 4))))
    seen: list[tuple] = []
    view.highlight_requested.connect(seen.append)

    row = _rows(view)[0]
    row.hovered.emit(row.property("openchem_fact"))
    row.hovered.emit(None)

    assert seen == [(2, 3, 4), ()]
    _dispose(view)


def test_a_fact_about_nothing_in_particular_clears_the_highlight(qapp):
    """Molecular weight is not about any atom, so hovering it must not
    leave the previous fact's atoms lit."""
    view = _view(_report(_fact("Molecular weight")))
    seen: list[tuple] = []
    view.highlight_requested.connect(seen.append)

    row = _rows(view)[0]
    row.hovered.emit(row.property("openchem_fact"))

    assert seen == [()]
    _dispose(view)


# --- the detached window ----------------------------------------------------


def test_open_in_window_shows_the_same_report(qapp):
    """Marvin opens each result in its own window and it is genuinely
    useful -- two side by side, or one kept open while you work. The copy
    is a second FactView on the SAME report, so it cannot drift."""
    report = _report(_fact("Element"), _fact("Charge", FactCategory.ELECTRONIC))
    view = _view(report)

    dialog = view.open_in_window()

    assert dialog is not None
    detached = dialog.findChild(FactView)
    assert detached is not None
    assert detached.report() is report
    assert sorted(detached.visible_fact_labels()) == ["Charge", "Element"]
    _dispose(dialog)
    _dispose(view)


def test_open_in_window_with_nothing_shown_does_nothing(qapp):
    view = FactView()
    assert view.open_in_window() is None
    _dispose(view)


def test_a_link_followed_in_the_detached_window_reaches_the_host(qapp):
    """Otherwise a cross-link works in the panel and silently does nothing
    in the window, which is the worse half of the two."""
    view = _view(_report(
        _fact("Element", link=FactLink(target="periodic_table", params={"symbol": "C"})),
    ))
    seen: list = []
    view.link_activated.connect(seen.append)

    dialog = view.open_in_window()
    detached = dialog.findChild(FactView)
    button = next(
        b for s in detached._sections.values()
        for b in s.findChildren(QPushButton)
        if b.text() == ">"
    )
    button.click()

    assert len(seen) == 1
    assert seen[0].target == "periodic_table"
    _dispose(dialog)
    _dispose(view)


# --- clearing ---------------------------------------------------------------


def test_clearing_removes_every_section(qapp):
    view = _view(_report(_fact("Element")))
    assert view._sections

    view.clear("Nothing", "Pick something.")

    assert view._sections == {}
    assert view.status_text() == "Pick something."
    assert view.report() is None
    _dispose(view)


def test_a_summary_is_shown_above_the_sections_and_only_when_there_is_one(qapp):
    """People want formula, weight and a few descriptors immediately, not
    after opening a category."""
    view = FactView()
    view.set_report(_report(_fact("Element")), "Subject")
    assert view._summary.isHidden() or not view._summary.text()

    view.set_report(_report(_fact("Element")), "Subject", "C9H8O4 - 180.16 g/mol")
    assert "180.16" in view._summary.text()

    layout = view.layout()
    order = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert order.index(view._summary) < order.index(view._area)
    _dispose(view)
