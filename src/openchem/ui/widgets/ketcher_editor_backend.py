from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from openchem.ui.editor_backend import EditorBackend

logger = logging.getLogger("openchem.ui")

_DIST_INDEX = (
    Path(__file__).resolve().parent.parent.parent
    / "resources"
    / "ketcher"
    / "dist"
    / "index.html"
)


class _Bridge(QObject):
    """QWebChannel-exposed object. Ketcher's JS side (tools/ketcher-host/src/main.jsx)
    calls back into these slots — see there for why: QWebEnginePage.runJavaScript's
    own callback does not await Promises in this Qt build, so any result that
    depends on an async Ketcher API call (getMolfile, init) has to come back
    through here instead of through runJavaScript's return value.
    """

    def __init__(
        self,
        on_structure_edited: Callable[[str], None],
        on_ketcher_ready: Callable[[], None],
        on_molfile_ready: Callable[[str, str], None],
    ) -> None:
        super().__init__()
        self._on_structure_edited = on_structure_edited
        self._on_ketcher_ready = on_ketcher_ready
        self._on_molfile_ready = on_molfile_ready

    @Slot(str)
    def structureEdited(self, molblock: str) -> None:  # noqa: N802 - called from JS by this exact name
        self._on_structure_edited(molblock)

    @Slot()
    def ketcherReady(self) -> None:  # noqa: N802
        self._on_ketcher_ready()

    @Slot(str, str)
    def molfileReady(self, request_id: str, molblock: str) -> None:  # noqa: N802
        self._on_molfile_ready(request_id, molblock)


class _LoggingPage(QWebEnginePage):
    """Forwards the page's JS console to Python logging.

    Without this, a failure inside Ketcher/indigo's own init sequence is
    invisible from the host application.
    """

    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802 - Qt override
        logger.debug("[ketcher-js:%s:%d] %s", source, line, message)


class KetcherEditorBackend(EditorBackend):
    """The only place in the application that knows Ketcher exists.

    Hosts the vendored Ketcher build (built by tools/ketcher-host into
    resources/ketcher/dist/) in a QWebEngineView, bridged to Python via
    QWebChannel. Everything else talks to this through the `EditorBackend`
    interface only.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        if not _DIST_INDEX.exists():
            raise FileNotFoundError(
                f"Ketcher bundle not found at {_DIST_INDEX} — build it with "
                "'npm install && npm run build' in tools/ketcher-host/"
            )
        self._view = QWebEngineView(parent)
        self._page = _LoggingPage(self._view)
        self._view.setPage(self._page)
        self._channel = QWebChannel(self._page)
        self._bridge = _Bridge(
            self._on_structure_edited, self._on_ketcher_ready, self._on_molfile_ready
        )
        self._channel.registerObject("bridge", self._bridge)
        self._page.setWebChannel(self._channel)

        self._ketcher_ready = False
        self._pending_molblock: str | None = None
        self._pending_requests: dict[str, Callable[[str | None], None]] = {}

        self._page.load(QUrl.fromLocalFile(str(_DIST_INDEX)))

    def _on_ketcher_ready(self) -> None:
        self._ketcher_ready = True
        if self._pending_molblock is not None:
            self._run_set_molecule(self._pending_molblock)
            self._pending_molblock = None

    def _on_structure_edited(self, molblock: str) -> None:
        self.edited.emit()

    def _on_molfile_ready(self, request_id: str, molblock: str) -> None:
        callback = self._pending_requests.pop(request_id, None)
        if callback is not None:
            callback(molblock or None)

    def load_molblock(self, molblock: str) -> None:
        if self._ketcher_ready:
            self._run_set_molecule(molblock)
        else:
            self._pending_molblock = molblock

    def _run_set_molecule(self, molblock: str) -> None:
        script = f"""
        (function() {{
          if (!window.ketcher) return;
          window.ketcher.setMolecule({json.dumps(molblock)});
        }})();
        """
        self._page.runJavaScript(script)

    def get_molblock(self, callback: Callable[[str | None], None]) -> None:
        if not self._ketcher_ready:
            callback(None)
            return
        request_id = str(uuid.uuid4())
        self._pending_requests[request_id] = callback
        script = f"""
        (function() {{
          window.ketcher.getMolfile().then(function(molfile) {{
            window.__openchemBridge.molfileReady({json.dumps(request_id)}, molfile);
          }}).catch(function(e) {{
            window.__openchemBridge.molfileReady({json.dumps(request_id)}, "");
          }});
        }})();
        """
        self._page.runJavaScript(script)

    def widget(self):
        return self._view
