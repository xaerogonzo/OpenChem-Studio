"""The recovery copy: written while dirty, gone after Save, never a fake project."""

from __future__ import annotations

import json

from openchem.domain.calculator import DRAWING
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.result_store import BundlePart, BundleState, ResultIdentity, SessionResultStore, StoredResult
from openchem.domain.scientific_result import PerAtomDataset
from openchem.events.base import EventBus
from openchem.services.project_service import ProjectService
from openchem.services.recovery_service import RecoveryService


def _project_with_results() -> tuple[ProjectModel, SessionResultStore]:
    project = ProjectModel(name="unsaved work")
    project.molecules.append(MoleculeModel(uuid="m"))
    store = SessionResultStore(project.uuid)
    dataset = PerAtomDataset(property_id="a", name="a", units="", method="", molecule_uuid="m", values={0: 1.0})
    store.put(StoredResult(ResultIdentity("m", "a", DRAWING, "fp", "rdkit"), dataset))
    store.record_part("m", BundlePart("rdkit", "fp", ("a",)))
    return project, store


def _service(tmp_path, clock=None) -> RecoveryService:
    kwargs = {"clock": clock} if clock else {}
    return RecoveryService(ProjectService(EventBus()), tmp_path / "recovery", **kwargs)


def test_a_written_copy_is_offered_with_its_results(qapp, tmp_path):
    service = _service(tmp_path, clock=lambda: 1234.0)
    project, store = _project_with_results()

    assert service.write(project, store, None, service.generation)
    [candidate] = service.candidates()

    assert candidate.project_uuid == project.uuid
    assert candidate.written_at == 1234.0
    assert candidate.molecule_count == 1
    loaded_project, loaded_results = service.load(candidate)
    assert loaded_project.name == "unsaved work"
    assert loaded_results.bundle_state("m", "fp", {"rdkit"})[0] is BundleState.COMPLETE


def test_a_write_queued_before_a_save_cannot_recreate_the_file(qapp, tmp_path):
    """THE RACE: scheduled, then Save, then the timer fires."""
    service = _service(tmp_path)
    project, store = _project_with_results()
    queued_under = service.generation
    service.write(project, store, None, queued_under)

    service.settle(project.uuid)  # Save succeeded
    assert not service.write(project, store, None, queued_under)

    assert service.candidates() == []


def test_a_truncated_file_is_not_offered(qapp, tmp_path):
    service = _service(tmp_path)
    project, store = _project_with_results()
    service.write(project, store, None, service.generation)
    path = service.path_for(project.uuid)
    path.write_text(path.read_text(encoding="utf-8")[: len(path.read_text(encoding="utf-8")) // 2], encoding="utf-8")

    assert service.candidates() == []


def test_a_file_whose_name_and_contents_disagree_is_not_offered(qapp, tmp_path):
    service = _service(tmp_path)
    project, store = _project_with_results()
    service.write(project, store, None, service.generation)
    service.path_for(project.uuid).rename(service.path_for("some-other-project"))

    assert service.candidates() == []


def test_a_newer_recovery_format_is_not_offered(qapp, tmp_path):
    service = _service(tmp_path)
    project, store = _project_with_results()
    service.write(project, store, None, service.generation)
    path = service.path_for(project.uuid)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["recovery_version"] = 99
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert service.candidates() == []


def test_newest_first(qapp, tmp_path):
    times = iter([10.0, 20.0])
    service = _service(tmp_path, clock=lambda: next(times))
    older, store_a = _project_with_results()
    newer, store_b = _project_with_results()
    service.write(older, store_a, None, service.generation)
    service.write(newer, store_b, None, service.generation)

    assert [c.project_uuid for c in service.candidates()] == [newer.uuid, older.uuid]


def test_no_directory_is_no_candidates(qapp, tmp_path):
    assert _service(tmp_path).candidates() == []
