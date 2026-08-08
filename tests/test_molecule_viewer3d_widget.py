from __future__ import annotations

from PySide6.QtWidgets import QWidget

from openchem.chem.engine import ChemistryEngine
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.services.conformer_service import ConformerService
from openchem.services.measurement_service import MeasurementService
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.visualization import VisualizationLayer
from openchem.ui.widgets.molecule_viewer3d_widget import MoleculeViewer3DWidget


class FakeViewerBackend(ViewerBackend):
    """Records calls instead of driving a real QWebEngineView -- the
    widget's own `backend=` constructor parameter exists for exactly this
    kind of fast, isolated test."""

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


def _make_widget(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    conformer_service = ConformerService(bus, engine)
    measurement_service = MeasurementService(engine)
    backend = FakeViewerBackend()
    widget = MoleculeViewer3DWidget(conformer_service, measurement_service, bus, backend=backend)
    return widget, backend, bus


def _molecule_with_conformer() -> MoleculeModel:
    model = MoleculeModel(display_name="Test")
    model.conformers = [ConformerModel(molblock="fake molblock", method="rdkit")]
    return model


def test_widget_has_no_color_by_dropdown(qapp):
    """Phase 23: per-property colouring moved out of this widget entirely --
    it predated CalculatorRegistry and hardcoded two properties, which the
    registry-driven Calculator Inspector now supersedes generically. This
    widget is style/navigation/measurement only."""
    widget, _backend, _bus = _make_widget(qapp)

    assert not hasattr(widget, "_color_by_combo")
    assert not hasattr(widget, "_per_atom_datasets")


def test_widget_never_applies_a_visualization_layer(qapp):
    widget, backend, _bus = _make_widget(qapp)
    widget.set_molecule(_molecule_with_conformer())

    assert backend.applied_layers == []


def test_loading_a_molecule_loads_its_first_conformer(qapp):
    widget, backend, _bus = _make_widget(qapp)
    widget.set_molecule(_molecule_with_conformer())

    assert backend.loaded_molblocks == ["fake molblock"]


def test_switching_conformer_loads_the_next_molblock(qapp):
    widget, backend, _bus = _make_widget(qapp)
    molecule = MoleculeModel(display_name="Test")
    molecule.conformers = [
        ConformerModel(molblock="conf-1", method="rdkit"),
        ConformerModel(molblock="conf-2", method="rdkit"),
    ]
    widget.set_molecule(molecule)

    widget._show_next_conformer()

    assert backend.loaded_molblocks[-1] == "conf-2"
    assert "2/2" in widget._status_label.text()


def test_switching_back_returns_to_the_previous_conformer(qapp):
    widget, backend, _bus = _make_widget(qapp)
    molecule = MoleculeModel(display_name="Test")
    molecule.conformers = [
        ConformerModel(molblock="conf-1", method="rdkit"),
        ConformerModel(molblock="conf-2", method="rdkit"),
    ]
    widget.set_molecule(molecule)
    widget._show_next_conformer()

    widget._show_previous_conformer()

    assert backend.loaded_molblocks[-1] == "conf-1"


def test_molecule_with_no_conformers_reports_none(qapp):
    widget, backend, _bus = _make_widget(qapp)

    widget.set_molecule(MoleculeModel(display_name="Empty"))

    assert widget._status_label.text() == "No conformers"
    assert backend.loaded_molblocks == []


def test_highlight_atoms_paints_and_clears(qapp):
    """The viewer half of hover-to-highlight.

    Wired to nothing yet -- see `ui/widgets/fact_view.py` for why the panel
    that would drive it is not adopted. Tested now so the API is known to
    work when it is.

    Safe to drive from a hover because this viewer applies no atom
    colouring of its own; there is no "Color by" layer to clobber and then
    fail to restore.
    """
    widget, backend, _bus = _make_widget(qapp)

    widget.highlight_atoms((1, 3))
    assert backend.applied_layers[-1].atom_colors == {1: "#ffb300", 3: "#ffb300"}

    widget.highlight_atoms(())
    assert backend.applied_layers[-1] is None


# --- a crystal is a different index space, and clicks must not cross ---------


class CrystalCapableBackend(FakeViewerBackend):
    """`load_crystal` is optional on a ViewerBackend -- Mol* predates
    crystals and simply does not have it -- so the fake needs its own
    subclass rather than growing the method for everybody."""

    def __init__(self) -> None:
        super().__init__()
        self.loaded_scenes: list[dict] = []

    def load_crystal(self, scene: dict) -> None:
        self.loaded_scenes.append(scene)


_SCENE = {
    "atoms": [
        {"element": "Na", "x": 0.0, "y": 0.0, "z": 0.0, "site": "Na1", "occupancy": 1.0},
        {"element": "Cl", "x": 2.8, "y": 0.0, "z": 0.0, "site": "Cl1", "occupancy": 1.0},
    ],
    "edges": [],
    "axes": [],
    "name": "fixture",
}


def _crystal_widget(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    widget = MoleculeViewer3DWidget(
        ConformerService(bus, engine),
        MeasurementService(engine),
        bus,
        backend=CrystalCapableBackend(),
    )
    return widget, widget._backend


def test_a_crystal_click_never_reaches_the_molecular_measurement(qapp):
    """**This was live.** `show_crystal` did not clear the molecule, so
    two clicks on a unit cell ran the distance measurement against
    whatever conformer happened to be loaded -- correct arithmetic on the
    wrong object, reported as a plain number in the readout."""
    widget, backend = _crystal_widget(qapp)
    widget.set_molecule(_molecule_with_conformer())
    widget.show_crystal(_SCENE)

    backend.atoms_selected.emit([0])
    backend.atoms_selected.emit([1])

    assert widget._measurement_label.text() == ""


def test_a_crystal_click_does_not_reach_the_atom_inspector(qapp):
    """A crystal atom and a molecular atom that share index 7 are not the
    same object. The inspector was spared before this only because
    `_atom_is_in_report` refuses out-of-range indices, which is luck."""
    widget, backend = _crystal_widget(qapp)
    atom_clicks: list[int] = []
    site_clicks: list[int] = []
    widget.atom_clicked.connect(atom_clicks.append)
    widget.crystal_site_clicked.connect(site_clicks.append)
    widget.show_crystal(_SCENE)

    backend.atoms_selected.emit([1])

    assert atom_clicks == []
    assert site_clicks == [1]


def test_a_molecule_loaded_after_a_crystal_gets_its_clicks_back(qapp):
    """The mirror image of the bug above, and the reason `set_molecule`
    clears the scene: a molecule shown after a unit cell must stop
    routing clicks into a scene nobody is drawing."""
    widget, backend = _crystal_widget(qapp)
    atom_clicks: list[int] = []
    site_clicks: list[int] = []
    widget.atom_clicked.connect(atom_clicks.append)
    widget.crystal_site_clicked.connect(site_clicks.append)

    widget.show_crystal(_SCENE)
    widget.set_molecule(_molecule_with_conformer())
    backend.atoms_selected.emit([1])

    assert site_clicks == []
    assert atom_clicks == [1]


def test_showing_a_crystal_drops_a_half_finished_measurement(qapp):
    """One click on a molecule, then a crystal import: the pending atom
    must not pair up with a crystal index on the next click."""
    widget, backend = _crystal_widget(qapp)
    widget.set_molecule(_molecule_with_conformer())
    backend.atoms_selected.emit([0])
    assert widget._selected_atoms == [0]

    widget.show_crystal(_SCENE)

    assert widget._selected_atoms == []
