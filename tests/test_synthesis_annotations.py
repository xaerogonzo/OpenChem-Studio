"""The per-molecule regulatory annotations of a plan (Stage 1 slice 6): `RouteSet.node_screenings`, `chem.synthesis_gate.annotate_route_set` and the planning service that applies it.

An alert is a screening of a molecule and NEVER takes a route away; a molecule that could not be screened says so, and a missing screening is never read as "nothing matched"."""

from __future__ import annotations

import dataclasses

import pytest
from test_synthesis_gate import ASPIRIN, ETHANOL, SARIN

from openchem.chem import synthesis_gate as gate
from openchem.domain.synthesis_gate import AlertFinding, NodeScreening
from openchem.domain.synthesis_route import (
    ALERTS_NOT_CHECKED,
    SOME_NOT_SCREENED,
    STANDARD_LIMITATIONS,
    PlannerIdentity,
    Route,
    RouteMolecule,
    RouteSet,
    RouteStatus,
    RouteStep,
    TargetIdentity,
    route_molecules,
)

TARGET = TargetIdentity(molecule_uuid="u", canonical_smiles=ASPIRIN, fingerprint="f")
PLANNER = PlannerIdentity(planner="AiZynthFinder", version="4.4.1")
ANHYDRIDE = "CC(=O)OC(C)=O"
SALICYLIC = "O=C(O)c1ccccc1O"
PHENOL = "Oc1ccccc1"


def two_step_route(rank: int = 1) -> Route:
    """Phenol to salicylic acid to aspirin: an intermediate, three starting materials besides the target."""
    return Route(
        target_smiles=ASPIRIN, rank=rank,
        steps=(RouteStep(product=SALICYLIC, reactants=(PHENOL, "O=C=O")), RouteStep(product=ASPIRIN, reactants=(ANHYDRIDE, SALICYLIC))),
        starting_materials=(RouteMolecule(smiles=PHENOL, in_stock=True), RouteMolecule(smiles="O=C=O", in_stock=True), RouteMolecule(smiles=ANHYDRIDE, in_stock=True)),
    )


def found(*routes: Route, **kw) -> RouteSet:
    return RouteSet(status=RouteStatus.FOUND, target=TARGET, planner=PLANNER, routes=routes or (two_step_route(),), **kw)


def screened(smiles: str, *, alert: bool = False) -> NodeScreening:
    findings = (AlertFinding(ruleset_id="r", rule_id="rule-1", display_name="a rule", domain="d", jurisdiction="j"),) if alert else ()
    return NodeScreening(smiles=smiles, screened=True, findings=findings, rulesets_consulted=("r",), screened_on="2026-10-21")


def unscreened(smiles: str) -> NodeScreening:
    return NodeScreening(smiles=smiles, screened=False, reason="the screen failed (X)")


def every_molecule(route_set: RouteSet, make=screened) -> tuple[NodeScreening, ...]:
    return tuple(make(smiles) for smiles in dict.fromkeys(m for route in route_set.routes for m in route_molecules(route)))


# --- the domain ---------------------------------------------------------------------------------------------------------


def test_a_routes_molecules_are_the_target_each_step_and_the_starting_materials_each_once_in_the_order_run():
    route = two_step_route()
    assert route_molecules(route) == (ASPIRIN, SALICYLIC, PHENOL, "O=C=O", ANHYDRIDE)
    assert len(route_molecules(route)) == len(set(route_molecules(route)))


def test_screenings_must_be_exactly_the_molecules_of_the_routes_each_once():
    base = found()
    complete = every_molecule(base)
    assert dataclasses.replace(base, node_screenings=complete).node_screenings == complete
    for wrong in (complete[:-1], complete + (screened("CCO"),), complete + (complete[0],), (screened("CCO"),)):
        with pytest.raises(ValueError, match="exactly the molecules"):
            dataclasses.replace(base, node_screenings=wrong)


def test_only_a_found_set_can_carry_screenings():
    with pytest.raises(ValueError, match="carries no routes to screen"):
        RouteSet(status=RouteStatus.NO_ROUTE, target=TARGET, planner=PLANNER, node_screenings=(screened("CCO"),))


def test_a_set_nobody_has_screened_says_so_and_never_reads_as_nothing_matched():
    base = found()
    assert ALERTS_NOT_CHECKED in base.all_limitations() and base.screenings_for(base.routes[0]) == () and base.alert_count(base.routes[0]) == 0
    assert RouteSet(status=RouteStatus.NO_ROUTE, target=TARGET, planner=PLANNER).all_limitations() == STANDARD_LIMITATIONS  # nothing to screen, so nothing to say


def test_a_screened_set_drops_the_not_checked_sentence_and_a_molecule_that_could_not_be_screened_adds_its_own():
    base = found()
    clean = dataclasses.replace(base, node_screenings=every_molecule(base))
    assert ALERTS_NOT_CHECKED not in clean.all_limitations() and SOME_NOT_SCREENED not in clean.all_limitations()
    partly = dataclasses.replace(base, node_screenings=tuple(unscreened(s.smiles) if s.smiles == PHENOL else s for s in every_molecule(base)))
    assert SOME_NOT_SCREENED in partly.all_limitations() and ALERTS_NOT_CHECKED not in partly.all_limitations()


def test_the_screenings_of_a_route_follow_its_molecules_and_the_alert_count_counts_only_alerts():
    base = found()
    marked = tuple(screened(s.smiles, alert=s.smiles in (SALICYLIC, ANHYDRIDE)) for s in every_molecule(base))
    annotated = dataclasses.replace(base, node_screenings=marked)
    route = annotated.routes[0]
    assert [s.smiles for s in annotated.screenings_for(route)] == list(route_molecules(route))
    assert annotated.alert_count(route) == 2


def test_screenings_are_shared_between_routes_that_share_a_molecule():
    one, two = two_step_route(1), Route(target_smiles=ASPIRIN, rank=2, steps=(RouteStep(product=ASPIRIN, reactants=(ANHYDRIDE, SALICYLIC)),), starting_materials=(RouteMolecule(smiles=ANHYDRIDE, in_stock=True), RouteMolecule(smiles=SALICYLIC, in_stock=True)))
    base = found(one, two)
    annotated = dataclasses.replace(base, node_screenings=tuple(screened(s.smiles, alert=s.smiles == ANHYDRIDE) for s in every_molecule(base)))
    assert annotated.alert_count(one) == 1 and annotated.alert_count(two) == 1
    assert len(annotated.node_screenings) == len(set(m for r in (one, two) for m in route_molecules(r)))


# --- annotate_route_set ----------------------------------------------------------------------------------------------------


def test_a_set_with_no_routes_is_returned_as_it_is():
    nothing = RouteSet(status=RouteStatus.NO_ROUTE, target=TARGET, planner=PLANNER)
    assert gate.annotate_route_set(nothing, screen=lambda molecules: pytest.fail("nothing to screen")) is nothing


def test_every_distinct_molecule_is_screened_once_and_the_routes_are_untouched():
    asked = []

    def screen(molecules):
        asked.append(tuple(molecules))
        return tuple(screened(s) for s in molecules)

    base = found(two_step_route(1), two_step_route(2))
    result = gate.annotate_route_set(base, screen=screen)

    assert asked == [route_molecules(base.routes[0])] and result.routes == base.routes and result.status is RouteStatus.FOUND
    assert [s.smiles for s in result.node_screenings] == list(route_molecules(base.routes[0]))


def test_an_alert_flags_the_molecule_and_never_removes_or_refuses_the_route():
    route = Route(target_smiles=ETHANOL, rank=1, steps=(RouteStep(product=ETHANOL, reactants=(SARIN,)),), starting_materials=(RouteMolecule(smiles=SARIN, in_stock=True),))
    base = RouteSet(status=RouteStatus.FOUND, target=TargetIdentity(molecule_uuid="u", canonical_smiles=ETHANOL, fingerprint="f"), planner=PLANNER, routes=(route,))

    result = gate.annotate_route_set(base)  # the real shared engine

    assert result.status is RouteStatus.FOUND and result.routes == base.routes  # shown, not refused
    flagged = {s.smiles: s for s in result.node_screenings}
    assert flagged[SARIN].screened and flagged[SARIN].has_alert and "cwc-schedule-1" in {f.ruleset_id for f in flagged[SARIN].findings}
    # the match belongs to the molecule it is about: the common solvent in the same route carries no Schedule 1 finding (it may carry others: an alert is any listing, and the wider rulesets include exposure limits)
    assert flagged[ETHANOL].screened and "cwc-schedule-1" not in {f.ruleset_id for f in flagged[ETHANOL].findings}


def test_a_real_plan_of_ordinary_molecules_is_screened_and_none_is_mistaken_for_the_gates_list():
    result = gate.annotate_route_set(found())
    assert all(s.screened for s in result.node_screenings) and len(result.node_screenings) == 5
    assert not any(f.ruleset_id == "cwc-schedule-1" for s in result.node_screenings for f in s.findings)
    assert ALERTS_NOT_CHECKED not in result.all_limitations()  # it was asked, whatever the answer


def test_a_screen_that_raises_keeps_the_plan_and_marks_every_molecule_unscreened_with_the_reason():
    def boom(molecules):
        raise RuntimeError("no engine")

    base = found()
    result = gate.annotate_route_set(base, screen=boom)

    assert result.routes == base.routes and len(result.node_screenings) == len(route_molecules(base.routes[0]))
    assert all(not s.screened and s.reason == "the screen could not be run (RuntimeError)" for s in result.node_screenings)
    assert SOME_NOT_SCREENED in result.all_limitations()


def test_a_screen_that_answers_for_the_wrong_molecules_is_a_failed_screen_not_a_wrong_annotation():
    result = gate.annotate_route_set(found(), screen=lambda molecules: (screened("CCO"),))
    assert all(not s.screened for s in result.node_screenings) and {s.smiles for s in result.node_screenings} == set(route_molecules(result.routes[0]))


# --- the planning service applies it ---------------------------------------------------------------------------------------


def _service_world(runner, annotator=None):
    from openchem.chem.aizynth_planner import PlannerSetup
    from openchem.domain.synthesis_gate import GateDecision, GateOutcome
    from openchem.events.base import EventBus
    from openchem.events.events import SynthesisRouteReady
    from openchem.services.synthesis_planner_setup import DEFAULT_LIMITS
    from openchem.services.synthesis_planning_service import SynthesisPlanningService

    bus = EventBus()
    ready: list = []
    bus.subscribe(SynthesisRouteReady, ready.append)
    setup = PlannerSetup(python="p", config={"stock": {"zinc": "z"}}, stock="zinc", expansion="uspto", filter=None, limits=DEFAULT_LIMITS)
    allowed = GateDecision(outcome=GateOutcome.ALLOWED, ruleset_version="1", ruleset_sha256="x", screened_on="today")
    extra = {} if annotator is None else {"annotator": annotator}
    service = SynthesisPlanningService(bus, setup_provider=lambda: setup, runner=runner, gate=lambda smiles: allowed, **extra)
    return service, ready


def _plan_and_wait(qapp, service, ready) -> RouteSet:
    import time

    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.molecule import MoleculeModel

    model = MoleculeModel(display_name="target")
    ChemistryEngine().set_structure_from_smiles(model, ASPIRIN)
    assert service.request_plan(model) .value == "started"
    end = time.monotonic() + 20
    while not ready and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    service.shutdown()
    assert ready, "the plan never finished"
    return ready[0].route_set


def test_a_found_plan_is_annotated_before_it_is_stored_and_announced(qapp):
    def runner(request, target, **kw):
        return RouteSet(status=RouteStatus.FOUND, target=target, planner=PLANNER, routes=(two_step_route(),))

    service, ready = _service_world(runner)
    announced = _plan_and_wait(qapp, service, ready)

    assert len(announced.node_screenings) == 5 and all(s.screened for s in announced.node_screenings)
    assert ALERTS_NOT_CHECKED not in announced.all_limitations()


def test_a_plan_that_found_nothing_is_stored_as_it_is(qapp):
    def runner(request, target, **kw):
        return RouteSet(status=RouteStatus.NO_ROUTE, target=target, planner=PLANNER)

    service, ready = _service_world(runner)
    assert _plan_and_wait(qapp, service, ready).node_screenings == ()


def test_an_annotator_that_raises_loses_nothing_and_the_plan_says_its_molecules_were_not_checked(qapp):
    def runner(request, target, **kw):
        return RouteSet(status=RouteStatus.FOUND, target=target, planner=PLANNER, routes=(two_step_route(),))

    def boom(route_set):
        raise RuntimeError("annotator broke")

    service, ready = _service_world(runner, annotator=boom)
    announced = _plan_and_wait(qapp, service, ready)

    assert announced.status is RouteStatus.FOUND and announced.routes[0] == two_step_route()
    assert announced.node_screenings == () and ALERTS_NOT_CHECKED in announced.all_limitations()
