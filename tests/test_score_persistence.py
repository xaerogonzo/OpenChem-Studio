"""Score definitions in the project file, the recovery copy and the real window (`docs/DERIVED_SCORES_DESIGN.md` section 8).

The properties that matter are the ones a person would only notice by losing work:

* a project that never used scores is **byte for byte the file it always was** (no block), so an older build opening it loses nothing;
* a definition a build cannot read -- newer, damaged, or in a newer envelope -- **survives a save of a project that was loaded**, unchanged;
* the window's own File > Save, File > Open and recovery carry the definitions (the wiring between the service and the file is what loses them), and
  changing one marks the project unsaved, because a definition is never also a result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.score_definition import ScoreDefinition
from openchem.domain.score_definition_store import ScoreDefinitionStore
from openchem.domain.score_value import ScoreStatus
from openchem.events.base import EventBus
from openchem.services.project_service import DERIVED_SCORES_KEY, ProjectService
from openchem.services.recovery_service import RecoveryService

_NEWER = {"schema_version": 99, "score_id": "user.future", "label": "From the future", "weights": [1, 2], "novel": {"x": None}}
_DAMAGED = {"schema_version": 1, "score_id": "user.broken", "label": "Broken", "formula": 7}


def _definition(score_id="user.a", label="Window") -> ScoreDefinition:
    return ScoreDefinition(score_id, label, "ramp(psa, 140, 60)", "1", (("psa", "descriptor:tpsa"),), owner="Alex", created="2026-10-14", note="n")


def _store(project, *definitions) -> ScoreDefinitionStore:
    store = ScoreDefinitionStore(project.uuid)
    for definition in definitions:
        store.add(definition)
    return store


# --- the project file ------------------------------------------------------------------------------------------------------------


def test_a_project_without_scores_writes_no_block_at_all(tmp_path: Path, qapp):
    service = ProjectService(EventBus())
    project = ProjectModel(name="never used scores")
    plain, none, empty = tmp_path / "plain.ocsproj", tmp_path / "none.ocsproj", tmp_path / "empty.ocsproj"
    service.save(project, plain)
    service.save(project, none, derived_scores=None)
    service.save(project, empty, derived_scores=ScoreDefinitionStore(project.uuid))
    assert DERIVED_SCORES_KEY not in json.loads(plain.read_text(encoding="utf-8"))
    assert plain.read_text(encoding="utf-8") == none.read_text(encoding="utf-8") == empty.read_text(encoding="utf-8")
    assert DERIVED_SCORES_KEY == "derived_scores"


def test_definitions_round_trip_through_a_saved_project(tmp_path: Path, qapp):
    service = ProjectService(EventBus())
    project = ProjectModel(name="with scores")
    store = _store(project, _definition("user.a"), _definition("user.b", "Second"))
    path = tmp_path / "scores.ocsproj"
    service.save(project, path, derived_scores=store)
    assert json.loads(path.read_text(encoding="utf-8"))[DERIVED_SCORES_KEY]["version"] == 1
    loaded = service.load_document(path).derived_scores
    assert loaded.definitions() == store.definitions() and loaded.project_uuid == project.uuid


def test_a_definition_with_a_default_round_trips_through_a_saved_project_in_format_two(tmp_path: Path, qapp):
    service = ProjectService(EventBus())
    project = ProjectModel(name="with a default")
    defaulting = ScoreDefinition(
        "user.d", "Defaulting", "ramp(psa, 140, 60) * ramp(logp, 5, 2)", "1", (("psa", "descriptor:tpsa"), ("logp", "descriptor:mol_logp")),
        schema_version=2, on_missing="default", defaults=(("logp", 3.5),), created="2026-10-15",
    )
    store = _store(project, _definition("user.a"), defaulting)
    path = tmp_path / "defaults.ocsproj"
    service.save(project, path, derived_scores=store)
    written = json.loads(path.read_text(encoding="utf-8"))[DERIVED_SCORES_KEY]["definitions"]
    assert "defaults" not in written[0] and written[0]["schema_version"] == 1, "a score with no default is the file an earlier build wrote"
    assert written[1]["defaults"] == [["logp", 3.5]] and written[1]["schema_version"] == 2 and written[1]["on_missing"] == "default"
    loaded = service.load_document(path).derived_scores
    assert loaded.definitions() == store.definitions() and loaded.definitions()[1].digest == defaulting.digest


def test_a_build_that_reads_only_format_one_keeps_a_score_with_a_default_and_writes_it_back_as_it_was(tmp_path: Path, qapp, monkeypatch):
    """The older build must neither evaluate the definition without its default nor drop it: it is kept, shown as not readable, and saved unchanged."""
    from openchem.domain import score_definition

    defaulting = ScoreDefinition(
        "user.d", "Defaulting", "ramp(psa, 140, 60) * ramp(logp, 5, 2)", "1", (("psa", "descriptor:tpsa"), ("logp", "descriptor:mol_logp")),
        schema_version=2, on_missing="default", defaults=(("logp", 3.5),), created="2026-10-15",
    )
    service = ProjectService(EventBus())
    project = ProjectModel(name="older build")
    path = tmp_path / "defaults.ocsproj"
    service.save(project, path, derived_scores=_store(project, _definition("user.a"), defaulting))
    monkeypatch.setattr(score_definition, "SCHEMA_VERSION", 1)
    older = service.load_document(path).derived_scores
    assert [d.score_id for d in older.definitions()] == ["user.a"]
    (kept,) = older.kept()
    assert kept.score_id == "user.d" and "newer version" in kept.reason
    again = tmp_path / "again.ocsproj"
    service.save(project, again, derived_scores=older)
    assert json.loads(again.read_text(encoding="utf-8"))[DERIVED_SCORES_KEY]["definitions"][1] == defaulting.to_dict()


def test_a_project_saved_before_scores_existed_opens_with_an_empty_store(tmp_path: Path, qapp):
    service = ProjectService(EventBus())
    path = tmp_path / "old.ocsproj"
    service.save(ProjectModel(name="old"), path)
    document = service.load_document(path)
    assert document.derived_scores.is_empty and document.derived_scores.project_uuid == document.project.uuid


@pytest.mark.parametrize(
    "block",
    [
        {"version": 1, "definitions": [_NEWER]},
        {"version": 1, "definitions": [_DAMAGED, "garbage"]},
        {"version": 1, "definitions": [_NEWER, _definition("user.a").to_dict(), _DAMAGED]},
        {"version": 2, "definitions": [], "from": "a newer envelope"},
        ["not", "an", "object"],
    ],
)
def test_what_a_build_cannot_read_survives_loading_and_saving_a_project(tmp_path: Path, qapp, block):
    service = ProjectService(EventBus())
    first = tmp_path / "first.ocsproj"
    document = ProjectModel(name="carries work").to_dict()
    document[DERIVED_SCORES_KEY] = block
    first.write_text(json.dumps(document), encoding="utf-8")

    loaded = service.load_document(first)
    second = tmp_path / "second.ocsproj"
    service.save(loaded.project, second, derived_scores=loaded.derived_scores)
    assert json.loads(second.read_text(encoding="utf-8"))[DERIVED_SCORES_KEY] == block


def test_a_block_that_could_not_be_read_is_reported_in_the_log(tmp_path: Path, qapp, caplog):
    service = ProjectService(EventBus())
    path = tmp_path / "p.ocsproj"
    document = ProjectModel(name="p").to_dict()
    document[DERIVED_SCORES_KEY] = {"version": 1, "definitions": [_DAMAGED]}
    path.write_text(json.dumps(document), encoding="utf-8")
    with caplog.at_level("WARNING"):
        service.load_document(path)
    assert any("Saved score definitions kept but not used" in r.getMessage() for r in caplog.records)


def test_the_recovery_copy_carries_the_definitions(tmp_path: Path, qapp):
    service = RecoveryService(ProjectService(EventBus()), tmp_path / "recovery")
    project = ProjectModel(name="unsaved")
    project.molecules.append(MoleculeModel(uuid="m"))
    store = _store(project, _definition())
    assert service.write(project, None, None, service.generation, derived_scores=store)
    [candidate] = service.candidates()
    assert service.load(candidate).derived_scores.definitions() == store.definitions()


# --- the real window ---------------------------------------------------------------------------------------------------------------


@pytest.fixture
def window(qapp, tmp_path):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none"))
    built = MainWindow(services, settings, SessionManager())
    yield built
    built.close()


def _project_with_one_molecule(window) -> MoleculeModel:
    model = MoleculeModel(display_name="Aspirin")
    window._services.chemistry_engine.set_structure_from_smiles(model, "CC(=O)Oc1ccccc1C(=O)O")
    project = ProjectModel(name="p")
    project.molecules.append(model)
    window._set_project(project)
    return model


def _make(window, label="Window blend"):
    return window._services.score_service.create(
        label=label, formula="ramp(psa, 140, 60)", result_unit="1", inputs=[("psa", "descriptor:tpsa")]
    )


def test_making_a_score_marks_the_session_unsaved_and_so_does_removing_it(window, qapp):
    _project_with_one_molecule(window)
    assert not window._session.is_dirty
    made = _make(window)
    assert window._session.is_dirty
    window._session.mark_clean()
    assert window._services.score_service.remove(made.score_id) and window._session.is_dirty


def test_a_failed_attempt_does_not_mark_anything_unsaved(window, qapp):
    from openchem.domain.score_formula import FormulaError

    _project_with_one_molecule(window)
    with pytest.raises(FormulaError):
        window._services.score_service.create(label="Bad", formula="psa +", result_unit="1", inputs=[("psa", "descriptor:tpsa")])
    assert not window._session.is_dirty


def test_a_new_project_starts_with_no_scores_and_the_old_ones_are_gone(window, qapp):
    _project_with_one_molecule(window)
    _make(window)
    window._set_project(ProjectModel(name="fresh"))
    service = window._services.score_service
    assert len(service.store) == 0 and service.store.project_uuid == window._session.project.uuid


def test_scores_survive_the_windows_own_save_and_open(window, qapp, tmp_path, monkeypatch):
    """Through `save_project_to` and `_open_project`, the paths File > Save and File > Open take: the wiring between the service and the file is what carries them."""
    from PySide6.QtWidgets import QFileDialog

    model = _project_with_one_molecule(window)
    made = _make(window)
    path = tmp_path / "saved.ocsproj"
    window.save_project_to(path)
    assert not window._session.is_dirty

    window._set_project(ProjectModel(name="something else"))
    assert window._services.score_service.store.get(made.score_id) is None
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))
    window._open_project()

    reopened = window._services.score_service.store.get(made.score_id)
    assert reopened == made and window._session.project.find_molecule(model.uuid) is not None
    # And it is the store a later edit changes, not a copy: change it, save, and the file says so.
    window._services.score_service.update(made.score_id, note="edited after opening")
    window.save_project_to(path)
    saved = json.loads(path.read_text(encoding="utf-8"))[DERIVED_SCORES_KEY]["definitions"]
    assert [d["note"] for d in saved] == ["edited after opening"]


def test_a_window_save_of_a_project_with_no_scores_writes_no_block(window, qapp, tmp_path):
    _project_with_one_molecule(window)
    path = tmp_path / "plain.ocsproj"
    window.save_project_to(path)
    assert DERIVED_SCORES_KEY not in json.loads(path.read_text(encoding="utf-8"))


def test_what_the_window_could_not_read_survives_its_own_open_and_save(window, qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    document = ProjectModel(name="carries work").to_dict()
    block = {"version": 1, "definitions": [_NEWER, _DAMAGED]}
    document[DERIVED_SCORES_KEY] = block
    first, second = tmp_path / "first.ocsproj", tmp_path / "second.ocsproj"
    first.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(first), "")))
    window._open_project()
    store = window._services.score_service.store
    assert [k.kind for k in store.kept()] == ["newer", "damaged"]
    window.save_project_to(second)
    assert json.loads(second.read_text(encoding="utf-8"))[DERIVED_SCORES_KEY] == block


def test_scores_reach_the_recovery_copy_and_come_back_with_it(window, qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    service = RecoveryService(window._services.project_service, tmp_path / "recovery")
    window.enable_recovery(service, delay_ms=0)
    _project_with_one_molecule(window)
    made = _make(window)
    for _ in range(20):
        qapp.processEvents()
    [candidate] = service.candidates()
    assert service.load(candidate).derived_scores.get(made.score_id) == made

    window._set_project(ProjectModel(name="something else"))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    assert window.offer_recovery()
    assert window._services.score_service.store.get(made.score_id) == made and window._session.is_dirty


def test_the_drive_harness_reopens_a_project_with_its_scores(window, qapp, tmp_path):
    """The harness's `open_project` must hand over what File > Open does, or no driven save-then-reopen could notice them lost."""
    from openchem.app.debug_drive import _Driver

    _project_with_one_molecule(window)
    made = _make(window)
    path = tmp_path / "driven.ocsproj"
    driver = _Driver(window, [])
    driver._do_save_project({"path": str(path)})
    window._set_project(ProjectModel(name="something else"))
    driver._do_open_project({"path": str(path)})
    assert window._services.score_service.store.get(made.score_id) == made


def test_a_reopened_score_reads_the_results_the_project_kept(window, qapp, tmp_path, monkeypatch):
    """The whole route: the real descriptors compute, the project saves its results and its score, reopens, and the score has its value without anything running."""
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QFileDialog

    from openchem.domain.calculator import DRAWING

    model = _project_with_one_molecule(window)
    made = _make(window)
    window._services.descriptor_service.request_descriptors(model, DRAWING)
    QThreadPool.globalInstance().waitForDone(60_000)
    for _ in range(50):
        qapp.processEvents()
    before = window._services.score_service.values_for(model)[0]
    assert before.status is ScoreStatus.VALUE, before.reason

    path = tmp_path / "whole.ocsproj"
    window.save_project_to(path)
    window._set_project(ProjectModel(name="something else"))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))
    window._open_project()
    reopened = window._session.project.find_molecule(model.uuid)
    after = window._services.score_service.values_for(reopened)[0]
    assert after.status is ScoreStatus.VALUE and after.value == pytest.approx(before.value) and after.definition.score_id == made.score_id
