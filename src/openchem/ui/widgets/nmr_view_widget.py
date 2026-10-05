from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QMenu,
    QMessageBox,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from openchem.chem import jcamp
from openchem.chem.engine import ChemistryEngine
from openchem.chem.nmr_export import export_jcamp, export_sdf
from openchem.chem.nmr_measured import NmrReference, read_nmr_reference
from openchem.chem.nmr_signals import (
    DEFAULT_FREQUENCY_MHZ,
    RESIDUAL_SOLVENT_PEAKS,
    SPECTROMETER_FREQUENCIES_MHZ,
    NMRSignal,
    align_mol_to_spectrum,
    build_nmr_signals,
    depiction_atoms,
)
from openchem.chem.tautomer_nmr import TautomerOverlay, tautomer_overlay
from openchem.domain.scientific_result import SpectrumResult, StructureSetResult, TautomerNmrResult
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.visualization import VisualizationLayer
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend
from openchem.ui.widgets.nmr_spectrum_widget import (
    DEFAULT_PALETTE,
    NMR_PALETTES,
    NmrSpectrumWidget,
    palette_hex,
)
from openchem.ui.widgets.scroll_safe import make_scroll_safe
from openchem.ui.widgets.sortable_item import SortableItem
from openchem.ui.widgets.tautomer_overlay_controls import TautomerOverlayControls

#: Column headers for the signal table, in display order. Deliberately NO
#: "Prediction quality" column, which is what MarvinSketch shows here.
#: Marvin can rate its own confidence because it has a HOSE-code
#: experimental reference database behind every number; nothing wired up
#: here does, so a rating would be invented rather than measured --
#: exactly the fabricated precision this project refuses elsewhere (the
#: hERG risk-factor checklist, the BBB/bioavailability approximations).
#: "Method" is the honest substitute: it says where the number came from
#: and lets the reader judge.
_TABLE_COLUMNS = ("Shift (ppm)", "Integration", "Multiplicity", "Coupling (Hz)", "Method")
#: The per-atom and per-coupling views of the same signals.
_ATOM_COLUMNS = ("Atom", "Shift (ppm)", "Multiplicity")
#: One row per (partner count, |J|) group of a signal; see `_populate_projections`.
_COUPLING_COLUMNS = ("Shift (ppm)", "Partners", "J (Hz)", "Source")
#: Nucleus combo display text, keyed by element symbol.
_ELEMENT_LABELS = {"H": "¹H", "C": "¹³C"}
#: The signal a table row, a 3D atom click, or a direct click selected --
#: the same colour `NmrSpectrumWidget`'s own highlighted-stick pen uses
#: (`QColor(214, 100, 20)` is this hex value), just as a string for the
#: SVG/CSS paths here rather than a `QColor`.
_HIGHLIGHT_COLOR = palette_hex(DEFAULT_PALETTE, "highlight")
#: An ordinary, unselected signal's atoms in the 3D view and 2D depiction.
_BASE_COLOR = "#9aa0a6"
#: A row's stable identity (its signal's atom indices), read back after a
#: sort to find which row is which -- row index stops meaning "this
#: signal" the moment `setSortingEnabled(True)` lets a header click
#: reorder rows out from under `self._signals`'s own order.
_ROW_IDENTITY_ROLE = Qt.ItemDataRole.UserRole + 2


@dataclass(frozen=True)
class NmrViewerSettings:
    """The persistent viewer settings that exist, as ONE value.

    **THE SINGLE SOURCE OF THE DEFAULTS.** Construction reads them, "Reset
    Settings" applies them, and a test asserts a freshly built viewer reports
    exactly them -- so a setting added to the toolbar without a default here
    fails loudly instead of quietly surviving a reset. Only settings that
    exist are listed: no placeholders for controls that are not built yet.
    One-shot ACTIONS (Reset Zoom, Copy Spectrum Image) are not settings, and
    neither is navigation (the zoom), which Reset Settings must not touch.
    """

    element: str = "H"
    frequency_mhz: float = DEFAULT_FREQUENCY_MHZ
    solvent: str | None = None
    unit: str = "ppm"
    label_mode: str = "shift"
    smooth: bool = False
    decoupled: bool = False
    integral: bool = False
    zoom_follow: bool = True
    legend: bool = False
    #: Draw the 2D structure's implicit hydrogens as atoms. View state only.
    explicit_hydrogens: bool = False
    #: One of `NMR_PALETTES`. Presentation only.
    palette: str = DEFAULT_PALETTE
    #: Display scale of an imported measured spectrum (the record itself is
    #: never scaled) and whether its peaks are marked.
    reference_scale: float = 1.0
    reference_peaks: bool = False


#: The defaults every viewer starts with and "Reset Settings" restores.
NMR_VIEWER_DEFAULTS = NmrViewerSettings()


class NmrViewWidget(QWidget):
    """The Marvin-parity NMR view: peak spectrum, signal table, and the
    shifts drawn on the structure, all wired to each other.

    Its own widget rather than another tab in `CalculatorInspectorDialog`,
    which is built around one-value-per-atom colouring -- an NMR result is
    grouped into signals, so per-atom colouring is the wrong shape for it.

    Clicking a peak, or a table row, or an atom in the 3D view all resolve
    to the same thing: an `NMRSignal`, which owns the full list of atoms
    contributing to it. That is what makes the highlight bidirectional
    without a separate atom->row index.
    """

    def __init__(
        self,
        engine: ChemistryEngine,
        backend: ViewerBackend | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._molblock: str = ""
        self._spectrum: SpectrumResult | None = None
        self._mol = None  # rdkit Mol aligned to the spectrum's numbering
        self._signals: list[NMRSignal] = []

        self._header_label = QLabel("", self)
        self._header_label.setWordWrap(True)

        # The honest state of spin-spin coupling for what's on screen --
        # see `_update_coupling_note`. A spectrum-level note rather than a
        # per-signal one: more discoverable (a user may never hover a
        # peak), and it is what distinguishes "this 'd' is unsplit because
        # no J was ever calculated" from "this 'd' is unsplit because the
        # coupling output failed to parse" from "real coupling IS being
        # shown, at this frequency" -- three states that look identical on
        # the plot otherwise.
        self._coupling_note_label = QLabel("", self)
        self._coupling_note_label.setWordWrap(True)
        self._coupling_note_label.setStyleSheet("color: #666;")

        # `make_scroll_safe` on every combo below: confirmed live
        # (OPENCHEM_DRIVE's wheel_trace/wheel steps) that a `QComboBox`
        # accepts a wheel event unconditionally, focus or not -- scrolling
        # PAST Nucleus/Frequency/Solvent on the way down this pop-out
        # silently changed whichever one the cursor happened to be over.
        self._scroll_safe_guards: list = []

        self._element_combo = QComboBox(self)
        self._element_combo.currentIndexChanged.connect(self._on_element_changed)
        self._scroll_safe_guards.append(make_scroll_safe(self._element_combo))

        self._svg_widget = QSvgWidget(self)
        # Small enough that the splitter below can give the spectrum --
        # the primary analytical view -- the majority of the space by
        # DEFAULT, which a large minimum here would have prevented
        # regardless of the splitter's own sizing: this was the exact
        # complaint that started Phase D. Still large enough to read a
        # modest structure; dragging the splitter can always make it
        # bigger.
        self._svg_widget.setMinimumSize(200, 160)

        self._backend: ViewerBackend = backend or Mol3DViewerBackend(self)
        self._backend.atoms_selected.connect(self._on_atoms_selected)
        # Fetched once and reused below (for the minimum size AND the
        # splitter) rather than calling `.widget()` again -- it is
        # documented as returning THE underlying widget, singular, but
        # nothing enforces that a second implementation actually caches
        # it the way `Mol3DViewerBackend` does.
        backend_widget = self._backend.widget()
        backend_widget.setMinimumSize(200, 160)

        self._spectrum_widget = NmrSpectrumWidget(parent=self)
        self._spectrum_widget.peak_clicked.connect(self._on_peak_clicked)

        self._table = QTableWidget(0, len(_TABLE_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_TABLE_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self._table.setMinimumHeight(80)

        # Two more VIEWS of the same signals (Marvin splits its table the
        # same way): per-atom and per-coupling. They are projections, never a
        # second dataset -- rebuilt from `self._signals` in
        # `_populate_projections`, and every row carries the owning signal's
        # stable identity (its atom indices), so a selection in any of the
        # three resolves to the SAME signal and never depends on a row number.
        self._atoms_table = self._make_projection_table(_ATOM_COLUMNS)
        self._couplings_table = self._make_projection_table(_COUPLING_COLUMNS)
        # Bound methods, not a lambda capturing `self`: the Qt-disposal guard
        # (tests/test_qt_object_disposal.py) forbids that shape.
        self._atoms_table.itemSelectionChanged.connect(self._on_atoms_row_selected)
        self._couplings_table.itemSelectionChanged.connect(self._on_couplings_row_selected)
        self._table_tabs = QTabWidget(self)
        self._table_tabs.addTab(self._table, "Signals")
        self._table_tabs.addTab(self._atoms_table, "Atoms")
        self._table_tabs.addTab(self._couplings_table, "Couplings")

        # Marvin's own NMR panel offers both. Neither changes a predicted
        # shift -- frequency only sets how far apart a multiplet's lines
        # fall in ppm, and the solvent peak is the solvent's, not the
        # sample's -- but both are what make a plot read like a real
        # spectrum instead of a bar chart.
        self._frequency_combo = QComboBox(self)
        for frequency in SPECTROMETER_FREQUENCIES_MHZ:
            self._frequency_combo.addItem(f"{frequency:g} MHz", frequency)
        self._frequency_combo.setCurrentIndex(
            list(SPECTROMETER_FREQUENCIES_MHZ).index(NMR_VIEWER_DEFAULTS.frequency_mhz)
        )
        self._frequency_combo.currentIndexChanged.connect(self._on_frequency_changed)
        self._scroll_safe_guards.append(make_scroll_safe(self._frequency_combo))

        self._solvent_combo = QComboBox(self)
        self._solvent_combo.addItem("None", None)
        for solvent in RESIDUAL_SOLVENT_PEAKS:
            self._solvent_combo.addItem(solvent, solvent)
        self._solvent_combo.currentIndexChanged.connect(self._on_solvent_changed)
        self._scroll_safe_guards.append(make_scroll_safe(self._solvent_combo))

        # Sticks are the exact data (zero-width, at each multiplet line);
        # smooth convolves the same lines with a Lorentzian so the plot
        # reads like a real trace. Neither is more "correct" -- see
        # `NmrSpectrumWidget`'s docstring -- so this is a display choice,
        # not a recompute.
        self._smooth_check = QCheckBox("Smooth rendering", self)
        self._smooth_check.toggled.connect(self._on_render_mode_toggled)
        # A pure display switch -- `NmrSpectrumWidget.set_decoupled` never
        # touches `coupling_groups`/`multiplicity`, so this computes
        # nothing new and stores no project state (see that method's own
        # docstring). Grouped with `_smooth_check` -- the two rendering-
        # mode toggles -- ahead of the independent integral/zoom checks.
        self._decoupled_check = QCheckBox("Decoupled", self)
        self._decoupled_check.toggled.connect(self._spectrum_widget.set_decoupled)
        self._integral_check = QCheckBox("Relative integral", self)
        self._integral_check.toggled.connect(self._spectrum_widget.set_show_integral)
        # Default on, matching Marvin's own "Zoom Follows Selection" --
        # a checkbox rather than always-on so it can be turned off if it
        # ever feels disruptive rather than helpful.
        self._zoom_follow_check = QCheckBox("Zoom to selection", self)
        self._zoom_follow_check.setChecked(NMR_VIEWER_DEFAULTS.zoom_follow)
        # A static key for the marks on the plot; off by default so the plot
        # is unchanged for anyone who does not ask for it.
        self._legend_check = QCheckBox("Legend", self)
        self._legend_check.toggled.connect(self._spectrum_widget.set_show_legend)
        # Structure-pane view state: never part of a signal, a result or a
        # fingerprint, and it draws a COPY of the molecule.
        self._palette_combo = QComboBox(self)
        for name in NMR_PALETTES:
            self._palette_combo.addItem(f"Colours: {name}", name)
        self._palette_combo.currentIndexChanged.connect(self._on_palette_changed)
        self._scroll_safe_guards.append(make_scroll_safe(self._palette_combo))
        # A measured spectrum beside the prediction. Its scale and peak marks
        # are view settings; the imported record itself is not a setting, so
        # Reset Settings leaves it (Clear Reference removes it).
        self._reference: NmrReference | None = None
        self._reference_scale_spin = QDoubleSpinBox(self)
        self._reference_scale_spin.setPrefix("Reference scale: ")
        self._reference_scale_spin.setRange(0.1, 10.0)
        self._reference_scale_spin.setSingleStep(0.1)
        self._reference_scale_spin.setValue(NMR_VIEWER_DEFAULTS.reference_scale)
        self._reference_scale_spin.valueChanged.connect(self._on_reference_scale_changed)
        self._reference_peaks_check = QCheckBox("Reference peaks", self)
        self._reference_peaks_check.toggled.connect(self._spectrum_widget.set_show_reference_peaks)
        self._reference_scale_spin.setEnabled(False)
        self._reference_peaks_check.setEnabled(False)
        self._reference_note_label = QLabel("", self)
        self._reference_note_label.setWordWrap(True)
        self._reference_note_label.setStyleSheet("color: #666;")
        self._reference_note_label.setVisible(False)
        # Tautomer peaks drawn over the spectrum, with their toggles and notes. Hidden until a tautomer NMR
        # result is attached (`set_tautomer_nmr`); view state like the reference, so Reset Settings leaves it.
        self._tautomer_overlay: TautomerOverlay | None = None
        self._tautomer_controls = TautomerOverlayControls(self._spectrum_widget, self)
        self._explicit_h_check = QCheckBox("Explicit H", self)
        self._explicit_h_check.toggled.connect(self._on_explicit_h_toggled)
        self._highlighted_atoms: list[int] = []

        # Display-only -- never recomputes or mutates a signal's own ppm
        # `shift`; see `NmrSpectrumWidget.set_display_unit`. Disabled
        # whenever the current spectrum is raw shielding (`_rebuild_
        # signals`), since σ has no reference-frequency relationship to
        # convert through.
        self._unit_combo = QComboBox(self)
        self._unit_combo.addItem("ppm", "ppm")
        self._unit_combo.addItem("Offset (Hz)", "hz")
        self._unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        self._scroll_safe_guards.append(make_scroll_safe(self._unit_combo))

        # None/Chemical shifts/Atom indices, applied identically to sticks
        # and smooth mode (see `NmrSpectrumWidget.set_label_mode`).
        # "Chemical shifts" matches today's always-on stick-mode default.
        self._labels_combo = QComboBox(self)
        self._labels_combo.addItem("Labels: Chemical shifts", "shift")
        self._labels_combo.addItem("Labels: Atom indices", "atom")
        self._labels_combo.addItem("Labels: None", "none")
        self._labels_combo.currentIndexChanged.connect(self._on_label_mode_changed)
        self._scroll_safe_guards.append(make_scroll_safe(self._labels_combo))

        # A QToolBar, not the QHBoxLayout this row used to be -- every
        # control below is the SAME widget, same attribute name, same
        # signal connection as before; this is a container swap, not a
        # rewire. Not movable/floatable: this toolbar lives inside a
        # docked panel widget, not a QMainWindow, and nothing about it
        # calls for the user being able to drag or detach it.
        # TWO rows. One toolbar overflowed into its "..." menu well before the
        # panel got narrow (seen on screen at 1300 px), hiding the newest
        # controls and both Reset actions. The top row holds what the spectrum
        # is OF (nucleus, frequency, solvent, unit, labels) and the actions;
        # the second holds the display options. Every control is still the
        # same widget with the same attribute name and connection.
        toolbar = QToolBar(self)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.addWidget(QLabel("Nucleus:", self))
        toolbar.addWidget(self._element_combo)
        toolbar.addWidget(QLabel("Frequency:", self))
        toolbar.addWidget(self._frequency_combo)
        toolbar.addWidget(QLabel("Solvent peak:", self))
        toolbar.addWidget(self._solvent_combo)
        toolbar.addWidget(QLabel("Unit:", self))
        toolbar.addWidget(self._unit_combo)
        toolbar.addWidget(self._labels_combo)
        # QToolBar has no QBoxLayout.addStretch() equivalent -- an
        # expanding spacer widget reproduces the old row's trailing
        # stretch, pushing the actions to the right, distinct from the
        # settings controls to their left.
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # Beside Reset Zoom but independent of it: settings are what the
        # controls say, the zoom is where the plot is looking.
        self._reset_settings_action = QAction("Reset Settings", self)
        self._reset_settings_action.setToolTip("Restore every viewer setting to its default (the zoom is kept)")
        self._reset_settings_action.triggered.connect(self.reset_settings)
        toolbar.addAction(self._reset_settings_action)

        self._reset_zoom_action = QAction("Reset Zoom", self)
        self._reset_zoom_action.setToolTip("Restore the full spectrum span")
        self._reset_zoom_action.triggered.connect(self._on_reset_zoom_clicked)
        toolbar.addAction(self._reset_zoom_action)

        self._copy_spectrum_action = QAction("Copy Spectrum Image", self)
        self._copy_spectrum_action.setToolTip("Copy the spectrum plot as an image")
        self._copy_spectrum_action.triggered.connect(self._on_copy_spectrum_image_clicked)
        toolbar.addAction(self._copy_spectrum_action)

        display_toolbar = QToolBar(self)
        display_toolbar.setMovable(False)
        display_toolbar.setFloatable(False)
        for control in (
            self._smooth_check,
            self._decoupled_check,
            self._integral_check,
            self._zoom_follow_check,
            self._legend_check,
            self._explicit_h_check,
            self._palette_combo,
        ):
            display_toolbar.addWidget(control)

        # A third row for the measured reference and export: the first two
        # already fill the width at 1300 px (seen on screen).
        reference_toolbar = QToolBar(self)
        reference_toolbar.setMovable(False)
        reference_toolbar.setFloatable(False)
        self._import_reference_action = QAction("Import Reference...", self)
        self._import_reference_action.setToolTip(
            "Draw a measured NMR spectrum (JCAMP-DX) behind the prediction; it never changes a prediction"
        )
        self._import_reference_action.triggered.connect(self._on_import_reference_clicked)
        reference_toolbar.addAction(self._import_reference_action)
        self._clear_reference_action = QAction("Clear Reference", self)
        self._clear_reference_action.setEnabled(False)
        self._clear_reference_action.triggered.connect(self.clear_reference)
        reference_toolbar.addAction(self._clear_reference_action)

        self._export_button = QToolButton(self)
        self._export_button.setText("Export")
        self._export_button.setToolTip("Write the predicted spectrum out (read from the data, not the screen)")
        self._export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        export_menu = QMenu(self._export_button)
        self._export_jcamp_action = export_menu.addAction("JCAMP-DX spectrum...")
        self._export_sdf_action = export_menu.addAction("SD file with shifts...")
        self._export_pdf_action = export_menu.addAction("PDF report...")
        self._export_jcamp_action.triggered.connect(self._on_export_jcamp_clicked)
        self._export_sdf_action.triggered.connect(self._on_export_sdf_clicked)
        self._export_pdf_action.triggered.connect(self._on_export_pdf_clicked)
        self._export_button.setMenu(export_menu)

        reference_toolbar.addWidget(self._reference_peaks_check)
        reference_toolbar.addWidget(self._reference_scale_spin)
        reference_spacer = QWidget(self)
        reference_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        reference_toolbar.addWidget(reference_spacer)
        reference_toolbar.addWidget(self._export_button)

        # Nested, not one flat splitter: the 2D/3D pair is its own
        # resizable pair before it is one pane of the outer one, so
        # either structure view can be widened without stealing space
        # from the spectrum or the table.
        self._structures_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._structures_splitter.addWidget(self._svg_widget)
        self._structures_splitter.addWidget(backend_widget)
        self._structures_splitter.setChildrenCollapsible(False)

        self._main_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._main_splitter.addWidget(self._structures_splitter)
        self._main_splitter.addWidget(self._spectrum_widget)
        self._main_splitter.addWidget(self._table_tabs)
        self._main_splitter.setChildrenCollapsible(False)
        # The spectrum is the primary analytical view; the structure
        # panes are assignment context and the table is the exact-value
        # detail layer -- so it gets the majority of both the initial
        # size AND any extra space from a later resize (`setSizes` fixes
        # the former, `setStretchFactor` the latter; neither alone
        # covers both).
        self._main_splitter.setStretchFactor(0, 1)
        self._main_splitter.setStretchFactor(1, 3)
        self._main_splitter.setStretchFactor(2, 1)
        self._main_splitter.setSizes([220, 480, 160])

        layout = QVBoxLayout(self)
        layout.addWidget(self._header_label)
        layout.addWidget(self._coupling_note_label)
        layout.addWidget(self._reference_note_label)
        layout.addWidget(self._tautomer_controls)
        layout.addWidget(toolbar)
        layout.addWidget(display_toolbar)
        layout.addWidget(reference_toolbar)
        layout.addWidget(self._main_splitter)

    def set_spectrum(
        self,
        molblock: str,
        spectrum: SpectrumResult,
        conformer_molblock: str | None = None,
    ) -> None:
        """`molblock` is the molecule's own (2D editor) structure, which the
        depiction is drawn from; `conformer_molblock` is an optional 3D
        conformer for the 3D pane. Atom indices are shared across all three
        because `Chem.AddHs` and RDKit's embedding both append hydrogens
        after the heavy atoms without reordering them -- the same invariant
        `CalculatorInspectorDialog` already relies on to colour its 2D and
        3D panes from one dataset.
        """
        self._molblock = molblock
        self._spectrum = spectrum
        self._mol = align_mol_to_spectrum(self._engine.mol_from_molblock(molblock), spectrum)

        self._header_label.setText(f"{spectrum.name} — {spectrum.units}")
        if conformer_molblock:
            self._backend.load_conformer(conformer_molblock)

        elements = sorted({spectrum.elements[index] for index in spectrum.values if index in spectrum.elements})
        self._element_combo.blockSignals(True)
        self._element_combo.clear()
        for element in elements:
            self._element_combo.addItem(_ELEMENT_LABELS.get(element, element), element)
        # 1H is what a chemist reads first, and the only nucleus this view's
        # multiplicity/integration columns are meaningful for.
        preferred = self._element_combo.findData("H")
        self._element_combo.setCurrentIndex(preferred if preferred >= 0 else 0)
        self._element_combo.blockSignals(False)
        self._rebuild_signals()

    def signals(self) -> list[NMRSignal]:
        return list(self._signals)

    def set_tautomer_nmr(self, result: TautomerNmrResult, distribution: StructureSetResult) -> TautomerOverlay:
        """Draw each tautomer's predicted peaks, and (when the distribution is validated and complete) their
        fast-exchange average, over this spectrum. `distribution` supplies the populations, labels and the
        structures the spectra's atom numbering refers to. Returns what is shown. Never touches a signal."""
        self._tautomer_overlay = tautomer_overlay(result, distribution)
        self._tautomer_controls.set_overlay(self._tautomer_overlay, self._current_element(), result.method_basis)
        return self._tautomer_overlay

    def clear_tautomer_nmr(self) -> None:
        self._tautomer_overlay = None
        self._tautomer_controls.clear()

    def current_tautomer_overlay(self) -> TautomerOverlay | None:
        return self._tautomer_overlay

    def tautomer_controls(self) -> TautomerOverlayControls:
        return self._tautomer_controls

    def current_settings(self) -> NmrViewerSettings:
        """What the controls say now, in the same shape as the defaults."""
        return NmrViewerSettings(
            element=self._current_element(),
            frequency_mhz=self._frequency_combo.currentData(),
            solvent=self._solvent_combo.currentData(),
            unit=self._unit_combo.currentData(),
            label_mode=self._labels_combo.currentData(),
            smooth=self._smooth_check.isChecked(),
            decoupled=self._decoupled_check.isChecked(),
            integral=self._integral_check.isChecked(),
            zoom_follow=self._zoom_follow_check.isChecked(),
            legend=self._legend_check.isChecked(),
            explicit_hydrogens=self._explicit_h_check.isChecked(),
            palette=self._palette_combo.currentData(),
            reference_scale=round(self._reference_scale_spin.value(), 6),
            reference_peaks=self._reference_peaks_check.isChecked(),
        )

    def apply_settings(self, settings: NmrViewerSettings) -> None:
        """Drives the REAL controls, so every handler runs exactly as for a
        user's click. Never touches the zoom (navigation, not a setting),
        though changing the nucleus necessarily re-fits the axis."""
        for combo, value in (
            (self._element_combo, settings.element),
            (self._frequency_combo, settings.frequency_mhz),
            (self._solvent_combo, settings.solvent),
            (self._unit_combo, settings.unit),
            (self._labels_combo, settings.label_mode),
            (self._palette_combo, settings.palette),
        ):
            index = combo.findData(value)
            if index >= 0:
                combo.setCurrentIndex(index)
        for check, value in (
            (self._smooth_check, settings.smooth),
            (self._decoupled_check, settings.decoupled),
            (self._integral_check, settings.integral),
            (self._zoom_follow_check, settings.zoom_follow),
            (self._legend_check, settings.legend),
            (self._explicit_h_check, settings.explicit_hydrogens),
            (self._reference_peaks_check, settings.reference_peaks),
        ):
            check.setChecked(value)

        self._reference_scale_spin.setValue(settings.reference_scale)

    def reset_settings(self) -> None:
        self.apply_settings(NMR_VIEWER_DEFAULTS)

    def _current_element(self) -> str:
        return self._element_combo.currentData() or "H"

    def _on_element_changed(self, _index: int) -> None:
        self._rebuild_signals()
        self._update_reference_note()

    def _on_frequency_changed(self, _index: int) -> None:
        self._spectrum_widget.set_frequency(self._frequency_combo.currentData())
        self._update_coupling_note()

    def _on_solvent_changed(self, _index: int) -> None:
        self._spectrum_widget.set_solvent(self._solvent_combo.currentData())

    def _on_render_mode_toggled(self, smooth: bool) -> None:
        self._spectrum_widget.set_render_mode("smooth" if smooth else "sticks")

    def _on_unit_changed(self, _index: int) -> None:
        self._spectrum_widget.set_display_unit(self._unit_combo.currentData())
        # The table's own Shift column/header must agree with the plot --
        # it is not re-derived automatically, since it is rendered
        # independently of `NmrSpectrumWidget`'s paintEvent.
        self._populate_table()

    def _on_label_mode_changed(self, _index: int) -> None:
        self._spectrum_widget.set_label_mode(self._labels_combo.currentData())

    # -- measured reference ------------------------------------------------

    def _on_import_reference_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open measured NMR spectrum", "",
            "JCAMP-DX spectra (*.jdx *.dx *.jcm *.jcamp);;All files (*)",
        )
        if path:
            self.load_reference_file(path)

    def load_reference_file(self, path: str) -> NmrReference | None:
        """Reads and draws a measured spectrum. Every failure is SHOWN, never
        absorbed into an empty plot: JCAMP-DX varies by vendor and a file that
        will not load is information worth the user's eyes."""
        try:
            reference = read_nmr_reference(Path(path).read_bytes(), Path(path).name)
        except jcamp.JcampError as exc:
            QMessageBox.warning(self, "Could not read spectrum", str(exc))
            return None
        except OSError as exc:
            QMessageBox.warning(self, "Could not open file", str(exc))
            return None
        self.set_reference(reference)
        return reference

    def set_reference(self, reference: NmrReference | None) -> None:
        self._reference = reference
        self._spectrum_widget.set_reference(reference)
        present = reference is not None
        self._clear_reference_action.setEnabled(present)
        self._reference_scale_spin.setEnabled(present)
        self._reference_peaks_check.setEnabled(present)
        self._update_reference_note()

    def clear_reference(self) -> None:
        self.set_reference(None)

    def reference(self) -> NmrReference | None:
        return self._reference

    def _on_reference_scale_changed(self, value: float) -> None:
        self._spectrum_widget.set_reference_scale(value)

    def _update_reference_note(self) -> None:
        reference = self._reference
        if reference is None:
            self._reference_note_label.setVisible(False)
            return
        text = f"Reference: {reference.describe()}"
        if not self._spectrum_widget.reference_drawn():
            text += (
                f" -- not drawn: it is a {reference.nucleus} spectrum and the viewer is showing "
                f"{self._current_element()} (or a raw shielding axis)."
            )
        self._reference_note_label.setText(text)
        self._reference_note_label.setVisible(True)

    # -- export ------------------------------------------------------------------

    def _export_parameters(self) -> dict:
        return {
            "frequency_mhz": self._frequency_combo.currentData(),
            "element": self._current_element(),
            "solvent": self._solvent_combo.currentData() or "",
            "method": self._spectrum.method if self._spectrum is not None else "",
        }

    def export_jcamp_text(self) -> str:
        return export_jcamp(
            self._signals, decoupled=self._decoupled_check.isChecked(), **self._export_parameters()
        )

    def export_sdf_text(self) -> str:
        if self._mol is None:
            raise ValueError("There is no structure to export.")
        return export_sdf(self._mol, self._signals, **self._export_parameters())

    def export_pdf(self, path: str) -> bool:
        """A one-page report: header, the spectrum plot as drawn (the figure
        is a rendering; everything else is read from the signal list) and the
        signal table."""
        from PySide6.QtCore import QMarginsF, QRectF
        from PySide6.QtGui import QFont, QPageSize, QPainter, QPdfWriter

        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageMargins(QMarginsF(15, 15, 15, 15))
        painter = QPainter(writer)
        if not painter.isActive():
            return False
        width = writer.width()
        y = 0
        body = QFont("Sans Serif", 9)
        painter.setFont(QFont("Sans Serif", 14, QFont.Weight.Bold))
        painter.drawText(QRectF(0, y, width, 400), self._header_label.text() or "NMR spectrum")
        y += 420
        painter.setFont(body)
        parameters = self._export_parameters()
        for line in (
            f"{parameters['element']} NMR at {parameters['frequency_mhz']:g} MHz"
            + (f", {parameters['solvent']}" if parameters["solvent"] else ""),
            "PREDICTED, not a measurement. First-order multiplets; no second-order effects.",
        ):
            painter.drawText(QRectF(0, y, width, 220), line)
            y += 220
        pixmap = self._spectrum_widget.grab()
        height = int(width * pixmap.height() / max(pixmap.width(), 1))
        painter.drawPixmap(QRectF(0, y, width, height).toRect(), pixmap)
        y += height + 200
        painter.setFont(QFont("Sans Serif", 9, QFont.Weight.Bold))
        columns = (0, width * 0.2, width * 0.4, width * 0.6)
        for x, text in zip(columns, ("Shift (ppm)", "Integration", "Multiplicity", "Coupling (Hz)")):
            painter.drawText(QRectF(x, y, width * 0.2, 220), text)
        y += 240
        painter.setFont(body)
        for signal in self._signals:
            cells = (
                f"{signal.shift:.3f}", f"{signal.integration}{signal.element}", signal.multiplicity,
                ", ".join(f"{hz:.1f}" for hz in signal.coupling_hz) or "-",
            )
            for x, text in zip(columns, cells):
                painter.drawText(QRectF(x, y, width * 0.2, 220), text)
            y += 220
            if y > writer.height() - 300:
                writer.newPage()
                y = 0
        painter.end()
        return True

    def _save_text(self, caption: str, pattern: str, text_factory) -> None:
        path, _ = QFileDialog.getSaveFileName(self, caption, "", pattern)
        if not path:
            return
        try:
            Path(path).write_text(text_factory(), encoding="utf-8")
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Could not export", str(exc))

    def _on_export_jcamp_clicked(self) -> None:
        self._save_text("Export JCAMP-DX", "JCAMP-DX (*.jdx);;All files (*)", self.export_jcamp_text)

    def _on_export_sdf_clicked(self) -> None:
        self._save_text("Export SD file", "SD file (*.sdf);;All files (*)", self.export_sdf_text)

    def _on_export_pdf_clicked(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF report", "", "PDF (*.pdf)")
        if path and not self.export_pdf(path):
            QMessageBox.warning(self, "Could not export", "The PDF could not be written.")

    def _on_palette_changed(self, _index: int) -> None:
        self._spectrum_widget.set_palette(self._palette_combo.currentData())
        # The structure panes colour the selected signal too, and must agree.
        self._render_structure(self._highlighted_atoms)

    def _highlight_hex(self) -> str:
        return palette_hex(self._palette_combo.currentData() or DEFAULT_PALETTE, "highlight")

    def _on_explicit_h_toggled(self, _checked: bool) -> None:
        self._render_structure(self._highlighted_atoms)

    def _on_reset_zoom_clicked(self) -> None:
        self._spectrum_widget.reset_view()

    def _on_copy_spectrum_image_clicked(self) -> None:
        """Copies the spectrum PLOT only, not the structure panes or the
        table -- Marvin's own "copy any panel as an image" is ambiguous
        about scope; this picks the one Marvin wording actually calls the
        "spectrum" and names the action accordingly."""
        QApplication.clipboard().setPixmap(self._spectrum_widget.grab())

    def _rebuild_signals(self) -> None:
        if self._spectrum is None or self._mol is None:
            return
        element = self._current_element()
        self._signals = build_nmr_signals(self._mol, self._spectrum, element)
        # σ, not δ, until the result has been referenced: see
        # `NmrSpectrumWidget.set_signals` for why the two cannot share an axis.
        shielding = self._spectrum.spectrum_type == "nmr_raw_shielding"
        symbol = "σ" if shielding else "δ"
        self._spectrum_widget.set_signals(
            self._signals,
            # No unit baked in here -- `NmrSpectrumWidget` owns its own
            # unit suffix (ppm/Hz toggle), see `set_signals`'s docstring.
            x_label=f"{_ELEMENT_LABELS.get(element, element)} {symbol}",
            shielding=shielding,
        )
        # Hz is only meaningful for a referenced chemical shift -- raw σ
        # has no reference-frequency relationship to convert through.
        # `NmrSpectrumWidget` already goes inert on its own in this case
        # (`_effective_unit`), but the control itself is disabled too
        # rather than left clickable with no visible effect.
        if element in ("H", "C"):
            self._spectrum_widget.set_tautomer_trace_element(element)
        self._unit_combo.setEnabled(not shielding)
        self._unit_combo.setToolTip(
            "Hz display needs a referenced chemical shift; raw shielding has "
            "no reference-frequency relationship to convert through."
            if shielding
            else ""
        )
        self._populate_table()
        self._render_structure(highlighted=[])
        self._update_coupling_note()

    def _update_coupling_note(self) -> None:
        """Says plainly which of four states this element's signals are
        in, rather than leaving a "d" next to an unsplit stick to read as
        a defect. Priority, highest first: a genuine parser failure beats
        everything (something broke, not "not requested"); a visible
        non-singlet signal with no real J beats a generic positive
        message (the gap is the thing worth saying); real coupling data,
        confirmed present -- with a richer variant when any signal's
        `coupling_groups` needed symmetry completion (see
        `nmr_signals._coupling_groups_hz`), since a 2-of-3 averaged value
        must never read the same as a 3-of-3 one; otherwise nothing to say
        (every signal here is a genuine singlet, or this element has no
        multiplet concept at all -- 13C is always reported decoupled).
        """
        if self._spectrum is None:
            self._coupling_note_label.setText("")
            return
        coupling_error = getattr(self._spectrum, "coupling_error", None)
        couplings = getattr(self._spectrum, "couplings", None)
        if coupling_error:
            self._coupling_note_label.setText(
                f"Spin-spin coupling was requested, but ORCA's output could not be "
                f"parsed ({coupling_error}) -- multiplet spacing is not shown."
            )
            return
        missing = any(signal.multiplicity != "s" and not signal.coupling_hz for signal in self._signals)
        if missing:
            self._coupling_note_label.setText(
                "Multiplicity is predicted from connectivity; spin-spin coupling was "
                "not calculated for this run, so multiplet spacing is not shown."
            )
            return
        if couplings:
            if any(signal.coupling_groups_inferred for signal in self._signals):
                self._coupling_note_label.setText(
                    f"Spin-spin coupling calculated; multiplet spacing shown at "
                    f"{self._frequency_combo.currentText()} -- one or more multiplets "
                    f"include a symmetry-completed coupling value because ORCA did not "
                    f"report every equivalent partner."
                )
                return
            self._coupling_note_label.setText(
                f"Spin-spin coupling calculated; multiplet spacing shown at "
                f"{self._frequency_combo.currentText()}."
            )
            return
        self._coupling_note_label.setText("")

    def _populate_table(self) -> None:
        method = self._spectrum.method if self._spectrum is not None else ""
        raw = self._spectrum is not None and self._spectrum.spectrum_type == "nmr_raw_shielding"
        if raw:
            header_text = "Shielding σ (ppm)"
        elif self._spectrum_widget.unit_suffix() == "Hz":
            # Not "Shift (Hz)" -- a chemical shift is fundamentally a
            # dimensionless ppm quantity; this column is showing the
            # FREQUENCY OFFSET from the reference, a different (if
            # related) number.
            header_text = "Offset (Hz)"
        else:
            header_text = _TABLE_COLUMNS[0]
        self._table.setHorizontalHeaderItem(0, QTableWidgetItem(header_text))
        self._table.blockSignals(True)
        # OFF during population: Qt would otherwise re-sort after every
        # single `setItem`, scrambling row/signal correspondence as the
        # table fills. This also IS the "sort order resets on a new
        # spectrum" behaviour -- rows are always inserted in
        # `self._signals`'s own order, so a fresh spectrum starts
        # unsorted regardless of how the previous one was left.
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._signals))
        for row, signal in enumerate(self._signals):
            # No coupling data is an em dash, not "0" or a guessed typical
            # J -- and sorts BELOW every real value (`-inf`), grouping the
            # "nothing calculated" rows at one end rather than scattering
            # them by string order.
            coupling_text = ", ".join(f"{hz:.1f}" for hz in signal.coupling_hz) or "—"
            coupling_sort = signal.coupling_hz[0] if signal.coupling_hz else float("-inf")

            # Sort value is always the raw ppm, regardless of the display
            # unit -- Hz is a monotonic function of ppm at a fixed
            # frequency/nucleus, so the row ORDER is identical either way;
            # only the printed text changes.
            shift_item = SortableItem(self._spectrum_widget.format_shift(signal.shift), signal.shift)
            shift_item.setData(_ROW_IDENTITY_ROLE, tuple(signal.atom_indices))
            items = (
                shift_item,
                SortableItem(f"{signal.integration}{signal.element}", signal.integration),
                QTableWidgetItem(signal.multiplicity),
                SortableItem(coupling_text, coupling_sort),
                QTableWidgetItem(method),
            )
            for column, item in enumerate(items):
                self._table.setItem(row, column, item)
        # Without this, `setSortingEnabled(True)` re-applies whatever
        # sort indicator the header already carries -- measured: a
        # BRAND NEW `QHeaderView`'s own default is (section 0,
        # DESCENDING), not "no sort", so a never-before-sorted table's
        # very first population would otherwise come up sorted anyway.
        # `-1` means no column, which leaves this population's natural
        # (`self._signals`'s own) order alone.
        self._table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self._table.setSortingEnabled(True)
        self._table.blockSignals(False)
        self._populate_projections()

    def _make_projection_table(self, columns: tuple[str, ...]) -> QTableWidget:
        table = QTableWidget(0, len(columns), self)
        table.setHorizontalHeaderLabels(columns)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setMinimumHeight(80)
        return table

    def _populate_projections(self) -> None:
        """Rebuilds the Atoms and Couplings views from `self._signals`.

        Atom numbers are the app-wide one-based display numbers (`index + 1`,
        as the Atom Inspector and the spectrum's own atom labels use). A
        coupling row is one (partner count, |J|) group of a signal, with
        whether its value was symmetry-completed, so a signal with no
        calculated coupling simply has no rows here rather than a guessed one.
        """
        unit_text = self._spectrum_widget.format_shift
        atoms: list[tuple[tuple[int, ...], tuple[str, ...]]] = []
        couplings: list[tuple[tuple[int, ...], tuple[str, ...]]] = []
        for signal in self._signals:
            identity = tuple(signal.atom_indices)
            for atom_index in signal.atom_indices:
                atoms.append((identity, (str(atom_index + 1), unit_text(signal.shift), signal.multiplicity)))
            for count, hz in signal.coupling_groups:
                source = "symmetry-completed" if signal.coupling_groups_inferred else "calculated"
                couplings.append((identity, (unit_text(signal.shift), str(count), f"{hz:.1f}", source)))
        for table, rows in ((self._atoms_table, atoms), (self._couplings_table, couplings)):
            table.blockSignals(True)
            table.setRowCount(len(rows))
            for row, (identity, cells) in enumerate(rows):
                for column, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    item.setData(_ROW_IDENTITY_ROLE, identity)
                    table.setItem(row, column, item)
            table.blockSignals(False)

    def _on_atoms_row_selected(self) -> None:
        self._on_projection_selected(self._atoms_table)

    def _on_couplings_row_selected(self) -> None:
        self._on_projection_selected(self._couplings_table)

    def _on_projection_selected(self, table: QTableWidget) -> None:
        rows = {index.row() for index in table.selectedIndexes()}
        if len(rows) != 1:
            return
        item = table.item(rows.pop(), 0)
        identity = item.data(_ROW_IDENTITY_ROLE) if item is not None else None
        signal = next((s for s in self._signals if tuple(s.atom_indices) == identity), None)
        if signal is not None:
            self._select_signal(signal)

    def _select_projection_rows(self, signal: NMRSignal) -> None:
        """Marks the signal's first row in each projection (no re-entry)."""
        target = tuple(signal.atom_indices)
        for table in (self._atoms_table, self._couplings_table):
            table.blockSignals(True)
            table.clearSelection()
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item is not None and item.data(_ROW_IDENTITY_ROLE) == target:
                    table.selectRow(row)
                    break
            table.blockSignals(False)

    def _row_for_signal(self, signal: NMRSignal) -> int | None:
        """The row currently showing `signal`, by its stable identity --
        never by `self._signals.index(signal)`, which stops meaning
        anything once a header click has reordered the rows."""
        target = tuple(signal.atom_indices)
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(_ROW_IDENTITY_ROLE) == target:
                return row
        return None

    def _render_structure(self, highlighted: list[int]) -> None:
        if self._mol is None or not self._molblock:
            return
        self._highlighted_atoms = list(highlighted)
        highlighted_set = set(highlighted)
        atom_labels: dict[int, str] = {}
        atom_colors: dict[int, str] = {}
        for signal in self._signals:
            for atom_index in depiction_atoms(self._mol, signal):
                # A carbon bearing two diastereotopic protons owns two
                # signals; both shifts are shown rather than one silently
                # winning.
                label = f"{signal.shift:.2f}"
                existing = atom_labels.get(atom_index)
                atom_labels[atom_index] = f"{existing}/{label}" if existing else label
                if highlighted_set & set(signal.atom_indices):
                    atom_colors[atom_index] = self._highlight_hex()
        svg = self._engine.render_2d_svg(
            self._molblock,
            atom_colors or None,
            atom_labels or None,
            explicit_hydrogens=self._explicit_h_check.isChecked(),
        )
        self._svg_widget.load(svg.encode("utf-8"))

        # The 3D pane carries explicit hydrogens, so it highlights the real
        # protons rather than their heavy parents. Every signal atom gets a
        # neutral base colour, not just the selected ones: the 3Dmol.js
        # backend treats an empty `atom_colors` as "clear the layer", which
        # would take the shift labels down with it and leave the 3D pane
        # blank until the user happened to click a peak.
        layer = VisualizationLayer(
            name=self._spectrum.name if self._spectrum else "NMR",
            atom_colors={
                index: self._highlight_hex() if index in highlighted_set else _BASE_COLOR
                for signal in self._signals
                for index in signal.atom_indices
            },
            atom_labels={
                index: f"{signal.shift:.2f}" for signal in self._signals for index in signal.atom_indices
            },
        )
        try:
            self._backend.apply_visualization(layer)
        except NotImplementedError:
            # Optional capability (see ViewerBackend) -- a backend without it
            # still shows the structure, just without the shift labels.
            pass

    def _select_signal(self, signal: NMRSignal | None) -> None:
        if signal is None:
            return
        self._spectrum_widget.set_highlighted_atoms(signal.atom_indices)
        if self._zoom_follow_check.isChecked():
            self._spectrum_widget.zoom_to_signal(signal)
        self._render_structure(highlighted=signal.atom_indices)
        row = self._row_for_signal(signal)
        if row is not None:
            self._table.blockSignals(True)
            self._table.selectRow(row)
            self._table.blockSignals(False)
        self._select_projection_rows(signal)

    def _signal_owning(self, atom_indices: list[int]) -> NMRSignal | None:
        wanted = set(atom_indices)
        for signal in self._signals:
            if wanted & set(signal.atom_indices):
                return signal
        return None

    def _on_peak_clicked(self, atom_indices: list[int]) -> None:
        self._select_signal(self._signal_owning(atom_indices))

    def _on_table_selection_changed(self) -> None:
        rows = {index.row() for index in self._table.selectedIndexes()}
        if len(rows) != 1:
            return
        item = self._table.item(rows.pop(), 0)
        identity = item.data(_ROW_IDENTITY_ROLE) if item is not None else None
        signal = next((s for s in self._signals if tuple(s.atom_indices) == identity), None)
        if signal is not None:
            self._select_signal(signal)

    def _on_atoms_selected(self, atom_indices: list[int]) -> None:
        """A 3D atom click selects the signal that atom belongs to -- the
        inbound half of the bidirectional link. Silently ignores an atom
        with no signal (a carbon in a 1H view, say)."""
        self._select_signal(self._signal_owning(list(atom_indices)))
