from __future__ import annotations

from unittest.mock import patch

import pytest

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container


_WINDOWS: list = []


def _track(window):
    _WINDOWS.append(window)
    return window


@pytest.fixture(autouse=True)
def _close_windows():
    yield
    while _WINDOWS:
        _WINDOWS.pop().close()


def _make_window(tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    session = SessionManager()
    window = _track(MainWindow(services, settings, session))
    return window, session, settings


def test_new_project_auto_creates_and_selects_a_blank_molecule(qapp, tmp_path):
    """Regression test for the 'nothing works until File > New Molecule'
    bug: a brand-new project used to start with zero molecules and nothing
    selected, so the 2D editor's target stayed None and every edit was
    silently discarded (see test_molecule_editor_widget.py) until the user
    manually created a molecule."""
    window, session, _ = _make_window(tmp_path)

    assert session.project is not None
    assert len(session.project.molecules) == 1
    auto_created = session.project.molecules[0]
    assert session.selected_molecule_uuid == auto_created.uuid
    assert window._editor._molecule is auto_created


def test_auto_created_molecule_appears_in_docking_and_quantum_chemistry_combos(qapp, tmp_path):
    """Regression test: DockingPanel's ligand combo and QuantumChemistryPanel's
    molecule combo are only populated when set_project runs (project open/
    new) -- confirmed live that a molecule added afterward (including the
    empty-project auto-create above) never appeared in either dropdown,
    making them look permanently unusable ('clicking the dropdown arrow
    does nothing'). add_molecule/_import_molecule/add_macromolecule must
    also refresh both panels' combos."""
    window, session, _ = _make_window(tmp_path)
    auto_created = session.project.molecules[0]

    ligand_items = [
        window._docking_panel._ligand_combo.itemText(i)
        for i in range(window._docking_panel._ligand_combo.count())
    ]
    molecule_items = [
        window._quantum_chemistry_panel._molecule_combo.itemText(i)
        for i in range(window._quantum_chemistry_panel._molecule_combo.count())
    ]
    assert auto_created.display_name in ligand_items
    assert auto_created.display_name in molecule_items


def test_a_second_added_molecule_also_appears_in_both_combos(qapp, tmp_path):
    window, session, _ = _make_window(tmp_path)

    window._new_molecule()
    second = session.project.molecules[-1]

    ligand_combo_data = [
        window._docking_panel._ligand_combo.itemData(i)
        for i in range(window._docking_panel._ligand_combo.count())
    ]
    molecule_combo_data = [
        window._quantum_chemistry_panel._molecule_combo.itemData(i)
        for i in range(window._quantum_chemistry_panel._molecule_combo.count())
    ]
    # Both combos store the uuid as item data (see _refresh_combos/
    # _refresh_molecule_combo) -- check by uuid, not display name, since two
    # molecules can share the default "New molecule" name.
    assert second.uuid in ligand_combo_data
    assert second.uuid in molecule_combo_data
    assert len(ligand_combo_data) == 2
    assert len(molecule_combo_data) == 2


def test_added_macromolecule_appears_in_docking_receptor_combo(qapp, tmp_path):
    from openchem.domain.macromolecule import MacromoleculeModel

    window, _, _ = _make_window(tmp_path)
    macromolecule = MacromoleculeModel(
        display_name="Test receptor", structure_text="HEADER\nATOM\nEND\n", source_format="pdb"
    )

    window.add_macromolecule(macromolecule)

    receptor_items = [
        window._docking_panel._receptor_combo.itemText(i)
        for i in range(window._docking_panel._receptor_combo.count())
    ]
    assert "Test receptor" in receptor_items


def test_new_molecule_action_still_works_after_auto_create(qapp, tmp_path):
    """The auto-create-on-empty-project fix must not swallow File > New
    Molecule -- a project that already has the auto-created molecule
    should still gain a second one when the user asks for it explicitly."""
    window, session, _ = _make_window(tmp_path)
    assert len(session.project.molecules) == 1

    window._new_molecule()

    assert len(session.project.molecules) == 2


def test_opening_a_project_that_loads_with_no_molecules_also_auto_creates_one(qapp, tmp_path):
    """_set_project (shared by both _new_project and _open_project) is
    where the auto-create fix lives -- a loaded project that happens to be
    empty must get the same treatment as a brand-new one."""
    from openchem.domain.project import ProjectModel

    window, session, _ = _make_window(tmp_path)
    empty_project = ProjectModel(name="Loaded but empty")
    assert empty_project.molecules == []

    window._set_project(empty_project)

    assert len(session.project.molecules) == 1


def test_close_event_saves_window_geometry_and_state(qapp, tmp_path):
    """Doesn't assert a blank starting value: QSettings' backing ini file is
    keyed off tmp_path.name, whose directory numbering pytest can reuse
    across separate invocations of this same test, so a previous run's
    value can genuinely still be on disk (same caveat documented in
    test_docking_service.py's test_default_provider_reads_executable_path_
    from_settings). Instead, compare against exactly what saveGeometry()/
    saveState() produce for this window, which close() must persist.
    """
    window, _, settings = _make_window(tmp_path)
    expected_geometry = bytes(window.saveGeometry())
    expected_state = bytes(window.saveState())

    window.close()

    assert bytes(settings.window_geometry()) == expected_geometry
    assert bytes(settings.window_state()) == expected_state


def test_existing_window_geometry_and_state_are_restored_on_init(qapp, tmp_path):
    """Settings.window_geometry/window_state existed since an earlier phase
    but were never actually wired up -- MainWindow must call
    restoreGeometry/restoreState with whatever's already saved."""
    first_window, _, settings = _make_window(tmp_path)
    first_window.close()  # populates settings.window_geometry()/window_state()

    services2 = build_service_container()
    session2 = SessionManager()
    with (
        patch.object(MainWindow, "restoreGeometry") as mock_restore_geometry,
        patch.object(MainWindow, "restoreState") as mock_restore_state,
    ):
        _track(MainWindow(services2, settings, session2))

    mock_restore_geometry.assert_called_once()
    mock_restore_state.assert_called_once()


def test_right_side_docks_are_tabified_not_stacked(qapp, tmp_path):
    """Regression test for the 'garbled text' layout bug: Properties,
    Docking, and Quantum Chemistry used to all get addDockWidget'd to the
    same RightDockWidgetArea with no tabbing, so six-plus docks (once
    plugin panels join in) shared one vertical column."""
    window, _, _ = _make_window(tmp_path)

    tabified = window.tabifiedDockWidgets(window._properties_dock)
    titles = {dock.windowTitle() for dock in tabified}

    assert "Docking" in titles
    assert "Quantum Chemistry" in titles
