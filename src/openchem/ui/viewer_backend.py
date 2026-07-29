from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget


class ViewerBackend(QObject):
    """Interface for a 3D structure-viewer widget's underlying engine.

    `Mol3DViewerBackend` (3Dmol.js) is the only implementation today; a
    future macromolecule/crystallography-oriented backend (e.g. Mol*) can be
    added as a sibling implementation without touching chemistry, services,
    or commands — same shape as `EditorBackend` for the 2D editor.

    Plain QObject rather than QObject+ABC: PySide6's QObject metaclass
    conflicts with ABCMeta, so "abstract" here means NotImplementedError,
    enforced by convention rather than by the type system.
    """

    atoms_selected = Signal(list)  # list[int] atom indices, for measurement tools

    def load_conformer(self, molblock: str) -> None:
        """Render a 3D conformer (a molblock carrying 3D coordinates)."""
        raise NotImplementedError

    def set_style(self, style: str) -> None:
        """Set the render style: 'stick', 'sphere', 'line', or 'ballstick'."""
        raise NotImplementedError

    def clear(self) -> None:
        """Clear the current view."""
        raise NotImplementedError

    def widget(self) -> QWidget:
        """Return the underlying QWidget to embed in the host window."""
        raise NotImplementedError
