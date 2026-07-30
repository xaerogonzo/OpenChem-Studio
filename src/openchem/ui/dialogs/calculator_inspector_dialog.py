from __future__ import annotations

from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState, ScientificResult
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import PerAtomDataset
from openchem.ui.visualization import build_visualization_layer
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend


class _CalculatorResultView(QWidget):
    """One calculator result's Marvin-style inspection: overall value, a
    2D-colored-and-numbered depiction of the molecule's own editor
    structure, and a 3D-colored-and-numbered view -- all built from the
    SAME `VisualizationLayer` (`build_visualization_layer`) so the 2D and
    3D renderings are visually consistent, not two independent color/label
    choices for the same data.
    """

    def __init__(
        self,
        engine: ChemistryEngine,
        molecule: MoleculeModel,
        result: ScientificResult,
        conformer_molblock: str | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layer = build_visualization_layer(result, include_labels=True)

        # Sum of the per-atom contributions IS the molecular total for
        # every PerAtomDataset this dialog shows today (Crippen LogP/MR
        # contributions and Gasteiger partial charges are additive by
        # construction) -- no separate lookup into the scalar descriptor
        # set needed, and this stays correct for any future additive
        # per-atom property without extra wiring.
        #
        # Deliberately NOT attempted for a SpectrumResult (Phase 23):
        # summing chemical shifts is chemically meaningless, so a spectrum
        # gets no summary line at all rather than a misleading total or a
        # bare "Overall: n/a" that reads like something failed.
        # Both PerAtomDataset and SpectrumResult carry `units`, so the
        # legend below gets its suffix either way -- only the *total* is
        # PerAtomDataset-only.
        units = getattr(result, "units", "")
        units_suffix = f" {units}" if units else ""
        total: float | None = None
        if isinstance(result, PerAtomDataset) and result.values:
            total = sum(result.values.values())

        if result.cache_state == CacheState.FAILED:
            summary_text = result.error or "Failed"
        elif total is not None:
            summary_text = f"Overall: {total:.4g}{units_suffix}"
        else:
            summary_text = ""
        summary_label = QLabel(summary_text, self)
        summary_label.setWordWrap(True)
        summary_label.setVisible(bool(summary_text))

        svg_widget = QSvgWidget(self)
        if molecule.molblock and layer is not None:
            svg = engine.render_2d_svg(molecule.molblock, layer.atom_colors, layer.atom_labels)
            svg_widget.load(svg.encode("utf-8"))
        svg_widget.setMinimumSize(360, 320)

        self._viewer3d = Mol3DViewerBackend(self)
        if conformer_molblock and layer is not None:
            self._viewer3d.load_conformer(conformer_molblock)
            self._viewer3d.apply_visualization(layer)

        legend_label = QLabel(self)
        if layer is not None and layer.color_scale is not None:
            legend_label.setText(
                f"{layer.color_scale.domain_min:.3f} to {layer.color_scale.domain_max:.3f}{units_suffix}"
            )
        elif not conformer_molblock:
            legend_label.setText("No conformer generated yet -- 3D view is empty.")

        views_row = QHBoxLayout()
        views_row.addWidget(svg_widget)
        views_row.addWidget(self._viewer3d.widget())

        layout = QVBoxLayout(self)
        layout.addWidget(summary_label)
        layout.addLayout(views_row)
        layout.addWidget(legend_label)


class CalculatorInspectorDialog(QDialog):
    """Marvin-style calculator-result inspector -- overall value plus 2D-
    and 3D-colored-and-numbered depictions for ONE calculator's result.
    Opened from the Property Panel's per-category "Open [Calculator]..."
    row, after that calculator's settings dialog (if it has parameters).
    Named "Calculator" rather than "Property" since it can show results
    from any registered `CalculatorRegistry` entry, not just classic
    scalar/per-atom descriptors.
    """

    def __init__(
        self,
        engine: ChemistryEngine,
        molecule: MoleculeModel,
        result: ScientificResult,
        conformer_molblock: str | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Calculator Inspector — {molecule.display_name}")
        self.resize(820, 460)

        layout = QVBoxLayout(self)
        layout.addWidget(_CalculatorResultView(engine, molecule, result, conformer_molblock, self))
