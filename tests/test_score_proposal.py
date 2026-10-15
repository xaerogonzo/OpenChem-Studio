"""A score the assistant proposes (`domain/score_proposal.py`; `docs/DERIVED_SCORES_DESIGN.md` slice 4d).

Two things matter here and nothing else is clever: a request is turned into a definition by the SAME rules a typed one meets (and refused, in the request's own words, when it is not
shaped as a score or does not check), and the book that holds proposals for a person decides each one once, holds few of them, and never stores anything.
"""

from __future__ import annotations

import math
import threading

import pytest

from openchem.domain.score_definition import ON_MISSING_REFUSE, ScoreDefinition
from openchem.domain.score_formula import Problem
from openchem.domain.score_proposal import (
    ASSISTANT_OWNER,
    card_of,
    DRAFT_ID,
    MAX_PENDING,
    REQUEST_KEYS,
    ProposalBook,
    ProposalProblem,
    ProposalRefusal,
    ProposalState,
    Registered,
    ScoreProposal,
    check_request,
    definition_from_request,
)
from openchem.domain.score_value import InputState, ScoreStatus, evaluate_score

_TPSA = "descriptor:tpsa"
_LOGP = "descriptor:mol_logp"


def _request(**changes) -> dict:
    base = {
        "label": "Polar window",
        "formula": "ramp(psa, hi, 60) * ramp(logp, 5, 2)",
        "result_unit": "1",
        "inputs": [{"name": "psa", "output": _TPSA}, {"name": "logp", "output": _LOGP}],
        "constants": [{"name": "hi", "value": 140, "unit": "Å^2"}],
        "note": "a first try",
    }
    base.update(changes)
    return base


# --- turning a request into a definition ---------------------------------------------------------------------------------------------------------


def test_a_good_request_is_a_definition_the_assistant_owns_with_a_draft_id_and_the_first_policy():
    definition = check_request(_request())
    assert isinstance(definition, ScoreDefinition)
    assert definition.score_id == DRAFT_ID == "user.draft" and definition.owner == ASSISTANT_OWNER and definition.label == "Polar window"
    assert definition.inputs == (("psa", _TPSA), ("logp", _LOGP)) and definition.constants[0].name == "hi" and definition.constants[0].value == 140.0
    assert (definition.schema_version, definition.on_missing, getattr(definition, "defaults", ()), definition.created, definition.note) == (1, ON_MISSING_REFUSE, (), "", "a first try")


def test_the_constants_and_the_note_are_optional():
    definition = check_request(_request(formula="ramp(psa, 140, 60)", inputs=[{"name": "psa", "output": _TPSA}], constants=None) | {})
    assert isinstance(definition, ProposalRefusal), "None is not a list of constants"
    request = _request(formula="ramp(psa, 140, 60)", inputs=[{"name": "psa", "output": _TPSA}])
    del request["constants"], request["note"]
    definition = check_request(request)
    assert isinstance(definition, ScoreDefinition) and definition.constants == () and definition.note == ""


def test_an_integer_constant_is_a_float_and_nothing_else_is_coerced():
    assert isinstance(check_request(_request()).constants[0].value, float)
    for bad in ("140", True, None, math.nan, math.inf, [140]):
        refused = definition_from_request(_request(constants=[{"name": "hi", "value": bad, "unit": "Å^2"}]))
        assert isinstance(refused, ProposalRefusal) and refused.problem is ProposalProblem.NOT_A_REQUEST and refused.where == "constants", bad


@pytest.mark.parametrize("key", ["owner", "score_id", "schema_version", "on_missing", "defaults", "created", "anything"])
def test_a_key_that_is_not_the_models_to_give_is_refused_by_name(key):
    refused = definition_from_request(_request() | {key: "x"})
    assert isinstance(refused, ProposalRefusal) and refused.problem is ProposalProblem.NOT_A_REQUEST
    assert key in refused.message and "not part of a score request" in refused.message and all(name in refused.message for name in REQUEST_KEYS)


@pytest.mark.parametrize("missing", ["label", "formula", "result_unit", "inputs"])
def test_a_missing_required_field_is_named(missing):
    request = _request()
    del request[missing]
    refused = definition_from_request(request)
    assert isinstance(refused, ProposalRefusal) and refused.where == missing and missing in refused.message and "required" in refused.message


@pytest.mark.parametrize(
    "changes, where",
    [
        ({"label": 5}, "label"), ({"formula": None}, "formula"), ({"result_unit": 1}, "result_unit"), ({"note": ["x"]}, "note"),
        ({"inputs": "psa"}, "inputs"), ({"inputs": []}, "inputs"), ({"inputs": [{"name": "psa"}]}, "inputs"),
        ({"inputs": [{"name": "psa", "output": _TPSA, "default": 1}]}, "inputs"), ({"inputs": [{"name": 1, "output": _TPSA}]}, "inputs"),
        ({"inputs": [{"name": "psa", "output": _TPSA, "owner": "someone"}]}, "inputs"),
        ({"constants": [{"name": "hi", "value": 140, "unit": "Å^2", "owner": "someone"}]}, "constants"), ({"constants": [{"name": 5, "value": 140, "unit": "Å^2"}]}, "constants"),
        ({"inputs": ["psa"]}, "inputs"), ({"constants": "hi"}, "constants"), ({"constants": [{"name": "hi", "value": 1}]}, "constants"),
        ({"constants": [{"name": "hi", "value": 1, "unit": 3}]}, "constants"), ({"constants": ["hi"]}, "constants"),
    ],
)
def test_a_request_that_is_not_shaped_as_a_score_says_which_field(changes, where):
    refused = definition_from_request(_request(**changes))
    assert isinstance(refused, ProposalRefusal) and refused.problem is ProposalProblem.NOT_A_REQUEST and refused.where == where and refused.message


def test_a_request_that_is_not_an_object_is_refused():
    for bad in (None, "score", [1], 3):
        refused = definition_from_request(bad)
        assert isinstance(refused, ProposalRefusal) and refused.problem is ProposalProblem.NOT_A_REQUEST and "must be an object" in refused.message


# --- the same rules as a typed definition -----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes, rule, where",
    [
        ({"label": ""}, "definition", "label"),
        ({"label": "TPSA"}, "definition", "label"),
        ({"label": "CNS MPO again"}, "definition", "label"),
        ({"formula": "ramp(psa, hi, 60) * ramp(logp, 5, "}, "syntax", "formula"),
        ({"formula": "psa + logp", "constants": []}, "unit", "formula"),
        ({"result_unit": "Å^2"}, "unit", "result_unit"),
        ({"inputs": [{"name": "psa", "output": "descriptor:nothing"}, {"name": "logp", "output": _LOGP}]}, "output", "inputs"),
        ({"inputs": [{"name": "a", "output": "descriptor:esol_logs"}, {"name": "b", "output": "calculator:solubility:Predicted intrinsic solubility (mol/L)"}], "formula": "a + b", "constants": []}, "consensus", "inputs"),
        ({"constants": [{"name": "hi", "value": 140, "unit": "nm^2"}]}, "unit", "formula"),
        ({"owner": "x"}, None, ""),
    ],
)
def test_a_request_that_does_not_check_is_refused_by_the_rule_that_refuses_a_typed_one(changes, rule, where):
    refused = check_request(_request(**changes), reserved_names=["CNS MPO"])
    assert isinstance(refused, ProposalRefusal)
    if rule is None:
        assert refused.problem is ProposalProblem.NOT_A_REQUEST
        return
    assert refused.problem is ProposalProblem.DOES_NOT_CHECK and refused.rule == rule and refused.message
    assert refused.where == where, (refused.where, refused.message)


def test_a_formula_problem_carries_the_place_in_the_formula():
    refused = check_request(_request(formula="ramp(psa, hi, 60) * (logp"))
    assert isinstance(refused, ProposalRefusal) and refused.rule == "syntax" and isinstance(refused.position, int) and refused.position >= 0


def test_a_label_close_to_a_name_the_application_gives_is_refused_and_one_it_does_not_know_is_not():
    refused = check_request(_request(label="Ludicrous"), reserved_names=["Ludicrous Speed Score"])
    assert isinstance(refused, ProposalRefusal) and refused.where == "label" and "too close to" in refused.message
    assert isinstance(check_request(_request(label="Ludicrous")), ScoreDefinition)


def test_the_defaults_and_the_policy_cannot_be_asked_for():
    """The second policy exists (a person's box in the dialog); a model cannot choose it: its request has no such key and the definition made is the first policy."""
    assert "defaults" not in REQUEST_KEYS and "on_missing" not in REQUEST_KEYS
    assert check_request(_request()).on_missing == "refuse" and getattr(check_request(_request()), "defaults", ()) == ()


# --- the book ---------------------------------------------------------------------------------------------------------------------------------


def _proposal(book_id: str = "p1", *, label: str = "Polar window", project: str = "project-1", formula: str = "ramp(psa, 140, 60)") -> ScoreProposal:
    definition = check_request({"label": label, "formula": formula, "result_unit": "1", "inputs": [{"name": "psa", "output": _TPSA}]})
    assert isinstance(definition, ScoreDefinition), definition
    value = evaluate_score(definition, ())
    assert value.status is ScoreStatus.REFUSED and value.inputs[0].state is InputState.NOT_RUN
    return ScoreProposal(book_id, project, "m1", "Aspirin", definition, value)


def test_a_proposal_registered_waits_and_is_found_by_its_id():
    book = ProposalBook()
    registered = book.register(_proposal("a"))
    assert isinstance(registered, Registered) and not registered.already_waiting and registered.proposal.proposal_id == "a"
    assert [p.proposal_id for p in book.pending()] == ["a"] and book.get("a") is registered.proposal and book.state_of("a") is ProposalState.PENDING


def test_the_same_score_proposed_again_while_it_waits_is_the_one_that_waits():
    book = ProposalBook()
    book.register(_proposal("a"))
    again = book.register(_proposal("b"))
    assert isinstance(again, Registered) and again.already_waiting and again.proposal.proposal_id == "a" and len(book.pending()) == 1


def test_a_different_formula_a_different_label_or_another_project_is_another_proposal():
    book = ProposalBook()
    book.register(_proposal("a"))
    assert not book.register(_proposal("b", formula="ramp(psa, 150, 60)")).already_waiting
    assert not book.register(_proposal("c", label="Another")).already_waiting
    assert not book.register(_proposal("d", project="project-2")).already_waiting
    assert len(book.pending()) == 4


def test_only_a_few_wait_at_once_and_the_refusal_says_so():
    book = ProposalBook()
    for index in range(MAX_PENDING):
        assert isinstance(book.register(_proposal(f"p{index}", label=f"Score {chr(97 + index)}")), Registered)
    refused = book.register(_proposal("one-more", label="Score z"))
    assert isinstance(refused, ProposalRefusal) and refused.problem is ProposalProblem.TOO_MANY_WAITING and str(MAX_PENDING) in refused.message
    assert len(book.pending()) == MAX_PENDING
    book.settle("p0", ProposalState.CANCELLED, "no")
    assert isinstance(book.register(_proposal("one-more", label="Score z")), Registered), "room again once one is decided"


def test_a_proposal_is_decided_once_and_a_repeated_decision_changes_nothing():
    book = ProposalBook()
    book.register(_proposal("a"))
    outcome = book.settle("a", ProposalState.SAVED, "saved", "user.polar_window")
    assert outcome.state is ProposalState.SAVED and outcome.score_id == "user.polar_window" and outcome.label == "Polar window" and outcome.molecule_name == "Aspirin"
    assert book.settle("a", ProposalState.CANCELLED, "too late") is None and book.settle("nobody", ProposalState.CANCELLED, "x") is None
    assert book.state_of("a") is ProposalState.SAVED and book.outcome_of("a") is outcome and book.get("a") is None and book.pending() == ()


def test_a_proposal_cannot_be_settled_into_pending():
    book = ProposalBook()
    book.register(_proposal("a"))
    with pytest.raises(ValueError):
        book.settle("a", ProposalState.PENDING, "x")


def test_an_unknown_proposal_has_no_state():
    assert ProposalBook().state_of("nothing") is None and ProposalBook().outcome_of("nothing") is None and ProposalBook().get("nothing") is None


def test_proposals_made_in_another_project_are_voided_and_the_open_projects_are_left():
    book = ProposalBook()
    book.register(_proposal("a", project="old"))
    book.register(_proposal("b", project="new", label="Other"))
    voided = book.void_outside("new", "the project changed")
    assert [o.proposal_id for o in voided] == ["a"] and voided[0].state is ProposalState.VOID and voided[0].message == "the project changed"
    assert [p.proposal_id for p in book.pending()] == ["b"]


def test_the_settled_outcomes_are_remembered_for_a_while_and_not_forever():
    book = ProposalBook(limit=1000)
    for index in range(60):
        book.register(_proposal(f"p{index}", label=f"Score {index}"))
        book.settle(f"p{index}", ProposalState.CANCELLED, "no")
    assert book.outcome_of("p59") is not None and book.outcome_of("p0") is None


def test_the_ids_it_makes_are_distinct_and_say_what_they_are():
    ids = {ProposalBook.new_id() for _ in range(200)}
    assert len(ids) == 200 and all(i.startswith("score-proposal-") for i in ids)


def test_many_threads_proposing_never_hold_more_than_the_limit_and_never_lose_one():
    book = ProposalBook()
    results = []

    def propose(index: int) -> None:
        results.append(book.register(_proposal(f"t{index}", label=f"Thread score {index}")))

    threads = [threading.Thread(target=propose, args=(i,)) for i in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    made = [r for r in results if isinstance(r, Registered)]
    refused = [r for r in results if isinstance(r, ProposalRefusal)]
    assert len(made) == MAX_PENDING and len(refused) == 40 - MAX_PENDING and len(book.pending()) == MAX_PENDING


def test_the_problems_a_rule_can_raise_all_have_a_place_in_the_request():
    """`_where_of` is a table over the rule problems: a new one that nobody placed would come back with no field."""
    placed = {"syntax", "limit", "name", "function", "exponent", "inputs", "output", "consensus", "constant", "unit", "definition"}
    assert {problem.value for problem in Problem} == placed, "a rule problem nobody placed would come back from a proposal with no field"


# --- the card -----------------------------------------------------------------------------------------------------------------------------------


def _calculated_proposal(*, value_for_psa: float = 63.6) -> ScoreProposal:
    from openchem.domain.calculator import DRAWING
    from openchem.domain.common import CacheState
    from openchem.domain.descriptor import DescriptorValue
    from openchem.domain.result_store import ResultIdentity, StoredResult
    from openchem.domain.turn_snapshot import classify_results

    result = DescriptorValue("tpsa", "tpsa", "Å²", "c", "rdkit", "m1", value=value_for_psa, cache_state=CacheState.COMPLETED)
    stored = StoredResult(ResultIdentity("m1", "descriptor:rdkit:tpsa", DRAWING, "fp", "rdkit"), result)
    entries = classify_results([stored], [stored], {DRAWING: "fp"})
    definition = check_request(_request(formula="ramp(psa, hi, 60)", inputs=[{"name": "psa", "output": _TPSA}]))
    return ScoreProposal("p1", "project-1", "m1", "Aspirin", definition, evaluate_score(definition, entries))


def test_the_card_says_what_a_person_decides_on_in_plain_lines():
    card = card_of(_calculated_proposal())
    assert card["proposal_id"] == "p1" and card["label"] == "Polar window (user-defined, unvalidated)" and card["formula"] == "ramp(psa, hi, 60)"
    assert card["inputs"] == ["psa = tpsa"]
    assert card["constants"] == ["hi = 140 Å^2"] and card["declared_unit"] == "1" and card["molecule"] == "Aspirin" and card["owner"] == ASSISTANT_OWNER and card["note"] == "a first try"
    assert card["preview"] == "For Aspirin: 0.955"


def test_the_card_gives_the_unit_after_a_number_that_has_one_and_not_after_a_plain_number():
    definition = check_request(_request(formula="psa", inputs=[{"name": "psa", "output": _TPSA}], result_unit="Å^2", constants=[]))
    from openchem.domain.score_value import evaluate_score as evaluate

    proposal = ScoreProposal("p1", "project-1", "m1", "Aspirin", definition, evaluate(definition, ()))
    assert card_of(proposal)["declared_unit"] == "Å^2" and card_of(proposal)["preview"].startswith("For Aspirin: no value yet.")


def test_a_score_nothing_has_been_calculated_for_says_why_it_has_no_value_yet():
    card = card_of(_proposal())
    assert card["preview"].startswith("For Aspirin: no value yet.") and "has not been calculated for this molecule" in card["preview"]


def test_the_card_is_the_definitions_own_words_and_nothing_a_model_could_add():
    card = card_of(_calculated_proposal())
    assert set(card) == {"proposal_id", "label", "formula", "inputs", "constants", "declared_unit", "preview", "molecule", "owner", "note"}


def test_the_numbers_a_card_and_a_model_are_told_are_the_ones_the_description_promises():
    assert MAX_PENDING == 5, "the tool's description says at most 5 proposals wait at once"
    assert ASSISTANT_OWNER == "AI assistant (you approved it)", "the card, the stored owner and the model's note all quote this"
