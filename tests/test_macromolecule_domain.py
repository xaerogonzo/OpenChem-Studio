from __future__ import annotations

from pathlib import Path

from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.services.project_service import ProjectService


def test_macromolecule_to_dict_from_dict_roundtrip():
    model = MacromoleculeModel(
        display_name="Lysozyme",
        structure_text="ATOM      1  N   ALA A   1\n",
        source_format="pdb",
        metadata={"resolution": 1.8, "experimental_method": "X-RAY DIFFRACTION"},
    )

    data = model.to_dict()
    restored = MacromoleculeModel.from_dict(data)

    assert restored.uuid == model.uuid
    assert restored.display_name == "Lysozyme"
    assert restored.structure_text == model.structure_text
    assert restored.source_format == "pdb"
    assert restored.metadata == {"resolution": 1.8, "experimental_method": "X-RAY DIFFRACTION"}


def test_macromolecule_from_dict_defaults_for_missing_keys():
    restored = MacromoleculeModel.from_dict({"uuid": "abc"})
    assert restored.display_name == "Untitled macromolecule"
    assert restored.structure_text == ""
    assert restored.source_format == "pdb"
    assert restored.metadata == {}


def test_project_find_macromolecule():
    project = ProjectModel()
    macromolecule = MacromoleculeModel(display_name="Test structure")
    project.macromolecules.append(macromolecule)

    assert project.find_macromolecule(macromolecule.uuid) is macromolecule
    assert project.find_macromolecule("does-not-exist") is None


def test_macromolecules_survive_project_roundtrip(tmp_path: Path, qapp):
    service = ProjectService(EventBus())

    project = ProjectModel(name="Macromolecule project")
    macromolecule = MacromoleculeModel(
        display_name="Test PDB", structure_text="HEADER\nATOM\n", source_format="pdb"
    )
    project.macromolecules.append(macromolecule)

    path = tmp_path / "test.ocsproj"
    service.save(project, path)
    loaded = service.load(path)

    assert len(loaded.macromolecules) == 1
    assert loaded.macromolecules[0].uuid == macromolecule.uuid
    assert loaded.macromolecules[0].structure_text == "HEADER\nATOM\n"


def test_old_project_file_without_macromolecules_key_loads_fine(tmp_path: Path, qapp):
    """Additive-field regression: a project file saved before macromolecules
    existed (no "macromolecules" key at all) must still load, matching the
    same .get(key, default) precedent MoleculeModel.conformers established.
    """
    service = ProjectService(EventBus())
    project = ProjectModel(name="Old project")
    path = tmp_path / "old.ocsproj"
    service.save(project, path)

    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    del data["macromolecules"]
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = service.load(path)
    assert loaded.macromolecules == []
