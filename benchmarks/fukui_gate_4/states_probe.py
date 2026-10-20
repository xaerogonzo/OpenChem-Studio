"""EXPLORATORY probe for the fourth Fukui gate (decides nothing, nothing shipped): the exhaustive hole search of one molecule with the character of every cation state read from ORCA's own
Loewdin spin populations, on a molecule oriented with its plane as xy.

    python states_probe.py NAME [--geometry KEY] [--cores 4] [--holes 7]

NAME is a species of the second or third gate (its optimised geometry is read from `benchmarks/fukui_v3/artifacts/geometries.json`, key `NAME_reference`) or, with ``--smiles``, a molecule whose
geometry is optimised here. It prints one row per cation job: how far above the lowest it lies, the out-of-plane fraction of its spin (the pi character, 1 for a pure pi hole and 0 for a pure
sigma one) and the spin on each non-hydrogen atom. This is the CALIBRATION of the reading, run on molecules whose results were seen before the fourth gate was written (PREREGISTRATION.md 2).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Geometry import Point3D

from openchem.app import fukui_gate_4 as gate
from openchem.chem.fukui_plan import has_diffuse_functions, searchable_holes
from openchem.chem.orca_engine import _CALC_TYPE_KEYWORDS, OrcaQuantumEngineProvider, add_parallel_block
from openchem.chem.orca_engine import _TOTAL_CHARGE_RE

ORCA = r"D:\ORCA\orca.exe"
REPO = Path(__file__).resolve().parents[2]
GEOMETRIES = REPO / "benchmarks" / "fukui_v3" / "artifacts" / "geometries.json"
SMILES = {"pyridine": "c1ccncc1", "thiophene": "c1ccsc1", "pyrrole": "c1cc[nH]c1", "furan": "c1ccoc1"}


def oriented(xyz: np.ndarray) -> np.ndarray:
    """The coordinates centred and rotated so that the plane of a planar molecule is xy (the direction of least spread is z)."""
    centred = xyz - xyz.mean(axis=0)
    _values, vectors = np.linalg.eigh(np.cov(centred.T))
    basis = vectors[:, ::-1]  # largest spread first, least last: z
    if np.linalg.det(basis) < 0:
        basis[:, 2] *= -1
    return centred @ basis


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--smiles")
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--holes", type=int, default=7)
    parser.add_argument("--method", default="B3LYP 6-31G*")
    args = parser.parse_args()

    smiles = args.smiles or SMILES[args.name]
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    stored = json.loads(GEOMETRIES.read_text())[f"{args.name}_reference"]
    xyz = oriented(np.array(stored))
    conf = mol.GetConformer()
    for index, (x, y, z) in enumerate(xyz):
        conf.SetAtomPosition(index, Point3D(float(x), float(y), float(z)))
    coordinates = [f"{a.GetSymbol():<3}{conf.GetAtomPosition(a.GetIdx()).x:>14.6f}{conf.GetAtomPosition(a.GetIdx()).y:>14.6f}{conf.GetAtomPosition(a.GetIdx()).z:>14.6f}" for a in mol.GetAtoms()]
    provider = OrcaQuantumEngineProvider(cation_search=lambda: True)
    search = searchable_holes([a.GetAtomicNum() for a in mol.GetAtoms()], 0, offsets=tuple(range(1, args.holes + 1)))
    header = f"! {args.method} {_CALC_TYPE_KEYWORDS['fukui']}".strip()
    text = provider._build_fukui_input(header, coordinates, 0, 1, diffuse=has_diffuse_functions(args.method), holes=search.offsets, homo=search.homo)
    work = Path(tempfile.mkdtemp(prefix=f"g4probe_{args.name}_"))
    (work / "job.inp").write_text(add_parallel_block(text, args.cores))
    began = time.time()
    done = subprocess.run([ORCA, "job.inp"], capture_output=True, text=True, cwd=work)
    out = done.stdout
    (work / "job.out").write_text(out)
    symbols = [a.GetSymbol().upper() for a in mol.GetAtoms()]
    print(f"{args.name}: exit {done.returncode}, {time.time() - began:.0f} s, {work}")
    results = provider._fukui_job_results(out, symbols)
    starts = [m.start() for m in _TOTAL_CHARGE_RE.finditer(out)]
    segments = [out[a:b] for a, b in zip(starts, [*starts[1:], len(out)])]
    cation = [(i, r) for i, r in enumerate(results) if r.state == "N-1" and r.energy_hartree is not None]
    lowest = min(r.energy_hartree for _i, r in cation)
    heavy = [i for i, s in enumerate(symbols) if s != "H"]
    print(f"{'job':>3} {'start':<22} {'above eV':>9} {'S2':>6} {'out-of-plane':>12}   spin on " + " ".join(f"{symbols[i]}{i}" for i in heavy))
    for i, r in sorted(cation, key=lambda t: t[1].energy_hartree):
        spins = gate.parse_lowdin_spin(segments[i], len(symbols))
        frac = gate.out_of_plane_fraction(spins) if spins else float("nan")
        per_atom = " ".join(f"{sum(spins[k].values()):6.3f}" for k in heavy) if spins else ""
        print(f"{i + 1:>3} {str(r.start):<22} {(r.energy_hartree - lowest) * gate.HARTREE_TO_EV:9.3f} {r.s_squared if r.s_squared is not None else float('nan'):6.3f} {frac:12.3f}   {per_atom}")


if __name__ == "__main__":
    main()
