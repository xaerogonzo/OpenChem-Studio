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
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

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
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Contents of {display_name}")
        self._summary = summary
        self._checks: dict[str, QTableWidgetItem] = {}

        headline = QLabel(
            f"{len(summary.chains)} chains, {summary.total_atoms:,} atoms", self
        )

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
            values = [
                chain.chain_id,
                chain.kind,
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
                    included = keep_chains is None or chain.chain_id in keep_chains
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

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(headline)
        layout.addWidget(warning)
        layout.addWidget(table)
        layout.addWidget(note)
        layout.addWidget(buttons)
        self.resize(760, 420)

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
