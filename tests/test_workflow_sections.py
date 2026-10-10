"""Workflow sections: a whole workflow hosted inside Properties.

The first one is "Align several molecules", which is the 3D Alignment panel's own
class built a second time with `embedded=True`. What is guarded:

* the mechanism (a collapsed section above the calculators, found by Find);
* PARITY, which holds by construction and is checked anyway: one alignment fills
  the rail panel's table and the section's table with the same cells;
* the two things that differ on purpose (pop-out id, picture floor);
* the application actually registers it, and sends it the project.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QWidget

import conftest
from openchem.bootstrap import build_service_container
from openchem.domain.alignment import EnsembleEntry
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.events import EnsembleAlignmentReady
from openchem.ui.panels import alignment_panel as alignment_module
from openchem.ui.panels.alignment_panel import AlignmentPanel
from openchem.ui.panels.property_panel import PropertyPanel


@pytest.fixture
def services(qapp):
    return build_service_container()


@pytest.fixture
def built():
    widgets = []
    yield widgets
    for widget in widgets:
        conftest.dispose(widget)


def _properties(services, built) -> PropertyPanel:
    panel = PropertyPanel(
        services.event_bus,
        services.calculator_registry,
        services.descriptor_service,
        services.chemistry_engine,
        structure_version_of=services.structure_check_service.current_version,
    )
    built.append(panel)
    return panel


def _project(services, *names_and_smiles) -> ProjectModel:
    project = ProjectModel(name="test")
    for name, smiles in names_and_smiles:
        molecule = MoleculeModel(display_name=name)
        services.chemistry_engine.set_structure_from_smiles(molecule, smiles)
        project.molecules.append(molecule)
    return project


def _entries() -> list[EnsembleEntry]:
    return [
        EnsembleEntry(label="Ref (reference)", molblock="ref"),
        EnsembleEntry(
            label="Probe",
            molblock="probe",
            score=100.5,
            rmsd=0.25,
            matched_atoms=10,
            core_rmsd=0.1,
            flexible_rmsd=0.4,
            geometry_source="project_conformers",
        ),
        EnsembleEntry(label="Broken", molblock="", error="could not embed"),
    ]


def _cells(panel: AlignmentPanel) -> list[list[str]]:
    table = panel._result_table
    return [
        [
            (table.item(row, column).text() if table.item(row, column) is not None else "")
            for column in range(table.columnCount())
        ]
        for row in range(table.rowCount())
    ]


# --- the mechanism ---------------------------------------------------------------


def test_a_workflow_is_a_collapsed_section_above_the_calculators(services, built):
    panel = _properties(services, built)

    section = panel.add_workflow("demo", "Demo workflow", QLabel("hello"), keywords="demo")

    assert panel.workflow_section("demo") is section
    assert not section.is_expanded()
    layout = panel._sections_layout
    first = layout.itemAt(0).widget()
    assert first is panel._workflow_header and first.text() == "Workflows"
    assert layout.itemAt(1).widget() is section
    # The long calculator list follows, not precedes.
    assert any(layout.itemAt(i).widget() is s for i in range(2, layout.count()) for s in panel._sections.values())


def test_a_workflow_is_not_a_calculator(services, built):
    """No tick box and no place in "Run selected": a workflow has a Run of its own."""
    panel = _properties(services, built)
    before = set(panel._calculator_ticks)

    panel.add_workflow("demo", "Demo workflow", QLabel("hello"))

    assert set(panel._calculator_ticks) == before
    assert "demo" not in panel._calculator_rows


def test_find_matches_a_workflow_by_its_keywords_and_puts_it_back(services, built):
    panel = _properties(services, built)
    section = panel.add_workflow("demo", "Demo workflow", QLabel("x"), keywords="superimpose overlay")

    panel._find_box.setText("overlay")
    assert not section.isHidden() and section.is_expanded()
    assert not panel._workflow_header.isHidden()

    panel._find_box.setText("zzz-no-such-thing")
    assert section.isHidden()
    assert panel._workflow_header.isHidden()

    panel._find_box.setText("")
    assert not section.isHidden()
    assert not section.is_expanded(), "Find must put back the expansion it found"
    assert not panel._workflow_header.isHidden()


def test_find_for_a_calculator_hides_a_workflow_that_does_not_match(services, built):
    panel = _properties(services, built)
    section = panel.add_workflow("demo", "Demo workflow", QLabel("x"), keywords="overlay")

    panel._find_box.setText("logp")

    assert section.isHidden()


# --- the alignment section: parity -------------------------------------------------


def _pair(services, built):
    rail = AlignmentPanel(services.alignment_service, services.event_bus)
    section = AlignmentPanel(services.alignment_service, services.event_bus, embedded=True)
    built.extend([rail, section])
    return rail, section


def _publish(services):
    services.event_bus.publish(
        EnsembleAlignmentReady(reference_uuid="r", entries=_entries(), method="atom_types", accuracy="Normal")
    )


def test_one_alignment_fills_both_tables_with_the_same_cells(services, built):
    rail, section = _pair(services, built)

    _publish(services)

    assert _cells(rail) == _cells(section)
    # And they are the cells, not two empty tables agreeing: a score, a failed row, the reference dashes.
    cells = _cells(section)
    assert cells[1][2] == "100.50" and cells[1][3] == "0.250"
    assert cells[1][7] == "Project"
    assert cells[0][2] == "-"
    assert "could not embed" in cells[2][2]


def test_the_two_copies_share_colours_and_visibility_independently(services, built):
    rail, section = _pair(services, built)
    _publish(services)

    assert rail._colors == section._colors
    # Hiding a structure in one view is that view's business: the other keeps drawing it.
    section._result_table.item(1, 0).setCheckState(alignment_module.Qt.CheckState.Unchecked)
    assert section._visible[1] is False
    assert rail._visible[1] is True


def test_both_copies_hear_the_job_state(services, built):
    from openchem.domain.common import CacheState
    from openchem.events.events import AlignmentJobStateChanged

    rail, section = _pair(services, built)

    services.event_bus.publish(AlignmentJobStateChanged(reference_uuid="r", state=CacheState.RUNNING))

    assert not rail._align_button.isEnabled()
    assert not section._align_button.isEnabled()


def test_both_copies_follow_the_project_and_keep_their_own_ticks(services, built):
    rail, section = _pair(services, built)
    project = _project(services, ("A", "CCO"), ("B", "CCN"), ("C", "CCC"))

    rail.set_project(project)
    section.set_project(project)

    assert [rail._probe_list.item(i).text() for i in range(rail._probe_list.count())] == ["B", "C"]
    assert [section._probe_list.item(i).text() for i in range(section._probe_list.count())] == ["B", "C"]


# --- the two differences, on purpose ---------------------------------------------------


def _pop_out_id(panel: AlignmentPanel) -> str:
    return panel._viewer_host._settings_id


def test_the_two_copies_save_their_pop_out_under_different_ids(services, built):
    """One key would have each copy overwrite the other's saved window."""
    rail, section = _pair(services, built)

    assert _pop_out_id(rail) == "alignment.overlay"
    assert _pop_out_id(section) != _pop_out_id(rail)


def test_only_the_embedded_copy_reserves_height_for_the_picture(services, built):
    rail, section = _pair(services, built)

    assert section._viewer_container.minimumHeight() == alignment_module._EMBEDDED_VIEW_MIN_HEIGHT
    assert rail._viewer_container.minimumHeight() == 0


def test_the_embedded_copy_builds_no_viewer_until_it_is_shown(services, built):
    """It is a Chromium view; a collapsed section must not pay for one."""
    _rail, section = _pair(services, built)
    _publish(services)

    assert not section.viewer_is_built


# --- the application ------------------------------------------------------------------


@pytest.fixture(scope="module")
def main_window(qapp, tmp_path_factory):
    """One real window for the file; see the same fixture in test_command_palette_vocabulary."""
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings

    directory = tmp_path_factory.mktemp("workflow")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(directory / "none"))
    settings.set("plugins/user_directory", str(directory / "none2"))
    return MainWindow(services, settings, SessionManager())


def test_the_application_registers_the_alignment_section(main_window):
    section = main_window._property_panel.workflow_section("alignment")

    assert section is not None
    assert section.title() == "Align several molecules"
    assert not section.is_expanded()
    assert isinstance(main_window._alignment_section_panel, AlignmentPanel)
    assert main_window._alignment_section_panel is not main_window._alignment_panel


def test_the_rail_panel_is_still_there(main_window):
    """The baseline stays until every row of the inventory is shown equal."""
    assert main_window._dock_by_panel_id("3D_Alignment") is not None


def test_both_copies_receive_the_project_when_the_window_refreshes(main_window):
    """`_refresh_molecule_combos` runs on every project mutation; a copy it forgot
    would show a stale molecule list while the other was right."""
    main_window._alignment_panel._project = None
    main_window._alignment_section_panel._project = None

    main_window._refresh_molecule_combos()

    project = main_window._session.project
    assert main_window._alignment_panel._project is project
    assert main_window._alignment_section_panel._project is project


def test_a_widget_without_a_parent_is_not_left_behind(services, built):
    """`add_workflow` re-parents the widget into the section, so it is owned by the panel."""
    panel = _properties(services, built)
    widget = QWidget()

    section = panel.add_workflow("demo", "Demo", widget)

    assert widget.parent() is not None
    assert section.isAncestorOf(widget)
