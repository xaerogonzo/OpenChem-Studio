"""An SVG at its own size, zoomable, in a scroll area.

**EXTRACTED FROM `LewisDiagramDialog` RATHER THAN COPIED.** The decay
chart needs the identical contract -- a diagram with a real natural size,
too big for any sensible dialog, that must not be squeezed to fit -- and
a second implementation of zoom is exactly the drift this project has
recorded over and over. The Lewis dialog keeps its whole public surface
(`zoom`, `set_zoom`, `zoom_to_fit`, `zoom_to_natural`, `natural_size`,
`_view`, `_scroll`) as delegations, so its behaviour is unchanged by
construction rather than by re-testing.

The thing it exists to prevent, in the Lewis dialog's own words: a
`QSvgWidget` scales its viewBox to fill its pane, so a 42-atom structure
was rendered into about 600x450 and every glyph came out a few pixels
tall -- which is what "extremely hard to read" was about.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: FOUR CONTROLS, TWO RENDERINGS EACH -- the decay chart and the Lewis
#: diagram both build this widget, so the contract lives here for the same
#: reason `CollapsibleSection` owns its section-header one: "zoom in" means
#: the same thing wherever this view is used, and writing it at each host
#: would be two chances to disagree.
#:
#: The two that need saying are `100%` and `Fit`, because they are easy to
#: read as the same button. They are not, and the case that proves it is a
#: small diagram in a large window: Fit magnifies it past 100%.
_HELP: dict[str, HelpTooltip] = {
    "zoom_out": HelpTooltip(
        text=(
            "Zooms out one step, each step a factor of 1.25.\n\n"
            "The view stops at 25%; the diagram is never shrunk to fit its "
            "pane on its own, which is what the scroll bars are for."
        ),
        tier=1,
        help_id="diagram.zoom_out",
        topic="diagram",
    ),
    "zoom_natural": HelpTooltip(
        text=(
            "Draws the diagram at its OWN size -- 100% of the drawing, not "
            "100% of this pane.\n\n"
            "The two are easy to conflate and are different buttons: at "
            "100% a large diagram overflows and scrolls, where Fit would "
            "shrink it to fit."
        ),
        tier=1,
        help_id="diagram.zoom_natural",
        topic="diagram",
    ),
    "zoom_in": HelpTooltip(
        text=(
            "Zooms in one step, each step a factor of 1.25.\n\n"
            "The view stops at 800%. Zooming does not redraw the diagram at "
            "a higher quality -- it is vector art, so it stays sharp."
        ),
        tier=1,
        help_id="diagram.zoom_in",
        topic="diagram",
    ),
    "zoom_to_fit": HelpTooltip(
        text=(
            "The largest zoom at which the whole diagram fits this pane, "
            "aspect ratio kept.\n\n"
            "FIT CAN BE MORE THAN 100%: a small diagram in a large window "
            "is magnified to fill it, which is the case that makes this a "
            "different button from 100%. Only a diagram larger than the "
            "pane is reduced."
        ),
        tier=1,
        help_id="diagram.zoom_to_fit",
        topic="diagram",
    ),
}


class ZoomableSvgView(QWidget):
    """A scroll area holding an SVG at a chosen zoom, plus its controls."""

    MIN_ZOOM = 0.25
    MAX_ZOOM = 8.0
    ZOOM_STEP = 1.25

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        minimum_size: tuple[int, int] = (560, 420),
        fallback_size: tuple[int, int] = (420, 340),
    ) -> None:
        super().__init__(parent)
        self._zoom = 1.0
        self._fallback = QSize(*fallback_size)

        self._view = QSvgWidget(self)
        self._scroll = QScrollArea(self)
        # **NOT resizable**, which is the whole point: the child keeps the
        # size the zoom gives it and the area scrolls, instead of the
        # child being shrunk to fit.
        self._scroll.setWidgetResizable(False)
        self._scroll.setWidget(self._view)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setMinimumSize(*minimum_size)

        # A FIXED ROW, outside the scroll area, so the content can never
        # squeeze the controls.
        self._zoom_row = QHBoxLayout()
        self._buttons: list[QPushButton] = []
        for label, slot, help_key in (
            ("−", self._zoom_out, "zoom_out"),
            ("100%", self.zoom_to_natural, "zoom_natural"),
            ("+", self._zoom_in, "zoom_in"),
            ("Fit", self.zoom_to_fit, "zoom_to_fit"),
        ):
            button = QPushButton(label, self)
            button.clicked.connect(slot)
            # Taken by KEY from the table above rather than set here, so a
            # fifth button added to this loop is red until it is declared.
            apply_help_tooltip(button, _HELP[help_key])
            button.setFixedWidth(56)
            self._zoom_row.addWidget(button)
            self._buttons.append(button)
        self._zoom_label = QLabel("100%", self)
        self._zoom_row.addWidget(self._zoom_label)
        self._zoom_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._zoom_row)
        layout.addWidget(self._scroll, 1)

    # --- content ------------------------------------------------------------

    def load(self, svg: str) -> None:
        """Show an SVG, keeping the current zoom.

        Keeping it is deliberate: stepping between two diagrams of the
        same kind should not throw away a zoom somebody chose, and the
        caller can always ask for `zoom_to_fit` when the subject changes
        enough to warrant it.
        """
        self._view.load(svg.encode("utf-8"))
        self.set_zoom(self._zoom)

    def set_content_visible(self, visible: bool) -> None:
        """Hide the picture AND its controls together.

        **A REFUSAL IS NOT SHOWN AS A PICTURE** -- a `QSvgWidget` scales
        its viewBox to fill the pane, so a card carrying a sentence was
        rendered at about 37 px with both ends clipped and read as a
        broken window. Zoom buttons over an absent diagram are the same
        mistake one step along.
        """
        self._scroll.setVisible(visible)
        for button in self._buttons:
            button.setVisible(visible)
        self._zoom_label.setVisible(visible)

    # --- zoom ---------------------------------------------------------------

    def natural_size(self) -> QSize:
        """The SVG's own width and height, as the renderer emitted them."""
        renderer = self._view.renderer()
        size = renderer.defaultSize() if renderer is not None else QSize()
        if size.isEmpty():
            return QSize(self._fallback)
        return size

    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, factor: float) -> None:
        factor = max(self.MIN_ZOOM, min(self.MAX_ZOOM, factor))
        self._zoom = factor
        natural = self.natural_size()
        self._view.setFixedSize(
            max(1, round(natural.width() * factor)),
            max(1, round(natural.height() * factor)),
        )
        self._zoom_label.setText(f"{round(factor * 100)}%")

    def zoom_to_natural(self, _checked: bool = False) -> None:
        """**100% means the SVG's OWN size**, not 100% of the viewport.

        Stated because the two are easy to conflate, and conflating them
        would make this button and Fit do the same thing.
        """
        self.set_zoom(1.0)

    def zoom_to_fit(self, _checked: bool = False) -> None:
        """The largest zoom at which the whole diagram fits, aspect kept.

        **Fit can be GREATER than 100%**, and that is the case which
        proves the two buttons are different: a small molecule in a large
        window is magnified to fill it. Only a diagram bigger than the
        viewport is reduced.
        """
        natural = self.natural_size()
        viewport = self._scroll.viewport().size()
        if natural.width() <= 0 or natural.height() <= 0:  # pragma: no cover
            return
        self.set_zoom(
            min(
                viewport.width() / natural.width(),
                viewport.height() / natural.height(),
            )
        )

    def _zoom_in(self, _checked: bool = False) -> None:
        self.set_zoom(self._zoom * self.ZOOM_STEP)

    def _zoom_out(self, _checked: bool = False) -> None:
        self.set_zoom(self._zoom / self.ZOOM_STEP)
