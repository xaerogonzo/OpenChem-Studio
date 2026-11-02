"""Compare cells know where they came from, and a double-click opens them in Results.

The table used to keep `(display, units)` and nothing else, so a value could not be traced to
its report and two reports that both said "Energy" were one row.
"""

from __future__ import annotations

import pytest

from openchem.chem.comparison import CompareCell, compare_values, finite_number
from openchem.domain.common import Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis
from openchem.events.base import EventBus
from openchem.events.events import DescriptorComputed, MoleculeSelected, ReportComputed
from openchem.ui.panels.comparison_panel import ComparisonPanel

import conftest


def _cell(display, key, report="r", label=None, number=None, units=""):
    return CompareCell(
        display=display, units=units, numeric_value=number, row_key=key,
        report_id=report, fact_label=label or key.split("::")[-1],
    )


# --- the engine, without Qt -------------------------------------------------


def test_two_reports_with_the_same_wording_are_two_rows():
    rows = compare_values([
        ("A", {"orca::Energy": _cell("-76.4", "orca::Energy", "orca", "Energy"),
               "psi4::Energy": _cell("-76.3", "psi4::Energy", "psi4", "Energy")}),
        ("B", {"orca::Energy": _cell("-154.9", "orca::Energy", "orca", "Energy")}),
    ])
    assert [row.row_key for row in rows] == ["orca::Energy", "psi4::Energy"]
    # Never two indistinguishable rows on screen.
    assert len({row.label for row in rows}) == 2
    assert rows[0].label == "Energy [orca]"
    # The wording each reveal needs is untouched by the disambiguation.
    assert rows[0].cells[0].fact_label == "Energy"


def test_a_unique_label_is_left_exactly_as_it_was():
    rows = compare_values([("A", {"r::Mass": _cell("18", "r::Mass", "r", "Mass")})])
    assert rows[0].label == "Mass"


def test_cells_line_up_with_molecules_and_missing_ones_are_none():
    rows = compare_values([
        ("A", {"r::X": _cell("1", "r::X")}),
        ("B", {}),
        ("C", {"r::X": _cell("3", "r::X")}),
    ])
    assert [c.display if c else None for c in rows[0].cells] == ["1", None, "3"]
    assert rows[0].values == ("1", "", "3")


def test_numbers_are_the_producers_own_not_parsed_text():
    rows = compare_values([
        ("A", {"r::M": _cell("18.02", "r::M", number=18.0153)}),
        ("B", {"r::M": _cell("46.07", "r::M", number=46.0684)}),
    ])
    assert rows[0].numbers() == (18.0153, 46.0684)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "3", None])
def test_only_real_finite_numbers_count(value):
    assert finite_number(value) is None


def test_source_cell_skips_a_blank_first_column():
    rows = compare_values([
        ("A", {}),
        ("B", {"r::X": _cell("2", "r::X")}),
    ])
    index, cell = rows[0].source_cell()
    assert (index, cell.display) == (1, "2")


# --- the panel ----------------------------------------------------------------


@pytest.fixture
def panel(qapp):
    bus = EventBus()
    widget = ComparisonPanel(bus)
    yield widget, bus
    conftest.dispose(widget)


def _project() -> ProjectModel:
    return ProjectModel(molecules=[
        MoleculeModel(display_name="Water", canonical_smiles="O"),
        MoleculeModel(display_name="Ethanol", canonical_smiles="CCO"),
    ])


def _descriptor(uuid, name, value, did=None):
    return DescriptorComputed(descriptor=DescriptorValue(
        descriptor_id=did or name.lower(), name=name, units="", category="",
        provider="rdkit", molecule_uuid=uuid, value=value,
    ))


def _report(uuid, report_id, label, value):
    return ReportComputed(report=ReportResult(
        molecule_uuid=uuid, report_id=report_id, name=report_id, category="geometry",
        facts=(Fact(category=FactCategory.GEOMETRY, label=label, value=value,
                    display_value=str(value), source="x", basis=Basis.DETERMINISTIC),),
        provenance=Provenance(created_by="core", method="rdkit"),
    ))


def _ready(panel):
    widget, bus = panel
    project = _project()
    widget.set_project(project)
    a, b = project.molecules[0].uuid, project.molecules[1].uuid
    bus.publish(_descriptor(a, "MW", 18.015))
    bus.publish(_descriptor(b, "MW", 46.07))
    bus.publish(_report(b, "geometry_analysis", "Max radius", 2.1))
    widget.compare_with([a, b])
    return widget, a, b


def _row(widget, label):
    return next(i for i, r in enumerate(widget._shown_rows) if r.label == label)


def test_a_descriptor_cell_opens_the_descriptor_aggregate(panel):
    widget, a, b = _ready(panel)
    assert widget.target_at(_row(widget, "MW"), 2) == (b, DESCRIPTOR_AGGREGATE_ID, "MW")
    assert widget.target_at(_row(widget, "MW"), 1) == (a, DESCRIPTOR_AGGREGATE_ID, "MW")


def test_a_report_cell_opens_its_own_report(panel):
    widget, a, b = _ready(panel)
    assert widget.target_at(_row(widget, "Max radius"), 2) == (b, "geometry_analysis", "Max radius")


def test_a_blank_cell_has_no_target_and_says_why(panel):
    widget, a, b = _ready(panel)
    row = _row(widget, "Max radius")
    assert widget.target_at(row, 1) is None
    seen = []
    widget.fact_activated.connect(lambda *args: seen.append(args))
    assert widget.activate(row, 1) is False
    assert seen == []
    assert "has not been run" in widget._status.text()


def test_the_property_column_opens_the_first_molecule_that_has_the_value(panel):
    """Water has no 'Max radius'; opening the first column's blank would be the wrong answer."""
    widget, a, b = _ready(panel)
    assert widget.target_at(_row(widget, "Max radius"), 0) == (b, "geometry_analysis", "Max radius")


def test_every_gesture_goes_through_one_activation(panel):
    widget, a, b = _ready(panel)
    seen = []
    widget.fact_activated.connect(lambda *args: seen.append(args))
    row = _row(widget, "MW")

    widget._on_cell_double_clicked(row, 2)
    widget._table.setCurrentCell(row, 2)
    widget._on_show_clicked()
    widget._activate_current()

    assert seen == [(b, DESCRIPTOR_AGGREGATE_ID, "MW")] * 3


def test_exports_are_unchanged_by_the_new_metadata(panel):
    widget, a, b = _ready(panel)
    text = widget.as_text()
    assert text.splitlines()[0] == "Property\tWater\tEthanol"
    assert "MW\t18.02\t46.07" in text


# --- the real window ---------------------------------------------------------------


@pytest.fixture(scope="module")
def main_window(qapp, tmp_path_factory):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    directory = tmp_path_factory.mktemp("compare_to_results")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(directory / "none"))
    settings.set("plugins/user_directory", str(directory / "none2"))
    window = MainWindow(services, settings, SessionManager())
    yield window
    # Revealing Results from Compare pops it out into a top-level window; leaving this window alive
    # would leave that window behind for whichever test next counts the process's windows.
    conftest.dispose(window)


def _molecule(window, name, smiles):
    """A molecule the application can really compute on."""
    return window._services.chemistry_engine.set_structure_from_smiles(
        MoleculeModel(display_name=name), smiles
    )


def _wait_for(qapp, condition, seconds=30):
    import time

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_double_click_selects_the_molecule_and_focuses_the_fact_in_results(main_window, qapp):
    """End to end: the descriptors the application itself computes when a molecule is selected,
    then another molecule is selected, then Compare asks for the first one's value."""
    window = main_window
    project = window._session.project
    water = _molecule(window, "Water", "O")
    ethanol = _molecule(window, "Ethanol", "CCO")
    project.molecules.extend([water, ethanol])
    window._comparison_panel.set_project(project)
    panel = window._comparison_panel
    bus = window._services.event_bus

    for molecule in (ethanol, water):
        bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
        assert _wait_for(
            qapp, lambda: len(panel._values.get(molecule.uuid, {})) > 10
        ), "descriptors never arrived"
    panel.compare_with([water.uuid, ethanol.uuid])
    row = next(i for i, r in enumerate(panel._shown_rows) if r.label == "Molecular Weight")

    assert panel.activate(row, 2)

    assert window._session.selected_molecule_uuid == ethanol.uuid
    assert window._results_view.molecule_uuid() == ethanol.uuid
    assert window._results_view.focus() == DESCRIPTOR_AGGREGATE_ID
    assert window._results_view._view.visible_fact_labels() == ["Molecular Weight"]
    assert "Showing Molecular Weight for Ethanol" in panel._status.text()
    # The comparison itself did not move with the selection.
    assert panel._chosen == [water.uuid, ethanol.uuid]


def test_a_value_that_is_no_longer_stored_says_so_instead_of_doing_nothing(main_window):
    window = main_window
    project = window._session.project
    gone = MoleculeModel(display_name="Gone", canonical_smiles="C")
    project.molecules.append(gone)
    window._comparison_panel.set_project(project)

    window._on_compare_fact_activated(gone.uuid, "geometry_analysis", "Max radius")

    assert "no stored result" in window._comparison_panel._status.text()

    window._on_compare_fact_activated("not-a-uuid", "x", "y")
    assert "no longer in the project" in window._comparison_panel._status.text()


# --- Calculate basic properties ----------------------------------------------------


def test_calculate_basics_is_off_until_two_are_ticked_and_asks_for_exactly_those(panel):
    widget, bus = panel
    project = _project()
    widget.set_project(project)
    a, b = project.molecules[0].uuid, project.molecules[1].uuid
    asked = []
    widget.calculate_requested.connect(lambda uuids: asked.append(uuids))

    widget.compare_with([a])
    assert not widget._calculate_button.isEnabled()
    assert "Needs two or more" in widget._calculate_button.toolTip()

    widget.compare_with([a, b])
    assert widget._calculate_button.isEnabled()
    widget._calculate_button.click()
    assert asked == [[a, b]]


def test_progress_survives_the_re_renders_each_arriving_value_causes(panel):
    widget, bus = panel
    project = _project()
    widget.set_project(project)
    a, b = project.molecules[0].uuid, project.molecules[1].uuid
    widget.compare_with([a, b])
    widget._calculate_button.click()
    assert "0 of 2" in widget._status.text()

    bus.publish(_descriptor(a, "MW", 18.0))
    assert "1 of 2" in widget._status.text()
    bus.publish(_descriptor(a, "Rings", 0))
    bus.publish(_descriptor(b, "MW", 46.0))
    assert "Basic properties are in" in widget._status.text()
    # Said once: the next render is the table's own line again.
    bus.publish(_descriptor(b, "Rings", 0))
    assert "Basic properties are in" not in widget._status.text()


def test_a_molecule_that_cannot_start_does_not_leave_progress_hanging(panel):
    widget, bus = panel
    project = _project()
    widget.set_project(project)
    a, b = project.molecules[0].uuid, project.molecules[1].uuid
    widget.compare_with([a, b])
    widget._calculate_button.click()
    bus.publish(_descriptor(a, "MW", 18.0))

    widget.calculation_skipped([b])

    assert "Basic properties are in" in widget._status.text()


def test_the_window_computes_the_ticked_molecules_and_compare_fills_in(main_window, qapp):
    """The real thing: nothing computed, press the button, the table fills in, and nothing
    was computed for a molecule that was not ticked."""
    window = main_window
    project = window._session.project
    water = _molecule(window, "Water2", "O")
    ethanol = _molecule(window, "Ethanol2", "CCO")
    bystander = _molecule(window, "Methane", "C")
    project.molecules.extend([water, ethanol, bystander])
    panel = window._comparison_panel
    panel.set_project(project)
    panel.compare_with([water.uuid, ethanol.uuid])
    assert panel._shown_rows == []

    panel._calculate_button.click()

    assert _wait_for(
        qapp, lambda: any(r.label == "Molecular Weight" for r in panel._shown_rows)
    ), "the table never filled in"
    row = next(r for r in panel._shown_rows if r.label == "Molecular Weight")
    assert all(row.values), row.values
    assert row.numbers()[0] == pytest.approx(18.015, abs=0.01)
    assert bystander.uuid not in panel._values


# --- plain English and who is higher ---------------------------------------------------


def _numeric_cell(display, number, help_id, units=""):
    return CompareCell(
        display=display, units=units, numeric_value=number, row_key=help_id,
        report_id="molecular_properties", fact_label=help_id, help_id=help_id,
    )


def _row_of(help_id, *numbers, units=("",) * 8):
    columns = [
        (f"M{i}", {help_id: _numeric_cell(str(n), n, help_id, units[i])} if n is not None else {})
        for i, n in enumerate(numbers)
    ]
    return compare_values(columns)[0]


def test_direction_names_the_highest_and_lowest_and_a_factor_only_on_a_ratio_scale():
    from openchem.chem.comparison import direction

    mass = direction(_row_of("descriptor.mol_wt", 18.0, 46.0))
    assert (mass.highest, mass.lowest) == ((1,), (0,))
    assert mass.factor == pytest.approx(46.0 / 18.0)

    # LogP is a log scale: ordered, never "x times".
    logp = direction(_row_of("descriptor.mol_logp", 0.5, 2.0))
    assert (logp.highest, logp.factor) == ((1,), None)


def test_direction_says_nothing_it_should_not():
    from openchem.chem.comparison import direction

    assert direction(_row_of("descriptor.formula", 1.0, 2.0)) is None, "no policy for this row"
    assert direction(_row_of("descriptor.mol_wt", 18.0, None)) is None, "one value is not a comparison"
    assert direction(_row_of("descriptor.mol_wt", 18.0, 18.0)) is None, "a tie has no highest"
    assert direction(_row_of("descriptor.mol_wt", 18.0, 46.0, units=("g/mol", "kg/mol"))) is None
    assert direction(_row_of("descriptor.mol_wt", 18.0, float("nan"))) is None


def test_ties_for_the_highest_are_all_marked_and_a_missing_value_is_not_zero():
    from openchem.chem.comparison import direction

    found = direction(_row_of("descriptor.num_hbd", 2, 2, 0, None))
    assert found.highest == (0, 1)
    assert found.lowest == (2,)


def test_a_zero_or_negative_lowest_gets_no_factor():
    from openchem.chem.comparison import direction

    assert direction(_row_of("descriptor.tpsa", 0.0, 20.0)).factor is None


def test_the_summary_is_only_for_two_molecules_and_only_reviewed_rows():
    from openchem.chem.comparison import summary_sentence

    rows = [
        _row_of("descriptor.mol_wt", 18.0, 46.0),
        _row_of("descriptor.formula", 1.0, 2.0),
    ]
    text = summary_sentence(["Water", "Ethanol"], rows)
    assert text.startswith("By these calculated numbers:")
    assert "Ethanol is heavier" in text
    assert "formula" not in text.lower()
    assert summary_sentence(["A", "B", "C"], rows) == ""
    assert summary_sentence(["Water", "Ethanol"], [rows[1]]) == ""


def test_no_plain_text_says_a_value_is_better_or_worse():
    import re

    from openchem.ui.fact_help import CONTRACTS, PLAIN, plain_for

    for help_id, text in PLAIN.items():
        assert help_id in CONTRACTS, f"{help_id} has a plain sentence but no contract"
        assert text.strip()
        assert not re.search(r"\b(better|worse|good|bad|healthy|safe|toxic)\b", text, re.I), text
    assert plain_for("") == "" and plain_for("nothing.here") == ""


def _two_with_values(panel):
    widget, bus = panel
    project = _project()
    widget.set_project(project)
    a, b = project.molecules[0].uuid, project.molecules[1].uuid
    for uuid, mass, logp in ((a, 18.015, -0.82), (b, 46.07, -0.0014)):
        bus.publish(_descriptor(uuid, "Molecular Weight", mass, "mol_wt"))
        bus.publish(_descriptor(uuid, "LogP", logp, "mol_logp"))
    widget.compare_with([a, b])
    return widget


def test_plain_english_marks_the_highest_explains_the_row_and_summarises(panel):
    widget = _two_with_values(panel)
    row = _row(widget, "Molecular Weight")

    assert widget._table.item(row, 2).text().endswith("\u25b2")
    assert not widget._table.item(row, 1).text().endswith("\u25b2")
    assert "not better or worse" in widget._table.item(row, 2).toolTip()
    assert "about 2.6 times" in widget._table.item(row, 2).toolTip()

    widget._table.setCurrentCell(row, 1)
    assert "How heavy one molecule is" in widget._meaning.text()
    assert "Highest here: Ethanol" in widget._meaning.text()
    assert "Ethanol is heavier" in widget._summary.text()
    assert not widget._summary.isHidden()


def test_a_copy_never_carries_the_mark(panel):
    from PySide6.QtGui import QGuiApplication

    widget = _two_with_values(panel)
    row = _row(widget, "Molecular Weight")
    widget._table.clearSelection()
    widget._table.selectRow(row)
    QGuiApplication.clipboard().clear()
    widget.copy_selection()
    assert QGuiApplication.clipboard().text() == "Molecular Weight\t18.02\t46.07"
    assert "\u25b2" not in widget.as_text()


def test_plain_english_off_is_the_plain_table(panel):
    widget = _two_with_values(panel)
    row = _row(widget, "Molecular Weight")
    widget.set_plain_english(False)

    assert widget._table.item(row, 2).text() == "46.07"
    assert widget._table.item(row, 2).toolTip() == "46.07"
    widget._table.setCurrentCell(row, 1)
    assert widget._meaning.isHidden() and widget._summary.isHidden()
    assert widget._meaning.text() == "" and widget._summary.text() == ""

    widget.set_plain_english(True)
    assert widget._table.item(row, 2).text().endswith("\u25b2")


def test_the_setting_updates_an_open_compare_panel(qapp):
    from openchem.app.settings import PLAIN_ENGLISH, Settings

    bus = EventBus()
    settings = Settings(bus)
    settings.set_preference(PLAIN_ENGLISH, True)
    widget = ComparisonPanel(bus)
    try:
        widget.attach_settings(settings)
        assert widget._plain_english is True
        settings.set_preference(PLAIN_ENGLISH, False)
        assert widget._plain_english is False
        settings.set_preference(PLAIN_ENGLISH, True)
        assert widget._plain_english is True
    finally:
        settings.set_preference(PLAIN_ENGLISH, True)
        conftest.dispose(widget)
