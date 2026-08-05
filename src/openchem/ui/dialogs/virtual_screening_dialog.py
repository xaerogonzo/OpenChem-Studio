"""Dock every ligand in the project into one receptor, and rank them.

The receptor comes from the macromolecules already in the project, and the
search box is derived from the co-crystallised ligand that entry names --
the same `binding_site.box_from_ligand` path the Docking panel uses, on
the same redocking-validated boxes the curated 49-receptor library carries.
A screen against a hand-drawn box would rank ligands by how well they fit
a guess.

THE SCORES ARE A RANKING, NOT AFFINITIES. Vina's kcal/mol are not free
energies and do not convert to a Kd; what they support is "this one before
that one, against this receptor". The dialog says so on its face rather
than in documentation, because a column of numbers headed kcal/mol is read
as a measurement by default.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.common import CacheState
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.services.docking_service import DEFAULT_NUM_POSES
from openchem.services.screening_service import ScreeningProgress, ScreeningService

logger = logging.getLogger("openchem.ui")


class VirtualScreeningDialog(QDialog):
    """Receptor choice, run control, and the ranked result."""

    def __init__(
        self,
        screening_service: ScreeningService,
        event_bus: EventBus,
        project: ProjectModel | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = screening_service
        self._project = project
        self.setWindowTitle("Virtual screening")
        self.resize(720, 560)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Docks every molecule in the project into one receptor, one at a time, "
                "and ranks them.\n"
                "Vina scores rank ligands against ONE receptor; they are not binding "
                "free energies and do not convert to a Kd."
            )
        )

        form = QFormLayout()
        self._receptor = QComboBox(self)
        for macromolecule in (project.macromolecules if project else []):
            self._receptor.addItem(macromolecule.display_name, macromolecule.uuid)
        form.addRow("Receptor", self._receptor)
        self._poses = QSpinBox(self)
        self._poses.setRange(1, 50)
        self._poses.setValue(DEFAULT_NUM_POSES)
        form.addRow("Poses per ligand", self._poses)
        layout.addLayout(form)

        self._ligand_note = QLabel("", self)
        self._ligand_note.setWordWrap(True)
        layout.addWidget(self._ligand_note)

        buttons = QHBoxLayout()
        self._run = QPushButton("Run screen", self)
        self._run.clicked.connect(self._start)
        self._cancel = QPushButton("Cancel", self)
        self._cancel.setEnabled(False)
        self._cancel.clicked.connect(self._service.cancel)
        buttons.addWidget(self._run)
        buttons.addWidget(self._cancel)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._progress = QProgressBar(self)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)
        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._results = QTableWidget(0, 4, self)
        self._results.setHorizontalHeaderLabels(["Rank", "Ligand", "Best score (kcal/mol)", "Poses"])
        self._results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._results, stretch=1)

        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(close)
        layout.addLayout(footer)

        event_bus.subscribe(ScreeningProgress, self._on_progress)
        self._refresh_ligand_note()

    def _refresh_ligand_note(self) -> None:
        ligands = self._ligands()
        if not self._project:
            self._ligand_note.setText("No project open.")
        elif not self._project.macromolecules:
            self._ligand_note.setText(
                "No receptor in this project. Import one, or take a curated target "
                "with a validated binding site from File > Receptor Library."
            )
        else:
            self._ligand_note.setText(f"{len(ligands)} ligands will be docked, in project order.")
        self._run.setEnabled(bool(ligands and self._project and self._project.macromolecules))

    def _ligands(self):
        if self._project is None:
            return []
        return [molecule for molecule in self._project.molecules if molecule.molblock]

    def _start(self) -> None:
        from openchem.chem.binding_site import box_from_ligand

        if self._project is None:
            return
        receptor = self._project.find_macromolecule(self._receptor.currentData())
        if receptor is None:
            self._status.setText("Select a receptor first.")
            return
        ligand_code = receptor.metadata.get("ligand_code", "")
        try:
            site = box_from_ligand(receptor.structure_text, receptor.source_format, ligand_code)
        except Exception as exc:  # noqa: BLE001 - reported, never crashes the dialog
            logger.exception("Could not derive a search box for %s", receptor.display_name)
            self._status.setText(
                f"Could not place a search box on {receptor.display_name}: {exc}\n"
                "A receptor from the curated library carries the ligand code that "
                "defines its site; an imported structure may not."
            )
            return
        # The site's own description is shown before the run rather than
        # after: "3 atoms spanning 2 A" means the code matched an ion and
        # every score from the screen would be meaningless, and that is
        # worth seeing while there is still time not to run it.
        self._status.setText(site.describe())
        self._service.request_screen(
            self._ligands(), receptor, site.box, num_poses=self._poses.value()
        )

    def _on_progress(self, event: ScreeningProgress) -> None:
        running = event.state in (CacheState.QUEUED, CacheState.RUNNING)
        self._run.setEnabled(not running)
        self._cancel.setEnabled(running)
        self._progress.setVisible(running)
        if event.total:
            self._progress.setMaximum(event.total)
            self._progress.setValue(event.completed)
        self._status.setText(event.error or event.message)
        self._render(event.entries)

    def _render(self, entries) -> None:
        self._results.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            # Rank is blank for a failure: numbering a ligand that never
            # produced a score puts it in an ordering it is not part of.
            rank = "" if entry.best_affinity_kcal_mol is None else str(row + 1)
            self._results.setItem(row, 0, QTableWidgetItem(rank))
            self._results.setItem(row, 1, QTableWidgetItem(entry.display_name))
            score = (
                f"{entry.best_affinity_kcal_mol:.2f}"
                if entry.best_affinity_kcal_mol is not None
                else (entry.error or "—")
            )
            item = QTableWidgetItem(score)
            if entry.failed:
                item.setToolTip(entry.error or "")
            self._results.setItem(row, 2, item)
            self._results.setItem(row, 3, QTableWidgetItem(str(entry.pose_count)))

    def results(self):
        """The ranked entries currently shown -- read by tests and by
        anything that wants to feed the scores back into a batch table."""
        return [
            self._results.item(row, 1).text() for row in range(self._results.rowCount())
        ]
