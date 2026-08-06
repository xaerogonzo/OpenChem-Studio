"""Runs the checkers, owns the structure version, applies the quick fixes.

Synchronous, like `MeasurementService` and unlike the descriptor and
docking services. Nine checkers over a drawing-sized molecule is
arithmetic over a few dozen atoms -- measured at well under a millisecond
-- and putting that on a thread pool would buy nothing while adding a
second source of stale results to the one this class exists to prevent.

**The version counter is the point of this class.** Checking is cheap but
not instant, and someone drawing quickly generates edits faster than
results come back. Every edit bumps the molecule's version; every result
carries the version it was computed from; a consumer compares before
displaying. Without that, the panel eventually shows a finding about a
structure that no longer exists, with atom indices that now point at
different atoms -- which is the same bug class this project already hit
twice (a canvas showing the pre-undo structure, a pose table showing a
deleted result).
"""

from __future__ import annotations

from openchem.chem.quick_fixes import QuickFix, QuickFixRegistry, build_default_fix_registry
from openchem.chem.structure_check import (
    CheckerRegistry,
    build_context,
    build_default_registry,
    run_checks,
)
from openchem.domain.structure_issue import CheckerResult
from openchem.events.base import EventBus
from openchem.events.events import MoleculeChanged, StructureChecked


class StructureCheckService:
    def __init__(
        self,
        event_bus: EventBus,
        checker_registry: CheckerRegistry | None = None,
        fix_registry: QuickFixRegistry | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._checkers = checker_registry or build_default_registry()
        self._fixes = fix_registry or build_default_fix_registry()
        self._versions: dict[str, int] = {}
        #: Per-molecule waivers. A checker suppressed here is reported as
        #: waived rather than silently dropped -- query atoms, reaction
        #: templates and teaching examples are all drawn wrong on purpose.
        self._suppressed: dict[str, set[str]] = {}

        event_bus.subscribe(MoleculeChanged, self._on_molecule_changed)

    # --- versions -----------------------------------------------------------

    def _on_molecule_changed(self, event: MoleculeChanged) -> None:
        self._versions[event.molecule_uuid] = self._versions.get(event.molecule_uuid, 0) + 1

    def current_version(self, molecule_uuid: str) -> int:
        return self._versions.get(molecule_uuid, 0)

    def is_current(self, result: CheckerResult) -> bool:
        """Whether a result still describes the structure on screen.

        The comparison a consumer must make before displaying anything --
        exposed here rather than left to each panel to reimplement, since
        getting it wrong is silent and looks like a rendering glitch.
        """
        return result.structure_version >= self.current_version(result.molecule_uuid)

    # --- checking -----------------------------------------------------------

    @property
    def checkers(self) -> CheckerRegistry:
        """For plugins, which register their own checkers against it."""
        return self._checkers

    def check(self, molecule_uuid: str, molblock: str) -> CheckerResult:
        """Analyse one structure and publish the result.

        Returns it as well as publishing, so a caller that wants the answer
        now (the batch table, an import pipeline) does not have to round-trip
        through the event bus to get it.
        """
        result = run_checks(
            self._checkers,
            build_context(molblock),
            molecule_uuid,
            structure_version=self.current_version(molecule_uuid),
            suppressed=sorted(self._suppressed.get(molecule_uuid, ())),
        )
        self._event_bus.publish(StructureChecked(result=result))
        return result

    # --- suppression --------------------------------------------------------

    def suppress(self, molecule_uuid: str, checker_id: str) -> None:
        self._suppressed.setdefault(molecule_uuid, set()).add(checker_id)

    def unsuppress(self, molecule_uuid: str, checker_id: str) -> None:
        self._suppressed.get(molecule_uuid, set()).discard(checker_id)

    def suppressed_for(self, molecule_uuid: str) -> frozenset[str]:
        return frozenset(self._suppressed.get(molecule_uuid, ()))

    # --- fixes --------------------------------------------------------------

    def fix_for(self, fix_id: str) -> QuickFix | None:
        return self._fixes.get(fix_id)

    def apply_fix(self, fix_id: str, molblock: str) -> str:
        """The repaired molblock, for the caller to push through
        `EditStructureCommand`.

        This deliberately does NOT touch the molecule or the undo stack
        itself. A service that edited the project directly would produce a
        structure change nobody can undo, which is worse than the issue it
        repaired -- so the transformation lives here and the command stays
        with the caller that owns the stack.
        """
        fix = self._fixes.get(fix_id)
        if fix is None:
            raise KeyError(f"no quick fix registered as {fix_id!r}")
        return fix.apply(molblock)
