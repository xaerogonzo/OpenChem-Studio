from __future__ import annotations

from openchem.chem.conformer_providers import (
    DEFAULT_OPTIMISATION_LEVEL,
    DEFAULT_RMS_THRESHOLD,
    OPTIMISATION_LEVELS,
    GenerationOptions,
)

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
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

#: No time limit. The generation is already cancellable from the Jobs
#: panel, so a limit is a convenience rather than the only way out.
NO_TIME_LIMIT = 0


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

        # **"Diversity threshold (RMSD)", never bare "diversity".** It is
        # a sampling and de-duplication parameter, not a definition of
        # what makes two conformers different -- and the tooltip says so,
        # with the measurement behind it, so the number reads as a choice
        # rather than as a fact about chemistry.
        self._diversity_spin = QDoubleSpinBox()
        self._diversity_spin.setRange(0.05, 3.0)
        self._diversity_spin.setSingleStep(0.05)
        self._diversity_spin.setDecimals(2)
        self._diversity_spin.setSuffix(" Å")
        self._diversity_spin.setValue(DEFAULT_RMS_THRESHOLD)
        self._diversity_spin.setToolTip(
            "How far apart two embeddings must be to count as different shapes.\n"
            "This is a sampling and de-duplication parameter, NOT a definition of\n"
            "what makes two conformers different -- no single value is right for\n"
            "every molecule. 0.5 was fitted to butane, whose pairwise RMSDs really\n"
            "are bimodal; a drug-like molecule's are a flat continuum with no gap\n"
            "for a threshold to sit in.\n\n"
            "Lower keeps more near-identical structures; higher merges more."
        )

        self._optimisation_combo = QComboBox()
        for label in OPTIMISATION_LEVELS:
            self._optimisation_combo.addItem(label)
        self._optimisation_combo.setCurrentText(DEFAULT_OPTIMISATION_LEVEL)
        self._optimisation_combo.setToolTip(
            "How hard to minimise each embedding: iterations and gradient\n"
            "tolerance. These are OpenChem's levels, inspired by Marvin's\n"
            "control and not numerically equivalent to it.\n\n"
            "Measured over 30 embeddings each of seven molecules: every level\n"
            "converged 30 of 30, and the retained count differed on only one\n"
            "molecule -- ethylmorphine, where Loose found 8 against 9 elsewhere.\n"
            "A geometry that does not converge is discarded at every level."
        )

        self._time_limit_spin = QSpinBox()
        self._time_limit_spin.setRange(NO_TIME_LIMIT, 3600)
        self._time_limit_spin.setValue(NO_TIME_LIMIT)
        self._time_limit_spin.setSpecialValueText("No limit")
        self._time_limit_spin.setSuffix(" s")
        self._time_limit_spin.setToolTip(
            "Stop STARTING new embeddings once this many seconds have passed.\n"
            "Not a hard ceiling: an embedding already under way runs to the end,\n"
            "so the overshoot is up to one embedding. Neither RDKit's embedder\n"
            "nor its minimiser can be interrupted part-way."
        )

        # **Marvin's word appears nowhere**, not in this label, not in the
        # tooltip, and not in provenance. ChemAxon's `hyperfine` is short
        # molecular dynamics followed by strict optimisation; there is no
        # MD engine here and a second minimisation is not an
        # approximation of trajectory sampling.
        self._refine_check = QCheckBox("Enhanced refinement")
        self._refine_check.setToolTip(
            "Put every surviving conformer through a second, stricter\n"
            "minimisation, and discard any that will not settle.\n\n"
            "Measured: this changes nothing at Normal or above, because those\n"
            "already converge. Its one visible effect was to recover what a\n"
            "Loose run had lost -- ethylmorphine 8 back to 9 -- at about 25%\n"
            "more time. It is not a way to find more conformers."
        )

        form = QFormLayout()
        form.addRow("Embeddings to try:", self._embeddings_spin)
        form.addRow("Distinct conformers to keep:", self._keep_spin)
        form.addRow("Diversity threshold (RMSD):", self._diversity_spin)
        form.addRow("Optimisation:", self._optimisation_combo)
        form.addRow("Time limit:", self._time_limit_spin)
        form.addRow("", self._refine_check)

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

    def options(self) -> GenerationOptions:
        """Everything beyond the two counts, as one object.

        The counts stay separate because `request_conformers` has taken
        them as parameters since before this existed and a caller that
        wants nothing else should not have to build an object.
        """
        seconds = self._time_limit_spin.value()
        return GenerationOptions(
            diversity_rmsd=self._diversity_spin.value(),
            optimisation=self._optimisation_combo.currentText(),
            time_limit_seconds=None if seconds == NO_TIME_LIMIT else float(seconds),
            enhanced_refinement=self._refine_check.isChecked(),
        )
