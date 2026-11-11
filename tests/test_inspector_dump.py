"""Read-only Inspector dump: drawing vs depiction vs viewer structure, layout, expects."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.app.inspector_dump import (
    SCHEMA_VERSION,
    dispose_driver_inspector,
    encode_inspect_dump,
    evaluate_inspect_expect,
    inspect_dump,
)
from openchem.chem.engine import ChemistryEngine
from openchem.chem.result_structure import EFFECTIVE_STRUCTURE, structure_fingerprint
from openchem.domain.common import CacheState, Provenance, declare_total
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import PerAtomDataset
from openchem.ui.dialogs.calculator_inspector_dialog import CalculatorInspectorDialog


def _dataset(
    values: dict[int, float],
    *,
    structure_molblock: str = "",
    parameters: dict | None = None,
    cache_state: CacheState = CacheState.COMPLETED,
    error=None,
    name: str = "Test Calculator",
    property_id: str = "test_calc",
) -> PerAtomDataset:
    fingerprint = structure_fingerprint(structure_molblock) if structure_molblock else ""
    return PerAtomDataset(
        property_id=property_id,
        name=name,
        units="",
        method="rdkit",
        molecule_uuid="mol-1",
        values=values,
        structure_molblock=structure_molblock,
        structure_fingerprint=fingerprint,
        provenance=Provenance(created_by="core", method="rdkit", parameters=parameters or {}),
        cache_state=cache_state,
        error=error,
    )


def _show(dialog, qapp) -> None:
    dialog.show()
    qapp.processEvents()


def test_dump_has_required_keys_and_layout_matches_widgets(qapp):
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    result = _dataset({0: -0.2, 1: 0.3, 2: 0.15})
    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)
    dialog._requested_calculator_id = "crippen_logp_contrib"
    _show(dialog, qapp)

    dump = inspect_dump(dialog, molecule, tag="ethanol-basic")
    assert dump["schema_version"] == SCHEMA_VERSION
    assert dump["tag"] == "ethanol-basic"
    for key in (
        "drawing", "depiction", "shown_3d", "comparison", "text", "layout", "table",
        "calculator", "structure_source",
    ):
        assert key in dump
    view = dialog._view
    sizes = view._views_splitter.sizes()
    total = sum(sizes)
    assert dump["layout"]["views_splitter_sizes"] == sizes
    assert dump["layout"]["2d_share"] == sizes[0] / total
    assert dump["layout"]["pane_2d_min_width_px"] == view._svg_widget.minimumWidth()
    assert dump["layout"]["pane_3d_min_width_px"] == view._viewer3d.widget().minimumWidth()
    assert dump["layout"]["pane_2d_width_px"] == view._svg_widget.width()
    assert dump["table"]["model_rows"] == dialog._view._table_model.rowCount()
    assert dump["table"]["visible_rows"] == dialog._view._table_proxy.rowCount()
    assert dump["calculator"]["id"] == "crippen_logp_contrib"
    assert dump["calculator"]["result_property_id"] == "test_calc"
    encode_inspect_dump(dump)


def test_drawing_versus_effective_structure(qapp):
    engine = ChemistryEngine()
    drawing = MoleculeModel(display_name="Dimethylamine")
    engine.set_structure_from_smiles(drawing, "CNC")
    ion = MoleculeModel(display_name="ion")
    engine.set_structure_from_smiles(ion, "C[NH2+]C")
    n_atoms = engine.mol_from_molblock(ion.molblock).GetNumAtoms()
    result = _dataset(
        {i: 0.0 for i in range(n_atoms)},
        structure_molblock=ion.molblock,
        parameters={"pH": 7.4, "include_hydrogens": False, "hydrogen_aggregation": "separate"},
    )
    dialog = CalculatorInspectorDialog(engine, drawing, result, conformer_molblock=None)
    _show(dialog, qapp)
    dump = inspect_dump(dialog, drawing)

    assert dump["drawing"]["net_formal_charge"] == 0
    assert dump["depiction"]["net_formal_charge"] == 1
    assert dump["shown_3d"]["net_formal_charge"] == 1
    assert dump["structure_source"] == EFFECTIVE_STRUCTURE
    assert dump["comparison"]["depiction_same_formal_charge_as_drawing"] is False
    assert dump["comparison"]["depiction_same_heavy_atom_count_as_drawing"] is True
    assert dump["drawing"]["heavy_atom_count"] == dump["depiction"]["heavy_atom_count"]
    assert dump["provenance"]["parameters"]["pH"] == 7.4
    assert dump["drawing_charge"] == 0
    assert dump["depiction_charge"] == 1
    assert dump["formal_charge"] == 1


def test_missing_and_unparsable_structures_do_not_raise(qapp):
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Untitled")
    result = _dataset({0: 0.1})
    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)
    dump = inspect_dump(dialog, molecule)
    assert dump["drawing"]["present"] is False
    assert dump["drawing"]["atom_count"] is None
    assert dump["drawing"]["net_formal_charge"] is None

    molecule.molblock = "not a molfile"
    dump = inspect_dump(dialog, molecule)
    assert dump["drawing"]["present"] is True
    assert dump["drawing"]["parse_ok"] is False
    assert dump["drawing"]["atom_count"] is None
    encode_inspect_dump(dump)


def test_flat_viewer_structure_is_not_reported_as_3d(qapp):
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    result = _dataset({0: 0.1, 1: 0.2, 2: 0.3})
    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=molecule.molblock)
    dump = inspect_dump(dialog, molecule)
    assert dump["shown_3d"]["present"] is True
    assert dump["shown_3d"]["parse_ok"] is True
    assert dump["shown_3d"]["has_3d_coordinates"] is False


def test_embedded_conformer_is_reported_as_3d(qapp):
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    mol = Chem.AddHs(engine.mol_from_model(molecule))
    assert AllChem.EmbedMolecule(mol, randomSeed=7) == 0
    molblock = Chem.MolToMolBlock(mol)
    result = _dataset({i: 0.0 for i in range(mol.GetNumAtoms())})
    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=molblock)
    dump = inspect_dump(dialog, molecule)
    assert dump["shown_3d"]["has_3d_coordinates"] is True
    assert dump["shown_3d"]["z_span_angstrom"] > 0.01


def test_headline_labels_and_filtered_table(qapp):
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Dimethylamine")
    engine.set_structure_from_smiles(molecule, "CNC")
    total = declare_total(1.0, "LogP (Crippen)")
    total["balance"] = {"visible_basis": "heavy-atom contributions", "explanation": "implicit hydrogens"}
    result = _dataset({0: 0.5, 1: 0.25}, parameters={"total": total}, name="LogP Contribution (Crippen)")
    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)
    view = dialog._view
    view._table_filter.setText("N")
    view._table.selectRow(0)
    dump = inspect_dump(dialog, molecule)
    assert dump["text"]["name"] == "LogP Contribution (Crippen)"
    assert "LogP (Crippen)" in dump["text"]["summary"]
    assert "implicit hydrogens" in dump["text"]["balance"]
    assert dump["table"]["filter"] == "N"
    assert dump["table"]["model_rows"] == 2
    assert dump["table"]["visible_rows"] < dump["table"]["model_rows"]
    assert dump["table"]["selected_atom"] is not None
    assert dump["table"]["labels_2d"] >= 1


def test_existing_expect_keys_and_unknown_key_fails():
    dump = {
        "structure_source": "none",
        "formal_charge": 0,
        "depiction_charge": 1,
        "drawing_charge": 0,
        "layout": {
            "pane_2d_min_width_px": 320,
            "pane_2d_width_px": 520,
            "pane_3d_min_width_px": 320,
            "pane_3d_width_px": 520,
            "2d_share": 0.5,
        },
    }
    assert evaluate_inspect_expect(dump, None) is None
    assert evaluate_inspect_expect(dump, {}) is None
    assert evaluate_inspect_expect(dump, {"structure": "none", "formal_charge": 0, "depiction_charge": 1}) == []
    assert evaluate_inspect_expect(dump, {"drawing_charge": 0}) == []
    problems = evaluate_inspect_expect(dump, {"formal_charge": 9})
    assert problems and "formal_charge" in problems[0]
    unknown = evaluate_inspect_expect(dump, {"chemically_correct": True})
    assert unknown and "unknown expect keys" in unknown[0]
    layout_ok = evaluate_inspect_expect(dump, {"pane_2d_min_width_px": 320})
    assert layout_ok == []


def test_helper_does_not_compute(qapp, monkeypatch):
    calls = {"n": 0}

    def boom(*_a, **_k):
        calls["n"] += 1
        raise AssertionError("compute must not run")

    monkeypatch.setattr("openchem.services.calculator_registry.CalculatorRegistry.compute", boom)
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    dialog = CalculatorInspectorDialog(engine, molecule, _dataset({0: 0.1, 1: 0.2, 2: 0.3}), None)
    inspect_dump(dialog, molecule)
    assert calls["n"] == 0


def test_dispose_does_not_leave_driver_inspectors(qapp):
    from PySide6.QtCore import Qt

    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    first = CalculatorInspectorDialog(engine, molecule, _dataset({0: 0.1}), None)
    first.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    first.show()
    qapp.processEvents()
    dispose_driver_inspector(first)
    first = None
    qapp.processEvents()
    second = CalculatorInspectorDialog(engine, molecule, _dataset({0: 0.2}), None)
    second.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    second.show()
    qapp.processEvents()
    alive = [
        widget
        for widget in QApplication.topLevelWidgets()
        if isinstance(widget, CalculatorInspectorDialog) and widget.isVisible()
    ]
    assert alive == [second]
    dispose_driver_inspector(second)
    second = None
    qapp.processEvents()
    leftover = [
        widget
        for widget in QApplication.topLevelWidgets()
        if isinstance(widget, CalculatorInspectorDialog) and widget.isVisible()
    ]
    assert leftover == []
