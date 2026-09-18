"""The plan search's budget, and the starvation it used to allow.

**A TRUNCATED SEARCH IS NOT A DECISION.** The engine enumerates candidate
naming plans and then ranks them, so a plan that is never generated cannot
lose on the merits -- it simply is not there, and the output is whatever the
survivors happened to include. That failure is invisible from the name: the
answer looks like a considered choice.

Measured 2026-09-17 over the 227 benchmark molecules: a single plan counter
capped at 20 was REACHED by 67 of the 189 that produce a top-level trace, and
in the worst cases all 20 slots went to ONE parent's numbering variants.
`phenyltrimethylsilane` was named `(trimethylsilan-yl)benzene` for that
reason alone -- the silicon parent scores 5000 against benzene's 561 and
would have won instantly, but no silicon plan was ever proposed. D-032 in
`test_namer_known_defects.py` pins the four names; this file pins the
*mechanism*, because the names could come back right for the wrong reason.

What is asserted here is the contract, not the constants. `_PlanBudget` may
be retuned; what must not change is that one parent hypothesis cannot consume
the budget a different hypothesis needs.

These tests build real `SubstitutivePlan` objects rather than stand-ins. The
first draft used a fake class and every fake landed in ONE bucket, because
the key reads a candidate only for a plan type that HAS one -- which is a
fact about the engine worth stating rather than a wrinkle to work around.
Only `SubstitutivePlan` carries a `named_parent`; `FunctionalClassPlan`,
`MultiplicativePlan`, `RingAssemblyPlan` and the rest have no parent
candidate at all, so they are keyed by class and share one bucket per class.
That is coarser than the substitutive case on purpose: the tier ordering in
`_generate_all_plans` already runs those handlers first so a substitutive
plan space cannot starve them, and the measured maximum total is 138 plans
against a 512 bound, so the coarse bucket has never bound anything.
"""

from __future__ import annotations

import pytest

from openchem.vendor.iupac_namer.engine import (
    _PLANS_PER_HYPOTHESIS,
    _TOTAL_PLAN_BUDGET,
    _PlanBudget,
    _parent_hypothesis_key,
)
from openchem.vendor.iupac_namer.types import (
    CandidateParent,
    NamedParent,
    SubstitutivePlan,
)


def _plan(
    *,
    atoms=(0, 1, 2, 3, 4, 5),
    kind="monocyclic",
    element=None,
    pcg=None,
    method="systematic",
) -> SubstitutivePlan:
    """A plan carrying only the fields the hypothesis key reads."""
    candidate = CandidateParent(
        atom_indices=frozenset(atoms),
        type=kind,
        length=len(atoms),
        ring_system=None,
        unsaturation=None,
        element=element,
        lambda_value=None,
    )
    parent = NamedParent(
        candidate=candidate,
        name="(test)",
        stem="(test)",
        alkyl_stem=None,
        naming_method=method,
        indicated_hydrogen=None,
        numbering_options=(),
    )
    return SubstitutivePlan(
        interpretation=None,
        stereo_descriptors=None,
        named_parent=parent,
        numbering=None,
        pcg_type=pcg,
        pcg_instances=(),
        suffix_groups=(),
        unsaturation=(),
        prefix_assignments=(),
        indicated_hydrogen=None,
    )


# --- what counts as the same hypothesis ----------------------------------


def test_two_numberings_of_one_parent_are_one_hypothesis():
    """The whole point. Numbering variants share a parent, so they share a
    budget -- otherwise there is nothing to divide."""
    assert _parent_hypothesis_key(_plan()) == _parent_hypothesis_key(_plan())


def test_a_different_parent_is_a_different_hypothesis():
    benzene = _plan(atoms=(0, 1, 2, 3, 4, 5))
    silicon = _plan(kind="heteroatom_center", atoms=(6,), element="Si")

    assert _parent_hypothesis_key(benzene) != _parent_hypothesis_key(silicon)


def test_the_same_atoms_named_a_different_way_are_a_different_hypothesis():
    """A retained-name reading and a systematic one over the same ring are two
    hypotheses, and must not starve each other."""
    assert _parent_hypothesis_key(_plan(method="systematic")) != _parent_hypothesis_key(
        _plan(method="retained")
    )


def test_the_same_parent_with_a_different_suffix_group_is_a_different_hypothesis():
    """warfarin's ring is offered with a phenol suffix and (once the PCG work
    lands) with a ring ketone. Those are different naming decisions over the
    same atoms, they compete on the merits, so they get separate budgets."""
    assert _parent_hypothesis_key(_plan(pcg="phenol")) != _parent_hypothesis_key(
        _plan(pcg="ketone")
    )


def test_the_key_is_not_object_identity():
    """Two separately built plans for the same hypothesis must share a bucket.
    Keying on identity would give every plan its own budget and re-open the
    defect while looking like a fix."""
    first, second = _plan(), _plan()

    assert first is not second
    assert _parent_hypothesis_key(first) == _parent_hypothesis_key(second)


def test_the_key_is_hashable_because_the_budget_is_a_dict():
    assert isinstance(hash(_parent_hypothesis_key(_plan())), int)


# --- the budget itself ----------------------------------------------------


def test_one_hypothesis_cannot_spend_more_than_its_share():
    budget = _PlanBudget(_TOTAL_PLAN_BUDGET)
    admitted = sum(
        1 for _ in range(_PLANS_PER_HYPOTHESIS * 3) if budget.admits(_plan())
    )

    assert admitted == _PLANS_PER_HYPOTHESIS


def test_a_second_hypothesis_is_still_admitted_after_the_first_is_exhausted():
    """THE DEFECT, AS A TEST. Benzene arriving first must not mean silicon
    never arrives at all."""
    budget = _PlanBudget(_TOTAL_PLAN_BUDGET)
    for _ in range(_PLANS_PER_HYPOTHESIS * 2):
        budget.admits(_plan())  # benzene, well over its quota

    silicon = _plan(kind="heteroatom_center", atoms=(6,), element="Si")

    assert budget.admits(silicon), "the senior parent was starved"
    assert not budget.exhausted


def test_the_work_bound_still_holds_across_many_hypotheses():
    """The anti-starvation bound must not become a way around the work bound:
    a molecule with hundreds of hypotheses is still bounded."""
    budget = _PlanBudget(_TOTAL_PLAN_BUDGET)
    admitted = 0
    for i in range(_TOTAL_PLAN_BUDGET * 2):
        if budget.exhausted:
            break
        if budget.admits(_plan(atoms=(i,))):
            admitted += 1

    assert admitted <= _TOTAL_PLAN_BUDGET
    assert budget.exhausted


def test_the_budget_is_wide_enough_for_the_widest_molecule_measured():
    """Sized from measurement, not taste. With the cap lifted, the most plans
    any of the 227 benchmark molecules produces for a SINGLE hypothesis is 96
    (benzene-1,3,5-tricarbonylium) and the most in total is 138. A bound below
    those would silently truncate a real molecule, which is the same defect
    wearing a smaller number."""
    assert _PLANS_PER_HYPOTHESIS > 96
    assert _TOTAL_PLAN_BUDGET > 138


# --- the adversarial case -------------------------------------------------


def test_more_hypotheses_than_one_quota_all_get_a_turn():
    """The expectation comes from the budget contract, not from what the
    engine happens to do -- "an obviously senior parent is not starved" would
    otherwise just restate the engine's behaviour back at itself.

    More distinct hypotheses than one quota's worth of plans, fed in order:
    every one must be represented. A policy that spent the budget depth-first
    would drop the tail entirely, which is precisely the old behaviour.
    """
    hypotheses = [_plan(atoms=(i,)) for i in range(_PLANS_PER_HYPOTHESIS + 5)]
    budget = _PlanBudget(_TOTAL_PLAN_BUDGET)

    admitted: set[tuple] = set()
    for plan in hypotheses:
        if budget.exhausted:
            break
        if budget.admits(plan):
            admitted.add(_parent_hypothesis_key(plan))

    assert len(admitted) == len(hypotheses), (
        f"{len(hypotheses) - len(admitted)} hypotheses never got a slot"
    )


def test_a_depth_first_spender_would_fail_the_test_above():
    """Breaking the guard, so it is not passing for free.

    A budget that ignored the hypothesis key -- one shared counter, which is
    what the engine had -- lets the first hypothesis take everything. If the
    assertion above can pass under that policy then it is not testing
    anything.
    """
    class _SharedCounterBudget:
        def __init__(self, total: int) -> None:
            self.total_budget = total
            self.total = 0

        def admits(self, _plan) -> bool:
            self.total += 1
            return True

        @property
        def exhausted(self) -> bool:
            return self.total >= self.total_budget

    hypotheses = [_plan(atoms=(i,)) for i in range(_PLANS_PER_HYPOTHESIS + 5)]
    # A budget as small as one quota is what the old code effectively had for
    # a single-hypothesis molecule; the point is that nothing divides it.
    budget = _SharedCounterBudget(_PLANS_PER_HYPOTHESIS)

    admitted: set[tuple] = set()
    for plan in hypotheses:
        if budget.exhausted:
            break
        if budget.admits(plan):
            admitted.add(_parent_hypothesis_key(plan))

    assert len(admitted) < len(hypotheses), (
        "the shared-counter policy admitted every hypothesis, so the test "
        "above cannot distinguish the two policies"
    )


@pytest.mark.parametrize(
    "smiles,expected",
    [
        ("C[Si](C)(C)c1ccccc1", "heteroatom_center"),
        ("c1ccccc1P(c1ccccc1)c1ccccc1", "heteroatom_center"),
    ],
)
def test_the_senior_parent_now_reaches_the_ranked_set(smiles, expected):
    """End to end, and asserted on the CANDIDATE SET rather than the name.

    D-032 pins the names. This asserts the thing that was actually broken:
    that a plan with the senior parent is generated at all. A future change
    could get the name right by another route and leave the search just as
    starved.
    """
    from openchem.vendor.iupac_namer import engine as eng
    from openchem.vendor.iupac_namer import name_smiles
    from openchem.vendor.iupac_namer.types import OutputForm

    original = eng._search_plans
    seen: list[str] = []

    def spy(perception, mol, output_form, free_valence, query, strategy, session):
        ranked = original(
            perception, mol, output_form, free_valence, query, strategy, session
        )
        if output_form == OutputForm.STANDALONE and not seen:
            seen.extend(
                getattr(plan.named_parent.candidate, "type", "?")
                for _score, _seq, plan in ranked
                if hasattr(plan, "named_parent")
            )
        return ranked

    eng._search_plans = spy
    try:
        name_smiles(smiles)
    finally:
        eng._search_plans = original

    assert expected in seen, (
        f"no {expected} parent was proposed at all; "
        f"the ranked set was {sorted(set(seen))}"
    )
