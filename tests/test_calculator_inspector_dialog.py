from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QWidget
from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState, Provenance
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    StructureEntry,
    StructureSetResult,
)
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


def test_spectrum_result_gets_no_overall_summary_line(qapp):
    """Phase 23: summing chemical shifts is chemically meaningless, so a
    spectrum must show NO summary line -- not a bogus total, and not the
    bare "Overall: n/a" that used to appear and read like a failure."""
    from openchem.domain.scientific_result import NMRSpectrumResult

    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    result = NMRSpectrumResult(
        spectrum_type="nmr_empirical",
        name="NMR Shift",
        units="ppm",
        method="smarts_lookup",
        molecule_uuid="mol-1",
        values={0: 25.0, 1: 70.0},
    )

    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert not any(t.startswith("Overall") for t in texts)


def test_per_atom_dataset_still_gets_its_overall_total(qapp):
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")

    dialog = CalculatorInspectorDialog(engine, molecule, _dataset({0: 0.5, 1: 0.25}), conformer_molblock=None)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert any(t.startswith("Overall: 0.75") for t in texts)


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


def test_a_ph_curve_result_opens_the_chart_not_the_molecular_view(qapp):
    """A PhCurveResult has no per-atom data, so build_visualization_layer
    returns None for it and the default 2D+3D view would render two empty
    molecule panes plus a misleading "No conformer generated yet" line --
    the same empty-looks-broken bug Phase 23a fixed for spectra. The
    result-type view registry is what prevents that."""
    from openchem.domain.scientific_result import PhCurveResult
    from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend
    from openchem.ui.widgets.ph_curve_widget import PhCurveWidget

    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ibuprofen")
    engine.set_structure_from_smiles(molecule, "CC(C)Cc1ccc(cc1)C(C)C(=O)O")
    result = PhCurveResult(
        curve_id="logd_vs_ph",
        name="LogD vs pH",
        method="henderson_hasselbalch",
        molecule_uuid="mol-1",
        ph_values=[2.0, 7.4, 12.0],
        series={"logD": [3.07, 0.49, -2.11]},
        y_label="logD",
        cache_state=CacheState.COMPLETED,
    )

    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)

    assert dialog.findChildren(PhCurveWidget), "expected the pH-curve chart"
    # No 3D molecular viewer was constructed for a result that has no atoms.
    assert not dialog.findChildren(Mol3DViewerBackend)
    assert not any("No conformer" in label.text() for label in dialog.findChildren(QLabel))


def test_a_per_atom_result_still_gets_the_molecular_view(qapp):
    """Regression guard on the registry fallback: adding chart routing must
    not divert the results that legitimately want 2D+3D."""
    from openchem.ui.widgets.ph_curve_widget import PhCurveWidget

    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")

    dialog = CalculatorInspectorDialog(engine, molecule, _dataset({0: -0.2, 1: 0.3}), conformer_molblock=None)

    assert not dialog.findChildren(PhCurveWidget)
    assert any(label.text().startswith("Overall:") for label in dialog.findChildren(QLabel))


def test_surface_combo_is_disabled_without_a_conformer(qapp):
    """A surface needs 3D coordinates. Offering the control with nothing to
    wrap would look like a broken feature rather than a missing input."""
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")

    dialog = CalculatorInspectorDialog(engine, molecule, _dataset({0: -0.2, 1: 0.3}), conformer_molblock=None)

    view = dialog.findChild(QWidget)
    combo = next(c for c in dialog.findChildren(QComboBox))
    assert not combo.isEnabled()


def test_surface_combo_offers_every_confirmed_representation(qapp):
    from openchem.ui.visualization import SURFACE_REPRESENTATIONS

    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")

    dialog = CalculatorInspectorDialog(engine, molecule, _dataset({0: -0.2}), conformer_molblock=None)

    combo = next(c for c in dialog.findChildren(QComboBox))
    offered = [combo.itemData(i) for i in range(combo.count())]
    assert offered == ["", *SURFACE_REPRESENTATIONS]


def test_selecting_a_surface_applies_one_built_from_the_result(qapp):
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    result = _dataset({0: -0.2, 1: 0.3})
    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock="fake molblock")

    applied = []
    view = dialog.findChildren(QWidget)
    combo = next(c for c in dialog.findChildren(QComboBox))
    # Capture what reaches the backend rather than round-tripping through
    # a real WebEngine page, which this unit test has no reason to spin up.
    target = next(w for w in dialog.findChildren(QWidget) if hasattr(w, "_viewer3d"))
    target._viewer3d.apply_surface = applied.append

    combo.setCurrentIndex(1)  # first real representation

    assert len(applied) == 1
    assert applied[0].representation == "vdw"
    assert applied[0].atom_colors  # coloured by the result's own values


def test_selecting_no_surface_clears_it(qapp):
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    dialog = CalculatorInspectorDialog(
        engine, molecule, _dataset({0: -0.2}), conformer_molblock="fake molblock"
    )
    combo = next(c for c in dialog.findChildren(QComboBox))
    target = next(w for w in dialog.findChildren(QWidget) if hasattr(w, "_viewer3d"))
    applied = []
    target._viewer3d.apply_surface = applied.append

    combo.setCurrentIndex(1)
    combo.setCurrentIndex(0)

    assert applied[-1] is None


def _colouring_combo(dialog):
    return dialog.findChildren(QComboBox)[1]


def test_electrostatic_potential_is_offered_only_for_charges(qapp):
    """The potential is computed FROM partial charges -- there is nothing
    to compute it from on a LogP-contribution dataset, and offering it
    there would produce a picture of a quantity nobody asked for.

    Keyed on the dataset's units rather than on a list of calculator ids,
    so this test also pins down that a future charge model qualifies
    without anyone editing the dialog.
    """
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")

    charges = CalculatorInspectorDialog(
        engine, molecule, _dataset({0: -0.2}, units="e"), conformer_molblock="fake"
    )
    logp = CalculatorInspectorDialog(
        engine, molecule, _dataset({0: -0.2}, units=""), conformer_molblock="fake"
    )

    assert "esp" in [
        _colouring_combo(charges).itemData(i)
        for i in range(_colouring_combo(charges).count())
    ]
    assert "esp" not in [
        _colouring_combo(logp).itemData(i) for i in range(_colouring_combo(logp).count())
    ]
    assert not _colouring_combo(logp).isEnabled()


def test_choosing_the_potential_sends_a_field_instead_of_atom_colours(qapp):
    """The two are alternatives, not a combination: nearest-atom colouring
    steps between atoms, a field varies continuously through the space
    between them."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    dialog = CalculatorInspectorDialog(
        engine,
        molecule,
        _dataset({2: -0.4, 0: 0.2}, units="e"),
        conformer_molblock=Chem.MolToMolBlock(mol),
    )
    target = next(w for w in dialog.findChildren(QWidget) if hasattr(w, "_viewer3d"))
    applied = []
    target._viewer3d.apply_surface = applied.append

    _colouring_combo(dialog).setCurrentIndex(1)  # Electrostatic potential
    dialog.findChildren(QComboBox)[0].setCurrentIndex(1)  # vdW

    layer = applied[-1]
    assert layer.scalar_field_dx and "gridpositions" in layer.scalar_field_dx
    assert layer.atom_colors is None
    low, high = layer.scalar_field_range
    assert low == -high, "an off-centre range puts neutral space somewhere other than white"
    assert layer.color_scale.domain_min == low


def test_the_legend_names_the_quantity_actually_on_screen(qapp):
    """Caught by looking at the running app rather than by a test: with the
    potential selected, the legend still read the CHARGE range in
    electrons. Not merely stale -- a different physical quantity in
    different units, printed with the same authority as a correct one."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)O"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Acetic acid")
    engine.set_structure_from_smiles(molecule, "CC(=O)O")
    dialog = CalculatorInspectorDialog(
        engine,
        molecule,
        _dataset({0: -0.5, 3: 0.3}, units="e"),
        conformer_molblock=Chem.MolToMolBlock(mol),
    )
    target = next(w for w in dialog.findChildren(QWidget) if hasattr(w, "_viewer3d"))
    target._viewer3d.apply_surface = lambda _layer: None
    legend = target._legend_label

    dialog.findChildren(QComboBox)[0].setCurrentIndex(1)  # vdW, per-atom colouring
    per_atom_text = legend.text()
    _colouring_combo(dialog).setCurrentIndex(1)  # Electrostatic potential
    potential_text = legend.text()

    assert per_atom_text.endswith("e")
    assert "kcal/(mol*e)" in potential_text
    assert potential_text != per_atom_text

    _colouring_combo(dialog).setCurrentIndex(0)  # back to per-atom
    assert legend.text() == per_atom_text, "switching back must restore the charge legend"


# --- Report results, copy, and taking a structure out ---------------------


def _aspirin_molecule(engine):
    molecule = MoleculeModel(display_name="aspirin")
    engine.set_structure_from_smiles(molecule, "CC(=O)Oc1ccccc1C(=O)O")
    return molecule


def test_a_report_result_shows_its_lines_instead_of_two_empty_molecule_panes(qapp):
    """The regression this guards: AlertResult fell through to the
    per-atom 2D+3D view, which has nothing to draw for it -- so Elemental
    Analysis computed a formula, a mass and a full composition and
    displayed NONE of it, under a "No conformer generated yet" label that
    made it look like a conformer problem."""
    from PySide6.QtWidgets import QPlainTextEdit

    engine = ChemistryEngine()
    result = AlertResult(
        alert_id="elemental",
        name="Elemental Analysis",
        molecule_uuid="m",
        matched=["Formula: C9H8O4", "Mass: 180.159"],
    )

    dialog = CalculatorInspectorDialog(engine, _aspirin_molecule(engine), result, None)

    shown = dialog.findChildren(QPlainTextEdit)[0].toPlainText()
    assert "Formula: C9H8O4" in shown
    assert "Mass: 180.159" in shown


def test_a_failed_report_result_shows_its_error(qapp):
    from PySide6.QtWidgets import QPlainTextEdit

    engine = ChemistryEngine()
    result = AlertResult(
        alert_id="geometry",
        name="Geometry",
        molecule_uuid="m",
        matched=[],
        cache_state=CacheState.FAILED,
        error="This calculation needs a 3D conformer.",
    )

    dialog = CalculatorInspectorDialog(engine, _aspirin_molecule(engine), result, None)

    assert "needs a 3D conformer" in dialog.findChildren(QPlainTextEdit)[0].toPlainText()


def _button(dialog, text):
    return next(b for b in dialog.findChildren(QPushButton) if b.text() == text)


def test_copy_all_puts_the_result_on_the_clipboard(qapp):
    engine = ChemistryEngine()
    result = AlertResult(
        alert_id="elemental", name="Elemental Analysis", molecule_uuid="m", matched=["Formula: C9H8O4"]
    )
    dialog = CalculatorInspectorDialog(engine, _aspirin_molecule(engine), result, None)

    _button(dialog, "Copy All").click()

    assert QGuiApplication.clipboard().text() == "Elemental Analysis\nFormula: C9H8O4"


def _stereoisomer_result():
    entries = [
        StructureEntry(molblock=Chem.MolToMolBlock(Chem.MolFromSmiles(smiles)), label=f"Isomer {i}")
        for i, smiles in enumerate(["C[C@H](F)Cl", "C[C@@H](F)Cl"], start=1)
    ]
    return StructureSetResult(
        set_id="stereoisomers",
        name="Stereoisomers",
        method="rdkit",
        molecule_uuid="m",
        entries=entries,
    )


def test_structure_actions_stay_disabled_until_one_is_picked(qapp):
    engine = ChemistryEngine()
    dialog = CalculatorInspectorDialog(
        engine, _aspirin_molecule(engine), _stereoisomer_result(), None
    )

    assert not _button(dialog, "Copy SMILES").isEnabled()

    dialog._view._on_cell_clicked(0)

    assert _button(dialog, "Copy SMILES").isEnabled()


def test_copying_the_picked_isomer_keeps_its_stereochemistry(qapp):
    """The workflow this exists for: generate the isomers, pick the one
    you wanted, take it away. Copying the SECOND one specifically, since
    a bug that always copied the first would still look right."""
    engine = ChemistryEngine()
    dialog = CalculatorInspectorDialog(
        engine, _aspirin_molecule(engine), _stereoisomer_result(), None
    )

    dialog._view._on_cell_clicked(1)
    _button(dialog, "Copy SMILES").click()

    assert QGuiApplication.clipboard().text() == "C[C@@H](F)Cl"


def test_copying_a_molblock_gives_the_molblock_not_smiles(qapp):
    """A molblock is what carries 3D coordinates -- the whole difference
    for a conformer set."""
    engine = ChemistryEngine()
    dialog = CalculatorInspectorDialog(
        engine, _aspirin_molecule(engine), _stereoisomer_result(), None
    )

    dialog._view._on_cell_clicked(0)
    _button(dialog, "Copy Molblock").click()

    copied = QGuiApplication.clipboard().text()
    assert "V2000" in copied
    assert Chem.MolFromMolBlock(copied) is not None


def test_add_to_project_hands_over_the_picked_structure(qapp):
    engine = ChemistryEngine()
    added: list[tuple[str, str]] = []
    dialog = CalculatorInspectorDialog(
        engine,
        _aspirin_molecule(engine),
        _stereoisomer_result(),
        None,
        on_add_structure=lambda molblock, label: added.append((molblock, label)),
    )

    dialog._view._on_cell_clicked(1)
    _button(dialog, "Add to Project").click()

    assert len(added) == 1
    molblock, label = added[0]
    assert label == "Isomer 2"
    assert engine.molblock_to_smiles(molblock) == "C[C@@H](F)Cl"


def test_add_to_project_is_hidden_when_no_handler_was_given(qapp):
    """The dialog is constructible without a project (tests, and any
    future caller that has no undo stack) -- it must not offer an action
    it cannot perform."""
    engine = ChemistryEngine()
    dialog = CalculatorInspectorDialog(
        engine, _aspirin_molecule(engine), _stereoisomer_result(), None
    )

    assert not _button(dialog, "Add to Project").isVisible()
