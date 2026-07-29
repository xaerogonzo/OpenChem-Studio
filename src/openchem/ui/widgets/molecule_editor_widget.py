from __future__ import annotations

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QVBoxLayout, QWidget

from openchem.chem.engine import ChemistryEngine
from openchem.commands.molecule_commands import EditStructureCommand
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.ui.editor_backend import EditorBackend
from openchem.ui.widgets.ketcher_editor_backend import KetcherEditorBackend


class MoleculeEditorWidget(QWidget):
    """Hosts an EditorBackend (Ketcher today) for the session's active molecule.

    Never touches RDKit directly: a structure edit is pushed as an
    EditStructureCommand onto the shared QUndoStack, which is the only thing
    that mutates MoleculeModel.
    """

    def __init__(
        self,
        engine: ChemistryEngine,
        event_bus: EventBus,
        undo_stack: QUndoStack,
        backend: EditorBackend | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._event_bus = event_bus
        self._undo_stack = undo_stack
        self._backend: EditorBackend = backend or KetcherEditorBackend(self)
        self._molecule: MoleculeModel | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._backend.widget())

        self._backend.edited.connect(self._on_editor_edited)

    def set_molecule(self, molecule: MoleculeModel | None) -> None:
        self._molecule = molecule
        if molecule is not None and molecule.molblock:
            self._backend.load_molblock(molecule.molblock)
        else:
            # No molecule selected, or a freshly-created one with no
            # structure yet -- clear the canvas instead of silently leaving
            # whatever the previous molecule (or an orphaned pre-selection
            # drawing) left on screen.
            self._backend.clear()

    def _on_editor_edited(self) -> None:
        if self._molecule is None:
            return

        def apply(molblock: str | None) -> None:
            if not molblock or self._molecule is None:
                return
            command = EditStructureCommand(self._engine, self._molecule, molblock, self._event_bus)
            self._undo_stack.push(command)

        self._backend.get_molblock(apply)
