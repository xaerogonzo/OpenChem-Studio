from __future__ import annotations

import logging
import weakref
from collections.abc import Callable

from PySide6.QtGui import QGuiApplication
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.engine import ChemistryEngine
from openchem.chem.descriptor_providers import compute_gasteiger_charges
from openchem.chem.scalar_field import electrostatic_potential_for_conformer
from openchem.domain.common import EXPLICIT_H, CacheState, ScientificResult
from openchem.domain.molecule import MoleculeModel
from openchem.domain.report import ReportResult
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    StructureEntry,
    StructureSetResult,
    TrajectoryResult,
)
from openchem.ui.result_clipboard import result_to_text
from openchem.ui.widgets.fact_view import FactView
from openchem.ui.visualization import (
    DIVERGING_COLOUR_MAP,
    SURFACE_REPRESENTATION_LABELS,
    SURFACE_REPRESENTATIONS,
    atom_basis,
    build_scalar_field_surface_layer,
    build_surface_layer,
    build_visualization_layer,
    data_range,
    declared_total,
    label_decimals,
    summary_note,
)
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend
from openchem.ui.widgets.ph_curve_widget import PhCurveWidget
from openchem.ui.widgets.structure_grid_widget import StructureGridWidget

logger = logging.getLogger("openchem.ui")


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
        _OPEN_INSPECTORS.add(self)
        layer = build_visualization_layer(result, include_labels=True)

        # THE TOTAL IS READ, NEVER DERIVED. This used to be
        # `sum(result.values.values())`, on the stated belief that the
        # per-atom values of everything shown here were additive. They are
        # not, and the belief was wrong in three separate ways at once --
        # measured on aspirin:
        #
        #   Crippen LogP    summed to  0.1511  against a real LogP of 1.3101
        #   Gasteiger       summed to -0.6555  for a NEUTRAL molecule
        #   eccentricity    summed to  65      which is not a quantity
        #
        # The first two are the same cause: the editor's hydrogens are
        # implicit, so the increments Crippen and PEOE give them have no
        # atom to sit on. The third has no cause to fix -- adding
        # eccentricities together was never meaningful.
        #
        # This line had already been narrowed twice, for spectra and then
        # for categorical results, and each narrowing was one more special
        # case discovered the hard way. The default is inverted now: no
        # declaration, no headline. See `domain/common.TOTAL`.
        units = getattr(result, "units", "")
        units_suffix = f" {units}" if units else ""
        total = declared_total(result) if isinstance(result, PerAtomDataset) else None
        places = label_decimals(result)

        if result.cache_state == CacheState.FAILED:
            summary_text = result.error or "Failed"
        elif total is not None:
            total_units = f" {total['units']}" if total["units"] else ""
            summary_text = f"{total['label']}: {total['value']:.{places}f}{total_units}"
        else:
            # A producer that can explain an empty or category-valued result
            # says so here. Without it an annotation that matched nothing
            # renders as an uncoloured molecule beside a blank line, which
            # reads as broken rather than as "nothing found".
            summary_text = summary_note(result)
        # WHAT AM I LOOKING AT. `result.name` carries the parameters that
        # change the answer -- "Partial Charge (Gasteiger) at pH 7.4 incl.
        # H" states the pH AND the hydrogen mode -- and this dialog showed
        # neither, while the window title carries only the molecule.
        #
        # That is how a correct number came to read as a wrong one: the
        # Properties panel says "Total charge 0" for the drawn structure
        # and this said "Net calculated charge: 1.00 e" for the pH 7.4
        # microspecies, with nothing on screen relating the two.
        name_label = QLabel(getattr(result, "name", "") or "", self)
        name_label.setWordWrap(True)
        name_label.setVisible(bool(name_label.text()))

        summary_label = QLabel(summary_text, self)
        summary_label.setWordWrap(True)
        summary_label.setVisible(bool(summary_text))

        # A PRODUCER'S OWN SENTENCE, AND IT MUST NOT BE AN EITHER/OR.
        # `summary_note` was reachable only when there was NO total, so a
        # result that has both a headline and something to explain about it
        # could not say the second thing. The charge calculator is exactly
        # that case: it has a total, and the interesting fact is which
        # SPECIES the total belongs to.
        note_label = QLabel(summary_note(result) if total is not None else "", self)
        note_label.setWordWrap(True)
        note_label.setVisible(bool(note_label.text()))

        # WHY THE ATOMS BELOW MAY NOT ADD UP TO IT.
        #
        # The arithmetic is this dialog's: subtracting two numbers is
        # ordinary work for a view. The MEANING of the difference is not,
        # and is taken verbatim from the producer -- reading
        # `total - sum(values)` and concluding "so the rest is on the
        # implicit hydrogens" would be a mechanism invented from a
        # residual, which is a mistake this project has made and measured
        # before. Without a producer explanation the gap goes unmentioned
        # rather than guessed at.
        balance_label = QLabel(self)
        balance_label.setWordWrap(True)
        balance_text = self._balance_text(result, total, places)
        balance_label.setText(balance_text)
        balance_label.setVisible(bool(balance_text))

        self._engine = engine
        self._molecule = molecule
        self._layer = layer
        self._conformer_molblock = conformer_molblock
        self._surface_result = result if isinstance(result, PerAtomDataset) else None
        self._depiction_molblock = self._depiction_for(result)

        self._svg_widget = QSvgWidget(self)
        self._render_2d()
        self._svg_widget.setMinimumSize(360, 320)

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
        self._surface_combo.setEnabled(self._surface_result is not None and bool(conformer_molblock))
        self._surface_combo.currentIndexChanged.connect(self._on_surface_changed)

        # An electrostatic potential map is offered only for a dataset of
        # partial CHARGES, because that is the only thing the potential
        # can be computed from -- painting one over LogP contributions
        # would be a picture of a quantity nobody asked for. Keyed on
        # `units == "e"` rather than on a list of calculator ids, so a
        # future charge model qualifies without a code change here.
        self._colouring_combo = QComboBox(self)
        self._colouring_combo.addItem("Per-atom value", "atoms")
        is_charge = self._surface_result is not None and self._surface_result.units == "e"
        if is_charge:
            self._colouring_combo.addItem("Electrostatic potential", "esp")
        self._colouring_combo.setEnabled(is_charge and bool(conformer_molblock))
        self._colouring_combo.currentIndexChanged.connect(self._on_surface_changed)

        # The legend describes whatever is CURRENTLY on screen, so it is
        # rebuilt on every colouring change rather than fixed at
        # construction. Fixing it was a real bug: with the potential
        # selected the label still read the charge range in electrons,
        # which is not merely stale -- it names a different physical
        # quantity in different units, and reads as authoritative.
        # THE DATA RANGE, NOT THE COLOUR DOMAIN. This read
        # `color_scale.domain_min/domain_max`, which for signed data is
        # symmetric about zero and so names a value no atom need have: the
        # molecule this was reported for showed "-1.019 to 1.019" here
        # while the Properties panel three inches away showed
        # "-1.019 to 0.5437" for the same numbers. A reader has no way to
        # tell which is the data. It is the one that says it is.
        #
        # The colour domain still exists and is still symmetric -- see
        # `build_atom_color_layer`, which explains why that is right for
        # colouring. The two are separate quantities with separate names
        # now, which is what stops them being conflated again.
        self._legend_label = QLabel(self)
        span = data_range(result) if isinstance(result, PerAtomDataset) else None
        self._per_atom_legend = (
            f"{span[0]:.{places}f} to {span[1]:.{places}f}{units_suffix}" if span is not None else ""
        )
        if self._per_atom_legend:
            self._legend_label.setText(self._per_atom_legend)
        elif not conformer_molblock:
            self._legend_label.setText("No conformer generated yet -- 3D view is empty.")

        views_row = QHBoxLayout()
        views_row.addWidget(self._svg_widget)
        views_row.addWidget(self._viewer3d.widget())

        # The 2D counterpart of the 3D surface control beside it: the same
        # data as either discrete atom highlights or a continuous field.
        # Only meaningful for numeric per-atom data, so it is enabled on
        # the same condition the surface is.
        self._map_combo = QComboBox(self)
        self._map_combo.addItem("Atom colours", "atoms")
        self._map_combo.addItem("Heat map", "heatmap")
        self._map_combo.setEnabled(self._surface_result is not None)
        self._map_combo.currentIndexChanged.connect(self._on_map_changed)

        surface_row = QHBoxLayout()
        surface_row.addWidget(QLabel("2D:", self))
        surface_row.addWidget(self._map_combo)
        surface_row.addWidget(QLabel("3D surface:", self))
        surface_row.addWidget(self._surface_combo)
        surface_row.addWidget(QLabel("coloured by:", self))
        surface_row.addWidget(self._colouring_combo)
        surface_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(name_label)
        layout.addWidget(summary_label)
        layout.addWidget(note_label)
        layout.addWidget(balance_label)
        layout.addLayout(views_row)
        layout.addLayout(surface_row)
        layout.addWidget(self._legend_label)

    @staticmethod
    def _balance_text(result, total: dict | None, places: int) -> str:
        """"...and the atoms below sum to something else", when they do.

        SUPPRESSED WITHIN THE DISPLAYED PRECISION, which is not cosmetic:
        the two hydrogen modes that DO add up reproduce their total to
        about 1e-16, and without a tolerance every one of them would print
        "the balance (+0.0000000000000002) is on implicit hydrogens" --
        noise given a voice, and worse than saying nothing. The tolerance
        comes from the precision actually on screen, so a user who asks for
        4 decimal places is told about a gap that shows at 4 decimal
        places.
        """
        if total is None or not getattr(result, "values", None):
            return ""
        balance = total.get("balance")
        if not isinstance(balance, dict):
            return ""
        visible = sum(result.values.values())
        difference = total["value"] - visible
        if abs(difference) < 0.5 * 10 ** (-places):
            return ""
        # ASCII hyphen, not an em dash. This sentence is copyable and this
        # project has already hit `UnicodeEncodeError: 'charmap' codec` three
        # times on result text reaching a Windows console stream.
        return (
            f"{len(result.values)} {balance.get('visible_basis', 'values')} sum to "
            f"{visible:.{places}f} - the balance ({difference:+.{places}f}) is on "
            f"{balance.get('explanation', 'atoms not shown')}."
        )

    def _depiction_for(self, result) -> str:
        """Which structure the 2D pane draws.

        Normally the molecule's own editor structure, which is the whole
        point of this pane -- the user recognises what they drew. A dataset
        keyed to EXPLICIT hydrogens is the exception: its values run past
        the end of that structure, `render_2d_svg` drops every index it
        cannot place, and the pane would show a labelled skeleton beside a
        header describing half again as many atoms.

        A VIEW TRANSFORMATION AND NOTHING MORE. The molblock is built here
        and used here; `MoleculeModel.molblock`, the conformer set and the
        undo stack are never touched. That boundary matters more than it
        looks -- this app distinguishes retained, display-aligned and
        adopted conformers, and a dialog quietly writing a hydrogenated
        structure back into any of them would corrupt all three.
        """
        molblock = self._molecule.molblock
        if not molblock or atom_basis(result) != EXPLICIT_H:
            return molblock
        try:
            return self._engine.molblock_with_explicit_hydrogens(molblock)
        except Exception:  # noqa: BLE001 - a depiction that cannot be built must not lose the dialog
            logger.exception("Could not build an explicit-hydrogen depiction; drawing the structure as-is")
            return molblock

    def _render_2d(self) -> None:
        """Draws the 2D pane in whichever mode is selected.

        Called from `__init__` before `_map_combo` exists, so the mode is
        read defensively -- the first render is always the atom-colour one
        and the combo only ever switches away from it.
        """
        if not self._depiction_molblock or self._layer is None:
            return
        combo = getattr(self, "_map_combo", None)
        if combo is not None and combo.currentData() == "heatmap" and self._surface_result:
            svg = self._engine.render_2d_heatmap_svg(
                self._depiction_molblock,
                self._surface_result.values,
                colour_map=DIVERGING_COLOUR_MAP,
                atom_labels=self._layer.atom_labels,
            )
        else:
            svg = self._engine.render_2d_svg(
                self._depiction_molblock, self._layer.atom_colors, self._layer.atom_labels
            )
        self._svg_widget.load(svg.encode("utf-8"))

    def _on_map_changed(self, _index: int) -> None:
        self._render_2d()

    def _on_surface_changed(self, _index: int) -> None:
        representation = self._surface_combo.currentData()
        showing_potential = (
            bool(representation)
            and self._colouring_combo.currentData() == "esp"
            and bool(self._conformer_molblock)
        )
        if not representation or self._surface_result is None:
            self._viewer3d.apply_surface(None)
            self._legend_label.setText(self._per_atom_legend)
            return
        if showing_potential:
            # Charges are recomputed on the CONFORMER rather than reused
            # from the dataset on screen, and the difference is not
            # cosmetic. The dataset is computed on the implicit-hydrogen
            # editor molecule and (matching Marvin) excludes each heavy
            # atom's hydrogen charge, so it covers only heavy atoms and
            # does not sum to the molecular charge. Feeding that to a
            # field gave neutral acetic acid a net -0.40 e and painted
            # the whole surface red. A potential needs charge and
            # geometry to describe the SAME molecule; only recomputing
            # on the conformer guarantees that.
            mol = self._engine.mol_from_molblock(self._conformer_molblock)
            charges = compute_gasteiger_charges(mol)
            field = electrostatic_potential_for_conformer(mol, charges)
            layer = build_scalar_field_surface_layer(field, representation=representation)
            self._viewer3d.apply_surface(layer)
            low, high = layer.scalar_field_range
            # The units come from the FIELD, not from the dataset that fed
            # it: charges are in e, the potential they produce is not.
            #
            # The basis is spelled out because of a consequence a user
            # would otherwise have to guess at: these charges come from
            # the 3D conformer, so the pH this calculator was run at moves
            # the per-atom numbers but does NOT move this surface. A
            # control that silently stops applying is worse than one that
            # says where it stops.
            self._legend_label.setText(
                f"{low:.1f} to {high:.1f} {field.units} "
                "- Gasteiger charges on the 3D conformer, independent of the pH above"
            )
            return
        self._viewer3d.apply_surface(
            build_surface_layer(self._surface_result, representation=representation)
        )
        self._legend_label.setText(self._per_atom_legend)


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
        self._facts_view = self._build_facts_view(result)
        if self._facts_view is not None:
            layout.addWidget(self._facts_view)
        # The chart takes the spare height, not the facts block. A
        # `Preferred` policy on both would split it evenly and leave a
        # four-line stats panel as tall as the graph -- exactly what the
        # 3D viewer's one-line measurement label did before it was
        # given a stretch factor.
        layout.addWidget(self._chart, 1)
        layout.addWidget(self._readout)

    def _build_facts_view(self, result: PhCurveResult) -> QWidget | None:
        """The scalar findings, above the chart, or nothing when a curve
        carries none.

        `FactView` reads `by_category()`/`find()`, which are
        `StructureReport`'s and not `PhCurveResult`'s, so the facts are
        wrapped rather than the widget being taught a second shape. Wrapping
        is what keeps units, limitations and copy-out working for free.

        Controls are hidden: a handful of scalars beside a graph does not
        need a search box, and the full panel is a page of chrome in a
        space Marvin uses for four lines of text.
        """
        if not result.facts:
            return None
        report = ReportResult(
            report_id=result.curve_id,
            name=result.name,
            molecule_uuid=result.molecule_uuid,
            facts=tuple(result.facts),
        )
        view = FactView(self, show_controls=False)
        view.set_report(report)
        return view

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


class _TextResultView(QWidget):
    """A report-style result: the calculator's own lines, selectable.

    `AlertResult` carries its entire output in `matched` and has no
    per-atom data at all, so it used to fall through to
    `_CalculatorResultView` and render TWO EMPTY molecule panes plus "No
    conformer generated yet" -- Elemental Analysis computed a formula, a
    mass and a full composition breakdown and displayed none of it. Every
    report-shaped calculator (Topology, Geometry, Surface, Interactions,
    Elemental, BBB, Stereo, CNS MPO, Huckel...) was affected.

    Read-only but SELECTABLE, so text can be dragged out with the mouse
    as well as taken with the Copy button.
    """

    def __init__(self, result: ScientificResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        text = QPlainTextEdit(self)
        text.setReadOnly(True)
        if result.cache_state == CacheState.FAILED:
            text.setPlainText(getattr(result, "error", "") or "Failed")
        else:
            text.setPlainText("\n".join(getattr(result, "matched", [])))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(getattr(result, "name", ""), self))
        layout.addWidget(text)


def _build_text_view(
    engine: ChemistryEngine,
    molecule: MoleculeModel,
    result: ScientificResult,
    conformer_molblock: str | None,
    parent: QWidget | None,
) -> QWidget:
    return _TextResultView(result, parent)


def _build_trajectory_view(
    engine: ChemistryEngine,
    molecule: MoleculeModel,
    result: ScientificResult,
    conformer_molblock: str | None,
    parent: QWidget | None,
) -> QWidget:
    """A trajectory is MOTION, so it gets a player rather than a picture.

    Without this entry the dispatch fell back to the single-molecule
    2D+3D view, which would have depicted the input molecule and none of
    the 101 frames -- so the Properties panel deliberately opened nothing
    at all rather than open that.
    """
    from openchem.ui.widgets.trajectory_player import TrajectoryPlayerWidget

    return TrajectoryPlayerWidget(result, parent=parent)


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
    TrajectoryResult: _build_trajectory_view,
    AlertResult: _build_text_view,
    ReportResult: _build_text_view,
}


#: How many Calculator Inspectors may be open at once.
#:
#: **AN APPLICATION-LEVEL COUNT OF LIVE DIALOGS, NOT A PROCESS COUNT.**
#: Chromium process topology is a diagnostic that JUSTIFIES this number,
#: never the functional contract -- a cap expressed in
#: `QtWebEngineProcess.exe` counts would change meaning under a Qt upgrade
#: and is not something a user can reason about.
#:
#: Measured before it was written, sampled DURING the run because they are
#: all reaped at exit and a post-mortem finds zero and looks healthy:
#:
#:     open inspectors    QtWebEngineProcess
#:     0                                   0
#:     1..8                             1..8      exactly one each, linear
#:     disposed                            0      per-widget flush frees all
#:
#: So RESOURCES are not the binding constraint -- this project's recorded
#: hang was at 91-116 live processes, and one inspector each puts that
#: nowhere near eight. **The bound is READABILITY**, and it is stated as
#: that rather than dressed up as a resource limit: the Properties panel
#: reached the same conclusion independently, declining to pop inspectors
#: from a multi-calculator run because "six inspectors stacking up is not
#: what anybody asked for".
#:
#: The disposal half is the one that would turn this from a concurrent cap
#: into a cumulative one. `processEvents()` NEVER delivers a
#: `DeferredDelete` at event-loop level 0 against this Qt build -- measured
#: again here, eight dialogs closed that way left all eight processes
#: alive -- so `close()` must be followed by the per-widget
#: `sendPostedEvents(dialog, DeferredDelete)`, never the global form.
MAX_OPEN_INSPECTORS = 8

#: Weak, so a disposed dialog leaves on its own. A strong container here
#: would be the leak this cap exists to prevent, wearing the cap's clothes.
_OPEN_INSPECTORS: "weakref.WeakSet[CalculatorInspectorDialog]" = weakref.WeakSet()


def open_inspector_count() -> int:
    """How many inspectors are alive right now."""
    return len(_OPEN_INSPECTORS)


def inspector_budget_message() -> str | None:
    """Why the next inspector cannot open, or None if it can.

    A REFUSAL WITH A COUNT, not a silent no-op and not a degraded view.
    This app already refuses an LED job on estimated cost and a solvent
    outside its table; a control that quietly does nothing is the one
    outcome this project has repeatedly called worse than a missing one.
    """
    count = open_inspector_count()
    if count < MAX_OPEN_INSPECTORS:
        return None
    return (
        f"{count} calculator inspectors are already open, which is the limit. "
        "Close one to open another -- past this many, a side-by-side "
        "comparison stops being readable."
    )


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
        on_add_structure: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Calculator Inspector — {molecule.display_name}")
        self.resize(820, 460)
        self._engine = engine
        self._result = result
        self._on_add_structure = on_add_structure

        factory = _RESULT_VIEW_FACTORIES.get(type(result), _CalculatorResultView)
        self._view = factory(engine, molecule, result, conformer_molblock, self)

        layout = QVBoxLayout(self)
        layout.addWidget(self._view)
        layout.addLayout(self._build_actions(molecule))

    def _build_actions(self, molecule: MoleculeModel) -> QHBoxLayout:
        """One action row for every result type. "Copy All" is always
        offered -- a calculator whose numbers cannot leave the dialog may
        as well not have run."""
        row = QHBoxLayout()
        self._status_label = QLabel("", self)

        copy_all = QPushButton("Copy All", self)
        copy_all.setToolTip("Copy this result as text (tab-separated where it is tabular).")
        copy_all.clicked.connect(self._on_copy_all)
        row.addWidget(copy_all)

        if isinstance(self._view, StructureGridWidget):
            # A structure set is the case where copying the WHOLE result is
            # the less useful option: the point of a stereoisomer grid is
            # picking the one you wanted and taking that.
            self._copy_smiles_button = QPushButton("Copy SMILES", self)
            self._copy_smiles_button.clicked.connect(self._on_copy_smiles)
            self._copy_molblock_button = QPushButton("Copy Molblock", self)
            self._copy_molblock_button.clicked.connect(self._on_copy_molblock)
            self._add_button = QPushButton("Add to Project", self)
            self._add_button.setToolTip("Add the selected structure as a new molecule (undoable).")
            self._add_button.clicked.connect(self._on_add_selected)
            self._add_button.setVisible(self._on_add_structure is not None)
            for button in (self._copy_smiles_button, self._copy_molblock_button, self._add_button):
                row.addWidget(button)
            self._view.structure_selected.connect(self._on_structure_selected)
            self._update_structure_actions()

        row.addStretch(1)
        row.addWidget(self._status_label)
        return row

    # --- actions ----------------------------------------------------------

    def _set_status(self, message: str) -> None:
        self._status_label.setText(message)

    def _copy(self, text: str, what: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self._set_status(f"{what} copied.")

    def _on_copy_all(self) -> None:
        self._copy(result_to_text(self._result), "Result")

    def _selected_entry(self) -> StructureEntry | None:
        return self._view.selected_entry() if isinstance(self._view, StructureGridWidget) else None

    def _update_structure_actions(self) -> None:
        has_selection = self._selected_entry() is not None
        for button in (self._copy_smiles_button, self._copy_molblock_button, self._add_button):
            button.setEnabled(has_selection)
        if not has_selection:
            self._set_status("Click a structure to select it.")

    def _on_structure_selected(self, _index: int) -> None:
        self._update_structure_actions()
        entry = self._selected_entry()
        if entry is not None:
            self._set_status(f"Selected: {entry.label}")

    def _on_copy_smiles(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        try:
            self._copy(self._engine.molblock_to_smiles(entry.molblock), "SMILES")
        except Exception as exc:  # noqa: BLE001 - say why rather than copying nothing
            self._set_status(f"Could not convert to SMILES: {exc}")

    def _on_copy_molblock(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            # The molblock, not SMILES, is what preserves 3D coordinates --
            # which is the whole difference for a conformer set.
            self._copy(entry.molblock, "Molblock")

    def _on_add_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None or self._on_add_structure is None:
            return
        self._on_add_structure(entry.molblock, entry.label)
        self._set_status(f"Added {entry.label} to the project.")
