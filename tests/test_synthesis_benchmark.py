"""The matching rule, the judge and the runner's own logic of the synthesis benchmark (`benchmarks/synthesis/`, `PREREGISTRATION.md`), on the planner's real saved routes and on synthetic records. No planner is run here."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_BENCH = Path(__file__).parent.parent / "benchmarks" / "synthesis"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(_BENCH))  # plan_batch imports its sibling spike_plan by name
try:
    plan_batch = _load("synthesis_plan_batch_under_test", _BENCH / "plan_batch.py")
finally:
    sys.path.remove(str(_BENCH))
run = _load("synthesis_run_quality_under_test", _BENCH / "run_quality.py")
match, judge = run.matching, run.judge


def _fixture(name: str) -> dict:
    return json.loads((_BENCH / "fixtures" / f"{name}_it100.json").read_text(encoding="utf-8"))


def _mol(smiles, children=None, in_stock=True):
    node = {"type": "mol", "smiles": smiles, "in_stock": in_stock}
    if children is not None:
        node["children"] = children
    return node


def _step(*precursors):
    return {"type": "reaction", "smiles": "", "metadata": {}, "children": list(precursors)}


def _tree(target, *steps):
    node = _mol(target, list(steps))
    return node


ASPIRIN = _tree("CC(=O)Oc1ccccc1C(=O)O", _step(_mol("CC(=O)OC(C)=O"), _mol("O=C(O)c1ccccc1O")))


# --- the matching rule ------------------------------------------------------------------------------------------------------


def test_a_route_matches_itself_whatever_the_order_of_its_precursors_the_atom_maps_or_the_way_the_smiles_is_written():
    shuffled = _tree("OC(=O)c1ccccc1OC(C)=O", _step(_mol("[CH3:1]C(=O)O[C:2](C)=O"), _mol("Oc1ccccc1C(=O)O")))

    assert match.matches(shuffled, ASPIRIN) and match.matches(ASPIRIN, shuffled)


def test_a_different_precursor_or_a_missing_or_extra_reaction_is_not_a_match():
    other_precursor = _tree("CC(=O)Oc1ccccc1C(=O)O", _step(_mol("CC(=O)Cl"), _mol("O=C(O)c1ccccc1O")))
    two_steps = _tree("CC(=O)Oc1ccccc1C(=O)O", _step(_mol("CC(=O)OC(C)=O"), _mol("O=C(O)c1ccccc1O", [_step(_mol("O=C(O)c1ccccc1[O-]"))])))

    assert not match.matches(other_precursor, ASPIRIN)
    assert not match.matches(two_steps, ASPIRIN) and not match.matches(ASPIRIN, two_steps)


def test_stereo_is_kept_so_the_other_enantiomer_does_not_match():
    s = _tree("CC(C)Cc1ccc([C@H](C)C(=O)O)cc1", _step(_mol("COC(=O)[C@@H](C)c1ccc(CC(C)C)cc1")))
    r = _tree("CC(C)Cc1ccc([C@@H](C)C(=O)O)cc1", _step(_mol("COC(=O)[C@H](C)c1ccc(CC(C)C)cc1")))

    assert match.matches(s, copy.deepcopy(s)) and not match.matches(s, r)


def test_a_bare_target_with_no_reaction_never_matches_anything_not_even_itself():
    bare = _mol("CCO")

    assert not match.matches(bare, bare) and not match.matches(ASPIRIN, bare)


def test_recovery_at_k_uses_the_planners_own_order_and_the_first_k_routes_only():
    wrong = _tree("CC(=O)Oc1ccccc1C(=O)O", _step(_mol("CC(=O)Cl"), _mol("O=C(O)c1ccccc1O")))
    routes = [wrong, wrong, copy.deepcopy(ASPIRIN), wrong]

    assert not match.recovered_at(routes, ASPIRIN, 1) and not match.recovered_at(routes, ASPIRIN, 2)
    assert match.recovered_at(routes, ASPIRIN, 3) and match.recovered_at(routes, ASPIRIN, 10)
    assert not match.recovered_at([], ASPIRIN, 10)


def test_leaf_overlap_and_shorter_are_reported_measures():
    chloride = _tree("CC(=O)Oc1ccccc1C(=O)O", _step(_mol("CC(=O)Cl"), _mol("O=C(O)c1ccccc1O")))

    assert match.leaf_overlap(ASPIRIN, ASPIRIN) == 1.0
    assert match.leaf_overlap(chloride, ASPIRIN) == pytest.approx(1 / 2)  # one of two leaves shared
    longer = _tree("CC(=O)Oc1ccccc1C(=O)O", _step(_mol("CC(=O)OC(C)=O"), _mol("O=C(O)c1ccccc1O", [_step(_mol("O=C(O)c1ccccc1[O-]"))])))
    assert match.is_shorter(ASPIRIN, longer) and not match.is_shorter(longer, ASPIRIN) and not match.is_shorter(ASPIRIN, ASPIRIN)


# --- the judge --------------------------------------------------------------------------------------------------------------


def _rows(n=300, solved=300, recovered=300, valid_of=None, failed=0):
    rows = []
    for i in range(n):
        rows.append({"index": i, "failed": i < failed, "solved": i >= n - solved, "recovered_at_10": i >= n - recovered, "top1_has_reaction": True, "top1_valid": True})
    if valid_of is not None:
        for i, r in enumerate(rows):
            r["top1_valid"] = i < valid_of
    return rows


def _stable(n_same=20):
    return [{"index": i, "solved": [True, True, True] if i < n_same else [True, False, True]} for i in range(20)]


def test_a_perfect_run_is_go_and_each_claim_has_its_own_pass_bar():
    result = judge.judge(_rows(), _stable())

    assert result["overall"] == judge.GO and all(c.verdict == judge.PASS for c in result["claims"].values())


@pytest.mark.parametrize(
    "solved, expected",
    [(270, judge.PASS), (269, judge.PARTIAL), (240, judge.PARTIAL), (239, judge.NO_GO)],  # 0.90 and 0.80 of 300
)
def test_the_solved_bars_are_ninety_and_eighty_percent(solved, expected):
    assert judge.judge(_rows(solved=solved), _stable())["claims"]["solved"].verdict == expected


@pytest.mark.parametrize("recovered, expected", [(150, judge.PASS), (149, judge.PARTIAL), (105, judge.PARTIAL), (104, judge.NO_GO)])  # 0.50 and 0.35 of 300
def test_the_recovery_bars_are_fifty_and_thirty_five_percent(recovered, expected):
    assert judge.judge(_rows(recovered=recovered), _stable())["claims"]["recovered"].verdict == expected


@pytest.mark.parametrize("valid, expected", [(285, judge.PASS), (284, judge.PARTIAL), (240, judge.PARTIAL), (239, judge.NO_GO)])  # 0.95 and 0.80 of 300
def test_the_validity_bars_are_ninety_five_and_eighty_percent(valid, expected):
    assert judge.judge(_rows(valid_of=valid), _stable())["claims"]["valid"].verdict == expected


@pytest.mark.parametrize("same, expected", [(20, judge.PASS), (19, judge.PASS), (18, judge.PARTIAL), (17, judge.PARTIAL), (16, judge.NO_GO)])
def test_the_stability_bars_are_nineteen_and_seventeen_of_twenty(same, expected):
    assert judge.judge(_rows(), _stable(same))["claims"]["stable"].verdict == expected


def test_one_failed_claim_makes_the_run_no_go_and_a_partial_makes_it_partial():
    assert judge.judge(_rows(solved=200), _stable())["overall"] == judge.NO_GO
    assert judge.judge(_rows(solved=250), _stable())["overall"] == judge.PARTIAL
    assert judge.judge(_rows(solved=250, recovered=50), _stable())["overall"] == judge.NO_GO  # a no-go outranks a partial


def test_a_run_with_too_many_failed_targets_or_no_stability_or_no_valid_base_is_not_evaluable():
    assert judge.judge(_rows(failed=16), _stable())["overall"] == judge.NOT_EVALUABLE  # more than 5% of 300
    assert judge.judge(_rows(failed=15), _stable())["overall"] == judge.GO  # exactly 5% failed is allowed
    assert judge.judge(_rows(), _stable()[:19])["overall"] == judge.NOT_EVALUABLE
    assert judge.judge(_rows(), [])["overall"] == judge.NOT_EVALUABLE
    assert judge.judge([], _stable())["overall"] == judge.NOT_EVALUABLE
    no_reaction = [dict(r, top1_has_reaction=False) for r in _rows()]
    assert judge.judge(no_reaction, _stable())["overall"] == judge.NOT_EVALUABLE


def test_a_failed_target_counts_as_a_miss_not_a_solve():
    rows = _rows()
    for r in rows[:30]:
        r["failed"] = True  # 10% failed: also not evaluable, but the solved count must exclude them
    assert judge.judge(rows, _stable())["claims"]["solved"].value == pytest.approx(270 / 300)


# --- the draw and the configuration -----------------------------------------------------------------------------------------


def test_the_draw_is_seeded_excludes_what_the_spike_saw_and_has_a_stability_prefix():
    first, second = run.draw(10000), run.draw(10000)

    assert first == second and first["seed"] == 20261019
    assert len(first["main"]) == 300 and len(set(first["main"])) == 300 and not set(first["main"]) & {0, 1, 2}
    assert first["stability"] == first["main"][:20] and all(0 <= i < 10000 for i in first["main"])


def test_the_planner_configuration_has_the_public_policy_no_filter_and_the_set_stock():
    config = run.planner_config(Path("D:/models"), Path("D:/keys.txt"))

    assert set(config) == {"expansion", "stock"} and "filter" not in config
    assert config["stock"] == {"n1": str(Path("D:/keys.txt"))} and config["expansion"]["uspto"][0].endswith("uspto_model.onnx")


def test_the_batch_resume_reads_which_target_and_run_pairs_are_done(tmp_path):
    path = tmp_path / "out.jsonl"
    path.write_text(json.dumps({"id": 4, "run_label": "r1"}) + "\n\n" + json.dumps({"id": 4, "run_label": "r2"}) + "\n", encoding="utf-8")

    assert plan_batch._done(str(path)) == {(4, "r1"), (4, "r2")} and plan_batch._done(str(tmp_path / "none.jsonl")) == set()


# --- the per-target row and the report --------------------------------------------------------------------------------------


def _record(i, routes, solved=True, status="completed", seconds=30.0, identity=None):
    record = {"id": i, "run_label": "r1", "status": status, "target": "x", "seconds": seconds, "peak_working_set_mb": 900.0, "identity": identity or {"planner": "p"}}
    if status == "completed":
        record.update(statistics={"is_solved": solved}, routes=routes)
    return record


def test_a_target_row_reads_solved_recovery_validity_and_the_reported_measures_from_a_real_route():
    reference = _fixture("aspirin")["routes"][0]
    row = run.target_row(reference, _record(7, [copy.deepcopy(reference)]))

    assert (row["failed"], row["solved"], row["recovered_at_1"], row["recovered_at_10"]) == (False, True, True, True)
    assert row["top1_has_reaction"] and row["top1_valid"] and row["leaf_overlap"] == 1.0 and row["top1_shorter"] is False


def test_a_failed_target_and_an_unsolved_one_are_rows_that_cannot_score():
    reference = _fixture("aspirin")["routes"][0]

    failed = run.target_row(reference, _record(1, [], status="failed"))
    unsolved = run.target_row(reference, _record(2, [], solved=False))

    assert failed["failed"] and not failed["solved"] and not unsolved["failed"] and not unsolved["solved"] and not unsolved["recovered_at_10"] and not unsolved["top1_has_reaction"]


def _world(n=300, solved_share=1.0, commit="abc", dirty=False, drop_one_stability_run=False):
    reference_route = _fixture("aspirin")["routes"][0]
    reference = [reference_route] * n
    routes = [copy.deepcopy(reference_route)]
    draw = {"main": list(range(n)), "stability": list(range(20))}
    results = {label: [] for label in run.RUNS}
    for i in range(n):
        results["r1"].append(_record(i, routes, solved=i < n * solved_share))
    for label in ("r2", "r3"):
        for i in range(20):
            if drop_one_stability_run and label == "r3" and i == 0:
                continue
            results[label].append(_record(i, routes))
    return reference, results, [{"commit": commit, "dirty": dirty}], draw


def test_a_run_that_reproduces_every_reference_is_go_and_says_so_with_its_caveats():
    text, verdict = run.report_text(*_world())

    assert verdict["overall"] == judge.GO and "VERDICT GO" in text and verdict["problem"] is None
    assert "CONTAMINATION" in text and "Feasibility is not measured" in text and "0.20 / 0.55 / 0.61" in text


def test_a_low_solved_share_is_no_go_in_the_report():
    _, verdict = run.report_text(*_world(solved_share=0.5))
    assert verdict["overall"] == judge.NO_GO and verdict["claims"]["solved"]["verdict"] == judge.NO_GO


def test_an_incomplete_stability_triple_leaves_the_run_not_evaluable():
    _, verdict = run.report_text(*_world(drop_one_stability_run=True))
    assert verdict["overall"] == judge.NOT_EVALUABLE  # 19 complete triples of the 20


@pytest.mark.parametrize("problem", ["commits", "dirty", "identity"])
def test_records_from_two_commits_a_dirty_tree_or_two_planner_identities_are_refused_even_when_perfect(problem):
    reference, results, provenance, draw = _world()
    if problem == "commits":
        provenance = provenance + [{"commit": "def", "dirty": False}]
    elif problem == "dirty":
        provenance = [{"commit": "abc", "dirty": True}]
    else:
        results["r2"][0]["identity"] = {"planner": "other"}

    text, verdict = run.report_text(reference, results, provenance, draw)

    assert verdict["overall"] == judge.NOT_EVALUABLE and verdict["problem"] and "REFUSED" in text
