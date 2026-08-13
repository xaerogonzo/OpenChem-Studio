from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.conformer import ConformerModel

#: `provenance key -> label`, in funnel order: every candidate enters at the
#: top and the rows below account for where they went.
#:
#: **`conformers_distinct` is captioned "Distinct after production
#: filtering", never bare "Distinct".** A reader seeing "Distinct: 12"
#: beside a viewer showing 10 has to guess which number is the conformers
#: they have; saying what the count is OF removes the guess.
_STAGES: tuple[tuple[str, str], ...] = (
    ("conformers_attempted", "Embeddings attempted"),
    ("conformers_embedded", "Successfully embedded"),
    ("conformers_converged", "Converged (minimised)"),
    ("conformers_distinct", "Distinct after production filtering"),
    ("conformers_returned", "Returned"),
)

#: Shown only when non-zero, since "0 failed" on every ordinary run is
#: noise that pushes the numbers that moved off the top of the dialog.
_FAILURES: tuple[tuple[str, str], ...] = (
    ("embedding_failures", "Failed to embed"),
    ("convergence_failures", "Failed to converge"),
)


class ConformerDetailsDialog(QDialog):
    """Where a conformer run's candidates went, from the run's own provenance.

    **IT COMPUTES NOTHING.** Every number here was already being recorded
    by `ConformerService` and shown to nobody -- the same "computed and
    thrown away" shape as `inapplicable_calculators` and regulatory's
    coverage notes. The forensic view (pre-optimisation diversity, the
    discarded pairs, the torsions) lives in `benchmarks/conformers/`, where
    it can be swept across seeds and thresholds; duplicating it here would
    be a second answer free to disagree with the first.

    The row that motivated this is `Distinct` against `Returned`. A run
    that finds 12 distinct conformers and hands back 10 is not a filtering
    defect -- it is the requested cap doing exactly what it says -- but the
    status line saying so has usually scrolled away by the time anybody
    wonders, and "I asked for conformers and got fewer than exist" is the
    confusion this whole diagnostic was built to answer.
    """

    def __init__(self, conformer: ConformerModel | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Conformer Generation Details")

        layout = QVBoxLayout(self)
        parameters = self._parameters(conformer)

        if not parameters:
            # **NOTHING IS FABRICATED.** A conformer from an imported file,
            # or from a project saved before any of this was recorded, has
            # no generation history -- and inventing plausible counts for
            # it would be worse than the blankness this replaces.
            layout.addWidget(
                self._note(
                    "No generation details were recorded for this conformer.\n\n"
                    "Conformers imported from a file, or generated before the "
                    "application recorded these counts, carry no history of how "
                    "they were produced."
                )
            )
        else:
            layout.addLayout(self._stages(parameters))
            note = self._truncation_note(parameters)
            if note:
                layout.addWidget(self._note(note))
            missing = [label for key, label in _STAGES if key not in parameters]
            if missing:
                # Partial provenance: say which stages were not recorded
                # rather than leaving gaps that read as zeroes.
                layout.addWidget(
                    self._note(
                        "This conformer predates some of these counts, so the "
                        "following were never recorded: " + ", ".join(missing) + "."
                    )
                )

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        # A bound method, not a self-capturing lambda: PySide6 holds a
        # connected plain callable STRONGLY and would root this dialog for
        # the life of the process. See tests/test_qt_object_disposal.py.
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _parameters(conformer: ConformerModel | None) -> dict:
        if conformer is None or conformer.provenance is None:
            return {}
        return conformer.provenance.parameters or {}

    @staticmethod
    def _stages(parameters: dict) -> QFormLayout:
        form = QFormLayout()
        for key, label in _STAGES:
            if key in parameters:
                form.addRow(f"{label}:", QLabel(str(parameters[key])))
        for key, label in _FAILURES:
            if parameters.get(key):
                form.addRow(f"{label}:", QLabel(str(parameters[key])))
        return form

    @staticmethod
    def _truncation_note(parameters: dict) -> str:
        """Why the returned count is below the distinct one, when it is.

        **ONLY WHEN THE CAP IS DEMONSTRABLY THE WHOLE REASON**, which takes
        both halves: fewer came back than were found, AND exactly as many
        came back as were asked for. A bare subtraction would produce this
        sentence for any shortfall whatever its cause, which is the "infer
        the mechanism from the residual" mistake this project has already
        paid for once.

        The cap is read from the run's OWN `num_conformers`, never from the
        dialog's current default -- an old project, or a run where the
        setting was different, would otherwise be described with a number
        that was never used.
        """
        distinct = parameters.get("conformers_distinct")
        returned = parameters.get("conformers_returned")
        cap = parameters.get("num_conformers")
        if distinct is None or returned is None or cap is None:
            return ""
        if not (distinct > returned and returned == cap):
            return ""
        omitted = distinct - returned
        return (
            f"{omitted} more distinct conformer{'s were' if omitted != 1 else ' was'} found "
            f"and not returned, because this run was asked to keep {cap}.\n\n"
            f"They converged and are distinct under the criterion this run used. "
            f"Generating again with a higher \"Distinct conformers to keep\" returns them."
        )

    @staticmethod
    def _note(text: str) -> QLabel:
        # A plain QLabel with wrapping, NOT `WrappedLabel`: that class
        # reports a MinimumExpanding policy so a wrapped label survives a
        # squeeze inside a scroll area, and in a top-level dialog row it
        # claims the whole vertical stretch instead. See CLAUDE.md.
        label = QLabel(text)
        label.setWordWrap(True)
        return label
