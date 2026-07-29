from __future__ import annotations

import time

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
