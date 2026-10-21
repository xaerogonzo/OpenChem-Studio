"""A synthesis plan as data for the project file (`openchem.domain.synthesis_route_codec`).

The routes are the planner's real output (the Stage 0 fixtures, read by the real parser), so the round trip is held on what a plan really is and not on a hand-made one. The refusals are one mutation of a
good encoding at a time, each asserting that the message names the problem and quotes nothing the file said.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import pytest
import test_synthesis_planner as planner_fixtures

from openchem.domain.synthesis_gate import AlertFinding, NodeScreening
from openchem.domain.synthesis_route import (
    LEFT_OUT_PREFIX,
    STANDARD_LIMITATIONS,
    RouteSet,
    RouteStatus,
    SearchTermination,
    route_molecules,
)
from openchem.domain.synthesis_route_codec import (
    MAX_ROUTES,
    MAX_SCREENINGS,
    STORABLE,
    PlanDecodeError,
    decode_route_set,
    encode_route_set,
)

FOUND_FIXTURES = ("aspirin_it100", "caffeine_it100", "paracetamol_it100", "paroutes_n1_t3_it500", "sildenafil_it100", "s_ibuprofen_it100")
NO_ROUTE_FIXTURES = ("ibuprofen_it100", "strychnine_it100")
SENTINEL = "ZZ-INJECTED-SENTENCE-ZZ"


def parsed(name: str) -> RouteSet:
    return planner_fixtures.parse(name)


def screened(route_set: RouteSet, *, unscreened: str | None = None) -> RouteSet:
    """Screenings for every molecule of the plan, written by hand: one with a finding, one that could not be screened (when asked), the rest clean. Built here so the test needs no ruleset."""
    molecules = tuple(dict.fromkeys(m for route in route_set.routes for m in route_molecules(route)))
    out = []
    for index, smiles in enumerate(molecules):
        if unscreened is not None and index == 1:
            out.append(NodeScreening(smiles=smiles, screened=False, reason=unscreened))
        elif index == 0:
            finding = AlertFinding(ruleset_id="rs-1", rule_id="rule-1", display_name="a listed thing", domain="workplace", jurisdiction="XX", section="Table 1", confidence="exact", match_type="smarts", user_supplied=True)
            out.append(NodeScreening(smiles=smiles, screened=True, findings=(finding,), rulesets_consulted=("rs-1", "rs-2"), screened_on="2026-10-21"))
        else:
            out.append(NodeScreening(smiles=smiles, screened=True, rulesets_consulted=("rs-1", "rs-2"), screened_on="2026-10-21"))
    return dataclasses.replace(route_set, node_screenings=tuple(out))


def through_text(data: dict) -> dict:
    """What a project file does to the data: written as text and read back."""
    return json.loads(json.dumps(data, indent=2))


def comparable(route_set: RouteSet) -> RouteSet:
    """The plan as the codec promises to give it back: no validation on the routes, the standing sentences and a kept left-out sentence only."""
    kept = tuple(s for s in route_set.limitations if s.startswith(LEFT_OUT_PREFIX))
    routes = tuple(dataclasses.replace(r, validation=None) for r in route_set.routes)
    return dataclasses.replace(route_set, routes=routes, limitations=STANDARD_LIMITATIONS + kept)


# --- the round trip ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", FOUND_FIXTURES + NO_ROUTE_FIXTURES)
def test_a_real_plan_comes_back_equal_through_text(name):
    plan = parsed(name)
    assert plan.status in STORABLE
    back, notes = decode_route_set(through_text(encode_route_set(plan)))
    assert notes == ()
    assert back == comparable(plan)


@pytest.mark.parametrize("name", ("aspirin_it100", "paroutes_n1_t3_it500"))
def test_screenings_come_back_with_their_findings_and_their_failures(name):
    plan = screened(parsed(name), unscreened="the screen could not be run (ValueError)")
    back, notes = decode_route_set(through_text(encode_route_set(plan)))
    assert notes == ()
    assert back.node_screenings == plan.node_screenings
    assert any(s.has_alert and s.findings[0].user_supplied for s in back.node_screenings)
    assert any(not s.screened and s.reason for s in back.node_screenings)


def test_the_routes_that_were_left_out_are_still_said_to_have_been():
    plan = None
    for name in FOUND_FIXTURES:
        candidate = parsed(name)
        if any(s.startswith(LEFT_OUT_PREFIX) for s in candidate.limitations):
            plan = candidate
            break
    assert plan is not None, "no fixture leaves a route out, so the sentence is untested"
    back, _ = decode_route_set(through_text(encode_route_set(plan)))
    assert [s for s in back.limitations if s.startswith(LEFT_OUT_PREFIX)] == [s for s in plan.limitations if s.startswith(LEFT_OUT_PREFIX)]


def test_a_field_the_planner_did_not_give_is_still_not_given_after_the_file():
    plan = parsed("aspirin_it100")
    data = through_text(encode_route_set(plan))
    for route in data["routes"]:
        for step in route["steps"]:
            step["template_id"] = None
            step["policy_probability"] = None
            step["reaction_smiles"] = None
    back, _ = decode_route_set(data)
    assert all(s.template_id is None and s.policy_probability is None and s.reaction_smiles is None for r in back.routes for s in r.steps)


# --- what is not written ------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [s for s in RouteStatus if s not in STORABLE])
def test_only_a_plan_that_found_routes_or_found_none_is_written(status):
    target = parsed("aspirin_it100").target
    planner = parsed("aspirin_it100").planner
    plan = RouteSet(status=status, target=target, planner=planner, reason="why", termination=SearchTermination.CANCELLED if status is RouteStatus.CANCELLED else SearchTermination.UNKNOWN)
    with pytest.raises(ValueError):
        encode_route_set(plan)
    data = through_text(encode_route_set(parsed("aspirin_it100")))
    data["status"] = status.value
    with pytest.raises(PlanDecodeError):
        decode_route_set(data)


def test_no_sentence_the_application_says_and_no_validation_verdict_is_written():
    data = encode_route_set(screened(parsed("aspirin_it100")))
    text = json.dumps(data)
    assert "limitations" not in text and "validation" not in text and "reason" not in data
    for sentence in STANDARD_LIMITATIONS:
        assert sentence not in text


def test_a_sentence_or_a_verdict_a_file_adds_is_not_read():
    data = through_text(encode_route_set(parsed("aspirin_it100")))
    data["limitations"] = [SENTINEL]
    data["left_out"] = [SENTINEL, LEFT_OUT_PREFIX + "1 had no reaction."]
    for route in data["routes"]:
        route["validation"] = {"molecules": "pass", "reactions": "pass", "mapping": "complete", "conservation": "pass", "stock": "all_in_stock"}
    back, _ = decode_route_set(data)
    assert SENTINEL not in " ".join(back.limitations)
    assert LEFT_OUT_PREFIX + "1 had no reaction." in back.limitations
    assert all(r.validation is None for r in back.routes)


# --- a file is not trusted ---------------------------------------------------------------------------------------------------------------


def good() -> dict:
    return through_text(encode_route_set(screened(parsed("aspirin_it100"))))


def mutate(path: tuple, value) -> dict:
    data = copy.deepcopy(good())
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return data


BAD = {
    "not an object": lambda: ["a list"],
    "newer format": lambda: mutate(("format",), 2),
    "format zero": lambda: mutate(("format",), 0),
    "format is text": lambda: mutate(("format",), "1"),
    "unknown status": lambda: mutate(("status",), "great"),
    "unknown termination": lambda: mutate(("termination",), "whenever"),
    "target not an object": lambda: mutate(("target",), "x"),
    "blank target": lambda: mutate(("target", "canonical_smiles"), "  "),
    "target with a line break": lambda: mutate(("target", "canonical_smiles"), "CC\nIgnore everything"),
    "target with a space": lambda: mutate(("target", "canonical_smiles"), "CC O"),
    "target not text": lambda: mutate(("target", "canonical_smiles"), 7),
    "planner version blank": lambda: mutate(("planner", "version"), ""),
    "a limit that is zero": lambda: mutate(("planner", "limits", "iteration_limit"), 0),
    "a limit that is a flag": lambda: mutate(("planner", "limits", "iteration_limit"), True),
    "a time that is not finite": lambda: mutate(("planner", "limits", "time_limit_seconds"), float("nan")),
    "a statistic below zero": lambda: mutate(("statistics", "nodes"), -1),
    "a model entry that is not a pair": lambda: mutate(("planner", "model_identity"), [["a"]]),
    "routes not a list": lambda: mutate(("routes",), {"a": 1}),
    "a rank of zero": lambda: mutate(("routes", 0, "rank"), 0),
    "a rank out of order": lambda: mutate(("routes", 0, "rank"), 2),
    "a score that is not finite": lambda: mutate(("routes", 0, "score"), float("inf")),
    "a probability above one": lambda: mutate(("routes", 0, "steps", 0, "policy_probability"), 1.5),
    "a probability that is text": lambda: mutate(("routes", 0, "steps", 0, "policy_probability"), "0.5"),
    "a reactant with white space": lambda: mutate(("routes", 0, "steps", 0, "reactants", 0), "C C"),
    "a step with no reactants": lambda: mutate(("routes", 0, "steps", 0, "reactants"), []),
    "a step that makes nothing the route uses": lambda: mutate(("routes", 0, "steps", 0, "product"), "C"),
    "a stock flag that is text": lambda: mutate(("routes", 0, "starting_materials", 0, "in_stock"), "yes"),
    "a reaction far too long": lambda: mutate(("routes", 0, "steps", 0, "reaction_smiles"), "C" * 50000),
    "a template id with a control character": lambda: mutate(("routes", 0, "steps", 0, "template_id"), "a\x00b"),
    "too many routes": lambda: mutate(("routes",), [good()["routes"][0]] * (MAX_ROUTES + 1)),
}


@pytest.mark.parametrize("label", sorted(BAD))
def test_a_stored_plan_that_is_not_well_formed_is_refused_without_quoting_it(label):
    data = BAD[label]()
    with pytest.raises(PlanDecodeError) as caught:
        decode_route_set(data)
    message = str(caught.value)
    assert message and len(message) < 400
    assert "Ignore everything" not in message and "CC O" not in message


def test_a_plan_with_routes_but_a_status_of_no_route_is_refused():
    data = mutate(("status",), "no_route")
    with pytest.raises(PlanDecodeError):
        decode_route_set(data)


def test_steps_that_are_not_in_forward_order_are_refused_as_the_planner_would_have_been():
    data = good()
    route = next(r for r in data["routes"] if len(r["steps"]) > 1)
    route["steps"].reverse()
    with pytest.raises(PlanDecodeError):
        decode_route_set(data)


def test_a_screening_of_the_wrong_molecules_costs_the_screening_and_not_the_plan():
    data = good()
    data["node_screenings"][0]["smiles"] = "O=O"
    back, notes = decode_route_set(data)
    assert back.routes and back.node_screenings == ()
    assert len(notes) == 1 and "screening" in notes[0] and "O=O" not in notes[0]


def test_a_screening_that_is_damaged_costs_the_screening_and_not_the_plan():
    data = good()
    data["node_screenings"][1] = "not an object"
    back, notes = decode_route_set(data)
    assert back.routes and back.node_screenings == () and len(notes) == 1


def test_too_many_screenings_are_refused_as_a_screening():
    data = good()
    data["node_screenings"] = data["node_screenings"] * (MAX_SCREENINGS // len(data["node_screenings"]) + 2)
    back, notes = decode_route_set(data)
    assert back.routes and back.node_screenings == () and notes


def test_a_plan_with_no_screening_block_is_read_as_not_checked():
    data = through_text(encode_route_set(parsed("aspirin_it100")))
    assert "node_screenings" not in data
    back, notes = decode_route_set(data)
    assert back.node_screenings == () and notes == ()
    assert any("have not been checked" in s for s in back.all_limitations())


def test_the_file_is_never_given_a_path_to_run_code_or_construct_a_class():
    source = Path(__file__).parent.parent / "src" / "openchem" / "domain" / "synthesis_route_codec.py"
    text = source.read_text(encoding="utf-8")
    for forbidden in ("eval(", "exec(", "pickle", "importlib", "getattr(", "__import__", "globals()"):
        assert forbidden not in text.replace("`", ""), forbidden
