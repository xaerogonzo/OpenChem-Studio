"""The molecule analysis engine: issues, checkers, and the registry.

Structure checking is the first consumer of this, not the whole of it. The
same `StructureIssue` shape is what an import diagnostic, a batch quality
column and a plugin's own opinion are all expected to speak, which is why
this is a registry of independent checkers rather than one `check()`
function with branches in it.

Pure and Qt-free. RDKit is allowed here (this is the chemistry layer); Qt
is not, so the engine can run in a worker, in a batch job, or in a test
with no application object.

Three deliberate absences, each of which had an argument for it:

**No numeric confidence.** A `WARNING 70%` on a bond-length heuristic is a
number nobody measured, and this project has thrown away work rather than
ship one (Miller polarizability, HLB, TSEI). The real distinction -- some
checks are arithmetic, some are judgement -- is `Basis`, and the panel says
it in words.

**No health score.** Same reason. The useful half, a per-category count, is
free from `CheckerResult.by_category()`.

**No new result base class.** `CheckerResult` joins the existing
`ScientificResult` hierarchy, so batch export, the clipboard path and
provenance display all work already.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from openchem.domain.common import Provenance, ScientificResult


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
    count is DETERMINISTIC: it is right or the periodic table is wrong. A
    bond that looks too short for its order is HEURISTIC: it depends on a
    threshold somebody chose, and reasonable drawings will trip it.
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


#: Display order for categories. Not alphabetical -- most serious first,
#: so a panel that simply iterates this puts VALIDITY at the top.
CATEGORY_ORDER: tuple[Category, ...] = (
    Category.VALIDITY,
    Category.REPRESENTATION,
    Category.GEOMETRY,
    Category.LAYOUT,
    Category.REGULATORY,
    Category.PLUGIN,
)


# --- capabilities -----------------------------------------------------------
#
# What a given structure can actually support being asked about. A checker
# declares what it needs; the engine computes what is available once, up
# front, and skips the rest WITH THE REASON rather than running them
# against a molecule they cannot describe.
#
# This is the thing that stops a cascade. A structure that will not
# sanitize makes every aromaticity, stereo and oxidation-state complaint
# downstream of it meaningless, and forty meaningless warnings hide the one
# real message ("it does not sanitize, here is why").

#: RDKit could read the molblock at all, sanitization aside.
PARSED_MOLECULE = "parsed_molecule"
#: RDKit sanitization succeeded -- aromaticity, valence and ring info are
#: trustworthy.
SANITIZED_MOLECULE = "sanitized_molecule"
#: There is a conformer, and its atoms are not all stacked at one point.
COORDINATES = "coordinates"

#: Why each capability might be missing, in the words the panel shows.
_MISSING_CAPABILITY_REASON = {
    PARSED_MOLECULE: "the structure could not be read",
    SANITIZED_MOLECULE: "the structure does not sanitize",
    COORDINATES: "no coordinates",
}


@dataclass(frozen=True, kw_only=True)
class StructureIssue:
    """One finding about one structure.

    `atom_indices` and `bond_indices` are what lets a panel highlight the
    offending part in our own depiction. They may be empty: "this molecule
    carries a net charge" is about the whole thing.

    `fix_id` names an available repair or is empty. It is deliberately not
    a callable: an issue is data, it travels through events and gets
    exported, and a bound method would not survive either.
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
    #: canvas draws its own valence warnings from Indigo and we cannot turn
    #: those off or enumerate them, so the honest move is to explain the
    #: disagreement rather than pretend it is not on screen.
    explains_editor_warning: bool = False


@dataclass(frozen=True, kw_only=True)
class SkippedChecker:
    """A checker that could not run, and why.

    Reported rather than dropped. "No answer" is part of the answer here,
    the same way the oxidation-state code refuses rather than guesses.
    """

    checker_id: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class CheckerDefinition:
    """One registered checker.

    `run` takes a `CheckContext` and returns the issues it found -- an
    empty sequence means "checked, nothing to report", which is a different
    statement from being skipped.

    `requires` is how a plugin inserts itself into the run without being
    appended to a list somebody has to maintain: declare what you need, and
    the engine works out whether you can run.
    """

    checker_id: str
    display_name: str
    category: Category
    run: Callable[["CheckContext"], Sequence[StructureIssue]]
    requires: frozenset[str] = frozenset({SANITIZED_MOLECULE})
    #: Which library and which rule produced the verdicts, carried per
    #: checker so a finding can cite its source the way every number in
    #: this project already does.
    provenance: Provenance | None = None
    description: str = ""


@dataclass(frozen=True, kw_only=True)
class CheckContext:
    """Everything a checker is given.

    `mol` is sanitized when `SANITIZED_MOLECULE` is available and merely
    parsed otherwise -- never None while `PARSED_MOLECULE` is present, so a
    checker that declared its requirements does not have to re-check them.
    """

    mol: Any  # rdkit.Chem.Mol -- typed loosely so this module imports lazily
    capabilities: frozenset[str]
    molblock: str = ""
    #: Populated when sanitization failed; this is RDKit's own message, and
    #: it is usually the single most useful sentence available.
    sanitization_error: str = ""

    def has(self, capability: str) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True, kw_only=True)
class CheckerResult(ScientificResult):
    """The outcome of one analysis pass over one structure.

    `structure_version` is the anti-staleness field. Every structure change
    increments a counter; a panel holding a result whose version is behind
    the current one must discard it rather than display it. This session
    produced two bugs of exactly that shape already (a canvas showing the
    pre-undo structure, a pose table showing a deleted result), and while
    somebody is drawing quickly is precisely when a highlight pointing at
    the previous structure is most confusing.
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


class CheckerRegistry:
    """Metadata + dispatch for registered checkers.

    Mirrors `CalculatorRegistry` deliberately -- same shape, same
    constructor-injected standalone lifetime -- so a new checker is a
    function plus a registration and never a branch. Expect this to grow
    past thirty; that is the whole reason it is a registry.
    """

    def __init__(self) -> None:
        self._definitions: dict[str, CheckerDefinition] = {}

    def register(self, definition: CheckerDefinition) -> None:
        self._definitions[definition.checker_id] = definition

    def get(self, checker_id: str) -> CheckerDefinition | None:
        return self._definitions.get(checker_id)

    def all(self) -> list[CheckerDefinition]:
        """Every checker, in run order.

        Order is derived from the `requires` sets, not from registration
        order: fewer prerequisites first, then by category seriousness,
        then by id for determinism. A checker needing nothing but a parsed
        molecule therefore reports before one needing coordinates, which
        reads correctly when several fire at once.

        Ordering is presentation. What actually prevents a cascade of
        meaningless warnings is the capability gate in `run_checks`.
        """
        return sorted(
            self._definitions.values(),
            key=lambda d: (len(d.requires), CATEGORY_ORDER.index(d.category), d.checker_id),
        )

    def by_category(self, category: Category) -> list[CheckerDefinition]:
        return [d for d in self.all() if d.category is category]


def build_context(molblock: str) -> CheckContext:
    """Parse once, and record what the result can support being asked.

    Sanitization is attempted separately from parsing because the two
    failures mean different things: an unparseable molblock is a broken
    file, while a molblock that parses but will not sanitize is usually a
    real structure somebody drew that RDKit refuses -- which is itself the
    finding, and is what the `sanitizable` checker reports.
    """
    from rdkit import Chem

    mol = Chem.MolFromMolBlock(molblock, sanitize=False, removeHs=False)
    if mol is None:
        return CheckContext(mol=None, capabilities=frozenset(), molblock=molblock)

    capabilities = {PARSED_MOLECULE}
    sanitization_error = ""
    sanitized = Chem.Mol(mol)
    try:
        Chem.SanitizeMol(sanitized)
    except Exception as exc:  # RDKit raises several unrelated types here
        sanitization_error = str(exc)
    else:
        mol = sanitized
        capabilities.add(SANITIZED_MOLECULE)

    if _has_usable_coordinates(mol):
        capabilities.add(COORDINATES)

    return CheckContext(
        mol=mol,
        capabilities=frozenset(capabilities),
        molblock=molblock,
        sanitization_error=sanitization_error,
    )


def _has_usable_coordinates(mol: Any) -> bool:
    """A conformer whose atoms are not all at the same point.

    A molblock built from SMILES without a depiction step has every atom at
    the origin. That is a conformer by RDKit's reckoning, and every
    geometry checker run against it reports every atom as overlapping every
    other -- the exact cascade the capability gate exists to stop.
    """
    if mol is None or mol.GetNumConformers() == 0:
        return False
    conformer = mol.GetConformer()
    positions = [conformer.GetAtomPosition(i) for i in range(mol.GetNumAtoms())]
    if len(positions) < 2:
        return False
    first = positions[0]
    return any(
        abs(p.x - first.x) > 1e-6 or abs(p.y - first.y) > 1e-6 or abs(p.z - first.z) > 1e-6
        for p in positions[1:]
    )


def run_checks(
    registry: CheckerRegistry,
    context: CheckContext,
    molecule_uuid: str,
    *,
    structure_version: int = 0,
    suppressed: Iterable[str] = (),
) -> CheckerResult:
    """Run every checker whose prerequisites are met, and say why the rest
    did not run.

    A checker that raises is reported as skipped with the exception text
    rather than taking the whole pass down with it. A registry is expected
    to carry plugin-contributed checkers, and one bad plugin must not be
    able to silence every other opinion about a structure.
    """
    suppressed_ids = tuple(dict.fromkeys(suppressed))
    issues: list[StructureIssue] = []
    skipped: list[SkippedChecker] = []

    for definition in registry.all():
        if definition.checker_id in suppressed_ids:
            skipped.append(
                SkippedChecker(checker_id=definition.checker_id, reason="suppressed for this molecule")
            )
            continue

        missing = definition.requires - context.capabilities
        if missing:
            skipped.append(
                SkippedChecker(
                    checker_id=definition.checker_id,
                    reason=_reason_for_missing(missing, context),
                )
            )
            continue

        try:
            issues.extend(definition.run(context))
        except Exception as exc:
            skipped.append(
                SkippedChecker(
                    checker_id=definition.checker_id,
                    reason=f"the check itself failed: {type(exc).__name__}: {exc}",
                )
            )

    return CheckerResult(
        molecule_uuid=molecule_uuid,
        structure_version=structure_version,
        issues=tuple(issues),
        skipped=tuple(skipped),
        suppressed=suppressed_ids,
        provenance=Provenance(
            created_by="core",
            method="openchem.chem.structure_check",
            parameters={
                "checkers_run": len(registry.all()) - len(skipped),
                "checkers_skipped": len(skipped),
                "suppressed": list(suppressed_ids),
            },
        ),
    )


def _reason_for_missing(missing: frozenset[str] | set[str], context: CheckContext) -> str:
    """One sentence naming the single most explanatory missing capability.

    Reporting all of them is noise, so the most fundamental failure wins.

    An unreadable molblock is a special case rather than just the first
    item of an ordered list, because it is the root cause of every other
    absence at once. A geometry checker asks only for coordinates, so
    without this a broken file would be reported to it as "no coordinates"
    -- true, useless, and it buries the one sentence that explains the
    whole run.
    """
    if not context.has(PARSED_MOLECULE):
        return _MISSING_CAPABILITY_REASON[PARSED_MOLECULE]

    for capability in (SANITIZED_MOLECULE, COORDINATES):
        if capability in missing:
            reason = _MISSING_CAPABILITY_REASON[capability]
            if capability is SANITIZED_MOLECULE and context.sanitization_error:
                return f"{reason} ({context.sanitization_error})"
            return reason
    return "a prerequisite was not met"


def build_default_registry() -> CheckerRegistry:
    """The core checkers, registered.

    Imported lazily so this module stays importable without pulling in
    every checker (and, through them, RDKit) -- which is what lets the
    dataclasses above be used from `domain`-adjacent code and tests.
    """
    from openchem.chem.checkers import register_core_checkers

    registry = CheckerRegistry()
    register_core_checkers(registry)
    return registry
