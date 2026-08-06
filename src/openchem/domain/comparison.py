"""Comparing one calculator's output across several molecules, per atom.

**Read this before assuming a comparison table is missing: it is not.**
`domain/batch.py` already tabulates N molecules against M calculators, and
`BatchAnalysisDialog` already correlates, clusters and PCAs the result.
Anything that wants "these molecules, side by side, one number each" should
use that and not this.

What batch cannot do is the reason this exists. `result_reduction.
_reduce_per_atom` collapses a `PerAtomDataset` to ONE float per molecule --
which is right for a 200-row survey and destroys exactly the data a
difference map needs. Aspirin against salicylic acid coloured by delta
partial charge is a question about atom 7 against atom 7, and by the time
the mean has been taken there are no atoms left to ask about.

So the split is deliberate: **batch is the wide survey, this is the deep
pairwise comparison.** The entry KIND is explicit so that stays true when
spectra and tables arrive -- aggregation becomes the default *view* of a
`PER_ATOM` entry rather than the shape everything is forced into.

`chem/result_reduction.PER_ATOM_AGGREGATES` supplies that view, reused
rather than re-derived, and the raw values stay reachable beside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from openchem.domain.common import ScientificResult


class EntryKind(str, Enum):
    """What sort of thing is being compared for one molecule.

    `SPECTRUM` and `TABLE` have no view yet. They are named now because the
    cost is one enum member, and the cost of admitting them to a
    scalar-shaped API later is a redesign of every consumer.
    """

    SCALAR = "scalar"
    PER_ATOM = "per_atom"
    SPECTRUM = "spectrum"
    TABLE = "table"
    #: The calculator produced nothing for this molecule, or has not run for
    #: it. Distinct from a zero, and never rendered as one -- an absent
    #: partial charge and a partial charge of 0.00 are different findings.
    ABSENT = "absent"


@dataclass(frozen=True)
class ComparisonEntry:
    """One molecule's contribution to a comparison.

    `values` keeps the per-atom numbers AS per-atom numbers. `scalar` is the
    reduced view when one applies, and `aggregate` records how it was
    reduced, because "0.42" means different things as a mean and as a
    max_abs and a reader cannot tell them apart afterwards.

    Not hashable: `values` is a dict, so the frozen dataclass's generated
    `__hash__` raises. Same trade `PerAtomDataset` already makes, and the
    same one that cost an afternoon in `AtomFact` -- filter these by
    identity or index, never by putting them in a set.
    """

    molecule_uuid: str
    molecule_name: str
    kind: EntryKind
    scalar: float | None = None
    #: Atom index -> value, for a `PER_ATOM` entry. Empty otherwise.
    values: dict[int, float] = field(default_factory=dict)
    aggregate: str = ""
    units: str = ""
    #: Why there is no number, when there is no number. A per-atom
    #: calculator that legitimately found nothing (caffeine's zero
    #: functional groups) must say so rather than render blank.
    note: str = ""

    def __bool__(self) -> bool:
        return self.kind is not EntryKind.ABSENT


@dataclass(frozen=True)
class AtomDelta:
    """One atom's difference between the reference molecule and another.

    Carries both atom indices, not just the delta, because the whole point
    is to be able to point at the atom afterwards -- highlight it in the
    viewer, select its row in the Atom Inspector. A bare number cannot.
    """

    reference_index: int
    other_index: int
    reference_value: float
    other_value: float
    element: str = ""

    @property
    def delta(self) -> float:
        return self.other_value - self.reference_value


@dataclass(frozen=True, kw_only=True)
class ComparisonDataset(ScientificResult):
    """One calculator, several molecules, with the per-atom data intact.

    Deliberately not a `dict[str, float]` and deliberately not a
    `BatchTable`. The first cannot hold what a difference map needs; the
    second already exists and answers the other question (see the module
    docstring).
    """

    calculator_id: str
    calculator_name: str
    entries: tuple[ComparisonEntry, ...] = ()
    aggregate: str = ""
    units: str = ""
    #: True when the values are category ids (ring system, functional
    #: group) rather than measurements. A delta between two category ids is
    #: arithmetic on labels and means nothing, so consumers must not
    #: subtract these -- `deltas_against` refuses.
    categorical: bool = False
    limitations: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return any(self.entries)

    def present(self) -> tuple[ComparisonEntry, ...]:
        """Only the molecules that actually produced something."""
        return tuple(entry for entry in self.entries if entry)

    def comparable(self) -> tuple[ComparisonEntry, ...]:
        """Entries carrying a number that can be ranked against the others."""
        return tuple(entry for entry in self.present() if entry.scalar is not None)

    def spread(self) -> tuple[float, float] | None:
        """(min, max) of the comparable numbers, or None if there are none.

        A range rather than a single "difference" because a comparison of
        more than two molecules has no single difference, and taking the
        first pair would be an arbitrary answer to a question nobody asked.
        """
        numbers = [entry.scalar for entry in self.comparable() if entry.scalar is not None]
        if not numbers:
            return None
        return min(numbers), max(numbers)

    # A `per_atom_entries()` filter was written here and removed: nothing
    # called it. `EntryKind` is what makes a later difference map a new view
    # rather than a rewrite; an unused accessor added nothing to that and
    # is two lines to write when something wants it.

    def entry_for(self, molecule_uuid: str) -> ComparisonEntry | None:
        for entry in self.entries:
            if entry.molecule_uuid == molecule_uuid:
                return entry
        return None
