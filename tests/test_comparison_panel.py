"""Molecules side by side, and the rows where they disagree.

The engine existed before this panel and was reachable from exactly one
place: a tab inside `BatchAnalysisDialog`, behind building a batch table
first. "How do these two differ" is a question people ask constantly and
could not get at.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from openchem.chem.comparison import ValueRow, compare_values, differing_rows
from openchem.domain.common import Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis
from openchem.events.base import EventBus
from openchem.events.events import DescriptorComputed, ReportComputed
from openchem.ui.panels.comparison_panel import ComparisonPanel

import conftest


def _dispose(widget) -> None:
    conftest.dispose(widget)


# --- the engine, without any Qt ---------------------------------------------


def test_rows_keep_the_order_the_producers_used():
    """A calculator emits its facts deliberately -- formula before mass
    before composition -- and alphabetising would scatter that."""
    rows = compare_values([
        ("A", {"Formula": ("C9H8O4", ""), "Mass": ("180.16", "g/mol")}),
        ("B", {"Formula": ("C7H6O3", ""), "Mass": ("138.12", "g/mol")}),
    ])
    assert [row.label for row in rows] == ["Formula", "Mass"]


def test_a_property_only_one_molecule_has_still_gets_a_row():
    """And it counts as a DIFFERENCE. A property one has and another does
    not is usually the interesting thing, so hiding it under "differences
    only" would be the more misleading of the two choices."""
    rows = compare_values([
        ("A", {"Shared": ("1", "")}),
        ("B", {"Shared": ("1", ""), "Only B": ("yes", "")}),
    ])
    only = next(row for row in rows if row.label == "Only B")
    assert only.values == ("", "yes")
    assert only.differs


def test_every_row_is_as_wide_as_the_molecule_list():
    """A ragged row would put a number under the wrong heading, which is
    the one failure a comparison table must not have."""
    rows = compare_values([
        ("A", {"X": ("1", "")}),
        ("B", {}),
        ("C", {"Y": ("2", "")}),
    ])
    assert all(len(row.values) == 3 for row in rows), [row.values for row in rows]


def test_differing_rows_keeps_only_the_disagreements():
    rows = compare_values([
        ("A", {"Same": ("1", ""), "Different": ("2", "")}),
        ("B", {"Same": ("1", ""), "Different": ("3", "")}),
    ])
    assert [row.label for row in differing_rows(rows)] == ["Different"]


def test_numeric_values_are_offered_but_not_required():
    """Rows are built from display strings so they can carry "C9H8O4" and
    "ambiphilic" as readily as "180.16"; a consumer that wants to sort or
    plot asks for the numbers."""
    row = ValueRow(label="Mass", units="g/mol", values=("180.16 g/mol", "", "text"), differs=True)
    assert row.numeric_values() == (180.16, None, None)


# --- the panel --------------------------------------------------------------


@pytest.fixture
def panel(qapp):
    bus = EventBus()
    widget = ComparisonPanel(bus)
    yield widget, bus
    _dispose(widget)


def _project() -> ProjectModel:
    return ProjectModel(molecules=[
        MoleculeModel(display_name="Aspirin", canonical_smiles="CC(=O)Oc1ccccc1C(=O)O"),
        MoleculeModel(display_name="Salicylic acid", canonical_smiles="OC(=O)c1ccccc1O"),
    ])


def _descriptor(uuid: str, name: str, value) -> DescriptorComputed:
    return DescriptorComputed(descriptor=DescriptorValue(
        descriptor_id=name.lower().replace(" ", "_"), name=name, units="", category="",
        provider="rdkit", molecule_uuid=uuid, value=value,
    ))


def test_it_shows_nothing_until_two_molecules_are_chosen(panel):
    widget, bus = panel
    project = _project()
    widget.set_project(project)
    bus.publish(_descriptor(project.molecules[0].uuid, "MW", 180.16))

    widget.compare_with([project.molecules[0].uuid])

    assert widget.rows() == []
    assert "Tick two or more" in widget.empty_message()


def test_two_molecules_line_up_their_values(panel):
    widget, bus = panel
    project = _project()
    widget.set_project(project)
    a, b = project.molecules[0].uuid, project.molecules[1].uuid
    bus.publish(_descriptor(a, "MW", 180.16))
    bus.publish(_descriptor(b, "MW", 138.12))

    widget.compare_with([a, b])

    row = next(r for r in widget.rows() if r.label == "MW")
    assert row.values == ("180.2", "138.1")
    assert row.differs


def test_differences_only_hides_the_rows_that_agree(panel):
    """The feature that makes it worth opening."""
    widget, bus = panel
    project = _project()
    widget.set_project(project)
    a, b = project.molecules[0].uuid, project.molecules[1].uuid
    for uuid, mw in ((a, 180.16), (b, 138.12)):
        bus.publish(_descriptor(uuid, "MW", mw))
        bus.publish(_descriptor(uuid, "Rings", 1))
    widget.compare_with([a, b])

    assert {r.label for r in widget.rows()} == {"MW", "Rings"}

    widget._differences_only.setChecked(True)
    assert [r.label for r in widget.rows()] == ["MW"]


def test_agreeing_on_everything_is_reported_as_a_result_not_a_blank(panel):
    """Two molecules matching on every property known IS the answer, and
    showing the same "nothing here" message as an empty table would hide
    it."""
    widget, bus = panel
    project = _project()
    widget.set_project(project)
    a, b = project.molecules[0].uuid, project.molecules[1].uuid
    bus.publish(_descriptor(a, "Rings", 1))
    bus.publish(_descriptor(b, "Rings", 1))
    widget.compare_with([a, b])

    widget._differences_only.setChecked(True)

    assert widget.rows() == []
    assert "agree on everything" in widget.empty_message()


def test_a_report_contributes_each_of_its_facts(panel):
    """Reports and plain descriptors land in the same table -- otherwise
    half of what the app computes would be uncomparable."""
    widget, bus = panel
    project = _project()
    widget.set_project(project)
    a, b = project.molecules[0].uuid, project.molecules[1].uuid
    for uuid, radius in ((a, "2.73"), (b, "2.10")):
        bus.publish(ReportComputed(report=ReportResult(
            molecule_uuid=uuid, report_id="geometry_analysis", name="Geometry",
            category="geometry",
            facts=(Fact(
                category=FactCategory.GEOMETRY, label="Max radius", value=float(radius),
                display_value=radius, source="Geometry", basis=Basis.DETERMINISTIC, units="A",
            ),),
            provenance=Provenance(created_by="core", method="rdkit"),
        )))
    widget.compare_with([a, b])

    row = next(r for r in widget.rows() if r.label == "Max radius")
    assert row.values == ("2.73", "2.10")
    assert row.units == "A"


def test_it_never_starts_a_calculation(panel):
    """A comparison view that silently launches forty calculators is one
    people stop opening. This one only ever remembers what arrived."""
    widget, bus = panel
    project = _project()
    widget.set_project(project)

    widget.compare_with([m.uuid for m in project.molecules])

    # Nothing has been computed for either, so every cell is blank rather
    # than the panel having gone and filled them in.
    assert widget.rows() == []
    assert widget._values == {}


def test_selecting_a_different_molecule_does_not_reshuffle_the_comparison(panel):
    """The ticks are a deliberate choice. Changing them because somebody
    clicked elsewhere in the tree would silently change what the table on
    screen describes."""
    from openchem.events.events import MoleculeSelected

    widget, bus = panel
    project = _project()
    widget.set_project(project)
    a, b = project.molecules[0].uuid, project.molecules[1].uuid
    widget.compare_with([a, b])

    bus.publish(MoleculeSelected(molecule_uuid=b))

    assert widget._chosen == [a, b]


def test_the_table_copies_as_tab_separated_text(panel):
    """A grid pastes into a spreadsheet cleanly only as TSV."""
    widget, bus = panel
    project = _project()
    widget.set_project(project)
    a, b = project.molecules[0].uuid, project.molecules[1].uuid
    bus.publish(_descriptor(a, "MW", 180.16))
    bus.publish(_descriptor(b, "MW", 138.12))
    widget.compare_with([a, b])

    text = widget.as_text()

    assert text.splitlines()[0] == "Property\tAspirin\tSalicylic acid"
    assert "MW\t180.2\t138.1" in text


def test_ticking_survives_a_rename(panel):
    """The list is rebuilt wholesale rather than diffed, so the ticks are
    kept by uuid -- renaming a molecule must not clear the comparison."""
    widget, bus = panel
    project = _project()
    widget.set_project(project)
    a, b = project.molecules[0].uuid, project.molecules[1].uuid
    widget.compare_with([a, b])

    project.molecules[0].display_name = "Renamed"
    widget.set_project(project)

    assert widget._chosen == [a, b]
    checked = [
        widget._molecules.item(i).text()
        for i in range(widget._molecules.count())
        if widget._molecules.item(i).checkState() == Qt.CheckState.Checked
    ]
    assert "Renamed" in checked
