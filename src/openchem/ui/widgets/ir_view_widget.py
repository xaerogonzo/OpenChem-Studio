from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from openchem.chem import jcamp
from openchem.chem.engine import ChemistryEngine
from openchem.chem.ir_export import export_jcamp_peaks
from openchem.chem.mode_animation import normal_mode_frames
from openchem.chem.spectrum_overlay import prepare_measured
from openchem.domain.scientific_result import VibrationalSpectrumResult
from openchem.ui.picture_export import copy_picture
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.widgets.ir_spectrum_widget import IrSpectrumWidget
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend
from openchem.ui.widgets.sortable_item import SortableItem

_TABLE_COLUMNS = ("Wavenumber (cm⁻¹)", "IR intensity (km/mol)", "Character")

#: A row's stable identity: its mode's own position in `spectrum.modes`,
#: the same number `IrSpectrumWidget.mode_clicked`/`set_highlighted_modes`/
#: `_start_animation` already mean by "mode index". Read back after a
#: sort, since the table ROW index stops matching it the moment a header
#: click reorders the rows.
_ROW_IDENTITY_ROLE = Qt.ItemDataRole.UserRole + 2

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
        # Fetched once and reused below -- see the identical note in
        # `NmrViewWidget.__init__`.
        backend_widget = self._backend.widget()
        backend_widget.setMinimumSize(200, 160)

        self._spectrum_widget = IrSpectrumWidget(parent=self)
        self._spectrum_widget.mode_clicked.connect(self._on_peak_clicked)

        self._table = QTableWidget(0, len(_TABLE_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_TABLE_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self._table.setMinimumHeight(80)

        self._import_button = QPushButton("Overlay measured spectrum...", self)
        self._import_button.setToolTip(
            "Load a measured IR spectrum (JCAMP-DX .jdx/.dx) and draw it "
            "behind the computed bands"
        )
        self._import_button.clicked.connect(self._on_import_measured)

        self._clear_measured_button = QPushButton("Clear overlay", self)
        self._clear_measured_button.setEnabled(False)
        self._clear_measured_button.clicked.connect(self._on_clear_measured)

        self._animate_button = QPushButton("Animate mode", self)
        self._animate_button.setCheckable(True)
        self._animate_button.setEnabled(False)
        self._animate_button.toggled.connect(self._on_animate_toggled)

        self._reset_zoom_button = QPushButton("Reset Zoom", self)
        self._reset_zoom_button.setToolTip("Restore the full wavenumber span (also: double-click the plot)")
        self._reset_zoom_button.setEnabled(False)
        self._reset_zoom_button.clicked.connect(self._spectrum_widget.reset_view)
        self._spectrum_widget.view_changed.connect(self._on_view_changed)

        self._copy_image_button = QPushButton("Copy Spectrum Image", self)
        self._copy_image_button.setToolTip("Copy the spectrum plot as an image (also: right-click the plot)")
        self._copy_image_button.clicked.connect(self._on_copy_image)

        self._export_button = QPushButton("Export JCAMP-DX...", self)
        self._export_button.setToolTip(
            "Write the predicted bands as a JCAMP-DX peak table (labelled predicted; "
            "this application's own overlay import reads spectra, not peak tables)"
        )
        self._export_button.setEnabled(False)
        self._export_button.clicked.connect(self._on_export_clicked)

        # Parented to self, so it is destroyed with the widget rather than
        # firing into a deleted backend.
        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_INTERVAL_MS)
        self._timer.timeout.connect(self._advance_frame)

        controls = QHBoxLayout()
        controls.addWidget(self._animate_button)
        controls.addWidget(self._import_button)
        controls.addWidget(self._clear_measured_button)
        controls.addStretch()
        controls.addWidget(self._reset_zoom_button)
        controls.addWidget(self._copy_image_button)
        controls.addWidget(self._export_button)

        # Same structure as `NmrViewWidget`'s own splitter, on purpose --
        # see this class's docstring. No inner horizontal splitter here:
        # unlike NMR there is only one structure pane (3D; IR has no 2D
        # depiction), so the outer vertical one is the whole story.
        self._main_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._main_splitter.addWidget(backend_widget)
        self._main_splitter.addWidget(self._spectrum_widget)
        self._main_splitter.addWidget(self._table)
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.setStretchFactor(0, 1)
        self._main_splitter.setStretchFactor(1, 3)
        self._main_splitter.setStretchFactor(2, 1)
        self._main_splitter.setSizes([220, 480, 160])

        layout = QVBoxLayout(self)
        layout.addWidget(self._header_label)
        layout.addWidget(self._warning_label)
        layout.addLayout(controls)
        layout.addWidget(self._main_splitter)

    # -- measured overlay ------------------------------------------------

    def _on_import_measured(self) -> None:
        """Load a JCAMP-DX file and draw it behind the computed bands.

        Every failure here is REPORTED, never absorbed into an empty plot.
        JCAMP-DX is an old format with real vendor variation, and this
        reader has been validated against the spec rather than against a
        file any particular instrument wrote -- so a file that will not
        load is information worth showing the user verbatim, and worth
        their reporting.
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open measured spectrum",
            "",
            "JCAMP-DX spectra (*.jdx *.dx *.jcm *.jcamp);;All files (*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
            spectrum = jcamp.parse(text)
            series = prepare_measured(spectrum)
        except jcamp.JcampError as exc:
            QMessageBox.warning(self, "Could not read spectrum", str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(self, "Could not open file", str(exc))
            return

        if series.point_count < 2:
            QMessageBox.warning(
                self,
                "Nothing to overlay",
                "That file parsed but contains fewer than two points.",
            )
            return

        self._spectrum_widget.set_measured(series)
        self._clear_measured_button.setEnabled(True)
        low, high = min(series.wavenumbers), max(series.wavenumbers)
        note = f"Overlaid {series.point_count} measured points, {low:.0f}-{high:.0f} cm-1"
        if series.was_percent:
            note += "; read as percent transmittance, converted to absorbance"
        elif "TRANS" in (series.source_units or "").upper():
            note += "; converted from transmittance to absorbance"
        self._header_label.setText(note)

    def export_jcamp_text(self) -> str:
        """The predicted bands as JCAMP-DX, read from the held result and never
        from the screen. Raises `ValueError` with nothing to export."""
        if self._spectrum is None:
            raise ValueError("There is no spectrum to export.")
        return export_jcamp_peaks(
            self._spectrum.modes, method=self._spectrum.method, scaling_factor=self._spectrum.scaling_factor
        )

    def _on_export_clicked(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export JCAMP-DX", "", "JCAMP-DX (*.jdx);;All files (*)")
        if not path:
            return
        try:
            Path(path).write_text(self.export_jcamp_text(), encoding="utf-8")
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Could not export", str(exc))

    def _on_view_changed(self) -> None:
        self._reset_zoom_button.setEnabled(self._spectrum_widget.is_zoomed())

    def _on_copy_image(self) -> None:
        # Say what happened: a copy that says nothing reads like one that failed.
        QToolTip.showText(QCursor.pos(), copy_picture(self._spectrum_widget), self)

    def _on_clear_measured(self) -> None:
        self._spectrum_widget.set_measured(None)
        self._clear_measured_button.setEnabled(False)

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
        self._export_button.setEnabled(any(not m.is_imaginary for m in spectrum.modes))

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
        # OFF during population, and resets any earlier sort order the
        # same way `NmrViewWidget._populate_table` does -- rows are
        # always (re)inserted in `spectrum.modes`'s own order.
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(spectrum.modes))
        for row, mode in enumerate(spectrum.modes):
            # Imaginary modes ARE listed, unlike in the plot. A table is a
            # record of what the calculation found; leaving them out would
            # make the row count disagree with the mode numbering ORCA
            # itself printed. Sorting by wavenumber still reads sensibly:
            # a negative (imaginary) wavenumber is a genuinely LOW number,
            # so it groups at that end ascending without special-casing.
            wavenumber_text = f"{mode.wavenumber_cm1:.1f}"
            if mode.is_imaginary:
                wavenumber_text += "  (imaginary)"
            intensity_text = (
                "—"
                if mode.ir_intensity_km_mol is None
                else f"{mode.ir_intensity_km_mol:.2f}"
            )
            # Missing intensity sorts BELOW every real value, grouping
            # the "not reported" rows at one end rather than scattering
            # them by string order -- same convention as NMR's missing
            # coupling column.
            intensity_sort = (
                float("-inf") if mode.ir_intensity_km_mol is None else mode.ir_intensity_km_mol
            )
            wavenumber_item = SortableItem(wavenumber_text, mode.wavenumber_cm1)
            wavenumber_item.setData(_ROW_IDENTITY_ROLE, row)
            items = (
                wavenumber_item,
                SortableItem(intensity_text, intensity_sort),
                QTableWidgetItem(mode.character or "—"),
            )
            for column, item in enumerate(items):
                if mode.is_imaginary:
                    item.setForeground(Qt.GlobalColor.red)
                self._table.setItem(row, column, item)
        # See the identical comment in `NmrViewWidget._populate_table`:
        # a fresh `QHeaderView`'s own default sort indicator is (section
        # 0, DESCENDING), not "no sort", so this table's very first
        # population would otherwise come up pre-sorted on its own.
        self._table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self._table.setSortingEnabled(True)
        self._table.blockSignals(False)

    # -- selection -------------------------------------------------------

    def _row_for_mode_index(self, mode_index: int) -> int | None:
        """The row currently showing mode `mode_index`, by its stable
        identity -- never by row position, which stops matching the mode
        list the moment a header click reorders the rows."""
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(_ROW_IDENTITY_ROLE) == mode_index:
                return row
        return None

    def selected_mode(self) -> int | None:
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        if not rows:
            return None
        item = self._table.item(rows[0].row(), 0)
        return item.data(_ROW_IDENTITY_ROLE) if item is not None else None

    def _on_peak_clicked(self, mode_index: int) -> None:
        row = self._row_for_mode_index(mode_index)
        if row is not None:
            self._table.selectRow(row)

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
