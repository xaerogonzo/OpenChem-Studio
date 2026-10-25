"""Runs protocol 3 of the synthesis quality benchmark (`PREREGISTRATION_3.md`, option 3c) and writes its reading. OpenChem's own Python drives it; the planner runs in ITS Python, in a child process.

    python run_quality_3.py prepare  --planner-python PY --planner-data DIR    references, the three stocks, the targets, the planner configuration
    python run_quality_3.py run      --planner-python PY --planner-data DIR    the searches (resumable; HOURS of CPU)
    python run_quality_3.py report                                              report.txt, verdict.json, table.json
    python run_quality_3.py status

The 51 references are `artifacts_protocol3/references/<stem>.json` whose decision is `route`; `refs_meta.json` gives each one's stratum, period, tier and publisher group. Settings are protocol 2's. The stocks are fixed in the preregistration: PRIMARY = protocol 2's n1 list plus every reference's own starting materials minus every reference's intermediates and targets; LEAVES = the starting materials only; ZINC = the application's own stock with nothing added. Runs: r1 on all three, r2 and r3 on the primary stock (the noise floor).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "artifacts_protocol3"
P2 = HERE / "artifacts_protocol2"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


j3 = _load("synthesis_quality_judge_3", "judge_3.py")
p2 = _load("synthesis_quality_protocol2_for_3", "run_quality_2.py")
p1 = p2.p1
rank, matching = j3.rank, j3.matching

#: The three stocks and the searches, in the order they run. (label, stock key, run label)
RUNS = [("primary", "primary", "primary-r1"), ("leaves", "leaves", "leaves-r1"), ("zinc", "zinc", "zinc-r1"), ("primary", "primary", "primary-r2"), ("primary", "primary", "primary-r3")]
#: Protocol 2's model files (sizes and md5s, `artifacts_protocol2/provenance.jsonl`): this run refuses if they differ.
MODEL_MD5 = {"uspto_model.onnx": "b466a436b6a8eceaba8c14ef5e2a88c8", "uspto_templates.csv.gz": "e8fb29d4dcd54073658000e212b7845a"}
SHOWN = 10


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324 - an integrity label for the record, not security


def read_lines(path: Path) -> list[dict]:
    if path.exists():
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    packed = Path(str(path) + ".gz")
    if packed.exists():
        with gzip.open(packed, "rt", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    return []


# --- the references ---------------------------------------------------------------------------------------------------------


def load_references() -> list[dict]:
    """The usable references in file-name order, each with its tree, depth, leaves, intermediates and metadata."""
    meta = json.loads((OUT / "refs_meta.json").read_text(encoding="utf-8"))
    refs = []
    for path in sorted((OUT / "references").glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("decision") != "route":
            continue
        tree = j3.reference_tree(document)
        refs.append({"id": len(refs), "stem": path.stem, "tree": tree, "target": tree["smiles"], "depth": j3.tree_depth(tree), "steps": len(document["reactions"]),
                     "leaves": sorted(j3.leaves_of(tree)), "intermediates": sorted(j3.intermediates_of(tree)), **meta[path.stem]})
    return refs


def stock_keys(refs: list[dict]) -> dict[str, list[str]]:
    """The primary and leaves-only stocks as InChI-key lists, plus the conflicts the preregistration says to report."""
    leaves = {s for r in refs for s in r["leaves"]}
    inter = {s for r in refs for s in r["intermediates"]}
    targets = {r["target"] for r in refs}
    conflicts = sorted((leaves & (inter | targets)))
    n1 = {line.strip() for line in (P2 / "stock_n1_inchikeys.txt").read_text(encoding="utf-8").splitlines() if line.strip()}
    ik = j3.inchikey
    leaf_keys = {ik(s) for s in leaves}
    remove = {ik(s) for s in (inter | targets)}
    primary = (n1 | leaf_keys) - remove
    return {"primary": sorted(primary), "leaves": sorted(leaf_keys - remove), "conflicts": conflicts, "n1_size": len(n1), "removed_from_n1": sorted((n1 & remove)), "removed_leaf_conflicts": len(leaf_keys & remove)}


def prepare(args) -> None:
    refs = load_references()
    keys = stock_keys(refs)
    OUT.mkdir(exist_ok=True)
    (OUT / "stocks").mkdir(exist_ok=True)
    for name in ("primary", "leaves"):
        (OUT / "stocks" / f"{name}_inchikeys.txt").write_text("\n".join(keys[name]) + "\n", encoding="utf-8", newline="\n")
    data = Path(args.planner_data)
    config = {"expansion": {"uspto": [str(data / "uspto_model.onnx"), str(data / "uspto_templates.csv.gz")]},
              "stock": {"primary": str(OUT / "stocks" / "primary_inchikeys.txt"), "leaves": str(OUT / "stocks" / "leaves_inchikeys.txt"), "zinc": str(data / "zinc_stock.hdf5")}}
    (OUT / "planner_config.json").write_text(json.dumps(config), encoding="utf-8")
    (OUT / "targets.json").write_text(json.dumps([{"id": r["id"], "smiles": r["target"]} for r in refs]), encoding="utf-8")
    summary = [{k: r[k] for k in ("id", "stem", "target", "depth", "steps", "leaves", "intermediates", "stratum", "year", "period", "tier", "publisher")} for r in refs]
    (OUT / "references.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"{len(refs)} references; depths {dict(sorted(Counter(r['depth'] for r in refs).items()))}")
    print(f"primary stock {len(keys['primary']):,} keys (n1 {keys['n1_size']:,}); leaves-only {len(keys['leaves'])}")
    print(f"a leaf of one route that is an intermediate or target of another (to run alone): {keys['conflicts'] or 'none'}")
    print(f"n1 molecules removed because a reference makes them: {len(keys['removed_from_n1'])}")


# --- the run ----------------------------------------------------------------------------------------------------------------


def run_stage(args) -> None:
    data, python = Path(args.planner_data), args.planner_python
    if not (OUT / "planner_config.json").exists():
        raise SystemExit("run the prepare stage first")
    for name, digest in MODEL_MD5.items():
        if md5(data / name) != digest:
            raise SystemExit(f"{name} is not protocol 2's model file (checksum); refusing to run")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src"], capture_output=True, text=True, cwd=REPO).stdout.strip())
    inputs = {p.name: md5(p) for p in (OUT / "stocks" / "primary_inchikeys.txt", OUT / "stocks" / "leaves_inchikeys.txt", OUT / "targets.json")}
    for name in MODEL_MD5:
        inputs[name] = md5(data / name)
        inputs[f"{name} size"] = (data / name).stat().st_size
    with (OUT / "provenance.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"protocol": 3, "commit": commit, "dirty": dirty, "config_md5": md5(OUT / "planner_config.json"), "inputs": inputs}) + "\n")
    for _, stock, label in RUNS:
        print(f"[{label}] stock {stock}", flush=True)
        command = [python, str(HERE / "plan_batch.py"), "--config", str(OUT / "planner_config.json"), "--stock", stock, "--targets", str(OUT / "targets.json"), "--out", str(OUT / f"results_{label}.jsonl"),
                   "--run-label", label, "--iteration-limit", str(p1.ITERATION_LIMIT), "--time-limit", str(p1.TIME_LIMIT), "--max-transforms", str(p1.MAX_TRANSFORMS), "--filter", "none", "--all-routes"]
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=sys.stderr, text=True)
        print(completed.stdout.strip(), flush=True)
        if completed.returncode:
            raise SystemExit(f"the planner batch {label} exited {completed.returncode}")


# --- the judgement ----------------------------------------------------------------------------------------------------------


def target_row(ref: dict, record: dict | None) -> dict:
    row = {"id": ref["id"], "stem": ref["stem"], "depth": ref["depth"], "steps": ref["steps"], "tier": ref["tier"], "period": ref["period"], "stratum": ref["stratum"], "publisher": ref["publisher"], "failed": record is None or record["status"] != "completed"}
    if row["failed"]:
        return row
    routes = record["routes"]
    row["solved"] = bool(record["statistics"].get("is_solved"))
    row["route_count"] = len(routes)
    if not routes:
        row.update(m1_10=False, m2_1=False, m2_5=False, m2_10=False, m3_10=False, pool=False, lenient_m2_10=False, lenient_pool=False, same_materials_any=False, same_materials_first10=False, recall=j3.reaction_recall([], ref["tree"]))
        return row
    an = rank.analyse(routes, ref["tree"])
    first10 = [routes[i] for i in an.user_order[:SHOWN]]
    row.update(m1_10=an.m1(10), m2_1=an.m2(1), m2_5=an.m2(5), m2_10=an.m2(10), m3_10=an.m3(10), pool=an.pool(),
               lenient_m2_10=any(j3.lenient_match(r, ref["tree"]) for r in first10), lenient_pool=any(j3.lenient_match(r, ref["tree"]) for r in routes),
               same_materials_any=any(j3.same_materials_route(r, ref["tree"]) for r in routes), same_materials_first10=any(j3.same_materials_route(r, ref["tree"]) for r in first10),
               first_hit_rank=an.first_hit_rank(), recall=j3.reaction_recall(routes, ref["tree"]))
    return row


def rate(rows: list[dict], key: str) -> dict:
    k, n = sum(1 for r in rows if r.get(key)), len(rows)
    low, high = j3.wilson(k, n)
    return {"k": k, "n": n, "rate": round(k / n, 3) if n else None, "interval_95": [round(low, 3), round(high, 3)]}


def groups(rows: list[dict], key: str, measure: str) -> dict:
    return {str(g): rate([r for r in rows if r[key] == g], measure) for g in sorted({r[key] for r in rows})}


def same_planner(identity: dict) -> dict:
    """What has to be the same in every record and in protocol 2: the packages, Python, expansion and filter. The STOCK name differs between the three stocks by design, so it is left out."""
    normalised = p2.normalised(identity)
    return {"packages": normalised["packages"], "python": normalised["python"], "selection": {k: v for k, v in normalised["selection"].items() if k != "stock"}}


def identity_problems(records_by_run: dict[str, list[dict]], provenance: list[dict]) -> list[str]:
    found = []
    if len({p["commit"] for p in provenance}) > 1:
        found.append("the runs come from more than one commit")
    if any(p["dirty"] for p in provenance):
        found.append("some runs were made with a dirty src/")
    ours = {json.dumps(same_planner(r["identity"]), sort_keys=True) for records in records_by_run.values() for r in records}
    theirs = {json.dumps(same_planner(r["identity"]), sort_keys=True) for r in read_lines(P2 / "results_r1.jsonl")[:1]}
    if len(ours) > 1:
        found.append("the records carry more than one planner identity")
    elif ours and theirs and next(iter(ours)) not in theirs:
        found.append("the planner identity differs from protocol 2's")
    limits = {json.dumps({k: v for k, v in r["limits"].items()}, sort_keys=True) for records in records_by_run.values() for r in records}
    if len(limits) > 1:
        found.append("the search limits differ between records")
    if any(not r["limits"].get("all_routes") for records in records_by_run.values() for r in records):
        found.append("some records were made without --all-routes")
    return found


def judge(refs: list[dict], records_by_run: dict[str, list[dict]], provenance: list[dict]) -> tuple[str, dict, dict]:
    by_ref = {label: {r["id"]: r for r in records} for label, records in records_by_run.items()}
    table = {label: [target_row(ref, by_ref.get(label, {}).get(ref["id"])) for ref in refs] for label in records_by_run}
    problems = identity_problems(records_by_run, provenance)
    primary = [r for r in table.get("primary-r1", []) if not r["failed"]]
    verdict: dict = {"protocol": 3, "references": len(refs), "problems": problems}
    lines = [f"QUALITY BENCHMARK, PROTOCOL 3 (routes of papers after the training data): {len(refs)} references, run labels {sorted(table)}", ""]
    if problems:
        lines += ["NOT EVALUABLE: " + "; ".join(problems), ""]
    if not primary:
        return "\n".join(lines + ["no completed primary-stock run"]), verdict, table
    verdict["primary_failed"] = len(refs) - len(primary)
    verdict["m2_at_10_all"] = rate(primary, "m2_10")
    verdict["m2_at_10_tier_A"] = rate([r for r in primary if r["tier"] == "A"], "m2_10")
    lines += [f"HEADLINE (primary stock, exact rule): the paper's route is among the first 10 shown for {verdict['m2_at_10_all']['k']} of {verdict['m2_at_10_all']['n']} = {verdict['m2_at_10_all']['rate']} (95% {verdict['m2_at_10_all']['interval_95']})",
              f"  tier A alone: {verdict['m2_at_10_tier_A']['k']} of {verdict['m2_at_10_tier_A']['n']} = {verdict['m2_at_10_tier_A']['rate']} (95% {verdict['m2_at_10_tier_A']['interval_95']})", ""]
    read = j3.reading([r["depth"] for r in primary], [r["m2_10"] for r in primary])
    verdict["reading"] = read
    lines += [f"THE READING (routes of depth 2 or more against protocol 2's M2 at 10 by depth, 0.81 / 0.39 / 0.04 at depths 2 / 3 / 4):",
              f"  {read['routes']} routes, {read['recovered']} recovered, {read['expected']} expected ({read['expected_rate']}), observed {read['observed_rate']} (95% {read['interval_95']}); lower-tail probability {read['lower_tail_probability']}",
              f"  READING: {read['reading']}", ""]
    ones = [r for r in primary if r["depth"] == 1]
    verdict["depth_1"] = rate(ones, "m2_10")
    lines.append(f"depth-1 routes (no protocol 2 counterpart): {verdict['depth_1']['k']} of {verdict['depth_1']['n']} = {verdict['depth_1']['rate']}")
    for key in ("depth", "period", "stratum", "tier", "publisher"):
        verdict[f"by_{key}"] = groups(primary, key, "m2_10")
        lines.append(f"M2 at 10 by {key}: " + "; ".join(f"{g} {v['k']}/{v['n']}" for g, v in verdict[f"by_{key}"].items()))
    lines.append("")
    lines.append("BY STOCK (exact M2 at 10 / lenient / M1 at 10 / pool / same-materials route in the first 10 / solved):")
    for label in [x for x in ("primary-r1", "leaves-r1", "zinc-r1") if x in table]:
        rows = [r for r in table[label] if not r["failed"]]
        verdict[label] = {m: rate(rows, m) for m in ("m2_10", "lenient_m2_10", "m1_10", "pool", "same_materials_first10", "solved")}
        lines.append(f"  {label}: " + " / ".join(f"{verdict[label][m]['k']}/{verdict[label][m]['n']}" for m in ("m2_10", "lenient_m2_10", "m1_10", "pool", "same_materials_first10", "solved")) + f"   ({len(table[label]) - len(rows)} failed)")
    noise = {}
    for label in ("primary-r2", "primary-r3"):
        if label in table:
            rows = [r for r in table[label] if not r["failed"]]
            noise[label] = {"m2_10": sum(1 for r in rows if r["m2_10"]), "n": len(rows)}
    if noise:
        base = verdict["m2_at_10_all"]["k"] / verdict["m2_at_10_all"]["n"]
        spread = max(abs(v["m2_10"] / v["n"] - base) for v in noise.values() if v["n"])
        same_solved = all({r["id"]: r.get("solved") for r in table[label]} == {r["id"]: r.get("solved") for r in table["primary-r1"]} for label in noise)
        verdict["noise_floor"] = {"runs": noise, "max_difference_from_r1": round(spread, 3), "range_reported": spread > j3.NOISE_FLOOR, "solved_identical": same_solved}
        lines += ["", f"NOISE FLOOR (primary stock): r1 {verdict['m2_at_10_all']['k']}/{verdict['m2_at_10_all']['n']}, " + ", ".join(f"{k} {v['m2_10']}/{v['n']}" for k, v in noise.items()) + f"; largest difference {verdict['noise_floor']['max_difference_from_r1']}; solved identical: {same_solved}"]
    lines += ["", "CONTAMINATION: papers post-date the planner's training data (to Sep 2016), but similar chemistry may not. The 2017 stratum is closest. Feasibility is not measured and never reported.",
              "Selection: only papers with an explicit route of 4 reactions or fewer qualify; long and hard routes are not measured."]
    return "\n".join(lines), verdict, table


def report_stage(args) -> None:
    refs = load_references()
    provenance = read_lines(OUT / "provenance.jsonl")
    records_by_run = {label: read_lines(OUT / f"results_{label}.jsonl") for _, _, label in RUNS}
    records_by_run = {k: v for k, v in records_by_run.items() if v}
    text, verdict, table = judge(refs, records_by_run, provenance)
    (OUT / "report.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    (OUT / "verdict.json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")
    (OUT / "table.json").write_text(json.dumps(table), encoding="utf-8")
    print(text)


def status_stage(args) -> None:
    for _, _, label in RUNS:
        done = read_lines(OUT / f"results_{label}.jsonl")
        print(f"{label}: {len(done)} targets done")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["prepare", "run", "report", "status"])
    parser.add_argument("--planner-python", default=r"D:\_scratch\aizynth\env\Scripts\python.exe")
    parser.add_argument("--planner-data", default=r"D:\_scratch\aizynth\data")
    args = parser.parse_args()
    {"prepare": prepare, "run": run_stage, "report": report_stage, "status": status_stage}[args.command](args)


if __name__ == "__main__":
    main()
