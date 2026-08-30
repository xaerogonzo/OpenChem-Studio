"""Guards for the geometric oracle, in two halves that must not merge.

**THE PREDICATES GET CONSTRUCTED GEOMETRY. THE EXTRACTION GETS REAL
WIDGETS.** Every predicate test below builds its own `QRect`s and strings,
so it is arithmetic and can never quietly become a claim about the test
machine's fonts -- `offscreen`'s default font is more than twice as wide as
the one a user sees, and this project has already had a geometry assertion
fail by 40 px on a panel that was measurably clean in the running
application.

The extraction tests do the opposite and read a REAL widget tree, but they
assert POPULATION and PAIRING rather than pixel widths, for the same reason.

**AND THE NARROW HALF IS LOAD-BEARING EVERY TIME.** For each predicate there
is a test that it reports the defect and a test that it stays silent on a
clean surface. Without the second, `return everything` passes the first --
and an over-broad predicate produces a GREEN suite and a smaller universe,
which reads as a coverage jump rather than as a fault.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

from openchem.ui import visual_check
from openchem.ui.visual_check import (
    LabelledRow,
    PaintedText,
    collapsed,
    labelled_rows,
    latched_ellipsis,
    overflowing,
    overlapping,
    painted_items,
)

import conftest


def _dispose(widget: QWidget) -> None:
    """The per-widget recipe, never the global drain.

    `sendPostedEvents(None, DeferredDelete)` drains every pending deferred
    delete in the process, including ones other test files left queued,
    which is a double free.
    """
    conftest.dispose(widget)


def _item(
    *,
    text: str = "Aqueous Solubility",
    full_text: str = "",
    rect: QRect | None = None,
    inner_width: int = 0,
    needed_width: int = 0,
    full_text_width: int = 0,
    minimum_width: int = 0,
) -> PaintedText:
    """A painted-text record with every number supplied by the caller.

    Nothing here is measured, which is the point: a predicate test that
    called `QFontMetrics` would be testing this machine's fonts.
    """
    return PaintedText(
        path="Panel > QLabel",
        text=text,
        full_text=full_text,
        rect=rect if rect is not None else QRect(0, 0, 100, 20),
        widget_class="QLabel",
        inner_width=inner_width,
        needed_width=needed_width,
        full_text_width=full_text_width,
        minimum_width=minimum_width,
    )


# -- overflowing ----------------------------------------------------------

BOUNDS = QRect(0, 0, 200, 400)


def test_text_past_the_right_edge_is_reported() -> None:
    # `QRect.right()` is INCLUSIVE -- left + width - 1 -- so a 100 px widget
    # at x=150 ends at 249 against a bound ending at 199.
    found = overflowing([_item(rect=QRect(150, 0, 100, 20))], BOUNDS)
    assert [f.right for f in found] == [50]


def test_text_past_the_left_edge_is_reported() -> None:
    """Left-edge clipping is not hypothetical -- `bb_permeant` and
    "unctional Groups" are both on record from a panel scrolled right."""
    found = overflowing([_item(rect=QRect(-30, 0, 100, 20))], BOUNDS)
    assert [f.left for f in found] == [30]


def test_a_clip_inside_the_widget_is_reported_separately() -> None:
    """A single unbreakable token longer than the space it was given: no
    amount of repositioning the widget would reveal it, so it is its own
    term rather than folded into the edges."""
    found = overflowing([_item(inner_width=80, needed_width=140)], BOUNDS)
    assert [(f.left, f.right, f.intra) for f in found] == [(0, -100, 60)]


def test_text_that_fits_is_NOT_reported() -> None:
    """THE NARROW HALF. Without this, `return items` passes every test above."""
    assert overflowing([_item(rect=QRect(10, 0, 100, 20))], BOUNDS) == []


def test_a_widget_one_pixel_over_is_absorbed_by_the_tolerance() -> None:
    """Rounding must not make the walk untrustworthy where it needs believing."""
    assert overflowing([_item(rect=QRect(0, 0, 201, 20))], BOUNDS) == []


# -- overlapping ----------------------------------------------------------


def _row(label: QRect, field: QRect, row: int = 0) -> LabelledRow:
    return LabelledRow(
        row=row,
        label=_item(text="Aqueous Solubility", rect=label),
        field=_item(text="-3.68", rect=field),
    )


def test_a_value_painted_over_its_caption_is_reported() -> None:
    """The recorded defect: an ignored label stopped sizing the label
    column, so "Aqueous Solubility" and "-3.68" shared one rectangle and
    rendered as `Aqu36ous Solubility (...`. Every panel test passed."""
    found = overlapping([_row(QRect(0, 0, 120, 20), QRect(30, 0, 90, 20))])
    assert len(found) == 1
    assert "overlaps its label" in found[0].detail


def test_a_row_whose_columns_are_separate_is_NOT_reported() -> None:
    """THE NARROW HALF, and the one that keeps this from being a generic
    rectangle-collision detector: Qt composites children constantly, so a
    predicate reporting any intersection would be deleted within a week."""
    assert overlapping([_row(QRect(0, 0, 120, 20), QRect(130, 0, 90, 20))]) == []


def test_columns_that_merely_touch_are_NOT_reported() -> None:
    assert overlapping([_row(QRect(0, 0, 120, 20), QRect(119, 0, 90, 20))]) == []


def test_rows_are_judged_independently() -> None:
    """A clean row must not be tarred by an overlapping one beside it."""
    found = overlapping(
        [
            _row(QRect(0, 0, 120, 20), QRect(130, 0, 90, 20), row=0),
            _row(QRect(0, 30, 120, 20), QRect(30, 30, 90, 20), row=1),
        ]
    )
    assert [f.detail.split()[1] for f in found] == ["1"]


# -- latched_ellipsis -----------------------------------------------------


def test_a_caption_still_elided_with_room_to_grow_is_reported() -> None:
    """The hints measured the ELIDED string, so once squeezed the caption
    reported the width of an ellipsis, was given that, and could never grow
    back -- three captions rendered as a bare `...`."""
    found = latched_ellipsis(
        [_item(text="Aqu...", full_text="Aqueous Solubility", inner_width=200, full_text_width=150)]
    )
    assert len(found) == 1
    assert "still elided" in found[0].detail


def test_a_caption_elided_because_it_genuinely_lacks_room_is_NOT_reported() -> None:
    """THE NARROW HALF. Eliding when there is no room is correct behaviour,
    and reporting it would make every squeezed panel a wall of findings."""
    assert (
        latched_ellipsis(
            [
                _item(
                    text="Aqu...",
                    full_text="Aqueous Solubility",
                    inner_width=60,
                    full_text_width=150,
                )
            ]
        )
        == []
    )


def test_a_literal_ellipsis_in_a_value_is_NOT_reported() -> None:
    """**THE PREDICATE NEVER LOOKS FOR THE GLYPH.** A value may legitimately
    contain an ellipsis; a check matching on the character would report it.
    Comparing against the widget's own stored full text makes that false
    positive structurally impossible rather than merely unlikely."""
    # A widget that stores no full text can never be compared, so it can
    # never be reported -- but that alone is a DEGENERATE fixture: it also
    # passes a predicate that sniffs for the glyph, because the width
    # short-circuit hides the difference. Found by mutation.
    assert latched_ellipsis([_item(text="loading...", full_text="")]) == []
    # THE DISCRIMINATING CASE. Ample room, a real measured width, and a
    # value that genuinely contains an ellipsis while NOT being elided.
    # Correct code skips it because painted == full; a glyph-sniffing
    # predicate reports it.
    assert (
        latched_ellipsis(
            [_item(text="a...b", full_text="a...b", inner_width=200, full_text_width=50)]
        )
        == []
    )


# -- collapsed ------------------------------------------------------------


def test_a_caption_at_zero_width_against_a_stated_minimum_is_reported() -> None:
    """`QFormLayout` COLLAPSES a label whose `sizeHint` does not fit rather
    than clamping it -- `QRect(16, 2, 0, 14)` against a stated minimum of
    120, measured on a bare form 290 px wide."""
    found = collapsed([_item(rect=QRect(16, 2, 0, 14), minimum_width=120)])
    assert len(found) == 1
    assert "minimum of 120" in found[0].detail


def test_a_merely_narrow_caption_is_NOT_reported() -> None:
    """THE NARROW HALF. A label squeezed to 40 px is doing what a squeezed
    layout should do; only near-zero against a real stated minimum is the
    defect."""
    assert collapsed([_item(rect=QRect(16, 2, 40, 14), minimum_width=120)]) == []


def test_a_zero_width_widget_that_asks_for_nothing_is_NOT_reported() -> None:
    """A spacer legitimately has no width and no demand."""
    assert collapsed([_item(rect=QRect(0, 0, 0, 14), minimum_width=0)]) == []


# -- extraction: real widgets, asserting population and pairing -----------


class _StubEliding(QLabel):
    """Stands in for `property_panel._ElidingLabel`'s stored full text."""

    def __init__(self, painted: str, full: str, parent: QWidget | None = None) -> None:
        super().__init__(painted, parent)
        self.full_text = full


def _form_surface() -> tuple[QWidget, QFormLayout]:
    host = QWidget()
    form = QFormLayout(host)
    form.addRow(QLabel("Aqueous Solubility"), QLabel("-3.68"))
    form.addRow(QLabel("LogP"), QLabel("1.19"))
    return host, form


def test_the_extraction_walk_finds_every_label_that_paints(qapp) -> None:
    """**THE POPULATION ASSERTION, AND IT IS THE HALF A PURE-PREDICATE TEST
    CANNOT COVER.** An extraction walk that silently returned nothing would
    make every predicate above vacuously happy while the application clipped
    -- a green suite and a smaller universe. Four labels go in; four painted
    items must come out."""
    host, _ = _form_surface()
    host.show()
    try:
        items = painted_items(host)
        assert len(items) == 4, [i.text for i in items]
        assert {i.text for i in items} == {"Aqueous Solubility", "-3.68", "LogP", "1.19"}
    finally:
        _dispose(host)


def test_a_container_that_paints_no_text_is_not_an_item(qapp) -> None:
    """A holder wider than the viewport with every child inside it clips
    nothing; reporting it would bury the one widget that does."""
    host, _ = _form_surface()
    host.show()
    try:
        assert all(i.text for i in painted_items(host))
    finally:
        _dispose(host)


def test_the_label_and_field_of_one_row_are_paired_by_qt(qapp) -> None:
    """**THE PAIRING IS ASKED OF QT, NEVER INFERRED FROM PROXIMITY.**"""
    host, _ = _form_surface()
    host.show()
    try:
        rows = labelled_rows(host)
        assert [(r.label.text, r.field.text) for r in rows] == [
            ("Aqueous Solubility", "-3.68"),
            ("LogP", "1.19"),
        ]
    finally:
        _dispose(host)


def test_a_spanning_row_is_excluded_rather_than_half_read(qapp) -> None:
    """A spanning row has no label beside it, so it cannot exhibit the
    caption/value overlap this feeds. `property_panel` records the trap from
    the other side: a walk reading only `FieldRole` omits spanning rows
    entirely, which is how a dump came to miss exactly the rows it was
    written for. Here the exclusion is deliberate and asserted."""
    host, form = _form_surface()
    form.addRow(QLabel("A wide row spanning both columns"))
    host.show()
    try:
        rows = labelled_rows(host)
        assert len(rows) == 2, [(r.label.text, r.field.text) for r in rows]
        # ...and the spanning row's widget IS still a painted item, so it is
        # excluded from the PAIRING and not from the walk.
        assert "A wide row spanning both columns" in {i.text for i in painted_items(host)}
    finally:
        _dispose(host)


def test_a_spanning_widget_is_never_paired_with_a_label_beside_it(qapp) -> None:
    """**THE ARM THAT MAKES THE SPANNING RULE LOAD-BEARING**, and `addRow`
    cannot reach it -- which is why the test above survived a mutation that
    deleted the rule outright.

    Measured: for a row built with `addRow(QWidget)`, `LabelRole` is None
    and `FieldRole` returns the spanning widget, so the None guard excludes
    it and the explicit rule is redundant. But `setWidget` can put a label
    AND a spanning widget on ONE row, and then `LabelRole` is a real caption
    while `FieldRole` hands back the full-width widget. Without the rule
    those two are paired, and a row spanning both columns is judged as
    though it sat beside a caption.
    """
    host = QWidget()
    form = QFormLayout(host)
    form.setWidget(0, QFormLayout.ItemRole.LabelRole, QLabel("Caption"))
    form.setWidget(0, QFormLayout.ItemRole.SpanningRole, QLabel("Spanning"))
    host.show()
    try:
        # Assert the SETUP, so a Qt that stops allowing this fails loudly
        # rather than making the guard pass vacuously.
        assert form.itemAt(0, QFormLayout.ItemRole.LabelRole) is not None
        assert form.itemAt(0, QFormLayout.ItemRole.FieldRole) is not None
        assert labelled_rows(host) == []
    finally:
        _dispose(host)


def test_extraction_carries_a_widgets_stored_full_text(qapp) -> None:
    """The plumbing `latched_ellipsis` rests on. The numeric decision is
    tested on constructed geometry above; this asserts only that a widget's
    own stored string reaches the record."""
    host = QWidget()
    _StubEliding("Aqu...", "Aqueous Solubility", host)
    host.show()
    try:
        items = [i for i in painted_items(host) if i.text == "Aqu..."]
        assert [i.full_text for i in items] == ["Aqueous Solubility"]
        assert items[0].full_text_width > 0
    finally:
        _dispose(host)


def test_a_plain_label_can_never_be_reported_as_latched(qapp) -> None:
    """An ordinary `QLabel` has no notion of being elided, so it carries no
    full text and `latched_ellipsis` has nothing to compare against."""
    host, _ = _form_surface()
    host.show()
    try:
        assert latched_ellipsis(painted_items(host)) == []
    finally:
        _dispose(host)


def test_a_widget_in_a_hidden_branch_is_not_measured(qapp) -> None:
    """`isVisibleTo`, not `isHidden` and not `isVisible`. A widget that has
    never been laid out carries a default geometry that reads as an enormous
    overflow -- measured before that filter existed: 56 findings at
    "right 384 px", every one a label in a collapsed section, against a real
    overflow of 14."""
    host = QWidget()
    branch = QWidget(host)
    QLabel("hidden away", branch)
    branch.setVisible(False)
    host.show()
    try:
        assert "hidden away" not in {i.text for i in painted_items(host)}
    finally:
        _dispose(host)


# -- the two levels stay apart --------------------------------------------

_PREDICATES = ("overflowing", "overlapping", "latched_ellipsis", "collapsed")


def test_no_predicate_measures_a_font() -> None:
    """**THIS IS WHAT KEEPS THE TWO LEVELS FROM MERGING.** A predicate that
    called `QFontMetrics` would be a predicate whose unit test is a claim
    about the test machine's fonts, which is exactly the trap the module
    header describes. Measuring belongs to extraction; predicates get
    numbers somebody already measured.

    Asserted on the SOURCE, because a predicate could take a font
    measurement without any fixture noticing.
    """
    source = Path(visual_check.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in _PREDICATES:
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name) and inner.id in {"QFontMetrics", "QFont"}:
                offenders.append(f"{node.name} references {inner.id}")
            if isinstance(inner, ast.Attribute) and inner.attr in {
                "font",
                "horizontalAdvance",
                "boundingRect",
            }:
                offenders.append(f"{node.name} calls .{inner.attr}")
    assert not offenders, offenders
    # ...and assert the setup, so a renamed predicate cannot make this pass
    # vacuously by matching nothing at all.
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert set(_PREDICATES) <= names, sorted(names)
