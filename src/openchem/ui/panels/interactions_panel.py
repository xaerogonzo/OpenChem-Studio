"""How two of the project's molecules interact.

Named **Interactions** rather than "Lewis Adduct" on purpose. The
existing `interaction_analysis` calculator -- hydrogen bonding,
pi-stacking, metal contacts -- is the obvious second tab, and the panel
should not have to be renamed when it moves in. Only the Lewis tab is
built here.

Two molecules is the reason this exists at all. `CalculatorRegistry.compute`
receives exactly one molecule and no project handle, so the registry
calculator has to take its partner as a typed SMILES; that is fine for a
batch column and poor for actually working. Same split as
`AlignmentPanel`, for the same reason.

**The quantum lines fill themselves in.** Chemical hardness and the
frontier orbital energies come from any ORCA job, so this panel listens
for `QuantumChemistryResultReady` and remembers the numbers per molecule.
Run a job on the acid and one on the base, from the Quantum Chemistry
panel, and the two orbital-based lines of evidence appear here without
anything being wired between the panels by hand.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.engine import ChemistryEngine
from openchem.chem.lewis_adduct import predict
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import QuantumChemistryResultReady
from openchem.ui.molecule_combo import repopulate

_COLUMNS = ("Evidence", "Value", "Units", "Basis", "What it means")

#: descriptor_id suffix -> the keyword `predict` takes it as. delta-SCF is
#: listed first for hardness and wins, because Koopmans hardness inverts
#: ammonia against phosphine and a hard/soft match built on it can be
#: exactly backwards.
_HARDNESS_KEYS = ("orca.dscf_hardness", "orca.hardness")

_INTRO = (
    "Lewis acid/base pairing, on evidence rather than a score. Each line below "
    "answers a different question and they are not combined, because no accepted "
    "way of weighing them against each other exists. Run a quantum chemistry job "
    "on each molecule and the orbital-based lines fill in."
)


class InteractionsPanel(QWidget):
    """Pick an acid and a base from the project and see what can be said."""

    def __init__(
        self,
        engine: ChemistryEngine,
        event_bus: EventBus,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._event_bus = event_bus
        self._project: ProjectModel | None = None
        #: molecule uuid -> {descriptor_id: value}, filled by QM results.
        self._quantum: dict[str, dict[str, float]] = {}

        self._acid_combo = QComboBox(self)
        self._base_combo = QComboBox(self)
        self._predict_button = QPushButton("Predict", self)
        self._predict_button.clicked.connect(self._on_predict_clicked)

        self._status_label = QLabel("", self)
        self._status_label.setWordWrap(True)

        self._table = QTableWidget(0, len(_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setWordWrap(True)

        self._notes = QTextEdit(self)
        self._notes.setReadOnly(True)

        intro = QLabel(_INTRO, self)
        intro.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Lewis acid:", self._acid_combo)
        form.addRow("Lewis base:", self._base_combo)

        pair_box = QGroupBox("Pair", self)
        pair_layout = QVBoxLayout(pair_box)
        pair_layout.addLayout(form)
        pair_layout.addWidget(intro)
        buttons = QHBoxLayout()
        buttons.addWidget(self._predict_button)
        buttons.addStretch(1)
        pair_layout.addLayout(buttons)
        pair_layout.addWidget(self._status_label)

        lewis_tab = QWidget(self)
        lewis_layout = QVBoxLayout(lewis_tab)
        lewis_layout.addWidget(pair_box)
        lewis_layout.addWidget(self._table, 1)
        lewis_layout.addWidget(self._notes, 1)

        self._tabs = QTabWidget(self)
        self._tabs.addTab(lewis_tab, "Lewis Adduct")

        layout = QVBoxLayout(self)
        layout.addWidget(self._tabs)

        event_bus.subscribe(QuantumChemistryResultReady, self._on_quantum_result)

    # --- project wiring ---------------------------------------------------

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        molecules = list(project.molecules) if project is not None else []
        entries = [(m.display_name, m.uuid) for m in molecules]
        # Neither combo follows the tree selection. Both are deliberate
        # picks defining one comparison, and reshuffling either underneath
        # the user because they clicked something else in the tree would
        # silently change what the table on screen describes.
        repopulate(self._acid_combo, entries)
        repopulate(self._base_combo, entries)

    def _on_quantum_result(self, event: QuantumChemistryResultReady) -> None:
        """Remember every quantum number, keyed by molecule.

        Stored rather than requested, because a quantum job is minutes of
        work that has usually already been done by the time somebody opens
        this panel -- and the descriptor service offers no synchronous
        lookup to ask after the fact.
        """
        values = self._quantum.setdefault(event.molecule_uuid, {})
        for descriptor in event.descriptors:
            values[descriptor.descriptor_id] = descriptor.value

    # --- prediction --------------------------------------------------------

    def _molecule_for(self, combo: QComboBox):
        from PySide6.QtCore import Qt

        uuid = combo.currentData(Qt.ItemDataRole.UserRole)
        if self._project is None or uuid is None:
            return None, None
        model = next((m for m in self._project.molecules if m.uuid == uuid), None)
        if model is None:
            return None, None
        try:
            return model, self._engine.mol_from_model(model)
        except Exception:  # noqa: BLE001 - an unreadable structure is a status, not a crash
            return model, None

    def _quantum_value(self, uuid: str, keys: tuple[str, ...]) -> float | None:
        values = self._quantum.get(uuid, {})
        return next((values[key] for key in keys if key in values), None)

    def _on_predict_clicked(self) -> None:
        acid_model, acid = self._molecule_for(self._acid_combo)
        base_model, base = self._molecule_for(self._base_combo)
        if acid is None or base is None:
            self._show_status("Pick a Lewis acid and a Lewis base from the project.")
            return
        if acid_model.uuid == base_model.uuid:
            # Self-association is real chemistry -- water, carboxylic acids --
            # but it is not what this panel computes, and silently reporting
            # a molecule's parameters against themselves would look like an
            # answer.
            self._show_status(
                "The acid and the base are the same molecule. Pick two, or add a "
                "second copy if you really mean self-association."
            )
            return

        result = predict(
            acid,
            base,
            acid_uuid=acid_model.uuid,
            base_uuid=base_model.uuid,
            acid_label=acid_model.display_name,
            base_label=base_model.display_name,
            acid_lumo_ev=self._quantum_value(acid_model.uuid, ("orca.lumo_energy",)),
            base_homo_ev=self._quantum_value(base_model.uuid, ("orca.homo_energy",)),
            acid_hardness=self._quantum_value(acid_model.uuid, _HARDNESS_KEYS),
            base_hardness=self._quantum_value(base_model.uuid, _HARDNESS_KEYS),
        )

        if result.refused:
            self._table.setRowCount(0)
            self._show_status(f"{result.acid_label} + {result.base_label}: {result.reason}")
            self._notes.setPlainText("")
            return

        self._show_status(f"{result.acid_label} + {result.base_label}. {result.summary}")
        self._fill_table(result)
        self._fill_notes(result)

    def _fill_table(self, result) -> None:
        self._table.setRowCount(len(result.evidence))
        for row, item in enumerate(result.evidence):
            # An unavailable line stays VISIBLE, with its reason in the
            # last column. Dropping the row would read as "this does not
            # apply here" when it means "run a quantum job".
            cells = (
                item.label,
                "--" if item.value is None else f"{item.value:.2f}",
                item.units,
                item.basis.value,
                item.note,
            )
            for column, text in enumerate(cells):
                self._table.setItem(row, column, QTableWidgetItem(text))
        self._table.resizeRowsToContents()

    def _fill_notes(self, result) -> None:
        lines = [f"Assumption: {text}" for text in result.assumptions]
        lines.extend(f"Limitation: {text}" for text in result.limitations)
        self._notes.setPlainText("\n\n".join(lines))

    def _show_status(self, message: str) -> None:
        self._status_label.setText(message)
