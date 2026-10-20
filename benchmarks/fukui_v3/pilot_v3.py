"""EXPLORATORY PILOT of Fukui v3 (decides nothing, nothing shipped): is the f- the application's own parse reports the same under the noise that made v2's benzaldehyde a coin flip?

For one molecule: an ORCA B3LYP/6-31G* optimization from an RDKit ETKDG seed-7 + MMFF embedding (the probe's recipe), then the application's own input (`OrcaQuantumEngineProvider`, the cation
search ON) on that geometry, on `--rotations` rigid rotations of it and on `--noise` copies with every coordinate displaced by Gaussian noise of sigma 0.001 A, each run through real ORCA and
read with `parse_per_atom_output`. Reports, per run, f- against the reference run's f- (largest difference over atoms), the lowest N-1 energy, how many states were found and the competing ones.
The same runs with the search OFF (`--v2`) are the control: that is v2's own input, and the spread it gives is what the search is for.

    python pilot_v3.py <name> <smiles> [--rotations 4] [--noise 4] [--sigma 0.001] [--cores 4] [--workers 6] [--v2] [--seed 2026]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Geometry import Point3D

from openchem.chem.orca_engine import OrcaQuantumEngineProvider, add_parallel_block

ORCA = r"D:\ORCA\orca.exe"
METHOD = "B3LYP 6-31G*"
COORDS = re.compile(r"^\s*([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")
HARTREE_TO_EV = 27.211386245988
ROOT = Path(tempfile.mkdtemp(prefix="pilot_v3_"))


def orca(name: str, text: str, cores: int) -> str:
    work = ROOT / re.sub(r"\W+", "_", name)
    work.mkdir(parents=True, exist_ok=True)
    (work / "job.inp").write_text(text)
    out = subprocess.run([ORCA, "job.inp"], capture_output=True, text=True, cwd=work).stdout
    (work / "job.out").write_text(out)
    return out


def embedded(smiles: str, seed: int = 7) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
    return mol


def optimized(name: str, mol: Chem.Mol, cores: int) -> np.ndarray:
    conf = mol.GetConformer()
    start = [f"{a.GetSymbol():<3}{conf.GetAtomPosition(a.GetIdx()).x:>14.6f}{conf.GetAtomPosition(a.GetIdx()).y:>14.6f}{conf.GetAtomPosition(a.GetIdx()).z:>14.6f}" for a in mol.GetAtoms()]
    out = orca(f"{name}_opt", f"! {METHOD} Opt\n%pal nprocs {cores} end\n* xyz 0 1\n" + "\n".join(start) + "\n*\n", cores)
    assert "THE OPTIMIZATION HAS CONVERGED" in out, name
    block = out[out.rfind("CARTESIAN COORDINATES (ANGSTROEM)"):]
    atoms = []
    for line in block.splitlines()[2:]:
        match = COORDS.match(line)
        if not match:
            break
        atoms.append([float(match.group(2)), float(match.group(3)), float(match.group(4))])
    assert len(atoms) == mol.GetNumAtoms()
    return np.array(atoms)


def with_coordinates(mol: Chem.Mol, xyz: np.ndarray) -> Chem.Mol:
    clone = Chem.Mol(mol)
    conf = clone.GetConformer()
    for index, (x, y, z) in enumerate(xyz):
        conf.SetAtomPosition(index, Point3D(float(x), float(y), float(z)))
    return clone


def random_rotation(rng: np.random.Generator) -> np.ndarray:
    q, r = np.linalg.qr(rng.normal(size=(3, 3)))
    q = q * np.sign(np.diag(r))
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    return q


def run(name: str, label: str, mol: Chem.Mol, search: bool, cores: int) -> dict:
    provider = OrcaQuantumEngineProvider(cation_search=lambda: search)
    text = add_parallel_block(provider.build_input(mol, 0, 1, METHOD, "fukui"), cores)
    began = time.time()
    out = orca(f"{name}_{label}", text, cores)
    seconds = time.time() - began
    try:
        datasets = {d.property_id: d for d in provider.parse_per_atom_output(out, mol, "m", "fukui")}
    except Exception as error:  # noqa: BLE001
        return {"label": label, "error": str(error), "seconds": seconds}
    minus = datasets["orca.fukui_minus"]
    parameters = minus.provenance.parameters
    return {
        "label": label, "seconds": round(seconds), "f_minus": [minus.values[i] for i in range(len(minus.values))],
        "states_found": parameters.get("cation_states_found"), "competing_ev": parameters.get("cation_competing_ev"), "search": parameters.get("cation_search"),
        "note": parameters.get("cation_note", ""), "start_gain_ev": parameters.get("start_gain_ev"), "starts_run": parameters.get("starts_run"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("smiles")
    parser.add_argument("--rotations", type=int, default=4)
    parser.add_argument("--noise", type=int, default=4)
    parser.add_argument("--sigma", type=float, default=0.001)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--v2", action="store_true", help="the control: the same runs with the search off")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    mol = embedded(args.smiles)
    base = optimized(args.name, mol, args.cores)
    rng = np.random.default_rng(args.seed)
    variants = [("reference", base)]
    variants += [(f"rotation{k}", base @ random_rotation(rng).T) for k in range(args.rotations)]
    variants += [(f"noise{k}", base + rng.normal(scale=args.sigma, size=base.shape)) for k in range(args.noise)]
    search = not args.v2
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda item: run(args.name, item[0], with_coordinates(mol, item[1]), search, args.cores), variants))
    reference = rows[0]
    print(f"\n{args.name} ({args.smiles}), search {'ON' if search else 'OFF (v2)'}, scratch {ROOT}")
    for row in rows:
        if "error" in row:
            print(f"  {row['label']:11s} ERROR {row['error'][:100]}")
            continue
        spread = max(abs(a - b) for a, b in zip(row["f_minus"], reference["f_minus"])) if "f_minus" in reference else float("nan")
        print(f"  {row['label']:11s} max|f- - reference| = {spread:.4f}   states {row['states_found']}  competing_ev {row['competing_ev'] if row['competing_ev'] is None else round(row['competing_ev'], 3)}  gain {row['start_gain_ev'] if row['start_gain_ev'] is None else round(row['start_gain_ev'], 3)}  {row['seconds']} s")
    spreads = [max(abs(a - b) for a, b in zip(row["f_minus"], reference["f_minus"])) for row in rows[1:] if "f_minus" in row]
    print(f"  WORST over {len(spreads)} runs: {max(spreads):.4f}" if spreads else "  no runs")
    (ROOT / "pilot.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
