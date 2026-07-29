from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.engine import ChemistryEngine
from openchem.domain.docking import DockingBox
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import DockingJobStateChanged, DockingResultReady
from openchem.services.docking_service import DockingService

_POSE_COLUMNS = ("Pose", "Binding Affinity (kcal/mol)", "RMSD l.b.", "RMSD u.b.")

_LIMITATION_NOTE = (
    "Note: receptor/ligand preparation uses Open Babel's default hydrogen "
    "addition only — no protonation-state assignment, water/cofactor "
    "handling, or missing-residue repair. Treat results as a starting "
    "point, not production-grade docking prep."
)


class DockingPanel(QWidget):
    """Pick a receptor (macromolecule) + ligand (molecule) from the current
    project, define a search box, and run AutoDock Vina via whichever
    `VinaEngine` is available (chem/vina_engine.py) — the panel itself
    doesn't know or care which one.
    """

    def __init__(
        self,
        docking_service: DockingService,
        chemistry_engine: ChemistryEngine,
        event_bus: EventBus,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._docking_service = docking_service
        self._chemistry_engine = chemistry_engine
        self._event_bus = event_bus
        self._project: ProjectModel | None = None
        self._pending_ligand_uuid: str | None = None
        self._pending_receptor_uuid: str | None = None

        self._receptor_combo = QComboBox(self)
        self._ligand_combo = QComboBox(self)

        self._center_x = self._make_spin(-1000, 1000, 0.0)
        self._center_y = self._make_spin(-1000, 1000, 0.0)
        self._center_z = self._make_spin(-1000, 1000, 0.0)
        self._size_x = self._make_spin(1, 200, 20.0)
        self._size_y = self._make_spin(1, 200, 20.0)
        self._size_z = self._make_spin(1, 200, 20.0)

        self._num_poses_spin = QSpinBox(self)
        self._num_poses_spin.setRange(1, 50)
        self._num_poses_spin.setValue(9)

        self._dock_button = QPushButton("Dock", self)
        self._dock_button.clicked.connect(self._on_dock_clicked)

        self._status_label = QLabel("", self)
        self._limitation_label = QLabel(_LIMITATION_NOTE, self)
        self._limitation_label.setWordWrap(True)

        self._table = QTableWidget(0, len(_POSE_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_POSE_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        selection_form = QFormLayout()
        selection_form.addRow("Receptor:", self._receptor_combo)
        selection_form.addRow("Ligand:", self._ligand_combo)

        box_group = QGroupBox("Search box (Å)", self)
        box_form = QFormLayout(box_group)
        center_row = QHBoxLayout()
        center_row.addWidget(self._center_x)
        center_row.addWidget(self._center_y)
        center_row.addWidget(self._center_z)
        size_row = QHBoxLayout()
        size_row.addWidget(self._size_x)
        size_row.addWidget(self._size_y)
        size_row.addWidget(self._size_z)
        box_form.addRow("Center (x, y, z):", center_row)
        box_form.addRow("Size (x, y, z):", size_row)

        run_row = QHBoxLayout()
        run_row.addWidget(QLabel("Poses:"))
        run_row.addWidget(self._num_poses_spin)
        run_row.addWidget(self._dock_button)

        layout = QVBoxLayout(self)
        layout.addLayout(selection_form)
        layout.addWidget(box_group)
        layout.addLayout(run_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._table)
        layout.addWidget(self._limitation_label)

        event_bus.subscribe(DockingJobStateChanged, self._on_job_state_changed)
        event_bus.subscribe(DockingResultReady, self._on_result_ready)

    def _make_spin(self, minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self._refresh_combos()

    def _refresh_combos(self) -> None:
        self._receptor_combo.clear()
        self._ligand_combo.clear()
        if self._project is None:
            return
        for macromolecule in self._project.macromolecules:
            self._receptor_combo.addItem(macromolecule.display_name, macromolecule.uuid)
        for molecule in self._project.molecules:
            self._ligand_combo.addItem(molecule.display_name, molecule.uuid)

    def _on_dock_clicked(self) -> None:
        if self._project is None:
            return
        receptor_uuid = self._receptor_combo.currentData()
        ligand_uuid = self._ligand_combo.currentData()
        if receptor_uuid is None or ligand_uuid is None:
            self._status_label.setText("Select both a receptor and a ligand first.")
            return
        receptor = self._project.find_macromolecule(receptor_uuid)
        ligand = self._project.find_molecule(ligand_uuid)
        if receptor is None or ligand is None:
            return

        box = DockingBox(
            center=(self._center_x.value(), self._center_y.value(), self._center_z.value()),
            size=(self._size_x.value(), self._size_y.value(), self._size_z.value()),
        )
        ligand_mol = self._chemistry_engine.mol_from_model(ligand)

        self._pending_ligand_uuid = ligand_uuid
        self._pending_receptor_uuid = receptor_uuid
        self._dock_button.setEnabled(False)
        self._table.setRowCount(0)
        self._status_label.setText("Queued...")

        self._docking_service.request_docking(
            ligand_molecule_uuid=ligand_uuid,
            ligand_mol=ligand_mol,
            receptor_macromolecule_uuid=receptor_uuid,
            receptor_structure_text=receptor.structure_text,
            receptor_source_format=receptor.source_format,
            box=box,
            num_poses=self._num_poses_spin.value(),
        )

    def _is_pending(self, ligand_molecule_uuid: str, receptor_macromolecule_uuid: str) -> bool:
        return (
            ligand_molecule_uuid == self._pending_ligand_uuid
            and receptor_macromolecule_uuid == self._pending_receptor_uuid
        )

    def _on_job_state_changed(self, event: DockingJobStateChanged) -> None:
        if not self._is_pending(event.ligand_molecule_uuid, event.receptor_macromolecule_uuid):
            return
        self._status_label.setText(f"{event.state.value}{': ' + event.message if event.message else ''}")
        if event.state.value in ("completed", "failed"):
            self._dock_button.setEnabled(True)

    def _on_result_ready(self, event: DockingResultReady) -> None:
        result = event.result
        if not self._is_pending(result.ligand_molecule_uuid, result.receptor_macromolecule_uuid):
            return
        self._table.setRowCount(len(result.poses))
        for row, pose in enumerate(result.poses):
            values = (
                str(row + 1),
                f"{pose.binding_affinity_kcal_mol:.2f}",
                f"{pose.rmsd_lb:.3f}",
                f"{pose.rmsd_ub:.3f}",
            )
            for col, value in enumerate(values):
                self._table.setItem(row, col, QTableWidgetItem(value))
