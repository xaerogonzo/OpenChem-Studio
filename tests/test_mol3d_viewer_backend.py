from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.ui.visualization import (
    SurfaceLayer,
    VisualizationLayer,
    build_scalar_field_surface_layer,
)
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend

_CURRENT_VISUALIZATION_JS = "JSON.stringify(currentVisualization)"


def _ethanol_molblock() -> str:
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    return Chem.MolToMolBlock(mol)


def _wait_until(qapp, predicate, timeout_seconds: float = 15) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _run_js(qapp, backend: Mol3DViewerBackend, script: str, timeout_seconds: float = 5) -> object:
    result: dict[str, object] = {}
    backend._page.runJavaScript(script, lambda value: result.__setitem__("value", value))
    _wait_until(qapp, lambda: "value" in result, timeout_seconds=timeout_seconds)
    return result.get("value")


def _current_visualization(qapp, backend: Mol3DViewerBackend) -> object:
    return _run_js(qapp, backend, _CURRENT_VISUALIZATION_JS)


def _ready_backend(qapp) -> Mol3DViewerBackend:
    backend = Mol3DViewerBackend()
    assert _wait_until(qapp, lambda: backend._page_ready)
    backend.load_conformer(_ethanol_molblock())
    return backend


def test_apply_visualization_sets_atom_colors(qapp):
    backend = _ready_backend(qapp)

    layer = VisualizationLayer(name="LogP contribution", atom_colors={0: "#d32f2f", 1: "#1976d2"})
    backend.apply_visualization(layer)

    assert _wait_until(qapp, lambda: _current_visualization(qapp, backend) not in (None, "null"))
    raw = _current_visualization(qapp, backend)
    assert '"0":"#d32f2f"' in raw
    assert '"1":"#1976d2"' in raw


def test_apply_visualization_none_clears(qapp):
    backend = _ready_backend(qapp)
    backend.apply_visualization(VisualizationLayer(name="test", atom_colors={0: "#d32f2f"}))
    assert _wait_until(qapp, lambda: _current_visualization(qapp, backend) not in (None, "null"))

    backend.apply_visualization(None)

    assert _wait_until(qapp, lambda: _current_visualization(qapp, backend) == "null")


def test_apply_visualization_empty_colors_clears(qapp):
    backend = _ready_backend(qapp)

    backend.apply_visualization(VisualizationLayer(name="empty", atom_colors={}))

    assert _wait_until(qapp, lambda: _current_visualization(qapp, backend) == "null")


def test_loading_a_new_molecule_clears_previous_visualization(qapp):
    backend = _ready_backend(qapp)
    backend.apply_visualization(VisualizationLayer(name="test", atom_colors={0: "#d32f2f"}))
    assert _wait_until(qapp, lambda: _current_visualization(qapp, backend) not in (None, "null"))

    backend.load_conformer(_ethanol_molblock())

    assert _wait_until(qapp, lambda: _current_visualization(qapp, backend) == "null")


def test_apply_visualization_with_labels_adds_a_3dmol_label_per_atom(qapp):
    backend = _ready_backend(qapp)
    layer = VisualizationLayer(
        name="LogP contribution", atom_colors={0: "#d32f2f", 1: "#1976d2"}, atom_labels={0: "-0.50", 1: "+0.50"}
    )

    backend.apply_visualization(layer)

    def label_count() -> object:
        return _run_js(qapp, backend, "viewer.getNumLabels ? viewer.getNumLabels() : viewer.labels.length")

    assert _wait_until(qapp, lambda: label_count() == 2)


def test_clear_visualization_removes_labels(qapp):
    backend = _ready_backend(qapp)
    layer = VisualizationLayer(name="test", atom_colors={0: "#d32f2f"}, atom_labels={0: "+0.50"})
    backend.apply_visualization(layer)

    def label_count() -> object:
        return _run_js(qapp, backend, "viewer.getNumLabels ? viewer.getNumLabels() : viewer.labels.length")

    assert _wait_until(qapp, lambda: label_count() == 1)

    backend.apply_visualization(None)

    assert _wait_until(qapp, lambda: label_count() == 0)


def test_visualization_applied_before_the_page_loads_is_replayed(qapp):
    """Regression test for the real bug behind the Calculator Inspector's
    uncoloured 3D pane: CalculatorInspectorDialog constructs a fresh
    backend and calls load_conformer + apply_visualization synchronously in
    __init__, long before loadFinished. load_conformer already deferred via
    _pending_molblock, but apply_visualization fired runJavaScript into a
    dead page and was silently discarded, with nothing replaying it -- so
    the 3D view was ALWAYS uncoloured there while the 2D pane (synchronous
    RDKit SVG) rendered colours fine."""
    backend = Mol3DViewerBackend()
    assert not backend._page_ready  # exactly the inspector's situation

    backend.load_conformer(_ethanol_molblock())
    backend.apply_visualization(
        VisualizationLayer(name="LogP", atom_colors={0: "#ff0000", 1: "#0000ff"})
    )

    assert _wait_until(qapp, lambda: backend._page_ready)
    assert _wait_until(qapp, lambda: _current_visualization(qapp, backend) not in (None, "null"))
    assert backend._pending_layer is None  # consumed, not left queued forever


def test_multiple_atom_layers_composite_with_later_layers_winning(qapp):
    """Phase 23: several simultaneous layers merge into one colour map,
    later layers overriding earlier ones where they overlap."""
    backend = _ready_backend(qapp)
    fired: list[str] = []
    original = backend._page.runJavaScript
    backend._page.runJavaScript = lambda js, *a, **k: (fired.append(js), original(js, *a, **k))[1]

    backend.apply_visualizations([
        VisualizationLayer(name="LogP", atom_colors={0: "#ff0000", 1: "#00ff00"}, atom_labels={0: "+1"}),
        VisualizationLayer(name="Charge", atom_colors={1: "#0000ff", 2: "#ffff00"}),
    ])

    js = fired[-1]
    assert '"1": "#0000ff"' in js  # the later layer won this atom
    assert '"0": "#ff0000"' in js  # untouched by the later layer
    assert '"2": "#ffff00"' in js
    assert '"0": "+1"' in js  # labels merged too


def test_a_residue_layer_alone_is_ignored_by_the_small_molecule_viewer(qapp):
    """3Dmol.js renders conformers, which have no residues -- an
    unrenderable layer is ignored rather than raising, so callers need not
    know which backend they are talking to."""
    from openchem.ui.visualization import ResidueColorLayer

    backend = _ready_backend(qapp)
    fired: list[str] = []
    original = backend._page.runJavaScript
    backend._page.runJavaScript = lambda js, *a, **k: (fired.append(js), original(js, *a, **k))[1]

    backend.apply_visualizations([ResidueColorLayer(name="H-bonds", residue_colors={"TYR652": "#1976d2"})])

    assert "clearVisualization" in fired[-1]


def test_apply_visualizations_with_an_empty_list_clears(qapp):
    backend = _ready_backend(qapp)
    fired: list[str] = []
    original = backend._page.runJavaScript
    backend._page.runJavaScript = lambda js, *a, **k: (fired.append(js), original(js, *a, **k))[1]

    backend.apply_visualizations([])

    assert "clearVisualization" in fired[-1]


def test_single_layer_keeps_its_color_scale_but_a_composite_does_not(qapp):
    """One legend can only describe one scale honestly."""
    from openchem.ui.visualization import ColorScale

    scale = ColorScale(palette=[(0.0, "#ff0000"), (1.0, "#0000ff")], domain_min=0.0, domain_max=1.0)
    backend = _ready_backend(qapp)
    captured: list = []
    backend._run_apply_visualization = captured.append

    backend.apply_visualizations([VisualizationLayer(name="A", atom_colors={0: "#ff0000"}, color_scale=scale)])
    assert captured[-1].color_scale is scale

    backend.apply_visualizations([
        VisualizationLayer(name="A", atom_colors={0: "#ff0000"}, color_scale=scale),
        VisualizationLayer(name="B", atom_colors={1: "#0000ff"}, color_scale=scale),
    ])
    assert captured[-1].color_scale is None


def test_pending_visualization_is_replayed_after_the_molblock_not_before(qapp):
    """Order matters: viewer.html's loadMolblock() resets any active
    visualization, so replaying a queued layer before the queued molblock
    would immediately undo it."""
    backend = Mol3DViewerBackend()
    fired: list[str] = []
    original = backend._page.runJavaScript
    backend._page.runJavaScript = lambda js, *a, **k: (fired.append(js), original(js, *a, **k))[1]

    backend.load_conformer(_ethanol_molblock())
    backend.apply_visualization(VisualizationLayer(name="t", atom_colors={0: "#ff0000"}))
    assert fired == []  # nothing escaped to a page that isn't ready

    assert _wait_until(qapp, lambda: len(fired) >= 2)
    assert "loadMolblock" in fired[0]
    assert "applyVisualization" in fired[1]


_SURFACE_STATE_JS = "JSON.stringify(currentSurface)"


def _current_surface(qapp, backend: Mol3DViewerBackend) -> object:
    return _run_js(qapp, backend, _SURFACE_STATE_JS)


def test_apply_surface_sets_the_surface_state(qapp):
    backend = _ready_backend(qapp)

    backend.apply_surface(SurfaceLayer(name="vdW", representation="vdw", opacity=0.8))

    assert _wait_until(qapp, lambda: _current_surface(qapp, backend) not in (None, "null"))
    raw = _current_surface(qapp, backend)
    assert '"representation":"vdw"' in raw
    assert '"opacity":0.8' in raw


def test_apply_surface_carries_per_atom_colors(qapp):
    """Confirmed live that 3Dmol's colorfunc is invoked once per atom and
    surface vertices take the nearest atom's colour -- that's what maps a
    property like partial charge onto the surface."""
    backend = _ready_backend(qapp)

    backend.apply_surface(
        SurfaceLayer(name="Charge", representation="sas", atom_colors={0: "#d32f2f", 2: "#1976d2"})
    )

    assert _wait_until(qapp, lambda: _current_surface(qapp, backend) not in (None, "null"))
    raw = _current_surface(qapp, backend)
    assert '"0":"#d32f2f"' in raw
    assert '"2":"#1976d2"' in raw


def _tiny_field():
    """A dipole: -1 e at the origin, +1 e four Angstrom away. Chosen over
    a real molecule's charges because the SIGN at each end is then beyond
    argument, and a low resolution keeps the OpenDX text small enough to
    read back through runJavaScript in a test."""
    from openchem.chem.scalar_field import electrostatic_potential

    return electrostatic_potential(
        [(0.0, 0.0, 0.0), (4.0, 0.0, 0.0)], [-1.0, 1.0], resolution=8, padding=3.0
    )


def test_a_scalar_field_reaches_the_page_with_its_colour_range(qapp):
    backend = _ready_backend(qapp)

    layer = build_scalar_field_surface_layer(_tiny_field(), representation="vdw")
    backend.apply_surface(layer)

    assert _wait_until(qapp, lambda: _current_surface(qapp, backend) not in (None, "null"))
    raw = _current_surface(qapp, backend)
    assert "gridpositions counts 8 8 8" in raw
    low, high = layer.scalar_field_range
    assert low == -high, "the range must stay centred on zero through the round trip"
    assert f'"low":{low}' in raw


def test_the_field_is_handed_to_3dmol_as_volume_data_not_atom_colours(qapp):
    """The branch that matters, asserted where it can be: 3Dmol must
    receive a real `VolumeData` plus an RWB gradient, NOT the per-atom
    `colorfunc` path.

    It stops there rather than checking the drawn vertices because this
    backend's page is never shown, so no WebGL runs and the surface's
    `geometryGroups` stays empty -- the same never-painted trap CLAUDE.md
    records for `repaint()`. That the vertices genuinely follow the field
    was established live instead, in a visible browser: acetic acid's
    surface came back with 94 distinct colours over 302 vertices, and
    correlating each rendered vertex colour against the potential at its
    own position gave r = -0.95 (negative because RWB puts red at the low
    end) with not one vertex coloured with the wrong sign.
    """
    backend = _ready_backend(qapp)
    _run_js(
        qapp,
        backend,
        """
        window.__surfaceStyle = null;
        var original = viewer.addSurface.bind(viewer);
        viewer.addSurface = function (type, style) {
          window.__surfaceStyle = {
            voldata: style.voldata ? style.voldata.constructor.name : null,
            volscheme: style.volscheme ? style.volscheme.constructor.name : null,
            hasColorfunc: !!style.colorfunc,
          };
          return original(type, style);
        };
        """,
    )

    backend.apply_surface(
        build_scalar_field_surface_layer(_tiny_field(), representation="vdw")
    )

    assert _wait_until(
        qapp,
        lambda: _run_js(qapp, backend, "JSON.stringify(window.__surfaceStyle)")
        not in (None, "null"),
    )
    style = json.loads(_run_js(qapp, backend, "JSON.stringify(window.__surfaceStyle)"))
    assert style["voldata"] == "VolumeData"
    assert style["volscheme"] == "RWB"
    assert not style["hasColorfunc"], "a field must not also install nearest-atom colouring"


def test_a_field_wins_over_per_atom_colours_when_both_are_given(qapp):
    """They are not two settings to combine -- one is a step function over
    the atoms and the other is continuous, so showing both is impossible
    and the more specific request has to win."""
    backend = _ready_backend(qapp)
    _run_js(
        qapp,
        backend,
        "window.__usedColorfunc = null;"
        "var original = viewer.addSurface.bind(viewer);"
        "viewer.addSurface = function (t, s) { window.__usedColorfunc = !!s.colorfunc;"
        " return original(t, s); };",
    )

    layer = build_scalar_field_surface_layer(_tiny_field())
    backend.apply_surface(replace(layer, atom_colors={0: "#d32f2f"}))

    assert _wait_until(
        qapp,
        lambda: _run_js(qapp, backend, "window.__usedColorfunc") is not None,
    )
    assert _run_js(qapp, backend, "window.__usedColorfunc") is False


def test_loading_a_new_molecule_drops_the_field(qapp):
    """A grid is pinned to the coordinates it was computed on. Carrying it
    across a molecule change would drape one molecule's potential over
    another's shape -- which renders perfectly happily and is nonsense."""
    backend = _ready_backend(qapp)
    backend.apply_surface(build_scalar_field_surface_layer(_tiny_field()))
    assert _wait_until(qapp, lambda: "gridpositions" in str(_current_surface(qapp, backend)))

    backend.load_conformer(_ethanol_molblock())

    assert _wait_until(
        qapp, lambda: "gridpositions" not in str(_current_surface(qapp, backend))
    )
    assert '"representation"' in str(_current_surface(qapp, backend)), (
        "the surface itself should survive -- only its stale field goes"
    )


def test_apply_surface_none_clears(qapp):
    backend = _ready_backend(qapp)
    backend.apply_surface(SurfaceLayer(name="vdW", representation="vdw"))
    assert _wait_until(qapp, lambda: _current_surface(qapp, backend) not in (None, "null"))

    backend.apply_surface(None)

    assert _wait_until(qapp, lambda: _current_surface(qapp, backend) in (None, "null"))


def test_surface_applied_before_the_page_loads_is_replayed(qapp):
    """The same deferral race that has now been introduced and fixed three
    times in this codebase (the Calculator Inspector's 3D pane, the Mol*
    structure replay, the Mol* None-sentinel). Shipped WITH the feature
    this time rather than after it."""
    backend = Mol3DViewerBackend()
    assert not backend._page_ready

    backend.load_conformer(_ethanol_molblock())
    backend.apply_surface(SurfaceLayer(name="vdW", representation="ms", opacity=0.6))

    assert _wait_until(qapp, lambda: backend._page_ready)
    assert _wait_until(qapp, lambda: _current_surface(qapp, backend) not in (None, "null"))
    raw = _current_surface(qapp, backend)
    assert '"representation":"ms"' in raw


def test_a_queued_surface_clear_is_not_swallowed(qapp):
    """None is a real queued VALUE here (meaning 'clear'), which is why the
    empty marker is a sentinel object rather than None -- using None for
    both is exactly what silently dropped queued clears in the Mol*
    backend."""
    backend = Mol3DViewerBackend()
    backend.apply_surface(SurfaceLayer(name="vdW", representation="vdw"))
    backend.apply_surface(None)

    assert backend._pending_surface is None  # queued clear, still distinguishable
    assert _wait_until(qapp, lambda: backend._page_ready)
    assert _wait_until(qapp, lambda: backend._pending_surface is not None)  # consumed


def test_apply_visualizations_routes_a_surface_layer_to_the_surface(qapp):
    backend = _ready_backend(qapp)

    backend.apply_visualizations([
        VisualizationLayer(name="LogP", atom_colors={0: "#ff0000"}),
        SurfaceLayer(name="LogP surface", representation="sas", atom_colors={0: "#ff0000"}),
    ])

    assert _wait_until(qapp, lambda: _current_surface(qapp, backend) not in (None, "null"))
    assert '"representation":"sas"' in _current_surface(qapp, backend)
    # The atom layer still applied too -- a surface doesn't replace it.
    assert _wait_until(qapp, lambda: _current_visualization(qapp, backend) not in (None, "null"))


def test_a_layer_list_without_a_surface_clears_any_existing_one(qapp):
    backend = _ready_backend(qapp)
    backend.apply_surface(SurfaceLayer(name="vdW", representation="vdw"))
    assert _wait_until(qapp, lambda: _current_surface(qapp, backend) not in (None, "null"))

    backend.apply_visualizations([VisualizationLayer(name="LogP", atom_colors={0: "#ff0000"})])

    assert _wait_until(qapp, lambda: _current_surface(qapp, backend) in (None, "null"))


def test_loading_a_new_molecule_drops_stale_surface_colors_but_keeps_the_shape(qapp):
    """A new molecule's atom indices have nothing to do with the previous
    molecule's property values -- same staleness rule loadMolblock already
    applies to currentVisualization."""
    backend = _ready_backend(qapp)
    backend.apply_surface(
        SurfaceLayer(name="Charge", representation="ms", atom_colors={0: "#d32f2f"})
    )
    assert _wait_until(qapp, lambda: _current_surface(qapp, backend) not in (None, "null"))

    backend.load_conformer(_ethanol_molblock())

    assert _wait_until(qapp, lambda: '"atomColors":null' in str(_current_surface(qapp, backend)))
    assert '"representation":"ms"' in _current_surface(qapp, backend)


# --- Ensemble overlay (3D alignment panel) --------------------------------


def _methanol_molblock() -> str:
    mol = Chem.AddHs(Chem.MolFromSmiles("CO"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    return Chem.MolToMolBlock(mol)


def _model_count(qapp, backend: Mol3DViewerBackend) -> int:
    """This vendored 3Dmol build has no `getNumModels()` -- confirmed live,
    it is `undefined`. `viewer.models` is the real array, and reading the
    wrong one is how a working feature looks broken."""
    return _run_js(qapp, backend, "viewer.models.length")


def test_load_ensemble_creates_one_real_model_per_structure(qapp):
    """Read back the VIEWER's own model list, not just that the JS call
    returned. `runJavaScript` succeeding proves nothing about whether
    3Dmol actually built anything -- a lesson this project has now
    learned three separate times."""
    backend = Mol3DViewerBackend()
    assert _wait_until(qapp, lambda: backend._page_ready)

    backend.load_ensemble([(_ethanol_molblock(), "#0072b2"), (_methanol_molblock(), "#d55e00")])

    assert _wait_until(qapp, lambda: _model_count(qapp, backend) == 2)
    # And each model really holds its own structure -- ethanol's 9 atoms
    # and methanol's 6, not one merged blob or two copies of the first.
    counts = _run_js(
        qapp, backend, "JSON.stringify(viewer.models.map(function (m) "
        "{ return m.selectedAtoms({}).length; }))"
    )
    assert counts == "[9,6]"


def test_ensemble_colours_survive_a_style_change(qapp):
    """The reason per-model colour is held as state: a global
    setStyle({}) on the next style change would flatten every structure
    to one colour, which is exactly what an overlay must not do."""
    backend = Mol3DViewerBackend()
    assert _wait_until(qapp, lambda: backend._page_ready)
    backend.load_ensemble([(_ethanol_molblock(), "#0072b2"), (_methanol_molblock(), "#d55e00")])
    assert _wait_until(qapp, lambda: _model_count(qapp, backend) == 2)

    backend.set_style("sphere")

    assert _wait_until(
        qapp,
        lambda: _run_js(qapp, backend, "JSON.stringify(currentEnsemble)")
        == '["#0072b2","#d55e00"]',
    )
    # The colour is really on the atoms' style, not just remembered in a
    # variable.
    style = _run_js(
        qapp, backend, "JSON.stringify(viewer.models[1].selectedAtoms({})[0].style)"
    )
    assert "#d55e00" in style


def test_loading_a_single_molecule_leaves_ensemble_mode(qapp):
    backend = Mol3DViewerBackend()
    assert _wait_until(qapp, lambda: backend._page_ready)
    backend.load_ensemble([(_ethanol_molblock(), "#0072b2"), (_methanol_molblock(), "#d55e00")])
    assert _wait_until(qapp, lambda: _model_count(qapp, backend) == 2)

    backend.load_conformer(_ethanol_molblock())

    assert _wait_until(qapp, lambda: _model_count(qapp, backend) == 1)
    assert _run_js(qapp, backend, "JSON.stringify(currentEnsemble)") == "null"


def test_an_ensemble_requested_before_the_page_is_ready_still_lands(qapp):
    """The deferral race that has now bitten this backend three times
    (Calculator Inspector, Mol* replay, the surface None sentinel), so it
    ships WITH the feature rather than as a later fix."""
    backend = Mol3DViewerBackend()
    assert not backend._page_ready

    backend.load_ensemble([(_ethanol_molblock(), "#0072b2"), (_methanol_molblock(), "#d55e00")])

    assert _wait_until(qapp, lambda: backend._page_ready)
    assert _wait_until(qapp, lambda: _model_count(qapp, backend) == 2)


def test_queueing_an_ensemble_replaces_a_queued_single_molecule(qapp):
    """The two modes are mutually exclusive, so whichever call came last
    is what the user asked for -- replaying both would load a molecule
    and then immediately discard it."""
    backend = Mol3DViewerBackend()
    assert not backend._page_ready

    backend.load_conformer(_ethanol_molblock())
    backend.load_ensemble([(_methanol_molblock(), "#d55e00")])

    assert backend._pending_molblock is None
    assert _wait_until(qapp, lambda: backend._page_ready)
    assert _wait_until(qapp, lambda: _model_count(qapp, backend) == 1)
    assert _run_js(qapp, backend, "JSON.stringify(currentEnsemble)") == '["#d55e00"]'


def test_clearing_before_the_page_loads_never_calls_into_the_page(qapp):
    """`MoleculeViewer3DWidget._refresh_view` calls `clear()` during its
    own construction, when the starter molecule has no conformers -- long
    before `loadFinished`. Unguarded that threw

        Uncaught TypeError: Cannot read properties of undefined
        (reading 'clear')

    on EVERY cold launch, measured on 9 of 9 while instrumenting the
    viewer, and invisible in normal use because the page's console logs
    at DEBUG. Nothing needs replaying -- the page starts empty, so a
    clear that arrives before it loads has already happened."""
    backend = Mol3DViewerBackend()
    assert not backend._page_ready  # exactly the widget's situation

    calls: list[str] = []
    original = backend._page.runJavaScript
    backend._page.runJavaScript = lambda script, *a, **k: calls.append(script)  # type: ignore[method-assign]
    backend.clear()
    backend._page.runJavaScript = original  # type: ignore[method-assign]

    assert calls == []


def test_a_clear_before_the_page_loads_cancels_the_queued_structure(qapp):
    """The hazard the early return creates and must not leave open: a
    clear issued between a load and `loadFinished` would otherwise be
    overtaken on replay by the very structure it was meant to remove."""
    backend = Mol3DViewerBackend()
    backend.load_conformer(_ethanol_molblock())
    assert backend._pending_molblock is not None

    backend.clear()
    assert backend._pending_molblock is None

    assert _wait_until(qapp, lambda: backend._page_ready)
    assert _run_js(qapp, backend, "viewer.getModel() ? 1 : 0") in (0, None)


def test_a_style_chosen_before_the_page_loads_is_not_lost(qapp):
    """`set_style` was the second unguarded entry point, and the damaging
    one: `clear` merely threw, but a dropped style leaves the viewer
    rendering in the default representation while the combo box shows the
    one the user picked.

    No caller reaches it before `loadFinished` today -- both run
    `addItems` before connecting, so the default selection emits
    nothing -- but the combo box is on screen and clickable while the page
    is still loading, and that ordering is not something a future edit
    would know to preserve."""
    backend = Mol3DViewerBackend()
    assert not backend._page_ready

    backend.set_style("sphere")
    assert backend._pending_style == "sphere"

    assert _wait_until(qapp, lambda: backend._page_ready)
    assert _wait_until(qapp, lambda: _run_js(qapp, backend, "currentStyle") == "sphere")


def test_every_draw_path_waits_for_a_sized_container(qapp):
    """Qt lays a freshly-shown tab out asynchronously, so a draw issued
    right after the switch runs against a 0x0 container and 3Dmol reads
    its canvas size from the container at draw time. `loadCrystal`
    learned this over five cold launches; `loadMolblock` and
    `loadEnsemble` shipped without it for far longer.

    A source check rather than a render check, because the failure is a
    scheduling race that a test cannot reliably provoke -- and because
    what must not regress is a FOURTH load path being added without the
    wait."""
    page = (
        Path(__file__).resolve().parent.parent
        / "src/openchem/resources/viewer3d/viewer.html"
    ).read_text(encoding="utf-8")

    for name in ("loadMolblock", "loadEnsemble", "loadCrystal"):
        start = page.index(f"{name}: function")
        body = page[start : page.index("\n        },", start)]
        assert "drawWhenSized(" in body, f"{name} draws without waiting for a size"

    # rAF is suspended for content the browser considers not visible, so
    # the callback can simply never fire and nothing is ever drawn.
    helper = page[page.index("function drawWhenSized") :][:600]
    assert "setTimeout" in helper
    assert "requestAnimationFrame" not in helper


# --- keeping the camera between conformers -----------------------------------


def _loads_fired(backend) -> list[str]:
    """Capture the `loadMolblock` calls this backend emits.

    Asserted on the JS itself because the decision under test is a boolean
    the page receives -- there is no Python state that records it, and a
    test on `_structure_key` would only be re-reading the input.
    """
    fired: list[str] = []
    original = backend._page.runJavaScript
    backend._page.runJavaScript = lambda js, *a, **k: (fired.append(js), original(js, *a, **k))[1]
    return fired


def test_the_camera_is_kept_when_the_structure_key_repeats(qapp):
    """Two conformers of one molecule share a key, so the second load must
    tell the page to keep the camera -- which is the whole mechanism behind
    "stepping between conformers no longer jumps"."""
    backend = _ready_backend(qapp)
    fired = _loads_fired(backend)

    backend.load_conformer(_ethanol_molblock(), structure_key=("mol", (1.0,)))
    backend.load_conformer(_ethanol_molblock(), structure_key=("mol", (1.0,)))

    loads = [js for js in fired if "loadMolblock" in js]
    assert len(loads) == 2
    assert loads[0].rstrip().endswith("false);"), loads[0][-40:]
    assert loads[1].rstrip().endswith("true);"), loads[1][-40:]


def test_the_camera_is_refitted_when_the_structure_key_changes(qapp):
    """A different molecule must NOT inherit the previous camera -- there
    is no guarantee it is even in frame at that angle."""
    backend = _ready_backend(qapp)
    fired = _loads_fired(backend)

    backend.load_conformer(_ethanol_molblock(), structure_key=("mol-a", (1.0,)))
    backend.load_conformer(_ethanol_molblock(), structure_key=("mol-b", (1.0,)))

    loads = [js for js in fired if "loadMolblock" in js]
    assert loads[1].rstrip().endswith("false);"), loads[1][-40:]


def test_a_caller_with_no_structure_key_always_refits(qapp):
    """`None` means "I have not thought about this", and re-fitting is the
    answer that cannot strand a structure off screen. Two identical calls,
    because `None == None` would keep the camera if the guard were written
    as a plain equality."""
    backend = _ready_backend(qapp)
    fired = _loads_fired(backend)

    backend.load_conformer(_ethanol_molblock())
    backend.load_conformer(_ethanol_molblock())

    loads = [js for js in fired if "loadMolblock" in js]
    assert all(js.rstrip().endswith("false);") for js in loads), loads


# --- the conformer gallery, against the real 3Dmol grid ----------------------

#: **THE GALLERY NEEDS A SECOND WebGL CONTEXT, and the test suite runs
#: without one.** `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen`,
#: where the page's FIRST context works and a second comes back null, so
#: `$3Dmol.createViewerGrid` throws "Cannot read properties of null
#: (reading 'clearDepth')". Measured, and not fixable from here:
#:
#:     offscreen                                       throws
#:     offscreen + --use-angle=swiftshader             throws
#:     offscreen, first context explicitly released    throws
#:     ordinary windowed platform                      4 cells, 2 canvases
#:
#: So these run only where a display is available -- deliberately kept
#: rather than deleted, because they are the only thing that exercises the
#: real grid, and `QT_QPA_PLATFORM` is set with `setdefault`, so
#: `QT_QPA_PLATFORM=windows pytest ...` runs them.
#:
#: What DOES run everywhere is `test_a_gallery_that_cannot_be_built_is_reported`
#: below, which is the path this environment takes.
_OFFSCREEN = os.environ.get("QT_QPA_PLATFORM") == "offscreen"
_needs_a_display = pytest.mark.skipif(
    _OFFSCREEN, reason="a gallery needs a second WebGL context; offscreen grants one"
)


def _grid_backend(qapp, cells: int = 4, rows: int = 2, cols: int = 2, linked: bool = False):
    """A real grid, sized and shown.

    Shown because `drawWhenSized` and the overlay layout both need a real
    viewport, and settled for a moment after `loadFinished` -- the page is
    parsed by then but the container has not been laid out, and a grid
    built into a zero-sized box produces no cells.
    """
    backend = Mol3DViewerBackend()
    backend.widget().resize(800, 600)
    backend.widget().show()
    assert _wait_until(qapp, lambda: backend._page_ready)
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)
    entries = [(_ethanol_molblock(), f"{i + 1}") for i in range(cells)]
    backend.load_conformer_grid(entries, rows, cols, linked=linked)
    assert _wait_until(
        qapp,
        lambda: _run_js(qapp, backend, "document.querySelectorAll('.cell-overlay').length") == cells,
        timeout_seconds=20,
    ), "the gallery never drew its cells"
    return backend


def _grid_views(qapp, backend) -> list[list[float]]:
    import json

    raw = _run_js(qapp, backend, "window.openchemViewer.gridViews()", timeout_seconds=10)
    return json.loads(raw) if raw else []


@_needs_a_display
def test_the_gallery_builds_a_cell_per_conformer_sharing_one_canvas(qapp):
    """Against the real bundle, because `createViewerGrid` is the whole
    mechanism and a Python-side test would only re-read its own input.

    **The canvas count is the load-bearing half.** One context for the
    whole grid is what makes this affordable; a QWebEngineView per
    conformer would be a Chromium helper set per conformer, and CLAUDE.md
    records those accumulating into a 40-minute hang.
    """
    backend = _grid_backend(qapp, cells=4, rows=2, cols=2)

    assert len(_grid_views(qapp, backend)) == 4
    canvases = _run_js(qapp, backend, "document.querySelectorAll('canvas').length")
    assert canvases <= 2, f"{canvases} canvases; the grid should share one"


@_needs_a_display
def test_unlocked_cells_turn_independently(qapp):
    """The ask, in one sentence: "independently rotatable"."""
    backend = _grid_backend(qapp, cells=4, rows=2, cols=2, linked=False)
    before = _grid_views(qapp, backend)

    _run_js(qapp, backend, "window.openchemViewer.rotateGridCell(0, 60, 'y'); 1")
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)
    after = _grid_views(qapp, backend)

    assert after[0] != before[0], "the cell that was turned did not move"
    assert after[1:] == before[1:], "turning one cell moved the others"


@_needs_a_display
def test_locked_cells_move_by_the_SAME_transform(qapp):
    """**Not merely that they all moved.** "Everything changed" passes
    against a scramble; what makes conformers comparable is that the cells
    end up pointing the SAME way, which is an equality rather than an
    inequality.
    """
    backend = _grid_backend(qapp, cells=4, rows=2, cols=2, linked=True)

    _run_js(qapp, backend, "window.openchemViewer.rotateGridCell(0, 60, 'y'); 1")
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)
    views = _grid_views(qapp, backend)

    # The quaternion is what orientation means; the pan and zoom depend on
    # each cell's own viewport and are not expected to match.
    orientations = {tuple(view[4:]) for view in views}
    assert len(orientations) == 1, f"locked cells point {len(orientations)} different ways"
    assert orientations != {(0.0, 0.0, 0.0, 1.0)}, "nothing actually turned"


@_needs_a_display
def test_match_all_points_every_cell_where_the_selected_one_points(qapp):
    """Different from locking: a one-off, after which the cells are free
    to turn separately again. Starts from cells that genuinely disagree,
    or the assertion would hold before the button was pressed."""
    backend = _grid_backend(qapp, cells=4, rows=2, cols=2, linked=False)
    _run_js(qapp, backend, "window.openchemViewer.rotateGridCell(0, 55, 'x'); 1")
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)
    before = _grid_views(qapp, backend)
    assert len({tuple(v[4:]) for v in before}) > 1, "the cells already agreed"

    backend.match_grid_views(0)
    _wait_until(qapp, lambda: False, timeout_seconds=1.5)

    orientations = {tuple(view[4:]) for view in _grid_views(qapp, backend)}
    assert len(orientations) == 1, "match-all left the cells pointing different ways"


@_needs_a_display
def test_leaving_the_gallery_puts_the_single_viewer_back(qapp):
    """The grid has its own container; without this the single viewer
    stays hidden behind it and the tab looks empty."""
    backend = _grid_backend(qapp, cells=4, rows=2, cols=2)
    assert _run_js(qapp, backend, "getComputedStyle(document.getElementById"
                                  "('grid-container')).display") == "block"

    backend.leave_grid()
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)

    assert _run_js(qapp, backend, "getComputedStyle(document.getElementById"
                                  "('grid-container')).display") == "none"
    assert _run_js(qapp, backend, "getComputedStyle(document.getElementById"
                                  "('viewer-container')).display") == "block"


@pytest.mark.skipif(not _OFFSCREEN, reason="only offscreen refuses the second context")
def test_a_gallery_that_cannot_be_built_is_reported(qapp):
    """THE PATH THIS ENVIRONMENT TAKES, and a real user might too.

    An unbuildable gallery used to leave the pane empty with a JS
    exception in a debug log -- indistinguishable from the feature being
    broken. It reports instead, so the widget can go back to the single
    view and say why.

    Asserted here rather than only in the widget tests because the failure
    originates in the page, and a Python-side fake would be asserting that
    a signal this file emits reaches a slot this file connects.
    """
    backend = Mol3DViewerBackend()
    backend.widget().resize(800, 600)
    backend.widget().show()
    assert _wait_until(qapp, lambda: backend._page_ready)
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)

    failures: list[str] = []
    backend.grid_failed.connect(failures.append)
    backend.load_conformer_grid([(_ethanol_molblock(), "1")], 1, 1)

    assert _wait_until(qapp, lambda: bool(failures), timeout_seconds=20), (
        "the gallery failed silently"
    )
    assert "clearDepth" in failures[0] or "null" in failures[0], failures[0]
    # And the single viewer is back, rather than a hidden container.
    assert _run_js(qapp, backend, "getComputedStyle(document.getElementById"
                                  "('viewer-container')).display") == "block"
