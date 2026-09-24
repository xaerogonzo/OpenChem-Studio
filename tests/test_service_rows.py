"""Calculators run from another panel have a REAL row in Properties, and pressing it opens that panel.

Nine calculators -- Vina docking, the seven ORCA jobs and Hardness/Softness -- are run by their
own service from their own panel, and Properties skipped them with one `continue` and an italic
sentence naming the panel. A person looking for an ab initio NMR in Properties found a hint and
nothing to press. Now each has a row that OPENS the panel with the calculation chosen; it has no
tick box (nothing here runs) and no status chip, and "Run selected" can never include it.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QPushButton

from openchem.app.main_window import HELP_TOPIC_BY_DOCK, MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import RegistryExecution, ServiceExecution
from openchem.events.base import EventBus
from openchem.ui.panels.property_panel import PropertyPanel
from tests.conftest import dispose
from tests.test_property_panel import _FakeDescriptorService


def _service_definitions(registry):
    return [
        d
        for category in registry.categories()
        for d in registry.by_category(category)
        if isinstance(d.execution, ServiceExecution)
    ]


@pytest.fixture(scope="module")
def registry():
    return build_service_container().calculator_registry


@pytest.fixture
def panel(qapp, registry):
    widget = PropertyPanel(EventBus(), registry, _FakeDescriptorService(), ChemistryEngine())
    yield widget
    dispose(widget)


def test_every_service_calculator_declares_a_panel_that_exists(registry):
    """A guard, not a convenience: a row whose panel id is a typo is a button that opens nothing."""
    definitions = _service_definitions(registry)
    assert len(definitions) == 9, "the nine calculators run from another panel"
    for definition in definitions:
        assert definition.execution.panel_id in HELP_TOPIC_BY_DOCK, (
            f"{definition.calculator_id} names panel {definition.execution.panel_id!r}, "
            f"which is not one of {sorted(HELP_TOPIC_BY_DOCK)}"
        )


def test_every_service_calculator_has_a_row(panel, registry):
    for definition in _service_definitions(registry):
        assert definition.calculator_id in panel._service_rows, definition.calculator_id


def test_a_service_row_is_a_button_with_no_tick_and_no_chip(panel, registry):
    for definition in _service_definitions(registry):
        row = panel._service_rows[definition.calculator_id]
        assert isinstance(row, QPushButton)
        assert definition.calculator_id not in panel._calculator_ticks, "nothing here can be batched"
        assert definition.calculator_id not in panel._calculator_status, "nothing here has a result to report"


def test_the_label_names_the_panel_it_opens(panel, registry):
    definition = registry.get("orca.nmr")
    label = panel._service_rows["orca.nmr"]._full_text
    assert definition.display_name in label
    assert "Quantum Chemistry panel" in label


def test_pressing_a_row_asks_for_that_panel_and_that_calculation(panel):
    requests: list[tuple[str, str]] = []
    panel.service_panel_requested.connect(lambda panel_id, calculator_id: requests.append((panel_id, calculator_id)))

    panel._service_rows["orca.nmr"].click()
    panel._service_rows["docking.vina"].click()

    assert requests == [("Quantum_Chemistry", "orca.nmr"), ("Docking", "docking.vina")]


def test_run_selected_never_includes_a_service_row(panel):
    assert not any(cid.startswith(("orca.", "docking.")) for cid in panel._selected_calculator_ids())
    assert "lewis_hsab" not in panel._calculator_ticks


def test_the_service_only_categories_now_have_sections(panel):
    assert {"docking", "quantum_chemistry"} <= set(panel._sections)


def test_the_hsab_row_sits_in_the_lewis_section_beside_the_registry_calculators(panel, registry):
    assert registry.get("lewis_hsab").category == "lewis"
    assert "lewis_hsab" in panel._service_rows
    assert any(isinstance(d.execution, RegistryExecution) for d in registry.by_category("lewis"))


def test_the_row_tooltip_says_it_runs_nothing_and_does_not_borrow_the_registry_basis(panel):
    from openchem.ui.widgets.help_tooltip import help_tooltip_for

    contract = help_tooltip_for(panel._service_rows["orca.nmr"])
    assert contract is not None
    assert "runs nothing" in contract.text
    assert "structure as drawn" not in contract.text, "that sentence is about registry calculators"


# --- the panel it opens ---------------------------------------------------------------------


def test_the_quantum_panel_selects_a_calculation_by_its_type_code(qapp):
    from openchem.ui.panels.quantum_chemistry_panel import CALC_TYPE_LABELS, QuantumChemistryPanel

    services = build_service_container()
    settings = Settings(services.event_bus)
    quantum = QuantumChemistryPanel(
        services.quantum_chemistry_service, services.chemistry_engine, settings, services.event_bus
    )
    try:
        assert quantum.select_calculation_type("nmr") is True
        assert CALC_TYPE_LABELS[quantum._calc_type_combo.currentText()] == "nmr"
        assert quantum.select_calculation_type("no_such_job") is False
        assert CALC_TYPE_LABELS[quantum._calc_type_combo.currentText()] == "nmr", "unchanged on a miss"
    finally:
        dispose(quantum)


@pytest.fixture
def window(qapp, tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    return MainWindow(services, settings, SessionManager())


def test_the_window_shows_the_panel_and_chooses_the_calculation(window):
    from openchem.ui.panels.quantum_chemistry_panel import CALC_TYPE_LABELS

    window._property_panel.service_panel_requested.emit("Quantum_Chemistry", "orca.nmr_coupling")

    dock = window._dock_by_panel_id("Quantum_Chemistry")
    assert dock is not None and not dock.isHidden(), "the panel was not shown"
    chosen = window._quantum_chemistry_panel._calc_type_combo.currentText()
    assert CALC_TYPE_LABELS[chosen] == "nmr_coupling"


def test_the_docking_row_opens_the_docking_panel_and_chooses_nothing(window):
    window._property_panel.service_panel_requested.emit("Docking", "docking.vina")
    dock = window._dock_by_panel_id("Docking")
    assert dock is not None and not dock.isHidden()


def test_every_panel_id_a_row_can_ask_for_is_a_real_dock(window, registry):
    for definition in _service_definitions(registry):
        assert window._dock_by_panel_id(definition.execution.panel_id) is not None, definition.calculator_id
