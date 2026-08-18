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
    a fixed height is a fact. So this label reports no height-for-width
    at all and keeps its own fixed height correct, on every text change
    and every resize.

    Proven by removal: with this label AND `DontWrapRows` (see
    `CollapsibleSection`, whose policy makes the form height-for-width by
    itself) every level of the chain reports `ok` and the value renders
    in full.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # TOP-aligned because the height is stated rather than negotiated.
        # A `QLabel` centres vertically by default, so wherever the stated
        # height exceeds what the text draws -- `heightForWidth` reserves
        # 144 px for the Elemental Analysis report where the glyphs use
        # about 96 -- the slack appears as a gap ABOVE the first line,
        # which reads as a broken row. Top-aligned it becomes trailing
        # space, which reads as nothing at all.
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

    def _match_height_to_text(self) -> None:
        self._stop_offering_height_for_width()
        width = self.width()
        # Before the first layout pass there is no width to wrap against,
        # and `heightForWidth` would be answering about nothing.
        if width <= 0:
            return
        wanted = self.heightForWidth(width)
        # Guarded because `setFixedHeight` triggers another resize; with
        # the width unchanged the second pass agrees and it settles.
        if wanted > 0 and wanted != self.minimumHeight():
            self.setFixedHeight(wanted)

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
        # the full width. `PropertyPanel._add_wide_row` does it instead,
        # with a genuine spanning row -- explicit, and free of any
        # width-dependent height. `WrapAllRows` is the other non-hfw
        # option and is still wrong for this panel: it moves EVERY short
        # scalar onto two rows, measured at +75% section height.
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
