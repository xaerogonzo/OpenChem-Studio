"""A workflow closes its settings when a run it started finishes.

The settings have done their job by then; the table and the picture are what the
person is looking for, and the closed groups still say what was run. What is
guarded is the part that is easy to get wrong: only a run THIS panel started closes
them, and a failed run leaves them open.
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


def _aligner(services, built) -> AlignmentPanel:
    service = _Recording(services.event_bus, services.chemistry_engine)
    panel = AlignmentPanel(service, services.event_bus)
    built.append(panel)
    panel.set_project(_project(services, ("A", "CCO"), ("B", "CCN")))
    panel._probe_list.item(0).setCheckState(Qt.CheckState.Checked)
    return panel


def _ready(services):
    services.event_bus.publish(
        EnsembleAlignmentReady(
            reference_uuid="r",
            entries=[EnsembleEntry(label="Ref (reference)", molblock="x")],
            method="atom_types",
            accuracy="Normal",
        )
    )


def test_the_alignment_settings_close_when_its_run_finishes(services, built):
    panel = _aligner(services, built)
    assert panel.settings_section.is_expanded()

    panel._on_align_clicked()
    _ready(services)

    assert not panel.settings_section.is_expanded()
    assert panel.settings_section.summary().startswith("1 molecule onto A")


def test_a_result_nobody_here_asked_for_leaves_the_settings_alone(services, built):
    panel = _aligner(services, built)

    _ready(services)  # published by something else: a script, a test

    assert panel.settings_section.is_expanded()


def test_a_failed_alignment_leaves_the_settings_open(services, built):
    panel = _aligner(services, built)

    panel._on_align_clicked()
    services.event_bus.publish(
        AlignmentJobStateChanged(reference_uuid="r", state=CacheState.FAILED, message="no")
    )
    _ready(services)

    assert panel.settings_section.is_expanded()


def test_one_press_closes_once(services, built):
    """The flag is spent when the result arrives, so a later result does not close them again."""
    panel = _aligner(services, built)
    panel._on_align_clicked()
    _ready(services)
    panel.settings_section.set_expanded(True)

    _ready(services)

    assert panel.settings_section.is_expanded()


# --- docking -------------------------------------------------------------------------------


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


def _docker(services, built):
    panel = DockingPanel(
        services.docking_service,
        services.chemistry_engine,
        Settings(services.event_bus),
        services.event_bus,
    )
    built.append(panel)
    project = _project(services, ("Ethanol", "CCO"))
    receptor = MacromoleculeModel(
        display_name="Receptor", structure_text="HEADER\nATOM\nEND\n", source_format="pdb"
    )
    project.macromolecules.append(receptor)
    panel.set_project(project)
    return panel, project, receptor


def test_the_docking_groups_close_when_its_run_finishes(services, built):
    panel, project, receptor = _docker(services, built)
    panel.search_section.set_expanded(True)
    assert panel.box_section.is_expanded() and panel.search_section.is_expanded()
    panel._pending_ligand_uuid = project.molecules[0].uuid
    panel._pending_receptor_uuid = receptor.uuid

    services.event_bus.publish(DockingResultReady(result=_dock_result(project, receptor)))

    assert not panel.box_section.is_expanded()
    assert not panel.prep_section.is_expanded()
    assert not panel.search_section.is_expanded()


def test_a_docking_result_nobody_here_asked_for_leaves_the_groups_alone(services, built):
    panel, project, receptor = _docker(services, built)
    # Nothing pending: a script, or another run's result.

    services.event_bus.publish(DockingResultReady(result=_dock_result(project, receptor)))

    assert panel.box_section.is_expanded()
