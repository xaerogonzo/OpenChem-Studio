"""The assistant proposes a score and a person decides (slice 4d of `docs/DERIVED_SCORES_DESIGN.md`).

The real host, the plugin's own tools and panel, and a scripted provider on a real worker thread: the properties that matter live in how the pieces meet. A model can PROPOSE (the tool
checks the request by the rules a typed definition meets and leaves a card); it cannot SAVE (a score exists only after the panel's own Approve button is pressed, which a tool is never handed);
and what is saved is exactly the definition that was shown.
"""

from __future__ import annotations

import json
import sys
import threading

import pytest
from ai_assistant.bridge import ToolBridge
from ai_assistant.calculation_tools import CALCULATION_HANDLERS, CALCULATION_TOOLS, LIST_SCORE_OUTPUTS, PROPOSE_SCORE
from ai_assistant.panel import SYSTEM_PROMPT_PREFIX
from ai_assistant.tools import validate_arguments
from PySide6.QtCore import Qt
from test_ai_assistant_bridge import _call, _Rig, _tool_message, _two_step
from test_calculation_host import _World

from openchem.domain.calculator import DRAWING
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.project import ProjectModel
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.score_proposal import ASSISTANT_OWNER, MAX_PENDING, ProposalState
from openchem.plugins.calculation_access import PluginCalculationApprovals, PluginCalculations

_PSA = "descriptor:tpsa"
_LOGP = "descriptor:mol_logp"


def _put(services, model, descriptor_id, value, units=""):
    fingerprint = services.result_store_service.fingerprints_for(model)[DRAWING]
    result = DescriptorValue(descriptor_id, descriptor_id, units, "c", "rdkit", model.uuid, value=value, cache_state=CacheState.COMPLETED)
    services.result_store_service.store.put(StoredResult(ResultIdentity(model.uuid, f"descriptor:rdkit:{descriptor_id}", DRAWING, fingerprint, "rdkit"), result))


def _request(**changes) -> dict:
    base = {
        "label": "Polar window",
        "formula": "ramp(psa, hi, 60) * ramp(logp, 5, 2)",
        "result_unit": "1",
        "inputs": [{"name": "psa", "output": _PSA}, {"name": "logp", "output": _LOGP}],
        "constants": [{"name": "hi", "value": 140, "unit": "Å^2"}],
        "note": "a starting point",
    }
    base.update(changes)
    return base


@pytest.fixture
def rig(qapp, tmp_path):
    built = _Rig(qapp, tmp_path, held=False)
    built.world.services.score_service.set_project(built.world.project)
    _put(built.world.services, built.world.molecule, "tpsa", 63.6, "Å²")
    _put(built.world.services, built.world.molecule, "mol_logp", 1.31)
    return built


def _propose(rig, **changes):
    """One model turn that proposes a score; returns (the tool's JSON, the provider)."""
    provider = _two_step([_call("propose_score", **_request(**changes))])
    thread, _box = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    (message,) = _tool_message(provider)
    return json.loads(message.content) if message.content.startswith("{") else message.content, provider


def _scores(rig):
    return rig.world.services.score_service.store.definitions()


# --- the tool: it proposes, it saves nothing -------------------------------------------------------------------------------------------------


def test_a_proposal_leaves_a_card_for_the_user_and_saves_nothing(rig):
    data, _provider = _propose(rig)
    assert data["ok"] is True and data["state"] == "awaiting_approval" and data["proposal_id"].startswith("score-proposal-") and data["already_waiting"] is False
    assert _scores(rig) == (), "a proposal is not a score"
    assert rig.panel.pending_score_ids() == [data["proposal_id"]]
    assert any("waiting for your approval" in line and "Polar window" in line and "Aspirin" in line for line in rig.panel.ledger_lines())


def test_what_the_model_is_told_says_nothing_is_saved_and_it_cannot_approve_and_never_the_draft_id(rig):
    data, _provider = _propose(rig)
    assert "NOTHING IS SAVED" in data["message"] and "you cannot approve it" in data["message"] and "never that it is saved" in data["message"]
    score = data["score"]
    assert "score_id" not in score and "user.draft" not in json.dumps(data), "the draft's id is not the id it will have"
    assert score["name"] == "Polar window (user-defined, unvalidated)" and score["outcome"] == "computed" and 0.0 < score["data"]["value"] < 1.0
    assert data["owner_if_approved"] == ASSISTANT_OWNER and data["molecule_uuid"] == rig.world.molecule.uuid


def test_the_card_shows_the_definition_as_plain_text_with_the_value_and_who_it_will_say_wrote_it(rig):
    _propose(rig, label="<b>Bold</b> window", note="<img src='x'> why")
    (proposal_id,) = rig.panel.pending_score_ids()
    card = rig.panel._score_cards[proposal_id]
    assert card.body.textFormat() == Qt.TextFormat.PlainText, "text a model wrote is never read as markup"
    text = card.body.text()
    assert "<b>Bold</b> window (user-defined, unvalidated)" in text and "<img src='x'> why" in text
    assert "Formula: ramp(psa, hi, 60) * ramp(logp, 5, 2)" in text and "psa = " in text and "hi = 140 Å^2" in text and "Declared unit: 1" in text
    assert "For Aspirin: 0." in text and ASSISTANT_OWNER in text and "Nothing is saved unless you approve" in text
    assert card.approve_button.text() == "Approve" and card.cancel_button.text() == "Cancel"


def test_the_same_proposal_asked_for_twice_is_one_card(rig):
    first, _ = _propose(rig)
    second, _ = _propose(rig)
    assert second["already_waiting"] is True and second["proposal_id"] == first["proposal_id"]
    assert len(rig.panel.pending_score_ids()) == 1 and len(rig.world.host.pending_scores()) == 1


# --- the person decides ----------------------------------------------------------------------------------------------------------------------------------


def test_pressing_approve_saves_exactly_what_was_shown_with_the_assistant_as_owner(rig):
    data, _ = _propose(rig)
    shown = rig.world.host.pending_scores()[0].definition
    card = rig.panel._score_cards[data["proposal_id"]]
    card.approve_button.click()
    rig.qapp.processEvents()
    (made,) = _scores(rig)
    assert made.score_id == "user.polar_window" and made.label == "Polar window" and made.owner == ASSISTANT_OWNER and made.note == "a starting point"
    assert (made.formula, made.result_unit, made.inputs, made.constants) == (shown.formula, shown.result_unit, shown.inputs, shown.constants)
    assert made.digest == shown.digest and made.created != ""
    assert rig.panel.pending_score_ids() == [] and rig.world.host.pending_scores() == ()
    assert rig.world.host.score_state_of(data["proposal_id"]) is ProposalState.SAVED


def test_an_approved_score_is_read_by_the_user_and_by_the_model_like_any_other(rig):
    _propose(rig)
    rig.panel._score_cards[rig.panel.pending_score_ids()[0]].approve_button.click()
    rig.qapp.processEvents()
    provider = _two_step([_call("read_scores")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    (message,) = _tool_message(provider)
    (score,) = json.loads(message.content)["scores"]
    assert score["name"] == "Polar window (user-defined, unvalidated)" and score["outcome"] == "computed"
    assert "Alex" not in message.content and ASSISTANT_OWNER not in message.content, "the owner is a stored detail the model is not sent"


def test_pressing_cancel_saves_nothing_and_the_model_is_told_with_the_next_message(rig):
    data, _ = _propose(rig)
    rig.panel._score_cards[data["proposal_id"]].cancel_button.click()
    rig.qapp.processEvents()
    assert _scores(rig) == () and rig.panel.pending_score_ids() == []
    assert any("cancelled; nothing was saved" in line for line in rig.panel.ledger_lines())
    (note,) = rig.panel._notes
    assert note.startswith("[Application note]") and "'Polar window'" in note and "cancelled by the user" in note and "Nothing was saved" in note
    assert rig.world.host.score_outcome_of(data["proposal_id"]).state is ProposalState.CANCELLED


def test_an_approval_is_told_to_the_model_with_the_next_message_and_rides_ahead_of_what_the_user_types(rig):
    data, _ = _propose(rig)
    rig.panel._score_cards[data["proposal_id"]].approve_button.click()
    rig.qapp.processEvents()
    (note,) = rig.panel._notes
    assert "was saved after the user approved it" in note and "user.polar_window" in note and "read_scores" in note
    assert any("saved after you approved it" in line for line in rig.panel.ledger_lines())
    rig.panel._input.setPlainText("what does it give?")
    rig.panel._history.clear()
    sent = {}
    panel_module = sys.modules[type(rig.panel).__module__]
    original = panel_module.run_async
    panel_module.run_async = lambda func, *a, **k: sent.update(called=True)
    try:
        rig.panel._on_send_clicked()
    finally:
        panel_module.run_async = original
    last = rig.panel._history[-1]
    assert sent.get("called") and rig.panel._notes == [] and last.content.startswith("[Application note]") and last.content.endswith("what does it give?")


def test_a_decision_is_made_once_and_pressing_again_changes_nothing(rig):
    data, _ = _propose(rig)
    approvals = rig.panel._context.calculation_approvals
    first = approvals.approve_score(data["proposal_id"])
    again = approvals.approve_score(data["proposal_id"])
    assert first.state is ProposalState.SAVED and again == first and len(_scores(rig)) == 1
    assert approvals.cancel_score(data["proposal_id"]) is False and len(_scores(rig)) == 1 and len(rig.panel._notes) == 1


def test_an_approval_in_another_project_saves_nothing_and_says_so(rig):
    data, _ = _propose(rig)
    other = ProjectModel(name="Another")
    rig.world.services.score_service.set_project(other)
    outcome = rig.panel._context.calculation_approvals.approve_score(data["proposal_id"])
    assert outcome.state is ProposalState.VOID and "not the one this score was proposed in" in outcome.message
    assert rig.world.services.score_service.store.definitions() == () and "project changed" in rig.panel._notes[0]


def test_a_proposal_from_a_project_that_was_closed_is_voided_when_the_next_message_is_sent_and_its_card_goes(rig):
    data, _ = _propose(rig)
    other = ProjectModel(name="Another")
    rig.world.session.set_project(other)
    rig.world.services.score_service.set_project(other)
    assert rig.panel.pending_score_ids() == [data["proposal_id"]], "the card waits until the next message, or until Approve is pressed"
    rig.panel._context.calculations.begin_turn()
    rig.qapp.processEvents()
    assert rig.panel.pending_score_ids() == [] and rig.world.host.score_state_of(data["proposal_id"]) is ProposalState.VOID
    assert "project changed" in rig.panel._notes[0] and other.molecules == [] and rig.world.services.score_service.store.definitions() == ()


def test_a_score_the_rules_now_refuse_is_not_saved_and_says_why(rig):
    """Approved after the application gained a calculator whose name the label is now too close to: the same rule that refuses a typed one refuses it here."""
    data, _ = _propose(rig)
    rig.world.register("polar_window", lambda request: None)
    outcome = rig.panel._context.calculation_approvals.approve_score(data["proposal_id"])
    assert outcome.state is ProposalState.FAILED and "could not be saved" in outcome.message and "too close" in outcome.message
    assert _scores(rig) == () and "approved but could not be saved" in rig.panel._notes[0]


# --- the refusals the model fixes --------------------------------------------------------------------------------------------------------


def test_a_request_that_breaks_a_rule_is_refused_in_the_requests_own_terms_with_no_card_and_a_ledger_row(rig):
    data, _ = _propose(rig, formula="psa + logp", constants=[])
    assert data["ok"] is False and data["problem"] == "does_not_check" and data["rule"] == "unit" and data["where"] == "formula" and data["nothing_saved"] is True
    assert "position_in_formula" in data and "correct the request" in data["next"]
    assert rig.panel.pending_score_ids() == [] and _scores(rig) == ()
    assert any("not started" in line and "Polar window" in line for line in rig.panel.ledger_lines())


@pytest.mark.parametrize("label", ["TPSA", "Topological polar surface area", "QED"])
def test_a_label_that_reads_like_a_name_the_application_gives_is_refused(rig, label):
    data, _ = _propose(rig, label=label)
    assert data["ok"] is False and data["where"] == "label" and "too close to" in data["message"] and rig.panel.pending_score_ids() == []


@pytest.mark.parametrize("key", ["owner", "score_id", "schema_version", "on_missing", "defaults", "created"])
def test_a_model_cannot_choose_who_wrote_it_or_the_policy_or_the_format(rig, key):
    provider = _two_step([_call("propose_score", **_request(), **{key: "x"})])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    (message,) = _tool_message(provider)
    assert "was not run" in message.content and key in message.content, "refused by the tool's own schema before the handler"
    assert _scores(rig) == () and rig.panel.pending_score_ids() == []


def test_a_request_with_a_missing_or_mistyped_field_never_reaches_the_handler(rig):
    for arguments in ({"label": "x", "formula": "psa", "result_unit": "1"}, {**_request(), "label": 5}, {**_request(), "inputs": "psa"}):
        provider = _two_step([_call("propose_score", **arguments)])
        thread, _ = rig.loop(provider, rig.bridge())
        rig.settle(thread)
        assert "was not run" in _tool_message(provider)[0].content
    assert rig.panel.pending_score_ids() == []


def test_a_request_shaped_wrongly_inside_is_refused_by_the_proposal_rules(rig):
    data, _ = _propose(rig, inputs=[{"name": "psa", "output": _PSA, "default": 3}])
    assert data["ok"] is False and data["problem"] == "not_a_request" and data["where"] == "inputs"


def test_only_a_few_proposals_wait_at_once_and_the_refusal_says_so(rig):
    for index in range(MAX_PENDING):
        data, _ = _propose(rig, label=f"Blend {chr(97 + index)}")
        assert data["ok"] is True
    data, _ = _propose(rig, label="Blend z")
    assert data["ok"] is False and data["problem"] == "too_many_waiting" and len(rig.panel.pending_score_ids()) == MAX_PENDING


def test_a_project_that_holds_the_most_scores_refuses_a_proposal(rig, monkeypatch):
    from openchem.domain import turn_snapshot

    original = turn_snapshot.build_turn_context

    def build(**kwargs):
        kwargs["scores"] = [object()] * 100
        return original(**kwargs)

    monkeypatch.setattr("openchem.app.calculation_host.build_turn_context", build)
    data, _ = _propose(rig)
    assert data["ok"] is False and data["problem"] == "project_full" and rig.panel.pending_score_ids() == []


# --- the model cannot save, approve or reach what does ------------------------------------------------------------------------------------------


def test_the_tool_facing_handle_and_the_bridge_have_no_call_that_saves_a_score_and_the_approvals_face_has_one_the_tools_never_get():
    tool_side = {name for name in dir(PluginCalculations) if not name.startswith("_")} | {name for name in dir(ToolBridge) if not name.startswith("_")}
    assert not any(word in name for name in tool_side for word in ("approve", "cancel", "create", "update", "remove", "save", "write", "delete", "define"))
    assert "approve_score" in dir(PluginCalculationApprovals) and "approve_score" not in tool_side
    assert not hasattr(ToolBridge, "approve_score")


def test_proposing_never_changes_the_projects_scores_whatever_the_model_asks(rig):
    before = _scores(rig)
    for index in range(3):
        _propose(rig, label=f"Blend {chr(97 + index)}")
    _propose(rig, label="TPSA")
    _propose(rig, formula="((")
    assert _scores(rig) == before == ()


def test_the_tools_are_offered_with_the_others_and_have_handlers():
    names = [tool.name for tool in CALCULATION_TOOLS]
    assert PROPOSE_SCORE in CALCULATION_TOOLS and LIST_SCORE_OUTPUTS in CALCULATION_TOOLS and len(names) == len(set(names)) == len(CALCULATION_HANDLERS) == 8
    assert "propose_score" in CALCULATION_HANDLERS and "list_score_outputs" in CALCULATION_HANDLERS
    assert validate_arguments(LIST_SCORE_OUTPUTS.input_schema, {}) == [] and validate_arguments(LIST_SCORE_OUTPUTS.input_schema, {"x": 1})
    assert validate_arguments(PROPOSE_SCORE.input_schema, _request()) == []


def test_the_description_tells_the_model_what_it_may_do_and_say():
    text = PROPOSE_SCORE.description
    for phrase in (
        "You CANNOT save it", "nothing is saved unless they approve", "Never say it is saved", "list_score_outputs", "never invent", "never a prediction",
        "unvalidated", "never converted", "'CNS MPO'", "At most 5", "ramp(x, bad, good)",
    ):
        assert phrase.lower() in text.lower() or phrase.lower() in LIST_SCORE_OUTPUTS.description.lower(), phrase


def test_the_system_prompt_says_a_model_can_suggest_a_score_and_the_person_decides():
    assert "propose_score" in SYSTEM_PROMPT_PREFIX and "only if the person approves" in SYSTEM_PROMPT_PREFIX and "cannot approve for them" in SYSTEM_PROMPT_PREFIX


def test_the_outputs_a_score_may_read_are_listed_with_their_units_and_endpoints(rig):
    provider = _two_step([_call("list_score_outputs")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    data = json.loads(_tool_message(provider)[0].content)
    by_id = {entry["output_id"]: entry for entry in data["outputs"]}
    assert len(by_id) == 21 and by_id[_PSA]["unit"] == "Å^2" and by_id[_PSA]["endpoint"] == "polar_surface_area" and by_id[_LOGP]["unit"] == "1"
    assert "never converted" in data["note"].lower() or "never converted" in data["note"] or "Units are never converted" in data["note"]
    assert data["left_out_for_length"] == 0


def test_a_bridge_with_no_molecule_says_unavailable_for_a_proposal(qapp):
    bridge = ToolBridge(PluginCalculations(None), None)
    data = json.loads(bridge.propose_score(_request()))
    assert data["ok"] is False and data["problem"] == "unavailable"


def test_a_host_with_no_score_service_refuses_a_proposal_and_stores_nothing(rig):
    rig.world.services.score_service = None
    data, _ = _propose(rig)
    assert data["ok"] is False and data["problem"] == "no_project" and rig.panel.pending_score_ids() == []


def test_a_plugin_context_with_no_host_refuses_and_decides_nothing():
    handle = PluginCalculations(None)
    refusal = handle.propose_score(None, _request())
    assert refusal.problem.value == "no_project"
    approvals = PluginCalculationApprovals(None)
    assert approvals.pending_scores() == () and approvals.approve_score("x") is None and approvals.cancel_score("x") is False
    assert approvals.score_state_of("x") is None and approvals.score_outcome_of("x") is None
    approvals.on_score_finished(lambda outcome: None)


def test_deciding_a_proposal_from_another_thread_is_refused_and_changes_nothing(rig):
    data, _ = _propose(rig)
    errors = []

    def decide(action):
        try:
            action()
        except RuntimeError as exc:
            errors.append(str(exc))

    for action in (lambda: rig.world.host.approve_score(data["proposal_id"]), lambda: rig.world.host.cancel_score(data["proposal_id"])):
        worker = threading.Thread(target=decide, args=(action,))
        worker.start()
        worker.join()
    assert len(errors) == 2 and all("GUI thread" in error for error in errors)
    assert rig.world.host.score_state_of(data["proposal_id"]) is ProposalState.PENDING and _scores(rig) == ()


def test_proposals_from_many_worker_threads_at_once_neither_exceed_the_limit_nor_save_anything(rig):
    calculations = rig.panel._context.calculations
    turn = calculations.begin_turn()
    results = []

    def propose(index):
        results.append(calculations.propose_score(turn, _request(label=f"Blend {chr(97 + index // 26)}{chr(97 + index % 26)}")))

    threads = [threading.Thread(target=propose, args=(i,)) for i in range(30)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    waiting = rig.world.host.pending_scores()
    assert len(waiting) == MAX_PENDING and sum(1 for r in results if hasattr(r, "proposal")) == MAX_PENDING and _scores(rig) == ()
