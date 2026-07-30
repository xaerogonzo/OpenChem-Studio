from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import (
    CalculationRequest,
    CalculatorDefinition,
    RegistryExecution,
    ServiceExecution,
)
from openchem.domain.project import ProjectModel
from openchem.domain.scientific_result import PerAtomDataset, SpectrumResult
from openchem.events.base import EventBus
from openchem.events.events import (
    AlertComputed,
    DescriptorComputed,
    MoleculeSelected,
    PerAtomDataComputed,
    SpectrumComputed,
)
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService
from openchem.ui.dialogs.calculator_inspector_dialog import CalculatorInspectorDialog
from openchem.ui.dialogs.calculator_settings_dialog import CalculatorSettingsDialog

# Preferred display order -- any category not listed here (e.g. a future
# plugin-supplied one) is appended alphabetically after these, not dropped.
_CATEGORY_ORDER = [
    "physicochemical",
    "identity",
    "charge",
    "logp",
    "logd",
    "molar_refractivity",
    "topology",
    "stereochemistry",
    "medicinal_chemistry",
    "pka",
    "admet",
    "shape",
]
_CATEGORY_LABELS = {
    "physicochemical": "Physicochemical",
    "identity": "Identity",
    "charge": "Charge",
    "logp": "LogP",
    "logd": "LogD (pH-dependent)",
    "molar_refractivity": "Molar Refractivity",
    "topology": "Topology",
    "stereochemistry": "Stereochemistry",
    "medicinal_chemistry": "Medicinal Chemistry",
    "pka": "pKa",
    "admet": "ADMET / Toxicity",
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
    plain content `QWidget` is the standard idiom.

    Holds two sub-layouts: `_calculators_layout` (Phase 18's "Open
    [Calculator]..." buttons, static per category, never touched by
    `clear_rows()`) above `_content_layout` (the per-molecule descriptor
    rows `clear_rows()` does reset on every molecule switch) -- kept
    separate so the calculator buttons stay visible across molecule
    switches instead of blinking away until the first descriptor for that
    category arrives again.
    """

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
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(16, 2, 2, 6)
        self._calculators_layout = QVBoxLayout()
        content_layout.addLayout(self._calculators_layout)
        self._content_layout = QFormLayout()
        content_layout.addLayout(self._content_layout)

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

    def add_calculator_widget(self, widget: QWidget) -> None:
        """A persistent widget for this section (an "Open [Calculator]..."
        button, or a hint label) -- lives in `_calculators_layout`, which
        `clear_rows` deliberately leaves alone, unlike the per-molecule
        descriptor rows in `_content_layout`."""
        self._calculators_layout.addWidget(widget)

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
    calls RDKit directly; descriptors arrive fully computed via events from
    DescriptorService.

    Phase 18: each category also gets one "Open [Calculator]..." button per
    `CalculatorRegistry` entry registered for it -- clicking one opens that
    calculator's settings dialog (if it has parameters), runs it via
    `DescriptorService.run_calculator`, and opens a `CalculatorInspectorDialog`
    once the matching result arrives. Holds `calculator_registry`/
    `descriptor_service`/`chemistry_engine` references and a `ProjectModel`
    (via `set_project`, same pattern `DockingPanel`/`QuantumChemistryPanel`
    already use) to drive this directly -- unlike the purely event-reactive
    descriptor rendering, opening a calculator is a user-initiated action
    that needs the real `MoleculeModel`, not just its uuid.
    """

    def __init__(
        self,
        event_bus: EventBus,
        calculator_registry: CalculatorRegistry,
        descriptor_service: DescriptorService,
        chemistry_engine: ChemistryEngine,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._calculator_registry = calculator_registry
        self._descriptor_service = descriptor_service
        self._chemistry_engine = chemistry_engine
        self._project: ProjectModel | None = None
        self._selected_molecule_uuid: str | None = None
        # Set right before DescriptorService.run_calculator() and cleared
        # once the matching result arrives -- distinguishes "the user just
        # asked for this calculator" from an eager-batch PerAtomDataComputed
        # for the same property_id (crippen_logp_contrib/crippen_mr_contrib
        # are computed both ways, deliberately the same value either way --
        # see compute_crippen_logp_contrib_calculator's docstring), which
        # must not silently pop the inspector open on its own.
        self._pending_calculator_id: str | None = None
        # Keyed on (provider, descriptor_id) rather than bare descriptor_id:
        # two providers (e.g. a plugin and the built-in one) could otherwise
        # pick the same short name and silently collide.
        self._value_labels: dict[tuple[str, str], QLabel] = {}
        self._alert_labels: dict[tuple[str, str], QLabel] = {}
        self._sections: dict[str, _CollapsibleSection] = {}
        # Which section each row currently lives in -- lets
        # _on_descriptor_computed detect a category change and re-parent the
        # row instead of leaving it stuck in whatever section it first drew
        # in (see the category-bucketing bug this guards against).
        self._row_sections: dict[tuple[str, str], _CollapsibleSection] = {}

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

        # Eagerly create a section (with its "Open..." buttons) for every
        # registered calculator category, even one with no matching scalar
        # descriptor to otherwise trigger section creation (pKa has none) --
        # the registry is static (registered once at bootstrap), so this
        # only ever needs to run once. Skips a category that's entirely
        # ServiceExecution-backed (Docking, QuantumChemistry, Phase 21) --
        # those run through their own panel, not through a settings-dialog
        # -> run_calculator() -> inspector flow this panel drives, so an
        # eager section for them here would just be an empty, unusable
        # section (or a button that raises CalculatorRegistry.compute()'s
        # ValueError if it somehow got one).
        for category in calculator_registry.categories():
            if any(
                isinstance(d.execution, RegistryExecution) for d in calculator_registry.by_category(category)
            ):
                self._section_for(category)

        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)
        event_bus.subscribe(DescriptorComputed, self._on_descriptor_computed)
        event_bus.subscribe(AlertComputed, self._on_alert_computed)
        event_bus.subscribe(PerAtomDataComputed, self._on_per_atom_data_computed)
        event_bus.subscribe(SpectrumComputed, self._on_spectrum_computed)

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project

    def _on_molecule_selected(self, event: MoleculeSelected) -> None:
        self._selected_molecule_uuid = event.molecule_uuid
        self._pending_calculator_id = None
        self._value_labels.clear()
        self._alert_labels.clear()
        self._row_sections.clear()
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
        for definition in self._calculator_registry.by_category(category):
            if not isinstance(definition.execution, RegistryExecution):
                # ServiceExecution-backed (Docking, QuantumChemistry) --
                # registered for discovery only, run from their own panel.
                continue
            button = QPushButton(f"Open {definition.display_name}...", section.content)
            button.clicked.connect(lambda _checked=False, d=definition: self._open_calculator(d))
            section.add_calculator_widget(button)
        self._add_service_execution_hint(section, category)
        self._reorder_sections()
        return section

    def _add_service_execution_hint(self, section: _CollapsibleSection, category: str) -> None:
        """Phase 23: a section whose runnable calculators are all
        `prediction_basis == "empirical"` gets a one-line pointer to the
        matching `"ab_initio"` calculator, when one exists. Concretely: the
        NMR section's clickable row is the instant SMARTS estimate, and
        nothing on screen previously hinted that a real ORCA NMR
        calculation exists at all -- a user could reasonably believe they
        had just run the ab initio one (Alex did).

        The ab initio counterpart lives in a DIFFERENT category
        (`orca.nmr` is in `"quantum_chemistry"`, so its own panel keeps its
        natural grouping), so the match is on the dotted-calculator_id
        convention established in Phase 21: `orca.nmr` / `orca.nmr_coupling`
        both carry `nmr` as their id suffix. Registry-driven rather than
        hardcoding "NMR", so a future empirical/ab-initio pair following
        the same naming gets this for free.
        """
        runnable = [
            d for d in self._calculator_registry.by_category(category)
            if isinstance(d.execution, RegistryExecution)
        ]
        if not runnable or any(d.prediction_basis != "empirical" for d in runnable):
            return
        ab_initio = [
            d
            for c in self._calculator_registry.categories()
            for d in self._calculator_registry.by_category(c)
            if d.prediction_basis == "ab_initio"
            and isinstance(d.execution, ServiceExecution)
            and category in d.calculator_id.split(".")[-1].split("_")
        ]
        if not ab_initio:
            return
        panel_name = ab_initio[0].execution.panel_name
        hint = QLabel(
            f"Estimate above is empirical (instant). For a real ab initio "
            f"calculation, use the {panel_name}.",
            section.content,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666666; font-style: italic;")
        section.add_calculator_widget(hint)

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
        elif self._row_sections.get(row_key) is not section:
            # A row's category can legitimately change between events (e.g.
            # a placeholder published before the real category was known) --
            # move it to the right section instead of leaving it stuck
            # wherever it was first drawn. `takeRow` (not `removeRow`, which
            # deletes the widgets) removes the row without destroying
            # `value_label`, so it can be re-added under the new section.
            old_section = self._row_sections.get(row_key)
            if old_section is not None:
                taken = old_section.content_layout().takeRow(value_label)
                if taken.labelItem is not None and taken.labelItem.widget() is not None:
                    taken.labelItem.widget().deleteLater()
            section.content_layout().addRow(label, value_label)
        self._row_sections[row_key] = section

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
        # Phase 19: routed via alert.category (PAINS -> medicinal_chemistry,
        # BRENK -> admet) now that a second alert catalog exists.
        section = self._section_for(alert.category)
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

    def _on_per_atom_data_computed(self, event: PerAtomDataComputed) -> None:
        dataset = event.dataset
        if (
            self._pending_calculator_id is not None
            and dataset.property_id == self._pending_calculator_id
            and dataset.molecule_uuid == self._selected_molecule_uuid
        ):
            self._pending_calculator_id = None
            self._open_inspector(dataset)

    def _on_spectrum_computed(self, event: SpectrumComputed) -> None:
        # Phase 22: a RegistryExecution-backed calculator (e.g. the
        # empirical SMARTS NMR estimator) can produce a SpectrumResult
        # instead of a PerAtomDataset -- matched by spectrum_type against
        # _pending_calculator_id the same way property_id is matched
        # above (the two calculators that use this path name their
        # calculator_id and spectrum_type identically).
        spectrum = event.spectrum
        if (
            self._pending_calculator_id is not None
            and spectrum.spectrum_type == self._pending_calculator_id
            and spectrum.molecule_uuid == self._selected_molecule_uuid
        ):
            self._pending_calculator_id = None
            self._open_inspector(spectrum)

    def _open_calculator(self, definition: CalculatorDefinition) -> None:
        if self._project is None or self._selected_molecule_uuid is None:
            return
        molecule = self._project.find_molecule(self._selected_molecule_uuid)
        if molecule is None:
            return
        parameters: dict[str, object] = {}
        if definition.parameters:
            dialog = CalculatorSettingsDialog(definition, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            parameters = dialog.parameters()
        self._pending_calculator_id = definition.calculator_id
        self._descriptor_service.run_calculator(
            molecule,
            CalculationRequest(calculator_id=definition.calculator_id, molecule_uuid=molecule.uuid, parameters=parameters),
        )

    def _open_inspector(self, result: PerAtomDataset | SpectrumResult) -> None:
        if self._project is None:
            return
        molecule = self._project.find_molecule(result.molecule_uuid)
        if molecule is None:
            return
        conformer_molblock = molecule.conformers[0].molblock if molecule.conformers else None
        dialog = CalculatorInspectorDialog(self._chemistry_engine, molecule, result, conformer_molblock, self)
        dialog.exec()
