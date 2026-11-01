"""Screening a stored synthesis plan again, on request (`SynthesisPlanningService.request_rescreen`).

A plan read from a project file shows the alerts it had on the day it was made, with a sentence saying the screen was not repeated; this is the action that repeats it. What is asserted: the gate speaks
first, the fresh screening replaces the old one and the sentence goes, the routes are the same routes, no planner and no setting is touched, a screen that cannot be made leaves the plan as it was, and the
molecule's one slot is held while it runs.
"""

from __future__ import annotations

import dataclasses
import threading

import pytest
from test_synthesis_plan_persistence import ASPIRIN, allow_all, opened, plan_for
from test_synthesis_planning_service import molecule

from openchem.domain.project import ProjectModel
from openchem.domain.synthesis_gate import GateDecision, GateMatch, GateOutcome, NodeScreening
from openchem.domain.synthesis_route import RouteSet, RouteStatus, SearchTermination, route_molecules
from openchem.events.base import EventBus
from openchem.events.events import SynthesisJobStateChanged, SynthesisRouteReady
from openchem.services.synthesis_planning_service import RequestOutcome, SynthesisPlanningService

TODAY = "2026-11-01"


def fresh_annotator(calls: list | None = None):
    """An annotator that screens every molecule of the plan as of TODAY, with a ruleset the old screening did not consult."""

    def annotate(plan: RouteSet) -> RouteSet:
        if calls is not None:
            calls.append(plan)
        molecules = tuple(dict.fromkeys(m for r in plan.routes for m in route_molecules(r)))
        return dataclasses.replace(plan, node_screenings=tuple(NodeScreening(smiles=m, screened=True, rulesets_consulted=("rs-2",), screened_on=TODAY) for m in molecules))

    return annotate


class Rig:
    def __init__(self, qapp, *, annotator=None, gate=allow_all):
        self.qapp = qapp
        self.bus = EventBus()
        self.ready: list[SynthesisRouteReady] = []
        self.states: list[SynthesisJobStateChanged] = []
        self.bus.subscribe(SynthesisRouteReady, self.ready.append)
        self.bus.subscribe(SynthesisJobStateChanged, self.states.append)
        self.runner_calls: list = []

        def runner(*args, **kwargs):
            self.runner_calls.append(args)
            raise AssertionError("a re-screen must not start a planner")

        self.service = SynthesisPlanningService(
            self.bus, setup_provider=lambda: pytest.fail("a re-screen reads no setting"), gate=gate, runner=runner, annotator=annotator or fresh_annotator()
        )
        self.target = molecule(ASPIRIN)
        self.project = ProjectModel(name="p", molecules=[self.target])
        opened(self.service, self.project, plan_for(self.target, screen=True))

    def drain(self) -> None:
        self.service._pool.waitForDone(30000)
        for _ in range(40):
            self.qapp.processEvents()

    def plan(self) -> RouteSet:
        return self.service.result_for(self.target).route_set


@pytest.fixture
def rig(qapp):
    built = Rig(qapp)
    yield built
    built.service.shutdown(2000)


def test_a_restored_plan_is_screened_again_and_stops_saying_it_was_not(rig):
    before = rig.plan()
    assert {s.screened_on for s in before.node_screenings} == {"2026-10-21"} and any("not repeated" in s for s in before.limitations)
    assert rig.service.request_rescreen(rig.target) is RequestOutcome.STARTED
    rig.drain()
    after = rig.plan()
    assert after.node_screenings and {s.screened_on for s in after.node_screenings} == {TODAY} and all(s.rulesets_consulted == ("rs-2",) for s in after.node_screenings)
    assert not any("was not repeated" in s for s in after.limitations) and not any(s.startswith("The regulatory screen of these routes") for s in after.limitations)
    assert after.routes == before.routes and after.target == before.target and after.status is RouteStatus.FOUND
    assert rig.runner_calls == []


def test_it_is_announced_as_a_plan_is_and_the_slot_is_free_again(rig):
    rig.service.request_rescreen(rig.target)
    rig.drain()
    assert len(rig.ready) == 1 and rig.ready[0].molecule_uuid == rig.target.uuid
    assert [s.state.name for s in rig.states] == ["QUEUED", "RUNNING", "COMPLETED"]
    assert "again" in rig.states[0].message and "again" in rig.states[1].message
    assert not rig.service.is_planning(rig.target.uuid)


def test_the_gate_speaks_first_and_a_target_it_no_longer_allows_loses_the_plan(qapp):
    def gate(_smiles: str) -> GateDecision:
        return GateDecision(outcome=GateOutcome.REFUSED, reason="r", matches=(GateMatch(ruleset_id="x", rule_id="y", display_name="z"),))

    calls: list = []
    rig = Rig(qapp, annotator=fresh_annotator(calls), gate=allow_all)
    rig.service._gate = gate  # the ruleset grew after the plan was opened
    assert rig.service.request_rescreen(rig.target) is RequestOutcome.FINISHED
    assert rig.plan().status is RouteStatus.REFUSED and not rig.plan().routes
    assert calls == [] and not rig.service.is_planning(rig.target.uuid)
    rig.service.shutdown(2000)


def test_a_gate_that_cannot_tell_is_unscreened_and_screens_nothing(qapp):
    calls: list = []
    rig = Rig(qapp, annotator=fresh_annotator(calls))
    rig.service._gate = lambda _smiles: (_ for _ in ()).throw(RuntimeError("boom"))
    assert rig.service.request_rescreen(rig.target) is RequestOutcome.FINISHED
    assert rig.plan().status is RouteStatus.UNSCREENED and calls == []
    rig.service.shutdown(2000)


def test_a_molecule_with_no_plan_is_rejected_and_publishes_nothing(qapp):
    rig = Rig(qapp)
    other = molecule("CCO", "ethanol")
    assert rig.service.request_rescreen(other) is RequestOutcome.REJECTED
    assert rig.ready == [] and rig.states == []
    rig.service.shutdown(2000)


def test_a_plan_with_no_routes_has_nothing_to_screen(qapp):
    rig = Rig(qapp)
    kept = rig.plan()
    none_found = RouteSet(status=RouteStatus.NO_ROUTE, target=kept.target, planner=kept.planner, termination=SearchTermination.COMPLETED)
    rig.service._results[rig.target.uuid] = none_found
    assert rig.service.request_rescreen(rig.target) is RequestOutcome.REJECTED
    assert rig.service.result_for(rig.target).route_set is none_found
    rig.service.shutdown(2000)


def test_a_screen_that_cannot_be_made_leaves_the_plan_and_its_sentence_as_they_were(qapp):
    def broken(_plan: RouteSet) -> RouteSet:
        raise RuntimeError("the ruleset could not be loaded")

    rig = Rig(qapp, annotator=broken)
    before = rig.plan()
    assert rig.service.request_rescreen(rig.target) is RequestOutcome.STARTED
    rig.drain()
    after = rig.plan()
    assert after == before and any("not repeated" in s for s in after.limitations) and {s.screened_on for s in after.node_screenings} == {"2026-10-21"}
    assert not rig.service.is_planning(rig.target.uuid)
    rig.service.shutdown(2000)


def test_an_annotator_that_returns_the_plan_untouched_does_not_pass_for_a_new_screening(qapp):
    rig = Rig(qapp, annotator=lambda plan: plan)
    before = rig.plan()
    rig.service.request_rescreen(rig.target)
    rig.drain()
    assert rig.plan() == before and any("not repeated" in s for s in rig.plan().limitations)
    rig.service.shutdown(2000)


def test_a_second_request_while_it_runs_is_already_running_and_the_plan_is_unchanged_until_it_ends(qapp):
    started, release = threading.Event(), threading.Event()
    inner = fresh_annotator()

    def slow(plan: RouteSet) -> RouteSet:
        started.set()
        assert release.wait(20)
        return inner(plan)

    rig = Rig(qapp, annotator=slow)
    before = rig.plan()
    assert rig.service.request_rescreen(rig.target) is RequestOutcome.STARTED
    assert started.wait(20)
    assert rig.service.is_planning(rig.target.uuid)
    assert rig.service.request_rescreen(rig.target) is RequestOutcome.ALREADY_RUNNING
    assert rig.service.request_plan(rig.target) is RequestOutcome.ALREADY_RUNNING
    assert rig.plan() == before, "the old screening stays what is shown until the new one is ready"
    release.set()
    rig.drain()
    assert {s.screened_on for s in rig.plan().node_screenings} == {TODAY}
    rig.service.shutdown(2000)


def test_a_re_screen_waiting_its_turn_can_be_cancelled_and_leaves_the_plan_as_it_was(qapp):
    started, release = threading.Event(), threading.Event()
    inner = fresh_annotator()
    seen: list[str] = []

    def annotate(plan: RouteSet) -> RouteSet:
        seen.append(plan.target.molecule_uuid)
        started.set()
        assert release.wait(20)
        return inner(plan)

    rig = Rig(qapp, annotator=annotate)
    second = molecule(ASPIRIN, "second")
    rig.project.molecules.append(second)
    other_plan = dataclasses.replace(plan_for(second, screen=True))
    rig.service._results[second.uuid] = other_plan
    assert rig.service.request_rescreen(rig.target) is RequestOutcome.STARTED
    assert started.wait(20)
    assert rig.service.request_rescreen(second) is RequestOutcome.STARTED
    assert rig.service.cancel(second.uuid) is True
    release.set()
    rig.drain()
    assert seen == [rig.target.uuid], "the cancelled one never reached the screen"
    assert rig.service.result_for(second).route_set == other_plan
    assert {s.screened_on for s in rig.plan().node_screenings} == {TODAY}
    rig.service.shutdown(2000)


def test_a_re_screened_plan_is_what_a_save_writes(rig):
    rig.service.request_rescreen(rig.target)
    rig.drain()
    store = rig.service.plan_store(rig.project)
    [written] = store.plans()
    assert {s.screened_on for s in written.node_screenings} == {TODAY}


def test_no_screen_is_made_by_the_request_itself_on_the_calling_thread(qapp):
    """The GUI thread asks and returns: the annotator runs on the pool, never inside `request_rescreen`."""
    main = threading.get_ident()
    where: list[int] = []
    inner = fresh_annotator()

    def annotate(plan: RouteSet) -> RouteSet:
        where.append(threading.get_ident())
        return inner(plan)

    rig = Rig(qapp, annotator=annotate)
    rig.service.request_rescreen(rig.target)
    rig.drain()
    assert where and all(ident != main for ident in where)
    rig.service.shutdown(2000)



def test_a_busy_molecule_is_answered_before_the_gate_is_asked(qapp):
    asked: list[str] = []

    def gate(smiles: str) -> GateDecision:
        asked.append(smiles)
        return allow_all(smiles)

    rig = Rig(qapp, gate=gate)
    asked.clear()
    assert rig.service._job_manager.try_start("synthesis", rig.target.uuid)
    assert rig.service.request_rescreen(rig.target) is RequestOutcome.ALREADY_RUNNING
    assert asked == []
    rig.service.shutdown(2000)
