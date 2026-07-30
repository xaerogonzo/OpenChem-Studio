from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformerJobStateChanged, ConformersChanged
from openchem.services.conformer_service import ConformerService
from openchem.services.measurement_service import MeasurementService
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend


class MoleculeViewer3DWidget(QWidget):
    """Hosts a ViewerBackend (3Dmol.js today) for the active molecule's
    conformers, plus a small toolbar for style/navigation/generation and a
    click-two-atoms distance measurement readout.

    Never touches RDKit directly: generation goes through ConformerService;
    turning the result into a persisted, undoable change is MainWindow's
    job via SetConformersCommand — this widget only calls the service and
    reacts to events, matching how the other panels stay thin.
    """

    def __init__(
        self,
        conformer_service: ConformerService,
        measurement_service: MeasurementService,
        event_bus: EventBus,
        backend: ViewerBackend | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conformer_service = conformer_service
        self._measurement_service = measurement_service
        self._molecule: MoleculeModel | None = None
        self._conformer_index = 0
        self._selected_atoms: list[int] = []

        self._backend: ViewerBackend = backend or Mol3DViewerBackend(self)
        self._backend.atoms_selected.connect(self._on_atoms_selected)

        self._style_combo = QComboBox(self)
        self._style_combo.addItems(["stick", "ballstick", "sphere", "line"])
        self._style_combo.currentTextChanged.connect(self._backend.set_style)

        self._generate_button = QPushButton("Generate Conformers...", self)
        self._generate_button.clicked.connect(self._on_generate_clicked)

        self._prev_button = QPushButton("<", self)
        self._prev_button.clicked.connect(self._show_previous_conformer)
        self._next_button = QPushButton(">", self)
        self._next_button.clicked.connect(self._show_next_conformer)
        self._status_label = QLabel("No conformers", self)
        self._measurement_label = QLabel("", self)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Style:"))
        toolbar.addWidget(self._style_combo)
        toolbar.addWidget(self._generate_button)
        toolbar.addStretch()
        toolbar.addWidget(self._prev_button)
        toolbar.addWidget(self._status_label)
        toolbar.addWidget(self._next_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(self._backend.widget())
        layout.addWidget(self._measurement_label)

        event_bus.subscribe(ConformersChanged, self._on_conformers_changed)
        event_bus.subscribe(ConformerJobStateChanged, self._on_job_state_changed)

    def set_molecule(self, molecule: MoleculeModel | None) -> None:
        self._molecule = molecule
        self._conformer_index = 0
        self._selected_atoms.clear()
        self._measurement_label.setText("")
        self._refresh_view()

    def _on_generate_clicked(self) -> None:
        if self._molecule is None:
            return
        count, ok = QInputDialog.getInt(
            self, "Generate Conformers", "Number of conformers:", 10, 1, 200
        )
        if not ok:
            return
        self._conformer_service.request_conformers(self._molecule, count, optimize=True)

    def _on_conformers_changed(self, event: ConformersChanged) -> None:
        if self._molecule is not None and event.molecule_uuid == self._molecule.uuid:
            self._conformer_index = 0
            self._refresh_view()

    def _on_job_state_changed(self, event: ConformerJobStateChanged) -> None:
        if self._molecule is None or event.molecule_uuid != self._molecule.uuid:
            return
        if event.state == CacheState.RUNNING:
            self._status_label.setText(event.message or "Generating...")
        elif event.state == CacheState.FAILED:
            self._status_label.setText(f"Failed: {event.message}")

    def _show_previous_conformer(self) -> None:
        if self._molecule and self._conformer_index > 0:
            self._conformer_index -= 1
            self._refresh_view()

    def _show_next_conformer(self) -> None:
        if self._molecule and self._conformer_index < len(self._molecule.conformers) - 1:
            self._conformer_index += 1
            self._refresh_view()

    def _on_atoms_selected(self, indices: list[int]) -> None:
        if self._molecule is None or not self._molecule.conformers:
            return
        self._selected_atoms.extend(indices)
        if len(self._selected_atoms) < 2:
            return
        atom_1, atom_2 = self._selected_atoms[-2], self._selected_atoms[-1]
        self._selected_atoms.clear()
        conformer = self._molecule.conformers[self._conformer_index]
        try:
            distance = self._measurement_service.bond_length(conformer.molblock, atom_1, atom_2)
        except Exception:  # noqa: BLE001 - a bad atom index pair should not crash the widget
            self._measurement_label.setText(f"Could not measure atoms {atom_1}-{atom_2}")
            return
        self._measurement_label.setText(f"Distance atoms {atom_1}-{atom_2}: {distance:.3f} Å")

    def _refresh_view(self) -> None:
        if self._molecule is None or not self._molecule.conformers:
            self._backend.clear()
            self._status_label.setText("No conformers")
            return
        conformer = self._molecule.conformers[self._conformer_index]
        self._backend.load_conformer(conformer.molblock)
        energy_text = f"{conformer.energy:.2f} kcal/mol" if conformer.energy is not None else "n/a"
        self._status_label.setText(
            f"Conformer {self._conformer_index + 1}/{len(self._molecule.conformers)} - {energy_text}"
        )
