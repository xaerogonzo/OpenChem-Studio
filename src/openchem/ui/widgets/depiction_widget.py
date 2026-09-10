"""A declared depiction, drawn on the structure it belongs to.

The third renderer of the chart channel, and the one that needs something
the annotation deliberately does not carry: a molecule.

    annotation      WHAT to draw -- atom indices and their styling
    report          WHICH molecule -- `StructureReport.molecule_uuid`
    render context  the geometry, resolved and supplied by the UI

**THE RESOLVER IS INJECTED, NEVER LOOKED UP HERE.** A widget that reached
for a project or a session to find a molblock would be a view that knows
where structures live, and this one is a lens over data somebody else
holds. The host that already has the project supplies a callable; a host
that has none supplies nothing, and the widget says so on screen rather
than drawing an empty frame.

**"NO STRUCTURE HERE" AND "NOTHING DECLARED" ARE DIFFERENT FACTS**, and
telling them apart is the same rule the factory applies to an unrenderable
kind: an empty frame is indistinguishable from `charts == ()`, which is a
producer saying it has no picture.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from openchem.domain.report import DepictionAnnotation, valid_chart_annotation

logger = logging.getLogger("openchem.ui")

#: Shown when the annotation is fine and this surface cannot resolve the
#: molecule it is about. A sentence rather than a blank frame: the two
#: read identically otherwise, and they are opposite facts about why
#: nothing is drawn.
NO_STRUCTURE = (
    "This result declared a picture of the structure, and this view cannot "
    "resolve which molecule it belongs to. The facts below are unaffected."
)


class DepictionWidget(QWidget):
    """One `DepictionAnnotation`, drawn onto its molecule's 2D depiction."""

    def __init__(
        self,
        annotation: DepictionAnnotation | None = None,
        parent: QWidget | None = None,
        molblock: str = "",
        refusal: str = "",
    ) -> None:
        super().__init__(parent)
        self._annotation: DepictionAnnotation | None = None
        self._molblock = molblock
        #: Why the host would not supply a structure. Shown INSTEAD of
        #: `NO_STRUCTURE`, because "this result describes an earlier version
        #: of the molecule" and "there is no molecule here" are different
        #: statements and only one of them tells a reader what to do.
        #: Defaults empty, so every existing caller is unmoved.
        self._refusal = refusal
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # **A `QSvgWidget` INSIDE A LAYOUT, and never given a message to
        # render.** It scales its viewBox to fill the pane, so an SVG
        # carrying a sentence becomes unreadable text at whatever size the
        # pane happens to be -- this project has already turned a refusal
        # card into 37 px of clipped prose that way. A refusal is a
        # `QLabel`; only a picture goes in the SVG.
        self._view = QSvgWidget(self)
        self._message = QLabel(NO_STRUCTURE, self)
        self._message.setWordWrap(True)
        #: The producer's caption under the picture -- for a depiction this
        #: is usually the LEGEND, which is the one thing a reader needs to
        #: interpret it. Found by driving the app: the Lewis diagram drew
        #: two blue atoms and nothing anywhere said blue meant donor,
        #: because the caption was declared and dropped. The other two
        #: chart widgets have painted theirs from the start.
        self._caption = QLabel("", self)
        self._caption.setWordWrap(True)
        self._caption.setStyleSheet("color: #6e6e6e;")
        layout.addWidget(self._view)
        layout.addWidget(self._caption)
        layout.addWidget(self._message)
        self.setMinimumHeight(240)
        if refusal:
            # BEFORE the annotation is looked at. A refusal is about the
            # STRUCTURE, so it holds whether or not there is something to draw
            # -- and rendering the picture first would defeat it.
            self._show_message(refusal)
        elif annotation is not None:
            self.set_annotation(annotation)
        else:
            self._show_message(NO_STRUCTURE)

    # -- what it is showing ------------------------------------------------

    def set_annotation(self, annotation: DepictionAnnotation | None) -> None:
        """Adopt `annotation`, or refuse it and draw nothing.

        The contract every renderer of this channel has: a malformed
        annotation is REFUSED with a log line rather than repaired,
        because a picture assembled from repaired nonsense reads as a
        result.
        """
        if annotation is not None and not valid_chart_annotation(annotation):
            logger.warning("Refusing to draw a malformed depiction: %r", annotation)
            annotation = None
        self._annotation = annotation
        self._render()

    def annotation(self) -> DepictionAnnotation | None:
        return self._annotation

    def set_molblock(self, molblock: str) -> None:
        """Supply the geometry the annotation deliberately does not carry."""
        self._molblock = molblock or ""
        self._render()

    def is_drawing(self) -> bool:
        """Whether a picture is on screen, as opposed to a message.

        Three states reach this widget and two of them are empty frames
        without it: nothing declared, declared and refused, and declared
        with no molecule to draw it on.
        """
        return self._annotation is not None and bool(self._molblock) and self._view.isVisibleTo(self)

    # -- painting ----------------------------------------------------------

    def _show_message(self, text: str) -> None:
        self._message.setText(text)
        self._message.setHidden(False)
        self._view.setHidden(True)
        # The legend goes with the picture it explains. Left showing, it
        # would describe colours that are not on screen.
        self._caption.setHidden(True)

    def _render(self) -> None:
        if self._annotation is None:
            self._show_message(NO_STRUCTURE)
            return
        if not self._molblock:
            self._show_message(NO_STRUCTURE)
            return
        try:
            svg = self._svg()
        except Exception as exc:  # a broken molblock is the host's problem
            logger.warning("Could not draw a declared depiction: %s", exc)
            self._show_message(NO_STRUCTURE)
            return
        self._view.load(QByteArray(svg.encode("utf-8")))
        self._view.setHidden(False)
        self._message.setHidden(True)
        caption = self._annotation.caption
        self._caption.setText(caption)
        self._caption.setHidden(not caption)

    def _svg(self) -> str:
        """The depiction, from the ONE renderer that already draws these.

        `render_2d_svg` takes `atom_colors` and `atom_labels` in exactly
        the shape `VisualizationLayer` carries -- it was written that way
        so the Property Inspector could feed one set of colours into both
        the 2D and the 3D view. Nothing is converted here.

        It also owns the bounds check: a calculator legitimately holds
        data keyed to `AddHs(mol)` while the depiction is the editor's
        molblock, so an index with no atom is DROPPED there rather than
        raising. That is the half of validation the annotation cannot do,
        because it has no molecule.
        """
        from openchem.chem.engine import ChemistryEngine

        layer = self._annotation.layer
        return ChemistryEngine().render_2d_svg(
            self._molblock,
            atom_colors=dict(layer.atom_colors),
            atom_labels=dict(layer.atom_labels) if layer.atom_labels else None,
        )
