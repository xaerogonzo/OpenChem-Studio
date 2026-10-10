"""Moving a workflow between its own tab and Properties, in the real window.

The claim under test is that it is ONE widget: moved, never rebuilt, so everything the
person set and any result on screen comes with it. Around that claim:

* the tab says where the workflow went, and a click on the rail entry goes there;
* the home is remembered;
* the search box on the structure follows where the docking workflow lives;
* nothing is left behind in either container.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.alignment import EnsembleEntry
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.events.events import EnsembleAlignmentReady
from openchem.ui.widgets.workflow_body import HOME_PROPERTIES, HOME_TAB


@pytest.fixture(scope="module")
def main_window(qapp, tmp_path_factory):
    """One real window for the file; see the same fixture in test_command_palette_vocabulary."""
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager

    directory = tmp_path_factory.mktemp("workflow_move")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(directory / "none"))
    settings.set("plugins/user_directory", str(directory / "none2"))
    return MainWindow(services, settings, SessionManager())


@contextmanager
def _moved(window, workflow_id, home):
    """Move a workflow, and put it back in its tab whatever the test did."""
    window._move_workflow(workflow_id, home)
    try:
        yield
    finally:
        window._move_workflow(workflow_id, HOME_TAB)


def _body(window, workflow_id):
    return window._property_panel.workflow_body(workflow_id)


def _in_dock(window, workflow_id) -> bool:
    spec = window._workflow_homes[workflow_id]
    return spec.scroll.widget() is spec.panel


def _in_properties(window, workflow_id) -> bool:
    return _body(window, workflow_id).widget() is window._workflow_homes[workflow_id].panel


def _receptor_in(window):
    project = window._session.project
    if not project.macromolecules:
        project.macromolecules.append(
            MacromoleculeModel(
                display_name="Receptor", structure_text="HEADER\nATOM\nEND\n", source_format="pdb"
            )
        )
    window._refresh_molecule_combos()


# --- where they start ----------------------------------------------------------------------


@pytest.mark.parametrize("workflow_id", ["docking", "alignment"])
def test_a_workflow_starts_in_its_own_tab(main_window, workflow_id):
    assert main_window._property_panel.workflow_home(workflow_id) == HOME_TAB
    assert _in_dock(main_window, workflow_id)
    assert not _in_properties(main_window, workflow_id)


def test_both_workflows_have_a_section_and_a_rail_dock(main_window):
    for workflow_id, dock in (("docking", "Docking"), ("alignment", "3D_Alignment")):
        assert main_window._property_panel.workflow_section(workflow_id) is not None
        assert main_window._dock_by_panel_id(dock) is not None


# --- the move ------------------------------------------------------------------------------


@pytest.mark.parametrize("workflow_id", ["docking", "alignment"])
def test_moving_to_properties_moves_the_same_widget(main_window, workflow_id):
    spec = main_window._workflow_homes[workflow_id]
    panel = spec.panel

    with _moved(main_window, workflow_id, HOME_PROPERTIES):
        assert _in_properties(main_window, workflow_id)
        assert not _in_dock(main_window, workflow_id)
        assert spec.scroll.widget() is spec.placeholder, "the tab says where it went"
        assert spec.panel is panel

    # And back: the same object again, and the tab holds it, not the note.
    assert _in_dock(main_window, workflow_id)
    assert not _in_properties(main_window, workflow_id)
    assert spec.panel is panel


def test_what_the_person_set_survives_a_round_trip(main_window):
    panel = main_window._docking_panel
    panel._ph_spin.setValue(6.3)
    panel._replicates_spin.setValue(3)
    panel._center_x.setValue(12.5)

    with _moved(main_window, "docking", HOME_PROPERTIES):
        assert panel._ph_spin.value() == 6.3
        assert panel._replicates_spin.value() == 3
        assert panel.displayed_box().center[0] == 12.5

    assert panel._ph_spin.value() == 6.3
    assert panel._replicates_spin.value() == 3
    assert panel.displayed_box().center[0] == 12.5
    panel._ph_spin.setValue(7.4)
    panel._replicates_spin.setValue(1)
    panel._center_x.setValue(0.0)


def test_an_alignment_result_survives_a_round_trip(main_window):
    panel = main_window._alignment_panel
    main_window._services.event_bus.publish(
        EnsembleAlignmentReady(
            reference_uuid="r",
            entries=[
                EnsembleEntry(label="Ref (reference)", molblock="x"),
                EnsembleEntry(label="Probe", molblock="y", score=12.5, rmsd=0.5, matched_atoms=4),
            ],
            method="atom_types",
            accuracy="Normal",
        )
    )
    rows = panel._result_table.rowCount()
    assert rows == 2

    with _moved(main_window, "alignment", HOME_PROPERTIES):
        assert panel._result_table.rowCount() == rows
        assert panel._result_table.item(1, 2).text() == "12.50"

    assert panel._result_table.rowCount() == rows
    assert panel._result_table.item(1, 2).text() == "12.50"


def test_moving_to_the_home_it_is_already_in_does_nothing(main_window):
    spec = main_window._workflow_homes["docking"]

    main_window._move_workflow("docking", HOME_TAB)

    assert _in_dock(main_window, "docking")
    assert spec.scroll.widget() is spec.panel


def test_the_buttons_do_the_moving(main_window):
    """Through the REAL buttons, so it is the wiring that is checked."""
    body = _body(main_window, "alignment")

    body._move_here.click()
    try:
        assert main_window._property_panel.workflow_home("alignment") == HOME_PROPERTIES
        assert _in_properties(main_window, "alignment")
    finally:
        body._move_to_tab.click()

    assert main_window._property_panel.workflow_home("alignment") == HOME_TAB
    assert _in_dock(main_window, "alignment")


def test_the_note_in_the_tab_can_bring_it_back(main_window):
    spec = main_window._workflow_homes["alignment"]
    main_window._move_workflow("alignment", HOME_PROPERTIES)
    try:
        spec.placeholder.move_back_requested.emit()
        assert main_window._property_panel.workflow_home("alignment") == HOME_TAB
        assert _in_dock(main_window, "alignment")
    finally:
        main_window._move_workflow("alignment", HOME_TAB)


def test_the_note_in_the_tab_can_take_you_to_the_section(main_window):
    spec = main_window._workflow_homes["alignment"]
    section = main_window._property_panel.workflow_section("alignment")
    with _moved(main_window, "alignment", HOME_PROPERTIES):
        section.set_expanded(False)

        spec.placeholder.show_requested.emit()

        assert section.is_expanded()
        assert not main_window._dock_by_panel_id("Properties").isHidden()


# --- the rail ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("workflow_id", "dock"), [("docking", "Docking"), ("alignment", "3D_Alignment")]
)
def test_a_rail_click_on_a_workflow_in_properties_goes_to_its_section(main_window, workflow_id, dock):
    section = main_window._property_panel.workflow_section(workflow_id)
    with _moved(main_window, workflow_id, HOME_PROPERTIES):
        main_window._on_panel_chosen("Properties")
        section.set_expanded(False)
        main_window._on_panel_chosen(dock)

        assert section.is_expanded()
        assert not main_window._dock_by_panel_id("Properties").isHidden()
        assert main_window._dock_by_panel_id(dock).isHidden(), "the note's dock is not what is shown"


def test_a_rail_click_on_a_workflow_in_its_tab_still_shows_the_tab(main_window):
    main_window._on_panel_chosen("Properties")

    main_window._on_panel_chosen("3D_Alignment")

    assert not main_window._dock_by_panel_id("3D_Alignment").isHidden()


def test_moving_to_the_tab_shows_the_tab(main_window):
    main_window._move_workflow("alignment", HOME_PROPERTIES)

    main_window._move_workflow("alignment", HOME_TAB)

    assert not main_window._dock_by_panel_id("3D_Alignment").isHidden()


# --- remembered ----------------------------------------------------------------------------------


def test_the_home_is_remembered_and_read_back(main_window):
    settings = main_window._settings
    with _moved(main_window, "docking", HOME_PROPERTIES):
        assert settings.get("workflows/docking/home") == HOME_PROPERTIES
        assert main_window._stored_workflow_home("docking") == HOME_PROPERTIES
    assert settings.get("workflows/docking/home") == HOME_TAB
    assert main_window._stored_workflow_home("docking") == HOME_TAB


def test_an_unknown_stored_home_falls_back_to_the_tab(main_window):
    main_window._settings.set("workflows/docking/home", "somewhere-else")
    try:
        assert main_window._stored_workflow_home("docking") == HOME_TAB
    finally:
        main_window._settings.set("workflows/docking/home", HOME_TAB)


# --- the search box on the structure follows the home ----------------------------------------------


def test_the_box_is_drawn_for_the_tab_while_the_tab_shows(main_window):
    _receptor_in(main_window)

    main_window._on_panel_chosen("Docking")

    assert main_window._active_docking_panel() is main_window._docking_panel


def test_no_box_while_neither_home_is_showing(main_window):
    _receptor_in(main_window)
    main_window._on_panel_chosen("Properties")

    assert main_window._active_docking_panel() is None


def test_the_box_is_drawn_for_the_open_section_when_the_workflow_lives_there(main_window):
    _receptor_in(main_window)
    section = main_window._property_panel.workflow_section("docking")
    with _moved(main_window, "docking", HOME_PROPERTIES):
        main_window._on_panel_chosen("Properties")
        section.set_expanded(True)
        assert main_window._active_docking_panel() is main_window._docking_panel

        section.set_expanded(False)
        assert main_window._active_docking_panel() is None, "a closed section draws no box"


def test_a_section_hidden_by_find_draws_no_box(main_window):
    _receptor_in(main_window)
    section = main_window._property_panel.workflow_section("docking")
    with _moved(main_window, "docking", HOME_PROPERTIES):
        main_window._on_panel_chosen("Properties")
        section.set_expanded(True)
        main_window._property_panel._find_box.setText("zzz-nothing-matches")
        try:
            assert main_window._active_docking_panel() is None
        finally:
            main_window._property_panel._find_box.setText("")


def test_the_tab_does_not_draw_a_box_while_the_workflow_lives_in_properties(main_window):
    """Its dock may well be shown (a restored layout); the note in it has no box to draw."""
    _receptor_in(main_window)
    with _moved(main_window, "docking", HOME_PROPERTIES):
        main_window._property_panel.workflow_section("docking").set_expanded(False)
        main_window._dock_by_panel_id("Docking").setVisible(True)

        assert main_window._active_docking_panel() is None
        main_window._dock_by_panel_id("Docking").setVisible(False)


# --- the project reaches the one panel ---------------------------------------------------------------------


def test_the_project_reaches_each_panel_wherever_it_lives(main_window):
    for workflow_id in ("docking", "alignment"):
        main_window._workflow_homes[workflow_id].panel._project = None
        with _moved(main_window, workflow_id, HOME_PROPERTIES):
            main_window._refresh_molecule_combos()
            assert main_window._workflow_homes[workflow_id].panel._project is main_window._session.project
