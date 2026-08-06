"""The molecule analysis engine: issues, checkers, and the registry.

Structure checking is the first consumer of this, not the whole of it. The
same `StructureIssue` shape is what an import diagnostic, a batch quality
column and a plugin's own opinion are all expected to speak, which is why
this is a registry of independent checkers rather than one `check()`
function with branches in it.

Pure and Qt-free. RDKit is allowed here (this is the chemistry layer); Qt
is not, so the engine can run in a worker, in a batch job, or in a test
with no application object.

The findings themselves live in `domain/structure_issue.py` and are
re-exported below. They are split off for the same reason
`domain/docking.py` is split from `chem/docking_providers.py`: a result
travels further than the thing that produced it, and an event or a panel
should not have to import the chemistry layer to name its type. Checker
authors still get one import site, which is what the re-export is for.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from openchem.domain.common import Provenance
from openchem.domain.structure_issue import (
    CATEGORY_ORDER,
    Basis,
    Category,
    CheckerResult,
    Severity,
    SkippedChecker,
    StructureIssue,
)

__all__ = [
    "CATEGORY_ORDER",
    "COORDINATES",
    "PARSED_MOLECULE",
    "SANITIZED_MOLECULE",
    "Basis",
    "Category",
    "CheckContext",
    "CheckerDefinition",
    "CheckerRegistry",
    "CheckerResult",
    "Severity",
    "SkippedChecker",
    "StructureIssue",
    "build_context",
    "build_default_registry",
    "run_checks",
]


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
