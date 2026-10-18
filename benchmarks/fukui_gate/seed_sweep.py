"""POST-GATE SWEEP (not the gate, decides nothing, changes nothing shipped): how reproducible is the application's own Fukui calculation when the
only thing that changes is the starting embedding?

Every gate species at the four levels of the published table, three different RDKit embedding seeds, each optimized by ORCA at its own level (as the
gate's blocks do) and then run through the application's own three-job Fukui input at ORCA's default grid. Reported: for each species and level, the
largest difference between the three seeds in any HEAVY atom's f+ and in any heavy atom's f- (the equivalent hydrogens of a methyl group are numbered
by position, which differs between embeddings, so an all-atom spread of acetone is that and not a result; it is kept beside the heavy-atom one), and the
spread of the optimized total energy (the three seeds should be one minimum). Standalone ORCA in fresh directories, four species-levels at a time.

    python seed_sweep.py [output.json]                 # run everything (about 25 minutes)
    python seed_sweep.py --resummarize output.json     # recompute the summary from the rows already in the file
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
SEEDS = (7, 11, 23)
COORDS = re.compile(r"^\s*([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")
ENERGY = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")


def orca(work: Path, text: str) -> str:
    work.mkdir(parents=True, exist_ok=True)
    (work / "job.inp").write_text(text)
    out = subprocess.run([ORCA, str(work / "job.inp")], capture_output=True, text=True, cwd=work).stdout
    (work / "job.out").write_text(out)
    return out


def embedded(smiles: str, seed: int) -> list[str]:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
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
    assert len(atoms) == expected
    return atoms


def one(root: Path, task: tuple[str, str, int]) -> dict:
    name, level, seed = task
    species = gate.SPECIES[name]
    method = gate.METHOD_BASIS[level]
    tag = re.sub(r"\W+", "_", f"{name}_{level}_{seed}")
    start = embedded(species.smiles, seed)
    opt = orca(root / tag / "opt", f"! {method} {_CALC_TYPE_KEYWORDS['opt']}".strip() + f"\n* xyz {species.charge} 1\n" + "\n".join(start) + "\n*\n")
    energy = ENERGY.findall(opt)
    geometry = optimized(opt, len(start))
    out = orca(root / tag / "fukui", OrcaQuantumEngineProvider()._build_fukui_input(f"! {method} {_CALC_TYPE_KEYWORDS['fukui']}".strip(), geometry, species.charge, 1))
    tables = parse_hirshfeld_tables(out)
    row = {"species": name, "level": level, "seed": seed, "opt_energy": float(energy[-1]) if energy else None}
    if len(tables) == 3:
        neutral, cation, anion = ([charge for _e, charge in table] for table in tables)
        row["f_plus"] = [n - a for n, a in zip(neutral, anion)]
        row["f_minus"] = [c - n for n, c in zip(neutral, cation)]
    print(name, level, seed, row.get("f_plus") and [round(v, 3) for v in row["f_plus"][:4]], flush=True)
    return row


def summarize(rows: list[dict]) -> list[dict]:
    summary = []
    for level in gate.OLAH_LEVELS:
        for name in gate.SPECIES:
            group = [r for r in rows if r["species"] == name and r["level"] == level and "f_plus" in r]
            if len(group) < 2:
                summary.append({"species": name, "level": level, "seeds": len(group)})
                continue
            atoms = gate.SPECIES[name].atoms
            heavy = [i for i, a in enumerate(atoms) if a != "H"]

            def spread(key: str, indices) -> float:
                return max(max(abs(g1[key][i] - g2[key][i]) for i in indices) for g1 in group for g2 in group)

            energies = [r["opt_energy"] for r in group if r["opt_energy"] is not None]
            summary.append({
                "species": name, "level": level, "seeds": len(group),
                "heavy_f_plus_spread": round(spread("f_plus", heavy), 4), "heavy_f_minus_spread": round(spread("f_minus", heavy), 4),
                "all_atoms_f_plus_spread": round(spread("f_plus", range(len(atoms))), 4), "all_atoms_f_minus_spread": round(spread("f_minus", range(len(atoms))), 4),
                "opt_energy_spread_eV": round((max(energies) - min(energies)) * 27.2114, 4),
            })
    return summary


def main() -> None:
    if sys.argv[1:2] == ["--resummarize"]:
        path = Path(sys.argv[2])
        data = json.loads(path.read_text())
        data["summary"] = summarize(data["rows"])
        path.write_text(json.dumps(data, indent=1))
        print("resummarized", path)
        return
    root = Path(tempfile.mkdtemp(prefix="fukui_seed_sweep_"))
    tasks = [(name, level, seed) for level in gate.OLAH_LEVELS for name in gate.SPECIES for seed in SEEDS]
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda task: one(root, task), tasks))
    summary = summarize(rows)
    Path(sys.argv[1] if len(sys.argv) > 1 else "seed_sweep.json").write_text(json.dumps({"scratch": str(root), "rows": rows, "summary": summary}, indent=1))
    print("\nSUMMARY: largest seed-to-seed difference in any heavy atom's f+ and f-, and the spread of the optimized energy")
    for s in summary:
        print(s)


if __name__ == "__main__":
    main()
