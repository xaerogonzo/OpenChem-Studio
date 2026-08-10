from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from openchem.ui.visualization import AnyVisualizationLayer, VisualizationLayer


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

    def load_conformer(self, molblock: str, structure_key: object = None) -> None:
        """Render a 3D conformer (a molblock carrying 3D coordinates).

        `structure_key` identifies what is on screen for the viewer
        SESSION, so a backend that can keep its camera knows whether this
        structure belongs with the last one -- two conformers of one
        molecule share a key. Optional and defaulting to None, which means
        "treat this as new", because a backend is free to ignore it and
        most callers have no opinion.
        """
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
        """Apply a single visualization layer (atom colors — see
        `ui/visualization.py`), or clear the active one if `layer` is
        `None`. Optional capability, same reasoning as
        `load_macromolecule` above.

        Retained as the single-layer convenience over
        `apply_visualizations` below, since the great majority of callers
        (the Calculator Inspector, every per-atom property) show exactly
        one layer and reading `apply_visualization(layer)` at those call
        sites is clearer than `apply_visualizations([layer])`.
        """
        self.apply_visualizations([layer] if layer is not None else [])

    def apply_visualizations(self, layers: list[AnyVisualizationLayer]) -> None:
        """Apply several visualization layers at once, compositing in
        order so later layers win where they overlap (Phase 23). An empty
        list clears.

        Layers may target different things -- atoms (`VisualizationLayer`)
        or whole residues (`ResidueColorLayer`). A backend renders the
        target kinds it can and IGNORES the rest rather than raising:
        3Dmol.js has no residue concept for a small-molecule conformer,
        and a macromolecule viewer has no per-atom scientific data, so
        refusing an unrenderable layer would force every caller to know
        which backend it happens to be talking to.
        """
        raise NotImplementedError

    def apply_surface(self, layer) -> None:
        """Apply a molecular surface coloured by a scalar field, or clear
        the active one if `layer` is None.

        Optional capability, declared here rather than only on
        `Mol3DViewerBackend` for the reason `load_macromolecule` gives
        above: this base is where an optional viewer capability is meant
        to be announced, so a caller can see what a backend may be asked
        for without reading each implementation. Mol* does not implement
        it -- a volumetric field over a whole receptor is a different
        problem from one over a small molecule.
        """
        raise NotImplementedError
