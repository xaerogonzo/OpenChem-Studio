"""The predicate language regulatory rules are written in.

The tests that matter most are the ones asserting FAILURES are reported
rather than swallowed. A screen that can only say "no match" is much less
useful than one that can say which condition failed, and the whole
evaluator is shaped around keeping that information.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.regulatory.predicates import (
    SUPPORTED_OPS,
    PredicateError,
    evaluate,
)

# CWC Schedule 1.A.1, "O-Alkyl (<=C10, incl. cycloalkyl) alkyl-
# phosphonofluoridates". The connectivity is a SMARTS question; the carbon
# limit is not, which is why this rule needs both halves.
SCHEDULE_1_A_1 = {
    "op": "all",
    "of": [
        {
            "op": "contains",
            "smarts": "[CX4]P(=O)(F)O[CX4]",
            "label": "O-alkyl alkylphosphonofluoridate core",
        },
        {"op": "element_count", "element": "C", "max": 10,
         "label": "alkyl groups total <= C10"},
    ],
}

SARIN = "CC(C)OP(C)(=O)F"
#: Diisopropyl fluorophosphate. A phosphoFLUORIDATE, not a
#: phosphoNOfluoridate -- no P-C bond, so NOT Schedule 1. The near-miss
#: that makes a positives-only test suite worthless.
DFP = "CC(C)OP(=O)(F)OC(C)C"


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return mol


# --- The rule that motivated the language -------------------------------


def test_a_scheduled_structure_matches():
    passed, outcomes = evaluate(SCHEDULE_1_A_1, _mol(SARIN))
    assert passed
    assert all(outcome.passed for outcome in outcomes)


def test_a_near_miss_fails_on_the_condition_that_distinguishes_it():
    """DFP lacks the P-C bond. The rule must reject it, AND must say which
    condition rejected it -- "no match" alone leaves a user unable to see
    where the boundary runs."""
    passed, outcomes = evaluate(SCHEDULE_1_A_1, _mol(DFP))
    assert not passed

    failed = [o for o in outcomes if not o.passed]
    assert len(failed) == 1
    assert "core" in failed[0].label
    # The size limit is satisfied; only the connectivity is not.
    assert any(o.passed and "C10" in o.label for o in outcomes)


def test_a_size_limit_rejects_what_smarts_alone_would_accept():
    """THE REASON THIS IS A LANGUAGE AND NOT A SMARTS STRING. A C12
    homologue has the exact scheduled connectivity and is outside the
    schedule's "<=C10" clause. No SMARTS expresses that."""
    passed, outcomes = evaluate(SCHEDULE_1_A_1, _mol("CCCCCCCCCCCCOP(C)(=O)F"))
    assert not passed

    failed = [o for o in outcomes if not o.passed]
    assert len(failed) == 1
    assert "C10" in failed[0].label
    assert "13" in failed[0].detail


# --- Nothing short-circuits ---------------------------------------------


def test_all_evaluates_every_child_even_after_one_fails():
    """Short-circuiting would be a small speed win and would destroy the
    near-miss report, which needs to know that four conditions passed and
    one did not."""
    expression = {
        "op": "all",
        "of": [
            {"op": "contains", "smarts": "[Br]", "label": "bromine"},
            {"op": "contains", "smarts": "[F]", "label": "fluorine"},
            {"op": "contains", "smarts": "[Cl]", "label": "chlorine"},
        ],
    }
    passed, outcomes = evaluate(expression, _mol("FCCl"))
    assert not passed
    assert len(outcomes) == 3           # all three ran
    assert [o.passed for o in outcomes] == [False, True, True]


def test_any_reports_as_ONE_condition_not_one_per_branch():
    """MEASURED ON THE REAL CWC RULE, and it was wrong twice over before.

    An `any` is a single condition -- "the P-alkyl is methyl, ethyl,
    n-propyl or isopropyl" -- so reporting its branches individually made
    SARIN MATCH WHILE REPORTING THREE FAILURES (it is P-methyl, so the
    other three branches did not fire), and pushed diisopropyl
    fluorophosphate's near-miss distance from 1 to 4, past the threshold,
    so the one case the explainer exists for stopped being reported.

    Every branch is still evaluated; the group just counts once."""
    expression = {
        "op": "any",
        "label": "halogen present",
        "of": [
            {"op": "contains", "smarts": "[Br]", "label": "bromine"},
            {"op": "contains", "smarts": "[F]", "label": "fluorine"},
        ],
    }
    passed, outcomes = evaluate(expression, _mol("FCCl"))
    assert passed
    assert len(outcomes) == 1
    assert outcomes[0].label == "halogen present"


def test_a_passing_any_names_only_the_branch_that_actually_matched():
    """A BUG THIS CAUGHT. The detail listed every branch TRIED as though
    each had matched, so a molecule with no bromine was reported as
    "matched bromine, fluorine"."""
    expression = {
        "op": "any",
        "of": [
            {"op": "contains", "smarts": "[Br]", "label": "bromine"},
            {"op": "contains", "smarts": "[F]", "label": "fluorine"},
        ],
    }
    _, outcomes = evaluate(expression, _mol("FCCl"))
    assert "fluorine" in outcomes[0].detail
    assert "bromine" not in outcomes[0].detail


def test_a_failing_any_lists_what_was_tried():
    expression = {
        "op": "any",
        "of": [
            {"op": "contains", "smarts": "[Br]", "label": "bromine"},
            {"op": "contains", "smarts": "[I]", "label": "iodine"},
        ],
    }
    passed, outcomes = evaluate(expression, _mol("FCCl"))
    assert not passed
    assert "none of" in outcomes[0].detail
    assert "bromine" in outcomes[0].detail and "iodine" in outcomes[0].detail


def test_not_keeps_the_reason_it_inverted():
    """"failed BECAUSE the excluded group was present" is the useful
    reading; a bare inverted boolean is not."""
    expression = {
        "op": "not",
        "label": "must not contain a nitro group",
        "of": [{"op": "contains", "smarts": "[N+](=O)[O-]", "label": "nitro"}],
    }
    passed, outcomes = evaluate(expression, _mol("CC[N+](=O)[O-]"))
    assert not passed
    assert any("nitro" in o.label for o in outcomes)


# --- Leaves -------------------------------------------------------------


def test_a_bare_smarts_string_is_accepted():
    """A simple rule should not have to carry ceremony it does not use."""
    passed, _ = evaluate("[F]", _mol("CCF"))
    assert passed


def test_absent_is_not_the_same_as_a_failed_contains():
    passed, _ = evaluate({"op": "absent", "smarts": "[Br]"}, _mol("CCF"))
    assert passed


def test_matched_atoms_are_reported_for_highlighting():
    _, outcomes = evaluate({"op": "contains", "smarts": "[F]"}, _mol("CCF"))
    assert outcomes[0].atoms == frozenset({2})


def test_numeric_predicates_share_range_handling():
    assert evaluate({"op": "mw", "max": 100}, _mol("CCO"))[0]
    assert not evaluate({"op": "mw", "min": 500}, _mol("CCO"))[0]
    assert evaluate({"op": "ring_count", "equals": 1}, _mol("c1ccccc1"))[0]
    assert evaluate({"op": "charge", "equals": 0}, _mol("CCO"))[0]
    assert evaluate({"op": "hetero_count", "min": 1}, _mol("CCO"))[0]


def test_fragment_count_distinguishes_a_salt_from_its_parent():
    """Regulations reach "and its salts", so a rule may need to say which
    form it is looking at."""
    assert evaluate({"op": "fragment_count", "equals": 1}, _mol("CCN"))[0]
    assert evaluate({"op": "fragment_count", "equals": 2}, _mol("CCN.Cl"))[0]


def test_unassigned_stereocentres_are_not_a_stereochemical_claim():
    """An undrawn wedge is not a statement about configuration, so
    `has_stereo` must not count it."""
    assert evaluate({"op": "has_stereo", "value": True}, _mol("C[C@H](N)C(=O)O"))[0]
    assert evaluate({"op": "has_stereo", "value": False}, _mol("CC(N)C(=O)O"))[0]


# --- Failures are visible at build time ---------------------------------


def test_an_unknown_op_raises_rather_than_matching_nothing():
    """A regulation that silently matches nothing is the worst outcome this
    system has, so a typo must be loud."""
    with pytest.raises(PredicateError, match="Unknown predicate"):
        evaluate({"op": "definitely_not_an_op"}, _mol("CCO"))


def test_invalid_smarts_raises():
    with pytest.raises(PredicateError, match="Invalid SMARTS"):
        evaluate({"op": "contains", "smarts": "this is not smarts ((("}, _mol("CCO"))


def test_a_numeric_predicate_without_bounds_raises():
    with pytest.raises(PredicateError, match="min"):
        evaluate({"op": "mw"}, _mol("CCO"))


def test_a_combinator_without_children_raises():
    with pytest.raises(PredicateError, match="non-empty"):
        evaluate({"op": "all", "of": []}, _mol("CCO"))


def test_supported_ops_is_exposed_for_build_time_validation():
    """So a ruleset can be checked before it ships, rather than at
    screening time when the symptom is silence."""
    assert {"all", "any", "not", "contains", "element_count"} <= SUPPORTED_OPS
