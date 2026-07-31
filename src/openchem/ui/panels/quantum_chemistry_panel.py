from __future__ import annotations

import dataclasses

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.app.settings import Settings
from openchem.chem.engine import ChemistryEngine
from openchem.chem.nmr_correlation import compute_cosy_pairs, compute_hmbc_pairs, compute_hsqc_pairs
from openchem.chem.orca_engine import (
    CALC_TYPE_LABELS,
    METHOD_BASIS_PRESETS,
    NMR_METHOD_BASIS,
    SOLVENTS,
)
from openchem.domain.project import ProjectModel
from openchem.domain.scientific_result import CrossPeak, SpectrumResult
from openchem.events.base import EventBus
from openchem.events.events import (
    NmrReferenceCalibrated,
    QuantumChemistryJobStateChanged,
    QuantumChemistryResultReady,
    SpectrumComputed,
)
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.ui.dialogs.external_tools_dialog import ExternalToolsDialog
from openchem.ui.widgets.nmr_correlation_plot_widget import NmrCorrelationPlotWidget, Peak
from openchem.ui.widgets.nmr_view_widget import NmrViewWidget

_NMR_SPECTRUM_COLUMNS = ("Atom", "Element", "Value (ppm)")
_CORRELATION_COLUMNS = ("Atom A", "Atom B", "Shift A", "Shift B", "J (Hz)")
_RAW_SHIELDING_NOTE = (
    "Note: isotropic shielding constants, not yet referenced to a standard (e.g. TMS) "
    "as a chemical shift — treat as raw ORCA output, not a directly comparable δ (ppm) value."
)
_CALIBRATED_NOTE = "Calibrated to TMS — values are real δ (ppm) chemical shifts."
# (correlation_type, compute_fn, x_axis_label, y_axis_label) -- HSQC/HMBC
# always put H first/C second (see chem/nmr_correlation.py), COSY is H-H.
_CORRELATION_SPECS = (
    ("hsqc", compute_hsqc_pairs, "1H shift (ppm)", "13C shift (ppm)"),
    ("hmbc", compute_hmbc_pairs, "1H shift (ppm)", "13C shift (ppm)"),
    ("cosy", compute_cosy_pairs, "1H shift (ppm)", "1H shift (ppm)"),
)


class QuantumChemistryPanel(QWidget):
    """Pick a molecule from the current project, configure a calculation,
    and run it via whichever `QuantumEngineProvider` is registered
    (`OrcaQuantumEngineProvider` is the only one today). Streams ORCA's
    stdout live and shows a summary once results arrive.
    """

    def __init__(
        self,
        quantum_chemistry_service: QuantumChemistryService,
        chemistry_engine: ChemistryEngine,
        settings: Settings,
        event_bus: EventBus,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._quantum_chemistry_service = quantum_chemistry_service
        self._chemistry_engine = chemistry_engine
        self._settings = settings
        self._project: ProjectModel | None = None
        self._pending_molecule_uuid: str | None = None
        self._pending_mol = None  # rdkit.Chem.Mol, set in _on_run_clicked -- needed
        # by _on_spectrum_computed to compute connectivity-derived HSQC/
        # HMBC/COSY correlations against whichever shift values arrive.
        # The molecule's own 2D structure and its conformer, kept for the 1D
        # NMR view: the depiction must come from the 2D molblock (drawing
        # the conformer's flattened 3D coordinates gives an unreadable
        # tangle), the 3D pane from the conformer.
        self._pending_molblock: str = ""
        self._pending_conformer_molblock: str = ""

        self._molecule_combo = QComboBox(self)
        self._molecule_combo.currentIndexChanged.connect(self._on_molecule_changed)

        self._calc_type_combo = QComboBox(self)
        self._calc_type_combo.addItems(list(CALC_TYPE_LABELS.keys()))
        self._calc_type_combo.currentTextChanged.connect(self._on_calc_type_changed)

        self._charge_spin = QSpinBox(self)
        self._charge_spin.setRange(-10, 10)

        self._multiplicity_spin = QSpinBox(self)
        self._multiplicity_spin.setRange(1, 10)
        self._multiplicity_spin.setValue(1)

        self._method_combo = QComboBox(self)
        self._method_combo.setEditable(True)
        self._method_combo.addItems(METHOD_BASIS_PRESETS)

        # Solvent is NOT a separate parameter threaded through the service --
        # it is appended to the method/basis string as a CPCM keyword, which
        # is what ORCA itself wants (`! B3LYP pcSseg-1 CPCM(Chloroform)`) and
        # what `method_basis` already is here: the whole free-text `!` header.
        #
        # That is not just convenience. The TMS reference cache is keyed on
        # the method_basis string verbatim, so appending the solvent makes a
        # chloroform reference and a gas-phase reference distinct cache
        # entries automatically. A separate `solvent` parameter would have
        # left them sharing one key and silently calibrated solvated shifts
        # against a gas-phase TMS.
        self._solvent_combo = QComboBox(self)
        for solvent in SOLVENTS:
            self._solvent_combo.addItem(solvent or "None (gas phase)", solvent)

        self._configure_button = QPushButton("Configure ORCA...", self)
        self._configure_button.clicked.connect(self._on_configure_clicked)

        self._calibrate_button = QPushButton("Calibrate Reference (TMS)...", self)
        self._calibrate_button.clicked.connect(self._on_calibrate_clicked)

        self._run_button = QPushButton("Run", self)
        self._run_button.clicked.connect(self._on_run_clicked)
        self._cancel_button = QPushButton("Cancel", self)
        self._cancel_button.setEnabled(False)
        self._cancel_button.clicked.connect(self._on_cancel_clicked)

        self._status_label = QLabel("", self)
        self._output_log = QPlainTextEdit(self)
        self._output_log.setReadOnly(True)
        self._results_label = QLabel("", self)
        self._results_label.setWordWrap(True)

        self._spectrum_note_label = QLabel(_RAW_SHIELDING_NOTE, self)
        self._spectrum_note_label.setWordWrap(True)
        self._spectrum_note_label.setVisible(False)
        self._spectrum_table = QTableWidget(0, len(_NMR_SPECTRUM_COLUMNS), self)
        self._spectrum_table.setHorizontalHeaderLabels(_NMR_SPECTRUM_COLUMNS)
        self._spectrum_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._spectrum_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._spectrum_table.setVisible(False)

        # NMR tabs: the Phase 23c 1D signal view first, then the Phase 22 2D
        # correlation tabs (HSQC/HMBC/COSY) -- one table + scatter plot per
        # correlation type, built from connectivity alone
        # (chem/nmr_correlation.py), so they populate regardless of
        # whether the shift values are raw shielding or TMS-calibrated.
        self._correlation_tabs = QTabWidget(self)
        self._correlation_tabs.setVisible(False)
        # The 1D view owns a QWebEngineView for its 3D pane, which is
        # expensive enough not to build for every user who never runs an NMR
        # calculation -- the tab exists from the start (so tab order never
        # shifts under the user), the widget lands in it on first result.
        self._nmr_view: NmrViewWidget | None = None
        self._nmr_view_tab = QWidget(self._correlation_tabs)
        self._nmr_view_layout = QVBoxLayout(self._nmr_view_tab)
        self._correlation_tabs.addTab(self._nmr_view_tab, "1D Signals")
        self._correlation_tables: dict[str, QTableWidget] = {}
        self._correlation_plots: dict[str, NmrCorrelationPlotWidget] = {}
        for correlation_type, _compute_fn, _x_label, _y_label in _CORRELATION_SPECS:
            tab = QWidget(self._correlation_tabs)
            tab_layout = QVBoxLayout(tab)
            table = QTableWidget(0, len(_CORRELATION_COLUMNS), tab)
            table.setHorizontalHeaderLabels(_CORRELATION_COLUMNS)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            plot = NmrCorrelationPlotWidget(parent=tab)
            tab_layout.addWidget(table)
            tab_layout.addWidget(plot)
            self._correlation_tabs.addTab(tab, correlation_type.upper())
            self._correlation_tables[correlation_type] = table
            self._correlation_plots[correlation_type] = plot

        form = QFormLayout()
        form.addRow("Molecule:", self._molecule_combo)
        form.addRow("Calculation:", self._calc_type_combo)
        form.addRow("Charge:", self._charge_spin)
        form.addRow("Multiplicity:", self._multiplicity_spin)
        form.addRow("Method/basis:", self._method_combo)
        form.addRow("Solvent (CPCM):", self._solvent_combo)

        run_row = QHBoxLayout()
        run_row.addWidget(self._configure_button)
        run_row.addWidget(self._calibrate_button)
        run_row.addWidget(self._run_button)
        run_row.addWidget(self._cancel_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(run_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._output_log)
        layout.addWidget(self._results_label)
        layout.addWidget(self._spectrum_note_label)
        layout.addWidget(self._spectrum_table)
        layout.addWidget(self._correlation_tabs)

        event_bus.subscribe(QuantumChemistryJobStateChanged, self._on_job_state_changed)
        event_bus.subscribe(QuantumChemistryResultReady, self._on_result_ready)
        event_bus.subscribe(SpectrumComputed, self._on_spectrum_computed)
        event_bus.subscribe(NmrReferenceCalibrated, self._on_reference_calibrated)

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self._refresh_molecule_combo()

    def _refresh_molecule_combo(self) -> None:
        self._molecule_combo.clear()
        if self._project is None:
            return
        for molecule in self._project.molecules:
            self._molecule_combo.addItem(molecule.display_name, molecule.uuid)

    def _current_molecule(self):
        if self._project is None:
            return None
        molecule_uuid = self._molecule_combo.currentData()
        if molecule_uuid is None:
            return None
        return self._project.find_molecule(molecule_uuid)

    def _on_molecule_changed(self, _index: int) -> None:
        molecule = self._current_molecule()
        if molecule is not None and molecule.molblock:
            self._charge_spin.setValue(self._chemistry_engine.formal_charge(molecule))

    def _on_configure_clicked(self) -> None:
        dialog = ExternalToolsDialog(self._settings, self, focus="orca")
        dialog.exec()

    def _on_run_clicked(self) -> None:
        molecule = self._current_molecule()
        if molecule is None or not molecule.molblock:
            self._status_label.setText("Select a molecule with a structure first.")
            return
        if not molecule.conformers:
            # Confirmed live against a real ORCA install: molecule.molblock
            # alone (from SMILES import or the 2D editor) carries only
            # heavy atoms -- hydrogens stay implicit, same as virtually
            # every MOL/SDF representation -- so building an ORCA input
            # straight from it silently sends an incomplete structure (a
            # bare oxygen atom for water, not H2O) rather than failing
            # loudly. RDKitConformerProvider._embed_one already calls
            # Chem.AddHs() before embedding, so requiring a real conformer
            # here guarantees explicit hydrogens with real 3D positions,
            # not just a flatter/lower-quality geometry.
            self._status_label.setText(
                'Switch to the "3D Viewer" tab and click "Generate Conformers..." first -- '
                "quantum chemistry needs explicit hydrogens with real 3D positions, which "
                "the 2D editor's structure alone doesn't have."
            )
            return

        molblock = molecule.conformers[0].molblock
        mol = self._chemistry_engine.mol_from_molblock(molblock)

        calc_type = CALC_TYPE_LABELS[self._calc_type_combo.currentText()]
        method_basis = self._effective_method_basis()
        if not method_basis:
            self._status_label.setText("Enter a method/basis (e.g. 'B3LYP def2-SVP').")
            return

        self._pending_molecule_uuid = molecule.uuid
        self._pending_mol = mol
        self._pending_molblock = molecule.molblock
        self._pending_conformer_molblock = molblock
        self._run_button.setEnabled(False)
        self._cancel_button.setEnabled(True)
        self._output_log.clear()
        self._results_label.setText("")
        self._spectrum_table.setRowCount(0)
        self._spectrum_table.setVisible(False)
        self._spectrum_note_label.setVisible(False)
        self._correlation_tabs.setVisible(False)
        self._status_label.setText("queued")

        self._quantum_chemistry_service.request_calculation(
            mol=mol,
            molecule_uuid=molecule.uuid,
            calc_type=calc_type,
            charge=self._charge_spin.value(),
            multiplicity=self._multiplicity_spin.value(),
            method_basis=method_basis,
        )

    def _on_cancel_clicked(self) -> None:
        if self._pending_molecule_uuid is not None:
            self._quantum_chemistry_service.cancel(self._pending_molecule_uuid)

    def _effective_method_basis(self) -> str:
        """The full ORCA `!` header body -- method/basis plus the CPCM
        solvent keyword when one is selected.

        Both Run and Calibrate go through here, and they must: the TMS
        reference is cached against this exact string, so a reference
        calibrated in chloroform would never be found by a job that built
        its header differently.
        """
        method_basis = self._method_combo.currentText().strip()
        if not method_basis:
            return ""
        solvent = self._solvent_combo.currentData()
        return f"{method_basis} CPCM({solvent})" if solvent else method_basis

    def _on_calc_type_changed(self, label: str) -> None:
        """Steers NMR runs onto an NMR-appropriate basis.

        Shielding depends on core electron density, which the general-purpose
        valence bases don't describe -- so the default preset is a poor choice
        for exactly the calculation whose point is shielding accuracy. Only
        moves off a preset the user hasn't customised: an edited or
        hand-typed method string is left alone.
        """
        if CALC_TYPE_LABELS.get(label) not in ("nmr", "nmr_coupling"):
            return
        if self._method_combo.currentText().strip() in METHOD_BASIS_PRESETS:
            self._method_combo.setCurrentText(NMR_METHOD_BASIS)

    def _on_calibrate_clicked(self) -> None:
        method_basis = self._effective_method_basis()
        if not method_basis:
            self._status_label.setText("Enter a method/basis before calibrating.")
            return
        self._calibrate_button.setEnabled(False)
        self._status_label.setText(f"Calibrating reference (TMS) for {method_basis!r} — this may take a while.")
        self._quantum_chemistry_service.request_reference_calibration(method_basis)

    def _on_reference_calibrated(self, event: NmrReferenceCalibrated) -> None:
        self._calibrate_button.setEnabled(True)
        if event.error:
            self._status_label.setText(f"Reference calibration failed: {event.error}")
        else:
            elements = ", ".join(sorted(event.values))
            self._status_label.setText(f"Reference calibrated for {event.method_basis!r} ({elements}).")

    def _on_job_state_changed(self, event: QuantumChemistryJobStateChanged) -> None:
        if event.molecule_uuid != self._pending_molecule_uuid:
            return
        self._status_label.setText(event.state.value)
        if event.message:
            self._output_log.appendPlainText(event.message)
        if event.state.value in ("completed", "failed"):
            self._run_button.setEnabled(True)
            self._cancel_button.setEnabled(False)

    def _on_result_ready(self, event: QuantumChemistryResultReady) -> None:
        if event.molecule_uuid != self._pending_molecule_uuid:
            return
        lines = [f"{d.name}: {d.value:.6f} {d.units}" for d in event.descriptors]
        if event.conformer is not None:
            lines.append("Optimized geometry added as a new conformer.")
        self._results_label.setText("\n".join(lines))

    def _on_spectrum_computed(self, event: SpectrumComputed) -> None:
        spectrum = event.spectrum
        if spectrum.molecule_uuid != self._pending_molecule_uuid:
            return
        self._spectrum_note_label.setText(
            _RAW_SHIELDING_NOTE if spectrum.spectrum_type == "nmr_raw_shielding" else _CALIBRATED_NOTE
        )
        self._spectrum_note_label.setVisible(True)
        self._spectrum_table.setVisible(True)
        atom_indices = sorted(spectrum.values)
        self._spectrum_table.setRowCount(len(atom_indices))
        for row, atom_index in enumerate(atom_indices):
            values = (
                str(atom_index),
                spectrum.elements.get(atom_index, ""),
                f"{spectrum.values[atom_index]:.3f}",
            )
            for col, text in enumerate(values):
                self._spectrum_table.setItem(row, col, QTableWidgetItem(text))

        self._update_nmr_view(spectrum)
        self._update_correlation_tabs(spectrum)

    def _update_nmr_view(self, spectrum: SpectrumResult) -> None:
        """Populates the 1D signal view -- the same `NmrViewWidget` the
        Property Panel opens for the empirical estimator, so a real ORCA
        result and a SMARTS estimate are read the same way."""
        if not self._pending_molblock:
            return
        if self._nmr_view is None:
            self._nmr_view = NmrViewWidget(self._chemistry_engine, parent=self._nmr_view_tab)
            self._nmr_view_layout.addWidget(self._nmr_view)
        self._nmr_view.set_spectrum(
            self._pending_molblock, spectrum, self._pending_conformer_molblock or None
        )
        self._correlation_tabs.setVisible(True)

    def _update_correlation_tabs(self, spectrum: SpectrumResult) -> None:
        mol = self._pending_mol
        if mol is None:
            return
        # NMRSpectrumResult.couplings (Phase 22, "NMR + Spin-Spin Coupling"
        # calc_type only) -- getattr since the base SpectrumResult type
        # this method is annotated with doesn't have the field.
        real_couplings: dict[tuple[int, int], float] = getattr(spectrum, "couplings", None) or {}
        for correlation_type, compute_fn, x_label, y_label in _CORRELATION_SPECS:
            cross_peaks = compute_fn(mol, spectrum.values)
            if real_couplings:
                cross_peaks = [
                    dataclasses.replace(
                        cp, coupling_hz=real_couplings.get((min(cp.atom_a, cp.atom_b), max(cp.atom_a, cp.atom_b)))
                    )
                    for cp in cross_peaks
                ]
            self._populate_correlation_tab(correlation_type, cross_peaks, spectrum, x_label, y_label)
        self._correlation_tabs.setVisible(True)

    def _populate_correlation_tab(
        self,
        correlation_type: str,
        cross_peaks: list[CrossPeak],
        spectrum: SpectrumResult,
        x_label: str,
        y_label: str,
    ) -> None:
        table = self._correlation_tables[correlation_type]
        table.setRowCount(len(cross_peaks))
        peaks: list[Peak] = []
        for row, cross_peak in enumerate(cross_peaks):
            shift_a = spectrum.values.get(cross_peak.atom_a)
            shift_b = spectrum.values.get(cross_peak.atom_b)
            values = (
                str(cross_peak.atom_a),
                str(cross_peak.atom_b),
                f"{shift_a:.3f}" if shift_a is not None else "",
                f"{shift_b:.3f}" if shift_b is not None else "",
                f"{cross_peak.coupling_hz:.2f}" if cross_peak.coupling_hz is not None else "—",
            )
            for col, text in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(text))
            if shift_a is not None and shift_b is not None:
                peaks.append(Peak(x=shift_a, y=shift_b))
        self._correlation_plots[correlation_type].set_peaks(peaks, x_label=x_label, y_label=y_label)
