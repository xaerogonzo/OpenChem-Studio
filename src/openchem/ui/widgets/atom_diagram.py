"""The atom, drawn: shell rings and orbital boxes, side by side.

**This widget computes no chemistry.** It draws what
`chem/electron_shells.py` hands it, which is the arrangement that lets a
3D orbital renderer be added later without touching any of this -- it
would consume the same `Subshell` triples. It is also what keeps
`tests/test_layering.py` happy, since `ui/` may not import RDKit.

Two views because they answer different questions. The rings say how many
electrons are how far out, which is what "valence shell" means. The boxes
say which orbital each electron is in and which way it is spinning, which
is where Hund's rule becomes visible -- nitrogen's three unpaired 2p
electrons are a picture, not a sentence.
"""

from __future__ import annotations

import logging
import math
from typing import NamedTuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.electron_shells import (
    Configuration,
    ConfigurationResult,
    ConfigurationUnavailable,
    Nucleus,
    Subshell,
    ion_configuration,
    isoelectronic_noble_gas,
    nucleus,
)

logger = logging.getLogger(__name__)

_NUCLEUS_COLOUR = QColor("#e8546b")
_ELECTRON_COLOUR = QColor("#3aa0e0")
_RING_COLOUR = QColor("#7a7a7a")
_BOX_COLOUR = QColor("#444444")
_MUTED = "color: #666666;"


class ShellDiagram(QWidget):
    """Nucleus with proton/neutron counts, electrons on their shells."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._shells: dict[int, int] = {}
        self._nucleus: Nucleus | None = None
        self.setMinimumSize(220, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_atom(self, shells: dict[int, int], centre: Nucleus | None) -> None:
        self._shells = dict(shells)
        self._nucleus = centre
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())

        centre = QPointF(self.width() / 2, self.height() / 2)
        # Leave room for the outermost electrons, which sit ON the ring.
        span = min(self.width(), self.height()) / 2 - 16
        count = max(1, len(self._shells))

        for index, (shell, electrons) in enumerate(sorted(self._shells.items()), start=1):
            radius = span * index / count
            painter.setPen(QPen(_RING_COLOUR, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(centre, radius, radius)

            painter.setBrush(_ELECTRON_COLOUR)
            painter.setPen(QPen(_ELECTRON_COLOUR.darker(130), 1))
            for slot in range(electrons):
                # Start at the top and go round; the offset per shell stops
                # every shell putting an electron at the same angle, which
                # reads as a spoke rather than as a shell.
                angle = 2 * math.pi * slot / electrons - math.pi / 2 + index * 0.35
                point = QPointF(
                    centre.x() + radius * math.cos(angle),
                    centre.y() + radius * math.sin(angle),
                )
                painter.drawEllipse(point, 5, 5)
            del shell

        if self._nucleus is not None:
            painter.setBrush(_NUCLEUS_COLOUR)
            painter.setPen(QPen(_NUCLEUS_COLOUR.darker(140), 1))
            painter.drawEllipse(centre, 26, 26)
            painter.setPen(QPen(QColor("#ffffff")))
            font = QFont(painter.font())
            font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
            painter.setFont(font)
            # Protons alone where the element has no natural isotope --
            # the count is certain, and "0n" would be a claim nobody made.
            caption = f"{self._nucleus.protons}p"
            if self._nucleus.has_neutron_count:
                caption += f"\n{self._nucleus.neutrons}n"
            painter.drawText(
                QRectF(centre.x() - 26, centre.y() - 26, 52, 52),
                Qt.AlignmentFlag.AlignCenter,
                caption,
            )
        painter.end()


#: Box geometry in pixels. A subshell occupies `orbitals` boxes side by
#: side with its label underneath; `_ROW_HEIGHT` includes the gap to the
#: row below, so `y + _ROW_HEIGHT` is the next row's top.
_BOX = 22.0
_BOX_GAP = 2.0
_SUBSHELL_GAP = 6.0
_LABEL_HEIGHT = 16.0
_ROW_HEIGHT = _BOX + _LABEL_HEIGHT + 10.0
_MARGIN = 8.0

#: Height reserved for the two-line placeholder, which is centred in the
#: whole rect rather than laid out in rows.
_MESSAGE_HEIGHT = 120


class PlacedSubshell(NamedTuple):
    """One subshell and where its boxes go. What `_layout_rows` returns."""

    subshell: Subshell
    x: float
    y: float
    width: float


class OrbitalBoxes(QWidget):
    """The `1s UD | 2s UD | 2p U U U` layout.

    **THIS USED TO DROP ELECTRONS SILENTLY.** The paint loop packed rows
    against `self.height()` and `break`ed when it ran out, so polonium's
    panel stopped at `5s` -- `5p6 5d10 6s2 6p4`, 22 of its 84 electrons,
    absent from the picture while the line directly above it printed the
    full `[Xe] 4f14 5d10 6s2 6p4`. Bismuth was the same. The string and
    the drawing disagreed and the drawing lost quietly, which is the
    worst way for a reference table to be wrong.

    **THE SIZING CONTRACT, STATED RATHER THAN NEGOTIATED.** The obvious
    repair -- `heightForWidth` plus a resizable scroll area -- is two
    mechanisms fighting: the scroll area tells the child to fit the
    viewport while height-for-width says the natural height follows from
    the width. This project has paid for height-for-width negotiating
    through parent layouts twice already (`WrappedLabel` starving a
    panel; a style change re-arming the flag through `changeEvent`). So
    there is no `heightForWidth` here. Instead:

        _layout_rows(width)   the one authority on where anything goes
        _draw_rows(...)       draws ALL of them, with no truncation branch
        the widget is told its WIDTH and answers with a minimum HEIGHT

    `set_configuration` applies that height as well as `resizeEvent`,
    because **a widget that was never shown gets no `resizeEvent`** --
    measured in this project at 0 calls across two successive `resize()`s
    before `show()`, which is exactly the state a test constructs.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._configuration: Configuration | None = None
        self.setMinimumHeight(_MESSAGE_HEIGHT)
        # Wide enough for the widest single subshell (7 f orbitals), so a
        # narrow viewport scrolls rather than clipping a row in half. This
        # is not width NEGOTIATION -- the scroll area still decides the
        # width, this only floors it.
        self.setMinimumWidth(int(_MARGIN * 2 + 7 * _BOX + 6 * _BOX_GAP))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_configuration(self, configuration: Configuration | None) -> None:
        self._configuration = configuration
        self._apply_required_height()
        self.update()

    # --- layout: one authority, and it does no painting -------------------

    def _layout_rows(self, width: float) -> list[PlacedSubshell]:
        """Where every subshell goes at this width. **Never truncates.**

        Laid out in WRITING order (1s, 2s, 2p...), which is how every
        table and textbook spells this. The filling order lives in the
        model.

        A subshell wider than the whole widget is NOT wrapped onto an
        empty row -- that would leave a blank row and still overflow. The
        minimum width in `__init__` is what stops that arising at all.
        """
        if self._configuration is None or self._configuration.electrons == 0:
            return []
        placed: list[PlacedSubshell] = []
        x, y = _MARGIN, _MARGIN
        for subshell in self._configuration.in_writing_order():
            span = subshell.orbitals * _BOX + (subshell.orbitals - 1) * _BOX_GAP
            if x > _MARGIN and x + span > width - _MARGIN:
                x, y = _MARGIN, y + _ROW_HEIGHT
            placed.append(PlacedSubshell(subshell, x, y, span))
            x += span + _SUBSHELL_GAP
        return placed

    def required_height(self, width: float) -> float:
        """The height every subshell needs at this width."""
        rows = self._layout_rows(width)
        if not rows:
            return float(_MESSAGE_HEIGHT)
        return max(row.y for row in rows) + _ROW_HEIGHT + _MARGIN

    def missing_row_count(self, width: float, height: float) -> int:
        """How many subshells would fall outside a widget of this size.

        **A VIOLATED INVARIANT, not a display mode.**
        `_apply_required_height` guarantees this is zero for the widget's
        own geometry, so anything else means the minimum height was not
        honoured. It is a predicate rather than a branch buried in
        `paintEvent` so it can be asserted directly -- this project's rule
        that an unreachable branch is a question about where to assert,
        not automatically dead code.
        """
        return sum(1 for row in self._layout_rows(width) if row.y + _ROW_HEIGHT > height)

    def _apply_required_height(self) -> None:
        # Guarded on a change so calling this from `resizeEvent` cannot
        # recurse: the height depends only on the WIDTH, so a second pass
        # at the same width computes the same number and stops.
        needed = int(math.ceil(self.required_height(self.width())))
        if needed != self.minimumHeight():
            self.setMinimumHeight(needed)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        super().resizeEvent(event)
        self._apply_required_height()

    # --- painting ---------------------------------------------------------

    def _paint_message(self, painter: QPainter, headline: str, action: str) -> None:
        """Two lines, the second naming what would fill the space.

        The project's own rule: "an empty state is two sentences, and the
        second one is the point". A placeholder saying only "nothing here"
        has told the reader what they could already see.
        """
        painter.setPen(QPen(QColor("#666666")))
        text = f"{headline}\n{action}" if action else headline
        painter.drawText(
            self.rect().adjusted(12, 12, -12, -12),
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            text,
        )

    def _draw_rows(self, painter: QPainter, rows: list[PlacedSubshell]) -> None:
        """Draw every row it is handed. **There is no truncation branch.**"""
        painter.setFont(QFont(painter.font().family(), 8))
        for placed in rows:
            for index, (up, down) in enumerate(placed.subshell.spins()):
                left = placed.x + index * (_BOX + _BOX_GAP)
                painter.setPen(QPen(_BOX_COLOUR, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(left, placed.y, _BOX, _BOX))
                painter.setPen(QPen(_BOX_COLOUR, 1.4))
                if up:
                    painter.drawText(
                        QRectF(left, placed.y, _BOX / 2, _BOX),
                        Qt.AlignmentFlag.AlignCenter,
                        "\u2191",
                    )
                if down:
                    painter.drawText(
                        QRectF(left + _BOX / 2, placed.y, _BOX / 2, _BOX),
                        Qt.AlignmentFlag.AlignCenter,
                        "\u2193",
                    )

            painter.setPen(QPen(_BOX_COLOUR))
            painter.drawText(
                QRectF(placed.x, placed.y + _BOX + 1, placed.width, _LABEL_HEIGHT),
                Qt.AlignmentFlag.AlignCenter,
                placed.subshell.label,
            )

    def _draw_incomplete_banner(self, painter: QPainter, missing: int) -> None:
        """Say so, loudly, if the sizing invariant was ever violated.

        A tidy note here would swap *silently wrong* for *quietly wrong*,
        which is the whole defect this class was rewritten for. Somebody
        meeting this banner should be meeting a bug, not a shrug -- hence
        the log line as well as the paint.
        """
        logger.warning(
            "OrbitalBoxes: %d subshell(s) fall outside %dx%d; the minimum height "
            "(%d) was not honoured",
            missing,
            self.width(),
            self.height(),
            self.minimumHeight(),
        )
        band = QRectF(0, 0, self.width(), 22)
        painter.fillRect(band, QColor("#c62828"))
        painter.setPen(QPen(QColor("#ffffff")))
        painter.drawText(
            band,
            Qt.AlignmentFlag.AlignCenter,
            f"Orbital display incomplete: {missing} subshell(s) could not be rendered",
        )

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())

        # Painted where the boxes would be, following
        # `NmrCorrelationPlotWidget` -- a message in the space the data
        # would occupy is where the reader is already looking.
        #
        # **Zero electrons is a RESULT, not missing data.** H+ really is a
        # bare nucleus, so the wording says that rather than implying
        # something failed, and the second line still names the one action
        # that changes it.
        if self._configuration is None:
            self._paint_message(painter, "Select an element.", "")
            painter.end()
            return
        if self._configuration.electrons == 0:
            self._paint_message(
                painter,
                "No electrons \u2014 a bare nucleus.",
                'Press "+ electron" or "Neutral" to put one back.',
            )
            painter.end()
            return

        rows = self._layout_rows(self.width())
        self._draw_rows(painter, rows)
        missing = self.missing_row_count(self.width(), self.height())
        if missing:
            self._draw_incomplete_banner(painter, missing)
        painter.end()


class AtomDiagram(QWidget):
    """Both views of one element, with electron add/remove.

    The `+`/`-` buttons go through `ion_configuration`, which prefers a
    curated reference and labels anything it derived. That labelling is
    the point: a control that lets somebody walk into an unusual
    transition-metal ion should say when the answer is this app's
    arithmetic rather than a measured ground state.
    """

    charge_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._symbol = ""
        self._charge = 0

        self.shells = ShellDiagram(self)
        self.boxes = OrbitalBoxes(self)

        self.title = QLabel("", self)
        title_font = QFont(self.title.font())
        title_font.setBold(True)
        self.title.setFont(title_font)

        self.configuration_label = QLabel("", self)
        self.configuration_label.setWordWrap(True)
        self.nucleus_label = QLabel("", self)
        self.nucleus_label.setWordWrap(True)
        self.provenance_label = QLabel("", self)
        self.provenance_label.setStyleSheet(_MUTED)
        self.provenance_label.setWordWrap(True)

        self.remove_button = QPushButton("− electron", self)
        self.remove_button.setToolTip("Remove an electron, forming a cation.")
        self.remove_button.clicked.connect(self._on_remove)
        self.add_button = QPushButton("+ electron", self)
        self.add_button.setToolTip("Add an electron, forming an anion.")
        self.add_button.clicked.connect(self._on_add)
        self.reset_button = QPushButton("Neutral", self)
        self.reset_button.clicked.connect(self._on_reset)

        buttons = QHBoxLayout()
        buttons.addWidget(self.remove_button)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.reset_button)
        buttons.addStretch()

        # **THE SCROLL AREA IS THE OTHER HALF OF THE FIX**, and the half
        # no test of `_layout_rows` can see. `OrbitalBoxes` answers a
        # width with the minimum height it needs; something has to be
        # willing to grant that height and scroll the excess, or a
        # polonium that no longer truncates is merely clipped instead.
        #
        # `setWidgetResizable(True)` is what hands the child the viewport
        # WIDTH -- which is the one number it wants -- while its own
        # minimum height governs the vertical. That pairing only works
        # because the child has no `heightForWidth`; see `OrbitalBoxes`.
        self.boxes_scroll = QScrollArea(self)
        self.boxes_scroll.setWidget(self.boxes)
        self.boxes_scroll.setWidgetResizable(True)
        self.boxes_scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        right = QVBoxLayout()
        right.addWidget(self.title)
        right.addWidget(self.configuration_label)
        right.addWidget(self.nucleus_label)
        right.addWidget(self.boxes_scroll, 1)
        right.addLayout(buttons)
        right.addWidget(self.provenance_label)

        layout = QHBoxLayout(self)
        layout.addWidget(self.shells, 1)
        layout.addLayout(right, 1)

    def set_element(self, symbol: str, charge: int = 0) -> None:
        self._symbol = symbol
        self._charge = charge
        self._refresh()

    def charge(self) -> int:
        return self._charge

    # --- the two buttons ------------------------------------------------

    def _on_remove(self, _checked: bool = False) -> None:
        self._try_charge(self._charge + 1)

    def _on_add(self, _checked: bool = False) -> None:
        self._try_charge(self._charge - 1)

    def _on_reset(self, _checked: bool = False) -> None:
        self._try_charge(0)

    def _try_charge(self, charge: int) -> None:
        """Move to `charge` only if a configuration can be given for it.

        A refusal leaves the previous state on screen rather than blanking
        it -- stripping past the electron count is the user reaching the
        end of the element, not an error to punish them with.
        """
        try:
            ion_configuration(self._symbol, charge)
        except ConfigurationUnavailable as exc:
            self.provenance_label.setText(str(exc))
            return
        self._charge = charge
        self._refresh()
        self.charge_changed.emit(charge)

    # --- rendering ------------------------------------------------------

    def _refresh(self) -> None:
        if not self._symbol:
            return
        try:
            result = ion_configuration(self._symbol, self._charge)
        except ConfigurationUnavailable as exc:
            self.title.setText(self._symbol)
            self.configuration_label.setText(str(exc))
            self.shells.set_atom({}, None)
            self.boxes.set_configuration(None)
            return

        self.title.setText(f"{self._symbol}{_charge_label(self._charge)}")
        self.configuration_label.setText(result.configuration.with_noble_core() or "no electrons")

        centre: Nucleus | None
        try:
            centre = nucleus(self._symbol)
        except ConfigurationUnavailable:
            centre = None
        self.nucleus_label.setText(_nucleus_text(centre, result.configuration.electrons))

        self.shells.set_atom(result.configuration.shells(), centre)
        self.boxes.set_configuration(result.configuration)
        self.provenance_label.setText(_provenance_text(result))

        self.remove_button.setEnabled(result.configuration.electrons > 0)


def _charge_label(charge: int) -> str:
    if charge == 0:
        return ""
    magnitude = "" if abs(charge) == 1 else str(abs(charge))
    return f"{magnitude}{'+' if charge > 0 else '−'}"


def _nucleus_text(centre: Nucleus | None, electrons: int) -> str:
    """Protons, neutrons and electrons -- **naming the isotope**.

    A neutron count is not a property of an element: silicon does not have
    14 neutrons, Si-28 does. Saying which one the number came from is the
    difference between a fact and a plausible misreading.

    **AN ELEMENT WITH NO NATURAL ISOTOPE STILL GETS ITS PROTONS**, and is
    told WHY there is no neutron count beside them. This used to read
    "Electrons: 84" and nothing else, which is a fact about polonium
    stated as though the rest had failed to load.
    """
    if centre is None:
        return f"Electrons: {electrons}"
    if not centre.has_neutron_count:
        return (
            f"Protons: {centre.protons} · Electrons: {electrons} · no naturally "
            "occurring isotope, so no neutron count is shown"
        )
    source = (
        f"most abundant isotope, {centre.isotope}"
        if centre.is_most_abundant
        else centre.isotope
    )
    return (
        f"Protons: {centre.protons} · Neutrons: {centre.neutrons} "
        f"({source}) · Electrons: {electrons}"
    )


def _provenance_text(result: ConfigurationResult) -> str:
    """Where this configuration came from, and what it is like.

    Shown quietly rather than prominently -- a reader should be able to
    tell a measured ground state from this module's arithmetic without the
    UI making a fuss about it on every element.
    """
    noble = isoelectronic_noble_gas(result.configuration)
    parts = [
        "Electron configuration model: ground-state reference"
        if result.source == "reference"
        else "Configuration generated by the general ionisation rule"
    ]
    if noble is not None:
        parts.append(f"isoelectronic with {noble}")
    return " · ".join(parts)
