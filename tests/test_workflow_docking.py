"""The Docking section of Properties, and the collapsible settings inside the sections.

The docking section is the rail panel's own class built a second time
(`embedded=True`). What is guarded:

* the two copies start from the same inputs, because they are one class;
* only the embedded copy has collapsible groups, and each closed group SAYS what
  it holds, so closing one to make room never hides a setting;
* a finished dock shows in both copies, through the project;
* the application draws ONE box on the structure, for the copy that is active.
"""

from __future__ import annotations

import pytest

import conftest
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.common import Provenance
from openchem.domain.docking import DockingBox, DockingPoseModel, DockingResultModel
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.ui.panels import alignment_panel as alignment_module
from openchem.ui.panels import docking_panel as docking_module
from openchem.ui.panels.alignment_panel import AlignmentPanel
from openchem.ui.panels.docking_panel import DockingPanel


@pytest.fixture
def services(qapp):
    return build_service_container()


@pytest.fixture
def built():
    widgets = []
    yield widgets
    for widget in widgets:
        conftest.dispose(widget)


def _project(services, *names_and_smiles) -> ProjectModel:
    project = ProjectModel(name="test")
    for name, smiles in names_and_smiles:
        molecule = MoleculeModel(display_name=name)
        services.chemistry_engine.set_structure_from_smiles(molecule, smiles)
        project.molecules.append(molecule)
    return project


# --- collapsible alignment settings ---------------------------------------------------


def _align_pair(services, built):
    rail = AlignmentPanel(services.alignment_service, services.event_bus)
    section = AlignmentPanel(services.alignment_service, services.event_bus, embedded=True)
    built.extend([rail, section])
    return rail, section


def test_closing_the_alignment_settings_says_what_align_would_do(services, built):
    _rail, section = _align_pair(services, built)
    section.set_project(_project(services, ("A", "CCO"), ("B", "CCN"), ("C", "CCC")))
    settings = section.settings_section
    assert settings is not None and settings.is_expanded()
    assert settings._summary_label.isHidden(), "open: the settings themselves are the answer"

    section._probe_list.item(0).setCheckState(alignment_module.Qt.CheckState.Checked)
    settings.set_expanded(False)

    assert not settings._summary_label.isHidden()
    assert settings.summary().startswith("1 molecule onto A")
    assert "Normal" in settings.summary() and "Flexible" in settings.summary()


def test_the_align_button_stays_reachable_when_the_settings_are_closed(services, built):
    """Closing them to make room must not take the way to run with it."""
    _rail, section = _align_pair(services, built)

    section.settings_section.set_expanded(False)

    assert not section._align_button.isHidden()
    assert not section._status_label.isHidden()


def test_the_rail_alignment_copy_has_no_collapsible_settings(services, built):
    rail, _section = _align_pair(services, built)

    assert rail.settings_section is None


# --- no empty boxes in a section --------------------------------------------------------


def test_the_alignment_section_shows_no_empty_table_or_picture(services, built):
    from openchem.domain.alignment import EnsembleEntry
    from openchem.events.events import EnsembleAlignmentReady

    rail, section = _align_pair(services, built)

    assert section._result_table.isHidden() and section._viewer_host.isHidden()
    assert not rail._result_table.isHidden() and not rail._viewer_host.isHidden(), "the baseline keeps them"

    services.event_bus.publish(
        EnsembleAlignmentReady(
            reference_uuid="r",
            entries=[EnsembleEntry(label="Ref (reference)", molblock="x")],
            method="atom_types",
            accuracy="Normal",
        )
    )

    assert not section._result_table.isHidden() and not section._viewer_host.isHidden()


def test_the_docking_section_shows_no_pose_table_until_there_are_poses(services, built):
    rail, section = _dock_pair(services, built)

    assert section._table.isHidden()
    assert not rail._table.isHidden(), "the baseline keeps its table"

    project = _project(services, ("Ethanol", "CCO"))
    receptor = MacromoleculeModel(
        display_name="Receptor", structure_text="HEADER\nATOM\nEND\n", source_format="pdb"
    )
    project.macromolecules.append(receptor)
    section.set_project(project)
    project.docking_results.append(
        DockingResultModel(
            ligand_molecule_uuid=project.molecules[0].uuid,
            receptor_macromolecule_uuid=receptor.uuid,
            box=DockingBox(center=(0.0, 0.0, 0.0), size=(10.0, 10.0, 10.0)),
            poses=[
                DockingPoseModel(
                    pose_molblock="pose", binding_affinity_kcal_mol=-7.0, rmsd_lb=0.0, rmsd_ub=0.0
                )
            ],
            provenance=Provenance(created_by="core", method="vina", parameters={}),
            engine="vina",
            engine_version="1.2.7",
            scoring_function="vina",
            exhaustiveness=25,
            seed=1,
        )
    )

    section.sync_with_project(project)
    assert not section._table.isHidden()

    project.docking_results.clear()
    section.sync_with_project(project)
    assert section._table.isHidden(), "an undone dock takes the table away again"


# --- the docking section: two copies of one class ------------------------------------------


def _dock_pair(services, built):
    settings = Settings(services.event_bus)
    rail = DockingPanel(
        services.docking_service, services.chemistry_engine, settings, services.event_bus
    )
    section = DockingPanel(
        services.docking_service,
        services.chemistry_engine,
        settings,
        services.event_bus,
        embedded=True,
    )
    built.extend([rail, section])
    return rail, section


def test_the_two_docking_copies_start_with_the_same_inputs(services, built):
    rail, section = _dock_pair(services, built)

    assert rail.displayed_box() == section.displayed_box()
    assert rail.displayed_search_options() == section.displayed_search_options()
    assert rail.displayed_replicates() == section.displayed_replicates()
    assert rail._num_poses_spin.value() == section._num_poses_spin.value()
    assert rail._ph_spin.value() == section._ph_spin.value()
    assert rail._strip_waters_check.isChecked() == section._strip_waters_check.isChecked()
    assert rail._strip_cofactors_check.isChecked() == section._strip_cofactors_check.isChecked()


def test_only_the_embedded_docking_copy_has_collapsible_groups(services, built):
    rail, section = _dock_pair(services, built)

    assert rail.box_section is None and rail.prep_section is None and rail.search_section is None
    # The search box is the thing to place, so it starts open; the others keep sound defaults and
    # say what they hold while closed.
    assert section.box_section.is_expanded()
    assert not section.prep_section.is_expanded()
    assert not section.search_section.is_expanded()


def test_the_closed_docking_groups_state_their_settings(services, built):
    _rail, section = _dock_pair(services, built)

    assert section.prep_section.summary() == "pH 7.4 · waters removed · cofactors kept"
    assert section.search_section.summary().startswith(
        "exhaustiveness 25 · vina · rescore off · 1 replicate · seed random"
    )
    assert not section.prep_section._summary_label.isHidden()


def test_a_docking_summary_follows_each_of_its_controls(services, built):
    """One control at a time: changing several before reading would let a later signal
    refresh a summary that an earlier control's own connection never did."""
    _rail, section = _dock_pair(services, built)

    section._ph_spin.setValue(6.5)
    assert section.prep_section.summary() == "pH 6.5 · waters removed · cofactors kept"

    section._strip_waters_check.setChecked(False)
    assert section.prep_section.summary() == "pH 6.5 · waters kept · cofactors kept"

    section._strip_cofactors_check.setChecked(True)
    assert section.prep_section.summary() == "pH 6.5 · waters kept · cofactors removed"

    section._replicates_spin.setValue(4)
    assert "4 replicates" in section.search_section.summary()

    section._search_controls.seed.setValue(77)
    assert section.search_section.summary().endswith("seed 77")

    index = section._search_controls.rescore_with.findData("vinardo")
    section._search_controls.rescore_with.setCurrentIndex(index)
    assert "rescore vinardo" in section.search_section.summary()

    section._center_x.setValue(12.5)
    assert section.box_section.summary().startswith("centre (12.5, 0.0, 0.0)")
    assert section.box_section.summary().endswith("set by hand")


def test_opening_a_docking_group_hides_its_summary(services, built):
    _rail, section = _dock_pair(services, built)

    section.search_section.set_expanded(True)

    assert section.search_section._summary_label.isHidden()


def test_a_finished_dock_shows_in_both_copies_through_the_project(services, built):
    """The result is project data, so a copy that did not start the run still shows it."""
    rail, section = _dock_pair(services, built)
    project = _project(services, ("Ethanol", "CCO"))
    receptor = MacromoleculeModel(
        display_name="Receptor", structure_text="HEADER\nATOM\nEND\n", source_format="pdb"
    )
    project.macromolecules.append(receptor)
    rail.set_project(project)
    section.set_project(project)
    project.docking_results.append(
        DockingResultModel(
            ligand_molecule_uuid=project.molecules[0].uuid,
            receptor_macromolecule_uuid=receptor.uuid,
            box=DockingBox(center=(0.0, 0.0, 0.0), size=(10.0, 10.0, 10.0)),
            poses=[
                DockingPoseModel(
                    pose_molblock="pose",
                    binding_affinity_kcal_mol=-7.25,
                    rmsd_lb=0.0,
                    rmsd_ub=0.0,
                )
            ],
            provenance=Provenance(created_by="core", method="vina", parameters={}),
            engine="vina",
            engine_version="1.2.7",
            scoring_function="vina",
            exhaustiveness=25,
            seed=1,
        )
    )

    rail.sync_with_project(project)
    section.sync_with_project(project)

    def cells(panel):
        table = panel._table
        return [
            [table.item(r, c).text() for c in range(table.columnCount()) if table.item(r, c)]
            for r in range(table.rowCount())
        ]

    assert cells(rail) == cells(section)
    assert cells(section) and cells(section)[0][1] == "-7.25"


def test_the_embedded_pose_table_is_capped(services, built):
    rail, section = _dock_pair(services, built)

    assert section._table.maximumHeight() == docking_module._EMBEDDED_TABLE_MAX_HEIGHT
    assert section._table.minimumHeight() == docking_module._EMBEDDED_TABLE_MIN_HEIGHT
    assert rail._table.maximumHeight() > docking_module._EMBEDDED_TABLE_MAX_HEIGHT


# --- the application: one box on the structure, for the copy that is active ----------------


@pytest.fixture(scope="module")
def main_window(qapp, tmp_path_factory):
    """One real window for the file; see the same fixture in test_command_palette_vocabulary."""
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager

    directory = tmp_path_factory.mktemp("workflow_docking")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(directory / "none"))
    settings.set("plugins/user_directory", str(directory / "none2"))
    return MainWindow(services, settings, SessionManager())


def _receptor_in(main_window):
    project = main_window._session.project
    if not project.macromolecules:
        project.macromolecules.append(
            MacromoleculeModel(
                display_name="Receptor", structure_text="HEADER\nATOM\nEND\n", source_format="pdb"
            )
        )
    main_window._refresh_molecule_combos()


def test_the_application_registers_the_docking_section(main_window):
    section = main_window._property_panel.workflow_section("docking")

    assert section is not None
    assert section.title() == "Dock a molecule into a receptor"
    assert not section.is_expanded()
    assert main_window._docking_section_panel is not main_window._docking_panel
    assert main_window._dock_by_panel_id("Docking") is not None, "the rail panel is the baseline"


def test_the_box_belongs_to_the_open_section_while_properties_shows(main_window):
    _receptor_in(main_window)
    section = main_window._property_panel.workflow_section("docking")

    main_window._on_panel_chosen("Properties")
    section.set_expanded(True)
    try:
        assert main_window._active_docking_panel() is main_window._docking_section_panel
        section.set_expanded(False)
        assert main_window._active_docking_panel() is None, "closed section, Docking hidden: no box"
    finally:
        section.set_expanded(False)


def test_the_box_belongs_to_the_rail_panel_while_docking_shows(main_window):
    _receptor_in(main_window)
    main_window._property_panel.workflow_section("docking").set_expanded(False)

    main_window._on_panel_chosen("Docking")

    assert main_window._active_docking_panel() is main_window._docking_panel


def test_an_open_section_hidden_by_find_draws_no_box(main_window):
    _receptor_in(main_window)
    section = main_window._property_panel.workflow_section("docking")
    main_window._on_panel_chosen("Properties")
    section.set_expanded(True)
    main_window._property_panel._find_box.setText("zzz-nothing-matches")
    try:
        assert main_window._active_docking_panel() is None
    finally:
        main_window._property_panel._find_box.setText("")
        section.set_expanded(False)


def test_both_docking_copies_receive_the_project(main_window):
    main_window._docking_panel._project = None
    main_window._docking_section_panel._project = None

    main_window._refresh_molecule_combos()

    project = main_window._session.project
    assert main_window._docking_panel._project is project
    assert main_window._docking_section_panel._project is project


def test_an_undo_or_redo_refreshes_the_pose_table_of_both_copies(main_window):
    """`_on_undo_index_changed` rebuilds the pose table from the project; a copy it
    forgot would keep showing a dock the project no longer contains."""
    project = main_window._session.project
    molecule = MoleculeModel(display_name="Ethanol")
    main_window._services.chemistry_engine.set_structure_from_smiles(molecule, "CCO")
    project.molecules.append(molecule)
    _receptor_in(main_window)
    receptor = project.macromolecules[0]
    project.docking_results.append(
        DockingResultModel(
            ligand_molecule_uuid=molecule.uuid,
            receptor_macromolecule_uuid=receptor.uuid,
            box=DockingBox(center=(0.0, 0.0, 0.0), size=(10.0, 10.0, 10.0)),
            poses=[
                DockingPoseModel(
                    pose_molblock="pose", binding_affinity_kcal_mol=-6.5, rmsd_lb=0.0, rmsd_ub=0.0
                )
            ],
            provenance=Provenance(created_by="core", method="vina", parameters={}),
            engine="vina",
            engine_version="1.2.7",
            scoring_function="vina",
            exhaustiveness=25,
            seed=1,
        )
    )
    for panel in (main_window._docking_panel, main_window._docking_section_panel):
        panel.set_project(project)
        panel._ligand_combo.setCurrentIndex(panel._ligand_combo.findData(molecule.uuid))

    main_window._on_undo_index_changed(0)

    assert main_window._docking_panel._table.rowCount() == 1
    assert main_window._docking_section_panel._table.rowCount() == 1
