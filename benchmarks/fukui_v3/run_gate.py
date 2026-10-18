"""Runs the third Fukui gate (`PREREGISTRATION.md`) with real ORCA, through the application's own input builder and parse, and judges it with `openchem.app.fukui_gate_3`.

    python run_gate.py floors      the two noise floors (same input twice; the whole chain twice) on acetaldehyde and ethylene
    python run_gate.py r           arm R: the reference run and its perturbations of every panel species
    python run_gate.py c           arm C: the exhaustive search (holes down to the HOMO-7) on every panel species' reference geometry
    python run_gate.py n           arm N: the eight species of the second gate with this calculation, against the published numbers
    python run_gate.py reported    the reported arm: benzene and methane (seen); then `report` writes reported.json: the recall of the note under perturbation, how often the default job was not on the lowest state, timings
    python run_gate.py judge       reads the records and writes verdict.json

Common options: ``--out DIR`` (default `artifacts/` beside this file), ``--cores 4`` per ORCA job, ``--workers 6`` jobs at once, ``--species NAME`` to run one species.

Every ORCA job goes through `OrcaQuantumEngineProvider.build_input` (the cation search ON, as the application's default) and is read with `_condensed_fukui` (what `parse_per_atom_output` calls), so the
numbers are the application's own. **A job that did not finish may be repeated unchanged up to `MAX_ATTEMPTS` times; a job that completed is never repeated** (a record with `completed: true` is
read back, not run again). The records are JSON lines in `runs.jsonl`, one per attempt, carrying the commit, whether `src/` differed from it, the ORCA version and the sha256 of the input.
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
from rdkit.Chem import AllChem, rdMolTransforms
from rdkit.Geometry import Point3D

from openchem.app import fukui_gate_2 as second
from openchem.app import fukui_gate_3 as gate
from openchem.chem.fukui_plan import has_diffuse_functions, searchable_holes
from openchem.chem.orca_engine import _CALC_TYPE_KEYWORDS, OrcaOutputError, OrcaQuantumEngineProvider, add_parallel_block

ORCA = r"D:\ORCA\orca.exe"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HARTREE_TO_EV = 27.211386245988
COORDS = re.compile(r"^\s*([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")
#: One rng stream per species, seeded from its place in the panel: the rotations, then the displacements. Fixed here, before any run.
SEED_BASE = 20261019

LOCK = threading.Lock()


class Context:
    def __init__(self, out: Path, cores: int, workers: int) -> None:
        self.out, self.cores, self.workers = out, cores, workers
        out.mkdir(parents=True, exist_ok=True)
        self.scratch = Path(tempfile.mkdtemp(prefix="fukui_v3_"))
        self.runs_path = out / "runs.jsonl"
        self.geometries_path = out / "geometries.json"
        self.commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
        self.dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src"], capture_output=True, text=True, cwd=REPO).stdout.strip())
        self.provider = OrcaQuantumEngineProvider(cation_search=lambda: True)
        self._geometries: dict[str, list[list[float]]] = json.loads(self.geometries_path.read_text()) if self.geometries_path.exists() else {}

    # -- the store ---------------------------------------------------------------------------------------------------------
    def records(self) -> list[dict]:
        if not self.runs_path.exists():
            return []
        return [json.loads(line) for line in self.runs_path.read_text().splitlines() if line.strip()]

    def append(self, record: dict) -> None:
        with LOCK:
            with self.runs_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")

    def completed(self, species: str, variant: str, kind: str) -> dict | None:
        return next((r for r in self.records() if (r["species"], r["variant"], r["kind"]) == (species, variant, kind) and r["completed"]), None)

    def attempts(self, species: str, variant: str, kind: str) -> int:
        return sum(1 for r in self.records() if (r["species"], r["variant"], r["kind"]) == (species, variant, kind))

    # -- geometries --------------------------------------------------------------------------------------------------------
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
    AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
    return mol


def with_coordinates(mol: Chem.Mol, xyz: np.ndarray) -> Chem.Mol:
    clone = Chem.Mol(mol)
    conf = clone.GetConformer()
    for index, (x, y, z) in enumerate(xyz):
        conf.SetAtomPosition(index, Point3D(float(x), float(y), float(z)))
    return clone


def optimized(ctx: Context, key: str, smiles: str, charge: int, method_basis: str, seed: int, *, s_trans: bool = False) -> np.ndarray:
    """The ORCA optimization of an RDKit ETKDG + MMFF embedding (the probe's recipe), cached under `key`.

    `s_trans` starts from the O=C-C=C dihedral set to 180 degrees (acrolein's four heavy atoms are 0 to 3 in the order the application embeds them), for the molecule the source published: its
    s-cis minimum is a different planar minimum, and ORCA stays in whichever it is started in."""
    cached = ctx.geometry(key)
    if cached is not None:
        return cached
    mol = embed(smiles, seed)
    if s_trans:
        rdMolTransforms.SetDihedralDeg(mol.GetConformer(), 0, 1, 2, 3, 180.0)
    conf = mol.GetConformer()
    start = [f"{a.GetSymbol():<3}{conf.GetAtomPosition(a.GetIdx()).x:>14.6f}{conf.GetAtomPosition(a.GetIdx()).y:>14.6f}{conf.GetAtomPosition(a.GetIdx()).z:>14.6f}" for a in mol.GetAtoms()]
    out, _code, _seconds = orca(ctx, f"{key}_opt", f"! {method_basis} Opt\n* xyz {charge} 1\n" + "\n".join(start) + "\n*\n")
    if "THE OPTIMIZATION HAS CONVERGED" not in out:
        raise RuntimeError(f"the optimization of {key} did not converge")
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
    return np.array(atoms)


def random_rotation(rng: np.random.Generator) -> np.ndarray:
    q, r = np.linalg.qr(rng.normal(size=(3, 3)))
    q = q * np.sign(np.diag(r))
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    return q


def symmetry_classes(smiles: str) -> list[list[int]]:
    """The atoms of the molecule as the application embeds it, grouped by topological equivalence."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
    groups: dict[int, list[int]] = {}
    for index, rank in enumerate(ranks):
        groups.setdefault(rank, []).append(index)
    return list(groups.values())


def states_of(reading) -> list[dict]:
    """Every distinct state a reading holds within the window (the ones read, then the competing), lowest first, as {energy_hartree, charges}."""
    states = [*reading.averaged, *reading.competing]
    return sorted(({"energy_hartree": s.energy_hartree, "charges": list(s.charges)} for s in states), key=lambda s: s["energy_hartree"])


def fukui_run(ctx: Context, kind: str, species_name: str, variant: str, mol: Chem.Mol, charge: int, method_basis: str, *, holes: tuple[int, ...] | None = None, extra: dict | None = None) -> dict:
    """One Fukui job and its record. `holes` replaces the application's holes (the exhaustive search); None is the application's own input."""
    done = ctx.completed(species_name, variant, kind)
    if done is not None:
        return done
    attempt = ctx.attempts(species_name, variant, kind) + 1
    provider = ctx.provider
    if holes is None:
        text = provider.build_input(mol, charge, 1, method_basis, "fukui")
    else:
        conf = mol.GetConformer()
        coordinates = [f"{a.GetSymbol():<3}{conf.GetAtomPosition(a.GetIdx()).x:>14.6f}{conf.GetAtomPosition(a.GetIdx()).y:>14.6f}{conf.GetAtomPosition(a.GetIdx()).z:>14.6f}" for a in mol.GetAtoms()]
        search = searchable_holes([a.GetAtomicNum() for a in mol.GetAtoms()], charge, offsets=holes)
        header = f"! {method_basis} {_CALC_TYPE_KEYWORDS['fukui']}".strip()
        text = provider._build_fukui_input(header, coordinates, charge, 1, diffuse=has_diffuse_functions(method_basis), holes=search.offsets, homo=search.homo)
    out, code, seconds = orca(ctx, f"{species_name}_{variant}_{kind}_{attempt}", text)
    record = {
        "kind": kind, "species": species_name, "variant": variant, "attempt": attempt, "commit": ctx.commit, "dirty": ctx.dirty, "seconds": round(seconds, 1), "orca_exit": code,
        "input_sha256": hashlib.sha256(add_parallel_block(text, ctx.cores).encode()).hexdigest(), "method_basis": method_basis, "charge": charge,
        "orca_version": (re.search(r"Program Version\s+(\S+)", out) or [None, None])[1], **(extra or {}),
    }
    try:
        result = provider._condensed_fukui(out, mol)
    except OrcaOutputError as error:
        record.update({"completed": False, "error": str(error)})
        ctx.append(record)
        return record
    reading = result.cation_reading
    record.update({
        "completed": True, "f_minus": list(result.f_minus), "f_plus": list(result.f_plus), "f_zero": list(result.f_zero), "dual": list(result.dual), "symbols": [a.GetSymbol() for a in mol.GetAtoms()],
        "states": states_of(reading) if reading is not None else [], "states_found": (len(reading.averaged) + len(reading.competing) + reading.farther) if reading else None,
        "competing_ev": [round(s.above_ev, 4) for s in reading.competing] if reading else [], "degenerate": bool(reading and reading.degenerate), "incomplete": bool(reading and reading.incomplete),
        "cation_note": result.cation_note, "default_above_lowest_ev": ((reading.default.energy_hartree - reading.energy_hartree) * HARTREE_TO_EV) if reading else None,
    })
    ctx.append(record)
    return record


def run_with_attempts(ctx: Context, kind: str, species_name: str, variant: str, mol: Chem.Mol, charge: int, method_basis: str, **kwargs) -> dict:
    for _ in range(gate.MAX_ATTEMPTS):
        record = fukui_run(ctx, kind, species_name, variant, mol, charge, method_basis, **kwargs)
        if record["completed"]:
            return record
    return record


# --- the arms ------------------------------------------------------------------------------------------------------------------


def panel_species(only: str | None, extra=()):
    return [s for s in (*gate.PANEL, *extra) if only in (None, s.name)]


def species_seed(name: str) -> int:
    names = [s.name for s in (*gate.PANEL, *gate.FLOOR_SPECIES, *gate.REPORTED_SPECIES)]
    return SEED_BASE + names.index(name)


def variant_geometry(ctx: Context, species: gate.PanelSpecies, variant: str) -> np.ndarray:
    """The coordinates of one variant: the optimized reference geometry (seed 7), its rotations and displacements (one rng stream per species), or an optimization from another embedding."""
    base = optimized(ctx, f"{species.name}_reference", species.smiles, species.charge, species.method_basis, 7)
    if variant == "reference":
        return base
    if variant.startswith("embedding"):
        seed = int(variant.removeprefix("embedding"))
        return optimized(ctx, f"{species.name}_{variant}", species.smiles, species.charge, species.method_basis, seed)
    rng = np.random.default_rng(species_seed(species.name))
    rotations = [random_rotation(rng) for _ in range(gate.ROTATIONS)]
    displaced = [base + rng.normal(scale=gate.DISPLACEMENT_SIGMA, size=base.shape) for _ in range(gate.DISPLACEMENTS)]
    if variant.startswith("rotation"):
        return base @ rotations[int(variant.removeprefix("rotation"))].T
    return displaced[int(variant.removeprefix("displacement"))]


def arm_r(ctx: Context, only: str | None) -> None:
    species_list = panel_species(only)
    # Phase 1: every ORCA optimization (the reference geometry of each species and the independent ones), in parallel and each once, so that two workers never optimize one key twice.
    keys = []
    for species in species_list:
        keys.append((f"{species.name}_reference", species, 7))
        keys += [(f"{species.name}_embedding{seed}", species, seed) for seed in gate.EMBEDDING_SEEDS if species.embeddings]

    def optimize(item):
        key, species, seed = item
        optimized(ctx, key, species.smiles, species.charge, species.method_basis, seed)
        print(f"optimized {key}", flush=True)

    with ThreadPoolExecutor(max_workers=ctx.workers) as pool:
        list(pool.map(optimize, keys))

    # Phase 2: the Fukui runs.
    tasks = []
    for species in species_list:
        mol = embed(species.smiles, 7)
        for variant in species.variants():
            tasks.append((species, variant, mol))

    def work(task):
        species, variant, mol = task
        record = run_with_attempts(ctx, "R", species.name, variant, with_coordinates(mol, variant_geometry(ctx, species, variant)), species.charge, species.method_basis)
        print(f"R {species.name:13s} {variant:14s} completed={record['completed']} {record['seconds']} s", flush=True)

    with ThreadPoolExecutor(max_workers=ctx.workers) as pool:
        list(pool.map(work, tasks))


def arm_c(ctx: Context, only: str | None) -> None:
    def work(species):
        mol = with_coordinates(embed(species.smiles, 7), variant_geometry(ctx, species, "reference"))
        record = run_with_attempts(ctx, "C", species.name, "exhaustive", mol, species.charge, species.method_basis, holes=gate.EXHAUSTIVE_OFFSETS)
        print(f"C {species.name:13s} completed={record['completed']} {record['seconds']} s", flush=True)

    with ThreadPoolExecutor(max_workers=ctx.workers) as pool:
        list(pool.map(work, panel_species(only)))


def arm_n(ctx: Context, only: str | None) -> None:
    def work(name):
        species = second.SPECIES[name]
        mol = embed(species.smiles, 7)
        # Acrolein is started s-trans (the published molecule): its first run, from the seed-7 embedding, stayed in the s-cis minimum (dihedral 0.01 degrees), the judge refused it as input
        # validity (the run is kept in runs.jsonl as variant "reference"), and it was repeated from this start as variant "s-trans" (PREREGISTRATION.md 7 and 9: NOT EVALUABLE may be repeated after its cause is fixed).
        s_trans = name == "acrolein"
        key = f"N_{name}_strans" if s_trans else f"N_{name}"
        base = optimized(ctx, key, species.smiles, species.charge, species.method_basis, 7, s_trans=s_trans)
        # Acrolein has two planar minima and the published one is s-trans: its optimized O=C-C=C dihedral is recorded with the run, and the judge refuses it beyond the second gate's limit.
        extra = {"dihedral_degrees": second.acrolein_dihedral(list(species.labels), base.tolist())} if name == "acrolein" else None
        record = run_with_attempts(ctx, "N", name, "s-trans" if s_trans else "reference", with_coordinates(mol, base), species.charge, species.method_basis, extra=extra)
        print(f"N {name:14s} completed={record['completed']} {record['seconds']} s", flush=True)

    with ThreadPoolExecutor(max_workers=ctx.workers) as pool:
        list(pool.map(work, [n for n in gate.N_SPECIES if only in (None, n)]))


def floor_difference(a: dict, b: dict, classes) -> float:
    worst = 0.0
    for name in ("f_minus", "f_plus", "f_zero", "dual"):
        worst = max(worst, gate.class_sorted_difference(a[name], b[name], classes))
    return worst


def arm_floors(ctx: Context) -> None:
    results = []
    for species in gate.FLOOR_SPECIES:
        classes = symmetry_classes(species.smiles)
        base = optimized(ctx, f"{species.name}_reference", species.smiles, species.charge, species.method_basis, 7)
        mol = with_coordinates(embed(species.smiles, 7), base)
        first = run_with_attempts(ctx, "floor", species.name, "first", mol, species.charge, species.method_basis)
        second_run = run_with_attempts(ctx, "floor", species.name, "same-input-again", mol, species.charge, species.method_basis)
        other = optimized(ctx, f"{species.name}_chain2", species.smiles, species.charge, species.method_basis, 11)
        chain = run_with_attempts(ctx, "floor", species.name, "chain-again", with_coordinates(embed(species.smiles, 11), other), species.charge, species.method_basis)
        results.append({
            "species": species.name, "same_input_twice": floor_difference(first, second_run, classes), "whole_chain_twice": floor_difference(first, chain, classes),
        })
        print(results[-1], flush=True)
    (ctx.out / "floors.json").write_text(json.dumps({"floors": results, "floor": max(max(r["same_input_twice"], r["whole_chain_twice"]) for r in results)}, indent=1))


def judged(ctx: Context) -> dict:
    records = ctx.records()
    # Of the attempts of one run the completed one decides, and otherwise the last.
    by_key: dict[tuple, dict] = {}
    for record in (r for r in records if r["kind"] == "R"):
        key = (record["species"], record["variant"])
        if key not in by_key or record["completed"] or not by_key[key]["completed"]:
            by_key[key] = record
    runs = list(by_key.values())
    exhaustive = []
    for species in gate.PANEL:
        reference = by_key.get((species.name, "reference"))
        record = next((r for r in records if r["kind"] == "C" and r["species"] == species.name and r["completed"]), None)
        if record is None:
            failed = [r for r in records if r["kind"] == "C" and r["species"] == species.name]
            if failed:
                exhaustive.append({"species": species.name, "completed": False})
            continue
        exhaustive.append({"species": species.name, "completed": True, "states_application": reference["states"], "states_exhaustive": record["states"]})
    published = []
    for name in gate.N_SPECIES:
        # The last completed run of the species: acrolein's first run (s-cis, refused as input) is kept in the file and superseded by its s-trans one.
        record = next((r for r in reversed(records) if r["kind"] == "N" and r["species"] == name and r["completed"]), None)
        if record is None:
            continue
        species = second.SPECIES[name]
        published.append(second.MeasuredRun(
            name, species.level, tuple(record["symbols"]), tuple(record["f_plus"]), tuple(record["f_minus"]), tuple(record["f_zero"]), tuple(record["dual"]), species.charge, 1,
            record["orca_version"], species.method_basis, second.GRID, second.FUNCTIONS_FULL, species.charge, True, True, record["commit"], record["dirty"],
            record.get("dihedral_degrees"),
        ))
    floors = json.loads((ctx.out / "floors.json").read_text())["floor"] if (ctx.out / "floors.json").exists() else None
    classes = {species.name: symmetry_classes(species.smiles) for species in gate.PANEL}
    verdict = gate.judge(runs=runs, exhaustive=exhaustive, published_runs=published, floor=floors, classes=classes)
    return {
        "outcome": verdict.outcome, "reasons": list(verdict.reasons), "arms": dict(verdict.arms), "floor": floors,
        "reproducibility": [vars(row) for row in verdict.reproducibility], "completeness": [{**vars(row), "missed": list(row.missed)} for row in verdict.completeness],
        "regression": [vars(row) for row in verdict.regression], "sites": list(verdict.site_rows),
    }


def reported_summary(ctx: Context) -> dict:
    """The reported arm's numbers (PREREGISTRATION.md section 10), from the records: nothing here decides."""
    records = [r for r in ctx.records() if r["kind"] == "R" and r["completed"]]
    species_rows = []
    for species in gate.PANEL:
        runs = [r for r in records if r["species"] == species.name]
        reference = next((r for r in runs if r["variant"] == "reference"), None)
        perturbed = [r for r in runs if r["variant"] != "reference"]
        noted = lambda record: bool([gap for gap in record["competing_ev"]]) or record["degenerate"]  # noqa: E731
        species_rows.append({
            "species": species.name,
            "reference_reported_a_competing_state": bool(reference and noted(reference)),
            "runs_with_a_note": sum(1 for r in perturbed if noted(r)), "perturbed_runs": len(perturbed),
            "runs_whose_default_state_was_not_the_lowest": sum(1 for r in runs if (r["default_above_lowest_ev"] or 0.0) > 0.01), "runs": len(runs),
            "largest_default_above_lowest_ev": max((r["default_above_lowest_ev"] or 0.0 for r in runs), default=None),
            "median_seconds": float(np.median([r["seconds"] for r in runs])) if runs else None,
        })
    degenerate = [r for r in ctx.records() if r["kind"] == "reported" and r["completed"]]
    return {"species": species_rows, "degenerate_and_seen": [{k: r[k] for k in ("species", "f_minus", "states_found", "degenerate", "cation_note")} for r in degenerate]}


def arm_reported(ctx: Context, only: str | None) -> None:
    def work(species):
        mol = with_coordinates(embed(species.smiles, 7), optimized(ctx, f"{species.name}_reference", species.smiles, species.charge, species.method_basis, 7))
        record = run_with_attempts(ctx, "reported", species.name, "reference", mol, species.charge, species.method_basis)
        print(f"reported {species.name:10s} completed={record['completed']} note={record.get('cation_note', '')[:120]}", flush=True)

    with ThreadPoolExecutor(max_workers=ctx.workers) as pool:
        list(pool.map(work, [s for s in gate.REPORTED_SPECIES if only in (None, s.name)]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["floors", "r", "c", "n", "reported", "report", "judge"])
    parser.add_argument("--out", type=Path, default=HERE / "artifacts")
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--species")
    args = parser.parse_args()
    ctx = Context(args.out, args.cores, args.workers)
    print(f"commit {ctx.commit} dirty={ctx.dirty} scratch {ctx.scratch}", flush=True)
    if args.command == "floors":
        arm_floors(ctx)
    elif args.command == "r":
        arm_r(ctx, args.species)
    elif args.command == "c":
        arm_c(ctx, args.species)
    elif args.command == "n":
        arm_n(ctx, args.species)
    elif args.command == "reported":
        arm_reported(ctx, args.species)
    elif args.command == "report":
        (ctx.out / "reported.json").write_text(json.dumps(reported_summary(ctx), indent=1))
        print(json.dumps(reported_summary(ctx), indent=1))
    else:
        verdict = judged(ctx)
        (ctx.out / "verdict.json").write_text(json.dumps(verdict, indent=1, default=str))
        print(json.dumps({k: verdict[k] for k in ("outcome", "arms", "reasons", "floor")}, indent=1))


if __name__ == "__main__":
    main()
