"""A long result must not collapse into a one-word-per-line ribbon.

Confirmed from the running app: with the Properties panel at the ~170 px
the right-hand dock gave it, a six-line Geometry result rendered as 33
lines, and a REPORT row -- whose field column also carries an 80 px
"Details..." button -- had about 22 px left for its text, with the button
itself cut off.

MEASURED AGAINST FONT METRICS, NEVER AGAINST THE LABEL'S OWN SIZE HINT.
The probe that previously reported this panel healthy compared each
label's `height()` to its own `minimumSizeHint()`, and `WrappedLabel`
computes that hint FROM its current width -- so when the hint
under-reports, the height matches it and the check passes while the text
is cut off. Four clean measurements were taken that way before the flaw
was noticed. The hint cannot be both the thing under test and the
reference, so `QFontMetrics.boundingRect` for the real string at the
label's real width is the reference here.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState, Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.scientific_result import AlertResult
from openchem.events.base import EventBus
from openchem.events.events import AlertComputed, DescriptorComputed, MoleculeSelected
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.ui.panels.property_panel import PropertyPanel
from openchem.ui.widgets.collapsible_section import CollapsibleSection

#: A real Geometry result. Six lines, and the longest needs ~187 px on
#: one line at the default font.
GEOMETRY_LINES = [
    "Max radius (from centroid): 6.90 A",
    "Min radius (from centroid): 0.13 A",
    "Mean radius (from centroid): 3.71 A",
    "Projection area (xy): 78.44 A^2",
    "MMFF94 energy: 109.52 kcal/mol",
    "UFF energy: 141.08 kcal/mol",
]

#: Short scalars, present so the label column is sized by a realistic
#: widest label. Without them the field column is wider than it ever is in
#: the app and the failure does not reproduce.
SHORT = [
    ("mol_wt", "Molecular Weight", 313.4),
    ("tpsa", "TPSA", 41.93),
    ("logp", "LogP", 1.53),
    ("rings", "Ring Count", 5),
]


class _FakeService:
    def run_calculator(self, model, request) -> None:  # noqa: D102 - test double
        pass


def _lines_used(label: QLabel) -> int:
    """How many lines the text actually needs at this label's width."""
    metrics = QFontMetrics(label.font())
    width = label.contentsRect().width()
    if width <= 0:
        return 0
    flags = Qt.TextFlag.TextWordWrap if label.wordWrap() else Qt.TextFlag.TextSingleLine
    height = metrics.boundingRect(QRect(0, 0, width, 0), int(flags), label.text()).height()
    return max(1, round(height / metrics.lineSpacing()))


def _required_height(label: QLabel) -> int:
    metrics = QFontMetrics(label.font())
    width = label.contentsRect().width()
    if width <= 0:
        return 0
    flags = Qt.TextFlag.TextWordWrap if label.wordWrap() else Qt.TextFlag.TextSingleLine
    return metrics.boundingRect(QRect(0, 0, width, 0), int(flags), label.text()).height()


def _panel_with_a_long_result(qapp, width: int, height: int = 1000):
    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _FakeService(), ChemistryEngine())
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))
    for descriptor_id, name, value in SHORT:
        bus.publish(
            DescriptorComputed(
                descriptor=DescriptorValue(
                    descriptor_id=descriptor_id,
                    name=name,
                    units="",
                    category="physicochemical",
                    provider="rdkit",
                    molecule_uuid="mol-1",
                    value=value,
                    cache_state=CacheState.COMPLETED,
                )
            )
        )
    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="geometry_analysis",
                name="Geometry",
                molecule_uuid="mol-1",
                matched=GEOMETRY_LINES,
                category="physicochemical",
                cache_state=CacheState.COMPLETED,
                provenance=Provenance(created_by="core", method="test"),
            )
        )
    )
    for section in panel._sections.values():
        section.set_expanded(True)
    panel.resize(width, height)
    panel.show()
    # More than a couple of cycles on purpose. `WrappedLabel` derives its
    # minimum height from its CURRENT width, so the layout needs a few
    # passes to settle -- reading it too early measures a transient
    # mid-relayout state, which is how an earlier "reproduction" of this
    # bug turned out to be an artefact.
    for _ in range(40):
        qapp.processEvents()
    panel.adjustSize()
    for _ in range(20):
        qapp.processEvents()
    return panel


def _dispose(panel, qapp) -> None:
    from PySide6.QtCore import QCoreApplication, QEvent

    panel.hide()
    panel.setParent(None)
    panel.deleteLater()
    QCoreApplication.sendPostedEvents(panel, QEvent.Type.DeferredDelete)


def test_the_probe_can_see_a_clip_at_all(qapp):
    """The control. A clean report from `_lines_used` means nothing unless
    it can detect an obvious failure -- which is exactly how the previous,
    circular probe reported this panel healthy four times."""
    label = QLabel("word " * 200)
    label.setWordWrap(True)
    label.resize(180, 20)
    label.show()
    qapp.processEvents()
    assert _required_height(label) > label.contentsRect().height()
    assert _lines_used(label) > 10
    label.hide()
    label.deleteLater()


#: A wrapped row's field starts at the left margin and spans the panel;
#: a shared row's field starts after the label column. 0.8 separates them
#: with room to spare -- measured, the wrapped label takes 212 of a 240 px
#: panel (88%) while a shared one takes well under half.
_WRAPPED_FRACTION = 0.8


def test_a_long_result_gets_the_whole_panel_width(qapp):
    """170 px is what the running app's right-hand dock gave this panel,
    and the panel now refuses to be that narrow.

    ASSERTS THE WRAP, NOT A LINE COUNT, and that is not a weaker check --
    it is the only one that means the same thing on both platforms. The
    suite runs `QT_QPA_PLATFORM=offscreen`, whose default font is much
    wider than the real one: the longest line here needs 187 px on the
    platform a user sees and 420 px offscreen. A "renders in six lines"
    assertion would therefore be asserting the test environment's font.
    The row WRAPPING is font-independent, and it is the thing the fix
    actually does.
    """
    panel = _panel_with_a_long_result(qapp, width=170)
    try:
        label = next(iter(panel._alert_labels.values()))
        assert label.contentsRect().width() >= _WRAPPED_FRACTION * panel.width()
    finally:
        _dispose(panel, qapp)


def test_it_keeps_the_whole_width_across_the_range_the_dock_produces(qapp):
    """Not a single lucky width. The dock is user-resizable, so the
    property has to hold across the range rather than at one point --
    including the ~300 px dead zone where a smaller minimum left the
    field column too narrow to fit the text and too wide to trigger the
    wrap."""
    for width in (170, 240, 300, 400):
        panel = _panel_with_a_long_result(qapp, width=width)
        try:
            label = next(iter(panel._alert_labels.values()))
            assert label.contentsRect().width() >= _WRAPPED_FRACTION * panel.width(), width
        finally:
            _dispose(panel, qapp)


def test_nothing_is_actually_clipped(qapp):
    """The original complaint: text cut mid-glyph. Distinct from the
    ribbon problem above -- a label can use the right number of lines and
    still be given too little height for them."""
    panel = _panel_with_a_long_result(qapp, width=170)
    try:
        for label in panel._alert_labels.values():
            assert _required_height(label) - label.contentsRect().height() <= 1
    finally:
        _dispose(panel, qapp)


def test_a_short_value_still_shares_its_row_with_its_label(qapp):
    """The cost this fix exists to AVOID.

    `WrapAllRows` also renders long values correctly and was measured at
    +75% section height, because it moves every short scalar onto two
    rows and this panel is mostly short scalars. Short values must keep
    sharing a row, so the fix has to be selective.
    """
    panel = _panel_with_a_long_result(qapp, width=240)
    try:
        short = next(iter(panel._value_labels.values()))
        long_value = next(iter(panel._alert_labels.values()))
        # A shared row puts the value to the RIGHT of its label, so it
        # starts well into the panel; a wrapped row starts at the left.
        assert short.x() > long_value.x()
    finally:
        _dispose(panel, qapp)


def test_the_form_layout_wraps_long_rows_only(qapp):
    """Both halves of the mechanism, asserted where they live.

    Neither works alone: the policy without a minimum width never
    triggers (Qt wraps when the FIELD's minimum will not fit beside the
    label), and a minimum width without the policy just forces the panel
    wider.
    """
    from PySide6.QtWidgets import QFormLayout

    from openchem.ui.panels.property_panel import (
        _MULTILINE_VALUE_MIN_WIDTH,
        _PANEL_MIN_WIDTH,
    )

    section = CollapsibleSection("Test", expanded=True)
    try:
        assert (
            section.content_layout().rowWrapPolicy()
            == QFormLayout.RowWrapPolicy.WrapLongRows
        )
    finally:
        section.deleteLater()

    # THE THIRD HALF, and the one the first attempt got wrong. A minimum
    # on the value is a minimum on the CONTENT, so if the panel can be
    # narrower than the value demands, it scrolls SIDEWAYS instead of
    # wrapping -- measured as a horizontal scrollbar at every width below
    # 360 px. The panel's own minimum has to cover the value's.
    assert 0 < _MULTILINE_VALUE_MIN_WIDTH <= _PANEL_MIN_WIDTH


def test_the_panel_never_scrolls_sideways(qapp):
    """A properties panel that scrolls horizontally is worse than one
    that wraps, and that is exactly what the first two versions of this
    fix shipped.

    THE PANEL MUST BE SHORT ENOUGH TO NEED A VERTICAL SCROLLBAR, which
    is the whole point of the height below and is what the first version
    of this test got wrong. A scroll area's content gets its VIEWPORT
    width, not its own width, and the vertical scrollbar takes 24 px of
    it. Measured with a section short enough not to scroll, a 240 px
    minimum looked fine; in the running app, where the panel always
    scrolls, it produced a horizontal scrollbar.
    """
    from PySide6.QtWidgets import QScrollArea

    for width in (170, 200, 280, 340, 460):
        panel = _panel_with_a_long_result(qapp, width=width, height=320)
        try:
            scroll = panel.findChild(QScrollArea)
            assert scroll is not None
            assert scroll.verticalScrollBar().maximum() > 0, (
                f"at {width} px the content is too short to scroll -- this test "
                f"is not exercising the case it exists for"
            )
            assert scroll.horizontalScrollBar().maximum() == 0, width
        finally:
            _dispose(panel, qapp)
