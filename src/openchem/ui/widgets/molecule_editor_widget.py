from __future__ import annotations

from PySide6.QtCore import Signal

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.chem import electron_overlay
from openchem.chem.engine import ChemistryEngine
from openchem.chem.stereochemistry import StereochemistryConflict
from openchem.commands.conformer_commands import RotateStructureCommand
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

    #: One atom, when the user selects exactly one on the 2D canvas.
    atom_selected = Signal(int)
    atom_context_menu = Signal(int, int, int)
    #: One bond, likewise. Ketcher reports both through the same event.
    bond_selected = Signal(int)
    #: The user pressed one of the engine's own controls that this
    #: application already provides. Forwarded so the window can answer
    #: it -- see `EditorBackend.editor_action_requested`.
    editor_action_requested = Signal(str)
    #: The user asked to rotate a molecule with no 3D geometry.
    #: The window answers it, because generating one is a chemical
    #: operation and this widget owns no chemistry.
    geometry_requested = Signal()
    #: What the electron overlay has to say out loud, or "" when the dots
    #: speak for themselves. Carries a REFUSAL or a "no lone pairs", both
    #: of which draw nothing and would otherwise be indistinguishable.
    electron_status = Signal(str)

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
        #: "off", "pairs", or "lewis". Off by default: an annotation
        #: nobody asked for is one more thing on a crowded canvas.
        self._electron_mode = "off"
        #: Whether (R)/(S) and (E)/(Z) are shown. Off by default, same
        #: reasoning. Lives here rather than in the window so the labels are
        #: recomputed whenever the structure changes -- see
        #: `_refresh_annotations`.
        self._cip_labels = False

        # **A MODE, and an unmistakable one.** It steals the drag
        # gesture, so the user must never be in doubt about whether a drag
        # will draw a bond or turn the molecule. The bar appears only
        # while the mode is on.
        self._rotate_button = QPushButton("Rotate 3D", self)
        self._rotate_button.setCheckable(True)
        self._rotate_button.setToolTip(
            "Turn the structure in three dimensions and draw the result.\n"
            "While this is on, dragging rotates instead of drawing."
        )
        self._rotate_button.toggled.connect(self._on_rotate_toggled)
        self._rotate_readout = QLabel("", self)
        self._rotate_cancel = QPushButton("Cancel", self)
        self._rotate_cancel.clicked.connect(self._cancel_rotation)
        for widget in (self._rotate_readout, self._rotate_cancel):
            widget.setVisible(False)

        rotate_bar = QHBoxLayout()
        rotate_bar.setContentsMargins(4, 2, 4, 2)
        rotate_bar.addWidget(self._rotate_button)
        rotate_bar.addWidget(self._rotate_readout)
        rotate_bar.addStretch()
        rotate_bar.addWidget(self._rotate_cancel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(rotate_bar)
        layout.addWidget(self._backend.widget())

        self._backend.edited.connect(self._on_editor_edited)
        # Straight through: the widget adds nothing to an atom index,
        # and a consumer should not have to reach for the backend.
        self._backend.atom_selected.connect(self.atom_selected)
        self._backend.atom_context_menu.connect(self.atom_context_menu)
        self._backend.bond_selected.connect(self.bond_selected)
        self._backend.editor_action_requested.connect(self.editor_action_requested)
        # The canvas has to follow changes it did not make. Undo is the one
        # that matters: `EditStructureCommand` reverts the model and
        # publishes `MoleculeChanged`, and nothing was listening -- so
        # pasting a structure and pressing Ctrl+Z emptied the molecule while
        # the editor went on drawing it. Confirmed live: after an undo the
        # Properties panel read mol_wt 0 with a blank formula and aspirin
        # was still on screen.
        self._backend.rotation_angles_changed.connect(self._on_rotation_angles)
        self._backend.rotation_finished.connect(self._on_rotation_finished)
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
        # The CHEMISTRY tier: a different structure means different
        # counts, and the page cannot work them out for itself. Done here
        # rather than at each call site so that every route into a new
        # structure -- selection, undo, adopt, rotate -- refreshes the
        # annotations without having to remember to.
        self._refresh_annotations()

    def set_render_option(self, name: str, value: object) -> None:
        """Proxies to the underlying EditorBackend's own display option
        (e.g. Ketcher's `showHydrogenLabels`) -- lets MainWindow's View
        menu reach a capability Ketcher already has, without MainWindow
        reaching past this widget into `_backend` directly."""
        self._backend.set_render_option(name, value)

    def set_atom_tool(self, symbol: str, mass_number: int | None = None) -> None:
        """Arm the canvas to draw `symbol` on the next click -- what the
        application's periodic table does with a chosen element, and with
        a chosen isotope. See `EditorBackend.set_atom_tool` for why it
        arms rather than places."""
        self._backend.set_atom_tool(symbol, mass_number)

    def open_atom_editor(self, atom_index: int) -> None:
        """Ketcher's own atom dialog, offered from our context menu."""
        self._backend.open_atom_editor(atom_index)

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
            # What the canvas was known to be showing BEFORE this edit --
            # read now, because the push below overwrites it.
            was = self._synced_smiles
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
            # AFTER the push, and the ordering is load-bearing. The command
            # is what makes the model authoritative; the lone-pair counts
            # are keyed on MOLFILE POSITION, so refreshing before it would
            # compute them from the previous structure and put the dots on
            # the wrong atoms -- the exact failure this call exists to fix.
            self._refresh_annotations(structure_changed=self._synced_smiles != was)

        self._backend.get_molblock(apply)

    # --- calculated annotations ---------------------------------------------
    #
    # The class of display this application did not have, and the source of
    # two bugs. A CALCULATED ANNOTATION derives from the current molecular
    # graph and is drawn attached to it -- lone pairs, CIP descriptors -- so
    # unlike one of Ketcher's render options it cannot re-derive itself when
    # the structure changes. Something has to recompute it, and that
    # something is here.
    #
    # THE CONTRACT: every route that makes a new authoritative
    # `MoleculeModel` structure ends in `set_molecule` -- selection, undo,
    # redo, paste, a quick fix, adopting a conformer, committing a rotation,
    # aromatize, explicit hydrogens -- because all of them publish
    # `MoleculeChanged` and `_on_molecule_changed` reloads. The one route
    # that does NOT is the user drawing on the canvas, which is why
    # `_on_editor_edited` calls this itself.
    #
    # The two paths deliberately do not converge any further than this.
    # `set_molecule` also reloads the canvas, and doing that on the user's
    # own edit would pull the drawing out from under them mid-structure --
    # far worse than the bug it would fix, as `_on_molecule_changed` records.

    def _refresh_annotations(self, structure_changed: bool = True) -> None:
        """Recompute what is drawn ON the structure, when the structure moved.

        **TIERED, and the tiering is the point rather than an
        optimisation.** `_publish_electron_overlay` runs a `LewisAnalysis`,
        and the page's own three tiers (chemistry / positions / viewport)
        exist so that a pan does not re-measure a label. A coordinate-only
        change -- Layout, Clean Up, dragging an atom -- moves no chemistry,
        and the page already repositions the dots for it from the struct it
        has. Recomputing here as well would make this "every change
        recalculates everything", which is what those tiers were built to
        prevent.

        `structure_changed` defaults to True because that is what every
        caller except the canvas-edit path means: `set_molecule` is handed a
        different molecule.
        """
        if not structure_changed:
            return
        self._publish_electron_overlay()
        if self._cip_labels:
            self._backend.set_cip_labels(True)

    def set_cip_labels(self, on: bool) -> None:
        """Show CIP stereo descriptors on the canvas, or take them off.

        **The MODE lives here rather than in the window**, exactly as
        `set_electron_mode`'s does and for the same reason: the labels are
        then recomputed whenever the molecule changes without every caller
        having to remember to. The window only ever says which state it
        wants.

        Turning it ON recomputes rather than resurrecting: the backend's
        refresh clears the old descriptors before writing the new ones, so
        a centre that stopped being a stereocentre while the display was off
        does not come back wearing its old label.
        """
        self._cip_labels = on
        self._backend.set_cip_labels(on)

    def cip_labels(self) -> bool:
        return self._cip_labels

    # --- the electron overlay -----------------------------------------------

    def set_electron_mode(self, mode: str) -> None:
        """Show lone pairs on the canvas, or take them off with "off".

        **The MODE lives here rather than in the window**, so that the
        payload is rebuilt whenever the molecule changes without every
        caller having to remember to. `set_molecule` republishes; the
        window only ever says which mode it wants.
        """
        self._electron_mode = mode
        self._publish_electron_overlay()

    def electron_mode(self) -> str:
        return self._electron_mode

    def _publish_electron_overlay(self) -> None:
        """Recompute the counts and hand them over. The CHEMISTRY tier.

        Reached only when the mode changes or the structure does -- never
        on a pan, a zoom or a rotation frame, which the page answers from
        what it already has. `LewisAnalysis` on every frame would be
        absurd, and the page has no way to know it should not ask.
        """
        if self._electron_mode == "off" or self._molecule is None:
            self._backend.set_electron_overlay(None)
            self.electron_status.emit("")
            return
        overlay = electron_overlay.for_molblock(self._molecule.molblock)
        payload = overlay.to_payload()
        payload["mode"] = self._electron_mode
        self._backend.set_electron_overlay(payload)
        self.electron_status.emit(overlay.status_message())

    # --- 3D rotation mode ---------------------------------------------------

    def has_geometry(self) -> bool:
        """Does the drawing on the canvas carry real 3D coordinates?

        Public because the window has to answer `geometry_requested` and
        then decide whether the answer worked. Without it the obvious
        implementation -- "put a geometry in, then turn the mode back on"
        -- loops forever whenever putting one in fails.
        """
        return self._molecule is not None and _has_3d(self._molecule)

    def begin_rotation(self) -> None:
        """Enter the mode from outside, as if the button had been pressed.

        Through the button rather than past it, so the checked state, the
        bar and the page all follow exactly as they do for a click. A
        caller that has just supplied a geometry uses this; one that has
        not will simply be asked for one again, which is the same
        behaviour as the button.
        """
        self._rotate_button.setChecked(True)

    def _on_rotate_toggled(self, on: bool) -> None:
        """Enter or leave the mode.

        **Entering mutates nothing.** The page snapshots the geometry and
        rotates a copy, so toggling on and straight off again leaves the
        structure byte-identical -- which is what makes a mode you tried
        out of curiosity safe.
        """
        for widget in (self._rotate_readout, self._rotate_cancel):
            widget.setVisible(on)
        if not on:
            return
        if self._molecule is None or not self._molecule.molblock:
            self._rotate_button.setChecked(False)
            return
        if not _has_3d(self._molecule):
            # **ROTATING A FLAT DRAWING IS NOT ROTATION.** With every z at
            # zero, turning about the vertical axis only squashes the
            # picture -- so the mode asks for a geometry rather than
            # pretending it has one. Entering has still mutated nothing:
            # the window offers, and waits for an answer.
            self._rotate_button.setChecked(False)
            self.geometry_requested.emit()
            return
        self._rotate_readout.setText("X 0\u00b0   Y 0\u00b0")
        if not self._backend.start_rotation():
            # The editor could not enter -- its page is still loading, or
            # it is a backend with no rotation at all. **The button comes
            # back up rather than claiming a mode nothing is in.** A
            # banner and a live readout over a canvas where dragging still
            # draws bonds is the failure this whole line of work keeps
            # finding: a control that says it did something it did not.
            self._rotate_button.setChecked(False)

    def _on_rotation_angles(self, x_degrees: float, y_degrees: float) -> None:
        self._rotate_readout.setText(f"X {x_degrees:.0f}\u00b0   Y {y_degrees:.0f}\u00b0")

    def _cancel_rotation(self, _checked: bool = False) -> None:
        """Leave the mode, putting the entry geometry back.

        Zero undo steps: the preview was never an edit. A conformer
        generated on the way in stays -- cancelling a rotation must not
        delete a legitimate structure.
        """
        self._backend.end_rotation(restore=True)
        self._rotate_button.setChecked(False)

    def _on_rotation_finished(self) -> None:
        """A drag ended: read the structure back and commit it once."""
        if self._molecule is None:
            return
        self._backend.get_molblock(self._commit_rotation)

    def _commit_rotation(self, molblock: str | None) -> None:
        if not molblock or self._molecule is None:
            return
        try:
            command = RotateStructureCommand(
                self._engine,
                self._molecule,
                molblock,
                self._event_bus,
                on_applied=self.set_molecule,
            )
        except StereochemistryConflict as exc:
            QMessageBox.warning(self, "Rotate 3D", str(exc))
            self._cancel_rotation()
            return
        if not command.moved:
            # A zero-distance drag. Nothing moved, so nothing is pushed --
            # an undo entry that restores what is already there is worse
            # than no entry at all.
            #
            # **ASKED OF THE COMMAND, NOT OF THE TEXT.** The obvious
            # version of this compares the incoming molblock with the
            # model's, and is never true: the editor's copy is at
            # Ketcher's own scale (measured x0.6994), so the two strings
            # differ on every drag including the ones that moved nothing.
            # The command has restored the scale and can answer on the
            # geometry; this widget may not import RDKit and could not.
            return
        self._applying_own_edit = True
        try:
            self._undo_stack.push(command)
        finally:
            self._applying_own_edit = False


def _has_3d(molecule) -> bool:
    """Does this molecule's drawing carry real 3D coordinates?

    Read off the molblock's z column rather than through RDKit, because
    `ui/` may not import it (`tests/test_layering.py`).
    """
    lines = (molecule.molblock or "").splitlines()
    if len(lines) < 5:
        return False
    try:
        count = int(lines[3][:3])
    except ValueError:
        return False
    try:
        zs = [float(lines[4 + i][20:30]) for i in range(count)]
    except (IndexError, ValueError):
        return False
    return max(zs) - min(zs) > 0.01
