from __future__ import annotations

from pathlib import Path

from openchem.commands.base import OpenChemCommand
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import MoleculeChanged
from openchem.services.export_service import ExportService
from openchem.services.import_service import ImportService


class ImportMoleculeCommand(OpenChemCommand):
    def __init__(
        self,
        import_service: ImportService,
        project: ProjectModel,
        path: Path,
        event_bus: EventBus,
    ) -> None:
        super().__init__(f"Import '{path.name}'")
        self._import_service = import_service
        self._project = project
        self._path = path
        self._event_bus = event_bus
        self._imported: list[MoleculeModel] = []

    def redo(self) -> None:
        self._imported = self._import_service.import_file(self._path)
        self._project.molecules.extend(self._imported)
        self._project.record_history(f"Imported {self._path.name}")
        for molecule in self._imported:
            self._event_bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid))

    def undo(self) -> None:
        for molecule in self._imported:
            self._project.molecules.remove(molecule)
            self._event_bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid))
        self._project.record_history(f"Undid import of {self._path.name}")


class ExportMoleculeCommand(OpenChemCommand):
    """Exporting to disk isn't reversible; modeled as a command for uniform
    logging/scripting alongside the undoable commands."""

    def __init__(self, export_service: ExportService, molecule: MoleculeModel, path: Path) -> None:
        super().__init__(f"Export '{molecule.display_name}' to {path.name}")
        self._export_service = export_service
        self._molecule = molecule
        self._path = path

    def redo(self) -> None:
        self._export_service.export_file(self._molecule, self._path)

    def undo(self) -> None:
        pass
