from __future__ import annotations

import json
import time

from openchem.ui.widgets.ketcher_editor_backend import KetcherEditorBackend


def _wait_until(qapp, predicate, timeout_seconds: float = 15) -> bool:
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


def test_set_render_option_before_ketcher_is_ready_does_not_raise(qapp):
    backend = KetcherEditorBackend()
    backend.set_render_option("showHydrogenLabels", "All")  # must not raise even pre-ready


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


def test_trigger_toolbar_action_before_ketcher_is_ready_does_not_raise(qapp):
    backend = KetcherEditorBackend()
    backend.trigger_toolbar_action("Add/Remove explicit hydrogens button")  # must not raise


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
