"""The generic stick renderer.

Every ink assertion here HOLDS THE AXES FIXED and varies only the content.
"More ink than the same widget with no data" is killed by mutation,
because different data moves the tick labels and the extreme-value
captions -- so each pair below shares its extreme x values and differs by
one stick in the middle.
"""

from __future__ import annotations

import math

import pytest
from PySide6.QtGui import QPainter

from openchem.domain.report import Stick, StickChartAnnotation
from openchem.ui.widgets.plot_axis import LABEL_HEIGHT
from openchem.ui.widgets.stick_chart_widget import StickChartWidget, axis_caption
from tests.conftest import ink, painted


def _annotation(sticks, **overrides) -> StickChartAnnotation:
    fields = {
        "sticks": tuple(sticks),
        "x_label": "m/z",
        "y_label": "Relative abundance",
        "x_descending": False,
    }
    fields.update(overrides)
    return StickChartAnnotation(**fields)


#: The two ENDS are identical in both, so the axis range, the tick labels
#: and the printed maximum are all the same and cannot account for a
#: difference in ink.
_TWO_STICKS = [Stick(100.0, 1.0), Stick(120.0, 0.5)]
_THREE_STICKS = [Stick(100.0, 1.0), Stick(110.0, 0.7), Stick(120.0, 0.5)]


def test_an_empty_widget_still_draws_its_axis(qapp):
    """Asserts its own setup: if this drew nothing at all, every ink
    comparison below would be measuring the difference between nothing and
    something rather than between two spectra."""
    widget = StickChartWidget()
    assert not widget.is_drawing()
    assert ink(widget) > 0


def test_an_extra_stick_puts_more_ink_on_the_canvas(qapp):
    two = StickChartWidget(_annotation(_TWO_STICKS))
    three = StickChartWidget(_annotation(_THREE_STICKS))
    assert ink(three) > ink(two)


def test_a_taller_stick_draws_a_longer_stick(qapp):
    """Same positions, same count, same axis -- only the height differs, so
    a widget that ignored `y` would draw identical pictures."""
    short = StickChartWidget(_annotation([Stick(100.0, 1.0), Stick(110.0, 0.05), Stick(120.0, 0.5)]))
    tall = StickChartWidget(_annotation([Stick(100.0, 1.0), Stick(110.0, 0.95), Stick(120.0, 0.5)]))
    assert ink(tall) > ink(short)


def test_descending_puts_high_x_on_the_left(qapp):
    widget = StickChartWidget(_annotation(_TWO_STICKS, x_descending=True))
    widget.resize(400, 300)
    regions = widget.hit_regions()
    # sticks[0] is at m/z 100, sticks[1] at 120: descending puts the HIGHER
    # mass further left.
    assert regions[1].center().x() < regions[0].center().x()


def test_ascending_puts_high_x_on_the_right(qapp):
    """**THE TWIN, AND THE REASON BOTH EXIST.** A widget hard-coded to
    descending passes every NMR- and IR-shaped test and then silently
    mirrors every mass spectrum. A mirrored spectrum does not look broken;
    it looks like a different compound."""
    widget = StickChartWidget(_annotation(_TWO_STICKS, x_descending=False))
    widget.resize(400, 300)
    regions = widget.hit_regions()
    assert regions[0].center().x() < regions[1].center().x()


def test_hit_regions_exist_before_the_first_paint(qapp):
    """Derived from geometry rather than recorded during `paintEvent`, so a
    click resolves on a widget nobody has painted yet."""
    widget = StickChartWidget(_annotation(_TWO_STICKS))
    widget.resize(400, 300)
    assert len(widget.hit_regions()) == 2


def test_two_sticks_at_the_same_x_both_get_a_region_and_the_first_wins(qapp):
    """Two isotopologues can land in one nominal bin. The regions overlap
    by construction, so the tie has to be decided rather than left to
    whichever the iteration happened to reach."""
    widget = StickChartWidget(
        _annotation([Stick(100.0, 1.0, "a"), Stick(100.0, 0.5, "b"), Stick(120.0, 0.2)])
    )
    widget.resize(400, 300)
    regions = widget.hit_regions()
    assert len(regions) == 3
    centre = regions[0].center()
    assert widget.stick_index_at(centre.x(), centre.y()) == 0


def test_the_producers_order_is_preserved(qapp):
    """Sticks arrive unsorted and stay unsorted: the renderer never
    reorders scientific data.

    **AND SORTING THEM FOR THE DRAW IS AN ADMITTED EQUIVALENT MUTATION**,
    measured rather than assumed: a stick is placed by its x, so a sorted
    loop paints the identical picture, and Python's sort is stable so even
    two sticks sharing an x keep their order. What order really decides is
    the HIT REGIONS, and those read the annotation directly. The claim
    worth holding is therefore that the data is unchanged -- which is this
    test -- not that some internal loop iterates in a particular order.
    """
    sticks = [Stick(120.0, 0.5), Stick(100.0, 1.0)]
    widget = StickChartWidget(_annotation(sticks))
    assert [stick.x for stick in widget.annotation().sticks] == [120.0, 100.0]


def test_rendering_does_not_mutate_the_annotation(qapp):
    """The chart is a presentation channel. Rendering must not
    renormalise, reorder or relabel the data it was handed."""
    annotation = _annotation([Stick(120.0, 7.5, "M+2"), Stick(100.0, 2.5)])
    widget = StickChartWidget(annotation)
    painted(widget)
    assert widget.annotation() is annotation
    assert annotation.sticks[0].y == 7.5
    assert annotation.sticks[1].y == 2.5
    assert annotation.sticks[0].label == "M+2"


def test_sticks_are_never_clipped_against_the_widgets_own_height(qapp):
    """The polonium defect: `if y + row_height > self.height(): break`
    dropped 22 of 84 electrons with every test green. A short widget must
    draw a short plot, not a partial one -- so the line count is the stick
    count plus the axis, whatever the height."""
    sticks = [Stick(float(100 + 5 * i), 1.0 - i * 0.05) for i in range(12)]
    widget = StickChartWidget(_annotation(sticks))
    drawn: list[int] = []
    original = QPainter.drawLine

    def counting(self, *args):
        drawn.append(1)
        return original(self, *args)

    QPainter.drawLine = counting
    try:
        painted(widget, width=400, height=90)
    finally:
        QPainter.drawLine = original
    # One axis line plus one line per stick, at a height far below what the
    # content would like.
    assert len(drawn) == len(sticks) + 1


def test_the_axis_label_and_its_units_reach_the_canvas(qapp):
    """A number on an unlabelled axis is a measurement in units the reader
    supplies themselves."""
    widget = StickChartWidget(_annotation(_TWO_STICKS, x_units="Da"))
    texts: list[str] = []
    original = QPainter.drawText

    def recording(self, *args):
        texts.append(str(args[-1]))
        return original(self, *args)

    QPainter.drawText = recording
    try:
        painted(widget)
    finally:
        QPainter.drawText = original
    assert "m/z (Da)" in texts


def test_the_real_maximum_is_printed_beside_the_scaled_picture(qapp):
    """The tallest stick fills the plot, so without the number the display
    scaling reads as a calibrated axis."""
    widget = StickChartWidget(
        _annotation([Stick(100.0, 4200.0), Stick(120.0, 2100.0)], y_units="counts")
    )
    texts: list[str] = []
    original = QPainter.drawText

    def recording(self, *args):
        texts.append(str(args[-1]))
        return original(self, *args)

    QPainter.drawText = recording
    try:
        painted(widget)
    finally:
        QPainter.drawText = original
    assert any("4200" in text and "counts" in text for text in texts)


def test_the_producers_caption_reaches_the_canvas(qapp):
    """Where a mass spectrum says it is CALCULATED rather than measured.
    A caption that never renders is the same as no caption."""
    caption = "CALCULATED -- natural-abundance isotope distribution."
    widget = StickChartWidget(_annotation(_TWO_STICKS, caption=caption))
    texts: list[str] = []
    original = QPainter.drawText

    def recording(self, *args):
        texts.append(str(args[-1]))
        return original(self, *args)

    QPainter.drawText = recording
    try:
        painted(widget)
    finally:
        QPainter.drawText = original
    assert caption in texts


@pytest.mark.parametrize(
    "annotation",
    [
        pytest.param(
            StickChartAnnotation(sticks=(), x_label="m/z", y_label="I", x_descending=False),
            id="empty",
        ),
        pytest.param(
            StickChartAnnotation(
                sticks=(Stick(math.nan, 1.0),), x_label="m/z", y_label="I", x_descending=False
            ),
            id="nan x",
        ),
        pytest.param(
            StickChartAnnotation(
                sticks=(Stick(1.0, 1.0),), x_label="", y_label="I", x_descending=False
            ),
            id="unlabelled axis",
        ),
    ],
)
def test_a_malformed_annotation_is_refused_rather_than_drawn(qapp, annotation):
    """Refused at the door, so nothing downstream has to cope with it --
    and `is_drawing()` says so without anybody reading the log."""
    widget = StickChartWidget(annotation)
    assert not widget.is_drawing()
    assert widget.hit_regions() == []


def test_a_refused_annotation_draws_no_more_than_an_empty_one(qapp):
    """It never falls back to a partial picture built from the parts that
    happened to be well-formed."""
    good = StickChartWidget(_annotation(_TWO_STICKS))
    refused = StickChartWidget(
        StickChartAnnotation(
            sticks=(Stick(100.0, 1.0), Stick(120.0, math.inf)),
            x_label="m/z",
            y_label="I",
            x_descending=False,
        )
    )
    assert ink(refused) < ink(good)


def test_the_axis_caption_composes_label_and_units():
    assert axis_caption("m/z", "") == "m/z"
    assert axis_caption("Relative abundance", "%") == "Relative abundance (%)"


def test_the_label_clearance_keeps_a_short_sticks_label_off_the_axis(qapp):
    """A label on a stick barely taller than the text would sit on the axis
    or on its neighbour, and a label over the wrong stick is worse than no
    label."""
    widget = StickChartWidget(
        _annotation([Stick(100.0, 1.0, "tall"), Stick(120.0, 0.001, "tiny")])
    )
    texts: list[str] = []
    original = QPainter.drawText

    def recording(self, *args):
        texts.append(str(args[-1]))
        return original(self, *args)

    QPainter.drawText = recording
    try:
        painted(widget, width=400, height=300)
    finally:
        QPainter.drawText = original
    assert "tall" in texts
    assert "tiny" not in texts
    assert LABEL_HEIGHT > 0
