"""What a structure checker found: the data, with no engine attached.

Split from `chem/structure_check.py` for the same reason `domain/docking.py`
is split from `chem/docking_providers.py` -- the result travels further than
the thing that produced it. An event carries it, a panel renders it, the
batch table columns it, and none of those should have to import the
chemistry layer to name its type.

`CheckerResult` joins the `ScientificResult` hierarchy rather than starting
a parallel one, so batch export, the clipboard path and provenance display
already work on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from openchem.domain.common import ScientificResult


class Severity(str, Enum):
    """How much a reader should care.

    ERROR is reserved for "this cannot be a real molecule" -- an impossible
    valence, a structure that will not sanitize. Everything a chemist might
    legitimately have meant is a WARNING or INFO, because a checker that
    calls a deliberate drawing an error teaches people to ignore errors.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Basis(str, Enum):
    """Whether the verdict is arithmetic or judgement.

    This is the honest form of the "confidence percentage" idea. A valence
    count is DETERMINISTIC: it is right, or the periodic table is wrong. A
    bond that looks too short for its order is HEURISTIC: it depends on a
    threshold somebody chose, and reasonable drawings will trip it.

    Two values rather than a number, because a "65%" on a bond-length
    heuristic is a figure nobody measured -- and this project has built,
    measured and then NOT shipped several things for exactly that reason.
    """

    DETERMINISTIC = "deterministic"
    HEURISTIC = "heuristic"


class Category(str, Enum):
    """What kind of claim the issue is making.

    VALIDITY and LAYOUT are separate on purpose. "This valence is
    impossible" and "these two labels overlap" are not the same kind of
    statement, and filing both under one heading is how the serious one
    gets missed in a list of forty.
    """

    VALIDITY = "validity"  # chemically impossible
    GEOMETRY = "geometry"  # the coordinates, as coordinates
    REPRESENTATION = "representation"  # how it is written down
    LAYOUT = "layout"  # drawing quality only
    REGULATORY = "regulatory"
    PLUGIN = "plugin"


#: Display order. Not alphabetical -- most serious first, so a panel that
#: simply iterates this puts VALIDITY at the top.
CATEGORY_ORDER: tuple[Category, ...] = (
    Category.VALIDITY,
    Category.REPRESENTATION,
    Category.GEOMETRY,
    Category.LAYOUT,
    Category.REGULATORY,
    Category.PLUGIN,
)

#: Human wording for each category heading.
CATEGORY_LABELS: dict[Category, str] = {
    Category.VALIDITY: "Chemistry",
    Category.REPRESENTATION: "How it is written",
    Category.GEOMETRY: "Coordinates",
    Category.LAYOUT: "Drawing",
    Category.REGULATORY: "Regulatory",
    Category.PLUGIN: "Plugins",
}


@dataclass(frozen=True, kw_only=True)
class StructureIssue:
    """One finding about one structure.

    `atom_indices` and `bond_indices` are what lets a panel highlight the
    offending part in our own depiction. They may be empty: "this molecule
    carries a net charge" is about the whole thing.

    `fix_id` names an available repair or is empty. Deliberately not a
    callable -- an issue is data, it travels through events and gets
    exported, and a bound method would survive neither.
    """

    checker_id: str
    category: Category
    severity: Severity
    basis: Basis
    message: str
    atom_indices: tuple[int, ...] = ()
    bond_indices: tuple[int, ...] = ()
    fix_id: str = ""
    #: Set when we deliberately accept something the 2D editor flags. The
    #: canvas draws its own valence warnings from Indigo and we can neither
    #: suppress nor enumerate them, so the honest move is to explain the
    #: disagreement rather than pretend it is not on screen.
    explains_editor_warning: bool = False


@dataclass(frozen=True, kw_only=True)
class SkippedChecker:
    """A checker that could not run, and why.

    Reported rather than dropped. "No answer" is part of the answer here,
    the same way the oxidation-state work refuses rather than guesses.
    """

    checker_id: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class CheckerResult(ScientificResult):
    """The outcome of one analysis pass over one structure.

    `structure_version` is the anti-staleness field. Every structure change
    increments a counter; a consumer holding a result whose version is
    behind the current one must discard it rather than display it. This
    project has produced two bugs of exactly that shape (a canvas showing
    the pre-undo structure, a pose table showing a deleted result), and
    while somebody is drawing quickly is precisely when a highlight
    pointing at the previous structure is most confusing.
    """

    molecule_uuid: str
    structure_version: int = 0
    issues: tuple[StructureIssue, ...] = ()
    skipped: tuple[SkippedChecker, ...] = ()
    #: Checker ids the caller waived for this molecule or project. Recorded
    #: rather than silently honoured, so a later reader can tell a check
    #: that was waived from one that passed.
    suppressed: tuple[str, ...] = ()

    @property
    def errors(self) -> tuple[StructureIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[StructureIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.WARNING)

    def by_category(self) -> dict[Category, tuple[StructureIssue, ...]]:
        """Issues grouped for display, in `CATEGORY_ORDER`, omitting
        categories with nothing in them."""
        grouped: dict[Category, tuple[StructureIssue, ...]] = {}
        for category in CATEGORY_ORDER:
            found = tuple(i for i in self.issues if i.category is category)
            if found:
                grouped[category] = found
        return grouped

    @property
    def worst_severity(self) -> Severity | None:
        """The most serious thing found, or None for a clean structure --
        what the status-bar indicator colours itself from."""
        for severity in (Severity.ERROR, Severity.WARNING, Severity.INFO):
            if any(i.severity is severity for i in self.issues):
                return severity
        return None
