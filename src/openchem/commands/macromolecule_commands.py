from __future__ import annotations

from openchem.commands.base import OpenChemCommand
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.project import ProjectModel


class AddMacromoleculeCommand(OpenChemCommand):
    """Mirrors `AddMoleculeCommand` (commands/molecule_commands.py) — same
    undoable append/remove shape, for the project's `macromolecules` list
    instead of `molecules`."""

    def __init__(self, project: ProjectModel, macromolecule: MacromoleculeModel) -> None:
        super().__init__(f"Import macromolecule '{macromolecule.display_name}'")
        self._project = project
        self._macromolecule = macromolecule

    def redo(self) -> None:
        self._project.macromolecules.append(self._macromolecule)
        self._project.record_history(f"Imported macromolecule {self._macromolecule.uuid}")

    def undo(self) -> None:
        self._project.macromolecules.remove(self._macromolecule)
        self._project.record_history(f"Removed macromolecule {self._macromolecule.uuid}")
