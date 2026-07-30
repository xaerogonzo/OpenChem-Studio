from __future__ import annotations

from PySide6.QtWidgets import QLabel

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState, Provenance
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import PerAtomDataset
from openchem.ui.dialogs.calculator_inspector_dialog import CalculatorInspectorDialog


def _dataset(values: dict[int, float], units: str = "", cache_state: CacheState = CacheState.COMPLETED, error=None) -> PerAtomDataset:
    return PerAtomDataset(
        property_id="test_calc",
        name="Test Calculator",
        units=units,
        method="rdkit",
        molecule_uuid="mol-1",
        values=values,
        provenance=Provenance(created_by="core", method="rdkit"),
        cache_state=cache_state,
        error=error,
    )


def test_overall_value_is_the_sum_of_per_atom_contributions(qapp):
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    result = _dataset({0: -0.2, 1: 0.3, 2: 0.15})

    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)

    labels = dialog.findChildren(QLabel)
    summary_text = next(label.text() for label in labels if label.text().startswith("Overall:"))
    assert summary_text == "Overall: 0.25"


def test_failed_result_shows_the_error_message_instead_of_a_total(qapp):
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Untitled")
    result = _dataset({}, cache_state=CacheState.FAILED, error="pkasolver not installed")

    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)

    labels = dialog.findChildren(QLabel)
    assert any(label.text() == "pkasolver not installed" for label in labels)


def test_dialog_with_no_molblock_does_not_crash(qapp):
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Untitled")  # no molblock drawn yet
    result = _dataset({0: 0.1})

    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)

    assert dialog.windowTitle() == "Calculator Inspector — Untitled"


def test_dialog_with_no_conformer_and_no_color_scale_shows_the_no_conformer_hint(qapp):
    # An empty-values dataset never produces a color_scale (see
    # build_atom_color_layer), so the legend falls to the "no conformer"
    # branch instead -- the two legend texts are mutually exclusive,
    # matching _CalculatorResultView's elif structure.
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    result = _dataset({})

    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)

    labels = dialog.findChildren(QLabel)
    assert any("No conformer generated yet" in label.text() for label in labels)
