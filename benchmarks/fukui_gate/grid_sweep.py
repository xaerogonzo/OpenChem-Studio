"""POST-GATE SWEEP (not the gate, decides nothing, changes nothing shipped): does ORCA's integration grid move the Fukui numbers?

Every gate species at the four levels of the published table, each optimized by ORCA at its own level (as the gate's blocks do), then the
application's own three-job Fukui input run twice on that geometry: ORCA's default grid, and `%method IntAcc 6.0 end` in every job's header.
Standalone ORCA in fresh directories, four species-levels at a time. The values are the application's arithmetic (f+ = q(N) - q(N+1),
f- = q(N-1) - q(N), Hirshfeld) applied WITHOUT its charge-sum rule, so a state the application would refuse is still read and its
shortfall is reported beside it. Compared with the published numbers through `openchem.app.fukui_gate.compare`, at the gate's tolerance, undecided.

    python grid_sweep.py [output.json]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.app import fukui_gate as gate
from openchem.chem.orca_engine import _CALC_TYPE_KEYWORDS, OrcaQuantumEngineProvider, parse_hirshfeld_tables

ORCA = r"D:\ORCA\orca.exe"
ROOT = Path(tempfile.mkdtemp(prefix="fukui_grid_sweep_"))
FINER = "%method\n  IntAcc 6.0\nend"
GRIDS = {"default": "", "IntAcc 6.0": FINER}
COORDS = re.compile(r"^\s*([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")


def orca(work: Path, text: str) -> str:
    work.mkdir(parents=True, exist_ok=True)
    (work / "job.inp").write_text(text)
    out = subprocess.run([ORCA, str(work / "job.inp")], capture_output=True, text=True, cwd=work).stdout
    (work / "job.out").write_text(out)
    return out


def embedded(species: gate.Species) -> list[str]:
    mol = Chem.AddHs(Chem.MolFromSmiles(species.smiles))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    conf = mol.GetConformer()
    return [f"{a.GetSymbol():<3}{conf.GetAtomPosition(a.GetIdx()).x:>14.6f}{conf.GetAtomPosition(a.GetIdx()).y:>14.6f}{conf.GetAtomPosition(a.GetIdx()).z:>14.6f}" for a in mol.GetAtoms()]


def optimized(out: str, expected: int) -> list[str]:
    block = out[out.rfind("CARTESIAN COORDINATES (ANGSTROEM)"):]
    atoms = []
    for line in block.splitlines()[2:]:
        match = COORDS.match(line)
        if not match:
            break
        atoms.append(f"{match.group(1):<3}{float(match.group(2)):>14.6f}{float(match.group(3)):>14.6f}{float(match.group(4)):>14.6f}")
    assert len(atoms) == expected, (len(atoms), expected)
    return atoms


def one(task: tuple[str, str]) -> list[dict]:
    name, level = task
    species = gate.SPECIES[name]
    method = gate.METHOD_BASIS[level]
    tag = re.sub(r"\W+", "_", f"{name}_{level}")
    engine = OrcaQuantumEngineProvider()
    start = embedded(species)
    opt = orca(ROOT / tag / "opt", f"! {method} {_CALC_TYPE_KEYWORDS['opt']}".strip() + f"\n* xyz {species.charge} 1\n" + "\n".join(start) + "\n*\n")
    geometry = optimized(opt, len(start))
    results = []
    for grid, block in GRIDS.items():
        header = f"! {method} {_CALC_TYPE_KEYWORDS['fukui']}".strip() + ("\n" + block if block else "")
        out = orca(ROOT / tag / grid.replace(" ", "_").replace(".", "_"), engine._build_fukui_input(header, geometry, species.charge, 1))
        tables = parse_hirshfeld_tables(out)
        row = {"species": name, "level": level, "grid": grid, "tables": len(tables)}
        if len(tables) == 3:
            neutral, cation, anion = ([charge for _el, charge in table] for table in tables)
            symbols = tuple(element for element, _charge in tables[0])
            row["short"] = {state: round(sum(table) - expected, 4) for state, table, expected in (
                ("neutral", neutral, species.charge), ("cation", cation, species.charge + 1), ("anion", anion, species.charge - 1))}
            f_plus = tuple(n - a for n, a in zip(neutral, anion))
            f_minus = tuple(c - n for n, c in zip(neutral, cation))
            row["run"] = gate.MeasuredRun(
                name, level, symbols, f_plus, f_minus, tuple((p + m) / 2 for p, m in zip(f_plus, f_minus)),
                tuple(p - m for p, m in zip(f_plus, f_minus)), species.charge, 1, "6.1.1")
        results.append(row)
        print(name, level, grid, row.get("short"), flush=True)
    return results


def main() -> None:
    tasks = [(name, level) for level in gate.OLAH_LEVELS for name in gate.SPECIES]
    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(one, tasks))
    # what the gate itself compares: the decided Olah numbers at the 6-31G** levels and Olah's 6-311+G** columns (every one, the refused jobs' included)
    entries = [e for e in gate.decided_entries() if e.source == "olah2002"] + [
        e for e in gate.reported_entries() if e.source == "olah2002" and e.level in gate.REPORTED_LEVELS
    ] + list(gate.bultinck_entries())
    summary = []
    for grid in GRIDS:
        runs = {(row["species"], row["level"]): row["run"] for batch in batches for row in batch if row["grid"] == grid and "run" in row}
        rows = gate.compare(entries, runs, gate.TOLERANCE, decided=False)
        for level in gate.OLAH_LEVELS:
            for attack in gate.ATTACKS:
                picked = [r for r in rows if r.level == level and r.attack == attack and r.source == "olah2002"]
                if picked:
                    summary.append({"grid": grid, "level": level, "attack": attack, "rows": len(picked), "within": sum(1 for r in picked if r.within),
                                    "max_abs_diff": round(max(abs(r.difference) for r in picked), 4)})
        for r in rows:
            if r.source == "bultinck2007" and r.level == gate.HF_B:
                summary.append({"grid": grid, "level": r.level, "bultinck": r.element + " " + r.attack, "diff": round(r.difference, 4), "within": r.within})
    movement = []
    for batch in batches:
        first, second = batch
        if "run" in first and "run" in second:
            worst = max(abs(a - b) for attack in gate.ATTACKS for a, b in zip(first["run"].values(attack), second["run"].values(attack)))
            movement.append({"species": first["species"], "level": first["level"], "max_change_in_f": round(worst, 4),
                             "short_default": first["short"], "short_fine": second["short"]})
    out = {"scratch": str(ROOT), "summary": summary, "movement": movement}
    Path(sys.argv[1] if len(sys.argv) > 1 else "grid_sweep.json").write_text(json.dumps(out, indent=1))
    for line in movement:
        print(line)
    for line in summary:
        print(line)


if __name__ == "__main__":
    main()
