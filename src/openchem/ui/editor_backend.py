from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget


class EditorBackend(QObject):
    """Interface for a 2D structure-editor widget's underlying engine.

    `KetcherEditorBackend` is the only implementation today, but nothing
    outside `ui/widgets/` should assume Ketcher specifically — a future
    implementation (Kekule.js, ChemDoodle, a native canvas) can swap in here
    without touching chemistry or command code.

    Plain QObject rather than QObject+ABC: PySide6's QObject metaclass
    conflicts with ABCMeta, so "abstract" here means NotImplementedError,
    enforced by convention rather than by the type system.
    """

    edited = Signal()  # emitted whenever the user changes the structure
    #: One atom index, when the user selects exactly one atom on the canvas.
    #: Declared on the INTERFACE rather than on the Ketcher subclass because
    #: "which atom is selected" is a property of a 2D editor, not of this
    #: particular engine -- a replacement backend owes the same signal.
    #: A backend whose engine cannot report selection simply never emits it.
    atom_selected = Signal(int)
    #: A right-click ON an atom, as a molfile position plus the cursor.
    #: A backend with no such gesture simply never emits it.
    atom_context_menu = Signal(int, int, int)
    #: One bond picked on the canvas. Ketcher reports this through the same
    #: `selectionChange` event as atoms; a backend that cannot report bonds
    #: simply never emits it.
    bond_selected = Signal(int)
    #: The user pressed a control on the editor's OWN toolbar that this
    #: application already provides, and the application should answer it.
    #:
    #: Carries a short action name -- "periodic_table", "import",
    #: "export", "about", "help", "settings", "viewer_3d", "undo",
    #: "redo" -- rather than one signal per control. Nine signals whose
    #: only difference is a name is the shape this whole line of work is
    #: removing, and the receiving end is a dict either way.
    #:
    #: On the INTERFACE because "the user wants the thing this
    #: application already has" is a property of an embedded editor, not
    #: of one engine. A backend with no such controls never emits it, and
    #: every one of these is still reachable from the menus.
    editor_action_requested = Signal(str)
    #: Live drag angles while 3D rotation mode is on, in degrees about the
    #: screen's horizontal and vertical axes. Absolute from the moment the
    #: mode was entered, so re-entering reads 0, 0.
    rotation_angles_changed = Signal(float, float)
    #: A drag ended. The host then reads the structure back and commits it
    #: as ONE undoable step -- the preview itself is not undoable and does
    #: not touch Ketcher's own history.
    rotation_finished = Signal()

    def load_molblock(self, molblock: str) -> None:
        """Load a structure (as a V2000/V3000 molblock) into the editor."""
        raise NotImplementedError

    def clear(self) -> None:
        """Empty the editor's canvas entirely.

        Default implementation delegates to `load_molblock("")`, which
        `KetcherEditorBackend` already handles safely (calls
        `window.ketcher.setMolecule("")`) -- a subclass only needs to
        override this if an empty molblock isn't a safe "clear" signal for
        its underlying engine.
        """
        self.load_molblock("")

    def set_render_option(self, name: str, value: object) -> None:
        """Set one of the underlying editor's own rendering/display options
        (e.g. whether to show explicit hydrogen labels) -- optional
        capability, not every backend has a settable-options surface.
        Fire-and-forget, same as `load_molblock`: no confirmation, the
        backend is expected to apply it immediately.

        A backend that is not yet ready must QUEUE this and replay it, as
        `load_molblock` does -- an option is durable state, and dropping it
        leaves the caller's own UI (a checked menu item) claiming something
        the canvas is not doing, with nothing on screen to say which is
        real. An option set twice before ready is one option: apply the
        last value once.
        """
        raise NotImplementedError

    def set_electron_overlay(self, payload: dict | None) -> None:
        """Show lone pairs on the canvas, or take them off with `None`.

        **STATE, so it must be QUEUED until the editor is ready** -- the
        deliberate opposite of `start_rotation`. A dropped payload leaves
        the View menu claiming an electron display the canvas is not
        showing, with nothing on screen to say which is real; a replayed
        one merely draws the dots a moment late, which is what the user
        asked for. Same reasoning as `set_render_option`, and the same
        reason `trigger_toolbar_action` goes the other way.

        Only the LAST payload matters: it describes the current molecule,
        so an older one is not a lost instruction but a stale fact.

        Concrete and a no-op by default, like `start_rotation`: an editor
        that cannot draw an overlay is not broken, and forcing every test
        double to declare that would be noise.
        """

    def set_cip_labels(self, on: bool) -> None:
        """Show CIP stereo descriptors -- (R)/(S), (E)/(Z) -- or take them off.

        **CALCULATED ANNOTATION STATE**, which is the category this
        application did not have and both of its stale-annotation bugs came
        from. It is not a render option (the editor cannot derive it from a
        flag) and it is not a structural edit (the molecule is untouched):
        it is a value derived from the current molecular graph and drawn
        attached to it, so it must be RECOMPUTED whenever that graph
        changes. Reported as "if a molecule is changed while the label is
        turned on, it won't update".

        STATE, so a backend that is not ready must QUEUE this, for the same
        reason as `set_render_option` and `set_electron_overlay`: a dropped
        request leaves a checked menu item claiming something the canvas is
        not showing. Only the LAST request matters -- on then off before the
        page boots is off, not a pair of instructions.

        Concrete and a no-op by default, like `set_electron_overlay`: an
        editor with no descriptor display is not broken.
        """

    def start_rotation(self) -> bool:
        """Enter 3D rotation mode, if this editor has one.

        **Returns whether the mode really started**, and the default is
        `False` because an editor that cannot rotate has not entered
        anything. A caller that ignored this would show a banner, a
        Cancel button and a live readout over a canvas where dragging
        still draws bonds -- a control claiming something the editor is
        not doing, with nothing on screen to say which is real.

        A GESTURE, not state, so an implementation that is not ready must
        answer `False` rather than queue it -- same as
        `trigger_toolbar_action` and the deliberate opposite of
        `set_render_option`. Replayed on ready, it would put the user in
        a mode they asked for seconds ago, over whatever structure loaded
        in the meantime.
        """
        return False

    def end_rotation(self, restore: bool) -> None:
        """Leave 3D rotation mode, optionally restoring the entry geometry.

        Safe to call when the mode never started -- leaving is how a
        refusal and a cancel both unwind, and neither should have to know
        whether entering worked.
        """

    def set_atom_tool(self, symbol: str, mass_number: int | None = None) -> None:
        """Arm the editor to draw `symbol` on the next canvas click.

        `mass_number` labels what gets placed, so picking C-13 in the
        periodic table and clicking the canvas deposits carbon-13 rather
        than carbon. **Reported as "I can place carbon 13, but it's just
        CH4, there's no 13"** -- and the cause was not rendering, which
        works: this method armed a BARE element and the mass number was
        never part of the gesture at all.

        The same gesture the engine's own periodic table performs -- pick
        an element, then click where it goes -- exposed so the
        application's periodic table can drive the canvas instead of the
        engine needing a second table of its own.

        A GESTURE, not state, so a backend that is not ready must DROP it
        rather than queue it, exactly as `trigger_toolbar_action` does:
        replayed later it would arm a tool the user asked for seconds ago
        and has since moved on from, and the next click anywhere on the
        canvas would deposit an atom they did not ask for.
        """
        raise NotImplementedError

    def open_atom_editor(self, atom_index: int) -> None:
        """Open the editor's own atom-properties dialog, if it has one.

        A no-op by default: a backend without such a dialog has nothing to
        open, and that is a correct answer rather than a failure -- the
        same reasoning as `ViewerBackend`'s shape methods.
        """

    def trigger_toolbar_action(self, action_id: str) -> None:
        """Trigger one of the underlying editor's own built-in toolbar
        actions (e.g. "add/remove explicit hydrogens", "open the 3D
        viewer") by an implementation-defined id -- optional capability,
        not every backend has actions worth exposing this way. Structure-
        mutating actions triggered this way still end up going through the
        normal `edited` signal -> EditStructureCommand path, same as any
        other in-canvas edit.

        A backend that is not yet ready should DROP this rather than queue
        it -- the deliberate opposite of `set_render_option` above. An
        action is a transient gesture, and replaying one performs it
        against whatever structure loaded in the meantime, which is not
        the one the user was looking at when they asked.
        """
        raise NotImplementedError

    def get_molblock(self, callback: Callable[[str | None], None]) -> None:
        """Asynchronously fetch the current structure as a molblock.

        Async because the concrete backend (a web view) may need to
        round-trip through JavaScript; `callback(molblock)` is invoked when
        ready, with `None` if no structure is loaded.
        """
        raise NotImplementedError

    def widget(self) -> QWidget:
        """Return the underlying QWidget to embed in the host window."""
        raise NotImplementedError
