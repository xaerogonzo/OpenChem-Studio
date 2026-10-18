"""POST-GATE PROBE (not the gate, decides nothing, changes nothing shipped): which N-1 state did the published numbers and the application each describe?

The second gate failed on the f- of molecules whose lowest cation states lie close together (benzaldehyde, the five-membered rings, HCN, anilinium, thiocyanate's sulfur) while
reproducing eleven other molecules to 0.002 or better. The application's N-1 job starts from the neutral's orbitals and removes the electron of the HOMO (ORCA's aufbau), so it
reaches ONE state; De Proft et al.'s own tables carry the integrated HOMO density beside each f-, and for benzaldehyde and anilinium it describes a different orbital from the one
the application emptied. This probe converges the N-1 state with its hole in the HOMO, the HOMO-1, the HOMO-2 (and HOMO-3) of the N state, by rotating the beta orbitals of the
guess (`%scf Rotate {HOMO-k, HOMO, 90, 1, 1} end`, which was checked on water: the 3a1 hole came out 2.2 eV above the 1b1 one), and reports for each state its energy above the
lowest found, its <S**2>, the Hirshfeld f- it gives, and how far that is from the published numbers.

    python cation_states_probe.py <output json> [species ...]

Standalone ORCA 6.1.1, a fresh directory per job, B3LYP 6-31G* (6-31+G* for the anions), the application's own settings for the single points (`IntAcc 6.0`, RHF for the N state, UHF for
the N-1 state, Hirshfeld printed). The geometry is ORCA's own optimization from an RDKit ETKDG (seed 7) + MMFF embedding, as the gate's was.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.app import fukui_gate_2 as gate
from openchem.chem.orca_engine import parse_hirshfeld_tables

ORCA = r"D:\ORCA\orca.exe"
CORES = 4
ROOT = Path(tempfile.mkdtemp(prefix="cation_states_"))
ENERGY = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
S2 = re.compile(r"Expectation value of <S\*\*2>\s*:\s*(-?\d+\.\d+)")
COORDS = re.compile(r"^\s*([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")
HARTREE_TO_EV = 27.211386245988
FAILED = ("HCN", "benzaldehyde", "pyrrole", "furan", "thiophene", "anilinium", "SCN-")
CONTROLS = ("phenol", "aniline", "N2O", "styrene")
HOLES = (0, 1, 2, 3)


def run(name: str, text: str) -> tuple[str, Path]:
    work = ROOT / re.sub(r"\W+", "_", name)
    work.mkdir(parents=True, exist_ok=True)
    (work / "job.inp").write_text(text)
    out = subprocess.run([ORCA, str(work / "job.inp")], capture_output=True, text=True, cwd=work).stdout
    (work / "job.out").write_text(out)
    return out, work


def coordinates(smiles: str) -> list[str]:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
    conf = mol.GetConformer()
    return [f"{a.GetSymbol():<3}{conf.GetAtomPosition(a.GetIdx()).x:>14.6f}{conf.GetAtomPosition(a.GetIdx()).y:>14.6f}{conf.GetAtomPosition(a.GetIdx()).z:>14.6f}" for a in mol.GetAtoms()]


def optimized(name: str, species: gate.GateSpecies) -> list[str]:
    method = gate.METHOD_BASIS[species.level]
    pal = f"%pal nprocs {CORES} end\n"
    out, _ = run(f"{name}_opt", f"! {method} Opt\n{pal}* xyz {species.charge} 1\n" + "\n".join(coordinates(species.smiles)) + "\n*\n")
    block = out[out.rfind("CARTESIAN COORDINATES (ANGSTROEM)"):]
    atoms = []
    for line in block.splitlines()[2:]:
        match = COORDS.match(line)
        if not match:
            break
        atoms.append(f"{match.group(1):<3}{float(match.group(2)):>14.6f}{float(match.group(3)):>14.6f}{float(match.group(4)):>14.6f}")
    assert len(atoms) == len(species.atoms), (name, len(atoms))
    return atoms


def occupied_orbitals(output: str) -> list[tuple[int, float]]:
    """(index, energy in eV) of the occupied orbitals of the LAST orbital table, restricted jobs only (one table)."""
    block = output[output.rfind("ORBITAL ENERGIES"):]
    rows = re.findall(r"^\s*(\d+)\s+(2\.0000|1\.0000)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$", block, re.M)
    return [(int(i), float(ev)) for i, _occ, _eh, ev in rows]


def spin_down_non_aufbau(output: str) -> bool:
    """True when an unoccupied beta orbital lies below an occupied one at convergence: the state is not the aufbau one."""
    block = output[output.rfind("SPIN DOWN ORBITALS"):]
    rows = re.findall(r"^\s*(\d+)\s+(\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$", block, re.M)
    seen_empty = False
    for _i, occ, _eh, _ev in rows:
        if float(occ) == 0.0:
            seen_empty = True
        elif seen_empty:
            return True
    return False


def f_minus_distance(name: str, species: gate.GateSpecies, f_minus: list[float]) -> tuple[float, dict]:
    run_ = gate.MeasuredRun(
        molecule=name, level=species.level, symbols=species.atoms, f_plus=(), f_minus=tuple(f_minus), f_zero=(), dual=(), charge=species.charge, multiplicity=1, orca_version="6.1.1"
    )
    rows = gate.compare([e for e in gate.deproft_entries([name]) if e.attack == "f-"], {(name, species.level): run_}, gate.TOLERANCE)
    if not rows:
        return float("nan"), {}
    return max(abs(r.difference) for r in rows), {f"{r.element}": round(r.measured, 4) for r in rows}


def one(name: str) -> dict:
    species = gate.ALL_SPECIES[name]
    method = gate.METHOD_BASIS[species.level]
    atoms = optimized(name, species)
    body = "\n".join(atoms)
    grid = "%method\n  IntAcc 6.0\nend\n"
    pal = f"%pal nprocs {CORES} end\n"
    head = f"! {method}\n{pal}"
    neutral, work = run(f"{name}_N", f"{head}%scf\n  HFTyp RHF\nend\n{grid}%output\n  Print[P_Hirshfeld] 1\nend\n* xyz {species.charge} 1\n{body}\n*\n")
    n_energy = float(ENERGY.findall(neutral)[-1])
    n_table = [q for _e, q in parse_hirshfeld_tables(neutral)[0]]
    orbitals = occupied_orbitals(neutral)
    homo = orbitals[-1][0]
    result = {"species": name, "level": species.level, "n_energy": n_energy, "homo_index": homo, "occupied_top_ev": [round(ev, 3) for _i, ev in orbitals[-5:]], "states": []}
    gbw = str(work / "job.gbw").replace("\\", "/")
    lowest = None
    for k in HOLES:
        rotate = "" if k == 0 else f"%scf\n  Rotate {{{homo - k}, {homo}, 90, 1, 1}} end\nend\n"
        text = f"! {method} MORead\n{pal}%moinp \"{gbw}\"\n%scf\n  HFTyp UHF\nend\n{rotate}{grid}%output\n  Print[P_Hirshfeld] 1\nend\n* xyz {species.charge + 1} 2\n{body}\n*\n"
        out, _ = run(f"{name}_hole{k}", text)
        energies = ENERGY.findall(out)
        tables = parse_hirshfeld_tables(out)
        if not energies or not tables:
            result["states"].append({"hole": k, "converged": False})
            continue
        energy = float(energies[-1])
        f_minus = [c - n for n, c in zip(n_table, (q for _e, q in tables[-1]))]
        distance, labelled = f_minus_distance(name, species, f_minus)
        squares = S2.findall(out)
        state = {
            "hole": k, "converged": True, "energy": energy, "s2": float(squares[-1]) if squares else None, "non_aufbau": spin_down_non_aufbau(out),
            "f_minus": [round(v, 4) for v in f_minus], "max_distance_to_published": round(distance, 4), "by_label": labelled,
        }
        result["states"].append(state)
        lowest = energy if lowest is None else min(lowest, energy)
    for state in result["states"]:
        if state.get("converged"):
            state["above_lowest_ev"] = round((state["energy"] - lowest) * HARTREE_TO_EV, 3)
    print(json.dumps({k: v for k, v in result.items() if k != "states"}), flush=True)
    for state in result["states"]:
        print("   ", json.dumps(state), flush=True)
    return result


def main() -> None:
    out_path = Path(sys.argv[1])
    names = sys.argv[2:] or list(FAILED + CONTROLS)
    rows = [one(name) for name in names]
    out_path.write_text(json.dumps({"scratch": str(ROOT), "rows": rows}, indent=1), encoding="utf-8")
    print("\nSUMMARY: species, hole, energy above the lowest (eV), <S2>, non-aufbau, f- distance to the published numbers")
    for row in rows:
        print(row["species"], "occupied top (eV):", row["occupied_top_ev"])
        for state in row["states"]:
            if state.get("converged"):
                print(f"   hole {state['hole']}: +{state['above_lowest_ev']:.3f} eV  S2 {state['s2']}  non-aufbau {state['non_aufbau']}  max |f- - published| {state['max_distance_to_published']}")
            else:
                print(f"   hole {state['hole']}: did not converge")


if __name__ == "__main__":
    main()
