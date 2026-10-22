"""The synthesis planning service (`openchem.services.synthesis_planning_service`): the gate in the one shared path with no process started for a refusal, the target captured before the worker starts, one slot per molecule, cancel and shutdown that leave no process, and a result that is never shown for a structure it was not made for.

The planner process is a stand-in script run by the REAL `run_planner` (so a real child is started, cancelled and checked gone); where a test needs to count or forbid process creation, `subprocess.Popen` in the host module is spied on."""

from __future__ import annotations

import functools
import inspect
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from openchem.chem import aizynth_planner as host
from openchem.chem import synthesis_gate as gate_module
from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.domain.synthesis_gate import GateDecision, GateOutcome
from openchem.domain.synthesis_route import RouteStatus, SearchLimits, SearchTermination
from openchem.events.base import EventBus
from openchem.events.events import SynthesisJobStateChanged, SynthesisRouteReady
from openchem.services import synthesis_planning_service as service_module
from openchem.services.job_manager import JobManager
from openchem.services.synthesis_planning_service import JOB_KIND, RequestOutcome, SynthesisPlanningService

_FIXTURES = Path(__file__).parent.parent / "benchmarks" / "synthesis" / "fixtures"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
SARIN = "CC(C)OP(C)(=O)F"
ETHANOL = "CCO"


@pytest.fixture(autouse=True)
def _fresh_gate():
    gate_module.reset_gate_engine()
    yield
    gate_module.reset_gate_engine()


def molecule(smiles: str, name: str = "target") -> MoleculeModel:
    model = MoleculeModel(display_name=name)
    ChemistryEngine().set_structure_from_smiles(model, smiles)
    return model


def fixture_document() -> dict:
    document = json.loads((_FIXTURES / "aspirin_it100.json").read_text(encoding="utf-8"))
    document["schema"] = host.RUN_SCHEMA
    document["limits"].setdefault("all_routes", False)
    return document


def setup(python: str | None = None, **kw) -> host.PlannerSetup:
    return host.PlannerSetup(
        **{"python": python or sys.executable, "config": {"expansion": {"uspto": ["m", "t"]}, "stock": {"zinc": "s"}}, "stock": "zinc", "expansion": "uspto", "filter": "uspto", "limits": SearchLimits(iteration_limit=100, time_limit_seconds=600, max_transforms=6), **kw}
    )


def stand_in(tmp_path: Path, body: str, name: str = "fake_runner.py") -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def good_child(tmp_path: Path, pid_file: Path | None = None, sleep: float = 0.0) -> Path:
    (tmp_path / "doc.json").write_text(json.dumps(fixture_document()), encoding="utf-8")
    record = f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))" if pid_file else "pass"
    return stand_in(
        tmp_path,
        f"""
        import os, sys, time
        {record}
        sys.stdin.buffer.read()
        time.sleep({sleep})
        sys.stdout.write(open({str(tmp_path / 'doc.json')!r}, encoding='utf-8').read() + chr(10))
        """,
    )


def hanging_child(tmp_path: Path, pid_file: Path, name: str = "hang.py") -> Path:
    return stand_in(tmp_path, f"import os, sys, time\nopen({str(pid_file)!r}, 'w').write(str(os.getpid()))\nsys.stdin.buffer.read()\ntime.sleep(120)\n", name)


def pid_alive(pid: int) -> bool:
    try:
        import psutil

        return psutil.pid_exists(pid)
    except ImportError:
        pass
    if os.name == "nt":
        return str(pid) in subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class Harness:
    def __init__(self, qapp, provider=None, runner=None, gate=None, job_manager=None):
        self.qapp = qapp
        self.bus = EventBus()
        self.states: list[SynthesisJobStateChanged] = []
        self.ready: list[SynthesisRouteReady] = []
        self.bus.subscribe(SynthesisJobStateChanged, self.states.append)
        self.bus.subscribe(SynthesisRouteReady, self.ready.append)
        kwargs = {"setup_provider": provider or (lambda: setup()), "job_manager": job_manager}
        if runner is not None:
            kwargs["runner"] = runner
        if gate is not None:
            kwargs["gate"] = gate
        self.service = SynthesisPlanningService(self.bus, structure_version_of=lambda uuid: 3, **kwargs)

    def drain(self, timeout_ms: int = 60000) -> None:
        self.service._pool.waitForDone(timeout_ms)
        for _ in range(60):
            self.qapp.processEvents()

    def wait_until(self, condition, seconds: float = 30.0) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.qapp.processEvents()
            if condition():
                return
            time.sleep(0.05)
        raise AssertionError("the condition never became true")


@pytest.fixture
def popen_log(monkeypatch):
    calls: list = []
    real = subprocess.Popen

    def spy(args, **kwargs):
        calls.append(args)
        return real(args, **kwargs)

    monkeypatch.setattr(host.subprocess, "Popen", spy)
    return calls


# --- the gate, in the one shared path ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("requested_by", ["the user", "the assistant"])
def test_a_schedule_1_target_is_refused_and_no_process_is_started_whoever_asked(qapp, popen_log, requested_by):
    h = Harness(qapp)  # the real service, the real gate and the real run_planner; only the planner setting is present

    outcome = h.service.request_plan(molecule(SARIN), requested_by=requested_by)
    h.drain()

    assert outcome is RequestOutcome.FINISHED and popen_log == []
    stored = h.ready[0].route_set
    assert stored.status is RouteStatus.REFUSED and "CWC Schedule 1" in stored.reason and "not a legal determination" in stored.reason
    assert stored.planner.version == service_module.NOT_STARTED and stored.routes == ()
    assert [s.state for s in h.states] == [CacheState.FAILED] and not h.service.is_planning(h.ready[0].molecule_uuid)


def test_a_broken_gate_is_unscreened_and_nothing_is_started_even_for_a_harmless_target(qapp, popen_log, monkeypatch):
    def exploding(include_user=True):
        raise OSError("disk gone")

    monkeypatch.setattr(gate_module, "load_all", exploding)
    h = Harness(qapp)

    assert h.service.request_plan(molecule(ETHANOL)) is RequestOutcome.FINISHED
    assert popen_log == [] and h.ready[0].route_set.status is RouteStatus.UNSCREENED and "could not be screened" in h.ready[0].route_set.reason


@pytest.mark.parametrize("gate", [lambda s: GateDecision(outcome=GateOutcome.UNSCREENED, reason="the target could not be screened against CWC Schedule 1: no."), lambda s: (_ for _ in ()).throw(RuntimeError("boom"))])
def test_a_gate_that_cannot_tell_or_that_raises_is_unscreened_and_the_runner_is_never_called(qapp, gate):
    calls = []
    h = Harness(qapp, gate=gate, runner=lambda *a, **k: calls.append(1))

    assert h.service.request_plan(molecule(ETHANOL)) is RequestOutcome.FINISHED
    assert calls == [] and h.ready[0].route_set.status is RouteStatus.UNSCREENED


def test_the_runner_is_called_in_one_place_after_the_gate_and_never_from_request_plan():
    request_source = inspect.getsource(SynthesisPlanningService.request_plan)
    assert request_source.index("self._decide") < request_source.index("try_start") < request_source.index("self._pool.start")
    assert "_runner" not in request_source and "run_planner" not in request_source
    source = inspect.getsource(service_module)
    assert source.count("service._runner(") == 1  # the task, and nowhere else


def test_a_mixture_is_refused_by_its_parts_before_it_is_called_a_mixture(qapp, popen_log):
    h = Harness(qapp)
    h.service.request_plan(molecule("CCO." + SARIN))
    assert h.ready[0].route_set.status is RouteStatus.REFUSED and popen_log == []


def test_a_mixture_that_is_not_regulated_is_failed_with_its_reason_and_starts_nothing(qapp, popen_log):
    h = Harness(qapp)
    h.service.request_plan(molecule("CCO.CCCO"))
    result = h.ready[0].route_set
    assert result.status is RouteStatus.FAILED and "several components" in result.reason and popen_log == []


def test_a_missing_or_unreadable_setup_is_unavailable_after_the_gate_has_spoken(qapp, popen_log):
    h = Harness(qapp, provider=lambda: None)
    h.service.request_plan(molecule(ETHANOL))
    assert h.ready[0].route_set.status is RouteStatus.UNAVAILABLE and "not set up" in h.ready[0].route_set.reason
    h.service.request_plan(molecule(SARIN))  # the gate answers before the setup is even asked about
    assert h.ready[1].route_set.status is RouteStatus.REFUSED

    def broken():
        raise PermissionError("registry")

    g = Harness(qapp, provider=broken)
    g.service.request_plan(molecule(ETHANOL))
    assert g.ready[0].route_set.status is RouteStatus.UNAVAILABLE and "could not be read (PermissionError)" in g.ready[0].route_set.reason
    assert popen_log == []


def test_a_molecule_with_no_structure_is_rejected_without_a_result(qapp):
    h = Harness(qapp)
    empty = MoleculeModel(display_name="blank")
    assert h.service.request_plan(empty) is RequestOutcome.REJECTED
    assert h.ready == [] and h.states[0].state is CacheState.FAILED and "no structure" in h.states[0].message
    assert h.service.result_for(empty) is None


def test_the_real_container_plans_nothing_until_the_planner_is_set_up_and_still_refuses_first():
    from openchem.bootstrap import build_service_container

    service = build_service_container().synthesis_planning_service
    bus_events = []
    service._event_bus.subscribe(SynthesisRouteReady, bus_events.append)
    service.request_plan(molecule(ETHANOL))
    service.request_plan(molecule(SARIN))
    assert [e.route_set.status for e in bus_events] == [RouteStatus.UNAVAILABLE, RouteStatus.REFUSED]


# --- a search, with a real child ---------------------------------------------------------------------------------------------------------


def test_a_search_is_queued_runs_and_publishes_its_routes_with_the_job_finished_first(qapp, tmp_path):
    child = good_child(tmp_path)
    jobs = JobManager()
    h = Harness(qapp, runner=functools.partial(host.run_planner, runner=child), job_manager=jobs)
    seen_active_at_ready = []
    h.bus.subscribe(SynthesisRouteReady, lambda e: seen_active_at_ready.append(jobs.is_active(JOB_KIND, e.molecule_uuid)))
    target = molecule(ASPIRIN, "aspirin")

    outcome = h.service.request_plan(target, requested_by="the assistant")
    queued_message = h.states[0].message
    h.drain()

    assert outcome is RequestOutcome.STARTED and h.states[0].state is CacheState.QUEUED and "requested by the assistant" in queued_message
    assert [s.state for s in h.states] == [CacheState.QUEUED, CacheState.RUNNING, CacheState.COMPLETED] and "Planning aspirin" in h.states[1].message
    assert len(h.ready) == 1 and h.ready[0].route_set.status is RouteStatus.FOUND and h.ready[0].route_set.routes
    assert seen_active_at_ready == [False]  # the slot is free by the time anyone hears the result
    bound = h.service.result_for(target)
    assert bound.is_current and bound.note == "" and bound.route_set is h.ready[0].route_set


def test_the_target_and_the_setup_are_captured_when_the_request_is_made(qapp, tmp_path):
    child = good_child(tmp_path, sleep=1.0)
    seen = {}

    def spy(request, target, **kw):
        seen["request"], seen["target"], seen["kw"] = request, target, kw
        return host.run_planner(request, target, runner=child, **kw)

    current = {"python": sys.executable}
    h = Harness(qapp, provider=lambda: setup(python=current["python"]), runner=spy)
    target = molecule(ASPIRIN)
    h.service.request_plan(target)
    current["python"] = "C:/somewhere/else/python.exe"  # the setting changes while it is queued or running
    target.canonical_smiles = ETHANOL  # and so does the drawing
    h.drain()

    assert seen["target"].canonical_smiles == ASPIRIN and seen["target"].fingerprint == f"{ASPIRIN}|v3" and seen["request"].target_smiles == ASPIRIN
    assert seen["kw"]["python"] == sys.executable


def test_a_plan_is_never_shown_for_a_structure_it_was_not_made_for(qapp, tmp_path):
    child = good_child(tmp_path)
    h = Harness(qapp, runner=functools.partial(host.run_planner, runner=child))
    target = molecule(ASPIRIN, "aspirin")
    h.service.request_plan(target)
    h.drain()

    # a different molecule entirely, under another uuid, gets nothing
    assert h.service.result_for(molecule(ASPIRIN, "another")) is None
    # the same molecule edited to another structure: returned, but labelled as the earlier plan
    target.canonical_smiles = ETHANOL
    bound = h.service.result_for(target)
    assert bound is not None and not bound.is_current and ASPIRIN in bound.note and "earlier version" in bound.note
    # a mass label only is the same structure
    target.canonical_smiles = "[13CH3]C(=O)Oc1ccccc1C(=O)O"
    assert h.service.result_for(target).is_current
    # a structure that cannot be read cannot be matched, so it is not current
    target.canonical_smiles = "not a structure"
    assert not h.service.result_for(target).is_current
    target.canonical_smiles = ""
    assert not h.service.result_for(target).is_current


def test_forgetting_a_plan_removes_it(qapp, tmp_path):
    h = Harness(qapp, runner=functools.partial(host.run_planner, runner=good_child(tmp_path)))
    target = molecule(ASPIRIN)
    h.service.request_plan(target)
    h.drain()
    h.service.forget(target.uuid)
    assert h.service.result_for(target) is None


def test_a_second_request_for_a_molecule_being_planned_is_refused_and_publishes_nothing(qapp, tmp_path):
    pid_file = tmp_path / "pid"
    h = Harness(qapp, runner=functools.partial(host.run_planner, runner=hanging_child(tmp_path, pid_file)))
    target = molecule(ASPIRIN)
    h.service.request_plan(target)
    before = len(h.states)

    assert h.service.request_plan(target) is RequestOutcome.ALREADY_RUNNING
    assert len(h.states) == before and h.service.is_planning(target.uuid)

    h.service.cancel(target.uuid)
    h.drain()


def test_cancelling_a_running_search_stops_the_child_and_publishes_a_cancelled_result(qapp, tmp_path):
    pid_file = tmp_path / "pid"
    jobs = JobManager()
    h = Harness(qapp, runner=functools.partial(host.run_planner, runner=hanging_child(tmp_path, pid_file)), job_manager=jobs)
    target = molecule(ASPIRIN)
    h.service.request_plan(target)
    h.wait_until(lambda: pid_file.exists() and any(s.state is CacheState.RUNNING for s in h.states))
    assert [j.kind for j in jobs.active_jobs()] == [JOB_KIND] and "Planning" in jobs.active_jobs()[0].message

    assert jobs.cancel(JOB_KIND, target.uuid) is True  # through the Jobs panel's own door
    h.drain()

    result = h.ready[0].route_set
    assert result.status is RouteStatus.CANCELLED and result.termination is SearchTermination.CANCELLED and result.routes == ()
    assert h.states[-1].state is CacheState.FAILED and not h.service.is_planning(target.uuid)
    time.sleep(0.5)
    assert not pid_alive(int(pid_file.read_text()))
    assert h.service.cancel(target.uuid) is False  # nothing left to cancel


def test_a_search_waiting_its_turn_can_be_cancelled_and_never_starts_a_process(qapp, tmp_path, popen_log):
    first_pid, second_pid = tmp_path / "pid1", tmp_path / "pid2"
    first = hanging_child(tmp_path, first_pid, "hang1.py")
    second = hanging_child(tmp_path, second_pid, "hang2.py")

    def runner(request, target, **kw):
        return host.run_planner(request, target, runner=first if target.canonical_smiles == ASPIRIN else second, **kw)

    h = Harness(qapp, runner=runner)
    a, b = molecule(ASPIRIN, "a"), molecule("CC(=O)Nc1ccc(O)cc1", "b")
    h.service.request_plan(a)
    h.wait_until(lambda: first_pid.exists())
    assert h.service.request_plan(b) is RequestOutcome.STARTED  # one thread: this one is waiting
    assert h.service.is_planning(b.uuid) and not second_pid.exists()

    h.service.cancel(b.uuid)  # while queued
    h.service.cancel(a.uuid)
    h.drain()

    by_molecule = {e.molecule_uuid: e.route_set for e in h.ready}
    assert by_molecule[b.uuid].status is RouteStatus.CANCELLED and "before it started" in by_molecule[b.uuid].reason
    assert by_molecule[a.uuid].status is RouteStatus.CANCELLED
    assert not second_pid.exists() and len(popen_log) == 1  # the queued one never launched anything


def test_shutdown_cancels_every_search_and_leaves_no_process(qapp, tmp_path):
    pid_file = tmp_path / "pid"
    h = Harness(qapp, runner=functools.partial(host.run_planner, runner=hanging_child(tmp_path, pid_file)))
    target = molecule(ASPIRIN)
    h.service.request_plan(target)
    h.wait_until(pid_file.exists)

    began = time.monotonic()
    h.service.shutdown(wait_ms=30000)

    assert time.monotonic() - began < 30
    for _ in range(40):
        qapp.processEvents()
    assert h.ready[0].route_set.status is RouteStatus.CANCELLED and not h.service.is_planning(target.uuid)
    time.sleep(0.5)
    assert not pid_alive(int(pid_file.read_text()))


def test_an_unexpected_exception_in_the_runner_is_a_failed_result_and_the_slot_is_free_again(qapp):
    calls = []

    def runner(request, target, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return host._failure(RouteStatus.FAILED, request, target, "second time")

    h = Harness(qapp, runner=runner)
    target = molecule(ASPIRIN)
    h.service.request_plan(target)
    h.drain()
    assert h.ready[0].route_set.status is RouteStatus.FAILED and "unexpectedly (RuntimeError)" in h.ready[0].route_set.reason
    assert h.service.request_plan(target) is RequestOutcome.STARTED  # not stuck "already running"
    h.drain()
    assert len(h.ready) == 2


def test_a_planner_failure_is_published_as_a_failed_state_with_its_message(qapp, tmp_path):
    child = stand_in(tmp_path, "import sys\nsys.stdin.buffer.read()\nsys.stderr.write('ImportError: pyarrow')\nsys.exit(2)\n")
    h = Harness(qapp, runner=functools.partial(host.run_planner, runner=child))
    h.service.request_plan(molecule(ASPIRIN))
    h.drain()
    assert h.ready[0].route_set.status is RouteStatus.FAILED and h.states[-1].state is CacheState.FAILED and "exited with code 2" in h.states[-1].message


def test_each_molecule_has_its_own_slot_and_its_own_result(qapp, tmp_path):
    child = good_child(tmp_path)
    h = Harness(qapp, runner=functools.partial(host.run_planner, runner=child))
    a, b = molecule(ASPIRIN, "a"), molecule("CC(=O)Nc1ccc(O)cc1", "b")
    assert h.service.request_plan(a) is RequestOutcome.STARTED and h.service.request_plan(b) is RequestOutcome.STARTED
    h.drain()
    assert {e.molecule_uuid for e in h.ready} == {a.uuid, b.uuid}
    assert h.service.result_for(a).route_set.target.molecule_uuid == a.uuid and h.service.result_for(b).route_set.target.molecule_uuid == b.uuid


def test_searches_run_one_at_a_time(qapp, tmp_path):
    running, peak = [0], [0]
    lock = threading.Lock()

    def runner(request, target, **kw):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.3)
        with lock:
            running[0] -= 1
        return host._failure(RouteStatus.FAILED, request, target, "stand-in")

    h = Harness(qapp, runner=runner)
    for name, smiles in (("a", ASPIRIN), ("b", "CC(=O)Nc1ccc(O)cc1"), ("c", "OC(=O)c1ccccc1O")):
        h.service.request_plan(molecule(smiles, name))
    h.drain()
    assert peak[0] == 1 and len(h.ready) == 3


# --- gaps the mutation check found -------------------------------------------------------------------------------------------------------


def test_a_request_for_a_molecule_being_planned_is_already_running_before_the_gate_is_even_asked(qapp, tmp_path):
    """Without the early check, a refused request would finish at once, free the slot of the search still running and overwrite its result."""
    pid_file = tmp_path / "pid"
    gate_calls = []

    def counting_gate(smiles):
        gate_calls.append(smiles)
        return gate_module.check_target(smiles)

    h = Harness(qapp, runner=functools.partial(host.run_planner, runner=hanging_child(tmp_path, pid_file)), gate=counting_gate)
    target = molecule(ASPIRIN)
    h.service.request_plan(target)
    h.wait_until(pid_file.exists)
    asked_before, published_before = len(gate_calls), len(h.states)

    target.canonical_smiles = SARIN  # edited to a regulated structure while the search runs
    assert h.service.request_plan(target) is RequestOutcome.ALREADY_RUNNING

    assert len(gate_calls) == asked_before and len(h.states) == published_before and h.ready == []
    assert h.service.is_planning(target.uuid)  # the running search still holds its slot
    h.service.cancel(target.uuid)
    h.drain()


def test_the_slot_is_free_while_the_result_is_announced_not_after(qapp):
    """Called directly on the GUI thread so the bus delivers at once and the order is observable (from the worker it is delivered later)."""
    jobs = JobManager()
    h = Harness(qapp, job_manager=jobs)
    target = molecule(ASPIRIN)
    seen = []
    h.bus.subscribe(SynthesisRouteReady, lambda e: seen.append(jobs.is_active(JOB_KIND, e.molecule_uuid)))
    h.bus.subscribe(SynthesisJobStateChanged, lambda e: seen.append(("state", jobs.is_active(JOB_KIND, e.molecule_uuid))))
    jobs.try_start(JOB_KIND, target.uuid)
    result = host._failure(RouteStatus.FAILED, host.PlanRequest(target_smiles=ASPIRIN, config={"x": 1}, stock="zinc", expansion="uspto", limits=SearchLimits(iteration_limit=1, time_limit_seconds=1, max_transforms=1)), service_module.TargetIdentity(molecule_uuid=target.uuid, canonical_smiles=ASPIRIN, fingerprint="f"), "x")

    h.service._store_and_announce(result)

    assert seen == [False, ("state", False)]


def test_a_stored_plan_filed_under_the_wrong_molecule_is_not_returned(qapp, tmp_path):
    h = Harness(qapp, runner=functools.partial(host.run_planner, runner=good_child(tmp_path)))
    a, b = molecule(ASPIRIN, "a"), molecule(ASPIRIN, "b")
    h.service.request_plan(a)
    h.drain()
    h.service._results[b.uuid] = h.service._results[a.uuid]  # a corrupted store: a's plan under b's key

    assert h.service.result_for(b) is None
