from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from openchem.ui.viewer_backend import ViewerBackend

logger = logging.getLogger("openchem.ui")

_VIEWER_HTML = Path(__file__).resolve().parent.parent.parent / "resources" / "molstar" / "viewer.html"


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
        self._pending_call: tuple[str, str, str] | None = None
        self._page.load(QUrl.fromLocalFile(str(_VIEWER_HTML)))

    def _on_viewer_ready(self) -> None:
        self._viewer_ready = True
        if self._pending_call is not None:
            structure_text, source_format, label = self._pending_call
            self._run_load(structure_text, source_format, label)
            self._pending_call = None

    def load_macromolecule(self, structure_text: str, source_format: str) -> None:
        label = "structure"
        if self._viewer_ready:
            self._run_load(structure_text, source_format, label)
        else:
            self._pending_call = (structure_text, source_format, label)

    def _run_load(self, structure_text: str, source_format: str, label: str) -> None:
        self._page.runJavaScript(
            "window.openchemMolstarViewer.loadStructure("
            f"{json.dumps(structure_text)}, {json.dumps(source_format)}, {json.dumps(label)});"
        )

    def clear(self) -> None:
        if self._viewer_ready:
            self._page.runJavaScript("window.openchemMolstarViewer.clear();")
        self._pending_call = None

    def widget(self):
        return self._view
