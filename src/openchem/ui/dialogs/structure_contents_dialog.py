"""What is in the receptor you are about to dock against.

Measured across the bundled catalogue: 32 of 49 curated receptors are
multi-polymer complexes. 3SN6 -- catalogued as "beta2-adrenergic
receptor" -- is five polymer chains of 443, 349, 340, 128 and 58
residues, and reading their sequences in this very dialog is what
identified them: chain D opens `NIFEMLRIDEGLRLKIYKDTEGYY`, which is T4
LYSOZYME fused into the receptor, and chain A opens
`TEDQRNEEKAQREANKKIEKQLQKDKQVYRATHRLLLLGAGESGKS`, which is Gs-alpha --
`GAGESGKS` is its P-loop. The rest are G-beta, G-gamma and a nanobody.

So the target is not even the chain a size-ordered list puts first: it is
buried inside the largest chain, spliced to a lysozyme. Docking into that
file without looking means docking into a G protein, and NAMING the
chains by eye is only possible because the sequence is shown.

Chains can also be TICKED OFF, which excludes them from docking. That
travels as `keep_chains` in `receptor_prep_options`, the same dict the
service already hands to both the receptor preparation and the
interaction analysis, so the two cannot be given different receptors --
the discipline `is_stripped_residue` established and that the 195
phantom-clash bug exists to remember.

Everything ticked is the default and is treated as "no restriction"
rather than as a list of every chain, so a user who never opens this
dialog gets exactly the previous behaviour.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.structure_assembly import AssemblyAnnotation
from openchem.chem.structure_summary import StructureSummary

_COLUMNS = ["Chain", "Type", "Contents", "Atoms", "Sequence"]

#: How much of a chain's sequence to show inline. Enough to recognise a
#: chain by eye without turning the row into a wall of letters; the full
#: sequence is not truncated in the data, only in this cell.
_SEQUENCE_PREVIEW = 60


class StructureContentsDialog(QDialog):
    """A read-only chain table for one macromolecule."""

    def __init__(
        self,
        display_name: str,
        summary: StructureSummary,
        parent: QWidget | None = None,
        keep_chains: list[str] | None = None,
        assembly: AssemblyAnnotation | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Contents of {display_name}")
        self._summary = summary
        self._checks: dict[str, QTableWidgetItem] = {}
        self._assembly = assembly or AssemblyAnnotation()
        primary = self._assembly.primary
        self._surplus = set(
            self._assembly.extra_chains([c.chain_id for c in summary.chains])
        )

        headline = QLabel(
            f"{len(summary.chains)} chains, {summary.total_atoms:,} atoms", self
        )

        # What the depositor said, which beats anything inferable from
        # the atoms. Shown above the complex warning because it often
        # ANSWERS it: "5 polymer chains" is a question, "the biological
        # unit is a monomer of chain D" is the answer.
        assembly_note = QLabel(self)
        assembly_note.setWordWrap(True)
        if primary is not None:
            parts = []
            if primary.oligomeric_details:
                parts.append(f"Deposited biological unit: {primary.oligomeric_details}")
            if self._surplus:
                parts.append(
                    f"Chains not part of it: {', '.join(sorted(self._surplus))} "
                    "(marked below) — these are crystallisation extras or lattice "
                    "neighbours and are usually worth excluding."
                )
            if primary.needs_generated_copies:
                parts.append(
                    f"It is built by applying {primary.operator_applications} "
                    "transformations, so the full oligomer is not all present in "
                    "this file. Tick the box below to generate the missing copies "
                    "before docking — that only matters if your site sits at the "
                    "interface between them."
                )
            assembly_note.setText("  ".join(parts))
        assembly_note.setVisible(bool(assembly_note.text()))

        warning = QLabel(self)
        warning.setWordWrap(True)
        if summary.looks_like_a_complex():
            names = ", ".join(
                f"{c.chain_id} ({c.polymer_residue_count})"
                for c in summary.polymer_chains
            )
            warning.setText(
                f"This structure has {len(summary.polymer_chains)} polymer chains: "
                f"{names}. Deposited complexes often include a fusion partner, a "
                "nanobody or a G protein alongside the target — check that the "
                "search box sits on the chain you mean."
            )
        warning.setVisible(summary.looks_like_a_complex())

        table = QTableWidget(len(summary.chains), len(_COLUMNS), self)
        table.setHorizontalHeaderLabels(_COLUMNS)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, chain in enumerate(summary.chains):
            sequence = chain.sequence
            if len(sequence) > _SEQUENCE_PREVIEW:
                sequence = f"{sequence[:_SEQUENCE_PREVIEW]}…"
            kind = chain.kind
            if chain.chain_id in self._surplus:
                # Named on the row itself, not only in the paragraph
                # above, so the chain to untick is identifiable at a
                # glance in a table that can run to 25 rows.
                kind = f"{kind} (not in assembly)"
            values = [
                chain.chain_id,
                kind,
                chain.describe(),
                f"{chain.atom_count:,}",
                sequence,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    # The chain cell doubles as the include/exclude tick.
                    # Ticked by default: an untouched dialog must leave
                    # docking exactly as it was.
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    if keep_chains is not None:
                        included = chain.chain_id in keep_chains
                    else:
                        # First open with an annotation present:
                        # pre-untick what the depositor excluded. Still
                        # only a SUGGESTION -- nothing is applied until
                        # OK, and Cancel leaves docking untouched.
                        included = chain.chain_id not in self._surplus
                    item.setCheckState(
                        Qt.CheckState.Checked if included else Qt.CheckState.Unchecked
                    )
                    self._checks[chain.chain_id] = item
                if column == 4 and chain.sequence:
                    # The cell is truncated; the tooltip is not, so a
                    # chain stays identifiable by BLASTing what is here.
                    item.setToolTip(chain.sequence)
                table.setItem(row, column, item)
        table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setStretchLastSection(True)

        note = QLabel(
            "Untick a chain to exclude it from docking. Chains are described by "
            "size and sequence rather than named: the depositor's own "
            "description lives in mmCIF entity records, and half of these "
            "structures arrive as PDB.",
            self,
        )
        note.setWordWrap(True)

        # OFF BY DEFAULT, and offered only where it would change
        # something. Building silently would alter what a saved docking
        # box means without anybody asking for it, and offering the
        # choice on a file that already holds its whole biological unit
        # is an invitation to wonder what it does.
        self._build_assembly_check = QCheckBox(
            "Build the biological assembly before docking", self
        )
        self._build_assembly_check.setChecked(False)
        self._build_assembly_check.setToolTip(
            "Applies the depositor's transformations to generate the missing "
            "copies. Only matters when your site sits at the interface between "
            "them. If the assembly cannot be built, docking stops rather than "
            "quietly using the deposited structure instead."
        )
        # An EXPLICIT flag, not `isVisible()`. A child of a window
        # nobody has shown reports `isVisible() == False` whatever it was
        # set to, so deriving the answer from visibility would make this
        # return False under any test harness while looking right in the
        # running app -- the same blindness this project already records
        # for `repaint()` and for `_help_topic_for_visible_panel`.
        self._assembly_can_be_built = bool(primary is not None and primary.needs_generated_copies)
        self._build_assembly_check.setVisible(self._assembly_can_be_built)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(headline)
        layout.addWidget(assembly_note)
        layout.addWidget(warning)
        layout.addWidget(table)
        layout.addWidget(note)
        layout.addWidget(self._build_assembly_check)
        layout.addWidget(buttons)
        self.resize(760, 420)

    def build_assembly(self) -> bool:
        """Whether to generate the annotated assembly before docking.

        False unless the file needs generated copies AND the user asked
        for them -- the checkbox is hidden otherwise, so this cannot come
        back True for a structure where it would be a no-op.
        """
        return self._assembly_can_be_built and self._build_assembly_check.isChecked()

    def keep_chains(self) -> list[str]:
        """The ticked chains, or an EMPTY LIST when all of them are.

        "Everything" is returned as empty rather than as the full list on
        purpose: downstream, an empty `keep_chains` means "no restriction"
        and skips the filter entirely. Returning every chain id instead
        would make the filter run on every dock for no reason, and would
        silently drop any atom whose chain label the parser reports
        differently from this table -- a chainless HETATM, for one.
        """
        selected = [
            chain_id
            for chain_id, item in self._checks.items()
            if item.checkState() == Qt.CheckState.Checked
        ]
        return [] if len(selected) == len(self._checks) else selected
