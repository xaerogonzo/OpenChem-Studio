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
from openchem.ui.visualization import VisualizationLayer

logger = logging.getLogger("openchem.ui")

_VIEWER_HTML = (
    Path(__file__).resolve().parent.parent.parent / "resources" / "viewer3d" / "viewer.html"
)


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

    def _on_atom_clicked(self, atom_index: int) -> None:
        self.atoms_selected.emit([atom_index])

    def load_conformer(self, molblock: str) -> None:
        if self._page_ready:
            self._run_load(molblock)
        else:
            self._pending_molblock = molblock

    def _run_load(self, molblock: str) -> None:
        self._page.runJavaScript(f"window.openchemViewer.loadMolblock({json.dumps(molblock)});")

    def set_style(self, style: str) -> None:
        self._page.runJavaScript(f"window.openchemViewer.setStyle({json.dumps(style)});")

    def clear(self) -> None:
        self._page.runJavaScript("window.openchemViewer.clear();")

    def apply_visualization(self, layer: VisualizationLayer | None) -> None:
        if layer is None or not layer.atom_colors:
            self._page.runJavaScript("window.openchemViewer.clearVisualization();")
            return
        # dict keys become JSON string keys (json.dumps does this
        # automatically for int keys) -- fine, JS object property access
        # coerces a numeric atom index to the same string either way.
        self._page.runJavaScript(
            f"window.openchemViewer.applyVisualization({json.dumps(layer.atom_colors)});"
        )

    def widget(self):
        return self._view
