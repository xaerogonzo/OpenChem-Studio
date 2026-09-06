"""Rank statistics for the docking benchmarks, in one place.

`spearman` was written and verified in `rescore_power.py` and is MOVED here
rather than copied, because the ranking benchmark needs the same function and
two implementations of one statistic is how two benchmarks come to disagree
about a number. Its verification docstring travels with it.

Everything else here exists for the Within-Assay Docking Ranking Benchmark and
is separated from the runner for the reason `ui/visual_check.py` gives: these
are pure functions over lists of floats, testable on CONSTRUCTED values, where
the runner needs real Vina and a network. A statistic that reaches for a
toolkit becomes a test about the machine.
"""

from __future__ import annotations

import math

#: The replicate groups the search-repeatability diagnostic compares.
#:
#: FIXED HERE, BEFORE ANY RUN, and that is the whole point. Choosing the split
#: after seeing results is choosing the answer. Six replicates rather than five
#: so the halves are EVEN -- five splits 2/3, and two aggregates over different
#: counts are not comparable, which is the trap `seed_spread.py` records for
#: widths at different n.
#:
#: Six also clears `domain/affinity_range.MIN_REPLICATES_FOR_SEPARATION`, which
#: is 4.
REPLICATE_HALVES = ((0, 1, 2), (3, 4, 5))


def spearman(a: list[float], b: list[float]) -> float | None:
    """Rank correlation, written out rather than imported: scipy is not a
    dependency of this project and adding one for a benchmark would be a
    dependency nobody reviewed.

    **VERIFIED BEFORE ITS NUMBERS WERE WRITTEN DOWN**, because a hand-rolled
    statistic with a tie-handling bug produces plausible figures and this
    one's output goes straight into a README:

        [1,2,3,4,5] vs [10,20,30,40,50]   +1.0
        [1,2,3,4,5] vs [50,40,30,20,10]   -1.0
        [1,2,3]     vs [7,7,7]            None -- zero variance, not 0.0
        [1,2,3,4,5] vs [2,1,4,3,5]        +0.8, by 1 - 6*sum(d^2)/(n(n^2-1))
                                          with d = [-1,+1,-1,+1,0]
        [1,2,3,4]   vs [1,2,2,4]          +0.948683..., midranks 1/2.5/2.5/4

    The fourth case is worth keeping for a reason that is about the CHECKER
    rather than the code: it was first written with an expected 0.6, pulled
    from memory, and the function was briefly suspected before the identity
    was worked through by hand. An expectation invented to test a function
    is not an oracle.

    Zero variance returns None rather than 0.0 -- "the ranks do not vary" is
    not "the ranks are uncorrelated", and a benchmark that averaged the
    second into a mean would be reporting a value it never measured.
    """
    n = len(a)
    if n < 2:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = shared
            i = j + 1
        return out

    ra, rb = ranks(a), ranks(b)
    mean_a, mean_b = sum(ra) / n, sum(rb) / n
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - mean_a) ** 2 for x in ra) * sum((y - mean_b) ** 2 for y in rb))
    return None if den == 0 else num / den


def distinct(values: list[float]) -> int:
    """How many DIFFERENT values a column holds.

    Printed beside every correlation, because a rho over eight ligands of
    which six are tied at one potency is driven by two points and six
    midranks -- and must not render as `n = 8`. This is the honest n, and
    the gap between it and `len(values)` is what a reader needs to see.
    """
    return len({round(v, 12) for v in values})


def random_floor_sd(n: int) -> float | None:
    """The standard deviation of Spearman's rho under a random ranking.

    DERIVED, NOT SIMULATED and not fitted: under the null of independent
    rankings E[rho] = 0 exactly and Var[rho] = 1/(n-1), so the SD is
    1/sqrt(n-1). A benchmark that reports a rho of +0.3 on five ligands
    should be read against an SD of 0.5, and printing the floor is what
    makes that automatic rather than something a reader has to know.

    None below n = 2, where a rank correlation is undefined anyway.
    """
    return None if n < 2 else 1.0 / math.sqrt(n - 1)


def pairs_reordered(a: list[float], b: list[float]) -> int:
    """How many of the n(n-1)/2 pairs the two orderings disagree about.

    Reported BESIDE the repeatability rho, because that number saturates
    easily and a saturated statistic reads as a strong result. A
    repeatability of +1.0 over five well-separated ligands means "noise did
    not reorder five ligands that were far apart", not "the search is
    noiseless" -- and the pair count says which, because it is an absolute
    count rather than a normalised one.

    Ties in EITHER list are not counted as disagreements: two ligands the
    search cannot separate have not been reordered, they have not been
    ordered at all.
    """
    n = len(a)
    total = 0
    for i in range(n):
        for j in range(i + 1, n):
            da, db = a[i] - a[j], b[i] - b[j]
            if da == 0 or db == 0:
                continue
            if (da > 0) != (db > 0):
                total += 1
    return total


# THERE IS DELIBERATELY NO `median` HERE, and the reason is a bug this file
# briefly contained. The representative replicate must be the SHIPPED one --
# `domain.affinity_range.AffinityRange.median` -- which is
# `sorted(values)[n // 2]`, so for even n it takes the LESS NEGATIVE of the two
# middle values on purpose: the conservative side for a Vina score, and one
# rule for both parities.
#
# The first version of this module wrote its own, averaging the two middles.
# On `[-10, -9, -8, -1]` the shipped rule gives -8.0 and the average gives
# -8.5, so the benchmark would have reported a representative the application
# never produces -- while measuring something it calls "what the panel shows".
# Caught by running the shipped fixture through both, which is the only reason
# a 0.5 kcal/mol disagreement between two plausible medians was visible at all.
#
# Callers import `AffinityRange` and ask it. Two implementations of one
# statistic is how a benchmark and its subject come to disagree.
