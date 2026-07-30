from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from openchem.events.base import EventBus
from openchem.events.events import AlertComputed, DescriptorComputed, MoleculeSelected

# Preferred display order -- any category not listed here (e.g. a future
# plugin-supplied one) is appended alphabetically after these, not dropped.
_CATEGORY_ORDER = [
    "physicochemical",
    "identity",
    "topology",
    "stereochemistry",
    "medicinal_chemistry",
    "shape",
]
_CATEGORY_LABELS = {
    "physicochemical": "Physicochemical",
    "identity": "Identity",
    "topology": "Topology",
    "stereochemistry": "Stereochemistry",
    "medicinal_chemistry": "Medicinal Chemistry",
    "shape": "Shape",
}
_DEFAULT_EXPANDED = {"physicochemical", "identity"}

# Sections are collapsed/expanded up front, computation is NOT deferred
# until a section opens -- every descriptor here finishes in well under a
# millisecond (confirmed live for the full ~30-descriptor RDKit batch), so
# a lazy-per-category compute path would add real service-layer complexity
# (splitting one provider's `compute()` by category, or threading a
# category filter through DescriptorService) to solve a performance
# problem that doesn't exist. Collapsing is purely a decluttering aid.


class _CollapsibleSection(QWidget):
    """A titled section that shows/hides its content on click — no native
    Qt widget does this, so a `QToolButton` (checkable, arrow icon) plus a
    plain content `QWidget` is the standard idiom."""

    def __init__(self, title: str, expanded: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._toggle_button = QToolButton(self)
        self._toggle_button.setText(title)
        self._toggle_button.setCheckable(True)
        self._toggle_button.setChecked(expanded)
        self._toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle_button.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._toggle_button.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self._toggle_button.toggled.connect(self._on_toggled)

        self.content = QWidget(self)
        self.content.setVisible(expanded)
        self._content_layout = QFormLayout(self.content)
        self._content_layout.setContentsMargins(16, 2, 2, 6)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._toggle_button)
        layout.addWidget(self.content)

    def _on_toggled(self, checked: bool) -> None:
        self._toggle_button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.content.setVisible(checked)

    def content_layout(self) -> QFormLayout:
        return self._content_layout

    def clear_rows(self) -> None:
        while self._content_layout.rowCount():
            self._content_layout.removeRow(0)


def _format_value(value: object) -> tuple[str, str]:
    """Returns (text, stylesheet) for a descriptor's value -- dispatches on
    the Python type of the value itself (bool vs. number vs. text) rather
    than a separate declared "display_type" field, so no per-category
    branching accumulates here as new descriptors are added."""
    if value is None:
        return "", ""
    if isinstance(value, bool):
        return ("Pass", "color: #2e7d32;") if value else ("Fail", "color: #c62828;")
    if isinstance(value, float):
        return f"{value:.4g}", ""
    return str(value), ""


class PropertyPanel(QWidget):
    """Categorized, collapsible descriptor view.

    Subscribes to DescriptorComputed/AlertComputed and re-renders with no
    manual refresh — the outline's "live property panel" requirement. Never
    calls RDKit; descriptors arrive fully computed via events from
    DescriptorService.
    """

    def __init__(self, event_bus: EventBus, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected_molecule_uuid: str | None = None
        # Keyed on (provider, descriptor_id) rather than bare descriptor_id:
        # two providers (e.g. a plugin and the built-in one) could otherwise
        # pick the same short name and silently collide.
        self._value_labels: dict[tuple[str, str], QLabel] = {}
        self._alert_labels: dict[tuple[str, str], QLabel] = {}
        self._sections: dict[str, _CollapsibleSection] = {}

        self._sections_container = QWidget(self)
        self._sections_layout = QVBoxLayout(self._sections_container)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.addStretch()

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self._sections_container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(scroll_area)

        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)
        event_bus.subscribe(DescriptorComputed, self._on_descriptor_computed)
        event_bus.subscribe(AlertComputed, self._on_alert_computed)

    def _on_molecule_selected(self, event: MoleculeSelected) -> None:
        self._selected_molecule_uuid = event.molecule_uuid
        self._value_labels.clear()
        self._alert_labels.clear()
        for section in self._sections.values():
            section.clear_rows()

    def _section_for(self, category: str) -> _CollapsibleSection:
        section = self._sections.get(category)
        if section is not None:
            return section
        expanded = category in _DEFAULT_EXPANDED
        title = _CATEGORY_LABELS.get(category, category.replace("_", " ").title() or "Other")
        section = _CollapsibleSection(title, expanded, self._sections_container)
        self._sections[category] = section
        self._reorder_sections()
        return section

    def _reorder_sections(self) -> None:
        # Re-inserts every known section in preferred order (listed
        # categories first, any unlisted ones appended alphabetically) --
        # cheap to just rebuild since there are only ever a handful of
        # sections, and this only runs when a brand-new category shows up
        # for the first time, not on every descriptor.
        while self._sections_layout.count():
            self._sections_layout.takeAt(0)
        ordered = sorted(
            self._sections,
            key=lambda cat: (
                _CATEGORY_ORDER.index(cat) if cat in _CATEGORY_ORDER else len(_CATEGORY_ORDER),
                cat,
            ),
        )
        for category in ordered:
            self._sections_layout.addWidget(self._sections[category])
        self._sections_layout.addStretch()

    def _on_descriptor_computed(self, event: DescriptorComputed) -> None:
        descriptor = event.descriptor
        if descriptor.molecule_uuid != self._selected_molecule_uuid:
            return
        section = self._section_for(descriptor.category or "other")
        row_key = (descriptor.provider, descriptor.descriptor_id)
        label = f"{descriptor.name} ({descriptor.units})" if descriptor.units else descriptor.name

        value_label = self._value_labels.get(row_key)
        if value_label is None:
            value_label = QLabel(section.content)
            value_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            section.content_layout().addRow(label, value_label)
            self._value_labels[row_key] = value_label

        if descriptor.cache_state.value == "failed":
            value_label.setText(descriptor.error or "Failed")
            value_label.setStyleSheet("color: #c62828;")
            value_label.setToolTip(descriptor.error or "")
        elif descriptor.cache_state.value in ("queued", "running"):
            value_label.setText(descriptor.cache_state.value.capitalize() + "...")
            value_label.setStyleSheet("color: #888888;")
            value_label.setToolTip("")
        else:
            text, style = _format_value(descriptor.value)
            value_label.setText(text)
            value_label.setStyleSheet(style)
            value_label.setToolTip("")

    def _on_alert_computed(self, event: AlertComputed) -> None:
        alert = event.alert
        if alert.molecule_uuid != self._selected_molecule_uuid:
            return
        # PAINS (the only alert catalog today) reads naturally as a
        # medicinal-chemistry concern -- not worth a category field on
        # AlertResult itself for a single instance.
        section = self._section_for("medicinal_chemistry")
        row_key = ("core", alert.alert_id)

        value_label = self._alert_labels.get(row_key)
        if value_label is None:
            value_label = QLabel(section.content)
            value_label.setWordWrap(True)
            section.content_layout().addRow(alert.name, value_label)
            self._alert_labels[row_key] = value_label

        if alert.matched:
            value_label.setText(f"{len(alert.matched)} alert(s): {', '.join(alert.matched)}")
            value_label.setStyleSheet("color: #c62828;")
        else:
            value_label.setText("Clean")
            value_label.setStyleSheet("color: #2e7d32;")
