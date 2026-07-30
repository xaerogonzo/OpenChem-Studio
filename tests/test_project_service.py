from __future__ import annotations

import json
from pathlib import Path

import pytest

from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import ProjectLoaded
from openchem.services.project_service import ProjectService


def test_save_and_load_roundtrip(tmp_path: Path, qapp):
    service = ProjectService(EventBus())

    project = ProjectModel(name="Test project")
    molecule = MoleculeModel(display_name="Benzene", canonical_smiles="c1ccccc1", molblock="dummy")
    project.molecules.append(molecule)
    project.record_history("created")

    path = tmp_path / "test.ocsproj"
    service.save(project, path)
    loaded = service.load(path)

    assert loaded.uuid == project.uuid
    assert loaded.name == "Test project"
    assert len(loaded.molecules) == 1
    assert loaded.molecules[0].uuid == molecule.uuid
    assert loaded.molecules[0].canonical_smiles == "c1ccccc1"
    assert loaded.schema_version == project.schema_version
    assert len(loaded.history) == 1


def test_conformers_survive_project_roundtrip(tmp_path: Path, qapp):
    service = ProjectService(EventBus())

    project = ProjectModel(name="Conformer project")
    conformer = ConformerModel(molblock="mock molblock", energy=12.34, method="rdkit+MMFF94/UFF")
    molecule = MoleculeModel(display_name="Ethanol", molblock="dummy", conformers=[conformer])
    project.molecules.append(molecule)

    path = tmp_path / "conformers.ocsproj"
    service.save(project, path)
    loaded = service.load(path)

    assert len(loaded.molecules[0].conformers) == 1
    loaded_conformer = loaded.molecules[0].conformers[0]
    assert loaded_conformer.conformer_id == conformer.conformer_id
    assert loaded_conformer.molblock == "mock molblock"
    assert loaded_conformer.energy == 12.34
    assert loaded_conformer.method == "rdkit+MMFF94/UFF"


def test_old_project_without_conformers_key_still_loads(tmp_path: Path, qapp):
    """A project file saved before conformers existed has no "conformers"
    key at all — must still load without a schema migration."""
    service = ProjectService(EventBus())
    project = ProjectModel(name="Pre-conformer project")
    molecule = MoleculeModel(display_name="Old molecule", molblock="dummy")
    project.molecules.append(molecule)

    data = project.to_dict()
    del data["molecules"][0]["conformers"]
    path = tmp_path / "old.ocsproj"
    path.write_text(json.dumps(data))

    loaded = service.load(path)
    assert loaded.molecules[0].conformers == []


def test_load_publishes_project_loaded_event(tmp_path: Path, qapp):
    bus = EventBus()
    service = ProjectService(bus)
    project = ProjectModel(name="Events test")
    path = tmp_path / "events.ocsproj"
    service.save(project, path)

    received = []
    bus.subscribe(ProjectLoaded, lambda e: received.append(e.project_uuid))
    service.load(path)

    assert received == [project.uuid]


def test_future_schema_version_rejected(tmp_path: Path, qapp):
    service = ProjectService(EventBus())
    path = tmp_path / "future.ocsproj"
    data = ProjectModel().to_dict()
    data["schema_version"] = 999
    path.write_text(json.dumps(data))

    with pytest.raises(ValueError):
        service.load(path)
