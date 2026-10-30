"""The assistant reads the user's scores, and cannot write one (slice 4 of `docs/DERIVED_SCORES_DESIGN.md`).

The real host (so `begin_turn` captures the definitions the window holds), the plugin's own tool and bridge, and a scripted provider on a real worker thread: the properties that matter
(the turn is frozen, the model reads and cannot write, a refusal reaches the model as a refusal) live in how the pieces meet.
"""

from __future__ import annotations

import json

import pytest
from ai_assistant.bridge import REPLY_BUDGET, ToolBridge
from ai_assistant.calculation_tools import CALCULATION_HANDLERS, CALCULATION_TOOLS, READ_SCORES
from ai_assistant.panel import SYSTEM_PROMPT_PREFIX
from ai_assistant.tools import validate_arguments
from test_ai_assistant_bridge import _call, _Rig, _tool_message, _two_step
from test_calculation_host import _World

from openchem.domain.calculator import DRAWING
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.plugins.calculation_access import PluginCalculations

_PSA = "descriptor:tpsa"
_LOGP = "descriptor:mol_logp"
_UNITS = "Å²"


def _put(services, model, descriptor_id, value, units=""):
    fingerprint = services.result_store_service.fingerprints_for(model)[DRAWING]
    result = DescriptorValue(descriptor_id, descriptor_id, units, "c", "rdkit", model.uuid, value=value, cache_state=CacheState.COMPLETED)
    services.result_store_service.store.put(StoredResult(ResultIdentity(model.uuid, f"descriptor:rdkit:{descriptor_id}", DRAWING, fingerprint, "rdkit"), result))


def _make(world, **changes):
    arguments = dict(
        label="Window", formula="ramp(psa, 140, 60) * ramp(logp, 5, 2)", result_unit="1", inputs=[("psa", _PSA), ("logp", _LOGP)], owner="Alex", note="my private note"
    )
    arguments.update(changes)
    return world.services.score_service.create(**arguments)


@pytest.fixture
def world(qapp):
    built = _World(qapp, held=False)
    built.services.score_service.set_project(built.project)
    return built


# --- the host freezes the definitions with the results --------------------------------------------------------------------------------------


def test_a_turn_holds_the_scores_the_project_had_when_it_began(world):
    made = _make(world)
    turn = world.host.begin_turn()
    assert turn.scores == (made,) and isinstance(turn.scores, tuple)


def test_a_score_made_or_edited_or_removed_after_the_turn_began_changes_nothing_about_it(world):
    made = _make(world)
    turn = world.host.begin_turn()
    world.services.score_service.update(made.score_id, formula="ramp(psa, 100, 60)", inputs=[("psa", _PSA)], constants=[])
    _make(world, label="Another")
    world.services.score_service.remove(made.score_id)
    assert turn.scores == (made,) and [v.definition for v in PluginCalculations(None).read_scores(turn).values] == [made]
    later = world.host.begin_turn()
    assert [d.label for d in later.scores] == ["Another"]


def test_a_stranger_projects_scores_are_never_frozen_into_this_projects_turn(world):
    from openchem.domain.project import ProjectModel

    _make(world)
    stranger = ProjectModel(name="Another")
    world.services.score_service.set_project(stranger)
    world.services.score_service.create(label="Stranger", formula="psa", result_unit="Å^2", inputs=[("psa", _PSA)])
    assert len(world.services.score_service.store) == 1
    assert world.host.begin_turn().scores == (), "the service held another project's scores, and this project's turn must not read them"


def test_a_host_with_no_score_service_gives_a_turn_with_no_scores(world):
    world.services.score_service = None
    assert world.host.begin_turn().scores == ()


def test_a_project_with_no_scores_gives_a_turn_with_none(world):
    assert world.host.begin_turn().scores == ()


def test_the_score_service_holding_another_project_gives_a_turn_no_scores(world):
    _make(world)
    from openchem.domain.project import ProjectModel

    world.services.score_service.set_project(ProjectModel(name="Another"))
    assert world.host.begin_turn().scores == ()


def test_reading_scores_needs_no_host_and_there_is_no_call_that_writes_one(world):
    _make(world)
    turn = world.host.begin_turn()
    handle = PluginCalculations(None)
    assert len(handle.read_scores(turn).values) == 1 and handle.read_scores(turn, ["ghost"]).not_found == ("ghost",)
    public = {name for name in dir(PluginCalculations) if not name.startswith("_")}
    assert not any(word in name for name in public for word in ("create", "update", "remove", "write", "define", "delete", "save"))


# --- the tool ------------------------------------------------------------------------------------------------------------------------------


def test_the_tool_is_offered_with_the_others_and_has_a_handler_that_takes_the_bridge():
    assert READ_SCORES in CALCULATION_TOOLS and "read_scores" in CALCULATION_HANDLERS and len(CALCULATION_TOOLS) == len(CALCULATION_HANDLERS) == 9
    assert validate_arguments(READ_SCORES.input_schema, {}) == []
    assert validate_arguments(READ_SCORES.input_schema, {"scores": ["user.window", "Another"]}) == []
    assert validate_arguments(READ_SCORES.input_schema, {"scores": "user.window"}) and validate_arguments(READ_SCORES.input_schema, {"scores": [1]})
    assert validate_arguments(READ_SCORES.input_schema, {"molecule": "x"}), "a model cannot name another molecule"


def test_the_description_tells_the_model_what_a_score_is_and_what_it_must_not_do():
    text = READ_SCORES.description
    for phrase in (
        "user-defined, unvalidated", "not a prediction", "never state a value", "treat it as zero", "CURRENT results",
        "cannot create, change or delete a score", "Tools > Derived Scores", "read_results never shows one", "not_found",
    ):
        assert phrase in text, phrase


def test_the_system_prompt_names_the_tool_and_what_it_is_not():
    assert "read_scores" in SYSTEM_PROMPT_PREFIX and "not predictions" in SYSTEM_PROMPT_PREFIX and "only if the person approves" in SYSTEM_PROMPT_PREFIX


def test_a_bridge_with_no_molecule_says_unavailable_for_scores_too(qapp):
    bridge = ToolBridge(PluginCalculations(None), None)
    data = json.loads(bridge.read_scores())
    assert data["ok"] is False and data["problem"] == "unavailable"


def test_the_bridge_has_no_way_to_write_a_score():
    surface = {name for name in dir(ToolBridge) if not name.startswith("_")}
    assert "read_scores" in surface and not any(word in name for name in surface for word in ("create", "update", "remove", "define", "delete", "save", "write"))


# --- a scripted provider on a real worker thread ---------------------------------------------------------------------------------------------


@pytest.fixture
def rig(qapp, tmp_path):
    built = _Rig(qapp, tmp_path, held=False)
    built.world.services.score_service.set_project(built.world.project)
    return built


def _read(rig, **arguments):
    provider = _two_step([_call("read_scores", **arguments)])
    thread, box = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    (message,) = _tool_message(provider)
    return json.loads(message.content), provider, box


def test_a_model_that_asks_gets_every_score_with_its_value_label_and_inputs(rig):
    _put(rig.world.services, rig.world.molecule, "tpsa", 63.6, _UNITS)
    _put(rig.world.services, rig.world.molecule, "mol_logp", 1.31)
    _make(rig.world)
    data, _provider, box = _read(rig)
    (score,) = data["scores"]
    assert score["name"] == "Window (user-defined, unvalidated)" and score["outcome"] == "computed" and 0.0 < score["data"]["value"] < 1.0
    assert [i["state"] for i in score["inputs"]] == ["read", "read"] and score["freshness"] == "current"
    assert data["molecule_uuid"] == rig.world.molecule.uuid and box["response"].text == "Done."


def test_a_score_nobody_has_calculated_inputs_for_reaches_the_model_as_a_refusal_with_no_number(rig):
    _make(rig.world)
    data, _provider, _box = _read(rig)
    (score,) = data["scores"]
    assert score["outcome"] == "refused" and "data" not in score and set(score["refusal"]["inputs_not_read"]) == {"psa", "logp"}
    assert "has not been calculated for this molecule" in score["refusal"]["reason"]


def test_a_model_names_a_score_by_label_and_one_that_does_not_exist_is_reported(rig):
    _make(rig.world)
    data, _provider, _box = _read(rig, scores=["window", "Imaginary"])
    assert [s["score_id"] for s in data["scores"]] == ["user.window"] and data["not_found"] == ["Imaginary"]


def test_a_project_without_scores_says_so_and_does_not_invent_one(rig):
    data, _provider, _box = _read(rig)
    assert data["scores"] == [] and data["defined_in_this_project"] == 0


def test_a_long_list_of_scores_is_cut_to_the_reply_budget_and_says_so(rig):
    for index in range(40):
        _make(rig.world, label=f"Blend {chr(97 + index // 26)}{chr(97 + index % 26)}")
    text = rig.bridge().read_scores()
    data = json.loads(text)
    assert len(text) <= REPLY_BUDGET, "a reply is read in full on every later request"
    assert data["shortened_for_length"] is True and 0 < len(data["scores"]) < 40
    assert data["left_out_for_length"] == 40 - len(data["scores"]) and data["defined_in_this_project"] == 40


def test_bad_arguments_never_reach_the_tool(rig):
    provider = _two_step([_call("read_scores", scores="not a list")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    (message,) = _tool_message(provider)
    assert "was not run" in message.content and "scores must be array" in message.content


def test_a_result_that_arrives_mid_turn_does_not_change_what_the_turn_reads(rig):
    _make(rig.world)
    frozen = rig.bridge()
    first = json.loads(frozen.read_scores())["scores"][0]
    assert first["outcome"] == "refused"
    _put(rig.world.services, rig.world.molecule, "tpsa", 63.6, _UNITS)
    _put(rig.world.services, rig.world.molecule, "mol_logp", 1.31)
    assert json.loads(frozen.read_scores())["scores"][0]["outcome"] == "refused", "the turn was frozen before the results existed"
    assert json.loads(rig.bridge().read_scores())["scores"][0]["outcome"] == "computed", "the next turn sees them"


def test_a_score_edited_mid_turn_does_not_change_what_the_turn_reads(rig):
    made = _make(rig.world)
    _put(rig.world.services, rig.world.molecule, "tpsa", 63.6, _UNITS)
    _put(rig.world.services, rig.world.molecule, "mol_logp", 1.31)
    frozen = rig.bridge()
    before = json.loads(frozen.read_scores())["scores"][0]
    rig.world.services.score_service.update(made.score_id, formula="ramp(psa, 100, 60)", inputs=[("psa", _PSA)], constants=[])
    assert json.loads(frozen.read_scores())["scores"][0] == before
    assert json.loads(rig.bridge().read_scores())["scores"][0]["formula"] == "ramp(psa, 100, 60)"


def test_selecting_another_molecule_mid_reply_changes_nothing_about_the_scores_a_tool_reads(rig):
    _make(rig.world)
    _put(rig.world.services, rig.world.molecule, "tpsa", 63.6, _UNITS)
    _put(rig.world.services, rig.world.molecule, "mol_logp", 1.31)
    bridge = rig.bridge()
    rig.world.add("CCO", "Ethanol")
    data = json.loads(bridge.read_scores())
    assert data["molecule_uuid"] == rig.world.molecule.uuid and data["scores"][0]["outcome"] == "computed"


def test_the_persons_owner_and_note_never_reach_the_provider(rig):
    _put(rig.world.services, rig.world.molecule, "tpsa", 63.6, _UNITS)
    _put(rig.world.services, rig.world.molecule, "mol_logp", 1.31)
    _make(rig.world)
    provider = _two_step([_call("read_scores")])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    sent = json.dumps([m.content for m in provider.stream_calls[1].messages])
    assert "my private note" not in sent and "Alex" not in sent


def test_a_tool_thread_cannot_have_changed_the_projects_scores(rig):
    _make(rig.world)
    before = tuple(rig.world.services.score_service.store.definitions())
    _read(rig)
    _read(rig, scores=["Window"])
    assert tuple(rig.world.services.score_service.store.definitions()) == before


# --- the second policy, through the real host and tool ---------------------------------------------------------------------------------------


def test_a_model_that_reads_a_score_with_a_default_is_told_which_input_was_not_calculated(rig):
    _put(rig.world.services, rig.world.molecule, "tpsa", 63.6, _UNITS)
    _make(rig.world, defaults=[("logp", 3.5)])
    data, _provider, _box = _read(rig)
    (score,) = data["scores"]
    assert score["outcome"] == "computed_with_defaults" and score["defaults_used"] == ["logp"] and score["data"]["value"] > 0
    assert {i["name"]: i["state"] for i in score["inputs"]} == {"psa": "read", "logp": "default"}


def test_the_same_score_is_computed_once_the_calculator_has_run_and_the_default_is_not_used(rig):
    _put(rig.world.services, rig.world.molecule, "tpsa", 63.6, _UNITS)
    _put(rig.world.services, rig.world.molecule, "mol_logp", 1.31)
    _make(rig.world, defaults=[("logp", 3.5)])
    data, _provider, _box = _read(rig)
    (score,) = data["scores"]
    assert score["outcome"] == "computed" and "defaults_used" not in score and {i["name"]: i["state"] for i in score["inputs"]}["logp"] == "read"


def test_the_tool_description_tells_the_model_what_a_default_is_and_what_to_say_of_one():
    assert "computed_with_defaults" in READ_SCORES.description and "defaults_used" in READ_SCORES.description
    assert "never present the number as the result of calculating them" in READ_SCORES.description


def test_a_default_declared_after_the_turn_began_changes_nothing_about_what_the_turn_reads(rig):
    made = _make(rig.world)
    _put(rig.world.services, rig.world.molecule, "tpsa", 63.6, _UNITS)
    frozen = rig.bridge()
    assert json.loads(frozen.read_scores())["scores"][0]["outcome"] == "refused"
    rig.world.services.score_service.update(made.score_id, defaults=[("logp", 3.5)])
    assert json.loads(frozen.read_scores())["scores"][0]["outcome"] == "refused", "the definitions were frozen with the results"
    assert json.loads(rig.bridge().read_scores())["scores"][0]["outcome"] == "computed_with_defaults"
