"""Protocol 2 of the synthesis quality benchmark (`benchmarks/synthesis/PREREGISTRATION_2.md`): the PaRoutes route score and shared ranks, the three counts (M1, M2, M3), the runner's row and report logic, its refusals, and the `--all-routes` wiring of the batch runner. No planner is run here; the planner module is replaced by a fake that records what it was told."""

from __future__ import annotations

import copy
import gzip
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

_BENCH = Path(__file__).parent.parent / "benchmarks" / "synthesis"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rank = _load("synthesis_rank_under_test", _BENCH / "route_rank.py")
run2 = _load("synthesis_run_quality_2_under_test", _BENCH / "run_quality_2.py")
sys.path.insert(0, str(_BENCH))  # plan_batch imports its sibling spike_plan by name
try:
    plan_batch = _load("synthesis_plan_batch_2_under_test", _BENCH / "plan_batch.py")
finally:
    sys.path.remove(str(_BENCH))
judge = run2.judge

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
ANHYDRIDE, SALICYLIC = "CC(=O)OC(C)=O", "O=C(O)c1ccccc1O"


def mol(smiles, children=None, in_stock=True):
    node = {"type": "mol", "smiles": smiles, "in_stock": in_stock}
    if children is not None:
        node["children"] = children
    return node


def step(*precursors):
    return {"type": "reaction", "smiles": "", "metadata": {}, "children": list(precursors)}


def tree(target, *steps, in_stock=True):
    return mol(target, list(steps), in_stock=in_stock)


def scored(route, state):
    return {**route, "scores": {"state score": state}}


#: The reference: aspirin from the anhydride and salicylic acid, salicylic acid from phenol and CO2 (two reactions).
REFERENCE = tree(ASPIRIN, step(mol(ANHYDRIDE), mol(SALICYLIC, [step(mol("Oc1ccccc1"), mol("O=C=O"))])))


def one_step(i):
    """A distinct one-step route to aspirin: all of them tie on the route score."""
    return tree(ASPIRIN, step(mol("C" * (i + 1) + "O"), mol("O")))


# --- the route score ---------------------------------------------------------------------------------------------------------


def test_the_route_score_is_the_library_formula_computed_by_hand():
    # a leaf in stock 1, not in stock 10; a reaction 1.0 + each precursor's cost / 0.8
    assert rank.route_cost(mol("C")) == 1.0
    assert rank.route_cost(mol("C", in_stock=False)) == 10.0
    assert rank.route_cost(one_step(0)) == pytest.approx(1.0 + 2 * 1.0 / 0.8)  # 3.5
    assert rank.route_cost(REFERENCE) == pytest.approx(1.0 + (1.0 + (1.0 + 2 * 1.0 / 0.8)) / 0.8)  # 6.625
    assert rank.route_cost(tree(ASPIRIN, step(mol("C", in_stock=False)))) == pytest.approx(1.0 + 10.0 / 0.8)  # 13.5
    assert rank.route_cost({"type": "mol", "smiles": "C"}) == 1.0  # no in_stock flag counts as in stock, as the library does


def test_only_the_first_reaction_under_a_molecule_is_read():
    two = mol(ASPIRIN, [step(mol("C"), mol("O")), step(mol("CC"), mol("CCC"), mol("CCCC"))])
    assert rank.route_cost(two) == rank.route_cost(mol(ASPIRIN, [step(mol("C"), mol("O"))]))


def test_a_costlier_route_scores_higher_so_a_shorter_one_ranks_first():
    assert rank.route_cost(one_step(0)) < rank.route_cost(REFERENCE) < rank.route_cost(tree(ASPIRIN, step(mol("C", in_stock=False))))


# --- shared ranks ------------------------------------------------------------------------------------------------------------


def test_equal_scores_share_a_rank_and_a_new_score_is_the_previous_rank_plus_one():
    assert rank.dense_ranks([3.5, 3.5, 6.625, 6.625, 6.625, 13.5]) == [1, 1, 2, 2, 2, 3]
    assert rank.dense_ranks([]) == [] and rank.dense_ranks([2.0]) == [1]


def test_scores_closer_than_the_tolerance_tie_and_scores_further_apart_do_not():
    assert rank.dense_ranks([1.0, 1.0 + 5e-9]) == [1, 1]
    assert rank.dense_ranks([1.0, 1.0 + 5e-8]) == [1, 2]


def test_the_tie_test_compares_neighbours_as_the_library_does():
    # 0 -> 6e-9 -> 1.2e-8: each step is a tie, though the ends are not within 1e-8; the library chains them.
    assert rank.dense_ranks([1.0, 1.0 + 6e-9, 1.0 + 1.2e-8]) == [1, 1, 1]


# --- the three counts --------------------------------------------------------------------------------------------------------


def _pool_with_the_reference_last():
    routes = [scored(one_step(i), 0.95 - i * 0.001) for i in range(12)] + [scored(copy.deepcopy(REFERENCE), 0.90)]
    return routes


def test_the_paroutes_count_includes_every_tied_route_so_a_reference_at_the_second_level_is_in_the_top_ten_but_not_the_first_ten_routes():
    a = rank.analyse(_pool_with_the_reference_last(), REFERENCE)

    assert a.count == 13 and a.pool()
    # twelve routes tie at level 1; the reference is the only route at level 2, and the 13th in every order.
    assert (a.m1(1), a.m1(2), a.m1(10)) == (False, True, True)
    assert (a.m2(1), a.m2(5), a.m2(10)) == (False, False, False)
    assert (a.m3(1), a.m3(5), a.m3(10)) == (False, False, False)
    assert a.routes_within_rank(1) == 12 and a.routes_within_rank(2) == 13 and a.distinct_ranks() == 2 and a.first_hit_rank() == 2


def test_the_user_facing_order_breaks_a_tie_by_state_score_then_by_the_planners_order():
    tied = [scored(one_step(0), 0.5), scored(copy.deepcopy(REFERENCE), 0.9), scored(one_step(1), 0.5)]
    # the reference costs more, so it is last by rank; make three routes of ONE shape and let the state score decide.
    shape = [scored(tree(ASPIRIN, step(mol("CO"), mol("O"))), 0.2), scored(tree(ASPIRIN, step(mol("CCO"), mol("O"))), 0.9), scored(tree(ASPIRIN, step(mol("CCCO"), mol("O"))), 0.9)]
    a = rank.analyse(shape, tree(ASPIRIN, step(mol("CCO"), mol("O"))))
    assert a.user_order == (1, 2, 0)  # 0.9 before 0.2; the two 0.9s keep the planner's order
    assert a.m2(1) is True and rank.analyse(shape, tree(ASPIRIN, step(mol("CO"), mol("O")))).m2(2) is False
    assert rank.analyse(tied, REFERENCE).user_order[-1] == 1  # the costlier reference is last whatever its state score


def test_a_tie_is_a_tie_even_when_the_last_float_digit_differs(monkeypatch):
    # Two routes of one shape can score 3.5 and 3.5 + 1e-12; ordering by the raw cost would put the first one first and let float noise decide.
    costs = {id_: value for id_, value in ((0, 3.5), (1, 3.5 + 1e-12))}
    routes = [scored(one_step(0), 0.1), scored(one_step(1), 0.9)]
    by_object = {id(routes[0]): costs[0], id(routes[1]): costs[1]}
    monkeypatch.setattr(rank, "route_cost", lambda route: by_object[id(route)])

    a = rank.analyse(routes, one_step(1))

    assert a.cost_ranks == (1, 1) and a.user_order == (1, 0) and a.m2(1) is True


def test_the_planners_own_order_is_what_m3_reads_and_the_pool_is_the_ceiling():
    routes = [scored(one_step(0), 0.9), scored(copy.deepcopy(REFERENCE), 0.8)]
    a = rank.analyse(routes, REFERENCE)
    assert (a.m3(1), a.m3(2)) == (False, True) and a.pool() and a.m1(2)


def test_a_reference_with_no_reaction_matches_nothing_and_empty_pools_are_safe():
    bare = mol(ASPIRIN)
    a = rank.analyse([copy.deepcopy(bare)], bare)
    assert not a.pool() and not a.m1(10) and a.first_hit_rank() is None
    empty = rank.analyse([], REFERENCE)
    assert empty.count == 0 and not empty.m1(10) and not empty.m2(10) and empty.distinct_ranks() == 0 and empty.routes_within_rank(10) == 0


def test_stereo_is_kept_in_the_match():
    reference = tree("C[C@H](N)C(=O)O", step(mol("CC(=O)C(=O)O"), mol("N")))
    other = tree("C[C@@H](N)C(=O)O", step(mol("CC(=O)C(=O)O"), mol("N")))
    assert not rank.analyse([other], reference).pool() and rank.analyse([copy.deepcopy(reference)], reference).pool()


# --- the batch runner's flag -------------------------------------------------------------------------------------------------


class _Collection:
    def __init__(self, routes):
        self._routes = routes

    def __len__(self):
        return len(self._routes)

    def dict_with_scores(self):
        return self._routes


class _Selector:
    def select(self, value, *args):
        pass


def _fake_planner(monkeypatch, seen):
    class Finder:
        def __init__(self, configdict=None, configfile=None):
            self.config = types.SimpleNamespace(search=types.SimpleNamespace(), post_processing=types.SimpleNamespace(all_routes=False))
            self.stock, self.expansion_policy, self.filter_policy = _Selector(), _Selector(), _Selector()
            seen["finder"] = self

        def prepare_tree(self):
            pass

        def tree_search(self):
            pass

        def build_routes(self):
            seen["all_routes_at_build"] = self.config.post_processing.all_routes
            self.routes = _Collection([{"type": "mol", "smiles": self.target_smiles, "children": []}])

        def extract_statistics(self):
            return {"is_solved": True}

    module = types.ModuleType("aizynthfinder.aizynthfinder")
    module.AiZynthFinder = Finder
    monkeypatch.setitem(sys.modules, "aizynthfinder", types.ModuleType("aizynthfinder"))
    monkeypatch.setitem(sys.modules, "aizynthfinder.aizynthfinder", module)


@pytest.mark.parametrize("flag", [True, False])
def test_the_all_routes_flag_reaches_the_planner_before_the_routes_are_built_and_is_recorded_only_when_set(tmp_path, monkeypatch, flag):
    seen: dict = {}
    _fake_planner(monkeypatch, seen)
    config, targets, out = tmp_path / "c.json", tmp_path / "t.json", tmp_path / "out.jsonl"
    config.write_text("{}", encoding="utf-8")
    targets.write_text(json.dumps([{"id": 3, "smiles": "CCO"}]), encoding="utf-8")
    argv = ["plan_batch.py", "--config", str(config), "--stock", "n1", "--targets", str(targets), "--out", str(out), "--run-label", "r1"] + (["--all-routes"] if flag else [])
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(sys, "stdout", sys.stdout)  # main() points stdout at stderr and never puts it back; this restores it afterwards

    assert plan_batch.main() == 0
    record = json.loads(out.read_text(encoding="utf-8").splitlines()[0])

    assert seen["all_routes_at_build"] is flag
    assert record["limits"].get("all_routes") is (True if flag else None)
    assert ("all_routes" in record["limits"]) is flag  # a protocol 1 record keeps the shape it had


# --- a target row ------------------------------------------------------------------------------------------------------------


def _record(i, routes, solved=True, status="completed", all_routes=True, identity=None, seconds=30.0):
    ident = identity or IDENTITY
    record = {"id": i, "run_label": "r1", "status": status, "target": "x", "seconds": seconds, "peak_working_set_mb": 900.0, "identity": ident,
              "limits": {"iteration_limit": 500, "time_limit": 1800, "max_transforms": 10, **({"all_routes": True} if all_routes else {})}}
    if status == "completed":
        record.update(statistics={"is_solved": solved}, routes=routes)
    return record


IDENTITY = {"planner": "aizynthfinder", "packages": {"aizynthfinder": "4.4.1"}, "python": "3.12.1", "config_sha256": "AAA", "selection": {"stock": "n1", "expansion": "uspto", "filter": "none"}}


def test_the_judges_recovered_field_is_m1_and_the_others_ride_beside_it():
    row = run2.target_row(REFERENCE, _record(4, _pool_with_the_reference_last()))

    assert (row["recovered_at_1"], row["recovered_at_5"], row["recovered_at_10"]) == (False, True, True)  # M1
    assert row["m2"] == [False, False, False] and row["m3"] == [False, False, False] and row["pool"]
    assert row["routes_rank10"] == 13 and row["distinct_ranks"] == 2 and row["first_hit_rank"] == 2 and row["route_count"] == 13


def test_the_first_route_that_is_validated_is_the_first_of_the_user_facing_order():
    good = scored(_fixture_route(), 0.99)  # a real route that validates; one step, so it costs 3.5
    cheaper_but_bad = scored(tree(ASPIRIN, step(mol("CCO"))), 0.1)  # costs 2.25 and has no mapped reaction, so it cannot validate
    first_by_planner = run2.target_row(_fixture_route(), _record(1, [good]))
    row = run2.target_row(_fixture_route(), _record(1, [good, cheaper_but_bad]))
    assert first_by_planner["top1_valid"]
    assert row["top1_has_reaction"] and not row["top1_valid"]  # the cheaper route comes first, though the planner listed the other first


def test_a_failed_target_is_a_miss_and_an_unsolved_one_still_scores_its_pool():
    failed = run2.target_row(REFERENCE, _record(1, [], status="failed"))
    assert failed["failed"] and not failed["solved"] and not any(failed["m2"]) and failed["recovered_at_10"] is False
    unsolved = run2.target_row(REFERENCE, _record(2, [], solved=False))
    assert not unsolved["failed"] and not unsolved["solved"] and not unsolved["top1_has_reaction"]


# --- the report ---------------------------------------------------------------------------------------------------------------


def _fixture_route():
    return json.loads((_BENCH / "fixtures" / "aspirin_it100.json").read_text(encoding="utf-8"))["routes"][0]


PROTOCOL1 = {"recovered": 1.0, "identity": run2.normalised(IDENTITY), "inputs": {"targets_n1.txt": "T", "stock_n1.txt": "S"}, "stock_keys_md5": "K"}


def _world(n=300, commit="abc", dirty=False, drop_one_stability_run=False, all_routes=True, identity=None, pool=None):
    route = _fixture_route()
    reference = [route] * n
    routes = pool if pool is not None else [scored(copy.deepcopy(route), 0.9)]
    draw = {"main": list(range(n)), "stability": list(range(20))}
    results = {label: [] for label in run2.RUNS}
    for i in range(n):
        results["r1"].append(_record(i, routes, all_routes=all_routes, identity=identity))
    for label in ("r2", "r3"):
        for i in range(20):
            if drop_one_stability_run and label == "r3" and i == 0:
                continue
            results[label].append(_record(i, routes, all_routes=all_routes, identity=identity))
    provenance = [{"commit": commit, "dirty": dirty, "inputs": {"targets_n1.txt": "T", "stock_n1.txt": "S", "stock_n1_inchikeys.txt": "K", "uspto_model.onnx size": 91518243, "uspto_templates.csv.gz size": 3313598}}]
    return reference, results, provenance, draw, copy.deepcopy(PROTOCOL1)


def test_a_run_that_reproduces_every_reference_is_go_and_reports_the_decomposition_and_the_caveats():
    text, summary, rows = run2.report_text(*_world())

    assert summary["overall"] == judge.GO and summary["problems"] == [] and len(rows) == 300
    assert summary["m1"] == summary["m2"] == summary["m3"] == 1.0
    for expected in ("PROTOCOL 2", "protocol 1's PARTIAL stands as measured", "THE DECOMPOSITION", "M1  every route in the first 10 score levels", "M2  first 10 routes", "M3  planner's own order",
                     "CONTAMINATION", "Feasibility is not measured", "0.20 / 0.55 / 0.61", "the shortfall was protocol"):
        assert expected in text


def test_the_pool_and_the_ranking_can_move_the_verdict_while_the_planners_order_does_not():
    # The reference is the 13th route, tied on cost with twelve others that the planner listed first: M1 counts the whole tied level, M2 and M3 count 10 routes.
    route = _fixture_route()
    pool = [scored(one_step(i), 0.95 - i * 0.001) for i in range(12)] + [scored(copy.deepcopy(route), 0.9)]
    reference, results, provenance, draw, protocol1 = _world(pool=pool)
    protocol1["recovered"] = 0.0
    text, summary, _ = run2.report_text(reference, results, provenance, draw, protocol1)
    assert summary["m3"] == 0.0 and summary["m2"] == 0.0 and summary["m1"] == 1.0
    assert summary["claims"]["recovered"]["verdict"] == judge.PASS
    # ... and the first route validated is the first of M2's order (a synthetic one that cannot validate), so the judge's validity claim fails and so does the whole.
    assert summary["claims"]["valid"]["verdict"] == judge.NO_GO and summary["overall"] == judge.NO_GO


def test_m1_below_the_partial_bar_reads_as_not_protocol():
    reference, results, provenance, draw, protocol1 = _world(pool=[scored(one_step(0), 0.5)])
    protocol1["recovered"] = 0.0
    text, summary, _ = run2.report_text(reference, results, provenance, draw, protocol1)
    assert summary["claims"]["recovered"]["verdict"] == judge.NO_GO and "not protocol" in text and summary["overall"] == judge.NO_GO


def test_the_partial_band_reads_as_partly_protocol():
    route = _fixture_route()
    n = 300
    reference, results, provenance, draw, protocol1 = _world(n=n, pool=[scored(copy.deepcopy(route), 0.9)])
    # 40% of the targets keep the reference in their pool, the rest do not
    miss = [scored(one_step(0), 0.5)]
    for i in range(int(n * 0.4), n):
        results["r1"][i]["routes"] = miss
    protocol1["recovered"] = 0.4
    text, summary, _ = run2.report_text(reference, results, provenance, draw, protocol1)
    assert summary["claims"]["recovered"]["verdict"] == judge.PARTIAL and "partly protocol" in text


@pytest.mark.parametrize("what", ["commits", "dirty", "identity", "two_identities", "no_all_routes", "limits", "targets", "stock", "model", "stock_keys", "consistency"])
def test_anything_that_makes_the_run_not_comparable_with_protocol_1_is_refused_even_when_perfect(what):
    reference, results, provenance, draw, protocol1 = _world()
    if what == "commits":
        provenance = provenance + [{"commit": "def", "dirty": False, "inputs": provenance[0]["inputs"]}]
    elif what == "dirty":
        provenance[0]["dirty"] = True
    elif what == "identity":
        for records in results.values():
            for r in records:
                r["identity"] = {**IDENTITY, "packages": {"aizynthfinder": "4.5.0"}}
    elif what == "two_identities":
        results["r2"][0]["identity"] = {**IDENTITY, "python": "3.11.0"}
    elif what == "no_all_routes":
        del results["r2"][3]["limits"]["all_routes"]
    elif what == "limits":
        results["r1"][5]["limits"]["iteration_limit"] = 100
    elif what == "targets":
        provenance[0]["inputs"]["targets_n1.txt"] = "other"
    elif what == "stock":
        provenance[0]["inputs"]["stock_n1.txt"] = "other"
    elif what == "model":
        provenance[0]["inputs"]["uspto_model.onnx size"] = 1
    elif what == "stock_keys":
        provenance[0]["inputs"]["stock_n1_inchikeys.txt"] = "other"
    else:
        protocol1["recovered"] = 0.373

    text, summary, _ = run2.report_text(reference, results, provenance, draw, protocol1)

    assert summary["overall"] == judge.NOT_EVALUABLE and summary["problems"] and "REFUSED" in text


def test_the_consistency_tolerance_is_five_hundredths():
    reference, results, provenance, draw, protocol1 = _world()
    protocol1["recovered"] = 0.9501
    assert run2.report_text(reference, results, provenance, draw, protocol1)[1]["overall"] == judge.GO
    protocol1["recovered"] = 0.9499
    assert run2.report_text(reference, results, provenance, draw, protocol1)[1]["overall"] == judge.NOT_EVALUABLE


def test_an_incomplete_stability_triple_leaves_the_run_not_evaluable():
    assert run2.report_text(*_world(drop_one_stability_run=True))[1]["overall"] == judge.NOT_EVALUABLE


def test_a_missing_input_checksum_in_protocol_1s_records_is_not_a_refusal():
    reference, results, provenance, draw, protocol1 = _world()
    protocol1["inputs"], protocol1["stock_keys_md5"] = {}, None
    assert run2.report_text(reference, results, provenance, draw, protocol1)[1]["problems"] == []


# --- reading protocol 1's records ---------------------------------------------------------------------------------------------


def test_protocol_1_is_read_from_its_committed_gzipped_records_and_the_configuration_hash_is_not_part_of_the_identity(tmp_path):
    (tmp_path / "verdict.json").write_text(json.dumps({"claims": {"recovered": {"value": 0.3733, "verdict": "PARTIAL"}}}), encoding="utf-8")
    with gzip.open(tmp_path / "results_r1.jsonl.gz", "wt", encoding="utf-8") as handle:
        handle.write(json.dumps({"id": 1, "identity": IDENTITY}) + "\n")
    (tmp_path / "provenance.jsonl").write_text(json.dumps({"commit": "x", "dirty": False, "inputs": {"targets_n1.txt": "T"}}) + "\n", encoding="utf-8")
    (tmp_path / "stock_n1_inchikeys.txt").write_text("KEY\n", encoding="utf-8")

    reference = run2.protocol1_reference(tmp_path)

    assert reference["recovered"] == 0.3733 and reference["identity"] == run2.normalised(IDENTITY) and "config_sha256" not in reference["identity"]
    assert reference["inputs"] == {"targets_n1.txt": "T"} and reference["stock_keys_md5"] == run2.p1.md5(tmp_path / "stock_n1_inchikeys.txt")
    assert run2.normalised({**IDENTITY, "config_sha256": "OTHER"}) == run2.normalised(IDENTITY)


def test_the_real_protocol_1_records_are_readable_and_give_its_published_result():
    reference = run2.protocol1_reference(_BENCH / "artifacts")
    assert 0.37 < reference["recovered"] < 0.38 and reference["identity"]["packages"]["aizynthfinder"] == "4.4.1"


# --- gaps the mutation check found ---------------------------------------------------------------------------------------------


def test_the_best_ranked_match_is_the_lowest_level_not_the_highest():
    # The same reactions twice, one with a leaf not in stock: the same reference is matched at level 1 and at level 2.
    cheap = copy.deepcopy(REFERENCE)
    dear = copy.deepcopy(REFERENCE)
    dear["children"][0]["children"][0]["in_stock"] = False
    a = rank.analyse([scored(dear, 0.9), scored(cheap, 0.1)], REFERENCE)
    assert a.cost_ranks == (1, 2) and a.first_hit_rank() == 1


def test_the_planners_first_routes_and_the_user_facing_first_routes_are_different_lists():
    # The planner listed the reference first, but twelve cheaper routes outrank it: M3 has it at 1, M2 and the user-facing list do not.
    pool = [scored(copy.deepcopy(REFERENCE), 0.99)] + [scored(one_step(i), 0.5) for i in range(12)]
    row = run2.target_row(REFERENCE, _record(9, pool))
    assert row["m3"] == [True, True, True]
    assert row["m2"] == [False, False, False]
    assert row["recovered_at_10"] is True  # M1: level 2 of 2


@pytest.mark.parametrize("protocol1_recovered,refused", [(0.5, True), (0.0, True), (0.98, False)])
def test_the_consistency_check_is_two_sided(protocol1_recovered, refused):
    # M3 here is 1.0; a protocol 1 figure far BELOW or far ABOVE it both mean the run does not reproduce protocol 1.
    reference, results, provenance, draw, protocol1 = _world()
    protocol1["recovered"] = protocol1_recovered
    assert (run2.report_text(reference, results, provenance, draw, protocol1)[1]["overall"] == judge.NOT_EVALUABLE) is refused
    reference, results, provenance, draw, protocol1 = _world(pool=[scored(one_step(0), 0.5)])
    protocol1["recovered"] = 0.5
    assert run2.report_text(reference, results, provenance, draw, protocol1)[1]["problems"] != []  # M3 = 0.0 against 0.5: too low


# --- the official-metric check ---------------------------------------------------------------------------------------------------

official = _load("synthesis_official_check_under_test", _BENCH / "official_check.py")


def test_only_the_routes_that_can_enter_a_count_are_compared_with_the_official_distance():
    # Twelve routes on twelve different levels: the PaRoutes top-10 is the first ten; the planner listed index 11 first.
    a = rank.Analysis(hits=(False,) * 12, costs=tuple(float(i) for i in range(12)), cost_order=tuple(range(12)), cost_ranks=tuple(range(1, 13)), user_order=tuple(range(12)))
    assert official.needed_indices(a) == list(range(10))
    b = rank.Analysis(hits=(False,) * 12, costs=tuple(float(i) for i in range(12)), cost_order=tuple(range(12)), cost_ranks=tuple(range(1, 13)), user_order=(11, 10) + tuple(range(10)))
    assert official.needed_indices(b) == list(range(12))


def test_the_official_distance_decides_the_matches_and_the_disagreements_are_counted():
    routes = [scored(one_step(i), 0.9 - i * 0.01) for i in range(4)]
    reference = one_step(0)  # the exact rule matches route 0 only
    distances = {id(routes[0]): 0.5, id(routes[1]): 0.0, id(routes[2]): 0.0, id(routes[3]): 5.0}  # the library calls 1 and 2 identical and 0 different

    exact, official_analysis, differences = official.official_analysis(routes, reference, distance=lambda ref, route: distances[id(route)])

    assert exact.hits == (True, False, False, False) and official_analysis.hits == (False, True, True, False)
    assert differences == {"computed": 4, "official_only": 2, "exact_only": 1}
    assert official_analysis.costs == exact.costs and official_analysis.user_order == exact.user_order  # only what counts as a match changed


def test_the_tolerance_is_the_scripts_own_and_an_unreadable_route_never_matches():
    routes = [scored(one_step(0), 0.9), scored(one_step(1), 0.8)]
    seen = {id(routes[0]): 9.9e-7, id(routes[1]): official.UNREADABLE}
    _, analysis, _ = official.official_analysis(routes, one_step(5), distance=lambda ref, route: seen[id(route)])
    assert analysis.hits == (True, False) and official.OFFICIAL_TOLERANCE == 1e-6
    _, strict, _ = official.official_analysis(routes[:1], one_step(5), distance=lambda ref, route: 1.0e-6)
    assert strict.hits == (False,)  # "below", not "at most"


def test_the_summary_has_both_rules_and_three_counts_at_three_depths():
    a = rank.analyse([scored(copy.deepcopy(REFERENCE), 0.9)], REFERENCE)
    miss = rank.analyse([scored(one_step(0), 0.9)], REFERENCE)
    summary = official.summarise([(a, a), (miss, a)])
    assert summary["exact"]["m1"] == [0.5, 0.5, 0.5] and summary["official"]["m1"] == [1.0, 1.0, 1.0]
    assert set(summary) == {"exact", "official"} and set(summary["exact"]) == {"m1", "m2", "m3"}


_OFFICIAL_PYTHON = Path("D:/_scratch/route_distances_env/Scripts/python.exe")


@pytest.mark.skipif(not _OFFICIAL_PYTHON.exists(), reason="the separate route-distances environment is not on this machine")
def test_the_real_official_distance_is_zero_for_a_route_and_itself_and_positive_for_a_different_one(tmp_path):
    import subprocess

    script = tmp_path / "probe.py"
    script.write_text(
        "import importlib.util, json, sys\n"
        "spec = importlib.util.spec_from_file_location('oc', sys.argv[1]); m = importlib.util.module_from_spec(spec); sys.modules['oc'] = m; spec.loader.exec_module(m)\n"
        "doc = json.load(open(sys.argv[2], encoding='utf-8'))['routes']\n"
        "print(json.dumps([m.official_distance(doc[0], doc[0]), m.official_distance(doc[0], doc[1])]))\n",
        encoding="utf-8",
    )
    done = subprocess.run([str(_OFFICIAL_PYTHON), "-I", str(script), str(_BENCH / "official_check.py"), str(_BENCH / "fixtures" / "sildenafil_it100.json")], capture_output=True, text=True, timeout=300)
    same, different = json.loads(done.stdout.strip().splitlines()[-1])
    assert same == 0.0 and different > 1e-6
