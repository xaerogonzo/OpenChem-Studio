"""The Calculator Inspector draws the structure a per-atom result describes, and makes it readable.

What Alex reported on 2026-09-17, with butyryl fentanyl at pH 7.4: the protonated nitrogen was not
drawn, the 2D pane said "not shown" (two phenyls, several matches that disagree), and the 3D labels --
10 px, on all 57 atoms -- could not be read. Each test here was run against the code before the fix
it guards, or broken on purpose, before it was trusted.
"""

from __future__ import annotations

import json
import time

import pytest
from PySide6.QtCore import Qt
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.engine import ChemistryEngine
from openchem.chem.result_structure import EFFECTIVE_STRUCTURE, LEGACY_STORED_CONFORMER
from openchem.domain.common import Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import PerAtomDataset
from openchem.ui.dialogs.calculator_inspector_dialog import CalculatorInspectorDialog
from openchem.ui.visualization import VisualizationLayer
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend

BUTYRYL_FENTANYL = "CCCC(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1"
PH = {"ph_dependent": True, "pH": 7.4}


def _registry():
    from openchem.bootstrap import build_service_container

    return build_service_container().calculator_registry


def _molecule_with_conformer(smiles: str) -> tuple[ChemistryEngine, MoleculeModel, Chem.Mol]:
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name=smiles)
    engine.set_structure_from_smiles(molecule, smiles)
    mol = Chem.AddHs(engine.mol_from_model(molecule))
    assert AllChem.EmbedMolecule(mol, randomSeed=7) == 0
    molblock = Chem.MolToMolBlock(mol)
    molecule.conformers = [ConformerModel(conformer_id="c1", molblock=molblock)]
    return engine, molecule, engine.mol_from_molblock(molblock)


@pytest.fixture
def recorded_viewer(monkeypatch):
    """What the dialog hands the 3D backend, without spinning up a page."""
    seen: dict[str, list] = {"loaded": [], "layers": [], "hover": [], "highlight": []}
    monkeypatch.setattr(Mol3DViewerBackend, "load_conformer", lambda self, molblock, *a, **k: seen["loaded"].append(molblock))
    monkeypatch.setattr(Mol3DViewerBackend, "apply_visualization", lambda self, layer: seen["layers"].append(layer))
    real_hover = Mol3DViewerBackend.set_hover
    monkeypatch.setattr(Mol3DViewerBackend, "set_hover",
                        lambda self, *a, **k: (seen["hover"].append((a, k)), real_hover(self, *a, **k)))
    monkeypatch.setattr(Mol3DViewerBackend, "highlight_atom", lambda self, index: seen["highlight"].append(index))
    return seen


def _inspect(engine, molecule, result, qapp):
    dialog = CalculatorInspectorDialog(engine, molecule, result, molecule.conformers[0].molblock)
    return dialog, dialog._view


def test_the_3d_pane_shows_the_protonated_microspecies_not_the_stored_conformer(qapp, recorded_viewer):
    engine, molecule, mol = _molecule_with_conformer(BUTYRYL_FENTANYL)
    result = _registry().compute("geometry_partial_charge", mol, molecule.uuid, PH)
    _dialog, view = _inspect(engine, molecule, result, qapp)

    assert view._structure_source == EFFECTIVE_STRUCTURE
    (loaded,) = recorded_viewer["loaded"]
    assert loaded == result.structure_molblock != molecule.conformers[0].molblock
    shown = Chem.MolFromMolBlock(loaded, removeHs=False)
    assert shown.GetNumAtoms() == 57 and Chem.GetFormalCharge(shown) == 1


def test_the_2d_pane_labels_every_heavy_atom_and_draws_the_n_h(qapp, recorded_viewer):
    """"2D: not shown" was the refusal for a molecule with two phenyls; drawing the computed
    structure itself leaves nothing to match."""
    engine, molecule, mol = _molecule_with_conformer(BUTYRYL_FENTANYL)
    result = _registry().compute("geometry_partial_charge", mol, molecule.uuid, PH)
    _dialog, view = _inspect(engine, molecule, result, qapp)

    assert not view._placement_label.text()
    depicted = Chem.MolFromMolBlock(view._depiction_molblock, removeHs=False)
    heavy = [a.GetIdx() for a in depicted.GetAtoms() if a.GetAtomicNum() > 1]
    assert len(heavy) == 26 and depicted.GetNumAtoms() == 27  # plus the N-H of the cation
    (nh,) = [a for a in depicted.GetAtoms() if a.GetAtomicNum() == 1]
    assert nh.GetNeighbors()[0].GetSymbol() == "N" and nh.GetNeighbors()[0].GetFormalCharge() == 1
    assert set(view._layer_2d.atom_labels) == set(range(27))
    # Each depicted atom carries its OWN structure atom's value.
    for k, source in {v: s for s, v in view._to_depiction.items()}.items():
        assert view._values_2d[k] == result.values[source]
    # Deterministic, so a driven screenshot is comparable run to run.
    assert engine.depiction_of(result.structure_molblock, molecule.molblock) == engine.depiction_of(
        result.structure_molblock, molecule.molblock)


def test_a_result_without_a_structure_still_uses_its_stored_conformer(qapp, recorded_viewer):
    engine, molecule, mol = _molecule_with_conformer("CCO")
    legacy = PerAtomDataset(
        property_id="x", name="x", units="e", method="m", molecule_uuid=molecule.uuid,
        values={i: 0.1 * i for i in range(mol.GetNumAtoms())},
        provenance=Provenance(created_by="core", method="m",
                              parameters={"input_source": "conformer", "input_conformer_id": "c1"}),
    )
    _dialog, view = _inspect(engine, molecule, legacy, qapp)
    assert view._structure_source == LEGACY_STORED_CONFORMER
    assert recorded_viewer["loaded"] == [molecule.conformers[0].molblock]


def test_3d_labels_go_on_heavy_atoms_and_polar_hydrogens_and_every_value_reaches_hover(qapp, recorded_viewer):
    engine, molecule, mol = _molecule_with_conformer(BUTYRYL_FENTANYL)
    result = _registry().compute("geometry_partial_charge", mol, molecule.uuid, PH)
    _inspect(engine, molecule, result, qapp)

    (layer,) = recorded_viewer["layers"]
    structure = Chem.MolFromMolBlock(result.structure_molblock, removeHs=False)
    labelled = set(layer.atom_labels)
    for atom in structure.GetAtoms():
        on_carbon = atom.GetAtomicNum() == 1 and atom.GetNeighbors()[0].GetSymbol() == "C"
        assert (atom.GetIdx() in labelled) != on_carbon, (atom.GetIdx(), atom.GetSymbol())
    assert len(layer.atom_colors) == 57  # every atom is still coloured
    ((values, elements), keywords) = recorded_viewer["hover"][0]
    assert values == result.values and len(elements) == 57 and keywords["units"] == "e"


def _acid_view(qapp):
    engine, molecule, mol = _molecule_with_conformer("OC(=O)CCN")
    result = _registry().compute("geometry_partial_charge", mol, molecule.uuid, PH)
    assert result.structure_molblock, result.error
    return _inspect(engine, molecule, result, qapp) + (result,)


def test_a_sorted_and_filtered_table_row_selects_ITS_atom_not_the_row_number(qapp, recorded_viewer):
    _dialog, view, result = _acid_view(qapp)
    table = view._table
    structure = Chem.MolFromMolBlock(result.structure_molblock, removeHs=False)

    table.sortByColumn(2, Qt.SortOrder.DescendingOrder)
    view._table_filter.setText("O")
    assert view._table_proxy.rowCount() == 2  # the two carboxylate oxygens

    table.selectRow(0)
    atom = view.selected_atom()
    assert structure.GetAtomWithIdx(atom).GetSymbol() == "O"
    assert recorded_viewer["highlight"][-1] == atom
    # The highest-valued oxygen, which is what "sorted descending, first row" means.
    oxygens = [i for i in result.values if structure.GetAtomWithIdx(i).GetSymbol() == "O"]
    assert atom == max(oxygens, key=lambda i: result.values[i])
    # And the 2D pane emphasises the same atom, through the depiction's own numbering.
    assert view._emphasised == view._to_depiction[atom]

    # A row whose atom cannot be its row number: the only nitrogen, alone after filtering. (The
    # oxygen above happens to be atom 0 in row 0, so on its own it could not tell the two apart --
    # a mutation returning the row number survived it.)
    view._table_filter.setText("N")
    assert view._table_proxy.rowCount() == 1
    table.selectRow(0)
    (nitrogen,) = [a.GetIdx() for a in structure.GetAtoms() if a.GetSymbol() == "N"]
    assert nitrogen != 0 and view.selected_atom() == nitrogen
    assert recorded_viewer["highlight"][-1] == nitrogen


def test_copy_all_includes_the_value_table(qapp, recorded_viewer):
    dialog, view, result = _acid_view(qapp)
    dialog._on_copy_all()
    from PySide6.QtGui import QGuiApplication

    copied = QGuiApplication.clipboard().text()
    assert "#\tElement\tValue (e)" in copied
    assert copied.count("\n") >= len(result.values)


def test_the_inspector_opens_large_and_stays_resizable(qapp, recorded_viewer):
    dialog, _view, _result = _acid_view(qapp)
    assert dialog.width() >= 640 and dialog.height() >= 480
    assert dialog.minimumSize() != dialog.maximumSize()


# --- the page: labels, hover and highlight on a real 3Dmol viewer -------------------------------


PAGE_READY_TIMEOUT_SECONDS = 60


def _wait_until(qapp, predicate, timeout_seconds: float = 15) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _run_js(qapp, backend, script: str):
    result: dict = {}
    backend._page.runJavaScript(script, lambda value: result.__setitem__("value", value))
    _wait_until(qapp, lambda: "value" in result, timeout_seconds=5)
    return result.get("value")


def _state(qapp, backend) -> dict:
    return json.loads(_run_js(qapp, backend, "window.openchemViewer.labelState()") or "{}")


def test_a_hover_label_comes_and_goes_without_taking_value_or_shape_labels(qapp):
    """3Dmol has one label collection. The hover label is removed by its own handle; the lifecycle
    below is the sequence that would expose a `removeAllLabels` or a leaked handle."""
    from openchem.chem.dipole import compute_dipole_moment

    mol = Chem.AddHs(Chem.MolFromSmiles("CO"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    backend = Mol3DViewerBackend()
    assert _wait_until(qapp, lambda: backend._page_ready, PAGE_READY_TIMEOUT_SECONDS)
    backend.load_conformer(Chem.MolToMolBlock(mol))
    backend.set_hover({0: -0.25, 1: -0.5}, {0: "C", 1: "O"}, units="e", places=2)
    backend.apply_visualization(VisualizationLayer(name="x", atom_colors={0: "#ff0000", 1: "#0000ff"},
                                                   atom_labels={0: "-0.25", 1: "-0.50"}))
    assert _wait_until(qapp, lambda: {"-0.25", "-0.50"} <= set(_state(qapp, backend).get("texts", [])))

    assert _run_js(qapp, backend, "window.openchemViewer.simulateHover(1)") == "O2  -0.50 e"
    backend.apply_shapes(compute_dipole_moment(mol, "u").spatial)
    assert _wait_until(qapp, lambda: len(_state(qapp, backend)["texts"]) >= 4), _state(qapp, backend)
    assert _run_js(qapp, backend, "window.openchemViewer.simulateHover(0)") == "C1  -0.25 e"
    state = _state(qapp, backend)
    assert state["texts"].count("O2  -0.50 e") == 0, "the first hover label was left behind"
    assert state["texts"].count("C1  -0.25 e") == 1

    _run_js(qapp, backend, "window.openchemViewer.simulateUnhover(); 1")
    state = _state(qapp, backend)
    assert state["hover"] is None and not any("  " in text for text in state["texts"])
    assert {"-0.25", "-0.50"} <= set(state["texts"]), "a value label went with the hover label"
    assert any(text.endswith("D") for text in state["texts"]), "the dipole caption went with the hover label"
    assert state["hoverLabelsCreated"] == 2


def test_highlight_follows_the_atom_index_and_survives_a_relayer(qapp):
    mol = Chem.AddHs(Chem.MolFromSmiles("CO"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    backend = Mol3DViewerBackend()
    assert _wait_until(qapp, lambda: backend._page_ready, PAGE_READY_TIMEOUT_SECONDS)
    backend.load_conformer(Chem.MolToMolBlock(mol))
    backend.apply_visualization(VisualizationLayer(name="x", atom_colors={0: "#ff0000"}))
    backend.highlight_atom(1)
    assert _wait_until(qapp, lambda: _state(qapp, backend).get("highlight") == 1)
    backend.apply_visualization(VisualizationLayer(name="y", atom_colors={1: "#00ff00"}))
    assert _wait_until(qapp, lambda: _state(qapp, backend).get("highlight") == 1)
    backend.highlight_atom(None)
    assert _wait_until(qapp, lambda: _state(qapp, backend).get("highlight") is None)
