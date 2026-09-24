"""Two to four per-atom results set beside each other, atom by atom, with how much they disagree.

Opened from a Calculator Inspector ("Compare with...") once a second method has been run on the
same structure. What is compared has already been checked by `domain.compare.compare`, which
refuses anything that is not the same molecule, drawing, atoms and units -- so this window only
ever shows a comparison that means something, and says why when it cannot.

The table is the answer: one row per atom, one column per result, a **Spread** (largest minus
smallest) and a **difference from the first** for each later result. The first result is the
reference, so the deltas read as "this method minus that one". The spread column is shaded by how
large it is against the largest, so the atoms the methods disagree about are the ones the eye
finds.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.compare import Comparison
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: What the comparison table is, for its one contract.
_TABLE_HELP = HelpTooltip(
    text=(
        "One row per atom, one column per result, then how much they disagree.\n\n"
        "Spread is the largest value minus the smallest across the results. Each later "
        "result also has a difference column: its value minus the FIRST result's, so the "
        "first is the reference. Click a column heading to sort by it; sorting by Spread "
        "puts the atoms the methods disagree about most at the top."
    ),
    tier=2,
    help_id="compare.table",
    topic="properties",
    help_anchor="properties",
)

#: What the Copy button does.
_COPY_HELP = HelpTooltip(
    text="Copy the table as text, tab-separated, with the units and the reference named.",
    tier=1,
    help_id="compare.copy",
    topic="properties",
    help_anchor="properties",
)

#: What the Close button does.
_CLOSE_HELP = HelpTooltip(
    text="Close this comparison. Nothing is changed or stored by it.",
    tier=1,
    help_id="compare.close",
    topic="properties",
    help_anchor="properties",
)

#: How strongly the largest spread is shaded, 0 to 255.
_SHADE_ALPHA = 110


def _two_lines(label: str) -> str:
    """A long result name over two lines at its first parenthesis, so a column heading is narrow.

    "Partial Charge (EEM, Bultinck 2002, 3D)" is 40 characters, and with one line per heading the
    value columns were wider than the numbers under them by a factor of ten while the last column
    elided. The full text is in the heading's tooltip.
    """
    return label.replace(" (", "\n(", 1)


class _NumberItem(QTableWidgetItem):
    """A cell that sorts by its number rather than by its text ("-0.5" sorts after "0.4" as text)."""

    def __init__(self, value: float, text: str) -> None:
        super().__init__(text)
        self._value = value
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _NumberItem):
            return self._value < other._value
        return super().__lt__(other)


class CompareResultsDialog(QDialog):
    """See the module docstring."""

    def __init__(
        self,
        comparison: Comparison,
        symbols: dict[int, str],
        molecule_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._comparison = comparison
        self._symbols = symbols
        labels = [column.label for column in comparison.columns]
        self.setWindowTitle(f"Compare — {molecule_name}")
        self.resize(900, 520)
        self.setMinimumSize(560, 320)

        self._summary = QLabel(self._summary_text(labels), self)
        self._summary.setObjectName("compareSummary")
        self._summary.setWordWrap(True)

        self._table = QTableWidget(self)
        self._table.setObjectName("compareTable")
        apply_help_tooltip(self._table, _TABLE_HELP)
        self._fill_table(labels)

        self._copy_button = QPushButton("Copy", self)
        self._copy_button.setObjectName("compareCopy")
        apply_help_tooltip(self._copy_button, _COPY_HELP)
        self._copy_button.clicked.connect(self._on_copy)
        self._close_button = QPushButton("Close", self)
        self._close_button.setObjectName("compareClose")
        apply_help_tooltip(self._close_button, _CLOSE_HELP)
        self._close_button.clicked.connect(self.close)
        for button in (self._copy_button, self._close_button):
            button.setAutoDefault(False)

        self._status = QLabel("", self)
        actions = QHBoxLayout()
        actions.addWidget(self._copy_button)
        actions.addStretch(1)
        actions.addWidget(self._status)
        actions.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._summary)
        layout.addWidget(self._table, 1)
        layout.addLayout(actions)

    # --- content ----------------------------------------------------------------

    def _summary_text(self, labels: list[str]) -> str:
        comparison = self._comparison
        worst = comparison.largest_spread()
        text = f"Comparing {', '.join(labels)} ({comparison.units or 'no units'}); the first is the reference."
        if worst is not None:
            symbol = self._symbols.get(worst.index, "")
            atom = f"atom {worst.index + 1}" + (f" ({symbol})" if symbol else "")
            text += f" They disagree most at {atom}: a spread of {worst.spread:.3g} {comparison.units}.".rstrip()
        return text

    def _fill_table(self, labels: list[str]) -> None:
        comparison = self._comparison
        headers = ["#", "Element", *labels, "Spread"]
        headers += [f"Δ {label}" for label in labels[1:]]
        table = self._table
        table.setSortingEnabled(False)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels([_two_lines(h) for h in headers])
        # The whole name, and what a difference column means, on hover.
        for column, full in enumerate(headers):
            item = table.horizontalHeaderItem(column)
            if item is not None:
                item.setToolTip(full)
        first_label = labels[0]
        spread_column = 2 + len(labels)
        for offset, label in enumerate(labels[1:]):
            item = table.horizontalHeaderItem(spread_column + 1 + offset)
            if item is not None:
                item.setToolTip(f"{label} minus {first_label}, atom by atom")
        table.setRowCount(len(comparison.rows))
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        largest = comparison.largest_spread()
        scale = largest.spread if largest is not None and largest.spread > 0 else 0.0
        for row_number, row in enumerate(comparison.rows):
            table.setItem(row_number, 0, _NumberItem(row.index + 1, str(row.index + 1)))
            table.setItem(row_number, 1, QTableWidgetItem(self._symbols.get(row.index, "")))
            for column, value in enumerate(row.values):
                table.setItem(row_number, 2 + column, _NumberItem(value, f"{value:+.4f}"))
            spread_item = _NumberItem(row.spread, f"{row.spread:.4f}")
            if scale:
                shade = QColor(214, 96, 77, int(_SHADE_ALPHA * row.spread / scale))
                spread_item.setBackground(QBrush(shade))
            table.setItem(row_number, spread_column, spread_item)
            for offset, delta in enumerate(row.deltas):
                table.setItem(
                    row_number, spread_column + 1 + offset, _NumberItem(delta, f"{delta:+.4f}")
                )
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        table.setSortingEnabled(True)

    # --- actions ------------------------------------------------------------------

    def table_text(self) -> str:
        """The comparison as tab-separated text (what Copy puts on the clipboard)."""
        return self._comparison.as_text(self._symbols)

    def _on_copy(self) -> None:
        QGuiApplication.clipboard().setText(self.table_text())
        self._status.setText("Copied.")
