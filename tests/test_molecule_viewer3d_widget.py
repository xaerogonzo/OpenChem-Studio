from __future__ import annotations

from PySide6.QtWidgets import QWidget

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import PerAtomDataset
from openchem.events.base import EventBus
from openchem.events.events import PerAtomDataComputed
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


def test_color_by_default_never_applies_a_layer(qapp):
    widget, backend, _bus = _make_widget(qapp)
    widget.set_molecule(_molecule_with_conformer())

    # Default selection: apply_visualization(None) only (the "clear" case),
    # never a real layer.
    assert all(layer is None for layer in backend.applied_layers)


def test_selecting_color_by_applies_cached_dataset(qapp):
    widget, backend, bus = _make_widget(qapp)
    molecule = _molecule_with_conformer()
    widget.set_molecule(molecule)

    bus.publish(
        PerAtomDataComputed(
            dataset=PerAtomDataset(
                property_id="crippen_logp_contrib",
                name="LogP Contribution",
                units="",
                method="rdkit",
                molecule_uuid=molecule.uuid,
                values={0: -0.5, 1: 0.5},
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )

    widget._color_by_combo.setCurrentText("LogP contribution")

    real_layers = [layer for layer in backend.applied_layers if layer is not None]
    assert len(real_layers) == 1
    assert real_layers[0].atom_colors.keys() == {0, 1}
    assert "LogP Contribution" in widget._legend_label.text()


def test_per_atom_data_for_a_different_molecule_is_ignored(qapp):
    widget, backend, bus = _make_widget(qapp)
    widget.set_molecule(_molecule_with_conformer())
    widget._color_by_combo.setCurrentText("Partial charge")

    bus.publish(
        PerAtomDataComputed(
            dataset=PerAtomDataset(
                property_id="gasteiger_charge",
                name="Partial Charge",
                units="e",
                method="rdkit",
                molecule_uuid="some-other-molecule",
                values={0: 0.1},
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )

    assert all(layer is None for layer in backend.applied_layers)


def test_switching_molecule_resets_color_by_to_default(qapp):
    widget, backend, bus = _make_widget(qapp)
    molecule = _molecule_with_conformer()
    widget.set_molecule(molecule)
    bus.publish(
        PerAtomDataComputed(
            dataset=PerAtomDataset(
                property_id="crippen_logp_contrib",
                name="LogP Contribution",
                units="",
                method="rdkit",
                molecule_uuid=molecule.uuid,
                values={0: -0.5},
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )
    widget._color_by_combo.setCurrentText("LogP contribution")
    assert any(layer is not None for layer in backend.applied_layers)

    other_molecule = _molecule_with_conformer()
    widget.set_molecule(other_molecule)

    assert widget._color_by_combo.currentText() == "Default"
    assert widget._per_atom_datasets == {}


def test_switching_conformer_reapplies_active_visualization(qapp):
    widget, backend, bus = _make_widget(qapp)
    molecule = MoleculeModel(display_name="Test")
    molecule.conformers = [
        ConformerModel(molblock="conf-1", method="rdkit"),
        ConformerModel(molblock="conf-2", method="rdkit"),
    ]
    widget.set_molecule(molecule)
    bus.publish(
        PerAtomDataComputed(
            dataset=PerAtomDataset(
                property_id="crippen_logp_contrib",
                name="LogP Contribution",
                units="",
                method="rdkit",
                molecule_uuid=molecule.uuid,
                values={0: -0.5},
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )
    widget._color_by_combo.setCurrentText("LogP contribution")
    backend.applied_layers.clear()

    widget._show_next_conformer()

    assert backend.loaded_molblocks[-1] == "conf-2"
    real_layers = [layer for layer in backend.applied_layers if layer is not None]
    assert len(real_layers) == 1
