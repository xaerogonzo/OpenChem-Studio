"""A project's score definitions, and the block of the project file they are saved in (`docs/DERIVED_SCORES_DESIGN.md` section 8).

**DEFINITIONS ARE PROJECT DATA, IN A BLOCK OF THEIR OWN** (`derived_scores`), with an envelope version of their own, so a number can be reproduced by
whoever opens the file. They are not results and do not go through `result_codec`: plain data with an explicit `to_dict`, so there is no class on an
allow-list to construct from a file.

**NOTHING A PERSON WROTE IS DROPPED BECAUSE THIS BUILD CANNOT READ IT.** Ignoring a definition with a warning is what happens to a newer quantum-chemistry
run, and for a derived record that costs a re-run. A formula is authored, and the next save would delete it. So:

* a definition from a newer format is KEPT as it was read, shown as "written by a newer version, not evaluated", and written back unchanged;
* a damaged one is kept the same way, with the reason, so that a person can mend the file;
* a block from a newer ENVELOPE is kept whole and written back unchanged, and this build shows none of it.

This build does not stamp the project file with a newer `schema_version`: an older build opens a project that holds definitions and drops the block on its
next save, as it does every block it does not know. That cost was accepted for the beta (the design record, section 8).

Pure: no Qt, no chemistry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from openchem.domain.score_definition import MAX_DEFINITIONS, DefinitionError, NewerDefinition, ScoreDefinition

logger = logging.getLogger("openchem.scores")

#: The version of the block's envelope (`{"version": ..., "definitions": [...]}`), separate from the definition format inside it.
ENVELOPE_VERSION = 1

#: An entry kept because a later build wrote it (a definition format this build does not read).
KEPT_NEWER = "newer"

#: An entry kept because it is not a definition at all, or is one with something missing or of the wrong type.
KEPT_DAMAGED = "damaged"


@dataclass(frozen=True)
class KeptEntry:
    """An entry of the block that this build cannot use, exactly as it was read."""

    #: What was in the file, unchanged. Written back as it is.
    raw: Any
    #: `KEPT_NEWER` or `KEPT_DAMAGED`.
    kind: str
    #: For the person: what is wrong, or which version wrote it.
    reason: str

    @property
    def score_id(self) -> str:
        """The entry's own id when it has a readable one, for a message; empty otherwise."""
        if isinstance(self.raw, dict) and isinstance(self.raw.get("score_id"), str):
            return self.raw["score_id"]
        return ""

    @property
    def label(self) -> str:
        if isinstance(self.raw, dict) and isinstance(self.raw.get("label"), str):
            return self.raw["label"]
        return ""


class ScoreDefinitionStore:
    """One project's definitions, in the order they were made, plus whatever this build had to leave alone."""

    def __init__(self, project_uuid: str) -> None:
        self.project_uuid = project_uuid
        #: Definitions and kept entries in one list, in file order, so a save puts everything back where it was.
        self._items: list[ScoreDefinition | KeptEntry] = []
        #: The whole block, when its envelope is one this build cannot read. Written back unchanged; nothing in the store is then usable.
        self._foreign: Any = None
        self.load_problems: tuple[str, ...] = ()

    # --- reading ---------------------------------------------------------------------------------------------------------

    def definitions(self) -> tuple[ScoreDefinition, ...]:
        return tuple(item for item in self._items if isinstance(item, ScoreDefinition))

    def kept(self) -> tuple[KeptEntry, ...]:
        """Entries this build cannot use: newer, or damaged."""
        return tuple(item for item in self._items if isinstance(item, KeptEntry))

    @property
    def foreign(self) -> bool:
        """True when the whole block is from a newer envelope and is being carried through untouched."""
        return self._foreign is not None

    def get(self, score_id: str) -> ScoreDefinition | None:
        for item in self._items:
            if isinstance(item, ScoreDefinition) and item.score_id == score_id:
                return item
        return None

    def score_ids(self) -> tuple[str, ...]:
        """Every id in the block, including the ones kept, so a new id never collides with something that is only being carried."""
        ids = [item.score_id for item in self._items]
        return tuple(i for i in ids if i)

    def __len__(self) -> int:
        return len(self.definitions())

    @property
    def is_empty(self) -> bool:
        """Nothing to save: no definition, nothing kept and no foreign block. A project with none writes no block at all, so a file that never used scores
        is byte for byte the file it always was, and an older build loses nothing by opening it."""
        return not self._items and not self.foreign

    # --- writing ---------------------------------------------------------------------------------------------------------

    def _check_writable(self) -> None:
        if self.foreign:
            raise ValueError("this project's score definitions were written by a newer version of the application and cannot be changed here")

    def add(self, definition: ScoreDefinition) -> None:
        self._check_writable()
        if definition.score_id in self.score_ids():
            raise ValueError(f"a score with the id {definition.score_id} already exists")
        if len(self._items) >= MAX_DEFINITIONS:
            raise ValueError(f"a project holds at most {MAX_DEFINITIONS} scores")
        self._items.append(definition)

    def replace(self, definition: ScoreDefinition) -> None:
        """Put `definition` where the one with its id was. A kept entry is never replaced: the id would silently take it over."""
        self._check_writable()
        for index, item in enumerate(self._items):
            if isinstance(item, ScoreDefinition) and item.score_id == definition.score_id:
                self._items[index] = definition
                return
        raise KeyError(definition.score_id)

    def remove(self, score_id: str) -> bool:
        self._check_writable()
        for index, item in enumerate(self._items):
            if isinstance(item, ScoreDefinition) and item.score_id == score_id:
                del self._items[index]
                return True
        return False

    # --- the project file ------------------------------------------------------------------------------------------------

    def to_dict(self) -> Any:
        if self.foreign:
            return self._foreign
        return {
            "version": ENVELOPE_VERSION,
            "definitions": [item.to_dict() if isinstance(item, ScoreDefinition) else item.raw for item in self._items],
        }

    @classmethod
    def from_dict(cls, data: Any, project_uuid: str) -> ScoreDefinitionStore:
        """The store a block describes. `None` (a project saved before scores existed) is an empty store. Never raises: what cannot be read is kept."""
        store = cls(project_uuid)
        if data is None:
            return store
        problems: list[str] = []
        version = data.get("version") if isinstance(data, dict) else None
        if not isinstance(data, dict) or isinstance(version, bool) or not isinstance(version, int) or version != ENVELOPE_VERSION:
            store._foreign = data
            problems.append(
                f"the derived_scores block is not one this build reads (envelope {version!r}; this build reads {ENVELOPE_VERSION}); it is kept as it is"
            )
            store.load_problems = tuple(problems)
            return store
        entries = data.get("definitions")
        if not isinstance(entries, list):
            store._foreign = data
            problems.append("the derived_scores block has no list of definitions; it is kept as it is")
            store.load_problems = tuple(problems)
            return store
        seen: set[str] = set()
        for raw in entries:
            try:
                definition = ScoreDefinition.from_dict(raw)
            except NewerDefinition as exc:
                store._items.append(KeptEntry(raw, KEPT_NEWER, str(exc)))
                continue
            except DefinitionError as exc:
                store._items.append(KeptEntry(raw, KEPT_DAMAGED, str(exc)))
                problems.append(f"a score definition is damaged and is kept as it is: {exc}")
                continue
            if definition.score_id in seen:
                store._items.append(KeptEntry(raw, KEPT_DAMAGED, f"the score id {definition.score_id} appears twice; the first is used"))
                problems.append(f"the score id {definition.score_id} appears twice; the second is kept as it is")
                continue
            seen.add(definition.score_id)
            store._items.append(definition)
        store.load_problems = tuple(problems)
        for problem in problems:
            logger.warning("%s", problem)
        return store

