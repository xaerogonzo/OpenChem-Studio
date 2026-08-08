from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

#: Defaults. 10 kept is what the single-field dialog this replaces asked
#: for, so the number a returning user recognises is unchanged; 50 tried
#: is new, and is the smallest count that found a drug-like molecule's
#: minima in the benchmark. Ebejer/Morris/Deane's convention for
#: drug-like conformer generation is 50-300 embeddings, and the app's
#: previous behaviour was effectively 10.
DEFAULT_CONFORMERS_TO_KEEP = 10
DEFAULT_EMBEDDINGS_TO_TRY = 50

#: The old dialog's ceiling was 200, applied to what turned out to be the
#: embedding count. Kept for embeddings; keeping more than 50 distinct
#: conformers is not a thing anybody has asked for and a larger number
#: mostly buys a slow N-squared comparison.
MAX_EMBEDDINGS = 500
MAX_CONFORMERS_TO_KEEP = 50


class ConformerOptionsDialog(QDialog):
    """Asks for the two numbers conformer generation actually takes.

    WHY TWO FIELDS. The dialog this replaces asked for "Number of
    conformers" and passed it straight to the EMBEDDER, so a user asking
    for 10 got 10 random embeddings and however many distinct shapes
    happened to fall out -- reported as "Kept 2 distinct conformer(s) of
    10 embedded", which reads as a failure. The two are genuinely
    different quantities: a random search finds fewer distinct shapes
    than it takes samples, and for a drug-like molecule 10 embeddings
    cannot find its minima at any de-duplication threshold (measured: at
    most 6 found against a reference lower bound of 12).

    Separate fields rather than a single number with oversampling behind
    it, because the cost is the user's to spend -- embeddings are the
    slow part, and somebody who wants a quick look at a rigid molecule
    should not silently pay for 300 of them.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Generate Conformers")

        self._embeddings_spin = QSpinBox()
        self._embeddings_spin.setRange(1, MAX_EMBEDDINGS)
        self._embeddings_spin.setValue(DEFAULT_EMBEDDINGS_TO_TRY)
        self._embeddings_spin.setToolTip(
            "How many random embeddings to generate. The search is random, not "
            "exhaustive, so more attempts find more distinct shapes -- with no "
            "guarantee attached to any count."
        )

        self._keep_spin = QSpinBox()
        self._keep_spin.setRange(1, MAX_CONFORMERS_TO_KEEP)
        self._keep_spin.setValue(DEFAULT_CONFORMERS_TO_KEEP)
        self._keep_spin.setToolTip(
            "How many distinct conformers to keep, lowest in energy first. "
            "Fewer may come back: a rigid molecule has fewer distinct shapes "
            "than this, which is a result about the molecule."
        )

        form = QFormLayout()
        form.addRow("Embeddings to try:", self._embeddings_spin)
        form.addRow("Distinct conformers to keep:", self._keep_spin)

        # Says the quiet part out loud, because "I asked for 10 and got 3"
        # is the exact confusion this dialog exists to prevent.
        note = QLabel(
            "Embeddings are attempts; conformers are the distinct shapes found "
            "among them. Fewer conformers than attempts is normal."
        )
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        # Bound methods of the dialog, not lambdas capturing it -- PySide6
        # holds a connected plain callable STRONGLY, so a self-capturing
        # lambda roots its widget for the life of the process. See
        # CLAUDE.md and tests/test_qt_object_disposal.py.
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def embeddings_to_try(self) -> int:
        return self._embeddings_spin.value()

    def conformers_to_keep(self) -> int:
        return self._keep_spin.value()
