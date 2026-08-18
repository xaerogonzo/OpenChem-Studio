from __future__ import annotations

import json
import logging
import uuid
from functools import partial
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
        on_editor_action: Callable[[str], None] | None = None,
        on_rotation_angles: Callable[[float, float], None] | None = None,
        on_rotation_finished: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_structure_edited = on_structure_edited
        self._on_rotation_angles = on_rotation_angles
        self._on_rotation_finished = on_rotation_finished
        self._on_ketcher_ready = on_ketcher_ready
        self._on_molfile_ready = on_molfile_ready
        self._on_load_complete = on_load_complete
        self._on_atom_selected = on_atom_selected
        self._on_bond_selected = on_bond_selected
        self._on_editor_action = on_editor_action

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

    # --- controls intercepted from Ketcher's own UI --------------------
    #
    # Each of these fires because `tools/ketcher-host/src/main.jsx`
    # swallowed the click (or the shortcut) before React saw it, so
    # Ketcher's own answer never appears and the application's does.
    #
    # SEPARATE NAMED SLOTS, not one parameterised one: QWebChannel
    # matches by name, and `test_ketcher_bundle_is_current` derives a
    # test per name from the JSX -- so a new interception arrives with
    # its coverage already attached.

    @Slot(float, float)
    def rotationAngles(self, x_degrees: float, y_degrees: float) -> None:  # noqa: N802 - from JS
        if self._on_rotation_angles is not None:
            self._on_rotation_angles(x_degrees, y_degrees)

    @Slot()
    def rotationFinished(self) -> None:  # noqa: N802 - called from JS by this exact name
        if self._on_rotation_finished is not None:
            self._on_rotation_finished()

    @Slot()
    def periodicTableRequested(self) -> None:  # noqa: N802 - called from JS by this exact name
        """Answered with its periodic table."""
        self._emit_editor_action("periodic_table")

    @Slot()
    def importRequested(self) -> None:  # noqa: N802 - called from JS by this exact name
        """Answered with File > Import Molecule."""
        self._emit_editor_action("import")

    @Slot()
    def exportRequested(self) -> None:  # noqa: N802 - called from JS by this exact name
        """Answered with File > Export Molecule."""
        self._emit_editor_action("export")

    @Slot()
    def aboutRequested(self) -> None:  # noqa: N802 - called from JS by this exact name
        """Answered with Help > About OpenChem Studio."""
        self._emit_editor_action("about")

    @Slot()
    def helpRequested(self) -> None:  # noqa: N802 - called from JS by this exact name
        """Answered with the Help menu."""
        self._emit_editor_action("help")

    @Slot()
    def viewer3dRequested(self) -> None:  # noqa: N802 - called from JS by this exact name
        """Answered with the 3D Viewer tab."""
        self._emit_editor_action("viewer_3d")

    @Slot()
    def undoRequested(self) -> None:  # noqa: N802 - called from JS by this exact name
        """Answered with the application's undo stack."""
        self._emit_editor_action("undo")

    @Slot()
    def redoRequested(self) -> None:  # noqa: N802 - called from JS by this exact name
        """Answered with the application's undo stack."""
        self._emit_editor_action("redo")

    def _emit_editor_action(self, action: str) -> None:
        if self._on_editor_action is not None:
            self._on_editor_action(action)


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
            self.editor_action_requested.emit,
            self.rotation_angles_changed.emit,
            self.rotation_finished.emit,
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
        #: Render options chosen before Ketcher reported ready, replayed
        #: when it does.
        #:
        #: A DICT, not a list of calls: an option toggled twice before the
        #: page is up is one option whose value the user changed their mind
        #: about, and replaying both would set it and then unset it. Keyed
        #: by option name, last value wins -- which is what the menu's own
        #: checkbox will be showing by then.
        self._pending_render_options: dict[str, object] = {}
        #: A 1-tuple holding the last overlay payload, or None if none is
        #: waiting. A tuple rather than the payload itself because `None`
        #: is a MEANINGFUL payload -- "take the overlay off" -- and would
        #: otherwise be indistinguishable from "nothing queued".
        self._pending_electron_overlay: tuple[dict | None] | None = None
        #: The last CIP display state asked for before Ketcher reported
        #: ready, or None if nothing was asked for.
        #:
        #: ONE SLOT, LAST REQUEST WINS -- `bool | None` rather than a list,
        #: for the same reason `_pending_render_options` is a dict: on then
        #: off before the page boots is off, not two instructions to replay
        #: in order. `None` is distinguishable from `False` because "nothing
        #: was asked for" and "the user turned it off" are different, and
        #: only the second should spend a call on a canvas that has never
        #: shown a label.
        self._pending_cip: bool | None = None
        #: Non-None while one of OUR loads is settling; see
        #: `_on_structure_edited`.
        self._loading_token: str | None = None
        self._pending_requests: dict[str, Callable[[str | None], None]] = {}

        self._page.load(QUrl.fromLocalFile(str(_DIST_INDEX)))

    def _on_atom_selected(self, atom_index: int) -> None:
        """One atom picked on the 2D canvas, as a MOLFILE POSITION.

        Ketcher's `selectionChange` fires for marquee selections too; the
        JS side forwards only single-atom selections, because the inspector
        describes ONE atom and a drag across half the structure would
        otherwise make it flicker through whatever came last.

        **The index arriving here has already been translated out of
        Ketcher's own id space**, by `molfilePosition` in
        tools/ketcher-host/src/main.jsx -- read that comment before
        trusting any index from this editor. Ketcher's selection reports
        POOL IDS, which are permanent identity handles from a
        never-reused counter, not positions; they match molfile order only
        until the first atom is deleted. So this value is directly usable
        as an RDKit atom index and the raw selection value was not.
        """
        self.atom_selected.emit(atom_index)

    def _on_bond_selected(self, bond_index: int) -> None:
        """One bond picked on the 2D canvas, as a MOLFILE POSITION.

        Ketcher reports bonds through the same `selectionChange` event as
        atoms, in a selection object that carries ONLY the keys with
        something in them -- a bond click gives `{bonds: [0]}` with no
        `atoms` key. Confirmed against the real vendored build rather than
        assumed from the wrapper, which is what got the atom path wrong the
        first time.

        Translated the same way as the atom index above, and it needs it
        just as badly. This file previously claimed Ketcher's bond ids were
        "dense and in molfile order" -- that was verified on a freshly
        LOADED molblock, which is precisely the case where a pool has
        never had anything removed from it and the two agree by accident.
        Measured after erasing one of two drawn rings: bond pool ids 6..11
        against a molfile of six bonds. Bonds fail worse than atoms, too --
        a wrong bond index usually stays in range, so the panel reported
        facts about a DIFFERENT bond instead of declining.
        """
        self.bond_selected.emit(bond_index)

    def _on_ketcher_ready(self) -> None:
        self._ketcher_ready = True
        # Options before the structure, so it is laid out the way the user
        # asked rather than drawn once and re-rendered a frame later.
        # Applying them to a still-empty canvas holds for whatever is
        # loaded next -- measured, `setMolecule` does not reset
        # `render.options`, unlike 3Dmol's `loadMolblock`, which clears the
        # layers and surfaces Mol3DViewerBackend therefore replays LAST.
        # A preference, not a constraint: inverting it breaks no test, and
        # `test_an_option_queued_alongside_a_structure_survives_the_load`
        # says so rather than pretending to pin it.
        for name, value in self._pending_render_options.items():
            self._run_set_render_option(name, value)
        self._pending_render_options.clear()
        if self._pending_molblock is not None:
            self._run_set_molecule(self._pending_molblock)
            self._pending_molblock = None
        if self._pending_electron_overlay is not None:
            # AFTER the structure, unlike the render options above: the
            # overlay is keyed to atoms, and replaying it onto a canvas
            # that has not loaded them yet would draw nothing and then
            # never be asked again.
            self._run_set_electron_overlay(self._pending_electron_overlay[0])
            self._pending_electron_overlay = None
        if self._pending_cip is not None:
            # AFTER the structure, for the same reason as the overlay: the
            # descriptors are computed FROM the atoms, so replaying this
            # onto a canvas that has not loaded them yet would compute
            # nothing and never be asked again. Measured: a load queued
            # after a CIP request still wins, because `_pending_molblock`
            # keeps only the last one and it is applied above this.
            self._run_set_cip_labels(self._pending_cip)
            self._pending_cip = None

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

        **THE TOKEN TRAVELS WITH THE CALLABLE, and moving it onto `self`
        would break that keying.** The obvious way to drop the
        self-capturing lambda is to store the pending token on the object
        and read it back in a no-argument slot. That inverts the very
        behaviour this docstring describes: with loads A then B in
        flight, A's timer would read the stored token, find B, and clear
        a load that is still settling -- exactly the early clear the
        keying exists to prevent. `partial` keeps the token bound to the
        shot that owns it.

        `self` is the CONTEXT OBJECT so a backend destroyed inside the
        grace period cancels the shot instead of being touched after
        death. This one would not have raised -- `_clear_loading_token`
        reads a plain Python attribute, not a C++ object -- so unlike the
        crashing sites elsewhere in the app this is tidiness rather than
        a fix, and it is worth being clear about which it is.
        """
        if token != self._loading_token:
            return
        QTimer.singleShot(_LOAD_SETTLE_MS, self, partial(self._clear_loading_token, token))

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
        # Queued like `load_molblock`, and for the same reason: a
        # `runJavaScript` issued before the page exists is silently
        # discarded. Ketcher's ready signal is a JS callback rather than
        # `loadFinished`, so it arrives LATER than the page does and the
        # window in which this is reachable-but-dropped is wider than the
        # one the 3D viewer had.
        #
        # No caller reaches it before ready today -- the View menu's
        # toggles are never `setChecked` at construction, so nothing emits
        # `toggled` until a user clicks one. But the menu is on screen and
        # clickable while Ketcher is still booting, and a dropped call is
        # the silent kind of failure: the checkbox shows one thing and the
        # canvas does another, with nothing to suggest which is real.
        if not self._ketcher_ready:
            self._pending_render_options[name] = value
            return
        self._run_set_render_option(name, value)

    def _run_set_render_option(self, name: str, value: object) -> None:
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

    def set_electron_overlay(self, payload: dict | None) -> None:
        """Hand the page the lone-pair counts, or `None` to take them off.

        Queued when the page is not ready, and **only the last payload is
        kept** -- see `EditorBackend.set_electron_overlay`. A dict rather
        than a list of calls for the same reason `_pending_render_options`
        is a dict: an overlay set twice before the page boots is one
        overlay whose contents the caller revised, and replaying both
        would draw a molecule that is no longer selected.
        """
        if not self._ketcher_ready:
            self._pending_electron_overlay = (payload,)
            return
        self._run_set_electron_overlay(payload)

    def _run_set_electron_overlay(self, payload: dict | None) -> None:
        script = f"""
        (function() {{
          if (window.openchemElectrons) {{
            window.openchemElectrons.set({json.dumps(payload)});
          }}
        }})();
        """
        self._page.runJavaScript(script)

    def set_cip_labels(self, on: bool) -> None:
        """Show or hide (R)/(S) and (E)/(Z) on the canvas.

        **NOT Ketcher's "Calculate CIP" toolbar button**, which is what this
        used to go through and is the whole reason the labels went stale.
        Measured against this bundle, that button:

            fires a `change`      ASYNCHRONOUSLY -- 0 immediately after the
                                  click, 1 after settling, so nothing can
                                  correlate the event with its cause
            grows Ketcher's own
            undo history          3 -> 4

        A `change` becomes an `EditStructureCommand` on the application's
        undo stack, so recomputing after every edit that way would leave a
        phantom undo step per edit and no safe way to tell it from a real
        one.

        `window.openchemCip` (see `tools/ketcher-host/src/main.jsx`) goes
        through `ketcher.indigo.calculateCip` and writes the answer onto the
        live struct instead. Measured end to end: **0 change events, and the
        history unchanged at undo 1 -> 1.**

        Queued when Ketcher is not ready, per `EditorBackend.set_cip_labels`.
        """
        if not self._ketcher_ready:
            self._pending_cip = on
            return
        self._run_set_cip_labels(on)

    def _run_set_cip_labels(self, on: bool) -> None:
        # Guarded on the global rather than assuming it: a dist built before
        # this feature existed has no `openchemCip`. The bundle-currency
        # guard catches that at the source, but a call reaching an older
        # page should warn rather than throw into a dead callback.
        call = "refresh" if on else "clear"
        script = f"""
        (function() {{
          if (!window.openchemCip) {{
            console.warn('[ketcher-host] openchemCip is missing -- stale dist?');
            return;
          }}
          window.openchemCip.{call}();
        }})();
        """
        self._page.runJavaScript(script)

    def set_atom_tool(self, symbol: str, mass_number: int | None = None) -> None:
        """Arm Ketcher to draw `symbol` on the next canvas click.

        `ketcher.editor.tool(name, options)` is a real public method on the
        live editor -- PROBED against the vendored bundle rather than read
        out of it, because 35 MB of generated JS has already produced one
        confidently wrong claim in this codebase. Measured:

            typeof ketcher.editor.tool                'function', arity 2
            ketcher.editor.tool('atom', {label:'Na'}) returns an object,
                                                      active tool AtomTool2

        That is precisely what Ketcher's own periodic table does with a
        chosen element, so the application's table produces the identical
        gesture rather than a parallel insertion path -- there is one way
        an atom reaches the canvas, and this is it.

        DROPPED before Ketcher is ready, never queued, for the reason
        `trigger_toolbar_action` gives: arming a tool is a transient
        gesture. Replayed a second later it would leave the canvas primed
        with an element the user has stopped thinking about, and the next
        click anywhere would deposit it.

        **`mass_number` IS OMITTED, NEVER SENT AS ZERO.** Measured against
        the real bundle, the tool keeps whatever `atomProps` it is given:

            tool('atom', {label: 'C', isotope: 13})  ->  {label, isotope}
            tool('atom', {label: 'C'})               ->  {label}

        so an ordinary element arms with exactly today's payload and
        cannot acquire an isotope of 0, which Ketcher would have to
        interpret.

        **THE TOOL STAYS ARMED AFTER A PLACEMENT**, which is Ketcher's own
        behaviour rather than anything added here -- `editor.tool()` still
        reports the atom tool afterwards, so a second click places a
        second atom. Preserved deliberately: the editor's own element
        buttons work that way, and two gestures that look identical
        should not behave differently.
        """
        if not self._ketcher_ready:
            logger.debug("Dropping atom tool %r -- Ketcher is not ready", symbol)
            return
        atom_props: dict[str, object] = {"label": symbol}
        if mass_number is not None:
            atom_props["isotope"] = int(mass_number)
        props = json.dumps(atom_props)
        script = f"""
        (function() {{
          try {{
            window.ketcher.editor.tool('atom', {props});
          }} catch (e) {{
            console.warn('[ketcher-host] could not arm the atom tool: ' + e);
          }}
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
        #
        # DROPPED before Ketcher is ready, deliberately, whereas a render
        # option is queued. A toolbar action is a transient GESTURE, not a
        # piece of state: replaying it means performing it against a
        # structure the user had not seen when they clicked, because the
        # canvas is empty until `_pending_molblock` replays a moment later.
        # "Add/Remove explicit hydrogens" would then mutate that structure
        # unasked, and "3D Viewer" would open a dialog seconds after the
        # click that asked for it. Both are worse than nothing happening on
        # a blank canvas, which is what the user is looking at and can
        # simply repeat. DEBUG rather than a warning because the drop is
        # correct here, not a fault -- and it is traceable in the same log
        # as the load-echo suppression above.
        if not self._ketcher_ready:
            logger.debug("Dropping toolbar action %r -- Ketcher is not ready", action_id)
            return
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

    def start_rotation(self) -> bool:
        """Enter 3D rotation mode: snapshot the geometry and show the rulers.

        **Nothing is mutated by entering.** The page keeps the entry
        coordinates and rotates a copy of them, so leaving without a drag
        leaves the structure byte-identical.

        **DROPPED, NOT QUEUED, WHEN THE PAGE IS NOT READY** -- and the
        caller is told, so it does not show a mode banner over a canvas
        that never entered one. `window.openchemRotation` does not exist
        before `ketcherReady`, so the call would silently do nothing while
        every control said otherwise.
        """
        if not self._ketcher_ready:
            logger.info("The editor is not ready yet; not entering rotation mode.")
            return False
        self._page.runJavaScript(
            "if (window.openchemRotation) window.openchemRotation.enter();"
        )
        return True

    def end_rotation(self, restore: bool) -> None:
        """Leave the mode. `restore=True` puts the entry geometry back."""
        self._page.runJavaScript(
            f"if (window.openchemRotation) "
            f"window.openchemRotation.leave({json.dumps(bool(restore))});"
        )

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
