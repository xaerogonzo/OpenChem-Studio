from __future__ import annotations

from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.engine import ChemistryEngine
from openchem.chem.nmr_signals import NMRSignal, align_mol_to_spectrum, build_nmr_signals, depiction_atoms
from openchem.domain.scientific_result import SpectrumResult
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.visualization import VisualizationLayer
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend
from openchem.ui.widgets.nmr_spectrum_widget import NmrSpectrumWidget

# Deliberately NO "Prediction quality" column, which is what MarvinSketch
# shows here. Marvin can rate its own confidence because it has a HOSE-code
# experimental reference database behind every number; nothing wired up here
# does, so a rating would be invented rather than measured -- exactly the
# fabricated precision this project refuses elsewhere (the hERG risk-factor
# checklist, the BBB/bioavailability approximations). "Method" is the honest
# substitute: it says where the number came from and lets the reader judge.
_TABLE_COLUMNS = ("Shift (ppm)", "Integration", "Multiplicity", "Coupling (Hz)", "Method")
_ELEMENT_LABELS = {"H": "¹H", "C": "¹³C"}
_HIGHLIGHT_COLOR = "#d66414"
_BASE_COLOR = "#9aa0a6"


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

        self._element_combo = QComboBox(self)
        self._element_combo.currentIndexChanged.connect(self._on_element_changed)

        self._svg_widget = QSvgWidget(self)
        self._svg_widget.setMinimumSize(360, 300)

        self._backend: ViewerBackend = backend or Mol3DViewerBackend(self)
        self._backend.atoms_selected.connect(self._on_atoms_selected)

        self._spectrum_widget = NmrSpectrumWidget(parent=self)
        self._spectrum_widget.peak_clicked.connect(self._on_peak_clicked)

        self._table = QTableWidget(0, len(_TABLE_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_TABLE_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)

        element_row = QHBoxLayout()
        element_row.addWidget(QLabel("Nucleus:", self))
        element_row.addWidget(self._element_combo)
        element_row.addStretch()

        structures_row = QHBoxLayout()
        structures_row.addWidget(self._svg_widget)
        structures_row.addWidget(self._backend.widget())

        layout = QVBoxLayout(self)
        layout.addWidget(self._header_label)
        layout.addLayout(element_row)
        layout.addLayout(structures_row)
        layout.addWidget(self._spectrum_widget)
        layout.addWidget(self._table)

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

    def _current_element(self) -> str:
        return self._element_combo.currentData() or "H"

    def _on_element_changed(self, _index: int) -> None:
        self._rebuild_signals()

    def _rebuild_signals(self) -> None:
        if self._spectrum is None or self._mol is None:
            return
        element = self._current_element()
        self._signals = build_nmr_signals(self._mol, self._spectrum, element)
        self._spectrum_widget.set_signals(
            self._signals, x_label=f"{_ELEMENT_LABELS.get(element, element)} δ (ppm)"
        )
        self._populate_table()
        self._render_structure(highlighted=[])

    def _populate_table(self) -> None:
        method = self._spectrum.method if self._spectrum is not None else ""
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._signals))
        for row, signal in enumerate(self._signals):
            values = (
                f"{signal.shift:.2f}",
                f"{signal.integration}{signal.element}",
                signal.multiplicity,
                # An em dash, not "0" or a guessed typical J: no coupling
                # data means no coupling data.
                ", ".join(f"{hz:.1f}" for hz in signal.coupling_hz) or "—",
                method,
            )
            for column, text in enumerate(values):
                self._table.setItem(row, column, QTableWidgetItem(text))
        self._table.blockSignals(False)

    def _render_structure(self, highlighted: list[int]) -> None:
        if self._mol is None or not self._molblock:
            return
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
                    atom_colors[atom_index] = _HIGHLIGHT_COLOR
        svg = self._engine.render_2d_svg(self._molblock, atom_colors or None, atom_labels or None)
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
                index: _HIGHLIGHT_COLOR if index in highlighted_set else _BASE_COLOR
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
        self._render_structure(highlighted=signal.atom_indices)
        row = self._signals.index(signal)
        self._table.blockSignals(True)
        self._table.selectRow(row)
        self._table.blockSignals(False)

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
        if len(rows) == 1:
            self._select_signal(self._signals[rows.pop()])

    def _on_atoms_selected(self, atom_indices: list[int]) -> None:
        """A 3D atom click selects the signal that atom belongs to -- the
        inbound half of the bidirectional link. Silently ignores an atom
        with no signal (a carbon in a 1H view, say)."""
        self._select_signal(self._signal_owning(list(atom_indices)))
