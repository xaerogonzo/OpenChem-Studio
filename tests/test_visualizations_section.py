"""Every picture a result declares, as peers, each saying what it is.

Stage 1f. They were peers in the MODEL already -- all producer-declared
annotations, validated fail-closed, and `ui/visualization.py` calls the layer
type renderer-independent. What differed was where each one ended up:

    charts and depictions   rendered inside the reader
    spatial annotations     a separate MODAL window the reader was no part of

**AND THE DIVERSION WAS THE LIVE HALF.** `_on_details_clicked` sent any
report declaring `spatial` into `SpatialResultDialog(...).exec()` and
RETURNED, so of the sixty results reaching the reader, the two carrying a 3D
overlay -- Geometry and Dipole Moment -- never reached it from that button at
all, and reached a modal dialog instead. That reinstated for those two exactly
what `MergedResultsDialog`'s own docstring says it exists to remove: with a
modal window you cannot run the second calculator whose results the reader
accumulates.

Measured on aspirin with a real conformer: 6 results carry a picture -- 2
stick charts, 1 line chart, 1 depiction, 1 axes, 1 arrow.
"""

from __future__ import annotations

import pytest

from openchem.domain.report import (
    ArrowAnnotation,
    AxesAnnotation,
    Basis,
    ConeAnnotation,
    DepictionAnnotation,
    Fact,
    FactCategory,
    LineChartAnnotation,
    ReportResult,
    Stick,
    StickChartAnnotation,
)
from openchem.domain.visualization import VisualizationLayer
from openchem.domain.visualization_index import (
    CHART,
    DEPICTION,
    OVERLAY_3D,
    VISUALIZATION_KINDS,
    declared_visualizations,
    kind_of_annotation,
)
from openchem.ui.widgets.results_view import ResultsView
from tests.conftest import dispose

MOLECULE = "mol-1"


def _fact(label: str = "Formula") -> Fact:
    return Fact(
        category=FactCategory.IDENTITY, label=label, value=label,
        display_value=label, source="RDKit", basis=Basis.DETERMINISTIC,
    )


def _stick(title="Isotope pattern") -> StickChartAnnotation:
    return StickChartAnnotation(
        sticks=(Stick(1.0, 1.0),), x_label="m/z", y_label="rel",
        x_descending=False, title=title,
    )


def _arrow(label="0.89 D") -> ArrowAnnotation:
    """**THE LABEL IS A VALUE, WHICH IS THE SHAPE EVERY REAL PRODUCER USES.**
    The first version of this fixture passed "Dipole moment" -- a name none of
    them writes -- so the unit tests agreed with a rule the running
    application disproved on its first drive. `dipole.py` formats
    `f"{magnitude:.2f} D"`, `steric.py` `f"{angle:.1f} deg"`.
    """
    return ArrowAnnotation(anchor=(0, 0, 0), vector=(1, 0, 0), units="D", label=label)


def _axes() -> AxesAnnotation:
    return AxesAnnotation(
        origin=(0, 0, 0), axes=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        extents=(1.0, 1.0, 1.0), labels=("a", "b", "c"),
    )


def _report(report_id="dipole_moment", name="Dipole Moment", charts=(), spatial=()):
    return ReportResult(
        molecule_uuid=MOLECULE, report_id=report_id, name=name,
        category="electronic", facts=(_fact(),),
        charts=tuple(charts), spatial=tuple(spatial),
    )


@pytest.fixture
def window(qapp):
    w = ResultsView(MOLECULE)
    yield w
    dispose(w)


def _visual_rows(window):
    """Every row of the Visualizations list, as the strings it shows."""
    layout = window._visuals_layout
    rows = []
    for i in range(1, layout.count()):  # 0 is the heading
        row = layout.itemAt(i).widget()
        texts = []
        inner = row.layout()
        for j in range(inner.count()):
            widget = inner.itemAt(j).widget()
            if widget is not None:
                texts.append(widget.text())
        rows.append(texts)
    return rows


# --- the vocabulary is closed and derived from the TYPE ------------------


@pytest.mark.parametrize(
    "annotation, kind",
    [
        (_stick(), CHART),
        (
            LineChartAnnotation(
                series=(), x_label="pH", y_label="f",
                x_descending=False, title="Curve",
            ),
            CHART,
        ),
        (
            DepictionAnnotation(
                layer=VisualizationLayer(name="sites", atom_colors={}, atom_labels={}),
                title="Lewis sites",
            ),
            DEPICTION,
        ),
        (_arrow(), OVERLAY_3D),
        (_axes(), OVERLAY_3D),
        (
            ConeAnnotation(
                apex=(0, 0, 0), axis=(0, 0, 1), half_angle_deg=45.0,
                length=2.0, label="Steric cone",
            ),
            OVERLAY_3D,
        ),
    ],
)
def test_every_shipped_annotation_type_declares_a_kind(annotation, kind):
    """TOTAL over the six, and derived from the TYPE -- the same question
    `chart_widget_for` asks, so a label and its widget cannot disagree about
    what an annotation is."""
    assert kind_of_annotation(annotation) == kind
    assert kind in VISUALIZATION_KINDS


def test_an_unrecognised_annotation_raises_rather_than_rendering_as_nothing():
    """Refuses rather than defaulting, for the reason `kind_of` does: a
    default turns an unknown annotation into a plausible picture of the wrong
    sort, and the alternative -- returning "" -- makes a seventh annotation
    type silently invisible, which is the failure this module ends."""
    with pytest.raises(TypeError):
        kind_of_annotation(object())


# --- what a result declares ----------------------------------------------


def test_charts_and_spatial_arrive_as_one_list():
    found = declared_visualizations(_report(charts=[_stick()], spatial=[_arrow()]))
    assert [(v.title, v.kind, v.inline) for v in found] == [
        ("Isotope pattern", CHART, True),
        # The REPORT's name, because the arrow declares no title and its
        # `label` is a measurement rather than a name.
        ("Dipole Moment", OVERLAY_3D, False),
    ]


def test_a_3d_overlay_is_never_inline():
    """It needs a `Mol3DViewerBackend`, which is a QtWebEngine process -- this
    project has measured those accumulating to 116 and hanging the suite --
    and a fixed-height 3D view inside a resizable `QScrollArea` is the
    height-for-width fight already lost three times here."""
    for visual in declared_visualizations(_report(spatial=[_arrow(), _axes()])):
        assert not visual.inline, visual.title


def test_a_spatial_annotations_label_is_a_VALUE_and_never_the_title():
    """**FOUND BY DRIVING THE APP, AND THIS TEST USED TO ASSERT THE
    OPPOSITE.**

    The first rule here was `title or label`, and the row for aspirin's
    dipole came out titled **"0.89 D"** -- a measurement where a picture's
    name belongs. All three shipped spatial producers format a number into
    that field; it is a caption drawn ON the model, which is why the 3D view
    wants it and a list of pictures does not.

    The predecessor passed because its fixture invented `label="Dipole
    moment"`, a name no producer writes.
    """
    found = declared_visualizations(_report(spatial=[_arrow("0.89 D")]))
    assert found[0].title != "0.89 D"
    assert found[0].title == "Dipole Moment", "the report names its own picture"


def test_an_unnamed_annotation_takes_the_name_of_the_result_it_belongs_to():
    """`AxesAnnotation` declares `labels` -- one per axis -- which names three
    things rather than the picture. A spatial annotation is one report's
    picture, so the report is what names it."""
    found = declared_visualizations(_report(report_id="geometry", name="Geometry",
                                            spatial=[_axes()]))
    assert found[0].title == "Geometry"


def test_the_KIND_is_the_last_resort_when_nothing_names_it():
    """Never a positional "Visualization 2", which tells a reader deciding
    whether to open something nothing at all."""
    anonymous = _report(report_id="x", name="", spatial=[_axes()])
    assert declared_visualizations(anonymous)[0].title == OVERLAY_3D


def test_an_entry_with_neither_field_declares_nothing():
    """`StructureReport`, `AtomReport` and `BondReport` have neither, and this
    is read by a widget the Atom Inspector also uses."""

    class Bare:
        pass

    assert declared_visualizations(Bare()) == ()


def test_nothing_here_derives_a_picture_from_the_facts():
    """An empty result is the producer's statement that it has none -- the
    rule `_rebuild_charts` already holds, and the reason elemental analysis's
    "C: 55.34%" facts do not become bars."""
    facts_only = _report(report_id="elemental_analysis", name="Elemental Analysis")
    assert declared_visualizations(facts_only) == ()


# --- the reader lists them -----------------------------------------------


def test_the_section_is_absent_when_a_result_declares_no_picture(window):
    window.set_reports([_report(report_id="topology", name="Topology")])
    window.set_focus("topology")
    assert not window._visuals.isVisibleTo(window)


def test_each_row_says_what_kind_of_picture_it_is(window):
    window.set_reports([_report(charts=[_stick()], spatial=[_arrow()])])
    window.set_focus("dipole_moment")

    rows = _visual_rows(window)
    assert rows[0][:2] == ["Isotope pattern", f"[{CHART}]"]
    assert rows[1][:2] == ["Dipole Moment", f"[{OVERLAY_3D}]"]


def test_an_inline_picture_is_listed_and_offers_no_button(window):
    """It is already drawn a few rows below; an Open button would imply a
    second copy. It is still LISTED, so "what can this show me" has one
    answer rather than one split between a list and a scroll."""
    from PySide6.QtWidgets import QPushButton

    window.set_reports([_report(report_id="mass_spectrum", name="Mass Spectrum",
                                charts=[_stick()])])
    window.set_focus("mass_spectrum")

    assert _visual_rows(window)[0] == ["Isotope pattern", f"[{CHART}]", "shown below"]
    assert not window._visuals.findChildren(QPushButton)


def test_the_section_goes_away_when_the_reader_moves_to_all_results(window):
    """Several producers at once, so no one result's pictures are on screen.
    The setup asserts the section was UP first -- without that this holds
    against a render path that does nothing at all, which is the degenerate
    fixture this stage has already produced four times."""
    window.set_reports([_report(spatial=[_arrow()])])
    window.set_focus("dipole_moment")
    assert window._visuals.isVisibleTo(window), "setup: the section must be up"

    window.set_focus("")
    assert not window._visuals.isVisibleTo(window)


# --- and pressing Open asks the router, not the dialog -------------------


def test_pressing_open_names_the_report_and_the_annotation(window):
    seen = []
    window.link_activated.connect(seen.append)
    window.set_reports([_report(charts=[_stick()], spatial=[_arrow()])])
    window.set_focus("dipole_moment")

    from PySide6.QtWidgets import QPushButton

    buttons = window._visuals.findChildren(QPushButton)
    assert len(buttons) == 1, "only the 3D overlay is openable"
    buttons[0].click()

    assert len(seen) == 1
    assert seen[0].target == "spatial_view"
    assert seen[0].params == {"report_id": "dipole_moment", "annotation_index": 1}


# --- and the map stays total, derived rather than remembered -------------


def test_every_annotation_type_the_domain_declares_has_a_kind():
    """**THE POPULATION IS WALKED, NOT LISTED.**

    A seventh annotation type added without an entry in `_KIND_OF_ANNOTATION`
    does not fail anywhere: `declared_visualizations` would raise only if
    something actually declared one, and until a producer does, the type
    simply cannot be shown. That is the green-suite-and-a-smaller-universe
    failure -- a picture nobody can see, with nothing red.

    Derived from `domain/report.py`'s own classes so the rule cannot rot into
    a list somebody has to remember, and the population is asserted so a walk
    that collapses to nothing cannot pass vacuously.
    """
    import ast
    import pathlib

    from openchem.domain.visualization_index import _KIND_OF_ANNOTATION

    source = pathlib.Path(
        "src/openchem/domain/report.py"
    ).read_text(encoding="utf-8")
    declared = {
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ClassDef) and node.name.endswith("Annotation")
    }
    assert len(declared) >= 6, f"the walk found only {sorted(declared)}"

    mapped = {annotation.__name__ for annotation in _KIND_OF_ANNOTATION}
    assert declared <= mapped, (
        "these annotation types can never be shown: " + ", ".join(sorted(declared - mapped))
    )


# --- the three the mutation pass found ----------------------------------
#
# F11, F12 and F14 all SURVIVED a first pass against 168 green tests, and F11
# is the defect this stage exists to remove -- guarded by nothing at all,
# because every test above covers what the reader SHOWS and none covered how
# a reader gets there.


def _panel(qapp):
    from openchem.chem.engine import ChemistryEngine
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeSelected
    from openchem.services.calculator_registry import CalculatorRegistry
    from openchem.ui.panels.property_panel import PropertyPanel

    class _FakeService:
        def run_calculator(self, model, request) -> None:
            pass

    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _FakeService(), ChemistryEngine())
    bus.publish(MoleculeSelected(molecule_uuid=MOLECULE))
    return bus, panel


def test_details_reaches_the_READER_even_for_a_shape_valued_result(qapp):
    """**F11, AND IT IS THE WHOLE POINT OF THIS STAGE.**

    `_on_details_clicked` used to send any report declaring `spatial` into
    `SpatialResultDialog(...).exec()` and RETURN, so Geometry and Dipole
    Moment -- 2 of the 60 results reaching the reader -- never reached it
    from that button, and reached a MODAL window instead.

    Driven through the real button rather than by calling the handler, for
    the reason `jobs_cancel` presses the real control: the handler reads
    which report it means off `sender()`, so calling it directly passes
    `sender() is None` and proves nothing about the wiring that changed.
    """
    from openchem.events.events import ReportComputed
    from PySide6.QtWidgets import QPushButton

    bus, panel = _panel(qapp)
    reader = ResultsView()
    panel.attach_reader(reader)
    try:
        bus.publish(ReportComputed(report=_report(spatial=[_arrow()])))
        row = panel._report_labels["dipole_moment"].parentWidget()
        details = row.findChildren(QPushButton)[0]
        assert details.text() == "Details...", "setup: the real button"

        details.click()

        # STRONGER than "a reader exists": the shape-valued result has to
        # arrive FOCUSED, like every other one. The window it used to be
        # diverted into could not be focused on anything.
        assert reader.focus() == "dipole_moment", (
            "a shape-valued result must reach the reader like every other one"
        )
    finally:
        dispose(reader)
        dispose(panel)


def test_a_result_with_no_conformer_refuses_its_own_picture(qapp):
    """**F12, AND MY FIRST FIXTURE FOR IT NEVER REACHED THE BRANCH.**

    A conformer must exist to draw on, so a molecule without one answers
    FALSE and the router turns that into a visible message rather than a
    button that does nothing.

    The first version built a panel with NO PROJECT, which is refused several
    lines earlier -- so the conformer check was never executed and a mutation
    making it answer True survived. It needs a real project holding a real
    molecule that genuinely has no conformer, which is the ordinary state of
    a structure somebody has only drawn.
    """
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.molecule import MoleculeModel
    from openchem.domain.project import ProjectModel
    from openchem.events.events import MoleculeSelected, ReportComputed

    bus, panel = _panel(qapp)
    try:
        engine = ChemistryEngine()
        molecule = MoleculeModel()
        engine.set_structure_from_smiles(molecule, "CCO")
        assert not molecule.conformers, "setup: a drawn structure has no conformer"

        panel.set_project(ProjectModel(molecules=[molecule]))
        bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
        bus.publish(ReportComputed(
            report=_report(spatial=[_arrow()]).__class__(
                molecule_uuid=molecule.uuid, report_id="dipole_moment",
                name="Dipole Moment", category="electronic",
                facts=(_fact(),), spatial=(_arrow(),),
            )
        ))
        assert "dipole_moment" in panel._reports, "setup: the report is held"

        assert panel.open_spatial_view("dipole_moment") is False
        # And a report this panel is not holding is refused too.
        assert panel.open_spatial_view("nothing-here") is False
    finally:
        dispose(panel)


def test_an_inline_charts_heading_says_what_kind_it_is(qapp):
    """**F14.** A folded heading is all a reader scrolling past can see, and
    "Isotope pattern" does not say whether it is a plot or a structure
    drawing. Nothing asserted the heading text at all."""
    from openchem.ui.widgets.fact_view import FactView

    view = FactView()
    try:
        view.set_report(_report(report_id="mass_spectrum", name="Mass Spectrum",
                                charts=[_stick()]), "Mass Spectrum", "")
        # The heading is the section's own toggle button -- read from Qt
        # rather than from a stored string, so this cannot pass against a
        # title that was computed and never drawn.
        headings = [s._toggle_button.text() for s in view._chart_sections]
        assert headings, "setup: a chart section must have been built"
        assert any(f"[{CHART}]" in h for h in headings), headings
    finally:
        dispose(view)
