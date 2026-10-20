"""The assistant's calculator tools: what a model may ask, what it is told, and what it can never do.

Two layers. The bridge and tool functions are tested against a stub of the plugin handle, so each
behaviour is isolated; the panel is then driven end to end with a scripted provider, the REAL host
and a real worker thread, because the properties that matter here (the approval boundary, the frozen
turn, the preview that waits for a person) live in how the pieces meet.
"""

from __future__ import annotations

import json
import sys
import threading
import time

import pytest
from ai_assistant.bridge import REPLY_BUDGET, BridgeEvent, ToolBridge, bounded_json
from ai_assistant.calculation_tools import CALCULATION_HANDLERS, CALCULATION_TOOLS
from ai_assistant.panel import SYSTEM_PROMPT_PREFIX
from ai_assistant.providers import AIMessage, AIResponse, ToolCall
from ai_assistant.tools import AVAILABLE_TOOLS, validate_arguments
from test_ai_assistant_panel import _StubToolProvider
from test_calculation_host import ASPIRIN, ETHANOL, _pump, _World
from test_plugin_manager import FakeUIRegistry

from openchem.app.settings import Settings
from openchem.domain.calculation_bridge import ProblemCode
from openchem.domain.calculator_goals import GOALS
from openchem.domain.common import CacheState
from openchem.domain.result_envelope import CAP_STEPS, envelope_of
from openchem.domain.run_lifecycle import RunState
from openchem.domain.scientific_result import PerAtomDataset
from openchem.plugins.calculation_access import PluginCalculations
from openchem.plugins.manager import PluginManager
from pathlib import Path

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"


# --- argument validation ------------------------------------------------------------------------------


SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 30},
        "flag": {"type": "boolean"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "mode": {"type": "string", "enum": ["a", "b"]},
        "settings": {"type": "object"},
    },
    "required": ["name"],
}


def test_valid_arguments_have_no_problems():
    assert validate_arguments(SCHEMA, {"name": "x", "limit": 5, "flag": True, "tags": ["a"], "mode": "a", "settings": {"k": 1}}) == []


def test_every_way_of_getting_the_arguments_wrong_is_named():
    cases = {
        "missing": ({}, "name is required"),
        "wrong type": ({"name": 3}, "name must be string"),
        "bool is not an integer": ({"name": "x", "limit": True}, "limit must be integer"),
        "float is not an integer": ({"name": "x", "limit": 2.5}, "limit must be integer"),
        "too small": ({"name": "x", "limit": 0}, "limit must be at least 1"),
        "too large": ({"name": "x", "limit": 31}, "limit must be at most 30"),
        "not an enum member": ({"name": "x", "mode": "z"}, "mode must be one of"),
        "array item": ({"name": "x", "tags": ["a", 1]}, "tags[1] must be string"),
        "undeclared argument": ({"name": "x", "extra": 1}, "'extra' is not an argument"),
        "not an object": ("name", "must be an object"),
    }
    for label, (arguments, expected) in cases.items():
        problems = validate_arguments(SCHEMA, arguments)
        assert any(expected in p for p in problems), (label, problems)


def test_a_number_is_accepted_where_a_number_is_asked_for_and_a_bool_is_not():
    schema = {"type": "object", "properties": {"x": {"type": "number"}}}
    assert validate_arguments(schema, {"x": 3}) == [] and validate_arguments(schema, {"x": 3.5}) == []
    assert validate_arguments(schema, {"x": True})


def test_every_tool_definition_is_a_well_formed_schema_that_accepts_its_own_minimal_call():
    for tool in [*AVAILABLE_TOOLS, *CALCULATION_TOOLS]:
        required = tool.input_schema.get("required", [])
        sample = {name: _sample(tool.input_schema["properties"][name]) for name in required}
        assert validate_arguments(tool.input_schema, sample) == [], tool.name


def _sample(spec):
    return {"string": "x", "integer": 1, "number": 1.0, "boolean": True, "object": {}, "array": []}[spec["type"]]


# --- the bridge against a stub handle -------------------------------------------------------------------


class _StubCalculations(PluginCalculations):
    """The real handle's behaviour with no host: every call answers `unavailable`."""

    def __init__(self):
        super().__init__(None)


def _bridge(calculations=None, turn=None, events=None):
    return ToolBridge(calculations or _StubCalculations(), turn, events.append if events is not None else None)


def test_a_bridge_with_no_host_or_no_molecule_says_unavailable_and_never_raises():
    bridge = _bridge()
    assert bridge.available is False
    for text in (
        bridge.find_calculators("x"), bridge.list_goals(), bridge.describe_calculator("x"), bridge.read_results(), bridge.read_scores(),
        bridge.propose_score({"label": "x"}), bridge.run_calculator("x"),
    ):
        data = json.loads(text)
        assert data["ok"] is False and data["problem"] == "unavailable"


def test_the_bridge_a_tool_receives_has_no_way_to_approve_or_cancel():
    surface = {name for name in dir(ToolBridge) if not name.startswith("_")}
    assert surface == {
        "available", "turn", "find_calculators", "list_goals", "describe_calculator", "read_results", "read_scores", "list_score_outputs", "propose_score", "run_calculator",
    }
    for name in ("approve", "cancel", "pending", "on_finished", "calculation_approvals"):
        assert not hasattr(_bridge(), name)
    assert "approve" not in " ".join(CALCULATION_HANDLERS) and len(CALCULATION_TOOLS) == len(CALCULATION_HANDLERS) == 8


def test_the_tool_descriptions_tell_the_model_what_it_must_not_do():
    by_name = {t.name: t.description for t in CALCULATION_TOOLS}
    assert "never be reported as the current answer" in by_name["read_results"]
    assert "never state a value" in by_name["read_results"]
    assert "cannot approve" in by_name["run_calculator"] and "never corrected" in by_name["run_calculator"]
    assert "route" in by_name["find_calculators"]
    assert "editorial" in by_name["list_goals"] and "starts nothing" in by_name["list_goals"]


def test_bounded_json_keeps_the_largest_detail_that_fits_and_says_when_it_shortened():
    def build(caps):
        return {"values": list(range(caps.atoms * 20))}

    small = bounded_json(build, budget=10**6)
    assert "shortened_for_length" not in json.loads(small)
    tight = bounded_json(build, budget=len(small) // 4)
    assert json.loads(tight)["shortened_for_length"] is True and len(tight) < len(small)
    # Nothing fits: the smallest step is still returned, marked, rather than cut mid-structure.
    assert json.loads(bounded_json(build, budget=5))["shortened_for_length"] is True


def test_a_huge_result_still_fits_the_reply_budget_with_its_header_and_units():
    from openchem.domain.result_store import ResultIdentity, StoredResult
    from openchem.domain.turn_snapshot import classify_results

    result = PerAtomDataset(property_id="p", name="P", units="e", method="m", molecule_uuid="m",
                            values={i: float(i) for i in range(50000)}, cache_state=CacheState.COMPLETED)
    stored = StoredResult(ResultIdentity("m", "p", "drawing", "fp", "calc"), result)
    entry = classify_results([stored], [stored], {"drawing": "fp"})[0]
    text = bounded_json(lambda caps: {"results": [envelope_of(entry, caps)]})
    data = json.loads(text)["results"][0]
    assert len(text) <= REPLY_BUDGET and data["data"]["units"] == "e" and data["data"]["count"] == 50000
    assert len(CAP_STEPS) == 4


# --- the real thing: a scripted provider, the real host, a real worker thread ----------------------------------


def _load_assistant(world, tmp_path):
    settings = Settings(world.services.event_bus)
    settings.set("plugins/project_directory", str(PLUGINS_DIR))
    settings.set("plugins/user_directory", str(tmp_path / "unused"))
    ui = FakeUIRegistry()
    manager = PluginManager(world.services, ui, settings, world.host)
    manager.load_all()
    assert "ai_assistant" in manager.loaded_plugin_ids
    return manager, ui.panels["AI Assistant"], ui


class _Rig:
    """A world with the assistant loaded against its real host."""

    def __init__(self, qapp, tmp_path, held=True):
        self.qapp = qapp
        self.world = _World(qapp, held=held)
        self.manager, self.panel, self.ui = _load_assistant(self.world, tmp_path)

    def bridge(self):
        """A bridge for a turn frozen NOW, as Send would, on the GUI thread."""
        calculations = self.panel._context.calculations
        return ToolBridge(calculations, calculations.begin_turn(), self.panel._bridge_signal.event.emit)

    def loop(self, provider, bridge, text="go"):
        """Run the tool loop on a worker thread, as `run_async` does, while this thread serves the GUI."""
        box: dict = {}
        thread = threading.Thread(
            target=lambda: box.update(response=self.panel._run_completion(
                provider, "sys", [AIMessage(role="user", content=text)], "m", "k", lambda c: None, bridge)),
            daemon=True,
        )
        thread.start()
        return thread, box

    def settle(self, thread, *, run_pool=False):
        if run_pool:
            _pump(self.qapp, lambda: self.world.pool.tasks)
            self.world.pool.run_all()
        _pump(self.qapp, lambda: not thread.is_alive(), seconds=30.0)
        self.qapp.processEvents()


def _call(name, **arguments):
    return ToolCall(id=f"t-{name}", name=name, input=arguments)


def _two_step(first_calls, final="Done."):
    return _StubToolProvider([
        AIResponse(text="", tool_calls=list(first_calls), stop_reason="tool_use"),
        AIResponse(text=final),
    ])


def _tool_message(provider):
    return [m for m in provider.stream_calls[1].messages if m.role == "tool"]


@pytest.fixture
def rig(qapp, tmp_path):
    return _Rig(qapp, tmp_path, held=True)


def test_the_calculator_tools_are_offered_only_when_a_molecule_is_selected_and_the_provider_takes_tools(rig):
    seen = []

    class Recorder(_StubToolProvider):
        def stream(self, request, on_chunk, tools=None):
            seen.append([t.name for t in tools] if tools is not None else None)
            return AIResponse(text="ok")

    thread, _ = rig.loop(Recorder([]), rig.bridge())
    rig.settle(thread)
    assert seen[0] == [t.name for t in [*AVAILABLE_TOOLS, *CALCULATION_TOOLS]]

    rig.world.session.select_molecule(None)
    thread, _ = rig.loop(Recorder([]), rig.bridge())
    rig.settle(thread)
    assert seen[1] == [t.name for t in AVAILABLE_TOOLS], "with nothing selected only the older tools are offered"

    class NoTools(Recorder):
        supports_tools = False

    thread, _ = rig.loop(NoTools([]), rig.bridge())
    rig.settle(thread)
    assert seen[2] is None


def test_a_model_asking_for_an_automatic_run_gets_the_result_with_its_provenance(qapp, tmp_path):
    rig = _Rig(qapp, tmp_path, held=False)
    provider = _two_step([_call("run_calculator", calculator_id="polar_surface_area", parameters={"pH": 7})])
    thread, box = rig.loop(provider, rig.bridge())
    rig.settle(thread)

    (message,) = _tool_message(provider)
    outcome = json.loads(message.content)
    assert outcome["state"] == "completed" and outcome["has_number"] is True
    result = outcome["result"]
    assert result["freshness"] == "current" and result["calculator"] == "polar_surface_area"
    assert result["input"]["fingerprint"] and result["parameters"]["pH"] == 7.0 and result["data"]
    assert box["response"].text == "Done."
    assert rig.panel.ledger_lines() == ["polar_surface_area on Aspirin: completed"]


def test_bad_arguments_never_reach_the_tool_and_the_problems_come_back(rig):
    provider = _two_step([_call("run_calculator")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    (message,) = _tool_message(provider)
    assert "was not run" in message.content and "calculator_id is required" in message.content
    assert rig.world.pool.tasks == [] and rig.panel.ledger_lines() == []


def test_an_invalid_setting_is_refused_with_every_problem_and_nothing_starts(rig):
    provider = _two_step([_call("run_calculator", calculator_id="geometry_analysis", parameters={"conformer_policy": "lowest_energy", "colour": 1})])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    data = json.loads(_tool_message(provider)[0].content)
    assert data["ok"] is False and data["started"] is False
    assert {p["code"] for p in data["problems"]} == {"not_a_choice", "unknown_parameter"}
    assert rig.world.pool.tasks == []
    assert any("not started" in line for line in rig.panel.ledger_lines())


def test_a_calculator_a_model_invents_is_refused_plainly(rig):
    provider = _two_step([_call("run_calculator", calculator_id="no_such_calculator")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    data = json.loads(_tool_message(provider)[0].content)
    assert data["problems"][0]["code"] == "unknown_calculator" and rig.world.pool.tasks == []


def test_a_service_run_calculator_is_described_with_what_it_would_take_and_cannot_be_started(rig):
    provider = _two_step([_call("run_calculator", calculator_id="orca.sp")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    reply = json.loads(_tool_message(provider)[0].content)
    assert reply["state"] == "preview_only" and reply["started"] is False and "You cannot start this" in reply["message"]
    preview = reply["service_preview"]
    assert preview["can_start_here"] is False and preview["run_it_from"] == "Quantum Chemistry panel"
    assert {r["what"] for r in preview["requirements"]} >= {"the ORCA executable"}
    assert "run_id" not in reply and rig.world.pool.tasks == [] and rig.world.host.pending() == ()

    rig.qapp.processEvents()
    (key,) = rig.panel.service_preview_keys()
    card = rig.panel._service_cards[key]
    assert not hasattr(card, "approve_button"), "nothing to approve: the assistant cannot start these"
    assert rig.panel.pending_run_ids() == []
    assert any("cannot be started from here" in line for line in rig.panel.ledger_lines())


def test_the_service_card_opens_the_panel_that_owns_the_job_and_can_be_dismissed(rig):
    provider = _two_step([_call("run_calculator", calculator_id="orca.sp")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    (key,) = rig.panel.service_preview_keys()
    card = rig.panel._service_cards[key]
    card.open_button.click()
    assert rig.ui.revealed_panels[-1] == "Quantum_Chemistry"
    card.dismiss_button.click()
    assert rig.panel.service_preview_keys() == [] and rig.panel._cards_host.isHidden()


def test_a_request_that_needs_a_person_leaves_a_preview_and_starts_nothing(rig):
    provider = _two_step([_call("run_calculator", calculator_id="alignment_3d", parameters={"reference_smiles": ETHANOL})])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    reply = json.loads(_tool_message(provider)[0].content)
    assert reply["state"] == "awaiting_approval" and reply["started"] is False and "31 s" in reply["why_approval_is_needed"]
    assert "do not call run_calculator" in reply["message"]

    rig.qapp.processEvents()
    assert rig.world.pool.tasks == [], "the model's request started nothing"
    assert len(rig.panel.pending_run_ids()) == 1
    card = next(iter(rig.panel._cards.values()))
    assert card.approve_button.text() == "Approve" and card.cancel_button.text() == "Cancel"
    assert any("waiting for your approval" in line for line in rig.panel.ledger_lines())


def test_asking_again_for_the_same_preview_does_not_start_it(rig):
    provider = _two_step([_call("run_calculator", calculator_id="alignment_3d", parameters={"reference_smiles": ETHANOL})])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    run_id = rig.panel.pending_run_ids()[0]
    # A model that ignores the instruction can only reach the same preview; no tool can start it.
    again = _two_step([_call("run_calculator", calculator_id="alignment_3d", parameters={"reference_smiles": ETHANOL})])
    thread, _ = rig.loop(again, rig.bridge())
    rig.settle(thread)
    assert rig.world.pool.tasks == [] and rig.world.host.state_of(run_id) is RunState.PREVIEWED


def test_only_the_users_approve_button_starts_a_preview_and_the_model_is_told_afterwards(rig):
    provider = _two_step([_call("run_calculator", calculator_id="alignment_3d", parameters={"reference_smiles": ETHANOL})])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    run_id = rig.panel.pending_run_ids()[0]
    card = rig.panel._cards[run_id]

    card.approve_button.click()
    assert len(rig.world.pool.tasks) == 1 and rig.panel.pending_run_ids() == []
    assert any("running" in line for line in rig.panel.ledger_lines())
    rig.world.pool.run_all()
    rig.qapp.processEvents()

    assert rig.world.host.state_of(run_id) in (RunState.COMPLETED, RunState.REFUSED, RunState.FAILED)
    assert any("completed" in line or "declined" in line or "failed" in line for line in rig.panel.ledger_lines())
    assert len(rig.panel._notes) == 1 and "[Application note]" in rig.panel._notes[0] and run_id in rig.panel._notes[0]

    # The note goes ahead of the user's next message, in the user's turn, so roles still alternate.
    rig.panel._input.setPlainText("what did it find?")
    sent = {}
    rig.panel._history.clear()
    # The plugin manager loads the plugin under a synthetic module name, so patch the module THIS panel
    # instance was built from, not the one the test imported.
    panel_module = sys.modules[type(rig.panel).__module__]
    original = panel_module.run_async
    panel_module.run_async = lambda func, *a, **k: sent.update(called=True)
    try:
        rig.panel._on_send_clicked()
    finally:
        panel_module.run_async = original
    assert sent.get("called") and rig.panel._notes == []
    last = rig.panel._history[-1]
    assert last.role == "user" and last.content.startswith("[Application note]") and last.content.endswith("what did it find?")


def test_cancelling_a_preview_starts_nothing_and_the_model_is_told_it_was_cancelled(rig):
    provider = _two_step([_call("run_calculator", calculator_id="alignment_3d", parameters={"reference_smiles": ETHANOL})])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    run_id = rig.panel.pending_run_ids()[0]
    rig.panel._cards[run_id].cancel_button.click()
    rig.qapp.processEvents()
    assert rig.world.pool.tasks == [] and rig.world.host.state_of(run_id) is RunState.CANCELLED
    assert any("cancelled" in line for line in rig.panel.ledger_lines())
    assert len(rig.panel._notes) == 1 and "cancelled" in rig.panel._notes[0]


def test_approving_after_the_structure_changed_voids_the_run_and_says_so(rig):
    provider = _two_step([_call("run_calculator", calculator_id="alignment_3d", parameters={"reference_smiles": ETHANOL})])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    run_id = rig.panel.pending_run_ids()[0]
    rig.world.engine.set_structure_from_smiles(rig.world.molecule, ETHANOL)
    rig.panel._cards[run_id].approve_button.click()
    assert rig.world.pool.tasks == [] and rig.world.host.state_of(run_id) is RunState.INVALIDATED
    assert any("withdrawn" in line for line in rig.panel.ledger_lines()) and "invalidated" in rig.panel._notes[0]


def test_an_automatic_runs_end_is_not_told_to_the_model_a_second_time(qapp, tmp_path):
    rig = _Rig(qapp, tmp_path, held=False)
    provider = _two_step([_call("run_calculator", calculator_id="polar_surface_area")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    assert rig.panel._notes == [] and rig.panel._awaiting == set()
    assert sum("completed" in line for line in rig.panel.ledger_lines()) == 1, "one ledger row per run, not one per announcement"


def test_reading_results_before_and_after_a_run_and_the_turn_that_was_frozen_before(qapp, tmp_path):
    rig = _Rig(qapp, tmp_path, held=False)
    before = rig.bridge()
    first = json.loads(before.read_results(["polar_surface_area"]))
    assert first["not_run"] == ["polar_surface_area"] and first["results"] == []

    provider = _two_step([_call("run_calculator", calculator_id="polar_surface_area")])
    thread, _ = rig.loop(provider, before)
    rig.settle(thread)

    still_frozen = json.loads(before.read_results(["polar_surface_area"]))
    assert still_frozen["not_run"] == ["polar_surface_area"], "a result finishing mid-turn cannot change what the turn reads"
    after = json.loads(rig.bridge().read_results(["polar_surface_area"]))
    assert after["not_run"] == [] and after["results"][0]["freshness"] == "current"


def test_selecting_another_molecule_mid_reply_changes_nothing_about_what_a_tool_reads(qapp, tmp_path):
    rig = _Rig(qapp, tmp_path, held=False)
    bridge = rig.bridge()
    rig.world.add(ETHANOL, "Ethanol")  # selects it
    assert rig.world.session.selected_molecule_uuid != bridge.turn.molecule_uuid
    provider = _two_step([_call("run_calculator", calculator_id="polar_surface_area")])
    thread, _ = rig.loop(provider, bridge)
    rig.settle(thread)
    outcome = json.loads(_tool_message(provider)[0].content)
    assert outcome["result"]["input"]["fingerprint"] == bridge.turn.fingerprints["drawing"][:16]
    stored = rig.world.services.result_store_service.store.all_results(bridge.turn.molecule_uuid)
    assert any(s.identity.producer == "polar_surface_area" for s in stored)
    assert rig.world.services.result_store_service.store.all_results(rig.world.session.selected_molecule_uuid) == []


def test_a_model_cannot_call_an_approve_tool_because_there_is_none(rig):
    provider = _two_step([_call("approve_calculation", run_id="x"), _call("cancel_run", run_id="x")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    assert [m.content for m in _tool_message(provider)] == ["Unknown tool: approve_calculation", "Unknown tool: cancel_run"]


def test_the_older_tools_still_work_beside_the_new_ones(rig):
    provider = _two_step([_call("validate_smarts", pattern="[C]")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    assert "Valid SMARTS pattern" in _tool_message(provider)[0].content


def test_find_and_describe_tell_the_model_what_it_may_run(rig):
    provider = _two_step([_call("find_calculators", query="adduct"), _call("describe_calculator", calculator_id="alignment_3d")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    found = json.loads(_tool_message(provider)[0].content)
    assert any(c["calculator_id"] == "lewis_adduct" for c in found["calculators"]) and "how_to_read_route" in found
    described = json.loads(_tool_message(provider)[1].content)["calculator"]
    assert described["route"] == "needs_approval" and described["parameters"]


# --- goals: the wizard's table, offered as knowledge and never as a way to run ---------------------------------


def test_listing_goals_with_no_argument_summarises_every_goal_the_wizard_has(rig):
    provider = _two_step([_call("list_goals")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    text = _tool_message(provider)[0].content
    data = json.loads(text)
    assert data["ok"] is True and "editorial" in data["note"] and len(text) <= REPLY_BUDGET
    assert [g["goal_id"] for g in data["goals"]] == [g.goal_id for g in GOALS]
    for shown, goal in zip(data["goals"], GOALS):
        assert shown["question"] == goal.question and shown["recommended"] == list(goal.recommended_ids())


def test_listing_one_goal_gives_each_entry_its_reason_its_route_and_the_split_by_what_the_assistant_may_do(rig):
    provider = _two_step([_call("list_goals", goal_id="charge"), _call("describe_calculator", calculator_id="alignment_3d")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    goal = json.loads(_tool_message(provider)[0].content)["goal"]
    wizard = next(g for g in GOALS if g.goal_id == "charge")
    assert [e["calculator_id"] for e in goal["entries"]] == [e.calculator_id for e in wizard.entries]
    assert [e["reason"] for e in goal["entries"]] == [e.reason for e in wizard.entries]
    placed = goal["you_may_run"] + goal["needs_user_approval"] + goal["cannot_start_here"]
    assert sorted(placed) == sorted(e["calculator_id"] for e in goal["entries"]) and len(set(placed)) == len(placed)
    # the same words describe_calculator uses for the same calculator
    described = json.loads(_tool_message(provider)[1].content)["calculator"]
    assert described["route"] in {"auto", "needs_approval", "preview_only", "blocked"}


def test_a_goal_tells_the_model_to_run_its_calculators_one_at_a_time_and_that_the_list_is_not_a_protocol(rig):
    text = rig.bridge().list_goals("solubility")
    data = json.loads(text)
    assert "run_calculator" in data["how_to_use"] and "one at a time" in data["how_to_use"]
    assert "not a validated protocol" in data["note"]


def test_every_goal_fits_the_reply_budget_in_full(rig):
    bridge = rig.bridge()
    for goal in GOALS:
        assert len(bridge.list_goals(goal.goal_id)) <= REPLY_BUDGET, goal.goal_id


def test_a_goal_id_nobody_has_is_named_with_the_ones_that_exist(rig):
    data = json.loads(rig.bridge().list_goals("make_gold"))
    assert data["ok"] is False and data["problem"] == "unknown_goal" and data["known"] == [g.goal_id for g in GOALS]


def test_the_loop_refuses_a_goal_id_outside_the_schema_before_the_tool_runs(rig):
    provider = _two_step([_call("list_goals", goal_id="make_gold")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    (message,) = _tool_message(provider)
    assert "was not run" in message.content and "goal_id must be one of" in message.content


def test_reading_every_goal_starts_nothing_asks_nobody_and_leaves_no_ledger_row(rig):
    provider = _two_step([_call("list_goals")] + [_call("list_goals", goal_id=g.goal_id) for g in GOALS])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    assert rig.world.pool.tasks == [] and rig.panel.pending_run_ids() == [] and rig.panel.ledger_lines() == []
    assert rig.panel._context.calculation_approvals.pending() == ()


# --- the words and the disclosure --------------------------------------------------------------------------------


def test_the_system_prompt_no_longer_claims_the_assistant_cannot_touch_the_project_and_states_the_rules():
    assert "no ability" not in SYSTEM_PROMPT_PREFIX and "Never claim to have modified" not in SYSTEM_PROMPT_PREFIX
    for needle in ("recorded in the user's project", "approve a preview", "never imply you approved", "historical",
                   "never present a missing result as zero", "cannot name another", "list_goals", "editorial"):
        assert needle in SYSTEM_PROMPT_PREFIX, needle
    assert SYSTEM_PROMPT_PREFIX.rstrip().endswith("selected molecule:")


def test_the_panel_says_where_calculator_results_go_for_each_provider(rig):
    notes = {}
    for provider_id in rig.panel._providers:
        rig.panel._provider_combo.setCurrentText(provider_id)
        notes[provider_id] = rig.panel._privacy.text()
    assert "leave this machine" in notes["anthropic"] and "anthropic" in notes["anthropic"]
    assert "leave this machine" in notes["openai"]
    assert "localhost:11434" in notes["ollama"] and "leave this machine" not in notes["ollama"]
    assert "cannot use this application's tools" in notes["claude_cli"]
    assert all(notes.values())
    for provider_id in ("anthropic", "openai", "ollama"):
        assert "names and formulas of your scores" in notes[provider_id], provider_id
    assert "nor read your scores" in notes["claude_cli"]


def test_a_panel_with_no_host_still_works_and_offers_no_calculator_tools(qapp, tmp_path):
    from test_ai_assistant_plugin import _make_manager

    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()
    panel = ui.panels["AI Assistant"]
    seen = []

    class Recorder(_StubToolProvider):
        def stream(self, request, on_chunk, tools=None):
            seen.append([t.name for t in tools])
            return AIResponse(text="ok")

    bridge = ToolBridge(panel._context.calculations, panel._context.calculations.begin_turn())
    panel._run_completion(Recorder([]), "s", [AIMessage(role="user", content="hi")], "m", "k", lambda c: None, bridge)
    assert seen == [[t.name for t in AVAILABLE_TOOLS]]
