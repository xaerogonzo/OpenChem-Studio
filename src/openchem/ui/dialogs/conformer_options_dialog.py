from __future__ import annotations

from openchem.chem.conformer_providers import (
    DEFAULT_OPTIMISATION_LEVEL,
    DEFAULT_RMS_THRESHOLD,
    OPTIMISATION_LEVELS,
    GenerationOptions,
)

from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
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

#: Defaults, raised from 10/50 on the funnel's evidence (2026-08-13).
#:
#: The old keep of 10 was "the number a returning user recognises", and
#: it was quietly truncating: the funnel measured drug-like molecules
#: finding 12-17 distinct conformers at 50-100 embeddings, so on
#: ordinary inputs real conformers were dropped with only a status line
#: saying so. Measured live on ethylmorphine at the old defaults:
#: 12 distinct found, 10 returned.
#:
#: **20 exceeds the maximum distinct count observed so far at 100
#: embeddings (~15-18) -- observed headroom, NOT a claim that 20 is
#: sufficient for every molecule.** A 200-embedding run reached 17 before
#: small-ring torsions shipped and the discoverable union is at least 25
#: with them, which is exactly why the cap still exists and why the
#: Details dialog says when it bites.
#:
#: 100 embeddings roughly doubles the yield on flexible molecules
#: (ethylmorphine 10 -> 15 distinct) at ~5 s against ~2 s, inside
#: Ebejer/Morris/Deane's 50-300 convention for drug-like generation.
#: Generation shows progress and is cancellable, so the cost is visible
#: rather than mysterious.
DEFAULT_CONFORMERS_TO_KEEP = 20
DEFAULT_EMBEDDINGS_TO_TRY = 100

#: The old dialog's ceiling was 200, applied to what turned out to be the
#: embedding count. Kept for embeddings; keeping more than 50 distinct
#: conformers is not a thing anybody has asked for and a larger number
#: mostly buys a slow N-squared comparison.
MAX_EMBEDDINGS = 500
MAX_CONFORMERS_TO_KEEP = 50

#: No time limit. The generation is already cancellable from the Jobs
#: panel, so a limit is a convenience rather than the only way out.
NO_TIME_LIMIT = 0


#: THE PROSE WAS ALREADY RIGHT, and that is the whole reason this
#: conversion is mechanical: every one of these tooltips already carried
#: its measurement and its caveat. What they lacked was a DECLARATION --
#: a tier, a stable id, and a place for the guard to check the structure
#: of the claim rather than the wording of it.
#:
#: FOUR OF THE SIX ARE TIER 3, which is unusually many for one dialog and
#: is a property of the subject: every control here changes what the
#: returned conformers MEAN, not merely how many there are.
_HELP: dict[str, HelpTooltip] = {
    "embeddings": HelpTooltip(
        text=(
            "How many random embeddings to generate.\n\n"
            "The search is random rather than exhaustive, so more attempts "
            "find more distinct shapes -- with no guarantee attached to any "
            "count. Cost is roughly linear in this number."
        ),
        tier=2,
        help_id="conformers.embeddings_to_try",
        topic="conformers",
    ),
    "keep": HelpTooltip(
        text=(
            "How many distinct conformers to keep, lowest in energy "
            "first.\n\n"
            "FEWER MAY COME BACK, and that is a result about the molecule "
            "rather than a failure: a rigid structure has fewer distinct "
            "shapes than this. More may also be FOUND than are kept -- when "
            "that happens the rest are real conformers and a higher limit "
            "returns them, which is the one place genuine conformers are "
            "silently lost. The Details dialog after a run says which "
            "happened."
        ),
        tier=3,
        help_id="conformers.distinct_to_keep",
        topic="conformers",
    ),
    "diversity": HelpTooltip(
        text=(
            "How far apart two embeddings must be to count as different "
            "shapes.\n\n"
            "A SAMPLING AND DE-DUPLICATION PARAMETER, NOT a definition of "
            "what makes two conformers different, and no single value is "
            "right for every molecule. 0.50 A was fitted to butane, whose "
            "pairwise RMSDs really are bimodal; a drug-like molecule's are "
            "a flat continuum with no gap for a threshold to sit in.\n\n"
            "Lower keeps more near-identical structures; higher merges "
            "more. Range 0.05 to 3.00 A."
        ),
        tier=3,
        help_id="conformers.diversity_threshold",
        topic="conformers",
    ),
    "optimisation": HelpTooltip(
        text=(
            "How hard to minimise each embedding: iteration count and "
            "gradient tolerance.\n\n"
            "THESE ARE OPENCHEM'S LEVELS, inspired by Marvin's control and "
            "NOT numerically equivalent to it -- a setting of the same name "
            "in another program does not mean the same thing.\n\n"
            "Measured over 30 embeddings each of seven molecules: every "
            "level converged 30 of 30, and the retained count differed on "
            "only one molecule. A geometry that does not converge is "
            "discarded at every level, so this decides how hard to try and "
            "never what counts as a conformer."
        ),
        tier=3,
        help_id="conformers.optimisation_level",
        topic="conformers",
    ),
    "time_limit": HelpTooltip(
        text=(
            "Stop STARTING new embeddings once this many seconds have "
            "passed.\n\n"
            "Not a hard ceiling: an embedding already under way runs to the "
            "end, so the overshoot is up to one embedding. Neither RDKit's "
            "embedder nor its minimiser can be interrupted part-way. "
            "Default no limit."
        ),
        tier=2,
        help_id="conformers.time_limit",
        topic="conformers",
    ),
    "refine": HelpTooltip(
        text=(
            "Put every surviving conformer through a second, stricter "
            "minimisation, and discard any that will not settle.\n\n"
            "IT IS NOT A WAY TO FIND MORE CONFORMERS. Measured: it changes "
            "nothing at Normal or above, because those already converge. "
            "Its one visible effect was to recover what a Loose run had "
            "lost, at about 25% more time."
        ),
        tier=3,
        help_id="conformers.enhanced_refinement",
        topic="conformers",
    ),
}


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
        apply_help_tooltip(self._embeddings_spin, _HELP['embeddings'])

        self._keep_spin = QSpinBox()
        self._keep_spin.setRange(1, MAX_CONFORMERS_TO_KEEP)
        self._keep_spin.setValue(DEFAULT_CONFORMERS_TO_KEEP)
        apply_help_tooltip(self._keep_spin, _HELP['keep'])

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
        apply_help_tooltip(self._diversity_spin, _HELP['diversity'])

        self._optimisation_combo = QComboBox()
        for label in OPTIMISATION_LEVELS:
            self._optimisation_combo.addItem(label)
        self._optimisation_combo.setCurrentText(DEFAULT_OPTIMISATION_LEVEL)
        apply_help_tooltip(self._optimisation_combo, _HELP['optimisation'])

        self._time_limit_spin = QSpinBox()
        self._time_limit_spin.setRange(NO_TIME_LIMIT, 3600)
        self._time_limit_spin.setValue(NO_TIME_LIMIT)
        self._time_limit_spin.setSpecialValueText("No limit")
        self._time_limit_spin.setSuffix(" s")
        apply_help_tooltip(self._time_limit_spin, _HELP['time_limit'])

        # **Marvin's word appears nowhere**, not in this label, not in the
        # tooltip, and not in provenance. ChemAxon's `hyperfine` is short
        # molecular dynamics followed by strict optimisation; there is no
        # MD engine here and a second minimisation is not an
        # approximation of trajectory sampling.
        self._refine_check = QCheckBox("Enhanced refinement")
        apply_help_tooltip(self._refine_check, _HELP['refine'])

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
