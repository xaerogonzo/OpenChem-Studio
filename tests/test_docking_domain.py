from __future__ import annotations

from pathlib import Path

from openchem.domain.common import Provenance
from openchem.domain.docking import DockingBox, DockingPoseModel, DockingResultModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.services.project_service import ProjectService


def _make_result() -> DockingResultModel:
    return DockingResultModel(
        ligand_molecule_uuid="lig-1",
        receptor_macromolecule_uuid="rec-1",
        box=DockingBox(center=(1.0, 2.0, 3.0), size=(20.0, 20.0, 20.0)),
        poses=[
            DockingPoseModel(
                pose_molblock="mock molblock",
                binding_affinity_kcal_mol=-6.5,
                rmsd_lb=0.0,
                rmsd_ub=0.0,
                metadata={"note": "best pose"},
            )
        ],
        provenance=Provenance(created_by="core", method="vina", parameters={"num_poses": 9}),
        engine="vina-python",
        engine_version="1.2.7",
        scoring_function="vina",
        exhaustiveness=8,
        seed=42,
        receptor_prep_params={"addh": True},
        ligand_prep_params={"addh": True},
    )


def test_docking_result_to_dict_from_dict_roundtrip():
    result = _make_result()
    restored = DockingResultModel.from_dict(result.to_dict())

    assert restored.uuid == result.uuid
    assert restored.ligand_molecule_uuid == "lig-1"
    assert restored.receptor_macromolecule_uuid == "rec-1"
    assert restored.box.center == (1.0, 2.0, 3.0)
    assert restored.box.size == (20.0, 20.0, 20.0)
    assert len(restored.poses) == 1
    assert restored.poses[0].binding_affinity_kcal_mol == -6.5
    assert restored.poses[0].metadata == {"note": "best pose"}
    assert restored.provenance.method == "vina"
    assert restored.engine == "vina-python"
    assert restored.seed == 42
    assert restored.receptor_prep_params == {"addh": True}


def test_project_find_docking_result():
    project = ProjectModel()
    result = _make_result()
    project.docking_results.append(result)

    assert project.find_docking_result(result.uuid) is result
    assert project.find_docking_result("nope") is None


def test_docking_results_survive_project_roundtrip(tmp_path: Path, qapp):
    service = ProjectService(EventBus())
    project = ProjectModel(name="Docking project")
    result = _make_result()
    project.docking_results.append(result)

    path = tmp_path / "test.ocsproj"
    service.save(project, path)
    loaded = service.load(path)

    assert len(loaded.docking_results) == 1
    assert loaded.docking_results[0].uuid == result.uuid
    assert loaded.docking_results[0].poses[0].binding_affinity_kcal_mol == -6.5


def test_old_project_file_without_docking_results_key_loads_fine(tmp_path: Path, qapp):
    service = ProjectService(EventBus())
    project = ProjectModel(name="Old project")
    path = tmp_path / "old.ocsproj"
    service.save(project, path)

    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    del data["docking_results"]
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = service.load(path)
    assert loaded.docking_results == []
