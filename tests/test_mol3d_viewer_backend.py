from __future__ import annotations

import time

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.ui.visualization import VisualizationLayer
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
