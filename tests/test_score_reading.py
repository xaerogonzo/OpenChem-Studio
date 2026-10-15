"""The user-defined scores of the selected molecule, as the assistant reads them (`domain/score_reading.py`, `result_envelope.scores_view_envelope`; design record section 9).

Pure: a hand-built turn (frozen results and frozen definitions), so each way a score can fail to have a value is one case. The real host, the plugin tool and a scripted
provider are in `test_ai_assistant_scores.py`.
"""

from __future__ import annotations

import json

import pytest

from openchem.domain.calculator import DRAWING
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.result_envelope import CAP_STEPS, FULL, SCORE_NOT_A_PREDICTION, SCORES_NOTE, Caps, score_envelope_of, scores_view_envelope
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.score_answer import LIMITATION
from openchem.domain.score_constants import Constant
from openchem.domain.score_definition import ScoreDefinition
from openchem.domain.score_outputs import approved_output
from openchem.domain.score_reading import DEFAULT_READ_LIMIT, read_scores
from openchem.domain.score_value import ScoreStatus, evaluate_score
from openchem.domain.turn_snapshot import build_turn_context

_TPSA = "descriptor:tpsa"
_LOGP = "descriptor:mol_logp"
_MOLECULE = "aspirin-uuid"


def _definition(score_id="user.window", label="Window", **changes) -> ScoreDefinition:
    base = dict(
        score_id=score_id, label=label, formula="ramp(psa, 140, 60) * ramp(logp, 5, 2)", result_unit="1", inputs=(("psa", _TPSA), ("logp", _LOGP)),
        schema_version=1, owner="Alex", created="2026-10-15", note="a private note about the formula",
    )
    base.update(changes)
    return ScoreDefinition(**base)


def _record(descriptor_id: str, value: float, *, fingerprint: str = "fp1") -> StoredResult:
    units = approved_output(f"descriptor:{descriptor_id}").carried_as
    result = DescriptorValue(descriptor_id, descriptor_id, units, "c", "rdkit", _MOLECULE, value=value, cache_state=CacheState.COMPLETED)
    return StoredResult(ResultIdentity(_MOLECULE, f"descriptor:rdkit:{descriptor_id}", DRAWING, fingerprint, "rdkit"), result)


def _turn(scores=(), records=None, *, fingerprint="fp1", has_structure=True):
    records = [_record("tpsa", 63.6), _record("mol_logp", 1.31)] if records is None else records
    current = [r for r in records if r.identity.input_fingerprint == fingerprint]
    return build_turn_context(
        project_uuid="p", molecule_uuid=_MOLECULE, display_name="Aspirin", canonical_smiles="CC(=O)Oc1ccccc1C(=O)O", heavy_atoms=13, has_structure=has_structure,
        conformer_count=0, fingerprints={DRAWING: fingerprint}, records=records, fresh=current, scores=scores,
    )


# --- what is frozen -----------------------------------------------------------------------------------------------------------------------


def test_a_turn_holds_the_definitions_it_began_with_as_a_tuple():
    definition = _definition()
    turn = _turn([definition])
    assert turn.scores == (definition,) and isinstance(turn.scores, tuple)


def test_a_turn_with_no_scores_has_none():
    assert _turn().scores == () and read_scores(_turn()).values == () and read_scores(_turn()).defined == 0


def test_a_list_given_to_the_turn_cannot_be_edited_into_it_afterwards():
    scores = [_definition()]
    turn = _turn(scores)
    scores.append(_definition("user.other", "Other"))
    assert len(turn.scores) == 1 and len(read_scores(turn).values) == 1


# --- reading ------------------------------------------------------------------------------------------------------------------------------


def test_every_score_is_read_in_the_order_it_was_defined_with_the_value_results_gives():
    first, second = _definition("user.a", "A"), _definition("user.b", "B", formula="ramp(psa, 140, 60)", inputs=(("psa", _TPSA),))
    turn = _turn([first, second])
    view = read_scores(turn)
    assert [v.definition.score_id for v in view.values] == ["user.a", "user.b"] and view.not_found == () and view.truncated == 0 and view.defined == 2
    assert view.turn_id == turn.turn_id and view.molecule_uuid == _MOLECULE
    for value, definition in zip(view.values, (first, second)):
        assert value == evaluate_score(definition, turn.entries), "the same ScoreValue the Results reader is built from"
        assert value.status is ScoreStatus.VALUE


@pytest.mark.parametrize("name", ["user.window", "USER.WINDOW", "Window", "window", "Window (user-defined, unvalidated)", "  Window  "])
def test_a_score_is_found_by_its_id_its_label_or_its_label_as_shown(name):
    view = read_scores(_turn([_definition(), _definition("user.other", "Other")]), [name])
    assert [v.definition.score_id for v in view.values] == ["user.window"] and view.not_found == ()


def test_a_name_that_matches_nothing_is_not_found_and_never_matched_loosely():
    view = read_scores(_turn([_definition()]), ["Wind", "user.window", "ghost", "ghost", ""])
    assert [v.definition.score_id for v in view.values] == ["user.window"] and view.not_found == ("Wind", "ghost")


def test_naming_nothing_reads_nothing_and_naming_none_reads_everything():
    turn = _turn([_definition()])
    assert read_scores(turn, []).values == () and len(read_scores(turn, None).values) == 1


def test_defined_counts_every_score_the_project_has_and_not_only_those_asked_for():
    view = read_scores(_turn([_definition(), _definition("user.b", "B")]), ["Window"])
    assert len(view.values) == 1 and view.defined == 2
    assert read_scores(_turn([_definition(), _definition("user.b", "B")]), ["ghost"]).defined == 2


def test_with_no_limit_given_forty_scores_are_read_and_the_rest_are_counted():
    definitions = [_definition(f"user.s{i}", f"S{i}") for i in range(DEFAULT_READ_LIMIT + 5)]
    view = read_scores(_turn(definitions))
    assert len(view.values) == DEFAULT_READ_LIMIT == 40 and view.truncated == 5 and view.defined == 45


def test_a_score_named_twice_is_read_once():
    view = read_scores(_turn([_definition()]), ["Window", "user.window"])
    assert len(view.values) == 1


def test_the_limit_leaves_scores_out_and_says_how_many():
    definitions = [_definition(f"user.s{i}", f"S{i}") for i in range(5)]
    view = read_scores(_turn(definitions), limit=2)
    assert [v.definition.score_id for v in view.values] == ["user.s0", "user.s1"] and view.truncated == 3 and view.defined == 5
    assert read_scores(_turn(definitions), limit=0).values == () and read_scores(_turn(definitions), limit=-3).truncated == 5
    assert DEFAULT_READ_LIMIT == 40


def test_a_score_whose_input_was_never_calculated_has_no_value_and_says_which():
    view = read_scores(_turn([_definition()], records=[_record("tpsa", 63.6)]))
    (value,) = view.values
    assert value.status is ScoreStatus.REFUSED and value.value is None and "logp (descriptor:mol_logp): it has not been calculated for this molecule" in value.reason


def test_a_score_whose_inputs_were_calculated_for_an_earlier_structure_has_no_value_and_says_so():
    stale = [_record("tpsa", 63.6, fingerprint="old"), _record("mol_logp", 1.31, fingerprint="old")]
    (value,) = read_scores(_turn([_definition()], stale)).values
    assert value.status is ScoreStatus.REFUSED and "no longer describe this molecule" in value.reason


def test_a_molecule_with_nothing_drawn_has_refused_scores_and_never_a_number():
    (value,) = read_scores(_turn([_definition()], records=[], has_structure=False)).values
    assert value.status is ScoreStatus.REFUSED and value.value is None


# --- the envelope -------------------------------------------------------------------------------------------------------------------------


def _envelope(scores=None, **kwargs):
    return scores_view_envelope(read_scores(_turn(scores if scores is not None else [_definition()], **kwargs)))


def test_a_score_with_a_number_has_a_header_and_a_data_block_with_units():
    (item,) = _envelope()["scores"]
    assert item["score_id"] == "user.window" and item["name"] == "Window (user-defined, unvalidated)"
    assert item["kind"] == "user_defined_score" and item["validation"] == "user_defined_unvalidated"
    assert item["freshness"] == "current" and item["outcome"] == "computed" and "refusal" not in item
    assert "never stored" in item["freshness_note"] and "this turn" in item["freshness_note"], "a model is told how current a score is, and why it is not stored"
    assert item["declared_units"] == "1" and item["definition"] == _definition().digest and item["formula"] == _definition().formula
    assert item["data"]["units"] == "1" and item["data"]["value"] == pytest.approx(evaluate_score(_definition(), _turn([_definition()]).entries).value, rel=1e-5)


def test_every_input_says_what_it_reads_and_the_state_it_was_read_in():
    (item,) = _envelope()["scores"]
    psa, logp = item["inputs"]
    carried = approved_output(_TPSA).carried_as
    assert psa == {"name": "psa", "reads": "tpsa", "output_id": _TPSA, "state": "read", "value": 63.6, "units": carried}
    assert logp["state"] == "read" and logp["value"] == 1.31 and logp["name"] == "logp"


def test_a_refused_score_has_the_reason_and_no_number_anywhere():
    (item,) = _envelope(records=[_record("tpsa", 63.6)])["scores"]
    assert item["outcome"] == "refused" and "data" not in item
    assert item["refusal"]["inputs_not_read"] == ["logp"] and "has not been calculated" in item["refusal"]["reason"]
    unread = item["inputs"][1]
    assert unread["state"] == "not_run" and "value" not in unread and "has not been calculated" in unread["note"]
    assert "value" not in json.dumps(item["refusal"])


def test_every_score_says_it_is_a_persons_formula_and_not_a_prediction():
    (item,) = _envelope()["scores"]
    assert item["caveats"] == [LIMITATION, SCORE_NOT_A_PREDICTION] and "not a prediction" in SCORE_NOT_A_PREDICTION
    assert _envelope()["note"] == SCORES_NOTE and "cannot create, change or delete" in SCORES_NOTE and "never state a value" in SCORES_NOTE


def test_a_persons_free_text_is_never_sent():
    data = _envelope()
    text = json.dumps(data)
    assert "private note" not in text and "Alex" not in text, "the owner's name and the note's words are the person's own"
    (item,) = data["scores"]
    assert "owner" not in item and "note" not in item and "created" not in item


def test_a_named_constant_is_sent_with_its_unit():
    definition = _definition(formula="ramp(psa, hi, 60)", inputs=(("psa", _TPSA),), constants=(Constant("hi", 140.0, "Å^2"),))
    (item,) = _envelope([definition])["scores"]
    assert item["constants"] == [{"name": "hi", "value": 140.0, "units": "Å^2"}]


def test_the_envelope_is_plain_json_with_the_counts_a_model_needs():
    data = _envelope([_definition(), _definition("user.b", "B")], records=[_record("tpsa", 63.6)])
    assert json.loads(json.dumps(data)) == data
    assert data["envelope_version"] == 1 and data["molecule_uuid"] == _MOLECULE and data["defined_in_this_project"] == 2
    assert data["not_found"] == [] and data["left_out_for_length"] == 0


def test_a_name_that_matched_nothing_is_in_the_envelope():
    data = scores_view_envelope(read_scores(_turn([_definition()]), ["ghost"]))
    assert data["scores"] == [] and data["not_found"] == ["ghost"]


def test_the_caps_shrink_the_number_of_scores_and_inputs_and_say_how_many_were_left_out():
    definitions = [_definition(f"user.s{i}", f"S{i}") for i in range(30)]
    view = read_scores(_turn(definitions))
    sizes = [len(scores_view_envelope(view, caps)["scores"]) for caps in CAP_STEPS]
    assert sizes == sorted(sizes, reverse=True) and sizes[0] == 30 and sizes[-1] < 30
    smallest = scores_view_envelope(view, CAP_STEPS[-1])
    assert smallest["left_out_for_length"] == 30 - sizes[-1]
    assert all(item["score_id"] and item["name"] and item["outcome"] and item["caveats"] for item in smallest["scores"]), "a header is never what is cut"


def test_a_tight_cap_cuts_the_inputs_and_the_constants_of_one_score_and_nothing_else():
    definition = _definition(
        formula="ramp(psa, hi, lo) * ramp(logp, 5, 2)", constants=(Constant("hi", 140.0, "Å^2"), Constant("lo", 60.0, "Å^2")),
    )
    value = read_scores(_turn([definition])).values[0]
    full = score_envelope_of(value)
    assert [i["name"] for i in full["inputs"]] == ["psa", "logp"] and [c["name"] for c in full["constants"]] == ["hi", "lo"]
    tight = score_envelope_of(value, Caps(items=1))
    assert [i["name"] for i in tight["inputs"]] == ["psa"] and [c["name"] for c in tight["constants"]] == ["hi"]
    assert tight["outcome"] == "computed" and tight["data"] == full["data"], "the number is never what is cut"


def test_the_longest_text_is_cut_and_says_so_but_the_header_stays():
    long_formula = " + ".join(["psa"] * 80)
    item = score_envelope_of(read_scores(_turn([_definition(formula=long_formula, inputs=(("psa", _TPSA),))])).values[0], CAP_STEPS[-1])
    assert item["formula"].endswith("…") and item["score_id"] == "user.window" and item["caveats"]


def test_a_value_is_rounded_for_the_model_to_six_figures_and_a_non_finite_one_is_never_sent():
    definition = _definition(formula="psa / 3", inputs=(("psa", _TPSA),), result_unit="Å^2")
    (item,) = scores_view_envelope(read_scores(_turn([definition], [_record("tpsa", 100.0)]))).get("scores")
    assert item["data"]["value"] == 33.3333 and item["data"]["units"] == "Å^2"
    zero = _definition(formula="psa / z", inputs=(("psa", _TPSA),), constants=(Constant("z", 0.0, "Å^2"),), result_unit="1")
    (refused,) = scores_view_envelope(read_scores(_turn([zero]))).get("scores")
    assert refused["outcome"] == "refused" and "data" not in refused


def test_the_scores_left_out_by_the_read_limit_are_counted_in_the_envelope_too():
    definitions = [_definition(f"user.s{i}", f"S{i}") for i in range(5)]
    data = scores_view_envelope(read_scores(_turn(definitions), limit=2))
    assert len(data["scores"]) == 2 and data["left_out_for_length"] == 3 and data["defined_in_this_project"] == 5


def test_the_full_caps_are_the_first_step():
    assert CAP_STEPS[0] == FULL
