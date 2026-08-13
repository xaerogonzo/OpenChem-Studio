from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from openchem.domain.report import ReportResult
from openchem.ui.widgets.fact_view import FactView
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend


class SpatialResultDialog(QDialog):
    """A shape-valued result on a 3D model -- Marvin's dipole popup, ours.

    Shown for a `ReportResult` whose producer declared `spatial`
    annotations: the conformer with the annotation drawn on it, and the
    same `FactView` the plain details dialog uses underneath, so search,
    evidence, limitations and export are not lost by gaining a picture.

    **The Calculator Inspector is deliberately NOT extended for this.**
    Its machinery -- declared totals, balance text, per-atom surfaces, the
    2D heat map -- is per-atom-specific, and this project's file records
    that panel family as the one an out-of-app harness has misdescribed
    six times. A result with a vector and no per-atom values gets a small
    dialog of its own.

    **The frame is safe by construction and still carries a caveat.** The
    dialog loads the molecule's STORED conformer -- the frame the
    annotation's coordinates are in -- so no transform exists to get
    wrong. What it cannot prove is that the stored conformer is the one
    the calculator ran on: a result computed before conformers were
    regenerated pairs old numbers with a new geometry, and a vector on
    the wrong conformer looks perfectly reasonable. The caveat states the
    assumption rather than letting the picture claim more authority than
    the result it draws; result-conformer identity tracking is its own
    piece of work, shared with the per-atom inspector.
    """

    def __init__(
        self,
        report: ReportResult,
        conformer_molblock: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(report.name)
        self.resize(560, 720)

        self._backend = Mol3DViewerBackend(self)
        self._backend.load_conformer(conformer_molblock)
        # After the load, exactly as the state machine wants: a load drops
        # pending shapes, so shapes for THIS conformer follow it.
        self._backend.apply_shapes(report.spatial)

        caveat = QLabel(
            "Drawn on the molecule's stored conformer -- the geometry this "
            "result's coordinates are in. If conformers have been regenerated "
            "since this was calculated, rerun the calculator before reading "
            "the picture.",
            self,
        )
        caveat.setWordWrap(True)

        facts = FactView(self)
        facts.set_report(report, report.name)

        layout = QVBoxLayout(self)
        # **Stretch 2:1 in the viewer's favour, and not zero on the
        # facts.** A QWebEngineView and a QLabel both report Preferred,
        # and an even split once left this app's 3D viewer half the size
        # it should be with a one-line label holding the rest.
        layout.addWidget(self._backend.widget(), 2)
        layout.addWidget(caveat, 0)
        layout.addWidget(facts, 1)
