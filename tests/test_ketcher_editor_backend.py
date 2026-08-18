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


# --- CIP stereo descriptors ------------------------------------------------
#
# Reported: "if a molecule is changed while the label is turned on, it won't
# update. It will only update once the R/S option is clicked again."
#
# These run against the REAL bundle because the fix is mostly JS -- a stale
# dist would leave the application broken with every Python test green,
# which `test_ketcher_bundle_is_current.py` catches at the source and
# cannot catch behaviourally.

#: (S) at one carbon and (E) at one double bond -- so a single fixture
#: covers both descriptor kinds. Written out rather than generated, so the
#: expected positions below are fixed rather than whatever RDKit's depiction
#: happens to produce today. Verified against the real bundle: atom 3 is
#: the stereocentre, bond 1 is the alkene.
_CHIRAL_ALKENE = (
    "\n     RDKit          2D\n\n"
    "  7  6  0  0  0  0  0  0  0  0999 V2000\n"
    "   -3.3863   -0.3229    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "   -2.0220    0.3004    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "   -0.8000   -0.5695    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    0.5644    0.0538    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    0.7068    1.5470    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    1.7864   -0.8161    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    3.1507   -0.1928    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "  1  2  1  0\n  2  3  2  0\n  3  4  1  0\n"
    "  4  5  1  1\n  4  6  1  0\n  6  7  1  0\nM  END\n"
)


def _cip_labels(qapp, backend) -> dict:
    """What the PAGE is drawing, in molfile positions."""
    return json.loads(_run_js_json(qapp, backend, "return window.openchemCip.labels();"))


def _wait_for_cip(qapp, backend, predicate, timeout_seconds: float = 20) -> dict:
    """`set_cip_labels` is fire-and-forget and the calculation is a promise,
    so the answer lands some frames later."""
    _wait_until(qapp, lambda: predicate(_cip_labels(qapp, backend)),
                timeout_seconds=timeout_seconds)
    return _cip_labels(qapp, backend)


def _erase_atoms(qapp, backend, selector: str) -> None:
    """Erase whatever `selector` picks, through Ketcher's own Delete hotkey.

    `selector` is a JS expression over `(a, id)` naming the atoms to go, so
    the state under test is one the real editor produces rather than one
    poked into the pool.
    """
    _run_js_json(qapp, backend, """
      var e = window.ketcher.editor, s = e.struct();
      var atoms = [];
      s.atoms.forEach(function (a, id) { if (%s) atoms.push(id); });
      var bonds = Array.from(s.bonds.keys()).filter(function (b) {
        var bd = s.bonds.get(b);
        return atoms.indexOf(bd.begin) >= 0 || atoms.indexOf(bd.end) >= 0; });
      e.selection({atoms: atoms, bonds: bonds});
      return 1;
    """ % selector)
    _wait_until(qapp, lambda: False, timeout_seconds=0.5)
    _run_js_json(qapp, backend, """
      var el = document.querySelector('.Ketcher-root') || document.body;
      ['keydown','keyup'].forEach(function (t) {
        el.dispatchEvent(new KeyboardEvent(t, {key:'Delete', code:'Delete',
          bubbles:true, cancelable:true, keyCode:46, which:46})); });
      return 1;
    """)
    _wait_until(qapp, lambda: False, timeout_seconds=1.5)


def _delete_the_amine(qapp, backend) -> None:
    _erase_atoms(qapp, backend, "a.label === 'N'")


def _pool_keys(qapp, backend) -> dict:
    return _run_js_json(qapp, backend, """
      var s = window.ketcher.editor.struct();
      return {atoms: Array.from(s.atoms.keys()), bonds: Array.from(s.bonds.keys())};
    """)


def test_a_descriptor_lands_on_the_atom_it_describes_after_an_edit(qapp):
    """THE DESCRIPTOR WAS DRAWN ON THE WRONG ATOM, and a fresh load hides it.

    Reported from the running app: the label appeared "way to the left of
    the molecule" -- on a ring carbon nowhere near the stereocentre -- and
    pressing Ctrl+Z fixed it, because undo reloads through `setMolecule`,
    which rebuilds the pool dense.

    `calculateCip` parses its answer back into a POOL STARTING AT ZERO,
    while the live pool only starts at zero until the first deletion.
    Copying by id therefore wrote the descriptor one position early:

        live pool          [1, 2, 3, 4, 5, 6]     the centre is id 3
        calculateCip's     [0, 1, 2, 3, 4, 5]     the centre is id 2

    **THE TEST ABOVE CANNOT SEE THIS, and that is why it exists
    separately.** It erases the amine, which destroys the stereocentre --
    so there is no surviving atom label left to misplace, and the one
    surviving bond sits at an index the two pools happen to agree on. It
    passed throughout. What it takes is an edit that leaves a centre
    STANDING while making the pool non-dense.
    """
    backend = _ready_backend(qapp, shown=True)
    backend.load_molblock(_CHIRAL_ALKENE)
    assert _wait_until(qapp, lambda: (_get_molblock_sync(qapp, backend) or "").strip() != "")

    # The terminal methyl, which the stereocentre does not depend on.
    _erase_atoms(qapp, backend, "id === 0")

    # ASSERT THE SETUP. With a dense pool the ids and the positions agree
    # by coincidence and this test proves nothing at all.
    pool = _pool_keys(qapp, backend)
    assert pool["atoms"] == [1, 2, 3, 4, 5, 6], (
        f"the edit did not leave a non-dense pool, so this test would pass "
        f"vacuously: {pool}"
    )

    backend.set_cip_labels(True)

    labels = _wait_for_cip(qapp, backend, lambda got: bool(got["atoms"]))
    assert labels["atoms"] == [[2, "S"]], (
        f"the descriptor is on the wrong atom: {labels}. Position 2 is the "
        f"stereocentre; anything lower is the pool-id offset."
    )
    backend.widget().hide()


def test_the_cip_api_the_page_exposes_is_the_one_python_calls(qapp):
    """The FAIL-CLOSED half of the bundle-currency guard.

    `test_ketcher_bundle_is_current.py` scans `main.jsx` for
    `window.openchem*` and checks the name reached the bundle. That proves
    the name was written, not that the functions hanging off it survived
    the build -- so on its own it is fail-open, and the two are deliberately
    paired. This asks the real page.
    """
    backend = _ready_backend(qapp, shown=True)

    shape = _run_js_json(qapp, backend, """
      var api = window.openchemCip;
      if (!api) return {missing: true};
      var out = {};
      ['refresh', 'clear', 'labels', 'work'].forEach(function (n) { out[n] = typeof api[n]; });
      return out;
    """)

    assert shape == {"refresh": "function", "clear": "function",
                     "labels": "function", "work": "function"}, shape
    backend.widget().hide()


def test_the_descriptors_are_recomputed_after_a_real_edit(qapp):
    """THE REPORTED BUG.

    A structure edited while the labels are on kept the descriptor it had
    before the edit, because Ketcher stores CIP on `atom.cip` and never
    invalidates it. Reproduced here through Ketcher's own Delete hotkey:
    erasing the amine destroys the stereocentre, so its (S) must go while
    the alkene's (E) -- untouched by that edit -- must stay.

    **THE STALE STATE IS ASSERTED IN THE MIDDLE**, not just the fixed one.
    Without it, a refresh that silently did nothing at all would leave the
    labels empty and the final assertion could be written to pass.
    """
    backend = _ready_backend(qapp, shown=True)
    backend.load_molblock(_CHIRAL_ALKENE)
    assert _wait_until(qapp, lambda: (_get_molblock_sync(qapp, backend) or "").strip() != "")

    backend.set_cip_labels(True)
    drawn = _wait_for_cip(qapp, backend, lambda labels: bool(labels["atoms"]))
    assert drawn == {"atoms": [[3, "S"]], "bonds": [[1, "E"]]}, drawn

    _delete_the_amine(qapp, backend)

    # The bug, still present at this instant: the centre is gone and its
    # label is not. This is what the user saw.
    stale = _cip_labels(qapp, backend)
    assert stale["atoms"] == [[3, "S"]], (
        f"the setup did not reproduce the staleness, so this test would "
        f"prove nothing: {stale}"
    )

    backend.set_cip_labels(True)

    fixed = _wait_for_cip(qapp, backend, lambda labels: not labels["atoms"])
    assert fixed["atoms"] == [], "a descriptor outlived the centre it described"
    assert fixed["bonds"] == [[1, "E"]], "an untouched descriptor was lost"
    backend.widget().hide()


def test_turning_the_descriptors_off_takes_them_off_without_editing_anything(qapp):
    """Off has to mean off, and it must not cost an edit.

    A display toggle that fired Ketcher's `change` would reach
    `EditStructureCommand` and leave an undo step for switching a label
    off. Measured on the route this uses: 0 change events, and Ketcher's
    own history unmoved.
    """
    backend = _ready_backend(qapp, shown=True)
    backend.load_molblock(_CHIRAL_ALKENE)
    assert _wait_until(qapp, lambda: (_get_molblock_sync(qapp, backend) or "").strip() != "")
    _run_js_json(qapp, backend, """
      window.__changes = 0;
      window.ketcher.editor.subscribe('change', function () { window.__changes++; });
      window.__history = window.ketcher.editor.historySize().undo;
      return 1;
    """)

    backend.set_cip_labels(True)
    assert _wait_for_cip(qapp, backend, lambda labels: bool(labels["atoms"]))["atoms"]

    backend.set_cip_labels(False)

    gone = _wait_for_cip(qapp, backend, lambda labels: not labels["atoms"] and not labels["bonds"])
    assert gone == {"atoms": [], "bonds": []}, gone
    after = _run_js_json(qapp, backend, """
      return {changes: window.__changes,
              historyGrew: window.ketcher.editor.historySize().undo - window.__history};
    """)
    assert after == {"changes": 0, "historyGrew": 0}, (
        f"showing and hiding descriptors edited the structure: {after}. "
        f"Ketcher's own Calculate CIP button does exactly this -- measured, "
        f"1 change and history 3 -> 4 -- which is why this route does not "
        f"use it."
    )
    backend.widget().hide()


def _cip_work(qapp, backend) -> dict:
    return json.loads(_run_js_json(qapp, backend, "return window.openchemCip.work();"))


def test_switching_the_display_off_beats_a_calculation_already_in_flight(qapp):
    """The stale-answer race, and the one that would look like the toggle
    is broken.

    The calculation is a promise, so an answer is always in flight for a
    few frames. Turning the display off during that window must win: an
    answer landing afterwards would redraw exactly what the user just
    asked to remove, and only sometimes, which reads as a flaky toggle
    rather than as a race.

    Asserted through the page's own counters, because the superseded
    answer is discarded microseconds later and never reaches a screenshot
    -- the same reason `gridBuilds` exists for the conformer gallery.
    """
    backend = _ready_backend(qapp, shown=True)
    backend.load_molblock(_CHIRAL_ALKENE)
    assert _wait_until(qapp, lambda: (_get_molblock_sync(qapp, backend) or "").strip() != "")
    _run_js_json(qapp, backend, "window.openchemCip.resetWork(); return 1;")

    _run_js_json(
        qapp, backend,
        "window.openchemCip.refresh(); window.openchemCip.clear(); return 1;",
    )
    _wait_until(qapp, lambda: _cip_work(qapp, backend)["superseded"] > 0, timeout_seconds=15)

    work = _cip_work(qapp, backend)
    assert work["applied"] == 0, f"an answer landed after the display was switched off: {work}"
    assert work["superseded"] == 1, work
    assert _cip_labels(qapp, backend) == {"atoms": [], "bonds": []}
    backend.widget().hide()


def test_the_newer_of_two_calculations_is_the_one_that_lands(qapp):
    """Scrubbing an edit produces several refreshes with overlapping
    promises, and JavaScript makes no promise about resolution order. The
    older answer landing last would describe the structure as it was two
    edits ago, which is the bug this whole feature is about, reintroduced
    one layer down.
    """
    backend = _ready_backend(qapp, shown=True)
    backend.load_molblock(_CHIRAL_ALKENE)
    assert _wait_until(qapp, lambda: (_get_molblock_sync(qapp, backend) or "").strip() != "")
    _run_js_json(qapp, backend, "window.openchemCip.resetWork(); return 1;")

    _run_js_json(
        qapp, backend,
        "window.openchemCip.refresh(); window.openchemCip.refresh(); return 1;",
    )
    _wait_until(qapp, lambda: _cip_work(qapp, backend)["applied"] > 0, timeout_seconds=15)

    work = _cip_work(qapp, backend)
    assert work == {"refreshes": 2, "applied": 1, "superseded": 1, "failed": 0}, work
    assert _cip_labels(qapp, backend)["atoms"] == [[3, "S"]]
    backend.widget().hide()


def test_the_descriptors_are_queued_when_ketcher_is_not_ready_yet(qapp):
    """STATE, so it queues -- and the LAST request is the one that counts.

    On-then-off before the page boots is off, not two instructions to
    replay in order; the second assertion is the one a queue that appends
    would fail. Replayed after the structure, because a descriptor is
    computed FROM the atoms: onto an empty canvas it would compute nothing
    and never be asked again.
    """
    backend = KetcherEditorBackend()
    assert not backend._ketcher_ready

    backend.set_cip_labels(True)
    assert backend._pending_cip is True
    backend.set_cip_labels(False)
    assert backend._pending_cip is False, "the queue kept the first request, not the last"

    calls = _record_page_calls(backend, backend._on_ketcher_ready)

    assert len(calls) == 1 and "openchemCip.clear()" in calls[0], calls
    assert backend._pending_cip is None, "the queue was not emptied"


def test_a_load_queued_after_the_descriptors_still_wins(qapp):
    """The stale-state class this project keeps finding: molblock A, the
    descriptors, then molblock B, all before ready. B must be what loads
    and what the descriptors are computed for -- never A.

    It holds because `_pending_molblock` keeps only the last one and is
    replayed BEFORE the descriptors. Asserted rather than left to hold by
    construction, which is exactly the kind of thing that stops holding
    silently.
    """
    backend = KetcherEditorBackend()
    backend.load_molblock(_BENZENE)
    backend.set_cip_labels(True)
    backend.load_molblock(_CHIRAL_ALKENE)

    calls = _record_page_calls(backend, backend._on_ketcher_ready)

    structure = [i for i, c in enumerate(calls) if "setMolecule" in c]
    descriptors = [i for i, c in enumerate(calls) if "openchemCip" in c]
    assert structure and descriptors, calls
    assert len(structure) == 1, "both molblocks were replayed"
    assert _CHIRAL_ALKENE.strip().splitlines()[3] in calls[structure[0]].replace("\\n", "\n"), (
        "the SUPERSEDED molblock was the one replayed"
    )
    assert structure[0] < descriptors[0], (
        "the descriptors were computed before the structure they describe"
    )


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


def test_an_armed_atom_carries_its_mass_number(qapp):
    """**THE BUG ALEX REPORTED, at the line that caused it.**

    "I can place carbon 13, but it's just CH4, there's no 13." Ketcher
    renders isotopes perfectly well -- a molblock with `M  ISO` draws as
    `13C` -- so nothing was wrong downstream. The mass number was simply
    never part of the gesture: this method armed a bare label.
    """
    backend = _ready_backend(qapp)

    calls = _record_page_calls(backend, lambda: backend.set_atom_tool("C", 13))

    assert calls, "nothing reached the page"
    assert '"isotope": 13' in calls[0]
    assert '"label": "C"' in calls[0]


def test_an_ordinary_element_carries_NO_isotope_key(qapp):
    """**OMITTED, NOT SENT AS ZERO.** Measured against the real bundle,
    the tool keeps whatever `atomProps` it is handed -- so an isotope of 0
    would be a value Ketcher has to interpret, where an absent key is the
    payload it received before this change.
    """
    backend = _ready_backend(qapp)

    calls = _record_page_calls(backend, lambda: backend.set_atom_tool("C"))

    assert calls
    assert "isotope" not in calls[0]
    assert '"label": "C"' in calls[0]
