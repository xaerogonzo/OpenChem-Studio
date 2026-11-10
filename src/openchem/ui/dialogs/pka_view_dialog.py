"""Dedicated pKa / microspecies-distribution window.

One instance per molecule UUID. It never starts a calculator: it shows stored
pKa and distribution results, and names what is missing.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.engine import ChemistryEngine
from openchem.chem.ionisable_sites import ACID, BASE, UNKNOWN
from openchem.chem.pka_sites import (
    PkaSiteRecord,
    records_from_provenance,
    site_marker,
    species_index_from_name,
)
from openchem.chem.pka_species_ladder import LADDER_NOTE, LadderRefusal, SpeciesLadder, build_species_ladder
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import AlertResult, PhCurveResult
from openchem.ui import theme
from openchem.ui.widgets.ph_curve_widget import annotation_for
from openchem.ui.widgets.line_chart_widget import LineChartWidget

SOURCE_NOTE = (
    "pKa values come from pkasolver. The chart and pictures use the sequential "
    "model of those per-site values. Major Microspecies is a separate Dimorphite "
    "calculation. Spread is the ensemble spread already shown on pKa lines, not "
    "a calibrated confidence interval."
)


class _SpeciesPicture(QFrame):
    hovered = Signal(object)
    left = Signal()

    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMouseTracking(True)
        self._caption = QLabel(f"Species {index}", self)
        self._caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._svg = QSvgWidget(self)
        theme.paper(self._svg)
        self._svg.setFixedSize(180, 150)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._caption)
        layout.addWidget(self._svg)

    def set_picture(self, molblock: str, engine: ChemistryEngine, caption: str) -> None:
        self._caption.setText(caption)
        svg = engine.render_2d_svg(molblock, width=180, height=150)
        self._svg.load(svg.encode("utf-8"))

    def enterEvent(self, event) -> None:  # noqa: N802
        self.hovered.emit(self.index)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.left.emit()


class PkaViewDialog(QDialog):
    """Labeled sites, sequential chart, species pictures, and the sampled pH table."""

    def __init__(
        self,
        engine: ChemistryEngine,
        molecule: MoleculeModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PkaViewDialog")
        self._engine = engine
        self._molecule = molecule
        self._pka: AlertResult | None = None
        self._curve: PhCurveResult | None = None
        self._records: tuple[PkaSiteRecord, ...] = ()
        self._ladder: SpeciesLadder | LadderRefusal | None = None
        self._hover_species: int | None = None
        self._pinned_x: float | None = None
        self.resize(1100, 820)
        self.setWindowTitle(f"pKa — {molecule.display_name}")

        self._source = QLabel(SOURCE_NOTE, self)
        self._source.setWordWrap(True)
        theme.style(self._source, "color: #555555;")
        self._status = QLabel("", self)
        self._status.setWordWrap(True)

        self._svg = QSvgWidget(self)
        theme.paper(self._svg)
        self._svg.setMinimumSize(280, 240)

        self._sites = QLabel("", self)
        self._sites.setWordWrap(True)
        self._sites.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._chart = LineChartWidget(parent=self)
        self._chart.x_hovered.connect(self._on_x_hovered)
        self._chart.x_pinned.connect(self._on_x_pinned)
        self._chart.series_hovered.connect(self._on_series_hovered)

        self._pictures_note = QLabel("", self)
        self._pictures_note.setWordWrap(True)
        self._pictures_host = QWidget(self)
        self._pictures_layout = QHBoxLayout(self._pictures_host)
        self._pictures_layout.setContentsMargins(0, 0, 0, 0)
        self._pictures_scroll = QScrollArea(self)
        self._pictures_scroll.setWidgetResizable(True)
        self._pictures_scroll.setWidget(self._pictures_host)
        self._pictures_scroll.setMinimumHeight(210)

        self._table = QTableWidget(0, 1, self)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        copy = QPushButton("Copy table", self)
        copy.setToolTip("Copy the full pH table, including species whose pictures are hidden.")
        copy.clicked.connect(self._copy_table)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self._svg, 1)
        left_layout.addWidget(self._sites)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        top = QSplitter(Qt.Orientation.Horizontal, self)
        top.addWidget(left)
        top.addWidget(self._chart)
        splitter.addWidget(top)
        pictures = QWidget(self)
        pictures_layout = QVBoxLayout(pictures)
        pictures_layout.addWidget(self._pictures_note)
        pictures_layout.addWidget(self._pictures_scroll, 1)
        splitter.addWidget(pictures)
        splitter.addWidget(self._table)

        layout = QVBoxLayout(self)
        layout.addWidget(self._source)
        layout.addWidget(self._status)
        layout.addWidget(splitter, 1)
        layout.addWidget(copy, 0, Qt.AlignmentFlag.AlignRight)

        theme.follow(self, lambda _w: self._redraw_labels(), immediately=False, slot="pka-labels")

    @property
    def molecule_uuid(self) -> str:
        return self._molecule.uuid

    def records(self) -> tuple[PkaSiteRecord, ...]:
        return self._records

    def picture_message(self) -> str:
        return self._pictures_note.text()

    def table_text(self) -> str:
        rows = []
        headers = [self._table.horizontalHeaderItem(col).text() if self._table.horizontalHeaderItem(col) else "" for col in range(self._table.columnCount())]
        rows.append("\t".join(headers))
        for row in range(self._table.rowCount()):
            rows.append("\t".join(self._table.item(row, col).text() if self._table.item(row, col) else "" for col in range(self._table.columnCount())))
        return "\n".join(rows)

    def highlighted_species(self) -> int | None:
        return self._hover_species

    def chart(self) -> LineChartWidget:
        return self._chart

    def set_payload(
        self,
        molecule: MoleculeModel | None,
        pka: AlertResult | None,
        curve: PhCurveResult | None,
    ) -> None:
        if molecule is None:
            self.close()
            return
        pinned = self._chart.pinned_x()
        hover = self._hover_species
        self._molecule = molecule
        self.setWindowTitle(f"pKa — {molecule.display_name}")
        self._pka = pka
        self._curve = curve
        self._records = self._load_records()
        self._ladder = self._build_ladder()
        self._status.setText(self._status_line())
        self._redraw_labels()
        self._fill_sites()
        self._fill_chart()
        self._fill_pictures()
        self._fill_table()
        if pinned is not None:
            self._chart.pin(pinned)
        if hover is not None:
            self._set_species_highlight(hover)

    def _load_records(self) -> tuple[PkaSiteRecord, ...]:
        for source in (self._curve, self._pka):
            if source is None:
                continue
            if getattr(source, "cache_state", None) is CacheState.FAILED:
                continue
            records = records_from_provenance(getattr(source, "provenance", None))
            if records:
                return records
        return ()

    def _build_ladder(self) -> SpeciesLadder | LadderRefusal | None:
        if not self._records or not self._molecule.molblock:
            return None
        try:
            parent = self._engine.mol_from_molblock(self._molecule.molblock)
        except Exception:
            return LadderRefusal("parent", "The drawing could not be read, so no pictures are shown.")
        ph_values = list(self._curve.ph_values) if self._curve is not None and self._curve.ph_values else None
        return build_species_ladder(parent, self._records, ph_values=ph_values)

    def _status_line(self) -> str:
        pka_failed = self._pka is not None and self._pka.cache_state is CacheState.FAILED
        curve_failed = self._curve is not None and self._curve.cache_state is CacheState.FAILED
        if pka_failed and self._pka.error:
            return self._pka.error
        if self._pka is None and self._curve is None:
            return "No stored pKa or distribution result for this molecule."
        if not self._records:
            if pka_failed:
                return self._pka.error or "pKa did not produce sites."
            return "No predicted sites are stored on these results."
        mapped = sum(1 for record in self._records if record.atom_index is not None)
        bits = [f"{len(self._records)} predicted site(s)", f"{mapped} mapped onto the drawing"]
        if self._curve is None:
            bits.append("no distribution curve")
        elif curve_failed:
            bits.append("distribution failed")
        return "; ".join(bits) + "."

    def _site_styles(self) -> tuple[dict[int, str], dict[int, str]]:
        colors: dict[int, str] = {}
        labels: dict[int, str] = {}
        for record in self._records:
            if record.atom_index is None:
                continue
            marker = site_marker(record.kind)
            piece = f"{marker} {record.pka:.2f}"
            if record.atom_index in labels:
                labels[record.atom_index] = f"{labels[record.atom_index]}, {piece}"
            else:
                labels[record.atom_index] = piece
            if record.kind == ACID:
                colors[record.atom_index] = theme.acid_ink().name()
            elif record.kind == BASE:
                colors[record.atom_index] = theme.base_ink().name()
        return colors, labels

    def _redraw_labels(self) -> None:
        if not self._molecule.molblock:
            self._svg.load(b"")
            return
        colors, labels = self._site_styles()
        try:
            svg = self._engine.render_2d_svg(
                self._molecule.molblock, atom_colors=colors, atom_labels=labels, width=360, height=300
            )
        except Exception:
            self._svg.load(b"")
            return
        self._svg.load(svg.encode("utf-8"))

    def _fill_sites(self) -> None:
        if not self._records:
            self._sites.setText("No site list.")
            return
        lines = []
        for index, record in enumerate(self._records, start=1):
            marker = site_marker(record.kind)
            atom = "mapping unavailable" if record.atom_index is None else f"atom {record.atom_index + 1}"
            kind = record.kind if record.kind != UNKNOWN else "direction unknown"
            spread = f", spread {record.spread:.2f}" if record.spread else ""
            lines.append(f"{index}. {marker} pKa {record.pka:.2f} ({kind}) at {atom}{spread}")
        self._sites.setText("\n".join(lines))

    def _fill_chart(self) -> None:
        if self._curve is None or self._curve.cache_state is CacheState.FAILED or not self._curve.series:
            self._chart.set_annotation(None)
            return
        self._chart.set_annotation(annotation_for(self._curve))

    def _clear_pictures(self, message: str) -> None:
        self._pictures_note.setText(message)
        while self._pictures_layout.count():
            item = self._pictures_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _fill_pictures(self) -> None:
        ladder = self._ladder
        if self._curve is None or self._curve.cache_state is CacheState.FAILED:
            if self._records:
                self._clear_pictures("No distribution curve is stored, so there are no species pictures.")
            else:
                self._clear_pictures("")
            return
        if isinstance(ladder, LadderRefusal):
            self._clear_pictures(ladder.message)
            return
        if not isinstance(ladder, SpeciesLadder):
            self._clear_pictures("Pictures need mapped site records on the stored result.")
            return
        note = LADDER_NOTE
        if not ladder.kinds_match_curve:
            note += " The curve's acid/base centre counts differ from these site kinds, so charge labels on the chart are not treated as this molecule's net charge."
        elif not ladder.charge_labels_match:
            note += " Generated net charges do not match the chart's charge labels, so those labels are not shown as molecular net charge."
        self._clear_pictures(note)
        names = list(self._curve.series.keys())
        for index, molblock in enumerate(ladder.molblocks):
            if index in ladder.hidden:
                continue
            caption = names[index] if index < len(names) else f"Species {index}"
            cell = _SpeciesPicture(index, self._pictures_host)
            cell.set_picture(molblock, self._engine, caption)
            cell.hovered.connect(self._set_species_highlight)
            cell.left.connect(self._clear_species_highlight)
            self._pictures_layout.addWidget(cell)
        self._pictures_layout.addStretch(1)

    def _fill_table(self) -> None:
        curve = self._curve
        if curve is None or not curve.ph_values or not curve.series:
            self._table.clear()
            self._table.setRowCount(0)
            self._table.setColumnCount(1)
            return
        names = list(curve.series.keys())
        self._table.setColumnCount(1 + len(names))
        self._table.setHorizontalHeaderLabels(["pH", *names])
        self._table.setRowCount(len(curve.ph_values))
        for row, ph in enumerate(curve.ph_values):
            self._table.setItem(row, 0, QTableWidgetItem(f"{ph:.2f}"))
            for col, name in enumerate(names, start=1):
                values = curve.series[name]
                text = f"{values[row]:.4g}" if row < len(values) else ""
                self._table.setItem(row, col, QTableWidgetItem(text))

    def _copy_table(self) -> None:
        QGuiApplication.clipboard().setText(self.table_text())

    def _on_x_hovered(self, _x: float) -> None:
        return

    def _on_x_pinned(self, x: object) -> None:
        self._pinned_x = x if isinstance(x, float) else None

    def _on_series_hovered(self, name: object) -> None:
        index = species_index_from_name(str(name or ""))
        self._set_species_highlight(index)

    def _set_species_highlight(self, index: object) -> None:
        species = index if isinstance(index, int) else None
        self._hover_species = species
        name = None
        if species is not None and self._curve is not None:
            names = list(self._curve.series.keys())
            if 0 <= species < len(names):
                name = names[species]
        self._chart.highlight_series(name)
        for i in range(self._pictures_layout.count()):
            widget = self._pictures_layout.itemAt(i).widget()
            if isinstance(widget, _SpeciesPicture):
                if widget.index == species:
                    widget.setFrameStyle(int(QFrame.Shape.Box) | int(QFrame.Shadow.Raised))
                    widget.setLineWidth(2)
                else:
                    widget.setFrameStyle(int(QFrame.Shape.StyledPanel))
                    widget.setLineWidth(1)

    def _clear_species_highlight(self) -> None:
        if self._chart.hovered_series() is not None:
            return
        self._set_species_highlight(None)
