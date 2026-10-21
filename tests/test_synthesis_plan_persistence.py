"""Saving synthesis plans in the project file: the block, the store, the planning service's restore and the window's own save, open and recovery.

Three layers, each asserted where it is real: the store and the project service on text (what a file holds and what an older or damaged file does), the planning service on what it will SHOW from a file (the
gate asked again, the routes validated again, the sentences the reading build's own), and the window through `save_project_to`, `_open_project` and the recovery offer, the paths a person's menu takes.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
import test_synthesis_planner as planner_fixtures
from test_synthesis_planning_service import SARIN, molecule

from openchem.chem.aizynth_planner import BENCHMARK_FINDING
from openchem.chem.engine import ChemistryEngine
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.synthesis_gate import GateDecision, GateOutcome, NodeScreening
from openchem.domain.synthesis_plan_store import ENVELOPE_VERSION, MAX_PLANS, SynthesisPlanStore
from openchem.domain.synthesis_route import (
    LEFT_OUT_PREFIX,
    STANDARD_LIMITATIONS,
    RouteSet,
    RouteStatus,
    SearchTermination,
    TargetIdentity,
    route_molecules,
)
from openchem.domain.synthesis_route_codec import encode_route_set
from openchem.events.base import EventBus
from openchem.services.project_service import SYNTHESIS_PLANS_KEY, ProjectService
from openchem.services.synthesis_planning_service import SynthesisPlanningService

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
SENTINEL = "ZZ-INJECTED-SENTENCE-ZZ"


def plan_for(target: MoleculeModel, name: str = "aspirin_it100", *, screen: bool = False) -> RouteSet:
    """A plan the real parser made from a real planner output, for `target`. `screen` adds hand-made screenings dated 2026-10-21, so no ruleset is needed."""
    document = planner_fixtures.fixture(name)
    identity = TargetIdentity(molecule_uuid=target.uuid, canonical_smiles=target.canonical_smiles, fingerprint="fp")
    plan = planner_fixtures.host.parse_document(document, planner_fixtures.request_for(document), identity)
    if screen:
        molecules = tuple(dict.fromkeys(m for r in plan.routes for m in route_molecules(r)))
        plan = dataclasses.replace(
            plan,
            node_screenings=tuple(NodeScreening(smiles=m, screened=True, rulesets_consulted=("rs-1",), screened_on="2026-10-21") for m in molecules),
        )
    return plan


def store_of(project: ProjectModel, *plans: RouteSet) -> SynthesisPlanStore:
    store = SynthesisPlanStore(project.uuid)
    for plan in plans:
        assert store.put(plan)
    return store


def reread(store: SynthesisPlanStore) -> SynthesisPlanStore:
    """The store as a project file hands it back: written as text, read as text."""
    return SynthesisPlanStore.from_dict(json.loads(json.dumps(store.to_dict(), indent=2)), store.project_uuid)


def allow_all(_smiles: str) -> GateDecision:
    return GateDecision(outcome=GateOutcome.ALLOWED, ruleset_version="t", ruleset_sha256="t", screened_on="2026-10-21")


@pytest.fixture
def service(qapp):
    built = SynthesisPlanningService(EventBus(), setup_provider=lambda: None, gate=allow_all)
    yield built
    built.shutdown(2000)


# --- the block in the file ---------------------------------------------------------------------------------------------------------------


def test_a_project_that_never_planned_is_the_file_it_always_was(qapp):
    project = ProjectModel(name="p")
    plain = ProjectService(EventBus()).serialise(project)
    empty = ProjectService(EventBus()).serialise(project, synthesis_plans=SynthesisPlanStore(project.uuid))
    assert plain == empty and SYNTHESIS_PLANS_KEY not in json.loads(plain)


def test_plans_are_written_under_their_own_key_and_read_back_by_the_project_service(qapp):
    project = ProjectModel(name="p")
    target = molecule(ASPIRIN)
    project.molecules.append(target)
    text = ProjectService(EventBus()).serialise(project, synthesis_plans=store_of(project, plan_for(target)))
    data = json.loads(text)
    assert data[SYNTHESIS_PLANS_KEY]["version"] == ENVELOPE_VERSION and len(data[SYNTHESIS_PLANS_KEY]["plans"]) == 1
    document = ProjectService(EventBus()).parse(data)
    assert document.synthesis_plans.get(target.uuid) is not None and document.synthesis_plans.load_problems == ()


def test_a_project_saved_before_plans_were_kept_loads_with_none(qapp):
    document = ProjectService(EventBus()).parse(ProjectModel(name="old").to_dict())
    assert document.synthesis_plans.is_empty and document.synthesis_plans.load_problems == ()


def test_the_other_blocks_are_untouched_by_the_new_one(qapp):
    project = ProjectModel(name="p")
    target = molecule(ASPIRIN)
    project.molecules.append(target)
    service = ProjectService(EventBus())
    with_plans = json.loads(service.serialise(project, synthesis_plans=store_of(project, plan_for(target))))
    without = json.loads(service.serialise(project))
    assert {k: v for k, v in with_plans.items() if k != SYNTHESIS_PLANS_KEY} == without


def test_a_block_from_a_newer_envelope_restores_nothing_and_says_so():
    block = {"version": ENVELOPE_VERSION + 1, "plans": [{"anything": 1}]}
    store = SynthesisPlanStore.from_dict(block, "u")
    assert store.is_empty and len(store.load_problems) == 1 and "envelope" in store.load_problems[0]


@pytest.mark.parametrize("block", ["text", 7, [], {"version": "1", "plans": []}, {"version": True, "plans": []}, {"version": 1}, {"version": 1, "plans": "x"}])
def test_a_block_that_is_not_an_envelope_restores_nothing_and_never_raises(block):
    store = SynthesisPlanStore.from_dict(block, "u")
    assert store.is_empty and store.load_problems


def test_one_bad_plan_does_not_cost_the_others(qapp):
    a, b = molecule(ASPIRIN, "a"), molecule("CC(=O)Nc1ccc(O)cc1", "b")
    block = store_of(ProjectModel(), plan_for(a), plan_for(b, "paracetamol_it100")).to_dict()
    block["plans"][0]["status"] = "refused"
    block["plans"][1]["routes"][0]["steps"][0]["policy_probability"] = SENTINEL
    block["plans"].append(dict(block["plans"][1]))
    good = encode_route_set(plan_for(molecule("CCO", "c"), "caffeine_it100"))
    block["plans"].append(good)
    store = SynthesisPlanStore.from_dict(block, "u")
    assert [p.target.molecule_uuid for p in store.plans()] == [good["target"]["molecule_uuid"]]
    assert len(store.load_problems) == 3
    assert all(SENTINEL not in p and a.uuid not in p for p in store.load_problems)


def test_a_molecule_listed_twice_keeps_the_first(qapp):
    target = molecule(ASPIRIN)
    one = encode_route_set(plan_for(target))
    other = encode_route_set(plan_for(target, "sildenafil_it100"))
    store = SynthesisPlanStore.from_dict({"version": ENVELOPE_VERSION, "plans": [one, other]}, "u")
    assert len(store) == 1 and len(store.get(target.uuid).routes) == len(plan_for(target).routes)
    assert len(store.load_problems) == 1


def test_a_project_holds_at_most_the_most_plans(qapp, monkeypatch):
    import openchem.domain.synthesis_plan_store as module

    monkeypatch.setattr(module, "MAX_PLANS", 2)
    store = SynthesisPlanStore("u")
    kept = [store.put(plan_for(molecule("CCO", str(i)))) for i in range(3)]
    assert kept == [True, True, False]
    block = {"version": ENVELOPE_VERSION, "plans": [encode_route_set(plan_for(molecule("CCO", str(i)))) for i in range(3)]}
    assert len(SynthesisPlanStore.from_dict(block, "u")) == 2
    assert MAX_PLANS == 2000


def test_a_plan_that_is_not_a_result_is_not_put(qapp):
    target = molecule(ASPIRIN)
    refused = RouteSet(status=RouteStatus.REFUSED, target=plan_for(target).target, planner=plan_for(target).planner, reason="r")
    cancelled = RouteSet(
        status=RouteStatus.CANCELLED, target=plan_for(target).target, planner=plan_for(target).planner, reason="r", termination=SearchTermination.CANCELLED
    )
    store = SynthesisPlanStore("u")
    assert not store.put(refused) and not store.put(cancelled) and store.is_empty


# --- what the planning service will show from a file --------------------------------------------------------------------------------------


def opened(service: SynthesisPlanningService, project: ProjectModel, *plans: RouteSet):
    problems = service.set_project(project, reread(store_of(project, *plans)))
    return problems


def test_a_stored_plan_is_the_plan_for_its_molecule_after_the_file(service):
    target = molecule(ASPIRIN)
    project = ProjectModel(name="p", molecules=[target])
    assert opened(service, project, plan_for(target)) == ()
    bound = service.result_for(target)
    assert bound is not None and bound.is_current and bound.route_set.status is RouteStatus.FOUND
    assert len(bound.route_set.routes) == len(plan_for(target).routes)


def test_the_routes_are_validated_again_and_not_believed_from_the_file(service):
    target = molecule(ASPIRIN)
    project = ProjectModel(name="p", molecules=[target])
    store = store_of(project, plan_for(target))
    block = json.loads(json.dumps(store.to_dict()))
    for route in block["plans"][0]["routes"]:
        route["validation"] = {"molecules": "pass", "reactions": "pass", "mapping": "complete", "conservation": "pass", "stock": "all_in_stock"}
    service.set_project(project, SynthesisPlanStore.from_dict(block, project.uuid))
    routes = service.result_for(target).route_set.routes
    assert routes and all(r.validation is not None for r in routes)
    assert [r.validation for r in routes] == [r.validation for r in plan_for(target).routes]


def test_the_sentences_are_this_builds_and_a_file_cannot_add_one(service):
    target = molecule(ASPIRIN)
    project = ProjectModel(name="p", molecules=[target])
    block = json.loads(json.dumps(store_of(project, plan_for(target)).to_dict()))
    block["plans"][0]["limitations"] = [SENTINEL, "An old measured result that no longer holds."]
    block["plans"][0]["left_out"] = [SENTINEL]
    service.set_project(project, SynthesisPlanStore.from_dict(block, project.uuid))
    limitations = service.result_for(target).route_set.all_limitations()
    assert all(s in limitations for s in STANDARD_LIMITATIONS)
    assert limitations.count(BENCHMARK_FINDING) == 1
    assert not any(SENTINEL in s or "An old measured result" in s for s in limitations)


def test_a_left_out_sentence_the_search_wrote_survives_the_file(service):
    target = molecule(ASPIRIN)
    project = ProjectModel(name="p", molecules=[target])
    made = plan_for(target)
    note = LEFT_OUT_PREFIX + "2 had no reaction."
    made = dataclasses.replace(made, limitations=made.limitations + (note,))
    opened(service, project, made)
    assert note in service.result_for(target).route_set.limitations


def test_a_screening_is_shown_with_the_date_it_was_made_and_the_note_that_it_was_not_repeated(service):
    target = molecule(ASPIRIN)
    project = ProjectModel(name="p", molecules=[target])
    opened(service, project, plan_for(target, screen=True))
    restored = service.result_for(target).route_set
    assert restored.node_screenings and any("2026-10-21" in s and "not repeated" in s for s in restored.limitations)


def test_a_plan_with_no_screening_makes_no_claim_about_one(service):
    target = molecule(ASPIRIN)
    project = ProjectModel(name="p", molecules=[target])
    opened(service, project, plan_for(target))
    restored = service.result_for(target).route_set
    assert not any("not repeated" in s for s in restored.limitations)
    assert any("have not been checked" in s for s in restored.all_limitations())


def test_a_plan_for_a_molecule_the_project_does_not_have_is_dropped_and_says_so(service):
    target, other = molecule(ASPIRIN), molecule(ASPIRIN, "other")
    project = ProjectModel(name="p", molecules=[other])
    problems = opened(service, project, plan_for(target))
    assert len(problems) == 1 and target.uuid not in problems[0] and ASPIRIN not in problems[0]
    assert service.result_for(target) is None and service.result_for(other) is None


def test_a_store_read_for_another_project_is_ignored(service):
    target = molecule(ASPIRIN)
    project = ProjectModel(name="p", molecules=[target])
    foreign = store_of(ProjectModel(), plan_for(target))
    assert foreign.project_uuid != project.uuid
    service.set_project(project, foreign)
    assert service.result_for(target) is None


def test_a_new_project_holds_none_of_the_last_projects_plans(service):
    target = molecule(ASPIRIN)
    first = ProjectModel(name="one", molecules=[target])
    opened(service, first, plan_for(target))
    assert service.result_for(target) is not None
    service.set_project(ProjectModel(name="two"))
    assert service.result_for(target) is None
    assert service.plan_store(first).is_empty


# --- the gate is asked again of a file -----------------------------------------------------------------------------------------------------


def refused_plan(uuid_source: MoleculeModel) -> RouteSet:
    """A plan whose TARGET is a structure the gate refuses, carrying real routes: what a file edited by hand could say."""
    base = plan_for(uuid_source)
    return dataclasses.replace(base, target=TargetIdentity(molecule_uuid=uuid_source.uuid, canonical_smiles=SARIN, fingerprint="fp"))


def test_a_file_cannot_put_routes_for_a_refused_target_on_screen(qapp):
    from openchem.chem import synthesis_gate as gate_module

    gate_module.reset_gate_engine()
    try:
        real = SynthesisPlanningService(EventBus(), setup_provider=lambda: None)
        target = molecule(ASPIRIN)
        project = ProjectModel(name="p", molecules=[target])
        problems = opened(real, project, refused_plan(target))
        assert len(problems) == 1 and "regulatory" in problems[0] and SARIN not in problems[0]
        assert real.result_for(target) is None and real.plan_store(project).is_empty
    finally:
        gate_module.reset_gate_engine()


@pytest.mark.parametrize("outcome", [GateOutcome.REFUSED, GateOutcome.UNSCREENED])
def test_a_gate_that_refuses_or_cannot_tell_drops_the_plan(qapp, outcome):
    from openchem.domain.synthesis_gate import GateMatch

    def gate(_smiles: str) -> GateDecision:
        if outcome is GateOutcome.REFUSED:
            return GateDecision(outcome=outcome, reason="r", matches=(GateMatch(ruleset_id="x", rule_id="y", display_name="z"),))
        return GateDecision(outcome=outcome, reason="r")

    svc = SynthesisPlanningService(EventBus(), setup_provider=lambda: None, gate=gate)
    target = molecule(ASPIRIN)
    project = ProjectModel(name="p", molecules=[target])
    assert len(opened(svc, project, plan_for(target))) == 1
    assert svc.result_for(target) is None


def test_a_gate_that_raises_drops_the_plan(qapp):
    def gate(_smiles: str) -> GateDecision:
        raise RuntimeError("boom")

    svc = SynthesisPlanningService(EventBus(), setup_provider=lambda: None, gate=gate)
    target = molecule(ASPIRIN)
    project = ProjectModel(name="p", molecules=[target])
    assert len(opened(svc, project, plan_for(target))) == 1 and svc.result_for(target) is None


def test_restoring_a_plan_starts_no_planner_and_runs_no_screen(qapp):
    calls: list[str] = []

    def runner(*args, **kwargs):
        calls.append("runner")
        raise AssertionError("a restore must not start a planner")

    def annotator(route_set):
        calls.append("annotator")
        return route_set

    svc = SynthesisPlanningService(EventBus(), setup_provider=lambda: pytest.fail("a restore reads no setting"), gate=allow_all, runner=runner, annotator=annotator)
    target = molecule(ASPIRIN)
    project = ProjectModel(name="p", molecules=[target])
    opened(svc, project, plan_for(target))
    assert calls == [] and not svc.is_planning(target.uuid)


# --- what a save writes ------------------------------------------------------------------------------------------------------------------


def test_a_save_writes_the_projects_own_plans_in_the_projects_order(service):
    a, b, c = molecule(ASPIRIN, "a"), molecule("CC(=O)Nc1ccc(O)cc1", "b"), molecule("CCO", "c")
    project = ProjectModel(name="p", molecules=[a, b, c])
    stranger = molecule(ASPIRIN, "not in the project")
    service.set_project(project, reread(store_of(project, plan_for(b, "paracetamol_it100"), plan_for(a))))
    service._store_and_announce(plan_for(stranger))
    store = service.plan_store(project)
    assert [p.target.molecule_uuid for p in store.plans()] == [a.uuid, b.uuid]


def test_only_a_result_is_written(service):
    a, b, c = molecule(ASPIRIN, "a"), molecule("CC(=O)Nc1ccc(O)cc1", "b"), molecule("CCO", "c")
    project = ProjectModel(name="p", molecules=[a, b, c])
    no_route = planner_fixtures.parse("strychnine_it100")
    service._store_and_announce(plan_for(a))
    service._store_and_announce(dataclasses.replace(no_route, target=TargetIdentity(molecule_uuid=b.uuid, canonical_smiles=b.canonical_smiles, fingerprint="fp")))
    service._store_and_announce(RouteSet(status=RouteStatus.FAILED, target=TargetIdentity(molecule_uuid=c.uuid, canonical_smiles="CCO", fingerprint="fp"), planner=plan_for(a).planner, reason="r", termination=SearchTermination.FAILED))
    store = service.plan_store(project)
    assert [(p.target.molecule_uuid, p.status) for p in store.plans()] == [(a.uuid, RouteStatus.FOUND), (b.uuid, RouteStatus.NO_ROUTE)]


def test_what_a_session_makes_is_what_the_next_session_is_shown(service):
    target = molecule(ASPIRIN)
    project = ProjectModel(name="p", molecules=[target])
    service._store_and_announce(plan_for(target, screen=True))
    before = service.result_for(target).route_set
    service.set_project(project, reread(service.plan_store(project)))
    after = service.result_for(target).route_set
    assert after.status is before.status and after.routes == before.routes and after.target == before.target
    assert after.node_screenings == before.node_screenings and after.statistics == before.statistics


def test_a_plan_for_a_structure_edited_since_is_the_earlier_plan_after_the_file_too(service):
    target = molecule(ASPIRIN)
    project = ProjectModel(name="p", molecules=[target])
    opened(service, project, plan_for(target))
    ChemistryEngine().set_structure_from_smiles(target, "CC(=O)Oc1ccccc1C(=O)OC")
    bound = service.result_for(target)
    assert bound is not None and not bound.is_current and "earlier version" in bound.note
    assert [p.target.molecule_uuid for p in service.plan_store(project).plans()] == [target.uuid]


def test_a_plan_for_the_same_structure_under_another_molecule_is_not_that_molecules(service):
    target, twin = molecule(ASPIRIN, "a"), molecule(ASPIRIN, "b")
    project = ProjectModel(name="p", molecules=[target, twin])
    opened(service, project, plan_for(target))
    assert service.result_for(twin) is None


# --- the window ----------------------------------------------------------------------------------------------------------------------------


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


def _drain(qapp) -> None:
    for _ in range(20):
        qapp.processEvents()


def _project_with(window, *smiles: str) -> list[MoleculeModel]:
    engine = window._services.chemistry_engine
    project = ProjectModel(name="p")
    molecules = []
    for s in smiles:
        model = MoleculeModel(display_name=s)
        engine.set_structure_from_smiles(model, s)
        molecules.append(model)
    project.molecules.extend(molecules)
    window._set_project(project)
    return molecules


def _finish(window, qapp, plan: RouteSet) -> None:
    """What the planning service does when a search ends: store it and announce it."""
    window._services.synthesis_planning_service._store_and_announce(plan)
    _drain(qapp)


def test_a_finished_search_that_found_routes_is_an_unsaved_change(window, qapp):
    [a] = _project_with(window, ASPIRIN)
    assert not window._session.is_dirty
    _finish(window, qapp, plan_for(a))
    assert window._session.is_dirty


def test_a_search_that_found_none_is_an_unsaved_change_too(window, qapp):
    [a] = _project_with(window, ASPIRIN)
    no_route = planner_fixtures.parse("strychnine_it100")
    _finish(window, qapp, dataclasses.replace(no_route, target=TargetIdentity(molecule_uuid=a.uuid, canonical_smiles=a.canonical_smiles, fingerprint="fp")))
    assert window._session.is_dirty


@pytest.mark.parametrize("status", [RouteStatus.REFUSED, RouteStatus.FAILED, RouteStatus.UNAVAILABLE, RouteStatus.UNSCREENED])
def test_an_outcome_that_is_not_kept_leaves_the_project_as_saved(window, qapp, status):
    [a] = _project_with(window, ASPIRIN)
    base = plan_for(a)
    _finish(window, qapp, RouteSet(status=status, target=base.target, planner=base.planner, reason="r"))
    assert not window._session.is_dirty


def test_a_result_for_a_molecule_the_project_lacks_changes_nothing(window, qapp):
    _project_with(window, ASPIRIN)
    _finish(window, qapp, plan_for(molecule(ASPIRIN, "stranger")))
    assert not window._session.is_dirty


def test_a_plan_survives_the_windows_own_save_and_open(window, qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    a, b = _project_with(window, ASPIRIN, "CCO")
    _finish(window, qapp, plan_for(a, screen=True))
    path = tmp_path / "saved.ocsproj"
    window.save_project_to(path)
    assert SYNTHESIS_PLANS_KEY in json.loads(path.read_text(encoding="utf-8"))

    window._set_project(ProjectModel(name="something else"))
    assert window._services.synthesis_planning_service.result_for(a) is None
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *args, **kwargs: (str(path), "")))
    window._open_project()

    service = window._services.synthesis_planning_service
    reopened = window._session.project.find_molecule(a.uuid)
    bound = service.result_for(reopened)
    assert bound is not None and bound.is_current and bound.route_set.routes
    assert service.result_for(window._session.project.find_molecule(b.uuid)) is None


def test_the_file_of_a_project_with_no_plan_has_no_block(window, qapp, tmp_path):
    _project_with(window, ASPIRIN)
    path = tmp_path / "plain.ocsproj"
    window.save_project_to(path)
    assert SYNTHESIS_PLANS_KEY not in json.loads(path.read_text(encoding="utf-8"))


def test_accepting_the_recovery_offer_restores_the_plans(window, qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from openchem.services.recovery_service import RecoveryService

    window.enable_recovery(RecoveryService(window._services.project_service, tmp_path / "recovery"), delay_ms=0)
    [a] = _project_with(window, ASPIRIN)
    _finish(window, qapp, plan_for(a))
    _drain(qapp)

    window._set_project(ProjectModel(name="something else"))
    assert window._services.synthesis_planning_service.result_for(a) is None
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes))
    assert window.offer_recovery()
    assert window._services.synthesis_planning_service.result_for(window._session.project.find_molecule(a.uuid)) is not None


def test_the_drive_harness_reopens_a_project_with_its_plans(window, qapp, tmp_path):
    from openchem.app.debug_drive import _Driver

    [a] = _project_with(window, ASPIRIN)
    _finish(window, qapp, plan_for(a))
    path = tmp_path / "driven.ocsproj"
    driver = _Driver(window, [])
    driver._do_save_project({"path": str(path)})
    window._set_project(ProjectModel(name="something else"))
    driver._do_open_project({"path": str(path)})
    assert window._services.synthesis_planning_service.result_for(window._session.project.find_molecule(a.uuid)) is not None


def test_opening_a_file_whose_plan_is_for_a_refused_target_shows_no_plan(window, qapp, tmp_path, monkeypatch):
    """The whole path, from a file a person could have been sent to the Synthesis dock's reading surface."""
    from PySide6.QtWidgets import QFileDialog

    [a] = _project_with(window, ASPIRIN)
    path = tmp_path / "sent.ocsproj"
    window.save_project_to(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data[SYNTHESIS_PLANS_KEY] = store_of(window._session.project, refused_plan(a)).to_dict()
    path.write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *args, **kwargs: (str(path), "")))
    window._open_project()
    service = window._services.synthesis_planning_service
    assert service.result_for(window._session.project.find_molecule(a.uuid)) is None
    assert service.plan_store(window._session.project).is_empty

