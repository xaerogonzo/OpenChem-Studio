"""Type a short L-amino-acid sequence and insert the atomistic peptide.

The dialog imports no RDKit. The host expands the text and inserts the
molblock through ``insert_template_molblock``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

_TOPIC = "peptide-sequence"


@dataclass
class PeptideSequenceHost:
    """Lookups the dialog is handed. It imports no engine."""

    expand: Callable[[str], str]
    insert_molblock: Callable[[str, Callable[[str | None], None]], None]


class PeptideSequenceDialog(QDialog):
    def __init__(self, host: PeptideSequenceHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Peptide sequence")
        self.setModal(False)
        self.resize(440, 180)
        self._host = host

        self._sequence = QLineEdit(self)
        self._sequence.setObjectName("sequence")
        self._sequence.setPlaceholderText("AEG or Ala-Glu-Gly")
        apply_help_tooltip(
            self._sequence,
            HelpTooltip(
                text=(
                    "A linear peptide of the 20 standard L-amino acids, at least two "
                    "residues. Uppercase one-letter codes (AEG) or hyphenated "
                    "three-letter names (Ala-Glu-Gly). Neutral free termini, not a "
                    "zwitterion, not D-residues, and not the editor's polymer mode."
                ),
                tier=1,
                help_id="peptide_sequence.sequence",
                topic=_TOPIC,
                help_anchor=_TOPIC,
            ),
        )

        self._status = QLabel("", self)
        self._status.setObjectName("status")
        self._status.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Close,
            self,
        )
        self._insert = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._insert.setText("Insert")
        self._insert.setObjectName("insert")
        self._insert.setDefault(True)
        apply_help_tooltip(
            self._insert,
            HelpTooltip(
                text=(
                    "Builds one connected atomistic peptide and places it to the "
                    "right of the drawing as one undo step."
                ),
                tier=1,
                help_id="peptide_sequence.insert",
                topic=_TOPIC,
                help_anchor=_TOPIC,
            ),
        )
        buttons.accepted.connect(self._on_insert)
        buttons.rejected.connect(self.close)

        form = QFormLayout()
        form.addRow("Sequence:", self._sequence)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._status)
        layout.addWidget(buttons)

    def snapshot(self) -> dict[str, object]:
        return {
            "sequence": self._sequence.text(),
            "status": self._status.text(),
        }

    def set_sequence(self, text: str) -> None:
        self._sequence.setText(text)

    def _on_insert(self) -> None:
        try:
            molblock = self._host.expand(self._sequence.text())
        except ValueError as exc:
            self._status.setText(str(exc))
            return
        self._status.setText("Inserting…")

        def done(error: str | None) -> None:
            self._status.setText("Inserted." if error is None else error)

        self._host.insert_molblock(molblock, done)
