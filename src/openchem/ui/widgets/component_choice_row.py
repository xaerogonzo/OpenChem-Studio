"""The row under the Properties header that lets a person say which piece of a multi-piece drawing is meant.

A drawing of a salt, a hydrate or a mixture has several components, and the compound-property calculators
are handed one of them: ChEMBL's parent when the rule leaves exactly one, else the largest, which is a guess
(`chem/components.py`). This row shows what is computed on and lets the person replace the guess with a
choice. The widget computes nothing: it is handed the components' SMILES (the chem layer made them) and
reports the pick, which the window turns into an undoable command.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

#: The combo's data for "no choice": the automatic pick.
AUTOMATIC = ""


class ComponentChoiceRow(QWidget):
    """`Compute on: [Automatic | <component> ...]`, visible only for a drawing with different components."""

    #: The canonical SMILES the person picked, or `AUTOMATIC` ("") to go back to the automatic pick.
    choice_made = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("componentChoiceRow")
        self._label = QLabel("Compute on:", self)
        self._combo = QComboBox(self)
        self._combo.setObjectName("componentChoiceCombo")
        self._combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._combo.setMinimumContentsLength(12)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        layout.addWidget(self._combo, 1)
        self._combo.activated.connect(self._on_activated)
        self.setVisible(False)

    @property
    def combo(self) -> QComboBox:
        """The picker itself, so the panel that owns the help contract can attach its tooltip."""
        return self._combo

    def set_components(self, components: Sequence[str], current: str) -> None:
        """Offer `components` (one entry per distinct species), with `current` selected, or hide the row.

        Fewer than two distinct components has nothing to choose between, so the row is hidden. A `current`
        that no component matches (the drawing was edited since) reads as Automatic, which is what the
        calculators do with it.
        """
        distinct = list(dict.fromkeys(components))
        self._combo.blockSignals(True)
        try:
            self._combo.clear()
            self._combo.addItem("Automatic", AUTOMATIC)
            for smiles in distinct:
                self._combo.addItem(smiles, smiles)
            index = self._combo.findData(current) if current else 0
            self._combo.setCurrentIndex(max(index, 0))
        finally:
            self._combo.blockSignals(False)
        self.setVisible(len(distinct) >= 2)

    def current_choice(self) -> str:
        """What the combo shows now: a component's SMILES, or `AUTOMATIC`."""
        return str(self._combo.currentData() or AUTOMATIC)

    def _on_activated(self, _index: int) -> None:
        self.choice_made.emit(self.current_choice())
