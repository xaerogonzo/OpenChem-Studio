"""Tests for `chem/tautomer_distribution.py`: candidate generation/
fingerprinting/embedding, and the pure incomplete-aware result builder.

No ORCA, no Qt -- the QC orchestration this module feeds lives in
`services/quantum_chemistry_service.py` and is tested separately.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.tautomer_distribution import (
    CONFIRMATION_THRESHOLD,
    DEFAULT_MAX_CANDIDATES,
    FAILURE_OPTIMIZATION_NOT_CONVERGED,
    HARTREE_TO_KCAL_PER_MOL,
    VALIDATION_UNVALIDATED,
    CandidateResult,
    CandidateStatus,
    _embed_candidate,
    _fingerprint,
    build_outcome,
    build_structure_set_result,
    format_population_percent,
    generate_tautomer_candidates,
    model_version,
)

CYCLOHEXANONE = "O=C1CCCCC1"  # keto <-> enol, the same fixture test_phase27_structures.py uses


def _result(
    fingerprint: str,
    status: CandidateStatus,
    energy: float | None = None,
    reason_code: str = "",
) -> CandidateResult:
    return CandidateResult(
        fingerprint=fingerprint,
        molblock="",
        status=status,
        absolute_energy_hartree=energy,
        failure_reason_code=reason_code,
    )


# --- candidate generation / fingerprinting / embedding ---------------------


def test_cyclohexanone_produces_distinct_keto_and_enol_candidates():
    candidates, embedding_failures = generate_tautomer_candidates(Chem.MolFromSmiles(CYCLOHEXANONE))
    assert embedding_failures == 0
    assert len(candidates) >= 2
    assert len({c.fingerprint for c in candidates}) == len(candidates)
    for candidate in candidates:
        assert candidate.mol.GetNumConformers() == 1


def test_candidate_generation_is_deterministic_across_calls():
    first, _ = generate_tautomer_candidates(Chem.MolFromSmiles(CYCLOHEXANONE))
    second, _ = generate_tautomer_candidates(Chem.MolFromSmiles(CYCLOHEXANONE))
    assert [c.fingerprint for c in first] == [c.fingerprint for c in second]


def test_candidates_are_sorted_by_fingerprint_not_enumerator_order():
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles(CYCLOHEXANONE))
    assert [c.fingerprint for c in candidates] == sorted(c.fingerprint for c in candidates)


def test_fingerprint_is_stable_for_the_same_molblock():
    mol = Chem.MolFromSmiles(CYCLOHEXANONE)
    block = Chem.MolToMolBlock(mol, kekulize=False)
    assert _fingerprint(block) == _fingerprint(block)


def test_fingerprint_differs_for_a_real_structural_difference():
    keto = Chem.MolToMolBlock(Chem.MolFromSmiles("O=C1CCCCC1"), kekulize=False)
    enol = Chem.MolToMolBlock(Chem.MolFromSmiles("OC1=CCCCC1"), kekulize=False)
    assert _fingerprint(keto) != _fingerprint(enol)


def test_embedding_failure_is_reported_not_silently_dropped(monkeypatch):
    import openchem.chem.tautomer_distribution as module

    monkeypatch.setattr(module.AllChem, "EmbedMolecule", lambda *a, **k: -1)
    embedded, seed = _embed_candidate(Chem.MolFromSmiles("C"), base_seed=0, index=0)
    assert embedded is None
    assert seed == 0


def test_generate_candidates_counts_embedding_failures_separately(monkeypatch):
    import openchem.chem.tautomer_distribution as module

    monkeypatch.setattr(module, "_embed_candidate", lambda mol, base_seed, index: (None, base_seed + index))
    candidates, embedding_failures = generate_tautomer_candidates(Chem.MolFromSmiles(CYCLOHEXANONE))
    assert candidates == []
    assert embedding_failures >= 2


def test_confirmation_threshold_is_smaller_than_the_free_enumeration_cap():
    assert CONFIRMATION_THRESHOLD < DEFAULT_MAX_CANDIDATES


# --- build_outcome: the complete case ---------------------------------------


def test_all_candidates_succeeding_produces_a_complete_outcome_with_populations():
    candidates = [
        _result("a", CandidateStatus.SUCCEEDED, energy=-100.0),
        _result("b", CandidateStatus.SUCCEEDED, energy=-100.0 + 1.0 / HARTREE_TO_KCAL_PER_MOL),
    ]
    outcome = build_outcome(candidates)

    assert outcome.complete is True
    assert outcome.populations is not None
    assert sum(outcome.populations.values()) == pytest.approx(1.0)
    assert outcome.populations["a"] > outcome.populations["b"]
    assert outcome.relative_energy_kcal_mol["a"] == pytest.approx(0.0)
    assert outcome.relative_energy_kcal_mol["b"] == pytest.approx(1.0, rel=1e-6)
    assert "incomplete" not in outcome.energy_label


def test_identical_energies_in_any_order_give_equal_populations():
    forward = build_outcome(
        [_result("a", CandidateStatus.SUCCEEDED, energy=-50.0), _result("b", CandidateStatus.SUCCEEDED, energy=-50.0)]
    )
    backward = build_outcome(
        [_result("b", CandidateStatus.SUCCEEDED, energy=-50.0), _result("a", CandidateStatus.SUCCEEDED, energy=-50.0)]
    )
    assert forward.populations == pytest.approx({"a": 0.5, "b": 0.5})
    assert backward.populations == pytest.approx({"a": 0.5, "b": 0.5})


# --- build_outcome: the incomplete case -- the scientific trap -------------


def test_one_failed_candidate_means_no_populations_at_all():
    outcome = build_outcome(
        [
            _result("a", CandidateStatus.SUCCEEDED, energy=-100.0),
            _result("b", CandidateStatus.FAILED, reason_code=FAILURE_OPTIMIZATION_NOT_CONVERGED),
        ]
    )
    assert outcome.complete is False
    assert outcome.populations is None
    assert "incomplete" in outcome.energy_label


def test_survivor_relative_energy_is_not_presented_as_the_complete_set_baseline():
    """The trap a prior draft of this plan missed: if the FAILED candidate
    would actually have been the true minimum, the survivors' reported gap
    is relative only to each other, not to the real global minimum -- and
    this is exactly why `complete` must be read before trusting
    `relative_energy_kcal_mol` as "the" ΔE."""
    outcome = build_outcome(
        [
            _result("survivor_low", CandidateStatus.SUCCEEDED, energy=-100.0),
            _result("survivor_high", CandidateStatus.SUCCEEDED, energy=-100.0 + 1.0 / HARTREE_TO_KCAL_PER_MOL),
            _result("would_have_been_lowest", CandidateStatus.FAILED, reason_code="optimization_not_converged"),
        ]
    )
    assert outcome.complete is False
    assert outcome.relative_energy_kcal_mol["survivor_low"] == pytest.approx(0.0)
    assert outcome.relative_energy_kcal_mol["survivor_high"] == pytest.approx(1.0, rel=1e-6)
    assert "would_have_been_lowest" not in outcome.relative_energy_kcal_mol
    assert outcome.populations is None


def test_zero_successful_candidates_gives_an_empty_outcome():
    outcome = build_outcome(
        [
            _result("a", CandidateStatus.FAILED, reason_code="embedding_failed"),
            _result("b", CandidateStatus.FAILED, reason_code="energy_unparseable"),
        ]
    )
    assert outcome.complete is False
    assert outcome.populations is None
    assert outcome.relative_energy_kcal_mol == {}
    assert outcome.failed_count == 2
    assert outcome.succeeded_count == 0


def test_an_empty_candidate_list_is_not_treated_as_complete():
    outcome = build_outcome([])
    assert outcome.complete is False
    assert outcome.populations is None


def test_a_cancelled_candidate_also_blocks_completeness():
    outcome = build_outcome(
        [
            _result("a", CandidateStatus.SUCCEEDED, energy=-1.0),
            _result("b", CandidateStatus.NOT_RUN),
        ]
    )
    assert outcome.complete is False
    assert outcome.populations is None
    assert outcome.not_run_count == 1


# --- format_population_percent ----------------------------------------------


def test_format_population_percent_rounds_a_normal_value():
    assert format_population_percent(0.4217) == "42.17%"


def test_format_population_percent_never_shows_a_bare_zero_for_a_nonzero_value():
    assert format_population_percent(1e-8) == "<0.01%"


def test_format_population_percent_shows_full_zero_as_small_not_bare():
    assert format_population_percent(0.0) == "<0.01%"


def test_format_population_percent_rejects_a_negative_value():
    with pytest.raises(ValueError):
        format_population_percent(-0.1)


# --- constant cross-check: catches the two Hartree<->kcal/mol constants ----
# drifting apart if `tests/test_boltzmann.py`'s own value is ever changed
# without updating this one, or vice versa.


def test_hartree_to_kcal_constant_matches_the_one_boltzmann_tests_already_use():
    from tests.test_boltzmann import KCAL_PER_MOL

    assert HARTREE_TO_KCAL_PER_MOL == pytest.approx(1.0 / KCAL_PER_MOL, rel=1e-12)


# --- model_version / build_structure_set_result -----------------------------


def test_model_version_changes_when_any_input_changes():
    base = model_version("HF def2-SVP", "ETKDGv3", 298.15)
    assert model_version("B3LYP def2-SVP", "ETKDGv3", 298.15) != base
    assert model_version("HF def2-SVP", "ETKDGv2", 298.15) != base
    assert model_version("HF def2-SVP", "ETKDGv3", 300.0) != base
    assert model_version("HF def2-SVP", "ETKDGv3", 298.15) == base


def _molblock(smiles: str) -> str:
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


def test_build_structure_set_result_includes_every_candidate_succeeded_or_not():
    outcome = build_outcome(
        [
            CandidateResult("a", _molblock("CCO"), CandidateStatus.SUCCEEDED, absolute_energy_hartree=-100.0),
            CandidateResult(
                "b",
                _molblock("CC=O"),
                CandidateStatus.FAILED,
                failure_reason="did not converge",
                failure_reason_code=FAILURE_OPTIMIZATION_NOT_CONVERGED,
            ),
        ]
    )
    result = build_structure_set_result(outcome, "mol-1", "HF def2-SVP", run_id="run-1")

    assert len(result.entries) == 2
    statuses = {entry.metadata["status"] for entry in result.entries}
    assert statuses == {"succeeded", "failed"}
    succeeded = next(e for e in result.entries if e.metadata["status"] == "succeeded")
    assert succeeded.energy == pytest.approx(0.0)
    # Incomplete (one candidate failed) -- no population/score on ANY entry.
    assert succeeded.score is None
    failed = next(e for e in result.entries if e.metadata["status"] == "failed")
    assert failed.energy is None
    assert failed.metadata["failure_reason_code"] == FAILURE_OPTIMIZATION_NOT_CONVERGED
    assert result.provenance.parameters["complete"] is False
    assert result.provenance.parameters["validation_branch"] == VALIDATION_UNVALIDATED
    assert result.provenance.parameters["candidate_count_succeeded"] == 1
    assert result.provenance.parameters["candidate_count_failed"] == 1
    assert result.provenance.parameters["parent_run_id"] == "run-1"


def test_build_structure_set_result_carries_the_population_score_when_complete():
    outcome = build_outcome(
        [
            CandidateResult("a", _molblock("CCO"), CandidateStatus.SUCCEEDED, absolute_energy_hartree=-100.0),
            CandidateResult(
                "b", _molblock("CC=O"), CandidateStatus.SUCCEEDED, absolute_energy_hartree=-100.0 + 1.0
            ),
        ]
    )
    result = build_structure_set_result(outcome, "mol-1", "HF def2-SVP", run_id="run-2")
    assert all(entry.score is not None for entry in result.entries)
    assert sum(entry.score for entry in result.entries) == pytest.approx(1.0)
    assert result.provenance.parameters["complete"] is True


def test_build_structure_set_result_orders_ascending_energy_with_failures_last():
    outcome = build_outcome(
        [
            CandidateResult("c", _molblock("CCO"), CandidateStatus.SUCCEEDED, absolute_energy_hartree=-99.0),
            CandidateResult("a", _molblock("CC=O"), CandidateStatus.SUCCEEDED, absolute_energy_hartree=-100.0),
            CandidateResult("b", _molblock("C"), CandidateStatus.FAILED, failure_reason_code="embedding_failed"),
        ]
    )
    result = build_structure_set_result(outcome, "mol-1", "HF def2-SVP", run_id="run-3")
    fingerprints_in_order = [entry.metadata["fingerprint"] for entry in result.entries]
    assert fingerprints_in_order == ["a", "c", "b"]
