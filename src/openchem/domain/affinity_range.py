"""The spread of a docking score across repeated searches, and the one thing
that spread licenses.

A single Vina affinity is one draw from a distribution. Measured on 5C1M at
exhaustiveness 25, changing nothing but the random seed moved one molecule by
0.06 kcal/mol, while three different fentanyl analogues spanned 0.13 -- so the
difference between three *different molecules* was about twice what one
molecule shows against a seed change. The pose table printed the number to two
decimal places either way.

WHAT THIS MODULE COMPUTES IS THE SAMPLE RANGE of the runs performed. It is
deliberately not called an interval: "interval" invites a reading as a
confidence or prediction interval, which is the exact misreading this exists to
prevent. It describes variation among the runs performed here. It is not an
uncertainty on the binding affinity.

TWO LAYERS, AND THEY ARE SEPARATE FUNCTIONS ON PURPOSE
------------------------------------------------------

    layer 1   `ranges_separate`      pure geometry, distribution-free.
                                     Answers "do these two observed ranges
                                     completely separate?" and nothing else.

    layer 2   `separation_p_value`   the statistical rationale for believing
                                     layer 1 means something.

Fusing them would mean that a later change to the statistic silently changes
which pairs the application orders. The ordering rule survives the statistical
framing evolving, because it never depended on it.

`ranges_separate` is named for what it does and nothing more. A deterministic
provider returning [-9, -9, -9] against [-8, -8, -8] separates -- truthfully as
a statement about those values, and meaninglessly as evidence about
reproducibility. A name like `supports_ordering` does not survive that case.

WHAT A SEPARATION LICENSES, IN ONE DIRECTION ONLY
-------------------------------------------------

    ranges OVERLAP        "indistinguishable by this method"    SUPPORTED
    ranges are DISJOINT   "A binds better than B"               NOT SUPPORTED

Non-overlap says the *scoring function* separated them by more than its own
run-to-run scatter. It does not say the separation is real: CASF-2016 puts even
top-ranked scoring functions at correlation "around 0.6" ([source:su2019]), and
an independent 800-complex evaluation puts Vina at 0.498 ([source:nguyen2020]).
An error bar that read as accuracy would be strictly worse than the bare number
it replaced, because a bare number at least claims no precision.

THE STATISTICAL LAYER NEEDS INDEPENDENT REPLICATE SETS
------------------------------------------------------

Complete separation is the extreme outcome (U = 0) of the Mann-Whitney /
Wilcoxon rank-sum test ([source:mann1947]). Under the null that the two ligands
share an affinity distribution, all n_a + n_b values are exchangeable, so every
assignment of ranks is equally likely and exactly one puts all of A below all
of B -- one more puts all of B below all of A.

THE PROCEDURE IS TWO-SIDED, because the caller reports a separation in either
direction without fixing one beforehand. So the rate is 2/C(n_a+n_b, n_a), not
1/C(...):

    n        one-sided      the procedure actually shipped
    2        0.167          0.333
    3        0.050          0.100     <- does NOT reach 0.05
    4        0.014          0.029     <- the smallest that does
    5        0.004          0.008

`MIN_REPLICATES_FOR_SEPARATION` is derived from that function rather than
typed, so the two cannot drift apart.

EXCHANGEABILITY IS A PRECONDITION ON THE CALLER, not something this module can
check. It requires the two replicate sets to be independent -- which is why
`DockingService` derives replicate seeds per ligand, from
(protocol_seed, ligand_uuid), so two ligands never share a replicate seed.
Sharing one would make the values arrive as correlated pairs and would void the
exact calculation. A paired or deterministic provider may still be shown the
range and the separation verdict; it must not be given the p-value reading.

AND A PER-PAIR RATE DOES NOT CONTROL A TABLE. A 50-ligand screen has 1225
pairs; at 0.029 each you would expect ~35 falsely-ordered pairs. No p-value is
ever rendered per row -- it justifies the minimum count and belongs in the
documentation, not in a cell.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from itertools import count

#: The false-separation rate this application is willing to accept for ONE
#: pair of ligands.
#:
#: A DECLARED STATISTICAL CONVENTION, not a measurement, and deliberately not a
#: kcal/mol quantity. Nothing in this module is fitted to a molecule: the only
#: inputs to the gate are two replicate COUNTS, so there is no threshold in the
#: units of the data for anyone to tune. That is the structural answer to the
#: roadmap's requirement that the reported spread be measured and never
#: assumed -- a "noise floor" constant cannot be added here without the
#: scaling-invariance guard going red.
SEPARATION_ALPHA = 0.05


class Ordering(Enum):
    """What the replicate evidence says about two ligands.

    THREE OUTCOMES, NOT TWO. "The ranges overlap" and "there are too few runs
    to tell" are different statements, and collapsing them is the same class of
    error as reporting a spread of +/-0.00 for a single run. `NOT_ASSESSED` is
    what makes a one-replicate screen safe by construction: every pair returns
    it, so nothing is ordered and the table can say why.
    """

    #: The observed ranges do not overlap, at counts that can support it.
    SEPARATED = "separated"
    #: The observed ranges overlap. Indistinguishable by this method.
    NOT_SEPARATED = "not_separated"
    #: Too few runs for any arrangement of the numbers to support an ordering.
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True, slots=True)
class AffinityRange:
    """The best affinity from each successful replicate, and nothing derived
    that the count does not support.

    RAW VALUES ARE STORED, never a summary. A reader can recompute, the count
    is inherent rather than an adjacent field that can drift from it, and no
    distributional shape is asserted anywhere.

    THE VALUES ARE PER-REPLICATE BEST AFFINITIES, never per pose row. Pose 1 of
    run A and pose 1 of run B are not the same pose, and `rmsd_lb`/`rmsd_ub`
    are measured relative to pose 1 *of their own run*, so a cross-replicate
    row comparison silently mixes reference frames. A per-row range would
    invent a correspondence that does not exist.

    RANGE + MEDIAN + N, never mean +/- sd. The per-replicate best is a minimum
    over Vina's own internal exhaustiveness runs AND over the poses of each --
    a skewed, extreme-value-shaped statistic. A mean with a standard deviation
    invites a Gaussian reading of it. The rank-based separation rule is
    unaffected by the skew because it is distribution-free, which is the reason
    it is the rule.
    """

    #: One best-affinity value per SUCCESSFUL replicate, in run order.
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.values:
            # An absent range is `None` at the call site, never an empty
            # AffinityRange. Allowing an empty one would give `low`/`high`
            # nothing to answer with and would make "no successful replicate"
            # indistinguishable from "not measured".
            raise ValueError("An AffinityRange needs at least one value")

    @property
    def n(self) -> int:
        """How many runs this range was measured over.

        Rendered wherever the range is, because a spread over 3 seeds and over
        30 say different things -- and because the width GROWS with n in
        expectation, so a wider range is not a noisier molecule and two widths
        measured at different n are not comparable.
        """
        return len(self.values)

    @property
    def low(self) -> float:
        return min(self.values)

    @property
    def high(self) -> float:
        return max(self.values)

    @property
    def width(self) -> float | None:
        """The measured spread, or None when a single run measured none.

        NONE AT n == 1, AND 0.0 ONLY WHEN MEASURED. Five runs that genuinely
        agree have a width of exactly zero and that is a result; one run has no
        width at all and that is an absence. Encoding the difference in the
        TYPE is what makes it impossible for a caller to print "+/-0.00" by
        accident -- this project's `n/a is not 0` rule, in the one place it can
        be enforced rather than remembered.
        """
        if self.n < 2:
            return None
        return self.high - self.low

    @property
    def median(self) -> float:
        """The representative value: `sorted(values)[n // 2]`.

        NOT THE BEST. Taking the most negative value would be a max-over-N
        selection, so the headline number would get better purely as the
        replicate count rose -- the reported affinity becoming a function of
        how many times it was run, which is the exact harm this whole module
        exists to prevent, reintroduced in the first number a reader sees.

        For even n this picks the LESS NEGATIVE of the two middle values, which
        is the conservative side for a Vina score and gives one rule for both
        parities rather than a special case.
        """
        return sorted(self.values)[self.n // 2]


def separation_p_value(n_a: int, n_b: int) -> float:
    """The probability that two exchangeable replicate sets of these sizes
    separate completely, in either direction.

    The exact two-sided rate of the extreme (U = 0) rank-sum outcome:
    `2 / C(n_a + n_b, n_a)`.

    TWO COUNTS, NEVER ONE, because unequal sizes are the ordinary case -- a
    failed replicate, a legacy result, a re-run at a different setting -- and
    the general form behaves in a way no "minimum 4 each" shortcut reproduces:

        2 vs 5   0.095   refused
        2 vs 8   0.044   allowed

    So this is COMPUTED and never tabulated.
    """
    if n_a < 1 or n_b < 1:
        raise ValueError("A replicate count is at least 1")
    return 2 / math.comb(n_a + n_b, n_a)


def minimum_replicates(alpha: float = SEPARATION_ALPHA) -> int:
    """The smallest equal replicate count at which a separation can ever be
    supported at `alpha`.

    DERIVED, NEVER TYPED. Writing `4` here would be a second statement of
    something `separation_p_value` already determines, free to drift from it
    the moment the procedure changes -- and this project's first draft of this
    module did exactly that, hard-coding a 3 that a one-sided formula had
    justified and a two-sided one does not.

    Terminates for any positive alpha because the p-value falls monotonically
    to zero in n.
    """
    if alpha <= 0:
        raise ValueError("alpha must be positive")
    for n in count(1):
        if separation_p_value(n, n) <= alpha:
            return n
    raise AssertionError("unreachable: the p-value falls to zero in n")


#: The smallest equal replicate count that can support a separation at
#: `SEPARATION_ALPHA`. Computed at import from the function that justifies it,
#: so the two cannot disagree.
MIN_REPLICATES_FOR_SEPARATION = minimum_replicates()


def ranges_separate(lower: AffinityRange, upper: AffinityRange) -> bool:
    """Whether `lower`'s whole range lies below `upper`'s.

    PURE GEOMETRY. No null model, no distributional assumption, no replicate
    count -- just `max(lower) < min(upper)`. Everything statistical is in
    `separation_p_value`, and keeping the two apart is what stops a change to
    the statistic silently changing which pairs get ordered.

    "BELOW" MEANS NUMERICALLY LOWER, which for a Vina affinity is the BETTER
    score. The direction reads backwards and is stated rather than left to be
    inferred -- `screening_service.rank()` carries the same warning for the
    same reason.

    Strict: two ranges that merely touch (`max(lower) == min(upper)`) do not
    separate.

    This is a strict partial order (an interval order): if A lies below B and B
    below C, then A.high < B.low <= B.high < C.low, so A lies below C. The
    dominance ranking depends on that transitivity.
    """
    return lower.high < upper.low


def separated_below(
    lower: AffinityRange, upper: AffinityRange, alpha: float = SEPARATION_ALPHA
) -> bool:
    """Whether `lower` is below `upper` AND the counts can support saying so.

    Both layers, composed in the one place that is entitled to compose them.
    """
    return (
        separation_p_value(lower.n, upper.n) <= alpha
        and ranges_separate(lower, upper)
    )


def compare(
    a: AffinityRange, b: AffinityRange, alpha: float = SEPARATION_ALPHA
) -> Ordering:
    """What the replicate evidence says about this pair.

    The count is checked FIRST: with too few runs the answer is
    `NOT_ASSESSED` whatever the numbers are, because no arrangement of them
    could support a separation. Reporting `NOT_SEPARATED` there would say the
    ligands were measured and found indistinguishable, which is a stronger
    claim than the data makes.
    """
    if separation_p_value(a.n, b.n) > alpha:
        return Ordering.NOT_ASSESSED
    if ranges_separate(a, b) or ranges_separate(b, a):
        return Ordering.SEPARATED
    return Ordering.NOT_SEPARATED


def dominance_rank(
    ranges: Sequence[AffinityRange], alpha: float = SEPARATION_ALPHA
) -> list[int]:
    """A rank per entry: 1 + however many entries are separated below it.

    NOT A TIE-GROUPING OVER OVERLAPPING PAIRS, which was this design's first
    answer and destroys real findings. "Not separated" is not an equivalence
    relation -- with A = [-9.0, -8.5], B = [-8.6, -7.0], C = [-7.2, -6.0], A
    overlaps B and B overlaps C while A and C are disjoint. Grouping by
    overlap renders 1, 1, 1 and loses a genuine separation.

    "Separated below" IS a strict partial order (see `ranges_separate`), so
    counting dominators is well defined. On that example it gives 1, 1, 2:
    A and B indistinguishable, C behind at least one of them.

    It collapses to 1..N when everything separates, and to all-1 when nothing
    does -- including when every entry has too few replicates to assess, which
    is what makes a single-run screen stop numbering an ordering it cannot
    support.
    """
    return [
        1 + sum(1 for other in ranges if separated_below(other, entry, alpha))
        for entry in ranges
    ]
