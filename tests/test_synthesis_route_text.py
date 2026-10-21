"""The words the synthesis panel shows about a route (`plugins/synthesis_planner/route_text.py`): a field the planner did not give is "not provided", a number is named for what it is, and the checks are reported separately and never as a verdict on the chemistry."""

from __future__ import annotations

import pytest
from synthesis_planner import route_text as words

from openchem.domain.synthesis_route import Check, MappingStatus, Route, RouteMolecule, RouteStep, StockStatus, ValidationReport

T = "CC(=O)Oc1ccccc1C(=O)O"
A = "CC(=O)OC(C)=O"
B = "O=C(O)c1ccccc1O"


def route(**kw) -> Route:
    fields = {"target_smiles": T, "rank": 1, "steps": (RouteStep(product=T, reactants=(A, B)),), "starting_materials": (RouteMolecule(smiles=A, in_stock=True), RouteMolecule(smiles=B, in_stock=False))}
    fields.update(kw)
    return Route(**fields)


def test_a_title_counts_steps_and_starting_materials_and_names_the_score_as_the_planners():
    assert words.route_title(route()) == "Route 1: 1 step, 2 starting materials"
    assert words.route_title(route(rank=3, score=0.98765)) == "Route 3: 1 step, 2 starting materials, planner score 0.988"
    one = route(steps=(RouteStep(product=T, reactants=(A,)),), starting_materials=(RouteMolecule(smiles=A),))
    assert words.route_title(one) == "Route 1: 1 step, 1 starting material"
    two = route(steps=(RouteStep(product=B, reactants=("Oc1ccccc1",)), RouteStep(product=T, reactants=(A, B))), starting_materials=(RouteMolecule(smiles="Oc1ccccc1"), RouteMolecule(smiles=A)))
    assert words.route_title(two).startswith("Route 1: 2 steps, 2 starting materials")


def test_a_step_title_is_numbered_from_one_and_reads_reactants_then_product():
    step = RouteStep(product=T, reactants=(A, B))
    assert words.step_title(1, step) == f"Step 1: {A} + {B}  >>  {T}"
    assert words.step_title(4, step).startswith("Step 4: ")


def test_a_step_with_nothing_but_its_molecules_says_every_other_field_was_not_provided():
    text = words.step_text(RouteStep(product=T, reactants=(A, B)))
    assert text.splitlines() == [
        f"Makes: {T}", f"From: {A} + {B}", "Template: not provided", "Policy: not provided", "Policy probability: not provided",
        "Conditions, reagents and yield: not provided (the planner does not supply them).",
    ]


def test_the_policy_probability_is_the_models_score_and_never_a_yield_or_a_chance():
    text = words.step_text(RouteStep(product=T, reactants=(A, B), template_id="t7", policy_name="uspto", policy_probability=0.25))
    assert "Template: t7" in text and "Policy: uspto" in text
    assert "Policy probability: 0.25 (the model's score for this template, not a yield and not a chance that the step works)" in text
    zero = words.step_text(RouteStep(product=T, reactants=(A, B), policy_probability=0.0))
    assert "Policy probability: 0 (the model's score" in zero  # a real zero is a number, not "not provided"


def test_each_starting_material_says_whether_the_stock_lists_it_and_a_missing_flag_is_not_a_no():
    rows = words.starting_materials_text(route(starting_materials=(RouteMolecule(smiles=A, in_stock=True), RouteMolecule(smiles=B, in_stock=False)))).splitlines()
    assert rows == ["Starting materials:", f"  {A}   (in stock)", f"  {B}   (NOT in stock)"]
    unknown = words.starting_materials_text(route(starting_materials=(RouteMolecule(smiles=A), RouteMolecule(smiles=B))))
    assert unknown.count("stock status not provided") == 2 and "NOT in stock" not in unknown


def test_no_report_is_not_checked_and_a_report_gives_each_outcome_separately():
    assert words.validation_text(None) == "Internal consistency: not checked."
    report = ValidationReport(molecules=Check.PASS, reactions=Check.PASS, mapping=MappingStatus.PARTIAL, conservation=Check.NOT_ASSESSABLE, stock=StockStatus.SOME_NOT_IN_STOCK, diagnostics=("one reaction has an unmapped product atom",), missing=("template ids",))
    lines = words.validation_text(report).splitlines()
    assert lines[0] == "Internal consistency (the route's own bookkeeping, not the chemistry):"
    assert lines[1:6] == ["  molecules parse: passed", "  reactions parse: passed", "  atom mapping: partial", "  atoms conserved: could not be assessed", "  starting materials: some NOT in stock"]
    assert "  one reaction has an unmapped product atom" in lines and "  missing: template ids" in lines


@pytest.mark.parametrize("check,word", [(Check.PASS, "passed"), (Check.FAIL, "FAILED"), (Check.NOT_ASSESSABLE, "could not be assessed")])
def test_a_failed_check_is_said_loudly_and_a_check_that_could_not_be_made_is_neither_a_pass_nor_a_fail(check, word):
    report = ValidationReport(molecules=check, reactions=Check.PASS, mapping=MappingStatus.ABSENT, conservation=Check.NOT_ASSESSABLE, stock=StockStatus.NOT_PROVIDED)
    assert f"molecules parse: {word}" in words.validation_text(report) and "starting materials: not provided" in words.validation_text(report)


def test_the_route_text_is_where_it_begins_and_how_it_was_checked_and_never_says_validated_or_recommended():
    text = words.route_text(route())
    assert text.startswith("Starting materials:") and "Internal consistency: not checked." in text
    for forbidden in ("validated", "recommended", "best route", "will work", "feasible"):
        assert forbidden not in text.lower()


# --- regulatory alerts on the molecules of a route ---------------------------------------------------------------------------


def _set(route_obj: Route, node_screenings=()):
    from openchem.domain.synthesis_route import PlannerIdentity, RouteSet, RouteStatus, TargetIdentity

    return RouteSet(status=RouteStatus.FOUND, target=TargetIdentity(molecule_uuid="u", canonical_smiles=T, fingerprint="f"), planner=PlannerIdentity(planner="AiZynthFinder", version="4.4.1"), routes=(route_obj,), node_screenings=node_screenings)


def _clean(smiles: str):
    from openchem.domain.synthesis_gate import NodeScreening

    return NodeScreening(smiles=smiles, screened=True, rulesets_consulted=("cwc-schedule-1", "dea-listed-chemicals"), screened_on="2026-10-21")


def _alert(smiles: str, *, mine: bool = False):
    from openchem.domain.synthesis_gate import AlertFinding, NodeScreening

    finding = AlertFinding(ruleset_id="lab-policy" if mine else "osha-table-z1", rule_id="rule-9", display_name="a listed substance", domain="occupational_exposure", jurisdiction="united_states", section="Table Z-1", confidence="exact", user_supplied=mine)
    return NodeScreening(smiles=smiles, screened=True, findings=(finding,), rulesets_consulted=("osha-table-z1",), screened_on="2026-10-21")


def _unscreened(smiles: str):
    from openchem.domain.synthesis_gate import NodeScreening

    return NodeScreening(smiles=smiles, screened=False, reason="the screen failed (X)")


def test_a_set_nobody_screened_says_only_that_and_its_titles_carry_no_alert_words():
    unscreened = _set(route())
    assert words.alerts_text(unscreened, unscreened.routes[0]) == "Regulatory alerts: not checked."
    assert words.route_title(unscreened.routes[0], unscreened) == "Route 1: 1 step, 2 starting materials"


def test_a_route_with_alerts_counts_the_molecules_that_carry_one_and_a_clean_route_says_nothing_about_alerts():
    base = route()
    clean = _set(base, tuple(_clean(s) for s in (T, A, B)))
    assert words.route_title(base, clean) == "Route 1: 1 step, 2 starting materials"  # no alert is not written as a good sign
    flagged = _set(base, (_alert(T), _alert(A), _clean(B)))
    assert words.route_title(base, flagged) == "Route 1: 1 step, 2 starting materials, 2 molecules with a regulatory alert"
    assert words.route_title(base, _set(base, (_alert(T), _clean(A), _clean(B)))).endswith(", 1 molecule with a regulatory alert")


def test_a_molecule_that_could_not_be_screened_is_said_in_the_title_and_never_counted_as_clean():
    mixed = _set(route(), (_clean(T), _unscreened(A), _clean(B)))
    assert words.route_title(mixed.routes[0], mixed).endswith(", some molecules not screened")
    assert "regulatory alert" not in words.route_title(mixed.routes[0], mixed)
    text = words.alerts_text(mixed, mixed.routes[0])
    assert f"  {A}: could not be screened: the screen failed (X)" in text.splitlines()
    # the claim is only about the molecules that were screened, never "no molecule matched" while one could not be
    assert "  none of the molecules that could be screened matched a rule in: cwc-schedule-1, dea-listed-chemicals." in text.splitlines()
    assert not any(line.startswith("  no molecule of this route") for line in text.splitlines())


def test_an_alert_names_what_matched_where_and_whose_ruleset_it_is_and_calls_itself_a_listing():
    both = _set(route(), (_alert(T), _alert(B, mine=True), _clean(A)))
    text = words.alerts_text(both, both.routes[0])
    lines = text.splitlines()
    assert lines[0] == "Regulatory alerts (a listing in a ruleset, not a legal determination; no alert does not mean nothing applies):"
    assert f"  {T}   (the target)" in lines and f"  {B}   (a starting material)" in lines and f"  {A}   (a starting material)" not in lines
    assert "    - a listed substance   [rule-9; osha-table-z1; occupational_exposure; united_states, Table Z-1; confidence: exact]" in lines
    assert "    - a listed substance   [rule-9; lab-policy, your own ruleset; occupational_exposure; united_states, Table Z-1; confidence: exact]" in lines
    assert not any("no molecule of this route matched" in line for line in lines)


def test_an_intermediate_is_named_as_one():
    two = Route(target_smiles=T, rank=1, steps=(RouteStep(product=B, reactants=("Oc1ccccc1", "O=C=O")), RouteStep(product=T, reactants=(A, B))), starting_materials=(RouteMolecule(smiles="Oc1ccccc1", in_stock=True), RouteMolecule(smiles="O=C=O", in_stock=True), RouteMolecule(smiles=A, in_stock=True)))
    screened = _set(two, tuple(_alert(s) if s == B else _clean(s) for s in (T, B, "Oc1ccccc1", "O=C=O", A)))
    assert f"  {B}   (an intermediate)" in words.alerts_text(screened, two).splitlines()


def test_when_nothing_matched_the_text_names_the_rulesets_it_asked_and_does_not_claim_more():
    clean = _set(route(), tuple(_clean(s) for s in (T, A, B)))
    last = words.alerts_text(clean, clean.routes[0]).splitlines()[-1]
    assert last == "  no molecule of this route matched a rule in: cwc-schedule-1, dea-listed-chemicals."
    assert "safe" not in words.alerts_text(clean, clean.routes[0]).lower()
