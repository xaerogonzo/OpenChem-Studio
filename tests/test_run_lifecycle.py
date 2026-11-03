"""The run ledger: a requested calculation as a state machine nothing can skip."""

from __future__ import annotations

import threading

import pytest

from openchem.domain import run_lifecycle
from openchem.domain.calculation_bridge import Route
from openchem.domain.execution_policy import AiRun, RunDecision
from openchem.domain.run_lifecycle import (
    PREVIEW_TTL_SECONDS,
    Preparation,
    PrepareResult,
    RunLedger,
    RunOutcome,
    RunState,
)


def _prep(run_id="r1", route=Route.AUTO, molecule="mol-1", created_at=0.0, **kw):
    decision = RunDecision(AiRun.AUTO) if route is Route.AUTO else RunDecision(AiRun.CONFIRM, "a person decides")
    base = dict(
        run_id=run_id, turn_id="t1", calculator_id="calc", display_name="Calc", molecule_uuid=molecule,
        molecule_name="Aspirin", project_uuid="proj", calculation_input="drawing", input_fingerprint="fp", parameters={"x": 1},
        route=route, decision=decision, created_at=created_at,
    )
    base.update(kw)
    return Preparation(**base)


def _outcome(state, run_id="r1"):
    return RunOutcome(run_id=run_id, calculator_id="calc", state=state, message="m")


@pytest.fixture
def ledger():
    return RunLedger(clock=lambda: 100.0)


# --- registering --------------------------------------------------------------------------------


def test_an_automatic_run_starts_prepared_and_one_needing_a_person_starts_previewed(ledger):
    assert ledger.register(_prep("a", Route.AUTO)) is RunState.PREPARED
    assert ledger.register(_prep("b", Route.NEEDS_APPROVAL)) is RunState.PREVIEWED


def test_the_same_run_id_cannot_be_registered_twice(ledger):
    ledger.register(_prep())
    with pytest.raises(ValueError):
        ledger.register(_prep())


def test_a_run_id_nobody_prepared_does_not_exist(ledger):
    assert ledger.get("nope") is None and ledger.state_of("nope") is None
    assert not ledger.claim_dispatch("nope") and not ledger.approve("nope") and not ledger.cancel("nope")


# --- dispatch is once, and a preview needs a person -----------------------------------------------


def test_a_run_is_dispatched_by_exactly_one_caller(ledger):
    ledger.register(_prep())
    assert ledger.claim_dispatch("r1") is True
    assert ledger.claim_dispatch("r1") is False
    assert ledger.state_of("r1") is RunState.RUNNING


def test_many_threads_claiming_one_run_start_one_calculation(ledger):
    ledger.register(_prep())
    results: list[bool] = []
    barrier = threading.Barrier(40)

    def claim():
        barrier.wait()
        results.append(ledger.claim_dispatch("r1"))

    threads = [threading.Thread(target=claim) for _ in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1 and results.count(False) == 39


def test_a_preview_cannot_be_dispatched_until_a_person_approves_it(ledger):
    ledger.register(_prep(route=Route.NEEDS_APPROVAL))
    assert ledger.claim_dispatch("r1") is False and ledger.state_of("r1") is RunState.PREVIEWED
    assert ledger.approve("r1") is True and ledger.state_of("r1") is RunState.APPROVED
    assert ledger.claim_dispatch("r1") is True


def test_approving_twice_or_approving_something_never_previewed_does_nothing(ledger):
    ledger.register(_prep("auto", Route.AUTO))
    assert ledger.approve("auto") is False
    ledger.register(_prep("gated", Route.NEEDS_APPROVAL))
    assert ledger.approve("gated") is True and ledger.approve("gated") is False


# --- cancelling, invalidating, finishing ------------------------------------------------------------


def test_cancel_stops_a_run_that_has_not_started_and_it_stays_stopped(ledger):
    ledger.register(_prep(route=Route.NEEDS_APPROVAL))
    assert ledger.cancel("r1") is True
    assert ledger.state_of("r1") is RunState.CANCELLED
    assert not ledger.approve("r1") and not ledger.claim_dispatch("r1")
    assert ledger.outcome_of("r1").state is RunState.CANCELLED


def test_a_running_run_cannot_be_cancelled_or_invalidated(ledger):
    ledger.register(_prep())
    ledger.claim_dispatch("r1")
    assert not ledger.cancel("r1") and not ledger.invalidate("r1", "changed")
    assert ledger.state_of("r1") is RunState.RUNNING


def test_a_running_job_stopped_by_a_person_ends_cancelled_but_cancel_cannot_do_it(ledger):
    """An ORCA job cancelled in its own panel is reported by the host through `finish`; `cancel` stays the decline of a run that has not started."""
    ledger.register(_prep())
    ledger.claim_dispatch("r1")
    assert ledger.cancel("r1") is False and ledger.state_of("r1") is RunState.RUNNING
    assert ledger.finish(_outcome(RunState.CANCELLED)) is True
    assert ledger.state_of("r1") is RunState.CANCELLED and ledger.outcome_of("r1").state is RunState.CANCELLED
    assert ledger.claim_dispatch("r1") is False and ledger.finish(_outcome(RunState.COMPLETED)) is False


def test_an_invalidated_preview_cannot_be_approved(ledger):
    ledger.register(_prep(route=Route.NEEDS_APPROVAL))
    assert ledger.invalidate("r1", "the structure changed") is True
    assert not ledger.approve("r1") and not ledger.claim_dispatch("r1")
    assert ledger.outcome_of("r1").message == "the structure changed"


def test_invalidate_for_voids_only_that_molecules_unstarted_runs(ledger):
    ledger.register(_prep("a", Route.AUTO, molecule="m1"))
    ledger.register(_prep("b", Route.NEEDS_APPROVAL, molecule="m1"))
    ledger.register(_prep("c", Route.AUTO, molecule="m2"))
    ledger.register(_prep("d", Route.AUTO, molecule="m1"))
    ledger.claim_dispatch("d")
    assert ledger.invalidate_for("m1", "edited") == 2
    assert [ledger.state_of(r) for r in "abcd"] == [
        RunState.INVALIDATED, RunState.INVALIDATED, RunState.PREPARED, RunState.RUNNING,
    ]


def test_only_a_running_run_can_finish_and_only_into_a_final_state(ledger):
    ledger.register(_prep())
    assert ledger.finish(_outcome(RunState.COMPLETED)) is False  # not running yet
    ledger.claim_dispatch("r1")
    with pytest.raises(ValueError):
        ledger.finish(_outcome(RunState.INVALIDATED))
    with pytest.raises(ValueError):
        ledger.finish(_outcome(RunState.TIMED_OUT))
    assert ledger.finish(_outcome(RunState.COMPLETED)) is True
    assert ledger.state_of("r1") is RunState.COMPLETED
    assert ledger.finish(_outcome(RunState.FAILED)) is False  # terminal is final
    assert ledger.outcome_of("r1").state is RunState.COMPLETED


@pytest.mark.parametrize("final", [RunState.COMPLETED, RunState.REFUSED, RunState.FAILED, RunState.CANCELLED])
def test_each_way_a_run_can_end_is_recorded(ledger, final):
    ledger.register(_prep())
    ledger.claim_dispatch("r1")
    ledger.finish(_outcome(final))
    assert ledger.state_of("r1") is final and ledger.outcome_of("r1").state is final


def test_a_finished_run_cannot_be_dispatched_again(ledger):
    ledger.register(_prep())
    ledger.claim_dispatch("r1")
    ledger.finish(_outcome(RunState.COMPLETED))
    assert ledger.claim_dispatch("r1") is False


# --- time ---------------------------------------------------------------------------------------


def test_a_preview_nobody_answered_is_withdrawn_instead_of_approved():
    ledger = RunLedger(clock=lambda: PREVIEW_TTL_SECONDS + 5.0)
    ledger.register(_prep(route=Route.NEEDS_APPROVAL, created_at=0.0))
    assert ledger.approve("r1") is False
    assert ledger.state_of("r1") is RunState.INVALIDATED
    assert "not answered in time" in ledger.outcome_of("r1").message


def test_a_preview_just_inside_its_time_can_still_be_approved():
    ledger = RunLedger(clock=lambda: PREVIEW_TTL_SECONDS - 1.0)
    ledger.register(_prep(route=Route.NEEDS_APPROVAL, created_at=0.0))
    assert ledger.approve("r1") is True


# --- reading ------------------------------------------------------------------------------------


def test_pending_lists_previews_awaiting_a_person_oldest_first(ledger):
    ledger.register(_prep("auto", Route.AUTO))
    ledger.register(_prep("first", Route.NEEDS_APPROVAL))
    ledger.register(_prep("second", Route.NEEDS_APPROVAL))
    ledger.approve("first")
    ledger.register(_prep("third", Route.NEEDS_APPROVAL))
    assert [p.run_id for p in ledger.pending()] == ["second", "third"]


def test_only_a_completed_run_carries_a_number():
    stored = object()
    assert RunOutcome("r", "c", RunState.COMPLETED, stored=stored).has_number is True
    assert RunOutcome("r", "c", RunState.COMPLETED).has_number is False
    for state in (RunState.REFUSED, RunState.FAILED, RunState.TIMED_OUT, RunState.CANCELLED, RunState.INVALIDATED):
        assert RunOutcome("r", "c", state, stored=stored).has_number is False


def test_the_oldest_finished_runs_are_forgotten_past_the_limit(monkeypatch):
    monkeypatch.setattr(run_lifecycle, "MAX_FINISHED_RUNS", 3)
    ledger = RunLedger(clock=lambda: 100.0)
    for i in range(5):
        ledger.register(_prep(f"r{i}"))
        ledger.claim_dispatch(f"r{i}")
        ledger.finish(_outcome(RunState.COMPLETED, f"r{i}"))
    assert ledger.get("r0") is None and ledger.get("r1") is None
    assert ledger.get("r2") is not None and ledger.get("r4") is not None


def test_a_running_or_pending_run_is_never_forgotten_to_make_room(monkeypatch):
    monkeypatch.setattr(run_lifecycle, "MAX_FINISHED_RUNS", 1)
    ledger = RunLedger(clock=lambda: 100.0)
    ledger.register(_prep("pending", Route.NEEDS_APPROVAL))
    for i in range(4):
        ledger.register(_prep(f"r{i}"))
        ledger.claim_dispatch(f"r{i}")
        ledger.finish(_outcome(RunState.COMPLETED, f"r{i}"))
    assert ledger.state_of("pending") is RunState.PREVIEWED


def test_a_preparation_and_a_prepare_result_are_json_plain():
    import json

    prep = _prep(route=Route.NEEDS_APPROVAL)
    json.dumps(prep.to_dict())
    assert prep.to_dict()["needs_approval"] is True
    assert PrepareResult(preparation=prep).ok and not PrepareResult().ok
    json.dumps(PrepareResult().to_dict())
