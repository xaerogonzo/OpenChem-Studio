"""Measure G5 crystal `--score_only` sanity on the engine-pilot receptors (open item 2).

    uv run --no-sync python benchmarks/docking/engine_g5_probe.py
    uv run --no-sync python benchmarks/docking/engine_g5_probe.py --out bench-out/engine_g5

Uses the survey's app preparation, the deposited ligand copy the box chose, and all five
preregistered arms. Writes `results.jsonl` and a summary with suggested `min_fraction` per arm.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from engine_core import G5_ARMS, G5_MIN_FRACTION  # noqa: E402
from engine_g5_crystal import measure_g5_crystal_scores, suggest_min_fraction  # noqa: E402
from engine_pilot import ARMS, pilot_receptors  # noqa: E402


def run_probe(out_dir: pathlib.Path) -> dict:
    receptors = pilot_receptors()
    rows, fractions = measure_g5_crystal_scores(receptors, arms=ARMS)

    results_path = out_dir / "results.jsonl"
    results_path.write_text(
        "\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )

    summary: dict = {"receptors": receptors, "arms": {}}
    for arm in G5_ARMS:
        mine = [r for r in rows if r["arm"] == arm]
        scored = [r for r in mine if r.get("score") is not None]
        fav = [r for r in scored if r.get("favorable")]
        errors = [r for r in mine if r.get("error")]
        total = len(receptors)
        summary["arms"][arm] = {
            "scored": len(scored),
            "errors": len(errors),
            "favorable": len(fav),
            "total_pilot": total,
            "favorable_fraction": round(fractions[arm], 4),
            "suggested_min_fraction": round(suggest_min_fraction(len(fav), total), 4),
            "pinned_min_fraction": round(G5_MIN_FRACTION[arm], 4),
            "failed_pdbs": sorted({r["pdb"] for r in mine if r.get("error") or not r.get("favorable")}),
        }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="benchmarks/docking/artifacts_engine_g5")
    args = parser.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = run_probe(out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
