"""Protocol 2 re-scored with only the routes whose every starting material is in stock. A DIAGNOSTIC of saved records: it decides nothing and the verdict of `run_quality_2.py report` stands.

    python stocked_rescore.py --paroutes DIR [--artifacts DIR]

Why it exists. Protocol 2 asked the planner for every route (`post_processing.all_routes`) and ranked them all; the product (`chem/aizynth_planner.py`) keeps only routes whose starting materials are all flagged in stock, so that "a route was returned" means what the benchmark's "solved" meant. This asks whether that filter changes the user-facing figure (M2), using the benchmark's own ranker and matcher (`route_rank.py`, `route_match.py`), not the product's. It also counts how much of the benchmark's pool was routes with a starting material that is not in stock, which the preregistration did not expect ("every solved route").

Needs the raw main-run records `results_r1.jsonl` (gunzip `results_r1.jsonl.gz` if only that is kept).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import route_match  # noqa: E402,F401  (route_rank loads it itself; imported so a missing RDKit fails here)
import route_rank  # noqa: E402


def fully_stocked(node: dict) -> bool:
    """Every starting material of the route tree is flagged in stock."""
    reactions = [child for child in node.get("children") or [] if isinstance(child, dict) and child.get("type") == "reaction"]
    if not reactions:
        return node.get("in_stock") is True
    return all(fully_stocked(child) for child in reactions[0].get("children") or [] if isinstance(child, dict))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paroutes", required=True)
    parser.add_argument("--artifacts", default=str(HERE / "artifacts_protocol2"))
    args = parser.parse_args()
    artifacts = Path(args.artifacts)
    reference = json.load(open(Path(args.paroutes) / "ref_routes_n1.json", encoding="utf-8"))
    rows = [json.loads(line) for line in open(artifacts / "results_r1.jsonl", encoding="utf-8") if line.strip()]

    totals = {"all": {"m1": 0, "m2": 0, "pool": 0}, "stocked": {"m1": 0, "m2": 0, "pool": 0}}
    mixed = slots = taken = 0
    shares = []
    for row in rows:
        routes = row["routes"]
        ref = reference[row["id"]]
        stocked = [r for r in routes if fully_stocked(r)]
        for name, pool in (("all", routes), ("stocked", stocked)):
            analysis = route_rank.analyse(pool, ref)
            totals[name]["m1"] += analysis.m1(10)
            totals[name]["m2"] += analysis.m2(10)
            totals[name]["pool"] += analysis.pool()
        if routes:
            shares.append((len(routes) - len(stocked)) / len(routes))
            if len(stocked) < len(routes) and row["statistics"]["is_solved"]:
                mixed += 1
            first_ten = route_rank.analyse(routes, ref).user_order[:10]
            slots += len(first_ten)
            taken += sum(1 for i in first_ten if not fully_stocked(routes[i]))
    n = len(rows)
    lines = [
        "PROTOCOL 2 RE-SCORED WITH ONLY THE ROUTES WHOSE EVERY STARTING MATERIAL IS IN STOCK (a diagnostic; decides nothing)",
        f"targets {n}",
        f"as measured (every route the planner returned)   M1 {totals['all']['m1'] / n:.4f}   M2 {totals['all']['m2'] / n:.4f} ({totals['all']['m2']} of {n})   pool {totals['all']['pool'] / n:.4f}",
        f"only routes with every starting material in stock M1 {totals['stocked']['m1'] / n:.4f}   M2 {totals['stocked']['m2'] / n:.4f} ({totals['stocked']['m2']} of {n})   pool {totals['stocked']['pool'] / n:.4f}",
        f"solved targets whose returned routes include some with a starting material not in stock: {mixed}",
        f"share of such routes in a target's returned routes (median / mean): {statistics.median(shares):.3f} / {statistics.mean(shares):.3f}",
        f"places in M2's first 10 taken by such a route: {taken} of {slots}",
    ]
    text = "\n".join(lines)
    print(text)
    (artifacts / "stocked_rescore.txt").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
