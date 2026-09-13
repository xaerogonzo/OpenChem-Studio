from __future__ import annotations

from pathlib import Path

from openchem.commands.base import OpenChemCommand
from openchem.domain.project import ProjectModel
from openchem.domain.result_store import SessionResultStore
from openchem.services.project_service import ProjectService


class SaveProjectCommand(OpenChemCommand):
    """Saving to disk isn't meaningfully reversible; still expressed as a
    command so it appears wherever OpenChemCommands are logged or scripted.

    `results` and `current_fingerprints` are optional so a caller with no
    result store saves exactly the file it always did.
    """

    def __init__(
        self,
        project_service: ProjectService,
        project: ProjectModel,
        path: Path,
        results: SessionResultStore | None = None,
        current_fingerprints: dict[str, dict[str, str]] | None = None,
    ) -> None:
        super().__init__(f"Save project '{project.name}'")
        self._project_service = project_service
        self._project = project
        self._path = path
        self._results = results
        self._current_fingerprints = current_fingerprints

    def redo(self) -> None:
        self._project_service.save(self._project, self._path, self._results, self._current_fingerprints)

    def undo(self) -> None:
        pass


class OpenProjectCommand(OpenChemCommand):
    """The loaded project is available on `.loaded_project` after push(),
    since QUndoStack.push() calls redo() synchronously -- and its saved
    results on `.loaded_results`, from the same read of the file.
    """

    def __init__(self, project_service: ProjectService, path: Path) -> None:
        super().__init__(f"Open project '{path.name}'")
        self._project_service = project_service
        self._path = path
        self.loaded_project: ProjectModel | None = None
        self.loaded_results: SessionResultStore | None = None

    def redo(self) -> None:
        self.loaded_project, self.loaded_results = self._project_service.load_document(self._path)

    def undo(self) -> None:
        if self.loaded_project is not None:
            self._project_service.close(self.loaded_project)
