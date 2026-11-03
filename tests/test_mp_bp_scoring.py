"""The melting / normal-boiling-point scorer (`benchmarks/mp_bp/mpbp_score.py`, `mpbp_models.py`), tested on made-up numbers.

The corpus is copyrighted and not here; what is held is the logic the preregistration fixes: the PASS / FAIL / NOT
EVALUABLE decision and each of its seven criteria, the bootstrap, Candidate C's ridge fit and its refusal of an unfitted
group, the development-only baseline, and the three guards that keep the holdout sealed (selection never reads a holdout
label; the holdout runs only when confirmed, only on frozen code, and only once).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "mp_bp"


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


models = _load("mpbp_models", BENCH / "mpbp_models.py")
score = _load("mpbp_score", BENCH / "mpbp_score.py")
vr = _load("validation_rows", ROOT / "tools" / "validation_rows.py")


# ------------------------------------------------------------------------------------- the preregistered numbers
def test_the_thresholds_are_the_preregistered_ones():
    ref, p, u = score.REFERENCE_ERROR_K, score.POINT_FACTOR, score.UPPER_FACTOR
    assert [round(p * ref[k], 2) for k in (("joback", "normal_boiling_point"), ("marrero_gani", "melting_point"),
                                            ("marrero_gani", "normal_boiling_point"), ("candidate_c", "melting_point"))] == [19.35, 37.35, 11.85, 33.9]
    assert [round(u * ref[k], 1) for k in (("joback", "normal_boiling_point"), ("marrero_gani", "melting_point"),
                                            ("marrero_gani", "normal_boiling_point"), ("candidate_c", "melting_point"))] == [25.8, 49.8, 15.8, 45.2]
    assert (score.MIN_IMPROVEMENT, score.MIN_IMPROVEMENT_LOWER, score.MIN_COVERAGE, score.MIN_PAIRED) == (0.20, 0.10, 0.70, 300)
    assert (score.BOOTSTRAP_RESAMPLES, score.MIN_STRATUM) == (10_000, 30)
    assert ("joback", "melting_point") not in ref          # Joback's Tf is never given a Tm reference


def _gate(**over):
    base = {"model": "candidate_c", "prop": "normal_boiling_point", "gate_eligible": True,
                "leakage_status": "known_population_no_overlap", "paired": 400, "coverage": 0.8, "mae": 10.0,
                "mae_ci": [9.0, 11.0], "improvement": 0.5, "improvement_ci": [0.4, 0.6]}
    base.update(over)
    return score.evaluate_gate(**base)


def test_a_method_meeting_every_criterion_passes():
    g = _gate()
    assert g["evaluation_status"] == "PASS" and all(g["criteria"].values())


@pytest.mark.parametrize(
    ("over", "criterion"),
    [
        ({"mae": 19.5}, "point_mae_within_1.5x"),                         # 19.35 K is the ceiling for a 12.9 K reference
        ({"mae_ci": [20.0, 25.9]}, "upper_mae_within_2.0x"),
        ({"improvement": 0.19}, "improvement_at_least_20pct"),
        ({"improvement_ci": [0.09, 0.5]}, "improvement_lower_at_least_10pct"),
        ({"coverage": 0.69}, "coverage_at_least_70pct"),
    ],
)
def test_each_numeric_criterion_alone_fails_the_gate_and_is_named(over, criterion):
    g = _gate(**over)
    assert g["evaluation_status"] == "FAIL"
    assert criterion in g["reason"] and not g["criteria"][criterion]


def test_the_boundaries_are_inclusive():
    assert _gate(mae=19.35, mae_ci=[18.0, 25.8], improvement=0.20, improvement_ci=[0.10, 0.3], coverage=0.70)["evaluation_status"] == "PASS"


def test_fewer_than_300_paired_entities_is_not_evaluable_not_a_fail():
    g = _gate(paired=299)
    assert g["evaluation_status"] == "NOT_EVALUABLE" and "300" in g["reason"]
    assert _gate(paired=300)["evaluation_status"] == "PASS"


def test_unknown_leakage_is_not_evaluable_however_good_the_numbers_are():
    g = _gate(model="joback", leakage_status="unknown", mae=1.0, mae_ci=[0.9, 1.1], improvement=0.95, improvement_ci=[0.9, 0.99])
    assert g["evaluation_status"] == "NOT_EVALUABLE" and g["numeric_criteria_all_met"]      # the good numbers are shown, labelled


def test_a_proxy_output_can_never_pass():
    g = _gate(model="joback", prop="melting_point", gate_eligible=False, leakage_status="no_overlap_by_evidence")
    assert g["evaluation_status"] == "NOT_EVALUABLE" and g["reference_error_k"] is None


# ------------------------------------------------------------------------------------- the bootstrap
def test_the_bootstrap_is_reproducible_and_brackets_the_point_estimate():
    rng = np.random.default_rng(1)
    base = rng.uniform(5, 40, 400)
    errs = base * rng.uniform(0.3, 0.8, 400)
    a = score.bootstrap(errs, base, resamples=2000)
    assert a == score.bootstrap(errs, base, resamples=2000)
    mae_ci, imp_ci = a
    assert mae_ci[0] < errs.mean() < mae_ci[1]
    point = 1 - errs.mean() / base.mean()
    assert imp_ci[0] < point < imp_ci[1]


def test_the_bootstrap_interval_narrows_with_more_entities_and_a_tie_with_the_baseline_gives_zero_improvement():
    rng = np.random.default_rng(2)
    small = rng.uniform(5, 30, 60)
    large = rng.uniform(5, 30, 1200)
    w = lambda x: np.diff(score.bootstrap(x, x * 2, resamples=1000)[0])[0]
    assert w(large) < w(small)
    same = rng.uniform(5, 30, 100)
    assert score.bootstrap(same, same, resamples=500)[1] == [0.0, 0.0]
    with pytest.raises(ValueError):
        score.bootstrap([1.0], [1.0, 2.0])


# ------------------------------------------------------------------------------------- Candidate C
GROUPS = ["g1", "g2", "g3", "g4"]


def _rows(*count_dicts):
    return [{"counts": c} for c in count_dicts]


def test_candidate_c_recovers_a_linear_model_with_a_small_penalty():
    rng = np.random.default_rng(3)
    true = {"g1": 30.0, "g2": -12.0, "g3": 55.0}
    rows = [{"counts": {g: int(n) for g, n in zip(("g1", "g2", "g3"), rng.integers(0, 4, 3)) if n}} for _ in range(300)]
    rows = [r for r in rows if r["counts"]]
    y = [200.0 + sum(n * true[g] for g, n in r["counts"].items()) for r in rows]
    fit = models.fit_candidate_c("normal_boiling_point", 0.01, rows, y, GROUPS)
    assert fit.intercept == pytest.approx(200.0, abs=0.5)
    assert dict(zip(fit.groups, fit.coefficients)) == pytest.approx(true, abs=0.2)
    assert fit.predict({"counts": {"g1": 2, "g3": 1}}).value == pytest.approx(200.0 + 60 + 55, abs=1.0)


def test_a_group_with_no_development_example_is_refused_not_scored_as_zero():
    fit = models.fit_candidate_c("melting_point", 1.0, _rows({"g1": 1}, {"g1": 2}, {"g2": 1}), [10.0, 20.0, 5.0], GROUPS)
    assert set(fit.unfitted) == {"g3", "g4"}
    refused = fit.predict({"counts": {"g1": 1, "g4": 1}})
    assert refused.value is None and refused.refusal == "UNFITTED_GROUP"
    assert fit.predict({"counts": {"g1": 1}}).value is not None
    assert fit.predict({"refusal": "CHARGED"}).refusal == "CHARGED"


def test_the_penalty_must_be_one_the_preregistration_allows_and_the_intercept_is_not_penalised():
    with pytest.raises(ValueError):
        models.fit_candidate_c("melting_point", 0.5, _rows({"g1": 1}), [1.0], GROUPS)
    rows = _rows({"g1": 1}, {"g1": 2}, {"g1": 3}, {"g1": 4})
    a = models.fit_candidate_c("melting_point", 100.0, rows, [10.0, 20.0, 30.0, 40.0], GROUPS)
    b = models.fit_candidate_c("melting_point", 100.0, rows, [1010.0, 1020.0, 1030.0, 1040.0], GROUPS)
    assert b.coefficients == pytest.approx(a.coefficients)             # a constant shift moves only the intercept
    assert b.intercept - a.intercept == pytest.approx(1000.0)
    assert a.coefficients[0] < 10.0                                    # a heavy penalty shrinks the slope below its OLS value of 10


def test_a_prediction_is_a_value_or_a_refusal_never_both_or_neither():
    with pytest.raises(ValueError):
        models.Prediction()
    with pytest.raises(ValueError):
        models.Prediction(value=1.0, refusal="x")
    assert models.Prediction(value=0.0).value == 0.0                   # a zero is a value, not a refusal


def test_the_baseline_uses_the_development_rows_it_is_given_and_falls_back_to_their_mean():
    by_family, overall = models.family_baseline(["nitro", "nitro", "ester"], [300.0, 310.0, 200.0])
    assert by_family == {"nitro": 305.0, "ester": 200.0} and overall == pytest.approx(270.0)
    assert models.baseline_prediction("nitro", by_family, overall) == 305.0
    assert models.baseline_prediction("amide", by_family, overall) == pytest.approx(270.0)
    with pytest.raises(ValueError):
        models.family_baseline([], [])


# ------------------------------------------------------------------------------------- the methods on real structures
def test_joback_and_marrero_gani_features_give_a_number_or_a_coded_refusal():
    j = models.joback_features("CCO")
    assert 300 < models.joback_prediction(j, "tb").value < 420          # ethanol boils at 351 K
    assert models.joback_prediction(models.joback_features("[Na+].[Cl-]"), "tb").refusal == "NOT_A_PURE_COMPONENT"
    mg = models.mg_features("CCO")
    assert 300 < models.mg_prediction(mg, "tb").value < 420
    assert models.mg_prediction(models.mg_features("[Na+].[Cl-]"), "tb").refusal.startswith("grouping_")


# ------------------------------------------------------------------------------------- a small corpus on disk
def _tiny_corpus(tmp_path, *, holdout_shift=0.0):
    ids = sorted({g for g in __import__("sys").modules["mpbp_models"]._joback().groups()})
    blocks = {}
    entities, features = [], {}
    np.random.default_rng(7)
    for i in range(240):
        part = "development" if i % 5 in (0, 1, 2) else ("selection" if i % 5 == 3 else "holdout")
        block = f"BLOCK{i:04d}"
        g = ids[i % 3]
        n = 1 + (i % 4)
        value = 250.0 + n * 20.0 + (holdout_shift if part == "holdout" else 0.0)
        entities.append({"identity_block": block, "smiles": "CCO", "name": block, "sources": ["crc97"], "stratum": "primary",
                         "family": "ester" if i % 2 else "nitro", "partition": part,
                         "labels": {prop: {"status": "resolved", "value_k": value + shift, "low_k": value + shift,
                                           "high_k": value + shift, "is_range": False, "record_id": f"crc97:{i}:{prop}",
                                           "cross_source": "single_source"}
                                    for prop, shift in (("melting_point", 0.0), ("normal_boiling_point", 90.0))}})
        features[block] = {"joback": {"counts": {g: n}, "tb": 300.0, "tf": 290.0}, "mg": {"counts": {1: n}, "tm": 280.0, "tb": 330.0}}
        blocks[block] = part
    (tmp_path / "entities.jsonl").write_text("\n".join(json.dumps(e) for e in entities), encoding="utf-8")
    (tmp_path / "observations.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "summary.json").write_text(json.dumps({"source_files": {}, "builder_version": "t", "manifest_checksum": "x"}), encoding="utf-8")
    (tmp_path / "features.json").write_text(json.dumps(features), encoding="utf-8")


def test_selection_never_reads_a_holdout_label(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _tiny_corpus(a)
    _tiny_corpus(b, holdout_shift=5000.0)                                # same corpus, absurd holdout labels
    fa = score.stage_select(a, a / "freeze.json")
    fb = score.stage_select(b, b / "freeze.json")
    for key in ("penalties", "selection_mae_by_penalty", "candidate_c", "development_blocks"):
        assert fa[key] == fb[key]


def test_development_and_selection_scoring_ignore_holdout_labels(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _tiny_corpus(a)
    _tiny_corpus(b, holdout_shift=5000.0)
    for d in (a, b):
        score.stage_select(d, d / "freeze.json")
    ra = score.stage_score(a, a / "freeze.json", "selection", a / "out")
    rb = score.stage_score(b, b / "freeze.json", "selection", b / "out")
    assert [r["metrics"]["mae"] for r in ra if "metrics" in r] == [r["metrics"]["mae"] for r in rb if "metrics" in r]


def test_the_holdout_runs_only_when_confirmed_on_frozen_code_and_once(tmp_path, monkeypatch):
    _tiny_corpus(tmp_path)
    freeze = tmp_path / "freeze.json"
    score.stage_select(tmp_path, freeze)
    monkeypatch.setattr(score, "git_dirty", lambda: False)
    monkeypatch.setattr(score, "stage_score", lambda *a, **k: ["scored"])
    with pytest.raises(SystemExit, match="confirm-holdout-once"):
        score.stage_holdout(tmp_path, freeze, tmp_path / "out", confirmed=False)
    assert not (tmp_path / "holdout_scored.lock").exists()
    # a frozen file that changed after the freeze blocks the run
    tampered = json.loads(freeze.read_text(encoding="utf-8"))
    tampered["file_hashes"]["benchmarks/mp_bp/mpbp_score.py"] = "0" * 64
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(SystemExit, match="changed since the freeze"):
        score.stage_holdout(tmp_path, bad, tmp_path / "out", confirmed=True)
    assert not (tmp_path / "holdout_scored.lock").exists()
    # an uncommitted tree blocks it
    monkeypatch.setattr(score, "git_dirty", lambda: True)
    with pytest.raises(SystemExit, match="uncommitted"):
        score.stage_holdout(tmp_path, freeze, tmp_path / "out", confirmed=True)
    # the one allowed run writes its lock BEFORE scoring, and a second run is refused
    monkeypatch.setattr(score, "git_dirty", lambda: False)
    assert score.stage_holdout(tmp_path, freeze, tmp_path / "out", confirmed=True) == ["scored"]
    assert (tmp_path / "holdout_scored.lock").exists()
    with pytest.raises(SystemExit, match="already scored"):
        score.stage_holdout(tmp_path, freeze, tmp_path / "out", confirmed=True)


def test_the_cli_cannot_score_the_holdout_through_the_score_command():
    with pytest.raises(SystemExit):
        score.main(["score", "--corpus", "x", "--freeze", "y", "--out", "z", "--partition", "holdout"])


def test_the_frozen_file_list_names_files_that_exist():
    assert all((ROOT / rel).is_file() for rel in score.FROZEN_FILES)
    assert set(score.file_hashes()) == set(score.FROZEN_FILES)


def test_the_baseline_is_built_from_development_labels_alone(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _tiny_corpus(a)
    _tiny_corpus(b)
    # make every NON-development label absurd in b: the baseline must not move
    ents = [json.loads(line) for line in (b / "entities.jsonl").read_text(encoding="utf-8").splitlines()]
    for e in ents:
        if e["partition"] != "development":
            for label in e["labels"].values():
                label["value_k"] = label["low_k"] = label["high_k"] = 9999.0
    (b / "entities.jsonl").write_text("\n".join(json.dumps(e) for e in ents), encoding="utf-8")
    for prop in score.PROPERTIES:
        assert score.baseline_for(score.load_corpus(a), prop) == score.baseline_for(score.load_corpus(b), prop)


def test_joback_freezing_point_is_reported_as_a_proxy_and_never_gate_eligible(tmp_path):
    _tiny_corpus(tmp_path)
    score.stage_select(tmp_path, tmp_path / "freeze.json")
    reports = score.stage_score(tmp_path, tmp_path / "freeze.json", "selection", tmp_path / "out")
    proxy = next(r for r in reports if r["model"] == "joback" and r["target"] == "melting_point")
    assert proxy["gate_eligible"] is False and proxy["target_matched"] is False
    assert proxy["gate"]["evaluation_status"] == "NOT_EVALUABLE"
    assert all(r["gate"]["evaluation_status"] != "PASS" for r in reports if r["model"] != "candidate_c")
    c = next(r for r in reports if r["model"] == "candidate_c" and r["target"] == "melting_point")
    assert c["leakage"]["status"] == "known_population_no_overlap" and c["leakage"]["may_claim_independent_holdout"]
    assert all(r["leakage"]["status"] == "unknown" for r in reports if r["model"] in ("joback", "marrero_gani"))


# ------------------------------------------------------------------------------------- the committed result
RESULTS = BENCH / "results"
result_mod = _load("mpbp_result", BENCH / "mpbp_result.py")


def _reports(partition):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESULTS.glob(f"{partition}_*.json"))]


def test_every_committed_verdict_follows_from_its_own_numbers():
    reports = _reports("holdout") + _reports("selection") + _reports("development")
    assert len(reports) == 18
    for r in reports:
        m = r["metrics"]
        again = score.evaluate_gate(
            model=r["model"], prop=r["target"], gate_eligible=r["gate_eligible"], leakage_status=r["leakage"]["status"],
            paired=r["counts"]["paired_with_baseline"], coverage=r["coverage"], mae=m["mae"], mae_ci=m["mae_ci95"],
            improvement=m["improvement_over_baseline"], improvement_ci=m["improvement_ci95"])
        assert again["evaluation_status"] == r["gate"]["evaluation_status"], (r["model"], r["target"], r["partition"])


def test_the_holdout_was_examined_once_and_by_no_other_report():
    for r in _reports("development") + _reports("selection"):
        assert all(p["partition"] != "holdout" for p in r["partitions_examined"])
    holdout = _reports("holdout")
    assert len(holdout) == 6 and all(p["partition"] == "holdout" for p in holdout)
    assert all(sum(1 for e in r["partitions_examined"] if e["partition"] == "holdout") == 1 for r in holdout)
    assert (RESULTS / "holdout_scored.lock").read_text(encoding="utf-8").startswith("started ")


def test_the_freeze_records_the_preregistered_grid_and_thresholds():
    freeze = json.loads((RESULTS / "freeze.json").read_text(encoding="utf-8"))
    assert all(p in models.RIDGE_GRID for p in freeze["penalties"].values())
    assert freeze["dirty_tree"] is False
    t = freeze["thresholds"]
    assert (t["point_factor"], t["upper_factor"], t["min_improvement"], t["min_improvement_lower"], t["min_coverage"], t["min_paired"]) == (
        score.POINT_FACTOR, score.UPPER_FACTOR, score.MIN_IMPROVEMENT, score.MIN_IMPROVEMENT_LOWER, score.MIN_COVERAGE, score.MIN_PAIRED)
    summary = json.loads((BENCH / "corpus_summary.json").read_text(encoding="utf-8"))
    assert freeze["manifest_checksum"] == summary["manifest_checksum"]
    assert set(freeze["file_hashes"]) == set(score.FROZEN_FILES)


def test_no_proxy_or_unknown_leakage_report_is_ever_a_pass_and_candidate_c_leakage_is_known():
    for r in _reports("holdout") + _reports("selection") + _reports("development"):
        if not r["gate_eligible"] or r["leakage"]["status"] == "unknown":
            assert r["gate"]["evaluation_status"] != "PASS"
        if r["model"] == "candidate_c":
            # in-sample on development (its fit population IS that partition), clear on selection and holdout
            expected = "known_population_overlap_removed" if r["partition"] == "development" else "known_population_no_overlap"
            assert r["leakage"]["status"] == expected
        else:
            assert r["leakage"]["status"] == "unknown" and not r["leakage"]["may_claim_independent_holdout"]


def test_the_committed_result_document_is_what_the_generator_makes_from_the_committed_reports():
    assert (BENCH / "RESULT.md").read_text(encoding="utf-8") == result_mod.render()
