"""The value of a derived score for one molecule: what it reads, what it refuses, and the evidence either way (`domain/score_value.py`).

The rule under test is the design record's section 7: an input is read from the molecule's CURRENT results only, a refused, failed or absent input refuses
the score naming the input and why, and there is never a zero and never a skipped term. Every way an input can fail to be read is its own case, and
each is checked to refuse WITHOUT a number, because a score that returns a number when an input could not be read is the failure this module exists to
prevent.
"""

from __future__ import annotations

import math

import pytest

from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.score_constants import Constant
from openchem.domain.score_definition import FORMAT_DEFAULTS, ON_MISSING_DEFAULT, ScoreDefinition
from openchem.domain.score_value import (
    InputState,
    ScoreStatus,
    evaluate_score,
    read_output,
)
from openchem.domain.turn_snapshot import Freshness, Outcome, classify_results

_FP = {"drawing": "fp-now", "geometry": "gfp-now"}


def _identity(result_id, producer, *, calculation_input="drawing", fingerprint="fp-now", parameters_key=""):
    return ResultIdentity("m", result_id, calculation_input, fingerprint, producer, parameters_key)


def _descriptor(descriptor_id, value, units="", *, state=CacheState.COMPLETED, error=None, fingerprint="fp-now", calculation_input="drawing"):
    result = DescriptorValue(descriptor_id, descriptor_id, units, "c", "rdkit", "m", value=value, cache_state=state, error=error)
    return StoredResult(_identity(f"descriptor:rdkit:{descriptor_id}", "rdkit", calculation_input=calculation_input, fingerprint=fingerprint), result)


def _fact(label, value, units=""):
    return Fact(FactCategory.STRUCTURE, label, value, str(value), "test", Basis.DETERMINISTIC, units=units)


def _report(calculator_id, *facts, state=CacheState.COMPLETED, error=None, parameters_key="", fingerprint="fp-now", inapplicable=False):
    result = ReportResult(
        molecule_uuid="m", report_id=calculator_id, name=calculator_id, facts=tuple(facts), cache_state=state, error=error, inapplicable=inapplicable
    )
    return StoredResult(_identity(calculator_id, calculator_id, parameters_key=parameters_key, fingerprint=fingerprint), result)


def _entries(*stored, fresh=None):
    """Classified results. Every record is `fresh` (the one the application would replay) unless `fresh` says which are."""
    chosen = list(stored) if fresh is None else list(fresh)
    return classify_results(list(stored), chosen, _FP)


def _definition(formula="ramp(psa, 140, 60) * ramp(logp, 5, 2)", inputs=(("psa", "descriptor:tpsa"), ("logp", "descriptor:mol_logp")), **extra):
    return ScoreDefinition(
        score_id="user.test", label="Tester", formula=formula, result_unit=extra.pop("result_unit", "1"), inputs=tuple(inputs), **extra
    )


def _good():
    return _entries(_descriptor("tpsa", 100.0, "Å²"), _descriptor("mol_logp", 3.5, ""))


# --- the value, and the evidence behind it --------------------------------------------------------------------------------------


def test_a_score_with_every_input_current_has_a_value_and_its_evidence():
    value = evaluate_score(_definition(), _good())
    assert value.status is ScoreStatus.VALUE and value.reason == ""
    assert value.value == pytest.approx(0.5 * 0.5)
    assert value.unit == "1" and value.digest == _definition().digest
    assert value.formula == "ramp(psa, 140, 60) * ramp(logp, 5, 2)"
    by_name = {item.name: item for item in value.inputs}
    assert by_name["psa"].state is InputState.READ and by_name["psa"].value == 100.0
    assert by_name["psa"].output_id == "descriptor:tpsa" and by_name["psa"].unit == "Å^2" and by_name["psa"].carried_as == "Å²"
    assert by_name["psa"].result_id == "descriptor:rdkit:tpsa"
    assert [item.name for item in value.inputs] == ["psa", "logp"]


def test_an_input_that_is_zero_is_a_number_and_not_a_missing_input():
    entries = _entries(_descriptor("tpsa", 0.0, "Å²"))
    value = evaluate_score(_definition("psa", (("psa", "descriptor:tpsa"),), result_unit="Å^2"), entries)
    assert value.status is ScoreStatus.VALUE and value.value == 0.0
    assert value.inputs[0].state is InputState.READ and value.inputs[0].value == 0.0


def test_constants_are_part_of_the_value():
    definition = _definition("ramp(psa, hi, lo)", (("psa", "descriptor:tpsa"),), constants=(Constant("hi", 140, "Å^2"), Constant("lo", 60, "Å^2")))
    value = evaluate_score(definition, _entries(_descriptor("tpsa", 100.0, "Å²")))
    assert value.status is ScoreStatus.VALUE and value.value == pytest.approx(0.5)


def test_a_calculators_fact_is_read_by_its_label():
    definition = _definition("ob / 100", (("ob", "calculator:oxygen_balance:Oxygen balance (CO basis)"),), result_unit="1")
    entries = _entries(_report("oxygen_balance", _fact("Oxygen balance (CO basis)", -80.0, "%"), _fact("Formula", "C9H8O4")))
    value = evaluate_score(definition, entries)
    assert value.status is ScoreStatus.REFUSED, "a percent is not dimensionless, so a bare ratio of it is not declared 1"
    definition = _definition("ob", (("ob", "calculator:oxygen_balance:Oxygen balance (CO basis)"),), result_unit="%")
    value = evaluate_score(definition, entries)
    assert value.status is ScoreStatus.VALUE and value.value == -80.0 and value.inputs[0].result_id == "oxygen_balance"


# --- an input that cannot be read refuses the score, and never becomes a number --------------------------------------------------


def _refused_with(entries, state, fragment, name="psa"):
    value = evaluate_score(_definition(), entries)
    assert value.status is ScoreStatus.REFUSED and value.value is None
    item = {i.name: i for i in value.inputs}[name]
    assert item.state is state and item.value is None, item
    assert name in value.reason and "descriptor:tpsa" in value.reason and fragment in value.reason, value.reason
    return value


def test_an_input_nothing_was_calculated_for_refuses_naming_it():
    _refused_with(_entries(_descriptor("mol_logp", 3.5)), InputState.NOT_RUN, "has not been calculated for this molecule")


def test_a_result_from_an_earlier_structure_is_not_used():
    entries = _entries(_descriptor("tpsa", 100.0, "Å²", fingerprint="fp-OLD"), _descriptor("mol_logp", 3.5))
    _refused_with(entries, InputState.NOT_CURRENT, "earlier structure")


def test_a_result_with_no_fingerprint_is_not_vouched_for():
    entries = _entries(_descriptor("tpsa", 100.0, "Å²", fingerprint=""), _descriptor("mol_logp", 3.5))
    _refused_with(entries, InputState.NOT_CURRENT, "no input fingerprint")


def test_a_superseded_record_is_not_used_though_its_fingerprint_matches():
    old, new = _descriptor("tpsa", 90.0, "Å²"), _descriptor("mol_logp", 3.5)
    entries = _entries(old, new, fresh=[new])
    _refused_with(entries, InputState.NOT_CURRENT, "superseded")


def test_a_refused_input_keeps_the_methods_own_reason():
    entries = _entries(
        _descriptor("tpsa", None, "Å²", state=CacheState.FAILED, error="needs a 3D conformer"), _descriptor("mol_logp", 3.5)
    )
    value = _refused_with(entries, InputState.FAILED, "needs a 3D conformer")
    assert {i.name: i for i in value.inputs}["psa"].result_id == "descriptor:rdkit:tpsa"


def test_a_calculators_refusal_is_a_refusal_and_not_a_missing_fact():
    definition = _definition("ob", (("ob", "calculator:oxygen_balance:Oxygen balance (CO basis)"),), result_unit="%")
    entries = _entries(_report("oxygen_balance", state=CacheState.FAILED, error="no oxygen balance for this molecule", inapplicable=True))
    value = evaluate_score(definition, entries)
    assert value.status is ScoreStatus.REFUSED and value.inputs[0].state is InputState.REFUSED
    assert "no oxygen balance for this molecule" in value.reason


def test_a_computed_report_without_the_fact_is_a_missing_fact():
    definition = _definition("ob", (("ob", "calculator:oxygen_balance:Oxygen balance (CO basis)"),), result_unit="%")
    value = evaluate_score(definition, _entries(_report("oxygen_balance", _fact("Formula", "C9H8O4"))))
    assert value.status is ScoreStatus.REFUSED and value.inputs[0].state is InputState.MISSING_FACT and "holds the fact" in value.reason


def test_a_fact_held_twice_is_a_missing_fact_and_not_the_first_of_them():
    definition = _definition("ob", (("ob", "calculator:oxygen_balance:Oxygen balance (CO basis)"),), result_unit="%")
    both = _report("oxygen_balance", _fact("Oxygen balance (CO basis)", -80.0, "%"), _fact("Oxygen balance (CO basis)", -10.0, "%"))
    value = evaluate_score(definition, _entries(both))
    assert value.inputs[0].state is InputState.MISSING_FACT and value.value is None


@pytest.mark.parametrize("bad", ["63.60", True, None, math.nan, math.inf, [1.0]])
def test_a_value_the_producer_did_not_type_as_a_finite_number_is_not_used(bad):
    entries = _entries(_descriptor("tpsa", bad, "Å²"), _descriptor("mol_logp", 3.5))
    value = evaluate_score(_definition(), entries)
    assert value.status is ScoreStatus.REFUSED and {i.name: i for i in value.inputs}["psa"].state is InputState.NOT_A_NUMBER


@pytest.mark.parametrize("carried", ["A^2", "", "Å", "nm²"])
def test_a_result_carrying_another_unit_is_refused_and_nothing_is_converted(carried):
    entries = _entries(_descriptor("tpsa", 100.0, carried), _descriptor("mol_logp", 3.5))
    value = evaluate_score(_definition(), entries)
    item = {i.name: i for i in value.inputs}["psa"]
    assert value.status is ScoreStatus.REFUSED and item.state is InputState.UNIT and item.carried_as == carried
    assert "nothing is converted" in value.reason


def test_only_the_drawing_is_read():
    """The always-on descriptors are stored for the drawing and for a geometry under one id; a score reads the drawing's and never the geometry's."""
    only_geometry = _entries(_descriptor("tpsa", 100.0, "Å²", calculation_input="geometry"), _descriptor("mol_logp", 3.5))
    _refused_with(only_geometry, InputState.NOT_RUN, "has not been calculated")
    both = _entries(
        _descriptor("tpsa", 100.0, "Å²"), _descriptor("tpsa", 999.0, "Å²", calculation_input="geometry"), _descriptor("mol_logp", 3.5)
    )
    assert evaluate_score(_definition(), both).value == pytest.approx(0.25), "the geometry's 999 is never read"


def test_every_unread_input_is_named_not_only_the_first():
    value = evaluate_score(_definition(), _entries())
    assert value.status is ScoreStatus.REFUSED
    assert "psa (descriptor:tpsa)" in value.reason and "logp (descriptor:mol_logp)" in value.reason
    assert [i.state for i in value.inputs] == [InputState.NOT_RUN, InputState.NOT_RUN]


def test_a_missing_term_is_not_skipped_even_when_the_rest_could_be_summed():
    definition = _definition("psa + psa2", (("psa", "descriptor:tpsa"), ("psa2", "descriptor:labute_asa")), result_unit="Å^2")
    value = evaluate_score(definition, _entries(_descriptor("tpsa", 100.0, "Å²")))
    assert value.status is ScoreStatus.REFUSED and value.value is None


# --- two current results that disagree --------------------------------------------------------------------------------------------


def test_two_current_results_with_different_numbers_are_not_guessed_between():
    one = _report("solubility", _fact("Predicted intrinsic solubility (mol/L)", 0.001, "mol/L"), parameters_key="ph7")
    two = _report("solubility", _fact("Predicted intrinsic solubility (mol/L)", 0.002, "mol/L"), parameters_key="ph6")
    definition = _definition("s", (("s", "calculator:solubility:Predicted intrinsic solubility (mol/L)"),), result_unit="mol/L")
    value = evaluate_score(definition, _entries(one, two))
    assert value.status is ScoreStatus.REFUSED and value.inputs[0].state is InputState.AMBIGUOUS and "cannot tell which was meant" in value.reason


def test_two_current_results_that_agree_are_read_once():
    one = _report("solubility", _fact("Predicted intrinsic solubility (mol/L)", 0.001, "mol/L"), parameters_key="a")
    two = _report("solubility", _fact("Predicted intrinsic solubility (mol/L)", 0.001, "mol/L"), parameters_key="b")
    definition = _definition("s", (("s", "calculator:solubility:Predicted intrinsic solubility (mol/L)"),), result_unit="mol/L")
    value = evaluate_score(definition, _entries(one, two))
    assert value.status is ScoreStatus.VALUE and value.value == 0.001


def test_a_current_result_wins_over_a_historical_one_for_the_same_output():
    old = _descriptor("tpsa", 55.0, "Å²", fingerprint="fp-OLD")
    value = evaluate_score(_definition(), _entries(old, _descriptor("tpsa", 100.0, "Å²"), _descriptor("mol_logp", 3.5)))
    assert value.status is ScoreStatus.VALUE and value.inputs[0].value == 100.0


# --- the definition and the evaluation can refuse too ------------------------------------------------------------------------------


def test_a_definition_that_no_longer_checks_refuses_with_its_reason_and_no_evidence():
    definition = _definition("psa", (("psa", "descriptor:not_an_output"),))
    value = evaluate_score(definition, _good())
    assert value.status is ScoreStatus.REFUSED and value.value is None and value.inputs == () and value.formula == ""
    assert "no longer checks" in value.reason and "not an approved output" in value.reason


def test_a_label_that_now_looks_like_a_name_does_not_refuse_the_value():
    definition = ScoreDefinition(
        score_id="user.x", label="TPSA", formula="ramp(psa, 140, 60)", result_unit="1", inputs=(("psa", "descriptor:tpsa"),)
    )
    assert evaluate_score(definition, _entries(_descriptor("tpsa", 100.0, "Å²"))).status is ScoreStatus.VALUE


def test_a_step_the_evaluator_refuses_names_the_step_and_keeps_the_evidence():
    definition = _definition("1 / (psa - 100)", (("psa", "descriptor:tpsa"),), result_unit="1/Å^2")
    value = evaluate_score(definition, _entries(_descriptor("tpsa", 100.0, "Å²")))
    assert value.status is ScoreStatus.REFUSED and value.value is None
    assert "division by zero" in value.reason and "1 / (psa - 100)" in value.reason
    assert value.inputs[0].state is InputState.READ and value.inputs[0].value == 100.0


def test_a_result_the_evaluator_cannot_represent_is_refused_and_never_returned_as_infinity():
    definition = _definition("exp(logp ^ 2 * 1000)", (("logp", "descriptor:mol_logp"),))
    value = evaluate_score(definition, _entries(_descriptor("mol_logp", 3.5)))
    assert value.status is ScoreStatus.REFUSED and value.value is None


# --- read_output on its own ----------------------------------------------------------------------------------------------------


def test_read_output_of_an_output_that_is_not_approved_says_so():
    read = read_output("descriptor:formal_charge", _good())
    assert read.state is InputState.NOT_APPROVED and read.value is None


def test_read_output_classes_come_from_the_assistants_one_rule_for_current():
    entries = _good()
    assert {e.freshness for e in entries} == {Freshness.CURRENT} and {e.outcome for e in entries} == {Outcome.COMPUTED}
    assert read_output("descriptor:tpsa", entries).state is InputState.READ


def test_another_calculators_results_are_not_this_outputs():
    """Reading an output looks at the records of what produces it. A report from a different calculator, however current, is not a record of this one."""
    definition = _definition("ob", (("ob", "calculator:oxygen_balance:Oxygen balance (CO basis)"),), result_unit="%")
    other = _report("solubility", _fact("Oxygen balance (CO basis)", -80.0, "%"))
    value = evaluate_score(definition, _entries(other, _descriptor("tpsa", 100.0, "\u00c5\u00b2")))
    assert value.status is ScoreStatus.REFUSED and value.inputs[0].state is InputState.NOT_RUN and value.value is None


def test_another_descriptors_results_are_not_this_outputs():
    value = evaluate_score(_definition(), _entries(_descriptor("labute_asa", 100.0, "\u00c5\u00b2"), _descriptor("mol_logp", 3.5)))
    assert {i.name: i for i in value.inputs}["psa"].state is InputState.NOT_RUN


# --- the second policy: a default stands in for an input nobody calculated, and for nothing else ----------------------------------


def _defaulting(**defaults) -> ScoreDefinition:
    """The usual two-input score, declaring these defaults (by input name)."""
    return _definition(on_missing=ON_MISSING_DEFAULT, schema_version=FORMAT_DEFAULTS, defaults=tuple(defaults.items()))


def test_an_input_nobody_calculated_takes_the_default_the_definition_declares_and_says_so():
    value = evaluate_score(_defaulting(logp=5.0), _entries(_descriptor("tpsa", 100.0, "Å²")))
    assert value.status is ScoreStatus.VALUE and value.reason == ""
    assert value.value == pytest.approx(0.5 * 0.0), "ramp(5, 5, 2) is 0: the default is what the formula read"
    by_name = {item.name: item for item in value.inputs}
    assert by_name["psa"].state is InputState.READ and by_name["logp"].state is InputState.DEFAULT
    assert by_name["logp"].value == 5.0 and by_name["logp"].unit == "1" and by_name["logp"].result_id == ""
    assert "not calculated for this molecule" in by_name["logp"].note and "default of 5 is used" in by_name["logp"].note
    assert [item.name for item in value.defaulted] == ["logp"] and value.defaulted[0] is by_name["logp"]


def test_the_default_is_what_the_formula_reads_and_a_changed_default_changes_the_number():
    entries = _entries(_descriptor("tpsa", 100.0, "Å²"))
    assert evaluate_score(_defaulting(logp=2.0), entries).value == pytest.approx(0.5 * 1.0)
    assert evaluate_score(_defaulting(logp=3.5), entries).value == pytest.approx(0.5 * 0.5)


def test_a_default_of_zero_is_a_declared_number_and_is_marked_like_any_other():
    value = evaluate_score(_defaulting(logp=0.0), _entries(_descriptor("tpsa", 100.0, "Å²")))
    assert value.status is ScoreStatus.VALUE and value.defaulted[0].value == 0.0 and value.defaulted[0].state is InputState.DEFAULT


def test_a_result_that_exists_is_read_and_the_default_is_not_used():
    value = evaluate_score(_defaulting(logp=5.0), _good())
    assert value.status is ScoreStatus.VALUE and value.defaulted == ()
    assert {i.name: i for i in value.inputs}["logp"].state is InputState.READ
    assert value.value == evaluate_score(_definition(), _good()).value == pytest.approx(0.25), "a default never overrides what was calculated"


@pytest.mark.parametrize(
    "entries, state, fragment",
    [
        (_entries(_descriptor("tpsa", 100.0, "Å²"), _descriptor("mol_logp", 3.5, "", fingerprint="fp-OLD")), InputState.NOT_CURRENT, "earlier structure"),
        (_entries(_descriptor("tpsa", 100.0, "Å²"), _descriptor("mol_logp", None, "", state=CacheState.FAILED, error="needs a 3D conformer")), InputState.FAILED, "needs a 3D conformer"),
        (_entries(_descriptor("tpsa", 100.0, "Å²"), _descriptor("mol_logp", "3.5", "")), InputState.NOT_A_NUMBER, "number"),
        (_entries(_descriptor("tpsa", 100.0, "Å²"), _descriptor("mol_logp", 3.5, "mol/L")), InputState.UNIT, "nothing is converted"),
    ],
)
def test_a_default_never_stands_in_for_an_answer_about_this_molecule(entries, state, fragment):
    """An input that WAS calculated and refused, failed, belongs to an earlier structure or carries another unit is an answer; a default would hide it."""
    value = evaluate_score(_defaulting(logp=2.0), entries)
    item = {i.name: i for i in value.inputs}["logp"]
    assert value.status is ScoreStatus.REFUSED and value.value is None and value.defaulted == ()
    assert item.state is state and fragment in value.reason and "logp" in value.reason


def test_a_declined_calculator_is_not_defaulted_either():
    definition = _definition(
        "ob + ob2", (("ob", "calculator:oxygen_balance:Oxygen balance (CO basis)"), ("ob2", "calculator:oxygen_balance:Oxygen balance (CO₂ basis)")), result_unit="%",
        on_missing=ON_MISSING_DEFAULT, schema_version=FORMAT_DEFAULTS, defaults=(("ob", -50.0),),
    )
    entries = _entries(_report("oxygen_balance", state=CacheState.FAILED, error="no oxygen balance for this molecule", inapplicable=True))
    value = evaluate_score(definition, entries)
    assert value.status is ScoreStatus.REFUSED and {i.name: i for i in value.inputs}["ob"].state is InputState.REFUSED
    assert "no oxygen balance for this molecule" in value.reason


def test_a_score_worked_out_from_defaults_alone_is_refused_and_says_so():
    value = evaluate_score(_defaulting(psa=100.0, logp=3.5), _entries())
    assert value.status is ScoreStatus.REFUSED and value.value is None
    assert "defaults alone" in value.reason and "psa (descriptor:tpsa)" in value.reason and "logp (descriptor:mol_logp)" in value.reason
    assert [i.state for i in value.inputs] == [InputState.DEFAULT, InputState.DEFAULT], "the evidence still says what each input was"


def test_an_input_with_no_default_still_refuses_when_nobody_calculated_it():
    value = evaluate_score(_defaulting(logp=2.0), _entries(_descriptor("mol_logp", 3.5)))
    assert value.status is ScoreStatus.REFUSED and {i.name: i for i in value.inputs}["psa"].state is InputState.NOT_RUN
    assert "psa (descriptor:tpsa)" in value.reason and "logp (descriptor:mol_logp)" not in value.reason, "only the input with no default is named"


def test_a_default_is_not_applied_unless_the_definition_says_it_is_the_second_policy():
    """A stored definition whose policy is something this build does not know is read as the first one: its defaults are never used."""
    odd = _definition(on_missing="zero", defaults=(("logp", 2.0),))
    value = evaluate_score(odd, _entries(_descriptor("tpsa", 100.0, "Å²")))
    assert value.status is ScoreStatus.REFUSED and value.defaulted == ()
    first = _definition(on_missing="refuse", defaults=(("logp", 2.0),))
    assert evaluate_score(first, _entries(_descriptor("tpsa", 100.0, "Å²"))).status is ScoreStatus.REFUSED


def test_a_default_for_a_name_the_definition_has_no_input_for_is_ignored():
    value = evaluate_score(_defaulting(ghost=1.0), _entries(_descriptor("tpsa", 100.0, "Å²")))
    assert value.status is ScoreStatus.REFUSED and value.defaulted == ()


def test_a_score_with_no_defaults_has_none_defaulted():
    assert evaluate_score(_definition(), _good()).defaulted == ()
