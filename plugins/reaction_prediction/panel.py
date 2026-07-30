from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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
from openchem.plugins.async_task import run_async
from openchem.plugins.context import PluginContext

from .molecule_cache import SelectedMoleculeCache
from .providers import (
    ReactionPredictionError,
    ReactionPredictor,
    ReactionPrediction,
    RemoteReactionAPIProvider,
)

_COLUMNS = ("Product SMILES", "Source", "Confidence")


def _molecule_from_smiles(display_name: str, smiles: str) -> MoleculeModel:
    """Mirrors `database_search.panel._molecule_from_smiles` — same small,
    self-contained SMILES-to-MoleculeModel conversion each plugin needing
    it does directly, rather than a shared helper module extracted before
    a second real caller's shape is visible (see the Phase 6 plan's
    6.1->6.3 checkpoint note)."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Could not parse SMILES: {smiles!r}")
    model = MoleculeModel(display_name=display_name, molblock=Chem.MolToMolBlock(mol))
    model.canonical_smiles = Chem.MolToSmiles(mol)
    inchi = Chem.MolToInchi(mol)
    model.inchi = inchi or None
    model.inchikey = Chem.InchiToInchiKey(inchi) if inchi else None
    return model


class _RemoteAPISettingsDialog(QDialog):
    def __init__(self, context: PluginContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure Remote Reaction API")
        self._context = context

        self._base_url_edit = QLineEdit(self)
        self._base_url_edit.setPlaceholderText("https://rxn.res.ibm.com/...")
        self._base_url_edit.setText(context.settings.get("remote_api_base_url", ""))

        self._api_key_edit = QLineEdit(self)
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setText(context.secrets.get("remote_api_key") or "")

        form = QFormLayout()
        form.addRow("Base URL:", self._base_url_edit)
        form.addRow("API key:", self._api_key_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def accept(self) -> None:
        self._context.settings.set("remote_api_base_url", self._base_url_edit.text())
        self._context.secrets.set("remote_api_key", self._api_key_edit.text())
        super().accept()


class ReactionPredictionPanel(QWidget):
    def __init__(
        self,
        context: PluginContext,
        providers: dict[str, ReactionPredictor],
        cache: SelectedMoleculeCache,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._context = context
        self._providers = providers
        self._cache = cache
        self._predictions: list[ReactionPrediction] = []

        self._reactant1_edit = QLineEdit(self)
        self._reactant1_edit.setPlaceholderText("Reactant 1 SMILES")
        self._reactant2_edit = QLineEdit(self)
        self._reactant2_edit.setPlaceholderText("Reactant 2 SMILES")

        self._method_combo = QComboBox(self)
        self._method_combo.addItems(list(providers.keys()))
        self._method_combo.currentTextChanged.connect(self._on_method_changed)

        self._configure_button = QPushButton("Configure...", self)
        self._configure_button.clicked.connect(self._on_configure_clicked)
        self._configure_button.setVisible(self._method_combo.currentText() == "Remote API")

        self._predict_button = QPushButton("Predict", self)
        self._predict_button.clicked.connect(self._on_predict_clicked)

        self._status_label = QLabel("", self)

        self._table = QTableWidget(0, len(_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        self._import_button = QPushButton("Add as new molecule", self)
        self._import_button.setEnabled(False)
        self._import_button.clicked.connect(self._on_import_clicked)
        self._table.itemSelectionChanged.connect(
            lambda: self._import_button.setEnabled(bool(self._table.selectedItems()))
        )

        reactants_bar = QHBoxLayout()
        reactants_bar.addWidget(self._reactant1_edit)
        reactants_bar.addWidget(self._reactant2_edit)

        method_bar = QHBoxLayout()
        method_bar.addWidget(QLabel("Method:"))
        method_bar.addWidget(self._method_combo)
        method_bar.addWidget(self._configure_button)
        method_bar.addWidget(self._predict_button)

        layout = QVBoxLayout(self)
        layout.addLayout(reactants_bar)
        layout.addLayout(method_bar)
        layout.addWidget(self._status_label)
        layout.addWidget(self._table)
        layout.addWidget(self._import_button)

    def focus_and_prefill_from_selection(self) -> None:
        if self._cache.has_molecule():
            self._reactant1_edit.setText(self._cache.canonical_smiles() or "")
        self._reactant1_edit.setFocus()

    def _on_method_changed(self, method: str) -> None:
        self._configure_button.setVisible(method == "Remote API")

    def _on_configure_clicked(self) -> None:
        dialog = _RemoteAPISettingsDialog(self._context, self)
        dialog.exec()

    def _on_predict_clicked(self) -> None:
        reactants = [
            text.strip()
            for text in (self._reactant1_edit.text(), self._reactant2_edit.text())
            if text.strip()
        ]
        if not reactants:
            return

        provider = self._providers[self._method_combo.currentText()]
        if isinstance(provider, RemoteReactionAPIProvider):
            provider.base_url = self._context.settings.get("remote_api_base_url", "")
            provider.api_key = self._context.secrets.get("remote_api_key") or ""

        self._predict_button.setEnabled(False)
        self._status_label.setText("Predicting...")
        run_async(
            lambda: provider.predict(reactants),
            ReactionPredictionError,
            self._on_predictions,
            self._on_error,
        )

    def _on_predictions(self, predictions: list[ReactionPrediction]) -> None:
        self._predict_button.setEnabled(True)
        self._predictions = predictions
        self._status_label.setText(f"{len(predictions)} prediction(s)")
        self._table.setRowCount(len(predictions))
        for row, prediction in enumerate(predictions):
            confidence_text = (
                f"{prediction.confidence:.2f}" if prediction.confidence is not None else ""
            )
            values = (prediction.product_smiles, prediction.source_label, confidence_text)
            for col, value in enumerate(values):
                self._table.setItem(row, col, QTableWidgetItem(value))

    def _on_error(self, message: str) -> None:
        self._predict_button.setEnabled(True)
        self._status_label.setText(f"Error: {message}")
        self._predictions = []
        self._table.setRowCount(0)

    def _on_import_clicked(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._predictions):
            return
        prediction = self._predictions[row]
        try:
            molecule = _molecule_from_smiles("Predicted product", prediction.product_smiles)
        except ValueError as exc:
            self._status_label.setText(f"Error: {exc}")
            return
        self._context.molecules.add(molecule)
