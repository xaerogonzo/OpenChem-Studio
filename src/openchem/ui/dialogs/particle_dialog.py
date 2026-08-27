"""Compose a hadron from quarks and see what it adds up to.

The editor for `domain.particle`. Three quarks make a baryon, three
antiquarks an antibaryon, a quark with an antiquark a meson; the additive
quantum numbers are derived from the content and the result is looked up
against the PDG summary tables.

## IT SHOWS THREE VERDICTS, NOT TWO

    invalid                  not a baryon or a meson
    valid, not identified    the arithmetic works, no unique named state
    identified               one PDG row matches this content

The middle row is the one the layout is built around, because it is the
one a two-state design would have to lie about. `u d s` reaches it -- the
content of BOTH Lambda and Sigma zero -- and so does any quark with its
own antiquark, which the PDG prints as a superposition rather than a
pair. See `domain/particle.py`.

## THE DERIVED PANEL NEVER READS A PDG ROW

Charge, baryon number, strangeness and the rest come from the quark
content whether or not anything was identified, so they are on screen for
a composition with no name at all. Reading them off a matched row instead
would make the panel go blank exactly when the arithmetic is the only
thing there is to show.

## NO CHEMISTRY

This dialog imports `domain.particle` and nothing else of the
application's; there is no path from a particle to a molecule. See the
layering guard in `tests/test_particle.py`.
"""

from __future__ import annotations

from fractions import Fraction

from openchem.domain.particle import (
    Composition,
    Flavour,
    Quark,
    Verdict,
    identify,
)
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

#: The slots a composition is built in. Three is the maximum a hadron here
#: takes, and the third is disabled for a meson rather than hidden --
#: a control that vanishes reads as a bug, and one that greys out says
#: "a meson has two".
_SLOTS = 3

#: `(label, flavour, anti)` for the picker. Antiquarks are spelled `ubar`
#: rather than with a combining overbar: this text reaches a result string
#: and a console, and a non-ASCII glyph there has already cost this
#: project a `UnicodeEncodeError`.
_CHOICES: tuple[tuple[str, Flavour, bool], ...] = tuple(
    [(f.value, f, False) for f in Flavour]
    + [(f"{f.value}bar", f, True) for f in Flavour]
)


def _fraction(value: Fraction) -> str:
    """`1`, `-1`, `1/2`. An integer-valued Fraction prints as an integer,
    because `1/1` reads as an unfinished calculation."""
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


_HELP: dict[str, HelpTooltip] = {
    "slot": HelpTooltip(
        text=(
            "One quark of the composition.\n\n"
            "Three quarks make a baryon, three antiquarks an antibaryon, and "
            "one quark with one antiquark makes a meson. An antiquark is "
            "written with 'bar', so 'dbar' is the anti-down.\n\n"
            "Anything else is refused rather than answered: exotic hadrons "
            "such as tetraquarks are real and are out of scope here."
        ),
        tier=2,
        help_id="particle.quark_slot",
    ),
    "meson": HelpTooltip(
        text=(
            "Compose a meson from two quarks instead of a baryon from "
            "three.\n\n"
            "The third slot is disabled rather than hidden, so the control "
            "says a meson has two constituents rather than appearing to "
            "have lost one."
        ),
        tier=1,
        help_id="particle.meson_mode",
    ),
    "identify": HelpTooltip(
        text=(
            "Adds up the quantum numbers and looks for a matching PDG "
            "state.\n\n"
            "THE LOOKUP IS BY QUARK CONTENT, never by quantum-number tuple. "
            "Matching numbers is necessary and not sufficient for identity: "
            "Lambda and Sigma zero are both u d s with the same charge, "
            "baryon number, strangeness and third isospin component, and "
            "differ only in TOTAL isospin, which is not a sum over the "
            "content. When several states share a content this reports all "
            "of them rather than choosing."
        ),
        tier=3,
        help_id="particle.identify",
    ),
    "reset": HelpTooltip(
        text="Returns the three slots to up, up, down -- a proton.",
        tier=1,
        help_id="particle.reset",
    ),
}


class ParticleDialog(QDialog):
    """Quark content in, derived quantum numbers and a verdict out."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Quarks and Hadrons")
        self.resize(560, 560)

        self._slots: list[QComboBox] = []
        slot_row = QHBoxLayout()
        for index in range(_SLOTS):
            box = QComboBox(self)
            for label, flavour, anti in _CHOICES:
                box.addItem(label, (flavour, anti))
            apply_help_tooltip(box, _HELP["slot"])
            box.currentIndexChanged.connect(self._refresh)
            self._slots.append(box)
            slot_row.addWidget(box)
        slot_row.addStretch(1)

        self._meson = QPushButton("Meson (two quarks)", self)
        self._meson.setCheckable(True)
        apply_help_tooltip(self._meson, _HELP["meson"])
        self._meson.toggled.connect(self._on_meson_toggled)

        self._identify = QPushButton("Identify", self)
        apply_help_tooltip(self._identify, _HELP["identify"])
        self._identify.clicked.connect(self._refresh)

        self._reset = QPushButton("Reset to a proton", self)
        apply_help_tooltip(self._reset, _HELP["reset"])
        self._reset.clicked.connect(self._reset_to_proton)

        button_row = QHBoxLayout()
        button_row.addWidget(self._meson)
        button_row.addWidget(self._identify)
        button_row.addWidget(self._reset)
        button_row.addStretch(1)

        self._verdict = QLabel(self)
        self._verdict.setWordWrap(True)
        self._verdict.setStyleSheet("font-weight: bold;")
        self._reason = QLabel(self)
        self._reason.setWordWrap(True)

        derived_box = QGroupBox("Derived from the quark content", self)
        self._derived_form = QFormLayout(derived_box)
        self._derived: dict[str, QLabel] = {}
        for key, caption in (
            ("charge", "Electric charge Q:"),
            ("baryon", "Baryon number B:"),
            ("strangeness", "Strangeness S:"),
            ("charm", "Charm C:"),
            ("bottomness", "Bottomness B':"),
            ("topness", "Topness T:"),
            ("isospin_3", "Isospin I3:"),
            ("hypercharge", "Hypercharge Y:"),
        ):
            label = QLabel("-", derived_box)
            self._derived[key] = label
            self._derived_form.addRow(caption, label)

        self._measured = QLabel(self)
        self._measured.setWordWrap(True)

        # Says on the FACE of the dialog what the tooltips also say. A
        # meaning that lives only in a tooltip is absent from every
        # screenshot, which this project has already paid for twice.
        note = QLabel(
            "Quantum numbers are summed from the quark content. Matching them "
            "is necessary and not sufficient for identity: a PDG row is the "
            "claim, and the arithmetic only checks it.",
            self,
        )
        note.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Quark content:", self))
        layout.addLayout(slot_row)
        layout.addLayout(button_row)
        layout.addWidget(self._verdict)
        layout.addWidget(self._reason)
        layout.addWidget(derived_box)
        layout.addWidget(self._measured)
        layout.addWidget(note)
        layout.addStretch(1)
        layout.addWidget(buttons)

        self._reset_to_proton()

    # --- state -------------------------------------------------------------

    def _on_meson_toggled(self, checked: bool) -> None:
        self._slots[2].setEnabled(not checked)
        if checked:
            # A meson's default is the one whose content is unambiguous.
            self._select(0, Flavour.UP, False)
            self._select(1, Flavour.DOWN, True)
        self._refresh()

    def _select(self, slot: int, flavour: Flavour, anti: bool) -> None:
        """Choose a flavour in one slot.

        **`findData` CANNOT DO THIS, and it fails SILENTLY.** The item
        data is a Python tuple `(Flavour, bool)`; `QComboBox.findData`
        compares through `QVariant` and returns -1 rather than matching
        it, so every call left its box at index 0. Measured by driving
        the app: the dialog opened on `u u u` -- a Delta++ -- while
        `_reset_to_proton` believed it had set `u u d`, and every test
        passed because `content()` reads `currentData()`, which was
        perfectly correct about the wrong selection.

        Comparing in Python is the fix. A -1 from a lookup that should
        always succeed would be a programming error, so it raises rather
        than leaving the box wherever it was.
        """
        box = self._slots[slot]
        for index in range(box.count()):
            if box.itemData(index) == (flavour, anti):
                box.setCurrentIndex(index)
                return
        # `getattr`, because this message must survive being handed
        # something that is not a Flavour at all -- which is exactly the
        # case a caller would be in when it deserves to be told.
        name = getattr(flavour, "value", flavour)
        raise ValueError(f"no combo entry for {name} anti={anti}")

    def _reset_to_proton(self) -> None:
        self._meson.setChecked(False)
        self._slots[2].setEnabled(True)
        self._select(0, Flavour.UP, False)
        self._select(1, Flavour.UP, False)
        self._select(2, Flavour.DOWN, False)
        self._refresh()

    def content(self) -> tuple[Quark, ...]:
        """The composition the slots currently describe."""
        used = self._slots[:2] if self._meson.isChecked() else self._slots
        quarks = []
        for box in used:
            flavour, anti = box.currentData()
            quarks.append(Quark(flavour, anti))
        return tuple(quarks)

    # --- rendering ---------------------------------------------------------

    def _refresh(self) -> None:
        result = identify(self.content())

        if result.verdict is Verdict.IDENTIFIED:
            state = result.state
            self._verdict.setText(f"Identified: {state.name} ({state.symbol})")
        elif result.verdict is Verdict.VALID_UNIDENTIFIED:
            kind = (
                result.composition.value
                if result.composition is not Composition.INVALID
                else "combination"
            )
            self._verdict.setText(f"A valid {kind}, not identified")
        else:
            self._verdict.setText("Not a valid combination")
        self._reason.setText(result.reason)

        numbers = result.numbers
        if numbers is None:
            for label in self._derived.values():
                label.setText("-")
        else:
            self._derived["charge"].setText(_fraction(numbers.charge))
            self._derived["baryon"].setText(_fraction(numbers.baryon_number))
            self._derived["strangeness"].setText(str(numbers.strangeness))
            self._derived["charm"].setText(str(numbers.charm))
            self._derived["bottomness"].setText(str(numbers.bottomness))
            self._derived["topness"].setText(str(numbers.topness))
            self._derived["isospin_3"].setText(_fraction(numbers.isospin_3))
            self._derived["hypercharge"].setText(_fraction(numbers.hypercharge))

        self._measured.setText(self._measured_text(result))

    def _measured_text(self, result) -> str:
        """What the PDG PRINTS, kept separate from what was derived.

        Only a single identified state gets measured values. Two
        candidates get their masses side by side and no choice between
        them, which is the whole point of the middle verdict.
        """
        if not result.candidates:
            return ""
        if result.verdict is not Verdict.IDENTIFIED:
            masses = "; ".join(
                f"{s.name} {s.mass_mev:g} MeV" for s in result.candidates
            )
            return f"PDG states sharing this content: {masses}."
        state = result.candidates[0]
        parity = "+" if state.parity > 0 else "-"
        parts = [
            f"PDG: mass {state.mass_mev:g} +/- {state.mass_uncertainty_mev:g} MeV",
            f"I(J^P) = {_fraction(state.isospin)}({_fraction(state.spin)}{parity})",
        ]
        if state.mean_life_s is not None:
            parts.append(f"mean life {state.mean_life_s:g} s")
        elif state.mean_life_note:
            parts.append(state.mean_life_note)
        return ", ".join(parts) + "."

    # --- for tests and the drive harness ------------------------------------

    def verdict_text(self) -> str:
        return self._verdict.text()

    def reason_text(self) -> str:
        return self._reason.text()

    def measured_text(self) -> str:
        return self._measured.text()

    def derived_text(self, key: str) -> str:
        return self._derived[key].text()
