"""Preregistered smina engine pose-ranking test runner (`PREREGISTRATION_ENGINE.md`).

    uv run --no-sync python benchmarks/docking/run_engine_test.py list
    uv run --no-sync python benchmarks/docking/run_engine_test.py dock
    uv run --no-sync python benchmarks/docking/run_engine_test.py report
    uv run --no-sync python benchmarks/docking/run_engine_test.py gates --out bench-out/engine

`list` prints the deciding population and job count and starts nothing.
`dock` runs the 5×3×N deciding docks (resume-safe). `report` writes RESULT.md
only when the jsonl is complete and evaluable. `gates` is G1–G5; `--pilot` skips G4.
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
from engine_g3_repro import G3_RECEPTOR, run_g3_gate  # noqa: E402
from engine_g4_coverage import run_g4_gate  # noqa: E402
from engine_g5_crystal import run_g5_gate  # noqa: E402
from engine_dock import git_state, load_plan, plan_dict, run_missing  # noqa: E402
from engine_judge import judge, load_jsonl, render_result, summary_dict  # noqa: E402
from engine_pilot import ARM_NAME, pilot_receptors, recorded_rows  # noqa: E402


def measurable_receptors() -> list[str]:
    """The 47 catalogued receptors where the prep-and-box survey has a measurable distance."""
    rows = [r for r in recorded_rows() if r["arm"] == ARM_NAME]
    return sorted({r["pdb"] for r in rows if not r["outcome"].startswith("setup")})


def _write_g5(
    out_dir: pathlib.Path,
    rows: list[dict],
    fractions: dict[str, float],
    g5_gates: list[core.GateResult],
) -> None:
    (out_dir / "g5_results.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )
    summary = {
        "population": len({r.get("pdb") for r in rows}),
        "favorable_fractions": {arm: round(fractions[arm], 6) for arm in core.G5_ARMS},
        "pinned_min_fraction": {arm: round(core.G5_MIN_FRACTION[arm], 6) for arm in core.G5_ARMS},
        "gates": [_gate_dict(g) for g in g5_gates],
        "failed_pdbs": {
            arm: sorted(
                {
                    r["pdb"]
                    for r in rows
                    if r.get("arm") == arm and (r.get("error") or not r.get("favorable"))
                }
            )
            for arm in core.G5_ARMS
        },
    }
    (out_dir / "g5_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


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
    g3_rows: list[dict] = []
    g5_rows: list[dict] = []
    fractions: dict[str, float] = {}
    report_extra: dict = {}
    if g1_gate.passed:
        g2_gate, g2_rows, _diffs = run_g2_gate()
        (out_dir / "g2_results.jsonl").write_text(
            "\n".join(json.dumps(r) for r in g2_rows) + ("\n" if g2_rows else ""),
            encoding="utf-8",
        )
        gates.append(g2_gate)
        if g2_gate.passed:
            g3_gate, g3_rows = run_g3_gate()
            (out_dir / "g3_results.jsonl").write_text(
                "\n".join(json.dumps(r) for r in g3_rows) + ("\n" if g3_rows else ""),
                encoding="utf-8",
            )
            gates.append(g3_gate)
            g4_ok = g3_gate.passed
            if g4_ok and not pilot:
                g4_gate, g4_rows, docked, dropped = run_g4_gate(receptors)
                (out_dir / "g4_results.jsonl").write_text(
                    "\n".join(json.dumps(r) for r in g4_rows) + ("\n" if g4_rows else ""),
                    encoding="utf-8",
                )
                gates.append(g4_gate)
                g4_ok = g4_gate.passed
                report_extra = {
                    "g4_docked": docked,
                    "g4_dropped": sorted(dropped),
                }
            elif pilot:
                report_extra = {"g4_skipped": True}
            if g4_ok:
                g5_gates, g5_rows, fractions = run_g5_gate(receptors)
                _write_g5(out_dir, g5_rows, fractions, g5_gates)
                gates.extend(g5_gates)

    report = {
        "population": len(receptors),
        "pilot_only": pilot,
        "g1_compared": len(g1_rows),
        "g2_receptors": list(g2_receptors()),
        "g2_compared": len(g2_rows),
        "g3_receptor": G3_RECEPTOR,
        "g3_compared": len(g3_rows),
        **report_extra,
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


def cmd_g5(args: argparse.Namespace) -> None:
    """Crystal `--score_only` only — does not rewrite G1–G4 artifacts."""
    receptors = pilot_receptors() if args.pilot else measurable_receptors()
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    g5_gates, g5_rows, fractions = run_g5_gate(receptors)
    _write_g5(out_dir, g5_rows, fractions, g5_gates)
    report = {
        "population": len(receptors),
        "pilot_only": args.pilot,
        "favorable_fractions": {arm: round(fractions[arm], 6) for arm in core.G5_ARMS},
        "gates": [_gate_dict(g) for g in g5_gates],
        "first_failed": _gate_dict(f) if (f := core.first_failed_gate(g5_gates)) else None,
        "overall_verdict": core.overall_verdict(g5_gates, {}),
    }
    print(json.dumps(report, indent=2))
    (out_dir / "g5_gate.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def cmd_list(args: argparse.Namespace) -> None:
    measurable = measurable_receptors()
    deciding, dropped = load_plan(pathlib.Path(args.gates), measurable)
    plan = plan_dict(deciding, dropped, n_measurable=len(measurable))
    print(json.dumps(plan, indent=2))
    print(
        f"{plan['n_deciding']} receptors × {len(plan['arms'])} arms × {len(plan['seeds'])} seeds "
        f"= {plan['n_jobs']} docks",
        flush=True,
    )


def cmd_dock(args: argparse.Namespace) -> None:
    root = pathlib.Path(__file__).resolve().parents[2]
    measurable = measurable_receptors()
    deciding, dropped = load_plan(pathlib.Path(args.gates), measurable)
    plan = plan_dict(deciding, dropped, n_measurable=len(measurable))
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    commit, dirty = git_state(root)
    print(json.dumps({"commit": commit, "dirty": dirty, **{k: plan[k] for k in ("n_jobs", "dropped")}}, indent=2))
    run_missing(out_dir, deciding, commit=commit, dirty=dirty)


def cmd_report(args: argparse.Namespace) -> None:
    gates_dir = pathlib.Path(args.gates)
    out_dir = pathlib.Path(args.out)
    measurable = measurable_receptors()
    deciding, dropped = load_plan(gates_dir, measurable)
    rows = load_jsonl(out_dir / "results.jsonl")
    judged = judge(rows, deciding, gates=[])
    summary = summary_dict(judged)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    text = render_result(judged, dropped=dropped, overlap=sorted(core.TRAINING_OVERLAP))
    complete = not judged["missing"] and not judged["unevaluable"]
    if complete:
        (out_dir / "RESULT.md").write_text(text, encoding="utf-8")
    print(text)
    if not complete:
        raise SystemExit("report refused: incomplete or unevaluable")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    gates = sub.add_parser("gates", help="Run input-sanity gates (G1–G5; --pilot skips G4)")
    gates.add_argument("--out", default="benchmarks/docking/artifacts_engine_gates")
    gates.add_argument(
        "--pilot",
        action="store_true",
        help="Use the 17 pilot receptors instead of the 47 measurable catalog receptors",
    )
    gates.set_defaults(func=cmd_gates)

    g5 = sub.add_parser(
        "g5",
        help="Run G5 crystal --score_only only (does not rewrite G1–G4 artifacts)",
    )
    g5.add_argument("--out", default="benchmarks/docking/artifacts_engine_gates")
    g5.add_argument(
        "--pilot",
        action="store_true",
        help="Score the 17 pilot receptors instead of the 47 measurable catalog receptors",
    )
    g5.set_defaults(func=cmd_g5)

    listing = sub.add_parser("list", help="Print deciding receptors and job count; run nothing")
    listing.add_argument("--gates", default="benchmarks/docking/artifacts_engine_gates")
    listing.set_defaults(func=cmd_list)

    dock = sub.add_parser("dock", help="Run missing deciding docks (resume-safe)")
    dock.add_argument("--gates", default="benchmarks/docking/artifacts_engine_gates")
    dock.add_argument("--out", default="benchmarks/docking/artifacts_engine")
    dock.set_defaults(func=cmd_dock)

    report = sub.add_parser("report", help="Judge complete deciding docks; write RESULT.md")
    report.add_argument("--gates", default="benchmarks/docking/artifacts_engine_gates")
    report.add_argument("--out", default="benchmarks/docking/artifacts_engine")
    report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
