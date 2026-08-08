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
    #: One bond picked on the canvas. Ketcher reports this through the same
    #: `selectionChange` event as atoms; a backend that cannot report bonds
    #: simply never emits it.
    bond_selected = Signal(int)

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
