"""Which calculators the launcher offers, what says so, and what happens when that changes.

Found in a live session on a nitramine: Thermophysical Properties (Joback) and
Detonation both read "Not applicable" for nearly everything drawn, sitting in the
launcher beside Elemental Analysis. They are hidden by default now
(`domain/calculator_support`); these tests hold the other half of that bargain --
a person who wonders where they went finds them named, explained and
switchable, and turning one on never runs it.
"""

from __future__ import annotations

import logging

import pytest
from PySide6.QtWidgets import QCheckBox, QPushButton

from openchem.app.settings import SHOW_HIDDEN_CALCULATORS, Settings
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import CalculatorDefinition, RegistryExecution
from openchem.domain.calculator_support import (
    CalculatorSupport,
    SupportStage,
    Visibility,
    help_anchor_for,
)
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected, SettingsChanged
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.ui.dialogs.calculator_visibility_page import CalculatorVisibilityPage
from openchem.ui.panels.property_panel import PropertyPanel

LIMITED = CalculatorSupport(
    SupportStage.LIMITED, Visibility.HIDDEN, support_reason="refuses most of what is drawn",
    scope_note="a small family",
)


def _definition(calculator_id: str, category: str, support=None) -> CalculatorDefinition:
    return CalculatorDefinition(
        calculator_id=calculator_id, display_name=calculator_id.replace("_", " ").title(),
        category=category, description="a calculator",
        execution=RegistryExecution(compute=lambda mol, uuid, params: None), support=support,
    )


def _registry() -> CalculatorRegistry:
    registry = CalculatorRegistry()
    registry.register(_definition("everyday", "identity"))
    registry.register(_definition("shown_too", "identity"))
    registry.register(_definition("niche", "thermophysical", LIMITED))
    registry.register(_definition("niche_beside_others", "identity", LIMITED))
    return registry


def _definitions(registry: CalculatorRegistry) -> list:
    return [d for category in registry.categories() for d in registry.by_category(category)]


class _Service:
    def __init__(self) -> None:
        self.calls: list = []

    def run_calculator(self, model, request) -> None:
        self.calls.append(request.calculator_id)


def _panel(qapp, settings=None, registry=None):
    bus = EventBus()
    service = _Service()
    panel = PropertyPanel(
        bus, registry or _registry(), service, ChemistryEngine(),
        settings=settings if settings is not None else Settings(bus),
    )
    return panel, bus, service


# --- the stored preferences -------------------------------------------------


def test_nothing_is_stored_until_somebody_chooses(qapp):
    settings = Settings(EventBus())
    assert settings.preference(SHOW_HIDDEN_CALCULATORS) is False
    assert settings.calculator_override("niche") is None


def test_a_choice_for_one_calculator_survives_the_ini_backend(qapp):
    """The INI file hands values back as strings, so this reads them as names."""
    Settings(EventBus()).set_calculator_override("niche", Visibility.SHOWN)
    assert Settings(EventBus()).calculator_override("niche") is Visibility.SHOWN
    Settings(EventBus()).set_calculator_override("niche", None)
    assert Settings(EventBus()).calculator_override("niche") is None


def test_a_damaged_choice_follows_the_default_and_says_so(qapp, caplog):
    settings = Settings(EventBus())
    settings.set("calculators/override/niche", "sometimes")
    with caplog.at_level(logging.WARNING, logger="openchem.app"):
        assert settings.calculator_override("niche") is None
    assert "calculators/override/niche" in caplog.text


def test_effective_visibility_combines_the_default_the_master_toggle_and_the_choice(qapp):
    settings = Settings(EventBus())
    registry = _registry()
    niche = registry.get("niche")
    everyday = registry.get("everyday")
    assert settings.calculator_is_visible(everyday) and not settings.calculator_is_visible(niche)

    settings.set_preference(SHOW_HIDDEN_CALCULATORS, True)
    assert settings.calculator_is_visible(niche)

    settings.set_calculator_override("niche", Visibility.HIDDEN)  # the person's own choice wins
    assert not settings.calculator_is_visible(niche)


def test_writing_a_choice_says_so_on_the_bus(qapp):
    bus = EventBus()
    heard: list[str] = []
    bus.subscribe(SettingsChanged, lambda event: heard.append(event.key))
    settings = Settings(bus)
    settings.set_calculator_override("niche", Visibility.SHOWN)
    settings.set_calculator_override("niche", None)
    assert heard == ["calculators/override/niche", "calculators/override/niche"]


# --- the page ---------------------------------------------------------------


def test_the_page_lists_only_what_has_something_to_explain(qapp):
    page = CalculatorVisibilityPage(Settings(EventBus()), _definitions(_registry()))
    assert sorted(page._row_ticks) == ["niche", "niche_beside_others"]


def test_each_row_says_its_level_its_reason_and_its_coverage(qapp):
    page = CalculatorVisibilityPage(Settings(EventBus()), _definitions(_registry()))
    from PySide6.QtWidgets import QLabel

    level = page.findChild(QLabel, "calculatorLevel:niche")
    why = page.findChild(QLabel, "calculatorWhy:niche")
    covers = page.findChild(QLabel, "calculatorCovers:niche")
    assert "Limited" in level.text() and "hidden by default" in level.text()
    assert "refuses most of what is drawn" in why.text()
    assert "a small family" in covers.text()


def test_a_hidden_calculator_starts_unticked_and_ticking_it_stores_a_choice(qapp):
    settings = Settings(EventBus())
    page = CalculatorVisibilityPage(settings, _definitions(_registry()))
    assert page.offered("niche") is False

    page._row_ticks["niche"].setChecked(True)

    assert settings.calculator_override("niche") is Visibility.SHOWN
    assert settings.calculator_is_visible(_registry().get("niche"))


def test_ticking_a_row_back_to_its_default_forgets_the_choice_rather_than_storing_one(qapp):
    """A stored "hidden" would outlive a later change of the calculator's default."""
    settings = Settings(EventBus())
    page = CalculatorVisibilityPage(settings, _definitions(_registry()))
    page._row_ticks["niche"].setChecked(True)
    page._row_ticks["niche"].setChecked(False)
    assert settings.calculator_override("niche") is None


def test_the_master_toggle_moves_every_tick_and_stores_no_per_calculator_choice(qapp):
    settings = Settings(EventBus())
    page = CalculatorVisibilityPage(settings, _definitions(_registry()))
    page._master.setChecked(True)
    assert page.offered("niche") and page.offered("niche_beside_others")
    assert settings.calculator_override("niche") is None


def test_a_choice_of_ones_own_beats_the_master_toggle(qapp):
    settings = Settings(EventBus())
    page = CalculatorVisibilityPage(settings, _definitions(_registry()))
    page._master.setChecked(True)
    page._row_ticks["niche"].setChecked(False)  # differs from what the master gives
    assert settings.calculator_override("niche") is Visibility.HIDDEN
    assert page.offered("niche") is False and page.offered("niche_beside_others") is True


def test_reset_puts_every_calculator_back_to_its_default(qapp):
    settings = Settings(EventBus())
    registry = _registry()
    page = CalculatorVisibilityPage(settings, _definitions(registry))
    page._master.setChecked(True)
    page._row_ticks["niche"].setChecked(False)

    page.findChild(QPushButton, "resetCalculatorVisibility").click()

    assert settings.preference(SHOW_HIDDEN_CALCULATORS) is False
    assert settings.calculator_override("niche") is None
    assert page._master.isChecked() is False and page.offered("niche") is False


def test_learn_more_opens_that_calculators_own_section(qapp):
    opened: list[str] = []
    page = CalculatorVisibilityPage(
        Settings(EventBus()), _definitions(_registry()), open_help=opened.append
    )
    page.findChild(QPushButton, "calculatorLearnMore:niche").click()
    assert opened == [help_anchor_for("niche")] == ["calc-niche"]


def test_learn_more_with_no_route_opens_a_help_window_that_is_a_child_of_the_page(qapp):
    """A modal Settings window blocks input to every window except its own
    children, so a help window parented to the main window would open dead."""
    from openchem.ui.dialogs.help_dialog import HelpDialog

    page = CalculatorVisibilityPage(Settings(EventBus()), _definitions(_registry()))
    page.show_help_for("joback_properties")
    window = page._help_window
    try:
        assert isinstance(window, HelpDialog) and window.parent() is page
        assert window._current_key == help_anchor_for("joback_properties")
    finally:
        window.close()


def test_the_real_registry_page_names_joback_and_detonation(qapp):
    from openchem.bootstrap import build_service_container

    definitions = _definitions(build_service_container().calculator_registry)
    page = CalculatorVisibilityPage(Settings(EventBus()), definitions)
    assert sorted(page._row_ticks) == ["detonation", "joback_properties"]
    assert page.offered("joback_properties") is False and page.offered("detonation") is False


# --- the launcher ------------------------------------------------------------


def test_a_hidden_calculator_has_no_row_and_its_section_goes_with_it(qapp):
    panel, _bus, _service = _panel(qapp)
    assert panel._calculator_rows["niche"].isHidden()
    assert panel._calculator_rows["niche_beside_others"].isHidden()
    assert not panel._calculator_rows["everyday"].isHidden()
    # The thermophysical section held only the hidden one; identity still has two others.
    assert panel._sections["thermophysical"].isHidden()
    assert not panel._sections["identity"].isHidden()


def test_the_footer_says_how_many_are_hidden_and_where_they_went(qapp):
    panel, _bus, _service = _panel(qapp)
    link = panel._hidden_link
    assert not link.isHidden()
    assert link.text() == "2 calculators hidden by default -- Settings..."
    heard: list[str] = []
    panel.settings_requested.connect(heard.append)
    link.click()
    assert heard == ["calculators"]


def test_with_nothing_hidden_there_is_no_footer(qapp):
    registry = CalculatorRegistry()
    registry.register(_definition("everyday", "identity"))
    panel, _bus, _service = _panel(qapp, registry=registry)
    assert panel._hidden_link.isHidden()


def test_turning_the_master_toggle_on_offers_them_without_running_anything(qapp):
    panel, _bus, service = _panel(qapp)

    panel._settings.set_preference(SHOW_HIDDEN_CALCULATORS, True)

    assert not panel._calculator_rows["niche"].isHidden()
    assert not panel._sections["thermophysical"].isHidden()
    assert panel._hidden_link.isHidden()
    assert service.calls == [], "offering a calculator never runs it"


def test_one_calculators_own_choice_offers_only_that_one(qapp):
    panel, _bus, _service = _panel(qapp)

    panel._settings.set_calculator_override("niche_beside_others", Visibility.SHOWN)

    assert not panel._calculator_rows["niche_beside_others"].isHidden()
    assert panel._calculator_rows["niche"].isHidden()
    assert panel._hidden_link.text() == "1 calculator hidden by default -- Settings..."


def test_a_withdrawn_calculator_is_never_run_by_run_selected(qapp):
    """Ticked while offered, then withdrawn: the tick goes with the row, so
    "Run selected" cannot run something the person can no longer see."""
    panel, bus, service = _panel(qapp)
    panel._settings.set_preference(SHOW_HIDDEN_CALCULATORS, True)
    panel._project = ProjectModel()
    molecule = MoleculeModel(molblock="x")
    panel._project.molecules.append(molecule)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    panel._calculator_ticks["niche"].setChecked(True)
    panel._calculator_ticks["everyday"].setChecked(True)
    assert set(panel._selected_calculator_ids()) == {"everyday", "niche"}

    panel._settings.set_preference(SHOW_HIDDEN_CALCULATORS, False)

    assert panel._calculator_ticks["niche"].isChecked() is False
    assert panel._selected_calculator_ids() == ["everyday"]
    panel._on_run_selected()
    assert service.calls == ["everyday"]


def test_a_panel_built_with_no_settings_offers_what_it_always_did(qapp):
    """A fixture with no `Settings` sees every UNCLASSIFIED calculator, and the
    classified hidden ones stay hidden: the declaration is the default."""
    bus = EventBus()
    panel = PropertyPanel(bus, _registry(), _Service(), ChemistryEngine())
    assert not panel._calculator_rows["everyday"].isHidden()
    assert panel._calculator_rows["niche"].isHidden()


def test_the_footer_and_the_settings_page_agree_about_how_many_are_hidden(qapp):
    panel, _bus, _service = _panel(qapp)
    page = CalculatorVisibilityPage(panel._settings, _definitions(_registry()))
    unticked = [cid for cid in page._row_ticks if not page.offered(cid)]
    assert len(unticked) == len(panel._hidden_calculator_ids) == 2


def test_every_row_of_the_page_carries_a_help_contract(qapp):
    from openchem.ui.widgets.help_tooltip import help_tooltip_for, placeholder_reason

    page = CalculatorVisibilityPage(Settings(EventBus()), _definitions(_registry()))
    controls = list(page.findChildren(QCheckBox)) + list(page.findChildren(QPushButton))
    # The master toggle and Reset, plus a tick and a Learn more for each of two rows.
    assert len(controls) == 6
    for control in controls:
        contract = help_tooltip_for(control)
        assert contract is not None, control.objectName() or control.text()
        assert placeholder_reason(contract) is None
