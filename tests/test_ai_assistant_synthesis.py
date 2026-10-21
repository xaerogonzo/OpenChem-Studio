"""The assistant's synthesis tools (Stage 1 slice 9 of `docs/SYNTHESIS_HELPER_DESIGN.md`): a model can ASK for a search and read the plan, and a person decides.

Two layers, like the calculator tools. The bridge and the words are tested over a fake host, so each behaviour is isolated; the panel is then driven with a scripted provider on a real worker thread, and
the last tests put the REAL host and planning service under it, because the properties that matter live in how the pieces meet: nothing starts before Approve, the gate speaks inside the service
whoever asked, and what the model is told never carries the text the gate keeps for the person.
"""

from __future__ import annotations

import dataclasses
import json
import threading
import time
from pathlib import Path

import pytest
from ai_assistant.bridge import REPLY_BUDGET, BridgeEvent
from ai_assistant.panel import SYSTEM_PROMPT_PREFIX
from ai_assistant.providers import AIMessage, AIResponse, ToolCall
from ai_assistant.synthesis_tools import (
    GATE_DECLINED,
    HOW_TO_READ,
    PLAN_SYNTHESIS,
    READ_SYNTHESIS_PLAN,
    SYNTHESIS_HANDLERS,
    SYNTHESIS_TOOLS,
    SynthesisBridge,
    SynthesisTurn,
    begin_synthesis_turn,
    card_key,
    card_lines,
    plan_envelope,
)
from ai_assistant.tools import AVAILABLE_TOOLS, validate_arguments
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from test_ai_assistant_bridge import _call, _two_step
from test_ai_assistant_panel import _StubToolProvider
from test_plugin_manager import FakeUIRegistry
from test_synthesis_host import World as RealWorld
from test_synthesis_panel import ANHYDRIDE, ASPIRIN, OPTIONS, SALICYLIC, TARGET, UUID, FakeHost, route_set

from openchem.app.settings import Settings
from openchem.app.synthesis_host import SynthesisHost as RealHost
from openchem.bootstrap import build_service_container
from openchem.chem import aizynth_planner as planner_host
from openchem.chem import synthesis_gate as gate_module
from openchem.domain.synthesis_gate import AlertFinding, GateDecision, GateMatch, GateOutcome, NodeScreening
from openchem.domain.synthesis_route import Check, MappingStatus, RouteSet, RouteStatus, StockStatus, ValidationReport, route_molecules
from openchem.events.events import SynthesisRouteReady
from openchem.plugins.manager import PluginManager
from openchem.plugins.synthesis_access import PluginSynthesis, PluginSynthesisRequests
from openchem.services.synthesis_planning_service import BoundResult, RequestOutcome

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"

#: Text the gate and the screens keep for the PERSON. If it appears in anything a model is told, the split is broken.
SENTINEL = "SENTINEL-LISTING-NAME"
SECRET_REASON = "SENTINEL-REASON D:\\Users\\someone\\planner\\env"


class Host(FakeHost):
    """The fake host of the synthesis panel's tests, plus the call a card's Approve makes before it asks."""

    def __init__(self) -> None:
        super().__init__()
        self.structures = {UUID: TARGET}

    def structure_of(self, molecule_uuid):
        return self.structures.get(molecule_uuid)


def screened(route_set_: RouteSet, alert_on: str | None = ASPIRIN, unscreened: str | None = None) -> RouteSet:
    """The set with a screening for every molecule of its routes: one alert (by a sentinel name), one molecule that could not be screened."""
    seen: list[str] = []
    for route in route_set_.routes:
        for smiles in route_molecules(route):
            if smiles not in seen:
                seen.append(smiles)
    rows = []
    for smiles in seen:
        if smiles == unscreened:
            rows.append(NodeScreening(smiles=smiles, screened=False, reason=SECRET_REASON))
            continue
        findings = ()
        if smiles == alert_on:
            findings = (AlertFinding(ruleset_id="test-ruleset", rule_id="test-rule-1", display_name=SENTINEL, domain="exposure_limit", jurisdiction="XX", section="s1", confidence="exact"),)
        rows.append(NodeScreening(smiles=smiles, screened=True, findings=findings, rulesets_consulted=("test-ruleset",), screened_on="today"))
    return dataclasses.replace(route_set_, node_screenings=tuple(rows))


def bound(route_set_: RouteSet, current: bool = True) -> BoundResult:
    return BoundResult(route_set=route_set_, is_current=current, note="" if current else "made for an earlier structure")


def pump(predicate, seconds=10.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class Rig:
    """The assistant plugin loaded over a synthesis host, as the application loads it."""

    def __init__(self, tmp_path, host, services=None) -> None:
        self.services = services or build_service_container()
        settings = Settings(self.services.event_bus)
        settings.set("plugins/project_directory", str(PLUGINS_DIR))
        settings.set("plugins/user_directory", str(tmp_path / "unused"))
        self.ui = FakeUIRegistry()
        self.manager = PluginManager(self.services, self.ui, settings, None, host)
        self.manager.load_all()
        assert "ai_assistant" in self.manager.loaded_plugin_ids
        self.host = host
        self.panel = self.ui.panels["AI Assistant"]

    def bridge(self, events=None) -> SynthesisBridge:
        """A bridge for a turn frozen NOW, as Send would, on the GUI thread."""
        context = self.panel._context
        emit = events.append if events is not None else self.panel._bridge_signal.event.emit
        return SynthesisBridge(context.synthesis, begin_synthesis_turn(context.synthesis), emit)

    def loop(self, provider, synthesis, text="go"):
        """Run the tool loop on a worker thread, as `run_async` does, while this thread serves the GUI."""
        box: dict = {}
        thread = threading.Thread(
            target=lambda: box.update(response=self.panel._run_completion(provider, "sys", [AIMessage(role="user", content=text)], "m", "k", lambda c: None, None, synthesis)),
            daemon=True,
        )
        thread.start()
        return thread, box

    def settle(self, thread) -> None:
        assert pump(lambda: not thread.is_alive(), 30.0)
        QApplication.processEvents()

    def ask(self, *calls, synthesis=None):
        provider = _two_step(list(calls))
        thread, _box = self.loop(provider, synthesis or self.bridge())
        self.settle(thread)
        return provider

    def publish(self, route_set_: RouteSet, uuid: str = UUID) -> None:
        self.services.event_bus.publish(SynthesisRouteReady(molecule_uuid=uuid, route_set=route_set_))
        QApplication.processEvents()


@pytest.fixture
def rig(tmp_path, qapp):
    built = []

    def make(host=None, services=None):
        item = Rig(tmp_path, host or Host(), services)
        built.append(item)
        return item

    yield make
    for item in built:
        for plugin_id in list(item.manager.loaded_plugin_ids):
            item.manager.unload(plugin_id)


def told(provider) -> list[str]:
    """What the tools answered the model, in order."""
    return [m.content for m in provider.stream_calls[1].messages if m.role == "tool"]


def told_json(provider) -> dict:
    (text,) = told(provider)
    return json.loads(text)


# --- the definitions -----------------------------------------------------------------------------------------------------------------------------------


def test_the_two_tools_are_well_formed_and_collide_with_no_other_tool():
    names = [t.name for t in SYNTHESIS_TOOLS]
    assert names == ["plan_synthesis", "read_synthesis_plan"] and set(SYNTHESIS_HANDLERS) == set(names)
    assert not set(names) & {t.name for t in AVAILABLE_TOOLS}
    assert validate_arguments(PLAN_SYNTHESIS.input_schema, {}) == [], "it takes nothing"
    assert validate_arguments(PLAN_SYNTHESIS.input_schema, {"smiles": "CCO"}), "a model cannot name another molecule"
    assert validate_arguments(READ_SYNTHESIS_PLAN.input_schema, {}) == [] and validate_arguments(READ_SYNTHESIS_PLAN.input_schema, {"route": 2}) == []
    assert validate_arguments(READ_SYNTHESIS_PLAN.input_schema, {"route": -1}) and validate_arguments(READ_SYNTHESIS_PLAN.input_schema, {"route": "1"})


def test_the_descriptions_say_what_the_model_cannot_do_and_what_a_route_is_not():
    ask, read = PLAN_SYNTHESIS.description, READ_SYNTHESIS_PLAN.description
    assert "CANNOT start" in ask and "Approve" in ask and "regulatory check" in ask and "no arguments" in ask
    assert "hypothesis" in read and "do not supply them" in read and "not a yield" in read and "'null' means not provided" in read and "not clearance" in read
    assert "plan_synthesis" in SYSTEM_PROMPT_PREFIX and "read_synthesis_plan" in SYSTEM_PROMPT_PREFIX and "must not supply" in SYSTEM_PROMPT_PREFIX


# --- which object the tool is handed --------------------------------------------------------------------------------------------------------------------


def test_the_bridge_a_tool_receives_has_no_way_to_start_stop_or_configure_a_plan():
    assert {name for name in dir(SynthesisBridge) if not name.startswith("_")} == {"available", "turn", "plan_synthesis", "read_synthesis_plan"}
    for name in ("request_plan", "cancel", "choose", "approve", "synthesis_requests"):
        assert not hasattr(PluginSynthesis, name), name
    bridge = SynthesisBridge(PluginSynthesis(Host()), None)
    assert not any(isinstance(value, PluginSynthesisRequests) for value in vars(bridge).values())
    assert isinstance(vars(bridge)["_synthesis"], PluginSynthesis) and not isinstance(vars(bridge)["_synthesis"], PluginSynthesisRequests)


def test_the_panel_hands_the_tools_the_reading_handle_and_keeps_the_starting_one(rig):
    world = rig()
    synthesis = world.bridge()
    assert type(vars(synthesis)["_synthesis"]) is PluginSynthesis
    assert type(world.panel._context.synthesis_requests) is PluginSynthesisRequests


# --- unavailable ------------------------------------------------------------------------------------------------------------------------------------------------


def test_a_bridge_with_no_host_or_no_molecule_says_unavailable_and_never_raises(rig):
    no_host = SynthesisBridge(PluginSynthesis(None), None)
    assert no_host.available is False
    for text in (no_host.plan_synthesis(), no_host.read_synthesis_plan(), no_host.read_synthesis_plan(2)):
        data = json.loads(text)
        assert data["ok"] is False and data["problem"] == "unavailable"
    host = Host()
    host.target_value = None
    nothing = rig(host).bridge()
    assert nothing.available is False and json.loads(nothing.plan_synthesis())["problem"] == "unavailable"
    assert begin_synthesis_turn(PluginSynthesis(host)) is None


# --- asking: a card, and nothing started ------------------------------------------------------------------------------------------------------------------


def test_asking_leaves_a_request_for_the_person_and_starts_nothing(rig):
    world = rig()
    events: list[BridgeEvent] = []
    reply = json.loads(world.bridge(events).plan_synthesis())
    assert reply["ok"] is True and reply["started"] is False and reply["state"] == "awaiting_approval"
    assert "nothing has started" in reply["message"] and "do not state or guess any route" in reply["message"] and "do not say it was started" in reply["message"]
    (event,) = events
    assert event.kind == "synthesis_proposed" and event.run_id == card_key(UUID) and event.molecule == "Aspirin"
    assert event.preparation == {
        "molecule_uuid": UUID, "name": "Aspirin", "smiles": ASPIRIN, "planner_version": "4.4.1", "expansion": "uspto", "stock": "zinc", "filter": "none",
    }
    assert [call for call in world.host.calls if call[0] == "request_plan"] == [], "asking is not starting"


def test_the_request_card_is_drawn_from_the_applications_record_as_plain_text(rig):
    world = rig()
    world.ask(_call("plan_synthesis"))
    (key,) = world.panel.pending_synthesis_keys()
    card = world.panel._synthesis_cards[key]
    assert key == card_key(UUID) and card.body.textFormat() == Qt.TextFormat.PlainText
    text = card.body.text()
    assert "Aspirin" in text and f"Structure: {ASPIRIN}" in text and "policy uspto, stock zinc, filter none" in text and "regulatory check" in text and "Nothing starts unless you approve" in text
    assert card.approve_button.text() == "Approve" and card.cancel_button.text() == "Cancel"
    assert any("synthesis plan on Aspirin: waiting for your approval" in line for line in world.panel.ledger_lines())
    assert [c for c in world.host.calls if c[0] == "request_plan"] == []
    assert not world.panel._cards_host.isHidden(), "the strip of cards shows while a request waits"
    assert card_lines({"name": "n", "smiles": "s"})[2].count("not chosen") == 2, "a missing choice is said, not blank"


def test_asking_twice_is_one_card(rig):
    world = rig()
    world.ask(_call("plan_synthesis"))
    world.ask(_call("plan_synthesis"))
    assert world.panel.pending_synthesis_keys() == [card_key(UUID)]
    assert sum("waiting for your approval" in line for line in world.panel.ledger_lines()) == 1
    assert world.panel._cards_layout.count() == 1, "a second card on screen would be one the person could press twice"


def test_a_planner_that_is_not_set_up_leaves_no_card_and_does_not_send_the_local_message(rig):
    host = Host()
    host.options_value = dataclasses.replace(OPTIONS, ok=False, problem=SECRET_REASON)
    world = rig(host)
    provider = world.ask(_call("plan_synthesis"))
    data = told_json(provider)
    assert data["ok"] is False and data["problem"] == "planner_not_set_up" and "External Tools" in data["message"]
    assert SECRET_REASON not in json.dumps(data) and "SENTINEL" not in json.dumps(data), "a path on the user's machine is not for the provider"
    assert world.panel.pending_synthesis_keys() == []
    assert any("synthesis plan on Aspirin: not started" in line and "SENTINEL-REASON" in line for line in world.panel.ledger_lines()), "the person is told why"


def test_a_stored_current_plan_is_read_not_asked_for_again(rig):
    for status in (RouteStatus.FOUND, RouteStatus.NO_ROUTE):
        host = Host()
        host.results[UUID] = bound(route_set(status))
        world = rig(host)
        events: list = []
        data = json.loads(world.bridge(events).plan_synthesis())
        assert data["state"] == "plan_exists" and "read_synthesis_plan" in data["message"] and events == []


def test_a_plan_that_failed_or_is_for_an_earlier_structure_does_not_stop_a_new_request(rig):
    for stored in (bound(route_set(RouteStatus.FAILED)), bound(route_set(), current=False), bound(route_set(RouteStatus.REFUSED))):
        host = Host()
        host.results[UUID] = stored
        events: list = []
        data = json.loads(rig(host).bridge(events).plan_synthesis())
        assert data["state"] == "awaiting_approval" and len(events) == 1


def test_a_search_already_running_is_not_asked_for_again(rig):
    host = Host()
    host.planning.add(UUID)
    events: list = []
    assert json.loads(rig(host).bridge(events).plan_synthesis())["state"] == "already_running" and events == []
    later = Host()
    world = rig(later)
    bridge = world.bridge(events)
    later.planning.add(UUID)  # started by the person AFTER Send: the live flag is read too
    assert json.loads(bridge.plan_synthesis())["state"] == "already_running" and events == []


# --- the person decides -------------------------------------------------------------------------------------------------------------------------------------


def test_approve_asks_the_service_once_and_only_then(rig):
    world = rig()
    world.ask(_call("plan_synthesis"))
    assert [c for c in world.host.calls if c[0] == "request_plan"] == []
    world.panel._synthesis_cards[card_key(UUID)].approve_button.click()
    QApplication.processEvents()
    assert [c for c in world.host.calls if c[0] == "request_plan"] == [("request_plan", UUID, "the assistant, approved by the user")]
    assert world.panel.pending_synthesis_keys() == [] and world.panel._cards_host.isHidden(), "the strip goes when the last card does"
    assert any("synthesis plan on Aspirin: searching" in line for line in world.panel.ledger_lines())
    assert world.panel._notes == [], "nothing to tell the model until the search ends"


def test_cancel_starts_nothing_and_the_model_is_told_with_the_next_message(rig):
    world = rig()
    world.ask(_call("plan_synthesis"))
    world.panel._synthesis_cards[card_key(UUID)].cancel_button.click()
    QApplication.processEvents()
    assert [c for c in world.host.calls if c[0] == "request_plan"] == [] and world.panel.pending_synthesis_keys() == []
    (note,) = world.panel._notes
    assert note.startswith("[Application note]") and "cancelled by the user" in note and "Nothing was started" in note
    assert any("cancelled; nothing was started" in line for line in world.panel.ledger_lines())


def test_an_edited_structure_is_not_planned_under_an_approval_given_for_the_old_one(rig):
    world = rig()
    world.ask(_call("plan_synthesis"))
    world.host.structures[UUID] = dataclasses.replace(TARGET, canonical_smiles=SALICYLIC)
    world.panel._synthesis_cards[card_key(UUID)].approve_button.click()
    QApplication.processEvents()
    assert [c for c in world.host.calls if c[0] == "request_plan"] == []
    (note,) = world.panel._notes
    assert "structure changed" in note and "was not started" in note and world.panel._synthesis_awaiting == {}


def test_a_molecule_removed_before_approval_is_not_planned(rig):
    world = rig()
    world.ask(_call("plan_synthesis"))
    world.host.structures.clear()
    world.panel._synthesis_cards[card_key(UUID)].approve_button.click()
    QApplication.processEvents()
    assert [c for c in world.host.calls if c[0] == "request_plan"] == [] and "structure changed" in world.panel._notes[0]


@pytest.mark.parametrize("outcome, wanted", [(RequestOutcome.ALREADY_RUNNING, "already running"), (RequestOutcome.REJECTED, "was not started")])
def test_a_request_the_service_would_not_take_is_told_as_not_started_and_awaits_nothing(rig, outcome, wanted):
    host = Host()
    host.outcome = outcome
    world = rig(host)
    world.ask(_call("plan_synthesis"))
    world.panel._synthesis_cards[card_key(UUID)].approve_button.click()
    QApplication.processEvents()
    assert wanted in world.panel._notes[0] and world.panel._synthesis_awaiting == {}


# --- what the model is told when a search ends ---------------------------------------------------------------------------------------------------------------


def started_world(rig, host=None):
    world = rig(host)
    world.ask(_call("plan_synthesis"))
    world.panel._synthesis_cards[card_key(UUID)].approve_button.click()
    QApplication.processEvents()
    return world


def test_routes_found_are_told_with_the_application_words_and_a_pointer_to_the_reading_tool(rig):
    world = started_world(rig)
    world.publish(route_set())
    (note,) = world.panel._notes
    assert note.startswith("[Application note]") and "2 routes found." in note and "read_synthesis_plan" in note and "not a validated synthesis" in note
    assert any("synthesis plan on Aspirin: routes found" in line for line in world.panel.ledger_lines()) and world.panel._synthesis_awaiting == {}
    assert "Synthesis plan for Aspirin: routes found." in world.panel._transcript.toPlainText()


def test_a_plan_the_gate_declined_is_told_in_fixed_words_and_never_the_reason(rig):
    for status in (RouteStatus.REFUSED, RouteStatus.UNSCREENED):
        world = started_world(rig)
        world.publish(route_set(status, reason=f"{SENTINEL} {SECRET_REASON}"))
        (note,) = world.panel._notes
        assert GATE_DECLINED in note and f"status '{status.value}'" in note
        everything = note + "\n".join(world.panel.ledger_lines()) + world.panel._transcript.toPlainText()
        assert "SENTINEL" not in everything and "D:\\Users" not in everything


def test_a_failed_search_is_told_as_a_status_and_never_the_planners_message(rig):
    for status in (RouteStatus.FAILED, RouteStatus.UNAVAILABLE, RouteStatus.CANCELLED):
        world = started_world(rig)
        world.publish(route_set(status, reason=SECRET_REASON))
        (note,) = world.panel._notes
        assert f"status '{status.value}'" in note and "There are no routes to read" in note and "SENTINEL" not in note and "someone" not in note


def test_a_search_the_person_started_themselves_is_not_the_assistants_to_report(rig):
    world = rig()
    world.publish(route_set())
    assert world.panel._notes == [] and world.panel.ledger_lines() == []


def test_a_second_ending_is_not_told_twice(rig):
    world = started_world(rig)
    world.publish(route_set())
    world.publish(route_set())
    assert len(world.panel._notes) == 1


# --- reading ----------------------------------------------------------------------------------------------------------------------------------------------------


def read(rig, host, *calls, **kw):
    world = rig(host)
    provider = world.ask(*(calls or (_call("read_synthesis_plan"),)))
    return told_json(provider)


def test_with_no_plan_the_model_is_told_there_is_none_and_how_to_ask(rig):
    data = read(rig, Host())
    assert data["has_plan"] is False and "plan_synthesis" in data["message"]
    busy = Host()
    busy.planning.add(UUID)
    data = read(rig, busy)
    assert data["planning"] is True and "running" in data["message"]


def test_the_summary_lists_every_route_with_its_own_checks_and_the_standing_limitations(rig):
    plan = screened(route_set())
    host = Host()
    host.results[UUID] = bound(plan)
    data = read(rig, host)
    assert data["status"] == "found" and data["current"] is True and data["message"] == plan.message() and data["planner"] == plan.planner.label()
    assert data["limitations"] == list(plan.all_limitations()) and len(data["limitations"]) >= 5
    assert data["how_to_read"] == HOW_TO_READ
    first, second = data["routes"]
    assert (first["route"], first["steps"], first["starting_materials"], first["score"]) == (1, 1, 2, 0.9876) and second["steps"] == 2
    assert first["consistency"] == {"checked": False}, "a route nobody checked says so"
    assert first["molecules_with_alert"] == 1 and first["molecules_not_screened"] == 0 and first["alerts_checked"] is True
    assert "next" in data


def test_a_route_is_read_in_full_with_steps_in_the_order_they_would_run_and_missing_fields_as_null(rig):
    plan = route_set()
    host = Host()
    host.results[UUID] = bound(plan)
    data = read(rig, host, _call("read_synthesis_plan", route=2))
    detail = data["detail"]
    assert [s["makes"] for s in detail["steps_in_the_order_they_would_be_run"]] == [step.product for step in plan.routes[1].steps]
    first_route = read(rig, host, _call("read_synthesis_plan", route=1))["detail"]
    (step,) = first_route["steps_in_the_order_they_would_be_run"]
    assert step["from"] == [ANHYDRIDE, SALICYLIC] and step["template_id"] == "t1" and step["policy_probability"] == 0.5
    assert step["policy_name"] is None and step["reaction_smiles"] is None, "a field the planner did not supply is null, not zero or an empty string"
    assert first_route["starting_materials"] == [{"smiles": ANHYDRIDE, "in_stock": True}, {"smiles": SALICYLIC, "in_stock": None}]
    assert first_route["regulatory_alerts"] == {"checked": False, "molecules": []}, "never screened is said, not an empty list of alerts"


def test_an_alert_is_given_by_its_rule_and_never_by_the_name_of_the_listing(rig):
    plan = screened(route_set())
    host = Host()
    host.results[UUID] = bound(plan)
    text = told(rig(host).ask(_call("read_synthesis_plan", route=1)))[0]
    assert SENTINEL not in text
    data = json.loads(text)
    alerts = {m["smiles"]: m for m in data["detail"]["regulatory_alerts"]["molecules"]}
    assert alerts[ASPIRIN]["role"] == "target" and alerts[ASPIRIN]["alerts"] == [
        {"rule_id": "test-rule-1", "ruleset_id": "test-ruleset", "domain": "exposure_limit", "jurisdiction": "XX", "section": "s1", "confidence": "exact", "user_supplied": False}
    ]
    assert alerts[ANHYDRIDE]["role"] == "starting_material" and alerts[ANHYDRIDE]["alerts"] == []


def test_a_molecule_that_could_not_be_screened_says_so_and_is_not_an_empty_list(rig):
    plan = screened(route_set(), unscreened=SALICYLIC)
    host = Host()
    host.results[UUID] = bound(plan)
    data = read(rig, host, _call("read_synthesis_plan", route=1))
    molecules = {m["smiles"]: m for m in data["detail"]["regulatory_alerts"]["molecules"]}
    assert molecules[SALICYLIC]["screened"] is False and "alerts" not in molecules[SALICYLIC] and molecules[SALICYLIC]["why_not"]
    summary = read(rig, host)
    assert summary["routes"][0]["molecules_not_screened"] == 1 and any("could not be screened" in line for line in summary["limitations"])


def test_an_unknown_route_is_named_as_such(rig):
    host = Host()
    host.results[UUID] = bound(route_set())
    data = read(rig, host, _call("read_synthesis_plan", route=7))
    assert data["ok"] is False and data["problem"] == "unknown_route" and "1 to 2" in data["message"] and "detail" not in data


def test_a_plan_for_an_earlier_structure_has_no_routes_in_it(rig):
    host = Host()
    host.results[UUID] = bound(screened(route_set()), current=False)
    data = read(rig, host)
    assert data["current"] is False and "EARLIER structure" in data["message"] and "routes" not in data and "detail" not in data
    assert data["limitations"], "the limitations travel even with no routes"


def test_a_plan_with_no_route_says_none_was_found_within_the_limits_and_not_that_none_exists(rig):
    host = Host()
    host.results[UUID] = bound(route_set(RouteStatus.NO_ROUTE))
    data = read(rig, host)
    assert data["status"] == "no_route" and "within the configured search limits" in data["message"] and "does not mean none exists" in data["message"] and "routes" not in data


def test_a_plan_the_gate_declined_or_that_failed_has_no_routes_and_none_of_the_stored_text(rig):
    for status, expected in ((RouteStatus.REFUSED, GATE_DECLINED), (RouteStatus.UNSCREENED, GATE_DECLINED), (RouteStatus.FAILED, None), (RouteStatus.UNAVAILABLE, None), (RouteStatus.CANCELLED, None)):
        host = Host()
        host.results[UUID] = bound(route_set(status, reason=f"{SENTINEL} {SECRET_REASON}"))
        text = told(rig(host).ask(_call("read_synthesis_plan")))[0]
        data = json.loads(text)
        assert "SENTINEL" not in text and "someone" not in text and "routes" not in data and data["status"] == status.value, status
        if expected is not None:
            assert data["message"] == expected
        else:
            assert status.value in data["message"] and "no routes" in data["message"]
        assert data["limitations"], "the standing limitations travel with every plan, refused or not"


def test_a_very_long_plan_is_shortened_to_the_budget_and_never_loses_a_route_or_a_limitation(rig):
    base = route_set()
    report = ValidationReport(
        molecules=Check.PASS, reactions=Check.PASS, mapping=MappingStatus.ABSENT, conservation=Check.NOT_ASSESSABLE, stock=StockStatus.ALL_IN_STOCK,
        diagnostics=tuple(f"step {n}: a diagnostic sentence that is long enough to matter when forty routes carry four of them" for n in range(4)),
    )
    many = tuple(dataclasses.replace(base.routes[1], rank=n, validation=report) for n in range(1, 41))
    plan = dataclasses.replace(base, routes=many)
    host = Host()
    host.results[UUID] = bound(plan)
    text = told(rig(host).ask(_call("read_synthesis_plan")))[0]
    data = json.loads(text)
    assert len(text) <= REPLY_BUDGET and data["shortened_for_length"] is True and len(data["routes"]) == 40 and data["limitations"]
    full = json.dumps(plan_envelope(TARGET, bound(plan), 0, 0))
    assert len(full) > REPLY_BUDGET, "the test plan really was over budget at full detail"
    one = json.loads(told(rig(host).ask(_call("read_synthesis_plan", route=3)))[0])
    assert one["detail"]["route"] == 3 and "shortened_for_length" not in one


def test_what_is_read_is_the_plan_as_it_was_when_the_turn_began(rig):
    host = Host()
    host.results[UUID] = bound(route_set())
    world = rig(host)
    bridge = world.bridge()
    host.results[UUID] = bound(route_set(RouteStatus.NO_ROUTE))
    host.target_value = dataclasses.replace(TARGET, molecule_uuid="another", display_name="Other")
    assert json.loads(bridge.read_synthesis_plan())["status"] == "found"
    assert bridge.turn.target.molecule_uuid == UUID and isinstance(bridge.turn, SynthesisTurn)


# --- the loop --------------------------------------------------------------------------------------------------------------------------------------------------


def test_the_synthesis_tools_are_offered_only_with_a_reachable_molecule_and_a_provider_that_takes_tools(rig):
    seen: list = []

    class Recorder(_StubToolProvider):
        def stream(self, request, on_chunk, tools=None):
            seen.append([t.name for t in tools] if tools is not None else None)
            return AIResponse(text="ok")

    host = Host()
    world = rig(host)
    thread, _ = world.loop(Recorder([]), world.bridge())
    world.settle(thread)
    assert seen[0] == [t.name for t in AVAILABLE_TOOLS] + ["plan_synthesis", "read_synthesis_plan"], "no calculator host here, so only the synthesis tools join the older two"

    host.target_value = None
    thread, _ = world.loop(Recorder([]), world.bridge())
    world.settle(thread)
    assert seen[1] == [t.name for t in AVAILABLE_TOOLS]

    thread, _ = world.loop(Recorder([]), None)
    world.settle(thread)
    assert seen[2] == [t.name for t in AVAILABLE_TOOLS]

    class NoTools(Recorder):
        supports_tools = False

    host.target_value = TARGET
    thread, _ = world.loop(NoTools([]), world.bridge())
    world.settle(thread)
    assert seen[3] is None


def test_a_bad_call_never_reaches_the_tool(rig):
    world = rig()
    provider = world.ask(_call("plan_synthesis", smiles="CCO"))
    (message,) = told(provider)
    assert "was not run" in message and "'smiles' is not an argument" in message
    assert world.panel.pending_synthesis_keys() == []


def test_without_a_synthesis_bridge_the_tool_says_it_is_unavailable_and_does_nothing(rig):
    world = rig()
    answer = world.panel._execute_tool(ToolCall(id="t", name="plan_synthesis", input={}), None, None)
    assert json.loads(answer)["problem"] == "unavailable" and world.panel.pending_synthesis_keys() == []


def test_the_privacy_note_says_a_plan_the_assistant_reads_leaves_the_machine(rig):
    world = rig()
    note = world.panel.privacy_note()
    assert "synthesis plan" in note


# --- the real host and service under the panel ------------------------------------------------------------------------------------------------------------


class ReadyHost(RealHost):
    """The real host, over the real service, with the planner's configuration answered as set up, so the request gets as far as a card."""

    def options(self):
        return OPTIONS


@pytest.fixture(autouse=True)
def _fresh_gate():
    gate_module.reset_gate_engine()
    yield
    gate_module.reset_gate_engine()


def real_rig(rig, tmp_path, qapp, smiles=ASPIRIN):
    world = RealWorld(tmp_path, qapp)
    model = world.add(smiles, "Target")
    host = ReadyHost(world.services, world.session, world.settings)
    return rig(host, world.services), world, model


def refused_gate(smiles):
    return GateDecision(
        outcome=GateOutcome.REFUSED, matches=(GateMatch(ruleset_id="cwc-schedule-1", rule_id="test-rule", display_name=SENTINEL),), reason=f"{SECRET_REASON} matched {SENTINEL}",
        ruleset_version="1", ruleset_sha256="x", screened_on="today",
    )


def test_an_approved_request_for_a_target_the_gate_refuses_starts_no_process_and_the_model_is_not_told_why(rig, tmp_path, qapp, monkeypatch):
    world, real, model = real_rig(rig, tmp_path, qapp)
    real.services.synthesis_planning_service._gate = refused_gate
    started = []
    real_popen = planner_host.subprocess.Popen
    monkeypatch.setattr(planner_host.subprocess, "Popen", lambda *a, **k: started.append(a) or real_popen(*a, **k))

    provider = world.ask(_call("plan_synthesis"))
    assert told_json(provider)["state"] == "awaiting_approval" and world.panel.pending_synthesis_keys() == [card_key(model.uuid)]
    world.panel._synthesis_cards[card_key(model.uuid)].approve_button.click()
    assert pump(lambda: bool(world.panel._notes))

    assert started == [], "the gate spoke inside the service, whoever asked"
    assert real.host.result_for(model.uuid).route_set.status is RouteStatus.REFUSED
    (note,) = world.panel._notes
    assert GATE_DECLINED in note and "status 'refused'" in note
    everything = note + "\n".join(world.panel.ledger_lines()) + world.panel._transcript.toPlainText() + json.dumps(told(provider))
    assert "SENTINEL" not in everything and "D:\\Users" not in everything
    # and the model reading it afterwards is told the same, with the reason still not among the words
    again = world.ask(_call("read_synthesis_plan"), synthesis=world.bridge())
    data = told_json(again)
    assert data["status"] == "refused" and data["message"] == GATE_DECLINED and "SENTINEL" not in json.dumps(data)


def test_an_approved_request_the_gate_allows_but_the_setup_cannot_serve_ends_as_a_status(rig, tmp_path, qapp):
    world, real, model = real_rig(rig, tmp_path, qapp)
    world.ask(_call("plan_synthesis"))
    world.panel._synthesis_cards[card_key(model.uuid)].approve_button.click()
    assert pump(lambda: bool(world.panel._notes))
    (note,) = world.panel._notes
    assert "status 'unavailable'" in note and "Synthesis panel" in note
    assert real.host.result_for(model.uuid).route_set.status is RouteStatus.UNAVAILABLE
