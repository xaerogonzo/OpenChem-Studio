from __future__ import annotations

import json
from pathlib import Path

import pytest

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
