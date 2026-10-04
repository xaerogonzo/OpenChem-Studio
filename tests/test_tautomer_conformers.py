"""The conformer pool and the model-revision-4 contract around it.

Each test here pins a decision that was measured or got wrong once: a seed of 0
returns N identical conformers, an OH rotamer is a distinct conformer, a conformer
that did not converge is never ranked, a selection is not a truncation, and a
conformer's identity is its recipe and never its rank.
"""

from __future__ import annotations

import dataclasses

import pytest
from rdkit import Chem

from openchem.chem import tautomer_conformers as tc
from openchem.chem.tautomer_conformers import (
    PREFILTER_MMFF,
    PREFILTER_UFF,
    SEARCH_FULL,
    SEARCH_TOPK,
    build_pool,
    recipe_fingerprint,
)
from openchem.chem.tautomer_distribution import (
    MODEL_POLICY,
    MODEL_POLICY_FULL,
    MODEL_POLICY_SINGLE,
    MODEL_POLICY_TOPK,
    CandidateResult,
    CandidateStatus,
    ModelPolicy,
    TautomerState,
    build_outcome,
    build_structure_set_result,
    generate_tautomer_candidates,
    model_assumptions,
    model_version,
    policy_for_mode,
    tautomer_distribution_table,
)

#: Z-enol of acetylacetone: its OH can point at the carbonyl (hydrogen bonded) or away.
ENOL = "CC(=O)/C=C(/C)O"


def _pool(smiles=ENOL, **overrides):
    kwargs = dict(
        stereo_fingerprint="stereo", seed=1, search=SEARCH_TOPK, embeds=50, topk=3, cap=10,
        rms_threshold=0.5, energy_window=1.0, max_iters=2000, embed_policy="policy",
    )
    kwargs.update(overrides)
    return build_pool(Chem.MolFromSmiles(smiles), **kwargs)


def _oh_to_carbonyl_o(mol) -> float:
    """Shortest O-H...O distance (A) from a hydroxyl hydrogen to another oxygen."""
    conf = mol.GetConformer()
    best = 99.0
    for atom in mol.GetAtoms():
        if atom.GetSymbol() == "H" and atom.GetNeighbors()[0].GetSymbol() == "O":
            donor = atom.GetNeighbors()[0].GetIdx()
            for other in mol.GetAtoms():
                if other.GetSymbol() == "O" and other.GetIdx() != donor:
                    best = min(best, (conf.GetAtomPosition(atom.GetIdx()) - conf.GetAtomPosition(other.GetIdx())).Length())
    return best


# --- the trap that made v3 wrong ---------------------------------------------------


def test_a_pool_seed_of_zero_is_refused_because_it_returns_identical_conformers():
    with pytest.raises(ValueError, match="at least 1"):
        _pool(seed=0)


def test_a_non_pool_search_is_refused():
    with pytest.raises(ValueError, match="not a pool search"):
        _pool(search="single")


def test_the_enol_pool_finds_both_oh_orientations_and_the_hydrogen_bonded_one_is_lowest():
    """THE v3 FAILURE: one embedded geometry kept the OH 4.76 A from the carbonyl.
    A pool must contain the hydrogen-bonded rotamer, and force-field scoring must
    put it first. Asserted on geometry, not on a count."""
    pool = _pool()

    assert pool.distinct == 2 and len(pool.selected) == 2
    lowest, other = pool.selected
    assert lowest.prefilter_energy < other.prefilter_energy
    assert _oh_to_carbonyl_o(lowest.mol) < 2.2 < 3.0 < _oh_to_carbonyl_o(other.mol)


def test_polar_hydrogens_make_an_oh_rotamer_a_distinct_conformer():
    """Ethanol's heavy atoms are a rigid three points: only the O-H orientation
    separates its two conformers, which is exactly what a heavy-atom comparison drops."""
    assert _pool("CCO").distinct == 2


def test_methyl_rotors_are_not_distinct_conformers():
    """Acetone has methyl groups and nothing else to rotate."""
    assert _pool("CC(C)=O").distinct == 1


# --- identity is the recipe, never the rank ----------------------------------------


def test_the_recipe_fingerprint_depends_on_every_input_and_nothing_else():
    base = recipe_fingerprint("stereo", 7, 3, "policy")

    assert base == recipe_fingerprint("stereo", 7, 3, "policy")
    assert len({base, recipe_fingerprint("other", 7, 3, "policy"), recipe_fingerprint("stereo", 8, 3, "policy"),
                recipe_fingerprint("stereo", 7, 4, "policy"), recipe_fingerprint("stereo", 7, 3, "different")}) == 5


def test_the_rdkit_release_is_part_of_a_conformers_identity(monkeypatch):
    before = recipe_fingerprint("s", 1, 0, "p")
    monkeypatch.setattr(tc, "RDKIT_VERSION", "1999.01.1")

    assert recipe_fingerprint("s", 1, 0, "p") != before


def test_a_selected_conformers_identity_does_not_change_with_how_many_are_selected():
    """Rank-based identity would move when the selection widened; a recipe cannot."""
    one = _pool("CCCCO", topk=1)
    three = _pool("CCCCO", topk=3)

    assert one.selected_recipes[0] == three.selected_recipes[0]
    assert set(three.selected_recipes) <= set(three.retained_recipes)


def test_the_pool_is_deterministic():
    assert _pool("CCCCO").selected_recipes == _pool("CCCCO").selected_recipes


def test_selected_conformers_are_ordered_lowest_energy_first_with_ties_by_recipe():
    pool = _pool("CCCCO", topk=5)
    keys = [(round(m.prefilter_energy, 3), m.recipe_fingerprint) for m in pool.selected]

    assert keys == sorted(keys)


def test_exactly_tied_energies_are_ordered_by_recipe_never_by_embedding_order(monkeypatch):
    """Two identical-energy conformers must come out in the same order on every run
    and every machine: the recipe fingerprint decides, not the order they embedded in."""
    real = tc._optimize

    def flat(mol, max_iters):
        used, energies = real(mol, max_iters)
        return used, {cid: -5.0 for cid in energies}

    monkeypatch.setattr(tc, "_optimize", flat)
    pool = _pool("CCCCO", topk=10)

    assert len(pool.selected) >= 3
    assert list(pool.selected_recipes) == sorted(pool.selected_recipes)


# --- selection is not truncation ---------------------------------------------------


def test_choosing_the_top_k_of_more_distinct_conformers_is_a_selection_not_a_truncation():
    pool = _pool("CCCCO", topk=2)

    assert pool.distinct > 2 and len(pool.selected) == 2
    assert pool.truncated is False


def test_the_full_mode_truncates_only_above_its_cap():
    wide = _pool("CCCCO", search=SEARCH_FULL, cap=100)
    narrow = _pool("CCCCO", search=SEARCH_FULL, cap=2)

    assert wide.truncated is False and len(wide.selected) == wide.distinct
    assert narrow.truncated is True and len(narrow.selected) == 2
    assert narrow.selected_recipes == wide.selected_recipes[:2], "the cap keeps the lowest, deterministically"


# --- the prefilter is a rule, and a failed one is never ranked -----------------------


def test_a_molecule_mmff_cannot_parameterise_is_scored_by_uff_and_says_so():
    pool = _pool("C[Se]CC")

    assert pool.prefilter == PREFILTER_UFF and pool.selected
    assert _pool("CCO").prefilter == PREFILTER_MMFF


def test_a_conformer_that_did_not_converge_is_never_ranked(monkeypatch):
    real = tc.AllChem.MMFFOptimizeMoleculeConfs

    def half_fail(mol, **kwargs):
        results = real(mol, **kwargs)
        return [(1, e) if i % 2 else (flag, e) for i, (flag, e) in enumerate(results)]

    monkeypatch.setattr(tc.AllChem, "MMFFOptimizeMoleculeConfs", half_fail)
    pool = _pool("CCCCO")

    assert pool.prefilter_failed > 0 and pool.prefilter_ok + pool.prefilter_failed == pool.produced
    assert pool.selected, "the converged half still gives a pool"


def test_a_non_finite_energy_is_never_ranked(monkeypatch):
    real = tc.AllChem.MMFFOptimizeMoleculeConfs
    monkeypatch.setattr(
        tc.AllChem, "MMFFOptimizeMoleculeConfs",
        lambda mol, **kw: [(flag, float("nan")) for flag, _e in real(mol, **kw)],
    )

    assert _pool("CCO").selected == ()


def test_zero_usable_conformers_is_an_empty_pool_the_caller_can_count():
    pool = _pool("CCO", embeds=0)

    assert pool.selected == () and pool.produced == 0


# --- the model identity ------------------------------------------------------------


def test_the_three_policies_are_different_models_and_the_default_is_top_k():
    versions = {model_version("M062X def2-TZVP", "ETKDGv3", 298.15, p) for p in (MODEL_POLICY_TOPK, MODEL_POLICY_FULL, MODEL_POLICY_SINGLE)}

    assert len(versions) == 3
    assert MODEL_POLICY is MODEL_POLICY_TOPK
    assert policy_for_mode(False) is MODEL_POLICY_TOPK and policy_for_mode(True) is MODEL_POLICY_FULL


@pytest.mark.parametrize("field", [f.name for f in dataclasses.fields(ModelPolicy)])
def test_changing_any_policy_field_changes_the_model_version(field):
    """One test per field: a model input that does not move the version could let a
    stale validation stamp keep authorising percentages under a different model."""
    original = getattr(MODEL_POLICY, field)
    changed = original + 1 if isinstance(original, int) else f"{original}-changed"
    other = dataclasses.replace(MODEL_POLICY, **{field: changed})

    assert model_version("m", "e", 298.15, other) != model_version("m", "e", 298.15, MODEL_POLICY)


def test_rewording_the_prose_changes_no_model_version(monkeypatch):
    before = model_version("m", "e", 298.15)
    monkeypatch.setattr("openchem.chem.tautomer_distribution.model_assumptions", lambda policy=MODEL_POLICY: ("reworded",))

    assert model_version("m", "e", 298.15) == before


def test_the_assumptions_name_the_conformer_search_and_say_it_is_not_exhaustive():
    topk = " ".join(model_assumptions(MODEL_POLICY_TOPK))
    full = " ".join(model_assumptions(MODEL_POLICY_FULL))
    single = " ".join(model_assumptions(MODEL_POLICY_SINGLE))

    assert "lowest 3" not in topk and "the 3 lowest" in topk and "not exhaustive" in topk
    assert "not exhaustive enumeration" in full and "up to 10" in full
    assert "no conformer search" in single


def test_the_effective_embedding_parameters_are_in_the_policy():
    assert "ETversion=" in MODEL_POLICY.conformer_embed_params
    assert MODEL_POLICY.conformer_engine.startswith("rdkit-")


# --- candidates, identity chain and the outcome --------------------------------------


def _candidates(policy=MODEL_POLICY_TOPK, smiles="CC(=O)CC(C)=O"):
    return generate_tautomer_candidates(Chem.MolFromSmiles(smiles), policy=policy)[0]


def test_the_stereo_class_identity_is_unchanged_and_each_conformer_is_a_job_under_it():
    """The identity chain: stereo fingerprint (what v3 called the candidate) ->
    conformer recipe -> job. Moving to a conformer search must not re-key stereo."""
    single = {c.fingerprint for c in _candidates(MODEL_POLICY_SINGLE)}
    searched = _candidates()

    assert {c.conformer.stereo_fingerprint for c in searched} == single
    assert len({c.fingerprint for c in searched}) == len(searched) > len(single)
    assert all(c.fingerprint not in single for c in searched)
    assert all(c.conformer.recipe_fingerprint for c in searched)


def test_a_conformer_candidate_carries_its_pool_facts():
    candidate = next(c for c in _candidates() if c.conformer.selected > 1)
    status = candidate.conformer

    assert status.search == SEARCH_TOPK and status.prefilter == PREFILTER_MMFF
    assert status.seed >= 1 and status.generated == 50 and status.distinct >= status.selected
    assert status.selected_recipes and status.recipe_fingerprint in status.selected_recipes
    assert status.recipe_fingerprint in status.retained_recipes


def _outcome_for(candidates, energies):
    return build_outcome(
        [
            CandidateResult.for_candidate(c, "", CandidateStatus.SUCCEEDED, absolute_energy_hartree=e)
            for c, e in zip(candidates, energies, strict=True)
        ]
    )


def test_a_tautomer_is_represented_by_its_lowest_conformer_whatever_the_order():
    candidates = [c for c in _candidates() if c.conformer.selected > 1][:2]
    outcome = _outcome_for(candidates, [-100.0, -100.001])
    reversed_outcome = _outcome_for(list(reversed(candidates)), [-100.001, -100.0])

    assert outcome.representatives == reversed_outcome.representatives
    assert set(outcome.representatives.values()) == {candidates[1].fingerprint}


def test_selecting_fewer_conformers_than_exist_is_complete_when_every_selected_one_succeeded():
    candidates = _candidates(smiles="CCCCO")
    assert candidates[0].conformer.distinct > candidates[0].conformer.selected

    outcome = _outcome_for(candidates, [-100.0 - 0.001 * i for i in range(len(candidates))])

    assert outcome.complete is True
    assert set(outcome.tautomer_states.values()) == {TautomerState.COMPLETE}
    assert outcome.populations is not None


def test_one_failed_conformer_makes_its_tautomer_and_the_set_incomplete():
    candidates = _candidates(smiles="CCCCO")
    results = [
        CandidateResult.for_candidate(
            c, "", CandidateStatus.FAILED if i == 0 else CandidateStatus.SUCCEEDED,
            absolute_energy_hartree=None if i == 0 else -100.0 - 0.001 * i,
            failure_reason_code="optimization_not_converged" if i == 0 else "",
        )
        for i, c in enumerate(candidates)
    ]
    outcome = build_outcome(results)

    assert outcome.complete is False and outcome.populations is None
    assert set(outcome.tautomer_states.values()) == {TautomerState.INCOMPLETE}


def test_a_truncated_full_mode_pool_makes_the_tautomer_incomplete_even_though_every_job_succeeded():
    policy = dataclasses.replace(MODEL_POLICY_FULL, conformer_cap=1)
    candidates = _candidates(policy=policy, smiles="CCCCO")
    assert all(c.conformer.truncated for c in candidates)

    outcome = _outcome_for(candidates, [-100.0 - 0.001 * i for i in range(len(candidates))])

    assert outcome.complete is False and outcome.populations is None
    assert outcome.truncated_conformer_class_count == 1
    assert "truncated" in outcome.energy_label and "not exhaustive" not in outcome.energy_label


def test_the_energy_label_never_claims_the_lowest_energy_conformer():
    candidates = _candidates(smiles="CCCCO")
    outcome = _outcome_for(candidates, [-100.0 - 0.001 * i for i in range(len(candidates))])

    assert "sampled" in outcome.energy_label and "not exhaustive" in outcome.energy_label
    assert "lowest-energy" not in outcome.energy_label


def test_the_result_records_the_search_the_pools_and_the_lowest_for_each_stereoisomer():
    candidates = _candidates(smiles="CCCCO")
    outcome = _outcome_for(candidates, [-100.0 - 0.001 * i for i in range(len(candidates))])
    result = build_structure_set_result(outcome, "m", "M062X def2-TZVP", run_id="r", policy=MODEL_POLICY_TOPK)
    params = result.provenance.parameters

    assert params["conformer_search"] == SEARCH_TOPK and params["model_revision"] == 5
    assert params["model_policy"]["conformer_topk"] == 3
    assert params["model_version"].startswith("tautomer-boltzmann-v5|")
    (pool,) = params["conformer_pools"]
    assert pool["selected"] == len(candidates) and pool["distinct"] >= pool["selected"] and pool["truncated"] is False
    assert pool["selected_recipes"] == [c.conformer.recipe_fingerprint for c in candidates]
    lowest = [e for e in result.entries if e.metadata["is_lowest_calculated_for_stereo"]]
    assert len(lowest) == 1 and lowest[0].energy == 0.0


def test_the_table_lists_every_conformer_and_still_blanks_the_population_unless_validated():
    candidates = _candidates(smiles="CCCCO")
    outcome = _outcome_for(candidates, [-100.0 - 0.001 * i for i in range(len(candidates))])
    result = build_structure_set_result(outcome, "m", "M062X def2-TZVP", run_id="r", policy=MODEL_POLICY_TOPK)
    headers, rows = tautomer_distribution_table(result)
    table = [dict(zip(headers, row, strict=True)) for row in rows]

    assert len(table) == len(candidates)
    assert [r["Conformer"] for r in table] == [str(i + 1) for i in range(len(candidates))] or sorted(
        r["Conformer"] for r in table
    ) == sorted(str(i + 1) for i in range(len(candidates)))
    assert {r["Conformers selected"] for r in table} == {str(len(candidates))}
    assert all(r["Conformer recipe fingerprint"] for r in table)
    assert all(r["Population estimate"] == "" for r in table)


def test_a_single_geometry_result_leaves_the_conformer_columns_blank():
    candidates = _candidates(MODEL_POLICY_SINGLE)
    outcome = _outcome_for(candidates, [-100.0 - 0.001 * i for i in range(len(candidates))])
    result = build_structure_set_result(outcome, "m", "HF STO-3G", run_id="r", policy=MODEL_POLICY_SINGLE)
    headers, rows = tautomer_distribution_table(result)

    assert {dict(zip(headers, r, strict=True))["Conformer"] for r in rows} == {""}
