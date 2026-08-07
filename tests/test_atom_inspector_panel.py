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
    return [s._toggle_button.text() for s in panel._facts._sections.values()]


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
    assert "Atom 10" in widget.title_text()


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
    assert "Atom 10" in widget.title_text()


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
    expanded = {name for name, s in widget._facts._sections.items() if s._toggle_button.isChecked()}
    assert expanded == {"identity", "electronic"}
    assert len(widget._facts._sections) > len(expanded), "something must be collapsed"


# --- search -----------------------------------------------------------------


def test_search_filters_to_matching_facts(panel):
    widget, _bus = panel
    showing(widget, molecule(), CARBONYL_O)
    widget.set_search_text("lewis")
    QCoreApplication.processEvents()
    assert section_titles(widget) == ["Electronic (1)"]
    assert "1 of" in widget.status_text()


def test_search_expands_what_it_matched(panel):
    """A search whose own results hide behind a collapsed header is worse
    than no search."""
    widget, _bus = panel
    showing(widget, molecule(), CARBONYL_O)
    # "oxidation" matches a fact in a category that is COLLAPSED by
    # default. An earlier version searched "ring", which matches nothing
    # on this atom -- zero sections, and `all([])` is vacuously true, so
    # the test passed without exercising anything.
    widget.set_search_text("oxidation")
    QCoreApplication.processEvents()
    assert widget._facts._sections, "the search matched nothing, so this proves nothing"
    assert all(s._toggle_button.isChecked() for s in widget._facts._sections.values())


def test_clearing_the_search_restores_everything(panel):
    widget, _bus = panel
    showing(widget, molecule(), CARBONYL_O)
    before = len(widget._facts._sections)
    widget.set_search_text("lewis")
    QCoreApplication.processEvents()
    widget.set_search_text("")
    QCoreApplication.processEvents()
    assert len(widget._facts._sections) == before


# --- cross-links ------------------------------------------------------------


def test_a_fact_links_to_the_tool_that_produced_it(panel):
    """The inspector is a hub. It answers "what is known" and hands you to
    the tool that owns the detail."""
    widget, _bus = panel
    showing(widget, molecule(), CARBONYL_O)
    followed: list = []
    widget.link_activated.connect(followed.append)

    buttons = [b for s in widget._facts._sections.values() for b in s.findChildren(QPushButton)]
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
    buttons = [b for s in widget._facts._sections.values() for b in s.findChildren(QPushButton)]
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
    widget.set_search_text("lewis")
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
    assert "Select an atom" in widget.status_text()


# --- bonds and molecules ----------------------------------------------------
#
# `AtomReport`'s siblings arrived and reused the whole rendering half of
# this panel unchanged -- sections, search, copy, links. What is new is
# only which subjects the table lists and which report gets built, so that
# is what these cover.


def show_subject(panel: AtomInspectorPanel, model: MoleculeModel, subject: str):
    panel.set_project(ProjectModel(molecules=[model]))
    panel._on_molecule_selected(MoleculeSelected(molecule_uuid=model.uuid))
    panel._subject_combo.setCurrentText(subject)
    QCoreApplication.processEvents()


def test_the_table_lists_bonds_when_the_subject_is_bonds(panel):
    widget, _bus = panel
    model = molecule()
    show_subject(widget, model, "Bond")
    assert widget._atom_table.rowCount() == Chem.MolFromSmiles(CHALCONE).GetNumBonds()


def test_the_bond_rows_are_labelled_readably(panel):
    """"C1:C2" rather than a bare index -- an index alone tells nobody
    which bond they are looking at."""
    widget, _bus = panel
    show_subject(widget, molecule(), "Bond")
    labels = [
        widget._atom_table.item(row, 1).text()
        for row in range(widget._atom_table.rowCount())
    ]
    assert all(label for label in labels)
    assert any(":" in label for label in labels), "chalcone has aromatic bonds"
    assert any("=" in label for label in labels), "and a carbonyl"


def test_selecting_a_bond_row_shows_that_bonds_facts(panel):
    widget, _bus = panel
    show_subject(widget, molecule(), "Bond")
    # By index, not by row -- the table keeps whatever sort order was last
    # applied, and row 0 held bond 16 the first time this was written.
    widget.select_bond(0)
    QCoreApplication.processEvents()
    assert widget._bond_index == 0
    assert "Bond 1" in widget.title_text()
    assert section_titles(widget), "a bond must render some facts"


def test_selecting_a_bond_does_not_emit_an_atom_highlight(panel):
    """The viewers highlight ATOMS. Emitting a bond row's index as an atom
    would highlight an unrelated atom, which is worse than highlighting
    nothing."""
    widget, _bus = panel
    seen: list[int] = []
    widget.atom_selected.connect(seen.append)
    show_subject(widget, molecule(), "Bond")
    widget.select_bond(3)
    QCoreApplication.processEvents()
    assert seen == []


def test_the_molecule_subject_hides_the_row_list(panel):
    """One subject, so a table would be a single inert row inviting a
    click that does nothing."""
    widget, _bus = panel
    show_subject(widget, molecule(), "Molecule")
    assert not widget._atom_table.isVisible() or widget._atom_table.rowCount() == 0


def test_the_molecule_subject_needs_no_selection(panel):
    widget, _bus = panel
    show_subject(widget, molecule(), "Molecule")
    assert "chalcone" in widget.title_text()
    assert section_titles(widget), "the molecule report must render"


def test_switching_subject_re_renders_rather_than_keeping_the_old_facts(panel):
    widget, _bus = panel
    model = molecule()
    showing(widget, model, CARBONYL_O)
    atom_titles = section_titles(widget)
    assert atom_titles

    widget._subject_combo.setCurrentText("Molecule")
    QCoreApplication.processEvents()
    assert "chalcone" in widget.title_text()
    assert "Atom" not in widget.title_text()


def test_each_subject_is_cached_separately(panel):
    """One cache keyed by subject as well as version. Keyed on the index
    alone, an atom report would be served for a bond of the same number."""
    widget, _bus = panel
    model = molecule()
    showing(widget, model, 0)
    widget._subject_combo.setCurrentText("Bond")
    QCoreApplication.processEvents()
    widget.select_bond(0)
    QCoreApplication.processEvents()

    subjects = {key[2] for key in widget._cache}
    assert {"Atom", "Bond"} <= subjects


@pytest.mark.parametrize("fmt", ["Markdown", "Plain text", "JSON", "CSV"])
def test_every_format_handles_every_subject(fmt):
    """`format_report` used to read `report.atom_index` unconditionally,
    which would raise on the other two the first time Copy was pressed."""
    from rdkit.Chem import AllChem

    from openchem.chem.bond_report import build_bond_report
    from openchem.chem.molecule_report import build_molecule_report

    mol = Chem.MolFromSmiles(CHALCONE)
    AllChem.Compute2DCoords(mol)
    for report in (
        build_bond_report(mol, 0, molecule_uuid="m"),
        build_molecule_report(mol, molecule_uuid="m", context={"display_name": "chalcone"}),
    ):
        text = format_report(report, fmt)
        assert text.strip(), f"{fmt} produced nothing"
        if fmt == "JSON":
            payload = json.loads(text)
            assert payload["subject"] in {"bond", "molecule"}


def test_the_json_export_names_its_subject():
    """A consumer receiving a report needs to know what it is about
    without guessing from which keys are present."""
    from openchem.chem.bond_report import build_bond_report

    mol = Chem.MolFromSmiles(CHALCONE)
    payload = json.loads(format_report(build_bond_report(mol, 0), "JSON"))
    assert payload["subject"] == "bond"
    assert "bond_index" in payload
    assert "atom_index" not in payload


# --- picking a bond from the viewers ----------------------------------------


def test_a_ketcher_bond_selection_reaches_the_panel(panel):
    """Ketcher reports bonds through the same `selectionChange` event as
    atoms, and its bond ids are RDKit's -- both dense and in molfile
    order, verified by loading one molblock into each."""
    widget, _bus = panel
    show_subject(widget, molecule(), "Bond")
    widget.select_bond(2)
    QCoreApplication.processEvents()
    assert widget._bond_index == 2
    assert "Bond 3" in widget.title_text()


def test_two_bonded_atom_clicks_select_the_bond_between_them(panel):
    """3Dmol has no bond picking -- `setClickable` hands back an ATOM -- so
    two atoms that happen to be bonded is the only way to name a bond in
    3D using what the library provides."""
    widget, _bus = panel
    show_subject(widget, molecule(), "Bond")

    mol = Chem.MolFromSmiles(CHALCONE)
    bond = mol.GetBondWithIdx(4)
    widget.select_atom(bond.GetBeginAtomIdx())
    widget.select_atom(bond.GetEndAtomIdx())
    QCoreApplication.processEvents()

    assert widget._bond_index == 4


def test_two_unbonded_atom_clicks_start_over_rather_than_failing(panel):
    """Somebody who changed their mind mid-pick clicked a second atom on
    purpose; treating that as an error would be wrong."""
    widget, _bus = panel
    show_subject(widget, molecule(), "Bond")

    mol = Chem.MolFromSmiles(CHALCONE)
    far_apart = [
        (i, j)
        for i in range(mol.GetNumAtoms())
        for j in range(mol.GetNumAtoms())
        if i != j and mol.GetBondBetweenAtoms(i, j) is None
    ][0]
    widget.select_atom(far_apart[0])
    widget.select_atom(far_apart[1])
    QCoreApplication.processEvents()

    assert widget._bond_index is None, "no bond joins them, so none is selected"
    assert widget._pending_bond_atom == far_apart[1], "the pick restarted here"


def test_a_half_finished_pick_does_not_survive_a_subject_change(panel):
    """Otherwise a stray click made in Bond mode completes against an
    unrelated one after the user has moved on."""
    widget, _bus = panel
    show_subject(widget, molecule(), "Bond")
    widget.select_atom(0)
    assert widget._pending_bond_atom == 0

    widget._subject_combo.setCurrentText("Atom")
    QCoreApplication.processEvents()
    assert widget._pending_bond_atom is None


def test_atom_clicks_still_select_atoms_when_the_subject_is_atoms(panel):
    """The two-click behaviour must be confined to Bond mode -- it would
    otherwise break the shipped 3D atom picking."""
    widget, _bus = panel
    showing(widget, molecule())
    widget.select_atom(CARBONYL_O)
    QCoreApplication.processEvents()
    assert widget._atom_index == CARBONYL_O
    assert widget._pending_bond_atom is None


# --- the index spaces do not always match -----------------------------------
#
# A 3D conformer carries EXPLICIT hydrogens; the structure as drawn has
# implicit ones. Ethanol is 3 atoms in the report and 9 in the viewer, so a
# click on a hydrogen sends an index past the end. The heavy atoms agree
# only because `AddHs` appends -- which is why the first three line up and
# nothing warned about the rest.


def test_rdkit_really_raises_on_an_out_of_range_atom_pair():
    """Anchors why the guard exists. If a future RDKit returned None here
    instead, the guard would be belt-and-braces rather than load-bearing,
    and this test says which."""
    mol = Chem.MolFromSmiles("CCO")
    assert mol.GetNumAtoms() == 3
    with pytest.raises(RuntimeError):
        mol.GetBondBetweenAtoms(1, 5)


def test_clicking_a_hydrogen_in_3d_does_not_crash_the_bond_pick(panel):
    """The bug this closes: unguarded, the second click raised
    `RuntimeError: Range Error` inside a Qt signal handler."""
    widget, _bus = panel
    model = molecule("CCO", "ethanol")
    show_subject(widget, model, "Bond")

    widget.select_atom(1)          # a real carbon
    widget.select_atom(5)          # a hydrogen: only exists in the 3D mol
    QCoreApplication.processEvents()

    assert widget._bond_index is None
    assert "not in the structure as drawn" in widget.status_text()


def test_an_out_of_range_atom_does_not_become_a_pending_pick(panel):
    """Otherwise it sits there and completes against the NEXT click,
    naming a bond the user never pointed at."""
    widget, _bus = panel
    show_subject(widget, molecule("CCO", "ethanol"), "Bond")

    widget.select_atom(7)
    QCoreApplication.processEvents()
    assert widget._pending_bond_atom is None


def test_clicking_a_hydrogen_in_atom_mode_explains_itself(panel):
    """It used to no-op in silence, which is indistinguishable from a
    broken handler -- exactly the ambiguity that made two mis-aimed clicks
    hard to interpret during the live check."""
    widget, _bus = panel
    model = molecule("CCO", "ethanol")
    showing(widget, model)

    widget.select_atom(6)
    QCoreApplication.processEvents()
    assert widget._atom_index is None
    assert "Pick a heavy atom" in widget.status_text()


def test_a_heavy_atom_still_selects_normally(panel):
    """The guard must not cost the case that works -- heavy atoms line up
    across both index spaces because AddHs appends."""
    widget, _bus = panel
    model = molecule("CCO", "ethanol")
    showing(widget, model)

    widget.select_atom(2)
    QCoreApplication.processEvents()
    assert widget._atom_index == 2


def test_an_out_of_range_bond_index_is_refused_too(panel):
    widget, _bus = panel
    show_subject(widget, molecule("CCO", "ethanol"), "Bond")

    widget.select_bond(9)
    QCoreApplication.processEvents()
    assert widget._bond_index is None
    assert "not in the structure as drawn" in widget.status_text()


def test_a_hovered_fact_is_bounds_checked_before_it_reaches_a_viewer(panel):
    """The 3D viewer carries EXPLICIT hydrogens and a report does not.

    Ethanol is 3 atoms in a report and 9 in the viewer, so a fact claiming
    atom 7 would ask the viewer to paint something the report never
    described. The mirror image of this mismatch raised
    `RuntimeError: Range Error` inside a Qt signal handler when it was
    assumed rather than checked.
    """
    widget, _bus = panel
    showing(widget, molecule("CCO", "ethanol"), atom=0)
    seen: list[tuple] = []
    widget.atoms_highlighted.connect(seen.append)

    widget._on_highlight_requested((0, 1, 7, 99))

    assert seen == [(0, 1)], "out-of-range indices must be dropped, not forwarded"


def test_a_hover_that_clears_forwards_an_empty_tuple(panel):
    """Otherwise the last fact's atoms stay lit after the pointer leaves."""
    widget, _bus = panel
    showing(widget, molecule("CCO", "ethanol"), atom=0)
    seen: list[tuple] = []
    widget.atoms_highlighted.connect(seen.append)

    widget._on_highlight_requested(())

    assert seen == [()]
