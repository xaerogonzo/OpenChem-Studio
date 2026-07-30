from __future__ import annotations

from openchem.commands.base import OpenChemCommand
from openchem.domain.docking import DockingResultModel
from openchem.domain.project import ProjectModel


class SetDockingResultCommand(OpenChemCommand):
    """Mirrors `AddMacromoleculeCommand`'s undoable append/remove shape,
    for the project's `docking_results` list. Its own command, not
    `SetConformersCommand` — a docking result isn't a conformer, and
    nothing about it replaces an existing list wholesale."""

    def __init__(self, project: ProjectModel, result: DockingResultModel) -> None:
        super().__init__(f"Dock result ({len(result.poses)} pose(s))")
        self._project = project
        self._result = result

    def redo(self) -> None:
        self._project.docking_results.append(self._result)
        self._project.record_history(f"Added docking result {self._result.uuid}")

    def undo(self) -> None:
        self._project.docking_results.remove(self._result)
        self._project.record_history(f"Removed docking result {self._result.uuid}")
