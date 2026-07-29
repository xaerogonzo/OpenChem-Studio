from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from rdkit import Chem

from openchem.domain.molecule import MoleculeModel
from openchem.plugins.context import PluginContext

from .providers import DatabaseSearchError, DatabaseSearchProvider, SearchResult

_COLUMNS = ("Source", "ID", "Name", "Formula", "MW", "SMILES")


def _molecule_from_smiles(display_name: str, smiles: str) -> MoleculeModel:
    """Builds a canonicalized MoleculeModel directly from a SMILES string.

    Plugins are expected to do real chemistry alongside `chem/` (see
    `plugins/interfaces.py`'s module docstring) — `PluginContext` doesn't
    expose `ChemistryEngine` itself (no other plugin has needed it yet), so
    this mirrors `ChemistryEngine.set_structure_from_smiles`/`.canonicalize`
    directly rather than plumbing the engine through the plugin API for one
    caller.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Could not parse SMILES: {smiles!r}")
    model = MoleculeModel(display_name=display_name, molblock=Chem.MolToMolBlock(mol))
    model.canonical_smiles = Chem.MolToSmiles(mol)
    inchi = Chem.MolToInchi(mol)
    model.inchi = inchi or None
    model.inchikey = Chem.InchiToInchiKey(inchi) if inchi else None
    return model


class _SearchSignals(QObject):
    finished = Signal(list)  # list[SearchResult]
    failed = Signal(str)


class _SearchTask(QRunnable):
    """Runs one provider.search() call off the GUI thread — same pattern as
    ai_assistant's _CompletionTask."""

    def __init__(self, provider: DatabaseSearchProvider, query: str, query_type: str) -> None:
        super().__init__()
        self._provider = provider
        self._query = query
        self._query_type = query_type
        self.signals = _SearchSignals()

    def run(self) -> None:
        try:
            results = self._provider.search(self._query, self._query_type)
        except DatabaseSearchError as exc:
            self.signals.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - never let an unexpected error escape the pool
            self.signals.failed.emit(f"Unexpected error: {exc}")
        else:
            self.signals.finished.emit(results)


class DatabaseSearchPanel(QWidget):
    """Search UI: query + query-type + source selector, a results table,
    and an "Import as new molecule" action per row.
    """

    def __init__(
        self,
        context: PluginContext,
        providers: dict[str, DatabaseSearchProvider],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._context = context
        self._providers = providers
        self._results: list[SearchResult] = []

        self._query_edit = QLineEdit(self)
        self._query_edit.setPlaceholderText("Search by name, SMILES, or InChIKey...")
        self._query_edit.returnPressed.connect(self._on_search_clicked)

        self._query_type_combo = QComboBox(self)
        self._query_type_combo.addItems(["name", "smiles", "inchikey"])

        self._source_combo = QComboBox(self)
        self._source_combo.addItems(list(providers.keys()))

        self._search_button = QPushButton("Search", self)
        self._search_button.clicked.connect(self._on_search_clicked)

        self._status_label = QLabel("", self)

        self._table = QTableWidget(0, len(_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        self._import_button = QPushButton("Import as new molecule", self)
        self._import_button.setEnabled(False)
        self._import_button.clicked.connect(self._on_import_clicked)
        self._table.itemSelectionChanged.connect(
            lambda: self._import_button.setEnabled(bool(self._table.selectedItems()))
        )

        top_bar = QHBoxLayout()
        top_bar.addWidget(self._query_edit)
        top_bar.addWidget(self._query_type_combo)
        top_bar.addWidget(QLabel("in:"))
        top_bar.addWidget(self._source_combo)
        top_bar.addWidget(self._search_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top_bar)
        layout.addWidget(self._status_label)
        layout.addWidget(self._table)
        layout.addWidget(self._import_button)

    def _on_search_clicked(self) -> None:
        query = self._query_edit.text().strip()
        if not query:
            return
        provider = self._providers[self._source_combo.currentText()]
        query_type = self._query_type_combo.currentText()

        self._search_button.setEnabled(False)
        self._status_label.setText("Searching...")
        task = _SearchTask(provider, query, query_type)
        task.signals.finished.connect(self._on_results)
        task.signals.failed.connect(self._on_error)
        QThreadPool.globalInstance().start(task)

    def _on_results(self, results: list[SearchResult]) -> None:
        self._search_button.setEnabled(True)
        self._results = results
        self._status_label.setText(f"{len(results)} result(s)")
        self._table.setRowCount(len(results))
        for row, result in enumerate(results):
            values = (
                result.source,
                result.external_id,
                result.name,
                result.molecular_formula or "",
                f"{result.molecular_weight:.2f}" if result.molecular_weight is not None else "",
                result.smiles,
            )
            for col, value in enumerate(values):
                self._table.setItem(row, col, QTableWidgetItem(value))

    def _on_error(self, message: str) -> None:
        self._search_button.setEnabled(True)
        self._status_label.setText(f"Error: {message}")
        self._results = []
        self._table.setRowCount(0)

    def _on_import_clicked(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._results):
            return
        result = self._results[row]
        try:
            molecule = _molecule_from_smiles(result.name, result.smiles)
        except ValueError as exc:
            self._status_label.setText(f"Error: {exc}")
            return
        self._context.molecules.add(molecule)
