from __future__ import annotations

from collections.abc import Callable

from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState, ScientificResult
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import PerAtomDataset, PhCurveResult, StructureSetResult
from openchem.ui.visualization import (
    SURFACE_REPRESENTATION_LABELS,
    SURFACE_REPRESENTATIONS,
    build_surface_layer,
    build_visualization_layer,
)
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend
from openchem.ui.widgets.ph_curve_widget import PhCurveWidget
from openchem.ui.widgets.structure_grid_widget import StructureGridWidget


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

        # Phase 25b: the same per-atom data, optionally painted onto a
        # molecular surface -- the Marvin charge/LogP screenshots show the
        # property as a coloured surface, not only as coloured sticks.
        # Off by default so the numbered stick view stays the first thing
        # seen; a surface hides the atom labels underneath it.
        self._surface_combo = QComboBox(self)
        self._surface_combo.addItem("No surface", "")
        for representation in SURFACE_REPRESENTATIONS:
            self._surface_combo.addItem(SURFACE_REPRESENTATION_LABELS[representation], representation)
        self._surface_result = result if isinstance(result, PerAtomDataset) else None
        self._surface_combo.setEnabled(self._surface_result is not None and bool(conformer_molblock))
        self._surface_combo.currentIndexChanged.connect(self._on_surface_changed)

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

        surface_row = QHBoxLayout()
        surface_row.addWidget(QLabel("3D surface:", self))
        surface_row.addWidget(self._surface_combo)
        surface_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(summary_label)
        layout.addLayout(views_row)
        layout.addLayout(surface_row)
        layout.addWidget(legend_label)

    def _on_surface_changed(self, _index: int) -> None:
        representation = self._surface_combo.currentData()
        if not representation or self._surface_result is None:
            self._viewer3d.apply_surface(None)
            return
        self._viewer3d.apply_surface(
            build_surface_layer(self._surface_result, representation=representation)
        )


class _PhCurveResultView(QWidget):
    """A pH-curve result's inspection: the chart plus a live readout.

    Deliberately NOT the molecular 2D+3D view above. A `PhCurveResult` has
    no per-atom data at all, so `build_visualization_layer` returns `None`
    for it and `_CalculatorResultView` would render two empty molecule
    panes plus a misleading "No conformer generated yet" line -- the same
    class of empty-looking-like-broken bug Phase 23a fixed when a spectrum
    was showing "Overall: n/a".
    """

    def __init__(self, result: PhCurveResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._chart = PhCurveWidget(result, self)
        self._readout = QLabel(self)
        self._readout.setWordWrap(True)
        self._chart.ph_hovered.connect(self._on_ph_hovered)

        header = QLabel(result.name, self)
        if result.cache_state == CacheState.FAILED:
            header.setText(result.error or "Failed")

        layout = QVBoxLayout(self)
        layout.addWidget(header)
        layout.addWidget(self._chart)
        layout.addWidget(self._readout)

    def _on_ph_hovered(self, ph: float) -> None:
        values = self._chart.readout_at(ph)
        self._readout.setText(
            f"pH {ph:.2f} — " + ", ".join(f"{name}: {value:.2f}" for name, value in values.items())
        )


def _build_ph_curve_view(
    engine: ChemistryEngine,
    molecule: MoleculeModel,
    result: ScientificResult,
    conformer_molblock: str | None,
    parent: QWidget | None,
) -> QWidget:
    return _PhCurveResultView(result, parent)


def _build_structure_grid_view(
    engine: ChemistryEngine,
    molecule: MoleculeModel,
    result: ScientificResult,
    conformer_molblock: str | None,
    parent: QWidget | None,
) -> QWidget:
    """A structure SET has many molecules, so the single-molecule 2D+3D
    view is the wrong shape entirely -- it would depict the input rather
    than any of the results."""
    return StructureGridWidget(engine, result, parent)


# Result type -> view factory, mirroring `_VISUALIZATION_ADAPTERS`'
# type-keyed dispatch (Phase 18) but one level up: that registry answers
# "how do I colour atoms for this result", which only makes sense for
# results that HAVE atoms. This one answers "what widget shows this
# result at all", so a chart-shaped result can opt out of the molecular
# view entirely instead of rendering it empty.
#
# Anything unregistered falls back to the 2D+3D molecular view, which is
# right for every per-atom and spectral result shipped so far.
_RESULT_VIEW_FACTORIES: dict[type, Callable[..., QWidget]] = {
    PhCurveResult: _build_ph_curve_view,
    StructureSetResult: _build_structure_grid_view,
}


class CalculatorInspectorDialog(QDialog):
    """Marvin-style calculator-result inspector -- overall value plus 2D-
    and 3D-colored-and-numbered depictions for ONE calculator's result.
    Opened from the Property Panel's per-category "Open [Calculator]..."
    row, after that calculator's settings dialog (if it has parameters).
    Named "Calculator" rather than "Property" since it can show results
    from any registered `CalculatorRegistry` entry, not just classic
    scalar/per-atom descriptors -- which is now literally true: the view
    is chosen by result type via `_RESULT_VIEW_FACTORIES`.
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

        factory = _RESULT_VIEW_FACTORIES.get(type(result), _CalculatorResultView)
        layout = QVBoxLayout(self)
        layout.addWidget(factory(engine, molecule, result, conformer_molblock, self))
