"""Superimpose several of the project's molecules in one 3D frame.

Marvin's 3D Alignment plugin compares two or more structures; the
registry calculator built alongside it can only take one molecule plus a
typed-in reference SMILES, because `CalculatorRegistry.compute` receives
exactly one molecule and no project handle. This panel is where the
multi-molecule case lives, for the same reason docking has its own panel.

The result is shown in an embedded 3D view rather than the structure
GRID the other `StructureSetResult` calculators use: a grid of 2D
depictions cannot show a superposition, which is the entire output here.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.alignment import EnsembleEntry
from openchem.domain.common import CacheState
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import AlignmentJobStateChanged, EnsembleAlignmentReady
from openchem.services.alignment_service import AlignmentService
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend

_RESULT_COLUMNS = ("Molecule", "Score", "RMSD (A)", "Paired atoms")

# Deliberately not a gradient: these identify structures, so neighbouring
# entries have to be told apart at a glance. Colour-blind-safe ordering
# (Okabe-Ito), with the reference's grey first so it reads as the fixed
# frame everything else was moved onto.
_ENSEMBLE_COLORS = (
    "#888888",
    "#0072b2",
    "#d55e00",
    "#009e73",
    "#cc79a7",
    "#e69f00",
    "#56b4e9",
    "#f0e442",
)

_METHOD_NOTE = (
    "Extended atom types pairs atoms by MMFF type (Open3DAlign). Common scaffold fixes the "
    "pairing from the 2D maximum common substructure first, then refines everything else "
    "around it. Score is an overlap quality where HIGHER is better; RMSD is a distance in "
    "angstroms where LOWER is better -- they are not the same measure."
)


class AlignmentPanel(QWidget):
    """Pick a reference and any number of molecules to align onto it."""

    def __init__(
        self,
        alignment_service: AlignmentService,
        event_bus: EventBus,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._alignment_service = alignment_service
        self._event_bus = event_bus
        self._project: ProjectModel | None = None
        self._entries: list[EnsembleEntry] = []

        self._reference_combo = QComboBox(self)
        self._reference_combo.currentIndexChanged.connect(self._on_reference_changed)

        self._probe_list = QListWidget(self)
        self._probe_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._probe_list.setMaximumHeight(140)

        self._method_combo = QComboBox(self)
        from openchem.chem.alignment import ACCURACY_LEVELS, ALIGNMENT_METHODS

        self._method_combo.addItems(list(ALIGNMENT_METHODS))
        self._accuracy_combo = QComboBox(self)
        self._accuracy_combo.addItems(list(ACCURACY_LEVELS))
        self._accuracy_combo.setCurrentText("Normal")

        self._align_button = QPushButton("Align", self)
        self._align_button.clicked.connect(self._on_align_clicked)
        self._status_label = QLabel("", self)
        self._status_label.setWordWrap(True)

        self._result_table = QTableWidget(0, len(_RESULT_COLUMNS), self)
        self._result_table.setHorizontalHeaderLabels(_RESULT_COLUMNS)
        self._result_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._result_table.setMaximumHeight(160)

        self._viewer = Mol3DViewerBackend(self)
        self._style_combo = QComboBox(self)
        self._style_combo.addItems(["stick", "ballstick", "sphere", "line"])
        self._style_combo.currentTextChanged.connect(self._viewer.set_style)

        note = QLabel(_METHOD_NOTE, self)
        note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Reference:", self._reference_combo)
        form.addRow("Align onto it:", self._probe_list)
        form.addRow("Method:", self._method_combo)
        form.addRow("Accuracy:", self._accuracy_combo)

        settings_box = QGroupBox("Alignment", self)
        settings_layout = QVBoxLayout(settings_box)
        settings_layout.addLayout(form)
        settings_layout.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addWidget(self._align_button)
        buttons.addStretch(1)
        settings_layout.addLayout(buttons)
        settings_layout.addWidget(self._status_label)

        view_header = QHBoxLayout()
        view_header.addWidget(QLabel("Style:", self))
        view_header.addWidget(self._style_combo)
        view_header.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(settings_box)
        layout.addWidget(self._result_table)
        layout.addLayout(view_header)
        layout.addWidget(self._viewer.widget(), 1)

        event_bus.subscribe(AlignmentJobStateChanged, self._on_job_state_changed)
        event_bus.subscribe(EnsembleAlignmentReady, self._on_alignment_ready)

    # --- project wiring ---------------------------------------------------

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        molecules = list(project.molecules) if project is not None else []

        previous = self._reference_combo.currentData()
        self._reference_combo.blockSignals(True)
        self._reference_combo.clear()
        for molecule in molecules:
            self._reference_combo.addItem(molecule.display_name, molecule.uuid)
        if previous is not None:
            restored = self._reference_combo.findData(previous)
            if restored >= 0:
                self._reference_combo.setCurrentIndex(restored)
        self._reference_combo.blockSignals(False)
        self._rebuild_probe_list()

    def _rebuild_probe_list(self) -> None:
        """Everything except the reference, each with a checkbox.

        Checked state is preserved across rebuilds by uuid -- `set_project`
        is called on every project mutation (see MainWindow's
        `_refresh_project_panels`), and silently clearing the user's
        selection because an unrelated molecule was renamed would be its
        own bug.
        """
        checked = {
            self._probe_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self._probe_list.count())
            if self._probe_list.item(row).checkState() == Qt.CheckState.Checked
        }
        reference_uuid = self._reference_combo.currentData()
        self._probe_list.clear()
        molecules = list(self._project.molecules) if self._project is not None else []
        for molecule in molecules:
            if molecule.uuid == reference_uuid:
                continue
            item = QListWidgetItem(molecule.display_name)
            item.setData(Qt.ItemDataRole.UserRole, molecule.uuid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if molecule.uuid in checked else Qt.CheckState.Unchecked
            )
            self._probe_list.addItem(item)

    def _on_reference_changed(self) -> None:
        self._rebuild_probe_list()

    # --- running ----------------------------------------------------------

    def _checked_uuids(self) -> list[str]:
        return [
            self._probe_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self._probe_list.count())
            if self._probe_list.item(row).checkState() == Qt.CheckState.Checked
        ]

    def _on_align_clicked(self) -> None:
        if self._project is None:
            return
        reference_uuid = self._reference_combo.currentData()
        by_uuid = {molecule.uuid: molecule for molecule in self._project.molecules}
        reference = by_uuid.get(reference_uuid)
        if reference is None:
            self._status_label.setText("Pick a reference molecule first.")
            return
        probes = [by_uuid[uuid] for uuid in self._checked_uuids() if uuid in by_uuid]
        if not probes:
            self._status_label.setText("Tick at least one molecule to align onto the reference.")
            return

        from openchem.chem.alignment import ALIGNMENT_METHODS

        self._alignment_service.request_alignment(
            reference,
            probes,
            method=ALIGNMENT_METHODS[self._method_combo.currentText()],
            accuracy=self._accuracy_combo.currentText(),
        )

    def _on_job_state_changed(self, event: AlignmentJobStateChanged) -> None:
        running = event.state in (CacheState.QUEUED, CacheState.RUNNING)
        self._align_button.setEnabled(not running)
        self._status_label.setText(event.message or event.state.value)

    def _on_alignment_ready(self, event: EnsembleAlignmentReady) -> None:
        self._entries = event.entries
        # Assigned ONCE and handed to both consumers. A failed entry gets
        # no colour and no model, so the table's row index and the
        # viewer's model index do not line up -- deriving the colour
        # separately in each place is how they would silently disagree
        # about which structure is which, which is the one thing an
        # overlay must not get wrong.
        colors: dict[int, str] = {}
        for position, index in enumerate(
            i for i, entry in enumerate(event.entries) if entry.aligned and entry.molblock
        ):
            colors[index] = _ENSEMBLE_COLORS[position % len(_ENSEMBLE_COLORS)]
        self._populate_table(event.entries, colors)
        self._show_ensemble(event.entries, colors)

    def _populate_table(self, entries: list[EnsembleEntry], colors: dict[int, str]) -> None:
        self._result_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            name = QTableWidgetItem(entry.label)
            if row in colors:
                name.setForeground(QColor(colors[row]))
            self._result_table.setItem(row, 0, name)
            if not entry.aligned:
                # The reason spans the numeric columns -- a failed entry
                # has no score or RMSD, and blank cells would read as
                # zeros rather than as "this one did not align".
                reason = QTableWidgetItem(entry.error or "Alignment failed")
                self._result_table.setItem(row, 1, reason)
                self._result_table.setSpan(row, 1, 1, len(_RESULT_COLUMNS) - 1)
                continue
            self._result_table.setSpan(row, 1, 1, 1)
            if entry.score is None:
                # The reference itself: it defines the frame, so it has no
                # score against anything.
                for column in range(1, len(_RESULT_COLUMNS)):
                    self._result_table.setItem(row, column, QTableWidgetItem("-"))
                continue
            self._result_table.setItem(row, 1, QTableWidgetItem(f"{entry.score:.2f}"))
            self._result_table.setItem(
                row, 2, QTableWidgetItem("-" if entry.rmsd is None else f"{entry.rmsd:.3f}")
            )
            self._result_table.setItem(row, 3, QTableWidgetItem(str(entry.matched_atoms)))

    def _show_ensemble(self, entries: list[EnsembleEntry], colors: dict[int, str]) -> None:
        self._viewer.load_ensemble(
            [(entries[index].molblock, color) for index, color in sorted(colors.items())]
        )
