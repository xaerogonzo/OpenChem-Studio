"""The family-grouped generalisation report (`benchmarks/mp_bp/mpbp_family.py`, Amendment 3 of the preregistration).

What is held: the model is never fitted on the family it is scored on, the baseline is built from the entities it was fitted
on only, a thin family is skipped and a small one is not a claim, the report carries no verdict, and the committed reports
are consistent with the corpus summary, the frozen penalty and the document built from them.
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


family = _load("mpbp_family", BENCH / "mpbp_family.py")
score = _load("mpbp_score", BENCH / "mpbp_score.py")
models = _load("mpbp_models", BENCH / "mpbp_models.py")
vr = _load("validation_rows", ROOT / "tools" / "validation_rows.py")

GROUPS = ["g1", "g2", "g3"]


def _data(per_family=80, seed=5):
    """Three families whose labels sit far apart, so that any leak of a family into its own fit shows."""
    rng = np.random.default_rng(seed)
    rows, features = [], {}
    centre = {"nitro": 500.0, "ester": 300.0, "amide": 100.0}
    for fam, c in centre.items():
        for i in range(per_family):
            n = int(rng.integers(1, 4))
            block = f"{fam}{i:03d}"
            value = c + 10.0 * n + float(rng.normal(0, 1))
            e = {"identity_block": block, "family": fam, "labels": {}}
            rows.append((e, vr.ValidationRow(row_id=block, smiles="CCO", property="melting_point", value=value, units="K",
                                             source_id="t", record_id=block, partition="development", transition_type="melting")))
            features[block] = {"joback": {"counts": {"g1": n}, "tb": 400.0, "tf": 300.0}, "mg": {"counts": {1: n}, "tm": 310.0, "tb": 420.0}}
    return rows, features, centre


def test_a_family_is_never_in_its_own_training_set(monkeypatch):
    rows, features, centre = _data()
    seen = {}
    real = models.fit_candidate_c

    def spy(prop, penalty, joback_rows, targets, all_groups):
        seen[len(seen)] = list(targets)
        return real(prop, penalty, joback_rows, targets, all_groups)

    monkeypatch.setattr(models, "fit_candidate_c", spy)
    out = family.leave_one_family_out("melting_point", rows, features, 0.01, GROUPS, min_training=10)
    assert set(out) == set(centre)
    for k, fam in enumerate(sorted(centre)):
        # every label of the family left out is far from the training labels: none of them may be among the targets fitted
        left_out = {r.value for e, r in rows if e["family"] == fam}
        assert not left_out & set(seen[k])
        assert len(seen[k]) == sum(1 for e, _ in rows if e["family"] != fam)


def test_the_baseline_is_the_mean_of_the_other_families_labels():
    rows, features, _centre = _data()
    out = family.leave_one_family_out("melting_point", rows, features, 0.01, GROUPS, min_training=10)
    amide = out["amide"]["models"]["candidate_c"]
    others = [r.value for e, r in rows if e["family"] != "amide"]
    # the baseline error on an amide is its distance to the mean of the OTHER families
    amide_rows = [r for e, r in rows if e["family"] == "amide"]
    assert amide["baseline_errors"] == pytest.approx([abs(np.mean(others) - r.value) for r in amide_rows])


def test_an_unseen_family_is_predicted_from_the_other_families_not_from_itself():
    rows, features, _centre = _data()
    out = family.leave_one_family_out("melting_point", rows, features, 0.01, GROUPS, min_training=10)
    # nitro labels are ~500 and the others ~100-300: a model that never saw nitro cannot reach them
    assert np.mean(out["nitro"]["models"]["candidate_c"]["signed"]) < -100.0


def test_a_family_with_too_few_training_entities_is_skipped_and_listed():
    rows, features, _ = _data(per_family=20)
    out = family.leave_one_family_out("melting_point", rows, features, 0.01, GROUPS, min_training=50)
    assert all("skipped" in v for v in out.values())


def test_the_summary_pools_the_families_and_carries_no_verdict():
    rows, features, _ = _data(per_family=40)
    out = family.leave_one_family_out("melting_point", rows, features, 0.01, GROUPS, min_training=10)
    reports = family.summarise("melting_point", out, 0.01)
    c = next(r for r in reports if r["model"] == "candidate_c")
    assert c["verdict"].startswith("none") and c["gate_eligible"] is False and c["ridge_penalty"] == 0.01
    assert c["pooled"]["n_predicted"] == sum(v["n_predicted"] for v in c["by_family"].values())
    assert all(v["claim_supported"] for v in c["by_family"].values())          # 40 per family is at least 30
    jb = next(r for r in reports if r["model"] == "joback")
    assert jb["ridge_penalty"] is None and jb["fitted_here"] is False


def test_a_family_under_thirty_predicted_entities_is_not_a_claim():
    rows, features, _ = _data(per_family=29)
    out = family.leave_one_family_out("melting_point", rows, features, 0.01, GROUPS, min_training=10)
    c = next(r for r in family.summarise("melting_point", out, 0.01) if r["model"] == "candidate_c")
    assert not any(v["claim_supported"] for v in c["by_family"].values())


# ------------------------------------------------------------------------------------- the committed report
RESULTS = BENCH / "results_family"


def _reports():
    return {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESULTS.glob("family_*.json"))}


def test_the_committed_reports_agree_with_the_corpus_summary_and_the_frozen_penalty():
    reports = _reports()
    assert len(reports) == 6
    summary = json.loads((BENCH / "corpus_summary.json").read_text(encoding="utf-8"))
    freeze = json.loads((BENCH / "results" / "freeze.json").read_text(encoding="utf-8"))
    for r in reports.values():
        assert r["pooled"]["n_test"] == summary["entities_with_resolved_label_in_primary_stratum"][r["target"]]
        assert r["verdict"].startswith("none") and r["gate_eligible"] is False
        if r["model"] == "candidate_c":
            assert r["ridge_penalty"] == freeze["penalties"][r["target"]]          # the penalty was not re-chosen
        else:
            assert r["ridge_penalty"] is None
    # every entity is in exactly one family: the per-family test counts add up to the whole
    for r in reports.values():
        assert sum(v["n_test"] for v in r["by_family"].values()) == r["pooled"]["n_test"]


def test_the_committed_family_report_is_what_the_generator_makes_from_the_committed_results():
    assert (BENCH / "FAMILY_REPORT.md").read_text(encoding="utf-8") == family.render(RESULTS)
