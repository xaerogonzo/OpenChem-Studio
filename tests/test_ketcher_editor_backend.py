from __future__ import annotations

import json
import time

from openchem.ui.widgets.ketcher_editor_backend import KetcherEditorBackend


#: 60 rather than 15, for the reason recorded on
#: `PAGE_READY_TIMEOUT_SECONDS` in `test_mol3d_viewer_backend.py`: a
#: readiness wait on a webview is a wait on an external resource, the
#: predicate returns the moment it is true, and 15 s was exceeded once on
#: a CI runner against a locally-measured 0.2-0.4 s. This file has the
#: same exposure -- more of it, since Ketcher loads a 35 MB bundle.
def _wait_until(qapp, predicate, timeout_seconds: float = 60) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _run_js(qapp, backend: KetcherEditorBackend, script: str, timeout_seconds: float = 5) -> object:
    result: dict[str, object] = {}
    backend._page.runJavaScript(script, lambda value: result.__setitem__("value", value))
    _wait_until(qapp, lambda: "value" in result, timeout_seconds=timeout_seconds)
    return result.get("value")


def _run_js_json(qapp, backend: KetcherEditorBackend, body: str, timeout_seconds: float = 10):
    """Evaluate a JS function body and marshal its return value as JSON.

    **`runJavaScript` on this Qt build returns PRIMITIVES ONLY** -- measured:
    a number or string arrives intact, while an array or a plain object
    arrives as the empty string, indistinguishable from a script that
    returned nothing. Anything structural has to cross as a JSON string, so
    a probe reading a list of ids straight back reads `''` and looks like a
    Ketcher failure rather than a marshalling one.
    """
    script = (
        "(function(){ try { return JSON.stringify((function(){ %s })()); }"
        "catch (e) { return JSON.stringify({__error: String(e)}); } })()" % body
    )
    raw = _run_js(qapp, backend, script, timeout_seconds=timeout_seconds)
    if not raw:
        return {"__error": f"no serialisable result: {raw!r}"}
    return json.loads(raw)


def _ready_backend(qapp, shown: bool = False) -> KetcherEditorBackend:
    backend = KetcherEditorBackend()
    if shown:
        # Ketcher's toolbar is responsive -- an unshown widget reports a
        # 0x0 viewport, which collapses secondary buttons (e.g. "Add/Remove
        # explicit hydrogens", "3D Viewer") out of the DOM entirely
        # (confirmed live). Tests exercising those buttons need a real,
        # visible size; render-option tests (which don't touch the
        # toolbar's DOM) don't.
        backend.widget().resize(1280, 800)
        backend.widget().show()
    assert _wait_until(qapp, lambda: backend._ketcher_ready)
    return backend


def test_set_render_option_updates_ketchers_own_render_options(qapp):
    """End-to-end regression test for the Phase 17 audit: confirms
    `window.ketcher.editor.render.options` (not guessed -- inspected live
    against this vendored build) actually applies via `setOptions`."""
    backend = _ready_backend(qapp)

    backend.set_render_option("showHydrogenLabels", "All")

    assert _wait_until(
        qapp,
        lambda: _run_js(qapp, backend, "window.ketcher.editor.render.options.showHydrogenLabels") == "All",
    )


def _record_page_calls(backend: KetcherEditorBackend, action) -> list[str]:
    """Run `action`, returning the scripts it pushed into the page.

    Asserting on the recorded calls rather than on the JS console, because
    `_LoggingPage` forwards the console at DEBUG -- which is exactly what
    hid the 3D viewer's equivalent bug through nine of nine cold launches.
    A call that reaches an unloaded page is discarded in JS, so from
    Python it looks identical to one that was never made; recording at the
    boundary is what tells the two apart.
    """
    calls: list[str] = []
    original = backend._page.runJavaScript
    backend._page.runJavaScript = lambda script, *a, **k: calls.append(script)  # type: ignore[method-assign]
    try:
        action()
    finally:
        backend._page.runJavaScript = original  # type: ignore[method-assign]
    return calls


def test_a_render_option_set_before_ketcher_is_ready_never_calls_into_the_page(qapp):
    """Every other entry point on this backend queues; these two did not.

    Ketcher's ready signal is a JS callback (`ketcherReady`) rather than
    `loadFinished`, so it arrives later than the page does -- the window
    in which a call is reachable and dropped is WIDER here than the one
    the 3D viewer had, not narrower.
    """
    backend = KetcherEditorBackend()
    assert not backend._ketcher_ready

    calls = _record_page_calls(
        backend, lambda: backend.set_render_option("showHydrogenLabels", "All")
    )

    assert calls == []
    assert backend._pending_render_options == {"showHydrogenLabels": "All"}


def test_a_render_option_chosen_before_ketcher_is_ready_reaches_the_real_editor(qapp):
    """The replay, against the real bundle rather than a recorded call.

    No caller reaches this before ready today -- the View menu's toggles
    are never `setChecked` at construction, so nothing emits `toggled`
    until a user clicks one. But the menu is on screen and clickable while
    Ketcher is still booting, and dropping the call is the silent kind of
    failure: the checkbox shows one thing and the canvas does another,
    with nothing on screen to say which is real.
    """
    backend = KetcherEditorBackend()
    assert not backend._ketcher_ready

    backend.set_render_option("showHydrogenLabels", "All")

    assert _wait_until(qapp, lambda: backend._ketcher_ready)
    assert _wait_until(
        qapp,
        lambda: _run_js(
            qapp, backend, "window.ketcher.editor.render.options.showHydrogenLabels"
        ) == "All",
    )


def test_one_option_toggled_twice_before_ready_is_applied_once_with_the_last_value(qapp):
    """Why the queue is a dict and not a list of calls.

    An option toggled twice before the page is up is one option whose
    value the user changed their mind about. Replayed as a list it would
    be set and then unset, leaving the canvas disagreeing with the menu
    checkbox -- the very failure the queue exists to prevent.
    """
    backend = KetcherEditorBackend()
    backend.set_render_option("showHydrogenLabels", "All")
    backend.set_render_option("showHydrogenLabels", "Terminal")

    assert backend._pending_render_options == {"showHydrogenLabels": "Terminal"}

    calls = _record_page_calls(backend, backend._on_ketcher_ready)

    assert len(calls) == 1, f"expected one replayed call, got {len(calls)}: {calls}"
    assert "Terminal" in calls[0]
    assert "All" not in calls[0], "the superseded value was replayed too"
    assert backend._pending_render_options == {}


def test_the_electron_overlay_is_QUEUED_before_ready_and_the_last_one_wins(qapp):
    """STATE, so it queues -- the deliberate opposite of `start_rotation`.

    A dropped payload leaves the View menu claiming an electron display
    the canvas is not showing, with nothing on screen to say which is
    real. A replayed one merely draws the dots a moment late.

    **Only the LAST payload survives**, because a payload describes the
    current molecule: an older one is a stale fact, not a lost
    instruction, and replaying both would draw a molecule that is no
    longer selected.
    """
    backend = KetcherEditorBackend()
    calls: list[str] = []
    backend._page.runJavaScript = lambda script, *a, **k: calls.append(script)

    backend.set_electron_overlay({"counts": {"0": 2}, "refused": False, "reason": ""})
    backend.set_electron_overlay({"counts": {"1": 3}, "refused": False, "reason": ""})
    assert calls == [], "it ran before the page was ready"

    backend._ketcher_ready = True
    backend._on_ketcher_ready()

    overlay_calls = [c for c in calls if "openchemElectrons" in c]
    assert len(overlay_calls) == 1, overlay_calls
    assert '"1": 3' in overlay_calls[0] or '"1":3' in overlay_calls[0], overlay_calls[0]
    assert "0" not in overlay_calls[0].split("counts")[1][:12], "the superseded payload replayed"


def test_taking_the_overlay_OFF_survives_the_queue_too(qapp):
    """`None` is a meaningful payload -- "remove the dots" -- so the queue
    holds a 1-tuple rather than the payload itself.

    Stored bare, `None` would be indistinguishable from "nothing queued",
    and a user who turned the overlay off while Ketcher was still booting
    would get it switched on the moment the page arrived.
    """
    backend = KetcherEditorBackend()
    calls: list[str] = []
    backend._page.runJavaScript = lambda script, *a, **k: calls.append(script)

    backend.set_electron_overlay({"counts": {"0": 2}, "refused": False, "reason": ""})
    backend.set_electron_overlay(None)

    backend._ketcher_ready = True
    backend._on_ketcher_ready()

    overlay_calls = [c for c in calls if "openchemElectrons" in c]
    assert len(overlay_calls) == 1, overlay_calls
    assert "null" in overlay_calls[0], overlay_calls[0]


def test_rotation_is_refused_before_ready_rather_than_queued_or_faked(qapp):
    """A GESTURE, so it is dropped -- and the caller is TOLD.

    `window.openchemRotation` does not exist until `ketcherReady`, so
    running the call in that window does nothing at all. Two ways to be
    wrong, and this asserts against both: queueing it would put the user
    in a mode they asked for seconds ago over whatever structure loaded
    meanwhile (the `trigger_toolbar_action` reasoning), and answering
    `True` would leave the host showing a banner, rulers and a live
    readout over a canvas where dragging still draws bonds.
    """
    backend = KetcherEditorBackend()
    calls: list[str] = []
    backend._page.runJavaScript = lambda script, *a, **k: calls.append(script)

    assert backend.start_rotation() is False
    assert calls == [], calls

    backend._ketcher_ready = True
    assert backend.start_rotation() is True
    assert len(calls) == 1 and "openchemRotation" in calls[0], calls


def test_two_different_options_queued_before_ready_both_survive(qapp):
    """The complement, and the one a single-slot queue would fail.

    Keeping one `(name, value)` pair satisfies the last-value-wins test
    above completely, while silently discarding every option but the most
    recent -- and the View menu offers two of them side by side, so
    toggling both before Ketcher boots is the ordinary case rather than a
    contrived one.
    """
    backend = KetcherEditorBackend()
    backend.set_render_option("showHydrogenLabels", "All")
    backend.set_render_option("carbonExplicitly", True)

    calls = _record_page_calls(backend, backend._on_ketcher_ready)

    assert len(calls) == 2, f"expected both options replayed, got {calls}"
    assert any("showHydrogenLabels" in script for script in calls)
    assert any("carbonExplicitly" in script for script in calls)


_ETHANOL_MOLBLOCK_NO_EXPLICIT_H = (
    "\n  Mrv2014 01010000002D\n\n"
    "  3  2  0  0  0  0            999 V2000\n"
    "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    1.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    2.0000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "  1  2  1  0  0  0  0\n"
    "  2  3  1  0  0  0  0\n"
    "M  END\n"
)


def _get_molblock_sync(qapp, backend: KetcherEditorBackend, timeout_seconds: float = 5) -> str | None:
    result: dict[str, object] = {}
    backend.get_molblock(lambda mb: result.__setitem__("mb", mb))
    _wait_until(qapp, lambda: "mb" in result, timeout_seconds=timeout_seconds)
    return result.get("mb")


def _atom_count(molblock: str) -> int:
    return int(molblock.splitlines()[3][:3])


def test_an_option_queued_alongside_a_structure_survives_the_load(qapp):
    """The two queues drain in one pass, and an option must survive it.

    `Mol3DViewerBackend` has to replay its layers and surfaces AFTER the
    structure, because its `loadMolblock` genuinely clears them. Ketcher's
    `setMolecule` does not touch `render.options`, which is what this
    measures against the real bundle -- so the option is still in effect
    on the loaded structure.

    **It does not pin the ORDER, and deliberately says so rather than
    implying it.** Measured by inverting the replay in `_on_ketcher_ready`
    (structure first, options after): all 14 tests in this file still
    pass. Options-first is the better arrangement -- the structure is laid
    out the way the user asked instead of drawn once and re-rendered a
    frame later -- but it is a preference, not a correctness constraint,
    and a test claiming otherwise would be claiming more than it checks.
    """
    backend = KetcherEditorBackend()
    assert not backend._ketcher_ready

    backend.set_render_option("showHydrogenLabels", "All")
    backend.load_molblock(_ETHANOL_MOLBLOCK_NO_EXPLICIT_H)

    assert _wait_until(qapp, lambda: backend._ketcher_ready)
    # The structure really did arrive -- otherwise the option assertion
    # below would hold vacuously, on a canvas nothing was loaded into.
    assert _wait_until(qapp, lambda: (_get_molblock_sync(qapp, backend) or "").strip() != "")
    assert _atom_count(_get_molblock_sync(qapp, backend)) == 3

    assert _wait_until(
        qapp,
        lambda: _run_js(
            qapp, backend, "window.ketcher.editor.render.options.showHydrogenLabels"
        ) == "All",
    ), "the load reset a render option applied before it"


def test_trigger_toolbar_action_adds_explicit_hydrogens(qapp):
    """End-to-end regression test for the Phase 17 audit correction: the
    "Add/Remove explicit hydrogens" button is a real, working Ketcher
    toolbar action that mutates the structure (adds real H atoms) --
    confirmed live via before/after atom counts, unlike the
    `showHydrogenLabels` render option (display-only, does nothing for a
    structure with no explicit H atoms already present)."""
    backend = _ready_backend(qapp, shown=True)
    backend.load_molblock(_ETHANOL_MOLBLOCK_NO_EXPLICIT_H)
    assert _wait_until(qapp, lambda: (_get_molblock_sync(qapp, backend) or "").strip() != "")
    before_count = _atom_count(_get_molblock_sync(qapp, backend))
    assert before_count == 3  # C-C-O, no explicit hydrogens yet

    backend.trigger_toolbar_action("Add/Remove explicit hydrogens button")

    def has_more_atoms() -> bool:
        molblock = _get_molblock_sync(qapp, backend)
        return bool(molblock) and _atom_count(molblock) > before_count

    assert _wait_until(qapp, has_more_atoms)
    backend.widget().hide()


def test_a_toolbar_action_before_ketcher_is_ready_is_dropped_not_queued(qapp):
    """The deliberate asymmetry with `set_render_option`, asserted so it
    reads as a decision rather than an oversight.

    A toolbar action is a transient GESTURE, not a piece of state.
    Replaying it would perform it against a structure the user had not
    seen when they clicked -- the canvas is empty until `_pending_molblock`
    replays a moment later -- so "Add/Remove explicit hydrogens" would
    mutate that structure unasked and "3D Viewer" would open a dialog
    seconds after the click that asked for it. Both are worse than nothing
    happening on a blank canvas, which the user can see and simply repeat.
    """
    backend = KetcherEditorBackend()
    assert not backend._ketcher_ready

    calls = _record_page_calls(
        backend,
        lambda: backend.trigger_toolbar_action("Add/Remove explicit hydrogens button"),
    )
    assert calls == []

    # Dropped, NOT queued -- the half that makes it a choice. If it were
    # merely deferred, this would fire it at ready and the two clauses
    # above would both still pass.
    assert _record_page_calls(backend, backend._on_ketcher_ready) == []


def test_arming_an_atom_tool_before_ketcher_is_ready_is_dropped_not_queued(qapp):
    """Same asymmetry as the toolbar action above, and for the same
    reason: "Insert into drawing" is a GESTURE.

    Replayed when Ketcher comes up, it would leave the canvas primed with
    an element the user chose seconds ago and has since moved on from, and
    the next click ANYWHERE on the canvas would deposit it. Nothing on
    screen would say the canvas was armed, which makes it the silent kind
    of wrong -- an atom appears where the user was only trying to select.
    """
    backend = KetcherEditorBackend()
    assert not backend._ketcher_ready

    assert _record_page_calls(backend, lambda: backend.set_atom_tool("Na")) == []

    # Dropped, NOT deferred. Without this line a queued implementation
    # passes the assertion above and still misbehaves at ready.
    assert _record_page_calls(backend, backend._on_ketcher_ready) == []


def test_arming_an_atom_tool_when_ready_asks_ketcher_for_that_element(qapp):
    """`ketcher.editor.tool('atom', {label: ...})` is the real public API
    -- probed against the vendored bundle (arity 2; the active tool
    becomes `AtomTool2`), not read out of 35 MB of generated JS.

    The SYMBOL is asserted, not merely that a call happened: arming the
    wrong element still draws, just not what was asked for.
    """
    backend = KetcherEditorBackend()
    assert _wait_until(qapp, lambda: backend._ketcher_ready)

    calls = _record_page_calls(backend, lambda: backend.set_atom_tool("Fe"))

    assert len(calls) == 1
    assert "editor.tool" in calls[0]
    assert '"Fe"' in calls[0]


# --- our own loads must not look like the user drawing ----------------------


def test_a_change_event_during_our_own_load_is_ignored(qapp):
    """One paste pushed FOUR undo commands, all the same molecule.

    Loading a structure makes Ketcher fire `change`, and the vendored
    bundle reports every one of those through `structureEdited` -- so the
    host could not tell its own load from a user edit. Measured against
    real Ketcher: stack depth 4 after one paste, and Ctrl+Z appeared to do
    nothing twice before anything moved.

    Tested at the backend rather than through a real load, so it needs no
    web engine: what matters is that a change arriving while a load is in
    flight does not reach `edited`.
    """
    backend = KetcherEditorBackend()
    fired = []
    backend.edited.connect(lambda: fired.append(True))

    backend._loading_token = "a-load-in-flight"
    backend._on_structure_edited("anything")

    assert fired == []


def test_a_change_event_outside_a_load_still_reaches_the_undo_stack(qapp):
    """The complement, and the one that matters more.

    If suppression ever stuck on, the editor would stop recording real
    edits entirely -- silently, and much worse than the redundant undo
    entries it was added to remove.
    """
    backend = KetcherEditorBackend()
    fired = []
    backend.edited.connect(lambda: fired.append(True))

    backend._loading_token = None
    backend._on_structure_edited("anything")

    assert fired == [True]


def test_the_settle_timer_only_clears_its_own_load(qapp):
    """Selecting quickly through a project starts a load while the last
    one is still settling. The older one finishing must not unsuppress the
    newer one."""
    backend = KetcherEditorBackend()
    backend._loading_token = "newer"

    backend._clear_loading_token("older")

    assert backend._loading_token == "newer"
    backend._clear_loading_token("newer")
    assert backend._loading_token is None


def test_each_settle_shot_carries_the_token_it_was_scheduled_with(qapp):
    """The end-to-end half of the test above, through the real timer.

    That one calls `_clear_loading_token` directly, so it checks the
    PREDICATE and not the wiring -- it passes unchanged however the token
    reaches the slot. This one fails if the token stops travelling with
    its own shot.

    That is the live hazard in dropping the self-capturing lambda: the
    obvious replacement stores the pending token on the backend and reads
    it back in a no-argument slot, at which point the older shot reads
    the NEWER token, finds it current, and clears a load that is still
    settling -- inverting the keying `_on_load_complete` documents.

    **BOTH LOADS MUST COMPLETE for this to discriminate.** If the second
    only starts, the stored token is never overwritten and the two
    implementations agree; it takes a second completion to make the
    older shot read a token that is not its own.

    **ORDER IS DELIBERATELY NOT ASSERTED.** Two shots scheduled
    microseconds apart with the same delay came back `['newer', 'older']`
    -- Qt does not promise FIFO for same-expiry single shots, and the
    first version of this test asserted schedule order and failed against
    correct code. What is being guarded is that each shot carries its own
    token, which is a fact about this module; the dispatch order is a
    fact about Qt's timer queue and none of our business.
    """
    import time

    from PySide6.QtCore import QCoreApplication

    backend = KetcherEditorBackend()
    seen: list[str] = []
    # Shadowed BEFORE scheduling: the shot binds the method at schedule
    # time, so a later patch would never be seen.
    backend._clear_loading_token = seen.append

    backend._loading_token = "older"
    backend._on_load_complete("older")
    backend._loading_token = "newer"
    backend._on_load_complete("newer")

    deadline = time.monotonic() + 5.0
    while len(seen) < 2 and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)

    assert len(seen) == 2, "both settle shots must fire"
    assert sorted(seen) == ["newer", "older"], (
        "a settle shot cleared a load that was not its own"
    )


# --- a selection must arrive as a MOLFILE POSITION, not a Ketcher pool id ---


_BENZENE = (
    "\n  Mrv\n\n"
    "  6  6  0  0  0  0            999 V2000\n"
    "    0.0000    1.4000    0.0000 C   0  0\n"
    "    1.2124    0.7000    0.0000 C   0  0\n"
    "    1.2124   -0.7000    0.0000 C   0  0\n"
    "    0.0000   -1.4000    0.0000 C   0  0\n"
    "   -1.2124   -0.7000    0.0000 C   0  0\n"
    "   -1.2124    0.7000    0.0000 C   0  0\n"
    "  1  2  2  0\n  2  3  1  0\n  3  4  2  0\n"
    "  4  5  1  0\n  5  6  2  0\n  6  1  1  0\nM  END\n"
)
#: The same ring, translated well clear of the first so nothing merges.
_BENZENE_OFFSET = (
    "\n  Mrv\n\n"
    "  6  6  0  0  0  0            999 V2000\n"
    "   10.0000    1.4000    0.0000 C   0  0\n"
    "   11.2124    0.7000    0.0000 C   0  0\n"
    "   11.2124   -0.7000    0.0000 C   0  0\n"
    "   10.0000   -1.4000    0.0000 C   0  0\n"
    "    8.7876   -0.7000    0.0000 C   0  0\n"
    "    8.7876    0.7000    0.0000 C   0  0\n"
    "  1  2  2  0\n  2  3  1  0\n  3  4  2  0\n"
    "  4  5  1  0\n  5  6  2  0\n  6  1  1  0\nM  END\n"
)


def _draw_two_rings_and_erase_the_first(qapp, backend) -> dict:
    """Leave one six-atom ring on the canvas whose pool ids start at 6.

    Erasure goes through Ketcher's own Delete hotkey rather than by poking
    the pool, so the state under test is one the real editor produces.
    """
    _run_js_json(qapp, backend, "window.ketcher.setMolecule(%s); return 1;" % json.dumps(_BENZENE))
    _wait_until(qapp, lambda: False, timeout_seconds=1.5)
    _run_js_json(
        qapp, backend, "window.ketcher.addFragment(%s); return 1;" % json.dumps(_BENZENE_OFFSET)
    )
    _wait_until(qapp, lambda: False, timeout_seconds=1.5)
    _run_js_json(qapp, backend, """
      var e = window.ketcher.editor, s = e.struct();
      var atoms = Array.from(s.atoms.keys()).slice(0, 6);
      var bonds = Array.from(s.bonds.keys()).filter(function(b){
        var bd = s.bonds.get(b);
        return atoms.indexOf(bd.begin) >= 0 && atoms.indexOf(bd.end) >= 0; });
      e.selection({atoms: atoms, bonds: bonds});
      return 1;
    """)
    _wait_until(qapp, lambda: False, timeout_seconds=0.5)
    _run_js_json(qapp, backend, """
      var el = document.querySelector('.Ketcher-root') || document.body;
      ['keydown','keyup'].forEach(function(t){
        el.dispatchEvent(new KeyboardEvent(t, {key:'Delete', code:'Delete',
          bubbles:true, cancelable:true, keyCode:46, which:46})); });
      return 1;
    """)
    _wait_until(qapp, lambda: False, timeout_seconds=1.5)
    return _run_js_json(qapp, backend, """
      var s = window.ketcher.editor.struct();
      return {atoms: Array.from(s.atoms.keys()), bonds: Array.from(s.bonds.keys())};
    """)


def _select_and_collect(qapp, backend, key: str, pool_ids, received: list) -> list:
    got = []
    for pool_id in pool_ids:
        _run_js_json(qapp, backend, "window.ketcher.editor.selection(null); return 1;")
        _wait_until(qapp, lambda: False, timeout_seconds=0.25)
        received.clear()
        _run_js_json(
            qapp, backend,
            "window.ketcher.editor.selection({%s: [%d]}); return 1;" % (key, pool_id),
        )
        _wait_until(qapp, lambda: bool(received), timeout_seconds=5)
        got.append(received[-1] if received else None)
    return got


def test_a_selection_arrives_as_a_molfile_position_not_a_ketcher_pool_id(qapp):
    """Clicking a carbon said "pick a heavy atom". THE INDEX WAS A POOL ID.

    Ketcher's `Pool` extends Map and allocates from a counter that only ever
    increments, so an id is a permanent identity handle and a freed one is
    never reused -- while the molfile is positional and RDKit numbers atoms
    by reading it in order. The two agree only until something is deleted.

    Reproduced exactly as reported: two rings drawn, the first erased, and
    the surviving benzene's six carbons carried pool ids 6..11 against a
    six-atom molfile. Clicking two vertices sent 8 and 10, and the Atom
    Inspector answered "Atom 9 is in the 3D structure but not in the
    structure as drawn -- pick a heavy atom" about a carbon.

    Bonds had the identical offset and were WORSE: a wrong bond index stays
    in range, so the panel silently described a different bond. Both are
    asserted here.

    This must run against the real bundle, because the fix lives in JS and a
    stale dist would leave the app broken with every Python test green.
    """
    backend = _ready_backend(qapp, shown=True)
    atoms_received: list[int] = []
    bonds_received: list[int] = []
    backend.atom_selected.connect(atoms_received.append)
    backend.bond_selected.connect(bonds_received.append)

    pool = _draw_two_rings_and_erase_the_first(qapp, backend)

    # ASSERT THE SETUP, or the test proves nothing. If the Delete hotkey
    # ever stops erasing, the pool stays dense, pool ids equal positions by
    # accident and the assertions below pass while testing nothing at all.
    assert pool.get("atoms") == [6, 7, 8, 9, 10, 11], (
        f"setup did not produce non-dense pool ids, so this test would pass "
        f"vacuously: {pool}"
    )
    assert pool.get("bonds") == [6, 7, 8, 9, 10, 11], f"bond setup failed: {pool}"

    assert _select_and_collect(qapp, backend, "atoms", pool["atoms"], atoms_received) == [
        0, 1, 2, 3, 4, 5
    ], "atom pool ids reached Python untranslated"
    assert _select_and_collect(qapp, backend, "bonds", pool["bonds"], bonds_received) == [
        0, 1, 2, 3, 4, 5
    ], "bond pool ids reached Python untranslated"

    backend.widget().hide()


def test_a_freshly_loaded_structure_still_reports_the_same_indices(qapp):
    """The common path, and the one the translation could quietly break.

    A fresh `setMolecule` rebuilds the pool from zero, so ids and positions
    coincide and `molfilePosition` must be an identity here. Worth its own
    test because the regression test above deliberately works only on an
    EDITED structure -- a translation that returned, say, the id minus six
    would satisfy it and break every molecule nobody had edited yet.
    """
    backend = _ready_backend(qapp, shown=True)
    atoms_received: list[int] = []
    bonds_received: list[int] = []
    backend.atom_selected.connect(atoms_received.append)
    backend.bond_selected.connect(bonds_received.append)

    backend.load_molblock(_ETHANOL_MOLBLOCK_NO_EXPLICIT_H)
    assert _wait_until(qapp, lambda: (_get_molblock_sync(qapp, backend) or "").strip() != "")

    pool = _run_js_json(qapp, backend, """
      var s = window.ketcher.editor.struct();
      return {atoms: Array.from(s.atoms.keys()), bonds: Array.from(s.bonds.keys())};
    """)
    assert pool.get("atoms") == [0, 1, 2], f"expected a dense pool after a load: {pool}"

    assert _select_and_collect(qapp, backend, "atoms", pool["atoms"], atoms_received) == [0, 1, 2]
    assert _select_and_collect(qapp, backend, "bonds", pool["bonds"], bonds_received) == [0, 1]

    backend.widget().hide()


def test_the_canvas_can_reach_the_system_clipboard(qapp):
    """Ctrl+C / Ctrl+V inside the canvas.

    QtWebEngine defaults BOTH of these to off -- measured on this build,
    a bare QWebEnginePage reports False for each. Ketcher's copy handler
    runs, produces a molfile and then cannot hand it to the clipboard,
    which is exactly the reported symptom: "something flashes for a
    second then nothing".

    Asserted on the real page rather than on a flag we set ourselves, so
    a rename of the attribute fails here rather than in the app.
    """
    from PySide6.QtWebEngineCore import QWebEngineSettings

    attribute = QWebEngineSettings.WebAttribute
    backend = KetcherEditorBackend()
    settings = backend._page.settings()

    assert settings.testAttribute(attribute.JavascriptCanAccessClipboard)
    assert settings.testAttribute(attribute.JavascriptCanPaste)
