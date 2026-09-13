"""A copy of unsaved work, so a crash or a forgotten Save loses nothing.

**WHY.** Results are kept for the whole session now, and the user asked for
them to survive even when the project is never saved. A crash, a killed
process, or closing without saving would otherwise throw away every result
since the last Save -- and those can be minutes of calculator time each.

**WHAT IS WRITTEN.** The same text Save writes (`ProjectService.serialise`,
results included), wrapped with a generation counter, a timestamp and the
path the project was last saved to. One file per project uuid under
`<data root>/recovery`, replaced atomically: written to a temporary file in
the same directory, then `os.replace`d over the old one, so a crash
mid-write leaves the previous copy intact rather than a truncated one.

**THE SAVE RACE, AND THE GENERATION THAT CLOSES IT.** Writes are debounced,
so one can be queued when a Save happens. If it fired afterwards it would
recreate a recovery file for work that is safely on disk -- and the next
launch would offer to "recover" two seconds of nothing. Every Save or
Discard advances `generation`; a write carries the generation it was
scheduled under and is dropped if that is no longer current.

**A DAMAGED FILE IS NOT A PROJECT.** `candidates` parses, builds the project,
and builds the result store before offering anything. A truncated or
foreign file is reported as unusable -- never offered as an empty project,
which would invite somebody to "recover" over their real work.

No Qt here: the debounce timer belongs to the window.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from openchem.domain.project import ProjectModel
from openchem.domain.result_store import SessionResultStore
from openchem.services.project_service import ProjectService

logger = logging.getLogger("openchem.recovery")

#: The wrapper's own layout version; a newer one is not offered.
RECOVERY_VERSION = 1
#: Not `.ocsproj`, so a recovery copy can never be opened by mistake as the
#: project it is a copy of.
SUFFIX = ".ocsrecover"


@dataclass(frozen=True)
class RecoveryCandidate:
    path: Path
    project_uuid: str
    project_name: str
    written_at: float
    generation: int
    source_path: str
    molecule_count: int


class RecoveryService:
    def __init__(self, project_service: ProjectService, directory: Path, clock=time.time) -> None:
        self._project_service = project_service
        self._directory = directory
        self._clock = clock
        #: Advanced by every Save/Discard; see the module docstring.
        self.generation = 0

    def path_for(self, project_uuid: str) -> Path:
        return self._directory / f"{project_uuid}{SUFFIX}"

    def write(
        self,
        project: ProjectModel,
        results: SessionResultStore | None,
        fingerprints: dict[str, dict[str, str]] | None,
        generation: int,
        source_path: str = "",
    ) -> bool:
        """Write a recovery copy, unless it was scheduled before a Save."""
        if generation != self.generation:
            logger.debug("Skipping a recovery write from generation %s (now %s)", generation, self.generation)
            return False
        document = json.loads(self._project_service.serialise(project, results, fingerprints))
        payload = {
            "recovery_version": RECOVERY_VERSION,
            "generation": generation,
            "written_at": self._clock(),
            "source_path": source_path,
            "document": document,
        }
        self._directory.mkdir(parents=True, exist_ok=True)
        target = self.path_for(project.uuid)
        handle, temporary = tempfile.mkstemp(dir=self._directory, prefix=".writing-", suffix=SUFFIX)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(payload, stream)
            os.replace(temporary, target)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        return True

    def settle(self, project_uuid: str) -> None:
        """The work is saved or deliberately discarded: no recovery needed.

        Advances the generation FIRST, so a write already queued cannot
        land after the file is removed.
        """
        self.generation += 1
        self.path_for(project_uuid).unlink(missing_ok=True)

    def candidates(self) -> list[RecoveryCandidate]:
        """Every recovery file that really holds a project, newest first."""
        if not self._directory.is_dir():
            return []
        found = []
        for path in self._directory.glob(f"*{SUFFIX}"):
            if path.name.startswith(".writing-"):
                continue
            candidate = self._validate(path)
            if candidate is not None:
                found.append(candidate)
        found.sort(key=lambda c: c.written_at, reverse=True)
        return found

    def _validate(self, path: Path) -> RecoveryCandidate | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("recovery_version", 0) > RECOVERY_VERSION:
                logger.warning("Recovery file %s is from a newer build; not offered", path.name)
                return None
            project, _results = self._project_service.parse(payload["document"])
        except Exception as exc:  # noqa: BLE001 - a damaged file is unusable, never a crash
            logger.warning("Recovery file %s is unusable: %s", path.name, exc)
            return None
        if f"{project.uuid}{SUFFIX}" != path.name:
            logger.warning("Recovery file %s holds project %s; not offered", path.name, project.uuid)
            return None
        return RecoveryCandidate(
            path=path,
            project_uuid=project.uuid,
            project_name=project.name,
            written_at=float(payload.get("written_at", 0.0)),
            generation=int(payload.get("generation", 0)),
            source_path=str(payload.get("source_path", "")),
            molecule_count=len(project.molecules),
        )

    def load(self, candidate: RecoveryCandidate) -> tuple[ProjectModel, SessionResultStore]:
        payload = json.loads(candidate.path.read_text(encoding="utf-8"))
        return self._project_service.parse(payload["document"])

    def discard(self, candidate: RecoveryCandidate) -> None:
        candidate.path.unlink(missing_ok=True)
