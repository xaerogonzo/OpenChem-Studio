"""A project's synthesis plans, and the block of the project file they are saved in (`docs/SYNTHESIS_HELPER_DESIGN.md`, "Saving plans in the project").

**A PLAN IS A DERIVED RECORD, SO AN UNREADABLE ONE COSTS A RE-RUN, NOT A PERSON'S WORK.** That is the difference from `score_definition_store` (a formula somebody wrote, kept whatever its version) and
the reason this store behaves like the run histories instead: an entry this build cannot read, or that fails the checks in `synthesis_route_codec`, is reported in `load_problems` and not restored, and the
other plans carry on. A block from a newer envelope is not restored either. Nothing here guesses.

**WRITTEN ONLY WHEN THERE IS SOMETHING TO WRITE** (`is_empty`), so a project that never planned a synthesis is byte for byte the file it always was and an older build loses nothing by opening it. An
older build that does open a project with plans drops the block on its next save, as it does every block it does not know.

ONE PLAN PER MOLECULE, bound to the molecule's uuid: the plan's own target says which molecule it is for and the structure it was planned for, and the reader compares that structure with the one now
drawn, so a plan for a structure that has since been edited comes back as an earlier plan and never as the current one (`SynthesisPlanningService.result_for`).

Pure: no Qt, no chemistry.
"""

from __future__ import annotations

import logging
from typing import Any

from openchem.domain.synthesis_route import RouteSet
from openchem.domain.synthesis_route_codec import STORABLE, PlanDecodeError, decode_route_set, encode_route_set

logger = logging.getLogger("openchem.chemistry")

#: The version of the block's envelope (`{"version": ..., "plans": [...]}`), separate from the format of a plan inside it.
ENVELOPE_VERSION = 1

#: The most plans one project keeps. A plan is at most a few tens of kilobytes; a project of thousands of structures that each had a search is not what this is for, and an unbounded block is how a file becomes a problem.
MAX_PLANS = 2000


class SynthesisPlanStore:
    """One project's plans, by molecule uuid, in the order they were stored."""

    def __init__(self, project_uuid: str) -> None:
        self.project_uuid = project_uuid
        self._plans: dict[str, RouteSet] = {}
        #: Why a plan in the file was not read, one sentence each, naming no substance and quoting no text from the file.
        self.load_problems: tuple[str, ...] = ()
        #: The plans that were read but not kept as they were (a screening that could not be read), same shape as `load_problems`.
        self.load_notes: tuple[str, ...] = ()

    def plans(self) -> tuple[RouteSet, ...]:
        return tuple(self._plans.values())

    def get(self, molecule_uuid: str) -> RouteSet | None:
        return self._plans.get(molecule_uuid)

    def __len__(self) -> int:
        return len(self._plans)

    @property
    def is_empty(self) -> bool:
        return not self._plans

    def put(self, route_set: RouteSet) -> bool:
        """Keep `route_set` as its molecule's plan. False (and nothing kept) for a status the file does not keep or when the project already holds `MAX_PLANS`."""
        if route_set.status not in STORABLE:
            return False
        uuid = route_set.target.molecule_uuid
        if uuid not in self._plans and len(self._plans) >= MAX_PLANS:
            return False
        self._plans[uuid] = route_set
        return True

    # --- the project file ------------------------------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {"version": ENVELOPE_VERSION, "plans": [encode_route_set(plan) for plan in self._plans.values()]}

    @classmethod
    def from_dict(cls, data: Any, project_uuid: str) -> SynthesisPlanStore:
        """The store a block describes. `None` (a project saved before plans were kept) is an empty store. Never raises."""
        store = cls(project_uuid)
        if data is None:
            return store
        problems: list[str] = []
        notes: list[str] = []
        version = data.get("version") if isinstance(data, dict) else None
        entries = data.get("plans") if isinstance(data, dict) else None
        if isinstance(version, bool) or not isinstance(version, int) or version != ENVELOPE_VERSION:
            problems.append(f"the synthesis_plans block is not one this build reads (envelope {version!r}; this build reads {ENVELOPE_VERSION}); its plans are not restored")
        elif not isinstance(entries, list):
            problems.append("the synthesis_plans block has no list of plans; none is restored")
        else:
            if len(entries) > MAX_PLANS:
                problems.append(f"the synthesis_plans block holds {len(entries)} plans; only the first {MAX_PLANS} are read")
            for position, raw in enumerate(entries[:MAX_PLANS], start=1):
                try:
                    route_set, entry_notes = decode_route_set(raw)
                except PlanDecodeError as exc:
                    problems.append(f"plan {position} was not restored: {exc}")
                    continue
                if route_set.target.molecule_uuid in store._plans:
                    problems.append(f"plan {position} was not restored: the molecule already has a plan in this file; the first is used")
                    continue
                store._plans[route_set.target.molecule_uuid] = route_set
                notes.extend(f"plan {position}: {note}" for note in entry_notes)
        store.load_problems = tuple(problems)
        store.load_notes = tuple(notes)
        for problem in (*problems, *notes):
            logger.warning("%s", problem)
        return store
