"""The synthesis route domain (`openchem.domain.synthesis_route`): what a route must be, how a result says it ended, and that
nothing the planner did not supply is invented. Pure; no planner, no RDKit.

The last class builds routes from the REAL planner output saved by the Stage 0 spike (`benchmarks/synthesis/fixtures/`), so
the shape rules are checked against what a planner actually returns and not only against hand-made trees.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from openchem.domain.synthesis_route import (
    ALERTS_NOT_CHECKED,
    LIMITS_NOT_EXHAUSTIVE,
    NOT_PROVIDED,
    STANDARD_LIMITATIONS,
    Check,
    MappingStatus,
    PlannerIdentity,
    Route,
    RouteMolecule,
    RouteSet,
    RouteStatus,
    RouteStep,
    SearchLimits,
    SearchStatistics,
    SearchTermination,
    StockStatus,
    TargetIdentity,
    ValidationReport,
    forward_order,
    read_termination,
    shown,
)

FIXTURES = Path(__file__).resolve().parents[1] / "benchmarks" / "synthesis" / "fixtures"

TARGET = TargetIdentity(molecule_uuid="u-1", canonical_smiles="CC(=O)Oc1ccccc1C(=O)O", fingerprint="fp-1")
PLANNER = PlannerIdentity(planner="AiZynthFinder", version="4.4.1", model_identity=(("expansion", "uspto"),))


def step(product: str, *reactants: str, **kw) -> RouteStep:
    return RouteStep(product=product, reactants=tuple(reactants), **kw)


def two_step_route(**kw) -> Route:
    """T made from I and C; I made from A and B. Forward order: I first."""
    return Route(
        target_smiles="T",
        steps=(step("I", "A", "B"), step("T", "I", "C")),
        starting_materials=(RouteMolecule(smiles="A", in_stock=True), RouteMolecule(smiles="B", in_stock=True), RouteMolecule(smiles="C", in_stock=True)),
        rank=kw.pop("rank", 1),
        **kw,
    )


def good_validation() -> ValidationReport:
    return ValidationReport(molecules=Check.PASS, reactions=Check.PASS, mapping=MappingStatus.COMPLETE, conservation=Check.PASS, stock=StockStatus.ALL_IN_STOCK)


def found(*routes: Route, **kw) -> RouteSet:
    return RouteSet(status=RouteStatus.FOUND, target=TARGET, planner=PLANNER, routes=routes, **kw)


class TestNotProvided:
    def test_none_is_worded_never_blank_or_zero(self):
        assert shown(None) == NOT_PROVIDED
        assert shown(0.0) == "0.0"
        assert shown("") == ""

    def test_a_step_defaults_to_nothing_supplied(self):
        s = step("P", "R")
        assert s.reaction_smiles is None and s.template_id is None and s.policy_probability is None


class TestLimitsAndStatistics:
    @pytest.mark.parametrize("kw", [{"iteration_limit": 0}, {"iteration_limit": -1}, {"iteration_limit": True}, {"max_transforms": 0}, {"time_limit_seconds": 0}, {"time_limit_seconds": math.nan}, {"time_limit_seconds": math.inf}])
    def test_bad_limits_are_refused(self, kw):
        with pytest.raises(ValueError):
            SearchLimits(**kw)

    @pytest.mark.parametrize("kw", [{"iterations": -1}, {"iterations": True}, {"nodes": 1.5}, {"search_seconds": -0.1}, {"search_seconds": math.nan}, {"solved_routes": -3}])
    def test_bad_counters_are_refused(self, kw):
        with pytest.raises(ValueError):
            SearchStatistics(**kw)

    def test_zero_iterations_is_a_real_counter(self):
        assert SearchStatistics(iterations=0, search_seconds=0.0).iterations == 0


class TestReadTermination:
    LIMITS = SearchLimits(iteration_limit=500, time_limit_seconds=1800.0)

    def test_iterations_at_the_limit(self):
        assert read_termination(self.LIMITS, SearchStatistics(iterations=500, search_seconds=30.0)) is SearchTermination.ITERATION_LIMIT

    def test_time_at_the_limit(self):
        assert read_termination(self.LIMITS, SearchStatistics(iterations=120, search_seconds=1800.0)) is SearchTermination.TIME_LIMIT

    def test_both_reached_reads_as_the_iteration_limit(self):
        assert read_termination(self.LIMITS, SearchStatistics(iterations=500, search_seconds=1900.0)) is SearchTermination.ITERATION_LIMIT

    def test_fewer_iterations_is_unknown_never_completed(self):
        # A tree that ran out of nodes and one a stop signal cut short look the same; "completed" is a claim nobody made.
        assert read_termination(self.LIMITS, SearchStatistics(iterations=499, search_seconds=10.0)) is SearchTermination.UNKNOWN

    def test_missing_numbers_or_limits_are_unknown(self):
        assert read_termination(self.LIMITS, SearchStatistics()) is SearchTermination.UNKNOWN
        assert read_termination(SearchLimits(), SearchStatistics(iterations=10**6, search_seconds=10**6)) is SearchTermination.UNKNOWN


class TestRouteStep:
    @pytest.mark.parametrize("kw", [{"product": " "}, {"product": ""}])
    def test_blank_product(self, kw):
        with pytest.raises(ValueError):
            RouteStep(reactants=("R",), **kw)

    def test_a_step_consumes_something(self):
        with pytest.raises(ValueError):
            RouteStep(product="P", reactants=())

    def test_blank_reactant(self):
        with pytest.raises(ValueError):
            step("P", "R", " ")

    @pytest.mark.parametrize("p", [-0.01, 1.01, math.nan, math.inf, True])
    def test_probability_must_be_a_number_from_0_to_1(self, p):
        with pytest.raises(ValueError):
            step("P", "R", policy_probability=p)

    @pytest.mark.parametrize("p", [0.0, 0.5, 1.0])
    def test_probability_edges_are_allowed(self, p):
        assert step("P", "R", policy_probability=p).policy_probability == p

    @pytest.mark.parametrize("field", ["reaction_smiles", "template_id", "policy_name"])
    def test_a_supplied_text_field_is_not_blank(self, field):
        with pytest.raises(ValueError):
            step("P", "R", **{field: "  "})


class TestRouteShape:
    def test_a_two_step_route(self):
        r = two_step_route()
        assert r.length == 2 and r.steps[-1].product == "T"

    def test_no_steps_is_not_a_route(self):
        with pytest.raises(ValueError, match="at least one step"):
            Route(target_smiles="T", steps=(), starting_materials=(), rank=1)

    def test_rank_starts_at_one(self):
        for bad in (0, -1, True):
            with pytest.raises(ValueError):
                two_step_route(rank=bad)

    def test_score_must_be_finite(self):
        with pytest.raises(ValueError):
            two_step_route(score=math.nan)
        assert two_step_route(score=0.99).score == 0.99

    def test_steps_in_backward_order_are_refused(self):
        with pytest.raises(ValueError, match="forward order"):
            Route(target_smiles="T", steps=(step("T", "I", "C"), step("I", "A", "B")), starting_materials=(RouteMolecule(smiles="A"), RouteMolecule(smiles="B"), RouteMolecule(smiles="C")), rank=1)

    def test_a_middle_step_listed_before_the_step_that_makes_its_reactant(self):
        # The last step does make the target, so only the per-step order check can catch this one.
        steps = (step("J", "I", "B"), step("I", "A"), step("T", "I", "J"))
        with pytest.raises(ValueError, match="forward order"):
            Route(target_smiles="T", steps=steps, starting_materials=(RouteMolecule(smiles="A"), RouteMolecule(smiles="B")), rank=1)

    def test_last_step_must_make_the_target(self):
        with pytest.raises(ValueError):
            # Both steps lead to T, but T's step is listed first.
            Route(target_smiles="T", steps=(step("T", "I"), step("I", "A")), starting_materials=(RouteMolecule(smiles="A"),), rank=1)

    def test_nothing_makes_the_target(self):
        with pytest.raises(ValueError, match="makes the target"):
            Route(target_smiles="T", steps=(step("X", "A"),), starting_materials=(RouteMolecule(smiles="A"),), rank=1)

    def test_two_steps_making_one_molecule(self):
        with pytest.raises(ValueError, match="same molecule"):
            Route(target_smiles="T", steps=(step("T", "A"), step("T", "B")), starting_materials=(RouteMolecule(smiles="A"), RouteMolecule(smiles="B")), rank=1)

    def test_a_step_the_target_does_not_lead_to(self):
        with pytest.raises(ValueError, match="lead to the target"):
            Route(target_smiles="T", steps=(step("X", "A"), step("T", "B")), starting_materials=(RouteMolecule(smiles="A"), RouteMolecule(smiles="B")), rank=1)

    def test_a_cycle(self):
        with pytest.raises(ValueError, match="cycle"):
            Route(target_smiles="T", steps=(step("I", "T"), step("T", "I")), starting_materials=(), rank=1)

    def test_starting_materials_must_be_exactly_the_unmade_reactants(self):
        base = dict(target_smiles="T", steps=(step("I", "A", "B"), step("T", "I", "C")), rank=1)
        missing = (RouteMolecule(smiles="A"), RouteMolecule(smiles="B"))
        extra = (RouteMolecule(smiles="A"), RouteMolecule(smiles="B"), RouteMolecule(smiles="C"), RouteMolecule(smiles="D"))
        repeated = (RouteMolecule(smiles="A"), RouteMolecule(smiles="B"), RouteMolecule(smiles="C"), RouteMolecule(smiles="C"))
        made = (RouteMolecule(smiles="A"), RouteMolecule(smiles="B"), RouteMolecule(smiles="C"), RouteMolecule(smiles="I"))
        for bad in (missing, extra, repeated, made):
            with pytest.raises(ValueError, match="starting materials"):
                Route(starting_materials=bad, **base)

    def test_an_intermediate_used_twice_is_one_step_before_both_users(self):
        # I is consumed by J and by T; it is made once, and must precede both.
        steps = (step("I", "A"), step("J", "I", "B"), step("T", "I", "J"))
        r = Route(target_smiles="T", steps=steps, starting_materials=(RouteMolecule(smiles="A"), RouteMolecule(smiles="B")), rank=1)
        assert [s.product for s in r.steps] == ["I", "J", "T"]

    def test_a_molecule_listed_twice_among_a_steps_reactants_is_allowed(self):
        r = Route(target_smiles="T", steps=(step("T", "A", "A"),), starting_materials=(RouteMolecule(smiles="A"),), rank=1)
        assert r.length == 1

    def test_a_stock_flag_may_be_unknown(self):
        assert RouteMolecule(smiles="A").in_stock is None


class TestForwardOrder:
    def test_sorts_farthest_from_the_target_first(self):
        steps = [step("T", "I", "C"), step("I", "J"), step("J", "A")]
        ordered = forward_order(steps, "T")
        assert [s.product for s in ordered] == ["J", "I", "T"]

    def test_ties_keep_the_planners_order(self):
        steps = [step("T", "X", "Y"), step("Y", "A"), step("X", "B")]
        assert [s.product for s in forward_order(steps, "T")] == ["Y", "X", "T"]
        steps = [step("T", "X", "Y"), step("X", "B"), step("Y", "A")]
        assert [s.product for s in forward_order(steps, "T")] == ["X", "Y", "T"]

    def test_a_shared_intermediate_goes_before_its_deepest_user(self):
        steps = [step("T", "I", "J"), step("J", "I", "B"), step("I", "A")]
        assert [s.product for s in forward_order(steps, "T")] == ["I", "J", "T"]

    def test_refuses_what_is_not_rooted_at_the_target(self):
        with pytest.raises(ValueError):
            forward_order([step("X", "A")], "T")


class TestValidationReport:
    def test_fully_validated_needs_each_of_the_four(self):
        assert good_validation().fully_validated
        for change in (
            {"molecules": Check.FAIL},
            {"reactions": Check.FAIL},
            {"reactions": Check.NOT_ASSESSABLE},
            {"mapping": MappingStatus.PARTIAL, "conservation": Check.NOT_ASSESSABLE},
            {"conservation": Check.FAIL},
            {"conservation": Check.NOT_ASSESSABLE},
        ):
            base = dict(molecules=Check.PASS, reactions=Check.PASS, mapping=MappingStatus.COMPLETE, conservation=Check.PASS, stock=StockStatus.ALL_IN_STOCK)
            base.update(change)
            assert not ValidationReport(**base).fully_validated, change

    def test_stock_does_not_decide_validity(self):
        r = ValidationReport(molecules=Check.PASS, reactions=Check.PASS, mapping=MappingStatus.COMPLETE, conservation=Check.PASS, stock=StockStatus.SOME_NOT_IN_STOCK)
        assert r.fully_validated

    @pytest.mark.parametrize("mapping", [MappingStatus.PARTIAL, MappingStatus.ABSENT])
    @pytest.mark.parametrize("conservation", [Check.PASS, Check.FAIL])
    def test_conservation_is_never_asserted_without_a_complete_mapping(self, mapping, conservation):
        with pytest.raises(ValueError):
            ValidationReport(molecules=Check.PASS, reactions=Check.PASS, mapping=mapping, conservation=conservation, stock=StockStatus.NOT_PROVIDED)

    def test_negative_unmapped_atoms(self):
        with pytest.raises(ValueError):
            ValidationReport(molecules=Check.PASS, reactions=Check.PASS, mapping=MappingStatus.COMPLETE, conservation=Check.PASS, stock=StockStatus.NOT_PROVIDED, unmapped_right_atoms=-1)


class TestIdentities:
    def test_blank_identities_are_refused(self):
        with pytest.raises(ValueError):
            TargetIdentity(molecule_uuid="", canonical_smiles="C", fingerprint="f")
        with pytest.raises(ValueError):
            TargetIdentity(molecule_uuid="u", canonical_smiles="C", fingerprint=" ")
        with pytest.raises(ValueError):
            PlannerIdentity(planner="", version="1")
        with pytest.raises(ValueError):
            PlannerIdentity(planner="p", version="1", model_identity=(("expansion", ""),))

    def test_the_label_shows_names_and_no_path(self):
        label = PLANNER.label()
        assert label == "AiZynthFinder 4.4.1 (expansion: uspto)"
        assert PlannerIdentity(planner="X", version="2").label() == "X 2"


class TestRouteSetStatuses:
    def test_found_needs_a_route(self):
        with pytest.raises(ValueError, match="at least one route"):
            RouteSet(status=RouteStatus.FOUND, target=TARGET, planner=PLANNER)

    @pytest.mark.parametrize("status", [s for s in RouteStatus if s is not RouteStatus.FOUND])
    def test_nothing_else_carries_routes(self, status):
        with pytest.raises(ValueError, match="no routes"):
            RouteSet(status=status, target=TARGET, planner=PLANNER, routes=(two_step_route(),), reason="because")

    @pytest.mark.parametrize("status", [RouteStatus.REFUSED, RouteStatus.FAILED, RouteStatus.CANCELLED, RouteStatus.UNAVAILABLE, RouteStatus.UNSCREENED])
    def test_these_need_a_reason(self, status):
        with pytest.raises(ValueError, match="reason"):
            RouteSet(status=status, target=TARGET, planner=PLANNER)
        with pytest.raises(ValueError, match="reason"):
            RouteSet(status=status, target=TARGET, planner=PLANNER, reason="   ")

    def test_no_route_needs_no_reason(self):
        assert RouteSet(status=RouteStatus.NO_ROUTE, target=TARGET, planner=PLANNER).routes == ()

    def test_routes_must_be_ranked_in_order(self):
        with pytest.raises(ValueError, match="ranked"):
            found(two_step_route(rank=2))
        with pytest.raises(ValueError, match="ranked"):
            found(two_step_route(rank=1), two_step_route(rank=3))
        assert len(found(two_step_route(rank=1), two_step_route(rank=2)).routes) == 2

    def test_a_cancelled_request_cannot_claim_another_stop(self):
        with pytest.raises(ValueError, match="cancelled"):
            RouteSet(status=RouteStatus.CANCELLED, target=TARGET, planner=PLANNER, reason="Cancelled by the user.", termination=SearchTermination.TIME_LIMIT)
        RouteSet(status=RouteStatus.CANCELLED, target=TARGET, planner=PLANNER, reason="Cancelled by the user.", termination=SearchTermination.CANCELLED)

    def test_the_standing_limitations_cannot_be_dropped(self):
        for i in range(len(STANDARD_LIMITATIONS)):
            kept = STANDARD_LIMITATIONS[:i] + STANDARD_LIMITATIONS[i + 1 :]
            with pytest.raises(ValueError, match="limitations"):
                found(two_step_route(), limitations=kept)
        with pytest.raises(ValueError, match="limitations"):
            found(two_step_route(), limitations=())

    def test_a_provider_may_add_a_limitation(self):
        extra = "The public model was probably trained on the benchmark's reference reactions."
        rs = found(two_step_route(validation=good_validation()), limitations=STANDARD_LIMITATIONS + (extra,))
        assert extra in rs.all_limitations() and set(STANDARD_LIMITATIONS) <= set(rs.all_limitations())


class TestRouteSetWords:
    def test_no_route_says_the_search_not_the_chemistry(self):
        text = RouteSet(status=RouteStatus.NO_ROUTE, target=TARGET, planner=PLANNER).message()
        assert "within the configured search limits" in text
        assert "no route exists" not in text.lower()

    def test_no_message_ever_says_a_route_does_not_exist(self):
        sets = [
            RouteSet(status=RouteStatus.NO_ROUTE, target=TARGET, planner=PLANNER),
            found(two_step_route()),
            *[RouteSet(status=s, target=TARGET, planner=PLANNER, reason="why") for s in RouteStatus if s not in (RouteStatus.FOUND, RouteStatus.NO_ROUTE)],
        ]
        for rs in sets:
            assert "no route exists" not in rs.message().lower()
            assert "impossible" not in rs.message().lower()

    def test_found_counts_its_routes(self):
        assert found(two_step_route()).message() == "1 route found."
        assert found(two_step_route(rank=1), two_step_route(rank=2)).message() == "2 routes found."

    @pytest.mark.parametrize("termination,words", [(SearchTermination.ITERATION_LIMIT, "iteration limit"), (SearchTermination.TIME_LIMIT, "time limit"), (SearchTermination.DEPTH_LIMIT, "depth limit")])
    def test_a_search_stopped_at_a_limit_says_so(self, termination, words):
        rs = found(two_step_route(), termination=termination)
        assert f"stopped at its {words}" in rs.message() and "there may be others" in rs.message()
        assert LIMITS_NOT_EXHAUSTIVE in rs.all_limitations()

    def test_an_unknown_stop_claims_nothing(self):
        rs = found(two_step_route(validation=good_validation()), termination=SearchTermination.UNKNOWN)
        assert "stopped" not in rs.message()
        assert LIMITS_NOT_EXHAUSTIVE not in rs.all_limitations()

    @pytest.mark.parametrize("status,start", [(RouteStatus.REFUSED, "Not planned: "), (RouteStatus.FAILED, "The search failed: "), (RouteStatus.CANCELLED, "Cancelled: "), (RouteStatus.UNAVAILABLE, "The planner is not available: "), (RouteStatus.UNSCREENED, "Not planned: the target could not be screened: ")])
    def test_a_reason_is_shown_after_the_status(self, status, start):
        assert RouteSet(status=status, target=TARGET, planner=PLANNER, reason=" the reason ").message() == start + "the reason"

    def test_unchecked_and_unvalidated_routes_are_flagged(self):
        unchecked = found(two_step_route())
        assert any("not been checked" in s for s in unchecked.all_limitations())
        partial = ValidationReport(molecules=Check.PASS, reactions=Check.PASS, mapping=MappingStatus.PARTIAL, conservation=Check.NOT_ASSESSABLE, stock=StockStatus.ALL_IN_STOCK)
        flagged = found(two_step_route(validation=partial))
        assert any("could not be fully validated" in s for s in flagged.all_limitations())
        clean = found(two_step_route(validation=good_validation()))
        assert clean.all_limitations() == STANDARD_LIMITATIONS + (ALERTS_NOT_CHECKED,)  # validated, but the molecules have not been screened: that is said too

    def test_all_limitations_never_repeat_a_sentence(self):
        rs = found(two_step_route(), termination=SearchTermination.ITERATION_LIMIT, limitations=STANDARD_LIMITATIONS + (LIMITS_NOT_EXHAUSTIVE,))
        assert len(rs.all_limitations()) == len(set(rs.all_limitations()))


# ---- real planner output ------------------------------------------------------------------------------------------


def _steps_from_tree(root: dict) -> tuple[list[RouteStep], list[RouteMolecule]]:
    """A test-local reading of AiZynthFinder's route dictionary (the real parser is a later slice)."""
    steps: dict[str, RouteStep] = {}
    leaves: dict[str, RouteMolecule] = {}

    def visit(mol: dict) -> None:
        reactions = mol.get("children") or []
        if not reactions:
            leaves.setdefault(mol["smiles"], RouteMolecule(smiles=mol["smiles"], in_stock=mol.get("in_stock")))
        for rxn in reactions:
            kids = [c for c in rxn["children"] if c["type"] == "mol"]
            meta = rxn.get("metadata") or {}
            steps.setdefault(
                mol["smiles"],
                RouteStep(
                    product=mol["smiles"],
                    reactants=tuple(k["smiles"] for k in kids),
                    reaction_smiles=meta.get("mapped_reaction_smiles"),
                    template_id=meta.get("template_hash"),
                    policy_name=meta.get("policy_name"),
                    policy_probability=meta.get("policy_probability"),
                ),
            )
            for kid in kids:
                visit(kid)

    visit(root)
    return list(steps.values()), list(leaves.values())


def _fixture_routes():
    found = []
    for path in sorted(FIXTURES.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for index, tree in enumerate(document.get("routes") or []):
            found.append(pytest.param(path.name, index, tree, id=f"{path.stem}-{index}"))
    return found


class TestRealPlannerRoutes:
    def test_the_fixtures_are_there(self):
        assert len(list(FIXTURES.glob("*.json"))) >= 9

    @pytest.mark.parametrize("name,index,tree", _fixture_routes())
    def test_every_returned_route_with_a_reaction_is_a_valid_route(self, name, index, tree):
        steps, leaves = _steps_from_tree(tree)
        if not steps:
            pytest.skip("a tree with no reaction: the planner's way of saying it found nothing")
        ordered = forward_order(steps, tree["smiles"])
        route = Route(target_smiles=tree["smiles"], steps=ordered, starting_materials=tuple(leaves), rank=index + 1, score=(tree.get("scores") or {}).get("state score"))
        assert route.steps[-1].product == tree["smiles"]
        assert {m.smiles for m in route.starting_materials}.isdisjoint({s.product for s in route.steps})
        # What the spike measured: the mapped reaction and a probability on every step; nothing is invented when absent.
        for s in route.steps:
            assert s.reaction_smiles is not None and s.policy_probability is not None

    def test_the_three_step_route_is_in_forward_order(self):
        document = json.loads((FIXTURES / "sildenafil_it100.json").read_text(encoding="utf-8"))
        tree = next(t for t in document["routes"] if len(_steps_from_tree(t)[0]) == 3)
        steps, _ = _steps_from_tree(tree)
        ordered = forward_order(steps, tree["smiles"])
        made = set()
        for s in ordered:
            assert all(r not in {x.product for x in ordered} or r in made for r in s.reactants)
            made.add(s.product)
        assert ordered[-1].product == tree["smiles"]

    def test_an_unsolved_search_still_returns_routes_and_the_domain_does_not_decide_which_count(self):
        # Strychnine at 100 iterations is unsolved, yet build_routes returned five: the bare target and four single steps
        # into a precursor that is not in stock. The domain accepts the second kind (a stock flag of False is data) and
        # refuses the first (no reaction); keeping only SOLVED routes is the parser's decision, not this type's.
        document = json.loads((FIXTURES / "strychnine_it100.json").read_text(encoding="utf-8"))
        assert document["statistics"]["is_solved"] is False
        built = bare = 0
        for index, tree in enumerate(document["routes"]):
            steps, leaves = _steps_from_tree(tree)
            if not steps:
                bare += 1
                with pytest.raises(ValueError):
                    Route(target_smiles=tree["smiles"], steps=(), starting_materials=(), rank=1)
                continue
            route = Route(target_smiles=tree["smiles"], steps=tuple(steps), starting_materials=tuple(leaves), rank=index + 1)
            assert all(m.in_stock is False for m in route.starting_materials)
            built += 1
        assert (bare, built) == (1, 4)
