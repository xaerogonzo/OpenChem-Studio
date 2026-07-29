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
        # A FIFO, not a single slot: load_macromolecule() followed
        # immediately by load_additional_structure() (as
        # MainWindow._on_docking_result_ready does, to show a docked
        # ligand pose with its receptor) must run in that order even if
        # neither call happened to be Python-side "ready" yet.
        self._pending_calls: list[tuple[str, str, str, bool]] = []
        self._page.load(QUrl.fromLocalFile(str(_VIEWER_HTML)))

    def _on_viewer_ready(self) -> None:
        self._viewer_ready = True
        pending, self._pending_calls = self._pending_calls, []
        for structure_text, source_format, label, additional in pending:
            self._run_load(structure_text, source_format, label, additional)

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

    def widget(self):
        return self._view
