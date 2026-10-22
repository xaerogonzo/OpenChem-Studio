"""The order routes are shown in (`openchem.chem.route_ranking`) and what the planner parser does with it: the PaRoutes route score, M2's order, the cap of ten and the sentence that says what was left out.

The order is the one protocol 2 of the quality benchmark measured, so the tests hold the product's functions to the benchmark's own (`benchmarks/synthesis/route_rank.py`) on the planner's real saved output, and hold the scores to numbers worked out by hand.
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from openchem.chem import aizynth_planner as host
from openchem.chem import route_ranking as ranking
from openchem.domain.synthesis_route import SearchLimits, TargetIdentity

_BENCH = Path(__file__).parent.parent / "benchmarks" / "synthesis"
_FIXTURES = _BENCH / "fixtures"
TARGET = TargetIdentity(molecule_uuid="u-1", canonical_smiles="CC(=O)Oc1ccccc1C(=O)O", fingerprint="fp")


def _benchmark_ranker():
    spec = importlib.util.spec_from_file_location("benchmark_route_rank_under_test", _BENCH / "route_rank.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fixture(name: str) -> dict:
    document = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    document["schema"] = host.RUN_SCHEMA
    document["limits"].setdefault("all_routes", False)
    document.pop("route_count", None)
    return document


def _request(document: dict, **kw) -> host.PlanRequest:
    limits = document["limits"]
    return host.PlanRequest(
        target_smiles=document["target"],
        config={"expansion": {"uspto": ["m.onnx", "t.csv.gz"]}, "stock": {"zinc": "s.hdf5"}},
        stock=document["identity"]["selection"]["stock"],
        expansion="uspto",
        filter=None if document["identity"]["selection"]["filter"] == "none" else document["identity"]["selection"]["filter"],
        limits=SearchLimits(iteration_limit=limits["iteration_limit"], time_limit_seconds=limits["time_limit"], max_transforms=limits["max_transforms"]),
        **kw,
    )


# --- trees written by hand -----------------------------------------------------------------------------------------------------------------


def leaf(smiles: str = "C", in_stock: bool = True) -> dict:
    return {"type": "mol", "smiles": smiles, "in_stock": in_stock}


def made(smiles: str, *precursors: dict, state: float | None = None) -> dict:
    tree = {"type": "mol", "smiles": smiles, "children": [{"type": "reaction", "smiles": ">>", "children": list(precursors)}]}
    if state is not None:
        tree["scores"] = {"state score": state}
    return tree


def test_the_score_of_a_leaf_a_step_and_two_steps_is_what_the_formula_gives_by_hand():
    assert ranking.route_cost(leaf()) == 1.0
    assert ranking.route_cost(leaf(in_stock=False)) == 10.0
    assert ranking.route_cost(made("T", leaf())) == pytest.approx(1 + 1 / 0.8) == pytest.approx(2.25)
    assert ranking.route_cost(made("T", leaf(), leaf())) == pytest.approx(1 + 2 / 0.8) == pytest.approx(3.5)
    assert ranking.route_cost(made("T", leaf(in_stock=False))) == pytest.approx(1 + 10 / 0.8) == pytest.approx(13.5)
    # target <- A, B ; A <- two leaves: A costs 3.5, so the target costs 1 + (3.5 + 1) / 0.8
    assert ranking.route_cost(made("T", made("A", leaf(), leaf()), leaf())) == pytest.approx(1 + (3.5 + 1.0) / 0.8) == pytest.approx(6.625)


def test_a_molecule_with_no_in_stock_flag_counts_as_in_stock_as_the_library_does_and_only_the_first_reaction_is_read():
    assert ranking.route_cost({"type": "mol", "smiles": "C"}) == 1.0
    two = made("T", leaf())
    two["children"].append({"type": "reaction", "children": [leaf(), leaf(), leaf()]})
    assert ranking.route_cost(two) == pytest.approx(2.25)


def test_a_child_that_is_not_what_the_planner_writes_is_ignored_and_never_raises():
    odd = {"type": "mol", "smiles": "T", "children": ["x", None, {"type": "reaction", "children": [leaf(), "x", {"type": "reaction"}]}]}
    assert ranking.route_cost(odd) == pytest.approx(2.25)


def test_dense_ranks_share_a_rank_within_the_tolerance_and_never_skip_one():
    assert ranking.dense_ranks([]) == []
    assert ranking.dense_ranks([1.0, 1.0, 2.0, 2.0, 2.0, 5.0]) == [1, 1, 2, 2, 2, 3]
    assert ranking.dense_ranks([1.0, 1.0 + 5e-9, 1.0 + 2e-8]) == [1, 1, 2]
    assert ranking.dense_ranks([3.5]) == [1]


# --- the order -------------------------------------------------------------------------------------------------------------------------


def test_fewer_steps_come_first_then_the_planners_score_higher_first_then_the_order_given():
    trees = [
        made("a", leaf(), leaf(), state=0.9),  # 3.5, 0.9
        made("b", leaf(), state=0.1),  # 2.25, 0.1   -> first: cheapest
        made("c", leaf(), leaf(), state=0.95),  # 3.5, 0.95 -> before a: same rank, higher score
        made("d", leaf(), leaf(), state=0.9),  # 3.5, 0.9  -> after a: a tie in both, the order given decides
        made("e", leaf(), leaf(), leaf(), state=1.0),  # 4.75
    ]
    assert ranking.shown_order(trees) == [1, 2, 0, 3, 4]


def test_two_routes_of_one_shape_that_differ_in_the_last_float_digit_still_tie_on_rank():
    first = made("a", leaf(), state=0.2)
    second = made("b", leaf(), state=0.8)
    second_cost = ranking.route_cost(second)
    assert ranking.dense_ranks(sorted([ranking.route_cost(first), second_cost + 1e-12])) == [1, 1]
    # so the planner's score decides between them, not the float noise
    assert ranking.shown_order([first, second]) == [1, 0]


def test_a_cost_that_differs_only_in_float_noise_does_not_decide_the_order(monkeypatch):
    """The same thing through `shown_order`, with the noise put in by hand: the cheaper-by-1e-12 route must not beat a higher planner score."""
    trees = [{"jitter": 0.0, "scores": {"state score": 0.1}}, {"jitter": 1e-12, "scores": {"state score": 0.9}}, {"jitter": 1.0, "scores": {"state score": 1.0}}]
    monkeypatch.setattr(ranking, "route_cost", lambda tree: 3.5 + tree["jitter"])
    assert ranking.shown_order(trees) == [1, 0, 2]


def test_a_missing_or_malformed_planner_score_sorts_below_a_given_one_and_an_empty_list_is_empty():
    assert ranking.shown_order([]) == []
    no_score = made("a", leaf())
    bad = made("b", leaf())
    bad["scores"] = {"state score": "high"}
    nan = made("c", leaf())
    nan["scores"] = {"state score": float("nan")}
    true = made("d", leaf())
    true["scores"] = {"state score": True}
    given = made("e", leaf(), state=0.01)
    assert ranking.shown_order([no_score, bad, nan, true, given]) == [4, 0, 1, 2, 3]


def test_the_order_does_not_depend_on_where_a_route_was_in_the_list_except_for_a_full_tie():
    trees = [made(f"r{i}", *[leaf() for _ in range(1 + i % 3)], state=round(0.5 + i / 100, 3)) for i in range(30)]
    expected = [trees[i]["smiles"] for i in ranking.shown_order(trees)]
    shuffled = trees[:]
    random.Random(7).shuffle(shuffled)
    assert [shuffled[i]["smiles"] for i in ranking.shown_order(shuffled)] == expected  # every (rank, score) pair is distinct here


@pytest.mark.parametrize(
    "name",
    ["aspirin_it100", "caffeine_it100", "paracetamol_it100", "paroutes_n1_t3_it500", "paroutes_n1_t3_it500_nofilter", "s_ibuprofen_it100", "sildenafil_it100", "ibuprofen_it100", "strychnine_it100"],
)
def test_the_order_is_the_benchmarks_own_m2_order_on_the_planners_real_output(name):
    """What the benchmark measured (0.417) is the order the product shows: both are computed from the same trees."""
    benchmark = _benchmark_ranker()
    trees = _fixture(name)["routes"]
    ours = ranking.shown_order(trees)
    theirs = benchmark.analyse(trees, {"type": "mol", "smiles": "x", "children": []}).user_order  # an empty reference matches nothing; the order is what is read
    assert tuple(ours) == tuple(theirs)
    assert [ranking.route_cost(t) for t in trees] == list(benchmark.analyse(trees, {"type": "mol", "smiles": "x", "children": []}).costs)


def test_the_order_is_the_benchmarks_on_random_trees_with_many_ties():
    benchmark = _benchmark_ranker()
    rng = random.Random(11)

    def tree(depth: int) -> dict:
        if depth == 0 or rng.random() < 0.4:
            return leaf(in_stock=rng.random() < 0.8)
        return made("m", *[tree(depth - 1) for _ in range(rng.randint(1, 3))])

    trees = [made("t", *[tree(2) for _ in range(rng.randint(1, 3))], state=rng.choice([0.5, 0.9509, 0.9509, 1.0])) for _ in range(200)]
    assert tuple(ranking.shown_order(trees)) == tuple(benchmark.analyse(trees, {"type": "mol", "smiles": "x", "children": []}).user_order)


# --- the parser keeps ten, in that order, and says what it left out ---------------------------------------------------------------------------


def _parse(name: str, **kw):
    document = _fixture(name)
    return host.parse_document(document, _request(document, **kw), TARGET), document


def test_a_plan_keeps_the_first_ten_in_the_shown_order_and_ranks_them_one_to_ten():
    result, document = _parse("paracetamol_it100")  # the planner returned 15 solved routes
    assert len(result.routes) == host.ROUTES_SHOWN == 10
    assert [r.rank for r in result.routes] == list(range(1, 11))
    order = ranking.shown_order(document["routes"])
    expected = [host.route_from_tree(document["routes"][i], rank=1) for i in order[:10]]
    assert [r.steps for r in result.routes] == [e.steps for e in expected]
    assert [r.score for r in result.routes] == [e.score for e in expected]
    assert order[:10] != list(range(10)), "the fixture would not show the order being applied"
    assert all(r.validation is not None and r.validation.fully_validated for r in result.routes)


def test_what_was_not_kept_is_counted_and_said_never_dropped_silently():
    result, _ = _parse("paracetamol_it100")
    sentence = [s for s in result.limitations if s.startswith("Routes the planner returned that are not shown: ")]
    assert len(sentence) == 1 and "5 more solved routes ranked below the 10 shown" in sentence[0]
    aspirin, _ = _parse("aspirin_it100")  # 12
    assert any("2 more solved routes ranked below the 10 shown" in s for s in aspirin.limitations)
    one = _fixture("aspirin_it100")
    one["routes"] = one["routes"][:11]
    again = host.parse_document(one, _request(one), TARGET)
    assert any("1 more solved route ranked below the 10 shown" in s for s in again.limitations), "singular"


def test_a_plan_with_ten_or_fewer_solved_routes_says_nothing_about_routes_left_out():
    document = _fixture("caffeine_it100")  # 11 -> cut to 10
    document["routes"] = document["routes"][:10]
    result = host.parse_document(document, _request(document), TARGET)
    assert len(result.routes) == 10 and not any(s.startswith("Routes the planner returned that are not shown") for s in result.limitations)


def test_unsolved_routes_are_still_left_out_and_counted_beside_the_ones_beyond_the_cap():
    document = _fixture("sildenafil_it100")  # 5 returned, 2 solved
    result = host.parse_document(document, _request(document), TARGET)
    assert len(result.routes) == 2 and any("not in the stock" in s and "more solved" not in s for s in result.limitations)
    paracetamol = _fixture("paracetamol_it100")
    paracetamol["routes"] = paracetamol["routes"] + _fixture("strychnine_it100")["routes"]
    mixed = host.parse_document(paracetamol, _request(paracetamol), TARGET)
    sentence = next(s for s in mixed.limitations if s.startswith("Routes the planner returned that are not shown"))
    assert "5 more solved routes ranked below the 10 shown" in sentence and "not in the stock" in sentence


def test_a_route_that_ranks_tenth_by_cost_is_not_lost_to_an_unsolved_one_in_front_of_it():
    """The ranking is among SOLVED routes only; an unsolved route costs 10 per missing leaf and never takes a place."""
    document = _fixture("caffeine_it100")
    unsolved = json.loads(json.dumps(document["routes"][0]))

    def unstock(node):
        if not node.get("children"):
            node["in_stock"] = False
        for child in node.get("children") or []:
            for grandchild in child.get("children") or []:
                unstock(grandchild)

    unstock(unsolved)
    document["routes"] = [unsolved] + document["routes"]
    result = host.parse_document(document, _request(document), TARGET)
    assert len(result.routes) == 10 and all(all(m.in_stock for m in r.starting_materials) for r in result.routes)
    assert any("1 had a starting material" in s for s in result.limitations)


# --- the request asks for every solved route --------------------------------------------------------------------------------------------------


def test_every_solved_route_is_asked_for_unless_the_caller_says_otherwise():
    document = _fixture("aspirin_it100")
    assert _request(document).all_routes is True and _request(document).document()["all_routes"] is True
    assert _request(document, all_routes=False).document()["all_routes"] is False
    setup = host.PlannerSetup(python="p", config={"a": 1}, stock="zinc", expansion="uspto", limits=SearchLimits(iteration_limit=5, time_limit_seconds=5.0, max_transforms=3))
    assert setup.all_routes is True and setup.request_for("CCO").all_routes is True
    assert replace(setup, all_routes=False).request_for("CCO").all_routes is False
