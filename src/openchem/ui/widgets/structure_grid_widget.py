"""A scrollable grid of 2D structure depictions.

The shared view for every `StructureSetResult` -- stereoisomers,
tautomers, resonance forms, conformers and Markush library members --
matching the grid MarvinSketch shows for all of them.

Renders each entry from its own molblock via `ChemistryEngine.render_2d_svg`.
Deliberately does NOT deduplicate: resonance contributors collapse to
identical canonical SMILES while being genuinely different molecules, so
any dedupe would silently delete half a resonance result (see
`chem/structure_generators.py`).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.engine import ChemistryEngine
from openchem.domain.scientific_result import StructureEntry, StructureSetResult

_COLUMNS = 3
_CELL_WIDTH = 240
_CELL_HEIGHT = 210


class _StructureCell(QFrame):
    """One depiction plus its caption. Clickable, so a grid can act as a
    picker -- Marvin's own grid has a "Select" action along the bottom."""

    clicked = Signal(int)

    def __init__(
        self, index: int, entry: StructureEntry, engine: ChemistryEngine, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._index = index
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedSize(_CELL_WIDTH, _CELL_HEIGHT)

        number = QLabel(str(index + 1), self)
        number.setAlignment(Qt.AlignmentFlag.AlignCenter)

        svg_widget = QSvgWidget(self)
        try:
            svg = engine.render_2d_svg(entry.molblock, {}, None)
            svg_widget.load(svg.encode("utf-8"))
        except Exception:  # noqa: BLE001 - one unrenderable entry must not blank the whole grid
            svg_widget.setToolTip("This structure could not be depicted.")
        svg_widget.setMinimumSize(_CELL_WIDTH - 20, _CELL_HEIGHT - 70)

        caption_parts = [entry.label] if entry.label else []
        if entry.energy is not None:
            caption_parts.append(f"{entry.energy:.2f} kcal/mol")
        if entry.score is not None:
            caption_parts.append(f"score {entry.score:.2f}")
        caption = QLabel(" — ".join(caption_parts), self)
        caption.setWordWrap(True)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setToolTip(entry.label)
        # Two lines maximum, or one long SMILES pushes every cell out of
        # alignment and the grid stops reading as a grid.
        caption.setMaximumHeight(34)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(number)
        layout.addWidget(svg_widget)
        layout.addWidget(caption)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.clicked.emit(self._index)
        super().mousePressEvent(event)


class StructureGridWidget(QWidget):
    """Marvin-style grid of generated structures."""

    structure_selected = Signal(int)  # index into the result's entries

    def __init__(
        self,
        engine: ChemistryEngine,
        result: StructureSetResult | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._result: StructureSetResult | None = None
        self._selected_index: int | None = None

        self._summary = QLabel(self)
        self._summary.setWordWrap(True)

        self._grid_host = QWidget(self)
        self._grid = QGridLayout(self._grid_host)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._grid_host)

        layout = QVBoxLayout(self)
        layout.addWidget(self._summary)
        layout.addWidget(scroll)

        if result is not None:
            self.set_result(result)

    def set_result(self, result: StructureSetResult | None) -> None:
        self._result = result
        self._selected_index = None
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if result is None or not result.entries:
            self._summary.setText(result.error if result and result.error else "No structures generated.")
            return

        self._summary.setText(self._summary_text(result))
        for index, entry in enumerate(result.entries):
            cell = _StructureCell(index, entry, self._engine, self._grid_host)
            cell.clicked.connect(self._on_cell_clicked)
            self._grid.addWidget(cell, index // _COLUMNS, index % _COLUMNS)

    def _summary_text(self, result: StructureSetResult) -> str:
        shown = len(result.entries)
        if result.total_available is not None and result.total_available > shown:
            # The distinction that matters for a Markush library: a class
            # of 38 million members showing its first thousand must not
            # read as "this class has a thousand members".
            return f"Showing {shown:,} of {result.total_available:,} structures."
        if result.truncated:
            return f"Showing {shown:,} structures (truncated at the generation limit)."
        return f"{shown:,} structure{'s' if shown != 1 else ''}."

    def _on_cell_clicked(self, index: int) -> None:
        self._selected_index = index
        self.structure_selected.emit(index)

    def selected_index(self) -> int | None:
        return self._selected_index

    def selected_entry(self) -> StructureEntry | None:
        if self._result is None or self._selected_index is None:
            return None
        return self._result.entries[self._selected_index]

    def result(self) -> StructureSetResult | None:
        return self._result
