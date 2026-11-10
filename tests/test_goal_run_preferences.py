"""Goal-run settings: the resolver, the saved store, and the all-recommended list.

A direct Properties run is not in here. These choices apply only when a goal asks.
"""

from __future__ import annotations

import json
import logging

import pytest

from openchem.bootstrap import build_service_container
from openchem.domain.calculator_goals import RECOMMENDED, GOALS, Goal, Recommendation, goal_of
from openchem.domain.goal_run_preferences import (
    GOAL_PARAMETER_KEY,
    GoalParameterStore,
    chemistry_summary,
    confirmation_text,
    parameters_for_run,
    recommended_calculators,
    resolve_parameters,
)


@pytest.fixture
def services(qapp):
    return build_service_container()


def _nmr(services):
    return services.calculator_registry.get("nmr_database")


def test_spectra_recommends_1h_while_the_registration_stays_13c(services):
    entry = goal_of("spectra").entry("nmr_database")
    assert dict(entry.parameters) == {"nucleus": "1H"}
    nucleus = next(parameter for parameter in _nmr(services).parameters if parameter.name == "nucleus")
    assert nucleus.default == "13C"


def test_a_saved_choice_wins_over_the_recommendation(services):
    definition = _nmr(services)
    resolved = resolve_parameters(definition, {"nucleus": "1H"}, {"nucleus": "13C"})
    assert resolved["nucleus"] == "13C"
    assert parameters_for_run(definition, {"nucleus": "1H"}, {"nucleus": "13C"}) == {}


def test_the_recommendation_is_used_when_nothing_is_saved(services):
    definition = _nmr(services)
    assert resolve_parameters(definition, {"nucleus": "1H"}, {})["nucleus"] == "1H"
    assert parameters_for_run(definition, {"nucleus": "1H"}, {}) == {"nucleus": "1H"}


def test_an_invalid_stored_value_falls_through(services, caplog):
    definition = _nmr(services)
    with caplog.at_level(logging.INFO):
        resolved = resolve_parameters(
            definition,
            {"nucleus": "1H"},
            {"nucleus": "15N", "retired": True},
        )
    assert resolved["nucleus"] == "1H"
    assert "15N" in caplog.text and "retired" in caplog.text


def test_the_customise_line_names_the_chemistry_and_not_the_decimal_places(services):
    definition = services.calculator_registry.get("geometry_partial_charge")
    resolved = resolve_parameters(definition, {}, {})
    line = chemistry_summary(definition, resolved)
    assert "Decimal" not in line
    assert "EEM" in line or "Bultinck" in line
    nmr = chemistry_summary(_nmr(services), resolve_parameters(_nmr(services), {"nucleus": "1H"}, {}))
    assert "1H" in nmr
    assert "13C" not in nmr


def test_the_aggregate_lists_each_recommended_calculator_once_in_goal_order():
    found = recommended_calculators(GOALS)
    expected: list[str] = []
    for goal in GOALS:
        for entry in goal.recommended():
            if entry.calculator_id not in expected:
                expected.append(entry.calculator_id)
    assert list(found.calculator_ids) == expected
    assert found.conflict_id == ""
    assert len(found.calculator_ids) == len(set(found.calculator_ids))


def test_identical_recommendations_merge_and_different_ones_refuse():
    same = Recommendation("nmr_database", RECOMMENDED, "shifts", {"nucleus": "1H"})
    other = Recommendation("nmr_database", RECOMMENDED, "shifts", {"nucleus": "13C"})
    merged = recommended_calculators((
        Goal("spectra", "spectra", (same,)),
        Goal("again", "again", (same,)),
    ))
    assert merged.calculator_ids == ("nmr_database",)
    assert merged.conflict_id == ""

    refused = recommended_calculators((
        Goal("spectra", "spectra", (same,)),
        Goal("again", "again", (other,)),
    ))
    assert refused.calculator_ids == ()
    assert refused.conflict_id == "nmr_database"


def test_a_damaged_store_is_ignored_and_accept_is_what_saves():
    class _Settings:
        def __init__(self) -> None:
            self.values: dict[str, str] = {GOAL_PARAMETER_KEY: "{not json"}

        def get(self, key, default=""):
            return self.values.get(key, default)

        def set(self, key, value):
            self.values[key] = value

    settings = _Settings()
    store = GoalParameterStore.from_settings(settings)
    assert store.get("nmr_database") == {}
    store.remember("nmr_database", {"nucleus": "1H"})
    assert settings.values[GOAL_PARAMETER_KEY] == "{not json"
    store.save(settings)
    assert json.loads(settings.values[GOAL_PARAMETER_KEY]) == {"nmr_database": {"nucleus": "1H"}}


def test_the_confirmation_names_the_counts_the_conformers_and_the_exclusions():
    text = confirmation_text(
        calculator_count=30,
        job_count=30,
        molecule_count=1,
        conformer_names=["Partial charge"],
        lacking_conformers=1,
        exclusions="Left out: Oxygen balance (needs a density).",
    )
    assert "30 recommended calculators" in text
    assert "30 calculations on 1 molecule" in text
    assert "Partial charge" in text
    assert "have none yet" in text
    assert "Left out: Oxygen balance" in text
    assert "Nothing starts until you continue." in text
