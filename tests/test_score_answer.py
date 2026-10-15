"""A user-defined score as the Results reader holds it (`domain/score_answer.py`).

What matters is what a person reading the number is told: the label says it is user-defined and unvalidated, the evidence names the formula and every input, the
one limitation says nobody checked it, and a score with no number says which input could not be read and why, in the application's own vocabulary for a
refusal. None of it is stored, and none of it is ever called a prediction.
"""

from __future__ import annotations

import pytest

from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.refusal_kinds import RefusalKind, refusal_kind_of_result
from openchem.domain.report import (
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    DEFAULT_EXPANDED,
    Basis,
    FactCategory,
)
from openchem.domain.result_status import NEEDS_INPUT, status_of
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.score_answer import (
    DEFAULTED,
    LIMITATION,
    NO_VALUE,
    REFUSAL_CODE,
    ScoreAnswer,
    project_score_answers,
    report_id_of,
)
from openchem.domain.score_constants import Constant
from openchem.domain.score_definition import FORMAT_DEFAULTS, ON_MISSING_DEFAULT, VALIDATION, ScoreDefinition
from openchem.domain.score_value import evaluate_score
from openchem.domain.turn_snapshot import classify_results

_FP = {"drawing": "fp-now"}


def _descriptor(descriptor_id, value, units=""):
    result = DescriptorValue(descriptor_id, descriptor_id, units, "c", "rdkit", "m", value=value, cache_state=CacheState.COMPLETED)
    return StoredResult(ResultIdentity("m", f"descriptor:rdkit:{descriptor_id}", "drawing", "fp-now", "rdkit"), result)


def _entries(*stored):
    return classify_results(list(stored), list(stored), _FP)


def _definition(**changes) -> ScoreDefinition:
    base = ScoreDefinition(
        score_id="user.window", label="Window blend", formula="ramp(psa, hi, 60) * ramp(logp, 5, 2)", result_unit="1",
        inputs=(("psa", "descriptor:tpsa"), ("logp", "descriptor:mol_logp")), constants=(Constant("hi", 140.0, "Å^2"),),
    )
    from dataclasses import replace

    return replace(base, **changes)


def _value(definition=None, entries=None):
    entries = _entries(_descriptor("tpsa", 100.0, "Å²"), _descriptor("mol_logp", 3.5)) if entries is None else entries
    return evaluate_score(definition or _definition(), entries)


def _answer(value=None, viewing="viewing-molecule", version=7) -> ScoreAnswer:
    (answer,) = project_score_answers([value or _value()], viewing=viewing, structure_version=version)
    return answer


# --- a score with a number -----------------------------------------------------------------------------------------------------


def test_a_score_with_a_number_is_one_fact_labelled_user_defined_and_unvalidated():
    answer = _answer()
    (fact,) = answer.facts
    assert answer.name == "Window blend (user-defined, unvalidated)" and fact.label == "Window blend (user-defined, unvalidated)"
    assert fact.value == pytest.approx(0.25) and fact.display_value == "0.25" and fact.units == ""
    assert fact.category is FactCategory.DERIVED and fact.basis is Basis.HEURISTIC and fact.source == "derived score"
    assert answer.cache_state is CacheState.COMPLETED and answer.error is None


def test_the_value_is_shown_to_four_significant_digits_and_kept_whole():
    value = _value(_definition(formula="psa / 3", constants=(), inputs=(("psa", "descriptor:tpsa"),), result_unit="Å^2"))
    (fact,) = _answer(value).facts
    assert fact.display_value == "33.33" and fact.value == pytest.approx(100.0 / 3) and fact.units == "Å^2"


def test_the_one_limitation_is_in_these_words_on_the_fact_and_the_report():
    answer = _answer()
    assert LIMITATION == "A formula a person wrote. Nothing has checked it against measurements."
    assert answer.facts[0].limitations == (LIMITATION,) and LIMITATION in answer.limitations


def test_the_evidence_names_the_formula_every_input_every_constant_and_the_digest():
    answer = _answer()
    text = "\n".join(answer.facts[0].evidence)
    assert "Formula: ramp(psa, hi, 60) * ramp(logp, 5, 2)" in text
    assert "psa = 100" in text and "Å²" in text and "descriptor:tpsa" in text and "descriptor:rdkit:tpsa" in text
    assert "computed on the drawing" in text, "a person comparing with a conformer's number beside it must be told which this read"
    assert "logp = 3.5" in text and "descriptor:mol_logp" in text
    assert "hi = 140 Å^2" in text and "a constant of this definition" in text
    assert answer.digest in text and answer.facts[0].evidence[0].startswith("Formula:")


def test_the_provenance_says_a_user_wrote_it_and_nobody_validated_it():
    answer = _answer()
    provenance = answer.provenance
    assert provenance.created_by == "user" and provenance.method == "derived_score:1"
    parameters = provenance.parameters
    assert parameters["validation"] == VALIDATION == "user_defined_unvalidated"
    assert parameters["formula"] == _definition().formula and parameters["schema_version"] == 1
    assert parameters["digest"] == answer.digest == _definition().digest and parameters["score_id"] == "user.window"
    assert "refusal" not in parameters


def test_it_is_filed_under_its_own_id_that_can_never_be_a_calculators():
    answer = _answer()
    assert answer.report_id == report_id_of("user.window") == "score:user.window" and answer.score_id == "user.window"
    assert answer.category == "derived"


def test_it_is_stamped_with_the_molecule_being_looked_at_and_the_structure_version_it_was_given():
    answer = _answer(viewing="the-one-shown", version=12)
    assert answer.molecule_uuid == "the-one-shown" and answer.structure_version == 12


def test_a_score_is_never_called_a_prediction_in_any_string_it_generates():
    for answer in (_answer(), _answer(_value(entries=_entries()))):
        strings = [answer.name, answer.error or "", answer.error_summary or "", *answer.limitations]
        for fact in answer.facts:
            strings.extend([fact.label, fact.display_value, *fact.evidence, *fact.limitations])
        text = " ".join(strings).lower()
        assert "predict" not in text and "validated" in text.replace("unvalidated", "validated")


# --- a score with no number -------------------------------------------------------------------------------------------------------


def _refused():
    return _answer(_value(entries=_entries(_descriptor("mol_logp", 3.5))))


def test_a_score_with_no_number_is_a_refusal_in_the_applications_own_vocabulary():
    answer = _refused()
    assert answer.facts == () and answer.cache_state is CacheState.FAILED
    assert refusal_kind_of_result(answer) is RefusalKind.NEEDS_INPUT and status_of(answer) == NEEDS_INPUT
    assert answer.provenance.parameters["refusal"] == REFUSAL_CODE


def test_the_reason_names_the_input_that_could_not_be_read_and_why():
    answer = _refused()
    assert "psa (descriptor:tpsa)" in answer.error and "has not been calculated for this molecule" in answer.error
    assert answer.error_summary == f"{NO_VALUE}: an input cannot be read"


def test_the_formula_and_the_definition_are_said_as_one_sentence_when_there_is_no_number():
    """The reader joins the limitations with spaces, so each must read as a sentence; evidence lines stuffed in here ran together ("Formula: ob ob (...)")."""
    answer = _refused()
    assert answer.limitations == (
        f"Formula ramp(psa, hi, 60) * ramp(logp, 5, 2) (declared unit 1; definition {_definition().digest}).", LIMITATION
    )
    assert all(text.endswith(".") for text in answer.limitations)
    assert "psa (descriptor:tpsa)" in answer.error, "the unread input is named in the reason"


def test_a_refused_score_still_carries_its_label_and_provenance():
    answer = _refused()
    assert answer.name == "Window blend (user-defined, unvalidated)" and answer.provenance.created_by == "user"
    assert answer.provenance.parameters["validation"] == VALIDATION and answer.digest == _definition().digest


def test_a_definition_that_no_longer_checks_is_a_refusal_with_its_reason():
    value = _value(_definition(inputs=(("psa", "descriptor:gone"), ("logp", "descriptor:mol_logp"))))
    answer = _answer(value)
    assert answer.cache_state is CacheState.FAILED and "no longer checks" in answer.error and "not an approved output" in answer.error


# --- several scores, and the category ----------------------------------------------------------------------------------------------


def test_scores_come_back_in_the_order_the_definitions_were_made():
    first, second = _value(_definition(score_id="user.one", label="One")), _value(_definition(score_id="user.two", label="Two"))
    answers = project_score_answers([first, second], viewing="m", structure_version=0)
    assert [a.score_id for a in answers] == ["user.one", "user.two"]
    assert project_score_answers([], viewing="m", structure_version=0) == ()


def test_the_derived_category_is_ordered_last_labelled_and_open_by_default():
    assert CATEGORY_ORDER[-1] is FactCategory.DERIVED and CATEGORY_LABELS[FactCategory.DERIVED] == "Derived scores"
    assert FactCategory.DERIVED in DEFAULT_EXPANDED and FactCategory.DERIVED.value == "derived"


def test_the_codes_and_texts_are_these_literals():
    """Pinned as literals: a test that reads them by name moves with a mutant that changes them."""
    from openchem.domain.score_answer import SIGNIFICANT_DIGITS

    assert (REFUSAL_CODE, NO_VALUE, SIGNIFICANT_DIGITS) == ("SCORE_NO_VALUE", "no value", 4)
    assert _refused().provenance.parameters["refusal"] == "SCORE_NO_VALUE"
    assert _refused().error_summary == "no value: an input cannot be read"


# --- a number that used a default says so, wherever it is read ----------------------------------------------------------------------


def _defaulting(**defaults) -> ScoreDefinition:
    return _definition(on_missing=ON_MISSING_DEFAULT, schema_version=FORMAT_DEFAULTS, defaults=tuple(defaults.items()))


def _used_a_default() -> ScoreAnswer:
    return _answer(_value(_defaulting(logp=3.5), _entries(_descriptor("tpsa", 100.0, "Å²"))))


def test_a_number_that_used_a_default_says_so_in_its_value_its_evidence_and_its_limitations():
    answer = _used_a_default()
    (fact,) = answer.facts
    assert fact.value == pytest.approx(0.25) and isinstance(fact.value, float), "the number is kept whole and numeric"
    assert fact.display_value.endswith("(default used for logp)") and fact.display_value.startswith("0.25")
    said = DEFAULTED.format(names="logp")
    assert said in fact.evidence and fact.limitations == (LIMITATION, said) and answer.limitations == (LIMITATION, said)
    assert any(line.startswith("logp = 3.5") and "A DEFAULT of this definition" in line and "not a result" in line for line in fact.evidence)
    assert any(line.startswith("psa = 100") and "read from the stored result" in line for line in fact.evidence), "the input that was read is still told as one"
    assert answer.provenance.parameters["defaulted"] == ["logp"] and answer.provenance.parameters["schema_version"] == 2


def test_a_number_that_used_no_default_is_told_exactly_as_before():
    answer = _answer()
    (fact,) = answer.facts
    assert "default" not in fact.display_value and fact.limitations == (LIMITATION,) and answer.limitations == (LIMITATION,)
    assert "defaulted" not in answer.provenance.parameters
    assert not any("DEFAULT" in line or "default" in line for line in fact.evidence)


def test_a_score_with_a_default_that_was_not_needed_is_told_as_a_score_that_used_none():
    answer = _answer(_value(_defaulting(logp=5.0)))
    (fact,) = answer.facts
    assert "default" not in fact.display_value and fact.limitations == (LIMITATION,) and "defaulted" not in answer.provenance.parameters


def test_a_score_that_would_be_worked_out_from_defaults_alone_is_the_refusal_it_always_was():
    answer = _answer(_value(_defaulting(psa=100.0, logp=3.5), _entries()))
    assert answer.facts == () and "defaults alone" in answer.error and answer.error_summary.startswith(NO_VALUE)
    assert refusal_kind_of_result(answer) is RefusalKind.NEEDS_INPUT
    assert "defaulted" not in answer.provenance.parameters, "there is no number, so no number used a default"
