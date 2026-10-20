"""Runs protocol 2 of the synthesis quality benchmark (`PREREGISTRATION_2.md`, option 3a) and writes its verdict. OpenChem's own Python drives it; the planner runs in ITS Python, in a child process. Protocol 1's runner (`run_quality.py`) is not changed by this file.

    python run_quality_2.py draw   --paroutes DIR                       copy protocol 1's draw (and check it reproduces)
    python run_quality_2.py stock  --paroutes DIR --planner-python PY   the InChI-key stock file (compared with protocol 1's, if it is still on disk)
    python run_quality_2.py run    --paroutes DIR --planner-python PY --planner-data DIR   the searches (resumable; HOURS of CPU)
    python run_quality_2.py report --paroutes DIR                       report.txt, verdict.json and table.json
    python run_quality_2.py status

Same targets, planner, models, stock and search limits as protocol 1; the planner returns EVERY solved route (`--all-routes`) and the routes are ranked here, offline, by the PaRoutes route score with equal scores sharing a rank (`route_rank.py`). `judge.py` is applied UNCHANGED with the recovered claim read from M1 at k = 10. Run it ALONE: not beside the ORCA runs.
"""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p1 = _load("synthesis_quality_protocol1", "run_quality.py")
rank = _load("synthesis_quality_rank", "route_rank.py")
judge, validator, matching = p1.judge, p1.validator, p1.matching

RUNS = p1.RUNS
PROTOCOL1_DIR = HERE / "artifacts"
#: |M3 at 10 - protocol 1's recovered at 10| above this means this run does not reproduce protocol 1 (about two standard deviations of a fraction of 300 near 0.37); approved 2026-10-20.
CONSISTENCY_TOLERANCE = 0.05
#: The public model files' sizes as protocol 1 used them (`docs/SYNTHESIS_HELPER_DESIGN.md` 0b). Protocol 1 recorded no checksum of them, so the size is what can be compared; their MD5s are recorded now.
PROTOCOL1_MODEL_SIZES = {"uspto_model.onnx": 91518243, "uspto_templates.csv.gz": 3313598}


# --- records of protocol 1 ---------------------------------------------------------------------------------------------------


def normalised(identity: dict) -> dict:
    """The part of a planner identity that has to be the same in both protocols: the packages and Python, and what was selected. The configuration hash is left out because it contains the folder the stock file sits in."""
    return {"packages": identity["packages"], "python": identity["python"], "selection": identity["selection"]}


def read_records(path: Path) -> list[dict]:
    """A results file, from `path` or from its gzipped copy (what is committed)."""
    if path.exists():
        return p1.read_lines(path)
    packed = Path(str(path) + ".gz")
    if packed.exists():
        with gzip.open(packed, "rt", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    return []


def protocol1_reference(directory: Path) -> dict:
    """What protocol 2 is compared with, read from protocol 1's committed records: its recovered-at-10 fraction, its planner identity, and the checksums of its inputs."""
    verdict = json.loads((directory / "verdict.json").read_text(encoding="utf-8"))
    records = read_records(directory / "results_r1.jsonl")
    provenance = p1.read_lines(directory / "provenance.jsonl")
    stock_keys = directory / "stock_n1_inchikeys.txt"
    return {
        "recovered": verdict["claims"]["recovered"]["value"],
        "identity": normalised(records[0]["identity"]) if records else None,
        "inputs": provenance[0]["inputs"] if provenance else {},
        "stock_keys_md5": p1.md5(stock_keys) if stock_keys.exists() else None,
    }


# --- one target ------------------------------------------------------------------------------------------------------------


def _empty_row(index: int) -> dict:
    return {"index": index, "failed": True, "solved": False, "recovered_at_1": False, "recovered_at_5": False, "recovered_at_10": False, "top1_has_reaction": False, "top1_valid": False,
            "leaf_overlap": None, "top1_shorter": None, "route_count": 0, "m2": [False] * 3, "m3": [False] * 3, "pool": False, "routes_rank10": 0, "distinct_ranks": 0, "first_hit_rank": None}


def target_row(reference_route: dict, record: dict) -> dict:
    """One target's outcome. The judge's `recovered_at_*` fields are M1 (the PaRoutes count); M2, M3 and the pool ride beside them. The first route is the first of M2's order."""
    row = _empty_row(record["id"])
    if record["status"] != "completed":
        return row
    routes = record["routes"]
    row["failed"] = False
    row["solved"] = bool(record["statistics"].get("is_solved"))
    row["route_count"] = len(routes)
    analysis = rank.analyse(routes, reference_route)
    row["recovered_at_1"], row["recovered_at_5"], row["recovered_at_10"] = (analysis.m1(k) for k in (1, 5, 10))
    row["m2"] = [analysis.m2(k) for k in (1, 5, 10)]
    row["m3"] = [analysis.m3(k) for k in (1, 5, 10)]
    row["pool"] = analysis.pool()
    row["routes_rank10"] = analysis.routes_within_rank(10)
    row["distinct_ranks"] = analysis.distinct_ranks()
    row["first_hit_rank"] = analysis.first_hit_rank()
    if routes:
        first = routes[analysis.user_order[0]]
        checked = validator.validate_route(first)
        row["top1_has_reaction"] = checked.steps > 0
        row["top1_valid"] = checked.fully_validated
        row["leaf_overlap"] = matching.leaf_overlap(first, reference_route)
        row["top1_shorter"] = matching.is_shorter(first, reference_route)
    return row


# --- the report ------------------------------------------------------------------------------------------------------------


def problems(provenance: list[dict], records_by_run: dict[str, list[dict]], reference: dict) -> list[str]:
    """Everything that makes the run not comparable with protocol 1 (each is a reason for NOT EVALUABLE)."""
    found = []
    commits = {p["commit"] for p in provenance}
    if len(commits) > 1:
        found.append(f"the runs come from {len(commits)} commits: {sorted(c[:8] for c in commits)}")
    if any(p["dirty"] for p in provenance):
        found.append("some runs were made with a dirty src/")
    identities = {json.dumps(normalised(r["identity"]), sort_keys=True) for records in records_by_run.values() for r in records}
    if len(identities) > 1:
        found.append(f"the records carry {len(identities)} planner identities")
    elif identities and reference["identity"] is not None and json.loads(next(iter(identities))) != reference["identity"]:
        found.append("the planner identity (packages, Python, selection) differs from protocol 1's")
    limits = {json.dumps({k: v for k, v in r["limits"].items() if k != "all_routes"}, sort_keys=True) for records in records_by_run.values() for r in records}
    if len(limits) > 1:
        found.append("the search limits differ between records")
    if any(not r["limits"].get("all_routes") for records in records_by_run.values() for r in records):
        found.append("some records were made without --all-routes")
    for p in provenance:
        theirs, ours = reference["inputs"], p["inputs"]
        for name in ("targets_n1.txt", "stock_n1.txt"):
            if name in theirs and name in ours and theirs[name] != ours[name]:
                found.append(f"{name} differs from protocol 1's (checksum)")
        sizes = {name: ours.get(f"{name} size") for name in PROTOCOL1_MODEL_SIZES}
        for name, size in PROTOCOL1_MODEL_SIZES.items():
            if sizes[name] is not None and sizes[name] != size:
                found.append(f"{name} is {sizes[name]} bytes, protocol 1's was {size}")
        if reference["stock_keys_md5"] and ours.get("stock_n1_inchikeys.txt") not in (None, reference["stock_keys_md5"]):
            found.append("the InChI-key stock differs from protocol 1's")
    return list(dict.fromkeys(found))


def report_text(reference_routes: list[dict], records_by_run: dict[str, list[dict]], provenance: list[dict], draw_record: dict, protocol1: dict) -> tuple[str, dict, list[dict]]:
    by_run = {label: {r["id"]: r for r in records} for label, records in records_by_run.items()}
    rows = [target_row(reference_routes[i], by_run["r1"][i]) for i in draw_record["main"] if i in by_run["r1"]]
    rows += [_empty_row(i) for i in draw_record["main"] if i not in by_run["r1"]]
    stability = []
    for i in draw_record["stability"]:
        flags = [bool(by_run[label][i]["statistics"].get("is_solved")) for label in RUNS if i in by_run.get(label, {}) and by_run[label][i]["status"] == "completed"]
        if len(flags) == len(RUNS):
            stability.append({"index": i, "solved": flags})
    result = judge.judge(rows, stability)
    n = len(rows) or 1
    fraction = lambda predicate: sum(1 for r in rows if predicate(r)) / n  # noqa: E731
    m3_at_10 = fraction(lambda r: r["m3"][2])
    found = problems(provenance, records_by_run, protocol1)
    if abs(m3_at_10 - protocol1["recovered"]) > CONSISTENCY_TOLERANCE:
        found.append(f"M3 at 10 is {m3_at_10:.3f}, protocol 1's recovered at 10 was {protocol1['recovered']:.3f}: more than {CONSISTENCY_TOLERANCE} apart, so this run does not reproduce protocol 1")
    overall = judge.NOT_EVALUABLE if found else result["overall"]
    done = [r for r in rows if not r["failed"]]
    m1, m2, m3 = fraction(lambda r: r["recovered_at_10"]), fraction(lambda r: r["m2"][2]), m3_at_10
    lines = [f"QUALITY BENCHMARK, PROTOCOL 2 (all solved routes, PaRoutes ranking): {len(rows)} targets drawn, {result['failed']} failed or missing" + ("".join(f"; REFUSED: {p}" for p in found) if found else ""),
             f"VERDICT (protocol 2) {overall}; protocol 1's PARTIAL stands as measured", ""]
    for key in ("solved", "recovered", "valid", "stable"):
        claim = result["claims"][key]
        shown = "-" if claim.value is None else (f"{claim.value:.0f} of {result['stability_targets']}" if key == "stable" else f"{claim.value:.3f}")
        name = claim.name + (" [M1: the PaRoutes top-10]" if key == "recovered" else "")
        lines.append(f"{name:70s} {shown:>8s}  {claim.verdict}")
    lines += ["", "THE DECOMPOSITION (recovered at 10; each step changes one thing):",
              f"  protocol 1 (planner's order, 5 to 25 routes returned):                     {protocol1['recovered']:.3f}",
              f"  M3  planner's own order over the full pool (consistency check):             {m3:.3f}",
              f"  M2  first 10 routes ranked by route score (the user-facing count):          {m2:.3f}",
              f"  M1  every route in the first 10 score levels (the PaRoutes count):          {m1:.3f}",
              f"  pool: the reference is anywhere among the returned routes (the ceiling):    {fraction(lambda r: r['pool']):.3f}",
              "", "reported, deciding nothing:",
              f"  M1 at 1 / 5 / 10: {fraction(lambda r: r['recovered_at_1']):.3f} / {fraction(lambda r: r['recovered_at_5']):.3f} / {m1:.3f} (published, reference-excluding model: 0.20 / 0.55 / 0.61)",
              f"  M2 at 1 / 5 / 10: {fraction(lambda r: r['m2'][0]):.3f} / {fraction(lambda r: r['m2'][1]):.3f} / {m2:.3f}",
              f"  M3 at 1 / 5 / 10: {fraction(lambda r: r['m3'][0]):.3f} / {fraction(lambda r: r['m3'][1]):.3f} / {m3:.3f}"]
    if done:
        counts = sorted(r["route_count"] for r in done)
        tier = sorted(r["routes_rank10"] for r in done)
        levels = sorted(r["distinct_ranks"] for r in done)
        hits = sorted(r["first_hit_rank"] for r in done if r["first_hit_rank"] is not None)
        lines += [f"  routes returned per target (median / max): {counts[len(counts) // 2]} / {counts[-1]}",
                  f"  routes inside the PaRoutes top-10 (median / max): {tier[len(tier) // 2]} / {tier[-1]}; distinct score levels (median / max): {levels[len(levels) // 2]} / {levels[-1]}",
                  f"  score level of the best-ranked matching route (median, over targets that have one): {hits[len(hits) // 2] if hits else '-'}",
                  f"  targets with a first route that has a reaction: {result['with_reaction']}; of those fully validated: {sum(1 for r in done if r['top1_has_reaction'] and r['top1_valid'])}"]
        overlap = [r["leaf_overlap"] for r in done if r["leaf_overlap"] is not None]
        if overlap:
            lines.append(f"  mean leaf overlap of the first route with the reference: {sum(overlap) / len(overlap):.3f}; first route shorter than the reference: {sum(1 for r in done if r['top1_shorter']) / len(done):.3f}")
    if by_run["r1"]:
        seconds = sorted(r["seconds"] for r in by_run["r1"].values())
        lines.append(f"  seconds per target (median, run r1): {seconds[len(seconds) // 2]:.1f}; peak working set seen (MB): {max((r.get('peak_working_set_mb') or 0) for r in by_run['r1'].values()):.0f}")
    reading = ("the shortfall was protocol: pool, ranking and tie-counting explain protocol 1's PARTIAL (quote M2 beside any PaRoutes-style figure)" if m1 >= judge.RECOVERED_PASS
               else "partly protocol: the decomposition says how much; nothing is explained away; the narrowed claim stands" if m1 >= judge.RECOVERED_PARTIAL
               else "not protocol: the public model does not recover the reference routes at the published rate however they are counted; options 3b and 3c are next")
    lines += ["", "PREREGISTERED READING OF M1 AT 10 (" + ("not evaluable, so none applies" if found else f"{m1:.3f}") + "): " + ("-" if found else reading), "",
              "CONTAMINATION: the same public ONNX model, probably trained on these reference reactions; recovery is not evidence that the planner generalises (PREREGISTRATION.md).",
              "M1 counts tied score levels and is generous by construction; the user-facing count is M2. Feasibility is not measured and is never reported."]
    summary = {"protocol": 2, "overall": overall, "problems": found, "protocol1_recovered": protocol1["recovered"], "m1": m1, "m2": m2, "m3": m3,
               "claims": {k: {"value": c.value, "verdict": c.verdict} for k, c in result["claims"].items()}}
    return "\n".join(lines), summary, rows


# --- the commands -----------------------------------------------------------------------------------------------------------


def run_stage(args, out: Path) -> None:
    paroutes, data, python = Path(args.paroutes), Path(args.planner_data), args.planner_python
    draw_record = json.loads((out / "draw.json").read_text(encoding="utf-8"))
    targets = p1.read_targets(paroutes)
    stock = out / "stock_n1_inchikeys.txt"
    if not stock.exists():
        raise SystemExit("run the stock stage first")
    config = out / "planner_config.json"
    config.write_text(json.dumps(p1.planner_config(data, stock)), encoding="utf-8")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src"], capture_output=True, text=True, cwd=REPO).stdout.strip())
    inputs = {p.name: p1.md5(p) for p in (paroutes / "targets_n1.txt", paroutes / "stock_n1.txt", stock)}
    for name in PROTOCOL1_MODEL_SIZES:
        inputs[name] = p1.md5(data / name)
        inputs[f"{name} size"] = (data / name).stat().st_size
    with (out / "provenance.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"protocol": 2, "commit": commit, "dirty": dirty, "config_md5": p1.md5(config), "inputs": inputs}) + "\n")
    plan = [("r1", draw_record["main"]), ("r2", draw_record["stability"]), ("r3", draw_record["stability"])]
    for label, indices in plan:
        listing = out / f"targets_{label}.json"
        listing.write_text(json.dumps([{"id": i, "smiles": targets[i]} for i in indices]), encoding="utf-8")
        print(f"[{label}] {len(indices)} targets", flush=True)
        command = [python, str(HERE / "plan_batch.py"), "--config", str(config), "--stock", p1.STOCK_KEY, "--targets", str(listing), "--out", str(out / f"results_{label}.jsonl"), "--run-label", label,
                   "--iteration-limit", str(p1.ITERATION_LIMIT), "--time-limit", str(p1.TIME_LIMIT), "--max-transforms", str(p1.MAX_TRANSFORMS), "--filter", "none", "--all-routes"]
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
    parser.add_argument("--out", default=str(HERE / "artifacts_protocol2"))
    parser.add_argument("--protocol1", default=str(PROTOCOL1_DIR))
    args = parser.parse_args()
    out, first = Path(args.out), Path(args.protocol1)
    out.mkdir(parents=True, exist_ok=True)
    if args.command == "draw":
        record = json.loads((first / "draw.json").read_text(encoding="utf-8"))
        again = p1.draw(len(p1.read_targets(Path(args.paroutes))))
        if again != record:
            raise SystemExit("protocol 1's draw.json does not reproduce from the seed; refusing to continue")
        (out / "draw.json").write_text(json.dumps(record), encoding="utf-8")
        print(f"copied protocol 1's draw: {len(record['main'])} targets, stability {record['stability']}")
    elif args.command == "stock":
        done = subprocess.run([args.planner_python, str(HERE / "make_stock.py"), str(Path(args.paroutes) / "stock_n1.txt"), str(out / "stock_n1_inchikeys.txt")])
        theirs = first / "stock_n1_inchikeys.txt"
        if done.returncode == 0 and theirs.exists():
            print("stock identical to protocol 1's:", p1.md5(theirs) == p1.md5(out / "stock_n1_inchikeys.txt"))
        raise SystemExit(done.returncode)
    elif args.command == "run":
        run_stage(args, out)
    elif args.command == "status":
        for label in RUNS:
            print(label, len(p1.read_lines(out / f"results_{label}.jsonl")), "records")
    else:
        reference = json.loads((Path(args.paroutes) / "ref_routes_n1.json").read_text(encoding="utf-8"))
        records = {label: p1.read_lines(out / f"results_{label}.jsonl") for label in RUNS}
        text, summary, rows = report_text(reference, records, p1.read_lines(out / "provenance.jsonl"), json.loads((out / "draw.json").read_text(encoding="utf-8")), protocol1_reference(first))
        print(text)
        (out / "report.txt").write_text(text, encoding="utf-8")
        (out / "verdict.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        (out / "table.json").write_text(json.dumps(rows), encoding="utf-8")


if __name__ == "__main__":
    main()
