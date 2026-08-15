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

from PySide6.QtCore import QCoreApplication, QEvent, QRect, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel, QScrollArea

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


def _calculator_definition_with_name(calculator_id: str, category: str, display_name: str):
    from openchem.domain.calculator import CalculatorDefinition, RegistryExecution

    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=display_name,
        category=category,
        description=display_name,
        execution=RegistryExecution(compute=lambda mol, uuid, params: None),
    )


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


def _widest_floor(qapp) -> int:
    """The narrowest width at which this panel is both REACHABLE and FITS.

    Two different numbers, and neither alone is the floor -- measured on
    Windows, where they disagree by 19 px:

        minimumWidth()             280   an explicit floor Qt will enforce
        minimumSizeHint().width()  299   what the LAYOUT says it needs

    The panel is therefore allowed to be squeezed 19 px below its own
    content minimum, and that gap is exactly where the horizontal
    scrollbar lives -- 280 overflows by 20 px, 300 by none. So a width
    below the size hint is not a defect when it scrolls sideways; it is
    Qt reporting that it was asked for something impossible.

    Taking `minimumSizeHint` alone is wrong too: on a Linux runner it
    reports 198 while `minimumWidth` still refuses anything under 280, so
    a width derived from it cannot be reached at all. The first attempt at
    this test did exactly that and asserted about a size that never
    happened -- caught immediately by the `panel.width() == width`
    assertion added beside it.

    The larger of the two is the only value that satisfies both.
    """
    panel = _panel_with_a_long_result(qapp, width=400, height=1000)
    try:
        panel.resize(1, panel.height())
        for _ in range(20):
            qapp.processEvents()
        return max(panel.width(), panel.minimumSizeHint().width())
    finally:
        _dispose(panel, qapp)


def _panel_forced_to_scroll(qapp, width: int):
    """A panel at `width` whose height GUARANTEES a vertical scrollbar.

    The height was hardcoded at 320 px, which was tuned on Windows font
    metrics. On a Linux runner the identical content is short enough to
    fit, no vertical scrollbar appears, and the test's own setup assertion
    fires -- **correctly**, because without that scrollbar the viewport
    never loses its 24 px and the horizontal-overflow case being tested
    does not arise. It was the first failure the non-blocking Linux job
    ever reported.

    The fix is NOT to relax that assertion, which is the one thing
    standing between this test and passing while exercising nothing. It is
    to stop guessing a height: measure what the content actually wants on
    THIS platform's fonts and ask for meaningfully less, so the
    precondition is true by construction anywhere.
    """
    from PySide6.QtWidgets import QScrollArea

    panel = _panel_with_a_long_result(qapp, width=width, height=1000)
    scroll = panel.findChild(QScrollArea)
    assert scroll is not None
    wanted = scroll.widget().sizeHint().height()

    # Half, with a floor so the panel stays a sane size. `adjustSize()` has
    # already run inside the helper, so nothing re-expands this afterwards.
    panel.resize(width, max(120, wanted // 2))
    for _ in range(40):
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


def test_no_layout_in_a_section_offers_a_height_for_width(qapp):
    """The mechanism that makes long values work, asserted where it lives.

    **A vertical `QBoxLayout` OVERWRITES a height-for-width item's minimum
    with its `heightForWidth` before distributing space.** One such widget
    anywhere inside a section makes every ancestor layout height-for-width
    carrying, and from there no minimum stated anywhere can win: measured
    in the running app, a section asked for 225 px and was given 113 while
    its own layout item reported `minSize=225 hfw=75`. Its report row got
    14 px of the 144 it needed, and an unrelated `formula` row in the same
    section dropped from 16 px to 14 -- the tell that the field was never
    the problem.

    Eight fixes were designed against the field before this was measured.
    This test is the guard on the answer, so it checks the whole chain
    rather than one widget.
    """
    panel = _panel_with_a_long_result(qapp, width=280)
    try:
        for name, section in panel._sections.items():
            if section.isHidden() or not section.is_expanded():
                continue
            assert not section.content_layout().hasHeightForWidth(), (
                f"the {name} form offers a height-for-width, so every section "
                f"above it loses its minimum"
            )
            assert not section.content.layout().hasHeightForWidth(), name
            assert not section.layout().hasHeightForWidth(), name
    finally:
        _dispose(panel, qapp)


def test_the_wrap_policy_is_the_one_that_can_be_free_of_height_for_width(qapp):
    """`WrapLongRows` is height-for-width WHATEVER its children are.

    Whether a row wraps depends on the width, so the form's height does
    too -- which is why the policy itself, not any label, is half of what
    truncated report rows. Measured across all three:

        policy          hfw items   non-hfw items
        DontWrapRows    True        False
        WrapLongRows    True        True     <- unavoidable
        WrapAllRows     True        False

    `WrapAllRows` is the other safe one and is rejected for a different,
    measured reason: it moves every short scalar onto two rows, +75%
    section height, and this panel is mostly short scalars.
    """
    from PySide6.QtWidgets import QFormLayout

    section = CollapsibleSection("Test", expanded=True)
    try:
        assert (
            section.content_layout().rowWrapPolicy()
            == QFormLayout.RowWrapPolicy.DontWrapRows
        )
    finally:
        section.deleteLater()


def test_a_long_value_is_added_as_a_spanning_row(qapp):
    """The full width comes from a SPANNING row now, not from the wrap
    policy -- so it must actually be one.

    The old mechanism forced the field's minimum wide enough that Qt had
    to wrap the row. That minimum was also a minimum on the CONTENT, so
    below ~360 px the panel scrolled sideways instead of wrapping. Asking
    for a spanning row says the same thing with nothing forced wide, and
    `test_the_panel_never_scrolls_sideways` is what holds that gain.
    """
    from PySide6.QtWidgets import QFormLayout

    panel = _panel_with_a_long_result(qapp, width=280)
    try:
        long_value = next(iter(panel._alert_labels.values()))
        form = None
        for section in panel._sections.values():
            if long_value in section.content.findChildren(type(long_value)):
                form = section.content_layout()
                break
        assert form is not None, "the long value is not in any section"
        spanning = [
            form.itemAt(row, QFormLayout.ItemRole.SpanningRole)
            for row in range(form.rowCount())
        ]
        holders = [item.widget() for item in spanning if item is not None]
        assert any(long_value in holder.findChildren(type(long_value)) for holder in holders), (
            "the long value is not in a spanning row, so it only has the "
            "field column's width"
        )
    finally:
        _dispose(panel, qapp)


def test_an_explicit_height_label_never_offers_a_height_for_width_after_setText(qapp):
    """The trap that made a half-applied fix WORSE than none.

    `QLabelPrivate::updateLabel()` re-derives the size policy's
    height-for-width flag from the word-wrap flag on every label update,
    so clearing it in `__init__` is silently undone by the first
    `setText`. Measured when this was got wrong: the label held a correct
    fixed height while the chain stayed height-for-width carrying, the
    section collapsed to 75 px and its rows were crushed to 3 px each,
    against 14 before.
    """
    from openchem.ui.widgets.collapsible_section import ExplicitHeightLabel

    label = ExplicitHeightLabel("")
    try:
        assert not label.sizePolicy().hasHeightForWidth()
        label.setText("a value\nwith several\nlines in it")
        assert not label.sizePolicy().hasHeightForWidth(), (
            "setText put the height-for-width flag back -- see "
            "ExplicitHeightLabel._stop_offering_height_for_width"
        )
        assert not label.hasHeightForWidth()
    finally:
        label.deleteLater()


def test_an_explicit_height_label_never_offers_a_height_for_width_after_a_style_change(qapp):
    """A STYLE CHANGE re-derives the flag, and `setText` is not the only
    door -- the guard above passed for the whole life of this bug.

    `QLabel::changeEvent` answers `StyleChange` and `FontChange` by
    calling the same `QLabelPrivate::updateLabel()` that `setText` does,
    so a style sheet set on ANY ancestor re-arms the height-for-width
    flag on every wrapped label beneath it, long after the last
    `setText`. Nothing on the label itself changes, which is why this
    was invisible to every existing test.

    Measured in the running app by logging each transition of the flag,
    Lipophilicity section, panel at 280 px:

        '13 atoms, -0.4195 to 0.5437'  re-set hfw on event 100
                                                 (QEvent::StyleChange)

    The plain `QLabel` arm is the CONTROL and is not decoration: if
    `setStyleSheet` on the parent ever stopped delivering a StyleChange
    to its children, the interesting assertion below would pass while
    testing nothing at all.

    **THERE IS DELIBERATELY NO SYMPTOM-LEVEL GUARD BESIDE THIS ONE**,
    and that is a measured limit rather than an omission. In the running
    app the flag costs the Lipophilicity section 47 px -- given 145
    against the 192 it asks for, crushing its three calculator buttons
    to 15/15/14 px against their own 26 px minimum, which is the
    overlap that was reported. A panel built here cannot reproduce it:
    the section's `heightForWidth` and its minimum come out EQUAL
    (measured, 418 and 418 at 280 px), so the substitution has nothing
    to take away and no arrangement of siblings starves anything. Two
    versions of such a test were written and both passed with the bug
    deliberately restored -- a shorter panel, then one with the
    calculator buttons registered.

    This is the fifth time an out-of-app harness has disagreed with the
    running application about THIS panel; see the four in `CLAUDE.md`.
    The symptom was verified where it lives, by driving the app.
    """
    from PySide6.QtWidgets import QWidget

    from openchem.ui.widgets.collapsible_section import ExplicitHeightLabel

    parent = QWidget()
    ours = ExplicitHeightLabel("a value\nwith several\nlines in it", parent)
    plain = QLabel("a value\nwith several\nlines in it", parent)
    plain.setWordWrap(True)
    try:
        assert not ours.sizePolicy().hasHeightForWidth()
        parent.setStyleSheet("QLabel { color: #555; }")
        qapp.processEvents()
        assert plain.sizePolicy().hasHeightForWidth(), (
            "the control did not pick up a height-for-width, so the style "
            "change never reached the children and this test proves nothing"
        )
        assert not ours.sizePolicy().hasHeightForWidth(), (
            "a style change on an ancestor put the height-for-width flag "
            "back -- see ExplicitHeightLabel.changeEvent"
        )
        assert not ours.hasHeightForWidth()
    finally:
        parent.deleteLater()
        QCoreApplication.sendPostedEvents(parent, QEvent.Type.DeferredDelete)


def test_the_panel_has_no_horizontal_scrollbar(qapp):
    """A SECONDARY invariant. **The absence of a horizontal scrollbar
    does NOT prove the absence of clipping**, and this test is renamed
    from `test_the_panel_never_scrolls_sideways` because that name
    claimed it did.

    It passed, unchanged and on every platform, while the running app
    clipped the last character off every visual line of the Properties
    panel -- content 272 px against a 256 px viewport, every row laid
    out 14 px past the right edge. A scrollbar's `maximum()` is a fact
    about one widget's range; whether painted text left the viewport is
    a different question, and only the second one is the symptom.

    `test_no_row_is_rendered_past_the_scroll_viewport` is the
    authoritative oracle. This is kept because a horizontal scrollbar in
    THIS panel is independently unwanted -- the project calls a
    sideways-scrolling properties panel worse than a wrapping one -- and
    because a regression that reintroduces one should name itself here
    as well as there.

    THE PANEL MUST BE SHORT ENOUGH TO NEED A VERTICAL SCROLLBAR, which
    is the whole point of the height below and is what the first version
    of this test got wrong. A scroll area's content gets its VIEWPORT
    width, not its own width, and the vertical scrollbar takes 24 px of
    it. Measured with a section short enough not to scroll, a 240 px
    minimum looked fine; in the running app, where the panel always
    scrolls, it produced a horizontal scrollbar.
    """
    from PySide6.QtWidgets import QScrollArea

    floor = _widest_floor(qapp)

    # RELATIVE TO THE PANEL'S OWN DECLARED MINIMUM, not five hardcoded
    # pixel widths. Two separate reasons, both learned from a Linux runner:
    #
    # The widths used to be (170, 200, 280, 340, 460) and FOUR OF THE FIVE
    # were never tested. `_panel_with_a_long_result` ends with
    # `adjustSize()`, which expands the panel to its sizeHint and discards
    # the requested width -- measured, every one of those five came out at
    # 388 px. The test asserted five times about one size.
    #
    # And a width BELOW the panel's declared minimum is not a defect when
    # it scrolls sideways: it is Qt correctly reporting that it was asked
    # for something impossible. Measured, the overflow closes exactly at
    # the declared minimum -- 280 px overflows by 20, 290 by 10, 298 by 2,
    # and 300 px and everything above by 0. Hardcoded pixels also encode
    # one platform's font metrics, which is what made the old height fail
    # on Linux in the first place.
    for width in (floor + 1, floor + 40, floor + 80, floor + 160, floor + 300):
        panel = _panel_forced_to_scroll(qapp, width=width)
        try:
            scroll = panel.findChild(QScrollArea)
            assert scroll is not None
            assert panel.width() == width, (
                f"asked for {width} px and got {panel.width()} -- the panel is not "
                "actually at the width being tested, which is how the previous "
                "version of this test asserted five times about one size"
            )
            assert scroll.verticalScrollBar().maximum() > 0, (
                f"at {width} px the content is too short to scroll -- this test "
                f"is not exercising the case it exists for"
            )
            assert scroll.horizontalScrollBar().maximum() == 0, width
        finally:
            _dispose(panel, qapp)


def test_a_long_calculator_name_does_not_widen_the_panel(qapp):
    """The widest thing in this panel is a BUTTON, not a value.

    `QPushButton` refuses to be narrower than its text, and a scroll area
    sizes its content to `max(viewport, minimum)` -- so one long
    "Open [Calculator]..." label pushes every row past the right edge and
    the values are clipped there. Measured in the running app with the
    ADMET section open at the panel's 280 px minimum: viewport 256,
    content 287, that section's minimum 287 while its form's was 184.
    The rows were never the problem, and the symptom
    (`(93rd percentile amo` where a wrap belonged) reads exactly like one.

    `test_the_panel_never_scrolls_sideways` cannot catch this: it builds
    the panel with a registry holding only what it registers, so no
    long-named button ever exists. This one registers the long name on
    purpose.
    """
    from openchem.services.calculator_registry import CalculatorRegistry
    from openchem.ui.panels.property_panel import PropertyPanel

    registry = CalculatorRegistry()
    registry.register(
        _calculator_definition_with_name(
            "monstrous", "physicochemical",
            "Absolutely Enormous Calculator Name (hERG, CYP, Ames, ADME, and more)",
        )
    )
    bus = EventBus()
    panel = PropertyPanel(bus, registry, _FakeService(), ChemistryEngine())
    try:
        panel.resize(280, 400)
        panel.show()
        qapp.processEvents()
        scroll = panel.findChild(QScrollArea)
        assert scroll is not None
        content = scroll.widget().minimumSizeHint().width()
        viewport = scroll.viewport().width()
        assert content <= viewport, (
            f"content needs {content} px against a {viewport} px viewport, so every "
            f"row is clipped on the right"
        )
    finally:
        panel.setParent(None)
        panel.deleteLater()
        QCoreApplication.sendPostedEvents(panel, QEvent.Type.DeferredDelete)


# --- the WIDTH oracle -------------------------------------------------------
#
# Everything above this line measures HEIGHT. `_required_height` and
# `_lines_used` both derive a height from `QFontMetrics.boundingRect` at the
# label's own `contentsRect().width()`, so neither can see a label that was
# laid out wider than the viewport it is drawn in -- and that is what the
# panel was doing: content 272 px against a 256 px viewport, every row 14 px
# past the right edge, every visual line losing its last character.
# Recoverable by scrolling right, which is why it read as a cosmetic
# annoyance rather than as the layout fault it was.


def _settle(qapp, passes: int = 40) -> None:
    """Let the layout finish.

    `_ElidingCaptionLabel` re-elides on resize, so its final text is only
    knowable after the passes have run -- reading earlier measures a
    transient, which this file already records as the source of one false
    reproduction of the height bug.
    """
    for _ in range(passes):
        qapp.processEvents()


def _text_of_at_least(width: int, widget) -> str:
    """A caption whose UNELIDED width is at least `width` px.

    Built from font metrics rather than from a hardcoded string, so the
    boundary it probes is the real one on this platform's fonts. This file
    already records what hardcoded pixels cost: five widths that were
    secretly all the same size, and a height tuned on Windows that failed on
    a Linux runner.
    """
    metrics = QFontMetrics(widget.font())
    text = "Wide caption "
    while metrics.horizontalAdvance(text) < width:
        text += "wider "
    return text


def _plain_caption(text: str, parent):
    """The caption widget as the panel built it BEFORE the fix: a plain
    `QLabel`, word wrap off, whose `minimumSizeHint` is its whole text
    width. `QFormLayout.addRow(str, widget)` builds exactly this."""
    label = QLabel(text, parent)
    label.setWordWrap(False)
    return label


def test_no_row_is_rendered_past_the_scroll_viewport(qapp):
    """THE ORACLE. Nothing the panel paints may leave its viewport.

    Swept across the range the dock produces rather than asserted at one
    width, and the widths come from the panel's own declared minimum via
    `_widest_floor` -- not from invented pixel numbers, for the reason
    `test_the_panel_has_no_horizontal_scrollbar` records.

    The panel is forced to scroll VERTICALLY on purpose: the vertical
    scrollbar is what takes ~12 px off the viewport, and the defect only
    appeared once it did. Measured in the running app, the same panel was
    clean at viewport 268 and overflowed at 256.

    **IT ADDS A LONG CAPTION, AND WITHOUT THAT IT TESTED NOTHING.** The
    shared fixture's captions are "LogP", "TPSA", "Ring Count" -- none wider
    than about a third of the viewport, so no arrangement of them can push
    the content past its edge. Measured: with the fixture's own rows only,
    removing the cap from `_ElidingCaptionLabel.minimumSizeHint` -- the whole
    of the fix -- left this test passing. The real panel's widest caption is
    "Blood-Brain Barrier Permeant (heuristic)" at 210 px against a 256 px
    viewport, and a guard that never holds one cannot see the bug.
    """
    from openchem.ui.panels.property_panel import _ElidingCaptionLabel, rendered_overflow

    floor = _widest_floor(qapp)
    for width in (floor + 1, floor + 40, floor + 80, floor + 160, floor + 300):
        panel = _panel_forced_to_scroll(qapp, width=width)
        try:
            _settle(qapp)
            viewport = panel.findChild(QScrollArea).viewport().width()

            # The production widget, carrying a caption wider than the whole
            # viewport -- the condition the app is in, made unmissable. Sized
            # from font metrics so it crosses the boundary on any platform.
            section = next(iter(panel._sections.values()))
            section.content_layout().addRow(
                _ElidingCaptionLabel(_text_of_at_least(viewport + 1, panel), section.content),
                QLabel("value", section.content),
            )
            _settle(qapp)

            findings = rendered_overflow(panel)
            assert not findings, "\n".join(
                [f"at panel width {width} (viewport {viewport}):"]
                + ["  " + finding.describe(viewport) for finding in findings]
            )
        finally:
            _dispose(panel, qapp)


def test_a_long_descriptor_caption_does_not_widen_the_panel(qapp):
    """The same invariant, reached through the PRODUCTION PATH.

    **The test above wires its caption by hand and therefore cannot see a
    regression at the call site.** Measured: reverting
    `_on_descriptor_computed` to `addRow(label_string, value)` -- which is
    exactly how the bug shipped, since `QFormLayout` then builds a plain
    non-eliding `QLabel` for you -- left every other test in this file
    passing, including the oracle. The caption has to arrive the way the app
    makes it arrive, from a `DescriptorComputed` carrying a long name.

    A real one is 40 characters ("Blood-Brain Barrier Permeant (heuristic)");
    this one is sized from font metrics so it crosses the boundary whatever
    the platform's fonts do.
    """
    from openchem.ui.panels.property_panel import rendered_overflow

    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _FakeService(), ChemistryEngine())
    try:
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
        for section in panel._sections.values():
            section.set_expanded(True)
        panel.resize(_widest_floor(qapp) + 1, 400)
        panel.show()
        _settle(qapp)

        viewport = panel.findChild(QScrollArea).viewport().width()
        bus.publish(
            DescriptorComputed(
                descriptor=DescriptorValue(
                    descriptor_id="a_very_long_one",
                    name=_text_of_at_least(viewport + 1, panel),
                    units="",
                    category="physicochemical",
                    provider="rdkit",
                    molecule_uuid="mol-1",
                    value=1.0,
                    cache_state=CacheState.COMPLETED,
                )
            )
        )
        _settle(qapp)

        findings = rendered_overflow(panel)
        assert not findings, "\n".join(
            [f"a long descriptor caption widened the panel (viewport {viewport}):"]
            + ["  " + finding.describe(viewport) for finding in findings]
        )
    finally:
        _dispose(panel, qapp)


def test_a_long_report_caption_does_not_widen_the_panel(qapp):
    """`_add_wide_row`'s caption is a SECOND path to the same defect.

    A spanning row builds its own caption rather than letting `QFormLayout`
    make one, and that caption was a plain `QLabel` with word wrap off for
    the same stated reason -- a wrapped one would be height-for-width and
    would put back the truncation the whole section exists to prevent. Word
    wrap off is right; reporting the full text width as a minimum is what
    was wrong, and the helper's docstring claimed the opposite ("nothing
    needs to be forced wide now, so nothing can overflow").

    The row-label path is covered above. This one arrives as a REPORT,
    which is how the app reaches this helper.

    **THE MARGIN OVER THE VIEWPORT IS 40 px, NOT 1, AND THAT IS THE
    DIFFERENCE BETWEEN A GUARD AND A DECORATION.** A spanning row has no
    field column beside it, so the overflow it produces is just
    `caption - viewport` rather than `caption + field - viewport`. At one
    pixel over, reverting this caption to a plain `QLabel` moved the
    content from 290 to 293 -- a 3 px demand that the row's own margins
    absorbed down to within `_OVERFLOW_TOLERANCE`, so the mutation passed
    and this test proved nothing. The real defect was 16 px; 40 puts the
    probe unambiguously past the noise it is allowed to ignore.
    """
    from openchem.domain.report import ReportResult
    from openchem.events.events import ReportComputed
    from openchem.ui.panels.property_panel import rendered_overflow

    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _FakeService(), ChemistryEngine())
    try:
        bus.publish(MoleculeSelected(molecule_uuid="mol-1"))
        for section in panel._sections.values():
            section.set_expanded(True)
        panel.resize(_widest_floor(qapp) + 1, 400)
        panel.show()
        _settle(qapp)

        viewport = panel.findChild(QScrollArea).viewport().width()
        bus.publish(
            ReportComputed(
                report=ReportResult(
                    molecule_uuid="mol-1",
                    report_id="wide_caption",
                    name=_text_of_at_least(viewport + 40, panel),
                    category="physicochemical",
                    facts=(),
                    cache_state=CacheState.COMPLETED,
                    provenance=Provenance(created_by="core", method="test"),
                )
            )
        )
        _settle(qapp)

        findings = rendered_overflow(panel)
        assert not findings, "\n".join(
            [f"a long report caption widened the panel (viewport {viewport}):"]
            + ["  " + finding.describe(viewport) for finding in findings]
        )
    finally:
        _dispose(panel, qapp)


def test_the_overflow_probe_can_see_a_clip_at_all(qapp):
    """THE CONTROL, and simultaneously a mutation of the FIX itself.

    A probe that cannot say "yes" is worth nothing -- this file already
    carries that argument for the height side, where a circular probe
    reported the panel healthy four times running.

    What makes this the stronger form: it does not fake an overflow by
    resizing something. It rebuilds the caption **the way the panel built it
    before the fix** -- a plain `QLabel` with word wrap off, which is
    literally what `QFormLayout.addRow(str, widget)` creates -- and requires
    the oracle to fail. So the guard is pinned to the implementation
    mechanism that caused the bug rather than to a fixture: swapping
    `_ElidingCaptionLabel` back for a plain label fails here, naming the
    widget and the pixel count.

    It ASSERTS ITS OWN SETUP first. Without the clean reading, the overflow
    afterwards would prove nothing about the caption -- the panel might have
    been overflowing for some other reason all along.
    """
    from openchem.ui.panels.property_panel import rendered_overflow

    panel = _panel_forced_to_scroll(qapp, width=_widest_floor(qapp) + 1)
    try:
        _settle(qapp)
        assert not rendered_overflow(panel), (
            "the panel already overflows before the caption is added, so this test "
            "cannot attribute anything to the caption"
        )
        viewport = panel.findChild(QScrollArea).viewport().width()

        section = next(iter(panel._sections.values()))
        caption = _plain_caption(_text_of_at_least(viewport + 1, panel), section.content)
        section.content_layout().addRow(caption, QLabel("value", section.content))
        _settle(qapp)

        assert rendered_overflow(panel), (
            f"a non-eliding caption wider than the {viewport} px viewport was added "
            "and the probe reported nothing -- it cannot detect the defect it exists for"
        )
    finally:
        _dispose(panel, qapp)


def test_a_caption_that_fits_is_not_reported_as_overflow(qapp):
    """THE NEGATIVE CONTROL. A detector that flagged every long caption
    would pass the test above while making the oracle worthless.

    Same construction as the control, one step the other way: a caption
    comfortably inside the viewport, added as the same plain non-eliding
    `QLabel`, must NOT be reported. The pair is what says the probe measures
    the boundary rather than the length.
    """
    from openchem.ui.panels.property_panel import rendered_overflow

    panel = _panel_forced_to_scroll(qapp, width=_widest_floor(qapp) + 1)
    try:
        _settle(qapp)
        viewport = panel.findChild(QScrollArea).viewport().width()

        section = next(iter(panel._sections.values()))
        # Half the viewport: long enough to be a real caption, short enough
        # that no part of it can reach an edge.
        caption = _plain_caption(_text_of_at_least(viewport // 2, panel), section.content)
        section.content_layout().addRow(caption, QLabel("v", section.content))
        _settle(qapp)

        findings = rendered_overflow(panel)
        assert not findings, "\n".join(
            ["a caption that fits was reported as overflow:"]
            + ["  " + finding.describe(viewport) for finding in findings]
        )
    finally:
        _dispose(panel, qapp)


def test_the_two_reported_lines_render_in_full(qapp):
    """The two strings the bug was REPORTED on, taken from the real
    calculator rather than retyped.

    The user saw the untouched Schedule 2 "Legitimate uses" line losing the
    last character of every visual line, and then the new bad-date refusal
    riding on the same defect -- `...or leave the field blank...` rendering
    as `...leave the field bla`.

    Three assertions, because they are three different claims and the
    geometry one alone would not have caught the original report:

        the stored text is COMPLETE     no message was shortened to fit
        nothing is rendered past the viewport
        the row is actually PAINTED     a widget can satisfy both above
                                        while drawing nothing at all

    **Byte-equality is about the STORED text, not the visual layout.** The
    value wraps across several lines on screen and is expected to; what must
    not happen is a character going missing, or somebody "fixing" the width
    by trimming the sentence. Taking the strings from
    `compute_regulatory_screen` is what makes the second of those fail here.

    **THE PANEL IS SIZED FROM ITS OWN CONTENT, AND THAT IS NOT A DODGE.**
    These are REAL strings of fixed length, so any width asserted against
    them is really an assertion about the font -- and the suite runs
    `offscreen`, whose default font this file already records as more than
    twice as wide as the one a user sees (187 px against 420 for the same
    line). Pinned at a fixed width this test failed by 40 px on a panel that
    is measurably clean in the running app. Giving the panel room for its
    content first keeps the claim font-independent: *given somewhere to put
    it, none of this text is painted outside the viewport*. The claim that
    the panel FITS at its own minimum is a different one, and it is made by
    the three tests above, whose captions are sized from font metrics and so
    mean the same thing on every platform.
    """
    from rdkit import Chem

    from openchem.chem.regulatory.calculator import compute_regulatory_screen
    from openchem.events.events import ReportComputed
    from openchem.ui.panels.property_panel import rendered_overflow
    from tests.conftest import ink

    mol = Chem.MolFromSmiles("COP(C)(=O)OC")  # dimethyl methylphosphonate
    screened = compute_regulatory_screen(mol, "mol-1", {})
    refused = compute_regulatory_screen(mol, "mol-1", {"as_of": "2019/13/99"})

    legitimate = next(f for f in screened.facts if f.label == "Legitimate uses")
    assert refused.error, "the refusal carries no message, so there is nothing to render"

    for report, expected in ((screened, legitimate.display_value), (refused, refused.error)):
        bus = EventBus()
        panel = PropertyPanel(bus, CalculatorRegistry(), _FakeService(), ChemistryEngine())
        try:
            bus.publish(MoleculeSelected(molecule_uuid="mol-1"))
            bus.publish(ReportComputed(report=report))
            for section in panel._sections.values():
                section.set_expanded(True)
            panel.resize(_widest_floor(qapp) + 1, 500)
            panel.show()
            _settle(qapp)

            # Room for the content, whatever this platform's font makes of
            # it -- see the docstring. The vertical scrollbar's width is
            # added back because it is taken off the viewport, which is the
            # very subtraction that produced the original defect.
            scroll = panel.findChild(QScrollArea)
            needed = scroll.widget().minimumSizeHint().width()
            bar = scroll.verticalScrollBar().sizeHint().width()
            panel.resize(max(panel.width(), needed + bar + 8), 500)
            _settle(qapp)

            label = panel._report_labels["regulatory_screen"]
            assert expected in label.text(), (
                f"the panel dropped part of the message.\n  wanted: {expected!r}\n"
                f"  showed: {label.text()[:300]!r}"
            )
            viewport = panel.findChild(QScrollArea).viewport().width()
            findings = rendered_overflow(panel)
            assert not findings, "\n".join(
                [f"the reported line overflowed (viewport {viewport}):"]
                + ["  " + finding.describe(viewport) for finding in findings]
            )
            assert ink(label) > 0, "the row holds the text and paints nothing"
        finally:
            _dispose(panel, qapp)


def test_copying_the_panel_gives_the_full_caption_not_the_elided_one(qapp):
    """An elided caption is a WIDTH decision, and it must not reach the
    clipboard.

    `_ElidingCaptionLabel.text()` is what is painted, so a caption squeezed
    on a narrow panel reads `Blood-Brain Barrier Permeant (heur...`. Exported
    through "Copy all" that is the presentation layer corrupting data on its
    way out -- the same class of mistake `_without_glyphs` already exists to
    prevent on the value side, and this panel has a recorded history of
    presentation decisions leaking into what the numbers mean.
    """
    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _FakeService(), ChemistryEngine())
    try:
        bus.publish(MoleculeSelected(molecule_uuid="mol-1"))
        for section in panel._sections.values():
            section.set_expanded(True)
        panel.resize(_widest_floor(qapp) + 1, 400)
        panel.show()
        _settle(qapp)

        # SIZED FROM FONT METRICS AGAINST THE REAL VIEWPORT, so the caption
        # is certain to elide whatever the platform's font is. A fixed
        # string does not do this: a 59-character name chosen by hand fitted
        # comfortably here and the test's own setup assertion caught it
        # rendering unelided, proving nothing about the export path.
        viewport = panel.findChild(QScrollArea).viewport().width()
        long_name = _text_of_at_least(viewport + 1, panel)
        bus.publish(
            DescriptorComputed(
                descriptor=DescriptorValue(
                    descriptor_id="bbb",
                    name=long_name,
                    units="",
                    category="physicochemical",
                    provider="rdkit",
                    molecule_uuid="mol-1",
                    value="Pass",
                    cache_state=CacheState.COMPLETED,
                )
            )
        )
        _settle(qapp)

        caption = next(
            child
            for child in panel.findChildren(QLabel)
            if getattr(child, "full_text", "") == long_name
        )
        assert caption.text() != long_name, (
            "the caption was not elided at this width, so this test is not "
            "exercising the case it exists for"
        )
        assert long_name in panel.as_text(), (
            f"'Copy all' exported the elided caption {caption.text()!r} instead of "
            "the full one"
        )
    finally:
        _dispose(panel, qapp)


def test_the_viewport_does_not_shrink_to_fit_long_content(qapp):
    """The invariant is *content adapts to the viewport*, and the opposite is
    a way of passing every other test here while making the panel worse.

    A fix that narrowed the viewport instead of the content would show zero
    overflow, no horizontal scrollbar, and less visible text than before --
    indistinguishable from success by any assertion that only counts
    findings.
    """
    panel = _panel_forced_to_scroll(qapp, width=_widest_floor(qapp) + 80)
    try:
        _settle(qapp)
        scroll = panel.findChild(QScrollArea)
        before = scroll.viewport().width()

        section = next(iter(panel._sections.values()))
        section.content_layout().addRow(
            _text_of_at_least(before * 2, panel), QLabel("value", section.content)
        )
        _settle(qapp)

        after = scroll.viewport().width()
        assert after >= before, (
            f"the viewport shrank from {before} px to {after} px when long content "
            "arrived -- content must adapt to the viewport, not the other way round"
        )
    finally:
        _dispose(panel, qapp)
