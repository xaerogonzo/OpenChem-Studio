"""The grid-offset experiment of `PLAN_GRID_OFFSET.md`: does the steady DFT offset between Psi4 and ORCA (version 3 of the agreement check, PARTIAL) move when each program's integration grid is made finer?

    python run_grid_offset.py run    --engine orca|psi4 [--workers 3] [--cores 4]
    python run_grid_offset.py report

It reuses the agreement runner's inputs, its job runner and its record format (`run_agreement.py`), so every input is the one the application writes. Four runs per cell: each engine at its own default grid and at its finer one (Psi4 `dft_radial_points 99`, `dft_spherical_points 590`, `e_convergence 1e-10`, the runner's `grid` variant; ORCA `TightSCF DefGrid3`, its `tight` variant). The rule is the code of `judge_cells` below, tested by `tests/test_psi4_grid_offset.py`; where the plan and this code disagree, that is a defect fixed before any run.
Records go to `artifacts_grid/<stage>/<engine>.jsonl`; a report is refused for records from more than one commit or made with a dirty `src/`.
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

STAGE = "gridoff"
#: The molecules, fixed by the rule in the plan: the five with the largest mean M062X difference (Psi4 - ORCA) over the three bases in version 3's records, then water (the smallest) as the small-molecule control.
MOLECULES = ["dimethyl ether", "fluorobenzene", "benzene", "dimethyl sulfoxide", "propanal", "water"]
DFT_COMBINATIONS = [("M062X", "def2-SVP"), ("M062X", "def2-TZVP"), ("B3LYP", "def2-SVP"), ("B3LYP", "def2-TZVP")]
#: A functional with no grid: the pipeline's negative control. A finer DFT grid must not move a Hartree-Fock energy.
HF_CONTROLS = [("water", "HF", "def2-SVP"), ("benzene", "HF", "def2-SVP")]
LEVELS = {"orca": ("default", "tight"), "psi4": ("default", "grid")}  # (default grid, finer grid)

#: Fixed by the plan from version 3's artifacts (its DFT floor 0.0629 mEh and tolerance 0.126 mEh) and not tuned here.
T_DFT_MEH = 0.126
#: A cell carries two engines' errors, so a single cell is allowed twice the tolerance.
T_CELL_MEH = 2 * T_DFT_MEH
#: Hartree-Fock has no grid: any move above this (version 3's HF floor was 0.00001 mEh) means the finer variants changed something other than the grid.
HF_CONTROL_MEH = 0.01
#: The offset must reproduce for the question to be asked at all.
MIN_OFFSET_MEH = 0.1
EXPLAINED_SHARE = 0.8
HALVED = 0.5
UNCHANGED = 0.75
MIN_DFT_CELLS = 22  # of 24: at most 2 cells (about 8%) may lack one of their four runs


def jobs(engine: str) -> list[ra.Job]:
    low, fine = LEVELS[engine]
    cells = [(m, f, b) for m in MOLECULES for f, b in DFT_COMBINATIONS] + HF_CONTROLS
    return [ra.Job(STAGE, engine, m, f, b, v, "sp") for m, f, b in cells for v in (low, fine)]


def _energies(records: list[dict]) -> dict[tuple, float]:
    return {(r["molecule"], r["functional"], r["basis"], r["variant"]): r["energy_hartree"] for r in records if r.get("completed")}


def cells_from(orca: list[dict], psi4: list[dict]) -> list[dict]:
    """One row per cell that has all four runs: the energies in Hartree and the five differences in mEh (d_default = Psi4 - ORCA at each program's default grid; d_fine at both finer grids; the cross terms; and each program's own grid shift)."""
    o, p = _energies(orca), _energies(psi4)
    rows = []
    for m, f, b in [(m, f, b) for m in MOLECULES for f, b in DFT_COMBINATIONS] + HF_CONTROLS:
        keys = (o.get((m, f, b, "default")), o.get((m, f, b, "tight")), p.get((m, f, b, "default")), p.get((m, f, b, "grid")))
        if None in keys:
            continue
        o0, o1, p0, p1 = (k * 1000.0 for k in keys)
        rows.append({"molecule": m, "functional": f, "basis": b, "d_default": p0 - o0, "d_psi4_fine": p1 - o0, "d_orca_fine": p0 - o1, "d_fine": p1 - o1, "shift_psi4": p1 - p0, "shift_orca": o1 - o0})
    return rows


def judge_cells(rows: list[dict]) -> tuple[str, list[str]]:
    """The reading rule of the plan, first line that holds decides.
    1. NOT EVALUABLE: fewer than MIN_DFT_CELLS of the 24 DFT cells, or a Hartree-Fock control, lack one of their four runs.
    2. NOT VALID: a Hartree-Fock control moved by more than HF_CONTROL_MEH in either program (the finer variants changed more than the grid), or the median default-grid offset of the DFT cells is below MIN_OFFSET_MEH (version 3's offset did not reproduce).
    3. GRID EXPLAINS: the median fine-grid offset is within T_DFT of zero, at least EXPLAINED_SHARE of the cells are within T_CELL of zero, and the median fine-grid offset is at most HALVED of the median default-grid offset.
    4. NOT THE GRID: the median fine-grid offset is still at least UNCHANGED of the median default-grid offset.
    5. otherwise PARTIAL.
    """
    dft = [r for r in rows if r["functional"] != "HF"]
    hf = [r for r in rows if r["functional"] == "HF"]
    if len(dft) < MIN_DFT_CELLS or len(hf) < len(HF_CONTROLS):
        return "NOT EVALUABLE", [f"{len(dft)} of 24 DFT cells and {len(hf)} of {len(HF_CONTROLS)} Hartree-Fock controls have all four runs"]
    biggest_hf = max(max(abs(r["shift_psi4"]), abs(r["shift_orca"])) for r in hf)
    m_default = statistics.median(r["d_default"] for r in dft)
    m_fine = statistics.median(r["d_fine"] for r in dft)
    share = sum(1 for r in dft if abs(r["d_fine"]) <= T_CELL_MEH) / len(dft)
    facts = [f"median offset at the default grids {m_default:+.3f} mEh, at the finer grids {m_fine:+.3f} mEh; {share:.0%} of {len(dft)} cells within {T_CELL_MEH:.3f} mEh at the finer grids; largest Hartree-Fock control move {biggest_hf:.5f} mEh"]
    if biggest_hf > HF_CONTROL_MEH:
        return "NOT VALID", facts + [f"a Hartree-Fock control moved by {biggest_hf:.4f} mEh (limit {HF_CONTROL_MEH})"]
    if m_default < MIN_OFFSET_MEH:
        return "NOT VALID", facts + [f"the median default-grid offset {m_default:+.3f} mEh is below {MIN_OFFSET_MEH}: the offset did not reproduce"]
    if abs(m_fine) <= T_DFT_MEH and share >= EXPLAINED_SHARE and abs(m_fine) <= HALVED * abs(m_default):
        return "GRID EXPLAINS", facts
    if abs(m_fine) >= UNCHANGED * abs(m_default):
        return "NOT THE GRID", facts
    return "PARTIAL", facts


def report_lines(rows: list[dict]) -> list[str]:
    """Reported, in no rule: where the shift comes from (each program's own grid shift) and how it goes with the molecule and the functional."""
    dft = [r for r in rows if r["functional"] != "HF"]
    lines = []
    if dft:
        lines.append(f"median grid shift: Psi4 {statistics.median(r['shift_psi4'] for r in dft):+.3f} mEh, ORCA {statistics.median(r['shift_orca'] for r in dft):+.3f} mEh (energy at the finer grid minus the default; the offset moves by Psi4's minus ORCA's)")
        lines.append(f"median Psi4-fine/ORCA-default {statistics.median(r['d_psi4_fine'] for r in dft):+.3f}, Psi4-default/ORCA-fine {statistics.median(r['d_orca_fine'] for r in dft):+.3f} mEh")
    lines.append("")
    lines.append("cell                                   default  Psi4 fine  ORCA fine     both   (mEh, Psi4 - ORCA)")
    for r in rows:
        lines.append(f"  {r['molecule']:20s} {r['functional']:6s} {r['basis']:9s} {r['d_default']:+8.3f} {r['d_psi4_fine']:+10.3f} {r['d_orca_fine']:+10.3f} {r['d_fine']:+8.3f}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "report"])
    parser.add_argument("--engine", choices=["orca", "psi4"])
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--out", default=str(HERE / "artifacts_grid"))
    args = parser.parse_args()
    ctx = ra.Context(Path(args.out), args.cores, args.workers)
    if args.command == "run":
        if not args.engine:
            parser.error("run needs --engine")
        ra.run_all(ctx, jobs(args.engine))
        return
    orca, psi4 = ctx.records(STAGE, "orca"), ctx.records(STAGE, "psi4")
    problem = ra.provenance_problem(orca, psi4)
    rows = cells_from(orca, psi4)
    verdict, why = ("NOT EVALUABLE", [problem]) if problem else judge_cells(rows)
    text = "\n".join([*why, "", *report_lines(rows), "", f"VERDICT {verdict}"])
    (ctx.out / "report.txt").write_text(text, encoding="utf-8")
    (ctx.out / "verdict.json").write_text(json.dumps({"verdict": verdict, "why": why}, indent=1), encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
