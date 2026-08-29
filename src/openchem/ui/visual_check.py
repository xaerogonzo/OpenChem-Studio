"""Geometric invariants a laid-out UI must satisfy -- and nothing about taste.

**THE VISUAL ORACLE OWNS GEOMETRIC INVARIANTS THAT ARE MECHANICALLY
MEASURABLE. THE SCREENSHOT OWNS HUMAN JUDGMENT ABOUT APPEARANCE.** This
module may establish that text left its viewport, that a value was painted
over its caption, that a label collapsed to nothing, or that one is still
elided with room to grow. It may never attempt to establish that a surface
"looks right".

That line is the one `ui/widgets/help_tooltip.py` already draws when it
forbids grading tooltip prose: the validator owns the SHAPE, a reviewer owns
the meaning. Without it this layer drifts into computer vision.

## WHY IT EXISTS AT ALL

CLAUDE.md carries a running count of roughly fourteen defects found ONLY by
driving the application and magnifying the screenshot, every one of them with
a fully green suite. Three of those are pure geometry, and they are the reason
this module has the predicates it has:

    a value painted on top of its caption     "Aqu36ous Solubility (..."
    a caption latched at an ellipsis          hints measured the elided string
    a caption collapsed to zero width         QRect(16, 2, 0, 14) vs a min of 120

All three were found by eye. None of them needs to be.

## THE TWO LEVELS, AND WHY THEY ARE SEPARATE

    the predicates      pure functions over QRects and strings. Tested
                        headless on CONSTRUCTED geometry, so a guard can
                        never quietly become a claim about the machine's
                        fonts -- which has already cost this project a
                        geometry test that failed by 40 px on a panel
                        measurably clean in the running application.
    the extraction      reads ACTUAL laid-out geometry off a real widget
                        tree and measures real font metrics. Exercised by
                        the drive step, against the running application.

**NEITHER ALONE IS THE CHECK.** A passing predicate suite proves the rectangle
arithmetic and says nothing about whether the application is laid out
correctly; an extraction walk that silently returned nothing would make every
predicate vacuously happy. That second half is the dangerous one -- an
over-broad exclusion produces a GREEN suite and a smaller universe -- so
`painted_items` is asserted against a known population by its caller. See
`tests/test_visual_check.py`.

This module imports no pytest and no chemistry: the drive step runs inside the
real application and cannot reach `tests/conftest.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

#: Pixels of slack before a geometry finding is reported.
#:
#: Not zero, because a laid-out widget can sit a pixel past a boundary through
#: ordinary rounding, and reporting that would make the walk untrustworthy
#: exactly where it needs to be believed. This is the value
#: `property_panel._OVERFLOW_TOLERANCE` has always used.
DEFAULT_TOLERANCE = 2

#: At or below this width a label is COLLAPSED rather than merely narrow.
#:
#: The recorded defect is `QRect(16, 2, 0, 14)` -- a `QFormLayout` giving a
#: label ZERO width against a stated minimum of 120, rather than clamping it.
#: A merely narrow label is a different thing and must not be reported, which
#: is why this is near-zero rather than a fraction of the stated minimum.
COLLAPSE_TOLERANCE = 2


@dataclass(frozen=True)
class PaintedText:
    """One widget's painted text, its geometry, and every width a predicate needs.

    Every font measurement is taken HERE, during extraction, so the predicates
    stay pure arithmetic over numbers somebody handed them. A predicate that
    called `QFontMetrics` itself would be a predicate whose unit test is a
    claim about the test machine's fonts.

    `full_text` is the unelided string when the widget stores one (see
    `property_panel._ElidingLabel`) and `""` when it does not -- an ordinary
    `QLabel` has no notion of being elided, so it can never be reported as
    latched.
    """

    path: str
    text: str
    full_text: str
    rect: QRect
    #: The widget's class NAME, never the widget.
    #:
    #: A finding may outlive the walk that produced it, and PySide invalidates
    #: a wrapper reached through a temporary -- this codebase has already had
    #: `Internal C++ object already deleted` from exactly that. A name is all
    #: any consumer needs and cannot dangle.
    widget_class: str
    #: The widget's own content width, or 0 where it is not meaningful.
    #:
    #: **LABELS ONLY.** A `QPushButton`'s `contentsRect` is not its text
    #: rectangle -- the style adds its own padding -- so an intra-widget
    #: comparison there is meaningless. Measured: an 80 px "Details..."
    #: button reports 40 px of phantom overflow under the test platform's
    #: wider font while rendering correctly for a user.
    inner_width: int
    #: What the PAINTED text needs at `inner_width`. 0 when not measurable.
    needed_width: int
    #: What `full_text` would need on one line. 0 when there is no full text.
    full_text_width: int
    #: `minimumSizeHint().width()` -- what the widget says it needs.
    minimum_width: int


@dataclass(frozen=True)
class LabelledRow:
    """A `QFormLayout` row carrying BOTH a label and a field.

    **THE PAIRING IS ASKED OF QT, NEVER INFERRED FROM PROXIMITY.** Two widgets
    overlapping is not a defect in general -- Qt composites children
    constantly -- so a generic rectangle-collision detector would produce a
    pile of false positives and be deleted within a week. `QFormLayout` knows
    which label belongs to which field, so `overlapping` only ever compares
    two rectangles Qt itself says are the two halves of one row. Same move as
    `tooltip_inventory`'s echo check: ask Qt rather than reimplement its
    private detail.

    A SPANNING row has no label beside it and so cannot exhibit this defect;
    `labelled_rows` excludes it by construction rather than crashing on it.
    """

    row: int
    label: PaintedText
    field: PaintedText


@dataclass(frozen=True)
class Finding:
    """One geometric invariant, violated, with enough context to act on it.

    `path` is an ancestry chain rather than a bare class name, because
    "QLabel overflowed by 17 px" is not actionable in a panel holding a
    hundred labels.
    """

    kind: str
    path: str
    text: str
    detail: str

    def describe(self) -> str:
        return f"{self.kind}: {self.text[:44]!r} -- {self.detail} | path: {self.path}"


# -- predicates: pure functions over rectangles and strings ----------------


@dataclass(frozen=True)
class Overflow:
    """One overflow, with its three magnitudes kept apart.

    A dedicated type rather than three more fields on `Finding`, because
    only this predicate has magnitudes and a shared type carrying fields
    meaningful for one member is the one-field-two-jobs smell this codebase
    has already paid for.

    `left`/`right` are pixels PAST each bound, so a fitting widget is
    `(<=0, <=0)`. `intra` is separate and means the clip happens INSIDE the
    widget, which no amount of moving it would fix.
    """

    item: PaintedText
    left: int
    right: int
    intra: int

    def as_finding(self, bounds_width: int) -> Finding:
        return Finding(
            kind="overflowing",
            path=self.item.path,
            text=self.item.text,
            detail=(
                f"left {self.left} px / right {self.right} px / "
                f"intra {self.intra} px against bounds width {bounds_width}"
            ),
        )


def overflowing(
    items: Sequence[PaintedText],
    bounds: QRect,
    tolerance: int = DEFAULT_TOLERANCE,
) -> list[Overflow]:
    """Painted text that leaves `bounds`, on either edge or inside itself.

    **BOTH EDGES.** Left-edge clipping is not hypothetical: `bb_permeant` and
    "unctional Groups" are both on record from a panel that had been scrolled
    right.

    The intra term is separate from the two edge terms and means the clip
    happens INSIDE the widget -- a single unbreakable token longer than the
    space it was given, which no amount of repositioning would reveal.
    """
    found: list[Overflow] = []
    for item in items:
        left = bounds.left() - item.rect.left()
        right = item.rect.right() - bounds.right()
        intra = item.needed_width - item.inner_width if item.inner_width > 0 else 0
        if left > tolerance or right > tolerance or intra > tolerance:
            found.append(Overflow(item=item, left=left, right=right, intra=intra))
    return found


def overlapping(
    rows: Sequence[LabelledRow], tolerance: int = DEFAULT_TOLERANCE
) -> list[Finding]:
    """A row whose field's painted text intersects its own label's.

    The recorded defect: an ignored label stopped sizing the label column, so
    `QFormLayout` drew the value on top of the caption and "Aqueous
    Solubility" plus "-3.68" shared one rectangle. Every panel test passed
    while the two were overlapping.

    Both rectangles are already in one coordinate space -- that is
    extraction's job -- so this is an intersection test and nothing more.
    `tolerance` keeps two rectangles merely touching at an edge from being
    reported.
    """
    findings: list[Finding] = []
    for row in rows:
        overlap = row.label.rect.intersected(row.field.rect)
        if overlap.width() > tolerance and overlap.height() > tolerance:
            findings.append(
                Finding(
                    kind="overlapping",
                    path=row.field.path,
                    text=row.field.text,
                    detail=(
                        f"row {row.row} field overlaps its label "
                        f"{row.label.text[:24]!r} by "
                        f"{overlap.width()}x{overlap.height()} px"
                    ),
                )
            )
    return findings


def latched_ellipsis(items: Sequence[PaintedText]) -> list[Finding]:
    """A label still showing elided text after the room came back.

    **THIS NEVER LOOKS FOR AN ELLIPSIS CHARACTER.** A value may legitimately
    contain one, and a predicate matching on the glyph would report it -- the
    exact false positive this check must not produce. Instead it compares the
    painted string against the widget's OWN stored `full_text`, which
    `_ElidingLabel` keeps precisely because it "does not change when the
    painted string does".

    So the signal is elision STATE plus available width: the widget is
    painting something other than its full text, and its full text would now
    fit. A label elided because it genuinely lacks room is correct behaviour
    and is not reported.
    """
    findings: list[Finding] = []
    for item in items:
        if not item.full_text or item.text == item.full_text:
            continue
        available = item.inner_width if item.inner_width > 0 else item.rect.width()
        if available >= item.full_text_width > 0:
            findings.append(
                Finding(
                    kind="latched_ellipsis",
                    path=item.path,
                    text=item.text,
                    detail=(
                        f"still elided with {available} px available and "
                        f"{item.full_text_width} px needed for "
                        f"{item.full_text[:32]!r}"
                    ),
                )
            )
    return findings


def collapsed(
    items: Sequence[PaintedText], tolerance: int = COLLAPSE_TOLERANCE
) -> list[Finding]:
    """A label laid out at essentially no width while claiming it needs one.

    `QFormLayout` COLLAPSES a label whose `sizeHint` does not fit rather than
    clamping it at `minimumSizeHint` -- measured on a bare form 290 px wide,
    `QRect(16, 2, 0, 14)` against a stated minimum of 120.

    Merely narrow is not reported, deliberately: a label squeezed to 40 px is
    doing what a squeezed layout should do, and only a near-zero width against
    a real stated minimum is the defect.
    """
    findings: list[Finding] = []
    for item in items:
        if not item.text:
            continue
        if item.rect.width() <= tolerance < item.minimum_width:
            findings.append(
                Finding(
                    kind="collapsed",
                    path=item.path,
                    text=item.text,
                    detail=(
                        f"laid out at {item.rect.width()} px against a stated "
                        f"minimum of {item.minimum_width} px"
                    ),
                )
            )
    return findings


# -- extraction: the only half that touches real Qt geometry --------------


def ancestry_path(widget: QWidget, top: QWidget) -> str:
    """`A > B > C`, so a finding names WHERE the offender sits."""
    names: list[str] = []
    node: QWidget | None = widget
    while node is not None and node is not top:
        names.append(type(node).__name__)
        node = node.parentWidget()
    names.append(type(top).__name__)
    return " > ".join(reversed(names))


def painted_string(widget: QWidget) -> str:
    """The text a widget actually draws, or `""` for a pure container.

    **Containers are deliberately excluded.** A holder wider than the viewport
    with every child inside it clips nothing, and reporting it would bury the
    one widget that does -- the false positive this walk exists to avoid.
    """
    getter = getattr(widget, "text", None)
    if not callable(getter):
        return ""
    try:
        return str(getter() or "")
    except (TypeError, RuntimeError):
        # A Qt method needing arguments, or a freed C++ object.
        return ""


def measure(widget: QWidget, space: QWidget) -> PaintedText | None:
    """Read one widget's painted geometry into `space`'s coordinates.

    Returns None for anything that paints no text of its own.
    """
    text = painted_string(widget)
    if not text:
        return None
    rect = QRect(widget.mapTo(space, QPoint(0, 0)), widget.size())
    inner = widget.contentsRect().width() if isinstance(widget, QLabel) else 0
    metrics = QFontMetrics(widget.font())
    needed = 0
    if inner > 0:
        wraps = bool(getattr(widget, "wordWrap", None) and widget.wordWrap())
        flags = Qt.TextFlag.TextWordWrap if wraps else Qt.TextFlag.TextSingleLine
        needed = metrics.boundingRect(QRect(0, 0, inner, 0), int(flags), text).width()
    full = str(getattr(widget, "full_text", "") or "")
    return PaintedText(
        path=ancestry_path(widget, space),
        text=text,
        full_text=full,
        rect=rect,
        widget_class=type(widget).__name__,
        inner_width=inner,
        needed_width=needed,
        full_text_width=metrics.horizontalAdvance(full) if full else 0,
        minimum_width=widget.minimumSizeHint().width(),
    )


def painted_items(root: QWidget, space: QWidget | None = None) -> list[PaintedText]:
    """Every visible descendant of `root` that paints text, in one space.

    **`isVisibleTo`, NOT `isHidden` AND NOT `isVisible`.** A widget inside a
    COLLAPSED section has `isHidden() == False` -- the flag is on the
    section's content, not on the child -- and it has never been laid out, so
    it carries a default geometry that reads as an enormous overflow.
    Measured before that filter existed: 56 findings at "right 384 px", every
    one a label in a collapsed section, against a real overflow of 14.
    `isVisible()` is the opposite mistake and is False for every child of a
    window nobody showed, so under a test harness it answers "none of them".
    """
    space = space or root
    items: list[PaintedText] = []
    for child in root.findChildren(QWidget):
        if not child.isVisibleTo(root):
            continue
        item = measure(child, space)
        if item is not None:
            items.append(item)
    return items


def labelled_rows(root: QWidget, space: QWidget | None = None) -> list[LabelledRow]:
    """Every `QFormLayout` row under `root` carrying BOTH a label and a field.

    **A SPANNING ROW IS EXCLUDED DELIBERATELY, NOT MISSED.** `property_panel`
    records the trap from the other direction: a walk reading only `FieldRole`
    omits spanning rows entirely, which is how a dump came to miss exactly the
    rows it was written for. Here the exclusion has a reason -- a spanning row
    has no label beside it, so it cannot exhibit the caption/value overlap
    this feeds.
    """
    space = space or root
    rows: list[LabelledRow] = []
    for form in root.findChildren(QFormLayout):
        for index in range(form.rowCount()):
            if form.itemAt(index, QFormLayout.ItemRole.SpanningRole) is not None:
                continue
            label_item = form.itemAt(index, QFormLayout.ItemRole.LabelRole)
            field_item = form.itemAt(index, QFormLayout.ItemRole.FieldRole)
            if label_item is None or field_item is None:
                continue
            label_widget = label_item.widget()
            field_widget = field_item.widget()
            if label_widget is None or field_widget is None:
                continue
            if not label_widget.isVisibleTo(root) or not field_widget.isVisibleTo(root):
                continue
            label = measure(label_widget, space)
            field = measure(field_widget, space)
            if label is None or field is None:
                continue
            rows.append(LabelledRow(row=index, label=label, field=field))
    return rows


def check_surface(
    root: QWidget,
    bounds: QRect | None = None,
    space: QWidget | None = None,
    tolerance: int = DEFAULT_TOLERANCE,
) -> list[Finding]:
    """Every predicate, against one surface. What the drive step calls.

    `bounds` defaults to `space`'s own rectangle, which is the right answer
    for a plain dialog. A SCROLLING surface must pass its VIEWPORT rect
    instead -- content legitimately extends past a viewport, and judging it
    against the content widget's own rectangle would report nothing forever.
    """
    space = space or root
    bounds = bounds if bounds is not None else space.rect()
    items = painted_items(root, space)
    return [
        *(o.as_finding(bounds.width()) for o in overflowing(items, bounds, tolerance)),
        *overlapping(labelled_rows(root, space), tolerance),
        *latched_ellipsis(items),
        *collapsed(items),
    ]
