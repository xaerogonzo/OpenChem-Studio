"""Runs the PRIMARY arm of the bond-dissociation benchmark of `PREREGISTRATION.md` (M062X/def2-TZVPD optimization and frequencies of each parent and each radical, one hydrogen-atom single point) and writes its verdict.

    python run_bde.py structures                    build every starting structure (RDKit; no ORCA): artifacts/structures.json
    python run_bde.py run [--workers 3] [--cores 4] the ORCA jobs (resumes; a completed job is never repeated)
    python run_bde.py report                        report.txt, verdict.json (the judge's verdict, primary arm)
    python run_bde.py status                        how many structures and jobs there are and how many are done

The secondary arm (DLPNO-CCSD(T) single points on these geometries) is a later stage and is not here. **Every rule is in `PREREGISTRATION.md`; the arithmetic is `bde_core.py` and the verdict `judge.py`.**
A report is refused (NOT EVALUABLE) for records from more than one commit or made with a dirty `src/`. ORCA is `D:\\ORCA\\orca.exe`.

The structure, conformer and ORCA-output machinery is the proton-affinity runner's (`benchmarks/proton_affinity/run_pa.py`), loaded by path: the same ETKDG seed, MMFF relaxation, RMSD dedupe, output parser and bond perception, so the two benchmarks cannot drift apart.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from rdkit import Chem

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PA_DIRECTORY = REPO / "benchmarks" / "proton_affinity"


def _load(name: str, path: Path, needs_path: Path | None = None):
    """Loads a module by path under a unique name. `run_pa` imports its siblings `judge` and `pa_core` by plain name, which would shadow this benchmark's own `judge`, so those two names are taken back out afterwards."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    saved = {key: sys.modules.pop(key, None) for key in ("judge", "pa_core")}
    if needs_path:
        sys.path.insert(0, str(needs_path))
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if needs_path:
            sys.path.remove(str(needs_path))
        for key, value in saved.items():
            sys.modules.pop(key, None)
            if value is not None:
                sys.modules[key] = value
    return module


pa = _load("proton_affinity_run_pa", PA_DIRECTORY / "run_pa.py", needs_path=PA_DIRECTORY)
core = _load("bde_run_core", HERE / "bde_core.py")
judge = _load("bde_run_judge", HERE / "judge.py")

ORCA = pa.ORCA
HEADER = pa.HEADER
ATOM_HEADER = "! M062X def2-TZVPD TightSCF DefGrid3"
IMAGINARY_CM = pa.IMAGINARY_CM
JOB_TIMEOUT_SECONDS = pa.JOB_TIMEOUT_SECONDS
LOCK = threading.Lock()
ATOM_ID = "atom|H"


# --- structures -------------------------------------------------------------------------------------------------------------


def reference_bonds() -> list[dict]:
    return json.loads((HERE / "reference_values.json").read_text(encoding="utf-8"))["bonds"]


def parent_molecule(smiles: str) -> Chem.Mol:
    """The closed-shell parent with explicit hydrogens, which RDKit appends after the heavy atoms, so a heavy atom's index is the one the SMILES gives it."""
    return Chem.AddHs(Chem.MolFromSmiles(smiles))


def build_structures() -> list[dict]:
    """Every starting structure: each distinct parent's kept conformers once, one radical start per bond and kept parent conformer, and the hydrogen atom."""
    structures: list[dict] = []
    conformers: dict[str, list[np.ndarray]] = {}
    for bond in reference_bonds():
        smiles = bond["smiles"]
        mol = parent_molecule(smiles)
        symbols = [a.GetSymbol() for a in mol.GetAtoms()]
        if smiles not in conformers:
            conformers[smiles] = pa.conformers_of(mol)
            for k, xyz in enumerate(conformers[smiles]):
                structures.append({"id": f"parent|{smiles}|{k}", "role": "parent", "smiles": smiles, "charge": 0, "mult": 1, "symbols": symbols, "coordinates": xyz.tolist()})
        neighbors = [n.GetIdx() for n in mol.GetAtomWithIdx(bond["atom"]).GetNeighbors()]
        for k, xyz in enumerate(conformers[smiles]):
            radical_symbols, radical_xyz = core.radical_start(symbols, xyz, bond["atom"], neighbors)
            structures.append({"id": f"radical|{bond['name']}|{k}", "role": "radical", "bond": bond["name"], "smiles": smiles, "atom": bond["atom"], "charge": 0, "mult": 2,
                               "symbols": radical_symbols, "coordinates": radical_xyz.tolist()})
    structures.append({"id": ATOM_ID, "role": "atom", "charge": 0, "mult": 2, "symbols": ["H"], "coordinates": [[0.0, 0.0, 0.0]]})
    return structures


# --- the ORCA job and its output ---------------------------------------------------------------------------------------------


def orca_input(structure: dict, cores: int, retry: bool = False) -> str:
    """The input of one job: the preregistered keywords, the structure's own charge and multiplicity (a radical's is 2, so ORCA runs it unrestricted), and for the atom a single point."""
    if structure["role"] == "atom":
        lines = [ATOM_HEADER, "%maxcore 3000"]
    else:
        lines = [HEADER, f"%pal nprocs {cores} end", "%maxcore 3000"]
        if retry:
            lines += ["%geom", "  Calc_Hess true", "end"]
    lines.append(f"* xyz {structure['charge']} {structure['mult']}")
    lines += [f"{s:<3}{x:>14.8f}{y:>14.8f}{z:>14.8f}" for s, (x, y, z) in zip(structure["symbols"], structure["coordinates"])]
    lines += ["*", ""]
    return "\n".join(lines)


def parse_s2(text: str) -> float | None:
    """The unrestricted <S**2> of the LAST SCF of the output (an optimization prints one per geometry; the last belongs to the final structure); None for a restricted run."""
    found = re.findall(r"Expectation value of <S\*\*2>\s+:\s+(-?\d+\.\d+)", text)
    return float(found[-1]) if found else None


def parse_atom(text: str) -> dict:
    """The hydrogen atom's electronic energy from its single-point output; raises ValueError if the job did not finish normally."""
    if "ORCA TERMINATED NORMALLY" not in text:
        raise ValueError("the atom's job did not finish normally")
    found = re.findall(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", text)
    if not found:
        raise ValueError("no energy in the atom's output")
    return {"energy": float(found[-1]), "s2": parse_s2(text), "orca_version": (re.findall(r"Program Version\s+(\S+)", text) or [None])[-1]}


def parse_species(text: str) -> dict:
    """One Opt Freq output of a parent or radical: the proton-affinity runner's reading (energy, enthalpy, frequencies, final geometry, 298.15 K and 1 atm checked) plus the radical's <S**2>."""
    return dict(pa.parse_output(text), s2=parse_s2(text))


def heavy_bonds(mol: Chem.Mol) -> set[tuple[int, int]]:
    return {tuple(sorted((b.GetBeginAtomIdx(), b.GetEndAtomIdx()))) for b in mol.GetBonds() if b.GetBeginAtom().GetAtomicNum() > 1 and b.GetEndAtom().GetAtomicNum() > 1}


def same_skeleton(structure: dict, result: dict) -> bool:
    """Whether an optimized structure is still the species it was meant to be: the parent's heavy-atom bonds and hydrogen counts, minus ONE hydrogen on the named atom for a radical.

    A radical that ORCA took to a rearranged structure (a hydrogen that migrated, a ring or chain that opened) has a lower energy and is not the radical of the bond; it is a failed structure, not a low one. Perception is from the optimized distances only (covalent radii + 0.4 Angstrom)."""
    mol = parent_molecule(structure["smiles"])
    perceived = pa.connectivity(result["symbols"], result["coordinates"])
    expected = pa.hydrogen_counts(mol)
    if structure["role"] == "radical":
        expected[structure["atom"]] -= 1
    return heavy_bonds(perceived) == heavy_bonds(mol) and pa.hydrogen_counts(perceived) == expected


def finish(structure: dict, result: dict) -> dict:
    return dict(result, skeleton_kept=same_skeleton(structure, result))


# --- selection and the report -----------------------------------------------------------------------------------------------


def accepted(records: list[dict]) -> list[dict]:
    """The records that count: a completed job (a species also with no imaginary frequency and its skeleton kept). A structure's retry replaces its first attempt."""
    latest: dict[str, dict] = {}
    for record in records:
        if record.get("completed"):
            latest[record["structure"]] = record
    return [r for r in latest.values() if r["role"] == "atom" or (r["lowest_frequency"] >= IMAGINARY_CM and r["skeleton_kept"])]


def hydrogen_enthalpy(records: list[dict]) -> float | None:
    atoms = [r for r in records if r["role"] == "atom"]
    return core.hydrogen_atom_enthalpy(atoms[-1]["energy"]) if atoms else None


def select(records: list[dict], bond: dict) -> dict | None:
    """The bond's DH298 (Hartree) from its accepted records: the lowest-enthalpy parent structure and radical structure; None if either, or the hydrogen atom, is missing. Also the radical's <S**2> and how many structures were used."""
    parents = [r for r in records if r["role"] == "parent" and r["smiles"] == bond["smiles"]]
    radicals = [r for r in records if r["role"] == "radical" and r["bond"] == bond["name"]]
    h_atom = hydrogen_enthalpy(records)
    if not parents or not radicals or h_atom is None:
        return None
    parent, radical = min(parents, key=lambda r: r["enthalpy"]), min(radicals, key=lambda r: r["enthalpy"])
    return {"value_eh": core.bond_dissociation_enthalpy(parent["enthalpy"], radical["enthalpy"], h_atom), "s2": radical.get("s2"), "structures": len(parents) + len(radicals)}


def judge_records(records: list[dict], bonds: list[dict]) -> list[dict]:
    done = accepted(records)
    rows = []
    for bond in bonds:
        picked = select(done, bond)
        rows.append({"name": bond["name"], "dh_ref": bond["dh298"], "uncertainty": bond["uncertainty"], "dh_kcal": picked["value_eh"] * core.HARTREE_TO_KCAL if picked else None,
                     "s2": picked["s2"] if picked else None})
    return rows


def provenance_problem(records: list[dict]) -> str | None:
    commits = {r["commit"] for r in records}
    if len(commits) > 1:
        return f"the records come from {len(commits)} commits: {sorted(c[:8] for c in commits)}"
    if any(r["dirty"] for r in records):
        return "some records were made with a dirty src/"
    return None


def bond_class(name: str) -> str:
    """The class a bond is reported under: its element, with the peroxides apart (the multireference-looking cases)."""
    element = name.split()[-1]
    return "peroxide O-H" if "peroxide" in name else element


def _stats_line(label: str, s) -> str:
    f = lambda v, sign=False: "-" if v is None else (f"{v:+.2f}" if sign else f"{v:.2f}")  # noqa: E731
    return f"{label:34s} n={s.count:2d} missing={s.missing:2d} MAE={f(s.mae)} MSE={f(s.mse, True)} max={f(s.max_abs)} kcal/mol"


def report_text(records: list[dict], bonds: list[dict]) -> tuple[str, dict]:
    problem = provenance_problem(records)
    rows = judge_records(records, bonds)
    result = judge.judge(rows, "primary")
    verdict = judge.NOT_EVALUABLE if problem else result["verdict"]
    done = accepted(records)
    lines = [f"PRIMARY ARM (M062X/def2-TZVPD), {len(done)} accepted structures of {len(records)} jobs" + (f"; REFUSED: {problem}" if problem else ""),
             _stats_line("deciding (25, uncertainty <= 1.0)", result["deciding"]), _stats_line("loose reference (8, reported only)", result["low"]), _stats_line("all 33", result["all"]),
             f"VERDICT {verdict}", "", "by class (all bonds, reported only):"]
    classes = sorted({bond_class(r["name"]) for r in rows})
    for cls in classes:
        lines.append(_stats_line(f"  {cls}", judge.stats([r for r in rows if bond_class(r["name"]) == cls])))
    lines += ["", f"{'bond':32s} {'calc':>8s} {'ref':>8s} {'error':>7s} {'<S2>':>6s}"]
    contaminated = []
    for row in rows:
        error = "missing" if row["dh_kcal"] is None else f"{row['dh_kcal'] - row['dh_ref']:+.2f}"
        flag = row["s2"] is not None and core.spin_contaminated(row["s2"])
        if flag:
            contaminated.append(row["name"])
        marker = " *" if judge.is_low(row) else ""
        calc = "-" if row["dh_kcal"] is None else f"{row['dh_kcal']:.2f}"
        s2 = "-" if row["s2"] is None else f"{row['s2']:.3f}{'!' if flag else ''}"
        lines.append(f"{row['name']:32s} {calc:>8s} {row['dh_ref']:8.2f} {error:>7s} {s2:>6s}{marker}")
    lines += ["", "* loose reference (reported only); ! <S2> above 0.80", f"spin-contaminated radicals: {len(contaminated)}" + (f" ({', '.join(contaminated)})" if contaminated else "")]
    return "\n".join(lines), {"verdict": verdict, "problem": problem}


# --- the commands -----------------------------------------------------------------------------------------------------------


def run_stage(out: Path, cores: int, workers: int) -> None:
    structures = json.loads((out / "structures.json").read_text(encoding="utf-8"))
    path = out / "primary" / "runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src"], capture_output=True, text=True, cwd=REPO).stdout.strip())

    def done_ids() -> set[str]:
        records = pa.records_of(path)
        return {r["structure"] for r in accepted(records)} | {r["structure"] for r in records if r.get("final")}

    pending = [s for s in structures if s["id"] not in done_ids()]
    print(f"{len(structures) - len(pending)} done, {len(pending)} to run", flush=True)

    def append(record: dict) -> None:
        with LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def attempt(structure: dict, retry: bool) -> dict:
        scratch = Path(tempfile.mkdtemp(prefix="bde_"))
        record = {"structure": structure["id"], "role": structure["role"], "retry": retry, "commit": commit, "dirty": dirty, "completed": False}
        for key in ("smiles", "bond"):
            if key in structure:
                record[key] = structure[key]
        began = time.time()
        try:
            (scratch / "job.inp").write_text(orca_input(structure, cores, retry), encoding="utf-8")
            completed = subprocess.run([ORCA, "job.inp"], cwd=scratch, capture_output=True, text=True, timeout=JOB_TIMEOUT_SECONDS)
            text = completed.stdout or ""
            record.update(parse_atom(text) if structure["role"] == "atom" else finish(structure, parse_species(text)))
            record["completed"] = True
        except subprocess.TimeoutExpired:
            record["error"] = f"timeout after {JOB_TIMEOUT_SECONDS} s"
        except Exception as error:  # noqa: BLE001 - a failed job is a missing structure, recorded with its reason
            record["error"] = f"{type(error).__name__}: {error}"[:300]
        finally:
            record["seconds"] = round(time.time() - began, 1)
            shutil.rmtree(scratch, ignore_errors=True)
        return record

    def work(structure: dict) -> None:
        record = attempt(structure, retry=False)
        append(record)
        if record["completed"] and structure["role"] != "atom" and record["lowest_frequency"] < IMAGINARY_CM:
            # one re-run from the structure's own final geometry, with an initial Hessian (PREREGISTRATION.md); it replaces the first attempt
            again = dict(structure, symbols=record["symbols"], coordinates=record["coordinates"])
            retried = attempt(again, retry=True)
            retried["final"] = True
            append(retried)
        print(f"{structure['id']}  completed={record['completed']}  {record['seconds']} s  {record.get('error', '')}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, pending))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["structures", "run", "report", "status"])
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--out", default=str(HERE / "artifacts"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.command == "structures":
        structures = build_structures()
        (out / "structures.json").write_text(json.dumps(structures), encoding="utf-8")
        roles = [s["role"] for s in structures]
        print(f"{len(structures)} structures ({roles.count('parent')} parent, {roles.count('radical')} radical, {roles.count('atom')} atom) for {len(reference_bonds())} bonds")
    elif args.command == "run":
        run_stage(out, args.cores, args.workers)
    elif args.command == "status":
        structures = json.loads((out / "structures.json").read_text(encoding="utf-8"))
        records = pa.records_of(out / "primary" / "runs.jsonl")
        print(f"{len(structures)} structures, {len({r['structure'] for r in records if r.get('completed')})} completed, {len(accepted(records))} accepted")
    else:
        records = pa.records_of(out / "primary" / "runs.jsonl")
        text, verdict = report_text(records, reference_bonds())
        print(text)
        (out / "report.txt").write_text(text, encoding="utf-8")
        (out / "verdict.json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
