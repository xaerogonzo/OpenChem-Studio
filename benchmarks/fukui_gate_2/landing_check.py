"""POST-GATE CHECK 4 (not the gate, decides nothing, changes nothing shipped): how often does the application's input land on each N-1 state when only NOISE changes?

`core_check.py` showed that the core count does not decide it (benzaldehyde on probe 1's geometry reached the same N-1 state, to 11 digits of energy, at 8, 4, 2 and 1 cores) and `route_check.py` that the
gate's run (the lowest state) and a rerun on probe 1's geometry (a state 0.145 eV above it) differ. The gate's geometry is not stored, so what separates them was not measured. This measures how big a
change is needed to move the landing, with the application's own three-job input (`OrcaQuantumEngineProvider._build_fukui_input`) at the application's own core count:

  rotations   the SAME geometry, rigidly rotated: the physics is identical, the DFT integration grid and the integrals are not, so this is numerical noise alone
  noise       the same geometry with every coordinate displaced by Gaussian noise of sigma `--sigma` Angstrom (the optimizer's own tolerance is of this order)
  embeddings  independent ORCA optimizations from RDKit embeddings with different seeds, as the gate's own run was (an unknown seed of the application's own embedding)

Each variant is classified by the Hirshfeld f- it gave: within 0.01 of the published numbers (the state 0.145 eV above the lowest), or not (the lowest state, or another).

    python landing_check.py <probe json> <output json> <species> [--cores 8] [--rotations 4] [--noise 4] [--sigma 0.001] [--embeddings 5] [--seed 2026]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cation_states_probe as probe
import numpy as np
import route_check
from openchem.chem.orca_engine import _CALC_TYPE_KEYWORDS, OrcaQuantumEngineProvider, add_parallel_block, parse_hirshfeld_tables
from rdkit import Chem
from rdkit.Chem import AllChem

MATCH = 0.01


def split(atoms: list[str]) -> tuple[list[str], np.ndarray]:
    symbols = [line.split()[0] for line in atoms]
    return symbols, np.array([[float(v) for v in line.split()[1:4]] for line in atoms])


def join(symbols: list[str], xyz: np.ndarray) -> list[str]:
    return [f"{s:<3}{x:>14.6f}{y:>14.6f}{z:>14.6f}" for s, (x, y, z) in zip(symbols, xyz)]


def random_rotation(rng: np.random.Generator) -> np.ndarray:
    q, r = np.linalg.qr(rng.normal(size=(3, 3)))
    q = q * np.sign(np.diag(r))
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    return q


def optimized_from(name: str, species, seed: int) -> list[str]:
    """`probe.optimized`, from an embedding with this seed (the probe's own is 7)."""
    method = probe.gate.METHOD_BASIS[species.level]
    mol = Chem.AddHs(Chem.MolFromSmiles(species.smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
    conf = mol.GetConformer()
    start = [f"{a.GetSymbol():<3}{conf.GetAtomPosition(a.GetIdx()).x:>14.6f}{conf.GetAtomPosition(a.GetIdx()).y:>14.6f}{conf.GetAtomPosition(a.GetIdx()).z:>14.6f}" for a in mol.GetAtoms()]
    out, _ = probe.run(f"{name}_opt_seed{seed}", f"! {method} Opt\n%pal nprocs {probe.CORES} end\n* xyz {species.charge} 1\n" + "\n".join(start) + "\n*\n")
    block = out[out.rfind("CARTESIAN COORDINATES (ANGSTROEM)"):]
    atoms = []
    for line in block.splitlines()[2:]:
        match = probe.COORDS.match(line)
        if not match:
            break
        atoms.append(f"{match.group(1):<3}{float(match.group(2)):>14.6f}{float(match.group(3)):>14.6f}{float(match.group(4)):>14.6f}")
    assert len(atoms) == len(species.atoms), (name, seed, len(atoms))
    return atoms


def land(name: str, label: str, atoms: list[str], cores: int, probe_rows: list[dict]) -> dict:
    species = probe.gate.ALL_SPECIES[name]
    method = probe.gate.METHOD_BASIS[species.level]
    header = f"! {method} {_CALC_TYPE_KEYWORDS['fukui']}".strip()
    text = OrcaQuantumEngineProvider()._build_fukui_input(header, atoms, species.charge, 1, diffuse=False)
    out, _work = probe.run(f"{name}_{label}", add_parallel_block(text, cores))
    energies = [float(e) for e in probe.ENERGY.findall(out)]
    tables = parse_hirshfeld_tables(out)
    result = {"variant": label, "jobs_with_energy": len(energies), "tables": len(tables)}
    if len(energies) < 2 or len(tables) < 2:
        result["converged"] = False
    else:
        neutral, cation = [q for _e, q in tables[0]], [q for _e, q in tables[1]]
        distance, labelled = probe.f_minus_distance(name, species, [c - n for n, c in zip(neutral, cation)])
        result.update({
            "converged": True, "n_minus_1_energy": energies[1], "max_distance_to_published": round(distance, 4), "by_label": labelled,
            "matches_published": distance <= MATCH,
            # only meaningful for the probe geometry; another geometry shifts every energy a little
            "above_probe_lowest_ev": round((energies[1] - route_check.lowest_energy(probe_rows, name)) * probe.HARTREE_TO_EV, 3),
        })
    print(json.dumps(result), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("probe_json")
    parser.add_argument("output_json")
    parser.add_argument("species")
    parser.add_argument("--cores", type=int, default=8)
    parser.add_argument("--rotations", type=int, default=4)
    parser.add_argument("--noise", type=int, default=4)
    parser.add_argument("--sigma", type=float, default=0.001)
    parser.add_argument("--embeddings", type=int, default=5)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    probe_rows = json.loads(Path(args.probe_json).read_text(encoding="utf-8"))["rows"]
    name = args.species
    species = probe.gate.ALL_SPECIES[name]
    rng = np.random.default_rng(args.seed)
    base = probe.optimized(name, species)
    symbols, xyz = split(base)
    rows = [dict(land(name, "reference", base, args.cores, probe_rows), group="reference")]
    for k in range(args.rotations):
        rows.append(dict(land(name, f"rotation{k}", join(symbols, xyz @ random_rotation(rng).T), args.cores, probe_rows), group="rotation"))
    for k in range(args.noise):
        rows.append(dict(land(name, f"noise{k}", join(symbols, xyz + rng.normal(scale=args.sigma, size=xyz.shape)), args.cores, probe_rows), group="noise", sigma=args.sigma))
    for k in range(args.embeddings):
        seed = 100 + k
        rows.append(dict(land(name, f"embedding{seed}", optimized_from(name, species, seed), args.cores, probe_rows), group="embedding", embedding_seed=seed))
    Path(args.output_json).write_text(json.dumps({"scratch": str(probe.ROOT), "species": name, "cores": args.cores, "rows": rows}, indent=1), encoding="utf-8")
    print("\nSUMMARY (matches = f- within 0.01 of the published numbers)")
    for group in ("reference", "rotation", "noise", "embedding"):
        part = [r for r in rows if r["group"] == group and r.get("converged")]
        print(f"{group:10s}: {sum(1 for r in part if r['matches_published'])} of {len(part)} reach the published-like state; max distances {[r['max_distance_to_published'] for r in part]}")


if __name__ == "__main__":
    main()
