from __future__ import annotations

import json
import time

import pytest

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
def test_a_chain_qualified_key_reaches_mol_script_as_a_chain_term(qapp):
    """`"B/TYR652"` must become an `auth_asym_id` term, unquoted.

    The page is what builds the expression, so this asserts the KEY makes
    it across the bridge; `test_the_chain_term_actually_narrows_what_is_painted`
    is what establishes the expression then selects less.
    """
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)
    calls = _fired_js(backend)

    backend.apply_visualizations(
        [ResidueColorLayer(name="H-bonds", residue_colors={"B/TYR652": "#1976d2"})]
    )

    js = calls[-1]
    assert "B/TYR652" in js
    assert '"B"' not in js  # never a quoted chain id, for the same reason
    # as the residue name: quoting matches zero atoms and commits happily.
#: Two chains, identical residue numbering -- the collision the chain term
#: exists for, and the smallest structure that can show it.
#:
#: A single-chain receptor CANNOT fail this test, which is why the fixture
#: is synthetic rather than one of the cached deposits: 4DKL, the entry
#: most of the docking work was measured on, has one chain and zero key
#: collisions, so a guard built on it would pass with the fix reverted.
_TWO_CHAIN_PDB = """\
ATOM      1  N   GLN A  72      10.000  10.000  10.000  1.00  0.00           N
ATOM      2  CA  GLN A  72      11.500  10.000  10.000  1.00  0.00           C
ATOM      3  C   GLN A  72      12.500  11.000  10.000  1.00  0.00           C
ATOM      4  O   GLN A  72      13.500  11.000  10.500  1.00  0.00           O
ATOM      5  N   GLN B  72      10.000  20.000  10.000  1.00  0.00           N
ATOM      6  CA  GLN B  72      11.500  20.000  10.000  1.00  0.00           C
ATOM      7  C   GLN B  72      12.500  21.000  10.000  1.00  0.00           C
ATOM      8  O   GLN B  72      13.500  21.000  10.500  1.00  0.00           O
END
"""


def _selection_clauses(qapp, backend, residue_colors: dict) -> dict:
    """What the PAGE builds for these keys, through its own builder."""
    result: dict = {}
    backend._page.runJavaScript(
        "JSON.stringify(window.openchemMolstarViewer.residueSelectionClauses("
        + json.dumps(residue_colors)
        + "))",
        lambda value: result.__setitem__("value", value),
    )
    _wait_until(qapp, lambda: "value" in result, timeout_seconds=20)
    return json.loads(result.get("value") or "{}")


def test_a_chain_qualified_key_selects_only_that_chain(qapp):
    """The selection must carry the chain, and the bare form must not.

    Measured on 6WGT before this landed: the residue key `GLN72` resolves
    to chains A, B and C, so a pose docked against the boxed copy coloured
    all three -- and 370 of that deposit's 388 residue keys collide the
    same way. A single-chain receptor cannot show it, which is why it
    survived: 4DKL, the deposit most of the docking work was measured on,
    has one chain and zero collisions.

    THAT A CHAIN TERM REALLY NARROWS THE SELECTION WAS ESTABLISHED
    SEPARATELY AND LIVE, by painting a three-chain deposit and counting
    red pixels -- with a control asking for a chain that is not in the
    structure, which painted nothing. See CLAUDE.md. That measurement is
    what licenses this cheaper guard: the semantics are known, and what
    has to be defended from here is that the expression keeps being
    emitted.

    Unquoted for the same reason residue NAMES are: quoting matches zero
    atoms while the overpaint commits successfully.
    """
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)

    clauses = _selection_clauses(
        qapp, backend, {"B/GLN72": "#ff0000", "GLN72": "#00ff00"}
    )

    qualified = clauses["B/GLN72"]
    assert "auth_asym_id B" in qualified, qualified
    assert '"B"' not in qualified, qualified
    assert "auth_comp_id GLN" in qualified and "auth_seq_id 72" in qualified

    bare = clauses["GLN72"]
    assert "auth_asym_id" not in bare, bare
    assert "auth_comp_id GLN" in bare and "auth_seq_id 72" in bare


def test_the_colouring_and_the_diagnostic_share_one_builder():
    """Two implementations of "the selection for this residue" would drift.

    The seam above is only worth reading if it is the same code the viewer
    paints with, so `applyResidueColors` must not carry a selection regex
    of its own. Checked on the source, because the claim is about which
    code exists rather than about one runtime answer.
    """
    from pathlib import Path

    page = (
        Path(__file__).parent.parent
        / "src"
        / "openchem"
        / "resources"
        / "molstar"
        / "viewer.html"
    ).read_text(encoding="utf-8")

    assert page.count("auth_asym_id") == 1, (
        "the chain term is written in more than one place -- the colouring "
        "and the diagnostic must share `residueClause`"
    )
    body = page[page.index("applyResidueColors: function") :]
    body = body[: body.index("clearResidueColors")]
    assert "auth_comp_id" not in body, (
        "applyResidueColors builds its own selection instead of calling "
        "residueClause"
    )
    assert "residueClause(" in body


# --- the viewer must show the coordinates docking uses -----------------------
#
# Mol*'s default preset builds BIOLOGICAL ASSEMBLY 1, which is a different
# set of atoms from the deposited file this application hands to Vina.
# `showDepositedCoordinates()` in viewer.html exists to correct that, and
# until now NOTHING here tested it -- `deposited`, `assembly` and
# `structure-from-model` all matched zero lines in this file.
#
# Reported on 6WGT (5-HT2A): a tryptamine docked into chain B's orthosteric
# pocket, drawn against chain A, ~43 A away, looking "way outside the
# receptor". The box was measurably correct -- 0.0 A from the 7LD site,
# holding 217 receptor atoms.

#: TWO CHAINS AND AN ASSEMBLY THAT NAMES ONLY ONE, which is 6WGT's shape in
#: miniature: `REMARK 350` builds assembly 1 from chain A alone, so the
#: deposited file and the default preset disagree about what is on screen.
#: Chain B sits ~40 A away, as 6WGT's three copies do.
_TWO_CHAIN_PDB = """HEADER    TEST
REMARK 350 BIOMOLECULE: 1
REMARK 350 APPLY THE FOLLOWING TO CHAINS: A
REMARK 350   BIOMT1   1  1.000000  0.000000  0.000000        0.00000
REMARK 350   BIOMT2   1  0.000000  1.000000  0.000000        0.00000
REMARK 350   BIOMT3   1  0.000000  0.000000  1.000000        0.00000
ATOM      1  N   ALA A   1      11.104  13.207   2.845  1.00 20.00           N
ATOM      2  CA  ALA A   1      11.999  12.040   2.945  1.00 20.00           C
ATOM      3  C   ALA A   1      13.398  12.442   2.508  1.00 20.00           C
ATOM      4  O   ALA A   1      13.598  13.601   2.128  1.00 20.00           O
ATOM      5  CB  ALA A   1      11.482  10.895   2.076  1.00 20.00           C
ATOM      6  N   ALA B   1      51.104  53.207  42.845  1.00 20.00           N
ATOM      7  CA  ALA B   1      51.999  52.040  42.945  1.00 20.00           C
ATOM      8  C   ALA B   1      53.398  52.442  42.508  1.00 20.00           C
ATOM      9  O   ALA B   1      53.598  53.601  42.128  1.00 20.00           O
ATOM     10  CB  ALA B   1      51.482  50.895  42.076  1.00 20.00           C
END
"""


def _structure_transforms(qapp, backend) -> list[dict]:
    """Every committed `structure-from-model` transform, from the page.

    JSON over the bridge because `runJavaScript` on this Qt build returns
    PRIMITIVES ONLY -- an array comes back as `''`, indistinguishable from a
    script that returned nothing, which is already recorded in CLAUDE.md as
    having cost a whole probe run.
    """
    result: dict[str, object] = {}
    backend._page.runJavaScript(
        "window.openchemMolstarViewer.structureTransforms();",
        lambda value: result.__setitem__("value", value),
    )
    _wait_until(qapp, lambda: "value" in result, timeout_seconds=5)
    raw = result.get("value")
    return json.loads(raw) if raw else []


def _transform_names(transforms: list[dict]) -> list[str]:
    return sorted(
        (t.get("type") or {}).get("name", "<none>") for t in transforms
    )


def test_the_fixture_can_actually_show_the_difference(qapp):
    """THE DEGENERACY CHECK, and the two guards below are worthless without it.

    If Mol* does not build an assembly from this fixture's `REMARK 350` --
    because the annotation is minimal, or because its PDB reader ignores it
    -- then the default preset and the deposited coordinates AGREE, both
    guards below pass for free, and the file reads as three-way coverage of
    a bug it cannot see. That is the "a fixture is degenerate or not with
    respect to a specific mutation" failure this project records repeatedly.

    `load_additional_structure` is the untouched default preset: it is the
    one path that never calls `showDepositedCoordinates`. So whatever it
    reports here is what Mol* does when nobody corrects it.

    A FAILURE HERE IS ABOUT THE FIXTURE, NOT THE APPLICATION. If this says
    'model', this PDB cannot reproduce the reported defect and the guards
    below need a real multi-copy deposit instead.
    """
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)

    backend.load_additional_structure(_TWO_CHAIN_PDB, "pdb", "receptor")
    assert _wait_until(qapp, lambda: _structure_count(qapp, backend) == 1)

    transforms = _structure_transforms(qapp, backend)
    assert transforms, "the probe found no structure-from-model cell at all"
    assert _transform_names(transforms) == ["assembly"], (
        f"this fixture cannot demonstrate the defect: Mol*'s untouched "
        f"default preset already reports {_transform_names(transforms)} "
        f"rather than ['assembly'], so 'deposited' and 'assembly 1' are the "
        f"same picture here and the guards below prove nothing"
    )


def test_a_receptor_loaded_alone_is_shown_as_deposited(qapp):
    """The control, and the case the original fix was verified against.

    Loading a receptor by itself is the ONE path that was checked when
    `showDepositedCoordinates` was written, which is why the defect below
    survived it.
    """
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)

    backend.load_macromolecule(_TWO_CHAIN_PDB, "pdb")
    assert _wait_until(qapp, lambda: _structure_count(qapp, backend) == 1)

    assert _wait_until(
        qapp,
        lambda: _transform_names(_structure_transforms(qapp, backend)) == ["model"],
    ), (
        f"a receptor loaded alone should be retargeted to deposited "
        f"coordinates, got "
        f"{_transform_names(_structure_transforms(qapp, backend))}"
    )


def test_the_docking_sequence_leaves_the_receptor_on_deposited_coordinates(qapp):
    """THE REGRESSION THIS FILE WAS MISSING, and it is expected to FAIL first.

    `_on_docking_result_ready` loads the receptor and then, in the same
    breath, the best pose:

        load_macromolecule(receptor)      -> loadStructure
        load_additional_structure(pose)   -> loadAdditionalStructure

    `loadStructure` does all its work inside `plugin.clear().then(...)` and
    returns immediately; `loadAdditionalStructure` has no such wrapper and
    runs synchronously. So the second load can interleave into the middle of
    the first, and `showDepositedCoordinates` -- which keeps the LAST
    matching cell -- can retarget the POSE while leaving the RECEPTOR on
    assembly 1. Retargeting a single-ligand structure is a no-op, so nothing
    anywhere reports a problem and the receptor is drawn ~43 A from its own
    search box.

    THE SETUP IS ASSERTED FIRST, deliberately. A failure because the page
    never loaded looks identical to one that caught the defect, and this
    project has repeatedly shipped guards that were green while testing
    nothing.

    The second structure is another PDB rather than a molblock: what matters
    is that a SECOND `structure-from-model` cell exists during the first
    load's promise chain, and `_MINIMAL_PDB` is already proven to parse here
    -- a molblock that failed to load would fail this test for a reason
    having nothing to do with the defect.
    """
    backend = MolStarViewerBackend()
    assert _wait_until(qapp, lambda: backend._viewer_ready)

    backend.load_macromolecule(_TWO_CHAIN_PDB, "pdb")
    backend.load_additional_structure(_MINIMAL_PDB, "pdb", "docked ligand")

    # Setup: both structures really did load. Without this, a page that
    # dropped one would report a single clean 'model' and pass.
    assert _wait_until(qapp, lambda: _structure_count(qapp, backend) == 2), (
        f"expected the receptor and the pose to both be loaded, got "
        f"{_structure_count(qapp, backend)} structure(s) -- the pose may "
        f"have been wiped by loadStructure's plugin.clear()"
    )

    transforms = _structure_transforms(qapp, backend)
    assert len(transforms) == 2, (
        f"expected one structure-from-model transform per structure, got "
        f"{transforms}"
    )

    names = _transform_names(transforms)
    assert "assembly" not in names, (
        f"a structure was left on a biological assembly after the docking "
        f"sequence: transforms are {names} (full state: {transforms}). The "
        f"receptor is being drawn as assembly 1 while the search box and the "
        f"pose are in deposited coordinates -- on 6WGT that is ~43 A apart, "
        f"which is the reported 'docked outside the receptor'."
    )


def _viewer_source() -> str:
    from pathlib import Path

    return (
        Path(__file__).parent.parent
        / "src"
        / "openchem"
        / "resources"
        / "molstar"
        / "viewer.html"
    ).read_text(encoding="utf-8")


# --- the three rules below are asserted on the SOURCE, and here is why ------
#
# MEASURED, by mutation, after the ordering fix landed: reverting
# `showDepositedCoordinates` to last-match-wins, making it retarget EVERY
# structure, and deleting the pose's generation check are all EQUIVALENT
# MUTATIONS through the public API -- each one leaves the full 25-test file
# green.
#
# They are equivalent for one reason, and it is worth knowing before anybody
# "simplifies" this page: `loadStructure` calls `plugin.clear()`, and the
# loads are serialized, so at the moment `showDepositedCoordinates` runs the
# scene contains NOTHING BUT the structure that load just created. There is
# no reachable state in which picking the last cell, picking every cell, and
# picking the one we loaded give different answers. The queue removed the
# condition the other two rules defend against.
#
# So the honest position is: ONE change is load-bearing today -- queueing the
# additional structure, which `test_the_docking_sequence_...` above catches
# and nothing else does. The rest is defence in depth, and it is kept rather
# than deleted because each rule becomes load-bearing again the moment
# `loadStructure` stops clearing, or a load path that does not go through the
# queue is added. Both are ordinary future edits.
#
# Asserting the SHAPE is what this project does with a rule whose failure is
# unreachable -- "an unreachable branch is a question about where to assert,
# not automatically dead code". These are deliberately not dressed up as
# behavioural coverage they do not have.


def test_showDepositedCoordinates_retargets_only_the_refs_it_is_given():
    """It must not go looking for structures of its own.

    The version that shipped walked every `structure-from-model` cell and
    kept the LAST, which is how a docked pose came to be retargeted while
    the receptor was left on assembly 1. "Some cell got retargeted" is true
    under both the right rule and the wrong one, which is exactly why that
    form cannot be guarded behaviourally.
    """
    page = _viewer_source()
    body = page[page.index("function showDepositedCoordinates") :]
    body = body[: body.index("\n      var SEARCH_BOX_COLOR")]

    assert "function showDepositedCoordinates(refs)" in body, (
        "showDepositedCoordinates no longer takes the refs it is to "
        "retarget, so it is choosing its own targets again"
    )
    assert "state.data.cells" not in body, (
        "showDepositedCoordinates walks the state tree itself instead of "
        "retargeting what its caller loaded"
    )


def test_the_receptor_load_claims_only_the_structures_it_created():
    """Ownership is a DIFF over the state tree, not a guess.

    `loadStructureFromData`'s return shape is not relied on: this project's
    standing rule is that a Mol* API is probed against the vendored bundle
    rather than assumed, and that rule was earned on this very call, whose
    `structure` option is accepted and silently ignored.
    """
    page = _viewer_source()
    body = page[page.index("loadStructure: function") :]
    body = body[: body.index("loadAdditionalStructure: function")]

    assert "var before = structureFromModelRefs();" in body, (
        "the load no longer snapshots the structures present beforehand, so "
        "it cannot tell which structure it created"
    )
    assert "before.indexOf(ref) === -1" in body, (
        "the load hands showDepositedCoordinates every structure rather "
        "than the ones it added"
    )


def test_an_additional_structure_is_bound_to_the_load_that_owns_it():
    """The generation is read at REQUEST time, and that is the whole point.

    Reading it when the step RUNS would always find the newest receptor and
    the binding would say nothing -- a pose would attach to whatever was
    current by then, which is the bug this rule exists to prevent.
    """
    page = _viewer_source()
    body = page[page.index("loadAdditionalStructure: function") :]
    body = body[: body.index("clear: function")]

    assert "var generation = loadGeneration;" in body, (
        "the pose no longer records which receptor load it belongs to"
    )
    assert "queueLoad(" in body, (
        "the pose is not queued behind the receptor load -- this is the one "
        "rule here with behavioural coverage, and it is the reported defect"
    )
    # Capturing the generation and never comparing it is a variable nothing
    # reads: measured, deleting this line alone leaves every other guard in
    # this file green.
    assert "if (generation !== loadGeneration) { return; }" in body, (
        "the pose records which receptor it belongs to and then draws "
        "itself regardless -- a pose against a receptor it was never "
        "docked into looks entirely plausible and is the wrong answer"
    )
    generation_capture = body.index("var generation = loadGeneration;")
    assert body.index("queueLoad(") > generation_capture, (
        "the generation is captured inside the queued step rather than when "
        "the pose was requested, so the binding names the newest receptor "
        "instead of the one this pose was computed for"
    )
