"""Runs the xtb comparison of `PREREGISTRATION.md`, stage by stage, and writes the verdicts.

    python run_comparison.py list                         every stage's job count (runs nothing)
    python run_comparison.py floor      [--workers 2] [--cores 4]    the optimizer floors: ORCA default/tight `Opt`, xtb tight/vtight/one-thread/repeat, on the floor set
    python run_comparison.py geometry   ...               arm G: ORCA, xtb (and Psi4 on set S) optimizations from the MMFF start of sets S and M
    python run_comparison.py conformers ...               set F: ORCA and xtb optimizations from each conformer's MMFF start
    python run_comparison.py reference  ...               arm R: B3LYP-D3BJ def2-TZVP and GFN2 single points at the ORCA structures
    python run_comparison.py preopt     ...               arm P: ORCA `Opt` started from the xtb structure
    python run_comparison.py gfn1       ...               the GFN1-xTB aside (reported, in no rule)
    python run_comparison.py report                       report.txt and verdict.json

Everything resumes: a job already recorded as completed is never run again. Records are `artifacts/<stage>/<engine>.jsonl`, one JSON line per attempt, each with the commit, whether `src/` was dirty, the engine's version,
the input's sha256 and the seconds. **The inputs are the ones the application writes** (`OrcaQuantumEngineProvider`, `Psi4QuantumEngineProvider`, `XtbQuantumEngineProvider` `.build_input`), run with each provider's
own `command_args`.

**A report is refused (NOT EVALUABLE) for records from more than one commit or from a dirty `src/`**, the guard the Psi4 and Fukui checks have.

Paths: ORCA is `D:\\ORCA\\orca.exe`, Psi4 is `OPENCHEM_PSI4_EXE` (the spike's `D:\\_scratch\\psi4-spike\\Scripts\\psi4.exe` when unset) and xtb is `OPENCHEM_XTB_EXE` (`D:\\_scratch\\xtb-6.7.1\\bin\\xtb.exe` when unset);
`--out` moves the artifacts (the default is `artifacts/` beside this file).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
from itertools import combinations
from pathlib import Path
from statistics import median

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _load_judge():
    """This folder's `judge.py` under a name of its own: `benchmarks/` holds several files called `judge.py`, and a bare `import judge` returns whichever was imported first (the Psi4 runner's lesson)."""
    name = "xtb_comparison_judge"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, HERE / "judge.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


judge = _load_judge()

from openchem.chem.orca_engine import OrcaQuantumEngineProvider, add_parallel_block  # noqa: E402
from openchem.chem.psi4_engine import Psi4QuantumEngineProvider  # noqa: E402
from openchem.chem.xtb_engine import XtbQuantumEngineProvider  # noqa: E402

ORCA = r"D:\ORCA\orca.exe"
PSI4 = os.environ.get("OPENCHEM_PSI4_EXE", r"D:\_scratch\psi4-spike\Scripts\psi4.exe")
XTB = os.environ.get("OPENCHEM_XTB_EXE", r"D:\_scratch\xtb-6.7.1\bin\xtb.exe")
SEED = 7
#: A job that takes longer is a missing cell (section 3 of the preregistration).
TIMEOUT_SECONDS = 3600
LOCK = threading.Lock()

#: The primary reference level and the energy reference level (decisions D1 and D2).
PRIMARY = "B3LYP def2-SVP"
ENERGY_REFERENCE = "B3LYP def2-TZVP D3BJ"
XTB_METHOD = "GFN2-xTB"
GFN1_METHOD = "GFN1-xTB"
#: Two optimized structures are the same conformer when their heavy-atom RMSD is at most this (Angstrom, section 4).
SAME_MINIMUM_RMSD = 0.3

#: Set S: the Psi4 agreement set, name -> (SMILES, charge, multiplicity).
SET_S: dict[str, tuple[str, int, int]] = {
    "water": ("O", 0, 1), "methane": ("C", 0, 1), "chloromethane": ("CCl", 0, 1), "ethanol": ("CCO", 0, 1), "dimethyl ether": ("COC", 0, 1),
    "acetic acid": ("CC(=O)O", 0, 1), "methyl formate": ("COC=O", 0, 1), "acetone": ("CC(C)=O", 0, 1), "propanal": ("CCC=O", 0, 1),
    "benzene": ("c1ccccc1", 0, 1), "pyridine": ("c1ccncc1", 0, 1), "fluorobenzene": ("Fc1ccccc1", 0, 1), "thiophene": ("c1ccsc1", 0, 1),
    "dimethyl sulfoxide": ("CS(C)=O", 0, 1), "acetate": ("CC(=O)[O-]", -1, 1), "hydroxyl radical": ("[OH]", 0, 2),
}
#: Reported, not judged (one each cannot support a rule).
REPORTED_ONLY = ("acetate", "hydroxyl radical")
#: Set M: molecules a user draws.
SET_M: dict[str, tuple[str, int, int]] = {
    "aspirin": ("CC(=O)Oc1ccccc1C(=O)O", 0, 1), "paracetamol": ("CC(=O)Nc1ccc(O)cc1", 0, 1), "nicotinamide": ("NC(=O)c1cccnc1", 0, 1),
    "caffeine": ("Cn1cnc2c1c(=O)n(C)c(=O)n2C", 0, 1), "2-phenylethanol": ("OCCc1ccccc1", 0, 1), "ethyl acetate": ("CCOC(C)=O", 0, 1),
}
#: Set F: flexible molecules, for conformer energies.
SET_F: dict[str, str] = {
    "1,2-ethanediol": "OCCO", "glycine": "NCC(=O)O", "1,2-dimethoxyethane": "COCCOC", "ethyl acetate": "CCOC(C)=O", "N-methylacetamide": "CC(=O)NC",
}
#: The conformers of set F: embeddings, the pruning RMSD (ALL atoms, hydrogens included, Angstrom: a hydroxyl or carboxylic hydrogen turned the other way is a conformer) and how many are kept.
CONFORMER_EMBEDDINGS = 300
CONFORMER_PRUNE_RMSD = 0.3
CONFORMERS_KEPT = 6
#: The three isomer pairs of set S.
PAIRS = [("ethanol", "dimethyl ether"), ("acetone", "propanal"), ("acetic acid", "methyl formate")]
#: The floor set (section 6).
FLOOR_MOLECULES = ["water", "ethanol", "acetic acid", "benzene", "pyridine", "dimethyl sulfoxide"]
JUDGED = [name for name in SET_S if name not in REPORTED_ONLY] + list(SET_M)
ALL_STRUCTURES = {**SET_S, **SET_M}
PAIR_MOLECULES = sorted({name for pair in PAIRS for name in pair})


# --- inputs ---------------------------------------------------------------------------------------------------------------


def molecule(name: str) -> Chem.Mol:
    """RDKit ETKDG (seed 7) plus MMFF, explicit hydrogens: the coordinates every engine is given (set S and set M)."""
    smiles = ALL_STRUCTURES[name][0]
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=SEED)
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
    except Exception:  # noqa: BLE001 - a diatomic has no MMFF terms; the embedded geometry stands
        pass
    return mol


def conformer_mols(name: str) -> list[Chem.Mol]:
    """The conformers of one set-F molecule, by the rule of section 3: 300 ETKDG embeddings (seed 7), MMFF-optimized, taken in MMFF-energy order, each kept only if its all-atom RMSD to every one already kept is at
    least 0.3 A (symmetry-aware), the first 6 kept. Each comes back as its own molecule with one conformer, so the same list is rebuilt for every stage."""
    mol = Chem.AddHs(Chem.MolFromSmiles(SET_F[name]))
    ids = list(AllChem.EmbedMultipleConfs(mol, numConfs=CONFORMER_EMBEDDINGS, randomSeed=SEED))
    results = AllChem.MMFFOptimizeMoleculeConfs(mol, maxIters=2000)
    ordered = sorted(zip(ids, (energy for _converged, energy in results)), key=lambda pair: (pair[1], pair[0]))
    reference = Chem.Mol(mol)
    kept: list[int] = []
    for cid, _energy in ordered:
        if all(rdMolAlign.GetBestRMS(Chem.Mol(reference), Chem.Mol(reference), prbId=cid, refId=other) >= CONFORMER_PRUNE_RMSD for other in kept):
            kept.append(cid)
        if len(kept) == CONFORMERS_KEPT:
            break
    out = []
    for cid in kept:
        single = Chem.Mol(mol)
        single.RemoveAllConformers()
        single.AddConformer(Chem.Conformer(mol.GetConformer(cid)), assignId=True)
        out.append(single)
    return out


def with_coordinates(mol: Chem.Mol, coordinates: list[list[float]]) -> Chem.Mol:
    """A copy of `mol` with its atoms placed at `coordinates` (same atom order, the way every provider returns an optimized structure)."""
    out = Chem.Mol(mol)
    conf = out.GetConformer()
    if len(coordinates) != out.GetNumAtoms():
        raise ValueError(f"{len(coordinates)} coordinates for {out.GetNumAtoms()} atoms")
    for index, (x, y, z) in enumerate(coordinates):
        conf.SetAtomPosition(index, (float(x), float(y), float(z)))
    return out


def kabsch_rmsd(a: np.ndarray, b: np.ndarray) -> float:
    """The RMSD after the best rigid-body alignment of `b` onto `a`, in the coordinates' unit. Same atom order (the structures share a start); no symmetry permutation."""
    a = a - a.mean(axis=0)
    b = b - b.mean(axis=0)
    u, _s, vt = np.linalg.svd(b.T @ a)
    d = np.sign(np.linalg.det(u @ vt))
    rotation = u @ np.diag([1.0, 1.0, d]) @ vt
    return float(np.sqrt(((b @ rotation - a) ** 2).sum() / len(a)))


def heavy_rmsd(mol: Chem.Mol, a: list[list[float]], b: list[list[float]]) -> float:
    """The RMSD over the heavy atoms of `mol` between two structures of it, after rigid-body alignment (Angstrom)."""
    heavy = [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetAtomicNum() > 1]
    return kabsch_rmsd(np.array(a)[heavy], np.array(b)[heavy])


def bond_mad(mol: Chem.Mol, a: list[list[float]], b: list[list[float]]) -> float:
    """The mean absolute difference of the molecule's own bond lengths between two structures of it (Angstrom)."""
    pa, pb = np.array(a), np.array(b)
    return float(np.mean([abs(np.linalg.norm(pa[x.GetBeginAtomIdx()] - pa[x.GetEndAtomIdx()]) - np.linalg.norm(pb[x.GetBeginAtomIdx()] - pb[x.GetEndAtomIdx()])) for x in mol.GetBonds()]))


# --- jobs -----------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Job:
    """One calculation. `structure` is a molecule name ("aspirin") or, for set F, "<molecule>#<conformer index>". `start` says where the coordinates come from: `mmff` (the molecule's own start) or
    `orca` / `xtb` (the optimized structure of that engine, read from the records of the stage that made it)."""

    stage: str
    engine: str
    structure: str
    method: str
    calc_type: str  # "sp" or "opt"
    start: str = "mmff"
    variant: str = "default"

    @property
    def key(self) -> str:
        return "|".join((self.stage, self.engine, self.structure, self.method, self.calc_type, self.start, self.variant))


def split_structure(structure: str) -> tuple[str, int | None]:
    name, _, index = structure.partition("#")
    return name, (int(index) if index else None)


def charge_spin(structure: str) -> tuple[int, int]:
    name, _ = split_structure(structure)
    if name in ALL_STRUCTURES:
        return ALL_STRUCTURES[name][1], ALL_STRUCTURES[name][2]
    return 0, 1  # set F: neutral closed shells


def start_mol(structure: str) -> Chem.Mol:
    name, index = split_structure(structure)
    return molecule(name) if index is None else conformer_mols(name)[index]


def orca_variant(text: str, variant: str, calc_type: str) -> str:
    """ORCA's input as the application writes it; `tight` appends `TightOpt` to the `!` line of an optimization (section 6: the default `Opt` against `TightOpt`)."""
    if variant == "default":
        return text
    if variant == "tight" and calc_type == "opt":
        lines = text.split("\n")
        index = next(i for i, line in enumerate(lines) if line.startswith("!"))
        lines[index] += " TightOpt"
        return "\n".join(lines)
    raise ValueError(f"unknown ORCA variant {variant!r} for {calc_type!r}")


def xtb_args(args: list[str], variant: str) -> list[str]:
    """The xtb command, with a floor variant applied: `vtight` swaps the optimization level `tight` for `vtight`; the others (`default`, `one_thread`, `repeat`) leave the command unchanged
    (`one_thread` is the provider's thread count, `repeat` a second identical run for determinism)."""
    if variant == "vtight":
        out = list(args)
        out[out.index("--opt" if "--opt" in out else "--ohess") + 1] = "vtight"
        return out
    if variant in ("default", "one_thread", "repeat"):
        return list(args)
    raise ValueError(f"unknown xtb variant {variant!r}")


def optimization_cycles(output: str) -> int | None:
    """How many cycles ORCA's optimization took: the highest `GEOMETRY OPTIMIZATION CYCLE n` it printed (None when it printed none)."""
    cycles = [int(n) for n in re.findall(r"GEOMETRY OPTIMIZATION CYCLE\s+(\d+)", output)]
    return max(cycles) if cycles else None


class Context:
    def __init__(self, out: Path, cores: int, workers: int) -> None:
        self.out, self.cores, self.workers = out, cores, workers
        self.commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
        self.dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src"], capture_output=True, text=True, cwd=REPO).stdout.strip())
        self.orca = OrcaQuantumEngineProvider()
        self.psi4 = Psi4QuantumEngineProvider(threads=lambda: cores)
        self.xtb = XtbQuantumEngineProvider(threads=lambda: cores)
        self.xtb_one = XtbQuantumEngineProvider(threads=lambda: 1)

    def path(self, stage: str, engine: str) -> Path:
        return self.out / stage / f"{engine}.jsonl"

    def records(self, stage: str, engine: str) -> list[dict]:
        path = self.path(stage, engine)
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []

    def completed(self, stage: str, engine: str) -> dict[str, dict]:
        return {r["key"]: r for r in self.records(stage, engine) if r.get("completed")}

    def done(self, job: Job) -> bool:
        return job.key in self.completed(job.stage, job.engine)

    def append(self, job: Job, record: dict) -> None:
        path = self.path(job.stage, job.engine)
        path.parent.mkdir(parents=True, exist_ok=True)
        with LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def coordinates(self, stage: str, engine: str, structure: str) -> list[list[float]] | None:
        """The optimized structure of `structure` that `engine` produced in `stage` (default variant), or None when that job is missing."""
        for record in self.completed(stage, engine).values():
            if record["structure"] == structure and record["variant"] == "default" and record["calc_type"] == "opt" and record["start"] == "mmff":
                return record["coordinates"]
        return None


def start_coordinates(ctx: Context, job: Job) -> Chem.Mol | None:
    """The molecule a job starts from, or None when the stage that makes its start has not produced it."""
    mol = start_mol(job.structure)
    if job.start == "mmff":
        return mol
    stage = "conformers" if split_structure(job.structure)[1] is not None else "geometry"
    coordinates = ctx.coordinates(stage, job.start, job.structure)
    return with_coordinates(mol, coordinates) if coordinates is not None else None


def run_job(ctx: Context, job: Job) -> dict | None:
    """One job through the engine's own provider; a record per attempt, a completed one never repeated."""
    if ctx.done(job):
        return None
    charge, multiplicity = charge_spin(job.structure)
    record: dict = {"key": job.key, "stage": job.stage, "engine": job.engine, "structure": job.structure, "method": job.method, "calc_type": job.calc_type, "start": job.start,
                    "variant": job.variant, "commit": ctx.commit, "dirty": ctx.dirty, "completed": False}
    began = time.time()
    scratch = Path(tempfile.mkdtemp(prefix=f"xtbcmp_{job.engine}_"))
    try:
        mol = start_coordinates(ctx, job)
        if mol is None:
            raise RuntimeError(f"the {job.start} structure this job starts from is missing")
        if job.engine == "orca":
            provider = ctx.orca
            text = orca_variant(provider.build_input(mol, charge, multiplicity, job.method, job.calc_type), job.variant, job.calc_type)
            text = add_parallel_block(text, ctx.cores)
            (scratch / "job.inp").write_text(text, encoding="utf-8")
            args = provider.command_args(ORCA, scratch / "job.inp")
        elif job.engine == "psi4":
            provider = ctx.psi4
            text = provider.build_input(mol, charge, multiplicity, job.method, job.calc_type)
            (scratch / "job.inp").write_text(text, encoding="utf-8")
            args = provider.command_args(PSI4, scratch / "job.inp")
        else:
            provider = ctx.xtb_one if job.variant == "one_thread" else ctx.xtb
            text = provider.build_input(mol, charge, multiplicity, job.method, job.calc_type)
            (scratch / "job.inp").write_text(text, encoding="utf-8")
            args = xtb_args(provider.command_args(XTB, scratch / "job.inp"), job.variant)
        record["input_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        completed = subprocess.run(args, cwd=scratch, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS)
        output = completed.stdout or ""
        if job.engine == "orca":
            version = re.search(r"Program Version\s+(\S+)", output)
            record["cycles"] = optimization_cycles(output) if job.calc_type == "opt" else None
        elif job.engine == "psi4":
            version = re.search(r"Psi4 (\d+\.\d+(?:\.\d+)?) release", output)
        else:
            version = re.search(r"xtb version (\S+)", output)
        record["engine_version"] = version.group(1) if version else None
        descriptors, conformer = provider.parse_output(output, mol, "xtb-comparison", job.calc_type)
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


# --- the job lists (the stages of the preregistration) ----------------------------------------------------------------------


def conformer_structures() -> list[str]:
    return [f"{name}#{i}" for name in SET_F for i in range(len(conformer_mols(name)))]


def floor_jobs() -> list[Job]:
    jobs = [Job("floor", "orca", m, PRIMARY, "opt", variant=v) for m in FLOOR_MOLECULES for v in ("default", "tight")]
    jobs += [Job("floor", "xtb", m, XTB_METHOD, "opt", variant=v) for m in FLOOR_MOLECULES for v in ("default", "vtight", "one_thread", "repeat")]
    return jobs


def geometry_jobs() -> list[Job]:
    jobs = [Job("geometry", "orca", m, PRIMARY, "opt") for m in ALL_STRUCTURES]
    jobs += [Job("geometry", "xtb", m, XTB_METHOD, "opt") for m in ALL_STRUCTURES]
    jobs += [Job("geometry", "psi4", m, PRIMARY, "opt") for m in SET_S]
    return jobs


def conformer_jobs() -> list[Job]:
    structures = conformer_structures()
    return [Job("conformers", "orca", s, PRIMARY, "opt") for s in structures] + [Job("conformers", "xtb", s, XTB_METHOD, "opt") for s in structures]


def reference_jobs() -> list[Job]:
    """The single points at the ORCA structures: the dispersion-corrected reference energy, and GFN2's own energy at the same structure (the fixed-geometry decomposition)."""
    structures = PAIR_MOLECULES + conformer_structures()
    jobs = [Job("reference", "orca", s, ENERGY_REFERENCE, "sp", start="orca") for s in structures]
    jobs += [Job("reference", "xtb", s, XTB_METHOD, "sp", start="orca") for s in structures]
    return jobs


def preopt_jobs() -> list[Job]:
    return [Job("preopt", "orca", m, PRIMARY, "opt", start="xtb") for m in ALL_STRUCTURES]


def gfn1_jobs() -> list[Job]:
    return [Job("gfn1", "xtb", m, GFN1_METHOD, "opt") for m in JUDGED]


STAGES = {"floor": floor_jobs, "geometry": geometry_jobs, "conformers": conformer_jobs, "reference": reference_jobs, "preopt": preopt_jobs, "gfn1": gfn1_jobs}


# --- reading ---------------------------------------------------------------------------------------------------------------


def _find(done: dict[str, dict], structure: str, variant: str = "default", start: str = "mmff", method: str | None = None) -> dict | None:
    for record in done.values():
        if record["structure"] == structure and record["variant"] == variant and record["start"] == start and (method is None or record["method"] == method):
            return record
    return None


def floors_from(ctx: Context) -> tuple[object, dict]:
    """The ORCA optimizer floor for the judge, and the xtb floors (reported): the largest change a harmless setting made, in mEh and Angstrom."""
    orca = ctx.completed("floor", "orca")
    energy, rmsd = [], []
    for m in FLOOR_MOLECULES:
        base, tight = _find(orca, m), _find(orca, m, "tight")
        if base and tight:
            energy.append((tight["energy_hartree"] - base["energy_hartree"]) * judge.HARTREE_TO_MEH)
            rmsd.append(kabsch_rmsd(np.array(base["coordinates"]), np.array(tight["coordinates"])))
    floors = judge.Floors(judge.floor(energy), judge.floor(rmsd))
    xtb = ctx.completed("floor", "xtb")
    reported: dict = {}
    for variant in ("vtight", "one_thread", "repeat"):
        e, r = [], []
        for m in FLOOR_MOLECULES:
            base, other = _find(xtb, m), _find(xtb, m, variant)
            if base and other:
                e.append((other["energy_hartree"] - base["energy_hartree"]) * judge.HARTREE_TO_MEH)
                r.append(kabsch_rmsd(np.array(base["coordinates"]), np.array(other["coordinates"])))
        reported[f"xtb_{variant}"] = {"energy_meh": judge.floor(e) if e else None, "rmsd_angstrom": judge.floor(r) if r else None, "molecules": len(e)}
    reported["orca_molecules"] = len(energy)
    return floors, reported


def geometry_rows(ctx: Context, stage: str = "geometry", method: str = XTB_METHOD) -> list[dict]:
    """C1's rows for the judged molecules (an xtb structure against the ORCA one). A molecule missing either structure is a row with `None`, which the judge counts as a missing cell."""
    orca, xtb = ctx.completed("geometry", "orca"), ctx.completed(stage, "xtb")
    rows = []
    for name in JUDGED:
        o, x = _find(orca, name, method=PRIMARY), _find(xtb, name, method=method)
        if o is None or x is None:
            rows.append({"molecule": name, "heavy_rmsd": None, "bond_mad": None})
        else:
            mol = molecule(name)
            rows.append({"molecule": name, "heavy_rmsd": heavy_rmsd(mol, x["coordinates"], o["coordinates"]), "bond_mad": bond_mad(mol, x["coordinates"], o["coordinates"])})
    return rows


def reported_aside(ctx: Context) -> dict:
    """What section 7 reports and no rule reads: GFN1-xTB against GFN2-xTB (structure against ORCA), the anion and the radical, and the ORCA-to-Psi4 spread of the reference itself on set S."""
    out: dict = {}
    gfn1 = [r["heavy_rmsd"] for r in geometry_rows(ctx, "gfn1", GFN1_METHOD) if r["heavy_rmsd"] is not None]
    gfn2 = [r["heavy_rmsd"] for r in geometry_rows(ctx) if r["heavy_rmsd"] is not None]
    out["median_heavy_rmsd_gfn1"] = median(gfn1) if gfn1 else None
    out["median_heavy_rmsd_gfn2"] = median(gfn2) if gfn2 else None
    orca, xtb, psi4 = ctx.completed("geometry", "orca"), ctx.completed("geometry", "xtb"), ctx.completed("geometry", "psi4")
    stressed = {}
    for name in REPORTED_ONLY:
        o, x, p = _find(orca, name), _find(xtb, name), _find(psi4, name)
        mol = molecule(name)
        stressed[name] = {
            "xtb_vs_orca_heavy_rmsd": heavy_rmsd(mol, x["coordinates"], o["coordinates"]) if o and x else None,
            "psi4_vs_orca_heavy_rmsd": heavy_rmsd(mol, p["coordinates"], o["coordinates"]) if o and p else None,
        }
    out["reported_only"] = stressed
    spread, pair_spread = [], []
    for name in SET_S:
        o, p = _find(orca, name), _find(psi4, name)
        if o and p and name not in REPORTED_ONLY:
            spread.append(heavy_rmsd(molecule(name), p["coordinates"], o["coordinates"]))
    for a, b in PAIRS:
        oa, ob, pa, pb = _find(orca, a), _find(orca, b), _find(psi4, a), _find(psi4, b)
        if oa and ob and pa and pb:
            pair_spread.append(abs(((pa["energy_hartree"] - pb["energy_hartree"]) - (oa["energy_hartree"] - ob["energy_hartree"])) * judge.HARTREE_TO_KCAL))
    out["psi4_vs_orca_heavy_rmsd_max"] = max(spread) if spread else None
    out["psi4_vs_orca_isomer_pair_difference_kcal_max"] = max(pair_spread) if pair_spread else None
    return out


def relative_pairs(ctx: Context) -> dict:
    """C2's pairs, end to end: GFN2's energy at the xtb structure against the dispersion-corrected reference energy at the ORCA structure (kcal/mol), plus the fixed-geometry decomposition.

    Conformers whose xtb and ORCA structures are not the same minimum (heavy-atom RMSD above SAME_MINIMUM_RMSD) are listed in `unmapped`, not paired and not counted missing.
    """
    kcal = judge.HARTREE_TO_KCAL
    geo_x, geo_o = ctx.completed("geometry", "xtb"), ctx.completed("geometry", "orca")
    con_x, con_o = ctx.completed("conformers", "xtb"), ctx.completed("conformers", "orca")
    ref, xsp = ctx.completed("reference", "orca"), ctx.completed("reference", "xtb")

    def energies(structure: str, x_done: dict, o_done: dict) -> tuple[float | None, float | None, float | None]:
        x, rf, sp = _find(x_done, structure), _find(ref, structure, start="orca"), _find(xsp, structure, start="orca")
        return (x["energy_hartree"] if x else None, rf["energy_hartree"] if rf else None, sp["energy_hartree"] if sp else None)

    def pair(label: str, a: str, b: str, x_done: dict, o_done: dict) -> dict:
        xa, ra, sa = energies(a, x_done, o_done)
        xb, rb, sb = energies(b, x_done, o_done)
        end = None if None in (xa, xb, ra, rb) else {"xtb_kcal": (xa - xb) * kcal, "reference_kcal": (ra - rb) * kcal}
        fixed = None if None in (sa, sb, ra, rb) else {"xtb_kcal": (sa - sb) * kcal, "reference_kcal": (ra - rb) * kcal}
        return {"label": label, "xtb_kcal": end["xtb_kcal"] if end else None, "reference_kcal": end["reference_kcal"] if end else None, "fixed_geometry": fixed}

    isomers = [pair(f"{a} - {b}", a, b, geo_x, geo_o) for a, b in PAIRS]
    conformer_pairs, unmapped, expected = [], [], 0
    for name in SET_F:
        count = len(conformer_mols(name))
        mapped = []
        for i in range(count):
            structure = f"{name}#{i}"
            x, o = _find(con_x, structure), _find(con_o, structure)
            if x is None or o is None:
                mapped.append(structure)  # a missing job keeps its pairs as missing cells below, never silently dropped
                continue
            if heavy_rmsd(conformer_mols(name)[i], x["coordinates"], o["coordinates"]) > SAME_MINIMUM_RMSD:
                unmapped.append(structure)
            else:
                mapped.append(structure)
        expected += count * (count - 1) // 2
        for a, b in combinations(mapped, 2):
            conformer_pairs.append(pair(f"{a} - {b}", a, b, con_x, con_o))
    return {"isomers": isomers, "conformers": conformer_pairs, "unmapped": unmapped, "expected_conformer_pairs": expected}


def preopt_rows(ctx: Context) -> list[dict]:
    """C3's rows: ORCA `Opt` from the MMFF start against from the xtb start, with the xtb time added to the second."""
    base, pre, xtb = ctx.completed("geometry", "orca"), ctx.completed("preopt", "orca"), ctx.completed("geometry", "xtb")
    rows = []
    for name in JUDGED:
        a, b, x = _find(base, name, method=PRIMARY), _find(pre, name, start="xtb"), _find(xtb, name, method=XTB_METHOD)
        rows.append({
            "molecule": name,
            "cycles_mmff": a.get("cycles") if a else None, "cycles_xtb": b.get("cycles") if b else None,
            "energy_mmff": a["energy_hartree"] if a else None, "energy_xtb": b["energy_hartree"] if b else None,
            "seconds_mmff": a["seconds"] if a else None, "seconds_xtb_total": (b["seconds"] + x["seconds"]) if b and x else None,
        })
    return rows


def records_consistent(ctx: Context) -> str | None:
    """The reason the records cannot be judged together (more than one commit, or a dirty `src/`), or None."""
    commits, dirty = set(), False
    for stage in STAGES:
        for engine in ("orca", "psi4", "xtb"):
            for record in ctx.records(stage, engine):
                commits.add(record["commit"])
                dirty = dirty or bool(record["dirty"])
    if len(commits) > 1:
        return f"the records come from {len(commits)} different commits"
    if dirty:
        return "some records were made with a dirty src/"
    return None


def report(ctx: Context) -> int:
    inconsistent = records_consistent(ctx)
    lines: list[str] = []
    verdicts: dict = {}
    if inconsistent:
        for claim in ("C1", "C2", "C3"):
            verdicts[claim] = {"verdict": judge.NOT_EVALUABLE, "reason": inconsistent}
        lines.append(f"NOT EVALUABLE for all claims: {inconsistent}")
    else:
        floors, reported_floors = floors_from(ctx)
        c1 = judge.judge_geometry(geometry_rows(ctx), floors)
        pairs = relative_pairs(ctx)
        all_pairs = pairs["isomers"] + pairs["conformers"]
        c2 = judge.judge_relative(all_pairs, conformer_pairs=len([p for p in pairs["conformers"] if p["xtb_kcal"] is not None]), total_cells=len(all_pairs))
        c3 = judge.judge_preoptimizer(preopt_rows(ctx), floors, total_cells=len(JUDGED))
        for verdict in (c1, c2, c3):
            verdicts[verdict.claim] = {"verdict": verdict.verdict, "reason": verdict.reason, "numbers": verdict.numbers}
            lines.append(str(verdict))
        lines += ["", f"ORCA optimizer floor: {floors.orca_opt_energy_meh:.4f} mEh, {floors.orca_opt_rmsd_angstrom:.5f} A; same-minimum tolerance {floors.same_minimum_meh:.4f} mEh",
                  f"xtb floors (reported): {json.dumps(reported_floors)}", f"reported aside (decides nothing): {json.dumps(reported_aside(ctx))}", f"conformers not on the same minimum (reported): {pairs['unmapped']}",
                  f"conformer pairs expected {pairs['expected_conformer_pairs']}, present {len(pairs['conformers'])}",
                  "fixed-geometry decomposition (reported, decides nothing): " + json.dumps([{"label": p["label"], **p["fixed_geometry"]} for p in all_pairs if p["fixed_geometry"]][:60])]
    (ctx.out).mkdir(parents=True, exist_ok=True)
    (ctx.out / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ctx.out / "verdict.json").write_text(json.dumps({"commit": ctx.commit, "verdicts": verdicts}, indent=1), encoding="utf-8")
    print("\n".join(lines))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["list", "report", *STAGES])
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--out", type=Path, default=HERE / "artifacts")
    args = parser.parse_args(argv)
    if args.stage == "list":
        for stage, jobs in STAGES.items():
            print(f"{stage:11s} {len(jobs()):4d} jobs")
        return 0
    ctx = Context(args.out, args.cores, args.workers)
    if args.stage == "report":
        return report(ctx)
    run_all(ctx, STAGES[args.stage]())
    return 0


if __name__ == "__main__":
    sys.exit(main())
