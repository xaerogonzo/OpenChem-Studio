"""The Docking and Alignment panels' presentation: groups that close and say what they hold.

Both panels are built once and live either in their own tab or in a section of
Properties (see `test_workflow_move.py`), so there is one presentation. What is
guarded here is that presentation:

* each group closes, and a closed group SAYS what it holds, so closing one to make
  room never hides a setting;
* the buttons that run stay in view when the groups are closed;
* an empty table or picture is not shown until there is something in it;
* a finished dock shows through the project.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

import conftest
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.alignment import EnsembleEntry
from openchem.domain.common import Provenance
from openchem.domain.docking import DockingBox, DockingPoseModel, DockingResultModel
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.events import EnsembleAlignmentReady
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


def _receptor() -> MacromoleculeModel:
    return MacromoleculeModel(
        display_name="Receptor", structure_text="HEADER\nATOM\nEND\n", source_format="pdb"
    )


def _dock_result(project, receptor, affinity=-7.25):
    return DockingResultModel(
        ligand_molecule_uuid=project.molecules[0].uuid,
        receptor_macromolecule_uuid=receptor.uuid,
        box=DockingBox(center=(0.0, 0.0, 0.0), size=(10.0, 10.0, 10.0)),
        poses=[
            DockingPoseModel(
                pose_molblock="pose", binding_affinity_kcal_mol=affinity, rmsd_lb=0.0, rmsd_ub=0.0
            )
        ],
        provenance=Provenance(created_by="core", method="vina", parameters={}),
        engine="vina",
        engine_version="1.2.7",
        scoring_function="vina",
        exhaustiveness=25,
        seed=1,
    )


# --- alignment -----------------------------------------------------------------------------


def _aligner(services, built) -> AlignmentPanel:
    panel = AlignmentPanel(services.alignment_service, services.event_bus)
    built.append(panel)
    return panel


def test_closing_the_alignment_settings_says_what_align_would_do(services, built):
    panel = _aligner(services, built)
    panel.set_project(_project(services, ("A", "CCO"), ("B", "CCN"), ("C", "CCC")))
    settings = panel.settings_section
    assert settings is not None and settings.is_expanded()
    assert settings._summary_label.isHidden(), "open: the settings themselves are the answer"

    panel._probe_list.item(0).setCheckState(Qt.CheckState.Checked)
    settings.set_expanded(False)

    assert not settings._summary_label.isHidden()
    assert settings.summary().startswith("1 molecule onto A")
    assert "Normal" in settings.summary() and "Flexible" in settings.summary()


def test_the_align_button_stays_reachable_when_the_settings_are_closed(services, built):
    """Closing them to make room must not take the way to run with it."""
    panel = _aligner(services, built)

    panel.settings_section.set_expanded(False)

    assert not panel._align_button.isHidden()
    assert not panel._status_label.isHidden()


def test_the_alignment_panel_shows_no_empty_table_or_picture(services, built):
    panel = _aligner(services, built)

    assert panel._result_table.isHidden() and panel._viewer_host.isHidden()

    services.event_bus.publish(
        EnsembleAlignmentReady(
            reference_uuid="r",
            entries=[EnsembleEntry(label="Ref (reference)", molblock="x")],
            method="atom_types",
            accuracy="Normal",
        )
    )

    assert not panel._result_table.isHidden() and not panel._viewer_host.isHidden()


def test_the_alignment_picture_is_not_built_before_the_panel_is_shown(services, built):
    """It is a Chromium view, built on first show (`test_lazy_web_views.py` holds that contract)."""
    panel = _aligner(services, built)

    assert not panel.viewer_is_built


# --- docking ------------------------------------------------------------------------------


def _dock(services, built) -> DockingPanel:
    panel = DockingPanel(
        services.docking_service,
        services.chemistry_engine,
        Settings(services.event_bus),
        services.event_bus,
    )
    built.append(panel)
    return panel


def test_the_docking_groups_close_and_the_box_starts_open(services, built):
    panel = _dock(services, built)

    # The search box is the thing to place, so it starts open; the others keep sound defaults and
    # say what they hold while closed.
    assert panel.box_section.is_expanded()
    assert not panel.prep_section.is_expanded()
    assert not panel.search_section.is_expanded()


def test_the_closed_docking_groups_state_their_settings(services, built):
    panel = _dock(services, built)

    assert panel.prep_section.summary() == "pH 7.4 · waters removed · cofactors kept"
    assert panel.search_section.summary().startswith(
        "exhaustiveness 25 · vina · rescore off · 1 replicate · seed random"
    )
    assert not panel.prep_section._summary_label.isHidden()


def test_a_docking_summary_follows_each_of_its_controls(services, built):
    """One control at a time: changing several before reading would let a later signal
    refresh a summary that an earlier control's own connection never did."""
    panel = _dock(services, built)

    panel._ph_spin.setValue(6.5)
    assert panel.prep_section.summary() == "pH 6.5 · waters removed · cofactors kept"

    panel._strip_waters_check.setChecked(False)
    assert panel.prep_section.summary() == "pH 6.5 · waters kept · cofactors kept"

    panel._strip_cofactors_check.setChecked(True)
    assert panel.prep_section.summary() == "pH 6.5 · waters kept · cofactors removed"

    panel._replicates_spin.setValue(4)
    assert "4 replicates" in panel.search_section.summary()

    panel._search_controls.seed.setValue(77)
    assert panel.search_section.summary().endswith("seed 77")

    index = panel._search_controls.rescore_with.findData("vinardo")
    panel._search_controls.rescore_with.setCurrentIndex(index)
    assert "rescore vinardo" in panel.search_section.summary()

    panel._center_x.setValue(12.5)
    assert panel.box_section.summary().startswith("centre (12.5, 0.0, 0.0)")
    assert panel.box_section.summary().endswith("set by hand")


def test_opening_a_docking_group_hides_its_summary(services, built):
    panel = _dock(services, built)

    panel.search_section.set_expanded(True)

    assert panel.search_section._summary_label.isHidden()


def test_the_pose_table_is_capped_and_absent_until_there_are_poses(services, built):
    panel = _dock(services, built)

    assert panel._table.maximumHeight() == docking_module._TABLE_MAX_HEIGHT
    assert panel._table.minimumHeight() == docking_module._TABLE_MIN_HEIGHT
    assert panel._table.isHidden()

    project = _project(services, ("Ethanol", "CCO"))
    receptor = _receptor()
    project.macromolecules.append(receptor)
    panel.set_project(project)
    project.docking_results.append(_dock_result(project, receptor))

    panel.sync_with_project(project)
    assert not panel._table.isHidden()
    assert panel._table.item(0, 1).text() == "-7.25"

    project.docking_results.clear()
    panel.sync_with_project(project)
    assert panel._table.isHidden(), "an undone dock takes the table away again"
