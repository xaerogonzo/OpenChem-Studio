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
    LONGEST_LIVED,
    MOST_ABUNDANT,
    Configuration,
    ConfigurationResult,
    ConfigurationUnavailable,
    Nucleus,
    Subshell,
    ion_configuration,
    isoelectronic_noble_gas,
    nucleus,
)
from openchem.chem.nuclides import format_half_life

logger = logging.getLogger(__name__)

_NUCLEUS_COLOUR = QColor("#e8546b")
_ELECTRON_COLOUR = QColor("#3aa0e0")
_RING_COLOUR = QColor("#7a7a7a")
_RING_LABEL_COLOUR = QColor("#4a4a4a")

#: The nucleus disc, and how far apart the ring counts fan, in radians.
_NUCLEUS_RADIUS = 26.0
_RING_LABEL_FAN = 0.30
_BOX_COLOUR = QColor("#444444")
_MUTED = "color: #666666;"


#: An electron dot, in pixels: never bigger than this, never smaller, and
#: in between it is a fraction of the arc each electron has to itself.
MAX_ELECTRON_RADIUS = 5.0
MIN_ELECTRON_RADIUS = 1.8
ELECTRON_ARC_FRACTION = 0.32


def electron_radius(ring_radius: float, electrons: int) -> float:
    """How big to draw one electron on a ring holding `electrons` of them.

    **A 32-ELECTRON SHELL DREW AS A SOLID BAND**, which is what polonium
    looked like in the report behind this: seven rings of touching dots
    with no nucleus in the middle. At the widget's own minimum size the
    N shell gives each electron about 12 px of arc, and a fixed 5 px
    radius is a 10 px dot in it.

    Scaled against the arc rather than against the electron count, because
    it is the SPACING that decides whether two dots touch -- a big ring
    with many electrons can be roomier than a small ring with few.
    """
    if electrons <= 0:
        return MAX_ELECTRON_RADIUS
    arc = 2 * math.pi * ring_radius / electrons
    return max(MIN_ELECTRON_RADIUS, min(MAX_ELECTRON_RADIUS, ELECTRON_ARC_FRACTION * arc))


class ShellDiagram(QWidget):
    """Nucleus with proton/neutron counts, electrons on their shells.

    Each ring carries its own electron count, which is the number anybody
    reads this drawing for and the only thing still legible once a shell
    holds 32 of them.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._shells: dict[int, int] = {}
        self._nucleus: Nucleus | None = None
        # **A FLOOR, NOT A PREFERRED SIZE.** 220 was comfortable and it
        # set the Atom tab's minimum, which through `QTabWidget`'s
        # maximum-over-pages set the whole dialog's -- the same chain that
        # put the action row off the bottom of a 1032 px screen. The rings
        # scale to whatever they are given, so the smallest legible square
        # is the honest floor; the dialog opens far larger.
        self.setMinimumSize(96, 96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_atom(self, shells: dict[int, int], centre: Nucleus | None) -> None:
        self._shells = dict(shells)
        self._nucleus = centre
        self.update()

    def _draw_ring_count(
        self,
        painter: QPainter,
        centre: QPointF,
        span: float,
        rings: int,
        index: int,
        electrons: int,
    ) -> None:
        """One ring's electron count, in the empty annulus beside it.

        **NEVER SKIPPED.** The first version dropped any label whose gap
        fell inside the nucleus disc, which is the innermost shell of
        every element -- a silent omission, in the one branch of this
        codebase written against silent omissions. A ring with no room
        inside it is labelled just OUTSIDE instead.
        """
        radius = span * index / rings
        previous = span * (index - 1) / rings
        inset = min(9.0, max(4.0, (radius - previous) / 2))
        label_radius = radius - inset
        if label_radius <= _NUCLEUS_RADIUS + 6:
            # Outside the ring instead -- and clear of the nucleus even
            # then, which uranium needs: its K shell sits at r=13, so
            # `radius + inset` is still under the disc.
            label_radius = max(radius + inset, _NUCLEUS_RADIUS + 16)
        # Fanned across the left, centred on due-left.
        bearing = math.pi - (index - (rings + 1) / 2) * _RING_LABEL_FAN
        x = centre.x() + label_radius * math.cos(bearing)
        y = centre.y() + label_radius * math.sin(bearing)
        box = QRectF(x - 11, y - 6, 22, 12)
        # A backing patch, because a fanned label can cross a ring line.
        painter.fillRect(box, self.palette().base())
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, str(electrons))

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())

        centre = QPointF(self.width() / 2, self.height() / 2)
        # Leave room for the outermost electrons, which sit ON the ring.
        span = min(self.width(), self.height()) / 2 - 16
        count = max(1, len(self._shells))

        label_font = QFont(painter.font())
        label_font.setPointSizeF(max(6.5, label_font.pointSizeF() - 2))

        for index, (shell, electrons) in enumerate(sorted(self._shells.items()), start=1):
            radius = span * index / count
            painter.setFont(painter.font())
            painter.setPen(QPen(_RING_COLOUR, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(centre, radius, radius)

            dot = electron_radius(radius, electrons)
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
                painter.drawEllipse(point, dot, dot)

            # **THE COUNT GOES IN THE GAP BESIDE ITS OWN RING**, where no
            # electron can be: dots sit exactly ON the rings, so the
            # annulus between two of them is empty by construction.
            #
            # FANNED rather than stacked on one bearing, which the first
            # version did and a magnified screenshot immediately killed:
            # polonium's rings are 15 px apart, so six labels at due-left
            # ran together and "18 32" read as one number. They spread
            # across the left side now, which buys separation from the
            # ANGLE where there is none in the radius.
            painter.setFont(label_font)
            painter.setPen(QPen(_RING_LABEL_COLOUR))
            self._draw_ring_count(painter, centre, span, count, index, electrons)
            del shell

        painter.setFont(QFont(painter.font().family()))
        if self._nucleus is not None:
            painter.setBrush(_NUCLEUS_COLOUR)
            painter.setPen(QPen(_NUCLEUS_COLOUR.darker(140), 1))
            painter.drawEllipse(centre, _NUCLEUS_RADIUS, _NUCLEUS_RADIUS)
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
            f"Protons: {centre.protons} · Electrons: {electrons} · no isotope "
            "is recorded for this element, so no neutron count is shown"
        )
    # **THE BASIS IS READ, NOT INFERRED.** Which isotope this is and WHY
    # are different claims, and deducing the second from whichever other
    # fields happen to be None is how they get confused.
    if centre.isotope_basis == LONGEST_LIVED:
        half_life = format_half_life(centre.half_life) if centre.half_life else "?"
        source = f"longest-lived isotope, {centre.isotope}, {half_life}"
    elif centre.isotope_basis == MOST_ABUNDANT:
        source = f"most abundant isotope, {centre.isotope}"
    else:
        source = centre.isotope
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
