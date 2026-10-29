"""The 0 K to 298 K step of Arm D's S-H references (`PREREGISTRATION.md` section 7, item 3 of section 10), computed instead of borrowed.

THE QUESTION. The gas-phase acidity route gives D0(RS-H) (`references.json`). The preregistered quantity is DH298, and the step between them is
    D298 - D0 = [H298 - H0](RS.) + [H298 - H0](H.) - [H298 - H0](RSH)
where [H298 - H0] is the thermal enthalpy WITHOUT the zero-point energy (the acidity cycle already works at 0 K). The hydrogen atom is translation only, 5/2 RT = 6.197 kJ/mol. Ervin 2015 computed the step for ethanethiol only (+5.2 kJ/mol, D0 359.5 -> D298 364.7);
the propanethiols had no published step, and the draft borrowed 5.2.

THE METHOD. Harmonic oscillator, rigid rotor, at a level that has NO spurious imaginary mode on a thiyl radical (B3LYP; M06-2X's analytic Hessian does, `benchmarks/thiyl_probe/`): every kept conformer of the thiol (the benchmark's own conformer pool) is optimised with frequencies, and its
radical starts from that conformer with the S-H hydrogen removed. The step is taken from the LOWEST-enthalpy conformer of each species, as the benchmark does, and the spread over the conformer pairs is reported as the uncertainty of the borrowing. ETHANETHIOL IS THE CHECK: if this
method does not reproduce Ervin's +5.2 kJ/mol for the ethyl case, it is not trusted for the propyl cases.

THE STEP IS A PROPERTY OF THE REFERENCE, not of the calculation under test: it converts a published 0 K bond energy to 298 K and nothing else.

    python thermal_step.py run  [--out DIR] [--route "! B3LYP def2-TZVPD TightSCF Opt Freq"] [--workers 3]
    python thermal_step.py report [--out DIR]

The ORCA output text is parsed by `thermal_from_output` (pure, tested in `tests/test_restart_v3_thermal_step.py` against the committed excerpt in `tests/fixtures/orca/`).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

#: kJ/mol per hartree, and the gas constant in kJ/(mol K)
KJ_PER_EH = 2625.4996394799
R_KJ = 8.314462618e-3
T = 298.15
#: the hydrogen atom's thermal enthalpy (translation, 3/2 RT, plus the PV = RT of an ideal gas): no electronic, rotational or vibrational part
H_ATOM_KJ = 2.5 * R_KJ * T
DEFAULT_ROUTE = "! B3LYP def2-TZVPD TightSCF Opt Freq"
BONDS = [("ethanethiol", "CCS", 2), ("1-propanethiol", "CCCS", 3), ("2-propanethiol", "CC(C)S", 3), ("thiophenol", "Sc1ccccc1", 0)]


def thermal_from_output(text: str) -> dict:
    """What the step needs from one ORCA frequency job: the electronic energy, the zero-point energy and the total enthalpy (hartree, as ORCA prints them in its thermochemistry block), the lowest vibrational frequency and the thermal enthalpy WITHOUT zero point,
    `h_thermal_kj` = (total enthalpy - electronic energy - zero-point energy) in kJ/mol. Raises ValueError naming what is missing, so a job that did not finish is never a number."""
    if "ORCA TERMINATED NORMALLY" not in text:
        raise ValueError("the job did not terminate normally")
    found = {}
    for key, pattern in (("electronic", r"Electronic energy\s+\.\.\.\s+(-?\d+\.\d+) Eh"), ("zpe", r"Zero point energy\s+\.\.\.\s+(-?\d+\.\d+) Eh"), ("enthalpy", r"Total [Ee]nthalpy\s+\.\.\.\s+(-?\d+\.\d+) Eh")):
        matches = re.findall(pattern, text)
        if not matches:
            raise ValueError(f"no {key} value in the thermochemistry block")
        found[key] = float(matches[-1])
    block = text.split("VIBRATIONAL FREQUENCIES")[-1].split("NORMAL MODES")[0]
    freqs = [float(f) for f in re.findall(r"^\s*\d+:\s+(-?\d+\.\d+) cm\*\*-1", block, re.M)]
    nonzero = [f for f in freqs if abs(f) > 1e-6]
    symbols, coordinates = [], []
    start = text.rfind("CARTESIAN COORDINATES (ANGSTROEM)")
    if start >= 0:
        for line in text[start:].splitlines()[2:]:
            m = re.match(r"^\s*([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$", line)
            if not m:
                break
            symbols.append(m.group(1))
            coordinates.append([float(m.group(2)), float(m.group(3)), float(m.group(4))])
    return {**found, "h_thermal_kj": (found["enthalpy"] - found["electronic"] - found["zpe"]) * KJ_PER_EH, "lowest_frequency": min(nonzero) if nonzero else None, "n_frequencies": len(nonzero), "symbols": symbols, "coordinates": coordinates}


def step_kj(radical_h_thermal_kj: float, parent_h_thermal_kj: float) -> float:
    """D298 - D0 of the bond: the radical's and the hydrogen atom's thermal enthalpies minus the parent's."""
    return radical_h_thermal_kj + H_ATOM_KJ - parent_h_thermal_kj


def usable(job: dict) -> bool:
    """The benchmark's own acceptance of a species: no frequency below -20 cm-1 and the skeleton kept (a record without the field is taken as kept, for hand-built inputs)."""
    return (job["lowest_frequency"] is None or job["lowest_frequency"] >= -20.0) and job.get("skeleton_kept", True)


def summarise(species: list[dict]) -> dict:
    """For one thiol: `species` has one entry per conformer with `parent` and `radical` outputs already parsed (`h_thermal_kj`, `electronic`, `zpe`, `enthalpy`).
    Returns the step from the usable conformers of lowest total enthalpy (the benchmark's rule: a structure with an imaginary mode or a changed skeleton is not a minimum of the species and is not used), the spread of the step over every usable
    parent/radical pair, and the `rejected` jobs with the reason, so that nothing is dropped silently. Raises ValueError if no parent or no radical is usable."""
    parents = [s["parent"] for s in species if usable(s["parent"])]
    radicals = [s["radical"] for s in species if usable(s["radical"])]
    if not parents or not radicals:
        raise ValueError("no usable parent or no usable radical")
    parent = min(parents, key=lambda j: j["enthalpy"])
    radical = min(radicals, key=lambda j: j["enthalpy"])
    pairs = [step_kj(r["h_thermal_kj"], p["h_thermal_kj"]) for r in radicals for p in parents]
    rejected = [{"role": role, "lowest_frequency": s[role]["lowest_frequency"], "skeleton_kept": s[role].get("skeleton_kept", True)} for s in species for role in ("parent", "radical") if not usable(s[role])]
    return {"step_kj": step_kj(radical["h_thermal_kj"], parent["h_thermal_kj"]), "spread_kj": max(pairs) - min(pairs), "pairs_kj": pairs, "rejected": rejected}


# --- the ORCA side ---------------------------------------------------------------------------------------------------------------------


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def structures() -> list[dict]:  # noqa: D401
    """Per thiol, per kept conformer: the parent and its radical start, as the restart runner builds them."""
    bde = _load("bde_run_for_thermal", REPO / "benchmarks" / "bde" / "run_bde.py")
    out = []
    for name, smiles, atom in BONDS:
        mol = bde.parent_molecule(smiles)
        symbols = [a.GetSymbol() for a in mol.GetAtoms()]
        neighbors = [n.GetIdx() for n in mol.GetAtomWithIdx(atom).GetNeighbors()]
        for k, xyz in enumerate(bde.pa.conformers_of(mol)):
            radical_symbols, radical_xyz = bde.core.radical_start(symbols, xyz, atom, neighbors)
            out.append({"name": name, "conformer": k, "role": "parent", "smiles": smiles, "mult": 1, "symbols": symbols, "coordinates": xyz.tolist()})
            out.append({"name": name, "conformer": k, "role": "radical", "smiles": smiles, "atom": atom, "bond": name, "mult": 2, "symbols": radical_symbols, "coordinates": radical_xyz.tolist()})
    return out


def run_job(structure: dict, route: str, cores: int, orca: str, bde=None) -> dict:
    lines = [route, f"%pal nprocs {cores} end", "%maxcore 3000", f"* xyz 0 {structure['mult']}"]
    lines += [f"{s:<3}{x:>14.8f}{y:>14.8f}{z:>14.8f}" for s, (x, y, z) in zip(structure["symbols"], structure["coordinates"])] + ["*", ""]
    scratch = Path(tempfile.mkdtemp(prefix="thermal_"))
    began = time.time()
    try:
        (scratch / "job.inp").write_text("\n".join(lines), encoding="utf-8")
        record = {k: structure[k] for k in ("name", "conformer", "role")} | {"route": route}
        try:
            done = subprocess.run([orca, "job.inp"], cwd=scratch, capture_output=True, text=True, timeout=6 * 3600, check=False)
        except subprocess.TimeoutExpired:
            return record | {"error": "timeout after 21600 s", "seconds": round(time.time() - began, 1)}
        record["seconds"] = round(time.time() - began, 1)
        try:
            parsed = thermal_from_output(done.stdout)
            record.update({k: v for k, v in parsed.items()})
            if bde is not None:
                record["skeleton_kept"] = bool(bde.same_skeleton(structure, parsed))
        except ValueError as error:
            record["error"] = str(error)
        return record
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def read_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def report(records: list[dict]) -> tuple[str, dict]:
    lines, result = [], {}
    for name, _, _ in BONDS:
        species = []
        for conformer in sorted({r["conformer"] for r in records if r["name"] == name}):
            pair = {r["role"]: r for r in records if r["name"] == name and r["conformer"] == conformer and "error" not in r}
            if len(pair) == 2:
                species.append({"parent": pair["parent"], "radical": pair["radical"]})
        if not species:
            lines.append(f"{name:16s} no finished conformer pair")
            continue
        try:
            s = summarise(species)
        except ValueError as error:
            lines.append(f"{name:16s} {error}")
            continue
        result[name] = s
        flag = f"  REJECTED (not minima of the species): {s['rejected']}" if s["rejected"] else ""
        lines.append(f"{name:16s} step {s['step_kj']:.2f} kJ/mol (lowest-enthalpy usable conformers), spread over {len(s['pairs_kj'])} usable pairs {s['spread_kj']:.2f}{flag}")
    return "\n".join(lines), result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["run", "report"])
    parser.add_argument("--out", default=str(HERE / "artifacts" / "thermal_step"))
    parser.add_argument("--route", default=DEFAULT_ROUTE)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--cores", type=int, default=4)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "records.jsonl"
    if args.command == "run":
        done = {(r["name"], r["conformer"], r["role"]) for r in read_records(path) if "error" not in r and r["route"] == args.route}
        todo = [s for s in structures() if (s["name"], s["conformer"], s["role"]) not in done]
        print(f"{len(done)} done, {len(todo)} to run", flush=True)
        bde = _load("bde_for_orca", REPO / "benchmarks" / "bde" / "run_bde.py")
        orca = str(Path(bde.ORCA))

        def work(s: dict) -> None:
            record = run_job(s, args.route, args.cores, orca, bde)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
            print(s["name"], s["conformer"], s["role"], record.get("error", f"{record['h_thermal_kj']:.2f} kJ/mol thermal, {record['seconds']} s"), flush=True)

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(work, todo))
    else:
        text, result = report([r for r in read_records(path) if r["route"] == args.route])
        print(text)
        (out / "summary.json").write_text(json.dumps({"route": args.route, "H_atom_kj": H_ATOM_KJ, "species": result}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
