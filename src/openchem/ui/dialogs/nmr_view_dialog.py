from __future__ import annotations

from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

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

        layout = QVBoxLayout(self)
        layout.addWidget(self.view)
