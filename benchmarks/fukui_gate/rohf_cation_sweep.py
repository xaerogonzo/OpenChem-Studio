"""POST-GATE SWEEP 2 (not the gate, decides nothing, changes nothing shipped): does a restricted open-shell (ROHF) CATION agree with the published
numbers better or worse than the application's unrestricted one, for every gate species at HF/6-31G**? (The anions are not spin-contaminated and stay unrestricted.)

The geometry of each species is the ORCA-optimized one the grid sweep (`grid_sweep.py`) already wrote; the neutral state and the unrestricted ions are
that sweep's default-grid job, unchanged. New here: the cation and the anion as ROHF doublets (`! ROHF 6-31G**`), at the same geometry, standalone
ORCA in fresh directories. Compared through `openchem.app.fukui_gate.compare` at the gate's tolerance, undecided.

    python rohf_cation_sweep.py <grid_sweep scratch directory> [output.json]
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
ROOT = Path(tempfile.mkdtemp(prefix="fukui_rohf_sweep_"))
LEVEL = gate.HF_B
COORDS = re.compile(r"^\s*([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")
S2 = re.compile(r"Expectation value of <S\*\*2>\s*:\s*(-?\d+\.\d+)")
MAP = {"CO": "CO", "CO2": "CO2", "H2CO": "H2CO", "acetone": "acetone", "CN-": "CN_", "NCO-": "NCO_", "CNO-": "CNO_"}


def geometry(name: str) -> list[str]:
    out = (SWEEP / f"{MAP[name]}_HF_6_31G_" / "opt" / "job.out").read_text(errors="replace")
    block = out[out.rfind("CARTESIAN COORDINATES (ANGSTROEM)"):]
    atoms = []
    for line in block.splitlines()[2:]:
        match = COORDS.match(line)
        if not match:
            break
        atoms.append(f"{match.group(1):<3}{float(match.group(2)):>14.6f}{float(match.group(3)):>14.6f}{float(match.group(4)):>14.6f}")
    return atoms


def orca(work: Path, text: str) -> str:
    work.mkdir(parents=True, exist_ok=True)
    (work / "job.inp").write_text(text)
    out = subprocess.run([ORCA, str(work / "job.inp")], capture_output=True, text=True, cwd=work).stdout
    (work / "job.out").write_text(out)
    return out


def table(out: str) -> list[float]:
    return [charge for _element, charge in parse_hirshfeld_tables(out)[-1]]


def one(name: str) -> dict:
    species = gate.SPECIES[name]
    atoms = geometry(name)
    body = "\n".join(atoms)
    # the unrestricted ions and the neutral: the grid sweep's own default-grid compound job, read back
    first = (SWEEP / f"{MAP[name]}_HF_6_31G_" / "default" / "job.out").read_text(errors="replace")
    neutral, cation_u, anion_u = ([charge for _e, charge in t] for t in parse_hirshfeld_tables(first))
    symbols = tuple(element for element, _charge in parse_hirshfeld_tables(first)[0])
    result = {"species": name, "symbols": symbols}
    runs = {}
    for label, ion in (("cation", species.charge + 1),):
        out = orca(ROOT / name / label, f"! ROHF 6-31G**\n%output\n  Print[P_Hirshfeld] 1\nend\n* xyz {ion} 2\n{body}\n*\n")
        runs[label] = table(out)
        squares = S2.findall(out)
        result[f"{label}_s_squared_rohf"] = float(squares[-1]) if squares else None
    for kind, cation, anion in (("uhf", cation_u, anion_u), ("rohf", runs["cation"], anion_u)):
        f_plus = tuple(n - a for n, a in zip(neutral, anion))
        f_minus = tuple(c - n for n, c in zip(neutral, cation))
        result[kind] = gate.MeasuredRun(name, LEVEL, symbols, f_plus, f_minus, tuple((p + m) / 2 for p, m in zip(f_plus, f_minus)),
                                        tuple(p - m for p, m in zip(f_plus, f_minus)), species.charge, 1, "6.1.1")
    print(name, "done", flush=True)
    return result


def main() -> None:
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, gate.SPECIES))
    entries = [e for e in gate.decided_entries() if e.level == LEVEL]
    report = {"scratch": str(ROOT), "per_species": []}
    for kind in ("uhf", "rohf"):
        runs = {(r["species"], LEVEL): r[kind] for r in results}
        rows = gate.compare(entries, runs, gate.TOLERANCE, decided=False)
        print(f"\n{kind.upper()} ions: {sum(1 for r in rows if r.within)} of {len(rows)} published numbers within {gate.TOLERANCE}")
        for r in sorted(rows, key=lambda x: -abs(x.difference))[:8]:
            print(f"  {r.source:13s} {r.molecule:8s} {r.element:2s} {r.attack}  published {r.published:.4f} measured {r.measured:.4f} diff {r.difference:+.4f}")
        for name in gate.SPECIES:
            mine = [r for r in rows if r.molecule == name and r.source == "olah2002"]
            report["per_species"].append({"kind": kind, "species": name, "max_abs_diff": round(max(abs(r.difference) for r in mine), 4) if mine else None})
    for r in results:
        print(f"{r['species']:8s} ROHF cation <S2>: {r['cation_s_squared_rohf']}")
    Path(sys.argv[2] if len(sys.argv) > 2 else "rohf_sweep.json").write_text(json.dumps(report, indent=1))
    print("\nlargest |diff| per species (Olah, HF/6-31G**):")
    for kind in ("uhf", "rohf"):
        print(kind, {e["species"]: e["max_abs_diff"] for e in report["per_species"] if e["kind"] == kind})


if __name__ == "__main__":
    main()
