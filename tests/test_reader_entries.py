"""The entries a reader pinned to another molecule shows are the ones selecting it would show.

This is the gate for Compare's side-by-side readers: the feed must give the same answer as the
selected molecule's own panel, and must do it without selecting the molecule or publishing a
single event (the store's `replay` publishes every stored result on the global bus).
"""

from __future__ import annotations

import time

import pytest

from openchem.domain.calculator import CalculationRequest
from openchem.domain.molecule import MoleculeModel
from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID
from openchem.domain.merged_results import merge_reports
from openchem.events.events import MoleculeSelected

import conftest


@pytest.fixture(scope="module")
def main_window(qapp, tmp_path_factory):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    directory = tmp_path_factory.mktemp("reader_entries")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(directory / "none"))
    settings.set("plugins/user_directory", str(directory / "none2"))
    window = MainWindow(services, settings, SessionManager())
    yield window
    # Revealing Results from Compare pops it out into a top-level window; leaving this window alive
    # would leave that window behind for whichever test next counts the process's windows.
    conftest.dispose(window)


def _wait_for(qapp, condition, seconds=60):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.02)
    return False


def _molecule(window, name, smiles):
    return window._services.chemistry_engine.set_structure_from_smiles(
        MoleculeModel(display_name=name), smiles
    )


def _what_a_reader_shows(entries, version):
    """Every fact a reader would draw, by (report, label), and each report's status."""
    merged = merge_reports(entries, structure_version=version)
    facts = {(f.origin, f.label): (f.display_value, f.units) for f in merged.facts}
    return facts, {r.report_id: r.structure_version for r in merged.reports}


def test_a_pinned_feed_matches_the_selected_panel_and_publishes_nothing(main_window, qapp):
    window = main_window
    project = window._session.project
    ethanol = _molecule(window, "Ethanol", "CCO")
    water = _molecule(window, "Water", "O")
    project.molecules.extend([ethanol, water])
    bus = window._services.event_bus
    panel = window._property_panel

    bus.publish(MoleculeSelected(molecule_uuid=ethanol.uuid))
    assert _wait_for(qapp, lambda: len(panel._descriptor_values) >= 30), "descriptors never arrived"
    window._services.descriptor_service.run_calculator(
        ethanol, CalculationRequest(calculator_id="topology_analysis", molecule_uuid=ethanol.uuid, parameters={})
    )
    assert _wait_for(qapp, lambda: "topology_analysis" in panel._reports), "no report arrived"
    # Let anything still arriving land before the snapshot is taken.
    _wait_for(qapp, lambda: False, seconds=1.5)

    selected_entries, selected_version = panel._reader_entries()
    selected = _what_a_reader_shows(selected_entries, selected_version)

    # Move away: the panel now describes Water, and Ethanol is just a molecule in the project.
    bus.publish(MoleculeSelected(molecule_uuid=water.uuid))
    assert _wait_for(qapp, lambda: panel.selected_molecule_uuid() == water.uuid)
    selection_before = window._session.selected_molecule_uuid

    published: list[object] = []
    original = bus.publish
    bus.publish = lambda event: (published.append(event), original(event))[1]  # noqa: E731
    try:
        entries, version = window.reader_entries_for(ethanol.uuid)
    finally:
        bus.publish = original

    assert published == [], f"building a pinned feed published {len(published)} event(s)"
    assert window._session.selected_molecule_uuid == selection_before == water.uuid
    pinned = _what_a_reader_shows(entries, version)

    assert DESCRIPTOR_AGGREGATE_ID in {getattr(e, "report_id", "") for e in entries}
    assert "topology_analysis" in {getattr(e, "report_id", "") for e in entries}
    missing = sorted(set(selected[0]) - set(pinned[0]))
    extra = sorted(set(pinned[0]) - set(selected[0]))
    assert not missing and not extra, (missing[:8], extra[:8])
    differing = {k: (selected[0][k], pinned[0][k]) for k in selected[0] if selected[0][k] != pinned[0][k]}
    assert not differing, dict(list(differing.items())[:8])
    assert set(selected[1]) == set(pinned[1])
    assert set(pinned[1].values()) == {version}, "every entry describes the structure as it is now"


def test_a_molecule_with_nothing_stored_has_nothing_to_show(main_window):
    window = main_window
    blank = _molecule(window, "Methane", "C")
    window._session.project.molecules.append(blank)
    assert window.reader_entries_for(blank.uuid)[0] == []
    assert window.reader_entries_for("no-such-molecule") == ([], 0)
