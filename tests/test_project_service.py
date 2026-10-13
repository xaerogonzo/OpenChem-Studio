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


def test_a_conformers_identity_survives_a_save_and_reload(tmp_path):
    """A stable id, or provenance citing a conformer means nothing.

    Provenance that named a conformer by INDEX would be wrong the moment
    anything re-sorted the list -- index 0 today is index 3 tomorrow. The
    id has to be the thing that travels, and an id that is only stable in
    memory is not stable at all: this is the round trip that proves it.
    """
    from openchem.domain.conformer import ConformerModel
    from openchem.domain.molecule import MoleculeModel
    from openchem.domain.project import ProjectModel

    conformers = [
        ConformerModel(molblock="a\n", energy=3.0, method="rdkit"),
        ConformerModel(molblock="b\n", energy=1.0, method="rdkit"),
        ConformerModel(molblock="c\n", energy=2.0, method="rdkit"),
    ]
    molecule = MoleculeModel(display_name="m", molblock="x\n", conformers=conformers)
    project = ProjectModel(name="p", molecules=[molecule])

    service = ProjectService(EventBus())
    path = tmp_path / "project.ocsproj"
    service.save(project, path)
    reloaded = service.load(path)

    restored = reloaded.molecules[0].conformers
    assert [c.conformer_id for c in restored] == [c.conformer_id for c in conformers]

    # ...and it still identifies the right geometry after a re-sort, which
    # is the case an index cannot survive.
    by_energy = sorted(restored, key=lambda c: c.energy)
    target = next(c for c in by_energy if c.conformer_id == conformers[0].conformer_id)
    assert target.molblock == "a\n"
    assert by_energy.index(target) != 0, "the re-sort must actually move it, or this proves nothing"


# --- recipe runs: a block of their own in the file ---------------------------------------------------------


def _recipe_run(*molecule_uuids: str):
    from openchem.domain.recipe_run import RecipeRun, RecipeRunStatus, SlotInput, StepRecord, StepState

    return RecipeRun(
        run_id="run-1", recipe_id="probe_pair", recipe_version="1", status=RecipeRunStatus.COMPLETED,
        inputs=tuple(SlotInput(f"slot{i}", uuid, f"key-{i}") for i, uuid in enumerate(molecule_uuids)),
        steps=(StepRecord("compare", StepState.COMPLETED),), created_at=5.0,
    )


def test_recipe_runs_are_written_to_their_own_key_and_read_back(tmp_path: Path, qapp):
    from openchem.domain.recipe_run import RecipeRunStore
    from openchem.services.project_service import RECIPE_RUNS_KEY

    service = ProjectService(EventBus())
    project = ProjectModel(name="Recipes")
    project.molecules.append(MoleculeModel(display_name="A", molblock="dummy"))
    runs = RecipeRunStore(project.uuid)
    runs.record(_recipe_run(project.molecules[0].uuid))

    path = tmp_path / "recipes.ocsproj"
    service.save(project, path, recipe_runs=runs)
    assert RECIPE_RUNS_KEY in json.loads(path.read_text(encoding="utf-8"))

    document = service.load_document(path)
    assert document.recipe_runs.get("run-1") == runs.get("run-1")
    assert document.recipe_runs.load_problems == []
    assert document.project.uuid == project.uuid


def test_a_project_saved_with_no_recipe_runs_is_an_ordinary_project(tmp_path: Path, qapp):
    """A file from before this block, and a save from a caller that has none, both load with an empty store."""
    from openchem.services.project_service import RECIPE_RUNS_KEY

    service = ProjectService(EventBus())
    project = ProjectModel(name="Plain")
    path = tmp_path / "plain.ocsproj"
    service.save(project, path)

    assert RECIPE_RUNS_KEY not in json.loads(path.read_text(encoding="utf-8"))
    document = service.load_document(path)
    assert document.recipe_runs.all_runs() == [] and document.recipe_runs.project_uuid == project.uuid


def test_a_newer_recipe_block_does_not_stop_the_project_opening(tmp_path: Path, qapp, caplog):
    """The file opens, the runs it cannot read are not shown, and the load says so."""
    import logging

    from openchem.domain.recipe_run import ENVELOPE_VERSION, RecipeRunStore
    from openchem.services.project_service import RECIPE_RUNS_KEY

    service = ProjectService(EventBus())
    project = ProjectModel(name="Future")
    path = tmp_path / "future.ocsproj"
    runs = RecipeRunStore(project.uuid)
    service.save(project, path, recipe_runs=runs)
    data = json.loads(path.read_text(encoding="utf-8"))
    data[RECIPE_RUNS_KEY]["envelope_version"] = ENVELOPE_VERSION + 1
    path.write_text(json.dumps(data), encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        document = service.load_document(path)
    assert document.project.name == "Future" and document.recipe_runs.all_runs() == []
    assert document.recipe_runs.load_problems
    assert any("Saved recipe runs not restored" in r.getMessage() for r in caplog.records)


def test_the_document_unpacks_as_a_tuple_and_reads_by_name(tmp_path: Path, qapp):
    service = ProjectService(EventBus())
    project = ProjectModel(name="Both ways")
    path = tmp_path / "both.ocsproj"
    service.save(project, path)
    document = service.load_document(path)
    unpacked_project, results, qc_runs, recipe_runs = document
    assert (unpacked_project, results, qc_runs, recipe_runs) == (
        document.project, document.results, document.qc_runs, document.recipe_runs)
