"""The plan ranking is a declared, lexicographic key -- and it behaves like one.

Naming round 4 replaced the one blended float that ranked candidate plans
(`strategy.score_plan`, band constants from 0.0001 to 1,000,000) with
`preference.NomenclaturePreferenceKey`, a tuple of tiers declared in
`TIER_SPECS`. The float had two measured defects:

* its alphanumerical tie-break keyed every carbon substituent as "z", so
  `4-ethyl-1-methylbenzene` (D-038);
* its bands could overflow each other: a numbering difference of 0.08
  outweighed a P-44 parent-selection difference of 0.01, so a numbering
  criterion overrode a parent criterion (cid43000's reorder, stage 5b).

These tests pin the key's semantics directly, and the behaviours only a real
search shows. The per-molecule outcomes are rows D-038a..h in
`test_namer_known_defects.py`.
"""

from __future__ import annotations

import random

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.preference import (
    LegacyScoreKey,
    NomenclaturePreferenceKey,
    SearchBound,
    TIER_SPECS,
    locant_set_tier,
)
from openchem.vendor.iupac_namer.strategy import IUPACCanonical


def _key(**overrides) -> NomenclaturePreferenceKey:
    """A key with every tier neutral, and the named tiers overridden."""
    empty = locant_set_tier(())
    values = {
        "plan_kind": 0, "pcg_seniority": 0.0, "pcg_count": 0, "parent_selection": 0.0,
        "retained_ring": 0.0, "naming_method": 0.0, "substituent_count": 0,
        "heteroatom_locants": 0.0, "indicated_hydrogen_locants": empty,
        "suffix_locants": empty, "added_hydrogen_locants": empty,
        "unsaturation_locants": empty,
        "prefix_locants": empty, "primes": 0,
    }
    values.update(overrides)
    return NomenclaturePreferenceKey(tuple(values[spec.name] for spec in TIER_SPECS))


# --- the tier semantics ----------------------------------------------------


def test_every_tier_is_declared_with_a_paragraph_and_a_direction():
    for spec in TIER_SPECS:
        assert spec.paragraph, spec.name
        assert spec.better in ("higher", "lower"), spec.name


def test_a_locant_set_is_compared_at_the_first_point_of_difference():
    """P-14.3.5. The float compared SUMS, and {1,4} and {2,3} tie on a sum."""
    assert locant_set_tier((1, 4)) > locant_set_tier((2, 3))
    assert locant_set_tier((1, 2, 5)) > locant_set_tier((1, 3, 4))


@pytest.mark.parametrize("index", range(len(TIER_SPECS)))
def test_each_tier_decides_when_every_earlier_tier_ties(index):
    """Equal on tiers 1..N-1, different on tier N: tier N decides."""
    spec = TIER_SPECS[index]
    if spec.name.endswith("_locants") and spec.name != "heteroatom_locants":
        better, worse = locant_set_tier((1, 4)), locant_set_tier((2, 3))
    else:
        better, worse = 2, 1
    a, b = _key(**{spec.name: better}), _key(**{spec.name: worse})
    assert a > b
    assert a.first_difference(b) == spec.name


def test_a_rule_that_applies_still_loses_to_an_earlier_tier():
    """What makes the key lexicographic rather than a pile of local boosts.

    Plan B has far better locants on EVERY numbering tier, and loses by the
    smallest step on parent selection. In the float, a 0.08 numbering
    advantage beat a 0.01 parent difference; here it cannot.
    """
    a = _key(parent_selection=3.0502, prefix_locants=locant_set_tier((3, 4)))
    b = _key(parent_selection=3.0501, prefix_locants=locant_set_tier((1, 2)),
             suffix_locants=locant_set_tier((1,)))
    assert a > b
    assert a.first_difference(b) == "parent_selection"


def test_the_naming_method_is_chosen_before_any_numbering():
    """The method names the parent; numbering is chosen within it. The float's
    x0.01 method band lost to numbering for small rank gaps -- which is how
    cid19000's steroid came out as a von Baeyer tetracycle."""
    fused = _key(naming_method=5.0, suffix_locants=locant_set_tier((17,)))
    bridged = _key(naming_method=1.2, suffix_locants=locant_set_tier((6,)))
    assert fused > bridged


def test_indicated_hydrogen_is_ranked_before_the_suffix_and_a_missing_one_last():
    """P-14.4 (b), pdf p. 74: '2H-pyran-6-carboxylic acid (PIN)', so the
    hydrogen keeps 2 although the suffix could have had it. A parent name that
    leaves the hydrogen out is not the empty -- best -- set: it ranks below
    every name that states one ('9H-fluoren-9-one (PIN)'; round 5, N3)."""
    from openchem.vendor.iupac_namer.strategy import _indicated_hydrogen_tier

    two_h = _key(indicated_hydrogen_locants=_indicated_hydrogen_tier("2H-pyran"),
                 suffix_locants=locant_set_tier((6,)))
    six_h = _key(indicated_hydrogen_locants=_indicated_hydrogen_tier("6H-pyran"),
                 suffix_locants=locant_set_tier((2,)))
    assert two_h > six_h
    assert _indicated_hydrogen_tier("9H-fluorene") > _indicated_hydrogen_tier("fluorene")
    assert _indicated_hydrogen_tier("3aH-indene") < _indicated_hydrogen_tier("3H-indene")
    assert (_indicated_hydrogen_tier("4,5-dihydro-2H-pyran")
            == _indicated_hydrogen_tier("2H-pyran"))


def test_ordering_is_antisymmetric_and_transitive_over_a_sample():
    rng = random.Random(20260918)
    keys = [
        _key(parent_selection=rng.choice((1.0, 2.0)),
             naming_method=rng.choice((0.9, 1.2)),
             prefix_locants=locant_set_tier(sorted(rng.sample(range(1, 7), 2))))
        for _ in range(40)
    ]
    for a in keys:
        for b in keys:
            assert (a < b) + (a == b) + (a > b) == 1
            for c in keys:
                if a < b and b < c:
                    assert a < c


# --- no implicit ordering domains --------------------------------------------


@pytest.mark.parametrize("bad", [None, float("nan")])
def test_a_tier_may_not_be_none_or_nan(bad):
    with pytest.raises(TypeError):
        _key(parent_selection=bad)


def test_a_locant_tier_holds_numbers_only():
    with pytest.raises(TypeError):
        _key(prefix_locants=(0, "4a"))


def test_the_search_bound_is_not_a_key():
    """A threshold that could be ranked as though it were a plan is how the
    old `good_enough_score` float leaked into the ordering."""
    bound = SearchBound(legacy_threshold=1_000_000.0, plan_kind_at_least=5)
    with pytest.raises(TypeError):
        _ = _key() < bound
    assert bound.reached_by(_key(plan_kind=5))
    assert not bound.reached_by(_key(plan_kind=4))
    assert bound.reached_by(LegacyScoreKey(1_000_000.0))


def test_legacy_and_preference_keys_do_not_compare():
    with pytest.raises(TypeError):
        _ = LegacyScoreKey(1.0) < _key()


# --- the behaviour only a real search shows ---------------------------------


class _Legacy(IUPACCanonical):
    """The same strategy ranking by the old float, for the compatibility check."""

    def preference_key(self, plan):
        return LegacyScoreKey(self.score_plan(plan))

    def cache_key(self) -> str:
        return "iupac-legacy-key"


def test_a_strategy_on_the_legacy_key_keeps_the_legacy_answer():
    """The P-14.4 (g) tie-break applies to NomenclaturePreferenceKey ties only.
    A strategy that ranks by the float keeps its old behaviour exactly -- which
    is also the evidence that the new answer comes from the new comparator."""
    assert name_smiles("CCc1ccc(C)cc1", strategy=_Legacy()) == "4-ethyl-1-methylbenzene"
    assert name_smiles("CCc1ccc(C)cc1") == "1-ethyl-4-methylbenzene"


@pytest.mark.parametrize("smiles,expected", [
    ("CCc1ccc(C)cc1", "1-ethyl-4-methylbenzene"),
    ("CC1CCCC(CC)C1", "1-ethyl-3-methylcyclohexane"),
    ("COc1ccc(C)cc1", "1-methoxy-4-methylbenzene"),
])
def test_the_answer_does_not_depend_on_atom_order(smiles, expected):
    """The best detector of accidental dependence on RDKit indices: the same
    graph under several atom orders must get one name. A residual tie falls to
    generation order, which depends on atom order -- so this is what would
    catch the tie-break silently failing to decide."""
    mol = Chem.MolFromSmiles(smiles)
    rng = random.Random(7)
    for _ in range(6):
        order = list(range(mol.GetNumAtoms()))
        rng.shuffle(order)
        shuffled = Chem.MolToSmiles(Chem.RenumberAtoms(mol, order), canonical=False)
        assert name_smiles(shuffled) == expected, shuffled


def test_the_substituent_count_does_not_outrank_the_naming_method():
    """D-022w and D-022z. A Hantzsch-Widman plan writes a ring's oxo groups as
    prefixes where a retained stem encodes them, so it "has more substituents"
    on the SAME skeleton. Inside the parent_selection tier that count beat the
    naming method; as its own tier after the method, it cannot."""
    retained = _key(parent_selection=5.55, naming_method=100.0, substituent_count=0)
    hantzsch_widman = _key(parent_selection=5.55, naming_method=50.0, substituent_count=2)
    assert retained > hantzsch_widman
    assert retained.first_difference(hantzsch_widman) == "naming_method"
