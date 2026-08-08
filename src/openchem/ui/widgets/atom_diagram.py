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

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.electron_shells import (
    Configuration,
    ConfigurationResult,
    ConfigurationUnavailable,
    Nucleus,
    ion_configuration,
    isoelectronic_noble_gas,
    nucleus,
)

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
            painter.drawText(
                QRectF(centre.x() - 26, centre.y() - 26, 52, 52),
                Qt.AlignmentFlag.AlignCenter,
                f"{self._nucleus.protons}p\n{self._nucleus.neutrons}n",
            )
        painter.end()


class OrbitalBoxes(QWidget):
    """The `1s ↑↓ | 2s ↑↓ | 2p ↑ ↑ ↑` layout."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._configuration: Configuration | None = None
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_configuration(self, configuration: Configuration | None) -> None:
        self._configuration = configuration
        self.update()

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
                "No electrons — a bare nucleus.",
                'Press "+ electron" or "Neutral" to put one back.',
            )
            painter.end()
            return

        # Drawn in WRITING order (1s, 2s, 2p...), which is how every table
        # and textbook lays this out. The filling order lives in the model.
        subshells = self._configuration.in_writing_order()
        box, gap, label_height = 22.0, 6.0, 16.0
        x, y = 8.0, 8.0
        row_height = box + label_height + 10

        painter.setFont(QFont(painter.font().family(), 8))
        for subshell in subshells:
            width = subshell.orbitals * box + (subshell.orbitals - 1) * 2
            if x + width > self.width() - 8:
                x, y = 8.0, y + row_height
            if y + row_height > self.height():
                break

            for index, (up, down) in enumerate(subshell.spins()):
                left = x + index * (box + 2)
                painter.setPen(QPen(_BOX_COLOUR, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(left, y, box, box))
                painter.setPen(QPen(_BOX_COLOUR, 1.4))
                if up:
                    painter.drawText(
                        QRectF(left, y, box / 2, box),
                        Qt.AlignmentFlag.AlignCenter,
                        "↑",
                    )
                if down:
                    painter.drawText(
                        QRectF(left + box / 2, y, box / 2, box),
                        Qt.AlignmentFlag.AlignCenter,
                        "↓",
                    )

            painter.setPen(QPen(_BOX_COLOUR))
            painter.drawText(
                QRectF(x, y + box + 1, width, label_height),
                Qt.AlignmentFlag.AlignCenter,
                subshell.label,
            )
            x += width + gap
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

        right = QVBoxLayout()
        right.addWidget(self.title)
        right.addWidget(self.configuration_label)
        right.addWidget(self.nucleus_label)
        right.addWidget(self.boxes, 1)
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
    """
    if centre is None:
        return f"Electrons: {electrons}"
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
