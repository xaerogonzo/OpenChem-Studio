"""Runs the Psi4 agreement check of `PLAN.md`, stage by stage, and writes the verdict.

    python run_agreement.py floor      --engine orca|psi4 [--workers 3] [--cores 4]    the floor runs (default and nuisance variants on the floor set)
    python run_agreement.py floor-report                                                 floor.json: the four floors and the tolerances
    python run_agreement.py grid       --engine orca|psi4                                the 240 single points
    python run_agreement.py optimize   --engine orca|psi4                                the 16 optimizations
    python run_agreement.py attribute                                                    Psi4 `scf_type pk` on every cell outside its tolerance (reported, decides nothing)
    python run_agreement.py report                                                       report.txt and verdict.json

Everything resumes: a job already recorded as completed is never run again. Records are `artifacts/<stage>/<engine>.jsonl`, one JSON line per attempt, each with the commit, whether `src/` was dirty, the engine's
version, the input's sha256 and the seconds. **The inputs are the ones the application writes** (`OrcaQuantumEngineProvider.build_input`, `Psi4QuantumEngineProvider.build_input`), run with each provider's own
`command_args`; the nuisance variants of the floor are text edits of those inputs, listed in `psi4_variant` and `orca_variant` and tested.

**A report is refused (NOT EVALUABLE) for records from more than one commit or from a dirty `src/`**, the guard the Fukui gates have: a verdict over two different engines is not a verdict.

Paths: ORCA is `D:\\ORCA\\orca.exe` and Psi4 is `OPENCHEM_PSI4_EXE` (the spike's `D:\\_scratch\\psi4-spike\\Scripts\\psi4.exe` when unset); `--out` moves the artifacts (the default is `artifacts/` beside this file).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import judge  # noqa: E402

from openchem.chem.orca_engine import OrcaQuantumEngineProvider, add_parallel_block  # noqa: E402
from openchem.chem.psi4_engine import Psi4QuantumEngineProvider  # noqa: E402

ORCA = r"D:\ORCA\orca.exe"
PSI4 = os.environ.get("OPENCHEM_PSI4_EXE", r"D:\_scratch\psi4-spike\Scripts\psi4.exe")
SEED = 7
TIMEOUT_SECONDS = 1800
LOCK = threading.Lock()

#: The 16 molecules of PLAN.md: name -> (SMILES, charge, multiplicity).
MOLECULES: dict[str, tuple[str, int, int]] = {
    "water": ("O", 0, 1), "methane": ("C", 0, 1), "chloromethane": ("CCl", 0, 1), "ethanol": ("CCO", 0, 1), "dimethyl ether": ("COC", 0, 1),
    "acetic acid": ("CC(=O)O", 0, 1), "methyl formate": ("COC=O", 0, 1), "acetone": ("CC(C)=O", 0, 1), "propanal": ("CCC=O", 0, 1),
    "benzene": ("c1ccccc1", 0, 1), "pyridine": ("c1ccncc1", 0, 1), "fluorobenzene": ("Fc1ccccc1", 0, 1), "thiophene": ("c1ccsc1", 0, 1),
    "dimethyl sulfoxide": ("CS(C)=O", 0, 1), "acetate": ("CC(=O)[O-]", -1, 1), "hydroxyl radical": ("[OH]", 0, 2),
}
#: The three isomer pairs.
PAIRS = [("ethanol", "dimethyl ether"), ("acetone", "propanal"), ("acetic acid", "methyl formate")]
#: The floor set and its three combinations.
FLOOR_MOLECULES = ["water", "ethanol", "acetic acid", "benzene", "pyridine", "dimethyl sulfoxide"]
FLOOR_COMBINATIONS = [("B3LYP", "def2-SVP"), ("PBE0", "def2-TZVP"), ("HF", "6-31G(d)")]
#: The 15 single-point combinations: 4 functionals x 3 bases, B3LYP at the two pcSseg bases, and B3LYP/G at def2-SVP.
GRID_COMBINATIONS = (
    [(f, b) for f in ("HF", "B3LYP", "PBE0", "M062X") for b in ("def2-SVP", "6-31G(d)", "def2-TZVP")]
    + [("B3LYP", "pcSseg-1"), ("B3LYP", "pcSseg-2"), ("B3LYP/G", "def2-SVP")]
)
OPT_COMBINATION = ("B3LYP", "def2-SVP")
#: Variants of a floor run: the engine's own input, and each setting that does not change the method.
ORCA_VARIANTS = ("default", "tight")
PSI4_VARIANTS = ("default", "pk", "grid", "one_thread")


# --- inputs ---------------------------------------------------------------------------------------------------------------


def molecule(name: str) -> Chem.Mol:
    """RDKit ETKDG (seed 7) plus MMFF, explicit hydrogens: the coordinates BOTH engines are given."""
    smiles = MOLECULES[name][0]
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=SEED)
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
    except Exception:  # noqa: BLE001 - a diatomic has no MMFF terms; the embedded geometry stands
        pass
    return mol


def orca_variant(text: str, variant: str, calc_type: str) -> str:
    """ORCA's input as the application writes it, with the nuisance variant's keywords appended to the `!` line (`tight`: TightSCF DefGrid3, and TightOpt for an optimization)."""
    if variant == "default":
        return text
    if variant == "tight":
        extra = " TightSCF DefGrid3" + (" TightOpt" if calc_type == "opt" else "")
        lines = text.split("\n")
        index = next(i for i, line in enumerate(lines) if line.startswith("!"))
        lines[index] = lines[index] + extra
        return "\n".join(lines)
    raise ValueError(f"unknown ORCA variant {variant!r}")


def psi4_variant(text: str, variant: str, calc_type: str) -> str:
    """Psi4's input as the engine writes it, with the nuisance variant's settings: `pk` (exact integrals instead of density fitting), `grid` (a finer DFT grid and tighter convergence), `one_thread` (the input is
    unchanged: the thread count is the command's), `tight_opt` is added for an optimization's tight variant."""
    if variant in ("default", "one_thread"):
        return text
    lines = text.rstrip("\n").split("\n")
    verb = lines.pop()  # the last line is the energy(...) / optimize(...) call
    if variant == "pk":
        lines = [("set scf_type pk" if line == "set scf_type df" else line) for line in lines]
    elif variant == "grid":
        lines = [line.replace("1e-8", "1e-10") for line in lines] + ["set dft_radial_points 99", "set dft_spherical_points 590"]
    elif variant == "tight":
        lines = lines + ["set g_convergence gau_tight"]
    else:
        raise ValueError(f"unknown Psi4 variant {variant!r}")
    return "\n".join([*lines, verb, ""])


def kabsch_rmsd(a: np.ndarray, b: np.ndarray) -> float:
    """The RMSD over all atoms after the best rigid-body alignment of `b` onto `a`, in the coordinates' unit."""
    a = a - a.mean(axis=0)
    b = b - b.mean(axis=0)
    u, _s, vt = np.linalg.svd(b.T @ a)
    d = np.sign(np.linalg.det(u @ vt))
    rotation = u @ np.diag([1.0, 1.0, d]) @ vt
    return float(np.sqrt(((b @ rotation - a) ** 2).sum() / len(a)))


# --- running --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Job:
    stage: str
    engine: str
    molecule: str
    functional: str
    basis: str
    variant: str
    calc_type: str  # "sp" or "opt"

    @property
    def key(self) -> str:
        return "|".join((self.stage, self.engine, self.molecule, self.functional, self.basis, self.variant, self.calc_type))


class Context:
    def __init__(self, out: Path, cores: int, workers: int) -> None:
        self.out, self.cores, self.workers = out, cores, workers
        out.mkdir(parents=True, exist_ok=True)
        self.commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
        self.dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src"], capture_output=True, text=True, cwd=REPO).stdout.strip())
        self.orca = OrcaQuantumEngineProvider()
        self.psi4 = Psi4QuantumEngineProvider(threads=lambda: cores)
        self.psi4_one = Psi4QuantumEngineProvider(threads=lambda: 1)

    def path(self, stage: str, engine: str) -> Path:
        return self.out / stage / f"{engine}.jsonl"

    def records(self, stage: str, engine: str) -> list[dict]:
        path = self.path(stage, engine)
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []

    def done(self, job: Job) -> bool:
        return any(r["key"] == job.key and r.get("completed") for r in self.records(job.stage, job.engine))

    def append(self, job: Job, record: dict) -> None:
        path = self.path(job.stage, job.engine)
        path.parent.mkdir(parents=True, exist_ok=True)
        with LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")


def run_job(ctx: Context, job: Job) -> dict | None:
    """One job through the engine's own provider; a record per attempt, a completed one never repeated."""
    if ctx.done(job):
        return None
    mol = molecule(job.molecule)
    _smiles, charge, multiplicity = MOLECULES[job.molecule]
    method_basis = f"{job.functional} {job.basis}"
    record: dict = {"key": job.key, "stage": job.stage, "engine": job.engine, "molecule": job.molecule, "functional": job.functional, "basis": job.basis,
                    "variant": job.variant, "calc_type": job.calc_type, "commit": ctx.commit, "dirty": ctx.dirty, "completed": False}
    began = time.time()
    scratch = Path(tempfile.mkdtemp(prefix=f"agree_{job.engine}_"))
    try:
        if job.engine == "orca":
            provider = ctx.orca
            text = orca_variant(provider.build_input(mol, charge, multiplicity, method_basis, job.calc_type), job.variant, job.calc_type)
            text = add_parallel_block(text, ctx.cores)
            (scratch / "job.inp").write_text(text, encoding="utf-8")
            args = provider.command_args(ORCA, scratch / "job.inp")
        else:
            provider = ctx.psi4_one if job.variant == "one_thread" else ctx.psi4
            text = psi4_variant(provider.build_input(mol, charge, multiplicity, method_basis, job.calc_type), job.variant, job.calc_type)
            (scratch / "job.inp").write_text(text, encoding="utf-8")
            args = provider.command_args(PSI4, scratch / "job.inp")
        record["input_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        completed = subprocess.run(args, cwd=scratch, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
        output = completed.stdout or ""
        version = re.search(r"Program Version\s+(\S+)", output) if job.engine == "orca" else re.search(r"Psi4 (\d+\.\d+(?:\.\d+)?) release", output)
        record["engine_version"] = version.group(1) if version else None
        descriptors, conformer = provider.parse_output(output, mol, "agreement", job.calc_type)
        record["energy_hartree"] = descriptors[0].value
        if job.calc_type == "opt":
            if conformer is None:
                raise RuntimeError("no optimized geometry was parsed")
            optimized = Chem.MolFromMolBlock(conformer.molblock, removeHs=False)
            record["coordinates"] = optimized.GetConformer().GetPositions().tolist()
        record["completed"] = True
    except subprocess.TimeoutExpired:
        record["error"] = f"timeout after {TIMEOUT_SECONDS} s"
    except Exception as error:  # noqa: BLE001 - a failed job is a missing cell, recorded with its reason
        record["error"] = f"{type(error).__name__}: {error}"[:400]
    finally:
        record["seconds"] = round(time.time() - began, 1)
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)
    ctx.append(job, record)
    return record


def run_all(ctx: Context, jobs: list[Job]) -> None:
    pending = [job for job in jobs if not ctx.done(job)]
    print(f"{len(jobs) - len(pending)} done, {len(pending)} to run", flush=True)

    def work(job: Job) -> None:
        record = run_job(ctx, job)
        if record is not None:
            print(f"{job.key}  completed={record['completed']}  {record['seconds']} s  {record.get('error', '')}", flush=True)

    with ThreadPoolExecutor(max_workers=ctx.workers) as pool:
        list(pool.map(work, pending))


# --- the job lists --------------------------------------------------------------------------------------------------------


def floor_jobs(engine: str) -> list[Job]:
    variants = ORCA_VARIANTS if engine == "orca" else PSI4_VARIANTS
    jobs = [Job("floor", engine, m, f, b, v, "sp") for m in FLOOR_MOLECULES for f, b in FLOOR_COMBINATIONS for v in variants]
    jobs += [Job("floor", engine, m, *OPT_COMBINATION, v, "opt") for m in FLOOR_MOLECULES for v in ("default", "tight")]
    return jobs


def grid_jobs(engine: str) -> list[Job]:
    return [Job("grid", engine, m, f, b, "default", "sp") for m in MOLECULES for f, b in GRID_COMBINATIONS]


def optimize_jobs(engine: str) -> list[Job]:
    return [Job("optimize", engine, m, *OPT_COMBINATION, "default", "opt") for m in MOLECULES]


# --- reading ---------------------------------------------------------------------------------------------------------------


def _completed(records: list[dict]) -> dict[str, dict]:
    return {r["key"]: r for r in records if r.get("completed")}


def floors_from(orca: list[dict], psi4: list[dict]) -> dict:
    """The four floors of PLAN.md from the floor records: the largest change a nuisance variant made, per class and engine (mEh), and for the optimizations the energy and RMSD floors (mEh, Angstrom)."""
    hf: list[float] = []
    dft: list[float] = []
    opt_energy: list[float] = []
    opt_rmsd: list[float] = []
    for engine, records, variants in (("orca", orca, ("tight",)), ("psi4", psi4, ("pk", "grid", "one_thread"))):
        done = _completed(records)
        for m in FLOOR_MOLECULES:
            for f, b in FLOOR_COMBINATIONS:
                base = done.get(Job("floor", engine, m, f, b, "default", "sp").key)
                for variant in variants:
                    other = done.get(Job("floor", engine, m, f, b, variant, "sp").key)
                    if base and other:
                        (hf if f == "HF" else dft).append((other["energy_hartree"] - base["energy_hartree"]) * judge.HARTREE_TO_MEH)
            base_o = done.get(Job("floor", engine, m, *OPT_COMBINATION, "default", "opt").key)
            tight_o = done.get(Job("floor", engine, m, *OPT_COMBINATION, "tight", "opt").key)
            if base_o and tight_o:
                opt_energy.append((tight_o["energy_hartree"] - base_o["energy_hartree"]) * judge.HARTREE_TO_MEH)
                opt_rmsd.append(kabsch_rmsd(np.array(base_o["coordinates"]), np.array(tight_o["coordinates"])))
    expected_sp = len(FLOOR_MOLECULES) * len(FLOOR_COMBINATIONS)
    return {
        "hf_meh": judge.floor(hf), "dft_meh": judge.floor(dft), "opt_energy_meh": judge.floor(opt_energy), "rmsd_angstrom": judge.floor(opt_rmsd),
        "measurements": {"hf": len(hf), "dft": len(dft), "opt": len(opt_energy), "expected_sp_per_variant": expected_sp},
    }


def single_point_records(orca: list[dict], psi4: list[dict]) -> list[dict]:
    o, p = _completed(orca), _completed(psi4)
    out = []
    for m in MOLECULES:
        for f, b in GRID_COMBINATIONS:
            ro, rp = o.get(Job("grid", "orca", m, f, b, "default", "sp").key), p.get(Job("grid", "psi4", m, f, b, "default", "sp").key)
            out.append({"molecule": m, "functional": f, "basis": b, "orca": ro["energy_hartree"] if ro else None, "psi4": rp["energy_hartree"] if rp else None})
    return out


def optimization_records(orca: list[dict], psi4: list[dict]) -> list[dict]:
    o, p = _completed(orca), _completed(psi4)
    out = []
    for m in MOLECULES:
        ro, rp = o.get(Job("optimize", "orca", m, *OPT_COMBINATION, "default", "opt").key), p.get(Job("optimize", "psi4", m, *OPT_COMBINATION, "default", "opt").key)
        both = ro is not None and rp is not None
        out.append({"molecule": m, "orca": ro["energy_hartree"] if ro else None, "psi4": rp["energy_hartree"] if rp else None,
                    "rmsd": kabsch_rmsd(np.array(ro["coordinates"]), np.array(rp["coordinates"])) if both else None})
    return out


def provenance_problem(*record_sets: list[dict]) -> str | None:
    """A reason the records cannot be judged: more than one commit, or a dirty `src/` at any run."""
    records = [r for rs in record_sets for r in rs]
    commits = {r["commit"] for r in records}
    if len(commits) > 1:
        return f"the records come from {len(commits)} commits: {sorted(c[:8] for c in commits)}"
    if any(r["dirty"] for r in records):
        return "some records were made with a dirty src/"
    return None


def tolerances_from(floor_file: dict) -> judge.Tolerances:
    return judge.tolerances(floor_file["hf_meh"], floor_file["dft_meh"], floor_file["opt_energy_meh"], floor_file["rmsd_angstrom"])


def report_lines(single_points: list[dict], optimizations: list[dict], tol: judge.Tolerances) -> list[str]:
    """The reported-and-in-no-rule part: the signed median per combination and the largest |d| per molecule."""
    lines = ["", "signed median d (Psi4 - ORCA, mEh) per combination:"]
    by_combination: dict[tuple[str, str], list[float]] = {}
    by_molecule: dict[str, list[float]] = {}
    for r in single_points:
        if r["orca"] is None or r["psi4"] is None:
            continue
        d = (r["psi4"] - r["orca"]) * judge.HARTREE_TO_MEH
        by_combination.setdefault((r["functional"], r["basis"]), []).append(d)
        by_molecule.setdefault(r["molecule"], []).append(d)
    for (f, b), ds in by_combination.items():
        lines.append(f"  {f:8s} {b:10s} median {median(ds):+8.3f}  range {min(ds):+8.3f} .. {max(ds):+8.3f}  (T = {tol.energy(f):.3f})")
    lines.append("largest |d| per molecule (mEh): " + ", ".join(f"{m} {max(abs(x) for x in ds):.3f}" for m, ds in by_molecule.items()))
    return lines


def restrict_to(names: set[str]) -> None:
    """A subset of the molecules, for a smoke test of the runner: a subset is never judged (the report would read the missing ones as missing cells)."""
    global MOLECULES, FLOOR_MOLECULES
    MOLECULES = {k: v for k, v in MOLECULES.items() if k in names}
    FLOOR_MOLECULES = [m for m in FLOOR_MOLECULES if m in names]


# --- the commands ----------------------------------------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["floor", "floor-report", "grid", "optimize", "attribute", "report"])
    parser.add_argument("--engine", choices=["orca", "psi4"])
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--out", default=str(HERE / "artifacts"))
    parser.add_argument("--molecules", nargs="*", help="a subset (smoke tests only; a subset is never judged)")
    args = parser.parse_args()
    ctx = Context(Path(args.out), args.cores, args.workers)
    if args.molecules:
        restrict_to(set(args.molecules))

    if args.command in ("floor", "grid", "optimize"):
        if args.engine is None:
            parser.error("--engine is required")
        builder = {"floor": floor_jobs, "grid": grid_jobs, "optimize": optimize_jobs}[args.command]
        run_all(ctx, builder(args.engine))
    elif args.command == "floor-report":
        floors = floors_from(ctx.records("floor", "orca"), ctx.records("floor", "psi4"))
        tol = tolerances_from(floors)
        floors["tolerances"] = {"hf_meh": tol.hf_meh, "dft_meh": tol.dft_meh, "opt_energy_meh": tol.opt_energy_meh, "geometry_angstrom": tol.geometry_angstrom}
        (ctx.out / "floor.json").write_text(json.dumps(floors, indent=1), encoding="utf-8")
        print(json.dumps(floors, indent=1))
    elif args.command == "attribute":
        floors = json.loads((ctx.out / "floor.json").read_text(encoding="utf-8"))
        tol = tolerances_from(floors)
        sp = single_point_records(ctx.records("grid", "orca"), ctx.records("grid", "psi4"))
        outside = [r for r in sp if r["orca"] is not None and r["psi4"] is not None and abs(r["psi4"] - r["orca"]) * judge.HARTREE_TO_MEH > tol.energy(r["functional"])]
        print(f"{len(outside)} cell(s) outside tolerance")
        run_all(ctx, [Job("attribute", "psi4", r["molecule"], r["functional"], r["basis"], "pk", "sp") for r in outside])
    elif args.command == "report":
        floors = json.loads((ctx.out / "floor.json").read_text(encoding="utf-8"))
        tol = tolerances_from(floors)
        grid_o, grid_p = ctx.records("grid", "orca"), ctx.records("grid", "psi4")
        opt_o, opt_p = ctx.records("optimize", "orca"), ctx.records("optimize", "psi4")
        problem = provenance_problem(grid_o, grid_p, opt_o, opt_p, ctx.records("floor", "orca"), ctx.records("floor", "psi4"))
        sp, op = single_point_records(grid_o, grid_p), optimization_records(opt_o, opt_p)
        if problem:
            verdict, why = judge.NOT_EVALUABLE, [problem]
        else:
            verdict, why = judge.judge(sp, op, PAIRS, tol)
        lines = [f"tolerances: T_HF {tol.hf_meh:.3f} mEh, T_DFT {tol.dft_meh:.3f} mEh, T_Eopt {tol.opt_energy_meh:.3f} mEh, T_geom {tol.geometry_angstrom:.4f} A",
                 f"floors: HF {floors['hf_meh']:.4f} mEh, DFT {floors['dft_meh']:.4f} mEh, opt energy {floors['opt_energy_meh']:.4f} mEh, RMSD {floors['rmsd_angstrom']:.5f} A", "", *why,
                 *report_lines(sp, op, tol)]
        attribution = _completed(ctx.records("attribute", "psi4"))
        if attribution:
            lines += ["", "attribution (Psi4 with scf_type pk on the cells outside tolerance; decides nothing): d with density fitting -> d with exact integrals (mEh)"]
            by_key = {(r["molecule"], r["functional"], r["basis"]): r for r in sp}
            for key, rec in sorted(attribution.items()):
                cell = by_key[(rec["molecule"], rec["functional"], rec["basis"])]
                if cell["orca"] is not None and cell["psi4"] is not None:
                    lines.append(f"  {rec['molecule']} {rec['functional']} {rec['basis']}: {(cell['psi4'] - cell['orca']) * 1000:+.3f} -> {(rec['energy_hartree'] - cell['orca']) * 1000:+.3f}")
        lines += ["", f"VERDICT {verdict}"]
        text = "\n".join(lines)
        print(text)
        (ctx.out / "report.txt").write_text(text, encoding="utf-8")
        (ctx.out / "verdict.json").write_text(json.dumps({"verdict": verdict, "why": why, "tolerances": floors.get("tolerances")}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
