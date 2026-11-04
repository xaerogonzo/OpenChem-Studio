"""Preregistered smina engine pose-ranking test runner (`PREREGISTRATION_ENGINE.md`).

    uv run --no-sync python benchmarks/docking/run_engine_test.py gates --out bench-out/engine
    uv run --no-sync python benchmarks/docking/run_engine_test.py gates --pilot

`gates` runs the input-sanity gates in order (G1, G2, then G5 today; G3–G4 added as the test is built).
A failed gate stops before later gates and before gained/lost; verdict is INCONCLUSIVE via
`engine_core.overall_verdict`.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import engine_core as core  # noqa: E402
from engine_g1_survey import run_g1_gate  # noqa: E402
from engine_g2_score_only import g2_receptors, run_g2_gate  # noqa: E402
from engine_g5_crystal import measure_g5_crystal_scores  # noqa: E402
from engine_pilot import ARM_NAME, pilot_receptors, recorded_rows  # noqa: E402


def measurable_receptors() -> list[str]:
    """The 47 catalogued receptors where the prep-and-box survey has a measurable distance."""
    rows = [r for r in recorded_rows() if r["arm"] == ARM_NAME]
    return sorted({r["pdb"] for r in rows if not r["outcome"].startswith("setup")})


def _gate_dict(g: core.GateResult) -> dict:
    return {"name": g.name, "passed": g.passed, "detail": g.detail}


def run_gates(
    out_dir: pathlib.Path,
    *,
    pilot: bool = False,
) -> dict:
    receptors = pilot_receptors() if pilot else measurable_receptors()
    out_dir.mkdir(parents=True, exist_ok=True)

    g1_gate, g1_rows, g1_recorded, g1_measured = run_g1_gate(receptors)
    g1_out = []
    for row in g1_rows:
        pdb = row["pdb"]
        rec = g1_recorded.get(pdb)
        meas = g1_measured.get(pdb)
        g1_out.append(
            {
                **row,
                "recorded_top_rmsd": rec,
                "measured_top_rmsd": meas,
                "delta_rmsd": None if rec is None or meas is None else round(meas - rec, 6),
            }
        )
    (out_dir / "g1_results.jsonl").write_text(
        "\n".join(json.dumps(r) for r in g1_out) + ("\n" if g1_out else ""),
        encoding="utf-8",
    )

    gates: list[core.GateResult] = [g1_gate]
    g2_rows: list[dict] = []
    g5_rows: list[dict] = []
    fractions: dict[str, float] = {}
    if g1_gate.passed:
        g2_gate, g2_rows, _diffs = run_g2_gate()
        (out_dir / "g2_results.jsonl").write_text(
            "\n".join(json.dumps(r) for r in g2_rows) + ("\n" if g2_rows else ""),
            encoding="utf-8",
        )
        gates.append(g2_gate)
        if g2_gate.passed:
            g5_rows, fractions = measure_g5_crystal_scores(receptors)
            (out_dir / "g5_results.jsonl").write_text(
                "\n".join(json.dumps(r) for r in g5_rows) + ("\n" if g5_rows else ""),
                encoding="utf-8",
            )
            gates.extend(core.gate_g5_all_arms(fractions))

    report = {
        "population": len(receptors),
        "pilot_only": pilot,
        "g1_compared": len(g1_rows),
        "g2_receptors": list(g2_receptors()),
        "g2_compared": len(g2_rows),
        "favorable_fractions": {arm: round(fractions[arm], 6) for arm in core.G5_ARMS} if fractions else {},
        "gates": [_gate_dict(g) for g in gates],
        "first_failed": _gate_dict(f) if (f := core.first_failed_gate(gates)) else None,
        "overall_verdict": core.overall_verdict(gates, {}),
    }
    (out_dir / "gates.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def cmd_gates(args: argparse.Namespace) -> None:
    report = run_gates(pathlib.Path(args.out), pilot=args.pilot)
    print(json.dumps(report, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    gates = sub.add_parser("gates", help="Run input-sanity gates (G1, G2, then G5)")
    gates.add_argument("--out", default="benchmarks/docking/artifacts_engine_gates")
    gates.add_argument(
        "--pilot",
        action="store_true",
        help="Use the 17 pilot receptors instead of the 47 measurable catalog receptors",
    )
    gates.set_defaults(func=cmd_gates)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
