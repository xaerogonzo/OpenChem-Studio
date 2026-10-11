"""The goal wizard dialog: the quick path, the customised path, and what a run carries.

The dialog is built with plain lookups (a registry's `get`, a list of molecules, a
selection, a scope), so these tests need no window. What is guarded:

* **Run recommended is the whole quick path**: one press, the goal's recommended set,
  default settings, the scope shown;
* **the customised path runs EXACTLY what is ticked, with exactly the settings chosen**,
  in the goal's order, and nothing else;
* **a run is fixed when it is asked for**: another goal, another tick or another scope
  afterwards cannot reach it;
* **it says what a run will cost and need before it starts**: the size, what is left
  out, and that some calculators want a 3D structure the molecule does not have.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog

import conftest
from openchem.bootstrap import build_service_container
from openchem.domain.calculator_goals import (
    GOALS,
    SCOPE_ALL,
    SCOPE_CHOSEN,
    SCOPE_THIS,
    goal_of,
)
from openchem.domain.molecule import MoleculeModel
from openchem.ui.dialogs import goal_wizard_dialog as wizard_module
from openchem.ui.dialogs.goal_wizard_dialog import GoalWizardDialog


@pytest.fixture
def services(qapp):
    return build_service_container()


@pytest.fixture
def built():
    widgets = []
    yield widgets
    for widget in widgets:
        conftest.dispose(widget)


def _molecules(services, *names_and_smiles):
    molecules = []
    for name, smiles in names_and_smiles:
        molecule = MoleculeModel(display_name=name)
        if smiles:
            services.chemistry_engine.set_structure_from_smiles(molecule, smiles)
        molecules.append(molecule)
    return molecules


def _wizard(services, built, molecules, *, selected=None, scope=(SCOPE_THIS, set()), conformers=None):
    wizard = GoalWizardDialog(
        services.calculator_registry.get,
        lambda: molecules,
        lambda: selected if selected is not None else (molecules[0].uuid if molecules else None),
        lambda: scope,
        on_generate_conformers=conformers,
    )
    built.append(wizard)
    return wizard


def _ids(run):
    return list(run.calculator_ids)


# --- the first page --------------------------------------------------------------------------


def test_every_goal_is_listed_in_order(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")))

    listed = [wizard._goal_list.item(i).data(wizard_module.Qt.ItemDataRole.UserRole) for i in range(wizard._goal_list.count())]

    assert listed == [g.goal_id for g in GOALS]
    assert wizard.goal.goal_id == GOALS[0].goal_id


def test_the_first_page_says_what_run_recommended_will_run(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")))
    wizard.select_goal("charge")

    text = wizard._will_run.text()

    for calculator_id in goal_of("charge").recommended_ids():
        assert services.calculator_registry.get(calculator_id).display_name in text
    assert "1 molecule" in text


def test_run_recommended_is_one_press_and_asks_for_the_recommended_set(services, built):
    molecules = _molecules(services, ("A", "CCO"))
    wizard = _wizard(services, built, molecules)
    wizard.select_goal("charge")
    asked = []
    wizard.run_requested.connect(asked.append)

    wizard._run_recommended_button.click()

    assert len(asked) == 1
    run = asked[0]
    assert run.goal_id == "charge"
    assert _ids(run) == list(goal_of("charge").recommended_ids())
    assert run.scope_mode == SCOPE_THIS
    assert dict(run.parameters) == {}, "default settings"
    assert wizard.last_run is run


def test_choosing_another_goal_changes_what_it_runs(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")))
    asked = []
    wizard.run_requested.connect(asked.append)

    wizard.select_goal("solubility")
    wizard._run_recommended_button.click()
    wizard.select_goal("druglike")
    wizard._run_recommended_button.click()

    assert [r.goal_id for r in asked] == ["solubility", "druglike"]
    assert _ids(asked[0]) == list(goal_of("solubility").recommended_ids())
    assert _ids(asked[1]) == list(goal_of("druglike").recommended_ids())


def test_the_scope_starts_as_properties_has_it_and_is_carried(services, built):
    molecules = _molecules(services, ("A", "CCO"), ("B", "CCN"), ("C", "CCC"))
    wizard = _wizard(services, built, molecules, scope=(SCOPE_ALL, set()))
    asked = []
    wizard.run_requested.connect(asked.append)

    wizard._run_recommended_button.click()

    assert asked[0].scope_mode == SCOPE_ALL
    assert "3 molecule" in wizard._will_run.text()
    assert wizard._scope_combo.currentData() == SCOPE_ALL


def test_a_chosen_scope_carries_the_molecules_by_id(services, built):
    molecules = _molecules(services, ("A", "CCO"), ("B", "CCN"), ("C", "CCC"))
    wizard = _wizard(services, built, molecules)
    asked = []
    wizard.run_requested.connect(asked.append)

    wizard.set_scope(SCOPE_CHOSEN, {molecules[0].uuid, molecules[2].uuid})
    wizard._run_recommended_button.click()

    assert asked[0].scope_mode == SCOPE_CHOSEN
    assert set(asked[0].scope_uuids) == {molecules[0].uuid, molecules[2].uuid}


def test_a_scope_with_no_molecules_cannot_be_run(services, built):
    wizard = _wizard(services, built, [])

    assert not wizard._run_recommended_button.isEnabled()
    assert not wizard._customise_button.isEnabled()


def test_changing_the_wizards_scope_does_not_touch_anything_it_was_given(services, built):
    """It starts from Properties' scope and keeps its own after that."""
    scope = (SCOPE_THIS, set())
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO"), ("B", "CCN")), scope=scope)

    wizard.set_scope(SCOPE_ALL)

    assert scope == (SCOPE_THIS, set())


# --- the customised path -------------------------------------------------------------------------


def _customise(wizard, goal_id):
    wizard.select_goal(goal_id)
    wizard._customise_button.click()


def test_customise_lists_recommended_ticked_and_optional_unticked(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")))
    _customise(wizard, "charge")
    goal = goal_of("charge")

    for entry in goal.entries:
        assert wizard._entry_checks[entry.calculator_id].isChecked() == (entry.role == "recommended")
    assert wizard.ticked_ids() == list(goal.recommended_ids())


def test_the_customised_run_is_exactly_what_is_ticked_in_the_goals_order(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")))
    _customise(wizard, "charge")
    asked = []
    wizard.run_requested.connect(asked.append)
    goal = goal_of("charge")
    untick = goal.recommended_ids()[1]
    add = goal.optional()[0].calculator_id
    wizard._entry_checks[untick].setChecked(False)
    wizard._entry_checks[add].setChecked(True)

    wizard._run_button.click()

    expected = [e.calculator_id for e in goal.entries if e.calculator_id != untick and e.calculator_id in set(goal.recommended_ids()) | {add}]
    assert _ids(asked[0]) == expected
    assert untick not in asked[0].calculator_ids and add in asked[0].calculator_ids


def test_a_changed_setting_travels_only_with_the_calculator_it_was_chosen_for(services, built, monkeypatch):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")))
    _customise(wizard, "charge")
    asked = []
    wizard.run_requested.connect(asked.append)

    class _Accepted:
        def __init__(self, definition, parent=None):
            self.definition = definition

        def exec(self):
            return QDialog.DialogCode.Accepted

        def parameters(self):
            return {"pH": 6.25}

    monkeypatch.setattr(wizard_module, "CalculatorSettingsDialog", _Accepted)
    row = wizard._entries_area.widget()
    buttons = [b for b in row.findChildren(wizard_module.QPushButton) if b.property("openchem_calculator_id") == "gasteiger_charge_at_ph"]
    assert buttons, "the calculator has a Settings button"
    buttons[0].click()

    wizard._run_button.click()

    assert dict(asked[0].parameters["gasteiger_charge_at_ph"]) == {"pH": 6.25}
    assert set(asked[0].parameters) == {"gasteiger_charge_at_ph"}


def test_a_setting_chosen_for_a_calculator_that_is_then_unticked_is_not_sent(services, built, monkeypatch):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")))
    _customise(wizard, "charge")
    asked = []
    wizard.run_requested.connect(asked.append)
    wizard._chosen_parameters["gasteiger_charge_at_ph"] = {"pH": 6.25}
    wizard._entry_checks["gasteiger_charge_at_ph"].setChecked(False)

    wizard._run_button.click()

    assert "gasteiger_charge_at_ph" not in asked[0].parameters


def test_choosing_another_goal_forgets_settings_chosen_for_the_last(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")))
    wizard.select_goal("charge")
    wizard._chosen_parameters["gasteiger_charge_at_ph"] = {"pH": 6.25}

    wizard.select_goal("solubility")

    assert wizard._chosen_parameters == {}


def test_the_run_button_is_off_when_nothing_is_ticked(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")))
    _customise(wizard, "charge")

    for check in wizard._entry_checks.values():
        check.setChecked(False)

    assert not wizard._run_button.isEnabled()


def test_back_returns_to_the_first_page(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")))
    _customise(wizard, "charge")
    assert wizard._stack.currentIndex() == wizard_module._PAGE_CUSTOMISE

    wizard._stack.currentWidget().findChildren(wizard_module.QPushButton)  # the page exists
    wizard._on_back()

    assert wizard._stack.currentIndex() == wizard_module._PAGE_GOALS


# --- a run is fixed when it is asked for ------------------------------------------------------------


def test_nothing_done_after_a_run_is_asked_for_can_reach_it(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO"), ("B", "CCN")))
    _customise(wizard, "charge")
    asked = []
    wizard.run_requested.connect(asked.append)
    wizard._run_button.click()
    first = asked[0]
    ids, parameters, scope = first.calculator_ids, dict(first.parameters), first.scope_mode

    for check in wizard._entry_checks.values():
        check.setChecked(True)
    wizard.select_goal("druglike")
    wizard.set_scope(SCOPE_ALL)

    assert first.calculator_ids == ids
    assert dict(first.parameters) == parameters
    assert first.scope_mode == scope == SCOPE_THIS


def test_a_second_press_makes_a_second_run_with_its_own_id(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")))
    asked = []
    wizard.run_requested.connect(asked.append)

    wizard._run_recommended_button.click()
    wizard._run_recommended_button.click()

    assert len(asked) == 2 and asked[0].run_id != asked[1].run_id


# --- what it says before it starts -----------------------------------------------------------------------


def test_the_plan_says_how_many_calculations_it_is(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO"), ("B", "CCN")), scope=(SCOPE_ALL, set()))
    _customise(wizard, "identity")

    text = wizard._plan_summary.text()

    count = len(goal_of("identity").recommended_ids())
    assert f"{count} calculator(s) on 2 molecule(s): {count * 2} calculation(s)" in text


def test_a_molecule_with_no_structure_is_named_as_left_out(services, built):
    molecules = _molecules(services, ("Drawn", "CCO"), ("Empty", None))
    wizard = _wizard(services, built, molecules, scope=(SCOPE_ALL, set()))
    _customise(wizard, "identity")

    assert "Empty" in wizard._plan_summary.text() and "no structure" in wizard._plan_summary.text()


def test_a_3d_calculator_with_no_conformer_is_said_so_and_a_way_to_make_one_is_offered(services, built):
    called = []
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")), conformers=lambda: called.append(1))
    _customise(wizard, "charge")

    assert not wizard._conformer_note.isHidden()
    assert "3D structure" in wizard._conformer_note.text()
    assert not wizard._conformer_button.isHidden()

    wizard._conformer_button.click()
    assert called == [1]


def test_no_conformer_note_for_a_goal_that_needs_none(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")), conformers=lambda: None)
    _customise(wizard, "identity")

    assert wizard._conformer_note.isHidden() and wizard._conformer_button.isHidden()


def test_no_conformer_note_once_the_molecule_has_one(services, built):
    molecules = _molecules(services, ("A", "CCO"))
    molecules[0].conformers.append(object())
    wizard = _wizard(services, built, molecules, conformers=lambda: None)
    _customise(wizard, "charge")

    assert wizard._conformer_note.isHidden()


def test_without_a_way_to_make_conformers_the_note_is_still_said(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")), conformers=None)
    _customise(wizard, "charge")

    assert not wizard._conformer_note.isHidden()
    assert wizard._conformer_button.isHidden()


def test_the_outcome_the_window_reports_is_shown(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")))

    wizard.show_outcome("Running 3 for 'Identity and naming'")

    assert wizard._status.text() == "Running 3 for 'Identity and naming'"


def test_choosing_another_goal_clears_what_was_said_about_the_last_run(services, built):
    wizard = _wizard(services, built, _molecules(services, ("A", "CCO")))
    wizard.show_outcome("Running 4 for 'Identity and naming'")

    wizard.select_goal("charge")

    assert wizard._status.text() == ""
