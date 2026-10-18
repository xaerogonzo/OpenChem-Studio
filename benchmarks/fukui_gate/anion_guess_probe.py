"""POST-GATE PROBE (not the gate, decides nothing, changes nothing shipped): is the unbound anion's SCF solution unique?

The N+1 state of a neutral closed-shell molecule is unbound, and with diffuse functions its extra electron can sit in a valence pi*/sigma* orbital or in a
diffuse one. The application runs ORCA's default initial guess once (inside a compound input, where ORCA starts the anion from the CATION's orbitals) and
reads whatever converged. Here the same anion, at the ORCA-optimized geometry the grid sweep (`grid_sweep.py`) wrote and with the application's own
keywords, is run standalone with other initial guesses (Hueckel, PAtom, HCore) and with ORCA's UHF stability analysis, and each solution is read: its SCF
energy, <S**2> and the Hirshfeld f+ it gives with the grid sweep's neutral table.

    python anion_guess_probe.py <grid_sweep scratch directory> diffuse|gated [output.json]

`diffuse` is the six cases that carry the question at the 6-311+G** levels; `gated` is every gate species at the two 6-31G** levels the gate decided on.
A variant whose job failed has no energy and is reported as such (ORCA's stability analysis stops with an error for some of the diatomics).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openchem.app import fukui_gate as gate
from openchem.chem.orca_engine import parse_hirshfeld_tables

ORCA = r"D:\ORCA\orca.exe"
SWEEP = Path(sys.argv[1])
MODE = sys.argv[2]
ROOT = Path(tempfile.mkdtemp(prefix="fukui_anion_probe_"))
COORDS = re.compile(r"^\s*([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")
ENERGY = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
S2 = re.compile(r"Expectation value of <S\*\*2>\s*:\s*(-?\d+\.\d+)")
DIRS = {"CO": "CO", "CO2": "CO2", "H2CO": "H2CO", "acetone": "acetone", "CN-": "CN_", "NCO-": "NCO_", "CNO-": "CNO_"}
STAB = "%scf\n  StabPerform true\n  StabRestartUHFifUnstable true\nend\n"
VARIANTS = (("default", "", ""), ("Hueckel", "Hueckel", ""), ("PAtom", "PAtom", ""), ("HCore", "HCore", ""), ("stability", "", STAB))
if MODE == "diffuse":
    CASES = (("acetone", gate.HF_A), ("acetone", gate.DFT_A), ("CN-", gate.HF_A), ("CN-", gate.DFT_A), ("CNO-", gate.DFT_A), ("H2CO", gate.DFT_A))
else:
    CASES = tuple((name, level) for level in (gate.HF_B, gate.DFT_B) for name in gate.SPECIES)


def geometry(name: str, level: str) -> list[str]:
    tag = re.sub(r"\W+", "_", f"{DIRS[name]}_{level}")
    out = (SWEEP / tag / "opt" / "job.out").read_text(errors="replace")
    block = out[out.rfind("CARTESIAN COORDINATES (ANGSTROEM)"):]
    atoms = []
    for line in block.splitlines()[2:]:
        match = COORDS.match(line)
        if not match:
            break
        atoms.append(f"{match.group(1):<3}{float(match.group(2)):>14.6f}{float(match.group(3)):>14.6f}{float(match.group(4)):>14.6f}")
    return atoms


def neutral_table(name: str, level: str) -> list[float]:
    tag = re.sub(r"\W+", "_", f"{DIRS[name]}_{level}")
    first = (SWEEP / tag / "default" / "job.out").read_text(errors="replace")
    return [charge for _e, charge in parse_hirshfeld_tables(first)[0]]


def one(case: tuple[str, str]) -> list[dict]:
    name, level = case
    species = gate.SPECIES[name]
    method = gate.METHOD_BASIS[level]
    body = "\n".join(geometry(name, level))
    neutral = neutral_table(name, level)
    rows = []
    for label, guess, block in VARIANTS:
        work = ROOT / re.sub(r"\W+", "_", f"{name}_{level}_{label}")
        work.mkdir(parents=True, exist_ok=True)
        (work / "job.inp").write_text(f"! {method} {guess}\n{block}%output\n  Print[P_Hirshfeld] 1\nend\n* xyz {species.charge - 1} 2\n{body}\n*\n")
        out = subprocess.run([ORCA, str(work / "job.inp")], capture_output=True, text=True, cwd=work).stdout
        (work / "job.out").write_text(out)
        energy = ENERGY.findall(out)
        squares = S2.findall(out)
        tables = parse_hirshfeld_tables(out)
        row = {"species": name, "level": level, "variant": label, "energy_hartree": float(energy[-1]) if energy else None, "s2": float(squares[-1]) if squares else None}
        if tables:
            row["f_plus"] = [round(n - a, 4) for n, a in zip(neutral, [charge for _e, charge in tables[-1]])]
        rows.append(row)
        print(row, flush=True)
    return rows


def main() -> None:
    with ThreadPoolExecutor(max_workers=3) as pool:
        batches = list(pool.map(one, CASES))
    print("\nSUMMARY (energy relative to the default guess; f+ of the heavy atoms and the first hydrogens)")
    for rows in batches:
        base = rows[0]["energy_hartree"]
        print(rows[0]["species"], rows[0]["level"])
        for r in rows:
            delta = "no energy (job failed)" if r["energy_hartree"] is None or base is None else f"{(r['energy_hartree'] - base) * 27.2114:+.3f} eV"
            print(f"   {r['variant']:10s} {delta:>24s}  <S2> {r['s2']}  f+ {r.get('f_plus', [])[:4]}")
    out_path = Path(sys.argv[3] if len(sys.argv) > 3 else f"anion_guess_probe_{MODE}.json")
    out_path.write_text(json.dumps({"scratch": str(ROOT), "mode": MODE, "rows": [row for rows in batches for row in rows]}, indent=1))


if __name__ == "__main__":
    main()
