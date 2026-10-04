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
    MODEL_POLICY,
    MODEL_POLICY_SINGLE,
    TAUTOMER_MODEL_REVISION,
    CandidateResult,
    CandidateStatus,
    TautomerState,
    _embed_candidate,
    _enumerate_stereo_classes,
    _fingerprint,
    _mirror_stereo,
    _stereo_class_key,
    build_outcome,
    build_structure_set_result,
    format_population_percent,
    generate_tautomer_candidates,
    model_assumptions,
    model_version,
)

# The stereo-mechanics tests below describe ONE embedded geometry per stereo class
# (the `single` policy, revision 3's behaviour): a conformer search multiplies the
# jobs per class, which `test_tautomer_conformers.py` and the v4 tests at the end of
# this file cover. Passing the policy explicitly keeps these assertions about stereo
# enumeration rather than about conformer counts.
import functools  # noqa: E402

_generate_with_search = generate_tautomer_candidates
generate_tautomer_candidates = functools.partial(_generate_with_search, policy=MODEL_POLICY_SINGLE)
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
            CandidateResult.for_candidate(
                c,
                Chem.MolToMolBlock(c.mol, kekulize=False),
                CandidateStatus.SUCCEEDED,
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


# --- undrawn stereo is ENUMERATED, and a tautomer is its lowest stereoisomer ---
#
# #177 pinned every undrawn element to one shared configuration, so the energies
# described one arbitrary diastereomer. Each unique stereo class is now its own
# ORCA job, and a tautomer is represented by its lowest SUCCESSFUL one.

DIMETHYLCYCLOHEXANONE = "CC1CCCC(=O)C1C"  # keto + two enols; two undrawn centres
BUTANEDIOL = "CC(O)C(C)O"  # two undrawn centres: a meso form and an enantiomer pair
TRIOL = "CC(O)C(O)C(C)O"  # three undrawn centres: raw isomers outnumber unique classes


def _by_tautomer(candidates):
    groups: dict[str, list] = {}
    for candidate in candidates:
        groups.setdefault(candidate.tautomer_fingerprint, []).append(candidate)
    return groups


def _succeeded(candidate, energy):
    return CandidateResult.for_candidate(
        candidate, "", CandidateStatus.SUCCEEDED, absolute_energy_hartree=energy
    )


def _failed(candidate):
    return CandidateResult.for_candidate(
        candidate, "", CandidateStatus.FAILED, failure_reason_code=FAILURE_OPTIMIZATION_NOT_CONVERGED
    )


def test_each_unique_stereo_class_is_its_own_job():
    candidates, failures = generate_tautomer_candidates(Chem.MolFromSmiles(DIMETHYLCYCLOHEXANONE))

    assert failures == 0
    groups = _by_tautomer(candidates)
    # The C=C enol toward C2 keeps one centre (one class); the keto form and the
    # other enol keep two (a cis and a trans class, each standing for a pair).
    assert sorted(len(members) for members in groups.values()) == [1, 2, 2]
    for members in groups.values():
        assert {c.stereo.isomers_calculated for c in members} == {len(members)}
        assert all(c.stereo.isomers_total == len(members) and c.stereo.isomers_total_known for c in members)
        assert not any(c.stereo.truncated or c.stereo.fallback for c in members)


@pytest.mark.parametrize("base_seed", range(4))
def test_the_jobs_of_one_tautomer_embed_in_genuinely_different_configurations(base_seed):
    """The point of enumerating: each job's 3D geometry is the configuration it
    claims, so the two jobs of a tautomer are different diastereomers."""
    candidates, _ = generate_tautomer_candidates(
        Chem.MolFromSmiles(DIMETHYLCYCLOHEXANONE), base_seed=base_seed
    )
    for members in _by_tautomer(candidates).values():
        if len(members) < 2:
            continue
        keys = set()
        for member in members:
            flat = Chem.Mol(member.mol)
            Chem.AssignStereochemistryFrom3D(flat)
            keys.add(_stereo_class_key(Chem.RemoveHs(flat)))
        assert len(keys) == len(members), keys


# --- the mirror image: tetrahedral tags only ---------------------------------


def test_an_enantiomer_pair_is_one_class_but_diastereomers_and_e_z_pairs_are_not():
    def key(smiles):
        return _stereo_class_key(Chem.MolFromSmiles(smiles))

    assert key("C[C@H](O)CO") == key("C[C@@H](O)CO")  # R/S: merged
    assert key("C[C@H](O)[C@H](C)O") == key("C[C@@H](O)[C@@H](C)O")  # (R,R)/(S,S): merged
    assert key("C[C@H](O)[C@@H](C)O") != key("C[C@H](O)[C@H](C)O")  # meso vs chiral
    assert key("C/C=C/C") != key("C/C=C\\C")  # E/Z: NEVER merged
    assert key("CCO") == key("CCO")  # achiral: one


def test_the_isomeric_form_is_what_tells_diastereomers_apart():
    """A non-isomeric comparison would collapse the very pairs that must stay
    distinct; this fixes that the key reads stereo, not just connectivity."""
    meso, chiral = Chem.MolFromSmiles("C[C@H](O)[C@@H](C)O"), Chem.MolFromSmiles("C[C@H](O)[C@H](C)O")

    assert Chem.MolToSmiles(meso, isomericSmiles=False) == Chem.MolToSmiles(chiral, isomericSmiles=False)
    assert _stereo_class_key(meso) != _stereo_class_key(chiral)


def test_mirroring_inverts_tetrahedral_tags_and_leaves_double_bond_stereo_alone():
    mirrored = _mirror_stereo(Chem.MolFromSmiles("C[C@H](O)/C=C/C"))

    assert Chem.MolToSmiles(mirrored) == Chem.MolToSmiles(Chem.MolFromSmiles("C[C@@H](O)/C=C/C"))


def test_propylene_glycol_is_one_class_standing_for_its_enantiomer_pair():
    """The regression for #176/#177, asserted for the reason and not just the
    count: the two enantiomers fall in ONE class, the retained representative
    is the same structure on every run, and the shown structure stays as drawn."""
    mol = Chem.MolFromSmiles("CC(O)CO")
    first, _ = generate_tautomer_candidates(mol)
    second, _ = generate_tautomer_candidates(mol)

    assert len(first) == 1 and first[0].stereo.enantiomer_merged
    assert first[0].fingerprint == second[0].fingerprint
    assert "@" not in Chem.MolToSmiles(Chem.MolFromMolBlock(first[0].display_molblock))


def test_a_drawn_centre_with_an_undrawn_one_gives_diastereomers_never_merged():
    """The whole-molecule mirror inverts the DRAWN centre too, so it is never
    another generated isomer: these are two diastereomers, two jobs."""
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles("C[C@H](O)C(C)O"))

    assert len(candidates) == 2
    assert not any(c.stereo.enantiomer_merged for c in candidates)
    assert len({c.fingerprint for c in candidates}) == 2


def test_an_enantiomer_pair_and_one_more_diastereomer_are_two_jobs_not_three():
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles(BUTANEDIOL))

    assert len(candidates) == 2  # meso, and the chiral pair counted once
    assert len({c.tautomer_fingerprint for c in candidates}) == 1
    assert sorted(c.stereo.enantiomer_merged for c in candidates) == [False, True]


def test_the_two_configurations_of_an_undrawn_double_bond_are_both_enumerated():
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles("CCC(C)=O"))
    enol = [c for c in candidates if c.stereo.isomers_calculated == 2]

    assert len(enol) == 2
    assert len({c.fingerprint for c in enol}) == 2
    assert not any(c.stereo.enantiomer_merged for c in enol)


def test_identity_does_not_depend_on_the_order_rdkit_enumerates_in(monkeypatch):
    """A class's fingerprint, and the geometry it embeds from, must not depend
    on which mirror image RDKit happened to list first."""
    import openchem.chem.tautomer_distribution as module

    mol = Chem.MolFromSmiles(BUTANEDIOL)
    forward, _ = generate_tautomer_candidates(mol)
    original = module.EnumerateStereoisomers
    monkeypatch.setattr(
        module, "EnumerateStereoisomers", lambda m, options=None: iter(reversed(list(original(m, options=options))))
    )
    backward, _ = generate_tautomer_candidates(mol)

    assert {c.fingerprint for c in forward} == {c.fingerprint for c in backward}


def test_candidates_differing_in_one_retained_element_never_share_a_fingerprint():
    for smiles in (BUTANEDIOL, DIMETHYLCYCLOHEXANONE, "CCC(C)=O"):
        candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles(smiles))
        assert len({c.fingerprint for c in candidates}) == len(candidates), smiles


def test_a_class_standing_for_an_enantiomer_pair_is_the_same_structure_in_every_seed():
    reference, _ = generate_tautomer_candidates(Chem.MolFromSmiles(BUTANEDIOL), base_seed=0)
    for base_seed in range(1, 4):
        again, _ = generate_tautomer_candidates(Chem.MolFromSmiles(BUTANEDIOL), base_seed=base_seed)
        assert {c.fingerprint for c in again} == {c.fingerprint for c in reference}


# --- the cap counts UNIQUE jobs, and truncation is incomplete -----------------


def test_the_cap_counts_unique_jobs_not_raw_rdkit_output():
    from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers, StereoEnumerationOptions

    mol = Chem.MolFromSmiles(TRIOL)
    raw = len(list(EnumerateStereoisomers(mol, options=StereoEnumerationOptions(onlyUnassigned=True, unique=True))))
    unique = len(_enumerate_stereo_classes(mol, cap=64).classes)
    assert raw > unique  # enantiomer pairs fold, so a raw cutoff would over-truncate

    at_cap = _enumerate_stereo_classes(mol, cap=unique)
    assert not at_cap.truncated and at_cap.total == unique and at_cap.total_known

    under_cap = _enumerate_stereo_classes(mol, cap=unique - 1)
    assert under_cap.truncated and under_cap.total is None and not under_cap.total_known
    assert len(under_cap.classes) == 1  # the single fallback configuration


def test_a_truncated_tautomer_falls_back_to_one_deterministic_configuration():
    mol = Chem.MolFromSmiles(BUTANEDIOL)
    first, _ = generate_tautomer_candidates(mol, stereo_cap=1)
    second, _ = generate_tautomer_candidates(mol, stereo_cap=1)

    assert len(first) == 1
    only = first[0]
    assert only.stereo.truncated and only.stereo.fallback
    assert only.stereo.fallback_reason == "enumeration_cap_exceeded"
    assert only.stereo.isomers_total is None and not only.stereo.isomers_total_known
    assert only.fingerprint == second[0].fingerprint


def test_a_truncated_tautomer_is_incomplete_even_though_its_job_succeeded():
    """The fallback is a SUCCESSFUL optimization of an INCOMPLETE stereo search:
    candidate status and tautomer state coexist, and no population follows."""
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles(BUTANEDIOL), stereo_cap=1)
    outcome = build_outcome([_succeeded(c, -100.0) for c in candidates])

    key = candidates[0].tautomer_fingerprint
    assert outcome.tautomer_states[key] is TautomerState.INCOMPLETE
    assert outcome.succeeded_count == 1
    assert not outcome.complete and outcome.populations is None
    assert outcome.energy_reference == "lowest_successful_calculated"
    assert "truncated" in outcome.energy_label and "lowest successful stereoisomer" in outcome.energy_label
    assert "lowest-energy stereoisomer" not in outcome.energy_label

    result = build_structure_set_result(outcome, "m", "HF STO-3G", run_id="r")
    entry = result.entries[0]
    assert entry.metadata["stereo_fallback"] is True
    assert entry.metadata["tautomer_state"] == "incomplete"
    assert "fallback" in entry.label
    assert result.provenance.parameters["stereo_enumeration_truncated"] == 1
    assert result.provenance.parameters["complete"] is False


# --- a tautomer is its lowest SUCCESSFUL stereoisomer -------------------------


def _two_job_tautomer():
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles(BUTANEDIOL))
    assert len(candidates) == 2
    return candidates


def test_the_lower_energy_stereoisomer_represents_its_tautomer():
    low, high = _two_job_tautomer()
    outcome = build_outcome([_succeeded(low, -100.0010), _succeeded(high, -100.0000)])

    key = low.tautomer_fingerprint
    assert outcome.representatives[key] == low.fingerprint
    assert outcome.tautomer_states[key] is TautomerState.COMPLETE and outcome.complete
    assert outcome.energy_reference == "global_minimum"
    assert outcome.energy_label == "ΔE (kcal/mol), lowest-energy stereoisomer of each tautomer"
    assert outcome.relative_energy_kcal_mol[low.fingerprint] == 0.0


def test_the_representative_does_not_depend_on_enumeration_order():
    a, b = _two_job_tautomer()
    forward = build_outcome([_succeeded(a, -100.0000), _succeeded(b, -99.9990)])
    backward = build_outcome([_succeeded(b, -99.9990), _succeeded(a, -100.0000)])

    key = a.tautomer_fingerprint
    assert forward.representatives[key] == backward.representatives[key] == a.fingerprint
    assert forward.relative_energy_kcal_mol == backward.relative_energy_kcal_mol


def test_equal_energy_stereoisomers_are_both_kept_but_carry_one_statistical_state():
    """Unit degeneracy, asserted: a second stereoisomer of the same tautomer
    adds no weight, however equal its energy."""
    a, b = _two_job_tautomer()
    outcome = build_outcome([_succeeded(a, -100.0), _succeeded(b, -100.0)])

    assert outcome.complete
    assert set(outcome.populations) == {outcome.representatives[a.tautomer_fingerprint]}
    assert outcome.populations[outcome.representatives[a.tautomer_fingerprint]] == pytest.approx(1.0)
    result = build_structure_set_result(outcome, "m", "HF STO-3G", run_id="r")
    assert len(result.entries) == 2  # both retained for audit and display


def test_populations_are_over_tautomers_not_over_stereo_jobs():
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles(DIMETHYLCYCLOHEXANONE))
    groups = _by_tautomer(candidates)
    results = []
    for index, members in enumerate(groups.values()):
        results += [_succeeded(m, -100.0 - 0.001 * index - 0.0001 * j) for j, m in enumerate(members)]
    outcome = build_outcome(results)

    assert outcome.complete
    assert len(outcome.populations) == len(groups) == outcome.tautomer_count
    assert sum(outcome.populations.values()) == pytest.approx(1.0)


def test_a_failed_stereoisomer_makes_its_tautomer_and_the_set_incomplete():
    """The surviving job is the lowest SUCCESSFUL one, not known to be the lowest."""
    low, high = _two_job_tautomer()
    outcome = build_outcome([_succeeded(low, -100.0), _failed(high)])

    assert outcome.tautomer_states[low.tautomer_fingerprint] is TautomerState.INCOMPLETE
    assert not outcome.complete and outcome.populations is None
    assert "lowest successful stereoisomer" in outcome.energy_label
    assert "lowest-energy stereoisomer" not in outcome.energy_label
    result = build_structure_set_result(outcome, "m", "HF STO-3G", run_id="r")
    lowest = [e for e in result.entries if e.metadata["is_lowest_calculated_for_tautomer"]]
    assert len(lowest) == 1 and lowest[0].metadata["tautomer_state"] == "incomplete"


def test_a_tautomer_with_no_usable_job_is_failed():
    low, high = _two_job_tautomer()
    outcome = build_outcome([_failed(low), _failed(high)])

    assert outcome.tautomer_states[low.tautomer_fingerprint] is TautomerState.FAILED
    assert not outcome.complete and outcome.succeeded_count == 0


def test_a_dropped_embedding_makes_the_tautomer_incomplete(monkeypatch):
    import openchem.chem.tautomer_distribution as module

    real = module._embed_candidate
    monkeypatch.setattr(
        module, "_embed_candidate", lambda mol, base_seed, index: (None, base_seed + index) if index % 9 == 1 else real(mol, base_seed, index)
    )
    candidates, failures = generate_tautomer_candidates(Chem.MolFromSmiles(BUTANEDIOL))

    assert failures == 1 and len(candidates) == 1
    assert candidates[0].stereo.embedding_failed == 1
    outcome = build_outcome([_succeeded(candidates[0], -100.0)])
    assert outcome.tautomer_states[candidates[0].tautomer_fingerprint] is TautomerState.INCOMPLETE
    assert not outcome.complete


def test_the_wedged_drawing_appears_only_where_it_tells_jobs_apart():
    two = _result_labels(BUTANEDIOL)
    one = _result_labels("CC(O)CO")

    assert all("@" in label and " of 2]" in label for label in two), two
    assert all("@" not in label for label in one), one


# --- the model identity is built from structured policy, never from prose ----


@pytest.mark.parametrize(
    ("field_name", "other"),
    [
        ("stereo_cap", 9),
        ("enantiomer_policy", "keep_both"),
        ("bond_stereo_policy", "ignore"),
        ("tautomer_representative", "first_stereo"),
        ("state_degeneracy", "counted"),
        ("incomplete_population_policy", "renormalize"),
    ],
)
def test_changing_any_policy_field_is_a_different_model(field_name, other):
    from dataclasses import replace

    changed = replace(MODEL_POLICY, **{field_name: other})

    assert model_version("HF STO-3G", "ETKDGv3", 298.15, changed) != model_version(
        "HF STO-3G", "ETKDGv3", 298.15
    )


def test_rewording_the_assumption_prose_does_not_change_the_model(monkeypatch):
    import openchem.chem.tautomer_distribution as module

    before = model_version("HF STO-3G", "ETKDGv3", 298.15)
    monkeypatch.setattr(module, "model_assumptions", lambda policy=MODEL_POLICY: ("reworded",))

    assert model_version("HF STO-3G", "ETKDGv3", 298.15) == before


def test_the_policy_serializes_in_one_fixed_order_and_is_immutable():
    assert MODEL_POLICY.canonical().split(";")[0] == "stereo_cap=8"
    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError
        MODEL_POLICY.stereo_cap = 99
    assert model_version("a", "b", 1.0).startswith(f"tautomer-boltzmann-v{TAUTOMER_MODEL_REVISION}|")
    assert TAUTOMER_MODEL_REVISION == 4


def test_the_assumptions_state_unit_degeneracy_and_the_lowest_representative_rule():
    text = " ".join(model_assumptions())

    assert "unit degeneracy" in text
    assert "lowest successful stereoisomer" in text
    assert "no separate statistical weight" in text


def test_the_result_carries_the_policy_the_reference_and_the_search_facts():
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles(BUTANEDIOL))
    outcome = build_outcome([_succeeded(c, -100.0 - 0.001 * i) for i, c in enumerate(candidates)])
    params = build_structure_set_result(
        outcome, "m", "HF STO-3G", run_id="r", policy=MODEL_POLICY_SINGLE
    ).provenance.parameters

    assert params["model_revision"] == 4
    assert params["model_policy"]["conformer_search"] == "single"
    assert params["model_policy"]["stereo_cap"] == 8
    assert params["energy_reference"] == "global_minimum"
    assert params["stereo_enumeration_cap"] == 8 and params["stereo_enumeration_truncated"] == 0
    assert params["stereo_search"] is True
    assert params["tautomer_count"] == 1 and params["candidate_count_expected"] == 2
    assert params["model_version"].startswith("tautomer-boltzmann-v4|")


# --- the result as a table (the survey's item 7) ------------------------------------


def _table_for(outcome, branch=VALIDATION_UNVALIDATED):
    from openchem.chem.tautomer_distribution import tautomer_distribution_table

    result = build_structure_set_result(outcome, "mol-1", "HF def2-SVP", run_id="run-9", validation_branch=branch)
    headers, rows = tautomer_distribution_table(result)
    return result, headers, [dict(zip(headers, row, strict=True)) for row in rows]


def test_the_table_has_one_row_per_candidate_and_the_documented_columns():
    from openchem.chem.tautomer_distribution import TABLE_COLUMNS

    result, headers, rows = _table_for(_complete_outcome())
    assert tuple(headers) == TABLE_COLUMNS and len(rows) == len(result.entries) == 2


def test_energies_are_written_at_full_precision_not_as_displayed():
    _result, _headers, rows = _table_for(_complete_outcome())
    by_absolute = {float(r["Absolute energy (Hartree)"]): r for r in rows}
    assert set(by_absolute) == {-100.0, -99.0}
    lowest = by_absolute[-100.0]
    assert float(lowest["Relative energy (kcal/mol)"]) == 0.0
    assert float(by_absolute[-99.0]["Relative energy (kcal/mol)"]) == pytest.approx(HARTREE_TO_KCAL_PER_MOL)


def test_the_population_column_is_blank_unless_the_model_is_validated():
    """No file may carry a percentage the screen was not allowed to show: the
    withheld `population_unvalidated` is never exported."""
    for branch in (VALIDATION_UNVALIDATED, "ranking_only"):
        _result, _headers, rows = _table_for(_complete_outcome(), branch)
        assert all(r["Population estimate"] == "" for r in rows)
    _result, _headers, rows = _table_for(_complete_outcome(), "validated")
    assert all(0.0 <= float(r["Population estimate"]) <= 1.0 for r in rows)
    assert all(r["Population estimate"] != "" for r in rows)  # present, even where it underflows to 0.0
    assert sum(float(r["Population estimate"]) for r in rows) == pytest.approx(1.0)


def test_every_row_names_what_qualifies_its_energy():
    _result, _headers, rows = _table_for(_complete_outcome())
    assert {r["Energy reference"] for r in rows} == {"global_minimum"}
    assert {r["Validation branch"] for r in rows} == {VALIDATION_UNVALIDATED}
    assert all(r["Model version"].startswith("tautomer-boltzmann-v") for r in rows)


def test_a_failed_candidate_is_kept_with_its_reason_and_no_energy():
    outcome = build_outcome(
        [
            CandidateResult("a", _molblock("CCO"), CandidateStatus.SUCCEEDED, absolute_energy_hartree=-100.0),
            CandidateResult(
                "b", _molblock("CC=O"), CandidateStatus.FAILED,
                failure_reason="did not converge", failure_reason_code="optimization_not_converged",
            ),
        ]
    )
    _result, _headers, rows = _table_for(outcome)
    failed = next(r for r in rows if r["Status"] == "failed")
    assert failed["Failure"] == "optimization_not_converged"
    assert failed["Absolute energy (Hartree)"] == "" and failed["Relative energy (kcal/mol)"] == ""
    assert {r["Energy reference"] for r in rows} == {"lowest_successful_calculated"}


def test_the_candidate_identity_is_exported_so_a_row_can_be_traced():
    _result, _headers, rows = _table_for(_complete_outcome())
    assert {r["Candidate fingerprint"] for r in rows} == {"a", "b"}
