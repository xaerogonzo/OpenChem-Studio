from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView

from openchem.domain.report import (
    ArrowAnnotation,
    AxesAnnotation,
    ConeAnnotation,
    SpatialAnnotation,
    valid_spatial_annotation,
)
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.visualization import AnyVisualizationLayer, SurfaceLayer, VisualizationLayer

logger = logging.getLogger("openchem.ui")


def shape_payloads(annotations: tuple[SpatialAnnotation, ...] | list[SpatialAnnotation]) -> list[dict]:
    """Spatial annotations as the dicts `viewer.html`'s applyShapes draws.

    **The validation gate for the whole render path.** Anything failing
    `valid_spatial_annotation` is dropped HERE with a warning, so the page
    only ever receives well-formed geometry and never has to guess -- a
    picture built from repaired nonsense reads as a result, which is worse
    than no picture. The payload carries the physical values untouched;
    display scaling is the page's job.
    """
    payloads: list[dict] = []
    for annotation in annotations:
        if not valid_spatial_annotation(annotation):
            logger.warning("Refusing to render a malformed spatial annotation: %r", annotation)
            continue
        if isinstance(annotation, ArrowAnnotation):
            payloads.append(
                {
                    "kind": "arrow",
                    "anchor": list(annotation.anchor),
                    "vector": list(annotation.vector),
                    "units": annotation.units,
                    "label": annotation.label,
                }
            )
        elif isinstance(annotation, ConeAnnotation):
            payloads.append(
                {
                    "kind": "cone",
                    "apex": list(annotation.apex),
                    "axis": list(annotation.axis),
                    "half_angle_deg": annotation.half_angle_deg,
                    "length": annotation.length,
                    "label": annotation.label,
                }
            )
        elif isinstance(annotation, AxesAnnotation):
            payloads.append(
                {
                    "kind": "axes",
                    "origin": list(annotation.origin),
                    "axes": [list(axis) for axis in annotation.axes],
                    "extents": list(annotation.extents),
                    "labels": list(annotation.labels),
                }
            )
    return payloads

_VIEWER_HTML = (
    Path(__file__).resolve().parent.parent.parent / "resources" / "viewer3d" / "viewer.html"
)

# Distinct from None, which is a real queued value meaning "clear the
# surface" -- same sentinel MolStarViewerBackend uses for the same reason.
_NOTHING_PENDING = object()


class _Bridge(QObject):
    """QWebChannel-exposed object. viewer.html's JS calls these by name."""

    def __init__(
        self,
        on_atom_clicked: Callable[[int], None],
        on_grid_cell_clicked: Callable[[int], None] | None = None,
        on_grid_cell_toggled: Callable[[int, bool], None] | None = None,
        on_grid_failed: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_atom_clicked = on_atom_clicked
        self._on_grid_cell_clicked = on_grid_cell_clicked
        self._on_grid_cell_toggled = on_grid_cell_toggled
        self._on_grid_failed = on_grid_failed

    @Slot(int)
    def atomClicked(self, atom_index: int) -> None:  # noqa: N802 - called from JS by this exact name
        self._on_atom_clicked(atom_index)

    @Slot(int)
    def gridCellClicked(self, index: int) -> None:  # noqa: N802 - called from JS by this exact name
        if self._on_grid_cell_clicked is not None:
            self._on_grid_cell_clicked(index)

    @Slot(int, bool)
    def gridCellToggled(self, index: int, checked: bool) -> None:  # noqa: N802 - from JS
        if self._on_grid_cell_toggled is not None:
            self._on_grid_cell_toggled(index, checked)

    @Slot(str)
    def gridFailed(self, message: str) -> None:  # noqa: N802 - called from JS by this name
        if self._on_grid_failed is not None:
            self._on_grid_failed(message)


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
        # **Do not cache the viewer page.** It is loaded from file://
        # and Chromium will happily serve a stale copy, so an edit to
        # viewer.html can appear to take effect on one run and not the
        # next. That cost a long, confusing debugging session: the same
        # code rendered correctly, small, and blank across restarts,
        # while an isolated QWebEngineView loading the same file was
        # perfectly repeatable every time.
        QWebEngineProfile.defaultProfile().setHttpCacheType(
            QWebEngineProfile.HttpCacheType.NoCache
        )
        self._page = _LoggingPage(self._view)
        self._view.setPage(self._page)
        self._channel = QWebChannel(self._page)
        self._bridge = _Bridge(
            self._on_atom_clicked,
            self._on_grid_cell_clicked,
            self._on_grid_cell_toggled,
            self._on_grid_failed,
        )
        self._channel.registerObject("bridge", self._bridge)
        self._page.setWebChannel(self._channel)

        self._page_ready = False
        #: (molblock, keep_camera) queued until the page is ready.
        self._pending_molblock: tuple[str, bool] | None = None
        #: The viewer-session identity of what is on screen; see
        #: `load_conformer`. None means 'nothing comparable yet'.
        self._structure_key: object = None
        #: (entries, rows, cols, linked, selected) while the gallery is
        #: showing, or None. Queued like every other payload, because a
        #: runJavaScript before `loadFinished` is silently dropped.
        self._grid: tuple | None = None
        # Mutually exclusive with _pending_molblock: the viewer shows
        # either one molecule or one superimposed ensemble, never both, so
        # queueing one clears the other. Whichever call came last is what
        # the user asked for.
        self._pending_ensemble: list[dict[str, str]] | None = None
        # A crystal is a THIRD mutually exclusive thing the viewer can
        # be showing. It shares the exclusion with the other two -- one
        # molecule, one ensemble, or one unit cell, never a mixture.
        self._pending_crystal: dict | None = None
        self._pending_layer: VisualizationLayer | None = None
        #: Shape payloads applied before the page was ready. Replayed
        #: AFTER the molblock like `_pending_layer` -- and unlike it,
        #: DROPPED by a new load: shape coordinates are in one conformer's
        #: frame, so pending shapes belong to the current load only.
        self._pending_shapes: list[dict] | None = None
        #: Per-cell shape payloads applied before the page was ready.
        #: A dict rather than one slot, because cells are independent and
        #: a single pending payload would let the last cell to ask
        #: silently win for all of them.
        self._pending_grid_shapes: dict[int, list[dict]] = {}
        # `_NOTHING_PENDING` rather than None, because None is itself a
        # meaningful queued VALUE for a surface -- it means "clear". The
        # same ambiguity was a real bug in MolStarViewerBackend, where
        # using None for both silently swallowed queued clears.
        self._pending_surface: SurfaceLayer | None | object = _NOTHING_PENDING
        # The style is a plain preference, so unlike the payloads above it
        # has a sensible default and only needs queueing when it differs.
        self._pending_style: str | None = None
        self._page.loadFinished.connect(self._on_load_finished)
        self._page.load(QUrl.fromLocalFile(str(_VIEWER_HTML)))

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            logger.error("Failed to load 3D viewer page from %s", _VIEWER_HTML)
            return
        self._page_ready = True
        # Before any payload, so the structure is drawn in the style the
        # user already chose rather than being restyled a frame later.
        if self._pending_style is not None:
            self._run_set_style(self._pending_style)
            self._pending_style = None
        if self._pending_molblock is not None:
            self._run_load(*self._pending_molblock)
            self._pending_molblock = None
        if self._pending_ensemble is not None:
            self._run_load_ensemble(self._pending_ensemble)
            self._pending_ensemble = None
        if self._pending_crystal is not None:
            self._run_load_crystal(self._pending_crystal)
            self._pending_crystal = None
        if self._grid is not None:
            self._run_load_grid()
        # Replayed AFTER the molblock, never before: viewer.html's
        # loadMolblock() resets any active visualization, so applying the
        # layer first would immediately be undone.
        if self._pending_layer is not None:
            self._run_apply_visualization(self._pending_layer)
            self._pending_layer = None
        if self._pending_shapes is not None:
            self._run_apply_shapes(self._pending_shapes)
            self._pending_shapes = None
        for cell_index, payloads in list(self._pending_grid_shapes.items()):
            self._run_apply_grid_shapes(cell_index, payloads)
        self._pending_grid_shapes.clear()
        # Also after the molblock, for the same reason -- loadMolblock()
        # drops the surface's stale per-atom colours.
        if self._pending_surface is not _NOTHING_PENDING:
            self._run_apply_surface(self._pending_surface)
            self._pending_surface = _NOTHING_PENDING

    def _on_atom_clicked(self, atom_index: int) -> None:
        self.atoms_selected.emit([atom_index])

    def _on_grid_cell_clicked(self, index: int) -> None:
        self.grid_cell_clicked.emit(index)

    def _on_grid_cell_toggled(self, index: int, checked: bool) -> None:
        self.grid_cell_toggled.emit(index, checked)

    def _on_grid_failed(self, message: str) -> None:
        logger.warning("The conformer gallery could not be created: %s", message)
        self._grid = None
        self.grid_failed.emit(message)

    def load_conformer_grid(
        self,
        entries: list[tuple[str, str]],
        rows: int,
        cols: int,
        linked: bool = False,
        selected: list[int] | None = None,
    ) -> None:
        """Show several conformers at once, each independently rotatable.

        `entries` is (molblock, label) in reading order. One WebGL context
        serves the whole grid -- see `loadGrid` in viewer.html for the
        measurements, and for why a QWebEngineView per conformer is not an
        option.
        """
        payload = [{"molblock": molblock, "label": label} for molblock, label in entries]
        # Pending shapes belong to the grid being REPLACED -- their
        # coordinates are in the previous conformers' frames, so replaying
        # them onto these cells would draw a plausible picture of nothing.
        # Same rule as `load_conformer` dropping `_pending_shapes`, and the
        # other half of the same contract: this covers a payload queued
        # against a page that has not loaded yet, while the page's own
        # `loadGrid` resets `gridShapes` for one that has. Shapes for THIS
        # grid arrive via `apply_grid_shapes()` after this call.
        self._pending_grid_shapes.clear()
        self._grid = (payload, rows, cols, linked, list(selected or []))
        if self._page_ready:
            self._run_load_grid()

    def _run_load_grid(self) -> None:
        payload, rows, cols, linked, selected = self._grid
        self._page.runJavaScript(
            f"window.openchemViewer.loadGrid({json.dumps(payload)}, {rows}, {cols}, "
            f"{json.dumps(bool(linked))}, {json.dumps(selected)});"
        )

    def match_grid_views(self, index: int) -> None:
        """Point every cell where cell `index` is pointing.

        Distinct from locking: this is a one-off, after which the cells go
        back to turning independently.
        """
        self._page.runJavaScript(f"window.openchemViewer.matchGridViews({int(index)});")

    def select_grid_cell(self, index: int) -> None:
        self._page.runJavaScript(f"window.openchemViewer.selectGridCell({int(index)});")

    def leave_grid(self) -> None:
        self._grid = None
        self._page.runJavaScript("window.openchemViewer.leaveGrid();")

    def load_conformer(self, molblock: str, structure_key: object = None) -> None:
        """Draw one structure, keeping the camera if it belongs with the last.

        **`structure_key` is a viewer-session identity, not a structure
        comparison.** Two conformers of one molecule share a key, so
        stepping between them keeps whatever orientation the user has
        arranged -- which is the whole of what makes them comparable. A
        different molecule gets a different key and the camera is re-fitted.

        It is deliberately NOT the molblock, and not the model object: an
        imported structure that happens to have the same graph would
        silently inherit an unrelated camera under the first, and the
        second cannot survive the model being rebuilt. The widget builds it
        from the molecule's uuid and the identity of the conformer batch.

        `None` always re-fits, which is the safe answer for every caller
        that has not thought about it.
        """
        self._pending_ensemble = None
        self._pending_crystal = None
        # Pending shapes belong to the PREVIOUS load: their coordinates
        # are in that conformer's frame, and replaying them onto this one
        # would draw a plausible picture of nothing. Shapes for THIS
        # molecule arrive via apply_shapes() after this call, exactly as
        # the visualization layer does. (The ready path needs no
        # equivalent -- the page's loadMolblock clears rendered shapes.)
        self._pending_shapes = None
        keep_camera = structure_key is not None and structure_key == self._structure_key
        self._structure_key = structure_key
        if self._page_ready:
            self._run_load(molblock, keep_camera)
        else:
            self._pending_molblock = (molblock, keep_camera)

    def current_view(self, callback: Callable[[list[float] | None], None]) -> None:
        """The camera's current state, as 3Dmol's `getView()` array.

        **JSON round-tripped, because `runJavaScript` on this Qt build
        returns PRIMITIVES ONLY** -- an array arrives as the empty string,
        indistinguishable from a script that failed. Every structural
        probe in this project has to cross as a string; this one is no
        exception, and reading `''` as "no camera" would silently drop
        every rotation the user made.

        `None` when the page is not ready or the result cannot be read, so
        the caller falls back to an unrotated drawing rather than to
        nothing.
        """
        if not self._page_ready:
            callback(None)
            return

        def done(raw: object) -> None:
            if not raw:
                callback(None)
                return
            try:
                view = json.loads(str(raw))
            except (TypeError, ValueError):
                logger.warning("Could not read the 3D viewer camera: %r", raw)
                callback(None)
                return
            callback(view if isinstance(view, list) else None)

        # `currentView()` rather than `viewer.getView()`: in gallery
        # mode the single viewer is hidden and unrotated while the
        # selected CELL carries the orientation the user arranged, and
        # the page is the only side that knows which is showing.
        self._page.runJavaScript(
            "(window.openchemViewer && window.openchemViewer.currentView)"
            " ? window.openchemViewer.currentView() : ''",
            done,
        )

    def _run_load(self, molblock: str, keep_camera: bool = False) -> None:
        self._page.runJavaScript(
            f"window.openchemViewer.loadMolblock("
            f"{json.dumps(molblock)}, {json.dumps(bool(keep_camera))});"
        )

    def load_crystal(self, scene: dict) -> None:
        """Draw one unit cell of a periodic solid.

        `scene` is plain data from `chem.crystal_analysis.scene_for` --
        atoms already expanded, wrapped and deduplicated, plus the twelve
        cell edges and three axis labels. **This widget computes nothing
        about the structure**, which is what keeps `ui/` free of the
        chemistry layer and what stops the picture and the report
        disagreeing about where the atoms are.

        Queued like `load_conformer` if the page has not finished loading,
        for the same reason: a `runJavaScript` before `loadFinished` is
        silently dropped.
        """
        self._pending_ensemble = None
        self._pending_molblock = None
        if self._page_ready:
            self._run_load_crystal(scene)
        else:
            self._pending_crystal = scene

    def _run_load_crystal(self, scene: dict) -> None:
        self._page.runJavaScript(
            f"window.openchemViewer.loadCrystal({json.dumps(scene)});"
        )

    def load_ensemble(self, entries: list[tuple[str, str]]) -> None:
        """Superimpose several structures, each in its own colour.

        `entries` is (molblock, hex colour) in draw order. Used by the 3D
        alignment panel, where the structures are already in one shared
        coordinate frame and telling them apart by colour is the entire
        point of the view.
        """
        payload = [{"molblock": molblock, "color": color} for molblock, color in entries]
        self._pending_molblock = None
        self._pending_crystal = None
        if self._page_ready:
            self._run_load_ensemble(payload)
        else:
            self._pending_ensemble = payload

    def _run_load_ensemble(self, payload: list[dict[str, str]]) -> None:
        self._page.runJavaScript(f"window.openchemViewer.loadEnsemble({json.dumps(payload)});")

    def set_style(self, style: str) -> None:
        # Queued like every other call for the reason in `clear` below.
        # Today nothing sets a style before the page loads -- both callers
        # (`MoleculeViewer3DWidget`, `AlignmentPanel`) run `addItems`
        # BEFORE connecting, so the default selection emits nothing. That
        # is an ordering nobody would think to preserve, and the combo box
        # exists and is clickable while the page is still loading, so the
        # call is reachable either way. Dropping it is the silent kind of
        # failure: the viewer renders in the default representation while
        # the combo box shows what the user picked.
        if self._page_ready:
            self._run_set_style(style)
        else:
            self._pending_style = style

    def _run_set_style(self, style: str) -> None:
        self._page.runJavaScript(f"window.openchemViewer.setStyle({json.dumps(style)});")

    def clear(self) -> None:
        # `MoleculeViewer3DWidget._refresh_view` calls this during its own
        # construction, when the molecule has no conformers -- long before
        # the page has loaded. Unguarded, it threw
        # `Uncaught TypeError: Cannot read properties of undefined
        # (reading 'clear')` on EVERY launch, measured on 9 of 9 cold
        # starts, invisible because JS console output logs at DEBUG.
        #
        # Nothing needs replaying: the page starts empty, so a clear that
        # arrives before it loads has already happened. It does have to
        # CANCEL the queued payloads, or a clear issued between a load and
        # `loadFinished` would be overtaken by the very structure it was
        # meant to remove.
        if not self._page_ready:
            self._pending_molblock = None
            self._pending_ensemble = None
            self._pending_crystal = None
            self._pending_layer = None
            self._pending_surface = _NOTHING_PENDING
            return
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

    def apply_shapes(self, annotations: tuple[SpatialAnnotation, ...] | list[SpatialAnnotation]) -> None:
        """Draw spatial annotations on the loaded conformer, or clear with ().

        Deferred until the page is ready exactly like `apply_visualization`
        -- this race has been introduced and fixed enough times that the
        deferral ships WITH the feature. The state machine differs from the
        layer's in one deliberate way: `load_conformer` DROPS pending
        shapes, because their coordinates are in the previous conformer's
        frame and replaying them onto a new molecule would draw a plausible
        picture of nothing. Pending shapes belong to the current load.
        """
        payloads = shape_payloads(annotations)
        if not self._page_ready:
            self._pending_shapes = payloads
            return
        self._run_apply_shapes(payloads)

    def apply_grid_shapes(
        self, cell_index: int, annotations: tuple[SpatialAnnotation, ...] | list[SpatialAnnotation]
    ) -> None:
        """Draw one gallery cell's annotations, or clear it with ().

        PER CELL, deliberately. Each cell shows a different conformer and
        owns its own geometry; a shared payload would draw one
        conformer's arrow on all of them, which is the wrong-frame error
        this whole feature is built to avoid.

        Deferred until the page is ready like every other payload here.
        Unlike the single view there is no drop-on-load rule to mirror:
        the grid clears its own shape state when it is rebuilt, because
        a rebuild replaces the cell viewers themselves.
        """
        payloads = shape_payloads(annotations)
        if not self._page_ready:
            self._pending_grid_shapes[cell_index] = payloads
            return
        self._run_apply_grid_shapes(cell_index, payloads)

    def _run_apply_grid_shapes(self, cell_index: int, payloads: list[dict]) -> None:
        if not payloads:
            self._page.runJavaScript(
                f"window.openchemViewer.clearGridShapes({json.dumps(cell_index)});"
            )
            return
        self._page.runJavaScript(
            f"window.openchemViewer.applyGridShapes("
            f"{json.dumps(cell_index)}, {json.dumps(payloads)});"
        )

    def clear_all_grid_shapes(self) -> None:
        """Every cell at once -- only for a grid being rebuilt or torn
        down, which is the one moment the whole set is genuinely stale."""
        self._pending_grid_shapes.clear()
        if self._page_ready:
            self._page.runJavaScript("window.openchemViewer.clearAllGridShapes();")

    def _run_apply_shapes(self, payloads: list[dict]) -> None:
        if not payloads:
            self._page.runJavaScript("window.openchemViewer.clearShapes();")
            return
        self._page.runJavaScript(
            f"window.openchemViewer.applyShapes({json.dumps(payloads)});"
        )

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
        # The scalar field travels as OpenDX TEXT, which for the default
        # 48^3 grid is roughly 1.4 MB of it. That is a lot to push through
        # runJavaScript, but it is a one-shot cost per surface change and
        # the alternative -- serving it over a local HTTP endpoint the page
        # fetches -- would add a server to a widget that has never needed
        # one. Revisit if the resolution ever climbs.
        field = (
            None
            if layer.scalar_field_dx is None
            else {
                "dx": layer.scalar_field_dx,
                "low": (layer.scalar_field_range or (-1.0, 1.0))[0],
                "high": (layer.scalar_field_range or (-1.0, 1.0))[1],
            }
        )
        self._page.runJavaScript(
            f"window.openchemViewer.applySurface("
            f"{json.dumps(layer.representation)}, {json.dumps(layer.opacity)}, "
            f"{json.dumps(layer.atom_colors)}, {json.dumps(field)});"
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
