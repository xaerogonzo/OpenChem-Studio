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
    VALIDATION_RANKING_ONLY,
    VALIDATION_UNVALIDATED,
    VALIDATION_VALIDATED,
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
from openchem.domain.result_store import result_id_of

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


def test_build_structure_set_result_set_id_matches_the_registered_calculator_id():
    """`property_panel.py`'s documented invariant: a generator's `set_id`
    equals its registered `calculator_id` ("orca.tautomer_distribution",
    `bootstrap.py`) exactly -- never the bare "tautomer_distribution",
    which is a different namespace (the QC-run `results` dict key
    `_render_run` reads). A mismatch here would silently file this result
    under the "other" Properties category instead of "quantum_chemistry",
    and would make `make_identity`/`result_id_of` disagree with the
    registered calculator."""
    outcome = build_outcome(
        [CandidateResult("a", _molblock("CCO"), CandidateStatus.SUCCEEDED, absolute_energy_hartree=-100.0)]
    )
    result = build_structure_set_result(outcome, "mol-1", "HF def2-SVP", run_id="run-1")

    assert result.set_id == "orca.tautomer_distribution"
    assert result_id_of(result) == "orca.tautomer_distribution"


def _complete_outcome():
    return build_outcome(
        [
            CandidateResult("a", _molblock("CCO"), CandidateStatus.SUCCEEDED, absolute_energy_hartree=-100.0),
            CandidateResult(
                "b", _molblock("CC=O"), CandidateStatus.SUCCEEDED, absolute_energy_hartree=-100.0 + 1.0
            ),
        ]
    )


def test_build_structure_set_result_withholds_score_until_actually_validated():
    """The scientific-integrity gap a prior draft of this module had:
    `outcome.populations` is real and computed as soon as the run is
    complete, but `StructureGridWidget`'s shared caption renders any
    non-None `score` directly with no awareness of validation state -- so
    an unvalidated (the default) or ranking-only result must never put a
    number there, even though the real population IS known and complete."""
    result = build_structure_set_result(
        _complete_outcome(), "mol-1", "HF def2-SVP", run_id="run-2", validation_branch=VALIDATION_UNVALIDATED
    )
    assert all(entry.score is None for entry in result.entries)
    # Not lost, just not displayed -- retained for audit under its own key.
    assert all(entry.metadata["population_unvalidated"] is not None for entry in result.entries)

    ranking_only = build_structure_set_result(
        _complete_outcome(), "mol-1", "HF def2-SVP", run_id="run-3", validation_branch=VALIDATION_RANKING_ONLY
    )
    assert all(entry.score is None for entry in ranking_only.entries)


def test_build_structure_set_result_carries_the_population_score_once_validated():
    result = build_structure_set_result(
        _complete_outcome(), "mol-1", "HF def2-SVP", run_id="run-2", validation_branch=VALIDATION_VALIDATED
    )
    assert all(entry.score is not None for entry in result.entries)
    assert sum(entry.score for entry in result.entries) == pytest.approx(1.0)
    assert result.provenance.parameters["complete"] is True
    assert result.provenance.parameters["validation_branch"] == VALIDATION_VALIDATED


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


# --- stereo is shown as drawn, never invented from the 3D start geometry -----


def _result_labels(smiles: str) -> list[str]:
    """Run a molecule through the real candidate generator and the real
    result builder, as the service does, and return the entry labels."""
    candidates, _failures = generate_tautomer_candidates(Chem.MolFromSmiles(smiles))
    outcome = build_outcome(
        [
            CandidateResult(
                fingerprint=c.fingerprint,
                molblock=Chem.MolToMolBlock(c.mol, kekulize=False),
                display_molblock=c.display_molblock,
                status=CandidateStatus.SUCCEEDED,
                absolute_energy_hartree=-100.0,
            )
            for c in candidates
        ]
    )
    result = build_structure_set_result(outcome, "mol-1", "HF def2-SVP", run_id="run-1")
    return [entry.label for entry in result.entries]


def test_an_unspecified_stereocentre_is_not_labelled_with_an_invented_one():
    """FOUND IN THE DRIVEN APP: racemic propylene glycol was drawn with no
    stereochemistry and its candidate came back labelled C[C@@H](O)CO --
    chirality read back off the embedded 3D coordinates. The energies were
    unaffected; the label named a compound nobody specified."""
    labels = _result_labels("CC(O)CO")

    assert labels and all("@" not in label for label in labels), labels


def test_a_stereocentre_the_user_specified_is_kept():
    labels = _result_labels("C[C@H](O)CO")

    assert labels and all("@" in label for label in labels), labels


def test_the_shown_structure_is_flat_not_the_3d_start_geometry():
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles("CC(O)CO"))
    shown = Chem.MolFromMolBlock(candidates[0].display_molblock)

    assert shown is not None
    assert max(abs(shown.GetConformer().GetAtomPosition(i).z) for i in range(shown.GetNumAtoms())) == 0.0


# --- unspecified stereo is fixed to ONE configuration across candidates -------
#
# Embedding picks an arbitrary arrangement for every unspecified element, and
# each candidate has its own seed, so before this the keto and enol forms of a
# molecule with two undrawn centres landed on different diastereomers and the
# reported gap mixed a tautomer difference with a diastereomer one.

DIMETHYLCYCLOHEXANONE = "CC1CCCC(=O)C1C"  # keto, and two enols; two undrawn centres


def _centre_tags(candidate) -> dict[int, Chem.ChiralType]:
    """Each centre's configuration as it ACTUALLY embedded, read off the
    candidate's 3D coordinates (heavy-atom indices are shared by every
    tautomer, so the same index is the same atom in each)."""
    flat = Chem.Mol(candidate.mol)
    Chem.AssignStereochemistryFrom3D(flat)
    flat = Chem.RemoveHs(flat)
    return {
        atom.GetIdx(): atom.GetChiralTag()
        for atom in flat.GetAtoms()
        if atom.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED
    }


@pytest.mark.parametrize("base_seed", range(6))
def test_candidates_share_one_configuration_at_each_undrawn_centre(base_seed):
    candidates, failures = generate_tautomer_candidates(
        Chem.MolFromSmiles(DIMETHYLCYCLOHEXANONE), base_seed=base_seed
    )
    assert failures == 0 and len(candidates) == 3

    seen: dict[int, set] = {}
    for candidate in candidates:
        for idx, tag in _centre_tags(candidate).items():
            seen.setdefault(idx, set()).add(tag)

    shared = {idx for idx, tags in seen.items() if len(tags) != 1}
    assert not shared, f"centres {shared} embedded in more than one configuration"
    # The keto form and one enol carry both centres, so the comparison that
    # used to be arbitrary is genuinely exercised.
    assert sum(1 for c in candidates if len(_centre_tags(c)) == 2) >= 2


def test_two_undrawn_centres_are_reported_as_a_choice_that_moves_the_energy():
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles(DIMETHYLCYCLOHEXANONE))

    assert any(c.stereo_ambiguous for c in candidates)
    assert max(c.stereo_pinned for c in candidates) == 2


def test_one_undrawn_centre_alone_is_not_reported_as_ambiguous():
    """Enantiomers are degenerate: fixing propylene glycol's one centre moves
    no energy, so the result has nothing to disclose."""
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles("CC(O)CO"))

    assert candidates and not any(c.stereo_ambiguous for c in candidates)
    assert all(c.stereo_pinned == 1 for c in candidates)


def test_a_drawn_centre_is_never_overridden_by_the_shared_configuration():
    """One centre drawn, one not: the drawn one keeps its configuration in
    every seed, and the undrawn one is the thing fixed."""
    drawn = Chem.MolFromSmiles("C[C@H](O)C(C)O")
    reference, _ = generate_tautomer_candidates(drawn, base_seed=0)
    expected = _centre_tags(reference[0])[1]
    for base_seed in range(1, 5):
        candidates, _ = generate_tautomer_candidates(drawn, base_seed=base_seed)
        assert _centre_tags(candidates[0])[1] == expected
    assert reference[0].stereo_pinned == 1 and reference[0].stereo_ambiguous


def test_an_undrawn_double_bond_is_fixed_and_reported():
    """The enumerator marks a C=C it just created STEREOANY, which ETKDG leaves
    free: measured, butanone's enol embedded E and Z across seeds."""
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles("CCC(C)=O"))
    enol = [c for c in candidates if Chem.MolToSmiles(Chem.RemoveHs(c.mol)) == "CC=C(C)O"]

    assert len(enol) == 1
    assert enol[0].stereo_pinned == 1 and enol[0].stereo_ambiguous


@pytest.mark.parametrize(
    ("relation", "expected_cis"),
    [(Chem.BondStereo.STEREOCIS, True), (Chem.BondStereo.STEREOTRANS, False)],
)
def test_a_pinned_double_bond_embeds_the_same_way_in_every_seed(relation, expected_cis):
    """The mechanism itself: apply a pin to a C=C the enumerator left free and
    embed it under many seeds. Without the pin, seeds gave both 0 and 180."""
    from rdkit.Chem import rdMolTransforms

    from openchem.chem.tautomer_distribution import _apply_pins, _bond_neighbours, _StereoPins

    enol = Chem.MolFromSmiles("CC=C(C)O")
    bond_idx = next(b.GetIdx() for b in enol.GetBonds() if b.GetBondType() == Chem.BondType.DOUBLE)
    first, last = _bond_neighbours(enol, bond_idx)
    pins = _StereoPins(bonds={bond_idx: (first, last, relation)})
    pinned = _apply_pins(enol, pins, [], [bond_idx])

    bond = pinned.GetBondWithIdx(bond_idx)
    for seed in range(8):
        embedded, _ = _embed_candidate(pinned, base_seed=seed, index=0)
        dihedral = rdMolTransforms.GetDihedralDeg(
            embedded.GetConformer(), first, bond.GetBeginAtomIdx(), bond.GetEndAtomIdx(), last
        )
        assert (abs(dihedral) < 30) is expected_cis, (seed, dihedral)


def test_the_label_still_shows_the_stereo_as_drawn_not_as_pinned():
    """Pinning is a computational choice; the shown structure must not claim
    it. The label of a two-undrawn-centre molecule carries no @."""
    labels = _result_labels(DIMETHYLCYCLOHEXANONE)

    assert labels and all("@" not in label for label in labels), labels


def test_the_result_records_what_was_pinned_and_the_model_version_moves():
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles(DIMETHYLCYCLOHEXANONE))
    outcome = build_outcome(
        [
            CandidateResult(
                fingerprint=c.fingerprint,
                molblock="",
                display_molblock=c.display_molblock,
                status=CandidateStatus.SUCCEEDED,
                absolute_energy_hartree=-100.0,
                stereo_pinned=c.stereo_pinned,
                stereo_ambiguous=c.stereo_ambiguous,
            )
            for c in candidates
        ]
    )
    result = build_structure_set_result(outcome, "mol-1", "HF def2-SVP", run_id="run-1")
    params = result.provenance.parameters

    assert params["stereo_pinned"] == 2
    assert params["stereo_ambiguous"] is True
    # Fixing stereo changes what the energies describe, so it is a different
    # model: a stored "validated" stamp must never carry over.
    assert params["model_version"].startswith("tautomer-boltzmann-v2|")
