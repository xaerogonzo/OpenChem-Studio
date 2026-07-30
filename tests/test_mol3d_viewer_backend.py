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
