"""Compare's side-by-side readers: one pane per molecule, kept on the same value.

The panes are the application's own `ResultsView`, fed by a callable, so most of this runs against a
stub feed; the last tests drive the real window.
"""

from __future__ import annotations

import time

import pytest

from openchem.domain.common import Provenance
from openchem.domain.molecule import MoleculeModel
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis
from openchem.events.events import MoleculeSelected
from openchem.ui.widgets.compare_readers import CompareReaders

import conftest


def _report(uuid, report_id, **facts):
    return ReportResult(
        molecule_uuid=uuid, report_id=report_id, name=report_id.title(), category="geometry",
        facts=tuple(
            Fact(category=FactCategory.GEOMETRY, label=label, value=value, display_value=str(value),
                 source="x", basis=Basis.DETERMINISTIC)
            for label, value in facts.items()
        ),
        provenance=Provenance(created_by="core", method="rdkit"),
    )


class _Feed:
    """What each molecule 'has stored'; a molecule not in `held` has nothing."""

    def __init__(self):
        self.held: dict[str, list] = {}
        self.calls: list[str] = []

    def __call__(self, uuid):
        self.calls.append(uuid)
        return list(self.held.get(uuid, [])), 1


@pytest.fixture
def readers(qapp):
    feed = _Feed()
    names = {"a": "Water", "b": "Ethanol", "c": "Methane", "d": "Ammonia"}
    for uuid in names:
        feed.held[uuid] = [
            _report(uuid, "geometry_analysis", **{"Max radius": 1.5, "Min radius": 0.5}),
            _report(uuid, "topology_analysis", **{"Rings": 0}),
        ]
    widget = CompareReaders(feed=feed, names=lambda u: names.get(u, u))
    yield widget, feed
    if widget.isVisible() or widget.uuids():
        widget.close()
    conftest.dispose(widget)


def _focus(reader, report_id):
    reader._focus_box.setCurrentIndex(reader._focus_box.findData(report_id))


def test_two_molecules_start_side_by_side_and_more_start_as_tabs(readers):
    widget, _ = readers
    widget.set_molecules(["a", "b"])
    assert widget.is_side_by_side()
    widget.set_molecules(["a", "b", "c"])
    assert not widget.is_side_by_side()
    assert widget._tabs.count() == 3 and widget._tabs.tabText(0) == "Water"


def test_the_layout_can_be_switched_and_the_choice_is_kept(readers):
    widget, _ = readers
    widget.set_molecules(["a", "b"])
    widget._layout_button.click()
    assert not widget.is_side_by_side()
    widget.set_molecules(["a", "b"])
    assert not widget.is_side_by_side(), "a layout somebody chose is not taken back"
    assert widget._tabs.count() == 2


def test_every_pane_is_fed_for_its_own_molecule_only(readers):
    widget, feed = readers
    widget.set_molecules(["a", "b"])
    for uuid in ("a", "b"):
        reader = widget.pane(uuid).reader
        assert reader.molecule_uuid() == uuid
        assert {r.report_id for r in reader.merged().reports} == {"geometry_analysis", "topology_analysis"}


def test_moving_one_linked_pane_moves_the_others_without_an_echo(readers):
    widget, _ = readers
    widget.set_molecules(["a", "b", "c"])
    echoes = []
    for uuid in ("b", "c"):
        widget.pane(uuid).reader.view_changed.connect(lambda v, u=uuid: echoes.append(u))

    _focus(widget.pane("a").reader, "topology_analysis")

    assert {u: widget.pane(u).reader.focus() for u in "abc"} == {u: "topology_analysis" for u in "abc"}
    assert echoes == [], "following another pane is not a move of one's own"


def test_a_fact_filter_typed_in_one_reaches_the_others(readers):
    widget, _ = readers
    widget.set_molecules(["a", "b"])
    widget.pane("a").reader._view.set_filter_state("radius", False)
    widget.pane("a").reader._view.filter_changed.emit()
    assert widget.pane("b").reader.view().search == "radius"


def test_unlinked_panes_move_on_their_own(readers):
    widget, _ = readers
    widget.set_molecules(["a", "b"])
    widget.set_linked(False)
    _focus(widget.pane("a").reader, "topology_analysis")
    assert widget.pane("a").reader.focus() == "topology_analysis"
    assert widget.pane("b").reader.focus() == ""


def test_a_group_command_goes_to_every_pane_even_when_unlinked(readers):
    widget, _ = readers
    widget.set_molecules(["a", "b"])
    widget.set_linked(False)

    widget.show_target("geometry_analysis", "Max radius")

    for uuid in "ab":
        reader = widget.pane(uuid).reader
        assert reader.focus() == "geometry_analysis"
        assert reader._view.visible_fact_labels() == ["Max radius"]
    assert "2 of 2" in widget._status.text()


def test_a_molecule_without_the_result_says_so_instead_of_showing_everything(readers):
    widget, feed = readers
    feed.held["b"] = []
    widget.set_molecules(["a", "b"])

    widget.show_target("geometry_analysis", "Max radius")

    assert widget.pane("a")._note.isHidden()
    note = widget.pane("b")._note
    assert not note.isHidden() and "Ethanol" in note.text() and "not been calculated" in note.text()
    assert "1 of 2" in widget._status.text()


def test_a_result_with_no_such_value_is_told_apart_from_no_result(readers):
    widget, _ = readers
    widget.set_molecules(["a", "b"])
    widget.show_target("topology_analysis", "Max radius")
    assert "no value called Max radius" in widget.pane("a")._note.text()


def test_a_re_read_keeps_the_group_where_it_was_and_picks_up_new_results(readers):
    widget, feed = readers
    feed.held["b"] = []
    widget.set_molecules(["a", "b"])
    widget.show_target("geometry_analysis", "Max radius")
    assert not widget.pane("b")._note.isHidden()

    feed.held["b"] = [_report("b", "geometry_analysis", **{"Max radius": 2.0})]
    widget.refresh()

    assert widget.pane("b")._note.isHidden()
    assert widget.pane("b").reader.focus() == "geometry_analysis"
    assert "2 of 2" in widget._status.text()


def test_a_burst_of_results_is_one_re_read(readers, qapp):
    widget, feed = readers
    widget.set_molecules(["a", "b"])
    feed.calls.clear()
    for _ in range(20):
        widget.request_refresh()
    end = time.monotonic() + 3
    while time.monotonic() < end and not feed.calls:
        qapp.processEvents()
        time.sleep(0.01)
    time.sleep(0.4)
    qapp.processEvents()
    assert sorted(feed.calls) == ["a", "b"]


def test_a_molecule_that_stays_keeps_its_pane_and_one_that_leaves_is_disposed(readers):
    widget, _ = readers
    widget.set_molecules(["a", "b", "c"])
    keep, gone = widget.pane("a"), widget.pane("c")
    _focus(keep.reader, "topology_analysis")

    widget.set_molecules(["a", "b", "d"])

    assert widget.pane("a") is keep, "the pane of a molecule that stayed is not rebuilt"
    assert keep.reader.focus() == "topology_analysis"
    assert widget.pane("c") is None
    assert widget.pane("d").reader.focus() == "topology_analysis", "a newcomer joins where the group is"
    assert widget.uuids() == ["a", "b", "d"]


def test_closing_releases_every_pane_and_stops_the_timer(readers):
    widget, _ = readers
    widget.set_molecules(["a", "b"])
    widget.request_refresh()
    closed = []
    widget.closed.connect(lambda: closed.append(True))

    widget.show()
    widget.close()

    assert closed == [True]
    assert widget.uuids() == [] and widget._panes == {}
    assert not widget._refresh_timer.isActive()


# --- the real window ----------------------------------------------------------------


@pytest.fixture(scope="module")
def main_window(qapp, tmp_path_factory):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    directory = tmp_path_factory.mktemp("compare_readers")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(directory / "none"))
    settings.set("plugins/user_directory", str(directory / "none2"))
    return MainWindow(services, settings, SessionManager())


def _wait_for(qapp, condition, seconds=60):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_open_side_by_side_then_double_click_takes_every_pane_to_the_value(main_window, qapp):
    window = main_window
    engine = window._services.chemistry_engine
    water = engine.set_structure_from_smiles(MoleculeModel(display_name="Water"), "O")
    ethanol = engine.set_structure_from_smiles(MoleculeModel(display_name="Ethanol"), "CCO")
    project = window._session.project
    project.molecules.extend([water, ethanol])
    panel = window._comparison_panel
    panel.set_project(project)
    bus = window._services.event_bus
    for molecule in (water, ethanol):
        bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
        assert _wait_for(qapp, lambda m=molecule: len(panel._values.get(m.uuid, {})) > 10)
    panel.compare_with([water.uuid, ethanol.uuid])
    # Both are stored; Water is the selected one, Ethanol is just in the project.
    bus.publish(MoleculeSelected(molecule_uuid=water.uuid))

    panel._readers_button.click()

    readers = window._compare_readers
    assert readers is not None and readers.uuids() == [water.uuid, ethanol.uuid]
    assert _wait_for(
        qapp, lambda: all(readers.pane(u).reader.merged().reports for u in readers.uuids())
    ), "the panes were never fed"
    assert window._session.selected_molecule_uuid == water.uuid, "opening readers selects nothing"

    row = next(i for i, r in enumerate(panel._shown_rows) if r.label == "Molecular Weight")
    assert panel.activate(row, 2)

    for uuid in (water.uuid, ethanol.uuid):
        reader = readers.pane(uuid).reader
        assert reader.focus() == "molecular_properties"
        assert reader._view.visible_fact_labels() == ["Molecular Weight"]

    # The ticks move the group; fewer than two leave it alone.
    panel.compare_with([ethanol.uuid])
    assert readers.uuids() == [water.uuid, ethanol.uuid]
    readers.close()
    assert window._compare_readers is None
