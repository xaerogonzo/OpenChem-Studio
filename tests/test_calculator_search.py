"""The one rule for "which calculators match these words", shared by the launcher and the assistant."""

from __future__ import annotations

from openchem.bootstrap import build_service_container
from openchem.domain import calculator_search
from openchem.domain.calculator import CalculatorDefinition, RegistryExecution


def _definition(calculator_id, name, category="charge", description="", tags=None):
    return CalculatorDefinition(
        calculator_id=calculator_id, display_name=name, category=category, description=description,
        execution=RegistryExecution(compute=lambda mol, uuid, params: None), tags=tags,
    )


def _pool():
    return [
        _definition("a", "Lewis Adduct", "lewis", "Will this acid bind this base", ["hsab"]),
        _definition("b", "Lewis Sites", "lewis", "Where a molecule can accept or donate"),
        _definition("c", "Dipole Moment", "charge", "How polar it is", ["polarity"]),
    ]


def test_every_word_must_appear_in_any_order_and_case():
    pool = _pool()
    assert [d.calculator_id for d in calculator_search.search(pool, "lewis adduct")] == ["a"]
    assert [d.calculator_id for d in calculator_search.search(pool, "ADDUCT lewis")] == ["a"]
    assert [d.calculator_id for d in calculator_search.search(pool, "lewis")] == ["a", "b"]


def test_name_description_heading_and_tags_are_all_searched():
    pool = _pool()
    for query, expected in [("dipole", ["c"]), ("polar", ["c"]), ("hsab", ["a"]), ("accept", ["b"])]:
        assert [d.calculator_id for d in calculator_search.search(pool, query)] == expected, query


def test_an_empty_or_blank_query_matches_everything_and_a_miss_matches_nothing():
    pool = _pool()
    assert len(calculator_search.search(pool, "")) == 3
    assert len(calculator_search.search(pool, "   ")) == 3
    assert calculator_search.search(pool, "zzzz") == []
    # one word that matches and one that does not is not a partial match
    assert calculator_search.search(pool, "lewis zzzz") == []


def test_a_calculator_with_no_tags_is_still_searchable():
    assert calculator_search.matches(_definition("x", "Plain", tags=None), "plain")


def test_the_order_is_the_browse_order_and_does_not_depend_on_the_order_given():
    pool = _pool()
    forward = [d.calculator_id for d in calculator_search.search(pool, "")]
    backward = [d.calculator_id for d in calculator_search.search(list(reversed(pool)), "")]
    assert forward == backward


def test_limit_truncates_after_ordering_and_a_negative_one_returns_nothing():
    pool = _pool()
    assert len(calculator_search.search(pool, "", limit=2)) == 2
    assert calculator_search.search(pool, "", limit=0) == []
    assert calculator_search.search(pool, "", limit=-3) == []


def test_it_finds_real_calculators_by_the_words_a_person_would_use():
    registry = build_service_container().calculator_registry
    found = {d.calculator_id for d in calculator_search.search(registry._definitions.values(), "adduct")}
    assert "lewis_adduct" in found
    assert {d.calculator_id for d in calculator_search.search(registry._definitions.values(), "pka")} >= {"pka"}


def test_the_launchers_find_box_uses_this_rule(qapp):
    """Two words, in an order no calculator's text has them: the old whole-phrase substring
    would have found nothing, so a match here shows the launcher delegates to the shared rule."""
    from test_task_groups import _find_panel

    panel = _find_panel(qapp)
    panel._find_box.setText("polarity beta")
    assert {cid for cid, row in panel._calculator_rows.items() if not row.isHidden()} == {"beta_calc"}
