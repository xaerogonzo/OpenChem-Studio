from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QToolBar, QWidget, QWidgetAction
from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from conftest import synthetic_nmr_spectrum
from openchem.chem.nmr_signals import NMRSignal, depiction_atoms
from openchem.domain.molecule import MoleculeModel
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.visualization import VisualizationLayer
from openchem.ui.widgets import nmr_view_widget as nmr_view_module
from openchem.ui.widgets.nmr_view_widget import NmrViewWidget

IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"


class FakeViewerBackend(ViewerBackend):
    """Records calls instead of driving a real QWebEngineView -- the same
    `backend=` seam `MoleculeViewer3DWidget` already exposes for tests."""

    def __init__(self) -> None:
        super().__init__()
        self.applied_layers: list[VisualizationLayer | None] = []
        self.loaded_molblocks: list[str] = []

    def load_conformer(self, molblock: str, structure_key: object = None) -> None:
        self.loaded_molblocks.append(molblock)

    def set_style(self, style: str) -> None:
        pass

    def clear(self) -> None:
        pass

    def apply_visualization(self, layer: VisualizationLayer | None) -> None:
        self.applied_layers.append(layer)

    def widget(self) -> QWidget:
        return QWidget()


def _make_view(qapp, smiles: str = IBUPROFEN):
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Test")
    engine.set_structure_from_smiles(molecule, smiles)
    spectrum = synthetic_nmr_spectrum(
        Chem.AddHs(Chem.MolFromSmiles(smiles)), molecule.uuid
    )
    backend = FakeViewerBackend()
    view = NmrViewWidget(engine, backend=backend)
    view.set_spectrum(molecule.molblock, spectrum)
    return view, backend, molecule, spectrum


def test_table_lists_one_row_per_signal(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    assert view._table.rowCount() == len(view.signals()) == 9


# --- the coupling note: which of four states is on screen -----------------


def test_a_non_singlet_with_no_real_j_gets_the_not_calculated_note(qapp):
    """`synthetic_nmr_spectrum` carries no coupling data at all, and
    ibuprofen's isopropyl methyls are a real structural doublet -- exactly
    the state that used to render as an unexplained unsplit line."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    assert any(s.multiplicity != "s" for s in view.signals())

    assert "not calculated" in view._coupling_note_label.text()
    assert "predicted from connectivity" in view._coupling_note_label.text()


def test_real_coupling_gets_a_positive_confirmation_naming_the_frequency(qapp):
    from openchem.chem.engine import ChemistryEngine as _Engine
    from openchem.domain.molecule import MoleculeModel as _MoleculeModel
    from openchem.domain.scientific_result import NMRSpectrumResult

    engine = _Engine()
    molecule = _MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    hydrogens = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1]
    methyl, methylene = hydrogens[:3], hydrogens[3:5]
    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_calibrated",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid=molecule.uuid,
        values={i: 1.2 for i in methyl} | {i: 3.6 for i in methylene},
        elements={i: "H" for i in methyl + methylene},
        couplings={(methyl[0], methylene[0]): 7.05},
    )
    view = NmrViewWidget(engine, backend=FakeViewerBackend())
    view.set_spectrum(molecule.molblock, spectrum)

    note = view._coupling_note_label.text()
    assert "calculated" in note and "not calculated" not in note
    assert view._frequency_combo.currentText() in note
    # Only one of the methylene group's two members has a real value in
    # this fixture, so this is a symmetry-completed group -- the note
    # must say so, not read identically to a fully-reported one.
    assert "symmetry-completed" in note


def test_a_fully_reported_group_gets_the_plain_note_without_symmetry_completion(qapp):
    """The contrast case: every member of every signal's own real coupling
    group has a real value -- both the methyl signal's partner group
    (methylene, 2 members) and the methylene signal's partner group
    (methyl, 3 members) are fully covered here, so `coupling_groups_
    inferred` is False for both signals and the note must not claim a
    symmetry-completed value where none was needed."""
    from openchem.chem.engine import ChemistryEngine as _Engine
    from openchem.domain.molecule import MoleculeModel as _MoleculeModel
    from openchem.domain.scientific_result import NMRSpectrumResult

    engine = _Engine()
    molecule = _MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    hydrogens = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1]
    methyl, methylene = hydrogens[:3], hydrogens[3:5]
    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_calibrated",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid=molecule.uuid,
        values={i: 1.2 for i in methyl} | {i: 3.6 for i in methylene},
        elements={i: "H" for i in methyl + methylene},
        couplings={
            (methyl[0], methylene[0]): 7.05,
            (methyl[0], methylene[1]): 7.05,
            (methyl[1], methylene[0]): 7.05,
            (methyl[2], methylene[0]): 7.05,
        },
    )
    view = NmrViewWidget(engine, backend=FakeViewerBackend())
    view.set_spectrum(molecule.molblock, spectrum)

    note = view._coupling_note_label.text()
    assert "calculated" in note and "not calculated" not in note
    assert "symmetry-completed" not in note


def test_a_coupling_parse_failure_gets_its_own_note_not_the_generic_one(qapp):
    from openchem.chem.engine import ChemistryEngine as _Engine
    from openchem.domain.molecule import MoleculeModel as _MoleculeModel
    from openchem.domain.scientific_result import NMRSpectrumResult

    engine = _Engine()
    molecule = _MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    methyl = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1][:3]
    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_calibrated",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid=molecule.uuid,
        values={i: 1.2 for i in methyl},
        elements={i: "H" for i in methyl},
        couplings=None,
        coupling_error="unreadable SPIN-SPIN COUPLING table",
    )
    view = NmrViewWidget(engine, backend=FakeViewerBackend())
    view.set_spectrum(molecule.molblock, spectrum)

    note = view._coupling_note_label.text()
    assert "could not be parsed" in note
    assert "unreadable SPIN-SPIN COUPLING table" in note


def test_changing_frequency_refreshes_the_notes_stated_frequency(qapp):
    from openchem.chem.engine import ChemistryEngine as _Engine
    from openchem.domain.molecule import MoleculeModel as _MoleculeModel
    from openchem.domain.scientific_result import NMRSpectrumResult

    engine = _Engine()
    molecule = _MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    hydrogens = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1]
    methyl, methylene = hydrogens[:3], hydrogens[3:5]
    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_calibrated",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid=molecule.uuid,
        values={i: 1.2 for i in methyl} | {i: 3.6 for i in methylene},
        elements={i: "H" for i in methyl + methylene},
        couplings={(methyl[0], methylene[0]): 7.05},
    )
    view = NmrViewWidget(engine, backend=FakeViewerBackend())
    view.set_spectrum(molecule.molblock, spectrum)
    other_index = 0 if view._frequency_combo.currentIndex() != 0 else 1
    other_text = view._frequency_combo.itemText(other_index)

    view._frequency_combo.setCurrentIndex(other_index)

    assert other_text in view._coupling_note_label.text()


def test_table_columns_have_no_prediction_quality(qapp):
    """Marvin shows a confidence rating here because it has an experimental
    reference database behind every number. Nothing here does, so rating one
    would be invented rather than measured."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    headers = [view._table.horizontalHeaderItem(i).text() for i in range(view._table.columnCount())]

    assert headers == ["Shift (ppm)", "Integration", "Multiplicity", "Coupling (Hz)", "Method"]
    assert not any("quality" in header.lower() or "confidence" in header.lower() for header in headers)


def test_table_reports_the_method_the_numbers_came_from(qapp):
    view, _backend, _molecule, spectrum = _make_view(qapp)
    assert view._table.item(0, 4).text() == spectrum.method


def test_missing_coupling_data_shows_a_dash_not_a_zero(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    assert view._table.item(0, 3).text() == "—"


def test_spectrum_widget_receives_the_same_signals_as_the_table(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    assert view._spectrum_widget._signals == view.signals()


def test_nucleus_combo_offers_the_elements_present_and_defaults_to_proton(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    offered = {view._element_combo.itemData(i) for i in range(view._element_combo.count())}

    assert offered == {"H", "C"}
    assert view._element_combo.currentData() == "H"


def test_switching_nucleus_rebuilds_the_signal_list(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    view._element_combo.setCurrentIndex(view._element_combo.findData("C"))

    assert all(signal.element == "C" for signal in view.signals())
    assert view._table.rowCount() == len(view.signals())


def test_clicking_a_peak_selects_its_table_row(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    target = view.signals()[3]

    view._on_peak_clicked(list(target.atom_indices))

    assert {index.row() for index in view._table.selectedIndexes()} == {3}


def test_clicking_a_peak_highlights_its_atoms_in_the_3d_view(qapp):
    view, backend, _molecule, _spectrum = _make_view(qapp)
    target = view.signals()[0]

    view._on_peak_clicked(list(target.atom_indices))

    colors = backend.applied_layers[-1].atom_colors
    highlighted = {index for index, color in colors.items() if color == nmr_view_module._HIGHLIGHT_COLOR}
    assert highlighted == set(target.atom_indices)


def test_every_signal_atom_keeps_a_shift_label_in_3d(qapp):
    """The 3Dmol.js backend clears the whole layer (labels included) when it
    is handed no colours, so unselected atoms carry a neutral base colour
    rather than none at all."""
    view, backend, _molecule, _spectrum = _make_view(qapp)
    all_signal_atoms = {index for signal in view.signals() for index in signal.atom_indices}

    layer = backend.applied_layers[-1]

    assert set(layer.atom_colors) == all_signal_atoms
    assert set(layer.atom_labels) == all_signal_atoms


def test_a_3d_atom_click_selects_the_owning_signal(qapp):
    """The inbound half of the bidirectional link: `atoms_selected` carries
    one atom index, and the signal that owns it is what gets selected."""
    view, backend, _molecule, _spectrum = _make_view(qapp)
    target = view.signals()[2]

    backend.atoms_selected.emit([target.atom_indices[0]])

    assert {index.row() for index in view._table.selectedIndexes()} == {2}
    assert view._spectrum_widget._highlighted_atoms == set(target.atom_indices)


def test_a_3d_click_on_an_atom_with_no_signal_changes_nothing(qapp):
    """Clicking a carbon while the ¹H view is active must not clear or
    mis-select the current highlight."""
    view, backend, _molecule, _spectrum = _make_view(qapp)
    view._on_peak_clicked(list(view.signals()[0].atom_indices))
    before = set(view._spectrum_widget._highlighted_atoms)

    backend.atoms_selected.emit([0])  # a heavy atom, never in a 1H signal

    assert view._spectrum_widget._highlighted_atoms == before


def test_selecting_a_table_row_highlights_the_peak(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    view._table.selectRow(4)

    assert view._spectrum_widget._highlighted_atoms == set(view.signals()[4].atom_indices)


# --- Zoom follows selection -------------------------------------------


def test_selecting_a_signal_zooms_to_it_by_default(qapp):
    """Marvin's own "Zoom Follows Selection", on by default -- a peak
    click, a table row, and a 3D atom click all resolve through
    `_select_signal`, so one check here covers all three paths."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    assert view._zoom_follow_check.isChecked()
    assert not view._spectrum_widget.is_zoomed()

    view._on_peak_clicked(list(view.signals()[3].atom_indices))

    assert view._spectrum_widget.is_zoomed()


def test_unchecking_zoom_to_selection_turns_it_off(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    view._zoom_follow_check.setChecked(False)

    view._on_peak_clicked(list(view.signals()[3].atom_indices))

    assert not view._spectrum_widget.is_zoomed()


def test_a_table_row_selection_also_zooms(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    view._table.selectRow(2)

    assert view._spectrum_widget.is_zoomed()


def test_a_3d_atom_click_also_zooms(qapp):
    view, backend, _molecule, _spectrum = _make_view(qapp)
    target = view.signals()[1]

    backend.atoms_selected.emit([target.atom_indices[0]])

    assert view._spectrum_widget.is_zoomed()


# --- Resizable internal layout (nested splitters) ----------------------


def test_the_layout_is_a_nested_splitter_not_a_flat_one(qapp):
    """Outer vertical [structures | spectrum | table], inner horizontal
    [2D | 3D]."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QSplitter

    view, _backend, _molecule, _spectrum = _make_view(qapp)

    assert isinstance(view._main_splitter, QSplitter)
    assert view._main_splitter.orientation() == Qt.Orientation.Vertical
    assert view._main_splitter.count() == 3
    assert view._main_splitter.widget(0) is view._structures_splitter
    assert view._main_splitter.widget(1) is view._spectrum_widget
    # The signal table now lives in a tab widget beside its Atoms and Couplings views.
    assert view._main_splitter.widget(2) is view._table_tabs
    assert view._table_tabs.widget(0) is view._table

    assert isinstance(view._structures_splitter, QSplitter)
    assert view._structures_splitter.orientation() == Qt.Orientation.Horizontal
    assert view._structures_splitter.count() == 2
    assert view._structures_splitter.widget(0) is view._svg_widget
    # Not compared against `view._backend.widget()` directly: the test
    # double's own `widget()` builds a NEW `QWidget` on every call, so a
    # second call here would never match the one instance embedded at
    # construction regardless of what the production code does.
    assert view._structures_splitter.widget(1) is not None


def test_neither_splitter_lets_a_pane_collapse_away(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    assert view._main_splitter.childrenCollapsible() is False
    assert view._structures_splitter.childrenCollapsible() is False


def test_every_pane_has_a_real_minimum_size(qapp):
    """So a splitter can't be dragged into an unusably tiny sliver. The
    embedded 3D widget is read off the splitter itself, not a fresh
    `backend.widget()` call -- see the note above."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    assert view._svg_widget.minimumSize().width() > 0
    assert view._svg_widget.minimumSize().height() > 0
    assert view._structures_splitter.widget(1).minimumSize().width() > 0
    assert view._table.minimumHeight() > 0


def test_the_table_is_visible_by_default_not_hidden_behind_a_tab(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    assert not view._table.isHidden()


def test_sorting_by_shift_orders_numerically(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)

    view._table.sortItems(0, Qt.SortOrder.DescendingOrder)
    shown = [float(view._table.item(row, 0).text()) for row in range(view._table.rowCount())]
    assert shown == sorted(shown, reverse=True)

    view._table.sortItems(0, Qt.SortOrder.AscendingOrder)
    shown = [float(view._table.item(row, 0).text()) for row in range(view._table.rowCount())]
    assert shown == sorted(shown)


def test_sorting_by_integration_orders_numerically_not_lexicographically(qapp):
    """"12H" must sort after "2H" and "3H" -- lexicographic order would
    put it first."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    view._signals = [
        NMRSignal(shift=1.0, atom_indices=[0], integration=2, multiplicity="s"),
        NMRSignal(shift=2.0, atom_indices=[1], integration=12, multiplicity="s"),
        NMRSignal(shift=3.0, atom_indices=[2], integration=3, multiplicity="s"),
    ]
    view._populate_table()

    view._table.sortItems(1, Qt.SortOrder.AscendingOrder)

    order = [view._table.item(row, 1).text() for row in range(view._table.rowCount())]
    assert order == ["2H", "3H", "12H"]


def test_sorting_by_coupling_groups_the_dash_rows_without_raising(qapp):
    """A mixed column (real Hz floats alongside the "no data" em dash)
    must sort deterministically, not raise a TypeError from comparing a
    float against a string."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    view._signals = [
        NMRSignal(shift=1.0, atom_indices=[0], integration=1, multiplicity="d", coupling_hz=[7.0]),
        NMRSignal(shift=2.0, atom_indices=[1], integration=1, multiplicity="m"),
        NMRSignal(shift=3.0, atom_indices=[2], integration=1, multiplicity="t", coupling_hz=[14.0]),
    ]
    view._populate_table()

    view._table.sortItems(3, Qt.SortOrder.AscendingOrder)

    order = [view._table.item(row, 3).text() for row in range(view._table.rowCount())]
    assert order == ["—", "7.0", "14.0"]


def test_selecting_a_table_row_after_sorting_resolves_the_correct_signal(qapp):
    """The regression this phase exists to prevent: with row index
    trusted instead of the row's own stored identity, selecting row 0
    after a descending sort would have resolved to `self._signals[0]`
    (the LOWEST shift) instead of the row actually showing the HIGHEST."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    view._table.sortItems(0, Qt.SortOrder.DescendingOrder)
    expected_signal = max(view.signals(), key=lambda s: s.shift)

    view._table.selectRow(0)

    assert view._spectrum_widget._highlighted_atoms == set(expected_signal.atom_indices)


def test_selecting_a_signal_still_selects_the_right_row_after_a_sort(qapp):
    """The other direction of the same link: `_select_signal` (reached
    from a peak click or a 3D atom click) must find the row by identity
    too, not by `self._signals.index(signal)`."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    view._table.sortItems(0, Qt.SortOrder.DescendingOrder)
    target = min(view.signals(), key=lambda s: s.shift)

    view._on_peak_clicked(list(target.atom_indices))

    selected_rows = {index.row() for index in view._table.selectedIndexes()}
    assert len(selected_rows) == 1
    row = selected_rows.pop()
    assert view._table.item(row, 0).data(nmr_view_module._ROW_IDENTITY_ROLE) == tuple(target.atom_indices)


def test_a_rebuilt_spectrum_resets_the_sort_order(qapp):
    """A fresh population always inserts in `self._signals`'s own
    (shift-ascending) order, so sorting never persists across a new
    spectrum or run -- confirmed here via `_rebuild_signals`, the same
    method a real nucleus switch or a new molecule calls."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    view._table.sortItems(0, Qt.SortOrder.DescendingOrder)
    descending = [float(view._table.item(row, 0).text()) for row in range(view._table.rowCount())]
    assert descending == sorted(descending, reverse=True)

    view._rebuild_signals()

    shown = [float(view._table.item(row, 0).text()) for row in range(view._table.rowCount())]
    natural = [round(signal.shift, 2) for signal in view.signals()]
    assert shown == natural


def test_the_default_split_favours_the_spectrum(qapp):
    """The 2D depiction's own large minimum used to eat most of the
    default space -- the complaint Phase D exists to fix. Resized to a
    realistic size and laid out for real, the spectrum pane (index 1)
    must end up taller than either of its siblings."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    view.resize(900, 900)
    view.show()
    qapp.processEvents()

    sizes = view._main_splitter.sizes()
    assert len(sizes) == 3
    assert sizes[1] > sizes[0]
    assert sizes[1] > sizes[2]
    view.hide()


def test_structure_labels_land_on_heavy_atoms_only(qapp):
    """The 2D depiction is drawn from the editor molblock, whose hydrogens
    are implicit -- a proton shift has to be drawn on its parent carbon or
    it silently disappears."""
    view, _backend, molecule, _spectrum = _make_view(qapp)
    heavy_atom_count = Chem.MolFromMolBlock(molecule.molblock).GetNumAtoms()

    for signal in view.signals():
        for atom_index in depiction_atoms(view._mol, signal):
            assert atom_index < heavy_atom_count


def test_a_molecule_with_no_protons_still_renders(qapp):
    """Carbon tetrachloride has no 1H signals at all -- the view must fall
    back rather than raise on an empty proton list."""
    view, _backend, _molecule, _spectrum = _make_view(qapp, "ClC(Cl)(Cl)Cl")
    assert view._table.rowCount() == len(view.signals())


def test_a_raw_shielding_result_is_labelled_sigma_and_drawn_ascending(qapp):
    """The header says shielding, so the axis and the table must too: a
    sigma on a delta axis read as a backwards spectrum."""
    import dataclasses

    view, _backend, molecule, spectrum = _make_view(qapp)
    raw = dataclasses.replace(spectrum, spectrum_type="nmr_raw_shielding")
    view.set_spectrum(molecule.molblock, raw)

    assert view._spectrum_widget._shielding is True
    assert "σ" in view._spectrum_widget._x_label
    assert "σ" in view._table.horizontalHeaderItem(0).text()

    view.set_spectrum(molecule.molblock, spectrum)
    assert view._spectrum_widget._shielding is False
    assert "δ" in view._spectrum_widget._x_label


# --- Phase G: Hz/ppm toggle, wired through the view ----------------------


def test_the_unit_combo_is_disabled_on_a_raw_shielding_spectrum(qapp):
    import dataclasses

    view, _backend, molecule, spectrum = _make_view(qapp)
    assert view._unit_combo.isEnabled() is True

    raw = dataclasses.replace(spectrum, spectrum_type="nmr_raw_shielding")
    view.set_spectrum(molecule.molblock, raw)
    assert view._unit_combo.isEnabled() is False

    view.set_spectrum(molecule.molblock, spectrum)
    assert view._unit_combo.isEnabled() is True


def test_switching_to_hz_updates_both_the_table_header_and_its_values(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    signal = view.signals()[0]

    view._unit_combo.setCurrentIndex(view._unit_combo.findData("hz"))

    assert view._table.horizontalHeaderItem(0).text() == "Offset (Hz)"
    row = view._row_for_signal(signal)
    cell_text = view._table.item(row, 0).text()
    assert cell_text == view._spectrum_widget.format_shift(signal.shift)
    expected_hz = signal.shift * view._spectrum_widget._observation_mhz()
    assert abs(float(cell_text) - expected_hz) < 0.05


def test_switching_back_to_ppm_restores_the_plain_header(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    view._unit_combo.setCurrentIndex(view._unit_combo.findData("hz"))
    assert view._table.horizontalHeaderItem(0).text() == "Offset (Hz)"

    view._unit_combo.setCurrentIndex(view._unit_combo.findData("ppm"))

    assert view._table.horizontalHeaderItem(0).text() == "Shift (ppm)"


# --- Phase G: Spectrum Labels combo, wired through the view --------------


def test_the_labels_combo_controls_the_plots_label_mode(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    assert view._spectrum_widget.label_mode() == "shift"

    view._labels_combo.setCurrentIndex(view._labels_combo.findData("atom"))
    assert view._spectrum_widget.label_mode() == "atom"

    view._labels_combo.setCurrentIndex(view._labels_combo.findData("none"))
    assert view._spectrum_widget.label_mode() == "none"
    assert view._table.horizontalHeaderItem(0).text() == "Shift (ppm)"


# --- Phase H: the controls row became a QToolBar, plus Reset Zoom and
# Copy Spectrum Image ------------------------------------------------------


def test_the_toolbar_carries_every_existing_control_in_order(qapp):
    """The container swap (QHBoxLayout -> QToolBar) must not drop a
    control or its caption, or silently reorder them. Checked by the
    project's own widgets appearing in the intended sequence, not by a
    raw `findChildren()` comparison -- Qt can insert its own internal
    action widgets into a QToolBar that a literal child-list equality
    would trip over."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)

    expected_order = [
        view._element_combo,
        view._frequency_combo,
        view._solvent_combo,
        view._unit_combo,
        view._labels_combo,
        view._smooth_check,
        view._decoupled_check,
        view._integral_check,
        view._zoom_follow_check,
    ]
    # Two rows now (the one toolbar overflowed into "..." on screen); read
    # them top to bottom as one sequence.
    toolbar_widgets = [
        action.defaultWidget()
        for toolbar in (child for child in view.children() if isinstance(child, QToolBar))
        for action in toolbar.actions()
        if isinstance(action, QWidgetAction)
    ]
    positions = [toolbar_widgets.index(widget) for widget in expected_order]
    assert positions == sorted(positions), "controls are out of their original order"

    captions = [w.text() for w in toolbar_widgets if isinstance(w, QLabel)]
    assert captions == ["Nucleus:", "Frequency:", "Solvent peak:", "Unit:"]


def test_the_toolbar_still_fires_every_controls_existing_handler(qapp):
    """Presence isn't enough -- the swap must not have silently
    disconnected a signal either."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)

    view._frequency_combo.setCurrentIndex(1)
    assert view._spectrum_widget._frequency_mhz == view._frequency_combo.currentData()

    view._solvent_combo.setCurrentIndex(1)
    assert view._spectrum_widget._solvent == view._solvent_combo.currentData()

    view._smooth_check.setChecked(True)
    assert view._spectrum_widget._render_mode == "smooth"

    view._decoupled_check.setChecked(True)
    assert view._spectrum_widget.is_decoupled() is True

    view._integral_check.setChecked(True)
    assert view._spectrum_widget._show_integral is True


def test_the_toolbar_swap_does_not_change_the_unit_combos_enabled_state(qapp):
    import dataclasses

    view, _backend, molecule, spectrum = _make_view(qapp)
    assert view._unit_combo.isEnabled() is True

    raw = dataclasses.replace(spectrum, spectrum_type="nmr_raw_shielding")
    view.set_spectrum(molecule.molblock, raw)
    assert view._unit_combo.isEnabled() is False


def test_scroll_safe_guards_still_intercept_a_wheel_event_inside_the_toolbar(qapp):
    """A container swap is exactly the kind of change that can alter
    event propagation while leaving the guard object itself intact --
    this checks the actual behaviour, not just that the guard exists."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QWheelEvent

    combo = view._frequency_combo
    combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    before = combo.currentIndex()
    event = QWheelEvent(
        QPoint(5, 5).toPointF(),
        QPoint(5, 5).toPointF(),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(combo, event)
    assert combo.currentIndex() == before, "an unfocused combo inside the toolbar still scrolled"


def test_reset_zoom_restores_the_exact_full_span_not_merely_is_zoomed_false(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    full_range = view._spectrum_widget.view_range()

    view._on_peak_clicked(list(view.signals()[3].atom_indices))
    assert view._spectrum_widget.is_zoomed()
    assert view._spectrum_widget.view_range() != full_range

    view._reset_zoom_action.trigger()

    assert not view._spectrum_widget.is_zoomed()
    assert view._spectrum_widget.view_range() == full_range


def test_copy_spectrum_image_reflects_the_current_state_not_a_stale_one(qapp):
    """Zooms first, so a future refactor that copied a cached pixmap from
    before the state change would fail this, while a weaker test that
    only checked "is the clipboard non-null" would not catch it."""
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    view._on_peak_clicked(list(view.signals()[3].atom_indices))
    expected = view._spectrum_widget.grab()

    view._copy_spectrum_action.trigger()

    clipboard_pixmap = QApplication.clipboard().pixmap()
    assert not clipboard_pixmap.isNull()
    expected_logical_size = expected.size() / expected.devicePixelRatio()
    clipboard_logical_size = clipboard_pixmap.size() / clipboard_pixmap.devicePixelRatio()
    assert clipboard_logical_size == expected_logical_size


# --- Phase P1: legend and Reset Settings --------------------------------------


def test_a_fresh_viewer_reports_exactly_the_canonical_defaults(qapp):
    """The drift guard: a control added to the toolbar with a different
    starting value than `NMR_VIEWER_DEFAULTS` fails here, instead of quietly
    surviving a Reset."""
    view, *_ = _make_view(qapp)

    assert view.current_settings() == nmr_view_module.NMR_VIEWER_DEFAULTS


def _change_every_setting(view):
    view._frequency_combo.setCurrentIndex(view._frequency_combo.count() - 1)
    view._solvent_combo.setCurrentIndex(1)
    view._unit_combo.setCurrentIndex(1)
    view._labels_combo.setCurrentIndex(2)
    for check in (view._smooth_check, view._decoupled_check, view._integral_check, view._legend_check):
        check.setChecked(True)
    view._zoom_follow_check.setChecked(False)


def test_reset_settings_restores_every_control_and_what_the_plot_does(qapp):
    view, *_ = _make_view(qapp)
    _change_every_setting(view)
    assert view.current_settings() != nmr_view_module.NMR_VIEWER_DEFAULTS

    view.reset_settings()

    assert view.current_settings() == nmr_view_module.NMR_VIEWER_DEFAULTS
    plot = view._spectrum_widget
    assert plot.render_mode() == "sticks" and not plot.is_decoupled()
    assert not plot.is_legend_shown() and plot.label_mode() == "shift" and plot.display_unit() == "ppm"


def test_reset_settings_keeps_the_zoom(qapp):
    view, *_ = _make_view(qapp)
    view._spectrum_widget.zoom_to_signal(view.signals()[0])
    assert view._spectrum_widget.is_zoomed()
    view._smooth_check.setChecked(True)

    view.reset_settings()

    assert view._spectrum_widget.is_zoomed()
    assert not view._smooth_check.isChecked()


def test_reset_zoom_keeps_the_settings(qapp):
    view, *_ = _make_view(qapp)
    view._spectrum_widget.zoom_to_signal(view.signals()[0])
    view._smooth_check.setChecked(True)

    view._reset_zoom_action.trigger()

    assert not view._spectrum_widget.is_zoomed()
    assert view._smooth_check.isChecked()


def test_the_reset_settings_action_is_in_the_toolbar_and_wired(qapp):
    view, *_ = _make_view(qapp)
    view._legend_check.setChecked(True)

    view._reset_settings_action.trigger()

    assert not view._legend_check.isChecked()
    toolbar = view.findChild(QToolBar)
    assert view._reset_settings_action in toolbar.actions()


def test_the_legend_lists_only_marks_that_are_on_the_plot(qapp):
    view, *_ = _make_view(qapp)
    plot = view._spectrum_widget

    base = {text for _k, text, _c in plot.legend_entries()}
    assert not any("integral" in t or "Solvent" in t for t in base)

    view._integral_check.setChecked(True)
    view._solvent_combo.setCurrentIndex(1)
    shown = {text for _k, text, _c in plot.legend_entries()}
    assert any("integral" in t for t in shown) and any("Solvent" in t for t in shown)


def test_the_legend_draws_only_when_asked_and_never_changes_the_data(qapp):
    view, *_ = _make_view(qapp)
    plot = view._spectrum_widget
    plot.resize(600, 300)
    snapshot = [(s.shift, s.multiplicity, s.coupling_groups, s.integration) for s in view.signals()]
    plain = plot.grab().toImage()

    view._legend_check.setChecked(True)
    with_key = plot.grab().toImage()

    assert plain != with_key
    assert snapshot == [(s.shift, s.multiplicity, s.coupling_groups, s.integration) for s in view.signals()]
    view._legend_check.setChecked(False)
    assert plot.grab().toImage() == plain


# --- Phase P2: explicit hydrogens on the structure pane -----------------------


def _drawn_svg(view) -> tuple:
    calls = []
    original = view._engine.render_2d_svg

    def spy(*args, **kwargs):
        svg = original(*args, **kwargs)
        calls.append((kwargs.get("explicit_hydrogens"), svg))
        return svg

    view._engine.render_2d_svg = spy
    view._render_structure(view._highlighted_atoms)
    view._engine.render_2d_svg = original
    return calls[-1]


def test_explicit_hydrogens_draw_more_atoms_and_leave_the_molecule_alone(qapp):
    view, _backend, molecule, _spectrum = _make_view(qapp)
    before = molecule.molblock
    off_flag, off_svg = _drawn_svg(view)

    view._explicit_h_check.setChecked(True)
    on_flag, on_svg = _drawn_svg(view)

    assert (off_flag, on_flag) == (False, True)
    assert on_svg.count("<path") > off_svg.count("<path")  # the hydrogens are drawn
    assert molecule.molblock == before and view._molblock == before


def test_the_hydrogen_toggle_keeps_the_selection_and_the_signals(qapp):
    view, *_ = _make_view(qapp)
    view._select_signal(view.signals()[2])
    selected = list(view._highlighted_atoms)
    snapshot = [(s.shift, s.multiplicity, s.coupling_groups) for s in view.signals()]

    view._explicit_h_check.setChecked(True)

    assert view._highlighted_atoms == selected
    assert snapshot == [(s.shift, s.multiplicity, s.coupling_groups) for s in view.signals()]


def test_explicit_hydrogens_is_a_setting_that_reset_restores(qapp):
    view, *_ = _make_view(qapp)
    view._explicit_h_check.setChecked(True)
    assert view.current_settings().explicit_hydrogens is True

    view.reset_settings()

    assert not view._explicit_h_check.isChecked()
    assert view.current_settings() == nmr_view_module.NMR_VIEWER_DEFAULTS


# --- Phase P2: the Atoms and Couplings views ------------------------------------


def _with_couplings(view):
    """Give two signals real coupling groups, so the Couplings view has rows."""
    import dataclasses

    signals = list(view.signals())
    signals[0] = dataclasses.replace(signals[0], coupling_groups=((2, 7.1), (1, 6.9)), coupling_groups_inferred=True)
    signals[1] = dataclasses.replace(signals[1], coupling_groups=((3, 7.0),))
    view._signals = signals
    view._populate_table()
    return signals


def test_the_three_views_are_tabs_over_the_one_signal_list(qapp):
    view, *_ = _make_view(qapp)
    signals = _with_couplings(view)

    tabs = view._table_tabs
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["Signals", "Atoms", "Couplings"]
    assert view._table.rowCount() == len(signals)
    assert view._atoms_table.rowCount() == sum(len(s.atom_indices) for s in signals)
    assert view._couplings_table.rowCount() == 3  # 2 + 1 groups; the rest have none


def test_a_signal_with_no_calculated_coupling_has_no_coupling_row(qapp):
    view, *_ = _make_view(qapp)
    _with_couplings(view)
    owners = {view._couplings_table.item(r, 0).data(nmr_view_module._ROW_IDENTITY_ROLE)
              for r in range(view._couplings_table.rowCount())}

    assert owners == {tuple(view.signals()[0].atom_indices), tuple(view.signals()[1].atom_indices)}


def test_the_coupling_rows_say_when_a_value_was_symmetry_completed(qapp):
    view, *_ = _make_view(qapp)
    _with_couplings(view)
    sources = [view._couplings_table.item(r, 3).text() for r in range(view._couplings_table.rowCount())]

    assert sources.count("symmetry-completed") == 2 and sources.count("calculated") == 1


def test_atom_numbers_are_the_one_based_numbers_used_elsewhere(qapp):
    view, *_ = _make_view(qapp)
    first = view.signals()[0]

    shown = {view._atoms_table.item(r, 0).text() for r in range(view._atoms_table.rowCount())}

    assert str(first.atom_indices[0] + 1) in shown and "0" not in shown


def _select_row(table, row):
    table.blockSignals(False)
    table.selectRow(row)


def test_selecting_in_any_tab_selects_the_same_signal_everywhere(qapp):
    view, *_ = _make_view(qapp)
    signals = _with_couplings(view)
    target = signals[1]

    view._atoms_table.selectRow(next(
        r for r in range(view._atoms_table.rowCount())
        if view._atoms_table.item(r, 0).data(nmr_view_module._ROW_IDENTITY_ROLE) == tuple(target.atom_indices)
    ))
    assert list(view._spectrum_widget._highlighted_atoms) == list(target.atom_indices) or \
        set(view._spectrum_widget._highlighted_atoms) == set(target.atom_indices)
    selected_signal_rows = {i.row() for i in view._table.selectedIndexes()}
    assert view._table.item(selected_signal_rows.pop(), 0).data(nmr_view_module._ROW_IDENTITY_ROLE) == tuple(target.atom_indices)

    view._couplings_table.selectRow(0)  # a coupling row of signal 0
    assert set(view._spectrum_widget._highlighted_atoms) == set(signals[0].atom_indices)


def test_the_selection_follows_the_identity_not_the_row_number_after_a_sort(qapp):
    view, *_ = _make_view(qapp)
    signals = _with_couplings(view)
    view._table.sortByColumn(0, Qt.SortOrder.DescendingOrder)  # reorders the Signals rows only

    view._select_signal(signals[1])

    atom_rows = {i.row() for i in view._atoms_table.selectedIndexes()}
    assert atom_rows
    item = view._atoms_table.item(atom_rows.pop(), 0)
    assert item.data(nmr_view_module._ROW_IDENTITY_ROLE) == tuple(signals[1].atom_indices)


def test_a_unit_change_updates_the_projection_shift_text_too(qapp):
    view, *_ = _make_view(qapp)
    _with_couplings(view)
    before = view._atoms_table.item(0, 1).text()

    view._unit_combo.setCurrentIndex(1)  # Offset (Hz)

    assert view._atoms_table.item(0, 1).text() != before


# --- Phase P2: colour palettes -----------------------------------------------------


def test_the_palettes_are_a_short_fixed_list_naming_exactly_the_four_marks(qapp):
    from openchem.ui.widgets.nmr_spectrum_widget import NMR_PALETTES

    assert list(NMR_PALETTES) == ["Default", "Colour-blind safe", "High contrast"]
    for colours in NMR_PALETTES.values():
        assert set(colours) == {"peak", "highlight", "solvent", "integral", "reference"}
        assert len(set(colours.values())) == 5  # no two marks share a colour


def test_choosing_a_palette_recolours_the_plot_and_the_structure_pane_together(qapp):
    view, backend, *_ = _make_view(qapp)
    view._select_signal(view.signals()[0])
    plain = view._spectrum_widget.grab().toImage()

    view._palette_combo.setCurrentIndex(view._palette_combo.findData("High contrast"))

    assert view._spectrum_widget.palette_name() == "High contrast"
    assert view._spectrum_widget.grab().toImage() != plain
    layer = backend.applied_layers[-1]
    assert nmr_view_module.palette_hex("High contrast", "highlight") in layer.atom_colors.values()


def test_a_palette_never_touches_the_data_and_reset_restores_it(qapp):
    view, *_ = _make_view(qapp)
    snapshot = [(s.shift, s.multiplicity, s.coupling_groups, s.integration) for s in view.signals()]

    view._palette_combo.setCurrentIndex(2)
    assert view.current_settings().palette == "High contrast"
    assert snapshot == [(s.shift, s.multiplicity, s.coupling_groups, s.integration) for s in view.signals()]

    view.reset_settings()
    assert view._spectrum_widget.palette_name() == "Default"
    assert view.current_settings() == nmr_view_module.NMR_VIEWER_DEFAULTS


def test_an_unknown_palette_is_refused(qapp):
    import pytest

    from openchem.ui.widgets.nmr_spectrum_widget import NmrSpectrumWidget

    with pytest.raises(ValueError):
        NmrSpectrumWidget().set_palette("rainbow")


# --- Phase P3: a measured reference, and exporting ----------------------------------


def _write_jdx(tmp_path, name="measured.jdx", **kwargs):
    from test_nmr_measured import _jdx

    path = tmp_path / name
    path.write_text(_jdx(**kwargs), encoding="utf-8")
    return str(path)


def _snapshot(view):
    return [(s.shift, s.multiplicity, s.coupling_groups, s.integration, tuple(s.atom_indices)) for s in view.signals()]


def test_importing_a_reference_draws_it_and_says_it_is_not_a_prediction(qapp, tmp_path):
    view, *_ = _make_view(qapp)
    plain = view._spectrum_widget.grab().toImage()

    reference = view.load_reference_file(_write_jdx(tmp_path))

    assert reference is not None and view._spectrum_widget.reference_drawn()
    assert view._spectrum_widget.grab().toImage() != plain
    note = view._reference_note_label
    assert not note.isHidden() and "imported measurement, not a prediction" in note.text()
    assert view._clear_reference_action.isEnabled() and view._reference_scale_spin.isEnabled()


def test_import_scale_peaks_and_clear_never_touch_a_signal(qapp, tmp_path):
    view, *_ = _make_view(qapp)
    before = _snapshot(view)

    view.load_reference_file(_write_jdx(tmp_path))
    view._reference_scale_spin.setValue(3.0)
    view._reference_peaks_check.setChecked(True)
    view._spectrum_widget.grab()
    assert _snapshot(view) == before
    view.clear_reference()

    assert _snapshot(view) == before and view.reference() is None


def test_scaling_is_display_only_and_the_record_is_never_rewritten(qapp, tmp_path):
    view, *_ = _make_view(qapp)
    reference = view.load_reference_file(_write_jdx(tmp_path))
    ppm, intensity = reference.ppm, reference.intensity

    view._reference_scale_spin.setValue(4.0)
    view._reference_scale_spin.setValue(0.5)

    assert view.reference() is reference
    assert reference.ppm is ppm and reference.intensity is intensity
    assert view._spectrum_widget.reference_scale() == 0.5
    view._reference_scale_spin.setValue(1.0)  # reversible: nothing was baked in
    assert view._spectrum_widget.reference_scale() == 1.0


def test_the_scale_changes_what_is_drawn_and_only_that(qapp, tmp_path):
    view, *_ = _make_view(qapp)
    view.load_reference_file(_write_jdx(tmp_path))
    one = view._spectrum_widget.grab().toImage()

    view._reference_scale_spin.setValue(0.3)

    assert view._spectrum_widget.grab().toImage() != one


def test_a_file_that_will_not_load_is_reported_and_draws_nothing(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a[2])))
    view, *_ = _make_view(qapp)

    result = view.load_reference_file(_write_jdx(tmp_path, data_type="NMR FID"))

    assert result is None and view.reference() is None and not view._spectrum_widget.reference_drawn()
    assert shown and "FID" in shown[0]


def test_a_missing_file_is_reported_not_swallowed(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a[1])))
    view, *_ = _make_view(qapp)

    assert view.load_reference_file(str(tmp_path / "nope.jdx")) is None
    assert shown == ["Could not open file"]


def test_a_reference_for_another_nucleus_is_kept_but_not_drawn_and_says_why(qapp, tmp_path):
    view, *_ = _make_view(qapp)
    view.load_reference_file(_write_jdx(tmp_path, nucleus="^13C"))

    assert view.reference() is not None and not view._spectrum_widget.reference_drawn()
    assert "not drawn" in view._reference_note_label.text()
    assert not any("Measured" in text for _k, text, _c in view._spectrum_widget.legend_entries())


def test_the_legend_lists_the_measured_trace_only_while_it_is_drawn(qapp, tmp_path):
    view, *_ = _make_view(qapp)
    assert not any("Measured" in t for _k, t, _c in view._spectrum_widget.legend_entries())

    view.load_reference_file(_write_jdx(tmp_path, name="ethyl.jdx"))

    assert any(t == "Measured: ethyl.jdx" for _k, t, _c in view._spectrum_widget.legend_entries())


def test_reset_settings_keeps_the_imported_reference_but_resets_its_scale(qapp, tmp_path):
    view, *_ = _make_view(qapp)
    reference = view.load_reference_file(_write_jdx(tmp_path))
    view._reference_scale_spin.setValue(5.0)
    view._reference_peaks_check.setChecked(True)

    view.reset_settings()

    assert view.reference() is reference
    assert view._reference_scale_spin.value() == 1.0 and not view._reference_peaks_check.isChecked()
    assert view.current_settings() == nmr_view_module.NMR_VIEWER_DEFAULTS


def test_importing_through_the_real_action_uses_the_file_dialog(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    path = _write_jdx(tmp_path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (path, "")))
    view, *_ = _make_view(qapp)

    view._import_reference_action.trigger()

    assert view.reference() is not None and view.reference().filename == "measured.jdx"


def test_two_imports_of_one_filename_with_different_bytes_are_distinguishable(qapp, tmp_path):
    view, *_ = _make_view(qapp)
    first = view.load_reference_file(_write_jdx(tmp_path, solvent="CDCl3"))
    second = view.load_reference_file(_write_jdx(tmp_path, solvent="DMSO-d6"))

    assert first.filename == second.filename and first.content_sha256 != second.content_sha256


def test_the_jcamp_export_reads_the_signals_and_the_viewer_parameters(qapp):
    from openchem.chem import jcamp
    from openchem.chem.nmr_measured import read_nmr_reference

    view, *_ = _make_view(qapp)
    view._solvent_combo.setCurrentIndex(1)
    before = _snapshot(view)

    text = view.export_jcamp_text()

    ref = read_nmr_reference(text, "export.jdx")
    assert ref.frequency_mhz == view._frequency_combo.currentData()
    assert ref.solvent == view._solvent_combo.currentData() and ref.nucleus == "H"
    assert jcamp.parse(text).point_count == 4096 and _snapshot(view) == before


def test_the_decoupled_switch_reaches_the_export(qapp):
    view, *_ = _make_view(qapp)
    _with_couplings(view)  # the synthetic spectrum carries no coupling data
    coupled = view.export_jcamp_text()
    view._decoupled_check.setChecked(True)

    assert view.export_jcamp_text() != coupled


def test_the_sdf_export_carries_the_molecule_with_hydrogens_and_the_shifts(qapp):
    view, *_ = _make_view(qapp)

    text = view.export_sdf_text()

    assert "> <NMR_1H_PREDICTED_SHIFTS>" in text and text.rstrip().endswith("$" * 4)
    assert "PREDICTED, not measured" in text


def test_the_pdf_export_writes_a_real_pdf(qapp, tmp_path):
    view, *_ = _make_view(qapp)
    target = tmp_path / "report.pdf"

    assert view.export_pdf(str(target)) is True

    data = target.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 2000


def test_each_export_action_writes_through_the_save_dialog(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    view, *_ = _make_view(qapp)
    targets = iter([str(tmp_path / "a.jdx"), str(tmp_path / "a.sdf"), str(tmp_path / "a.pdf")])
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (next(targets), "")))

    view._export_jcamp_action.trigger()
    view._export_sdf_action.trigger()
    view._export_pdf_action.trigger()

    assert (tmp_path / "a.jdx").read_text(encoding="utf-8").startswith("##TITLE")
    assert (tmp_path / "a.sdf").read_text(encoding="utf-8").rstrip().endswith("$" * 4)
    assert (tmp_path / "a.pdf").read_bytes().startswith(b"%PDF")


def test_cancelling_the_save_dialog_writes_nothing(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    view, *_ = _make_view(qapp)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    view._export_jcamp_action.trigger()

    assert list(tmp_path.iterdir()) == []
