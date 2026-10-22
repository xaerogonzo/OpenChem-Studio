"""The functional ladder of `PLAN_FUNCTIONAL_LADDER.md`: is the steady DFT offset between Psi4 and ORCA (versions 3 of the agreement check and the grid test, both PARTIAL) something every density functional carries, or something one functional's own coding does?

    python run_functional_ladder.py run    --engine orca|psi4 [--workers 3] [--cores 4]
    python run_functional_ladder.py report

It reuses the agreement runner's inputs, job runner and record format (`run_agreement.py`). One run per cell and engine, each program at its own default grid, as shipped. The functionals are HF (a negative control: it has no
density functional), PBE, BLYP, B3LYP and PBE0. B3LYP, PBE0 and HF are the application's own inputs, byte for byte the ones version 3 ran; PBE and BLYP are the shipped B3LYP input with only the functional's name swapped
(`run_agreement.FUNCTIONAL_VARIANT`). The rule is the code of `judge_ladder` below, tested by `tests/test_psi4_functional_ladder.py`; where the plan and this code disagree, that is a defect fixed before any run.
Records go to `artifacts_ladder/ladder/<engine>.jsonl`; a report is refused for records from more than one commit or made with a dirty `src/`.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_agreement as ra  # noqa: E402

STAGE = "ladder"
#: The six molecules of the agreement check's floor set, fixed in version 1 before any offset was seen (so the choice does not depend on the thing measured).
MOLECULES = ra.FLOOR_MOLECULES
BASIS = "def2-SVP"
#: label -> (the functional the provider is asked for, the variant that swaps it). PBE and BLYP are not in the application's table: they are the B3LYP input with the name swapped.
FUNCTIONALS: dict[str, tuple[str, str]] = {
    "HF": ("HF", "default"),
    "PBE": ("B3LYP", f"{ra.FUNCTIONAL_VARIANT}PBE"),
    "BLYP": ("B3LYP", f"{ra.FUNCTIONAL_VARIANT}BLYP"),
    "B3LYP": ("B3LYP", "default"),
    "PBE0": ("PBE0", "default"),
}
DFT = ("PBE", "BLYP", "B3LYP", "PBE0")

#: A functional carries an offset when the median Psi4 - ORCA difference over the molecules is at least this (mEh): version 3's own threshold for an offset that reproduces.
PRESENT_MEH = 0.1
#: ...and is free of one below this (mEh): half of that, so that a median in between is neither.
ABSENT_MEH = 0.05
#: The four medians are "the same size" when the largest is at most this many times the smallest.
COMMON_RATIO = 2.0
#: Hartree-Fock has no density functional: it must agree to the floor version 3 measured for it (0.00001 mEh), with room, or the pipeline is not measuring what it names.
HF_CONTROL_MEH = 0.01
#: At most this many molecules may lack a run per functional.
MIN_MOLECULES = 5


def jobs(engine: str) -> list[ra.Job]:
    return [ra.Job(STAGE, engine, m, FUNCTIONALS[f][0], BASIS, FUNCTIONALS[f][1], "sp") for m in MOLECULES for f in FUNCTIONALS]


def _label(functional: str, variant: str) -> str:
    return next(label for label, (fn, var) in FUNCTIONALS.items() if (fn, var) == (functional, variant))


def _energies(records: list[dict]) -> dict[tuple[str, str], float]:
    return {(r["molecule"], _label(r["functional"], r["variant"])): r["energy_hartree"] for r in records if r.get("completed")}


def electrons(name: str) -> int:
    """The electron count of a molecule: the sum of the atomic numbers less the charge."""
    mol = ra.molecule(name)
    return sum(atom.GetAtomicNum() for atom in mol.GetAtoms()) - ra.MOLECULES[name][1]


def rows_from(orca: list[dict], psi4: list[dict]) -> list[dict]:
    """One row per (molecule, functional) that both engines completed: d = Psi4 - ORCA in mEh."""
    o, p = _energies(orca), _energies(psi4)
    return [
        {"molecule": m, "functional": f, "d": (p[(m, f)] - o[(m, f)]) * 1000.0}
        for m in MOLECULES for f in FUNCTIONALS if (m, f) in o and (m, f) in p
    ]


def medians(rows: list[dict]) -> dict[str, float]:
    return {f: statistics.median(r["d"] for r in rows if r["functional"] == f) for f in FUNCTIONALS if any(r["functional"] == f for r in rows)}


def judge_ladder(rows: list[dict]) -> tuple[str, list[str]]:
    """The reading rule of the plan, first line that holds decides.
    1. NOT EVALUABLE: a Hartree-Fock control, or fewer than MIN_MOLECULES molecules of any of the four functionals, lack a run on either engine.
    2. NOT VALID: Hartree-Fock moved by more than HF_CONTROL_MEH (some molecule), or B3LYP's median is below PRESENT_MEH (version 3's offset did not reproduce at these cells).
    3. COMMON TO DFT: all four medians are at least PRESENT_MEH and the largest is at most COMMON_RATIO times the smallest.
    4. FUNCTIONAL-SPECIFIC: at least one functional's median is below ABSENT_MEH (and, by rule 2, B3LYP's is not): the offset is in how a functional is coded, and the report names which carry it and which do not.
    5. otherwise MIXED.
    """
    counts = {f: sum(1 for r in rows if r["functional"] == f) for f in FUNCTIONALS}
    if counts["HF"] < len(MOLECULES) or any(counts[f] < MIN_MOLECULES for f in DFT):
        return "NOT EVALUABLE", [f"molecules completed on both engines: {counts}"]
    med = medians(rows)
    hf_worst = max(abs(r["d"]) for r in rows if r["functional"] == "HF")
    facts = [f"median Psi4 - ORCA (mEh): " + ", ".join(f"{f} {med[f]:+.3f}" for f in FUNCTIONALS) + f"; largest Hartree-Fock |d| {hf_worst:.5f}"]
    if hf_worst > HF_CONTROL_MEH:
        return "NOT VALID", facts + [f"Hartree-Fock moved by {hf_worst:.4f} mEh (limit {HF_CONTROL_MEH})"]
    if med["B3LYP"] < PRESENT_MEH:
        return "NOT VALID", facts + [f"B3LYP's median {med['B3LYP']:+.3f} mEh is below {PRESENT_MEH}: the offset did not reproduce at these cells"]
    values = [med[f] for f in DFT]
    if min(values) >= PRESENT_MEH and max(values) <= COMMON_RATIO * min(values):
        return "COMMON TO DFT", facts
    absent = [f for f in DFT if med[f] < ABSENT_MEH]
    if absent:
        present = [f for f in DFT if med[f] >= PRESENT_MEH]
        return "FUNCTIONAL-SPECIFIC", facts + [f"carry the offset: {', '.join(present)}; free of it: {', '.join(absent)}"]
    return "MIXED", facts


def report_lines(rows: list[dict]) -> list[str]:
    """Reported, in no rule: the size of the offset per electron, and every cell."""
    lines = []
    for f in DFT:
        cells = [(electrons(r["molecule"]), r["d"]) for r in rows if r["functional"] == f]
        per_electron = statistics.median(d / n for n, d in cells) if cells else float("nan")
        lines.append(f"{f:6s} median d per electron {per_electron * 1000:+.2f} ueh/e-")
    lines.append("")
    lines.append(f"{'molecule':22s}{'electrons':>10s}" + "".join(f"{f:>9s}" for f in FUNCTIONALS) + "   (mEh, Psi4 - ORCA)")
    for m in MOLECULES:
        have = {r["functional"]: r["d"] for r in rows if r["molecule"] == m}
        lines.append(f"  {m:20s}{electrons(m):>10d}" + "".join(f"{have[f]:>+9.3f}" if f in have else f"{'-':>9s}" for f in FUNCTIONALS))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "report"])
    parser.add_argument("--engine", choices=["orca", "psi4"])
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--out", default=str(HERE / "artifacts_ladder"))
    args = parser.parse_args()
    ctx = ra.Context(Path(args.out), args.cores, args.workers)
    if args.command == "run":
        if not args.engine:
            parser.error("run needs --engine")
        ra.run_all(ctx, jobs(args.engine))
        return
    orca, psi4 = ctx.records(STAGE, "orca"), ctx.records(STAGE, "psi4")
    problem = ra.provenance_problem(orca, psi4)
    rows = rows_from(orca, psi4)
    verdict, why = ("NOT EVALUABLE", [problem]) if problem else judge_ladder(rows)
    text = "\n".join([*why, "", *report_lines(rows), "", f"VERDICT {verdict}"])
    (ctx.out / "report.txt").write_text(text, encoding="utf-8")
    (ctx.out / "verdict.json").write_text(json.dumps({"verdict": verdict, "why": why}, indent=1), encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
