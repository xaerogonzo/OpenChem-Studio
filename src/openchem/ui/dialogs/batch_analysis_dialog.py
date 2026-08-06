"""The four things worth doing to a finished batch table.

Correlation, chemical space, clustering and distributions -- one dialog
with a tab each, because they all consume the same `BatchTable` and a
user moves between them while asking one question ("what drives this
column?").

THE CORRELATION TAB IS THE IMPORTANT ONE, and not because scatter plots
are hard. It is the in-app form of the check that overturned this
project's own hERG conclusion: the model appeared to separate blockers
from non-blockers and turned out to be tracking molecular size at
r = +0.98. Any predicted column can fail that way, and the defence is
being able to ask "what else does this track?" in two clicks. The
"Correlate against everything" button exists for exactly that -- it ranks
every other numeric column against the selected one, so the confound is
found rather than looked for.

Only numeric columns with at least two values are offered anywhere here.
A column that is selectable and yields an empty plot reads as a broken
tool rather than as missing data.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.analytics import correlate, describe, pca
from openchem.chem.comparison import atom_correspondence, build_comparison, deltas_against
from openchem.domain.batch import BatchColumn, BatchTable
from openchem.ui.widgets.histogram_widget import HistogramWidget
from openchem.ui.widgets.scatter_plot_widget import ScatterPlotWidget, ScatterPoint
from openchem.ui.widgets.sortable_item import SortableItem as _SortableItem


class BatchAnalysisDialog(QDialog):
    """Correlation / chemical space / clustering / statistics over one table."""

    def __init__(self, table: BatchTable, chemistry_engine, project=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._table = table
        self._engine = chemistry_engine
        self._project = project
        self.setWindowTitle("Analyse batch results")
        self.resize(880, 680)

        layout = QVBoxLayout(self)
        self._numeric = table.numeric_columns()
        if not self._numeric:
            layout.addWidget(
                QLabel(
                    "No numeric columns to analyse.\n\n"
                    "Every column in this table is either text (a formula, a name) or "
                    "has fewer than two values across the project — a correlation, a "
                    "projection and a histogram all need at least two numbers to mean "
                    "anything. Run more molecules, or select properties that produce "
                    "numbers."
                )
            )
            return

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._build_correlation_tab(), "Correlation")
        self._tabs.addTab(self._build_space_tab(), "Chemical space")
        self._tabs.addTab(self._build_cluster_tab(), "Clustering")
        self._tabs.addTab(self._build_statistics_tab(), "Distributions")
        # Only when there IS per-atom data for two molecules. An empty
        # fifth tab advertising a comparison that cannot be made is worse
        # than no tab -- the same judgement the "no numeric columns"
        # message above makes.
        self._has_atom_tab = bool(table.per_atom_calculators()) and len(table.row_uuids) >= 2
        if self._has_atom_tab:
            self._tabs.addTab(self._build_atoms_tab(), "Per-atom")
        layout.addWidget(self._tabs)

        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)

        self._update_correlation()
        self._update_space()
        self._update_statistics()
        if self._has_atom_tab:
            self._update_atoms()

    # -- correlation ------------------------------------------------------

    def _build_correlation_tab(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)

        controls = QHBoxLayout()
        self._x_combo = _column_combo(self._numeric, widget)
        self._y_combo = _column_combo(self._numeric, widget)
        if len(self._numeric) > 1:
            self._y_combo.setCurrentIndex(1)
        self._x_combo.currentIndexChanged.connect(self._update_correlation)
        self._y_combo.currentIndexChanged.connect(self._update_correlation)
        controls.addWidget(QLabel("X:"))
        controls.addWidget(self._x_combo, stretch=1)
        controls.addWidget(QLabel("Y:"))
        controls.addWidget(self._y_combo, stretch=1)
        rank_button = QPushButton("Correlate Y against everything", widget)
        rank_button.setToolTip(
            "Rank every other numeric column by how strongly it tracks Y.\n"
            "This is the confound check: a predicted property whose top "
            "correlate is molecular weight is measuring size."
        )
        rank_button.clicked.connect(self._rank_against_everything)
        controls.addWidget(rank_button)
        layout.addLayout(controls)

        self._scatter = ScatterPlotWidget(parent=widget)
        layout.addWidget(self._scatter, stretch=1)

        self._ranking = QTableWidget(0, 3, widget)
        self._ranking.setHorizontalHeaderLabels(["Column", "Pearson r", "n"])
        self._ranking.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._ranking.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._ranking.setMaximumHeight(190)
        self._ranking.setVisible(False)
        layout.addWidget(self._ranking)
        return widget

    def _update_correlation(self) -> None:
        x_column = self._selected(self._x_combo)
        y_column = self._selected(self._y_combo)
        if x_column is None or y_column is None:
            return
        xs, ys, uuids = self._table.paired_values(x_column.column_id, y_column.column_id)
        if len(xs) < 2:
            self._scatter.set_points([], x_column.header, y_column.header)
            self._scatter.set_empty_message(
                f"Only {len(xs)} molecule(s) have both of these values."
            )
            return
        result = correlate(xs, ys)
        self._scatter.set_points(
            [
                ScatterPoint(x=x, y=y, label=self._table.row_labels.get(uuid, uuid))
                for x, y, uuid in zip(xs, ys, uuids)
            ],
            x_column.header,
            y_column.header,
            result.describe(),
            fit=(result.slope, result.intercept),
        )

    def _rank_against_everything(self) -> None:
        target = self._selected(self._y_combo)
        if target is None:
            return
        rows = []
        for column in self._numeric:
            if column.column_id == target.column_id:
                continue
            xs, ys, _uuids = self._table.paired_values(column.column_id, target.column_id)
            if len(xs) < 3:
                continue
            rows.append((column, correlate(xs, ys)))
        rows.sort(key=lambda pair: -abs(pair[1].pearson_r))
        self._ranking.setRowCount(len(rows))
        for index, (column, result) in enumerate(rows):
            self._ranking.setItem(index, 0, QTableWidgetItem(column.header))
            self._ranking.setItem(index, 1, QTableWidgetItem(f"{result.pearson_r:+.3f}"))
            self._ranking.setItem(index, 2, QTableWidgetItem(str(result.n)))
        self._ranking.setVisible(True)

    # -- chemical space ---------------------------------------------------

    def _build_space_tab(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.addWidget(
            QLabel(
                "Principal components of every numeric column, standardised.\n"
                "Deterministic — the same project always gives the same picture, "
                "which is why this and not UMAP or t-SNE."
            )
        )
        self._space_scatter = ScatterPlotWidget(parent=widget)
        layout.addWidget(self._space_scatter, stretch=1)
        self._space_note = QLabel("", widget)
        self._space_note.setWordWrap(True)
        layout.addWidget(self._space_note)
        return widget

    def _update_space(self, groups: dict[str, int] | None = None) -> None:
        column_ids = [column.column_id for column in self._numeric]
        matrix, uuids = self._table.matrix(column_ids)
        dropped_rows = len(self._table.row_uuids) - len(uuids)
        if len(matrix) < 3:
            self._space_scatter.set_points([], "PC1", "PC2")
            self._space_scatter.set_empty_message(
                f"Only {len(matrix)} molecules have a value in every numeric column.\n"
                "A projection needs at least three."
            )
            self._space_note.setText(
                "A projection uses complete rows only — one failed column removes a "
                "molecule from it entirely. Deselect the columns that failed and run again."
            )
            return
        result = pca(matrix, [column.header for column in self._numeric], uuids, components=2)
        points = [
            ScatterPoint(
                x=score[0],
                y=score[1] if len(score) > 1 else 0.0,
                label=self._table.row_labels.get(uuid, uuid),
                group=None if groups is None else groups.get(uuid),
            )
            for score, uuid in zip(result.scores, result.row_uuids)
        ]
        self._space_scatter.set_points(points, "PC1", "PC2", result.describe())
        notes = [
            "PC1 is dominated by: "
            + ", ".join(f"{label} ({value:+.2f})" for label, value in result.top_loadings(0, 4)),
            "PC2 is dominated by: "
            + ", ".join(f"{label} ({value:+.2f})" for label, value in result.top_loadings(1, 4)),
        ]
        if result.dropped_columns:
            notes.append(
                f"{len(result.dropped_columns)} column(s) had the same value for every "
                f"molecule and carry no information: {', '.join(result.dropped_columns[:6])}"
            )
        if dropped_rows:
            notes.append(
                f"{dropped_rows} molecule(s) excluded — they are missing a value in at "
                "least one column."
            )
        self._space_note.setText("\n".join(notes))

    # -- clustering -------------------------------------------------------

    def _build_cluster_tab(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        form = QFormLayout()
        self._threshold = QDoubleSpinBox(widget)
        self._threshold.setRange(0.05, 0.99)
        self._threshold.setSingleStep(0.05)
        self._threshold.setValue(0.65)
        self._threshold.setToolTip(
            "Tanimoto similarity at or above which two molecules count as neighbours.\n"
            "Higher is stricter, so a higher threshold gives MORE, smaller clusters."
        )
        form.addRow("Similarity threshold", self._threshold)
        layout.addLayout(form)

        run = QPushButton("Cluster", widget)
        run.clicked.connect(self._run_clustering)
        layout.addWidget(run)

        self._cluster_note = QLabel(
            "Butina over Morgan fingerprints, computed from the structures in the "
            "project — not from the table columns. Cluster membership then colours "
            "the Chemical space tab.",
            widget,
        )
        self._cluster_note.setWordWrap(True)
        layout.addWidget(self._cluster_note)

        self._cluster_table = QTableWidget(0, 2, widget)
        self._cluster_table.setHorizontalHeaderLabels(["Molecule", "Cluster"])
        self._cluster_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._cluster_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._cluster_table, stretch=1)
        return widget

    def _run_clustering(self) -> None:
        """Cluster the project's structures, then recolour the projection.

        The structures come from the project rather than from the table
        because a fingerprint is not a column -- and this is the one place
        the analytics need the molecules themselves rather than the numbers
        computed from them.
        """
        from openchem.chem.clustering import cluster_molecules

        if self._project is None:
            self._cluster_note.setText("No project available to read structures from.")
            return
        mols = {}
        for molecule in self._project.molecules:
            if molecule.uuid not in self._table.row_labels:
                continue
            try:
                mols[molecule.uuid] = self._engine.mol_from_model(molecule)
            except Exception:  # noqa: BLE001 - one bad structure must not stop the clustering
                mols[molecule.uuid] = None
        assignment = cluster_molecules(mols, threshold=self._threshold.value())
        note = assignment.describe()
        if assignment.skipped:
            note += f"  ({len(assignment.skipped)} molecules had no usable structure)"
        self._cluster_note.setText(note)
        self._cluster_table.setRowCount(len(assignment.cluster_of))
        for row, (uuid, index) in enumerate(
            sorted(assignment.cluster_of.items(), key=lambda pair: pair[1])
        ):
            self._cluster_table.setItem(
                row, 0, QTableWidgetItem(self._table.row_labels.get(uuid, uuid))
            )
            self._cluster_table.setItem(row, 1, QTableWidgetItem(str(index)))
        # 1-based clusters, 0-based palette.
        self._update_space({uuid: index - 1 for uuid, index in assignment.cluster_of.items()})

    # -- statistics -------------------------------------------------------

    def _build_statistics_tab(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        self._stat_combo = _column_combo(self._numeric, widget)
        self._stat_combo.currentIndexChanged.connect(self._update_statistics)
        row = QHBoxLayout()
        row.addWidget(QLabel("Column:"))
        row.addWidget(self._stat_combo, stretch=1)
        layout.addLayout(row)
        self._histogram = HistogramWidget(parent=widget)
        layout.addWidget(self._histogram, stretch=1)
        self._stat_note = QLabel("", widget)
        self._stat_note.setWordWrap(True)
        self._stat_note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._stat_note)
        return widget

    def _update_statistics(self) -> None:
        column = self._selected(self._stat_combo)
        if column is None:
            return
        values = self._table.values(column.column_id)
        distribution = describe(values)
        self._histogram.set_distribution(distribution, column.header)
        missing = len(self._table.row_uuids) - distribution.n
        note = (
            f"n = {distribution.n}   mean {distribution.mean:.5g}   "
            f"sd {distribution.std_dev:.5g}   min {distribution.minimum:.5g}   "
            f"Q1 {distribution.q1:.5g}   median {distribution.median:.5g}   "
            f"Q3 {distribution.q3:.5g}   max {distribution.maximum:.5g}"
        )
        if missing:
            note += f"\n{missing} molecule(s) have no value in this column."
        self._stat_note.setText(note)

    # -- per-atom comparison ----------------------------------------------

    def _build_atoms_tab(self) -> QWidget:
        """Two molecules, one per-atom property, atom by atom.

        Separate from Correlation rather than folded into it because the
        question is different in kind: correlation asks which COLUMNS move
        together across the project, this asks which ATOMS differ between
        two structures. Sharing a tab would mean one of them borrowing the
        other's controls.
        """
        widget = QWidget(self)
        layout = QVBoxLayout(widget)

        controls = QHBoxLayout()
        self._atom_property = QComboBox(widget)
        for calculator_id in self._table.per_atom_calculators():
            self._atom_property.addItem(self._per_atom_label(calculator_id), calculator_id)
        self._atom_reference = _row_combo(self._table, widget)
        self._atom_other = _row_combo(self._table, widget)
        if self._atom_other.count() > 1:
            self._atom_other.setCurrentIndex(1)
        for combo in (self._atom_property, self._atom_reference, self._atom_other):
            combo.currentIndexChanged.connect(self._update_atoms)
        controls.addWidget(QLabel("Property:"))
        controls.addWidget(self._atom_property, stretch=1)
        controls.addWidget(QLabel("Reference:"))
        controls.addWidget(self._atom_reference, stretch=1)
        controls.addWidget(QLabel("Against:"))
        controls.addWidget(self._atom_other, stretch=1)
        layout.addLayout(controls)

        self._atom_table = QTableWidget(0, 5, widget)
        self._atom_table.setHorizontalHeaderLabels(
            ["Atom", "Element", "Reference", "Against", "Difference"]
        )
        self._atom_table.setSortingEnabled(True)
        self._atom_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._atom_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._atom_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self._atom_table, stretch=1)

        self._atom_note = QLabel("", widget)
        self._atom_note.setWordWrap(True)
        self._atom_note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._atom_note)
        return widget

    def _per_atom_label(self, calculator_id: str) -> str:
        for column in self._table.columns:
            if column.source_id == calculator_id:
                return column.label
        return calculator_id

    def _update_atoms(self) -> None:
        self._atom_table.setRowCount(0)
        calculator_id = self._atom_property.currentData()
        reference_uuid = self._atom_reference.currentData()
        other_uuid = self._atom_other.currentData()
        if not calculator_id or not reference_uuid or not other_uuid:
            self._atom_note.setText("Choose a property and two molecules.")
            return
        if reference_uuid == other_uuid:
            self._atom_note.setText("Choose two different molecules.")
            return

        results = {
            uuid: self._table.per_atom_for(uuid, calculator_id)
            for uuid in (reference_uuid, other_uuid)
        }
        comparison = build_comparison(
            results,
            {uuid: self._table.row_labels.get(uuid, uuid) for uuid in results},
            calculator_id=calculator_id,
            calculator_name=self._per_atom_label(calculator_id),
            order=[reference_uuid, other_uuid],
        )
        if comparison.categorical:
            # Return here rather than falling through. `deltas_against`
            # refuses a categorical dataset anyway, so continuing would
            # compute an MCS nothing uses and then overwrite this
            # explanation with a less specific one.
            self._atom_note.setText(
                "\n".join(comparison.limitations)
                + "\nNo differences are shown, because subtracting two "
                "category identifiers gives a number that means nothing."
            )
            return

        reference_mol = self._mol(reference_uuid)
        other_mol = self._mol(other_uuid)
        if reference_mol is None or other_mol is None:
            self._atom_note.setText(
                "The structures for these molecules are not available in this "
                "dialog, so their atoms cannot be matched up."
            )
            return

        mapping = atom_correspondence(reference_mol, other_mol)
        if not mapping:
            self._atom_note.setText(
                "These two molecules share no common substructure, so there are "
                "no corresponding atoms to compare. A difference here would be "
                "between atoms that are not the same site."
            )
            return

        deltas = deltas_against(
            comparison, reference_uuid, other_uuid, mapping, reference_mol=reference_mol
        )
        if not deltas and not comparison.categorical:
            self._atom_note.setText(
                "The two molecules correspond, but this property has no values "
                "for the atoms they share."
            )
            return

        self._atom_table.setSortingEnabled(False)
        self._atom_table.setRowCount(len(deltas))
        for row, delta in enumerate(deltas):
            self._atom_table.setItem(row, 0, _SortableItem(str(delta.reference_index), float(delta.reference_index)))
            self._atom_table.setItem(row, 1, QTableWidgetItem(delta.element))
            self._atom_table.setItem(row, 2, _SortableItem(f"{delta.reference_value:.4g}", delta.reference_value))
            self._atom_table.setItem(row, 3, _SortableItem(f"{delta.other_value:.4g}", delta.other_value))
            self._atom_table.setItem(row, 4, _SortableItem(f"{delta.delta:+.4g}", delta.delta))
        self._atom_table.setSortingEnabled(True)

        if not comparison.categorical:
            unmatched = reference_mol.GetNumAtoms() - len(deltas)
            note = (
                f"{len(deltas)} of {reference_mol.GetNumAtoms()} atoms in the "
                f"reference have a counterpart with a value."
            )
            if unmatched:
                # Saying so matters: the atoms that DIFFER are exactly the
                # ones with no counterpart, and a table that silently omits
                # them reads as "these molecules are nearly identical".
                note += (
                    f" The other {unmatched} are absent from the comparison "
                    "because they have no matching atom -- those are where the "
                    "two structures genuinely differ."
                )
            self._atom_note.setText(note)

    def _mol(self, molecule_uuid: str):
        """The RDKit molecule for a row, or None.

        Goes through the project because a `BatchTable` holds results, not
        structures -- and rebuilding one from a name would be guessing.
        """
        if self._project is None:
            return None
        for molecule in getattr(self._project, "molecules", []):
            if molecule.uuid == molecule_uuid:
                try:
                    return self._engine.mol_from_model(molecule)
                except Exception:  # noqa: BLE001 - an unparseable row is "no structure"
                    return None
        return None

    # -- shared -----------------------------------------------------------

    def _selected(self, combo: QComboBox) -> BatchColumn | None:
        column_id = combo.currentData()
        return self._table.column(column_id) if column_id else None


def _column_combo(columns: list[BatchColumn], parent: QWidget) -> QComboBox:
    combo = QComboBox(parent)
    for column in columns:
        combo.addItem(column.header, column.column_id)
    return combo


def _row_combo(table: BatchTable, parent: QWidget) -> QComboBox:
    combo = QComboBox(parent)
    for molecule_uuid in table.row_uuids:
        combo.addItem(table.row_labels.get(molecule_uuid, molecule_uuid), molecule_uuid)
    return combo
