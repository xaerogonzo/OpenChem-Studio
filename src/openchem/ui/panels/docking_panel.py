from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
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

import logging

from openchem.chem.calculation_input import canonical_conformer
from openchem.app.settings import Settings
from openchem.chem.engine import ChemistryEngine
from openchem.domain.docking import DockingBox
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import DockingJobStateChanged, DockingResultReady, MoleculeSelected
from openchem.services.docking_service import DockingService
from openchem.ui.dialogs.external_tools_dialog import ExternalToolsDialog
from openchem.ui.molecule_combo import repopulate, select

logger = logging.getLogger("openchem.ui")

_POSE_COLUMNS = ("Pose", "Binding Affinity (kcal/mol)", "RMSD l.b.", "RMSD u.b.")

_LIMITATION_NOTE = (
    "Note: receptor preparation handles pH-correct protonation and "
    "water/cofactor stripping (below), via Open Babel. Missing-residue "
    "repair is still not handled — treat results as a starting point, not "
    "production-grade docking prep."
)


def _box_defining_ligand_codes(receptor) -> list[str]:
    """The co-crystallised ligand that defined this receptor's search box.

    A catalogue import records it in `MacromoleculeModel.metadata`
    (`receptor_library_service.entry_metadata`), and the box is derived
    from its coordinates. Leaving it in the pocket it defined means docking
    into an occupied site: measured against real Vina on 1HSG, indinavir
    redocked into its own structure scored -5.34 kcal/mol with the ligand
    present and -9.75 with it removed, and the occupied run was SLOWER.

    Returns empty for a receptor the user imported themselves -- there is
    no catalogue entry, so nothing here knows which residue defined the
    box, and guessing would delete part of somebody's receptor.
    """
    metadata = getattr(receptor, "metadata", None) or {}
    code = str(metadata.get("ligand_code", "") or "").strip()
    return [code] if code else []


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
        settings: Settings,
        event_bus: EventBus,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._docking_service = docking_service
        self._chemistry_engine = chemistry_engine
        self._settings = settings
        self._event_bus = event_bus
        self._project: ProjectModel | None = None
        self._pending_ligand_uuid: str | None = None
        self._pending_receptor_uuid: str | None = None
        #: Which docking result the pose table is showing, so an undo
        #: that removes it can be told apart from a redo that restores it.
        self._displayed_result_uuid: str | None = None

        self._receptor_combo = QComboBox(self)
        # Parsing a receptor is not free (Open Babel reads the whole file),
        # so the summary is computed on demand from the button rather than
        # on every combo change.
        self._contents_button = QPushButton("Contents...", self)
        self._contents_button.setToolTip(
            "List the chains, ligands and waters in the selected receptor"
        )
        self._contents_button.clicked.connect(self._on_contents_clicked)
        # Empty means "no restriction", never "no chains" -- see
        # StructureContentsDialog.keep_chains. Reset whenever the receptor
        # changes, because a chain id names a different thing in a
        # different structure and carrying "keep A" across would silently
        # dock against the wrong subunit.
        self._keep_chains: list[str] = []
        self._receptor_combo.currentIndexChanged.connect(self._on_receptor_changed)
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

        self._ph_spin = QDoubleSpinBox(self)
        self._ph_spin.setRange(0.0, 14.0)
        self._ph_spin.setSingleStep(0.1)
        self._ph_spin.setValue(7.4)
        self._strip_waters_check = QCheckBox("Strip waters", self)
        self._strip_waters_check.setChecked(True)
        self._strip_cofactors_check = QCheckBox("Strip cofactors", self)
        self._strip_cofactors_check.setChecked(False)

        self._configure_button = QPushButton("Configure Vina...", self)
        self._configure_button.clicked.connect(self._on_configure_clicked)

        self._dock_button = QPushButton("Dock", self)
        self._dock_button.clicked.connect(self._on_dock_clicked)

        self._status_label = QLabel("", self)
        self._limitation_label = QLabel(_LIMITATION_NOTE, self)
        self._limitation_label.setWordWrap(True)

        self._table = QTableWidget(0, len(_POSE_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_POSE_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        receptor_row = QHBoxLayout()
        receptor_row.addWidget(self._receptor_combo, 1)
        receptor_row.addWidget(self._contents_button)

        selection_form = QFormLayout()
        selection_form.addRow("Receptor:", receptor_row)
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

        prep_group = QGroupBox("Receptor preparation", self)
        prep_form = QFormLayout(prep_group)
        prep_form.addRow("Protonation pH:", self._ph_spin)
        strip_row = QHBoxLayout()
        strip_row.addWidget(self._strip_waters_check)
        strip_row.addWidget(self._strip_cofactors_check)
        prep_form.addRow("", strip_row)

        run_row = QHBoxLayout()
        run_row.addWidget(QLabel("Poses:"))
        run_row.addWidget(self._num_poses_spin)
        run_row.addWidget(self._configure_button)
        run_row.addWidget(self._dock_button)

        layout = QVBoxLayout(self)
        layout.addLayout(selection_form)
        layout.addWidget(box_group)
        layout.addWidget(prep_group)
        layout.addLayout(run_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._table)
        layout.addWidget(self._limitation_label)

        event_bus.subscribe(DockingJobStateChanged, self._on_job_state_changed)
        event_bus.subscribe(DockingResultReady, self._on_result_ready)
        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)

    def _make_spin(self, minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self._refresh_combos()

    def _refresh_combos(self) -> None:
        macromolecules = self._project.macromolecules if self._project is not None else []
        molecules = self._project.molecules if self._project is not None else []
        repopulate(self._receptor_combo, [(m.display_name, m.uuid) for m in macromolecules])
        repopulate(self._ligand_combo, [(m.display_name, m.uuid) for m in molecules])

    def _on_molecule_selected(self, event: MoleculeSelected) -> None:
        """Follow the project tree for the LIGAND only.

        The receptor combo lists macromolecules and is deliberately left
        alone: a `MoleculeSelected` uuid is never in it, and blanking a
        chosen receptor because the user clicked a small molecule would
        throw away the search box that goes with it.
        """
        select(self._ligand_combo, event.molecule_uuid)

    def _on_contents_clicked(self) -> None:
        """Summarise the selected receptor and show its chains.

        Parsed here rather than cached on the model: the summary is a view
        of the structure text, and caching it would give the model a
        second copy of the truth that could go stale the moment the text
        was replaced.
        """
        from openchem.chem.structure_assembly import parse_assembly
        from openchem.chem.structure_summary import summarize_structure
        from openchem.ui.dialogs.structure_contents_dialog import StructureContentsDialog

        if self._project is None:
            return
        receptor_uuid = self._receptor_combo.currentData()
        receptor = (
            self._project.find_macromolecule(receptor_uuid) if receptor_uuid else None
        )
        if receptor is None:
            self._status_label.setText("Select a receptor first.")
            return
        try:
            summary = summarize_structure(receptor.structure_text, receptor.source_format)
        except Exception as exc:  # noqa: BLE001 - surfaced, never a crash
            logger.exception("Failed to summarise receptor")
            self._status_label.setText(f"Could not read that receptor: {exc}")
            return
        dialog = StructureContentsDialog(
            receptor.display_name,
            summary,
            self,
            keep_chains=self._keep_chains or None,
            # Parsed from the SAME text the chains came from -- mmCIF
            # assembly records name label_asym_ids and PDB REMARK 350
            # names author ids, so crossing the two formats would annotate
            # chains that do not exist under those names.
            assembly=parse_assembly(receptor.structure_text, receptor.source_format),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._keep_chains = dialog.keep_chains()
        self._update_chain_status()

    def _on_receptor_changed(self, _index: int) -> None:
        self._keep_chains = []
        self._update_chain_status()

    def _update_chain_status(self) -> None:
        """Say so on the panel when the receptor is being cut down.

        A restriction chosen in a dialog that is then closed is invisible,
        and this one changes what Vina sees -- the user should not have to
        reopen the dialog to find out whether it is in effect.
        """
        if self._keep_chains:
            self._status_label.setText(
                f"Docking against chain(s) {', '.join(self._keep_chains)} only."
            )
        elif self._status_label.text().startswith("Docking against chain"):
            self._status_label.setText("")

    def _on_configure_clicked(self) -> None:
        dialog = ExternalToolsDialog(self._settings, self, focus="vina")
        dialog.exec()

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
        if not ligand.conformers and not ligand.molblock:
            self._status_label.setText("Selected ligand has no structure yet.")
            return

        box = DockingBox(
            center=(self._center_x.value(), self._center_y.value(), self._center_z.value()),
            size=(self._size_x.value(), self._size_y.value(), self._size_z.value()),
        )
        # Prefer a real 3D conformer over the molecule's own molblock, which
        # for anything drawn in the 2D editor has all-zero z-coordinates --
        # docking a flat structure against a 3D receptor is meaningless, not
        # just lower quality. Mirrors QuantumChemistryPanel._on_run_clicked's
        # identical preference.
        best = canonical_conformer(ligand)
        ligand_molblock = best.molblock if best is not None else ligand.molblock
        ligand_mol = self._chemistry_engine.mol_from_molblock(ligand_molblock)

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
            receptor_prep_options={
                "ph": self._ph_spin.value(),
                "strip_waters": self._strip_waters_check.isChecked(),
                "strip_cofactors": self._strip_cofactors_check.isChecked(),
                # Travels in the SAME dict the service hands to both the
                # receptor preparation and the interaction analysis, so
                # they cannot be given different receptors.
                "keep_chains": list(self._keep_chains),
                "strip_ligand_codes": _box_defining_ligand_codes(receptor),
            },
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

    def sync_with_project(self, project: ProjectModel | None) -> None:
        """Make the pose table agree with the project's docking results.

        The table was filled from the `DockingResultReady` event and never
        read back from the project, so it only ever reflected what had just
        finished. Undoing a dock removed the result and left the poses on
        screen -- binding affinities, to two decimal places, for a run the
        project no longer contains. Measured: two rows still listed after
        the undo that emptied `project.docking_results`.

        Symmetric on purpose. Clearing on undo without restoring on redo
        would trade one wrong state for another, so this resolves the table
        from the project every time: the newest result for the currently
        selected receptor/ligand pair, or nothing.
        """
        self._table.setRowCount(0)
        self._displayed_result_uuid = None
        result = self._latest_result_for_selection(project)
        if result is not None:
            self._show_result(result)

    def _latest_result_for_selection(self, project: ProjectModel | None):
        if project is None:
            return None
        receptor_uuid = self._receptor_combo.currentData()
        ligand_uuid = self._ligand_combo.currentData()
        matching = [
            result
            for result in project.docking_results
            if result.receptor_macromolecule_uuid == receptor_uuid
            and result.ligand_molecule_uuid == ligand_uuid
        ]
        # Newest wins: re-docking the same pair should show the run just
        # made, not the first one ever made.
        return max(matching, key=lambda r: r.timestamp) if matching else None

    def _show_result(self, result) -> None:
        self._displayed_result_uuid = result.uuid
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

    def _on_result_ready(self, event: DockingResultReady) -> None:
        result = event.result
        if not self._is_pending(result.ligand_molecule_uuid, result.receptor_macromolecule_uuid):
            return
        self._show_result(result)
