from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from openchem.chem.engine import ChemistryEngine
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import SpectrumResult
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.widgets.nmr_view_widget import NmrViewWidget


class NmrViewDialog(QDialog):
    """Hosts `NmrViewWidget` for a spectrum opened from the Property Panel.

    Separate from `CalculatorInspectorDialog` on purpose: that dialog's job
    is one colour-scaled value per atom, and an NMR result is grouped into
    signals with integrations and multiplicities, which that layout has
    nowhere to put.
    """

    def __init__(
        self,
        engine: ChemistryEngine,
        molecule: MoleculeModel,
        spectrum: SpectrumResult,
        conformer_molblock: str | None,
        backend: ViewerBackend | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"NMR — {molecule.display_name}")
        self.resize(900, 720)

        self.view = NmrViewWidget(engine, backend=backend, parent=self)
        self.view.set_spectrum(molecule.molblock, spectrum, conformer_molblock)
        self._spectrum = spectrum
        self._status = QLabel("", self)

        # Two copies, because they are genuinely different data. The
        # SIGNAL list is what goes in a paper's experimental section
        # (grouped, with integrations and multiplicities); the raw
        # per-nucleus shifts are what you re-analyse elsewhere. Offering
        # only one would send someone back to retyping the other.
        copy_signals = QPushButton("Copy Signals", self)
        copy_signals.setToolTip("Shift, integration, multiplicity and J for each signal.")
        copy_signals.clicked.connect(self._on_copy_signals)
        copy_raw = QPushButton("Copy Raw Shifts", self)
        copy_raw.setToolTip("The per-nucleus values behind the signal list.")
        copy_raw.clicked.connect(self._on_copy_raw)

        actions = QHBoxLayout()
        actions.addWidget(copy_signals)
        actions.addWidget(copy_raw)
        actions.addStretch(1)
        actions.addWidget(self._status)

        layout = QVBoxLayout(self)
        layout.addWidget(self.view)
        layout.addLayout(actions)

    def signals_text(self) -> str:
        """Tab-separated, so it pastes into a spreadsheet as columns."""
        lines = ["Shift (ppm)\tIntegration\tMultiplicity\tJ (Hz)"]
        for signal in self.view.signals():
            coupling = ", ".join(f"{hz:.1f}" for hz in signal.coupling_hz)
            lines.append(
                f"{signal.shift:.2f}\t{signal.integration}{signal.element}\t"
                f"{signal.multiplicity}\t{coupling}"
            )
        return "\n".join(lines)

    def _on_copy_signals(self) -> None:
        QGuiApplication.clipboard().setText(self.signals_text())
        self._status.setText("Signals copied.")

    def _on_copy_raw(self) -> None:
        from openchem.ui.result_clipboard import result_to_text

        QGuiApplication.clipboard().setText(result_to_text(self._spectrum))
        self._status.setText("Raw shifts copied.")
