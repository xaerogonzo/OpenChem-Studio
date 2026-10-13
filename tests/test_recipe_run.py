"""A recipe run: its record, its store, its file envelope, and the staleness read off it (`RECIPES_DESIGN.md` 3, 6, 7).

No Qt and no ORCA. The runs here are built from real `RecipeRun` objects and written through real JSON, so what
is tested is what a project file holds and gives back.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace

import pytest

from openchem.domain.recipe_run import (
    ENVELOPE_VERSION,
    Assessment,
    BindingRecord,
    BindingState,
    Evidence,
    ProjectView,
    RecipeRun,
    RecipeRunStatus,
    RecipeRunStore,
    SlotInput,
    StaleCause,
    StepRecord,
    StepState,
    assess,
    classify,
    has_gaps,
)
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis

PROJECT = "project-1"


def _evidence(molecule: str = "mol-a", run_id: str = "qc-1", value: float = -10.17, **kw) -> Evidence:
    base = dict(
        molecule_uuid=molecule, run_id=run_id, descriptor_id="orca.homo_energy", value=value, unit="eV",
        calc_type="sp", method_basis="B3LYP def2-SVP", charge=0, multiplicity=1, input_fingerprint="fp-1",
    )
    base.update(kw)
    return Evidence(**base)


def _report() -> ReportResult:
    return ReportResult(
        molecule_uuid="mol-a", report_id="probe_pair", name="Probe pair",
        facts=(Fact(
            category=FactCategory.STRUCTURE, label="Frontier gap", value=8.13, display_value="8.13", source="probe",
            basis=Basis.HEURISTIC, units="eV", evidence=("run qc-1", "run qc-2"),
        ),),
    )


def _clean_steps() -> tuple[StepRecord, ...]:
    return (StepRecord("compare", StepState.COMPLETED),)


def _bound(target: str = "first_homo", **kw) -> BindingRecord:
    return BindingRecord("compare", target, BindingState.BOUND, evidence=_evidence(**kw))


def _run(**kw) -> RecipeRun:
    base = dict(
        run_id="run-1", recipe_id="probe_pair", recipe_version="1", status=RecipeRunStatus.COMPLETED,
        inputs=(SlotInput("first", "mol-a", "key-a", "draw-a"), SlotInput("second", "mol-b", "key-b", "draw-b")),
        parameters=(("method_basis", "B3LYP def2-SVP"), ("role", "auto")),
        steps=_clean_steps(),
        bindings=(_bound("first_homo", molecule="mol-a", run_id="qc-1"), _bound("second_homo", molecule="mol-b", run_id="qc-2")),
        result=_report(), created_at=100.0,
    )
    base.update(kw)
    return RecipeRun(**base)


def _through_a_file(store: RecipeRunStore, project: str = PROJECT) -> RecipeRunStore:
    """What a save and a reopen do to it: text on disk, parsed back."""
    return RecipeRunStore.from_dict(json.loads(json.dumps(store.to_dict())), project)


def _store(*runs: RecipeRun) -> RecipeRunStore:
    store = RecipeRunStore(PROJECT)
    for run in runs:
        store.record(run)
    return store


# --- what blocks what ------------------------------------------------------------------------------------


@pytest.mark.parametrize("state", list(BindingState))
def test_a_required_binding_blocks_in_every_state_but_bound(state):
    assert state.blocks(optional=False) is (state is not BindingState.BOUND)


@pytest.mark.parametrize("state", list(BindingState))
def test_an_optional_binding_never_blocks_but_keeps_its_state(state):
    """The step runs with `None` for it; the state is what says why, and it is recorded either way."""
    assert state.blocks(optional=True) is False


def test_there_are_exactly_eight_binding_states():
    assert {s.value for s in BindingState} == {
        "bound", "missing", "refused", "failed", "stale", "unverifiable", "incompatible", "ambiguous",
    }


# --- a run with gaps is never complete -------------------------------------------------------------------


def test_a_clean_run_is_completed():
    assert classify(_clean_steps(), (_bound(),)) is RecipeRunStatus.COMPLETED


@pytest.mark.parametrize("state", [s for s in BindingState if s is not BindingState.BOUND])
def test_a_binding_that_is_not_bound_makes_a_finished_run_partial(state):
    bindings = (_bound(), BindingRecord("compare", "second_homo", state, reason="why"))
    assert has_gaps(_clean_steps(), bindings)
    assert classify(_clean_steps(), bindings) is RecipeRunStatus.PARTIAL


def test_an_unfinished_step_makes_a_run_partial_and_a_skipped_one_does_not():
    steps = (StepRecord("a", StepState.COMPLETED), StepRecord("b", StepState.REFUSED, "no ORCA", "needs_setup"))
    assert classify(steps, ()) is RecipeRunStatus.PARTIAL
    skipped = (StepRecord("a", StepState.COMPLETED), StepRecord("b", StepState.SKIPPED))
    assert classify(skipped, ()) is RecipeRunStatus.COMPLETED


def test_a_run_where_nothing_finished_is_blocked_or_failed():
    assert classify((StepRecord("a", StepState.BLOCKED),), ()) is RecipeRunStatus.BLOCKED
    assert classify((StepRecord("a", StepState.REFUSED),), ()) is RecipeRunStatus.BLOCKED
    assert classify((StepRecord("a", StepState.FAILED, "broke"),), ()) is RecipeRunStatus.FAILED


def test_a_run_cannot_be_built_completed_with_a_gap():
    """The headline rule: partial is never presented as complete."""
    gap = BindingRecord("compare", "second_homo", BindingState.MISSING, reason="no delta-SCF run")
    with pytest.raises(ValueError, match="partial, not completed"):
        _run(bindings=(_bound(), gap))
    with pytest.raises(ValueError, match="partial, not completed"):
        _run(steps=(StepRecord("a", StepState.COMPLETED), StepRecord("b", StepState.FAILED, "broke")))
    _run(bindings=(_bound(), gap), status=RecipeRunStatus.PARTIAL)  # the same facts, honestly labelled


def test_a_partial_run_must_have_finished_something():
    with pytest.raises(ValueError, match="blocked or failed, not partial"):
        _run(status=RecipeRunStatus.PARTIAL, steps=(StepRecord("a", StepState.BLOCKED),),
             bindings=(BindingRecord("a", "x", BindingState.MISSING),), result=None)


# --- the file --------------------------------------------------------------------------------------------


def _partial() -> RecipeRun:
    return _run(
        run_id="run-partial", status=RecipeRunStatus.PARTIAL,
        steps=(StepRecord("compare", StepState.COMPLETED), StepRecord("hsab", StepState.REFUSED, "no hardness run", "needs_input")),
        bindings=(
            _bound(),
            BindingRecord("compare", "second_hardness", BindingState.AMBIGUOUS, "two earlier geometries; pick one",
                          candidates=("qc-7", "qc-9")),
            BindingRecord("compare", "first_hardness", BindingState.INCOMPATIBLE, "B3LYP def2-SVP against HF STO-3G"),
        ),
    )


@pytest.mark.parametrize(
    "run",
    [
        _run(),
        _partial(),
        _run(run_id="r3", status=RecipeRunStatus.BLOCKED, steps=(StepRecord("s", StepState.BLOCKED, "no ORCA", "needs_setup"),),
             bindings=(BindingRecord("s", "molecule", BindingState.STALE, "edited"),), result=None),
        _run(run_id="r4", status=RecipeRunStatus.FAILED, steps=(StepRecord("s", StepState.FAILED, "broke"),),
             bindings=(), result=None),
        _run(run_id="r5", status=RecipeRunStatus.CANCELLED, steps=(StepRecord("s", StepState.PENDING),),
             bindings=(), result=None),
    ],
    ids=["completed", "partial", "blocked", "failed", "cancelled"],
)
def test_a_run_survives_the_file_unchanged(run):
    [loaded] = _through_a_file(_store(run)).all_runs()
    assert loaded == run


def test_the_evidence_is_kept_as_copied_numbers_with_where_they_came_from():
    [loaded] = _through_a_file(_store(_run())).all_runs()
    first = loaded.evidence()[0]
    assert (first.value, first.unit, first.run_id, first.method_basis, first.calc_type) == (
        -10.17, "eV", "qc-1", "B3LYP def2-SVP", "sp")
    assert (first.charge, first.multiplicity, first.input_fingerprint, first.solvent) == (0, 1, "fp-1", "")


def test_the_result_is_the_real_report_through_the_result_codec():
    report = _report()
    [loaded] = _through_a_file(_store(_run(result=report))).all_runs()
    assert isinstance(loaded.result, ReportResult) and loaded.result == report


def test_a_run_in_flight_is_not_written():
    store = _store()
    store.record(RecipeRun("live", "probe_pair", "1", RecipeRunStatus.RUNNING))
    assert store.get("live") is None and store.to_dict()["runs"] == []


def test_a_running_entry_in_a_file_is_dropped_on_load_and_reported():
    data = _store(_run()).to_dict()
    data["runs"][0]["status"] = "running"
    assert RecipeRun.from_dict(json.loads(json.dumps(data["runs"][0]))) is None
    loaded = _through_a_file_data(data)
    assert loaded.all_runs() == []
    assert len(loaded.load_problems) == 1, "dropped, and said so; not dropped by the store in silence"


def _through_a_file_data(data: dict, project: str = PROJECT) -> RecipeRunStore:
    return RecipeRunStore.from_dict(json.loads(json.dumps(data)), project)


def test_a_damaged_run_is_skipped_without_breaking_the_others_and_is_reported(caplog):
    data = _store(_run(run_id="good"), _run(run_id="bad")).to_dict()
    bad = next(r for r in data["runs"] if r["run_id"] == "bad")
    bad["bindings"][0]["state"] = "no_such_state"
    with caplog.at_level(logging.WARNING, logger="openchem.recipe_run"):
        loaded = _through_a_file_data(data)
    assert [r.run_id for r in loaded.all_runs()] == ["good"]
    assert any("could not be read" in p for p in loaded.load_problems), "nothing may be dropped silently"
    assert any("Unreadable saved recipe run" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    "damage",
    [
        lambda r: r.pop("recipe_id"),
        lambda r: r.update(status="finished"),
        lambda r: r.update(result={"__type__": "report.NoSuchClass", "__version__": 1}),
        lambda r: r["bindings"][0]["evidence"].pop("value"),
        lambda r: r.update(inputs=[{"slot": "first"}]),
    ],
    ids=["no recipe id", "unknown status", "unknown result type", "evidence missing a number", "input missing a molecule"],
)
def test_each_kind_of_damage_costs_that_run_only(damage):
    data = _store(_run(run_id="good"), _run(run_id="bad")).to_dict()
    damage(next(r for r in data["runs"] if r["run_id"] == "bad"))
    loaded = _through_a_file_data(data)
    assert [r.run_id for r in loaded.all_runs()] == ["good"]
    assert len(loaded.load_problems) == 1


def test_a_completed_run_saved_with_a_gap_is_refused_on_load():
    """A file edited by hand, or written by a build with a bug, cannot smuggle in a complete-looking partial."""
    data = _store(_run()).to_dict()
    data["runs"][0]["bindings"][0]["state"] = "missing"
    loaded = _through_a_file_data(data)
    assert loaded.all_runs() == [] and len(loaded.load_problems) == 1


def test_a_newer_envelope_is_ignored_with_a_warning_not_misread(caplog):
    data = _store(_run()).to_dict()
    data["envelope_version"] = ENVELOPE_VERSION + 1
    with caplog.at_level(logging.WARNING, logger="openchem.recipe_run"):
        loaded = _through_a_file_data(data)
    assert loaded.all_runs() == []
    assert loaded.load_problems and "envelope" in loaded.load_problems[0]
    assert any("envelope" in r.getMessage() for r in caplog.records)


def test_another_projects_block_is_ignored():
    loaded = _through_a_file(_store(_run()), project="some-other-project")
    assert loaded.all_runs() == [] and loaded.load_problems


@pytest.mark.parametrize("data", [None, {}])
def test_no_block_is_an_empty_store_and_not_a_problem(data):
    store = RecipeRunStore.from_dict(data, PROJECT)
    assert store.all_runs() == [] and store.load_problems == []


def test_the_envelope_carries_its_version_and_project():
    data = _store(_run()).to_dict()
    assert data["envelope_version"] == ENVELOPE_VERSION and data["project_uuid"] == PROJECT


def test_staleness_is_never_written_to_the_file():
    """Derived at read. A stored flag would rot, and this pins that there is none to rot."""
    text = json.dumps(_store(_run(), _partial()).to_dict()).lower()
    assert "stale\"" not in text.replace('"state": "stale"', "") and "is_stale" not in text and "causes" not in text


# --- the store -------------------------------------------------------------------------------------------


def test_runs_come_back_newest_first_and_by_molecule_and_recipe():
    older = _run(run_id="old", created_at=1.0)
    newer = _run(run_id="new", created_at=2.0)
    other = _run(run_id="other", recipe_id="another", created_at=3.0,
                 inputs=(SlotInput("only", "mol-z", "key-z"),))
    store = _store(older, newer, other)
    assert [r.run_id for r in store.all_runs()] == ["other", "new", "old"]
    assert [r.run_id for r in store.runs_for_molecule("mol-b")] == ["new", "old"], "any slot counts"
    assert [r.run_id for r in store.runs_for_molecule("mol-z")] == ["other"]
    assert [r.run_id for r in store.runs_of("probe_pair")] == ["new", "old"]


def test_a_run_can_be_deleted_once():
    store = _store(_run())
    assert store.delete("run-1") is True and store.delete("run-1") is False and store.get("run-1") is None


def test_recording_the_same_run_id_replaces_it():
    store = _store(_run())
    store.record(replace(_run(), created_at=500.0))
    assert [r.created_at for r in store.all_runs()] == [500.0]


# --- staleness, derived at read ----------------------------------------------------------------------------


def _view(**kw) -> ProjectView:
    base = dict(
        constitution_keys={"mol-a": "key-a", "mol-b": "key-b"},
        qc_run_ids={"qc-1", "qc-2"},
        recipe_versions={"probe_pair": {"1"}},
    )
    base.update(kw)
    return ProjectView(**base)


def test_a_run_over_an_unchanged_project_is_not_stale():
    assert assess(_run(), _view()) == Assessment()
    assert not assess(_run(), _view()).stale and assess(_run(), _view()).can_reevaluate


def test_an_edited_structure_makes_the_run_stale_and_says_which_slot():
    result = assess(_run(), _view(constitution_keys={"mol-a": "key-a", "mol-b": "CHANGED"}))
    assert result.causes == (StaleCause.STRUCTURE_EDITED,)
    assert "second" in result.details[0] and "first" not in result.details[0]


def test_editing_a_structure_and_undoing_it_makes_the_same_run_current_again():
    """Because staleness is read, not stored: the record never changed, so there is nothing to put back."""
    run = _run()
    edited = assess(run, _view(constitution_keys={"mol-a": "other", "mol-b": "key-b"}))
    undone = assess(run, _view())
    assert edited.stale and not undone.stale


def test_a_molecule_removed_from_the_project_is_its_own_cause():
    result = assess(_run(), _view(constitution_keys={"mol-a": "key-a"}))
    assert result.causes == (StaleCause.MOLECULE_REMOVED,)
    assert "mol-b" in result.details[0]


def test_a_deleted_quantum_chemistry_run_makes_the_answer_stale_and_the_numbers_stay():
    run = _run()
    result = assess(run, _view(qc_run_ids={"qc-1"}))
    assert result.causes == (StaleCause.EVIDENCE_REMOVED,) and "qc-2" in result.details[0]
    assert [e.value for e in run.evidence()] == [-10.17, -10.17], "the recorded numbers are on the run, not looked up"


def test_a_missing_constitution_key_is_unverifiable_never_unchanged_and_never_stale():
    no_record = _run(inputs=(SlotInput("first", "mol-a", "", "draw-a"), SlotInput("second", "mol-b", "key-b")))
    assert assess(no_record, _view()) == Assessment(unverifiable_slots=("first",))
    assert assess(_run(), _view(constitution_keys={"mol-a": None, "mol-b": "key-b"})).unverifiable_slots == ("first",)
    assert not assess(no_record, _view()).stale


def test_a_recipe_version_this_build_does_not_have_is_stale_and_cannot_be_reevaluated():
    for versions in ({"probe_pair": {"2"}}, {}, {"probe_pair": set()}):
        result = assess(_run(), _view(recipe_versions=versions))
        assert result.causes == (StaleCause.RECIPE_VERSION_UNKNOWN,), versions
        assert not result.can_reevaluate


def test_every_cause_is_reported_in_a_fixed_order_not_just_the_first():
    result = assess(
        _run(),
        _view(constitution_keys={"mol-a": "x"}, qc_run_ids=set(), recipe_versions={"probe_pair": {"9"}}),
    )
    assert result.causes == (
        StaleCause.RECIPE_VERSION_UNKNOWN, StaleCause.STRUCTURE_EDITED, StaleCause.MOLECULE_REMOVED,
        StaleCause.EVIDENCE_REMOVED,
    )
    assert len(result.details) == 4


def test_a_newer_compatible_run_is_not_staleness():
    """It is an offer, made elsewhere. A project that has gained runs is a project the old answer still describes."""
    assert not assess(_run(), _view(qc_run_ids={"qc-1", "qc-2", "qc-3", "qc-4"})).stale


def test_a_bound_binding_with_no_run_id_is_not_looked_up():
    """Evidence with no quantum-chemistry run behind it (none was needed) cannot be 'removed'."""
    run = _run(bindings=(BindingRecord("compare", "x", BindingState.BOUND, evidence=_evidence(run_id="")),))
    assert not assess(run, _view(qc_run_ids=set())).stale
