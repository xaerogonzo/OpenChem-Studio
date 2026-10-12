"""The window's side of the calculator bridge: a model's request becomes a run, once, and only as allowed.

Most tests replace the service's thread pool with one that holds each task until the test runs it, so
the order of events is chosen rather than raced -- the technique `tests/test_input_snapshot.py` uses.
Two tests use the real pool, because "it works with the deterministic pool" is exactly what a
threading bug hides behind.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
from PySide6.QtCore import QThread

from openchem.app.calculation_host import CalculationHost
from openchem.app.session import SessionManager
from openchem.bootstrap import build_service_container
from openchem.chem.conformer_providers import RDKitConformerProvider
from openchem.domain.calculation_bridge import ProblemCode, Route
from openchem.domain.calculator import (
    GEOMETRY,
    CalculationRefusal,
    CalculatorDefinition,
    CalculatorScope,
    ComponentSelection,
    Aggregation,
    RegistryExecution,
)
from openchem.domain.conformer import ConformerModel
from openchem.domain.execution_policy import AiRun, ExecutionPolicy, ResourceClass
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.refusal_kinds import INPUT_REQUIRED
from openchem.domain.run_lifecycle import RunState
from openchem.domain.scientific_result import PerAtomDataset

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
ETHANOL = "CCO"


class _HeldPool:
    """Keeps every queued task until the test decides it may run."""

    def __init__(self) -> None:
        self.tasks: list = []

    def start(self, task) -> None:
        self.tasks.append(task)

    def run_all(self) -> None:
        tasks, self.tasks = self.tasks, []
        for task in tasks:
            task.run()


def _pump(qapp, predicate, seconds=5.0):
    """Process the GUI thread's events until `predicate()` holds."""
    deadline = time.monotonic() + seconds
    while not predicate():
        qapp.processEvents()
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for the GUI thread to do its part")
        time.sleep(0.002)


class _World:
    def __init__(self, qapp, held: bool = True) -> None:
        self.qapp = qapp
        self.services = build_service_container()
        self.engine = self.services.chemistry_engine
        self.project = ProjectModel(name="P")
        self.session = SessionManager()
        self.session.set_project(self.project)
        self.services.result_store_service.set_project(self.project)
        self.pool = _HeldPool() if held else None
        if held:
            self.services.descriptor_service._pool = self.pool
        self.host = CalculationHost(self.services, self.session)
        self.outcomes: list = []
        self.host.finished.connect(self.outcomes.append)
        self.molecule = self.add(ASPIRIN, "Aspirin")

    def add(self, smiles: str | None, name: str, *, select: bool = True) -> MoleculeModel:
        model = MoleculeModel(display_name=name)
        if smiles is not None:
            self.engine.set_structure_from_smiles(model, smiles)
        self.project.molecules.append(model)
        if select:
            self.session.select_molecule(model.uuid)
        return model

    def add_conformer(self, model: MoleculeModel) -> None:
        mol = self.engine.mol_from_model(model)
        conformer_mol, _energy = RDKitConformerProvider(random_seed=1).generate_conformers(mol, num_conformers=1, optimize=False)[0]
        model.conformers.append(ConformerModel(conformer_id="c1", molblock=self.engine.mol_to_molblock(conformer_mol), timestamp=0.0))

    def register(self, calculator_id, compute, policy=None, parameters=()):
        self.services.calculator_registry.register(CalculatorDefinition(
            calculator_id=calculator_id, display_name=calculator_id.title(), category="charge", description="a test calculator",
            execution=RegistryExecution(compute=compute), parameters=list(parameters),
            scope=CalculatorScope(ComponentSelection.WHOLE_STRUCTURE, Aggregation.SCALAR),
            execution_policy=policy or ExecutionPolicy(ResourceClass.INSTANT, AiRun.AUTO, measured="a test"),
        ))

    def run_in_worker(self, turn, run_id, **kw):
        """Call `host.run` from a worker thread while this thread serves the GUI thread's events."""
        box: dict = {}
        thread = threading.Thread(target=lambda: box.update(outcome=self.host.run(turn, run_id, **kw)), daemon=True)
        thread.start()
        return thread, box

    def finish(self, thread, box, *, run_pool=True):
        if run_pool:
            _pump(self.qapp, lambda: self.pool.tasks)
            self.pool.run_all()
        _pump(self.qapp, lambda: not thread.is_alive())
        return box["outcome"]


@pytest.fixture
def world(qapp):
    return _World(qapp)


def _fake_ok(mol, molecule_uuid, params):
    return PerAtomDataset(property_id="fake_ok", name="Fake", units="", method="test", molecule_uuid=molecule_uuid, values={0: 1.5})


# --- begin_turn -----------------------------------------------------------------------------------


def test_a_turn_captures_the_selected_molecule_and_its_identity(world):
    turn = world.host.begin_turn()
    assert turn.molecule_uuid == world.molecule.uuid and turn.display_name == "Aspirin"
    assert turn.heavy_atoms == 13 and turn.has_structure and turn.project_uuid == world.project.uuid
    assert turn.fingerprints["drawing"] and turn.entries == ()


def test_no_project_or_nothing_selected_is_no_turn(qapp):
    services = build_service_container()
    session = SessionManager()
    host = CalculationHost(services, session)
    assert host.begin_turn() is None
    session.set_project(ProjectModel())
    assert host.begin_turn() is None


def test_a_molecule_nobody_has_drawn_yet_still_gets_a_turn_and_nothing_can_be_prepared_for_it(world):
    world.add(None, "Blank")
    turn = world.host.begin_turn()
    assert not turn.has_structure and turn.heavy_atoms == 0
    result = world.host.prepare(turn, "polar_surface_area", {})
    assert [p.code for p in result.problems] == [ProblemCode.NO_STRUCTURE]


def test_begin_turn_refuses_to_run_off_the_gui_thread(world):
    box: dict = {}

    def attempt():
        try:
            world.host.begin_turn()
        except RuntimeError as error:
            box["error"] = str(error)

    thread = threading.Thread(target=attempt)
    thread.start()
    thread.join()
    assert "GUI thread" in box["error"]


def test_selecting_another_molecule_after_the_turn_began_changes_nothing_about_the_turn(world):
    turn = world.host.begin_turn()
    ethanol = world.add(ETHANOL, "Ethanol")  # selects it
    assert world.session.selected_molecule_uuid == ethanol.uuid
    prepared = world.host.prepare(turn, "polar_surface_area", {})
    assert prepared.preparation.molecule_uuid == world.molecule.uuid and prepared.preparation.molecule_name == "Aspirin"


# --- catalog and describe ---------------------------------------------------------------------------


def test_the_catalog_finds_calculators_by_the_words_a_person_would_type(world):
    ids = [card.calculator_id for card in world.host.catalog("lewis adduct")]
    assert "lewis_adduct" in ids
    assert len(world.host.catalog("", limit=5)) == 5
    assert world.host.catalog("zzzzzzzz") == ()


def test_describe_says_what_this_route_can_do_with_a_calculator(world):
    assert world.host.describe("orca.sp").route is Route.PREVIEW_ONLY
    assert world.host.describe("alignment_3d").route is Route.NEEDS_APPROVAL
    assert world.host.describe("polar_surface_area").route is Route.AUTO
    assert world.host.describe("not_a_calculator") is None


# --- prepare ----------------------------------------------------------------------------------------


def _problems(result):
    return [p.code for p in result.problems]


def test_prepare_refuses_an_unknown_calculator_and_a_service_run_one(world):
    turn = world.host.begin_turn()
    assert _problems(world.host.prepare(turn, "nope", {})) == [ProblemCode.UNKNOWN_CALCULATOR]
    assert _problems(world.host.prepare(turn, "orca.sp", {})) == [ProblemCode.SERVICE_RUN]


def test_prepare_reports_every_parameter_problem_at_once_and_starts_nothing(world):
    turn = world.host.begin_turn()
    result = world.host.prepare(turn, "geometry_analysis", {"conformer_policy": "lowest_energy", "colour": 1})
    assert set(_problems(result)) == {ProblemCode.NOT_A_CHOICE, ProblemCode.UNKNOWN_PARAMETER}
    assert world.host.pending() == () and world.pool.tasks == []


def test_prepare_says_what_a_calculator_needs(world):
    result = world.host.prepare(world.host.begin_turn(), "lewis_adduct", {})
    assert _problems(result) == [ProblemCode.NEEDS_INPUT] and result.problems[0].parameter == "partner_smiles"


def test_a_partner_smiles_that_does_not_parse_is_refused(world):
    result = world.host.prepare(world.host.begin_turn(), "lewis_adduct", {"partner_smiles": "C(("})
    assert _problems(result) == [ProblemCode.INVALID_STRUCTURE]


def _geometry_calculator(world):
    """A registry calculator that reads 3D coordinates and has nothing required."""
    return next(
        d for d in world.services.calculator_registry.definitions()
        if d.calculation_input == GEOMETRY and isinstance(d.execution, RegistryExecution)
        and not any(p.required for p in d.parameters)
    )


def test_a_calculator_that_needs_a_conformer_prepares_and_then_refuses_in_its_own_words(world):
    # GEOMETRY means "prefer real 3D coordinates", so the bridge does not second-guess it: the
    # calculator that needs one declines, as it would for a person, and that refusal is recorded.
    geometry = _geometry_calculator(world)
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, geometry.calculator_id, {}).preparation
    thread, box = world.run_in_worker(turn, prep.run_id)
    outcome = world.finish(thread, box)
    assert outcome.state in (RunState.REFUSED, RunState.FAILED) and not outcome.has_number
    assert outcome.message and outcome.stored is not None


def test_a_calculator_that_reads_geometry_prepares_once_there_is_a_conformer(world):
    world.add_conformer(world.molecule)
    geometry = _geometry_calculator(world)
    result = world.host.prepare(world.host.begin_turn(), geometry.calculator_id, {})
    assert result.ok and result.preparation.calculation_input == GEOMETRY


def test_an_automatic_request_is_prepared_with_the_dialogs_parameters_and_registered(world):
    result = world.host.prepare(world.host.begin_turn(), "polar_surface_area", {"pH": 7})
    prep = result.preparation
    assert prep.route is Route.AUTO and world.host.state_of(prep.run_id) is RunState.PREPARED
    assert dict(prep.parameters) == {"pH": 7.0}
    assert world.pool.tasks == [], "prepare must start nothing"
    assert any("Aspirin" in line for line in prep.preview)


def test_each_prepare_makes_its_own_run_id(world):
    turn = world.host.begin_turn()
    a = world.host.prepare(turn, "polar_surface_area", {}).preparation
    b = world.host.prepare(turn, "polar_surface_area", {}).preparation
    assert a.run_id != b.run_id


def test_a_slow_calculator_is_prepared_as_a_preview_awaiting_a_person(world):
    result = world.host.prepare(world.host.begin_turn(), "alignment_3d", {"reference_smiles": ETHANOL})
    prep = result.preparation
    assert prep.route is Route.NEEDS_APPROVAL and world.host.state_of(prep.run_id) is RunState.PREVIEWED
    assert "31 s" in prep.decision.reason and prep in world.host.pending()


def test_a_fast_calculator_outside_its_measured_bound_becomes_a_preview_with_the_reason(world):
    prep = world.host.prepare(world.host.begin_turn(), "hbond_vs_ph", {"ph_step": 0.01}).preparation
    assert prep.route is Route.NEEDS_APPROVAL and "ph_step" in prep.decision.reason


def test_a_molecule_larger_than_anything_measured_needs_approval_for_any_calculator(world):
    world.add("C" * 50, "Fifty carbons")
    prep = world.host.prepare(world.host.begin_turn(), "polar_surface_area", {}).preparation
    assert prep.route is Route.NEEDS_APPROVAL and "50 heavy atoms" in prep.decision.reason


def test_every_line_of_a_preview_card_is_a_finished_sentence(world):
    """The reasons are clauses (`... can take far longer`) and the card stacks lines under one another, so one
    without a full stop read as running into the next. Seen in the real window's screenshot."""
    world.add("C" * 50, "Fifty carbons")
    prep = world.host.prepare(world.host.begin_turn(), "polar_surface_area", {}).preparation
    assert prep.preview
    for line in prep.preview:
        assert line.endswith((".", "!", "?")), line


def test_an_unclassified_plugin_calculator_needs_approval(world):
    world.services.calculator_registry.register(CalculatorDefinition(
        calculator_id="plugin_calc", display_name="Plugin", category="charge", description="",
        execution=RegistryExecution(compute=_fake_ok), scope=CalculatorScope(ComponentSelection.WHOLE_STRUCTURE, Aggregation.SCALAR),
    ))
    assert world.host.prepare(world.host.begin_turn(), "plugin_calc", {}).preparation.route is Route.NEEDS_APPROVAL


# --- running an automatic request -------------------------------------------------------------------------


def test_an_automatic_run_completes_and_is_recorded_like_one_a_person_started(world):
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "polar_surface_area", {}).preparation
    thread, box = world.run_in_worker(turn, prep.run_id)
    outcome = world.finish(thread, box)

    assert outcome.state is RunState.COMPLETED and outcome.has_number
    assert outcome.stored.identity.producer == "polar_surface_area" and outcome.stored.identity.molecule_uuid == world.molecule.uuid
    assert world.host.state_of(prep.run_id) is RunState.COMPLETED
    # Recorded in the result store, current for this structure -- not a private copy.
    fresh = world.services.result_store_service.store.fresh_results(world.molecule.uuid, world.services.result_store_service.fingerprints_for(world.molecule))
    assert any(s.identity.producer == "polar_surface_area" for s in fresh)
    assert [o.state for o in world.outcomes] == [RunState.COMPLETED]


def test_the_identity_of_an_ai_run_is_the_same_as_a_run_with_the_same_settings_from_the_dialog(world):
    from openchem.services.result_cache import parameters_key

    definition = world.services.calculator_registry.get("polar_surface_area")
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "polar_surface_area", {"pH": 7}).preparation
    thread, box = world.run_in_worker(turn, prep.run_id)
    outcome = world.finish(thread, box)
    dialog = {p.name: p.default for p in definition.parameters}
    dialog["pH"] = 7.0
    assert outcome.stored.identity.parameters_key == parameters_key(dialog)


def test_asking_for_a_run_twice_starts_one_calculation(world):
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "polar_surface_area", {}).preparation
    thread, box = world.run_in_worker(turn, prep.run_id)
    first = world.finish(thread, box)
    again, box2 = world.run_in_worker(turn, prep.run_id)
    _pump(world.qapp, lambda: not again.is_alive())
    assert box2["outcome"] is first or box2["outcome"].state is RunState.COMPLETED
    assert world.pool.tasks == [] and len(world.outcomes) == 1


def test_two_callers_racing_for_one_run_start_one_calculation_and_share_its_outcome(world):
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "polar_surface_area", {}).preparation
    t1, b1 = world.run_in_worker(turn, prep.run_id)
    t2, b2 = world.run_in_worker(turn, prep.run_id)
    _pump(world.qapp, lambda: world.pool.tasks)
    time.sleep(0.1)
    _pump(world.qapp, lambda: True)
    assert len(world.pool.tasks) == 1
    world.pool.run_all()
    _pump(world.qapp, lambda: not t1.is_alive() and not t2.is_alive())
    assert b1["outcome"].state is RunState.COMPLETED and b2["outcome"].state is RunState.COMPLETED


def test_a_request_that_needs_a_person_is_not_started_by_asking_to_run_it(world):
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "alignment_3d", {"reference_smiles": ETHANOL}).preparation
    thread, box = world.run_in_worker(turn, prep.run_id)
    _pump(world.qapp, lambda: not thread.is_alive())
    assert box["outcome"].state is RunState.PREVIEWED and "approve" in box["outcome"].message
    world.qapp.processEvents()
    assert world.pool.tasks == [] and world.host.state_of(prep.run_id) is RunState.PREVIEWED


def test_a_run_nobody_prepared_is_rejected(world):
    turn = world.host.begin_turn()
    thread, box = world.run_in_worker(turn, "made-up-by-a-model")
    _pump(world.qapp, lambda: not thread.is_alive())
    assert box["outcome"].state is RunState.REJECTED and box["outcome"].problems[0].code is ProblemCode.NO_SUCH_RUN


def test_a_run_prepared_in_another_turn_cannot_be_started_from_this_one(world):
    first = world.host.begin_turn()
    prep = world.host.prepare(first, "polar_surface_area", {}).preparation
    second = world.host.begin_turn()
    thread, box = world.run_in_worker(second, prep.run_id)
    _pump(world.qapp, lambda: not thread.is_alive())
    assert box["outcome"].problems[0].code is ProblemCode.WRONG_TURN and world.pool.tasks == []


def test_run_refuses_to_wait_on_the_gui_thread(world):
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "polar_surface_area", {}).preparation
    with pytest.raises(RuntimeError, match="worker thread"):
        world.host.run(turn, prep.run_id)


def test_a_calculator_that_declines_is_a_refused_run_with_its_own_words_and_no_number(world):
    def decline(mol, molecule_uuid, params):
        raise CalculationRefusal(INPUT_REQUIRED, "Needs a density", "Type in a loading density.")

    world.register("decliner", decline)
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "decliner", {}).preparation
    thread, box = world.run_in_worker(turn, prep.run_id)
    outcome = world.finish(thread, box)
    assert outcome.state is RunState.REFUSED and not outcome.has_number
    assert outcome.status == "needs_input" and "Needs a density" in outcome.message and "code" in outcome.message


def test_a_calculator_that_crashes_is_a_failed_run(world):
    def crash(mol, molecule_uuid, params):
        raise RuntimeError("boom")

    world.register("crasher", crash)
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "crasher", {}).preparation
    thread, box = world.run_in_worker(turn, prep.run_id)
    outcome = world.finish(thread, box)
    assert outcome.state is RunState.FAILED and "boom" in outcome.message and not outcome.has_number


def test_a_run_still_going_when_the_caller_stops_waiting_is_timed_out_not_restarted(world):
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "polar_surface_area", {}).preparation
    thread, box = world.run_in_worker(turn, prep.run_id, timeout=0.3)
    _pump(world.qapp, lambda: world.pool.tasks)
    _pump(world.qapp, lambda: not thread.is_alive())
    assert box["outcome"].state is RunState.TIMED_OUT and "Do not ask again" in box["outcome"].message
    assert world.host.state_of(prep.run_id) is RunState.RUNNING

    world.pool.run_all()                       # the work finishes after the caller gave up
    assert world.host.state_of(prep.run_id) is RunState.COMPLETED

    again, box2 = world.run_in_worker(turn, prep.run_id)
    _pump(world.qapp, lambda: not again.is_alive())
    assert box2["outcome"].state is RunState.COMPLETED and world.pool.tasks == []


# --- the plan is checked against the live molecule when it starts ---------------------------------------------


def test_a_structure_edited_after_prepare_voids_the_run_and_starts_nothing(world):
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "polar_surface_area", {}).preparation
    world.engine.set_structure_from_smiles(world.molecule, ETHANOL)   # redrawn between prepare and run
    thread, box = world.run_in_worker(turn, prep.run_id)
    outcome = world.finish(thread, box, run_pool=False)
    assert outcome.state is RunState.INVALIDATED and "structure changed" in outcome.message
    assert world.pool.tasks == [] and world.host.state_of(prep.run_id) is RunState.INVALIDATED


def test_a_different_project_voids_the_run(world):
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "polar_surface_area", {}).preparation
    world.session.set_project(ProjectModel(name="Other"))
    thread, box = world.run_in_worker(turn, prep.run_id)
    outcome = world.finish(thread, box, run_pool=False)
    assert outcome.state is RunState.INVALIDATED and world.pool.tasks == []


# --- approval ---------------------------------------------------------------------------------------------------


def _previewed(world):
    turn = world.host.begin_turn()
    return turn, world.host.prepare(turn, "alignment_3d", {"reference_smiles": ETHANOL}).preparation


def test_approving_a_preview_starts_it_once_and_records_the_outcome(world):
    _turn, prep = _previewed(world)
    assert world.host.approve(prep.run_id) is RunState.RUNNING
    assert len(world.pool.tasks) == 1
    world.pool.run_all()
    assert world.host.state_of(prep.run_id) in (RunState.COMPLETED, RunState.REFUSED, RunState.FAILED)
    assert world.host.approve(prep.run_id) is world.host.state_of(prep.run_id) and world.pool.tasks == []
    assert len(world.outcomes) == 1


def test_approving_twice_starts_one_calculation(world):
    _turn, prep = _previewed(world)
    world.host.approve(prep.run_id)
    world.host.approve(prep.run_id)
    assert len(world.pool.tasks) == 1


def test_cancelling_leaves_nothing_running_and_cannot_be_undone_by_approving(world):
    _turn, prep = _previewed(world)
    assert world.host.cancel(prep.run_id) is True
    assert world.host.approve(prep.run_id) is RunState.CANCELLED
    assert world.pool.tasks == [] and [o.state for o in world.outcomes] == [RunState.CANCELLED]


def test_a_preview_approved_after_the_structure_changed_is_voided_not_started(world):
    _turn, prep = _previewed(world)
    world.engine.set_structure_from_smiles(world.molecule, ETHANOL)
    assert world.host.approve(prep.run_id) is RunState.INVALIDATED
    assert world.pool.tasks == [] and [o.state for o in world.outcomes] == [RunState.INVALIDATED]


def test_approving_something_that_was_never_a_preview_does_nothing(world):
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "polar_surface_area", {}).preparation   # automatic
    assert world.host.approve(prep.run_id) is RunState.PREPARED and world.pool.tasks == []
    assert world.host.approve("invented") is None


def test_approval_and_cancel_are_gui_thread_calls(world):
    _turn, prep = _previewed(world)
    errors: list = []

    def attempt(call):
        try:
            call(prep.run_id)
        except RuntimeError as error:
            errors.append(str(error))

    for call in (world.host.approve, world.host.cancel):
        thread = threading.Thread(target=attempt, args=(call,))
        thread.start()
        thread.join()
    assert len(errors) == 2 and all("GUI thread" in e for e in errors)
    assert world.pool.tasks == [] and world.host.state_of(prep.run_id) is RunState.PREVIEWED


def test_a_model_cannot_reach_approval_through_the_handle_a_tool_is_given():
    from openchem.plugins.calculation_access import PluginCalculations

    for name in ("approve", "cancel", "pending", "state_of", "outcome_of"):
        assert not hasattr(PluginCalculations(None), name), name


# --- the real thread pool ----------------------------------------------------------------------------------------


def test_with_the_real_pool_a_worker_thread_gets_a_computed_number(qapp):
    world = _World(qapp, held=False)
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "polar_surface_area", {}).preparation
    thread, box = world.run_in_worker(turn, prep.run_id)
    _pump(qapp, lambda: not thread.is_alive(), seconds=30.0)
    outcome = box["outcome"]
    assert outcome.state is RunState.COMPLETED and outcome.has_number
    assert QThread.currentThread() is world.host.thread()


def test_with_the_real_pool_a_finished_runs_result_is_in_the_next_turns_snapshot(qapp):
    world = _World(qapp, held=False)
    turn = world.host.begin_turn()
    prep = world.host.prepare(turn, "polar_surface_area", {}).preparation
    thread, box = world.run_in_worker(turn, prep.run_id)
    _pump(qapp, lambda: not thread.is_alive(), seconds=30.0)

    assert world.host.read_results(turn, ["polar_surface_area"]).not_run == ("polar_surface_area",), "the FIRST turn is frozen"
    later = world.host.begin_turn()
    current = world.host.read_results(later, ["polar_surface_area"]).entries
    assert len(current) == 1 and current[0].producer == "polar_surface_area"


# --- service-run calculators: a preview of what they would take, never a run ---------------------------------------


def test_a_service_run_calculator_is_previewed_with_what_it_needs_and_nothing_is_prepared(world):
    result = world.host.prepare(world.host.begin_turn(), "orca.sp", {})
    assert not result.ok and [p.code for p in result.problems] == [ProblemCode.SERVICE_RUN]
    preview = result.service_preview
    assert preview.can_start_here is False and preview.panel_id == "Quantum_Chemistry"
    assert [r.what for r in preview.requirements][0].startswith("a drawn structure for Aspirin")
    assert world.host.pending() == () and world.pool.tasks == []
    json.dumps(result.to_dict())


def test_the_conformer_requirement_follows_the_molecule(world):
    def conformer_requirement():
        preview = world.host.prepare(world.host.begin_turn(), "orca.sp", {}).service_preview
        return next(r for r in preview.requirements if r.what.startswith("a 3D conformer"))

    assert conformer_requirement().ok is False and conformer_requirement().how_to_fix
    world.add_conformer(world.molecule)
    assert conformer_requirement().ok is True and conformer_requirement().how_to_fix == ""


def test_the_orca_requirement_reads_the_live_configuration_and_starts_nothing(world, tmp_path, monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)
    qc = world.services.quantum_chemistry_service
    qc._settings.set("orca/executable_path", "")

    def requirement():
        preview = world.host.prepare(world.host.begin_turn(), "orca.sp", {}).service_preview
        return next(r for r in preview.requirements if r.what == "the ORCA executable"), preview

    missing, preview = requirement()
    assert missing.ok is False and "External Tools" in missing.how_to_fix and preview.ready is False

    fake = tmp_path / "orca.exe"
    fake.write_text("not really")
    qc._settings.set("orca/executable_path", str(fake))
    found, _ = requirement()
    assert found.ok is True and qc.orca_executable() == str(fake)
    assert world.pool.tasks == []


def test_a_docking_preview_asks_for_a_receptor_and_for_vina(world):
    preview = world.host.prepare(world.host.begin_turn(), "docking.vina", {}).service_preview
    whats = {r.what: r for r in preview.requirements}
    assert whats["a receptor macromolecule in the project"].ok is False
    assert whats["AutoDock Vina"].ok is world.services.docking_service.is_available()


def test_the_hsab_preview_needs_orca_but_not_a_conformer(world):
    preview = world.host.prepare(world.host.begin_turn(), "lewis_hsab", {}).service_preview
    whats = [r.what for r in preview.requirements]
    assert "the ORCA executable" in whats and not any(w.startswith("a 3D conformer") for w in whats)


def test_a_service_run_request_is_validated_like_any_other(world):
    result = world.host.prepare(world.host.begin_turn(), "orca.sp", {"method_basis": "not a method"})
    assert [p.code for p in result.problems] == [ProblemCode.NOT_A_CHOICE] and result.service_preview is None


def test_a_service_run_preview_needs_a_drawn_structure(world):
    world.add(None, "Blank")
    result = world.host.prepare(world.host.begin_turn(), "orca.sp", {})
    assert [p.code for p in result.problems] == [ProblemCode.NO_STRUCTURE] and result.service_preview is None
