"""The exo-skeleton parent candidate (naming round 8, W1), unit-tested on the finder and its engine wrapper.

P-65.1.2.2.1 (pdf p. 579): an unbranched chain linked to MORE THAN TWO carboxy groups names all of them 'carboxylic
acid'. Until round 8 the skeleton chain that excludes every acid carbon was never a candidate. The D-rows (D-100a..l)
pin the NAMES; these pin the candidate's own contract, which several mutations of it leave the names unchanged for:
a threshold moved from three groups to two only adds a candidate that then loses the comparison.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer.engine import _has_distinct_nonterminal_form, _with_exo_skeleton_candidates
from openchem.vendor.iupac_namer.perception import Perception

CITRIC = "OC(=O)CC(O)(CC(O)=O)C(O)=O"


def _finder(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    return mol, Perception(mol).chains


def _acid_carbons(mol) -> tuple[int, ...]:
    """The carboxyl carbons: a carbon with a double-bonded O and a single-bonded O."""
    return tuple(
        a.GetIdx() for a in mol.GetAtoms()
        if a.GetSymbol() == "C"
        and sum(1 for n in a.GetNeighbors() if n.GetSymbol() == "O" and mol.GetBondBetweenAtoms(a.GetIdx(), n.GetIdx()).GetBondTypeAsDouble() == 2.0) == 1
        and sum(1 for n in a.GetNeighbors() if n.GetSymbol() == "O" and mol.GetBondBetweenAtoms(a.GetIdx(), n.GetIdx()).GetBondTypeAsDouble() == 1.0) == 1
    )


def test_citric_acid_gets_the_propane_skeleton_that_excludes_all_three_acid_carbons():
    mol, chains = _finder(CITRIC)
    anchors = _acid_carbons(mol)
    assert len(anchors) == 3
    (candidate,) = chains.find_exo_skeleton_chains(anchors)
    assert candidate.length == 3 and candidate.type == "chain"
    assert not (candidate.atom_indices & set(anchors)), "the skeleton EXCLUDES every anchor: that is what makes them exo"


def test_two_groups_never_reach_the_rule():
    """P-65.1.2.1: two terminal groups are a dioic chain. The finder refuses fewer than three anchors, so a threshold
    dropped from here is caught, not merely harmless."""
    mol, chains = _finder("OC(=O)CCC(O)=O")
    assert chains.find_exo_skeleton_chains(_acid_carbons(mol)) == []
    mol, chains = _finder(CITRIC)
    assert chains.find_exo_skeleton_chains(_acid_carbons(mol)[:2]) == []


def test_an_anchor_that_is_not_an_exo_group_gives_no_candidate():
    """An anchor with TWO carbon neighbours is a chain-interior atom, not a group hanging off the chain."""
    mol, chains = _finder("CCCCC")
    assert chains.find_exo_skeleton_chains((1, 2, 3)) == []


def test_anchors_on_a_ring_or_on_different_arms_give_no_candidate():
    ring, chains = _finder("OC(=O)CCC(C(O)=O)c1ccc(cc1)C(O)=O")
    assert chains.find_exo_skeleton_chains(_acid_carbons(ring)) == [], "one acid hangs off a ring, not the chain"
    arms, chains = _finder("OC(=O)CCC(O)(CCC(O)=O)CCC(O)=O")
    assert chains.find_exo_skeleton_chains(_acid_carbons(arms)) == [], "no single path reaches all three arms"


def test_the_engine_offers_the_candidate_only_for_three_or_more_groups_with_a_distinct_nonterminal_form():
    mol, chains = _finder(CITRIC)
    perception = SimpleNamespace(chains=chains)
    anchors = _acid_carbons(mol)
    fg = lambda anchor, distinct=True: SimpleNamespace(  # noqa: E731
        anchor=anchor,
        suffix_forms_dict=lambda d=distinct: {"terminal": "oic acid", "nonterminal": "carboxylic acid" if d else "oic acid"},
    )
    existing = SimpleNamespace(atom_indices=frozenset({999}))
    base = [existing]
    three = _with_exo_skeleton_candidates(iter(base), perception, [fg(a) for a in anchors])
    assert three[0] is existing and len(three) == 2, "the finder's candidate is appended after the existing ones"
    assert _with_exo_skeleton_candidates(iter(base), perception, [fg(a) for a in anchors[:2]]) == base, "two groups"
    assert _with_exo_skeleton_candidates(iter(base), perception, [fg(a, distinct=False) for a in anchors]) == base, (
        "a suffix whose nonterminal form is the same word has no exo reading"
    )


def test_a_candidate_already_offered_is_not_offered_twice():
    mol, chains = _finder(CITRIC)
    perception = SimpleNamespace(chains=chains)
    anchors = _acid_carbons(mol)
    (candidate,) = chains.find_exo_skeleton_chains(anchors)
    fgs = [SimpleNamespace(anchor=a, suffix_forms_dict=lambda: {"terminal": "a", "nonterminal": "b"}) for a in anchors]
    assert _with_exo_skeleton_candidates([candidate], perception, fgs) == [candidate]


@pytest.mark.parametrize("terminal, nonterminal, expected", [
    ("oic acid", "carboxylic acid", True), ("nitrile", "carbonitrile", True), ("ol", "ol", False), ("al", None, False),
])
def test_a_distinct_nonterminal_form_is_what_makes_the_exo_carbon_part_of_the_suffix(terminal, nonterminal, expected):
    fg = SimpleNamespace(suffix_forms_dict=lambda: {"terminal": terminal, "nonterminal": nonterminal})
    assert _has_distinct_nonterminal_form(fg) is expected


def test_pcg_count_decides_where_it_disagrees_with_the_legacy_parent_selection_tier():
    """The plan's claim about the comparator, MEASURED. `parent_selection` is a declared LEGACY BLENDED TIER ranked BELOW
    `pcg_count` (preference.TIER_SPECS). For citric acid the exo-skeleton plan (three suffix groups) has the LOWER legacy
    score and the higher count, and it must win: the count decides first, and the legacy tier is never consulted. This is
    the case that separates 'the comparator is lexicographic' from 'a weighted score happens to agree'."""
    from openchem.vendor.iupac_namer import engine as eng
    from openchem.vendor.iupac_namer import name_smiles
    from openchem.vendor.iupac_namer.preference import TIER_SPECS
    from openchem.vendor.iupac_namer.strategy import IUPACCanonical
    from openchem.vendor.iupac_namer.types import OutputForm, SubstitutivePlan

    captured: list = []
    original = eng._search_plans

    def spy(perception, mol, output_form, free_valence, query, strategy, session):
        ranked = original(perception, mol, output_form, free_valence, query, strategy, session)
        if output_form == OutputForm.STANDALONE and not captured:
            captured.append((mol, ranked))
        return ranked

    eng._search_plans = spy
    try:
        assert name_smiles(CITRIC) == "2-hydroxypropane-1,2,3-tricarboxylic acid"
    finally:
        eng._search_plans = original
    mol, ranked = captured[0]
    strategy = IUPACCanonical()
    names = [t.name for t in TIER_SPECS]
    exo = dioic = None
    for _s, _q, plan in ranked:
        if not isinstance(plan, SubstitutivePlan) or plan.pcg_type != "carboxylic_acid":
            continue
        forms = sorted(sg.base_form for sg in plan.suffix_groups)
        if forms == ["carboxylic acid"] * 3:
            exo = plan
        elif forms == ["oic acid"] * 2 and plan.named_parent.candidate.length == 5:
            dioic = plan
    assert exo is not None and dioic is not None, "both readings must be among the ranked plans"
    key_exo, key_dioic = strategy.preference_key(exo, mol), strategy.preference_key(dioic, mol)
    i, j = names.index("pcg_count"), names.index("parent_selection")
    assert key_exo.tiers[i] > key_dioic.tiers[i], "three suffix groups against two"
    assert key_exo.tiers[j] < key_dioic.tiers[j], "and the LEGACY score prefers the other plan"
    assert key_exo.first_difference(key_dioic) == "pcg_count"
    assert key_exo > key_dioic
