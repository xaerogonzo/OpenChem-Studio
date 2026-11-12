"""Compose a two-ion salt from project molecules. It computes a ratio, not a crystal.

Modeless, one instance. The dialog knows no chemistry: a host evaluates and
returns a ``SaltPreview``. Charge-valid is never shown as an isolable salt.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.salt_preview import (
    DISCLAIMER,
    MODE_ANALYZE,
    MODE_ENUMERATE,
    MODE_IONS,
    MODE_NEUTRALS,
    SaltPreview,
)
from openchem.ui import molecule_combo
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

_TOPIC = "salt-composition"

_MODE_HELP = HelpTooltip(
    text=(
        "What to ask of the structures. Analyze reading treats one drawing's "
        "disconnected ions as drawn and never rewrites their counts. Two neutrals "
        "transfers one proton when each side has a unique N/O/P/S ionization. "
        "Two ions uses the charges as given. Enumerate lists charge-balanced pairs "
        "from those states, at most 50, and does not rank them by pKa."
    ),
    tier=1, help_id="salt_composition.mode", topic=_TOPIC, help_anchor=_TOPIC,
)
_FIRST_HELP = HelpTooltip(
    text=(
        "The first molecule. In Analyze it is the drawing. In Two neutrals it is "
        "the base. In Two ions and Enumerate it is the cation side."
    ),
    tier=1, help_id="salt_composition.first", topic=_TOPIC, help_anchor=_TOPIC,
)
_SECOND_HELP = HelpTooltip(
    text=(
        "The second molecule. Unused in Analyze. In Two neutrals it is the acid. "
        "In Two ions and Enumerate it is the anion side. It never defaults to the "
        "same molecule as the first."
    ),
    tier=1, help_id="salt_composition.second", topic=_TOPIC, help_anchor=_TOPIC,
)

_MODE_LABELS = (
    (MODE_ANALYZE, "Analyze drawing"),
    (MODE_NEUTRALS, "Two neutrals (proton transfer)"),
    (MODE_IONS, "Two ions as drawn"),
    (MODE_ENUMERATE, "Enumerate pair"),
)


@dataclass
class SaltHost:
    """Lookups the dialog is handed. It imports no engine."""

    molecules: Callable[[], Sequence[tuple[str, str]]]
    selected_uuid: Callable[[], str | None]
    evaluate: Callable[[str, str | None, str | None], SaltPreview]


class SaltCompositionDialog(QDialog):
    def __init__(self, host: SaltHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Salt composition")
        self.setModal(False)
        self.resize(560, 420)
        self._host = host
        self._preview: SaltPreview | None = None

        self._mode = QComboBox(self)
        for code, label in _MODE_LABELS:
            self._mode.addItem(label, code)
        self._first = QComboBox(self)
        self._second = QComboBox(self)
        apply_help_tooltip(self._mode, _MODE_HELP)
        apply_help_tooltip(self._first, _FIRST_HELP)
        apply_help_tooltip(self._second, _SECOND_HELP)
        self._mode.currentIndexChanged.connect(self._on_form_changed)
        self._first.currentIndexChanged.connect(self._on_form_changed)
        self._second.currentIndexChanged.connect(self._on_form_changed)

        self._first_label = QLabel("Molecule:", self)
        self._second_label = QLabel("Second molecule:", self)
        form = QFormLayout()
        form.addRow("Ask:", self._mode)
        form.addRow(self._first_label, self._first)
        form.addRow(self._second_label, self._second)

        self._headline = QLabel("", self)
        self._headline.setWordWrap(True)
        self._body = QLabel("", self)
        self._body.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._headline)
        layout.addWidget(self._body, 1)
        layout.addWidget(buttons)

        self._populate_molecules(initial=True)
        self._sync_mode_rows()
        self._evaluate()

    def _needs_second(self) -> bool:
        return self._mode.currentData() != MODE_ANALYZE

    def _sync_mode_rows(self) -> None:
        mode = self._mode.currentData()
        labels = {
            MODE_ANALYZE: ("Molecule:", "Second molecule:"),
            MODE_NEUTRALS: ("Base:", "Acid:"),
            MODE_IONS: ("Cation:", "Anion:"),
            MODE_ENUMERATE: ("Cation side:", "Anion side:"),
        }
        first, second = labels.get(mode, ("Molecule:", "Second molecule:"))
        self._first_label.setText(first)
        self._second_label.setText(second)
        self._second.setEnabled(self._needs_second())
        self._second_label.setEnabled(self._needs_second())

    def _populate_molecules(self, *, initial: bool = False) -> None:
        molecules = list(self._host.molecules())
        entries = [(name or "(unnamed)", uuid) for name, uuid in molecules]
        uuids = [uuid for _, uuid in molecules]
        second_survives = self._second.currentData() in uuids
        molecule_combo.repopulate(self._first, entries)
        molecule_combo.repopulate(self._second, entries)
        if initial:
            selected = self._host.selected_uuid()
            if selected in uuids:
                self._first.blockSignals(True)
                self._first.setCurrentIndex(self._first.findData(selected))
                self._first.blockSignals(False)
        if initial or not second_survives:
            others = [uuid for uuid in uuids if uuid != self._first.currentData()]
            self._second.blockSignals(True)
            self._second.setCurrentIndex(self._second.findData(others[0]) if others else -1)
            self._second.blockSignals(False)

    def _on_form_changed(self, _index: int = 0) -> None:
        self._sync_mode_rows()
        self._evaluate()

    def refresh(self) -> None:
        self._populate_molecules()
        self._evaluate()

    def select_molecules(self, first_uuid: str | None, second_uuid: str | None) -> None:
        for combo, uuid in ((self._first, first_uuid), (self._second, second_uuid)):
            if uuid is not None:
                index = combo.findData(uuid)
                if index >= 0:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(index)
                    combo.blockSignals(False)
        self._evaluate()

    def set_mode(self, mode: str) -> None:
        index = self._mode.findData(mode)
        if index < 0:
            raise ValueError(f"{mode!r} is not one of the modes")
        self._mode.setCurrentIndex(index)

    def snapshot(self) -> dict[str, object]:
        preview = self._preview
        return {
            "mode": self._mode.currentData(),
            "first": self._first.currentData(),
            "second": self._second.currentData(),
            "headline": preview.headline if preview else "",
            "body": preview.body if preview else "",
            "charge_valid": preview.charge_valid if preview else None,
            "disclaimer": DISCLAIMER,
        }

    def _evaluate(self) -> None:
        first = self._first.currentData()
        second = self._second.currentData() if self._needs_second() else None
        if not first:
            preview = SaltPreview("Add a molecule to the project.", DISCLAIMER, None, self._mode.currentData() or MODE_ANALYZE, ())
        else:
            preview = self._host.evaluate(self._mode.currentData(), first, second)
        self._preview = preview
        self._headline.setText(preview.headline)
        self._body.setText(preview.body)
