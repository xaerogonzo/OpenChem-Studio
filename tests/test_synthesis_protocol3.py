"""Protocol 3 of the synthesis quality benchmark (`benchmarks/synthesis/PREREGISTRATION_3.md`): the pure functions that turn a transcribed reference into a tree, the secondary matches, the by-depth reading, and the committed references themselves.

The references are data that a program checks before any planner is run, so these tests hold the numbers the preregistration states (51 routes, their tiers and depths, the expected 14.0 recoveries) to the committed files, and hold the stock rule (never contains a reference's own intermediate or target) to the code that builds it.
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
from collections import Counter
from pathlib import Path

import pytest

_BENCH = Path(__file__).parent.parent / "benchmarks" / "synthesis"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _BENCH / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


j3 = _load("judge_3_under_test", "judge_3.py")
run3 = _load("run_quality_3_under_test", "run_quality_3.py")


def _doc(reactions, target):
    return {"target": {"smiles": target}, "reactions": [{"step": i + 1, "product": {"smiles": p}, "reactants": [{"smiles": s} for s in rs]} for i, (p, rs) in enumerate(reactions)]}


# A two-step route: ethanol + acetic acid -> ethyl acetate; ethyl acetate + methylamine -> N-methylacetamide (methylamine is "small").
TWO_STEP = _doc([("CCOC(C)=O", ["CCO", "CC(=O)O"]), ("CNC(C)=O", ["CCOC(C)=O", "CN"])], "CNC(C)=O")


def _route(reactions, target):
    return j3.reference_tree(_doc(reactions, target))


def test_a_salt_is_compared_as_its_free_base() -> None:
    assert j3.normalise("CCN.Cl") == j3.normalise("CCN")


def test_the_reference_tree_depth_leaves_and_intermediates() -> None:
    tree = j3.reference_tree(TWO_STEP)
    assert j3.tree_depth(tree) == 2
    assert j3.leaves_of(tree) == frozenset({j3.normalise("CCO"), j3.normalise("CC(=O)O"), j3.normalise("CN")})
    assert j3.intermediates_of(tree) == frozenset({j3.normalise("CCOC(C)=O")})


def test_depth_is_the_longest_chain_not_the_reaction_count() -> None:
    # a convergent route: two reactions feed one, so 3 reactions but depth 2
    doc = _doc([("CC(=O)OC", ["CC(=O)O", "CO"]), ("CCN", ["CCBr", "N"]), ("CC(=O)NCC", ["CC(=O)OC", "CCN"])], "CC(=O)NCC")
    assert j3.tree_depth(j3.reference_tree(doc)) == 2
    assert len(doc["reactions"]) == 3


def test_the_exact_rule_is_the_benchmarks_and_the_lenient_rule_drops_only_small_precursors() -> None:
    ref = j3.reference_tree(TWO_STEP)
    without_reagent = _route([("CCOC(C)=O", ["CCO", "CC(=O)O"]), ("CNC(C)=O", ["CCOC(C)=O"])], "CNC(C)=O")  # the planner left methylamine out
    assert not j3.matching.matches(without_reagent, ref)
    assert j3.lenient_match(without_reagent, ref)
    wrong_big_partner = _route([("CCOC(C)=O", ["CCO", "CC(=O)O"]), ("CNC(C)=O", ["CCOC(C)=O", "CCCCN"])], "CNC(C)=O")
    assert not j3.lenient_match(wrong_big_partner, ref)


def test_a_route_from_the_same_materials_by_other_chemistry_is_counted_apart() -> None:
    ref = j3.reference_tree(TWO_STEP)
    other = _route([("CNC(C)=O", ["CC(=O)O", "CN"])], "CNC(C)=O")  # a direct amide coupling from two of the reference's starting materials
    assert j3.same_materials_route(other, ref)
    assert not j3.matching.matches(other, ref)
    assert not j3.same_materials_route(ref, ref)  # an exact match is not a "same materials" route
    foreign = _route([("CNC(C)=O", ["CC(=O)Cl", "CN"])], "CNC(C)=O")
    assert not j3.same_materials_route(foreign, ref)


def test_reaction_recall_says_which_reference_reaction_was_never_proposed() -> None:
    ref = j3.reference_tree(TWO_STEP)
    only_last = _route([("CNC(C)=O", ["CCOC(C)=O", "CN"])], "CNC(C)=O")
    recall = {r["product"]: r["routes_containing"] for r in j3.reaction_recall([only_last, only_last], ref)}
    assert recall[j3.normalise("CNC(C)=O")] == 2
    assert recall[j3.normalise("CCOC(C)=O")] == 0


def test_wilson_interval_known_values() -> None:
    low, high = j3.wilson(0, 10)
    assert low == 0.0 and high == pytest.approx(0.2775, abs=1e-3)
    low, high = j3.wilson(5, 10)
    assert (low, high) == pytest.approx((0.2366, 0.7634), abs=1e-3)
    assert j3.wilson(0, 0) == (0.0, 1.0)


def test_the_lower_tail_matches_brute_force() -> None:
    probs = [0.81, 0.39, 0.39, 0.04]
    for k in range(5):
        brute = 0.0
        for outcome in itertools.product((0, 1), repeat=4):
            if sum(outcome) <= k:
                mass = 1.0
                for o, p in zip(outcome, probs):
                    mass *= p if o else 1 - p
                brute += mass
        assert j3.poisson_binomial_lower_tail(probs, k) == pytest.approx(brute)


def test_the_reading_is_lower_only_below_the_stated_tail_and_ignores_depth_one() -> None:
    depths = [3] * 10 + [1] * 5
    assert j3.reading(depths, [False] * 10 + [True] * 5)["reading"] == "LOWER"  # 0.61**10 = 0.007; the depth-1 routes do not count
    assert j3.reading(depths, [True] * 4 + [False] * 6 + [False] * 5)["reading"] == "NO EVIDENCE OF A DROP"
    read = j3.reading(depths, [True] * 15)
    assert read["routes"] == 10 and read["expected"] == pytest.approx(3.9)


def test_the_protocol_2_depth_rates_are_the_preregistered_text() -> None:
    assert j3.PROTOCOL2_M2_AT_10_BY_DEPTH == {2: 0.81, 3: 0.39, 4: 0.04}
    assert j3.SMALL_PRECURSOR_HEAVY_ATOMS == 3 and j3.LOWER_TAIL_LEVEL == 0.05 and j3.NOISE_FLOOR == 0.06


# --- the committed references and the stock rule ----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def refs():
    return run3.load_references()


def test_the_references_are_the_ones_the_preregistration_states(refs) -> None:
    assert len(refs) == 51
    assert Counter(r["tier"] for r in refs) == {"A": 32, "B": 19}
    assert Counter(r["depth"] for r in refs) == {1: 15, 2: 10, 3: 14, 4: 12}
    assert Counter(r["period"] for r in refs) == {"2018-2022": 30, "2023-2025": 13, "2017": 8}
    assert Counter(r["stratum"] for r in refs) == {"1": 13, "2": 17, "3": 21}
    assert len({r["target"] for r in refs}) == 51
    assert all(r["steps"] <= 4 for r in refs)


def test_the_expected_recoveries_are_the_preregistered_14_0(refs) -> None:
    read = j3.reading([r["depth"] for r in refs], [False] * len(refs))
    assert read["routes"] == 36 and read["expected"] == pytest.approx(14.04, abs=0.01)


def test_the_stocks_never_hold_a_reference_s_own_intermediate_or_target(refs) -> None:
    keys = run3.stock_keys(refs)
    assert keys["conflicts"] == [], "a leaf of one route is an intermediate or target of another: run those routes alone (PREREGISTRATION_3.md)"
    primary, leaves = set(keys["primary"]), set(keys["leaves"])
    for ref in refs:
        for molecule in ref["intermediates"] + [ref["target"]]:
            assert j3.inchikey(molecule) not in primary
            assert j3.inchikey(molecule) not in leaves
        for leaf in ref["leaves"]:
            assert j3.inchikey(leaf) in primary and j3.inchikey(leaf) in leaves
    assert leaves < primary


def test_the_judge_reads_a_synthetic_record_the_way_the_protocol_says(refs) -> None:
    ref = refs[0]
    from_tree = {"type": "mol", "smiles": ref["tree"]["smiles"], "children": ref["tree"]["children"], "scores": {"state score": 1.0}}
    record = {"status": "completed", "routes": [from_tree], "statistics": {"is_solved": True}}
    row = run3.target_row(ref, record)
    assert row["m2_10"] and row["m1_10"] and row["pool"] and row["lenient_m2_10"]
    assert not row["same_materials_any"]  # an exact match is not counted as "same materials"
    assert all(r["routes_containing"] == 1 for r in row["recall"])
    assert run3.target_row(ref, None)["failed"]
