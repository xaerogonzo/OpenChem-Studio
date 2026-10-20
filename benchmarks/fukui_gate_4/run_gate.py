"""Runs the fourth Fukui gate (`PREREGISTRATION.md`) with real ORCA, through the application's own input builder and parse, and judges it with `openchem.app.fukui_gate_4`.

    python run_gate.py run          for every decided species: the ORCA optimisation of its geometry, the exhaustive search (holes down to the HOMO-7) with every N-1 state's spin read, and the
                                    application's own run (the default job and holes in the HOMO-1, -2 and -3) on the same geometry
    python run_gate.py run --calibration --out DIR    the same for the four species seen before the gate, to check the reading (PREREGISTRATION.md 3); never judged
    python run_gate.py judge        reads the records and writes verdict.json
    python run_gate.py report       prints each species' states against what the sources print

Options: ``--out DIR`` (default `artifacts/` beside this file), ``--cores 4`` per ORCA job, ``--workers 4`` species at once, ``--species NAME`` to run one.

The geometry of a species is the ORCA B3LYP/6-31G* optimisation of an RDKit ETKDG + MMFF embedding (seed 7), as the third gate's, rotated so that the plane of the molecule is the xy plane (the spin
reading needs it). The exhaustive input is the application's own with the holes it is given here; the application's run is `OrcaQuantumEngineProvider.build_input` itself, the cation search ON. **A job
that did not finish may be repeated unchanged up to `MAX_ATTEMPTS` times; a job that completed is never repeated.** The records are JSON lines in `runs.jsonl`, one per attempt, carrying the commit,
whether `src/` differed from it, the ORCA version and the sha256 of the input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Geometry import Point3D

from openchem.app import fukui_gate_4 as gate
from openchem.chem.fukui_plan import has_diffuse_functions, searchable_holes
from openchem.chem.orca_engine import _CALC_TYPE_KEYWORDS, _TOTAL_CHARGE_RE, OrcaOutputError, OrcaQuantumEngineProvider, add_parallel_block

ORCA = r"D:\ORCA\orca.exe"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SEED = 7
#: The embedding seeds an optimisation is tried from, in order, until one converges (the first is the third gate's).
OPTIMIZATION_SEEDS = (7, 8, 9)
COORDS = re.compile(r"^\s*([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")
LOCK = threading.Lock()


class Context:
    def __init__(self, out: Path, cores: int, workers: int) -> None:
        self.out, self.cores, self.workers = out, cores, workers
        out.mkdir(parents=True, exist_ok=True)
        self.scratch = Path(tempfile.mkdtemp(prefix="fukui_gate4_"))
        self.runs_path = out / "runs.jsonl"
        self.geometries_path = out / "geometries.json"
        self.commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
        self.dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src"], capture_output=True, text=True, cwd=REPO).stdout.strip())
        self.provider = OrcaQuantumEngineProvider(cation_search=lambda: True)
        self._geometries: dict[str, list[list[float]]] = json.loads(self.geometries_path.read_text()) if self.geometries_path.exists() else {}

    def records(self) -> list[dict]:
        if not self.runs_path.exists():
            return []
        return [json.loads(line) for line in self.runs_path.read_text().splitlines() if line.strip()]

    def append(self, record: dict) -> None:
        with LOCK:
            with self.runs_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")

    def completed(self, species: str, kind: str) -> dict | None:
        return next((r for r in self.records() if (r["species"], r["kind"]) == (species, kind) and r["completed"]), None)

    def attempts(self, species: str, kind: str) -> int:
        return sum(1 for r in self.records() if (r["species"], r["kind"]) == (species, kind))

    def store_geometry(self, key: str, xyz: list[list[float]]) -> None:
        with LOCK:
            self._geometries[key] = xyz
            self.geometries_path.write_text(json.dumps(self._geometries, indent=1))

    def geometry(self, key: str) -> np.ndarray | None:
        return np.array(self._geometries[key]) if key in self._geometries else None


def orca(ctx: Context, name: str, text: str, cores: int | None = None) -> tuple[str, int, float]:
    work = ctx.scratch / re.sub(r"\W+", "_", name)
    work.mkdir(parents=True, exist_ok=True)
    (work / "job.inp").write_text(add_parallel_block(text, cores or ctx.cores))
    began = time.time()
    done = subprocess.run([ORCA, "job.inp"], capture_output=True, text=True, cwd=work)
    (work / "job.out").write_text(done.stdout)
    return done.stdout, done.returncode, time.time() - began


def embed(smiles: str, seed: int) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)  # a molecule MMFF has no parameters for (selenium) is left as embedded: ORCA does the optimisation
    return mol


def lines_of(mol: Chem.Mol) -> list[str]:
    conf = mol.GetConformer()
    return [f"{a.GetSymbol():<3}{conf.GetAtomPosition(a.GetIdx()).x:>14.6f}{conf.GetAtomPosition(a.GetIdx()).y:>14.6f}{conf.GetAtomPosition(a.GetIdx()).z:>14.6f}" for a in mol.GetAtoms()]


def optimized(ctx: Context, species: gate.GateSpecies) -> np.ndarray:
    """The ORCA optimisation of an RDKit ETKDG + MMFF embedding (the third gate's recipe), cached under the species' name."""
    key = f"{species.name}_reference"
    cached = ctx.geometry(key)
    if cached is not None:
        return cached
    # An optimisation that does not converge is repeated from the next embedding seed (PREREGISTRATION.md 9); the seed that gave the geometry is stored beside it.
    for seed in OPTIMIZATION_SEEDS:
        mol = embed(species.smiles, seed)
        out, _code, _seconds = orca(ctx, f"{key}_opt{seed}", f"! {species.method_basis} Opt\n* xyz {species.charge} 1\n" + "\n".join(lines_of(mol)) + "\n*\n")
        if "THE OPTIMIZATION HAS CONVERGED" not in out:
            print(f"the optimization of {key} from seed {seed} did not converge", flush=True)
            continue
        block = out[out.rfind("CARTESIAN COORDINATES (ANGSTROEM)"):]
        atoms = []
        for line in block.splitlines()[2:]:
            match = COORDS.match(line)
            if not match:
                break
            atoms.append([float(match.group(2)), float(match.group(3)), float(match.group(4))])
        if len(atoms) != mol.GetNumAtoms():
            raise RuntimeError(f"the optimization of {key} printed {len(atoms)} atoms, not {mol.GetNumAtoms()}")
        ctx.store_geometry(key, atoms)
        ctx.store_geometry(f"{key}_seed", [[float(seed)]])
        return np.array(atoms)
    raise RuntimeError(f"the optimization of {key} did not converge from seeds {OPTIMIZATION_SEEDS}")


def oriented(xyz: np.ndarray) -> np.ndarray:
    """The coordinates centred and rotated so that the plane of a planar molecule is xy (the direction of least spread is z)."""
    centred = xyz - xyz.mean(axis=0)
    _values, vectors = np.linalg.eigh(np.cov(centred.T))
    basis = vectors[:, ::-1].copy()
    if np.linalg.det(basis) < 0:
        basis[:, 2] *= -1
    return centred @ basis


def with_coordinates(mol: Chem.Mol, xyz: np.ndarray) -> Chem.Mol:
    clone = Chem.Mol(mol)
    conf = clone.GetConformer()
    for index, (x, y, z) in enumerate(xyz):
        conf.SetAtomPosition(index, Point3D(float(x), float(y), float(z)))
    return clone


def base_record(ctx: Context, kind: str, species: gate.GateSpecies, attempt: int, text: str, out: str, code: int, seconds: float) -> dict:
    return {
        "kind": kind, "species": species.name, "attempt": attempt, "commit": ctx.commit, "dirty": ctx.dirty, "seconds": round(seconds, 1), "orca_exit": code,
        "input_sha256": hashlib.sha256(add_parallel_block(text, ctx.cores).encode()).hexdigest(), "method_basis": species.method_basis, "charge": species.charge,
        "orca_version": (re.search(r"Program Version\s+(\S+)", out) or [None, None])[1],
    }


def exhaustive_run(ctx: Context, species: gate.GateSpecies, mol: Chem.Mol) -> dict:
    """The exhaustive search on the oriented geometry, and every N-1 job's energy and spin."""
    done = ctx.completed(species.name, "E")
    if done is not None:
        return done
    attempt = ctx.attempts(species.name, "E") + 1
    atomic_numbers = [a.GetAtomicNum() for a in mol.GetAtoms()]
    search = searchable_holes(atomic_numbers, species.charge, offsets=gate.EXHAUSTIVE_OFFSETS)
    header = f"! {species.method_basis} {_CALC_TYPE_KEYWORDS['fukui']}".strip()
    text = ctx.provider._build_fukui_input(header, lines_of(mol), species.charge, 1, diffuse=has_diffuse_functions(species.method_basis), holes=search.offsets, homo=search.homo)
    out, code, seconds = orca(ctx, f"{species.name}_E_{attempt}", text)
    record = base_record(ctx, "E", species, attempt, text, out, code, seconds)
    symbols = [a.GetSymbol().upper() for a in mol.GetAtoms()]
    z = np.array([mol.GetConformer().GetAtomPosition(i).z for i in range(mol.GetNumAtoms())])
    record["planarity"] = float(np.abs(z - z.mean()).max())
    record["hetero_index"] = next((i for i, s in enumerate(symbols) if s == species.hetero.upper()), None) if species.hetero else None
    record["planned_holes"] = list(search.offsets)
    try:
        results = ctx.provider._fukui_job_results(out, symbols)
    except OrcaOutputError as error:
        record.update({"completed": False, "error": str(error)})
        ctx.append(record)
        return record
    starts = [m.start() for m in _TOTAL_CHARGE_RE.finditer(out)]
    segments = [out[a:b] for a, b in zip(starts, [*starts[1:], len(out)])]
    # every planned job must have finished: the neutral, the default cation, the cation holes and the N+1 state
    expected_jobs = 3 + len(search.offsets)
    jobs = []
    for index, result in enumerate(results):
        if result.state != "N-1" or result.energy_hartree is None:
            continue
        spins = gate.parse_lowdin_spin(segments[index], len(symbols))
        if spins is None:
            continue
        jobs.append({
            "position": index + 1, "start": str(result.start), "energy_hartree": result.energy_hartree, "s_squared": result.s_squared,
            "out_of_plane": gate.out_of_plane_fraction(spins), "atom_spin": [sum(atom.values()) for atom in spins],
        })
    finished = sum(1 for r in results if r.energy_hartree is not None)
    completed = code == 0 and finished == expected_jobs and len(jobs) == 1 + len(search.offsets)
    record.update({"completed": completed, "jobs": jobs, "symbols": symbols, "jobs_finished": finished, "jobs_expected": expected_jobs})
    if not completed:
        record["error"] = f"{finished} of {expected_jobs} jobs finished, exit {code}"
    ctx.append(record)
    return record


def application_run(ctx: Context, species: gate.GateSpecies, mol: Chem.Mol) -> dict:
    """The application's own run: `build_input` and `_condensed_fukui`, as the Quantum Chemistry panel does."""
    done = ctx.completed(species.name, "A")
    if done is not None:
        return done
    attempt = ctx.attempts(species.name, "A") + 1
    text = ctx.provider.build_input(mol, species.charge, 1, species.method_basis, "fukui")
    out, code, seconds = orca(ctx, f"{species.name}_A_{attempt}", text)
    record = base_record(ctx, "A", species, attempt, text, out, code, seconds)
    try:
        result = ctx.provider._condensed_fukui(out, mol)
    except OrcaOutputError as error:
        record.update({"completed": False, "error": str(error)})
        ctx.append(record)
        return record
    reading = result.cation_reading
    record.update({
        "completed": reading is not None, "lowest_hartree": reading.energy_hartree if reading else None, "note": result.cation_note or "",
        "competing_ev": [round(s.above_ev, 4) for s in reading.competing] if reading else [], "degenerate": bool(reading and reading.degenerate),
        "f_minus": list(result.f_minus),
    })
    ctx.append(record)
    return record


def with_attempts(function, *args):
    for _ in range(gate.MAX_ATTEMPTS):
        record = function(*args)
        if record["completed"]:
            return record
    return record


def run_species(ctx: Context, species: gate.GateSpecies) -> None:
    base = optimized(ctx, species)
    print(f"optimized {species.name}", flush=True)
    mol = with_coordinates(embed(species.smiles, SEED), oriented(base))
    record = with_attempts(exhaustive_run, ctx, species, mol)
    print(f"E {species.name:12s} completed={record['completed']} {record['seconds']} s", flush=True)
    record = with_attempts(application_run, ctx, species, mol)
    print(f"A {species.name:12s} completed={record['completed']} {record['seconds']} s", flush=True)


def judged(ctx: Context) -> dict:
    records = [r for r in ctx.records() if r["species"] in {s.name for s in gate.GATE_SPECIES}]
    final = {}
    for r in records:  # the last attempt of each (species, kind), a completed one in preference
        key = (r["species"], r["kind"])
        if key not in final or r["completed"] or not final[key]["completed"]:
            final[key] = r
    exhaustive = [r for (name, kind), r in final.items() if kind == "E"]
    application = [r for (name, kind), r in final.items() if kind == "A"]
    verdict = gate.judge(exhaustive=exhaustive, application=application, runs=records)
    document = {
        "outcome": verdict.outcome, "reasons": list(verdict.reasons), "arms": dict(verdict.arms),
        "rows": [{"species": row.species, "claim": row.claim, "expected": row.expected, "found": row.found, "holds": row.holds} for row in verdict.rows],
    }
    (ctx.out / "verdict.json").write_text(json.dumps(document, indent=1))
    return document


def report(ctx: Context, calibration: bool = False) -> None:
    for species in gate.CALIBRATION if calibration else gate.GATE_SPECIES:
        record = ctx.completed(species.name, "E")
        reference = species.reference
        print(f"\n{species.name}: " + (f"the sources print a gap of {reference.gap_ev[0]:.2f} to {reference.gap_ev[1]:.2f} eV; lowest {reference.lowest}, second {reference.second}" if reference else "seen before the gate"))
        application = ctx.completed(species.name, "A")
        if record is not None and application is not None and application.get("lowest_hartree") is not None:
            lowest = min(job["energy_hartree"] for job in record["jobs"])
            print(f"  the application's lowest state is {(application['lowest_hartree'] - lowest) * gate.HARTREE_TO_EV:+.4f} eV from the exhaustive search's; its note: {application['note'] or '(none)'}")
        if record is None:
            print("  no completed exhaustive record")
            continue
        index = record.get("hetero_index")
        for state in gate.states_of(record["jobs"]):
            extra = f"  spin on {species.hetero} {state.atom_spin[index]:+.3f} ({gate.hetero_class(state.atom_spin[index])})" if index is not None else ""
            print(f"  +{state.above_ev:6.3f} eV  {state.kind or 'unclassified':10s} out of plane {state.out_of_plane:6.3f}  {state.jobs} job(s){extra}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["run", "judge", "report"])
    parser.add_argument("--out", type=Path, default=HERE / "artifacts")
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--species")
    parser.add_argument("--calibration", action="store_true", help="run the CALIBRATION species (seen before the gate) instead of the decided ones; use with --out so the records stay apart")
    args = parser.parse_args()
    ctx = Context(args.out, args.cores, args.workers)
    if args.command == "run":
        chosen = [s for s in (gate.CALIBRATION if args.calibration else gate.GATE_SPECIES) if args.species in (None, s.name)]
        with ThreadPoolExecutor(max_workers=ctx.workers) as pool:
            list(pool.map(lambda s: run_species(ctx, s), chosen))
    elif args.command == "judge":
        document = judged(ctx)
        print(json.dumps({k: document[k] for k in ("outcome", "reasons", "arms")}, indent=1))
        for row in document["rows"]:
            print(f"  {'ok  ' if row['holds'] else 'MISS'} {row['species']:12s} {row['claim']:3s} expected {row['expected']} | found {row['found']}")
    else:
        report(ctx, args.calibration)


if __name__ == "__main__":
    main()
