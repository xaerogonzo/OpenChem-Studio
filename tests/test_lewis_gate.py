"""The arithmetic of the Lewis pairing gate (`benchmarks/lewis_gate/PREREGISTRATION.md`).

Pure, and fed INVENTED measurements built from the documented numbers: nothing here runs ORCA or the pair. What is pinned
is every condition the preregistration states, so that a pass condition cannot drift after a measurement exists.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from openchem.app import lewis_gate as gate
from openchem.app.lewis_gate import (
    DOCUMENTED,
    DOCUMENTED_CO_HARDNESS_EV,
    DOCUMENTED_CO_HOMO_EV,
    LINE_LABELS,
    MeasuredPair,
    Outcome,
    judge,
    noise_floor_ev,
    repeat_differences,
    tolerance_from_floor,
)

CLEAN_LABELS = ("Role", "Acid", "Base") + LINE_LABELS
#: What the report PRINTS its lines under. The Drago-Wayland line is filed under the report's own name as a FACT, so the
#: two sets differ on purpose: the gate checks the lines by the name a person reads.
CLEAN_LINES = ("Role", "Acid", "Base", "Assumption", "Limitation") + LINE_LABELS


def _pair(name: str, **changes) -> MeasuredPair:
    """The pair exactly as documented, as the recipe would report it, then changed."""
    documented = DOCUMENTED[name]
    base = MeasuredPair(
        acid=name,
        acid_lumo_ev=documented.acid_lumo_ev,
        acid_hardness_ev=documented.acid_hardness_ev,
        base_homo_ev=DOCUMENTED_CO_HOMO_EV,
        base_hardness_ev=DOCUMENTED_CO_HARDNESS_EV,
        printed_gap_ev=documented.gap_ev,
        printed_hardness_difference_ev=documented.hardness_difference_ev,
        all_bound=True,
        role_set_by_user=True,
        fact_labels=CLEAN_LABELS,
        line_names=CLEAN_LINES,
    )
    return replace(base, **changes)


def _both(**per_pair) -> dict[str, MeasuredPair]:
    return {name: _pair(name, **per_pair.get(name, {})) for name in DOCUMENTED}


def _judge(pairs=None, tolerance=0.01, versions=("6.1.1",), unfinished=()):
    return judge(_both() if pairs is None else pairs, tolerance, orca_versions=versions, unfinished_runs=unfinished)


def _shifted(name: str, *, acid_lumo=0.0, acid_hardness=0.0, base_homo=0.0, base_hardness=0.0) -> MeasuredPair:
    """A pair whose six inputs moved and whose printed lines follow them, as the report's would."""
    documented = DOCUMENTED[name]
    pair = _pair(
        name,
        acid_lumo_ev=documented.acid_lumo_ev + acid_lumo,
        acid_hardness_ev=documented.acid_hardness_ev + acid_hardness,
        base_homo_ev=DOCUMENTED_CO_HOMO_EV + base_homo,
        base_hardness_ev=DOCUMENTED_CO_HARDNESS_EV + base_hardness,
    )
    return replace(pair, printed_gap_ev=round(pair.gap_ev, 2), printed_hardness_difference_ev=round(pair.hardness_difference_ev, 2))


# --- the documented numbers ------------------------------------------------------------------------------------------


def test_the_documented_numbers_agree_with_their_inputs():
    """The only circularity allowed: the four documented outputs follow from the six documented inputs."""
    for name, documented in DOCUMENTED.items():
        assert documented.gap_ev == pytest.approx(documented.acid_lumo_ev - DOCUMENTED_CO_HOMO_EV, abs=1e-9), name
        assert documented.hardness_difference_ev == pytest.approx(
            abs(documented.acid_hardness_ev - DOCUMENTED_CO_HARDNESS_EV), abs=1e-9
        ), name


def test_the_documented_numbers_are_the_ones_the_adduct_tests_carry():
    """Typed in on purpose and compared with the test module that documents them, so neither can move alone."""
    from tests import test_lewis_adduct as adduct

    assert adduct.CO_HOMO_EV == DOCUMENTED_CO_HOMO_EV and adduct.CO_HARDNESS == DOCUMENTED_CO_HARDNESS_EV
    assert (adduct.BORANE_LUMO_EV, adduct.BORANE_HARDNESS) == (DOCUMENTED["BH3"].acid_lumo_ev, DOCUMENTED["BH3"].acid_hardness_ev)
    assert (adduct.BF3_LUMO_EV, adduct.BF3_HARDNESS) == (DOCUMENTED["BF3"].acid_lumo_ev, DOCUMENTED["BF3"].acid_hardness_ev)


def test_the_documented_pairs_disagree_which_is_the_finding():
    bh3, bf3 = DOCUMENTED["BH3"], DOCUMENTED["BF3"]
    assert bh3.gap_ev < bf3.gap_ev, "the frontier gap says BH3 binds CO better"
    assert bf3.hardness_difference_ev < bh3.hardness_difference_ev, "the hardness match says BF3 does"


def test_the_window_is_derived_from_the_smallest_margin_the_orderings_rest_on():
    margin = DOCUMENTED["BH3"].hardness_difference_ev - DOCUMENTED["BF3"].hardness_difference_ev
    assert margin == pytest.approx(0.74)
    assert gate.TOLERANCE_CEILING_EV == pytest.approx(margin / 2) and gate.TOLERANCE_FLOOR_EV == 0.01


# --- the noise floor and the tolerance rule ----------------------------------------------------------------------------


def test_a_repeat_difference_is_absolute_and_per_quantity():
    assert repeat_differences({"homo": -10.17, "lumo": 1.0}, {"homo": -10.1702, "lumo": 0.9995}) == pytest.approx(
        {"homo": 0.0002, "lumo": 0.0005}
    )


def test_a_repeat_difference_does_not_depend_on_which_run_was_first():
    forward = repeat_differences({"homo": -10.1702, "lumo": 0.9995}, {"homo": -10.17, "lumo": 1.0})
    backward = repeat_differences({"homo": -10.17, "lumo": 1.0}, {"homo": -10.1702, "lumo": 0.9995})
    assert forward == pytest.approx(backward) and all(value > 0 for value in forward.values())


def test_a_repeat_that_measured_different_quantities_has_no_difference_to_report():
    with pytest.raises(ValueError, match="same quantities"):
        repeat_differences({"homo": 1.0}, {"homo": 1.0, "lumo": 2.0})


def test_the_floor_is_the_largest_difference_of_every_repeat():
    assert noise_floor_ev({"a": 0.001, "b": 0.004}, {"a": 0.009, "b": 0.0}) == 0.009


def test_a_floor_needs_a_repeat():
    with pytest.raises(ValueError, match="needs at least one repeat"):
        noise_floor_ev()
    with pytest.raises(ValueError, match="needs at least one repeat"):
        noise_floor_ev({})


@pytest.mark.parametrize(
    ("floor", "expected"),
    [
        (0.0, 0.01),
        (0.0004, 0.01),
        (0.01, 0.01),
        (0.0100000001, 0.01),  # a float's own rounding is not a reason to double the tolerance
        (0.0101, 0.02),
        (0.011, 0.02),
        (0.02, 0.02),
        (0.185, 0.19),
        (0.3699, 0.37),
        (0.37, 0.37),
    ],
)
def test_the_tolerance_is_the_floor_rounded_up_to_the_next_hundredth_and_never_below_the_minimum(floor, expected):
    tolerance = tolerance_from_floor(floor)
    assert tolerance.value_ev == pytest.approx(expected) and tolerance.floor_ev == floor


@pytest.mark.parametrize("floor", [0.3701, 0.38, 0.74, 5.0])
def test_a_floor_that_needs_more_than_the_ceiling_leaves_no_tolerance_and_says_why(floor):
    tolerance = tolerance_from_floor(floor)
    assert tolerance.value_ev is None
    assert "cannot tell the two hardness orderings apart" in tolerance.reason


@pytest.mark.parametrize("floor", [-0.001, math.nan])
def test_a_floor_is_a_non_negative_number(floor):
    with pytest.raises(ValueError, match="non-negative number"):
        tolerance_from_floor(floor)


def test_the_tolerance_never_exceeds_the_ceiling_by_rounding():
    for hundredths in range(1, 60):
        tolerance = tolerance_from_floor(hundredths / 100)
        assert tolerance.value_ev is None or tolerance.value_ev <= gate.TOLERANCE_CEILING_EV + 1e-9


# --- the verdict --------------------------------------------------------------------------------------------------------


def test_the_documented_numbers_themselves_pass():
    verdict = _judge()
    assert verdict.outcome is Outcome.PASS and verdict.reasons == ()
    assert [row.quantity for row in verdict.rows] == [
        "BF3/CO frontier gap", "BF3/CO |d eta|", "BH3/CO frontier gap", "BH3/CO |d eta|",
    ]
    assert all(row.within for row in verdict.rows)


def test_a_difference_exactly_at_the_tolerance_is_within_it_and_a_hair_over_is_not():
    on_the_line = _both()
    on_the_line["BH3"] = _shifted("BH3", acid_lumo=0.01)
    assert _judge(on_the_line, tolerance=0.01).outcome is Outcome.PASS
    over = _both()
    over["BH3"] = _shifted("BH3", acid_lumo=0.0111)
    verdict = _judge(over, tolerance=0.01)
    assert verdict.outcome is Outcome.FAIL
    assert any("BH3/CO frontier gap" in reason and "beyond 0.01 eV" in reason for reason in verdict.reasons)


@pytest.mark.parametrize(
    ("pair", "shift", "quantity"),
    [
        ("BH3", dict(acid_lumo=0.3), "BH3/CO frontier gap"),
        ("BH3", dict(base_homo=-0.3), "BH3/CO frontier gap"),
        ("BH3", dict(acid_hardness=0.3), "BH3/CO |d eta|"),
        ("BH3", dict(base_hardness=-0.3), "BH3/CO |d eta|"),
        ("BF3", dict(acid_lumo=-0.3), "BF3/CO frontier gap"),
        ("BF3", dict(base_homo=0.3), "BF3/CO frontier gap"),
        ("BF3", dict(acid_hardness=-0.3), "BF3/CO |d eta|"),
        ("BF3", dict(base_hardness=0.3), "BF3/CO |d eta|"),
    ],
)
def test_each_of_the_four_numbers_is_held_to_the_tolerance_separately(pair, shift, quantity):
    pairs = _both()
    pairs[pair] = _shifted(pair, **shift)
    verdict = _judge(pairs, tolerance=0.2)
    assert verdict.outcome is Outcome.FAIL
    assert any(quantity in reason for reason in verdict.reasons)
    others = [row for row in verdict.rows if row.quantity != quantity and quantity.split("/")[0] not in row.quantity]
    assert all(row.within for row in others), "only the shifted pair's number misses"


def test_a_larger_tolerance_that_is_still_inside_the_window_accepts_what_a_smaller_one_does_not():
    pairs = _both()
    pairs["BH3"] = _shifted("BH3", acid_lumo=0.15)
    assert _judge(pairs, tolerance=0.1).outcome is Outcome.FAIL
    assert _judge(pairs, tolerance=0.2).outcome is Outcome.PASS


def test_the_frontier_gap_must_still_order_the_pairs_as_documented():
    pairs = _both()
    pairs["BH3"] = _shifted("BH3", acid_lumo=3.0)  # BH3/CO's gap now above BF3/CO's
    verdict = _judge(pairs, tolerance=0.37)
    assert verdict.outcome is Outcome.FAIL
    assert any("does not order the pairs as documented" in reason for reason in verdict.reasons)


def test_the_disagreement_must_reproduce_a_recipe_that_fixes_it_has_altered_the_chemistry():
    """The hardness difference of BF3/CO moved above BH3/CO's, so the two lines now AGREE. Within a very large
    tolerance every number would pass, so the ordering is what refuses it."""
    pairs = _both()
    pairs["BF3"] = _shifted("BF3", acid_hardness=1.0)
    verdict = _judge(pairs, tolerance=2.0)
    assert verdict.outcome is Outcome.NOT_EVALUABLE, "a tolerance of 2 eV is outside the window, so nothing is decided"
    verdict = _judge(pairs, tolerance=0.37)
    assert verdict.outcome is Outcome.FAIL
    assert any("the disagreement did not reproduce" in reason for reason in verdict.reasons)


def test_every_failure_is_reported_and_none_hides_another():
    pairs = _both()
    pairs["BH3"] = _shifted("BH3", acid_lumo=3.0, acid_hardness=1.5)
    pairs["BF3"] = replace(pairs["BF3"], role_set_by_user=False, fact_labels=("Role", "Combined score"), line_names=("Role",))
    verdict = _judge(pairs, tolerance=0.2)
    assert verdict.outcome is Outcome.FAIL
    text = " | ".join(verdict.reasons)
    for expected in (
        "BH3/CO frontier gap", "BH3/CO |d eta|", "does not order the pairs", "disagreement did not reproduce",
        "combines lines", "lacks the line(s)", "role was not recorded as set by the user",
    ):
        assert expected in text, expected


@pytest.mark.parametrize("word", gate.COMBINED_WORDS)
def test_a_field_that_combines_the_lines_fails_whatever_it_is_called(word):
    pairs = _both()
    pairs["BH3"] = replace(pairs["BH3"], fact_labels=CLEAN_LABELS + (f"Pairing {word.upper()}",))
    verdict = _judge(pairs)
    assert verdict.outcome is Outcome.FAIL and any("combines lines" in reason for reason in verdict.reasons)


@pytest.mark.parametrize("word", gate.COMBINED_WORDS)
def test_a_printed_line_that_combines_the_lines_fails_even_when_it_is_not_a_fact_label(word):
    pairs = _both()
    pairs["BH3"] = replace(pairs["BH3"], line_names=CLEAN_LINES + (f"Overall {word}",))
    verdict = _judge(pairs)
    assert verdict.outcome is Outcome.FAIL and any("combines lines" in reason for reason in verdict.reasons)


def test_a_report_missing_one_of_the_three_lines_fails():
    pairs = _both()
    pairs["BF3"] = replace(pairs["BF3"], line_names=("Role", "Frontier orbital gap", "HSAB hardness match"))
    verdict = _judge(pairs)
    assert verdict.outcome is Outcome.FAIL and any("Drago-Wayland enthalpy" in reason for reason in verdict.reasons)


def test_the_lines_are_found_by_the_name_they_are_printed_under_and_not_by_fact_label():
    """The Drago-Wayland line is a fact filed under the report's own name. A check on labels would have failed a correct
    report; this is the regression for it, found before any measurement existed."""
    pairs = _both()
    pairs["BF3"] = replace(pairs["BF3"], fact_labels=("Lewis pairing",) * 3)
    assert _judge(pairs).outcome is Outcome.PASS


def test_the_role_must_have_been_the_one_the_person_set():
    pairs = _both()
    pairs["BH3"] = replace(pairs["BH3"], role_set_by_user=False)
    assert _judge(pairs).outcome is Outcome.FAIL


# --- what the gate cannot decide ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("tolerance", [None, 0.005, 0.38, 1.0])
def test_a_tolerance_that_is_unset_or_outside_its_window_decides_nothing(tolerance):
    verdict = _judge(tolerance=tolerance)
    assert verdict.outcome is Outcome.NOT_EVALUABLE
    assert any("tolerance" in reason for reason in verdict.reasons)


def test_the_window_edges_are_inside_the_window():
    assert _judge(tolerance=0.01).outcome is Outcome.PASS and _judge(tolerance=0.37).outcome is Outcome.PASS


@pytest.mark.parametrize("versions", [("6.1.0",), ("6.1.1", "6.2.0"), ("5.0.4",)])
def test_another_orca_version_is_recorded_and_is_never_a_pass(versions):
    verdict = _judge(versions=versions)
    assert verdict.outcome is Outcome.NOT_EVALUABLE
    assert any("is not the documented 6.1.1" in reason for reason in verdict.reasons)


def test_no_recorded_version_is_not_the_documented_one_either():
    verdict = _judge(versions=())
    assert verdict.outcome is Outcome.NOT_EVALUABLE and any("no recorded version" in r for r in verdict.reasons)


def test_a_run_that_did_not_complete_decides_nothing():
    verdict = _judge(unfinished=("run-abc",))
    assert verdict.outcome is Outcome.NOT_EVALUABLE and any("run-abc" in reason for reason in verdict.reasons)


def test_a_number_that_was_not_bound_to_a_current_run_decides_nothing():
    pairs = _both()
    pairs["BF3"] = replace(pairs["BF3"], all_bound=False)
    verdict = _judge(pairs)
    assert verdict.outcome is Outcome.NOT_EVALUABLE and any("BF3 with CO: not every number was bound" in r for r in verdict.reasons)


def test_a_report_that_disagrees_with_its_own_evidence_decides_nothing():
    """The report and the gate are two readings of one set of numbers. When they differ the defect is in the code, and
    the gate says so rather than reporting a chemistry result."""
    pairs = _both()
    pairs["BH3"] = replace(pairs["BH3"], printed_gap_ev=8.5)
    verdict = _judge(pairs)
    assert verdict.outcome is Outcome.NOT_EVALUABLE
    assert any("prints Frontier orbital gap 8.50 eV but its own evidence gives 8.1300 eV" in r for r in verdict.reasons)


def test_a_printed_line_may_differ_from_the_full_precision_number_by_its_own_rounding():
    pairs = _both()
    pairs["BH3"] = _shifted("BH3", acid_lumo=0.004)  # 8.134, printed 8.13
    assert _judge(pairs).outcome is Outcome.PASS


def test_a_report_that_printed_no_line_decides_nothing():
    pairs = _both()
    pairs["BH3"] = replace(pairs["BH3"], printed_hardness_difference_ev=None)
    verdict = _judge(pairs)
    assert verdict.outcome is Outcome.NOT_EVALUABLE and any("printed no HSAB hardness match line" in r for r in verdict.reasons)


def test_the_gate_needs_exactly_the_two_documented_pairs():
    only_one = {"BH3": _pair("BH3")}
    assert _judge(only_one).outcome is Outcome.NOT_EVALUABLE
    extra = {**_both(), "AlCl3": _pair("BH3", acid="AlCl3")}
    assert _judge(extra).outcome is Outcome.NOT_EVALUABLE


def test_not_evaluable_takes_precedence_over_a_failure_and_every_reason_is_given():
    pairs = _both()
    pairs["BH3"] = _shifted("BH3", acid_lumo=3.0)
    verdict = _judge(pairs, tolerance=None, versions=("6.2.0",), unfinished=("r1",))
    assert verdict.outcome is Outcome.NOT_EVALUABLE
    assert len(verdict.reasons) == 3
    assert all("does not order" not in reason for reason in verdict.reasons), "a gate that cannot decide claims no failure"


def test_the_rows_are_still_built_when_the_gate_cannot_decide_so_the_numbers_are_recorded():
    verdict = _judge(versions=("6.2.0",))
    assert len(verdict.rows) == 4 and all(row.within for row in verdict.rows)
    assert _judge(tolerance=None).rows[0].within is None, "with no tolerance there is no within"


def test_the_rows_carry_signed_differences_from_the_documented_values():
    pairs = _both()
    pairs["BF3"] = _shifted("BF3", acid_lumo=-0.05)
    row = next(r for r in _judge(pairs, tolerance=0.1).rows if r.quantity == "BF3/CO frontier gap")
    assert row.documented_ev == 10.90 and row.measured_ev == pytest.approx(10.85) and row.difference_ev == pytest.approx(-0.05)


# --- the boundaries and ties, on numbers a float holds exactly -------------------------------------------------------------
#
# The documented numbers are not exact in binary, so a boundary test on them would pass or fail by float noise. Here the
# documented table is replaced by one whose numbers are exact (eighths), and a measurement is placed exactly on, a hair
# inside and a hair outside the tolerance.


@pytest.fixture
def exact_documented(monkeypatch):
    from openchem.app.lewis_gate import DocumentedPair

    monkeypatch.setitem(DOCUMENTED, "BH3", DocumentedPair("BH3", -2.0, 6.0, 8.0, 2.0))
    monkeypatch.setitem(DOCUMENTED, "BF3", DocumentedPair("BF3", 0.0, 9.0, 10.0, 1.0))
    monkeypatch.setattr(gate, "DOCUMENTED_CO_HOMO_EV", -10.0)
    monkeypatch.setattr(gate, "DOCUMENTED_CO_HARDNESS_EV", 8.0)


def _exact(name: str, *, gap_shift=0.0, hardness_shift=0.0, **changes) -> MeasuredPair:
    documented = DOCUMENTED[name]
    pair = MeasuredPair(
        acid=name, acid_lumo_ev=documented.acid_lumo_ev + gap_shift, acid_hardness_ev=documented.acid_hardness_ev + hardness_shift,
        base_homo_ev=-10.0, base_hardness_ev=8.0, printed_gap_ev=None, printed_hardness_difference_ev=None,
        all_bound=True, role_set_by_user=True, fact_labels=CLEAN_LABELS, line_names=CLEAN_LINES,
    )
    pair = replace(pair, printed_gap_ev=round(pair.gap_ev, 2), printed_hardness_difference_ev=round(pair.hardness_difference_ev, 2))
    return replace(pair, **changes)


def test_a_difference_exactly_the_tolerance_is_within_it(exact_documented):
    pairs = {"BH3": _exact("BH3", gap_shift=0.25), "BF3": _exact("BF3")}
    verdict = _judge(pairs, tolerance=0.25)
    assert verdict.outcome is Outcome.PASS
    assert next(r for r in verdict.rows if r.quantity == "BH3/CO frontier gap").difference_ev == 0.25


def test_a_difference_a_float_hair_over_the_tolerance_is_within_it_and_a_real_miss_is_not(exact_documented):
    hair = {"BH3": _exact("BH3", gap_shift=0.25 + 5e-10), "BF3": _exact("BF3")}
    assert _judge(hair, tolerance=0.25).outcome is Outcome.PASS, "the slack is for float noise"
    over = {"BH3": _exact("BH3", gap_shift=0.25 + 2e-9), "BF3": _exact("BF3")}
    assert _judge(over, tolerance=0.25).outcome is Outcome.FAIL


def test_a_miss_in_either_direction_is_a_miss(exact_documented):
    for shift in (0.26, -0.26):
        pairs = {"BH3": _exact("BH3", gap_shift=shift), "BF3": _exact("BF3")}
        assert _judge(pairs, tolerance=0.25).outcome is Outcome.FAIL, shift


def test_a_tie_in_the_frontier_gaps_is_not_the_documented_ordering(exact_documented, monkeypatch):
    from openchem.app.lewis_gate import DocumentedPair

    monkeypatch.setitem(DOCUMENTED, "BF3", DocumentedPair("BF3", -2.0, 9.0, 8.0, 1.0))  # documented as a tie, to isolate the ordering
    verdict = _judge({"BH3": _exact("BH3"), "BF3": _exact("BF3")}, tolerance=0.25)
    assert verdict.outcome is Outcome.FAIL
    assert [r for r in verdict.reasons if "does not order the pairs as documented" in r] and not [r for r in verdict.reasons if "|d eta|" in r and "beyond" in r]


def test_a_tie_in_the_hardness_differences_is_not_the_disagreement(exact_documented, monkeypatch):
    from openchem.app.lewis_gate import DocumentedPair

    monkeypatch.setitem(DOCUMENTED, "BF3", DocumentedPair("BF3", 0.0, 10.0, 10.0, 2.0))  # BF3's |d eta| = BH3's
    verdict = _judge({"BH3": _exact("BH3"), "BF3": _exact("BF3")}, tolerance=0.25)
    assert verdict.outcome is Outcome.FAIL
    assert any("the disagreement did not reproduce" in reason for reason in verdict.reasons)


def test_a_printed_line_off_by_a_few_hundredths_is_a_report_that_disagrees_with_its_evidence():
    for off in (0.02, 0.05, 0.09):
        pairs = _both()
        pairs["BH3"] = replace(pairs["BH3"], printed_gap_ev=8.13 + off)
        assert _judge(pairs).outcome is Outcome.NOT_EVALUABLE, off


# --- reading a real evaluated pairing --------------------------------------------------------------------------------------
#
# The documented numbers are fed to the REAL evaluator as stored-run objects (the wiring check the recipe's own tests do; it
# proves nothing about ORCA) and the gate's reader is run on what comes out, so the reader is shown to read a real report
# before it ever reads a measured one.


def _evaluated(acid_smiles: str, uuid: str, label: str, numbers: dict, *, role: str = "acid", **kw):
    from openchem.chem.lewis_pairing_eval import evaluate_lewis_pairing
    from tests.lewis_helpers import METHOD, carbon_monoxide, member, runs_of

    acid = member(acid_smiles, uuid, label, runs_of(uuid, numbers))
    return evaluate_lewis_pairing(acid, carbon_monoxide(**kw), method_basis=METHOD, role=role)


def _documented_runs():
    bh3 = _evaluated("B", "bh3", "BH3", dict(homo=-99.0, lumo=-2.04, hardness=6.77))
    bf3 = _evaluated("FB(F)F", "bf3", "BF3", dict(homo=-99.0, lumo=0.73, hardness=9.29))
    return bh3, bf3


def test_the_reader_reads_a_real_report_into_the_six_numbers_and_the_two_printed_lines():
    from openchem.app.lewis_gate import measure_pair

    bh3, _ = _documented_runs()
    pair = measure_pair("BH3", bh3)
    assert (pair.acid_lumo_ev, pair.acid_hardness_ev, pair.base_homo_ev, pair.base_hardness_ev) == (-2.04, 6.77, -10.17, 8.40)
    assert pair.gap_ev == pytest.approx(8.13) and pair.hardness_difference_ev == pytest.approx(1.63)
    assert (pair.printed_gap_ev, pair.printed_hardness_difference_ev) == (8.13, 1.63)
    assert pair.all_bound and pair.role_set_by_user


def test_the_reader_finds_all_three_lines_under_the_names_a_person_reads_even_though_one_is_not_a_fact_label():
    from openchem.app.lewis_gate import measure_pair

    pair = measure_pair("BH3", _documented_runs()[0])
    assert set(LINE_LABELS) <= set(pair.line_names)
    assert "Drago-Wayland enthalpy" not in pair.fact_labels, "the reason the lines are read by name"


def test_the_documented_numbers_through_the_real_evaluator_and_the_reader_pass_the_gate():
    """The gate CAN pass: nothing in the machinery makes a correct recipe fail, which is not the same as the recipe being
    correct on ORCA. Stand-ins for measurements, exactly the documented numbers."""
    from openchem.app.lewis_gate import measure_pair

    bh3, bf3 = _documented_runs()
    pairs = {"BH3": measure_pair("BH3", bh3), "BF3": measure_pair("BF3", bf3)}
    verdict = _judge(pairs, tolerance=0.01)
    assert verdict.outcome is Outcome.PASS, verdict.reasons


def test_the_report_has_no_combined_field_and_the_summary_sentence_is_not_mistaken_for_a_line():
    from openchem.app.lewis_gate import measure_pair

    run = _documented_runs()[0]
    pair = measure_pair("BH3", run)
    assert not [name for name in pair.line_names + pair.fact_labels if any(word in name.lower() for word in gate.COMBINED_WORDS)]
    summary = [line for line in run.result.matched if line.startswith("Frontier orbital gap ") and "HSAB" in line]
    assert summary, "the report has a sentence naming both lines side by side"
    assert all(not name.startswith("Frontier orbital gap ") for name in pair.line_names)


def test_a_role_left_to_the_recipe_is_not_recorded_as_set_by_the_person():
    from openchem.app.lewis_gate import measure_pair

    auto = _evaluated("B", "bh3", "BH3", dict(homo=-99.0, lumo=-2.04, hardness=6.77), role="auto")
    assert not measure_pair("BH3", auto).role_set_by_user


def test_a_pairing_with_a_number_that_is_not_bound_is_read_as_not_bound():
    from openchem.app.lewis_gate import measure_pair

    gap = _evaluated("B", "bh3", "BH3", dict(homo=-99.0, lumo=-2.04, hardness=6.77), hardness=False)
    with pytest.raises(ValueError, match="no bound value for second_hardness"):
        measure_pair("BH3", gap)


def test_a_pairing_with_no_answer_cannot_be_read():
    from dataclasses import replace as replace_

    from openchem.app.lewis_gate import measure_pair

    run = replace_(_documented_runs()[0], result=None)
    with pytest.raises(ValueError, match="has no answer to read"):
        measure_pair("BH3", run)


def test_a_pairing_with_an_unused_orbital_not_bound_is_not_all_bound_though_the_four_numbers_are():
    """The recipe binds six numbers and a verdict compares four. A gap in one of the other two is still a gap: the gate
    does not decide on a pairing whose evidence is incomplete."""
    from dataclasses import replace as replace_

    from openchem.app.lewis_gate import measure_pair
    from openchem.domain.recipe_run import BindingRecord, BindingState, RecipeRunStatus

    run = _documented_runs()[0]
    gapped = tuple(
        BindingRecord(b.step_id, b.target, BindingState.MISSING, "no run") if b.target == "first_homo" else b
        for b in run.bindings
    )
    partial = replace_(run, bindings=gapped, status=RecipeRunStatus.PARTIAL)
    pair = measure_pair("BH3", partial)
    assert not pair.all_bound and pair.acid_lumo_ev == -2.04, "the four numbers are bound, and the pairing still is not"
    assert _judge({"BH3": pair, "BF3": _pair("BF3")}).outcome is Outcome.NOT_EVALUABLE


def test_a_pairing_with_a_binding_missing_altogether_is_not_all_bound():
    from dataclasses import replace as replace_

    from openchem.app.lewis_gate import measure_pair
    from openchem.domain.recipe_run import RecipeRunStatus

    run = _documented_runs()[0]
    without = replace_(run, bindings=tuple(b for b in run.bindings if b.target != "first_homo"), status=RecipeRunStatus.PARTIAL)
    assert not measure_pair("BH3", without).all_bound


def test_a_printed_line_is_read_with_its_sign():
    from openchem.app.lewis_gate import _printed

    lines = ["Frontier orbital gap: -0.50 eV [heuristic] -- x", "HSAB hardness match: 1.63 eV [heuristic] -- y"]
    assert _printed(lines, "Frontier orbital gap") == -0.5 and _printed(lines, "HSAB hardness match") == 1.63


def test_a_line_that_is_not_there_is_no_number_and_a_sentence_naming_both_lines_is_not_a_line():
    from openchem.app.lewis_gate import _printed

    assert _printed(["Role: as you set it."], "Frontier orbital gap") is None
    assert _printed(["  Frontier orbital gap 8.05 eV; HSAB hardness match 0.85 eV."], "Frontier orbital gap") is None


# --- the committed record ------------------------------------------------------------------------------------------------
#
# `benchmarks/lewis_gate/artifacts/pair.json` is what the gate wrote on real ORCA. Re-deriving its verdict from its own
# numbers with the code as it is now means the record cannot be made to disagree with the arithmetic, or the arithmetic edited
# so that the recorded outcome no longer follows, without a test saying so.


def _record() -> dict:
    import json
    from pathlib import Path

    return json.loads((Path(__file__).resolve().parents[1] / "benchmarks" / "lewis_gate" / "artifacts" / "pair.json").read_text(encoding="utf-8"))


def _recorded_pairs(record: dict) -> dict[str, MeasuredPair]:
    fields = ("acid", "acid_lumo_ev", "acid_hardness_ev", "base_homo_ev", "base_hardness_ev", "printed_gap_ev",
              "printed_hardness_difference_ev", "all_bound", "role_set_by_user")
    return {
        name: MeasuredPair(**{f: pair[f] for f in fields}, fact_labels=tuple(pair["fact_labels"]), line_names=tuple(pair["line_names"]))
        for name, pair in record["pairs"].items()
    }


def test_the_recorded_verdict_follows_from_the_recorded_numbers_by_the_code_as_it_is():
    record = _record()
    verdict = judge(_recorded_pairs(record), record["tolerance_ev"], orca_versions=record["orca_versions"])
    assert verdict.outcome.value == record["outcome"] == "pass" and verdict.reasons == ()
    assert [(r.quantity, r.measured_ev, r.within) for r in verdict.rows] == [(r["quantity"], r["measured_ev"], r["within"]) for r in record["rows"]]


def test_the_recorded_tolerance_is_the_one_the_rule_gives_the_recorded_floor_and_the_run_was_on_the_documented_orca():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "benchmarks" / "lewis_gate"
    floor = json.loads((root / "artifacts" / "floor.json").read_text(encoding="utf-8"))
    assert tolerance_from_floor(floor["floor_ev"]).value_ev == _record()["tolerance_ev"] == 0.01
    assert set(_record()["orca_versions"]) == set(floor["orca_versions"]) == {gate.ORCA_VERSION}


def test_the_recorded_numbers_are_within_the_recorded_tolerance_of_the_documented_ones():
    record = _record()
    for row in record["rows"]:
        assert abs(row["measured_ev"] - row["documented_ev"]) <= record["tolerance_ev"], row["quantity"]
    pairs = _recorded_pairs(record)
    for name, documented in DOCUMENTED.items():
        assert pairs[name].gap_ev == pytest.approx(documented.gap_ev, abs=0.01)
        assert pairs[name].hardness_difference_ev == pytest.approx(documented.hardness_difference_ev, abs=0.01)
