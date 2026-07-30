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
