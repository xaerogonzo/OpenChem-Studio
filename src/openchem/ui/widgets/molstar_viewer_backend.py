from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.visualization import AnyVisualizationLayer, ResidueColorLayer

logger = logging.getLogger("openchem.ui")

_VIEWER_HTML = Path(__file__).resolve().parent.parent.parent / "resources" / "molstar" / "viewer.html"

# Distinct from None, which is a real queued value meaning "clear".
_NOTHING_PENDING = object()


class _Bridge(QObject):
    """QWebChannel-exposed object. viewer.html's JS calls these back —
    `viewerReady` once Mol*'s async `Viewer.create(...)` promise resolves
    (unlike 3Dmol.js, Mol* has no synchronous-ready shortcut, same async
    shape KetcherEditorBackend's `ketcherReady` handles), and
    `structureClicked` whenever the user clicks a structural element.
    """

    def __init__(self, backend: "MolStarViewerBackend") -> None:
        super().__init__()
        self._backend = backend

    @Slot()
    def viewerReady(self) -> None:  # noqa: N802 - called from JS by this exact name
        self._backend._on_viewer_ready()

    @Slot(str)
    def structureClicked(self, loci_kind: str) -> None:  # noqa: N802
        self._backend.structure_clicked.emit(loci_kind)


class _LoggingPage(QWebEnginePage):
    """Forwards the page's JS console to Python logging."""

    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802 - Qt override
        logger.debug("[molstar-js:%s:%d] %s", source, line, message)


class MolStarViewerBackend(ViewerBackend):
    """The only place in the application that knows Mol* exists.

    Hosts the vendored resources/molstar/viewer.html (Mol*'s prebuilt
    viewer bundle, dependency-free like 3Dmol's) in a QWebEngineView,
    bridged to Python via QWebChannel. Sibling to `Mol3DViewerBackend` —
    this one is for macromolecular/crystallographic structures
    (`MacromoleculeModel`), not small-molecule conformers, and doesn't
    implement `load_conformer`/`set_style` (not meaningful for a receptor-
    sized structure); it implements `load_macromolecule` instead.
    """

    structure_clicked = Signal(str)  # Loci "kind" string, e.g. "element-loci"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        if not _VIEWER_HTML.exists():
            raise FileNotFoundError(f"Macromolecule viewer page not found at {_VIEWER_HTML}")
        self._view = QWebEngineView(parent)
        self._page = _LoggingPage(self._view)
        self._view.setPage(self._page)
        self._channel = QWebChannel(self._page)
        self._bridge = _Bridge(self)
        self._channel.registerObject("bridge", self._bridge)
        self._page.setWebChannel(self._channel)

        self._viewer_ready = False
        # A FIFO, not a single slot: load_macromolecule() followed
        # immediately by load_additional_structure() (as
        # MainWindow._on_docking_result_ready does, to show a docked
        # ligand pose with its receptor) must run in that order even if
        # neither call happened to be Python-side "ready" yet.
        self._pending_calls: list[tuple[str, str, str, bool]] = []
        # Residue colouring queued before the viewer exists. A single slot,
        # not a FIFO like _pending_calls above: layers replace rather than
        # accumulate, so only the most recent one matters.
        #
        # `_NOTHING_PENDING` rather than None as the empty marker, because
        # None is itself a meaningful queued VALUE here -- it means "clear
        # the colouring". Using None for both lost queued clears entirely.
        self._pending_layers: dict[str, str] | None | object = _NOTHING_PENDING
        #: The search box requested before the viewer existed. Same single
        #: slot and same sentinel as `_pending_layers`, for the same reason:
        #: None means "clear", so it cannot double as "nothing requested".
        self._pending_search_box: tuple | None | object = _NOTHING_PENDING
        self._page.load(QUrl.fromLocalFile(str(_VIEWER_HTML)))

    def _on_viewer_ready(self) -> None:
        self._viewer_ready = True
        pending, self._pending_calls = self._pending_calls, []
        for structure_text, source_format, label, additional in pending:
            self._run_load(structure_text, source_format, label, additional)
        # Replayed AFTER the structures, never before: overpaint attaches
        # to a representation that does not exist until its structure is
        # loaded, so colouring first would target nothing.
        if self._pending_layers is not _NOTHING_PENDING:
            self._run_apply_residue_colors(self._pending_layers)
            self._pending_layers = _NOTHING_PENDING
        # Position among these replays does not matter, unlike the layers
        # above: the box is a free-standing shape at the state-tree root and
        # attaches to no representation, so it cannot be applied "too early"
        # the way overpaint can. Replayed last only for readability.
        if self._pending_search_box is not _NOTHING_PENDING:
            self._run_apply_search_box(self._pending_search_box)
            self._pending_search_box = _NOTHING_PENDING

    def load_macromolecule(self, structure_text: str, source_format: str) -> None:
        self._load(structure_text, source_format, "structure", additional=False)

    def load_additional_structure(self, structure_text: str, source_format: str, label: str = "structure") -> None:
        """Adds a structure alongside whatever is already loaded (does not
        clear first) — used to show a docked ligand pose together with its
        receptor."""
        self._load(structure_text, source_format, label, additional=True)

    def _load(self, structure_text: str, source_format: str, label: str, additional: bool) -> None:
        if self._viewer_ready:
            self._run_load(structure_text, source_format, label, additional)
        else:
            self._pending_calls.append((structure_text, source_format, label, additional))

    def _run_load(self, structure_text: str, source_format: str, label: str, additional: bool) -> None:
        js_function = "loadAdditionalStructure" if additional else "loadStructure"
        self._page.runJavaScript(
            f"window.openchemMolstarViewer.{js_function}("
            f"{json.dumps(structure_text)}, {json.dumps(source_format)}, {json.dumps(label)});"
        )

    def clear(self) -> None:
        if self._viewer_ready:
            self._page.runJavaScript("window.openchemMolstarViewer.clear();")
        self._pending_calls = []
        self._pending_layers = _NOTHING_PENDING
        # `plugin.clear()` empties the whole state tree, box included, so the
        # page's own refs are stale afterwards -- tell it, rather than
        # leaving `searchBoxState()` describing a shape that no longer
        # exists. Not merely dropping the pending slot: a viewer that is
        # already up has a real box on screen to remove.
        self._apply_search_box(None)

    def apply_visualizations(self, layers: list[AnyVisualizationLayer]) -> None:
        """Renders `ResidueColorLayer`s and IGNORES atom layers -- per
        `ViewerBackend.apply_visualizations`' contract, a backend renders
        the target kinds it can. Per-atom scientific data (LogP
        contributions, partial charges) is computed for small molecules and
        has no meaning against a receptor-sized structure here.

        Composites in order with later layers winning, which is what makes
        `build_interaction_layers` emit clashes after H-bonds: a residue
        doing both ends up flagged with the problem.
        """
        residue_layers = [layer for layer in layers if isinstance(layer, ResidueColorLayer)]
        if not residue_layers:
            self._apply_residue_colors(None)
            return
        merged: dict[str, str] = {}
        for layer in residue_layers:
            merged.update(layer.residue_colors)
        self._apply_residue_colors(merged)

    def _apply_residue_colors(self, residue_colors: dict[str, str] | None) -> None:
        # Deferred like every other call here: Mol*'s viewer is created
        # asynchronously, and a colouring applied before it exists would be
        # silently dropped (the same class of bug that left the Calculator
        # Inspector's 3D pane uncoloured -- see Mol3DViewerBackend).
        if not self._viewer_ready:
            self._pending_layers = residue_colors
            return
        self._run_apply_residue_colors(residue_colors)

    def _run_apply_residue_colors(self, residue_colors: dict[str, str] | None) -> None:
        if not residue_colors:
            self._page.runJavaScript("window.openchemMolstarViewer.clearResidueColors();")
            return
        self._page.runJavaScript(
            f"window.openchemMolstarViewer.applyResidueColors({json.dumps(residue_colors)});"
        )

    # --- the docking search box ---------------------------------------------

    def show_search_box(
        self,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
    ) -> None:
        """Draw the docking search region on the loaded structure.

        PLAIN GEOMETRY, NEVER A `DockingBox`. The viewer knows nothing about
        docking, ligand codes or reference sites; the contract is "draw this
        box in the structure's coordinates", which is what lets virtual
        screening reuse it without making Mol* docking-aware. Nothing in
        `tests/test_layering.py` forbids the import -- it only bars rdkit and
        openbabel from `ui/` -- so this is a design choice, pinned in the
        signature so nobody later passes the whole domain object through.

        Colour and line width are the PAGE's, deliberately: docking supplies
        geometry and appearance is presentation.
        """
        self._apply_search_box((tuple(center), tuple(size)))

    def clear_search_box(self) -> None:
        self._apply_search_box(None)

    def _apply_search_box(self, box) -> None:
        """A box is STATE, so it queues -- "queue state, drop gestures".

        ONE SLOT, NOT A FIFO, which is also what makes latest-wins hold on
        this side: a newer request replaces an older uncommitted one rather
        than being appended behind it. Guaranteeing that only in JavaScript
        would fix nothing if Python still replayed every superseded box into
        the page.

        `_NOTHING_PENDING` rather than None as the empty marker, for the same
        reason `_pending_layers` uses it one method up: None is a meaningful
        queued VALUE here meaning "clear", and using it for both loses a
        queued clear entirely.
        """
        if not self._viewer_ready:
            self._pending_search_box = box
            return
        self._run_apply_search_box(box)

    def _run_apply_search_box(self, box) -> None:
        if box is None:
            self._page.runJavaScript("window.openchemMolstarViewer.clearSearchBox();")
            return
        center, size = box
        self._page.runJavaScript(
            f"window.openchemMolstarViewer.showSearchBox("
            f"{json.dumps(list(center))}, {json.dumps(list(size))});"
        )

    def widget(self):
        return self._view
