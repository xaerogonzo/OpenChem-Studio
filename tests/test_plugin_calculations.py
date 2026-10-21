"""`context.calculations`: the plugin's handle on the calculator bridge, and what it must not carry."""

from __future__ import annotations

from pathlib import Path

from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.chem.engine import ChemistryEngine, InvalidStructureError
from openchem.domain.calculation_bridge import ProblemCode
from openchem.domain.molecule import MoleculeModel
from openchem.domain.run_lifecycle import PrepareResult, RunOutcome, RunState
from openchem.domain.turn_snapshot import build_turn_context
from openchem.plugins.calculation_access import PluginCalculations
from openchem.plugins.manager import PluginManager
from test_plugin_manager import FakeUIRegistry

import pytest


def _turn():
    return build_turn_context(
        project_uuid="p", molecule_uuid="m", display_name="Aspirin", canonical_smiles="", heavy_atoms=13,
        has_structure=True, conformer_count=0, fingerprints={"drawing": "fp"}, records=[], fresh=[],
    )


class _FakeHost:
    def __init__(self):
        self.calls = []

    def begin_turn(self):
        self.calls.append(("begin_turn",))
        return _turn()

    def catalog(self, query="", limit=20):
        self.calls.append(("catalog", query, limit))
        return ()

    def describe(self, calculator_id):
        self.calls.append(("describe", calculator_id))
        return None

    def goals(self):
        self.calls.append(("goals",))
        return ()

    def prepare(self, turn, calculator_id, parameters=None):
        self.calls.append(("prepare", calculator_id, parameters))
        return PrepareResult()

    def run(self, turn, run_id, *, timeout=None):
        self.calls.append(("run", run_id, timeout))
        return RunOutcome(run_id, "c", RunState.COMPLETED)


# --- the handle ---------------------------------------------------------------------------------


def test_the_handle_offers_exactly_these_calls_and_none_that_approve():
    public = {name for name in dir(PluginCalculations) if not name.startswith("_")}
    assert public == {"available", "begin_turn", "catalog", "describe", "goals", "read_results", "read_scores", "list_score_outputs", "propose_score", "prepare", "run"}


def test_the_handle_does_not_hand_out_the_host():
    handle = PluginCalculations(_FakeHost())
    for name in dir(handle):
        if name.startswith("_"):
            continue
        assert not isinstance(getattr(handle, name, None), _FakeHost), name


def test_with_no_host_every_call_answers_unavailable_rather_than_raising():
    handle = PluginCalculations(None)
    assert handle.available is False
    assert handle.begin_turn() is None and handle.catalog("x") == () and handle.describe("x") is None
    assert handle.goals() == ()
    prepared = handle.prepare(_turn(), "polar_surface_area", {})
    assert not prepared.ok and prepared.problems[0].code is ProblemCode.UNAVAILABLE
    outcome = handle.run(_turn(), "r1")
    assert outcome.state is RunState.REJECTED and outcome.problems[0].code is ProblemCode.UNAVAILABLE


def test_reading_results_needs_no_host_because_it_reads_only_the_frozen_turn():
    view = PluginCalculations(None).read_results(_turn(), ["pka"])
    assert view.not_run == ("pka",) and view.entries == ()


def test_the_handle_passes_every_call_to_the_host_unchanged():
    host = _FakeHost()
    handle = PluginCalculations(host)
    turn = handle.begin_turn()
    handle.catalog("lewis", 3)
    handle.describe("pka")
    handle.goals()
    handle.prepare(turn, "polar_surface_area", {"pH": 7})
    handle.run(turn, "r1", timeout=2.5)
    assert host.calls == [
        ("begin_turn",), ("catalog", "lewis", 3), ("describe", "pka"), ("goals",),
        ("prepare", "polar_surface_area", {"pH": 7}), ("run", "r1", 2.5),
    ]


# --- the context and the manager ----------------------------------------------------------------------


_CAPTURE = """
from openchem.plugins.interfaces import Plugin

class Capture(Plugin):
    def activate(self, context):
        pass
    def deactivate(self):
        pass

def create_plugin():
    return Capture()
"""


def _load_capture_plugin(tmp_path: Path, host):
    plugins = tmp_path / "plugins" / "capture"
    plugins.mkdir(parents=True)
    (plugins / "plugin.py").write_text(_CAPTURE, encoding="utf-8")
    (plugins / "manifest.toml").write_text(
        'plugin_id = "capture"\nversion = "0.1.0"\napi_version = 1\ndisplay_name = "Capture"\n'
        'author = "t"\ndescription = "d"\nhomepage = ""\nlicense = "GPL-3.0-or-later"\ndependencies = []\n',
        encoding="utf-8",
    )
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "none"))
    manager = PluginManager(services, FakeUIRegistry(), settings, host)
    manager.load_all()
    assert "capture" in manager.loaded_plugin_ids
    return manager._loaded["capture"].context.calculations


def test_a_plugin_loaded_with_a_host_gets_a_working_handle(tmp_path, qapp):
    host = _FakeHost()
    handle = _load_capture_plugin(tmp_path, host)
    assert handle.available is True
    handle.catalog("pka")
    assert ("catalog", "pka", 20) in host.calls


def test_a_plugin_loaded_without_a_host_gets_an_unavailable_handle(tmp_path, qapp):
    assert _load_capture_plugin(tmp_path, None).available is False


# --- the small additions this slice made -----------------------------------------------------------------


def test_the_registry_lists_every_calculator_as_a_copy():
    registry = build_service_container().calculator_registry
    listed = registry.definitions()
    assert len(listed) == 74 and listed[0].calculator_id == next(iter(registry._definitions))
    listed.clear()
    assert len(registry.definitions()) == 74


def test_the_engine_counts_the_heavy_atoms_of_a_drawing():
    engine = ChemistryEngine()
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CC(=O)Oc1ccccc1C(=O)O")
    assert engine.heavy_atom_count(model) == 13
    with pytest.raises(InvalidStructureError):
        engine.heavy_atom_count(MoleculeModel())


# --- the approvals face: for a panel, never a tool ------------------------------------------------------


from PySide6.QtCore import QObject, Signal

from openchem.plugins.calculation_access import PluginCalculationApprovals
from openchem.plugins.context import PluginContext


class _FakeApprovalHost(QObject):
    finished = Signal(object)

    def __init__(self):
        super().__init__()
        self.calls = []

    def pending(self):
        self.calls.append(("pending",))
        return ()

    def approve(self, run_id):
        self.calls.append(("approve", run_id))
        return RunState.RUNNING

    def cancel(self, run_id):
        self.calls.append(("cancel", run_id))
        return True

    def state_of(self, run_id):
        return RunState.PREVIEWED

    def outcome_of(self, run_id):
        return None


def test_the_approvals_face_offers_exactly_these_calls():
    public = {name for name in dir(PluginCalculationApprovals) if not name.startswith("_")}
    assert public == {
        "available", "pending", "approve", "cancel", "state_of", "outcome_of", "on_finished",
        "pending_scores", "approve_score", "cancel_score", "score_state_of", "score_outcome_of", "on_score_finished",
    }


def test_with_no_host_nothing_is_pending_and_no_decision_does_anything():
    approvals = PluginCalculationApprovals(None)
    assert approvals.available is False and approvals.pending() == ()
    assert approvals.approve("r") is None and approvals.cancel("r") is False
    assert approvals.state_of("r") is None and approvals.outcome_of("r") is None
    approvals.on_finished(lambda outcome: None)  # nothing to connect to, and no error


def test_the_approvals_face_passes_decisions_to_the_host(qapp):
    host = _FakeApprovalHost()
    approvals = PluginCalculationApprovals(host)
    approvals.pending()
    assert approvals.approve("r1") is RunState.RUNNING and approvals.cancel("r2") is True
    assert host.calls == [("pending",), ("approve", "r1"), ("cancel", "r2")]


def _context(tmp_path, host):
    services = build_service_container()
    settings = Settings(services.event_bus)
    return PluginContext("p", tmp_path, services, FakeUIRegistry(), settings, host)


def test_the_context_gives_a_plugin_both_faces_as_different_objects(tmp_path, qapp):
    context = _context(tmp_path, _FakeApprovalHost())
    assert isinstance(context.calculations, PluginCalculations)
    assert isinstance(context.calculation_approvals, PluginCalculationApprovals)
    assert context.calculation_approvals is not context.calculations
    assert not hasattr(context.calculations, "approve") and not hasattr(context.calculations, "on_finished")


def test_a_finished_callback_runs_until_the_plugin_unloads_and_then_never_again(tmp_path, qapp):
    host = _FakeApprovalHost()
    context = _context(tmp_path, host)
    seen = []
    context.calculation_approvals.on_finished(seen.append)
    outcome = RunOutcome("r1", "c", RunState.COMPLETED)
    host.finished.emit(outcome)
    assert seen == [outcome]

    context.unwind()
    host.finished.emit(RunOutcome("r2", "c", RunState.COMPLETED))
    assert seen == [outcome], "a callback left connected would run against a panel that no longer exists"
