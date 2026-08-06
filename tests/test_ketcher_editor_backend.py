from __future__ import annotations

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
