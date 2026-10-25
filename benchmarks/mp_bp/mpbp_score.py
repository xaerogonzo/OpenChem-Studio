"""Phase 3 of `PREREGISTRATION.md`: score the candidates, in three stages that the code itself keeps apart.

    features    structure -> Joback and Marrero-Gani output for every primary-stratum entity (no label is read)
    select      fit Candidate C on DEVELOPMENT rows for each preregistered penalty, pick the penalty with the lowest
                SELECTION error, and write `freeze.json` (the penalties, the fitted coefficients, a hash of every file
                that decides a score, and the thresholds); nothing has seen a holdout label
    score       development or selection: any time. holdout: ONLY with `--confirm-holdout-once`, ONLY if every hashed
                file still matches `freeze.json`, and ONLY once -- a lock file is written before the first holdout
                label is read, and a second run refuses

The reference corpus is the one `mpbp_build.py` wrote (copyrighted values, outside Git). The gate reports are aggregate
and are what the repository keeps; per-entity predictions stay beside the corpus.

Every threshold below is the preregistered number, read from section 10; none is tuned. `evaluate_gate` is pure and is
tested on made-up numbers, including each way a method can fail to pass.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
JUDGE_VERSION = "mp_bp-judge-1"

PROPERTIES = ("melting_point", "normal_boiling_point")

#: Section 10: the published-error references and the two multiples. `None` means the output is not gate-eligible.
REFERENCE_ERROR_K = {
    ("joback", "normal_boiling_point"): 12.9,
    ("marrero_gani", "melting_point"): 24.90,
    ("marrero_gani", "normal_boiling_point"): 7.90,
    ("candidate_c", "normal_boiling_point"): 12.9,
    ("candidate_c", "melting_point"): 22.6,
}
POINT_FACTOR = 1.5
UPPER_FACTOR = 2.0
MIN_IMPROVEMENT = 0.20
MIN_IMPROVEMENT_LOWER = 0.10
MIN_COVERAGE = 0.70
MIN_PAIRED = 300
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261025
MIN_STRATUM = 30

#: Which model output answers which property. Joback's Tf is a FREEZING point: a diagnostic proxy for Tm, never gate-eligible.
MODELS = {
    "melting_point": (
        {"model": "joback", "output": "tf", "gate_eligible": False, "target_matched": False},
        {"model": "marrero_gani", "output": "tm", "gate_eligible": True, "target_matched": True},
        {"model": "candidate_c", "output": "tm", "gate_eligible": True, "target_matched": True},
    ),
    "normal_boiling_point": (
        {"model": "joback", "output": "tb", "gate_eligible": True, "target_matched": True},
        {"model": "marrero_gani", "output": "tb", "gate_eligible": True, "target_matched": True},
        {"model": "candidate_c", "output": "tb", "gate_eligible": True, "target_matched": True},
    ),
}

#: Files whose contents decide a score. Their hashes go into `freeze.json`, and the holdout refuses if one changed.
FROZEN_FILES = (
    "benchmarks/mp_bp/mpbp_score.py", "benchmarks/mp_bp/mpbp_models.py", "benchmarks/mp_bp/PREREGISTRATION.md",
    "tools/validation_rows.py", "src/openchem/chem/joback.py", "src/openchem/chem/data/joback_groups.json",
    "benchmarks/thermophysical/marrero2001_groups.py", "benchmarks/thermophysical/marrero2001_table.py",
)


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def models_module():
    return _load("mpbp_models", HERE / "mpbp_models.py")


def vr_module():
    return _load("validation_rows", ROOT / "tools" / "validation_rows.py")


def file_hashes() -> dict[str, str]:
    return {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in FROZEN_FILES}


# ------------------------------------------------------------------------------------------------ statistics
def mean_abs(errors) -> float:
    return float(np.mean(errors))


def bootstrap(errors, baseline_errors, *, resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED):
    """Percentile 95% intervals, resampling ENTITIES, for the candidate's MAE and for its relative improvement over the
    baseline on the same entities. `errors` and `baseline_errors` are paired by position."""
    e = np.asarray(errors, dtype=float)
    b = np.asarray(baseline_errors, dtype=float)
    if len(e) != len(b) or len(e) == 0:
        raise ValueError("need paired, non-empty error lists")
    rng = np.random.default_rng(seed)
    n = len(e)
    maes = np.empty(resamples)
    imps = np.empty(resamples)
    chunk = 500
    for start in range(0, resamples, chunk):
        size = min(chunk, resamples - start)
        idx = rng.integers(0, n, size=(size, n))
        me = e[idx].mean(axis=1)
        mb = b[idx].mean(axis=1)
        maes[start:start + size] = me
        imps[start:start + size] = np.where(mb > 0, 1.0 - me / np.where(mb > 0, mb, 1.0), 0.0)
    lo, hi = 2.5, 97.5
    return ([float(np.percentile(maes, lo)), float(np.percentile(maes, hi))],
            [float(np.percentile(imps, lo)), float(np.percentile(imps, hi))])


def evaluate_gate(*, model: str, prop: str, gate_eligible: bool, leakage_status: str, paired: int,
                  coverage: float, mae: float, mae_ci: list[float], improvement: float, improvement_ci: list[float]) -> dict:
    """The preregistered PASS / FAIL / NOT EVALUABLE decision, each criterion shown (section 10).

    NOT_EVALUABLE when the output is not gate-eligible, leakage is `unknown`, or there are fewer than 300 paired
    entities; the numeric criteria are still computed and returned, labelled, so an exploratory number is not hidden. A
    relaxed threshold is never applied."""
    reference = REFERENCE_ERROR_K.get((model, prop))
    criteria = {
        "leakage_not_unknown": leakage_status != "unknown",
        "point_mae_within_1.5x": reference is not None and mae <= POINT_FACTOR * reference,
        "upper_mae_within_2.0x": reference is not None and mae_ci[1] <= UPPER_FACTOR * reference,
        "improvement_at_least_20pct": improvement >= MIN_IMPROVEMENT,
        "improvement_lower_at_least_10pct": improvement_ci[0] >= MIN_IMPROVEMENT_LOWER,
        "coverage_at_least_70pct": coverage >= MIN_COVERAGE,
        "paired_at_least_300": paired >= MIN_PAIRED,
    }
    numeric = all(v for k, v in criteria.items() if k not in ("leakage_not_unknown", "paired_at_least_300"))
    if not gate_eligible:
        status, why = "NOT_EVALUABLE", "a diagnostic proxy: its output is not the target and it can never promote"
    elif leakage_status == "unknown":
        status, why = "NOT_EVALUABLE", "leakage for this (model, property) is unknown: no independent-holdout claim"
    elif paired < MIN_PAIRED:
        status, why = "NOT_EVALUABLE", f"fewer than {MIN_PAIRED} paired entities"
    else:
        status = "PASS" if all(criteria.values()) else "FAIL"
        why = "all criteria met" if status == "PASS" else "criteria not met: " + ", ".join(k for k, v in criteria.items() if not v)
    return {"evaluation_status": status, "reason": why, "criteria": criteria,
            "numeric_criteria_all_met": numeric, "reference_error_k": reference}


# ------------------------------------------------------------------------------------------------ the corpus
def load_corpus(corpus: Path) -> dict:
    entities = [json.loads(line) for line in (corpus / "entities.jsonl").read_text(encoding="utf-8").splitlines()]
    observations = [json.loads(line) for line in (corpus / "observations.jsonl").read_text(encoding="utf-8").splitlines()]
    summary = json.loads((corpus / "summary.json").read_text(encoding="utf-8"))
    accepted: dict[tuple[str, str], list[dict]] = {}
    for o in observations:
        if o["disposition"] in ("accepted_melting_point", "accepted_normal_boiling_point"):
            accepted.setdefault((o["identity_block"], o["property"]), []).append(o)
    return {"entities": entities, "accepted": accepted, "summary": summary,
            "primary": [e for e in entities if e["stratum"] == "primary"]}


def compute_features(corpus: dict, out: Path) -> dict:
    """Joback and Marrero-Gani output for every primary entity with a resolved label. Structure only."""
    m = models_module()
    features = {}
    for e in corpus["primary"]:
        if not any(l["status"] == "resolved" for l in e["labels"].values()):
            continue
        features[e["identity_block"]] = {"joback": m.joback_features(e["smiles"]), "mg": m.mg_features(e["smiles"])}
    out.write_text(json.dumps(features, sort_keys=True), encoding="utf-8")
    return features


def entity_rows(corpus: dict, prop: str, partition: str, *, label_choice: int = 0):
    """`(entity, ValidationRow)` for the primary entities with a resolved label for `prop` in `partition`.

    `label_choice` 0 is the preregistered label; k > 0 picks the k-th alternative admissible observation (the
    sensitivity analysis), clamped to the observations the entity has."""
    vr = vr_module()
    rows = []
    for e in corpus["primary"]:
        label = e["labels"].get(prop)
        if not label or label["status"] != "resolved" or e["partition"] != partition:
            continue
        obs = sorted(corpus["accepted"].get((e["identity_block"], prop), []), key=lambda o: (o["source"], o["entry"]))
        if label_choice == 0 or not obs:
            low, high, value, is_range = label["low_k"], label["high_k"], label["value_k"], label["is_range"]
            record = label["record_id"]
        else:
            o = obs[min(label_choice, len(obs) - 1)]
            low, high, value, is_range, record = o["low_k"], o["high_k"], o["value_k"], o["is_range"], o["record_id"]
        rows.append((e, vr.ValidationRow(
            row_id=e["identity_block"], smiles=e["smiles"], property=prop, value=float(value), units="K",
            source_id=label.get("record_id", "").split(":")[0] or "handbook", record_id=record, partition=partition,
            transition_type="melting" if prop == "melting_point" else "boiling", value_source="secondary",
            range_low=float(low) if is_range else None, range_high=float(high) if is_range else None)))
    return rows


# ------------------------------------------------------------------------------------------------ one report
def predict_all(prop: str, rows, features: dict, fits: dict, baseline: tuple[dict, float]) -> dict:
    """Per model: block -> Prediction; and the baseline's value per block."""
    m = models_module()
    out = {}
    for spec in MODELS[prop]:
        preds = {}
        for entity, _ in rows:
            feat = features[entity["identity_block"]]
            if spec["model"] == "joback":
                preds[entity["identity_block"]] = m.joback_prediction(feat["joback"], spec["output"])
            elif spec["model"] == "marrero_gani":
                preds[entity["identity_block"]] = m.mg_prediction(feat["mg"], spec["output"])
            else:
                preds[entity["identity_block"]] = fits[prop].predict(feat["joback"])
        out[spec["model"]] = preds
    by_family, overall = baseline
    out["__baseline__"] = {e["identity_block"]: m.baseline_prediction(e["family"], by_family, overall) for e, _ in rows}
    return out


def report_for(prop: str, spec: dict, rows, preds: dict, partition: str, corpus: dict, features, fits, baseline,
               frozen: dict, partitions_examined: list[dict]) -> dict:
    """The gate report for one (model, property) on one partition: the shape of section 10's example."""
    vr = vr_module()
    model = spec["model"]
    mine = preds[model]
    base = preds["__baseline__"]
    denominator = len(rows)
    paired = [(e, row) for e, row in rows if mine[e["identity_block"]].value is not None]
    errs = [vr.absolute_error(row, mine[e["identity_block"]].value) for e, row in paired]
    base_errs = [vr.absolute_error(row, base[e["identity_block"]]) for e, row in paired]
    signed = [mine[e["identity_block"]].value - row.value for e, row in paired]
    coverage = len(paired) / denominator if denominator else 0.0
    refusals = Counter(mine[e["identity_block"]].refusal for e, _ in rows if mine[e["identity_block"]].value is None)
    populations = {}
    if model == "candidate_c":
        populations = {(model, prop): frozenset(b for b, p in frozen["development_blocks"][prop].items())}
    leak_rows = [row for _, row in rows]
    leakage = vr.assess_leakage(leak_rows, model, populations,
                                no_overlap_evidence={}) if leak_rows else vr.LeakageAssessment(model, prop, "unknown")
    if model == "candidate_c" and not leakage.status.startswith("known"):
        raise AssertionError("Candidate C's fit population is the development partition: its status must be known")
    report: dict = {
        "target": prop, "model": model, "model_output": spec["output"], "target_matched": spec["target_matched"],
        "gate_eligible": spec["gate_eligible"], "partition": partition,
        "leakage": {"status": leakage.status, "evidence": leakage.evidence or (
            "fit population is the development partition of this corpus" if model == "candidate_c" else
            "the paper does not list its fit population"),
            "may_claim_independent_holdout": vr.may_claim_independent_holdout(leakage)},
        "counts": {"entities_considered": len([e for e in corpus["primary"]]),
                   "entities_with_eligible_target": denominator, "entities_predicted": len(paired),
                   "paired_with_baseline": len(paired)},
        "coverage": coverage, "refusals": dict(refusals),
    }
    if paired:
        mae_ci, imp_ci = bootstrap(errs, base_errs)
        base_mae = mean_abs(base_errs)
        improvement = 1.0 - mean_abs(errs) / base_mae if base_mae > 0 else 0.0
        report["metrics"] = {
            "mae": mean_abs(errs), "mae_ci95": mae_ci, "rmse": float(np.sqrt(np.mean(np.square(errs)))),
            "median_ae": float(statistics.median(errs)), "bias": float(np.mean(signed)),
            "baseline_mae_on_same_entities": base_mae, "improvement_over_baseline": improvement,
            "improvement_ci95": imp_ci}
        report["gate"] = evaluate_gate(
            model=model, prop=prop, gate_eligible=spec["gate_eligible"], leakage_status=leakage.status,
            paired=len(paired), coverage=coverage, mae=mean_abs(errs), mae_ci=mae_ci, improvement=improvement,
            improvement_ci=imp_ci)
        strata = {}
        for fam in sorted({e["family"] for e, _ in paired}):
            fam_errs = [er for (e, _), er in zip(paired, errs) if e["family"] == fam]
            strata[fam] = {"n": len(fam_errs), "mae": mean_abs(fam_errs), "claim_supported": len(fam_errs) >= MIN_STRATUM}
        report["strata"] = strata
        agree = [er for (e, _), er in zip(paired, errs) if e["labels"][prop].get("cross_source") == "agree"]
        report["label_quality_subset"] = {"cross_source_agree_n": len(agree),
                                           "cross_source_agree_mae": mean_abs(agree) if agree else None}
        alt = []
        for k in range(1, 4):
            alt_rows = {e["identity_block"]: row for e, row in entity_rows(corpus, prop, partition, label_choice=k)}
            alt_errs = [vr.absolute_error(alt_rows[e["identity_block"]], mine[e["identity_block"]].value)
                        for e, _ in paired if e["identity_block"] in alt_rows]
            alt.append(mean_abs(alt_errs))
        report["sensitivity"] = {"mae_range_over_alternative_observations": [min(alt + [mean_abs(errs)]), max(alt + [mean_abs(errs)])]}
    else:
        report["gate"] = {"evaluation_status": "NOT_EVALUABLE", "reason": "the model predicted no entity"}
    report["partitions_examined"] = partitions_examined
    report["provenance"] = {
        "source_file_hashes": {k: v["sha256"] for k, v in corpus["summary"]["source_files"].items()},
        "corpus_builder": corpus["summary"]["builder_version"], "split_manifest_hash": corpus["summary"]["manifest_checksum"],
        "judge_version": JUDGE_VERSION, "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "frozen_at_commit": frozen.get("commit"), "full_corpus_evaluated": True}
    report["limitations"] = [
        "reference values cannot be regenerated from the public repository (copyrighted handbook tables)",
        "handbook values contain printed errors; see CORPUS_REPORT.md",
    ]
    return report


def common_cohort(prop: str, rows, preds: dict) -> list[str]:
    return [e["identity_block"] for e, _ in rows
            if all(preds[s["model"]][e["identity_block"]].value is not None for s in MODELS[prop])]


# ------------------------------------------------------------------------------------------------ stages
def git_commit() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT, check=False).stdout.strip()


def git_dirty() -> bool:
    return bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, cwd=ROOT, check=False).stdout.strip())


def training_set(corpus: dict, prop: str, features: dict):
    """Development rows that Joback fragments: the fit population of Candidate C."""
    rows = entity_rows(corpus, prop, "development")
    X, y, blocks = [], [], {}
    for e, row in rows:
        j = features[e["identity_block"]]["joback"]
        if "counts" in j:
            X.append(j)
            y.append(row.value)
            blocks[e["identity_block"]] = e["family"]
    return X, y, blocks, rows


def baseline_for(corpus: dict, prop: str):
    m = models_module()
    rows = entity_rows(corpus, prop, "development")
    return m.family_baseline([e["family"] for e, _ in rows], [row.value for _, row in rows])


def stage_select(corpus_dir: Path, out: Path) -> dict:
    """Fit Candidate C on development rows for every preregistered penalty, pick each property's penalty by the lowest
    SELECTION error, and freeze. Reads development and selection labels; never a holdout label."""
    m = models_module()
    vr = vr_module()
    corpus = load_corpus(corpus_dir)
    features = json.loads((corpus_dir / "features.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(ROOT / "src"))
    from openchem.chem import joback

    all_groups = sorted(joback.groups())
    frozen = {"penalties": {}, "selection_mae_by_penalty": {}, "candidate_c": {}, "development_blocks": {}}
    for prop in PROPERTIES:
        X, y, blocks, _ = training_set(corpus, prop, features)
        sel_rows = entity_rows(corpus, prop, "selection")
        best = None
        table = {}
        for penalty in m.RIDGE_GRID:
            fit = m.fit_candidate_c(prop, penalty, X, y, all_groups)
            errs = [vr.absolute_error(row, p.value) for e, row in sel_rows
                    if (p := fit.predict(features[e["identity_block"]]["joback"])).value is not None]
            table[str(penalty)] = {"selection_mae": mean_abs(errs), "n": len(errs)}
            if best is None or mean_abs(errs) < best[0]:
                best = (mean_abs(errs), penalty, fit)
        frozen["penalties"][prop] = best[1]
        frozen["selection_mae_by_penalty"][prop] = table
        frozen["candidate_c"][prop] = best[2].to_json()
        frozen["development_blocks"][prop] = blocks
    frozen.update({"commit": git_commit(), "dirty_tree": git_dirty(), "file_hashes": file_hashes(),
                   "judge_version": JUDGE_VERSION, "frozen_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "manifest_checksum": corpus["summary"]["manifest_checksum"],
                   "thresholds": {"point_factor": POINT_FACTOR, "upper_factor": UPPER_FACTOR,
                                  "min_improvement": MIN_IMPROVEMENT, "min_improvement_lower": MIN_IMPROVEMENT_LOWER,
                                  "min_coverage": MIN_COVERAGE, "min_paired": MIN_PAIRED}})
    out.write_text(json.dumps(frozen, indent=1, sort_keys=True), encoding="utf-8")
    return frozen


def stage_score(corpus_dir: Path, frozen_path: Path, partition: str, out_dir: Path) -> list[dict]:
    m = models_module()
    corpus = load_corpus(corpus_dir)
    features = json.loads((corpus_dir / "features.json").read_text(encoding="utf-8"))
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for prop in PROPERTIES:
        rows = entity_rows(corpus, prop, partition)
        fits = {p: m.CandidateC.from_json(frozen["candidate_c"][p]) for p in PROPERTIES}
        preds = predict_all(prop, rows, features, fits, baseline_for(corpus, prop))
        examined = [{"partition": "development", "purpose": "fit Candidate C, build the baseline"},
                    {"partition": "selection", "purpose": "choose Candidate C's ridge penalty"}]
        if partition == "holdout":
            examined.append({"partition": "holdout", "purpose": "the single preregistered evaluation"})
        cohort = common_cohort(prop, rows, preds)
        for spec in MODELS[prop]:
            rep = report_for(prop, spec, rows, preds, partition, corpus, features, fits, baseline_for(corpus, prop), frozen, examined)
            rep["counts"]["all_method_common_cohort"] = len(cohort)
            reports.append(rep)
            (out_dir / f"{partition}_{prop}_{spec['model']}.json").write_text(
                json.dumps(rep, indent=1, sort_keys=True), encoding="utf-8")
    return reports


def stage_holdout(corpus_dir: Path, frozen_path: Path, out_dir: Path, *, confirmed: bool) -> list[dict]:
    """The one holdout evaluation. Refuses unless confirmed, unless every frozen file is byte-identical, and a second time."""
    lock = corpus_dir / "holdout_scored.lock"
    if not confirmed:
        raise SystemExit("refused: the holdout is scored once; pass --confirm-holdout-once")
    if lock.exists():
        raise SystemExit(f"refused: the holdout was already scored ({lock.read_text(encoding='utf-8').strip()})")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    changed = [k for k, v in file_hashes().items() if frozen["file_hashes"].get(k) != v]
    if changed:
        raise SystemExit(f"refused: files changed since the freeze: {changed}")
    if git_dirty():
        raise SystemExit("refused: the working tree has uncommitted changes to tracked files")
    lock.write_text(f"started {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} at {git_commit()}\n", encoding="utf-8")
    return stage_score(corpus_dir, frozen_path, "holdout", out_dir)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("features", "select", "score", "holdout"):
        p = sub.add_parser(name)
        p.add_argument("--corpus", type=Path, required=True)
        if name != "features":
            p.add_argument("--freeze", type=Path, required=True)
        if name in ("score", "holdout"):
            p.add_argument("--out", type=Path, required=True)
        if name == "score":
            p.add_argument("--partition", choices=("development", "selection"), required=True)
        if name == "holdout":
            p.add_argument("--confirm-holdout-once", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "features":
        compute_features(load_corpus(args.corpus), args.corpus / "features.json")
    elif args.cmd == "select":
        stage_select(args.corpus, args.freeze)
    elif args.cmd == "score":
        stage_score(args.corpus, args.freeze, args.partition, args.out)
    else:
        stage_holdout(args.corpus, args.freeze, args.out, confirmed=args.confirm_holdout_once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
