"""The full Lewis structure, as a window you open on one molecule.

**A SNAPSHOT, not a view that follows the editor.** The diagram is built
once, from the molblock it was given, and never rebuilt. A window silently
showing structure A after the editor has moved to B is the failure this
removes by construction rather than by refresh logic -- and the header
says which molecule it is of, so a stale one is obvious rather than
merely wrong.

**IT CANNOT CHANGE ANYTHING.** No undo command, no event, no write of any
kind: it reads a molblock and draws. That is what makes opening it free,
and `test_opening_the_dialog_changes_nothing` is the guard.

**The ANALYSIS DETAILS panel is deliberately more than a shipped product
would show.** With one user and a chemistry model still being built, a
window into what the engine actually believes -- the electron budget, the
regions, every abstention with its reason -- is worth more than polish. It
is collapsed by default so it costs nothing to anyone not asking.

This module imports no chemistry toolkit. Everything it needs about the
molecule comes off the `LewisDiagram`, including the formula, which is
what `tests/test_layering.py` requires of anything under `ui/`.
"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.lewis_builder import CROWDED_APPROACH, build, crowding
from openchem.chem.lewis_diagram import Known
from openchem.chem.lewis_svg import render

#: What the three marks mean. Named here rather than inside the SVG so it
#: reads in the dialog's own font, and so the diagram somebody exports is
#: the diagram rather than the diagram plus a key.
LEGEND = (
    "Two dots = a localised electron pair.    "
    "A dashed outline = a delocalised system, labelled with its electron count "
    "(? if that count was not determined).    "
    "A solid line = a connection this analysis declined to represent as electrons."
)


class LewisDiagramDialog(QDialog):
    """One molecule's Lewis structure, as it was when this was opened."""

    def __init__(
        self,
        molblock: str | None,
        display_name: str = "",
        structure_revision: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._diagram = build(molblock, structure_revision=structure_revision)
        self._rendered = render(self._diagram)
        # The molecule's name is in the TITLE as well as the header,
        # because more than one of these can be open and the taskbar and
        # the window list only ever show the title.
        self.setWindowTitle(
            f"Full Lewis Structure - {display_name}"
            if display_name
            else "Full Lewis Structure"
        )

        layout = QVBoxLayout(self)

        # **WHICH MOLECULE, said out loud.** This is a separate window, it
        # does not follow the editor, and more than one can be open at
        # once; a diagram with no name on it is a diagram somebody will
        # eventually misattribute.
        heading = display_name or "Structure"
        formula = self._diagram.formula
        self._header = QLabel(
            f"<b>{heading}</b>" + (f" — {formula}" if formula else ""), self
        )
        layout.addWidget(self._header)

        self._status = QLabel(self.status_text(), self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._view = QSvgWidget(self)
        self._view.setMinimumSize(420, 340)
        self._view.load(self._rendered.svg.encode("utf-8"))
        # **A REFUSAL IS NOT SHOWN AS A PICTURE.** `render` is total and
        # returns a card carrying the reason, which keeps the renderer
        # honest -- but a QSvgWidget scales its 200-unit viewBox to fill
        # the pane, so driving the app showed that sentence at ~37 px and
        # clipped off both edges. It read as a broken window. The status
        # line above already carries the same words at a normal size.
        self._view.setVisible(self._diagram.drawable)
        layout.addWidget(self._view, 1)

        self._legend = QLabel(LEGEND, self)
        self._legend.setWordWrap(True)
        # A key to marks that are not on the page would be noise; a
        # refused diagram draws none of them.
        self._legend.setVisible(self._diagram.drawable)
        layout.addWidget(self._legend)

        self._details = QPlainTextEdit(self)
        self._details.setReadOnly(True)
        self._details.setPlainText(self.details_text())
        self._details.setVisible(False)
        self._details.setMinimumHeight(160)
        layout.addWidget(self._details)

        buttons = QHBoxLayout()
        self._details_button = QPushButton("Analysis details", self)
        self._details_button.setCheckable(True)
        self._details_button.toggled.connect(self._details.setVisible)
        buttons.addWidget(self._details_button)
        buttons.addStretch()
        self._copy_button = QPushButton("Copy SVG", self)
        self._copy_button.clicked.connect(self._copy_svg)
        buttons.addWidget(self._copy_button)
        self._save_button = QPushButton("Save SVG...", self)
        self._save_button.clicked.connect(self._save_svg)
        buttons.addWidget(self._save_button)
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        # **Export is gated on `drawable`, not on the SVG being non-empty.**
        # A refused analysis still renders -- to a card carrying its
        # reason -- so a truthiness check here would offer to export a
        # picture of an error message as though it were a structure.
        for button in (self._copy_button, self._save_button):
            button.setEnabled(self._diagram.drawable)

    # --- what it is showing --------------------------------------------------

    @property
    def diagram(self):
        return self._diagram

    @property
    def svg(self) -> str:
        return self._rendered.svg

    def status_text(self) -> str:
        """One line, and the four outcomes never share it.

        **A crowded layout is a LEGIBILITY note beside a successful
        diagram, never "analysis unsupported"** -- the plan's own limit.
        Saying the second when it is the first sends somebody looking for
        a chemistry problem that is not there.
        """
        summary = self._diagram.summary()
        if not self._diagram.drawable:
            return summary
        notes = [summary]
        if not self._rendered.complete:
            notes.append(
                "Some electrons could not be placed clear of the labels: "
                + ", ".join(self._rendered.unplaceable)
            )
        if crowding(self._diagram) < CROWDED_APPROACH:
            notes.append("This structure is crowded and may be hard to read at this size.")
        return "  ".join(notes)

    def details_text(self) -> str:
        """Everything the analysis believes, in plain text.

        ASCII only, deliberately: this text is copied out, and this
        project has recorded three separate `UnicodeEncodeError`s from
        result lines meeting a cp1252 console.
        """
        diagram = self._diagram
        accounting = diagram.accounting
        lines = [f"Status: {diagram.status.value}", ""]
        if diagram.reason:
            lines += [f"  {diagram.reason}", ""]

        lines.append("Electron accounting")
        if not diagram.drawable:
            # **A REFUSED DIAGRAM HAS NO BUDGET, and printing one is a
            # claim.** With no atoms every term is zero and `balances`
            # reads "yes" -- so the panel was reporting a closed electron
            # budget for a molecule it had explicitly declined to analyse.
            # Caught by driving the app; every test passed.
            lines.append("  not applicable - nothing was analysed")
        else:
            lines += [
                f"  total valence electrons     {accounting.valence_electrons}",
                f"  localised bonding electrons {accounting.localised_bonding_electrons}",
                f"  delocalised electrons       {accounting.delocalised_electrons}",
                f"  lone-pair electrons         {accounting.lone_pair_electrons}",
                f"  accounted                   {accounting.accounted}",
                f"  balances                    {'yes' if accounting.balances else 'no'}",
            ]
            if not accounting.balances:
                lines.append(
                    "  (a budget that cannot be closed is reported as such rather"
                    " than rounded to something that adds up)"
                )

        lines += ["", "Delocalised regions"]
        if diagram.regions:
            for region in diagram.regions:
                shape = "ring" if region.is_ring else "open"
                electrons = region.electrons
                count = (
                    f"{electrons.value} electrons"
                    if isinstance(electrons, Known)
                    else f"electron count not determined - {electrons.reason}"
                )
                atoms = ", ".join(str(index) for index in region.atom_indices)
                lines.append(f"  {shape} over atoms {atoms}: {count}")
        else:
            lines.append("  none")

        lines += ["", "Abstentions"]
        if diagram.abstentions:
            for abstention in diagram.abstentions:
                lines.append(f"  {abstention.subject}: {abstention.reason}")
        else:
            lines.append("  none")

        provenance = diagram.provenance
        lines += [
            "",
            "Provenance",
            f"  molblock              {provenance.molblock_sha or '-'}",
            f"  structure revision    {provenance.structure_revision}",
            f"  analysis version      {provenance.analysis_version or '-'}",
            f"  RDKit                 {provenance.rdkit_version or '-'}",
            "",
            "This diagram is a snapshot of the structure as it was when this"
            " window was opened. It does not follow the editor.",
        ]
        return "\n".join(lines)

    # --- export ---------------------------------------------------------------

    def _copy_svg(self) -> None:
        QGuiApplication.clipboard().setText(self._rendered.svg)

    def _save_svg(self) -> None:
        """SVG, not PNG. The renderer emits vector output and a Lewis
        diagram is exactly the kind of picture somebody scales."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Lewis structure", "lewis.svg", "SVG image (*.svg)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self._rendered.svg)
        except OSError as exc:
            QMessageBox.warning(self, "Save Lewis structure", str(exc))
