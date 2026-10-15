"""The approved outputs a derived score may name, and the rules that live on them (`docs/DERIVED_SCORES_DESIGN.md` sections 3, 6 and 7).

Three groups, in the order they are cheapest:

* **The table itself**, with no registry: every entry is well formed, every unit parses, every endpoint is on the reviewed list and
  used, and the two rules on it (an output that is not approved is refused; two outputs of one endpoint are refused, which is
  "consensus is unexpressible") hold on the REAL pairs the table contains and not only on invented ones.
* **The sweep's own rules**, with invented results: a bool, a string, a non-finite number and a failed result are not candidates,
  and every way an entry can be wrong is reported (`entry_problems`), so a green run means something.
* **The table against the registry**, on the census panel: each entry resolves, through the application's own path, to a finite
  number carrying the units it declares, from a calculator that is stable or limited and offered by default. A rename of a fact label
  turns this red and says which scores it breaks. The control arms run REAL calculators that must be refused (a hidden one, and one whose
  numbers are text rounded by a setting), because a guard that has never failed is unproven.
"""

from __future__ import annotations

import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.score_formula import (
    FormulaError,
    Problem,
    Refusal,
    check_definition,
    evaluate,
)
from openchem.domain.score_outputs import (
    APPROVED,
    ENDPOINTS,
    READ_FROM,
    ApprovedOutput,
    accept_value,
    approved_output,
    check_inputs,
    unit_of,
    values_by_name,
)
from openchem.domain.score_units import DIMENSIONLESS, SYMBOLS, parse_unit

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))
import sweep_score_outputs as sweep_tool  # noqa: E402

#: The calculators the table draws from, plus the two controls: `joback_properties` is limited and HIDDEN by default, and
#: `polar_surface_area` carries its number as text rounded by the decimal-places setting.
_CALCULATORS_UNDER_TEST = ["oxygen_balance", "solubility", "joback_properties", "polar_surface_area", "logd"]


def _entry(**changes) -> ApprovedOutput:
    return replace(approved_output("descriptor:mol_wt"), **changes)


# --- the table itself ---------------------------------------------------------------------------------------------------------


def test_the_table_is_sorted_and_has_no_duplicate_id():
    ids = [entry.output_id for entry in APPROVED]
    assert ids == sorted(ids), "keep the table sorted by id, so a review diff reads as additions"
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("entry", APPROVED, ids=lambda e: e.output_id)
def test_every_entry_is_well_formed(entry):
    # The id is a batch column id: `descriptor:<id>` or `calculator:<calculator id>:<label>`.
    kind, _, rest = entry.output_id.partition(":")
    assert kind in ("descriptor", "calculator"), entry.output_id
    if kind == "calculator":
        calculator_id, _, label = rest.partition(":")
        assert calculator_id and label, entry.output_id
    else:
        assert rest and ":" not in rest, entry.output_id
    # The unit is written in the language of `score_units`, and an unlabelled number can only be dimensionless.
    parsed = parse_unit(entry.unit)
    assert unit_of(entry) == parsed
    assert unit_of(entry).parts == () or entry.carried_as != "", "a unit with symbols cannot be carried as no unit at all"
    if entry.carried_as == "":
        assert parsed == DIMENSIONLESS, f"{entry.output_id} carries no unit and so can only be declared as 1"
    assert entry.endpoint in ENDPOINTS
    assert len(entry.approved) == 10 and entry.approved[4] == entry.approved[7] == "-"
    assert READ_FROM == "drawing"


def test_every_unit_symbol_an_entry_uses_is_in_the_symbol_list():
    used = {symbol for entry in APPROVED for symbol, _ in unit_of(entry).parts}
    assert used <= SYMBOLS
    assert {"Å", "g", "mol", "L", "mg", "mL", "%"} <= used, "the table exercises every non-trivial unit it was built to spell"


def test_every_endpoint_tag_is_used_and_described():
    used = {entry.endpoint for entry in APPROVED}
    assert used == set(ENDPOINTS), f"unused tags: {sorted(set(ENDPOINTS) - used)}"
    for tag, description in ENDPOINTS.items():
        assert tag == tag.lower() and " " not in tag
        assert description.strip() and description == description.strip()


#: Which approved outputs estimate one quantity, written out. **THIS IS A REVIEW, NOT A TAUTOLOGY**: the endpoint tags are a person's
#: judgement and are what make a consensus unexpressible, so changing which outputs share one has to be done on purpose, here, where a reviewer
#: sees it. A wrong tag is a wrong guard; moving an output into or out of a group changes what the application will refuse to combine.
_SHARED_ENDPOINTS = {
    "aqueous_solubility_intrinsic": [
        "calculator:solubility:Predicted intrinsic solubility (mg/mL)",
        "calculator:solubility:Predicted intrinsic solubility (mol/L)",
        "descriptor:esol_logs",
    ],
}

#: The unit of every approved output, written out for the same reason: it decides what a formula over it may add and what it works out to.
_UNITS = {
    "calculator:oxygen_balance:Oxygen balance (CO basis)": "%",
    "calculator:oxygen_balance:Oxygen balance (CO₂ basis)": "%",
    "calculator:solubility:Predicted intrinsic solubility (mg/mL)": "mg/mL",
    "calculator:solubility:Predicted intrinsic solubility (mol/L)": "mol/L",
    "descriptor:bertz_ct": "1", "descriptor:esol_logs": "1", "descriptor:exact_mass": "g/mol", "descriptor:fsp3": "1",
    "descriptor:heavy_atom_count": "1", "descriptor:labute_asa": "Å^2", "descriptor:mol_logp": "1", "descriptor:mol_wt": "g/mol",
    "descriptor:np_likeness": "1", "descriptor:num_hba": "1", "descriptor:num_hbd": "1", "descriptor:num_rotatable_bonds": "1",
    "descriptor:num_stereocenters": "1", "descriptor:qed": "1", "descriptor:ring_count": "1", "descriptor:sa_score": "1",
    "descriptor:tpsa": "Å^2",
}


def test_the_outputs_that_share_an_endpoint_are_exactly_these():
    by_tag: dict[str, list[str]] = {}
    for entry in APPROVED:
        by_tag.setdefault(entry.endpoint, []).append(entry.output_id)
    assert {tag: sorted(ids) for tag, ids in by_tag.items() if len(ids) > 1} == _SHARED_ENDPOINTS


def test_the_unit_of_every_approved_output_is_exactly_this():
    assert {entry.output_id: entry.unit for entry in APPROVED} == _UNITS


# --- an output that is not approved is refused ------------------------------------------------------------------------------


def test_an_approved_output_is_accepted_with_its_unit():
    units = check_inputs([("mw", "descriptor:mol_wt"), ("psa", "descriptor:tpsa")])
    assert list(units) == ["mw", "psa"]
    assert str(units["mw"]) == "g/mol" and str(units["psa"]) == "Å^2"


@pytest.mark.parametrize(
    "output_id",
    [
        "descriptor:logp",  # not a descriptor id
        "descriptor:MOL_WT",  # case matters
        "descriptor:mol_wt ",  # whitespace matters
        "calculator:joback_properties:Boiling point (normal)",  # a real output of a hidden calculator
        "calculator:polar_surface_area:Polar surface area",  # a real output that is text
        "calculator:oxygen_balance:Oxygen balance (CO2 basis)",  # the label spelled with an ASCII 2
        "mol_wt",
        "",
    ],
)
def test_an_output_that_is_not_approved_is_refused(output_id):
    with pytest.raises(FormulaError) as caught:
        check_inputs([("x", output_id)])
    assert caught.value.problem is Problem.OUTPUT
    assert "not an approved output" in str(caught.value)


def test_a_bad_name_is_refused_before_the_outputs_are_looked_at():
    with pytest.raises(FormulaError) as caught:
        check_inputs([("Not-A-Name", "descriptor:not_approved")])
    assert caught.value.problem is Problem.INPUTS


def test_one_output_under_two_names_is_refused_as_a_duplicate_and_not_as_consensus():
    with pytest.raises(FormulaError) as caught:
        check_inputs([("a", "descriptor:mol_wt"), ("b", "descriptor:mol_wt")])
    assert caught.value.problem is Problem.INPUTS
    assert "same output" in str(caught.value)


# --- consensus is unexpressible ---------------------------------------------------------------------------------------------


def _pairs_sharing_an_endpoint():
    by_tag: dict[str, list[ApprovedOutput]] = {}
    for entry in APPROVED:
        by_tag.setdefault(entry.endpoint, []).append(entry)
    return [
        (a.output_id, b.output_id, tag)
        for tag, group in by_tag.items()
        for i, a in enumerate(group)
        for b in group[i + 1:]
    ]


@pytest.mark.parametrize("first, second, tag", _pairs_sharing_an_endpoint())
def test_two_outputs_of_one_endpoint_are_refused_whatever_order(first, second, tag):
    for pair in ([("a", first), ("b", second)], [("a", second), ("b", first)]):
        with pytest.raises(FormulaError) as caught:
            check_inputs(pair)
        assert caught.value.problem is Problem.CONSENSUS
        message = str(caught.value)
        assert first in message and second in message
        assert ENDPOINTS[tag] in message
        assert "consensus predictor" in message


def test_the_real_pair_a_person_would_try_is_stopped():
    """Two estimates of intrinsic aqueous solubility, the ESOL descriptor and the solubility calculator: the example the design gives."""
    with pytest.raises(FormulaError) as caught:
        check_inputs([
            ("esol", "descriptor:esol_logs"),
            ("model", "calculator:solubility:Predicted intrinsic solubility (mol/L)"),
        ])
    assert caught.value.problem is Problem.CONSENSUS


def test_outputs_of_different_endpoints_are_never_refused_as_consensus():
    one_per_tag = {}
    for entry in APPROVED:
        one_per_tag.setdefault(entry.endpoint, entry)
    chosen = list(one_per_tag.values())[:12]
    units = check_inputs([(f"x{i}", e.output_id) for i, e in enumerate(chosen)])
    assert len(units) == 12


def test_an_unapproved_output_is_reported_before_a_consensus():
    with pytest.raises(FormulaError) as caught:
        check_inputs([("a", "descriptor:esol_logs"), ("b", "descriptor:nope"), ("c", "calculator:solubility:Predicted intrinsic solubility (mol/L)")])
    assert caught.value.problem is Problem.OUTPUT


# --- a definition built on the table -------------------------------------------------------------------------------------------


def _definition(text, inputs, result="1"):
    units = check_inputs(inputs)
    return check_definition(text, units, parse_unit(result))


def test_a_threshold_on_an_approved_output_with_a_unit_is_writable():
    """The first thing a person types: a desirability on a topological polar surface area. A bare number takes the unit of the quantity."""
    inputs = [("psa", "descriptor:tpsa"), ("logp", "descriptor:mol_logp")]
    formula = _definition("ramp(psa, 140, 60) * ramp(logp, 5, 2)", inputs)
    values = values_by_name(inputs, {"descriptor:tpsa": (100.0, "Å²"), "descriptor:mol_logp": (3.5, "")})
    assert evaluate(formula, values) == pytest.approx(0.5 * 0.5)


def test_a_unit_mismatch_between_approved_outputs_is_refused_not_converted():
    with pytest.raises(FormulaError) as caught:
        _definition("mw + psa", [("mw", "descriptor:mol_wt"), ("psa", "descriptor:tpsa")], "g/mol")
    assert caught.value.problem is Problem.UNIT


def test_two_dimensionless_outputs_combine_and_evaluate_end_to_end():
    inputs = [("logp", "descriptor:mol_logp"), ("hbd", "descriptor:num_hbd"), ("qed", "descriptor:qed")]
    formula = _definition("ramp(logp, 5, 2) + qed - hbd / 10", inputs)
    read = {
        "descriptor:mol_logp": (3.5, ""),
        "descriptor:num_hbd": (2, ""),
        "descriptor:qed": (0.5, ""),
    }
    values = values_by_name(inputs, read)
    assert values == {"logp": 3.5, "hbd": 2.0, "qed": 0.5}
    assert evaluate(formula, values) == pytest.approx(0.5 + 0.5 - 0.2)


# --- reading a value: never converted, never coerced, never zero ----------------------------------------------------------------


def test_a_number_with_the_declared_units_is_accepted_and_an_int_is_a_float():
    assert accept_value(approved_output("descriptor:mol_wt"), 180, "g/mol") == 180.0
    assert isinstance(accept_value(approved_output("descriptor:mol_wt"), 180, "g/mol"), float)
    assert accept_value(approved_output("descriptor:tpsa"), 63.6, "Å²") == 63.6
    assert accept_value(approved_output("descriptor:qed"), 0.0, "") == 0.0


@pytest.mark.parametrize("value", [True, False, "63.60", None, [1.0], (1, 0), math.nan, math.inf, -math.inf])
def test_a_value_the_producer_did_not_type_as_a_finite_number_is_refused(value):
    with pytest.raises(Refusal):
        accept_value(approved_output("descriptor:mol_wt"), value, "g/mol")


@pytest.mark.parametrize("carried", ["", "kg/mol", "G/MOL", "g/mol ", "Da"])
def test_a_result_carrying_other_units_is_refused_and_nothing_is_converted(carried):
    with pytest.raises(Refusal) as caught:
        accept_value(approved_output("descriptor:mol_wt"), 180.0, carried)
    assert "nothing is converted" in str(caught.value)


def test_the_unit_the_application_spells_two_ways_accepts_only_the_declared_spelling():
    tpsa = approved_output("descriptor:tpsa")
    assert accept_value(tpsa, 63.6, "Å²") == 63.6
    for other in ("A^2", "Å^2", "A²", "Ų", ""):
        with pytest.raises(Refusal):
            accept_value(tpsa, 63.6, other)


def test_a_missing_input_refuses_the_score_and_is_never_a_zero():
    inputs = [("mw", "descriptor:mol_wt"), ("logp", "descriptor:mol_logp")]
    with pytest.raises(Refusal) as caught:
        values_by_name(inputs, {"descriptor:mol_wt": (180.0, "g/mol")})
    assert "descriptor:mol_logp" in str(caught.value) and "logp has no current result" in str(caught.value)


def test_a_wrong_unit_on_one_of_two_inputs_refuses_the_whole_read():
    inputs = [("mw", "descriptor:mol_wt"), ("logp", "descriptor:mol_logp")]
    with pytest.raises(Refusal):
        values_by_name(inputs, {"descriptor:mol_wt": (180.0, "g/mol"), "descriptor:mol_logp": (1.0, "log")})


def test_an_output_that_is_not_approved_cannot_be_read():
    with pytest.raises(Refusal):
        values_by_name([("x", "descriptor:nope")], {"descriptor:nope": (1.0, "")})


# --- the sweep's own rules, with invented results -----------------------------------------------------------------------------


def _stored(result, calculation_input="drawing") -> StoredResult:
    return StoredResult(ResultIdentity("m", "r", calculation_input, "f", "p"), result)


def _fact(label, value, units="") -> Fact:
    return Fact(FactCategory.STRUCTURE, label, value, str(value), "test", Basis.DETERMINISTIC, units=units)


def _descriptor(descriptor_id, value, units="", state=CacheState.COMPLETED) -> DescriptorValue:
    return DescriptorValue(descriptor_id, descriptor_id, units, "c", "p", "m", value=value, cache_state=state)


def _report(*facts, state=CacheState.COMPLETED) -> ReportResult:
    return ReportResult(molecule_uuid="m", report_id="r", name="R", facts=tuple(facts), cache_state=state)


def test_only_a_finite_typed_number_is_a_candidate():
    report = _report(
        _fact("int", 3), _fact("float", 2.5, "K"), _fact("bool", True), _fact("text", "63.60"),
        _fact("nan", math.nan), _fact("inf", math.inf), _fact("none", None), _fact("tuple", (1, 0)),
    )
    found = {row[0]: row[4] for row in sweep_tool.scalars_of("calc", [_stored(report)])}
    assert found == {
        "calculator:calc:int": 3.0, "calculator:calc:float": 2.5, "calculator:calc:bool": None, "calculator:calc:text": None,
        "calculator:calc:nan": None, "calculator:calc:inf": None, "calculator:calc:none": None, "calculator:calc:tuple": None,
    }


def test_a_failed_result_is_not_read_for_numbers():
    failed = _report(_fact("x", 1.0), state=CacheState.FAILED)
    assert sweep_tool.scalars_of("calc", [_stored(failed)]) == []
    assert sweep_tool.scalars_of("always_on", [_stored(_descriptor("d", 1.0, state=CacheState.FAILED))]) == []


def test_a_descriptor_and_a_report_fact_are_both_read_with_their_input_and_units():
    got = sweep_tool.scalars_of(
        "calc",
        [_stored(_descriptor("mol_wt", 180.0, "g/mol"), "geometry"), _stored(_report(_fact("Dipole", 1.5, "D")))],
    )
    assert got[0] == ("descriptor:mol_wt", "mol_wt", "descriptor", "mol_wt", 180.0, "g/mol", "geometry")
    assert got[1] == ("calculator:calc:Dipole", "Dipole", "calculator", "calc", 1.5, "D", "drawing")


class _Row:
    def __init__(self, row_id):
        self.id = row_id


def test_two_facts_with_one_label_in_a_report_make_the_id_ambiguous():
    sweep = sweep_tool.Sweep()
    sweep("calc", _Row("a"), [_stored(_report(_fact("Same", 1.0), _fact("Same", 2.0), _fact("Other", 3.0)))])
    assert sweep.candidates["calculator:calc:Same"].ambiguous
    assert not sweep.candidates["calculator:calc:Other"].ambiguous


def test_the_sweep_remembers_each_row_input_and_unit():
    sweep = sweep_tool.Sweep()
    sweep("always_on", _Row("a"), [_stored(_descriptor("d", 1.0, "u"), "drawing"), _stored(_descriptor("d", 1.0, "u"), "geometry")])
    sweep("always_on", _Row("b"), [_stored(_descriptor("d", 2.0, "u"), "drawing")])
    candidate = sweep.candidates["descriptor:d"]
    assert candidate.observations == [("a", "drawing", 1.0, "u"), ("a", "geometry", 1.0, "u"), ("b", "drawing", 2.0, "u")]
    assert candidate.carried == ["u"]


# --- entry_problems: every way an entry can be wrong, reported --------------------------------------------------------------


def _synthetic(output_id, *, rows=6, units="g/mol", calc_input="drawing", source="descriptor", source_id="mol_wt", ambiguous=False):
    sweep = sweep_tool.Sweep()
    candidate = sweep_tool.Candidate(output_id, "label", source, source_id, ambiguous=ambiguous)
    candidate.observations = [(f"row{i}", calc_input, 1.0 + i, units) for i in range(rows)]
    sweep.candidates[output_id] = candidate
    return sweep


_SUPPORT = {"c": {"stage": "stable", "visibility": "shown"}}


def _problems(entry, sweep, support=None):
    return sweep_tool.entry_problems(entry, sweep, {"support": support if support is not None else _SUPPORT})


def test_a_well_formed_entry_has_no_problem():
    assert _problems(_entry(), _synthetic("descriptor:mol_wt")) == []
    calc = _entry(output_id="calculator:c:Label")
    assert _problems(calc, _synthetic("calculator:c:Label", source="calculator", source_id="c")) == []


def test_every_problem_says_what_it_breaks():
    assert all("breaks every score" in p for p in _problems(_entry(), sweep_tool.Sweep()))
    assert all("breaks every score" in p for p in _problems(_entry(), _synthetic("descriptor:mol_wt", rows=1, units="kg")))


def test_a_missing_output_is_reported_as_renamed_or_removed():
    (problem,) = _problems(_entry(), sweep_tool.Sweep())
    assert "produced by no run" in problem and "renamed" in problem


def test_an_ambiguous_output_is_reported():
    problems = _problems(_entry(), _synthetic("descriptor:mol_wt", ambiguous=True))
    assert any("names no single number" in p for p in problems)


@pytest.mark.parametrize("stage", ["experimental", "unclassified"])
def test_an_output_of_an_unapprovable_stage_is_reported(stage):
    entry = _entry(output_id="calculator:c:Label")
    sweep = _synthetic("calculator:c:Label", source="calculator", source_id="c")
    problems = _problems(entry, sweep, {"c": {"stage": stage, "visibility": "shown"}})
    assert any(stage in p and "may be approved" in p for p in problems)


def test_an_output_hidden_by_default_is_reported():
    entry = _entry(output_id="calculator:c:Label")
    sweep = _synthetic("calculator:c:Label", source="calculator", source_id="c")
    problems = _problems(entry, sweep, {"c": {"stage": "limited", "visibility": "hidden"}})
    assert any("hidden by default" in p for p in problems)


def test_a_calculator_that_is_not_in_the_registry_is_reported():
    entry = _entry(output_id="calculator:gone:Label")
    sweep = _synthetic("calculator:gone:Label", source="calculator", source_id="gone")
    assert any("not a registry calculator" in p for p in _problems(entry, sweep))


def test_an_output_seen_only_on_the_geometry_is_reported():
    problems = _problems(_entry(), _synthetic("descriptor:mol_wt", calc_input="geometry"))
    assert any("never a finite typed number on the drawing input" in p for p in problems)


def test_an_output_on_too_few_rows_is_reported():
    problems = _problems(_entry(), _synthetic("descriptor:mol_wt", rows=sweep_tool.MIN_ROWS - 1))
    assert any(f"at least {sweep_tool.MIN_ROWS}" in p for p in problems)
    assert _problems(_entry(), _synthetic("descriptor:mol_wt", rows=sweep_tool.MIN_ROWS)) == []


def test_an_output_carrying_other_units_is_reported():
    problems = _problems(_entry(), _synthetic("descriptor:mol_wt", units="Da"))
    assert any("'Da'" in p and "'g/mol'" in p for p in problems)


# --- the table against the registry, on the census panel -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def swept(qapp, tmp_path_factory):
    """The census panel through the always-on set and the calculators the table draws from, with no NMR database (as the census does)."""
    from openchem.chem import nmr_database

    missing = tmp_path_factory.mktemp("no-nmr-db") / "absent.sqlite"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(nmr_database, "default_database_path", lambda: missing)
        return sweep_tool.run_sweep(qapp, calculator_ids=_CALCULATORS_UNDER_TEST)


def test_every_approved_output_resolves_through_the_registry_with_its_declared_units(swept):
    sweep, census = swept
    found = {e.output_id: sweep_tool.entry_problems(e, sweep, census) for e in APPROVED}
    bad = {output_id: problems for output_id, problems in found.items() if problems}
    assert not bad, "\n".join(f"{output_id}: {p}" for output_id, problems in bad.items() for p in problems)


def test_no_approved_output_comes_from_an_experimental_or_hidden_calculator(swept):
    _, census = swept
    for entry in APPROVED:
        kind, _, rest = entry.output_id.partition(":")
        if kind != "calculator":
            continue
        support = census["support"][rest.partition(":")[0]]
        assert support["stage"] in ("stable", "limited"), entry.output_id
        assert support["visibility"] == "shown", entry.output_id


def test_a_renamed_fact_label_turns_the_guard_red_and_says_what_it_breaks(swept):
    sweep, census = swept
    renamed = _entry(output_id="calculator:oxygen_balance:Oxygen balance (carbon monoxide basis)", carried_as="%", unit="%")
    (problem,) = sweep_tool.entry_problems(renamed, sweep, census)
    assert "produced by no run" in problem and "breaks every score that uses calculator:oxygen_balance:" in problem


def test_a_hidden_calculators_output_is_refused_by_the_guard_on_real_data(swept):
    """Joback is limited and hidden by default. It is a real number on the panel, which is exactly why the rule has to be explicit."""
    sweep, census = swept
    boiling = _entry(output_id="calculator:joback_properties:Boiling point (normal)", unit="K", carried_as="K")
    problems = sweep_tool.entry_problems(boiling, sweep, census)
    assert any("hidden by default" in p for p in problems), problems
    assert sweep.candidates[boiling.output_id].observations, "the control must be a number the panel really produced"


def test_a_number_carried_as_rounded_text_is_not_a_candidate_on_real_data(swept):
    """`Polar surface area` is '63.60' to two places: it changes with the decimal-places setting, so a score must not rest on it."""
    sweep, census = swept
    text = _entry(output_id="calculator:polar_surface_area:Polar surface area", unit="Å^2", carried_as="Å² (as drawn)")
    (problem,) = sweep_tool.entry_problems(text, sweep, census)
    assert "never a finite typed number" in problem
    assert sweep.candidates[text.output_id].observations == [], "the id is real; it is the value that is text"


def test_a_wrong_declared_unit_is_caught_on_real_data(swept):
    sweep, census = swept
    wrong = _entry(carried_as="Da")
    problems = sweep_tool.entry_problems(wrong, sweep, census)
    assert any("'Da'" in p for p in problems), problems


def _paired_sweep(first_values, second_values, second_input="drawing"):
    sweep = sweep_tool.Sweep()
    for output_id, values, calc_input in (("descriptor:mol_wt", first_values, "drawing"), ("descriptor:qed", second_values, second_input)):
        candidate = sweep_tool.Candidate(output_id, "label", "descriptor", output_id.split(":")[1])
        candidate.observations = [(f"row{i}", calc_input, v, "") for i, v in enumerate(values)]
        sweep.candidates[output_id] = candidate
    return sweep


def _pair(first_tag="molecular_weight", second_tag="qed_drug_likeness"):
    return [_entry(endpoint=first_tag), _entry(output_id="descriptor:qed", endpoint=second_tag)]


def test_two_outputs_that_agree_on_every_shared_row_but_carry_different_tags_are_reported():
    same = [1.0, 2.0, 3.0, 4.0, 5.0]
    found = sweep_tool.identical_pairs(_pair(), _paired_sweep(same, same))
    assert [(a.output_id, b.output_id) for a, b in found] == [("descriptor:mol_wt", "descriptor:qed")]


@pytest.mark.parametrize(
    "first, second, tags",
    [
        ([1.0, 2.0, 3.0, 4.0, 5.0], [1.0, 2.0, 3.0, 4.0, 5.1], ("molecular_weight", "qed_drug_likeness")),  # one row differs
        ([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0], ("molecular_weight", "qed_drug_likeness")),  # too few shared rows
        ([1.0, 2.0, 3.0, 4.0, 5.0], [1.0, 2.0, 3.0, 4.0, 5.0], ("molecular_weight", "molecular_weight")),  # already one tag
    ],
)
def test_agreement_that_is_not_a_copy_is_not_reported(first, second, tags):
    assert sweep_tool.identical_pairs(_pair(*tags), _paired_sweep(first, second)) == []


def test_only_the_drawing_is_compared():
    same = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert sweep_tool.identical_pairs(_pair(), _paired_sweep(same, same, second_input="geometry")) == []


def test_a_difference_in_the_last_digit_still_separates_two_outputs():
    first = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert sweep_tool.identical_pairs(_pair(), _paired_sweep(first, [1.0, 2.0, 3.0, 4.0, 5.0 + 1e-6])) == []


def test_no_two_approved_outputs_are_one_number_under_two_tags(swept):
    sweep, _ = swept
    assert [(a.output_id, b.output_id) for a, b in sweep_tool.identical_pairs(APPROVED, sweep)] == []


def test_the_copy_guard_finds_a_real_copy_on_real_data(swept):
    """The control arm: the solubility calculator's log mol/L IS the ESOL descriptor (16 of 16 rows), which is why that entry was dropped."""
    sweep, _ = swept
    esol = approved_output("descriptor:esol_logs")
    copy = _entry(output_id="calculator:solubility:Predicted intrinsic solubility (log mol/L)", endpoint="logp_octanol_water")
    found = sweep_tool.identical_pairs([esol, copy], sweep)
    assert [(a.output_id, b.output_id) for a, b in found] == [(esol.output_id, copy.output_id)]


def test_logd_is_not_approved_because_the_panel_can_only_show_its_degenerate_case(swept):
    """The plain id exists, on the panel, only for molecules with no ionizable centre (where it equals LogP), and the approximation only for the
    ionizable ones: the two never share a row. With pkasolver unconfigured the panel cannot exercise the plain id's main path, so it cannot be
    approved. If this turns red the census can run the tool: revisit the withdrawal."""
    sweep, _ = swept
    plain = sweep.candidates["calculator:logd:LogD at pH 7.4"]
    weaker = sweep.candidates["calculator:logd:LogD at pH 7.4 (approximation)"]

    def drawing_rows(candidate):
        return {row for row, calc_input, _value, _units in candidate.observations if calc_input == READ_FROM}

    assert len(drawing_rows(plain)) == 16 and len(drawing_rows(weaker)) == 9
    assert not drawing_rows(plain) & drawing_rows(weaker)
    assert approved_output(plain.output_id) is None and approved_output(weaker.output_id) is None


def test_the_sweeps_limits_are_these_numbers():
    """Pinned as numbers: a test that reads them by name moves with them, which is how a limit moved by one went unnoticed in slice 1."""
    assert sweep_tool.MIN_ROWS == 5
    assert sweep_tool.APPROVABLE_STAGES == {"stable", "limited"}


def test_the_panel_resolves_each_entry_on_enough_rows_to_mean_something(swept):
    sweep, _ = swept
    for entry in APPROVED:
        rows = {row for row, calc_input, _v, _u in sweep.candidates[entry.output_id].observations if calc_input == READ_FROM}
        assert len(rows) >= sweep_tool.MIN_ROWS, (entry.output_id, len(rows))


def test_every_approved_descriptor_is_stored_under_the_drawing_alone(swept):
    """`READ_FROM` is one input, and for the always-on descriptors it is now also the ONLY input.

    This test used to assert the opposite: that `descriptor:mol_wt` was observed under both the drawing and a
    geometry, "the same id stored twice, and a score must read exactly one of the two". That double storage was
    a defect and not a design: a conformer carries explicit hydrogens, the drawing's are implicit, and re-running
    the descriptors on it moved Synthetic Accessibility from 1.58 to 6.445 in the reader. A conformer request
    computes only the provider's geometric descriptors now (`DescriptorProvider.geometric_descriptor_ids`), so an
    approved output exists under the drawing alone and the choice of input cannot change a score.
    """
    sweep, _ = swept
    stored_elsewhere = {
        entry.output_id: sorted({i for _r, i, _v, _u in sweep.candidates[entry.output_id].observations} - {READ_FROM})
        for entry in APPROVED
        if entry.output_id.startswith("descriptor:")
    }
    assert {k: v for k, v in stored_elsewhere.items() if v} == {}
    assert {i for _r, i, _v, _u in sweep.candidates["descriptor:mol_wt"].observations} == {"drawing"}


def test_a_geometric_descriptor_is_stored_under_the_geometry_alone(swept):
    """The other half: the ten shape descriptors exist only where a conformer does, so they are not approved outputs."""
    sweep, _ = swept
    assert {i for _r, i, _v, _u in sweep.candidates["descriptor:pmi1"].observations} == {"geometry"}
    assert not any(entry.output_id == "descriptor:pmi1" for entry in APPROVED)
