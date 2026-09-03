"""Guards for `domain/affinity_range.py`.

Every test here names the mutation it exists to catch, because several of them
guard against a specific wrong version this design actually went through.
"""

from __future__ import annotations

import ast
import itertools
from pathlib import Path

import pytest

from openchem.domain import affinity_range as ar
from openchem.domain.affinity_range import (
    MIN_REPLICATES_FOR_SEPARATION,
    SEPARATION_ALPHA,
    AffinityRange,
    Ordering,
    compare,
    dominance_rank,
    minimum_replicates,
    ranges_separate,
    separated_below,
    separation_p_value,
)

MODULE = Path(ar.__file__)


def _spread(centre: float, n: int) -> AffinityRange:
    """`n` values in a tight cluster about `centre`, 0.01 apart."""
    return AffinityRange(tuple(centre + i * 0.01 for i in range(n)))


# --- the two-sided correction -------------------------------------------------


def test_three_replicates_cannot_separate_and_four_can():
    """MUTATION: `1 / comb(...)` (the one-sided rate) instead of `2 / comb(...)`.

    THIS IS THE TEST THAT PINS THE FACTOR-OF-TWO CORRECTION. The first draft of
    this module used the one-sided rate and concluded the minimum useful count
    was 3. It is not: the procedure reports a separation in EITHER direction
    without fixing one beforehand, which is two-sided, so n=3 sits at 0.10 and
    only n=4 reaches 0.05. Under the one-sided formula this test's first
    assertion flips.
    """
    assert separation_p_value(3, 3) == pytest.approx(0.10)
    assert separation_p_value(3, 3) > SEPARATION_ALPHA

    assert separation_p_value(4, 4) == pytest.approx(2 / 70)
    assert separation_p_value(4, 4) <= SEPARATION_ALPHA

    assert MIN_REPLICATES_FOR_SEPARATION == 4

    # ...and it is the COUNT that decides, not the numbers: three runs cannot
    # separate however far apart they are.
    assert compare(_spread(-9.0, 3), _spread(-1.0, 3)) is Ordering.NOT_ASSESSED
    assert compare(_spread(-9.0, 4), _spread(-1.0, 4)) is Ordering.SEPARATED


def test_two_replicates_can_never_support_an_ordering():
    """MUTATION: dropping the alpha gate and returning SEPARATED on disjointness.

    The gap here is 100 kcal/mol -- chemically absurd on purpose, so that a
    failure can only mean the COUNT was ignored, never that the numbers were
    too close.
    """
    assert separation_p_value(2, 2) == pytest.approx(2 / 6)
    assert separation_p_value(2, 2) > SEPARATION_ALPHA
    assert compare(_spread(-108.0, 2), _spread(-8.0, 2)) is Ordering.NOT_ASSESSED


def test_the_bound_is_the_exact_rank_sum_extreme():
    """MUTATION: any off-by-one in the binomial coefficient."""
    import math

    for n_a, n_b in itertools.product(range(1, 9), repeat=2):
        assert separation_p_value(n_a, n_b) == pytest.approx(
            2 / math.comb(n_a + n_b, n_a)
        )


def test_two_replicates_separate_from_eight_but_not_from_five():
    """MUTATION: replacing the computed gate with `min(n_a, n_b) >= 4`.

    Unequal counts are the ordinary case -- a failed replicate, a legacy
    result, a re-run at another setting -- and the general form behaves in a
    way no per-side minimum reproduces. A `min(n_a, n_b) >= 4` shortcut gets
    BOTH arms wrong: it refuses the 2-vs-8 case that is genuinely supportable
    and it would have refused 2-vs-5 for the wrong reason.
    """
    assert separation_p_value(2, 5) == pytest.approx(2 / 21)
    assert separation_p_value(2, 5) > SEPARATION_ALPHA

    assert separation_p_value(2, 8) == pytest.approx(2 / 45)
    assert separation_p_value(2, 8) <= SEPARATION_ALPHA

    assert compare(_spread(-9.0, 2), _spread(-8.0, 5)) is Ordering.NOT_ASSESSED
    assert compare(_spread(-9.0, 2), _spread(-8.0, 8)) is Ordering.SEPARATED


def test_the_minimum_replicate_count_is_derived_from_alpha_and_not_typed():
    """MUTATION: `return 4`.

    The number must fall out of the rule. A typed constant is free to drift
    from the function that justifies it the moment the procedure changes --
    which is exactly what happened to this module's first draft.
    """
    assert minimum_replicates(0.2) == 3
    assert minimum_replicates(0.05) == 4
    assert minimum_replicates(0.001) == 7
    assert MIN_REPLICATES_FOR_SEPARATION == minimum_replicates(SEPARATION_ALPHA)


# --- no fitted constant, behaviourally then lexically -------------------------


def test_the_decision_is_invariant_under_positive_scaling():
    """MUTATION: `if upper.low - lower.high > 0.06: separated` -- the exact
    fitted constant the roadmap forbids, a noise floor measured on one molecule
    on one receptor and presented as a property of the method.

    Scaling every affinity by 0.01 shrinks the gap to 0.005 while leaving the
    ordering untouched, so a mutant with any absolute kcal/mol margin says
    NOT_SEPARATED here. This is the BEHAVIOURAL half of the guard and catches
    such a constant introduced under any name.
    """
    low = (-9.00, -8.95, -8.90, -8.85)
    high = (-8.35, -8.30, -8.25, -8.20)

    for factor in (1.0, 10.0, 0.1, 0.01):
        a = AffinityRange(tuple(v * factor for v in low))
        b = AffinityRange(tuple(v * factor for v in high))
        assert compare(a, b) is Ordering.SEPARATED, f"failed at scale {factor}"


def test_the_decision_is_invariant_under_shifting_every_affinity():
    """MUTATION: any absolute threshold on the VALUES, e.g. `value < -8.0`."""
    low = (-9.00, -8.95, -8.90, -8.85)
    high = (-8.35, -8.30, -8.25, -8.20)

    for shift in (0.0, 1000.0, -1000.0):
        a = AffinityRange(tuple(v + shift for v in low))
        b = AffinityRange(tuple(v + shift for v in high))
        assert compare(a, b) is Ordering.SEPARATED, f"failed at shift {shift}"


def test_no_kcal_literal_lives_in_the_module():
    """MUTATION: inserting `_NOISE_FLOOR = 0.06`.

    The LEXICAL half of the no-fitted-constant guard. The only inputs to the
    gate are two replicate counts, so the module has no business holding a
    number in the units of the data. Allowed: 0, 1 and 2 (indices, the
    two-sided factor, the median divisor) and the declared alpha.
    """
    allowed = {0, 1, 2, SEPARATION_ALPHA}
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    offenders = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
        and node.value not in allowed
    ]
    assert not offenders, f"numeric literals that are not counts or alpha: {offenders}"


def test_the_range_is_never_dressed_up_as_an_accuracy():
    """MUTATION: adding a `mean`, `stdev` or `confidence_interval` member.

    A mean with a standard deviation invites a Gaussian reading of what is a
    minimum-of-minimums statistic, and any member named for an interval invites
    the confidence-interval reading the whole module exists to prevent. Guarded
    on the SYMBOLS rather than on the prose, because the docstring
    legitimately uses those words to disclaim them.
    """
    forbidden = ("mean", "stdev", "std_dev", "sd", "sem", "confidence_interval")
    for name in forbidden:
        assert not hasattr(AffinityRange(( -8.0, -7.0)), name), (
            f"AffinityRange.{name} would assert a distributional shape "
            "nothing here has established"
        )

    public = [name for name in vars(ar) if not name.startswith("_")]
    assert not [
        name for name in public if "interval" in name.lower()
    ], "no public symbol may be named for an interval; this computes a range"


# --- the geometry ------------------------------------------------------------


def test_separated_below_means_numerically_lower():
    """MUTATION: flipping the comparison.

    Plausible everywhere, because a MORE NEGATIVE Vina score is the BETTER one
    and "below" reads backwards.
    """
    better = _spread(-9.0, 4)
    worse = _spread(-8.0, 4)
    assert ranges_separate(better, worse)
    assert not ranges_separate(worse, better)
    assert separated_below(better, worse)
    assert not separated_below(worse, better)


def test_touching_ranges_are_not_separated():
    """MUTATION: `<` becomes `<=`."""
    a = AffinityRange((-9.0, -8.5))
    b = AffinityRange((-8.5, -8.0))
    assert a.high == b.low
    assert not ranges_separate(a, b)


def test_overlapping_ranges_are_not_separated_however_far_apart_the_medians_are():
    """MUTATION: comparing medians instead of ranges.

    One wide range and one narrow one can have very different medians and still
    overlap -- which is precisely the case where an ordering must be refused.
    """
    wide = AffinityRange((-12.0, -11.0, -10.0, -4.0))
    narrow = AffinityRange((-8.6, -8.5, -8.4, -8.3))
    assert wide.median < narrow.median
    assert not ranges_separate(wide, narrow)
    assert compare(wide, narrow) is Ordering.NOT_SEPARATED


def test_separation_is_transitive():
    """MUTATION: any argument-order or comparison slip that breaks the strict
    partial order.

    Tested as the mathematical PROPERTY over a generated grid rather than
    through one fixture, because the dominance ranking is only well defined if
    this holds universally.
    """
    bounds = [(lo, lo + w) for lo in (-10.0, -9.0, -8.5, -8.0) for w in (0.0, 0.5, 2.0)]
    ranges = [AffinityRange((lo, hi)) for lo, hi in bounds]

    for a, b, c in itertools.product(ranges, repeat=3):
        if ranges_separate(a, b) and ranges_separate(b, c):
            assert ranges_separate(a, c), "separated-below must be transitive"


# --- n/a is not 0 -------------------------------------------------------------


def test_a_single_run_has_no_width_rather_than_zero():
    """MUTATION: `width` returning `high - low` unconditionally.

    One run measured no spread at all. Reporting 0.0 there would say five runs
    agreed perfectly, which is a measurement nobody took.
    """
    assert AffinityRange((-8.79,)).width is None
    assert AffinityRange((-8.79,)).n == 1


def test_a_zero_width_range_is_a_measurement_and_not_an_absence():
    """MUTATION: `return width or None` -- the falsy-zero bug, `n/a is not 0`
    in reverse.

    Five runs that genuinely agree have a width of exactly zero, and that is a
    result. A deterministic provider produces exactly this, and its ranges must
    still be able to separate.
    """
    agreed = AffinityRange((-9.0, -9.0, -9.0, -9.0))
    assert agreed.width == 0.0
    assert agreed.width is not None
    assert agreed.n == 4

    other = AffinityRange((-8.0, -8.0, -8.0, -8.0))
    assert compare(agreed, other) is Ordering.SEPARATED


def test_an_empty_range_is_refused_rather_than_constructed():
    """MUTATION: allowing an empty `values`.

    An absent range is `None` at the call site. An empty AffinityRange would
    make "every replicate failed" indistinguishable from "not measured", and
    would leave `low`/`high` with nothing to answer.
    """
    with pytest.raises(ValueError):
        AffinityRange(())


# --- the representative -------------------------------------------------------


def test_the_representative_is_the_median_replicate():
    """MUTATION: taking the best, the first, or the mean.

    THE FIXTURE DISCRIMINATES ALL FOUR RULES AT ONCE, which an even-length list
    with tied middles would not:

        best  -10.0     first  -1.0     mean  -7.0     median  -8.0

    "Best" is the dangerous one: it is a max-over-N selection, so the headline
    number improves purely as the replicate count rises.
    """
    values = (-1.0, -10.0, -9.0, -8.0)
    r = AffinityRange(values)

    assert r.median == -8.0
    assert r.median != r.low            # not the best
    assert r.median != values[0]        # not the first
    assert r.median != sum(values) / len(values)  # not the mean


def test_the_median_does_not_improve_as_replicates_are_added():
    """MUTATION: representative = best.

    The centre must be a location statistic, not an extreme one. Adding runs
    from the same distribution leaves the median where it is while the minimum
    marches off -- which is the whole reason "best" is disqualified.
    """
    few = AffinityRange((-8.0, -8.5, -9.0))
    many = AffinityRange((-8.0, -8.5, -9.0, -8.1, -8.9, -9.6, -8.4, -8.6, -8.2))

    assert many.median == pytest.approx(few.median, abs=0.5)
    assert many.low < few.low  # the minimum, by contrast, keeps improving


# --- the dominance ranking ----------------------------------------------------


def test_overlapping_ligands_share_a_rank_and_a_transitively_separated_one_does_not():
    """MUTATION: grouping by overlap (adjacency or transitive closure) instead
    of counting dominators.

    THE COUNTEREXAMPLE THAT KILLED THE FIRST DESIGN. "Not separated" is not an
    equivalence relation: A overlaps B and B overlaps C, while A and C are
    disjoint. Closing over overlap renders 1, 1, 1 and destroys a real
    separation; counting dominators gives the correct 1, 1, 2.
    """
    a = AffinityRange((-9.0, -8.9, -8.6, -8.5))
    b = AffinityRange((-8.6, -8.2, -7.4, -7.0))
    c = AffinityRange((-7.2, -6.9, -6.4, -6.0))

    assert not ranges_separate(a, b)
    assert not ranges_separate(b, c)
    assert ranges_separate(a, c)

    assert dominance_rank([a, b, c]) == [1, 1, 2]


def test_a_screen_at_one_replicate_ranks_nothing():
    """MUTATION: falling back to a positional `1..N` rank.

    THE DEFAULT PATH. With one run each, no pair can be assessed whatever the
    numbers are, so every rank is 1 and the table stops numbering an ordering
    it cannot support. These three are far apart on purpose: a failure here
    means the count was ignored.
    """
    entries = [AffinityRange((-12.0,)), AffinityRange((-9.0,)), AffinityRange((-4.0,))]

    assert all(
        compare(x, y) is Ordering.NOT_ASSESSED
        for x, y in itertools.combinations(entries, 2)
    )
    assert dominance_rank(entries) == [1, 1, 1]


def test_a_fully_separated_field_ranks_one_to_n():
    """The control for the test above: when every pair really does separate at
    a supporting count, the ranking is the ordinary 1..N.

    Without this, "always return 1" would satisfy the single-replicate guard.
    """
    entries = [_spread(-12.0, 4), _spread(-9.0, 4), _spread(-4.0, 4)]
    assert dominance_rank(entries) == [1, 2, 3]
