from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QUndoStack
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QMenu, QVBoxLayout, QWidget

from openchem.commands.molecule_commands import DeleteMoleculeCommand, RenameMoleculeCommand
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import MoleculeChanged, MoleculeSelected


class ProjectExplorerPanel(QWidget):
    """Lists the active project's molecules. Selecting one publishes MoleculeSelected.

    Delete (context menu or the Delete key) and rename (double-click or
    context menu) both go through `DeleteMoleculeCommand`/
    `RenameMoleculeCommand` on the shared undo stack -- `DeleteMoleculeCommand`
    already existed (used nowhere until this panel wired it up);
    `RenameMoleculeCommand` is new, same shape.
    """

    def __init__(self, event_bus: EventBus, undo_stack: QUndoStack, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._event_bus = event_bus
        self._undo_stack = undo_stack
        self._project: ProjectModel | None = None
        # Set while `refresh()` is rebuilding `_list` -- guards `_on_item_changed`
        # against firing a rename command for edits that aren't user-initiated
        # (blockSignals around refresh already covers item creation, but not
        # a rename commit that lands mid-refresh from a stale editor).
        self._refreshing = False

        self._list = QListWidget(self)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._list)

        self._list.currentItemChanged.connect(self._on_selection_changed)
        self._list.customContextMenuRequested.connect(self._on_context_menu_requested)
        self._list.itemChanged.connect(self._on_item_changed)
        QShortcut(QKeySequence.StandardKey.Delete, self._list, self._delete_selected).setContext(
            Qt.ShortcutContext.WidgetShortcut
        )
        event_bus.subscribe(MoleculeChanged, self._on_molecule_changed)

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self.refresh()

    def refresh(self) -> None:
        self._refreshing = True
        self._list.blockSignals(True)
        self._list.clear()
        if self._project is not None:
            for molecule in self._project.molecules:
                item = QListWidgetItem(molecule.display_name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, molecule.uuid)
                self._list.addItem(item)
        self._list.blockSignals(False)
        self._refreshing = False

    def _on_selection_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        molecule_uuid = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self._event_bus.publish(MoleculeSelected(molecule_uuid=molecule_uuid))

    def _on_molecule_changed(self, event: MoleculeChanged) -> None:
        self.refresh()

    def _molecule_for_item(self, item: QListWidgetItem):
        if self._project is None:
            return None
        return self._project.find_molecule(item.data(Qt.ItemDataRole.UserRole))

    def _on_context_menu_requested(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self._list)
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        chosen = menu.exec(self._list.mapToGlobal(pos))
        if chosen is rename_action:
            self._list.editItem(item)
        elif chosen is delete_action:
            self._delete_item(item)

    def _delete_selected(self) -> None:
        item = self._list.currentItem()
        if item is not None:
            self._delete_item(item)

    def _delete_item(self, item: QListWidgetItem) -> None:
        molecule = self._molecule_for_item(item)
        if molecule is None or self._project is None:
            return
        self._undo_stack.push(DeleteMoleculeCommand(self._project, molecule, self._event_bus))

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._refreshing:
            return
        molecule = self._molecule_for_item(item)
        if molecule is None:
            return
        new_name = item.text().strip()
        if not new_name or new_name == molecule.display_name:
            # Empty/unchanged edit -- restore the displayed text instead of
            # pushing a no-op (or blank-name) rename command.
            self.refresh()
            return
        self._undo_stack.push(RenameMoleculeCommand(molecule, new_name, self._event_bus))
