from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import MoleculeChanged, MoleculeSelected


class ProjectExplorerPanel(QWidget):
    """Lists the active project's molecules. Selecting one publishes MoleculeSelected."""

    def __init__(self, event_bus: EventBus, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._event_bus = event_bus
        self._project: ProjectModel | None = None

        self._list = QListWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._list)

        self._list.currentItemChanged.connect(self._on_selection_changed)
        event_bus.subscribe(MoleculeChanged, self._on_molecule_changed)

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self.refresh()

    def refresh(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        if self._project is not None:
            for molecule in self._project.molecules:
                item = QListWidgetItem(molecule.display_name)
                item.setData(Qt.ItemDataRole.UserRole, molecule.uuid)
                self._list.addItem(item)
        self._list.blockSignals(False)

    def _on_selection_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        molecule_uuid = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self._event_bus.publish(MoleculeSelected(molecule_uuid=molecule_uuid))

    def _on_molecule_changed(self, event: MoleculeChanged) -> None:
        self.refresh()
