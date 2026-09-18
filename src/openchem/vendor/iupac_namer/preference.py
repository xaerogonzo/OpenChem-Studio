"""How candidate naming plans are ranked: typed keys instead of one blended float.

**WHY THIS MODULE EXISTS.** Plans were ranked by one float that added band
constants from 0.0001 to 1,000,000, and comments policed the collisions
("this band-2 score must stay well below 10 so that the band-3 minimum step
always dominates"). A collision is silent -- the output is simply the
second-best name -- and naming round 4 found one living in the smallest band:
the alphanumerical tie-break (P-14.4 (g)) keyed every carbon substituent as
"z", so `ethyl` and `methyl` tied and plan order produced
`4-ethyl-1-methylbenzene`. A real tier cannot be written inside a ×0.0001 term.

Three things, kept apart:

* `LegacyScoreKey` wraps the old float EXACTLY. It is the mechanical step:
  same value, same ordering, same ties, same winners.
* `NomenclaturePreferenceKey` is a tuple of declared tiers compared
  lexicographically (`TIER_SPECS` says what each tier is, and in which
  direction it is better). No tier can overflow into the one above, and locant
  sets are compared at the FIRST POINT OF DIFFERENCE as P-14.3.5 requires,
  where the float compared SUMS ({1,4} and {2,3} tie on a sum).
* `SearchBound` is the early-stop test. It is a different type from a key,
  so a threshold can never be ranked as though it were a plan.

The alphanumerical criterion is deliberately NOT a tier. It needs the
prefixes' complete names (P-14.5.2), which do not exist until a plan is
executed, so it is applied at selection time, between plans that tie on every
tier here -- see `engine._break_alphanumerical_tie`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering
from typing import Any

#: Stamped into stage records, so a comparator change is distinguishable from
#: a library or corpus change.
COMPARATOR_SPEC_ID = "nomenclature-preference-v1"

#: The exact representation P-14.4 (g) compares, as data rather than prose.
#: Prefix name as `assembly.derive_sort_name` produces it: multiplying
#: prefixes excluded, locants / stereodescriptors / isotope descriptors
#: excluded, enclosing marks and hyphens ignored, case-folded, a compound
#: prefix under the first letter of its complete name (P-14.5.2).
SORT_NORMALIZATION_ID = "PREFIX_P14_5_2_V1"


@dataclass(frozen=True)
class TierSpec:
    """One tier of the preference key: what it decides and where it comes from."""

    name: str
    paragraph: str
    better: str  # "higher" or "lower", stated so a reader need not infer it
    note: str = ""


#: The tiers of `NomenclaturePreferenceKey`, in comparison order. Every value
#: is stored so that HIGHER is better; a "lower is better" quantity is stored
#: negated, and the spec says so.
TIER_SPECS: tuple[TierSpec, ...] = (
    TierSpec("plan_kind", "P-12 / P-51",
             "higher",
             "retained 5, substitutive with a ring cation claimed 4, multiplicative 3, "
             "ring assembly 2, functional class 1, other substitutive and replacement 0 -- "
             "the order the legacy constants produced, now declared"),
    TierSpec("pcg_seniority", "P-41 / P-43", "higher",
             "the principal characteristic group's class seniority"),
    TierSpec("parent_selection", "P-44", "higher",
             "LEGACY BLENDED TIER: the P-44 cascade is still one float inside this "
             "tier (see strategy._parent_selection_score). It can no longer overflow "
             "into or be overridden by the tiers below it; its internal constants "
             "are the remaining float to decompose"),
    TierSpec("retained_ring", "P-31.1.3", "higher",
             "a retained ring name over a systematic construction of the same ring"),
    TierSpec("naming_method", "P-31.1.3 / P-52", "higher",
             "how the parent is named (retained > Hantzsch-Widman > ... > systematic). "
             "BEFORE the locant tiers: the method chooses the parent's name, and "
             "numbering is chosen within it. The old ×0.01 band put it after them "
             "for small rank gaps and before them for large ones -- its own "
             "comment relied on the large gaps -- which is not an ordering at all"),
    TierSpec("substituent_count", "P-45.2.1", "higher",
             "'the maximum number of substituent groups cited as prefixes' (p. 415), "
             "which the book applies BEFORE P-45.2.2's lower locant set -- its first "
             "example is 4-methoxy-N-phenylaniline (PIN) [not "
             "N-(4-methoxyphenyl)aniline]. Split out of parent_selection and placed "
             "AFTER the naming method: between two namings of the same ring it "
             "only counts notation (D-022w, D-022z)"),
    TierSpec("heteroatom_locants", "P-31.1.4.2.1", "higher",
             "legacy weighted heteroatom locant score, as before"),
    TierSpec("suffix_locants", "P-31.1.4.2.3", "lower",
             "stored as (-count, -l1, -l2, ...): the locant SET, first point of difference"),
    TierSpec("added_hydrogen_locants", "P-31.1.4.2.4 (d) / P-58.2", "lower",
             "'added indicated hydrogen', after the principal group and before hydro "
             "prefixes (pdf p. 76): pyrimidine-4,6(1H,5H)-dione, not (3H,5H). Stored as "
             "suffix_locants, a fusion letter as +1..26 on number x 100"),
    TierSpec("unsaturation_locants", "P-31.1.4.2.4", "lower", "as suffix_locants"),
    TierSpec("prefix_locants", "P-45.2.2 / P-14.4 (f)", "lower",
             "all detachable prefixes together, as suffix_locants"),
    TierSpec("primes", "P-14.3", "lower", "unprimed ring-assembly locants before primed"),
)


@total_ordering
@dataclass(frozen=True)
class LegacyScoreKey:
    """The old float, wrapped. Ordering is the float's ordering, exactly."""

    value: float

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, LegacyScoreKey):
            return NotImplemented
        return self.value < other.value


@total_ordering
@dataclass(frozen=True)
class NomenclaturePreferenceKey:
    """The declared tiers, compared in order. Higher is better throughout."""

    tiers: tuple

    def __post_init__(self) -> None:
        if len(self.tiers) != len(TIER_SPECS):
            raise ValueError(
                f"a preference key needs {len(TIER_SPECS)} tiers, got {len(self.tiers)}"
            )
        for value in self.tiers:
            _check_ordering_domain(value)

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, NomenclaturePreferenceKey):
            return NotImplemented
        return self.tiers < other.tiers

    def first_difference(self, other: "NomenclaturePreferenceKey") -> str | None:
        """The name of the tier that decides between two keys, or None if equal."""
        for spec, mine, theirs in zip(TIER_SPECS, self.tiers, other.tiers):
            if mine != theirs:
                return spec.name
        return None


def _check_ordering_domain(value: Any) -> None:
    """No implicit ordering domains: no None, no NaN, no mixed types.

    A None compares against nothing in Python 3 and would raise mid-sort; a
    NaN compares false against everything and would make ordering silently
    non-transitive. Both are refused at construction instead.
    """
    if value is None:
        raise TypeError("a preference tier may not be None")
    if isinstance(value, float) and value != value:
        raise TypeError("a preference tier may not be NaN")
    if isinstance(value, tuple):
        for item in value:
            if not isinstance(item, (int, float)) or isinstance(item, bool):
                raise TypeError(f"locant tiers hold numbers only, got {item!r}")
            if isinstance(item, float) and item != item:
                raise TypeError("a preference tier may not contain NaN")


@dataclass(frozen=True)
class SearchBound:
    """When a plan is good enough to stop searching. NOT a preference key.

    The legacy search stopped on a float threshold (a retained name scored
    1,000,000). That threshold must not be comparable with keys as though it
    were a plan, so it is its own type with its own question.
    """

    legacy_threshold: float
    #: For `NomenclaturePreferenceKey`: stop once the plan kind reaches this.
    plan_kind_at_least: int

    def reached_by(self, key: Any) -> bool:
        if isinstance(key, LegacyScoreKey):
            return key.value >= self.legacy_threshold
        if isinstance(key, NomenclaturePreferenceKey):
            return key.tiers[0] >= self.plan_kind_at_least
        raise TypeError(f"not a preference key: {key!r}")


def locant_set_tier(locants) -> tuple:
    """A locant set as a "higher is better" tier: fewer locants, then lower ones.

    Sorted, then compared at the first point of difference (P-14.3.5), which
    is what the legacy SUM could not do: {1,4} and {2,3} tie on a sum, and
    P-14.3.5 prefers {1,4}.
    """
    values = sorted(int(v) for v in locants)
    return (-len(values),) + tuple(-v for v in values)
