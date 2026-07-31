from __future__ import annotations

import time

from openchem.ui.visualization import ResidueColorLayer, VisualizationLayer
from openchem.ui.widgets.molstar_viewer_backend import MolStarViewerBackend

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


def _wait_until(qapp, predicate, timeout_seconds: float = 15) -> bool:
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
    assert backend._pending_layers is None


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
