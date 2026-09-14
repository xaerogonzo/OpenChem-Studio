"""Two widgets the panels share: a collapsible section and an honest label.

Both were written inside `property_panel.py` and lived there while it was
their only consumer. The Atom Inspector is the second, and importing a
private class out of a sibling panel is the kind of dependency that quietly
becomes load-bearing, so they moved here rather than being reached for
across the package.

`WrappedLabel` in particular is not a convenience -- read its docstring
before simplifying it. All three of its overrides are required, measured,
and none works alone.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip


class WrappedLabel(QLabel):
    """A word-wrapped label that tells its layout how tall it really is.

    **A wrapped `QLabel` reports a ONE-LINE minimum height however much
    text it holds.** Qt has always done this, and normally nothing
    notices, because a layout with room to spare gives the label its
    (correct) size hint rather than its minimum.

    The property panel is the case where it does notice. Every section
    lives in one `QVBoxLayout` inside a `QScrollArea` with
    `setWidgetResizable`, and that scroll area sizes the panel to
    `max(viewport, minimumSizeHint)`. With the minimum under-reported --
    measured at 78 pixels for a panel whose content needed far more -- the
    panel was pinned to exactly the viewport height and NEVER SCROLLED. The
    layout then squeezed every compressible child to make the content fit,
    and the "Open [Calculator]..." buttons went from 20 pixels to 13, below
    their own minimum size hint.

    **All three overrides below are required, and NONE works alone.**
    Measured with two sections expanded and a long result in each, which is
    the smallest case that reproduces it:

        plain QLabel (what shipped)   buttons 13 px, 2 labels clipped
        size policy only              buttons 13 px, 2 labels clipped
        hasHeightForWidth only        buttons 13 px, 2 labels clipped
        minimumSizeHint only          buttons 13 px, 2 labels clipped
        all three                     buttons 20 px, nothing clipped

    They are three halves of one mechanism: `minimumSizeHint` supplies an
    honest minimum, `hasHeightForWidth` is what lets the layout ask for it
    during its minimum calculation, and the `MinimumExpanding` policy is
    what makes that minimum BINDING rather than a suggestion the layout may
    shrink past. Remove any one and the label goes back to claiming it
    needs one line.

    Note the second symptom in that table. The old behaviour did not only
    squeeze the buttons -- it CLIPPED the text, silently, so part of a
    result was simply not on screen.

    `QLayout.SizeConstraint.SetMinimumSize` on the panel does NOT fix it,
    also measured: the under-reporting is in the labels, so the panel's own
    minimum stays 78 whatever constraint it is given.

    A method note, because it nearly produced a wrong answer: with only ONE
    section expanded, nothing compresses and every arm looks identical. An
    A/B run in that configuration says the fix does nothing. Reproduce the
    failure first, then compare.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt's own casing
        return True

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt's own casing
        """The height this text actually needs at the width it has.

        Falls back to Qt's answer before the first layout pass, when the
        width is not yet known and `heightForWidth` would be meaningless.
        """
        width = self.width()
        if width <= 0:
            return super().minimumSizeHint()
        return QSize(0, self.heightForWidth(width))


class ClampedLabel(WrappedLabel):
    """A `WrappedLabel` that claims at most `max_lines` until expanded.

    **`WrappedLabel`'s whole point is that its full height is BINDING, and
    that is exactly wrong for prose pinned above or below a scroll area.**
    The Results reader's summary ("35 result(s): Molecular Properties, ...")
    and its caveat note are both unbounded, so in a narrow or short dock the
    two labels took their full height and the fact list between them -- the
    thing being read -- was squeezed to about two rows. Nothing is lost by
    clamping: `is_truncated()` says when text is cut, the host shows a way to
    expand it, and Copy report carries every word.

    Top-aligned for the reason `ExplicitHeightLabel` gives: the clamp cuts
    the bottom, so the first lines are the ones that show.

    **IT PREFERS `max_lines` AND MAY GIVE WAY TO ONE.** Measured with Results
    docked across the top at the 190 px it was reported at: the reader's
    chrome plus two notes held to three lines each already exceeded the dock
    before a single fact row, so the dock's own scroll area took over and the
    facts were off screen entirely. A folded note therefore states
    `max_lines` as its PREFERRED height and one line as its MINIMUM, and the
    layout shrinks it before the fact area, whose floor is binding. Expanded,
    the whole text is binding: somebody asked for it.

    NO HEIGHT-FOR-WIDTH, for the reason `ExplicitHeightLabel` records: a box
    layout overwrites a height-for-width item's minimum with that height, so
    "prefer three, accept one" cannot be expressed through it. The heights
    are stated from the current width and restated when the width changes.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None, max_lines: int = 3) -> None:
        super().__init__(text, parent)
        self._max_lines = max_lines
        self._expanded = False
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        # MAXIMUM, not Preferred: the size hint is a CEILING it may shrink
        # below, never a floor it may grow past. Preferred let a roomy layout
        # hand spare height to the note -- six lines at 700 px in the guard
        # -- which is the unfolding this class exists to stop.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt's own casing
        return False

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt's own casing
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            self.updateGeometry()
        self._show_whole_lines_only()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt's own casing
        super().setText(text)
        self.updateGeometry()
        self._show_whole_lines_only()

    def _show_whole_lines_only(self) -> None:
        """Mask off a line the height it was given cuts through.

        **"PREFER THREE, ACCEPT ONE" ALSO MEANS ACCEPTING TWO AND A HALF.** A
        box layout hands a note anything between its one-line minimum and its
        three-line hint, and a top-aligned label paints into all of it -- so a
        second line whose top half fit was drawn with its bottom half cut off.
        Magnified in the Results reader docked across the top at 190 px, once
        the reader had 10 px to spare: 27 px for a note whose lines are 18.

        Masked rather than laid out differently, because the layout cannot be
        asked for whole-line heights. The spare pixels stay blank; the text,
        `is_truncated` and More are unchanged.
        """
        width, height = self.width(), self.height()
        if width <= 0 or height <= 0 or not self.text() or self.full_height(width) <= height:
            self.clearMask()
            return
        shown = self._lines_height(1, width)
        lines = 2
        while True:
            taller = self._lines_height(lines, width)
            if taller > height or taller <= shown:
                break
            shown, lines = taller, lines + 1
        if shown >= height:
            self.clearMask()
        else:
            self.setMask(QRegion(0, 0, width, shown))

    def _lines_height(self, lines: int, width: int) -> int:
        """The height THIS label would take for exactly `lines` lines.

        **MEASURED ON A PROBE, NOT DERIVED.** The first version took the full
        height minus a font-metrics estimate of the wrapped text, and the two
        wrap at different widths: under `offscreen` it put 44 px of
        "overhead" on a 14 px line and folded to six lines instead of three.
        A hidden label with the same font and style, holding `lines` short
        lines, answers with Qt's own arithmetic -- padding included.
        """
        probe = getattr(self, "_probe", None)
        if probe is None:
            probe = self._probe = QLabel(self)
            probe.setWordWrap(True)
            probe.hide()
        probe.setFont(self.font())
        probe.setStyleSheet(self.styleSheet())
        probe.setText("\n".join(["M"] * max(1, lines)))
        return probe.heightForWidth(width)

    def _line_height(self, width: int) -> int:
        return min(self.full_height(width), self._lines_height(1, width))

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self.updateGeometry()
        self._show_whole_lines_only()

    def is_expanded(self) -> bool:
        return self._expanded

    def full_height(self, width: int) -> int:
        return super().heightForWidth(width)

    def clamped_height(self, width: int) -> int:
        """`max_lines` of text plus whatever the label adds around text."""
        return min(self.full_height(width), self._lines_height(self._max_lines, width))

    def is_truncated(self) -> bool:
        """Whether the text does not fit in the height the label HAS now --
        which is what a reader sees, whether the fold or the layout cut it."""
        width = self.width()
        if width <= 0 or not self.text():
            return False
        return self.full_height(width) > self.height()

    def _width(self) -> int:
        return self.width() if self.width() > 0 else 0

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt's own casing
        hint = super().sizeHint()
        width = self._width()
        if width > 0:
            hint.setHeight(self.full_height(width) if self._expanded else self.clamped_height(width))
        return hint

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt's own casing
        width = self._width()
        if width <= 0:
            return QLabel.minimumSizeHint(self)
        if self._expanded:
            return QSize(0, self.full_height(width))
        return QSize(0, self._line_height(width))


class ExplicitHeightLabel(QLabel):
    """A wrapped label that STATES a height instead of offering a
    height-for-width. Use this for any long value inside a
    `CollapsibleSection`.

    `WrappedLabel` above is still right for a label sitting directly in a
    panel, where nothing squeezes it. Inside a section it is actively
    harmful, and the difference is not stylistic -- it truncated every
    report row for eight attempted fixes.

    **`QBoxLayout.setGeometry` OVERWRITES a height-for-width item's
    minimum with its `heightForWidth` before it distributes space.** One
    height-for-width widget anywhere inside a section makes every
    ancestor layout height-for-width carrying, and from there no minimum
    stated anywhere on the chain can win. Measured in the running app,
    Identity section holding one report row, panel at 280 px:

        item CollapsibleSection  geom_h=113  minSize=225  hfw=75

    225 was right and unused; 75 was the height the section needed before
    the row's text arrived. The section got 113, its content 94 of the
    206 it asked for, and the form shared that out -- which is why an
    unrelated `formula` row dropped from 16 px to 14 at the same moment.

    A `heightForWidth` is an OFFER a layout may recompute and get wrong;
    a stated height is a fact. So this label reports no height-for-width
    at all and states the height its text needs at the width it HAS, on
    every text change and every resize -- as its size hint under a
    `Fixed` policy, and NEVER as an explicit minimum.
    `_match_height_to_text` has the measurement that made that last
    clause part of the contract.

    Proven by removal: with this label AND `DontWrapRows` (see
    `CollapsibleSection`, whose policy makes the form height-for-width by
    itself) every level of the chain reports `ok` and the value renders
    in full.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        #: The height stated for the current width and text; 0 until measured.
        self._stated_height = 0
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # TOP-aligned because the height is stated rather than negotiated.
        # A `QLabel` centres vertically by default, so wherever a stated
        # height exceeds what the text draws the slack appears as a gap
        # ABOVE the first line, which reads as a broken row; top-aligned it
        # is trailing space, which reads as nothing at all. It was recorded
        # here as 144 px stated for the Elemental Analysis report where the
        # glyphs used about 96. A height left over from a narrower width is
        # the one cause of such slack since measured, and it is closed (see
        # `_match_height_to_text`); the alignment stays for any other.
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._match_height_to_text()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt's own casing
        super().setText(text)
        self._match_height_to_text()

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt's own casing
        """A STYLE CHANGE RE-DERIVES THE HEIGHT-FOR-WIDTH FLAG, and
        overriding `setText` and `resizeEvent` alone does not catch it.

        `QLabel::changeEvent` answers `StyleChange` and `FontChange` by
        calling `QLabelPrivate::updateLabel()` -- the same function
        `_stop_offering_height_for_width` exists to undo. Setting a style
        sheet on ANY ancestor sends `StyleChange` to every descendant, so
        a label that was correctly cleared at `setText` silently starts
        offering a height-for-width again some time later, with nothing
        on the label itself having changed.

        Measured in the running app, Lipophilicity section, panel at
        280 px, by logging every transition of the flag:

            '13 atoms, -0.4195 to 0.5437'  re-set hfw on event 100
                                                    (QEvent::StyleChange)

        From there the whole chain becomes height-for-width carrying
        again and `QBoxLayout.setGeometry` substitutes the section's
        `heightForWidth` for its minimum -- the exact failure the class
        docstring describes:

            arm                     section h   its minimum   buttons
            without this override         145           192   15/15/14
            with it                       192           192   26/26/26

        26 px is the buttons' own minimum, so below it they overlap.

        It recomputes rather than merely re-clearing, because a style or
        font change is also the one event that can change how tall the
        text draws -- so the stated height has to be restated, not just
        defended.

        **It answers EVERY change event rather than filtering for
        `StyleChange`**, which is deliberate. The history of this class
        is nine fixes that were each too narrow -- clearing the flag in
        `__init__` was undone by `setText`, and clearing it in `setText`
        was undone by this -- so the cheap, total answer is the one that
        cannot be wrong about a Qt version that re-derives the flag from
        somewhere new. Both routines it calls are already guarded
        against doing redundant work, so the extra events cost nothing.
        """
        super().changeEvent(event)
        self._match_height_to_text()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt's own casing
        """A wrapped label's height depends on the width it was GIVEN, so
        the only honest moment to recompute is once the layout has
        assigned one."""
        super().resizeEvent(event)
        self._match_height_to_text()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt's own casing
        """The stated height, and `QLabel`'s width.

        `sizeHint` alone, not `minimumSizeHint` too: for a `Fixed` policy the
        layout takes the larger of the two, and `QLabel`'s own minimum is a
        single line. Overriding both let each cover for the other's removal.
        Without this, `QLabel`'s own guess stands, made for a width it picks
        itself. Measured, a row 110 px tall where its text needed 250 --
        cut off -- and 110 where it needed 54.
        """
        hint = super().sizeHint()
        # `getattr`: a hint asked for before `__init__` has set anything.
        stated = getattr(self, "_stated_height", 0)
        if stated > 0:
            hint.setHeight(stated)
        return hint

    def _match_height_to_text(self) -> None:
        """State the height the text needs at the width the label has.

        **A SIZE HINT AND NEVER AN EXPLICIT MINIMUM, because
        `QLabel.heightForWidth` never answers below the label's own minimum
        height.** `QLabelPrivate::sizeForWidth` ends by expanding to
        `minimumSize()`: measured, a label held at 1608 px answers 1608 at a
        width where its text needs 250. This used to `setFixedHeight` what
        that call returned and then ask it again, so a stated height could
        grow and never come back down -- and the first width it is ever
        asked about is Qt's 100 px default for a child widget, before any
        layout pass. Every row that wraps at 100 px kept that height.
        Measured in the Results reader at its default docked width, on the
        pH-dependent charges result for fentanyl:

            row       width  held    its text needs   held = the need at
            Finding     251  272 px  96 px, 6 lines   100 px
            Keyed to    251   48 px  16 px, 1 line    106 px

        To a layout a hint under a `Fixed` policy binds as a fixed height
        does: the item's minimum, maximum and hint are all the hint. In the
        section chain, widened, narrowed and widened again, the hint and an
        honestly measured fixed height gave the same section heights and the
        same layout passes. Two other repairs
        were measured and not taken. Lifting the minimum around the call
        invalidated the parent layout on every change event, three layout
        requests for three no-op events against none. And a hidden probe
        label must copy every property that sizes text to stay right. See
        docs/LESSONS.md.

        **SO NOTHING MAY GIVE THIS LABEL AN EXPLICIT MINIMUM HEIGHT.**
        `setFixedHeight` or `setMinimumHeight` from a host puts the floor
        back.
        """
        self._stop_offering_height_for_width()
        width = self.width()
        # Not a wait for the first layout pass: Qt reports 100, not 0, for a
        # child widget nobody has sized. That first answer is a guess the
        # first real width corrects, which only works because nothing
        # floors the correction.
        if width <= 0:
            return
        wanted = self.heightForWidth(width)
        # Guarded because a new hint makes the layout resize this label;
        # with the width unchanged the second pass agrees and it settles.
        if wanted > 0 and wanted != self._stated_height:
            self._stated_height = wanted
            self.updateGeometry()

    def _stop_offering_height_for_width(self) -> None:
        """Clear the size policy's height-for-width flag HERE, not in
        `__init__`.

        **`QLabelPrivate::updateLabel()` re-derives that flag from the
        word-wrap flag on every label update**, so a policy set once at
        construction is silently undone by the first `setText`:

            after __init__ sequence   False
            after setText             True

        Clearing it only once made things WORSE than not trying at all --
        the label held a correct fixed height while the chain stayed
        height-for-width carrying, so the section collapsed to 75 px and
        crushed its rows to 3 px each, against 14 before.
        """
        policy = self.sizePolicy()
        if policy.hasHeightForWidth():
            policy.setHeightForWidth(False)
            self.setSizePolicy(policy)


#: The header button every section carries.
_SECTION_TOGGLE_HELP = HelpTooltip(
    text=(
        "Shows or hides this section's contents.\n\n"
        "Collapsing one hides its results, it does not discard them or stop "
        "anything running -- a calculation started here keeps going and its "
        "answer is waiting when the section is opened again.\n\n"
        "Which sections start open is a fixed default, not a memory of how "
        "you last left them."
    ),
    tier=1,
    help_id="properties.section_toggle",
    topic="properties",
    help_anchor="properties",
)


class CollapsibleSection(QWidget):
    """A titled section that shows/hides its content on click — no native
    Qt widget does this, so a `QToolButton` (checkable, arrow icon) plus a
    plain content `QWidget` is the standard idiom.

    Holds two sub-layouts: `_calculators_layout` (Phase 18's "Open
    [Calculator]..." buttons, static per category, never touched by
    `clear_rows()`) above `_content_layout` (the per-molecule descriptor
    rows `clear_rows()` does reset on every molecule switch) -- kept
    separate so the calculator buttons stay visible across molecule
    switches instead of blinking away until the first descriptor for that
    category arrives again.
    """

    def __init__(self, title: str, expanded: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._toggle_button = QToolButton(self)
        self._toggle_button.setText(title)
        self._toggle_button.setCheckable(True)
        self._toggle_button.setChecked(expanded)
        self._toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle_button.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._toggle_button.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        # ONE CONCEPT, ONE CONTRACT, however many sections exist.
        #
        # "Show or hide this section" means the same thing on all seventeen
        # Properties categories and on every other section built from this
        # class; WHICH section is what `instance_path` records. The same
        # call as the sixty batch tick boxes one file over.
        apply_help_tooltip(self._toggle_button, _SECTION_TOGGLE_HELP)
        self._toggle_button.toggled.connect(self._on_toggled)

        self.content = QWidget(self)
        self.content.setVisible(expanded)
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(16, 2, 2, 6)
        self._calculators_layout = QVBoxLayout()
        content_layout.addLayout(self._calculators_layout)
        self._content_layout = QFormLayout()
        # **`WrapLongRows` IS HEIGHT-FOR-WIDTH WHATEVER ITS CHILDREN ARE**,
        # and that is what truncated report rows through eight attempted
        # fixes. Whether a row wraps depends on the width, so the form's
        # height does too, and every section above it then inherits the
        # substitution described in `ExplicitHeightLabel`. Measured:
        #
        #     policy          form hfw with     form hfw with
        #                     hfw items         non-hfw items
        #     DontWrapRows    True              False
        #     WrapLongRows    True              True     <- unavoidable
        #     WrapAllRows     True              False
        #
        # So the wrap policy cannot be the thing that gives a long value
        # the full width. `PropertyPanel._add_wide_row` did it instead,
        # with a genuine spanning row -- explicit, and free of any
        # width-dependent height. That row went with the result rendering
        # in 2c and this panel has no long values left, but the POLICY
        # still has to be `DontWrapRows`: the reason is the height-for-width
        # chain above, which the descriptor rows sit in exactly as the
        # result rows did. `WrapAllRows` is the other non-hfw option and is
        # still wrong here: it moves EVERY short scalar onto two rows,
        # measured at +75% section height.
        self._content_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        content_layout.addLayout(self._content_layout)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._toggle_button)
        layout.addWidget(self.content)

    def set_expanded(self, expanded: bool) -> None:
        """Open or close it in code.

        Goes through the toggle button rather than `content.setVisible`
        directly, so the arrow and the button's checked state cannot drift
        out of step with what is on screen -- a section showing a
        right-pointing arrow above visible content is a small thing that
        makes a UI feel broken.
        """
        self._toggle_button.setChecked(expanded)

    def is_expanded(self) -> bool:
        return self._toggle_button.isChecked()

    def _on_toggled(self, checked: bool) -> None:
        self._toggle_button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.content.setVisible(checked)

    def content_layout(self) -> QFormLayout:
        return self._content_layout

    def add_calculator_widget(self, widget: QWidget) -> None:
        """A persistent widget for this section (an "Open [Calculator]..."
        button, or a hint label) -- lives in `_calculators_layout`, which
        `clear_rows` deliberately leaves alone, unlike the per-molecule
        descriptor rows in `_content_layout`."""
        self._calculators_layout.addWidget(widget)

    def clear_rows(self) -> None:
        while self._content_layout.rowCount():
            self._content_layout.removeRow(0)
