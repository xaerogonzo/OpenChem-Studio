"""Runs the held-out SIZE arm of the proton-affinity benchmark (`PREREGISTRATION_HELDOUT.md`).

The protocol is the original primary arm in `run_pa.py` (M062X/def2-TZVPD Opt Freq). This file only names the six bases, writes under `artifacts_heldout/`, and judges with `heldout.MISSING_ALLOWED`. It does not edit `run_pa.py`.

    python run_pa_heldout.py structures
    python run_pa_heldout.py run [--workers 3] [--cores 4]
    python run_pa_heldout.py report
    python run_pa_heldout.py status

A report is refused (NOT EVALUABLE) for records from more than one commit or made with a dirty `src/`. Do not start `run` until the freeze is committed and `src/` is clean.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import heldout  # noqa: E402
import judge  # noqa: E402
import pa_core  # noqa: E402
import run_pa  # noqa: E402

OUT = HERE / "artifacts_heldout"


def install_panel() -> dict[str, str]:
    """Point `run_pa.BASES` at the held-out six; return the previous mapping so a caller can restore it."""
    previous = dict(run_pa.BASES)
    run_pa.BASES = heldout.smiles()
    return previous


def report_text(records: list[dict], reference: list[dict]) -> tuple[str, dict]:
    problem = run_pa.provenance_problem(records)
    rows = run_pa.judge_records(records, reference)
    result = judge.judge(rows, "primary", missing_allowed=heldout.MISSING_ALLOWED)
    verdicts = {q: result[q]["verdict"] for q in ("pa", "gb")}
    if problem:
        verdicts = {q: judge.NOT_EVALUABLE for q in verdicts}
    done = run_pa.accepted(records)
    n = len(reference)
    low_n = sum(1 for row in reference if row["pa_kj"] <= judge.LOW_BASICITY_KJ)
    deciding_n = n - low_n
    lines = [
        f"HELDOUT SIZE ARM (M062X/def2-TZVPD), {len(done)} accepted structures of {len(records)} jobs"
        + (f"; REFUSED: {problem}" if problem else "")
    ]
    for quantity in ("pa", "gb"):
        r = result[quantity]
        for label, s in (
            (f"deciding ({deciding_n}, above propene)", r["deciding"]),
            (f"low ({low_n}, reported only)", r["low"]),
            (f"all {n}", r["all"]),
        ):
            mae = "-" if s.mae is None else f"{s.mae:.2f}"
            mse = "-" if s.mse is None else f"{s.mse:+.2f}"
            mx = "-" if s.max_abs is None else f"{s.max_abs:.2f}"
            lines.append(f"{quantity.upper()} {label:36s} n={s.count:2d} missing={s.missing:2d} MAE={mae} MSE={mse} max={mx} kcal/mol")
        lines.append(f"{quantity.upper()} VERDICT {verdicts[quantity]}")
    lines += ["", f"{'base':20s} {'PA calc':>9s} {'PA ref':>8s} {'GB calc':>9s} {'GB ref':>8s}   site (kJ/mol)"]
    previous = install_panel()
    try:
        for row, ref in zip(rows, reference):
            pa = run_pa.select(done, ref["name"], "pa")
            site = "-"
            if pa:
                base = run_pa.base_molecule(ref["name"])
                site = f"{base.GetAtomWithIdx(pa['site_atom']).GetSymbol()}{pa['site_atom']}"
            fmt = lambda kcal: "missing" if kcal is None else f"{kcal * 4.184:.1f}"  # noqa: E731
            lines.append(f"{ref['name']:20s} {fmt(row['pa_kcal']):>9s} {ref['pa_kj']:8.1f} {fmt(row['gb_kcal']):>9s} {ref['gb_kj']:8.1f}   {site}")
    finally:
        run_pa.BASES = previous
    differing = [r for r in done if r["sigma_orca"] != r["sigma_true"]]
    lines += ["", f"symmetry number: ORCA's differs from the one used in {len(differing)} of {len(done)} accepted structures"]
    return "\n".join(lines), {"verdicts": verdicts, "problem": problem, "missing_allowed": heldout.MISSING_ALLOWED}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["structures", "run", "report", "status"])
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    previous = install_panel()
    try:
        if args.command == "structures":
            structures = run_pa.build_structures()
            (out / "structures.json").write_text(json.dumps(structures), encoding="utf-8")
            n_base = sum(1 for s in structures if s["role"] == "base")
            n_ion = sum(1 for s in structures if s["role"] == "ion")
            print(f"{len(structures)} structures ({n_base} base, {n_ion} ion) for {len(run_pa.BASES)} held-out bases")
        elif args.command == "run":
            run_pa.run_stage(out, args.cores, args.workers)
        elif args.command == "status":
            structures = json.loads((out / "structures.json").read_text(encoding="utf-8"))
            records = run_pa.records_of(out / "primary" / "runs.jsonl")
            print(
                f"{len(structures)} structures, {len({r['structure'] for r in records if r.get('completed')})} completed, "
                f"{len(run_pa.accepted(records))} accepted"
            )
        else:
            reference = heldout.bases()
            records = run_pa.records_of(out / "primary" / "runs.jsonl")
            text, verdict = report_text(records, reference)
            print(text)
            (out / "report.txt").write_text(text, encoding="utf-8")
            (out / "verdict.json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")
    finally:
        run_pa.BASES = previous


if __name__ == "__main__":
    main()
