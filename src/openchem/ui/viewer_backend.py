from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from openchem.ui.visualization import VisualizationLayer


class ViewerBackend(QObject):
    """Interface for a 3D structure-viewer widget's underlying engine.

    `Mol3DViewerBackend` (3Dmol.js, small molecules) and
    `MolStarViewerBackend` (Mol*, macromolecules/crystallography) are the
    two implementations today — sibling implementations added without
    touching chemistry, services, or commands, same shape as
    `EditorBackend` for the 2D editor.

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

    def load_macromolecule(self, structure_text: str, source_format: str) -> None:
        """Render a macromolecular structure (`source_format` is `"pdb"` or
        `"mmcif"` — Mol*'s own vocabulary, see `MacromoleculeModel`).

        Optional capability, not implemented by every backend (3Dmol.js
        isn't built for large receptors) — deliberately added to this
        shared base rather than bolted onto `MolStarViewerBackend` alone,
        so a future viewer content type (a docking result, a trajectory)
        has an established place to declare its own optional capability
        method here too, instead of becoming a one-off special case.
        """
        raise NotImplementedError

    def apply_visualization(self, layer: VisualizationLayer | None) -> None:
        """Apply a visualization layer (atom colors today — see
        `ui/visualization.py`), or clear the active one if `layer` is
        `None`. Optional capability, same reasoning as
        `load_macromolecule` above: Mol*'s macromolecule viewer has no
        per-atom scientific data feeding it yet, so this stays here as the
        established place for a future implementer to declare it, not
        implemented unconditionally.
        """
        raise NotImplementedError
