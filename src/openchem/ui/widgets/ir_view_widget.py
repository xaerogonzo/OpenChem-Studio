from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.engine import ChemistryEngine
from openchem.chem.mode_animation import normal_mode_frames
from openchem.domain.scientific_result import VibrationalSpectrumResult
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.widgets.ir_spectrum_widget import IrSpectrumWidget
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend

_TABLE_COLUMNS = ("Wavenumber (cm⁻¹)", "IR intensity (km/mol)", "Character")

#: Milliseconds between animation frames. 20 frames at 60 ms is a 1.2 s
#: cycle -- slow enough to follow an individual atom, which is the point,
#: and deliberately unrelated to the mode's real femtosecond period. A
#: real C-H stretch takes about 11 fs; played at any true rate every mode
#: would be an indistinguishable blur.
_FRAME_INTERVAL_MS = 60

_WARNING_STYLE = "color: #c82828; font-weight: bold;"


class IrViewWidget(QWidget):
    """The IR counterpart of `NmrViewWidget`: stick spectrum, mode table,
    and a 3D pane that animates the selected normal mode.

    Same structure as the NMR view on purpose -- spectrum above, table
    below, 3D beside, and every selection resolving to the same object
    from whichever side it was made -- so a chemist who has used one can
    read the other. What differs is what a selection MEANS: an NMR peak
    owns a set of atoms, while a normal mode owns the whole molecule and
    a direction of motion, which is why selecting one here starts an
    animation rather than highlighting atoms.

    THE IMAGINARY WARNING IS THE MOST IMPORTANT THING THIS WIDGET DRAWS.
    A negative wavenumber means the geometry is a saddle point, and the
    consequence is not confined to the spectrum: every thermochemistry
    number from the SAME job -- the enthalpy, the entropy, the free
    energy the user probably ran the job for -- is computed from a
    harmonic partition function that assumes a minimum, and is therefore
    meaningless with nothing in the numbers themselves to say so. It is
    shown here in red, above the spectrum, and repeated inside the plot.
    """

    def __init__(
        self,
        engine: ChemistryEngine,
        backend: ViewerBackend | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._spectrum: VibrationalSpectrumResult | None = None
        self._conformer_molblock: str = ""
        self._frames: list[str] = []
        self._frame_index = 0
        self._animating_mode: int | None = None

        self._header_label = QLabel("", self)
        self._header_label.setWordWrap(True)

        self._warning_label = QLabel("", self)
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet(_WARNING_STYLE)
        self._warning_label.setVisible(False)

        self._backend: ViewerBackend = backend or Mol3DViewerBackend(self)

        self._spectrum_widget = IrSpectrumWidget(parent=self)
        self._spectrum_widget.mode_clicked.connect(self._on_peak_clicked)

        self._table = QTableWidget(0, len(_TABLE_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_TABLE_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)

        self._animate_button = QPushButton("Animate mode", self)
        self._animate_button.setCheckable(True)
        self._animate_button.setEnabled(False)
        self._animate_button.toggled.connect(self._on_animate_toggled)

        # Parented to self, so it is destroyed with the widget rather than
        # firing into a deleted backend.
        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_INTERVAL_MS)
        self._timer.timeout.connect(self._advance_frame)

        controls = QHBoxLayout()
        controls.addWidget(self._animate_button)
        controls.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self._header_label)
        layout.addWidget(self._warning_label)
        layout.addWidget(self._backend.widget())
        layout.addWidget(self._spectrum_widget)
        layout.addLayout(controls)
        layout.addWidget(self._table)

    # -- population ------------------------------------------------------

    def set_spectrum(
        self, spectrum: VibrationalSpectrumResult, conformer_molblock: str = ""
    ) -> None:
        """`conformer_molblock` must be the OPTIMISED geometry.

        An `opt_freq` job optimises before computing frequencies, so the
        modes describe motion about the optimised structure. Animating
        them about the submitted one shows the right displacements around
        the wrong molecule -- the same trap that made mode CLASSIFICATION
        label both of linear water's O-H stretches "bend".
        """
        self.stop()
        self._spectrum = spectrum
        self._conformer_molblock = conformer_molblock

        scaling = ""
        if spectrum.scaling_factor != 1.0:
            scaling = f", scaled by {spectrum.scaling_factor:g}"
        self._header_label.setText(
            f"{spectrum.name} — harmonic frequencies, {spectrum.method}{scaling}"
        )

        self._warning_label.setText(spectrum.imaginary_warning)
        self._warning_label.setVisible(bool(spectrum.imaginary_warning))

        self._spectrum_widget.set_modes(spectrum.modes, spectrum.imaginary_warning)
        self._populate_table(spectrum)

        if conformer_molblock:
            self._backend.load_conformer(conformer_molblock)
        self._animate_button.setEnabled(bool(conformer_molblock) and bool(spectrum.modes))

    def _populate_table(self, spectrum: VibrationalSpectrumResult) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(len(spectrum.modes))
        for row, mode in enumerate(spectrum.modes):
            # Imaginary modes ARE listed, unlike in the plot. A table is a
            # record of what the calculation found; leaving them out would
            # make the row count disagree with the mode numbering ORCA
            # itself printed.
            wavenumber = f"{mode.wavenumber_cm1:.1f}"
            if mode.is_imaginary:
                wavenumber += "  (imaginary)"
            intensity = (
                "—"
                if mode.ir_intensity_km_mol is None
                else f"{mode.ir_intensity_km_mol:.2f}"
            )
            for column, text in enumerate((wavenumber, intensity, mode.character or "—")):
                item = QTableWidgetItem(text)
                if mode.is_imaginary:
                    item.setForeground(Qt.GlobalColor.red)
                self._table.setItem(row, column, item)
        self._table.blockSignals(False)

    # -- selection -------------------------------------------------------

    def selected_mode(self) -> int | None:
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        return rows[0].row() if rows else None

    def _on_peak_clicked(self, mode_index: int) -> None:
        self._table.selectRow(mode_index)

    def _on_table_selection_changed(self) -> None:
        index = self.selected_mode()
        if index is None:
            return
        self._spectrum_widget.set_highlighted_modes([index])
        if self._animate_button.isChecked():
            # Switching modes mid-playback restarts on the new one rather
            # than continuing the old animation under a new label.
            self._start_animation(index)

    # -- animation -------------------------------------------------------

    def _on_animate_toggled(self, checked: bool) -> None:
        if not checked:
            self.stop()
            return
        index = self.selected_mode()
        if index is None:
            index = 0
            self._table.selectRow(0)
        self._start_animation(index)

    def _start_animation(self, mode_index: int) -> None:
        if self._spectrum is None or not self._conformer_molblock:
            return
        if not 0 <= mode_index < len(self._spectrum.modes):
            return
        mode = self._spectrum.modes[mode_index]
        if not mode.displacements:
            self._frames = []
            self.stop()
            return
        mol = self._engine.mol_from_molblock(self._conformer_molblock)
        try:
            self._frames = normal_mode_frames(mol, mode.displacements)
        except ValueError:
            # A mismatch between the conformer and the modes describes two
            # different molecules; refusing to animate is better than
            # animating the wrong atoms.
            self._frames = []
            self.stop()
            return
        self._animating_mode = mode_index
        self._frame_index = 0
        self._timer.start()

    def _advance_frame(self) -> None:
        if not self._frames:
            self.stop()
            return
        self._backend.load_conformer(self._frames[self._frame_index])
        self._frame_index = (self._frame_index + 1) % len(self._frames)

    def stop(self) -> None:
        """Stop playback and restore the equilibrium geometry.

        Public because a host closing or hiding this view must be able to
        stop the timer; a QTimer left running would keep pushing frames
        into a backend whose page may be gone.
        """
        self._timer.stop()
        self._animating_mode = None
        if self._animate_button.isChecked():
            self._animate_button.blockSignals(True)
            self._animate_button.setChecked(False)
            self._animate_button.blockSignals(False)
        if self._conformer_molblock:
            self._backend.load_conformer(self._conformer_molblock)
