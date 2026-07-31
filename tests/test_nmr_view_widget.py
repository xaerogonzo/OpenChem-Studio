from __future__ import annotations

from PySide6.QtWidgets import QWidget
from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from conftest import synthetic_nmr_spectrum
from openchem.chem.nmr_signals import depiction_atoms
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

    def load_conformer(self, molblock: str) -> None:
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
