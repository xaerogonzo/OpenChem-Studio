from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut, QUndoStack
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QMenu, QVBoxLayout, QWidget

from openchem.chem.identifiers import identifier_for_molblock
from openchem.commands.molecule_commands import DeleteMoleculeCommand, RenameMoleculeCommand
from openchem.domain.molecule import MoleculeModel
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

    def __init__(
        self,
        event_bus: EventBus,
        undo_stack: QUndoStack,
        parent: QWidget | None = None,
        on_duplicate: Callable[[MoleculeModel], None] | None = None,
        on_identify: Callable[[MoleculeModel], None] | None = None,
        on_check: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._event_bus = event_bus
        self._undo_stack = undo_stack
        self._on_duplicate = on_duplicate
        self._on_identify = on_identify
        self._on_check = on_check
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
        # Falls back to the selected row when the click misses one. With a
        # narrow dock holding a couple of entries most of the panel is
        # empty space, and a menu that silently does not appear reads as
        # "this panel has no context menu" rather than "aim at a row" --
        # which is exactly how it was reported.
        item = self._list.itemAt(pos) or self._list.currentItem()
        if item is None:
            return
        menu = QMenu(self._list)
        # Identifiers first: this is the most frequent reason to
        # right-click a molecule, and -- since most structures have no
        # verified IUPAC name (see benchmarks/naming) -- a SMILES or an
        # InChIKey is often the only way to refer to one at all.
        copy_smiles_action = menu.addAction("Copy SMILES")
        copy_inchi_action = menu.addAction("Copy InChI")
        copy_key_action = menu.addAction("Copy InChIKey")
        copy_molfile_action = menu.addAction("Copy Molfile")
        menu.addSeparator()
        # Duplicating needs the ChemistryEngine to rebuild the identifiers
        # on the copy, which this panel deliberately does not hold (UI
        # never imports chem engines -- tests/test_layering.py). So it is a
        # callback into MainWindow, the same shape PropertyPanel already
        # uses for `on_add_structure`.
        duplicate_action = menu.addAction("Duplicate") if self._on_duplicate else None
        identify_action = menu.addAction("Identify Online...") if self._on_identify else None
        # Same redundancy as Copy SMILES: the Structure menu is how you
        # find out this exists, the right-click is how you use it after
        # that. Reported as missing once already when it lived in only one
        # of the two places.
        check_action = menu.addAction("Check Structure...") if self._on_check else None
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        chosen = menu.exec(self._list.mapToGlobal(pos))
        if chosen is not None and chosen is check_action:
            self._on_check()
            return
        if chosen is copy_smiles_action:
            self._copy_identifier(item, "smiles")
        elif chosen is copy_inchi_action:
            self._copy_identifier(item, "inchi")
        elif chosen is copy_key_action:
            self._copy_identifier(item, "inchikey")
        elif chosen is copy_molfile_action:
            molecule = self._molecule_for_item(item)
            if molecule is not None and molecule.molblock:
                QGuiApplication.clipboard().setText(molecule.molblock)
        elif duplicate_action is not None and chosen is duplicate_action:
            molecule = self._molecule_for_item(item)
            if molecule is not None:
                self._on_duplicate(molecule)
        elif identify_action is not None and chosen is identify_action:
            molecule = self._molecule_for_item(item)
            if molecule is not None:
                self._on_identify(molecule)
        elif chosen is rename_action:
            self._list.editItem(item)
        elif chosen is delete_action:
            self._delete_item(item)

    def _copy_identifier(self, item: QListWidgetItem, kind: str) -> None:
        """Put one identifier for `item`'s molecule on the clipboard.

        Silent on failure by design: a molecule with no parseable
        structure has no identifier to copy, and a modal complaint on a
        right-click menu action would be more disruptive than the empty
        clipboard the user will notice immediately.
        """
        molecule = self._molecule_for_item(item)
        if molecule is None:
            return
        text = identifier_for_molblock(molecule.molblock, kind)
        if text:
            QGuiApplication.clipboard().setText(text)

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
