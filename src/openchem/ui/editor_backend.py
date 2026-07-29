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

    def load_molblock(self, molblock: str) -> None:
        """Load a structure (as a V2000/V3000 molblock) into the editor."""
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
