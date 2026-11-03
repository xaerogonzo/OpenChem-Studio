"""The post-freeze addendum to protocol 3 (`RESULT_3_ADDENDUM.md`): a few papers that arrived AFTER protocol 3 was frozen, read with the same rules, searched once on the primary stock, and reported BESIDE the frozen result, never inside it.

    python run_addendum_3.py prepare  [--planner-python PY --planner-data DIR]
    python run_addendum_3.py run      [--planner-python PY --planner-data DIR]
    python run_addendum_3.py report
    python run_addendum_3.py status

Nothing here changes `artifacts_protocol3/` or its reading. The measures, the match rules and the ranking are `run_quality_3.py`'s and `judge_3.py`'s, unchanged (this file only calls them). The stock is the frozen primary stock plus the addendum references' starting materials, minus their intermediates and targets; one search per target, settings protocol 2's. A handful of papers cannot support a test, so the report says what was recovered and why a miss was a miss, and states no reading.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run3 = _load("run_quality_3_for_addendum", "run_quality_3.py")
j3, p1 = run3.j3, run3.p1

REPO = run3.REPO
FROZEN = run3.OUT  # artifacts_protocol3: read here, never written
OUT = HERE / "artifacts_protocol3_addendum"
LABEL = "addendum-primary-r1"


def load_references() -> list[dict]:
    """The addendum's usable references (decision `route`), in file-name order, shaped as `run_quality_3.load_references` shapes the frozen ones."""
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


def stock_keys(refs: list[dict]) -> dict:
    """The frozen primary stock, plus these references' starting materials, minus their intermediates and targets; and the overlaps with the frozen references, which are reported."""
    ik = j3.inchikey
    frozen = {line.strip() for line in (FROZEN / "stocks" / "primary_inchikeys.txt").read_text(encoding="utf-8").splitlines() if line.strip()}
    leaves = {s for r in refs for s in r["leaves"]}
    made = {s for r in refs for s in (r["intermediates"] + [r["target"]])}
    own_conflicts = sorted(leaves & made)
    stock = (frozen | {ik(s) for s in leaves}) - {ik(s) for s in made}
    frozen_made = {ik(s) for r in run3.load_references() for s in (r["intermediates"] + [r["target"]])}
    return {"stock": sorted(stock), "own_conflicts": own_conflicts, "frozen_size": len(frozen), "removed_from_frozen": len(frozen & {ik(s) for s in made}),
            "new_leaf_is_a_frozen_intermediate_or_target": sorted(s for s in leaves if ik(s) in frozen_made)}


def prepare(args) -> None:
    refs = load_references()
    keys = stock_keys(refs)
    OUT.mkdir(exist_ok=True)
    (OUT / "stocks").mkdir(exist_ok=True)
    (OUT / "stocks" / "primary_inchikeys.txt").write_text("\n".join(keys["stock"]) + "\n", encoding="utf-8", newline="\n")
    data = Path(args.planner_data)
    config = {"expansion": {"uspto": [str(data / "uspto_model.onnx"), str(data / "uspto_templates.csv.gz")]}, "stock": {"primary": str(OUT / "stocks" / "primary_inchikeys.txt")}}
    (OUT / "planner_config.json").write_text(json.dumps(config), encoding="utf-8")
    (OUT / "targets.json").write_text(json.dumps([{"id": r["id"], "smiles": r["target"]} for r in refs]), encoding="utf-8")
    summary = [{k: r[k] for k in ("id", "stem", "target", "depth", "steps", "leaves", "intermediates", "stratum", "year", "period", "tier", "publisher")} for r in refs]
    (OUT / "references.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"{len(refs)} references; depths {dict(sorted(Counter(r['depth'] for r in refs).items()))}")
    print(f"stock {len(keys['stock']):,} keys (frozen primary {keys['frozen_size']:,}; removed because an addendum reference makes them: {keys['removed_from_frozen']})")
    print(f"a leaf that is another addendum route's intermediate or target: {keys['own_conflicts'] or 'none'}")
    print(f"an addendum leaf that is a FROZEN reference's intermediate or target (stocked here, as the frozen stock removed it): {keys['new_leaf_is_a_frozen_intermediate_or_target'] or 'none'}")


def run_stage(args) -> None:
    data, python = Path(args.planner_data), args.planner_python
    if not (OUT / "planner_config.json").exists():
        raise SystemExit("run the prepare stage first")
    for name, digest in run3.MODEL_MD5.items():
        if run3.md5(data / name) != digest:
            raise SystemExit(f"{name} is not protocol 2's model file (checksum); refusing to run")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src"], capture_output=True, text=True, cwd=REPO).stdout.strip())
    inputs = {p.name: run3.md5(p) for p in (OUT / "stocks" / "primary_inchikeys.txt", OUT / "targets.json")}
    with (OUT / "provenance.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"protocol": "3-addendum", "commit": commit, "dirty": dirty, "config_md5": run3.md5(OUT / "planner_config.json"), "inputs": inputs}) + "\n")
    command = [python, str(HERE / "plan_batch.py"), "--config", str(OUT / "planner_config.json"), "--stock", "primary", "--targets", str(OUT / "targets.json"), "--out", str(OUT / f"results_{LABEL}.jsonl"),
               "--run-label", LABEL, "--iteration-limit", str(p1.ITERATION_LIMIT), "--time-limit", str(p1.TIME_LIMIT), "--max-transforms", str(p1.MAX_TRANSFORMS), "--filter", "none", "--all-routes"]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=sys.stderr, text=True)
    print(completed.stdout.strip(), flush=True)
    if completed.returncode:
        raise SystemExit(f"the planner batch exited {completed.returncode}")


def judge(refs: list[dict], records: list[dict], provenance: list[dict]) -> tuple[str, dict]:
    by_id = {r["id"]: r for r in records}
    rows = [run3.target_row(ref, by_id.get(ref["id"])) for ref in refs]
    problems = run3.identity_problems({LABEL: records}, provenance)
    # the same planner as the frozen run, compared with the frozen run's own records
    frozen_records = run3.read_lines(FROZEN / "results_primary-r1.jsonl")
    ours = {json.dumps(run3.same_planner(r["identity"]), sort_keys=True) for r in records}
    theirs = {json.dumps(run3.same_planner(r["identity"]), sort_keys=True) for r in frozen_records[:1]}
    if ours and theirs and ours != theirs:
        problems.append("the planner identity differs from the frozen protocol 3 run's")
    lines = [f"PROTOCOL 3 ADDENDUM (papers that arrived after the freeze): {len(refs)} references, one search each on the primary stock", ""]
    if problems:
        lines += ["NOT EVALUABLE: " + "; ".join(problems), ""]
    deep = [r for r in rows if r["depth"] >= 2]
    expected = sum(j3.PROTOCOL2_M2_AT_10_BY_DEPTH[min(max(r["depth"], 2), 4)] for r in deep)
    for row in rows:
        if row["failed"]:
            lines.append(f"{row['stem']}: depth {row['depth']}, {row['steps']} reactions, tier {row['tier']}: the search FAILED")
            continue
        lines.append(f"{row['stem']}: depth {row['depth']}, {row['steps']} reactions, tier {row['tier']}: solved {row['solved']}, {row['route_count']} routes; exact match in the first 10: {row['m2_10']}; "
                     f"in the pool: {row['pool']}; same starting materials by other chemistry in the first 10: {row['same_materials_first10']}")
        for item in row["recall"]:
            lines.append(f"    reaction to {item['product']}: in {item['routes_containing']} returned routes")
    ok = [r for r in rows if not r["failed"]]
    lines += ["", f"recovered in the first 10: {sum(1 for r in ok if r['m2_10'])} of {len(refs)} (frozen protocol 3: 13 of 51). Protocol 2's depth rates would expect {expected:.2f} of the {len(deep)} routes of depth 2 or more.",
              "No reading is made: this few routes cannot support a test, and the frozen reading (LOWER) is not revised by it."]
    return "\n".join(lines), {"protocol": "3-addendum", "references": len(refs), "problems": problems, "rows": rows}


def report_stage(args) -> None:
    text, table = judge(load_references(), run3.read_lines(OUT / f"results_{LABEL}.jsonl"), run3.read_lines(OUT / "provenance.jsonl"))
    (OUT / "report.txt").write_text(text + "\n", encoding="utf-8")
    (OUT / "table.json").write_text(json.dumps(table, indent=1), encoding="utf-8")
    print(text)


def status_stage(args) -> None:
    print(f"{len(load_references())} references; {len(run3.read_lines(OUT / f'results_{LABEL}.jsonl'))} records of {LABEL}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["prepare", "run", "report", "status"])
    parser.add_argument("--planner-python", default=r"D:\_scratch\aizynth\env\Scripts\python.exe")
    parser.add_argument("--planner-data", default=r"D:\_scratch\aizynth\data")
    args = parser.parse_args()
    {"prepare": prepare, "run": run_stage, "report": report_stage, "status": status_stage}[args.command](args)


if __name__ == "__main__":
    main()
