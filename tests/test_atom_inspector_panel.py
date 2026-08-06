"""The Atom Inspector: a view over `AtomReport`, and only a view.

Geometry is asserted as well as content. The Interactions panel shipped a
table whose wrapped cells made every row 481 pixels tall inside a
106-pixel viewport, so it rendered correct data as three blank lines and
every content test passed. Opening the app was the only thing that caught
it, so the guards here check what a reader would actually see.
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QPushButton
from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.domain.atom_report import AtomFact, FactCategory
from openchem.domain.common import CacheState, Provenance
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.scientific_result import PerAtomDataset
from openchem.domain.structure_issue import Basis
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected, PerAtomDataComputed
from openchem.ui.panels.atom_inspector_panel import AtomInspectorPanel, format_report

CHALCONE = "c1ccc(cc1)C=CC(=O)c1ccccc1"
CARBONYL_O = 9
_PROVENANCE = Provenance(created_by="core", method="test")


def dispose(widget) -> None:
    """Destroy one widget now, flushing only ITS deferred delete.

    Never the global `sendPostedEvents(None, DeferredDelete)`: that drains
    every pending delete in the process, including ones other test files
    left queued, which is a double-free.
    """
    widget.setParent(None)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


def molecule(smiles: str = CHALCONE, name: str = "chalcone") -> MoleculeModel:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return MoleculeModel(
        display_name=name, molblock=Chem.MolToMolBlock(mol),
        canonical_smiles=Chem.MolToSmiles(mol),
    )


@pytest.fixture
def panel(qapp):
    bus = EventBus()
    widget = AtomInspectorPanel(ChemistryEngine(), bus)
    widget.resize(380, 800)
    yield widget, bus
    dispose(widget)


def showing(panel: AtomInspectorPanel, model: MoleculeModel, atom: int | None = None):
    panel.set_project(ProjectModel(molecules=[model]))
    panel._on_molecule_selected(MoleculeSelected(molecule_uuid=model.uuid))
    if atom is not None:
        panel.select_atom(atom)
    QCoreApplication.processEvents()


def section_titles(panel: AtomInspectorPanel) -> list[str]:
    return [s._toggle_button.text() for s in panel._sections.values()]


# --- navigation -------------------------------------------------------------


def test_the_atom_table_lists_every_atom(panel):
    widget, _bus = panel
    model = molecule()
    showing(widget, model)
    assert widget._atom_table.rowCount() == Chem.MolFromSmiles(CHALCONE).GetNumAtoms()


def test_the_table_works_without_a_3d_conformer(panel):
    """The primary navigation, and the reason it is the table rather than
    the viewer: a molecule just drawn has no conformer, which is exactly
    when somebody wants to look at an atom."""
    widget, _bus = panel
    model = molecule()
    assert not model.conformers
    showing(widget, model, CARBONYL_O)
    assert "Atom 10" in widget._title.text()


def test_selecting_an_atom_shows_its_facts(panel):
    widget, _bus = panel
    showing(widget, molecule(), CARBONYL_O)
    titles = " ".join(section_titles(widget))
    assert "Identity" in titles and "Electronic" in titles


def test_select_atom_finds_the_row_rather_than_assuming_the_index(panel):
    """The table is sortable, so row number and atom index stop matching
    the moment somebody sorts by element."""
    widget, _bus = panel
    showing(widget, molecule())
    widget._atom_table.sortItems(1)  # by element
    QCoreApplication.processEvents()
    widget.select_atom(CARBONYL_O)
    QCoreApplication.processEvents()
    assert widget._atom_index == CARBONYL_O
    assert "Atom 10" in widget._title.text()


def test_selecting_a_row_announces_the_atom(panel):
    """So a viewer can highlight it."""
    widget, _bus = panel
    seen: list[int] = []
    widget.atom_selected.connect(seen.append)
    showing(widget, molecule(), CARBONYL_O)
    assert seen == [CARBONYL_O]


# --- grouping and disclosure ------------------------------------------------

def test_categories_group_facts_rather_than_producers(panel):
    """Lewis role, lone pairs, formal charge and oxidation state all land
    under one Electronic heading. Grouping by producer would give several
    consecutive "Lewis" headings."""
    widget, _bus = panel
    showing(widget, molecule(), CARBONYL_O)
    electronic = [t for t in section_titles(widget) if t.startswith("Electronic")]
    assert len(electronic) == 1
    assert "Lewis" not in " ".join(section_titles(widget))


def test_most_categories_start_collapsed(panel):
    """Progressive disclosure. A hundred-odd facts rendered flat is a wall,
    and this is much cheaper to design in than to retrofit."""
    widget, _bus = panel
    showing(widget, molecule(), CARBONYL_O)
    # The toggle's checked state, not `isVisible()`: Qt reports any widget
    # with an unshown ancestor as invisible, so on an unshown panel every
    # section looks collapsed and the assertion would pass for the wrong
    # reason.
    expanded = {name for name, s in widget._sections.items() if s._toggle_button.isChecked()}
    assert expanded == {"identity", "electronic"}
    assert len(widget._sections) > len(expanded), "something must be collapsed"


# --- search -----------------------------------------------------------------


def test_search_filters_to_matching_facts(panel):
    widget, _bus = panel
    showing(widget, molecule(), CARBONYL_O)
    widget._search.setText("lewis")
    QCoreApplication.processEvents()
    assert section_titles(widget) == ["Electronic (1)"]
    assert "1 of" in widget._status.text()


def test_search_expands_what_it_matched(panel):
    """A search whose own results hide behind a collapsed header is worse
    than no search."""
    widget, _bus = panel
    showing(widget, molecule(), CARBONYL_O)
    # "oxidation" matches a fact in a category that is COLLAPSED by
    # default. An earlier version searched "ring", which matches nothing
    # on this atom -- zero sections, and `all([])` is vacuously true, so
    # the test passed without exercising anything.
    widget._search.setText("oxidation")
    QCoreApplication.processEvents()
    assert widget._sections, "the search matched nothing, so this proves nothing"
    assert all(s._toggle_button.isChecked() for s in widget._sections.values())


def test_clearing_the_search_restores_everything(panel):
    widget, _bus = panel
    showing(widget, molecule(), CARBONYL_O)
    before = len(widget._sections)
    widget._search.setText("lewis")
    QCoreApplication.processEvents()
    widget._search.setText("")
    QCoreApplication.processEvents()
    assert len(widget._sections) == before


# --- cross-links ------------------------------------------------------------


def test_a_fact_links_to_the_tool_that_produced_it(panel):
    """The inspector is a hub. It answers "what is known" and hands you to
    the tool that owns the detail."""
    widget, _bus = panel
    showing(widget, molecule(), CARBONYL_O)
    followed: list = []
    widget.link_activated.connect(followed.append)

    buttons = [b for s in widget._sections.values() for b in s.findChildren(QPushButton)]
    assert buttons, "no cross-link buttons rendered"
    buttons[0].click()
    QCoreApplication.processEvents()

    assert followed, "clicking a link emitted nothing"
    assert followed[0].target == "periodic_table"
    assert followed[0].params == {"symbol": "O"}


def test_link_payloads_ride_on_the_button_not_a_capturing_lambda(panel):
    """PySide6 holds a connected plain callable STRONGLY, so a lambda
    capturing `self` roots the panel for the life of the process. The
    payload travels as a Qt property and a bound method reads it back
    through `sender()`."""
    widget, _bus = panel
    showing(widget, molecule(), CARBONYL_O)
    buttons = [b for s in widget._sections.values() for b in s.findChildren(QPushButton)]
    assert buttons[0].property("fact_link") is not None


# --- results arriving by event ----------------------------------------------


def test_a_computed_result_joins_the_report_without_being_asked(panel):
    widget, bus = panel
    model = molecule()
    showing(widget, model, CARBONYL_O)
    before = len(widget._report_for(CARBONYL_O).facts)

    bus.publish(PerAtomDataComputed(dataset=PerAtomDataset(
        property_id="gasteiger_charge", name="Partial Charge", units="e", method="rdkit",
        molecule_uuid=model.uuid, values={CARBONYL_O: -0.2712},
        cache_state=CacheState.COMPLETED, provenance=_PROVENANCE)))
    QCoreApplication.processEvents()

    after = widget._report_for(CARBONYL_O)
    assert len(after.facts) == before + 1
    assert any(f.label == "Partial Charge" for f in after.facts)


def test_new_knowledge_invalidates_the_cached_report(panel):
    """A cached report that predates a calculation would show "not
    computed" for something that now exists."""
    widget, bus = panel
    model = molecule()
    showing(widget, model, CARBONYL_O)
    widget._report_for(CARBONYL_O)
    assert widget._cache

    bus.publish(PerAtomDataComputed(dataset=PerAtomDataset(
        property_id="atom_sasa", name="Atom SASA", units="A^2", method="rdkit",
        molecule_uuid=model.uuid, values={CARBONYL_O: 21.0},
        cache_state=CacheState.COMPLETED, provenance=_PROVENANCE)))
    QCoreApplication.processEvents()

    assert any(f.label == "Atom SASA" for f in widget._report_for(CARBONYL_O).facts)


def test_a_result_for_another_molecule_is_kept_apart(panel):
    widget, bus = panel
    mine, other = molecule(), molecule("CCO", "ethanol")
    showing(widget, mine, CARBONYL_O)

    bus.publish(PerAtomDataComputed(dataset=PerAtomDataset(
        property_id="gasteiger_charge", name="Partial Charge", units="e", method="rdkit",
        molecule_uuid=other.uuid, values={CARBONYL_O: 9.9},
        cache_state=CacheState.COMPLETED, provenance=_PROVENANCE)))
    QCoreApplication.processEvents()

    assert not any(f.label == "Partial Charge" for f in widget._report_for(CARBONYL_O).facts)


# --- the never-computes guarantee -------------------------------------------


def test_opening_the_inspector_starts_no_calculation(qapp):
    """The load-bearing guarantee, asserted with a spy rather than
    described. An inspector that launches ORCA when you click an atom is a
    calculator launcher, and people stop trusting it."""
    calls: list = []

    class SpyService:
        def run_calculator(self, *args, **kwargs):
            calls.append(args)

        def request_descriptors(self, *args, **kwargs):
            calls.append(args)

    widget = AtomInspectorPanel(ChemistryEngine(), EventBus())
    widget.resize(380, 800)
    widget._descriptor_service = SpyService()
    showing(widget, molecule(), CARBONYL_O)
    widget._search.setText("lewis")
    QCoreApplication.processEvents()

    assert widget._report_for(CARBONYL_O).facts, "it should still show facts"
    assert calls == []
    dispose(widget)


# --- geometry ---------------------------------------------------------------


def test_the_atom_table_rows_are_single_line(qapp):
    """The Interactions bug: wrapped cells made rows taller than the
    viewport and the panel rendered blank. Asserted as geometry, because
    every content test passed while that was broken."""
    widget = AtomInspectorPanel(ChemistryEngine(), EventBus())
    widget.resize(380, 800)
    widget.show()
    showing(widget, molecule(), CARBONYL_O)

    heights = [widget._atom_table.rowHeight(r) for r in range(widget._atom_table.rowCount())]
    assert heights
    assert max(heights) < 60, heights
    dispose(widget)


def test_no_fact_label_is_clipped(qapp):
    """Wrapped labels report a one-line minimum, so a layout under
    pressure silently cuts their text off. `WrappedLabel` exists for this
    and the panel must actually be using it."""
    from openchem.ui.widgets.collapsible_section import WrappedLabel

    widget = AtomInspectorPanel(ChemistryEngine(), EventBus())
    widget.resize(380, 800)
    widget.show()
    showing(widget, molecule(), CARBONYL_O)
    for _ in range(3):
        QCoreApplication.processEvents()

    clipped = [
        label.text()[:40]
        for label in widget.findChildren(WrappedLabel)
        if label.isVisible() and label.width() > 0
        and label.height() < label.heightForWidth(label.width())
    ]
    assert clipped == []
    dispose(widget)


# --- export -----------------------------------------------------------------


def test_every_export_format_round_trips(panel):
    widget, _bus = panel
    showing(widget, molecule(), CARBONYL_O)
    report = widget._report_for(CARBONYL_O)

    markdown = format_report(report, "Markdown")
    assert markdown.startswith("## Atom 10 (O)")
    assert "| Fact | Value | Source | Basis |" in markdown

    text = format_report(report, "Plain text")
    assert text.startswith("Atom 10 (O)")
    assert "Lewis role: donor" in text

    payload = json.loads(format_report(report, "JSON"))
    assert payload["atom_index"] == CARBONYL_O
    assert any(f["label"] == "Lewis role" for f in payload["facts"])

    rows = format_report(report, "CSV").splitlines()
    assert rows[0] == "category,label,value,units,source,basis"
    assert len(rows) == len(report.facts) + 1


def test_json_export_keeps_the_structure_a_consumer_wants():
    """The reason `value` is `Any` with `display_value` beside it -- an
    exporter, a plugin or the AI assistant wants categories and bases, not
    a pre-rendered wall of text."""
    from openchem.chem.atom_report import build_atom_report

    report = build_atom_report(Chem.MolFromSmiles(CHALCONE), CARBONYL_O, molecule_uuid="m1")
    payload = json.loads(format_report(report, "JSON"))
    fact = next(f for f in payload["facts"] if f["label"] == "Lewis role")
    assert fact["category"] == FactCategory.ELECTRONIC.value
    assert fact["basis"] == Basis.DETERMINISTIC.value
    assert fact["evidence"]


def test_copying_with_no_atom_selected_says_so(panel):
    widget, _bus = panel
    showing(widget, molecule())
    widget._on_copy_clicked()
    assert "Select an atom" in widget._status.text()
