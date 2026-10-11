"""The curated goals: that they are sound against the registry, and that a run is a value.

What is guarded, and why each is a real failure rather than tidiness:

* **every recommendation names a calculator that runs here and can be seen.** A retired id,
  a calculator that now needs input, one that runs from its own panel or is hidden by
  default would be a recommendation that silently runs nothing or runs what the person
  cannot see. `validate_goals` is the check, and it is mutated below so it is known to bite;
* **a goal is a task group's id**, so a group's "Run recommended" button and the wizard's
  goal of the same name are one set under one name;
* **a `GoalRun` cannot be changed after it is made**, which is what makes "a run is what it
  was when you pressed Run" true.
"""

from __future__ import annotations

import dataclasses

import pytest

from openchem.bootstrap import build_service_container
from openchem.domain.calculator_goals import (
    GOALS,
    OPTIONAL,
    RECOMMENDED,
    SCOPE_ALL,
    SCOPE_CHOSEN,
    SCOPE_THIS,
    SCOPES,
    Goal,
    GoalRun,
    Recommendation,
    goal_ids,
    goal_of,
    needs_conformer,
    validate_goals,
)
from openchem.domain.calculator_taxonomy import FALLBACK_TASK_GROUP, TASK_GROUPS


@pytest.fixture(scope="module")
def registry():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    return build_service_container().calculator_registry


# --- the table is sound -------------------------------------------------------------------


def test_the_goals_are_sound_against_the_real_registry(registry):
    assert validate_goals(registry.get) == []


def test_every_task_group_with_a_heading_has_a_goal_and_in_the_same_order():
    headed = [group for group in TASK_GROUPS if group != FALLBACK_TASK_GROUP]

    assert list(goal_ids()) == headed


def test_a_goal_is_named_by_its_task_groups_label():
    for goal in GOALS:
        assert goal.label == TASK_GROUPS[goal.goal_id]


def test_every_goal_recommends_something_and_offers_more_than_it_recommends_only_when_it_has_more():
    for goal in GOALS:
        assert goal.recommended(), goal.goal_id
        assert set(goal.recommended_ids()).isdisjoint(e.calculator_id for e in goal.optional())


def test_no_calculator_is_listed_twice_in_a_goal():
    for goal in GOALS:
        ids = [e.calculator_id for e in goal.entries]
        assert len(ids) == len(set(ids)), goal.goal_id


def test_every_entry_says_why_it_is_there():
    for goal in GOALS:
        for entry in goal.entries:
            assert entry.reason.strip(), f"{goal.goal_id}/{entry.calculator_id}"


def test_a_goal_can_be_found_by_id():
    assert goal_of("charge").goal_id == "charge"
    assert goal_of("no-such-goal") is None


def test_the_calculators_that_need_a_3d_structure_are_recognised(registry):
    assert needs_conformer(registry.get("dipole_moment"))
    assert needs_conformer(registry.get("geometry_partial_charge"))
    assert not needs_conformer(registry.get("elemental_analysis"))


# --- the check bites --------------------------------------------------------------------------


def _goal(*entries: Recommendation, goal_id: str = "charge") -> tuple[Goal, ...]:
    return (Goal(goal_id, "A question?", tuple(entries)),)


def _rec(calculator_id, role=RECOMMENDED, reason="because", **parameters):
    return Recommendation(calculator_id, role, reason, parameters)


def _problems(registry, *entries, goal_id="charge"):
    return validate_goals(registry.get, _goal(*entries, goal_id=goal_id))


def test_a_retired_id_is_reported(registry):
    assert any("no such calculator" in p for p in _problems(registry, _rec("not_a_calculator")))


def test_a_calculator_that_runs_from_its_own_panel_is_reported(registry):
    problems = _problems(registry, _rec("orca.sp"))

    assert any("own panel" in p for p in problems)


def test_a_calculator_hidden_by_default_is_reported(registry):
    problems = _problems(registry, _rec("joback_properties"))

    assert any("hidden by default" in p for p in problems)


def test_a_calculator_that_needs_input_only_the_person_has_is_reported(registry):
    problems = _problems(registry, _rec("lewis_adduct"))

    assert any("partner_smiles" in p for p in problems)


def test_an_override_of_a_setting_that_does_not_exist_is_reported(registry):
    problems = _problems(registry, _rec("gasteiger_charge_at_ph", no_such_setting=1))

    assert any("unknown setting" in p for p in problems)


def test_an_override_outside_a_settings_range_is_reported(registry):
    problems = _problems(registry, _rec("gasteiger_charge_at_ph", pH=99.0))

    assert any("above" in p for p in problems)


def test_an_override_that_is_not_one_of_the_choices_is_reported(registry):
    problems = _problems(registry, _rec("mass_spectrum", ion="[M+Zz]+"), goal_id="identity")

    assert any("is not one of" in p for p in problems)


def test_a_valid_override_is_accepted(registry):
    assert _problems(registry, _rec("gasteiger_charge_at_ph", pH=6.0)) == []


def test_a_calculator_listed_twice_is_reported(registry):
    problems = _problems(registry, _rec("pka"), _rec("pka"), goal_id="solubility")

    assert any("listed twice" in p for p in problems)


def test_an_unknown_role_and_an_empty_reason_are_reported(registry):
    problems = _problems(registry, _rec("pka", role="mandatory", reason="  "), goal_id="solubility")

    assert any("unknown role" in p for p in problems)
    assert any("no reason" in p for p in problems)


def test_a_goal_that_is_not_a_task_group_is_reported(registry):
    assert any("not a task group" in p for p in _problems(registry, _rec("pka"), goal_id="nonsense"))
    assert any("not a task group" in p for p in _problems(registry, _rec("pka"), goal_id=FALLBACK_TASK_GROUP))


def test_a_goal_that_recommends_nothing_is_reported(registry):
    problems = _problems(registry, _rec("pka", role=OPTIONAL), goal_id="solubility")

    assert any("recommends nothing" in p for p in problems)


# --- a run is a value --------------------------------------------------------------------------


def _run(**overrides):
    values = dict(
        goal_id="charge",
        calculator_ids=["gasteiger_charge_at_ph", "dipole_moment"],
        parameters={"gasteiger_charge_at_ph": {"pH": 6.5}},
        scope_mode=SCOPE_THIS,
    )
    values.update(overrides)
    return GoalRun(**values)


def test_a_run_holds_tuples_and_read_only_mappings():
    run = _run()

    assert isinstance(run.calculator_ids, tuple)
    assert isinstance(run.scope_uuids, tuple)
    with pytest.raises(TypeError):
        run.parameters["gasteiger_charge_at_ph"]["pH"] = 1.0
    with pytest.raises(TypeError):
        run.parameters["dipole_moment"] = {}


def test_a_run_cannot_be_reassigned():
    run = _run()

    with pytest.raises(dataclasses.FrozenInstanceError):
        run.scope_mode = SCOPE_ALL


def test_changing_what_a_run_was_made_from_does_not_change_the_run():
    ids = ["gasteiger_charge_at_ph"]
    settings = {"gasteiger_charge_at_ph": {"pH": 6.5}}
    run = _run(calculator_ids=ids, parameters=settings)

    ids.append("dipole_moment")
    settings["gasteiger_charge_at_ph"]["pH"] = 1.0

    assert run.calculator_ids == ("gasteiger_charge_at_ph",)
    assert run.parameters["gasteiger_charge_at_ph"]["pH"] == 6.5


def test_a_second_run_has_its_own_id():
    assert _run().run_id != _run().run_id


def test_an_unknown_scope_is_refused():
    with pytest.raises(ValueError):
        _run(scope_mode="somewhere")


def test_the_chosen_parameters_are_a_plain_copy():
    run = _run()

    chosen = run.chosen_parameters()
    chosen["gasteiger_charge_at_ph"]["pH"] = 1.0

    assert run.parameters["gasteiger_charge_at_ph"]["pH"] == 6.5
    assert type(chosen) is dict and type(chosen["gasteiger_charge_at_ph"]) is dict


def test_the_scope_words_are_the_ones_properties_uses():
    from openchem.ui.panels import property_panel

    assert SCOPES == {SCOPE_THIS, SCOPE_ALL, SCOPE_CHOSEN}
    assert property_panel._SCOPE_THIS == SCOPE_THIS
    assert property_panel._SCOPE_ALL == SCOPE_ALL
    assert property_panel._SCOPE_CHOSEN == SCOPE_CHOSEN
