"""A workflow section closes its settings when a run it started finishes.

The settings have done their job by then; the table and the picture are what the
person is looking for, and the closed groups still say what was run. What is
guarded is the part that is easy to get wrong: ONLY the copy the person pressed
the button in rearranges itself (both copies hear every result), and a failed run
leaves the settings open.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

import conftest
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.alignment import EnsembleEntry
from openchem.domain.common import CacheState, Provenance
from openchem.domain.docking import DockingBox, DockingPoseModel, DockingResultModel
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.events import (
    AlignmentJobStateChanged,
    DockingResultReady,
    EnsembleAlignmentReady,
)
from openchem.services.alignment_service import AlignmentService
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


class _Recording(AlignmentService):
    """Takes the request and does nothing, so the test publishes the outcome itself."""

    def request_alignment(self, reference, probes, **kwargs):
        pass


def _project(services, *names_and_smiles) -> ProjectModel:
    project = ProjectModel(name="test")
    for name, smiles in names_and_smiles:
        molecule = MoleculeModel(display_name=name)
        services.chemistry_engine.set_structure_from_smiles(molecule, smiles)
        project.molecules.append(molecule)
    return project


def _align_pair(services, built):
    service = _Recording(services.event_bus, services.chemistry_engine)
    project = _project(services, ("A", "CCO"), ("B", "CCN"))
    rail = AlignmentPanel(service, services.event_bus)
    section = AlignmentPanel(service, services.event_bus, embedded=True)
    built.extend([rail, section])
    for panel in (rail, section):
        panel.set_project(project)
        panel._probe_list.item(0).setCheckState(Qt.CheckState.Checked)
    return rail, section


def _ready(services):
    services.event_bus.publish(
        EnsembleAlignmentReady(
            reference_uuid="r",
            entries=[EnsembleEntry(label="Ref (reference)", molblock="x")],
            method="atom_types",
            accuracy="Normal",
        )
    )


def test_the_copy_that_started_the_alignment_closes_its_settings(services, built):
    _rail, section = _align_pair(services, built)
    assert section.settings_section.is_expanded()

    section._on_align_clicked()
    _ready(services)

    assert not section.settings_section.is_expanded()
    assert section.settings_section.summary().startswith("1 molecule onto A")


def test_the_copy_that_did_not_start_it_is_left_as_it_was(services, built):
    rail, section = _align_pair(services, built)

    rail._on_align_clicked()
    _ready(services)

    assert section.settings_section.is_expanded(), "the section did not press Align"


def test_a_failed_alignment_leaves_the_settings_open(services, built):
    _rail, section = _align_pair(services, built)

    section._on_align_clicked()
    services.event_bus.publish(
        AlignmentJobStateChanged(reference_uuid="r", state=CacheState.FAILED, message="no")
    )
    _ready(services)

    assert section.settings_section.is_expanded()


def test_a_later_result_from_elsewhere_does_not_close_them_again(services, built):
    """One press closes once: the flag is spent when the result arrives."""
    _rail, section = _align_pair(services, built)
    section._on_align_clicked()
    _ready(services)
    section.settings_section.set_expanded(True)

    _ready(services)

    assert section.settings_section.is_expanded()


# --- docking ------------------------------------------------------------------------------


def _dock_result(project, receptor):
    return DockingResultModel(
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


def _dock_pair(services, built):
    settings = Settings(services.event_bus)
    args = (services.docking_service, services.chemistry_engine, settings, services.event_bus)
    rail = DockingPanel(*args)
    section = DockingPanel(*args, embedded=True)
    built.extend([rail, section])
    project = _project(services, ("Ethanol", "CCO"))
    receptor = MacromoleculeModel(
        display_name="Receptor", structure_text="HEADER\nATOM\nEND\n", source_format="pdb"
    )
    project.macromolecules.append(receptor)
    rail.set_project(project)
    section.set_project(project)
    return rail, section, project, receptor


def test_the_docking_copy_that_started_the_run_closes_its_groups(services, built):
    _rail, section, project, receptor = _dock_pair(services, built)
    section.search_section.set_expanded(True)
    assert section.box_section.is_expanded() and section.search_section.is_expanded()
    section._pending_ligand_uuid = project.molecules[0].uuid
    section._pending_receptor_uuid = receptor.uuid

    services.event_bus.publish(DockingResultReady(result=_dock_result(project, receptor)))

    assert not section.box_section.is_expanded()
    assert not section.prep_section.is_expanded()
    assert not section.search_section.is_expanded()


def test_the_docking_copy_that_did_not_start_it_keeps_its_groups(services, built):
    _rail, section, project, receptor = _dock_pair(services, built)
    # Nothing pending in the section: a dock from the rail panel, say.

    services.event_bus.publish(DockingResultReady(result=_dock_result(project, receptor)))

    assert section.box_section.is_expanded()
