"""Choose which molecules a run covers.

The same ticked list the batch panel keeps under its "Molecules" heading, as a
dialog: Properties has no room for a list of molecules, and a choice made once
per run does not need one on screen.

**EVERYTHING STARTS TICKED WHEN NOTHING WAS CHOSEN BEFORE**, and a previous
choice survives by uuid, so renaming a molecule keeps its tick and deleting one
drops it. "No molecules" is refused by the dialog rather than accepted and then
quietly run as the whole project -- the defect `batch_service` guards against
by reading an empty list as "everything given".
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MoleculeScopeDialog(QDialog):
    def __init__(self, molecules, chosen: set[str] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose molecules")
        molecules = list(molecules)
        survivors = (chosen or set()) & {m.uuid for m in molecules}
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Run the ticked calculators on these molecules:"))
        self._list = QListWidget(self)
        for molecule in molecules:
            item = QListWidgetItem(molecule.display_name, self._list)
            item.setData(Qt.ItemDataRole.UserRole, molecule.uuid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if not survivors or molecule.uuid in survivors
                else Qt.CheckState.Unchecked
            )
        self._list.itemChanged.connect(self._refresh)
        layout.addWidget(self._list)

        row = QHBoxLayout()
        all_button = QPushButton("All", self)
        all_button.clicked.connect(self._tick_all)
        none_button = QPushButton("None", self)
        none_button.clicked.connect(self._untick_all)
        row.addWidget(all_button)
        row.addWidget(none_button)
        row.addStretch(1)
        layout.addLayout(row)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)
        self._refresh()

    # Bound methods, never lambdas closing over `self`: PySide6 holds a plain
    # callable strongly, and this window has paid for that leak before.
    def _tick_all(self, _checked: bool = False) -> None:
        self._set_all(Qt.CheckState.Checked)

    def _untick_all(self, _checked: bool = False) -> None:
        self._set_all(Qt.CheckState.Unchecked)

    def _set_all(self, state: Qt.CheckState) -> None:
        self._list.blockSignals(True)
        for index in range(self._list.count()):
            self._list.item(index).setCheckState(state)
        self._list.blockSignals(False)
        self._refresh()

    def _refresh(self, _item=None) -> None:
        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setEnabled(bool(self.chosen()))

    def chosen(self) -> set[str]:
        return {
            self._list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self._list.count())
            if self._list.item(index).checkState() is Qt.CheckState.Checked
        }
