from __future__ import annotations

import json
import time

from openchem.ui.visualization import ResidueColorLayer, VisualizationLayer
from openchem.ui.widgets.molstar_viewer_backend import _NOTHING_PENDING, MolStarViewerBackend

# A minimal, self-contained single-residue PDB — no network access needed.
# Confirmed against the real (offscreen-platform) Mol* viewer during the
# 6.3 spike: WebGL context-lost errors are logged under QT_QPA_PLATFORM=
# offscreen (no real GPU surface to render into), but Mol*'s structure
# state management (parsing, loading, clearing) is unaffected by that —
# a separate concern from 3D canvas compositing.
_MINIMAL_PDB = """HEADER    TEST
ATOM      1  N   ALA A   1      11.104  13.207   2.845  1.00 20.00           N
ATOM      2  CA  ALA A   1      11.999  12.040   2.945  1.00 20.00           C
ATOM      3  C   ALA A   1      13.398  12.442   2.508  1.00 20.00           C
ATOM      4  O   ALA A   1      13.598  13.601   2.128  1.00 20.00           O
ATOM      5  CB  ALA A   1      11.482  10.895   2.076  1.00 20.00           C
END
"""

_STRUCTURE_COUNT_JS = (
    "viewer && viewer.plugin ? "
    "viewer.plugin.managers.structure.hierarchy.current.structures.length : null"
)


def _pump(qapp, seconds: float) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)


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


def _structure_count(qapp, backend) -> object:
    """Runs `_STRUCTURE_COUNT_JS` and waits for its (async) result."""
    result: dict[str, object] = {}
    backend._page.runJavaScript(_STRUCTURE_COUNT_JS, lambda value: result.__setitem__("value", value))
    _wait_until(qapp, lambda: "value" in result, timeout_seconds=5)
    return result.get("value")


def test_viewer_becomes_ready(qapp):
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)


def test_load_macromolecule_adds_a_structure(qapp):
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)

    backend.load_macromolecule(_MINIMAL_PDB, "pdb")
    assert _wait_until(qapp, lambda: _structure_count(qapp, backend) == 1)


def test_load_before_ready_is_queued_and_applied_once_ready(qapp):
    backend = MolStarViewerBackend()
    # Call before waiting for _viewer_ready -- exercises the pending-call
    # queue (backend._pending_call), not just the already-ready path.
    backend.load_macromolecule(_MINIMAL_PDB, "pdb")

    assert _wait_until(qapp, lambda: _structure_count(qapp, backend) == 1, timeout_seconds=20)


def test_clear_removes_loaded_structure(qapp):
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)
    backend.load_macromolecule(_MINIMAL_PDB, "pdb")
    assert _wait_until(qapp, lambda: _structure_count(qapp, backend) == 1)

    backend.clear()
    assert _wait_until(qapp, lambda: _structure_count(qapp, backend) == 0)


# --- Phase 24: residue-target visualization layers ---------------------------


def _fired_js(backend: MolStarViewerBackend) -> list[str]:
    """Records the JS this backend emits, so ordering and syntax can be
    asserted without needing to read pixels back out of Mol*."""
    calls: list[str] = []
    original = backend._page.runJavaScript
    backend._page.runJavaScript = lambda js, *a, **k: (calls.append(js), original(js, *a, **k))[1]
    return calls


def test_residue_colors_applied_before_the_viewer_exists_are_replayed(qapp):
    """Regression test. Mol*'s viewer is created asynchronously, so a
    colouring applied in the same breath as loading a structure would fire
    into nothing -- the identical bug that left the Calculator Inspector's
    3D pane uncoloured, and which was reintroduced here once already
    before this test existed."""
    backend = MolStarViewerBackend()
    calls = _fired_js(backend)

    backend.load_macromolecule(_MINIMAL_PDB, "pdb")
    backend.apply_visualizations([ResidueColorLayer(name="H-bonds", residue_colors={"ALA1": "#1976d2"})])
    assert calls == []  # nothing escaped to a viewer that does not exist yet

    assert _wait_until(qapp, lambda: backend._viewer_ready)
    assert _wait_until(qapp, lambda: len(calls) >= 2)

    # Order matters: overpaint attaches to a representation that does not
    # exist until its structure is loaded.
    assert "loadStructure" in calls[0]
    assert "applyResidueColors" in calls[1]
    assert backend._pending_layers is _NOTHING_PENDING  # consumed, not left queued


def test_residue_names_are_passed_unquoted_to_mol_script(qapp):
    """The syntax that actually matches. Quoting a residue name makes the
    selection match ZERO atoms while the overpaint still commits
    successfully -- a silent failure confirmed interactively, and the
    reason an earlier attempt wrongly concluded Mol* colouring was
    unavailable."""
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)
    calls = _fired_js(backend)

    backend.apply_visualizations([ResidueColorLayer(name="H-bonds", residue_colors={"TYR652": "#1976d2"})])

    js = calls[-1]
    assert '"TYR"' not in js  # never a quoted residue NAME
    assert "TYR652" in js


def test_atom_layers_are_ignored_by_the_macromolecule_viewer(qapp):
    """Per ViewerBackend.apply_visualizations' contract: a backend renders
    the target kinds it can. Per-atom scientific data has no meaning
    against a receptor-sized structure, so it clears rather than raises."""
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)
    calls = _fired_js(backend)

    backend.apply_visualizations([VisualizationLayer(name="LogP", atom_colors={0: "#ff0000"})])

    assert "clearResidueColors" in calls[-1]


def test_several_residue_layers_composite_with_later_layers_winning(qapp):
    """build_interaction_layers emits clashes after H-bonds precisely so a
    residue doing both ends up flagged with the problem."""
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)
    calls = _fired_js(backend)

    backend.apply_visualizations([
        ResidueColorLayer(name="H-bonds", residue_colors={"TYR652": "#1976d2"}),
        ResidueColorLayer(name="Clashes", residue_colors={"TYR652": "#d32f2f"}),
    ])

    js = calls[-1]
    assert "#d32f2f" in js  # the clash colour won
    assert "#1976d2" not in js


def test_empty_layer_list_clears(qapp):
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)
    calls = _fired_js(backend)

    backend.apply_visualizations([])

    assert "clearResidueColors" in calls[-1]


def test_a_queued_clear_is_not_lost(qapp):
    """Regression test for an ambiguous sentinel: None is a real queued
    VALUE here (meaning "clear"), so using None as the also-means-empty
    marker silently dropped clears requested before the viewer existed."""
    backend = MolStarViewerBackend()
    calls = _fired_js(backend)

    backend.load_macromolecule(_MINIMAL_PDB, "pdb")
    backend.apply_visualizations([])  # queued clear, viewer not ready yet
    assert calls == []

    assert _wait_until(qapp, lambda: backend._viewer_ready)
    assert _wait_until(qapp, lambda: any("clearResidueColors" in js for js in calls))


# --- the docking search box --------------------------------------------------
#
# Drawn so a misplaced box is VISIBLE rather than only reported: the failure
# that motivated it was a search box 55 A off site that nobody could see.

_OWNED_BOX_SHAPES_JS = (
    "(function(){var n=0;viewer.plugin.state.data.cells.forEach(function(c){"
    "if(/box-shape/i.test(c.transform.transformer.id||String())) n++;});return n;})()"
)


def _js_value(qapp, backend, script):
    result: dict[str, object] = {}
    backend._page.runJavaScript(script, lambda value: result.__setitem__("value", value))
    _wait_until(qapp, lambda: "value" in result, timeout_seconds=5)
    return result.get("value")


def _search_box_state(qapp, backend):
    """The page's COMMITTED box state.

    Deliberately not the last value Python sent. A state read that echoed
    the request back would hand these tests their own input and pass while
    nothing had been committed -- this file's own "queued but never
    rendered" failure in a new place.
    """
    raw = _js_value(qapp, backend, "window.openchemMolstarViewer.searchBoxState()")
    return json.loads(raw) if raw else {}


def _owned_box_shapes(qapp, backend):
    """How many box shapes are IN THE SCENE.

    Counted on the scene rather than from the page's own refs, and that
    distinction caught a real bug: the first implementation reported exactly
    one box while leaving THREE in the state tree, because each replacement
    built its delete from a ref the previous commit had not yet landed, so
    the delete silently no-opped and the orphan stayed.
    """
    return _js_value(qapp, backend, _OWNED_BOX_SHAPES_JS)


def test_a_search_box_is_drawn_and_reports_its_committed_geometry(qapp):
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)
    backend.load_macromolecule(_MINIMAL_PDB, "pdb")
    assert _wait_until(qapp, lambda: _structure_count(qapp, backend) == 1)

    backend.show_search_box((1.0, 2.0, 3.0), (12.0, 10.0, 8.0))

    assert _wait_until(qapp, lambda: _search_box_state(qapp, backend).get("present") is True)
    state = _search_box_state(qapp, backend)
    assert state["center"] == [1.0, 2.0, 3.0]
    assert state["size"] == [12.0, 10.0, 8.0]


def test_clearing_leaves_no_box_AND_no_stale_geometry(qapp):
    """`present=False` must null the geometry.

    Returning the last centre beside `present: false` would let a caller
    keep reading coordinates off a box that is not there -- and a test doing
    the same would pass.
    """
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)
    backend.show_search_box((1.0, 2.0, 3.0), (12.0, 10.0, 8.0))
    assert _wait_until(qapp, lambda: _search_box_state(qapp, backend).get("present") is True)

    backend.clear_search_box()

    assert _wait_until(qapp, lambda: _search_box_state(qapp, backend).get("present") is False)
    state = _search_box_state(qapp, backend)
    assert state["center"] is None and state["size"] is None
    assert _wait_until(qapp, lambda: _owned_box_shapes(qapp, backend) == 0)


def test_a_burst_of_requests_leaves_exactly_the_LAST_one_drawn(qapp):
    """Latest-state-wins, asserted ON THE SCENE.

    Issued back to back rather than as three settled steps: the settled
    version is a weaker claim that passes against an implementation with no
    supersession at all. The first version of this page passed the geometry
    assertion below and left three boxes in the scene, which is why the
    shape count is here.
    """
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)
    backend.load_macromolecule(_MINIMAL_PDB, "pdb")
    assert _wait_until(qapp, lambda: _structure_count(qapp, backend) == 1)

    backend.show_search_box((20.0, 20.0, 20.0), (4.0, 4.0, 4.0))
    backend.show_search_box((-20.0, -20.0, -20.0), (4.0, 4.0, 4.0))
    backend.show_search_box((0.0, 0.0, 0.0), (14.0, 12.0, 12.0))

    assert _wait_until(
        qapp, lambda: _search_box_state(qapp, backend).get("center") == [0.0, 0.0, 0.0]
    )
    assert _wait_until(qapp, lambda: _owned_box_shapes(qapp, backend) == 1), (
        "a superseded box was left in the scene"
    )


def test_a_clear_racing_a_show_ends_on_whichever_came_last(qapp):
    """Both orders, because they fail differently."""
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)

    backend.show_search_box((9.0, 9.0, 9.0), (6.0, 6.0, 6.0))
    backend.clear_search_box()
    assert _wait_until(qapp, lambda: _search_box_state(qapp, backend).get("present") is False)

    backend.clear_search_box()
    backend.show_search_box((1.0, 2.0, 3.0), (8.0, 8.0, 8.0))
    assert _wait_until(
        qapp, lambda: _search_box_state(qapp, backend).get("center") == [1.0, 2.0, 3.0]
    )


def test_a_box_requested_before_the_viewer_exists_is_replayed(qapp):
    backend = MolStarViewerBackend()
    # No readiness wait: this is the queued path.
    backend.show_search_box((4.0, 5.0, 6.0), (10.0, 10.0, 10.0))

    assert _wait_until(
        qapp,
        lambda: _search_box_state(qapp, backend).get("center") == [4.0, 5.0, 6.0],
        timeout_seconds=20,
    )


def test_a_CLEAR_requested_before_the_viewer_exists_is_not_lost(qapp):
    """The sentinel's whole reason for existing.

    None is a meaningful queued VALUE here meaning "clear", so it cannot
    double as the empty marker -- using it for both silently drops queued
    clears, which is why `_NOTHING_PENDING` exists on this slot and on
    `_pending_layers`.
    """
    backend = MolStarViewerBackend()
    backend.show_search_box((4.0, 5.0, 6.0), (10.0, 10.0, 10.0))
    backend.clear_search_box()
    assert backend._pending_search_box is None, "a queued clear must not read as 'nothing queued'"
    assert backend._pending_search_box is not _NOTHING_PENDING

    assert _wait_until(qapp, lambda: backend._viewer_ready, timeout_seconds=20)
    assert _wait_until(qapp, lambda: _search_box_state(qapp, backend).get("present") is False)


def test_the_box_survives_loading_another_structure(qapp):
    """`loadStructure` calls `plugin.clear()`, emptying the whole state tree
    -- so the box is gone and the page's refs dangle.

    Found while wiring this. Without the reset-and-restore in
    `loadStructure`, the page kept reporting a box that no longer existed
    and the next replacement deleted refs resolving to nothing. The DESIRED
    box survives on purpose, so loading a receptor redraws its search region
    without the window having to sequence the two calls.
    """
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)
    backend.load_macromolecule(_MINIMAL_PDB, "pdb")
    assert _wait_until(qapp, lambda: _structure_count(qapp, backend) == 1)
    backend.show_search_box((0.0, 0.0, 0.0), (12.0, 10.0, 10.0))
    assert _wait_until(qapp, lambda: _search_box_state(qapp, backend).get("present") is True)

    backend.load_macromolecule(_MINIMAL_PDB, "pdb")

    assert _wait_until(qapp, lambda: _structure_count(qapp, backend) == 1)
    assert _wait_until(qapp, lambda: _search_box_state(qapp, backend).get("present") is True)
    assert _wait_until(qapp, lambda: _owned_box_shapes(qapp, backend) == 1), (
        "the restored box must replace the dangling one, not join it"
    )
