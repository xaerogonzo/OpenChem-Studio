from __future__ import annotations

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QVBoxLayout, QWidget

from openchem.chem.engine import ChemistryEngine
from openchem.commands.molecule_commands import EditStructureCommand
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import MoleculeChanged
from openchem.ui.editor_backend import EditorBackend
from openchem.ui.widgets.ketcher_editor_backend import KetcherEditorBackend


class MoleculeEditorWidget(QWidget):
    """Hosts an EditorBackend (Ketcher today) for the session's active molecule.

    Never touches RDKit directly: a structure edit is pushed as an
    EditStructureCommand onto the shared QUndoStack, which is the only thing
    that mutates MoleculeModel.

    Ketcher's own toolbar already has a real, working 3D view (its "3D
    Viewer" button opens an embedded Miew dialog that rotates the current
    structure and can bake a 3D-informed stereo edit back into the 2D
    structure via Apply) and a real "Add/Remove explicit hydrogens" action
    -- an earlier pass here built a second, read-only 3D pane inside this
    widget on the mistaken assumption that Ketcher's own 3D view wasn't
    wired up in this vendored build. It was: confirmed live via
    `data-testid="3D Viewer button"`, which the initial audit missed
    because that button has no accessible name, only a `title`/`data-testid`.
    That duplicate pane was removed (MainWindow.set_render_option-driven
    View-menu actions call Ketcher's OWN buttons instead -- see
    KetcherEditorBackend.trigger_toolbar_action).
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
        #: The constitution the canvas is known to be showing.
        self._synced_smiles: str | None = None
        #: Set while this widget is pushing its own edit; see
        #: `_on_molecule_changed`.
        self._applying_own_edit = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._backend.widget())

        self._backend.edited.connect(self._on_editor_edited)
        # The canvas has to follow changes it did not make. Undo is the one
        # that matters: `EditStructureCommand` reverts the model and
        # publishes `MoleculeChanged`, and nothing was listening -- so
        # pasting a structure and pressing Ctrl+Z emptied the molecule while
        # the editor went on drawing it. Confirmed live: after an undo the
        # Properties panel read mol_wt 0 with a blank formula and aspirin
        # was still on screen.
        event_bus.subscribe(MoleculeChanged, self._on_molecule_changed)

    def set_molecule(self, molecule: MoleculeModel | None) -> None:
        self._molecule = molecule
        self._synced_smiles = molecule.canonical_smiles if molecule is not None else None
        if molecule is not None and molecule.molblock:
            self._backend.load_molblock(molecule.molblock)
        else:
            # No molecule selected, or a freshly-created one with no
            # structure yet -- clear the canvas instead of silently leaving
            # whatever the previous molecule (or an orphaned pre-selection
            # drawing) left on screen.
            self._backend.clear()

    def set_render_option(self, name: str, value: object) -> None:
        """Proxies to the underlying EditorBackend's own display option
        (e.g. Ketcher's `showHydrogenLabels`) -- lets MainWindow's View
        menu reach a capability Ketcher already has, without MainWindow
        reaching past this widget into `_backend` directly."""
        self._backend.set_render_option(name, value)

    def trigger_toolbar_action(self, test_id: str) -> None:
        """Proxies to one of Ketcher's own real toolbar buttons (e.g. "Add/
        Remove explicit hydrogens", "3D Viewer") by its stable
        `data-testid` -- see KetcherEditorBackend.trigger_toolbar_action
        for why this goes through Ketcher's actual button rather than a
        reimplementation."""
        self._backend.trigger_toolbar_action(test_id)

    def _on_molecule_changed(self, event: MoleculeChanged) -> None:
        """Reload the canvas when the model moved underneath it.

        COMPARED ON CANONICAL SMILES, NOT ON THE MOLBLOCK TEXT.
        `EditStructureCommand` re-canonicalises through the engine, so the
        stored molblock is not textually what the editor handed over even
        when nothing about the structure changed. Comparing the text would
        reload the canvas after every single edit -- pulling the drawing
        out from under someone mid-structure, which is far worse than the
        bug this fixes.

        Comparing constitution means a user's own edit is a no-op here
        (the model now holds what they just drew) while an undo, a redo or
        a paste is a real difference and reloads. Moving an atom without
        changing the structure also correctly does nothing, so a layout
        tweak is never undone by a refresh.
        """
        if self._applying_own_edit:
            # `EditStructureCommand` publishes from inside `push()`, before
            # `_synced_smiles` can be brought up to date, so the comparison
            # below is not yet meaningful. Needed as well as the comparison
            # rather than instead of it: the flag covers delivery DURING
            # the push, the comparison covers delivery after it, and which
            # one happens depends on how the bus is connected.
            return
        if self._molecule is None or event.molecule_uuid != self._molecule.uuid:
            return
        if self._molecule.canonical_smiles == self._synced_smiles:
            return
        self.set_molecule(self._molecule)

    def _on_editor_edited(self) -> None:
        if self._molecule is None:
            return

        def apply(molblock: str | None) -> None:
            if not molblock or self._molecule is None:
                return
            command = EditStructureCommand(self._engine, self._molecule, molblock, self._event_bus)
            self._applying_own_edit = True
            try:
                self._undo_stack.push(command)
            finally:
                # In a finally block: leaving this set would make the
                # canvas permanently deaf to undo, which is the bug this
                # whole path exists to fix.
                self._applying_own_edit = False
            # Recorded AFTER the command runs, so it holds the engine's
            # canonical form rather than the editor's -- which is what
            # `_on_molecule_changed` compares against.
            self._synced_smiles = self._molecule.canonical_smiles

        self._backend.get_molblock(apply)
