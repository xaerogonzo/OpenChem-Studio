from __future__ import annotations

import dataclasses

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.calculation_input import canonical_conformer
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
from openchem.domain.scientific_result import (
    CrossPeak,
    SpectrumResult,
    VibrationalSpectrumResult,
)
from openchem.events.base import EventBus
from openchem.events.events import (
    MoleculeSelected,
    NmrReferenceCalibrated,
    NmrScalingCalibrated,
    QmSurfaceComputed,
    QuantumChemistryJobStateChanged,
    QuantumChemistryResultReady,
    SpectrumComputed,
)
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.ui.dialogs.external_tools_dialog import ExternalToolsDialog
from openchem.ui.molecule_combo import repopulate, select
from openchem.ui.widgets.empty_state import empty_state, empty_state_text, is_empty_state
from openchem.ui.widgets.esp_compare_widget import EspCompareWidget
from openchem.ui.widgets.ir_view_widget import IrViewWidget
from openchem.ui.widgets.nmr_correlation_plot_widget import NmrCorrelationPlotWidget, Peak
from openchem.ui.widgets.nmr_view_widget import NmrViewWidget

_NMR_SPECTRUM_COLUMNS = ("Atom", "Element", "Value (ppm)")
_CORRELATION_COLUMNS = ("Atom A", "Atom B", "Shift A", "Shift B", "J (Hz)")
# "Source" is a first-class column, not something to dig out of provenance:
# a spectrum drawn from two methods that does not say which value came from
# where is harder to trust than either method alone.
_HYBRID_COLUMNS = (
    "Atom",
    "Element",
    "Shift (ppm)",
    "Source",
    "Expected error",
    "Methods differ by",
)
_HYBRID_UNAVAILABLE_NOTE = (
    "The hybrid view merges this calculation with the experimental-shift database, "
    "per atom. It needs an empirically scaled spectrum — calibrate this method/basis "
    "first (Calibrate Reference), since TMS referencing alone leaves the computed "
    "values on a different scale from measured ones."
)
_RAW_SHIELDING_NOTE = (
    "Note: isotropic shielding constants, not yet referenced to a standard (e.g. TMS) "
    "as a chemical shift — treat as raw ORCA output, not a directly comparable δ (ppm) value."
)
_CALIBRATED_NOTE = "Calibrated to TMS — values are real δ (ppm) chemical shifts."
_SCALED_NOTE = (
    "Empirically scaled — real δ (ppm), fitted against known compounds at this exact "
    "method/basis. More accurate than TMS referencing alone, which assumes a slope of −1."
)
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
        qm_surface_service=None,
    ) -> None:
        super().__init__(parent)
        self._quantum_chemistry_service = quantum_chemistry_service
        self._chemistry_engine = chemistry_engine
        self._settings = settings
        # Optional, and after `parent` so every existing positional call
        # site keeps working. Without it the Surfaces tab says why it is
        # empty rather than not existing -- a missing tab reads as a
        # version difference, an explained one reads as configuration.
        self._qm_surface_service = qm_surface_service
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
        #: The geometry ORCA optimised, once it arrives. Kept separate from
        #: the submitted one because the normal modes describe motion about
        #: THIS structure, not the one that was sent.
        self._optimized_conformer_molblock: str = ""

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

        # Opt-in, because it costs one full ORCA run per conformer. Off by
        # default so nobody accidentally turns a 5-minute job into an hour.
        self._boltzmann_check = QCheckBox("Average over all conformers (Boltzmann)", self)
        self._boltzmann_check.setToolTip(
            "Runs the calculation on every conformer and averages the shifts by their "
            "Boltzmann populations, using each run's own SCF energy.\n\n"
            "A flexible molecule in solution interconverts fast on the NMR timescale, so "
            "the measured shift is a population average -- not the lowest-energy geometry's.\n\n"
            "Costs one full ORCA run per conformer."
        )

        self._configure_button = QPushButton("Configure ORCA...", self)
        self._configure_button.clicked.connect(self._on_configure_clicked)

        self._calibrate_button = QPushButton("Calibrate Reference (TMS)...", self)
        self._calibrate_button.clicked.connect(self._on_calibrate_clicked)
        # A second, more thorough calibration. Costs N ORCA runs against
        # the TMS button's one, which is why it is its own button rather
        # than an upgrade of that one -- the user should choose to spend
        # that time. Once it has run, its factors take priority.
        self._scaling_button = QPushButton("Calibrate Scaling (11 standards)...", self)
        self._scaling_button.setToolTip(
            "Fits an empirical shift-scaling line from real runs on known compounds. "
            "Much more accurate than TMS referencing alone, and much slower to calibrate."
        )
        self._scaling_button.clicked.connect(self._on_scaling_calibrate_clicked)

        self._run_button = QPushButton("Run", self)
        self._run_button.clicked.connect(self._on_run_clicked)
        self._cancel_button = QPushButton("Cancel", self)
        self._cancel_button.setEnabled(False)
        self._cancel_button.clicked.connect(self._on_cancel_clicked)

        self._status_label = QLabel("", self)
        self._output_log = QPlainTextEdit(self)
        self._output_log.setReadOnly(True)
        # `QPlainTextEdit` has placeholder text natively, so the Log tab
        # explains itself without adding a widget to a panel that cannot
        # afford one -- see the `addTab` comment below.
        self._output_log.setPlaceholderText(
            "Nothing has run yet. Press Run above and ORCA's output streams "
            "here as it works."
        )
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
        # Every tab below carries a placeholder saying why it is blank and
        # what would fill it. A job populates the tabs relevant to ITS
        # calculation type and leaves the rest untouched, so most of these
        # are empty most of the time -- an ESP single point lights up
        # Surfaces and nothing else. With nothing on screen to say so, all
        # six other tabs read as broken.
        #
        # They are deliberately NOT collected into a dict here; see
        # `_content_of` for the heap corruption that caused.

        self._nmr_view: NmrViewWidget | None = None
        self._nmr_view_tab = QWidget(self._correlation_tabs)
        self._nmr_view_layout = QVBoxLayout(self._nmr_view_tab)
        # THE LOG IS A TAB.
        #
        # `_output_log` is a `QPlainTextEdit` whose default Expanding
        # policy took the largest share of the panel, so a finished
        # calculation showed a wall of SCF iterations above a cramped band
        # of the numbers it was run for. Alex: "completed calculations
        # should emphasize results rather than console output".
        #
        # A tab rather than a collapsible section, which is the shape Alex
        # offered -- "or a separate Log tab" -- and which reparents the
        # widget that already exists rather than wrapping it in a new one.
        #
        # (Wrapping it DID crash the suite when this was written, and the
        # comment here used to explain that at length. The cause was the
        # test harness collecting MainWindows, not this panel; see
        # CLAUDE.md, "SOLVED: the teardown collect was DESTROYING
        # MainWindows". A section would be safe now. A tab is still the
        # better answer, so it stays.)
        self._correlation_tabs.addTab(self._nmr_view_tab, "1D Signals")
        self._add_empty_state(
            self._nmr_view_tab,
            self._nmr_view_layout,
            "No NMR signals for this molecule yet.",
            'Choose an NMR calculation in "Calculation" above and press Run. '
            "Grouped signals, integrations and multiplicities appear here.",
        )

        # IR, on the same deferred-construction pattern and for the same
        # reason (a QWebEngineView for its 3D pane). Added AFTER the NMR
        # tab rather than before it so existing tab positions do not move.
        self._ir_view: IrViewWidget | None = None
        self._ir_view_tab = QWidget(self._correlation_tabs)
        self._ir_view_layout = QVBoxLayout(self._ir_view_tab)
        self._correlation_tabs.addTab(self._ir_view_tab, "IR")
        self._add_empty_state(
            self._ir_view_tab,
            self._ir_view_layout,
            "No vibrational spectrum yet.",
            'Run an "Optimisation + Frequencies" calculation. The modes come '
            "from the frequency step, so a single point cannot produce them.",
        )

        # Surfaces: the point-charge ESP beside the ab initio one. Same
        # deferred construction -- it owns TWO QWebEngineViews, which is
        # the most expensive tab here and the least often opened.
        self._surfaces_view: EspCompareWidget | None = None
        self._surfaces_tab = QWidget(self._correlation_tabs)
        self._surfaces_layout = QVBoxLayout(self._surfaces_tab)
        self._correlation_tabs.addTab(self._surfaces_tab, "Surfaces")
        self._add_empty_state(
            self._surfaces_tab,
            self._surfaces_layout,
            "No surface computed yet.",
            "Run any calculation that keeps its wavefunction, then pick a "
            "surface type above and press Compute QM surface. The instant "
            "point-charge map needs no calculation at all.",
        )

        # Hybrid: this calculation merged with the experimental-shift
        # lookup, per atom, choosing whichever expects to be less wrong.
        # Built here rather than on first result because it is a plain
        # label and table -- nothing expensive to defer.
        hybrid_tab = QWidget(self._correlation_tabs)
        hybrid_layout = QVBoxLayout(hybrid_tab)
        self._hybrid_summary_label = QLabel("", hybrid_tab)
        self._hybrid_summary_label.setWordWrap(True)
        self._hybrid_table = QTableWidget(0, len(_HYBRID_COLUMNS), hybrid_tab)
        self._hybrid_table.setHorizontalHeaderLabels(_HYBRID_COLUMNS)
        self._hybrid_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._hybrid_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        hybrid_layout.addWidget(self._hybrid_summary_label)
        hybrid_layout.addWidget(self._hybrid_table)
        self._correlation_tabs.addTab(hybrid_tab, "Hybrid")
        # The hybrid tab needs no placeholder WIDGET: `_hybrid_summary_label`
        # already exists to carry exactly this kind of note, and already
        # shows `_HYBRID_UNAVAILABLE_NOTE` when a run produces no rows. It
        # only ever started blank, so it is given its message up front.
        self._hybrid_summary_label.setText(
            "No hybrid shifts yet. Run an NMR calculation -- this tab merges "
            "it with the experimental-shift lookup, per atom, choosing "
            "whichever expects to be less wrong."
        )

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
            # One checkbox per tab rather than one for the panel: HSQC is
            # sparse enough to read as dots while HMBC on the same molecule
            # is crowded enough to want contours, so the useful setting
            # genuinely differs between them.
            contour_toggle = QCheckBox("Contours", tab)
            contour_toggle.setChecked(True)
            contour_toggle.setToolTip(
                "Draw cross peaks as contour rings rather than dots.\n\n"
                "The rings show POSITION only. Predicted correlations carry no "
                "intensity, so every peak is drawn the same height and width -- "
                "unlike a measured spectrum, where contour height is peak volume."
            )
            contour_toggle.toggled.connect(plot.set_show_contours)
            tab_layout.addWidget(table)
            tab_layout.addWidget(contour_toggle)
            tab_layout.addWidget(plot)
            self._correlation_tabs.addTab(tab, correlation_type.upper())
            self._correlation_tables[correlation_type] = table
            self._correlation_plots[correlation_type] = plot
            # Painted into the plot rather than added as a placeholder
            # widget -- see `ui/widgets/empty_state.py` for the heap
            # corruption that a placeholder in a content-bearing tab
            # caused, measured 5/5. The message also lands exactly where
            # the peaks would be, which is where somebody is looking.
            plot.set_empty_message(
                f"No {correlation_type.upper()} cross peaks yet.\n"
                "Run an NMR calculation."
            )

        # LAST, deliberately -- "results outrank the log" is an ordering
        # claim as much as a layout one, and every existing tab keeps its
        # index so nothing shifts under somebody who has learned where
        # things are.
        self._correlation_tabs.addTab(self._output_log, "Log")

        form = QFormLayout()
        form.addRow("Molecule:", self._molecule_combo)
        form.addRow("Calculation:", self._calc_type_combo)
        form.addRow("Charge:", self._charge_spin)
        form.addRow("Multiplicity:", self._multiplicity_spin)
        form.addRow("Method/basis:", self._method_combo)
        form.addRow("Solvent (CPCM):", self._solvent_combo)
        form.addRow("", self._boltzmann_check)

        run_row = QHBoxLayout()
        run_row.addWidget(self._configure_button)
        run_row.addWidget(self._calibrate_button)
        run_row.addWidget(self._scaling_button)
        run_row.addWidget(self._run_button)
        run_row.addWidget(self._cancel_button)

        # THE RESULTS COME FIRST, AND THE LOG IS COLLAPSED UNDERNEATH.
        #
        # `_output_log` is a `QPlainTextEdit`, whose default Expanding
        # policy took the largest share of the panel -- so a finished
        # calculation showed a wall of scrolling SCF iterations above a
        # cramped band of the numbers somebody actually ran it for. Alex,
        # reading a completed job: "completed calculations should
        # emphasize results rather than console output".
        #
        # It expands by itself while a job runs, because then the log IS
        # the interesting thing -- there is nothing else yet, and a silent
        # panel during a ten-minute ORCA run reads as a hang.

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(run_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._results_label)
        layout.addWidget(self._spectrum_note_label)
        layout.addWidget(self._spectrum_table)
        layout.addWidget(self._correlation_tabs)

        self._reset_empty_states()

        event_bus.subscribe(QuantumChemistryJobStateChanged, self._on_job_state_changed)
        event_bus.subscribe(QuantumChemistryResultReady, self._on_result_ready)
        event_bus.subscribe(SpectrumComputed, self._on_spectrum_computed)
        event_bus.subscribe(QmSurfaceComputed, self._on_qm_surface_computed)
        event_bus.subscribe(NmrReferenceCalibrated, self._on_reference_calibrated)
        event_bus.subscribe(NmrScalingCalibrated, self._on_scaling_calibrated)
        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self._refresh_molecule_combo()

    def _refresh_molecule_combo(self) -> None:
        molecules = self._project.molecules if self._project is not None else []
        repopulate(self._molecule_combo, [(m.display_name, m.uuid) for m in molecules])

    def _on_molecule_selected(self, event: MoleculeSelected) -> None:
        """Follow the project tree, like the editor, the 3D viewer and the
        Property panel already do.

        Without this the panel silently computed on whichever molecule the
        combo happened to land on, which is how a project with two
        identically-named molecules turned into "ORCA refuses to run even
        though the 3D viewer is showing ten conformers".
        """
        select(self._molecule_combo, event.molecule_uuid)

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

        # `canonical_conformer` rather than `conformers[0]`: the two agree
        # only while the list happens to be energy-sorted, which a project
        # saved by an older version does not guarantee.
        molblock = canonical_conformer(molecule).molblock
        mol = self._chemistry_engine.mol_from_molblock(molblock)

        calc_type = CALC_TYPE_LABELS[self._calc_type_combo.currentText()]
        method_basis = self._effective_method_basis()
        if not method_basis:
            self._status_label.setText("Enter a method/basis (e.g. 'B3LYP def2-SVP').")
            return

        if calc_type == "led" and not self._confirm_led_cost(self, mol):
            return

        self._pending_molecule_uuid = molecule.uuid
        self._pending_mol = mol
        self._pending_molblock = molecule.molblock
        self._pending_conformer_molblock = molblock
        self._optimized_conformer_molblock = ""
        self._run_button.setEnabled(False)
        self._cancel_button.setEnabled(True)
        self._output_log.clear()
        self._results_label.setText("")
        self._spectrum_table.setRowCount(0)
        self._spectrum_table.setVisible(False)
        self._spectrum_note_label.setVisible(False)
        self._correlation_tabs.setVisible(False)
        # Back to placeholders. A second job of a different type must not
        # leave the first job's tables sitting under the new job's heading,
        # which would be worse than a blank tab -- it would be wrong.
        self._reset_empty_states()
        self._status_label.setText("queued")

        if self._boltzmann_check.isChecked() and len(molecule.conformers) > 1:
            self._quantum_chemistry_service.request_boltzmann_nmr(
                mols=[
                    self._chemistry_engine.mol_from_molblock(conformer.molblock)
                    for conformer in molecule.conformers
                ],
                molecule_uuid=molecule.uuid,
                calc_type=calc_type,
                charge=self._charge_spin.value(),
                multiplicity=self._multiplicity_spin.value(),
                method_basis=method_basis,
            )
            return

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

    @staticmethod
    def _confirm_led_cost(parent, mol) -> bool:
        """Show what an LED job will cost BEFORE it starts. True to proceed.

        Before, not after, because the two ways this job goes wrong are both
        unrecoverable once it is running: it takes days, or it fills the
        scratch disk. Measured, benzene-water is the case that makes the
        second one real -- ten minutes and 1.9 GB, so a time-only warning
        would wave through the job most likely to fill a laptop.

        A structure that is not two species is refused here rather than at
        input-building time, so the message arrives as a dialog instead of a
        failed job in the log.

        A staticmethod taking `parent` explicitly, because the decision it
        makes is worth testing on its own and a Qt widget cannot be
        instantiated without its whole service container.

        The fragment count comes from the chem layer rather than from a
        local `Chem.GetMolFrags` call: `tests/test_layering.py` forbids a UI
        module importing RDKit, and caught the first version of this doing
        exactly that.
        """
        from openchem.chem.orca_led import estimate_led_cost_for

        estimate = estimate_led_cost_for(mol)
        if estimate.fragment_count != 2:
            QMessageBox.information(
                parent,
                "Two partners needed",
                "An interaction breakdown needs exactly two separate species — "
                "they are the fragments it decomposes the interaction between.\n\n"
                "Draw the two partners as separate molecules (a Lewis acid and "
                "its base, a hydrogen-bonded pair) rather than joined by a bond.",
            )
            return False
        if estimate.geometry_problem:
            # Refused, not warned. A live run of an overlapping pair produced
            # +40619 kcal/mol -- arithmetically correct, physically
            # meaningless, and indistinguishable from a real result once it
            # is just a number on the panel.
            QMessageBox.warning(
                parent, "This geometry cannot be decomposed", estimate.geometry_problem
            )
            return False

        if not estimate.should_warn:
            return True
        answer = QMessageBox.question(
            parent,
            "This calculation is expensive",
            f"{estimate.advice}\n\n"
            f"{estimate.atoms} atoms, {estimate.basis_functions} basis functions, "
            f"DLPNO-CCSD(T).\n\n"
            "The estimate is scaled from two measured jobs and is a guide to the "
            "order of the cost, not a prediction.\n\nStart it anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

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

    def _on_scaling_calibrate_clicked(self) -> None:
        method_basis = self._effective_method_basis()
        if not method_basis:
            self._status_label.setText("Enter a method/basis before calibrating.")
            return
        self._scaling_button.setEnabled(False)
        self._status_label.setText(
            f"Calibrating scaling factors for {method_basis!r} across 11 reference compounds — "
            "this runs 11 ORCA jobs and will take a while."
        )
        self._quantum_chemistry_service.request_scaling_calibration(method_basis)

    def _on_scaling_calibrated(self, event: NmrScalingCalibrated) -> None:
        self._scaling_button.setEnabled(True)
        if not event.factors:
            self._status_label.setText(f"Scaling calibration failed: {event.error}")
            return
        # R^2 is shown, not hidden: a slope is only as good as the fit it
        # came from, and the user is about to trust every shift to it.
        summary = ", ".join(
            f"{element} R²={factors.r_squared:.4f} (n={factors.sample_count})"
            for element, factors in sorted(event.factors.items())
        )
        message = f"Scaling calibrated for {event.method_basis!r}: {summary}."
        if event.error:
            message += f" Not calibrated — {event.error}"
        self._status_label.setText(message)

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
        if event.state.value == "running":
            # Shown and selected while there is nothing else yet: a panel
            # that sits silent through a ten-minute ORCA run reads as a
            # hang, and the log is the only evidence anything is happening.
            self._correlation_tabs.setVisible(True)
            self._correlation_tabs.setCurrentWidget(self._output_log)
        if event.state.value in ("completed", "failed"):
            self._run_button.setEnabled(True)
            self._cancel_button.setEnabled(False)
            if event.state.value == "failed":
                # Stay on the log: it is where the reason is, and every
                # other tab is empty for a job that produced nothing.
                #
                # On SUCCESS nothing is forced. The numbers land in
                # `_results_label`, which sits above the tabs and is always
                # visible, and each `_update_*` selects its own tab when it
                # has something to show -- yanking the user to a tab that
                # says "no NMR signals yet" after an ESP run would be worse
                # than leaving them where they were.
                self._correlation_tabs.setCurrentWidget(self._output_log)
            # Failed keeps it OPEN: the log is where the reason is, and
            # collapsing it would hide the one thing worth reading.

    def _on_result_ready(self, event: QuantumChemistryResultReady) -> None:
        if event.molecule_uuid != self._pending_molecule_uuid:
            return
        lines = [f"{d.name}: {d.value:.6f} {d.units}" for d in event.descriptors]
        if event.conformer is not None:
            lines.append("Optimized geometry added as a new conformer.")
            # Held for the IR view, which must animate about the optimised
            # geometry. `QuantumChemistryResultReady` is published before
            # the vibrational `SpectrumComputed` from the same job
            # (`_finish_calculation_job` parses descriptors first), so by
            # the time the spectrum arrives this is already set.
            self._optimized_conformer_molblock = event.conformer.molblock
        self._results_label.setText("\n".join(lines))
        # After the conformer is recorded, so the surfaces are drawn on the
        # optimised geometry when there is one.
        self._update_surfaces_view()

    def _on_spectrum_computed(self, event: SpectrumComputed) -> None:
        spectrum = event.spectrum
        if spectrum.molecule_uuid != self._pending_molecule_uuid:
            return
        # A VIBRATIONAL SPECTRUM MUST NOT REACH THE NMR PATH BELOW, and
        # this branch is the whole reason the method dispatches at all.
        # `SpectrumComputed` carries every spectrum type, and everything
        # after this point reads `spectrum.values` -- which
        # `VibrationalSpectrumResult` documents as DELIBERATELY EMPTY,
        # because an IR peak belongs to a normal mode rather than to an
        # atom. Falling through produced no error and no empty state: an
        # NMR table with zero rows, a "1D Signals" view built from no
        # signals, and three correlation tabs computed over nothing, all
        # presented as a successful result.
        if isinstance(spectrum, VibrationalSpectrumResult):
            self._update_ir_view(spectrum)
            return
        referencing = (
            spectrum.provenance.parameters.get("referencing") if spectrum.provenance else None
        )
        if spectrum.spectrum_type == "nmr_raw_shielding":
            note = _RAW_SHIELDING_NOTE
        elif referencing == "empirical_linear_scaling":
            note = _SCALED_NOTE
        else:
            note = _CALIBRATED_NOTE
        self._spectrum_note_label.setText(note)
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
        self._update_hybrid_tab(spectrum)

    def _update_surfaces_view(self) -> None:
        """Shows the point-charge ESP beside the ab initio one.

        Populated on any completed calculation, not only a frequency job:
        the wavefunction a single-point leaves behind is enough to plot
        every surface, so requiring an `opt_freq` would withhold the
        cheapest path to the most expensive picture.
        """
        molblock = self._optimized_conformer_molblock or self._pending_conformer_molblock
        if not molblock or self._qm_surface_service is None:
            return
        if self._surfaces_view is None:
            self._surfaces_view = EspCompareWidget(
                self._chemistry_engine,
                self._qm_surface_service,
                parent=self._surfaces_tab,
            )
            self._surfaces_layout.addWidget(self._surfaces_view)
        self._surfaces_view.set_molecule(self._pending_molecule_uuid or "", molblock)
        self._fill_tab(self._surfaces_tab)
        self._correlation_tabs.setVisible(True)

    # --- empty states --------------------------------------------------------

    def _add_empty_state(
        self,
        tab: QWidget,
        layout: QVBoxLayout,
        headline: str,
        action: str,
    ) -> None:
        """Give `tab` a placeholder standing in for its content.

        **NOTHING IS STORED.** The placeholder and the content it replaces
        are both found through Qt's own parent/child tree whenever they
        are needed -- see `_content_of` for why, which is a heap
        corruption this cost three full suite runs to pin down.

        The content is "every direct child of the tab that is not the
        placeholder", which is exactly right here and needs no list: an
        empty `QTableWidget` still draws its header strip, so a populated
        header sitting above the words "nothing here yet" is the failure
        this hides. The three deferred tabs (1D Signals, IR, Surfaces)
        simply have no content yet, and the same rule gives an empty list.
        """
        layout.addWidget(empty_state(headline, action, tab))

    def empty_message_for_tab(self, index: int) -> str:
        """What this tab tells a reader when it has nothing to show.

        **Derived from the widgets, never from a list kept alongside
        them.** A tab that displays nothing must be able to fail the guard
        in `tests/test_empty_states.py`, and it cannot if the guard reads a
        registry of messages somebody remembered to update -- the same
        direction that let two panels ship with no help topic.

        Three mechanisms, because one size did not fit:

        - a placeholder label, for the three deferred tabs whose content
          does not exist until a result arrives;
        - `_hybrid_summary_label`, which already existed to carry notes;
        - text painted inside `NmrCorrelationPlotWidget`, for the
          correlation tabs.

        The split is not stylistic. A placeholder WIDGET added to a tab
        that already holds content widgets corrupted the heap during the
        teardown collect, 5 runs out of 5 -- see
        `ui/widgets/empty_state.py`. So only the genuinely-empty tabs get
        one, and the rest say it through a widget that is already there.
        """
        tab = self._correlation_tabs.widget(index)
        if tab is None:
            return ""
        for child in tab.findChildren(QWidget):
            if is_empty_state(child):
                return empty_state_text(child)
        for plot in tab.findChildren(NmrCorrelationPlotWidget):
            if plot.empty_message():
                return plot.empty_message()
        if self._hybrid_summary_label in tab.findChildren(QLabel):
            return self._hybrid_summary_label.text()
        if tab is self._output_log:
            return self._output_log.placeholderText()
        return ""

    @staticmethod
    def _content_of(tab: QWidget) -> tuple[QWidget | None, list[QWidget]]:
        """This tab's placeholder, and the widgets it stands in for.

        DISCOVERED, never remembered, and that distinction is load-bearing.

        The first version kept `dict[QWidget, tuple[EmptyState, ...]]` on
        the panel. **That crashed the suite with a Windows heap corruption
        (0xc0000374), deterministically, 3 runs out of 3**, inside the
        teardown `gc.collect()` -- and NOT in a test of this panel, but in
        `test_main_window_conformers.py`, five hundred tests after the
        window that built it went away.

        A dict keyed by a QWidget has to HASH that widget, and PySide
        hashes on the underlying C++ pointer. Qt deletes a parent's
        children C++-side, so by collection time those keys address freed
        memory. Reading it to hash or to decref is the corruption.

        The rule for anything holding Qt objects in this codebase: keep
        them where Qt already keeps them. The parent/child tree is valid
        for exactly as long as the widgets are, which a Python container
        cannot promise.
        """
        state: QWidget | None = None
        content: list[QWidget] = []
        for child in tab.children():
            if not isinstance(child, QWidget):
                continue  # the layout itself is a QObject, not a QWidget
            if is_empty_state(child):
                state = child
            else:
                content.append(child)
        return state, content

    def _fill_tab(self, tab: QWidget) -> None:
        """This tab now has real content: retire its placeholder."""
        state, content = self._content_of(tab)
        if state is None:
            return
        state.setVisible(False)
        for widget in content:
            widget.setVisible(True)

    def _reset_empty_states(self) -> None:
        """Back to placeholders, for a fresh job.

        Walks the tab widget rather than a stored collection, for the
        reason in `_content_of`.
        """
        for index in range(self._correlation_tabs.count()):
            state, content = self._content_of(self._correlation_tabs.widget(index))
            if state is None:
                continue
            state.setVisible(True)
            for widget in content:
                widget.setVisible(False)

    def _on_qm_surface_computed(self, event) -> None:
        if self._surfaces_view is None:
            return
        self._surfaces_view.on_surface_computed(
            event.molecule_uuid, event.field, event.error
        )

    def _update_ir_view(self, spectrum: VibrationalSpectrumResult) -> None:
        """Populates the IR tab, built on first result for the same reason
        the 1D NMR view is: it owns a `QWebEngineView` for its 3D pane,
        which is expensive to build for a user who never runs a frequency
        job. The tab itself exists from the start so tab order never
        shifts under the user."""
        if self._ir_view is None:
            self._ir_view = IrViewWidget(self._chemistry_engine, parent=self._ir_view_tab)
            self._ir_view_layout.addWidget(self._ir_view)
        # The OPTIMISED conformer, not the submitted structure: an
        # `opt_freq` optimises first and the modes describe motion about
        # the result. `_pending_conformer_molblock` is what was sent, so
        # the optimised geometry published by the same job is preferred
        # when it arrived.
        self._ir_view.set_spectrum(
            spectrum, self._optimized_conformer_molblock or self._pending_conformer_molblock or ""
        )
        self._fill_tab(self._ir_view_tab)
        self._correlation_tabs.setVisible(True)
        self._correlation_tabs.setCurrentWidget(self._ir_view_tab)

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
        self._fill_tab(self._nmr_view_tab)
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

    def _update_hybrid_tab(self, spectrum: SpectrumResult) -> None:
        """Merges this calculation with the database lookup, per atom.

        Runs only against an empirically scaled spectrum. A raw or
        TMS-only one is refused rather than merged: the database's values
        are measured ppm, and TMS referencing removes an offset without
        removing the scale error, so splicing the two would produce a
        step in the spectrum that reads as chemistry.
        """
        from openchem.chem import nmr_database, nmr_hybrid
        from openchem.domain.nmr import ScalingFactors

        mol = self._pending_mol
        parameters = (spectrum.provenance.parameters if spectrum.provenance else {}) or {}
        if mol is None or parameters.get("referencing") != "empirical_linear_scaling":
            self._hybrid_summary_label.setText(_HYBRID_UNAVAILABLE_NOTE)
            self._hybrid_table.setRowCount(0)
            return

        rows: list[tuple[str, ...]] = []
        counts: dict[str, int] = {}
        errors: list[float] = []
        notes: list[str] = []
        # Carbon only -- the lookup's per-band accuracy was measured on
        # carbons, and selecting protons on a number nobody measured is
        # exactly what this module refuses to do.
        for element in sorted(
            {e for e in spectrum.elements.values() if e in nmr_hybrid.MERGEABLE_ELEMENTS}
        ):
            computed = {
                index: value
                for index, value in spectrum.values.items()
                if spectrum.elements.get(index) == element
            }
            scaling = parameters.get(f"scaling_{element}")
            factors = ScalingFactors(**scaling) if isinstance(scaling, dict) else None

            lookup = nmr_database.predict_spectrum(mol, spectrum.molecule_uuid, element=element)
            if not lookup.values:
                notes.append(
                    f"{element}: no database values to merge with"
                    + (f" — {lookup.error}" if lookup.error else "")
                )
                continue

            check = nmr_hybrid.check_calibration(
                nmr_hybrid.trusted_values(lookup),
                computed,
                element,
                getattr(factors, "residual_rms", None),
            )
            lookups = nmr_hybrid.lookup_candidates(lookup)
            computed_candidates = nmr_hybrid.computed_candidates(computed, factors)
            candidates = {
                index: [c for c in (lookups.get(index), computed_candidates.get(index)) if c]
                for index in set(lookups) | set(computed_candidates)
            }
            merged = nmr_hybrid.fuse(
                candidates, spectrum.elements, spectrum.molecule_uuid, element, check
            )
            if merged.error:
                notes.append(f"{element}: {merged.error}")
                continue

            details = merged.provenance.parameters
            notes.append(self._hybrid_summary(element, details, check))
            for source, count in details["sources"].items():
                counts[source] = counts.get(source, 0) + count
            for index in sorted(merged.values):
                detail = details["per_atom"][str(index)]
                expected = detail["expected_error"]
                if expected is not None:
                    errors.append(expected)
                rows.append(
                    (
                        str(index),
                        element,
                        f"{merged.values[index]:.3f}",
                        str(detail["source"]),
                        f"{expected:.2f}" if expected is not None else "unknown",
                        f"{detail['disagreement_ppm']:.2f}"
                        if detail["disagreement_ppm"]
                        else "—",
                    )
                )

        if rows:
            totals = "   ".join(f"{count} {source}" for source, count in sorted(counts.items()))
            average = f"{sum(errors) / len(errors):.2f} ppm" if errors else "unknown"
            notes.insert(0, f"{len(rows)} atoms      {totals}\nexpected average error   {average}")
        self._hybrid_summary_label.setText("\n".join(notes) or _HYBRID_UNAVAILABLE_NOTE)
        # No `_fill_tab` here: this tab has no placeholder WIDGET to
        # retire. `_hybrid_summary_label` IS the placeholder, and the line
        # above has just overwritten it -- with the real summary when
        # there are rows, or `_HYBRID_UNAVAILABLE_NOTE` when a run
        # produced none, which is a more specific answer than the opening
        # message for somebody who has already run something.
        self._hybrid_table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for col, text in enumerate(values):
                self._hybrid_table.setItem(row, col, QTableWidgetItem(text))

    @staticmethod
    def _hybrid_summary(element: str, details: dict, check) -> str:
        """The calibration check, reported either way.

        A failing check no longer blocks the merge -- measured on DELTA50,
        refusing cost accuracy and prevented no harm. It is still worth
        showing: it says how far this calculation sits from values the
        database is confident about, which is real information about the
        run even when the merged spectrum is the better answer.
        """
        if check is None:
            return (
                f"{element}: no database values confident enough to check this "
                "calculation against — the merge could not verify itself."
            )
        verdict = "passed" if check.passed else "DISAGREES"
        note = (
            f"{element}: calibration check {verdict} against {check.compared} trusted "
            f"values (offset {check.mean_offset:+.2f}, RMS {check.rms:.2f}, "
            f"max {check.max_deviation:.2f} ppm)"
        )
        if not check.passed:
            note += (
                "\n   Merged anyway: each atom is still chosen by whichever method "
                "expects to be less wrong, and refusing the whole spectrum was "
                "measured to lose more than it saved."
            )
        return note

    def _populate_correlation_tab(
        self,
        correlation_type: str,
        cross_peaks: list[CrossPeak],
        spectrum: SpectrumResult,
        x_label: str,
        y_label: str,
    ) -> None:
        table = self._correlation_tables[correlation_type]
        # No `_fill_tab` here either -- the plot paints its own empty
        # message and stops as soon as it has peaks.
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
