"""Undoing a dock must take the poses off the screen, and redo must bring them back.

The pose table was filled from the `DockingResultReady` event and never
read back from the project, so it showed whatever had last finished.
Measured before the fix: after the undo that emptied
`project.docking_results`, the table still listed two poses with their
binding affinities.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.common import Provenance
from openchem.domain.docking import DockingBox, DockingPoseModel, DockingResultModel
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.events import DockingResultReady

import conftest


@pytest.fixture
def widgets():
    built = []
    yield built
    for widget in built:
        widget.close()
        conftest.dispose(widget)


@pytest.fixture
def docked(qapp, tmp_path, widgets):
    """A window with one finished docking result showing in the panel."""
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user"))
    window = MainWindow(services, settings, SessionManager())
    widgets.append(window)

    receptor = MacromoleculeModel(display_name="1HSG")
    receptor.structure_text = "ATOM      1  N   ALA A   1       0.000   0.000   0.000\nEND\n"
    receptor.source_format = "pdb"
    window.add_macromolecule(receptor)
    ligand = MoleculeModel(display_name="Indinavir")
    services.chemistry_engine.set_structure_from_smiles(ligand, "CCO")
    window.add_molecule(ligand)
    qapp.processEvents()

    molblock = Chem.MolToMolBlock(Chem.MolFromSmiles("CCO"))
    result = DockingResultModel(
        ligand_molecule_uuid=ligand.uuid,
        receptor_macromolecule_uuid=receptor.uuid,
        box=DockingBox(center=(0.0, 0.0, 0.0), size=(20.0, 20.0, 20.0)),
        poses=[
            DockingPoseModel(
                pose_molblock=molblock,
                binding_affinity_kcal_mol=-9.75,
                rmsd_lb=0.0,
                rmsd_ub=0.0,
            ),
            DockingPoseModel(
                pose_molblock=molblock,
                binding_affinity_kcal_mol=-8.10,
                rmsd_lb=1.2,
                rmsd_ub=2.4,
            ),
        ],
        provenance=Provenance(created_by="test", method="vina"),
        engine="vina-executable",
        engine_version="1.2.7",
        scoring_function="vina",
        exhaustiveness=8,
        seed=None,
    )
    panel = window._docking_panel
    panel._pending_ligand_uuid = ligand.uuid
    panel._pending_receptor_uuid = receptor.uuid
    services.event_bus.publish(DockingResultReady(result=result))
    qapp.processEvents()
    return window, panel, result


def test_the_poses_are_shown_to_begin_with(docked):
    _window, panel, _result = docked
    assert panel._table.rowCount() == 2


def test_undoing_the_dock_clears_the_pose_table(docked, qapp):
    """Binding affinities to two decimal places, for a run the project no
    longer contains, is the worst kind of stale: it reads as a result."""
    window, panel, _result = docked

    window._undo_stack.undo()
    qapp.processEvents()

    assert not window._session.project.docking_results
    assert panel._table.rowCount() == 0


def test_redoing_the_dock_brings_the_poses_back(docked, qapp):
    """Symmetry. Clearing on undo without restoring on redo would trade one
    wrong state for another."""
    window, panel, _result = docked
    window._undo_stack.undo()
    qapp.processEvents()

    window._undo_stack.redo()
    qapp.processEvents()

    assert len(window._session.project.docking_results) == 1
    assert panel._table.rowCount() == 2
    assert panel._table.item(0, 1).text() == "-9.75"


def test_the_table_resolves_from_the_project_not_from_the_last_event(docked, qapp):
    """`sync_with_project` reads the project, so a result that is present
    shows even though no event was published for it."""
    window, panel, result = docked
    panel._table.setRowCount(0)
    panel._displayed_result_uuid = None

    panel.sync_with_project(window._session.project)

    assert panel._table.rowCount() == 2
    assert panel._displayed_result_uuid == result.uuid


def test_a_result_for_a_different_pair_is_not_shown(docked, qapp):
    """The table is scoped to the selected receptor and ligand, so another
    pair's poses cannot leak into it."""
    window, panel, _result = docked
    other = MoleculeModel(display_name="Something else")
    window._services.chemistry_engine.set_structure_from_smiles(other, "CCC")
    window.add_molecule(other)
    qapp.processEvents()

    panel.sync_with_project(window._session.project)

    assert panel._table.rowCount() == 0
