"""Dock every ligand in the project into one receptor, and rank them.

The receptor comes from the macromolecules already in the project, and the
search box is derived from the co-crystallised ligand that entry names --
the same `binding_site.box_from_ligand` path the Docking panel uses, on
the same redocking-validated boxes the curated 49-receptor library carries.
A screen against a hand-drawn box would rank ligands by how well they fit
a guess.

THE SCORES ARE A RANKING, NOT AFFINITIES. Vina's kcal/mol are not free
energies and do not convert to a Kd; what they support is "this one before
that one, against this receptor". The dialog says so on its face rather
than in documentation, because a column of numbers headed kcal/mol is read
as a measurement by default.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.affinity_range import MIN_REPLICATES_FOR_SEPARATION
from openchem.domain.common import CacheState
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.services.docking_service import DEFAULT_NUM_POSES, DEFAULT_REPLICATES
from openchem.services.screening_service import (
    ScreeningProgress,
    ScreeningService,
    dominance_ranks,
    ranking_is_assessed,
)

logger = logging.getLogger("openchem.ui")

_RESULT_COLUMNS = (
    "Rank",
    "Ligand",
    "Best score (kcal/mol)",
    "Poses",
    "Range over runs",
)

#: The column that absorbs the dialog's spare width.
#:
#: NAMED, NOT INDEXED, so adding a column cannot silently stretch a different
#: one -- an index stays valid after a reorder and nothing looks wrong until
#: somebody magnifies the header.
_STRETCHED_COLUMN = "Ligand"

#: Why every row reads rank 1 when nothing was replicated.
#:
#: THE ABSENT STATE IS THE ONE ALMOST EVERYONE WILL SEE, because replicates
#: default to 1. Three ligands with clearly different scores all rank 1, which
#: is correct behaviour and looks exactly like a broken rank column -- so the
#: table has to say why rather than leave a reader to guess. The minimum is
#: interpolated from the derived constant, so the sentence cannot drift from
#: the arithmetic that justifies it.
_RANKING_NOT_ASSESSED = (
    "Ranking not assessed: at these replicate counts no two ligands can be "
    "separated, so every row is rank 1. Raise Replicates to at least "
    f"{MIN_REPLICATES_FOR_SEPARATION} and run again to compare run-to-run "
    "separation."
)

#: What a shared rank does and does not claim.
#:
#: A PER-PAIR STATEMENT, NOT A SIMULTANEOUS ONE. The separation rule controls
#: the false-ordering rate for ONE comparison; a table of N ligands makes
#: N(N-1)/2 of them, and at 50 ligands that is 1225. Saying so here rather than
#: only in the documentation, because a numbered table is read as a verdict.
_RANKING_ASSESSED = (
    "Ligands share a rank (=) when their score ranges overlap, so neither is "
    "distinguishable from the other by this method. Each comparison is a "
    "per-pair statement at the stated level, not a claim that the whole table "
    "is correctly ordered -- a table of N ligands makes N(N-1)/2 of them."
)


def _range_text(entry) -> str:
    """The Range-over-runs cell: the measured spread, or how few runs there were.

    "1 run" rather than a blank or a zero. A single run measured NO spread, and
    a zero would be a measurement -- five runs that genuinely agree really do
    have a width of 0.00, and the two must not render the same.
    """
    spread = entry.spread
    if spread is None:
        return ""
    if spread.n < 2:
        return "1 run"
    return f"{spread.low:.2f} to {spread.high:.2f} ({spread.n} runs)"


class VirtualScreeningDialog(QDialog):
    """Receptor choice, run control, and the ranked result."""

    def __init__(
        self,
        screening_service: ScreeningService,
        event_bus: EventBus,
        project: ProjectModel | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = screening_service
        self._project = project
        self.setWindowTitle("Virtual screening")
        self.resize(720, 560)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Docks every molecule in the project into one receptor, one at a time, "
                "and ranks them.\n"
                "Vina scores rank ligands against ONE receptor; they are not binding "
                "free energies and do not convert to a Kd."
            )
        )

        form = QFormLayout()
        self._receptor = QComboBox(self)
        for macromolecule in (project.macromolecules if project else []):
            self._receptor.addItem(macromolecule.display_name, macromolecule.uuid)
        form.addRow("Receptor", self._receptor)
        self._poses = QSpinBox(self)
        self._poses.setRange(1, 50)
        self._poses.setValue(DEFAULT_NUM_POSES)
        form.addRow("Poses per ligand", self._poses)
        # DEFAULTS TO 1, because N multiplies the WHOLE screen rather than one
        # run: 50 ligands at 5 replicates is 250 Vina searches. That cost has
        # to be chosen rather than inherited, which is why the note below
        # states the product before the run.
        self._replicates = QSpinBox(self)
        self._replicates.setRange(1, 25)
        self._replicates.setValue(DEFAULT_REPLICATES)
        self._replicates.valueChanged.connect(self._on_replicates_changed)
        form.addRow("Replicates per ligand", self._replicates)
        layout.addLayout(form)

        self._ligand_note = QLabel("", self)
        self._ligand_note.setWordWrap(True)
        layout.addWidget(self._ligand_note)

        buttons = QHBoxLayout()
        self._run = QPushButton("Run screen", self)
        self._run.clicked.connect(self._start)
        self._cancel = QPushButton("Cancel", self)
        self._cancel.setEnabled(False)
        self._cancel.clicked.connect(self._service.cancel)
        buttons.addWidget(self._run)
        buttons.addWidget(self._cancel)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._progress = QProgressBar(self)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)
        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._results = QTableWidget(0, len(_RESULT_COLUMNS), self)
        self._results.setHorizontalHeaderLabels(list(_RESULT_COLUMNS))
        # LIGAND STRETCHES, THE OTHERS SIZE TO THEIR OWN TEXT. Only column 1
        # was configured, so Rank, "Best score (kcal/mol)" and Poses kept
        # Qt's default fixed width -- and the score header, the longest of
        # the three, rendered clipped at BOTH ends as "est score (kcal/mo"
        # while the empty Ligand column took half the dialog. Found by
        # driving the dialog and magnifying the shot; the same column-sizing
        # defect the Batch panel's property tree had.
        #
        # A FIFTH COLUMN LEFT UNCONFIGURED REPRODUCES IT EXACTLY, which is why
        # the modes are derived from `_RESULT_COLUMNS` rather than listed: a
        # column added without a mode would inherit Qt's default width and clip
        # its own header, and nothing in the suite would notice.
        header = self._results.horizontalHeader()
        for column, name in enumerate(_RESULT_COLUMNS):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Stretch
                if name == _STRETCHED_COLUMN
                else QHeaderView.ResizeMode.ResizeToContents,
            )
        # **QT'S ROW INDEX CONTRADICTS THE RANK COLUMN, so it is hidden.**
        # A vertical header numbers the rows 1, 2, 3, 4 -- and this table is
        # SORTED BY SCORE, so that column reads as a strict ranking. It sat
        # immediately left of a Rank column reading 1, 1, 1 above a note
        # saying the ranking could not be assessed: the refusal was defeated
        # by the widget beside it, and a reader would believe the numbers.
        #
        # Not the same as the Docking panel's pose table, where the row index
        # merely DUPLICATES a "Pose" column -- poses really are strictly
        # ordered by score within one run, so that one is redundant rather
        # than wrong. Found by grabbing this dialog and reading the shot;
        # every guard in the file was green.
        self._results.verticalHeader().setVisible(False)
        self._results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._results, stretch=1)

        #: What the Rank column does and does not claim. ITS OWN LABEL rather
        #: than `_status`, which carries job state and is rewritten on every
        #: `ScreeningProgress` -- the defect `_box_status_label` and
        #: `_spread_label` each exist to prevent, a third time.
        self._ranking_note = QLabel("", self)
        self._ranking_note.setWordWrap(True)
        self._ranking_note.setVisible(False)
        layout.addWidget(self._ranking_note)

        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(close)
        layout.addLayout(footer)

        event_bus.subscribe(ScreeningProgress, self._on_progress)
        self._refresh_ligand_note()

    def _refresh_ligand_note(self) -> None:
        ligands = self._ligands()
        if not self._project:
            self._ligand_note.setText("No project open.")
        elif not self._project.macromolecules:
            self._ligand_note.setText(
                "No receptor in this project. Import one, or take a curated target "
                "with a validated binding site from File > Receptor Library."
            )
        elif self._replicates.value() > 1:
            # DERIVED, AND WITH NO WALL-CLOCK ESTIMATE. A seconds-per-run
            # constant would be a fitted number wearing a helpful hat -- it
            # depends on the receptor, the box, the exhaustiveness and the
            # machine. The run COUNT is arithmetic the reader can check.
            runs = len(ligands) * self._replicates.value()
            self._ligand_note.setText(
                f"{len(ligands)} ligands x {self._replicates.value()} replicates "
                f"= {runs} Vina runs, in project order."
            )
        else:
            self._ligand_note.setText(f"{len(ligands)} ligands will be docked, in project order.")
        self._run.setEnabled(bool(ligands and self._project and self._project.macromolecules))

    def _on_replicates_changed(self, _value: int) -> None:
        """A BOUND METHOD, never a lambda capturing `self`.

        PySide holds a connected plain callable strongly, so a lambda here
        would root this dialog for the life of the process -- the leak
        `test_no_signal_is_connected_to_a_self_capturing_lambda` exists to
        refuse. `valueChanged` passes the new value, which the note re-reads
        for itself.
        """
        self._refresh_ligand_note()

    def _ligands(self):
        if self._project is None:
            return []
        return [molecule for molecule in self._project.molecules if molecule.molblock]

    def _start(self) -> None:
        from openchem.chem.binding_site import box_from_ligand

        if self._project is None:
            return
        receptor = self._project.find_macromolecule(self._receptor.currentData())
        if receptor is None:
            self._status.setText("Select a receptor first.")
            return
        ligand_code = receptor.metadata.get("ligand_code", "")
        try:
            site = box_from_ligand(receptor.structure_text, receptor.source_format, ligand_code)
        except Exception as exc:  # noqa: BLE001 - reported, never crashes the dialog
            logger.exception("Could not derive a search box for %s", receptor.display_name)
            self._status.setText(
                f"Could not place a search box on {receptor.display_name}: {exc}\n"
                "A receptor from the curated library carries the ligand code that "
                "defines its site; an imported structure may not."
            )
            return
        # The site's own description is shown before the run rather than
        # after: "3 atoms spanning 2 A" means the code matched an ion and
        # every score from the screen would be meaningless, and that is
        # worth seeing while there is still time not to run it.
        self._status.setText(site.describe())
        self._service.request_screen(
            self._ligands(),
            receptor,
            site.box,
            num_poses=self._poses.value(),
            replicates=self._replicates.value(),
        )

    def _on_progress(self, event: ScreeningProgress) -> None:
        running = event.state in (CacheState.QUEUED, CacheState.RUNNING)
        self._run.setEnabled(not running)
        self._cancel.setEnabled(running)
        self._progress.setVisible(running)
        if event.total:
            self._progress.setMaximum(event.total)
            self._progress.setValue(event.completed)
        self._status.setText(event.error or event.message)
        self._render(event.entries)

    def _render(self, entries) -> None:
        from collections import Counter

        # A DOMINANCE RANK, NOT THE ROW NUMBER. `str(row + 1)` printed a strict
        # 1..N ordering whatever the evidence was -- three ligands within the
        # search's own scatter came out 1, 2, 3, which is the claim this whole
        # feature exists to stop making.
        ranks = dominance_ranks(entries)
        assessed = ranking_is_assessed(entries)
        shared = Counter(value for value in ranks if value is not None)

        self._results.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            # Rank is blank for a failure: numbering a ligand that never
            # produced a score puts it in an ordering it is not part of.
            value = ranks[row]
            if value is None:
                rank = ""
            elif assessed and shared[value] > 1:
                rank = f"{value}="
            else:
                rank = str(value)
            self._results.setItem(row, 0, QTableWidgetItem(rank))
            self._results.setItem(row, 1, QTableWidgetItem(entry.display_name))
            score = (
                f"{entry.best_affinity_kcal_mol:.2f}"
                if entry.best_affinity_kcal_mol is not None
                else (entry.error or "—")
            )
            item = QTableWidgetItem(score)
            if entry.failed:
                item.setToolTip(entry.error or "")
            self._results.setItem(row, 2, item)
            self._results.setItem(row, 3, QTableWidgetItem(str(entry.pose_count)))
            self._results.setItem(row, 4, QTableWidgetItem(_range_text(entry)))

        note = "" if not entries else (_RANKING_ASSESSED if assessed else _RANKING_NOT_ASSESSED)
        self._ranking_note.setText(note)
        self._ranking_note.setVisible(bool(note))

    def results(self):
        """The ranked entries currently shown -- read by tests and by
        anything that wants to feed the scores back into a batch table."""
        return [
            self._results.item(row, 1).text() for row in range(self._results.rowCount())
        ]
