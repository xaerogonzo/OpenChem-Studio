from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from openchem.domain.project import SCHEMA_VERSION, ProjectModel
from openchem.domain.result_store import SessionResultStore
from openchem.events.base import EventBus
from openchem.events.events import ProjectClosed, ProjectLoaded

logger = logging.getLogger("openchem.project")

#: The key the retained calculation results are written under.
RESULTS_KEY = "calculation_results"


class ProjectService:
    """Load/save ProjectModel as `.ocsproj` JSON.

    `_migrate` is the seam for schema changes: because ProjectModel already
    carries `schema_version`, a future on-disk format change is a new branch
    here, not a breaking change to every project file ever saved.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def save(
        self,
        project: ProjectModel,
        path: Path,
        results: SessionResultStore | None = None,
        current_fingerprints: dict[str, dict[str, str]] | None = None,
    ) -> None:
        path.write_text(self.serialise(project, results, current_fingerprints), encoding="utf-8")
        logger.info("Saved project %s to %s", project.uuid, path)

    def serialise(
        self,
        project: ProjectModel,
        results: SessionResultStore | None = None,
        current_fingerprints: dict[str, dict[str, str]] | None = None,
    ) -> str:
        """The file's text. Shared by Save and the recovery writer.

        **THE RESULTS ARE AN ENVELOPE BESIDE THE DOCUMENT, NOT PART OF IT.**
        `ProjectModel` stays what it was -- structures, notes, history --
        and `calculation_results` is written next to its fields by this
        service. A file without the block is an ordinary project; an older
        build reading a file with one ignores a key it does not know.
        """
        # Explicit UTF-8 on both sides: a project file is meant to move
        # between machines, and Python's default is the PLATFORM encoding
        # (cp1252 on Windows). This is safe today only because
        # json.dumps defaults to ensure_ascii=True; the day anything
        # non-ASCII reaches the file it would break silently and
        # asymmetrically depending on who saved it.
        data = project.to_dict()
        if results is not None:
            data[RESULTS_KEY] = results.to_dict(current_fingerprints)
        return json.dumps(data, indent=2)

    def load(self, path: Path) -> ProjectModel:
        return self.load_document(path)[0]

    def load_document(self, path: Path) -> tuple[ProjectModel, SessionResultStore]:
        """The project AND its saved results, from one read of the file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        project, results = self.parse(data)
        self._event_bus.publish(ProjectLoaded(project_uuid=project.uuid))
        logger.info("Loaded project %s from %s", project.uuid, path)
        if results.load_problems:
            logger.warning("Saved results not restored: %s", dict(results.load_problems))
        return project, results

    def parse(self, data: dict[str, Any]) -> tuple[ProjectModel, SessionResultStore]:
        data = self._migrate(data)
        project = ProjectModel.from_dict(data)
        # `.get` with no default block, like `crystals`: a project saved
        # before results were kept loads with an empty store.
        results = SessionResultStore.from_dict(data.get(RESULTS_KEY), project.uuid)
        return project, results

    def close(self, project: ProjectModel) -> None:
        self._event_bus.publish(ProjectClosed(project_uuid=project.uuid))

    def _migrate(self, data: dict[str, Any]) -> dict[str, Any]:
        schema_version = data.get("schema_version", SCHEMA_VERSION)
        if schema_version > SCHEMA_VERSION:
            raise ValueError(
                f"Project schema version {schema_version} is newer than this "
                f"application supports ({SCHEMA_VERSION})"
            )
        # No migrations exist yet — this is where a schema_version 1 -> 2
        # transform would be added once the on-disk format actually changes.
        return data
