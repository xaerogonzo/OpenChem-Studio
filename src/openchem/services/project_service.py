from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from openchem.domain.project import SCHEMA_VERSION, ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import ProjectClosed, ProjectLoaded

logger = logging.getLogger("openchem.project")


class ProjectService:
    """Load/save ProjectModel as `.ocsproj` JSON.

    `_migrate` is the seam for schema changes: because ProjectModel already
    carries `schema_version`, a future on-disk format change is a new branch
    here, not a breaking change to every project file ever saved.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def save(self, project: ProjectModel, path: Path) -> None:
        # Explicit UTF-8 on both sides: a project file is meant to move
        # between machines, and Python's default is the PLATFORM encoding
        # (cp1252 on Windows). This is safe today only because
        # json.dumps defaults to ensure_ascii=True; the day anything
        # non-ASCII reaches the file it would break silently and
        # asymmetrically depending on who saved it.
        path.write_text(json.dumps(project.to_dict(), indent=2), encoding="utf-8")
        logger.info("Saved project %s to %s", project.uuid, path)

    def load(self, path: Path) -> ProjectModel:
        data = json.loads(path.read_text(encoding="utf-8"))
        data = self._migrate(data)
        project = ProjectModel.from_dict(data)
        self._event_bus.publish(ProjectLoaded(project_uuid=project.uuid))
        logger.info("Loaded project %s from %s", project.uuid, path)
        return project

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
