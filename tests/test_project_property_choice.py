"""Choosing SOME of the always-on properties and alert catalogs for a project run, and ticking in bulk.

The Batch panel's tree could tick one of the 36 descriptors or one of the five alert catalogs;
Properties had one box for each, all or none. What is guarded:

* the run asks for exactly the chosen ids, and "all" is still what the box alone means;
* the choice rides in a preset only when somebody made one, and applying a preset that has
  none never switches a choice back to "all";
* the bulk ticks touch only what the launcher is showing (Find, and what is hidden by default).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog

import conftest
from openchem.bootstrap import build_service_container
from openchem.chem.descriptor_providers import RDKitDescriptorProvider
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.ui.dialogs.property_choice_dialog import PropertyChoiceDialog
from openchem.ui.panels.property_panel import _SCOPE_ALL, PropertyPanel

_ALL_DESCRIPTORS = set(RDKitDescriptorProvider().descriptor_ids())
_ALL_ALERTS = set(RDKitDescriptorProvider().alert_ids())


@pytest.fixture
def services(qapp):
    return build_service_container()


@pytest.fixture
def project(services):
    project = ProjectModel(name="test")
    for name, smiles in (("aspirin", "CC(=O)Oc1ccccc1C(=O)O"), ("caffeine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C")):
        molecule = MoleculeModel(display_name=name)
        services.chemistry_engine.set_structure_from_smiles(molecule, smiles)
        project.molecules.append(molecule)
    return project


@pytest.fixture
def built():
    widgets = []
    yield widgets
    for widget in widgets:
        conftest.dispose(widget)


def _settings(services):
    """The real store; pytest's autouse fixture isolates it from the person's own."""
    from openchem.app.settings import Settings

    return Settings(services.event_bus)


def _panel(services, project, built, settings=None) -> PropertyPanel:
    panel = PropertyPanel(
        services.event_bus,
        services.calculator_registry,
        services.descriptor_service,
        services.chemistry_engine,
        structure_version_of=services.structure_check_service.current_version,
        batch_service=services.batch_service,
        settings=settings,
    )
    panel.set_project(project)
    built.append(panel)
    return panel


def _plan_of(panel):
    """The plan the next project run would hand the service, read off the run-started signal."""
    plans = []
    panel.project_run_started.connect(plans.append)
    panel.set_scope(_SCOPE_ALL)
    panel._calculator_ticks["polar_surface_area"].setChecked(True)
    panel._on_run_selected()
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(120000)
    return plans[-1]


# --- the run asks for what was chosen ------------------------------------------------------


def test_the_box_alone_still_means_all_of_them(services, project, built):
    panel = _panel(services, project, built)
    panel._scope_descriptors.setChecked(True)

    assert set(_plan_of(panel).descriptor_ids) == _ALL_DESCRIPTORS


def test_a_chosen_subset_is_exactly_what_the_run_asks_for(services, project, built):
    panel = _panel(services, project, built)
    panel.set_descriptor_choice({"mol_logp", "mol_wt"})

    assert set(_plan_of(panel).descriptor_ids) == {"mol_logp", "mol_wt"}


def test_a_chosen_alert_catalog_is_exactly_what_the_run_asks_for(services, project, built):
    panel = _panel(services, project, built)
    panel._scope_descriptors.setChecked(False)
    panel.set_alert_choice({"pains"})

    assert set(_plan_of(panel).descriptor_ids) == {"pains"}


def test_a_choice_does_nothing_while_its_box_is_unticked(services, project, built):
    panel = _panel(services, project, built)
    panel.set_descriptor_choice({"mol_logp"})
    panel._scope_descriptors.setChecked(False)

    assert _plan_of(panel).descriptor_ids == ()


def test_choosing_ticks_the_box_so_the_choice_is_not_silently_ignored(services, project, built):
    panel = _panel(services, project, built)
    panel._scope_alerts.setChecked(False)

    panel.set_alert_choice({"brenk"})

    assert panel._scope_alerts.isChecked()


def test_everything_chosen_is_stored_as_all(services, project, built):
    panel = _panel(services, project, built)

    panel.set_descriptor_choice(_ALL_DESCRIPTORS)

    assert panel.descriptor_choice() is None


def test_an_empty_or_unknown_choice_is_all_never_nothing(services, project, built):
    panel = _panel(services, project, built)

    panel.set_descriptor_choice(set())
    assert panel.descriptor_choice() is None
    panel.set_descriptor_choice({"no_such_descriptor"})
    assert panel.descriptor_choice() is None


def test_an_unknown_id_in_a_choice_is_dropped(services, project, built):
    panel = _panel(services, project, built)

    panel.set_descriptor_choice({"mol_logp", "no_such_descriptor"})

    assert panel.descriptor_choice() == {"mol_logp"}


def test_the_boxes_say_how_many_are_included(services, project, built):
    panel = _panel(services, project, built)
    assert panel._scope_descriptors.text() == "Include always-on properties"

    panel.set_descriptor_choice({"mol_logp", "mol_wt"})
    panel.set_alert_choice({"pains"})

    assert panel._scope_descriptors.text() == f"Include always-on properties (2 of {len(_ALL_DESCRIPTORS)})"
    assert panel._scope_alerts.text() == f"Include structural alerts (1 of {len(_ALL_ALERTS)})"


def test_the_choose_buttons_appear_with_a_project_scope_only(services, project, built):
    panel = _panel(services, project, built)
    assert panel._choose_descriptors.isHidden() and panel._choose_alerts.isHidden()

    panel.set_scope(_SCOPE_ALL)

    assert not panel._choose_descriptors.isHidden() and not panel._choose_alerts.isHidden()


def test_the_picker_lists_every_property_grouped_with_its_name(services, project, built):
    panel = _panel(services, project, built)

    groups = panel._descriptor_choices()

    rows = [row for group in groups.values() for row in group]
    assert {row[0] for row in rows} == _ALL_DESCRIPTORS
    assert dict((row[0], row[1]) for row in rows)["mol_wt"] == "Molecular Weight"
    assert len(groups) > 1


def test_pressing_choose_opens_the_picker_and_takes_its_answer(services, project, built, monkeypatch):
    panel = _panel(services, project, built)
    seen = {}

    def fake_exec(self):
        seen["chosen_before"] = self.chosen()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PropertyChoiceDialog, "exec", fake_exec)
    monkeypatch.setattr(PropertyChoiceDialog, "chosen", lambda self: {"mol_logp"})

    panel._choose_descriptors.click()

    assert panel.descriptor_choice() == {"mol_logp"}


def test_cancelling_the_picker_changes_nothing(services, project, built, monkeypatch):
    panel = _panel(services, project, built)
    panel.set_descriptor_choice({"mol_wt"})
    monkeypatch.setattr(PropertyChoiceDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    monkeypatch.setattr(PropertyChoiceDialog, "chosen", lambda self: {"mol_logp"})

    panel._choose_descriptors.click()

    assert panel.descriptor_choice() == {"mol_wt"}


# --- presets -------------------------------------------------------------------------------


def test_a_preset_carries_a_chosen_subset(services, project, built):
    settings = _settings(services)
    panel = _panel(services, project, built, settings)
    panel._calculator_ticks["polar_surface_area"].setChecked(True)
    panel.set_descriptor_choice({"mol_logp", "mol_wt"})
    panel.set_alert_choice({"pains"})
    assert panel._presets.save("mine", panel._preset_ids_to_save())

    panel.set_descriptor_choice(None)
    panel.set_alert_choice(None)
    panel._on_clear_selection()
    panel.apply_preset("mine")

    assert panel.descriptor_choice() == {"mol_logp", "mol_wt"}
    assert panel.alert_choice() == {"pains"}
    assert panel._calculator_ticks["polar_surface_area"].isChecked()


def test_a_preset_made_with_the_boxes_at_all_stores_no_property_ids(services, project, built):
    panel = _panel(services, project, built, _settings(services))
    panel._calculator_ticks["polar_surface_area"].setChecked(True)

    assert panel._preset_ids_to_save() == ["polar_surface_area"]


def test_applying_a_preset_with_no_property_ids_leaves_the_choice_alone(services, project, built):
    panel = _panel(services, project, built, _settings(services))
    panel._presets.save("calcs only", ["polar_surface_area"])
    panel.set_descriptor_choice({"mol_wt"})

    panel.apply_preset("calcs only")

    assert panel.descriptor_choice() == {"mol_wt"}


def test_a_preset_of_only_properties_can_be_saved(services, project, built):
    panel = _panel(services, project, built, _settings(services))
    assert panel._preset_ids_to_save() == []

    panel.set_descriptor_choice({"mol_wt"})

    assert panel._preset_ids_to_save() == ["mol_wt"]


# --- ticking in bulk ----------------------------------------------------------------------------


def test_tick_all_shown_ticks_what_the_launcher_offers_and_says_how_many(services, project, built):
    panel = _panel(services, project, built)

    count = panel.tick_all_shown()

    ticked = {cid for cid, tick in panel._calculator_ticks.items() if tick.isChecked()}
    assert count == len(ticked) > 5
    assert not ticked & panel._hidden_calculator_ids
    assert panel._batch_status.text() == f"Ticked {count} shown."


def test_tick_all_shown_respects_what_find_is_showing(services, project, built):
    panel = _panel(services, project, built)
    panel._find_box.setText("polar surface")
    shown = {
        cid for cid in panel._calculator_ticks
        if not panel._calculator_rows[cid].isHidden() and cid not in panel._hidden_calculator_ids
    }

    panel.tick_all_shown()

    assert {cid for cid, tick in panel._calculator_ticks.items() if tick.isChecked()} == shown
    assert shown and len(shown) < len(panel._calculator_ticks)


def test_tick_all_shown_never_unticks(services, project, built):
    panel = _panel(services, project, built)
    panel._find_box.setText("polar surface")
    panel._find_box.setText("")
    panel._calculator_ticks["topology_analysis"].setChecked(True)

    panel._find_box.setText("polar surface")
    panel.tick_all_shown()

    assert panel._calculator_ticks["topology_analysis"].isChecked()


def test_a_section_tick_touches_only_that_section(services, project, built):
    panel = _panel(services, project, built)
    category = panel._calculator_registry.get("polar_surface_area").category
    same = {
        cid for cid in panel._calculator_ticks
        if panel._calculator_registry.get(cid).category == category and cid not in panel._hidden_calculator_ids
    }

    count = panel.set_section_ticks(category, True)

    ticked = {cid for cid, tick in panel._calculator_ticks.items() if tick.isChecked()}
    assert ticked == same and count == len(same)
    panel.set_section_ticks(category, False)
    assert not any(tick.isChecked() for tick in panel._calculator_ticks.values())


def test_the_calculator_menu_offers_the_section_ticks_and_they_work(services, project, built):
    panel = _panel(services, project, built)
    menu = panel._about_menu_for("polar_surface_area")
    actions = {a.text(): a for a in menu.actions()}

    actions["Tick every calculator in this section"].trigger()
    assert panel._calculator_ticks["polar_surface_area"].isChecked()
    actions["Untick every calculator in this section"].trigger()

    assert not panel._calculator_ticks["polar_surface_area"].isChecked()
    menu.deleteLater()


def test_the_presets_menu_offers_tick_all_shown(services, project, built):
    panel = _panel(services, project, built, _settings(services))
    menu, actions = panel.build_presets_menu()

    actions["tick_shown"].trigger()

    assert any(tick.isChecked() for tick in panel._calculator_ticks.values())
    menu.deleteLater()
