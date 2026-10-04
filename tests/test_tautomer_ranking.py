"""RDKit's heuristic tautomer preference, and its cross-check against ORCA.

The score is a heuristic, not an energy and not a probability: these tests fix
what a tie, a rank and a verdict MEAN so the display can never read a heuristic
as more than it is.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.structure_generators import enumerate_tautomers
from openchem.chem.tautomer_distribution import (
    MODEL_POLICY_SINGLE,
    CandidateResult,
    CandidateStatus,
    build_outcome,
    build_structure_set_result,
    generate_tautomer_candidates,
)
from openchem.chem.tautomer_ranking import (
    AGREES,
    DIFFERS,
    INDETERMINATE,
    ORCA_COMPARISON_TOLERANCE_KCAL,
    RDKIT_VERSION,
    TIED,
    competition_ranks,
    cross_check,
    score_tautomer,
    tied_flags,
)

#: Keto form scores 5; both enols score 2: a REAL RDKit tie in a fixture that
#: needs no ORCA. The unit tests below are the contract; this is the live case.
TIED_ENOLS = "CC1CCCC(=O)C1C"


# --- ranks and ties ---------------------------------------------------------


def test_competition_ranks_keep_a_tie_looking_like_one():
    assert competition_ranks([10, 10, 5]) == [1, 1, 3]
    assert competition_ranks([5, 10, 10]) == [3, 1, 1]
    assert competition_ranks([7]) == [1]
    # An ordinal rank would call these 1, 2, 3 and invent a preference.
    assert competition_ranks([3, 3, 3]) == [1, 1, 1]


def test_tied_is_derived_from_the_raw_score_not_from_the_rank():
    assert tied_flags([10, 10, 5]) == [True, True, False]
    assert tied_flags([1, 2, 3]) == [False, False, False]


def test_the_raw_score_is_returned_as_rdkit_gives_it():
    score = score_tautomer(Chem.MolFromSmiles("CC(C)=O"))

    assert score == 5 and isinstance(score, int)


# --- the RDKit generator ----------------------------------------------------


def test_the_generator_orders_best_first_and_labels_the_rank_as_a_heuristic():
    result = enumerate_tautomers(Chem.MolFromSmiles("CC(=O)C"), "m")

    scores = [e.metadata["rdkit_score"] for e in result.entries]
    assert scores == sorted(scores, reverse=True)
    assert result.entries[0].metadata["rdkit_rank"] == 1
    # The word is IN the label: a user can open the grid without ever seeing a description.
    assert all("heuristic rank" in e.label for e in result.entries)
    assert not any("%" in e.label for e in result.entries)


def test_the_heuristic_never_uses_the_validated_score_field():
    """`StructureEntry.score` is printed by the shared grid as a number and is
    reserved for validated populations; the heuristic must not wear it."""
    result = enumerate_tautomers(Chem.MolFromSmiles("CC(=O)C"), "m")

    assert all(e.score is None for e in result.entries)


def test_the_canonical_flag_is_independent_of_the_rank_field():
    result = enumerate_tautomers(Chem.MolFromSmiles("Oc1ccccn1"), "m")
    canonical = [e for e in result.entries if e.metadata["canonical"]]

    assert len(canonical) == 1 and "(canonical)" in canonical[0].label
    # The flag comes from RDKit's Canonicalize and the rank from the score;
    # one is not derived from the other.
    assert "rdkit_rank" in canonical[0].metadata and "canonical" in canonical[0].metadata


def test_two_tautomers_with_identical_scores_are_tied_and_neither_is_preferred():
    result = enumerate_tautomers(Chem.MolFromSmiles(TIED_ENOLS), "m")
    tied = [e for e in result.entries if e.metadata["rdkit_tied"]]

    assert len(tied) == 2
    assert len({e.metadata["rdkit_score"] for e in tied}) == 1
    assert len({e.metadata["rdkit_rank"] for e in tied}) == 1
    assert all(", tied]" in e.label for e in tied)
    smiles = [e.metadata["smiles"] for e in tied]
    assert smiles == sorted(smiles)  # deterministic display order, not a preference
    assert all(e.metadata["rdkit_rank"] == 2 for e in tied)  # competition: 1, 2, 2


def test_the_display_order_is_deterministic():
    first = [e.label for e in enumerate_tautomers(Chem.MolFromSmiles(TIED_ENOLS), "m").entries]
    second = [e.label for e in enumerate_tautomers(Chem.MolFromSmiles(TIED_ENOLS), "m").entries]

    assert first == second


def test_the_result_names_the_rdkit_version_and_what_the_score_is_not():
    params = enumerate_tautomers(Chem.MolFromSmiles("CC(=O)C"), "m").provenance.parameters

    assert params["rdkit_version"] == RDKIT_VERSION
    assert "not an energy" in params["score_meaning"]


# --- the cross-check --------------------------------------------------------


def _check(scores, energies, complete=True):
    return cross_check(scores, energies, complete)


def test_the_four_verdicts():
    assert _check({"a": 5, "b": 2}, {"a": 0.0, "b": 9.0})["verdict"] == AGREES
    assert _check({"a": 5, "b": 2}, {"a": 9.0, "b": 0.0})["verdict"] == DIFFERS
    assert _check({"a": 5, "b": 5}, {"a": 0.0, "b": 9.0})["verdict"] == TIED
    assert _check({"a": 5, "b": 2}, {"a": 0.0, "b": 9.0}, complete=False)["verdict"] == INDETERMINATE


def test_a_tie_follows_the_declared_tolerance_not_float_equality():
    """RDKit has a clear top (A); ORCA's A is lower than B by a margin just
    inside, then just outside, the comparison tolerance."""
    inside = _check({"a": 5, "b": 2}, {"a": 0.0, "b": ORCA_COMPARISON_TOLERANCE_KCAL - 0.01})
    outside = _check({"a": 5, "b": 2}, {"a": 0.0, "b": ORCA_COMPARISON_TOLERANCE_KCAL + 0.01})

    assert inside["verdict"] == TIED and inside["orca_tie"] and not inside["rdkit_tie"]
    assert outside["verdict"] == AGREES and not outside["orca_tie"]


def test_an_rdkit_tie_is_not_an_orca_tie():
    """It means the heuristic did not distinguish its top candidates at its own
    score resolution -- not that ORCA is tied."""
    check = _check({"a": 5, "b": 5, "c": 1}, {"a": 0.0, "b": 8.0, "c": 20.0})

    assert check["verdict"] == TIED and check["rdkit_tie"] and not check["orca_tie"]


def test_an_incomplete_orca_result_is_indeterminate_never_differs():
    check = _check({"a": 5, "b": 2}, {"b": 0.0}, complete=False)

    assert check["verdict"] == INDETERMINATE and check["orca_incomplete"] is True


def test_a_missing_heuristic_score_is_indeterminate():
    assert _check({"a": 5, "b": None}, {"a": 0.0, "b": 9.0})["verdict"] == INDETERMINATE


# --- in the ORCA result ------------------------------------------------------


def _outcome(smiles, energies_by_tautomer_rank):
    """Real candidates; `energies_by_tautomer_rank` are Hartree OFFSETS above
    -100.0, indexed by distinct RDKit score best first, so a bigger offset is
    a LESS stable tautomer."""
    # One start geometry per stereo class: this file is about the tautomer-level
    # comparison, not about conformer counts.
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles(smiles), policy=MODEL_POLICY_SINGLE)
    scores = sorted({c.rdkit_score for c in candidates}, reverse=True)
    results = []
    for candidate in candidates:
        energy = energies_by_tautomer_rank[scores.index(candidate.rdkit_score)]
        results.append(
            CandidateResult.for_candidate(
                candidate, "", CandidateStatus.SUCCEEDED, absolute_energy_hartree=-100.0 + energy
            )
        )
    return build_outcome(results)


def test_a_multi_stereo_tautomer_is_compared_once_at_tautomer_level(monkeypatch):
    import openchem.chem.tautomer_distribution as module

    seen = {}
    real = module.cross_check
    monkeypatch.setattr(module, "cross_check", lambda scores, energies, complete: seen.update(
        scores=scores, energies=energies) or real(scores, energies, complete))
    outcome = _outcome(TIED_ENOLS, [0.01, 0.0, 0.0])

    outcome.rdkit_cross_check()

    assert len(outcome.candidates) == 5 and len(seen["scores"]) == 3 == len(seen["energies"])


def test_the_result_carries_the_cross_check_and_the_rdkit_version():
    outcome = _outcome(TIED_ENOLS, [0.0, 0.002, 0.003])
    params = build_structure_set_result(outcome, "m", "HF STO-3G", run_id="r").provenance.parameters

    assert params["rdkit_version"] == RDKIT_VERSION
    # RDKit's unique top (the keto form, 5 vs 2) is also ORCA's lowest, by
    # ~1.3 kcal/mol, so both sides are clear and the verdict is "agrees".
    assert params["rdkit_cross_check"]["verdict"] == AGREES
    assert not params["rdkit_cross_check"]["rdkit_tie"] and not params["rdkit_cross_check"]["orca_tie"]


def test_an_incomplete_result_cross_checks_as_indeterminate():
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles("CCC(C)=O"))
    results = [
        CandidateResult.for_candidate(c, "", CandidateStatus.SUCCEEDED, absolute_energy_hartree=-100.0)
        for c in candidates[:-1]
    ] + [CandidateResult.for_candidate(candidates[-1], "", CandidateStatus.FAILED)]

    check = build_outcome(results).rdkit_cross_check()

    assert check["verdict"] == INDETERMINATE and check["orca_incomplete"] is True


def test_the_cross_check_never_reaches_populations_or_the_displayed_score():
    outcome = _outcome(TIED_ENOLS, [0.0, 0.002, 0.003])
    result = build_structure_set_result(outcome, "m", "HF STO-3G", run_id="r")

    assert all(entry.score is None for entry in result.entries)
    assert outcome.populations is not None and sum(outcome.populations.values()) == pytest.approx(1.0)


# --- the summary line --------------------------------------------------------


@pytest.mark.parametrize(
    ("check", "needle"),
    [
        ({"verdict": "agrees"}, "agrees with ORCA"),
        ({"verdict": "differs"}, "prefers a different tautomer"),
        ({"verdict": "tied", "rdkit_tie": True}, "does not distinguish its top candidates"),
        ({"verdict": "tied", "orca_tie": True, "tolerance_kcal": 0.5}, "within 0.5 kcal/mol"),
        ({"verdict": "indeterminate", "orca_incomplete": True}, "ORCA result is incomplete"),
    ],
)
def test_the_summary_words_each_verdict(check, needle):
    from openchem.ui.result_adapters import _rdkit_cross_check_text

    assert needle in _rdkit_cross_check_text(check)
