"""The support-stage star: what it says, where it appears, and that it stays quiet.

`domain/support_marker.py` owns the meaning (no Qt), `ui/widgets/stage_marker.py` draws
it, and the Properties rows and the Results reader place it. The rules worth pinning:

* a classified calculator is marked, an UNCLASSIFIED one is not (a neutral default is
  not a validation),
* the tooltip carries the calculator's own reason,
* an unmarked row is exactly what it was (no star built, nothing hidden or shown that
  was not before),
* the star follows the palette, so a dark theme needs no second table.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor, QImage, QPalette
from PySide6.QtWidgets import QWidget

from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import CalculatorDefinition, RegistryExecution
from openchem.domain.calculator_support import (
    UNCLASSIFIED,
    CalculatorSupport,
    SupportStage,
    Visibility,
)
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.domain.support_marker import (
    STAGE_FILLS,
    STAGE_LABELS,
    STAGE_MEANINGS,
    Fill,
    marker_for,
)
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected, ReportComputed
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService
from openchem.ui.panels.property_panel import PropertyPanel
from openchem.ui.widgets.fact_view import FactView
from openchem.ui.widgets.results_view import ResultsView
from openchem.ui.widgets.stage_marker import STAGE_MARKER_HELP, StageMarker
from tests.conftest import dispose

PLAIN = "plain"
STABLE = "steady"
LIMITED = "narrow"
EXPERIMENTAL = "rough"

_REASON = "Joback has no group for a ring tertiary amine, so it declines RDX."


def _definition(calculator_id: str, support: CalculatorSupport | None) -> CalculatorDefinition:
    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=calculator_id.capitalize(),
        category="topology",
        description=f"{calculator_id}. Runs nothing in this fixture.",
        execution=RegistryExecution(compute=lambda _mol, _uuid, _params: None),
        support=support,
    )


def _supports() -> dict[str, CalculatorSupport | None]:
    return {
        PLAIN: None,
        STABLE: CalculatorSupport(SupportStage.STABLE, Visibility.SHOWN, scope_note="C/H/N/O"),
        LIMITED: CalculatorSupport(SupportStage.LIMITED, Visibility.SHOWN, support_reason=_REASON),
        EXPERIMENTAL: CalculatorSupport(
            SupportStage.EXPERIMENTAL, Visibility.HIDDEN, support_reason="Not yet validated."
        ),
    }


# --- the mapping, with no Qt ---------------------------------------------------------


def test_every_stage_has_a_label_a_fill_and_a_meaning():
    for stage in SupportStage:
        assert STAGE_LABELS[stage]
        assert STAGE_MEANINGS[stage]
        assert stage in STAGE_FILLS


def test_the_three_stages_have_three_different_fills():
    assert STAGE_FILLS[SupportStage.STABLE] is Fill.FULL
    assert STAGE_FILLS[SupportStage.LIMITED] is Fill.HALF
    assert STAGE_FILLS[SupportStage.EXPERIMENTAL] is Fill.EMPTY
    assert len(set(STAGE_FILLS.values())) == 3


def test_an_unclassified_calculator_gets_no_marker():
    """`UNCLASSIFIED` is treated as STABLE so nothing changed under anybody; nobody earned
    it, so it must not be dressed as a star."""
    assert marker_for(_definition(PLAIN, None)) is None
    assert marker_for(None) is None
    # And the neutral default itself, were someone to declare it, is a DECLARATION.
    assert UNCLASSIFIED.stage is SupportStage.STABLE
    assert marker_for(_definition(PLAIN, UNCLASSIFIED)) is not None


@pytest.mark.parametrize(
    ("calculator_id", "label", "fill"),
    [
        (STABLE, "Stable", Fill.FULL),
        (LIMITED, "Limited", Fill.HALF),
        (EXPERIMENTAL, "Experimental", Fill.EMPTY),
    ],
)
def test_a_classified_calculator_maps_stage_to_label_and_fill(calculator_id, label, fill):
    marker = marker_for(_definition(calculator_id, _supports()[calculator_id]))
    assert marker is not None
    assert (marker.label, marker.fill) == (label, fill)


def test_the_tooltip_carries_the_reason_and_the_scope():
    limited = marker_for(_definition(LIMITED, _supports()[LIMITED]))
    assert _REASON in limited.tooltip
    assert "Limited" in limited.tooltip
    stable = marker_for(_definition(STABLE, _supports()[STABLE]))
    assert "Covers: C/H/N/O." in stable.tooltip
    assert "Why:" not in stable.tooltip, "a plain STABLE calculator has no reason to give"


def test_the_words_speak_for_the_implementation_not_the_method():
    """`calculator_support` is explicit that the stage never says the literature is unsure."""
    for meaning in STAGE_MEANINGS.values():
        assert "literature" not in meaning
    assert "implementation" in STAGE_MARKER_HELP.text
    assert "never about the published method" in STAGE_MARKER_HELP.text


# --- the widget -------------------------------------------------------------------------


def _painted(fill_stage: SupportStage | None, dark: bool = False) -> QImage:
    widget = StageMarker()
    if dark:
        palette = widget.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor("white"))
        widget.setPalette(palette)
    if fill_stage is not None:
        widget.set_marker(
            marker_for(
                _definition(
                    "x",
                    CalculatorSupport(fill_stage, Visibility.HIDDEN, support_reason="r"),
                )
            )
        )
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    dispose(widget)
    return image


def test_the_widget_is_hidden_and_draws_nothing_without_a_marker(qapp):
    widget = StageMarker()
    assert widget.isHidden()
    assert widget.marker() is None
    dispose(widget)


def _ink(image: QImage, x: int, y: int) -> bool:
    """Whether pixel (x, y) differs from the empty corner. `render` paints the widget's own
    opaque background first, so alpha cannot tell ink from paper; the corner can."""
    return image.pixelColor(x, y) != image.pixelColor(0, 0)


def test_the_three_fills_are_really_painted(qapp):
    """The star's centre is (6, 6) and its inner vertices are about 2 px out, so (5, 6)
    and (6, 6) are the two interior pixels either side of the clip at x = 6. FULL is ink on both sides, HALF only on
    the left, EMPTY (an outline) on neither."""
    full = _painted(SupportStage.STABLE)
    half = _painted(SupportStage.LIMITED)
    empty = _painted(SupportStage.EXPERIMENTAL)
    assert _ink(full, 5, 6) and _ink(full, 6, 6)
    assert _ink(half, 5, 6) and not _ink(half, 6, 6)
    assert not _ink(empty, 5, 6) and not _ink(empty, 6, 6)
    # An outline is still drawn: the star is not invisible.
    assert any(_ink(empty, x, y) for x in range(12) for y in range(12))


def test_the_star_is_low_contrast_and_stable_recedes(qapp):
    """Painted at a reduced opacity, so even the firmest ink is lighter than the palette's own
    text colour, and STABLE is fainter than the stages with a caveat. Compared as grey levels
    on the light fixture palette (0 is black text, 239 the paper)."""
    text = QWidget().palette().color(QPalette.ColorRole.WindowText).red()
    stable = _painted(SupportStage.STABLE).pixelColor(5, 6).red()
    limited = _painted(SupportStage.LIMITED).pixelColor(5, 6).red()
    assert text < limited < stable < 239


def test_the_star_follows_the_palette_so_a_dark_theme_needs_no_second_table(qapp):
    light = _painted(SupportStage.LIMITED).pixelColor(5, 6)
    dark = _painted(SupportStage.LIMITED, dark=True).pixelColor(5, 6)
    assert dark.red() > light.red()


def test_the_widget_carries_the_shared_contract_plus_its_own_reason(qapp):
    widget = StageMarker()
    widget.set_marker(marker_for(_definition(LIMITED, _supports()[LIMITED])))
    tip = widget.toolTip()
    assert tip.startswith(STAGE_MARKER_HELP.text)
    assert _REASON in tip
    assert widget.accessibleName() == "Support level: Limited"
    dispose(widget)


# --- the Properties rows ---------------------------------------------------------------


@pytest.fixture
def panel(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()
    for calculator_id, support in _supports().items():
        registry.register(_definition(calculator_id, support))
    widget = PropertyPanel(
        bus,
        registry,
        DescriptorService(bus, engine, calculator_registry=registry),
        engine,
        structure_version_of=lambda _uuid: 0,
    )
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    widget.set_project(ProjectModel(molecules=[molecule]))
    reader = ResultsView()
    widget.attach_reader(reader)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    QCoreApplication.processEvents()
    yield widget, bus, reader, molecule
    dispose(reader)
    dispose(widget)


def test_properties_rows_are_marked_only_where_a_stage_was_declared(panel):
    widget, _bus, _reader, _molecule = panel
    markers = widget._calculator_stage_markers
    assert markers[PLAIN].marker() is None
    # ...but it keeps the room, blank: its section has stars, and a row without one would
    # otherwise sit 18 px out of line with its neighbours.
    assert not markers[PLAIN].isHidden() and markers[PLAIN].toolTip() == ""
    assert markers[PLAIN].size() == markers[STABLE].size()
    assert markers[STABLE].marker().fill is Fill.FULL and not markers[STABLE].isHidden()
    assert markers[LIMITED].marker().fill is Fill.HALF and not markers[LIMITED].isHidden()
    assert markers[EXPERIMENTAL].marker().fill is Fill.EMPTY
    assert _REASON in markers[LIMITED].toolTip()


def test_a_section_with_no_star_is_exactly_what_it_was(qapp):
    """No room is reserved, and no star built, where nothing in the section is classified."""
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()
    registry.register(_definition(PLAIN, None))
    widget = PropertyPanel(
        bus, registry, DescriptorService(bus, engine, calculator_registry=registry), engine
    )
    try:
        assert widget._calculator_stage_markers[PLAIN].isHidden()
    finally:
        dispose(widget)


def test_the_star_is_the_rightmost_item_of_its_row(panel):
    widget, _bus, _reader, _molecule = panel
    row = widget._calculator_rows[LIMITED]
    items = [row.layout().itemAt(i).widget() for i in range(row.layout().count())]
    assert items[-1] is widget._calculator_stage_markers[LIMITED]
    assert items[-2] is widget._calculator_status[LIMITED]


# --- the Results reader ----------------------------------------------------------------


def _report(report_id: str, uuid: str) -> ReportResult:
    return ReportResult(
        molecule_uuid=uuid,
        report_id=report_id,
        name=report_id.capitalize(),
        category="topology",
        facts=(
            Fact(
                category=FactCategory.TOPOLOGY,
                label=f"{report_id} value",
                value=1,
                display_value="1",
                source="RDKit",
                basis=Basis.DETERMINISTIC,
            ),
        ),
        structure_version=0,
    )


def _land_all(bus, molecule):
    for calculator_id in (PLAIN, STABLE, LIMITED):
        bus.publish(ReportComputed(report=_report(calculator_id, molecule.uuid)))
    QCoreApplication.processEvents()


def _row_markers(reader: ResultsView) -> list[StageMarker]:
    return [m for m in reader.findChildren(StageMarker) if m is not reader.stage_marker()]


def test_all_results_marks_the_rows_of_classified_calculators_only(panel):
    _widget, bus, reader, molecule = panel
    _land_all(bus, molecule)
    assert reader.focus() == ""
    assert reader.stage_marker().isHidden()
    fills = sorted(m.marker().fill.value for m in _row_markers(reader))
    assert fills == ["full", "half"], "one star per classified calculator's fact, none for the plain one"


def test_a_focused_calculator_says_it_once_beside_showing_not_on_every_row(panel):
    _widget, bus, reader, molecule = panel
    _land_all(bus, molecule)
    reader.set_focus(LIMITED)
    header = reader.stage_marker()
    assert not header.isHidden() and header.marker().fill is Fill.HALF
    assert _REASON in header.toolTip()
    assert _row_markers(reader) == []
    reader.set_focus(PLAIN)
    assert header.isHidden()
    reader.set_focus("")
    assert header.isHidden()


def test_a_view_with_no_resolver_draws_no_star(qapp):
    view = FactView()
    view.set_report(_report(LIMITED, "u"), "t", "")
    assert view.findChildren(StageMarker) == []
    dispose(view)


def test_a_resolver_that_raises_costs_a_row_nothing(qapp):
    def boom(_report_id):
        raise RuntimeError("no registry today")

    view = FactView()
    view.set_support_resolver(boom)
    report = _report(LIMITED, "u")
    # `origin` is stamped by `merge_reports`; stamp it as a merge would.
    import dataclasses

    stamped = dataclasses.replace(
        report, facts=tuple(dataclasses.replace(f, origin=LIMITED) for f in report.facts)
    )
    view.set_report(stamped, "t", "")
    assert view.visible_fact_labels() == [f"{LIMITED} value"]
    assert view.findChildren(StageMarker) == []
    dispose(view)


# --- the rows that open another panel, on the real registry -------------------------------


def test_the_experimental_workflow_rows_carry_their_star_and_unclassified_ones_stay_bare(qapp):
    """The ORCA workflows are the calculators that are still experimental, and they are all
    rows that OPEN another panel. Fukui is declared experimental; Single Point Energy is a
    legacy-unclassified one, so its row is the bare button it always was."""
    from openchem.bootstrap import build_service_container
    from openchem.domain.calculator import ServiceExecution

    registry = build_service_container().calculator_registry
    widget = PropertyPanel(
        EventBus(), registry, DescriptorService(EventBus(), ChemistryEngine(), calculator_registry=registry),
        ChemistryEngine(),
    )
    try:
        fukui = widget._calculator_stage_markers["orca.fukui"]
        assert fukui.marker().fill is Fill.EMPTY
        assert registry.get("orca.fukui").support.support_reason in fukui.toolTip()
        assert isinstance(registry.get("orca.fukui").execution, ServiceExecution)
        # The button is still what a press and the help contract reach.
        assert widget._service_rows["orca.fukui"].parentWidget() is widget._service_row_widgets["orca.fukui"]
        # Single Point has no declared stage: no star, but its row keeps the room, because the
        # Quantum Chemistry section has stars and the buttons must end in one line.
        blank = widget._calculator_stage_markers["orca.sp"]
        assert blank.marker() is None and not blank.isHidden()
        # A section with no star at all keeps the bare button.
        assert widget._service_row_widgets["docking.vina"] is widget._service_rows["docking.vina"]
    finally:
        dispose(widget)
