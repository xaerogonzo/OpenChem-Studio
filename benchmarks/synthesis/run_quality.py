"""Runs the quality benchmark of `PREREGISTRATION.md` and writes its verdict. OpenChem's own Python drives it; the planner runs in ITS Python, in a child process.

    python run_quality.py draw   --paroutes DIR                       the seeded target draw (no planner)
    python run_quality.py stock  --paroutes DIR --planner-python PY   the InChI-key stock file the planner reads (a few seconds)
    python run_quality.py run    --paroutes DIR --planner-python PY --planner-data DIR   the searches (resumable; HOURS of CPU)
    python run_quality.py report --paroutes DIR                       report.txt and verdict.json
    python run_quality.py status

`DIR` holds `targets_n1.txt`, `stock_n1.txt` and `ref_routes_n1.json` of PaRoutes 2.0 (Zenodo 10.5281/zenodo.7341155). `--planner-data` is the folder `download_public_data` filled.
**Every rule is in `PREREGISTRATION.md`; the matching is `route_match.py`, the route checks `route_validator.py`, the verdict `judge.py`.** A report is refused (NOT EVALUABLE) for records from more than one commit, made with a dirty `src/`, or with more than one planner identity.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

#: The draw, fixed in the preregistration: indices of `targets_n1.txt` (0-based) seen in the spike are excluded, then 300 are drawn with this seed; the first 20 of the draw are the stability targets.
SEED = 20261019
SEEN_IN_SPIKE = (0, 1, 2)
DRAW_SIZE = 300
STABILITY_SIZE = 20
ITERATION_LIMIT = 500
TIME_LIMIT = 1800
MAX_TRANSFORMS = 10
#: The planner's configuration, fixed: the public ONNX USPTO policy, NO filter (the configuration the published numbers describe) and the set's own stock.
STOCK_KEY = "n1"
RUNS = ("r1", "r2", "r3")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


validator = _load("synthesis_quality_validator", "route_validator.py")
matching = _load("synthesis_quality_match", "route_match.py")
judge = _load("synthesis_quality_judge", "judge.py")


# --- the draw ---------------------------------------------------------------------------------------------------------------


def read_targets(paroutes: Path) -> list[str]:
    return [line.strip() for line in (paroutes / "targets_n1.txt").read_text(encoding="utf-8").splitlines() if line.strip()]


def draw(total: int) -> dict:
    """The seeded draw: `DRAW_SIZE` indices without replacement from everything except what the spike saw, and the first `STABILITY_SIZE` of them for the repeated runs."""
    pool = sorted(set(range(total)) - set(SEEN_IN_SPIKE))
    main = random.Random(SEED).sample(pool, DRAW_SIZE)
    return {"seed": SEED, "excluded": list(SEEN_IN_SPIKE), "size": DRAW_SIZE, "main": main, "stability": main[:STABILITY_SIZE]}


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324 - an integrity label for the record, not security


# --- the planner's configuration ---------------------------------------------------------------------------------------------


def planner_config(data: Path, stock_keys: Path) -> dict:
    """The configuration dictionary handed to the planner (a dict, read as UTF-8: a YAML file with a non-ASCII path is mis-decoded by the library)."""
    return {"expansion": {"uspto": [str(data / "uspto_model.onnx"), str(data / "uspto_templates.csv.gz")]}, "stock": {STOCK_KEY: str(stock_keys)}}


# --- reading the results ----------------------------------------------------------------------------------------------------


def read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def target_row(reference_route: dict, record: dict) -> dict:
    """One target's outcome from the planner's record and the reference route: failed, solved, recovered at 1, 5 and 10, whether the first route has a reaction and is fully validated, and the reported-only measures."""
    row = {"index": record["id"], "failed": record["status"] != "completed", "solved": False, "recovered_at_1": False, "recovered_at_5": False, "recovered_at_10": False,
           "top1_has_reaction": False, "top1_valid": False, "leaf_overlap": None, "top1_shorter": None, "route_count": 0}
    if row["failed"]:
        return row
    routes = record["routes"]
    row["solved"] = bool(record["statistics"].get("is_solved"))
    row["route_count"] = len(routes)
    row["recovered_at_1"], row["recovered_at_5"], row["recovered_at_10"] = (matching.recovered_at(routes, reference_route, k) for k in (1, 5, 10))
    if routes:
        checked = validator.validate_route(routes[0])
        row["top1_has_reaction"] = checked.steps > 0
        row["top1_valid"] = checked.fully_validated
        row["leaf_overlap"] = matching.leaf_overlap(routes[0], reference_route)
        row["top1_shorter"] = matching.is_shorter(routes[0], reference_route)
    return row


def provenance_problem(provenance: list[dict], identities: set[str]) -> str | None:
    commits = {p["commit"] for p in provenance}
    if len(commits) > 1:
        return f"the runs come from {len(commits)} commits: {sorted(c[:8] for c in commits)}"
    if any(p["dirty"] for p in provenance):
        return "some runs were made with a dirty src/"
    if len(identities) > 1:
        return f"the records carry {len(identities)} planner identities"
    return None


def report_text(reference: list[dict], records_by_run: dict[str, list[dict]], provenance: list[dict], draw_record: dict) -> tuple[str, dict]:
    main_ids = draw_record["main"]
    by_run = {label: {r["id"]: r for r in records} for label, records in records_by_run.items()}
    rows = [target_row(reference[i], by_run["r1"][i]) for i in main_ids if i in by_run["r1"]]
    missing = [i for i in main_ids if i not in by_run["r1"]]
    rows += [{"index": i, "failed": True, "solved": False, "recovered_at_1": False, "recovered_at_5": False, "recovered_at_10": False, "top1_has_reaction": False, "top1_valid": False,
              "leaf_overlap": None, "top1_shorter": None, "route_count": 0} for i in missing]
    stability = []
    for i in draw_record["stability"]:
        flags = [bool(by_run[label][i]["statistics"].get("is_solved")) for label in RUNS if i in by_run.get(label, {}) and by_run[label][i]["status"] == "completed"]
        if len(flags) == len(RUNS):
            stability.append({"index": i, "solved": flags})
    result = judge.judge(rows, stability)
    identities = {json.dumps(r["identity"], sort_keys=True) for records in records_by_run.values() for r in records}
    problem = provenance_problem(provenance, identities)
    overall = judge.NOT_EVALUABLE if problem else result["overall"]
    n = len(rows) or 1
    done = [r for r in rows if not r["failed"]]
    overlap = [r["leaf_overlap"] for r in done if r["leaf_overlap"] is not None]
    lines = [f"QUALITY BENCHMARK: {len(rows)} targets drawn, {result['failed']} failed or missing" + (f"; REFUSED: {problem}" if problem else ""), f"VERDICT {overall}", ""]
    for key in ("solved", "recovered", "valid", "stable"):
        claim = result["claims"][key]
        shown = "-" if claim.value is None else (f"{claim.value:.0f} of {result['stability_targets']}" if key == "stable" else f"{claim.value:.3f}")
        lines.append(f"{claim.name:62s} {shown:>10s}  {claim.verdict}")
    lines += ["", "reported, deciding nothing:",
              f"  recovered at 1 / 5 / 10: {sum(r['recovered_at_1'] for r in rows) / n:.3f} / {sum(r['recovered_at_5'] for r in rows) / n:.3f} / {sum(r['recovered_at_10'] for r in rows) / n:.3f} (published, uncontaminated model, tree edit distance: 0.20 / 0.55 / 0.61)",
              f"  mean leaf overlap of the first route with the reference: {sum(overlap) / len(overlap):.3f}" if overlap else "  mean leaf overlap: -",
              f"  first route shorter than the reference: {sum(1 for r in done if r['top1_shorter']) / (len(done) or 1):.3f}",
              f"  targets with a first route that has a reaction: {result['with_reaction']}; of those fully validated: {sum(1 for r in done if r['top1_has_reaction'] and r['top1_valid'])}",
              f"  seconds per target (median, run r1): {sorted(r['seconds'] for r in by_run['r1'].values())[len(by_run['r1']) // 2]:.1f}" if by_run["r1"] else "  seconds: -",
              f"  peak working set seen (MB): {max((r.get('peak_working_set_mb') or 0) for r in by_run['r1'].values()):.0f}" if by_run["r1"] else "",
              "", "CONTAMINATION: the public ONNX models may have been trained on these reference reactions; recovery is not evidence that the planner generalises (PREREGISTRATION.md).",
              "Feasibility is not measured and is never reported."]
    return "\n".join(lines), {"overall": overall, "problem": problem, "claims": {k: {"value": c.value, "verdict": c.verdict} for k, c in result["claims"].items()}}


# --- the commands -----------------------------------------------------------------------------------------------------------


def run_stage(args, out: Path) -> None:
    paroutes, data, python = Path(args.paroutes), Path(args.planner_data), args.planner_python
    draw_record = json.loads((out / "draw.json").read_text(encoding="utf-8"))
    targets = read_targets(paroutes)
    config = out / "planner_config.json"
    config.write_text(json.dumps(planner_config(data, out / "stock_n1_inchikeys.txt")), encoding="utf-8")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src"], capture_output=True, text=True, cwd=REPO).stdout.strip())
    with (out / "provenance.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"commit": commit, "dirty": dirty, "config_md5": md5(config), "inputs": {p.name: md5(p) for p in (paroutes / "targets_n1.txt", paroutes / "stock_n1.txt")}}) + "\n")
    plan = [("r1", draw_record["main"]), ("r2", draw_record["stability"]), ("r3", draw_record["stability"])]
    for label, indices in plan:
        listing = out / f"targets_{label}.json"
        listing.write_text(json.dumps([{"id": i, "smiles": targets[i]} for i in indices]), encoding="utf-8")
        print(f"[{label}] {len(indices)} targets", flush=True)
        command = [python, str(HERE / "plan_batch.py"), "--config", str(config), "--stock", STOCK_KEY, "--targets", str(listing), "--out", str(out / f"results_{label}.jsonl"), "--run-label", label,
                   "--iteration-limit", str(ITERATION_LIMIT), "--time-limit", str(TIME_LIMIT), "--max-transforms", str(MAX_TRANSFORMS), "--filter", "none"]
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=sys.stderr, text=True)
        print(completed.stdout.strip(), flush=True)
        if completed.returncode:
            raise SystemExit(f"the planner batch {label} exited {completed.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["draw", "stock", "run", "report", "status"])
    parser.add_argument("--paroutes")
    parser.add_argument("--planner-python")
    parser.add_argument("--planner-data")
    parser.add_argument("--out", default=str(HERE / "artifacts"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.command == "draw":
        record = draw(len(read_targets(Path(args.paroutes))))
        (out / "draw.json").write_text(json.dumps(record), encoding="utf-8")
        print(f"drawn {len(record['main'])} of {len(set(range(10000)) - set(SEEN_IN_SPIKE))} (seed {SEED}); stability {record['stability']}")
    elif args.command == "stock":
        done = subprocess.run([args.planner_python, str(HERE / "make_stock.py"), str(Path(args.paroutes) / "stock_n1.txt"), str(out / "stock_n1_inchikeys.txt")])
        raise SystemExit(done.returncode)
    elif args.command == "run":
        run_stage(args, out)
    elif args.command == "status":
        for label in RUNS:
            print(label, len(read_lines(out / f"results_{label}.jsonl")), "records")
    else:
        reference = json.loads((Path(args.paroutes) / "ref_routes_n1.json").read_text(encoding="utf-8"))
        records = {label: read_lines(out / f"results_{label}.jsonl") for label in RUNS}
        text, verdict = report_text(reference, records, read_lines(out / "provenance.jsonl"), json.loads((out / "draw.json").read_text(encoding="utf-8")))
        print(text)
        (out / "report.txt").write_text(text, encoding="utf-8")
        (out / "verdict.json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
