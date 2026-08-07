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
        self._toggle_button.toggled.connect(self._on_toggled)

        self.content = QWidget(self)
        self.content.setVisible(expanded)
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(16, 2, 2, 6)
        self._calculators_layout = QVBoxLayout()
        content_layout.addLayout(self._calculators_layout)
        self._content_layout = QFormLayout()
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
