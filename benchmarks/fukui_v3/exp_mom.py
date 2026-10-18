"""EXPLORATORY (decides nothing): does ORCA's DeltaSCF `IonizeBeta` (MOM-held hole) give cation states that are the same on two geometries of one molecule, where the Rotate starts relax to
the lowest state on one of them? Geometry = the first `* xyz` block of a pilot input.

    python exp_mom.py <pilot input> <label> [--cores 8] [--mode ionize|rotate]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

from openchem.chem.orca_engine import _S_SQUARED_RE, _SCF_ENERGY_RE, _TOTAL_CHARGE_RE, parse_hirshfeld_tables

ORCA = r"D:\ORCA\orca.exe"
H2EV = 27.211386245988


def coordinates(path: str) -> list[str]:
    text = Path(path).read_text()
    block = text.split("* xyz", 1)[1].split("\n", 1)[1].split("\n*", 1)[0]
    return [line for line in block.splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pilot_input")
    parser.add_argument("label")
    parser.add_argument("--cores", type=int, default=8)
    parser.add_argument("--mode", default="ionize")
    parser.add_argument("--homo", type=int, default=27)
    args = parser.parse_args()
    atoms = coordinates(args.pilot_input)
    head = "! B3LYP 6-31G*"
    grid = ["%method", "  IntAcc 6.0", "end", "%output", "  Print[P_Hirshfeld] 1", "end"]
    lines = [head, f"%pal nprocs {args.cores} end", "%scf", "  HFTyp RHF", "end", *grid, "* xyz 0 1", *atoms, "*"]
    labels = ["N"]
    for k in (0, 1, 2, 3):
        orbital = args.homo - k
        lines += ["", "$new_job"]
        if args.mode == "ionize":
            lines += [f"{head} UKS DeltaSCF MORead", '%moinp "job.gbw"', "%scf", f"  IonizeBeta {orbital}", "end", *grid, "* xyz 0 1", *atoms, "*"]
        else:
            lines += [f"{head} MORead", '%moinp "job.gbw"', "%scf", "  HFTyp UHF", f"  Rotate {{{orbital if k else args.homo}, {args.homo}, 90, 1, 1}} end" if k else "", "end", *grid, "* xyz 1 2", *atoms, "*"]
        labels.append(f"hole {k} (orbital {orbital})")
    work = Path(tempfile.mkdtemp(prefix=f"expmom_{args.label}_"))
    (work / "job.inp").write_text("\n".join(lines) + "\n")
    out = subprocess.run([ORCA, "job.inp"], capture_output=True, text=True, cwd=work).stdout
    (work / "job.out").write_text(out)
    starts = [m.start() for m in _TOTAL_CHARGE_RE.finditer(out)]
    segments = [out[a:b] for a, b in zip(starts, [*starts[1:], len(out)])]
    print(f"{args.label} ({args.mode}): {len(segments)} job echoes, scratch {work}")
    rows = []
    for label, segment in zip(labels, segments):
        energies = _SCF_ENERGY_RE.findall(segment)
        tables = parse_hirshfeld_tables(segment)
        squares = _S_SQUARED_RE.findall(segment)
        charge = re.search(r"Total Charge\s+Charge\s+\.\.\.\.\s+(-?\d+)", segment).group(1)
        rows.append((label, float(energies[-1]) if energies else None, [q for _e, q in tables[-1]] if tables else None, squares[-1] if squares else "", charge))
    neutral = rows[0][2]
    cation = [r for r in rows[1:] if r[1] is not None]
    lowest = min(r[1] for r in cation) if cation else None
    for label, energy, charges, s2, charge in rows:
        if energy is None:
            print(f"  {label}: NO ENERGY")
            continue
        extra = ""
        if label != "N" and neutral and charges:
            diffs = [c - n for n, c in zip(neutral, charges)]
            extra = f"+{(energy - lowest) * H2EV:6.3f} eV  S2={s2}  charge={charge}  f-(O)={diffs[0]:.3f} f-(C1)={diffs[1]:.3f} f-(sum)={sum(diffs):.3f}"
        print(f"  {label:26s} E={energy:.7f}  {extra}")
    if "ERROR" in out:
        print("--- ERROR lines:")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l or "Error" in l)[:600])


if __name__ == "__main__":
    main()
