"""The official-metric check of protocol 2 (`PREREGISTRATION_2.md`): M1, M2 and M3 recomputed with PaRoutes' own tree edit distance instead of the exact rule. A SECONDARY figure that decides nothing.

    D:/_scratch/route_distances_env/Scripts/python.exe -I official_check.py --paroutes DIR [--out DIR]

Run it with the SEPARATE environment's Python (route-distances 1.2.4 installed without its dependencies, plus numpy, scipy, apted, rdkit and pydantic), never the planner's: installing the package normally would pull in torch and change the planner's recorded identity. A reference route is found when `ReactionTreeWrapper(reference).distance_to(ReactionTreeWrapper(route))` is below 1e-6, exactly as `analysis/route_quality.py` of PaRoutes decides; a route the library cannot read counts as 1e6 away (never a match), as there. The ranks, the three orders and the scores are `route_rank.py`'s, unchanged; only what counts as a match differs.
"""
from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OFFICIAL_TOLERANCE = 1e-6
UNREADABLE = 1e6


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rank = _load("synthesis_official_rank", "route_rank.py")


def official_distance(reference: dict, route: dict) -> float:
    """PaRoutes' tree edit distance between two routes, or `UNREADABLE` if the library cannot read one of them."""
    from route_distances.ted.reactiontree import ReactionTreeWrapper

    try:
        return float(ReactionTreeWrapper(reference).distance_to(ReactionTreeWrapper(route)))
    except ValueError:
        return UNREADABLE


def needed_indices(base: "rank.Analysis", top: int = 10) -> list[int]:
    """The routes whose distance matters for k up to `top`: everything within the PaRoutes top-`top`, the first `top` of M2's order and the first `top` of the planner's order."""
    wanted = {i for i, r in zip(base.cost_order, base.cost_ranks) if r <= top}
    wanted |= set(base.user_order[:top])
    wanted |= set(range(min(top, base.count)))
    return sorted(wanted)


def official_analysis(routes: list[dict], reference: dict, distance=official_distance) -> tuple["rank.Analysis", "rank.Analysis", dict]:
    """The exact-rule analysis, the same analysis with the official distance deciding the matches, and how many computed routes the two rules disagree on. Routes outside `needed_indices` are never matched (they cannot enter any count asked for)."""
    exact = rank.analyse(routes, reference)
    hits = [False] * len(routes)
    disagreements = {"computed": 0, "official_only": 0, "exact_only": 0}
    for i in needed_indices(exact):
        hits[i] = distance(reference, routes[i]) < OFFICIAL_TOLERANCE
        disagreements["computed"] += 1
        disagreements["official_only"] += int(hits[i] and not exact.hits[i])
        disagreements["exact_only"] += int(exact.hits[i] and not hits[i])
    return exact, dataclasses.replace(exact, hits=tuple(hits)), disagreements


def summarise(per_target: list[tuple["rank.Analysis", "rank.Analysis"]]) -> dict:
    n = len(per_target) or 1
    out = {}
    for label, pick in (("exact", 0), ("official", 1)):
        out[label] = {name: [sum(1 for pair in per_target if getattr(pair[pick], name)(k)) / n for k in (1, 5, 10)] for name in ("m1", "m2", "m3")}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--paroutes", required=True)
    parser.add_argument("--out", default=str(HERE / "artifacts_protocol2"))
    args = parser.parse_args()
    out = Path(args.out)
    reference = json.loads((Path(args.paroutes) / "ref_routes_n1.json").read_text(encoding="utf-8"))
    draw = json.loads((out / "draw.json").read_text(encoding="utf-8"))
    records = {}
    with (out / "results_r1.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                record = json.loads(line)
                records[record["id"]] = record
    pairs, totals = [], {"computed": 0, "official_only": 0, "exact_only": 0}
    for done, index in enumerate(draw["main"], 1):
        record = records.get(index)
        if record is None or record["status"] != "completed":
            pairs.append((rank.analyse([], reference[index]),) * 2)
            continue
        exact, official, differences = official_analysis(record["routes"], reference[index])
        pairs.append((exact, official))
        for key in totals:
            totals[key] += differences[key]
        if done % 25 == 0:
            print(f"{done} of {len(draw['main'])} targets", flush=True)
    summary = summarise(pairs)
    summary["disagreements"] = totals
    lines = ["OFFICIAL-METRIC CHECK (secondary; decides nothing): recovered at 1 / 5 / 10, exact rule against PaRoutes' tree edit distance below 1e-6", ""]
    for name, title in (("m1", "M1 the PaRoutes count"), ("m2", "M2 first routes in rank order"), ("m3", "M3 the planner's order")):
        lines.append(f"{title:34s} exact {' / '.join(f'{v:.3f}' for v in summary['exact'][name])}   official {' / '.join(f'{v:.3f}' for v in summary['official'][name])}")
    lines.append(f"routes compared: {totals['computed']}; matched by the official distance only: {totals['official_only']}; by the exact rule only: {totals['exact_only']}")
    text = "\n".join(lines)
    print(text)
    (out / "official.txt").write_text(text, encoding="utf-8")
    (out / "official.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
