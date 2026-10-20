"""EXPLORATORY mechanics check for a Fukui v3 cation-state search (decides nothing, nothing shipped): can ONE compound ORCA input hold the neutral, the default cation job and
several cation jobs that each START FROM THE NEUTRAL'S ORBITALS with the hole forced into HOMO-k?

    python proto_holes.py <smiles> <name> [--cores 8] [--holes 1 2 3] [--method "B3LYP 6-31G*"]

The geometry here is RDKit ETKDG + MMFF, only so there is a geometry: this checks that the input converges, which guess each job reports and what each job's energy is. It says nothing about
which state a molecule's published numbers belong to.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
import time
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.orca_engine import _GUESS_RE, _S_SQUARED_RE, _SCF_ENERGY_RE, _TOTAL_CHARGE_RE, parse_hirshfeld_tables

ORCA = r"D:\ORCA\orca.exe"
HARTREE_TO_EV = 27.211386245988


def geometry(smiles: str) -> tuple[list[str], int]:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
    conf = mol.GetConformer()
    lines = [f"{a.GetSymbol():<3}{conf.GetAtomPosition(a.GetIdx()).x:>14.6f}{conf.GetAtomPosition(a.GetIdx()).y:>14.6f}{conf.GetAtomPosition(a.GetIdx()).z:>14.6f}" for a in mol.GetAtoms()]
    return lines, sum(a.GetAtomicNum() for a in mol.GetAtoms())


def job(header: str, hfty: str, charge: int, mult: int, atoms: list[str], extra: list[str] | None = None, guess_file: str | None = None) -> list[str]:
    out = [header + (" MORead" if guess_file else "")]
    if guess_file:
        out.append(f'%moinp "{guess_file}"')
    out += ["%scf", f"  HFTyp {hfty}", *(extra or []), "end", "%method", "  IntAcc 6.0", "end", "%output", "  Print[P_Hirshfeld] 1", "end", f"* xyz {charge} {mult}", *atoms, "*"]
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("smiles")
    parser.add_argument("name")
    parser.add_argument("--cores", type=int, default=8)
    parser.add_argument("--holes", type=int, nargs="*", default=[1, 2, 3])
    parser.add_argument("--method", default="B3LYP 6-31G*")
    args = parser.parse_args()

    atoms, electrons = geometry(args.smiles)
    homo = electrons // 2 - 1
    header = f"! {args.method}"
    lines: list[str] = []
    lines += job(header, "RHF", 0, 1, atoms)
    lines += ["", "$new_job"] + job(header, "UHF", 1, 2, atoms)
    labels = ["N", "N-1 default"]
    for k in args.holes:
        lines += ["", "$new_job"] + job(header, "UHF", 1, 2, atoms, extra=[f"  Rotate {{{homo - k}, {homo}, 90, 1, 1}} end"], guess_file="job.gbw")
        labels.append(f"N-1 hole HOMO-{k} (orbitals {homo - k},{homo})")
    text = "\n".join(lines) + "\n"
    text = text.replace(header + "\n", header + f"\n%pal nprocs {args.cores} end\n", 1)

    work = Path(tempfile.mkdtemp(prefix=f"proto_{args.name}_"))
    (work / "job.inp").write_text(text)
    began = time.time()
    done = subprocess.run([ORCA, "job.inp"], capture_output=True, text=True, cwd=work)
    seconds = time.time() - began
    out = done.stdout
    (work / "job.out").write_text(out)
    print(f"{args.name}: {len(atoms)} atoms, {electrons} electrons, HOMO index {homo}, exit {done.returncode}, {seconds:.0f} s, scratch {work}")
    print("files:", sorted(p.name for p in work.glob("*.gbw")))

    starts = [m.start() for m in _TOTAL_CHARGE_RE.finditer(out)]
    segments = [out[a:b] for a, b in zip(starts, [*starts[1:], len(out)])]
    print(f"{len(segments)} job echoes")
    rows = []
    for label, segment in zip(labels, segments):
        energies = _SCF_ENERGY_RE.findall(segment)
        tables = parse_hirshfeld_tables(segment)
        squares = _S_SQUARED_RE.findall(segment)
        guess = _GUESS_RE.search(segment)
        read_from = re.search(r"Guess MOs are being read from file:\s*([^\r\n]+)", segment)
        rows.append((label, float(energies[-1]) if energies else None, [q for _e, q in tables[-1]] if tables else None, float(squares[-1]) if squares else None,
                     guess.group(1).strip() if guess else "?", read_from.group(1).strip() if read_from else ""))
    cation = [r for r in rows[1:] if r[1] is not None]
    lowest = min(r[1] for r in cation) if cation else None
    neutral = rows[0][2]
    for label, energy, charges, s2, guess, read_from in rows:
        if energy is None:
            print(f"  {label}: NO ENERGY (did not finish)")
            continue
        above = f"+{(energy - lowest) * HARTREE_TO_EV:6.3f} eV" if (lowest is not None and not label.startswith("N ") and label != "N") else "        "
        fminus = ""
        if neutral and charges and label != "N":
            diffs = [n - c for n, c in zip(neutral, charges)]
            heavy = max(range(len(diffs)), key=lambda i: abs(diffs[i]))
            fminus = f"  f- max {diffs[heavy]:.3f} at atom {heavy}"
        print(f"  {label:34s} E={energy:.8f} {above}  S2={s2}  guess={guess} {read_from}{fminus}")
    if "ERROR" in out or done.returncode != 0:
        print("--- tail of output ---")
        print("\n".join(out.splitlines()[-25:]))


if __name__ == "__main__":
    main()
