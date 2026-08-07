from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QTimer, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from openchem.ui.editor_backend import EditorBackend

logger = logging.getLogger("openchem.ui")

#: How long after `setMolecule` resolves to keep ignoring change events.
#:
#: Measured, not chosen: Ketcher's echoes arrived ~80 ms after the promise
#: resolved (5.21s/5.25s loadComplete, 5.29s structureEdited). 400 ms is
#: five times that, and still far below the time a human needs to move to
#: the canvas and draw -- so a real edit within the window is not a case
#: that occurs, while a slow machine stretching the layout pass is.
_LOAD_SETTLE_MS = 400

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
        on_load_complete: Callable[[str], None] | None = None,
        on_atom_selected: Callable[[int], None] | None = None,
        on_bond_selected: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_structure_edited = on_structure_edited
        self._on_ketcher_ready = on_ketcher_ready
        self._on_molfile_ready = on_molfile_ready
        self._on_load_complete = on_load_complete
        self._on_atom_selected = on_atom_selected
        self._on_bond_selected = on_bond_selected

    @Slot(str)
    def structureEdited(self, molblock: str) -> None:  # noqa: N802 - called from JS by this exact name
        self._on_structure_edited(molblock)

    @Slot()
    def ketcherReady(self) -> None:  # noqa: N802
        self._on_ketcher_ready()

    @Slot(int)
    def atomSelected(self, atom_index: int) -> None:  # noqa: N802 - called from JS by this exact name
        if self._on_atom_selected is not None:
            self._on_atom_selected(atom_index)

    @Slot(int)
    def bondSelected(self, bond_index: int) -> None:  # noqa: N802 - called from JS by this exact name
        if self._on_bond_selected is not None:
            self._on_bond_selected(bond_index)

    @Slot(str, str)
    def molfileReady(self, request_id: str, molblock: str) -> None:  # noqa: N802
        self._on_molfile_ready(request_id, molblock)

    @Slot(str)
    def loadComplete(self, token: str) -> None:  # noqa: N802 - called from JS by this exact name
        """Ketcher's `setMolecule` promise has resolved for this load.

        Exists so the host can tell its OWN loads apart from a user's
        edits. Ketcher fires `change` for both, and the vendored bundle
        reports every one through `structureEdited` -- so loading a
        structure looked exactly like the user drawing it.
        """
        if self._on_load_complete is not None:
            self._on_load_complete(token)


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
            self._on_structure_edited,
            self._on_ketcher_ready,
            self._on_molfile_ready,
            self._on_load_complete,
            self._on_atom_selected,
            self._on_bond_selected,
        )
        self._channel.registerObject("bridge", self._bridge)
        self._page.setWebChannel(self._channel)

        # WITHOUT THESE TWO, Ctrl+C AND Ctrl+V DO NOTHING IN THE CANVAS.
        # Both default to FALSE in QtWebEngine, and the symptom is exactly
        # what gets reported: something flashes for a moment and no
        # structure appears. Ketcher's copy/paste is ordinary web
        # clipboard access, so with the permissions off its handler runs,
        # is refused, and fails silently -- there is no error dialog and
        # nothing in the application log.
        #
        # Scoped to this page rather than set globally on the default
        # profile: the only web content this application hosts that a user
        # types into is the editor. The 3D viewers have no clipboard need.
        settings = self._page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        # `JavascriptCanPaste` is separate and is the one that matters for
        # Ctrl+V: clipboard ACCESS alone still refuses a paste, because
        # reading the clipboard is the half that can exfiltrate.
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanPaste, True)

        self._ketcher_ready = False
        self._pending_molblock: str | None = None
        #: Non-None while one of OUR loads is settling; see
        #: `_on_structure_edited`.
        self._loading_token: str | None = None
        self._pending_requests: dict[str, Callable[[str | None], None]] = {}

        self._page.load(QUrl.fromLocalFile(str(_DIST_INDEX)))

    def _on_atom_selected(self, atom_index: int) -> None:
        """One atom picked on the 2D canvas.

        Ketcher's `selectionChange` fires for marquee selections too; the
        JS side forwards only single-atom selections, because the inspector
        describes ONE atom and a drag across half the structure would
        otherwise make it flicker through whatever came last.
        """
        self.atom_selected.emit(atom_index)

    def _on_bond_selected(self, bond_index: int) -> None:
        """One bond picked on the 2D canvas.

        Ketcher reports bonds through the same `selectionChange` event as
        atoms, in a selection object that carries ONLY the keys with
        something in them -- a bond click gives `{bonds: [0]}` with no
        `atoms` key. Confirmed against the real vendored build rather than
        assumed from the wrapper, which is what got the atom path wrong the
        first time.

        The id is usable as an RDKit bond index directly: both are dense
        and in molfile order, verified by loading one molblock into each
        and comparing every (begin, end) pair.
        """
        self.bond_selected.emit(bond_index)

    def _on_ketcher_ready(self) -> None:
        self._ketcher_ready = True
        if self._pending_molblock is not None:
            self._run_set_molecule(self._pending_molblock)
            self._pending_molblock = None

    def _on_structure_edited(self, molblock: str) -> None:
        if self._loading_token is not None:
            # Our own `setMolecule` echoing back, not the user drawing.
            # Ketcher fires `change` while it lays the loaded structure
            # out, and the vendored bundle reports every one of those --
            # so ONE paste pushed four undo commands, all carrying the
            # same molecule, and Ctrl+Z appeared to do nothing twice
            # before anything moved. Measured before this guard: stack
            # depth 4 after one paste, three of the entries redundant.
            logger.debug("Ignoring a change event from our own load")
            return
        self.edited.emit()

    def _on_load_complete(self, token: str) -> None:
        """Stop suppressing shortly after Ketcher says this load finished.

        NOT IMMEDIATELY, and that is the whole subtlety. `setMolecule`'s
        promise resolves when the structure has been set, and Ketcher emits
        its `change` events AFTERWARDS, while it lays the structure out.
        Traced with timestamps:

            5.21s  loadComplete
            5.25s  loadComplete
            5.29s  structureEdited   <- token already cleared
            5.29s  structureEdited

        Clearing on the promise therefore suppressed nothing: the echoes
        arrived about 80 ms late and still reached the undo stack. The
        grace period below is longer than that gap by a wide margin, and
        is the one piece of timing here -- the promise is still what
        starts the clock, so this is not a guess at how long a layout
        takes.

        Keyed on the token so a load starting while another is still
        settling is not cleared early by the older one finishing.
        """
        if token != self._loading_token:
            return
        QTimer.singleShot(
            _LOAD_SETTLE_MS, lambda: self._clear_loading_token(token)
        )

    def _clear_loading_token(self, token: str) -> None:
        if token == self._loading_token:
            self._loading_token = None

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
        # The token is generated HERE and closed by Ketcher's own promise
        # rather than by a timer. A timeout would be a guess about how
        # long a layout takes on an unknown machine with an unknown
        # structure; the promise is the actual end of the load.
        token = str(uuid.uuid4())
        self._loading_token = token
        script = f"""
        (function() {{
          var done = function() {{
            window.__openchemBridge.loadComplete({json.dumps(token)});
          }};
          // Every path below must reach `done()`. A token that is never
          // cleared suppresses the user's real edits for the rest of the
          // session, which is far worse than the redundant undo entries
          // this exists to remove -- so the "no ketcher yet" case reports
          // completion rather than returning early.
          if (!window.ketcher) {{ done(); return; }}
          try {{
            var result = window.ketcher.setMolecule({json.dumps(molblock)});
            // setMolecule returns a promise in this build, but guard for a
            // synchronous return rather than assuming -- a `.then` on
            // undefined would leave the host suppressing edits forever,
            // which is a far worse failure than one spurious undo entry.
            if (result && typeof result.then === "function") {{
              result.then(done).catch(done);
            }} else {{
              done();
            }}
          }} catch (e) {{
            done();
          }}
        }})();
        """
        self._page.runJavaScript(script)

    def set_render_option(self, name: str, value: object) -> None:
        # `window.ketcher.editor.setOptions` takes a JSON STRING (confirmed
        # live against this vendored build: `ketcher.editor.render.options`
        # exposes ~88 keys including `showHydrogenLabels`, `carbonExplicitly`,
        # `showValence`, `showCharge` -- no lone-pair option exists anywhere
        # in that set, confirmed absent from this Ketcher build, not just
        # unwired here), not a JS object literal -- `json.dumps` twice:
        # once to build the JSON payload, once more to embed it as a JS
        # string literal in the injected script.
        payload = json.dumps({name: value})
        script = f"""
        (function() {{
          if (!window.ketcher) return;
          window.ketcher.editor.setOptions({json.dumps(payload)});
        }})();
        """
        self._page.runJavaScript(script)

    def trigger_toolbar_action(self, action_id: str) -> None:
        # Ketcher's public `window.ketcher` object (the `Ketcher` class
        # instance) does NOT expose "add explicit hydrogens" or "open 3D
        # viewer" as callable methods -- those are wired only as onClick
        # handlers on the React toolbar's own buttons (confirmed by
        # searching the vendored bundle for `onToggleExplicitHydrogens`/
        # `onMiew`, both private props of the toolbar component, not the
        # Ketcher class). Clicking the real DOM button via its
        # `data-testid` (Ketcher's own e2e tests key off these, so they're
        # kept stable across releases) is the only integration point that
        # actually exists -- confirmed live: this correctly converts
        # implicit hydrogens into real explicit atoms (verified via
        # before/after getMolfile() atom counts) and opens the real Miew
        # 3D dialog for the current structure, not a template-only feature.
        # `action_id` is the button's `data-testid` value, e.g.
        # "Add/Remove explicit hydrogens button" or "3D Viewer button".
        #
        # KNOWN LIMITATION, confirmed live: Ketcher's toolbar is responsive
        # -- at a small/zero viewport (an unshown or very narrow
        # QWebEngineView) it collapses secondary buttons like these two
        # into an overflow menu, and this query then silently finds
        # nothing. A normally-docked, visible 2D Editor tab has plenty of
        # width in practice, but this is a real fragility, not a
        # theoretical one -- `console.warn` here at least surfaces it in
        # the JS console (forwarded to Python logging by `_LoggingPage`)
        # instead of failing completely silently.
        script = f"""
        (function() {{
          var btn = document.querySelector('[data-testid={json.dumps(action_id)}]');
          if (btn) {{
            btn.click();
          }} else {{
            console.warn('[ketcher-host] toolbar action not found (collapsed into overflow menu?): ' + {json.dumps(action_id)});
          }}
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
