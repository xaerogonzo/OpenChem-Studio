from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.visualization import AnyVisualizationLayer, SurfaceLayer, VisualizationLayer

logger = logging.getLogger("openchem.ui")

_VIEWER_HTML = (
    Path(__file__).resolve().parent.parent.parent / "resources" / "viewer3d" / "viewer.html"
)

# Distinct from None, which is a real queued value meaning "clear the
# surface" -- same sentinel MolStarViewerBackend uses for the same reason.
_NOTHING_PENDING = object()


class _Bridge(QObject):
    """QWebChannel-exposed object. viewer.html's JS calls atomClicked()
    whenever the user clicks an atom in the 3D view."""

    def __init__(self, on_atom_clicked: Callable[[int], None]) -> None:
        super().__init__()
        self._on_atom_clicked = on_atom_clicked

    @Slot(int)
    def atomClicked(self, atom_index: int) -> None:  # noqa: N802 - called from JS by this exact name
        self._on_atom_clicked(atom_index)


class _LoggingPage(QWebEnginePage):
    """Forwards the page's JS console to Python logging."""

    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802 - Qt override
        logger.debug("[viewer3d-js:%s:%d] %s", source, line, message)


class Mol3DViewerBackend(ViewerBackend):
    """The only place in the application that knows 3Dmol.js exists.

    Hosts the vendored resources/viewer3d/viewer.html in a QWebEngineView,
    bridged to Python via QWebChannel for atom-click events. Unlike Ketcher,
    viewer.html has no async post-load init (no WASM worker, no React
    mount) — its script runs synchronously as part of page parsing, so
    `loadFinished` is a reliable "ready" signal here.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        if not _VIEWER_HTML.exists():
            raise FileNotFoundError(f"3D viewer page not found at {_VIEWER_HTML}")
        self._view = QWebEngineView(parent)
        self._page = _LoggingPage(self._view)
        self._view.setPage(self._page)
        self._channel = QWebChannel(self._page)
        self._bridge = _Bridge(self._on_atom_clicked)
        self._channel.registerObject("bridge", self._bridge)
        self._page.setWebChannel(self._channel)

        self._page_ready = False
        self._pending_molblock: str | None = None
        # Mutually exclusive with _pending_molblock: the viewer shows
        # either one molecule or one superimposed ensemble, never both, so
        # queueing one clears the other. Whichever call came last is what
        # the user asked for.
        self._pending_ensemble: list[dict[str, str]] | None = None
        self._pending_layer: VisualizationLayer | None = None
        # `_NOTHING_PENDING` rather than None, because None is itself a
        # meaningful queued VALUE for a surface -- it means "clear". The
        # same ambiguity was a real bug in MolStarViewerBackend, where
        # using None for both silently swallowed queued clears.
        self._pending_surface: SurfaceLayer | None | object = _NOTHING_PENDING
        self._page.loadFinished.connect(self._on_load_finished)
        self._page.load(QUrl.fromLocalFile(str(_VIEWER_HTML)))

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            logger.error("Failed to load 3D viewer page from %s", _VIEWER_HTML)
            return
        self._page_ready = True
        if self._pending_molblock is not None:
            self._run_load(self._pending_molblock)
            self._pending_molblock = None
        if self._pending_ensemble is not None:
            self._run_load_ensemble(self._pending_ensemble)
            self._pending_ensemble = None
        # Replayed AFTER the molblock, never before: viewer.html's
        # loadMolblock() resets any active visualization, so applying the
        # layer first would immediately be undone.
        if self._pending_layer is not None:
            self._run_apply_visualization(self._pending_layer)
            self._pending_layer = None
        # Also after the molblock, for the same reason -- loadMolblock()
        # drops the surface's stale per-atom colours.
        if self._pending_surface is not _NOTHING_PENDING:
            self._run_apply_surface(self._pending_surface)
            self._pending_surface = _NOTHING_PENDING

    def _on_atom_clicked(self, atom_index: int) -> None:
        self.atoms_selected.emit([atom_index])

    def load_conformer(self, molblock: str) -> None:
        self._pending_ensemble = None
        if self._page_ready:
            self._run_load(molblock)
        else:
            self._pending_molblock = molblock

    def _run_load(self, molblock: str) -> None:
        self._page.runJavaScript(f"window.openchemViewer.loadMolblock({json.dumps(molblock)});")

    def load_ensemble(self, entries: list[tuple[str, str]]) -> None:
        """Superimpose several structures, each in its own colour.

        `entries` is (molblock, hex colour) in draw order. Used by the 3D
        alignment panel, where the structures are already in one shared
        coordinate frame and telling them apart by colour is the entire
        point of the view.
        """
        payload = [{"molblock": molblock, "color": color} for molblock, color in entries]
        self._pending_molblock = None
        if self._page_ready:
            self._run_load_ensemble(payload)
        else:
            self._pending_ensemble = payload

    def _run_load_ensemble(self, payload: list[dict[str, str]]) -> None:
        self._page.runJavaScript(f"window.openchemViewer.loadEnsemble({json.dumps(payload)});")

    def set_style(self, style: str) -> None:
        self._page.runJavaScript(f"window.openchemViewer.setStyle({json.dumps(style)});")

    def clear(self) -> None:
        self._page.runJavaScript("window.openchemViewer.clear();")

    def apply_visualizations(self, layers: list[AnyVisualizationLayer]) -> None:
        # Composites the atom-target layers into one colour/label map,
        # later layers winning where they overlap. ResidueColorLayers are
        # IGNORED here rather than rejected -- 3Dmol.js renders
        # small-molecule conformers, which have no residues; see
        # ViewerBackend.apply_visualizations' contract.
        # A SurfaceLayer is a different render target, not an atom-colour
        # map -- it goes to apply_surface() rather than being composited
        # into the colour merge below. Last one wins if several are passed;
        # only one surface can be shown at a time.
        surface_layers = [layer for layer in layers if isinstance(layer, SurfaceLayer)]
        self.apply_surface(surface_layers[-1] if surface_layers else None)

        atom_layers = [layer for layer in layers if isinstance(layer, VisualizationLayer)]
        if not atom_layers:
            self.apply_visualization(None)
            return
        merged_colors: dict[int, str] = {}
        merged_labels: dict[int, str] = {}
        for layer in atom_layers:
            merged_colors.update(layer.atom_colors)
            if layer.atom_labels:
                merged_labels.update(layer.atom_labels)
        self.apply_visualization(
            VisualizationLayer(
                name=" + ".join(layer.name for layer in atom_layers),
                atom_colors=merged_colors,
                # One legend can only describe one scale honestly, so a
                # composite keeps the scale only when a single layer
                # produced it.
                color_scale=atom_layers[0].color_scale if len(atom_layers) == 1 else None,
                atom_labels=merged_labels or None,
            )
        )

    def apply_visualization(self, layer: VisualizationLayer | None) -> None:
        # Deferred until the page is ready, exactly like load_conformer --
        # without this, a caller that constructs this backend and applies a
        # layer in the same synchronous block (CalculatorInspectorDialog
        # does) fired runJavaScript into a not-yet-loaded page, where it
        # was silently discarded and never replayed. That was the real
        # cause of the Calculator Inspector's 3D pane rendering uncoloured
        # while its 2D pane (synchronous RDKit SVG) showed colours fine.
        if not self._page_ready:
            self._pending_layer = layer
            return
        self._run_apply_visualization(layer)

    def apply_surface(self, layer: SurfaceLayer | None) -> None:
        """Shows a molecular surface, or clears it with `None`.

        Deferred until the page is ready, exactly like `load_conformer` and
        `apply_visualization` -- the deferral ships WITH the feature rather
        than after it, because this same race has been introduced and fixed
        three separate times in this codebase already (the Calculator
        Inspector's 3D pane, the Mol* structure replay, and the Mol*
        None-sentinel ambiguity).
        """
        if not self._page_ready:
            self._pending_surface = layer
            return
        self._run_apply_surface(layer)

    def _run_apply_surface(self, layer: SurfaceLayer | None) -> None:
        if layer is None:
            self._page.runJavaScript("window.openchemViewer.clearSurface();")
            return
        self._page.runJavaScript(
            f"window.openchemViewer.applySurface("
            f"{json.dumps(layer.representation)}, {json.dumps(layer.opacity)}, "
            f"{json.dumps(layer.atom_colors)});"
        )

    def _run_apply_visualization(self, layer: VisualizationLayer | None) -> None:
        if layer is None or not layer.atom_colors:
            self._page.runJavaScript("window.openchemViewer.clearVisualization();")
            return
        # dict keys become JSON string keys (json.dumps does this
        # automatically for int keys) -- fine, JS object property access
        # coerces a numeric atom index to the same string either way.
        # atom_labels (Phase 18) is optional -- `null` when absent, which
        # viewer.html's applyVisualization already treats as "no labels".
        self._page.runJavaScript(
            f"window.openchemViewer.applyVisualization("
            f"{json.dumps(layer.atom_colors)}, {json.dumps(layer.atom_labels)});"
        )

    def widget(self):
        return self._view
