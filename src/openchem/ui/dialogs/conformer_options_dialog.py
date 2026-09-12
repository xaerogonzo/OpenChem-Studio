from __future__ import annotations

from openchem.chem.conformer_providers import (  # noqa: F401 - re-exported
    DEFAULT_EMBEDDING_BATCH_SIZE,
    DEFAULT_PLATEAU_BATCHES,
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
    QHBoxLayout,
    QLabel,
    QRadioButton,
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

#: The search CEILING, not the number of embeddings a run makes.
#:
#: **IT CHANGED MEANING WHEN THE SEARCH DID, AND THAT IS WHY IT MOVED.**
#: Generation used to make exactly this many embeddings once; it now embeds
#: in batches and stops when a few in a row add nothing unmatched, so this
#: is the hard stop for a search that has not plateaued. Left at 100 it
#: would cut every flexible molecule short -- measured, the plateau arrives
#: at 200 embeddings for the reported cage and 350-400 for ethylmorphine.
#:
#: Chosen from the corpus rather than picked: nothing measured reaches it,
#: which is what a ceiling is for. Cost at the ceiling is roughly a minute,
#: and generation shows progress and is cancellable from the Jobs panel.
DEFAULT_EMBEDDINGS_TO_TRY = 1000

#: The old dialog's ceiling was 200, applied to what turned out to be the
#: embedding count. Kept for embeddings; keeping more than 50 distinct
#: conformers is not a thing anybody has asked for and a larger number
#: mostly buys a slow N-squared comparison.
MAX_EMBEDDINGS = 5000
MAX_CONFORMERS_TO_KEEP = 50

#: No time limit. The generation is already cancellable from the Jobs
#: panel, so a limit is a convenience rather than the only way out.
NO_TIME_LIMIT = 0

#: What "Automatic" spends, and it is a TESTED default rather than UI
#: decoration -- `tests/test_conformer_search.py` gates it on three cases
#: finishing: the rigid cage (plateau at 200 embeddings, ~13 s), the
#: flexible stress case ethylmorphine (plateau at 350-400, ~20 s), and a
#: molecule that reaches neither, which must stop on the ceiling.
#:
#: "Conformers are too few" is a complaint, not a request for a
#: stochastic-search configuration console. Nobody should have to know
#: whether to ask for 500 embeddings or 2 plateau batches, so by default
#: they are not asked.
AUTOMATIC_SEARCH = {
    "max_embeddings": DEFAULT_EMBEDDINGS_TO_TRY,
    "embedding_batch_size": DEFAULT_EMBEDDING_BATCH_SIZE,
    "plateau_batches_required": DEFAULT_PLATEAU_BATCHES,
    "time_limit_seconds": None,
}


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
    "automatic": HelpTooltip(
        text=(
            "Search until no new conformers are turning up, using a "
            "documented budget.\n\n"
            "The search embeds in batches and stops when two in a row add "
            "nothing new -- measured, that arrives at 200 embeddings for a "
            "fused cage and 350 to 400 for a flexible drug-like molecule. "
            "It is capped, and it can be cancelled from the Jobs panel."
        ),
        tier=2,
        help_id="conformers.search_automatic",
        topic="conformers",
    ),
    "advanced": HelpTooltip(
        text=(
            "Set the sampling budget by hand instead.\n\n"
            "Nothing here changes what a conformer IS -- only how hard the "
            "search looks before giving up. The results are selected the "
            "same way either way."
        ),
        tier=2,
        help_id="conformers.search_advanced",
        topic="conformers",
    ),
    "embeddings": HelpTooltip(
        text=(
            "The most random embeddings the search may make.\n\n"
            "A CEILING, NOT A COUNT. The search stops earlier when new "
            "shapes stop appearing, so a rigid molecule spends a fraction "
            "of this. Reaching it instead means the search was still "
            "finding things when it ran out of budget -- the Details "
            "dialog after a run says which happened.\n\n"
            "Cost is roughly linear in the embeddings actually made."
        ),
        tier=2,
        help_id="conformers.embeddings_to_try",
        topic="conformers",
    ),
    "batch": HelpTooltip(
        text=(
            "How many embeddings the search makes between checks for new "
            "shapes.\n\n"
            "IT DOES NOT CHANGE WHAT IS SAMPLED. Seeds come from a running "
            "count across the whole search, so the same budget draws the "
            "same embeddings at any batch size -- this trades how often "
            "the search can notice a plateau against the cost of checking."
        ),
        tier=3,
        help_id="conformers.embedding_batch_size",
        topic="conformers",
    ),
    "plateau": HelpTooltip(
        text=(
            "How many batches in a row must find nothing new before the "
            "search stops.\n\n"
            "ONE IS NOT EVIDENCE. A random search can miss a rare shape for "
            "a whole batch and find it in the next, so stopping at the "
            "first quiet one ends searches early. Higher is more thorough "
            "and slower.\n\n"
            "Stopping here means no new shapes were SAMPLED recently. It is "
            "not a statement that the molecule has no more."
        ),
        tier=3,
        help_id="conformers.plateau_batches",
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

        # **THE SEARCH HAS FOUR KNOBS AND SHOWS NONE OF THEM BY DEFAULT.**
        # Supporting a setting is not a reason to put it on screen: the
        # report behind this work was "I get way, way less conformers than I
        # should", which nobody answers by choosing a batch size.
        self._automatic = QRadioButton("Automatic")
        self._advanced = QRadioButton("Advanced")
        self._automatic.setChecked(True)
        apply_help_tooltip(self._automatic, _HELP['automatic'])
        apply_help_tooltip(self._advanced, _HELP['advanced'])
        search_mode = QHBoxLayout()
        search_mode.setContentsMargins(0, 0, 0, 0)
        search_mode.addWidget(self._automatic)
        search_mode.addWidget(self._advanced)
        search_mode.addStretch()
        self._search_mode = QWidget()
        self._search_mode.setLayout(search_mode)

        self._batch_spin = QSpinBox()
        self._batch_spin.setRange(1, MAX_EMBEDDINGS)
        self._batch_spin.setValue(DEFAULT_EMBEDDING_BATCH_SIZE)
        apply_help_tooltip(self._batch_spin, _HELP['batch'])

        self._plateau_spin = QSpinBox()
        self._plateau_spin.setRange(1, 10)
        self._plateau_spin.setValue(DEFAULT_PLATEAU_BATCHES)
        apply_help_tooltip(self._plateau_spin, _HELP['plateau'])

        form = QFormLayout()
        form.addRow("Distinct conformers to keep:", self._keep_spin)
        form.addRow("Diversity threshold (RMSD):", self._diversity_spin)
        form.addRow("Optimisation:", self._optimisation_combo)
        form.addRow("", self._refine_check)
        form.addRow("Search:", self._search_mode)
        # The four the radio hides. Kept in the same form so they line
        # up with the rest when they appear.
        self._advanced_rows = (
            ("Maximum embeddings:", self._embeddings_spin),
            ("Embeddings per batch:", self._batch_spin),
            ("Stop after quiet batches:", self._plateau_spin),
            ("Time limit:", self._time_limit_spin),
        )
        for label, widget in self._advanced_rows:
            form.addRow(label, widget)
        self._form = form
        self._advanced.toggled.connect(self._on_advanced_toggled)
        self._on_advanced_toggled(False)

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

    def _on_advanced_toggled(self, advanced: bool) -> None:
        """Show or hide the search controls.

        `setRowVisible` rather than hiding the widgets: hiding a field
        leaves its LABEL behind, which is the width-clip family of defect
        this project has already paid for three times.
        """
        for index in range(self._form.rowCount()):
            item = self._form.itemAt(index, QFormLayout.ItemRole.FieldRole)
            widget = None if item is None else item.widget()
            if widget in (w for _label, w in self._advanced_rows):
                self._form.setRowVisible(index, advanced)
        self.adjustSize()

    def is_automatic(self) -> bool:
        """Whether the documented budget is in use rather than these fields."""
        return self._automatic.isChecked()

    def embeddings_to_try(self) -> int:
        """The search CEILING. Automatic spends the documented budget."""
        if self.is_automatic():
            return int(AUTOMATIC_SEARCH["max_embeddings"])
        return self._embeddings_spin.value()

    def conformers_to_keep(self) -> int:
        return self._keep_spin.value()

    def options(self) -> GenerationOptions:
        """Everything beyond the two counts, as one object.

        The counts stay separate because `request_conformers` has taken
        them as parameters since before this existed and a caller that
        wants nothing else should not have to build an object.
        """
        if self.is_automatic():
            # **THE DOCUMENTED BUDGET, read from one place.** Reproducing
            # the three numbers here would make `AUTOMATIC_SEARCH` a
            # comment rather than a setting, and the gate that measures it
            # would be measuring something else.
            search = dict(AUTOMATIC_SEARCH)
        else:
            seconds = self._time_limit_spin.value()
            search = {
                "max_embeddings": self._embeddings_spin.value(),
                "embedding_batch_size": self._batch_spin.value(),
                "plateau_batches_required": self._plateau_spin.value(),
                "time_limit_seconds": None if seconds == NO_TIME_LIMIT else float(seconds),
            }
        return GenerationOptions(
            diversity_rmsd=self._diversity_spin.value(),
            optimisation=self._optimisation_combo.currentText(),
            enhanced_refinement=self._refine_check.isChecked(),
            **search,
        )
