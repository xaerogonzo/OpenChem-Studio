from __future__ import annotations

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from openchem.events.base import EventBus
from openchem.events.events import DescriptorComputed, MoleculeSelected


class PropertyPanel(QWidget):
    """Live descriptor table.

    Subscribes to DescriptorComputed and re-renders with no manual refresh —
    the outline's "live property panel" requirement. Never calls RDKit;
    descriptors arrive fully computed via events from DescriptorService.
    """

    def __init__(self, event_bus: EventBus, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected_molecule_uuid: str | None = None
        # Keyed on (provider, descriptor_id) rather than bare descriptor_id:
        # two providers (e.g. a plugin and the built-in one) could otherwise
        # pick the same short name and silently collide in this table.
        self._rows: dict[tuple[str, str], int] = {}

        self._table = QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels(["Descriptor", "Value", "Status"])
        self._table.horizontalHeader().setStretchLastSection(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._table)

        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)
        event_bus.subscribe(DescriptorComputed, self._on_descriptor_computed)

    def _on_molecule_selected(self, event: MoleculeSelected) -> None:
        self._selected_molecule_uuid = event.molecule_uuid
        self._table.setRowCount(0)
        self._rows.clear()

    def _on_descriptor_computed(self, event: DescriptorComputed) -> None:
        descriptor = event.descriptor
        if descriptor.molecule_uuid != self._selected_molecule_uuid:
            return
        row_key = (descriptor.provider, descriptor.descriptor_id)
        row = self._rows.get(row_key)
        if row is None:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._rows[row_key] = row
        label = f"{descriptor.name} ({descriptor.units})" if descriptor.units else descriptor.name
        value_text = "" if descriptor.value is None else str(descriptor.value)
        self._table.setItem(row, 0, QTableWidgetItem(label))
        self._table.setItem(row, 1, QTableWidgetItem(value_text))
        self._table.setItem(row, 2, QTableWidgetItem(descriptor.cache_state.value))
