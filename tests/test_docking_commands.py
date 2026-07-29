from __future__ import annotations

from PySide6.QtGui import QUndoStack

from openchem.commands.docking_commands import SetDockingResultCommand
from openchem.domain.common import Provenance
from openchem.domain.docking import DockingBox, DockingPoseModel, DockingResultModel
from openchem.domain.project import ProjectModel


def _make_result() -> DockingResultModel:
    return DockingResultModel(
        ligand_molecule_uuid="lig-1",
        receptor_macromolecule_uuid="rec-1",
        box=DockingBox(center=(0, 0, 0), size=(20, 20, 20)),
        poses=[DockingPoseModel(pose_molblock="mock", binding_affinity_kcal_mol=-5.0, rmsd_lb=0.0, rmsd_ub=0.0)],
        provenance=Provenance(created_by="core", method="vina"),
        engine="vina-python",
        engine_version="1.2.7",
        scoring_function="vina",
        exhaustiveness=8,
        seed=None,
    )


def test_set_docking_result_undo_redo(qapp):
    project = ProjectModel()
    result = _make_result()
    stack = QUndoStack()

    stack.push(SetDockingResultCommand(project, result))
    assert result in project.docking_results
    assert len(project.history) == 1

    stack.undo()
    assert result not in project.docking_results

    stack.redo()
    assert result in project.docking_results
